from __future__ import annotations

from datetime import date, datetime, timezone

from bve.analysis.portfolio_backtest import (
    OverlayComparisonResult,
    PortfolioBacktestConfig,
    PortfolioBacktester,
    RiskOverlayConfig,
    SURVIVORSHIP_BIAS_WARNING,
    compare_overlays,
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


# ---------------------------------------------------------------------------
# RiskOverlayConfig + overlay integration tests
# ---------------------------------------------------------------------------


def _make_store_with_asset(asset_id: str, ticker: str) -> KnowledgeStore:
    store = KnowledgeStore(":memory:")
    store.upsert_asset_registry_entry(
        AssetRegistryEntry(asset_id=asset_id, ticker=ticker, source="test")
    )
    return store


def _write_snap(store: KnowledgeStore, asset_id: str, signal_date: date, score: float = 0.8) -> None:
    ts = datetime(signal_date.year, signal_date.month, signal_date.day, 12, 0, tzinfo=timezone.utc)
    store.write_backtest_snapshot(
        BacktestSnapshot(
            snapshot_id=f"snap-{asset_id}-{signal_date.isoformat()}",
            alert_id=f"a-{asset_id}",
            asset_id=asset_id,
            signal_date=signal_date,
            composite_score=score,
            created_at=ts,
        )
    )


def test_risk_overlay_config_defaults():
    cfg = RiskOverlayConfig()
    assert cfg.momentum_lookback_days == 90
    assert cfg.momentum_threshold == -0.20
    assert cfg.event_suppression_days == 90
    assert cfg.drawdown_no_add_threshold == -0.25
    assert cfg.weight_cap == 0.075


def test_overlay_momentum_filter_blocks_position():
    """Asset with trailing return below threshold should be skipped."""
    store = _make_store_with_asset("asset-1", "AAA")
    try:
        _write_snap(store, "asset-1", date(2023, 3, 1))

        def _fetch(ticker: str, start: date, end: date) -> float | None:
            # Momentum window (start < signal_dt): return below threshold
            if end <= date(2023, 3, 1):
                return -0.35  # -35% → should block
            return 0.10  # forward return

        result = PortfolioBacktester(
            store,
            PortfolioBacktestConfig(
                n_holdings=1,
                rebalance_freq_days=30,
                overlay=RiskOverlayConfig(momentum_threshold=-0.20),
            ),
            price_fetcher=_fetch,
        ).run()
    finally:
        store.close()

    # Position filtered out by momentum check
    assert result.evaluated_positions == 0
    assert result.overlay_filtered_positions == 1


def test_overlay_momentum_filter_allows_good_momentum():
    """Asset with trailing return above threshold should NOT be blocked."""
    store = _make_store_with_asset("asset-1", "AAA")
    try:
        _write_snap(store, "asset-1", date(2023, 3, 1))

        def _fetch(ticker: str, start: date, end: date) -> float | None:
            # All periods return +5%
            return 0.05

        result = PortfolioBacktester(
            store,
            PortfolioBacktestConfig(
                n_holdings=1,
                rebalance_freq_days=30,
                overlay=RiskOverlayConfig(momentum_threshold=-0.20),
            ),
            price_fetcher=_fetch,
        ).run()
    finally:
        store.close()

    assert result.evaluated_positions == 1
    assert result.overlay_filtered_positions == 0


def test_overlay_event_suppression_blocks_position():
    """Asset with a recent negative event should be suppressed."""
    store = _make_store_with_asset("asset-1", "AAA")
    try:
        _write_snap(store, "asset-1", date(2023, 3, 1))

        def _fetch(ticker: str, start: date, end: date) -> float | None:
            return 0.10

        def _neg_event(asset_id: str, as_of: date, lookback_days: int) -> bool:
            return True  # always suppress

        result = PortfolioBacktester(
            store,
            PortfolioBacktestConfig(
                n_holdings=1,
                rebalance_freq_days=30,
                overlay=RiskOverlayConfig(),
            ),
            price_fetcher=_fetch,
            negative_event_checker=_neg_event,
        ).run()
    finally:
        store.close()

    assert result.evaluated_positions == 0
    assert result.overlay_filtered_positions == 1


def test_overlay_drawdown_gate_blocks_period():
    """When portfolio is down beyond threshold from peak, new period entries are blocked.

    Period 1 return is -0.40 applied at full weight (weight_cap=1.0).  Portfolio
    equity drops to 0.598x, which is -40.2% from peak — above the -5% gate.
    Period 2 should be skipped.
    """
    store = _make_store_with_asset("asset-1", "AAA")
    try:
        _write_snap(store, "asset-1", date(2023, 1, 1), score=0.9)
        _write_snap(store, "asset-1", date(2023, 2, 1), score=0.9)

        def _fetch(ticker: str, start: date, end: date) -> float | None:
            if ticker == "XBI":
                return 0.0
            if start == date(2023, 1, 1):
                return -0.40  # period 1: large loss
            return 0.10  # period 2 / momentum window

        result = PortfolioBacktester(
            store,
            PortfolioBacktestConfig(
                n_holdings=1,
                rebalance_freq_days=30,
                overlay=RiskOverlayConfig(
                    drawdown_no_add_threshold=-0.05,  # gate fires at 5% drawdown
                    weight_cap=1.0,                   # full weight so drawdown = position return
                    momentum_threshold=-0.50,         # high enough that -40% won't block via momentum
                ),
            ),
            price_fetcher=_fetch,
        ).run()
    finally:
        store.close()

    # Period 1 runs; period 2 is blocked because portfolio is -40% from peak
    assert result.evaluated_positions == 1


def test_overlay_weight_cap_applied():
    """RiskOverlayConfig.weight_cap should cap per-position weights."""
    store = KnowledgeStore(":memory:")
    ts = datetime(2023, 3, 9, 12, 0, tzinfo=timezone.utc)
    try:
        for i, ticker in enumerate(["AAA", "BBB", "CCC"], start=1):
            store.upsert_asset_registry_entry(
                AssetRegistryEntry(asset_id=f"asset-{i}", ticker=ticker, source="test")
            )
            store.write_backtest_snapshot(
                BacktestSnapshot(
                    snapshot_id=f"snap-{i}",
                    alert_id=f"a{i}",
                    asset_id=f"asset-{i}",
                    signal_date=date(2023, 3, 1),
                    composite_score=0.9,
                    created_at=ts,
                )
            )

        result = PortfolioBacktester(
            store,
            PortfolioBacktestConfig(
                n_holdings=3,
                rebalance_freq_days=30,
                overlay=RiskOverlayConfig(weight_cap=0.075),
            ),
            price_fetcher=lambda t, s, e: 0.05,
        ).run()
    finally:
        store.close()

    for entry in result.position_log:
        assert float(entry["weight"]) <= 0.075 + 1e-9, f"weight exceeded cap: {entry}"


def test_compare_overlays_returns_four_results():
    """compare_overlays returns baseline and overlay for both train and validation splits."""
    store = _make_store_with_asset("asset-1", "AAA")
    try:
        _write_snap(store, "asset-1", date(2022, 6, 1))
        _write_snap(store, "asset-1", date(2023, 2, 1))

        result = compare_overlays(
            store,
            RiskOverlayConfig(),
            train_start=date(2022, 1, 1),
            train_end=date(2022, 12, 31),
            validation_start=date(2023, 1, 1),
            validation_end=date(2023, 6, 30),
            price_fetcher=lambda t, s, e: 0.05,
        )
    finally:
        store.close()

    assert isinstance(result, OverlayComparisonResult)
    assert result.train_start == "2022-01-01"
    assert result.validation_end == "2023-06-30"
    assert isinstance(result.train_baseline.sharpe_ratio, float)
    assert isinstance(result.train_overlay.sharpe_ratio, float)


def test_compare_overlays_summary_table_contains_splits():
    """summary_table() must include both Train and Validation rows."""
    store = _make_store_with_asset("asset-1", "AAA")
    try:
        _write_snap(store, "asset-1", date(2022, 6, 1))

        result = compare_overlays(
            store,
            RiskOverlayConfig(),
            train_start=date(2022, 1, 1),
            train_end=date(2022, 12, 31),
            validation_start=date(2023, 1, 1),
            validation_end=date(2023, 6, 30),
            price_fetcher=lambda t, s, e: 0.05,
        )
    finally:
        store.close()

    table = result.summary_table()
    assert "Train" in table
    assert "Validation" in table
    assert "baseline" in table
    assert "overlay" in table
