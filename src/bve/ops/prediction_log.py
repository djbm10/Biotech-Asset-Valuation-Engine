"""Prediction log: persistent record of M&A scores, catalyst signals, and mispricing outputs.

Records are written at score time and can be resolved later (with outcome) to build
a track record for calibration and credibility purposes.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_DEFAULT_DB = Path(__file__).parent.parent.parent.parent / "outputs" / "intelligence" / "prediction_log.db"

_VALID_LOG_TYPES = {"ma_score", "catalyst_signal", "mispricing"}
_VALID_OUTCOMES = {"correct", "incorrect", "partial", "pending", "wrong"}


@dataclass
class PredictionLogEntry:
    """A prediction to be logged. Pass to PredictionLog.log()."""

    log_type: str
    asset_id: str
    score: float
    ticker: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None
    # logged_at is set by the store on insert; may be pre-set for testing
    logged_at: Optional[str] = None


class PredictionLog:
    """SQLite-backed store for prediction log entries.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file. Created on first use.
    """

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        path = Path(db_path) if db_path is not None else _DEFAULT_DB
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS prediction_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at    TEXT    NOT NULL,
                log_type     TEXT    NOT NULL,
                asset_id     TEXT    NOT NULL,
                ticker       TEXT,
                score        REAL    NOT NULL,
                confidence   REAL,
                notes        TEXT,
                resolved_at  TEXT,
                outcome      TEXT,
                outcome_notes TEXT
            )
        """)
        self._conn.commit()

    def log(self, entry: PredictionLogEntry) -> int:
        """Insert a new prediction log entry.

        Parameters
        ----------
        entry:
            PredictionLogEntry to persist.

        Returns
        -------
        int
            The ``id`` of the newly inserted row.
        """
        if entry.log_type not in _VALID_LOG_TYPES:
            raise ValueError(
                f"log_type must be one of {_VALID_LOG_TYPES}, got {entry.log_type!r}"
            )
        logged_at = entry.logged_at or datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO prediction_log
                (logged_at, log_type, asset_id, ticker, score, confidence, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (logged_at, entry.log_type, entry.asset_id, entry.ticker,
             entry.score, entry.confidence, entry.notes),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def resolve(
        self,
        entry_id: int,
        outcome: str,
        *,
        outcome_notes: Optional[str] = None,
    ) -> None:
        """Mark a prediction as resolved with an outcome.

        Parameters
        ----------
        entry_id:
            The ``id`` of the log entry to resolve.
        outcome:
            One of "correct", "incorrect", "partial", "pending", "wrong".
        outcome_notes:
            Free-text explanation of the outcome.
        """
        if outcome not in _VALID_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {_VALID_OUTCOMES}, got {outcome!r}"
            )
        resolved_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE prediction_log
            SET outcome = ?, outcome_notes = ?, resolved_at = ?
            WHERE id = ?
            """,
            (outcome, outcome_notes, resolved_at, entry_id),
        )
        self._conn.commit()

    def unresolved(self, log_type: Optional[str] = None) -> list[dict]:
        """Return all unresolved entries (outcome IS NULL) as dicts.

        Parameters
        ----------
        log_type:
            Optional filter by log_type.
        """
        if log_type is not None:
            rows = self._conn.execute(
                "SELECT * FROM prediction_log WHERE outcome IS NULL AND log_type = ? ORDER BY logged_at",
                (log_type,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM prediction_log WHERE outcome IS NULL ORDER BY logged_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict:
        """Return summary statistics over all entries."""
        all_rows = self._conn.execute(
            "SELECT * FROM prediction_log"
        ).fetchall()
        if not all_rows:
            return {
                "total": 0,
                "resolved": 0,
                "unresolved": 0,
                "correct": 0,
                "accuracy": None,
                "by_type": {},
            }

        total = len(all_rows)
        resolved_rows = [r for r in all_rows if r["outcome"] is not None]
        unresolved_rows = [r for r in all_rows if r["outcome"] is None]
        n_correct = sum(1 for r in resolved_rows if r["outcome"] == "correct")
        n_resolved = len(resolved_rows)
        accuracy = n_correct / n_resolved if n_resolved > 0 else None

        by_type: dict[str, int] = {}
        for r in all_rows:
            lt = r["log_type"]
            by_type[lt] = by_type.get(lt, 0) + 1

        return {
            "total": total,
            "resolved": n_resolved,
            "unresolved": len(unresolved_rows),
            "correct": n_correct,
            "accuracy": accuracy,
            "by_type": by_type,
        }

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def log_ma_score(
    log: PredictionLog,
    asset_id: str,
    score: float,
    *,
    ticker: Optional[str] = None,
    p_takeout: Optional[float] = None,
    acquirer: Optional[str] = None,
    confidence: Optional[float] = None,
    notes: Optional[str] = None,
) -> int:
    """Log an M&A probability score prediction."""
    parts: list[str] = []
    if notes:
        parts.append(notes)
    if acquirer:
        parts.append(f"best acquirer: {acquirer}")
    if p_takeout is not None:
        parts.append(f"p_takeout: {p_takeout:.2f}")
    note_str = "; ".join(parts) if parts else None
    return log.log(PredictionLogEntry(
        log_type="ma_score",
        asset_id=asset_id,
        score=score,
        ticker=ticker,
        confidence=confidence,
        notes=note_str,
    ))


def log_mispricing(
    log: PredictionLog,
    asset_id: str,
    *,
    ticker: Optional[str] = None,
    model_pos: Optional[float] = None,
    implied_pos: Optional[float] = None,
    pos_gap: Optional[float] = None,
    direction: Optional[str] = None,
    confidence: Optional[float] = None,
    notes: Optional[str] = None,
) -> int:
    """Log a valuation mispricing signal."""
    parts: list[str] = []
    if notes:
        parts.append(notes)
    if model_pos is not None:
        parts.append(f"model_pos: {model_pos}")
    if implied_pos is not None:
        parts.append(f"implied_pos: {implied_pos}")
    if pos_gap is not None:
        parts.append(f"pos_gap: {pos_gap:+.2f}")
    if direction:
        parts.append(direction)
    note_str = "; ".join(parts) if parts else None
    score = pos_gap if pos_gap is not None else 0.0
    return log.log(PredictionLogEntry(
        log_type="mispricing",
        asset_id=asset_id,
        score=score,
        ticker=ticker,
        confidence=confidence,
        notes=note_str,
    ))
