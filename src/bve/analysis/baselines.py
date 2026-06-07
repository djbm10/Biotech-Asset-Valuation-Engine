"""Baseline strategies for backtest comparison.

Every model claim of positive alpha must be benchmarked against these dumb
strategies. If the model cannot beat baseline A (equal-weight all catalyst
names) or baseline E (XBI beta), it does not add information.

Baselines implemented
---------------------
A — equal_weight_catalyst  : Buy every name with a catalyst within 30 days
B — market_cap_filtered    : Buy liquid small/mid-cap catalyst names only
C — cash_runway            : Buy names with runway > 6Q; avoid < 2Q
D — phase_stage            : Prefer Phase 2 PoC / Phase 3 readouts; avoid pre-clinical
E — xbi_beta               : Buy XBI instead of single names
F — random_score           : Randomly select same N trades (1,000 bootstrap runs)
G — analyst_heuristic      : Phase 2/3 + runway > 4Q + catalyst within 90 days

Usage
-----
    from bve.analysis.baselines import BaselineRunner, BaselineConfig

    runner = BaselineRunner(config=BaselineConfig(top_n=5, n_random_trials=1000))
    results = runner.run_all(candidates)
    for name, result in results.items():
        print(f"{name}: mean={result.mean_return_pct:.2f}% sharpe={result.sharpe:.2f}")
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BaselineCandidate:
    """Input record for baseline scoring.  All fields optional except ticker."""
    ticker: str
    return_pct: Optional[float] = None     # realised return for the period
    market_cap_millions: Optional[float] = None
    cash_millions: Optional[float] = None
    quarterly_burn_millions: Optional[float] = None  # quarterly cash burn
    phase: Optional[str] = None            # "phase_1" | "phase_2" | "phase_3" | "approved" | "preclinical"
    catalyst_days_away: Optional[int] = None  # days until next catalyst (None = no catalyst)
    ranking_score: Optional[float] = None  # model score (0–1)
    opportunity_score: Optional[float] = None
    adv_millions: Optional[float] = None   # 20-day average dollar volume

    @property
    def cash_runway_quarters(self) -> Optional[float]:
        if self.cash_millions and self.quarterly_burn_millions and self.quarterly_burn_millions > 0:
            return self.cash_millions / self.quarterly_burn_millions
        return None

    @property
    def has_near_catalyst(self) -> bool:
        """True if catalyst within 30 days."""
        return self.catalyst_days_away is not None and self.catalyst_days_away <= 30

    @property
    def has_medium_catalyst(self) -> bool:
        """True if catalyst within 90 days."""
        return self.catalyst_days_away is not None and self.catalyst_days_away <= 90

    @property
    def is_liquid(self) -> bool:
        """True if ADV ≥ $1M or ADV unknown (assume liquid for small universe)."""
        if self.adv_millions is None:
            return True
        return self.adv_millions >= 1.0

    @property
    def is_small_mid_cap(self) -> bool:
        """True if market cap $50M–$15B."""
        if self.market_cap_millions is None:
            return True  # unknown → include
        return 50 <= self.market_cap_millions <= 15_000


@dataclass
class BaselineResult:
    """Performance metrics for one baseline strategy."""
    strategy_name: str
    n_selected: int
    mean_return_pct: Optional[float]
    median_return_pct: Optional[float]
    std_return_pct: Optional[float]
    sharpe: Optional[float]             # mean / std (annualised approx)
    max_drawdown_pct: Optional[float]
    hit_rate: Optional[float]           # fraction of trades > 0
    precision_at_10: Optional[float]    # top-10 hit rate (None if N<10)
    # For random baseline only
    random_trial_means: list[float] = field(default_factory=list)
    random_mean_of_means: Optional[float] = None
    random_p25: Optional[float] = None
    random_p75: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy_name,
            "n_selected": self.n_selected,
            "mean_return_pct": _round(self.mean_return_pct),
            "median_return_pct": _round(self.median_return_pct),
            "std_return_pct": _round(self.std_return_pct),
            "sharpe": _round(self.sharpe),
            "max_drawdown_pct": _round(self.max_drawdown_pct),
            "hit_rate": _round(self.hit_rate),
            "precision_at_10": _round(self.precision_at_10),
        }


@dataclass
class BaselineConfig:
    top_n: int = 5                       # how many names to "hold" per period
    n_random_trials: int = 1_000         # bootstrap samples for random baseline
    random_seed: int = 42
    min_runway_quarters_include: float = 4.0   # C: minimum runway to buy
    min_runway_quarters_exclude: float = 2.0   # C: avoid below this
    catalyst_near_days: int = 30         # A, G: "near" catalyst threshold
    catalyst_medium_days: int = 90       # G: "medium" catalyst threshold
    phase_priority: list[str] = field(default_factory=lambda: [
        "phase_3", "phase_2", "phase_1", "approved", "preclinical"
    ])
    min_market_cap_millions: float = 50.0   # B: lower filter
    max_market_cap_millions: float = 15_000.0  # B: upper filter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _round(v: Optional[float], decimals: int = 4) -> Optional[float]:
    if v is None:
        return None
    return round(v, decimals)


def _metrics(returns: list[float], strategy_name: str, precision_at_10: Optional[float] = None) -> BaselineResult:
    if not returns:
        return BaselineResult(
            strategy_name=strategy_name, n_selected=0,
            mean_return_pct=None, median_return_pct=None, std_return_pct=None,
            sharpe=None, max_drawdown_pct=None, hit_rate=None, precision_at_10=None,
        )
    mean = statistics.mean(returns)
    median = statistics.median(returns)
    std = statistics.stdev(returns) if len(returns) > 1 else 0.0
    sharpe = (mean / std) if std > 0 else None
    hit_rate = sum(1 for r in returns if r > 0) / len(returns)
    max_dd = _max_drawdown(returns)
    p10 = precision_at_10
    if p10 is None and len(returns) >= 10:
        top10 = sorted(returns, reverse=True)[:10]
        p10 = sum(1 for r in top10 if r > 0) / 10
    return BaselineResult(
        strategy_name=strategy_name,
        n_selected=len(returns),
        mean_return_pct=round(mean, 4),
        median_return_pct=round(median, 4),
        std_return_pct=round(std, 4),
        sharpe=round(sharpe, 4) if sharpe is not None else None,
        max_drawdown_pct=round(max_dd, 4),
        hit_rate=round(hit_rate, 4),
        precision_at_10=round(p10, 4) if p10 is not None else None,
    )


def _max_drawdown(returns: list[float]) -> float:
    if not returns:
        return 0.0
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for r in returns:
        cumulative += r
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
    return -max_dd  # negative convention


def _top_n_returns(candidates: list[BaselineCandidate], n: int) -> list[float]:
    """Extract returns from top-N candidates (those with non-None return_pct)."""
    with_returns = [c for c in candidates if c.return_pct is not None]
    return [c.return_pct for c in with_returns[:n]]


# ---------------------------------------------------------------------------
# Baseline runner
# ---------------------------------------------------------------------------

class BaselineRunner:
    """Run all 7 baseline strategies against a universe of candidates."""

    def __init__(self, config: Optional[BaselineConfig] = None) -> None:
        self.config = config or BaselineConfig()

    def run_all(
        self, candidates: list[BaselineCandidate]
    ) -> dict[str, BaselineResult]:
        """Run all baselines. Returns dict of strategy_name → BaselineResult."""
        return {
            "A_equal_weight_catalyst": self.baseline_a(candidates),
            "B_market_cap_filtered":   self.baseline_b(candidates),
            "C_cash_runway":           self.baseline_c(candidates),
            "D_phase_stage":           self.baseline_d(candidates),
            "E_xbi_beta":              self.baseline_e(candidates),
            "F_random_score":          self.baseline_f(candidates),
            "G_analyst_heuristic":     self.baseline_g(candidates),
        }

    def baseline_a(self, candidates: list[BaselineCandidate]) -> BaselineResult:
        """A — Equal-weight all names with a catalyst within 30 days."""
        selected = [c for c in candidates if c.has_near_catalyst and c.return_pct is not None]
        returns = [c.return_pct for c in selected]
        return _metrics(returns, "A_equal_weight_catalyst")

    def baseline_b(self, candidates: list[BaselineCandidate]) -> BaselineResult:
        """B — Market-cap filtered catalyst basket (liquid small/mid-cap, catalyst ≤30d)."""
        selected = [
            c for c in candidates
            if c.has_near_catalyst
            and c.is_liquid
            and c.is_small_mid_cap
            and c.return_pct is not None
        ]
        returns = [c.return_pct for c in selected]
        return _metrics(returns, "B_market_cap_filtered")

    def baseline_c(self, candidates: list[BaselineCandidate]) -> BaselineResult:
        """C — Cash runway: runway > min_runway_quarters; avoid < exclude threshold."""
        selected = []
        for c in candidates:
            if c.return_pct is None:
                continue
            runway = c.cash_runway_quarters
            if runway is None:
                selected.append(c)  # unknown runway → include (conservative)
            elif runway >= self.config.min_runway_quarters_include:
                selected.append(c)
            # below exclude threshold → skip
        returns = [c.return_pct for c in selected]
        return _metrics(returns, "C_cash_runway")

    def baseline_d(self, candidates: list[BaselineCandidate]) -> BaselineResult:
        """D — Phase/stage: prefer Phase 2 PoC and Phase 3; avoid pre-clinical."""
        priority = {p: i for i, p in enumerate(self.config.phase_priority)}
        with_returns = [c for c in candidates if c.return_pct is not None and c.phase != "preclinical"]
        sorted_cands = sorted(with_returns, key=lambda c: priority.get(c.phase or "", 99))
        selected = sorted_cands[:self.config.top_n]
        returns = [c.return_pct for c in selected]
        return _metrics(returns, "D_phase_stage")

    def baseline_e(self, candidates: list[BaselineCandidate]) -> BaselineResult:
        """E — XBI beta: hold XBI instead of single names.

        Requires candidates to have a ``_xbi_return_pct`` attribute or the
        candidates list to contain a special ticker='XBI' entry. Falls back
        to mean of all candidates if XBI not found.
        """
        xbi = next((c for c in candidates if c.ticker.upper() == "XBI"), None)
        if xbi is not None and xbi.return_pct is not None:
            returns = [xbi.return_pct]
        else:
            # Fallback: use mean of full universe as XBI proxy
            all_returns = [c.return_pct for c in candidates if c.return_pct is not None]
            if all_returns:
                returns = [statistics.mean(all_returns)]
            else:
                returns = []
        return _metrics(returns, "E_xbi_beta")

    def baseline_f(self, candidates: list[BaselineCandidate]) -> BaselineResult:
        """F — Randomized score: randomly select top_n trades 1,000 times."""
        rng = random.Random(self.config.random_seed)
        eligible = [c for c in candidates if c.return_pct is not None]
        n = min(self.config.top_n, len(eligible))
        if n == 0:
            return BaselineResult(
                strategy_name="F_random_score", n_selected=0,
                mean_return_pct=None, median_return_pct=None, std_return_pct=None,
                sharpe=None, max_drawdown_pct=None, hit_rate=None, precision_at_10=None,
            )
        trial_means: list[float] = []
        for _ in range(self.config.n_random_trials):
            sample = rng.sample(eligible, n)
            trial_means.append(statistics.mean(c.return_pct for c in sample))  # type: ignore[arg-type]
        overall_mean = statistics.mean(trial_means)
        p25 = sorted(trial_means)[int(0.25 * len(trial_means))]
        p75 = sorted(trial_means)[int(0.75 * len(trial_means))]
        result = _metrics(trial_means, "F_random_score")
        result = BaselineResult(
            **{k: getattr(result, k) for k in result.__dataclass_fields__
               if k not in ("random_trial_means", "random_mean_of_means", "random_p25", "random_p75")},
            random_trial_means=trial_means,
            random_mean_of_means=round(overall_mean, 4),
            random_p25=round(p25, 4),
            random_p75=round(p75, 4),
        )
        return result

    def baseline_g(self, candidates: list[BaselineCandidate]) -> BaselineResult:
        """G — Analyst heuristic: Phase 2/3 + runway > 4Q + catalyst ≤ 90 days."""
        selected = [
            c for c in candidates
            if c.return_pct is not None
            and c.phase in ("phase_2", "phase_3")
            and c.has_medium_catalyst
            and (
                c.cash_runway_quarters is None
                or c.cash_runway_quarters >= self.config.min_runway_quarters_include
            )
        ]
        returns = [c.return_pct for c in selected]
        return _metrics(returns, "G_analyst_heuristic")

    def compare_to_model(
        self,
        model_mean_return: float,
        model_n: int,
        baselines: dict[str, BaselineResult],
    ) -> dict[str, dict]:
        """Return a comparison dict: model mean vs each baseline."""
        comparisons = {}
        for name, result in baselines.items():
            if result.mean_return_pct is None:
                comparisons[name] = {
                    "baseline_mean": None,
                    "model_advantage_pp": None,
                    "model_wins": None,
                }
            else:
                adv = model_mean_return - result.mean_return_pct
                comparisons[name] = {
                    "baseline_mean": result.mean_return_pct,
                    "model_advantage_pp": round(adv, 4),
                    "model_wins": adv > 0,
                    "n_baseline": result.n_selected,
                    "n_model": model_n,
                }
        return comparisons

    def print_comparison(
        self,
        model_mean_return: float,
        model_n: int,
        baselines: dict[str, BaselineResult],
    ) -> str:
        """Print a formatted comparison table."""
        from bve.validation.model_grade import (
            BacktestValidationStatus, validation_disclaimer,
        )
        disc = validation_disclaimer(BacktestValidationStatus.DIRECTIONAL_ONLY)
        lines = [disc, "=" * 70, "  BASELINE COMPARISON", "=" * 70]
        lines.append(
            f"  {'Strategy':<30} {'Baseline':>10}  {'Model':>10}  {'Advantage':>10}  {'Win?':>5}"
        )
        lines.append("  " + "─" * 66)
        for name, result in baselines.items():
            b = result.mean_return_pct
            if b is None:
                lines.append(f"  {name:<30} {'n/a':>10}  {model_mean_return:>+10.2f}%  {'—':>10}  {'—':>5}")
            else:
                adv = model_mean_return - b
                win = "✓" if adv > 0 else "✗"
                lines.append(
                    f"  {name:<30} {b:>+10.2f}%  {model_mean_return:>+10.2f}%  "
                    f"{adv:>+10.2f}pp  {win:>5}"
                )
        lines.append(f"\n  Model N = {model_n}")
        return "\n".join(lines)
