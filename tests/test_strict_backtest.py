from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.learning.calibration import ProbabilityCalibrator
from bve.ops.strict_backtest import (
    _build_date_splits,
    _choose_calibrator,
    _drawdown_improved_enough,
    _portfolio_objective,
    materialize_backtest_snapshots_from_company_sotp,
)


def test_build_date_splits_returns_ordered_train_validation_holdout():
    dates = [date(2021, month, 1) for month in range(1, 13)]

    splits = _build_date_splits(dates)

    assert [split.name for split in splits] == ["train", "validation", "holdout"]
    assert splits[0].start_date == date(2021, 1, 1)
    assert splits[0].end_date < splits[1].start_date
    assert splits[1].end_date < splits[2].start_date
    assert splits[2].end_date == date(2021, 12, 1)


def test_choose_calibrator_uses_train_validation_only():
    train_pairs = [(0.8, 1.0), (0.7, 1.0), (0.2, 0.0)] * 20
    validation_pairs = [(0.75, 1.0), (0.25, 0.0)] * 10

    calibrator, summary = _choose_calibrator(train_pairs, validation_pairs)

    assert isinstance(calibrator, ProbabilityCalibrator)
    assert summary["train_pairs"] == len(train_pairs)
    assert summary["validation_pairs"] == len(validation_pairs)
    assert "holdout_pairs" not in summary


def test_materialize_backtest_snapshots_uses_snapshot_date_not_backfill_created_at(tmp_path):
    db_path = tmp_path / "replay_knowledge.db"
    store = KnowledgeStore(str(db_path))
    try:
        row = SimpleNamespace(
            ticker="VKTX",
            company_id="co-vktx",
            company_name="Viking Therapeutics",
            snapshot_date=date(2024, 1, 1),
            rank=1,
            market_cap_millions=1000.0,
            enterprise_value_millions=900.0,
            sotp_equity_value_millions=1800.0,
            sotp_per_share=20.0,
            sotp_discount=1.0,
            ranked_sotp_discount=1.0,
            modeled_asset_coverage_pct=100.0,
            asset_count_modeled=1,
            modeled_asset_ids=["asset-1"],
            action_policy="buy",
            action_reason="test",
            buckets=[],
            limitations=[],
            notes="backfilled later",
        )
        store.write_company_sotp_snapshots([row], snapshot_date=date(2024, 1, 1))
    finally:
        store.close()

    written = materialize_backtest_snapshots_from_company_sotp(
        knowledge_db_path=str(db_path),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
    )

    assert written == 1

    store = KnowledgeStore(str(db_path))
    try:
        snapshots = store.get_backtest_snapshots()
    finally:
        store.close()

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.signal_date == date(2024, 1, 1)
    assert snapshot.created_at == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert snapshot.signal_timestamp == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert snapshot.composite_score is not None


def test_drawdown_improved_enough_returns_true_when_candidate_lower_by_threshold():
    baseline = {"max_drawdown": 0.20}
    candidate = {"max_drawdown": 0.17}  # 3pp improvement

    assert _drawdown_improved_enough(candidate, baseline) is True


def test_drawdown_improved_enough_returns_false_when_improvement_below_threshold():
    baseline = {"max_drawdown": 0.20}
    candidate = {"max_drawdown": 0.19}  # only 1pp improvement

    assert _drawdown_improved_enough(candidate, baseline) is False


def test_drawdown_improved_enough_returns_false_when_candidate_worse():
    baseline = {"max_drawdown": 0.15}
    candidate = {"max_drawdown": 0.22}  # drawdown increased

    assert _drawdown_improved_enough(candidate, baseline) is False


def test_drawdown_improved_enough_respects_custom_threshold():
    baseline = {"max_drawdown": 0.20}
    candidate = {"max_drawdown": 0.17}  # 3pp improvement

    # With 5pp threshold, 3pp is not enough
    assert _drawdown_improved_enough(candidate, baseline, min_improvement=0.05) is False
    # With 2pp threshold (default), 3pp is enough
    assert _drawdown_improved_enough(candidate, baseline, min_improvement=0.02) is True


def test_drawdown_improved_enough_handles_missing_keys():
    # Both missing → both treated as 0 → no improvement
    assert _drawdown_improved_enough({}, {}) is False

    # Candidate has no drawdown data (treated as 0), baseline has drawdown
    assert _drawdown_improved_enough({}, {"max_drawdown": 0.10}) is True


def test_portfolio_objective_penalises_drawdown_more_than_sharpe():
    # Drawdown multiplier is 2.0: a moderate-Sharpe/high-drawdown result should
    # score lower than a zero-Sharpe/minimal-drawdown result.
    moderate_sharpe_high_drawdown = {"sharpe_ratio": 0.5, "max_drawdown": 0.40}
    zero_sharpe_low_drawdown = {"sharpe_ratio": 0.0, "max_drawdown": 0.05}

    # 0.5 - 2*0.40 = -0.30  vs  0.0 - 2*0.05 = -0.10
    assert _portfolio_objective(moderate_sharpe_high_drawdown) < _portfolio_objective(zero_sharpe_low_drawdown)


def test_portfolio_objective_calibration_error_acts_as_tiebreaker():
    # Same Sharpe and drawdown, but different calibration error
    good_calibration = {"sharpe_ratio": 0.5, "max_drawdown": 0.10, "calibration_error": 0.05}
    poor_calibration = {"sharpe_ratio": 0.5, "max_drawdown": 0.10, "calibration_error": 0.50}

    assert _portfolio_objective(good_calibration) > _portfolio_objective(poor_calibration)
