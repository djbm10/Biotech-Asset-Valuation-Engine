from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import json

from bve.analysis.company_sotp_backtest import (
    CompanySOTPBacktestConfig,
    CompanySOTPBacktester,
    _render_comparison,
    _write_wave_log,
)
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.historical_replay import ReplayStore


def _company_snapshot(
    *,
    ticker: str,
    company_id: str,
    snapshot_date: date,
    ranked_sotp_discount: float,
    action_policy: str = "buy",
):
    return SimpleNamespace(
        ticker=ticker,
        company_id=company_id,
        company_name=f"Company {ticker}",
        snapshot_date=snapshot_date,
        rank=1,
        market_cap_millions=250.0,
        enterprise_value_millions=230.0,
        sotp_equity_value_millions=300.0,
        sotp_per_share=30.0,
        sotp_discount=ranked_sotp_discount,
        ranked_sotp_discount=ranked_sotp_discount,
        modeled_asset_coverage_pct=0.8,
        asset_count_modeled=1,
        modeled_asset_ids=[f"asset-{ticker.lower()}"],
        config_quality_summary="curated",
        modeled_asset_confidence_min=0.9,
        modeled_asset_confidence_avg=0.9,
        action_policy=action_policy,
        action_reason="ok",
        market_cap_source="unit_test",
        balance_sheet_source="sec_edgar_company_facts",
        balance_sheet_source_ref="unit-test",
        balance_sheet_snapshot_date=snapshot_date,
        balance_sheet_period_end_date=snapshot_date,
        balance_sheet_form_type="10-Q",
        balance_sheet_is_point_in_time=True,
        balance_sheet_age_days=10,
        balance_sheet_passes_recency_gate=True,
        balance_sheet_recency_penalty=1.0,
        buckets=[],
        limitations=[],
        notes=None,
    )


def test_company_sotp_backtester_uses_company_snapshots_as_signal_dataset(tmp_path: Path) -> None:
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    replay = ReplayStore(str(tmp_path / "replay.sqlite"))
    try:
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=1.8,
                ),
                _company_snapshot(
                    ticker="BBB",
                    company_id="co-bbb",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=1.2,
                ),
            ],
            snapshot_date=date(2024, 1, 1),
        )
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 2, 1),
                    ranked_sotp_discount=1.7,
                )
            ],
            snapshot_date=date(2024, 2, 1),
        )
        replay.insert_prices(
            "AAA",
            [
                (date(2024, 1, 1), 10.0),
                (date(2024, 1, 31), 12.0),
                (date(2024, 2, 1), 12.0),
                (date(2024, 3, 2), 13.0),
            ],
        )
        replay.insert_prices(
            "BBB",
            [
                (date(2024, 1, 1), 8.0),
                (date(2024, 1, 31), 8.5),
            ],
        )
        replay.insert_prices(
            "XBI",
            [
                (date(2024, 1, 1), 100.0),
                (date(2024, 1, 31), 105.0),
                (date(2024, 2, 1), 105.0),
                (date(2024, 3, 2), 110.0),
            ],
        )

        report = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=CompanySOTPBacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 15),
                hold_days=30,
                top_n=1,
                min_ranked_sotp_discount=1.0,
            ),
        ).run()
    finally:
        replay.close()
        knowledge.close()

    assert report.n_snapshot_dates == 2
    assert report.n_candidate_rows == 3
    assert report.n_selected_trades == 2
    assert report.n_missing_price_trades == 0
    assert report.stats.n_trades == 2
    assert report.csv_path.exists()
    assert [trade.ticker for trade in report.trades] == ["AAA", "AAA"]


def test_company_sotp_backtester_can_measure_needs_manual_review_lane(tmp_path: Path) -> None:
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    replay = ReplayStore(str(tmp_path / "replay.sqlite"))
    try:
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=2.0,
                    action_policy="needs_manual_review",
                ),
                _company_snapshot(
                    ticker="BBB",
                    company_id="co-bbb",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=1.8,
                    action_policy="buy",
                ),
            ],
            snapshot_date=date(2024, 1, 1),
        )
        replay.insert_prices(
            "AAA",
            [
                (date(2024, 1, 1), 10.0),
                (date(2024, 1, 31), 12.0),
            ],
        )
        replay.insert_prices(
            "BBB",
            [
                (date(2024, 1, 1), 8.0),
                (date(2024, 1, 31), 9.0),
            ],
        )
        replay.insert_prices(
            "XBI",
            [
                (date(2024, 1, 1), 100.0),
                (date(2024, 1, 31), 105.0),
            ],
        )

        report = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=CompanySOTPBacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 1),
                hold_days=30,
                top_n=5,
                min_ranked_sotp_discount=1.0,
                allowed_action_policies=("needs_manual_review",),
            ),
        ).run()
    finally:
        replay.close()
        knowledge.close()

    assert report.n_snapshot_dates == 1
    assert report.n_candidate_rows == 1
    assert report.n_selected_trades == 1
    assert [trade.ticker for trade in report.trades] == ["AAA"]
    assert report.csv_path.name.endswith("_actions-needs_manual_review.csv")


def test_company_sotp_backtester_default_lane_includes_needs_manual_review(tmp_path: Path) -> None:
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    replay = ReplayStore(str(tmp_path / "replay.sqlite"))
    try:
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=2.0,
                    action_policy="needs_manual_review",
                ),
                _company_snapshot(
                    ticker="BBB",
                    company_id="co-bbb",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=1.2,
                    action_policy="buy",
                ),
            ],
            snapshot_date=date(2024, 1, 1),
        )
        replay.insert_prices(
            "AAA",
            [
                (date(2024, 1, 1), 10.0),
                (date(2024, 1, 31), 12.0),
            ],
        )
        replay.insert_prices(
            "BBB",
            [
                (date(2024, 1, 1), 8.0),
                (date(2024, 1, 31), 9.0),
            ],
        )
        replay.insert_prices(
            "XBI",
            [
                (date(2024, 1, 1), 100.0),
                (date(2024, 1, 31), 105.0),
            ],
        )

        report = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=CompanySOTPBacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 1),
                hold_days=30,
                top_n=5,
                min_ranked_sotp_discount=1.0,
            ),
        ).run()
    finally:
        replay.close()
        knowledge.close()

    assert report.n_candidate_rows == 2
    assert [trade.ticker for trade in report.trades] == ["AAA", "BBB"]


def test_render_comparison_includes_primary_and_strict_lane_labels(tmp_path: Path) -> None:
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    replay = ReplayStore(str(tmp_path / "replay.sqlite"))
    try:
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=2.0,
                    action_policy="needs_manual_review",
                ),
                _company_snapshot(
                    ticker="BBB",
                    company_id="co-bbb",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=1.2,
                    action_policy="buy",
                ),
            ],
            snapshot_date=date(2024, 1, 1),
        )
        replay.insert_prices("AAA", [(date(2024, 1, 1), 10.0), (date(2024, 1, 31), 12.0)])
        replay.insert_prices("BBB", [(date(2024, 1, 1), 8.0), (date(2024, 1, 31), 9.0)])
        replay.insert_prices("XBI", [(date(2024, 1, 1), 100.0), (date(2024, 1, 31), 105.0)])

        primary = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=CompanySOTPBacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 1),
                hold_days=30,
                top_n=5,
                min_ranked_sotp_discount=1.0,
            ),
        ).run()
        strict = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=CompanySOTPBacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 1),
                hold_days=30,
                top_n=5,
                min_ranked_sotp_discount=1.0,
                allowed_action_policies=("buy", "watch"),
            ),
        ).run()
    finally:
        replay.close()
        knowledge.close()

    rendered = _render_comparison(primary, strict)
    assert "Primary lane: buy/watch/needs_manual_review" in rendered
    assert "Comparator lane: buy/watch" in rendered


def test_write_wave_log_creates_new_file(tmp_path: Path) -> None:
    """_write_wave_log creates a JSON file and writes a wave entry."""
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    replay = ReplayStore(str(tmp_path / "replay.sqlite"))
    try:
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=2.5,
                    action_policy="buy",
                ),
            ],
            snapshot_date=date(2024, 1, 1),
        )
        replay.insert_prices("AAA", [(date(2024, 1, 1), 10.0), (date(2024, 1, 31), 12.0)])
        replay.insert_prices("XBI", [(date(2024, 1, 1), 100.0), (date(2024, 1, 31), 102.0)])
        report = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=CompanySOTPBacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 1),
                hold_days=30,
                top_n=5,
                min_ranked_sotp_discount=1.0,
                allowed_action_policies=("buy", "watch", "needs_manual_review"),
            ),
        ).run()
    finally:
        replay.close()
        knowledge.close()

    wave_log_path = tmp_path / "wave_log.json"
    _write_wave_log(report, wave_label="test_wave_1", wave_log_path=wave_log_path)

    assert wave_log_path.exists()
    entries = json.loads(wave_log_path.read_text())
    assert len(entries) == 1
    entry = entries[0]
    assert entry["wave_label"] == "test_wave_1"
    assert entry["lane"] == "buy/watch/needs_manual_review"
    assert "mean_excess_return" in entry
    assert "bootstrap_p" in entry
    assert "cluster_count" in entry
    assert "run_timestamp" in entry
    assert entry["backfill_action_totals"] is None


def test_write_wave_log_appends_to_existing_file(tmp_path: Path) -> None:
    """_write_wave_log appends to an existing wave log without overwriting prior entries."""
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    replay = ReplayStore(str(tmp_path / "replay.sqlite"))
    try:
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=2.5,
                    action_policy="buy",
                ),
            ],
            snapshot_date=date(2024, 1, 1),
        )
        replay.insert_prices("AAA", [(date(2024, 1, 1), 10.0), (date(2024, 1, 31), 11.0)])
        replay.insert_prices("XBI", [(date(2024, 1, 1), 100.0), (date(2024, 1, 31), 101.0)])
        config = CompanySOTPBacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 1),
            hold_days=30,
            top_n=5,
            min_ranked_sotp_discount=1.0,
        )
        backtester = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=config,
        )
        report = backtester.run()
    finally:
        replay.close()
        knowledge.close()

    wave_log_path = tmp_path / "wave_log.json"
    _write_wave_log(report, wave_label="wave_a", wave_log_path=wave_log_path)
    _write_wave_log(report, wave_label="wave_b", wave_log_path=wave_log_path)

    entries = json.loads(wave_log_path.read_text())
    assert len(entries) == 2
    assert entries[0]["wave_label"] == "wave_a"
    assert entries[1]["wave_label"] == "wave_b"


def test_write_wave_log_includes_strict_comparison(tmp_path: Path) -> None:
    """_write_wave_log records strict buy/watch comparison block when provided."""
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    replay = ReplayStore(str(tmp_path / "replay.sqlite"))
    try:
        knowledge.write_company_sotp_snapshots(
            [
                _company_snapshot(
                    ticker="AAA",
                    company_id="co-aaa",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=2.5,
                    action_policy="needs_manual_review",
                ),
                _company_snapshot(
                    ticker="BBB",
                    company_id="co-bbb",
                    snapshot_date=date(2024, 1, 1),
                    ranked_sotp_discount=1.5,
                    action_policy="buy",
                ),
            ],
            snapshot_date=date(2024, 1, 1),
        )
        replay.insert_prices("AAA", [(date(2024, 1, 1), 10.0), (date(2024, 1, 31), 12.0)])
        replay.insert_prices("BBB", [(date(2024, 1, 1), 8.0), (date(2024, 1, 31), 9.0)])
        replay.insert_prices("XBI", [(date(2024, 1, 1), 100.0), (date(2024, 1, 31), 103.0)])
        primary = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=CompanySOTPBacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 1),
                hold_days=30,
                top_n=5,
                min_ranked_sotp_discount=1.0,
            ),
        ).run()
        strict = CompanySOTPBacktester(
            knowledge,
            replay_db_path=tmp_path / "replay.sqlite",
            output_dir=tmp_path / "analysis",
            config=CompanySOTPBacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 1),
                hold_days=30,
                top_n=5,
                min_ranked_sotp_discount=1.0,
                allowed_action_policies=("buy", "watch"),
            ),
        ).run()
    finally:
        replay.close()
        knowledge.close()

    wave_log_path = tmp_path / "wave_log.json"
    _write_wave_log(
        primary,
        wave_label="with_strict",
        wave_log_path=wave_log_path,
        strict_report=strict,
    )

    entry = json.loads(wave_log_path.read_text())[0]
    assert "strict_buy_watch_comparison" in entry
    cmp = entry["strict_buy_watch_comparison"]
    assert "mean_excess_return" in cmp
    assert "bootstrap_p" in cmp
