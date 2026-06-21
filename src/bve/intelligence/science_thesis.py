"""Layer 0 science thesis models and deterministic Phase 1 scoring.

The Phase 1 contract is intentionally heuristic. It separates the science thesis
from the POS modifier so downstream users can see what must be true, what is
missing, and how the current evidence heuristically changes technical POS.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field


class ScienceMode(str, Enum):
    DISCOVERY_INVESTMENT = "discovery_investment"
    BD = "bd"


class ScienceQuestion(str, Enum):
    RIGHT_TARGET = "right_target"
    ENOUGH_DRUG = "enough_drug"
    BIOMARKER_TRANSLATION = "biomarker_translation"
    HUMAN_POC = "human_poc"
    CLINICAL_MEANINGFULNESS = "clinical_meaningfulness"
    SAFETY_MARGIN = "safety_margin"


class EvidencePolarity(str, Enum):
    SUPPORTS = "supports"
    WEAKENS = "weakens"
    NEUTRAL = "neutral"


class EvidenceResolution(str, Enum):
    UNRESOLVED = "unresolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    RESOLVED = "resolved"
    REFUTED = "refuted"


class ScienceKillFlag(str, Enum):
    TARGET_REFUTED = "target_refuted"
    NEGATIVE_HUMAN_POC = "negative_human_poc"
    INFEASIBLE_EXPOSURE = "infeasible_exposure"
    UNACCEPTABLE_SAFETY = "unacceptable_safety"


class NegativeHumanPOCInterpretability(str, Enum):
    CLEAR = "clear"
    AMBIGUOUS = "ambiguous"
    WEAK = "weak"


class BindingConstraintSource(str, Enum):
    COMPONENT_SCORE = "component_score"
    MANUAL_OVERRIDE = "manual_override"
    HARD_CAP = "hard_cap"


class CalibrationStatus(str, Enum):
    HEURISTIC = "heuristic"
    CALIBRATED = "calibrated"
    DEPRECATED = "deprecated"


class EvidenceLayerUse(str, Enum):
    LAYER0 = "layer0"
    POS = "pos"


class EvidenceResolutionBasis(str, Enum):
    UNSPECIFIED = "unspecified"
    PRECLINICAL = "preclinical"
    HUMAN_PKPD = "human_pkpd"
    HUMAN_DOSE_RESPONSE = "human_dose_response"
    HUMAN_EXPOSURE_RESPONSE = "human_exposure_response"
    HUMAN_CLINICAL_POC = "human_clinical_poc"


class BDRoute(str, Enum):
    AVOID = "avoid"
    MONITOR = "monitor"
    COLLABORATION = "collaboration"
    OPTION = "option"
    EQUITY_PLUS_COLLABORATION = "equity_plus_collaboration"
    LICENSE = "license"
    MAJOR_LICENSE = "major_license"
    ACQUISITION = "acquisition"


class ScienceEvidenceItem(BaseModel):
    source_id: str = ""
    source_type: str = ""
    claim: str
    polarity: EvidencePolarity = EvidencePolarity.NEUTRAL
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    component: str = ""
    evidence_tags: list[str] = Field(default_factory=list)
    layer_uses: list[EvidenceLayerUse] = Field(default_factory=list)
    rationale: str = ""


class EvidenceQualityFactors(BaseModel):
    species_relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    model_relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    endpoint_relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    sample_size: float = Field(default=0.5, ge=0.0, le=1.0)
    reproducibility: float = Field(default=0.5, ge=0.0, le=1.0)
    independent_validation: float = Field(default=0.5, ge=0.0, le=1.0)
    recency: float = Field(default=0.5, ge=0.0, le=1.0)
    source_credibility: float = Field(default=0.5, ge=0.0, le=1.0)


class ClinicalMeaningfulnessContext(BaseModel):
    standard_of_care_context: str = ""
    competitive_effect_threshold: float | None = None
    clinically_meaningful_delta: float | None = None


class SafetyRiskContext(BaseModel):
    mechanistic_safety_risk: str = ""
    observed_clinical_safety_signal: str = ""
    tolerability_adherence_risk: str = ""
    regulatory_safety_burden: str = ""


class ScienceComponentScore(BaseModel):
    name: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    resolution: EvidenceResolution = EvidenceResolution.UNRESOLVED
    resolution_basis: EvidenceResolutionBasis = EvidenceResolutionBasis.UNSPECIFIED
    evidence_for: list[ScienceEvidenceItem] = Field(default_factory=list)
    evidence_against: list[ScienceEvidenceItem] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    rationale: str = ""


class BeliefState(BaseModel):
    prior_belief: float = Field(default=0.5, ge=0.0, le=1.0)
    current_belief: float = Field(default=0.5, ge=0.0, le=1.0)
    update_history: list[str] = Field(default_factory=list)


class ScienceModifierResult(BaseModel):
    scoring_version: str = "science_thesis_phase1"
    weight_set_version: str = "phase1_v1"
    calibration_status: CalibrationStatus = CalibrationStatus.HEURISTIC
    science_score: float = Field(ge=0.0, le=1.0)
    science_score_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    heuristic_science_modifier: float = Field(ge=0.0, le=1.1)
    binding_constraint: float = Field(ge=0.0, le=1.0)
    binding_constraint_source: BindingConstraintSource = BindingConstraintSource.COMPONENT_SCORE
    modifier_cap: float = Field(default=1.1, ge=0.0, le=1.1)
    kill_flags: list[ScienceKillFlag] = Field(default_factory=list)
    negative_human_poc_interpretability: NegativeHumanPOCInterpretability | None = None
    warnings: list[str] = Field(default_factory=list)
    rationale: str = ""


class ScienceThesis(BaseModel):
    asset_id: str
    asset_name: str = ""
    scoring_version: str = "science_thesis_phase1"
    weight_set_version: str = "phase1_v1"
    calibration_status: CalibrationStatus = CalibrationStatus.HEURISTIC
    indication: str = ""
    phase: str = ""
    modality: str = ""
    mode: ScienceMode = ScienceMode.DISCOVERY_INVESTMENT
    core_biological_hypothesis: str = ""
    binding_science_question: ScienceQuestion
    secondary_science_questions: list[ScienceQuestion] = Field(default_factory=list)
    what_must_be_true: list[str] = Field(default_factory=list)
    expected_biomarker_changes: list[str] = Field(default_factory=list)
    expected_clinical_changes: list[str] = Field(default_factory=list)
    key_readouts: list[str] = Field(default_factory=list)
    key_failure_modes: list[str] = Field(default_factory=list)
    missing_critical_evidence: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    must_answer_before_next_stage: list[str] = Field(default_factory=list)
    clinical_meaningfulness_context: ClinicalMeaningfulnessContext = Field(
        default_factory=ClinicalMeaningfulnessContext
    )
    safety_context: SafetyRiskContext = Field(default_factory=SafetyRiskContext)
    components: dict[str, ScienceComponentScore] = Field(default_factory=dict)
    belief_state: BeliefState = Field(default_factory=BeliefState)
    modifier_result: ScienceModifierResult | None = None
    next_readout_requirement: str = ""
    bd_diligence_questions: list[str] = Field(default_factory=list)


class BuyerProblem(BaseModel):
    buyer_id: str
    buyer_name: str = ""
    strategic_gap: str = ""
    required_ta: list[str] = Field(default_factory=list)
    required_targets: list[str] = Field(default_factory=list)
    required_modalities: list[str] = Field(default_factory=list)
    excluded_tas: list[str] = Field(default_factory=list)
    excluded_modalities: list[str] = Field(default_factory=list)
    must_have_evidence: list[str] = Field(default_factory=list)
    capability_constraints: list[str] = Field(default_factory=list)
    existing_portfolio_context: str = ""
    known_internal_overlap: list[str] = Field(default_factory=list)
    combination_or_lifecycle_fit: str = ""
    alternative_assets_available: list[str] = Field(default_factory=list)
    competitive_intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    scarcity_value: float = Field(default=0.5, ge=0.0, le=1.0)
    time_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    urgency: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class BDActionabilityResult(BaseModel):
    passed_hard_gates: bool
    failed_gates: list[str] = Field(default_factory=list)
    buyer_problem_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    science_thesis_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    diligence_readiness: float = Field(default=0.0, ge=0.0, le=1.0)
    modality_capability_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    buyer_owner_advantage: float = Field(default=0.0, ge=0.0, le=1.0)
    internal_portfolio_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    assessed_internal_overlap_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    combination_or_lifecycle_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    alternative_assets_available: list[str] = Field(default_factory=list)
    competitive_intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    scarcity_value: float = Field(default=0.5, ge=0.0, le=1.0)
    time_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    deal_feasibility: float = Field(default=0.0, ge=0.0, le=1.0)
    bd_actionability: float = Field(default=0.0, ge=0.0, le=1.0)
    bd_actionability_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    recommended_bd_route: BDRoute = BDRoute.MONITOR
    route_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    route_rationale: str = ""
    warnings: list[str] = Field(default_factory=list)
    diligence_questions: list[str] = Field(default_factory=list)


_COMPONENT_TO_QUESTION = {
    "T": ScienceQuestion.RIGHT_TARGET,
    "target_pathway": ScienceQuestion.RIGHT_TARGET,
    "D": ScienceQuestion.ENOUGH_DRUG,
    "dose_exposure_pkpd": ScienceQuestion.ENOUGH_DRUG,
    "B": ScienceQuestion.BIOMARKER_TRANSLATION,
    "biomarker_translation": ScienceQuestion.BIOMARKER_TRANSLATION,
    "H": ScienceQuestion.HUMAN_POC,
    "human_poc": ScienceQuestion.HUMAN_POC,
    "M": ScienceQuestion.CLINICAL_MEANINGFULNESS,
    "clinical_meaningfulness": ScienceQuestion.CLINICAL_MEANINGFULNESS,
    "S": ScienceQuestion.SAFETY_MARGIN,
    "safety_tolerability": ScienceQuestion.SAFETY_MARGIN,
}

_QUESTION_TO_COMPONENT = {value: key for key, value in _COMPONENT_TO_QUESTION.items() if len(key) == 1}

_PHASE_WEIGHTS: dict[str, dict[str, float]] = {
    "preclinical": {"T": 0.30, "D": 0.25, "B": 0.20, "H": 0.05, "M": 0.05, "S": 0.05, "Q": 0.10},
    "phase1": {"T": 0.20, "D": 0.30, "B": 0.20, "H": 0.10, "M": 0.05, "S": 0.05, "Q": 0.10},
    "phase_1": {"T": 0.20, "D": 0.30, "B": 0.20, "H": 0.10, "M": 0.05, "S": 0.05, "Q": 0.10},
    "phase2": {"T": 0.15, "D": 0.15, "B": 0.15, "H": 0.25, "M": 0.15, "S": 0.10, "Q": 0.05},
    "phase_2": {"T": 0.15, "D": 0.15, "B": 0.15, "H": 0.25, "M": 0.15, "S": 0.10, "Q": 0.05},
    "post_phase_2": {"T": 0.10, "D": 0.10, "B": 0.10, "H": 0.30, "M": 0.20, "S": 0.15, "Q": 0.05},
    "phase3": {"T": 0.10, "D": 0.10, "B": 0.10, "H": 0.25, "M": 0.20, "S": 0.20, "Q": 0.05},
    "phase_3": {"T": 0.10, "D": 0.10, "B": 0.10, "H": 0.25, "M": 0.20, "S": 0.20, "Q": 0.05},
    "nda_bla": {"T": 0.10, "D": 0.10, "B": 0.10, "H": 0.25, "M": 0.20, "S": 0.20, "Q": 0.05},
}

_POST_PHASE2_PHASES = {"post_phase_2", "phase3", "phase_3", "nda_bla", "approved"}


def _norm_phase(phase: str) -> str:
    return phase.lower().replace(" ", "_").replace("-", "_")


def _component_score(components: dict[str, ScienceComponentScore], key: str) -> float:
    component = components.get(key)
    if component is None:
        return 0.5
    return component.score


def _component_confidence(components: Iterable[ScienceComponentScore]) -> float:
    values = [component.confidence for component in components]
    if not values:
        return 0.5
    return round(sum(values) / len(values), 4)


def score_evidence_quality(factors: EvidenceQualityFactors) -> ScienceComponentScore:
    """Build the `Q` component from explicit evidence-quality factors."""
    values = factors.model_dump().values()
    score = round(sum(values) / 8, 4)
    return ScienceComponentScore(
        name="Q",
        score=score,
        confidence=score,
        resolution=EvidenceResolution.PARTIALLY_RESOLVED if score >= 0.5 else EvidenceResolution.UNRESOLVED,
        rationale="Evidence quality reflects species/model/endpoint relevance, sample size, "
        "reproducibility, independent validation, recency, and source credibility.",
    )


def find_biomarker_overlap_warnings(evidence_items: Iterable[ScienceEvidenceItem]) -> list[str]:
    """Detect biomarker evidence that risks double-counting across Layer 0 and POS."""
    warnings: list[str] = []
    for item in evidence_items:
        tags = set(item.evidence_tags)
        layer_uses = set(item.layer_uses)
        if "biomarker_clinical_bridge" in tags and {
            EvidenceLayerUse.LAYER0,
            EvidenceLayerUse.POS,
        }.issubset(layer_uses):
            warnings.append("biomarker_double_counting_risk")
            break
    return warnings


def post_phase2_enough_drug_resolved(phase: str, components: dict[str, ScienceComponentScore]) -> bool:
    """Return whether post-Phase-2 enough-drug risk is resolved by human evidence."""
    if _norm_phase(phase) not in _POST_PHASE2_PHASES:
        return False
    dose_component = components.get("D")
    human_component = components.get("H")
    if dose_component is None or human_component is None:
        return False
    human_resolution_bases = {
        EvidenceResolutionBasis.HUMAN_PKPD,
        EvidenceResolutionBasis.HUMAN_DOSE_RESPONSE,
        EvidenceResolutionBasis.HUMAN_EXPOSURE_RESPONSE,
        EvidenceResolutionBasis.HUMAN_CLINICAL_POC,
    }
    human_evidence_tags = {
        "human_pkpd",
        "human_dose_response",
        "human_exposure_response",
        "human_target_engagement",
    }
    has_human_basis = dose_component.resolution_basis in human_resolution_bases
    has_human_tag = any(
        human_evidence_tags.intersection(item.evidence_tags)
        for item in [*dose_component.evidence_for, *dose_component.evidence_against]
    )
    return (
        dose_component.resolution in {EvidenceResolution.RESOLVED, EvidenceResolution.PARTIALLY_RESOLVED}
        and human_component.score >= 0.5
        and (has_human_basis or has_human_tag)
    )


def _binding_component_key(question: ScienceQuestion) -> str:
    return _QUESTION_TO_COMPONENT.get(question, "T")


def compute_science_modifier(
    *,
    phase: str,
    binding_science_question: ScienceQuestion,
    components: dict[str, ScienceComponentScore],
    direct_negative_human_poc: bool = False,
    negative_human_poc_interpretability: NegativeHumanPOCInterpretability | None = None,
    no_feasible_exposure_at_active_dose: bool = False,
    target_pathway_refuted: bool = False,
    binding_constraint_override: float | None = None,
    additional_warnings: list[str] | None = None,
) -> ScienceModifierResult:
    """Compute the deterministic Phase 1 heuristic science modifier."""
    weights = _PHASE_WEIGHTS.get(_norm_phase(phase), _PHASE_WEIGHTS["phase2"])
    weighted = sum(_component_score(components, key) * weight for key, weight in weights.items())

    binding_source = BindingConstraintSource.COMPONENT_SCORE
    if binding_constraint_override is None:
        binding_key = _binding_component_key(binding_science_question)
        binding_constraint = _component_score(components, binding_key)
    else:
        binding_constraint = max(0.0, min(1.0, binding_constraint_override))
        binding_source = BindingConstraintSource.MANUAL_OVERRIDE

    science_score = min(weighted, binding_constraint + 0.15)
    heuristic_modifier = 0.70 + (0.40 * science_score)
    modifier_cap = 1.10
    kill_flags: list[ScienceKillFlag] = []
    warnings: list[str] = list(additional_warnings or [])

    if direct_negative_human_poc:
        if negative_human_poc_interpretability == NegativeHumanPOCInterpretability.CLEAR:
            modifier_cap = min(modifier_cap, 0.60)
            kill_flags.append(ScienceKillFlag.NEGATIVE_HUMAN_POC)
        else:
            warnings.append("ambiguous_negative_human_poc")

    if no_feasible_exposure_at_active_dose:
        modifier_cap = min(modifier_cap, 0.65)
        kill_flags.append(ScienceKillFlag.INFEASIBLE_EXPOSURE)

    if target_pathway_refuted:
        modifier_cap = min(modifier_cap, 0.40)
        kill_flags.append(ScienceKillFlag.TARGET_REFUTED)
        warnings.append("target_pathway_refuted_program_kill")

    if binding_source == BindingConstraintSource.MANUAL_OVERRIDE:
        warnings.append("manual_binding_constraint_override")

    if heuristic_modifier > modifier_cap:
        binding_source = BindingConstraintSource.HARD_CAP
    heuristic_modifier = min(heuristic_modifier, modifier_cap)

    confidence = _component_confidence(components.values())
    if science_score >= 0.70 and confidence < 0.50:
        warnings.append("low_confidence_high_score")

    return ScienceModifierResult(
        science_score=round(science_score, 4),
        science_score_confidence=confidence,
        heuristic_science_modifier=round(heuristic_modifier, 4),
        binding_constraint=round(binding_constraint, 4),
        binding_constraint_source=binding_source,
        modifier_cap=round(modifier_cap, 4),
        kill_flags=kill_flags,
        negative_human_poc_interpretability=negative_human_poc_interpretability,
        warnings=warnings,
        rationale=(
            f"weighted={weighted:.3f}; binding={binding_constraint:.3f}; "
            f"modifier_cap={modifier_cap:.3f}"
        ),
    )


class ScienceThesisScoringInput(BaseModel):
    thesis: ScienceThesis
    direct_negative_human_poc: bool = False
    negative_human_poc_interpretability: NegativeHumanPOCInterpretability | None = None
    no_feasible_exposure_at_active_dose: bool = False
    target_pathway_refuted: bool = False
    binding_constraint_override: float | None = None


def score_science_thesis(scoring_input: ScienceThesisScoringInput) -> ScienceThesis:
    """Return a copy of a thesis with its Phase 1 modifier populated."""
    thesis = scoring_input.thesis
    evidence_items: list[ScienceEvidenceItem] = []
    for component in thesis.components.values():
        evidence_items.extend(component.evidence_for)
        evidence_items.extend(component.evidence_against)
    modifier = compute_science_modifier(
        phase=thesis.phase,
        binding_science_question=thesis.binding_science_question,
        components=thesis.components,
        direct_negative_human_poc=scoring_input.direct_negative_human_poc,
        negative_human_poc_interpretability=scoring_input.negative_human_poc_interpretability,
        no_feasible_exposure_at_active_dose=scoring_input.no_feasible_exposure_at_active_dose,
        target_pathway_refuted=scoring_input.target_pathway_refuted,
        binding_constraint_override=scoring_input.binding_constraint_override,
        additional_warnings=find_biomarker_overlap_warnings(evidence_items),
    )
    return thesis.model_copy(update={"modifier_result": modifier})


def evaluate_bd_hard_gates(
    buyer_problem: BuyerProblem,
    *,
    therapeutic_area: str,
    target: str,
    modality: str,
    solves_buyer_problem: bool,
) -> list[str]:
    """Return failed BD gates for buyer-defined sandbox fit."""
    failed: list[str] = []
    ta = therapeutic_area.lower()
    target_l = target.lower()
    modality_l = modality.lower()

    if buyer_problem.required_ta and ta not in {item.lower() for item in buyer_problem.required_ta}:
        failed.append("ta_outside_buyer_strategy")
    if ta in {item.lower() for item in buyer_problem.excluded_tas}:
        failed.append("ta_excluded")
    if buyer_problem.required_targets and target_l not in {
        item.lower() for item in buyer_problem.required_targets
    }:
        failed.append("target_outside_buyer_sandbox")
    if buyer_problem.required_modalities and modality_l not in {
        item.lower() for item in buyer_problem.required_modalities
    }:
        failed.append("modality_outside_buyer_sandbox")
    if modality_l in {item.lower() for item in buyer_problem.excluded_modalities}:
        failed.append("modality_excluded")
    if not solves_buyer_problem:
        failed.append("does_not_solve_buyer_problem")
    return failed


def recommend_bd_route(
    *,
    passed_hard_gates: bool,
    science_thesis_fit: float,
    human_poc_strength: float,
    strategic_fit: float,
    urgency: float,
    platform_upside: float = 0.0,
    uncertainty: float = 0.5,
    thesis_refuted: bool = False,
) -> tuple[BDRoute, float, str]:
    """Simple deterministic Phase 1 deal-route guidance."""
    if thesis_refuted or not passed_hard_gates:
        return BDRoute.AVOID, 0.85, "Fails hard gates or thesis is refuted."
    if human_poc_strength >= 0.70 and strategic_fit >= 0.70 and urgency >= 0.70:
        return BDRoute.ACQUISITION, 0.70, "Strong human POC with urgent strategic fit."
    if human_poc_strength >= 0.70 and strategic_fit >= 0.60:
        return BDRoute.LICENSE, 0.65, "Strong human POC and strategic fit support license."
    if platform_upside >= 0.70 and uncertainty >= 0.50:
        return (
            BDRoute.EQUITY_PLUS_COLLABORATION,
            0.60,
            "Platform upside remains meaningful but uncertainty is high.",
        )
    if science_thesis_fit < 0.55 or uncertainty >= 0.65:
        return BDRoute.OPTION, 0.55, "Early or uncertain science supports option-style exposure."
    return BDRoute.COLLABORATION, 0.55, "Moderate fit supports collaboration before larger commitment."


def compute_bd_actionability(
    *,
    passed_hard_gates: bool,
    failed_gates: list[str] | None = None,
    buyer_problem_fit: float = 0.0,
    science_thesis_fit: float = 0.0,
    evidence_quality: float = 0.0,
    diligence_readiness: float = 0.0,
    modality_capability_fit: float = 0.0,
    buyer_owner_advantage: float = 0.0,
    internal_portfolio_fit: float = 0.0,
    assessed_internal_overlap_risk: float = 0.0,
    combination_or_lifecycle_fit: float = 0.0,
    alternative_assets_available: list[str] | None = None,
    competitive_intensity: float = 0.5,
    scarcity_value: float = 0.5,
    time_sensitivity: float = 0.5,
    deal_feasibility: float = 0.0,
    confidence_inputs: list[float] | None = None,
    route: BDRoute = BDRoute.MONITOR,
    route_confidence: float = 0.5,
    route_rationale: str = "",
    warnings: list[str] | None = None,
    diligence_questions: list[str] | None = None,
) -> BDActionabilityResult:
    """Compute BD actionability after hard gates."""
    failed = failed_gates or []
    if not passed_hard_gates:
        return BDActionabilityResult(
            passed_hard_gates=False,
            failed_gates=failed,
            recommended_bd_route=BDRoute.AVOID,
            route_confidence=0.85,
            route_rationale="Asset failed BD hard gates before actionability scoring.",
            alternative_assets_available=alternative_assets_available or [],
            competitive_intensity=competitive_intensity,
            scarcity_value=scarcity_value,
            time_sensitivity=time_sensitivity,
            warnings=warnings or [],
            diligence_questions=diligence_questions or [],
        )

    buyer_problem_fit_adjusted = min(1.0, buyer_problem_fit + (0.05 * time_sensitivity))
    buyer_owner_advantage_adjusted = min(
        1.0,
        buyer_owner_advantage
        + (0.05 * internal_portfolio_fit)
        + (0.05 * combination_or_lifecycle_fit)
        + (0.05 * scarcity_value),
    )
    deal_feasibility_adjusted = max(
        0.0,
        min(1.0, deal_feasibility - (0.05 * assessed_internal_overlap_risk)),
    )
    score = (
        0.30 * buyer_problem_fit_adjusted
        + 0.15 * science_thesis_fit
        + 0.15 * evidence_quality
        + 0.10 * diligence_readiness
        + 0.10 * modality_capability_fit
        + 0.10 * buyer_owner_advantage_adjusted
        + 0.10 * deal_feasibility_adjusted
    )
    confidence_values = confidence_inputs or [evidence_quality, diligence_readiness]
    confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0.5

    final_warnings = list(warnings or [])
    if score >= 0.70 and confidence < 0.50:
        final_warnings.append("low_confidence_high_score")

    return BDActionabilityResult(
        passed_hard_gates=True,
        failed_gates=[],
        buyer_problem_fit=round(buyer_problem_fit_adjusted, 4),
        science_thesis_fit=science_thesis_fit,
        evidence_quality=evidence_quality,
        diligence_readiness=diligence_readiness,
        modality_capability_fit=modality_capability_fit,
        buyer_owner_advantage=round(buyer_owner_advantage_adjusted, 4),
        internal_portfolio_fit=internal_portfolio_fit,
        assessed_internal_overlap_risk=assessed_internal_overlap_risk,
        combination_or_lifecycle_fit=combination_or_lifecycle_fit,
        alternative_assets_available=alternative_assets_available or [],
        competitive_intensity=competitive_intensity,
        scarcity_value=scarcity_value,
        time_sensitivity=time_sensitivity,
        deal_feasibility=round(deal_feasibility_adjusted, 4),
        bd_actionability=round(score, 4),
        bd_actionability_confidence=confidence,
        recommended_bd_route=route,
        route_confidence=route_confidence,
        route_rationale=route_rationale,
        warnings=final_warnings,
        diligence_questions=diligence_questions or [],
    )
