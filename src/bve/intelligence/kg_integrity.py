"""Knowledge graph integrity checks for weekly health validation."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_graph import NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KGIntegrityReport(BaseModel):
    """Summary of graph-level data quality checks."""

    checked_at: datetime = Field(default_factory=_utcnow)
    n_nodes: int = 0
    n_edges: int = 0
    orphan_edges: list[str] = Field(default_factory=list)
    duplicate_nodes: list[str] = Field(default_factory=list)
    invalid_confidence: list[str] = Field(default_factory=list)
    missing_asset_nodes: list[str] = Field(default_factory=list)
    passed: bool = True


class KGIntegrityChecker:
    """Runs consistency checks over kg_nodes/kg_edges."""

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    def check(self, watchlist_asset_ids: list[str]) -> KGIntegrityReport:
        conn = self._store._conn  # noqa: SLF001 - integrity checker is store-adjacent

        n_nodes = int(conn.execute("SELECT COUNT(*) AS n FROM kg_nodes").fetchone()["n"])
        n_edges = int(conn.execute("SELECT COUNT(*) AS n FROM kg_edges").fetchone()["n"])

        orphan_rows = conn.execute(
            """
            SELECT e.edge_id
            FROM kg_edges e
            LEFT JOIN kg_nodes src ON src.node_id = e.source_node_id
            LEFT JOIN kg_nodes dst ON dst.node_id = e.target_node_id
            WHERE src.node_id IS NULL OR dst.node_id IS NULL
            ORDER BY e.edge_id
            """
        ).fetchall()
        orphan_edges = [str(r["edge_id"]) for r in orphan_rows]

        duplicate_rows = conn.execute(
            """
            SELECT node_type, external_id, COUNT(*) AS n
            FROM kg_nodes
            WHERE external_id IS NOT NULL AND external_id <> ''
            GROUP BY node_type, external_id
            HAVING COUNT(*) > 1
            ORDER BY n DESC, node_type, external_id
            """
        ).fetchall()
        duplicate_nodes = [
            f"{row['node_type']}::{row['external_id']} (count={int(row['n'])})"
            for row in duplicate_rows
        ]

        invalid_rows = conn.execute(
            """
            SELECT edge_id
            FROM kg_edges
            WHERE confidence < 0.0 OR confidence > 1.0
            ORDER BY edge_id
            """
        ).fetchall()
        invalid_confidence = [str(r["edge_id"]) for r in invalid_rows]

        missing_asset_nodes: list[str] = []
        for asset_id in sorted(set(watchlist_asset_ids)):
            row = conn.execute(
                """
                SELECT 1
                FROM kg_nodes
                WHERE node_type = ? AND external_id = ?
                LIMIT 1
                """,
                (NodeType.ASSET.value, asset_id),
            ).fetchone()
            if row is None:
                missing_asset_nodes.append(asset_id)

        passed = (
            len(orphan_edges) == 0
            and len(duplicate_nodes) == 0
            and len(invalid_confidence) == 0
        )

        return KGIntegrityReport(
            checked_at=_utcnow(),
            n_nodes=n_nodes,
            n_edges=n_edges,
            orphan_edges=orphan_edges,
            duplicate_nodes=duplicate_nodes,
            invalid_confidence=invalid_confidence,
            missing_asset_nodes=missing_asset_nodes,
            passed=passed,
        )
