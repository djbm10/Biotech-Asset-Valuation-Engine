"""Explicit runway, raise-timing, dilution, and financing-adjusted value model."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class BurnProfile(BaseModel):
    """Quarterly burn under three scenarios."""
    bull_quarterly_burn_millions: float = Field(ge=0.0)
    base_quarterly_burn_millions: float = Field(ge=0.0)
    bear_quarterly_burn_millions: float = Field(ge=0.0)


class RaiseScenario(BaseModel):
    label: str              # "no_raise" / "small_bridge" / "standard_followon" / "dilutive" / "partnership" / "distressed"
    probability: float = Field(ge=0.0, le=1.0)
    expected_timing_months: float = 0.0
    gross_proceeds_millions: float = 0.0
    expected_dilution_pct: float = Field(ge=0.0, le=1.0, default=0.0)
    post_raise_runway_months: Optional[float] = None


class FinancingModelResult(BaseModel):
    company_id: str
    as_of_date: date
    cash_millions: float
    debt_millions: float
    net_cash_millions: float
    burn_profile: BurnProfile
    runway_months_bull: float
    runway_months_base: float
    runway_months_bear: float
    months_to_next_catalyst: Optional[float] = None
    capital_needed_to_catalyst_millions: float = 0.0
    capital_needed_to_approval_millions: float = 0.0
    probability_needs_raise_before_catalyst: float = Field(ge=0.0, le=1.0, default=0.0)
    expected_raise_timing_months: float = 0.0
    expected_raise_size_millions: float = 0.0
    expected_dilution_pct_low: float = 0.0
    expected_dilution_pct_base: float = 0.0
    expected_dilution_pct_high: float = 0.0
    raise_scenarios: list[RaiseScenario] = Field(default_factory=list)
    distress_risk: float = Field(ge=0.0, le=1.0, default=0.0)
    financing_risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    financing_risk_tier: str = "low"    # "low" / "medium" / "high" / "critical"
    financing_adjusted_ev_millions: float = 0.0
    summary: str = ""


def compute_financing_model(
    *,
    company_id: str,
    as_of_date: date,
    cash_millions: float,
    debt_millions: float,
    burn_profile: BurnProfile,
    months_to_next_catalyst: Optional[float] = None,
    total_trial_cost_remaining_millions: float = 0.0,
    current_ev_millions: float = 0.0,
) -> FinancingModelResult:
    """
    Compute runway, raise probability, dilution band, and financing-adjusted EV.

    Runway = net_cash / (quarterly_burn / 3) expressed in months.
    Capital needed to catalyst = months_to_next_catalyst / 3 × quarterly_burn - net_cash (floor 0).
    Capital to approval = total_trial_cost_remaining - net_cash (floor 0).

    P(raise before catalyst):
        if runway_base < months_to_next_catalyst → high (0.75)
        if runway_base < 1.5 × months_to_next_catalyst → medium (0.40)
        else → low (0.10)

    Financing risk score = weighted average of (1 - runway_base/24) and capital_needed/current_ev.
    Financing-adjusted EV = EV × (1 - expected_dilution_base).

    Distress risk: bear runway < 3 months → 0.8; < 6 → 0.4; else → 0.1.
    """
    net_cash = cash_millions - debt_millions

    monthly_burn_bull = burn_profile.bull_quarterly_burn_millions / 3
    monthly_burn_base = burn_profile.base_quarterly_burn_millions / 3
    monthly_burn_bear = burn_profile.bear_quarterly_burn_millions / 3

    def runway(net: float, monthly: float) -> float:
        return net / monthly if monthly > 0 else 999.0

    rwy_bull = runway(net_cash, monthly_burn_bull)
    rwy_base = runway(net_cash, monthly_burn_base)
    rwy_bear = runway(net_cash, monthly_burn_bear)

    cap_to_catalyst = 0.0
    p_raise = 0.10
    if months_to_next_catalyst is not None:
        needed = months_to_next_catalyst * monthly_burn_base - net_cash
        cap_to_catalyst = max(0.0, needed)
        if rwy_base < months_to_next_catalyst:
            p_raise = 0.75
        elif rwy_base < 1.5 * months_to_next_catalyst:
            p_raise = 0.40

    cap_to_approval = max(0.0, total_trial_cost_remaining_millions - net_cash)

    # Dilution band — rough estimate based on raise size as % of market cap
    base_raise = max(0.0, cap_to_catalyst) * 1.2  # 20% buffer
    dil_base = min(0.50, base_raise / current_ev_millions) if current_ev_millions > 0 else 0.0
    dil_low = dil_base * 0.5
    dil_high = min(0.70, dil_base * 1.8)

    # Distress risk
    if rwy_bear < 3:
        distress = 0.80
    elif rwy_bear < 6:
        distress = 0.40
    else:
        distress = max(0.05, 1.0 - rwy_bear / 24.0)

    # Financing risk score
    runway_score = min(1.0, max(0.0, 1.0 - rwy_base / 24.0))
    cap_score = min(1.0, cap_to_catalyst / current_ev_millions) if current_ev_millions > 0 else 0.0
    fin_risk = round((runway_score * 0.6 + cap_score * 0.4), 3)

    tier = "low" if fin_risk < 0.3 else "medium" if fin_risk < 0.55 else "high" if fin_risk < 0.75 else "critical"

    fin_adj_ev = current_ev_millions * (1 - dil_base) if current_ev_millions > 0 else 0.0

    raise_scenarios = [
        RaiseScenario(label="no_raise", probability=1 - p_raise, expected_timing_months=0, gross_proceeds_millions=0, expected_dilution_pct=0),
        RaiseScenario(label="standard_followon", probability=p_raise * 0.6, expected_timing_months=(months_to_next_catalyst or 6) * 0.5, gross_proceeds_millions=base_raise, expected_dilution_pct=dil_base),
        RaiseScenario(label="dilutive", probability=p_raise * 0.3, expected_timing_months=(months_to_next_catalyst or 6) * 0.3, gross_proceeds_millions=base_raise * 0.7, expected_dilution_pct=dil_high),
        RaiseScenario(label="distressed", probability=p_raise * 0.1, expected_timing_months=2, gross_proceeds_millions=base_raise * 0.5, expected_dilution_pct=min(0.70, dil_high * 1.5)),
    ]

    summary = (f"Net cash ${net_cash:.0f}M. Base runway {rwy_base:.1f}m. "
               f"P(raise before catalyst) {p_raise:.0%}. Financing risk: {tier}.")

    return FinancingModelResult(
        company_id=company_id, as_of_date=as_of_date,
        cash_millions=cash_millions, debt_millions=debt_millions, net_cash_millions=net_cash,
        burn_profile=burn_profile,
        runway_months_bull=round(rwy_bull, 1), runway_months_base=round(rwy_base, 1), runway_months_bear=round(rwy_bear, 1),
        months_to_next_catalyst=months_to_next_catalyst,
        capital_needed_to_catalyst_millions=round(cap_to_catalyst, 1),
        capital_needed_to_approval_millions=round(cap_to_approval, 1),
        probability_needs_raise_before_catalyst=p_raise,
        expected_raise_timing_months=(months_to_next_catalyst or 6) * 0.5 if p_raise > 0.15 else 0,
        expected_raise_size_millions=round(base_raise, 1),
        expected_dilution_pct_low=round(dil_low, 3),
        expected_dilution_pct_base=round(dil_base, 3),
        expected_dilution_pct_high=round(dil_high, 3),
        raise_scenarios=raise_scenarios,
        distress_risk=round(distress, 3),
        financing_risk_score=fin_risk,
        financing_risk_tier=tier,
        financing_adjusted_ev_millions=round(fin_adj_ev, 1),
        summary=summary,
    )
