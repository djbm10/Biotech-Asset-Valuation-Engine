from __future__ import annotations

from datetime import date
from pathlib import Path

from bve.analysis.alpha_validation import (
    AlphaValidator,
    PairedExcessTrade,
    _compute_block_bootstrap,
    _compute_excess_return_stats,
    _overlap_days,
    render_alpha_validation_report,
)
from bve.intelligence.replay_policy import ReplayDecision
from bve.ops.historical_replay import ReplayStore


def _static_price_fetcher(prices: dict[date, float]):
    def _fetch(_ticker: str, _start: date, _end: date) -> dict[date, float]:
        return prices

    return _fetch


def _make_trade(
    trade_id: str,
    asset_id: str,
    entry_date: date,
    excess_return: float,
    *,
    holding_days: int = 35,
) -> PairedExcessTrade:
    exit_date = date.fromordinal(entry_date.toordinal() + holding_days - 1)
    return PairedExcessTrade(
        trade_id=trade_id,
        asset_id=asset_id,
        ticker=asset_id.upper(),
        entry_date=entry_date,
        exit_date=exit_date,
        trade_return=excess_return + 2.0,
        xbi_return=2.0,
        excess_return=excess_return,
    )


def test_paired_excess_return_computed_correctly_for_known_trade(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    run_id = store.create_run(
        start_date=date(2025, 1, 2),
        end_date=date(2025, 2, 6),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v2.0",
        strategy_version="top2_add",
    )
    decision = ReplayDecision(
        asset_id="a-alny",
        ticker="ALNY",
        recommended_action="buy",
        recommended_size_pct=0.05,
        composite_score=0.82,
        decided_at=date(2025, 1, 2),
    )
    decision_id = store.insert_decision(run_id, decision, entry_price=100.0)
    store.close_decision(
        decision_id=decision_id,
        exit_price=110.0,
        exit_date=date(2025, 2, 6),
        return_pct=10.0,
        attribution_type="confirmed_thesis",
    )
    store.close()

    validator = AlphaValidator(
        replay_db_path=str(db_path),
        price_fetcher=_static_price_fetcher({
            date(2025, 1, 2): 100.0,
            date(2025, 2, 6): 105.0,
        }),
        output_dir=tmp_path / "analysis",
        bootstrap_iterations=500,
    )
    report = validator.validate(run_id)

    assert report.stats.n_trades == 1
    assert len(report.paired_trades) == 1
    assert report.paired_trades[0].xbi_return == 5.0
    assert report.paired_trades[0].excess_return == 5.0
    assert report.csv_path is not None and report.csv_path.exists()


def test_hold_days_reprices_trade_and_updates_report_title(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    run_id = store.create_run(
        start_date=date(2025, 1, 2),
        end_date=date(2025, 2, 6),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v2.0",
        strategy_version="top2_add",
    )
    decision = ReplayDecision(
        asset_id="a-alny",
        ticker="ALNY",
        recommended_action="buy",
        recommended_size_pct=0.05,
        composite_score=0.82,
        decided_at=date(2025, 1, 2),
    )
    decision_id = store.insert_decision(run_id, decision, entry_price=100.0)
    store.close_decision(
        decision_id=decision_id,
        exit_price=110.0,
        exit_date=date(2025, 2, 6),
        return_pct=10.0,
        attribution_type="confirmed_thesis",
    )
    store.insert_prices("ALNY", [
        (date(2025, 1, 2), 100.0),
        (date(2025, 3, 3), 120.0),
    ])
    store.insert_prices("XBI", [
        (date(2025, 1, 2), 100.0),
        (date(2025, 3, 3), 104.0),
    ])
    store.close()

    def _fail_fetcher(_ticker: str, _start: date, _end: date) -> dict[date, float]:
        raise AssertionError("external fetch should not be needed for repricing test")

    validator = AlphaValidator(
        replay_db_path=str(db_path),
        price_fetcher=_fail_fetcher,
        output_dir=tmp_path / "analysis",
        bootstrap_iterations=500,
    )
    report = validator.validate(run_id, hold_days=60, today=date(2025, 4, 1))
    rendered = render_alpha_validation_report(report)

    assert report.hold_days == 60
    assert report.stats.n_trades == 1
    assert report.paired_trades[0].exit_date == date(2025, 3, 3)
    assert report.paired_trades[0].trade_return == 20.0
    assert report.paired_trades[0].xbi_return == 4.0
    assert report.paired_trades[0].excess_return == 16.0
    assert "Paired Excess Returns (vs XBI same-window, 60d hold)" in rendered
    assert report.csv_path is not None
    assert report.csv_path.name == f"alpha_validation_{run_id}_hold60d.csv"


def test_hold_days_skips_trade_when_synthetic_exit_is_in_future(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    run_id = store.create_run(
        start_date=date(2025, 1, 2),
        end_date=date(2025, 2, 6),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v2.0",
        strategy_version="top2_add",
    )
    decision = ReplayDecision(
        asset_id="a-alny",
        ticker="ALNY",
        recommended_action="buy",
        recommended_size_pct=0.05,
        composite_score=0.82,
        decided_at=date(2025, 1, 2),
    )
    decision_id = store.insert_decision(run_id, decision, entry_price=100.0)
    store.close_decision(
        decision_id=decision_id,
        exit_price=110.0,
        exit_date=date(2025, 2, 6),
        return_pct=10.0,
        attribution_type="confirmed_thesis",
    )
    store.close()

    def _fail_fetcher(_ticker: str, _start: date, _end: date) -> dict[date, float]:
        raise AssertionError("future-only repricing should not fetch prices")

    validator = AlphaValidator(
        replay_db_path=str(db_path),
        price_fetcher=_fail_fetcher,
        output_dir=tmp_path / "analysis",
        bootstrap_iterations=200,
    )
    report = validator.validate(run_id, hold_days=120, today=date(2025, 4, 1))

    assert report.stats.n_trades == 0
    assert report.csv_path is not None
    assert report.csv_path.name == f"alpha_validation_{run_id}_hold120d.csv"


def test_overlap_detection_works_for_overlapping_ranges() -> None:
    assert _overlap_days(
        date(2025, 1, 1),
        date(2025, 1, 10),
        date(2025, 1, 5),
        date(2025, 1, 15),
    ) == 6
    assert _overlap_days(
        date(2025, 1, 1),
        date(2025, 1, 10),
        date(2025, 1, 11),
        date(2025, 1, 20),
    ) == 0


def test_block_bootstrap_produces_ci_narrower_than_naive_ci() -> None:
    trades = [
        _make_trade(
            f"t{i}",
            f"a{i % 2}",
            date.fromordinal(date(2025, 1, 1).toordinal() + (7 * i)),
            excess,
        )
        for i, excess in enumerate([5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 8.0])
    ]
    stats_summary = _compute_excess_return_stats(trades)
    bootstrap = _compute_block_bootstrap(
        trades,
        iterations=2_000,
        block_size_days=28,
        seed=7,
    )

    assert stats_summary.naive_ci_low is not None
    assert stats_summary.naive_ci_high is not None
    assert bootstrap.ci_low is not None
    assert bootstrap.ci_high is not None

    naive_width = stats_summary.naive_ci_high - stats_summary.naive_ci_low
    bootstrap_width = bootstrap.ci_high - bootstrap.ci_low
    assert bootstrap_width < naive_width


def test_report_generates_without_errors_on_empty_trade_set(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    store = ReplayStore(str(db_path))
    run_id = store.create_run(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 2, 1),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v2.0",
        strategy_version="top2_add",
    )
    store.close()

    def _fail_fetcher(_ticker: str, _start: date, _end: date) -> dict[date, float]:
        raise AssertionError("benchmark fetcher should not be called for an empty trade set")

    validator = AlphaValidator(
        replay_db_path=str(db_path),
        price_fetcher=_fail_fetcher,
        output_dir=tmp_path / "analysis",
        bootstrap_iterations=200,
    )
    report = validator.validate(run_id)
    rendered = render_alpha_validation_report(report)

    assert report.stats.n_trades == 0
    assert "ALPHA VALIDATION REPORT" in rendered
    assert "N trades:              0" in rendered
    assert report.csv_path is not None and report.csv_path.exists()
    assert report.csv_path.read_text(encoding="utf-8").strip().startswith(
        "trade_id,asset_id,ticker,entry_date,exit_date,trade_return,xbi_return,excess_return"
    )
