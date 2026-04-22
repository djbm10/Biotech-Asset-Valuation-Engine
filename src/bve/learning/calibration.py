"""Module-level calibration metrics (Brier score, calibration error, bias tracking)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

from pydantic import BaseModel

from bve.learning.prediction_log import PredictionLog

# ---------------------------------------------------------------------------
# Backward compatibility — old CalibrationRecord / CalibrationSummary / CalibrationEngine
# ---------------------------------------------------------------------------


class CalibrationRecord(BaseModel):
    """A single prediction record, optionally resolved with a realized value."""

    record_id: str
    asset_id: str
    module: str  # "pos" | "peak_sales" | "timeline" | "financing" | "competition" | "access"
    prediction_date: date
    outcome_date: Optional[date] = None
    predicted_value: float
    realized_value: Optional[float] = None
    error: Optional[float] = None
    squared_error: Optional[float] = None
    is_resolved: bool = False


class CalibrationSummary(BaseModel):
    """Aggregated calibration statistics for a module."""

    module: str
    n_resolved: int
    mean_error: float
    rmse: float
    bias: float
    brier_score: Optional[float] = None
    calibration_slope: Optional[float] = None


class CalibrationEngine:
    """Stores calibration records and computes per-module summaries (legacy API)."""

    def __init__(self) -> None:
        self._records: list[CalibrationRecord] = []

    def add_record(self, record: CalibrationRecord) -> None:
        self._records.append(record)

    def resolve_record(self, record_id: str, realized_value: float) -> CalibrationRecord:
        for i, r in enumerate(self._records):
            if r.record_id == record_id:
                error = realized_value - r.predicted_value
                squared_error = error ** 2
                updated = r.model_copy(
                    update={
                        "realized_value": realized_value,
                        "error": error,
                        "squared_error": squared_error,
                        "is_resolved": True,
                    }
                )
                self._records[i] = updated
                return updated
        raise ValueError(f"No record found with record_id='{record_id}'")

    def summarize(self, module: str) -> CalibrationSummary:
        resolved = [r for r in self._records if r.module == module and r.is_resolved]
        n = len(resolved)
        if n == 0:
            return CalibrationSummary(module=module, n_resolved=0, mean_error=0.0, rmse=0.0, bias=0.0)
        errors = [r.error for r in resolved if r.error is not None]
        sq_errors = [r.squared_error for r in resolved if r.squared_error is not None]
        mean_error = sum(errors) / len(errors) if errors else 0.0
        rmse = math.sqrt(sum(sq_errors) / len(sq_errors)) if sq_errors else 0.0
        return CalibrationSummary(module=module, n_resolved=n, mean_error=mean_error, rmse=rmse, bias=mean_error)


@dataclass(frozen=True)
class CalibrationBucket:
    bin_lower: float          # e.g. 0.0
    bin_upper: float          # e.g. 0.1
    n_predictions: int
    mean_predicted: float
    mean_actual: float
    calibration_error: float  # abs(mean_predicted - mean_actual)


@dataclass(frozen=True)
class CalibrationReport:
    n_total: int
    n_resolved: int
    brier_score: float        # mean((predicted_pos - binary_outcome)^2); lower is better
    mean_calibration_error: float   # mean of per-bucket calibration_error
    max_calibration_error: float    # worst bucket
    overall_bias: float             # mean(predicted_pos - binary_outcome); + = overconfident
    buckets: list[CalibrationBucket]
    skill_score: float        # 1 - (brier_score / brier_score_no_skill); no-skill = mean(y)*(1-mean(y))


def compute_brier_score(pairs: list[tuple[float, float]]) -> float:
    """mean((p - y)^2) over all (predicted, actual) pairs. Returns 0.0 if empty."""
    if not pairs:
        return 0.0
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def compute_calibration_buckets(
    pairs: list[tuple[float, float]],
    n_bins: int = 10,
) -> list[CalibrationBucket]:
    """
    Bin predictions into n_bins equal-width buckets [0,0.1), [0.1,0.2), ..., [0.9,1.0].
    Skip empty buckets.
    """
    if not pairs:
        return []

    bin_width = 1.0 / n_bins
    # Initialize bins: list of (predicted_list, actual_list)
    bins: list[tuple[list[float], list[float]]] = [
        ([], []) for _ in range(n_bins)
    ]

    for predicted, actual in pairs:
        # Clamp to [0, 1]
        predicted = max(0.0, min(1.0, predicted))
        # Determine bin index
        bin_idx = int(predicted / bin_width)
        # Handle edge case: predicted == 1.0
        if bin_idx >= n_bins:
            bin_idx = n_bins - 1
        bins[bin_idx][0].append(predicted)
        bins[bin_idx][1].append(actual)

    buckets: list[CalibrationBucket] = []
    for i, (preds, actuals) in enumerate(bins):
        if not preds:
            continue
        bin_lower = i * bin_width
        bin_upper = (i + 1) * bin_width
        mean_pred = sum(preds) / len(preds)
        mean_act = sum(actuals) / len(actuals)
        cal_error = abs(mean_pred - mean_act)
        buckets.append(
            CalibrationBucket(
                bin_lower=bin_lower,
                bin_upper=bin_upper,
                n_predictions=len(preds),
                mean_predicted=mean_pred,
                mean_actual=mean_act,
                calibration_error=cal_error,
            )
        )

    return buckets


def build_calibration_report(log: PredictionLog) -> CalibrationReport:
    """
    Pull matched_pairs() from log, compute all metrics.
    skill_score: brier_no_skill = mean_actual × (1 - mean_actual); skill = 1 - brier/brier_no_skill.
    Returns report with n_total=log.count(), n_resolved=len(resolved pairs).
    """
    pairs = log.matched_pairs()
    n_total = log.count()
    n_resolved = len(pairs)

    if not pairs:
        return CalibrationReport(
            n_total=n_total,
            n_resolved=0,
            brier_score=0.0,
            mean_calibration_error=0.0,
            max_calibration_error=0.0,
            overall_bias=0.0,
            buckets=[],
            skill_score=0.0,
        )

    brier = compute_brier_score(pairs)
    buckets = compute_calibration_buckets(pairs)

    # Overall bias: mean(predicted - actual)
    overall_bias = sum(p - y for p, y in pairs) / len(pairs)

    # Calibration error stats from buckets
    if buckets:
        cal_errors = [b.calibration_error for b in buckets]
        mean_cal_error = sum(cal_errors) / len(cal_errors)
        max_cal_error = max(cal_errors)
    else:
        mean_cal_error = 0.0
        max_cal_error = 0.0

    # Skill score
    mean_actual = sum(y for _, y in pairs) / len(pairs)
    brier_no_skill = mean_actual * (1.0 - mean_actual)
    if brier_no_skill == 0.0:
        skill_score = 0.0
    else:
        skill_score = 1.0 - (brier / brier_no_skill)

    return CalibrationReport(
        n_total=n_total,
        n_resolved=n_resolved,
        brier_score=brier,
        mean_calibration_error=mean_cal_error,
        max_calibration_error=max_cal_error,
        overall_bias=overall_bias,
        buckets=buckets,
        skill_score=skill_score,
    )
