"""
RNPVModel — combines ProbabilityResult, RevenueStream, and CostStream into rNPV,
optionally applying deal-layer economics (royalty stacking, receivable milestones,
upfront receipts).

This model only does:
  - Discounting EBIT cash flows to present value (anchored to years_to_approval)
  - Applying effective ownership (asset.net_ownership stacked with deal.royalty_rate)
  - Multiplying PV(revenue) by P(approval)
  - Subtracting probability-weighted PV(costs) [already computed by CostModel]
  - Adding PV(receivable milestones) and upfront receipts

It does not recompute POS, timelines, launch timing, or revenue details.

Deal economics boundary
-----------------------
RevenueModel is NEVER given DealEconomics.  Revenue is gross commercial revenue.
The ownership reduction (royalty) happens here, after revenue is modelled.

Royalty stacking:
  effective_net_ownership = asset.net_ownership × (1 − deal.royalty_rate)
  Setting deal.royalty_rate = 0.0 (default) leaves asset.net_ownership unchanged.

Entry-point hierarchy
---------------------
compute_rnpv_full(asset, trials, market, *, loe_profile, deal)
  Full economic stack: LOE erosion + deal economics.
  Used by ValuationEngine.run(), Monte Carlo, scenarios, sensitivity analysis.

compute_rnpv(asset, trials, market)
  Thin backward-compatible wrapper — no LOE, no deal economics.
  Kept so any external callers outside the engine continue to work unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial
from bve.models.cost_model import CostModel, CostStream
from bve.models.market_model import MarketModel
from bve.models.probability_model import ProbabilityModel, ProbabilityResult
from bve.models.revenue_model import RevenueModel, RevenueStream

if TYPE_CHECKING:
    from bve.models.deal_economics import DealEconomics


# ---------------------------------------------------------------------------
# Result objects (PhaseBreakdown kept for backward compatibility)
# ---------------------------------------------------------------------------

class PhaseBreakdown(BaseModel):
    """Per-phase detail — kept for backward compat with outputs.py and reporting."""
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

    # Deal economics decomposition (zero when no deal terms)
    deal_milestone_receipts_pv_millions: float = 0.0  # PV of receivable milestones
    upfront_receipt_millions: float = 0.0             # Upfront receipt at t=0

    # Key metrics
    cumulative_success_probability: float
    years_to_launch: float
    peak_sales_millions: float
    discount_rate: float
    net_ownership: float   # effective ownership after asset royalty × deal royalty stacking

    # Per-phase detail (backward compat)
    phase_breakdown: list[PhaseBreakdown] = Field(default_factory=list)

    # Step 2: structured sub-objects for intermediate inspectability
    probability_result: Optional[ProbabilityResult] = None
    revenue_stream: Optional[RevenueStream] = None
    cost_stream: Optional[CostStream] = None

    # Tax treatment applied in this run
    effective_tax_rate: float = 0.21
    nol_benefit_years: int = 0

    # NAV convenience (set externally by valuation engine)
    nav_millions: float = 0.0
    nav_per_share: float = 0.0

    @property
    def probability_approval_pct(self) -> str:
        return f"{self.cumulative_success_probability:.1%}"

    @property
    def pv_revenue_millions(self) -> float:
        """Probability-adjusted PV of revenue — named consistently for downstream use."""
        return self.probability_adjusted_revenue_pv_millions

    @property
    def pv_costs_millions(self) -> float:
        """Probability-weighted PV of trial costs — named consistently for downstream use."""
        return self.trial_costs_pv_millions


# ---------------------------------------------------------------------------
# RNPVModel — discounting only
# ---------------------------------------------------------------------------

class RNPVModel:
    """
    Stateless engine that combines the three upstream results into rNPV.

    Inputs:
      asset : provides discount_rate and base net_ownership
      prob  : provides cumulative_approval_probability and years_to_approval
      rev   : provides ebit_by_year (undiscounted, 1-indexed from launch)
      cost  : provides total_pv_weighted_millions (already probability-weighted,
              includes trial R&D + milestone payables + upfront cost if deal set)
      deal  : optional DealEconomics for royalty stacking and receivable milestones

    The EBIT cash flow for year yr (1-indexed from launch) is discounted at
    (years_to_approval + yr), then multiplied by effective_net_ownership.

    rNPV = P(approval) × PV(EBIT × ownership) − PV(costs) + PV(receivable milestones) + upfront receipts
    """

    @staticmethod
    def compute(
        asset: Asset,
        prob: ProbabilityResult,
        rev: RevenueStream,
        cost: CostStream,
        deal: Optional["DealEconomics"] = None,
    ) -> RNPVResult:
        from bve.models.deal_economics import DealEconomics, milestone_pv

        deal = deal or DealEconomics()
        r = asset.discount_rate

        # Effective ownership: asset royalty × deal royalty stacked multiplicatively
        effective_ownership = asset.net_ownership * (1.0 - deal.royalty_rate)

        years_to_launch = prob.years_to_approval
        cum_prob = prob.cumulative_approval_probability

        # Discount UFCF (EBIT × (1 − tax)) anchored to years_to_launch.
        # During nol_benefit_years from commercial launch, NOL carryforwards
        # defer cash taxes → effective tax = 0.0 for those years only.
        tax_rate = asset.effective_tax_rate
        nol_window = asset.nol_benefit_years
        gross_revenue_pv: float = 0.0
        for i, ebit in enumerate(rev.ebit_by_year):
            yr = i + 1                          # 1-indexed year from launch
            abs_year = years_to_launch + yr
            effective_tax = 0.0 if yr <= nol_window else tax_rate
            after_tax_ebit = ebit * (1.0 - effective_tax)
            gross_revenue_pv += (after_tax_ebit * effective_ownership) / (1.0 + r) ** abs_year

        probability_adjusted_revenue_pv = gross_revenue_pv * cum_prob
        trial_costs_pv = cost.total_pv_weighted_millions

        # Deal receipts: receivable milestones + upfront
        milestone_receipts_pv = sum(
            milestone_pv(m, prob, r, launch_year_offset=deal.launch_year_offset)
            for m in deal.receivable_milestones
        )
        upfront_receipt = deal.upfront_receipt_millions

        rnpv = (
            probability_adjusted_revenue_pv
            - trial_costs_pv
            + milestone_receipts_pv
            + upfront_receipt
        )

        # Reconstruct PhaseBreakdown for backward compatibility
        phase_lookup = {p.phase: p for p in prob.phases}
        phase_breakdown = [
            PhaseBreakdown(
                phase=pc.phase,
                prob_reaching=pc.prob_reaching,
                pv_cost_gross=pc.pv_cost_gross,
                pv_cost_weighted=pc.pv_cost_weighted,
                duration_years=round(
                    phase_lookup[pc.phase].year_end - phase_lookup[pc.phase].year_start, 4
                ),
                success_probability=phase_lookup[pc.phase].success_probability,
            )
            for pc in cost.phase_costs
        ]

        return RNPVResult(
            asset_id=asset.id,
            asset_name=asset.name,
            rnpv_millions=round(rnpv, 2),
            gross_revenue_pv_millions=round(gross_revenue_pv, 2),
            probability_adjusted_revenue_pv_millions=round(probability_adjusted_revenue_pv, 2),
            trial_costs_pv_millions=round(trial_costs_pv, 2),
            deal_milestone_receipts_pv_millions=round(milestone_receipts_pv, 2),
            upfront_receipt_millions=upfront_receipt,
            cumulative_success_probability=cum_prob,
            years_to_launch=years_to_launch,
            peak_sales_millions=round(rev.peak_sales_millions, 2),
            discount_rate=r,
            net_ownership=round(effective_ownership, 6),
            effective_tax_rate=tax_rate,
            nol_benefit_years=nol_window,
            phase_breakdown=phase_breakdown,
            probability_result=prob,
            revenue_stream=rev,
            cost_stream=cost,
        )


# ---------------------------------------------------------------------------
# Unified entry point (Step 6)
# ---------------------------------------------------------------------------

def compute_rnpv_full(
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
    *,
    loe_profile: Optional[dict] = None,
    deal: Optional["DealEconomics"] = None,
) -> RNPVResult:
    """
    Full economic stack: LOE erosion + deal economics.

    This is the single entry point used by ValuationEngine.run(), Monte Carlo,
    scenario analysis, and sensitivity analysis.  All four paths run the same
    economic assumptions, ensuring MC and scenarios are consistent with the
    deterministic base case.

    Parameters
    ----------
    loe_profile : dict or None
        LOE erosion profile forwarded to RevenueModel.compute().
        None → no post-patent tail (same as pre-Step-3 behaviour).
    deal : DealEconomics or None
        Deal terms forwarded to CostModel and RNPVModel.
        None → no deal terms (same as pre-Step-5 behaviour).
    """
    prob = ProbabilityModel.compute(asset, trials)
    rev = RevenueModel.compute(market_model, loe_profile=loe_profile)
    cost = CostModel.compute(prob, asset.discount_rate, deal=deal)
    return RNPVModel.compute(asset, prob, rev, cost, deal=deal)


# ---------------------------------------------------------------------------
# Backward-compatible wrapper
# ---------------------------------------------------------------------------

def compute_rnpv(
    asset: Asset,
    trials: list[ClinicalTrial],
    market_model: MarketModel,
) -> RNPVResult:
    """
    Thin backward-compatible wrapper — no LOE, no deal economics.

    Kept so external callers outside the valuation engine continue to work
    unchanged.  Internal engine paths (MC, scenarios, sensitivity) now call
    compute_rnpv_full() directly.
    """
    return compute_rnpv_full(asset, trials, market_model)
