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

import math
from typing import Optional

from pydantic import BaseModel

from bve.models.market_model import MarketModel
from bve.models.revenue_audit import RevenueAuditTable, build_audit_table


_LOE_TAIL_KEYS = (
    "year_1_loss", "year_2_loss", "year_3_loss",
    "year_4_loss", "year_5_loss",   # Sprint 9.10: extended from 3 to 5 tail years
)


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

    geo_extension_years: int = 0   # extra years added for delayed-region patent coverage

    revenue_by_year: list[float]   # gross revenue (net of G2N), yr 1..patent_life+geo_ext+tail
    gross_profit_by_year: list[float]
    ebit_by_year: list[float]

    peak_sales_millions: float     # competition-adjusted peak revenue during patent period
    peak_revenue_millions: float   # explicit alias — same value, clearer name for Step 5+

    diagnostics: RevenueDiagnostics

    audit_table: Optional[RevenueAuditTable] = None
    """Year-by-year multiplier decomposition (Task E1). None only when RevenueModel is called
    without a MarketModel reference (e.g., direct construction in tests)."""

    @property
    def total_years(self) -> int:
        """Patent years + geo-extension years + LOE tail years."""
        return self.patent_life_years + self.geo_extension_years + self.loe_tail_years


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
        RevenueStream with total_years = patent_life_years + geo_extension_years + loe_tail_years.
        """
        pl = market_model.patent_life_years
        eff_life = market_model._effective_patent_life()
        geo = market_model.geography_split
        cogs = market_model.cogs_rate

        # Count LOE tail years available in the profile
        loe_tail_count = sum(1 for k in _LOE_TAIL_KEYS if k in (loe_profile or {}))

        # Post-LOE SG&A collapses at LOE — marketing spend drops while COGS remains.
        # This typically produces HIGHER EBIT margins post-LOE than pre-LOE.
        sgna_fraction = float((loe_profile or {}).get("post_loe_sgna_fraction", 0.30))
        post_loe_sgna_rate = market_model.sgna_rate_mature * sgna_fraction

        if geo is not None:
            # ---------------------------------------------------------------
            # Geography-extended path (Sprint A3)
            # ---------------------------------------------------------------
            # Compute how many extra years are needed for delayed regions to
            # complete their own patent-protected window.
            geo_extension = math.ceil(
                max(r.launch_delay_years for r in geo.active_regions().values())
            )
            # Full horizon: US patent + delayed-region patent extension + LOE tail
            total_horizon = eff_life + geo_extension + loe_tail_count

            # Build the extended US+LOE callable so that each region's LOE
            # clock starts at its own patent expiry, not the US patent expiry.
            us_loe_fn = market_model._make_us_loe_revenue_fn(loe_profile)

            revenue_by_year: list[float] = []
            gross_profit_by_year: list[float] = []
            ebit_by_year: list[float] = []

            for y in range(1, total_horizon + 1):
                if y <= eff_life + geo_extension:
                    # Patent window (US or delayed regions still patent-protected).
                    # market_model.revenue_in_year / ebit_in_year already dispatch
                    # through geography using _us_base_revenue_in_year, which
                    # returns 0 past eff_life for the US — leaving only the
                    # revenue of whichever regions are still in their patent window.
                    rev = market_model.revenue_in_year(y)
                    gp = rev * (1.0 - cogs)
                    ebit = market_model.ebit_in_year(y)
                else:
                    # LOE tail years: geography with the US+LOE callable so each
                    # region's erosion starts at its own patent expiry.
                    rev = geo.global_revenue_in_year(us_loe_fn, y)
                    gp = rev * (1.0 - cogs)
                    ebit = gp - rev * post_loe_sgna_rate
                revenue_by_year.append(rev)
                gross_profit_by_year.append(gp)
                ebit_by_year.append(ebit)

            # Segment decomposition extended to match full horizon length
            by_segment = market_model.revenue_by_lot()
            seg_len = len(next(iter(by_segment.values()), []))
            for seg in by_segment:
                # Pad patent extension years
                for extra_y in range(seg_len + 1, eff_life + geo_extension + 1):
                    by_segment[seg].append(market_model.revenue_in_year(extra_y))
                # Append LOE tail approximation per segment (proportional to segment peak)
                if loe_tail_count > 0:
                    seg_peak = max(by_segment[seg]) if by_segment[seg] else 0.0
                    total_peak = market_model.peak_sales_millions
                    for key in _LOE_TAIL_KEYS:
                        if key not in (loe_profile or {}):
                            break
                        loss_frac = float(loe_profile[key])  # type: ignore[index]
                        by_segment[seg].append(
                            seg_peak * (1.0 - loss_frac) if total_peak > 0 else 0.0
                        )

            by_segment_geography = {seg: {"global": curve} for seg, curve in by_segment.items()}
            peak_by_segment = {seg: max(curve) if curve else 0.0 for seg, curve in by_segment.items()}
            peak_sales = market_model.peak_sales_millions

            stream = RevenueStream(
                asset_id=market_model.asset_id,
                patent_life_years=eff_life,
                geo_extension_years=geo_extension,
                loe_tail_years=loe_tail_count,
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
            stream = stream.model_copy(update={"audit_table": build_audit_table(
                market_model=market_model,
                revenue_by_year=revenue_by_year,
                gross_profit_by_year=gross_profit_by_year,
                ebit_by_year=ebit_by_year,
                patent_life_years=eff_life,
                geo_extension_years=geo_extension,
                loe_tail_years=loe_tail_count,
                post_loe_sgna_rate=post_loe_sgna_rate,
            )})
            return stream

        # -----------------------------------------------------------------------
        # Non-geography path (unchanged)
        # -----------------------------------------------------------------------
        years = list(range(1, eff_life + 1))

        revenue_by_year = [market_model.revenue_in_year(y) for y in years]
        gross_profit_by_year = [market_model.gross_profit_in_year(y) for y in years]
        ebit_by_year = [market_model.ebit_in_year(y) for y in years]

        # --- Post-LOE tail (Step 3) ---
        loe_tail_years = 0
        if loe_profile is not None:
            peak = market_model.peak_sales_millions

            for key in _LOE_TAIL_KEYS:
                if key not in loe_profile:
                    break   # profile does not define further erosion years
                loss_frac = float(loe_profile[key])
                tail_rev = peak * (1.0 - loss_frac)
                tail_gp = tail_rev * (1.0 - cogs)
                tail_ebit = tail_gp - tail_rev * post_loe_sgna_rate
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
                seg_peak = max(by_segment[seg]) if by_segment[seg] else 0.0
                seg_fraction = seg_peak / peak if peak > 0 else 0.0
                for key in _LOE_TAIL_KEYS:
                    if key not in loe_profile:  # type: ignore[operator]
                        break
                    loss_frac = float(loe_profile[key])  # type: ignore[index]
                    by_segment[seg].append(seg_peak * (1.0 - loss_frac) if seg_fraction > 0 else 0.0)

        # Wrap segments into segment_geography structure (geography="global" for now)
        by_segment_geography = {
            seg: {"global": curve}
            for seg, curve in by_segment.items()
        }

        peak_by_segment = {
            seg: max(curve) if curve else 0.0
            for seg, curve in by_segment.items()
        }

        peak_sales = market_model.peak_sales_millions

        stream = RevenueStream(
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
        return stream.model_copy(update={"audit_table": build_audit_table(
            market_model=market_model,
            revenue_by_year=revenue_by_year,
            gross_profit_by_year=gross_profit_by_year,
            ebit_by_year=ebit_by_year,
            patent_life_years=pl,
            geo_extension_years=0,
            loe_tail_years=loe_tail_years,
            post_loe_sgna_rate=post_loe_sgna_rate,
        )})
