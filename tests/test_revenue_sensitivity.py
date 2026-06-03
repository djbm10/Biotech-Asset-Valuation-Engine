"""
Revenue sensitivity tests — verify that each commercial input moves revenue
in the correct direction and by approximately the right magnitude.

These are monotonicity and proportionality tests, not exact-value tests.
They ensure the revenue model responds logically to parameter changes and
catch accidental sign flips or broken multiplier chains.

Parameters tested:
  1. net_price / TAM
  2. peak_penetration
  3. launch delay (years_to_peak)
  4. access_probability
  5. prior_auth_burden
  6. annual price erosion (base_annual_price_erosion_rate)
  7. competition price pressure (price_pressure_factor_per_competitor)
  8. COGS rate
  9. SG&A rates (launch + mature)
"""
from __future__ import annotations

import pytest

from bve.models.competition_model import CompetitionModel, CompetitorLaunch
from bve.models.market_model import MarketModel
from bve.models.payer_access import PayerAccessModel
from bve.models.revenue_model import RevenueModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market(**kw) -> MarketModel:
    base = dict(
        asset_id="sens-test",
        therapeutic_area="oncology",
        total_addressable_market_millions=1000.0,
        peak_penetration=0.10,
        patent_life_years=12,
        cogs_rate=0.20,
        sgna_rate_launch=0.40,
        sgna_rate_mature=0.20,
        sgna_ramp_years=5,
    )
    base.update(kw)
    return MarketModel(**base)


def _peak(mm: MarketModel) -> float:
    return max(RevenueModel.compute(mm).revenue_by_year)


def _total_revenue(mm: MarketModel) -> float:
    return sum(RevenueModel.compute(mm).revenue_by_year)


def _total_ebit(mm: MarketModel) -> float:
    return sum(RevenueModel.compute(mm).ebit_by_year)


def _total_gross_profit(mm: MarketModel) -> float:
    return sum(RevenueModel.compute(mm).gross_profit_by_year)


# ---------------------------------------------------------------------------
# 1. TAM / net price — proportional to revenue
# ---------------------------------------------------------------------------

class TestTAMSensitivity:
    def test_higher_tam_higher_revenue(self):
        assert _total_revenue(_market(total_addressable_market_millions=2000)) > \
               _total_revenue(_market(total_addressable_market_millions=1000))

    def test_tam_doubles_revenue_doubles(self):
        r1 = _total_revenue(_market(total_addressable_market_millions=1000))
        r2 = _total_revenue(_market(total_addressable_market_millions=2000))
        assert r2 == pytest.approx(r1 * 2, rel=1e-4)

    def test_higher_net_price_higher_revenue(self):
        mm_lo = _market(
            total_addressable_market_millions=None,
            addressable_patients_annual=10_000,
            net_price_per_patient_usd=100_000,
        )
        mm_hi = _market(
            total_addressable_market_millions=None,
            addressable_patients_annual=10_000,
            net_price_per_patient_usd=200_000,
        )
        assert _total_revenue(mm_hi) == pytest.approx(_total_revenue(mm_lo) * 2, rel=1e-4)


# ---------------------------------------------------------------------------
# 2. Peak penetration — proportional to revenue
# ---------------------------------------------------------------------------

class TestPeakPenetrationSensitivity:
    def test_higher_penetration_higher_revenue(self):
        assert _total_revenue(_market(peak_penetration=0.20)) > \
               _total_revenue(_market(peak_penetration=0.10))

    def test_penetration_doubles_revenue_doubles(self):
        r1 = _total_revenue(_market(peak_penetration=0.05))
        r2 = _total_revenue(_market(peak_penetration=0.10))
        assert r2 == pytest.approx(r1 * 2, rel=1e-3)

    def test_penetration_impact_on_peak_sales(self):
        p1 = _peak(_market(peak_penetration=0.05))
        p2 = _peak(_market(peak_penetration=0.10))
        assert p2 == pytest.approx(p1 * 2, rel=1e-3)


# ---------------------------------------------------------------------------
# 3. Launch delay (years_to_peak) — later peak, different cumulative revenue
# ---------------------------------------------------------------------------

class TestLaunchDelaySensitivity:
    def test_slower_ramp_lower_early_revenue(self):
        mm_fast = _market(years_to_peak=2)
        mm_slow = _market(years_to_peak=7)
        rev_fast = RevenueModel.compute(mm_fast).revenue_by_year
        rev_slow = RevenueModel.compute(mm_slow).revenue_by_year
        # Year 1: fast ramp has higher revenue
        assert rev_fast[0] > rev_slow[0]

    def test_slower_ramp_peak_occurs_later(self):
        mm_fast = _market(years_to_peak=2, use_s_curve=True)
        mm_slow = _market(years_to_peak=7, use_s_curve=True)
        rev_fast = RevenueModel.compute(mm_fast).revenue_by_year
        rev_slow = RevenueModel.compute(mm_slow).revenue_by_year
        peak_year_fast = rev_fast.index(max(rev_fast)) + 1
        peak_year_slow = rev_slow.index(max(rev_slow)) + 1
        assert peak_year_slow >= peak_year_fast

    def test_slower_ramp_total_revenue_lower_or_equal(self):
        """Slower ramp means more years at low revenue → total NPV lower."""
        r_fast = _total_revenue(_market(years_to_peak=2))
        r_slow = _total_revenue(_market(years_to_peak=8))
        # The peak is the same; slow ramp loses early-year revenue
        assert r_slow <= r_fast


# ---------------------------------------------------------------------------
# 4. access_probability — scales effective penetration permanently
# ---------------------------------------------------------------------------

class TestAccessProbabilitySensitivity:
    def test_lower_access_lower_revenue_all_years(self):
        mm_hi = _market(payer_access=PayerAccessModel(access_probability=0.90))
        mm_lo = _market(payer_access=PayerAccessModel(access_probability=0.40))
        rev_hi = RevenueModel.compute(mm_hi).revenue_by_year
        rev_lo = RevenueModel.compute(mm_lo).revenue_by_year
        for y_hi, y_lo in zip(rev_hi, rev_lo):
            assert y_hi >= y_lo - 1e-6

    def test_access_probability_scales_peak_proportionally(self):
        base = _peak(_market())
        p1 = _peak(_market(payer_access=PayerAccessModel(access_probability=0.60)))
        # Without prior_auth_burden, effective_penetration_multiplier = access_prob
        assert p1 == pytest.approx(base * 0.60, rel=1e-3)

    def test_access_1_equals_no_payer_access(self):
        r_none = _total_revenue(_market())
        r_full = _total_revenue(_market(payer_access=PayerAccessModel(access_probability=1.0)))
        assert r_full == pytest.approx(r_none, rel=1e-6)


# ---------------------------------------------------------------------------
# 5. prior_auth_burden — reduces effective peak by (1 - burden × 0.5)
# ---------------------------------------------------------------------------

class TestPriorAuthBurdenSensitivity:
    def test_higher_burden_lower_revenue(self):
        mm_lo = _market(payer_access=PayerAccessModel(prior_auth_burden=0.20))
        mm_hi = _market(payer_access=PayerAccessModel(prior_auth_burden=0.80))
        assert _total_revenue(mm_hi) < _total_revenue(mm_lo)

    def test_pa_burden_effect_formula(self):
        """peak = base × (1 - burden × 0.5)."""
        base = _peak(_market())
        p50 = _peak(_market(payer_access=PayerAccessModel(prior_auth_burden=0.50)))
        expected = base * (1 - 0.50 * 0.5)  # × 0.75
        assert p50 == pytest.approx(expected, rel=1e-3)

    def test_zero_burden_no_effect(self):
        r_none = _total_revenue(_market())
        r_zero = _total_revenue(_market(payer_access=PayerAccessModel(prior_auth_burden=0.0)))
        assert r_zero == pytest.approx(r_none, rel=1e-6)


# ---------------------------------------------------------------------------
# 6. Annual price erosion — compounds over years, revenue monotonically decreases
# ---------------------------------------------------------------------------

class TestAnnualPriceErosionSensitivity:
    def _model_with_erosion(self, rate: float) -> MarketModel:
        comp = CompetitionModel(base_annual_price_erosion_rate=rate)
        return _market(competition_model=comp)

    def test_higher_erosion_lower_total_revenue(self):
        r_none = _total_revenue(_market())
        r_lo = _total_revenue(self._model_with_erosion(0.03))
        r_hi = _total_revenue(self._model_with_erosion(0.10))
        assert r_lo < r_none
        assert r_hi < r_lo

    def test_revenue_decreases_over_time_with_erosion(self):
        mm = self._model_with_erosion(0.05)
        rev = RevenueModel.compute(mm).revenue_by_year
        # After ramp-up peaks, revenue should trend downward due to price erosion
        audit = RevenueModel.compute(mm).audit_table
        mults = [r.price_pressure_multiplier for r in audit.rows if r.loe_status == "patent_protected"]
        # Multiplier is non-increasing (compounds year-over-year)
        assert all(mults[i] >= mults[i + 1] for i in range(len(mults) - 1))

    def test_zero_erosion_equals_no_competition(self):
        r_none = _total_revenue(_market())
        r_zero = _total_revenue(self._model_with_erosion(0.0))
        assert r_zero == pytest.approx(r_none, rel=1e-6)


# ---------------------------------------------------------------------------
# 7. Competition price pressure (per-competitor factor)
# ---------------------------------------------------------------------------

class TestCompetitionPricePressureSensitivity:
    def _model_with_pressure(self, factor: float) -> MarketModel:
        comp = CompetitionModel(
            competitors=[
                CompetitorLaunch(name="Rival", status="approved",
                                 launch_year_relative=0, peak_market_share=0.25, years_to_peak=3),
            ],
            price_pressure_factor_per_competitor=factor,
        )
        return _market(competition_model=comp)

    def test_higher_factor_lower_revenue(self):
        r_none = _total_revenue(self._model_with_pressure(0.0))
        r_lo = _total_revenue(self._model_with_pressure(0.03))
        r_hi = _total_revenue(self._model_with_pressure(0.10))
        assert r_lo < r_none
        assert r_hi < r_lo

    def test_zero_factor_no_price_pressure(self):
        mm_no_pressure = _market(competition_model=CompetitionModel(
            competitors=[
                CompetitorLaunch(name="Rival", status="approved",
                                 launch_year_relative=0, peak_market_share=0.25, years_to_peak=3),
            ],
        ))
        mm_pressure = self._model_with_pressure(0.0)
        # Both have same market fraction effect; neither has price pressure
        assert _total_revenue(mm_pressure) == pytest.approx(_total_revenue(mm_no_pressure), rel=1e-6)


# ---------------------------------------------------------------------------
# 8. COGS rate — affects gross profit but NOT revenue
# ---------------------------------------------------------------------------

class TestCOGSSensitivity:
    def test_cogs_does_not_affect_revenue(self):
        r_lo = _total_revenue(_market(cogs_rate=0.10))
        r_hi = _total_revenue(_market(cogs_rate=0.50))
        assert r_lo == pytest.approx(r_hi, rel=1e-6)

    def test_higher_cogs_lower_gross_profit(self):
        gp_lo = _total_gross_profit(_market(cogs_rate=0.10))
        gp_hi = _total_gross_profit(_market(cogs_rate=0.50))
        assert gp_hi < gp_lo

    def test_cogs_scales_gross_profit_proportionally(self):
        rev = _total_revenue(_market(cogs_rate=0.30))
        gp = _total_gross_profit(_market(cogs_rate=0.30))
        assert gp == pytest.approx(rev * (1 - 0.30), rel=1e-4)

    def test_higher_cogs_lower_ebit(self):
        e_lo = _total_ebit(_market(cogs_rate=0.10))
        e_hi = _total_ebit(_market(cogs_rate=0.50))
        assert e_hi < e_lo


# ---------------------------------------------------------------------------
# 9. SG&A rates — affect EBIT but NOT revenue or gross profit
# ---------------------------------------------------------------------------

class TestSGnASensitivity:
    def test_sgna_does_not_affect_revenue(self):
        r_lo = _total_revenue(_market(sgna_rate_launch=0.20, sgna_rate_mature=0.10))
        r_hi = _total_revenue(_market(sgna_rate_launch=0.60, sgna_rate_mature=0.40))
        assert r_lo == pytest.approx(r_hi, rel=1e-6)

    def test_sgna_does_not_affect_gross_profit(self):
        gp_lo = _total_gross_profit(_market(sgna_rate_launch=0.20, sgna_rate_mature=0.10))
        gp_hi = _total_gross_profit(_market(sgna_rate_launch=0.60, sgna_rate_mature=0.40))
        assert gp_lo == pytest.approx(gp_hi, rel=1e-6)

    def test_higher_sgna_lower_ebit(self):
        e_lo = _total_ebit(_market(sgna_rate_launch=0.20, sgna_rate_mature=0.10))
        e_hi = _total_ebit(_market(sgna_rate_launch=0.60, sgna_rate_mature=0.40))
        assert e_hi < e_lo

    def test_sgna_launch_vs_mature_affects_early_years_more(self):
        """Higher launch SG&A reduces early-year EBIT more than late-year."""
        mm_hi_launch = _market(sgna_rate_launch=0.60, sgna_rate_mature=0.20)
        mm_lo_launch = _market(sgna_rate_launch=0.20, sgna_rate_mature=0.20)
        ebit_hi = RevenueModel.compute(mm_hi_launch).ebit_by_year
        ebit_lo = RevenueModel.compute(mm_lo_launch).ebit_by_year
        # Year 1: high launch SG&A → lower early EBIT
        assert ebit_hi[0] < ebit_lo[0]
        # Mature years should converge (same mature rate)
        assert ebit_hi[-1] == pytest.approx(ebit_lo[-1], rel=1e-4)
