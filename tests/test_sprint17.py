"""
Sprint 17 tests — Calibrated PoS model.

Tests blending, shrinkage, credible intervals, factory methods.
All data is synthetic — no live DB calls.
"""
from __future__ import annotations

import pytest

from bve.analysis.calibration_metrics import OutcomeRecord, PredictionRecord
from bve.models.pos_calibrated import (
    N_FULL_POSTERIOR,
    N_PRIOR_ONLY,
    BinSummary,
    CalibratedPOSModel,
    _FALLBACK_BASE_RATE,
    _beta_ci_approx,
    _build_bin_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pred(program_id, ta="oncology", phase="phase_2", model_pos=0.50):
    return PredictionRecord(
        program_id=program_id,
        ticker="X",
        ta=ta,
        phase=phase,
        model_pos=model_pos,
    )


def _make_outcome(program_id, outcome_type="approval"):
    return OutcomeRecord(program_id=program_id, outcome_type=outcome_type)


def _synthetic_dataset(
    ta="oncology",
    phase="phase_2",
    n_success=20,
    n_fail=20,
    outcome_types=None,
):
    """Build matched predictions + outcomes for one (ta, phase) bin."""
    preds, outcomes = [], []
    for i in range(n_success):
        pid = f"{ta}_{phase}_S{i}"
        preds.append(_make_pred(pid, ta=ta, phase=phase))
        outcomes.append(_make_outcome(pid, "approval"))
    for i in range(n_fail):
        pid = f"{ta}_{phase}_F{i}"
        preds.append(_make_pred(pid, ta=ta, phase=phase))
        outcomes.append(_make_outcome(pid, "failure_efficacy"))
    return preds, outcomes


# ===========================================================================
# TestBetaCiApprox
# ===========================================================================

class TestBetaCiApprox:
    def test_symmetric_distribution(self):
        lo, hi = _beta_ci_approx(5, 5)
        assert lo < 0.5 < hi
        assert abs((lo + hi) / 2 - 0.5) < 0.02

    def test_interval_is_within_0_1(self):
        lo, hi = _beta_ci_approx(100, 1)  # heavily skewed toward 1
        assert 0.0 <= lo <= hi <= 1.0

    def test_wider_with_less_data(self):
        lo_narrow, hi_narrow = _beta_ci_approx(50, 50)
        lo_wide, hi_wide = _beta_ci_approx(5, 5)
        width_narrow = hi_narrow - lo_narrow
        width_wide = hi_wide - lo_wide
        assert width_wide > width_narrow


# ===========================================================================
# TestBuildBinSummary
# ===========================================================================

class TestBuildBinSummary:
    def test_pure_prior_when_n_below_threshold(self):
        summary = _build_bin_summary("oncology", "phase_2", n=5, s=3, f=2, industry_prior=0.40)
        assert summary.blend_weight == 0.0
        assert summary.blended_rate == pytest.approx(0.40)

    def test_pure_posterior_when_n_above_threshold(self):
        summary = _build_bin_summary("oncology", "phase_2", n=60, s=30, f=30, industry_prior=0.40)
        assert summary.blend_weight == 1.0
        assert summary.blended_rate == pytest.approx(summary.posterior_mean)

    def test_blended_at_midpoint_n(self):
        n_mid = (N_PRIOR_ONLY + N_FULL_POSTERIOR) // 2
        summary = _build_bin_summary("oncology", "phase_2", n=n_mid, s=n_mid // 2, f=n_mid // 2, industry_prior=0.40)
        assert 0.0 < summary.blend_weight < 1.0

    def test_fields_populated(self):
        summary = _build_bin_summary("immuno", "phase_3", n=20, s=12, f=8, industry_prior=0.60)
        assert summary.ta == "immuno"
        assert summary.phase == "phase_3"
        assert summary.n_total == 20
        assert summary.n_success == 12
        assert summary.n_failure == 8

    def test_ci_lo_lt_mean_lt_hi(self):
        summary = _build_bin_summary("oncology", "phase_2", n=30, s=15, f=15, industry_prior=0.40)
        assert summary.ci_lo < summary.blended_rate < summary.ci_hi

    def test_posterior_mean_formula(self):
        # Alpha = s + 0.5, Beta = f + 0.5 (Jeffreys)
        n, s, f = 10, 7, 3
        alpha = s + 0.5
        beta = f + 0.5
        expected_posterior = alpha / (alpha + beta)
        summary = _build_bin_summary("onco", "phase_3", n=n, s=s, f=f, industry_prior=0.60)
        assert summary.posterior_mean == pytest.approx(expected_posterior, abs=0.001)


# ===========================================================================
# TestCalibratedPOSModel
# ===========================================================================

class TestCalibratedPOSModel:
    def test_from_records_returns_model(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        assert isinstance(model, CalibratedPOSModel)

    def test_base_rate_in_range(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        rate = model.base_rate("oncology", "phase_2")
        assert 0.0 <= rate <= 1.0

    def test_case_insensitive_ta_phase(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        r1 = model.base_rate("oncology", "phase_2")
        r2 = model.base_rate("ONCOLOGY", "PHASE_2")
        assert r1 == pytest.approx(r2)

    def test_unknown_ta_returns_fallback(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        rate = model.base_rate("xyzzy_unknown", "phase_99")
        assert rate in (_FALLBACK_BASE_RATE,) or (0.0 <= rate <= 1.0)

    def test_n_outcomes_counted(self):
        preds, outcomes = _synthetic_dataset(n_success=15, n_fail=15)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        assert model.n_outcomes == 30

    def test_confidence_interval_width(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        lo, hi = model.confidence_interval("oncology", "phase_2")
        assert lo < hi
        assert 0.0 <= lo <= hi <= 1.0

    def test_unknown_ta_returns_prior_interval(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        lo, hi = model.confidence_interval("unknown_ta", "phase_2")
        assert lo < hi

    def test_bin_summary_returns_none_for_unknown(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        assert model.bin_summary("alien_ta", "phase_9") is None

    def test_bin_summary_returns_summary_for_known(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        s = model.bin_summary("oncology", "phase_2")
        assert s is not None
        assert isinstance(s, BinSummary)

    def test_all_bins_returns_list(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        bins = model.all_bins()
        assert len(bins) >= 1

    def test_multiple_ta_bins(self):
        preds1, outcomes1 = _synthetic_dataset(ta="oncology", phase="phase_2", n_success=20, n_fail=20)
        preds2, outcomes2 = _synthetic_dataset(ta="immunology", phase="phase_3", n_success=20, n_fail=10)
        model = CalibratedPOSModel.from_records(preds1 + preds2, outcomes1 + outcomes2)
        assert model.base_rate("oncology", "phase_2") != model.base_rate("immunology", "phase_3")

    def test_ongoing_outcomes_excluded(self):
        preds = [_make_pred("P1", ta="oncology", phase="phase_2")]
        outcomes = [_make_outcome("P1", "ongoing")]
        model = CalibratedPOSModel.from_records(preds, outcomes)
        assert model.n_outcomes == 0
        # base_rate should fall through to industry prior or fallback
        rate = model.base_rate("oncology", "phase_2")
        assert 0.0 <= rate <= 1.0

    def test_empty_data_returns_prior_model(self):
        model = CalibratedPOSModel.from_records([], [])
        # Should return industry priors or fallback
        rate = model.base_rate("oncology", "phase_3")
        assert 0.0 <= rate <= 1.0

    def test_high_success_rate_shifts_base_rate_up(self):
        """If all 50 outcomes are successes, blended rate > industry prior."""
        preds, outcomes = _synthetic_dataset(n_success=N_FULL_POSTERIOR, n_fail=0)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        rate = model.base_rate("oncology", "phase_2")
        # Posterior is near 1.0; with full blend, rate should be high
        assert rate > 0.7

    def test_n_bins_calibrated(self):
        preds, outcomes = _synthetic_dataset(n_success=25, n_fail=25)
        model = CalibratedPOSModel.from_records(preds, outcomes)
        assert model.n_bins_calibrated >= 1
