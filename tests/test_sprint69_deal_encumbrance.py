"""
Block 29 — ROFR vs ROFN Deal Encumbrance
TDD tests written BEFORE implementation.

Tests for:
  1. DealEncumbranceType enum (5 values)
  2. Layer5Inputs new field: deal_encumbrance (Optional, default None)
  3. p_effective_close_12m — post-encumbrance closing probability (NEW field,
     separate from p_any_strategic_transaction_12m which is never mutated)
  4. Multiplier table: NONE=1.0, ROFN=0.90, ROFR=0.75, OPTION_TO_ACQUIRE=0.95
  5. UNKNOWN deal_encumbrance lowers CONFIDENCE one tier, NOT the point estimate
  6. encumbrance_flag output field
  7. encumbrance_multiplier_applied audit field
  8. Backward compatibility: no deal_encumbrance → p_effective_close == p_any
"""
from __future__ import annotations

import json

import pytest

from bve.intelligence.ma_layer5_calibration import (
    DealEncumbranceType,
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
# Block 29-A: DealEncumbranceType enum
# ---------------------------------------------------------------------------

class TestDealEncumbranceTypeEnum:

    def test_five_values_present(self):
        expected = {"none", "rofr", "rofn", "option_to_acquire", "unknown"}
        actual = {v.value for v in DealEncumbranceType}
        assert expected.issubset(actual)

    def test_none_value(self):
        assert DealEncumbranceType.NONE.value == "none"

    def test_rofr_value(self):
        assert DealEncumbranceType.ROFR.value == "rofr"

    def test_rofn_value(self):
        assert DealEncumbranceType.ROFN.value == "rofn"

    def test_option_to_acquire_value(self):
        assert DealEncumbranceType.OPTION_TO_ACQUIRE.value == "option_to_acquire"

    def test_unknown_value(self):
        assert DealEncumbranceType.UNKNOWN.value == "unknown"


# ---------------------------------------------------------------------------
# Block 29-B: Layer5Inputs new field
# ---------------------------------------------------------------------------

class TestLayer5InputsEncumbranceField:

    def test_deal_encumbrance_field_exists(self):
        inp = _base_inputs()
        assert hasattr(inp, "deal_encumbrance")

    def test_deal_encumbrance_default_none(self):
        inp = _base_inputs()
        assert inp.deal_encumbrance is None

    def test_deal_encumbrance_accepts_rofr(self):
        inp = _base_inputs(deal_encumbrance=DealEncumbranceType.ROFR)
        assert inp.deal_encumbrance == DealEncumbranceType.ROFR

    def test_deal_encumbrance_accepts_rofn(self):
        inp = _base_inputs(deal_encumbrance=DealEncumbranceType.ROFN)
        assert inp.deal_encumbrance == DealEncumbranceType.ROFN

    def test_deal_encumbrance_accepts_none_enum(self):
        inp = _base_inputs(deal_encumbrance=DealEncumbranceType.NONE)
        assert inp.deal_encumbrance == DealEncumbranceType.NONE

    def test_deal_encumbrance_accepts_unknown(self):
        inp = _base_inputs(deal_encumbrance=DealEncumbranceType.UNKNOWN)
        assert inp.deal_encumbrance == DealEncumbranceType.UNKNOWN


# ---------------------------------------------------------------------------
# Block 29-C: p_effective_close_12m output field
# ---------------------------------------------------------------------------

class TestPEffectiveClose12m:

    def test_p_effective_close_12m_field_exists(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert hasattr(out, "p_effective_close_12m")

    def test_p_effective_close_12m_is_float(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert isinstance(out.p_effective_close_12m, float)

    def test_p_effective_close_in_range(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert 0.0 <= out.p_effective_close_12m <= 1.0

    def test_no_encumbrance_p_effective_equals_p_any(self, tmp_path, monkeypatch):
        """When deal_encumbrance=None (backward compat), p_effective == p_any."""
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert out.p_effective_close_12m == pytest.approx(
            out.p_any_strategic_transaction_12m, abs=1e-4
        )

    def test_none_enum_p_effective_equals_p_any(self, tmp_path, monkeypatch):
        """DealEncumbranceType.NONE gives multiplier=1.0 → p_effective == p_any."""
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.NONE,
        ))
        assert out.p_effective_close_12m == pytest.approx(
            out.p_any_strategic_transaction_12m, abs=1e-4
        )

    def test_p_any_not_mutated_by_rofr(self, tmp_path, monkeypatch):
        """p_any_strategic_transaction_12m must be the same regardless of encumbrance."""
        out_no_enc = compute_layer5(_fitted(tmp_path, monkeypatch))
        out_rofr = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.ROFR,
        ))
        assert out_rofr.p_any_strategic_transaction_12m == pytest.approx(
            out_no_enc.p_any_strategic_transaction_12m, abs=1e-6
        )

    def test_p_any_not_mutated_by_rofn(self, tmp_path, monkeypatch):
        out_no_enc = compute_layer5(_fitted(tmp_path, monkeypatch))
        out_rofn = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.ROFN,
        ))
        assert out_rofn.p_any_strategic_transaction_12m == pytest.approx(
            out_no_enc.p_any_strategic_transaction_12m, abs=1e-6
        )


# ---------------------------------------------------------------------------
# Block 29-D: Multiplier values
# ---------------------------------------------------------------------------

class TestEncumbranceMultipliers:

    def _p_effective(self, tmp_path, monkeypatch, encumbrance) -> float:
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=encumbrance,
        ))
        return out.p_effective_close_12m

    def _p_any(self, tmp_path, monkeypatch) -> float:
        return compute_layer5(_fitted(tmp_path, monkeypatch)).p_any_strategic_transaction_12m

    def test_rofr_multiplier_0_75(self, tmp_path, monkeypatch):
        p_any = self._p_any(tmp_path, monkeypatch)
        p_eff = self._p_effective(tmp_path, monkeypatch, DealEncumbranceType.ROFR)
        assert p_eff == pytest.approx(p_any * 0.75, abs=1e-4)

    def test_rofn_multiplier_0_90(self, tmp_path, monkeypatch):
        p_any = self._p_any(tmp_path, monkeypatch)
        p_eff = self._p_effective(tmp_path, monkeypatch, DealEncumbranceType.ROFN)
        assert p_eff == pytest.approx(p_any * 0.90, abs=1e-4)

    def test_option_to_acquire_multiplier_0_95(self, tmp_path, monkeypatch):
        p_any = self._p_any(tmp_path, monkeypatch)
        p_eff = self._p_effective(tmp_path, monkeypatch, DealEncumbranceType.OPTION_TO_ACQUIRE)
        assert p_eff == pytest.approx(p_any * 0.95, abs=1e-4)

    def test_rofr_lowers_p_effective_more_than_rofn(self, tmp_path, monkeypatch):
        p_rofr = self._p_effective(tmp_path, monkeypatch, DealEncumbranceType.ROFR)
        p_rofn = self._p_effective(tmp_path, monkeypatch, DealEncumbranceType.ROFN)
        assert p_rofr < p_rofn

    def test_rofn_lowers_p_effective_more_than_option(self, tmp_path, monkeypatch):
        p_rofn = self._p_effective(tmp_path, monkeypatch, DealEncumbranceType.ROFN)
        p_opt = self._p_effective(tmp_path, monkeypatch, DealEncumbranceType.OPTION_TO_ACQUIRE)
        assert p_rofn < p_opt

    def test_unknown_p_effective_equals_p_any(self, tmp_path, monkeypatch):
        """UNKNOWN → multiplier=1.0; only confidence degrades."""
        p_any = self._p_any(tmp_path, monkeypatch)
        p_eff = self._p_effective(tmp_path, monkeypatch, DealEncumbranceType.UNKNOWN)
        assert p_eff == pytest.approx(p_any, abs=1e-4)

    def test_encumbrance_multiplier_applied_rofr(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.ROFR,
        ))
        assert out.encumbrance_multiplier_applied == pytest.approx(0.75)

    def test_encumbrance_multiplier_applied_rofn(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.ROFN,
        ))
        assert out.encumbrance_multiplier_applied == pytest.approx(0.90)

    def test_encumbrance_multiplier_applied_none_is_1_0(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert out.encumbrance_multiplier_applied == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Block 29-E: UNKNOWN lowers confidence, not point estimate
# ---------------------------------------------------------------------------

class TestUnknownEncumbranceConfidence:

    def test_unknown_encumbrance_degrades_confidence(self, tmp_path, monkeypatch):
        out_no_enc = compute_layer5(_fitted(tmp_path, monkeypatch))
        out_unknown = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.UNKNOWN,
        ))
        _order = ["high", "medium", "low", "very_low"]
        idx_no_enc = _order.index(out_no_enc.confidence_level)
        idx_unknown = _order.index(out_unknown.confidence_level)
        assert idx_unknown >= idx_no_enc  # confidence degraded (higher index = lower confidence)

    def test_unknown_p_any_unchanged(self, tmp_path, monkeypatch):
        out_no_enc = compute_layer5(_fitted(tmp_path, monkeypatch))
        out_unknown = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.UNKNOWN,
        ))
        assert out_unknown.p_any_strategic_transaction_12m == pytest.approx(
            out_no_enc.p_any_strategic_transaction_12m, abs=1e-6
        )


# ---------------------------------------------------------------------------
# Block 29-F: encumbrance_flag output field
# ---------------------------------------------------------------------------

class TestEncumbranceFlag:

    def test_encumbrance_flag_field_exists(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert hasattr(out, "encumbrance_flag")

    def test_no_encumbrance_flag_is_none(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert out.encumbrance_flag is None

    def test_rofr_sets_flag(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.ROFR,
        ))
        assert out.encumbrance_flag is not None
        assert "rofr" in out.encumbrance_flag.lower()

    def test_rofn_sets_flag(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.ROFN,
        ))
        assert out.encumbrance_flag is not None
        assert "rofn" in out.encumbrance_flag.lower()

    def test_option_to_acquire_sets_flag(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.OPTION_TO_ACQUIRE,
        ))
        assert out.encumbrance_flag is not None

    def test_unknown_sets_flag(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.UNKNOWN,
        ))
        assert out.encumbrance_flag is not None
        assert "unknown" in out.encumbrance_flag.lower()

    def test_none_enum_flag_is_none(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.NONE,
        ))
        assert out.encumbrance_flag is None

    def test_encumbrance_flag_is_string_or_none(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.ROFR,
        ))
        assert isinstance(out.encumbrance_flag, str)


# ---------------------------------------------------------------------------
# Block 29-G: backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompat:

    def test_no_encumbrance_field_existing_tests_pass(self):
        """All existing outputs present and p_effective == p_any when unset."""
        out = compute_layer5(_base_inputs())
        for field in [
            "rank_score", "p_takeout_12m", "p_takeout_6m", "p_takeout_18m",
            "probability_band", "confidence_level", "p_any_strategic_transaction_12m",
            "p_effective_close_12m",
        ]:
            assert hasattr(out, field), f"Missing field: {field}"

    def test_p_effective_serialisable(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        d = out.model_dump()
        assert "p_effective_close_12m" in d
        assert isinstance(d["p_effective_close_12m"], float)

    def test_encumbrance_multiplier_serialisable(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        d = out.model_dump()
        assert "encumbrance_multiplier_applied" in d
        assert isinstance(d["encumbrance_multiplier_applied"], float)
