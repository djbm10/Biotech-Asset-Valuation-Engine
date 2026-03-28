"""Tests for Wave 3B — Forecast Tracking."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from bve.intelligence.forecast_tracker import (
    ForecastRecord,
    CalibrationReport,
    CalibrationReporter,
    _infer_direction,
    _infer_delta_pct,
    record_forecast,
    resolve_forecasts,
)
from bve.intelligence.knowledge_layer import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    ks = KnowledgeStore(db_path=":memory:")
    yield ks
    ks.close()


def _make_signal(
    signal_id: str = "sig-001",
    event_id: str = "ev-001",
    asset_id: str = "asset-001",
    event_type: str = "trial_readout",
    signal_date: str = "2024-06-01",
    extraction_confidence: float = 0.8,
    primary_endpoint_met: Any = None,
    fda_action_type: Any = None,
) -> MagicMock:
    s = MagicMock()
    s.id = signal_id
    s.event_id = event_id
    s.asset_id = asset_id
    s.event_type = event_type
    s.signal_date = date.fromisoformat(signal_date)
    s.extraction_confidence = extraction_confidence
    s.primary_endpoint_met = primary_endpoint_met
    s.fda_action_type = fda_action_type
    return s


def _make_diff(delta_npv: float = 10.0, before_npv: float = 100.0) -> MagicMock:
    d = MagicMock()
    d.delta_npv = delta_npv
    d.valuation_before = {"rnpv_millions": before_npv}
    d.valuation_delta = {}
    return d


def _seed_outcome(
    store: KnowledgeStore,
    event_id: str = "ev-001",
    market_return_t30: float = 0.10,
    resolved_t30: int = 1,
    market_return_t180: float = None,
    resolved_t180: int = 0,
) -> None:
    store._conn.execute(
        """
        INSERT OR IGNORE INTO event_outcomes
            (outcome_id, event_id, asset_id, event_type, signal_date,
             market_return_t30, resolved_t30, market_return_t180, resolved_t180,
             fully_resolved, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"oc-{event_id}", event_id, "asset-001", "trial_readout", "2024-06-01",
            market_return_t30, resolved_t30, market_return_t180, resolved_t180,
            0, datetime.now(timezone.utc).isoformat(),
        ),
    )
    store._conn.commit()


# ---------------------------------------------------------------------------
# ForecastRecord model
# ---------------------------------------------------------------------------


def test_forecast_record_auto_uuid():
    r1 = ForecastRecord(
        signal_id="s", event_id="e", asset_id="a",
        event_type="trial_readout", signal_date="2024-01-01",
        predicted_direction="up",
    )
    r2 = ForecastRecord(
        signal_id="s2", event_id="e2", asset_id="a",
        event_type="trial_readout", signal_date="2024-01-01",
        predicted_direction="up",
    )
    assert r1.forecast_id != r2.forecast_id


def test_forecast_record_defaults():
    r = ForecastRecord(
        signal_id="s", event_id="e", asset_id="a",
        event_type="trial_readout", signal_date="2024-01-01",
        predicted_direction="neutral",
    )
    assert r.predicted_delta_pct is None
    assert r.actual_market_return_t30 is None
    assert r.outcome_correct is None
    assert r.resolved is False
    assert r.extraction_confidence == 0.0


# ---------------------------------------------------------------------------
# _infer_direction
# ---------------------------------------------------------------------------


def test_infer_direction_primary_endpoint_met_true():
    sig = _make_signal(primary_endpoint_met=True)
    diff = _make_diff()
    assert _infer_direction(sig, diff) == "up"


def test_infer_direction_primary_endpoint_met_false():
    sig = _make_signal(primary_endpoint_met=False)
    diff = _make_diff()
    assert _infer_direction(sig, diff) == "down"


def test_infer_direction_fda_approval():
    sig = _make_signal(fda_action_type="approval")
    diff = _make_diff()
    assert _infer_direction(sig, diff) == "up"


def test_infer_direction_fda_crl():
    sig = _make_signal(fda_action_type="crl")
    diff = _make_diff()
    assert _infer_direction(sig, diff) == "down"


def test_infer_direction_fda_hold():
    sig = _make_signal(fda_action_type="hold")
    diff = _make_diff()
    assert _infer_direction(sig, diff) == "down"


def test_infer_direction_falls_back_to_delta_npv_positive():
    sig = _make_signal()
    sig.primary_endpoint_met = None
    sig.fda_action_type = None
    diff = _make_diff(delta_npv=5.0)
    assert _infer_direction(sig, diff) == "up"


def test_infer_direction_falls_back_to_delta_npv_negative():
    sig = _make_signal()
    sig.primary_endpoint_met = None
    sig.fda_action_type = None
    diff = _make_diff(delta_npv=-5.0)
    assert _infer_direction(sig, diff) == "down"


def test_infer_direction_neutral_when_zero():
    sig = _make_signal()
    sig.primary_endpoint_met = None
    sig.fda_action_type = None
    diff = _make_diff(delta_npv=0.0)
    assert _infer_direction(sig, diff) == "neutral"


def test_infer_direction_primary_endpoint_takes_priority_over_delta():
    """primary_endpoint_met=True wins even if delta_npv is negative."""
    sig = _make_signal(primary_endpoint_met=True)
    diff = _make_diff(delta_npv=-50.0)
    assert _infer_direction(sig, diff) == "up"


# ---------------------------------------------------------------------------
# _infer_delta_pct
# ---------------------------------------------------------------------------


def test_infer_delta_pct_from_valuation_delta():
    diff = _make_diff()
    diff.valuation_delta = {"npv_delta_pct": 12.5}
    assert abs(_infer_delta_pct(diff) - 12.5) < 1e-9


def test_infer_delta_pct_from_delta_npv_and_before():
    diff = _make_diff(delta_npv=10.0, before_npv=100.0)
    result = _infer_delta_pct(diff)
    assert abs(result - 10.0) < 1e-9  # 10/100 * 100 = 10%


def test_infer_delta_pct_none_when_no_before_npv():
    diff = _make_diff(delta_npv=5.0)
    diff.valuation_before = {}
    diff.valuation_delta = {}
    result = _infer_delta_pct(diff)
    assert result is None


# ---------------------------------------------------------------------------
# KnowledgeStore — record_forecast / get_forecast
# ---------------------------------------------------------------------------


def test_record_forecast_stores(store):
    rec = ForecastRecord(
        signal_id="sig-001", event_id="ev-001", asset_id="asset-001",
        event_type="trial_readout", signal_date="2024-06-01",
        extraction_confidence=0.85, predicted_direction="up",
        predicted_delta_pct=8.0,
    )
    store.record_forecast(rec)
    retrieved = store.get_forecast(rec.forecast_id)
    assert retrieved is not None
    assert retrieved["signal_id"] == "sig-001"
    assert retrieved["predicted_direction"] == "up"
    assert abs(retrieved["predicted_delta_pct"] - 8.0) < 1e-9


def test_record_forecast_idempotent(store):
    """Second call for same signal_id is silently ignored."""
    rec = ForecastRecord(
        signal_id="sig-001", event_id="ev-001", asset_id="asset-001",
        event_type="trial_readout", signal_date="2024-06-01",
        predicted_direction="up",
    )
    store.record_forecast(rec)
    store.record_forecast(rec)  # duplicate
    rows = store._conn.execute("SELECT * FROM forecast_records").fetchall()
    assert len(rows) == 1


def test_get_forecast_returns_none_when_missing(store):
    assert store.get_forecast("nonexistent") is None


def test_get_forecast_by_signal(store):
    rec = ForecastRecord(
        signal_id="sig-002", event_id="ev-002", asset_id="asset-001",
        event_type="fda_approval", signal_date="2024-07-01",
        predicted_direction="up",
    )
    store.record_forecast(rec)
    retrieved = store.get_forecast_by_signal("sig-002")
    assert retrieved is not None
    assert retrieved["event_type"] == "fda_approval"


# ---------------------------------------------------------------------------
# record_forecast() hook (integration)
# ---------------------------------------------------------------------------


def test_record_forecast_hook_writes_row(store):
    sig = _make_signal(primary_endpoint_met=True)
    diff = _make_diff(delta_npv=15.0, before_npv=100.0)
    rec = record_forecast(sig, diff, store)
    assert rec.predicted_direction == "up"
    stored = store.get_forecast_by_signal("sig-001")
    assert stored is not None
    assert stored["predicted_direction"] == "up"


def test_record_forecast_hook_infers_delta_pct(store):
    sig = _make_signal()
    sig.primary_endpoint_met = None
    sig.fda_action_type = None
    diff = _make_diff(delta_npv=20.0, before_npv=200.0)
    rec = record_forecast(sig, diff, store)
    assert abs(rec.predicted_delta_pct - 10.0) < 1e-9


# ---------------------------------------------------------------------------
# resolve_forecasts
# ---------------------------------------------------------------------------


def test_resolve_forecasts_fills_actual_return(store):
    rec = ForecastRecord(
        signal_id="sig-001", event_id="ev-001", asset_id="asset-001",
        event_type="trial_readout", signal_date="2024-06-01",
        predicted_direction="up",
    )
    store.record_forecast(rec)
    _seed_outcome(store, event_id="ev-001", market_return_t30=0.12)
    updated = resolve_forecasts(store)
    assert updated == 1
    row = store.get_forecast(rec.forecast_id)
    assert abs(row["actual_market_return_t30"] - 0.12) < 1e-9
    assert row["resolved"] == 1


def test_resolve_forecasts_sets_outcome_correct_true(store):
    rec = ForecastRecord(
        signal_id="sig-001", event_id="ev-001", asset_id="asset-001",
        event_type="trial_readout", signal_date="2024-06-01",
        predicted_direction="up",
    )
    store.record_forecast(rec)
    _seed_outcome(store, event_id="ev-001", market_return_t30=0.05)
    resolve_forecasts(store)
    row = store.get_forecast(rec.forecast_id)
    assert row["outcome_correct"] == 1


def test_resolve_forecasts_sets_outcome_correct_false(store):
    rec = ForecastRecord(
        signal_id="sig-001", event_id="ev-001", asset_id="asset-001",
        event_type="trial_readout", signal_date="2024-06-01",
        predicted_direction="up",
    )
    store.record_forecast(rec)
    _seed_outcome(store, event_id="ev-001", market_return_t30=-0.15)
    resolve_forecasts(store)
    row = store.get_forecast(rec.forecast_id)
    assert row["outcome_correct"] == 0


def test_resolve_forecasts_idempotent(store):
    rec = ForecastRecord(
        signal_id="sig-001", event_id="ev-001", asset_id="asset-001",
        event_type="trial_readout", signal_date="2024-06-01",
        predicted_direction="up",
    )
    store.record_forecast(rec)
    _seed_outcome(store, event_id="ev-001", market_return_t30=0.05)
    resolve_forecasts(store)
    n = resolve_forecasts(store)  # second call — already resolved
    assert n == 0


def test_resolve_forecasts_skips_unresolved_outcomes(store):
    rec = ForecastRecord(
        signal_id="sig-001", event_id="ev-001", asset_id="asset-001",
        event_type="trial_readout", signal_date="2024-06-01",
        predicted_direction="up",
    )
    store.record_forecast(rec)
    _seed_outcome(store, event_id="ev-001", market_return_t30=0.05, resolved_t30=0)
    n = resolve_forecasts(store)
    assert n == 0


# ---------------------------------------------------------------------------
# CalibrationReporter
# ---------------------------------------------------------------------------


def _seed_resolved_forecast(
    store: KnowledgeStore,
    signal_id: str,
    event_id: str,
    predicted_direction: str,
    actual_return: float,
    predicted_delta_pct: float = None,
    confidence: float = 0.8,
) -> None:
    rec = ForecastRecord(
        signal_id=signal_id, event_id=event_id, asset_id="asset-001",
        event_type="trial_readout", signal_date="2024-06-01",
        extraction_confidence=confidence,
        predicted_direction=predicted_direction,
        predicted_delta_pct=predicted_delta_pct,
    )
    store.record_forecast(rec)
    _seed_outcome(store, event_id=event_id, market_return_t30=actual_return)
    resolve_forecasts(store)


def test_calibration_reporter_empty_store():
    ks = KnowledgeStore(db_path=":memory:")
    report = CalibrationReporter().report(ks)
    ks.close()
    assert report.n_total == 0
    assert report.n_resolved == 0
    assert report.directional_accuracy is None


def test_calibration_reporter_directional_accuracy(store):
    _seed_resolved_forecast(store, "s1", "e1", "up", 0.10)
    _seed_resolved_forecast(store, "s2", "e2", "down", -0.20)
    _seed_resolved_forecast(store, "s3", "e3", "up", -0.05)  # wrong
    report = CalibrationReporter().report(store)
    assert report.n_resolved == 3
    assert abs(report.directional_accuracy - 2 / 3) < 1e-9


def test_calibration_reporter_false_positive_rate(store):
    # 2 predicted up: 1 correct, 1 false positive
    _seed_resolved_forecast(store, "s1", "e1", "up", 0.10)
    _seed_resolved_forecast(store, "s2", "e2", "up", -0.15)
    _seed_resolved_forecast(store, "s3", "e3", "down", -0.10)
    report = CalibrationReporter().report(store)
    assert abs(report.false_positive_rate - 0.5) < 1e-9


def test_calibration_reporter_magnitude_rmse(store):
    """Two forecasts: pred 10%, actual 10% (perfect) → RMSE = 0."""
    _seed_resolved_forecast(store, "s1", "e1", "up", 0.10, predicted_delta_pct=10.0)
    _seed_resolved_forecast(store, "s2", "e2", "up", 0.10, predicted_delta_pct=10.0)
    report = CalibrationReporter().report(store)
    assert report.magnitude_rmse is not None
    assert abs(report.magnitude_rmse) < 1e-9


def test_calibration_reporter_confidence_bins_populated(store):
    _seed_resolved_forecast(store, "s1", "e1", "up", 0.10, confidence=0.9)
    _seed_resolved_forecast(store, "s2", "e2", "down", -0.10, confidence=0.9)
    report = CalibrationReporter().report(store)
    assert len(report.confidence_bins) == 10
    nonempty = [b for b in report.confidence_bins if b.n_forecasts > 0]
    assert len(nonempty) >= 1


def test_calibration_reporter_coverage_all_resolved(store):
    _seed_resolved_forecast(store, "s1", "e1", "up", 0.10)
    _seed_resolved_forecast(store, "s2", "e2", "down", -0.10)
    report = CalibrationReporter().report(store)
    assert report.coverage is not None
    assert abs(report.coverage - 1.0) < 1e-9


def test_calibration_reporter_coverage_partial(store):
    """Two forecasts, one resolved → coverage = 0.5."""
    # Resolved forecast
    _seed_resolved_forecast(store, "s1", "e1", "up", 0.10)
    # Unresolved forecast (no matching event_outcome)
    rec = ForecastRecord(
        signal_id="s2", event_id="ev-unresolved", asset_id="asset-001",
        event_type="trial_readout", signal_date="2024-06-01",
        predicted_direction="down",
    )
    store.record_forecast(rec)
    report = CalibrationReporter().report(store)
    assert abs(report.coverage - 0.5) < 1e-9


def test_calibration_reporter_coverage_none_when_no_forecasts():
    ks = KnowledgeStore(db_path=":memory:")
    report = CalibrationReporter().report(ks)
    ks.close()
    assert report.coverage is None


# ---------------------------------------------------------------------------
# Task 9.17 — Calibration status flag (Sprint 9 Phase 4)
# ---------------------------------------------------------------------------

def test_calibration_status_uncalibrated_when_below_threshold(store):
    """Report is 'uncalibrated' when fewer than 200 labeled outcomes exist."""
    _seed_resolved_forecast(store, "s1", "e1", "up", 0.10)
    report = CalibrationReporter().report(store)
    assert report.confidence_calibration_status == "uncalibrated"
    assert report.confidence_calibration_n_required == 200


def test_calibration_status_uncalibrated_on_empty_store():
    """Empty store → report shows uncalibrated status."""
    ks = KnowledgeStore(db_path=":memory:")
    report = CalibrationReporter().report(ks)
    ks.close()
    assert report.confidence_calibration_status == "uncalibrated"


def test_calibration_report_has_status_fields():
    """CalibrationReport model always exposes the calibration status fields."""
    report = CalibrationReport(n_total=0, n_resolved=0)
    assert hasattr(report, "confidence_calibration_status")
    assert hasattr(report, "confidence_calibration_n_required")
    assert report.confidence_calibration_status == "uncalibrated"
    assert report.confidence_calibration_n_required == 200
