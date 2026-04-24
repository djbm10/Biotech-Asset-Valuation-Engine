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
    assert result.brier_score is not None
    assert result.calibration_error is not None
    assert result.avg_return_by_tier


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


def test_portfolio_backtester_excludes_future_created_snapshot_from_as_of_window():
    store = KnowledgeStore(":memory:")
    ts = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
    calls: list[tuple[str, date, date]] = []
    try:
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(asset_id="asset-1", ticker="AAA", source="test")
        )
        store.write_backtest_snapshot(
            BacktestSnapshot(
                snapshot_id="snap-future",
                alert_id="a1",
                asset_id="asset-1",
                signal_date=date(2026, 3, 1),
                composite_score=0.9,
                created_at=ts,
            )
        )

        def _fetch(ticker: str, start: date, end: date):
            calls.append((ticker, start, end))
            return 0.05

        result = PortfolioBacktester(
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

    assert calls == []
    assert result.n_signals == 0


def test_max_single_position_weight_caps_individual_positions():
    """max_single_position_weight should prevent any single name exceeding the cap."""
    store = KnowledgeStore(":memory:")
    ts = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    weights_seen: list[float] = []
    try:
        # 2 equal-weight positions → each would be 0.5 without cap
        for i, ticker in enumerate(["AAA", "BBB"], start=1):
            store.upsert_asset_registry_entry(
                AssetRegistryEntry(asset_id=f"asset-{i}", ticker=ticker, source="test")
            )
            store.write_backtest_snapshot(
                BacktestSnapshot(
                    snapshot_id=f"snap-{i}",
                    alert_id=f"a{i}",
                    asset_id=f"asset-{i}",
                    signal_date=date(2026, 3, 1),
                    composite_score=0.9,
                    created_at=ts,
                )
            )

        def _fetch(ticker: str, start: date, end: date):
            return 0.05

        result = PortfolioBacktester(
            store,
            PortfolioBacktestConfig(
                n_holdings=2,
                rebalance_freq_days=30,
                max_single_position_weight=0.30,
            ),
            price_fetcher=_fetch,
        ).run()
    finally:
        store.close()

    for entry in result.position_log:
        weights_seen.append(float(entry["weight"]))

    assert all(w <= 0.30 + 1e-9 for w in weights_seen), (
        f"Some positions exceeded cap: {weights_seen}"
    )


def test_max_single_position_weight_none_does_not_change_behaviour():
    """max_single_position_weight=None (default) must produce the same result as before."""
    store = KnowledgeStore(":memory:")
    ts = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
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

        def _fetch(ticker: str, start: date, end: date):
            return 0.05

        result_default = PortfolioBacktester(
            store,
            PortfolioBacktestConfig(n_holdings=1, rebalance_freq_days=30),
            price_fetcher=_fetch,
        ).run()
        result_none = PortfolioBacktester(
            store,
            PortfolioBacktestConfig(
                n_holdings=1, rebalance_freq_days=30, max_single_position_weight=None
            ),
            price_fetcher=_fetch,
        ).run()
    finally:
        store.close()

    assert result_default.evaluated_positions == result_none.evaluated_positions
    assert abs(result_default.sharpe_ratio - result_none.sharpe_ratio) < 1e-9
