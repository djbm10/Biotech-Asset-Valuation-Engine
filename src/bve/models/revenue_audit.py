"""
RevenueAuditTable — year-by-year revenue decomposition for transparency and auditability.

Each row in the table corresponds to one calendar year post-launch and exposes every
multiplicative factor that determines that year's net revenue, gross profit, and EBIT:

    gross_uptake_revenue          TAM × uptake_penetration (before competition or payer)
    × competition_fraction        our_available_market_fraction(year) from CompetitionModel
    × price_pressure_multiplier   cumulative price erosion from competitor count
    × payer_combined_multiplier   access_probability × PA burden × delay × step-edit ramp
    = net_revenue                 canonical output of market_model.revenue_in_year(year)

    gross_profit = net_revenue × (1 - cogs_rate)
    sgna_expense = net_revenue × sgna_rate
    ebit         = gross_profit - sgna_expense

For geography mode, region_breakdown gives each region's contribution to net_revenue.

Note on gross_uptake_revenue in geography mode
-----------------------------------------------
When geography_split is active, net_revenue is the global sum across all regions.
gross_uptake_revenue is back-calculated from the US-base revenue only (before the
geography scaling), so it represents the US-equivalent pre-multiplier revenue.
The multipliers (competition, payer) are applied inside _us_base_revenue_in_year()
before geography scaling, so the decomposition is exact for US-only models and
approximately correct for the US component of global models.

LOE status labels
-----------------
  "patent_protected"  — within the patent window (year 1..patent_life_years)
  "geo_extension"     — within geography extension (delayed region still protected)
  "loe_tail_N"        — Nth year of post-LOE erosion tail (N = 1..5)
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from bve.models.market_model import MarketModel


class RevenueAuditRow(BaseModel, frozen=True):
    """One year's revenue decomposition."""

    year: int
    """Calendar years post-launch (1 = first commercial year)."""

    loe_status: str
    """One of: patent_protected, geo_extension, loe_tail_1 … loe_tail_5."""

    # --- Multiplier stack ---
    gross_uptake_revenue: float
    """Pre-competition, pre-payer US base revenue (TAM × penetration). USD millions."""

    competition_fraction: float
    """our_available_market_fraction(year); 1.0 when no CompetitionModel configured."""

    price_pressure_multiplier: float
    """Cumulative price erosion multiplier; 1.0 when no price pressure configured."""

    payer_combined_multiplier: float
    """access_probability × (1 − PA burden × 0.5) × delay_fraction × step_edit ramp;
    1.0 when no PayerAccessModel configured."""

    # --- Resulting financials ---
    net_revenue: float
    """Canonical annual revenue. Matches RevenueStream.revenue_by_year[year-1]. USD millions."""

    cogs_rate: float
    """COGS as fraction of net_revenue applied this year."""

    gross_profit: float
    """net_revenue × (1 − cogs_rate). USD millions."""

    sgna_rate: float
    """Effective SG&A rate (blended between launch and mature). Fraction of net_revenue."""

    sgna_expense: float
    """net_revenue × sgna_rate. USD millions."""

    ebit: float
    """gross_profit − sgna_expense. Matches RevenueStream.ebit_by_year[year-1]. USD millions."""

    # --- Geography ---
    region_breakdown: dict[str, float]
    """Per-region net revenue contributions summing to net_revenue. Empty dict for US-only models."""


class RevenueAuditTable(BaseModel):
    """Full year-by-year revenue audit for one asset valuation."""

    asset_id: str
    rows: list[RevenueAuditRow]

    # Summary statistics
    peak_net_revenue: float
    """Maximum annual net revenue over the full horizon (patent + LOE tail). USD millions."""

    peak_year: int
    """Year (1-indexed post-launch) at which peak_net_revenue occurs."""

    total_patent_revenue: float
    """Sum of net_revenue across all patent_protected + geo_extension years. USD millions."""

    total_loe_revenue: float
    """Sum of net_revenue across all loe_tail years. USD millions (0 if no LOE tail)."""

    total_ebit: float
    """Sum of EBIT across all years. USD millions."""

    notes: list[str]
    """Audit notes — e.g. which features are active, geography caveat, etc."""

    def to_table_dict(self) -> list[dict]:
        """Flat list of dicts suitable for pandas.DataFrame() or JSON serialization."""
        return [r.model_dump() for r in self.rows]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_audit_table(
    market_model: "MarketModel",
    revenue_by_year: list[float],
    gross_profit_by_year: list[float],
    ebit_by_year: list[float],
    patent_life_years: int,
    geo_extension_years: int,
    loe_tail_years: int,
    post_loe_sgna_rate: float = 0.0,
) -> RevenueAuditTable:
    """
    Build a RevenueAuditTable from a computed RevenueStream's arrays plus the
    MarketModel (for multiplier access).

    Parameters
    ----------
    market_model : MarketModel
        The finalized market model (post SG&A resolution, post-modality injection).
    revenue_by_year, gross_profit_by_year, ebit_by_year : list[float]
        Directly from RevenueStream.  Must be the same arrays — not recomputed.
    patent_life_years : int
        From RevenueStream.patent_life_years (may differ from market_model.patent_life_years
        when geography extension is involved).
    geo_extension_years, loe_tail_years : int
        From RevenueStream.
    post_loe_sgna_rate : float
        The effective post-LOE SG&A rate (sgna_rate_mature × post_loe_sgna_fraction).
        Used to report the sgna_rate for LOE tail rows.
    """
    total_years = patent_life_years + geo_extension_years + loe_tail_years
    assert len(revenue_by_year) == total_years, (
        f"revenue_by_year length {len(revenue_by_year)} != "
        f"patent_life_years({patent_life_years}) + geo({geo_extension_years}) + loe({loe_tail_years})"
    )

    comp = market_model.competition_model
    payer = market_model.payer_access
    geo = market_model.geography_split
    has_geo = geo is not None

    notes: list[str] = []
    if has_geo:
        notes.append(
            "Geography active: gross_uptake_revenue reflects US-only pre-multiplier revenue; "
            "net_revenue is global (all regions). Region breakdown provided per year."
        )
    if comp is not None:
        notes.append(
            f"CompetitionModel active: {len(comp.competitors)} competitor(s) modeled. "
            "competition_fraction and price_pressure_multiplier vary by year."
        )
    if payer is not None:
        notes.append(
            f"PayerAccessModel active: access_probability={payer.access_probability:.0%}, "
            f"prior_auth_burden={payer.prior_auth_burden:.0%}, "
            f"coverage_delay={payer.coverage_delay_months:.0f}mo, "
            f"step_edit_risk={payer.step_edit_risk:.0%}."
        )
    if loe_tail_years > 0:
        notes.append(
            f"LOE tail: {loe_tail_years} year(s) appended. "
            f"Post-LOE SG&A rate={post_loe_sgna_rate:.1%}."
        )

    rows: list[RevenueAuditRow] = []

    for idx, (rev, gp, ebit) in enumerate(
        zip(revenue_by_year, gross_profit_by_year, ebit_by_year)
    ):
        year = idx + 1  # 1-indexed

        # --- LOE status ---
        if year <= patent_life_years:
            loe_status = "patent_protected"
        elif year <= patent_life_years + geo_extension_years:
            loe_status = "geo_extension"
        else:
            tail_n = year - patent_life_years - geo_extension_years
            loe_status = f"loe_tail_{tail_n}"

        is_loe = loe_status.startswith("loe_tail")

        # --- Multipliers (not meaningful in LOE tail — model applies peak×loss directly) ---
        if is_loe:
            competition_fraction = 1.0
            price_mult = 1.0
            payer_mult = 1.0
            sgna_rate = post_loe_sgna_rate
        else:
            competition_fraction = (
                comp.our_available_market_fraction(year) if comp is not None else 1.0
            )
            price_mult = (
                comp.price_pressure_multiplier(year) if comp is not None else 1.0
            )
            payer_mult = payer.combined_multiplier(year) if payer is not None else 1.0
            sgna_rate = market_model._sgna_rate_at_year(year)

        # --- Gross uptake back-calculation ---
        # net_revenue = gross_uptake × comp_frac × price_mult × payer_mult
        # For geography: net_revenue is global; gross_uptake is US-only equivalent.
        if is_loe:
            gross_uptake = rev  # LOE tail: no multipliers applied — revenue IS the gross
        else:
            combined_mult = competition_fraction * price_mult * payer_mult
            if combined_mult > 1e-10:
                # In geo mode, use US base revenue directly for gross_uptake
                # (avoids the geography scaling which already makes net_revenue global)
                us_net = market_model._us_base_revenue_in_year(year)
                gross_uptake = us_net / combined_mult if combined_mult > 1e-10 else us_net
            else:
                gross_uptake = 0.0

        # --- SG&A expense (derive from ebit and gp rather than re-computing) ---
        sgna_expense = gp - ebit  # gp - sgna_expense = ebit → sgna_expense = gp - ebit
        cogs_used = 1.0 - (gp / rev) if rev > 1e-10 else market_model.cogs_rate

        # --- Region breakdown ---
        region_breakdown: dict[str, float] = {}
        if has_geo and not is_loe:
            geo_regions = geo.active_regions()  # type: ignore[union-attr]
            for region_name, region in geo_regions.items():
                fractional_year = year - region.launch_delay_years
                if fractional_year < 1.0:
                    region_breakdown[region_name] = 0.0
                else:
                    floor_y = math.floor(fractional_year)
                    weight = fractional_year - floor_y
                    rev_floor = market_model._us_base_revenue_in_year(floor_y)
                    rev_ceil = (
                        market_model._us_base_revenue_in_year(floor_y + 1) if weight > 1e-9 else 0.0
                    )
                    interp = rev_floor * (1.0 - weight) + rev_ceil * weight
                    region_breakdown[region_name] = interp * region.effective_revenue_scalar

        rows.append(RevenueAuditRow(
            year=year,
            loe_status=loe_status,
            gross_uptake_revenue=round(gross_uptake, 4),
            competition_fraction=round(competition_fraction, 6),
            price_pressure_multiplier=round(price_mult, 6),
            payer_combined_multiplier=round(payer_mult, 6),
            net_revenue=round(rev, 4),
            cogs_rate=round(cogs_used, 6),
            gross_profit=round(gp, 4),
            sgna_rate=round(sgna_rate, 6),
            sgna_expense=round(sgna_expense, 4),
            ebit=round(ebit, 4),
            region_breakdown={k: round(v, 4) for k, v in region_breakdown.items()},
        ))

    # --- Summary statistics ---
    patent_rows = [r for r in rows if r.loe_status in ("patent_protected", "geo_extension")]
    loe_rows = [r for r in rows if r.loe_status.startswith("loe_tail")]

    if rows:
        peak_row = max(rows, key=lambda r: r.net_revenue)
        peak_net_revenue = peak_row.net_revenue
        peak_year = peak_row.year
    else:
        peak_net_revenue = 0.0
        peak_year = 0

    return RevenueAuditTable(
        asset_id=market_model.asset_id,
        rows=rows,
        peak_net_revenue=peak_net_revenue,
        peak_year=peak_year,
        total_patent_revenue=round(sum(r.net_revenue for r in patent_rows), 4),
        total_loe_revenue=round(sum(r.net_revenue for r in loe_rows), 4),
        total_ebit=round(sum(r.ebit for r in rows), 4),
        notes=notes,
    )
