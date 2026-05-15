"""
Tests for P2.3 — POS Calibration: Platt-scaling logistic regression.

Verifies:
- load_oncology_dataset returns paired (raw_pos, outcomes) lists
- All raw_pos values in (0, 1), outcomes are binary {0, 1}
- fit_calibration returns CalibrationResult with expected fields
- CalibrationResult.slope, intercept are finite floats
- Brier score of calibrated <= raw (monotone improvement or tie)
- calibrate_pos maps (0, 1) → (0, 1) and is monotone
- calibrate_pos with slope=1, intercept=0 is identity (within tolerance)
- ECE metrics are non-negative
- POSCalibrationLayer convenience class: fit → calibrate workflow
- Dataset has N in expected range (≥80)
- Empirical success rate is in realistic range (~40–70%)
"""
from __future__ import annotations

import math

import pytest

from bve.models.pos_calibration import (
    CalibrationResult,
    POSCalibrationLayer,
    calibrate_pos,
    fit_calibration,
    load_oncology_dataset,
)


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

class TestLoadOncologyDataset:
    def setup_method(self):
        self.raw_pos, self.outcomes = load_oncology_dataset()

    def test_returns_equal_length_lists(self):
        assert len(self.raw_pos) == len(self.outcomes)

    def test_dataset_has_enough_samples(self):
        assert len(self.raw_pos) >= 80

    def test_raw_pos_all_in_unit_interval(self):
        for p in self.raw_pos:
            assert 0 < p < 1, f"raw_pos {p} not in (0, 1)"

    def test_outcomes_are_binary(self):
        for o in self.outcomes:
            assert o in {0, 1}, f"outcome {o} not in {{0, 1}}"

    def test_empirical_success_rate_realistic(self):
        rate = sum(self.outcomes) / len(self.outcomes)
        # Oncology phase 2/3 combined success ~40–70%
        assert 0.35 <= rate <= 0.75, f"success_rate={rate:.2f} outside expected range"

    def test_raw_pos_spread_across_range(self):
        """Model should not predict identical POS for every observation."""
        lo, hi = min(self.raw_pos), max(self.raw_pos)
        assert hi - lo > 0.05, "Raw POS has no meaningful spread"


# ---------------------------------------------------------------------------
# fit_calibration
# ---------------------------------------------------------------------------

class TestFitCalibration:
    def setup_method(self):
        self.raw_pos, self.outcomes = load_oncology_dataset()
        self.result = fit_calibration(self.raw_pos, self.outcomes)

    def test_returns_calibration_result(self):
        assert isinstance(self.result, CalibrationResult)

    def test_n_samples_matches_data(self):
        assert self.result.n_samples == len(self.raw_pos)

    def test_slope_is_finite(self):
        assert math.isfinite(self.result.slope)

    def test_intercept_is_finite(self):
        assert math.isfinite(self.result.intercept)

    def test_brier_scores_are_non_negative(self):
        assert self.result.brier_score_raw >= 0
        assert self.result.brier_score_calibrated >= 0

    def test_brier_scores_bounded_above(self):
        # Brier score ≤ 1 always
        assert self.result.brier_score_raw <= 1.0
        assert self.result.brier_score_calibrated <= 1.0

    def test_calibrated_brier_not_worse_than_raw(self):
        # Platt scaling should not increase Brier score (in-sample)
        assert self.result.brier_score_calibrated <= self.result.brier_score_raw + 1e-4

    def test_ece_metrics_non_negative(self):
        assert self.result.ece_raw >= 0
        assert self.result.ece_calibrated >= 0

    def test_mean_raw_pos_in_unit_interval(self):
        assert 0 < self.result.mean_raw_pos < 1

    def test_mean_outcome_in_unit_interval(self):
        assert 0 < self.result.mean_outcome < 1

    def test_calibration_improvement_non_negative(self):
        assert self.result.calibration_improvement >= -0.01  # tiny tolerance

    def test_net_bias_is_valid_string(self):
        assert self.result.net_bias in {"optimistic", "pessimistic", "neutral"}

    def test_confidence_flags_consistent(self):
        """Cannot be both over- and under-confident."""
        assert not (self.result.is_over_confident and self.result.is_under_confident)


# ---------------------------------------------------------------------------
# calibrate_pos
# ---------------------------------------------------------------------------

class TestCalibratePos:
    def setup_method(self):
        raw_pos, outcomes = load_oncology_dataset()
        self.result = fit_calibration(raw_pos, outcomes)

    def test_output_in_unit_interval(self):
        for raw in [0.10, 0.30, 0.50, 0.70, 0.90]:
            cal = calibrate_pos(raw, self.result)
            assert 0 < cal < 1, f"calibrate_pos({raw}) = {cal} not in (0, 1)"

    def test_monotone_increasing(self):
        """Higher raw_pos should map to higher (or equal) calibrated_pos."""
        vals = [0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.90]
        cal_vals = [calibrate_pos(p, self.result) for p in vals]
        for i in range(len(cal_vals) - 1):
            assert cal_vals[i] <= cal_vals[i + 1] + 1e-9, (
                f"Non-monotone: cal({vals[i]})={cal_vals[i]:.4f} > cal({vals[i+1]})={cal_vals[i+1]:.4f}"
            )

    def test_identity_calibration(self):
        """With slope=1 and intercept=0, calibrate_pos should be identity."""
        identity = CalibrationResult(
            n_samples=10, slope=1.0, intercept=0.0,
            brier_score_raw=0.25, brier_score_calibrated=0.25,
            ece_raw=0.05, ece_calibrated=0.05,
            mean_raw_pos=0.50, mean_outcome=0.50,
        )
        for raw in [0.20, 0.40, 0.60, 0.80]:
            cal = calibrate_pos(raw, identity)
            assert abs(cal - raw) < 1e-5, f"Identity failed: calibrate({raw})={cal}"

    def test_extreme_inputs_safe(self):
        """Values very close to 0 or 1 should not produce NaN or inf."""
        for raw in [0.001, 0.999]:
            cal = calibrate_pos(raw, self.result)
            assert math.isfinite(cal)
            assert 0 < cal < 1


# ---------------------------------------------------------------------------
# POSCalibrationLayer convenience class
# ---------------------------------------------------------------------------

class TestPOSCalibrationLayer:
    def test_not_fitted_initially(self):
        layer = POSCalibrationLayer()
        assert not layer.is_fitted

    def test_result_raises_before_fit(self):
        layer = POSCalibrationLayer()
        with pytest.raises(RuntimeError):
            _ = layer.result

    def test_fit_on_oncology_dataset_returns_result(self):
        layer = POSCalibrationLayer()
        cal = layer.fit_on_oncology_dataset()
        assert isinstance(cal, CalibrationResult)
        assert layer.is_fitted

    def test_calibrate_after_fit(self):
        layer = POSCalibrationLayer()
        layer.fit_on_oncology_dataset()
        cal = layer.calibrate(0.55)
        assert 0 < cal < 1

    def test_calibrate_raises_before_fit(self):
        layer = POSCalibrationLayer()
        with pytest.raises(RuntimeError):
            layer.calibrate(0.55)

    def test_result_same_as_fit_return(self):
        layer = POSCalibrationLayer()
        returned = layer.fit_on_oncology_dataset()
        assert layer.result is returned
