"""Tests for Wave 2A — Knowledge Graph (KGNode, KGEdge, KnowledgeStore graph methods)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    ks = KnowledgeStore(db_path=":memory:")
    yield ks
    ks.close()


def _asset_node(**kwargs) -> KGNode:
    return KGNode(node_type=NodeType.ASSET, name="DrugA", **kwargs)


def _company_node(**kwargs) -> KGNode:
    return KGNode(node_type=NodeType.COMPANY, name="AcmePharma", **kwargs)


def _competes_edge(src: str, tgt: str, **kwargs) -> KGEdge:
    return KGEdge(
        source_node_id=src,
        target_node_id=tgt,
        edge_type=EdgeType.COMPETES_WITH,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# NodeType / EdgeType enum coverage
# ---------------------------------------------------------------------------


def test_node_type_values():
    expected = {
        "asset",
        "company",
        "indication",
        "target",
        "mechanism",
        "trial",
        "competitor_program",
        "modality",
        "financing_state",
        "management_team",
        "thesis_snapshot",
        "catalyst",
    }
    assert {t.value for t in NodeType} == expected


def test_edge_type_values():
    expected = {
        "treats",
        "targets",
        "competes_with",
        "company_owns_asset",
        "asset_treats_indication",
        "asset_targets_target",
        "has_mechanism",
        "has_modality",
        "financing_applies_to_company",
        "management_runs_company",
        "thesis_snapshot_for_asset",
        "trial_belongs_to_asset",
        "competitor_overlaps_asset",
        "catalyst_for_asset",
        "same_indication",
        "same_target",
        "same_mechanism",
        "same_trial_phase",
        "same_endpoint",
        "same_population",
        "partnered_with",
    }
    assert {t.value for t in EdgeType} == expected


# ---------------------------------------------------------------------------
# KGNode model
# ---------------------------------------------------------------------------


def test_kg_node_auto_uuid():
    n1 = _asset_node()
    n2 = _asset_node()
    assert n1.node_id != n2.node_id
    assert len(n1.node_id) == 36  # UUID4 format


def test_kg_node_fields():
    n = KGNode(
        node_type=NodeType.TRIAL,
        name="NCT12345",
        external_id="NCT12345",
        properties={"phase": "3"},
    )
    assert n.node_type == NodeType.TRIAL
    assert n.name == "NCT12345"
    assert n.external_id == "NCT12345"
    assert n.properties == {"phase": "3"}


# ---------------------------------------------------------------------------
# KGEdge model
# ---------------------------------------------------------------------------


def test_kg_edge_auto_uuid():
    e1 = KGEdge(source_node_id="a", target_node_id="b", edge_type=EdgeType.TREATS)
    e2 = KGEdge(source_node_id="a", target_node_id="b", edge_type=EdgeType.TREATS)
    assert e1.edge_id != e2.edge_id


def test_kg_edge_confidence_default():
    e = KGEdge(source_node_id="a", target_node_id="b", edge_type=EdgeType.TARGETS)
    assert e.confidence == 1.0


def test_kg_edge_confidence_clamped_valid():
    e = KGEdge(source_node_id="a", target_node_id="b", edge_type=EdgeType.TARGETS, confidence=0.73)
    assert e.confidence == pytest.approx(0.73)


def test_kg_edge_confidence_below_zero_rejected():
    with pytest.raises(ValidationError):
        KGEdge(source_node_id="a", target_node_id="b", edge_type=EdgeType.TARGETS, confidence=-0.1)


def test_kg_edge_confidence_above_one_rejected():
    with pytest.raises(ValidationError):
        KGEdge(source_node_id="a", target_node_id="b", edge_type=EdgeType.TARGETS, confidence=1.1)


# ---------------------------------------------------------------------------
# add_node / get_node
# ---------------------------------------------------------------------------


def test_add_node_stores_and_retrieves(store):
    node = _asset_node(external_id="asset-1", properties={"TA": "oncology"})
    store.add_node(node)
    fetched = store.get_node(node.node_id)
    assert fetched is not None
    assert fetched.node_id == node.node_id
    assert fetched.node_type == NodeType.ASSET
    assert fetched.name == "DrugA"
    assert fetched.external_id == "asset-1"
    assert fetched.properties == {"TA": "oncology"}


def test_add_node_idempotent(store):
    node = _asset_node()
    store.add_node(node)
    store.add_node(node)  # should not raise or duplicate
    assert len(store.find_by_type(NodeType.ASSET)) == 1


def test_get_node_unknown_returns_none(store):
    assert store.get_node("does-not-exist") is None


# ---------------------------------------------------------------------------
# upsert_node
# ---------------------------------------------------------------------------


def test_upsert_node_updates_name_and_properties(store):
    node = _asset_node(external_id="asset-1")
    store.add_node(node)

    updated = KGNode(
        node_id=node.node_id,
        node_type=NodeType.ASSET,
        name="DrugA-Updated",
        properties={"TA": "cardiology"},
    )
    store.upsert_node(updated)

    fetched = store.get_node(node.node_id)
    assert fetched.name == "DrugA-Updated"
    assert fetched.properties == {"TA": "cardiology"}


# ---------------------------------------------------------------------------
# find_by_type
# ---------------------------------------------------------------------------


def test_find_by_type_returns_correct_type(store):
    store.add_node(_asset_node())
    store.add_node(_asset_node())
    store.add_node(_company_node())
    assets = store.find_by_type(NodeType.ASSET)
    assert len(assets) == 2
    assert all(n.node_type == NodeType.ASSET for n in assets)


def test_find_by_type_empty_when_none(store):
    assert store.find_by_type(NodeType.INDICATION) == []


# ---------------------------------------------------------------------------
# add_edge
# ---------------------------------------------------------------------------


def test_add_edge_stores_all_fields(store):
    src = _asset_node()
    tgt = KGNode(node_type=NodeType.COMPETITOR_PROGRAM, name="CompetitorX")
    store.add_node(src)
    store.add_node(tgt)

    edge = KGEdge(
        source_node_id=src.node_id,
        target_node_id=tgt.node_id,
        edge_type=EdgeType.COMPETES_WITH,
        confidence=0.85,
        source_signal_id="sig-001",
        properties={"note": "phase3"},
    )
    store.add_edge(edge)

    neighbors = store.neighbors(src.node_id, edge_type=EdgeType.COMPETES_WITH)
    assert len(neighbors) == 1
    assert neighbors[0].node_id == tgt.node_id


def test_add_edge_confidence_stored(store):
    src = _asset_node()
    tgt = _company_node()
    store.add_node(src)
    store.add_node(tgt)

    edge = KGEdge(
        source_node_id=src.node_id,
        target_node_id=tgt.node_id,
        edge_type=EdgeType.PARTNERED_WITH,
        confidence=0.73,
    )
    store.add_edge(edge)

    # Fetch via get_subgraph to inspect edge directly
    subgraph = store.get_subgraph(src.node_id, depth=1)
    assert len(subgraph["edges"]) == 1
    assert subgraph["edges"][0].confidence == pytest.approx(0.73)


def test_add_edge_source_signal_id_stored(store):
    src = _asset_node()
    tgt = _company_node()
    store.add_node(src)
    store.add_node(tgt)

    edge = KGEdge(
        source_node_id=src.node_id,
        target_node_id=tgt.node_id,
        edge_type=EdgeType.PARTNERED_WITH,
        source_signal_id="sig-xyz",
    )
    store.add_edge(edge)

    subgraph = store.get_subgraph(src.node_id, depth=1)
    assert subgraph["edges"][0].source_signal_id == "sig-xyz"


def test_add_edge_conflict_updates_confidence(store):
    src = _asset_node()
    tgt = _company_node()
    store.add_node(src)
    store.add_node(tgt)

    e1 = KGEdge(source_node_id=src.node_id, target_node_id=tgt.node_id,
                edge_type=EdgeType.PARTNERED_WITH, confidence=0.5)
    e2 = KGEdge(source_node_id=src.node_id, target_node_id=tgt.node_id,
                edge_type=EdgeType.PARTNERED_WITH, confidence=0.9)
    store.add_edge(e1)
    store.add_edge(e2)

    subgraph = store.get_subgraph(src.node_id, depth=1)
    assert len(subgraph["edges"]) == 1
    assert subgraph["edges"][0].confidence == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# neighbors
# ---------------------------------------------------------------------------


def test_neighbors_undirected_both_directions(store):
    a = _asset_node()
    b = _company_node()
    store.add_node(a)
    store.add_node(b)
    store.add_edge(KGEdge(source_node_id=a.node_id, target_node_id=b.node_id,
                          edge_type=EdgeType.PARTNERED_WITH))

    # from source perspective
    assert any(n.node_id == b.node_id for n in store.neighbors(a.node_id))
    # from target perspective
    assert any(n.node_id == a.node_id for n in store.neighbors(b.node_id))


def test_neighbors_isolated_node_returns_empty(store):
    node = _asset_node()
    store.add_node(node)
    assert store.neighbors(node.node_id) == []


def test_neighbors_edge_type_filter(store):
    a = _asset_node()
    b = _company_node()
    c = KGNode(node_type=NodeType.INDICATION, name="NSCLC")
    store.add_node(a)
    store.add_node(b)
    store.add_node(c)
    store.add_edge(KGEdge(source_node_id=a.node_id, target_node_id=b.node_id,
                          edge_type=EdgeType.PARTNERED_WITH))
    store.add_edge(KGEdge(source_node_id=a.node_id, target_node_id=c.node_id,
                          edge_type=EdgeType.TREATS))

    treats_neighbors = store.neighbors(a.node_id, edge_type=EdgeType.TREATS)
    assert len(treats_neighbors) == 1
    assert treats_neighbors[0].node_id == c.node_id


# ---------------------------------------------------------------------------
# get_subgraph
# ---------------------------------------------------------------------------


def test_get_subgraph_depth1(store):
    a = _asset_node()
    b = _company_node()
    c = KGNode(node_type=NodeType.INDICATION, name="NSCLC")
    store.add_node(a)
    store.add_node(b)
    store.add_node(c)
    store.add_edge(KGEdge(source_node_id=a.node_id, target_node_id=b.node_id,
                          edge_type=EdgeType.PARTNERED_WITH))
    store.add_edge(KGEdge(source_node_id=b.node_id, target_node_id=c.node_id,
                          edge_type=EdgeType.SAME_INDICATION))

    sg = store.get_subgraph(a.node_id, depth=1)
    node_ids = {n.node_id for n in sg["nodes"]}
    assert a.node_id in node_ids
    assert b.node_id in node_ids
    assert c.node_id not in node_ids  # two hops away
    assert len(sg["edges"]) == 1


def test_get_subgraph_depth2(store):
    a = _asset_node()
    b = _company_node()
    c = KGNode(node_type=NodeType.INDICATION, name="NSCLC")
    store.add_node(a)
    store.add_node(b)
    store.add_node(c)
    store.add_edge(KGEdge(source_node_id=a.node_id, target_node_id=b.node_id,
                          edge_type=EdgeType.PARTNERED_WITH))
    store.add_edge(KGEdge(source_node_id=b.node_id, target_node_id=c.node_id,
                          edge_type=EdgeType.SAME_INDICATION))

    sg = store.get_subgraph(a.node_id, depth=2)
    node_ids = {n.node_id for n in sg["nodes"]}
    assert a.node_id in node_ids
    assert b.node_id in node_ids
    assert c.node_id in node_ids
    assert len(sg["edges"]) == 2


def test_get_subgraph_unknown_node_returns_empty(store):
    sg = store.get_subgraph("ghost-node", depth=2)
    assert sg["nodes"] == []
    assert sg["edges"] == []


# ---------------------------------------------------------------------------
# find_competing_assets
# ---------------------------------------------------------------------------


def test_find_competing_assets_returns_competitors(store):
    drug = _asset_node()
    comp1 = KGNode(node_type=NodeType.COMPETITOR_PROGRAM, name="CompA")
    comp2 = KGNode(node_type=NodeType.COMPETITOR_PROGRAM, name="CompB")
    store.add_node(drug)
    store.add_node(comp1)
    store.add_node(comp2)
    store.add_edge(_competes_edge(drug.node_id, comp1.node_id))
    store.add_edge(_competes_edge(drug.node_id, comp2.node_id))

    competitors = store.find_competing_assets(drug.node_id)
    ids = {n.node_id for n in competitors}
    assert comp1.node_id in ids
    assert comp2.node_id in ids


def test_find_competing_assets_empty(store):
    drug = _asset_node()
    store.add_node(drug)
    assert store.find_competing_assets(drug.node_id) == []


# ---------------------------------------------------------------------------
# properties round-trip
# ---------------------------------------------------------------------------


def test_node_properties_roundtrip(store):
    node = KGNode(
        node_type=NodeType.MECHANISM,
        name="CDK4/6 inhibition",
        properties={"class": "kinase_inhibitor", "targets": ["CDK4", "CDK6"]},
    )
    store.add_node(node)
    fetched = store.get_node(node.node_id)
    assert fetched.properties == {"class": "kinase_inhibitor", "targets": ["CDK4", "CDK6"]}


def test_edge_properties_roundtrip(store):
    src = _asset_node()
    tgt = _company_node()
    store.add_node(src)
    store.add_node(tgt)
    edge = KGEdge(
        source_node_id=src.node_id,
        target_node_id=tgt.node_id,
        edge_type=EdgeType.PARTNERED_WITH,
        properties={"deal_year": 2023, "territory": "global"},
    )
    store.add_edge(edge)
    sg = store.get_subgraph(src.node_id, depth=1)
    assert sg["edges"][0].properties == {"deal_year": 2023, "territory": "global"}
