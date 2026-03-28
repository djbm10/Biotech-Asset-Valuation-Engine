"""
Calibration metrics for the PoS prediction database (Sprint 16).

Computes Brier score, AUC-ROC, and a reliability diagram from matched
prediction/outcome pairs stored in KnowledgeStore.

Key discipline: predictions are ONLY saved at the time they are made.
The calibration database is worthless if predictions are retroactively adjusted.

Usage
-----
    from bve.analysis.calibration_metrics import (
        compute_calibration,
        PredictionRecord,
        OutcomeRecord,
    )

    preds = [PredictionRecord(program_id="VKTX_VK2735", model_pos=0.42, ...)]
    outcomes = [OutcomeRecord(program_id="VKTX_VK2735", outcome_type="approval", ...)]
    report = compute_calibration(preds, outcomes)
    if report:
        print(f"Brier={report.brier_score:.3f}  AUC={report.auc_roc:.3f}")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class PredictionRecord:
    """One PoS prediction made at a specific point in time."""

    program_id: str
    ticker: str
    ta: str
    phase: str
    model_pos: float                       # 0-1: model's predicted success probability
    implied_pos: Optional[float] = None    # market-implied PoS at prediction time
    spread_pp: Optional[float] = None      # model_pos - implied_pos in pp
    peak_sales_millions: Optional[float] = None
    rnpv_millions: Optional[float] = None
    predicted_at: Optional[date] = None
    trial_end_expected: Optional[date] = None


@dataclass
class OutcomeRecord:
    """One resolved outcome for a program."""

    program_id: str
    outcome_date: Optional[date] = None
    outcome_type: Optional[str] = None     # approval | crl | failure_efficacy | failure_safety |
                                           # partial_approval | discontinued | ongoing
    trial_name: Optional[str] = None
    source: Optional[str] = None


# Outcome types that count as "success" (binary label = 1)
_SUCCESS_OUTCOMES = {"approval", "partial_approval"}

# Calibration bucket edges
_BUCKET_EDGES = [0.0, 0.20, 0.40, 0.60, 0.80, 1.0]


@dataclass
class CalibrationBucket:
    """Statistics for one predicted-probability bucket."""

    lo: float
    hi: float
    n: int
    mean_predicted: float
    actual_success_rate: float
    brier_contribution: float


@dataclass
class CalibrationReport:
    """Output of compute_calibration()."""

    n_pairs: int
    brier_score: float                          # lower is better; 0.0 = perfect, 0.25 = null
    brier_skill_score: float                    # vs. climatology (mean prediction as baseline)
    auc_roc: float                              # 0.5 = random, 1.0 = perfect
    ece: float                                  # expected calibration error (lower is better)
    buckets: list[CalibrationBucket] = field(default_factory=list)
    n_success: int = 0
    n_failure: int = 0
    base_rate: float = 0.0                      # actual success rate in matched set
    warnings: list[str] = field(default_factory=list)


def compute_calibration(
    predictions: list[PredictionRecord],
    outcomes: list[OutcomeRecord],
    min_n: int = 20,
) -> Optional[CalibrationReport]:
    """
    Compute Brier score, AUC-ROC, and reliability diagram.

    Matches predictions to outcomes on program_id. Only uses programs where
    outcome_type is not None and not "ongoing".

    Parameters
    ----------
    predictions : list of PredictionRecord
    outcomes    : list of OutcomeRecord
    min_n       : minimum matched pairs required (returns None if insufficient)

    Returns
    -------
    CalibrationReport or None if fewer than min_n matched pairs.
    """
    outcome_map = {o.program_id: o for o in outcomes}

    matched_pos: list[float] = []
    matched_labels: list[int] = []
    warnings: list[str] = []

    for pred in predictions:
        outcome = outcome_map.get(pred.program_id)
        if outcome is None:
            continue
        if outcome.outcome_type is None or outcome.outcome_type == "ongoing":
            continue
        label = 1 if outcome.outcome_type in _SUCCESS_OUTCOMES else 0
        matched_pos.append(pred.model_pos)
        matched_labels.append(label)

    n = len(matched_pos)
    if n < min_n:
        return None

    n_success = sum(matched_labels)
    n_failure = n - n_success
    base_rate = n_success / n

    brier = _brier_score(matched_pos, matched_labels)
    brier_ref = _brier_score([base_rate] * n, matched_labels)
    bss = 1.0 - brier / brier_ref if brier_ref > 0 else 0.0

    auc = _auc_roc(matched_pos, matched_labels)
    buckets = _reliability_buckets(matched_pos, matched_labels)
    ece = _expected_calibration_error(buckets)

    if n < 100:
        warnings.append(f"Only {n} matched pairs — metrics unreliable (target: 500+)")
    if base_rate > 0.75:
        warnings.append(
            f"Actual success rate {base_rate:.1%} may indicate survivor bias in dataset"
        )

    return CalibrationReport(
        n_pairs=n,
        brier_score=round(brier, 4),
        brier_skill_score=round(bss, 4),
        auc_roc=round(auc, 4),
        ece=round(ece, 4),
        buckets=buckets,
        n_success=n_success,
        n_failure=n_failure,
        base_rate=round(base_rate, 4),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _brier_score(probs: list[float], labels: list[int]) -> float:
    n = len(probs)
    if n == 0:
        return 0.0
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / n


def _auc_roc(probs: list[float], labels: list[int]) -> float:
    """Compute AUC-ROC via the trapezoidal rule (Mann-Whitney U statistic)."""
    paired = sorted(zip(probs, labels), key=lambda x: x[0], reverse=True)
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    tp = fp = 0
    prev_tp = prev_fp = 0
    prev_thr = None
    auc = 0.0
    for prob, label in paired:
        if prob != prev_thr and prev_thr is not None:
            # Trapezoidal area: (fp - prev_fp) × (tp + prev_tp) / 2 / (n_pos × n_neg)
            auc += (fp - prev_fp) * (tp + prev_tp) / 2
            prev_fp = fp
            prev_tp = tp
        if label == 1:
            tp += 1
        else:
            fp += 1
        prev_thr = prob
    # Final segment
    auc += (fp - prev_fp) * (tp + prev_tp) / 2
    return auc / (n_pos * n_neg)


def _reliability_buckets(
    probs: list[float],
    labels: list[int],
) -> list[CalibrationBucket]:
    buckets = []
    for lo, hi in zip(_BUCKET_EDGES[:-1], _BUCKET_EDGES[1:]):
        pts = [(p, y) for p, y in zip(probs, labels) if lo <= p < hi]
        if not pts:
            # Empty bucket: use midpoint as placeholder
            buckets.append(CalibrationBucket(
                lo=lo, hi=hi, n=0,
                mean_predicted=(lo + hi) / 2,
                actual_success_rate=0.0,
                brier_contribution=0.0,
            ))
            continue
        ps, ys = zip(*pts)
        mean_pred = sum(ps) / len(ps)
        actual = sum(ys) / len(ys)
        brier_c = sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)
        buckets.append(CalibrationBucket(
            lo=lo, hi=hi, n=len(pts),
            mean_predicted=round(mean_pred, 4),
            actual_success_rate=round(actual, 4),
            brier_contribution=round(brier_c, 4),
        ))
    return buckets


def _expected_calibration_error(buckets: list[CalibrationBucket]) -> float:
    """Weighted mean absolute error between mean_predicted and actual_success_rate."""
    total_n = sum(b.n for b in buckets)
    if total_n == 0:
        return 0.0
    return sum(
        b.n * abs(b.mean_predicted - b.actual_success_rate)
        for b in buckets
    ) / total_n
