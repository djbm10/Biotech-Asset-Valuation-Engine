"""Tests for Wave 2C — Trial Design Assessment."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError
from scipy.stats import norm

from bve.alerts.alert_model import Alert, AlertSeverity, AlertTrigger
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.intelligence.trial_design_assessment import (
    LOW_POWER_THRESHOLD,
    TIER_MULTIPLIERS,
    DesignQualityTier,
    TrialDesignAssessment,
    assess_trial_design,
    make_low_power_alert,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)
_TODAY = date.today()


def _signal(**kwargs) -> StructuredSignal:
    """Build a minimal StructuredSignal with overridable fields."""
    defaults = dict(
        id="sig-001",
        event_id="evt-001",
        asset_id="asset-001",
        company_id="company-001",
        event_type=EventType.TRIAL_READOUT,
        signal_date=_TODAY,
        extraction_model="test",
        created_at=_NOW,
    )
    defaults.update(kwargs)
    return StructuredSignal(**defaults)


# ---------------------------------------------------------------------------
# AlertTrigger enum
# ---------------------------------------------------------------------------


def test_alert_trigger_low_statistical_power_exists():
    assert AlertTrigger.LOW_STATISTICAL_POWER.value == "low_statistical_power"


# ---------------------------------------------------------------------------
# DesignQualityTier multipliers
# ---------------------------------------------------------------------------


def test_tier_multiplier_single_arm():
    assert TIER_MULTIPLIERS[DesignQualityTier.SINGLE_ARM] == pytest.approx(0.80)


def test_tier_multiplier_os_rct():
    assert TIER_MULTIPLIERS[DesignQualityTier.OS_RCT] == pytest.approx(1.10)


def test_tier_multiplier_pfs():
    assert TIER_MULTIPLIERS[DesignQualityTier.PFS] == pytest.approx(1.00)


def test_tier_multiplier_surrogate():
    assert TIER_MULTIPLIERS[DesignQualityTier.SURROGATE] == pytest.approx(0.85)


def test_tier_multiplier_standard():
    assert TIER_MULTIPLIERS[DesignQualityTier.STANDARD] == pytest.approx(1.00)


# ---------------------------------------------------------------------------
# Tier classification — priority order
# ---------------------------------------------------------------------------


def test_os_rct_tier(  ):
    s = _signal(randomization="randomized", endpoint_type="os")
    a = assess_trial_design(s)
    assert a.design_quality_tier == DesignQualityTier.OS_RCT
    assert a.design_quality_multiplier == pytest.approx(1.10)


def test_pfs_tier():
    s = _signal(randomization="randomized", endpoint_type="pfs")
    a = assess_trial_design(s)
    assert a.design_quality_tier == DesignQualityTier.PFS
    assert a.design_quality_multiplier == pytest.approx(1.00)


def test_surrogate_tier():
    s = _signal(endpoint_type="surrogate")
    a = assess_trial_design(s)
    assert a.design_quality_tier == DesignQualityTier.SURROGATE
    assert a.design_quality_multiplier == pytest.approx(0.85)


def test_single_arm_via_randomization_field():
    s = _signal(randomization="single_arm", endpoint_type="pfs")
    a = assess_trial_design(s)
    # SINGLE_ARM overrides PFS endpoint
    assert a.design_quality_tier == DesignQualityTier.SINGLE_ARM
    assert a.design_quality_multiplier == pytest.approx(0.80)


def test_single_arm_via_comparator_none():
    s = _signal(comparator_type="none", endpoint_type="os", randomization="randomized")
    a = assess_trial_design(s)
    # SINGLE_ARM (no comparator) overrides OS_RCT
    assert a.design_quality_tier == DesignQualityTier.SINGLE_ARM
    assert a.design_quality_multiplier == pytest.approx(0.80)


def test_single_arm_with_os_endpoint_still_single_arm():
    """Single-arm trial with OS endpoint → SINGLE_ARM, not OS_RCT."""
    s = _signal(randomization="single_arm", endpoint_type="os")
    a = assess_trial_design(s)
    assert a.design_quality_tier == DesignQualityTier.SINGLE_ARM


def test_standard_tier_fallback():
    s = _signal()  # no endpoint_type, no randomization
    a = assess_trial_design(s)
    assert a.design_quality_tier == DesignQualityTier.STANDARD
    assert a.design_quality_multiplier == pytest.approx(1.00)


def test_standard_tier_other_endpoint():
    s = _signal(endpoint_type="other")
    a = assess_trial_design(s)
    assert a.design_quality_tier == DesignQualityTier.STANDARD


# ---------------------------------------------------------------------------
# Statistical power computation
# ---------------------------------------------------------------------------


def _expected_power(n: int, effect: float, alpha: float) -> float:
    z_alpha = norm.ppf(1.0 - alpha / 2.0)
    return max(0.0, min(1.0, float(norm.cdf(abs(effect) * math.sqrt(n / 2.0) - z_alpha))))


def test_power_computed_correctly():
    s = _signal(n_patients=100, estimated_effect_size=0.5, alpha_level=0.05)
    a = assess_trial_design(s)
    assert a.power_computed is True
    assert a.statistical_power == pytest.approx(_expected_power(100, 0.5, 0.05), abs=1e-6)


def test_power_high_enough_no_flag():
    # Large n → high power, no alert
    s = _signal(n_patients=400, estimated_effect_size=0.5, alpha_level=0.05)
    a = assess_trial_design(s)
    assert a.power_computed is True
    assert a.statistical_power >= LOW_POWER_THRESHOLD
    assert a.low_power_flag is False


def test_power_below_threshold_sets_flag():
    # Tiny n → low power
    s = _signal(n_patients=10, estimated_effect_size=0.2, alpha_level=0.05)
    a = assess_trial_design(s)
    assert a.power_computed is True
    assert a.statistical_power < LOW_POWER_THRESHOLD
    assert a.low_power_flag is True


def test_power_uses_two_sided_alpha():
    """Power must use alpha/2, not alpha. Verify against reference formula."""
    s = _signal(n_patients=200, estimated_effect_size=0.3, alpha_level=0.05)
    a = assess_trial_design(s)
    expected = _expected_power(200, 0.3, 0.05)
    assert a.statistical_power == pytest.approx(expected, abs=1e-6)


def test_power_clamped_to_unit_interval():
    # Very large effect size shouldn't produce power > 1
    s = _signal(n_patients=10000, estimated_effect_size=10.0, alpha_level=0.05)
    a = assess_trial_design(s)
    assert 0.0 <= a.statistical_power <= 1.0


def test_power_inputs_recorded():
    s = _signal(n_patients=80, estimated_effect_size=0.4, alpha_level=0.05)
    a = assess_trial_design(s)
    assert a.power_inputs == {"n_patients": 80, "effect_size": 0.4, "alpha": 0.05}


def test_power_not_computed_missing_n():
    s = _signal(estimated_effect_size=0.5, alpha_level=0.05)
    a = assess_trial_design(s)
    assert a.power_computed is False
    assert a.statistical_power is None
    assert a.low_power_flag is False


def test_power_not_computed_missing_effect_size():
    s = _signal(n_patients=100, alpha_level=0.05)
    a = assess_trial_design(s)
    assert a.power_computed is False


def test_power_not_computed_missing_alpha():
    s = _signal(n_patients=100, estimated_effect_size=0.5)
    a = assess_trial_design(s)
    assert a.power_computed is False


def test_power_not_computed_n_zero():
    """n_patients=0 is rejected by the StructuredSignal schema (gt=0)."""
    with pytest.raises(ValidationError):
        _signal(n_patients=0)


def test_power_inputs_empty_when_not_computed():
    s = _signal()
    a = assess_trial_design(s)
    assert a.power_inputs == {}


# ---------------------------------------------------------------------------
# make_low_power_alert
# ---------------------------------------------------------------------------


def test_make_low_power_alert_returns_alert():
    s = _signal(n_patients=10, estimated_effect_size=0.2, alpha_level=0.05)
    a = assess_trial_design(s)
    assert a.low_power_flag is True
    alert = make_low_power_alert(a, company_id="company-001")
    assert isinstance(alert, Alert)


def test_make_low_power_alert_severity_high():
    s = _signal(n_patients=10, estimated_effect_size=0.2, alpha_level=0.05)
    a = assess_trial_design(s)
    alert = make_low_power_alert(a, company_id="company-001")
    assert alert.severity == AlertSeverity.HIGH


def test_make_low_power_alert_trigger():
    s = _signal(n_patients=10, estimated_effect_size=0.2, alpha_level=0.05)
    a = assess_trial_design(s)
    alert = make_low_power_alert(a, company_id="company-001")
    assert alert.trigger == AlertTrigger.LOW_STATISTICAL_POWER


def test_make_low_power_alert_message_contains_power():
    s = _signal(n_patients=10, estimated_effect_size=0.2, alpha_level=0.05)
    a = assess_trial_design(s)
    alert = make_low_power_alert(a, company_id="company-001")
    assert str(round(a.statistical_power, 2)) in alert.message
    assert str(LOW_POWER_THRESHOLD) in alert.message


def test_make_low_power_alert_raises_when_flag_false():
    s = _signal(n_patients=400, estimated_effect_size=0.5, alpha_level=0.05)
    a = assess_trial_design(s)
    assert a.low_power_flag is False
    with pytest.raises(ValueError, match="low_power_flag=False"):
        make_low_power_alert(a, company_id="company-001")


def test_make_low_power_alert_detail_fields():
    s = _signal(n_patients=10, estimated_effect_size=0.2, alpha_level=0.05)
    a = assess_trial_design(s)
    alert = make_low_power_alert(a, company_id="company-001")
    assert alert.detail["signal_id"] == "sig-001"
    assert alert.detail["threshold"] == LOW_POWER_THRESHOLD
    assert "power_inputs" in alert.detail
