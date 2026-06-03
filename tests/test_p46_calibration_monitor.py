"""
Tests for P4.6 — ECE/Brier monitoring + governance + recalibration schedule.

Verifies:
- CalibrationMonitor.compute returns CalibrationReport
- CalibrationReport has ece, brier_score, n_samples, calibration_bins
- ECE computed from binned confidence-accuracy data
- Brier score = mean((conf - outcome)^2)
- Perfect calibration (conf=outcome for all) → Brier ≈ 0, ECE ≈ 0
- Worst calibration (conf=1, outcome=0) → Brier = 1.0
- RecalibrationRecommendation returned with action and urgency
- action is one of: "no_action", "monitor", "recalibrate", "urgent_recalibrate"
- Recommendation.urgency is one of: "none", "low", "medium", "high"
- High ECE (>0.15) triggers "recalibrate" or "urgent_recalibrate"
- Low ECE (<0.05) triggers "no_action"
- CalibrationBin has lower, upper, avg_confidence, avg_outcome, n_samples, gap
- CalibrationReport.reliability_diagram_data returns list of (conf, acc) tuples
- n_bins configurable
- Empty samples raises ValueError
- n_samples < min_samples → RecalibrationRecommendation with "insufficient_data" reason
- GovernanceLog.record writes an entry
- GovernanceLog.entries returns list of logged entries
- RecalibrationSchedule.is_due returns bool based on last run date
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from bve.ops.calibration_monitor import (
    CalibrationBin,
    CalibrationMonitor,
    CalibrationReport,
    GovernanceLog,
    GovernanceLogEntry,
    RecalibrationRecommendation,
    RecalibrationSchedule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _perfect_samples(n: int = 20) -> tuple[list[float], list[float]]:
    """Confidence equals outcome: well-calibrated."""
    confs = [i / (n - 1) for i in range(n)]
    outcomes = confs[:]  # float outcomes (0 or 1 in practice)
    return confs, outcomes


def _overconfident_samples(n: int = 20) -> tuple[list[float], list[float]]:
    """Confidence always 0.9, outcome always 0."""
    return [0.9] * n, [0.0] * n


def _underconfident_samples(n: int = 20) -> tuple[list[float], list[float]]:
    """Confidence always 0.3, outcome always 1.0."""
    return [0.3] * n, [1.0] * n


# ---------------------------------------------------------------------------
# CalibrationBin
# ---------------------------------------------------------------------------

class TestCalibrationBin:
    def test_has_required_fields(self):
        b = CalibrationBin(lower=0.0, upper=0.2, avg_confidence=0.1,
                           avg_outcome=0.1, n_samples=5, gap=0.0)
        assert b.lower == 0.0
        assert b.upper == 0.2
        assert b.n_samples == 5

    def test_gap_formula(self):
        b = CalibrationBin(lower=0.4, upper=0.6, avg_confidence=0.5,
                           avg_outcome=0.3, n_samples=10, gap=0.2)
        assert b.gap == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# CalibrationMonitor.compute
# ---------------------------------------------------------------------------

class TestCalibrationMonitor:
    def test_returns_calibration_report(self):
        confs, outcomes = _perfect_samples()
        report = CalibrationMonitor().compute(confs, outcomes)
        assert isinstance(report, CalibrationReport)

    def test_n_samples(self):
        confs, outcomes = _perfect_samples(30)
        report = CalibrationMonitor().compute(confs, outcomes)
        assert report.n_samples == 30

    def test_brier_score_perfect(self):
        """Perfect calibration: conf=outcome=0 or 1 → Brier=0."""
        confs = [0.0] * 10 + [1.0] * 10
        outcomes = [0.0] * 10 + [1.0] * 10
        report = CalibrationMonitor().compute(confs, outcomes)
        assert report.brier_score == pytest.approx(0.0, abs=0.01)

    def test_brier_score_worst(self):
        """Worst: conf=1, outcome=0 → Brier=1."""
        confs = [1.0] * 20
        outcomes = [0.0] * 20
        report = CalibrationMonitor().compute(confs, outcomes)
        assert report.brier_score == pytest.approx(1.0, abs=0.01)

    def test_ece_near_zero_for_perfect_calibration(self):
        confs = [0.0] * 10 + [1.0] * 10
        outcomes = [0.0] * 10 + [1.0] * 10
        report = CalibrationMonitor().compute(confs, outcomes)
        assert report.ece < 0.05

    def test_ece_high_for_overconfident(self):
        confs, outcomes = _overconfident_samples()
        report = CalibrationMonitor().compute(confs, outcomes)
        assert report.ece > 0.10  # 90% confidence, 0% outcome

    def test_calibration_bins_returned(self):
        confs, outcomes = _perfect_samples()
        report = CalibrationMonitor().compute(confs, outcomes)
        assert isinstance(report.calibration_bins, list)
        assert len(report.calibration_bins) >= 1

    def test_bins_cover_range(self):
        confs, outcomes = _perfect_samples()
        report = CalibrationMonitor(n_bins=5).compute(confs, outcomes)
        non_empty = [b for b in report.calibration_bins if b.n_samples > 0]
        assert len(non_empty) >= 1

    def test_reliability_diagram_data(self):
        confs, outcomes = _perfect_samples()
        report = CalibrationMonitor().compute(confs, outcomes)
        diagram = report.reliability_diagram_data()
        assert isinstance(diagram, list)
        for conf, acc in diagram:
            assert 0.0 <= conf <= 1.0
            assert 0.0 <= acc <= 1.0

    def test_empty_samples_raises(self):
        with pytest.raises(ValueError, match="empty"):
            CalibrationMonitor().compute([], [])

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            CalibrationMonitor().compute([0.5, 0.7], [1.0])

    def test_n_bins_configurable(self):
        confs, outcomes = _perfect_samples(40)
        report5 = CalibrationMonitor(n_bins=5).compute(confs, outcomes)
        report10 = CalibrationMonitor(n_bins=10).compute(confs, outcomes)
        assert len(report5.calibration_bins) == 5
        assert len(report10.calibration_bins) == 10


# ---------------------------------------------------------------------------
# RecalibrationRecommendation
# ---------------------------------------------------------------------------

class TestRecalibrationRecommendation:
    def test_no_action_for_low_ece(self):
        confs = [0.0] * 10 + [1.0] * 10
        outcomes = [0.0] * 10 + [1.0] * 10
        report = CalibrationMonitor().compute(confs, outcomes)
        rec = report.recommendation()
        assert rec.action in ("no_action", "monitor")

    def test_recalibrate_for_high_ece(self):
        confs, outcomes = _overconfident_samples(40)
        report = CalibrationMonitor().compute(confs, outcomes)
        rec = report.recommendation()
        assert rec.action in ("recalibrate", "urgent_recalibrate")

    def test_recommendation_has_urgency(self):
        confs, outcomes = _overconfident_samples(40)
        report = CalibrationMonitor().compute(confs, outcomes)
        rec = report.recommendation()
        assert rec.urgency in ("none", "low", "medium", "high")

    def test_recommendation_has_reason(self):
        confs, outcomes = _overconfident_samples(40)
        report = CalibrationMonitor().compute(confs, outcomes)
        rec = report.recommendation()
        assert isinstance(rec.reason, str) and len(rec.reason) > 5

    def test_insufficient_data_reason(self):
        confs, outcomes = _perfect_samples(3)  # only 3 samples
        report = CalibrationMonitor(min_samples=10).compute(confs, outcomes)
        rec = report.recommendation()
        assert "insufficient" in rec.reason.lower() or rec.action == "monitor"


# ---------------------------------------------------------------------------
# GovernanceLog
# ---------------------------------------------------------------------------

class TestGovernanceLog:
    def test_record_adds_entry(self):
        log = GovernanceLog()
        log.record(event="recalibration_run", detail="ECE=0.08, Brier=0.12")
        assert len(log.entries()) == 1

    def test_entry_has_required_fields(self):
        log = GovernanceLog()
        log.record(event="model_update", detail="POS prior adjusted")
        entry = log.entries()[0]
        assert isinstance(entry, GovernanceLogEntry)
        assert entry.event == "model_update"
        assert len(entry.detail) > 0
        assert entry.logged_at is not None

    def test_multiple_entries_stored(self):
        log = GovernanceLog()
        log.record("a", "detail a")
        log.record("b", "detail b")
        assert len(log.entries()) == 2

    def test_entries_ordered_by_time(self):
        log = GovernanceLog()
        log.record("first", "d1")
        log.record("second", "d2")
        entries = log.entries()
        assert entries[0].event == "first"
        assert entries[1].event == "second"


# ---------------------------------------------------------------------------
# RecalibrationSchedule
# ---------------------------------------------------------------------------

class TestRecalibrationSchedule:
    def test_is_due_when_never_run(self):
        schedule = RecalibrationSchedule(cadence_days=30)
        assert schedule.is_due(last_run=None) is True

    def test_is_due_when_overdue(self):
        schedule = RecalibrationSchedule(cadence_days=30)
        last_run = date.today() - timedelta(days=45)
        assert schedule.is_due(last_run=last_run) is True

    def test_not_due_when_recent(self):
        schedule = RecalibrationSchedule(cadence_days=30)
        last_run = date.today() - timedelta(days=10)
        assert schedule.is_due(last_run=last_run) is False

    def test_next_due_date(self):
        schedule = RecalibrationSchedule(cadence_days=30)
        last_run = date.today() - timedelta(days=10)
        next_due = schedule.next_due(last_run=last_run)
        assert next_due == last_run + timedelta(days=30)

    def test_next_due_none_returns_today(self):
        schedule = RecalibrationSchedule(cadence_days=30)
        next_due = schedule.next_due(last_run=None)
        assert next_due == date.today()
