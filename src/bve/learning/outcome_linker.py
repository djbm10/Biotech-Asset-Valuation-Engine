"""Links realized market outcomes back to prediction records.

Provides two APIs:

1. New Step 12 API: OutcomeLinker(log: PredictionLog) with link_price_return(),
   link_event(), unresolved_count(), all_outcomes().

2. Legacy API: OutcomeLinker() with link(decision, ...), link_batch() methods
   that work with DecisionRecord / OutcomeRecord from persistence layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional

from bve.learning.prediction_log import (
    PredictionLog,
    DecisionPredictionOutcome as _NewOutcome,
)


class OutcomeSource(str, Enum):
    PRICE_RETURN = "price_return"       # derived from stock price move
    TRIAL_RESULT = "trial_result"       # explicit trial success/failure event
    FDA_DECISION = "fda_decision"       # FDA approval / CRL
    MANUAL = "manual"                   # analyst manually resolved


@dataclass(frozen=True)
class OutcomeRecord:
    """New Step 12 outcome record."""
    outcome_id: str            # UUID
    prediction_id: str
    asset_id: str
    source: OutcomeSource
    realized_return: float     # actual stock return
    outcome: _NewOutcome
    event_description: str
    resolved_at: datetime


class OutcomeLinker:
    """
    Links outcome events to pending predictions and resolves them in PredictionLog.

    Supports two modes:
    - New API: OutcomeLinker(log) — requires PredictionLog, uses new step12 tables
    - Legacy API: OutcomeLinker() — no-arg constructor, uses link(DecisionRecord, ...) method
    """

    def __init__(self, log: Optional[PredictionLog] = None) -> None:
        self._log = log
        self._outcomes: list[OutcomeRecord] = []

    # ------------------------------------------------------------------
    # New Step 12 API
    # ------------------------------------------------------------------

    def link_price_return(
        self,
        asset_id: str,
        realized_return: float,
        resolved_at: datetime,
        threshold: float = 0.10,   # |return| >= threshold → directional call
    ) -> list[OutcomeRecord]:
        """
        For all PENDING predictions for asset_id:
        - If realized_return >= threshold AND predicted_return > 0 → CORRECT
        - If realized_return <= -threshold AND predicted_return < 0 → CORRECT
        - If signs disagree beyond threshold → INCORRECT
        - Otherwise → PARTIAL
        Resolves each in the log. Returns list of OutcomeRecords created.
        """
        if self._log is None:
            raise RuntimeError("OutcomeLinker requires a PredictionLog for link_price_return()")

        pending = self._log.pending(asset_id=asset_id)
        created: list[OutcomeRecord] = []

        for record in pending:
            if realized_return >= threshold and record.predicted_return > 0:
                outcome = _NewOutcome.CORRECT
            elif realized_return <= -threshold and record.predicted_return < 0:
                outcome = _NewOutcome.CORRECT
            elif (
                (realized_return >= threshold and record.predicted_return < 0)
                or (realized_return <= -threshold and record.predicted_return > 0)
            ):
                outcome = _NewOutcome.INCORRECT
            else:
                outcome = _NewOutcome.PARTIAL

            self._log.resolve(
                prediction_id=record.prediction_id,
                outcome=outcome,
                realized_return=realized_return,
                resolved_at=resolved_at,
            )

            outcome_record = OutcomeRecord(
                outcome_id=str(uuid.uuid4()),
                prediction_id=record.prediction_id,
                asset_id=asset_id,
                source=OutcomeSource.PRICE_RETURN,
                realized_return=realized_return,
                outcome=outcome,
                event_description=f"Price return: {realized_return:.2%}",
                resolved_at=resolved_at,
            )
            self._outcomes.append(outcome_record)
            created.append(outcome_record)

        return created

    def link_event(
        self,
        asset_id: str,
        event_type: str,          # "trial_success", "trial_failure", "fda_approval", "crl"
        realized_return: float,
        event_description: str,
        resolved_at: datetime,
    ) -> list[OutcomeRecord]:
        """
        Maps event_type to PredictionOutcome:
        - "trial_success" / "fda_approval": CORRECT if predicted_return > 0 else INCORRECT
        - "trial_failure" / "crl": CORRECT if predicted_return < 0 else INCORRECT
        Resolves all pending predictions for asset_id.
        """
        if self._log is None:
            raise RuntimeError("OutcomeLinker requires a PredictionLog for link_event()")

        pending = self._log.pending(asset_id=asset_id)
        created: list[OutcomeRecord] = []

        if event_type in ("trial_success", "trial_failure"):
            source = OutcomeSource.TRIAL_RESULT
        elif event_type in ("fda_approval", "crl"):
            source = OutcomeSource.FDA_DECISION
        else:
            source = OutcomeSource.MANUAL

        for record in pending:
            if event_type in ("trial_success", "fda_approval"):
                outcome = (
                    _NewOutcome.CORRECT
                    if record.predicted_return > 0
                    else _NewOutcome.INCORRECT
                )
            elif event_type in ("trial_failure", "crl"):
                outcome = (
                    _NewOutcome.CORRECT
                    if record.predicted_return < 0
                    else _NewOutcome.INCORRECT
                )
            else:
                outcome = _NewOutcome.PARTIAL

            self._log.resolve(
                prediction_id=record.prediction_id,
                outcome=outcome,
                realized_return=realized_return,
                resolved_at=resolved_at,
            )

            outcome_record = OutcomeRecord(
                outcome_id=str(uuid.uuid4()),
                prediction_id=record.prediction_id,
                asset_id=asset_id,
                source=source,
                realized_return=realized_return,
                outcome=outcome,
                event_description=event_description,
                resolved_at=resolved_at,
            )
            self._outcomes.append(outcome_record)
            created.append(outcome_record)

        return created

    def unresolved_count(self, asset_id: str | None = None) -> int:
        """Return count of pending predictions."""
        if self._log is None:
            return 0
        return len(self._log.pending(asset_id=asset_id))

    def all_outcomes(self) -> list[OutcomeRecord]:
        """Return all outcome records created by this linker."""
        return list(self._outcomes)

    # ------------------------------------------------------------------
    # Legacy API (backward compatibility with test_learning_engine.py)
    # ------------------------------------------------------------------

    def link(
        self,
        decision,  # DecisionRecord from persistence layer
        outcome_date: date,
        return_realized_pct: float,
        *,
        catalyst_triggered: bool = False,
        catalyst_description: Optional[str] = None,
        thesis_confirmed: Optional[bool] = None,
    ):
        """Build and return a legacy OutcomeRecord (persistence layer) with computed attribution."""
        from bve.persistence.gap_fill_store import OutcomeRecord as PersistenceOutcomeRecord

        attribution = self._classify(
            return_realized_pct=return_realized_pct,
            catalyst_triggered=catalyst_triggered,
            thesis_confirmed=thesis_confirmed,
        )
        decision_date = (
            decision.decision_date.date()
            if hasattr(decision.decision_date, "date")
            else decision.decision_date
        )
        return PersistenceOutcomeRecord(
            decision_id=decision.decision_id,
            asset_id=decision.asset_id,
            ticker=decision.ticker,
            decision_date=decision_date,
            outcome_date=outcome_date,
            return_realized_pct=return_realized_pct,
            catalyst_triggered=catalyst_triggered,
            catalyst_description=catalyst_description,
            thesis_confirmed=thesis_confirmed,
            attribution=attribution,
        )

    def link_batch(
        self,
        decisions: list,
        returns_by_decision_id: dict[str, float],
        outcome_date: date,
    ) -> list:
        """Link a batch using legacy interface."""
        results = []
        for decision in decisions:
            if decision.decision_id not in returns_by_decision_id:
                continue
            return_pct = returns_by_decision_id[decision.decision_id]
            outcome = self.link(decision, outcome_date, return_pct)
            results.append(outcome)
        return results

    @staticmethod
    def _classify(
        return_realized_pct: float,
        catalyst_triggered: bool,
        thesis_confirmed: Optional[bool],
    ) -> str:
        positive_return = return_realized_pct > 0

        if catalyst_triggered:
            if thesis_confirmed is False:
                if positive_return:
                    return "pos_error"
                else:
                    return "timing_error"
            else:
                if positive_return:
                    return "confirmed_thesis"
                else:
                    return "timing_error"

        if positive_return:
            return "market_drift"
        else:
            return "thesis_error"
