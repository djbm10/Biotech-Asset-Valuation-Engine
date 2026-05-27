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

import json
import math
import warnings
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

# Path to fitted calibration parameters (written by ma_backtest.save_calibration_params)
_CALIBRATION_PARAMS_PATH: Path = (
    Path(__file__).parent.parent / "config" / "ma_calibration_params.json"
)


def _try_load_calibration_params() -> tuple[float, float]:
    """Load (slope, midpoint) from fitted JSON if available.

    Falls back to hard-coded defaults with a UserWarning when:
    - The file does not exist (no calibration has been run yet).
    - The file is malformed or missing required keys.

    Returns
    -------
    tuple[float, float]
        (slope, midpoint)
    """
    if not _CALIBRATION_PARAMS_PATH.exists():
        warnings.warn(
            f"No fitted calibration params found at {_CALIBRATION_PARAMS_PATH}. "
            "Using hard-coded defaults (slope=8.0, midpoint=0.68). "
            "Run ma_backtest.fit_logistic_calibration() and save_calibration_params() "
            "to replace these un-validated constants.",
            UserWarning,
            stacklevel=2,
        )
        return _LOGISTIC_SLOPE, _LOGISTIC_MIDPOINT

    try:
        data = json.loads(_CALIBRATION_PARAMS_PATH.read_text())
        return float(data["slope"]), float(data["midpoint"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        warnings.warn(
            f"Failed to parse calibration params at {_CALIBRATION_PARAMS_PATH}: {exc}. "
            "Using hard-coded defaults (slope=8.0, midpoint=0.68).",
            UserWarning,
            stacklevel=2,
        )
        return _LOGISTIC_SLOPE, _LOGISTIC_MIDPOINT


# Attempt to load fitted params; fall back to hard-coded defaults.
# These are used by _derive_logistic_probability().
_EFFECTIVE_SLOPE, _EFFECTIVE_MIDPOINT = _try_load_calibration_params()

# Shrinkage weight tiers: (base_rate_weight, logistic_weight, bucket_weight)
_SHRINKAGE_SMALL: tuple[float, float, float] = (0.60, 0.20, 0.20)     # n < 10
_SHRINKAGE_MODERATE: tuple[float, float, float] = (0.50, 0.30, 0.20)  # 10 ≤ n < 20
_SHRINKAGE_STANDARD: tuple[float, float, float] = (0.40, 0.40, 0.20)  # 20 ≤ n < 30
_SHRINKAGE_LARGE: tuple[float, float, float] = (0.30, 0.50, 0.20)     # n ≥ 30

_SHRINKAGE_SMALL_N: int = 10
_SHRINKAGE_MODERATE_N: int = 20
_SHRINKAGE_STANDARD_N: int = 30

# Time-window scaling (Block 31: defaults preserved for UNKNOWN/None catalyst)
_SCALE_6M: float = 0.55
_SCALE_18M_EXPONENT: float = 1.35  # survival: 1 − (1 − p12m)^exponent

# Block 31: Catalyst-based dynamic scaling tables (keyed by timing_shape string)
_HIGH_STAKE_CATALYST_TYPES = frozenset([
    "phase_3_readout", "regulatory_decision",
])
_MEANINGFUL_CATALYST_TYPES = frozenset([
    "phase_2_poc", "fda_meeting", "phase_3_readout", "regulatory_decision",
])

_6M_SCALE_TABLE: dict[str, float] = {
    "strongly_front_loaded": 0.80,
    "front_loaded":          0.68,
    "neutral":               0.55,   # EVIDENCE-INFORMED DEFAULT; matches old constant
    "back_loaded":           0.38,
}
_18M_EXPONENT_TABLE: dict[str, float] = {
    "strongly_front_loaded": 1.10,
    "front_loaded":          1.25,
    "neutral":               1.35,   # EVIDENCE-INFORMED DEFAULT; matches old constant
    "back_loaded":           1.55,
}

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

class CatalystType(str, Enum):
    """
    Type of the next material catalyst for this asset/company.

    Drives 6m/18m hazard-rate scaling.  Higher-stakes catalysts + near-term timing
    produce strongly front-loaded probability distributions.

    UNKNOWN is the default — preserves existing fixed-constant behaviour exactly
    (scale_6m=0.55, scale_18m_exponent=1.35).
    """
    NONE               = "none"                # No binary catalyst; continuous progress
    INVESTOR_UPDATE    = "investor_update"     # Conference, investor day — minor
    PHASE_2_POC        = "phase_2_poc"         # Phase 2 proof-of-concept readout
    FDA_MEETING        = "fda_meeting"         # Type B/C meeting or advisory committee
    REGULATORY_DECISION = "regulatory_decision"  # PDUFA date, EMA opinion, CRL response
    PHASE_3_READOUT    = "phase_3_readout"    # Pivotal Phase 3 top-line data
    UNKNOWN            = "unknown"             # No catalyst schedule available (default)


class SellerWillingness(str, Enum):
    """
    Observable anchor points for analyst assessment of management/board receptivity
    to a sale or partnership transaction.

    Anchors are grounded in observable events (not opinion). Ordered by signal strength.

    Cross-reference: ManagementReceptivity (ma_management_receptivity.py) captures the
    ACQUIRER's perspective on whether sell-side management would engage. SellerWillingness
    is the SELL-SIDE analyst assessment of the board/CEO disposition, grounded in
    observable signals (press release, banker mandate, defensive measures).
    These are complementary, not redundant — use both when evidence exists for each.

    Scores:
      ACTIVELY_SEEKING  0.90  Board/banker mandate confirmed (press release, banker hired)
      OPEN              0.70  CEO public statements, investor day comments, prior strategic review
      NEUTRAL           0.50  No public signal either way (known-neutral, not unknown)
      RELUCTANT         0.30  Defensive anti-takeover measure adopted (staggered board, etc.)
      HOSTILE           0.10  Poison pill, publicly declined bid, founder defense on record
      UNKNOWN           0.50  No evidence available; confidence degraded one tier (differs
                              from NEUTRAL — represents absence of knowledge, not neutral signal)
    """
    ACTIVELY_SEEKING = "actively_seeking"
    OPEN             = "open"
    NEUTRAL          = "neutral"
    RELUCTANT        = "reluctant"
    HOSTILE          = "hostile"
    UNKNOWN          = "unknown"


_SELLER_WILLINGNESS_SCORES: dict[SellerWillingness, float] = {
    SellerWillingness.ACTIVELY_SEEKING: 0.90,
    SellerWillingness.OPEN:             0.70,
    SellerWillingness.NEUTRAL:          0.50,
    SellerWillingness.RELUCTANT:        0.30,
    SellerWillingness.HOSTILE:          0.10,
    SellerWillingness.UNKNOWN:          0.50,  # same as NEUTRAL; flag added separately
}


def seller_willingness_to_score(willingness: SellerWillingness) -> float:
    """Map SellerWillingness anchor to a float score in [0, 1]."""
    return _SELLER_WILLINGNESS_SCORES[willingness]


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class ProbabilitySource(str, Enum):
    """
    Epistemological source for a probability estimate.

    CALIBRATED  — shrinkage blend with a fitted logistic curve
                  (ma_calibration_params.json present and valid)
    DERIVED     — fraction or time-scaling applied to a CALIBRATED parent;
                  not independently calibrated
    FALLBACK    — shrinkage blend using hard-coded default logistic parameters;
                  logistic curve has not been fitted to held-out data
    RANK_ONLY   — ordering signal only; no statistical probability interpretation
    """
    CALIBRATED = "calibrated"
    DERIVED    = "derived"
    FALLBACK   = "fallback"
    RANK_ONLY  = "rank_only"


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
        description="Layer 1 seller willingness score (overridden by seller_willingness_anchor)")
    # Block 27: observable anchor for seller willingness
    seller_willingness_anchor: Optional[SellerWillingness] = Field(
        default=None,
        description=(
            "Block 27 observable anchor. When set, overrides seller_willingness float. "
            "UNKNOWN adds a confidence flag and degrades confidence one tier."
        ),
    )
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

    # --- Block 21: score decomposition opt-in ---
    include_decomposition: bool = Field(default=False,
        description="When True, attach a ScoreComposition attribution breakdown to Layer5Output")

    # --- Block 20: transaction type split inputs ---
    acquisition_fraction: float = Field(default=0.60, ge=0.0, le=1.0,
        description="Historical full-acquisition share of strategic transactions")
    license_fraction: float = Field(default=0.35, ge=0.0, le=1.0,
        description="Historical licensing/partnership share of strategic transactions")
    comparable_bucket_rate_source: str = Field(default="",
        description="Source of comparable_bucket_rate: 'segment_report' | 'fallback' | ''")

    # --- Block 31: catalyst timing context ---
    days_to_catalyst: Optional[int] = Field(
        default=None,
        ge=0,
        description="Calendar days from as_of_date to next material catalyst. "
                    "None = no schedule available. Drives 6m/18m hazard scaling.",
    )
    catalyst_type: CatalystType = Field(
        default=CatalystType.UNKNOWN,
        description="Type of next material catalyst. Higher-stakes types + near-term "
                    "timing → more front-loaded probability distribution.",
    )

    # Metadata
    as_of_date: str = Field(default="",
        description="ISO date string for this observation (YYYY-MM-DD)")
    model_version: str = Field(default="v1.0",
        description="Model version for auditability")
    target_name: str = Field(default="Unknown")
    acquirer_id: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def _resolve_seller_willingness_anchor(self) -> "Layer5Inputs":
        """Block 27: override seller_willingness float when anchor is set."""
        if self.seller_willingness_anchor is not None:
            score = seller_willingness_to_score(self.seller_willingness_anchor)
            object.__setattr__(self, "seller_willingness", score)
        return self


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

    # --- Block 20: transaction type separation ---
    p_any_strategic_transaction_12m: float = Field(..., ge=0.0, le=1.0,
        description="Calibrated 12-month probability of ANY strategic transaction "
                    "(acquisition OR license/partnership)")
    p_full_acquisition_12m: float = Field(..., ge=0.0, le=1.0,
        description="Derived split: acquisition_fraction × p_any_strategic_transaction_12m. "
                    "HEURISTIC — derived from transaction mix prior, not independently calibrated.")
    p_license_or_partner_12m: float = Field(..., ge=0.0, le=1.0,
        description="Derived split: license_fraction × p_any_strategic_transaction_12m. "
                    "HEURISTIC — derived from transaction mix prior, not independently calibrated.")
    bucket_rate_warning: Optional[str] = Field(default=None,
        description="Set when comparable_bucket_rate is from a fallback source, "
                    "not a segment-specific empirical estimate. Confidence capped at Low.")

    # --- Block 21: score decomposition (attribution layer, opt-in) ---
    score_composition: Optional[Any] = Field(default=None,
        description="ScoreComposition attribution breakdown. None unless "
                    "Layer5Inputs.include_decomposition=True.")

    # --- Block 22: calibration truthfulness ---
    calibration_fitted: bool = Field(
        default=False,
        description="True only when ma_calibration_params.json exists and parses. "
                    "False means hard-coded defaults (slope=8.0, midpoint=0.68) are in use.",
    )
    calibration_params_source: str = Field(
        default="hard_coded_defaults",
        description="'fitted_file' when params loaded from JSON; 'hard_coded_defaults' otherwise.",
    )
    calibration_warning: Optional[str] = Field(
        default=None,
        description="Set to a warning string when calibration_fitted=False; None when fitted.",
    )

    # --- Block 27: seller willingness flag ---
    seller_willingness_flag: Optional[str] = Field(
        default=None,
        description="Set to 'seller_willingness_unknown' when seller_willingness_anchor=UNKNOWN. "
                    "Signals that seller willingness is unknown (not neutral); confidence degrades.",
    )

    # --- Block 26: probability source tags ---
    p_any_source: ProbabilitySource = Field(
        default=ProbabilitySource.FALLBACK,
        description="CALIBRATED when logistic params are fitted; FALLBACK when using defaults.",
    )
    p_full_acquisition_source: ProbabilitySource = Field(
        default=ProbabilitySource.DERIVED,
        description="Always DERIVED (acquisition_fraction × p_any; not independently calibrated).",
    )
    p_license_or_partner_source: ProbabilitySource = Field(
        default=ProbabilitySource.DERIVED,
        description="Always DERIVED (license_fraction × p_any; not independently calibrated).",
    )
    p_takeout_6m_source: ProbabilitySource = Field(
        default=ProbabilitySource.DERIVED,
        description="Always DERIVED (time-scaled from p_any_12m via hazard-rate approximation).",
    )
    p_takeout_18m_source: ProbabilitySource = Field(
        default=ProbabilitySource.DERIVED,
        description="Always DERIVED (time-scaled from p_any_12m via survival function scaling).",
    )

    # --- Block 31: catalyst timing audit fields ---
    timing_shape: str = Field(
        default="neutral",
        description="Timing shape derived from catalyst proximity: "
                    "strongly_front_loaded / front_loaded / neutral / back_loaded.",
    )
    timing_rationale: str = Field(
        default="",
        description="Human-readable explanation of timing shape applied.",
    )
    scale_6m_applied: float = Field(
        default=_SCALE_6M,
        description="Actual 6m hazard scale used (audit). 0.55 = neutral default.",
    )
    scale_18m_exponent_applied: float = Field(
        default=_SCALE_18M_EXPONENT,
        description="Actual 18m survival exponent used (audit). 1.35 = neutral default.",
    )

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
    """Map rank_score to a calibrated logistic probability via sigmoid transform.

    Uses ``_EFFECTIVE_SLOPE`` and ``_EFFECTIVE_MIDPOINT``, which are loaded from
    ``ma_calibration_params.json`` at import time when the file is present, and
    fall back to the hard-coded ``_LOGISTIC_SLOPE``/``_LOGISTIC_MIDPOINT`` otherwise.
    """
    return round(_expit(_EFFECTIVE_SLOPE * (rank_score - _EFFECTIVE_MIDPOINT)), 6)


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


# ---------------------------------------------------------------------------
# Block 31: catalyst timing helpers
# ---------------------------------------------------------------------------

def _compute_timing_shape(
    days: Optional[int],
    catalyst_type: "CatalystType",
) -> str:
    """Derive timing shape from catalyst proximity and type.

    Returns one of: strongly_front_loaded / front_loaded / neutral / back_loaded.

    Rules:
    - UNKNOWN type OR no days → neutral (backward-compat default)
    - NONE type → neutral (no binary catalyst; continuous hazard)
    - days > 365 → back_loaded (regardless of type)
    - days <= 90 AND high-stake type (Phase 3 / regulatory) → strongly_front_loaded
    - days <= 180 AND meaningful type (Phase 2+, FDA meeting) → front_loaded
    - otherwise → neutral
    """
    if catalyst_type == CatalystType.UNKNOWN or catalyst_type == CatalystType.NONE:
        return "neutral"
    if days is None:
        return "neutral"
    if days > 365:
        return "back_loaded"
    if days <= 90 and catalyst_type.value in _HIGH_STAKE_CATALYST_TYPES:
        return "strongly_front_loaded"
    if days <= 180 and catalyst_type.value in _MEANINGFUL_CATALYST_TYPES:
        return "front_loaded"
    return "neutral"


def _timing_rationale(shape: str, days: Optional[int], catalyst_type: "CatalystType") -> str:
    """Build a human-readable rationale string for the timing shape."""
    if shape == "neutral":
        if catalyst_type == CatalystType.UNKNOWN or days is None:
            return "No catalyst schedule available; using neutral hazard distribution."
        if catalyst_type == CatalystType.NONE:
            return "No binary catalyst event; continuous progress hazard applied."
        return "Catalyst timing neutral; standard hazard distribution applied."
    days_str = f"{days}d" if days is not None else "unknown"
    type_str = catalyst_type.value.replace("_", " ")
    if shape == "strongly_front_loaded":
        return (
            f"High-stakes {type_str} catalyst in {days_str}; "
            "probability strongly front-loaded into 6m window."
        )
    if shape == "front_loaded":
        return (
            f"Material {type_str} catalyst in {days_str}; "
            "probability moderately front-loaded into 6m window."
        )
    return (
        f"{type_str.capitalize()} catalyst in {days_str} (>12m horizon); "
        "probability back-loaded toward 18m window."
    )


def _compute_time_windows(
    p12m: float,
    scale_6m: float = _SCALE_6M,
    exponent_18m: float = _SCALE_18M_EXPONENT,
) -> tuple[float, float]:
    """Derive 6-month and 18-month probabilities from the 12-month estimate.

    p_6m  ≈ p_12m × scale_6m  (hazard-rate scaling; default 0.55)
    p_18m ≈ 1 − (1 − p_12m)^exponent_18m  (survival function; default 1.35)

    Block 31: scale_6m and exponent_18m are now dynamic based on catalyst timing.
    Default values preserve existing behaviour exactly (backward compat).
    """
    p6m = round(min(max(p12m * scale_6m, 0.0), 1.0), 6)
    p18m = round(min(max(1.0 - (1.0 - p12m) ** exponent_18m, 0.0), 1.0), 6)
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

    Block 20 — bucket_rate_source cap:
    When comparable_bucket_rate_source is 'fallback' or '' (unknown), confidence
    is capped at LOW regardless of data_confidence_score or n_comparable_observations.
    """
    if inputs.data_confidence_score < _LOW_CONFIDENCE_DATA_MIN:
        return ConfidenceLevel.VERY_LOW

    if (
        inputs.data_confidence_score >= _HIGH_CONFIDENCE_DATA_MIN
        and inputs.n_comparable_observations >= _HIGH_CONFIDENCE_N_MIN
    ):
        raw = ConfidenceLevel.HIGH
    elif (
        inputs.data_confidence_score >= _MEDIUM_CONFIDENCE_DATA_MIN
        or inputs.n_comparable_observations >= _MEDIUM_CONFIDENCE_N_MIN
    ):
        raw = ConfidenceLevel.MEDIUM
    else:
        raw = ConfidenceLevel.LOW

    # Cap at LOW when bucket rate is explicitly from a fallback source.
    # "" = legacy/unset — no cap applied (backward-compatible).
    if inputs.comparable_bucket_rate_source == "fallback":
        if raw in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM):
            return ConfidenceLevel.LOW

    return raw


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
# Block 22: calibration truthfulness helpers
# ---------------------------------------------------------------------------

def _is_calibration_fitted() -> bool:
    """Return True when ma_calibration_params.json exists AND parses successfully.

    Checked at call time (not import time) so monkeypatching in tests works correctly.
    """
    if not _CALIBRATION_PARAMS_PATH.exists():
        return False
    try:
        data = json.loads(_CALIBRATION_PARAMS_PATH.read_text())
        float(data["slope"])
        float(data["midpoint"])
        return True
    except (KeyError, ValueError, json.JSONDecodeError):
        return False


# ---------------------------------------------------------------------------
# Block 20: resolve_comparable_bucket_rate helper
# ---------------------------------------------------------------------------

def resolve_comparable_bucket_rate(
    rate: float,
    source: str,
) -> tuple[float, str]:
    """Resolve the comparable bucket rate and its source label.

    Parameters
    ----------
    rate:
        The candidate comparable bucket rate (0.0–1.0).
    source:
        Provider label: 'segment_report' indicates an empirically-derived rate;
        any other value ('' or 'fallback') is treated as a fallback estimate.

    Returns
    -------
    tuple[float, str]
        (rate, normalised_source) where normalised_source is
        'segment_report' or 'fallback'.
    """
    if source == "segment_report":
        return rate, "segment_report"
    return rate, "fallback"


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

    # Step 3: time windows (Block 31: catalyst-based dynamic scaling)
    _timing_shape = _compute_timing_shape(inputs.days_to_catalyst, inputs.catalyst_type)
    _scale_6m = _6M_SCALE_TABLE[_timing_shape]
    _exponent_18m = _18M_EXPONENT_TABLE[_timing_shape]
    _timing_rat = _timing_rationale(_timing_shape, inputs.days_to_catalyst, inputs.catalyst_type)
    p6m, p18m = _compute_time_windows(p12m, scale_6m=_scale_6m, exponent_18m=_exponent_18m)

    # Step 4: band, confidence, range
    band = _probability_band(p12m)
    confidence = _confidence_level(inputs)

    # Block 22: calibration truthfulness — cap confidence when logistic is unfitted
    cal_fitted = _is_calibration_fitted()
    if not cal_fitted and confidence != ConfidenceLevel.VERY_LOW:
        confidence = ConfidenceLevel.VERY_LOW
    cal_params_source = "fitted_file" if cal_fitted else "hard_coded_defaults"
    cal_warning: Optional[str] = (
        None if cal_fitted else (
            "Logistic calibration uses hard-coded defaults (slope=8.0, midpoint=0.68). "
            "Run fit_logistic_calibration() and save_calibration_params() to replace "
            "these un-validated constants."
        )
    )

    # Block 27: seller willingness unknown — degrade confidence one tier
    _seller_anchor = inputs.seller_willingness_anchor
    seller_willingness_flag: Optional[str] = None
    if _seller_anchor == SellerWillingness.UNKNOWN:
        seller_willingness_flag = "seller_willingness_unknown"
        # Degrade confidence by one tier (floor at VERY_LOW)
        _tier_order = [
            ConfidenceLevel.HIGH,
            ConfidenceLevel.MEDIUM,
            ConfidenceLevel.LOW,
            ConfidenceLevel.VERY_LOW,
        ]
        _idx = _tier_order.index(confidence)
        confidence = _tier_order[min(_idx + 1, len(_tier_order) - 1)]

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

    # Block 21: score decomposition (attribution only — computed after all scores are final)
    score_composition = None
    if inputs.include_decomposition:
        from bve.intelligence.ma_score_decomposition import compute_score_decomposition
        score_composition = compute_score_decomposition(
            target_name=inputs.target_name,
            acquirer_id=inputs.acquirer_id,
            final_score=inputs.rank_score,
            rank_score=inputs.rank_score,
            asset_quality=inputs.asset_quality,
            seller_willingness=inputs.seller_willingness,
            strategic_priority=inputs.strategic_priority,
            transaction_probability=inputs.transaction_probability,
            active_driver_bucket_count=inputs.active_driver_bucket_count,
            active_gate_ids=inputs.active_gate_ids,
            watchlist_class=inputs.watchlist_class,
            data_confidence_score=inputs.data_confidence_score,
            base_rate=inputs.base_rate,
            comparable_bucket_rate=inputs.comparable_bucket_rate,
            comparable_bucket_rate_source=inputs.comparable_bucket_rate_source,
            n_comparable_observations=inputs.n_comparable_observations,
            shrinkage_weights=weights,
            calibration_base_rate=inputs.base_rate,
            calibration_comparable_rate=inputs.comparable_bucket_rate,
        )

    # Block 20: transaction type separation
    _bucket_src = inputs.comparable_bucket_rate_source
    bucket_rate_warning: Optional[str] = None
    if _bucket_src == "fallback":
        bucket_rate_warning = (
            "comparable_bucket_rate is from a fallback source, not a segment-specific "
            "empirical estimate. Confidence capped at Low; treat splits as approximate."
        )
    p_any = p12m  # p_any_strategic_transaction_12m == the primary calibrated output
    p_full_acq = round(inputs.acquisition_fraction * p_any, 4)
    p_license = round(inputs.license_fraction * p_any, 4)
    # p_takeout_12m is the deprecated alias for p_full_acquisition_12m
    p_takeout_alias = p_full_acq

    return Layer5Output(
        target_name=inputs.target_name,
        acquirer_id=inputs.acquirer_id,
        rank_score=inputs.rank_score,
        p_takeout_12m=p_takeout_alias,
        p_takeout_6m=p6m,
        p_takeout_18m=p18m,
        p_any_strategic_transaction_12m=p_any,
        p_full_acquisition_12m=p_full_acq,
        p_license_or_partner_12m=p_license,
        bucket_rate_warning=bucket_rate_warning,
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
        score_composition=score_composition,
        calibration_fitted=cal_fitted,
        calibration_params_source=cal_params_source,
        calibration_warning=cal_warning,
        # Block 27: seller willingness flag
        seller_willingness_flag=seller_willingness_flag,
        # Block 26: probability source tags
        p_any_source=ProbabilitySource.CALIBRATED if cal_fitted else ProbabilitySource.FALLBACK,
        p_full_acquisition_source=ProbabilitySource.DERIVED,
        p_license_or_partner_source=ProbabilitySource.DERIVED,
        p_takeout_6m_source=ProbabilitySource.DERIVED,
        p_takeout_18m_source=ProbabilitySource.DERIVED,
        # Block 31: catalyst timing audit fields
        timing_shape=_timing_shape,
        timing_rationale=_timing_rat,
        scale_6m_applied=_scale_6m,
        scale_18m_exponent_applied=_exponent_18m,
        as_of_date=inputs.as_of_date,
        model_version=inputs.model_version,
        interpretation=interpretation,
    )


# ---------------------------------------------------------------------------
# New Layer 5 public API (5A–5H wrappers)
# ---------------------------------------------------------------------------
# These functions expose the new institutional-grade Layer 5 submodules via a
# single unified import path.  The old compute_layer5() contract is preserved
# above; nothing here modifies it.

from typing import Any  # noqa: E402  (placed here to avoid polluting old API)


def build_historical_ma_outcome_dataset(
    raw_cases: list[dict],
    *,
    observation_window_months: int = 12,
    exclude_leaky: bool = True,
) -> list:
    """5A — Build a validated historical outcome dataset.

    Wraps :mod:`bve.intelligence.ma_outcome_dataset`.

    Args:
        raw_cases: Raw case dicts as described in OutcomeDatasetConfig.
        observation_window_months: Primary labelling window.
        exclude_leaky: If True, cases with lookahead violations are excluded.

    Returns:
        List of :class:`~bve.intelligence.ma_calibration_models.HistoricalMAOutcome`.
    """
    from bve.intelligence.ma_calibration_models import OutcomeDatasetConfig
    from bve.intelligence.ma_outcome_dataset import build_historical_ma_outcome_dataset as _build

    config = OutcomeDatasetConfig(
        observation_window_months=observation_window_months,
        exclude_leaky_cases=exclude_leaky,
    )
    return _build(raw_cases, config)


def fit_layer5_calibration(
    cases: list,
    *,
    model_version: str = "v1",
    dataset_version: str = "v1",
    artifact_id: Optional[str] = None,
) -> Any:
    """5C — Fit a calibration artifact from historical outcomes.

    Wraps :func:`bve.intelligence.ma_probability_calibration.calibrate_ma_scores`.

    Returns:
        :class:`~bve.intelligence.ma_calibration_models.CalibrationArtifact`
    """
    from datetime import date as _date
    from bve.intelligence.ma_calibration_models import (
        CalibrationGovernanceMetadata,
        Layer5CalibrationConfig,
    )
    from bve.intelligence.ma_probability_calibration import calibrate_ma_scores

    config = Layer5CalibrationConfig(
        model_version=model_version,
        dataset_version=dataset_version,
    )
    governance = CalibrationGovernanceMetadata(
        model_version=model_version,
        calibration_dataset_version=dataset_version,
        calibration_date=_date.today(),
        calibration_artifact_id=artifact_id,
    )
    aid = artifact_id or f"artifact_{_date.today().isoformat()}"
    return calibrate_ma_scores(cases, config, artifact_id=aid, governance=governance)


def apply_layer5_calibration(raw_score: float, artifact: Any) -> tuple:
    """5C — Apply a fitted artifact to a new raw score.

    Wraps :func:`bve.intelligence.ma_probability_calibration.predict_calibrated_probabilities`.

    Returns:
        (CalibratedProbabilitySet, CalibrationQualityLabel, do_not_use, reason)
    """
    from bve.intelligence.ma_probability_calibration import predict_calibrated_probabilities
    return predict_calibrated_probabilities(raw_score, artifact)


def generate_segment_diagnostics(
    cases: list,
    dimensions: Optional[list[str]] = None,
) -> list:
    """5D — Compute segment calibration diagnostics.

    Wraps :func:`bve.intelligence.ma_segment_calibration.compute_segment_diagnostics`.

    Returns:
        List of :class:`~bve.intelligence.ma_calibration_models.SegmentDiagnostics`.
    """
    from bve.intelligence.ma_segment_calibration import compute_segment_diagnostics
    return compute_segment_diagnostics(cases, dimensions)


def generate_threshold_recommendations(
    cases: list,
    operating_mode: str = "balanced",
    *,
    cost_matrix: Optional[dict] = None,
) -> list:
    """5E — Generate threshold recommendations for the given operating mode.

    Wraps :func:`bve.intelligence.ma_threshold_optimizer.optimize_thresholds`.

    Returns:
        List of :class:`~bve.intelligence.ma_calibration_models.ThresholdRecommendation`.
    """
    from bve.intelligence.ma_calibration_models import OperatingMode
    from bve.intelligence.ma_threshold_optimizer import optimize_thresholds

    try:
        mode = OperatingMode(operating_mode)
    except ValueError:
        mode = OperatingMode.BALANCED
    return optimize_thresholds(cases, mode, cost_matrix=cost_matrix)


def create_postmortem_for_case(
    case: Any,
    *,
    layer4_route: Optional[str] = None,
    predicted_probabilities: Optional[dict] = None,
    predicted_acquisition: bool = False,
) -> Any:
    """5F — Create a postmortem record for a resolved historical case.

    Wraps :func:`bve.intelligence.ma_postmortem.create_postmortem`.

    Returns:
        :class:`~bve.intelligence.ma_calibration_models.PostmortemRecord`
    """
    from bve.intelligence.ma_postmortem import create_postmortem
    return create_postmortem(
        case,
        layer4_route=layer4_route,
        predicted_probabilities=predicted_probabilities,
        predicted_acquisition=predicted_acquisition,
    )


def detect_drift(
    historical_cases: list,
    recent_cases: list,
    *,
    rolling_window: int = 50,
) -> Any:
    """5G — Run drift detection comparing historical and recent case windows.

    Wraps :func:`bve.intelligence.ma_drift_detection.run_drift_detection`.

    Returns:
        :class:`~bve.intelligence.ma_calibration_models.DriftReport`
    """
    from bve.intelligence.ma_drift_detection import run_drift_detection
    return run_drift_detection(
        historical_cases, recent_cases, rolling_window=rolling_window
    )


def generate_model_governance_report(
    artifact: Any,
    *,
    drift_report: Optional[Any] = None,
    threshold_recs: Optional[list] = None,
    include_model_card: bool = True,
) -> dict:
    """5H — Generate a full governance report for a calibration artifact.

    Wraps :func:`bve.intelligence.ma_model_governance.generate_governance_report`.

    Returns:
        Governance report dict (see ma_model_governance for field details).
    """
    from bve.intelligence.ma_model_governance import generate_governance_report
    return generate_governance_report(
        artifact,
        drift_report=drift_report,
        threshold_recs=threshold_recs,
        include_model_card=include_model_card,
    )


def generate_layer_validation_report(
    cases_validated: dict,
    *,
    known_answer_cases: int = 0,
    top_k_precision: Optional[float] = None,
    base_rate_coverage: Optional[float] = None,
) -> dict:
    """5H — Generate a layer-by-layer validation report.

    Wraps :func:`bve.intelligence.ma_model_governance.generate_layer_validation_report`.

    Args:
        cases_validated: Dict mapping :class:`~bve.intelligence.ma_calibration_models.LayerValidated`
            to the number of validated cases.
        known_answer_cases: Count of cases with known historical outcomes.
        top_k_precision: Precision at top-K for the end-to-end pipeline.
        base_rate_coverage: Fraction of cases where base-rate calibration applies.

    Returns:
        Dict with keys: validation_date, layers, summary_status, limitations.
    """
    from bve.intelligence.ma_model_governance import generate_layer_validation_report as _gen
    return _gen(
        cases_validated,
        known_answer_cases=known_answer_cases,
        top_k_precision=top_k_precision,
        base_rate_coverage=base_rate_coverage,
    )


def build_prediction_audit_record(
    output: Any,
    *,
    run_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """5H — Build a structured audit record for a single Layer 5 prediction.

    Wraps :func:`bve.intelligence.ma_model_governance.build_audit_record`.

    Args:
        output: :class:`~bve.intelligence.ma_calibration_models.Layer5CalibrationOutput`.
        run_id: Optional run identifier for batch tracing.
        user_id: Optional user/system identifier who triggered the run.

    Returns:
        Dict suitable for serialisation to a JSONL audit log.
    """
    from bve.intelligence.ma_model_governance import build_audit_record
    return build_audit_record(output, run_id=run_id, user_id=user_id)


def write_prediction_audit_log(
    records: list[dict],
    path: str,
) -> None:
    """5H — Append audit records to a JSONL file (one record per line).

    Wraps :func:`bve.intelligence.ma_model_governance.write_audit_log`.

    Args:
        records: List of audit record dicts (from :func:`build_prediction_audit_record`).
        path: Absolute path to the JSONL file (parent dirs created automatically).
    """
    from bve.intelligence.ma_model_governance import write_audit_log
    write_audit_log(records, path)
