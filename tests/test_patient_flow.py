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
import yaml

from bve.models.commercial_inputs import (
    CommercialInputs,
    PatientPool,
    PricingModel,
    ShareModel,
)

_STEP4_COVERAGE_CONFIGS = ["relay_rly2608.yaml"] + sorted(
    f"auto_generated/{path.name}"
    for path in (Path(__file__).resolve().parents[1] / "examples" / "configs" / "auto_generated").glob("*.yaml")
)

_STEP4_REPLAY_GENERATED_CONFIGS = sorted(
    f"replay_generated/{path.name}"
    for path in (Path(__file__).resolve().parents[1] / "examples" / "configs" / "replay_generated").glob("*.yaml")
)

_STEP4_CURATED_DEFAULT_OVERRIDES = {
    "auto_generated/acad.yaml",
    "auto_generated/edit.yaml",
    "auto_generated/imvt.yaml",
    "auto_generated/rlay.yaml",
    "auto_generated/kymr.yaml",
    "auto_generated/agen.yaml",
    "auto_generated/fate.yaml",
    "auto_generated/gern.yaml",
    "auto_generated/arqt.yaml",
    "auto_generated/ptct.yaml",
    "auto_generated/fold.yaml",
    "auto_generated/sage.yaml",
    "auto_generated/ions.yaml",
    "auto_generated/rxrx.yaml",
    "auto_generated/spnv.yaml",
    "auto_generated/biib.yaml",
    "auto_generated/mdgl.yaml",
    "auto_generated/regn.yaml",
    "auto_generated/tgtx.yaml",
    "auto_generated/anab.yaml",
    "auto_generated/prax.yaml",
    "auto_generated/blue.yaml",
}

_STEP4_REPLAY_CURATED_UNDERWRITING = {
    "replay_generated/lly.yaml",
    "replay_generated/itci.yaml",
    "replay_generated/krtx.yaml",
    "replay_generated/bhvn.yaml",
    "replay_generated/rna.yaml",
    "replay_generated/myok.yaml",
    "replay_generated/immu.yaml",
    "replay_generated/xlrn.yaml",
}

_STEP4_VALIDATION_DRIVER_CURATED = {
    "replay_generated/fulc.yaml",
    "auto_generated/imvt.yaml",
    "auto_generated/mdgl.yaml",
    "auto_generated/tgtx.yaml",
}

_STEP4_CURATED_QUALITY_UPGRADES = {
    "auto_generated/anab.yaml",
    "auto_generated/imvt.yaml",
    "auto_generated/mdgl.yaml",
    "auto_generated/rxrx.yaml",
    "auto_generated/tgtx.yaml",
}


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


@pytest.mark.parametrize("relative_path", _STEP4_COVERAGE_CONFIGS)
def test_step4_coverage_configs_load_commercial_inputs(relative_path: str) -> None:
    config_path = Path(__file__).parents[1] / "examples" / "configs" / relative_path
    if not config_path.exists():
        pytest.skip(f"{relative_path} not found")

    import yaml as _yaml

    with open(config_path) as fh:
        cfg = _yaml.safe_load(fh)
    ci_cfg = cfg.get("market_model", {}).get("commercial_inputs")
    assert ci_cfg is not None, f"commercial_inputs block missing from {relative_path}"

    pricing_cfg = dict(ci_cfg["pricing"])
    if (
        "wac_per_year_usd" in pricing_cfg
        and "gross_to_net_rate" in pricing_cfg
        and "net_price_usd" not in pricing_cfg
    ):
        pricing = PricingModel.from_wac(
            wac_per_year_usd=pricing_cfg["wac_per_year_usd"],
            gross_to_net_rate=pricing_cfg["gross_to_net_rate"],
            launch_discount=pricing_cfg.get("launch_discount", 0.10),
            annual_erosion_rate=pricing_cfg.get("annual_erosion_rate", 0.02),
            uncertainty_cv=pricing_cfg.get("uncertainty_cv", 0.15),
        )
    else:
        pricing = PricingModel(**pricing_cfg)

    ci = CommercialInputs(
        patient_pool=PatientPool(**ci_cfg["patient_pool"]),
        pricing=pricing,
        share=ShareModel(**ci_cfg["share"]),
        ex_us_revenue_multiple=ci_cfg.get("ex_us_revenue_multiple", 1.0),
    )
    assert ci.to_peak_sales_millions() > 0


@pytest.mark.parametrize("relative_path", _STEP4_REPLAY_GENERATED_CONFIGS)
def test_step4_replay_generated_configs_preserve_heuristic_peak_sales(relative_path: str) -> None:
    config_path = Path(__file__).parents[1] / "examples" / "configs" / relative_path
    cfg = yaml.safe_load(config_path.read_text())
    ci_cfg = cfg["market_model"].get("commercial_inputs")
    assert ci_cfg is not None, f"commercial_inputs block missing from {relative_path}"
    pricing_cfg = dict(ci_cfg["pricing"])

    pricing = PricingModel.from_wac(
        wac_per_year_usd=pricing_cfg["wac_per_year_usd"],
        gross_to_net_rate=pricing_cfg["gross_to_net_rate"],
        launch_discount=pricing_cfg.get("launch_discount", 0.10),
        annual_erosion_rate=pricing_cfg.get("annual_erosion_rate", 0.02),
        uncertainty_cv=pricing_cfg.get("uncertainty_cv", 0.15),
    )
    ci = CommercialInputs(
        patient_pool=PatientPool(**ci_cfg["patient_pool"]),
        pricing=pricing,
        share=ShareModel(**ci_cfg["share"]),
        ex_us_revenue_multiple=ci_cfg.get("ex_us_revenue_multiple", 1.0),
    )

    assert pricing_cfg["gross_to_net_rate"] > 0.0
    patient_pool_cfg = ci_cfg["patient_pool"]
    if "addressable_k" in patient_pool_cfg:
        assert patient_pool_cfg["addressable_k"] > 0.0
    else:
        assert patient_pool_cfg["diagnosed_fraction"] > 0.0
        assert patient_pool_cfg["eligible_rate"] > 0.0
        assert patient_pool_cfg["treated_fraction"] > 0.0
    assert ci.to_peak_sales_millions() == pytest.approx(
        cfg["_meta"]["heuristic_peak_sales_millions"],
        rel=0.002,
    )


@pytest.mark.parametrize("relative_path", sorted(_STEP4_CURATED_DEFAULT_OVERRIDES))
def test_step4_priority_configs_override_mechanical_full_funnel_defaults(relative_path: str) -> None:
    cfg_path = Path(__file__).resolve().parents[1] / "examples" / "configs" / relative_path
    cfg = yaml.safe_load(cfg_path.read_text())
    patient_pool = cfg["market_model"]["commercial_inputs"]["patient_pool"]
    pricing = cfg["market_model"]["commercial_inputs"]["pricing"]

    assert patient_pool["diagnosed_fraction"] != pytest.approx(1.0)
    assert patient_pool["eligible_rate"] != pytest.approx(1.0)
    assert patient_pool["treated_fraction"] != pytest.approx(1.0)
    assert pricing["gross_to_net_rate"] > 0.0


@pytest.mark.parametrize("relative_path", sorted(_STEP4_REPLAY_CURATED_UNDERWRITING))
def test_step4_replay_curated_names_override_addressable_only_defaults(relative_path: str) -> None:
    cfg_path = Path(__file__).resolve().parents[1] / "examples" / "configs" / relative_path
    cfg = yaml.safe_load(cfg_path.read_text())
    patient_pool = cfg["market_model"]["commercial_inputs"]["patient_pool"]

    assert patient_pool["diagnosed_fraction"] != pytest.approx(1.0)
    assert patient_pool["eligible_rate"] != pytest.approx(1.0)
    assert patient_pool["treated_fraction"] != pytest.approx(1.0)
    assert patient_pool.get("addressable_k") is None


@pytest.mark.parametrize("relative_path", sorted(_STEP4_VALIDATION_DRIVER_CURATED))
def test_step4_validation_driver_names_use_explicit_nontrivial_funnels(relative_path: str) -> None:
    cfg_path = Path(__file__).resolve().parents[1] / "examples" / "configs" / relative_path
    cfg = yaml.safe_load(cfg_path.read_text())
    patient_pool = cfg["market_model"]["commercial_inputs"]["patient_pool"]
    pricing = cfg["market_model"]["commercial_inputs"]["pricing"]

    assert patient_pool["diagnosed_fraction"] != pytest.approx(1.0)
    assert patient_pool["eligible_rate"] != pytest.approx(1.0)
    assert patient_pool["treated_fraction"] != pytest.approx(1.0)
    assert pricing["gross_to_net_rate"] > 0.0


@pytest.mark.parametrize("relative_path", sorted(_STEP4_CURATED_QUALITY_UPGRADES))
def test_step4_curated_quality_upgrades_are_explicitly_labeled(relative_path: str) -> None:
    cfg_path = Path(__file__).resolve().parents[1] / "examples" / "configs" / relative_path
    cfg = yaml.safe_load(cfg_path.read_text())
    assert cfg.get("_meta", {}).get("config_quality") == "curated"


def test_step4_auto_generated_cohort_has_no_remaining_generic_defaults() -> None:
    root = Path(__file__).resolve().parents[1] / "examples" / "configs" / "auto_generated"
    remaining: list[str] = []
    for cfg_path in sorted(root.glob("*.yaml")):
        cfg = yaml.safe_load(cfg_path.read_text())
        ci_cfg = cfg["market_model"]["commercial_inputs"]
        patient_pool = ci_cfg["patient_pool"]
        pricing = ci_cfg["pricing"]
        generic = (
            patient_pool["diagnosed_fraction"] == pytest.approx(1.0)
            and patient_pool["eligible_rate"] == pytest.approx(1.0)
            and patient_pool["treated_fraction"] == pytest.approx(1.0)
            and pricing["gross_to_net_rate"] == pytest.approx(0.0)
            and ci_cfg.get("ex_us_revenue_multiple", 1.0) == pytest.approx(1.0)
        )
        if generic:
            remaining.append(cfg_path.name)

    assert remaining == []
