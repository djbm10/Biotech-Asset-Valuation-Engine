"""Block 6I: Management Diligence Question Generation tests.

Tests for:
  1. UNKNOWN management → baseline diligence questions with HIGH priority
  2. Weak trial design → trial design questions
  3. Weak BD partnering → partnering questions
  4. Weak capital allocation → financing/capital questions
  5. Weak disclosure → transparency questions
  6. Weak governance → governance questions
  7. Questions have owner, priority, source_needed, trigger
  8. Critical risks → CRITICAL or HIGH priority
  9. No duplicate questions (unique question text)
  10. Stable deterministic output order
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_management_quality import (
    ManagementQualityInput,
    compute_management_quality_score,
)
from bve.intelligence.ma_management_diligence import (
    ManagementDiligenceQuestion,
    generate_management_diligence_questions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score(
    clinical: float | None = 0.80,
    trial_design: float | None = 0.80,
    regulatory: float | None = 0.80,
    capital: float | None = 0.80,
    bd: float | None = 0.80,
    disclosure: float | None = 0.80,
    governance: float | None = 0.80,
    staleness: int | None = None,
):
    inp = ManagementQualityInput(
        target_id="test",
        clinical_execution_quality=clinical,
        trial_design_judgment=trial_design,
        regulatory_execution=regulatory,
        capital_allocation_discipline=capital,
        bd_partnering_judgment=bd,
        disclosure_transparency=disclosure,
        governance_alignment=governance,
        data_staleness_days=staleness,
    )
    return compute_management_quality_score(inp)


def _unknown_score():
    inp = ManagementQualityInput(target_id="unknown")
    return compute_management_quality_score(inp)


# ---------------------------------------------------------------------------
# 1. UNKNOWN management → baseline diligence questions
# ---------------------------------------------------------------------------

class TestUnknownManagementBaseline:
    def test_generates_questions_when_unknown(self):
        questions = generate_management_diligence_questions(_unknown_score())
        assert len(questions) > 0

    def test_baseline_includes_high_priority(self):
        questions = generate_management_diligence_questions(_unknown_score())
        priorities = {q.priority for q in questions}
        assert "HIGH" in priorities or "CRITICAL" in priorities

    def test_baseline_covers_multiple_categories(self):
        questions = generate_management_diligence_questions(_unknown_score())
        categories = {q.category for q in questions}
        assert len(categories) >= 2


# ---------------------------------------------------------------------------
# 2. Weak trial design → trial design questions
# ---------------------------------------------------------------------------

class TestTrialDesignQuestions:
    def test_weak_trial_design_generates_trial_questions(self):
        s = _score(trial_design=0.20)
        questions = generate_management_diligence_questions(s)
        trial_qs = [q for q in questions if q.category == "trial_design"]
        assert len(trial_qs) >= 1

    def test_trial_design_question_covers_endpoint_selection(self):
        s = _score(trial_design=0.20)
        questions = generate_management_diligence_questions(s)
        texts = " ".join(q.question.lower() for q in questions if q.category == "trial_design")
        assert "endpoint" in texts or "trial" in texts or "design" in texts

    def test_trial_design_questions_have_clinical_owner(self):
        s = _score(trial_design=0.20)
        questions = [q for q in generate_management_diligence_questions(s)
                     if q.category == "trial_design"]
        owners = {q.owner for q in questions}
        assert "Clinical" in owners or "BD" in owners or "Regulatory" in owners


# ---------------------------------------------------------------------------
# 3. Weak BD partnering → partnering questions
# ---------------------------------------------------------------------------

class TestBDPartneringQuestions:
    def test_weak_bd_generates_partnering_questions(self):
        s = _score(bd=0.20)
        questions = generate_management_diligence_questions(s)
        bd_qs = [q for q in questions if q.category == "bd_partnering"]
        assert len(bd_qs) >= 1

    def test_bd_question_covers_structure_or_optionality(self):
        s = _score(bd=0.20)
        questions = generate_management_diligence_questions(s)
        texts = " ".join(q.question.lower() for q in questions if q.category == "bd_partnering")
        assert any(kw in texts for kw in ("partner", "optionality", "license", "rights", "structure"))


# ---------------------------------------------------------------------------
# 4. Weak capital allocation → financing questions
# ---------------------------------------------------------------------------

class TestCapitalAllocationQuestions:
    def test_weak_capital_generates_financing_questions(self):
        s = _score(capital=0.20)
        questions = generate_management_diligence_questions(s)
        cap_qs = [q for q in questions if q.category == "capital_allocation"]
        assert len(cap_qs) >= 1

    def test_capital_question_covers_runway_or_dilution(self):
        s = _score(capital=0.20)
        questions = generate_management_diligence_questions(s)
        texts = " ".join(q.question.lower() for q in questions if q.category == "capital_allocation")
        assert any(kw in texts for kw in ("cash", "runway", "dilut", "financ", "capital"))


# ---------------------------------------------------------------------------
# 5. Weak disclosure → transparency questions
# ---------------------------------------------------------------------------

class TestDisclosureQuestions:
    def test_weak_disclosure_generates_transparency_questions(self):
        s = _score(disclosure=0.20)
        questions = generate_management_diligence_questions(s)
        disc_qs = [q for q in questions if q.category == "disclosure"]
        assert len(disc_qs) >= 1

    def test_disclosure_question_covers_data_completeness(self):
        s = _score(disclosure=0.20)
        questions = generate_management_diligence_questions(s)
        texts = " ".join(q.question.lower() for q in questions if q.category == "disclosure")
        assert any(kw in texts for kw in ("disclos", "safet", "data", "filing", "transparent"))


# ---------------------------------------------------------------------------
# 6. Weak governance → governance questions
# ---------------------------------------------------------------------------

class TestGovernanceQuestions:
    def test_weak_governance_generates_governance_questions(self):
        s = _score(governance=0.20)
        questions = generate_management_diligence_questions(s)
        gov_qs = [q for q in questions if q.category == "governance"]
        assert len(gov_qs) >= 1

    def test_governance_question_covers_board_or_alignment(self):
        s = _score(governance=0.20)
        questions = generate_management_diligence_questions(s)
        texts = " ".join(q.question.lower() for q in questions if q.category == "governance")
        assert any(kw in texts for kw in ("board", "insider", "align", "control", "shareholder"))


# ---------------------------------------------------------------------------
# 7. Questions have required fields
# ---------------------------------------------------------------------------

class TestQuestionFields:
    def test_all_questions_have_required_fields(self):
        s = _unknown_score()
        questions = generate_management_diligence_questions(s)
        for q in questions:
            assert isinstance(q, ManagementDiligenceQuestion)
            assert q.category
            assert q.question
            assert q.priority in {"CRITICAL", "HIGH", "MEDIUM"}
            assert q.owner
            assert isinstance(q.source_needed, list)
            assert q.trigger

    def test_source_needed_is_non_empty_list(self):
        questions = generate_management_diligence_questions(_unknown_score())
        for q in questions:
            assert len(q.source_needed) >= 1


# ---------------------------------------------------------------------------
# 8. Critical risks → CRITICAL or HIGH priority
# ---------------------------------------------------------------------------

class TestQuestionPriority:
    def test_unknown_management_produces_high_or_critical(self):
        questions = generate_management_diligence_questions(_unknown_score())
        assert any(q.priority in {"CRITICAL", "HIGH"} for q in questions)

    def test_weak_trial_design_produces_high_priority(self):
        s = _score(trial_design=0.15)
        questions = generate_management_diligence_questions(s)
        trial_qs = [q for q in questions if q.category == "trial_design"]
        assert any(q.priority in {"CRITICAL", "HIGH"} for q in trial_qs)

    def test_strong_management_produces_lower_priority_or_empty(self):
        s = _score()  # all 0.80 — no weak components
        questions = generate_management_diligence_questions(s)
        # Strong management should either produce no questions or only MEDIUM
        high_critical = [q for q in questions if q.priority in {"CRITICAL", "HIGH"}]
        assert len(high_critical) == 0


# ---------------------------------------------------------------------------
# 9. No duplicate questions
# ---------------------------------------------------------------------------

class TestNoDuplicateQuestions:
    def test_no_duplicate_question_text(self):
        s = _score(trial_design=0.20, capital=0.20, governance=0.20)
        questions = generate_management_diligence_questions(s)
        texts = [q.question for q in questions]
        assert len(texts) == len(set(texts))

    def test_unknown_no_duplicates(self):
        questions = generate_management_diligence_questions(_unknown_score())
        texts = [q.question for q in questions]
        assert len(texts) == len(set(texts))


# ---------------------------------------------------------------------------
# 10. Deterministic output order
# ---------------------------------------------------------------------------

class TestDeterministicOrder:
    def test_same_input_same_order(self):
        s = _score(trial_design=0.20, capital=0.20)
        q1 = generate_management_diligence_questions(s)
        q2 = generate_management_diligence_questions(s)
        assert [q.question for q in q1] == [q.question for q in q2]

    def test_context_does_not_break_ordering(self):
        s = _unknown_score()
        q1 = generate_management_diligence_questions(s, context={"buyer": "pfizer"})
        q2 = generate_management_diligence_questions(s, context={"buyer": "pfizer"})
        assert [q.question for q in q1] == [q.question for q in q2]
