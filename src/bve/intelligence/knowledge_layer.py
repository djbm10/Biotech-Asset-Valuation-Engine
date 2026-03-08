"""
Minimal relational knowledge layer for intelligence workflows.

Design goals:
  - structured (non-vector) retrieval first
  - source traceability on every persisted record
  - auditable, reconstructable dossier outputs
  - no direct dependency on valuation-engine modules
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.intelligence.extraction.raw_document import RawDocument
from bve.intelligence.extraction.result import ExtractionResult
from bve.intelligence.schemas.runs import ReviewDecision
from bve.intelligence.schemas.signals import Event, StructuredSignal
from bve.intelligence.taxonomy import EventType


class SourceTrace(BaseModel):
    """Provenance attached to each stored record."""

    source_type: str
    source_ref: str
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class RawDocumentRecord(BaseModel):
    """Minimal stored raw-document artifact."""

    id: str
    payload_json: dict
    created_at: datetime


class ExtractionResultRecord(BaseModel):
    """Minimal stored extraction-result artifact."""

    id: str
    raw_document_id: str
    payload_json: dict
    created_at: datetime


class StructuredSignalRecord(BaseModel):
    """Minimal stored structured-signal artifact."""

    id: str
    extraction_result_id: str
    payload_json: dict
    created_at: datetime


class StoredValuationDiff(BaseModel):
    """
    Storage-safe valuation diff model used by the knowledge layer.

    This model intentionally avoids importing valuation modules.
    """

    run_id: str
    event_id: str
    asset_id: str
    valuation_before: dict
    valuation_after: dict
    delta_npv: float
    created_at: datetime
    valuation_delta: dict[str, float] = Field(default_factory=dict)
    assumptions_changed: list[dict] = Field(default_factory=list)
    applied_overrides: dict[str, float] = Field(default_factory=dict)


class MemoRecord(BaseModel):
    """Persisted analyst/system memo."""

    id: str
    company_id: Optional[str] = None
    asset_id: Optional[str] = None
    title: str
    memo_type: str = "analyst_memo"
    content_markdown: str
    created_at: datetime
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    source_signal_ids: list[str] = Field(default_factory=list)
    source_run_ids: list[str] = Field(default_factory=list)
    referenced_event_ids: list[str] = Field(default_factory=list)
    referenced_diff_ids: list[str] = Field(default_factory=list)
    referenced_review_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    source_trace: SourceTrace


class DossierRecord(BaseModel):
    """Generated dossier for a company/asset."""

    id: str
    company_id: Optional[str] = None
    asset_id: Optional[str] = None
    generated_at: datetime
    recent_events: list[Event] = Field(default_factory=list)
    current_assumptions: dict = Field(default_factory=dict)
    latest_valuation_snapshot: dict = Field(default_factory=dict)
    recent_changes: list[StoredValuationDiff] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    source_trace: SourceTrace


class RecordWithTrace(BaseModel):
    """Stored payload + provenance + reconstructed chain."""

    record_type: str
    record_id: str
    payload: dict
    source_trace: SourceTrace
    provenance_chain: dict[str, Any] = Field(default_factory=dict)


class KnowledgeStore:
    """
    SQLite-backed knowledge storage and retrieval.

    Stores:
      - upstream provenance artifacts (raw documents, extraction results, structured signals)
      - events
      - valuation diffs (+ assumptions and valuation snapshots)
      - review decisions
      - memos
      - dossiers
    """

    def __init__(self, db_path: str | Path = "outputs/intelligence_phase2/knowledge.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _coerce_datetime(value: Any, *, default: Optional[datetime] = None) -> datetime:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
        else:
            dt = default or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        cols = {
            row["name"]
            for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in cols:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS raw_documents (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                document_hash TEXT,
                source_url TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS extraction_results (
                id TEXT PRIMARY KEY,
                raw_document_id TEXT,
                signal_id TEXT,
                event_id TEXT,
                company_id TEXT,
                asset_id TEXT,
                event_type TEXT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS structured_signals (
                id TEXT PRIMARY KEY,
                extraction_result_id TEXT,
                event_id TEXT,
                company_id TEXT,
                asset_id TEXT,
                event_type TEXT,
                signal_date TEXT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                signal_id TEXT,
                company_id TEXT,
                asset_id TEXT,
                indication_id TEXT,
                event_type TEXT,
                observed_at TEXT,
                ingested_at TEXT,
                source_url TEXT,
                source_type TEXT,
                headline TEXT,
                confidence REAL,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS valuation_diffs (
                run_id TEXT PRIMARY KEY,
                company_id TEXT,
                asset_id TEXT,
                event_id TEXT,
                created_at TEXT,
                delta_npv REAL,
                payload_json TEXT NOT NULL,
                assumptions_snapshot_json TEXT,
                valuation_snapshot_json TEXT,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS review_decisions (
                id TEXT PRIMARY KEY,
                proposal_id TEXT,
                run_id TEXT,
                company_id TEXT,
                asset_id TEXT,
                decision TEXT,
                reviewer_id TEXT,
                reviewed_at TEXT,
                override_value REAL,
                rationale TEXT,
                notes TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memos (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                asset_id TEXT,
                memo_type TEXT,
                title TEXT,
                created_at TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dossiers (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                asset_id TEXT,
                generated_at TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_raw_documents_created
                ON raw_documents(created_at);
            CREATE INDEX IF NOT EXISTS idx_raw_documents_hash
                ON raw_documents(document_hash);
            CREATE INDEX IF NOT EXISTS idx_extractions_raw_document
                ON extraction_results(raw_document_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_extractions_company_asset
                ON extraction_results(company_id, asset_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_signals_extraction
                ON structured_signals(extraction_result_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_signals_event
                ON structured_signals(event_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_signals_company_asset
                ON structured_signals(company_id, asset_id, signal_date);
            CREATE INDEX IF NOT EXISTS idx_signals_type_date
                ON structured_signals(event_type, signal_date);

            CREATE INDEX IF NOT EXISTS idx_events_signal
                ON events(signal_id);
            CREATE INDEX IF NOT EXISTS idx_events_company_asset_date
                ON events(company_id, asset_id, observed_at);
            CREATE INDEX IF NOT EXISTS idx_events_type_date
                ON events(event_type, observed_at);

            CREATE INDEX IF NOT EXISTS idx_diffs_company_asset_date
                ON valuation_diffs(company_id, asset_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_diffs_event_date
                ON valuation_diffs(event_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_reviews_company_asset_date
                ON review_decisions(company_id, asset_id, reviewed_at);
            CREATE INDEX IF NOT EXISTS idx_reviews_run
                ON review_decisions(run_id, reviewed_at);

            CREATE INDEX IF NOT EXISTS idx_memos_company_asset_date
                ON memos(company_id, asset_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_dossiers_company_asset_date
                ON dossiers(company_id, asset_id, generated_at);
            """
        )

        # Backward-compatible migration path for existing databases.
        self._ensure_column("raw_documents", "document_hash", "TEXT")
        self._ensure_column("events", "signal_id", "TEXT")
        self._ensure_column("valuation_diffs", "created_at", "TEXT")

        diff_cols = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(valuation_diffs)").fetchall()
        }
        # Backfill created_at from legacy generated_at if needed.
        if "generated_at" in diff_cols:
            self._conn.execute(
                """
                UPDATE valuation_diffs
                   SET created_at = COALESCE(created_at, generated_at)
                 WHERE created_at IS NULL
                """
            )
        self._conn.commit()

    @staticmethod
    def _event_type_value(event_type: Optional[str | EventType]) -> Optional[str]:
        if event_type is None:
            return None
        if isinstance(event_type, EventType):
            return event_type.value
        return event_type

    @staticmethod
    def _json_dump(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=True)

    # ---------------------------------------------------------------------
    # Inserts
    # ---------------------------------------------------------------------

    def add_raw_document(
        self,
        raw_document: RawDocument | RawDocumentRecord | dict,
        source_trace: SourceTrace,
    ) -> RawDocumentRecord:
        if isinstance(raw_document, RawDocumentRecord):
            record = raw_document
        else:
            payload = (
                raw_document.model_dump(mode="json")
                if hasattr(raw_document, "model_dump")
                else dict(raw_document)
            )
            record = RawDocumentRecord(
                id=str(payload.get("id")),
                payload_json=payload,
                created_at=self._coerce_datetime(
                    payload.get("created_at") or payload.get("retrieved_at")
                ),
            )

        source_url = record.payload_json.get("source_url")
        document_hash = record.payload_json.get("document_hash")
        self._conn.execute(
            """
            INSERT OR REPLACE INTO raw_documents(
                id, created_at, document_hash, source_url, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.created_at.isoformat(),
                document_hash,
                source_url,
                self._json_dump(record.payload_json),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()
        return record

    def add_extraction_result(
        self,
        extraction_result: ExtractionResult | ExtractionResultRecord | dict,
        source_trace: SourceTrace,
        *,
        raw_document_id: Optional[str] = None,
    ) -> ExtractionResultRecord:
        if isinstance(extraction_result, ExtractionResultRecord):
            record = extraction_result
            payload = record.payload_json
        else:
            payload = (
                extraction_result.model_dump(mode="json")
                if hasattr(extraction_result, "model_dump")
                else dict(extraction_result)
            )
            doc_id = str(raw_document_id or payload.get("raw_document_id") or payload.get("document_id") or "")
            if not doc_id:
                raise ValueError("raw_document_id/document_id is required for extraction result storage")
            extracted_at = payload.get("extracted_at") or payload.get("created_at")
            record = ExtractionResultRecord(
                id=str(payload.get("id") or payload.get("document_id") or uuid.uuid4()),
                raw_document_id=doc_id,
                payload_json=payload,
                created_at=self._coerce_datetime(extracted_at),
            )

        signal_payload = payload.get("signal") if isinstance(payload.get("signal"), dict) else {}
        signal_id = signal_payload.get("id")
        event_id = signal_payload.get("event_id")
        event_type = payload.get("event_type_detected") or signal_payload.get("event_type")
        company_id = payload.get("company_id") or signal_payload.get("company_id")
        asset_id = payload.get("asset_id") or signal_payload.get("asset_id")

        self._conn.execute(
            """
            INSERT OR REPLACE INTO extraction_results(
                id, raw_document_id, signal_id, event_id, company_id, asset_id,
                event_type, created_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.raw_document_id,
                signal_id,
                event_id,
                company_id,
                asset_id,
                event_type,
                record.created_at.isoformat(),
                self._json_dump(record.payload_json),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()
        return record

    def add_structured_signal(
        self,
        signal: StructuredSignal | StructuredSignalRecord | dict,
        source_trace: SourceTrace,
        *,
        extraction_result_id: Optional[str] = None,
    ) -> StructuredSignalRecord:
        if isinstance(signal, StructuredSignalRecord):
            record = signal
            payload = record.payload_json
        else:
            payload = signal.model_dump(mode="json") if hasattr(signal, "model_dump") else dict(signal)
            x_id = str(payload.get("extraction_result_id") or extraction_result_id or "")
            if not x_id:
                raise ValueError("extraction_result_id is required for structured signal storage")
            record = StructuredSignalRecord(
                id=str(payload.get("id")),
                extraction_result_id=x_id,
                payload_json=payload,
                created_at=self._coerce_datetime(payload.get("created_at")),
            )

        event_id = record.payload_json.get("event_id")
        company_id = record.payload_json.get("company_id")
        asset_id = record.payload_json.get("asset_id")
        event_type = record.payload_json.get("event_type")
        signal_date = record.payload_json.get("signal_date")

        self._conn.execute(
            """
            INSERT OR REPLACE INTO structured_signals(
                id, extraction_result_id, event_id, company_id, asset_id,
                event_type, signal_date, created_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.extraction_result_id,
                event_id,
                company_id,
                asset_id,
                event_type,
                signal_date,
                record.created_at.isoformat(),
                self._json_dump(record.payload_json),
                source_trace.model_dump_json(),
            ),
        )

        # Keep explicit event->signal relationship when the event row already exists.
        if event_id:
            self._conn.execute(
                "UPDATE events SET signal_id = ? WHERE id = ?",
                (record.id, event_id),
            )

        self._conn.commit()
        return record

    def link_event_signal(self, event_id: str, signal_id: str) -> None:
        """Explicitly link an event to a structured signal."""
        self._conn.execute(
            "UPDATE events SET signal_id = ? WHERE id = ?",
            (signal_id, event_id),
        )
        self._conn.commit()

    def raw_document_exists(self, document_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM raw_documents WHERE id = ? LIMIT 1",
            (document_id,),
        ).fetchone()
        return row is not None

    def event_exists(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM events WHERE id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        return row is not None

    def valuation_diff_exists_for_event(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM valuation_diffs WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        return row is not None

    def get_structured_signal_by_event_id(self, event_id: str) -> Optional[StructuredSignal]:
        row = self._conn.execute(
            """
            SELECT payload_json
              FROM structured_signals
             WHERE event_id = ?
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return StructuredSignal.model_validate_json(row["payload_json"])

    def add_event(
        self,
        event: Event,
        source_trace: SourceTrace,
        *,
        signal_id: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO events(
                id, signal_id, company_id, asset_id, indication_id, event_type,
                observed_at, ingested_at, source_url, source_type, headline,
                confidence, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                signal_id,
                event.company_id,
                event.asset_id,
                event.indication_id,
                event.event_type.value,
                event.observed_at.isoformat(),
                event.ingested_at.isoformat(),
                event.source_url,
                event.source_type,
                event.headline,
                float(event.confidence),
                event.model_dump_json(),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()

    @staticmethod
    def _normalize_stored_valuation_diff(diff: object) -> StoredValuationDiff:
        if isinstance(diff, StoredValuationDiff):
            return diff

        if isinstance(diff, dict):
            payload: dict[str, Any] = dict(diff)
        elif hasattr(diff, "model_dump"):
            payload = diff.model_dump(mode="json")
        else:
            raise TypeError("Unsupported valuation diff type")

        run_id = str(payload.get("run_id") or payload.get("id") or uuid.uuid4())
        event_id = str(payload.get("event_id") or "")
        asset_id = str(payload.get("asset_id") or "")
        if not event_id or not asset_id:
            raise ValueError("valuation diff must include event_id and asset_id")

        created_at = (
            payload.get("created_at")
            or payload.get("generated_at")
            or datetime.now(timezone.utc)
        )

        valuation_before = payload.get("valuation_before") or {}
        valuation_after = payload.get("valuation_after") or {}

        delta_npv_raw = payload.get("delta_npv")
        if delta_npv_raw is None:
            before_npv = float(valuation_before.get("rnpv_millions", 0.0) or 0.0)
            after_npv = float(valuation_after.get("rnpv_millions", 0.0) or 0.0)
            delta_npv = round(after_npv - before_npv, 2)
        else:
            delta_npv = float(delta_npv_raw)

        valuation_delta = payload.get("valuation_delta") or {}
        if not valuation_delta:
            for key in (
                "delta_npv",
                "delta_nav_per_share",
                "delta_mc_mean_millions",
                "delta_bull_rnpv_millions",
                "delta_base_rnpv_millions",
                "delta_bear_rnpv_millions",
            ):
                value = payload.get(key)
                if value is not None:
                    valuation_delta[key] = float(value)

        return StoredValuationDiff(
            run_id=run_id,
            event_id=event_id,
            asset_id=asset_id,
            valuation_before=valuation_before,
            valuation_after=valuation_after,
            delta_npv=delta_npv,
            created_at=KnowledgeStore._coerce_datetime(created_at),
            valuation_delta=valuation_delta,
            assumptions_changed=list(payload.get("assumptions_changed") or []),
            applied_overrides=dict(payload.get("applied_overrides") or {}),
        )

    def add_valuation_diff(
        self,
        diff: object,
        *,
        company_id: Optional[str],
        source_trace: SourceTrace,
        assumptions_snapshot: Optional[dict] = None,
        valuation_snapshot: Optional[dict] = None,
    ) -> StoredValuationDiff:
        stored = self._normalize_stored_valuation_diff(diff)

        snapshot = valuation_snapshot or stored.valuation_after
        self._conn.execute(
            """
            INSERT OR REPLACE INTO valuation_diffs(
                run_id, company_id, asset_id, event_id, created_at, delta_npv,
                payload_json, assumptions_snapshot_json, valuation_snapshot_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored.run_id,
                company_id,
                stored.asset_id,
                stored.event_id,
                stored.created_at.isoformat(),
                float(stored.delta_npv),
                stored.model_dump_json(),
                self._json_dump(assumptions_snapshot or {}),
                self._json_dump(snapshot),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()
        return stored

    def add_review_decision(
        self,
        decision: ReviewDecision,
        *,
        company_id: Optional[str],
        asset_id: Optional[str],
        source_trace: SourceTrace,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO review_decisions(
                id, proposal_id, run_id, company_id, asset_id, decision, reviewer_id,
                reviewed_at, override_value, rationale, notes, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.id,
                decision.proposal_id,
                decision.run_id,
                company_id,
                asset_id,
                decision.decision,
                decision.reviewer_id,
                decision.reviewed_at.isoformat(),
                decision.override_value,
                decision.rationale,
                decision.notes,
                decision.model_dump_json(),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()

    def add_memo(self, memo: MemoRecord) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO memos(
                id, company_id, asset_id, memo_type, title, created_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memo.id,
                memo.company_id,
                memo.asset_id,
                memo.memo_type,
                memo.title,
                memo.created_at.isoformat(),
                memo.model_dump_json(),
                memo.source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()

    def add_dossier(self, dossier: DossierRecord) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO dossiers(
                id, company_id, asset_id, generated_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                dossier.id,
                dossier.company_id,
                dossier.asset_id,
                dossier.generated_at.isoformat(),
                dossier.model_dump_json(),
                dossier.source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()

    # ---------------------------------------------------------------------
    # Retrieval
    # ---------------------------------------------------------------------

    def get_raw_documents(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[RawDocumentRecord]:
        clauses = []
        params: list[object] = []
        if date_from is not None:
            clauses.append("DATE(created_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(created_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM raw_documents"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        out: list[RawDocumentRecord] = []
        for r in rows:
            payload = json.loads(r["payload_json"])
            out.append(
                RawDocumentRecord(
                    id=str(payload.get("id")),
                    payload_json=payload,
                    created_at=self._coerce_datetime(
                        payload.get("created_at") or payload.get("retrieved_at")
                    ),
                )
            )
        return out

    def get_extraction_results(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[ExtractionResultRecord]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append("event_type = ?")
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(created_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(created_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT id, raw_document_id, payload_json, created_at FROM extraction_results"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            ExtractionResultRecord(
                id=row["id"],
                raw_document_id=row["raw_document_id"],
                payload_json=json.loads(row["payload_json"]),
                created_at=self._coerce_datetime(row["created_at"]),
            )
            for row in rows
        ]

    def get_structured_signals(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[StructuredSignalRecord]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append("event_type = ?")
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(signal_date) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(signal_date) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT id, extraction_result_id, payload_json, created_at FROM structured_signals"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY signal_date DESC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            StructuredSignalRecord(
                id=row["id"],
                extraction_result_id=row["extraction_result_id"],
                payload_json=json.loads(row["payload_json"]),
                created_at=self._coerce_datetime(row["created_at"]),
            )
            for row in rows
        ]

    def get_events(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[Event]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append("event_type = ?")
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(observed_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(observed_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY observed_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [Event.model_validate_json(r["payload_json"]) for r in rows]

    def get_valuation_diffs(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[StoredValuationDiff]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append("event_id IN (SELECT id FROM events WHERE event_type = ?)")
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(created_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(created_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM valuation_diffs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [StoredValuationDiff.model_validate_json(r["payload_json"]) for r in rows]

    def get_review_decisions(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        decision: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[ReviewDecision]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if decision is not None:
            clauses.append("decision = ?")
            params.append(decision)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append(
                "run_id IN ("
                "SELECT run_id FROM valuation_diffs "
                "WHERE event_id IN (SELECT id FROM events WHERE event_type = ?)"
                ")"
            )
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(reviewed_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(reviewed_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM review_decisions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY reviewed_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [ReviewDecision.model_validate_json(r["payload_json"]) for r in rows]

    def get_memos(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        memo_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[MemoRecord]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if memo_type is not None:
            clauses.append("memo_type = ?")
            params.append(memo_type)
        if date_from is not None:
            clauses.append("DATE(created_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(created_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM memos"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [MemoRecord.model_validate_json(r["payload_json"]) for r in rows]

    def get_dossiers(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[DossierRecord]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if date_from is not None:
            clauses.append("DATE(generated_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(generated_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM dossiers"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY generated_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [DossierRecord.model_validate_json(r["payload_json"]) for r in rows]

    # ---------------------------------------------------------------------
    # Dossier generation
    # ---------------------------------------------------------------------

    def generate_dossier(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_limit: int = 10,
        change_limit: int = 5,
        persist: bool = True,
    ) -> DossierRecord:
        if company_id is None and asset_id is None:
            raise ValueError("At least one of company_id or asset_id must be provided")

        recent_events = self.get_events(
            company_id=company_id,
            asset_id=asset_id,
            limit=event_limit,
        )
        recent_changes = self.get_valuation_diffs(
            company_id=company_id,
            asset_id=asset_id,
            limit=change_limit,
        )

        latest_ctx = self._latest_valuation_context(company_id=company_id, asset_id=asset_id)
        current_assumptions = latest_ctx.get("assumptions_snapshot", {})
        latest_valuation_snapshot = latest_ctx.get("valuation_snapshot", {})

        open_questions: list[str] = []
        for decision in self.get_review_decisions(
            company_id=company_id,
            asset_id=asset_id,
            decision="deferred",
            limit=10,
        ):
            open_questions.append(f"Deferred review {decision.id}: {decision.rationale}")
        for memo in self.get_memos(company_id=company_id, asset_id=asset_id, limit=5):
            open_questions.extend(memo.open_questions)

        # Deduplicate while preserving order.
        seen = set()
        deduped = []
        for q in open_questions:
            if q not in seen:
                seen.add(q)
                deduped.append(q)

        dossier = DossierRecord(
            id=str(uuid.uuid4()),
            company_id=company_id,
            asset_id=asset_id,
            generated_at=datetime.now(timezone.utc),
            recent_events=recent_events,
            current_assumptions=current_assumptions,
            latest_valuation_snapshot=latest_valuation_snapshot,
            recent_changes=recent_changes,
            open_questions=deduped,
            source_trace=SourceTrace(
                source_type="knowledge_layer",
                source_ref="KnowledgeStore.generate_dossier",
            ),
        )
        if persist:
            self.add_dossier(dossier)
        return dossier

    def _latest_valuation_context(
        self,
        *,
        company_id: Optional[str],
        asset_id: Optional[str],
    ) -> dict:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)

        sql = (
            "SELECT assumptions_snapshot_json, valuation_snapshot_json "
            "FROM valuation_diffs"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT 1"
        row = self._conn.execute(sql, params).fetchone()
        if row is None:
            return {}
        assumptions_json = row["assumptions_snapshot_json"] or "{}"
        valuation_json = row["valuation_snapshot_json"] or "{}"
        return {
            "assumptions_snapshot": json.loads(assumptions_json),
            "valuation_snapshot": json.loads(valuation_json),
        }

    # ---------------------------------------------------------------------
    # Provenance
    # ---------------------------------------------------------------------

    @staticmethod
    def _table_map() -> dict[str, tuple[str, str]]:
        return {
            "raw_documents": ("raw_documents", "id"),
            "extraction_results": ("extraction_results", "id"),
            "structured_signals": ("structured_signals", "id"),
            "events": ("events", "id"),
            "valuation_diffs": ("valuation_diffs", "run_id"),
            "review_decisions": ("review_decisions", "id"),
            "memos": ("memos", "id"),
            "dossiers": ("dossiers", "id"),
        }

    def get_source_trace(self, record_type: str, record_id: str) -> SourceTrace:
        """
        Retrieve provenance trace for a stored record.

        record_type:
          raw_documents | extraction_results | structured_signals | events |
          valuation_diffs | review_decisions | memos | dossiers
        """
        table_map = self._table_map()
        if record_type not in table_map:
            raise ValueError(
                f"Unknown record_type={record_type!r}; expected one of {sorted(table_map)}"
            )
        table, pk = table_map[record_type]
        row = self._conn.execute(
            f"SELECT source_trace_json FROM {table} WHERE {pk} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No record found for {record_type}:{record_id}")
        return SourceTrace.model_validate_json(row["source_trace_json"])

    def _fetch_row(self, record_type: str, record_id: str) -> sqlite3.Row:
        table, pk = self._table_map()[record_type]
        row = self._conn.execute(
            f"SELECT * FROM {table} WHERE {pk} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No record found for {record_type}:{record_id}")
        return row

    def _node(self, record_type: str, record_id: str) -> Optional[dict[str, Any]]:
        try:
            row = self._fetch_row(record_type, record_id)
        except KeyError:
            return None
        return {
            "record_type": record_type,
            "record_id": record_id,
            "payload": json.loads(row["payload_json"]),
            "source_trace": SourceTrace.model_validate_json(row["source_trace_json"]).model_dump(mode="json"),
        }

    def _latest_signal_for_event(self, event_id: str, preferred_signal_id: Optional[str]) -> Optional[sqlite3.Row]:
        if preferred_signal_id:
            row = self._conn.execute(
                "SELECT * FROM structured_signals WHERE id = ?",
                (preferred_signal_id,),
            ).fetchone()
            if row is not None:
                return row
        return self._conn.execute(
            """
            SELECT *
              FROM structured_signals
             WHERE event_id = ?
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (event_id,),
        ).fetchone()

    def _valuation_diff_for_event(self, event_id: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT *
              FROM valuation_diffs
             WHERE event_id = ?
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (event_id,),
        ).fetchone()

    def _review_rows_for_run(self, run_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT *
              FROM review_decisions
             WHERE run_id = ?
             ORDER BY reviewed_at DESC
            """,
            (run_id,),
        ).fetchall()

    def _memo_rows_related(self, *, run_id: Optional[str], signal_id: Optional[str]) -> list[sqlite3.Row]:
        rows = self._conn.execute("SELECT * FROM memos ORDER BY created_at DESC").fetchall()
        related: list[sqlite3.Row] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            run_ids = list(payload.get("source_run_ids") or []) + list(payload.get("referenced_diff_ids") or [])
            signal_ids = list(payload.get("source_signal_ids") or [])
            if run_id and run_id in run_ids:
                related.append(row)
                continue
            if signal_id and signal_id in signal_ids:
                related.append(row)
        return related

    def _build_provenance_chain(
        self,
        *,
        record_type: str,
        record_id: str,
        payload: dict,
    ) -> dict[str, Any]:
        chain: dict[str, Any] = {
            "source_url": None,
            "raw_document": None,
            "extraction_result": None,
            "structured_signal": None,
            "event": None,
            "valuation_diff": None,
            "review_decisions": [],
            "memos": [],
        }

        event_id: Optional[str] = None
        signal_id: Optional[str] = None
        extraction_id: Optional[str] = None
        raw_document_id: Optional[str] = None
        run_id: Optional[str] = None

        if record_type == "raw_documents":
            raw_document_id = record_id
        elif record_type == "extraction_results":
            extraction_id = record_id
            raw_document_id = payload.get("raw_document_id") or payload.get("document_id")
        elif record_type == "structured_signals":
            signal_id = record_id
            extraction_id = payload.get("extraction_result_id")
            event_id = payload.get("event_id")
        elif record_type == "events":
            event_id = record_id
            row = self._fetch_row("events", record_id)
            signal_id = row["signal_id"]
            chain["source_url"] = payload.get("source_url")
        elif record_type == "valuation_diffs":
            run_id = record_id
            event_id = payload.get("event_id")
            chain["valuation_diff"] = self._node("valuation_diffs", record_id)
        elif record_type == "review_decisions":
            run_id = payload.get("run_id")
        elif record_type == "memos":
            source_runs = list(payload.get("source_run_ids") or []) + list(payload.get("referenced_diff_ids") or [])
            source_signals = payload.get("source_signal_ids") or []
            run_id = source_runs[0] if source_runs else None
            signal_id = source_signals[0] if source_signals else None
        elif record_type == "dossiers":
            recent_events = payload.get("recent_events") or []
            if recent_events:
                event_id = recent_events[0].get("id")

        if run_id and chain["valuation_diff"] is None:
            vrow = self._conn.execute(
                "SELECT * FROM valuation_diffs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if vrow is not None:
                chain["valuation_diff"] = self._node("valuation_diffs", run_id)
                vpayload = json.loads(vrow["payload_json"])
                event_id = event_id or vpayload.get("event_id")

        if event_id:
            erow = self._conn.execute(
                "SELECT * FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if erow is not None:
                chain["event"] = self._node("events", event_id)
                epayload = json.loads(erow["payload_json"])
                chain["source_url"] = chain["source_url"] or epayload.get("source_url")
                signal_id = signal_id or erow["signal_id"]

                if chain["valuation_diff"] is None:
                    vrow = self._valuation_diff_for_event(event_id)
                    if vrow is not None:
                        chain["valuation_diff"] = self._node("valuation_diffs", vrow["run_id"])
                        run_id = run_id or vrow["run_id"]

        if signal_id is None and event_id:
            srow = self._latest_signal_for_event(event_id, preferred_signal_id=None)
            if srow is not None:
                signal_id = srow["id"]

        if signal_id:
            srow = self._conn.execute(
                "SELECT * FROM structured_signals WHERE id = ?",
                (signal_id,),
            ).fetchone()
            if srow is not None:
                chain["structured_signal"] = self._node("structured_signals", signal_id)
                extraction_id = extraction_id or srow["extraction_result_id"]
                event_id = event_id or srow["event_id"]

        if extraction_id:
            xrow = self._conn.execute(
                "SELECT * FROM extraction_results WHERE id = ?",
                (extraction_id,),
            ).fetchone()
            if xrow is not None:
                chain["extraction_result"] = self._node("extraction_results", extraction_id)
                raw_document_id = raw_document_id or xrow["raw_document_id"]

        if raw_document_id:
            rrow = self._conn.execute(
                "SELECT * FROM raw_documents WHERE id = ?",
                (raw_document_id,),
            ).fetchone()
            if rrow is not None:
                chain["raw_document"] = self._node("raw_documents", raw_document_id)
                rpayload = json.loads(rrow["payload_json"])
                chain["source_url"] = rpayload.get("source_url") or chain["source_url"]

        if run_id is None and chain["valuation_diff"] is not None:
            run_id = chain["valuation_diff"]["record_id"]

        if run_id:
            chain["review_decisions"] = [
                self._node("review_decisions", row["id"])
                for row in self._review_rows_for_run(run_id)
            ]

        memo_rows = self._memo_rows_related(run_id=run_id, signal_id=signal_id)
        chain["memos"] = [self._node("memos", row["id"]) for row in memo_rows]

        return chain

    def get_record_with_trace(self, record_type: str, record_id: str) -> RecordWithTrace:
        """
        Retrieve one persisted row with payload, trace, and provenance chain.

        record_type:
          raw_documents | extraction_results | structured_signals | events |
          valuation_diffs | review_decisions | memos | dossiers
        """
        table_map = self._table_map()
        if record_type not in table_map:
            raise ValueError(
                f"Unknown record_type={record_type!r}; expected one of {sorted(table_map)}"
            )

        table, pk = table_map[record_type]
        row = self._conn.execute(
            f"SELECT payload_json, source_trace_json FROM {table} WHERE {pk} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No record found for {record_type}:{record_id}")

        payload = json.loads(row["payload_json"])
        source_trace = SourceTrace.model_validate_json(row["source_trace_json"])
        provenance_chain = self._build_provenance_chain(
            record_type=record_type,
            record_id=record_id,
            payload=payload,
        )
        return RecordWithTrace(
            record_type=record_type,
            record_id=record_id,
            payload=payload,
            source_trace=source_trace,
            provenance_chain=provenance_chain,
        )
