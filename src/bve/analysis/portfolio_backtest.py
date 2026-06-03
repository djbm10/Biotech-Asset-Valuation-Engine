"""Portfolio backtest over alert snapshots persisted by the intelligence pipeline."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from enum import Enum
from typing import Any, Callable, Optional

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
    max_weight_per_therapeutic_area: float | None = Field(default=None, gt=0.0, le=1.0)
    max_weight_per_modality: float | None = Field(default=None, gt=0.0, le=1.0)
    max_weight_per_catalyst_bucket: float | None = Field(default=None, gt=0.0, le=1.0)
    financing_risk_haircut_multiplier: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_scaled_sizing: bool = False
    min_calibrated_score: float = Field(default=0.0, ge=0.0, le=1.0)
    # Per-position hard cap — prevents any single name exceeding this weight regardless of group caps.
    # Useful when the portfolio is small (N < 10) and equal-weight creates dangerous concentration.
    max_single_position_weight: float | None = Field(default=None, gt=0.0, le=1.0)
    overlay: Optional[RiskOverlayConfig] = None


class BacktestResult(BaseModel):
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    brier_score: float | None = None
    calibration_error: float | None = None
    max_drawdown: float
    win_rate: float
    avg_return_by_tier: dict[str, float] = Field(default_factory=dict)
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
    overlay_filtered_positions: int = 0
    notes: list[str] = Field(default_factory=list)
    disclaimer: str = SURVIVORSHIP_BIAS_WARNING


PriceReturnFetcher = Callable[[str, date, date], Optional[float]]
ProbabilityCalibrator = Callable[[float], float]
RiskMetadataFetcher = Callable[[BacktestSnapshot], dict[str, Any]]
# (asset_id, as_of_date, lookback_days) -> True if negative event present in window
NegativeEventChecker = Callable[[str, date, int], bool]


class RiskOverlayConfig(BaseModel):
    """Risk controls applied on top of the base portfolio construction.

    All four controls can be enabled independently.  Typical usage::

        overlay = RiskOverlayConfig()  # all defaults
        cfg = PortfolioBacktestConfig(overlay=overlay)
    """

    momentum_lookback_days: int = Field(default=90, ge=1)
    momentum_threshold: float = Field(
        default=-0.20,
        description="Exclude asset from period if trailing return < this value.",
    )
    event_suppression_days: int = Field(
        default=90,
        ge=1,
        description="Suppress asset for this many days after a negative clinical event.",
    )
    drawdown_no_add_threshold: float = Field(
        default=-0.25,
        le=0.0,
        description="Skip entire rebalance period when portfolio equity is this far below its running peak.",
    )
    weight_cap: float = Field(
        default=0.075,
        gt=0.0,
        le=1.0,
        description="Hard per-position weight cap (overrides PortfolioBacktestConfig.max_single_position_weight).",
    )


class PortfolioBacktester:
    """Runs a simple signal-to-return portfolio simulation from snapshot rows."""

    def __init__(
        self,
        store: KnowledgeStore,
        config: PortfolioBacktestConfig,
        *,
        price_fetcher: Optional[PriceReturnFetcher] = None,
        probability_calibrator: Optional[ProbabilityCalibrator] = None,
        risk_metadata_fetcher: Optional[RiskMetadataFetcher] = None,
        negative_event_checker: Optional[NegativeEventChecker] = None,
    ) -> None:
        self._store = store
        self._config = config
        self._price_fetcher = price_fetcher or self._default_price_return
        self._probability_calibrator = probability_calibrator or (lambda value: value)
        self._risk_metadata_fetcher = risk_metadata_fetcher or self._default_risk_metadata
        self._negative_event_checker = negative_event_checker

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

    def _zero_result(
        self,
        *,
        n_signals: int,
        note: str,
        overlay_filtered_positions: int = 0,
    ) -> BacktestResult:
        return BacktestResult(
            cagr=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            brier_score=None,
            calibration_error=None,
            max_drawdown=0.0,
            win_rate=0.0,
            avg_return_by_tier={},
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
            overlay_filtered_positions=overlay_filtered_positions,
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

    def _default_risk_metadata(self, snapshot: BacktestSnapshot) -> dict[str, Any]:
        entry = self._store.get_asset_registry_entry(snapshot.asset_id)
        return {
            "therapeutic_area": getattr(entry, "therapeutic_area", None),
            "modality": getattr(entry, "modality", None),
            "catalyst_bucket": snapshot.catalyst_type,
            "financing_risk_score": None,
            "confidence": snapshot.extraction_confidence,
        }

    @staticmethod
    def _tier_for_snapshot(snapshot: BacktestSnapshot) -> str:
        score = float(snapshot.composite_score or 0.0)
        if score >= 0.70:
            return "high"
        if score >= 0.50:
            return "medium"
        return "low"

    @staticmethod
    def _snapshot_available_on_or_before(snapshot: BacktestSnapshot, as_of: date) -> bool:
        if snapshot.signal_timestamp is not None and snapshot.signal_timestamp.date() > as_of:
            return False
        return snapshot.created_at.date() <= as_of

    @staticmethod
    def _apply_group_cap(
        weights: list[float],
        groups: list[str | None],
        cap: float | None,
    ) -> list[float]:
        if cap is None:
            return list(weights)
        adjusted = list(weights)
        used: dict[str, float] = defaultdict(float)
        ordered = sorted(range(len(adjusted)), key=lambda idx: adjusted[idx], reverse=True)
        for idx in ordered:
            group = groups[idx]
            if not group:
                continue
            remaining = cap - used[group]
            if remaining <= 0.0:
                adjusted[idx] = 0.0
                continue
            if adjusted[idx] > remaining:
                adjusted[idx] = remaining
            used[group] += adjusted[idx]
        return adjusted

    def run(self) -> BacktestResult:
        snapshots = self._store.get_backtest_snapshots(since=self._config.start_date)
        if self._config.end_date is not None:
            snapshots = [s for s in snapshots if s.signal_date <= self._config.end_date]
            snapshots = [
                s for s in snapshots if self._snapshot_available_on_or_before(s, self._config.end_date)
            ]

        if not snapshots:
            return self._zero_result(n_signals=0, note="n_signals=0", overlay_filtered_positions=0)

        snapshots.sort(key=lambda s: (s.signal_date, -(s.composite_score or 0.0), s.asset_id))
        grouped: dict[date, list[BacktestSnapshot]] = defaultdict(list)
        for snap in snapshots:
            grouped[snap.signal_date].append(snap)

        period_dates = sorted(grouped.keys())
        position_log: list[dict[str, object]] = []
        portfolio_returns: list[float] = []
        benchmark_returns: list[float] = []
        realized_dates: list[date] = []
        returns_by_tier: dict[str, list[float]] = defaultdict(list)
        brier_terms: list[float] = []
        calibration_pairs: list[tuple[float, float]] = []
        missing_price_positions = 0
        attempted_positions = 0
        evaluated_positions = 0
        assets_excluded: set[str] = set()

        tx_cost = 2.0 * (self._config.transaction_cost_bps / 10_000.0)
        overlay = self._config.overlay
        # Running equity for drawdown gate (only used when overlay is set)
        current_equity_value = self._config.initial_capital
        equity_value_peak = self._config.initial_capital
        overlay_filtered = 0

        for signal_dt in period_dates:
            # Drawdown gate: skip entire period when portfolio is too far below its peak
            if overlay is not None and overlay.drawdown_no_add_threshold < 0.0:
                if current_equity_value < equity_value_peak:
                    current_dd = (current_equity_value - equity_value_peak) / equity_value_peak
                    if current_dd < overlay.drawdown_no_add_threshold:
                        continue
            universe = sorted(
                grouped[signal_dt],
                key=lambda s: (-(s.composite_score or 0.0), s.rank_at_signal or 9_999, s.asset_id),
            )
            chosen = universe[: self._config.n_holdings]
            if not chosen:
                continue

            weights: list[float]
            if self._config.strategy == PortfolioStrategy.SCORE_WEIGHTED:
                raw = [
                    max(0.0, float(self._probability_calibrator(float(s.composite_score or 0.0))))
                    for s in chosen
                ]
                denom = sum(raw)
                if denom <= 0:
                    weights = [1.0 / len(chosen)] * len(chosen)
                else:
                    weights = [v / denom for v in raw]
            else:
                weights = [1.0 / len(chosen)] * len(chosen)

            metadata_rows = [self._risk_metadata_fetcher(snapshot) for snapshot in chosen]
            adjusted_weights: list[float] = []
            filtered_chosen: list[BacktestSnapshot] = []
            filtered_meta: list[dict[str, Any]] = []
            for snapshot, base_weight, metadata in zip(chosen, weights, metadata_rows):
                calibrated_score = max(
                    0.0,
                    min(1.0, float(self._probability_calibrator(float(snapshot.composite_score or 0.0)))),
                )
                if calibrated_score < self._config.min_calibrated_score:
                    continue
                multiplier = 1.0
                if self._config.confidence_scaled_sizing:
                    confidence = metadata.get("confidence")
                    if confidence is None:
                        confidence = calibrated_score
                    multiplier *= max(0.0, min(1.0, float(confidence)))
                financing_risk_score = metadata.get("financing_risk_score")
                if financing_risk_score is not None:
                    multiplier *= max(
                        0.0,
                        1.0 - (
                            min(1.0, max(0.0, float(financing_risk_score)))
                            * self._config.financing_risk_haircut_multiplier
                        ),
                    )
                adjusted_weights.append(base_weight * multiplier)
                filtered_chosen.append(snapshot)
                filtered_meta.append(metadata)
            chosen = filtered_chosen
            if not chosen:
                continue
            if sum(adjusted_weights) > 0.0:
                weights = adjusted_weights
            else:
                weights = [1.0 / len(chosen)] * len(chosen)
            weights = self._apply_group_cap(
                weights,
                [item.get("therapeutic_area") for item in filtered_meta],
                self._config.max_weight_per_therapeutic_area,
            )
            weights = self._apply_group_cap(
                weights,
                [item.get("modality") for item in filtered_meta],
                self._config.max_weight_per_modality,
            )
            weights = self._apply_group_cap(
                weights,
                [item.get("catalyst_bucket") for item in filtered_meta],
                self._config.max_weight_per_catalyst_bucket,
            )

            # Effective per-position weight cap: overlay takes precedence
            if overlay is not None:
                effective_cap: float | None = overlay.weight_cap
            else:
                effective_cap = self._config.max_single_position_weight
            if effective_cap is not None:
                weights = [min(w, effective_cap) if w > 0.0 else w for w in weights]

            weighted_return = 0.0
            position_count = 0
            benchmark_end = signal_dt + timedelta(days=self._config.rebalance_freq_days)

            for snap, weight, metadata in zip(chosen, weights, filtered_meta):
                if weight <= 0.0:
                    continue
                attempted_positions += 1
                ticker = self._ticker_for_asset(snap.asset_id)
                if not ticker:
                    missing_price_positions += 1
                    assets_excluded.add(snap.asset_id)
                    continue
                # Overlay: momentum filter
                if overlay is not None:
                    momentum_start = signal_dt - timedelta(days=overlay.momentum_lookback_days)
                    trailing = self._price_fetcher(ticker, momentum_start, signal_dt)
                    if trailing is not None and trailing < overlay.momentum_threshold:
                        overlay_filtered += 1
                        assets_excluded.add(snap.asset_id)
                        continue
                # Overlay: event suppression
                if overlay is not None and self._negative_event_checker is not None:
                    had_neg = self._negative_event_checker(
                        snap.asset_id, signal_dt, overlay.event_suppression_days
                    )
                    if had_neg:
                        overlay_filtered += 1
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
                returns_by_tier[self._tier_for_snapshot(snap)].append(net)
                predicted = max(
                    0.0,
                    min(1.0, float(self._probability_calibrator(float(snap.composite_score or 0.0)))),
                )
                actual = 1.0 if net > 0 else 0.0
                brier_terms.append((predicted - actual) ** 2)
                calibration_pairs.append((predicted, actual))
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
                        "calibrated_score": round(predicted, 6),
                        "catalyst_type": snap.catalyst_type,
                        "therapeutic_area": metadata.get("therapeutic_area"),
                        "modality": metadata.get("modality"),
                        "financing_risk_score": metadata.get("financing_risk_score"),
                    }
                )

            if position_count == 0:
                continue

            portfolio_returns.append(weighted_return)
            realized_dates.append(signal_dt)
            bench = self._price_fetcher(self._config.benchmark_ticker, signal_dt, benchmark_end)
            benchmark_returns.append(bench if bench is not None else 0.0)
            # Update running equity for drawdown gate
            current_equity_value *= (1.0 + weighted_return)
            equity_value_peak = max(equity_value_peak, current_equity_value)

        if not portfolio_returns:
            return self._zero_result(
                n_signals=len(snapshots),
                note="n_signals>0 but no valid return windows",
                overlay_filtered_positions=overlay_filtered,
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
        if overlay_filtered > 0:
            notes.append(f"overlay_filtered_positions={overlay_filtered}")
        if self._config.end_date is not None:
            notes.append(f"no_lookahead_cutoff={self._config.end_date.isoformat()}")

        return BacktestResult(
            cagr=round(cagr, 6),
            sharpe_ratio=round(sharpe, 6),
            sortino_ratio=round(sortino, 6),
            brier_score=round(sum(brier_terms) / len(brier_terms), 6) if brier_terms else None,
            calibration_error=(
                round(self._expected_calibration_error(calibration_pairs), 6)
                if calibration_pairs
                else None
            ),
            max_drawdown=round(self._max_drawdown(equity), 6),
            win_rate=round(sum(1 for r in portfolio_returns if r > 0) / len(portfolio_returns), 6),
            avg_return_by_tier={
                tier: round(sum(values) / len(values), 6)
                for tier, values in sorted(returns_by_tier.items())
                if values
            },
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
            overlay_filtered_positions=overlay_filtered,
            notes=notes,
        )

    @staticmethod
    def _expected_calibration_error(
        calibration_pairs: list[tuple[float, float]],
        *,
        n_bins: int = 5,
    ) -> float:
        if not calibration_pairs:
            return 0.0
        bins: list[list[tuple[float, float]]] = [[] for _ in range(n_bins)]
        for predicted, actual in calibration_pairs:
            index = min(int(predicted * n_bins), n_bins - 1)
            bins[index].append((predicted, actual))
        total = len(calibration_pairs)
        ece = 0.0
        for bucket in bins:
            if not bucket:
                continue
            mean_pred = sum(item[0] for item in bucket) / len(bucket)
            mean_actual = sum(item[1] for item in bucket) / len(bucket)
            ece += (len(bucket) / total) * abs(mean_pred - mean_actual)
        return ece


# ---------------------------------------------------------------------------
# Train / validation overlay comparison
# ---------------------------------------------------------------------------


class OverlayComparisonResult(BaseModel):
    """Side-by-side Sharpe / drawdown / hit-rate report for baseline vs overlay."""

    overlay_config: dict[str, Any]
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    train_baseline: BacktestResult
    train_overlay: BacktestResult
    validation_baseline: BacktestResult
    validation_overlay: BacktestResult

    def summary_table(self) -> str:
        """Render a compact comparison table."""
        col_w = (20, 10, 8, 8, 9, 10, 12)
        header = (
            f"{'Split':<{col_w[0]}} {'Variant':<{col_w[1]}} "
            f"{'Sharpe':>{col_w[2]}} {'MaxDD':>{col_w[3]}} "
            f"{'HitRate':>{col_w[4]}} {'N_pos':>{col_w[5]}} "
            f"{'Filtered':>{col_w[6]}}"
        )
        sep = "-" * len(header)
        rows = [header, sep]
        splits = [
            ("Train", self.train_start, self.train_end, self.train_baseline, self.train_overlay),
            (
                "Validation",
                self.validation_start,
                self.validation_end,
                self.validation_baseline,
                self.validation_overlay,
            ),
        ]
        for split_label, start, end, baseline, overlay_result in splits:
            label = f"{split_label} ({start[:7]}–{end[:7]})"
            for variant, res in [("baseline", baseline), ("overlay", overlay_result)]:
                rows.append(
                    f"{label:<{col_w[0]}} {variant:<{col_w[1]}} "
                    f"{res.sharpe_ratio:>{col_w[2]}.3f} "
                    f"{res.max_drawdown:>{col_w[3]}.3f} "
                    f"{res.win_rate:>{col_w[4]}.3f} "
                    f"{res.evaluated_positions:>{col_w[5]}} "
                    f"{res.overlay_filtered_positions:>{col_w[6]}}"
                )
        return "\n".join(rows)


def compare_overlays(
    store: "KnowledgeStore",
    overlay_config: RiskOverlayConfig,
    *,
    train_start: date,
    train_end: date,
    validation_start: date,
    validation_end: date,
    base_config: Optional[PortfolioBacktestConfig] = None,
    price_fetcher: Optional[PriceReturnFetcher] = None,
    negative_event_checker: Optional[NegativeEventChecker] = None,
) -> OverlayComparisonResult:
    """Run baseline and overlay backtests on train and validation splits.

    The frozen holdout (2024-01+) must NOT be passed as validation_end.
    Typical usage::

        result = compare_overlays(
            store, RiskOverlayConfig(),
            train_start=date(2021, 2, 1), train_end=date(2023, 6, 30),
            validation_start=date(2023, 7, 1), validation_end=date(2023, 12, 31),
        )
        print(result.summary_table())
    """
    base = base_config or PortfolioBacktestConfig()

    def _run(overlay: Optional[RiskOverlayConfig], start: date, end: date) -> BacktestResult:
        cfg = base.model_copy(update={"start_date": start, "end_date": end, "overlay": overlay})
        return PortfolioBacktester(
            store,
            cfg,
            price_fetcher=price_fetcher,
            negative_event_checker=negative_event_checker,
        ).run()

    return OverlayComparisonResult(
        overlay_config=overlay_config.model_dump(),
        train_start=train_start.isoformat(),
        train_end=train_end.isoformat(),
        validation_start=validation_start.isoformat(),
        validation_end=validation_end.isoformat(),
        train_baseline=_run(None, train_start, train_end),
        train_overlay=_run(overlay_config, train_start, train_end),
        validation_baseline=_run(None, validation_start, validation_end),
        validation_overlay=_run(overlay_config, validation_start, validation_end),
    )
