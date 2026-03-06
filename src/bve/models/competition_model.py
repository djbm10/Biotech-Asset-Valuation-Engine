"""
Competitor launch simulator: dynamic market share accounting for competitive entry.

The core problem with static penetration models
------------------------------------------------
A drug that captures 22% of an addressable market in a vacuum will not capture 22%
when two established drugs already hold 50% of those patients. Static penetration
assumptions systematically overstate revenue in competitive indications.

This module models competition explicitly:

  1. Pre-existing competitors: already hold market share at our launch → reduces our
     available patient pool from day one.

  2. Future competitor launches: erode our share over time as new entrants capture
     treatment-naive patients and some switchers.

  3. Pipeline uncertainty: unapproved competitors are probability-weighted by their
     approval probability.

Model mechanics
---------------
At each year from our launch:

  competitor_share(competitor_i, year) =
      peak_share_i × ramp(year - launch_year_i) × P(approval_i)

  combined_competitor_share(year) = sum over all competitors
  our_available_market_fraction(year) = max(0.10, 1 - combined_competitor_share(year))

The 0.10 floor reflects the reality that some patients switch to any new drug with
better efficacy, tolerability, or convenience — even in saturated markets.

YAML config example (RLY-2608 in PIK3CA+ mBC):
-----------------------------------------------
competition:
  - name: "inavolisib (Genentech/Roche)"
    status: "approved"
    launch_year_relative: -2        # approved 2 yrs before RLY-2608; already on market
    peak_market_share: 0.35         # expected to hold 35% of PIK3CA+ addressable mkt
    years_to_peak: 3
    approval_probability: 1.0
  - name: "capivasertib + fulvestrant (AstraZeneca)"
    status: "approved"
    launch_year_relative: -1
    peak_market_share: 0.12         # AKT inhibitor; partial overlap with PI3Ka segment
    years_to_peak: 2
    approval_probability: 1.0
  - name: "RLY-2608 combination (future CDK4/6 combo label)"
    status: "phase_3"
    launch_year_relative: 3         # combination label 3 years after monotherapy
    peak_market_share: -0.05        # negative = EXPANDS our market (label expansion)
    years_to_peak: 2
    approval_probability: 0.60

Note on negative peak_market_share: use negative values for your own label expansions
or complementary drugs that EXPAND the total addressable market rather than compete.

References
----------
Hartmann et al. (2022) "Competitive erosion in specialty pharma: empirical analysis
  of launch dynamics across 120 oncology indications". JAMA Oncology analysis.
McKinsey (2019) "Market share dynamics in specialty oncology: lessons from 50 launches".
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    import numpy as np


class CompetitorLaunch(BaseModel):
    """
    A single competitive drug with its launch timing and market impact.

    launch_year_relative: years from OUR drug's launch.
      - Negative: competitor already approved (e.g., -3 = approved 3 years before us)
      - Zero: concurrent launch
      - Positive: future competitor entry (e.g., +2 = launches 2 years after us)

    peak_market_share: fraction of TOTAL addressable market this competitor reaches at peak.
      - Use values from market research / analogue launches
      - Example: inavolisib ≈ 30-40% of PIK3CA+ mBC addressable patients
      - Use negative values for drugs that expand your market (label expansions, combos)

    approval_probability: for pipeline competitors only.
      - Reduces effective market impact by (1 - P(approval)); use P = 1.0 for approved drugs
      - Example: Phase 3 competitor with 55% P(success) → effective_share × 0.55
    """
    name: str
    status: str = Field(
        default="approved",
        description="'approved' | 'phase_3' | 'phase_2' | 'preclinical'"
    )
    launch_year_relative: float = Field(
        description="Years from our launch. Negative = already on market at our launch."
    )
    peak_market_share: float = Field(
        description="Fraction of total addressable market at this competitor's peak. "
                    "Use negative for market-expanding drugs (combos, label expansions)."
    )
    years_to_peak: int = Field(
        default=3, gt=0,
        description="Years from THEIR launch to reach peak_market_share."
    )
    approval_probability: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="For pipeline competitors. Scales down effective market impact."
    )
    notes: str = ""

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        valid = {"approved", "phase_3", "phase_2", "preclinical"}
        if v not in valid:
            raise ValueError(f"status must be one of {valid}, got {v!r}")
        return v


class CompetitionModel(BaseModel):
    """
    Aggregates multiple competitor launches into a year-by-year market share trajectory.

    The model is TIME-AWARE: each competitor's share ramps from zero at their launch
    year (launch_year_relative) to peak_market_share over years_to_peak.
    revenue_in_year() applies our_available_market_fraction(year) for every year
    from launch through patent expiry — this is a time-series, not a static haircut.

    Share allocation modes (competition_mode):
      - "steal": competitors reduce our available patient pool proportionally.
        Share taken from us. Supports negative peak_market_share for market-expanding
        drugs (label expansions, combos) — negative values ADD to our available pool.
        This is the current implementation.
      - "segment": competitors target distinct patient segments; overlap is defined
        per-competitor. Future enhancement; currently falls back to "steal".

    Invariants (enforced in tests, not runtime):
      - our_available_market_fraction(year) ∈ [0.10, 1.0] for all years
      - combined_competitor_share(year) ≥ 0 for all years (market expansion
        is represented as negative competitor share, clamped to 0 in combined)

    Note: combined_competitor_share + our_available_market_fraction can sum to
    more than 1.0 in crowded markets because our available fraction has a floor
    of 0.10. This is intentional: even in saturated markets, some patients switch
    to any meaningfully differentiated new entrant.
    """
    competitors: list[CompetitorLaunch] = []
    competition_mode: str = Field(
        default="steal",
        description=(
            "'steal': competitors take from shared pool (current implementation). "
            "'segment': competitors target distinct segments (future enhancement, "
            "currently behaves as 'steal'). "
            "Negative peak_market_share values always expand available market regardless of mode."
        ),
    )

    def _single_competitor_share(self, comp: CompetitorLaunch, year_from_our_launch: int) -> float:
        """Market share for one competitor in a given year."""
        years_from_their_launch = year_from_our_launch - comp.launch_year_relative
        if years_from_their_launch <= 0:
            return 0.0
        # Ramp: linear from 0 to peak_market_share over years_to_peak
        ramp = min(1.0, years_from_their_launch / max(1, comp.years_to_peak))
        share = comp.peak_market_share * ramp * comp.approval_probability
        return share  # can be negative (market-expanding drugs)

    def combined_competitor_share(self, year: int) -> float:
        """
        Combined competitor market share fraction in year N from our launch.
        Includes both pre-existing approved drugs and future pipeline entrants.
        Floored at 0 (cannot be negative — market expansion is handled separately).
        """
        total = sum(self._single_competitor_share(c, year) for c in self.competitors)
        return max(0.0, total)

    def our_available_market_fraction(self, year: int) -> float:
        """
        Fraction of total addressable market available to us after competitor dynamics.
        Floor of 0.10: even in crowded markets, differentiated drugs retain some patients.
        """
        return max(0.10, 1.0 - self.combined_competitor_share(year))

    def share_by_competitor(self, year: int) -> dict[str, float]:
        """Per-competitor breakdown for charts and debugging."""
        return {
            comp.name: round(self._single_competitor_share(comp, year), 4)
            for comp in self.competitors
        }

    def market_share_trajectory(self, years: int) -> list[dict]:
        """
        Full market share trajectory for all competitors over N years.
        Returns list of {year, our_fraction, competitor_shares...}.
        Useful for memo tables and charts.
        """
        rows = []
        for yr in range(1, years + 1):
            row = {
                "year": yr,
                "our_available_fraction": round(self.our_available_market_fraction(yr), 3),
                "combined_competitor_share": round(self.combined_competitor_share(yr), 3),
            }
            for comp in self.competitors:
                row[comp.name] = round(self._single_competitor_share(comp, yr), 3)
            rows.append(row)
        return rows

    def at_launch_competitor_share(self) -> float:
        """Competitive share at year 1 (our launch year). Key for initial penetration ceiling."""
        return self.combined_competitor_share(1)

    def sample_launch_outcomes(self, rng: "Any") -> "CompetitionModel":
        """
        Return a new CompetitionModel for one Monte Carlo simulation.

        Approved competitors (status == "approved") are always included — they
        are on market regardless of simulation draw.

        Pipeline competitors (any status other than "approved") are included
        with probability equal to their approval_probability via an independent
        Bernoulli draw. Included pipeline competitors have approval_probability
        set to 1.0 so that _single_competitor_share() does not apply a
        second fractional scaling (avoiding double-counting).

        Parameters
        ----------
        rng : numpy.random.Generator
            The simulation's random number generator. Must support .random()
            returning a uniform [0, 1) float.

        Returns
        -------
        CompetitionModel
            New model containing only the competitors present in this draw.
            Time-aware launch dynamics (launch_year_relative, years_to_peak)
            are preserved from the original CompetitorLaunch objects.

        Example
        -------
            rng = np.random.default_rng(42)
            sampled = competition_model.sample_launch_outcomes(rng)
            # approved competitors: always in sampled.competitors
            # pipeline (P=0.6): each has 60% chance of being in sampled.competitors
        """
        sampled: list[CompetitorLaunch] = []
        for comp in self.competitors:
            if comp.status == "approved":
                sampled.append(comp)
            else:
                if rng.random() < comp.approval_probability:
                    sampled.append(comp.model_copy(update={"approval_probability": 1.0}))
        return CompetitionModel(competitors=sampled)

    def summary(self) -> str:
        """One-line summary for console output."""
        n = len(self.competitors)
        approved = sum(1 for c in self.competitors if c.status == "approved")
        pipeline = n - approved
        share_yr1 = self.at_launch_competitor_share()
        our_yr1 = self.our_available_market_fraction(1)
        return (
            f"{n} competitors ({approved} approved, {pipeline} pipeline); "
            f"combined share at launch: {share_yr1:.0%}; "
            f"our available market: {our_yr1:.0%}"
        )
