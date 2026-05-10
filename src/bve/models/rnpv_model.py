"""
RNPVModel — combines ProbabilityResult, RevenueStream, and CostStream into rNPV,
optionally applying deal-layer economics (royalty on revenue, profit share on EBIT,
receivable milestones, upfront receipts).

Canonical formula
-----------------

rNPV =
    P(approval) × PV(after-tax FCF attributable to asset ownership)
    − total_pv_weighted_development_costs
    + PV(receivable milestones)
    + upfront_receipt

Expanded:

rNPV =
    P(approval) × Σ_t [
        after_tax_FCF_t × net_ownership / (1 + WACC)^t
    ]
    − total_pv_weighted_development_costs
    + PV(receivable milestones)
    + upfront_receipt

Where per year:
    adjusted_EBIT_t  = EBIT_t − revenue_t × royalty_rate − EBIT_t × profit_share_rate
    cash_tax_t       = max(adjusted_EBIT_t − usable_NOL_t, 0) × tax_rate_t
    after_tax_EBIT_t = adjusted_EBIT_t − cash_tax_t
    after_tax_FCF_t  = after_tax_EBIT_t − maintenance_capex_t − working_capital_t − launch_capex_t

Where:
    t                = years_to_approval + commercial_year  (1-indexed from launch)
    net_ownership    = asset.net_ownership = 1 − asset.royalty_rate  (equity stake only)
    royalty_rate     = deal.royalty_rate  (paid on net revenue — top-line deduction)
    profit_share_rate= deal.profit_share_rate  (paid on EBIT after royalty — applied before equity split)
    tax_rate_t       = 0 during NOL benefit window; effective_tax_rate thereafter
    total_pv_weighted_development_costs = CostStream.total_pv_weighted_millions
        (trial R&D + CMC + payable milestones + upfront cost + post-approval R&D)

Ownership vs. deal deductions — explicit separation
----------------------------------------------------
  net_ownership    : equity stake in the program (set on Asset, invariant to deal terms)
  royalty_rate     : royalty paid to deal partner as % of net sales (reduces revenue before EBIT)
  profit_share_rate: profit split to deal partner as % of EBIT (reduces EBIT after royalty)

Royalties reduce revenue; profit shares reduce EBIT.  These are NOT equivalent:
a 10% royalty on $100M revenue with 30% EBIT margin reduces EBIT by $10M,
whereas a 10% profit share on $30M EBIT reduces it by only $3M.

EBIT basis
----------
EBIT_t in ebit_by_year is:
  - Global (all geographies modeled in MarketModel — not US-only)
  - Post-gross-to-net (payer access × net_price_per_patient applied in RevenueModel)
  - Post-COGS (cogs_rate × revenue, applied per year in RevenueModel)
  - Post-SG&A (sgna_rate_launch → sgna_rate_mature ramp over years_to_peak in RevenueModel)
  - Pre-tax by default; after-tax when effective_tax_rate > 0 and NOL window has expired

NAV and per-share value
-----------------------
    NAV = rNPV + company.net_cash_millions
    NAV/share = NAV / company.diluted_shares_outstanding_millions

Deal economics boundary
-----------------------
RevenueModel is NEVER given DealEconomics.  Revenue is gross commercial revenue.
All deal deductions (royalty, profit share, equity split) happen in RNPVModel.

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
from bve.models.tax_profile import TaxAudit, TaxProfile, compute_year_fcf

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
    gross_revenue_pv_millions: float = Field(
        description=(
            "Pre-probability PV of post-deal, after-tax, ownership-adjusted EBIT. "
            "= Σ_t [(EBIT_t − royalty_t − profit_share_t) × (1−tax) × net_ownership / (1+r)^t]. "
            "Multiply by cumulative_success_probability to get probability_adjusted_revenue_pv_millions."
        )
    )
    probability_adjusted_revenue_pv_millions: float
    trial_costs_pv_millions: float = Field(
        description=(
            "Total probability-weighted PV of all development costs "
            "(trial R&D + CMC + payable milestones + upfront cost + post-approval R&D). "
            "See total_pv_weighted_development_costs property for the canonical name."
        )
    )

    # Deal economics decomposition (zero when no deal terms)
    deal_milestone_receipts_pv_millions: float = 0.0  # PV of receivable milestones
    upfront_receipt_millions: float = 0.0             # Upfront receipt at t=0

    # Deal deduction decomposition — value given up to deal partner on revenue side
    royalty_deductions_pv_millions: float = Field(
        default=0.0,
        description=(
            "Probability-adjusted PV of royalties paid to deal partner on net revenue. "
            "= P(approval) × Σ_t [revenue_t × royalty_rate × net_ownership × (1−tax) / (1+r)^t]. "
            "Zero when deal.royalty_rate = 0."
        ),
    )
    profit_share_deductions_pv_millions: float = Field(
        default=0.0,
        description=(
            "Probability-adjusted PV of profit share paid to deal partner from EBIT. "
            "= P(approval) × Σ_t [EBIT_t × profit_share_rate × net_ownership × (1−tax) / (1+r)^t]. "
            "Zero when deal.profit_share_rate = 0."
        ),
    )

    # Key metrics
    cumulative_success_probability: float
    years_to_launch: float
    peak_sales_millions: float
    discount_rate: float
    net_ownership: float = Field(
        description=(
            "Equity stake in the program: asset.net_ownership = 1 − asset.royalty_rate. "
            "Does NOT include deal.royalty_rate (that reduces revenue) or "
            "deal.profit_share_rate (that reduces EBIT). "
            "See royalty_deductions_pv_millions and profit_share_deductions_pv_millions "
            "for the deal partner's economic share."
        )
    )

    # Per-phase detail (backward compat)
    phase_breakdown: list[PhaseBreakdown] = Field(default_factory=list)

    # Step 2: structured sub-objects for intermediate inspectability
    probability_result: Optional[ProbabilityResult] = None
    revenue_stream: Optional[RevenueStream] = None
    cost_stream: Optional[CostStream] = None

    # Tax treatment applied in this run
    effective_tax_rate: float = 0.21
    nol_benefit_years: int = 0

    # BD/M&A tax audit (populated only when TaxProfile is supplied; None otherwise)
    tax_audit: Optional[TaxAudit] = None

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

    @property
    def total_pv_weighted_development_costs(self) -> float:
        """
        Canonical name for the total cost term subtracted in the rNPV formula.

        Includes: trial R&D (after cdev_share + inflation) + CMC/manufacturing +
        payable milestones + upfront cost + post-approval R&D obligations.
        Same value as trial_costs_pv_millions (kept for backward compatibility).
        """
        return self.trial_costs_pv_millions


# ---------------------------------------------------------------------------
# RNPVModel — discounting only
# ---------------------------------------------------------------------------

class RNPVModel:
    """
    Stateless engine that combines the three upstream results into rNPV.

    Two tax paths — selected by the presence of tax_profile:

    Path A (tax_profile=None, backward compatible):
      Simple after-tax EBIT: tax = 0 during asset.nol_benefit_years, then
      asset.effective_tax_rate thereafter.  No audit outputs produced.

    Path B (tax_profile provided, BD/M&A-ready):
      Per-year NOL-tracking, utilization limit, optional NOL generation,
      jurisdiction-mode blended rate, maintenance capex, working capital,
      and one-time launch capex.  Full TaxAudit populated in RNPVResult.

    Deal economics (both paths):
      1. royalty_t      = revenue_t × deal.royalty_rate        (top-line)
      2. profit_share_t = ebit_t × deal.profit_share_rate      (EBIT-level)
      3. adjusted_ebit  = ebit_t − royalty_t − profit_share_t
      → feed into tax path → after_tax_fcf → × net_ownership → discounted

    rNPV = P(approval) × PV(after-tax FCF × ownership)
           − total_pv_weighted_development_costs
           + PV(receivable milestones) + upfront_receipt
    """

    @staticmethod
    def compute(
        asset: Asset,
        prob: ProbabilityResult,
        rev: RevenueStream,
        cost: CostStream,
        deal: Optional["DealEconomics"] = None,
        tax_profile: Optional[TaxProfile] = None,
    ) -> RNPVResult:
        from bve.models.deal_economics import DealEconomics, milestone_pv

        deal = deal or DealEconomics()
        r = asset.discount_rate
        net_ownership = asset.net_ownership  # equity stake only — invariant to deal terms

        royalty_rate = deal.royalty_rate
        profit_share_rate = deal.profit_share_rate

        years_to_launch = prob.years_to_approval
        cum_prob = prob.cumulative_approval_probability

        # Tax path selection
        use_tax_profile = tax_profile is not None
        # Path A fallback values (used only when tax_profile is None)
        tax_rate_simple = asset.effective_tax_rate
        nol_window = asset.nol_benefit_years

        gross_revenue_pv: float = 0.0
        royalty_pv_sum: float = 0.0
        profit_share_pv_sum: float = 0.0

        # Path B audit accumulators (populated only when tax_profile provided)
        _pre_tax_adj_ebit: list[float] = []
        _taxable_income: list[float] = []
        _nol_used: list[float] = []
        _remaining_nol: list[float] = []
        _cash_tax: list[float] = []
        _after_tax_ebit: list[float] = []
        _capex: list[float] = []
        _working_capital: list[float] = []
        _after_tax_fcf: list[float] = []

        remaining_nol = tax_profile.nol_balance_millions if use_tax_profile else 0.0
        revenue_series = rev.revenue_by_year  # same length as ebit_by_year

        for i, ebit in enumerate(rev.ebit_by_year):
            yr = i + 1                              # 1-indexed year from launch
            abs_year = years_to_launch + yr
            revenue_t = revenue_series[i] if i < len(revenue_series) else 0.0

            # Deal deductions (both paths)
            royalty_t = revenue_t * royalty_rate
            profit_share_t = ebit * profit_share_rate
            adjusted_ebit = ebit - royalty_t - profit_share_t

            if use_tax_profile:
                # Path B — per-year NOL tracking + FCF adjustments
                (usable_nol, remaining_nol, taxable_income, cash_tax, after_tax_ebit,
                 maint_capex, wc, launch_capex_t, after_tax_fcf) = compute_year_fcf(
                    adjusted_ebit, revenue_t, remaining_nol, tax_profile, yr,
                )
                captured = after_tax_fcf * net_ownership

                # Track deductions (ownership-adjusted, post-FCF-tax)
                effective_tax_this_yr = cash_tax / adjusted_ebit if adjusted_ebit > 0 else 0.0
                _pre_tax_adj_ebit.append(round(adjusted_ebit, 2))
                _taxable_income.append(round(taxable_income, 2))
                _nol_used.append(round(usable_nol, 2))
                _remaining_nol.append(round(remaining_nol, 2))
                _cash_tax.append(round(cash_tax, 2))
                _after_tax_ebit.append(round(after_tax_ebit, 2))
                _capex.append(round(maint_capex + launch_capex_t, 2))
                _working_capital.append(round(wc, 2))
                _after_tax_fcf.append(round(after_tax_fcf, 2))

                royalty_pv_sum += (royalty_t * net_ownership * (1.0 - effective_tax_this_yr)) / (1.0 + r) ** abs_year
                profit_share_pv_sum += (profit_share_t * net_ownership * (1.0 - effective_tax_this_yr)) / (1.0 + r) ** abs_year

            else:
                # Path A — simple nol_benefit_years window (backward compatible)
                effective_tax = 0.0 if yr <= nol_window else tax_rate_simple
                after_tax_adjusted = adjusted_ebit * (1.0 - effective_tax)
                captured = after_tax_adjusted * net_ownership

                df = (1.0 + r) ** abs_year
                royalty_pv_sum += (royalty_t * net_ownership * (1.0 - effective_tax)) / df
                profit_share_pv_sum += (profit_share_t * net_ownership * (1.0 - effective_tax)) / df

            gross_revenue_pv += captured / (1.0 + r) ** abs_year

        probability_adjusted_revenue_pv = gross_revenue_pv * cum_prob
        trial_costs_pv = cost.total_pv_weighted_millions

        # Deal receipts: receivable milestones + upfront
        # Revenue stream is passed for SALES_THRESHOLD milestone resolution.
        milestone_receipts_pv = sum(
            milestone_pv(m, prob, r, launch_year_offset=deal.launch_year_offset,
                         revenue_stream=rev)
            for m in deal.receivable_milestones
        )
        upfront_receipt = deal.upfront_receipt_millions

        # SALES_THRESHOLD payable milestones: CostModel returned 0.0 for these
        # (no revenue context there). Resolve them here with the revenue stream
        # and subtract from rNPV to keep cost accounting consistent.
        from bve.models.deal_economics import MilestoneTrigger
        sales_threshold_payable_pv = sum(
            milestone_pv(m, prob, r, launch_year_offset=deal.launch_year_offset,
                         revenue_stream=rev)
            for m in deal.payable_milestones
            if m.trigger == MilestoneTrigger.SALES_THRESHOLD
        )

        rnpv = (
            probability_adjusted_revenue_pv
            - trial_costs_pv
            - sales_threshold_payable_pv
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

        # Build TaxAudit when Path B was used
        tax_audit: Optional[TaxAudit] = None
        if use_tax_profile:
            tax_audit = TaxAudit(
                pre_tax_adjusted_ebit_by_year=_pre_tax_adj_ebit,
                taxable_income_by_year=_taxable_income,
                nol_used_by_year=_nol_used,
                remaining_nol_by_year=_remaining_nol,
                cash_tax_by_year=_cash_tax,
                after_tax_ebit_by_year=_after_tax_ebit,
                capex_by_year=_capex,
                working_capital_by_year=_working_capital,
                after_tax_fcf_by_year=_after_tax_fcf,
                tax_profile_used=tax_profile,
            )

        return RNPVResult(
            asset_id=asset.id,
            asset_name=asset.name,
            rnpv_millions=round(rnpv, 0),                              # nearest $1M — false precision below $1M is noise
            gross_revenue_pv_millions=round(gross_revenue_pv, 0),
            probability_adjusted_revenue_pv_millions=round(probability_adjusted_revenue_pv, 0),
            trial_costs_pv_millions=round(trial_costs_pv, 1),          # costs matter to $0.1M
            deal_milestone_receipts_pv_millions=round(milestone_receipts_pv, 1),
            upfront_receipt_millions=upfront_receipt,
            royalty_deductions_pv_millions=round(royalty_pv_sum * cum_prob, 1),
            profit_share_deductions_pv_millions=round(profit_share_pv_sum * cum_prob, 1),
            cumulative_success_probability=cum_prob,
            years_to_launch=years_to_launch,
            peak_sales_millions=round(rev.peak_sales_millions, 0),
            discount_rate=r,
            net_ownership=round(net_ownership, 6),
            effective_tax_rate=tax_rate_simple,
            nol_benefit_years=nol_window,
            tax_audit=tax_audit,
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
    tax_profile: Optional[TaxProfile] = None,
) -> RNPVResult:
    """
    Full economic stack: LOE erosion + deal economics + optional TaxProfile.

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
    tax_profile : TaxProfile or None
        BD/M&A-ready tax and FCF model.  When None (default), the simple
        nol_benefit_years / effective_tax_rate path on Asset is used.
    """
    prob = ProbabilityModel.compute(asset, trials)
    rev = RevenueModel.compute(market_model, loe_profile=loe_profile)
    post_rd = getattr(asset, "post_approval_rd_millions", 0.0)
    cost = CostModel.compute(prob, asset.discount_rate, deal=deal,
                             post_approval_rd_millions=post_rd)
    return RNPVModel.compute(asset, prob, rev, cost, deal=deal, tax_profile=tax_profile)


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
