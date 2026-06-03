"""
Formal alpha validation for historical replay runs.

Builds a paired excess-return series versus XBI over each trade's exact
holding window, then applies several dependence-aware checks:

- naive t-test on paired excess returns
- overlap diagnostics with an effective-N adjustment
- asset-clustered standard errors
- moving-block bootstrap confidence interval

Usage
-----
    python -m bve.analysis.alpha_validation --run-id <run_id>
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Mapping, Optional

import numpy as np
from scipy import stats

from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore


OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "analysis"
DEFAULT_BENCHMARK_TICKER = "XBI"
DEFAULT_BOOTSTRAP_BLOCK_DAYS = 28
DEFAULT_BOOTSTRAP_ITERATIONS = 10_000
DEFAULT_BOOTSTRAP_SEED = 42

PriceSeriesFetcher = Callable[[str, date, date], Mapping[date, float]]


@dataclass(frozen=True)
class PairedExcessTrade:
    """One replay trade paired with a same-window benchmark return."""

    trade_id: str
    asset_id: str
    ticker: str
    entry_date: date
    exit_date: date
    trade_return: float
    xbi_return: float
    excess_return: float

    @property
    def holding_days(self) -> int:
        """Inclusive trade duration in calendar days."""
        return max(1, (self.exit_date - self.entry_date).days + 1)


@dataclass(frozen=True)
class ExcessReturnStats:
    """Summary statistics for the paired excess-return series."""

    n_trades: int = 0
    mean_excess_return: Optional[float] = None
    median_excess_return: Optional[float] = None
    std_excess_return: Optional[float] = None
    hit_rate: Optional[float] = None
    t_statistic: Optional[float] = None
    p_value: Optional[float] = None
    naive_ci_low: Optional[float] = None
    naive_ci_high: Optional[float] = None


@dataclass(frozen=True)
class OverlapDiagnostics:
    """Dependence diagnostics based on overlapping holding windows."""

    total_pairs: int = 0
    overlapping_pairs: int = 0
    mean_overlap_days: Optional[float] = None
    mean_pairwise_correlation: Optional[float] = None
    effective_n: Optional[float] = None
    t_statistic: Optional[float] = None
    p_value: Optional[float] = None


@dataclass(frozen=True)
class ClusterDiagnostics:
    """Asset-cluster diagnostics for repeated names."""

    n_assets: int = 0
    trades_per_asset: dict[str, int] = field(default_factory=dict)
    largest_cluster_asset: Optional[str] = None
    largest_cluster_size: int = 0
    clustered_se: Optional[float] = None
    t_statistic: Optional[float] = None
    p_value: Optional[float] = None


@dataclass(frozen=True)
class BootstrapDiagnostics:
    """Moving-block bootstrap interval for mean excess return."""

    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS
    block_size_days: int = DEFAULT_BOOTSTRAP_BLOCK_DAYS
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    p_value: Optional[float] = None


@dataclass(frozen=True)
class AlphaValidationReport:
    """Full alpha validation output for one replay run."""

    run_id: str
    start_date: date
    end_date: date
    benchmark_ticker: str
    hold_days: Optional[int] = None
    paired_trades: list[PairedExcessTrade] = field(default_factory=list)
    stats: ExcessReturnStats = field(default_factory=ExcessReturnStats)
    overlap: OverlapDiagnostics = field(default_factory=OverlapDiagnostics)
    clusters: ClusterDiagnostics = field(default_factory=ClusterDiagnostics)
    bootstrap: BootstrapDiagnostics = field(default_factory=BootstrapDiagnostics)
    alpha_survives_corrections: bool = False
    csv_path: Optional[Path] = None


def _download_yfinance_prices(ticker: str, start: date, end: date) -> Mapping[date, float]:
    """
    Download adjusted closes for *ticker* across the requested date span.

    A small lookback buffer is added so non-trading entry/exit dates can still
    resolve to the most recent prior close when necessary.
    """
    import yfinance as yf  # type: ignore[import-untyped]

    cache_dir = Path("/tmp") / "yfinance_tz_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        yf.set_tz_cache_location(str(cache_dir))
    except Exception:
        pass

    buffered_start = start - timedelta(days=7)
    buffered_end = end + timedelta(days=2)
    data = yf.download(
        ticker,
        start=buffered_start.isoformat(),
        end=buffered_end.isoformat(),
        auto_adjust=True,
        progress=False,
    )
    if data is None or data.empty:
        return {}

    close = data["Close"]
    if getattr(close, "ndim", 1) > 1:
        close = close.iloc[:, 0]
    close = close.dropna()
    return {
        idx.date(): float(value)
        for idx, value in close.items()
    }


def _parse_date(raw: object) -> date:
    """Parse an ISO date or datetime string into a date."""
    return date.fromisoformat(str(raw)[:10])


def _parse_float(raw: object) -> Optional[float]:
    """Parse an optional numeric field into float."""
    if raw is None:
        return None
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


def _lookup_close(
    prices: Mapping[date, float],
    price_date: date,
    *,
    lookback_days: int = 7,
) -> Optional[float]:
    """
    Resolve a close for *price_date*.

    Uses the exact date when present, otherwise falls back to the most recent
    prior close within ``lookback_days`` calendar days to handle market holidays.
    """
    exact = prices.get(price_date)
    if exact is not None:
        return exact

    for offset in range(1, lookback_days + 1):
        candidate = price_date - timedelta(days=offset)
        fallback = prices.get(candidate)
        if fallback is not None:
            return fallback
    return None


def _alpha_csv_output_path(output_dir: Path, run_id: str, hold_days: Optional[int]) -> Path:
    suffix = f"_hold{hold_days}d" if hold_days is not None else ""
    return output_dir / f"alpha_validation_{run_id}{suffix}.csv"


def _compute_t_statistic(
    mean_value: float,
    sample_std: Optional[float],
    n_obs: float,
    *,
    df: Optional[float] = None,
) -> tuple[Optional[float], Optional[float]]:
    """Return the two-sided t-statistic and p-value for a sample mean."""
    if n_obs <= 0 or sample_std is None:
        return None, None
    if sample_std == 0.0:
        if mean_value == 0.0:
            return 0.0, 1.0
        return math.copysign(math.inf, mean_value), 0.0

    std_err = sample_std / math.sqrt(n_obs)
    if std_err == 0.0:
        return None, None

    t_stat = mean_value / std_err
    df_value = df if df is not None else max(float(n_obs) - 1.0, 1.0)
    p_value = float(stats.t.sf(abs(t_stat), df=df_value) * 2.0)
    return float(t_stat), p_value


def _compute_naive_confidence_interval(
    mean_value: float,
    sample_std: Optional[float],
    n_obs: int,
    confidence: float = 0.95,
) -> tuple[Optional[float], Optional[float]]:
    """Return a t-based confidence interval around the sample mean."""
    if n_obs <= 0 or sample_std is None:
        return None, None
    if sample_std == 0.0:
        return mean_value, mean_value
    if n_obs == 1:
        return None, None

    alpha = 1.0 - confidence
    t_crit = float(stats.t.ppf(1.0 - alpha / 2.0, df=n_obs - 1))
    std_err = sample_std / math.sqrt(n_obs)
    margin = t_crit * std_err
    return mean_value - margin, mean_value + margin


def _compute_excess_return_stats(trades: list[PairedExcessTrade]) -> ExcessReturnStats:
    """Compute basic summary statistics for a paired excess-return series."""
    if not trades:
        return ExcessReturnStats()

    values = np.array([trade.excess_return for trade in trades], dtype=float)
    n_obs = int(values.size)
    mean_value = float(values.mean())
    median_value = float(np.median(values))
    std_value = float(values.std(ddof=1)) if n_obs > 1 else 0.0
    hit_rate = float(np.mean(values > 0.0))
    t_stat, p_value = _compute_t_statistic(mean_value, std_value, n_obs)
    ci_low, ci_high = _compute_naive_confidence_interval(mean_value, std_value, n_obs)
    return ExcessReturnStats(
        n_trades=n_obs,
        mean_excess_return=mean_value,
        median_excess_return=median_value,
        std_excess_return=std_value,
        hit_rate=hit_rate,
        t_statistic=t_stat,
        p_value=p_value,
        naive_ci_low=ci_low,
        naive_ci_high=ci_high,
    )


def _overlap_days(
    start_a: date,
    end_a: date,
    start_b: date,
    end_b: date,
) -> int:
    """Return inclusive overlap days between two date ranges."""
    overlap_start = max(start_a, start_b)
    overlap_end = min(end_a, end_b)
    if overlap_end < overlap_start:
        return 0
    return (overlap_end - overlap_start).days + 1


def _overlap_correlation_proxy(trade_a: PairedExcessTrade, trade_b: PairedExcessTrade) -> float:
    """
    Estimate pairwise dependence from overlapping holding windows.

    Only one realised return exists per trade, so direct return-to-return
    correlation is not estimable from a single pair. This proxy treats each
    trade as an equal-weight exposure vector across its holding days and uses
    cosine similarity of those vectors.
    """
    overlap = _overlap_days(
        trade_a.entry_date,
        trade_a.exit_date,
        trade_b.entry_date,
        trade_b.exit_date,
    )
    if overlap <= 0:
        return 0.0
    return overlap / math.sqrt(trade_a.holding_days * trade_b.holding_days)


def _compute_overlap_diagnostics(
    trades: list[PairedExcessTrade],
    stats_summary: ExcessReturnStats,
) -> OverlapDiagnostics:
    """Compute overlap diagnostics and an effective-N adjusted t-statistic."""
    n_obs = len(trades)
    total_pairs = n_obs * (n_obs - 1) // 2
    if n_obs <= 1 or total_pairs == 0:
        return OverlapDiagnostics(total_pairs=total_pairs)

    overlap_days_list: list[int] = []
    corr_proxy_list: list[float] = []
    for idx, trade_a in enumerate(trades):
        for trade_b in trades[idx + 1:]:
            overlap = _overlap_days(
                trade_a.entry_date,
                trade_a.exit_date,
                trade_b.entry_date,
                trade_b.exit_date,
            )
            if overlap <= 0:
                continue
            overlap_days_list.append(overlap)
            corr_proxy_list.append(_overlap_correlation_proxy(trade_a, trade_b))

    overlapping_pairs = len(overlap_days_list)
    if overlapping_pairs == 0:
        effective_n = float(n_obs)
        t_stat, p_value = _compute_t_statistic(
            stats_summary.mean_excess_return or 0.0,
            stats_summary.std_excess_return,
            effective_n,
        )
        return OverlapDiagnostics(
            total_pairs=total_pairs,
            overlapping_pairs=0,
            mean_overlap_days=0.0,
            mean_pairwise_correlation=0.0,
            effective_n=effective_n,
            t_statistic=t_stat,
            p_value=p_value,
        )

    mean_overlap_days = float(np.mean(overlap_days_list))
    mean_corr = float(np.mean(corr_proxy_list))
    effective_n = max(1.0, n_obs / (1.0 + mean_corr))
    t_stat, p_value = _compute_t_statistic(
        stats_summary.mean_excess_return or 0.0,
        stats_summary.std_excess_return,
        effective_n,
        df=max(effective_n - 1.0, 1.0),
    )
    return OverlapDiagnostics(
        total_pairs=total_pairs,
        overlapping_pairs=overlapping_pairs,
        mean_overlap_days=mean_overlap_days,
        mean_pairwise_correlation=mean_corr,
        effective_n=effective_n,
        t_statistic=t_stat,
        p_value=p_value,
    )


def _compute_cluster_diagnostics(trades: list[PairedExcessTrade]) -> ClusterDiagnostics:
    """Compute asset-clustered standard errors for the sample mean."""
    if not trades:
        return ClusterDiagnostics()

    counts = Counter(trade.asset_id for trade in trades)
    largest_cluster_asset = None
    largest_cluster_size = 0
    if counts:
        largest_cluster_asset, largest_cluster_size = counts.most_common(1)[0]

    n_assets = len(counts)
    if n_assets < 2:
        return ClusterDiagnostics(
            n_assets=n_assets,
            trades_per_asset=dict(sorted(counts.items())),
            largest_cluster_asset=largest_cluster_asset,
            largest_cluster_size=largest_cluster_size,
        )

    values = np.array([trade.excess_return for trade in trades], dtype=float)
    mean_value = float(values.mean())
    n_obs = float(values.size)
    cluster_sums_sq = 0.0
    for asset_id in counts:
        cluster_sum = sum(
            trade.excess_return - mean_value
            for trade in trades
            if trade.asset_id == asset_id
        )
        cluster_sums_sq += cluster_sum ** 2

    variance = (n_assets / (n_assets - 1.0)) * (cluster_sums_sq / (n_obs ** 2))
    clustered_se = math.sqrt(max(0.0, variance))
    if clustered_se == 0.0:
        if mean_value == 0.0:
            t_stat = 0.0
            p_value = 1.0
        else:
            t_stat = math.copysign(math.inf, mean_value)
            p_value = 0.0
    else:
        t_stat = mean_value / clustered_se
        p_value = float(stats.t.sf(abs(t_stat), df=n_assets - 1) * 2.0)

    return ClusterDiagnostics(
        n_assets=n_assets,
        trades_per_asset=dict(sorted(counts.items())),
        largest_cluster_asset=largest_cluster_asset,
        largest_cluster_size=largest_cluster_size,
        clustered_se=clustered_se,
        t_statistic=float(t_stat),
        p_value=p_value,
    )


def _build_bootstrap_blocks(
    trades: list[PairedExcessTrade],
    *,
    block_size_days: int,
) -> list[np.ndarray]:
    """Build moving blocks over time-ordered trade excess returns."""
    if not trades:
        return []

    ordered = sorted(trades, key=lambda trade: (trade.entry_date, trade.trade_id))
    blocks: list[np.ndarray] = []
    for idx, trade in enumerate(ordered):
        block_end = trade.entry_date + timedelta(days=block_size_days - 1)
        values: list[float] = []
        jdx = idx
        while jdx < len(ordered) and ordered[jdx].entry_date <= block_end:
            values.append(ordered[jdx].excess_return)
            jdx += 1
        if values:
            blocks.append(np.array(values, dtype=float))
    return blocks


def _compute_block_bootstrap(
    trades: list[PairedExcessTrade],
    *,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    block_size_days: int = DEFAULT_BOOTSTRAP_BLOCK_DAYS,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> BootstrapDiagnostics:
    """Compute a moving-block bootstrap interval for mean excess return."""
    if not trades:
        return BootstrapDiagnostics(
            iterations=iterations,
            block_size_days=block_size_days,
        )

    blocks = _build_bootstrap_blocks(trades, block_size_days=block_size_days)
    if not blocks:
        return BootstrapDiagnostics(
            iterations=iterations,
            block_size_days=block_size_days,
        )

    rng = np.random.default_rng(seed)
    n_obs = len(trades)
    means = np.empty(iterations, dtype=float)
    for idx in range(iterations):
        sample: list[float] = []
        while len(sample) < n_obs:
            block = blocks[int(rng.integers(0, len(blocks)))]
            sample.extend(float(v) for v in block)
        means[idx] = float(np.mean(sample[:n_obs]))

    ci_low, ci_high = np.percentile(means, [2.5, 97.5])
    lower_or_equal_zero = float(np.mean(means <= 0.0))
    bootstrap_p = min(1.0, 2.0 * lower_or_equal_zero)
    return BootstrapDiagnostics(
        iterations=iterations,
        block_size_days=block_size_days,
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        p_value=float(bootstrap_p),
    )


def _alpha_survives_corrections(report: AlphaValidationReport) -> bool:
    """Conservative final verdict for the corrected alpha checks."""
    mean_excess = report.stats.mean_excess_return
    if mean_excess is None or mean_excess <= 0.0:
        return False

    checks: list[bool] = []
    if report.overlap.p_value is not None and report.overlap.t_statistic is not None:
        checks.append(report.overlap.p_value < 0.05 and report.overlap.t_statistic > 0.0)
    if report.clusters.p_value is not None and report.clusters.t_statistic is not None:
        checks.append(report.clusters.p_value < 0.05 and report.clusters.t_statistic > 0.0)
    if report.bootstrap.ci_low is not None and report.bootstrap.p_value is not None:
        checks.append(report.bootstrap.ci_low > 0.0 and report.bootstrap.p_value < 0.05)
    return bool(checks) and all(checks)


def _format_pct(value: Optional[float], *, show_sign: bool = False) -> str:
    """Format a percentage-point value for the report."""
    if value is None:
        return "n/a"
    fmt = "{:+.2f}%" if show_sign else "{:.2f}%"
    return fmt.format(value)


def _format_p(value: Optional[float]) -> str:
    """Format a p-value with fixed precision."""
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _format_stat(value: Optional[float]) -> str:
    """Format a scalar test statistic."""
    if value is None:
        return "n/a"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.2f}"


def _format_n(value: Optional[float]) -> str:
    """Format an observation count or effective count."""
    if value is None:
        return "n/a"
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.1f}"


def render_alpha_validation_report(report: AlphaValidationReport) -> str:
    """Render a formatted alpha validation report."""
    sep = "=" * 60
    paired_title = "Paired Excess Returns (vs XBI same-window)"
    if report.hold_days is not None:
        paired_title = (
            f"Paired Excess Returns (vs XBI same-window, {report.hold_days}d hold)"
        )
    lines = [
        sep,
        "ALPHA VALIDATION REPORT",
        f"Run: {report.run_id}",
        f"Period: {report.start_date.isoformat()} -> {report.end_date.isoformat()}",
        sep,
        paired_title,
        f"  N trades:              {report.stats.n_trades}",
        f"  Mean excess return:    {_format_pct(report.stats.mean_excess_return, show_sign=True)}",
        f"  Median excess return:  {_format_pct(report.stats.median_excess_return, show_sign=True)}",
        (
            "  Excess hit rate:       "
            + ("n/a" if report.stats.hit_rate is None else f"{report.stats.hit_rate * 100.0:.1f}%")
        ),
        f"  Std dev:               {_format_pct(report.stats.std_excess_return)}",
        (
            "  t-statistic (naive):   "
            f"{_format_stat(report.stats.t_statistic)}  (p = {_format_p(report.stats.p_value)})"
        ),
        "",
        "Dependence Corrections",
        (
            "  Overlapping trade pairs: "
            f"{report.overlap.overlapping_pairs} / {report.overlap.total_pairs} total pairs"
        ),
        f"  Effective N (overlap):   {_format_n(report.overlap.effective_n)}",
        (
            "  t-statistic (overlap):   "
            f"{_format_stat(report.overlap.t_statistic)}  (p = {_format_p(report.overlap.p_value)})"
        ),
        "",
        f"  Asset clusters:          {report.clusters.n_assets} unique assets",
        (
            "  Largest cluster:         "
            f"{report.clusters.largest_cluster_size} trades "
            f"({report.clusters.largest_cluster_asset or 'n/a'})"
        ),
        (
            "  t-statistic (clustered): "
            f"{_format_stat(report.clusters.t_statistic)}  "
            f"(p = {_format_p(report.clusters.p_value)})"
        ),
        "",
        (
            "  Block bootstrap 95% CI:  "
            f"[{_format_pct(report.bootstrap.ci_low, show_sign=True)}, "
            f"{_format_pct(report.bootstrap.ci_high, show_sign=True)}]"
        ),
        f"  Bootstrap p-value:       {_format_p(report.bootstrap.p_value)}",
        "",
        "Conclusion",
        f"  Alpha survives corrections: {'YES' if report.alpha_survives_corrections else 'NO'}",
        sep,
    ]
    return "\n".join(lines)


class AlphaValidator:
    """Build a formal alpha validation report from replay decisions."""

    def __init__(
        self,
        *,
        replay_db_path: str = str(REPLAY_STORE_PATH),
        benchmark_ticker: str = DEFAULT_BENCHMARK_TICKER,
        price_fetcher: Optional[PriceSeriesFetcher] = None,
        output_dir: Path = OUTPUT_DIR,
        bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
        bootstrap_block_days: int = DEFAULT_BOOTSTRAP_BLOCK_DAYS,
        bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    ) -> None:
        self.replay_db_path = replay_db_path
        self.benchmark_ticker = benchmark_ticker
        self.price_fetcher = price_fetcher or _download_yfinance_prices
        self.output_dir = output_dir
        self.bootstrap_iterations = bootstrap_iterations
        self.bootstrap_block_days = bootstrap_block_days
        self.bootstrap_seed = bootstrap_seed

    def _load_store_price_series(
        self,
        store: ReplayStore,
        tickers: set[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, dict[date, float]]:
        if not tickers:
            return {}
        placeholders = ",".join("?" for _ in tickers)
        rows = store._conn.execute(
            "SELECT ticker, price_date, close_usd FROM historical_prices "
            f"WHERE ticker IN ({placeholders}) AND price_date >= ? AND price_date <= ?",
            (*sorted(tickers), (start_date - timedelta(days=5)).isoformat(), end_date.isoformat()),
        ).fetchall()
        prices_by_ticker: dict[str, dict[date, float]] = {ticker: {} for ticker in tickers}
        for row in rows:
            prices_by_ticker[str(row["ticker"])][_parse_date(row["price_date"])] = float(row["close_usd"])
        return prices_by_ticker

    def _hydrate_price_series(
        self,
        prices_by_ticker: dict[str, dict[date, float]],
        required_dates_by_ticker: dict[str, set[date]],
        *,
        start_date: date,
        end_date: date,
    ) -> dict[str, dict[date, float]]:
        for ticker, required_dates in required_dates_by_ticker.items():
            series = prices_by_ticker.setdefault(ticker, {})
            missing = [
                required_date
                for required_date in required_dates
                if _lookup_close(series, required_date, lookback_days=5) is None
            ]
            if not missing:
                continue
            fetched = dict(self.price_fetcher(ticker, start_date, end_date))
            if fetched:
                series.update(fetched)
        return prices_by_ticker

    def build_paired_excess_trades(
        self,
        run_id: str,
        *,
        hold_days: Optional[int] = None,
        today: Optional[date] = None,
    ) -> tuple[dict, list[PairedExcessTrade]]:
        """Build the same-window benchmark-paired trade series for *run_id*."""
        as_of_date = today or date.today()
        store = ReplayStore(self.replay_db_path)
        try:
            run = store.get_run(run_id)
            if run is None:
                raise ValueError(f"Replay run not found: {run_id}")

            decisions = store.get_run_decisions(run_id)
            closed = [
                decision for decision in decisions
                if int(decision.get("is_closed") or 0) == 1
                and decision.get("return_pct") is not None
                and decision.get("exit_date")
            ]
            if not closed:
                return run, []

            target_decisions: list[dict] = []
            required_dates_by_ticker: dict[str, set[date]] = {}
            required_dates_by_ticker[self.benchmark_ticker] = set()
            for decision in closed:
                entry_date = _parse_date(decision["decided_at"])
                exit_date = (
                    entry_date + timedelta(days=hold_days)
                    if hold_days is not None
                    else _parse_date(decision["exit_date"])
                )
                if hold_days is not None and exit_date > as_of_date:
                    continue
                target_decisions.append({
                    "raw": decision,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                })
                if hold_days is not None:
                    required_dates_by_ticker.setdefault(str(decision["ticker"]), set()).update({
                        entry_date,
                        exit_date,
                    })
                required_dates_by_ticker[self.benchmark_ticker].update({entry_date, exit_date})

            if not target_decisions:
                return run, []

            min_entry = min(item["entry_date"] for item in target_decisions)
            max_exit = max(item["exit_date"] for item in target_decisions)
            prices_by_ticker = self._load_store_price_series(
                store,
                set(required_dates_by_ticker),
                min_entry,
                max_exit,
            )
            prices_by_ticker = self._hydrate_price_series(
                prices_by_ticker,
                required_dates_by_ticker,
                start_date=min_entry,
                end_date=max_exit,
            )
        finally:
            store.close()

        benchmark_prices = prices_by_ticker.get(self.benchmark_ticker, {})
        paired: list[PairedExcessTrade] = []
        for item in target_decisions:
            decision = item["raw"]
            entry_date = item["entry_date"]
            exit_date = item["exit_date"]
            ticker = str(decision["ticker"])

            benchmark_entry = _lookup_close(benchmark_prices, entry_date, lookback_days=5)
            benchmark_exit = _lookup_close(benchmark_prices, exit_date, lookback_days=5)
            if benchmark_entry is None or benchmark_exit is None or benchmark_entry == 0.0:
                continue

            if hold_days is None:
                trade_return = float(decision["return_pct"])
            else:
                asset_prices = prices_by_ticker.get(ticker, {})
                entry_price = _parse_float(decision.get("entry_price"))
                if entry_price is None or entry_price == 0.0:
                    entry_price = _lookup_close(asset_prices, entry_date, lookback_days=5)
                exit_price = _lookup_close(asset_prices, exit_date, lookback_days=5)
                if entry_price is None or exit_price is None or entry_price == 0.0:
                    continue
                trade_return = round(((exit_price / entry_price) - 1.0) * 100.0, 6)

            benchmark_return = round(((benchmark_exit / benchmark_entry) - 1.0) * 100.0, 6)
            paired.append(PairedExcessTrade(
                trade_id=str(decision["decision_id"]),
                asset_id=str(decision["asset_id"]),
                ticker=ticker,
                entry_date=entry_date,
                exit_date=exit_date,
                trade_return=trade_return,
                xbi_return=benchmark_return,
                excess_return=round(trade_return - benchmark_return, 6),
            ))

        paired.sort(key=lambda trade: (trade.entry_date, trade.trade_id))
        return run, paired

    def export_csv(
        self,
        run_id: str,
        trades: list[PairedExcessTrade],
        *,
        hold_days: Optional[int] = None,
    ) -> Path:
        """Write the paired trade-level dataset to CSV."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = _alpha_csv_output_path(self.output_dir, run_id, hold_days)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "trade_id",
                    "asset_id",
                    "ticker",
                    "entry_date",
                    "exit_date",
                    "trade_return",
                    "xbi_return",
                    "excess_return",
                ],
            )
            writer.writeheader()
            for trade in trades:
                writer.writerow({
                    "trade_id": trade.trade_id,
                    "asset_id": trade.asset_id,
                    "ticker": trade.ticker,
                    "entry_date": trade.entry_date.isoformat(),
                    "exit_date": trade.exit_date.isoformat(),
                    "trade_return": f"{trade.trade_return:.6f}",
                    "xbi_return": f"{trade.xbi_return:.6f}",
                    "excess_return": f"{trade.excess_return:.6f}",
                })
        return path

    def validate(
        self,
        run_id: str,
        *,
        hold_days: Optional[int] = None,
        today: Optional[date] = None,
    ) -> AlphaValidationReport:
        """Generate a formal alpha validation report for *run_id*."""
        run, paired_trades = self.build_paired_excess_trades(
            run_id,
            hold_days=hold_days,
            today=today,
        )
        stats_summary = _compute_excess_return_stats(paired_trades)
        overlap = _compute_overlap_diagnostics(paired_trades, stats_summary)
        clusters = _compute_cluster_diagnostics(paired_trades)
        bootstrap = _compute_block_bootstrap(
            paired_trades,
            iterations=self.bootstrap_iterations,
            block_size_days=self.bootstrap_block_days,
            seed=self.bootstrap_seed,
        )
        csv_path = self.export_csv(run_id, paired_trades, hold_days=hold_days)
        report = AlphaValidationReport(
            run_id=run_id,
            start_date=_parse_date(run["start_date"]),
            end_date=_parse_date(run["end_date"]),
            benchmark_ticker=self.benchmark_ticker,
            hold_days=hold_days,
            paired_trades=paired_trades,
            stats=stats_summary,
            overlap=overlap,
            clusters=clusters,
            bootstrap=bootstrap,
            csv_path=csv_path,
        )
        return AlphaValidationReport(
            **{
                **report.__dict__,
                "alpha_survives_corrections": _alpha_survives_corrections(report),
            }
        )


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Validate replay alpha versus XBI")
    parser.add_argument("--run-id", required=True, help="Replay run ID")
    parser.add_argument(
        "--db",
        default=str(REPLAY_STORE_PATH),
        help="Replay SQLite store path",
    )
    parser.add_argument(
        "--benchmark",
        default=DEFAULT_BENCHMARK_TICKER,
        help="Benchmark ticker (default: XBI)",
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=DEFAULT_BOOTSTRAP_ITERATIONS,
        help="Block bootstrap iteration count",
    )
    parser.add_argument(
        "--hold-days",
        type=int,
        default=None,
        help="Override replay exits with a fixed hold period in calendar days",
    )
    return parser


def main() -> None:
    """CLI entrypoint for alpha validation."""
    args = _build_parser().parse_args()
    validator = AlphaValidator(
        replay_db_path=args.db,
        benchmark_ticker=args.benchmark,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    report = validator.validate(args.run_id, hold_days=args.hold_days)
    print(render_alpha_validation_report(report))


if __name__ == "__main__":
    main()
