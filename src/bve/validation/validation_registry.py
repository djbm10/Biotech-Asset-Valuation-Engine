"""Validation registry — stores and retrieves model grades."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from .model_grade import (
    ModelGrade,
    ModelGradeRecord,
    ValidationGateResult,
)

# Minimum gates per model and target grade
_POS_GATES_SCREENING = {
    "min_n": 50,
    "max_brier": 0.30,
    "min_auc": 0.55,
}
_POS_GATES_IC = {
    "min_n": 300,
    "max_ece": 0.08,
    "max_brier": 0.22,
    "min_auc": 0.65,
    "required_holdout": True,
}

_MNA_GATES_SCREENING = {
    "min_deal_universe_n": 50,
}
_MNA_GATES_IC = {
    "min_deal_universe_n": 150,
    "require_non_deal_controls": True,
    "precision_at_10_min": 0.20,
    "buyer_identification_top3_min": 0.40,
}

_CATALYST_GATES_IC = {
    "min_events_n": 200,
    "expected_move_direction_accuracy_min": 0.55,
    "calibration_error_max": 0.10,
}

_VALUATION_GATES_RESEARCH = {
    "launch_analog_backtest_min_n": 2,
}
_VALUATION_GATES_SCREENING = {
    "launch_analog_backtest_min_n": 10,
    "median_peak_sales_error_max_pct": 50.0,
}
_VALUATION_GATES_IC = {
    "launch_analog_backtest_min_n": 25,
    "median_peak_sales_error_max_pct": 35.0,
}


class ValidationRegistry:
    """In-memory store for model grades. In production, back with a database."""

    def __init__(self) -> None:
        self._records: dict[str, ModelGradeRecord] = {}
        self._populate_defaults()

    def _populate_defaults(self) -> None:
        """Seed with current known grades based on VALIDATION_STANDARD.md."""
        self._records["pos_model"] = ModelGradeRecord(
            model_name="pos_model",
            grade=ModelGrade.SCREENING_GRADE,
            last_validated=date(2026, 5, 15),
            n_samples=99,
            notes="Sprint 26C validated. Brier=0.2127, AUC=0.74. N<300 so IC_REVIEW_GRADE not yet achieved.",
        )
        self._records["valuation_model"] = ModelGradeRecord(
            model_name="valuation_model",
            grade=ModelGrade.RESEARCH_GRADE,
            last_validated=date(2026, 5, 15),
            n_samples=2,
            notes="N=2 historical cases (VRTX ivacaftor, INCY ruxolitinib). Survivor bias documented.",
        )
        self._records["mna_ranking"] = ModelGradeRecord(
            model_name="mna_ranking",
            grade=ModelGrade.UNVALIDATED,
            notes="No deal-universe backtest completed yet.",
        )
        self._records["catalyst_model"] = ModelGradeRecord(
            model_name="catalyst_model",
            grade=ModelGrade.UNVALIDATED,
            notes="No catalyst move accuracy measured yet.",
        )

    def get(self, model_name: str) -> ModelGradeRecord:
        if model_name not in self._records:
            return ModelGradeRecord(model_name=model_name, grade=ModelGrade.UNVALIDATED)
        return self._records[model_name]

    def set(self, record: ModelGradeRecord) -> None:
        self._records[record.model_name] = record

    def all_grades(self) -> list[ModelGradeRecord]:
        return list(self._records.values())

    def upgrade_grade(
        self,
        model_name: str,
        new_grade: ModelGrade,
        gate_results: Sequence[ValidationGateResult],
        n_samples: int,
        notes: str | None = None,
    ) -> ModelGradeRecord:
        existing = self.get(model_name)
        updated = existing.model_copy(
            update={
                "grade": new_grade,
                "last_validated": date.today(),
                "gate_results": list(gate_results),
                "n_samples": n_samples,
                "notes": notes,
            }
        )
        self.set(updated)
        return updated


# Module-level singleton
_default_registry = ValidationRegistry()


def get_registry() -> ValidationRegistry:
    return _default_registry
