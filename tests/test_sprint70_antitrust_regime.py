"""
Block 30 — Antitrust Regime Modeling
TDD tests written BEFORE implementation.

Tests for:
  1. AntitrustRiskTier enum (5 values: LOW, MEDIUM, HIGH, BLOCKED, UNKNOWN)
  2. AntitrustRegime enum (5 values: US_PERMISSIVE, US_STANDARD, US_HOSTILE,
     EU_STANDARD, MULTI_JURISDICTIONAL)
  3. Layer5Inputs new fields: antitrust_risk_tier, antitrust_regime
  4. p_effective_close_12m — antitrust applies multiplicatively AFTER encumbrance
     (Block 29 × Block 30 combined multiplier)
  5. p_any_strategic_transaction_12m is never mutated by antitrust
  6. BLOCKED tier → p_effective_close_12m = 0.0 (regardless of regime)
  7. antitrust_multiplier_applied audit field
  8. antitrust_flag output field
  9. UNKNOWN tier lowers confidence one tier, not the point estimate
  10. Backward compatibility: no antitrust inputs → no effect
"""
from __future__ import annotations

import json

import pytest

from bve.intelligence.ma_layer5_calibration import (
    AntitrustRiskTier,
    AntitrustRegime,
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
# Block 30-A: AntitrustRiskTier enum
# ---------------------------------------------------------------------------

class TestAntitrustRiskTierEnum:

    def test_five_values_present(self):
        expected = {"low", "medium", "high", "blocked", "unknown"}
        actual = {v.value for v in AntitrustRiskTier}
        assert expected.issubset(actual)

    def test_low_value(self):
        assert AntitrustRiskTier.LOW.value == "low"

    def test_medium_value(self):
        assert AntitrustRiskTier.MEDIUM.value == "medium"

    def test_high_value(self):
        assert AntitrustRiskTier.HIGH.value == "high"

    def test_blocked_value(self):
        assert AntitrustRiskTier.BLOCKED.value == "blocked"

    def test_unknown_value(self):
        assert AntitrustRiskTier.UNKNOWN.value == "unknown"


# ---------------------------------------------------------------------------
# Block 30-B: AntitrustRegime enum
# ---------------------------------------------------------------------------

class TestAntitrustRegimeEnum:

    def test_five_values_present(self):
        expected = {
            "us_permissive", "us_standard", "us_hostile",
            "eu_standard", "multi_jurisdictional",
        }
        actual = {v.value for v in AntitrustRegime}
        assert expected.issubset(actual)

    def test_us_permissive_value(self):
        assert AntitrustRegime.US_PERMISSIVE.value == "us_permissive"

    def test_us_hostile_value(self):
        assert AntitrustRegime.US_HOSTILE.value == "us_hostile"

    def test_multi_jurisdictional_value(self):
        assert AntitrustRegime.MULTI_JURISDICTIONAL.value == "multi_jurisdictional"


# ---------------------------------------------------------------------------
# Block 30-C: Layer5Inputs new fields
# ---------------------------------------------------------------------------

class TestLayer5InputsAntitrustFields:

    def test_antitrust_risk_tier_field_exists(self):
        inp = _base_inputs()
        assert hasattr(inp, "antitrust_risk_tier")

    def test_antitrust_risk_tier_default_none(self):
        inp = _base_inputs()
        assert inp.antitrust_risk_tier is None

    def test_antitrust_regime_field_exists(self):
        inp = _base_inputs()
        assert hasattr(inp, "antitrust_regime")

    def test_antitrust_regime_default_none(self):
        inp = _base_inputs()
        assert inp.antitrust_regime is None

    def test_antitrust_risk_tier_accepts_high(self):
        inp = _base_inputs(antitrust_risk_tier=AntitrustRiskTier.HIGH)
        assert inp.antitrust_risk_tier == AntitrustRiskTier.HIGH

    def test_antitrust_regime_accepts_us_hostile(self):
        inp = _base_inputs(antitrust_regime=AntitrustRegime.US_HOSTILE)
        assert inp.antitrust_regime == AntitrustRegime.US_HOSTILE


# ---------------------------------------------------------------------------
# Block 30-D: antitrust multiplier application
# ---------------------------------------------------------------------------

class TestAntitrustMultiplier:

    def test_no_antitrust_p_effective_unchanged(self, tmp_path, monkeypatch):
        """Backward compat: no antitrust inputs → p_effective == p_any."""
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert out.p_effective_close_12m == pytest.approx(
            out.p_any_strategic_transaction_12m, abs=1e-4
        )

    def test_low_tier_p_effective_near_p_any(self, tmp_path, monkeypatch):
        """LOW risk has a small (or no) haircut."""
        out_base = compute_layer5(_fitted(tmp_path, monkeypatch))
        out_low = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.LOW,
        ))
        # LOW tier multiplier >= 0.90
        assert out_low.p_effective_close_12m >= out_base.p_any_strategic_transaction_12m * 0.90

    def test_high_tier_lowers_p_effective(self, tmp_path, monkeypatch):
        out_base = compute_layer5(_fitted(tmp_path, monkeypatch))
        out_high = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.HIGH,
        ))
        assert out_high.p_effective_close_12m < out_base.p_effective_close_12m

    def test_blocked_tier_zero_p_effective(self, tmp_path, monkeypatch):
        """BLOCKED → p_effective_close_12m == 0."""
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.BLOCKED,
        ))
        assert out.p_effective_close_12m == pytest.approx(0.0, abs=1e-6)

    def test_blocked_tier_p_any_not_mutated(self, tmp_path, monkeypatch):
        """BLOCKED antitrust must not change p_any."""
        out_base = compute_layer5(_fitted(tmp_path, monkeypatch))
        out_blocked = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.BLOCKED,
        ))
        assert out_blocked.p_any_strategic_transaction_12m == pytest.approx(
            out_base.p_any_strategic_transaction_12m, abs=1e-6
        )

    def test_high_tier_lower_than_medium(self, tmp_path, monkeypatch):
        out_med = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.MEDIUM,
        ))
        out_high = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.HIGH,
        ))
        assert out_high.p_effective_close_12m < out_med.p_effective_close_12m

    def test_us_hostile_lowers_more_than_us_standard(self, tmp_path, monkeypatch):
        out_std = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.HIGH,
            antitrust_regime=AntitrustRegime.US_STANDARD,
        ))
        out_hostile = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.HIGH,
            antitrust_regime=AntitrustRegime.US_HOSTILE,
        ))
        assert out_hostile.p_effective_close_12m <= out_std.p_effective_close_12m

    def test_antitrust_multiplicative_with_encumbrance(self, tmp_path, monkeypatch):
        """p_effective = p_any × enc_multiplier × antitrust_multiplier."""
        from bve.intelligence.ma_layer5_calibration import DealEncumbranceType
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            deal_encumbrance=DealEncumbranceType.ROFN,
            antitrust_risk_tier=AntitrustRiskTier.MEDIUM,
        ))
        p_any = out.p_any_strategic_transaction_12m
        enc_mult = out.encumbrance_multiplier_applied
        at_mult = out.antitrust_multiplier_applied
        expected = round(min(p_any * enc_mult * at_mult, 1.0), 4)
        assert out.p_effective_close_12m == pytest.approx(expected, abs=1e-4)


# ---------------------------------------------------------------------------
# Block 30-E: antitrust_multiplier_applied audit field
# ---------------------------------------------------------------------------

class TestAntitrustAuditField:

    def test_antitrust_multiplier_applied_field_exists(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert hasattr(out, "antitrust_multiplier_applied")

    def test_no_antitrust_multiplier_is_1_0(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert out.antitrust_multiplier_applied == pytest.approx(1.0)

    def test_blocked_multiplier_is_0_0(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.BLOCKED,
        ))
        assert out.antitrust_multiplier_applied == pytest.approx(0.0)

    def test_multiplier_serialisable(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        d = out.model_dump()
        assert "antitrust_multiplier_applied" in d
        assert isinstance(d["antitrust_multiplier_applied"], float)


# ---------------------------------------------------------------------------
# Block 30-F: antitrust_flag output field
# ---------------------------------------------------------------------------

class TestAntitrustFlag:

    def test_antitrust_flag_field_exists(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert hasattr(out, "antitrust_flag")

    def test_no_antitrust_flag_is_none(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(tmp_path, monkeypatch))
        assert out.antitrust_flag is None

    def test_high_tier_sets_flag(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.HIGH,
        ))
        assert out.antitrust_flag is not None

    def test_blocked_tier_sets_flag(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.BLOCKED,
        ))
        assert out.antitrust_flag is not None
        assert "blocked" in out.antitrust_flag.lower()

    def test_low_tier_no_flag(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.LOW,
        ))
        assert out.antitrust_flag is None

    def test_unknown_tier_sets_flag(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.UNKNOWN,
        ))
        assert out.antitrust_flag is not None
        assert "unknown" in out.antitrust_flag.lower()

    def test_medium_tier_sets_flag(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.MEDIUM,
        ))
        assert out.antitrust_flag is not None


# ---------------------------------------------------------------------------
# Block 30-G: UNKNOWN tier confidence degradation
# ---------------------------------------------------------------------------

class TestUnknownAntitrustConfidence:

    def test_unknown_tier_degrades_confidence(self, tmp_path, monkeypatch):
        out_base = compute_layer5(_fitted(tmp_path, monkeypatch))
        out_unknown = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.UNKNOWN,
        ))
        _order = ["high", "medium", "low", "very_low"]
        idx_base = _order.index(out_base.confidence_level)
        idx_unknown = _order.index(out_unknown.confidence_level)
        assert idx_unknown >= idx_base  # degraded or same (already at floor)

    def test_unknown_tier_p_any_unchanged(self, tmp_path, monkeypatch):
        out_base = compute_layer5(_fitted(tmp_path, monkeypatch))
        out_unknown = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.UNKNOWN,
        ))
        assert out_unknown.p_any_strategic_transaction_12m == pytest.approx(
            out_base.p_any_strategic_transaction_12m, abs=1e-6
        )

    def test_unknown_tier_p_effective_equals_p_any(self, tmp_path, monkeypatch):
        """UNKNOWN → multiplier=1.0; p_effective not changed."""
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.UNKNOWN,
        ))
        assert out.p_effective_close_12m == pytest.approx(
            out.p_any_strategic_transaction_12m, abs=1e-4
        )


# ---------------------------------------------------------------------------
# Block 30-H: backward compatibility
# ---------------------------------------------------------------------------

class TestAntitrustBackwardCompat:

    def test_existing_output_fields_present(self):
        out = compute_layer5(_base_inputs())
        for field in [
            "rank_score", "p_takeout_12m", "p_takeout_6m", "p_takeout_18m",
            "p_any_strategic_transaction_12m", "p_effective_close_12m",
            "probability_band", "confidence_level",
            "antitrust_multiplier_applied", "antitrust_flag",
        ]:
            assert hasattr(out, field), f"Missing field: {field}"

    def test_antitrust_flag_serialisable(self, tmp_path, monkeypatch):
        out = compute_layer5(_fitted(
            tmp_path, monkeypatch,
            antitrust_risk_tier=AntitrustRiskTier.HIGH,
        ))
        d = out.model_dump()
        assert "antitrust_flag" in d
