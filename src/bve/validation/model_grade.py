"""Model validation grades and grade promotion logic."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class ModelGrade(str, Enum):
    UNVALIDATED = "UNVALIDATED"
    RESEARCH_GRADE = "RESEARCH_GRADE"
    SCREENING_GRADE = "SCREENING_GRADE"
    IC_REVIEW_GRADE = "IC_REVIEW_GRADE"
    DECISION_GRADE = "DECISION_GRADE"


GRADE_ORDER = [
    ModelGrade.UNVALIDATED,
    ModelGrade.RESEARCH_GRADE,
    ModelGrade.SCREENING_GRADE,
    ModelGrade.IC_REVIEW_GRADE,
    ModelGrade.DECISION_GRADE,
]

GRADE_WARNING = {
    ModelGrade.UNVALIDATED: (
        "This output is UNVALIDATED. Do not use for trade sizing or acquisition probability."
    ),
    ModelGrade.RESEARCH_GRADE: (
        "This output is RESEARCH_GRADE only. Do not use for trade sizing or acquisition probability."
    ),
    ModelGrade.SCREENING_GRADE: (
        "This output is SCREENING_GRADE only. Do not use for trade sizing or acquisition probability."
    ),
    ModelGrade.IC_REVIEW_GRADE: (
        "This output is IC_REVIEW_GRADE. Suitable for IC discussion; not for autonomous capital deployment."
    ),
    ModelGrade.DECISION_GRADE: None,  # no warning needed
}


class ValidationGateResult(BaseModel):
    """Result of evaluating one validation gate."""

    gate_name: str
    passed: bool
    actual_value: float | int | bool | None = None
    required_value: float | int | bool | None = None
    note: str | None = None


class ModelGradeRecord(BaseModel):
    """Stored validation grade for a specific model."""

    model_name: str
    grade: ModelGrade = ModelGrade.UNVALIDATED
    last_validated: date | None = None
    gate_results: list[ValidationGateResult] = Field(default_factory=list)
    n_samples: int = 0
    notes: str | None = None
    expires: date | None = None

    @property
    def warning_message(self) -> str | None:
        return GRADE_WARNING.get(self.grade)

    @property
    def is_decision_grade(self) -> bool:
        return self.grade == ModelGrade.DECISION_GRADE

    @property
    def is_at_least_screening(self) -> bool:
        return GRADE_ORDER.index(self.grade) >= GRADE_ORDER.index(ModelGrade.SCREENING_GRADE)

    def to_badge_dict(self) -> dict:
        return {
            "model": self.model_name,
            "grade": self.grade.value,
            "last_validated": self.last_validated.isoformat() if self.last_validated else None,
            "n_samples": self.n_samples,
            "warning": self.warning_message,
        }
