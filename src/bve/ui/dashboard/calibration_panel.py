"""Calibration health and bias summary panel data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class CalibrationModuleRow(BaseModel):
    module: str
    n_resolved: int
    mean_error: float
    rmse: float
    bias_direction: str          # "optimistic" / "pessimistic" / "calibrated"
    bias_magnitude: float        # 0-1
    status: str                  # "healthy" / "watch" / "degraded"


class CalibrationPanel(BaseModel):
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rows: list[CalibrationModuleRow]
    overall_bias_score: float    # 0-1
    most_biased_module: Optional[str] = None
    recommendations: list[str] = Field(default_factory=list)

    def degraded_modules(self) -> list[CalibrationModuleRow]:
        return [r for r in self.rows if r.status == "degraded"]

    def well_calibrated_modules(self) -> list[CalibrationModuleRow]:
        return [r for r in self.rows if r.status == "healthy"]
