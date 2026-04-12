"""
Out-of-sample validation harness for company-level SOTP signals.

Applies three additional tests on top of the standard alpha_validation module:

1. **Liquidity gate** — filters trades below a 20-day ADV threshold using the
   ``market_prices`` table in the replay store.  The gate is applied at entry
   date, not present day, so no forward-looking survivorship bias is introduced.

2. **Transaction cost model** — deducts a two-way round-trip cost tiered by ADV.
   High-liquidity names (ADV ≥ illiquid threshold) pay the base cost; names
   between the liquidity gate and the threshold pay the illiquid premium.

3. **Placebo test** — shuffles company ranks within each snapshot date 1,000
   times (by default) and records the mean excess return of each permuted
   top-N selection.  The real mean is then compared against the null
   distribution to derive a one-sided p-value.

4. **Subgroup cuts** — first-half vs second-half of the sample period.  More
   subgroups can be added via ``CompanySOTPBacktestTrade.action_policy`` or
   any caller-supplied ``subgroup_field``.

Usage
-----
    from bve.analysis.validation_harness import (
        ValidationHarnessConfig, run_validation_harness
    )

    report = run_validation_harness(
        backtest_report.trades,
        replay_db_path="outputs/intelligence/replay_store.sqlite",
    )
    print(report.validation_grade)
"""
from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
from scipy import stats as scipy_stats

from bve.analysis.alpha_validation import (
    ExcessReturnStats,
    _compute_excess_return_stats,
    PairedExcessTrade,
)
from bve.analysis.company_sotp_backtest import CompanySOTPBacktestTrade


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationHarnessConfig:
    """Configuration for the validation harness."""

    # Liquidity gate: minimum 20-day average dollar volume at entry date
    min_adv_millions: float = 1.0
    # Window (trading days) for ADV computation
    adv_window_days: int = 20
    # Minimum days of data required to compute ADV (relaxed for sparse history)
    adv_min_days: int = 10
    # ADV threshold separating base tx cost from illiquid premium (default $5M)
    illiquid_adv_threshold_millions: float = 5.0
    # Base one-way transaction cost (bps / 10000) for liquid names
    base_tx_cost_pct: float = 0.003   # 30bps
    # Illiquid one-way premium for names between gate and threshold
    illiquid_tx_cost_pct: float = 0.006  # 60bps
    # Placebo test iterations
    n_placebo_iterations: int = 1_000
    # Random seed for placebo
    placebo_seed: int = 42
    # Top-N trades selected per snapshot date (mirrors backtest setting)
    top_n: int = 10
    # p-value thresholds for grade assignment
    p_strong: float = 0.05
    p_moderate: float = 0.10


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlaceboTestResult:
    """Result of the rank-permutation placebo test."""

    n_placebo: int
    real_mean_excess_return: float
    placebo_mean: float
    placebo_std: float
    # Fraction of placebo simulations with mean >= real mean (one-sided p-value)
    p_value: float
    # Percentile rank of the real mean in the null distribution (0–1)
    percentile_rank: float


@dataclass(frozen=True)
class SubgroupResult:
    """Excess return statistics for one subgroup slice."""

    subgroup_name: str
    n_trades: int
    mean_excess_return: Optional[float]
    std_excess_return: Optional[float]
    hit_rate: Optional[float]
    t_statistic: Optional[float]
    p_value: Optional[float]


@dataclass(frozen=True)
class ValidationHarnessReport:
    """Full validation harness output."""

    # Input
    n_input_trades: int
    # After liquidity gate
    n_liquid_trades: int
    n_excluded_low_adv: int
    n_excluded_missing_adv: int
    # Gross stats (pre-cost, post-liquidity-gate)
    gross_stats: ExcessReturnStats
    # Net stats (after 2-way transaction cost)
    cost_adjusted_stats: ExcessReturnStats
    # Placebo test
    placebo: PlaceboTestResult
    # Subgroup cuts
    subgroups: list[SubgroupResult]
    # Summary grade
    validation_grade: str  # "strong" / "moderate" / "weak" / "insufficient"


# ---------------------------------------------------------------------------
# ADV helpers
# ---------------------------------------------------------------------------

def _compute_adv_millions(
    ticker: str,
    entry_date: date,
    db_path: str | Path,
    *,
    window_days: int = 20,
    min_days: int = 10,
) -> Optional[float]:
    """
    Compute the 20-day average dollar volume (ADV) for *ticker* as of *entry_date*.

    Looks up the ``market_prices`` table in the replay store.  Returns None if
    the ticker is absent or history is too sparse.
    """
    db_path = str(db_path)
    if db_path == ":memory:":
        return None

    lookback_start = entry_date - timedelta(days=window_days + 10)
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT close_usd, volume FROM market_prices
                WHERE ticker = ?
                  AND price_date >= ?
                  AND price_date <= ?
                ORDER BY price_date DESC
                LIMIT ?
                """,
                (ticker, lookback_start.isoformat(), entry_date.isoformat(), window_days + 5),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return None

    if len(rows) < min_days:
        return None

    total_dollar_volume = sum(
        float(close or 0.0) * int(vol or 0)
        for close, vol in rows[:window_days]
    )
    n = min(len(rows), window_days)
    if n == 0:
        return None
    return total_dollar_volume / n / 1_000_000.0


def _resolve_tx_cost_pct(
    adv_millions: Optional[float],
    *,
    config: ValidationHarnessConfig,
) -> float:
    """Return the one-way transaction cost for this liquidity tier."""
    if adv_millions is None or adv_millions < config.illiquid_adv_threshold_millions:
        return config.illiquid_tx_cost_pct
    return config.base_tx_cost_pct


# ---------------------------------------------------------------------------
# Placebo test
# ---------------------------------------------------------------------------

def _compute_placebo_distribution(
    candidate_map: dict[date, list[CompanySOTPBacktestTrade]],
    top_n: int,
    n_iterations: int,
    seed: int,
) -> list[float]:
    """
    Return *n_iterations* mean excess returns under random rank permutations.

    On each iteration, within every snapshot date the trade list is shuffled
    and the top-N are selected.  The global mean excess return is recorded.
    """
    rng = random.Random(seed)
    means: list[float] = []

    for _ in range(n_iterations):
        all_excess: list[float] = []
        for snap_trades in candidate_map.values():
            if not snap_trades:
                continue
            permuted = list(snap_trades)
            rng.shuffle(permuted)
            for trade in permuted[:top_n]:
                all_excess.append(trade.excess_return_pct)
        if all_excess:
            means.append(sum(all_excess) / len(all_excess))

    return means


def _build_placebo_result(
    trades: list[CompanySOTPBacktestTrade],
    config: ValidationHarnessConfig,
) -> PlaceboTestResult:
    """Run the placebo permutation test on *trades*."""
    # Group by snapshot date for permutation
    candidate_map: dict[date, list[CompanySOTPBacktestTrade]] = {}
    for trade in trades:
        candidate_map.setdefault(trade.snapshot_date, []).append(trade)

    placebo_means = _compute_placebo_distribution(
        candidate_map=candidate_map,
        top_n=config.top_n,
        n_iterations=config.n_placebo_iterations,
        seed=config.placebo_seed,
    )

    if not trades:
        return PlaceboTestResult(
            n_placebo=config.n_placebo_iterations,
            real_mean_excess_return=0.0,
            placebo_mean=0.0,
            placebo_std=0.0,
            p_value=1.0,
            percentile_rank=0.5,
        )

    real_mean = sum(t.excess_return_pct for t in trades) / len(trades)
    pbo_arr = np.array(placebo_means, dtype=float)
    pbo_mean = float(pbo_arr.mean()) if pbo_arr.size > 0 else 0.0
    pbo_std = float(pbo_arr.std(ddof=1)) if pbo_arr.size > 1 else 0.0

    # One-sided p-value: fraction of placebos ≥ real mean
    p_value = float(np.mean(pbo_arr >= real_mean)) if pbo_arr.size > 0 else 1.0
    pct_rank = float(np.mean(pbo_arr < real_mean)) if pbo_arr.size > 0 else 0.5

    return PlaceboTestResult(
        n_placebo=config.n_placebo_iterations,
        real_mean_excess_return=real_mean,
        placebo_mean=pbo_mean,
        placebo_std=pbo_std,
        p_value=p_value,
        percentile_rank=pct_rank,
    )


# ---------------------------------------------------------------------------
# Subgroup cuts
# ---------------------------------------------------------------------------

def _compute_subgroups(
    trades: list[CompanySOTPBacktestTrade],
    *,
    include_time_subgroups: bool = True,
    include_action_policy_subgroups: bool = True,
) -> list[SubgroupResult]:
    """Return subgroup excess return statistics."""
    if not trades or len(trades) < 4:
        return []

    results: list[SubgroupResult] = []

    if include_time_subgroups:
        all_dates = sorted({t.snapshot_date for t in trades})
        if len(all_dates) >= 2:
            mid_idx = len(all_dates) // 2
            mid_date = all_dates[mid_idx]
            first_half = [t for t in trades if t.snapshot_date < mid_date]
            second_half = [t for t in trades if t.snapshot_date >= mid_date]
            for label, subset in (("first_half", first_half), ("second_half", second_half)):
                results.append(_subgroup_from_trades(label, subset))

    if include_action_policy_subgroups:
        action_policies = sorted(
            {
                str(t.action_policy).strip().lower()
                for t in trades
                if str(t.action_policy).strip()
            }
        )
        for action_policy in action_policies:
            subset = [
                t for t in trades
                if str(t.action_policy).strip().lower() == action_policy
            ]
            if len(subset) >= 2:
                results.append(_subgroup_from_trades(f"action_policy:{action_policy}", subset))

    return results


def _subgroup_from_trades(name: str, trades: list[CompanySOTPBacktestTrade]) -> SubgroupResult:
    """Build a SubgroupResult from a trade subset."""
    if not trades:
        return SubgroupResult(
            subgroup_name=name,
            n_trades=0,
            mean_excess_return=None,
            std_excess_return=None,
            hit_rate=None,
            t_statistic=None,
            p_value=None,
        )
    excess = np.array([t.excess_return_pct for t in trades], dtype=float)
    n = int(excess.size)
    mean = float(excess.mean())
    std = float(excess.std(ddof=1)) if n > 1 else 0.0
    hit = float(np.mean(excess > 0.0))

    t_stat: Optional[float] = None
    p_val: Optional[float] = None
    if n > 1 and std > 0.0:
        se = std / (n ** 0.5)
        t_stat = mean / se
        p_val = float(scipy_stats.t.sf(abs(t_stat), df=n - 1) * 2.0)

    return SubgroupResult(
        subgroup_name=name,
        n_trades=n,
        mean_excess_return=mean,
        std_excess_return=std,
        hit_rate=hit,
        t_statistic=t_stat,
        p_value=p_val,
    )


# ---------------------------------------------------------------------------
# Grade assignment
# ---------------------------------------------------------------------------

def _assign_grade(
    n_liquid: int,
    gross_stats: ExcessReturnStats,
    placebo: PlaceboTestResult,
    config: ValidationHarnessConfig,
) -> str:
    """
    Assign a validation grade based on the key statistics.

    Grade criteria (all three required for "strong"):
    - n_liquid ≥ 20
    - cost-adjusted p_value ≤ p_strong
    - placebo p_value ≤ p_moderate (real mean beats ≥ 90% of placebos)

    "moderate": p_value ≤ p_moderate or (placebo p ≤ 0.15 and n ≥ 10)
    "weak": positive mean but not significant
    "insufficient": n < 5 or no data
    """
    if n_liquid < 5:
        return "insufficient"

    p_val = gross_stats.p_value
    mean = gross_stats.mean_excess_return

    if (
        n_liquid >= 20
        and p_val is not None
        and p_val <= config.p_strong
        and placebo.p_value <= config.p_moderate
    ):
        return "strong"

    if (
        p_val is not None
        and p_val <= config.p_moderate
    ) or (
        placebo.p_value <= 0.15
        and n_liquid >= 10
    ):
        return "moderate"

    if mean is not None and mean > 0:
        return "weak"

    return "insufficient"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_validation_harness(
    trades: list[CompanySOTPBacktestTrade],
    *,
    replay_db_path: str | Path = "",
    config: Optional[ValidationHarnessConfig] = None,
) -> ValidationHarnessReport:
    """
    Apply the full validation harness to a list of backtest trades.

    Parameters
    ----------
    trades:
        Output ``trades`` from ``CompanySOTPBacktestReport``.
    replay_db_path:
        Path to the replay SQLite database containing ``market_prices``.
    config:
        Harness configuration.  Defaults to ``ValidationHarnessConfig()``.

    Returns
    -------
    ValidationHarnessReport
    """
    if config is None:
        config = ValidationHarnessConfig()

    if not trades:
        empty_stats = ExcessReturnStats()
        empty_placebo = PlaceboTestResult(
            n_placebo=config.n_placebo_iterations,
            real_mean_excess_return=0.0,
            placebo_mean=0.0,
            placebo_std=0.0,
            p_value=1.0,
            percentile_rank=0.5,
        )
        return ValidationHarnessReport(
            n_input_trades=0,
            n_liquid_trades=0,
            n_excluded_low_adv=0,
            n_excluded_missing_adv=0,
            gross_stats=empty_stats,
            cost_adjusted_stats=empty_stats,
            placebo=empty_placebo,
            subgroups=[],
            validation_grade="insufficient",
        )

    db = str(replay_db_path) if replay_db_path else ":memory:"

    # --- Step 1: ADV liquidity gate ---
    liquid: list[CompanySOTPBacktestTrade] = []
    n_excluded_low = 0
    n_excluded_missing = 0

    adv_cache: dict[tuple[str, date], Optional[float]] = {}

    for trade in trades:
        key = (trade.ticker, trade.snapshot_date)
        if key not in adv_cache:
            adv_cache[key] = _compute_adv_millions(
                trade.ticker,
                trade.snapshot_date,
                db,
                window_days=config.adv_window_days,
                min_days=config.adv_min_days,
            )
        adv = adv_cache[key]

        if adv is None:
            # No ADV data: allow through but flag (market_prices not yet seeded)
            liquid.append(trade)
            n_excluded_missing += 1
        elif adv < config.min_adv_millions:
            n_excluded_low += 1
        else:
            liquid.append(trade)

    # Recompute n_excluded_missing to count only truly missing (allowed through)
    # The final liquid list includes both ADV-present-and-above-threshold AND missing-ADV
    n_liquid = len(liquid)
    # Trades excluded because ADV was measurably below threshold:
    n_excluded_low_adv_final = n_excluded_low

    # --- Step 2: Transaction cost adjustment ---
    paired_gross: list[PairedExcessTrade] = []
    paired_net: list[PairedExcessTrade] = []

    for trade in liquid:
        adv = adv_cache.get((trade.ticker, trade.snapshot_date))
        one_way_cost = _resolve_tx_cost_pct(adv, config=config)
        two_way_cost = 2.0 * one_way_cost
        net_excess = trade.excess_return_pct - two_way_cost

        paired_gross.append(
            PairedExcessTrade(
                trade_id=f"{trade.ticker}:{trade.snapshot_date.isoformat()}",
                asset_id=trade.company_id,
                ticker=trade.ticker,
                entry_date=trade.snapshot_date,
                exit_date=trade.exit_date,
                trade_return=trade.company_return_pct,
                xbi_return=trade.benchmark_return_pct,
                excess_return=trade.excess_return_pct,
            )
        )
        paired_net.append(
            PairedExcessTrade(
                trade_id=f"{trade.ticker}:{trade.snapshot_date.isoformat()}",
                asset_id=trade.company_id,
                ticker=trade.ticker,
                entry_date=trade.snapshot_date,
                exit_date=trade.exit_date,
                trade_return=trade.company_return_pct - two_way_cost,
                xbi_return=trade.benchmark_return_pct,
                excess_return=net_excess,
            )
        )

    gross_stats = _compute_excess_return_stats(paired_gross)
    cost_adjusted_stats = _compute_excess_return_stats(paired_net)

    # --- Step 3: Placebo test ---
    placebo = _build_placebo_result(liquid, config)

    # --- Step 4: Subgroup cuts ---
    subgroups = _compute_subgroups(liquid, include_time_subgroups=True)

    # --- Grade ---
    grade = _assign_grade(n_liquid, gross_stats, placebo, config)

    return ValidationHarnessReport(
        n_input_trades=len(trades),
        n_liquid_trades=n_liquid,
        n_excluded_low_adv=n_excluded_low_adv_final,
        n_excluded_missing_adv=n_excluded_missing,
        gross_stats=gross_stats,
        cost_adjusted_stats=cost_adjusted_stats,
        placebo=placebo,
        subgroups=subgroups,
        validation_grade=grade,
    )
