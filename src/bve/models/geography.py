"""
GeographySplit — regional revenue modeling for global asset valuations.

Architecture: Option A+ (revenue_ratio approach)
-------------------------------------------------
Each ex-US region's annual revenue is expressed as a fraction of the US base
revenue curve, shifted by the region's launch delay and scaled by reimbursement
and approval probabilities. This is the "simple per-region revenue_ratio" design.

Why revenue_ratio instead of per-region patient counts + pricing?
  - Most analysts know "EU5 adds ~30-40% of US revenue" from comp-set analysis
    without having separate European epidemiology or price data.
  - revenue_ratio is a single calibrated input with intuitive economic meaning:
    revenue_ratio=0.35 means EU5 peak revenue = 35% of US peak revenue.
  - Option B (full per-region patient pool + PricingModel) can be added in a
    later sprint for investment-memo-grade precision; it would layer on top of
    this infrastructure without breaking the Option A+ API.

When to use granular regional modeling (Option B, future):
  - Assets with published EU5/Japan epidemiology data
  - Assets where EU price negotiations produce materially different G2N curves
  - Assets where EU/Japan launch timing materially changes regulatory strategy
  - Full global revenue build-up for investment committee memos

Revenue formula per region in year t (post-US-launch)
------------------------------------------------------
    regional_rev(t) = US_revenue(t − delay_bucketed)
                      × revenue_ratio
                      × reimbursement_probability
                      × probability_of_regional_approval

    where US_revenue(t') = 0 if t' ≤ 0 or t' > US patent life.

Fractional delay bucketing
--------------------------
Fractional launch delays are conservatively floored to the nearest integer:
  - A 1.5-year delay → revenue starts at post-launch year 2 (not year 1).
  - A 2.0-year delay → revenue starts at post-launch year 3.
This avoids interpolation complexity and is appropriate for screening-level models.
Use integer launch_delay_years for precise timing control.

Sprint A known limitation
--------------------------
Revenue is computed over years 1..patent_life_years (the US patent window,
extended by any new_formulation lifecycle events). Regions with non-zero delays
contribute revenue from their first active year through patent_life_years.
The final `delay_bucketed` years of each delayed region's patent window are
not captured — they fall after the US patent boundary in calendar year terms.

Example: US patent 12 years, EU5 2-year delay → EU5 contributes years 3..12
of the US calendar (EU5 years 1..10); EU5 years 11–12 (calendar years 13–14)
are not modeled. For a 2yr delay asset, this understates EU5 NPV by roughly
2/12 ≈ 17% of EU5 value (discounting attenuates the impact further).

Future sprints will add per-region patent window extensions to close this gap.

Backward compatibility
----------------------
geography_split is an optional field on MarketModel. When not set, all existing
US-only and CommercialInputs.ex_us_revenue_multiple behavior is unchanged.
When geography_split is set, it overrides ex_us_revenue_multiple.
"""
from __future__ import annotations

import math
from typing import Callable, Optional

from pydantic import BaseModel, Field


class RegionalProfile(BaseModel, frozen=True):
    """
    Revenue profile for a single geographic region.

    Fields
    ------
    revenue_ratio : float
        Regional peak revenue as a fraction of the US base revenue in the same
        year. revenue_ratio=0.35 means this region contributes 35% of the US
        revenue in each active year (after adjusting for delay and scaling).
        Must be > 0; values > 1.0 are allowed for regions that may outperform
        the US base (e.g., a drug with broader EU reimbursement than expected).

    launch_delay_years : float
        Calendar years after the US approval date before this region launches.
        Bucketed conservatively to the floor integer for revenue computation:
        1.5 years → regional revenue starts at US post-launch year 2.
        Use 0.0 for simultaneous US/ex-US launch (rare).

    reimbursement_probability : float
        Probability that this region achieves broad formulary reimbursement.
        Accounts for HTA uncertainty (NICE, G-BA, ASMR, etc.).
        Set to 1.0 (default) when reimbursement is expected or already achieved.
        Multiplied into regional revenue as a probability-weighted haircut.

    probability_of_regional_approval : float
        Probability of receiving marketing authorization in this region.
        Usually 1.0 for major markets once US approval is granted.
        May be < 1.0 for China (NMPA independent review), Japan (PMDA needs
        local trial data), or regions with limited regulatory capacity.
    """

    revenue_ratio: float = Field(
        gt=0.0,
        description=(
            "Regional peak revenue as a fraction of the US base revenue. "
            "revenue_ratio=0.35 → this region peaks at 35% of US peak. "
            "Captures combined effect of regional pricing, patient pool, "
            "and penetration differences vs. US."
        ),
    )
    launch_delay_years: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Years after US approval before this region's commercial launch. "
            "Conservatively floor-bucketed: 1.5 → starts at post-launch year 2."
        ),
    )
    reimbursement_probability: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Probability of achieving broad formulary reimbursement. "
            "Set < 1.0 for HTA-uncertain markets (EU5 G-BA, NICE, ASMR, etc.)."
        ),
    )
    probability_of_regional_approval: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Probability of receiving marketing authorization in this region. "
            "Usually 1.0 for EU/Japan once US approved; may be lower for China."
        ),
    )

    @property
    def effective_revenue_scalar(self) -> float:
        """
        Combined probability-weighted revenue multiplier for this region.

        effective_scalar = revenue_ratio × reimbursement_probability
                           × probability_of_regional_approval

        Applied to US_revenue(t − delay) to produce this region's contribution
        to global revenue in calendar year t.
        """
        return (
            self.revenue_ratio
            * self.reimbursement_probability
            * self.probability_of_regional_approval
        )

    @property
    def delay_years_bucketed(self) -> int:
        """
        Launch delay conservatively floored to nearest integer year.

        A 1.5-year delay → 1 year bucketed → regional revenue starts at
        US post-launch year 2 (i.e., regional year 1 = US year 2).
        """
        return int(math.floor(self.launch_delay_years))


# Default US profile: full revenue, no delay, certain access.
_US_DEFAULT = RegionalProfile(
    revenue_ratio=1.0,
    launch_delay_years=0.0,
    reimbursement_probability=1.0,
    probability_of_regional_approval=1.0,
)


class GeographySplit(BaseModel, frozen=True):
    """
    Multi-region revenue breakdown for global asset valuation.

    Usage
    -----
    Set geography_split on MarketModel to compute global revenue as a sum of
    per-region contributions. When not set, MarketModel defaults to US-only
    (or CommercialInputs.ex_us_revenue_multiple for Mode 4 backward compat).

    Typical ex-US revenue ratios (vs. US base, oncology specialty pharma):
      EU5:           0.28 – 0.40  (pricing 55-70% of US; larger population offset)
      Japan:         0.10 – 0.18  (pricing 45-55% of US; conservative reimbursement)
      China:         0.06 – 0.15  (pricing 20-35% of US; large population upside)
      Rest of World: 0.05 – 0.12  (basket of smaller markets)

    Launch delay benchmarks (years after US approval):
      EU5:           1.5 – 2.5 (EMA review + member-state reimbursement)
      Japan:         2.0 – 3.0 (PMDA review; local data often required)
      China:         2.5 – 4.0 (NMPA review; significant uncertainty)
      Rest of World: 1.5 – 3.0 (varies widely by country/region)

    The `us` field defaults to a full-revenue, no-delay profile and should
    almost never be overridden. Override only if modeling a non-US primary
    market or applying a US-specific reimbursement haircut.

    Example
    -------
    # Typical global oncology: US + EU5 + Japan + China
    GeographySplit(
        eu5=RegionalProfile(revenue_ratio=0.32, launch_delay_years=2.0,
                            reimbursement_probability=0.85),
        japan=RegionalProfile(revenue_ratio=0.14, launch_delay_years=2.5,
                              probability_of_regional_approval=0.90),
        china=RegionalProfile(revenue_ratio=0.10, launch_delay_years=3.5,
                              reimbursement_probability=0.70,
                              probability_of_regional_approval=0.80),
    )
    """

    us: RegionalProfile = Field(
        default=_US_DEFAULT,
        description=(
            "US region profile. Defaults to revenue_ratio=1.0, no delay, "
            "full reimbursement and approval probability. Override only for "
            "non-US primary market modeling or US reimbursement haircuts."
        ),
    )
    eu5: Optional[RegionalProfile] = Field(
        default=None,
        description=(
            "EU5 (France, Germany, Italy, Spain, UK) combined region. "
            "Typical revenue_ratio: 0.28–0.40; launch_delay_years: 1.5–2.5."
        ),
    )
    japan: Optional[RegionalProfile] = Field(
        default=None,
        description=(
            "Japan (PMDA-regulated). "
            "Typical revenue_ratio: 0.10–0.18; launch_delay_years: 2.0–3.0. "
            "Set probability_of_regional_approval < 1.0 when local trial data "
            "is not yet available."
        ),
    )
    china: Optional[RegionalProfile] = Field(
        default=None,
        description=(
            "China (NMPA-regulated). "
            "Typical revenue_ratio: 0.06–0.15; launch_delay_years: 2.5–4.0. "
            "Higher uncertainty — use reimbursement_probability and "
            "probability_of_regional_approval to haircut accordingly."
        ),
    )
    rest_of_world: Optional[RegionalProfile] = Field(
        default=None,
        description=(
            "Rest of World basket (Canada, Australia, LatAm, ROW). "
            "Typical revenue_ratio: 0.05–0.12; launch_delay_years: 1.5–3.0."
        ),
    )

    def active_regions(self) -> dict[str, RegionalProfile]:
        """
        Return all configured regions as {region_name: RegionalProfile}.

        US is always included. Ex-US regions are included only when explicitly
        set (non-None). Order: us, eu5, japan, china, rest_of_world.
        """
        result: dict[str, RegionalProfile] = {"us": self.us}
        for name in ("eu5", "japan", "china", "rest_of_world"):
            region = getattr(self, name)
            if region is not None:
                result[name] = region
        return result

    def global_revenue_in_year(
        self,
        us_revenue_fn: Callable[[int], float],
        year: int,
    ) -> float:
        """
        Compute total global revenue in post-US-launch year `year`.

        For each active region:
            regional_rev = US_revenue(year − delay_bucketed)
                           × effective_revenue_scalar

        Where:
          - US_revenue(t') is `us_revenue_fn(t')`, returning 0 for t' ≤ 0
            or t' beyond the US patent life.
          - delay_bucketed = floor(launch_delay_years) — conservative bucketing.
          - effective_revenue_scalar = revenue_ratio × reimbursement_probability
                                       × probability_of_regional_approval.

        Parameters
        ----------
        us_revenue_fn : Callable[[int], float]
            Function returning US-only revenue for a given post-launch year.
            Must return 0.0 for year ≤ 0 or beyond the US patent window.
        year : int
            Post-US-launch year to compute global revenue for (1-indexed).

        Returns
        -------
        float
            Total global revenue in USD millions.
        """
        total = 0.0
        for region in self.active_regions().values():
            us_year = year - region.delay_years_bucketed
            if us_year < 1:
                # Region has not launched yet relative to the US launch calendar.
                continue
            regional_us_rev = us_revenue_fn(us_year)
            total += regional_us_rev * region.effective_revenue_scalar
        return total

    @property
    def implied_ex_us_scalar(self) -> float:
        """
        Approximate ex-US revenue as a multiple of US base at steady state.

        Computed as the sum of effective_revenue_scalar across all non-US
        regions. Does NOT account for launch delays (delay effects reduce
        early-year ex-US revenue but do not affect steady-state scalar).

        Useful for quick sanity-checking: implied_ex_us_scalar=0.55 means
        ex-US at peak ≈ 55% of US peak, for a global/US ratio of 1.55x.
        """
        return sum(
            r.effective_revenue_scalar
            for name, r in self.active_regions().items()
            if name != "us"
        )
