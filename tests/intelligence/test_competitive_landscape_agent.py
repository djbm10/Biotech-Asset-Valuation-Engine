from __future__ import annotations

from datetime import datetime, timezone

from bve.intelligence.competitive_landscape_agent import CompetitiveLandscapeAgent
from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace

_NOW = datetime(2026, 3, 9, 16, 0, tzinfo=timezone.utc)


def _trace(ref: str) -> SourceTrace:
    return SourceTrace(source_type="unit_test", source_ref=ref, ingested_at=_NOW)


def test_competitive_landscape_retrieves_kg_competitors_and_scores(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        asset = KGNode(node_type=NodeType.ASSET, name="Asset A", external_id="asset-a")
        store.add_node(asset)

        comp_high = KGNode(
            node_type=NodeType.COMPETITOR_PROGRAM,
            name="Comp High",
            external_id="NCT100",
            properties={"company": "Co1", "phase": "PHASE3", "status": "RECRUITING"},
        )
        comp_low = KGNode(
            node_type=NodeType.COMPETITOR_PROGRAM,
            name="Comp Low",
            external_id="NCT200",
            properties={"company": "Co2", "phase": "PHASE1", "status": "RECRUITING"},
        )
        store.add_node(comp_high)
        store.add_node(comp_low)
        store.add_edge(
            KGEdge(
                source_node_id=asset.node_id,
                target_node_id=comp_high.node_id,
                edge_type=EdgeType.COMPETES_WITH,
            )
        )
        store.add_edge(
            KGEdge(
                source_node_id=asset.node_id,
                target_node_id=comp_low.node_id,
                edge_type=EdgeType.COMPETES_WITH,
            )
        )

        landscape = CompetitiveLandscapeAgent().generate(
            store,
            asset_id="asset-a",
            generated_at=_NOW,
        )

        assert len(landscape.entries) == 2
        assert landscape.entries[0].drug == "Comp High"
        assert landscape.entries[0].risk_score > landscape.entries[1].risk_score
        assert landscape.entries[0].source_nct_id == "NCT100"
        assert landscape.entries[0].distance_to_market < landscape.entries[1].distance_to_market
        assert landscape.entries[0].mechanism_similarity_score >= 0.2
    finally:
        store.close()


def test_competitive_landscape_includes_same_indication_asset_neighbors(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        asset_a = KGNode(node_type=NodeType.ASSET, name="Asset A", external_id="asset-a")
        asset_b = KGNode(
            node_type=NodeType.ASSET,
            name="Asset B",
            external_id="asset-b",
            properties={"company": "PeerCo", "stage": "PHASE2", "mechanism": "EGFR inhibitor"},
        )
        store.add_node(asset_a)
        store.add_node(asset_b)
        store.add_edge(
            KGEdge(
                source_node_id=asset_a.node_id,
                target_node_id=asset_b.node_id,
                edge_type=EdgeType.SAME_INDICATION,
            )
        )

        landscape = CompetitiveLandscapeAgent().generate(
            store,
            asset_id="asset-a",
            generated_at=_NOW,
        )

        assert len(landscape.entries) == 1
        assert landscape.entries[0].relationship == "same_indication_asset"
        assert landscape.entries[0].drug == "Asset B"
        assert landscape.entries[0].phase == "PHASE2"
        assert landscape.entries[0].distance_to_market >= 0.5
    finally:
        store.close()


def test_knowledge_store_persists_competitive_landscape(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        asset = KGNode(node_type=NodeType.ASSET, name="Asset A", external_id="asset-a")
        comp = KGNode(
            node_type=NodeType.COMPETITOR_PROGRAM,
            name="Comp A",
            external_id="NCT300",
            properties={"company": "CompCo", "phase": "PHASE2", "status": "COMPLETED"},
        )
        store.add_node(asset)
        store.add_node(comp)
        store.add_edge(
            KGEdge(
                source_node_id=asset.node_id,
                target_node_id=comp.node_id,
                edge_type=EdgeType.COMPETES_WITH,
            )
        )

        landscape = CompetitiveLandscapeAgent().generate(
            store,
            asset_id="asset-a",
            company_id="company-a",
            generated_at=_NOW,
        )
        record = store.add_competitive_landscape(
            landscape,
            source_trace=_trace("competitive-landscape"),
        )
        loaded = store.get_competitive_landscapes(asset_id="asset-a")

        assert record.id == landscape.landscape_id
        assert len(loaded) == 1
        assert loaded[0]["landscape_id"] == landscape.landscape_id

        traced = store.get_record_with_trace("competitive_landscapes", landscape.landscape_id)
        assert traced.record_id == landscape.landscape_id
    finally:
        store.close()


def test_competitive_landscape_cli_hook_persists(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(db_path)
    try:
        asset = KGNode(node_type=NodeType.ASSET, name="Asset CLI", external_id="asset-cli")
        comp = KGNode(
            node_type=NodeType.COMPETITOR_PROGRAM,
            name="Comp CLI",
            external_id="NCT999",
            properties={"company": "CliCo", "phase": "PHASE3", "status": "RECRUITING"},
        )
        store.add_node(asset)
        store.add_node(comp)
        store.add_edge(
            KGEdge(
                source_node_id=asset.node_id,
                target_node_id=comp.node_id,
                edge_type=EdgeType.COMPETES_WITH,
            )
        )
    finally:
        store.close()

    from bve.cli.competitive_landscape import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-competitive-landscape",
            "--db",
            str(db_path),
            "--asset-id",
            "asset-cli",
            "--company-id",
            "company-cli",
            "--persist",
            "--json",
        ],
    )
    main()
    captured = capsys.readouterr()
    assert '"asset_id": "asset-cli"' in captured.out

    verify_store = KnowledgeStore(db_path)
    try:
        rows = verify_store.get_competitive_landscapes(asset_id="asset-cli")
        assert len(rows) == 1
        assert rows[0]["asset_id"] == "asset-cli"
    finally:
        verify_store.close()
