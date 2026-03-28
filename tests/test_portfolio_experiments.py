from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from bve.analysis.portfolio_experiments import (
    PortfolioExperimentRunner,
    ReplayPriceCache,
    _load_alpha_trade_overrides,
    _apply_first_entry_only_filter,
    _apply_top_k_filter,
    _group_weights,
    _reprice_trades_for_hold_days,
)
from bve.intelligence.replay_policy import ReplayDecision
from bve.ops.historical_replay import ReplayStore


def _static_price_fetcher(prices: dict[date, float]):
    def _fetch(_ticker: str, _start: date, _end: date) -> dict[date, float]:
        return prices

    return _fetch


def _seed_trade(
    store: ReplayStore,
    run_id: str,
    *,
    asset_id: str,
    ticker: str,
    entry_date: date,
    exit_date: date,
    return_pct: float,
    composite_score: float,
    attribution_type: str = "market_drift",
) -> None:
    decision = ReplayDecision(
        asset_id=asset_id,
        ticker=ticker,
        recommended_action="buy",
        recommended_size_pct=0.05,
        composite_score=composite_score,
        decided_at=entry_date,
    )
    decision_id = store.insert_decision(run_id, decision, entry_price=100.0)
    store.close_decision(
        decision_id=decision_id,
        exit_price=100.0 + return_pct,
        exit_date=exit_date,
        return_pct=return_pct,
        attribution_type=attribution_type,
    )


def _seed_asset_price_path(
    store: ReplayStore,
    ticker: str,
    entry_date: date,
    *,
    price_35d: float,
    price_60d: float,
    price_90d: float,
) -> None:
    rows = [
        (entry_date, 100.0),
        (entry_date + timedelta(days=35), price_35d),
        (entry_date + timedelta(days=60), price_60d),
        (entry_date + timedelta(days=90), price_90d),
    ]
    store.insert_prices(ticker, rows)


def _benchmark_prices() -> dict[date, float]:
    return {
        date(2025, 1, 6): 100.0,
        date(2025, 2, 10): 101.0,
        date(2025, 3, 7): 103.0,
        date(2025, 4, 6): 105.0,
        date(2025, 1, 13): 100.0,
        date(2025, 2, 17): 101.0,
        date(2025, 3, 14): 103.0,
        date(2025, 4, 13): 105.0,
    }


def _seed_run(db_path: Path) -> str:
    store = ReplayStore(str(db_path))
    run_id = store.create_run(
        start_date=date(2025, 1, 6),
        end_date=date(2025, 4, 13),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v2.0",
        strategy_version="top2_add",
    )

    _seed_trade(
        store,
        run_id,
        asset_id="a-alny",
        ticker="ALNY",
        entry_date=date(2025, 1, 6),
        exit_date=date(2025, 2, 10),
        return_pct=10.0,
        composite_score=0.90,
    )
    _seed_trade(
        store,
        run_id,
        asset_id="a-srpt",
        ticker="SRPT",
        entry_date=date(2025, 1, 6),
        exit_date=date(2025, 2, 10),
        return_pct=4.0,
        composite_score=0.70,
    )
    _seed_trade(
        store,
        run_id,
        asset_id="a-imvt",
        ticker="IMVT",
        entry_date=date(2025, 1, 6),
        exit_date=date(2025, 2, 10),
        return_pct=-2.0,
        composite_score=0.40,
    )
    _seed_trade(
        store,
        run_id,
        asset_id="a-alny",
        ticker="ALNY",
        entry_date=date(2025, 1, 13),
        exit_date=date(2025, 2, 17),
        return_pct=8.0,
        composite_score=0.80,
    )
    _seed_trade(
        store,
        run_id,
        asset_id="a-arvn",
        ticker="ARVN",
        entry_date=date(2025, 1, 13),
        exit_date=date(2025, 2, 17),
        return_pct=7.0,
        composite_score=0.60,
    )
    _seed_trade(
        store,
        run_id,
        asset_id="a-vktx",
        ticker="VKTX",
        entry_date=date(2025, 1, 13),
        exit_date=date(2025, 2, 17),
        return_pct=-5.0,
        composite_score=0.30,
    )

    _seed_asset_price_path(store, "ALNY", date(2025, 1, 6), price_35d=110.0, price_60d=125.0, price_90d=140.0)
    _seed_asset_price_path(store, "SRPT", date(2025, 1, 6), price_35d=104.0, price_60d=108.0, price_90d=112.0)
    _seed_asset_price_path(store, "IMVT", date(2025, 1, 6), price_35d=98.0, price_60d=102.0, price_90d=106.0)
    _seed_asset_price_path(store, "ALNY", date(2025, 1, 13), price_35d=108.0, price_60d=118.0, price_90d=130.0)
    _seed_asset_price_path(store, "ARVN", date(2025, 1, 13), price_35d=107.0, price_60d=111.0, price_90d=116.0)
    _seed_asset_price_path(store, "VKTX", date(2025, 1, 13), price_35d=95.0, price_60d=97.0, price_90d=100.0)

    store.insert_event(
        asset_id="a-alny",
        ticker="ALNY",
        event_type="trial_readout",
        announced_at=date(2025, 1, 11),
        effective_date=date(2025, 1, 11),
        outcome_label="positive",
        headline="ALNY event 1",
    )
    store.insert_event(
        asset_id="a-srpt",
        ticker="SRPT",
        event_type="trial_readout",
        announced_at=date(2025, 1, 26),
        effective_date=date(2025, 1, 26),
        outcome_label="positive",
        headline="SRPT event",
    )
    store.insert_event(
        asset_id="a-alny",
        ticker="ALNY",
        event_type="trial_readout",
        announced_at=date(2025, 3, 4),
        effective_date=date(2025, 3, 4),
        outcome_label="positive",
        headline="ALNY event 2",
    )
    store.insert_event(
        asset_id="a-arvn",
        ticker="ARVN",
        event_type="trial_readout",
        announced_at=date(2025, 1, 23),
        effective_date=date(2025, 1, 23),
        outcome_label="positive",
        headline="ARVN event",
    )
    store.close()
    return run_id


def test_top_k_filter_keeps_correct_number_of_trades_per_date(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_run(db_path)
    runner = PortfolioExperimentRunner(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        benchmark_price_fetcher=_static_price_fetcher(_benchmark_prices()),
    )
    trades = runner._base_trades(run_id)

    kept = _apply_top_k_filter(trades, top_k=2)
    counts: dict[date, int] = {}
    for trade in kept:
        counts[trade.entry_date] = counts.get(trade.entry_date, 0) + 1

    assert len(kept) == 4
    assert set(counts.values()) == {2}


def test_first_entry_filter_keeps_only_first_trade_per_asset(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_run(db_path)
    runner = PortfolioExperimentRunner(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        benchmark_price_fetcher=_static_price_fetcher(_benchmark_prices()),
    )
    trades = runner._base_trades(run_id)

    kept = _apply_first_entry_only_filter(trades)

    assert len(kept) == 5
    assert sum(1 for trade in kept if trade.asset_id == "a-alny") == 1


def test_hold_period_change_recomputes_xbi_return_correctly(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_run(db_path)
    runner = PortfolioExperimentRunner(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        benchmark_price_fetcher=_static_price_fetcher(_benchmark_prices()),
    )
    trades = runner._base_trades(run_id)
    price_cache = ReplayPriceCache(
        replay_db_path=str(db_path),
        benchmark_ticker="XBI",
        benchmark_price_fetcher=_static_price_fetcher(_benchmark_prices()),
    )
    price_cache.warm(trades, max_hold_days=90)

    repriced = _reprice_trades_for_hold_days(
        [trade for trade in trades if trade.asset_id == "a-alny" and trade.entry_date == date(2025, 1, 6)],
        hold_days=60,
        price_cache=price_cache,
    )

    assert len(repriced) == 1
    assert repriced[0].xbi_return == 3.0
    assert repriced[0].trade_return == 25.0
    assert repriced[0].excess_return == 22.0


def test_convex_sizing_weights_sum_to_one_per_date(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_run(db_path)
    runner = PortfolioExperimentRunner(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        benchmark_price_fetcher=_static_price_fetcher(_benchmark_prices()),
    )
    trades = [trade for trade in runner._base_trades(run_id) if trade.entry_date == date(2025, 1, 6)]

    weights = _group_weights(trades, sizing="convex")

    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_alpha_csv_loader_accepts_string_numeric_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "alpha_validation.csv"
    csv_path.write_text(
        "\n".join([
            "trade_id,asset_id,ticker,entry_date,exit_date,trade_return,xbi_return,excess_return",
            "t-1,a-alny,ALNY,2025-01-06,2025-02-10,-12.789155,1.5,-14.289155",
            "t-2,a-srpt,SRPT,2025-01-13,2025-02-17,8.25,-2.0,10.25",
        ]),
        encoding="utf-8",
    )

    overrides = _load_alpha_trade_overrides(csv_path)

    assert overrides["t-1"]["trade_return"] == -12.789155
    assert overrides["t-1"]["xbi_return"] == 1.5
    assert overrides["t-1"]["excess_return"] == -14.289155
    assert overrides["t-2"]["excess_return"] == 10.25


def test_alpha_csv_loader_accepts_pct_alias_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "alpha_validation_alias.csv"
    csv_path.write_text(
        "\n".join([
            "trade_id,asset_id,ticker,entry_date,exit_date,trade_return_pct,xbi_return_pct,excess_return_pct",
            "t-3,a-vktx,VKTX,2025-01-06,2025-02-10,4.0,-1.25,5.25",
        ]),
        encoding="utf-8",
    )

    overrides = _load_alpha_trade_overrides(csv_path)

    assert overrides["t-3"]["trade_return"] == 4.0
    assert overrides["t-3"]["xbi_return"] == -1.25
    assert overrides["t-3"]["excess_return"] == 5.25


def test_all_12_experiments_produce_valid_results(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_run(db_path)
    runner = PortfolioExperimentRunner(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        benchmark_price_fetcher=_static_price_fetcher(_benchmark_prices()),
    )

    report = runner.run(run_id)

    assert len(report.results) == 12
    assert all(result.n_trades >= 0 for result in report.results)
    assert report.best_variant in {result.name for result in report.results}


def test_results_csv_is_written_correctly(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite"
    run_id = _seed_run(db_path)
    runner = PortfolioExperimentRunner(
        replay_db_path=str(db_path),
        output_dir=tmp_path / "analysis",
        benchmark_price_fetcher=_static_price_fetcher(_benchmark_prices()),
    )

    report = runner.run(run_id)

    assert report.csv_path.exists()
    header = report.csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header == (
        "name,hold_days,top_k,first_entry_only,require_catalyst_within_days,"
        "loss_block_threshold_pct,loss_block_weeks,max_consecutive_losses,sizing,"
        "n_trades,n_unique_assets,mean_excess_return,median_excess_return,"
        "excess_hit_rate,std_excess,t_stat,p_value,max_drawdown_pct,sharpe_ratio"
    )
