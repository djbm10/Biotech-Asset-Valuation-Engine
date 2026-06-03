"""
Statistical evaluation of POS model predictions against real outcome records.

Metrics
-------
Brier score : mean squared error of probability estimates.
    Lower is better. A uninformative model guessing 0.5 always scores 0.25.

AUC-ROC : area under the receiver operating characteristic curve.
    Computed via the trapezoidal rule on sorted predictions.
    0.5 = random; 1.0 = perfect discrimination. Requires at least one
    positive and one negative example.

ECE : expected calibration error (reliability diagram binned into deciles).
    Measures the average gap between predicted probability and observed frequency.
    Lower is better. Well-calibrated model should score < 0.05.

Time-split evaluation : train on records with outcome_date < cutoff_year,
    evaluate on records with outcome_date >= cutoff_year. Returns Brier
    scores for both folds to detect temporal drift.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from bve.empirical.pos_outcome import POSOutcomeRecord

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Aggregated evaluation metrics for a set of predictions."""
    n: int
    brier_score: float
    auc: Optional[float]      # None when only one class present
    ece: float
    # Per-bin calibration for reliability diagram
    calibration_bins: list[dict]

    def __str__(self) -> str:
        auc_str = f"{self.auc:.3f}" if self.auc is not None else "N/A"
        return (
            f"EvaluationResult(n={self.n}, "
            f"Brier={self.brier_score:.4f}, "
            f"AUC={auc_str}, "
            f"ECE={self.ece:.4f})"
        )


@dataclass
class TimeSplitResult:
    """Results from a temporal train/test split evaluation."""
    cutoff_year: int
    n_train: int
    n_test: int
    train_brier: float
    test_brier: float
    train_auc: Optional[float]
    test_auc: Optional[float]
    brier_drift: float          # test - train (positive = degraded on future data)

    def __str__(self) -> str:
        return (
            f"TimeSplitResult(cutoff={self.cutoff_year}, "
            f"train_n={self.n_train}/Brier={self.train_brier:.4f}, "
            f"test_n={self.n_test}/Brier={self.test_brier:.4f}, "
            f"drift={self.brier_drift:+.4f})"
        )


def _brier_score(predictions: list[float], outcomes: list[bool]) -> float:
    """Mean squared error between predicted probabilities and binary outcomes."""
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have the same length")
    if not predictions:
        return 0.0
    n = len(predictions)
    total = sum((p - float(y)) ** 2 for p, y in zip(predictions, outcomes))
    return total / n


def _auc_roc(predictions: list[float], outcomes: list[bool]) -> Optional[float]:
    """
    Compute AUC-ROC using the trapezoidal rule.

    Returns None when all outcomes are the same class (AUC undefined).
    """
    n_pos = sum(outcomes)
    n_neg = len(outcomes) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None

    # Sort by descending predicted probability
    paired = sorted(zip(predictions, outcomes), key=lambda x: -x[0])

    # Build ROC curve points
    tpr_points = [0.0]
    fpr_points = [0.0]
    tp = fp = 0
    for pred, actual in paired:
        if actual:
            tp += 1
        else:
            fp += 1
        tpr_points.append(tp / n_pos)
        fpr_points.append(fp / n_neg)

    # Trapezoidal AUC
    auc = 0.0
    for i in range(1, len(fpr_points)):
        dx = fpr_points[i] - fpr_points[i - 1]
        avg_y = (tpr_points[i] + tpr_points[i - 1]) / 2.0
        auc += dx * avg_y
    return round(auc, 4)


def _ece(
    predictions: list[float],
    outcomes: list[bool],
    n_bins: int = 10,
) -> tuple[float, list[dict]]:
    """
    Expected calibration error with equal-width bins.

    Returns (ece_value, calibration_bins) where each bin dict contains:
        lower, upper, n, mean_pred, observed_rate, gap
    """
    if not predictions:
        return 0.0, []

    bins: list[dict] = []
    bin_size = 1.0 / n_bins

    for b in range(n_bins):
        lo = b * bin_size
        hi = (b + 1) * bin_size
        in_bin = [
            (p, float(y))
            for p, y in zip(predictions, outcomes)
            if lo <= p < hi or (b == n_bins - 1 and p == 1.0)
        ]
        if not in_bin:
            bins.append({"lower": lo, "upper": hi, "n": 0,
                         "mean_pred": None, "observed_rate": None, "gap": 0.0})
            continue
        preds_b = [x[0] for x in in_bin]
        outcomes_b = [x[1] for x in in_bin]
        mean_pred = sum(preds_b) / len(preds_b)
        obs_rate = sum(outcomes_b) / len(outcomes_b)
        bins.append({
            "lower": round(lo, 2),
            "upper": round(hi, 2),
            "n": len(in_bin),
            "mean_pred": round(mean_pred, 4),
            "observed_rate": round(obs_rate, 4),
            "gap": round(abs(mean_pred - obs_rate), 4),
        })

    total_n = len(predictions)
    ece_val = sum(
        (b["n"] / total_n) * b["gap"]
        for b in bins
        if b["n"] > 0
    )
    return round(ece_val, 4), bins


def evaluate(
    predictions: list[float],
    records: list[POSOutcomeRecord],
    n_bins: int = 10,
) -> EvaluationResult:
    """
    Evaluate model predictions against outcome records.

    Parameters
    ----------
    predictions:
        Predicted POS for each record (must be in the same order as records).
    records:
        Outcome records (censored rows must be excluded before calling).
    n_bins:
        Number of bins for ECE calculation.

    Returns
    -------
    EvaluationResult with Brier, AUC, ECE, and calibration bins.
    """
    if len(predictions) != len(records):
        raise ValueError(
            f"predictions length ({len(predictions)}) != records length ({len(records)})"
        )
    if not records:
        raise ValueError("No records to evaluate")

    outcomes = [r.success for r in records]
    brier = _brier_score(predictions, outcomes)
    auc = _auc_roc(predictions, outcomes)
    ece_val, bins = _ece(predictions, outcomes, n_bins)

    return EvaluationResult(
        n=len(records),
        brier_score=round(brier, 4),
        auc=auc,
        ece=ece_val,
        calibration_bins=bins,
    )


def evaluate_time_split(
    engine,    # EmpiricalPOSEngine or any object with predict(phase, moa_precedent, biomarker_selected)
    records: list[POSOutcomeRecord],
    cutoff_year: int,
) -> TimeSplitResult:
    """
    Temporal train/test split evaluation.

    Records with outcome_date < cutoff_year form the "train" fold
    (conceptually — the engine was built from these). Records with
    outcome_date >= cutoff_year form the "test" fold.

    Parameters
    ----------
    engine:
        Any object with a predict(phase, moa_precedent, biomarker_selected) → float method.
        Typically EmpiricalPOSEngine.
    records:
        All outcome records (combined).
    cutoff_year:
        Year boundary for the split.

    Returns
    -------
    TimeSplitResult with train/test Brier and AUC.
    """
    train_records = []
    test_records = []
    for rec in records:
        try:
            year = int(rec.outcome_date) if rec.outcome_date else None
        except (ValueError, TypeError):
            year = None

        if year is None or year < cutoff_year:
            train_records.append(rec)
        else:
            test_records.append(rec)

    def _predict_batch(recs: list[POSOutcomeRecord]) -> list[float]:
        return [
            engine.predict(
                phase=r.phase_at_entry,
                moa_precedent=r.moa_precedent,
                # Pass True/None — not False — to avoid over-stratifying when
                # biomarker_selected is False (use broader phase/MoA cell instead).
                biomarker_selected=True if r.biomarker_selected else None,
            )
            for r in recs
        ]

    train_preds = _predict_batch(train_records) if train_records else []
    test_preds = _predict_batch(test_records) if test_records else []

    train_brier = _brier_score(train_preds, [r.success for r in train_records]) if train_records else 0.0
    test_brier = _brier_score(test_preds, [r.success for r in test_records]) if test_records else 0.0
    train_auc = _auc_roc(train_preds, [r.success for r in train_records]) if train_records else None
    test_auc = _auc_roc(test_preds, [r.success for r in test_records]) if test_records else None

    return TimeSplitResult(
        cutoff_year=cutoff_year,
        n_train=len(train_records),
        n_test=len(test_records),
        train_brier=round(train_brier, 4),
        test_brier=round(test_brier, 4),
        train_auc=train_auc,
        test_auc=test_auc,
        brier_drift=round(test_brier - train_brier, 4),
    )
