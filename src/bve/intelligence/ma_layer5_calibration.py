"""
Layer 5 — Calibration, Confidence, and Explainability Overlay.

Converts the post-gate BD action score (from Layer 3) into a time-bounded,
confidence-adjusted probability estimate with uncertainty quantification,
calibration cohort identification, reason-code explainability, and
rank-vs-probability divergence diagnostics.

Key design principles:
  • The gated BD score remains the primary ranking signal. Calibration
    adds interpretability; it does not reorder the universe.
  • p_takeout_12m is a shrinkage blend of three components:
      base_rate           — historical TA/stage M&A base rate
      logistic_probability — calibrated score-to-probability mapping
      comparable_bucket_rate — historical rate for similar deal setups
    When sample size is small, base-rate weight increases; when large,
    the logistic probability is trusted more.
  • Probabilities are presented with bands to prevent false precision.
    Low-confidence observations show bands only; VERY_LOW is excluded.
  • Rank-vs-probability divergence flags surface when strategic ranking
    and calibrated probability materially disagree.
  • All gate codes and driver signals are translated into plain-English
    reason strings to make the output decision-useful without consulting
    upstream layer documentation.

Calibration cohorts (from Layer 4 watchlist class):
  process_ready      → High-readiness targets
  active_pursuit     → Active-setup targets
  catalyst_watch     → Catalyst-driven targets
  relationship_build → Relationship-stage targets
  strategic_radar    → Strategic-radar targets
  data_insufficient  → Excluded from calibrated output
  pass               → Excluded from calibration

Time windows:
  p_takeout_6m  ≈ p_takeout_12m × 0.55   (hazard-rate scaling)
  p_takeout_18m ≈ 1 − (1 − p_12m)^1.35  (survival function scaling)
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Logistic transform: maps bd_action_score → pseudo-logistic probability.
# Calibrated so that:
#   rank_score 0.35 (pass territory)   → logistic ≈ 0.07
#   rank_score 0.55 (strategic watch)  → logistic ≈ 0.26
#   rank_score 0.70 (active pursuit)   → logistic ≈ 0.54
#   rank_score 0.80 (process ready)    → logistic ≈ 0.72
_LOGISTIC_SLOPE: float = 8.0
_LOGISTIC_MIDPOINT: float = 0.68

# Shrinkage weight tiers: (base_rate_weight, logistic_weight, bucket_weight)
_SHRINKAGE_SMALL: tuple[float, float, float] = (0.60, 0.20, 0.20)     # n < 10
_SHRINKAGE_MODERATE: tuple[float, float, float] = (0.50, 0.30, 0.20)  # 10 ≤ n < 20
_SHRINKAGE_STANDARD: tuple[float, float, float] = (0.40, 0.40, 0.20)  # 20 ≤ n < 30
_SHRINKAGE_LARGE: tuple[float, float, float] = (0.30, 0.50, 0.20)     # n ≥ 30

_SHRINKAGE_SMALL_N: int = 10
_SHRINKAGE_MODERATE_N: int = 20
_SHRINKAGE_STANDARD_N: int = 30

# Time-window scaling
_SCALE_6M: float = 0.55
_SCALE_18M_EXPONENT: float = 1.35  # survival: 1 − (1 − p12m)^exponent

# Probability band thresholds (exclusive upper bound)
_BAND_VERY_LOW_MAX: float = 0.05
_BAND_LOW_MAX: float = 0.15
_BAND_MODERATE_MAX: float = 0.30
_BAND_HIGH_MAX: float = 0.50

# Divergence flag thresholds (from 5F)
_DIVERGENCE_HIGH_PERCENTILE: float = 0.85
_DIVERGENCE_LOW_PROB: float = 0.10
_DIVERGENCE_LOW_PERCENTILE: float = 0.50
_DIVERGENCE_HIGH_PROB: float = 0.25

# Confidence level thresholds
_HIGH_CONFIDENCE_DATA_MIN: float = 0.85
_HIGH_CONFIDENCE_N_MIN: int = 20
_MEDIUM_CONFIDENCE_DATA_MIN: float = 0.65
_MEDIUM_CONFIDENCE_N_MIN: int = 10
_LOW_CONFIDENCE_DATA_MIN: float = 0.50

# Relative uncertainty width by confidence
_RANGE_WIDTH: dict[str, float] = {
    "high": 0.30,
    "medium": 0.50,
    "low": 0.75,
    "very_low": 1.00,
}

# Human-readable calibration cohorts
_CALIBRATION_COHORTS: dict[str, str] = {
    "process_ready": "High-readiness targets (≥2 drivers, seller willing)",
    "active_pursuit": "Active-setup targets (2+ transaction drivers)",
    "catalyst_watch": "Catalyst-driven targets (event within 180 days)",
    "relationship_build": "Relationship-stage targets (management not engaged)",
    "strategic_radar": "Strategic-radar targets (no near-term urgency)",
    "data_insufficient": "Data-limited targets (excluded from calibrated output)",
    "pass": "Excluded from calibration",
}

# Gate-to-negative-driver translations
_GATE_DESCRIPTIONS: dict[str, str] = {
    "G1": "Broken asset — clinical quality below acceptance threshold",
    "G2": "No right-to-win — acquirer strategic fit insufficient",
    "G3": "No transaction rationale — zero active driver buckets",
    "G4": "Weak transaction setup — insufficient driver strength",
    "G5": "Seller not ready — no active engagement or process signal",
    "G6": "Capital pressure without quality — distress alone is not a deal thesis",
    "G7": "Encumbrance — rights or control issues block full acquisition",
    "G8": "Deal feasibility — affordability, antitrust, or integration risk",
}

# Gate-to-change-suggestion translations
_GATE_CHANGE_SUGGESTIONS: dict[str, str] = {
    "G5": "Seller engages banker or board announces strategic review",
    "G3": "Capital pressure materialises or deal wave intensifies in TA",
    "G4": "Second transaction driver activates (catalyst, activist, or deal pressure)",
    "G2": "Acquirer reshapes pipeline gap via internal program failure or LoE",
    "G7": "Rights encumbrance resolved via partner buyout or contract amendment",
    "G8": "Deal structure modified to improve affordability (option vs full acquisition)",
    "G1": "Clinical milestone achieved that substantially upgrades asset quality",
    "G6": "Asset quality score improves above 0.50 on additional clinical evidence",
}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class ProbabilityBand(str, Enum):
    VERY_LOW = "Very low"
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    EXCEPTIONAL = "Exceptional / requires manual review"


# ---------------------------------------------------------------------------
# Input / Output models
# ---------------------------------------------------------------------------

class Layer5Inputs(BaseModel):
    """Flat input model for the Layer 5 calibration overlay.

    Sources:
      Layer 1: asset_quality, seller_willingness
      Layer 2: strategic_priority, transaction_probability
      Layer 3: rank_score (post-gate), rank_percentile, active_driver_bucket_count,
               active_gate_ids, input_positive_drivers, input_negative_drivers
      Layer 4: watchlist_class, data_confidence_score, input_what_would_change
    """
    model_config = ConfigDict(frozen=True)

    # BD signal inputs
    rank_score: float = Field(..., ge=0.0, le=1.0,
        description="Post-gate BD action score (Layer 3 final_score)")
    rank_percentile: float = Field(..., ge=0.0, le=1.0,
        description="Percentile within current scored universe (0=lowest, 1=highest)")
    strategic_priority: float = Field(..., ge=0.0, le=1.0,
        description="Layer 2 strategic priority score")
    transaction_probability: float = Field(..., ge=0.0, le=1.0,
        description="Layer 2 transaction probability (= transaction readiness)")
    asset_quality: float = Field(..., ge=0.0, le=1.0,
        description="Layer 1 asset quality score")
    seller_willingness: float = Field(..., ge=0.0, le=1.0,
        description="Layer 1 seller willingness score")
    active_driver_bucket_count: int = Field(default=0, ge=0,
        description="Number of active transaction driver buckets (Layer 3)")
    active_gate_ids: list[str] = Field(default_factory=list,
        description="Gate IDs that triggered in Layer 3 (e.g. ['G2', 'G5'])")
    watchlist_class: str = Field(default="strategic_radar",
        description="Layer 4 watchlist classification string")
    data_confidence_score: float = Field(default=1.0, ge=0.0, le=1.0,
        description="Data completeness/confidence score (from Layer 4)")

    # Calibration components
    base_rate: float = Field(default=0.08, ge=0.0, le=1.0,
        description="Historical 12m M&A base rate for this TA/stage combination")
    comparable_bucket_rate: float = Field(default=0.12, ge=0.0, le=1.0,
        description="Historical 12m takeout rate for comparable deal setups")
    n_comparable_observations: int = Field(default=5, ge=0,
        description="Number of similar historical target-acquirer-date observations")
    logistic_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Fitted logistic model output; derived from rank_score when None")

    # Explainability inputs (passed from Layer 3/4)
    input_positive_drivers: list[str] = Field(default_factory=list,
        description="Active transaction driver names from Layer 3")
    input_negative_drivers: list[str] = Field(default_factory=list,
        description="Reason codes from Layer 3/4 explaining score suppression")
    input_what_would_change: list[str] = Field(default_factory=list,
        description="Promotion triggers from Layer 4 (events that would move class up)")
    input_data_gaps: list[str] = Field(default_factory=list,
        description="Known diligence gaps from Layer 4")

    # Deal value (optional, passed through for output table)
    estimated_deal_value_low_millions: Optional[float] = Field(default=None)
    estimated_deal_value_high_millions: Optional[float] = Field(default=None)

    # Metadata
    as_of_date: str = Field(default="",
        description="ISO date string for this observation (YYYY-MM-DD)")
    model_version: str = Field(default="v1.0",
        description="Model version for auditability")
    target_name: str = Field(default="Unknown")
    acquirer_id: Optional[str] = Field(default=None)


class Layer5Output(BaseModel):
    """Full Layer 5 calibration, confidence, and explainability overlay output."""
    model_config = ConfigDict(frozen=True)

    target_name: str
    acquirer_id: Optional[str]

    # Primary probability outputs (spec fields)
    rank_score: float = Field(..., description="Primary ranking score (unchanged from Layer 3)")
    p_takeout_12m: float = Field(..., ge=0.0, le=1.0,
        description="Calibrated 12-month takeout probability")
    p_takeout_6m: float = Field(..., ge=0.0, le=1.0,
        description="Calibrated 6-month takeout probability")
    p_takeout_18m: float = Field(..., ge=0.0, le=1.0,
        description="Calibrated 18-month takeout probability")
    probability_band: str = Field(...,
        description="Probability tier: Very low / Low / Moderate / High / Exceptional")
    probability_range_low: float = Field(..., ge=0.0, le=1.0,
        description="Lower bound of probability uncertainty range")
    probability_range_high: float = Field(..., ge=0.0, le=1.0,
        description="Upper bound of probability uncertainty range")
    confidence_level: str = Field(...,
        description="Classification confidence: high / medium / low / very_low")
    calibration_cohort: str = Field(...,
        description="Historical bucket used for comparable-rate calibration")

    # Explainability (spec fields)
    top_positive_drivers: list[str] = Field(...,
        description="Signals supporting the score")
    top_negative_drivers: list[str] = Field(...,
        description="Signals capping the score (gate codes translated to plain English)")
    what_would_change_score: list[str] = Field(...,
        description="Events that would materially raise the score")
    data_gaps: list[str] = Field(...,
        description="Known diligence gaps that reduce confidence")

    # Divergence diagnostic (spec 5F)
    rank_probability_divergence_flag: Optional[str] = Field(default=None,
        description="Set when rank and calibrated probability materially disagree")

    # Display helpers
    display_probability: str = Field(...,
        description="Human-readable probability string that respects confidence level")

    # Deal value (pass-through for output table)
    estimated_deal_value_low_millions: Optional[float]
    estimated_deal_value_high_millions: Optional[float]

    # Calibration internals (for auditability)
    logistic_probability_used: float = Field(...,
        description="Logistic probability value used in the shrinkage blend")
    shrinkage_weights: tuple[float, float, float] = Field(...,
        description="(base_rate_weight, logistic_weight, bucket_weight) used")

    # Metadata
    as_of_date: str
    model_version: str
    interpretation: str


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def _expit(x: float) -> float:
    """Numerically stable logistic sigmoid."""
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _derive_logistic_probability(rank_score: float) -> float:
    """Map rank_score to a calibrated logistic probability via sigmoid transform."""
    return round(_expit(_LOGISTIC_SLOPE * (rank_score - _LOGISTIC_MIDPOINT)), 6)


def _shrinkage_weights(n: int) -> tuple[float, float, float]:
    """Return (base_rate_weight, logistic_weight, bucket_weight) for n observations.

    When sample size is small, base rates are weighted more heavily to prevent
    overfitting on limited comparable observations.
    """
    if n < _SHRINKAGE_SMALL_N:
        return _SHRINKAGE_SMALL
    if n < _SHRINKAGE_MODERATE_N:
        return _SHRINKAGE_MODERATE
    if n < _SHRINKAGE_STANDARD_N:
        return _SHRINKAGE_STANDARD
    return _SHRINKAGE_LARGE


def _compute_p12m(
    base_rate: float,
    logistic_prob: float,
    bucket_rate: float,
    weights: tuple[float, float, float],
) -> float:
    """Shrinkage-calibrated 12-month probability."""
    wb, wl, wk = weights
    p = wb * base_rate + wl * logistic_prob + wk * bucket_rate
    return round(min(max(p, 0.0), 1.0), 6)


def _compute_time_windows(p12m: float) -> tuple[float, float]:
    """Derive 6-month and 18-month probabilities from the 12-month estimate.

    p_6m  ≈ p_12m × 0.55  (hazard-rate scaling)
    p_18m ≈ 1 − (1 − p_12m)^1.35  (survival function)
    """
    p6m = round(min(max(p12m * _SCALE_6M, 0.0), 1.0), 6)
    p18m = round(min(max(1.0 - (1.0 - p12m) ** _SCALE_18M_EXPONENT, 0.0), 1.0), 6)
    return p6m, p18m


def _probability_band(p: float) -> ProbabilityBand:
    """Map calibrated probability to a descriptive band."""
    if p < _BAND_VERY_LOW_MAX:
        return ProbabilityBand.VERY_LOW
    if p < _BAND_LOW_MAX:
        return ProbabilityBand.LOW
    if p < _BAND_MODERATE_MAX:
        return ProbabilityBand.MODERATE
    if p < _BAND_HIGH_MAX:
        return ProbabilityBand.HIGH
    return ProbabilityBand.EXCEPTIONAL


def _confidence_level(inputs: Layer5Inputs) -> ConfidenceLevel:
    """Derive confidence level from data completeness and sample size.

    HIGH:    data_confidence ≥ 0.85 AND n_comparable ≥ 20
    MEDIUM:  data_confidence ≥ 0.65 OR n_comparable ≥ 10  (and not HIGH)
    LOW:     data_confidence ≥ 0.50  (and not MEDIUM or HIGH)
    VERY_LOW: data_confidence < 0.50
    """
    if inputs.data_confidence_score < _LOW_CONFIDENCE_DATA_MIN:
        return ConfidenceLevel.VERY_LOW

    if (
        inputs.data_confidence_score >= _HIGH_CONFIDENCE_DATA_MIN
        and inputs.n_comparable_observations >= _HIGH_CONFIDENCE_N_MIN
    ):
        return ConfidenceLevel.HIGH

    if (
        inputs.data_confidence_score >= _MEDIUM_CONFIDENCE_DATA_MIN
        or inputs.n_comparable_observations >= _MEDIUM_CONFIDENCE_N_MIN
    ):
        return ConfidenceLevel.MEDIUM

    return ConfidenceLevel.LOW


def _probability_range(p12m: float, confidence: ConfidenceLevel) -> tuple[float, float]:
    """Compute uncertainty range bounds scaled by confidence level.

    Width is relative to p_takeout_12m:
      HIGH:     ±30%
      MEDIUM:   ±50%
      LOW:      ±75%
      VERY_LOW: ±100%
    """
    w = _RANGE_WIDTH.get(confidence.value, 0.75)
    lo = round(max(0.0, p12m * (1.0 - w)), 4)
    hi = round(min(1.0, p12m * (1.0 + w)), 4)
    return lo, hi


def _divergence_flag(rank_percentile: float, p12m: float) -> Optional[str]:
    """Detect rank-vs-probability divergence (spec 5F).

    High rank + low probability: strategic fit is high but no transaction drivers.
    Low rank + high probability: transaction setup exists but target is low priority.
    """
    if rank_percentile > _DIVERGENCE_HIGH_PERCENTILE and p12m < _DIVERGENCE_LOW_PROB:
        return "strategic_fit_high_but_transaction_probability_low"
    if rank_percentile < _DIVERGENCE_LOW_PERCENTILE and p12m > _DIVERGENCE_HIGH_PROB:
        return "transaction_possible_but_low_strategic_priority"
    return None


def _calibration_cohort(watchlist_class: str) -> str:
    """Map Layer 4 watchlist class to a calibration cohort description."""
    return _CALIBRATION_COHORTS.get(watchlist_class, "Unclassified targets")


def _display_probability(
    p12m: float,
    band: ProbabilityBand,
    confidence: ConfidenceLevel,
) -> str:
    """Format the probability for display respecting confidence constraints.

    VERY_LOW → excluded text
    LOW      → band only (no numeric probability)
    MEDIUM   → approximate number + confidence marker
    HIGH     → precise number + confidence marker
    """
    if confidence == ConfidenceLevel.VERY_LOW:
        return "Insufficient data — excluded from calibrated output"
    if confidence == ConfidenceLevel.LOW:
        return f"Band: {band.value} (low confidence — probability range only)"
    pct = round(p12m * 100.0)
    if confidence == ConfidenceLevel.MEDIUM:
        return f"~{pct}% (Medium confidence)"
    return f"{pct}% (High confidence)"


def _build_negative_drivers(
    active_gate_ids: list[str],
    input_negative_drivers: list[str],
) -> list[str]:
    """Translate gate IDs to readable negative driver strings, then append extras."""
    drivers: list[str] = []
    seen: set[str] = set()
    for gate_id in active_gate_ids:
        desc = _GATE_DESCRIPTIONS.get(gate_id, f"Gate {gate_id} triggered")
        if desc not in seen:
            drivers.append(desc)
            seen.add(desc)
    for d in input_negative_drivers:
        if d not in seen:
            drivers.append(d)
            seen.add(d)
    return drivers


def _build_positive_drivers(
    input_positive_drivers: list[str],
    active_driver_bucket_count: int,
    strategic_priority: float,
    transaction_probability: float,
) -> list[str]:
    """Assemble positive driver strings from explicit inputs and score signals."""
    drivers: list[str] = list(input_positive_drivers)
    if not drivers:
        if strategic_priority >= 0.70:
            drivers.append(f"High strategic priority ({strategic_priority:.2f})")
        if transaction_probability >= 0.55:
            drivers.append(f"Elevated transaction probability ({transaction_probability:.2f})")
        if active_driver_bucket_count >= 2:
            drivers.append(f"{active_driver_bucket_count} active transaction driver buckets")
    return drivers


def _build_what_would_change(inputs: Layer5Inputs) -> list[str]:
    """Combine Layer 4 promotion triggers with gate-based improvement suggestions."""
    suggestions: list[str] = list(inputs.input_what_would_change)
    seen: set[str] = set(suggestions)
    for gate_id in inputs.active_gate_ids:
        suggestion = _GATE_CHANGE_SUGGESTIONS.get(gate_id)
        if suggestion and suggestion not in seen:
            suggestions.append(suggestion)
            seen.add(suggestion)
    return suggestions


def _build_data_gaps(inputs: Layer5Inputs) -> list[str]:
    """Return explicit data gaps or infer generic ones from confidence level."""
    if inputs.input_data_gaps:
        return list(inputs.input_data_gaps)
    confidence = _confidence_level(inputs)
    if confidence == ConfidenceLevel.VERY_LOW:
        return ["Complete diligence assessment required before classification"]
    if confidence == ConfidenceLevel.LOW:
        return [
            "Verify asset quality score with independent clinical review",
            "Confirm acquirer strategic fit assessment",
        ]
    if confidence == ConfidenceLevel.MEDIUM:
        return ["Confirm acquirer pipeline gap urgency", "Validate seller willingness signals"]
    return []


def _build_interpretation(
    target_name: str,
    p12m: float,
    band: ProbabilityBand,
    confidence: ConfidenceLevel,
    pos_drivers: list[str],
    neg_drivers: list[str],
    watchlist_class: str,
) -> str:
    """Compose a plain-English interpretation of the calibrated output."""
    parts: list[str] = []
    if confidence == ConfidenceLevel.VERY_LOW:
        parts.append(
            f"{target_name}: insufficient data — excluded from calibrated output."
        )
    else:
        pct = round(p12m * 100.0)
        parts.append(
            f"{target_name}: estimated 12-month takeout probability {pct}% "
            f"({band.value}, {confidence.value} confidence)."
        )
    if pos_drivers:
        parts.append(f"Supported by: {', '.join(pos_drivers[:3])}.")
    if neg_drivers:
        parts.append(f"Capped by: {', '.join(neg_drivers[:3])}.")
    parts.append(f"Watchlist class: {watchlist_class.replace('_', ' ')}.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_layer5(inputs: Layer5Inputs) -> Layer5Output:
    """Layer 5 Calibration, Confidence, and Explainability Overlay.

    Converts the post-gate BD action score into a time-bounded calibrated
    probability estimate with uncertainty bands, confidence classification,
    driver explainability, and rank-vs-probability divergence diagnostics.

    Args:
        inputs: Layer5Inputs with all scoring signals, calibration parameters,
                and optional explainability inputs from upstream layers.

    Returns:
        Layer5Output with p_takeout_6m/12m/18m, probability_band,
        probability_range, confidence_level, calibration_cohort,
        top_positive_drivers, top_negative_drivers, what_would_change_score,
        divergence_flag, display_probability, and interpretation.
    """
    # Step 1: logistic probability (explicit or derived)
    logistic_prob = (
        inputs.logistic_probability
        if inputs.logistic_probability is not None
        else _derive_logistic_probability(inputs.rank_score)
    )

    # Step 2: shrinkage calibration
    weights = _shrinkage_weights(inputs.n_comparable_observations)
    p12m = _compute_p12m(
        inputs.base_rate, logistic_prob, inputs.comparable_bucket_rate, weights
    )

    # Step 3: time windows
    p6m, p18m = _compute_time_windows(p12m)

    # Step 4: band, confidence, range
    band = _probability_band(p12m)
    confidence = _confidence_level(inputs)
    range_lo, range_hi = _probability_range(p12m, confidence)

    # Step 5: divergence flag
    div_flag = _divergence_flag(inputs.rank_percentile, p12m)

    # Step 6: cohort
    cohort = _calibration_cohort(inputs.watchlist_class)

    # Step 7: display
    display = _display_probability(p12m, band, confidence)

    # Step 8: explainability
    pos_drivers = _build_positive_drivers(
        inputs.input_positive_drivers,
        inputs.active_driver_bucket_count,
        inputs.strategic_priority,
        inputs.transaction_probability,
    )
    neg_drivers = _build_negative_drivers(
        inputs.active_gate_ids, inputs.input_negative_drivers
    )
    what_would_change = _build_what_would_change(inputs)
    data_gaps = _build_data_gaps(inputs)

    # Step 9: interpretation narrative
    interpretation = _build_interpretation(
        inputs.target_name, p12m, band, confidence,
        pos_drivers, neg_drivers, inputs.watchlist_class,
    )

    return Layer5Output(
        target_name=inputs.target_name,
        acquirer_id=inputs.acquirer_id,
        rank_score=inputs.rank_score,
        p_takeout_12m=p12m,
        p_takeout_6m=p6m,
        p_takeout_18m=p18m,
        probability_band=band.value,
        probability_range_low=range_lo,
        probability_range_high=range_hi,
        confidence_level=confidence.value,
        calibration_cohort=cohort,
        top_positive_drivers=pos_drivers,
        top_negative_drivers=neg_drivers,
        what_would_change_score=what_would_change,
        data_gaps=data_gaps,
        rank_probability_divergence_flag=div_flag,
        display_probability=display,
        estimated_deal_value_low_millions=inputs.estimated_deal_value_low_millions,
        estimated_deal_value_high_millions=inputs.estimated_deal_value_high_millions,
        logistic_probability_used=round(logistic_prob, 6),
        shrinkage_weights=weights,
        as_of_date=inputs.as_of_date,
        model_version=inputs.model_version,
        interpretation=interpretation,
    )
