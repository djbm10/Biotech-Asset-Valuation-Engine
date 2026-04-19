"""Immutable append-only log of model predictions for later comparison against outcomes."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class PredictionRecord(BaseModel):
    """A single model prediction, logged before catalyst resolution."""

    prediction_id: str  # UUID or hash
    asset_id: str
    predicted_on: date
    catalyst_type: str  # "phase3_readout" | "pdufa" | "interim" | etc.
    expected_catalyst_date: Optional[date] = None
    model_pos: float  # P(success) from our model
    market_implied_pos: Optional[float] = None
    asymmetry_score: Optional[float] = None
    scenario_ev_pct: Optional[float] = None  # expected return from scenario tree
    notes: str = ""


class PredictionOutcome(BaseModel):
    """Resolved outcome for a prior prediction."""

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
    n_successes_predicted: int  # model_pos >= 0.5 and actual == "success"
    n_correct: int
    brier_score: Optional[float] = None
    calibration_error: Optional[float] = None  # mean |predicted - actual|


class PredictionLog:
    """SQLite-backed prediction log.

    Default DB lives at ``outputs/learning/prediction_log.db``.
    Pass ``db_path=":memory:"`` for ephemeral in-process use (tests).
    """

    _SCHEMA = """
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

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            default = Path("outputs/learning/prediction_log.db")
            default.parent.mkdir(parents=True, exist_ok=True)
            db_path = str(default)
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def log_prediction(self, record: PredictionRecord) -> None:
        """Append a prediction record; raises if prediction_id already exists."""
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
        """Append or replace the outcome for a prediction."""
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

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_predictions(
        self, asset_id: Optional[str] = None
    ) -> list[PredictionRecord]:
        """Return all predictions, optionally filtered by asset_id."""
        if asset_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM predictions WHERE asset_id = ?", (asset_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM predictions").fetchall()
        return [self._row_to_prediction(r) for r in rows]

    def get_outcomes(
        self, asset_id: Optional[str] = None
    ) -> list[PredictionOutcome]:
        """Return all outcomes, optionally filtered by asset_id."""
        if asset_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM outcomes WHERE asset_id = ?", (asset_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM outcomes").fetchall()
        return [self._row_to_outcome(r) for r in rows]

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def matched_pairs(
        self, asset_id: Optional[str] = None
    ) -> list[tuple[PredictionRecord, PredictionOutcome]]:
        """Return (prediction, outcome) pairs where both records exist."""
        predictions = {p.prediction_id: p for p in self.get_predictions(asset_id)}
        outcomes = {o.prediction_id: o for o in self.get_outcomes(asset_id)}
        shared_ids = predictions.keys() & outcomes.keys()
        return [(predictions[pid], outcomes[pid]) for pid in sorted(shared_ids)]

    def compute_accuracy(
        self, asset_id: Optional[str] = None
    ) -> PredictionAccuracyRecord:
        """Compute accuracy statistics over matched pairs.

        Brier score = mean((model_pos - actual_binary)²)
        where actual_binary: success=1, all other results=0.

        calibration_error = mean(|model_pos - actual_binary|)
        """
        scope_id = asset_id or "__all__"
        all_predictions = self.get_predictions(asset_id)
        pairs = self.matched_pairs(asset_id)

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

            # n_correct: model prediction direction matches outcome
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
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_prediction(row: tuple) -> PredictionRecord:
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
    def _row_to_outcome(row: tuple) -> PredictionOutcome:
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
