"""
P4.3 — Decision journal & learning loop.

Records analyst/model predictions with their confidence and rationale, then
tracks actual outcomes when they become known. Over time, the journal surfaces
calibration metrics (accuracy vs. confidence, Brier score) that can inform
model recalibration and decision process improvement.

Design
------
- ``DecisionJournal`` is an in-memory store (optionally backed by SQLite).
- Entries are immutable ``JournalEntry`` frozen dataclasses.
- Resolving a prediction creates a new entry replacing the pending one.
- ``learning_summary()`` returns a ``LearningReport`` with calibration stats.
- No external dependencies required — pure Python.

Usage
-----
>>> from bve.ops.decision_journal import DecisionJournal, Outcome
>>> journal = DecisionJournal()
>>> entry = journal.log_prediction(
...     asset_id="rlay-001",
...     prediction_type="pos_approval",
...     predicted_value=0.65,
...     confidence=0.70,
...     rationale="Phase 3 RELAY-301 data suggests strong responder enrichment.",
... )
>>> # ... after outcome is known ...
>>> journal.resolve_prediction(entry.entry_id, actual_value=0.60, outcome=Outcome.CORRECT)
>>> report = journal.learning_summary()
>>> report.accuracy
0.75
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Outcome(str, Enum):
    PENDING = "pending"
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Journal entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JournalEntry:
    """
    A single logged prediction with optional resolution.

    Attributes
    ----------
    entry_id : str
        UUID4 identifier.
    asset_id : str
        Asset this prediction concerns.
    prediction_type : str
        Label describing what was predicted (e.g. "pos_approval", "peak_sales").
    predicted_value : float
        Numeric prediction (POS as 0–1, sales in $M, etc.).
    confidence : float
        Analyst/model confidence in the prediction (0–1).
    rationale : str
        Free-text explanation for the prediction.
    logged_at : datetime
        UTC timestamp when logged.
    outcome : Outcome
        Resolution status; PENDING until resolve_prediction() is called.
    actual_value : Optional[float]
        Actual observed value; None until resolved.
    resolved_at : Optional[datetime]
        UTC timestamp of resolution; None until resolved.
    """
    entry_id: str
    asset_id: str
    prediction_type: str
    predicted_value: float
    confidence: float
    rationale: str
    logged_at: datetime
    outcome: Outcome
    actual_value: Optional[float] = None
    resolved_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Learning report
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LearningReport:
    """
    Calibration summary across all resolved journal entries.

    Attributes
    ----------
    n_total : int
        Total entries (pending + resolved).
    n_resolved : int
        Entries with a final outcome.
    n_correct : int
        Entries with outcome == CORRECT.
    accuracy : Optional[float]
        n_correct / n_resolved; None when n_resolved == 0.
    avg_confidence : Optional[float]
        Mean confidence across resolved entries; None when none.
    calibration_gap : Optional[float]
        avg_confidence − accuracy; negative = overconfidence in wrong direction.
    brier_score : Optional[float]
        Mean squared error between confidence and binary correct indicator.
        Lower is better. None when n_resolved == 0.
    """
    n_total: int
    n_resolved: int
    n_correct: int
    accuracy: Optional[float]
    avg_confidence: Optional[float]
    calibration_gap: Optional[float]
    brier_score: Optional[float]


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

class DecisionJournal:
    """
    In-memory decision journal with optional SQLite persistence.

    Parameters
    ----------
    db_path : Optional[str]
        Path to SQLite database. If None, operates in-memory only.
        (SQLite persistence is planned for a future iteration.)
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        # In-memory store: {entry_id: JournalEntry}
        self._entries: dict[str, JournalEntry] = {}
        self._db_path = db_path  # reserved for future SQLite backing

    # ------------------------------------------------------------------ #
    # Write                                                                #
    # ------------------------------------------------------------------ #

    def log_prediction(
        self,
        asset_id: str,
        prediction_type: str,
        predicted_value: float,
        confidence: float,
        rationale: str,
    ) -> JournalEntry:
        """
        Log a new prediction.

        Parameters
        ----------
        asset_id : str
            Asset the prediction concerns.
        prediction_type : str
            Descriptive label (e.g. "pos_approval", "peak_sales_millions").
        predicted_value : float
            Numeric prediction.
        confidence : float
            Confidence level in [0, 1].
        rationale : str
            Free-text explanation.

        Returns
        -------
        JournalEntry
            Newly created entry with outcome=PENDING.
        """
        entry = JournalEntry(
            entry_id=str(uuid.uuid4()),
            asset_id=asset_id,
            prediction_type=prediction_type,
            predicted_value=predicted_value,
            confidence=confidence,
            rationale=rationale,
            logged_at=datetime.now(timezone.utc),
            outcome=Outcome.PENDING,
        )
        self._entries[entry.entry_id] = entry
        return entry

    def resolve_prediction(
        self,
        entry_id: str,
        actual_value: float,
        outcome: Outcome,
    ) -> JournalEntry:
        """
        Resolve a pending prediction with the observed outcome.

        Parameters
        ----------
        entry_id : str
            ID of the entry to resolve.
        actual_value : float
            Observed actual value.
        outcome : Outcome
            Classification of the prediction (CORRECT, INCORRECT, PARTIAL, EXPIRED).

        Returns
        -------
        JournalEntry
            Updated (new frozen) entry with outcome and actual_value set.

        Raises
        ------
        ValueError
            If entry_id is not found in the journal.
        """
        original = self._entries.get(entry_id)
        if original is None:
            raise ValueError(f"Entry {entry_id!r} not found in journal")

        # Dataclass is frozen — replace with a new instance
        resolved = JournalEntry(
            entry_id=original.entry_id,
            asset_id=original.asset_id,
            prediction_type=original.prediction_type,
            predicted_value=original.predicted_value,
            confidence=original.confidence,
            rationale=original.rationale,
            logged_at=original.logged_at,
            outcome=outcome,
            actual_value=actual_value,
            resolved_at=datetime.now(timezone.utc),
        )
        self._entries[entry_id] = resolved
        return resolved

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    def get_entries(self) -> list[JournalEntry]:
        """All entries, ordered by logged_at ascending."""
        return sorted(self._entries.values(), key=lambda e: e.logged_at)

    def get_entries_for_asset(self, asset_id: str) -> list[JournalEntry]:
        """Entries for a specific asset, ordered by logged_at."""
        return [e for e in self.get_entries() if e.asset_id == asset_id]

    def get_unresolved(self) -> list[JournalEntry]:
        """Entries with outcome == PENDING."""
        return [e for e in self.get_entries() if e.outcome == Outcome.PENDING]

    # ------------------------------------------------------------------ #
    # Learning                                                             #
    # ------------------------------------------------------------------ #

    def learning_summary(self) -> LearningReport:
        """
        Compute calibration metrics across all resolved entries.

        Only entries with CORRECT or INCORRECT outcomes contribute to accuracy.
        Entries with PARTIAL or EXPIRED are counted in n_resolved but excluded
        from accuracy and Brier score.
        """
        all_entries = self.get_entries()
        resolved = [e for e in all_entries if e.outcome != Outcome.PENDING]
        scorable = [e for e in resolved if e.outcome in (Outcome.CORRECT, Outcome.INCORRECT)]

        n_correct = sum(1 for e in scorable if e.outcome == Outcome.CORRECT)

        accuracy: Optional[float] = None
        avg_confidence: Optional[float] = None
        calibration_gap: Optional[float] = None
        brier_score: Optional[float] = None

        if scorable:
            accuracy = n_correct / len(scorable)
            avg_confidence = sum(e.confidence for e in scorable) / len(scorable)
            calibration_gap = avg_confidence - accuracy
            brier_score = round(
                sum(
                    (e.confidence - (1.0 if e.outcome == Outcome.CORRECT else 0.0)) ** 2
                    for e in scorable
                ) / len(scorable),
                6,
            )

        return LearningReport(
            n_total=len(all_entries),
            n_resolved=len(resolved),
            n_correct=n_correct,
            accuracy=accuracy,
            avg_confidence=avg_confidence,
            calibration_gap=calibration_gap,
            brier_score=brier_score,
        )
