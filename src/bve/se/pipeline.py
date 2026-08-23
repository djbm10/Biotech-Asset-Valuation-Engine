"""End-to-end landscape construction over discovery and provisional identity resolution."""

from __future__ import annotations

import json
from typing import Sequence

from pydantic import BaseModel, Field

from bve.se.discovery.orchestrator import DiscoveryOrchestrator, SourceAdapter
from bve.se.evidence.clinicaltrials import ClinicalTrialsEvidenceExtractor
from bve.se.evidence.entailment import EntailmentResult, check_structured_entailment
from bve.se.evidence.ledger import EvidenceLedger
from bve.se.evidence.pubmed import PubMedEvidenceExtractor
from bve.se.evidence.generic import PublicDocumentEvidenceExtractor
from bve.se.gates.engine import GateEngine, GateEvaluation
from bve.se.clinical.cohorts import assign_cohort
from bve.se.clinical.meaningfulness import assess_meaningfulness
from bve.se.resolution.registry import AssetRegistry
from bve.se.telemetry import StageTelemetry, summarize_attempts
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
    RunStatus,
    IdentityMention,
    CompanyRecord,
    IdentityMerge,
)

DEVELOPMENT_SCREEN_LABEL = (
    "Production-validated public-data S&E screen; pre-diligence—not verified truth."
)
INCOMPLETE_SCREEN_LABEL = (
    "Incomplete public-data S&E run; diagnostics only—not a production screen."
)


class SESearchResult(BaseModel):
    problem_id: str
    run_manifest: RunManifest
    candidates: list[CanonicalAsset] = Field(default_factory=list)
    identity_mentions: list[IdentityMention] = Field(default_factory=list)
    companies: list[CompanyRecord] = Field(default_factory=list)
    identity_merges: list[IdentityMerge] = Field(default_factory=list)
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
    processing_errors: list[str] = Field(default_factory=list)
    label: str = DEVELOPMENT_SCREEN_LABEL


def _dedupe_gate_facts(facts: Sequence[NormalizedFact]) -> list[NormalizedFact]:
    """Collapse identical cross-source facts without concealing genuine disagreement."""

    unique: dict[tuple[str, str, bool], NormalizedFact] = {}
    for fact in facts:
        key = (
            fact.fact_type,
            json.dumps(fact.value, sort_keys=True, default=str),
            bool(getattr(fact, "is_stale", False)),
        )
        existing = unique.get(key)
        if existing is None:
            unique[key] = fact
            continue
        unique[key] = existing.model_copy(
            update={
                "supporting_claim_ids": list(
                    dict.fromkeys(
                        [*existing.supporting_claim_ids, *fact.supporting_claim_ids]
                    )
                ),
                "contradicting_claim_ids": list(
                    dict.fromkeys(
                        [
                            *existing.contradicting_claim_ids,
                            *fact.contradicting_claim_ids,
                        ]
                    )
                ),
                "confidence": max(existing.confidence, fact.confidence),
            }
        )
    return list(unique.values())


_STAGE_BY_ORDER = {
    0: "DISCOVERY",
    1: "PRECLINICAL",
    2: "PHASE_1",
    3: "PHASE_2",
    4: "PHASE_3",
    5: "REGISTRATION",
    6: "APPROVED",
}


def run_landscape_search(
    problem: BuyerProblemV2,
    adapters: Sequence[SourceAdapter],
    *,
    run_id: str,
    code_version: str,
    normalization_version: str,
    declared_mandatory_sources: Sequence[str] | None = None,
    comparative_profiles: Sequence[PairwiseProfile] | None = None,
    telemetry: StageTelemetry | None = None,
) -> SESearchResult:
    # A run with no telemetry records nothing and prints nothing, so the default
    # behaviour of every existing caller is unchanged.
    telemetry = telemetry or StageTelemetry()
    with telemetry.stage("DISCOVERY") as stage:
        discovery = DiscoveryOrchestrator(
            adapters,
            declared_mandatory_sources=declared_mandatory_sources,
        ).run(
            problem,
            run_id=run_id,
            code_version=code_version,
            normalization_version=normalization_version,
        )
        per_source = summarize_attempts(discovery.attempts)
        stage.count(
            queries=sum(counts["queries"] for counts in per_source.values()),
            records=sum(counts["records"] for counts in per_source.values()),
            hits=len(discovery.hits),
        )
    if telemetry.emit is not None:
        # Which source carried the run is the first question after "how long"; a single
        # aggregate hides a source that returned nothing.
        for source in sorted(per_source):
            counts = per_source[source]
            telemetry.emit(
                f"  {source}: {counts['queries']} queries | {counts['records']} records "
                f"| {counts['candidates']} candidates | {counts['failed']} failed"
            )

    with telemetry.stage("IDENTITY") as stage:
        registry = AssetRegistry()
        hit_to_asset: dict[str, str] = {}
        for hit in discovery.hits:
            asset = registry.ingest_hit(hit)
            hit_to_asset[hit.hit_id] = asset.asset_id
        stage.count(hits=len(discovery.hits), assets=len(registry.assets))
    candidates = list(registry.assets.values())
    documents = {document.document_id: document for document in discovery.source_documents}
    ledger = EvidenceLedger()
    for source_document in documents.values():
        ledger.register_document(source_document)
    extractor = ClinicalTrialsEvidenceExtractor()
    pubmed_extractor = PubMedEvidenceExtractor()
    public_document_extractor = PublicDocumentEvidenceExtractor()
    facts_by_asset: dict[str, list[NormalizedFact]] = {}
    entailment_results: list[EntailmentResult] = []
    #: claim_id -> entailed, maintained as results are appended. This used to be rebuilt
    #: from the whole of ``entailment_results`` once per fact, which is quadratic in
    #: corpus size: harmless at a few hundred trials, ~3e9 dict insertions at the ~14k
    #: trials an exhaustive PDCD1 sweep returns.
    claim_entailment: dict[str, bool] = {}
    unsupported_by_asset: dict[str, list[ExtractedClaim]] = {}
    clinical_results: list[ClinicalResult] = []
    processing_errors: list[str] = []
    with telemetry.stage("EXTRACTION") as extraction_stage:
        for hit in discovery.hits:
            document: SourceDocument | None = documents.get(hit.source_document_id)
            if document is None or not document.snapshot_path:
                continue
            selected_extractor: (
                ClinicalTrialsEvidenceExtractor
                | PubMedEvidenceExtractor
                | PublicDocumentEvidenceExtractor
            )
            if document.publisher == "ClinicalTrials.gov":
                selected_extractor = extractor
            elif document.publisher == "PubMed":
                selected_extractor = pubmed_extractor
            else:
                selected_extractor = public_document_extractor
            try:
                bundle = selected_extractor.extract(hit, document)
            except Exception as exc:  # source parsing is an operational boundary
                processing_errors.append(
                    f"{hit.source}:{document.document_id}:{hit.hit_id}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            asset_id = hit_to_asset[hit.hit_id]
            for claim in bundle.claims:
                canonical_claim = claim.model_copy(update={"subject_id": asset_id})
                ledger.add_claim(canonical_claim)
                entailment = check_structured_entailment(canonical_claim)
                entailment_results.append(entailment)
                claim_entailment[entailment.claim_id] = entailment.entailed
                if not entailment.entailed:
                    unsupported_by_asset.setdefault(asset_id, []).append(canonical_claim)
            for fact in bundle.facts:
                canonical_fact = fact.model_copy(update={"subject_id": asset_id})
                if not all(claim_entailment.get(claim_id, False) for claim_id in fact.supporting_claim_ids):
                    continue
                ledger.add_fact(canonical_fact)
                facts_by_asset.setdefault(asset_id, []).append(canonical_fact)
            for result in bundle.clinical_results:
                clinical_results.append(result.model_copy(update={"subject_id": asset_id}))
            extraction_stage.count(
                documents=1,
                claims=len(bundle.claims),
                facts=len(bundle.facts),
            )
        extraction_stage.count(errors=len(processing_errors))

    for asset_id, facts in facts_by_asset.items():
        asset = registry.assets[asset_id]
        supporting_claim_ids = list(
            dict.fromkeys(
                claim_id
                for fact in facts
                for claim_id in fact.supporting_claim_ids
            )
        )
        stage_orders = [
            int(fact.value)
            for fact in facts
            if fact.fact_type == "development_stage_order"
            and isinstance(fact.value, int)
        ]
        statuses = [
            str(fact.value)
            for fact in facts
            if fact.fact_type == "development_status"
        ]
        registry.assets[asset_id] = asset.model_copy(
            update={
                "supporting_claim_ids": supporting_claim_ids,
                "development_stage": (
                    _STAGE_BY_ORDER.get(max(stage_orders)) if stage_orders else None
                ),
                "development_status": statuses[-1] if statuses else None,
            }
        )
    candidates = list(registry.assets.values())
    gate_engine = GateEngine()
    with telemetry.stage("GATING") as stage:
        evaluations = [
            gate_engine.evaluate(
                problem,
                subject_id=asset.asset_id,
                facts=_dedupe_gate_facts(facts_by_asset.get(asset.asset_id, [])),
            )
            for asset in candidates
            if facts_by_asset.get(asset.asset_id)
        ]
        stage.count(candidates=len(candidates), evaluated=len(evaluations))
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
    with telemetry.stage("SCORING") as stage:
        ranking = rank_profiles(comparative_profiles or [])
        stage.count(
            profiles=len(comparative_profiles or []),
            eligible=len(eligible),
            excluded=len(excluded),
            unresolved=len(unresolved),
        )
    # A pairwise profile cannot bypass an eligibility decision.
    ranking.ranked = [
        entry
        for entry in ranking.ranked
        if entry.asset_id in eligible
    ]
    run_manifest = discovery.manifest
    if processing_errors:
        run_manifest = run_manifest.model_copy(
            update={
                "status": RunStatus.INCOMPLETE,
                "incomplete_reasons": [
                    *run_manifest.incomplete_reasons,
                    f"evidence extraction failures: {len(processing_errors)}",
                ],
            }
        )
    return SESearchResult(
        problem_id=problem.problem_id,
        run_manifest=run_manifest,
        candidates=candidates,
        identity_mentions=list(registry.mentions.values()),
        companies=list(registry.companies.values()),
        identity_merges=list(registry.merges.values()),
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
        processing_errors=processing_errors,
        label=(
            DEVELOPMENT_SCREEN_LABEL
            if run_manifest.status.value == "CONVERGED"
            else INCOMPLETE_SCREEN_LABEL
        ),
    )
