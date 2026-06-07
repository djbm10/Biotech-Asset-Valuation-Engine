"""Model validation grades, grade promotion logic, and hard output disclaimers.

Every report that contains model outputs MUST display the disclaimer returned
by ``validation_disclaimer()``.  The disclaimer is specific to the validation
status and cannot be suppressed without explicitly passing
``suppress_disclaimer=True`` (reserved for machine-readable JSON payloads only).

Canonical validation status hierarchy (weakest → strongest):

    UNVALIDATED → DIRECTIONAL_ONLY → RESEARCH_GRADE →
    SCREENING_GRADE → INSTITUTIONAL_GRADE

These map onto the internal ``ModelGrade`` enum which has one additional tier
(IC_REVIEW_GRADE / DECISION_GRADE) used by the M&A and portfolio layers.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Plan-aligned validation status (used on every public-facing output)
# ---------------------------------------------------------------------------

class BacktestValidationStatus(str, Enum):
    """Hard validation labels displayed on every backtest report.

    Acceptance criteria before promotion:
      DIRECTIONAL_ONLY  — positive signal observed; N too small for significance
      RESEARCH_GRADE    — POS: N≥99, AUC≥0.65, oncology-only; Replay: N≥50, p<0.20
      SCREENING_GRADE   — POS: N≥300, multi-TA, AUC≥0.70, ECE≤0.08; Replay: N≥150, p<0.10
      INSTITUTIONAL_GRADE — all above + walk-forward + cost-adjusted + live shadow book
    """
    UNVALIDATED = "unvalidated"
    DIRECTIONAL_ONLY = "directional_only"
    RESEARCH_GRADE = "research_grade"
    SCREENING_GRADE = "screening_grade"
    INSTITUTIONAL_GRADE = "institutional_grade"


# Current validated status for each model component
CURRENT_STATUS: dict[str, BacktestValidationStatus] = {
    "pos_model_oncology":     BacktestValidationStatus.RESEARCH_GRADE,
    "pos_model_non_oncology": BacktestValidationStatus.UNVALIDATED,
    "historical_replay":      BacktestValidationStatus.DIRECTIONAL_ONLY,
    "trading_signal":         BacktestValidationStatus.UNVALIDATED,
    "mna_probability":        BacktestValidationStatus.UNVALIDATED,
    "acquisition_probability":BacktestValidationStatus.UNVALIDATED,
}

_STATUS_DISCLAIMER: dict[BacktestValidationStatus, str] = {
    BacktestValidationStatus.UNVALIDATED: (
        "⛔  UNVALIDATED — This output has not been backtested. "
        "Do not use for trade sizing, acquisition probability, or portfolio decisions."
    ),
    BacktestValidationStatus.DIRECTIONAL_ONLY: (
        "⚠   DIRECTIONAL ONLY — This backtest has not demonstrated statistically significant alpha. "
        "N is too small to distinguish signal from noise. "
        "Use for research and screening only. Not suitable for capital deployment."
    ),
    BacktestValidationStatus.RESEARCH_GRADE: (
        "ℹ   RESEARCH GRADE — This output has directional validation (oncology only, N=99). "
        "Brier=0.2127, AUC=0.74. "
        "Not calibrated across therapeutic areas. Not suitable for trade sizing or acquisition probability."
    ),
    BacktestValidationStatus.SCREENING_GRADE: (
        "✓   SCREENING GRADE — Multi-TA validated, N≥300, AUC≥0.70, ECE≤0.08. "
        "Suitable for screening and IC discussion. Not decision-grade."
    ),
    BacktestValidationStatus.INSTITUTIONAL_GRADE: (
        "✓✓  INSTITUTIONAL GRADE — Walk-forward validated, cost-adjusted, live shadow book confirmed. "
        "Suitable for IC review with live paper track record."
    ),
}

_FORBIDDEN_CLAIMS: dict[BacktestValidationStatus, list[str]] = {
    BacktestValidationStatus.UNVALIDATED: [
        "validated alpha", "institutional-grade", "tradeable edge",
        "acquisition probability", "decision-grade",
    ],
    BacktestValidationStatus.DIRECTIONAL_ONLY: [
        "validated alpha", "institutional-grade", "tradeable edge",
        "acquisition probability", "decision-grade",
    ],
    BacktestValidationStatus.RESEARCH_GRADE: [
        "institutional-grade", "tradeable edge", "acquisition probability",
    ],
    BacktestValidationStatus.SCREENING_GRADE: [
        "institutional-grade", "tradeable edge",
    ],
    BacktestValidationStatus.INSTITUTIONAL_GRADE: [],
}


def validation_disclaimer(
    status: BacktestValidationStatus,
    *,
    width: int = 72,
    suppress_disclaimer: bool = False,
) -> str:
    """Return the hard disclaimer string for a given validation status.

    This must be prepended to every human-readable backtest report.
    Machine-readable JSON payloads may pass suppress_disclaimer=True
    and embed the status field directly.
    """
    if suppress_disclaimer:
        return ""
    border = "─" * width
    return f"\n{border}\n{_STATUS_DISCLAIMER[status]}\n{border}\n"


def forbidden_claims(status: BacktestValidationStatus) -> list[str]:
    """Return the list of claims forbidden at this validation level."""
    return _FORBIDDEN_CLAIMS.get(status, [])


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
