"""
CostModel — computes probability-weighted present value of trial R&D costs,
optionally including deal-layer cost terms (co-dev share, payable milestones,
upfront payments).

Inputs:  ProbabilityResult (phase timing + prob_reaching + cost_millions),
         discount_rate (float),
         deal (DealEconomics, optional).
Output:  CostStream — per-phase PV breakdown and aggregate total.

This model is stateless.  It has no knowledge of revenue or approval outcomes.

Deal economics integration
--------------------------
When deal is provided:
  - Each phase cost is scaled by deal.cdev_cost_share (our share of R&D costs).
  - Payable milestones are discounted and probability-weighted using phase timing
    from ProbabilityResult.  Their PVs are summed into milestone_costs_pv_millions.
  - deal.upfront_cost_millions is added at face value (t=0, no discounting).

All three components are summed into total_pv_weighted_millions, which is the
single value RNPVModel subtracts.  The decomposition fields let callers inspect
each component separately.

Backward compatibility: deal=None (or default DealEconomics()) produces
identical results to the pre-Step-5 baseline.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from bve.models.probability_model import ProbabilityResult


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------

class PhaseCost(BaseModel):
    """Present-value cost detail for one clinical phase."""
    phase: str
    prob_reaching: float        # P(reaching this phase)
    year_start: float           # phase start time (from ProbabilityResult)
    year_end: float             # phase end time — used by milestone triggers
    year_midpoint: float        # discounting anchor = (year_start + year_end) / 2
    pv_cost_gross: float        # PV of cost before probability weighting (after cdev_cost_share)
    pv_cost_weighted: float     # probability-weighted PV cost


class CostStream(BaseModel):
    """Output of CostModel.compute()."""
    asset_id: str
    phase_costs: list[PhaseCost]

    # Deal terms
    cdev_cost_share: float = 1.0          # Fraction of trial costs we bear
    milestone_costs_pv_millions: float = 0.0  # PV of payable milestones
    upfront_cost_millions: float = 0.0    # Upfront payment at t=0 (face value)

    # Post-approval R&D (Phase 4, REMS, pharmacovigilance — Sprint 9.9)
    post_approval_rd_pv_millions: float = 0.0

    # Aggregate: trial R&D (after cdev share) + milestones + upfront + post-approval R&D
    total_pv_weighted_millions: float

    @property
    def trial_rd_pv_millions(self) -> float:
        """PV of trial R&D costs only (excluding milestones and upfront)."""
        return round(
            sum(pc.pv_cost_weighted for pc in self.phase_costs), 2
        )

    @property
    def pv_costs_millions(self) -> float:
        """Alias for total_pv_weighted_millions — consistent with RNPVResult naming."""
        return self.total_pv_weighted_millions


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class CostModel:
    """
    Stateless engine that discounts R&D costs and deal cost terms to PV.

    Trial R&D cost of phase i:
      cost (after cdev_share) / (1 + r)^midpoint × prob_reaching

    Payable milestone PVs are computed via deal_economics.milestone_pv()
    and added to total_pv_weighted_millions.
    """

    @staticmethod
    def compute(
        prob: ProbabilityResult,
        discount_rate: float,
        deal: Optional["DealEconomics"] = None,  # type: ignore[name-defined]
        post_approval_rd_millions: float = 0.0,
    ) -> CostStream:
        """
        Parameters
        ----------
        prob                     : ProbabilityResult providing phase timing and probabilities.
        discount_rate            : WACC used for discounting.
        deal                     : DealEconomics for co-dev share, milestones, upfront cost.
                                   None → no deal terms (backward compatible).
        post_approval_rd_millions: Post-approval R&D obligations (Phase 4, REMS, etc.)
                                   in USD millions (nominal). Discounted at years_to_approval.
                                   Default 0.0 → no post-approval costs (backward compatible).
        """
        from bve.models.deal_economics import DealEconomics, milestone_pv

        deal = deal or DealEconomics()
        r = discount_rate
        cdev = deal.cdev_cost_share

        phase_costs: list[PhaseCost] = []
        trial_rd_total = 0.0

        for phase in prob.phases:
            cost_after_share = phase.cost_millions * cdev
            mid_year = (phase.year_start + phase.year_end) / 2.0
            pv_cost_gross = cost_after_share / (1.0 + r) ** mid_year
            pv_cost_weighted = pv_cost_gross * phase.prob_reaching

            phase_costs.append(PhaseCost(
                phase=phase.phase,
                prob_reaching=phase.prob_reaching,
                year_start=phase.year_start,
                year_end=phase.year_end,
                year_midpoint=round(mid_year, 3),
                pv_cost_gross=round(pv_cost_gross, 2),
                pv_cost_weighted=round(pv_cost_weighted, 2),
            ))
            trial_rd_total += pv_cost_weighted

        # Payable milestones — pass launch_year_offset for FIRST_SALE timing
        milestone_costs_pv = sum(
            milestone_pv(m, prob, r, launch_year_offset=deal.launch_year_offset)
            for m in deal.payable_milestones
        )

        # Upfront cost (at t=0, no discounting)
        upfront_cost = deal.upfront_cost_millions

        # Post-approval R&D: discounted at years_to_approval (when these begin),
        # then probability-weighted by cumulative approval probability.
        post_approval_pv = 0.0
        if post_approval_rd_millions > 0.0:
            years_to_approval = prob.years_to_approval
            pv_nominal = post_approval_rd_millions / (1.0 + r) ** years_to_approval
            post_approval_pv = round(pv_nominal * prob.cumulative_approval_probability, 2)

        total = round(trial_rd_total + milestone_costs_pv + upfront_cost + post_approval_pv, 2)

        return CostStream(
            asset_id=prob.asset_id,
            phase_costs=phase_costs,
            cdev_cost_share=cdev,
            milestone_costs_pv_millions=round(milestone_costs_pv, 2),
            upfront_cost_millions=upfront_cost,
            post_approval_rd_pv_millions=post_approval_pv,
            total_pv_weighted_millions=total,
        )
