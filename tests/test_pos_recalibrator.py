"""Tests for Wave E — PoS Recalibration Loop."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from bve.analysis.pos_recalibrator import (
    MIN_SEGMENT_OBS,
    PRIOR_ESS,
    PoSCalibrationReport,
    PoSRecalibrator,
    SegmentCalibration,
)
from bve.intelligence.knowledge_layer import KnowledgeStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store() -> KnowledgeStore:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return KnowledgeStore(tmp.name)


def _insert_forecast(
    store: KnowledgeStore,
    *,
    trial_phase: str,
    indication: str,
    outcome_correct: int,
    n: int = 1,
) -> None:
    """Insert n synthetic resolved forecast_records."""
    now = datetime.now(timezone.utc).isoformat()
    import uuid as _uuid
    for i in range(n):
        uid = str(_uuid.uuid4())[:8]
        store._conn.execute(
            """
            INSERT INTO forecast_records
                (forecast_id, signal_id, event_id, asset_id, event_type,
                 signal_date, trial_phase, indication, predicted_direction,
                 outcome_correct, actual_market_return_t30, resolved,
                 predicted_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                f"fc-{uid}",
                f"sig-{uid}",
                f"evt-{uid}",
                f"asset-{indication}-{uid}",
                "trial_readout",
                "2025-06-01",
                trial_phase,
                indication,
                "up" if outcome_correct else "down",
                outcome_correct,
                0.20 if outcome_correct else -0.15,
                now,
                now,
            ),
        )
    store._conn.commit()


# ---------------------------------------------------------------------------
# SegmentCalibration model
# ---------------------------------------------------------------------------

def test_segment_calibration_fields() -> None:
    seg = SegmentCalibration(
        trial_phase="phase_2",
        indication="oncology",
        n_observations=20,
        n_correct=8,
        empirical_success_rate=0.40,
        prior_rate=0.32,
        updated_rate=0.34,
        updated_from_data=True,
        drift_pct=6.25,
    )
    assert seg.trial_phase == "phase_2"
    assert seg.updated_from_data is True


# ---------------------------------------------------------------------------
# Empty store
# ---------------------------------------------------------------------------

def test_calibrate_empty_store() -> None:
    store = _make_store()
    try:
        calibrator = PoSRecalibrator(store)
        report = calibrator.calibrate()
        assert report.n_resolved_forecasts == 0
        assert report.n_segments == 0
        assert report.segments == []
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Below-minimum segment — prior preserved
# ---------------------------------------------------------------------------

def test_below_minimum_preserves_prior() -> None:
    store = _make_store()
    try:
        # Insert only 5 resolved forecasts (< MIN_SEGMENT_OBS=15)
        _insert_forecast(store, trial_phase="phase_2", indication="oncology",
                         outcome_correct=1, n=5)
        calibrator = PoSRecalibrator(store)
        report = calibrator.calibrate()
        assert len(report.segments) == 1
        seg = report.segments[0]
        assert not seg.updated_from_data
        # Updated rate should equal prior
        assert abs(seg.updated_rate - seg.prior_rate) < 1e-9
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Sufficient data — Bayesian update
# ---------------------------------------------------------------------------

def test_sufficient_data_updates_rate() -> None:
    store = _make_store()
    try:
        # 15 observations, 10 correct → empirical = 0.667
        _insert_forecast(store, trial_phase="phase_3", indication="all",
                         outcome_correct=1, n=10)
        _insert_forecast(store, trial_phase="phase_3", indication="all",
                         outcome_correct=0, n=5)
        calibrator = PoSRecalibrator(store)
        report = calibrator.calibrate()
        seg = next(s for s in report.segments if s.trial_phase == "phase_3")
        assert seg.updated_from_data is True
        assert seg.n_observations == 15
        assert seg.n_correct == 10
        # Prior for phase_3/all = 0.60
        # Beta update: (0.60×50 + 10) / (50 + 15) = (30+10)/65 = 40/65 ≈ 0.615
        expected = (0.60 * 50 + 10) / (50 + 15)
        assert abs(seg.updated_rate - expected) < 0.01
    finally:
        store.close()


def test_updated_rate_between_prior_and_empirical() -> None:
    """Bayesian update should shrink toward prior."""
    store = _make_store()
    try:
        # 20 all-correct records → empirical = 1.0
        _insert_forecast(store, trial_phase="phase_2", indication="all",
                         outcome_correct=1, n=20)
        calibrator = PoSRecalibrator(store)
        report = calibrator.calibrate()
        seg = next(s for s in report.segments if s.trial_phase == "phase_2")
        # Updated should be between prior (0.37) and 1.0
        assert seg.updated_rate > seg.prior_rate
        assert seg.updated_rate < 1.0
    finally:
        store.close()


def test_updated_rate_bounded() -> None:
    """Updated rate must be in (0.01, 0.99)."""
    store = _make_store()
    try:
        _insert_forecast(store, trial_phase="phase_1", indication="all",
                         outcome_correct=1, n=100)
        calibrator = PoSRecalibrator(store)
        report = calibrator.calibrate()
        for seg in report.segments:
            assert 0.01 <= seg.updated_rate <= 0.99
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Drift alert
# ---------------------------------------------------------------------------

def test_drift_alert_fired_when_large_shift() -> None:
    store = _make_store()
    try:
        # Make empirical rate very high for a low-prior phase
        _insert_forecast(store, trial_phase="phase_2", indication="all",
                         outcome_correct=1, n=100)
        _insert_forecast(store, trial_phase="phase_2", indication="all",
                         outcome_correct=0, n=5)
        calibrator = PoSRecalibrator(store, prior_ess=1.0)   # weak prior → large update
        report = calibrator.calibrate()
        # With very weak prior (ess=1), empirical dominates → drift > 10%
        assert len(report.drift_alerts) >= 1
    finally:
        store.close()


def test_no_drift_alert_when_stable() -> None:
    store = _make_store()
    try:
        # Phase 3 prior = 0.60; push toward same with 50/50 win rate
        _insert_forecast(store, trial_phase="phase_3", indication="all",
                         outcome_correct=1, n=9)
        _insert_forecast(store, trial_phase="phase_3", indication="all",
                         outcome_correct=0, n=6)
        calibrator = PoSRecalibrator(store, prior_ess=50.0)
        report = calibrator.calibrate()
        assert report.drift_alerts == []
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Multiple segments
# ---------------------------------------------------------------------------

def test_multiple_segments_tracked_independently() -> None:
    store = _make_store()
    try:
        _insert_forecast(store, trial_phase="phase_2", indication="oncology",
                         outcome_correct=1, n=20)
        _insert_forecast(store, trial_phase="phase_3", indication="rare_disease",
                         outcome_correct=0, n=20)
        calibrator = PoSRecalibrator(store)
        report = calibrator.calibrate()
        assert report.n_segments == 2
        phases = {s.trial_phase for s in report.segments}
        assert "phase_2" in phases
        assert "phase_3" in phases
    finally:
        store.close()


# ---------------------------------------------------------------------------
# write_calibration
# ---------------------------------------------------------------------------

def test_write_calibration_creates_yaml(tmp_path: Path) -> None:
    store = _make_store()
    try:
        _insert_forecast(store, trial_phase="phase_2", indication="all",
                         outcome_correct=1, n=20)
        out_path = tmp_path / "pos_recalibration.yaml"
        calibrator = PoSRecalibrator(store, calibration_path=out_path)
        report = calibrator.calibrate()
        calibrator.write_calibration(report)
        assert out_path.exists()
        payload = yaml.safe_load(out_path.read_text())
        assert "calibrations" in payload
        assert "run_date" in payload
        assert len(payload["calibrations"]) >= 1
    finally:
        store.close()


def test_write_calibration_round_trip(tmp_path: Path) -> None:
    store = _make_store()
    try:
        _insert_forecast(store, trial_phase="phase_3", indication="oncology",
                         outcome_correct=1, n=20)
        out_path = tmp_path / "pos_recalibration.yaml"
        calibrator = PoSRecalibrator(store, calibration_path=out_path)
        report = calibrator.calibrate()
        calibrator.write_calibration(report)

        payload = yaml.safe_load(out_path.read_text())
        assert payload["n_resolved_forecasts"] == 20
        seg_data = payload["calibrations"][0]
        assert seg_data["trial_phase"] == "phase_3"
        assert seg_data["indication"] == "oncology"
        assert seg_data["updated_from_data"] is True
    finally:
        store.close()


# ---------------------------------------------------------------------------
# PoSCalibrationReport invariants
# ---------------------------------------------------------------------------

def test_report_n_segments_matches_len() -> None:
    store = _make_store()
    try:
        _insert_forecast(store, trial_phase="phase_1", indication="all",
                         outcome_correct=1, n=20)
        calibrator = PoSRecalibrator(store)
        report = calibrator.calibrate()
        assert report.n_segments == len(report.segments)
    finally:
        store.close()
