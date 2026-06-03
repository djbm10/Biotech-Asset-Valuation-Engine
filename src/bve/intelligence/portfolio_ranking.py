"""
Wave 4C — Portfolio Ranking + Clustering.

Groups tracked assets into indication clusters using KnowledgeGraph edges,
applies analyst-configurable portfolio constraints, and returns a ranked,
clustered view of opportunities.

Flow
----
1. ``OpportunityCluster`` — one cluster of assets sharing a KG edge type
   (e.g. SAME_INDICATION).  Carries combined stats and a flag for whether
   any member is pending review.

2. ``AssetClusterer.cluster(store, asset_ids, edge_type)`` — builds clusters
   from KG ``same_indication`` (or another specified edge type) edges using a
   Union-Find algorithm.  Assets with no KG node land in singleton clusters so
   nothing is silently dropped.

3. ``PortfolioConstraints`` — configurable filter thresholds:
   - ``min_confidence``: exclude diffs extracted with confidence below this
   - ``max_queue_age_days``: exclude diffs older than N days
   - ``min_abs_delta_npv_millions``: exclude diffs with |ΔNPV| below threshold
   - ``require_accepted_review``: if True, only include accepted diffs

4. ``PortfolioRankingEngine.rank(store, asset_ids)`` — applies constraints,
   scores assets, clusters them, and returns ``PortfolioRankingResult``.

CLI
---
``bve-portfolio-rank`` calls ``PortfolioRankingEngine.rank()`` and prints a
ranked cluster table.

Usage
-----
    bve-portfolio-rank --db outputs/intelligence_phase2/knowledge.db
    bve-portfolio-rank --db knowledge.db --min-confidence 0.7 --top-n 10
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Step 1 — OpportunityCluster model
# ---------------------------------------------------------------------------


class OpportunityCluster(BaseModel):
    """
    A group of assets linked by a common KG edge type.

    Attributes
    ----------
    cluster_id:
        Stable identifier formed from sorted asset_ids.
    cluster_label:
        Human-readable label — the shared indication/target/mechanism name
        derived from the KG node, or a concatenation of asset_ids for singletons.
    edge_type:
        The KG edge type that groups these assets (e.g. ``"same_indication"``).
        ``"singleton"`` for assets with no KG node or no shared edges.
    asset_ids:
        All asset_ids in the cluster (unsorted at input; stored sorted).
    n_assets:
        Number of assets in the cluster.
    combined_delta_npv_millions:
        Sum of the most recent diff's delta_npv for each member asset.
    combined_confidence_weighted_delta_npv_millions:
        Sum of delta_npv × extraction_confidence across member assets.
    n_pending_review:
        Count of member assets with at least one unreviewed diff.
    top_asset_id:
        The asset_id with the highest |combined_delta_npv| in this cluster.
    """

    cluster_id: str
    cluster_label: str
    edge_type: str = "singleton"
    asset_ids: list[str] = Field(default_factory=list)
    n_assets: int = 0
    combined_delta_npv_millions: float = 0.0
    combined_confidence_weighted_delta_npv_millions: float = 0.0
    n_pending_review: int = 0
    top_asset_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Step 2 — AssetClusterer (Union-Find over KG edges)
# ---------------------------------------------------------------------------


class _UnionFind:
    """Simple path-compressed Union-Find."""

    def __init__(self, items: list[str]) -> None:
        self._parent: dict[str, str] = {x: x for x in items}

    def find(self, x: str) -> str:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path compression
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra

    def groups(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for x in self._parent:
            root = self.find(x)
            result.setdefault(root, []).append(x)
        return result


class AssetClusterer:
    """
    Builds ``OpportunityCluster`` objects from KG edges.

    Assets that share at least one edge of ``edge_type`` are grouped together.
    Assets with no KG node (or no shared edges) become singleton clusters.

    Parameters
    ----------
    edge_type:
        KG edge type to cluster on.  Default: ``"same_indication"``.
    """

    def __init__(self, *, edge_type: str = "same_indication") -> None:
        self.edge_type = edge_type

    def cluster(
        self,
        store: "KnowledgeStore",  # type: ignore[name-defined]  # noqa: F821
        asset_ids: list[str],
        *,
        asset_stats: Optional[dict[str, dict]] = None,
    ) -> list[OpportunityCluster]:
        """
        Group *asset_ids* into clusters and return them sorted by
        |combined_delta_npv| descending.

        Parameters
        ----------
        store:
            Live ``KnowledgeStore`` instance.
        asset_ids:
            Distinct asset identifiers to cluster.
        asset_stats:
            Pre-computed per-asset stats dict, keyed by asset_id.
            Each value should have: ``delta_npv``, ``confidence_weighted_delta``,
            ``has_pending`` (bool).
            If omitted, all stats default to zero.
        """
        if not asset_ids:
            return []

        asset_stats = asset_stats or {}
        uf = _UnionFind(asset_ids)

        # Resolve asset_id → kg_node_id (external_id on the asset node)
        # and build a reverse map node_id → asset_id.
        node_to_asset: dict[str, str] = {}
        asset_to_node: dict[str, Optional[str]] = {}
        for asset_id in asset_ids:
            row = store._conn.execute(
                "SELECT node_id, name FROM kg_nodes WHERE external_id = ? "
                "AND node_type = 'asset' LIMIT 1",
                (asset_id,),
            ).fetchone()
            if row:
                node_to_asset[row["node_id"]] = asset_id
                asset_to_node[asset_id] = row["node_id"]
            else:
                asset_to_node[asset_id] = None

        # Query all edges of the requested type between known nodes
        known_node_ids = [nid for nid in node_to_asset if nid]
        if known_node_ids:
            placeholders = ",".join("?" * len(known_node_ids))
            edges = store._conn.execute(
                f"""
                SELECT source_node_id, target_node_id
                FROM kg_edges
                WHERE edge_type = ?
                  AND source_node_id IN ({placeholders})
                  AND target_node_id IN ({placeholders})
                """,
                [self.edge_type, *known_node_ids, *known_node_ids],
            ).fetchall()
            for edge in edges:
                src_asset = node_to_asset.get(edge["source_node_id"])
                tgt_asset = node_to_asset.get(edge["target_node_id"])
                if src_asset and tgt_asset and src_asset in asset_ids and tgt_asset in asset_ids:
                    uf.union(src_asset, tgt_asset)

        # Build clusters from Union-Find groups
        groups = uf.groups()
        clusters: list[OpportunityCluster] = []
        for root, members in groups.items():
            sorted_members = sorted(members)
            cluster_id = "|".join(sorted_members)

            # Derive label from the indication node linked to the cluster members
            label = self._cluster_label(store, sorted_members, asset_to_node)

            # Aggregate stats
            combined_delta = 0.0
            combined_weighted = 0.0
            n_pending = 0
            top_asset: Optional[str] = None
            top_delta = 0.0

            for asset_id in sorted_members:
                stats = asset_stats.get(asset_id, {})
                d = stats.get("delta_npv", 0.0)
                w = stats.get("confidence_weighted_delta", 0.0)
                combined_delta += d
                combined_weighted += w
                if stats.get("has_pending", False):
                    n_pending += 1
                if top_asset is None or abs(d) > abs(top_delta):
                    top_asset = asset_id
                    top_delta = d

            edge_label = self.edge_type if len(sorted_members) > 1 else "singleton"
            clusters.append(OpportunityCluster(
                cluster_id=cluster_id,
                cluster_label=label,
                edge_type=edge_label,
                asset_ids=sorted_members,
                n_assets=len(sorted_members),
                combined_delta_npv_millions=round(combined_delta, 2),
                combined_confidence_weighted_delta_npv_millions=round(combined_weighted, 2),
                n_pending_review=n_pending,
                top_asset_id=top_asset,
            ))

        # Sort by |combined_delta_npv| descending
        clusters.sort(key=lambda c: abs(c.combined_delta_npv_millions), reverse=True)
        return clusters

    def _cluster_label(
        self,
        store: "KnowledgeStore",  # type: ignore[name-defined]  # noqa: F821
        asset_ids: list[str],
        asset_to_node: dict[str, Optional[str]],
    ) -> str:
        """
        Derive a human-readable cluster label from the indication node
        linked to any member asset, or fall back to the asset_ids list.
        """
        for asset_id in asset_ids:
            node_id = asset_to_node.get(asset_id)
            if not node_id:
                continue
            # Find a TREATS edge to an indication node
            ind_row = store._conn.execute(
                """
                SELECT n.name FROM kg_nodes n
                JOIN kg_edges e ON n.node_id = e.target_node_id
                WHERE e.source_node_id = ? AND e.edge_type = 'treats'
                  AND n.node_type = 'indication'
                LIMIT 1
                """,
                (node_id,),
            ).fetchone()
            if ind_row:
                return ind_row["name"]
        return " / ".join(asset_ids[:3]) + ("…" if len(asset_ids) > 3 else "")


# ---------------------------------------------------------------------------
# Step 3 — PortfolioConstraints model
# ---------------------------------------------------------------------------


class PortfolioConstraints(BaseModel):
    """
    Analyst-configurable thresholds that filter diffs before ranking.

    Attributes
    ----------
    min_confidence:
        Exclude diffs whose linked signal has extraction_confidence below this.
        Set to 0.0 (default) to disable.
    max_queue_age_days:
        Exclude diffs created more than N calendar days ago.
        None (default) = no age filter.
    min_abs_delta_npv_millions:
        Exclude diffs with |ΔNPV| below this threshold.
        None (default) = no magnitude filter.
    require_accepted_review:
        If True, only include diffs that have an accepted review_decision.
        If False (default), include all diffs (pending + accepted).
    max_assets:
        Cap the number of distinct assets returned.  None = no cap.
    cluster_edge_type:
        KG edge type used by ``AssetClusterer``.  Default: ``"same_indication"``.
    top_n:
        Number of top-ranked clusters to include in the result.
    """

    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    max_queue_age_days: Optional[int] = Field(default=None, ge=1)
    min_abs_delta_npv_millions: Optional[float] = Field(default=None, ge=0.0)
    require_accepted_review: bool = False
    max_assets: Optional[int] = Field(default=None, ge=1)
    max_assets_per_indication: Optional[int] = Field(default=None, ge=1)
    max_assets_per_company: Optional[int] = Field(default=None, ge=1)
    cluster_edge_type: str = "same_indication"
    top_n: int = Field(default=10, ge=1)


# ---------------------------------------------------------------------------
# Step 4 — PortfolioRankingEngine
# ---------------------------------------------------------------------------


class PortfolioRankingResult(BaseModel):
    """Full output of one portfolio ranking run."""

    ranked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    constraints: PortfolioConstraints
    clusters: list[OpportunityCluster] = Field(default_factory=list)

    # Filter telemetry
    n_diffs_total: int = 0
    n_filtered_confidence: int = 0
    n_filtered_age: int = 0
    n_filtered_magnitude: int = 0
    n_filtered_not_accepted: int = 0
    n_diffs_passed: int = 0
    n_assets_evaluated: int = 0


class PortfolioRankingEngine:
    """
    Applies ``PortfolioConstraints``, scores assets, and clusters them.

    Parameters
    ----------
    constraints:
        Filter + config parameters.  Defaults to ``PortfolioConstraints()``.
    """

    def __init__(self, constraints: Optional[PortfolioConstraints] = None) -> None:
        self.constraints = constraints or PortfolioConstraints()

    def rank(
        self,
        store: "KnowledgeStore",  # type: ignore[name-defined]  # noqa: F821
        *,
        asset_ids: Optional[list[str]] = None,
    ) -> PortfolioRankingResult:
        """
        Load diffs from *store*, apply constraints, cluster, and return results.

        Parameters
        ----------
        store:
            Live ``KnowledgeStore`` instance.
        asset_ids:
            If provided, restrict to these assets only.
            If None, rank all assets with valuation diffs.
        """
        c = self.constraints
        result = PortfolioRankingResult(constraints=c)

        # ---- Load all diffs (optionally restricted by asset_ids) ----
        if asset_ids:
            placeholders = ",".join("?" * len(asset_ids))
            diff_rows = store._conn.execute(
                f"""
                SELECT
                    vd.run_id, vd.asset_id, vd.event_id, vd.delta_npv, vd.created_at
                FROM valuation_diffs vd
                WHERE vd.asset_id IN ({placeholders})
                ORDER BY vd.created_at DESC
                """,
                asset_ids,
            ).fetchall()
        else:
            diff_rows = store._conn.execute(
                """
                SELECT run_id, asset_id, event_id, delta_npv, created_at
                FROM valuation_diffs
                ORDER BY created_at DESC
                """
            ).fetchall()

        result.n_diffs_total = len(diff_rows)

        # ---- Fetch accepted run_ids for the require_accepted_review filter ----
        accepted_run_ids: set[str] = set()
        if c.require_accepted_review:
            rows = store._conn.execute(
                "SELECT run_id FROM review_decisions WHERE decision = 'accepted'"
            ).fetchall()
            accepted_run_ids = {r["run_id"] for r in rows}

        # ---- Fetch signal confidence for each diff ----
        def _get_confidence(event_id: Optional[str]) -> Optional[float]:
            if not event_id:
                return None
            row = store._conn.execute(
                "SELECT payload_json FROM structured_signals WHERE event_id = ? LIMIT 1",
                (event_id,),
            ).fetchone()
            if row:
                try:
                    return json.loads(row["payload_json"]).get("extraction_confidence")
                except Exception:
                    pass
            return None

        # ---- Apply filters; aggregate per-asset best diff ----
        now_utc = datetime.now(timezone.utc)
        cutoff_dt = (
            now_utc - timedelta(days=c.max_queue_age_days)
            if c.max_queue_age_days is not None
            else None
        )

        # asset_id → best diff stats (highest |ΔNPV| that passes all filters)
        asset_best: dict[str, dict] = {}
        # Track which run_ids have a pending review (no decision row)
        reviewed_run_ids_all: set[str] = set()

        rev_rows = store._conn.execute("SELECT run_id FROM review_decisions").fetchall()
        reviewed_run_ids_all = {r["run_id"] for r in rev_rows}

        for row in diff_rows:
            run_id    = row["run_id"]
            asset_id  = row["asset_id"] or ""
            event_id  = row["event_id"]
            delta_npv = row["delta_npv"] or 0.0
            created   = row["created_at"] or ""

            # Filter: require_accepted_review
            if c.require_accepted_review and run_id not in accepted_run_ids:
                result.n_filtered_not_accepted += 1
                continue

            # Filter: age
            if cutoff_dt is not None:
                try:
                    created_dt = datetime.fromisoformat(created[:19]).replace(tzinfo=timezone.utc)
                    if created_dt < cutoff_dt:
                        result.n_filtered_age += 1
                        continue
                except Exception:
                    pass

            # Filter: magnitude
            if c.min_abs_delta_npv_millions is not None and abs(delta_npv) < c.min_abs_delta_npv_millions:
                result.n_filtered_magnitude += 1
                continue

            # Filter: confidence
            conf = _get_confidence(event_id)
            if conf is not None and conf < c.min_confidence:
                result.n_filtered_confidence += 1
                continue

            conf_used = conf if conf is not None else 1.0
            weighted = delta_npv * conf_used

            # Keep the diff with highest |ΔNPV| per asset
            existing = asset_best.get(asset_id)
            if existing is None or abs(delta_npv) > abs(existing["delta_npv"]):
                asset_best[asset_id] = {
                    "delta_npv": delta_npv,
                    "confidence_weighted_delta": weighted,
                    "confidence": conf_used,
                    "has_pending": run_id not in reviewed_run_ids_all,
                }

        result.n_diffs_passed = sum(1 for _ in asset_best)
        result.n_assets_evaluated = len(asset_best)

        # Apply max_assets cap
        all_asset_ids = list(asset_best.keys())
        all_asset_ids.sort(key=lambda a: (-abs(asset_best[a]["delta_npv"]), a))

        selected_assets: list[str] = []
        company_counts: dict[str, int] = {}
        indication_counts: dict[str, int] = {}
        for asset_id in all_asset_ids:
            company_id = self._company_for_asset(store, asset_id) or "__unknown_company__"
            indication_key = self._indication_key_for_asset(store, asset_id)

            if (
                c.max_assets_per_company is not None
                and company_counts.get(company_id, 0) >= c.max_assets_per_company
            ):
                continue
            if (
                c.max_assets_per_indication is not None
                and indication_counts.get(indication_key, 0) >= c.max_assets_per_indication
            ):
                continue

            selected_assets.append(asset_id)
            company_counts[company_id] = company_counts.get(company_id, 0) + 1
            indication_counts[indication_key] = indication_counts.get(indication_key, 0) + 1
            if c.max_assets is not None and len(selected_assets) >= c.max_assets:
                break

        # ---- Cluster ----
        clusterer = AssetClusterer(edge_type=c.cluster_edge_type)
        clusters = clusterer.cluster(store, selected_assets, asset_stats=asset_best)

        result.clusters = clusters[: c.top_n]
        return result

    @staticmethod
    def _company_for_asset(
        store: "KnowledgeStore",  # type: ignore[name-defined]  # noqa: F821
        asset_id: str,
    ) -> Optional[str]:
        row = store._conn.execute(
            """
            SELECT company_id
            FROM events
            WHERE asset_id = ?
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        return row["company_id"] if row else None

    @staticmethod
    def _indication_key_for_asset(
        store: "KnowledgeStore",  # type: ignore[name-defined]  # noqa: F821
        asset_id: str,
    ) -> str:
        row = store._conn.execute(
            """
            SELECT n.name
            FROM kg_nodes a
            JOIN kg_edges e ON a.node_id = e.source_node_id
            JOIN kg_nodes n ON n.node_id = e.target_node_id
            WHERE a.node_type = 'asset'
              AND a.external_id = ?
              AND e.edge_type = 'treats'
              AND n.node_type = 'indication'
            LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if row:
            return str(row["name"])
        return f"__asset__:{asset_id}"


# ---------------------------------------------------------------------------
# Convenience: load PortfolioConstraints from a YAML dict
# ---------------------------------------------------------------------------

def constraints_from_dict(d: dict) -> PortfolioConstraints:
    """Build ``PortfolioConstraints`` from a plain dict (e.g. parsed from YAML)."""
    return PortfolioConstraints.model_validate(d)
