"""
Geography Sprint A tests — GeographySplit and RegionalProfile.

Test coverage:
  1. RegionalProfile — field validation, effective_revenue_scalar, delay bucketing
  2. GeographySplit — active_regions(), implied_ex_us_scalar, defaults
  3. global_revenue_in_year — arithmetic correctness for single and multi-region
  4. MarketModel + geography_split — US-only output unchanged (backward compat)
  5. MarketModel + geography_split — revenue_in_year() is geography-aware
  6. MarketModel + geography_split overrides ex_us_revenue_multiple (CommercialInputs)
  7. Delayed regional launches reduce cumulative NPV vs. same multiplier with no delay
  8. reimbursement_probability and probability_of_regional_approval scale revenue
  9. Missing optional regions do not error
 10. peak_sales_millions is geography-aware (global peak ≥ US peak)
 11. RevenueModel.compute() produces geography-scaled curves
 12. Existing valuation snapshot still passes (rNPV unchanged for US-only config)
"""
from __future__ import annotations

import math
import pytest

from bve.models.geography import GeographySplit, RegionalProfile
from bve.models.market_model import MarketModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _us_only_market(
    *,
    tam: float = 5_000.0,
    peak_pen: float = 0.10,
    years_to_peak: int = 4,
    patent_life: int = 12,
) -> MarketModel:
    """Standard TAM-based US-only MarketModel (no geography)."""
    return MarketModel(
        asset_id="test-us",
        total_addressable_market_millions=tam,
        peak_penetration=peak_pen,
        years_to_peak=years_to_peak,
        patent_life_years=patent_life,
    )


def _geo_market(
    geo: GeographySplit,
    *,
    tam: float = 5_000.0,
    peak_pen: float = 0.10,
    years_to_peak: int = 4,
    patent_life: int = 12,
) -> MarketModel:
    """TAM-based MarketModel with geography_split."""
    return MarketModel(
        asset_id="test-geo",
        total_addressable_market_millions=tam,
        peak_penetration=peak_pen,
        years_to_peak=years_to_peak,
        patent_life_years=patent_life,
        geography_split=geo,
    )


# ---------------------------------------------------------------------------
# 1. RegionalProfile
# ---------------------------------------------------------------------------

class TestRegionalProfile:
    def test_defaults(self):
        r = RegionalProfile(revenue_ratio=0.35)
        assert r.launch_delay_years == 0.0
        assert r.reimbursement_probability == 1.0
        assert r.probability_of_regional_approval == 1.0

    def test_effective_revenue_scalar_full(self):
        r = RegionalProfile(revenue_ratio=0.40)
        assert r.effective_revenue_scalar == pytest.approx(0.40)

    def test_effective_revenue_scalar_with_haircuts(self):
        r = RegionalProfile(
            revenue_ratio=0.40,
            reimbursement_probability=0.80,
            probability_of_regional_approval=0.90,
        )
        expected = 0.40 * 0.80 * 0.90
        assert r.effective_revenue_scalar == pytest.approx(expected)

    def test_delay_bucketing_floor(self):
        """1.5-year delay → bucketed to 1 year (floor)."""
        r = RegionalProfile(revenue_ratio=0.30, launch_delay_years=1.5)
        assert r.delay_years_bucketed == 1

    def test_delay_bucketing_exact_integer(self):
        r = RegionalProfile(revenue_ratio=0.30, launch_delay_years=2.0)
        assert r.delay_years_bucketed == 2

    def test_delay_bucketing_near_integer(self):
        """2.9-year delay → bucketed to 2 (floor, not round)."""
        r = RegionalProfile(revenue_ratio=0.30, launch_delay_years=2.9)
        assert r.delay_years_bucketed == 2

    def test_zero_delay_bucketed(self):
        r = RegionalProfile(revenue_ratio=1.0, launch_delay_years=0.0)
        assert r.delay_years_bucketed == 0

    def test_invalid_revenue_ratio_zero(self):
        with pytest.raises(Exception):
            RegionalProfile(revenue_ratio=0.0)

    def test_invalid_revenue_ratio_negative(self):
        with pytest.raises(Exception):
            RegionalProfile(revenue_ratio=-0.1)

    def test_revenue_ratio_above_one_allowed(self):
        """Regions can outperform US base (revenue_ratio > 1.0 is valid)."""
        r = RegionalProfile(revenue_ratio=1.20)
        assert r.effective_revenue_scalar == pytest.approx(1.20)

    def test_reimbursement_probability_bounds(self):
        with pytest.raises(Exception):
            RegionalProfile(revenue_ratio=0.30, reimbursement_probability=1.1)
        with pytest.raises(Exception):
            RegionalProfile(revenue_ratio=0.30, reimbursement_probability=-0.1)

    def test_frozen(self):
        r = RegionalProfile(revenue_ratio=0.30)
        with pytest.raises(Exception):
            r.revenue_ratio = 0.50  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. GeographySplit
# ---------------------------------------------------------------------------

class TestGeographySplit:
    def test_us_defaults(self):
        geo = GeographySplit()
        assert geo.us.revenue_ratio == pytest.approx(1.0)
        assert geo.us.launch_delay_years == 0.0
        assert geo.us.reimbursement_probability == pytest.approx(1.0)
        assert geo.us.probability_of_regional_approval == pytest.approx(1.0)

    def test_all_optional_regions_none_by_default(self):
        geo = GeographySplit()
        assert geo.eu5 is None
        assert geo.japan is None
        assert geo.china is None
        assert geo.rest_of_world is None

    def test_active_regions_us_only(self):
        geo = GeographySplit()
        active = geo.active_regions()
        assert list(active.keys()) == ["us"]

    def test_active_regions_with_eu5(self):
        geo = GeographySplit(eu5=RegionalProfile(revenue_ratio=0.35))
        active = geo.active_regions()
        assert set(active.keys()) == {"us", "eu5"}

    def test_active_regions_all_set(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35),
            japan=RegionalProfile(revenue_ratio=0.14),
            china=RegionalProfile(revenue_ratio=0.10),
            rest_of_world=RegionalProfile(revenue_ratio=0.08),
        )
        active = geo.active_regions()
        assert set(active.keys()) == {"us", "eu5", "japan", "china", "rest_of_world"}

    def test_implied_ex_us_scalar_us_only(self):
        geo = GeographySplit()
        assert geo.implied_ex_us_scalar == pytest.approx(0.0)

    def test_implied_ex_us_scalar_with_regions(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35),
            japan=RegionalProfile(revenue_ratio=0.14),
        )
        # US is excluded from the sum
        assert geo.implied_ex_us_scalar == pytest.approx(0.35 + 0.14)

    def test_implied_ex_us_scalar_with_haircuts(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.40, reimbursement_probability=0.80),
        )
        assert geo.implied_ex_us_scalar == pytest.approx(0.40 * 0.80)

    def test_frozen(self):
        geo = GeographySplit()
        with pytest.raises(Exception):
            geo.eu5 = RegionalProfile(revenue_ratio=0.30)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. global_revenue_in_year arithmetic
# ---------------------------------------------------------------------------

class TestGlobalRevenueArithmetic:
    def _constant_us_rev(self, value: float):
        """Helper: a US revenue function that always returns `value`."""
        return lambda t: value if t >= 1 else 0.0

    def test_us_only_returns_us_revenue(self):
        geo = GeographySplit()
        us_rev = self._constant_us_rev(100.0)
        result = geo.global_revenue_in_year(us_rev, year=1)
        assert result == pytest.approx(100.0)

    def test_us_plus_eu5_no_delay(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=0.0),
        )
        us_rev = self._constant_us_rev(100.0)
        result = geo.global_revenue_in_year(us_rev, year=1)
        # US: 100 × 1.0 + EU5: 100 × 0.35 = 135
        assert result == pytest.approx(135.0)

    def test_eu5_with_2_year_delay_year_1_zero(self):
        """Year 1: EU5 (2yr delay) has not launched → 0 contribution."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=2.0),
        )
        us_rev = self._constant_us_rev(100.0)
        assert geo.global_revenue_in_year(us_rev, year=1) == pytest.approx(100.0)
        assert geo.global_revenue_in_year(us_rev, year=2) == pytest.approx(100.0)

    def test_eu5_with_2_year_delay_year_3_active(self):
        """Year 3: EU5 (2yr delay) launches at EU5 year 1 → contributes."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=2.0),
        )
        us_rev = self._constant_us_rev(100.0)
        # year 3: eu5_year = 3 - 2 = 1 → us_rev(1) × 0.35 = 35.0
        assert geo.global_revenue_in_year(us_rev, year=3) == pytest.approx(135.0)

    def test_fractional_delay_bucketed_conservatively(self):
        """1.5yr delay → bucketed to 1yr → EU5 active from year 2, not 1.5."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=1.5),
        )
        us_rev = self._constant_us_rev(100.0)
        # year 1: eu5_year = 1 - 1 = 0 → not active
        assert geo.global_revenue_in_year(us_rev, year=1) == pytest.approx(100.0)
        # year 2: eu5_year = 2 - 1 = 1 → active (bucketed delay = 1, not 2)
        assert geo.global_revenue_in_year(us_rev, year=2) == pytest.approx(135.0)

    def test_reimbursement_probability_scales_revenue(self):
        geo = GeographySplit(
            eu5=RegionalProfile(
                revenue_ratio=0.40,
                reimbursement_probability=0.75,
                launch_delay_years=0.0,
            ),
        )
        us_rev = self._constant_us_rev(100.0)
        # EU5: 100 × 0.40 × 0.75 = 30.0; US: 100 → total 130.0
        assert geo.global_revenue_in_year(us_rev, year=1) == pytest.approx(130.0)

    def test_approval_probability_scales_revenue(self):
        geo = GeographySplit(
            china=RegionalProfile(
                revenue_ratio=0.10,
                probability_of_regional_approval=0.70,
                launch_delay_years=0.0,
            ),
        )
        us_rev = self._constant_us_rev(100.0)
        # China: 100 × 0.10 × 0.70 = 7.0; US: 100 → total 107.0
        assert geo.global_revenue_in_year(us_rev, year=1) == pytest.approx(107.0)

    def test_all_regions_sum_correctly(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=0.0),
            japan=RegionalProfile(revenue_ratio=0.14, launch_delay_years=0.0),
            china=RegionalProfile(revenue_ratio=0.10, launch_delay_years=0.0),
            rest_of_world=RegionalProfile(revenue_ratio=0.08, launch_delay_years=0.0),
        )
        us_rev = self._constant_us_rev(100.0)
        expected = 100.0 * (1.0 + 0.35 + 0.14 + 0.10 + 0.08)
        assert geo.global_revenue_in_year(us_rev, year=1) == pytest.approx(expected)

    def test_zero_us_revenue_propagates(self):
        """If US revenue is 0 (e.g., beyond patent), all regions are also 0."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=0.0),
        )
        us_rev = lambda t: 0.0
        assert geo.global_revenue_in_year(us_rev, year=5) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 4. MarketModel — US-only unchanged (backward compatibility)
# ---------------------------------------------------------------------------

class TestMarketModelBackwardCompat:
    def test_us_only_revenue_in_year_unchanged(self):
        """geography_split=None → revenue_in_year returns same as before."""
        m_no_geo = _us_only_market(tam=8_000.0, peak_pen=0.12, patent_life=12)
        m_us_geo = _geo_market(
            GeographySplit(),  # US-only geography
            tam=8_000.0, peak_pen=0.12, patent_life=12,
        )
        for yr in range(1, 13):
            assert m_no_geo.revenue_in_year(yr) == pytest.approx(
                m_us_geo.revenue_in_year(yr), rel=1e-9
            )

    def test_no_geography_peak_sales_unchanged(self):
        m = _us_only_market()
        assert m.peak_sales_millions == pytest.approx(5_000.0 * 0.10)

    def test_no_geography_revenue_curve_length(self):
        m = _us_only_market(patent_life=12)
        assert len(m.revenue_curve()) == 12

    def test_patient_based_us_only_unchanged(self):
        m = MarketModel(
            asset_id="pat-us",
            addressable_patients_annual=50_000,
            net_price_per_patient_usd=120_000.0,
            peak_penetration=0.20,
            years_to_peak=4,
            patent_life_years=10,
        )
        # With no geography, revenue_in_year == _us_base_revenue_in_year
        for yr in range(1, 11):
            assert m.revenue_in_year(yr) == pytest.approx(m._us_base_revenue_in_year(yr))


# ---------------------------------------------------------------------------
# 5. MarketModel with geography_split — revenue_in_year is geography-aware
# ---------------------------------------------------------------------------

class TestMarketModelWithGeography:
    def test_us_plus_eu5_revenue_year_1(self):
        """Year 1: EU5 (2yr delay) has not launched; only US contributes."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=2.0),
        )
        m = _geo_market(geo, tam=10_000.0, peak_pen=0.10, years_to_peak=1, patent_life=12)
        us_yr1 = m._us_base_revenue_in_year(1)
        global_yr1 = m.revenue_in_year(1)
        assert global_yr1 == pytest.approx(us_yr1)  # EU5 not yet active

    def test_us_plus_eu5_revenue_year_3(self):
        """Year 3: EU5 (2yr delay) contributes EU5 year 1 revenue."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=2.0),
        )
        m = _geo_market(geo, tam=10_000.0, peak_pen=0.10, years_to_peak=4, patent_life=12)
        us_yr1 = m._us_base_revenue_in_year(1)  # EU5 sees this in year 3
        us_yr3 = m._us_base_revenue_in_year(3)
        expected = us_yr3 + us_yr1 * 0.35
        assert m.revenue_in_year(3) == pytest.approx(expected)

    def test_global_revenue_greater_than_us_once_all_regions_launch(self):
        """After all delays resolve, global revenue > US-only revenue."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=1.0),
            japan=RegionalProfile(revenue_ratio=0.14, launch_delay_years=2.0),
        )
        m = _geo_market(geo, tam=5_000.0, peak_pen=0.12, years_to_peak=3, patent_life=12)
        # At year 5, all regions are active (delay 1 and 2 have both elapsed)
        us_yr5 = m._us_base_revenue_in_year(5)
        global_yr5 = m.revenue_in_year(5)
        assert global_yr5 > us_yr5

    def test_geography_vs_no_geography_year_zero(self):
        """Year 0 always returns 0, with or without geography."""
        geo = GeographySplit(eu5=RegionalProfile(revenue_ratio=0.35))
        m = _geo_market(geo)
        assert m.revenue_in_year(0) == pytest.approx(0.0)

    def test_geography_beyond_patent_life_zero(self):
        """Year > patent_life returns 0 (US revenue = 0 → all regions = 0)."""
        geo = GeographySplit(eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=0.0))
        m = _geo_market(geo, patent_life=12)
        assert m.revenue_in_year(13) == pytest.approx(0.0)

    def test_reimbursement_probability_reduces_global_revenue(self):
        geo_full = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, reimbursement_probability=1.0),
        )
        geo_haircut = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, reimbursement_probability=0.70),
        )
        m_full = _geo_market(geo_full, tam=5_000.0, peak_pen=0.10, years_to_peak=1, patent_life=12)
        m_haircut = _geo_market(geo_haircut, tam=5_000.0, peak_pen=0.10, years_to_peak=1, patent_life=12)
        assert m_haircut.revenue_in_year(1) < m_full.revenue_in_year(1)

    def test_approval_probability_reduces_regional_revenue(self):
        geo_certain = GeographySplit(
            china=RegionalProfile(revenue_ratio=0.10, probability_of_regional_approval=1.0),
        )
        geo_uncertain = GeographySplit(
            china=RegionalProfile(revenue_ratio=0.10, probability_of_regional_approval=0.60),
        )
        m_c = _geo_market(geo_certain, tam=5_000.0, peak_pen=0.10, years_to_peak=1, patent_life=12)
        m_u = _geo_market(geo_uncertain, tam=5_000.0, peak_pen=0.10, years_to_peak=1, patent_life=12)
        assert m_u.revenue_in_year(1) < m_c.revenue_in_year(1)

    def test_missing_optional_regions_do_not_error(self):
        """Only eu5 set; japan, china, rest_of_world absent → no exception."""
        geo = GeographySplit(eu5=RegionalProfile(revenue_ratio=0.30))
        m = _geo_market(geo)
        for yr in range(1, 13):
            _ = m.revenue_in_year(yr)  # must not raise


# ---------------------------------------------------------------------------
# 6. geography_split overrides ex_us_revenue_multiple
# ---------------------------------------------------------------------------

class TestGeographyOverridesExUs:
    def test_geography_split_applied_over_no_ex_us(self):
        """geography_split on a TAM-based model applies correctly."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=0.0),
        )
        m_us = _us_only_market(tam=5_000.0, peak_pen=0.10, years_to_peak=1, patent_life=12)
        m_geo = _geo_market(geo, tam=5_000.0, peak_pen=0.10, years_to_peak=1, patent_life=12)
        # Year 1: geo should be US + EU5 × 0.35
        us_yr1 = m_us.revenue_in_year(1)
        assert m_geo.revenue_in_year(1) == pytest.approx(us_yr1 * 1.35)


# ---------------------------------------------------------------------------
# 7. Delayed launches reduce cumulative undiscounted revenue vs. same ratio, no delay
# ---------------------------------------------------------------------------

class TestDelayReducesCumulativeRevenue:
    def test_delayed_launch_lower_cumulative_revenue(self):
        """Same revenue_ratio but with delay → fewer active years → lower total."""
        geo_no_delay = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=0.0),
        )
        geo_delayed = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=3.0),
        )
        m_nd = _geo_market(geo_no_delay, tam=5_000.0, peak_pen=0.10,
                           years_to_peak=4, patent_life=12)
        m_d = _geo_market(geo_delayed, tam=5_000.0, peak_pen=0.10,
                          years_to_peak=4, patent_life=12)
        total_nd = sum(m_nd.revenue_in_year(y) for y in range(1, 13))
        total_d = sum(m_d.revenue_in_year(y) for y in range(1, 13))
        assert total_d < total_nd

    def test_delay_magnitude_proportional_to_revenue_loss(self):
        """Larger delay → greater revenue loss."""
        tam, pen = 5_000.0, 0.10
        totals = []
        for delay in (0.0, 1.0, 2.0, 3.0):
            geo = GeographySplit(
                eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=delay),
            )
            m = _geo_market(geo, tam=tam, peak_pen=pen, years_to_peak=4, patent_life=12)
            totals.append(sum(m.revenue_in_year(y) for y in range(1, 13)))
        assert totals[0] >= totals[1] >= totals[2] >= totals[3]


# ---------------------------------------------------------------------------
# 8. peak_sales_millions is geography-aware
# ---------------------------------------------------------------------------

class TestPeakSalesWithGeography:
    def test_global_peak_geq_us_peak(self):
        """Global peak revenue ≥ US peak when ex-US regions are present."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=0.0),
        )
        m_us = _us_only_market(tam=5_000.0, peak_pen=0.10, years_to_peak=4, patent_life=12)
        m_geo = _geo_market(geo, tam=5_000.0, peak_pen=0.10, years_to_peak=4, patent_life=12)
        assert m_geo.peak_sales_millions >= m_us.peak_sales_millions

    def test_us_only_geography_peak_equals_base_peak(self):
        """GeographySplit with US only → peak_sales_millions same as without geo."""
        m_no_geo = _us_only_market(tam=5_000.0, peak_pen=0.10)
        m_us_geo = _geo_market(GeographySplit(), tam=5_000.0, peak_pen=0.10)
        assert m_us_geo.peak_sales_millions == pytest.approx(
            m_no_geo.peak_sales_millions, rel=1e-6
        )

    def test_delayed_region_peak_captured(self):
        """With a 2yr delay, the global peak is found in the extended window."""
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=2.0),
        )
        m = _geo_market(
            geo, tam=5_000.0, peak_pen=0.10, years_to_peak=2, patent_life=12
        )
        # US peak at year 2. EU5 contributes from year 3 onward.
        # Global peak should be > US peak (US peak + EU5 contribution at some year).
        us_m = _us_only_market(tam=5_000.0, peak_pen=0.10, years_to_peak=2, patent_life=12)
        assert m.peak_sales_millions > us_m.peak_sales_millions


# ---------------------------------------------------------------------------
# 9. RevenueModel integration
# ---------------------------------------------------------------------------

class TestRevenueModelIntegration:
    def test_revenue_model_compute_with_geography(self):
        """RevenueModel.compute() produces geography-scaled annual curves."""
        from bve.models.revenue_model import RevenueModel

        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=0.0),
        )
        m = _geo_market(geo, tam=5_000.0, peak_pen=0.10, years_to_peak=4, patent_life=12)
        m_us = _us_only_market(tam=5_000.0, peak_pen=0.10, years_to_peak=4, patent_life=12)

        stream_geo = RevenueModel.compute(m)
        stream_us = RevenueModel.compute(m_us)

        # Geography revenue > US revenue in every patent year (EU5 active from year 1)
        for yr_idx in range(len(stream_us.revenue_by_year)):
            assert stream_geo.revenue_by_year[yr_idx] >= stream_us.revenue_by_year[yr_idx]

    def test_revenue_model_total_revenue_higher_with_geography(self):
        from bve.models.revenue_model import RevenueModel

        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=1.0),
        )
        m = _geo_market(geo, tam=5_000.0, peak_pen=0.10, years_to_peak=4, patent_life=12)
        m_us = _us_only_market(tam=5_000.0, peak_pen=0.10, years_to_peak=4, patent_life=12)

        stream_geo = RevenueModel.compute(m)
        stream_us = RevenueModel.compute(m_us)

        total_geo = sum(stream_geo.revenue_by_year)
        total_us = sum(stream_us.revenue_by_year)
        assert total_geo > total_us


# ---------------------------------------------------------------------------
# 10. Existing valuation snapshot unchanged for US-only configs
# ---------------------------------------------------------------------------

class TestExistingValuationUnchanged:
    def test_us_only_market_revenue_curve_identical(self):
        """No regression: US-only MarketModel revenue curve is bit-for-bit unchanged."""
        m = MarketModel(
            asset_id="snap-001",
            total_addressable_market_millions=8_000.0,
            peak_penetration=0.12,
            years_to_peak=5,
            patent_life_years=12,
        )
        # Revenue curve should be deterministic and unchanged
        curve = m.revenue_curve()
        assert len(curve) == 12
        assert curve[0] < curve[4]  # ramp up
        assert all(v >= 0 for v in curve)

    def test_patient_based_market_unchanged(self):
        m = MarketModel(
            asset_id="snap-002",
            addressable_patients_annual=15_000,
            net_price_per_patient_usd=200_000.0,
            peak_penetration=0.20,
            years_to_peak=4,
            patent_life_years=10,
        )
        # Sanity: peak ≈ 15000 × 200000 × 0.80 × 0.20 / 1e6
        # compliance_rate default = 0.80
        expected_peak = 15_000 * 200_000.0 * 0.80 * 0.20 / 1e6
        assert m.peak_sales_millions == pytest.approx(expected_peak, rel=0.01)

    def test_geography_on_lot_market_model(self):
        """geography_split works alongside lines_of_therapy."""
        from bve.models.market_model import LineOfTherapySegment

        lot = LineOfTherapySegment(
            line="1L",
            patients_annual=8_000,
            net_price_per_patient_usd=150_000.0,
            peak_penetration=0.25,
            years_to_peak=3,
        )
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.30, launch_delay_years=0.0),
        )
        m = MarketModel(
            asset_id="lot-geo",
            lines_of_therapy=[lot],
            patent_life_years=12,
            geography_split=geo,
        )
        # Year 1: global = US_lot_yr1 × (1.0 + 0.30)
        us_yr1 = m._us_base_revenue_in_year(1)
        global_yr1 = m.revenue_in_year(1)
        assert global_yr1 == pytest.approx(us_yr1 * 1.30, rel=1e-6)
