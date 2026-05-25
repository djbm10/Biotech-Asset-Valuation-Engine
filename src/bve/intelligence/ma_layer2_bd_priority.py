"""
Layer 2 — BD Prioritization Engine (Institutional-Grade).

Answers the single question:
    "Given a target that passed Layer 0 and has a Layer 1 attractiveness score,
    should BD prioritize this target now, monitor it, map acquirers, wait for
    a catalyst, or pass?"

Formula:
    BD_Action_Score = 0.40 × Strategic_Priority
                    + 0.30 × Deal_Momentum
                    + 0.20 × Acquirer_Pull
                    + 0.10 × Information_Readiness

    capped_bd_action_score      = min(raw, all triggered cap values)
    confidence_adjusted_score   = capped_bd_action_score × confidence_multiplier

Layer 2 deliberately does NOT answer:
    • Is the company eligible?                  → Layer 0
    • Is the asset fundamentally attractive?    → Layer 1
    • Can a specific buyer afford it?           → Layer 3
    • Can a specific buyer integrate it?        → Layer 3
    • Is there pair-specific antitrust/ROFR?    → Layer 3
    • What exact deal structure?                → Layer 4
    • Calibrated probability of acquisition?    → Layer 5

Anti-double-counting: pair-specific affordability, antitrust, ROFR, integration,
and manufacturing-fit inputs are accepted as pass-through fields only.  They are
recorded in layer_ownership_warnings and do NOT affect any score.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Layer1Output is optional; deferred import guards against circular deps at runtime.
try:
    from bve.intelligence.ma_layer1_attractiveness import Layer1Output  # type: ignore
except ImportError:
    Layer1Output = None  # type: ignore


# ---------------------------------------------------------------------------
# Layer ownership map
# ---------------------------------------------------------------------------

LAYER2_OWNERSHIP_MAP: dict[str, str] = {
    "bd_action_priority": "Layer 2",
    "deal_momentum_analysis": "Layer 2",
    "acquirer_pull_diagnostics": "Layer 2",
    "information_readiness_assessment": "Layer 2",
    "target_strategic_attractiveness": "Layer 1",
    "acquirer_specific_affordability": "Layer 3",
    "acquirer_specific_integration": "Layer 3",
    "pair_specific_rofr": "Layer 3",
    "pair_specific_antitrust": "Layer 3",
    "pair_specific_manufacturing": "Layer 3",
    "deal_structure_routing": "Layer 4",
    "calibrated_takeout_probability": "Layer 5",
}

# Inputs that belong in Layer 3; Layer 2 ignores them for scoring
LAYER3_ONLY_INPUTS: frozenset[str] = frozenset({
    "affordability_override",
    "antitrust_risk",
    "rofr_impact",
    "integration_feasibility",
})


# ---------------------------------------------------------------------------
# Weight constants — all assert sum == 1.0
# ---------------------------------------------------------------------------

L2_WEIGHTS: dict[str, float] = {
    "strategic_priority": 0.40,
    "deal_momentum": 0.30,
    "acquirer_pull": 0.20,
    "information_readiness": 0.10,
}
assert abs(sum(L2_WEIGHTS.values()) - 1.0) < 1e-9, "L2_WEIGHTS must sum to 1.0"

_SP_WEIGHTS: dict[str, float] = {
    "layer1_attractiveness": 0.35,
    "acquirer_strategic_fit": 0.25,
    "strategic_scarcity": 0.20,
    "pipeline_gap_urgency": 0.10,
    "strategic_option_value": 0.10,
}
assert abs(sum(_SP_WEIGHTS.values()) - 1.0) < 1e-9

_TSP_WEIGHTS: dict[str, float] = {
    "financing_pressure": 0.30,
    "seller_openness": 0.20,
    "catalyst_timing": 0.20,
    "valuation_distress": 0.15,
    "governance_activist_pressure": 0.15,
}
assert abs(sum(_TSP_WEIGHTS.values()) - 1.0) < 1e-9

_BSU_WEIGHTS: dict[str, float] = {
    "pipeline_gap_urgency": 0.30,
    "loe_revenue_cliff_urgency": 0.25,
    "competitive_fomo": 0.20,
    "recent_bd_pattern": 0.15,
    "strategic_priority_recency": 0.10,
}
assert abs(sum(_BSU_WEIGHTS.values()) - 1.0) < 1e-9

_DM_TARGET_SIDE_WEIGHT: float = 0.55
_DM_BUYER_SIDE_WEIGHT: float = 0.45

_AP_WEIGHTS: dict[str, float] = {
    "ta_fit": 0.25,
    "modality_fit": 0.20,
    "pipeline_gap_urgency": 0.20,
    "buyer_deal_appetite": 0.15,
    "existing_relationship": 0.10,
    "competitive_fomo": 0.10,
}
assert abs(sum(_AP_WEIGHTS.values()) - 1.0) < 1e-9

_IR_WEIGHTS: dict[str, float] = {
    "layer1_confidence": 0.25,
    "acquirer_profile_freshness": 0.20,
    "transaction_driver_source_quality": 0.20,
    "valuation_data_freshness": 0.15,
    "rights_encumbrance_clarity": 0.10,
    "catalyst_date_confidence": 0.10,
}
assert abs(sum(_IR_WEIGHTS.values()) - 1.0) < 1e-9

# Confidence constants
_NEUTRAL: float = 0.50
_BASE_CONFIDENCE: float = 0.70
_MISSING_CONF_HIT: float = 0.10
_MIN_CONFIDENCE: float = 0.20

# Transaction driver weights (raw; used for weighted_driver_strength normalisation)
DRIVER_WEIGHTS: dict[str, float] = {
    "financing_pressure": 1.25,
    "major_catalyst": 1.25,
    "seller_openness": 1.20,
    "external_deal_wave": 1.00,
    "valuation_distress": 0.90,
    "activist_or_governance_pressure": 0.90,
    "scarcity_plus_fit": 0.80,
    "existing_partnership": 0.70,
    "buyer_pipeline_gap": 1.20,
    "loe_or_revenue_cliff": 1.10,
    "competitive_fomo": 0.90,
    "recent_bd_pattern": 0.80,
}
_TOTAL_DRIVER_WEIGHT: float = sum(DRIVER_WEIGHTS.values())

# Activation thresholds — driver fires when its strength >= this value
_DRIVER_ACTIVATION: dict[str, float] = {
    "financing_pressure": 0.50,
    "major_catalyst": 0.50,
    "seller_openness": 0.50,
    "external_deal_wave": 0.45,
    "valuation_distress": 0.50,
    "activist_or_governance_pressure": 0.45,
    "scarcity_plus_fit": 0.55,
    "existing_partnership": 0.50,
    "buyer_pipeline_gap": 0.50,
    "loe_or_revenue_cliff": 0.50,
    "competitive_fomo": 0.45,
    "recent_bd_pattern": 0.40,
}

# Acquirer pull depth thresholds
_AP_HIGH_THRESHOLD: float = 0.65   # buyer_universe_depth counts above this
_AP_MED_THRESHOLD: float = 0.55    # acquirer_pull_depth counts above this


# ---------------------------------------------------------------------------
# Shared utility models
# ---------------------------------------------------------------------------

class L2ScoreComponent(BaseModel):
    """Score + diagnostics for one Layer 2 sub-dimension."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    freshness_days: Optional[int] = None


class TransactionDriver(BaseModel):
    """A named transaction urgency signal with weight + strength diagnostics."""
    model_config = ConfigDict(frozen=True)

    name: str
    category: str  # target_side | buyer_side | market_side | governance_side
    is_active: bool
    strength: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    weight: float
    weighted_contribution: float  # is_active × strength × confidence × weight
    source_refs: list[str] = Field(default_factory=list)
    freshness_days: Optional[int] = None
    rationale: str = ""
    direction: str = "positive"  # positive | negative | neutral


class AcquirerPullResult(BaseModel):
    """Per-acquirer strategic pull diagnostics."""
    model_config = ConfigDict(frozen=True)

    acquirer_id: str
    acquirer_name: str
    acquirer_pull_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    ta_fit: float = Field(..., ge=0.0, le=1.0)
    modality_fit: float = Field(..., ge=0.0, le=1.0)
    pipeline_gap_urgency: float = Field(..., ge=0.0, le=1.0)
    buyer_deal_appetite: float = Field(..., ge=0.0, le=1.0)
    existing_relationship: float = Field(..., ge=0.0, le=1.0)
    competitive_fomo: float = Field(..., ge=0.0, le=1.0)
    source_refs: list[str] = Field(default_factory=list)
    profile_freshness_days: Optional[int] = None
    rationale: str = ""


# ---------------------------------------------------------------------------
# Output sub-group models
# ---------------------------------------------------------------------------

class Layer2StrategicPriority(BaseModel):
    model_config = ConfigDict(frozen=True)

    layer1_attractiveness: L2ScoreComponent
    acquirer_strategic_fit: L2ScoreComponent
    strategic_scarcity: L2ScoreComponent
    pipeline_gap_urgency: L2ScoreComponent
    strategic_option_value: L2ScoreComponent
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    caps: list[str] = Field(default_factory=list)
    rationale: str = ""
    # Block 1: pair-level urgency stored for downstream transparency
    strategic_urgency_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Pair-level strategic timing pressure applied as a blend modifier.",
    )


class Layer2DealMomentum(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_side_pressure: L2ScoreComponent
    buyer_side_urgency: L2ScoreComponent
    weighted_driver_strength: float = Field(..., ge=0.0, le=1.0)
    active_drivers: list[TransactionDriver] = Field(default_factory=list)
    inactive_drivers: list[TransactionDriver] = Field(default_factory=list)
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    caps: list[str] = Field(default_factory=list)
    rationale: str = ""


class Layer2AcquirerPull(BaseModel):
    model_config = ConfigDict(frozen=True)

    top_acquirer_pull: L2ScoreComponent
    acquirer_pull_depth: int = Field(..., ge=0)
    buyer_universe_depth: int = Field(..., ge=0)
    buyer_concentration_risk: float = Field(..., ge=0.0, le=1.0)
    top_acquirers: list[AcquirerPullResult] = Field(default_factory=list)
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""


class Layer2InformationReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)

    layer1_confidence: L2ScoreComponent
    acquirer_profile_freshness: L2ScoreComponent
    transaction_driver_source_quality: L2ScoreComponent
    valuation_data_freshness: L2ScoreComponent
    rights_encumbrance_clarity: L2ScoreComponent
    catalyst_date_confidence: L2ScoreComponent
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    readiness_label: str = ""
    missing_items: list[str] = Field(default_factory=list)
    rationale: str = ""


class Layer2BDOutput(BaseModel):
    """Full institutional-grade BD prioritization output for a single target."""
    model_config = ConfigDict(frozen=True)

    # Sub-group results
    strategic_priority: Layer2StrategicPriority
    deal_momentum: Layer2DealMomentum
    acquirer_pull: Layer2AcquirerPull
    information_readiness: Layer2InformationReadiness

    # Composite scores
    bd_action_score: float = Field(..., ge=0.0, le=1.0)
    capped_bd_action_score: float = Field(..., ge=0.0, le=1.0)
    confidence_adjusted_score: float = Field(..., ge=0.0, le=1.0)
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_multiplier: float = Field(..., ge=0.0, le=1.0)

    # Action decision
    action_classification: str
    expected_action_window: str

    # Convenience flattened diagnostics
    active_transaction_drivers: list[TransactionDriver] = Field(default_factory=list)
    weighted_driver_strength: float = Field(..., ge=0.0, le=1.0)
    target_side_pressure: float = Field(..., ge=0.0, le=1.0)
    buyer_side_urgency: float = Field(..., ge=0.0, le=1.0)
    buyer_universe_depth: int = Field(..., ge=0)
    buyer_concentration_risk: float = Field(..., ge=0.0, le=1.0)

    # Steering triggers
    upgrade_triggers: list[str] = Field(default_factory=list)
    downgrade_triggers: list[str] = Field(default_factory=list)

    # Data quality + compliance
    missing_data: list[str] = Field(default_factory=list)
    rationale: str = ""
    layer_ownership_warnings: list[str] = Field(default_factory=list)
    active_caps: list[str] = Field(default_factory=list)
    backward_compatibility: Optional[dict] = None


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class AcquirerPullInputRow(BaseModel):
    """Inputs for a single acquirer's strategic pull calculation."""
    model_config = ConfigDict(frozen=True)

    acquirer_id: str
    acquirer_name: str
    ta_fit: Optional[float] = Field(None, ge=0.0, le=1.0)
    modality_fit: Optional[float] = Field(None, ge=0.0, le=1.0)
    pipeline_gap_urgency: Optional[float] = Field(None, ge=0.0, le=1.0)
    buyer_deal_appetite: Optional[float] = Field(None, ge=0.0, le=1.0)
    existing_relationship: Optional[float] = Field(None, ge=0.0, le=1.0)
    competitive_fomo: Optional[float] = Field(None, ge=0.0, le=1.0)
    profile_freshness_days: Optional[int] = None
    source_refs: list[str] = Field(default_factory=list)


class Layer2StrategicPriorityInputs(BaseModel):
    """Inputs for Strategic Priority (40% of BD Action Score).

    When layer1_output is provided to Layer2Inputs, these fields are
    auto-populated from the Layer 1 engine result if not specified explicitly.

    strategic_urgency_score is PAIR-level timing pressure (this buyer + this target,
    e.g. patent cliff alignment, competitor acquisition pressure on this target).
    It is distinct from pipeline_gap_urgency which is buyer-level (generic gap).
    """
    model_config = ConfigDict(frozen=True)

    layer1_attractiveness_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    layer1_strategic_scarcity_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    layer1_asset_quality_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    acquirer_strategic_fit: Optional[float] = Field(None, ge=0.0, le=1.0)
    pipeline_gap_urgency: Optional[float] = Field(None, ge=0.0, le=1.0)
    strategic_option_value: Optional[float] = Field(None, ge=0.0, le=1.0)
    # Block 1: pair-level timing pressure — separate from buyer-level pipeline_gap_urgency
    strategic_urgency_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description=(
            "Pair-level strategic timing pressure: how urgent is THIS buyer + THIS target "
            "combination right now (e.g. patent cliff alignment, first-mover window)? "
            "Must not duplicate pipeline_gap_urgency which is buyer-level."
        ),
    )


class Layer2TargetSidePressureInputs(BaseModel):
    """Inputs for target-side deal pressure (part of Deal Momentum)."""
    model_config = ConfigDict(frozen=True)

    financing_pressure: Optional[float] = Field(None, ge=0.0, le=1.0)
    seller_openness: Optional[float] = Field(None, ge=0.0, le=1.0)
    catalyst_timing: Optional[float] = Field(None, ge=0.0, le=1.0)
    valuation_distress: Optional[float] = Field(None, ge=0.0, le=1.0)
    governance_activist_pressure: Optional[float] = Field(None, ge=0.0, le=1.0)


class Layer2BuyerSideUrgencyInputs(BaseModel):
    """Inputs for buyer-side urgency (part of Deal Momentum)."""
    model_config = ConfigDict(frozen=True)

    pipeline_gap_urgency: Optional[float] = Field(None, ge=0.0, le=1.0)
    loe_revenue_cliff_urgency: Optional[float] = Field(None, ge=0.0, le=1.0)
    competitive_fomo: Optional[float] = Field(None, ge=0.0, le=1.0)
    recent_bd_pattern: Optional[float] = Field(None, ge=0.0, le=1.0)
    strategic_priority_recency: Optional[float] = Field(None, ge=0.0, le=1.0)


class Layer2InformationReadinessInputs(BaseModel):
    """Inputs for information readiness (10% of BD Action Score)."""
    model_config = ConfigDict(frozen=True)

    layer1_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    acquirer_profile_freshness: Optional[float] = Field(None, ge=0.0, le=1.0)
    transaction_driver_source_quality: Optional[float] = Field(None, ge=0.0, le=1.0)
    valuation_data_freshness: Optional[float] = Field(None, ge=0.0, le=1.0)
    rights_encumbrance_clarity: Optional[float] = Field(None, ge=0.0, le=1.0)
    catalyst_date_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    known_missing_items: list[str] = Field(default_factory=list)


class PreliminaryTransactionFrictionInputs(BaseModel):
    """
    Simple pre-pair friction signals — Block 1F.

    These are OBVIOUS barriers observable before a full pair-level analysis:
      • obvious_seller_unwillingness: public statements / actions signalling no-deal
      • obvious_price_mismatch: publicly stated price expectations vs market
      • obvious_rights_issue: known in-licensed IP or ROFR that blocks outright sale
      • obvious_process_signal: ongoing strategic review, conflicting process
      • obvious_data_gap: core diligence data provably unavailable (e.g. in FDA review)

    NOT the full TransactionRealismScore (Layer 3 / Block 2):
      - No pair-specific affordability
      - No integration modelling
      - No circular dependency on Layer 2 scores

    UNKNOWN inputs (None) → treated as 0.0 (no friction assumed).
    """
    model_config = ConfigDict(frozen=True)

    obvious_seller_unwillingness: Optional[float] = Field(None, ge=0.0, le=1.0)
    obvious_price_mismatch: Optional[float] = Field(None, ge=0.0, le=1.0)
    obvious_rights_issue: Optional[float] = Field(None, ge=0.0, le=1.0)
    obvious_process_signal: Optional[float] = Field(None, ge=0.0, le=1.0)
    obvious_data_gap: Optional[float] = Field(None, ge=0.0, le=1.0)


class PreliminaryTransactionFrictionResult(BaseModel):
    """Output of compute_preliminary_friction."""
    model_config = ConfigDict(frozen=True)

    friction_score: float = Field(..., ge=0.0, le=1.0)
    friction_label: str  # CLEAN | MILD_FRICTION | HIGH_FRICTION | BLOCK
    active_friction_signals: list[str] = Field(default_factory=list)


# Friction label thresholds
_FRICTION_BLOCK_THRESHOLD: float = 0.80
_FRICTION_HIGH_THRESHOLD: float = 0.55
_FRICTION_MILD_THRESHOLD: float = 0.20

# Friction signal weights (must sum to 1.0)
_FRICTION_WEIGHTS: dict[str, float] = {
    "obvious_seller_unwillingness": 0.30,
    "obvious_price_mismatch": 0.25,
    "obvious_rights_issue": 0.20,
    "obvious_process_signal": 0.15,
    "obvious_data_gap": 0.10,
}
assert abs(sum(_FRICTION_WEIGHTS.values()) - 1.0) < 1e-9


def compute_preliminary_friction(
    inputs: PreliminaryTransactionFrictionInputs,
) -> PreliminaryTransactionFrictionResult:
    """
    Compute pre-pair transaction friction from 5 simple observable signals.

    UNKNOWN (None) → no friction assumed (benefit of doubt).
    Does NOT depend on any Layer 2 sub-scores (no circularity).
    """
    active_signals: list[str] = []
    score = 0.0

    field_map = {
        "obvious_seller_unwillingness": inputs.obvious_seller_unwillingness,
        "obvious_price_mismatch": inputs.obvious_price_mismatch,
        "obvious_rights_issue": inputs.obvious_rights_issue,
        "obvious_process_signal": inputs.obvious_process_signal,
        "obvious_data_gap": inputs.obvious_data_gap,
    }
    for field, value in field_map.items():
        if value is None:
            continue  # UNKNOWN → 0.0 benefit of doubt
        val = max(0.0, min(1.0, float(value)))
        score += _FRICTION_WEIGHTS[field] * val
        if val > 0.30:
            active_signals.append(field)

    score = max(0.0, min(1.0, score))

    if score >= _FRICTION_BLOCK_THRESHOLD:
        label = "BLOCK"
    elif score >= _FRICTION_HIGH_THRESHOLD:
        label = "HIGH_FRICTION"
    elif score >= _FRICTION_MILD_THRESHOLD:
        label = "MILD_FRICTION"
    else:
        label = "CLEAN"

    return PreliminaryTransactionFrictionResult(
        friction_score=round(score, 6),
        friction_label=label,
        active_friction_signals=active_signals,
    )


class Layer2Inputs(BaseModel):
    """Top-level Layer 2 inputs for a single BD target.

    Pass layer1_output to auto-populate strategic priority fields from
    the Layer 1 engine result.  All sub-group inputs can be specified
    directly to override or supplement.
    """
    model_config = ConfigDict(frozen=True)

    target_name: str

    # Layer 1 result — auto-populates SP fields when provided
    layer1_output: Optional[object] = None  # Layer1Output at runtime

    # Sub-group inputs
    strategic_priority: Layer2StrategicPriorityInputs = Field(
        default_factory=Layer2StrategicPriorityInputs
    )
    target_side_pressure: Layer2TargetSidePressureInputs = Field(
        default_factory=Layer2TargetSidePressureInputs
    )
    buyer_side_urgency: Layer2BuyerSideUrgencyInputs = Field(
        default_factory=Layer2BuyerSideUrgencyInputs
    )
    acquirer_pull: list[AcquirerPullInputRow] = Field(default_factory=list)
    information_readiness: Layer2InformationReadinessInputs = Field(
        default_factory=Layer2InformationReadinessInputs
    )

    # Block 1: pre-pair simple friction signals
    preliminary_transaction_friction: Optional[PreliminaryTransactionFrictionInputs] = Field(
        default=None,
        description=(
            "Obvious pre-pair friction signals (seller unwillingness, price mismatch, etc.). "
            "When present, high friction adds a warning to output but does NOT hard-block "
            "action_classification. Full pair realism belongs in Layer 3."
        ),
    )

    # Layer 3-only inputs — accepted for pass-through, never affect score
    affordability_override: Optional[float] = None
    antitrust_risk: Optional[float] = None
    rofr_impact: Optional[float] = None
    integration_feasibility: Optional[float] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _resolve(val: Optional[float]) -> tuple[float, bool]:
    """(score, is_missing). Missing → neutral 0.50."""
    if val is None:
        return _NEUTRAL, True
    return _clamp(float(val)), False


def _group_confidence(n_total: int, n_missing: int) -> float:
    return _clamp(_BASE_CONFIDENCE - n_missing * _MISSING_CONF_HIT, lo=_MIN_CONFIDENCE)


def _confidence_multiplier(c: float) -> float:
    if c >= 0.80:
        return 1.00
    if c >= 0.60:
        return 0.90
    if c >= 0.40:
        return 0.75
    return 0.50


def _make_comp(
    score: float,
    confidence: float,
    *,
    rationale: str = "",
    positive: list[str] | None = None,
    negative: list[str] | None = None,
    missing: list[str] | None = None,
) -> L2ScoreComponent:
    return L2ScoreComponent(
        score=round(_clamp(score), 6),
        confidence=round(_clamp(confidence), 6),
        rationale=rationale,
        positive_drivers=positive or [],
        negative_drivers=negative or [],
        missing_data=missing or [],
    )


def _weighted(weights: dict[str, float], values: dict[str, float]) -> float:
    return _clamp(sum(weights[k] * values[k] for k in weights))


# ---------------------------------------------------------------------------
# Strategic Priority
# ---------------------------------------------------------------------------

def _score_strategic_priority(
    sp_in: Layer2StrategicPriorityInputs,
    l1: object,  # Layer1Output | None
) -> Layer2StrategicPriority:
    """Score Strategic Priority (40% of BD Action Score).

    Auto-populates from Layer1Output when provided.

    Caps:
      • layer1_asset_quality < 0.50 → cap 0.55
      • acquirer_strategic_fit < 0.35 → cap 0.50
      • strategic_scarcity < 0.35 AND pipeline_gap_urgency < 0.40 → cap 0.60
    """
    # Auto-populate from Layer 1 if not explicit
    l1a_raw = sp_in.layer1_attractiveness_score
    l1s_raw = sp_in.layer1_strategic_scarcity_score
    l1aq_raw = sp_in.layer1_asset_quality_score

    if l1 is not None:
        if l1a_raw is None:
            l1a_raw = getattr(l1, "capped_score", None)
        if l1s_raw is None:
            ss = getattr(l1, "strategic_scarcity", None)
            l1s_raw = getattr(ss, "score", None) if ss is not None else None
        if l1aq_raw is None:
            aq = getattr(l1, "asset_quality", None)
            l1aq_raw = getattr(aq, "score", None) if aq is not None else None

    l1a, l1a_m = _resolve(l1a_raw)
    l1s, l1s_m = _resolve(l1s_raw)
    asf, asf_m = _resolve(sp_in.acquirer_strategic_fit)
    pgu, pgu_m = _resolve(sp_in.pipeline_gap_urgency)
    sov, sov_m = _resolve(sp_in.strategic_option_value)
    l1aq, _ = _resolve(l1aq_raw)

    n_miss = sum([l1a_m, l1s_m, asf_m, pgu_m, sov_m])
    conf = _group_confidence(5, n_miss)

    raw = _weighted(_SP_WEIGHTS, {
        "layer1_attractiveness": l1a,
        "acquirer_strategic_fit": asf,
        "strategic_scarcity": l1s,
        "pipeline_gap_urgency": pgu,
        "strategic_option_value": sov,
    })

    caps: list[str] = []
    if l1aq < 0.50:
        raw = min(raw, 0.55)
        caps.append("strategic_priority_capped_0.55_weak_asset_quality")
    if asf < 0.35:
        raw = min(raw, 0.50)
        caps.append("strategic_priority_capped_0.50_weak_acquirer_strategic_fit")
    if l1s < 0.35 and pgu < 0.40:
        raw = min(raw, 0.60)
        caps.append("strategic_priority_capped_0.60_low_scarcity_and_pipeline_gap")

    def _sp_rat(s: float) -> str:
        if s >= 0.85:
            return "Board-level strategic asset; multiple buyers likely care."
        if s >= 0.70:
            return "Strong strategic priority."
        if s >= 0.55:
            return "Worth monitoring; selective BD work justified."
        if s >= 0.40:
            return "Interesting but not urgent."
        return "Low strategic priority."

    def mk(v: float, m: bool, name: str, note: str) -> L2ScoreComponent:
        return _make_comp(v, conf, rationale=note, missing=[name] if m else [])

    # Block 1: blend in pair-level strategic urgency when provided.
    # Blend weight: 15% urgency, 85% base SP score.
    # UNKNOWN (None) → no change to backward compat.
    _URGENCY_BLEND: float = 0.15
    urgency_raw = sp_in.strategic_urgency_score
    if urgency_raw is not None:
        urgency_val = _clamp(float(urgency_raw))
        raw = _clamp(raw * (1.0 - _URGENCY_BLEND) + urgency_val * _URGENCY_BLEND)

    return Layer2StrategicPriority(
        layer1_attractiveness=mk(l1a, l1a_m, "layer1_attractiveness_score",
                                  "Layer 1 capped strategic attractiveness score"),
        acquirer_strategic_fit=mk(asf, asf_m, "acquirer_strategic_fit",
                                   "Industry-level acquirer strategic fit (not pair-specific)"),
        strategic_scarcity=mk(l1s, l1s_m, "layer1_strategic_scarcity_score",
                               "From Layer 1 strategic scarcity sub-group"),
        pipeline_gap_urgency=mk(pgu, pgu_m, "pipeline_gap_urgency",
                                 "Industry-level pipeline gap urgency across buyer universe"),
        strategic_option_value=mk(sov, sov_m, "strategic_option_value",
                                   "Platform optionality and future indication value"),
        score=round(raw, 6),
        confidence=round(conf, 6),
        caps=caps,
        rationale=_sp_rat(raw),
        strategic_urgency_score=urgency_raw,
    )


# ---------------------------------------------------------------------------
# Transaction Drivers
# ---------------------------------------------------------------------------

def _build_drivers(
    tsp: Layer2TargetSidePressureInputs,
    bsu: Layer2BuyerSideUrgencyInputs,
    top_pull: float,
    top_er: float,
) -> list[TransactionDriver]:
    """Build all transaction driver records from available inputs."""
    fp, _ = _resolve(tsp.financing_pressure)
    cat, _ = _resolve(tsp.catalyst_timing)
    so, _ = _resolve(tsp.seller_openness)
    vd, _ = _resolve(tsp.valuation_distress)
    gov, _ = _resolve(tsp.governance_activist_pressure)
    bpg, _ = _resolve(bsu.pipeline_gap_urgency)
    loe, _ = _resolve(bsu.loe_revenue_cliff_urgency)
    fomo, _ = _resolve(bsu.competitive_fomo)
    bdp, _ = _resolve(bsu.recent_bd_pattern)

    # Derived composite drivers
    ext_wave = _clamp((so + fomo) / 2.0)   # external deal wave
    saf = _clamp(bpg * top_pull)            # scarcity + fit

    raw_drivers = [
        ("financing_pressure", "target_side", fp),
        ("major_catalyst", "target_side", cat),
        ("seller_openness", "target_side", so),
        ("external_deal_wave", "market_side", ext_wave),
        ("valuation_distress", "target_side", vd),
        ("activist_or_governance_pressure", "governance_side", gov),
        ("scarcity_plus_fit", "buyer_side", saf),
        ("existing_partnership", "buyer_side", top_er),
        ("buyer_pipeline_gap", "buyer_side", bpg),
        ("loe_or_revenue_cliff", "buyer_side", loe),
        ("competitive_fomo", "buyer_side", fomo),
        ("recent_bd_pattern", "buyer_side", bdp),
    ]

    drivers: list[TransactionDriver] = []
    for name, cat, strength in raw_drivers:
        w = DRIVER_WEIGHTS[name]
        threshold = _DRIVER_ACTIVATION[name]
        is_active = strength >= threshold
        contribution = round(w * strength * 0.85, 6) if is_active else 0.0
        drivers.append(TransactionDriver(
            name=name,
            category=cat,
            is_active=is_active,
            strength=round(strength, 6),
            confidence=0.85,
            weight=w,
            weighted_contribution=contribution,
            direction="positive",
            rationale=f"strength={strength:.2f}, threshold={threshold:.2f}",
        ))
    return drivers


def _weighted_driver_strength(drivers: list[TransactionDriver]) -> float:
    active_sum = sum(d.weighted_contribution for d in drivers if d.is_active)
    return round(_clamp(active_sum / _TOTAL_DRIVER_WEIGHT), 6)


# ---------------------------------------------------------------------------
# Deal Momentum
# ---------------------------------------------------------------------------

def _score_deal_momentum(
    tsp: Layer2TargetSidePressureInputs,
    bsu: Layer2BuyerSideUrgencyInputs,
    drivers: list[TransactionDriver],
) -> Layer2DealMomentum:
    """Score Deal Momentum (30% of BD Action Score).

    Deal_Momentum = 0.55 × Target_Side_Pressure + 0.45 × Buyer_Side_Urgency

    Caps:
      • 0 active drivers: cap 0.35
      • 1 active driver: cap 0.60
      • fp < 0.30 AND catalyst < 0.30 AND seller_openness < 0.30: cap 0.50
    """
    tsp_vals, tsp_miss = {}, []
    for f in _TSP_WEIGHTS:
        v, m = _resolve(getattr(tsp, f))
        tsp_vals[f] = v
        if m:
            tsp_miss.append(f)

    bsu_vals, bsu_miss = {}, []
    for f in _BSU_WEIGHTS:
        v, m = _resolve(getattr(bsu, f))
        bsu_vals[f] = v
        if m:
            bsu_miss.append(f)

    tsp_score = _weighted(_TSP_WEIGHTS, tsp_vals)
    bsu_score = _weighted(_BSU_WEIGHTS, bsu_vals)
    tsp_conf = _group_confidence(len(_TSP_WEIGHTS), len(tsp_miss))
    bsu_conf = _group_confidence(len(_BSU_WEIGHTS), len(bsu_miss))

    raw = _clamp(_DM_TARGET_SIDE_WEIGHT * tsp_score + _DM_BUYER_SIDE_WEIGHT * bsu_score)
    active_drivers = [d for d in drivers if d.is_active]
    n_active = len(active_drivers)
    wds = _weighted_driver_strength(drivers)

    caps: list[str] = []
    fp = tsp_vals["financing_pressure"]
    cat = tsp_vals["catalyst_timing"]
    so = tsp_vals["seller_openness"]

    if n_active == 0:
        raw = min(raw, 0.35)
        caps.append("deal_momentum_capped_0.35_no_active_drivers")
    elif n_active == 1:
        raw = min(raw, 0.60)
        caps.append("deal_momentum_capped_0.60_single_driver")
    if fp < 0.30 and cat < 0.30 and so < 0.30:
        raw = min(raw, 0.50)
        caps.append("deal_momentum_capped_0.50_no_target_pressure")

    def _dm_rat(s: float, n: int) -> str:
        if s >= 0.65 and n >= 2:
            return f"Strong deal momentum: {n} active drivers."
        if s >= 0.45:
            return f"Moderate momentum: {n} active driver(s)."
        if n == 0:
            return "No active transaction drivers. Monitor only."
        return f"Weak momentum: {n} active driver(s), needs reinforcement."

    overall_conf = _clamp(0.55 * tsp_conf + 0.45 * bsu_conf)
    return Layer2DealMomentum(
        target_side_pressure=_make_comp(
            tsp_score, tsp_conf,
            rationale=f"TSP: fp={fp:.2f}, cat={cat:.2f}, so={so:.2f}",
            missing=tsp_miss,
        ),
        buyer_side_urgency=_make_comp(
            bsu_score, bsu_conf,
            rationale="BSU: pipeline gap, LOE, FOMO, BD pattern, priority recency",
            missing=bsu_miss,
        ),
        weighted_driver_strength=wds,
        active_drivers=active_drivers,
        inactive_drivers=[d for d in drivers if not d.is_active],
        score=round(raw, 6),
        confidence=round(overall_conf, 6),
        caps=caps,
        rationale=_dm_rat(raw, n_active),
    )


# ---------------------------------------------------------------------------
# Acquirer Pull
# ---------------------------------------------------------------------------

def _score_single_acquirer(row: AcquirerPullInputRow) -> AcquirerPullResult:
    vals: dict[str, float] = {}
    n_miss = 0
    for field in _AP_WEIGHTS:
        v, m = _resolve(getattr(row, field, None))
        vals[field] = v
        if m:
            n_miss += 1
    raw = _weighted(_AP_WEIGHTS, vals)
    conf = _group_confidence(len(_AP_WEIGHTS), n_miss)
    if row.profile_freshness_days is not None and row.profile_freshness_days > 365:
        raw = raw * 0.85
        conf = conf * 0.85
    return AcquirerPullResult(
        acquirer_id=row.acquirer_id,
        acquirer_name=row.acquirer_name,
        acquirer_pull_score=round(_clamp(raw), 6),
        confidence=round(_clamp(conf), 6),
        ta_fit=round(vals["ta_fit"], 6),
        modality_fit=round(vals["modality_fit"], 6),
        pipeline_gap_urgency=round(vals["pipeline_gap_urgency"], 6),
        buyer_deal_appetite=round(vals["buyer_deal_appetite"], 6),
        existing_relationship=round(vals["existing_relationship"], 6),
        competitive_fomo=round(vals["competitive_fomo"], 6),
        source_refs=list(row.source_refs),
        profile_freshness_days=row.profile_freshness_days,
        rationale=f"pull={raw:.2f}, conf={conf:.2f}",
    )


def _score_acquirer_pull(
    acquirers: list[AcquirerPullInputRow],
    profile_freshness_score: Optional[float],
) -> Layer2AcquirerPull:
    """Score Acquirer Pull (20% of BD Action Score).

    No acquirers → neutral score (0.50), very low confidence, mapping needed.
    """
    if not acquirers:
        # No acquirers → below-neutral score (0.40) to trigger ACQUIRER_MAPPING_NEEDED
        # classification rather than neutral (0.50) which would mask the gap.
        comp = _make_comp(
            0.40, _MIN_CONFIDENCE,
            rationale="No acquirers provided; acquirer mapping needed.",
            missing=["acquirer_list"],
        )
        return Layer2AcquirerPull(
            top_acquirer_pull=comp,
            acquirer_pull_depth=0,
            buyer_universe_depth=0,
            buyer_concentration_risk=0.0,
            top_acquirers=[],
            score=0.40,
            confidence=_MIN_CONFIDENCE,
            rationale="Acquirer mapping needed.",
        )

    results = sorted(
        [_score_single_acquirer(r) for r in acquirers],
        key=lambda r: r.acquirer_pull_score,
        reverse=True,
    )
    top_pull = results[0].acquirer_pull_score
    second_pull = results[1].acquirer_pull_score if len(results) > 1 else 0.0
    conc_risk = round(_clamp(top_pull - second_pull), 6)
    depth_high = sum(1 for r in results if r.acquirer_pull_score >= _AP_HIGH_THRESHOLD)
    depth_med = sum(1 for r in results if r.acquirer_pull_score >= _AP_MED_THRESHOLD)

    top3 = results[:3]
    avg_top3 = sum(r.acquirer_pull_score for r in top3) / len(top3)
    conf = _group_confidence(1, 0)
    if profile_freshness_score is not None and profile_freshness_score < 0.40:
        avg_top3 = avg_top3 * 0.85
        conf = conf * 0.85

    def _ap_rat(depth: int, risk: float) -> str:
        if depth >= 3:
            return "Multiple high-pull acquirers; competitive process likely."
        if depth == 2:
            return "Two high-pull buyers; bilateral or competitive scenario."
        if depth == 1:
            cr = "High" if risk > 0.30 else "Moderate"
            return f"{cr} single-buyer concentration risk."
        return "No high-pull acquirers identified; mapping needed."

    return Layer2AcquirerPull(
        top_acquirer_pull=_make_comp(
            top_pull, conf,
            rationale=f"Top acquirer: {results[0].acquirer_name}",
        ),
        acquirer_pull_depth=depth_med,
        buyer_universe_depth=depth_high,
        buyer_concentration_risk=conc_risk,
        top_acquirers=results[:5],
        score=round(_clamp(avg_top3), 6),
        confidence=round(_clamp(conf), 6),
        rationale=_ap_rat(depth_high, conc_risk),
    )


# ---------------------------------------------------------------------------
# Information Readiness
# ---------------------------------------------------------------------------

def _score_information_readiness(
    ir_in: Layer2InformationReadinessInputs,
    l1: object,  # Layer1Output | None
) -> Layer2InformationReadiness:
    """Score Information Readiness (10% of BD Action Score)."""
    l1c_raw = ir_in.layer1_confidence
    if l1c_raw is None and l1 is not None:
        l1c_raw = getattr(l1, "overall_confidence", None)

    fields = {
        "layer1_confidence": l1c_raw,
        "acquirer_profile_freshness": ir_in.acquirer_profile_freshness,
        "transaction_driver_source_quality": ir_in.transaction_driver_source_quality,
        "valuation_data_freshness": ir_in.valuation_data_freshness,
        "rights_encumbrance_clarity": ir_in.rights_encumbrance_clarity,
        "catalyst_date_confidence": ir_in.catalyst_date_confidence,
    }
    vals: dict[str, float] = {}
    miss_fields: list[str] = []
    for name, raw in fields.items():
        v, m = _resolve(raw)
        vals[name] = v
        if m:
            miss_fields.append(name)

    conf = _group_confidence(len(fields), len(miss_fields))
    score = _weighted(_IR_WEIGHTS, vals)

    missing_items = list(ir_in.known_missing_items)
    _MISS_MSGS = {
        "layer1_confidence": "layer1_confidence_not_provided",
        "acquirer_profile_freshness": "refresh_acquirer_profiles",
        "transaction_driver_source_quality": "verify_transaction_driver_sources",
        "valuation_data_freshness": "update_market_cap_ev_data",
        "rights_encumbrance_clarity": "check_rights_rofr_status",
        "catalyst_date_confidence": "confirm_catalyst_date",
    }
    for f in miss_fields:
        missing_items.append(_MISS_MSGS[f])

    label = (
        "High" if score >= 0.80 else
        "Medium" if score >= 0.60 else
        "Low" if score >= 0.40 else
        "Very Low"
    )
    def mk(k: str, note: str) -> L2ScoreComponent:
        return _make_comp(vals[k], conf, rationale=note, missing=[k] if k in miss_fields else [])

    return Layer2InformationReadiness(
        layer1_confidence=mk("layer1_confidence", "Layer 1 scoring confidence"),
        acquirer_profile_freshness=mk("acquirer_profile_freshness", "Freshness of acquirer profiles"),
        transaction_driver_source_quality=mk("transaction_driver_source_quality",
                                              "Source quality of transaction drivers"),
        valuation_data_freshness=mk("valuation_data_freshness", "Recency of market/EV data"),
        rights_encumbrance_clarity=mk("rights_encumbrance_clarity", "Rights and ROFR clarity"),
        catalyst_date_confidence=mk("catalyst_date_confidence", "Catalyst timing confidence"),
        score=round(score, 6),
        confidence=round(conf, 6),
        readiness_label=label,
        missing_items=missing_items,
        rationale=f"Information readiness: {label}. {len(missing_items)} missing item(s).",
    )


# ---------------------------------------------------------------------------
# Final score + caps
# ---------------------------------------------------------------------------

def _compute_final(
    sp: float, dm: float, ap: float, ir: float,
    sp_c: float, dm_c: float, ap_c: float, ir_c: float,
) -> tuple[float, float, float, float, float, list[str]]:
    """Returns (raw, capped, overall_conf, multiplier, conf_adjusted, active_caps)."""
    raw = _clamp(
        L2_WEIGHTS["strategic_priority"] * sp
        + L2_WEIGHTS["deal_momentum"] * dm
        + L2_WEIGHTS["acquirer_pull"] * ap
        + L2_WEIGHTS["information_readiness"] * ir
    )
    capped = raw
    caps: list[str] = []
    if sp < 0.40:
        capped = min(capped, 0.50)
        caps.append("bd_action_score_capped_0.50_low_strategic_priority")
    if dm < 0.30:
        capped = min(capped, 0.65)
        caps.append("bd_action_score_capped_0.65_low_deal_momentum")
    if ap < 0.35:
        capped = min(capped, 0.55)
        caps.append("bd_action_score_capped_0.55_low_acquirer_pull")
    if ir < 0.40:
        capped = min(capped, 0.60)
        caps.append("bd_action_score_capped_0.60_low_information_readiness")

    overall_conf = _clamp(
        0.35 * sp_c + 0.30 * dm_c + 0.20 * ap_c + 0.15 * ir_c
    )
    mult = _confidence_multiplier(overall_conf)
    conf_adj = round(_clamp(capped * mult), 6)
    return round(raw, 6), round(capped, 6), round(overall_conf, 6), round(mult, 6), conf_adj, caps


# ---------------------------------------------------------------------------
# Action classification
# ---------------------------------------------------------------------------

class ActionClass:
    ACTIVE_PURSUIT = "Active Pursuit Candidate"
    HIGH_PRIORITY_DILIGENCE = "High-Priority BD Diligence"
    CATALYST_WATCH = "Catalyst Watch"
    STRATEGIC_WATCH = "Strategic Watch"
    RELATIONSHIP_BUILD = "Relationship Build"
    ACQUIRER_MAPPING_NEEDED = "Acquirer Mapping Needed"
    DILIGENCE_QUEUE = "Diligence Queue"
    LOW_PRIORITY_PASS = "Low Priority / Pass"
    DISTRESS_TRAP_WARNING = "Distress Trap Warning"


def _classify_action(
    sp: float, dm: float, ap: float, ir: float,
    bd_score: float,
    catalyst_timing: float,
    financing_pressure: float,
    asset_quality: float,
    valuation_distress: float,
    existing_relationship: float,
) -> str:
    """Priority-ordered action classification from component scores."""
    # Distress trap first — cheapness cannot rescue broken science
    if financing_pressure >= 0.70 and valuation_distress >= 0.65 and asset_quality < 0.50:
        return ActionClass.DISTRESS_TRAP_WARNING
    if sp >= 0.75 and dm >= 0.65 and ap >= 0.65 and ir >= 0.60:
        return ActionClass.ACTIVE_PURSUIT
    if sp >= 0.70 and ap >= 0.60 and ir < 0.60:
        return ActionClass.HIGH_PRIORITY_DILIGENCE
    if catalyst_timing >= 0.70 and sp >= 0.55 and 0.45 <= dm < 0.70:
        return ActionClass.CATALYST_WATCH
    if ir < 0.50 and bd_score >= 0.45:
        return ActionClass.DILIGENCE_QUEUE
    if sp >= 0.70 and dm < 0.45:
        return ActionClass.STRATEGIC_WATCH
    if sp >= 0.65 and ap >= 0.60 and dm < 0.50 and existing_relationship < 0.40:
        return ActionClass.RELATIONSHIP_BUILD
    if sp >= 0.60 and ap < 0.45:
        return ActionClass.ACQUIRER_MAPPING_NEEDED
    if bd_score < 0.45:
        return ActionClass.LOW_PRIORITY_PASS
    return ActionClass.STRATEGIC_WATCH


def _estimate_window(
    financing_pressure: float,
    catalyst_timing: float,
    sp: float,
    dm: float,
    ir: float,
    action: str,
) -> str:
    """Estimate BD action timing window."""
    if ir < 0.40:
        return "uncertain"
    if action == ActionClass.DISTRESS_TRAP_WARNING:
        return "0-6 months"
    if financing_pressure >= 0.70 and catalyst_timing >= 0.70:
        return "0-6 months"
    if catalyst_timing >= 0.55 and dm >= 0.60:
        return "6-18 months"
    if sp >= 0.70 and dm < 0.45:
        return "strategic_watch_only"
    if sp >= 0.55 and dm >= 0.45:
        return "18-36 months"
    return "uncertain"


# ---------------------------------------------------------------------------
# Upgrade / downgrade triggers
# ---------------------------------------------------------------------------

def _upgrade_triggers(
    tsp: Layer2TargetSidePressureInputs,
    bsu: Layer2BuyerSideUrgencyInputs,
    sp_in: Layer2StrategicPriorityInputs,
    ap: Layer2AcquirerPull,
) -> list[str]:
    fp, _ = _resolve(tsp.financing_pressure)
    cat, _ = _resolve(tsp.catalyst_timing)
    pgu, _ = _resolve(bsu.pipeline_gap_urgency)
    l1a, _ = _resolve(sp_in.layer1_attractiveness_score)
    triggers = []
    if fp < 0.60:
        triggers.append("financing_runway_falls_below_12_months")
    if cat < 0.65:
        triggers.append("positive_catalyst_data_phase2_or_phase3")
    if pgu < 0.65:
        triggers.append("buyer_pipeline_failure_same_ta")
    triggers += [
        "comparable_deal_at_premium_establishes_new_valuation_reference",
        "management_announces_strategic_review",
        "activist_pressure_increases",
    ]
    if ap.buyer_universe_depth < 2:
        triggers.append("additional_buyer_pipeline_gap_identified")
    triggers += [
        "competitor_safety_issue_improves_relative_attractiveness",
        "partner_relationship_deepens",
    ]
    if l1a < 0.70:
        triggers.append("layer1_upgrade_from_new_clinical_data")
    return triggers


def _downgrade_triggers(
    tsp: Layer2TargetSidePressureInputs,
    bsu: Layer2BuyerSideUrgencyInputs,
    sp_in: Layer2StrategicPriorityInputs,
    ir: Layer2InformationReadiness,
) -> list[str]:
    fp, _ = _resolve(tsp.financing_pressure)
    pgu, _ = _resolve(bsu.pipeline_gap_urgency)
    l1a, _ = _resolve(sp_in.layer1_attractiveness_score)
    triggers = []
    if fp >= 0.50:
        triggers.append("financing_extended_runway_above_24_months")
    if pgu >= 0.60:
        triggers.append("buyer_fills_pipeline_gap_elsewhere")
    if l1a >= 0.60:
        triggers.append("competitor_reports_superior_data")
    triggers += [
        "catalyst_delayed_more_than_12_months",
        "negative_trial_or_regulatory_update",
        "insider_selling_or_governance_issue",
        "rights_rofr_issue_worsens",
        "market_expectations_rise_removes_value_gap",
    ]
    if ir.score < 0.60:
        triggers.append("acquirer_profile_stale_or_priority_changes")
    return triggers


# ---------------------------------------------------------------------------
# Layer ownership compliance
# ---------------------------------------------------------------------------

def _ownership_warnings(inputs: Layer2Inputs) -> list[str]:
    warnings = []
    if inputs.affordability_override is not None:
        warnings.append("affordability_input_ignored_layer3_owned")
    if inputs.antitrust_risk is not None:
        warnings.append("antitrust_input_ignored_layer3_owned")
    if inputs.rofr_impact is not None:
        warnings.append("pair_specific_rofr_input_ignored_layer3_owned")
    if inputs.integration_feasibility is not None:
        warnings.append("integration_feasibility_input_ignored_layer3_owned")
    return warnings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_layer2_bd_priority(inputs: Layer2Inputs) -> Layer2BDOutput:
    """Layer 2 BD Prioritization Engine.

    Computes BD_Action_Score = 0.40×SP + 0.30×DM + 0.20×AP + 0.10×IR.

    Does NOT score pair-specific affordability, antitrust, ROFR, or
    integration capability — those belong in Layer 3.

    Args:
        inputs: Layer2Inputs with target name, optional Layer1Output,
                sub-group inputs for SP/DM/AP/IR, and pass-through L3 fields.

    Returns:
        Layer2BDOutput with action classification, timing window,
        steering triggers, and full sub-group diagnostics.
    """
    l1 = inputs.layer1_output

    # 1. Score acquirer pull first (needed for driver building)
    ap = _score_acquirer_pull(
        inputs.acquirer_pull,
        inputs.information_readiness.acquirer_profile_freshness,
    )
    top_pull = ap.score
    top_er = ap.top_acquirers[0].existing_relationship if ap.top_acquirers else 0.0

    # 2. Build transaction drivers
    drivers = _build_drivers(
        inputs.target_side_pressure,
        inputs.buyer_side_urgency,
        top_pull,
        top_er,
    )

    # 3. Score sub-groups
    sp = _score_strategic_priority(inputs.strategic_priority, l1)
    dm = _score_deal_momentum(inputs.target_side_pressure, inputs.buyer_side_urgency, drivers)
    ir = _score_information_readiness(inputs.information_readiness, l1)

    # 4. Compute final score with caps and confidence
    raw, capped, overall_conf, mult, conf_adj, final_caps = _compute_final(
        sp.score, dm.score, ap.score, ir.score,
        sp.confidence, dm.confidence, ap.confidence, ir.confidence,
    )

    # 5. Resolved values for classification
    fp, _ = _resolve(inputs.target_side_pressure.financing_pressure)
    cat, _ = _resolve(inputs.target_side_pressure.catalyst_timing)
    vd, _ = _resolve(inputs.target_side_pressure.valuation_distress)
    if l1 is not None:
        aq_obj = getattr(l1, "asset_quality", None)
        aq = getattr(aq_obj, "score", _NEUTRAL) if aq_obj is not None else _NEUTRAL
    else:
        aq, _ = _resolve(inputs.strategic_priority.layer1_asset_quality_score)

    action = _classify_action(
        sp.score, dm.score, ap.score, ir.score,
        conf_adj, cat, fp, aq, vd, top_er,
    )
    window = _estimate_window(fp, cat, sp.score, dm.score, ir.score, action)

    # 6. Triggers
    up = _upgrade_triggers(inputs.target_side_pressure, inputs.buyer_side_urgency,
                            inputs.strategic_priority, ap)
    down = _downgrade_triggers(inputs.target_side_pressure, inputs.buyer_side_urgency,
                                inputs.strategic_priority, ir)

    # 7. Missing data + compliance
    all_missing = list(dict.fromkeys(
        ir.missing_items
        + [d for c in [sp.layer1_attractiveness, sp.acquirer_strategic_fit,
                       sp.strategic_scarcity, sp.pipeline_gap_urgency,
                       sp.strategic_option_value] for d in c.missing_data]
    ))
    warnings = _ownership_warnings(inputs)

    # Block 1: preliminary friction — add warning when any signal is elevated.
    # Never hard-blocks action_classification; full realism belongs in Layer 3.
    if inputs.preliminary_transaction_friction is not None:
        friction_result = compute_preliminary_friction(inputs.preliminary_transaction_friction)
        if friction_result.friction_label != "CLEAN" or friction_result.active_friction_signals:
            signal_list = ", ".join(friction_result.active_friction_signals) or "unspecified"
            warnings.append(
                f"preliminary_friction:{friction_result.friction_label};"
                f"signals=[{signal_list}];"
                f"score={friction_result.friction_score:.2f};"
                "full_realism_scoring_belongs_in_layer3"
            )

    all_caps = list(sp.caps) + list(dm.caps) + final_caps

    return Layer2BDOutput(
        strategic_priority=sp,
        deal_momentum=dm,
        acquirer_pull=ap,
        information_readiness=ir,
        bd_action_score=raw,
        capped_bd_action_score=capped,
        confidence_adjusted_score=conf_adj,
        overall_confidence=overall_conf,
        confidence_multiplier=mult,
        action_classification=action,
        expected_action_window=window,
        active_transaction_drivers=dm.active_drivers,
        weighted_driver_strength=dm.weighted_driver_strength,
        target_side_pressure=dm.target_side_pressure.score,
        buyer_side_urgency=dm.buyer_side_urgency.score,
        buyer_universe_depth=ap.buyer_universe_depth,
        buyer_concentration_risk=ap.buyer_concentration_risk,
        upgrade_triggers=up,
        downgrade_triggers=down,
        missing_data=all_missing,
        rationale=(
            f"{inputs.target_name}: {action}. "
            f"BD score={conf_adj:.2f} (capped={capped:.2f}). "
            f"Window: {window}. {len(dm.active_drivers)} active driver(s)."
        ),
        layer_ownership_warnings=warnings,
        active_caps=all_caps,
    )
