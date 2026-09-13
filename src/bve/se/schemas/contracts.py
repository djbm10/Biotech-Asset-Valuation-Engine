"""Canonical, evidence-first contracts for buyer-specific Search & Evaluation.

These models intentionally contain no valuation, rNPV, market-pricing, or investment fields.
They define the boundary between discovery, evidence, eligibility, analyst review, and ranking.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Forbid silent schema drift at the S&E boundary."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TargetOperator(str, Enum):
    ANY = "ANY"
    ALL = "ALL"
    EXACT_COMBINATION = "EXACT_COMBINATION"


class LandscapeMode(str, Enum):
    COMBINED = "COMBINED"
    SEPARATE = "SEPARATE"


class LandscapeGroup(str, Enum):
    TARGET = "TARGET"
    INDICATION = "INDICATION"
    COHORT = "COHORT"
    STAGE = "STAGE"


class MissingEvidencePolicy(str, Enum):
    REVIEW = "REVIEW"
    ABSTAIN = "ABSTAIN"


class RequirementDomain(str, Enum):
    ELIGIBILITY = "ELIGIBILITY"
    EVIDENCE_SUFFICIENCY = "EVIDENCE_SUFFICIENCY"


class RequirementOperator(str, Enum):
    EQ = "EQ"
    NE = "NE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    GTE = "GTE"
    LTE = "LTE"
    CONTAINS_ALL = "CONTAINS_ALL"
    CONTAINS_ANY = "CONTAINS_ANY"
    EXISTS = "EXISTS"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class OverallDisposition(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    EXCLUDED = "EXCLUDED"
    UNRESOLVED = "UNRESOLVED"


class CohortStatus(str, Enum):
    COMPARABLE = "COMPARABLE"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    COHORT_UNRESOLVED = "COHORT_UNRESOLVED"


class MeaningfulnessStatus(str, Enum):
    MEETS = "MEETS"
    DOES_NOT_MEET = "DOES_NOT_MEET"
    UNKNOWN = "UNKNOWN"


class EvidenceConfidenceTier(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class AttractivenessTier(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    UNRANKED = "UNRANKED"


class PairwiseOutcome(str, Enum):
    LEFT_PREFERRED = "LEFT_PREFERRED"
    RIGHT_PREFERRED = "RIGHT_PREFERRED"
    TIE = "TIE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    ABSTAIN = "ABSTAIN"


class SourceTier(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    COMPANY_AUTHORED = "COMPANY_AUTHORED"
    REGULATORY = "REGULATORY"
    REGISTRY = "REGISTRY"


class VerificationStatus(str, Enum):
    EXTRACTED = "EXTRACTED"
    MACHINE_VERIFIED = "MACHINE_VERIFIED"
    ANALYST_CONFIRMED = "ANALYST_CONFIRMED"
    REJECTED = "REJECTED"


class SearchOutcome(str, Enum):
    """How a source's acquisition ended.

    ``NOT_CONFIGURED`` is structurally distinct from ``FAILED`` because the two carry
    opposite consequences: a declared source with no connector is a known blind spot the
    operator may waive, while a source that broke mid-acquisition leaves the corpus short
    an unknown number of records and can never be scored. Run B6 conflated them -- seven
    unbuilt connectors reported ``FAILED`` and made an otherwise clean CT.gov run
    unscoreable -- which is why this is an outcome and not an inference from counts.
    """

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NO_EVIDENCE_FOUND = "NO_EVIDENCE_FOUND"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class TargetAssertionStatus(str, Enum):
    """What authoritative evidence concludes about one asset and one target.

    Deliberately not a boolean. An asset no authority has heard of and an asset
    documented to act on something else are different answers, and a pipeline that
    collapses them will exclude the first for the reasons that apply to the second.
    """

    #: Direct mechanism evidence for the requested target.
    CONFIRMED_TARGET = "CONFIRMED_TARGET"
    #: Direct mechanism evidence, all of it for other targets.
    CONFIRMED_OTHER_TARGET = "CONFIRMED_OTHER_TARGET"
    #: Direct evidence from more than one source, and the sources disagree.
    CONFLICTING = "CONFLICTING"
    #: No direct evidence either way. Silence, not a negative.
    UNRESOLVED = "UNRESOLVED"


class TargetEvidenceRef(StrictModel):
    """A pointer back to the upstream row an assertion rests on."""

    source: str = Field(min_length=1)
    source_release: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    evidence_hash: str = Field(min_length=1)
    canonical_target_id: str | None = None
    relationship_type: str = Field(min_length=1)


class CandidateTargetAssertion(StrictModel):
    """What an asset is documented to act on, on its own evidence.

    Distinct from :attr:`CompiledQuery.target_ids`, which says only what was searched
    for. A candidate returned by a PDCD1 query has PDCD1 in its search context; whether
    it has a PDCD1 *assertion* is a separate question this answers, and the separation is
    the point: a chemotherapy co-administered in a PDCD1 trial is a legitimate discovery
    result and an illegitimate PDCD1 attribution.
    """

    canonical_target_id: str = Field(min_length=1)
    status: TargetAssertionStatus
    #: Every target direct evidence supports, which for a bispecific is more than one.
    documented_targets: list[str] = Field(default_factory=list)
    #: The rows that decided the status.
    evidence: list[TargetEvidenceRef] = Field(default_factory=list)
    #: Family or complex rows mentioning the requested target. Never decisional -- they
    #: are carried so an analyst reviewing an UNRESOLVED candidate can see why it came up.
    supporting_associations: list[TargetEvidenceRef] = Field(default_factory=list)


class SourceEvidenceType(str, Enum):
    """What a source document is being read as saying.

    Company pipelines, filings, press releases and abstracts are written in prose, where
    "in combination with", a trade name, a platform name and a partner's asset all appear
    in the same sentence. A source that emits bare names forces the registry to guess
    which kind of statement it just received; typing the claim at the boundary is what
    stops "given with pembrolizumab" from arriving in the same shape as "also known as
    pembrolizumab".
    """

    #: This document mentions a program worth looking at. Never identity.
    DISCOVERY_EVIDENCE = "DISCOVERY_EVIDENCE"
    #: This document states that two names denote the same entity. The only type that may
    #: even be *considered* for an alias, and still subject to corroboration and veto.
    IDENTITY_EVIDENCE = "IDENTITY_EVIDENCE"
    #: What the program is said to act on.
    TARGET_EVIDENCE = "TARGET_EVIDENCE"
    #: Phase, IND status, first-in-human, and similar.
    DEVELOPMENT_STAGE_EVIDENCE = "DEVELOPMENT_STAGE_EVIDENCE"
    #: Who owns, licenses or sponsors the program.
    COMPANY_OWNERSHIP_EVIDENCE = "COMPANY_OWNERSHIP_EVIDENCE"
    #: Designations, approvals, clinical holds.
    REGULATORY_EVIDENCE = "REGULATORY_EVIDENCE"
    #: An asserted relationship between two programs that is explicitly not sameness.
    RELATIONSHIP_EVIDENCE = "RELATIONSHIP_EVIDENCE"


#: The evidence types that may take part in an identity decision at all. Everything else
#: is discovery or context, however confidently a source words it. Enforced in
#: ``bve.se.resolution.registry``, not merely documented here: a new source family must be
#: unable to create an alias by wording a discovery claim persuasively.
IDENTITY_BEARING_EVIDENCE = frozenset({SourceEvidenceType.IDENTITY_EVIDENCE})


class CandidateHit(StrictModel):
    """One source-specific mention; not yet a canonical asset assertion."""

    hit_id: str
    source: str
    source_document_id: str
    query: str
    asset_name: str | None = None
    company_name: str | None = None
    trial_id: str | None = None
    target_terms: list[str] = Field(default_factory=list)
    modality_terms: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    #: The source's own structural classification of the intervention, e.g. CT.gov
    #: ``DRUG`` / ``BIOLOGICAL`` / ``COMBINATION_PRODUCT``. Carried so that relationship
    #: classification can consult declared product structure instead of guessing from
    #: punctuation in a name.
    intervention_type: str | None = None
    #: What kind of statement ``aliases`` is. Defaults to discovery, so a source family
    #: that does not declare an identity claim cannot produce one: new sources must opt
    #: in to identity, never inherit it. PubMed, for instance, puts the article title
    #: here, which is not a name at all.
    alias_evidence_type: SourceEvidenceType = SourceEvidenceType.DISCOVERY_EVIDENCE
    snippet: str = ""
    provisional_identity_key: str = Field(min_length=1)
    retrieved_at: datetime
    applicable_as_of_date: date


class IdentityMention(StrictModel):
    mention_id: str
    hit_id: str
    raw_asset_name: str | None = None
    raw_company_name: str | None = None
    raw_trial_id: str | None = None
    normalized_asset_name: str | None = None
    normalized_company_name: str | None = None
    source_document_id: str
    observed_at: datetime


class CompanyRecord(StrictModel):
    company_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    predecessor_company_ids: list[str] = Field(default_factory=list)
    successor_company_ids: list[str] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)


class OwnershipRight(StrictModel):
    right_id: str
    asset_id: str
    company_id: str
    geography: str = "GLOBAL"
    indication: str | None = None
    right_type: str
    effective_from: date
    effective_to: date | None = None
    supporting_claim_ids: list[str] = Field(min_length=1)


class CanonicalAsset(StrictModel):
    asset_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    #: This asset's names in the one normalized space identity is decided in -- the same
    #: space ``IdentityMention.normalized_asset_name`` is written in, produced by the same
    #: ``normalize_identity_name``. ``canonical_name`` and ``aliases`` are for display and
    #: keep their punctuation; joining anything to an asset by one of those strings
    #: compares across two name spaces and silently loses every development code. Published
    #: because the registry already indexes on these keys internally, and a caller left to
    #: re-derive them is a caller free to derive them differently.
    identity_keys: list[str] = Field(default_factory=list)
    company_ids: list[str] = Field(default_factory=list)
    trial_ids: list[str] = Field(default_factory=list)
    #: Targets this asset is documented to act on. Populated only from confirmed
    #: mechanism assertions -- never from the target a query was scoped to, and never
    #: from targets merely named by a document the asset appeared in.
    target_ids: list[str] = Field(default_factory=list)
    #: Targets named by the contexts this asset was discovered in. Discovery evidence,
    #: not attribution: kept so a candidate can be traced back to why it surfaced,
    #: and deliberately never merged into ``target_ids``.
    discovery_target_context: list[str] = Field(default_factory=list)
    target_assertions: list[CandidateTargetAssertion] = Field(default_factory=list)
    modality_id: str | None = None
    indication_ids: list[str] = Field(default_factory=list)
    development_stage: str | None = None
    development_status: str | None = None
    last_confirmed_active_date: date | None = None
    mention_ids: list[str] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    provisional: bool = True


class IdentityRelationship(str, Enum):
    """How a name observed alongside an asset relates to that asset's identity.

    Co-occurrence is not identity. A registry reads ``otherNames`` and finds a mixture of
    true synonyms, co-formulated components, regimen partners and class descriptors; only
    the first is safe to merge. Naming the rest is what keeps a combination partner from
    silently becoming an alias.
    """

    #: The same molecular entity under another spelling. Safe to merge.
    IDENTITY_ALIAS = "IDENTITY_ALIAS"
    #: A component of one fixed-dose or co-formulated product. Identity-bearing at the
    #: product level; explicitly NOT molecular synonymy, so the canonical ids stay distinct.
    COFORMULATED_COMPONENT = "COFORMULATED_COMPONENT"
    #: A distinct drug given as part of the same combination. Never identity.
    COMBINATION_PARTNER = "COMBINATION_PARTNER"
    #: Observed in the same trial or regimen, with no stronger relationship established.
    COADMINISTERED_WITH = "COADMINISTERED_WITH"
    #: One name is the antibody or small molecule the other conjugates, e.g. Datopotamab
    #: within Dato-DXd, or Trastuzumab within T-DM1. A real and useful relationship, and
    #: emphatically not sameness: the conjugate and its parent are different molecules with
    #: different targets of effect, so the canonical ids stay distinct.
    #:
    #: Added in M12 because M11 had to label these ``COMBINATION_PARTNER``, which got the
    #: identity decision right and the relationship wrong. Emitted only where an authority
    #: documents the conjugation; it is never inferred from one name containing the other,
    #: which would be the same string-shape reasoning the evidence model exists to reject.
    CONJUGATE_PARENT = "CONJUGATE_PARENT"
    #: Insufficient positive evidence to classify. Held for review, never merged.
    UNCERTAIN_RELATIONSHIP = "UNCERTAIN_RELATIONSHIP"


class IdentityEdge(StrictModel):
    """One observed name-to-name relationship, with the evidence that produced it.

    Emitted for every related name a source offers, whether or not it was acted on, so the
    identity graph can be diffed across runs and every merge can be explained by the exact
    edge that caused it.
    """

    edge_id: str
    asset_id: str
    #: The name the source gave as the intervention's own.
    primary_name: str
    #: The name the source offered alongside it.
    related_name: str
    relationship: IdentityRelationship
    #: Whether this edge actually contributed an alias to the asset in this run.
    merged: bool
    #: Where the related name came from, e.g. ``clinicaltrials_gov.intervention.otherNames``.
    evidence_field: str
    #: Why the relationship was classified as it was.
    basis: str
    hit_id: str
    source_document_id: str | None = None
    trial_id: str | None = None


class MergeStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPLIED = "APPLIED"
    REVERSED = "REVERSED"
    REJECTED = "REJECTED"


class IdentityMerge(StrictModel):
    merge_id: str
    source_asset_ids: list[str] = Field(min_length=2)
    target_asset_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    deterministic_basis: str | None = None
    evidence_claim_ids: list[str] = Field(default_factory=list)
    status: MergeStatus = MergeStatus.PROPOSED
    analyst_review_required: bool = True
    created_at: datetime
    applied_at: datetime | None = None
    reversed_at: datetime | None = None


class CompiledQuery(StrictModel):
    query_id: str
    query: str
    target_ids: list[str] = Field(default_factory=list)
    modality_ids: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    expansion_depth: int = Field(default=0, ge=0)
    #: ``SeedProvenance`` value: whether this query came from the target's own vocabulary
    #: or from a drug name the drug->target authority supplied. Defaulted so existing
    #: callers keep working, and carried through to the attempt log because it cannot be
    #: reconstructed afterwards -- a document reached by searching the authority's own
    #: reference data corroborates nothing about that data.
    seed_provenance: str = "TARGET_VOCABULARY"
    #: Canonical drug id this query was seeded from, when it was seeded from one.
    seed_drug_id: str | None = None


class RunStatus(str, Enum):
    CONVERGED = "CONVERGED"
    INCOMPLETE = "INCOMPLETE"
    RUNNING = "RUNNING"


class RunMode(str, Enum):
    """What a run's output will be used for, which decides how strict it must be.

    The distinction is not about confidence, it is about consequence. An interactive
    search that degrades when a capability is missing gives a user a narrower answer and
    a warning saying so, which is useful. An evaluation that degrades the same way
    produces a *number* — a recall figure, a benchmark score — and that number then gets
    compared against runs that did not degrade. Nothing downstream can tell the two
    apart, so the strictness has to be enforced before the run, not inferred after it.
    """

    INTERACTIVE = "INTERACTIVE"
    EVALUATION = "EVALUATION"


class TargetTerm(StrictModel):
    canonical_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)


class TargetExpression(StrictModel):
    operator: TargetOperator
    targets: list[TargetTerm] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_expression(self) -> "TargetExpression":
        ids = [target.canonical_id.casefold() for target in self.targets]
        if len(ids) != len(set(ids)):
            raise ValueError("target_expression contains duplicate canonical target IDs")
        if self.operator == TargetOperator.EXACT_COMBINATION and len(ids) < 2:
            raise ValueError("EXACT_COMBINATION requires at least two canonical targets")
        return self


class OutputSpec(StrictModel):
    landscape_mode: LandscapeMode = LandscapeMode.COMBINED
    group_by: LandscapeGroup = LandscapeGroup.COHORT


class BuyerRequirement(StrictModel):
    requirement_id: str = Field(min_length=1)
    domain: RequirementDomain
    fact_type: str = Field(min_length=1)
    operator: RequirementOperator
    expected_value: Any = None
    unit: str | None = None
    pass_condition: str = Field(min_length=1)
    fail_condition: str = Field(min_length=1)
    unknown_condition: str = Field(min_length=1)
    freshness_days: int | None = Field(default=None, gt=0)
    analyst_confirmation_required: bool = False


class EvidenceFloor(StrictModel):
    minimum_stage: str | None = None
    human_poc_required: bool = False
    evaluable_patients_minimum: int | None = Field(default=None, ge=1)
    follow_up_minimum_days: int | None = Field(default=None, ge=1)
    required_evidence_types: list[str] = Field(default_factory=list)


class ClinicalEffectBar(StrictModel):
    indication: str | None = None
    population: str | None = None
    treatment_line: str | None = None
    endpoint: str | None = None
    minimum_effect: float | None = None
    effect_unit: str | None = None
    comparator: str | None = None
    durability_minimum_days: int | None = Field(default=None, ge=1)
    safety_ceiling: float | None = None


class CapabilityConstraints(StrictModel):
    manufacturing: list[BuyerRequirement] = Field(default_factory=list)
    delivery: list[BuyerRequirement] = Field(default_factory=list)
    clinical_operations: list[BuyerRequirement] = Field(default_factory=list)
    commercial: list[BuyerRequirement] = Field(default_factory=list)
    integration: list[BuyerRequirement] = Field(default_factory=list)


class StrategicGap(StrictModel):
    therapeutic_areas: list[str] = Field(min_length=1)
    indications: list[str] = Field(default_factory=list)
    target_expression: TargetExpression
    modalities: list[str] = Field(min_length=1)
    required_biology: list[BuyerRequirement] = Field(default_factory=list)
    capability_constraints: CapabilityConstraints = Field(default_factory=CapabilityConstraints)
    evidence_floor: EvidenceFloor = Field(default_factory=EvidenceFloor)
    clinical_effect_bar: ClinicalEffectBar = Field(default_factory=ClinicalEffectBar)
    acceptable_deal_routes: list[str] = Field(default_factory=list)
    geographic_rights_requirements: list[BuyerRequirement] = Field(default_factory=list)
    missing_evidence_policy: MissingEvidencePolicy = MissingEvidencePolicy.REVIEW


class BuyerIdentity(StrictModel):
    buyer_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    as_of_date: date


class BuyerProblemV2(StrictModel):
    schema_version: Literal["se_buyer_problem_v2"] = "se_buyer_problem_v2"
    problem_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    buyer: BuyerIdentity
    strategic_gap: StrategicGap
    output: OutputSpec = Field(default_factory=OutputSpec)
    ranking_cohort_required: bool = True

    @model_validator(mode="after")
    def validate_requirement_ids(self) -> "BuyerProblemV2":
        constraints = self.strategic_gap.capability_constraints
        requirements = [
            *self.strategic_gap.required_biology,
            *constraints.manufacturing,
            *constraints.delivery,
            *constraints.clinical_operations,
            *constraints.commercial,
            *constraints.integration,
            *self.strategic_gap.geographic_rights_requirements,
        ]
        ids = [requirement.requirement_id for requirement in requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("BuyerRequirement.requirement_id values must be unique")
        return self


class CapabilityEvidence(StrictModel):
    capability_id: str
    category: str
    description: str
    evidence_claim_ids: list[str] = Field(default_factory=list)
    analyst_asserted: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    effective_from: date
    effective_to: date | None = None


class BuyerCapabilityProfile(StrictModel):
    profile_id: str
    buyer_id: str
    version: str
    as_of_date: date
    scientific_translational: list[CapabilityEvidence] = Field(default_factory=list)
    clinical_development: list[CapabilityEvidence] = Field(default_factory=list)
    manufacturing_delivery: list[CapabilityEvidence] = Field(default_factory=list)
    commercial_presence: list[CapabilityEvidence] = Field(default_factory=list)
    portfolio_combinations: list[CapabilityEvidence] = Field(default_factory=list)
    integration_constraints: list[CapabilityEvidence] = Field(default_factory=list)
    risk_transaction_preferences: list[CapabilityEvidence] = Field(default_factory=list)


class SourceDocument(StrictModel):
    document_id: str
    source_url: str
    publisher: str
    document_type: str
    publication_date: date | None = None
    retrieval_date: datetime
    content_hash: str
    snapshot_path: str | None = None
    source_tier: SourceTier
    public_only: bool = True


class SourceEvidenceClaim(StrictModel):
    """One typed statement a source document makes, with the provenance to adjudicate it.

    Provenance is first-class because two sources will disagree -- about targets, codes,
    ownership and stage -- and resolving that needs to know who said it, in which release,
    as written, and on what date. ``entity_string_as_written`` is kept unnormalized
    deliberately: the string a filing used is the evidence, and normalizing it away loses
    the ability to re-adjudicate later.
    """

    claim_id: str
    source_family: str
    #: The source's own release or version identifier, e.g. an EDGAR accession number or a
    #: conference abstract-book edition. Distinct from ``retrieved_at``: the same release
    #: fetched twice must be recognizable as the same evidence.
    source_release: str | None = None
    document_id: str
    document_hash: str
    retrieved_at: datetime
    #: When the source says the statement was true, which is not when it was fetched.
    effective_date: date | None = None
    entity_string_as_written: str
    claim_type: SourceEvidenceType
    claim_value: Any
    #: The quoted span or the structured field path the claim was read from. One of the two
    #: must be present, so no claim exists without a way to check it.
    evidence_span: str | None = None
    structured_field: str | None = None
    #: Relative standing of the source family when claims conflict. Higher wins; equal
    #: ranks are a conflict to record rather than a tie to break silently.
    authority_rank: int = 0

    @model_validator(mode="after")
    def _requires_something_to_check(self) -> "SourceEvidenceClaim":
        if not (self.evidence_span or self.structured_field):
            raise ValueError(
                "a claim needs evidence_span or structured_field: an assertion with no"
                " locatable basis cannot be re-adjudicated"
            )
        return self


class ExtractedClaim(StrictModel):
    claim_id: str
    subject_id: str
    predicate: str
    normalized_value: Any
    unit: str | None = None
    indication: str | None = None
    population: str | None = None
    endpoint: str | None = None
    dose: str | None = None
    data_cut_date: date | None = None
    source_document_id: str
    supporting_passage: str
    locator: str | None = None
    direct_observation: bool = True
    extraction_method: str
    extractor_version: str
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.EXTRACTED
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    supersedes_claim_ids: list[str] = Field(default_factory=list)
    applicable_as_of_date: date


class NormalizedFact(StrictModel):
    fact_id: str
    subject_id: str
    fact_type: str
    value: Any
    unit: str | None = None
    supporting_claim_ids: list[str] = Field(min_length=1)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    analyst_confirmed: bool = False


class TemporalFact(NormalizedFact):
    effective_from: date
    effective_to: date | None = None
    freshness_days: int | None = Field(default=None, gt=0)
    evaluated_as_of: date
    is_stale: bool = False


class GateDecision(StrictModel):
    gate_id: str
    requirement_id: str
    subject_id: str
    status: GateStatus
    observed_fact_ids: list[str] = Field(default_factory=list)
    supporting_or_contradictory_claim_ids: list[str] = Field(default_factory=list)
    rationale: str
    next_action: str | None = None
    analyst_override: GateStatus | None = None
    override_rationale: str | None = None

    @model_validator(mode="after")
    def evidence_required_for_decisions(self) -> "GateDecision":
        if self.status in (GateStatus.PASS, GateStatus.FAIL):
            if not self.observed_fact_ids or not self.supporting_or_contradictory_claim_ids:
                raise ValueError("PASS and FAIL gate decisions require fact and claim evidence")
        if self.status == GateStatus.UNKNOWN and not self.next_action:
            raise ValueError("UNKNOWN gate decisions require a next action")
        if self.analyst_override and not self.override_rationale:
            raise ValueError("analyst overrides require an override rationale")
        return self


class AnalystReviewItem(StrictModel):
    review_id: str
    subject_id: str
    gate_id: str | None = None
    requirement_id: str | None = None
    reason: str
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    claim_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False


class SearchAttempt(StrictModel):
    attempt_id: str
    run_id: str
    pass_number: int = Field(ge=1)
    source: str
    query: str
    aliases_searched: list[str] = Field(default_factory=list)
    outcome: SearchOutcome
    candidates_found: int = Field(default=0, ge=0)
    unique_candidates_added: int = Field(default=0, ge=0)
    error: str | None = None
    retrieval_date: datetime
    applicable_as_of_date: date
    snapshot_ids: list[str] = Field(default_factory=list)
    #: How many times this one query was issued before it settled. A transient CT.gov
    #: timeout is invisible in the outcome alone -- a query that succeeded on its third
    #: attempt and one that succeeded immediately both read SUCCESS -- so the count is
    #: recorded to keep a retried acquisition distinguishable from a clean one.
    attempts_made: int = Field(default=1, ge=1)
    #: Transport pages consumed. Distinguishes a query that returned little because the
    #: universe is small from one that stopped early.
    pages_fetched: int = Field(default=0, ge=0)


class CoveragePass(StrictModel):
    pass_number: int = Field(ge=1)
    new_mentions: int = Field(default=0, ge=0)
    new_provisional_identities: int = Field(default=0, ge=0)
    new_canonical_identities: int = Field(default=0, ge=0)
    new_aliases: int = Field(default=0, ge=0)
    new_claims: int = Field(default=0, ge=0)
    unresolved_mentions: int = Field(default=0, ge=0)
    remaining_frontier: list[str] = Field(default_factory=list)
    source_unique_contributions: dict[str, int] = Field(default_factory=dict)


class TrialUniverseProvenance(StrictModel):
    """Which trial universe a run actually saw, and how it was obtained.

    Recorded so an answer can later be reproduced against the same universe rather than
    against whatever the backend serves today. ``backend`` and ``extractor`` are kept
    separate because they are separate concerns: two backends can feed equivalent
    scientific records through different parsers, and only the pair explains an output.

    Retrieval timestamps are provenance, not identity — two runs over the same universe
    are the same run even though they happened at different times, so nothing that
    compares runs for determinism may read them.
    """

    backend: str
    provider_version: str | None = None
    #: Upstream data release the backend served, e.g. an AACT mirror date.
    source_release: str | None = None
    #: Content-addressed ids of the preserved payloads.
    snapshot_ids: list[str] = Field(default_factory=list)
    query: dict[str, Any] = Field(default_factory=dict)
    retrieval_started_at: datetime | None = None
    retrieval_completed_at: datetime | None = None
    records_considered: int = 0
    records_returned: int = 0
    #: True when a record cap cut the universe short. A truncated universe cannot support
    #: a coverage claim, so this must survive into the manifest rather than being inferred.
    truncated: bool = False
    #: Parser that interpreted the payloads, distinct from the backend that supplied them.
    extractor: str | None = None
    extractor_version: str | None = None
    #: Digest over the identity-bearing fields above, for cheap run-to-run comparison.
    provenance_hash: str | None = None


class RunManifest(StrictModel):
    run_id: str
    problem_id: str
    problem_version: str
    as_of_date: date
    started_at: datetime
    completed_at: datetime | None = None
    code_version: str
    extractor_versions: dict[str, str] = Field(default_factory=dict)
    normalization_version: str
    #: Pinned biomedical entity snapshot, e.g.
    #: ``chembl_36__open_targets_26.06__resolver_v1__modality_v2``. Recorded so a run
    #: stays reproducible after the upstream databases move; ``no_snapshot__…`` means
    #: the run relied solely on problem-declared aliases.
    ontology_version: str | None = None
    #: The trial universe this run queried. ``None`` when trials were not acquired through
    #: a provider, which is itself worth recording: such a run cannot state its universe.
    trial_universe: TrialUniverseProvenance | None = None
    source_status: dict[str, SearchOutcome] = Field(default_factory=dict)
    query_log_ids: list[str] = Field(default_factory=list)
    evidence_snapshot_ids: list[str] = Field(default_factory=list)
    coverage_passes: list[CoveragePass] = Field(default_factory=list)
    known_blind_spots: list[str] = Field(default_factory=list)
    status: RunStatus = RunStatus.RUNNING
    incomplete_reasons: list[str] = Field(default_factory=list)
    #: The subset of ``incomplete_reasons`` that no caller may waive. A mandatory source
    #: that was never configured is a declared, constant blind spot, and a run may be
    #: scored against it knowingly. A mandatory source that *failed mid-acquisition* is
    #: different in kind: the corpus is missing an unknown amount of evidence, so recall
    #: measured on it is not a measurement. ``--allow-incomplete`` covers the first and
    #: must never cover the second.
    fatal_reasons: list[str] = Field(default_factory=list)

    @property
    def scoreable(self) -> bool:
        """Whether this run's corpus may be used for a benchmark or a decision."""

        return not self.fatal_reasons

    @model_validator(mode="after")
    def validate_completion(self) -> "RunManifest":
        if self.status == RunStatus.CONVERGED and self.incomplete_reasons:
            raise ValueError("a CONVERGED run cannot carry incomplete reasons")
        if self.status == RunStatus.INCOMPLETE and not self.incomplete_reasons:
            raise ValueError("an INCOMPLETE run must state at least one reason")
        return self


class CohortAssignment(StrictModel):
    subject_id: str
    indication: str | None = None
    population: str | None = None
    treatment_line: str | None = None
    stage: str | None = None
    endpoint_family: str | None = None
    cohort_id: str | None = None
    status: CohortStatus
    rationale: str
    supporting_claim_ids: list[str] = Field(default_factory=list)


class ClinicalResult(StrictModel):
    result_id: str
    subject_id: str
    indication: str
    population: str
    treatment_line: str
    development_stage: str
    endpoint: str
    endpoint_family: str
    effect_size: float | None = None
    effect_unit: str | None = None
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    evaluable_patients: int | None = Field(default=None, ge=1)
    follow_up_days: int | None = Field(default=None, ge=0)
    comparator: str | None = None
    analysis_set: str | None = None
    safety_grade3plus_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    discontinuation_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    uncontrolled: bool = True
    selected_subgroup: bool = False
    endpoint_switched: bool = False
    incomplete_reporting: bool = False
    supporting_claim_ids: list[str] = Field(min_length=1)


class ClinicalMeaningfulness(StrictModel):
    subject_id: str
    result_id: str
    status: MeaningfulnessStatus
    rationale: str
    limitations: list[str] = Field(default_factory=list)
    evidence_confidence: EvidenceConfidenceTier
    supporting_claim_ids: list[str] = Field(default_factory=list)


class PairwiseProfile(StrictModel):
    subject_id: str
    cohort_id: str
    clinical_tier: AttractivenessTier
    differentiation_tier: AttractivenessTier
    durability_safety_tier: AttractivenessTier
    development_maturity_tier: AttractivenessTier
    operating_fit_tier: AttractivenessTier
    buyer_advantage_tier: AttractivenessTier
    transaction_path_tier: AttractivenessTier
    diligence_burden_tier: AttractivenessTier
    evidence_confidence: EvidenceConfidenceTier
    supporting_claim_ids: list[str] = Field(default_factory=list)


class PairwiseComparison(StrictModel):
    left_subject_id: str
    right_subject_id: str
    cohort_id: str | None = None
    outcome: PairwiseOutcome
    rationale: str
    decisive_dimensions: list[str] = Field(default_factory=list)
    sensitivity_warning: str | None = None


class RankedAsset(StrictModel):
    asset_id: str
    cohort_id: str
    rank: int | None = Field(default=None, ge=1)
    tier: AttractivenessTier
    rationale: str
    abstained: bool = False


class RankingResult(StrictModel):
    ranked: list[RankedAsset] = Field(default_factory=list)
    comparisons: list[PairwiseComparison] = Field(default_factory=list)


class BuyerAdvantageHypothesis(StrictModel):
    buyer_id: str
    asset_id: str
    tier: AttractivenessTier
    rationale: str
    matched_capability_ids: list[str] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    public_pre_diligence: bool = True


class ScreeningRouteHypothesis(StrictModel):
    asset_id: str
    route: str | None = None
    status: GateStatus
    rationale: str
    supporting_fact_ids: list[str] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    decisive_unknown: str | None = None
    public_pre_diligence: bool = True
