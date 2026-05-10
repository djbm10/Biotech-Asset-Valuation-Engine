"""
Scenario definitions: base / bull / bear.

Each scenario modifies key assumptions multiplicatively or additively
from the base case and re-runs the full engine (POS → revenue → competition
→ costs → tax/FCF → rNPV → NAV/share).  The final rNPV is never shocked
directly.

Two APIs
--------
Legacy (backward-compatible):
    ``ScenarioAssumptions``, ``build_scenarios()`` — simple multipliers only.

New (Sprint 31B):
    ``ScenarioShock``, ``apply_scenario_shock()``, ``build_scenarios_from_shocks()``
    — full 6-category input shock.  ScenarioResult is extended with Sprint 31D
    fields (scenario_NAV, scenario_NAV_per_share, delta_vs_base,
    key_assumption_changes, top_value_drivers, kill_criteria_triggered,
    memo_interpretation).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.market_model import MarketModel
from bve.models.rnpv_model import compute_rnpv_full
from bve.models.scenario_shock import (
    ScenarioShock,
    SHOCK_BASE,
    SHOCK_BEAR,
    SHOCK_BULL,
)

if TYPE_CHECKING:
    from bve.models.deal_economics import DealEconomics
    from bve.models.tax_profile import TaxProfile


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

    # Tax rate adjustment (additive, e.g. +0.03 for bear scenario tax increase)
    tax_rate_add: float = 0.0


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


# ---------------------------------------------------------------------------
# Sprint 31B — ScenarioShock application
# ---------------------------------------------------------------------------

def apply_scenario_shock(
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
    shock: ScenarioShock,
    deal: Optional["DealEconomics"] = None,
    tax_profile: Optional["TaxProfile"] = None,
) -> tuple[Asset, list[ClinicalTrial], MarketModel, "Optional[DealEconomics]", "Optional[TaxProfile]"]:
    """
    Apply a ScenarioShock to model inputs, returning shocked copies.

    No original object is mutated.  The caller passes the shocked inputs to
    compute_rnpv_full() or the 4-engine path.

    Returns
    -------
    (shocked_asset, shocked_trials, shocked_market, shocked_deal, shocked_tax_profile)
    """
    from bve.models.tax_profile import TaxProfile as TaxProfileModel

    s_clin = shock.clinical
    s_reg = shock.regulatory
    s_comm = shock.commercial
    s_comp = shock.competition
    s_cost = shock.costs_fcf
    s_deal = shock.deal_economics

    # ------------------------------------------------------------------
    # Asset — WACC and tax rate
    # ------------------------------------------------------------------
    new_wacc = max(0.01, asset.discount_rate + s_cost.discount_rate_delta)
    new_tax = max(0.0, min(0.99, asset.effective_tax_rate + s_cost.tax_rate_delta))
    shocked_asset = asset.model_copy(update={
        "discount_rate": new_wacc,
        "effective_tax_rate": new_tax,
    })

    # ------------------------------------------------------------------
    # Trials — POS, duration, cost per phase
    # ------------------------------------------------------------------
    # Build per-phase POS multiplier map: global pos_mult × per-phase override
    # TrialPhase enum value → multiplier
    _phase_mults: dict[str, float] = {}
    for tp in TrialPhase:
        override = s_clin.per_phase_pos_mult.get(tp.value, 1.0)
        _phase_mults[tp.value] = s_clin.pos_mult * override

    total_delay = s_reg.duration_add_years + s_reg.crl_delay_add_years

    shocked_trials: list[ClinicalTrial] = []
    for t in trials:
        phase_key = t.phase.value if hasattr(t.phase, "value") else str(t.phase)
        phase_mult = _phase_mults.get(phase_key, s_clin.pos_mult)

        new_pos = max(0.01, min(0.99, t.success_probability * phase_mult))
        new_dur = max(0.25, t.duration_years + total_delay)
        new_cost = t.cost_millions * s_cost.rd_cost_mult
        shocked_trials.append(t.model_copy(update={
            "success_probability": new_pos,
            "duration_years": new_dur,
            "cost_millions": new_cost,
        }))

    # ------------------------------------------------------------------
    # MarketModel — patients/TAM, price, penetration, payer, competition
    # ------------------------------------------------------------------
    mm_updates: dict = {"uptake_curve": None}  # always reset cached uptake

    # Patient population / TAM: label_breadth_mult × addressable_patients_mult
    population_mult = s_reg.label_breadth_mult * s_comm.addressable_patients_mult
    if market_model.addressable_patients_annual is not None:
        mm_updates["addressable_patients_annual"] = max(
            1.0, market_model.addressable_patients_annual * population_mult
        )
    if market_model.total_addressable_market_millions is not None:
        mm_updates["total_addressable_market_millions"] = max(
            0.0, market_model.total_addressable_market_millions * population_mult
        )

    # Net price
    if market_model.net_price_per_patient_usd is not None:
        mm_updates["net_price_per_patient_usd"] = max(
            0.0, market_model.net_price_per_patient_usd * s_comm.net_price_mult
        )

    # Gross-to-net rate (clamped [0, 1])
    if market_model.gross_to_net_rate is not None:
        mm_updates["gross_to_net_rate"] = max(
            0.0, min(1.0, market_model.gross_to_net_rate + s_comm.gross_to_net_rate_delta)
        )
    elif s_comm.gross_to_net_rate_delta != 0.0:
        mm_updates["gross_to_net_rate"] = max(0.0, min(1.0, s_comm.gross_to_net_rate_delta))

    # Peak penetration
    if market_model.peak_penetration is not None:
        mm_updates["peak_penetration"] = max(
            0.0, min(1.0, market_model.peak_penetration * s_comm.peak_penetration_mult)
        )

    # Years to peak
    if market_model.years_to_peak is not None:
        mm_updates["years_to_peak"] = max(
            0.5, market_model.years_to_peak + s_comm.years_to_peak_add
        )

    # COGS and SG&A
    mm_updates["cogs_rate"] = max(
        0.0, min(1.0, market_model.cogs_rate + s_cost.cogs_rate_delta)
    )
    mm_updates["sgna_rate_launch"] = max(
        0.0, min(1.0, market_model.sgna_rate_launch + s_cost.sgna_rate_delta)
    )
    mm_updates["sgna_rate_mature"] = max(
        0.0, min(1.0, market_model.sgna_rate_mature + s_cost.sgna_rate_delta)
    )

    # Payer access model
    if market_model.payer_access is not None:
        pa = market_model.payer_access
        new_access_prob = max(
            0.0, min(1.0, pa.access_probability * s_comm.payer_access_probability_mult)
        )
        new_pa_burden = max(
            0.0, min(1.0, pa.prior_auth_burden + s_comm.prior_auth_burden_delta)
        )
        mm_updates["payer_access"] = pa.model_copy(update={
            "access_probability": new_access_prob,
            "prior_auth_burden": new_pa_burden,
        })

    # Competition model
    if market_model.competition_model is not None:
        cm = market_model.competition_model
        shocked_competitors = []
        for c in cm.competitors:
            c_updates: dict = {}
            # Pipeline competitors (not yet approved): scale approval_probability
            if c.status in ("phase_2", "phase_3", "preclinical"):
                c_updates["approval_probability"] = max(
                    0.0, min(1.0, c.approval_probability * s_comp.competitor_approval_prob_mult)
                )
            # Launch timing
            if s_comp.competitor_launch_timing_add_years != 0.0:
                c_updates["launch_year_relative"] = max(
                    0.0, c.launch_year_relative + s_comp.competitor_launch_timing_add_years
                )
            # Market share
            if s_comp.competitor_market_share_mult != 1.0:
                c_updates["peak_market_share"] = (
                    c.peak_market_share * s_comp.competitor_market_share_mult
                )
            if c_updates:
                shocked_competitors.append(c.model_copy(update=c_updates))
            else:
                shocked_competitors.append(c)

        # Competition-driven price pressure (additive to base_annual_price_erosion_rate)
        cm_updates: dict = {"competitors": shocked_competitors}
        if s_comp.competition_price_pressure_delta != 0.0:
            current_erosion = cm.base_annual_price_erosion_rate or 0.0
            cm_updates["base_annual_price_erosion_rate"] = max(
                0.0, current_erosion + s_comp.competition_price_pressure_delta
            )
        mm_updates["competition_model"] = cm.model_copy(update=cm_updates)

    shocked_market = market_model.model_copy(update=mm_updates)

    # ------------------------------------------------------------------
    # DealEconomics — royalty, profit-share, cost-share, milestones
    # ------------------------------------------------------------------
    shocked_deal: Optional[DealEconomics] = deal
    if deal is not None:
        deal_updates: dict = {}
        if s_deal.royalty_rate_override is not None:
            deal_updates["royalty_rate"] = s_deal.royalty_rate_override
        if s_deal.profit_share_rate_override is not None:
            deal_updates["profit_share_rate"] = s_deal.profit_share_rate_override
        if s_deal.cdev_cost_share_override is not None:
            deal_updates["cdev_cost_share"] = s_deal.cdev_cost_share_override
        if s_deal.milestone_payment_mult != 1.0 or s_deal.milestone_receipt_mult != 1.0:
            shocked_milestones = []
            for m in deal.milestones:
                if m.direction == "payable":
                    shocked_milestones.append(m.model_copy(
                        update={"amount_millions": m.amount_millions * s_deal.milestone_payment_mult}
                    ))
                else:
                    shocked_milestones.append(m.model_copy(
                        update={"amount_millions": m.amount_millions * s_deal.milestone_receipt_mult}
                    ))
            deal_updates["milestones"] = shocked_milestones
        if deal_updates:
            shocked_deal = deal.model_copy(update=deal_updates)

    # ------------------------------------------------------------------
    # TaxProfile — capex/WC and tax rate (already handled via asset for simple tax)
    # ------------------------------------------------------------------
    shocked_tax: Optional[TaxProfileModel] = tax_profile
    if tax_profile is not None:
        tp_updates: dict = {}
        if s_cost.maintenance_capex_rate_delta != 0.0:
            tp_updates["annual_maintenance_capex_rate"] = max(
                0.0, min(1.0, tax_profile.annual_maintenance_capex_rate + s_cost.maintenance_capex_rate_delta)
            )
        if s_cost.working_capital_rate_delta != 0.0:
            tp_updates["working_capital_rate"] = max(
                0.0, min(1.0, tax_profile.working_capital_rate + s_cost.working_capital_rate_delta)
            )
        if s_cost.tax_rate_delta != 0.0:
            tp_updates["effective_tax_rate"] = max(
                0.0, min(0.99, tax_profile.effective_tax_rate + s_cost.tax_rate_delta)
            )
        if tp_updates:
            shocked_tax = tax_profile.model_copy(update=tp_updates)

    return shocked_asset, shocked_trials, shocked_market, shocked_deal, shocked_tax


def _apply_shock_scenario(
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
    shock: ScenarioShock,
    net_cash_millions: float = 0.0,
    shares_outstanding_millions: float = 1.0,
    *,
    loe_profile: Optional[dict] = None,
    deal: Optional["DealEconomics"] = None,
    tax_profile: Optional["TaxProfile"] = None,
) -> ScenarioResult:
    """Run the full engine with a ScenarioShock applied to all inputs."""
    s_asset, s_trials, s_market, s_deal, s_tax = apply_scenario_shock(
        asset, trials, market_model, shock, deal, tax_profile
    )

    result = compute_rnpv_full(
        s_asset, s_trials, s_market,
        loe_profile=loe_profile,
        deal=s_deal,
        tax_profile=s_tax,
    )

    nav = result.rnpv_millions + net_cash_millions
    nav_ps = nav / shares_outstanding_millions if shares_outstanding_millions else 0.0

    return ScenarioResult(
        label=shock.label,
        description=shock.description,
        rnpv_millions=result.rnpv_millions,
        cumulative_success_probability=result.cumulative_success_probability,
        peak_sales_millions=result.peak_sales_millions,
        years_to_launch=result.years_to_launch,
        nav_millions=nav,
        nav_per_share=nav_ps,
    )


def build_scenarios_from_shocks(
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
    net_cash_millions: float = 0.0,
    shares_outstanding_millions: float = 1.0,
    shocks: Optional[list[ScenarioShock]] = None,
    *,
    loe_profile: Optional[dict] = None,
    deal: Optional["DealEconomics"] = None,
    tax_profile: Optional["TaxProfile"] = None,
) -> ScenarioSet:
    """
    Build Bull/Base/Bear scenarios using full ScenarioShock input shocks.

    Each scenario reruns the complete engine chain (POS → revenue →
    competition → costs → tax/FCF → rNPV → NAV/share).  The final rNPV
    is never shocked directly.

    Parameters
    ----------
    shocks
        List of exactly 3 ScenarioShock objects [bull, base, bear].
        Defaults to [SHOCK_BULL, SHOCK_BASE, SHOCK_BEAR].
    """
    _shocks = shocks or [SHOCK_BULL, SHOCK_BASE, SHOCK_BEAR]
    if len(_shocks) != 3:
        raise ValueError(
            f"build_scenarios_from_shocks requires exactly 3 shocks (bull, base, bear), "
            f"got {len(_shocks)}"
        )
    results = [
        _apply_shock_scenario(
            asset, trials, market_model, s,
            net_cash_millions, shares_outstanding_millions,
            loe_profile=loe_profile, deal=deal, tax_profile=tax_profile,
        )
        for s in _shocks
    ]
    return ScenarioSet(bull=results[0], base=results[1], bear=results[2])


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
    *,
    loe_profile: Optional[dict] = None,
    deal: Optional["DealEconomics"] = None,
) -> ScenarioResult:
    r = max(0.01, asset.discount_rate + assumptions.discount_rate_add)
    new_tax = max(0.0, min(0.50, asset.effective_tax_rate + assumptions.tax_rate_add))
    sim_asset = asset.model_copy(update={"discount_rate": r, "effective_tax_rate": new_tax})

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

    result = compute_rnpv_full(sim_asset, sim_trials, sim_market, loe_profile=loe_profile, deal=deal)

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
    *,
    loe_profile: Optional[dict] = None,
    deal: Optional["DealEconomics"] = None,
) -> ScenarioSet:
    """Build bull/base/bear rNPV scenarios on the full economic stack."""
    scenarios = custom_scenarios or [SCENARIO_BULL, SCENARIO_BASE, SCENARIO_BEAR]
    results = [
        _apply_scenario(
            asset, trials, market_model, s,
            net_cash_millions, shares_outstanding_millions,
            loe_profile=loe_profile, deal=deal,
        )
        for s in scenarios[:3]
    ]
    return ScenarioSet(bull=results[0], base=results[1], bear=results[2])
