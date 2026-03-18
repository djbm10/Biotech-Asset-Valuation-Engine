from __future__ import annotations

from datetime import date, datetime, timezone

from bve.analysis.portfolio_backtest import (
    PortfolioBacktestConfig,
    PortfolioBacktester,
    SURVIVORSHIP_BIAS_WARNING,
)
from bve.cli.portfolio_backtest import main as portfolio_backtest_main
from bve.intelligence.knowledge_layer import (
    AssetRegistryEntry,
    BacktestSnapshot,
    KnowledgeStore,
)


def test_portfolio_backtester_empty_snapshots_returns_graceful_result():
    store = KnowledgeStore(":memory:")
    try:
        result = PortfolioBacktester(store, PortfolioBacktestConfig()).run()
    finally:
        store.close()

    assert result.n_signals == 0
    assert result.notes == ["n_signals=0"]
    assert result.position_log == []


def test_portfolio_backtest_cli_prints_survivorship_disclaimer(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-portfolio-backtest",
            "--db",
            ":memory:",
        ],
    )
    portfolio_backtest_main()
    captured = capsys.readouterr()
    assert SURVIVORSHIP_BIAS_WARNING in captured.out


def test_portfolio_backtester_reports_snapshot_coverage_and_exclusions():
    store = KnowledgeStore(":memory:")
    ts = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    try:
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(asset_id="asset-1", ticker="AAA", source="test")
        )
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(asset_id="asset-2", ticker="BBB", source="test")
        )
        store.write_backtest_snapshot(
            BacktestSnapshot(
                snapshot_id="snap-1",
                alert_id="a1",
                asset_id="asset-1",
                signal_date=date(2026, 3, 1),
                composite_score=0.9,
                created_at=ts,
            )
        )
        store.write_backtest_snapshot(
            BacktestSnapshot(
                snapshot_id="snap-2",
                alert_id="a2",
                asset_id="asset-2",
                signal_date=date(2026, 3, 1),
                composite_score=0.8,
                created_at=ts,
            )
        )

        def _fetch(ticker: str, start: date, end: date):
            if ticker == "BBB":
                return None
            return 0.10

        result = PortfolioBacktester(
            store,
            PortfolioBacktestConfig(n_holdings=2, rebalance_freq_days=10),
            price_fetcher=_fetch,
        ).run()
    finally:
        store.close()

    assert result.evaluated_positions == 1
    assert result.missing_price_positions == 1
    assert result.assets_excluded_missing_prices == 1
    assert result.snapshot_coverage_pct == 50.0


def test_portfolio_backtester_does_not_use_snapshots_beyond_end_date():
    store = KnowledgeStore(":memory:")
    ts = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    calls: list[tuple[str, date, date]] = []
    try:
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(asset_id="asset-1", ticker="AAA", source="test")
        )
        store.write_backtest_snapshot(
            BacktestSnapshot(
                snapshot_id="snap-1",
                alert_id="a1",
                asset_id="asset-1",
                signal_date=date(2026, 3, 1),
                composite_score=0.9,
                created_at=ts,
            )
        )
        store.write_backtest_snapshot(
            BacktestSnapshot(
                snapshot_id="snap-2",
                alert_id="a2",
                asset_id="asset-1",
                signal_date=date(2026, 3, 20),
                composite_score=0.95,
                created_at=ts,
            )
        )

        def _fetch(ticker: str, start: date, end: date):
            calls.append((ticker, start, end))
            return 0.05

        PortfolioBacktester(
            store,
            PortfolioBacktestConfig(
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 10),
                rebalance_freq_days=10,
            ),
            price_fetcher=_fetch,
        ).run()
    finally:
        store.close()

    # One asset leg + one benchmark leg from the in-window snapshot only.
    assert len(calls) == 2
    assert all(start == date(2026, 3, 1) for _, start, _ in calls)
