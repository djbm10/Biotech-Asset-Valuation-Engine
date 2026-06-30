"""Layer 0 science thesis models and deterministic Phase 1 scoring.

The Phase 1 contract is intentionally heuristic. It separates the science thesis
from the POS modifier so downstream users can see what must be true, what is
missing, and how the current evidence heuristically changes technical POS.
"""

from __future__ import annotations

from enum import Enum
from math import prod
from typing import Iterable, Mapping

from pydantic import BaseModel, Field

from bve.config.assumptions_loader import AssumptionsLoader


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


class GuardrailSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CAP = "cap"
    KILL = "kill"


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


class EvidenceGrade(str, Enum):
    """How confident we can be in the evidence behind a BD actionability score.

    The tool ingests public information only, so it can rank but never confer
    in-lab conviction. ``screening_public`` is the default the tool emits; the
    stronger grades are only reachable after the buyer's own technical diligence.
    """

    SCREENING_PUBLIC = "screening_public"
    PARTIAL_DISCLOSED = "partial_disclosed"
    DILIGENCE_CONFIRMED = "diligence_confirmed"


# Stage 3 cap: a public-data-only asset is never "ready to transact". Its
# actionability is capped and carries a mandatory ``pre_diligence`` flag.
SCREENING_PUBLIC_ACTIONABILITY_CAP = 0.75
# Stage 2: screening-grade evidence_quality cannot dominate the fit score.
EVIDENCE_QUALITY_TERM_CAP = 0.75


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


def _neutral_component(name: str) -> ScienceComponentScore:
    return ScienceComponentScore(
        name=name,
        score=0.5,
        confidence=0.5,
        resolution=EvidenceResolution.UNRESOLVED,
        rationale="Neutral placeholder until source-backed evidence is mapped.",
    )


class ScienceScoredQuestions(BaseModel):
    """Scored biological thesis risk only: T/D/B.

    ``ScienceQuestion`` is already the public enum for binding-question names, so
    this model uses a distinct name while representing the plan's question split.
    """

    right_target: ScienceComponentScore = Field(
        default_factory=lambda: _neutral_component("T")
    )
    enough_drug: ScienceComponentScore = Field(
        default_factory=lambda: _neutral_component("D")
    )
    translation_bridge: ScienceComponentScore = Field(
        default_factory=lambda: _neutral_component("B")
    )


class ScienceContext(BaseModel):
    """Non-scored science context for audit, memo, and BD routing."""

    human_poc: ScienceComponentScore | None = None
    clinical_meaningfulness: ClinicalMeaningfulnessContext = Field(
        default_factory=ClinicalMeaningfulnessContext
    )
    evidence_quality: EvidenceQualityFactors = Field(default_factory=EvidenceQualityFactors)


class ScienceGuardrail(BaseModel):
    """Downside-only science guardrails; never positive score drivers."""

    target_refuted: bool = False
    infeasible_exposure: bool = False
    biomarker_bridge_refuted: bool = False
    negative_human_poc: bool = False
    negative_human_poc_interpretability: NegativeHumanPOCInterpretability | None = None
    unacceptable_safety: bool = False
    mechanism_linked_severe_safety: bool = False
    manageable_safety_concern: bool = False


class ScienceGuardrailEffect(BaseModel):
    key: str
    triggered: bool = False
    hard_cap: float | None = Field(default=None, ge=0.0, le=1.0)
    soft_derate: float = Field(default=1.0, ge=0.0, le=1.0)
    severity: GuardrailSeverity = GuardrailSeverity.INFO
    rationale: str = ""


class SciencePOSOverlapWarning(BaseModel):
    key: str
    severity: GuardrailSeverity = GuardrailSeverity.WARN
    shared_source_id: str = ""
    component: str = ""
    rationale: str = ""


class BeliefState(BaseModel):
    prior_belief: float = Field(default=0.5, ge=0.0, le=1.0)
    current_belief: float = Field(default=0.5, ge=0.0, le=1.0)
    update_history: list[str] = Field(default_factory=list)


class ScienceModifierResult(BaseModel):
    scoring_version: str = "science_thesis_phase2"
    weight_set_version: str = "phase2_tdb_v1"
    calibration_status: CalibrationStatus = CalibrationStatus.HEURISTIC
    science_score: float = Field(ge=0.0, le=1.0)
    science_score_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    heuristic_science_modifier: float = Field(ge=0.0, le=1.1)
    binding_constraint: float = Field(ge=0.0, le=1.0)
    binding_constraint_source: BindingConstraintSource = BindingConstraintSource.COMPONENT_SCORE
    modifier_cap: float = Field(default=1.1, ge=0.0, le=1.1)
    kill_flags: list[ScienceKillFlag] = Field(default_factory=list)
    negative_human_poc_interpretability: NegativeHumanPOCInterpretability | None = None
    guardrail_effects: list[ScienceGuardrailEffect] = Field(default_factory=list)
    combined_soft_derate: float = Field(default=1.0, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    rationale: str = ""


class ScienceThesis(BaseModel):
    asset_id: str
    asset_name: str = ""
    scoring_version: str = "science_thesis_phase2"
    weight_set_version: str = "phase2_tdb_v1"
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
    scored_questions: ScienceScoredQuestions = Field(default_factory=ScienceScoredQuestions)
    science_context: ScienceContext = Field(default_factory=ScienceContext)
    science_guardrail: ScienceGuardrail = Field(default_factory=ScienceGuardrail)
    components: dict[str, ScienceComponentScore] = Field(default_factory=dict)
    belief_state: BeliefState = Field(default_factory=BeliefState)
    modifier_result: ScienceModifierResult | None = None
    killer_question_set: object | None = Field(default=None, exclude=True)
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
    # science_thesis_fit retained for backward compatibility (memo + older callers);
    # Stage 2 now splits it into human_poc_strength + clinical_meaningfulness.
    science_thesis_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    human_poc_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    clinical_meaningfulness: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_grade: EvidenceGrade = EvidenceGrade.SCREENING_PUBLIC
    pre_diligence: bool = True
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
    killer_question_set: object | None = Field(default=None, exclude=True)


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

_SCIENCE_KEY_MAP: dict[str, str] = {
    "T": "scored_questions.right_target",
    "target_pathway": "scored_questions.right_target",
    "D": "scored_questions.enough_drug",
    "dose_exposure_pkpd": "scored_questions.enough_drug",
    "B": "scored_questions.translation_bridge",
    "biomarker_translation": "scored_questions.translation_bridge",
    "translation_bridge": "scored_questions.translation_bridge",
    # Legacy keys route to non-scored homes after the ownership split.
    "H": "science_context.human_poc",
    "human_poc": "science_context.human_poc",
    "M": "science_context.clinical_meaningfulness",
    "clinical_meaningfulness": "science_context.clinical_meaningfulness",
    "S": "science_guardrail",
    "safety_tolerability": "science_guardrail",
    "Q": "science_context.evidence_quality",
    "evidence_quality": "science_context.evidence_quality",
}


def route_science_key(key: str) -> str:
    """Return the Phase 2 ownership home for a legacy science component key."""
    return _SCIENCE_KEY_MAP.get(key, "unmapped")

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


def check_science_pos_overlap(
    components: dict[str, ScienceComponentScore],
    pos_fired_adjusters: set[str] | None = None,
) -> list[SciencePOSOverlapWarning]:
    """Audit source-backed science evidence for science-to-POS double counting."""
    fired = {item.lower() for item in (pos_fired_adjusters or set())}
    overlap_warnings: list[SciencePOSOverlapWarning] = []
    related_pos_tags = {
        "human_proof_of_mechanism",
        "biomarker_clinical_bridge",
        "biomarker_selection",
        "endpoint_type",
        "clinical_effect_magnitude",
        "safety_profile",
        "dose_selection_confidence",
    }

    for component in components.values():
        for item in [*component.evidence_for, *component.evidence_against]:
            tags = {tag.lower() for tag in item.evidence_tags}
            layer_uses = set(item.layer_uses)
            if {EvidenceLayerUse.LAYER0, EvidenceLayerUse.POS}.issubset(layer_uses):
                overlap_warnings.append(
                    SciencePOSOverlapWarning(
                        key="shared_science_pos_evidence",
                        severity=GuardrailSeverity.KILL,
                        shared_source_id=item.source_id,
                        component=component.name,
                        rationale="Same source-backed evidence item is used by science and POS.",
                    )
                )
                continue

            if tags & related_pos_tags or fired & tags:
                overlap_warnings.append(
                    SciencePOSOverlapWarning(
                        key="related_science_pos_signal",
                        severity=GuardrailSeverity.WARN,
                        shared_source_id=item.source_id,
                        component=component.name,
                        rationale="Science evidence is related to a POS factor; review for overlap.",
                    )
                )
    return overlap_warnings


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


def _tdb_components(
    components: dict[str, ScienceComponentScore],
) -> dict[str, ScienceComponentScore]:
    return {
        "T": components.get("T", _neutral_component("T")),
        "D": components.get("D", _neutral_component("D")),
        "B": components.get("B", _neutral_component("B")),
    }


def _binding_tdb_key(components: dict[str, ScienceComponentScore]) -> str:
    tdb = _tdb_components(components)
    return min(tdb, key=lambda key: tdb[key].score)


def _science_phase_weights(phase: str) -> Mapping[str, float]:
    weights = AssumptionsLoader.get().science_phase_weights_tdb
    phase_key = _norm_phase(phase)
    compact_key = phase_key.replace("_", "")
    return weights.get(phase_key, weights.get(compact_key, weights["phase2"]))


def _pos_factor_keys_for_component(component_key: str) -> set[str]:
    return {
        "T": {
            "T",
            "right_target",
            "target_pathway",
            "moa_precedent",
            "human_proof_of_mechanism",
        },
        "D": {
            "D",
            "enough_drug",
            "dose_exposure_pkpd",
            "dose_selection_confidence",
            "human_proof_of_mechanism",
        },
        "B": {
            "B",
            "translation_bridge",
            "biomarker_translation",
            "biomarker_selection",
            "human_proof_of_mechanism",
            "endpoint_type",
        },
    }.get(component_key, {component_key})


def _has_unresolved(
    *,
    phase: str,
    components: dict[str, ScienceComponentScore],
    pos_fired_adjusters: set[str] | None = None,
) -> bool:
    """Strict late-stage unresolved-biology gate for T/D/B only."""
    if _norm_phase(phase) not in _POST_PHASE2_PHASES:
        return True

    tdb = _tdb_components(components)
    binding_key = _binding_tdb_key(components)
    binding = tdb[binding_key]
    threshold = float(AssumptionsLoader.get().science_guardrails["unresolved_threshold"])
    value_relevant = (
        binding.score < threshold
        or bool(binding.evidence_against)
        or binding.resolution in {EvidenceResolution.REFUTED, EvidenceResolution.UNRESOLVED}
    )
    if not value_relevant:
        return False

    fired = {item.lower() for item in (pos_fired_adjusters or set())}
    already_scored = bool(
        {item.lower() for item in _pos_factor_keys_for_component(binding_key)} & fired
    )
    return not already_scored


def _guardrail_effect(
    *,
    key: str,
    triggered: bool,
    config_key: str,
    caps: Mapping[str, object],
    severity: GuardrailSeverity,
    rationale: str,
) -> ScienceGuardrailEffect:
    cfg = caps.get(config_key, {})
    hard_cap = cfg.get("hard_cap") if isinstance(cfg, Mapping) else None
    soft_derate = cfg.get("soft_derate", 1.0) if isinstance(cfg, Mapping) else 1.0
    return ScienceGuardrailEffect(
        key=key,
        triggered=triggered,
        hard_cap=float(hard_cap) if hard_cap is not None else None,
        soft_derate=float(soft_derate),
        severity=severity,
        rationale=rationale,
    )


def _science_guardrail_from_legacy_flags(
    *,
    direct_negative_human_poc: bool,
    negative_human_poc_interpretability: NegativeHumanPOCInterpretability | None,
    no_feasible_exposure_at_active_dose: bool,
    target_pathway_refuted: bool,
) -> ScienceGuardrail:
    return ScienceGuardrail(
        target_refuted=target_pathway_refuted,
        infeasible_exposure=no_feasible_exposure_at_active_dose,
        negative_human_poc=direct_negative_human_poc,
        negative_human_poc_interpretability=negative_human_poc_interpretability,
    )


def apply_science_guardrail(
    modifier: float,
    guardrail: ScienceGuardrail,
    caps: Mapping[str, object] | None = None,
) -> tuple[float, list[ScienceGuardrailEffect], float, float, list[ScienceKillFlag], list[str]]:
    """Apply downside-only science guardrails using YAML caps/derates."""
    caps = caps or AssumptionsLoader.get().science_guardrails
    effects: list[ScienceGuardrailEffect] = []
    warnings: list[str] = []
    kill_flags: list[ScienceKillFlag] = []

    effect_specs = [
        (
            "target_refuted",
            guardrail.target_refuted,
            "target_refuted",
            GuardrailSeverity.CAP,
            "Target/pathway thesis is refuted.",
            ScienceKillFlag.TARGET_REFUTED,
        ),
        (
            "infeasible_exposure",
            guardrail.infeasible_exposure,
            "infeasible_exposure",
            GuardrailSeverity.CAP,
            "No feasible exposure at active dose.",
            ScienceKillFlag.INFEASIBLE_EXPOSURE,
        ),
        (
            "biomarker_bridge_refuted",
            guardrail.biomarker_bridge_refuted,
            "biomarker_bridge_refuted",
            GuardrailSeverity.CAP,
            "Translational bridge is refuted.",
            None,
        ),
        (
            "manageable_safety_concern",
            guardrail.manageable_safety_concern,
            "manageable_safety_concern",
            GuardrailSeverity.WARN,
            "Manageable safety concern is a mild downside derate.",
            None,
        ),
        (
            "unacceptable_safety",
            guardrail.unacceptable_safety,
            "unacceptable_safety",
            GuardrailSeverity.CAP,
            "Unacceptable safety profile caps the thesis.",
            ScienceKillFlag.UNACCEPTABLE_SAFETY,
        ),
        (
            "mechanism_linked_severe_safety",
            guardrail.mechanism_linked_severe_safety,
            "mechanism_linked_severe_safety",
            GuardrailSeverity.CAP,
            "Mechanism-linked severe safety risk sharply caps the thesis.",
            ScienceKillFlag.UNACCEPTABLE_SAFETY,
        ),
    ]
    for key, triggered, config_key, severity, rationale, kill_flag in effect_specs:
        effects.append(
            _guardrail_effect(
                key=key,
                triggered=triggered,
                config_key=config_key,
                caps=caps,
                severity=severity,
                rationale=rationale,
            )
        )
        if triggered and kill_flag is not None:
            kill_flags.append(kill_flag)
        if triggered and key == "target_refuted":
            warnings.append("target_pathway_refuted_program_kill")

    if guardrail.negative_human_poc:
        clear = (
            guardrail.negative_human_poc_interpretability
            == NegativeHumanPOCInterpretability.CLEAR
        )
        config_key = "negative_human_poc_clear" if clear else "negative_human_poc_ambiguous"
        effects.append(
            _guardrail_effect(
                key=config_key,
                triggered=True,
                config_key=config_key,
                caps=caps,
                severity=GuardrailSeverity.CAP if clear else GuardrailSeverity.WARN,
                rationale="Negative human PoC readout affects science confidence.",
            )
        )
        if clear:
            kill_flags.append(ScienceKillFlag.NEGATIVE_HUMAN_POC)
        else:
            warnings.append("ambiguous_negative_human_poc")

    triggered_effects = [effect for effect in effects if effect.triggered]
    hard_caps = [
        effect.hard_cap for effect in triggered_effects if effect.hard_cap is not None
    ]
    raw_soft_derate = (
        prod(effect.soft_derate for effect in triggered_effects)
        if triggered_effects
        else 1.0
    )
    soft_floor = float(caps.get("soft_derate_floor", 0.70))
    combined_soft_derate = max(soft_floor, raw_soft_derate) if triggered_effects else 1.0
    modifier_cap = min([1.1, *hard_caps]) if hard_caps else 1.1
    effective_modifier = min(modifier, modifier_cap) * combined_soft_derate
    return (
        round(effective_modifier, 4),
        triggered_effects,
        round(combined_soft_derate, 4),
        round(modifier_cap, 4),
        kill_flags,
        warnings,
    )


def _legacy_compute_science_modifier_phase1(
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
    pos_fired_adjusters: set[str] | None = None,
    science_guardrail: ScienceGuardrail | None = None,
) -> ScienceModifierResult:
    """Compute deterministic Phase 2 heuristic science modifier from T/D/B only."""
    tdb = _tdb_components(components)
    weights = _science_phase_weights(phase)
    weighted = sum(tdb[key].score * float(weights[key]) for key in ("T", "D", "B"))

    binding_source = BindingConstraintSource.COMPONENT_SCORE
    if binding_constraint_override is None:
        binding_key = _binding_component_key(binding_science_question)
        if binding_key not in {"T", "D", "B"}:
            binding_key = _binding_tdb_key(components)
        binding_constraint = tdb[binding_key].score
    else:
        binding_constraint = max(0.0, min(1.0, binding_constraint_override))
        binding_source = BindingConstraintSource.MANUAL_OVERRIDE

    science_score = min(weighted, binding_constraint + 0.15)
    heuristic_modifier = 0.70 + (0.40 * science_score)
    confidence_component = components.get("Q")
    science_score_confidence = (
        confidence_component.score
        if confidence_component is not None
        else _component_confidence(tdb.values())
    )

    if _norm_phase(phase) in _POST_PHASE2_PHASES and not _has_unresolved(
        phase=phase,
        components=components,
        pos_fired_adjusters=pos_fired_adjusters,
    ):
        heuristic_modifier = 1.0

    guardrail = science_guardrail or _science_guardrail_from_legacy_flags(
        direct_negative_human_poc=direct_negative_human_poc,
        negative_human_poc_interpretability=negative_human_poc_interpretability,
        no_feasible_exposure_at_active_dose=no_feasible_exposure_at_active_dose,
        target_pathway_refuted=target_pathway_refuted,
    )
    (
        heuristic_modifier,
        guardrail_effects,
        combined_soft_derate,
        modifier_cap,
        kill_flags,
        guardrail_warnings,
    ) = apply_science_guardrail(heuristic_modifier, guardrail)

    warnings = [*(additional_warnings or []), *guardrail_warnings]
    if binding_source == BindingConstraintSource.MANUAL_OVERRIDE:
        warnings.append("manual_binding_constraint_override")
    return ScienceModifierResult(
        science_score=round(science_score, 4),
        science_score_confidence=round(science_score_confidence, 4),
        heuristic_science_modifier=round(heuristic_modifier, 4),
        binding_constraint=round(binding_constraint, 4),
        binding_constraint_source=binding_source,
        modifier_cap=round(modifier_cap, 4),
        kill_flags=kill_flags,
        negative_human_poc_interpretability=negative_human_poc_interpretability,
        guardrail_effects=guardrail_effects,
        combined_soft_derate=combined_soft_derate,
        warnings=warnings,
        rationale=(
            f"tdb_weighted={weighted:.3f}; binding={binding_constraint:.3f}; "
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
    overlap_warnings = check_science_pos_overlap(thesis.components)
    additional_warnings = [
        *find_biomarker_overlap_warnings(evidence_items),
        *[
            f"science_pos_overlap_{warning.severity.value}:{warning.key}"
            for warning in overlap_warnings
        ],
    ]
    modifier = compute_science_modifier(
        phase=thesis.phase,
        binding_science_question=thesis.binding_science_question,
        components=thesis.components,
        direct_negative_human_poc=scoring_input.direct_negative_human_poc,
        negative_human_poc_interpretability=scoring_input.negative_human_poc_interpretability,
        no_feasible_exposure_at_active_dose=scoring_input.no_feasible_exposure_at_active_dose,
        target_pathway_refuted=scoring_input.target_pathway_refuted,
        binding_constraint_override=scoring_input.binding_constraint_override,
        additional_warnings=additional_warnings,
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
    human_poc_strength: float | None = None,
    clinical_meaningfulness: float | None = None,
    evidence_quality: float = 0.0,
    evidence_grade: EvidenceGrade = EvidenceGrade.SCREENING_PUBLIC,
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
    """Compute BD actionability after hard gates.

    Stage 2 ranks assets that already passed the Stage 1 hard gates. The fit
    score is split into human-POC strength and clinical meaningfulness (Chris
    anchored repeatedly on human proof-of-concept and *clinical* — not merely
    statistical — effect size), and ``evidence_quality`` is capped because the
    underlying claims are screening-grade public data. Stage 3 then caps the
    whole score for any asset whose evidence is still ``screening_public``.
    """
    failed = failed_gates or []
    # Backward-compat: callers that only pass science_thesis_fit get it mapped
    # onto both human-POC and clinical-meaningfulness terms.
    if human_poc_strength is None:
        human_poc_strength = science_thesis_fit
    if clinical_meaningfulness is None:
        clinical_meaningfulness = science_thesis_fit
    # Keep a representative science_thesis_fit for the memo / older readers.
    science_thesis_fit_out = (
        science_thesis_fit
        if science_thesis_fit > 0.0
        else round((human_poc_strength + clinical_meaningfulness) / 2, 4)
    )

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
            evidence_grade=evidence_grade,
            pre_diligence=evidence_grade != EvidenceGrade.DILIGENCE_CONFIRMED,
            warnings=warnings or [],
            diligence_questions=diligence_questions or [],
        )

    buyer_problem_fit_adjusted = min(1.0, buyer_problem_fit)
    # Idea 15: scarcity has ONE home — buyer_owner_advantage, set by the matcher's
    # _owner_advantage (and constrained there to sandbox scarcity). It is NOT
    # re-added here: the old "+ 0.05 * scarcity_value" term double-counted it and
    # let general "hotness" leak into value. time_sensitivity is routing-only and
    # never enters this score at all.
    buyer_owner_advantage_adjusted = min(
        1.0,
        buyer_owner_advantage
        + (0.05 * internal_portfolio_fit)
        + (0.05 * combination_or_lifecycle_fit),
    )
    deal_feasibility_adjusted = max(
        0.0,
        min(1.0, deal_feasibility - (0.05 * assessed_internal_overlap_risk)),
    )
    # Screening-grade evidence cannot dominate the fit score (Stage 2 cap).
    evidence_quality_capped = min(evidence_quality, EVIDENCE_QUALITY_TERM_CAP)
    score = (
        0.25 * buyer_problem_fit_adjusted
        + 0.20 * human_poc_strength
        + 0.15 * clinical_meaningfulness
        + 0.10 * evidence_quality_capped
        + 0.10 * modality_capability_fit
        + 0.10 * buyer_owner_advantage_adjusted
        + 0.10 * deal_feasibility_adjusted
    )

    # Stage 3 — public data is never conviction. Cap the score and flag it.
    pre_diligence = evidence_grade != EvidenceGrade.DILIGENCE_CONFIRMED
    final_warnings = list(warnings or [])
    if evidence_grade == EvidenceGrade.SCREENING_PUBLIC and score > SCREENING_PUBLIC_ACTIONABILITY_CAP:
        score = SCREENING_PUBLIC_ACTIONABILITY_CAP
        final_warnings.append("capped_screening_public_pre_diligence")

    # Idea 15 consistency guard: high scarcity is not credible when the buyer
    # already has alternatives that solve the same problem. Flag the contradiction
    # (the matcher separately caps the owner-advantage bump in this case).
    if scarcity_value >= 0.70 and (alternative_assets_available or []):
        final_warnings.append("scarcity_inconsistent_with_alternatives")

    confidence_values = confidence_inputs or [evidence_quality, diligence_readiness]
    confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0.5

    if score >= 0.70 and confidence < 0.50:
        final_warnings.append("low_confidence_high_score")

    return BDActionabilityResult(
        passed_hard_gates=True,
        failed_gates=[],
        buyer_problem_fit=round(buyer_problem_fit_adjusted, 4),
        science_thesis_fit=science_thesis_fit_out,
        human_poc_strength=round(human_poc_strength, 4),
        clinical_meaningfulness=round(clinical_meaningfulness, 4),
        evidence_quality=evidence_quality,
        evidence_grade=evidence_grade,
        pre_diligence=pre_diligence,
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


class ShortlistEntry(BaseModel):
    """One eligible asset on a buyer-problem shortlist (Stage 4 output)."""

    asset_id: str
    asset_name: str = ""
    bd_actionability: float = Field(ge=0.0, le=1.0)
    evidence_grade: EvidenceGrade = EvidenceGrade.SCREENING_PUBLIC
    pre_diligence: bool = True
    recommended_bd_route: BDRoute = BDRoute.MONITOR
    why_this_asset: str = ""
    # The one thing to diligence first, surfaced from the killer-question spine.
    decisive_killer_question: str = ""


class ExcludedEntry(BaseModel):
    """An asset that failed a Stage 1 hard gate, with the gate(s) it tripped.

    Idea 14 (gate audit trail): an excluded asset never receives a score, but the
    analyst should still see *which door it hit* (TA / target / modality /
    doesn't-solve-problem) so the "we wouldn't even look at it" logic is legible.
    The gate tokens are exactly those returned by ``evaluate_bd_hard_gates``.
    """

    asset_id: str
    asset_name: str = ""
    failed_gates: list[str] = Field(default_factory=list)


class BuyerProblemShortlist(BaseModel):
    """Stage 4 deliverable: a ranked shortlist of eligible assets for one buyer problem.

    Chris's actual deliverable is a ranked list (e.g. "every company with a T-cell
    engager targeting CD19 and BCMA"), not a per-asset verdict in isolation. Only
    assets that pass the Stage 1 hard gates appear in ``ranked``; assets that fail
    are listed in ``excluded`` as ``ExcludedEntry`` records (with their failed
    gates) and never receive a number.
    """

    buyer_problem_id: str
    ranked: list[ShortlistEntry] = Field(default_factory=list)
    excluded: list[ExcludedEntry] = Field(default_factory=list)


def build_buyer_problem_shortlist(
    buyer_problem_id: str,
    scored: Iterable[tuple[str, str, BDActionabilityResult]],
    *,
    limit: int | None = None,
) -> BuyerProblemShortlist:
    """Build a ranked shortlist from per-asset BD actionability results.

    ``scored`` is an iterable of ``(asset_id, asset_name, result)`` triples. The
    per-asset results are kept by the caller; this is a pure, side-effect-free
    join that ranks the eligible set and records the excluded asset ids.
    """
    eligible: list[ShortlistEntry] = []
    excluded: list[ExcludedEntry] = []
    for asset_id, asset_name, result in scored:
        if not result.passed_hard_gates:
            excluded.append(
                ExcludedEntry(
                    asset_id=asset_id,
                    asset_name=asset_name,
                    failed_gates=list(result.failed_gates),
                )
            )
            continue
        killer_set = getattr(result, "killer_question_set", None)
        decisive = list(getattr(killer_set, "decisive", []) or [])
        decisive_q = ""
        if decisive:
            decisive_q = (
                getattr(decisive[0], "diligence_question", "")
                or getattr(decisive[0], "question_text", "")
            )
        eligible.append(
            ShortlistEntry(
                asset_id=asset_id,
                asset_name=asset_name,
                bd_actionability=result.bd_actionability,
                evidence_grade=result.evidence_grade,
                pre_diligence=result.pre_diligence,
                recommended_bd_route=result.recommended_bd_route,
                why_this_asset=result.route_rationale,
                decisive_killer_question=decisive_q,
            )
        )
    eligible.sort(key=lambda entry: entry.bd_actionability, reverse=True)
    if limit is not None:
        eligible = eligible[:limit]
    return BuyerProblemShortlist(
        buyer_problem_id=buyer_problem_id,
        ranked=eligible,
        excluded=excluded,
    )
