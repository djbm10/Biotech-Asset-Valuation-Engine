"""Tests for model grade assignment and validation registry."""

import pytest
from datetime import date

from bve.validation.model_grade import (
    ModelGrade,
    ModelGradeRecord,
    ValidationGateResult,
    GRADE_ORDER,
)
from bve.validation.validation_registry import ValidationRegistry
from bve.reporting.validation_badges import render_badge, render_badge_block, get_output_warning


class TestModelGrade:
    def test_grade_order_is_ascending(self):
        assert GRADE_ORDER.index(ModelGrade.UNVALIDATED) < GRADE_ORDER.index(ModelGrade.DECISION_GRADE)
        assert GRADE_ORDER.index(ModelGrade.SCREENING_GRADE) < GRADE_ORDER.index(ModelGrade.IC_REVIEW_GRADE)

    def test_warning_message_none_for_decision_grade(self):
        record = ModelGradeRecord(
            model_name="pos_model",
            grade=ModelGrade.DECISION_GRADE,
            last_validated=date.today(),
        )
        assert record.warning_message is None

    def test_warning_message_present_for_unvalidated(self):
        record = ModelGradeRecord(model_name="pos_model", grade=ModelGrade.UNVALIDATED)
        assert record.warning_message is not None
        assert "UNVALIDATED" in record.warning_message

    def test_is_decision_grade(self):
        r = ModelGradeRecord(model_name="x", grade=ModelGrade.DECISION_GRADE)
        assert r.is_decision_grade

    def test_is_not_decision_grade(self):
        r = ModelGradeRecord(model_name="x", grade=ModelGrade.SCREENING_GRADE)
        assert not r.is_decision_grade

    def test_is_at_least_screening(self):
        for g in [ModelGrade.SCREENING_GRADE, ModelGrade.IC_REVIEW_GRADE, ModelGrade.DECISION_GRADE]:
            r = ModelGradeRecord(model_name="x", grade=g)
            assert r.is_at_least_screening

    def test_not_at_least_screening_when_lower(self):
        for g in [ModelGrade.UNVALIDATED, ModelGrade.RESEARCH_GRADE]:
            r = ModelGradeRecord(model_name="x", grade=g)
            assert not r.is_at_least_screening

    def test_badge_dict_has_required_keys(self):
        r = ModelGradeRecord(
            model_name="pos_model",
            grade=ModelGrade.SCREENING_GRADE,
            last_validated=date.today(),
            n_samples=99,
        )
        badge = r.to_badge_dict()
        assert "model" in badge
        assert "grade" in badge
        assert "last_validated" in badge
        assert "warning" in badge


class TestValidationRegistry:
    def test_default_registry_has_known_models(self):
        reg = ValidationRegistry()
        assert reg.get("pos_model").grade == ModelGrade.SCREENING_GRADE
        assert reg.get("mna_ranking").grade == ModelGrade.UNVALIDATED
        assert reg.get("valuation_model").grade == ModelGrade.RESEARCH_GRADE

    def test_unknown_model_returns_unvalidated(self):
        reg = ValidationRegistry()
        r = reg.get("nonexistent_model")
        assert r.grade == ModelGrade.UNVALIDATED

    def test_upgrade_grade(self):
        reg = ValidationRegistry()
        gate = ValidationGateResult(gate_name="min_n", passed=True, actual_value=350, required_value=300)
        updated = reg.upgrade_grade(
            "pos_model",
            ModelGrade.IC_REVIEW_GRADE,
            gate_results=[gate],
            n_samples=350,
            notes="Promoted after N=350 holdout run",
        )
        assert updated.grade == ModelGrade.IC_REVIEW_GRADE
        assert reg.get("pos_model").grade == ModelGrade.IC_REVIEW_GRADE

    def test_set_and_get(self):
        reg = ValidationRegistry()
        record = ModelGradeRecord(
            model_name="custom_model",
            grade=ModelGrade.RESEARCH_GRADE,
            n_samples=10,
        )
        reg.set(record)
        assert reg.get("custom_model").grade == ModelGrade.RESEARCH_GRADE

    def test_all_grades_returns_list(self):
        reg = ValidationRegistry()
        grades = reg.all_grades()
        assert len(grades) >= 4


class TestValidationBadges:
    def test_render_badge_contains_grade(self):
        record = ModelGradeRecord(
            model_name="pos_model",
            grade=ModelGrade.SCREENING_GRADE,
            last_validated=date.today(),
            n_samples=99,
        )
        badge = render_badge(record)
        assert "SCREENING" in badge
        assert "pos_model" in badge

    def test_render_badge_block_contains_warnings(self):
        reg = ValidationRegistry()
        block = render_badge_block(["pos_model", "mna_ranking"], registry=reg)
        assert "SCREENING" in block
        assert "UNVALIDATED" in block

    def test_output_warning_none_for_decision_grade(self):
        reg = ValidationRegistry()
        reg.set(ModelGradeRecord(model_name="my_model", grade=ModelGrade.DECISION_GRADE))
        assert get_output_warning("my_model", registry=reg) is None

    def test_output_warning_present_for_screening(self):
        reg = ValidationRegistry()
        warning = get_output_warning("pos_model", registry=reg)
        assert warning is not None
        assert "SCREENING" in warning
