"""
Block 26 — M&A Probability Architecture
TDD tests written BEFORE implementation.

Tests for ProbabilitySource enum and _source fields on Layer5Output:

  p_any_source:               CALIBRATED when calibration_fitted=True, FALLBACK otherwise
  p_full_acquisition_source:  always DERIVED (fraction × calibrated parent)
  p_license_or_partner_source: always DERIVED
  p_takeout_6m_source:        always DERIVED (time-scaled from p_any)
  p_takeout_18m_source:       always DERIVED

Depends on Block 22 (calibration_fitted field already on Layer5Output).
"""
from __future__ import annotations

import json

import pytest

from bve.intelligence.ma_layer5_calibration import (
    Layer5Inputs,
    Layer5Output,
    ProbabilitySource,
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


def _fitted_inputs(tmp_path, monkeypatch, **kwargs) -> Layer5Inputs:
    """Return inputs with monkeypatched fitted calibration file."""
    params_file = tmp_path / "ma_calibration_params.json"
    params_file.write_text(json.dumps({"slope": 8.0, "midpoint": 0.68}))
    monkeypatch.setattr(
        "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
        params_file,
    )
    return _base_inputs(**kwargs)


# ---------------------------------------------------------------------------
# Block 26-A: ProbabilitySource enum
# ---------------------------------------------------------------------------

class TestProbabilitySourceEnum:

    def test_four_source_values(self):
        assert ProbabilitySource.CALIBRATED.value == "calibrated"
        assert ProbabilitySource.DERIVED.value == "derived"
        assert ProbabilitySource.FALLBACK.value == "fallback"
        assert ProbabilitySource.RANK_ONLY.value == "rank_only"

    def test_calibrated_when_fitted(self, tmp_path, monkeypatch):
        inp = _fitted_inputs(tmp_path, monkeypatch)
        out = compute_layer5(inp)
        assert out.p_any_source == ProbabilitySource.CALIBRATED

    def test_fallback_when_unfitted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        out = compute_layer5(_base_inputs())
        assert out.p_any_source == ProbabilitySource.FALLBACK


# ---------------------------------------------------------------------------
# Block 26-B: Source fields present on Layer5Output
# ---------------------------------------------------------------------------

class TestProbabilitySourceFields:

    def test_p_any_source_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "p_any_source")
        assert isinstance(out.p_any_source, ProbabilitySource)

    def test_p_full_acquisition_source_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "p_full_acquisition_source")
        assert isinstance(out.p_full_acquisition_source, ProbabilitySource)

    def test_p_license_or_partner_source_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "p_license_or_partner_source")

    def test_p_takeout_6m_source_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "p_takeout_6m_source")

    def test_p_takeout_18m_source_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "p_takeout_18m_source")

    def test_p_full_acquisition_always_derived(self):
        out = compute_layer5(_base_inputs())
        assert out.p_full_acquisition_source == ProbabilitySource.DERIVED

    def test_p_license_always_derived(self):
        out = compute_layer5(_base_inputs())
        assert out.p_license_or_partner_source == ProbabilitySource.DERIVED

    def test_p_takeout_6m_always_derived(self):
        out = compute_layer5(_base_inputs())
        assert out.p_takeout_6m_source == ProbabilitySource.DERIVED

    def test_p_takeout_18m_always_derived(self):
        out = compute_layer5(_base_inputs())
        assert out.p_takeout_18m_source == ProbabilitySource.DERIVED


# ---------------------------------------------------------------------------
# Block 26-C: Source consistency
# ---------------------------------------------------------------------------

class TestSourceConsistency:

    def test_fallback_source_and_very_low_confidence_co_occur(self, tmp_path, monkeypatch):
        """Block 22 caps confidence to VERY_LOW when unfitted; p_any_source is FALLBACK."""
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        out = compute_layer5(_base_inputs())
        assert out.p_any_source == ProbabilitySource.FALLBACK
        assert out.confidence_level == "very_low"

    def test_calibrated_source_allows_higher_confidence(self, tmp_path, monkeypatch):
        inp = _fitted_inputs(
            tmp_path, monkeypatch,
            data_confidence_score=0.90,
            n_comparable_observations=25,
            comparable_bucket_rate_source="segment_report",
        )
        out = compute_layer5(inp)
        assert out.p_any_source == ProbabilitySource.CALIBRATED
        assert out.confidence_level == "high"

    def test_all_sources_are_valid_enum_values(self):
        out = compute_layer5(_base_inputs())
        for field in ["p_any_source", "p_full_acquisition_source",
                      "p_license_or_partner_source", "p_takeout_6m_source",
                      "p_takeout_18m_source"]:
            val = getattr(out, field)
            assert isinstance(val, ProbabilitySource), f"{field} is not ProbabilitySource"

    def test_derived_sources_independent_of_calibration(self, tmp_path, monkeypatch):
        """DERIVED sources are always DERIVED regardless of calibration state."""
        # unfitted
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            tmp_path / "nonexistent.json",
        )
        out = compute_layer5(_base_inputs())
        assert out.p_full_acquisition_source == ProbabilitySource.DERIVED
        assert out.p_license_or_partner_source == ProbabilitySource.DERIVED


# ---------------------------------------------------------------------------
# Block 26-D: Backward compatibility
# ---------------------------------------------------------------------------

class TestBlock26BackwardCompat:

    def test_existing_fields_unchanged(self):
        out = compute_layer5(_base_inputs())
        for field in [
            "rank_score", "p_takeout_12m", "p_takeout_6m", "p_takeout_18m",
            "probability_band", "confidence_level", "top_positive_drivers",
            "top_negative_drivers", "calibration_cohort", "display_probability",
            "interpretation", "calibration_fitted", "calibration_params_source",
        ]:
            assert hasattr(out, field), f"Missing field: {field}"

    def test_source_fields_serialisable(self):
        """Source fields must survive model_dump() (machine-readable)."""
        out = compute_layer5(_base_inputs())
        d = out.model_dump()
        assert "p_any_source" in d
        assert "p_full_acquisition_source" in d
        assert isinstance(d["p_any_source"], str)  # enum serialised to string

    def test_new_source_fields_have_defaults(self):
        """All new source fields have defaults (backward compat for callers not reading them)."""
        out = compute_layer5(_base_inputs())
        # Just accessing them should not raise
        _ = out.p_any_source
        _ = out.p_full_acquisition_source
        _ = out.p_license_or_partner_source
        _ = out.p_takeout_6m_source
        _ = out.p_takeout_18m_source
