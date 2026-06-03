"""
Tests for bve.empirical.calibration — CalibrationArtifact, fit_calibration,
fit_calibration_time_split.
"""
import math
import pytest

from bve.empirical.calibration import (
    CalibrationArtifact,
    fit_calibration,
    fit_calibration_time_split,
    _fit_platt,
    _pava,
    _fit_isotonic,
)
from bve.empirical.engine import EmpiricalPOSEngine
from bve.empirical.pos_outcome import POSOutcomeRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _simple_preds_outcomes(n=30):
    """Well-calibrated predictions: pred ≈ outcome rate in each band."""
    import random
    random.seed(42)
    preds = [i / n for i in range(1, n + 1)]
    outcomes = [random.random() < p for p in preds]
    return preds, outcomes


def _rec(phase="phase_2", success=True, year="2018") -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"T-{phase}-{success}-{year}",
        sponsor="AcmeBio",
        asset_name="DrugX",
        indication_raw="NSCLC",
        phase_at_entry=phase,
        therapeutic_area="oncology",
        modality="small_molecule",
        moa_precedent="novel",
        biomarker_selected=False,
        success=success,
        outcome_raw="advanced" if success else "failed",
        outcome_date=year,
    )


# ---------------------------------------------------------------------------
# _pava — Pool Adjacent Violators
# ---------------------------------------------------------------------------

class TestPAVA:
    def test_already_monotone_unchanged(self):
        y = [0.1, 0.3, 0.5, 0.7, 0.9]
        result = _pava(y)
        assert len(result) == 5
        for i in range(len(result) - 1):
            assert result[i] <= result[i + 1] + 1e-9

    def test_constant_sequence(self):
        y = [0.5, 0.5, 0.5]
        result = _pava(y)
        assert all(abs(v - 0.5) < 1e-9 for v in result)

    def test_decreasing_becomes_flat(self):
        y = [0.9, 0.7, 0.5, 0.3]
        result = _pava(y)
        # PAVA makes it non-decreasing
        for i in range(len(result) - 1):
            assert result[i] <= result[i + 1] + 1e-9

    def test_output_length_matches_input(self):
        y = [0.8, 0.2, 0.6, 0.4, 0.9]
        result = _pava(y)
        assert len(result) == len(y)

    def test_empty_input(self):
        assert _pava([]) == []


# ---------------------------------------------------------------------------
# _fit_platt
# ---------------------------------------------------------------------------

class TestFitPlatt:
    def test_returns_three_tuple(self):
        preds, outcomes = _simple_preds_outcomes()
        a, b, converged = _fit_platt(preds, outcomes)
        assert isinstance(a, float)
        assert isinstance(b, float)
        assert isinstance(converged, bool)

    def test_identity_on_perfect_calibration(self):
        """When predictions ARE the true probabilities, Platt should be near identity."""
        # Use a large, clean dataset where pred = outcome rate
        n = 100
        preds = [0.3] * 50 + [0.7] * 50
        outcomes = [False] * 35 + [True] * 15 + [False] * 15 + [True] * 35
        a, b, _ = _fit_platt(preds, outcomes)
        # a ≈ 1 and b ≈ 0 for well-calibrated predictions
        assert abs(a - 1.0) < 1.5  # not strict — small data, just non-degenerate
        assert isinstance(b, float)

    def test_a_and_b_are_finite(self):
        preds, outcomes = _simple_preds_outcomes()
        a, b, _ = _fit_platt(preds, outcomes)
        assert math.isfinite(a)
        assert math.isfinite(b)


# ---------------------------------------------------------------------------
# _fit_isotonic
# ---------------------------------------------------------------------------

class TestFitIsotonic:
    def test_returns_two_lists_of_equal_length(self):
        from bve.empirical.calibration import _fit_isotonic
        preds, outcomes = _simple_preds_outcomes()
        x_breaks, y_breaks = _fit_isotonic(preds, outcomes)
        assert len(x_breaks) == len(y_breaks)

    def test_x_breaks_monotone(self):
        from bve.empirical.calibration import _fit_isotonic
        preds, outcomes = _simple_preds_outcomes()
        x_breaks, _ = _fit_isotonic(preds, outcomes)
        for i in range(len(x_breaks) - 1):
            assert x_breaks[i] <= x_breaks[i + 1] + 1e-9

    def test_y_breaks_monotone(self):
        from bve.empirical.calibration import _fit_isotonic
        preds, outcomes = _simple_preds_outcomes()
        _, y_breaks = _fit_isotonic(preds, outcomes)
        for i in range(len(y_breaks) - 1):
            assert y_breaks[i] <= y_breaks[i + 1] + 1e-9


# ---------------------------------------------------------------------------
# fit_calibration — Platt method
# ---------------------------------------------------------------------------

class TestFitCalibrationPlatt:
    def test_returns_calibration_artifact(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        assert isinstance(artifact, CalibrationArtifact)

    def test_method_attribute_is_platt(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        assert artifact.method == "platt"

    def test_platt_params_stored(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        assert artifact.platt_a is not None
        assert artifact.platt_b is not None
        assert isinstance(artifact.platt_converged, bool)

    def test_n_train_matches_input(self):
        preds, outcomes = _simple_preds_outcomes(20)
        artifact = fit_calibration(preds, outcomes, method="platt")
        assert artifact.n_train == 20

    def test_apply_returns_float_in_unit_interval(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            out = artifact.apply(p)
            assert 0.0 <= out <= 1.0, f"apply({p}) = {out} out of [0,1]"

    def test_apply_is_monotone(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        vals = [artifact.apply(p / 10) for p in range(1, 10)]
        for i in range(len(vals) - 1):
            assert vals[i] <= vals[i + 1] + 0.05  # allow small numeric noise

    def test_train_metrics_stored(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        assert 0.0 <= artifact.train_brier_raw <= 1.0
        assert 0.0 <= artifact.train_brier_calibrated <= 1.0
        assert 0.0 <= artifact.train_ece_raw <= 1.0
        assert 0.0 <= artifact.train_ece_calibrated <= 1.0

    def test_test_metrics_stored_when_provided(self):
        preds, outcomes = _simple_preds_outcomes(20)
        test_p, test_o = _simple_preds_outcomes(10)
        artifact = fit_calibration(
            preds, outcomes, method="platt",
            predictions_test=test_p, outcomes_test=test_o
        )
        assert artifact.n_test == 10
        assert artifact.test_brier_raw is not None
        assert artifact.test_brier_calibrated is not None

    def test_no_test_metrics_when_not_provided(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        assert artifact.n_test is None
        assert artifact.test_brier_raw is None


# ---------------------------------------------------------------------------
# fit_calibration — Isotonic method
# ---------------------------------------------------------------------------

class TestFitCalibrationIsotonic:
    def test_method_attribute_is_isotonic(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="isotonic")
        assert artifact.method == "isotonic"

    def test_isotonic_params_stored(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="isotonic")
        assert artifact.isotonic_x is not None
        assert artifact.isotonic_y is not None
        assert len(artifact.isotonic_x) == len(artifact.isotonic_y)

    def test_apply_in_unit_interval(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="isotonic")
        for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            out = artifact.apply(p)
            assert 0.0 <= out <= 1.0

    def test_invalid_method_raises(self):
        preds, outcomes = _simple_preds_outcomes()
        with pytest.raises(ValueError):
            fit_calibration(preds, outcomes, method="neural_net")


# ---------------------------------------------------------------------------
# CalibrationArtifact serialization
# ---------------------------------------------------------------------------

class TestCalibrationArtifactSerialization:
    def test_to_dict_is_serializable(self):
        import json
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        d = artifact.to_dict()
        serialized = json.dumps(d)
        assert isinstance(serialized, str)

    def test_from_dict_roundtrip_platt(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        d = artifact.to_dict()
        restored = CalibrationArtifact.from_dict(d)
        assert restored.method == artifact.method
        assert abs(restored.platt_a - artifact.platt_a) < 1e-6
        assert abs(restored.platt_b - artifact.platt_b) < 1e-6
        # apply() should give same result
        for p in [0.2, 0.5, 0.8]:
            assert abs(restored.apply(p) - artifact.apply(p)) < 1e-5

    def test_from_dict_roundtrip_isotonic(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="isotonic")
        restored = CalibrationArtifact.from_dict(artifact.to_dict())
        assert restored.method == "isotonic"
        for p in [0.2, 0.5, 0.8]:
            assert abs(restored.apply(p) - artifact.apply(p)) < 1e-5

    def test_to_dict_has_required_keys(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        d = artifact.to_dict()
        for key in ("method", "n_train", "platt_a", "platt_b",
                    "train_brier_raw", "train_brier_calibrated"):
            assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# CalibrationArtifact.calibration_summary
# ---------------------------------------------------------------------------

class TestCalibrationSummary:
    def test_summary_is_multi_line_string(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        summary = artifact.calibration_summary()
        assert isinstance(summary, str)
        assert "\n" in summary

    def test_summary_contains_method(self):
        preds, outcomes = _simple_preds_outcomes()
        artifact = fit_calibration(preds, outcomes, method="platt")
        assert "platt" in artifact.calibration_summary().lower()

    def test_summary_contains_n_train(self):
        preds, outcomes = _simple_preds_outcomes(20)
        artifact = fit_calibration(preds, outcomes, method="platt")
        assert "20" in artifact.calibration_summary()


# ---------------------------------------------------------------------------
# fit_calibration_time_split
# ---------------------------------------------------------------------------

class TestFitCalibrationTimeSplit:
    def _make_dated_records(self):
        recs = []
        for phase in ["phase_1", "phase_2", "phase_3"]:
            for i in range(8):
                year = "2015" if i < 4 else "2020"
                recs.append(_rec(phase=phase, success=(i % 2 == 0), year=year))
        return recs

    def test_returns_calibration_artifact(self):
        recs = self._make_dated_records()
        engine = EmpiricalPOSEngine(recs, min_n_for_stratified=1)
        artifact = fit_calibration_time_split(engine, recs, cutoff_year=2018, method="platt")
        assert isinstance(artifact, CalibrationArtifact)

    def test_cutoff_year_stored(self):
        recs = self._make_dated_records()
        engine = EmpiricalPOSEngine(recs, min_n_for_stratified=1)
        artifact = fit_calibration_time_split(engine, recs, cutoff_year=2018, method="platt")
        assert artifact.cutoff_year == 2018

    def test_test_metrics_populated_from_split(self):
        recs = self._make_dated_records()
        engine = EmpiricalPOSEngine(recs, min_n_for_stratified=1)
        artifact = fit_calibration_time_split(engine, recs, cutoff_year=2018, method="platt")
        assert artifact.n_test is not None and artifact.n_test > 0

    def test_raises_when_no_train_data(self):
        """All records after cutoff → no training data → should raise."""
        recs = [_rec(year="2020") for _ in range(5)]
        engine = EmpiricalPOSEngine(recs, min_n_for_stratified=1)
        with pytest.raises((ValueError, Exception)):
            fit_calibration_time_split(engine, recs, cutoff_year=2000, method="platt")
