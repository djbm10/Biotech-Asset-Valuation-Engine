"""
SQLite-backed evidence store for classified and scored events.

Records are deduplicated by checksum (SHA-256 of the payload).
All queries return EvidenceRecord Pydantic objects; the SQLite layer
is an implementation detail hidden behind the EvidenceStore interface.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from bve.evidence.classifier import ClassificationResult, classify
from bve.evidence.materiality import (
    MaterialityScore,
    resolve_affected_entities,
    score_materiality,
)
from bve.ingestion.raw_event import RawEvent

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS evidence_records (
    id                   TEXT PRIMARY KEY,
    source               TEXT NOT NULL,
    record_type          TEXT NOT NULL,
    source_url           TEXT NOT NULL,
    checksum             TEXT NOT NULL UNIQUE,
    fetched_at           TEXT NOT NULL,
    stored_at            TEXT NOT NULL,
    event_type           TEXT NOT NULL,
    confidence           REAL NOT NULL,
    materiality_score    REAL NOT NULL,
    materiality_tier     TEXT NOT NULL,
    affected_entities_json TEXT NOT NULL,
    payload_json         TEXT NOT NULL,
    classification_json  TEXT NOT NULL,
    materiality_json     TEXT NOT NULL
)
"""

_CREATE_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_ev_checksum ON evidence_records(checksum)",
    "CREATE INDEX IF NOT EXISTS idx_ev_event_type ON evidence_records(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_ev_stored_at ON evidence_records(stored_at)",
    "CREATE INDEX IF NOT EXISTS idx_ev_materiality_score ON evidence_records(materiality_score)",
]


class EvidenceRecord(BaseModel):
    """A fully classified and scored evidence record persisted in the store."""

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_event: RawEvent
    classification: ClassificationResult
    materiality: MaterialityScore
    affected_entities: list[str]
    stored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _serialize_datetime(dt: datetime) -> str:
    return dt.isoformat()


def _deserialize_datetime(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _record_to_row(record: EvidenceRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "source": record.raw_event.source,
        "record_type": record.raw_event.record_type,
        "source_url": record.raw_event.source_url,
        "checksum": record.raw_event.checksum,
        "fetched_at": _serialize_datetime(record.raw_event.fetched_at),
        "stored_at": _serialize_datetime(record.stored_at),
        "event_type": record.classification.event_type.value,
        "confidence": record.classification.confidence,
        "materiality_score": record.materiality.score,
        "materiality_tier": record.materiality.tier.value,
        "affected_entities_json": json.dumps(record.affected_entities),
        "payload_json": json.dumps(record.raw_event.payload, default=str),
        "classification_json": record.classification.model_dump_json(),
        "materiality_json": record.materiality.model_dump_json(),
    }


def _row_to_record(row: sqlite3.Row) -> EvidenceRecord:
    payload = json.loads(row["payload_json"])
    raw_event = RawEvent(
        source=row["source"],
        record_type=row["record_type"],
        source_url=row["source_url"],
        fetched_at=_deserialize_datetime(row["fetched_at"]),
        checksum=row["checksum"],
        payload=payload,
        entity_ids=json.loads(row["affected_entities_json"]),
    )
    classification = ClassificationResult.model_validate_json(row["classification_json"])
    materiality = MaterialityScore.model_validate_json(row["materiality_json"])
    affected_entities: list[str] = json.loads(row["affected_entities_json"])

    return EvidenceRecord(
        id=row["id"],
        raw_event=raw_event,
        classification=classification,
        materiality=materiality,
        affected_entities=affected_entities,
        stored_at=_deserialize_datetime(row["stored_at"]),
    )


class EvidenceStore:
    """
    SQLite-backed store for evidence records.

    All records are deduplicated by payload checksum. Ingesting a duplicate
    returns None without raising an error.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup_schema()

    def _setup_schema(self) -> None:
        with self._conn:
            self._conn.execute(_CREATE_TABLE_SQL)
            for idx_sql in _CREATE_INDEX_SQL:
                self._conn.execute(idx_sql)

    def ingest(self, raw_event: RawEvent) -> EvidenceRecord | None:
        """
        Classify, score, and store a raw event.

        Returns the EvidenceRecord if stored, or None if the checksum already
        exists (duplicate).
        """
        if self.is_duplicate(raw_event.checksum):
            return None

        classification = classify(raw_event)
        materiality = score_materiality(raw_event, classification)
        affected_entities = resolve_affected_entities(raw_event, classification)

        record = EvidenceRecord(
            raw_event=raw_event,
            classification=classification,
            materiality=materiality,
            affected_entities=affected_entities,
        )

        row = _record_to_row(record)
        placeholders = ", ".join(f":{k}" for k in row)
        columns = ", ".join(row.keys())
        sql = f"INSERT OR IGNORE INTO evidence_records ({columns}) VALUES ({placeholders})"

        with self._conn:
            self._conn.execute(sql, row)

        return record

    def get_by_id(self, record_id: str) -> EvidenceRecord | None:
        cursor = self._conn.execute(
            "SELECT * FROM evidence_records WHERE id = ?", (record_id,)
        )
        row = cursor.fetchone()
        return _row_to_record(row) if row else None

    def get_by_checksum(self, checksum: str) -> EvidenceRecord | None:
        cursor = self._conn.execute(
            "SELECT * FROM evidence_records WHERE checksum = ?", (checksum,)
        )
        row = cursor.fetchone()
        return _row_to_record(row) if row else None

    def get_by_entity(self, entity_id: str, limit: int = 50) -> list[EvidenceRecord]:
        """Return records where affected_entities_json contains the entity_id."""
        cursor = self._conn.execute(
            """
            SELECT * FROM evidence_records
            WHERE affected_entities_json LIKE ?
            ORDER BY stored_at DESC
            LIMIT ?
            """,
            (f'%"{entity_id}"%', limit),
        )
        return [_row_to_record(row) for row in cursor.fetchall()]

    def get_by_event_type(
        self, event_type: str, limit: int = 50
    ) -> list[EvidenceRecord]:
        cursor = self._conn.execute(
            """
            SELECT * FROM evidence_records
            WHERE event_type = ?
            ORDER BY stored_at DESC
            LIMIT ?
            """,
            (event_type, limit),
        )
        return [_row_to_record(row) for row in cursor.fetchall()]

    def get_by_materiality(
        self, min_score: float, limit: int = 50
    ) -> list[EvidenceRecord]:
        cursor = self._conn.execute(
            """
            SELECT * FROM evidence_records
            WHERE materiality_score >= ?
            ORDER BY materiality_score DESC, stored_at DESC
            LIMIT ?
            """,
            (min_score, limit),
        )
        return [_row_to_record(row) for row in cursor.fetchall()]

    def get_recent(self, limit: int = 50) -> list[EvidenceRecord]:
        cursor = self._conn.execute(
            """
            SELECT * FROM evidence_records
            ORDER BY stored_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [_row_to_record(row) for row in cursor.fetchall()]

    def count(self) -> int:
        cursor = self._conn.execute("SELECT COUNT(*) FROM evidence_records")
        return cursor.fetchone()[0]

    def is_duplicate(self, checksum: str) -> bool:
        cursor = self._conn.execute(
            "SELECT 1 FROM evidence_records WHERE checksum = ? LIMIT 1", (checksum,)
        )
        return cursor.fetchone() is not None

    def close(self) -> None:
        self._conn.close()
