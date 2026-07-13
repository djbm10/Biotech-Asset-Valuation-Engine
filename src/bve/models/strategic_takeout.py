"""Strategic takeout value — a configurable control-premium layer over rNPV.

rNPV is *intrinsic* (standalone) value: the probability-weighted DCF of the asset
developed by its current holder. Observed biotech acquisitions price well above
intrinsic value — a control premium plus strategic value (assembled workforce /
platform know-how, synergies, pipeline optionality beyond the modeled indication).

This module models that gap as a single, transparent control premium that applies
ONLY to the estimated acquisition (takeout) price. It NEVER touches rNPV, revenue,
cost, scenarios, or Monte Carlo. rNPV remains the intrinsic floor; the strategic
takeout value is purely additive on top.

v1 deliberately uses one configurable premium band (low / base / high) rather than a
multi-component decomposition, to avoid fake precision. The premium's drivers are
named qualitatively in ``rationale`` but are not quantified separately.

Suppression rule: a premium multiplier on a non-positive rNPV is meaningless, and
distressed / option-value deals require a separate strategic option model — not a
control-premium multiplier. So ``compute_strategic_takeout`` returns ``None`` when
rNPV <= 0; callers should surface ``NON_POSITIVE_RNPV_NOTE`` in that case.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

# Default control-premium band over intrinsic rNPV (literature-backed 30–80%).
DEFAULT_LOW_PREMIUM_PCT: float = 0.30
DEFAULT_BASE_PREMIUM_PCT: float = 0.50
DEFAULT_HIGH_PREMIUM_PCT: float = 0.80

# Qualitative drivers of the premium — named, not quantified separately (v1).
DEFAULT_PREMIUM_RATIONALE: tuple[str, ...] = (
    "Acquisition control premium over intrinsic value",
    "Assembled workforce / platform know-how",
    "Strategic synergies (cost savings, cross-selling)",
    "Pipeline optionality beyond the modeled indication(s)",
)

# Note surfaced when the takeout value is suppressed for non-positive rNPV.
NON_POSITIVE_RNPV_NOTE: str = (
    "Not shown because standalone rNPV is non-positive; "
    "strategic option value not modeled."
)

# Note surfaced when the takeout layer is not enabled (no YAML block / enabled: false).
NOT_ENABLED_NOTE: str = (
    "Not shown because the strategic takeout layer is not enabled; "
    "add a strategic_takeout block (enabled: true) to estimate a takeout value."
)


class StrategicTakeoutPremium(BaseModel):
    """Configurable control-premium band applied over intrinsic rNPV.

    Premiums are fractions (``0.50`` == +50%). Defaults to the 30/50/80 band.
    """

    model_config = {"frozen": True}

    low_premium_pct: float = Field(default=DEFAULT_LOW_PREMIUM_PCT, ge=0.0)
    base_premium_pct: float = Field(default=DEFAULT_BASE_PREMIUM_PCT, ge=0.0)
    high_premium_pct: float = Field(default=DEFAULT_HIGH_PREMIUM_PCT, ge=0.0)
    rationale: tuple[str, ...] = Field(default=DEFAULT_PREMIUM_RATIONALE)

    @model_validator(mode="after")
    def _check_ordering(self) -> "StrategicTakeoutPremium":
        if not (self.low_premium_pct <= self.base_premium_pct <= self.high_premium_pct):
            raise ValueError(
                "strategic takeout premiums must satisfy low <= base <= high "
                f"(got {self.low_premium_pct}, {self.base_premium_pct}, "
                f"{self.high_premium_pct})"
            )
        return self


DEFAULT_STRATEGIC_TAKEOUT_PREMIUM = StrategicTakeoutPremium()


class StrategicTakeoutValue(BaseModel):
    """Estimated acquisition (takeout) price band derived from rNPV + premium.

    ``floor_millions`` is the intrinsic rNPV; low/base/high apply the premium band.
    """

    model_config = {"frozen": True}

    floor_millions: float        # = intrinsic rNPV
    low_millions: float          # rNPV × (1 + low_premium_pct)
    base_millions: float         # rNPV × (1 + base_premium_pct)
    high_millions: float         # rNPV × (1 + high_premium_pct)
    low_premium_pct: float
    base_premium_pct: float
    high_premium_pct: float
    rationale: tuple[str, ...]


def compute_strategic_takeout(
    rnpv_millions: float,
    premium: Optional[StrategicTakeoutPremium] = None,
) -> Optional[StrategicTakeoutValue]:
    """Apply a control premium to intrinsic rNPV → estimated takeout band.

    Returns ``None`` when ``rnpv_millions <= 0`` (see module docstring for why).
    """
    if rnpv_millions <= 0:
        return None
    p = premium or DEFAULT_STRATEGIC_TAKEOUT_PREMIUM
    return StrategicTakeoutValue(
        floor_millions=round(rnpv_millions, 2),
        low_millions=round(rnpv_millions * (1.0 + p.low_premium_pct), 2),
        base_millions=round(rnpv_millions * (1.0 + p.base_premium_pct), 2),
        high_millions=round(rnpv_millions * (1.0 + p.high_premium_pct), 2),
        low_premium_pct=p.low_premium_pct,
        base_premium_pct=p.base_premium_pct,
        high_premium_pct=p.high_premium_pct,
        rationale=p.rationale,
    )
