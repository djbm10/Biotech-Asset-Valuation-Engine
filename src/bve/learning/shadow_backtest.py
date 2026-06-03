"""Shadow backtest runner — replays predictions against a held-out historical outcome set.

Provides new Step 12 API (BacktestEntry, BacktestSummary, run_shadow_backtest)
and legacy API (ShadowBacktestConfig, ShadowBacktestResult, ShadowBacktest class).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ===========================================================================
# New Step 12 API
# ===========================================================================


@dataclass(frozen=True)
class BacktestEntry:
    asset_id: str
    ticker: str
    predicted_pos: float
    predicted_return: float
    asymmetry_score: float
    thesis_strength: str
    action_taken: str
    domain_scores: dict[str, float]
    predicted_at: datetime
    realized_return: float          # known historical outcome
    realized_at: datetime


@dataclass(frozen=True)
class BacktestSummary:
    """New Step 12 shadow backtest result."""
    n_entries: int
    brier_score: float
    mean_predicted_return: float
    mean_realized_return: float
    return_correlation: float       # Pearson r between predicted and realized returns
    hit_rate: float                 # fraction where sign(predicted) == sign(realized)
    mean_abs_return_error: float    # mean(|predicted_return - realized_return|)
    entries_by_action: dict[str, int]   # action_taken -> count


def run_shadow_backtest(entries: list[BacktestEntry]) -> BacktestSummary:
    """
    Compute all metrics over the provided entries.
    Brier: treat predicted_pos as forecast, binary_outcome = 1.0 if realized_return > 0 else 0.0.
    Pearson r: manual computation (no scipy); if std of either series is 0, return 0.0.
    hit_rate: sign agreement (both positive, both negative; zeros count as positive).
    Returns result with n_entries, all metrics.
    """
    n = len(entries)

    if n == 0:
        return BacktestSummary(
            n_entries=0,
            brier_score=0.0,
            mean_predicted_return=0.0,
            mean_realized_return=0.0,
            return_correlation=0.0,
            hit_rate=0.0,
            mean_abs_return_error=0.0,
            entries_by_action={},
        )

    # Brier score: binary_outcome = 1.0 if realized_return > 0 else 0.0
    brier_pairs = [
        (e.predicted_pos, 1.0 if e.realized_return > 0 else 0.0)
        for e in entries
    ]
    brier_score = sum((p - y) ** 2 for p, y in brier_pairs) / n

    # Returns
    predicted_returns = [e.predicted_return for e in entries]
    realized_returns = [e.realized_return for e in entries]

    mean_predicted = sum(predicted_returns) / n
    mean_realized = sum(realized_returns) / n

    # Pearson correlation (manual)
    return_correlation = _pearson_r(predicted_returns, realized_returns)

    # Hit rate: sign agreement (zero counts as positive)
    def _sign(x: float) -> int:
        return 1 if x >= 0 else -1

    hits = sum(
        1 for e in entries
        if _sign(e.predicted_return) == _sign(e.realized_return)
    )
    hit_rate = hits / n

    # Mean absolute return error
    mean_abs_error = sum(
        abs(e.predicted_return - e.realized_return) for e in entries
    ) / n

    # Entries by action
    entries_by_action: dict[str, int] = {}
    for e in entries:
        entries_by_action[e.action_taken] = entries_by_action.get(e.action_taken, 0) + 1

    return BacktestSummary(
        n_entries=n,
        brier_score=brier_score,
        mean_predicted_return=mean_predicted,
        mean_realized_return=mean_realized,
        return_correlation=return_correlation,
        hit_rate=hit_rate,
        mean_abs_return_error=mean_abs_error,
        entries_by_action=entries_by_action,
    )


def _pearson_r(xs: list[float], ys: list[float]) -> float:
    """Compute Pearson correlation coefficient manually (no scipy)."""
    n = len(xs)
    if n == 0:
        return 0.0

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / n
    std_x = (sum((x - mean_x) ** 2 for x in xs) / n) ** 0.5
    std_y = (sum((y - mean_y) ** 2 for y in ys) / n) ** 0.5

    if std_x == 0.0 or std_y == 0.0:
        return 0.0

    return cov / (std_x * std_y)


# ===========================================================================
# Legacy API (backward compatibility with test_learning_engine.py)
# ===========================================================================

_ERROR_ATTRIBUTIONS = {"thesis_error", "pos_error"}


class ShadowBacktestConfig(BaseModel):
    """Legacy shadow backtest configuration."""
    min_decisions_required: int = 10
    min_positive_return_rate: float = 0.50
    max_attribution_error_rate: float = 0.40


class ShadowBacktestResult(BaseModel):
    """Legacy shadow backtest result (Pydantic model, backward compat)."""
    passed: bool
    n_decisions: int
    positive_return_rate: float
    attribution_error_rate: float
    mean_return_pct: float
    recommendation: str
    notes: list[str]


class ShadowBacktest:
    """Legacy shadow backtest class."""

    def __init__(self, config: Optional[ShadowBacktestConfig] = None) -> None:
        self._config = config or ShadowBacktestConfig()

    def run(self, outcomes: list) -> ShadowBacktestResult:
        n = len(outcomes)

        if n == 0:
            return ShadowBacktestResult(
                passed=False,
                n_decisions=0,
                positive_return_rate=0.0,
                attribution_error_rate=0.0,
                mean_return_pct=0.0,
                recommendation="hold",
                notes=["No outcome records provided."],
            )

        if n < self._config.min_decisions_required:
            return ShadowBacktestResult(
                passed=False,
                n_decisions=n,
                positive_return_rate=_legacy_positive_rate(outcomes),
                attribution_error_rate=_legacy_error_rate(outcomes),
                mean_return_pct=_legacy_mean_return(outcomes),
                recommendation="hold",
                notes=[f"Insufficient data: {n} decisions < required {self._config.min_decisions_required}."],
            )

        positive_rate = _legacy_positive_rate(outcomes)
        error_rate = _legacy_error_rate(outcomes)
        mean_ret = _legacy_mean_return(outcomes)
        gate_failures: list[str] = []

        if positive_rate < self._config.min_positive_return_rate:
            gate_failures.append(
                f"Positive return rate {positive_rate:.2%} < required {self._config.min_positive_return_rate:.2%}."
            )

        if error_rate > self._config.max_attribution_error_rate:
            gate_failures.append(
                f"Attribution error rate {error_rate:.2%} > maximum {self._config.max_attribution_error_rate:.2%}."
            )

        if gate_failures:
            return ShadowBacktestResult(
                passed=False,
                n_decisions=n,
                positive_return_rate=positive_rate,
                attribution_error_rate=error_rate,
                mean_return_pct=mean_ret,
                recommendation="reject",
                notes=gate_failures,
            )

        return ShadowBacktestResult(
            passed=True,
            n_decisions=n,
            positive_return_rate=positive_rate,
            attribution_error_rate=error_rate,
            mean_return_pct=mean_ret,
            recommendation="promote",
            notes=["All gates passed."],
        )


def _legacy_positive_rate(outcomes: list) -> float:
    if not outcomes:
        return 0.0
    return sum(1 for o in outcomes if o.return_realized_pct > 0) / len(outcomes)


def _legacy_error_rate(outcomes: list) -> float:
    if not outcomes:
        return 0.0
    return sum(1 for o in outcomes if o.attribution in _ERROR_ATTRIBUTIONS) / len(outcomes)


def _legacy_mean_return(outcomes: list) -> float:
    if not outcomes:
        return 0.0
    return sum(o.return_realized_pct for o in outcomes) / len(outcomes)
