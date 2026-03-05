"""
Scenario definitions: base / bull / bear.

Each scenario modifies key assumptions multiplicatively or additively
from the base case and re-runs rNPV.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial
from bve.models.market_model import MarketModel
from bve.models.rnpv_model import RNPVResult, compute_rnpv


class ScenarioAssumptions(BaseModel):
    """Multipliers applied to the base-case inputs for a scenario."""
    label: str
    description: str

    # Market multipliers (applied to peak_sales)
    peak_sales_mult: float = 1.0

    # Success probability multipliers per phase
    pos_mult: float = 1.0      # applies to all phases uniformly

    # Timing (additive years on each phase duration)
    duration_add_years: float = 0.0

    # Cost multipliers
    cost_mult: float = 1.0

    # Discount rate adjustment (additive)
    discount_rate_add: float = 0.0


SCENARIO_BULL = ScenarioAssumptions(
    label="Bull",
    description="Best-in-class clinical data; faster timelines; larger addressable market",
    peak_sales_mult=1.50,
    pos_mult=1.30,
    duration_add_years=-0.5,
    cost_mult=0.90,
    discount_rate_add=-0.01,
)

SCENARIO_BASE = ScenarioAssumptions(
    label="Base",
    description="Base case reflecting analyst estimates",
    peak_sales_mult=1.00,
    pos_mult=1.00,
    duration_add_years=0.0,
    cost_mult=1.00,
    discount_rate_add=0.00,
)

SCENARIO_BEAR = ScenarioAssumptions(
    label="Bear",
    description="Mixed clinical signal; pricing pressure; delays",
    peak_sales_mult=0.55,
    pos_mult=0.70,
    duration_add_years=1.0,
    cost_mult=1.20,
    discount_rate_add=0.02,
)


class ScenarioResult(BaseModel):
    label: str
    description: str
    rnpv_millions: float
    cumulative_success_probability: float
    peak_sales_millions: float
    years_to_launch: float
    nav_millions: float = 0.0
    nav_per_share: float = 0.0


class ScenarioSet(BaseModel):
    bull: ScenarioResult
    base: ScenarioResult
    bear: ScenarioResult

    @property
    def as_list(self) -> list[ScenarioResult]:
        return [self.bull, self.base, self.bear]

    @property
    def upside_downside_ratio(self) -> Optional[float]:
        """Bull/Bear rNPV ratio — rough risk-reward metric."""
        if self.bear.rnpv_millions == 0:
            return None
        return round(self.bull.rnpv_millions / self.bear.rnpv_millions, 2)


def _apply_scenario(
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
    assumptions: ScenarioAssumptions,
    net_cash_millions: float = 0.0,
    shares_outstanding_millions: float = 1.0,
) -> ScenarioResult:
    r = max(0.01, asset.discount_rate + assumptions.discount_rate_add)
    sim_asset = asset.model_copy(update={"discount_rate": r})

    # Scale market
    if market_model.total_addressable_market_millions is not None:
        new_tam = market_model.total_addressable_market_millions * assumptions.peak_sales_mult
        sim_market = market_model.model_copy(
            update={"total_addressable_market_millions": new_tam, "uptake_curve": None}
        )
    else:
        new_price = (market_model.net_price_per_patient_usd or 1) * assumptions.peak_sales_mult
        sim_market = market_model.model_copy(
            update={"net_price_per_patient_usd": new_price, "uptake_curve": None}
        )

    # Scale trials
    sim_trials = []
    for t in trials:
        new_pos = min(0.99, t.success_probability * assumptions.pos_mult)
        new_dur = max(0.5, t.duration_years + assumptions.duration_add_years)
        new_cost = t.cost_millions * assumptions.cost_mult
        sim_trials.append(t.model_copy(update={
            "success_probability": new_pos,
            "duration_years": new_dur,
            "cost_millions": new_cost,
        }))

    result = compute_rnpv(sim_asset, sim_trials, sim_market)

    nav = result.rnpv_millions + net_cash_millions
    nav_ps = nav / shares_outstanding_millions if shares_outstanding_millions else 0.0

    return ScenarioResult(
        label=assumptions.label,
        description=assumptions.description,
        rnpv_millions=result.rnpv_millions,
        cumulative_success_probability=result.cumulative_success_probability,
        peak_sales_millions=result.peak_sales_millions,
        years_to_launch=result.years_to_launch,
        nav_millions=nav,
        nav_per_share=nav_ps,
    )


def build_scenarios(
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
    net_cash_millions: float = 0.0,
    shares_outstanding_millions: float = 1.0,
    custom_scenarios: Optional[list[ScenarioAssumptions]] = None,
) -> ScenarioSet:
    """Build bull/base/bear rNPV scenarios."""
    scenarios = custom_scenarios or [SCENARIO_BULL, SCENARIO_BASE, SCENARIO_BEAR]
    results = [
        _apply_scenario(asset, trials, market_model, s, net_cash_millions, shares_outstanding_millions)
        for s in scenarios[:3]
    ]
    return ScenarioSet(bull=results[0], base=results[1], bear=results[2])
