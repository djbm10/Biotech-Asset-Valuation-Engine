"""SQLite-backed log of full prediction state at decision time.

Exports both a legacy Pydantic-based API and a new Step 12 dataclass API.

New Step 12 API uses:
- DecisionPredictionOutcome (Enum): PENDING, CORRECT, INCORRECT, PARTIAL
- DecisionPredictionRecord (frozen dataclass): new fields for Step 12

Legacy API (backward compat) uses:
- PredictionOutcome (Pydantic model): outcome result
- PredictionRecord (Pydantic model): prediction record
- PredictionLog methods: log_prediction(), log_outcome(), get_predictions(),
  get_outcomes(), compute_accuracy(), matched_pairs()
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel


# ===========================================================================
# New Step 12 API — DecisionPredictionOutcome + DecisionPredictionRecord
# ===========================================================================


class DecisionPredictionOutcome(str, Enum):
    """Outcome enum for Step 12 learning loop."""
    PENDING = "pending"       # outcome not yet known
    CORRECT = "correct"       # prediction directionally correct
    INCORRECT = "incorrect"   # prediction wrong
    PARTIAL = "partial"       # mixed result


@dataclass(frozen=True)
class DecisionPredictionRecord:
    """New-style prediction record for Step 12 calibration loop."""
    prediction_id: str        # UUID
    asset_id: str
    ticker: str
    predicted_pos: float      # model PoS at decision time (0.0-1.0)
    predicted_return: float   # expected return (e.g. 0.35)
    asymmetry_score: float
    thesis_strength: str
    action_taken: str         # TradeAction value
    domain_scores: dict[str, float]   # domain -> score snapshot
    predicted_at: datetime    # UTC
    outcome: DecisionPredictionOutcome = DecisionPredictionOutcome.PENDING
    realized_return: float | None = None
    resolved_at: datetime | None = None


# ===========================================================================
# Legacy API — original Pydantic models (backward compat)
# ===========================================================================


class PredictionRecord(BaseModel):
    """A single model prediction, logged before catalyst resolution (legacy API)."""

    prediction_id: str
    asset_id: str
    predicted_on: date
    catalyst_type: str
    expected_catalyst_date: Optional[date] = None
    model_pos: float
    market_implied_pos: Optional[float] = None
    asymmetry_score: Optional[float] = None
    scenario_ev_pct: Optional[float] = None
    notes: str = ""


class PredictionOutcome(BaseModel):
    """Resolved outcome for a prior prediction (legacy API)."""

    prediction_id: str
    asset_id: str
    outcome_date: date
    actual_result: str  # "success" | "failure" | "partial" | "withdrawn"
    price_change_pct: Optional[float] = None
    notes: str = ""


class PredictionAccuracyRecord(BaseModel):
    """Aggregated accuracy statistics, optionally filtered to one asset."""

    asset_id: str
    n_predictions: int
    n_successes_predicted: int
    n_correct: int
    brier_score: Optional[float] = None
    calibration_error: Optional[float] = None


# ===========================================================================
# Database schema
# ===========================================================================


_NEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS step12_predictions (
    prediction_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    predicted_pos REAL NOT NULL,
    predicted_return REAL NOT NULL,
    asymmetry_score REAL NOT NULL,
    thesis_strength TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    domain_scores TEXT NOT NULL,
    predicted_at TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'pending',
    realized_return REAL,
    resolved_at TEXT
);
"""

_LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    predicted_on TEXT NOT NULL,
    catalyst_type TEXT NOT NULL,
    expected_catalyst_date TEXT,
    model_pos REAL NOT NULL,
    market_implied_pos REAL,
    asymmetry_score REAL,
    scenario_ev_pct REAL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS outcomes (
    prediction_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    outcome_date TEXT NOT NULL,
    actual_result TEXT NOT NULL,
    price_change_pct REAL,
    notes TEXT NOT NULL DEFAULT ''
);
"""


# ===========================================================================
# PredictionLog — unified class supporting both APIs
# ===========================================================================


class PredictionLog:
    """SQLite-backed prediction log. Use ':memory:' for tests.

    Supports both the new Step 12 API (via log(), get(), resolve(), etc.)
    and the legacy pre-Step12 API (via log_prediction(), log_outcome(), etc.).
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """Create tables if not exists."""
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_NEW_SCHEMA + _LEGACY_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # New Step 12 API
    # ------------------------------------------------------------------

    def log(self, record: DecisionPredictionRecord) -> str:
        """Insert new-style record, return prediction_id."""
        self._conn.execute(
            """
            INSERT INTO step12_predictions
              (prediction_id, asset_id, ticker, predicted_pos, predicted_return,
               asymmetry_score, thesis_strength, action_taken, domain_scores,
               predicted_at, outcome, realized_return, resolved_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record.prediction_id,
                record.asset_id,
                record.ticker,
                record.predicted_pos,
                record.predicted_return,
                record.asymmetry_score,
                record.thesis_strength,
                record.action_taken,
                json.dumps(record.domain_scores),
                record.predicted_at.isoformat(),
                record.outcome.value,
                record.realized_return,
                record.resolved_at.isoformat() if record.resolved_at else None,
            ),
        )
        self._conn.commit()
        return record.prediction_id

    def get(self, prediction_id: str) -> DecisionPredictionRecord | None:
        """Retrieve new-style record by prediction_id."""
        row = self._conn.execute(
            "SELECT * FROM step12_predictions WHERE prediction_id = ?",
            (prediction_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_new_record(row)

    def resolve(
        self,
        prediction_id: str,
        outcome: DecisionPredictionOutcome,
        realized_return: float,
        resolved_at: datetime | None = None,
    ) -> None:
        """Update outcome + realized_return + resolved_at."""
        if resolved_at is None:
            resolved_at = datetime.now(timezone.utc)
        self._conn.execute(
            """
            UPDATE step12_predictions
            SET outcome = ?, realized_return = ?, resolved_at = ?
            WHERE prediction_id = ?
            """,
            (
                outcome.value,
                realized_return,
                resolved_at.isoformat(),
                prediction_id,
            ),
        )
        self._conn.commit()

    def pending(self, asset_id: str | None = None) -> list[DecisionPredictionRecord]:
        """Return new-style records with PENDING outcome."""
        if asset_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM step12_predictions WHERE outcome = 'pending' AND asset_id = ?",
                (asset_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM step12_predictions WHERE outcome = 'pending'",
            ).fetchall()
        return [self._row_to_new_record(r) for r in rows]

    def resolved(self, asset_id: str | None = None) -> list[DecisionPredictionRecord]:
        """Return new-style records that have been resolved (not PENDING)."""
        if asset_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM step12_predictions WHERE outcome != 'pending' AND asset_id = ?",
                (asset_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM step12_predictions WHERE outcome != 'pending'",
            ).fetchall()
        return [self._row_to_new_record(r) for r in rows]

    def all(self) -> list[DecisionPredictionRecord]:
        """Return all new-style records."""
        rows = self._conn.execute("SELECT * FROM step12_predictions").fetchall()
        return [self._row_to_new_record(r) for r in rows]

    def count(self) -> int:
        """Return total number of new-style records."""
        row = self._conn.execute("SELECT COUNT(*) FROM step12_predictions").fetchone()
        return row[0]

    def matched_pairs(
        self, asset_id: str | None = None
    ) -> list:
        """
        New API: Returns list of (predicted_pos, binary_outcome) for resolved new-style records.
        binary_outcome: 1.0 if CORRECT, 0.0 if INCORRECT, 0.5 if PARTIAL.

        Legacy API (when called with asset_id on a log that has legacy data):
        Returns list of (PredictionRecord, PredictionOutcome) tuples.
        """
        # If legacy data exists, return legacy pairs (old behavior)
        if self._has_legacy_data():
            return self._legacy_matched_pairs(asset_id=asset_id)

        # New API: return (predicted_pos, binary_outcome) floats
        resolved_records = self.resolved(asset_id=asset_id)
        pairs: list[tuple[float, float]] = []
        for record in resolved_records:
            if record.outcome == DecisionPredictionOutcome.CORRECT:
                binary = 1.0
            elif record.outcome == DecisionPredictionOutcome.INCORRECT:
                binary = 0.0
            elif record.outcome == DecisionPredictionOutcome.PARTIAL:
                binary = 0.5
            else:
                continue
            pairs.append((record.predicted_pos, binary))
        return pairs

    # ------------------------------------------------------------------
    # Legacy API (backward compatibility)
    # ------------------------------------------------------------------

    def log_prediction(self, record: PredictionRecord) -> None:
        """Append a legacy prediction record."""
        self._conn.execute(
            """
            INSERT INTO predictions
              (prediction_id, asset_id, predicted_on, catalyst_type,
               expected_catalyst_date, model_pos, market_implied_pos,
               asymmetry_score, scenario_ev_pct, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record.prediction_id,
                record.asset_id,
                record.predicted_on.isoformat(),
                record.catalyst_type,
                record.expected_catalyst_date.isoformat()
                if record.expected_catalyst_date
                else None,
                record.model_pos,
                record.market_implied_pos,
                record.asymmetry_score,
                record.scenario_ev_pct,
                record.notes,
            ),
        )
        self._conn.commit()

    def log_outcome(self, outcome: PredictionOutcome) -> None:
        """Append or replace the legacy outcome for a prediction."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO outcomes
              (prediction_id, asset_id, outcome_date, actual_result,
               price_change_pct, notes)
            VALUES (?,?,?,?,?,?)
            """,
            (
                outcome.prediction_id,
                outcome.asset_id,
                outcome.outcome_date.isoformat(),
                outcome.actual_result,
                outcome.price_change_pct,
                outcome.notes,
            ),
        )
        self._conn.commit()

    def get_predictions(
        self, asset_id: Optional[str] = None
    ) -> list[PredictionRecord]:
        """Return all legacy predictions, optionally filtered by asset_id."""
        if asset_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM predictions WHERE asset_id = ?", (asset_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM predictions").fetchall()
        return [self._row_to_legacy_prediction(r) for r in rows]

    def get_outcomes(
        self, asset_id: Optional[str] = None
    ) -> list[PredictionOutcome]:
        """Return all legacy outcomes, optionally filtered by asset_id."""
        if asset_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM outcomes WHERE asset_id = ?", (asset_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM outcomes").fetchall()
        return [self._row_to_legacy_outcome(r) for r in rows]

    def compute_accuracy(
        self, asset_id: Optional[str] = None
    ) -> PredictionAccuracyRecord:
        """Compute accuracy statistics over matched legacy pairs."""
        scope_id = asset_id or "__all__"
        all_predictions = self.get_predictions(asset_id)
        pairs = self._legacy_matched_pairs(asset_id=asset_id)

        if not pairs:
            return PredictionAccuracyRecord(
                asset_id=scope_id,
                n_predictions=len(all_predictions),
                n_successes_predicted=0,
                n_correct=0,
                brier_score=None,
                calibration_error=None,
            )

        n_correct = 0
        n_successes_predicted = 0
        brier_sum = 0.0
        calibration_sum = 0.0

        for pred, outcome in pairs:
            actual_binary = 1 if outcome.actual_result == "success" else 0
            predicted_success = pred.model_pos >= 0.5

            if predicted_success and outcome.actual_result == "success":
                n_successes_predicted += 1

            model_predicted_success = pred.model_pos >= 0.5
            if model_predicted_success == (outcome.actual_result == "success"):
                n_correct += 1

            brier_sum += (pred.model_pos - actual_binary) ** 2
            calibration_sum += abs(pred.model_pos - actual_binary)

        n = len(pairs)
        return PredictionAccuracyRecord(
            asset_id=scope_id,
            n_predictions=len(all_predictions),
            n_successes_predicted=n_successes_predicted,
            n_correct=n_correct,
            brier_score=brier_sum / n,
            calibration_error=calibration_sum / n,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _has_legacy_data(self) -> bool:
        """Check if legacy predictions table has any data."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM predictions"
        ).fetchone()
        return row[0] > 0

    def _legacy_matched_pairs(
        self, asset_id: Optional[str] = None
    ) -> list[tuple[PredictionRecord, PredictionOutcome]]:
        """Return (legacy_prediction, legacy_outcome) pairs."""
        predictions = {p.prediction_id: p for p in self.get_predictions(asset_id)}
        outcomes = {o.prediction_id: o for o in self.get_outcomes(asset_id)}
        shared_ids = predictions.keys() & outcomes.keys()
        return [(predictions[pid], outcomes[pid]) for pid in sorted(shared_ids)]

    @staticmethod
    def _row_to_new_record(row: tuple) -> DecisionPredictionRecord:
        (
            prediction_id,
            asset_id,
            ticker,
            predicted_pos,
            predicted_return,
            asymmetry_score,
            thesis_strength,
            action_taken,
            domain_scores_json,
            predicted_at_str,
            outcome_str,
            realized_return,
            resolved_at_str,
        ) = row

        predicted_at = datetime.fromisoformat(predicted_at_str)
        resolved_at = datetime.fromisoformat(resolved_at_str) if resolved_at_str else None
        domain_scores = json.loads(domain_scores_json)
        outcome = DecisionPredictionOutcome(outcome_str)

        return DecisionPredictionRecord(
            prediction_id=prediction_id,
            asset_id=asset_id,
            ticker=ticker,
            predicted_pos=predicted_pos,
            predicted_return=predicted_return,
            asymmetry_score=asymmetry_score,
            thesis_strength=thesis_strength,
            action_taken=action_taken,
            domain_scores=domain_scores,
            predicted_at=predicted_at,
            outcome=outcome,
            realized_return=realized_return,
            resolved_at=resolved_at,
        )

    @staticmethod
    def _row_to_legacy_prediction(row: tuple) -> PredictionRecord:
        (
            prediction_id,
            asset_id,
            predicted_on,
            catalyst_type,
            expected_catalyst_date,
            model_pos,
            market_implied_pos,
            asymmetry_score,
            scenario_ev_pct,
            notes,
        ) = row
        return PredictionRecord(
            prediction_id=prediction_id,
            asset_id=asset_id,
            predicted_on=date.fromisoformat(predicted_on),
            catalyst_type=catalyst_type,
            expected_catalyst_date=date.fromisoformat(expected_catalyst_date)
            if expected_catalyst_date
            else None,
            model_pos=model_pos,
            market_implied_pos=market_implied_pos,
            asymmetry_score=asymmetry_score,
            scenario_ev_pct=scenario_ev_pct,
            notes=notes or "",
        )

    @staticmethod
    def _row_to_legacy_outcome(row: tuple) -> PredictionOutcome:
        (
            prediction_id,
            asset_id,
            outcome_date,
            actual_result,
            price_change_pct,
            notes,
        ) = row
        return PredictionOutcome(
            prediction_id=prediction_id,
            asset_id=asset_id,
            outcome_date=date.fromisoformat(outcome_date),
            actual_result=actual_result,
            price_change_pct=price_change_pct,
            notes=notes or "",
        )
