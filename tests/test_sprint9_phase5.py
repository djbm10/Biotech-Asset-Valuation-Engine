"""
Sprint 9 Phase 5 — Monte Carlo distribution improvements (Task 9.19).

Verifies:
- Stage-conditional peak_sales_cv selection
- Phase 1 MC width > Phase 3 MC width (at least 1.5x)
- Updated ESS values per stage
- WACC-to-peak-sales correlation present in DEFAULT_CORRELATION
- peak_sales_cv_used exposed on MonteCarloResult
- Explicit override respected (not replaced by stage lookup)
"""
from __future__ import annotations

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.config.constants import MC_PEAK_SALES_CV, MC_PEAK_SALES_CV_BY_STAGE, MC_PHASE_ESS
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.models.correlations import DEFAULT_CORRELATION
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import (
    MonteCarloParams,
    _resolve_peak_sales_cv,
    run_monte_carlo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_asset(stage: DevelopmentStage) -> Asset:
    return Asset(
        id=f"test-{stage.value}",
        name=f"TEST-{stage.value}",
        indication="Oncology",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=stage,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.12,
    )


def _make_market() -> MarketModel:
    return MarketModel(
        asset_id="test-asset",
        total_addressable_market_millions=2_000.0,
        peak_penetration=0.10,
        years_to_peak=5,
        patent_life_years=12,
        use_s_curve=True,
    )


def _make_trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            id="t1",
            asset_id="test-asset",
            phase=TrialPhase.PHASE_2,
            success_probability=0.40,
            duration_years=3,
            cost_millions=80.0,
            primary_endpoint_type=EndpointType.HARD_CLINICAL,
        ),
        ClinicalTrial(
            id="t2",
            asset_id="test-asset",
            phase=TrialPhase.PHASE_3,
            success_probability=0.65,
            duration_years=4,
            cost_millions=250.0,
            primary_endpoint_type=EndpointType.HARD_CLINICAL,
        ),
    ]


# ---------------------------------------------------------------------------
# YAML / loader tests
# ---------------------------------------------------------------------------

class TestStageConditionalCVConfig:
    def test_by_stage_table_present_in_yaml(self):
        a = AssumptionsLoader.get()
        table = a.mc_peak_sales_cv_by_stage
        assert isinstance(table, dict)
        assert len(table) >= 6

    def test_stage_values_in_expected_ranges(self):
        a = AssumptionsLoader.get()
        table = a.mc_peak_sales_cv_by_stage
        # Earlier stages must have wider CV than later stages
        assert table["phase_1"] > table["phase_3"]
        assert table["phase_3"] > table["approved"]
        assert table["preclinical"] >= table["phase_1"]

    def test_all_expected_stages_present(self):
        table = MC_PEAK_SALES_CV_BY_STAGE
        for stage in ("preclinical", "phase_1", "phase_2", "phase_3", "nda_bla", "approved"):
            assert stage in table, f"Missing stage: {stage}"

    def test_fallback_default_key_present(self):
        assert "default" in MC_PEAK_SALES_CV_BY_STAGE

    def test_flat_fallback_cv_unchanged(self):
        """The flat MC_PEAK_SALES_CV sentinel must remain 0.35."""
        assert MC_PEAK_SALES_CV == pytest.approx(0.35)


class TestUpdatedESSValues:
    def test_phase_1_ess_is_20(self):
        assert MC_PHASE_ESS["phase_1"] == 20

    def test_phase_2_ess_is_25(self):
        assert MC_PHASE_ESS["phase_2"] == 25

    def test_phase_3_ess_is_25(self):
        assert MC_PHASE_ESS["phase_3"] == 25

    def test_nda_bla_ess_is_45(self):
        assert MC_PHASE_ESS["nda_bla"] == 45

    def test_phase_3_ess_ge_phase_1_ess(self):
        """Phase 3 prior should be at least as tight as Phase 1."""
        assert MC_PHASE_ESS["phase_3"] >= MC_PHASE_ESS["phase_1"]

    def test_nda_bla_ess_ge_phase_3_ess(self):
        assert MC_PHASE_ESS["nda_bla"] >= MC_PHASE_ESS["phase_3"]


# ---------------------------------------------------------------------------
# _resolve_peak_sales_cv unit tests
# ---------------------------------------------------------------------------

class TestResolvePeakSalesCV:
    def test_phase_1_uses_wider_cv(self):
        asset = _make_asset(DevelopmentStage.PHASE_1)
        cv = _resolve_peak_sales_cv(asset, MonteCarloParams())
        assert cv == pytest.approx(MC_PEAK_SALES_CV_BY_STAGE["phase_1"])
        assert cv > MC_PEAK_SALES_CV  # wider than the flat default

    def test_phase_3_uses_narrower_cv(self):
        asset = _make_asset(DevelopmentStage.PHASE_3)
        cv = _resolve_peak_sales_cv(asset, MonteCarloParams())
        assert cv == pytest.approx(MC_PEAK_SALES_CV_BY_STAGE["phase_3"])
        assert cv < MC_PEAK_SALES_CV  # narrower than the flat default

    def test_phase_2_uses_intermediate_cv(self):
        asset = _make_asset(DevelopmentStage.PHASE_2)
        cv = _resolve_peak_sales_cv(asset, MonteCarloParams())
        assert cv == pytest.approx(MC_PEAK_SALES_CV_BY_STAGE["phase_2"])

    def test_approved_uses_tightest_cv(self):
        asset = _make_asset(DevelopmentStage.APPROVED)
        cv = _resolve_peak_sales_cv(asset, MonteCarloParams())
        assert cv == pytest.approx(MC_PEAK_SALES_CV_BY_STAGE["approved"])
        assert cv < MC_PEAK_SALES_CV_BY_STAGE["phase_3"]

    def test_explicit_override_respected(self):
        """When params.peak_sales_cv != default, stage lookup is skipped."""
        asset = _make_asset(DevelopmentStage.PHASE_1)
        params = MonteCarloParams(peak_sales_cv=0.20)  # explicit narrow override
        cv = _resolve_peak_sales_cv(asset, params)
        assert cv == pytest.approx(0.20)
        # Not the stage-conditional Phase 1 value
        assert cv != pytest.approx(MC_PEAK_SALES_CV_BY_STAGE["phase_1"])

    def test_phase_1_cv_wider_than_phase_3_cv(self):
        p1_cv = _resolve_peak_sales_cv(_make_asset(DevelopmentStage.PHASE_1), MonteCarloParams())
        p3_cv = _resolve_peak_sales_cv(_make_asset(DevelopmentStage.PHASE_3), MonteCarloParams())
        assert p1_cv > p3_cv


# ---------------------------------------------------------------------------
# DEFAULT_CORRELATION tests
# ---------------------------------------------------------------------------

class TestDefaultCorrelation:
    def test_peak_sales_discount_rate_negative(self):
        """WACC-to-peak-sales correlation should be negative."""
        found = False
        for a, b, rho in DEFAULT_CORRELATION.pairs:
            if {a, b} == {"peak_sales", "discount_rate"}:
                assert rho < 0, "peak_sales/discount_rate correlation should be negative"
                found = True
        assert found, "peak_sales/discount_rate pair not found in DEFAULT_CORRELATION"

    def test_correlation_matrix_is_positive_definite(self):
        """Cholesky should succeed without fallback for the default spec."""
        import numpy as np
        mat = DEFAULT_CORRELATION.build_matrix()
        eigvals = np.linalg.eigvalsh(mat)
        assert all(e > 0 for e in eigvals), "Correlation matrix is not positive-definite"


# ---------------------------------------------------------------------------
# run_monte_carlo integration tests
# ---------------------------------------------------------------------------

class TestMCWidthByStage:
    """Phase 1 MC P5-P95 width must be at least 1.5x the Phase 3 width."""

    def _run(self, stage: DevelopmentStage, n: int = 2_000) -> tuple[float, float, float]:
        asset = Asset(
            id="mc-test",
            name="MC Test",
            indication="Oncology",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=stage,
            modality=Modality.SMALL_MOLECULE,
            discount_rate=0.12,
        )
        market = MarketModel(
            asset_id="mc-test",
            total_addressable_market_millions=2_000.0,
            peak_penetration=0.10,
            years_to_peak=5,
            patent_life_years=12,
            use_s_curve=True,
        )
        trials = [
            ClinicalTrial(
                id="t1", asset_id="mc-test",
                phase=TrialPhase.PHASE_2,
                success_probability=0.40, duration_years=3,
                cost_millions=80.0,
                primary_endpoint_type=EndpointType.HARD_CLINICAL,
            ),
            ClinicalTrial(
                id="t2", asset_id="mc-test",
                phase=TrialPhase.PHASE_3,
                success_probability=0.65, duration_years=4,
                cost_millions=250.0,
                primary_endpoint_type=EndpointType.HARD_CLINICAL,
            ),
        ]
        params = MonteCarloParams(n_simulations=n, random_seed=42)
        result = run_monte_carlo(asset, trials, market, params)
        width = result.percentile_95_millions - result.percentile_5_millions
        return result.peak_sales_cv_used, width, result.std_millions

    def test_phase_1_cv_used_is_wider_than_phase_3(self):
        cv1, _, _ = self._run(DevelopmentStage.PHASE_1)
        cv3, _, _ = self._run(DevelopmentStage.PHASE_3)
        assert cv1 > cv3

    def test_phase_1_width_at_least_1_5x_phase_3(self):
        _, w1, _ = self._run(DevelopmentStage.PHASE_1)
        _, w3, _ = self._run(DevelopmentStage.PHASE_3)
        assert w1 >= 1.5 * w3, f"Phase 1 width ({w1:.0f}) not 1.5x Phase 3 width ({w3:.0f})"

    def test_peak_sales_cv_used_on_result(self):
        asset = _make_asset(DevelopmentStage.PHASE_2)
        trials = _make_trials()
        market = _make_market()
        market = market.model_copy(update={"asset_id": asset.id})
        params = MonteCarloParams(n_simulations=200, random_seed=1)
        result = run_monte_carlo(asset, trials, market, params)
        assert result.peak_sales_cv_used == pytest.approx(
            MC_PEAK_SALES_CV_BY_STAGE["phase_2"]
        )

    def test_explicit_cv_override_propagated_to_result(self):
        asset = _make_asset(DevelopmentStage.PHASE_1)
        trials = _make_trials()
        market = _make_market()
        market = market.model_copy(update={"asset_id": asset.id})
        params = MonteCarloParams(n_simulations=200, random_seed=1, peak_sales_cv=0.20)
        result = run_monte_carlo(asset, trials, market, params)
        assert result.peak_sales_cv_used == pytest.approx(0.20)
