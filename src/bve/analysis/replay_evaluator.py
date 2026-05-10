"""
ReplayEvaluator — three independent evaluation tracks for replay decisions.

Phase 3C objective
------------------
Evaluation is split into three independent tracks so that ranking quality,
calibration, and portfolio performance are NEVER conflated.

Track 1 — Ranking (RankingEvaluator)
    Measures whether high-ranked names had better outcomes than low-ranked names.
    Metrics: precision@k, hit_rate_by_decile.

Track 2 — Calibration (CalibrationEvaluator)
    Measures whether predicted probabilities match empirical hit rates.
    Metrics: Brier score, reliability_buckets (10 bins).

Track 3 — Action / Portfolio (PortfolioEvaluator)
    Measures whether "buy" decisions generated positive returns.
    Metrics: simple_returns, mean_return, hit_rate, max_drawdown, turnover.

Design
------
All evaluators are stateless — they take input lists and return result objects.
No database access, no side effects.  They work with any outcome data,
including synthetic data in tests.

Outcome conventions
-------------------
``outcome`` is always a float in [-1, 1] representing the subsequent price
return (e.g. +0.15 = +15%, -0.30 = -30%).

``binary_outcome`` is 1 (positive return) or 0 (negative return).  The
evaluators accept raw returns and convert internally.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Track 1 — Ranking
# ---------------------------------------------------------------------------

class RankingResult(BaseModel, frozen=True):
    """Output of RankingEvaluator."""
    k: int
    precision_at_k: float          # fraction of top-k with positive outcome
    n_evaluated: int               # total decisions with outcomes
    n_top_k: int                   # number of top-k decisions with outcomes
    hit_rate_overall: float        # fraction of all decisions with positive outcome
    decile_hit_rates: list[float]  # hit rate per decile (decile 1 = top-ranked)


class RankingEvaluator:
    """
    Measures whether the ranking order predicts outcomes.

    Parameters
    ----------
    decisions : list of (rank, outcome) where rank is 1-indexed, outcome is float.
    k         : top-k cutoff for precision@k.
    """

    @staticmethod
    def precision_at_k(
        ranked_outcomes: list[tuple[int, float]],
        k: int,
    ) -> float:
        """
        Fraction of top-k ranked decisions that had a positive outcome.

        Parameters
        ----------
        ranked_outcomes : list of (rank, outcome) tuples.
        k               : top-k cutoff.

        Returns 0.0 when no top-k decisions have outcomes.
        """
        top_k = [(r, o) for r, o in ranked_outcomes if r <= k]
        if not top_k:
            return 0.0
        return sum(1 for _, o in top_k if o > 0) / len(top_k)

    @staticmethod
    def hit_rate_by_decile(
        ranked_outcomes: list[tuple[int, float]],
        n_deciles: int = 10,
    ) -> list[float]:
        """
        Compute hit rate per decile of the rank distribution.

        Decile 1 = top-ranked (rank 1 to n/10), decile 10 = bottom-ranked.
        Returns a list of length ``n_deciles`` with NaN for empty deciles.
        """
        if not ranked_outcomes:
            return [float("nan")] * n_deciles

        sorted_outcomes = sorted(ranked_outcomes, key=lambda t: t[0])
        n = len(sorted_outcomes)
        decile_size = max(1, n // n_deciles)

        result: list[float] = []
        for d in range(n_deciles):
            start = d * decile_size
            end = start + decile_size if d < n_deciles - 1 else n
            bucket = sorted_outcomes[start:end]
            if not bucket:
                result.append(float("nan"))
            else:
                result.append(sum(1 for _, o in bucket if o > 0) / len(bucket))
        return result

    @staticmethod
    def evaluate(
        ranked_outcomes: list[tuple[int, float]],
        k: int = 5,
    ) -> RankingResult:
        """Run all ranking metrics and return a structured result."""
        top_k_with_outcomes = [(r, o) for r, o in ranked_outcomes if r <= k]
        p_at_k = RankingEvaluator.precision_at_k(ranked_outcomes, k)
        decile_rates = RankingEvaluator.hit_rate_by_decile(ranked_outcomes)
        overall_hit = (
            sum(1 for _, o in ranked_outcomes if o > 0) / len(ranked_outcomes)
            if ranked_outcomes else 0.0
        )
        return RankingResult(
            k=k,
            precision_at_k=p_at_k,
            n_evaluated=len(ranked_outcomes),
            n_top_k=len(top_k_with_outcomes),
            hit_rate_overall=overall_hit,
            decile_hit_rates=decile_rates,
        )


# ---------------------------------------------------------------------------
# Track 2 — Calibration
# ---------------------------------------------------------------------------

class CalibrationBucket(BaseModel, frozen=True):
    """One reliability-diagram bucket."""
    lower: float
    upper: float
    mean_predicted: float
    empirical_rate: float
    n: int


class CalibrationResult(BaseModel, frozen=True):
    """Output of CalibrationEvaluator."""
    brier_score: float                        # lower is better; 0 = perfect
    brier_skill_score: Optional[float]        # vs. climatology baseline; >0 = skill
    mean_calibration_error: float             # mean |empirical - predicted| across bins
    reliability_buckets: list[CalibrationBucket]
    n_pairs: int


class CalibrationEvaluator:
    """
    Measures whether predicted probabilities match empirical hit rates.

    Parameters
    ----------
    pairs : list of (predicted_probability, binary_outcome) tuples.
            predicted_probability ∈ [0, 1]; binary_outcome ∈ {0, 1}.
    """

    @staticmethod
    def brier_score(pairs: list[tuple[float, int]]) -> float:
        """
        Mean squared error between predicted probability and binary outcome.
        Brier = (1/N) × Σ(f_i − o_i)²
        """
        if not pairs:
            return float("nan")
        return sum((p - o) ** 2 for p, o in pairs) / len(pairs)

    @staticmethod
    def reliability_buckets(
        pairs: list[tuple[float, int]],
        n_bins: int = 10,
    ) -> list[CalibrationBucket]:
        """
        Build a reliability diagram with ``n_bins`` equal-width bins over [0, 1].

        Empty bins are included with empirical_rate=nan and n=0.
        """
        bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
        for pred, outcome in pairs:
            idx = min(int(pred * n_bins), n_bins - 1)
            bins[idx].append((pred, outcome))

        result: list[CalibrationBucket] = []
        for i, bucket in enumerate(bins):
            lower = i / n_bins
            upper = (i + 1) / n_bins
            if not bucket:
                result.append(CalibrationBucket(
                    lower=lower, upper=upper,
                    mean_predicted=float("nan"),
                    empirical_rate=float("nan"),
                    n=0,
                ))
            else:
                result.append(CalibrationBucket(
                    lower=lower, upper=upper,
                    mean_predicted=sum(p for p, _ in bucket) / len(bucket),
                    empirical_rate=sum(o for _, o in bucket) / len(bucket),
                    n=len(bucket),
                ))
        return result

    @staticmethod
    def evaluate(
        pairs: list[tuple[float, int]],
        n_bins: int = 10,
    ) -> CalibrationResult:
        """Run all calibration metrics and return a structured result."""
        bs = CalibrationEvaluator.brier_score(pairs)

        # Climatology baseline: always predict the mean outcome rate
        if pairs:
            mean_outcome = sum(o for _, o in pairs) / len(pairs)
            baseline_bs = sum((mean_outcome - o) ** 2 for _, o in pairs) / len(pairs)
            skill = 1 - bs / baseline_bs if baseline_bs > 0 else None
        else:
            skill = None

        buckets = CalibrationEvaluator.reliability_buckets(pairs, n_bins)
        filled = [b for b in buckets if b.n > 0]
        mce = (
            sum(abs(b.empirical_rate - b.mean_predicted) for b in filled) / len(filled)
            if filled else float("nan")
        )

        return CalibrationResult(
            brier_score=bs,
            brier_skill_score=skill,
            mean_calibration_error=mce,
            reliability_buckets=buckets,
            n_pairs=len(pairs),
        )


# ---------------------------------------------------------------------------
# Track 3 — Portfolio / Action
# ---------------------------------------------------------------------------

class PortfolioResult(BaseModel, frozen=True):
    """Output of PortfolioEvaluator."""
    n_decisions: int
    n_buy: int
    n_watch: int
    mean_return_buy: Optional[float]    # mean return for "buy" decisions
    mean_return_watch: Optional[float]  # mean return for "watch" decisions
    hit_rate_buy: Optional[float]       # fraction of buy decisions with positive return
    hit_rate_watch: Optional[float]
    max_drawdown: Optional[float]       # largest consecutive loss in the buy portfolio
    turnover: float                     # buy decisions / total decisions


class PortfolioEvaluator:
    """
    Measures portfolio-level outcomes for buy/watch decisions.

    Parameters
    ----------
    decisions : list of (action, outcome) tuples.
                action is "buy" | "watch" | "no_action"; outcome is float return.
    """

    @staticmethod
    def evaluate(
        decision_outcomes: list[tuple[str, float]],
    ) -> PortfolioResult:
        """
        Compute portfolio metrics from a list of (action, return) pairs.

        ``outcome`` is a raw price return, e.g. 0.15 = +15%.
        """
        buy_returns = [o for a, o in decision_outcomes if a == "buy"]
        watch_returns = [o for a, o in decision_outcomes if a == "watch"]

        def _mean(lst: list[float]) -> Optional[float]:
            return sum(lst) / len(lst) if lst else None

        def _hit_rate(lst: list[float]) -> Optional[float]:
            return sum(1 for r in lst if r > 0) / len(lst) if lst else None

        def _max_drawdown(returns: list[float]) -> Optional[float]:
            """Peak-to-trough drawdown of a cumulative return series."""
            if not returns:
                return None
            cum = [1.0]
            for r in returns:
                cum.append(cum[-1] * (1.0 + r))
            peak = cum[0]
            max_dd = 0.0
            for v in cum:
                if v > peak:
                    peak = v
                dd = (peak - v) / peak
                if dd > max_dd:
                    max_dd = dd
            return max_dd

        n_total = len(decision_outcomes)
        return PortfolioResult(
            n_decisions=n_total,
            n_buy=len(buy_returns),
            n_watch=len(watch_returns),
            mean_return_buy=_mean(buy_returns),
            mean_return_watch=_mean(watch_returns),
            hit_rate_buy=_hit_rate(buy_returns),
            hit_rate_watch=_hit_rate(watch_returns),
            max_drawdown=_max_drawdown(buy_returns),
            turnover=len(buy_returns) / n_total if n_total > 0 else 0.0,
        )

    @staticmethod
    def simple_returns(
        decisions: list[tuple[str, float]],
        action_filter: str = "buy",
    ) -> list[float]:
        """
        Return the list of returns for decisions matching ``action_filter``.

        Useful for feeding into statistical significance tests.
        """
        return [o for a, o in decisions if a == action_filter]
