"""Portfolio backtest over alert snapshots persisted by the intelligence pipeline."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import BacktestSnapshot, KnowledgeStore

SURVIVORSHIP_BIAS_WARNING = (
    "WARNING: This backtest does not correct for survivorship bias. Biotech tickers\n"
    "with negative outcomes may be delisted; yfinance returns NaN for delisted names,\n"
    "which are excluded from return calculations. Results will overstate performance\n"
    "until a delisting-adjusted price feed is integrated."
)


class PortfolioStrategy(str, Enum):
    TOP_N_EQUAL_WEIGHT = "top_n_equal_weight"
    SCORE_WEIGHTED = "score_weighted"
    HOLD_UNTIL_CATALYST = "hold_until_catalyst"
    CATALYST_MOMENTUM = "catalyst_momentum"


class PortfolioBacktestConfig(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    strategy: PortfolioStrategy = PortfolioStrategy.TOP_N_EQUAL_WEIGHT
    n_holdings: int = Field(default=5, ge=1)
    rebalance_freq_days: int = Field(default=30, ge=1)
    benchmark_ticker: str = "XBI"
    initial_capital: float = Field(default=1_000_000.0, gt=0.0)
    transaction_cost_bps: float = Field(default=10.0, ge=0.0)


class BacktestResult(BaseModel):
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    alpha_vs_benchmark: float
    beta_vs_benchmark: float
    information_ratio: float
    monthly_returns: list[dict[str, float | str]] = Field(default_factory=list)
    equity_curve: list[dict[str, float | str]] = Field(default_factory=list)
    benchmark_equity_curve: list[dict[str, float | str]] = Field(default_factory=list)
    position_log: list[dict[str, object]] = Field(default_factory=list)
    n_signals: int = 0
    snapshot_coverage_pct: float = 0.0
    assets_excluded_missing_prices: int = 0
    missing_price_positions: int = 0
    evaluated_positions: int = 0
    notes: list[str] = Field(default_factory=list)
    disclaimer: str = SURVIVORSHIP_BIAS_WARNING


PriceReturnFetcher = Callable[[str, date, date], Optional[float]]


class PortfolioBacktester:
    """Runs a simple signal-to-return portfolio simulation from snapshot rows."""

    def __init__(
        self,
        store: KnowledgeStore,
        config: PortfolioBacktestConfig,
        *,
        price_fetcher: Optional[PriceReturnFetcher] = None,
    ) -> None:
        self._store = store
        self._config = config
        self._price_fetcher = price_fetcher or self._default_price_return

    @staticmethod
    def _default_price_return(ticker: str, start: date, end: date) -> Optional[float]:
        if end <= start:
            return None
        try:
            import yfinance as yf  # type: ignore[import-untyped]

            data = yf.download(
                ticker,
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                auto_adjust=True,
                progress=False,
            )
            if data is None or data.empty:
                return None
            close = data["Close"].dropna()
            if close.empty:
                return None
            first = float(close.iloc[0])
            last = float(close.iloc[-1])
            if first <= 0:
                return None
            return (last / first) - 1.0
        except Exception:
            return None

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return math.sqrt(max(0.0, var))

    @staticmethod
    def _max_drawdown(equity: list[float]) -> float:
        if not equity:
            return 0.0
        peak = equity[0]
        mdd = 0.0
        for value in equity:
            peak = max(peak, value)
            if peak <= 0:
                continue
            dd = (peak - value) / peak
            mdd = max(mdd, dd)
        return mdd

    def _zero_result(self, *, n_signals: int, note: str) -> BacktestResult:
        return BacktestResult(
            cagr=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            alpha_vs_benchmark=0.0,
            beta_vs_benchmark=0.0,
            information_ratio=0.0,
            monthly_returns=[],
            equity_curve=[],
            benchmark_equity_curve=[],
            position_log=[],
            n_signals=n_signals,
            snapshot_coverage_pct=0.0,
            assets_excluded_missing_prices=0,
            missing_price_positions=0,
            evaluated_positions=0,
            notes=[note],
        )

    def _ticker_for_asset(self, asset_id: str) -> Optional[str]:
        entry = self._store.get_asset_registry_entry(asset_id)
        if entry is None or not entry.ticker:
            return None
        return entry.ticker

    def _exit_date(self, snapshot: BacktestSnapshot) -> date:
        if (
            self._config.strategy == PortfolioStrategy.HOLD_UNTIL_CATALYST
            and snapshot.catalyst_date
        ):
            return max(snapshot.signal_date + timedelta(days=1), snapshot.catalyst_date)
        if self._config.strategy == PortfolioStrategy.CATALYST_MOMENTUM and snapshot.catalyst_date:
            horizon = max(5, min(45, (snapshot.catalyst_date - snapshot.signal_date).days // 2))
            return snapshot.signal_date + timedelta(days=horizon)
        return snapshot.signal_date + timedelta(days=self._config.rebalance_freq_days)

    def run(self) -> BacktestResult:
        snapshots = self._store.get_backtest_snapshots(since=self._config.start_date)
        if self._config.end_date is not None:
            snapshots = [s for s in snapshots if s.signal_date <= self._config.end_date]

        if not snapshots:
            return self._zero_result(n_signals=0, note="n_signals=0")

        snapshots.sort(key=lambda s: (s.signal_date, -(s.composite_score or 0.0), s.asset_id))
        grouped: dict[date, list[BacktestSnapshot]] = defaultdict(list)
        for snap in snapshots:
            grouped[snap.signal_date].append(snap)

        period_dates = sorted(grouped.keys())
        position_log: list[dict[str, object]] = []
        portfolio_returns: list[float] = []
        benchmark_returns: list[float] = []
        realized_dates: list[date] = []
        missing_price_positions = 0
        attempted_positions = 0
        evaluated_positions = 0
        assets_excluded: set[str] = set()

        tx_cost = 2.0 * (self._config.transaction_cost_bps / 10_000.0)

        for signal_dt in period_dates:
            universe = sorted(
                grouped[signal_dt],
                key=lambda s: (-(s.composite_score or 0.0), s.rank_at_signal or 9_999, s.asset_id),
            )
            chosen = universe[: self._config.n_holdings]
            if not chosen:
                continue

            weights: list[float]
            if self._config.strategy == PortfolioStrategy.SCORE_WEIGHTED:
                raw = [max(0.0, float(s.composite_score or 0.0)) for s in chosen]
                denom = sum(raw)
                if denom <= 0:
                    weights = [1.0 / len(chosen)] * len(chosen)
                else:
                    weights = [v / denom for v in raw]
            else:
                weights = [1.0 / len(chosen)] * len(chosen)

            weighted_return = 0.0
            position_count = 0
            benchmark_end = signal_dt + timedelta(days=self._config.rebalance_freq_days)

            for snap, weight in zip(chosen, weights):
                attempted_positions += 1
                ticker = self._ticker_for_asset(snap.asset_id)
                if not ticker:
                    missing_price_positions += 1
                    assets_excluded.add(snap.asset_id)
                    continue
                end_dt = self._exit_date(snap)
                if self._config.end_date is not None:
                    end_dt = min(end_dt, self._config.end_date)
                if end_dt <= signal_dt:
                    missing_price_positions += 1
                    assets_excluded.add(snap.asset_id)
                    continue
                gross = self._price_fetcher(ticker, signal_dt, end_dt)
                if gross is None:
                    missing_price_positions += 1
                    assets_excluded.add(snap.asset_id)
                    continue
                net = gross - tx_cost
                weighted_return += weight * net
                position_count += 1
                evaluated_positions += 1
                benchmark_end = max(benchmark_end, end_dt)
                position_log.append(
                    {
                        "asset_id": snap.asset_id,
                        "ticker": ticker,
                        "signal_date": signal_dt.isoformat(),
                        "exit_date": end_dt.isoformat(),
                        "weight": round(weight, 6),
                        "gross_return": round(gross, 6),
                        "net_return": round(net, 6),
                        "rank_at_signal": snap.rank_at_signal,
                        "composite_score": snap.composite_score,
                        "catalyst_type": snap.catalyst_type,
                    }
                )

            if position_count == 0:
                continue

            portfolio_returns.append(weighted_return)
            realized_dates.append(signal_dt)
            bench = self._price_fetcher(self._config.benchmark_ticker, signal_dt, benchmark_end)
            benchmark_returns.append(bench if bench is not None else 0.0)

        if not portfolio_returns:
            return self._zero_result(
                n_signals=len(snapshots),
                note="n_signals>0 but no valid return windows",
            )

        periods_per_year = max(1.0, 365.0 / self._config.rebalance_freq_days)
        mean_r = sum(portfolio_returns) / len(portfolio_returns)
        std_r = self._std(portfolio_returns)
        downside = [r for r in portfolio_returns if r < 0.0]
        downside_std = self._std(downside) if downside else 0.0

        sharpe = (mean_r / std_r) * math.sqrt(periods_per_year) if std_r > 0 else 0.0
        sortino = (mean_r / downside_std) * math.sqrt(periods_per_year) if downside_std > 0 else 0.0

        start_dt = realized_dates[0]
        end_dt = self._config.end_date or realized_dates[-1]
        elapsed_years = max(1.0 / 365.0, (end_dt - start_dt).days / 365.0)

        equity = [self._config.initial_capital]
        for r in portfolio_returns:
            equity.append(equity[-1] * (1.0 + r))
        final_equity = equity[-1]
        cagr = (final_equity / self._config.initial_capital) ** (1.0 / elapsed_years) - 1.0

        bench_equity = [self._config.initial_capital]
        for r in benchmark_returns:
            bench_equity.append(bench_equity[-1] * (1.0 + r))

        beta = 0.0
        alpha = 0.0
        info_ratio = 0.0
        if len(portfolio_returns) >= 2 and len(portfolio_returns) == len(benchmark_returns):
            mean_b = sum(benchmark_returns) / len(benchmark_returns)
            var_b = sum((x - mean_b) ** 2 for x in benchmark_returns) / (len(benchmark_returns) - 1)
            cov = sum(
                (r - mean_r) * (b - mean_b) for r, b in zip(portfolio_returns, benchmark_returns)
            ) / (len(portfolio_returns) - 1)
            if var_b > 0:
                beta = cov / var_b
            alpha = mean_r - beta * mean_b
            active = [r - b for r, b in zip(portfolio_returns, benchmark_returns)]
            active_std = self._std(active)
            if active_std > 0:
                info_ratio = (sum(active) / len(active)) / active_std * math.sqrt(periods_per_year)

        monthly: dict[str, list[float]] = defaultdict(list)
        for signal_dt, ret in zip(realized_dates, portfolio_returns):
            month_key = signal_dt.strftime("%Y-%m")
            monthly[month_key].append(ret)
        monthly_returns = [
            {
                "month": month,
                "return": round(sum(vals), 6),
            }
            for month, vals in sorted(monthly.items())
        ]

        equity_curve = []
        benchmark_curve = []
        for idx, value in enumerate(equity):
            dt = start_dt if idx == 0 else realized_dates[idx - 1]
            equity_curve.append({"date": dt.isoformat(), "equity": round(value, 2)})
        for idx, value in enumerate(bench_equity):
            dt = start_dt if idx == 0 else realized_dates[idx - 1]
            benchmark_curve.append({"date": dt.isoformat(), "equity": round(value, 2)})

        coverage_pct = (
            (evaluated_positions / attempted_positions) * 100.0 if attempted_positions > 0 else 0.0
        )
        notes: list[str] = []
        if missing_price_positions > 0:
            notes.append(
                f"missing_price_data_positions={missing_price_positions}/{attempted_positions}"
            )

        return BacktestResult(
            cagr=round(cagr, 6),
            sharpe_ratio=round(sharpe, 6),
            sortino_ratio=round(sortino, 6),
            max_drawdown=round(self._max_drawdown(equity), 6),
            win_rate=round(sum(1 for r in portfolio_returns if r > 0) / len(portfolio_returns), 6),
            alpha_vs_benchmark=round(alpha * periods_per_year, 6),
            beta_vs_benchmark=round(beta, 6),
            information_ratio=round(info_ratio, 6),
            monthly_returns=monthly_returns,
            equity_curve=equity_curve,
            benchmark_equity_curve=benchmark_curve,
            position_log=position_log,
            n_signals=len(snapshots),
            snapshot_coverage_pct=round(coverage_pct, 2),
            assets_excluded_missing_prices=len(assets_excluded),
            missing_price_positions=missing_price_positions,
            evaluated_positions=evaluated_positions,
            notes=notes,
        )
