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

Fractional launch delay interpolation
--------------------------------------
Regional launch delays are handled with linear interpolation — no bucketing or
rounding. A 1.5-year delay means the region is at "year 1.5" of the US revenue
curve in that calendar year. Revenue at fractional year positions is computed as:

    interpolated_revenue(fractional_year) =
        us_revenue(floor(fractional_year)) × (1 − weight)
        + us_revenue(ceil(fractional_year)) × weight
    where weight = fractional_year − floor(fractional_year)

If fractional_year < 1.0 (region has not yet reached its first full year of
launch), regional contribution is 0. This is consistent with the MarketModel
convention that revenue starts at year 1.

For a 1.5-year delay (EU-typical):
  - Calendar year 1: fractional = 1 − 1.5 = −0.5 < 1 → 0
  - Calendar year 2: fractional = 2 − 1.5 =  0.5 < 1 → 0
  - Calendar year 3: fractional = 3 − 1.5 =  1.5 → interp(rev_yr1, rev_yr2, 0.5)
  - Calendar year 4: fractional = 4 − 1.5 =  2.5 → interp(rev_yr2, rev_yr3, 0.5)

Integer delays (e.g. 2.0 years) produce exact integer lookup — no interpolation
needed — and behave identically to the prior implementation.

Sprint A known limitation
--------------------------
Revenue is computed over years 1..patent_life_years (the US patent window,
extended by any new_formulation lifecycle events). The peak_sales_millions
slow path extends the iteration window by ceil(max_regional_delay) years to
capture delayed-region peaks that fall just after the US patent boundary.

However, revenue curves from RevenueModel.compute() are still bounded by
patent_life_years. Ex-US revenue that would fall in calendar years beyond
patent_life_years is not captured in annual LOE-tail calculations.

Example: US patent 12 years, EU5 1.5-year delay → EU5 contributes from
calendar year 3 onward (year 3 = EU5 year 1.5), with the last contribution
interpolated near year 12. Calendar years 13–14 are excluded.

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


def _interpolate_us_revenue(
    us_revenue_fn: Callable[[int], float],
    fractional_year: float,
) -> float:
    """
    Return interpolated US revenue at a fractional year position on the curve.

    This is the core primitive for fractional-delay regional revenue modeling.
    It maps a (possibly non-integer) year position to a revenue value by
    linearly interpolating between adjacent integer-year points on the US curve.

    Parameters
    ----------
    us_revenue_fn : Callable[[int], float]
        US-only revenue for a given post-launch integer year.
        Must return 0.0 for year ≤ 0 or beyond the US patent window.
    fractional_year : float
        Position on the US revenue curve, in post-launch year units.
        May be non-integer (e.g., 1.5 means halfway between year 1 and year 2).

    Returns
    -------
    float
        Interpolated revenue in USD millions.

    Behavior
    --------
    - fractional_year < 1.0  → returns 0.0 (region has not yet reached its
      first full year of launch; consistent with MarketModel year-1 convention).
    - fractional_year is a whole number  → returns us_revenue_fn(int(year))
      with no interpolation.
    - fractional_year is between two integers → linear interpolation:
        weight = fractional_year − floor(fractional_year)
        result = us_revenue_fn(lower) × (1 − weight)
               + us_revenue_fn(upper) × weight
    - upper exceeds the patent horizon → us_revenue_fn(upper) returns 0.0
      (handled gracefully by the MarketModel boundary check; no special casing
      needed here).

    Examples
    --------
    # EU5 with 1.5-year delay at calendar year 3:
    #   fractional_year = 3 − 1.5 = 1.5
    #   → 0.5 × us_revenue_fn(1) + 0.5 × us_revenue_fn(2)
    _interpolate_us_revenue(rev_fn, 1.5)

    # Japan with 2.5-year delay at calendar year 5:
    #   fractional_year = 5 − 2.5 = 2.5
    #   → 0.5 × us_revenue_fn(2) + 0.5 × us_revenue_fn(3)
    _interpolate_us_revenue(rev_fn, 2.5)
    """
    if fractional_year < 1.0:
        return 0.0
    lower = int(math.floor(fractional_year))
    weight = fractional_year - lower
    if weight == 0.0:
        # Exact integer year — no interpolation needed.
        return us_revenue_fn(lower)
    upper = lower + 1
    return us_revenue_fn(lower) * (1.0 - weight) + us_revenue_fn(upper) * weight


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
            "Supports fractional values (e.g., 1.5, 2.5). Revenue at fractional "
            "positions is linearly interpolated between adjacent integer years of "
            "the US revenue curve via _interpolate_us_revenue(). "
            "Regional contribution is 0 until the fractional position reaches 1.0."
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
            fractional_us_year = year − region.launch_delay_years
            regional_rev = _interpolate_us_revenue(us_revenue_fn, fractional_us_year)
                           × effective_revenue_scalar

        Fractional-year interpolation
        ------------------------------
        Regional revenue at calendar year `year` is computed by placing the
        region at fractional position `year − launch_delay_years` on the US
        revenue curve and interpolating linearly:

          - fractional_us_year < 1.0 → 0 (region not yet at its first full year)
          - fractional_us_year is integer → exact lookup (no interpolation)
          - fractional_us_year between integers → weighted average of adjacent years

        This means a 1.5-year delayed EU5:
          year 1: fractional = −0.5 < 1 → 0
          year 2: fractional =  0.5 < 1 → 0
          year 3: fractional =  1.5 → 0.5 × us_rev(1) + 0.5 × us_rev(2)
          year 4: fractional =  2.5 → 0.5 × us_rev(2) + 0.5 × us_rev(3)

        Parameters
        ----------
        us_revenue_fn : Callable[[int], float]
            US-only revenue for a given post-launch integer year.
            Must return 0.0 for year ≤ 0 or beyond the US patent window.
        year : int
            Calendar post-US-launch year to compute global revenue for.

        Returns
        -------
        float
            Total global revenue in USD millions.
        """
        total = 0.0
        for region in self.active_regions().values():
            fractional_us_year = year - region.launch_delay_years
            regional_us_rev = _interpolate_us_revenue(us_revenue_fn, fractional_us_year)
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
