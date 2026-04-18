"""Calibration engine — tracks predictions vs realized outcomes for model modules."""

from __future__ import annotations

import math
from datetime import date
from typing import Optional

from pydantic import BaseModel


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
    """Stores calibration records and computes per-module summaries.

    Records are held in-memory. Call add_record() to register a new prediction
    and resolve_record() once the realized outcome is known.
    """

    def __init__(self) -> None:
        self._records: list[CalibrationRecord] = []

    def add_record(self, record: CalibrationRecord) -> None:
        """Add a new calibration record."""
        self._records.append(record)

    def resolve_record(self, record_id: str, realized_value: float) -> CalibrationRecord:
        """Resolve a record with its realized value and compute error statistics.

        Returns the updated record (as a new object — the list is updated in place).
        Raises ValueError if the record_id is not found.
        """
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
        """Return aggregated calibration statistics for a given module."""
        resolved = [r for r in self._records if r.module == module and r.is_resolved]
        n = len(resolved)
        if n == 0:
            return CalibrationSummary(
                module=module,
                n_resolved=0,
                mean_error=0.0,
                rmse=0.0,
                bias=0.0,
            )
        errors = [r.error for r in resolved if r.error is not None]
        sq_errors = [r.squared_error for r in resolved if r.squared_error is not None]
        mean_error = sum(errors) / len(errors) if errors else 0.0
        rmse = math.sqrt(sum(sq_errors) / len(sq_errors)) if sq_errors else 0.0
        bias = mean_error  # signed average error
        return CalibrationSummary(
            module=module,
            n_resolved=n,
            mean_error=mean_error,
            rmse=rmse,
            bias=bias,
        )
