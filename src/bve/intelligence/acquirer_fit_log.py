"""
Block 5A — Acquirer-Fit Prediction Log.

Persists each acquirer-fit screening run to SQLite so that, when deals close,
predictions can be resolved and the model can be graded against actual outcomes.

No-lookahead guarantees:
  - get_predictions(as_of_date=date) adds AND date(screen_date) <= ?
  - resolve_prediction() rejects outcome_date < screen_date

Usage::

    from bve.intelligence.acquirer_fit_log import (
        log_fit_predictions,
        resolve_fit_prediction,
        get_fit_predictions,
        grade_fit_predictions,
    )

    # After a screening run:
    log_fit_predictions(store_path, acquirer_id="vertex", screen_date="2026-04-07",
                        rows=result.rows)

    # When Alpine/Vertex deal closed (2024-12-20):
    resolve_fit_prediction(store_path, record_id=..., outcome="acquisition",
                           outcome_date="2024-12-20")

    # Grade the model:
    report = grade_fit_predictions(store_path, acquirer_id="vertex")
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Record type
# ---------------------------------------------------------------------------

@dataclass
class FitPredictionRecord:
    record_id: str
    acquirer_id: str
    asset_id: str
    ticker: Optional[str]
    therapeutic_area: Optional[str]
    stage: Optional[str]
    rank: int
    fit_score: float
    screen_date: str              # ISO date "YYYY-MM-DD"
    outcome: Optional[str]        # None | "acquisition" | "license" | "partnership" | "none"
    outcome_date: Optional[str]
    resolved: bool
    created_at: str


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS acquirer_fit_predictions (
    record_id           TEXT PRIMARY KEY,
    acquirer_id         TEXT NOT NULL,
    asset_id            TEXT NOT NULL,
    ticker              TEXT,
    therapeutic_area    TEXT,
    stage               TEXT,
    rank                INTEGER NOT NULL,
    fit_score           REAL NOT NULL,
    screen_date         TEXT NOT NULL,
    outcome             TEXT,
    outcome_date        TEXT,
    resolved            INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_afp_acquirer ON acquirer_fit_predictions(acquirer_id);
CREATE INDEX IF NOT EXISTS idx_afp_asset ON acquirer_fit_predictions(asset_id);
CREATE INDEX IF NOT EXISTS idx_afp_screen_date ON acquirer_fit_predictions(screen_date);
"""


def _connect(store_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(store_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.commit()
    return conn


def _row_to_record(row: sqlite3.Row) -> FitPredictionRecord:
    return FitPredictionRecord(
        record_id=row["record_id"],
        acquirer_id=row["acquirer_id"],
        asset_id=row["asset_id"],
        ticker=row["ticker"],
        therapeutic_area=row["therapeutic_area"],
        stage=row["stage"],
        rank=row["rank"],
        fit_score=row["fit_score"],
        screen_date=row["screen_date"],
        outcome=row["outcome"],
        outcome_date=row["outcome_date"],
        resolved=bool(row["resolved"]),
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_fit_predictions(
    store_path: str | Path,
    *,
    acquirer_id: str,
    screen_date: str,
    rows: list,
    overwrite_same_date: bool = False,
) -> list[str]:
    """
    Persist a set of AcquirerFitRow objects as predictions.

    Args:
        store_path: SQLite path (created if absent).
        acquirer_id: Acquirer identifier.
        screen_date: Date of the screening run (YYYY-MM-DD).
        rows: List of AcquirerFitRow (or any object with .asset_id, .rank,
              .fit_score, and optional .ticker, .therapeutic_area, .stage).
        overwrite_same_date: When True, delete existing records for this
              (acquirer_id, screen_date) pair before inserting.

    Returns:
        List of record_ids for the inserted rows.
    """
    import datetime as _dt
    store_path = Path(store_path)
    conn = _connect(store_path)
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    record_ids: list[str] = []

    try:
        if overwrite_same_date:
            conn.execute(
                "DELETE FROM acquirer_fit_predictions WHERE acquirer_id=? AND screen_date=?",
                (acquirer_id, screen_date),
            )
        for row in rows:
            rid = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO acquirer_fit_predictions
                    (record_id, acquirer_id, asset_id, ticker, therapeutic_area,
                     stage, rank, fit_score, screen_date, resolved, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,0,?)
                """,
                (
                    rid,
                    acquirer_id,
                    getattr(row, "asset_id", ""),
                    getattr(row, "ticker", None),
                    getattr(row, "therapeutic_area", None),
                    getattr(row, "stage", None),
                    int(getattr(row, "rank", 0)),
                    float(getattr(row, "fit_score", 0.0)),
                    screen_date,
                    created_at,
                ),
            )
            record_ids.append(rid)
        conn.commit()
    finally:
        conn.close()

    return record_ids


def resolve_fit_prediction(
    store_path: str | Path,
    *,
    record_id: str,
    outcome: str,
    outcome_date: str,
) -> None:
    """
    Mark an existing prediction as resolved with an actual deal outcome.

    Args:
        store_path: SQLite path.
        record_id: UUID of the prediction record.
        outcome: One of 'acquisition', 'license', 'partnership', 'none'.
        outcome_date: ISO date of the outcome (YYYY-MM-DD). Must be >= screen_date.

    Raises:
        ValueError: If record not found or outcome_date is before screen_date.
    """
    valid_outcomes = {"acquisition", "license", "partnership", "none"}
    if outcome not in valid_outcomes:
        raise ValueError(f"outcome must be one of {valid_outcomes!r}, got {outcome!r}")

    conn = _connect(Path(store_path))
    try:
        row = conn.execute(
            "SELECT screen_date FROM acquirer_fit_predictions WHERE record_id=?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No prediction record with id={record_id!r}")
        if outcome_date < row["screen_date"]:
            raise ValueError(
                f"outcome_date {outcome_date!r} must be >= screen_date {row['screen_date']!r}"
            )
        conn.execute(
            """
            UPDATE acquirer_fit_predictions
            SET outcome=?, outcome_date=?, resolved=1
            WHERE record_id=?
            """,
            (outcome, outcome_date, record_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_fit_predictions(
    store_path: str | Path,
    *,
    acquirer_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    resolved_only: bool = False,
    as_of_date: Optional[str] = None,
) -> list[FitPredictionRecord]:
    """
    Query prediction records with optional filters.

    Args:
        store_path: SQLite path.
        acquirer_id: Filter by acquirer.
        asset_id: Filter by asset.
        resolved_only: Return only resolved records.
        as_of_date: No-lookahead guard: only predictions made on or before this date.

    Returns:
        List of FitPredictionRecord, ordered by screen_date DESC, rank ASC.
    """
    conn = _connect(Path(store_path))
    try:
        clauses: list[str] = []
        params: list = []
        if acquirer_id is not None:
            clauses.append("acquirer_id = ?")
            params.append(acquirer_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if resolved_only:
            clauses.append("resolved = 1")
        if as_of_date is not None:
            clauses.append("date(screen_date) <= ?")
            params.append(as_of_date)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM acquirer_fit_predictions {where} ORDER BY screen_date DESC, rank ASC",
            params,
        ).fetchall()
        return [_row_to_record(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Block 5B — Grading
# ---------------------------------------------------------------------------

@dataclass
class FitGradeReport:
    """Precision@K, MRR, and error breakdown for resolved acquirer-fit predictions."""
    acquirer_id: Optional[str]
    n_screens: int           # distinct screen dates evaluated
    n_total: int             # total resolved prediction records
    n_deals: int             # positive outcomes (acquisition|license|partnership)
    precision_at_1: float    # fraction of screens where rank-1 was a deal
    precision_at_3: float    # fraction of screens where ≥1 of top-3 was a deal
    mean_reciprocal_rank: float
    # Breakdown by TA (TA → {n, n_deals, precision_at_3})
    ta_breakdown: dict[str, dict]
    # Breakdown by stage
    stage_breakdown: dict[str, dict]


def grade_fit_predictions(
    store_path: str | Path,
    *,
    acquirer_id: Optional[str] = None,
) -> FitGradeReport:
    """
    Grade resolved predictions by P@1, P@3, and MRR.

    Only resolved records are used. Groups by screen_date to compute per-screen
    precision, then averages across all screens.

    Args:
        store_path: SQLite path.
        acquirer_id: If provided, limit to this acquirer.

    Returns:
        FitGradeReport with P@1, P@3, MRR, and TA/stage breakdowns.
    """
    records = get_fit_predictions(
        store_path,
        acquirer_id=acquirer_id,
        resolved_only=True,
    )

    if not records:
        return FitGradeReport(
            acquirer_id=acquirer_id,
            n_screens=0,
            n_total=0,
            n_deals=0,
            precision_at_1=0.0,
            precision_at_3=0.0,
            mean_reciprocal_rank=0.0,
            ta_breakdown={},
            stage_breakdown={},
        )

    _deal_outcomes = {"acquisition", "license", "partnership"}
    n_deals = sum(1 for r in records if r.outcome in _deal_outcomes)

    # Group by (acquirer_id, screen_date)
    from collections import defaultdict
    screens: dict[tuple, list[FitPredictionRecord]] = defaultdict(list)
    for r in records:
        screens[(r.acquirer_id, r.screen_date)].append(r)

    p1_hits = 0
    p3_hits = 0
    mrr_sum = 0.0
    n_screens = len(screens)

    for recs in screens.values():
        # Sort by rank
        sorted_recs = sorted(recs, key=lambda x: x.rank)
        # P@1
        if sorted_recs and sorted_recs[0].outcome in _deal_outcomes:
            p1_hits += 1
        # P@3
        top3 = sorted_recs[:3]
        if any(r.outcome in _deal_outcomes for r in top3):
            p3_hits += 1
        # MRR — first hit rank
        for r in sorted_recs:
            if r.outcome in _deal_outcomes:
                mrr_sum += 1.0 / r.rank
                break

    p1 = p1_hits / n_screens if n_screens > 0 else 0.0
    p3 = p3_hits / n_screens if n_screens > 0 else 0.0
    mrr = mrr_sum / n_screens if n_screens > 0 else 0.0

    # TA breakdown
    ta_data: dict[str, dict] = defaultdict(lambda: {"n": 0, "n_deals": 0})
    for r in records:
        ta = r.therapeutic_area or "unknown"
        ta_data[ta]["n"] += 1
        if r.outcome in _deal_outcomes:
            ta_data[ta]["n_deals"] += 1

    for ta, d in ta_data.items():
        d["precision"] = d["n_deals"] / d["n"] if d["n"] > 0 else 0.0

    # Stage breakdown
    stage_data: dict[str, dict] = defaultdict(lambda: {"n": 0, "n_deals": 0})
    for r in records:
        stage = r.stage or "unknown"
        stage_data[stage]["n"] += 1
        if r.outcome in _deal_outcomes:
            stage_data[stage]["n_deals"] += 1

    for stage, d in stage_data.items():
        d["precision"] = d["n_deals"] / d["n"] if d["n"] > 0 else 0.0

    return FitGradeReport(
        acquirer_id=acquirer_id,
        n_screens=n_screens,
        n_total=len(records),
        n_deals=n_deals,
        precision_at_1=round(p1, 4),
        precision_at_3=round(p3, 4),
        mean_reciprocal_rank=round(mrr, 4),
        ta_breakdown=dict(ta_data),
        stage_breakdown=dict(stage_data),
    )
