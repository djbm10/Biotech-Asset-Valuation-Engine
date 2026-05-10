"""
Tests for RevenueAuditTable — year-by-year revenue decomposition.

Invariants verified:
  1. Row count == total_years (patent + geo_extension + loe_tail)
  2. net_revenue matches RevenueStream.revenue_by_year exactly
  3. gross_profit matches RevenueStream.gross_profit_by_year exactly
  4. ebit matches RevenueStream.ebit_by_year exactly
  5. gross_profit == net_revenue × (1 - cogs_rate)
  6. sgna_expense == gross_profit - ebit
  7. net_revenue ≈ gross_uptake × competition_fraction × price_mult × payer_mult (non-geo)
  8. LOE status labels are correct
  9. Region breakdown sums to net_revenue (geography mode)
 10. Summary stats (peak_year, total_patent_revenue, total_loe_revenue, total_ebit)
"""
from __future__ import annotations

import pytest

from bve.models.competition_model import CompetitionModel, CompetitorLaunch
from bve.models.market_model import MarketModel
from bve.models.payer_access import PayerAccessModel
from bve.models.geography import GeographySplit, RegionalProfile
from bve.models.revenue_audit import RevenueAuditTable, build_audit_table
from bve.models.revenue_model import RevenueModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market(**kw) -> MarketModel:
    base = dict(
        asset_id="audit-test",
        therapeutic_area="oncology",
        total_addressable_market_millions=1000.0,
        peak_penetration=0.10,
        patent_life_years=10,
        cogs_rate=0.20,
        sgna_rate_launch=0.40,
        sgna_rate_mature=0.20,
        sgna_ramp_years=5,
    )
    base.update(kw)
    return MarketModel(**base)


def _rev(mm: MarketModel, loe_profile=None) -> RevenueModel:
    return RevenueModel.compute(mm, loe_profile=loe_profile)


# ---------------------------------------------------------------------------
# 1. Basic structure
# ---------------------------------------------------------------------------

class TestAuditTableStructure:
    def test_row_count_matches_total_years(self):
        mm = _market()
        rev = _rev(mm)
        assert len(rev.audit_table.rows) == rev.total_years

    def test_row_count_with_loe(self):
        from bve.config.assumptions_loader import AssumptionsLoader
        mm = _market(modality="small_molecule")
        loe = AssumptionsLoader.get().loe_erosion_profile("small_molecule")
        rev = _rev(mm, loe_profile=loe)
        assert len(rev.audit_table.rows) == rev.total_years
        assert rev.loe_tail_years > 0

    def test_asset_id_propagated(self):
        mm = _market()
        rev = _rev(mm)
        assert rev.audit_table.asset_id == "audit-test"

    def test_year_numbers_are_sequential(self):
        mm = _market()
        rev = _rev(mm)
        years = [r.year for r in rev.audit_table.rows]
        assert years == list(range(1, rev.total_years + 1))


# ---------------------------------------------------------------------------
# 2. Financial invariants — net_revenue, gross_profit, ebit must match RevenueStream
# ---------------------------------------------------------------------------

class TestFinancialInvariants:
    def test_net_revenue_matches_stream(self):
        mm = _market()
        rev = _rev(mm)
        for i, row in enumerate(rev.audit_table.rows):
            assert row.net_revenue == pytest.approx(rev.revenue_by_year[i], rel=1e-4), (
                f"Year {row.year}: audit net_revenue={row.net_revenue} != "
                f"stream={rev.revenue_by_year[i]}"
            )

    def test_gross_profit_matches_stream(self):
        mm = _market()
        rev = _rev(mm)
        for i, row in enumerate(rev.audit_table.rows):
            assert row.gross_profit == pytest.approx(rev.gross_profit_by_year[i], rel=1e-4)

    def test_ebit_matches_stream(self):
        mm = _market()
        rev = _rev(mm)
        for i, row in enumerate(rev.audit_table.rows):
            assert row.ebit == pytest.approx(rev.ebit_by_year[i], rel=1e-4)

    def test_gross_profit_equals_revenue_minus_cogs(self):
        mm = _market()
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            if row.net_revenue < 1e-9:
                continue
            expected_gp = row.net_revenue * (1.0 - row.cogs_rate)
            assert row.gross_profit == pytest.approx(expected_gp, rel=1e-4)

    def test_sgna_expense_equals_gp_minus_ebit(self):
        mm = _market()
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            assert row.sgna_expense == pytest.approx(row.gross_profit - row.ebit, rel=1e-4)

    def test_cogs_rate_consistent(self):
        mm = _market(cogs_rate=0.30)
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            if row.net_revenue > 1e-9 and not row.loe_status.startswith("loe_tail"):
                # Within patent window cogs_rate = model.cogs_rate
                assert row.cogs_rate == pytest.approx(0.30, rel=1e-4)


# ---------------------------------------------------------------------------
# 3. Multiplier decomposition (non-geography)
# ---------------------------------------------------------------------------

class TestMultiplierDecomposition:
    def test_no_competition_fraction_is_one(self):
        mm = _market()
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            if not row.loe_status.startswith("loe_tail"):
                assert row.competition_fraction == pytest.approx(1.0)

    def test_no_price_pressure_multiplier_is_one(self):
        mm = _market()
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            assert row.price_pressure_multiplier == pytest.approx(1.0)

    def test_no_payer_multiplier_is_one(self):
        mm = _market()
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            assert row.payer_combined_multiplier == pytest.approx(1.0)

    def test_gross_uptake_equals_net_revenue_when_no_multipliers(self):
        """No competition, no payer → gross_uptake == net_revenue."""
        mm = _market()
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            if not row.loe_status.startswith("loe_tail"):
                assert row.gross_uptake_revenue == pytest.approx(row.net_revenue, rel=1e-4)

    def test_competition_fraction_reduces_revenue(self):
        comp = CompetitionModel(competitors=[
            CompetitorLaunch(name="Rival", status="approved",
                             launch_year_relative=0, peak_market_share=0.30, years_to_peak=3),
        ])
        mm_base = _market()
        mm_comp = _market(competition_model=comp)
        rev_base = _rev(mm_base)
        rev_comp = _rev(mm_comp)
        for i, row in enumerate(rev_comp.audit_table.rows):
            if not row.loe_status.startswith("loe_tail") and row.year > 1:
                assert row.competition_fraction < 1.0
                assert row.net_revenue < rev_base.revenue_by_year[i] + 1e-6

    def test_price_pressure_multiplier_compounds(self):
        comp = CompetitionModel(
            competitors=[
                CompetitorLaunch(name="Rival", status="approved",
                                 launch_year_relative=0, peak_market_share=0.20, years_to_peak=3),
            ],
            base_annual_price_erosion_rate=0.05,
            price_pressure_factor_per_competitor=0.03,
        )
        mm = _market(competition_model=comp)
        rev = _rev(mm)
        # multiplier should be strictly decreasing over patent years (as erosion compounds)
        patent_mults = [
            r.price_pressure_multiplier
            for r in rev.audit_table.rows
            if r.loe_status == "patent_protected"
        ]
        assert patent_mults[0] == pytest.approx(1.0)  # Year 1: no erosion yet
        assert all(patent_mults[i] >= patent_mults[i + 1] for i in range(len(patent_mults) - 1))

    def test_payer_multiplier_below_one_in_early_years(self):
        payer = PayerAccessModel(
            access_probability=0.80,
            coverage_delay_months=6.0,
            prior_auth_burden=0.40,
        )
        mm = _market(payer_access=payer)
        rev = _rev(mm)
        row_y1 = rev.audit_table.rows[0]
        assert row_y1.payer_combined_multiplier < 1.0
        # Year 3+: step_edit_risk=0, so multiplier stabilizes
        row_y3 = rev.audit_table.rows[2]
        assert row_y3.payer_combined_multiplier < 1.0  # access_prob × PA burden still applies

    def test_back_calculation_identity_non_geo(self):
        """net_revenue ≈ gross_uptake × comp × price × payer for non-geography models."""
        comp = CompetitionModel(
            competitors=[
                CompetitorLaunch(name="Rival", status="approved",
                                 launch_year_relative=1, peak_market_share=0.25, years_to_peak=3),
            ],
            base_annual_price_erosion_rate=0.03,
        )
        payer = PayerAccessModel(access_probability=0.75, prior_auth_burden=0.30)
        mm = _market(competition_model=comp, payer_access=payer)
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            if row.loe_status.startswith("loe_tail"):
                continue
            implied = (
                row.gross_uptake_revenue
                * row.competition_fraction
                * row.price_pressure_multiplier
                * row.payer_combined_multiplier
            )
            # Should reconstruct net_revenue (within rounding)
            assert implied == pytest.approx(row.net_revenue, rel=1e-3), (
                f"Year {row.year}: gross_uptake × mults = {implied:.4f} != net={row.net_revenue:.4f}"
            )


# ---------------------------------------------------------------------------
# 4. LOE status labels
# ---------------------------------------------------------------------------

class TestLOEStatusLabels:
    def test_all_patent_protected_without_loe(self):
        mm = _market()
        rev = _rev(mm)
        statuses = {r.loe_status for r in rev.audit_table.rows}
        assert statuses == {"patent_protected"}

    def test_loe_tail_labels(self):
        from bve.config.assumptions_loader import AssumptionsLoader
        mm = _market(modality="small_molecule")
        loe = AssumptionsLoader.get().loe_erosion_profile("small_molecule")
        rev = _rev(mm, loe_profile=loe)
        patent_rows = [r for r in rev.audit_table.rows if r.loe_status == "patent_protected"]
        loe_rows = [r for r in rev.audit_table.rows if r.loe_status.startswith("loe_tail")]
        assert len(patent_rows) == mm.patent_life_years
        assert len(loe_rows) == rev.loe_tail_years
        for n, row in enumerate(loe_rows, start=1):
            assert row.loe_status == f"loe_tail_{n}"

    def test_loe_multipliers_are_one(self):
        """During LOE tail, multipliers are reported as 1.0 (not applicable)."""
        from bve.config.assumptions_loader import AssumptionsLoader
        payer = PayerAccessModel(access_probability=0.70, prior_auth_burden=0.50)
        mm = _market(modality="small_molecule", payer_access=payer)
        loe = AssumptionsLoader.get().loe_erosion_profile("small_molecule")
        rev = _rev(mm, loe_profile=loe)
        for row in rev.audit_table.rows:
            if row.loe_status.startswith("loe_tail"):
                assert row.competition_fraction == pytest.approx(1.0)
                assert row.price_pressure_multiplier == pytest.approx(1.0)
                assert row.payer_combined_multiplier == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. Summary statistics
# ---------------------------------------------------------------------------

class TestSummaryStats:
    def test_peak_year_is_highest_revenue_year(self):
        mm = _market()
        rev = _rev(mm)
        table = rev.audit_table
        actual_peak_row = max(rev.audit_table.rows, key=lambda r: r.net_revenue)
        assert table.peak_year == actual_peak_row.year
        assert table.peak_net_revenue == pytest.approx(actual_peak_row.net_revenue, rel=1e-4)

    def test_total_patent_revenue_sums_correctly(self):
        mm = _market()
        rev = _rev(mm)
        table = rev.audit_table
        expected = sum(
            r.net_revenue for r in table.rows
            if r.loe_status in ("patent_protected", "geo_extension")
        )
        assert table.total_patent_revenue == pytest.approx(expected, rel=1e-4)

    def test_total_loe_revenue_zero_without_loe(self):
        mm = _market()
        rev = _rev(mm)
        assert rev.audit_table.total_loe_revenue == pytest.approx(0.0)

    def test_total_loe_revenue_positive_with_loe(self):
        from bve.config.assumptions_loader import AssumptionsLoader
        mm = _market(modality="small_molecule")
        loe = AssumptionsLoader.get().loe_erosion_profile("small_molecule")
        rev = _rev(mm, loe_profile=loe)
        assert rev.audit_table.total_loe_revenue > 0.0

    def test_total_ebit_sums_rows(self):
        mm = _market()
        rev = _rev(mm)
        table = rev.audit_table
        assert table.total_ebit == pytest.approx(sum(r.ebit for r in table.rows), rel=1e-4)


# ---------------------------------------------------------------------------
# 6. Geography region breakdown
# ---------------------------------------------------------------------------

class TestGeographyRegionBreakdown:
    def test_region_breakdown_empty_without_geo(self):
        mm = _market()
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            assert row.region_breakdown == {}

    def test_region_breakdown_keys_match_active_regions(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.30, launch_delay_years=2.0),
        )
        mm = _market(geography_split=geo)
        rev = _rev(mm)
        # All patent-protected rows should have us + eu5 keys
        for row in rev.audit_table.rows:
            if row.loe_status == "patent_protected":
                assert "us" in row.region_breakdown
                assert "eu5" in row.region_breakdown

    def test_region_breakdown_sums_to_net_revenue(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.30, launch_delay_years=2.0),
            japan=RegionalProfile(revenue_ratio=0.12, launch_delay_years=2.5),
        )
        mm = _market(geography_split=geo)
        rev = _rev(mm)
        for row in rev.audit_table.rows:
            if row.region_breakdown and not row.loe_status.startswith("loe_tail"):
                region_sum = sum(row.region_breakdown.values())
                assert region_sum == pytest.approx(row.net_revenue, rel=1e-3), (
                    f"Year {row.year}: region sum={region_sum:.4f} != net={row.net_revenue:.4f}"
                )

    def test_eu5_zero_in_launch_delay_years(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.30, launch_delay_years=2.0),
        )
        mm = _market(geography_split=geo)
        rev = _rev(mm)
        # EU5 should contribute 0 in years 1 and 2 (before the 2-year delay completes)
        for row in rev.audit_table.rows[:2]:
            assert row.region_breakdown.get("eu5", 0.0) == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 7. to_table_dict() serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_table_dict_returns_list_of_dicts(self):
        mm = _market()
        rev = _rev(mm)
        rows = rev.audit_table.to_table_dict()
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)
        assert len(rows) == len(rev.audit_table.rows)

    def test_to_table_dict_contains_required_keys(self):
        mm = _market()
        rev = _rev(mm)
        required = {
            "year", "loe_status", "gross_uptake_revenue", "competition_fraction",
            "price_pressure_multiplier", "payer_combined_multiplier", "net_revenue",
            "cogs_rate", "gross_profit", "sgna_rate", "sgna_expense", "ebit",
            "region_breakdown",
        }
        for row in rev.audit_table.to_table_dict():
            assert required.issubset(row.keys())
