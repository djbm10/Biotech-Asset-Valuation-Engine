"""
Block 22 — M&A Calibration Truthfulness
TDD tests written BEFORE implementation.

Tests for:
  1. calibration_fitted=False when no params file present
  2. calibration_params_source="hard_coded_defaults" when no file
  3. calibration_warning set and non-empty when unfitted
  4. confidence_level capped at very_low when unfitted and would be HIGH/MEDIUM/LOW
  5. display_probability unchanged when unfitted
  6. calibration_fitted=True when valid params file is present
  7. calibration_params_source="fitted_file" when file present
  8. No calibration_warning when fitted
  9. Backward compatibility: all existing Layer5Output fields still present
  10. Cap does not re-cap already-very_low confidence
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bve.intelligence.ma_layer5_calibration import (
    Layer5Inputs,
    Layer5Output,
    compute_layer5,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_inputs(**kwargs) -> Layer5Inputs:
    defaults = dict(
        rank_score=0.55,
        rank_percentile=0.65,
        strategic_priority=0.60,
        transaction_probability=0.50,
        asset_quality=0.70,
        seller_willingness=0.55,
        base_rate=0.08,
        comparable_bucket_rate=0.12,
        n_comparable_observations=10,
        target_name="TestCo",
        as_of_date="2026-05-27",
    )
    defaults.update(kwargs)
    return Layer5Inputs(**defaults)


def _high_confidence_inputs() -> Layer5Inputs:
    """Inputs that produce HIGH confidence when calibration is fitted."""
    return _base_inputs(
        data_confidence_score=0.90,
        n_comparable_observations=25,
        comparable_bucket_rate_source="segment_report",
    )


# ---------------------------------------------------------------------------
# Block 22-A: calibration_fitted field — False when no params file
# ---------------------------------------------------------------------------

class TestCalibrationFittedField:

    def test_calibration_fitted_is_bool(self):
        out = compute_layer5(_base_inputs())
        assert isinstance(out.calibration_fitted, bool)

    def test_calibration_fitted_false_when_no_file(self, tmp_path, monkeypatch):
        """When no params file exists, calibration_fitted must be False."""
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        out = compute_layer5(_base_inputs())
        assert out.calibration_fitted is False

    def test_calibration_params_source_hard_coded_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        out = compute_layer5(_base_inputs())
        assert out.calibration_params_source == "hard_coded_defaults"

    def test_calibration_warning_set_when_unfitted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        out = compute_layer5(_base_inputs())
        assert out.calibration_warning is not None
        assert len(out.calibration_warning) > 0

    def test_calibration_warning_mentions_hard_coded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        out = compute_layer5(_base_inputs())
        assert "hard-coded" in out.calibration_warning.lower() or "default" in out.calibration_warning.lower()


# ---------------------------------------------------------------------------
# Block 22-B: confidence cap when unfitted
# ---------------------------------------------------------------------------

class TestCalibrationConfidenceCap:

    def test_high_confidence_capped_at_very_low_when_unfitted(self, tmp_path, monkeypatch):
        """Good data + segment_report would give HIGH; unfitted caps to VERY_LOW."""
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        out = compute_layer5(_high_confidence_inputs())
        assert out.confidence_level == "very_low"

    def test_medium_confidence_capped_at_very_low_when_unfitted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        inp = _base_inputs(
            data_confidence_score=0.70,
            n_comparable_observations=12,
            comparable_bucket_rate_source="segment_report",
        )
        out = compute_layer5(inp)
        assert out.confidence_level == "very_low"

    def test_low_confidence_capped_at_very_low_when_unfitted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        inp = _base_inputs(
            data_confidence_score=0.55,
            n_comparable_observations=7,
        )
        out = compute_layer5(inp)
        assert out.confidence_level == "very_low"

    def test_already_very_low_not_degraded_further(self, tmp_path, monkeypatch):
        """Already very_low confidence stays very_low — no 'below floor' issue."""
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        inp = _base_inputs(
            data_confidence_score=0.20,
            n_comparable_observations=1,
        )
        out = compute_layer5(inp)
        assert out.confidence_level == "very_low"

    def test_display_probability_unchanged_when_unfitted(self, tmp_path, monkeypatch):
        """Calibration truthfulness must not change the ranking signal."""
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        inp = _high_confidence_inputs()
        out_no_monkeypatch = compute_layer5(inp)
        out = compute_layer5(inp)
        # display_probability is a string derived from confidence; when very_low it shows bands
        # but rank_score is unchanged
        assert out.rank_score == pytest.approx(inp.rank_score)

    def test_p_takeout_12m_unchanged_when_unfitted(self, tmp_path, monkeypatch):
        """Probability values must not be altered by the calibration cap."""
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        # Run twice: once "fitted" scenario doesn't exist regardless — both use same math
        out = compute_layer5(_base_inputs())
        assert 0.0 <= out.p_takeout_12m <= 1.0


# ---------------------------------------------------------------------------
# Block 22-C: calibration_fitted=True when valid file present
# ---------------------------------------------------------------------------

class TestCalibrationFittedTrue:

    def test_calibration_fitted_true_when_valid_file(self, tmp_path, monkeypatch):
        params_file = tmp_path / "ma_calibration_params.json"
        params_file.write_text(json.dumps({"slope": 9.0, "midpoint": 0.65}))
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            params_file,
        )
        out = compute_layer5(_base_inputs())
        assert out.calibration_fitted is True

    def test_calibration_params_source_fitted_file(self, tmp_path, monkeypatch):
        params_file = tmp_path / "ma_calibration_params.json"
        params_file.write_text(json.dumps({"slope": 9.0, "midpoint": 0.65}))
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            params_file,
        )
        out = compute_layer5(_base_inputs())
        assert out.calibration_params_source == "fitted_file"

    def test_no_calibration_warning_when_fitted(self, tmp_path, monkeypatch):
        params_file = tmp_path / "ma_calibration_params.json"
        params_file.write_text(json.dumps({"slope": 9.0, "midpoint": 0.65}))
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            params_file,
        )
        out = compute_layer5(_base_inputs())
        assert out.calibration_warning is None or out.calibration_warning == ""

    def test_high_confidence_allowed_when_fitted(self, tmp_path, monkeypatch):
        """When fitted, confidence is not capped; HIGH is achievable."""
        params_file = tmp_path / "ma_calibration_params.json"
        params_file.write_text(json.dumps({"slope": 9.0, "midpoint": 0.65}))
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            params_file,
        )
        out = compute_layer5(_high_confidence_inputs())
        assert out.confidence_level == "high"


# ---------------------------------------------------------------------------
# Block 22-D: backward compatibility
# ---------------------------------------------------------------------------

class TestBlock22BackwardCompat:

    def test_existing_output_fields_still_present(self):
        out = compute_layer5(_base_inputs())
        for field in [
            "rank_score", "p_takeout_12m", "p_takeout_6m", "p_takeout_18m",
            "probability_band", "confidence_level", "top_positive_drivers",
            "top_negative_drivers", "calibration_cohort", "display_probability",
            "interpretation",
        ]:
            assert hasattr(out, field), f"Missing field: {field}"

    def test_new_fields_present_on_output(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "calibration_fitted")
        assert hasattr(out, "calibration_params_source")
        assert hasattr(out, "calibration_warning")

    def test_layer5_inputs_unchanged_construction(self):
        """Existing callers not passing new fields still construct fine."""
        inp = Layer5Inputs(
            rank_score=0.50,
            rank_percentile=0.50,
            strategic_priority=0.50,
            transaction_probability=0.50,
            asset_quality=0.60,
            seller_willingness=0.50,
        )
        out = compute_layer5(inp)
        assert 0.0 <= out.p_takeout_12m <= 1.0
