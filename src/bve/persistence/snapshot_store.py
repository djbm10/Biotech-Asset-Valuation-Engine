"""
SnapshotStore — SQLite persistence for immutable CompanySnapshot records.

Design principles
-----------------
- Insert-only: existing snapshot rows are NEVER updated.
- State transitions create a new snapshot row with parent_snapshot_id linking
  to the predecessor, plus an audit entry in snapshot_state_log.
- Separate snapshot_buckets table stores ValueBuckets with foreign key to
  company_snapshots.snapshot_id so bucket queries are efficient.
- JSON columns for nested objects (DilutionBridge, catalysts, flags,
  confidence, provenance) following the KnowledgeStore pattern.
- get_latest_snapshot(company_id, as_of) returns the most recent snapshot
  on or before as_of, enabling point-in-time replay.

Usage
-----
    store = SnapshotStore()                           # default path
    store = SnapshotStore("outputs/snapshots/cs.db")  # custom path

    snapshot = CompanySnapshot(...)
    store.insert_snapshot(snapshot)

    latest = store.get_latest_snapshot("vktx")
    history = store.get_snapshot_history("vktx", limit=10)
    candidates = store.get_capital_candidates()

    new_snap = store.transition_state(
        snapshot.snapshot_id,
        ReviewerState.REVIEWED,
        reviewer="djm",
        reason="Initial Q2 2026 pack review",
    )
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from bve.entities.company_snapshot import (
    CatalystEntry,
    CompanySnapshot,
    ConfidenceMetadata,
    DilutionBridge,
    ManagementFlag,
    ProvenanceMetadata,
    ReviewerState,
    ValueBucket,
)

_DEFAULT_DB_PATH = Path("outputs/snapshots/company_snapshots.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS company_snapshots (
    snapshot_id               TEXT PRIMARY KEY,
    company_id                TEXT NOT NULL,
    company_name              TEXT NOT NULL,
    ticker                    TEXT NOT NULL,
    as_of_date                TEXT NOT NULL,

    market_cap_millions       REAL NOT NULL,
    enterprise_value_millions REAL NOT NULL,
    share_price               REAL,

    cash_millions             REAL NOT NULL,
    debt_millions             REAL NOT NULL DEFAULT 0.0,

    dilution_bridge_json      TEXT,
    catalysts_json            TEXT NOT NULL DEFAULT '[]',
    management_flags_json     TEXT NOT NULL DEFAULT '[]',
    confidence_json           TEXT NOT NULL,
    provenance_json           TEXT NOT NULL,

    reviewer_state            TEXT NOT NULL DEFAULT 'draft',
    stale_since               TEXT,
    stale_reason              TEXT,
    notes                     TEXT,
    created_at                TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_company_date
    ON company_snapshots(company_id, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_date
    ON company_snapshots(ticker, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_state
    ON company_snapshots(reviewer_state, as_of_date DESC);

CREATE TABLE IF NOT EXISTS snapshot_buckets (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id             TEXT NOT NULL REFERENCES company_snapshots(snapshot_id),
    bucket_id               TEXT NOT NULL,
    bucket_type             TEXT NOT NULL,
    label                   TEXT NOT NULL,
    value_millions          REAL NOT NULL,
    methodology             TEXT NOT NULL,
    source_type             TEXT NOT NULL,
    source_ref              TEXT NOT NULL,
    as_of_date              TEXT NOT NULL,
    corroboration_count     INTEGER NOT NULL DEFAULT 0,
    corroboration_refs_json TEXT NOT NULL DEFAULT '[]',
    reviewer                TEXT,
    confidence              REAL NOT NULL,
    last_changed_at         TEXT,
    change_reason           TEXT,
    notes                   TEXT,
    UNIQUE(snapshot_id, bucket_id)
);

CREATE INDEX IF NOT EXISTS idx_buckets_snapshot
    ON snapshot_buckets(snapshot_id);

CREATE TABLE IF NOT EXISTS snapshot_state_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id      TEXT NOT NULL,
    from_state       TEXT NOT NULL,
    to_state         TEXT NOT NULL,
    transitioned_by  TEXT NOT NULL,
    reason           TEXT NOT NULL,
    transitioned_at  TEXT NOT NULL,
    new_snapshot_id  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_state_log_snapshot
    ON snapshot_state_log(snapshot_id);
"""


class SnapshotStore:
    """
    SQLite-backed store for CompanySnapshot records.

    All writes are insert-only.  Use transition_state() or mark_stale() to
    change a snapshot's lifecycle state — these create new snapshot rows
    and log the transition in snapshot_state_log.
    """

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write (insert-only)
    # ------------------------------------------------------------------

    def insert_snapshot(self, snapshot: CompanySnapshot) -> str:
        """
        Persist a CompanySnapshot.  Returns snapshot_id.
        Raises sqlite3.IntegrityError if snapshot_id already exists.
        """
        row = self._serialize_snapshot(snapshot)
        self._conn.execute(
            """
            INSERT INTO company_snapshots (
                snapshot_id, company_id, company_name, ticker, as_of_date,
                market_cap_millions, enterprise_value_millions, share_price,
                cash_millions, debt_millions,
                dilution_bridge_json, catalysts_json, management_flags_json,
                confidence_json, provenance_json,
                reviewer_state, stale_since, stale_reason, notes, created_at
            ) VALUES (
                :snapshot_id, :company_id, :company_name, :ticker, :as_of_date,
                :market_cap_millions, :enterprise_value_millions, :share_price,
                :cash_millions, :debt_millions,
                :dilution_bridge_json, :catalysts_json, :management_flags_json,
                :confidence_json, :provenance_json,
                :reviewer_state, :stale_since, :stale_reason, :notes, :created_at
            )
            """,
            row,
        )
        self._insert_buckets(snapshot.snapshot_id, snapshot.all_buckets)
        self._conn.commit()
        return snapshot.snapshot_id

    def _insert_buckets(self, snapshot_id: str, buckets: list[ValueBucket]) -> None:
        for b in buckets:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO snapshot_buckets (
                    snapshot_id, bucket_id, bucket_type, label, value_millions,
                    methodology, source_type, source_ref, as_of_date,
                    corroboration_count, corroboration_refs_json,
                    reviewer, confidence, last_changed_at, change_reason, notes
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    snapshot_id,
                    b.bucket_id, b.bucket_type, b.label, b.value_millions,
                    b.methodology, b.source_type, b.source_ref,
                    b.as_of_date.isoformat(),
                    b.corroboration_count,
                    json.dumps(b.corroboration_refs),
                    b.reviewer, b.confidence,
                    b.last_changed_at.isoformat() if b.last_changed_at else None,
                    b.change_reason, b.notes,
                ),
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_snapshot(self, snapshot_id: str) -> Optional[CompanySnapshot]:
        """Retrieve a specific snapshot by ID."""
        row = self._conn.execute(
            "SELECT * FROM company_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            return None
        return self._snapshot_from_row(row)

    def get_latest_snapshot(
        self,
        company_id: str,
        *,
        as_of: Optional[date] = None,
    ) -> Optional[CompanySnapshot]:
        """
        Return the most recent snapshot for company_id on or before as_of.
        If as_of is None, returns the absolute latest snapshot.
        """
        if as_of is None:
            row = self._conn.execute(
                """
                SELECT * FROM company_snapshots
                WHERE company_id = ?
                ORDER BY as_of_date DESC, created_at DESC
                LIMIT 1
                """,
                (company_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT * FROM company_snapshots
                WHERE company_id = ? AND as_of_date <= ?
                ORDER BY as_of_date DESC, created_at DESC
                LIMIT 1
                """,
                (company_id, as_of.isoformat()),
            ).fetchone()
        return self._snapshot_from_row(row) if row else None

    def get_snapshot_history(
        self,
        company_id: str,
        *,
        limit: int = 50,
    ) -> list[CompanySnapshot]:
        """Return all snapshots for a company ordered by date descending."""
        rows = self._conn.execute(
            """
            SELECT * FROM company_snapshots
            WHERE company_id = ?
            ORDER BY as_of_date DESC, created_at DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        return [self._snapshot_from_row(r) for r in rows]

    def list_snapshots(
        self,
        *,
        as_of_date: Optional[date] = None,
        reviewer_state: Optional[ReviewerState] = None,
        limit: int = 200,
    ) -> list[CompanySnapshot]:
        """List snapshots with optional filters."""
        clauses: list[str] = []
        params: list = []

        if as_of_date is not None:
            clauses.append("as_of_date = ?")
            params.append(as_of_date.isoformat())
        if reviewer_state is not None:
            clauses.append("reviewer_state = ?")
            params.append(reviewer_state.value)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        rows = self._conn.execute(
            f"SELECT * FROM company_snapshots {where} "
            f"ORDER BY as_of_date DESC, created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [self._snapshot_from_row(r) for r in rows]

    def get_capital_candidates(
        self, *, as_of: Optional[date] = None
    ) -> list[CompanySnapshot]:
        """
        Return all approved, non-stale snapshots with pack_version >= 1.
        These are the only names eligible for capital-candidate actions per
        docs/PRODUCT_SPEC.md.
        """
        snapshots = self.list_snapshots(reviewer_state=ReviewerState.APPROVED)
        result = []
        seen: set[str] = set()
        for snap in snapshots:
            if snap.company_id in seen:
                continue
            if as_of is not None and snap.as_of_date > as_of:
                continue
            if snap.is_capital_candidate_eligible:
                result.append(snap)
                seen.add(snap.company_id)
        return result

    def get_buckets(self, snapshot_id: str) -> list[ValueBucket]:
        """Load the ValueBuckets for a given snapshot_id from the buckets table."""
        rows = self._conn.execute(
            "SELECT * FROM snapshot_buckets WHERE snapshot_id = ? ORDER BY id",
            (snapshot_id,),
        ).fetchall()
        return [self._bucket_from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # State transitions (insert-only: creates new version)
    # ------------------------------------------------------------------

    def transition_state(
        self,
        snapshot_id: str,
        new_state: ReviewerState,
        *,
        reviewer: str,
        reason: str,
    ) -> CompanySnapshot:
        """
        Transition a snapshot to a new ReviewerState.

        Creates a new snapshot row (insert-only) with:
        - reviewer_state = new_state
        - provenance.parent_snapshot_id = snapshot_id
        - provenance.created_by = reviewer
        - provenance.change_summary = reason

        Returns the new snapshot.
        Raises ValueError if the snapshot does not exist.
        """
        old = self.get_snapshot(snapshot_id)
        if old is None:
            raise ValueError(f"Snapshot {snapshot_id!r} not found.")

        old_state = old.reviewer_state
        new_prov = old.provenance.model_copy(update={
            "parent_snapshot_id": snapshot_id,
            "created_by": reviewer,
            "created_at": datetime.now(timezone.utc),
            "change_summary": reason,
        })
        new_snap = old.model_copy(update={
            "snapshot_id": None,  # triggers default_factory
            "reviewer_state": new_state,
            "provenance": new_prov,
        })
        # frozen=True means model_copy with snapshot_id=None won't re-trigger default_factory;
        # must construct a fresh instance
        import uuid as _uuid
        new_id = str(_uuid.uuid4())
        new_snap = CompanySnapshot(
            **{
                **old.model_dump(),
                "snapshot_id": new_id,
                "reviewer_state": new_state,
                "provenance": new_prov,
            }
        )

        self.insert_snapshot(new_snap)
        self._conn.execute(
            """
            INSERT INTO snapshot_state_log
                (snapshot_id, from_state, to_state, transitioned_by, reason,
                 transitioned_at, new_snapshot_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                old_state.value,
                new_state.value,
                reviewer,
                reason,
                datetime.now(timezone.utc).isoformat(),
                new_id,
            ),
        )
        self._conn.commit()
        return new_snap

    def mark_stale(self, snapshot_id: str, reason: str) -> CompanySnapshot:
        """
        Mark a snapshot as stale.  Creates a new snapshot version with
        reviewer_state=STALE, stale_since=today, stale_reason=reason.
        """
        old = self.get_snapshot(snapshot_id)
        if old is None:
            raise ValueError(f"Snapshot {snapshot_id!r} not found.")

        import uuid as _uuid
        new_id = str(_uuid.uuid4())
        new_prov = old.provenance.model_copy(update={
            "parent_snapshot_id": snapshot_id,
            "created_at": datetime.now(timezone.utc),
            "change_summary": f"Marked stale: {reason}",
        })
        new_snap = CompanySnapshot(
            **{
                **old.model_dump(),
                "snapshot_id": new_id,
                "reviewer_state": ReviewerState.STALE,
                "stale_since": date.today(),
                "stale_reason": reason,
                "provenance": new_prov,
            }
        )
        self.insert_snapshot(new_snap)
        self._conn.execute(
            """
            INSERT INTO snapshot_state_log
                (snapshot_id, from_state, to_state, transitioned_by, reason,
                 transitioned_at, new_snapshot_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                old.reviewer_state.value,
                ReviewerState.STALE.value,
                "system",
                reason,
                datetime.now(timezone.utc).isoformat(),
                new_id,
            ),
        )
        self._conn.commit()
        return new_snap

    def get_state_log(self, snapshot_id: str) -> list[dict]:
        """Return all state transitions for a snapshot, ordered chronologically."""
        rows = self._conn.execute(
            "SELECT * FROM snapshot_state_log WHERE snapshot_id = ? ORDER BY transitioned_at",
            (snapshot_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_snapshot(snapshot: CompanySnapshot) -> dict:
        return {
            "snapshot_id": snapshot.snapshot_id,
            "company_id": snapshot.company_id,
            "company_name": snapshot.company_name,
            "ticker": snapshot.ticker,
            "as_of_date": snapshot.as_of_date.isoformat(),
            "market_cap_millions": snapshot.market_cap_millions,
            "enterprise_value_millions": snapshot.enterprise_value_millions,
            "share_price": snapshot.share_price,
            "cash_millions": snapshot.cash_millions,
            "debt_millions": snapshot.debt_millions,
            "dilution_bridge_json": (
                snapshot.dilution_bridge.model_dump_json()
                if snapshot.dilution_bridge else None
            ),
            "catalysts_json": json.dumps(
                [c.model_dump(mode="json") for c in snapshot.catalysts]
            ),
            "management_flags_json": json.dumps(
                [f.model_dump(mode="json") for f in snapshot.management_flags]
            ),
            "confidence_json": snapshot.confidence.model_dump_json(),
            "provenance_json": snapshot.provenance.model_dump_json(),
            "reviewer_state": snapshot.reviewer_state.value,
            "stale_since": snapshot.stale_since.isoformat() if snapshot.stale_since else None,
            "stale_reason": snapshot.stale_reason,
            "notes": snapshot.notes,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _snapshot_from_row(self, row: sqlite3.Row) -> CompanySnapshot:
        d = dict(row)
        buckets = self.get_buckets(d["snapshot_id"])

        # Partition buckets by type
        modeled = [b for b in buckets if b.bucket_type == "modeled_asset"]
        royalties = [b for b in buckets if b.bucket_type == "royalty"]
        platform = next((b for b in buckets if b.bucket_type == "platform"), None)
        unmodeled = next((b for b in buckets if b.bucket_type == "unmodeled_pipeline"), None)

        dilution_bridge = None
        if d["dilution_bridge_json"]:
            dilution_bridge = DilutionBridge.model_validate_json(d["dilution_bridge_json"])

        catalysts = [
            CatalystEntry(**c)
            for c in json.loads(d["catalysts_json"] or "[]")
        ]
        management_flags = [
            ManagementFlag(**f)
            for f in json.loads(d["management_flags_json"] or "[]")
        ]

        confidence = ConfidenceMetadata.model_validate_json(d["confidence_json"])
        provenance = ProvenanceMetadata.model_validate_json(d["provenance_json"])

        return CompanySnapshot(
            snapshot_id=d["snapshot_id"],
            company_id=d["company_id"],
            company_name=d["company_name"],
            ticker=d["ticker"],
            as_of_date=date.fromisoformat(d["as_of_date"]),
            market_cap_millions=d["market_cap_millions"],
            enterprise_value_millions=d["enterprise_value_millions"],
            share_price=d["share_price"],
            cash_millions=d["cash_millions"],
            debt_millions=d["debt_millions"],
            modeled_assets=modeled,
            royalty_streams=royalties,
            platform_value=platform,
            unmodeled_pipeline=unmodeled,
            dilution_bridge=dilution_bridge,
            catalysts=catalysts,
            management_flags=management_flags,
            confidence=confidence,
            provenance=provenance,
            reviewer_state=ReviewerState(d["reviewer_state"]),
            stale_since=date.fromisoformat(d["stale_since"]) if d["stale_since"] else None,
            stale_reason=d["stale_reason"],
            notes=d["notes"],
        )

    @staticmethod
    def _bucket_from_row(row: sqlite3.Row) -> ValueBucket:
        d = dict(row)
        return ValueBucket(
            bucket_id=d["bucket_id"],
            bucket_type=d["bucket_type"],
            label=d["label"],
            value_millions=d["value_millions"],
            methodology=d["methodology"],
            source_type=d["source_type"],
            source_ref=d["source_ref"],
            as_of_date=date.fromisoformat(d["as_of_date"]),
            corroboration_count=d["corroboration_count"],
            corroboration_refs=json.loads(d["corroboration_refs_json"] or "[]"),
            reviewer=d["reviewer"],
            confidence=d["confidence"],
            last_changed_at=(
                datetime.fromisoformat(d["last_changed_at"])
                if d["last_changed_at"] else None
            ),
            change_reason=d["change_reason"],
            notes=d["notes"],
        )
