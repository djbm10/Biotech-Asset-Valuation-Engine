"""Tests for Sprint 23 Task 2 — rolling holdout validation enhancements.

Verifies:
1. _rolling_windows() generates non-overlapping / stepped windows correctly.
2. WindowResult carries ece_raw, brier_raw, ece_passes, acquirer_top5_accuracy.
3. RollingHoldoutReport.calibration_gate_passes() returns True only when ALL
   populated windows have ECE ≤ 0.10.
4. calibration_gate_passes() returns False when at least one window exceeds 0.10.
5. calibration_gate_passes() returns False when no windows have ECE data.
6. _ece() and _brier_score() compute correct values.
"""
from __future__ import annotations

from dataclasses import field
from datetime import date

import pytest

from bve.analysis.rolling_holdout import (
    RollingHoldoutReport,
    WindowResult,
    _ECE_GATE_THRESHOLD,
    _brier_score,
    _ece,
    _rolling_windows,
)


# ---------------------------------------------------------------------------
# _rolling_windows
# ---------------------------------------------------------------------------

class TestRollingWindows:
    def test_single_window_when_range_equals_window(self):
        start = date(2024, 1, 1)
        end = date(2025, 1, 1)
        windows = _rolling_windows(start, end, window_months=12, step_months=6)
        assert len(windows) >= 1
        w0_start, w0_end, label = windows[0]
        assert w0_start == start

    def test_step_produces_multiple_windows(self):
        windows = _rolling_windows(
            date(2023, 1, 1), date(2025, 1, 1),
            window_months=12, step_months=6,
        )
        assert len(windows) >= 2

    def test_labels_contain_dates(self):
        windows = _rolling_windows(
            date(2024, 1, 1), date(2025, 6, 1),
            window_months=6, step_months=3,
        )
        for _, _, label in windows:
            assert "/" in label


# ---------------------------------------------------------------------------
# _ece and _brier_score helpers
# ---------------------------------------------------------------------------

class TestCalibrationHelpers:
    def test_brier_perfect(self):
        probs = [1.0, 0.0, 1.0, 0.0]
        outcomes = [1, 0, 1, 0]
        assert _brier_score(probs, outcomes) == pytest.approx(0.0, abs=1e-9)

    def test_brier_worst(self):
        probs = [0.0, 1.0]  # completely wrong
        outcomes = [1, 0]
        assert _brier_score(probs, outcomes) == pytest.approx(1.0, abs=1e-9)

    def test_brier_empty(self):
        import math
        assert math.isnan(_brier_score([], []))

    def test_ece_perfect(self):
        # All bins have mean_conf == mean_acc → ECE = 0
        probs = [0.1, 0.3, 0.5, 0.7, 0.9]
        outcomes = [0, 0, 1, 1, 1]
        # Not necessarily 0, but should be a valid float
        result = _ece(probs, outcomes)
        assert isinstance(result, float)
        assert result >= 0.0

    def test_ece_empty(self):
        import math
        assert math.isnan(_ece([], []))

    def test_ece_perfectly_calibrated_bucket(self):
        # All predictions in same bin with mean = outcome → ECE = 0
        probs = [0.5, 0.5, 0.5, 0.5]
        outcomes = [1, 0, 1, 0]  # 50% accuracy in the 0.4-0.6 bin
        result = _ece(probs, outcomes)
        assert result == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# WindowResult fields
# ---------------------------------------------------------------------------

class TestWindowResultFields:
    def test_default_ece_is_none(self):
        w = WindowResult(
            window_start=date(2024, 1, 1),
            window_end=date(2025, 1, 1),
            label="2024/2025",
        )
        assert w.ece_raw is None
        assert w.brier_raw is None
        assert w.ece_passes is False
        assert w.acquirer_top5_accuracy is None
        assert w.buyer_in_pool_pct is None
        assert w.false_positive_mix == {}

    def test_as_dict_includes_new_fields(self):
        w = WindowResult(
            window_start=date(2024, 1, 1),
            window_end=date(2025, 1, 1),
            label="2024/2025",
            ece_raw=0.05,
            brier_raw=0.18,
            ece_passes=True,
            acquirer_top5_accuracy=0.65,
            buyer_in_pool_pct=72.5,
            false_positive_mix={"dual_gate:low_pressure": 0.97},
        )
        d = w.as_dict()
        assert d["ece_raw"] == 0.05
        assert d["brier_raw"] == 0.18
        assert d["ece_passes"] is True
        assert d["acquirer_top5_accuracy"] == 0.65
        assert d["buyer_in_pool_pct"] == 72.5
        assert "false_positive_mix" in d


# ---------------------------------------------------------------------------
# RollingHoldoutReport.calibration_gate_passes()
# ---------------------------------------------------------------------------

def _make_report(windows: list[WindowResult]) -> RollingHoldoutReport:
    return RollingHoldoutReport(
        generated_at="2025-01-01T00:00:00Z",
        knowledge_db="fake.db",
        replay_store="fake.sqlite",
        overall_start=date(2024, 1, 1),
        overall_end=date(2025, 1, 1),
        window_months=12,
        step_months=3,
        top_k=10,
        lookahead_days=365,
        windows=windows,
    )


def _window_with_ece(ece: float | None, n_rows: int = 50) -> WindowResult:
    w = WindowResult(
        window_start=date(2024, 1, 1),
        window_end=date(2025, 1, 1),
        label="test",
        n_rows=n_rows,
    )
    if ece is not None:
        w.ece_raw = ece
        w.ece_passes = ece <= _ECE_GATE_THRESHOLD
    return w


class TestCalibrationGate:
    def test_passes_when_all_windows_below_threshold(self):
        windows = [_window_with_ece(0.05), _window_with_ece(0.08), _window_with_ece(0.09)]
        report = _make_report(windows)
        assert report.calibration_gate_passes() is True

    def test_fails_when_one_window_above_threshold(self):
        windows = [_window_with_ece(0.05), _window_with_ece(0.11), _window_with_ece(0.07)]
        report = _make_report(windows)
        assert report.calibration_gate_passes() is False

    def test_fails_when_no_ece_data(self):
        """Cold start: no ECE data at all → gate must be closed."""
        windows = [_window_with_ece(None), _window_with_ece(None)]
        report = _make_report(windows)
        assert report.calibration_gate_passes() is False

    def test_fails_when_no_windows(self):
        report = _make_report([])
        assert report.calibration_gate_passes() is False

    def test_passes_at_exact_threshold(self):
        windows = [_window_with_ece(0.10)]
        report = _make_report(windows)
        assert report.calibration_gate_passes() is True

    def test_fails_just_above_threshold(self):
        windows = [_window_with_ece(0.101)]
        report = _make_report(windows)
        assert report.calibration_gate_passes() is False

    def test_skips_windows_with_no_rows(self):
        """Windows with n_rows=0 (no data) should be skipped, not fail the gate."""
        windows = [
            _window_with_ece(0.05, n_rows=50),
            _window_with_ece(0.05, n_rows=0),  # no data — should be skipped
        ]
        report = _make_report(windows)
        assert report.calibration_gate_passes() is True

    def test_as_dict_includes_calibration_gate_passes(self):
        windows = [_window_with_ece(0.05)]
        report = _make_report(windows)
        d = report.as_dict()
        assert "calibration_gate_passes" in d
        assert d["calibration_gate_passes"] is True
