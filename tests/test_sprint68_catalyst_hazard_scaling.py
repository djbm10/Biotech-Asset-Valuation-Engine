"""
Block 31 — Catalyst-Based 6m/18m Hazard Scaling
TDD tests written BEFORE implementation.

Tests for:
  1. CatalystType enum (7 values)
  2. Timing shape derivation from days_to_catalyst + catalyst_type
  3. Dynamic _6M_SCALE and _18M_EXPONENT tables
  4. Layer5Inputs new fields: days_to_catalyst, catalyst_type
  5. Layer5Output new fields: timing_shape, timing_rationale,
     scale_6m_applied, scale_18m_exponent_applied
  6. Backward compatibility: default UNKNOWN matches old constants exactly
"""
from __future__ import annotations

import json

import pytest

from bve.intelligence.ma_layer5_calibration import (
    CatalystType,
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


def _fitted(tmp_path, monkeypatch, **kwargs) -> Layer5Inputs:
    p = tmp_path / "ma_calibration_params.json"
    p.write_text(json.dumps({"slope": 8.0, "midpoint": 0.68}))
    monkeypatch.setattr(
        "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH", p
    )
    return _base_inputs(**kwargs)


# ---------------------------------------------------------------------------
# Block 31-A: CatalystType enum
# ---------------------------------------------------------------------------

class TestCatalystTypeEnum:

    def test_seven_values_present(self):
        expected = {
            "none", "investor_update", "phase_2_poc",
            "fda_meeting", "regulatory_decision", "phase_3_readout", "unknown",
        }
        actual = {v.value for v in CatalystType}
        assert expected.issubset(actual)

    def test_unknown_value(self):
        assert CatalystType.UNKNOWN.value == "unknown"

    def test_phase_3_readout_value(self):
        assert CatalystType.PHASE_3_READOUT.value == "phase_3_readout"

    def test_regulatory_decision_value(self):
        assert CatalystType.REGULATORY_DECISION.value == "regulatory_decision"


# ---------------------------------------------------------------------------
# Block 31-B: Layer5Inputs new fields
# ---------------------------------------------------------------------------

class TestLayer5InputsNewFields:

    def test_days_to_catalyst_field_exists(self):
        inp = _base_inputs()
        assert hasattr(inp, "days_to_catalyst")

    def test_days_to_catalyst_default_none(self):
        inp = _base_inputs()
        assert inp.days_to_catalyst is None

    def test_catalyst_type_field_exists(self):
        inp = _base_inputs()
        assert hasattr(inp, "catalyst_type")

    def test_catalyst_type_default_unknown(self):
        inp = _base_inputs()
        assert inp.catalyst_type == CatalystType.UNKNOWN

    def test_days_to_catalyst_accepts_int(self):
        inp = _base_inputs(days_to_catalyst=45)
        assert inp.days_to_catalyst == 45

    def test_catalyst_type_accepts_phase3_readout(self):
        inp = _base_inputs(catalyst_type=CatalystType.PHASE_3_READOUT)
        assert inp.catalyst_type == CatalystType.PHASE_3_READOUT


# ---------------------------------------------------------------------------
# Block 31-C: timing_shape derivation
# ---------------------------------------------------------------------------

class TestTimingShape:

    def _shape(self, tmp_path, monkeypatch, **kwargs) -> str:
        out = compute_layer5(_fitted(tmp_path, monkeypatch, **kwargs))
        return out.timing_shape

    def test_phase3_readout_90d_strongly_front_loaded(self, tmp_path, monkeypatch):
        shape = self._shape(
            tmp_path, monkeypatch,
            days_to_catalyst=45,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        )
        assert shape == "strongly_front_loaded"

    def test_regulatory_decision_60d_strongly_front_loaded(self, tmp_path, monkeypatch):
        shape = self._shape(
            tmp_path, monkeypatch,
            days_to_catalyst=60,
            catalyst_type=CatalystType.REGULATORY_DECISION,
        )
        assert shape == "strongly_front_loaded"

    def test_phase2_poc_120d_front_loaded(self, tmp_path, monkeypatch):
        shape = self._shape(
            tmp_path, monkeypatch,
            days_to_catalyst=120,
            catalyst_type=CatalystType.PHASE_2_POC,
        )
        assert shape == "front_loaded"

    def test_fda_meeting_150d_front_loaded(self, tmp_path, monkeypatch):
        shape = self._shape(
            tmp_path, monkeypatch,
            days_to_catalyst=150,
            catalyst_type=CatalystType.FDA_MEETING,
        )
        assert shape == "front_loaded"

    def test_investor_update_30d_not_strongly_front_loaded(self, tmp_path, monkeypatch):
        """Investor update is a minor catalyst — should not strongly front-load."""
        shape = self._shape(
            tmp_path, monkeypatch,
            days_to_catalyst=30,
            catalyst_type=CatalystType.INVESTOR_UPDATE,
        )
        assert shape != "strongly_front_loaded"

    def test_none_catalyst_neutral(self, tmp_path, monkeypatch):
        shape = self._shape(
            tmp_path, monkeypatch,
            days_to_catalyst=None,
            catalyst_type=CatalystType.NONE,
        )
        assert shape == "neutral"

    def test_unknown_catalyst_neutral(self, tmp_path, monkeypatch):
        shape = self._shape(
            tmp_path, monkeypatch,
            days_to_catalyst=None,
            catalyst_type=CatalystType.UNKNOWN,
        )
        assert shape == "neutral"

    def test_beyond_365d_back_loaded(self, tmp_path, monkeypatch):
        shape = self._shape(
            tmp_path, monkeypatch,
            days_to_catalyst=400,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        )
        assert shape == "back_loaded"

    def test_no_days_unknown_type_neutral(self, tmp_path, monkeypatch):
        shape = self._shape(tmp_path, monkeypatch)  # all defaults
        assert shape == "neutral"


# ---------------------------------------------------------------------------
# Block 31-D: dynamic 6m scaling
# ---------------------------------------------------------------------------

class TestDynamic6mScaling:

    def _out(self, tmp_path, monkeypatch, **kwargs) -> Layer5Output:
        return compute_layer5(_fitted(tmp_path, monkeypatch, **kwargs))

    def test_strongly_front_loaded_6m_scale_0_80(self, tmp_path, monkeypatch):
        out = self._out(
            tmp_path, monkeypatch,
            days_to_catalyst=45,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        )
        assert out.scale_6m_applied == pytest.approx(0.80)

    def test_front_loaded_6m_scale_0_68(self, tmp_path, monkeypatch):
        out = self._out(
            tmp_path, monkeypatch,
            days_to_catalyst=120,
            catalyst_type=CatalystType.PHASE_2_POC,
        )
        assert out.scale_6m_applied == pytest.approx(0.68)

    def test_neutral_6m_scale_0_55_backward_compat(self, tmp_path, monkeypatch):
        out = self._out(tmp_path, monkeypatch)  # UNKNOWN defaults
        assert out.scale_6m_applied == pytest.approx(0.55)

    def test_back_loaded_6m_scale_0_38(self, tmp_path, monkeypatch):
        out = self._out(
            tmp_path, monkeypatch,
            days_to_catalyst=400,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        )
        assert out.scale_6m_applied == pytest.approx(0.38)

    def test_strongly_front_loaded_6m_prob_higher_than_neutral(self, tmp_path, monkeypatch):
        out_front = self._out(
            tmp_path, monkeypatch,
            days_to_catalyst=45,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        )
        out_neutral = self._out(tmp_path, monkeypatch)
        assert out_front.p_takeout_6m > out_neutral.p_takeout_6m

    def test_back_loaded_6m_prob_lower_than_neutral(self, tmp_path, monkeypatch):
        out_back = self._out(
            tmp_path, monkeypatch,
            days_to_catalyst=400,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        )
        out_neutral = self._out(tmp_path, monkeypatch)
        assert out_back.p_takeout_6m < out_neutral.p_takeout_6m


# ---------------------------------------------------------------------------
# Block 31-E: dynamic 18m exponent
# ---------------------------------------------------------------------------

class TestDynamic18mExponent:

    def _out(self, tmp_path, monkeypatch, **kwargs) -> Layer5Output:
        return compute_layer5(_fitted(tmp_path, monkeypatch, **kwargs))

    def test_strongly_front_loaded_18m_exponent_1_10(self, tmp_path, monkeypatch):
        out = self._out(
            tmp_path, monkeypatch,
            days_to_catalyst=45,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        )
        assert out.scale_18m_exponent_applied == pytest.approx(1.10)

    def test_neutral_18m_exponent_1_35_backward_compat(self, tmp_path, monkeypatch):
        out = self._out(tmp_path, monkeypatch)
        assert out.scale_18m_exponent_applied == pytest.approx(1.35)

    def test_back_loaded_18m_exponent_1_55(self, tmp_path, monkeypatch):
        out = self._out(
            tmp_path, monkeypatch,
            days_to_catalyst=400,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        )
        assert out.scale_18m_exponent_applied == pytest.approx(1.55)

    def test_front_loaded_18m_exponent_1_25(self, tmp_path, monkeypatch):
        out = self._out(
            tmp_path, monkeypatch,
            days_to_catalyst=120,
            catalyst_type=CatalystType.PHASE_2_POC,
        )
        assert out.scale_18m_exponent_applied == pytest.approx(1.25)

    def test_strongly_front_loaded_18m_prob_lower_than_neutral(self, tmp_path, monkeypatch):
        out_front = self._out(
            tmp_path, monkeypatch,
            days_to_catalyst=45,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        )
        out_neutral = self._out(tmp_path, monkeypatch)
        # lower exponent (1.10 vs 1.35) → slower decay → but probability is front-loaded
        # into the 6m window, so 18m probability is lower for strongly_front_loaded
        assert out_front.p_takeout_18m < out_neutral.p_takeout_18m


# ---------------------------------------------------------------------------
# Block 31-F: output fields
# ---------------------------------------------------------------------------

class TestOutputFields:

    def test_timing_shape_in_output(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "timing_shape")
        assert isinstance(out.timing_shape, str)

    def test_timing_rationale_in_output(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "timing_rationale")
        assert isinstance(out.timing_rationale, str)

    def test_scale_6m_applied_in_output(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "scale_6m_applied")
        assert isinstance(out.scale_6m_applied, float)

    def test_scale_18m_exponent_applied_in_output(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "scale_18m_exponent_applied")
        assert isinstance(out.scale_18m_exponent_applied, float)

    def test_timing_rationale_non_empty_when_catalyst_set(self, tmp_path, monkeypatch):
        p = tmp_path / "ma_calibration_params.json"
        p.write_text(json.dumps({"slope": 8.0, "midpoint": 0.68}))
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH", p
        )
        out = compute_layer5(_base_inputs(
            days_to_catalyst=45,
            catalyst_type=CatalystType.PHASE_3_READOUT,
        ))
        assert out.timing_rationale != ""

    def test_timing_shape_serialisable(self):
        out = compute_layer5(_base_inputs())
        d = out.model_dump()
        assert "timing_shape" in d
        assert isinstance(d["timing_shape"], str)


# ---------------------------------------------------------------------------
# Block 31-G: backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompat:

    def test_no_catalyst_uses_0_55_scale(self):
        out = compute_layer5(_base_inputs())
        assert out.scale_6m_applied == pytest.approx(0.55)

    def test_no_catalyst_uses_1_35_exponent(self):
        out = compute_layer5(_base_inputs())
        assert out.scale_18m_exponent_applied == pytest.approx(1.35)

    def test_existing_output_fields_present(self):
        out = compute_layer5(_base_inputs())
        for field in [
            "rank_score", "p_takeout_12m", "p_takeout_6m", "p_takeout_18m",
            "probability_band", "confidence_level", "top_positive_drivers",
            "calibration_fitted", "calibration_params_source",
            "p_any_source", "p_full_acquisition_source",
            "seller_willingness_flag",
        ]:
            assert hasattr(out, field), f"Missing field: {field}"

    def test_p_takeout_6m_formula_unchanged_for_neutral(self):
        """p_takeout_6m = p_any_strategic_transaction_12m * 0.55 when neutral."""
        out = compute_layer5(_base_inputs())
        assert out.p_takeout_6m == pytest.approx(out.p_any_strategic_transaction_12m * 0.55, abs=1e-4)

    def test_p_takeout_18m_formula_unchanged_for_neutral(self):
        """p_takeout_18m = 1-(1-p_any)^1.35 when neutral."""
        out = compute_layer5(_base_inputs())
        p_any = out.p_any_strategic_transaction_12m
        expected_18m = 1.0 - (1.0 - p_any) ** 1.35
        assert out.p_takeout_18m == pytest.approx(expected_18m, abs=1e-4)
