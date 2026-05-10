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

from bve.entities.trial import SpendProfile
from bve.models.cmc_costs import CMCCosts, CMCTimingMode
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

    # CMC / manufacturing investment (Sprint E3)
    cmc_pv_millions: float = 0.0

    # Aggregate: trial R&D (after cdev share) + milestones + upfront + post-approval R&D + CMC
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

def _compute_cmc_pv(
    cmc: CMCCosts,
    prob: ProbabilityResult,
    discount_rate: float,
) -> float:
    """
    Probability-weighted PV of CMC/manufacturing costs.

    Discount year is determined by timing_mode:
      PARALLEL_TO_PHASE_3 → Phase 3 midpoint
      POST_PHASE_2        → Phase 2 year_end (= Phase 3 year_start)
      PRE_PHASE_3_START   → Phase 3 year_start
      CUSTOM_YEAR         → cmc.custom_year

    Probability weight = prob_reaching for Phase 3.  Falls back to the last
    phase's prob_reaching when no Phase 3 is present in the program.
    """
    if cmc.total_millions == 0.0:
        return 0.0

    # Find relevant phases
    phases_by_name = {p.phase: p for p in prob.phases}
    p3 = phases_by_name.get("phase_3")
    p2 = phases_by_name.get("phase_2")

    # Discount year
    mode = cmc.timing_mode
    if mode == CMCTimingMode.CUSTOM_YEAR:
        year = cmc.custom_year or 0.0
    elif mode == CMCTimingMode.PARALLEL_TO_PHASE_3:
        year = (p3.year_start + p3.year_end) / 2.0 if p3 else prob.years_to_approval / 2.0
    elif mode == CMCTimingMode.POST_PHASE_2:
        year = p2.year_end if p2 else (p3.year_start if p3 else 0.0)
    elif mode == CMCTimingMode.PRE_PHASE_3_START:
        year = p3.year_start if p3 else (p2.year_end if p2 else 0.0)
    else:
        year = prob.years_to_approval / 2.0

    # Probability weight: prob_reaching_phase_3; fallback to last phase's prob_reaching
    if p3 is not None:
        pw = p3.prob_reaching
    elif prob.phases:
        pw = prob.phases[-1].prob_reaching
    else:
        pw = prob.cumulative_approval_probability

    pv = cmc.total_millions / (1.0 + discount_rate) ** year * pw
    return round(pv, 2)


def _spend_fraction_weights(
    year_start: float,
    year_end: float,
) -> list[tuple[float, float]]:
    """
    Split [year_start, year_end) into integer-boundary sub-intervals.

    Returns a list of (fraction, mid_year) pairs where:
      - fraction  = sub-interval length / total duration  (sums to 1.0)
      - mid_year  = midpoint of the sub-interval (used as discount anchor)

    Example: year_start=0.5, year_end=3.0 → sub-intervals
      [0.5, 1.0), [1.0, 2.0), [2.0, 3.0)
      fractions: 0.5/2.5, 1.0/2.5, 1.0/2.5
      midpoints: 0.75, 1.5, 2.5

    Degenerate: when duration == 0.0, returns a single entry at year_start.
    """
    duration = year_end - year_start
    if duration <= 0.0:
        return [(1.0, year_start)]

    result: list[tuple[float, float]] = []
    current = year_start
    while current < year_end - 1e-9:
        # Next integer boundary above current
        next_int = float(int(current) + 1)
        segment_end = min(next_int, year_end)
        interval = segment_end - current
        fraction = interval / duration
        mid = (current + segment_end) / 2.0
        result.append((fraction, mid))
        current = segment_end
    return result


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
        cmc_costs: Optional[CMCCosts] = None,
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
        cmc_costs                : CMCCosts for manufacturing/CMC investment.
                                   None → no CMC costs (backward compatible).
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

            sp = getattr(phase, "spend_profile", SpendProfile.UNIFORM)
            if sp == SpendProfile.ANNUAL_UNIFORM:
                pv_cost_gross = sum(
                    cost_after_share * frac / (1.0 + r) ** yr
                    for frac, yr in _spend_fraction_weights(phase.year_start, phase.year_end)
                )
            else:
                # UNIFORM — exact midpoint, bit-for-bit identical to pre-E1
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

        # CMC / manufacturing investment (Sprint E3)
        cmc_pv = _compute_cmc_pv(cmc_costs, prob, r) if cmc_costs is not None else 0.0

        total = round(trial_rd_total + milestone_costs_pv + upfront_cost + post_approval_pv + cmc_pv, 2)

        return CostStream(
            asset_id=prob.asset_id,
            phase_costs=phase_costs,
            cdev_cost_share=cdev,
            milestone_costs_pv_millions=round(milestone_costs_pv, 2),
            upfront_cost_millions=upfront_cost,
            post_approval_rd_pv_millions=post_approval_pv,
            cmc_pv_millions=cmc_pv,
            total_pv_weighted_millions=total,
        )
