"""
Risk-adjusted Net Present Value (rNPV) model.

Methodology
-----------
Walk forward through remaining clinical phases:

  For each phase i:
    - P(reaching phase i) = ∏ success_prob[j] for j < i
    - PV(cost_i) = cost_i / (1+r)^(midpoint of phase i)
    - Probability-weighted cost = PV(cost_i) × P(reaching phase i)

  After all phases:
    - P(approval) = ∏ success_prob[all phases]
    - Project EBIT from year 1 to patent_life post-launch
    - PV(revenue_yr) = EBIT_yr / (1+r)^(years_to_launch + yr)
    - rNPV = P(approval) × Σ PV(EBIT) - Σ probability-weighted PV(cost)

  Ownership adjustment: all revenue terms scaled by asset.net_ownership
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from bve.config.constants import PHASE_ORDER
from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial
from bve.models.market_model import MarketModel


class PhaseBreakdown(BaseModel):
    phase: str
    prob_reaching: float
    pv_cost_gross: float
    pv_cost_weighted: float
    duration_years: float
    success_probability: float


class RNPVResult(BaseModel):
    asset_id: str
    asset_name: str

    # Primary output
    rnpv_millions: float = Field(description="Risk-adjusted NPV in USD millions")

    # Revenue decomposition
    gross_revenue_pv_millions: float = Field(description="Sum of PV(EBIT) pre-probability weighting")
    probability_adjusted_revenue_pv_millions: float
    trial_costs_pv_millions: float = Field(description="Sum of probability-weighted PV(costs)")

    # Key metrics
    cumulative_success_probability: float
    years_to_launch: float
    peak_sales_millions: float
    discount_rate: float
    net_ownership: float

    # Per-phase detail
    phase_breakdown: list[PhaseBreakdown] = Field(default_factory=list)

    # NAV convenience (set externally by valuation engine)
    nav_millions: float = 0.0
    nav_per_share: float = 0.0

    @property
    def probability_approval_pct(self) -> str:
        return f"{self.cumulative_success_probability:.1%}"


def compute_rnpv(
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
) -> RNPVResult:
    """
    Compute rNPV for a single asset given remaining trials and market assumptions.

    Parameters
    ----------
    asset:         Asset entity (provides discount_rate, net_ownership)
    trials:        All remaining ClinicalTrial objects for this asset (any order)
    market_model:  Commercial assumptions (revenue curve, patent life)

    Returns
    -------
    RNPVResult with full breakdown
    """
    r = asset.discount_rate
    ownership = asset.net_ownership

    # Filter + sort by phase order
    asset_trials = [t for t in trials if t.asset_id == asset.id]
    sorted_trials = sorted(asset_trials, key=lambda t: PHASE_ORDER[t.phase.value])

    # --- Walk through clinical phases ---
    current_year: float = 0.0
    cum_prob: float = 1.0          # probability of currently being at this stage
    trial_costs_pv: float = 0.0
    breakdown: list[PhaseBreakdown] = []

    for trial in sorted_trials:
        mid_year = current_year + trial.duration_years / 2.0
        pv_cost_gross = trial.cost_millions / (1.0 + r) ** mid_year
        pv_cost_weighted = pv_cost_gross * cum_prob

        trial_costs_pv += pv_cost_weighted
        breakdown.append(PhaseBreakdown(
            phase=trial.phase.value,
            prob_reaching=round(cum_prob, 4),
            pv_cost_gross=round(pv_cost_gross, 2),
            pv_cost_weighted=round(pv_cost_weighted, 2),
            duration_years=trial.duration_years,
            success_probability=trial.success_probability,
        ))

        current_year += trial.duration_years
        cum_prob *= trial.success_probability

    years_to_launch = current_year

    # --- Project commercial cash flows ---
    gross_revenue_pv: float = 0.0
    for yr in range(1, market_model.patent_life_years + 1):
        ebit = market_model.ebit_in_year(yr) * ownership
        abs_year = years_to_launch + yr
        gross_revenue_pv += ebit / (1.0 + r) ** abs_year

    probability_adjusted_revenue_pv = gross_revenue_pv * cum_prob

    rnpv = probability_adjusted_revenue_pv - trial_costs_pv

    return RNPVResult(
        asset_id=asset.id,
        asset_name=asset.name,
        rnpv_millions=round(rnpv, 2),
        gross_revenue_pv_millions=round(gross_revenue_pv, 2),
        probability_adjusted_revenue_pv_millions=round(probability_adjusted_revenue_pv, 2),
        trial_costs_pv_millions=round(trial_costs_pv, 2),
        cumulative_success_probability=round(cum_prob, 6),
        years_to_launch=round(years_to_launch, 1),
        peak_sales_millions=round(market_model.peak_sales_millions, 2),
        discount_rate=r,
        net_ownership=ownership,
        phase_breakdown=breakdown,
    )
