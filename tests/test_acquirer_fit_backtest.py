"""
Tests for the acquirer-fit model backtest (Block 1B).

Grading criteria: the acquirer-fit scorer should demonstrate measurable signal
on closed M&A deals — at minimum P@1 > 10% and P@3 > 20% on the medium+
quality subset.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bve.analysis.acquirer_fit_backtest import (
    AcquirerFitBacktestResult,
    run_acquirer_fit_backtest,
)

DEALS_PATH = Path("research/mna/comparable_deals.yaml")
PROFILES_PATH = Path("examples/research/acquirer_profiles/")


@pytest.fixture(scope="module")
def backtest_result() -> AcquirerFitBacktestResult:
    return run_acquirer_fit_backtest(
        deals_path=DEALS_PATH,
        profiles_path=PROFILES_PATH,
        ma_only=True,
        min_data_quality="medium",
    )


def test_backtest_runs_without_error(backtest_result: AcquirerFitBacktestResult) -> None:
    assert backtest_result is not None


def test_backtest_grades_at_least_15_deals(backtest_result: AcquirerFitBacktestResult) -> None:
    """Enough deals with profiles to produce statistically meaningful metrics."""
    assert backtest_result.n_graded >= 15


def test_precision_at_1_has_signal(backtest_result: AcquirerFitBacktestResult) -> None:
    """P@1 > 10% — model beats chance (random baseline ≈ 1/33 ≈ 3%)."""
    assert backtest_result.precision_at_1 > 0.10, (
        f"P@1={backtest_result.precision_at_1:.1%} — model has no signal above random"
    )


def test_precision_at_3_has_signal(backtest_result: AcquirerFitBacktestResult) -> None:
    """P@3 > 20% — top-3 contains correct acquirer meaningfully above random (≈9%)."""
    assert backtest_result.precision_at_3 > 0.20, (
        f"P@3={backtest_result.precision_at_3:.1%} — model has insufficient top-3 signal"
    )


def test_mrr_above_floor(backtest_result: AcquirerFitBacktestResult) -> None:
    """MRR > 0.15 — average reciprocal rank indicates some hits near top."""
    assert backtest_result.mean_reciprocal_rank > 0.15


def test_known_hit_arena_pfizer(backtest_result: AcquirerFitBacktestResult) -> None:
    """Arena Pharmaceuticals → Pfizer should rank #1 (UC + immunology TA match)."""
    arena_rows = [r for r in backtest_result.rows if "arena" in r.target_name.lower()]
    assert arena_rows, "Arena Pharmaceuticals not in graded rows"
    assert arena_rows[0].actual_rank == 1, (
        f"Arena → Pfizer ranked {arena_rows[0].actual_rank}, expected 1"
    )


def test_known_hit_bellus_gsk(backtest_result: AcquirerFitBacktestResult) -> None:
    """Bellus Health → GSK should rank #1 (respiratory + P2b asset)."""
    bellus_rows = [r for r in backtest_result.rows if "bellus" in r.target_name.lower()]
    assert bellus_rows, "Bellus Health not in graded rows"
    assert bellus_rows[0].actual_rank == 1, (
        f"Bellus → GSK ranked {bellus_rows[0].actual_rank}, expected 1"
    )


def test_known_hit_imago_merck(backtest_result: AcquirerFitBacktestResult) -> None:
    """Imago → Merck should rank #1 (hematology/oncology)."""
    imago_rows = [r for r in backtest_result.rows if "imago" in r.target_name.lower()]
    assert imago_rows, "Imago BioSciences not in graded rows"
    assert imago_rows[0].actual_rank == 1, (
        f"Imago → Merck ranked {imago_rows[0].actual_rank}, expected 1"
    )


def test_all_rows_have_valid_scores(backtest_result: AcquirerFitBacktestResult) -> None:
    for row in backtest_result.rows:
        assert row.actual_rank is not None, f"Missing rank for {row.target_name}"
        assert 1 <= row.actual_rank <= len(row.ranked_acquirer_ids)
        assert 0.0 <= row.reciprocal_rank <= 1.0
        assert len(row.ranked_acquirer_ids) == len(row.ranked_scores)


def test_skipped_count_is_reasonable(backtest_result: AcquirerFitBacktestResult) -> None:
    """Most acquirers in the deals should have profiles — skip rate < 50%."""
    skip_rate = backtest_result.n_skipped_no_profile / max(backtest_result.n_total_deals, 1)
    assert skip_rate < 0.50, (
        f"Skip rate {skip_rate:.0%} — too many deals without acquirer profiles"
    )
