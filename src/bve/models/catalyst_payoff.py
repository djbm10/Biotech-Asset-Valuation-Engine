"""
P2.5 — Catalyst payoff simulation.

Computes success/failure EV scenarios directly from the valuation engine
objects (no YAML reload required), using the same formula as
intelligence/catalyst_ev.py:

    upside          = value_if_success - current_value
    downside        = current_value - value_if_failure
    delta_ev        = pos × upside - (1 - pos) × downside
    variance        = pos × (upside - delta_ev)² + (1-pos) × (-downside - delta_ev)²
    std_dev         = sqrt(variance)
    signal_strength = delta_ev / max(std_dev, |delta_ev| × std_floor_mult)
    asymmetry_ratio = upside / downside  (inf when downside == 0)

Integrated into ValuationOutput as an auto-populated field from
ValuationEngine.run() — no separate CLI step required.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bve.entities.asset import Asset
    from bve.entities.trial import ClinicalTrial
    from bve.models.market_model import MarketModel
    from bve.models.rnpv_model import RNPVResult
    from bve.models.deal_economics import DealEconomics

_STD_FLOOR_MULTIPLIER = 0.50


@dataclass(frozen=True)
class CatalystPayoffResult:
    """
    EV decomposition around the next binary catalyst event.

    Attributes
    ----------
    current_value : float
        rNPV at base-case PoS (same as ValuationOutput.rnpv.rnpv_millions).
    value_if_success : float
        rNPV when all trial success_probabilities are forced to 1.0.
    value_if_failure : float
        rNPV when all trial success_probabilities are forced to 0.0.
    current_pos : float
        Cumulative probability of approval used for weighting.
    upside : float
        value_if_success - current_value (≥ 0 for typical biotech).
    downside : float
        current_value - value_if_failure (magnitude of downside loss).
    delta_ev : float
        Expected value change from the catalyst:
        delta_ev = pos × upside - (1-pos) × downside.
    std_dev : float
        Standard deviation of the binary outcome distribution.
    signal_strength : float
        delta_ev / std_floor — Sharpe-like ratio of EV vs uncertainty.
        > 0 = positive EV; < 0 = negative EV.
    asymmetry_ratio : float
        upside / downside. > 1 = asymmetric upside; inf when downside == 0.
    """
    current_value: float
    value_if_success: float
    value_if_failure: float
    current_pos: float
    upside: float
    downside: float
    delta_ev: float
    std_dev: float
    signal_strength: float
    asymmetry_ratio: float

    @property
    def is_asymmetric_upside(self) -> bool:
        """True when upside / downside > 1.5 (typical threshold for a long catalyst)."""
        return math.isfinite(self.asymmetry_ratio) and self.asymmetry_ratio > 1.5

    @property
    def ev_label(self) -> str:
        if self.delta_ev > 10:
            return "positive"
        if self.delta_ev < -10:
            return "negative"
        return "neutral"


def compute_catalyst_payoff(
    asset: "Asset",
    trials: "list[ClinicalTrial]",
    market_model: "MarketModel",
    rnpv: "RNPVResult",
    *,
    loe_profile: Optional[dict] = None,
    deal: Optional["DealEconomics"] = None,
    std_floor_multiplier: float = _STD_FLOOR_MULTIPLIER,
) -> CatalystPayoffResult:
    """
    Compute binary catalyst EV decomposition from existing engine objects.

    Parameters
    ----------
    asset, trials, market_model :
        Same objects passed to ValuationEngine — not modified.
    rnpv :
        Result from the base-case engine run (provides current_value and pos).
    loe_profile, deal :
        Fixed economic context, forwarded to compute_rnpv_full() unchanged.
    std_floor_multiplier :
        Floor on std_dev for signal_strength computation (default 0.50).

    Returns
    -------
    CatalystPayoffResult
    """
    from bve.models.rnpv_model import compute_rnpv_full

    current_value = float(rnpv.rnpv_millions)
    current_pos = float(rnpv.cumulative_success_probability)

    # Success scenario: all trials forced to success_probability = 1.0
    success_trials = [
        t.model_copy(update={"success_probability": 1.0})
        for t in trials
    ]
    success_result = compute_rnpv_full(
        asset, success_trials, market_model,
        loe_profile=loe_profile, deal=deal,
    )
    value_if_success = float(success_result.rnpv_millions)

    # Failure scenario: all trials forced to success_probability = 0.0
    # Use a tiny non-zero value to avoid division-by-zero in log-odds internals
    failure_trials = [
        t.model_copy(update={"success_probability": 0.0})
        for t in trials
    ]
    failure_result = compute_rnpv_full(
        asset, failure_trials, market_model,
        loe_profile=loe_profile, deal=deal,
    )
    value_if_failure = float(failure_result.rnpv_millions)

    upside = value_if_success - current_value
    downside = current_value - value_if_failure
    delta_ev = current_pos * upside - (1.0 - current_pos) * downside

    # Variance of binary outcome distribution
    outcome_success = upside
    outcome_failure = -downside
    variance = (
        current_pos * (outcome_success - delta_ev) ** 2
        + (1.0 - current_pos) * (outcome_failure - delta_ev) ** 2
    )
    std_dev = math.sqrt(max(variance, 0.0))

    std_floor = max(std_dev, abs(delta_ev) * std_floor_multiplier)
    signal_strength = (delta_ev / std_floor) if std_floor > 0.0 else 0.0

    asymmetry_ratio = (
        upside / downside if downside > 0.0 else float("inf")
    )

    return CatalystPayoffResult(
        current_value=round(current_value, 2),
        value_if_success=round(value_if_success, 2),
        value_if_failure=round(value_if_failure, 2),
        current_pos=round(current_pos, 4),
        upside=round(upside, 2),
        downside=round(downside, 2),
        delta_ev=round(delta_ev, 2),
        std_dev=round(std_dev, 4),
        signal_strength=round(signal_strength, 4),
        asymmetry_ratio=(
            round(asymmetry_ratio, 4)
            if math.isfinite(asymmetry_ratio)
            else asymmetry_ratio
        ),
    )
