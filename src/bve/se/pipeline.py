"""End-to-end landscape construction over discovery and provisional identity resolution."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

from pydantic import BaseModel, Field

from bve.se.discovery.asset_qualification import (
    AssetEvidence,
    qualification_reason,
    document_frequencies,
    has_pharmacologic_context,
    is_abbreviation_gloss,
    qualifies_as_asset,
)
from bve.se.discovery import class_terms
from bve.se.discovery.adapters import UnavailableSourceAdapter
from bve.se.discovery.coverage import coverage_families, residual_limitations
from bve.se.discovery.custody import CorpusSeal
from bve.se.discovery.mention_support import (
    MentionDisposition,
    classify_mention_support,
)
from bve.se.discovery.custody_boundary import seal_acquisition
from bve.se.discovery.orchestrator import (
    DiscoveryOrchestrator,
    DiscoveryResult,
    SourceAdapter,
)
from bve.se.evidence.clinicaltrials import ClinicalTrialsEvidenceExtractor
from bve.se.evidence.construct_targets import (
    construct_target_evidence,
    supersede_construct_targets,
)
from bve.se.evidence.entailment import EntailmentResult, check_structured_entailment
from bve.se.evidence.human_poc import efficacy_statements, human_poc_evidence
from bve.se.evidence.source_capability import may_establish_human_poc
from bve.se.evidence import snapshot_cache
from bve.se.evidence.ledger import EvidenceLedger
from bve.se.evidence.pubmed import PubMedEvidenceExtractor
from bve.se.evidence.stage_attribution import StageRoleIndex
from bve.se.evidence.generic import PublicDocumentEvidenceExtractor
from bve.se.gates.engine import GateEngine, GateEvaluation
from bve.se.clinical.cohorts import assign_cohort
from bve.se.clinical.meaningfulness import assess_meaningfulness
from bve.se.resolution.registry import AssetRegistry
from bve.se.resolution.target_attribution import attribution_for
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
    IdentityEdge,
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
    #: The name-to-name relationships the run observed, with the evidence for each.
    identity_edges: list[IdentityEdge] = Field(default_factory=list)
    eligible_asset_ids: list[str] = Field(default_factory=list)
    excluded_asset_ids: list[str] = Field(default_factory=list)
    unresolved_asset_ids: list[str] = Field(default_factory=list)
    #: Candidates held out of the default scoring path for want of corroboration. They are
    #: still present in ``candidates`` with full provenance and still carry a review item;
    #: this list is the handle for promoting them, not a record of what was thrown away.
    low_support_asset_ids: list[str] = Field(default_factory=list)
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


def _has_entity_link(asset: CanonicalAsset) -> bool:
    """Whether anything ties this name to a particular entity rather than to a class.

    Trials, owners and attributed targets only. ``discovery_target_context`` and modality
    are deliberately excluded: they are co-occurrence, and on live data `bsAbs`,
    `frontline`, `cornerstone` and `ASCO 2023` all carry them while carrying no entity.
    """

    return bool(asset.trial_ids or asset.company_ids or asset.target_ids)


def _low_support_review_reason(
    asset: CanonicalAsset, support_by_name: Mapping[str, Sequence[object]]
) -> str:
    """Why this name is held for review, in the terms that actually held it.

    A class term is not short of evidence -- ``CD19 CAR-T cells`` carries 24 trials -- so the
    support-count sentence would be a true number attached to a false explanation, and a
    reviewer reading it would go looking for more documents that cannot help. v5 §5.7 asks
    for the demotion to be as auditable as an admission, which means naming the actual rule.
    """

    if class_terms.is_class_term(asset.canonical_name or ""):
        return (
            f"Nominated name '{asset.canonical_name}' denotes a class of therapies rather "
            "than one asset: modality, target designations and filler exhaust it, leaving "
            "nothing that individuates a molecule. Its trials, owners and target edges are "
            "retained for grouping; it does not stand in the population it groups. Not "
            "deleted -- promoted the moment an individuating name appears."
        )
    supporting = max(
        (len(support_by_name.get(key, ())) for key in asset.identity_keys), default=0
    )
    return (
        f"Nominated name '{asset.canonical_name}' has {supporting} supporting document(s), "
        "below the threshold for the default path. Retained as LOW_SUPPORT_UNKNOWN; "
        "not deleted."
    )


_STAGE_BY_ORDER = {
    0: "DISCOVERY",
    1: "PRECLINICAL",
    2: "PHASE_1",
    3: "PHASE_2",
    4: "PHASE_3",
    5: "REGISTRATION",
    6: "APPROVED",
}


def run_acquisition(
    problem: BuyerProblemV2,
    adapters: Sequence[SourceAdapter],
    *,
    run_id: str,
    code_version: str,
    normalization_version: str,
    declared_mandatory_sources: Sequence[str] | None = None,
    telemetry: StageTelemetry,
    custody_root: Path | None = None,
    custody_pins: Mapping[str, object] | None = None,
) -> tuple[DiscoveryResult, CorpusSeal | None]:
    """Discover, then seal. Nothing here interprets what was acquired.

    Separated from the stages that follow so an expensive scientific run can be split at
    the custody boundary: acquire once against live sources, then run everything
    downstream from the sealed bytes as many times as it takes. A downstream crash must
    never be a reason to touch a live source again.
    """

    with telemetry.stage("DISCOVERY") as stage:
        # A declared area is reached by whichever family the coverage table says reaches
        # it, and an area reached only by a narrower family states what it still misses.
        # Derived here rather than passed in, so every caller gets the same accounting.
        reaching = [
            adapter.source_name
            for adapter in adapters
            if not isinstance(adapter, UnavailableSourceAdapter)
        ]
        discovery = DiscoveryOrchestrator(
            adapters,
            declared_mandatory_sources=declared_mandatory_sources,
            coverage_families=coverage_families(),
            declared_coverage_limitations=residual_limitations(reaching),
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

    seal: CorpusSeal | None = None
    if custody_root is not None:
        # The custody boundary, not a checkpoint: seal_acquisition raises on any failure,
        # so IDENTITY is structurally unreachable from an unsealed or unvalidated corpus.
        with telemetry.stage("ACQUISITION") as stage:
            seal = seal_acquisition(
                discovery.custody,
                discovery.manifest,
                custody_root,
                mandatory_sources=declared_mandatory_sources or (),
                pins=custody_pins,
            )
            stage.count(
                records=seal.record_count,
                snapshots=seal.snapshot_count,
                attempts=seal.attempt_count,
                semantic_queries=seal.semantic_query_count,
                orphans=seal.orphan_record_count,
            )
    return discovery, seal


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
    custody_root: Path | None = None,
    custody_pins: Mapping[str, object] | None = None,
) -> SESearchResult:
    # A run with no telemetry records nothing and prints nothing, so the default
    # behaviour of every existing caller is unchanged.
    telemetry = telemetry or StageTelemetry()
    discovery, _ = run_acquisition(
        problem,
        adapters,
        run_id=run_id,
        code_version=code_version,
        normalization_version=normalization_version,
        declared_mandatory_sources=declared_mandatory_sources,
        telemetry=telemetry,
        custody_root=custody_root,
        custody_pins=custody_pins,
    )

    with telemetry.stage("IDENTITY") as stage:
        # Target attribution is per-asset and evidence-backed. It is deliberately built
        # from the declared targets only, never from the queries that were run or the
        # trials that came back: a candidate is attributed a target because an authority
        # documents it, not because it turned up in a search for that target.
        # The same ontology answers both questions, but they are passed separately
        # because they are different questions: what an asset's targets are, and whether
        # two names denote one molecule. Identity classification is fail-closed without
        # it -- nothing merges on a source's say-so alone.
        attribution = attribution_for(
            target.canonical_id
            for target in problem.strategic_gap.target_expression.targets
        )
        registry = AssetRegistry(attribution, identity_authority=attribution)
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
    extractor = ClinicalTrialsEvidenceExtractor(
        stage_index=StageRoleIndex.from_protocols(
            snapshot_cache.load_json(document.snapshot_path)
            for document in documents.values()
            if document.publisher == "ClinicalTrials.gov" and document.snapshot_path
        )
    )
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
    results_by_asset: dict[str, list[ClinicalResult]] = {}
    #: The documents each asset was actually seen in. Human proof of concept is read from
    #: these and no others: an efficacy sentence is evidence for an asset only in a
    #: document that mentions it, and scanning the whole corpus per asset would attribute
    #: every reported result to every candidate.
    documents_by_asset: dict[str, dict[str, SourceDocument]] = {}
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
            documents_by_asset.setdefault(asset_id, {})[document.document_id] = document
            for result in bundle.clinical_results:
                canonical_result = result.model_copy(update={"subject_id": asset_id})
                clinical_results.append(canonical_result)
                results_by_asset.setdefault(asset_id, []).append(canonical_result)
            extraction_stage.count(
                documents=1,
                claims=len(bundle.claims),
                facts=len(bundle.facts),
            )
        extraction_stage.count(errors=len(processing_errors))

    # Construct target sets, derived from each asset's own mechanism assertions rather
    # than from the documents it was found in. This runs over every candidate, not only
    # those with extracted facts, because an asset's targets are a property of the asset:
    # a corpus that never spells out what a molecule binds does not make the authority's
    # answer unavailable. Assets the authority cannot speak to yield nothing at all, which
    # the target gate reads as UNKNOWN.
    with telemetry.stage("CONSTRUCT_TARGETS") as stage:
        described = 0
        for asset in registry.assets.values():
            evidence = construct_target_evidence(asset, as_of_date=problem.buyer.as_of_date)
            if evidence is None:
                continue
            for document in evidence.documents:
                ledger.register_document(document)
            for claim in evidence.claims:
                ledger.add_claim(claim)
            ledger.add_fact(evidence.fact)
            # The authority supersedes an intervention record's own description of itself
            # rather than arguing with it. Both are admissible construct evidence, but a
            # curated drug->target edge is the better witness, and leaving a disagreement
            # standing would turn two answers into no answer: the gate reads competing
            # target facts as UNKNOWN, so the asset would lose the decision it had.
            # The superseded claims stay in the ledger, so the disagreement is still on
            # the record rather than erased by the one that won.
            facts_by_asset[asset.asset_id] = supersede_construct_targets(
                facts_by_asset.get(asset.asset_id, []), evidence.fact
            )
            described += 1
        stage.count(candidates=len(registry.assets), described=described)

    # Human proof of concept, from the two places a reported result can be found: a
    # structured clinical result the source published, and a sentence in a document the
    # asset was seen in. Assets with neither produce no fact, which the evidence floor
    # reads as UNKNOWN -- the deliberate choice over asserting a failure nobody reported.
    #: Distinct documents behind each name, straight off the mentions the registry already
    #: holds. The corpus is not reread. Computed before qualification because the
    #: saturation ceiling needs it, and used again by the disposition below.
    support_by_name: dict[str, set[str]] = defaultdict(set)
    for mention in registry.mentions.values():
        support_by_name[mention.normalized_asset_name].add(mention.source_document_id)

    def _support(asset) -> int:
        return max(
            (len(support_by_name.get(key, ())) for key in asset.identity_keys),
            default=0,
        )

    corpus_documents = len(ledger.documents)
    #: How common each word is in this corpus. Built in one pass because the alternative
    #: -- asking per candidate -- is 2,702 scans of 15,032 documents.
    with telemetry.stage("LEXICON") as stage:
        def _corpus_texts():
            for document in ledger.documents.values():
                if not document.snapshot_path:
                    continue
                try:
                    yield snapshot_cache.load_text(Path(document.snapshot_path))
                except OSError as exc:
                    processing_errors.append(
                        f"lexicon:{document.document_id}: {type(exc).__name__}: {exc}"
                    )

        word_frequency = document_frequencies(_corpus_texts())
        stage.count(documents=corpus_documents, vocabulary=len(word_frequency))

    #: A registry that describes a string as a construct and names its molecular targets
    #: has done the thing an ontology entry does: vouched, from outside the corpus, that
    #: this string names a therapeutic agent. Ordinary words never acquire one.
    described_constructs = {
        fact.subject_id
        for facts in facts_by_asset.values()
        for fact in facts
        if fact.fact_type == "construct_target_set"
    }

    def _document_frequency(asset) -> int:
        return word_frequency.get(asset.canonical_name.casefold(), 0)

    #: Whether a document ever used this asset's name the way documents use the name of a
    #: drug. Read in the same pass as the efficacy prose so the corpus is traversed once.
    pharmacologic_context: dict[str, bool] = {}
    #: Distinct documents witnessing that use, the gloss construction, and any mention at
    #: all. The last two are counted together because "every occurrence is a gloss" is the
    #: only form the gloss veto may take -- one ordinary use makes the name a name.
    pharmacologic_documents: dict[str, int] = {}
    gloss_documents: dict[str, int] = {}
    mentioning_documents: dict[str, int] = {}
    with telemetry.stage("HUMAN_POC") as stage:
        supported = 0
        qualified_assets = 0
        for asset_id, asset in registry.assets.items():
            names = [asset.canonical_name, *asset.aliases]
            statements = []
            #: Routes that need no corpus evidence: an ontology entry, a development code,
            #: a structured DRUG declaration. Checked first so the scan is skipped for the
            #: names that are already vouched for.
            evidence_so_far = AssetEvidence(
                name=asset.canonical_name,
                support=_support(asset),
                structurally_typed_drug=asset.structurally_typed_drug,
                comparator_observations=asset.comparator_observations,
                specific_comparator_observations=asset.specific_comparator_observations,
                therapeutic_observations=asset.therapeutic_observations,
                unknown_observations=asset.unknown_observations,
                entity_specific_link=_has_entity_link(asset),
                corpus_documents=corpus_documents,
                document_frequency=_document_frequency(asset),
                identity_authority=asset_id in described_constructs,
            )
            qualified = qualifies_as_asset(evidence_so_far)
            for document in documents_by_asset.get(asset_id, {}).values():
                if not document.snapshot_path:
                    continue
                # A registry record speaks through its structured outcome measures, which
                # carry their own "was this reported" flag. Reading its prose as well finds
                # only its eligibility criteria, written in the vocabulary of results.
                if document.document_type == "trial_registry_record":
                    continue
                try:
                    text = snapshot_cache.load_text(Path(document.snapshot_path))
                except OSError as exc:
                    processing_errors.append(
                        f"human_poc:{document.document_id}: {type(exc).__name__}: {exc}"
                    )
                    continue
                # Counted, not latched. One document used to be enough, and one document is
                # an accident: the corpus contains exactly one "treated with bsAbs", which
                # would qualify a class abbreviation on a single author's shorthand. The
                # count is of independent witnesses to one relation and is never traded
                # against support, frequency or shape.
                if any(has_pharmacologic_context(text, name) for name in names):
                    pharmacologic_documents[asset_id] = (
                        pharmacologic_documents.get(asset_id, 0) + 1
                    )
                    pharmacologic_context[asset_id] = True
                # A name that only ever appears expanding the phrase in front of it is an
                # abbreviation of that phrase. Tracked per document because a single
                # non-gloss use is enough to make it a name: "(POD24)" is a gloss in all 23
                # of its occurrences, while a development code beside its own molecule is
                # never one.
                if any(is_abbreviation_gloss(text, name) for name in names):
                    gloss_documents[asset_id] = gloss_documents.get(asset_id, 0) + 1
                mentioning_documents[asset_id] = mentioning_documents.get(asset_id, 0) + 1
                # v4 §3c. The gloss veto is applied here, at the decisional fact, and
                # nowhere else. v2 and v3 preregistered it for human proof of concept --
                # "bispecific antibodies (bsAbs)" reports no outcome for bsAbs -- and v3
                # then routed it through ``AssetEvidence``, where it silently became a
                # qualification rule and cost SYNCAR-001. Stated as a separate conjunct so
                # the two questions cannot be confused again.
                gloss_only = gloss_documents.get(asset_id, 0) > 0 and gloss_documents.get(
                    asset_id, 0
                ) == mentioning_documents.get(asset_id, 0)
                qualified = not gloss_only and qualifies_as_asset(
                    evidence_so_far.model_copy(
                        update={
                            "pharmacologic_context": pharmacologic_context.get(
                                asset_id, False
                            ),
                            "pharmacologic_documents": pharmacologic_documents.get(
                                asset_id, 0
                            ),
                        }
                    )
                )
                # The evidence policy gates the *fact*, and nothing else.
                #
                # It used to sit above, as a ``continue`` next to the registry-record skip,
                # and the two looked alike. They are not. The registry record is skipped
                # because of what its prose is; a source-capability exclusion is a statement
                # about one decisional fact. Placed at the top of the loop it also withheld
                # the document from ``has_pharmacologic_context`` -- so a policy about human
                # proof-of-concept was quietly deciding which strings count as assets at all.
                #
                # Measured, not hypothesised: lifting the conference exclusion added exactly
                # four candidates -- "bivalent", "tetravalent", "dopaminergic" and a run of
                # table junk -- none of which are drugs and none of which have anything to do
                # with human efficacy. Their qualification changed because a *different*
                # gate's guard had been suppressing the identity scan.
                #
                # The scan below therefore reads every document this loop can open. What the
                # policy decides is whether an efficacy sentence may be drawn from it.
                if may_establish_human_poc(document.document_type):
                    statements.extend(
                        efficacy_statements(
                            text, asset_names=names, document_id=document.document_id
                        )
                    )
            # An efficacy sentence is evidence about a result, never about whether the
            # string it mentions names a drug. Without positive asset evidence the
            # attribution would be correct and the identity still wrong, so the fact is
            # not produced -- the asset keeps every mention and is promoted the moment
            # qualifying evidence arrives.
            if not qualified:
                continue
            qualified_assets += 1
            evidence = human_poc_evidence(
                asset_id,
                results=results_by_asset.get(asset_id, []),
                statements=statements,
                as_of_date=problem.buyer.as_of_date,
                claim_documents={
                    claim_id: claim.source_document_id
                    for claim_id, claim in ledger.claims.items()
                },
            )
            if evidence is None:
                continue
            for claim in evidence.claims:
                ledger.add_claim(claim)
            ledger.add_fact(evidence.fact)
            facts_by_asset.setdefault(asset_id, []).append(evidence.fact)
            supported += 1
        stage.count(
            candidates=len(registry.assets),
            qualified=qualified_assets,
            supported=supported,
        )

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

    def _asset_evidence(asset: CanonicalAsset) -> AssetEvidence:
        """The one evidence record both the routing decision and the reason are read from.

        Built here rather than twice, so a disposition and a ``qualification_reason`` can
        never be computed from different inputs and silently disagree.
        """

        return AssetEvidence(
            name=asset.canonical_name,
            support=_support(asset),
            corpus_documents=corpus_documents,
            document_frequency=_document_frequency(asset),
            identity_authority=asset.asset_id in described_constructs,
            structurally_typed_drug=asset.structurally_typed_drug,
            comparator_observations=asset.comparator_observations,
            specific_comparator_observations=asset.specific_comparator_observations,
            therapeutic_observations=asset.therapeutic_observations,
            unknown_observations=asset.unknown_observations,
            entity_specific_link=_has_entity_link(asset),
            pharmacologic_context=pharmacologic_context.get(asset.asset_id, False),
            pharmacologic_documents=pharmacologic_documents.get(asset.asset_id, 0),
            # v4 §3c: the gloss signal is deliberately not carried into the qualification
            # evidence. It belongs to mention support, which reads it below.
        )

    dispositions = {
        asset.asset_id: classify_mention_support(
            asset.canonical_name,
            support=_support(asset),
            corpus_documents=corpus_documents,
            document_frequency=_document_frequency(asset),
            identity_authority=asset.asset_id in described_constructs,
            structurally_typed_drug=asset.structurally_typed_drug,
            comparator_observations=asset.comparator_observations,
            specific_comparator_observations=asset.specific_comparator_observations,
            therapeutic_observations=asset.therapeutic_observations,
            unknown_observations=asset.unknown_observations,
            entity_specific_link=_has_entity_link(asset),
            pharmacologic_context=pharmacologic_context.get(asset.asset_id, False),
            pharmacologic_documents=pharmacologic_documents.get(asset.asset_id, 0),
        )
        for asset in candidates
    }
    # Every candidate carries the reason it qualified, or ``None``. Recorded on the asset
    # rather than recomputed by each reader, so "why is this here?" is a field lookup. v2
    # made the decision single but left it anonymous, and tracing `paper` and `choice` back
    # to their routes took a walk through four modules.
    reasons = {
        asset.asset_id: qualification_reason(_asset_evidence(asset))
        for asset in candidates
    }
    candidates = [
        asset.model_copy(
            update={
                "qualification_reason": (
                    reasons[asset.asset_id].value if reasons[asset.asset_id] else None
                )
            }
        )
        for asset in candidates
    ]
    for asset in candidates:
        registry.assets[asset.asset_id] = asset

    low_support_asset_ids = [
        asset.asset_id
        for asset in candidates
        # Fail closed. A disposition is a routing decision and the reason is the authority;
        # if they ever disagree, the asset goes to review rather than onto the default path
        # with no auditable justification.
        if dispositions[asset.asset_id] is MentionDisposition.LOW_SUPPORT_UNKNOWN
        or reasons[asset.asset_id] is None
    ]
    #: Retained in full on ``candidates`` with their provenance; held out of the default
    #: scoring path only. Nothing is discarded here -- see ``mention_support``.
    default_path = [
        asset
        for asset in candidates
        if dispositions[asset.asset_id] is not MentionDisposition.LOW_SUPPORT_UNKNOWN
    ]
    gate_engine = GateEngine()
    with telemetry.stage("GATING") as stage:
        evaluations = [
            gate_engine.evaluate(
                problem,
                subject_id=asset.asset_id,
                facts=_dedupe_gate_facts(facts_by_asset.get(asset.asset_id, [])),
            )
            for asset in default_path
            if facts_by_asset.get(asset.asset_id)
        ]
        stage.count(
            candidates=len(candidates),
            default_path=len(default_path),
            low_support=len(low_support_asset_ids),
            evaluated=len(evaluations),
        )
    evaluated_ids = {evaluation.subject_id for evaluation in evaluations}
    review_queue = [item for evaluation in evaluations for item in evaluation.review_items]
    review_queue.extend(
        AnalystReviewItem(
            review_id=f"review:initial:{asset.asset_id}",
            subject_id=asset.asset_id,
            reason="Candidate requires claim extraction and evidence-backed gate evaluation.",
            priority="high",
        )
        for asset in default_path
        if asset.asset_id not in evaluated_ids
    )
    #: Low-support names stay visible and recoverable: one review item each, carrying the
    #: disposition and the support count that produced it, at a priority that keeps them
    #: out of the analyst's way until something promotes them.
    review_queue.extend(
        AnalystReviewItem(
            review_id=f"review:low_support:{asset.asset_id}",
            subject_id=asset.asset_id,
            reason=_low_support_review_reason(asset, support_by_name),
            priority="low",
        )
        for asset in candidates
        if dispositions[asset.asset_id] is MentionDisposition.LOW_SUPPORT_UNKNOWN
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
    unresolved.extend(
        asset.asset_id for asset in default_path if asset.asset_id not in evaluated_ids
    )
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
        identity_edges=list(registry.identity_edges),
        eligible_asset_ids=eligible,
        excluded_asset_ids=excluded,
        unresolved_asset_ids=list(dict.fromkeys(unresolved)),
        low_support_asset_ids=low_support_asset_ids,
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
