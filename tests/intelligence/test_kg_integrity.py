from __future__ import annotations

from bve.intelligence.kg_integrity import KGIntegrityChecker
from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore


def test_kg_integrity_clean_graph_passes(tmp_path):
    store = KnowledgeStore(tmp_path / "kg_clean.db")
    try:
        asset = KGNode(node_type=NodeType.ASSET, name="Asset A", external_id="asset-a")
        company = KGNode(node_type=NodeType.COMPANY, name="Company A", external_id="company-a")
        store.add_node(asset)
        store.add_node(company)
        store.add_edge(
            KGEdge(
                source_node_id=asset.node_id,
                target_node_id=company.node_id,
                edge_type=EdgeType.PARTNERED_WITH,
                confidence=0.8,
            )
        )

        report = KGIntegrityChecker(store).check(["asset-a"])
        assert report.passed is True
        assert report.orphan_edges == []
        assert report.duplicate_nodes == []
        assert report.invalid_confidence == []
        assert report.missing_asset_nodes == []
        assert report.n_nodes == 2
        assert report.n_edges == 1
    finally:
        store.close()


def test_kg_integrity_detects_orphan_and_duplicate_nodes(tmp_path):
    store = KnowledgeStore(tmp_path / "kg_orphan_duplicate.db")
    try:
        node_a = KGNode(node_type=NodeType.ASSET, name="Asset X", external_id="asset-x")
        node_b = KGNode(node_type=NodeType.ASSET, name="Asset X duplicate", external_id="asset-x")
        store.add_node(node_a)
        store.add_node(node_b)
        store._conn.execute(
            """
            INSERT INTO kg_edges(
                edge_id, source_node_id, target_node_id, edge_type,
                confidence, source_signal_id, properties_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "orphan-edge-1",
                node_a.node_id,
                "missing-target-node",
                EdgeType.SAME_INDICATION.value,
                0.6,
                None,
                "{}",
                "2026-03-09T12:00:00+00:00",
            ),
        )
        store._conn.commit()

        report = KGIntegrityChecker(store).check(["asset-x"])
        assert report.passed is False
        assert report.orphan_edges == ["orphan-edge-1"]
        assert any("asset::asset-x" in item for item in report.duplicate_nodes)
    finally:
        store.close()


def test_kg_integrity_detects_invalid_confidence_and_logs_report(tmp_path):
    store = KnowledgeStore(tmp_path / "kg_invalid_confidence.db")
    try:
        source = KGNode(node_type=NodeType.ASSET, name="Asset B", external_id="asset-b")
        target = KGNode(node_type=NodeType.INDICATION, name="NSCLC", external_id="indication-nsclc")
        store.add_node(source)
        store.add_node(target)
        store._conn.execute(
            """
            INSERT INTO kg_edges(
                edge_id, source_node_id, target_node_id, edge_type,
                confidence, source_signal_id, properties_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "invalid-confidence-edge",
                source.node_id,
                target.node_id,
                EdgeType.TREATS.value,
                1.5,
                None,
                "{}",
                "2026-03-09T12:00:00+00:00",
            ),
        )
        store._conn.commit()

        report = KGIntegrityChecker(store).check(["asset-b", "asset-missing"])
        assert report.passed is False
        assert report.invalid_confidence == ["invalid-confidence-edge"]
        assert report.missing_asset_nodes == ["asset-missing"]

        store.log_kg_integrity(report)
        latest = store.get_latest_kg_integrity()
        assert latest is not None
        assert latest["passed"] is False
        assert latest["report_json"]["invalid_confidence"] == ["invalid-confidence-edge"]
    finally:
        store.close()
