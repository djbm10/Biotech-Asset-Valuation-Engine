"""
Portfolio experiment framework for the strategy pivot.

Runs a fixed matrix of strategy variants against the same replay period using
the existing replay trade set, paired excess returns, and fast post-hoc
filters instead of re-running the historical replay loop.

Usage
-----
    python -m bve.analysis.portfolio_experiments --run-id <run_id>
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Mapping, Optional

import numpy as np

from bve.analysis.alpha_validation import (
    DEFAULT_BENCHMARK_TICKER,
    OUTPUT_DIR,
    _compute_t_statistic,
    _download_yfinance_prices,
    _lookup_close,
)
from bve.analysis.edge_decomposition import EnrichedTrade, _alpha_csv_path, _load_enriched_trades
from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore


PriceSeriesFetcher = Callable[[str, date, date], Mapping[date, float]]
RETURN_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "trade_return": ("trade_return", "trade_return_pct"),
    "xbi_return": ("xbi_return", "xbi_return_pct"),
    "excess_return": ("excess_return", "excess_return_pct"),
}


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    hold_days: int
    top_k: int
    first_entry_only: bool
    require_catalyst_within_days: int
    loss_block_threshold_pct: float = -15.0
    loss_block_weeks: int = 8
    max_consecutive_losses: int = 3
    sizing: str = "equal"


@dataclass(frozen=True)
class ExperimentResult:
    name: str
    n_trades: int
    n_unique_assets: int
    mean_excess_return: float
    median_excess_return: float
    excess_hit_rate: float
    std_excess: float
    t_stat: float
    p_value: float
    max_drawdown_pct: float
    sharpe_ratio: float


@dataclass(frozen=True)
class ExperimentTrade:
    trade_id: str
    asset_id: str
    ticker: str
    entry_date: date
    exit_date: date
    trade_return: float
    xbi_return: float
    excess_return: float
    composite_score: float
    days_to_catalyst: Optional[int]
    entry_kind: str


@dataclass(frozen=True)
class PortfolioExperimentReport:
    run_id: str
    start_date: date
    end_date: date
    results: list[ExperimentResult]
    best_variant: str
    csv_path: Path


def _parse_date(raw: object) -> date:
    return date.fromisoformat(str(raw)[:10])


def _results_csv_path(output_dir: Path, run_id: str) -> Path:
    return output_dir / f"portfolio_experiments_{run_id}.csv"


def _parse_float_value(raw: object) -> Optional[float]:
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    if math.isnan(value):
        return None
    return value


def _row_float(row: Mapping[str, str], canonical_name: str) -> Optional[float]:
    for candidate in RETURN_COLUMN_ALIASES[canonical_name]:
        value = _parse_float_value(row.get(candidate, ""))
        if value is not None:
            return value
    return None


def _load_alpha_trade_overrides(csv_path: Path) -> dict[str, dict[str, float]]:
    """Load numeric return fields from the alpha-validation CSV."""
    if not csv_path.exists():
        return {}

    overrides: dict[str, dict[str, float]] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            trade_id = str(row.get("trade_id", "")).strip()
            if not trade_id:
                continue

            trade_return = _row_float(row, "trade_return")
            xbi_return = _row_float(row, "xbi_return")
            excess_return = _row_float(row, "excess_return")
            if trade_return is None or xbi_return is None or excess_return is None:
                continue

            overrides[trade_id] = {
                "trade_return": trade_return,
                "xbi_return": xbi_return,
                "excess_return": excess_return,
            }
    return overrides


def _to_experiment_trades(trades: list[EnrichedTrade]) -> list[ExperimentTrade]:
    return [
        ExperimentTrade(
            trade_id=trade.trade_id,
            asset_id=trade.asset_id,
            ticker=trade.ticker,
            entry_date=trade.entry_date,
            exit_date=trade.exit_date,
            trade_return=trade.trade_return,
            xbi_return=trade.xbi_return,
            excess_return=trade.excess_return,
            composite_score=trade.composite_score,
            days_to_catalyst=trade.days_to_catalyst,
            entry_kind=trade.entry_kind,
        )
        for trade in trades
    ]


class ReplayPriceCache:
    """Cached price lookups for replay asset tickers and XBI."""

    def __init__(
        self,
        *,
        replay_db_path: str,
        benchmark_ticker: str,
        benchmark_price_fetcher: Optional[PriceSeriesFetcher] = None,
    ) -> None:
        self.replay_db_path = replay_db_path
        self.benchmark_ticker = benchmark_ticker
        self.benchmark_price_fetcher = benchmark_price_fetcher or _download_yfinance_prices
        self.asset_prices_by_ticker: dict[str, dict[date, float]] = {}
        self.benchmark_prices: dict[date, float] = {}

    def _missing_required_dates(
        self,
        prices: Mapping[date, float],
        required_dates: set[date],
    ) -> bool:
        return any(_lookup_close(prices, required_date) is None for required_date in required_dates)

    def warm(
        self,
        trades: list[ExperimentTrade],
        *,
        max_hold_days: int,
    ) -> None:
        """Load all price data needed for the experiment matrix."""
        if not trades:
            self.asset_prices_by_ticker = {}
            self.benchmark_prices = {}
            return

        tickers = sorted({trade.ticker for trade in trades})
        db_tickers = tickers if self.benchmark_ticker in tickers else [*tickers, self.benchmark_ticker]
        min_entry = min(trade.entry_date for trade in trades)
        max_exit = max(trade.entry_date + timedelta(days=max_hold_days) for trade in trades)

        store = ReplayStore(self.replay_db_path)
        try:
            placeholders = ",".join("?" for _ in db_tickers)
            rows = store._conn.execute(
                "SELECT ticker, price_date, close_usd FROM historical_prices "
                f"WHERE ticker IN ({placeholders}) AND price_date >= ? AND price_date <= ?",
                (*db_tickers, (min_entry - timedelta(days=7)).isoformat(), max_exit.isoformat()),
            ).fetchall()
        finally:
            store.close()

        prices: dict[str, dict[date, float]] = {ticker: {} for ticker in tickers}
        benchmark_prices: dict[date, float] = {}
        for row in rows:
            ticker = str(row["ticker"])
            price_date = _parse_date(row["price_date"])
            close_usd = float(row["close_usd"])
            if ticker == self.benchmark_ticker:
                benchmark_prices[price_date] = close_usd
                continue
            if ticker in prices:
                prices[ticker][price_date] = close_usd
        self.asset_prices_by_ticker = prices
        self.benchmark_prices = benchmark_prices

        required_dates_by_ticker: dict[str, set[date]] = defaultdict(set)
        for trade in trades:
            required_dates_by_ticker[trade.ticker].add(trade.entry_date)
            required_dates_by_ticker[trade.ticker].add(trade.entry_date + timedelta(days=max_hold_days))

        for ticker in tickers:
            if not self._missing_required_dates(
                self.asset_prices_by_ticker.get(ticker, {}),
                required_dates_by_ticker[ticker],
            ):
                continue
            fetched = dict(self.benchmark_price_fetcher(ticker, min_entry, max_exit))
            if fetched:
                self.asset_prices_by_ticker[ticker].update(fetched)

        benchmark_required_dates = {
            trade.entry_date for trade in trades
        } | {
            trade.entry_date + timedelta(days=max_hold_days) for trade in trades
        }
        benchmark_needs_fetch = self._missing_required_dates(
            self.benchmark_prices,
            benchmark_required_dates,
        )
        if benchmark_needs_fetch:
            fetched = dict(self.benchmark_price_fetcher(self.benchmark_ticker, min_entry, max_exit))
            if fetched:
                self.benchmark_prices.update(fetched)

    def asset_return(self, ticker: str, entry_date: date, exit_date: date) -> Optional[float]:
        prices = self.asset_prices_by_ticker.get(ticker, {})
        entry_price = _lookup_close(prices, entry_date)
        exit_price = _lookup_close(prices, exit_date)
        if entry_price is None or exit_price is None or entry_price == 0.0:
            return None
        return ((exit_price / entry_price) - 1.0) * 100.0

    def benchmark_return(self, entry_date: date, exit_date: date) -> Optional[float]:
        entry_price = _lookup_close(self.benchmark_prices, entry_date)
        exit_price = _lookup_close(self.benchmark_prices, exit_date)
        if entry_price is None or exit_price is None or entry_price == 0.0:
            return None
        return ((exit_price / entry_price) - 1.0) * 100.0


def _apply_top_k_filter(trades: list[ExperimentTrade], top_k: int) -> list[ExperimentTrade]:
    """Keep only the top-K trades by score within each entry date."""
    grouped: dict[date, list[ExperimentTrade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.entry_date].append(trade)

    kept: list[ExperimentTrade] = []
    for entry_date in sorted(grouped):
        ranked = sorted(
            grouped[entry_date],
            key=lambda trade: (-trade.composite_score, trade.trade_id),
        )
        kept.extend(ranked[:top_k])
    return kept


def _apply_first_entry_only_filter(trades: list[ExperimentTrade]) -> list[ExperimentTrade]:
    """Keep only the chronologically first trade for each asset."""
    grouped: dict[str, list[ExperimentTrade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.asset_id].append(trade)

    kept: list[ExperimentTrade] = []
    for asset_trades in grouped.values():
        first = min(asset_trades, key=lambda trade: (trade.entry_date, trade.trade_id))
        kept.append(first)
    kept.sort(key=lambda trade: (trade.entry_date, -trade.composite_score, trade.trade_id))
    return kept


def _apply_catalyst_gate(
    trades: list[ExperimentTrade],
    require_catalyst_within_days: int,
) -> list[ExperimentTrade]:
    """Filter trades by catalyst proximity."""
    if require_catalyst_within_days <= 0:
        return list(trades)
    return [
        trade
        for trade in trades
        if trade.days_to_catalyst is not None
        and trade.days_to_catalyst <= require_catalyst_within_days
    ]


def _group_weights(trades: list[ExperimentTrade], sizing: str) -> dict[str, float]:
    """Return trade_id -> weight for one decision-date cohort."""
    if not trades:
        return {}
    if sizing == "convex":
        raw = np.array([trade.composite_score ** 2 for trade in trades], dtype=float)
    else:
        raw = np.ones(len(trades), dtype=float)
    denom = float(raw.sum())
    if denom <= 0.0:
        weights = np.ones(len(trades), dtype=float) / len(trades)
    else:
        weights = raw / denom
    return {
        trade.trade_id: float(weight)
        for trade, weight in zip(trades, weights)
    }


def _reprice_trades_for_hold_days(
    trades: list[ExperimentTrade],
    *,
    hold_days: int,
    price_cache: ReplayPriceCache,
) -> list[ExperimentTrade]:
    """Recompute trade and benchmark returns for a new hold period."""
    repriced: list[ExperimentTrade] = []
    for trade in trades:
        new_exit = trade.entry_date + timedelta(days=hold_days)
        trade_return = price_cache.asset_return(trade.ticker, trade.entry_date, new_exit)
        benchmark_return = price_cache.benchmark_return(trade.entry_date, new_exit)
        if trade_return is None or benchmark_return is None:
            continue
        repriced.append(ExperimentTrade(
            trade_id=trade.trade_id,
            asset_id=trade.asset_id,
            ticker=trade.ticker,
            entry_date=trade.entry_date,
            exit_date=new_exit,
            trade_return=round(trade_return, 6),
            xbi_return=round(benchmark_return, 6),
            excess_return=round(trade_return - benchmark_return, 6),
            composite_score=trade.composite_score,
            days_to_catalyst=trade.days_to_catalyst,
            entry_kind=trade.entry_kind,
        ))
    return repriced


def _decision_date_returns(
    trades: list[ExperimentTrade],
    *,
    sizing: str,
) -> list[float]:
    """Convert trade-level excess returns into per-date portfolio excess returns."""
    grouped: dict[date, list[ExperimentTrade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.entry_date].append(trade)

    returns: list[float] = []
    for entry_date in sorted(grouped):
        cohort = grouped[entry_date]
        weights = _group_weights(cohort, sizing)
        returns.append(sum(weights[trade.trade_id] * trade.excess_return for trade in cohort))
    return returns


def _max_drawdown_pct(period_returns: list[float]) -> float:
    if not period_returns:
        return 0.0
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for ret in period_returns:
        equity *= 1.0 + (ret / 100.0)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return max_drawdown * 100.0


def _annualization_factor(period_dates: list[date]) -> float:
    if len(period_dates) < 2:
        return math.sqrt(52.0)
    diffs = [
        max(1, (period_dates[idx] - period_dates[idx - 1]).days)
        for idx in range(1, len(period_dates))
    ]
    avg_spacing_days = float(np.mean(diffs))
    return math.sqrt(365.0 / avg_spacing_days)


def _summarize_experiment(name: str, trades: list[ExperimentTrade], *, sizing: str) -> ExperimentResult:
    """Compute experiment metrics from filtered trades."""
    if not trades:
        return ExperimentResult(
            name=name,
            n_trades=0,
            n_unique_assets=0,
            mean_excess_return=0.0,
            median_excess_return=0.0,
            excess_hit_rate=0.0,
            std_excess=0.0,
            t_stat=0.0,
            p_value=1.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
        )

    grouped_dates = sorted({trade.entry_date for trade in trades})
    period_returns = np.array(_decision_date_returns(trades, sizing=sizing), dtype=float)
    mean_excess = float(period_returns.mean())
    median_excess = float(np.median(period_returns))
    std_excess = float(period_returns.std(ddof=1)) if period_returns.size > 1 else 0.0
    hit_rate = float(np.mean(period_returns > 0.0))
    t_stat, p_value = _compute_t_statistic(mean_excess, std_excess, period_returns.size)
    t_value = 0.0 if t_stat is None or math.isnan(t_stat) else float(t_stat)
    p_value_num = 1.0 if p_value is None or math.isnan(p_value) else float(p_value)
    ann_factor = _annualization_factor(grouped_dates)
    sharpe = 0.0 if std_excess == 0.0 else ann_factor * (mean_excess / std_excess)
    return ExperimentResult(
        name=name,
        n_trades=len(trades),
        n_unique_assets=len({trade.asset_id for trade in trades}),
        mean_excess_return=mean_excess,
        median_excess_return=median_excess,
        excess_hit_rate=hit_rate,
        std_excess=std_excess,
        t_stat=t_value,
        p_value=p_value_num,
        max_drawdown_pct=_max_drawdown_pct(period_returns.tolist()),
        sharpe_ratio=float(sharpe),
    )


def _best_result(results: list[ExperimentResult]) -> ExperimentResult:
    eligible = [result for result in results if result.n_trades >= 20]
    pool = eligible or [result for result in results if result.n_trades > 0]
    if not pool:
        return results[0]
    return max(pool, key=lambda result: (result.t_stat, result.mean_excess_return, -result.p_value))


def _format_pct(value: float, *, show_sign: bool = False) -> str:
    fmt = "{:+.2f}%" if show_sign else "{:.2f}%"
    return fmt.format(value)


def render_portfolio_experiment_report(report: PortfolioExperimentReport) -> str:
    sep = "=" * 60
    divider = "-" * 57
    lines = [
        sep,
        "PORTFOLIO EXPERIMENT RESULTS",
        f"Baseline run: {report.run_id}",
        f"Period: {report.start_date.isoformat()} -> {report.end_date.isoformat()}",
        sep,
        "",
        "Experiment          N    Excess   HitRate  t-stat  Sharpe",
        divider,
    ]
    for result in report.results:
        lines.append(
            f"{result.name:<18} {result.n_trades:>3}  "
            f"{_format_pct(result.mean_excess_return, show_sign=True):>8}  "
            f"{result.excess_hit_rate * 100.0:>6.1f}%  "
            f"{result.t_stat:>6.2f}  "
            f"{result.sharpe_ratio:>6.2f}"
        )

    lines.extend([
        "",
        f"BEST VARIANT: {report.best_variant} (highest t-stat with N >= 20)",
        sep,
    ])
    return "\n".join(lines)


class PortfolioExperimentRunner:
    """Run the 12-experiment pivot framework against a replay run."""

    def __init__(
        self,
        *,
        replay_db_path: str = str(REPLAY_STORE_PATH),
        benchmark_ticker: str = DEFAULT_BENCHMARK_TICKER,
        output_dir: Path = OUTPUT_DIR,
        benchmark_price_fetcher: Optional[PriceSeriesFetcher] = None,
    ) -> None:
        self.replay_db_path = replay_db_path
        self.benchmark_ticker = benchmark_ticker
        self.output_dir = output_dir
        self.benchmark_price_fetcher = benchmark_price_fetcher

    def _load_run_dates(self, run_id: str) -> tuple[date, date]:
        store = ReplayStore(self.replay_db_path)
        try:
            run = store.get_run(run_id)
        finally:
            store.close()
        if run is None:
            raise ValueError(f"Replay run not found: {run_id}")
        return _parse_date(run["start_date"]), _parse_date(run["end_date"])

    def _base_trades(self, run_id: str) -> list[ExperimentTrade]:
        enriched = _load_enriched_trades(
            run_id=run_id,
            replay_db_path=self.replay_db_path,
            benchmark_ticker=self.benchmark_ticker,
            output_dir=self.output_dir,
            price_fetcher=self.benchmark_price_fetcher,
        )
        overrides = _load_alpha_trade_overrides(_alpha_csv_path(self.output_dir, run_id))
        trades = _to_experiment_trades(enriched)
        if not overrides:
            return trades

        normalized: list[ExperimentTrade] = []
        for trade in trades:
            override = overrides.get(trade.trade_id)
            if override is None:
                normalized.append(trade)
                continue
            normalized.append(ExperimentTrade(
                trade_id=trade.trade_id,
                asset_id=trade.asset_id,
                ticker=trade.ticker,
                entry_date=trade.entry_date,
                exit_date=trade.exit_date,
                trade_return=override["trade_return"],
                xbi_return=override["xbi_return"],
                excess_return=override["excess_return"],
                composite_score=trade.composite_score,
                days_to_catalyst=trade.days_to_catalyst,
                entry_kind=trade.entry_kind,
            ))
        return normalized

    def _experiment_configs(self, run_id: str) -> list[ExperimentConfig]:
        base_trades = self._base_trades(run_id)
        price_cache = ReplayPriceCache(
            replay_db_path=self.replay_db_path,
            benchmark_ticker=self.benchmark_ticker,
            benchmark_price_fetcher=self.benchmark_price_fetcher,
        )
        price_cache.warm(base_trades, max_hold_days=90)

        repriced = {
            hold_days: _reprice_trades_for_hold_days(base_trades, hold_days=hold_days, price_cache=price_cache)
            for hold_days in (35, 60, 90)
        }

        hold_configs = [
            ExperimentConfig(name="hold_35d", hold_days=35, top_k=2, first_entry_only=False, require_catalyst_within_days=0),
            ExperimentConfig(name="hold_60d", hold_days=60, top_k=2, first_entry_only=False, require_catalyst_within_days=0),
            ExperimentConfig(name="hold_90d", hold_days=90, top_k=2, first_entry_only=False, require_catalyst_within_days=0),
        ]
        hold_results = [self._run_single(config, repriced[config.hold_days]) for config in hold_configs]
        best_hold = _best_result(hold_results)
        best_hold_days = next(config.hold_days for config in hold_configs if config.name == best_hold.name)

        concentration_configs = [
            ExperimentConfig(name="top2", hold_days=best_hold_days, top_k=2, first_entry_only=False, require_catalyst_within_days=0),
            ExperimentConfig(name="top3", hold_days=best_hold_days, top_k=3, first_entry_only=False, require_catalyst_within_days=0),
            ExperimentConfig(name="top5", hold_days=best_hold_days, top_k=5, first_entry_only=False, require_catalyst_within_days=0),
        ]
        concentration_results = [
            self._run_single(config, repriced[best_hold_days]) for config in concentration_configs
        ]
        best_conc = _best_result(concentration_results)
        best_top_k = next(config.top_k for config in concentration_configs if config.name == best_conc.name)

        entry_configs = [
            ExperimentConfig(name="first_entry_only", hold_days=best_hold_days, top_k=best_top_k, first_entry_only=True, require_catalyst_within_days=0),
            ExperimentConfig(name="controlled_reentry", hold_days=best_hold_days, top_k=best_top_k, first_entry_only=False, require_catalyst_within_days=0),
        ]
        entry_results = [self._run_single(config, repriced[best_hold_days]) for config in entry_configs]
        best_entry = _best_result(entry_results)
        best_entry_only = next(config.first_entry_only for config in entry_configs if config.name == best_entry.name)

        catalyst_configs = [
            ExperimentConfig(name="catalyst_45d", hold_days=best_hold_days, top_k=best_top_k, first_entry_only=best_entry_only, require_catalyst_within_days=45),
            ExperimentConfig(name="catalyst_14d", hold_days=best_hold_days, top_k=best_top_k, first_entry_only=best_entry_only, require_catalyst_within_days=14),
            ExperimentConfig(name="catalyst_7d", hold_days=best_hold_days, top_k=best_top_k, first_entry_only=best_entry_only, require_catalyst_within_days=7),
            ExperimentConfig(name="no_catalyst", hold_days=best_hold_days, top_k=best_top_k, first_entry_only=best_entry_only, require_catalyst_within_days=0),
        ]
        return [
            *hold_configs,
            *concentration_configs,
            *entry_configs,
            *catalyst_configs,
        ]

    def _filter_trades(self, config: ExperimentConfig, trades: list[ExperimentTrade]) -> list[ExperimentTrade]:
        filtered = _apply_catalyst_gate(trades, config.require_catalyst_within_days)
        if config.first_entry_only:
            filtered = _apply_first_entry_only_filter(filtered)
        filtered = _apply_top_k_filter(filtered, config.top_k)
        filtered.sort(key=lambda trade: (trade.entry_date, -trade.composite_score, trade.trade_id))
        return filtered

    def _run_single(self, config: ExperimentConfig, repriced_trades: list[ExperimentTrade]) -> ExperimentResult:
        filtered = self._filter_trades(config, repriced_trades)
        return _summarize_experiment(config.name, filtered, sizing=config.sizing)

    def _export_csv(self, run_id: str, configs: list[ExperimentConfig], results: list[ExperimentResult]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = _results_csv_path(self.output_dir, run_id)
        config_by_name = {config.name: config for config in configs}
        fieldnames = [
            "name",
            "hold_days",
            "top_k",
            "first_entry_only",
            "require_catalyst_within_days",
            "loss_block_threshold_pct",
            "loss_block_weeks",
            "max_consecutive_losses",
            "sizing",
            "n_trades",
            "n_unique_assets",
            "mean_excess_return",
            "median_excess_return",
            "excess_hit_rate",
            "std_excess",
            "t_stat",
            "p_value",
            "max_drawdown_pct",
            "sharpe_ratio",
        ]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for result in results:
                config = config_by_name[result.name]
                writer.writerow({
                    "name": result.name,
                    "hold_days": config.hold_days,
                    "top_k": config.top_k,
                    "first_entry_only": config.first_entry_only,
                    "require_catalyst_within_days": config.require_catalyst_within_days,
                    "loss_block_threshold_pct": config.loss_block_threshold_pct,
                    "loss_block_weeks": config.loss_block_weeks,
                    "max_consecutive_losses": config.max_consecutive_losses,
                    "sizing": config.sizing,
                    "n_trades": result.n_trades,
                    "n_unique_assets": result.n_unique_assets,
                    "mean_excess_return": result.mean_excess_return,
                    "median_excess_return": result.median_excess_return,
                    "excess_hit_rate": result.excess_hit_rate,
                    "std_excess": result.std_excess,
                    "t_stat": result.t_stat,
                    "p_value": result.p_value,
                    "max_drawdown_pct": result.max_drawdown_pct,
                    "sharpe_ratio": result.sharpe_ratio,
                })
        return path

    def run(self, run_id: str) -> PortfolioExperimentReport:
        start_date, end_date = self._load_run_dates(run_id)
        configs = self._experiment_configs(run_id)
        base_trades = self._base_trades(run_id)
        price_cache = ReplayPriceCache(
            replay_db_path=self.replay_db_path,
            benchmark_ticker=self.benchmark_ticker,
            benchmark_price_fetcher=self.benchmark_price_fetcher,
        )
        price_cache.warm(base_trades, max_hold_days=90)
        repriced_by_hold = {
            hold_days: _reprice_trades_for_hold_days(base_trades, hold_days=hold_days, price_cache=price_cache)
            for hold_days in {config.hold_days for config in configs}
        }
        results = [self._run_single(config, repriced_by_hold[config.hold_days]) for config in configs]
        best = _best_result(results)
        csv_path = self._export_csv(run_id, configs, results)
        return PortfolioExperimentReport(
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            results=results,
            best_variant=best.name,
            csv_path=csv_path,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run portfolio experiments on a replay run")
    parser.add_argument("--run-id", required=True, help="Replay run ID")
    parser.add_argument(
        "--db",
        default=str(REPLAY_STORE_PATH),
        help="Replay SQLite store path",
    )
    parser.add_argument(
        "--benchmark",
        default=DEFAULT_BENCHMARK_TICKER,
        help="Benchmark ticker used for paired excess returns",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    report = PortfolioExperimentRunner(
        replay_db_path=args.db,
        benchmark_ticker=args.benchmark,
    ).run(args.run_id)
    print(render_portfolio_experiment_report(report))


if __name__ == "__main__":
    main()
