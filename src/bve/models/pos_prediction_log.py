"""
Block 23 — POS Prediction Log

Persistent SQLite store for POS predictions and outcome resolution.
Supports calibration feedback loop via log_pos_prediction / resolve_pos_prediction / get_pos_predictions.

No-lookahead guard:
  - get_pos_predictions(as_of_date=...) adds AND date(prediction_date) <= ?
  - resolve_pos_prediction() rejects outcome_date < prediction_date
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Record type
# ---------------------------------------------------------------------------

@dataclass
class POSPredictionRecord:
    record_id: str
    trial_id: str
    ticker: str
    phase: str
    therapeutic_area: str
    predicted_pos: float
    confidence_flags: list[str]
    model_version: str
    adjuster_snapshot: dict
    prediction_date: str       # ISO date string "YYYY-MM-DD"
    outcome: Optional[str]     # None | "success" | "failure"
    outcome_date: Optional[str]
    resolved: bool


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS pos_predictions (
    record_id           TEXT PRIMARY KEY,
    trial_id            TEXT NOT NULL,
    ticker              TEXT NOT NULL,
    phase               TEXT NOT NULL,
    therapeutic_area    TEXT NOT NULL,
    predicted_pos       REAL NOT NULL,
    confidence_flags    TEXT NOT NULL,   -- JSON list
    model_version       TEXT NOT NULL,
    adjuster_snapshot   TEXT NOT NULL,   -- JSON dict
    prediction_date     TEXT NOT NULL,
    outcome             TEXT,
    outcome_date        TEXT,
    resolved            INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect(store_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(store_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_DDL)
    conn.commit()
    return conn


def _row_to_record(row: sqlite3.Row) -> POSPredictionRecord:
    return POSPredictionRecord(
        record_id=row["record_id"],
        trial_id=row["trial_id"],
        ticker=row["ticker"],
        phase=row["phase"],
        therapeutic_area=row["therapeutic_area"],
        predicted_pos=row["predicted_pos"],
        confidence_flags=json.loads(row["confidence_flags"]),
        model_version=row["model_version"],
        adjuster_snapshot=json.loads(row["adjuster_snapshot"]),
        prediction_date=row["prediction_date"],
        outcome=row["outcome"],
        outcome_date=row["outcome_date"],
        resolved=bool(row["resolved"]),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_pos_prediction(
    store_path: str | Path,
    *,
    trial_id: str,
    ticker: str,
    phase: str,
    therapeutic_area: str,
    predicted_pos: float,
    confidence_flags: list[str],
    model_version: str = "unknown",
    adjuster_snapshot: dict,
    prediction_date: str,
) -> str:
    """Persist a POS prediction record and return its record_id."""
    import datetime

    record_id = str(uuid.uuid4())
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with _connect(store_path) as conn:
        conn.execute(
            """
            INSERT INTO pos_predictions (
                record_id, trial_id, ticker, phase, therapeutic_area,
                predicted_pos, confidence_flags, model_version,
                adjuster_snapshot, prediction_date, outcome, outcome_date,
                resolved, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?)
            """,
            (
                record_id, trial_id, ticker, phase, therapeutic_area,
                predicted_pos,
                json.dumps(confidence_flags),
                model_version,
                json.dumps(adjuster_snapshot),
                prediction_date,
                created_at,
            ),
        )
        conn.commit()

    return record_id


def resolve_pos_prediction(
    store_path: str | Path,
    *,
    record_id: str,
    outcome: str,
    outcome_date: str,
) -> None:
    """Mark a prediction resolved with outcome and outcome_date.

    Raises ValueError if:
    - record_id does not exist
    - outcome_date is strictly before prediction_date
    """
    with _connect(store_path) as conn:
        row = conn.execute(
            "SELECT prediction_date FROM pos_predictions WHERE record_id = ?",
            (record_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"No record found with record_id={record_id!r}")

        prediction_date = row["prediction_date"]
        if outcome_date < prediction_date:
            raise ValueError(
                f"outcome_date ({outcome_date!r}) is before prediction_date ({prediction_date!r})"
            )

        conn.execute(
            """
            UPDATE pos_predictions
            SET outcome = ?, outcome_date = ?, resolved = 1
            WHERE record_id = ?
            """,
            (outcome, outcome_date, record_id),
        )
        conn.commit()


def get_pos_predictions(
    store_path: str | Path,
    *,
    ticker: Optional[str] = None,
    trial_id: Optional[str] = None,
    phase: Optional[str] = None,
    resolved_only: bool = False,
    as_of_date: Optional[str] = None,
) -> list[POSPredictionRecord]:
    """Query prediction records with optional filters.

    Parameters
    ----------
    ticker:
        Filter to a specific ticker symbol.
    trial_id:
        Filter to a specific trial ID.
    phase:
        Filter to a specific phase string (e.g. "phase_2").
    resolved_only:
        If True, return only resolved records.
    as_of_date:
        ISO date string; exclude records with prediction_date > as_of_date.
        Enforces no-lookahead guarantee for time-frozen queries.
    """
    clauses: list[str] = []
    params: list = []

    if ticker is not None:
        clauses.append("ticker = ?")
        params.append(ticker)
    if trial_id is not None:
        clauses.append("trial_id = ?")
        params.append(trial_id)
    if phase is not None:
        clauses.append("phase = ?")
        params.append(phase)
    if resolved_only:
        clauses.append("resolved = 1")
    if as_of_date is not None:
        clauses.append("date(prediction_date) <= date(?)")
        params.append(as_of_date)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM pos_predictions {where} ORDER BY prediction_date ASC"

    with _connect(store_path) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [_row_to_record(r) for r in rows]
