"""
RevenueModel — computes the commercial revenue profile from launch.

Inputs:  MarketModel (fully configured, including competition and segments).
         loe_profile (optional dict from AssumptionsLoader.loe_erosion_profile()).
Output:  RevenueStream — year-by-year revenue and EBIT curves, plus diagnostics.

This model is stateless.  It does not discount cash flows and has no knowledge
of probability-of-approval, trial timelines, or ownership structure.
All revenue logic (including post-LOE tail) lives here exclusively.
RNPVModel only does discounting.

Step 3: LOE erosion
-------------------
When loe_profile is provided, three tail years are appended to the revenue curve
beyond patent_life_years.  Revenue in each tail year =
    peak_sales_millions × (1 - loss_fraction(tail_year))

Where loss_fraction keys are: year_1_loss, year_2_loss, year_3_loss.
Post-LOE EBIT uses a REDUCED SG&A rate: marketing spend collapses at LOE while
COGS remains.  This typically produces HIGHER EBIT margins post-LOE than pre-LOE.
    post_loe_sgna = sgna_rate_mature × post_loe_sgna_fraction
    post_loe_sgna_fraction is stored in the profile (default 0.30 if absent).

The extended ebit_by_year is consumed by RNPVModel directly; no other model
needs to know about the tail structure.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from bve.models.market_model import MarketModel


_LOE_TAIL_KEYS = ("year_1_loss", "year_2_loss", "year_3_loss")


# ---------------------------------------------------------------------------
# Diagnostic sub-object
# ---------------------------------------------------------------------------

class RevenueDiagnostics(BaseModel):
    """
    Decomposed revenue for inspection and invariant verification.

    Invariants (enforced by RevenueModel and tested):
      combined[yr] == sum(by_segment_geography[seg]["global"][yr]) ∀ yr
      all values >= 0
    """
    # Primary decomposition: {segment: {geography: [revenue_yr1, ...]}}
    # Geographies are "global" until geo-launch modeling is added in a later step.
    by_segment_geography: dict[str, dict[str, list[float]]]

    # Flat view by segment for convenience (geography already collapsed)
    by_segment: dict[str, list[float]]

    # Combined total — mirrors RevenueStream.revenue_by_year for diagnostics access
    combined: list[float]

    # Peak contribution per segment
    peak_sales_by_segment: dict[str, float]


# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------

class RevenueStream(BaseModel):
    """Output of RevenueModel.compute()."""
    asset_id: str
    patent_life_years: int         # core patent period (excluding LOE tail)
    loe_tail_years: int            # number of tail years appended (0 if no LOE)

    revenue_by_year: list[float]   # gross revenue (net of G2N), yr 1..patent_life+tail
    gross_profit_by_year: list[float]
    ebit_by_year: list[float]

    peak_sales_millions: float     # competition-adjusted peak revenue during patent period
    peak_revenue_millions: float   # explicit alias — same value, clearer name for Step 5+

    diagnostics: RevenueDiagnostics

    @property
    def total_years(self) -> int:
        """Patent years + LOE tail years."""
        return self.patent_life_years + self.loe_tail_years


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class RevenueModel:
    """
    Stateless engine that materialises the full commercial revenue profile,
    optionally extended with a post-LOE erosion tail.

    Delegates all within-patent revenue arithmetic to MarketModel methods
    (which already encapsulate LOT-segment, competition, and cost-structure logic).
    LOE tail logic is implemented here and nowhere else.
    """

    @staticmethod
    def compute(
        market_model: MarketModel,
        loe_profile: Optional[dict] = None,
    ) -> RevenueStream:
        """
        Build revenue, gross-profit, and EBIT profiles.

        Parameters
        ----------
        market_model : MarketModel
            Fully configured market model.
        loe_profile : dict, optional
            LOE erosion profile from AssumptionsLoader.loe_erosion_profile(modality).
            Keys: year_1_loss, year_2_loss, year_3_loss, terminal_loss.
            When provided, three tail years are appended to every curve.

        Returns
        -------
        RevenueStream with total_years = patent_life_years + loe_tail_years.
        """
        pl = market_model.patent_life_years
        years = list(range(1, pl + 1))

        # --- Within-patent revenue ---
        revenue_by_year = [market_model.revenue_in_year(y) for y in years]
        gross_profit_by_year = [market_model.gross_profit_in_year(y) for y in years]
        ebit_by_year = [market_model.ebit_in_year(y) for y in years]

        # --- Post-LOE tail (Step 3) ---
        loe_tail_years = 0
        if loe_profile is not None:
            peak = market_model.peak_sales_millions
            cogs = market_model.cogs_rate
            # Post-LOE SG&A collapses: marketing spend drops sharply while COGS
            # remains.  This typically produces HIGHER EBIT margins than pre-LOE.
            # post_loe_sgna_fraction is stored in the profile (default 0.30 if absent).
            sgna_fraction = float(loe_profile.get("post_loe_sgna_fraction", 0.30))
            post_loe_sgna = market_model.sgna_rate_mature * sgna_fraction

            for key in _LOE_TAIL_KEYS:
                loss_frac = float(loe_profile[key])
                tail_rev = peak * (1.0 - loss_frac)
                tail_gp = tail_rev * (1.0 - cogs)
                tail_ebit = tail_gp - tail_rev * post_loe_sgna
                revenue_by_year.append(tail_rev)
                gross_profit_by_year.append(tail_gp)
                ebit_by_year.append(tail_ebit)
                loe_tail_years += 1

        # --- Segment decomposition (for diagnostics + invariant testing) ---
        by_segment = market_model.revenue_by_lot()

        # Extend segments with LOE tail if applied
        if loe_tail_years > 0:
            peak = market_model.peak_sales_millions
            for seg in by_segment:
                # Segment share of peak = peak_seg / total_peak
                seg_peak = max(by_segment[seg]) if by_segment[seg] else 0.0
                seg_fraction = seg_peak / peak if peak > 0 else 0.0
                for key in _LOE_TAIL_KEYS:
                    loss_frac = float(loe_profile[key])  # type: ignore[index]
                    by_segment[seg].append(seg_peak * (1.0 - loss_frac) if seg_fraction > 0 else 0.0)

        # Wrap segments into segment_geography structure (geography="global" for now)
        by_segment_geography: dict[str, dict[str, list[float]]] = {
            seg: {"global": curve}
            for seg, curve in by_segment.items()
        }

        peak_by_segment = {
            seg: max(curve) if curve else 0.0
            for seg, curve in by_segment.items()
        }

        peak_sales = market_model.peak_sales_millions

        return RevenueStream(
            asset_id=market_model.asset_id,
            patent_life_years=pl,
            loe_tail_years=loe_tail_years,
            revenue_by_year=revenue_by_year,
            gross_profit_by_year=gross_profit_by_year,
            ebit_by_year=ebit_by_year,
            peak_sales_millions=peak_sales,
            peak_revenue_millions=peak_sales,
            diagnostics=RevenueDiagnostics(
                by_segment_geography=by_segment_geography,
                by_segment=by_segment,
                combined=revenue_by_year,
                peak_sales_by_segment=peak_by_segment,
            ),
        )
