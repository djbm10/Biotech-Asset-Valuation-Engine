"""Bitemporal fact store — every material fact has valid_from/valid_to + known_at."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Generator, Sequence


@dataclass
class PointInTimeFact:
    """A single bitemporal fact record.

    Two time axes:
    - valid_from / valid_to  : when this fact was TRUE in the real world
    - known_at               : when we first learned about it (ingestion time)
    """

    entity_id: str
    fact_type: str
    value: Any
    valid_from: date
    valid_to: date | None  # None = still valid
    known_at: datetime
    ingested_at: datetime
    source: str
    source_document_id: str
    fact_id: int | None = None

    def as_of_check(self, as_of_date: date, knowledge_cutoff: datetime) -> bool:
        """
        Return True if this fact was known and valid as of the given dates.
        No-lookahead guarantee: known_at <= knowledge_cutoff AND valid_from <= as_of_date.
        """
        if self.known_at > knowledge_cutoff:
            return False
        if self.valid_from > as_of_date:
            return False
        if self.valid_to is not None and self.valid_to <= as_of_date:
            return False
        return True


DDL = """
CREATE TABLE IF NOT EXISTS pit_facts (
    fact_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id        TEXT    NOT NULL,
    fact_type        TEXT    NOT NULL,
    value            TEXT,
    valid_from       TEXT    NOT NULL,
    valid_to         TEXT,
    known_at         TEXT    NOT NULL,
    ingested_at      TEXT    NOT NULL,
    source           TEXT    NOT NULL,
    source_document_id TEXT  NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pit_entity_type ON pit_facts (entity_id, fact_type);
CREATE INDEX IF NOT EXISTS idx_pit_known_at    ON pit_facts (known_at);
CREATE INDEX IF NOT EXISTS idx_pit_valid_from  ON pit_facts (valid_from);
"""


class FactStore:
    """SQLite-backed store for PIT facts."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._in_memory = (self._db_path == ":memory:")
        # Keep a single persistent connection for :memory: databases so tables survive
        self._persistent_conn: sqlite3.Connection | None = None
        if self._in_memory:
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        if self._in_memory and self._persistent_conn is not None:
            yield self._persistent_conn
            self._persistent_conn.commit()
        else:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(DDL)

    def insert(self, fact: PointInTimeFact) -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO pit_facts
                   (entity_id, fact_type, value, valid_from, valid_to,
                    known_at, ingested_at, source, source_document_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fact.entity_id,
                    fact.fact_type,
                    str(fact.value) if fact.value is not None else None,
                    fact.valid_from.isoformat(),
                    fact.valid_to.isoformat() if fact.valid_to else None,
                    fact.known_at.isoformat(),
                    fact.ingested_at.isoformat(),
                    fact.source,
                    fact.source_document_id,
                ),
            )
            return cursor.lastrowid

    def insert_batch(self, facts: Sequence[PointInTimeFact]) -> list[int]:
        return [self.insert(f) for f in facts]

    def _row_to_fact(self, row: sqlite3.Row) -> PointInTimeFact:
        return PointInTimeFact(
            fact_id=row["fact_id"],
            entity_id=row["entity_id"],
            fact_type=row["fact_type"],
            value=row["value"],
            valid_from=date.fromisoformat(row["valid_from"]),
            valid_to=date.fromisoformat(row["valid_to"]) if row["valid_to"] else None,
            known_at=datetime.fromisoformat(row["known_at"]),
            ingested_at=datetime.fromisoformat(row["ingested_at"]),
            source=row["source"],
            source_document_id=row["source_document_id"],
        )

    def query_as_of(
        self,
        entity_id: str,
        fact_type: str,
        as_of_date: date,
        knowledge_cutoff: datetime,
    ) -> list[PointInTimeFact]:
        """
        No-lookahead query:
          WHERE known_at <= :knowledge_cutoff
          AND valid_from <= :as_of_date
          AND (valid_to IS NULL OR valid_to > :as_of_date)
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM pit_facts
                   WHERE entity_id = ?
                     AND fact_type = ?
                     AND known_at  <= ?
                     AND valid_from <= ?
                     AND (valid_to IS NULL OR valid_to > ?)
                   ORDER BY known_at DESC""",
                (
                    entity_id,
                    fact_type,
                    knowledge_cutoff.isoformat(),
                    as_of_date.isoformat(),
                    as_of_date.isoformat(),
                ),
            ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def latest_as_of(
        self,
        entity_id: str,
        fact_type: str,
        as_of_date: date,
        knowledge_cutoff: datetime,
    ) -> PointInTimeFact | None:
        facts = self.query_as_of(entity_id, fact_type, as_of_date, knowledge_cutoff)
        return facts[0] if facts else None
