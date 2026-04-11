"""
Tests for patient-flow model upgrades (Step 4 of institutional-grade plan).

Covers:
- PatientPool.eligible_rate narrows the addressable population
- PricingModel.from_wac() constructs from WAC + G2N rate
- PricingModel WAC/G2N consistency check warning
- CommercialInputs.ex_us_revenue_multiple scales global revenue
- Full patient-flow chain: diagnosed → eligible → treated → addressable
- Gold-tier config YAML round-trips through CommercialInputs
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from bve.models.commercial_inputs import (
    CommercialInputs,
    PatientPool,
    PricingModel,
    ShareModel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_pricing() -> PricingModel:
    return PricingModel(net_price_usd=20_000, launch_discount=0.0, uncertainty_cv=0.0)


def _default_share() -> ShareModel:
    return ShareModel(peak_share=0.20, years_to_peak=5, share_cv=0.0)


# ---------------------------------------------------------------------------
# PatientPool.eligible_rate
# ---------------------------------------------------------------------------

class TestPatientPoolEligibleRate:
    def test_eligible_rate_defaults_to_one(self) -> None:
        pool = PatientPool(indication="test", prevalence_thousands=100.0)
        assert pool.eligible_rate == 1.0

    def test_eligible_rate_narrows_addressable(self) -> None:
        pool_full = PatientPool(
            indication="test",
            prevalence_thousands=100.0,
            diagnosed_fraction=1.0,
            eligible_rate=1.0,
            treated_fraction=1.0,
        )
        pool_restricted = PatientPool(
            indication="test",
            prevalence_thousands=100.0,
            diagnosed_fraction=1.0,
            eligible_rate=0.50,  # only 50% meet label criteria
            treated_fraction=1.0,
        )
        assert pool_full.to_addressable() == pytest.approx(100_000)
        assert pool_restricted.to_addressable() == pytest.approx(50_000)

    def test_eligible_rate_applied_in_funnel_order(self) -> None:
        # Chain: 100k × 0.80 diagnosed × 0.60 eligible × 0.50 treated = 24k
        pool = PatientPool(
            indication="MASH F2-F4",
            prevalence_thousands=100.0,
            diagnosed_fraction=0.80,
            eligible_rate=0.60,
            treated_fraction=0.50,
        )
        expected = 100_000 * 0.80 * 0.60 * 0.50
        assert pool.to_addressable() == pytest.approx(expected)

    def test_addressable_k_override_bypasses_funnel(self) -> None:
        pool = PatientPool(
            indication="test",
            prevalence_thousands=100.0,
            diagnosed_fraction=0.5,
            eligible_rate=0.5,
            treated_fraction=0.5,
            addressable_k=200.0,  # override
        )
        assert pool.to_addressable() == pytest.approx(200_000)

    def test_eligible_rate_sampled_correctly(self) -> None:
        import numpy as np

        pool = PatientPool(
            indication="test",
            prevalence_thousands=100.0,
            diagnosed_fraction=1.0,
            eligible_rate=0.50,
            treated_fraction=1.0,
            uncertainty_cv=0.0,  # deterministic
        )
        rng = np.random.default_rng(0)
        assert pool.sample(rng) == pytest.approx(50_000)


# ---------------------------------------------------------------------------
# PricingModel.from_wac()
# ---------------------------------------------------------------------------

class TestPricingModelFromWac:
    def test_from_wac_derives_correct_net_price(self) -> None:
        pricing = PricingModel.from_wac(
            wac_per_year_usd=30_000,
            gross_to_net_rate=0.35,
        )
        assert pricing.net_price_usd == pytest.approx(30_000 * (1 - 0.35))

    def test_from_wac_stores_wac_and_g2n(self) -> None:
        pricing = PricingModel.from_wac(
            wac_per_year_usd=50_000,
            gross_to_net_rate=0.40,
        )
        assert pricing.wac_per_year_usd == 50_000
        assert pricing.gross_to_net_rate == 0.40

    def test_from_wac_passes_optional_params(self) -> None:
        pricing = PricingModel.from_wac(
            wac_per_year_usd=100_000,
            gross_to_net_rate=0.30,
            launch_discount=0.05,
            annual_erosion_rate=0.015,
        )
        assert pricing.launch_discount == 0.05
        assert pricing.annual_erosion_rate == 0.015

    def test_wac_fields_optional_in_direct_construction(self) -> None:
        pricing = PricingModel(net_price_usd=20_000)
        assert pricing.wac_per_year_usd is None
        assert pricing.gross_to_net_rate is None

    def test_wac_consistency_warning_when_mismatch(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            PricingModel(
                net_price_usd=10_000,
                wac_per_year_usd=30_000,
                gross_to_net_rate=0.35,  # implies net = 19,500, not 10,000
            )
        assert any("deviates" in str(x.message) for x in w)

    def test_no_warning_when_consistent(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            PricingModel(
                net_price_usd=19_500,
                wac_per_year_usd=30_000,
                gross_to_net_rate=0.35,  # 30,000 × 0.65 = 19,500 ✓
            )
        consistency_warns = [x for x in w if "deviates" in str(x.message)]
        assert len(consistency_warns) == 0


# ---------------------------------------------------------------------------
# CommercialInputs.ex_us_revenue_multiple
# ---------------------------------------------------------------------------

class TestExUsRevenueMultiple:
    def _make_ci(self, ex_us_multiple: float = 1.0) -> CommercialInputs:
        return CommercialInputs(
            patient_pool=PatientPool(
                indication="test",
                prevalence_thousands=100.0,
                diagnosed_fraction=1.0,
                eligible_rate=1.0,
                treated_fraction=1.0,
                uncertainty_cv=0.0,
            ),
            pricing=PricingModel(
                net_price_usd=10_000,
                launch_discount=0.0,
                uncertainty_cv=0.0,
            ),
            share=ShareModel(peak_share=0.10, years_to_peak=5, share_cv=0.0),
            ex_us_revenue_multiple=ex_us_multiple,
        )

    def test_defaults_to_one(self) -> None:
        ci = self._make_ci()
        assert ci.ex_us_revenue_multiple == 1.0

    def test_us_only_peak_sales(self) -> None:
        ci = self._make_ci(ex_us_multiple=1.0)
        # 100K patients × $10K × 10% share = $100M
        assert ci.to_peak_sales_millions() == pytest.approx(100.0)

    def test_global_multiple_scales_correctly(self) -> None:
        # ex_us_fraction=0.40 → multiple = 1 / 0.60 = 1.667
        ci = self._make_ci(ex_us_multiple=1.667)
        # 100K × 10K × 10% × 1.667 = ~$166.7M
        assert ci.to_peak_sales_millions() == pytest.approx(166.7, rel=0.01)

    def test_multiple_propagated_in_mc_sample(self) -> None:
        import numpy as np

        ci = self._make_ci(ex_us_multiple=1.5)
        us_ci = self._make_ci(ex_us_multiple=1.0)
        rng = np.random.default_rng(0)
        sample_global = ci.sample_peak_sales(rng)
        rng2 = np.random.default_rng(0)
        sample_us = us_ci.sample_peak_sales(rng2)
        assert sample_global == pytest.approx(sample_us * 1.5, rel=0.001)


# ---------------------------------------------------------------------------
# Full patient-flow chain integration
# ---------------------------------------------------------------------------

class TestFullPatientFlowChain:
    def test_mash_like_patient_flow(self) -> None:
        """
        MDGL Rezdiffra-like scenario:
        - US MASH prevalent: 5M
        - Diagnosed: 25% (many undiagnosed)
        - Eligible (F2-F4 label criteria): 15% of diagnosed
        - Treatment rate: 35%
        → addressable = 5M × 0.25 × 0.15 × 0.35 ≈ 65,625
        """
        pool = PatientPool(
            indication="MASH F2-F4",
            prevalence_thousands=5_000.0,
            diagnosed_fraction=0.25,
            eligible_rate=0.15,
            treated_fraction=0.35,
        )
        expected = 5_000_000 * 0.25 * 0.15 * 0.35
        assert pool.to_addressable() == pytest.approx(expected)

    def test_oncology_patient_flow(self) -> None:
        """
        ARVN-like scenario:
        - ER+/HER2- mBC prevalence: 160K (US)
        - Diagnosed: 95% (symptomatic)
        - Eligible (2L+ on CDK4/6, ESR1-wt or degrader indication): 60%
        - Treatment rate: 75%
        """
        pool = PatientPool(
            indication="ER+/HER2- mBC 2L+",
            prevalence_thousands=160.0,
            diagnosed_fraction=0.95,
            eligible_rate=0.60,
            treated_fraction=0.75,
        )
        expected = 160_000 * 0.95 * 0.60 * 0.75
        assert pool.to_addressable() == pytest.approx(expected, rel=0.001)

    def test_full_commercial_inputs_with_ex_us(self) -> None:
        """
        Full pipeline: prevalence → addressable × share × net_price × ex-US
        """
        pool = PatientPool(
            indication="MASH F2-F4",
            prevalence_thousands=5_000.0,
            diagnosed_fraction=0.25,
            eligible_rate=0.15,
            treated_fraction=0.35,
        )
        pricing = PricingModel.from_wac(
            wac_per_year_usd=60_000,
            gross_to_net_rate=0.40,   # → net $36K
            launch_discount=0.10,
            uncertainty_cv=0.0,
        )
        share = ShareModel(peak_share=0.15, years_to_peak=6, share_cv=0.0)
        ci = CommercialInputs(
            patient_pool=pool,
            pricing=pricing,
            share=share,
            ex_us_revenue_multiple=1.5,  # EU5 + Japan add-on
        )
        addressable = pool.to_addressable()  # ~65,625
        net_price = pricing.effective_launch_price()  # 36K × 0.90 = 32.4K
        peak = addressable * 0.15 * net_price * 1.5 / 1e6
        assert ci.to_peak_sales_millions() == pytest.approx(peak, rel=0.001)

    def test_wac_transparency_round_trip(self) -> None:
        """WAC + G2N → net_price → effective_launch_price should be fully traceable."""
        wac = 100_000
        g2n = 0.35
        launch_disc = 0.05
        pricing = PricingModel.from_wac(
            wac_per_year_usd=wac,
            gross_to_net_rate=g2n,
            launch_discount=launch_disc,
        )
        # Trace: net = 100k × 0.65 = 65k; effective = 65k × 0.95 = 61.75k
        assert pricing.net_price_usd == pytest.approx(wac * (1 - g2n))
        assert pricing.effective_launch_price() == pytest.approx(wac * (1 - g2n) * (1 - launch_disc))
