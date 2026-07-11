"""End-to-end landscape construction over discovery and provisional identity resolution."""

from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, Field

from bve.se.discovery.orchestrator import DiscoveryOrchestrator, SourceAdapter
from bve.se.evidence.clinicaltrials import ClinicalTrialsEvidenceExtractor
from bve.se.evidence.entailment import EntailmentResult, check_structured_entailment
from bve.se.evidence.ledger import EvidenceLedger
from bve.se.evidence.pubmed import PubMedEvidenceExtractor
from bve.se.gates.engine import GateEngine, GateEvaluation
from bve.se.clinical.cohorts import assign_cohort
from bve.se.clinical.meaningfulness import assess_meaningfulness
from bve.se.resolution.registry import AssetRegistry
from bve.se.ranking.engine import rank_profiles
from bve.se.schemas.contracts import (
    AnalystReviewItem,
    BuyerProblemV2,
    CanonicalAsset,
    ExtractedClaim,
    NormalizedFact,
    OverallDisposition,
    RunManifest,
    SearchAttempt,
    SourceDocument,
    PairwiseProfile,
    RankingResult,
    ClinicalResult,
    CohortAssignment,
    ClinicalMeaningfulness,
)

DEVELOPMENT_SCREEN_LABEL = (
    "Validated development screen; public-data pre-diligence—not production-proven."
)


class SESearchResult(BaseModel):
    problem_id: str
    run_manifest: RunManifest
    candidates: list[CanonicalAsset] = Field(default_factory=list)
    eligible_asset_ids: list[str] = Field(default_factory=list)
    excluded_asset_ids: list[str] = Field(default_factory=list)
    unresolved_asset_ids: list[str] = Field(default_factory=list)
    review_queue: list[AnalystReviewItem] = Field(default_factory=list)
    gate_evaluations: list[GateEvaluation] = Field(default_factory=list)
    source_documents: list[SourceDocument] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    facts: list[NormalizedFact] = Field(default_factory=list)
    entailment_results: list[EntailmentResult] = Field(default_factory=list)
    ranking: RankingResult = Field(default_factory=RankingResult)
    search_attempts: list[SearchAttempt] = Field(default_factory=list)
    clinical_results: list[ClinicalResult] = Field(default_factory=list)
    cohort_assignments: list[CohortAssignment] = Field(default_factory=list)
    clinical_meaningfulness: list[ClinicalMeaningfulness] = Field(default_factory=list)
    label: str = DEVELOPMENT_SCREEN_LABEL


def run_landscape_search(
    problem: BuyerProblemV2,
    adapters: Sequence[SourceAdapter],
    *,
    run_id: str,
    code_version: str,
    normalization_version: str,
    declared_mandatory_sources: Sequence[str] | None = None,
    comparative_profiles: Sequence[PairwiseProfile] | None = None,
) -> SESearchResult:
    discovery = DiscoveryOrchestrator(
        adapters,
        declared_mandatory_sources=declared_mandatory_sources,
    ).run(
        problem,
        run_id=run_id,
        code_version=code_version,
        normalization_version=normalization_version,
    )
    registry = AssetRegistry()
    hit_to_asset: dict[str, str] = {}
    for hit in discovery.hits:
        asset = registry.ingest_hit(hit)
        hit_to_asset[hit.hit_id] = asset.asset_id
    candidates = list(registry.assets.values())
    documents = {document.document_id: document for document in discovery.source_documents}
    ledger = EvidenceLedger()
    for source_document in documents.values():
        ledger.register_document(source_document)
    extractor = ClinicalTrialsEvidenceExtractor()
    pubmed_extractor = PubMedEvidenceExtractor()
    facts_by_asset: dict[str, list[NormalizedFact]] = {}
    entailment_results: list[EntailmentResult] = []
    unsupported_by_asset: dict[str, list[ExtractedClaim]] = {}
    clinical_results: list[ClinicalResult] = []
    for hit in discovery.hits:
        document: SourceDocument | None = documents.get(hit.source_document_id)
        if document is None or not document.snapshot_path:
            continue
        if document.publisher == "ClinicalTrials.gov":
            bundle = extractor.extract(hit, document)
        elif document.publisher == "PubMed":
            bundle = pubmed_extractor.extract(hit, document)
        else:
            continue
        asset_id = hit_to_asset[hit.hit_id]
        for claim in bundle.claims:
            canonical_claim = claim.model_copy(update={"subject_id": asset_id})
            ledger.add_claim(canonical_claim)
            entailment = check_structured_entailment(canonical_claim)
            entailment_results.append(entailment)
            if not entailment.entailed:
                unsupported_by_asset.setdefault(asset_id, []).append(canonical_claim)
        for fact in bundle.facts:
            canonical_fact = fact.model_copy(update={"subject_id": asset_id})
            claim_entailment = {
                result.claim_id: result.entailed for result in entailment_results
            }
            if not all(claim_entailment.get(claim_id, False) for claim_id in fact.supporting_claim_ids):
                continue
            ledger.add_fact(canonical_fact)
            facts_by_asset.setdefault(asset_id, []).append(canonical_fact)
        for result in bundle.clinical_results:
            clinical_results.append(result.model_copy(update={"subject_id": asset_id}))

    gate_engine = GateEngine()
    evaluations = [
        gate_engine.evaluate(
            problem,
            subject_id=asset.asset_id,
            facts=facts_by_asset.get(asset.asset_id, []),
        )
        for asset in candidates
        if facts_by_asset.get(asset.asset_id)
    ]
    evaluated_ids = {evaluation.subject_id for evaluation in evaluations}
    review_queue = [item for evaluation in evaluations for item in evaluation.review_items]
    review_queue.extend(
        AnalystReviewItem(
            review_id=f"review:initial:{asset.asset_id}",
            subject_id=asset.asset_id,
            reason="Candidate requires claim extraction and evidence-backed gate evaluation.",
            priority="high",
        )
        for asset in candidates
        if asset.asset_id not in evaluated_ids
    )
    review_queue.extend(
        AnalystReviewItem(
            review_id=f"review:entailment:{claim.claim_id}",
            subject_id=asset_id,
            reason=f"Citation does not entail material claim {claim.claim_id}.",
            priority="critical",
            claim_ids=[claim.claim_id],
        )
        for asset_id, claims in unsupported_by_asset.items()
        for claim in claims
    )
    eligible = [
        evaluation.subject_id
        for evaluation in evaluations
        if evaluation.disposition == OverallDisposition.ELIGIBLE
    ]
    excluded = [
        evaluation.subject_id
        for evaluation in evaluations
        if evaluation.disposition == OverallDisposition.EXCLUDED
    ]
    unresolved = [
        evaluation.subject_id
        for evaluation in evaluations
        if evaluation.disposition == OverallDisposition.UNRESOLVED
    ]
    unresolved.extend(asset.asset_id for asset in candidates if asset.asset_id not in evaluated_ids)
    ranking = rank_profiles(comparative_profiles or [])
    # A pairwise profile cannot bypass an eligibility decision.
    ranking.ranked = [
        entry
        for entry in ranking.ranked
        if entry.asset_id in eligible
    ]
    return SESearchResult(
        problem_id=problem.problem_id,
        run_manifest=discovery.manifest,
        candidates=candidates,
        eligible_asset_ids=eligible,
        excluded_asset_ids=excluded,
        unresolved_asset_ids=list(dict.fromkeys(unresolved)),
        review_queue=review_queue,
        gate_evaluations=evaluations,
        source_documents=list(ledger.documents.values()),
        claims=list(ledger.claims.values()),
        facts=list(ledger.facts.values()),
        entailment_results=entailment_results,
        ranking=ranking,
        search_attempts=discovery.attempts,
        clinical_results=clinical_results,
        cohort_assignments=[assign_cohort(result) for result in clinical_results],
        clinical_meaningfulness=[
            assess_meaningfulness(result, problem.strategic_gap.clinical_effect_bar)
            for result in clinical_results
        ],
    )
