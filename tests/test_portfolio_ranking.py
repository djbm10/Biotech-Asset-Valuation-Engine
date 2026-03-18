"""
Wave 4C — Tests for portfolio ranking + clustering.

Coverage:
  - OpportunityCluster model (Step 1)
  - AssetClusterer: singleton clusters, KG-edge clusters, Union-Find transitive (Step 2)
  - PortfolioConstraints defaults and validation (Step 3)
  - PortfolioRankingEngine: empty store, constraint filters, cluster output (Step 4)
  - constraints_from_dict helper
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.portfolio_ranking import (
    AssetClusterer,
    OpportunityCluster,
    PortfolioConstraints,
    PortfolioRankingEngine,
    PortfolioRankingResult,
    constraints_from_dict,
)
from bve.intelligence.schemas.runs import ReviewDecision


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _now_iso(*, offset_days: int = 0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=offset_days)
    return dt.isoformat()


def _insert_diff(
    store: KnowledgeStore,
    *,
    run_id: str | None = None,
    asset_id: str = "asset-A",
    event_id: str | None = None,
    delta_npv: float = 50.0,
    created_days_ago: int = 0,
) -> tuple[str, str]:
    """Insert a valuation_diff. Returns (run_id, event_id)."""
    run_id = run_id or str(uuid.uuid4())
    event_id = event_id or str(uuid.uuid4())
    created = _now_iso(offset_days=-created_days_ago)
    payload = {
        "run_id": run_id, "event_id": event_id, "asset_id": asset_id,
        "valuation_before": {"rnpv_millions": 100.0},
        "valuation_after":  {"rnpv_millions": 100.0 + delta_npv},
        "delta_npv": delta_npv, "created_at": created,
        "valuation_delta": {}, "assumptions_changed": [], "applied_overrides": {},
    }
    store._conn.execute(
        """
        INSERT INTO valuation_diffs
            (run_id, asset_id, event_id, delta_npv, created_at, payload_json, source_trace_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, asset_id, event_id, delta_npv, created,
         json.dumps(payload),
         json.dumps({"source_type": "test", "source_ref": "test"})),
    )
    store._conn.commit()
    return run_id, event_id


def _insert_event(store: KnowledgeStore, *, event_id: str, asset_id: str, company_id: str) -> None:
    payload = {"id": event_id, "asset_id": asset_id, "company_id": company_id}
    store._conn.execute(
        """
        INSERT INTO events
            (id, company_id, asset_id, event_type, observed_at, payload_json, source_trace_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            company_id,
            asset_id,
            "trial_readout",
            _now_iso(),
            json.dumps(payload),
            json.dumps({"source_type": "test", "source_ref": "test"}),
        ),
    )
    store._conn.commit()


def _insert_signal(
    store: KnowledgeStore,
    event_id: str,
    *,
    asset_id: str = "asset-A",
    confidence: float = 0.85,
) -> None:
    payload = {
        "id": str(uuid.uuid4()), "event_id": event_id, "asset_id": asset_id,
        "company_id": "co-001", "event_type": "trial_readout",
        "signal_date": "2025-01-15", "extraction_confidence": confidence,
    }
    store._conn.execute(
        """
        INSERT INTO structured_signals
            (id, extraction_result_id, event_id, company_id, asset_id, event_type,
             signal_date, payload_json, source_trace_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (payload["id"], str(uuid.uuid4()), event_id, "co-001", asset_id, "trial_readout",
         "2025-01-15", json.dumps(payload),
         json.dumps({"source_type": "test", "source_ref": "test"}),
         _now_iso()),
    )
    store._conn.commit()


def _accept_diff(store: KnowledgeStore, run_id: str, *, asset_id: str = "asset-A") -> None:
    rec = ReviewDecision(
        id=str(uuid.uuid4()), proposal_id=run_id, run_id=run_id,
        decision="accepted", reviewer_id="analyst",
        reviewed_at=datetime.now(timezone.utc), rationale="OK",
    )
    store.add_review_decision(
        rec, company_id=None, asset_id=asset_id,
        source_trace=SourceTrace(source_type="test", source_ref="test"),
    )


def _add_kg_asset_node(store: KnowledgeStore, asset_id: str, name: str | None = None) -> KGNode:
    node = KGNode(
        node_type=NodeType.ASSET,
        name=name or asset_id,
        external_id=asset_id,
    )
    return store.add_node(node)


def _add_same_indication_edge(
    store: KnowledgeStore, node_a: KGNode, node_b: KGNode
) -> None:
    store.add_edge(KGEdge(
        source_node_id=node_a.node_id,
        target_node_id=node_b.node_id,
        edge_type=EdgeType.SAME_INDICATION,
    ))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store() -> KnowledgeStore:
    s = KnowledgeStore(db_path=":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Step 1: OpportunityCluster model
# ---------------------------------------------------------------------------

class TestOpportunityClusterModel:
    def test_defaults(self) -> None:
        cl = OpportunityCluster(cluster_id="a|b", cluster_label="NSCLC")
        assert cl.edge_type == "singleton"
        assert cl.n_assets == 0
        assert cl.combined_delta_npv_millions == 0.0
        assert cl.combined_confidence_weighted_delta_npv_millions == 0.0
        assert cl.n_pending_review == 0
        assert cl.top_asset_id is None

    def test_fields_set(self) -> None:
        cl = OpportunityCluster(
            cluster_id="x",
            cluster_label="Oncology",
            edge_type="same_indication",
            asset_ids=["A", "B"],
            n_assets=2,
            combined_delta_npv_millions=130.0,
            combined_confidence_weighted_delta_npv_millions=110.0,
            n_pending_review=1,
            top_asset_id="A",
        )
        assert cl.n_assets == 2
        assert cl.combined_delta_npv_millions == 130.0


# ---------------------------------------------------------------------------
# Step 2: AssetClusterer
# ---------------------------------------------------------------------------

class TestAssetClustererSingletons:
    def test_no_kg_nodes_all_singletons(self, store: KnowledgeStore) -> None:
        clusterer = AssetClusterer()
        clusters = clusterer.cluster(store, ["A", "B", "C"])
        assert len(clusters) == 3
        for cl in clusters:
            assert cl.n_assets == 1
            assert cl.edge_type == "singleton"

    def test_empty_asset_list(self, store: KnowledgeStore) -> None:
        clusterer = AssetClusterer()
        assert clusterer.cluster(store, []) == []

    def test_single_asset_singleton(self, store: KnowledgeStore) -> None:
        clusters = AssetClusterer().cluster(store, ["only"])
        assert len(clusters) == 1
        assert clusters[0].asset_ids == ["only"]

    def test_singleton_label_is_asset_id(self, store: KnowledgeStore) -> None:
        clusters = AssetClusterer().cluster(store, ["asset-X"])
        assert "asset-X" in clusters[0].cluster_label


class TestAssetClustererWithKG:
    def test_two_assets_same_indication_grouped(self, store: KnowledgeStore) -> None:
        na = _add_kg_asset_node(store, "A")
        nb = _add_kg_asset_node(store, "B")
        _add_same_indication_edge(store, na, nb)
        clusters = AssetClusterer().cluster(store, ["A", "B"])
        assert len(clusters) == 1
        assert set(clusters[0].asset_ids) == {"A", "B"}
        assert clusters[0].edge_type == "same_indication"

    def test_unlinked_assets_stay_separate(self, store: KnowledgeStore) -> None:
        _add_kg_asset_node(store, "A")
        _add_kg_asset_node(store, "B")
        # No edge added
        clusters = AssetClusterer().cluster(store, ["A", "B"])
        assert len(clusters) == 2

    def test_transitive_grouping(self, store: KnowledgeStore) -> None:
        """A–B and B–C edges → A, B, C in same cluster."""
        na = _add_kg_asset_node(store, "A")
        nb = _add_kg_asset_node(store, "B")
        nc = _add_kg_asset_node(store, "C")
        _add_same_indication_edge(store, na, nb)
        _add_same_indication_edge(store, nb, nc)
        clusters = AssetClusterer().cluster(store, ["A", "B", "C"])
        assert len(clusters) == 1
        assert set(clusters[0].asset_ids) == {"A", "B", "C"}

    def test_mixed_linked_and_unlinked(self, store: KnowledgeStore) -> None:
        """A–B linked, C is singleton."""
        na = _add_kg_asset_node(store, "A")
        nb = _add_kg_asset_node(store, "B")
        _add_same_indication_edge(store, na, nb)
        clusters = AssetClusterer().cluster(store, ["A", "B", "C"])
        assert len(clusters) == 2
        sizes = sorted(cl.n_assets for cl in clusters)
        assert sizes == [1, 2]

    def test_asset_stats_propagated(self, store: KnowledgeStore) -> None:
        na = _add_kg_asset_node(store, "A")
        nb = _add_kg_asset_node(store, "B")
        _add_same_indication_edge(store, na, nb)
        stats = {
            "A": {"delta_npv": 80.0, "confidence_weighted_delta": 72.0, "has_pending": True},
            "B": {"delta_npv": 40.0, "confidence_weighted_delta": 36.0, "has_pending": False},
        }
        clusters = AssetClusterer().cluster(store, ["A", "B"], asset_stats=stats)
        cl = clusters[0]
        assert cl.combined_delta_npv_millions == pytest.approx(120.0)
        assert cl.combined_confidence_weighted_delta_npv_millions == pytest.approx(108.0)
        assert cl.n_pending_review == 1
        assert cl.top_asset_id == "A"

    def test_sorted_by_abs_combined_delta(self, store: KnowledgeStore) -> None:
        """Clusters ordered by |combined_delta_npv| desc."""
        stats = {
            "A": {"delta_npv": 30.0, "confidence_weighted_delta": 30.0, "has_pending": False},
            "B": {"delta_npv": 90.0, "confidence_weighted_delta": 90.0, "has_pending": False},
        }
        clusters = AssetClusterer().cluster(store, ["A", "B"], asset_stats=stats)
        deltas = [abs(cl.combined_delta_npv_millions) for cl in clusters]
        assert deltas == sorted(deltas, reverse=True)

    def test_cluster_label_from_indication_node(self, store: KnowledgeStore) -> None:
        na = _add_kg_asset_node(store, "A")
        nb = _add_kg_asset_node(store, "B")
        _add_same_indication_edge(store, na, nb)

        # Add an indication node linked by TREATS
        ind_node = store.add_node(KGNode(
            node_type=NodeType.INDICATION,
            name="Non-Small Cell Lung Cancer",
        ))
        store.add_edge(KGEdge(
            source_node_id=na.node_id,
            target_node_id=ind_node.node_id,
            edge_type=EdgeType.TREATS,
        ))
        clusters = AssetClusterer().cluster(store, ["A", "B"])
        assert "Non-Small Cell Lung Cancer" in clusters[0].cluster_label


# ---------------------------------------------------------------------------
# Step 3: PortfolioConstraints
# ---------------------------------------------------------------------------

class TestPortfolioConstraints:
    def test_defaults(self) -> None:
        c = PortfolioConstraints()
        assert c.min_confidence == 0.0
        assert c.max_queue_age_days is None
        assert c.min_abs_delta_npv_millions is None
        assert c.require_accepted_review is False
        assert c.max_assets is None
        assert c.cluster_edge_type == "same_indication"
        assert c.top_n == 10

    def test_custom_values(self) -> None:
        c = PortfolioConstraints(
            min_confidence=0.7,
            max_queue_age_days=30,
            min_abs_delta_npv_millions=25.0,
            require_accepted_review=True,
            max_assets=5,
            top_n=3,
        )
        assert c.min_confidence == pytest.approx(0.7)
        assert c.max_queue_age_days == 30
        assert c.min_abs_delta_npv_millions == pytest.approx(25.0)

    def test_min_confidence_bounds(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PortfolioConstraints(min_confidence=1.5)
        with pytest.raises(ValidationError):
            PortfolioConstraints(min_confidence=-0.1)

    def test_constraints_from_dict(self) -> None:
        c = constraints_from_dict({"min_confidence": 0.6, "top_n": 5})
        assert c.min_confidence == pytest.approx(0.6)
        assert c.top_n == 5


# ---------------------------------------------------------------------------
# Step 4: PortfolioRankingEngine
# ---------------------------------------------------------------------------

class TestPortfolioRankingEngineEmpty:
    def test_empty_store(self, store: KnowledgeStore) -> None:
        engine = PortfolioRankingEngine()
        result = engine.rank(store)
        assert isinstance(result, PortfolioRankingResult)
        assert result.n_diffs_total == 0
        assert result.clusters == []

    def test_result_has_ranked_at(self, store: KnowledgeStore) -> None:
        result = PortfolioRankingEngine().rank(store)
        assert result.ranked_at.tzinfo is not None

    def test_constraints_echoed(self, store: KnowledgeStore) -> None:
        c = PortfolioConstraints(min_confidence=0.5)
        result = PortfolioRankingEngine(constraints=c).rank(store)
        assert result.constraints.min_confidence == pytest.approx(0.5)


class TestPortfolioRankingEngineBasic:
    def test_single_asset_single_cluster(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-1", asset_id="A", delta_npv=80.0)
        result = PortfolioRankingEngine().rank(store)
        assert len(result.clusters) == 1
        assert result.clusters[0].asset_ids == ["A"]
        assert result.n_assets_evaluated == 1

    def test_multiple_assets_singleton_clusters(self, store: KnowledgeStore) -> None:
        for i, a in enumerate(["A", "B", "C"]):
            _insert_diff(store, run_id=f"run-{i}", asset_id=a, delta_npv=float(i * 10 + 10))
        result = PortfolioRankingEngine().rank(store)
        assert len(result.clusters) == 3
        assert result.n_assets_evaluated == 3

    def test_max_assets_per_company_cap(self, store: KnowledgeStore) -> None:
        _, e1 = _insert_diff(store, run_id="run-a1", asset_id="A1", delta_npv=90.0)
        _, e2 = _insert_diff(store, run_id="run-a2", asset_id="A2", delta_npv=80.0)
        _, e3 = _insert_diff(store, run_id="run-b1", asset_id="B1", delta_npv=70.0)
        _insert_event(store, event_id=e1, asset_id="A1", company_id="co-A")
        _insert_event(store, event_id=e2, asset_id="A2", company_id="co-A")
        _insert_event(store, event_id=e3, asset_id="B1", company_id="co-B")
        engine = PortfolioRankingEngine(
            constraints=PortfolioConstraints(max_assets_per_company=1, max_assets=10)
        )
        result = engine.rank(store)
        kept_assets = sorted([a for c in result.clusters for a in c.asset_ids])
        assert kept_assets == ["A1", "B1"]

    def test_max_assets_per_indication_cap(self, store: KnowledgeStore) -> None:
        for run_id, asset_id, delta in [
            ("run-a1", "A1", 95.0),
            ("run-a2", "A2", 85.0),
            ("run-b1", "B1", 75.0),
        ]:
            _, event_id = _insert_diff(store, run_id=run_id, asset_id=asset_id, delta_npv=delta)
            _insert_event(store, event_id=event_id, asset_id=asset_id, company_id=f"co-{asset_id}")

        a1 = _add_kg_asset_node(store, "A1")
        a2 = _add_kg_asset_node(store, "A2")
        b1 = _add_kg_asset_node(store, "B1")
        ind_x = store.add_node(KGNode(node_type=NodeType.INDICATION, name="ind-x"))
        ind_y = store.add_node(KGNode(node_type=NodeType.INDICATION, name="ind-y"))
        store.add_edge(
            KGEdge(source_node_id=a1.node_id, target_node_id=ind_x.node_id, edge_type=EdgeType.TREATS)
        )
        store.add_edge(
            KGEdge(source_node_id=a2.node_id, target_node_id=ind_x.node_id, edge_type=EdgeType.TREATS)
        )
        store.add_edge(
            KGEdge(source_node_id=b1.node_id, target_node_id=ind_y.node_id, edge_type=EdgeType.TREATS)
        )

        engine = PortfolioRankingEngine(
            constraints=PortfolioConstraints(max_assets_per_indication=1, max_assets=10)
        )
        result = engine.rank(store)
        kept_assets = sorted([a for c in result.clusters for a in c.asset_ids])
        assert kept_assets == ["A1", "B1"]

    def test_clusters_sorted_by_abs_delta(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-lo", asset_id="Lo", delta_npv=10.0)
        _insert_diff(store, run_id="run-hi", asset_id="Hi", delta_npv=90.0)
        result = PortfolioRankingEngine().rank(store)
        deltas = [abs(cl.combined_delta_npv_millions) for cl in result.clusters]
        assert deltas == sorted(deltas, reverse=True)

    def test_asset_ids_filter(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-A", asset_id="A", delta_npv=50.0)
        _insert_diff(store, run_id="run-B", asset_id="B", delta_npv=60.0)
        result = PortfolioRankingEngine().rank(store, asset_ids=["A"])
        assert result.n_assets_evaluated == 1
        assert result.clusters[0].asset_ids == ["A"]


class TestPortfolioRankingEngineConstraints:
    def test_confidence_filter(self, store: KnowledgeStore) -> None:
        run_id, event_id = _insert_diff(store, run_id="run-low", asset_id="Low", delta_npv=80.0)
        _insert_signal(store, event_id, asset_id="Low", confidence=0.4)
        _insert_diff(store, run_id="run-hi", asset_id="Hi", delta_npv=60.0)
        # High asset has no signal → confidence is None → not filtered

        c = PortfolioConstraints(min_confidence=0.6)
        result = PortfolioRankingEngine(constraints=c).rank(store)
        asset_ids_in_result = [a for cl in result.clusters for a in cl.asset_ids]
        assert "Low" not in asset_ids_in_result
        assert result.n_filtered_confidence == 1

    def test_magnitude_filter(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-small", asset_id="Small", delta_npv=10.0)
        _insert_diff(store, run_id="run-big",   asset_id="Big",   delta_npv=60.0)
        c = PortfolioConstraints(min_abs_delta_npv_millions=25.0)
        result = PortfolioRankingEngine(constraints=c).rank(store)
        asset_ids = [a for cl in result.clusters for a in cl.asset_ids]
        assert "Small" not in asset_ids
        assert "Big" in asset_ids
        assert result.n_filtered_magnitude == 1

    def test_age_filter(self, store: KnowledgeStore) -> None:
        # Old diff (40 days ago) should be filtered with max_queue_age_days=30
        _insert_diff(store, run_id="run-old", asset_id="Old", delta_npv=80.0, created_days_ago=40)
        _insert_diff(store, run_id="run-new", asset_id="New", delta_npv=60.0, created_days_ago=5)
        c = PortfolioConstraints(max_queue_age_days=30)
        result = PortfolioRankingEngine(constraints=c).rank(store)
        asset_ids = [a for cl in result.clusters for a in cl.asset_ids]
        assert "Old" not in asset_ids
        assert "New" in asset_ids
        assert result.n_filtered_age == 1

    def test_require_accepted_review(self, store: KnowledgeStore) -> None:
        run_a, _ = _insert_diff(store, run_id="run-acc", asset_id="Accepted", delta_npv=80.0)
        _insert_diff(store, run_id="run-pen", asset_id="Pending", delta_npv=60.0)
        _accept_diff(store, run_a, asset_id="Accepted")

        c = PortfolioConstraints(require_accepted_review=True)
        result = PortfolioRankingEngine(constraints=c).rank(store)
        asset_ids = [a for cl in result.clusters for a in cl.asset_ids]
        assert "Accepted" in asset_ids
        assert "Pending" not in asset_ids
        assert result.n_filtered_not_accepted == 1

    def test_max_assets_cap(self, store: KnowledgeStore) -> None:
        for i in range(5):
            _insert_diff(store, run_id=f"run-cap-{i}", asset_id=f"asset-{i}",
                         delta_npv=float(i * 10 + 10))
        c = PortfolioConstraints(max_assets=3)
        result = PortfolioRankingEngine(constraints=c).rank(store)
        total_assets = sum(cl.n_assets for cl in result.clusters)
        assert total_assets <= 3

    def test_top_n_caps_clusters(self, store: KnowledgeStore) -> None:
        for i in range(6):
            _insert_diff(store, run_id=f"run-tn-{i}", asset_id=f"asset-tn-{i}",
                         delta_npv=float(i * 10 + 10))
        c = PortfolioConstraints(top_n=3)
        result = PortfolioRankingEngine(constraints=c).rank(store)
        assert len(result.clusters) <= 3


class TestPortfolioRankingEngineKGClusters:
    def test_kg_edges_produce_multi_asset_cluster(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-A", asset_id="A", delta_npv=60.0)
        _insert_diff(store, run_id="run-B", asset_id="B", delta_npv=40.0)
        na = _add_kg_asset_node(store, "A")
        nb = _add_kg_asset_node(store, "B")
        _add_same_indication_edge(store, na, nb)

        result = PortfolioRankingEngine().rank(store)
        assert len(result.clusters) == 1
        assert set(result.clusters[0].asset_ids) == {"A", "B"}
        assert result.clusters[0].n_assets == 2

    def test_combined_delta_in_cluster(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-X", asset_id="X", delta_npv=70.0)
        _insert_diff(store, run_id="run-Y", asset_id="Y", delta_npv=30.0)
        nx = _add_kg_asset_node(store, "X")
        ny = _add_kg_asset_node(store, "Y")
        _add_same_indication_edge(store, nx, ny)

        result = PortfolioRankingEngine().rank(store)
        assert result.clusters[0].combined_delta_npv_millions == pytest.approx(100.0)

    def test_pending_review_count_in_cluster(self, store: KnowledgeStore) -> None:
        run_a, _ = _insert_diff(store, run_id="run-pa", asset_id="PA", delta_npv=50.0)
        _insert_diff(store, run_id="run-pb", asset_id="PB", delta_npv=40.0)
        _accept_diff(store, run_a, asset_id="PA")  # PA is reviewed

        na = _add_kg_asset_node(store, "PA")
        nb = _add_kg_asset_node(store, "PB")
        _add_same_indication_edge(store, na, nb)

        result = PortfolioRankingEngine().rank(store)
        cl = result.clusters[0]
        # PB still pending → n_pending_review = 1
        assert cl.n_pending_review == 1

    def test_no_kg_node_falls_back_to_singleton(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-nk", asset_id="NoKG", delta_npv=50.0)
        result = PortfolioRankingEngine().rank(store)
        assert result.clusters[0].edge_type == "singleton"

    def test_custom_cluster_edge_type(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-st1", asset_id="S1", delta_npv=60.0)
        _insert_diff(store, run_id="run-st2", asset_id="S2", delta_npv=40.0)
        ns1 = _add_kg_asset_node(store, "S1")
        ns2 = _add_kg_asset_node(store, "S2")
        store.add_edge(KGEdge(
            source_node_id=ns1.node_id,
            target_node_id=ns2.node_id,
            edge_type=EdgeType.SAME_TARGET,
        ))
        c = PortfolioConstraints(cluster_edge_type="same_target")
        result = PortfolioRankingEngine(constraints=c).rank(store)
        assert set(result.clusters[0].asset_ids) == {"S1", "S2"}
