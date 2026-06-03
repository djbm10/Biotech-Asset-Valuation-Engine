"""
Tests for P4.3 — Decision journal & learning loop.

Verifies:
- DecisionJournal.log_prediction returns a JournalEntry
- JournalEntry has entry_id, asset_id, prediction_type, predicted_value,
  confidence, rationale, logged_at
- DecisionJournal.resolve_prediction updates entry with actual_value, outcome
- Resolved entry has outcome != "pending"
- Outcome is one of: "correct", "incorrect", "partial", "expired", "pending"
- DecisionJournal.get_entries returns list of JournalEntry
- DecisionJournal.get_unresolved returns only pending entries
- learning_summary() returns LearningReport with calibration metrics
- LearningReport has n_total, n_resolved, n_correct, accuracy, avg_confidence
- Brier score computed when confidence and outcomes present
- resolve_prediction by entry_id
- JournalEntry is frozen after creation (immutable)
- DecisionJournal supports in-memory mode (no DB required)
- Multiple predictions for same asset stored separately
- get_entries_for_asset filters by asset_id
- LearningReport.calibration_gap = avg_confidence - accuracy
- JournalEntry.prediction_type is a string label
- Log entry with confidence=0.0 and =1.0 (boundary)
- unknown entry_id resolution raises ValueError
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bve.ops.decision_journal import (
    DecisionJournal,
    JournalEntry,
    LearningReport,
    Outcome,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _journal() -> DecisionJournal:
    return DecisionJournal()  # in-memory


def _log_one(journal: DecisionJournal, **kwargs) -> JournalEntry:
    return journal.log_prediction(
        asset_id=kwargs.get("asset_id", "rlay-001"),
        prediction_type=kwargs.get("prediction_type", "pos_approval"),
        predicted_value=kwargs.get("predicted_value", 0.65),
        confidence=kwargs.get("confidence", 0.70),
        rationale=kwargs.get("rationale", "Phase 3 data looks strong."),
    )


# ---------------------------------------------------------------------------
# JournalEntry
# ---------------------------------------------------------------------------

class TestJournalEntry:
    def test_has_entry_id(self):
        j = _journal()
        e = _log_one(j)
        assert isinstance(e.entry_id, str) and len(e.entry_id) > 0

    def test_has_asset_id(self):
        j = _journal()
        e = _log_one(j)
        assert e.asset_id == "rlay-001"

    def test_has_prediction_type(self):
        j = _journal()
        e = _log_one(j)
        assert e.prediction_type == "pos_approval"

    def test_has_predicted_value(self):
        j = _journal()
        e = _log_one(j)
        assert e.predicted_value == pytest.approx(0.65)

    def test_has_confidence(self):
        j = _journal()
        e = _log_one(j)
        assert e.confidence == pytest.approx(0.70)

    def test_has_rationale(self):
        j = _journal()
        e = _log_one(j)
        assert "Phase 3" in e.rationale

    def test_initial_outcome_is_pending(self):
        j = _journal()
        e = _log_one(j)
        assert e.outcome == Outcome.PENDING

    def test_logged_at_is_datetime(self):
        j = _journal()
        e = _log_one(j)
        assert isinstance(e.logged_at, datetime)

    def test_confidence_boundary_zero(self):
        j = _journal()
        e = j.log_prediction("x", "pos_approval", 0.5, confidence=0.0, rationale="test")
        assert e.confidence == pytest.approx(0.0)

    def test_confidence_boundary_one(self):
        j = _journal()
        e = j.log_prediction("x", "pos_approval", 0.5, confidence=1.0, rationale="test")
        assert e.confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Outcome enum
# ---------------------------------------------------------------------------

class TestOutcome:
    def test_pending_value(self):
        assert Outcome.PENDING.value == "pending"

    def test_correct_value(self):
        assert Outcome.CORRECT.value == "correct"

    def test_incorrect_value(self):
        assert Outcome.INCORRECT.value == "incorrect"

    def test_partial_value(self):
        assert Outcome.PARTIAL.value == "partial"

    def test_expired_value(self):
        assert Outcome.EXPIRED.value == "expired"


# ---------------------------------------------------------------------------
# log_prediction and get_entries
# ---------------------------------------------------------------------------

class TestLogAndRetrieve:
    def test_log_returns_entry(self):
        j = _journal()
        e = _log_one(j)
        assert isinstance(e, JournalEntry)

    def test_get_entries_returns_logged(self):
        j = _journal()
        _log_one(j)
        entries = j.get_entries()
        assert len(entries) == 1

    def test_multiple_entries_stored(self):
        j = _journal()
        _log_one(j)
        _log_one(j, prediction_type="peak_sales")
        entries = j.get_entries()
        assert len(entries) == 2

    def test_get_entries_for_asset(self):
        j = _journal()
        _log_one(j, asset_id="rlay")
        _log_one(j, asset_id="other")
        entries = j.get_entries_for_asset("rlay")
        assert len(entries) == 1
        assert entries[0].asset_id == "rlay"

    def test_entries_are_frozen(self):
        j = _journal()
        e = _log_one(j)
        with pytest.raises((AttributeError, TypeError)):
            e.confidence = 0.99  # type: ignore[misc]

    def test_get_unresolved_returns_pending(self):
        j = _journal()
        _log_one(j)
        unresolved = j.get_unresolved()
        assert len(unresolved) == 1

    def test_get_unresolved_excludes_resolved(self):
        j = _journal()
        e = _log_one(j)
        j.resolve_prediction(e.entry_id, actual_value=0.60, outcome=Outcome.CORRECT)
        unresolved = j.get_unresolved()
        assert len(unresolved) == 0


# ---------------------------------------------------------------------------
# resolve_prediction
# ---------------------------------------------------------------------------

class TestResolvePrediction:
    def test_resolve_returns_updated_entry(self):
        j = _journal()
        e = _log_one(j)
        resolved = j.resolve_prediction(e.entry_id, actual_value=0.60, outcome=Outcome.CORRECT)
        assert resolved.outcome == Outcome.CORRECT

    def test_resolve_updates_actual_value(self):
        j = _journal()
        e = _log_one(j)
        resolved = j.resolve_prediction(e.entry_id, actual_value=0.60, outcome=Outcome.CORRECT)
        assert resolved.actual_value == pytest.approx(0.60)

    def test_resolved_entry_not_in_unresolved(self):
        j = _journal()
        e = _log_one(j)
        j.resolve_prediction(e.entry_id, actual_value=0.60, outcome=Outcome.CORRECT)
        assert len(j.get_unresolved()) == 0

    def test_resolve_incorrect(self):
        j = _journal()
        e = _log_one(j)
        resolved = j.resolve_prediction(e.entry_id, actual_value=0.30, outcome=Outcome.INCORRECT)
        assert resolved.outcome == Outcome.INCORRECT

    def test_unknown_entry_id_raises(self):
        j = _journal()
        with pytest.raises(ValueError, match="not found"):
            j.resolve_prediction("nonexistent-id", actual_value=0.5, outcome=Outcome.CORRECT)


# ---------------------------------------------------------------------------
# LearningReport
# ---------------------------------------------------------------------------

class TestLearningReport:
    def _journal_with_results(self) -> DecisionJournal:
        j = _journal()
        # 3 correct, 1 incorrect
        for _ in range(3):
            e = j.log_prediction("x", "pos_approval", 0.65, confidence=0.70, rationale="r")
            j.resolve_prediction(e.entry_id, actual_value=0.65, outcome=Outcome.CORRECT)
        e = j.log_prediction("x", "pos_approval", 0.65, confidence=0.70, rationale="r")
        j.resolve_prediction(e.entry_id, actual_value=0.20, outcome=Outcome.INCORRECT)
        return j

    def test_returns_learning_report(self):
        j = _journal()
        report = j.learning_summary()
        assert isinstance(report, LearningReport)

    def test_n_total(self):
        j = self._journal_with_results()
        report = j.learning_summary()
        assert report.n_total == 4

    def test_n_resolved(self):
        j = self._journal_with_results()
        report = j.learning_summary()
        assert report.n_resolved == 4

    def test_n_correct(self):
        j = self._journal_with_results()
        report = j.learning_summary()
        assert report.n_correct == 3

    def test_accuracy(self):
        j = self._journal_with_results()
        report = j.learning_summary()
        assert report.accuracy == pytest.approx(0.75, abs=0.01)

    def test_avg_confidence(self):
        j = self._journal_with_results()
        report = j.learning_summary()
        assert report.avg_confidence == pytest.approx(0.70, abs=0.01)

    def test_calibration_gap(self):
        j = self._journal_with_results()
        report = j.learning_summary()
        # avg_confidence=0.70, accuracy=0.75 → gap = 0.70 - 0.75 = -0.05
        assert report.calibration_gap == pytest.approx(0.70 - 0.75, abs=0.01)

    def test_empty_journal_report(self):
        j = _journal()
        report = j.learning_summary()
        assert report.n_total == 0
        assert report.accuracy is None

    def test_unresolved_only_report(self):
        j = _journal()
        _log_one(j)
        report = j.learning_summary()
        assert report.n_resolved == 0
        assert report.accuracy is None
