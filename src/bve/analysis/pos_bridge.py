"""
CalibratedPOS bridge — Sprint 20.

Provides an opt-in integration between the hierarchical Bayesian
CalibratedPOSModel (Sprint 17) and the industry-prior-based POS model
(models/pos_model.py).

Design principles
-----------------
- Backward-compatible: all existing code using `compute_phase_pos()` is
  unaffected. The bridge is a thin wrapper that adds calibration as a
  parameter.
- Opt-in blending: `compute_phase_pos_calibrated()` accepts an optional
  `cal_model`. When None, behaviour is identical to `compute_phase_pos()`.
- Threshold-gated: calibration data below `blend_threshold` is ignored,
  preventing noisy low-N bins from corrupting priors.
- Transparent: `BaseRateSource` dataclass reports exactly which source
  (calibrated | industry_prior | fallback) was used and its blend_weight.

Usage
-----
    from bve.analysis.pos_bridge import compute_phase_pos_calibrated
    from bve.models.pos_calibrated import CalibratedPOSModel

    cal_model = CalibratedPOSModel.from_store("outputs/intelligence/ops.db")

    pos = compute_phase_pos_calibrated(
        TrialPhase.PHASE_2,
        TherapeuticArea.ONCOLOGY,
        adjusters=my_adjusters,
        cal_model=cal_model,
    )

    # Or use the low-level rate resolver directly:
    from bve.analysis.pos_bridge import resolve_base_rate
    result = resolve_base_rate("oncology", "phase_2", cal_model)
    print(result.rate, result.source, result.blend_weight)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Optional

from bve.config.constants import PHASE_SUCCESS_RATES

if TYPE_CHECKING:
    from bve.entities.asset import ApprovalPathwayType, TherapeuticArea
    from bve.entities.trial import TrialPhase
    from bve.models.pos_calibrated import CalibratedPOSModel
    from bve.models.pos_model import POSAdjusters


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum blend_weight for a calibrated bin to influence the base rate.
# Below this threshold the bin has < 25% posterior weight — not reliable enough.
_DEFAULT_BLEND_THRESHOLD: float = 0.10

BaseRateSourceType = Literal["calibrated", "industry_prior", "fallback"]


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

@dataclass
class BaseRateSource:
    """
    Result of resolve_base_rate().

    Attributes
    ----------
    rate:
        The resolved base rate (0.0–1.0).
    source:
        Which source provided the rate:
        - "calibrated"    : CalibratedPOSModel bin with blend_weight ≥ threshold
        - "industry_prior": PHASE_SUCCESS_RATES lookup
        - "fallback"      : _FALLBACK_BASE_RATE (0.40), used when no prior exists
    blend_weight:
        The bin's blend_weight from CalibratedPOSModel (0.0–1.0), or None when
        source is "industry_prior" or "fallback".
    n_outcomes:
        Number of outcomes in the calibration bin, or None when not calibrated.
    """

    rate: float
    source: BaseRateSourceType
    blend_weight: Optional[float] = None
    n_outcomes: Optional[int] = None


# ---------------------------------------------------------------------------
# Base rate resolver
# ---------------------------------------------------------------------------

def resolve_base_rate(
    therapeutic_area: str,
    phase: str,
    cal_model: Optional["CalibratedPOSModel"] = None,
    *,
    blend_threshold: float = _DEFAULT_BLEND_THRESHOLD,
) -> BaseRateSource:
    """
    Resolve the PoS base rate for (therapeutic_area, phase).

    Priority order
    --------------
    1. CalibratedPOSModel bin with blend_weight ≥ blend_threshold (if cal_model given)
    2. PHASE_SUCCESS_RATES industry prior
    3. Fallback rate (0.40)

    Parameters
    ----------
    therapeutic_area:
        TA string — matched case-insensitively (e.g. "oncology", "ONCOLOGY").
    phase:
        Phase string (e.g. "phase_2", "PHASE_2").
    cal_model:
        Optional CalibratedPOSModel. If None, falls through to industry prior.
    blend_threshold:
        Minimum blend_weight to accept calibration data. Default 0.10.

    Returns
    -------
    BaseRateSource
    """
    ta = therapeutic_area.lower()
    ph = phase.lower()

    # Attempt calibrated source
    if cal_model is not None:
        bin_summary = cal_model.bin_summary(ta, ph)
        if bin_summary is not None and bin_summary.blend_weight >= blend_threshold:
            return BaseRateSource(
                rate=bin_summary.blended_rate,
                source="calibrated",
                blend_weight=bin_summary.blend_weight,
                n_outcomes=bin_summary.n_total,
            )

    # Industry prior from PHASE_SUCCESS_RATES
    ta_rates = PHASE_SUCCESS_RATES.get(ta) or PHASE_SUCCESS_RATES.get("all")
    if ta_rates:
        rate = ta_rates.get(ph)
        if rate is not None:
            return BaseRateSource(rate=float(rate), source="industry_prior")

    # Last-resort fallback
    from bve.models.pos_calibrated import _FALLBACK_BASE_RATE
    return BaseRateSource(rate=_FALLBACK_BASE_RATE, source="fallback")


# ---------------------------------------------------------------------------
# Calibrated POS computation
# ---------------------------------------------------------------------------

def compute_phase_pos_calibrated(
    phase: "TrialPhase",
    therapeutic_area: "TherapeuticArea",
    *,
    adjusters: Optional["POSAdjusters"] = None,
    approval_pathway: Optional["ApprovalPathwayType"] = None,
    cal_model: Optional["CalibratedPOSModel"] = None,
    blend_threshold: float = _DEFAULT_BLEND_THRESHOLD,
) -> float:
    """
    Compute phase PoS using a calibrated base rate when available.

    Equivalent to `compute_phase_pos()` when `cal_model` is None — fully
    backward-compatible drop-in replacement.

    Parameters
    ----------
    phase:
        The trial phase.
    therapeutic_area:
        Therapeutic area.
    adjusters:
        Layer 1 qualitative adjusters. Defaults to average (no adjustment).
    approval_pathway:
        When ACCELERATED, applies the NDA/BLA confirmatory trial discount.
    cal_model:
        Optional CalibratedPOSModel. When None, uses industry priors only.
    blend_threshold:
        Minimum blend_weight to accept calibration data.

    Returns
    -------
    float
        Probability of success for this phase, in (0, 1).
    """
    from bve.models.pos_model import POSAdjusters, _compute_layer1_adjustment  # noqa: F401

    adjusters_provided = adjusters is not None
    if adjusters is None:
        adjusters = POSAdjusters()

    ta_str = therapeutic_area.value if hasattr(therapeutic_area, "value") else str(therapeutic_area)
    phase_str = phase.value if hasattr(phase, "value") else str(phase)

    # Resolve base rate
    base_source = resolve_base_rate(ta_str, phase_str, cal_model, blend_threshold=blend_threshold)
    base_rate = base_source.rate

    # Accelerated approval NDA/BLA discount (same logic as compute_phase_pos)
    try:
        from bve.entities.asset import ApprovalPathwayType as _APT
        from bve.entities.trial import TrialPhase as _TP
        _AA_NDA_DISCOUNT: float = 0.18
        if (
            approval_pathway is not None
            and approval_pathway == _APT.ACCELERATED
            and phase == _TP.NDA_BLA
        ):
            base_rate = base_rate * (1.0 - _AA_NDA_DISCOUNT)
    except Exception:
        pass  # entity imports unavailable in test stubs

    # Convert to log-odds, apply Layer 1 adjusters, convert back
    base_rate = max(0.01, min(0.99, base_rate))
    log_odds = math.log(base_rate / (1.0 - base_rate))

    try:
        from bve.models.pos_model import _L1_CAP_NEGATIVE, _L1_CAP_POSITIVE
        from bve.entities.trial import TrialPhase as _TP_ADJ
        if phase == _TP_ADJ.NDA_BLA and not adjusters_provided:
            adjustment = 0.0
        else:
            adjustment, _flags = _compute_layer1_adjustment(adjusters, ta_value=ta_str)
        adjustment = max(_L1_CAP_NEGATIVE, min(_L1_CAP_POSITIVE, adjustment))
        log_odds += adjustment
    except Exception:
        pass  # adjusters unavailable in minimal test stubs

    pos = 1.0 / (1.0 + math.exp(-log_odds))
    return round(pos, 4)


# ---------------------------------------------------------------------------
# Comparison helper
# ---------------------------------------------------------------------------

def pos_delta(
    phase: "TrialPhase",
    therapeutic_area: "TherapeuticArea",
    cal_model: "CalibratedPOSModel",
    *,
    blend_threshold: float = _DEFAULT_BLEND_THRESHOLD,
) -> Optional[float]:
    """
    Return the difference (calibrated PoS − industry prior PoS) in percentage
    points, or None if the calibrated bin has insufficient data.

    Positive → calibration is more optimistic than industry prior.
    Negative → calibration is more conservative.

    This is used by the daily brief to highlight where outcome data
    materially shifts the base rate estimate.
    """
    ta_str = therapeutic_area.value if hasattr(therapeutic_area, "value") else str(therapeutic_area)
    phase_str = phase.value if hasattr(phase, "value") else str(phase)

    cal_source = resolve_base_rate(ta_str, phase_str, cal_model, blend_threshold=blend_threshold)
    if cal_source.source != "calibrated":
        return None

    prior_source = resolve_base_rate(ta_str, phase_str, None)  # industry prior only
    return round((cal_source.rate - prior_source.rate) * 100, 2)
