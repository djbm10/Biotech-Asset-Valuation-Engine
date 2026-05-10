"""
DealEconomics — structured deal terms consumed by CostModel and RNPVModel.

Design boundary
---------------
DealEconomics lives on the program/container side (DrugAssetProgram.deal_economics).
It is consumed by:
  - CostModel.compute()   → scales trial costs by cdev_cost_share; discounts payable milestones
  - RNPVModel.compute()   → stacks deal royalty on asset ownership; adds receivable milestone PVs
It is NOT consumed by RevenueModel.  Revenue is gross commercial revenue.  The royalty
reduction is an economic ownership split that happens after revenue is modelled.

Milestone timing — explicit mapping
------------------------------------
Each trigger uses exactly one timing source from ProbabilityResult.  No business logic
is embedded in milestone_pv(); it is a purely mechanical discounting helper.

  MilestoneTrigger.PHASE_START   → year = phase.year_start
                                   P    = phase.prob_reaching
                                   (payment occurs on entering the phase)

  MilestoneTrigger.PHASE_SUCCESS → year = phase.year_end
                                   P    = phase.prob_reaching × phase.success_probability
                                   (payment occurs on successfully completing the phase)

  MilestoneTrigger.APPROVAL      → year = prob.years_to_approval
                                   P    = cumulative_approval_probability
                                   (regulatory approval timing)

  MilestoneTrigger.FIRST_SALE    → year = prob.years_to_approval + launch_year_offset
                                   P    = cumulative_approval_probability
                                   DISTINCT from APPROVAL: launch may lag approval by months/years.
                                   Default launch_year_offset=0.0 keeps current behaviour.
                                   Set DealEconomics.launch_year_offset to model a commercialisation lag.

  MilestoneTrigger.SALES_THRESHOLD → returns 0.0; reserved — requires revenue-dependent timing
                                      not yet available from ProbabilityResult alone.

Royalty formula — explicit
--------------------------
Revenue capture = gross_ebit_yr × asset.net_ownership × (1 − deal.royalty_rate)

Where:
  asset.net_ownership = 1 − asset.royalty_rate      (base economics on the Asset entity)
  deal.royalty_rate   = royalty paid to deal partner (additional layer, multiplicative)
  effective_ownership = asset.net_ownership × (1 − deal.royalty_rate)

Setting deal.royalty_rate = 0.0 (default) leaves asset.net_ownership unchanged.

Upfront cash flows
------------------
upfront_cost_millions and upfront_receipt_millions are time-0 cash flows.
They are added at face value with no discount factor applied.

Backward compatibility
----------------------
DealEconomics defaults to no-deal semantics:
  upfront_cost_millions = 0, upfront_receipt_millions = 0,
  royalty_rate = 0, cdev_cost_share = 1.0, milestones = [], launch_year_offset = 0.0.
CostModel and RNPVModel with deal=None or default DealEconomics produce identical results
to the pre-Step-5 baseline.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class MilestoneTrigger(str, Enum):
    """
    Event that triggers a milestone payment or receipt.

    Timing semantics — each trigger maps to exactly one timing source:
      PHASE_START     → phase.year_start    (entering the phase)
      PHASE_SUCCESS   → phase.year_end      (successfully completing the phase)
      APPROVAL        → prob.years_to_approval  (regulatory approval)
      FIRST_SALE      → prob.years_to_approval + deal.launch_year_offset
                        (first commercial sale; distinct from APPROVAL — set
                         launch_year_offset > 0 to model a commercialisation lag)
      SALES_THRESHOLD → not yet implemented; returns 0 — requires revenue-dependent
                        timing that is not available from ProbabilityResult alone.
    """
    PHASE_START = "phase_start"
    PHASE_SUCCESS = "phase_success"
    APPROVAL = "approval"
    FIRST_SALE = "first_sale"
    SALES_THRESHOLD = "sales_threshold"


class MilestoneDirection(str, Enum):
    """Whether the milestone flows out (cost) or in (income)."""
    PAYABLE = "payable"       # We pay — treated as a cost by CostModel
    RECEIVABLE = "receivable" # We receive — treated as income by RNPVModel


# ---------------------------------------------------------------------------
# Milestone
# ---------------------------------------------------------------------------

class Milestone(BaseModel):
    """
    A single contingent payment or receipt tied to a development event.

    Parameters
    ----------
    description             : Human-readable label (e.g. "Phase 3 start milestone").
    amount_millions         : Face value in USD millions.  Must be > 0.
    trigger                 : The event that triggers the payment/receipt.
    trigger_phase           : Required for PHASE_START and PHASE_SUCCESS triggers.
                              Must match a phase string in ProbabilityResult.phases
                              (e.g. "phase_1", "phase_2", "phase_3", "nda_bla").
    direction               : PAYABLE (outflow) or RECEIVABLE (inflow).
    sales_threshold_millions: Required for SALES_THRESHOLD trigger.  The milestone
                              is triggered in the first post-launch year where annual
                              revenue ≥ this value.  Revenue stream must be supplied
                              to milestone_pv(); otherwise falls back to 0.0.
    """
    description: str
    amount_millions: float = Field(gt=0.0)
    trigger: MilestoneTrigger
    trigger_phase: Optional[str] = None  # e.g. "phase_3"
    direction: MilestoneDirection = MilestoneDirection.PAYABLE
    sales_threshold_millions: Optional[float] = Field(
        default=None,
        gt=0.0,
        description=(
            "Revenue threshold (USD millions) for SALES_THRESHOLD trigger. "
            "Milestone fires in the first year annual revenue ≥ this value. "
            "Ignored for all other trigger types."
        ),
    )

    @model_validator(mode="after")
    def _validate_sales_threshold(self) -> "Milestone":
        if (self.trigger == MilestoneTrigger.SALES_THRESHOLD
                and self.sales_threshold_millions is None):
            raise ValueError(
                "Milestone with trigger=SALES_THRESHOLD requires "
                "sales_threshold_millions to be set."
            )
        return self


# ---------------------------------------------------------------------------
# DealEconomics
# ---------------------------------------------------------------------------

class DealEconomics(BaseModel):
    """
    Financial terms of a deal overlay on the base asset economics.

    All fields default to zero-effect — a default DealEconomics() is
    economically neutral and backward compatible with pre-Step-5 results.

    Parameters
    ----------
    upfront_cost_millions    : Upfront payment we make at t=0.  Added at face value
                               (no discounting — this is a time-0 cash flow).
    upfront_receipt_millions : Upfront payment we receive at t=0.  Added at face value
                               (no discounting — this is a time-0 cash flow).
    royalty_rate             : Royalty fraction paid to a deal partner on net sales.
                               Revenue capture formula (explicit):
                                 captured_revenue = gross_ebit
                                                    × asset.net_ownership
                                                    × (1 − royalty_rate)
                               Applied multiplicatively after asset.net_ownership:
                                 effective_ownership = asset.net_ownership × (1 − royalty_rate)
                               0.0 (default) = no deal royalty; asset.net_ownership unchanged.
    cdev_cost_share          : Our fraction of clinical development costs (0 < x ≤ 1).
                               1.0 (default) = we bear all costs.
                               0.5 = co-development 50/50 cost split.
    milestones               : List of Milestone objects.  Payable milestones are
                               consumed by CostModel; receivable by RNPVModel.
    launch_year_offset       : Years between regulatory approval and first commercial sale.
                               Used by FIRST_SALE milestones:
                                 year = prob.years_to_approval + launch_year_offset
                               0.0 (default) = first sale occurs at approval year.
                               Set to a positive value to model commercialisation lag.
    """
    upfront_cost_millions: float = Field(default=0.0, ge=0.0)
    upfront_receipt_millions: float = Field(default=0.0, ge=0.0)
    royalty_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    cdev_cost_share: float = Field(default=1.0, gt=0.0, le=1.0)
    milestones: list[Milestone] = Field(default_factory=list)
    launch_year_offset: float = Field(default=0.0, ge=0.0,
                                      description="Years from approval to first commercial sale")

    @property
    def payable_milestones(self) -> list[Milestone]:
        return [m for m in self.milestones if m.direction == MilestoneDirection.PAYABLE]

    @property
    def receivable_milestones(self) -> list[Milestone]:
        return [m for m in self.milestones if m.direction == MilestoneDirection.RECEIVABLE]

    @property
    def has_deal_terms(self) -> bool:
        """True if any non-default deal terms are present."""
        return bool(
            self.upfront_cost_millions > 0
            or self.upfront_receipt_millions > 0
            or self.royalty_rate > 0
            or self.cdev_cost_share < 1.0
            or self.milestones
            or self.launch_year_offset > 0
        )


# ---------------------------------------------------------------------------
# Milestone PV helper — purely mechanical; no business logic
# ---------------------------------------------------------------------------

def milestone_pv(
    milestone: Milestone,
    prob: "ProbabilityResult",  # type: ignore[name-defined]
    discount_rate: float,
    launch_year_offset: float = 0.0,
    revenue_stream: "Optional[RevenueStream]" = None,  # type: ignore[name-defined]
) -> float:
    """
    Compute the probability-weighted present value of a single milestone.

    This is a purely mechanical discounting helper.  The caller is responsible
    for supplying timing parameters (launch_year_offset); no business logic
    lives here.

    Parameters
    ----------
    milestone           : The milestone to evaluate.
    prob                : ProbabilityResult providing phase timing and probabilities.
    discount_rate       : WACC used for discounting.
    launch_year_offset  : Years from approval to first commercial sale.
                          Only applied to FIRST_SALE milestones.
                          0.0 (default) = first sale at approval year.
    revenue_stream      : Optional RevenueStream for SALES_THRESHOLD resolution.
                          When provided and trigger=SALES_THRESHOLD, finds the first
                          post-launch year where annual revenue ≥ sales_threshold_millions
                          and discounts the milestone to that year.
                          When None and trigger=SALES_THRESHOLD, returns 0.0.

    Returns 0.0 for unrecognised trigger_phase.
    Returns 0.0 for SALES_THRESHOLD when revenue_stream is None or threshold is never crossed.

    Timing sources (from module docstring):
      PHASE_START      → year_start,   P = prob_reaching
      PHASE_SUCCESS    → year_end,     P = prob_reaching × success_probability
      APPROVAL         → years_to_approval,                 P = cumulative_approval_probability
      FIRST_SALE       → years_to_approval + launch_year_offset, P = cumulative_approval_probability
      SALES_THRESHOLD  → years_to_approval + first year revenue ≥ threshold,
                         P = cumulative_approval_probability; requires revenue_stream.
    """
    phase_lookup = {p.phase: p for p in prob.phases}

    trigger = milestone.trigger

    if trigger == MilestoneTrigger.SALES_THRESHOLD:
        # Requires revenue_stream; return 0.0 if not provided
        if revenue_stream is None or milestone.sales_threshold_millions is None:
            return 0.0
        threshold = milestone.sales_threshold_millions
        # Find first year (1-based) where revenue_by_year[yr-1] >= threshold
        trigger_year: Optional[float] = None
        for yr_idx, rev in enumerate(revenue_stream.revenue_by_year, start=1):
            if rev >= threshold:
                trigger_year = float(yr_idx)
                break
        if trigger_year is None:
            return 0.0  # Threshold never crossed in revenue curve
        year = prob.years_to_approval + trigger_year
        prob_payment = prob.cumulative_approval_probability
        pv = milestone.amount_millions / (1.0 + discount_rate) ** year
        return round(pv * prob_payment, 4)

    if trigger == MilestoneTrigger.APPROVAL:
        year = prob.years_to_approval
        prob_payment = prob.cumulative_approval_probability

    elif trigger == MilestoneTrigger.FIRST_SALE:
        # Distinct from APPROVAL: launch may lag approval by months or years.
        # launch_year_offset=0.0 (default) collapses FIRST_SALE to APPROVAL timing.
        year = prob.years_to_approval + launch_year_offset
        prob_payment = prob.cumulative_approval_probability

    elif trigger == MilestoneTrigger.PHASE_START:
        tp = milestone.trigger_phase
        if tp not in phase_lookup:
            return 0.0
        year = phase_lookup[tp].year_start      # payment on entering the phase
        prob_payment = phase_lookup[tp].prob_reaching

    elif trigger == MilestoneTrigger.PHASE_SUCCESS:
        tp = milestone.trigger_phase
        if tp not in phase_lookup:
            return 0.0
        pr = phase_lookup[tp]
        year = pr.year_end                       # payment on completing the phase
        prob_payment = pr.prob_reaching * pr.success_probability

    else:
        return 0.0

    if year <= 0:
        pv = milestone.amount_millions           # t=0 cash flow; no discounting
    else:
        pv = milestone.amount_millions / (1.0 + discount_rate) ** year

    return round(pv * prob_payment, 4)
