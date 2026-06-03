"""
Rolling time-series backtest for M&A ranking model validation.

Approach
--------
For each as_of_date in a rolling sequence:
  1. Compute predicted score for every ticker using only evidence
     available strictly BEFORE as_of_date (no-lookahead via published_date).
  2. Define a ground-truth binary label: did this ticker experience a confirmed
     M&A event within the prediction horizon?
  3. Evaluate ranking quality across all windows.

Metrics
-------
  precision@K   : fraction of top-K predictions that are true positives
  AUC-ROC       : area under the ROC curve across all (score, label) pairs
  Brier score   : mean squared error of probability vs binary outcome
  calibration   : bucketed comparison of predicted vs observed hit rates

RollingBacktestConfig
---------------------
  as_of_dates           : list of ISO date strings (evaluation snapshots)
  prediction_horizon_months : months ahead to look for confirmed M&A events
  top_k                 : K for precision@K (default 10 and 25)
  min_score_threshold   : exclude very low confidence predictions from AUC
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class RollingBacktestConfig:
    """Configuration for a rolling backtest run."""
    as_of_dates: list[str]
    prediction_horizon_months: int = 12
    top_k_values: list[int] = field(default_factory=lambda: [10, 25])
    min_score_threshold: float = 0.0
    score_mode: str = "provisional"   # matches ScoreMode enum values


# ---------------------------------------------------------------------------
# BacktestRecord — one (as_of_date, ticker, score, label) triple
# ---------------------------------------------------------------------------


@dataclass
class BacktestRecord:
    """One evaluation row for the backtest."""
    as_of_date: str
    ticker: str
    predicted_score: float    # model score at as_of_date
    true_label: int           # 1 = M&A confirmed within horizon, 0 = not
    horizon_end_date: str     # as_of_date + horizon_months


# ---------------------------------------------------------------------------
# WindowResult — metrics for one as_of_date window
# ---------------------------------------------------------------------------


@dataclass
class WindowResult:
    """Metrics computed for one rolling window."""
    as_of_date: str
    n_tickers: int
    n_positive: int
    precision_at_k: dict[int, Optional[float]]  # k → precision value
    auc_roc: Optional[float]
    brier_score: float
    calibration_buckets: list[dict]  # [{bucket, predicted_mean, observed_rate, n}]


# ---------------------------------------------------------------------------
# RollingBacktestResult — aggregated across all windows
# ---------------------------------------------------------------------------


@dataclass
class RollingBacktestResult:
    """Aggregated results across all rolling windows."""
    config: RollingBacktestConfig
    window_results: list[WindowResult]
    mean_precision_at_k: dict[int, Optional[float]]
    mean_auc_roc: Optional[float]
    mean_brier_score: float
    total_records: int
    total_positives: int


# ---------------------------------------------------------------------------
# Metric computation helpers
# ---------------------------------------------------------------------------


def _precision_at_k(records: list[BacktestRecord], k: int) -> Optional[float]:
    """Precision@K: fraction of top-K by score that are true positives."""
    if not records or k <= 0:
        return None
    sorted_recs = sorted(records, key=lambda r: r.predicted_score, reverse=True)
    top_k = sorted_recs[:k]
    if not top_k:
        return None
    return sum(r.true_label for r in top_k) / len(top_k)


def _auc_roc(records: list[BacktestRecord]) -> Optional[float]:
    """
    AUC-ROC via the trapezoidal rule (Wilcoxon-Mann-Whitney estimator).

    Returns None if only one class is present (AUC undefined).
    """
    n_pos = sum(r.true_label for r in records)
    n_neg = len(records) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None

    sorted_recs = sorted(records, key=lambda r: r.predicted_score, reverse=True)
    # Count concordant pairs
    tp_count = 0.0
    running_pos = 0
    for rec in sorted_recs:
        if rec.true_label == 0:
            tp_count += running_pos
        else:
            running_pos += 1

    return tp_count / (n_pos * n_neg)


def _brier_score(records: list[BacktestRecord]) -> float:
    """Mean squared error of predicted_score vs true_label."""
    if not records:
        return 0.0
    return sum((r.predicted_score - r.true_label) ** 2 for r in records) / len(records)


def _calibration_buckets(
    records: list[BacktestRecord],
    n_buckets: int = 5,
) -> list[dict]:
    """
    Bucket records by predicted score and compare to observed positive rate.
    Returns list of {bucket_label, predicted_mean, observed_rate, n}.
    """
    if not records:
        return []
    width = 1.0 / n_buckets
    buckets: list[list[BacktestRecord]] = [[] for _ in range(n_buckets)]
    for rec in records:
        idx = min(int(rec.predicted_score / width), n_buckets - 1)
        buckets[idx].append(rec)

    result = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        low = i * width
        high = (i + 1) * width
        pred_mean = sum(r.predicted_score for r in bucket) / len(bucket)
        obs_rate = sum(r.true_label for r in bucket) / len(bucket)
        result.append({
            "bucket": f"{low:.1f}-{high:.1f}",
            "predicted_mean": round(pred_mean, 4),
            "observed_rate": round(obs_rate, 4),
            "n": len(bucket),
        })
    return result


# ---------------------------------------------------------------------------
# RollingBacktestEngine
# ---------------------------------------------------------------------------


class RollingBacktestEngine:
    """
    Evaluate ranking model quality using rolling time-series validation.

    Callers provide pre-computed BacktestRecord lists (one list per window).
    This engine computes metrics — it does not fetch data or compute scores itself.

    Usage::

        engine = RollingBacktestEngine()
        result = engine.evaluate(config, window_records)
        print(f"Mean AUC-ROC: {result.mean_auc_roc:.3f}")
    """

    def evaluate(
        self,
        config: RollingBacktestConfig,
        window_records: dict[str, list[BacktestRecord]],
    ) -> RollingBacktestResult:
        """
        Compute per-window and aggregate metrics.

        Parameters
        ----------
        config         : backtest configuration
        window_records : dict mapping as_of_date → list of BacktestRecord
        """
        window_results = []

        for as_of_date in config.as_of_dates:
            records = window_records.get(as_of_date, [])
            if config.min_score_threshold > 0:
                records = [
                    r for r in records
                    if r.predicted_score >= config.min_score_threshold
                ]
            wresult = self._evaluate_window(as_of_date, records, config.top_k_values)
            window_results.append(wresult)

        return self._aggregate(config, window_results)

    def _evaluate_window(
        self,
        as_of_date: str,
        records: list[BacktestRecord],
        top_k_values: list[int],
    ) -> WindowResult:
        n_pos = sum(r.true_label for r in records)

        prec_at_k = {k: _precision_at_k(records, k) for k in top_k_values}
        auc = _auc_roc(records)
        brier = _brier_score(records)
        cal = _calibration_buckets(records)

        return WindowResult(
            as_of_date=as_of_date,
            n_tickers=len(records),
            n_positive=n_pos,
            precision_at_k=prec_at_k,
            auc_roc=auc,
            brier_score=round(brier, 5),
            calibration_buckets=cal,
        )

    def _aggregate(
        self,
        config: RollingBacktestConfig,
        window_results: list[WindowResult],
    ) -> RollingBacktestResult:
        total_records = sum(w.n_tickers for w in window_results)
        total_positives = sum(w.n_positive for w in window_results)

        # Mean precision@K
        mean_prec: dict[int, Optional[float]] = {}
        for k in config.top_k_values:
            valid = [w.precision_at_k[k] for w in window_results if w.precision_at_k.get(k) is not None]
            mean_prec[k] = sum(valid) / len(valid) if valid else None

        # Mean AUC
        valid_aucs = [w.auc_roc for w in window_results if w.auc_roc is not None]
        mean_auc = sum(valid_aucs) / len(valid_aucs) if valid_aucs else None

        # Mean Brier
        brieres = [w.brier_score for w in window_results]
        mean_brier = sum(brieres) / len(brieres) if brieres else 0.0

        return RollingBacktestResult(
            config=config,
            window_results=window_results,
            mean_precision_at_k=mean_prec,
            mean_auc_roc=round(mean_auc, 5) if mean_auc is not None else None,
            mean_brier_score=round(mean_brier, 5),
            total_records=total_records,
            total_positives=total_positives,
        )
