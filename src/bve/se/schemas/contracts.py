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
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NO_EVIDENCE_FOUND = "NO_EVIDENCE_FOUND"


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
    company_ids: list[str] = Field(default_factory=list)
    trial_ids: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    modality_id: str | None = None
    indication_ids: list[str] = Field(default_factory=list)
    development_stage: str | None = None
    development_status: str | None = None
    last_confirmed_active_date: date | None = None
    mention_ids: list[str] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    provisional: bool = True


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


class RunStatus(str, Enum):
    CONVERGED = "CONVERGED"
    INCOMPLETE = "INCOMPLETE"
    RUNNING = "RUNNING"


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
    source_status: dict[str, SearchOutcome] = Field(default_factory=dict)
    query_log_ids: list[str] = Field(default_factory=list)
    evidence_snapshot_ids: list[str] = Field(default_factory=list)
    coverage_passes: list[CoveragePass] = Field(default_factory=list)
    known_blind_spots: list[str] = Field(default_factory=list)
    status: RunStatus = RunStatus.RUNNING
    incomplete_reasons: list[str] = Field(default_factory=list)

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
