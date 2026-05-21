"""Layer 0C (new) — Target-Size Pre-Screen.

Annotates a target with its market-cap / EV size bucket and buyer-universe
implications.  **No score effect at Layer 0.**  The size bucket is
informational; it propagates to:

  - ``Layer0Result.required_downstream_checks`` (e.g. ``"large_cap_buyer_required"``)
  - Layer 3A scoring, where the actual acquirer capacity is checked via
    ``compute_pair_affordability_batch()`` in ``ma_pair_affordability.py``

**Anti-double-counting contract**:
    This module never assigns a score multiplier or cap.  All numeric
    affordability penalties are computed pair-specifically in Layer 3A.
    See ``_DOUBLE_COUNT_GUARD_MAP`` in ``ma_eligibility.py``.

**Flag semantics** (clarified from report feedback):

  ``sub_scale_flag``
      True when EV/MC < $100M.  These are bolt-on targets; standalone deals
      are unlikely.  Flag is used to route to alternate deal models, NOT to
      penalise the target.

  ``small_cap_flag``
      True when EV/MC is $100M–$500M.  Informational only.  Small-cap
      biotechs are a *core* segment of the M&A universe and are NOT
      disadvantaged by this flag.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TargetSizeBucket(str, Enum):
    """EV/MC size bucket for a target company.

    Thresholds use a 35% standard takeout premium to estimate acquisition cost:
        expected_cost = reference_value × 1.35

    Bucket boundaries are applied to the raw reference value (pre-premium).
    """
    SUB_SCALE  = "sub_scale"   # EV/MC < $100M  — bolt-on only; standalone deal unlikely
    SMALL_CAP  = "small_cap"   # $100M–$500M    — standard small biotech deal
    MID_CAP    = "mid_cap"     # $500M–$5B      — core M&A universe
    LARGE_CAP  = "large_cap"   # $5B–$25B       — requires investment-grade acquirer
    MEGA_DEAL  = "mega_deal"   # > $25B         — top-10 pharma only; rare
    UNKNOWN    = "unknown"     # no market data available


# Thresholds: (upper_bound_exclusive_millions, bucket)
# Applied to the reference_value_millions (EV preferred; MC as fallback).
_SIZE_THRESHOLDS: list[tuple[float, TargetSizeBucket]] = [
    (100.0,   TargetSizeBucket.SUB_SCALE),
    (500.0,   TargetSizeBucket.SMALL_CAP),
    (5_000.0, TargetSizeBucket.MID_CAP),
    (25_000.0, TargetSizeBucket.LARGE_CAP),
    (float("inf"), TargetSizeBucket.MEGA_DEAL),
]

# Rough minimum buyer capacity (deal capacity, not market cap) needed for
# each bucket.  Based on reference_value × 1.35 (standard premium) / 1.5
# (acquirer uses ~67% of its deal capacity for a typical deal).
_MIN_BUYER_CAPACITY: dict[TargetSizeBucket, Optional[float]] = {
    TargetSizeBucket.SUB_SCALE:  None,          # no minimum; any acquirer can do this
    TargetSizeBucket.SMALL_CAP:  135.0,
    TargetSizeBucket.MID_CAP:    675.0,
    TargetSizeBucket.LARGE_CAP:  6_750.0,
    TargetSizeBucket.MEGA_DEAL:  33_750.0,
    TargetSizeBucket.UNKNOWN:    None,
}


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class TargetSizeInput(BaseModel):
    """Minimal inputs needed for the target-size pre-screen."""
    model_config = ConfigDict(frozen=True)

    target_id: str
    enterprise_value_millions: Optional[float] = None
    market_cap_millions: Optional[float] = Field(default=None, ge=0.0)


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class TargetSizeResult(BaseModel):
    """Target-size pre-screen result (0C — informational only, no score effect).

    Fields:
        size_bucket          — which size tier this target falls into
        reference_value_millions — the EV or MC used for classification
        reference_source     — which field was used ("enterprise_value",
                               "market_cap", or "none")
        minimum_buyer_capacity_needed_millions — rough deal-capacity floor
                               for a plausible acquirer; None for sub-scale
                               and unknown
        requires_large_cap_buyer — True when bucket is LARGE_CAP or MEGA_DEAL
        mega_deal_flag       — True when bucket is MEGA_DEAL
        sub_scale_flag       — True when EV/MC < $100M (bolt-on only;
                               standalone deal unlikely — NOT a penalty)
        small_cap_flag       — True when EV/MC $100M–$500M (informational
                               only; small-cap is a core M&A segment)
        rationale            — one-line human-readable explanation
        data_gaps            — list of missing fields that prevented full assessment
    """
    model_config = ConfigDict(frozen=True)

    size_bucket: TargetSizeBucket
    reference_value_millions: Optional[float]
    reference_source: Literal["enterprise_value", "market_cap", "none"]

    minimum_buyer_capacity_needed_millions: Optional[float]
    requires_large_cap_buyer: bool
    mega_deal_flag: bool
    sub_scale_flag: bool
    small_cap_flag: bool   # informational; small-cap is NOT a negative signal

    rationale: str
    data_gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_target_size(inp: TargetSizeInput) -> TargetSizeResult:
    """Classify a target into a size bucket and annotate buyer-universe signals.

    EV is preferred over market cap; if EV is unavailable but MC is present,
    MC is used as the reference value with a note in ``data_gaps``.

    No score penalties are applied.
    """
    data_gaps: list[str] = []

    # Choose reference value
    if inp.enterprise_value_millions is not None:
        ref_value: Optional[float] = inp.enterprise_value_millions
        ref_source: Literal["enterprise_value", "market_cap", "none"] = "enterprise_value"
    elif inp.market_cap_millions is not None:
        ref_value = inp.market_cap_millions
        ref_source = "market_cap"
        data_gaps.append("enterprise_value_missing: using market_cap as proxy")
    else:
        ref_value = None
        ref_source = "none"
        data_gaps.append("enterprise_value_missing")
        data_gaps.append("market_cap_missing")

    # Classify
    if ref_value is None:
        bucket = TargetSizeBucket.UNKNOWN
        rationale = "No market data available — size bucket unknown."
    else:
        # Use absolute value: negative EV (net-cash companies) still maps to
        # the sub-scale bucket rather than erroring.
        abs_ref = abs(ref_value)
        bucket = TargetSizeBucket.MEGA_DEAL  # default if nothing matches
        for upper, b in _SIZE_THRESHOLDS:
            if abs_ref < upper:
                bucket = b
                break
        rationale = _rationale(bucket, ref_value, ref_source)

    min_cap = _MIN_BUYER_CAPACITY[bucket]

    return TargetSizeResult(
        size_bucket=bucket,
        reference_value_millions=ref_value,
        reference_source=ref_source,
        minimum_buyer_capacity_needed_millions=min_cap,
        requires_large_cap_buyer=bucket in (TargetSizeBucket.LARGE_CAP, TargetSizeBucket.MEGA_DEAL),
        mega_deal_flag=bucket == TargetSizeBucket.MEGA_DEAL,
        sub_scale_flag=bucket == TargetSizeBucket.SUB_SCALE,
        small_cap_flag=bucket == TargetSizeBucket.SMALL_CAP,
        rationale=rationale,
        data_gaps=data_gaps,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rationale(
    bucket: TargetSizeBucket,
    ref_value: float,
    ref_source: str,
) -> str:
    src_label = "EV" if ref_source == "enterprise_value" else "MC"
    val_str = f"${ref_value:,.0f}M {src_label}"

    messages: dict[TargetSizeBucket, str] = {
        TargetSizeBucket.SUB_SCALE: (
            f"{val_str} — sub-scale; bolt-on acquisition only. "
            "Standalone deal unlikely without a strategic platform rationale."
        ),
        TargetSizeBucket.SMALL_CAP: (
            f"{val_str} — small-cap; standard biotech M&A range. "
            "Accessible to mid-cap and large-cap acquirers."
        ),
        TargetSizeBucket.MID_CAP: (
            f"{val_str} — mid-cap; core M&A universe. "
            "Accessible to large-cap acquirers with standard deal financing."
        ),
        TargetSizeBucket.LARGE_CAP: (
            f"{val_str} — large-cap; requires investment-grade acquirer with "
            "substantial balance sheet capacity."
        ),
        TargetSizeBucket.MEGA_DEAL: (
            f"{val_str} — mega-deal tier; accessible to top-10 global pharma only. "
            "Rare; typically requires regulatory scrutiny and consortium financing."
        ),
    }
    return messages.get(bucket, f"{val_str} — size bucket: {bucket.value}.")
