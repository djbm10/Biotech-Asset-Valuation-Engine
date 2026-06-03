"""
Block 27 — Structured Seller Willingness
TDD tests written BEFORE implementation.

Tests for:
  1. SellerWillingness enum with observable anchors
  2. _SELLER_WILLINGNESS_SCORES mapping float values
  3. seller_willingness_to_score() helper
  4. seller_willingness_anchor field on Layer5Inputs (optional)
  5. Model validator: anchor overrides float
  6. seller_willingness_flag on Layer5Output
  7. UNKNOWN anchor degrades confidence by one tier
  8. Backward compatibility: float-only callers unchanged
"""
from __future__ import annotations

import json

import pytest

from bve.intelligence.ma_layer5_calibration import (
    Layer5Inputs,
    Layer5Output,
    SellerWillingness,
    seller_willingness_to_score,
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


def _fitted_params_file(tmp_path):
    params_file = tmp_path / "ma_calibration_params.json"
    params_file.write_text(json.dumps({"slope": 8.0, "midpoint": 0.68}))
    return params_file


# ---------------------------------------------------------------------------
# Block 27-A: SellerWillingness enum
# ---------------------------------------------------------------------------

class TestSellerWillingnessEnum:

    def test_six_values_present(self):
        expected = {"actively_seeking", "open", "neutral", "reluctant", "hostile", "unknown"}
        actual = {v.value for v in SellerWillingness}
        assert expected.issubset(actual)

    def test_actively_seeking_value(self):
        assert SellerWillingness.ACTIVELY_SEEKING.value == "actively_seeking"

    def test_open_value(self):
        assert SellerWillingness.OPEN.value == "open"

    def test_neutral_value(self):
        assert SellerWillingness.NEUTRAL.value == "neutral"

    def test_reluctant_value(self):
        assert SellerWillingness.RELUCTANT.value == "reluctant"

    def test_hostile_value(self):
        assert SellerWillingness.HOSTILE.value == "hostile"

    def test_unknown_value(self):
        assert SellerWillingness.UNKNOWN.value == "unknown"

    def test_actively_seeking_score_0_90(self):
        assert seller_willingness_to_score(SellerWillingness.ACTIVELY_SEEKING) == pytest.approx(0.90)

    def test_open_score_0_70(self):
        assert seller_willingness_to_score(SellerWillingness.OPEN) == pytest.approx(0.70)

    def test_neutral_score_0_50(self):
        assert seller_willingness_to_score(SellerWillingness.NEUTRAL) == pytest.approx(0.50)

    def test_reluctant_score_0_30(self):
        assert seller_willingness_to_score(SellerWillingness.RELUCTANT) == pytest.approx(0.30)

    def test_hostile_score_0_10(self):
        assert seller_willingness_to_score(SellerWillingness.HOSTILE) == pytest.approx(0.10)

    def test_unknown_score_0_50(self):
        """UNKNOWN maps to 0.50 (neutral; epistemically different from NEUTRAL)."""
        assert seller_willingness_to_score(SellerWillingness.UNKNOWN) == pytest.approx(0.50)

    def test_scores_ordered_actively_seeking_highest(self):
        scores = [seller_willingness_to_score(w) for w in [
            SellerWillingness.HOSTILE,
            SellerWillingness.RELUCTANT,
            SellerWillingness.NEUTRAL,
            SellerWillingness.OPEN,
            SellerWillingness.ACTIVELY_SEEKING,
        ]]
        assert scores == sorted(scores)


# ---------------------------------------------------------------------------
# Block 27-B: seller_willingness_anchor field on Layer5Inputs
# ---------------------------------------------------------------------------

class TestLayer5InputsAnchor:

    def test_anchor_field_exists(self):
        inp = _base_inputs()
        assert hasattr(inp, "seller_willingness_anchor")

    def test_anchor_default_is_none(self):
        inp = _base_inputs()
        assert inp.seller_willingness_anchor is None

    def test_no_anchor_uses_float(self):
        inp = _base_inputs(seller_willingness=0.65)
        assert inp.seller_willingness == pytest.approx(0.65)

    def test_actively_seeking_anchor_overrides_float(self):
        inp = _base_inputs(
            seller_willingness=0.30,  # would normally be used
            seller_willingness_anchor=SellerWillingness.ACTIVELY_SEEKING,
        )
        assert inp.seller_willingness == pytest.approx(0.90)

    def test_hostile_anchor_overrides_float(self):
        inp = _base_inputs(
            seller_willingness=0.80,
            seller_willingness_anchor=SellerWillingness.HOSTILE,
        )
        assert inp.seller_willingness == pytest.approx(0.10)

    def test_unknown_anchor_sets_float_0_50(self):
        inp = _base_inputs(
            seller_willingness=0.70,
            seller_willingness_anchor=SellerWillingness.UNKNOWN,
        )
        assert inp.seller_willingness == pytest.approx(0.50)

    def test_neutral_anchor_sets_float_0_50(self):
        inp = _base_inputs(
            seller_willingness=0.80,
            seller_willingness_anchor=SellerWillingness.NEUTRAL,
        )
        assert inp.seller_willingness == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Block 27-C: seller_willingness_flag on Layer5Output
# ---------------------------------------------------------------------------

class TestSellerWillingnessFlag:

    def test_flag_field_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "seller_willingness_flag")

    def test_flag_none_when_no_anchor(self):
        out = compute_layer5(_base_inputs())
        assert out.seller_willingness_flag is None or out.seller_willingness_flag == ""

    def test_flag_set_when_unknown_anchor(self):
        inp = _base_inputs(seller_willingness_anchor=SellerWillingness.UNKNOWN)
        out = compute_layer5(inp)
        assert out.seller_willingness_flag is not None
        assert out.seller_willingness_flag != ""

    def test_flag_contains_unknown(self):
        inp = _base_inputs(seller_willingness_anchor=SellerWillingness.UNKNOWN)
        out = compute_layer5(inp)
        assert "unknown" in out.seller_willingness_flag.lower()

    def test_flag_none_when_neutral_anchor(self):
        """NEUTRAL (explicit observation) does not set the flag."""
        inp = _base_inputs(seller_willingness_anchor=SellerWillingness.NEUTRAL)
        out = compute_layer5(inp)
        assert out.seller_willingness_flag is None or out.seller_willingness_flag == ""

    def test_flag_none_when_open_anchor(self):
        inp = _base_inputs(seller_willingness_anchor=SellerWillingness.OPEN)
        out = compute_layer5(inp)
        assert out.seller_willingness_flag is None or out.seller_willingness_flag == ""


# ---------------------------------------------------------------------------
# Block 27-D: UNKNOWN anchor degrades confidence one tier
# ---------------------------------------------------------------------------

class TestSellerUnknownConfidenceDegradation:

    def test_unknown_anchor_degrades_high_to_medium(self, tmp_path, monkeypatch):
        """UNKNOWN anchor degrades HIGH → MEDIUM."""
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            _fitted_params_file(tmp_path),
        )
        # inputs that would produce HIGH without UNKNOWN anchor
        inp_high = _base_inputs(
            data_confidence_score=0.90,
            n_comparable_observations=25,
            comparable_bucket_rate_source="segment_report",
        )
        out_high = compute_layer5(inp_high)
        assert out_high.confidence_level == "high"

        # same inputs with UNKNOWN anchor → one tier down
        inp_unknown = _base_inputs(
            data_confidence_score=0.90,
            n_comparable_observations=25,
            comparable_bucket_rate_source="segment_report",
            seller_willingness_anchor=SellerWillingness.UNKNOWN,
        )
        out_unknown = compute_layer5(inp_unknown)
        assert out_unknown.confidence_level == "medium"

    def test_unknown_anchor_degrades_medium_to_low(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            _fitted_params_file(tmp_path),
        )
        inp = _base_inputs(
            data_confidence_score=0.70,
            n_comparable_observations=12,
            comparable_bucket_rate_source="segment_report",
            seller_willingness_anchor=SellerWillingness.UNKNOWN,
        )
        out = compute_layer5(inp)
        assert out.confidence_level == "low"

    def test_unknown_anchor_degrades_low_to_very_low(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            _fitted_params_file(tmp_path),
        )
        inp = _base_inputs(
            data_confidence_score=0.52,
            n_comparable_observations=4,
            seller_willingness_anchor=SellerWillingness.UNKNOWN,
        )
        out = compute_layer5(inp)
        assert out.confidence_level == "very_low"

    def test_already_very_low_stays_very_low_with_unknown_anchor(self, tmp_path, monkeypatch):
        """UNKNOWN anchor on top of already-VERY_LOW: stays VERY_LOW (no floor breach)."""
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            _fitted_params_file(tmp_path),
        )
        inp = _base_inputs(
            data_confidence_score=0.30,
            n_comparable_observations=2,
            seller_willingness_anchor=SellerWillingness.UNKNOWN,
        )
        out = compute_layer5(inp)
        assert out.confidence_level == "very_low"

    def test_neutral_anchor_no_confidence_penalty(self, tmp_path, monkeypatch):
        """NEUTRAL (known observation) does not degrade confidence."""
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            _fitted_params_file(tmp_path),
        )
        inp_no_anchor = _base_inputs(
            data_confidence_score=0.90,
            n_comparable_observations=25,
            comparable_bucket_rate_source="segment_report",
        )
        inp_neutral = _base_inputs(
            data_confidence_score=0.90,
            n_comparable_observations=25,
            comparable_bucket_rate_source="segment_report",
            seller_willingness_anchor=SellerWillingness.NEUTRAL,
        )
        out_no_anchor = compute_layer5(inp_no_anchor)
        out_neutral   = compute_layer5(inp_neutral)
        assert out_no_anchor.confidence_level == out_neutral.confidence_level

    def test_no_anchor_no_confidence_penalty(self):
        """Float-only callers (no anchor) do not get confidence penalty."""
        inp_no_anchor  = _base_inputs(seller_willingness=0.50)
        inp_with_float = _base_inputs(seller_willingness=0.50)
        out1 = compute_layer5(inp_no_anchor)
        out2 = compute_layer5(inp_with_float)
        assert out1.confidence_level == out2.confidence_level


# ---------------------------------------------------------------------------
# Block 27-E: Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatSeller:

    def test_float_only_callers_work_unchanged(self):
        inp = Layer5Inputs(
            rank_score=0.50,
            rank_percentile=0.50,
            strategic_priority=0.50,
            transaction_probability=0.50,
            asset_quality=0.60,
            seller_willingness=0.55,
        )
        out = compute_layer5(inp)
        assert 0.0 <= out.p_takeout_12m <= 1.0

    def test_existing_layer5_output_fields_present(self):
        out = compute_layer5(_base_inputs())
        for field in [
            "rank_score", "p_takeout_12m", "p_takeout_6m", "p_takeout_18m",
            "probability_band", "confidence_level", "top_positive_drivers",
            "calibration_fitted", "calibration_params_source",
            "p_any_source", "p_full_acquisition_source",
        ]:
            assert hasattr(out, field), f"Missing field: {field}"
