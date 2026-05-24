"""
Layer 1 — Strategic Attractiveness Engine (Institutional-Grade).

Answers the single question:
    "Assuming this company passed Layer 0, how fundamentally attractive is
    this asset/company as a BD target?"

Formula:
    raw_score = 0.35 × asset_quality
              + 0.25 × strategic_scarcity
              + 0.20 × value_creation
              + 0.15 × transaction_setup
              + 0.05 × structural_cleanliness

    capped_score                = min(raw_score, all_triggered_cap_values)
    confidence_adjusted_score   = capped_score × confidence_multiplier

Layer 1 deliberately does NOT answer:
    • Is the company eligible?                    → Layer 0
    • Can a specific acquirer afford it?          → Layer 3
    • Does a specific buyer fit this asset?       → Layer 2 / Layer 3
    • Should BD act immediately?                  → Layer 2
    • What exact deal structure should be used?   → Layer 4
    • Is the final score empirically calibrated?  → Layer 5

Anti-double-counting ownership map (authoritative for this module):
    eligibility / hard exclusion / routing            → Layer 0
    target-level asset quality                        → Layer 1  ← THIS MODULE
    target-level strategic scarcity                   → Layer 1  ← THIS MODULE
    target-level value creation                       → Layer 1  ← THIS MODULE
    target-level transaction setup                    → Layer 1  ← THIS MODULE
    structural cleanliness (residual after Layer 0)   → Layer 1  ← THIS MODULE
    BD action priority                                → Layer 2
    acquirer-specific affordability                   → Layer 3
    acquirer-specific integration capability          → Layer 3
    acquirer-specific ROFR / partner impact           → Layer 3
    acquirer-specific antitrust                       → Layer 3
    acquirer-specific manufacturing fit               → Layer 3
    deal structure routing                            → Layer 4
    calibration                                       → Layer 5
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Anti-double-counting constants
# ---------------------------------------------------------------------------

LAYER1_OWNERSHIP_MAP: dict[str, str] = {
    "eligibility_hard_exclusion": "Layer 0",
    "deal_type_routing": "Layer 0",
    "target_level_asset_quality": "Layer 1",
    "target_level_strategic_scarcity": "Layer 1",
    "target_level_value_creation": "Layer 1",
    "target_level_transaction_setup": "Layer 1",
    "structural_cleanliness_residual": "Layer 1",
    "bd_action_priority": "Layer 2",
    "acquirer_specific_affordability": "Layer 3",
    "acquirer_specific_integration": "Layer 3",
    "acquirer_specific_rofr_partner": "Layer 3",
    "acquirer_specific_antitrust": "Layer 3",
    "acquirer_manufacturing_fit": "Layer 3",
    "deal_structure_routing": "Layer 4",
    "calibration": "Layer 5",
}

# Signals that belong in Layer 3, never Layer 1
LAYER3_ONLY_SIGNALS: frozenset[str] = frozenset({
    "buyer_affordability",
    "buyer_integration_capability",
    "buyer_manufacturing_fit",
    "buyer_antitrust_risk",
    "buyer_rofr_impact",
    "buyer_regional_rights_fit",
    "buyer_specific_pipeline_gap",
    "pair_specific_asset_control",
})

ANTI_DOUBLE_COUNTING_NOTES: list[str] = [
    "buyer_affordability: belongs in Layer 3, not Layer 1",
    "buyer_integration_capability: belongs in Layer 3, not Layer 1",
    "buyer_manufacturing_fit: belongs in Layer 3, not Layer 1",
    "buyer_antitrust_risk: belongs in Layer 3, not Layer 1",
    "buyer_rofr_impact: belongs in Layer 3, not Layer 1",
    "buyer_regional_rights_fit: belongs in Layer 3, not Layer 1",
    "buyer_specific_pipeline_gap: belongs in Layer 2/3, not Layer 1",
    "hard_eligibility_exclusion: belongs in Layer 0, not Layer 1",
    "final_recommendation_to_act: belongs in Layer 2, not Layer 1",
    "exact_deal_structure_selection: belongs in Layer 4, not Layer 1",
]


# ---------------------------------------------------------------------------
# Weight constants
# ---------------------------------------------------------------------------

# Top-level Layer 1 weights
L1_WEIGHTS: dict[str, float] = {
    "asset_quality": 0.35,
    "strategic_scarcity": 0.25,
    "value_creation": 0.20,
    "transaction_setup": 0.15,
    "structural_cleanliness": 0.05,
}
assert abs(sum(L1_WEIGHTS.values()) - 1.0) < 1e-9, "L1_WEIGHTS must sum to 1.0"

# Asset Quality sub-weights
_AQ_WEIGHTS: dict[str, float] = {
    "clinical_evidence": 0.25,
    "differentiation": 0.20,
    "regulatory_path": 0.15,
    "ip_exclusivity": 0.15,
    "cmc_feasibility": 0.10,
    "commercial_meaningfulness": 0.10,
    "management_execution": 0.05,
}
assert abs(sum(_AQ_WEIGHTS.values()) - 1.0) < 1e-9

# Strategic Scarcity sub-weights
_SS_WEIGHTS: dict[str, float] = {
    "ta_scarcity": 0.25,
    "modality_platform_scarcity": 0.20,
    "competitive_position": 0.20,
    "pipeline_gap_relevance": 0.15,
    "franchise_optionality": 0.10,
    "replacement_difficulty": 0.10,
}
assert abs(sum(_SS_WEIGHTS.values()) - 1.0) < 1e-9

# Value Creation sub-weights
_VC_WEIGHTS: dict[str, float] = {
    "premium_adjusted_rnpv_gap": 0.35,
    "standalone_rnpv_quality": 0.20,
    "downside_protection": 0.15,
    "cost_to_complete": 0.10,
    "market_expectations_gap": 0.10,
    "strategic_option_value": 0.10,
}
assert abs(sum(_VC_WEIGHTS.values()) - 1.0) < 1e-9

# Transaction Setup sub-weights
_TS_WEIGHTS: dict[str, float] = {
    "financing_pressure": 0.30,
    "catalyst_proximity": 0.25,
    "seller_openness": 0.20,
    "valuation_stress": 0.15,
    "prior_bd_activity": 0.10,
}
assert abs(sum(_TS_WEIGHTS.values()) - 1.0) < 1e-9

# Structural Cleanliness sub-weights
_SC_WEIGHTS: dict[str, float] = {
    "rights_clarity": 0.30,
    "ip_cleanliness": 0.25,
    "economic_control": 0.20,
    "diligence_readiness": 0.15,
    "manufacturing_transferability": 0.10,
}
assert abs(sum(_SC_WEIGHTS.values()) - 1.0) < 1e-9

# Confidence scoring constants
_NEUTRAL = 0.50                    # default score when field is missing
_MISSING_CONFIDENCE_HIT = 0.10    # confidence reduction per missing field
_BASE_CONFIDENCE = 0.70            # default starting confidence
_MIN_CONFIDENCE = 0.20             # floor for group confidence


# ---------------------------------------------------------------------------
# Confidence multiplier tiers
# ---------------------------------------------------------------------------

def _confidence_multiplier(overall_confidence: float) -> float:
    """Map overall confidence [0,1] to a score multiplier [0.50, 1.00]."""
    if overall_confidence >= 0.80:
        return 1.00
    if overall_confidence >= 0.60:
        return 0.90
    if overall_confidence >= 0.40:
        return 0.75
    return 0.50


# ---------------------------------------------------------------------------
# Core shared data models
# ---------------------------------------------------------------------------

class Cap(BaseModel):
    """Explicit cap applied to a sub-group or Layer 1 composite score."""
    model_config = ConfigDict(frozen=True)

    name: str
    cap_value: float = Field(..., ge=0.0, le=1.0)
    reason: str
    owning_layer: Literal["Layer 1"] = "Layer 1"
    triggered_by: str


class ScoreComponent(BaseModel):
    """Rich score container for a single sub-dimension."""
    model_config = ConfigDict(frozen=True)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    caps_triggered: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Input models — one per Layer 1 sub-group
# ---------------------------------------------------------------------------

class Layer1AssetQualityInputs(BaseModel):
    """Inputs for Asset Quality (35% of Layer 1).

    All score fields are pre-computed sub-dimension scores in [0, 1].
    None = not available; score defaults to neutral (0.50) and reduces confidence.

    Anti-double-counting notes:
    - ip_exclusivity: scores residual exclusivity quality AFTER Layer 0 passes hard
      rights checks. Layer 0 should handle hard rights exclusions.
    - cmc_feasibility: target-level manufacturing risk. Buyer-specific manufacturing
      fit belongs in Layer 3, NOT here.
    - commercial_meaningfulness: target-level market opportunity. Buyer-specific
      commercial capability belongs in Layer 3, NOT here.
    - management_execution: intentionally small (5%) because Layer 0 and Layer 3
      both check governance and execution separately.
    """
    model_config = ConfigDict(frozen=True)

    clinical_evidence: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Strength of clinical package: phase, design, endpoints, effect size, safety"
    )
    differentiation: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Differentiation vs current and future standard of care"
    )
    regulatory_path: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Clarity and credibility of regulatory approval pathway"
    )
    ip_exclusivity: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="IP estate strength plus exclusivity runway (Layer 0 passes hard rights first)"
    )
    cmc_feasibility: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Manufacturing feasibility, scalability, CMC maturity (target-level, not buyer-specific)"
    )
    commercial_meaningfulness: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Market size and commercial opportunity (target-level, not buyer commercial capability)"
    )
    management_execution: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Management track record: clinical, regulatory, financing, transparency"
    )

    # Hard condition override flags — these trigger caps regardless of sub-scores
    no_human_data: bool = False                           # no human data for clinical-stage asset
    pivotal_failure_no_salvage: bool = False              # Phase 3 failure, no salvage path
    fatal_safety_signal: bool = False                     # safety signal that kills the program
    fraud_or_data_integrity_issue: bool = False           # material fraud / data integrity
    unresolved_clinical_hold: bool = False                # unresolved FDA/EMA clinical hold
    crl_without_credible_fix: bool = False                # CRL with no credible resolution path
    active_material_ip_litigation: bool = False           # active material IP litigation
    manufacturing_not_transferable: bool = False          # manufacturing cannot be transferred
    cogs_breaks_commercial_model: bool = False            # COGS makes commercial model unviable


class Layer1StrategicScarcityInputs(BaseModel):
    """Inputs for Strategic Scarcity (25% of Layer 1).

    All scores measure INDUSTRY-LEVEL demand for this type of asset, not any
    specific buyer's fit. Buyer-specific TA / modality alignment belongs in
    Layer 2 (BD action priority) and Layer 3 (acquirer fit).

    TODO: wire ta_scarcity from deal_heat_score or TA deal activity tracker.
    TODO: wire competitive_position from dynamic_competition_engine.
    """
    model_config = ConfigDict(frozen=True)

    ta_scarcity: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="TA heat: deal activity, patent cliff pressure, unmet need, late-stage scarcity"
    )
    modality_platform_scarcity: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Platform / modality scarcity; manufacturing or delivery barriers to entry"
    )
    competitive_position: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Relative competitive position in treatment algorithm vs current and future SoC"
    )
    pipeline_gap_relevance: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Maps to broad industry pipeline gaps (patent cliff, TA white space)"
    )
    franchise_optionality: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Follow-on indications, lifecycle management, platform reuse, combination potential"
    )
    replacement_difficulty: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="How hard it is for any buyer to recreate or substitute this asset"
    )

    # Hard condition flags
    clearly_inferior_to_future_soc: bool = False         # clearly worse than emerging SoC
    platform_unvalidated_no_clinical_asset: bool = False  # platform with no validated clinical asset
    no_clear_place_in_treatment_algorithm: bool = False   # no differentiated treatment role


class Layer1ValueCreationInputs(BaseModel):
    """Inputs for Value Creation (20% of Layer 1).

    Layer 1 assesses standalone economics and market-implied dislocation.
    Affordability by a specific acquirer is Layer 3, NOT Layer 1.

    Value-trap guard: if asset_quality < 0.50, premium_adjusted_rnpv_gap
    contribution is zeroed — cheapness cannot rescue broken science.

    TODO: wire premium_adjusted_rnpv_gap from valuation engine rNPV output.
    TODO: wire market_expectations_gap from market_expectations.py.
    """
    model_config = ConfigDict(frozen=True)

    premium_adjusted_rnpv_gap: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Normalised (buyer-neutral) strategic value minus expected acquisition cost"
    )
    standalone_rnpv_quality: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Credibility and quality of the standalone rNPV model"
    )
    downside_protection: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Protection from net cash, approved products, or platform residual value"
    )
    cost_to_complete: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Lower remaining development burden = higher score"
    )
    market_expectations_gap: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Model vs market implied dislocation (gap = opportunity)"
    )
    strategic_option_value: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Option value from follow-on indications, combinations, platform extensions"
    )

    # Raw gap in $M for guard logic (negative = value-destructive at current ask)
    premium_adjusted_rnpv_gap_raw: float = Field(
        default=0.0,
        description="Raw rNPV gap in $M; positive = accretive, negative = destructive at current ask"
    )
    market_data_stale_or_illiquid: bool = False


class Layer1TransactionSetupInputs(BaseModel):
    """Inputs for Transaction Setup (15% of Layer 1).

    This captures target-level transaction plausibility only.
    Full deal probability (including buyer urgency and pair-specific factors)
    belongs in Layer 2 and Layer 3.

    Important: This is NOT the same as Layer 2 transaction probability.
    Layer 1 only assesses whether the target has the conditions that COULD
    make a transaction plausible, not whether it WILL transact.
    """
    model_config = ConfigDict(frozen=True)

    financing_pressure: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Target's capital stress: cash runway, burn rate, going concern risk"
    )
    catalyst_proximity: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Proximity and materiality of upcoming value-defining catalysts"
    )
    seller_openness: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Signals of management/board openness to a transaction"
    )
    valuation_stress: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="EV compression, drawdown from high, EV vs strategic value dislocation"
    )
    prior_bd_activity: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="History of partnerships, licensing, and BD openness signals"
    )

    # Guard flags
    founder_controlled_no_pressure: bool = False
    management_committed_independence_well_funded: bool = False
    valuation_stress_due_to_asset_failure: bool = False


class Layer1StructuralCleanlinessInputs(BaseModel):
    """Inputs for Structural Cleanliness (5% of Layer 1).

    RESIDUAL quality check only. Major structural issues (hard ROFR, blocked
    rights, going-concern) should have been excluded by Layer 0.
    Pair-specific ROFR impact, partner consent, and antitrust belong in Layer 3.

    Important: This sub-group carries only 5% weight because Layer 0 and Layer 3
    already handle most structural / feasibility issues.
    """
    model_config = ConfigDict(frozen=True)

    rights_clarity: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Global rights clarity; regional/field limitations reduce score"
    )
    ip_cleanliness: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="IP ownership clarity, litigation absence, FTO clarity"
    )
    economic_control: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Clean economics: royalty / milestone / profit-share simplicity"
    )
    diligence_readiness: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Data room maturity and clinical / regulatory package completeness"
    )
    manufacturing_transferability: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Process documentation and tech transfer feasibility"
    )


class Layer1Inputs(BaseModel):
    """Top-level container for all Layer 1 inputs."""
    model_config = ConfigDict(frozen=True)

    target_name: str
    asset_quality: Layer1AssetQualityInputs = Field(
        default_factory=Layer1AssetQualityInputs
    )
    strategic_scarcity: Layer1StrategicScarcityInputs = Field(
        default_factory=Layer1StrategicScarcityInputs
    )
    value_creation: Layer1ValueCreationInputs = Field(
        default_factory=Layer1ValueCreationInputs
    )
    transaction_setup: Layer1TransactionSetupInputs = Field(
        default_factory=Layer1TransactionSetupInputs
    )
    structural_cleanliness: Layer1StructuralCleanlinessInputs = Field(
        default_factory=Layer1StructuralCleanlinessInputs
    )


# ---------------------------------------------------------------------------
# Sub-group output models
# ---------------------------------------------------------------------------

class Layer1AssetQuality(BaseModel):
    model_config = ConfigDict(frozen=True)

    clinical_evidence: ScoreComponent
    differentiation: ScoreComponent
    regulatory_path: ScoreComponent
    ip_exclusivity: ScoreComponent
    cmc_feasibility: ScoreComponent
    commercial_meaningfulness: ScoreComponent
    management_execution: ScoreComponent
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    caps: list[Cap] = Field(default_factory=list)


class Layer1StrategicScarcity(BaseModel):
    model_config = ConfigDict(frozen=True)

    ta_scarcity: ScoreComponent
    modality_platform_scarcity: ScoreComponent
    competitive_position: ScoreComponent
    pipeline_gap_relevance: ScoreComponent
    franchise_optionality: ScoreComponent
    replacement_difficulty: ScoreComponent
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    caps: list[Cap] = Field(default_factory=list)


class Layer1ValueCreation(BaseModel):
    model_config = ConfigDict(frozen=True)

    premium_adjusted_rnpv_gap: ScoreComponent
    standalone_rnpv_quality: ScoreComponent
    downside_protection: ScoreComponent
    cost_to_complete: ScoreComponent
    market_expectations_gap: ScoreComponent
    strategic_option_value: ScoreComponent
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    value_trap_flags: list[str] = Field(default_factory=list)
    caps: list[Cap] = Field(default_factory=list)


class Layer1TransactionSetup(BaseModel):
    model_config = ConfigDict(frozen=True)

    financing_pressure: ScoreComponent
    catalyst_proximity: ScoreComponent
    seller_openness: ScoreComponent
    valuation_stress: ScoreComponent
    prior_bd_activity: ScoreComponent
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    caps: list[Cap] = Field(default_factory=list)


class Layer1StructuralCleanliness(BaseModel):
    model_config = ConfigDict(frozen=True)

    rights_clarity: ScoreComponent
    ip_cleanliness: ScoreComponent
    economic_control: ScoreComponent
    diligence_readiness: ScoreComponent
    manufacturing_transferability: ScoreComponent
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    caps: list[Cap] = Field(default_factory=list)


class Layer1Output(BaseModel):
    """Full Layer 1 Strategic Attractiveness output for a single BD target."""
    model_config = ConfigDict(frozen=True)

    # Sub-group results
    asset_quality: Layer1AssetQuality
    strategic_scarcity: Layer1StrategicScarcity
    value_creation: Layer1ValueCreation
    transaction_setup: Layer1TransactionSetup
    structural_cleanliness: Layer1StructuralCleanliness

    # Composite scores
    raw_score: float = Field(..., ge=0.0, le=1.0,
        description="Weighted sum before caps")
    capped_score: float = Field(..., ge=0.0, le=1.0,
        description="After all Layer 1 caps applied")
    confidence_adjusted_score: float = Field(..., ge=0.0, le=1.0,
        description="After confidence multiplier applied")

    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_multiplier: float = Field(..., ge=0.0, le=1.0)

    # All caps that fired (sub-group + composite)
    active_caps: list[Cap] = Field(default_factory=list)

    # Narrative
    top_positive_drivers: list[str] = Field(default_factory=list)
    top_negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    diligence_questions: list[str] = Field(default_factory=list)

    # Classification
    thesis_type: str
    plain_english_verdict: str

    # Anti-double-counting audit trail
    anti_double_counting_notes: list[str] = Field(default_factory=list)

    # Flag: low confidence → push to diligence queue
    low_confidence_diligence_queue: bool = False


# ---------------------------------------------------------------------------
# Internal scoring helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _resolve(val: Optional[float]) -> tuple[float, bool]:
    """Return (score, is_missing). Missing → neutral score."""
    if val is None:
        return _NEUTRAL, True
    return float(val), False


def _group_confidence(n_fields: int, n_missing: int) -> float:
    """Base confidence, reduced by _MISSING_CONFIDENCE_HIT per missing field."""
    return _clamp(
        _BASE_CONFIDENCE - n_missing * _MISSING_CONFIDENCE_HIT,
        lo=_MIN_CONFIDENCE,
        hi=1.0,
    )


def _make_component(
    score: float,
    confidence: float,
    *,
    rationale: str = "",
    positive: list[str] | None = None,
    negative: list[str] | None = None,
    missing: list[str] | None = None,
    caps: list[str] | None = None,
) -> ScoreComponent:
    return ScoreComponent(
        score=round(_clamp(score), 6),
        confidence=round(_clamp(confidence), 6),
        rationale=rationale,
        positive_drivers=positive or [],
        negative_drivers=negative or [],
        missing_data=missing or [],
        caps_triggered=caps or [],
    )


def _sub_component(
    field: str,
    scores: dict[str, float],
    missing: list[str],
    confidence: float,
) -> ScoreComponent:
    """Build a ScoreComponent for one sub-dimension field."""
    v = scores[field]
    positive = [f"strong_{field}"] if v >= 0.70 else []
    negative = [f"weak_{field}"] if v < 0.40 else []
    missing_list = [field] if field in missing else []
    return _make_component(v, confidence, positive=positive, negative=negative, missing=missing_list)


# ---------------------------------------------------------------------------
# Sub-group scorers
# ---------------------------------------------------------------------------

def _score_asset_quality(
    inputs: Layer1AssetQualityInputs,
) -> Layer1AssetQuality:
    """Compute Asset Quality score (35% of Layer 1)."""
    field_names = list(_AQ_WEIGHTS.keys())
    scores: dict[str, float] = {}
    missing: list[str] = []
    for f in field_names:
        v, is_missing = _resolve(getattr(inputs, f))
        scores[f] = v
        if is_missing:
            missing.append(f)

    caps: list[Cap] = []

    # Clinical evidence hard condition caps (most restrictive wins)
    ce = scores["clinical_evidence"]
    if inputs.fatal_safety_signal and ce > 0.20:
        scores["clinical_evidence"] = 0.20
        caps.append(Cap(
            name="fatal_safety_signal_ce_cap",
            cap_value=0.20,
            reason="Fatal safety signal caps clinical_evidence at 0.20",
            triggered_by="fatal_safety_signal=True",
        ))
    elif inputs.pivotal_failure_no_salvage and ce > 0.25:
        scores["clinical_evidence"] = 0.25
        caps.append(Cap(
            name="pivotal_failure_ce_cap",
            cap_value=0.25,
            reason="Pivotal failure with no salvage path caps clinical_evidence at 0.25",
            triggered_by="pivotal_failure_no_salvage=True",
        ))
    elif inputs.no_human_data and ce > 0.35:
        scores["clinical_evidence"] = 0.35
        caps.append(Cap(
            name="no_human_data_ce_cap",
            cap_value=0.35,
            reason="No human data for clinical-stage asset caps clinical_evidence at 0.35",
            triggered_by="no_human_data=True",
        ))

    # Regulatory path hard condition caps
    reg = scores["regulatory_path"]
    if inputs.unresolved_clinical_hold and reg > 0.35:
        scores["regulatory_path"] = 0.35
        caps.append(Cap(
            name="unresolved_clinical_hold_reg_cap",
            cap_value=0.35,
            reason="Unresolved clinical hold caps regulatory_path at 0.35",
            triggered_by="unresolved_clinical_hold=True",
        ))
    elif inputs.crl_without_credible_fix and reg > 0.40:
        scores["regulatory_path"] = 0.40
        caps.append(Cap(
            name="crl_without_fix_reg_cap",
            cap_value=0.40,
            reason="CRL without credible resolution caps regulatory_path at 0.40",
            triggered_by="crl_without_credible_fix=True",
        ))

    # IP hard condition caps
    ip = scores["ip_exclusivity"]
    if inputs.active_material_ip_litigation and ip > 0.60:
        scores["ip_exclusivity"] = 0.60
        caps.append(Cap(
            name="active_ip_litigation_cap",
            cap_value=0.60,
            reason="Active material IP litigation caps ip_exclusivity at 0.60",
            triggered_by="active_material_ip_litigation=True",
        ))

    # CMC hard condition caps
    cmc = scores["cmc_feasibility"]
    if inputs.manufacturing_not_transferable and cmc > 0.40:
        scores["cmc_feasibility"] = 0.40
        caps.append(Cap(
            name="manufacturing_not_transferable_cmc_cap",
            cap_value=0.40,
            reason="Manufacturing not transferable caps cmc_feasibility at 0.40",
            triggered_by="manufacturing_not_transferable=True",
        ))

    # Commercial hard condition caps
    cm = scores["commercial_meaningfulness"]
    if inputs.cogs_breaks_commercial_model and cm > 0.55:
        scores["commercial_meaningfulness"] = 0.55
        caps.append(Cap(
            name="cogs_breaks_commercial_model_cap",
            cap_value=0.55,
            reason="COGS breaks commercial model caps commercial_meaningfulness at 0.55",
            triggered_by="cogs_breaks_commercial_model=True",
        ))

    # Management hard condition caps
    mgmt = scores["management_execution"]
    if inputs.fraud_or_data_integrity_issue and mgmt > 0.20:
        scores["management_execution"] = 0.20
        caps.append(Cap(
            name="fraud_data_integrity_mgmt_cap",
            cap_value=0.20,
            reason="Fraud or data integrity issue caps management_execution at 0.20",
            triggered_by="fraud_or_data_integrity_issue=True",
        ))

    # Weighted average
    raw = sum(scores[k] * _AQ_WEIGHTS[k] for k in _AQ_WEIGHTS)

    # Score-based cap: low clinical evidence caps asset_quality group
    ce_final = scores["clinical_evidence"]
    if ce_final < 0.35 and raw > 0.55:
        raw = 0.55
        caps.append(Cap(
            name="low_clinical_evidence_aq_cap",
            cap_value=0.55,
            reason=f"clinical_evidence={ce_final:.2f} < 0.35 caps asset_quality at 0.55",
            triggered_by="clinical_evidence<0.35",
        ))

    confidence = _group_confidence(len(field_names), len(missing))
    score = _clamp(raw)

    return Layer1AssetQuality(
        clinical_evidence=_sub_component("clinical_evidence", scores, missing, confidence),
        differentiation=_sub_component("differentiation", scores, missing, confidence),
        regulatory_path=_sub_component("regulatory_path", scores, missing, confidence),
        ip_exclusivity=_sub_component("ip_exclusivity", scores, missing, confidence),
        cmc_feasibility=_sub_component("cmc_feasibility", scores, missing, confidence),
        commercial_meaningfulness=_sub_component("commercial_meaningfulness", scores, missing, confidence),
        management_execution=_sub_component("management_execution", scores, missing, confidence),
        score=round(score, 6),
        confidence=round(confidence, 6),
        caps=caps,
    )


def _score_strategic_scarcity(
    inputs: Layer1StrategicScarcityInputs,
) -> Layer1StrategicScarcity:
    """Compute Strategic Scarcity score (25% of Layer 1)."""
    field_names = list(_SS_WEIGHTS.keys())
    scores: dict[str, float] = {}
    missing: list[str] = []
    for f in field_names:
        v, is_missing = _resolve(getattr(inputs, f))
        scores[f] = v
        if is_missing:
            missing.append(f)

    caps: list[Cap] = []

    # Hard condition caps
    cp = scores["competitive_position"]
    if inputs.clearly_inferior_to_future_soc and cp > 0.45:
        scores["competitive_position"] = 0.45
        caps.append(Cap(
            name="inferior_to_future_soc_cp_cap",
            cap_value=0.45,
            reason="Clearly inferior to future SoC caps competitive_position at 0.45",
            triggered_by="clearly_inferior_to_future_soc=True",
        ))
    elif inputs.no_clear_place_in_treatment_algorithm and cp > 0.55:
        scores["competitive_position"] = 0.55
        caps.append(Cap(
            name="no_treatment_algorithm_place_cp_cap",
            cap_value=0.55,
            reason="No clear place in treatment algorithm caps competitive_position at 0.55",
            triggered_by="no_clear_place_in_treatment_algorithm=True",
        ))

    mp = scores["modality_platform_scarcity"]
    if inputs.platform_unvalidated_no_clinical_asset and mp > 0.50:
        scores["modality_platform_scarcity"] = 0.50
        caps.append(Cap(
            name="platform_unvalidated_mp_cap",
            cap_value=0.50,
            reason="Platform unvalidated with no clinical asset caps modality_platform_scarcity at 0.50",
            triggered_by="platform_unvalidated_no_clinical_asset=True",
        ))

    raw = sum(scores[k] * _SS_WEIGHTS[k] for k in _SS_WEIGHTS)
    confidence = _group_confidence(len(field_names), len(missing))
    score = _clamp(raw)

    return Layer1StrategicScarcity(
        ta_scarcity=_sub_component("ta_scarcity", scores, missing, confidence),
        modality_platform_scarcity=_sub_component("modality_platform_scarcity", scores, missing, confidence),
        competitive_position=_sub_component("competitive_position", scores, missing, confidence),
        pipeline_gap_relevance=_sub_component("pipeline_gap_relevance", scores, missing, confidence),
        franchise_optionality=_sub_component("franchise_optionality", scores, missing, confidence),
        replacement_difficulty=_sub_component("replacement_difficulty", scores, missing, confidence),
        score=round(score, 6),
        confidence=round(confidence, 6),
        caps=caps,
    )


def _score_value_creation(
    inputs: Layer1ValueCreationInputs,
    asset_quality_score: float,
) -> Layer1ValueCreation:
    """Compute Value Creation score (20% of Layer 1).

    Value-trap guard: if asset_quality_score < 0.50, premium_adjusted_rnpv_gap
    contribution is zeroed — cheapness cannot rescue broken science.
    """
    field_names = list(_VC_WEIGHTS.keys())
    scores: dict[str, float] = {}
    missing: list[str] = []
    for f in field_names:
        v, is_missing = _resolve(getattr(inputs, f))
        scores[f] = v
        if is_missing:
            missing.append(f)

    caps: list[Cap] = []
    value_trap_flags: list[str] = []

    # Market data staleness cap
    mkt = scores["market_expectations_gap"]
    if inputs.market_data_stale_or_illiquid and mkt > 0.50:
        scores["market_expectations_gap"] = 0.50
        caps.append(Cap(
            name="stale_market_data_mkt_cap",
            cap_value=0.50,
            reason="Market data stale or illiquid caps market_expectations_gap at 0.50",
            triggered_by="market_data_stale_or_illiquid=True",
        ))

    # Value-trap guard: cheapness does not rescue low asset quality
    gap = scores["premium_adjusted_rnpv_gap"]
    if asset_quality_score < 0.50 and gap > _NEUTRAL:
        scores["premium_adjusted_rnpv_gap"] = _NEUTRAL
        value_trap_flags.append("cheapness_not_allowed_to_rescue_low_asset_quality")
        caps.append(Cap(
            name="value_trap_gap_zero",
            cap_value=_NEUTRAL,
            reason=(
                f"asset_quality={asset_quality_score:.2f} < 0.50: "
                "premium_adjusted_rnpv_gap clamped to neutral — "
                "cheapness does not rescue low-quality assets"
            ),
            triggered_by="asset_quality<0.50",
        ))

    # Market expectations gap also zeroed for low quality
    mkt_gap = scores["market_expectations_gap"]
    if asset_quality_score < 0.50 and mkt_gap > _NEUTRAL:
        scores["market_expectations_gap"] = _NEUTRAL
        if "cheapness_not_allowed_to_rescue_low_asset_quality" not in value_trap_flags:
            value_trap_flags.append("cheapness_not_allowed_to_rescue_low_asset_quality")

    raw = sum(scores[k] * _VC_WEIGHTS[k] for k in _VC_WEIGHTS)
    confidence = _group_confidence(len(field_names), len(missing))
    score = _clamp(raw)

    return Layer1ValueCreation(
        premium_adjusted_rnpv_gap=_sub_component("premium_adjusted_rnpv_gap", scores, missing, confidence),
        standalone_rnpv_quality=_sub_component("standalone_rnpv_quality", scores, missing, confidence),
        downside_protection=_sub_component("downside_protection", scores, missing, confidence),
        cost_to_complete=_sub_component("cost_to_complete", scores, missing, confidence),
        market_expectations_gap=_sub_component("market_expectations_gap", scores, missing, confidence),
        strategic_option_value=_sub_component("strategic_option_value", scores, missing, confidence),
        score=round(score, 6),
        confidence=round(confidence, 6),
        value_trap_flags=value_trap_flags,
        caps=caps,
    )


def _score_transaction_setup(
    inputs: Layer1TransactionSetupInputs,
) -> Layer1TransactionSetup:
    """Compute Transaction Setup score (15% of Layer 1)."""
    field_names = list(_TS_WEIGHTS.keys())
    scores: dict[str, float] = {}
    missing: list[str] = []
    for f in field_names:
        v, is_missing = _resolve(getattr(inputs, f))
        scores[f] = v
        if is_missing:
            missing.append(f)

    caps: list[Cap] = []

    # Seller openness caps
    so = scores["seller_openness"]
    if inputs.founder_controlled_no_pressure and so > 0.45:
        scores["seller_openness"] = 0.45
        caps.append(Cap(
            name="founder_controlled_so_cap",
            cap_value=0.45,
            reason="Founder-controlled with no pressure caps seller_openness at 0.45",
            triggered_by="founder_controlled_no_pressure=True",
        ))
    elif inputs.management_committed_independence_well_funded and so > 0.40:
        scores["seller_openness"] = 0.40
        caps.append(Cap(
            name="management_independence_so_cap",
            cap_value=0.40,
            reason="Management committed to independence and well-funded caps seller_openness at 0.40",
            triggered_by="management_committed_independence_well_funded=True",
        ))

    # Valuation stress guard: stress due to asset failure should not inflate setup
    vs = scores["valuation_stress"]
    if inputs.valuation_stress_due_to_asset_failure and vs > _NEUTRAL:
        scores["valuation_stress"] = _NEUTRAL
        caps.append(Cap(
            name="valuation_stress_asset_failure_guard",
            cap_value=_NEUTRAL,
            reason="Valuation stress is due to asset failure, not dislocation; clamped to neutral",
            triggered_by="valuation_stress_due_to_asset_failure=True",
        ))

    raw = sum(scores[k] * _TS_WEIGHTS[k] for k in _TS_WEIGHTS)
    confidence = _group_confidence(len(field_names), len(missing))
    score = _clamp(raw)

    return Layer1TransactionSetup(
        financing_pressure=_sub_component("financing_pressure", scores, missing, confidence),
        catalyst_proximity=_sub_component("catalyst_proximity", scores, missing, confidence),
        seller_openness=_sub_component("seller_openness", scores, missing, confidence),
        valuation_stress=_sub_component("valuation_stress", scores, missing, confidence),
        prior_bd_activity=_sub_component("prior_bd_activity", scores, missing, confidence),
        score=round(score, 6),
        confidence=round(confidence, 6),
        caps=caps,
    )


def _score_structural_cleanliness(
    inputs: Layer1StructuralCleanlinessInputs,
) -> Layer1StructuralCleanliness:
    """Compute Structural Cleanliness score (5% of Layer 1)."""
    field_names = list(_SC_WEIGHTS.keys())
    scores: dict[str, float] = {}
    missing: list[str] = []
    for f in field_names:
        v, is_missing = _resolve(getattr(inputs, f))
        scores[f] = v
        if is_missing:
            missing.append(f)

    raw = sum(scores[k] * _SC_WEIGHTS[k] for k in _SC_WEIGHTS)
    confidence = _group_confidence(len(field_names), len(missing))
    score = _clamp(raw)

    return Layer1StructuralCleanliness(
        rights_clarity=_sub_component("rights_clarity", scores, missing, confidence),
        ip_cleanliness=_sub_component("ip_cleanliness", scores, missing, confidence),
        economic_control=_sub_component("economic_control", scores, missing, confidence),
        diligence_readiness=_sub_component("diligence_readiness", scores, missing, confidence),
        manufacturing_transferability=_sub_component("manufacturing_transferability", scores, missing, confidence),
        score=round(score, 6),
        confidence=round(confidence, 6),
        caps=[],
    )


# ---------------------------------------------------------------------------
# Composite cap logic
# ---------------------------------------------------------------------------

def _apply_composite_caps(
    raw_score: float,
    aq: Layer1AssetQuality,
    ss: Layer1StrategicScarcity,
    vc: Layer1ValueCreation,
    ts: Layer1TransactionSetup,
    sc: Layer1StructuralCleanliness,
) -> tuple[float, list[Cap]]:
    """Apply Layer 1 composite-level caps.

    Caps only apply to issues Layer 1 owns. No buyer-specific caps here.
    Returns (capped_score, triggered_caps).
    """
    capped = raw_score
    triggered: list[Cap] = []

    def _maybe_cap(name: str, cap_val: float, reason: str, triggered_by: str) -> None:
        nonlocal capped
        if capped > cap_val:
            capped = cap_val
            triggered.append(Cap(name=name, cap_value=cap_val, reason=reason, triggered_by=triggered_by))

    # Asset quality caps
    if aq.clinical_evidence.score < 0.35:
        _maybe_cap(
            "composite_low_clinical_evidence",
            0.55,
            f"clinical_evidence={aq.clinical_evidence.score:.2f} < 0.35",
            "clinical_evidence<0.35",
        )
    if aq.score < 0.45:
        _maybe_cap(
            "composite_low_asset_quality",
            0.50,
            f"asset_quality={aq.score:.2f} < 0.45",
            "asset_quality<0.45",
        )
    if aq.differentiation.score < 0.35 and aq.commercial_meaningfulness.score < 0.50:
        _maybe_cap(
            "composite_no_differentiation_or_commercial",
            0.55,
            (
                f"differentiation={aq.differentiation.score:.2f} < 0.35 "
                f"AND commercial_meaningfulness={aq.commercial_meaningfulness.score:.2f} < 0.50"
            ),
            "differentiation<0.35_and_commercial_meaningfulness<0.50",
        )
    if aq.regulatory_path.score < 0.35:
        _maybe_cap(
            "composite_low_regulatory_path",
            0.55,
            f"regulatory_path={aq.regulatory_path.score:.2f} < 0.35",
            "regulatory_path<0.35",
        )
    if aq.ip_exclusivity.score < 0.35:
        _maybe_cap(
            "composite_low_ip_exclusivity",
            0.60,
            f"ip_exclusivity={aq.ip_exclusivity.score:.2f} < 0.35",
            "ip_exclusivity<0.35",
        )

    # Value-trap caps (cross-group)
    fp = ts.financing_pressure.score
    vs = ts.valuation_stress.score

    if aq.score < 0.50 and vs > 0.70:
        _maybe_cap(
            "composite_value_trap_stress",
            0.50,
            (
                f"asset_quality={aq.score:.2f} < 0.50 AND "
                f"valuation_stress={vs:.2f} > 0.70: distress without quality"
            ),
            "asset_quality<0.50_and_valuation_stress>0.70",
        )
    if fp > 0.70 and aq.score < 0.50:
        _maybe_cap(
            "composite_value_trap_financing",
            0.45,
            (
                f"financing_pressure={fp:.2f} > 0.70 AND "
                f"asset_quality={aq.score:.2f} < 0.50: distress without quality"
            ),
            "financing_pressure>0.70_and_asset_quality<0.50",
        )

    # Strategic scarcity cap
    if ss.score < 0.35:
        _maybe_cap(
            "composite_low_strategic_scarcity",
            0.60,
            f"strategic_scarcity={ss.score:.2f} < 0.35",
            "strategic_scarcity<0.35",
        )

    # Structural cleanliness cap (light — only 5% weight, but hard floor)
    if sc.score < 0.35:
        _maybe_cap(
            "composite_low_structural_cleanliness",
            0.65,
            f"structural_cleanliness={sc.score:.2f} < 0.35",
            "structural_cleanliness<0.35",
        )

    return round(_clamp(capped), 6), triggered


# ---------------------------------------------------------------------------
# Thesis classifier
# ---------------------------------------------------------------------------

def _classify_thesis(
    aq: Layer1AssetQuality,
    ss: Layer1StrategicScarcity,
    vc: Layer1ValueCreation,
    ts: Layer1TransactionSetup,
    sc: Layer1StructuralCleanliness,
    capped_score: float,
) -> tuple[str, str]:
    """Return (thesis_type, plain_english_verdict) from Layer 1 vector."""
    aq_s = aq.score
    ss_s = ss.score
    vc_s = vc.score
    ts_s = ts.score
    sc_s = sc.score
    fp_s = ts.financing_pressure.score
    vs_s = ts.valuation_stress.score
    fo_s = ss.franchise_optionality.score
    ce_s = aq.clinical_evidence.score
    is_value_trap = len(vc.value_trap_flags) > 0

    if aq_s >= 0.75 and ss_s >= 0.70 and vc_s >= 0.60:
        return (
            "high_quality_strategically_scarce",
            (
                f"This is a high-quality, strategically scarce asset with credible value creation. "
                f"Asset quality ({aq_s:.2f}), strategic scarcity ({ss_s:.2f}), and value creation "
                f"({vc_s:.2f}) are all strong, making this a compelling BD target. "
                f"{'Transaction setup is also favorable. ' if ts_s >= 0.50 else ''}"
                f"Structural cleanliness is {'clean' if sc_s >= 0.65 else 'acceptable' if sc_s >= 0.45 else 'complex'}."
            ),
        )

    if aq_s < 0.50 and (is_value_trap or vs_s > 0.70):
        return (
            "cheap_but_low_quality_value_trap",
            (
                f"This asset appears cheap or distressed, but asset quality is too weak "
                f"(score={aq_s:.2f}) to justify an acquisition premium. "
                "Score is capped as a value trap. "
                "Cheapness does not rescue broken or unvalidated science."
            ),
        )

    if aq_s >= 0.75 and ss_s >= 0.65 and ts_s < 0.40:
        return (
            "great_asset_not_yet_actionable",
            (
                f"Strong asset quality ({aq_s:.2f}) and strategic scarcity ({ss_s:.2f}), "
                f"but limited transaction setup today (setup={ts_s:.2f}). "
                "Better treated as strategic radar rather than active pursuit at this time. "
                "Revisit when financing pressure or catalyst proximity increases."
            ),
        )

    if ss_s >= 0.75 and vc_s < 0.45:
        return (
            "scarce_asset_weak_value_creation",
            (
                f"Strategically scarce asset (scarcity={ss_s:.2f}) but value creation economics "
                f"are insufficient ({vc_s:.2f}). "
                "Scarcity alone is not sufficient for a premium acquisition without viable economics. "
                "Consider option or partnership structures."
            ),
        )

    if fp_s >= 0.70 and aq_s >= 0.60:
        return (
            "distressed_but_viable",
            (
                f"Meaningful financing pressure ({fp_s:.2f}) combined with solid asset quality "
                f"({aq_s:.2f}). The combination of distress and asset value creates near-term BD opportunity. "
                "Act before a forced financing or dilutive event occurs."
            ),
        )

    if fo_s >= 0.75 and ce_s < 0.60:
        return (
            "platform_optionality_case",
            (
                f"Strong franchise / platform optionality ({fo_s:.2f}) with still-maturing clinical "
                f"evidence ({ce_s:.2f}). BD interest likely centers on platform potential, not the lead "
                "asset alone. Consider option or co-development structures."
            ),
        )

    if sc_s < 0.45 and aq_s >= 0.65:
        return (
            "structurally_messy_but_interesting",
            (
                f"Good asset quality ({aq_s:.2f}) but structural complexity is elevated "
                f"(structural cleanliness={sc_s:.2f}). "
                "Rights, IP, or economic structure issues add deal risk and cost. "
                "Asset is interesting but requires structural resolution before active pursuit."
            ),
        )

    if capped_score < 0.45:
        return (
            "low_priority_pass",
            (
                f"Layer 1 score is below minimum threshold ({capped_score:.2f}). "
                "This target does not currently meet the BD minimum bar. "
                "Monitor for material improvement in asset quality or transaction setup."
            ),
        )

    return (
        "moderate_interest",
        (
            f"Moderate BD interest: asset quality={aq_s:.2f}, scarcity={ss_s:.2f}, "
            f"value creation={vc_s:.2f}, transaction setup={ts_s:.2f}. "
            "No single signal is strong enough to drive immediate action. "
            "Monitor and revisit after the next clinical or financing catalyst."
        ),
    )


# ---------------------------------------------------------------------------
# Narrative helpers
# ---------------------------------------------------------------------------

def _build_drivers(
    aq: Layer1AssetQuality,
    ss: Layer1StrategicScarcity,
    vc: Layer1ValueCreation,
    ts: Layer1TransactionSetup,
    sc: Layer1StructuralCleanliness,
) -> tuple[list[str], list[str]]:
    """Return (top_positive_drivers, top_negative_drivers)."""
    positives: list[str] = []
    negatives: list[str] = []

    # Asset quality
    if aq.clinical_evidence.score >= 0.75:
        positives.append(f"Strong clinical evidence ({aq.clinical_evidence.score:.2f})")
    elif aq.clinical_evidence.score < 0.40:
        negatives.append(f"Weak clinical evidence ({aq.clinical_evidence.score:.2f})")

    if aq.differentiation.score >= 0.75:
        positives.append(f"Clear differentiation vs SoC ({aq.differentiation.score:.2f})")
    elif aq.differentiation.score < 0.40:
        negatives.append(f"Insufficient differentiation ({aq.differentiation.score:.2f})")

    if aq.ip_exclusivity.score >= 0.70:
        positives.append(f"Strong IP/exclusivity ({aq.ip_exclusivity.score:.2f})")
    elif aq.ip_exclusivity.score < 0.40:
        negatives.append(f"Weak IP/exclusivity runway ({aq.ip_exclusivity.score:.2f})")

    # Strategic scarcity
    if ss.ta_scarcity.score >= 0.75:
        positives.append(f"Hot therapeutic area with scarce assets ({ss.ta_scarcity.score:.2f})")
    elif ss.ta_scarcity.score < 0.35:
        negatives.append(f"Limited TA deal demand ({ss.ta_scarcity.score:.2f})")

    if ss.replacement_difficulty.score >= 0.75:
        positives.append(f"Hard to replace or recreate ({ss.replacement_difficulty.score:.2f})")

    # Value creation
    if vc.premium_adjusted_rnpv_gap.score >= 0.75:
        positives.append(f"Attractive value creation gap ({vc.premium_adjusted_rnpv_gap.score:.2f})")
    elif vc.premium_adjusted_rnpv_gap.score < 0.35:
        negatives.append(f"Limited value creation at current pricing ({vc.premium_adjusted_rnpv_gap.score:.2f})")

    if len(vc.value_trap_flags) > 0:
        negatives.append("Value trap: cheapness flagged, does not rescue asset quality")

    # Transaction setup
    if ts.financing_pressure.score >= 0.70:
        positives.append(f"Significant financing pressure motivating seller ({ts.financing_pressure.score:.2f})")
    if ts.catalyst_proximity.score >= 0.70:
        positives.append(f"Near-term catalyst proximity ({ts.catalyst_proximity.score:.2f})")
    if ts.seller_openness.score < 0.30:
        negatives.append(f"Low seller openness signals ({ts.seller_openness.score:.2f})")

    # Structural
    if sc.rights_clarity.score < 0.40:
        negatives.append(f"Rights complexity ({sc.rights_clarity.score:.2f}) adds deal friction")

    return positives[:5], negatives[:5]


def _build_missing_data(
    aq: Layer1AssetQuality,
    ss: Layer1StrategicScarcity,
    vc: Layer1ValueCreation,
    ts: Layer1TransactionSetup,
    sc: Layer1StructuralCleanliness,
) -> list[str]:
    missing: list[str] = []
    for group_name, group in [
        ("asset_quality", aq),
        ("strategic_scarcity", ss),
        ("value_creation", vc),
        ("transaction_setup", ts),
        ("structural_cleanliness", sc),
    ]:
        # Use type().model_fields to avoid Pydantic 2.11 deprecation on instances
        for field in type(group).model_fields.keys():
            val = getattr(group, field)
            if isinstance(val, ScoreComponent) and field in val.missing_data:
                missing.append(f"{group_name}.{field}")
    return missing


def _build_diligence_questions(
    aq: Layer1AssetQuality,
    vc: Layer1ValueCreationInputs,
    sc: Layer1StructuralCleanliness,
) -> list[str]:
    questions: list[str] = [
        "What is the complete IP landscape including all patent expiry dates and litigation history?",
        "Are there any undisclosed co-development agreements, ROFR clauses, or sublicensing rights?",
        "What is the projected cost-to-complete for each active clinical program?",
        "What are the key regulatory risks including any prior FDA/EMA feedback or clinical holds?",
        "What is the CMC readiness for commercial-scale manufacturing post-approval?",
    ]
    if aq.clinical_evidence.score < 0.60:
        questions.append(
            "Can the clinical data package be audited for completeness? "
            "What is the quality of the primary efficacy and safety dataset?"
        )
    if vc.premium_adjusted_rnpv_gap_raw < 50.0:
        questions.append(
            "What is management's view on pricing flexibility? "
            "Would earn-out, CVR, or milestone-heavy structures be acceptable?"
        )
    if sc.rights_clarity.score < 0.60:
        questions.append(
            "What is the complete rights table for each indication and geography? "
            "Are any ROFR, co-development consent, or change-of-control provisions present?"
        )
    return questions


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_layer1_strategic_attractiveness(inputs: Layer1Inputs) -> Layer1Output:
    """Compute the full Layer 1 Strategic Attractiveness score.

    This is the institutional-grade target-level attractiveness engine.
    It does NOT incorporate buyer-specific signals (affordability, integration,
    ROFR, antitrust) — those belong in Layer 3.

    Steps:
    1. Score each of the five sub-groups independently.
    2. Compute raw weighted composite.
    3. Apply composite-level caps.
    4. Compute overall confidence and apply confidence multiplier.
    5. Classify thesis type and generate plain-English verdict.
    6. Collect narrative, missing data, and diligence questions.
    """
    # Step 1: Score sub-groups
    aq = _score_asset_quality(inputs.asset_quality)
    ss = _score_strategic_scarcity(inputs.strategic_scarcity)
    vc = _score_value_creation(inputs.value_creation, asset_quality_score=aq.score)
    ts = _score_transaction_setup(inputs.transaction_setup)
    sc = _score_structural_cleanliness(inputs.structural_cleanliness)

    # Step 2: Raw composite
    raw_score = round(_clamp(
        aq.score * L1_WEIGHTS["asset_quality"]
        + ss.score * L1_WEIGHTS["strategic_scarcity"]
        + vc.score * L1_WEIGHTS["value_creation"]
        + ts.score * L1_WEIGHTS["transaction_setup"]
        + sc.score * L1_WEIGHTS["structural_cleanliness"]
    ), 6)

    # Step 3: Composite caps
    capped_score, composite_caps = _apply_composite_caps(raw_score, aq, ss, vc, ts, sc)

    # Aggregate all active caps
    all_caps: list[Cap] = (
        list(aq.caps) + list(ss.caps) + list(vc.caps)
        + list(ts.caps) + list(sc.caps)
        + composite_caps
    )

    # Step 4: Overall confidence and multiplier
    overall_confidence = round(_clamp(
        aq.confidence * L1_WEIGHTS["asset_quality"]
        + ss.confidence * L1_WEIGHTS["strategic_scarcity"]
        + vc.confidence * L1_WEIGHTS["value_creation"]
        + ts.confidence * L1_WEIGHTS["transaction_setup"]
        + sc.confidence * L1_WEIGHTS["structural_cleanliness"]
    ), 6)
    multiplier = _confidence_multiplier(overall_confidence)
    confidence_adjusted_score = round(_clamp(capped_score * multiplier), 6)
    low_confidence_flag = overall_confidence < 0.40

    # Step 5: Thesis and verdict
    thesis_type, plain_english_verdict = _classify_thesis(aq, ss, vc, ts, sc, capped_score)

    # Step 6: Narrative
    top_pos, top_neg = _build_drivers(aq, ss, vc, ts, sc)
    missing_data = _build_missing_data(aq, ss, vc, ts, sc)
    diligence = _build_diligence_questions(aq, inputs.value_creation, sc)

    return Layer1Output(
        asset_quality=aq,
        strategic_scarcity=ss,
        value_creation=vc,
        transaction_setup=ts,
        structural_cleanliness=sc,
        raw_score=raw_score,
        capped_score=capped_score,
        confidence_adjusted_score=confidence_adjusted_score,
        overall_confidence=overall_confidence,
        confidence_multiplier=round(multiplier, 6),
        active_caps=all_caps,
        top_positive_drivers=top_pos,
        top_negative_drivers=top_neg,
        missing_data=missing_data,
        diligence_questions=diligence,
        thesis_type=thesis_type,
        plain_english_verdict=plain_english_verdict,
        anti_double_counting_notes=ANTI_DOUBLE_COUNTING_NOTES,
        low_confidence_diligence_queue=low_confidence_flag,
    )
