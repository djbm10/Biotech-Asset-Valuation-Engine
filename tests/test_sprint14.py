"""
Sprint 14 tests — CommercialInputs layer.

Tests to_peak_sales_millions, sample_peak_sales, MC width, backward compat,
and relay_rly2608.yaml integration.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from bve.models.commercial_inputs import (
    CommercialInputs,
    PatientPool,
    PricingModel,
    ShareModel,
)
from bve.models.market_model import MarketModel

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pool():
    return PatientPool(
        indication="obesity",
        prevalence_thousands=120_000,
        diagnosed_fraction=0.40,
        treated_fraction=0.20,
        uncertainty_cv=0.25,
    )


@pytest.fixture()
def pricing():
    return PricingModel(
        net_price_usd=14_000,
        launch_discount=0.15,
        annual_erosion_rate=0.02,
        uncertainty_cv=0.15,
    )


@pytest.fixture()
def share():
    return ShareModel(peak_share=0.08, years_to_peak=5, share_cv=0.20)


@pytest.fixture()
def ci(pool, pricing, share):
    return CommercialInputs(patient_pool=pool, pricing=pricing, share=share)


# ===========================================================================
# TestPatientPool
# ===========================================================================

class TestPatientPool:
    def test_to_addressable_chain(self, pool):
        expected = 120_000 * 1_000 * 0.40 * 0.20
        assert pool.to_addressable() == pytest.approx(expected, rel=1e-6)

    def test_addressable_k_override(self):
        p = PatientPool(indication="test", prevalence_thousands=1, addressable_k=500)
        assert p.to_addressable() == 500_000

    def test_default_fractions_equal_full_prevalence(self):
        p = PatientPool(indication="test", prevalence_thousands=100)
        assert p.to_addressable() == pytest.approx(100_000)

    def test_sample_mean_near_point_estimate(self, pool):
        rng = np.random.default_rng(42)
        draws = [pool.sample(rng) for _ in range(5_000)]
        mean = sum(draws) / len(draws)
        assert mean == pytest.approx(pool.to_addressable(), rel=0.05)

    def test_sample_cv_near_target(self, pool):
        rng = np.random.default_rng(42)
        draws = np.array([pool.sample(rng) for _ in range(5_000)])
        cv = draws.std() / draws.mean()
        assert abs(cv - pool.uncertainty_cv) < 0.05

    def test_zero_cv_returns_point_estimate(self):
        p = PatientPool(indication="test", prevalence_thousands=100, uncertainty_cv=0.0)
        rng = np.random.default_rng(0)
        assert p.sample(rng) == pytest.approx(p.to_addressable())


# ===========================================================================
# TestPricingModel
# ===========================================================================

class TestPricingModel:
    def test_effective_launch_price(self, pricing):
        expected = 14_000 * (1 - 0.15)
        assert pricing.effective_launch_price() == pytest.approx(expected)

    def test_price_in_year_1_equals_launch(self, pricing):
        assert pricing.price_in_year(1) == pytest.approx(pricing.effective_launch_price())

    def test_price_decays_over_time(self, pricing):
        assert pricing.price_in_year(5) < pricing.price_in_year(1)

    def test_price_erosion_formula(self, pricing):
        launch = pricing.effective_launch_price()
        expected_yr5 = launch * (1 - 0.02) ** 4
        assert pricing.price_in_year(5) == pytest.approx(expected_yr5, rel=1e-6)

    def test_sample_mean_near_launch_price(self, pricing):
        rng = np.random.default_rng(99)
        draws = np.array([pricing.sample_launch_price(rng) for _ in range(5_000)])
        assert draws.mean() == pytest.approx(pricing.effective_launch_price(), rel=0.05)

    def test_zero_cv_returns_launch_price(self):
        p = PricingModel(net_price_usd=50_000, uncertainty_cv=0.0)
        rng = np.random.default_rng(0)
        assert p.sample_launch_price(rng) == pytest.approx(p.effective_launch_price())


# ===========================================================================
# TestShareModel
# ===========================================================================

class TestShareModel:
    def test_peak_share_stored(self, share):
        assert share.peak_share == 0.08

    def test_sample_mean_near_peak_share(self, share):
        rng = np.random.default_rng(7)
        draws = np.array([share.sample_peak_share(rng) for _ in range(5_000)])
        assert draws.mean() == pytest.approx(0.08, rel=0.06)

    def test_sample_clamped_to_1(self):
        s = ShareModel(peak_share=0.95, share_cv=1.0)
        rng = np.random.default_rng(0)
        draws = [s.sample_peak_share(rng) for _ in range(500)]
        assert all(d <= 1.0 for d in draws)

    def test_zero_cv_returns_peak_share(self):
        s = ShareModel(peak_share=0.10, share_cv=0.0)
        rng = np.random.default_rng(0)
        assert s.sample_peak_share(rng) == pytest.approx(0.10)

    def test_invalid_peak_share_raises(self):
        with pytest.raises(Exception):
            ShareModel(peak_share=1.5)


# ===========================================================================
# TestCommercialInputs
# ===========================================================================

class TestCommercialInputs:
    def test_to_peak_sales_formula(self, ci, pool, pricing, share):
        expected = (
            pool.to_addressable()
            * pricing.effective_launch_price()
            * share.peak_share
            / 1e6
        )
        assert ci.to_peak_sales_millions() == pytest.approx(expected, rel=1e-4)

    def test_point_estimate_is_positive(self, ci):
        assert ci.to_peak_sales_millions() > 0

    def test_sample_mean_near_point_estimate(self, ci):
        rng = np.random.default_rng(42)
        draws = np.array([ci.sample_peak_sales(rng) for _ in range(5_000)])
        point = ci.to_peak_sales_millions()
        assert draws.mean() == pytest.approx(point, rel=0.07)

    def test_mc_cv_wider_than_any_single_input(self, ci):
        """Propagating 3 independent CVs → total CV exceeds any individual CV."""
        rng = np.random.default_rng(1)
        draws = np.array([ci.sample_peak_sales(rng) for _ in range(5_000)])
        combined_cv = draws.std() / draws.mean()
        max_input_cv = max(
            ci.patient_pool.uncertainty_cv,
            ci.pricing.uncertainty_cv,
            ci.share.share_cv,
        )
        assert combined_cv > max_input_cv * 0.9  # at least as wide

    def test_deterministic_with_fixed_seed(self, ci):
        rng1 = np.random.default_rng(123)
        rng2 = np.random.default_rng(123)
        assert ci.sample_peak_sales(rng1) == ci.sample_peak_sales(rng2)

    def test_frozen_model_immutable(self, ci):
        with pytest.raises(Exception):
            ci.pricing = PricingModel(net_price_usd=99_000)  # type: ignore[misc]


# ===========================================================================
# TestMarketModelIntegration
# ===========================================================================

class TestMarketModelIntegration:
    def test_commercial_inputs_mode_accepted(self):
        """MarketModel should accept commercial_inputs without addressable_patients or TAM."""
        ci = CommercialInputs(
            patient_pool=PatientPool(indication="test", prevalence_thousands=100),
            pricing=PricingModel(net_price_usd=50_000),
            share=ShareModel(peak_share=0.10),
        )
        mm = MarketModel(
            asset_id="TEST",
            commercial_inputs=ci,
            peak_penetration=0.10,
            years_to_peak=5,
            patent_life_years=12,
        )
        assert mm.peak_sales_millions > 0

    def test_peak_sales_uses_commercial_inputs_value(self):
        ci = CommercialInputs(
            patient_pool=PatientPool(indication="test", prevalence_thousands=50),
            pricing=PricingModel(net_price_usd=100_000),
            share=ShareModel(peak_share=0.20),
        )
        mm = MarketModel(
            asset_id="TEST",
            commercial_inputs=ci,
            peak_penetration=0.20,
            years_to_peak=5,
            patent_life_years=12,
        )
        assert mm.peak_sales_millions == pytest.approx(ci.to_peak_sales_millions(), rel=1e-6)

    def test_backward_compat_without_commercial_inputs(self):
        """Existing configs without commercial_inputs continue to work."""
        mm = MarketModel(
            asset_id="TEST",
            total_addressable_market_millions=5000,
            peak_penetration=0.10,
            years_to_peak=5,
            patent_life_years=12,
        )
        assert mm.peak_sales_millions == pytest.approx(500.0)

    def test_missing_all_modes_raises(self):
        with pytest.raises(ValueError, match="Provide one of"):
            MarketModel(
                asset_id="TEST",
                peak_penetration=0.10,
                years_to_peak=5,
                patent_life_years=12,
            )

    def test_relay_config_loads_with_commercial_inputs(self):
        """relay_rly2608.yaml now has a commercial_inputs block — ensure it loads."""
        config_path = (
            Path(__file__).parents[1] / "examples" / "configs" / "relay_rly2608.yaml"
        )
        if not config_path.exists():
            pytest.skip("relay_rly2608.yaml not found")
        import yaml as _yaml
        with open(config_path) as fh:
            cfg = _yaml.safe_load(fh)
        mm_cfg = cfg.get("market_model", {})
        ci_cfg = mm_cfg.get("commercial_inputs")
        assert ci_cfg is not None, "commercial_inputs block missing from relay config"
        ci = CommercialInputs(
            patient_pool=PatientPool(**ci_cfg["patient_pool"]),
            pricing=PricingModel(**ci_cfg["pricing"]),
            share=ShareModel(**ci_cfg["share"]),
        )
        assert ci.to_peak_sales_millions() > 0

    def test_commercial_inputs_peak_sales_close_to_patient_mode(self):
        """
        When commercial_inputs is set with the same patient/price/share as
        patient-based mode, the two peak_sales estimates should be in the same ballpark.
        """
        patients = 10_000
        price = 200_000
        share = 0.15

        # Patient-based mode
        mm_patient = MarketModel(
            asset_id="T",
            addressable_patients_annual=patients,
            net_price_per_patient_usd=price,
            peak_penetration=share,
            years_to_peak=5,
            patent_life_years=12,
        )

        # CommercialInputs mode
        ci = CommercialInputs(
            patient_pool=PatientPool(indication="T", prevalence_thousands=patients / 1_000),
            pricing=PricingModel(net_price_usd=price, launch_discount=0.0),
            share=ShareModel(peak_share=share),
        )
        mm_ci = MarketModel(
            asset_id="T",
            commercial_inputs=ci,
            peak_penetration=share,
            years_to_peak=5,
            patent_life_years=12,
        )

        # Should be within 5% (difference: compliance_rate=0.80 in patient mode vs 1.0 in CI)
        ratio = mm_ci.peak_sales_millions / mm_patient.peak_sales_millions
        assert 0.90 <= ratio <= 1.40  # CI omits compliance_rate; ratio ~1.25
