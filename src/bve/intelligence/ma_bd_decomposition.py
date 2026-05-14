"""
Layer 1 — BD Decision Decomposition.

Replaces the three-model M&A scoring system with five diagnostic scores that
answer the five questions a senior BD team asks before recommending a deal.

Component weights:
  1A  asset_quality          30%
  1B  value_creation         20%
  1C  transaction_timing     20%
  1D  strategic_fit          25%
  1E  deal_feasibility        5%

Five institutional gates applied after composite calculation (caps, never boosts).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COMPONENT_WEIGHTS: dict[str, float] = {
    "asset_quality": 0.30,
    "value_creation": 0.20,
    "transaction_timing": 0.20,
    "strategic_fit": 0.25,
    "deal_feasibility": 0.05,
}
assert abs(sum(_COMPONENT_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

# Clinical evidence cap threshold for 1A
_CLINICAL_EVIDENCE_CAP_THRESHOLD = 0.35
_CLINICAL_EVIDENCE_ASSET_QUALITY_CAP = 0.55

# Valuation discount gate for 1B
_VALUE_CREATION_ASSET_QUALITY_MIN = 0.50

# Gate thresholds
_GATE1_ASSET_QUALITY_THRESHOLD = 0.35
_GATE1_COMPOSITE_CAP = 0.40

_GATE2_STRATEGIC_FIT_THRESHOLD = 0.45
_GATE2_COMPOSITE_CAP = 0.55

_GATE3_RNPV_GAP_THRESHOLD = 0.0
_GATE3_COMPOSITE_CAP = 0.60

_GATE4_SELLER_WILLINGNESS_THRESHOLD = 0.30
_GATE4_FINANCING_PRESSURE_THRESHOLD = 0.30
_GATE4_COMPOSITE_CAP = 0.55

_GATE5_ASSET_CONTROL_THRESHOLD = 0.40
_GATE5_COMPOSITE_CAP = 0.50


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RecommendedAction(str, Enum):
    PURSUE = "pursue"
    MONITOR = "monitor"
    PASS = "pass"
    CONDITIONAL = "conditional"


class RecommendedStructure(str, Enum):
    FULL_ACQUISITION = "full_acquisition"
    ASSET_ACQUISITION = "asset_acquisition"
    LICENSE_PARTNERSHIP = "license_partnership"
    OPTION_TO_ACQUIRE = "option_to_acquire"
    COLLABORATION = "collaboration"
    NOT_APPLICABLE = "not_applicable"


# ---------------------------------------------------------------------------
# 1A — Asset Quality Score inputs
# ---------------------------------------------------------------------------

class AssetQualityInputs(BaseModel):
    """Sub-scores for 1A: Is the asset worth owning?"""
    model_config = ConfigDict(frozen=True)

    # 0–1 scores for each sub-dimension
    clinical_evidence: float = Field(..., ge=0.0, le=1.0,
        description="Strength of clinical data (phase, endpoints, effect size)")
    differentiation: float = Field(..., ge=0.0, le=1.0,
        description="Degree of differentiation vs current standard of care")
    regulatory_path: float = Field(..., ge=0.0, le=1.0,
        description="Clarity and risk of regulatory pathway")
    ip_durability: float = Field(..., ge=0.0, le=1.0,
        description="IP estate strength and patent cliff timing")
    cmc_feasibility: float = Field(..., ge=0.0, le=1.0,
        description="CMC/manufacturing risk and scalability")
    commercial_meaningfulness: float = Field(..., ge=0.0, le=1.0,
        description="Market size and commercial opportunity magnitude")


# ---------------------------------------------------------------------------
# 1B — Value Creation Score inputs
# ---------------------------------------------------------------------------

class ValueCreationInputs(BaseModel):
    """Sub-scores for 1B: Can the acquirer create value after premium?"""
    model_config = ConfigDict(frozen=True)

    premium_adjusted_rnpv_gap: float = Field(..., ge=0.0, le=1.0,
        description="Acquirer rNPV minus (target price + control premium) / rNPV")
    synergy_upside: float = Field(..., ge=0.0, le=1.0,
        description="Revenue or cost synergies achievable post-close")
    downside_protection: float = Field(..., ge=0.0, le=1.0,
        description="Downside scenario protection (milestone structures, option rights)")
    cost_to_complete: float = Field(..., ge=0.0, le=1.0,
        description="Remaining development cost feasibility (low cost = high score)")
    capital_solution_value: float = Field(..., ge=0.0, le=1.0,
        description="Value of solving target's capital constraints via acquisition")

    # Raw gap for Gate 3 (can be negative); separate from the normalised 0-1 score
    premium_adjusted_rnpv_gap_raw: float = Field(default=0.0,
        description="Raw premium-adjusted rNPV gap in $ millions (negative = value-destructive)")


# ---------------------------------------------------------------------------
# 1C — Transaction Timing / Seller Willingness inputs
# ---------------------------------------------------------------------------

class TransactionTimingInputs(BaseModel):
    """Sub-scores for 1C: Is now the right time?"""
    model_config = ConfigDict(frozen=True)

    financing_pressure: float = Field(..., ge=0.0, le=1.0,
        description="Target's financing pressure (high = motivated seller)")
    seller_willingness: float = Field(..., ge=0.0, le=1.0,
        description="Estimated management / board willingness to transact")
    transaction_window_quality: float = Field(..., ge=0.0, le=1.0,
        description="Quality of the current M&A environment and deal window")
    external_deal_activity: float = Field(..., ge=0.0, le=1.0,
        description="Level of competitive M&A activity in the sector")
    catalyst_setup: float = Field(..., ge=0.0, le=1.0,
        description="Upcoming catalysts that could shift valuation or urgency")


# ---------------------------------------------------------------------------
# 1D — Strategic Fit / Right-to-Win inputs
# ---------------------------------------------------------------------------

class StrategicFitInputs(BaseModel):
    """Sub-scores for 1D: Is this the right buyer?"""
    model_config = ConfigDict(frozen=True)

    ta_fit: float = Field(..., ge=0.0, le=1.0,
        description="Therapeutic area alignment with acquirer portfolio")
    modality_fit: float = Field(..., ge=0.0, le=1.0,
        description="Modality (small molecule, biologic, gene therapy) alignment")
    pipeline_gap_urgency: float = Field(..., ge=0.0, le=1.0,
        description="Urgency of pipeline gap this asset fills")
    development_capability: float = Field(..., ge=0.0, le=1.0,
        description="Acquirer's development capability for this asset type")
    commercial_capability: float = Field(..., ge=0.0, le=1.0,
        description="Acquirer's commercial launch capability in the indication")
    cmc_capability: float = Field(..., ge=0.0, le=1.0,
        description="Acquirer's CMC/manufacturing capability for this modality")
    relationship_control: float = Field(..., ge=0.0, le=1.0,
        description="Existing relationship or information advantage with target")


# ---------------------------------------------------------------------------
# 1E — Deal Feasibility inputs
# ---------------------------------------------------------------------------

class DealFeasibilityInputs(BaseModel):
    """Sub-scores for 1E: Can this deal get done?"""
    model_config = ConfigDict(frozen=True)

    affordability: float = Field(..., ge=0.0, le=1.0,
        description="Deal affordability relative to acquirer capacity")
    antitrust_feasibility: float = Field(..., ge=0.0, le=1.0,
        description="Antitrust / regulatory approval likelihood")
    asset_control: float = Field(..., ge=0.0, le=1.0,
        description="Degree of clean title and absence of blocking rights")
    integration_feasibility: float = Field(..., ge=0.0, le=1.0,
        description="Operational integration feasibility post-close")
    bidder_competition_risk_adjusted: float = Field(..., ge=0.0, le=1.0,
        description="Risk of competitive bidding (low competition = high score)")


# ---------------------------------------------------------------------------
# Per-component result models
# ---------------------------------------------------------------------------

class ComponentScore(BaseModel):
    """Scored output for a single BD component."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    sub_scores: dict[str, float]
    cap_applied: bool = False
    cap_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Gate result
# ---------------------------------------------------------------------------

class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    gate_id: str
    triggered: bool
    cap_applied: float
    description: str


# ---------------------------------------------------------------------------
# BDMAOutput — the rich final output
# ---------------------------------------------------------------------------

class BDMAOutput(BaseModel):
    """Rich BD / M&A assessment output for a single acquirer–target pair."""
    model_config = ConfigDict(frozen=True)

    target_name: str
    best_acquirer_id: Optional[str]

    bd_ma_score: float = Field(..., ge=0.0, le=1.0)
    pre_gate_score: float = Field(..., ge=0.0, le=1.0,
        description="Raw composite before gates are applied")

    recommended_action: RecommendedAction
    recommended_structure: RecommendedStructure

    # Narrative lists
    primary_rationale: list[str]
    main_risks: list[str]
    kill_criteria: list[str]
    diligence_questions: list[str]

    # Gate metadata
    gate_codes_applied: list[str]

    # Per-component breakdown
    component_scores: dict[str, ComponentScore]


# ---------------------------------------------------------------------------
# Sub-score computation helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def compute_asset_quality(inputs: AssetQualityInputs) -> ComponentScore:
    """1A: weighted average; clinical_evidence < 0.35 caps score at 0.55."""
    weights = {
        "clinical_evidence":       0.25,
        "differentiation":         0.20,
        "regulatory_path":         0.15,
        "ip_durability":           0.15,
        "cmc_feasibility":         0.10,
        "commercial_meaningfulness": 0.15,
    }
    assert abs(sum(weights.values()) - 1.0) < 1e-9

    raw = sum(getattr(inputs, k) * w for k, w in weights.items())
    sub = {k: getattr(inputs, k) for k in weights}

    cap_applied = False
    cap_reason: Optional[str] = None
    if inputs.clinical_evidence < _CLINICAL_EVIDENCE_CAP_THRESHOLD:
        if raw > _CLINICAL_EVIDENCE_ASSET_QUALITY_CAP:
            raw = _CLINICAL_EVIDENCE_ASSET_QUALITY_CAP
            cap_applied = True
            cap_reason = (
                f"clinical_evidence={inputs.clinical_evidence:.2f} < "
                f"{_CLINICAL_EVIDENCE_CAP_THRESHOLD}: asset_quality capped at "
                f"{_CLINICAL_EVIDENCE_ASSET_QUALITY_CAP}"
            )

    return ComponentScore(
        score=_clamp(raw), sub_scores=sub,
        cap_applied=cap_applied, cap_reason=cap_reason,
    )


def compute_value_creation(
    inputs: ValueCreationInputs,
    asset_quality_score: float,
) -> ComponentScore:
    """1B: valuation discount only counts if asset_quality >= 0.50."""
    weights = {
        "premium_adjusted_rnpv_gap": 0.35,
        "synergy_upside":            0.20,
        "downside_protection":       0.15,
        "cost_to_complete":          0.15,
        "capital_solution_value":    0.15,
    }
    assert abs(sum(weights.values()) - 1.0) < 1e-9

    effective_gap = inputs.premium_adjusted_rnpv_gap
    cap_applied = False
    cap_reason: Optional[str] = None

    if asset_quality_score < _VALUE_CREATION_ASSET_QUALITY_MIN:
        # Valuation discount (gap > 0.50 = discounted) doesn't count for low-quality assets
        # Clamp to neutral 0.50 so it contributes nothing positive
        if effective_gap > 0.50:
            effective_gap = 0.50
            cap_applied = True
            cap_reason = (
                f"asset_quality={asset_quality_score:.2f} < "
                f"{_VALUE_CREATION_ASSET_QUALITY_MIN}: premium_adjusted_rnpv_gap "
                f"clamped to 0.50 (discount does not count for low-quality assets)"
            )

    raw = (
        effective_gap * weights["premium_adjusted_rnpv_gap"]
        + inputs.synergy_upside * weights["synergy_upside"]
        + inputs.downside_protection * weights["downside_protection"]
        + inputs.cost_to_complete * weights["cost_to_complete"]
        + inputs.capital_solution_value * weights["capital_solution_value"]
    )

    sub = {k: getattr(inputs, k) for k in weights}

    return ComponentScore(
        score=_clamp(raw), sub_scores=sub,
        cap_applied=cap_applied, cap_reason=cap_reason,
    )


def compute_transaction_timing(inputs: TransactionTimingInputs) -> ComponentScore:
    weights = {
        "financing_pressure":        0.25,
        "seller_willingness":        0.25,
        "transaction_window_quality": 0.20,
        "external_deal_activity":    0.15,
        "catalyst_setup":            0.15,
    }
    assert abs(sum(weights.values()) - 1.0) < 1e-9

    raw = sum(getattr(inputs, k) * w for k, w in weights.items())
    sub = {k: getattr(inputs, k) for k in weights}
    return ComponentScore(score=_clamp(raw), sub_scores=sub)


def compute_strategic_fit(inputs: StrategicFitInputs) -> ComponentScore:
    weights = {
        "ta_fit":               0.20,
        "modality_fit":         0.15,
        "pipeline_gap_urgency": 0.20,
        "development_capability": 0.15,
        "commercial_capability": 0.10,
        "cmc_capability":       0.10,
        "relationship_control": 0.10,
    }
    assert abs(sum(weights.values()) - 1.0) < 1e-9

    raw = sum(getattr(inputs, k) * w for k, w in weights.items())
    sub = {k: getattr(inputs, k) for k in weights}
    return ComponentScore(score=_clamp(raw), sub_scores=sub)


def compute_deal_feasibility(inputs: DealFeasibilityInputs) -> ComponentScore:
    weights = {
        "affordability":                   0.35,
        "antitrust_feasibility":           0.20,
        "asset_control":                   0.20,
        "integration_feasibility":         0.15,
        "bidder_competition_risk_adjusted": 0.10,
    }
    assert abs(sum(weights.values()) - 1.0) < 1e-9

    raw = sum(getattr(inputs, k) * w for k, w in weights.items())
    sub = {k: getattr(inputs, k) for k in weights}
    return ComponentScore(score=_clamp(raw), sub_scores=sub)


# ---------------------------------------------------------------------------
# Composite calculation
# ---------------------------------------------------------------------------

def _compute_raw_composite(scores: dict[str, ComponentScore]) -> float:
    total = sum(scores[k].score * _COMPONENT_WEIGHTS[k] for k in _COMPONENT_WEIGHTS)
    return _clamp(total)


# ---------------------------------------------------------------------------
# Gate application
# ---------------------------------------------------------------------------

def _apply_gates(
    composite: float,
    scores: dict[str, ComponentScore],
    vc_inputs: ValueCreationInputs,
    timing_inputs: TransactionTimingInputs,
    feasibility_inputs: DealFeasibilityInputs,
) -> tuple[float, list[GateResult]]:
    """Apply the 5 institutional gates. Gates cap, never boost."""
    gates: list[GateResult] = []

    # Gate 1: poor asset quality
    if scores["asset_quality"].score < _GATE1_ASSET_QUALITY_THRESHOLD:
        triggered = True
        composite = min(composite, _GATE1_COMPOSITE_CAP)
    else:
        triggered = False
    gates.append(GateResult(
        gate_id="G1",
        triggered=triggered,
        cap_applied=_GATE1_COMPOSITE_CAP,
        description=(
            f"asset_quality < {_GATE1_ASSET_QUALITY_THRESHOLD}: "
            f"composite capped at {_GATE1_COMPOSITE_CAP}"
        ),
    ))

    # Gate 2: weak strategic fit
    if scores["strategic_fit"].score < _GATE2_STRATEGIC_FIT_THRESHOLD:
        triggered = True
        composite = min(composite, _GATE2_COMPOSITE_CAP)
    else:
        triggered = False
    gates.append(GateResult(
        gate_id="G2",
        triggered=triggered,
        cap_applied=_GATE2_COMPOSITE_CAP,
        description=(
            f"strategic_fit < {_GATE2_STRATEGIC_FIT_THRESHOLD}: "
            f"composite capped at {_GATE2_COMPOSITE_CAP}"
        ),
    ))

    # Gate 3: value-destructive deal (negative raw rNPV gap)
    if vc_inputs.premium_adjusted_rnpv_gap_raw < _GATE3_RNPV_GAP_THRESHOLD:
        triggered = True
        composite = min(composite, _GATE3_COMPOSITE_CAP)
    else:
        triggered = False
    gates.append(GateResult(
        gate_id="G3",
        triggered=triggered,
        cap_applied=_GATE3_COMPOSITE_CAP,
        description=(
            f"premium_adjusted_rnpv_gap_raw < {_GATE3_RNPV_GAP_THRESHOLD}: "
            f"composite capped at {_GATE3_COMPOSITE_CAP}"
        ),
    ))

    # Gate 4: neither seller willing nor under financing pressure
    if (
        timing_inputs.seller_willingness < _GATE4_SELLER_WILLINGNESS_THRESHOLD
        and timing_inputs.financing_pressure < _GATE4_FINANCING_PRESSURE_THRESHOLD
    ):
        triggered = True
        composite = min(composite, _GATE4_COMPOSITE_CAP)
    else:
        triggered = False
    gates.append(GateResult(
        gate_id="G4",
        triggered=triggered,
        cap_applied=_GATE4_COMPOSITE_CAP,
        description=(
            f"seller_willingness < {_GATE4_SELLER_WILLINGNESS_THRESHOLD} AND "
            f"financing_pressure < {_GATE4_FINANCING_PRESSURE_THRESHOLD}: "
            f"composite capped at {_GATE4_COMPOSITE_CAP}"
        ),
    ))

    # Gate 5: asset control issues
    if feasibility_inputs.asset_control < _GATE5_ASSET_CONTROL_THRESHOLD:
        triggered = True
        composite = min(composite, _GATE5_COMPOSITE_CAP)
    else:
        triggered = False
    gates.append(GateResult(
        gate_id="G5",
        triggered=triggered,
        cap_applied=_GATE5_COMPOSITE_CAP,
        description=(
            f"asset_control < {_GATE5_ASSET_CONTROL_THRESHOLD}: "
            f"composite capped at {_GATE5_COMPOSITE_CAP}"
        ),
    ))

    return composite, gates


# ---------------------------------------------------------------------------
# Narrative generation
# ---------------------------------------------------------------------------

def _recommend_action(score: float, gates: list[GateResult]) -> RecommendedAction:
    triggered_gates = [g for g in gates if g.triggered]
    if len(triggered_gates) >= 2 or score < 0.35:
        return RecommendedAction.PASS
    if triggered_gates:
        return RecommendedAction.CONDITIONAL
    if score >= 0.65:
        return RecommendedAction.PURSUE
    if score >= 0.50:
        return RecommendedAction.MONITOR
    return RecommendedAction.PASS


def _recommend_structure(
    scores: dict[str, ComponentScore],
    vc_inputs: ValueCreationInputs,
) -> RecommendedStructure:
    aq = scores["asset_quality"].score
    sf = scores["strategic_fit"].score
    df = scores["deal_feasibility"].score

    if aq >= 0.70 and sf >= 0.70 and df >= 0.60 and vc_inputs.premium_adjusted_rnpv_gap_raw >= 0:
        return RecommendedStructure.FULL_ACQUISITION
    if aq >= 0.55 and sf >= 0.55:
        if vc_inputs.premium_adjusted_rnpv_gap_raw < 0:
            return RecommendedStructure.OPTION_TO_ACQUIRE
        return RecommendedStructure.ASSET_ACQUISITION
    if scores["transaction_timing"].score >= 0.50:
        return RecommendedStructure.LICENSE_PARTNERSHIP
    return RecommendedStructure.NOT_APPLICABLE


def _build_rationale(
    scores: dict[str, ComponentScore],
    gates: list[GateResult],
    vc_inputs: ValueCreationInputs,
) -> list[str]:
    lines: list[str] = []
    aq = scores["asset_quality"].score
    sf = scores["strategic_fit"].score
    tt = scores["transaction_timing"].score

    if aq >= 0.70:
        lines.append(f"Strong asset quality (score={aq:.2f}): differentiated asset with solid clinical evidence.")
    elif aq >= 0.50:
        lines.append(f"Moderate asset quality (score={aq:.2f}): asset is viable but with execution risk.")
    else:
        lines.append(f"Weak asset quality (score={aq:.2f}): insufficient clinical or commercial foundation.")

    if sf >= 0.65:
        lines.append(f"High strategic fit (score={sf:.2f}): strong TA/modality alignment and pipeline gap urgency.")
    elif sf >= 0.45:
        lines.append(f"Moderate strategic fit (score={sf:.2f}): reasonable alignment but not a must-have acquisition.")
    else:
        lines.append(f"Low strategic fit (score={sf:.2f}): limited TA or modality overlap.")

    if vc_inputs.premium_adjusted_rnpv_gap_raw > 0:
        lines.append(
            f"Value-accretive deal: raw rNPV gap = ${vc_inputs.premium_adjusted_rnpv_gap_raw:+.1f}M."
        )
    else:
        lines.append(
            f"Value-destructive at current pricing: raw rNPV gap = ${vc_inputs.premium_adjusted_rnpv_gap_raw:+.1f}M."
        )

    if tt >= 0.55:
        lines.append(f"Good transaction timing (score={tt:.2f}): seller motivated, window open.")
    else:
        lines.append(f"Timing challenges (score={tt:.2f}): low seller willingness or poor deal environment.")

    return lines


def _build_risks(
    scores: dict[str, ComponentScore],
    gates: list[GateResult],
    vc_inputs: ValueCreationInputs,
) -> list[str]:
    risks: list[str] = []

    aq = scores["asset_quality"].score
    sf = scores["strategic_fit"].score

    if aq < 0.50:
        risks.append("Clinical evidence insufficient to support a premium acquisition; further de-risking required.")
    if scores["asset_quality"].sub_scores.get("ip_durability", 1.0) < 0.40:
        risks.append("IP durability is weak — patent cliff could erode value before integration benefits accrue.")
    if vc_inputs.premium_adjusted_rnpv_gap_raw < 0:
        risks.append(
            f"Deal is value-destructive at current ask: rNPV gap = ${vc_inputs.premium_adjusted_rnpv_gap_raw:.1f}M."
        )
    if scores["deal_feasibility"].sub_scores.get("antitrust_feasibility", 1.0) < 0.50:
        risks.append("Antitrust risk is elevated; divestiture or remedies may be required to close.")
    if scores["deal_feasibility"].sub_scores.get("asset_control", 1.0) < 0.50:
        risks.append("Encumbered asset: ROFR, co-development rights, or royalty stacks may block clean acquisition.")
    if sf < 0.45:
        risks.append("Strategic fit is marginal; deal thesis may not survive post-merger integration scrutiny.")
    for g in gates:
        if g.triggered:
            risks.append(f"Institutional gate {g.gate_id} triggered: {g.description}")

    if not risks:
        risks.append("No material risk flags identified at current score levels.")
    return risks


def _build_kill_criteria(
    scores: dict[str, ComponentScore],
    gates: list[GateResult],
    vc_inputs: ValueCreationInputs,
) -> list[str]:
    criteria: list[str] = [
        "Phase 3 primary endpoint miss in lead indication.",
        "FDA complete response letter (CRL) citing safety or efficacy deficiencies.",
        f"Offer price implies rNPV gap below ${_GATE3_RNPV_GAP_THRESHOLD:.0f}M after due-diligence adjustments.",
        "Competing acquirer submits binding offer above walk-away price.",
        "Discovery of undisclosed material royalty obligations or ROFR rights.",
    ]
    if scores["asset_quality"].sub_scores.get("clinical_evidence", 1.0) < 0.50:
        criteria.append("Further clinical data confirms lack of differentiation vs. standard of care.")
    return criteria


def _build_diligence_questions(
    scores: dict[str, ComponentScore],
    vc_inputs: ValueCreationInputs,
    feasibility_inputs: DealFeasibilityInputs,
) -> list[str]:
    questions: list[str] = [
        "What is the complete IP landscape, including expiry dates and litigation history?",
        "Are there any undisclosed co-development agreements, ROFR clauses, or sublicensing rights?",
        "What is the projected cost-to-complete for each active clinical program?",
        "What are the key regulatory risks, including any prior FDA/EMA feedback or holds?",
        "What is the CMC readiness for commercial-scale manufacturing post-approval?",
    ]
    if scores["asset_quality"].sub_scores.get("clinical_evidence", 1.0) < 0.60:
        questions.append("Can the clinical data package be audited for completeness? What is the raw dataset?")
    if feasibility_inputs.antitrust_feasibility < 0.60:
        questions.append("What is external antitrust counsel's assessment of market concentration risk?")
    if vc_inputs.premium_adjusted_rnpv_gap_raw < 50:
        questions.append("What is management's view on price flexibility? Is an earn-out structure acceptable?")
    return questions


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_bd_mna_composite(
    target_name: str,
    asset_quality_inputs: AssetQualityInputs,
    value_creation_inputs: ValueCreationInputs,
    transaction_timing_inputs: TransactionTimingInputs,
    strategic_fit_inputs: StrategicFitInputs,
    deal_feasibility_inputs: DealFeasibilityInputs,
    acquirer_id: Optional[str] = None,
) -> BDMAOutput:
    """
    Compute the full Layer 1 BD / M&A composite score and generate
    the institutional-grade BDMAOutput.
    """
    # --- Step 1: compute sub-scores ---
    aq_score = compute_asset_quality(asset_quality_inputs)
    vc_score = compute_value_creation(value_creation_inputs, aq_score.score)
    tt_score = compute_transaction_timing(transaction_timing_inputs)
    sf_score = compute_strategic_fit(strategic_fit_inputs)
    df_score = compute_deal_feasibility(deal_feasibility_inputs)

    component_scores: dict[str, ComponentScore] = {
        "asset_quality":       aq_score,
        "value_creation":      vc_score,
        "transaction_timing":  tt_score,
        "strategic_fit":       sf_score,
        "deal_feasibility":    df_score,
    }

    # --- Step 2: raw composite ---
    raw_composite = _compute_raw_composite(component_scores)

    # --- Step 3: apply gates ---
    final_composite, gate_results = _apply_gates(
        raw_composite,
        component_scores,
        value_creation_inputs,
        transaction_timing_inputs,
        deal_feasibility_inputs,
    )

    # --- Step 4: action + structure ---
    action = _recommend_action(final_composite, gate_results)
    structure = _recommend_structure(component_scores, value_creation_inputs)

    # --- Step 5: narrative ---
    rationale = _build_rationale(component_scores, gate_results, value_creation_inputs)
    risks = _build_risks(component_scores, gate_results, value_creation_inputs)
    kill = _build_kill_criteria(component_scores, gate_results, value_creation_inputs)
    diligence = _build_diligence_questions(
        component_scores, value_creation_inputs, deal_feasibility_inputs
    )

    triggered_gate_codes = [g.gate_id for g in gate_results if g.triggered]

    return BDMAOutput(
        target_name=target_name,
        best_acquirer_id=acquirer_id,
        bd_ma_score=final_composite,
        pre_gate_score=raw_composite,
        recommended_action=action,
        recommended_structure=structure,
        primary_rationale=rationale,
        main_risks=risks,
        kill_criteria=kill,
        diligence_questions=diligence,
        gate_codes_applied=triggered_gate_codes,
        component_scores=component_scores,
    )
