from __future__ import annotations

from datetime import date
from pathlib import Path

from bve.analysis.edge_decomposition import (
    EdgeDecomposer,
    EnrichedTrade,
    _score_decile_rows,
    render_edge_decomposition_report,
)
from bve.intelligence.replay_policy import ReplayDecision
from bve.ops.historical_replay import ReplayStore


def _static_price_fetcher(prices: dict[date, float]):
    def _fetch(_ticker: str, _start: date, _end: date) -> dict[date, float]:
        return prices

    return _fetch


def _seed_small_run(db_path: Path) -> str:
    store = ReplayStore(str(db_path))
    run_id = store.create_run(
        start_date=date(2025, 1, 6),
        end_date=date(2025, 3, 3),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v2.0",
        strategy_version="top2_add",
    )

    trades = [
        ("a-alny", "ALNY", date(2025, 1, 6), date(2025, 2, 10), 10.0, 0.20, "confirmed_thesis"),
        ("a-srpt", "SRPT", date(2025, 1, 13), date(2025, 2, 17), 4.0, 0.50, "market_drift"),
        ("a-alny", "ALNY", date(2025, 1, 20), date(2025, 2, 24), 2.0, 0.90, "thesis_error"),
    ]
    for asset_id, ticker, entry_date, exit_date, ret, score, attr in trades:
        decision = ReplayDecision(
            asset_id=asset_id,
            ticker=ticker,
            recommended_action="buy",
            recommended_size_pct=0.05,
            composite_score=score,
            decided_at=entry_date,
        )
        decision_id = store.insert_decision(run_id, decision, entry_price=100.0)
        store.close_decision(
            decision_id=decision_id,
            exit_price=100.0 + ret,
            exit_date=exit_date,
            return_pct=ret,
            attribution_type=attr,
        )

    store.insert_event(
        asset_id="a-alny",
        ticker="ALNY",
        event_type="trial_readout",
        announced_at=date(2025, 1, 10),
        effective_date=date(2025, 1, 10),
        outcome_label="positive",
        headline="ALNY event",
    )
    store.close()
    return run_id


def _price_map() -> dict[date, float]:
    return {
        date(2025, 1, 6): 100.0,
        date(2025, 2, 10): 101.0,
        date(2025, 1, 13): 100.0,
        date(2025, 2, 17): 101.0,
        date(2025, 1, 20): 100.0,
        date(2025, 2, 24): 101.0,
    }


def test_first_entry_vs_reentry_classification_works_correctly(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_small_run(db_path)
    report = EdgeDecomposer(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        price_fetcher=_static_price_fetcher(_price_map()),
    ).generate(run_id)

    first_entry = next(row for row in report.first_entry_rows if row.label == "First Entry")
    re_entry = next(row for row in report.first_entry_rows if row.label == "Re-Entry")

    assert first_entry.n == 2
    assert re_entry.n == 1


def test_days_to_catalyst_bucketing_handles_missing_events(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_small_run(db_path)
    report = EdgeDecomposer(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        price_fetcher=_static_price_fetcher(_price_map()),
    ).generate(run_id)

    bucket_0_7 = next(row for row in report.catalyst_rows if row.label == "[0-7]")
    no_catalyst = next(row for row in report.catalyst_rows if row.label == "no_catalyst")

    assert bucket_0_7.n == 1
    assert no_catalyst.n == 2


def test_score_decile_computation_produces_ten_groups() -> None:
    trades = [
        EnrichedTrade(
            trade_id=f"t{i}",
            asset_id=f"a{i % 5}",
            ticker=f"T{i:03d}",
            entry_date=date.fromordinal(date(2025, 1, 1).toordinal() + i),
            exit_date=date.fromordinal(date(2025, 2, 1).toordinal() + i),
            trade_return=5.0,
            xbi_return=2.0,
            excess_return=3.0,
            composite_score=(i + 1) / 100.0,
            attribution_type="market_drift",
            entry_kind="first_entry",
            days_to_catalyst=None,
            catalyst_bucket="no_catalyst",
        )
        for i in range(100)
    ]
    rows = _score_decile_rows(trades)

    assert len(rows) == 10
    assert all(row.n == 10 for row in rows)


def test_report_generates_without_errors_on_small_trade_set(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_small_run(db_path)
    report = EdgeDecomposer(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        price_fetcher=_static_price_fetcher(_price_map()),
    ).generate(run_id)
    rendered = render_edge_decomposition_report(report)

    assert "EDGE DECOMPOSITION REPORT" in rendered
    assert "1. FIRST ENTRY vs RE-ENTRY" in rendered
    assert "5. BY ATTRIBUTION TYPE" in rendered


def test_csv_output_contains_all_decomposition_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_small_run(db_path)
    report = EdgeDecomposer(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        price_fetcher=_static_price_fetcher(_price_map()),
    ).generate(run_id)

    assert report.csv_path is not None and report.csv_path.exists()
    header = report.csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header == (
        "section,label,n,mean_excess_return,std_excess_return,hit_rate,"
        "t_statistic,mean_trade_return,mean_xbi_return,mean_hold_days,"
        "score_range_low,score_range_high,saved_per_blocked_trade"
    )
