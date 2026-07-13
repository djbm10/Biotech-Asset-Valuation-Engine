"""Phase E layered probability stack."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bve.models.financing_risk import FinancingRiskV2
    from bve.models.science_score import ScienceDiligenceResult
    from bve.intelligence.science_thesis import ScienceThesis

from bve.intelligence.science_engine import ScienceAssessment
from bve.models.approval_scenarios import (
    ApprovalScenarioWeight,
    ApprovalScenarioInputs,
    build_approval_scenarios,
)
from bve.models.label_breadth_model import (
    LabelBreadthInputs,
    LabelBreadthResult,
    infer_label_breadth,
)
from bve.models.regulatory_inference import RegulatoryInferenceResult
from bve.models.timeline_distribution_model import (
    TimelineDistributionInputs,
    TimelineDistributionResult,
    infer_timeline_distribution,
)


class ProbabilityStackInputs(BaseModel):
    asset_id: str
    asset_name: str
    base_pos: float = Field(ge=0.0, le=1.0)
    science_assessment: ScienceAssessment
    regulatory_inference: RegulatoryInferenceResult
    years_to_approval: float = Field(ge=0.0)
    financing_risk_score: float = Field(default=0.3, ge=0.0, le=1.0)
    market_access_pressure_score: float = Field(default=0.3, ge=0.0, le=1.0)
    management_execution_score: float = Field(default=0.6, ge=0.0, le=1.0)
    competitor_readthrough_score: float = Field(default=0.5, ge=0.0, le=1.0)


class ProbabilityLayer(BaseModel):
    name: str
    probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class ProbabilityStackResult(BaseModel):
    asset_id: str
    asset_name: str
    technical_success_probability: ProbabilityLayer
    regulatory_approval_probability: ProbabilityLayer
    label_breadth_probability: ProbabilityLayer
    commercial_realization_probability: ProbabilityLayer
    timeline_distribution: TimelineDistributionResult
    label_breadth_detail: LabelBreadthResult
    approval_scenarios: list[ApprovalScenarioWeight]
    composite_approval_probability: float = Field(ge=0.0, le=1.0)
    plain_english_summary: str


def build_probability_stack(inputs: ProbabilityStackInputs) -> ProbabilityStackResult:
    science = inputs.science_assessment
    science_conf = _confidence_from_band(science.confidence_band)

    technical = max(
        0.0,
        min(
            1.0,
            (inputs.base_pos * 0.35)
            + (science.science_score * 0.45)
            + (science.design_score * 0.20),
        ),
    )
    technical_layer = ProbabilityLayer(
        name="technical_success_probability",
        probability=round(technical, 4),
        confidence=round(science_conf, 4),
        rationale="Technical success blends base PoS with the Phase D science and design outputs.",
    )

    regulatory_prob = max(
        0.0,
        min(
            1.0,
            (inputs.regulatory_inference.approval_probability * 0.70)
            + (technical * 0.20)
            + (inputs.management_execution_score * 0.10),
        ),
    )
    regulatory_layer = ProbabilityLayer(
        name="regulatory_approval_probability",
        probability=round(regulatory_prob, 4),
        confidence=round(min(0.95, science_conf * 0.8 + 0.15), 4),
        rationale="Regulatory approval probability combines regulatory inference with technical quality and execution support.",
    )

    biomarker_score = _subscore_value(science, "biomarker_logic_quality")
    safety_score = _subscore_value(science, "safety_signal_seriousness")
    label_inputs = LabelBreadthInputs(
        design_score=science.design_score,
        biomarker_logic_score=biomarker_score,
        safety_score=safety_score,
        regulatory_approval_probability=regulatory_prob,
        endpoint_strength_score=min(1.0, science.design_score + 0.1),
    )
    label_detail = infer_label_breadth(label_inputs)
    label_layer = ProbabilityLayer(
        name="label_breadth_probability",
        probability=label_detail.broad_label_probability,
        confidence=round(min(0.9, science_conf * 0.75 + 0.2), 4),
        rationale=label_detail.rationale,
    )

    commercial = max(
        0.0,
        min(
            1.0,
            (label_detail.broad_label_probability * 0.35)
            + ((1.0 - inputs.market_access_pressure_score) * 0.25)
            + ((1.0 - inputs.financing_risk_score) * 0.15)
            + (inputs.management_execution_score * 0.15)
            + (inputs.competitor_readthrough_score * 0.10),
        ),
    )
    commercial_layer = ProbabilityLayer(
        name="commercial_realization_probability",
        probability=round(commercial, 4),
        confidence=round(min(0.9, science_conf * 0.7 + 0.15), 4),
        rationale="Commercial realization depends on label breadth, access pressure, financing, management, and competition.",
    )

    timeline = infer_timeline_distribution(
        TimelineDistributionInputs(
            years_to_approval=inputs.years_to_approval,
            regulatory_risk_score=regulatory_prob,
            design_score=science.design_score,
            financing_risk_score=inputs.financing_risk_score,
        )
    )

    scenarios = build_approval_scenarios(
        ApprovalScenarioInputs(
            technical_success_probability=technical,
            regulatory_approval_probability=regulatory_prob,
            broad_label_probability=label_detail.broad_label_probability,
            commercial_realization_probability=commercial,
            delay_probability=timeline.delay_probability,
        )
    )

    composite = round(technical * regulatory_prob * commercial, 4)
    summary = (
        f"{inputs.asset_name} has technical success {technical:.2f}, regulatory approval {regulatory_prob:.2f}, "
        f"broad-label probability {label_detail.broad_label_probability:.2f}, and commercial realization {commercial:.2f}. "
        f"The stack implies composite approval probability {composite:.2f}."
    )
    return ProbabilityStackResult(
        asset_id=inputs.asset_id,
        asset_name=inputs.asset_name,
        technical_success_probability=technical_layer,
        regulatory_approval_probability=regulatory_layer,
        label_breadth_probability=label_layer,
        commercial_realization_probability=commercial_layer,
        timeline_distribution=timeline,
        label_breadth_detail=label_detail,
        approval_scenarios=scenarios,
        composite_approval_probability=composite,
        plain_english_summary=summary,
    )


def _confidence_from_band(band: str) -> float:
    return {"high": 0.85, "medium": 0.68}.get(band, 0.5)


def _subscore_value(assessment: ScienceAssessment, name: str) -> float:
    for score in assessment.subscores:
        if score.name == name:
            return score.value
    return 0.5


# ---------------------------------------------------------------------------
# Step 7: Layered probability stack — new types added below existing Phase E types
# ---------------------------------------------------------------------------


class ApprovalScenarioV2(str, Enum):
    """Step 7 approval scenario enum (distinct from Phase E ApprovalScenario)."""

    FULL_APPROVAL = "full_approval"
    ACCELERATED_APPROVAL = "accelerated_approval"
    CONDITIONAL_APPROVAL = "conditional_approval"
    CRL_RESUBMISSION = "crl_resubmission"
    COMPLETE_FAILURE = "complete_failure"


PHASE_BASE_RATES: dict[str, dict[str, float]] = {
    "phase1": {
        "technical": 0.63,
        "regulatory": 0.85,
        "label_breadth": 0.70,
        "commercial": 0.60,
        "delay": 0.20,
        "crl": 0.10,
    },
    "phase2": {
        "technical": 0.40,
        "regulatory": 0.82,
        "label_breadth": 0.65,
        "commercial": 0.55,
        "delay": 0.25,
        "crl": 0.15,
    },
    "phase3": {
        "technical": 0.65,
        "regulatory": 0.85,
        "label_breadth": 0.70,
        "commercial": 0.65,
        "delay": 0.30,
        "crl": 0.20,
    },
    "nda_bla": {
        "technical": 0.90,
        "regulatory": 0.87,
        "label_breadth": 0.75,
        "commercial": 0.70,
        "delay": 0.35,
        "crl": 0.25,
    },
    "approved": {
        "technical": 1.00,
        "regulatory": 1.00,
        "label_breadth": 0.80,
        "commercial": 0.75,
        "delay": 0.05,
        "crl": 0.00,
    },
}


class ProbabilityLayerV2(BaseModel):
    """Step 7 probability layer — frozen, with key_drivers and modifiers_applied."""

    model_config = {"frozen": True}

    name: str
    probability: float
    confidence: float
    key_drivers: list[str]
    modifiers_applied: list[str]


class ProbabilityStack(BaseModel):
    """Step 7 full layered probability stack for a drug asset."""

    model_config = {"frozen": True}

    asset_id: str
    phase: str
    as_of_date: str
    technical_success_prob: ProbabilityLayerV2
    regulatory_approval_prob: ProbabilityLayerV2
    label_breadth_prob: ProbabilityLayerV2
    commercial_realization_prob: ProbabilityLayerV2
    composite_pos: float
    full_value_prob: float
    delay_prob: float
    crl_prob: float
    scenario_probs: dict[str, float]
    financing_modifier: float
    science_modifier: float
    rationale: str


def _clamp(v: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return max(lo, min(hi, v))


def compute_probability_stack(
    asset_id: str,
    phase: str,
    science_result: ScienceDiligenceResult | None = None,
    science_thesis: ScienceThesis | None = None,
    financing_risk: FinancingRiskV2 | None = None,
    has_breakthrough_designation: bool = False,
    has_fast_track: bool = False,
    has_orphan_designation: bool = False,
    prior_phase_success: bool | None = None,
    as_of_date: str = "",
) -> ProbabilityStack:
    """Compute a full layered ProbabilityStack from structured inputs."""
    # Import here to avoid circular imports at module load time
    from bve.models.financing_risk import DistressTier

    rates = dict(PHASE_BASE_RATES.get(phase, PHASE_BASE_RATES["phase2"]))

    technical = rates["technical"]
    regulatory = rates["regulatory"]
    label_breadth = rates["label_breadth"]
    commercial = rates["commercial"]
    delay = rates["delay"]
    crl = rates["crl"]

    # --- Science modifier ---
    science_modifier: float
    if science_thesis is not None and science_thesis.modifier_result is not None:
        science_modifier = science_thesis.modifier_result.heuristic_science_modifier
    elif science_result is not None:
        science_modifier = 0.70 + science_result.overall_score * 0.40
    else:
        science_modifier = 1.00

    # --- Financing modifier ---
    financing_modifier: float
    if financing_risk is not None:
        tier = financing_risk.distress_tier
        if tier in (DistressTier.NONE, DistressTier.LOW):
            financing_modifier = 1.00
        elif tier == DistressTier.MEDIUM:
            financing_modifier = 0.95
        elif tier == DistressTier.HIGH:
            financing_modifier = 0.85
        else:  # CRITICAL
            financing_modifier = 0.70
    else:
        financing_modifier = 1.00

    # --- Regulatory designation adjustments ---
    tech_modifiers: list[str] = []
    reg_modifiers: list[str] = []
    label_modifiers: list[str] = []

    if has_breakthrough_designation:
        technical += 0.05
        regulatory += 0.05
        delay = max(0.0, delay - 0.10)
        tech_modifiers.append("breakthrough_designation +0.05")
        reg_modifiers.append("breakthrough_designation +0.05")

    if has_fast_track:
        regulatory += 0.03
        delay = max(0.0, delay - 0.05)
        reg_modifiers.append("fast_track +0.03")

    if has_orphan_designation:
        regulatory += 0.04
        label_breadth += 0.05
        reg_modifiers.append("orphan_designation +0.04")
        label_modifiers.append("orphan_designation +0.05")

    if prior_phase_success is True:
        technical += 0.05
        tech_modifiers.append("prior_phase_success +0.05")
    elif prior_phase_success is False:
        technical -= 0.10
        tech_modifiers.append("prior_phase_success -0.10")

    # --- Apply effective science modifier to technical ---
    # For ScienceThesis inputs this is already post-guardrail:
    # min(raw_modifier, *hard_caps) * combined_soft_derate.
    technical = technical * science_modifier
    if science_result is not None or science_thesis is not None:
        tech_modifiers.append(f"science_modifier {science_modifier:.3f}")

    # --- Apply financing modifier to commercial ---
    commercial = commercial * financing_modifier
    if financing_risk is not None:
        label_modifiers.append(f"financing_modifier {financing_modifier:.3f}")

    # --- Clamp all ---
    technical = _clamp(technical)
    regulatory = _clamp(regulatory)
    label_breadth = _clamp(label_breadth)
    commercial = _clamp(commercial)
    delay = _clamp(delay)
    crl = _clamp(crl)

    # --- Composite ---
    composite_pos = technical * regulatory
    full_value_prob = composite_pos * label_breadth * commercial

    # --- Scenario probabilities ---
    accel_prob = composite_pos * (0.15 if (has_breakthrough_designation or has_orphan_designation) else 0.05)
    conditional_prob = composite_pos * 0.08
    crl_scenario_prob = composite_pos * crl
    failure_prob = 1.0 - composite_pos
    full_approval_prob = composite_pos * max(0.0, (1.0 - delay - crl)) * label_breadth

    raw_scenarios = {
        ApprovalScenarioV2.FULL_APPROVAL.value: full_approval_prob,
        ApprovalScenarioV2.ACCELERATED_APPROVAL.value: accel_prob,
        ApprovalScenarioV2.CONDITIONAL_APPROVAL.value: conditional_prob,
        ApprovalScenarioV2.CRL_RESUBMISSION.value: crl_scenario_prob,
        ApprovalScenarioV2.COMPLETE_FAILURE.value: failure_prob,
    }
    total = sum(raw_scenarios.values()) or 1.0
    scenario_probs = {k: max(0.0, v / total) for k, v in raw_scenarios.items()}

    # --- Rationale ---
    drivers: list[str] = [f"phase={phase}"]
    if has_breakthrough_designation:
        drivers.append("breakthrough designation")
    if has_fast_track:
        drivers.append("fast track")
    if has_orphan_designation:
        drivers.append("orphan designation")
    if science_result is not None:
        drivers.append(f"science_score={science_result.overall_score:.2f}")
    if science_thesis is not None and science_thesis.modifier_result is not None:
        drivers.append(f"science_thesis_score={science_thesis.modifier_result.science_score:.2f}")
    if financing_risk is not None:
        drivers.append(f"financing_tier={financing_risk.distress_tier.value}")
    rationale = (
        f"Probability stack for {asset_id} at {phase}: "
        f"composite_pos={composite_pos:.3f}, "
        f"full_value_prob={full_value_prob:.3f}. "
        f"Key drivers: {', '.join(drivers)}."
    )

    technical_layer = ProbabilityLayerV2(
        name="technical_success",
        probability=technical,
        confidence=0.75 if science_result is None else min(0.95, science_result.confidence + 0.15),
        key_drivers=[f"base_rate={rates['technical']:.2f}", f"phase={phase}"],
        modifiers_applied=tech_modifiers,
    )
    regulatory_layer = ProbabilityLayerV2(
        name="regulatory_approval",
        probability=regulatory,
        confidence=0.70,
        key_drivers=[f"base_rate={rates['regulatory']:.2f}", f"phase={phase}"],
        modifiers_applied=reg_modifiers,
    )
    label_layer = ProbabilityLayerV2(
        name="label_breadth",
        probability=label_breadth,
        confidence=0.65,
        key_drivers=[f"base_rate={rates['label_breadth']:.2f}", f"phase={phase}"],
        modifiers_applied=label_modifiers,
    )
    commercial_layer = ProbabilityLayerV2(
        name="commercial_realization",
        probability=commercial,
        confidence=0.60,
        key_drivers=[f"base_rate={rates['commercial']:.2f}", f"phase={phase}"],
        modifiers_applied=[f"financing_modifier={financing_modifier:.3f}"],
    )

    return ProbabilityStack(
        asset_id=asset_id,
        phase=phase,
        as_of_date=as_of_date,
        technical_success_prob=technical_layer,
        regulatory_approval_prob=regulatory_layer,
        label_breadth_prob=label_layer,
        commercial_realization_prob=commercial_layer,
        composite_pos=composite_pos,
        full_value_prob=full_value_prob,
        delay_prob=delay,
        crl_prob=crl,
        scenario_probs=scenario_probs,
        financing_modifier=financing_modifier,
        science_modifier=science_modifier,
        rationale=rationale,
    )
