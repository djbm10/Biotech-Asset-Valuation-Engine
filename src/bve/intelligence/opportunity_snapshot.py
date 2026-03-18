"""Daily persistence for ranked-opportunity snapshots."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from bve.intelligence.ranking import RankedOpportunity

if TYPE_CHECKING:
    from bve.intelligence.knowledge_layer import KnowledgeStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OpportunitySnapshotRecord(BaseModel):
    """One daily ranking snapshot row."""

    snapshot_date: date
    asset_id: str
    score: float
    mispricing: Optional[float] = None
    confidence: float
    event_type: Optional[str] = None
    rank: int
    run_id: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)


class OpportunitySnapshotStore:
    """SQLite-backed store for daily ranking snapshots."""

    def __init__(self, knowledge_store: "KnowledgeStore") -> None:
        self.knowledge = knowledge_store
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.knowledge._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS opportunity_snapshots (
                snapshot_date TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                score REAL NOT NULL,
                mispricing REAL,
                confidence REAL NOT NULL,
                event_type TEXT,
                rank INTEGER NOT NULL,
                run_id TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(snapshot_date, asset_id)
            )
            """
        )
        self.knowledge._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_opportunity_snapshots_rank
                ON opportunity_snapshots(snapshot_date, rank)
            """
        )
        self.knowledge._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_opportunity_snapshots_asset
                ON opportunity_snapshots(asset_id, snapshot_date)
            """
        )
        self.knowledge._conn.commit()

    @staticmethod
    def from_opportunity(
        opp: RankedOpportunity,
        *,
        snapshot_date: date,
        run_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> OpportunitySnapshotRecord:
        return OpportunitySnapshotRecord(
            snapshot_date=snapshot_date,
            asset_id=opp.asset_id,
            score=float(opp.composite_score),
            mispricing=float(opp.mispricing) if opp.mispricing is not None else None,
            confidence=float(opp.extraction_confidence),
            event_type=opp.signal_event_type,
            rank=int(opp.rank),
            run_id=run_id,
            created_at=created_at or _utcnow(),
        )

    def write_snapshot(self, snapshot: OpportunitySnapshotRecord) -> None:
        self.knowledge._conn.execute(
            """
            INSERT OR REPLACE INTO opportunity_snapshots(
                snapshot_date, asset_id, score, mispricing, confidence,
                event_type, rank, run_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_date.isoformat(),
                snapshot.asset_id,
                snapshot.score,
                snapshot.mispricing,
                snapshot.confidence,
                snapshot.event_type,
                snapshot.rank,
                snapshot.run_id,
                self.knowledge._coerce_datetime(snapshot.created_at).isoformat(),
            ),
        )
        self.knowledge._conn.commit()

    def write_snapshots(
        self,
        opportunities: list[RankedOpportunity],
        *,
        snapshot_date: date,
        run_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> int:
        timestamp = created_at or _utcnow()
        rows = [
            self.from_opportunity(
                opp,
                snapshot_date=snapshot_date,
                run_id=run_id,
                created_at=timestamp,
            )
            for opp in opportunities
        ]
        self.knowledge._conn.executemany(
            """
            INSERT OR REPLACE INTO opportunity_snapshots(
                snapshot_date, asset_id, score, mispricing, confidence,
                event_type, rank, run_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.snapshot_date.isoformat(),
                    row.asset_id,
                    row.score,
                    row.mispricing,
                    row.confidence,
                    row.event_type,
                    row.rank,
                    row.run_id,
                    self.knowledge._coerce_datetime(row.created_at).isoformat(),
                )
                for row in rows
            ],
        )
        self.knowledge._conn.commit()
        return len(rows)

    def get_snapshots(
        self,
        *,
        snapshot_date: Optional[date] = None,
        asset_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        top_n: Optional[int] = None,
        limit: int = 500,
    ) -> list[OpportunitySnapshotRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if snapshot_date is not None:
            clauses.append("snapshot_date = ?")
            params.append(snapshot_date.isoformat())
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if date_from is not None:
            clauses.append("snapshot_date >= ?")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("snapshot_date <= ?")
            params.append(date_to.isoformat())
        if top_n is not None:
            clauses.append("rank <= ?")
            params.append(int(top_n))

        sql = (
            "SELECT snapshot_date, asset_id, score, mispricing, confidence, "
            "event_type, rank, run_id, created_at FROM opportunity_snapshots"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY snapshot_date DESC, rank ASC, asset_id ASC LIMIT ?"
        params.append(limit)

        rows = self.knowledge._conn.execute(sql, params).fetchall()
        return [
            OpportunitySnapshotRecord(
                snapshot_date=date.fromisoformat(row["snapshot_date"]),
                asset_id=row["asset_id"],
                score=float(row["score"]),
                mispricing=float(row["mispricing"]) if row["mispricing"] is not None else None,
                confidence=float(row["confidence"]),
                event_type=row["event_type"],
                rank=int(row["rank"]),
                run_id=row["run_id"],
                created_at=self.knowledge._coerce_datetime(row["created_at"]),
            )
            for row in rows
        ]

    def get_snapshot_map(
        self,
        *,
        snapshot_date: date,
        top_n: Optional[int] = None,
    ) -> dict[str, OpportunitySnapshotRecord]:
        rows = self.get_snapshots(snapshot_date=snapshot_date, top_n=top_n, limit=5000)
        return {row.asset_id: row for row in rows}

    def latest_snapshot_date_before(self, snapshot_date: date) -> Optional[date]:
        row = self.knowledge._conn.execute(
            """
            SELECT MAX(snapshot_date) AS snapshot_date
            FROM opportunity_snapshots
            WHERE snapshot_date < ?
            """,
            (snapshot_date.isoformat(),),
        ).fetchone()
        if row is None or row["snapshot_date"] is None:
            return None
        return date.fromisoformat(row["snapshot_date"])

    def latest_snapshot_date(self) -> Optional[date]:
        row = self.knowledge._conn.execute(
            "SELECT MAX(snapshot_date) AS snapshot_date FROM opportunity_snapshots"
        ).fetchone()
        if row is None or row["snapshot_date"] is None:
            return None
        return date.fromisoformat(row["snapshot_date"])

    def latest_snapshot_date_on_or_before(self, snapshot_date: date) -> Optional[date]:
        row = self.knowledge._conn.execute(
            """
            SELECT MAX(snapshot_date) AS snapshot_date
            FROM opportunity_snapshots
            WHERE snapshot_date <= ?
            """,
            (snapshot_date.isoformat(),),
        ).fetchone()
        if row is None or row["snapshot_date"] is None:
            return None
        return date.fromisoformat(row["snapshot_date"])
