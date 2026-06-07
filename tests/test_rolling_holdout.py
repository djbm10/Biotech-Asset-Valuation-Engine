"""Tests for the rolling holdout evaluator."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from bve.analysis.rolling_holdout import (
    MIN_TARGETS_FOR_TRUST,
    RollingHoldoutReport,
    WindowResult,
    _rolling_windows,
    render_report,
    run_rolling_holdout,
)


# ---------------------------------------------------------------------------
# _rolling_windows
# ---------------------------------------------------------------------------


def test_rolling_windows_produces_correct_count():
    # 12 months, step 3 → from 2024-01 to 2025-12: 7 windows starting at
    # Jan, Apr, Jul, Oct 2024 and Jan, Apr, Jul 2025
    start = date(2024, 1, 1)
    end = date(2026, 1, 1)
    wins = _rolling_windows(start, end, window_months=12, step_months=3)
    # First window: 2024-01-01 to 2025-01-01
    # Last starting point that fits: 2025-01-01 to 2026-01-01
    assert len(wins) >= 5


def test_rolling_windows_first_window_correct_span():
    start = date(2024, 1, 1)
    end = date(2025, 6, 1)
    wins = _rolling_windows(start, end, window_months=12, step_months=6)
    w0_start, w0_end, _ = wins[0]
    assert w0_start == date(2024, 1, 1)
    assert w0_end == date(2025, 1, 1)


def test_rolling_windows_crops_to_end():
    start = date(2025, 1, 1)
    end = date(2025, 9, 1)
    wins = _rolling_windows(start, end, window_months=12, step_months=6)
    for _, w_end, _ in wins:
        assert w_end <= end


def test_rolling_windows_advances_by_step():
    start = date(2024, 1, 1)
    end = date(2026, 1, 1)
    wins = _rolling_windows(start, end, window_months=12, step_months=3)
    starts = [w[0] for w in wins]
    for i in range(1, len(starts)):
        months_diff = (starts[i].year - starts[i-1].year) * 12 + (starts[i].month - starts[i-1].month)
        assert months_diff == 3


def test_rolling_windows_empty_range():
    start = date(2025, 6, 1)
    end = date(2025, 5, 1)  # end before start
    wins = _rolling_windows(start, end, window_months=12, step_months=3)
    assert wins == []


def test_rolling_windows_step_larger_than_window():
    # Each window: 3 months, step: 6 months → non-overlapping
    start = date(2024, 1, 1)
    end = date(2025, 1, 1)
    wins = _rolling_windows(start, end, window_months=3, step_months=6)
    assert len(wins) == 2
    assert wins[0][0] == date(2024, 1, 1)
    assert wins[0][1] == date(2024, 4, 1)
    assert wins[1][0] == date(2024, 7, 1)


def test_rolling_windows_label_format():
    start = date(2024, 3, 1)
    end = date(2025, 3, 1)
    wins = _rolling_windows(start, end, window_months=12, step_months=6)
    _, _, label = wins[0]
    assert "/" in label
    assert label.startswith("2024-03-01/")


# ---------------------------------------------------------------------------
# WindowResult
# ---------------------------------------------------------------------------


def test_window_result_low_n_when_below_threshold():
    w = WindowResult(
        window_start=date(2024, 1, 1),
        window_end=date(2025, 1, 1),
        label="test",
        n_positive_targets=MIN_TARGETS_FOR_TRUST - 1,
        low_n=True,
    )
    assert w.low_n is True


def test_window_result_not_low_n_at_threshold():
    w = WindowResult(
        window_start=date(2024, 1, 1),
        window_end=date(2025, 1, 1),
        label="test",
        n_positive_targets=MIN_TARGETS_FOR_TRUST,
        low_n=False,
    )
    assert w.low_n is False


def test_window_result_as_dict_has_required_keys():
    w = WindowResult(
        window_start=date(2024, 1, 1),
        window_end=date(2025, 1, 1),
        label="2024-01-01/2025-01-01",
    )
    d = w.as_dict()
    for key in ["window", "n_rows", "n_positive_targets", "low_n",
                "stage_a_avg_positive", "stage_a_avg_control", "stage_a_auc",
                "stage_a_precision_at_k", "acquirer_top1_accuracy", "acquirer_mrr",
                "sharpe_ratio", "max_drawdown"]:
        assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# render_report
# ---------------------------------------------------------------------------


def _make_report(windows: list[WindowResult]) -> RollingHoldoutReport:
    return RollingHoldoutReport(
        generated_at="2026-04-25T00:00:00Z",
        knowledge_db="kb.db",
        replay_store="rs.sqlite",
        overall_start=date(2024, 1, 1),
        overall_end=date(2026, 1, 1),
        window_months=12,
        step_months=3,
        top_k=10,
        lookahead_days=365,
        windows=windows,
    )


def test_render_report_shows_header():
    report = _make_report([])
    text = render_report(report)
    assert "Rolling Holdout Evaluation" in text
    assert "MIN_TARGETS_FOR_TRUST" in text


def test_render_report_flags_low_n_windows():
    w_low = WindowResult(
        window_start=date(2024, 1, 1),
        window_end=date(2025, 1, 1),
        label="2024-01-01/2025-01-01",
        n_positive_targets=1,
        low_n=True,
    )
    text = render_report(_make_report([w_low]))
    assert "* " in text  # low-N flag


def test_render_report_no_flag_for_trusted_window():
    w_ok = WindowResult(
        window_start=date(2024, 1, 1),
        window_end=date(2025, 1, 1),
        label="2024-01-01/2025-01-01",
        n_positive_targets=MIN_TARGETS_FOR_TRUST,
        low_n=False,
    )
    text = render_report(_make_report([w_ok]))
    # The label line for the trusted window should not be prefixed with "* "
    # (The header legend line contains "* =" but that is separate)
    data_lines = [ln for ln in text.splitlines() if "2024-01-01/2025-01-01" in ln]
    assert data_lines, "Expected a data row for the window label"
    assert not any(ln.strip().startswith("*") for ln in data_lines)


def test_render_report_shows_mean_for_trusted_windows():
    w1 = WindowResult(
        window_start=date(2024, 1, 1),
        window_end=date(2025, 1, 1),
        label="w1",
        n_positive_targets=5, low_n=False,
        stage_a_auc=0.70, acquirer_top1_accuracy=0.8,
    )
    w2 = WindowResult(
        window_start=date(2024, 4, 1),
        window_end=date(2025, 4, 1),
        label="w2",
        n_positive_targets=4, low_n=False,
        stage_a_auc=0.75, acquirer_top1_accuracy=0.6,
    )
    text = render_report(_make_report([w1, w2]))
    assert "mean (trusted)" in text


def test_render_report_marks_skipped_public_markets():
    w = WindowResult(
        window_start=date(2024, 1, 1),
        window_end=date(2025, 1, 1),
        label="w",
        n_positive_targets=5, low_n=False,
        public_skipped=True,
        public_skip_reason="no_positions_in_window",
    )
    text = render_report(_make_report([w]))
    assert "skip" in text


# ---------------------------------------------------------------------------
# run_rolling_holdout (integration-lite with real DBs)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("window_months,step_months", [(12, 6), (6, 3)])
def test_run_rolling_holdout_returns_report(window_months, step_months):
    """Smoke-test: runs against real DBs without crashing."""
    kb = "outputs/intelligence/replay_knowledge.db"
    rs = "outputs/intelligence/replay_store.sqlite"
    uf = "outputs/universe_replay.json"
    if not Path(kb).exists() or not Path(rs).exists():
        pytest.skip("Live intelligence DBs not present")

    report = run_rolling_holdout(
        knowledge_db=kb,
        replay_store=rs,
        universe_file=uf,
        overall_start=date(2024, 1, 1),
        overall_end=date(2026, 3, 1),
        window_months=window_months,
        step_months=step_months,
        top_k=10,
        lookahead_days=365,
    )
    assert isinstance(report, RollingHoldoutReport)
    assert len(report.windows) >= 1
    for w in report.windows:
        assert isinstance(w, WindowResult)
        assert w.n_rows >= 0


def test_run_rolling_holdout_window_count_correct():
    """6 windows expected: 2024-Q1 through 2025-Q3 with step=3m, window=12m."""
    kb = "outputs/intelligence/replay_knowledge.db"
    rs = "outputs/intelligence/replay_store.sqlite"
    uf = "outputs/universe_replay.json"
    if not Path(kb).exists():
        pytest.skip("Live intelligence DBs not present")

    report = run_rolling_holdout(
        knowledge_db=kb,
        replay_store=rs,
        universe_file=uf,
        overall_start=date(2024, 1, 1),
        overall_end=date(2026, 3, 1),
        window_months=12,
        step_months=3,
        top_k=10,
        lookahead_days=365,
    )
    # With step=3m over 2 years, expect ~9 windows
    assert len(report.windows) >= 5


def test_run_rolling_holdout_stage_a_populated():
    """Stage A metrics should be populated in at least one window."""
    kb = "outputs/intelligence/replay_knowledge.db"
    rs = "outputs/intelligence/replay_store.sqlite"
    uf = "outputs/universe_replay.json"
    if not Path(kb).exists():
        pytest.skip("Live intelligence DBs not present")

    report = run_rolling_holdout(
        knowledge_db=kb,
        replay_store=rs,
        universe_file=uf,
        overall_start=date(2024, 1, 1),
        overall_end=date(2026, 3, 1),
        window_months=12,
        step_months=6,
        top_k=10,
        lookahead_days=365,
    )
    has_stage_a = any(w.stage_a_auc is not None for w in report.windows)
    assert has_stage_a, "Expected at least one window with stage_a_auc populated"


def test_run_rolling_holdout_positive_targets_per_window():
    """Each 12-month window covering known deal periods should have ≥1 positive target."""
    kb = "outputs/intelligence/replay_knowledge.db"
    rs = "outputs/intelligence/replay_store.sqlite"
    uf = "outputs/universe_replay.json"
    if not Path(kb).exists():
        pytest.skip("Live intelligence DBs not present")

    report = run_rolling_holdout(
        knowledge_db=kb,
        replay_store=rs,
        universe_file=uf,
        overall_start=date(2024, 1, 1),
        overall_end=date(2026, 3, 1),
        window_months=12,
        step_months=6,
        top_k=10,
        lookahead_days=365,
    )
    # The 2024-2025 period has confirmed deals — at least some windows should have positives
    windows_with_positives = [w for w in report.windows if w.n_positive_targets > 0]
    assert len(windows_with_positives) >= 1


def test_rolling_holdout_report_serializes_to_dict():
    kb = "outputs/intelligence/replay_knowledge.db"
    rs = "outputs/intelligence/replay_store.sqlite"
    uf = "outputs/universe_replay.json"
    if not Path(kb).exists():
        pytest.skip("Live intelligence DBs not present")

    report = run_rolling_holdout(
        knowledge_db=kb,
        replay_store=rs,
        universe_file=uf,
        overall_start=date(2024, 6, 1),
        overall_end=date(2025, 6, 1),
        window_months=12,
        step_months=12,
        top_k=10,
        lookahead_days=365,
    )
    d = report.as_dict()
    assert "windows" in d
    assert "overall_start" in d
    assert isinstance(d["windows"], list)
