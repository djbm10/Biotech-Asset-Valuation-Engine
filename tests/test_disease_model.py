"""
Sprint B1 tests — disease_model support in PatientPool / CommercialInputs.

Test coverage:
  1. Backward compat — prevalent (default) behavior is bit-for-bit unchanged
  2. incident_chronic — addressable = incidence × funnel × duration
  3. incident_one_time — Year 1 = backlog + incident; Year 2+ = incident only
  4. Validation — missing annual_incidence_k raises clear error
  5. Validation — prevalent without prevalence_thousands or addressable_k raises error
  6. Duration resolution — months → years, years direct, default 1.0
  7. MC sampling — to_addressable() determines the distribution mean
  8. CommercialInputs — to_peak_sales_millions / to_ongoing_sales_millions
  9. Oncology incident vs prevalent — different revenue sizing
 10. Gene therapy one-time — Year 1 front-loading vs Year 2+
 11. Backlog_years scaling
 12. Frozen model — immutability
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from bve.models.commercial_inputs import (
    CommercialInputs,
    PatientPool,
    PricingModel,
    ShareModel,
)


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _pricing(net_price: float = 100_000.0) -> PricingModel:
    return PricingModel(net_price_usd=net_price, launch_discount=0.0, annual_erosion_rate=0.0, uncertainty_cv=0.0)


def _share(peak: float = 0.10) -> ShareModel:
    return ShareModel(peak_share=peak, share_cv=0.0)


def _ci(pool: PatientPool, net_price: float = 100_000.0, peak: float = 0.10) -> CommercialInputs:
    return CommercialInputs(patient_pool=pool, pricing=_pricing(net_price), share=_share(peak))


# ===========================================================================
# 1. Backward compatibility — prevalent behavior unchanged
# ===========================================================================

class TestPrevalentBackwardCompat:
    def test_default_disease_model_is_prevalent(self):
        pool = PatientPool(
            indication="hf",
            prevalence_thousands=6_000,
        )
        assert pool.disease_model == "prevalent"

    def test_prevalent_to_addressable_with_full_funnel(self):
        """to_addressable() matches original funnel formula."""
        pool = PatientPool(
            indication="hf",
            prevalence_thousands=6_000,
            diagnosed_fraction=0.60,
            eligible_rate=0.70,
            treated_fraction=0.80,
        )
        expected = 6_000 * 1_000 * 0.60 * 0.70 * 0.80
        assert pool.to_addressable() == pytest.approx(expected)

    def test_prevalent_addressable_k_bypass(self):
        pool = PatientPool(indication="x", prevalence_thousands=10_000, addressable_k=50.0)
        assert pool.to_addressable() == pytest.approx(50_000.0)

    def test_prevalent_to_addressable_ongoing_equals_to_addressable(self):
        pool = PatientPool(indication="x", prevalence_thousands=10_000)
        assert pool.to_addressable_ongoing() == pytest.approx(pool.to_addressable())

    def test_prevalent_to_addressable_in_year_constant(self):
        pool = PatientPool(indication="x", prevalence_thousands=5_000)
        base = pool.to_addressable()
        for yr in (1, 2, 5, 10):
            assert pool.to_addressable_in_year(yr) == pytest.approx(base)

    def test_prevalent_peak_sales_unchanged(self):
        """to_peak_sales_millions output identical to Sprint 14 formula."""
        pool = PatientPool(indication="obesity", prevalence_thousands=120_000, diagnosed_fraction=0.40, treated_fraction=0.20)
        pricing = PricingModel(net_price_usd=14_000, launch_discount=0.15, annual_erosion_rate=0.02, uncertainty_cv=0.15)
        share = ShareModel(peak_share=0.08)
        ci = CommercialInputs(patient_pool=pool, pricing=pricing, share=share)

        addressable = pool.to_addressable()
        price = pricing.effective_launch_price()
        expected = round(addressable * price * 0.08 / 1e6, 2)
        assert ci.to_peak_sales_millions() == pytest.approx(expected)

    def test_prevalent_without_prevalence_raises(self):
        with pytest.raises(ValueError, match="prevalence_thousands or addressable_k"):
            PatientPool(indication="x")

    def test_prevalent_with_addressable_k_no_prevalence_ok(self):
        pool = PatientPool(indication="x", addressable_k=100.0)
        assert pool.to_addressable() == pytest.approx(100_000.0)


# ===========================================================================
# 2. incident_chronic
# ===========================================================================

class TestIncidentChronic:
    def _pool(
        self,
        annual_incidence_k: float = 10.0,
        duration_years: float | None = None,
        duration_months: float | None = None,
        diagnosed_fraction: float = 1.0,
        eligible_rate: float = 1.0,
        treated_fraction: float = 1.0,
    ) -> PatientPool:
        return PatientPool(
            indication="oncology",
            disease_model="incident_chronic",
            annual_incidence_k=annual_incidence_k,
            duration_on_therapy_years=duration_years,
            duration_on_therapy_months=duration_months,
            diagnosed_fraction=diagnosed_fraction,
            eligible_rate=eligible_rate,
            treated_fraction=treated_fraction,
        )

    def test_basic_formula(self):
        """addressable = incidence × 1000 × funnel × duration."""
        pool = self._pool(annual_incidence_k=10.0, duration_years=2.0)
        expected = 10_000 * 1.0 * 1.0 * 1.0 * 2.0
        assert pool.to_addressable() == pytest.approx(expected)

    def test_funnel_applied(self):
        pool = self._pool(
            annual_incidence_k=20.0,
            duration_years=1.5,
            diagnosed_fraction=0.80,
            eligible_rate=0.60,
            treated_fraction=0.70,
        )
        expected = 20_000 * 0.80 * 0.60 * 0.70 * 1.5
        assert pool.to_addressable() == pytest.approx(expected)

    def test_duration_months_converted(self):
        """duration_on_therapy_months=18 → 1.5 years."""
        pool = self._pool(annual_incidence_k=10.0, duration_months=18.0)
        expected = 10_000 * 1.5
        assert pool.to_addressable() == pytest.approx(expected)

    def test_duration_default_is_one_year(self):
        """No duration set → defaults to 1.0 year."""
        pool = PatientPool(
            indication="oncology",
            disease_model="incident_chronic",
            annual_incidence_k=10.0,
        )
        assert pool._resolved_duration_years == pytest.approx(1.0)
        assert pool.to_addressable() == pytest.approx(10_000.0)

    def test_addressable_k_bypasses_incidence_funnel(self):
        pool = PatientPool(
            indication="oncology",
            disease_model="incident_chronic",
            annual_incidence_k=10.0,
            addressable_k=5.0,  # explicit override
        )
        assert pool.to_addressable() == pytest.approx(5_000.0)

    def test_to_addressable_ongoing_equals_to_addressable(self):
        pool = self._pool(annual_incidence_k=10.0, duration_years=2.0)
        assert pool.to_addressable_ongoing() == pytest.approx(pool.to_addressable())

    def test_to_addressable_in_year_constant(self):
        pool = self._pool(annual_incidence_k=10.0, duration_years=2.0)
        base = pool.to_addressable()
        for yr in (1, 2, 5):
            assert pool.to_addressable_in_year(yr) == pytest.approx(base)

    def test_missing_annual_incidence_raises(self):
        with pytest.raises(ValueError, match="annual_incidence_k"):
            PatientPool(indication="oncology", disease_model="incident_chronic")

    def test_both_duration_fields_raises(self):
        with pytest.raises(ValueError):
            PatientPool(
                indication="x",
                disease_model="incident_chronic",
                annual_incidence_k=5.0,
                duration_on_therapy_months=12.0,
                duration_on_therapy_years=1.0,
            )

    def test_commercial_inputs_peak_sales(self):
        pool = self._pool(annual_incidence_k=8.0, duration_years=2.0)
        ci = _ci(pool, net_price=200_000.0, peak=0.20)
        addressable = pool.to_addressable()
        price = ci.pricing.effective_launch_price()
        expected = round(addressable * price * 0.20 / 1e6, 2)
        assert ci.to_peak_sales_millions() == pytest.approx(expected)


# ===========================================================================
# 3. incident_one_time
# ===========================================================================

class TestIncidentOneTime:
    def _pool(
        self,
        annual_incidence_k: float = 5.0,
        prevalence_thousands: float | None = 100.0,
        backlog_years: float = 1.0,
        diagnosed_fraction: float = 1.0,
        eligible_rate: float = 1.0,
        treated_fraction: float = 1.0,
    ) -> PatientPool:
        return PatientPool(
            indication="gene_therapy",
            disease_model="incident_one_time",
            annual_incidence_k=annual_incidence_k,
            prevalence_thousands=prevalence_thousands,
            backlog_years=backlog_years,
            diagnosed_fraction=diagnosed_fraction,
            eligible_rate=eligible_rate,
            treated_fraction=treated_fraction,
        )

    def test_year1_includes_backlog_plus_incident(self):
        """Year 1: prevalent_eligible × backlog_years + annual_incident_eligible."""
        pool = self._pool(annual_incidence_k=2.0, prevalence_thousands=50.0)
        backlog = 50_000 * 1.0  # backlog_years=1.0
        annual = 2_000
        assert pool.to_addressable() == pytest.approx(backlog + annual)

    def test_to_addressable_ongoing_is_annual_incident_only(self):
        """Year 2+: only annual_incidence_k × funnel (no backlog)."""
        pool = self._pool(annual_incidence_k=3.0, prevalence_thousands=80.0)
        assert pool.to_addressable_ongoing() == pytest.approx(3_000.0)

    def test_to_addressable_in_year_1_with_backlog(self):
        pool = self._pool(annual_incidence_k=2.0, prevalence_thousands=50.0)
        assert pool.to_addressable_in_year(1) == pytest.approx(pool.to_addressable())

    def test_to_addressable_in_year_2plus_is_ongoing(self):
        pool = self._pool(annual_incidence_k=2.0, prevalence_thousands=50.0)
        ongoing = pool.to_addressable_ongoing()
        for yr in (2, 3, 5, 10):
            assert pool.to_addressable_in_year(yr) == pytest.approx(ongoing)

    def test_year1_greater_than_year2(self):
        """Year 1 (backlog + incident) > Year 2+ (incident only)."""
        pool = self._pool(annual_incidence_k=2.0, prevalence_thousands=50.0)
        assert pool.to_addressable_in_year(1) > pool.to_addressable_in_year(2)

    def test_backlog_years_scales_backlog(self):
        """backlog_years=2 → double the backlog in Year 1."""
        pool1 = self._pool(annual_incidence_k=2.0, prevalence_thousands=50.0, backlog_years=1.0)
        pool2 = self._pool(annual_incidence_k=2.0, prevalence_thousands=50.0, backlog_years=2.0)
        diff = pool2.to_addressable() - pool1.to_addressable()
        assert diff == pytest.approx(50_000.0)  # one extra year of backlog

    def test_no_prevalent_pool_year1_equals_annual_incident(self):
        """Without prevalence_thousands, Year 1 = annual incident only."""
        pool = PatientPool(
            indication="gene_therapy",
            disease_model="incident_one_time",
            annual_incidence_k=3.0,
            # no prevalence_thousands
        )
        assert pool.to_addressable() == pytest.approx(3_000.0)

    def test_funnel_applied_to_both_backlog_and_incident(self):
        pool = PatientPool(
            indication="gt",
            disease_model="incident_one_time",
            annual_incidence_k=4.0,
            prevalence_thousands=100.0,
            diagnosed_fraction=0.80,
            eligible_rate=0.50,
            treated_fraction=0.60,
            backlog_years=1.0,
        )
        prevalent_eligible = 100_000 * 0.80 * 0.50 * 0.60
        annual_incident = 4_000 * 0.80 * 0.50 * 0.60
        assert pool.to_addressable() == pytest.approx(prevalent_eligible + annual_incident)
        assert pool.to_addressable_ongoing() == pytest.approx(annual_incident)

    def test_missing_annual_incidence_raises(self):
        with pytest.raises(ValueError, match="annual_incidence_k"):
            PatientPool(
                indication="gt",
                disease_model="incident_one_time",
                prevalence_thousands=100.0,
            )

    def test_commercial_inputs_peak_vs_ongoing(self):
        pool = self._pool(annual_incidence_k=2.0, prevalence_thousands=50.0)
        ci = _ci(pool, net_price=2_000_000.0, peak=0.50)
        assert ci.to_peak_sales_millions() > ci.to_ongoing_sales_millions()

    def test_ongoing_sales_matches_annual_incident_math(self):
        pool = self._pool(annual_incidence_k=2.0, prevalence_thousands=50.0)
        ci = _ci(pool, net_price=2_000_000.0, peak=0.50)
        price = ci.pricing.effective_launch_price()
        expected = round(2_000 * price * 0.50 / 1e6, 2)
        assert ci.to_ongoing_sales_millions() == pytest.approx(expected)


# ===========================================================================
# 4. Validation — missing annual_incidence_k
# ===========================================================================

class TestValidation:
    def test_incident_chronic_without_incidence_raises_clear_error(self):
        with pytest.raises(ValueError, match="annual_incidence_k"):
            PatientPool(
                indication="nsclc",
                disease_model="incident_chronic",
                # annual_incidence_k not set
            )

    def test_incident_one_time_without_incidence_raises_clear_error(self):
        with pytest.raises(ValueError, match="annual_incidence_k"):
            PatientPool(
                indication="sma",
                disease_model="incident_one_time",
                prevalence_thousands=20.0,
                # annual_incidence_k not set
            )

    def test_prevalent_without_size_fields_raises(self):
        with pytest.raises(ValueError, match="prevalence_thousands or addressable_k"):
            PatientPool(indication="x", disease_model="prevalent")

    def test_invalid_disease_model_raises(self):
        with pytest.raises(Exception):
            PatientPool(
                indication="x",
                prevalence_thousands=100.0,
                disease_model="continuous_infusion",  # type: ignore[arg-type]
            )


# ===========================================================================
# 5. Duration resolution
# ===========================================================================

class TestDurationResolution:
    def test_duration_years_direct(self):
        pool = PatientPool(
            indication="x", disease_model="incident_chronic",
            annual_incidence_k=5.0, duration_on_therapy_years=3.0,
        )
        assert pool._resolved_duration_years == pytest.approx(3.0)

    def test_duration_months_converts(self):
        pool = PatientPool(
            indication="x", disease_model="incident_chronic",
            annual_incidence_k=5.0, duration_on_therapy_months=24.0,
        )
        assert pool._resolved_duration_years == pytest.approx(2.0)

    def test_duration_default_one_year(self):
        pool = PatientPool(
            indication="x", disease_model="incident_chronic",
            annual_incidence_k=5.0,
        )
        assert pool._resolved_duration_years == pytest.approx(1.0)

    def test_duration_ignored_for_prevalent(self):
        pool = PatientPool(
            indication="x",
            prevalence_thousands=100.0,
            duration_on_therapy_years=2.0,  # allowed but not used
        )
        # prevalent still uses prevalence funnel
        assert pool.to_addressable() == pytest.approx(100_000.0)


# ===========================================================================
# 6. MC sampling
# ===========================================================================

class TestMCSampling:
    def test_prevalent_sample_mean_close_to_addressable(self):
        pool = PatientPool(indication="x", prevalence_thousands=100.0, uncertainty_cv=0.25)
        rng = np.random.default_rng(42)
        samples = [pool.sample(rng) for _ in range(5000)]
        assert abs(sum(samples) / len(samples) - pool.to_addressable()) / pool.to_addressable() < 0.05

    def test_incident_chronic_sample_mean_close_to_addressable(self):
        pool = PatientPool(
            indication="nsclc",
            disease_model="incident_chronic",
            annual_incidence_k=10.0,
            duration_on_therapy_years=2.0,
            uncertainty_cv=0.20,
        )
        rng = np.random.default_rng(99)
        samples = [pool.sample(rng) for _ in range(5000)]
        assert abs(sum(samples) / len(samples) - pool.to_addressable()) / pool.to_addressable() < 0.05

    def test_incident_one_time_sample_reflects_year1_peak(self):
        """sample() returns Year 1 (peak) counts for incident_one_time."""
        pool = PatientPool(
            indication="gt",
            disease_model="incident_one_time",
            annual_incidence_k=1.0,
            prevalence_thousands=50.0,
            uncertainty_cv=0.0,  # deterministic
        )
        rng = np.random.default_rng(1)
        sample = pool.sample(rng)
        assert sample == pytest.approx(pool.to_addressable())  # Year 1 value


# ===========================================================================
# 7. Oncology incident vs prevalent — different revenue sizing
# ===========================================================================

class TestOncologyIncidentVsPrevalent:
    def test_incident_chronic_sizes_differently_than_prevalent(self):
        """
        For a cancer with 200k prevalent and 80k incident annually (3mo median tx):
        - prevalent model: 200k × funnel = large pool (including long survivors)
        - incident_chronic: 80k × 0.25yr = much smaller steady-state pool on active tx
        These reflect genuinely different economic realities.
        """
        # NSCLC: 250k prevalent, 240k incident, median 1L duration ~6mo
        prevalent_pool = PatientPool(
            indication="nsclc_prevalent",
            prevalence_thousands=250.0,
            diagnosed_fraction=0.90,
            eligible_rate=0.40,
            treated_fraction=0.80,
        )
        incident_pool = PatientPool(
            indication="nsclc_incident",
            disease_model="incident_chronic",
            annual_incidence_k=240.0,
            diagnosed_fraction=0.90,
            eligible_rate=0.40,
            treated_fraction=0.80,
            duration_on_therapy_months=6.0,  # 6 months median PFS
        )
        # They should differ (incident × 0.5yr << prevalent because survivors accumulate)
        assert prevalent_pool.to_addressable() != incident_pool.to_addressable()

        # The incident chronic model gives the economically correct steady-state
        # (patients actually being treated at any moment), not the full survivor pool.
        expected_incident = 240_000 * 0.90 * 0.40 * 0.80 * 0.5
        assert incident_pool.to_addressable() == pytest.approx(expected_incident)

    def test_commercial_inputs_incident_vs_prevalent_peak_sales_differ(self):
        prevalent_pool = PatientPool(
            indication="prevalent", prevalence_thousands=100.0,
        )
        incident_pool = PatientPool(
            indication="incident",
            disease_model="incident_chronic",
            annual_incidence_k=20.0,
            duration_on_therapy_years=1.0,
        )
        ci_prev = _ci(prevalent_pool, net_price=50_000.0, peak=0.15)
        ci_inc = _ci(incident_pool, net_price=50_000.0, peak=0.15)
        # They should produce different peak sales (different addressable bases)
        assert ci_prev.to_peak_sales_millions() != ci_inc.to_peak_sales_millions()


# ===========================================================================
# 8. Gene therapy one-time — front-loading
# ===========================================================================

class TestGenetherapyOnetime:
    def test_year1_revenue_greater_than_year2(self):
        """Gene therapy: Year 1 (backlog + incident) >> Year 2+ (incident only)."""
        pool = PatientPool(
            indication="sma",
            disease_model="incident_one_time",
            annual_incidence_k=0.8,       # ~800 new SMA births/yr
            prevalence_thousands=25.0,    # ~25k living with SMA at launch
            diagnosed_fraction=0.85,
            eligible_rate=0.70,
            treated_fraction=0.60,
        )
        year1 = pool.to_addressable_in_year(1)
        year2 = pool.to_addressable_in_year(2)
        assert year1 > year2

    def test_gene_therapy_backlog_dominates_year1(self):
        """
        For a large prevalent pool relative to incidence, Year 1 >> Year 2+ by ≥ 5×.
        """
        pool = PatientPool(
            indication="sma",
            disease_model="incident_one_time",
            annual_incidence_k=0.8,
            prevalence_thousands=50.0,   # large prevalent backlog
        )
        year1 = pool.to_addressable_in_year(1)
        year2plus = pool.to_addressable_in_year(2)
        assert year1 / year2plus >= 5.0

    def test_peak_sales_reflects_year1_backlog_premium(self):
        """to_peak_sales_millions() > to_ongoing_sales_millions() for gene therapy."""
        pool = PatientPool(
            indication="sma",
            disease_model="incident_one_time",
            annual_incidence_k=1.0,
            prevalence_thousands=30.0,
        )
        ci = CommercialInputs(
            patient_pool=pool,
            pricing=PricingModel(net_price_usd=2_000_000, launch_discount=0.0, annual_erosion_rate=0.0, uncertainty_cv=0.0),
            share=ShareModel(peak_share=0.50, share_cv=0.0),
        )
        assert ci.to_peak_sales_millions() > ci.to_ongoing_sales_millions()

    def test_gene_therapy_ongoing_matches_incident_math(self):
        """Ongoing sales = annual_incidence × funnel × share × price."""
        pool = PatientPool(
            indication="sma",
            disease_model="incident_one_time",
            annual_incidence_k=1.0,        # 1000/yr
            prevalence_thousands=30.0,
            diagnosed_fraction=0.90,
            eligible_rate=0.80,
        )
        pricing = PricingModel(net_price_usd=2_000_000, launch_discount=0.0, annual_erosion_rate=0.0, uncertainty_cv=0.0)
        share = ShareModel(peak_share=0.60, share_cv=0.0)
        ci = CommercialInputs(patient_pool=pool, pricing=pricing, share=share)

        annual_eligible = 1_000 * 0.90 * 0.80  # 720/yr
        expected_ongoing = round(annual_eligible * 2_000_000 * 0.60 / 1e6, 2)
        assert ci.to_ongoing_sales_millions() == pytest.approx(expected_ongoing)


# ===========================================================================
# 9. Frozen model (immutability)
# ===========================================================================

class TestFrozen:
    def test_patient_pool_is_frozen(self):
        pool = PatientPool(indication="x", prevalence_thousands=100.0)
        with pytest.raises(Exception):
            pool.disease_model = "incident_chronic"  # type: ignore[misc]

    def test_commercial_inputs_is_frozen(self):
        pool = PatientPool(indication="x", prevalence_thousands=100.0)
        ci = _ci(pool)
        with pytest.raises(Exception):
            ci.ex_us_revenue_multiple = 2.0  # type: ignore[misc]
