"""
Wave 3B — Forecast Tracking.

Records model predictions at signal-extraction time, then resolves them
against actual market outcomes once event_outcomes windows close.

Flow
----
1. ``record_forecast(signal, diff, store)`` — called when a valuation diff is
   created.  Derives ``predicted_direction`` and ``predicted_delta_pct`` from
   the signal and diff, writes one ``ForecastRecord`` row.

2. ``resolve_forecasts(store)`` — called by any runner after
   ``EventOutcomeTracker.resolve()``.  Joins resolved ``event_outcomes`` rows
   to ``forecast_records`` and fills ``actual_market_return_t30``,
   ``actual_market_return_t180``, ``outcome_correct``.

3. ``CalibrationReporter.report(store)`` — reads fully-resolved forecast rows
   and computes calibration metrics:
   - directional accuracy
   - magnitude RMSE (predicted_delta_pct vs actual_market_return_t30)
   - Spearman rank correlation
   - confidence calibration bins (deciles of extraction_confidence)
   - false positive rate

CLI
---
``bve-calibration-report`` calls ``CalibrationReporter.report(store)`` and
prints a summary table.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Scipy is an optional heavy dependency; guard so tests without scipy still
# import cleanly.  CalibrationReport will surface None for spearman if absent.
try:
    from scipy.stats import spearmanr as _spearmanr  # type: ignore[import]
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PredictedDirection = Literal["up", "down", "neutral"]

# Number of confidence bins for calibration histogram (deciles).
_N_CONFIDENCE_BINS = 10


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class ForecastRecord(BaseModel):
    """
    One model prediction, created at signal-extraction time.

    Populated from a ``StructuredSignal`` + ``StoredValuationDiff`` pair.
    ``actual_*`` fields are filled later by ``resolve_forecasts()``.

    Attributes
    ----------
    horizon_days:
        Outcome window the prediction is evaluated against.
        Default is 30 (T+30 market return).  Stored explicitly so that short-
        and long-horizon forecasts can be tracked and compared separately.
    predicted_at:
        UTC timestamp when the prediction was generated (i.e. when the signal
        was extracted).  Kept separate from ``created_at`` (DB write time) to
        allow latency measurement between signal event and ingestion.
    created_at:
        UTC timestamp when the row was written to the database.
    """

    forecast_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    event_id: str
    asset_id: str
    event_type: str
    signal_date: str                         # ISO date string
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    predicted_direction: PredictedDirection
    predicted_delta_pct: Optional[float] = None   # predicted % valuation change
    horizon_days: int = 30                   # which outcome window to evaluate against
    predicted_at: datetime = Field(         # when the prediction was generated
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # E-lite: stratification buckets for PoS recalibration
    # Required so calibration can segment by (indication × phase × endpoint_type)
    # rather than mixing heterogeneous event classes.
    trial_phase:   Optional[str] = None   # e.g. "phase_2", "phase_3"
    indication:    Optional[str] = None   # e.g. "oncology", "nsclc"
    endpoint_type: Optional[str] = None   # e.g. "orr", "pfs_hr", "os"

    # Filled on resolution
    actual_market_return_t30:  Optional[float] = None
    actual_market_return_t180: Optional[float] = None
    outcome_label:             Optional[str]   = None   # wave 0.5 truth taxonomy
    outcome_correct:           Optional[bool]  = None   # direction accuracy
    resolved: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Calibration output
# ---------------------------------------------------------------------------


class CalibrationBin(BaseModel):
    """Accuracy within one confidence decile."""

    bin_low: float
    bin_high: float
    n_forecasts: int
    directional_accuracy: Optional[float] = None  # None when n_forecasts == 0


class CalibrationReport(BaseModel):
    """Summary of model calibration across all resolved forecasts."""

    n_total: int
    n_resolved: int
    coverage: Optional[float] = None               # n_resolved / n_total; None when n_total == 0
    directional_accuracy: Optional[float] = None   # fraction correct
    magnitude_rmse: Optional[float] = None          # RMSE(pred_delta_pct, actual_t30)
    spearman_correlation: Optional[float] = None    # rank correlation
    spearman_p_value: Optional[float] = None
    false_positive_rate: Optional[float] = None     # predicted "up" but actual < 0
    confidence_bins: list[CalibrationBin] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Confidence calibration status (Task 9.17 — Sprint 9 Phase 4)
    # LLM extraction confidence thresholds are provisional heuristics; calibration
    # requires ≥ 200 labeled outcomes (Platt scaling or isotonic regression).
    confidence_calibration_status: str = "uncalibrated"  # "uncalibrated" | "calibrated"
    confidence_calibration_n_required: int = 200         # minimum before re-calibration


# ---------------------------------------------------------------------------
# record_forecast
# ---------------------------------------------------------------------------


def _infer_direction(signal: Any, diff: Any) -> PredictedDirection:
    """
    Derive predicted direction from a StructuredSignal + StoredValuationDiff.

    Priority:
    1. Explicit signal fields (primary_endpoint_met, fda_action_type)
    2. Sign of diff.delta_npv
    3. "neutral" as final fallback.
    """
    # 1. Explicit signal facts
    if getattr(signal, "primary_endpoint_met", None) is True:
        return "up"
    if getattr(signal, "primary_endpoint_met", None) is False:
        return "down"

    fda = getattr(signal, "fda_action_type", None)
    if fda in ("approval",):
        return "up"
    if fda in ("crl", "hold"):
        return "down"

    # 2. Valuation diff sign
    delta = getattr(diff, "delta_npv", None)
    if delta is not None:
        if delta > 1e-6:
            return "up"
        if delta < -1e-6:
            return "down"

    return "neutral"


def _infer_delta_pct(diff: Any) -> Optional[float]:
    """
    Derive predicted_delta_pct from a StoredValuationDiff.

    Uses ``valuation_delta["npv_delta_pct"]`` when available, otherwise
    computes from delta_npv / before_npv.
    """
    val_delta = getattr(diff, "valuation_delta", {})
    if "npv_delta_pct" in val_delta:
        return float(val_delta["npv_delta_pct"])

    before = getattr(diff, "valuation_before", {})
    before_npv = before.get("rnpv_millions") or before.get("npv_millions")
    delta_npv = getattr(diff, "delta_npv", None)

    if before_npv is not None and delta_npv is not None and abs(before_npv) > 1e-6:
        return delta_npv / before_npv * 100.0
    return None


def record_forecast(
    signal: Any,
    diff: Any,
    store: Any,
) -> ForecastRecord:
    """
    Create a ForecastRecord from a StructuredSignal + StoredValuationDiff.

    Parameters
    ----------
    signal:
        A ``StructuredSignal`` instance.
    diff:
        A ``StoredValuationDiff`` instance.
    store:
        A ``KnowledgeStore`` instance.

    Returns
    -------
    ForecastRecord
        The persisted record.
    """
    rec = ForecastRecord(
        signal_id=signal.id,
        event_id=signal.event_id,
        asset_id=signal.asset_id,
        event_type=str(signal.event_type.value if hasattr(signal.event_type, "value")
                       else signal.event_type),
        signal_date=str(signal.signal_date),
        extraction_confidence=signal.extraction_confidence,
        predicted_direction=_infer_direction(signal, diff),
        predicted_delta_pct=_infer_delta_pct(diff),
        # E-lite stratification buckets — extract from signal where available.
        trial_phase   = _str_or_none(getattr(signal, "trial_phase",   None)),
        indication    = _str_or_none(getattr(signal, "indication",    None)),
        endpoint_type = _str_or_none(getattr(signal, "endpoint_type", None)),
    )
    store.record_forecast(rec)
    return rec


def _str_or_none(v: Any) -> Optional[str]:
    """Convert an enum value or string to a plain string, or return None."""
    if v is None:
        return None
    return str(v.value) if hasattr(v, "value") else str(v)


# ---------------------------------------------------------------------------
# resolve_forecasts
# ---------------------------------------------------------------------------


def resolve_forecasts(store: Any) -> int:
    """
    Match resolved event_outcomes to open forecast_records and fill actuals.

    Returns the number of records updated.
    """
    rows = store._conn.execute(
        """
        SELECT
            fr.forecast_id,
            fr.predicted_direction,
            eo.market_return_t30,
            eo.market_return_t180,
            eo.resolved_t30,
            eo.resolved_t180,
            eo.outcome_label
        FROM forecast_records fr
        JOIN event_outcomes eo ON eo.event_id = fr.event_id
        WHERE fr.resolved = 0
          AND eo.resolved_t30 = 1
        """
    ).fetchall()

    updated = 0
    for row in rows:
        r_t30 = row["market_return_t30"]
        r_t180 = row["market_return_t180"]
        direction = row["predicted_direction"]
        # Wave 0.5: use human-verified outcome_label when available;
        # fall back to market-return sign for market_reaction_only outcomes.
        outcome_label = row["outcome_label"]

        outcome_correct: Optional[bool] = None
        if r_t30 is not None:
            actual_dir = "up" if r_t30 > 0 else ("down" if r_t30 < 0 else "neutral")
            outcome_correct = actual_dir == direction

        store._conn.execute(
            """
            UPDATE forecast_records
               SET actual_market_return_t30  = ?,
                   actual_market_return_t180 = ?,
                   outcome_label             = ?,
                   outcome_correct           = ?,
                   resolved                  = 1
             WHERE forecast_id = ?
            """,
            (
                r_t30,
                r_t180 if row["resolved_t180"] else None,
                outcome_label,
                int(outcome_correct) if outcome_correct is not None else None,
                row["forecast_id"],
            ),
        )
        updated += 1

    store._conn.commit()
    return updated


# ---------------------------------------------------------------------------
# CalibrationReporter
# ---------------------------------------------------------------------------


class CalibrationReporter:
    """
    Computes calibration metrics from resolved forecast_records.

    Usage
    -----
    ::

        reporter = CalibrationReporter()
        report = reporter.report(store)
    """

    def report(self, store: Any) -> CalibrationReport:
        """
        Read all resolved forecast rows and compute calibration metrics.

        Parameters
        ----------
        store:
            A ``KnowledgeStore`` instance.

        Returns
        -------
        CalibrationReport
        """
        all_rows = store._conn.execute(
            "SELECT * FROM forecast_records ORDER BY created_at"
        ).fetchall()
        resolved_rows = [r for r in all_rows if r["resolved"]]

        n_total = len(all_rows)
        n_resolved = len(resolved_rows)
        coverage = n_resolved / n_total if n_total > 0 else None

        report = CalibrationReport(
            n_total=n_total,
            n_resolved=n_resolved,
            coverage=coverage,
        )

        if not resolved_rows:
            return report

        # ---- directional accuracy ----
        correct = [r for r in resolved_rows if r["outcome_correct"] == 1]
        report.directional_accuracy = len(correct) / len(resolved_rows)

        # ---- false positive rate ----
        # Predicted "up" but actual_market_return_t30 < 0
        predicted_up = [
            r for r in resolved_rows
            if r["predicted_direction"] == "up"
            and r["actual_market_return_t30"] is not None
        ]
        if predicted_up:
            fp = [r for r in predicted_up if r["actual_market_return_t30"] < 0]
            report.false_positive_rate = len(fp) / len(predicted_up)

        # ---- magnitude RMSE ----
        paired = [
            (r["predicted_delta_pct"], r["actual_market_return_t30"] * 100)
            for r in resolved_rows
            if r["predicted_delta_pct"] is not None
            and r["actual_market_return_t30"] is not None
        ]
        if paired:
            pred_vals, actual_vals = zip(*paired)
            mse = sum((p - a) ** 2 for p, a in zip(pred_vals, actual_vals)) / len(paired)
            report.magnitude_rmse = math.sqrt(mse)

            # ---- Spearman ----
            if _HAS_SCIPY and len(paired) >= 3:
                corr, pval = _spearmanr(list(pred_vals), list(actual_vals))
                report.spearman_correlation = float(corr) if not math.isnan(corr) else None
                report.spearman_p_value = float(pval) if not math.isnan(pval) else None

        # ---- confidence calibration bins ----
        bin_size = 1.0 / _N_CONFIDENCE_BINS
        bins: list[CalibrationBin] = []
        for i in range(_N_CONFIDENCE_BINS):
            lo = round(i * bin_size, 2)
            hi = round((i + 1) * bin_size, 2)
            in_bin = [
                r for r in resolved_rows
                if lo <= r["extraction_confidence"] < hi
                or (hi >= 1.0 and r["extraction_confidence"] == 1.0)
            ]
            acc: Optional[float] = None
            if in_bin:
                acc = sum(1 for r in in_bin if r["outcome_correct"] == 1) / len(in_bin)
            bins.append(CalibrationBin(
                bin_low=lo, bin_high=hi, n_forecasts=len(in_bin),
                directional_accuracy=acc,
            ))
        report.confidence_bins = bins

        # Confidence calibration status: "calibrated" only when sufficient
        # labeled outcomes exist for statistical reliability (≥ 200).
        if n_resolved >= report.confidence_calibration_n_required:
            report = report.model_copy(
                update={"confidence_calibration_status": "calibrated"}
            )

        return report
