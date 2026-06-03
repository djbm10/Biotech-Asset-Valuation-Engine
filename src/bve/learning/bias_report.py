"""Bias report engine — identifies systematic optimism/pessimism across modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from bve.learning.calibration import CalibrationSummary


class BiasEntry(BaseModel):
    """Bias assessment for a single module."""

    module: str
    direction: str  # "optimistic" | "pessimistic" | "calibrated"
    magnitude: float = Field(ge=0.0, le=1.0)
    n_samples: int
    example_assets: list[str] = Field(default_factory=list)


class BiasReport(BaseModel):
    """Aggregated bias report across all modules."""

    report_id: str
    generated_at: datetime
    entries: list[BiasEntry] = Field(default_factory=list)
    most_biased_module: Optional[str] = None
    overall_bias_score: float = Field(ge=0.0, le=1.0)
    recommendations: list[str] = Field(default_factory=list)


_BIAS_THRESHOLD = 0.05  # absolute bias below this is "calibrated"


class BiasReportEngine:
    """Generates a BiasReport from a list of CalibrationSummary objects."""

    def generate(self, calibration_summaries: list[CalibrationSummary]) -> BiasReport:
        """Analyse calibration summaries and return a structured bias report."""
        entries: list[BiasEntry] = []
        for summary in calibration_summaries:
            bias = summary.bias
            magnitude = min(1.0, abs(bias))
            if bias > _BIAS_THRESHOLD:
                direction = "optimistic"
            elif bias < -_BIAS_THRESHOLD:
                direction = "pessimistic"
            else:
                direction = "calibrated"
            entries.append(
                BiasEntry(
                    module=summary.module,
                    direction=direction,
                    magnitude=magnitude,
                    n_samples=summary.n_resolved,
                    example_assets=[],
                )
            )

        most_biased: Optional[str] = None
        if entries:
            most_biased_entry = max(entries, key=lambda e: e.magnitude)
            if most_biased_entry.direction != "calibrated":
                most_biased = most_biased_entry.module

        overall_score = (
            sum(e.magnitude for e in entries) / len(entries) if entries else 0.0
        )
        overall_score = min(1.0, overall_score)

        recommendations = _build_recommendations(entries)

        return BiasReport(
            report_id=str(uuid4()),
            generated_at=datetime.now(timezone.utc),
            entries=entries,
            most_biased_module=most_biased,
            overall_bias_score=overall_score,
            recommendations=recommendations,
        )


def _build_recommendations(entries: list[BiasEntry]) -> list[str]:
    recs: list[str] = []
    for entry in entries:
        if entry.direction == "optimistic":
            recs.append(
                f"Module '{entry.module}' is systematically optimistic (bias={entry.magnitude:.3f}). "
                f"Consider downward recalibration."
            )
        elif entry.direction == "pessimistic":
            recs.append(
                f"Module '{entry.module}' is systematically pessimistic (bias={entry.magnitude:.3f}). "
                f"Consider upward recalibration."
            )
    if not recs:
        recs.append("All modules appear well-calibrated. No recalibration recommended.")
    return recs
