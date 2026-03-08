"""Tests for Alert model and AlertSeverity ordering."""
from __future__ import annotations

from bve.alerts.alert_model import Alert, AlertSeverity, AlertTrigger, severity_gte


class TestAlertSeverityOrdering:
    def test_low_lt_medium(self):
        assert not severity_gte(AlertSeverity.LOW, AlertSeverity.MEDIUM)

    def test_medium_gte_medium(self):
        assert severity_gte(AlertSeverity.MEDIUM, AlertSeverity.MEDIUM)

    def test_critical_gte_low(self):
        assert severity_gte(AlertSeverity.CRITICAL, AlertSeverity.LOW)

    def test_high_not_gte_critical(self):
        assert not severity_gte(AlertSeverity.HIGH, AlertSeverity.CRITICAL)


class TestAlertModel:
    def test_construction_defaults(self):
        alert = Alert(
            severity=AlertSeverity.MEDIUM,
            trigger=AlertTrigger.SAFETY_SIGNAL_DETECTED,
            asset_id="asset-001",
            company_id="company-001",
            message="Test alert",
        )
        assert alert.id  # auto-generated
        assert alert.created_at is not None
        assert alert.signal_event_type is None
        assert alert.valuation_delta_npv is None

    def test_frozen(self):
        import pytest
        alert = Alert(
            severity=AlertSeverity.LOW,
            trigger=AlertTrigger.MATERIAL_VALUATION_CHANGE,
            asset_id="a",
            company_id="c",
            message="m",
        )
        with pytest.raises(Exception):
            alert.severity = AlertSeverity.CRITICAL  # type: ignore

    def test_round_trip_json(self):
        alert = Alert(
            severity=AlertSeverity.CRITICAL,
            trigger=AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY,
            asset_id="asset-x",
            company_id="company-x",
            message="test",
            detail={"key": "value"},
            signal_event_type="fda_approval",
            valuation_delta_npv=42.5,
            extraction_confidence=0.35,
        )
        data = alert.model_dump(mode="json")
        restored = Alert.model_validate(data)
        assert restored.severity == AlertSeverity.CRITICAL
        assert restored.trigger == AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY
        assert restored.valuation_delta_npv == 42.5
        assert restored.extraction_confidence == 0.35

    def test_unique_ids(self):
        a1 = Alert(
            severity=AlertSeverity.LOW, trigger=AlertTrigger.MATERIAL_VALUATION_CHANGE,
            asset_id="a", company_id="c", message="m",
        )
        a2 = Alert(
            severity=AlertSeverity.LOW, trigger=AlertTrigger.MATERIAL_VALUATION_CHANGE,
            asset_id="a", company_id="c", message="m",
        )
        assert a1.id != a2.id
