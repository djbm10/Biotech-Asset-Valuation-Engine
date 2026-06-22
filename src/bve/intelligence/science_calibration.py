"""Calibration diagnostics hooks for science thesis scoring.

This module intentionally does not mutate production weights. It only describes
whether enough labeled cases exist to consider future recalibration.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ScienceCalibrationRecommendation(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    DIAGNOSTICS_ONLY = "diagnostics_only"
    READY_FOR_RECALIBRATION_REVIEW = "ready_for_recalibration_review"


class ScienceCalibrationDiagnostic(BaseModel):
    calibration_status: str = "heuristic"
    recommendation: ScienceCalibrationRecommendation
    n_labeled_cases: int = Field(ge=0)
    min_cases_required: int = Field(default=50, ge=1)
    weight_update_allowed: bool = False
    rationale: str


def evaluate_calibration_readiness(
    n_labeled_cases: int,
    *,
    min_cases_required: int = 50,
) -> ScienceCalibrationDiagnostic:
    """Return readiness diagnostic; never updates production weights."""
    if n_labeled_cases < min_cases_required:
        return ScienceCalibrationDiagnostic(
            recommendation=ScienceCalibrationRecommendation.INSUFFICIENT_DATA,
            n_labeled_cases=n_labeled_cases,
            min_cases_required=min_cases_required,
            weight_update_allowed=False,
            rationale="Keep science modifier heuristic until enough labeled cases exist.",
        )
    return ScienceCalibrationDiagnostic(
        recommendation=ScienceCalibrationRecommendation.READY_FOR_RECALIBRATION_REVIEW,
        n_labeled_cases=n_labeled_cases,
        min_cases_required=min_cases_required,
        weight_update_allowed=False,
        rationale="Enough cases for review; explicit approval required before weight changes.",
    )
