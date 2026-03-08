"""Tests for Wave 2B — Competitor Program Discovery."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest

from bve.intelligence.competitor_discovery import (
    CompetitorDiscoveryEngine,
    CompetitorDiscoveryResult,
    CompetitorProgram,
    _extract_program,
)
from bve.intelligence.knowledge_graph import EdgeType, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    ks = KnowledgeStore(db_path=":memory:")
    yield ks
    ks.close()


@pytest.fixture
def asset_node(store) -> KGNode:
    node = KGNode(node_type=NodeType.ASSET, name="DrugA", external_id="asset-001")
    store.add_node(node)
    return node


def _raw_study(
    nct_id: str = "NCT12345678",
    drug_name: str = "CompetitorDrug",
    status: str = "RECRUITING",
    phase: str = "PHASE3",
    company: str = "AcmePharma",
    endpoint_measure: str = "Overall Survival",
) -> dict[str, Any]:
    """Build a minimal ClinicalTrials.gov protocolSection dict."""
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": drug_name},
            "statusModule": {"overallStatus": status},
            "designModule": {"phases": [phase]},
            "armsInterventionsModule": {
                "interventions": [{"interventionType": "DRUG", "name": drug_name}]
            },
            "outcomesModule": {
                "primaryOutcomes": [{"measure": endpoint_measure}]
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {"name": company}
            },
            "conditionsModule": {"conditions": ["NSCLC"]},
        }
    }


def _engine(store, studies: list[dict], max_results: int = 50) -> CompetitorDiscoveryEngine:
    """Build engine with a canned search function."""
    proto_list = [s.get("protocolSection", s) for s in studies]

    def fake_search(**kwargs):
        return [{"protocolSection": p} for p in proto_list]

    return CompetitorDiscoveryEngine(store=store, max_results=max_results, search_fn=fake_search)


# ---------------------------------------------------------------------------
# CompetitorProgram model
# ---------------------------------------------------------------------------


def test_competitor_program_auto_uuid():
    p1 = CompetitorProgram(asset_id="a", drug_name="Drug", indication="NSCLC")
    p2 = CompetitorProgram(asset_id="a", drug_name="Drug", indication="NSCLC")
    assert p1.program_id != p2.program_id


def test_competitor_program_fields():
    p = CompetitorProgram(
        asset_id="asset-001",
        company="BioPharma",
        drug_name="CompetitorX",
        nct_id="NCT00000001",
        phase="PHASE3",
        status="RECRUITING",
        primary_endpoint_type="os",
        indication="NSCLC",
    )
    assert p.asset_id == "asset-001"
    assert p.company == "BioPharma"
    assert p.nct_id == "NCT00000001"
    assert p.primary_endpoint_type == "os"


def test_competitor_program_optional_fields_default_none():
    p = CompetitorProgram(asset_id="a", drug_name="Drug", indication="NSCLC")
    assert p.company is None
    assert p.nct_id is None
    assert p.phase is None
    assert p.status is None
    assert p.primary_endpoint_type is None


# ---------------------------------------------------------------------------
# _extract_program
# ---------------------------------------------------------------------------


def test_extract_program_os_endpoint():
    raw = _raw_study(endpoint_measure="Overall Survival")
    proto = raw["protocolSection"]
    p = _extract_program(proto, "asset-001", "NSCLC", datetime.now(timezone.utc))
    assert p is not None
    assert p.primary_endpoint_type == "os"


def test_extract_program_pfs_endpoint():
    raw = _raw_study(endpoint_measure="Progression-Free Survival (PFS)")
    proto = raw["protocolSection"]
    p = _extract_program(proto, "asset-001", "NSCLC", datetime.now(timezone.utc))
    assert p.primary_endpoint_type == "pfs"


def test_extract_program_surrogate_endpoint():
    raw = _raw_study(endpoint_measure="ORR objective response rate")
    proto = raw["protocolSection"]
    p = _extract_program(proto, "asset-001", "NSCLC", datetime.now(timezone.utc))
    assert p.primary_endpoint_type == "surrogate"


def test_extract_program_no_drug_returns_none():
    proto = {
        "identificationModule": {"nctId": "NCT99", "briefTitle": ""},
        "statusModule": {"overallStatus": "RECRUITING"},
        "designModule": {"phases": []},
        "armsInterventionsModule": {"interventions": []},
        "outcomesModule": {"primaryOutcomes": []},
        "sponsorCollaboratorsModule": {},
        "conditionsModule": {},
    }
    result = _extract_program(proto, "asset-001", "NSCLC", datetime.now(timezone.utc))
    assert result is None


# ---------------------------------------------------------------------------
# KnowledgeStore — competitor_programs table
# ---------------------------------------------------------------------------


def test_add_competitor_program_stores(store):
    p = CompetitorProgram(
        asset_id="asset-001", drug_name="DrugX",
        nct_id="NCT00000001", indication="NSCLC",
    )
    store.add_competitor_program(p)
    rows = store.get_competitor_programs("asset-001")
    assert len(rows) == 1
    assert rows[0]["drug_name"] == "DrugX"
    assert rows[0]["nct_id"] == "NCT00000001"


def test_add_competitor_program_idempotent(store):
    p = CompetitorProgram(
        asset_id="asset-001", drug_name="DrugX",
        nct_id="NCT00000001", indication="NSCLC",
    )
    store.add_competitor_program(p)
    store.add_competitor_program(p)  # second call must not raise or duplicate
    assert len(store.get_competitor_programs("asset-001")) == 1


def test_get_competitor_programs_scoped_to_asset(store):
    p1 = CompetitorProgram(asset_id="asset-001", drug_name="DrugA",
                           nct_id="NCT0000001", indication="NSCLC")
    p2 = CompetitorProgram(asset_id="asset-002", drug_name="DrugB",
                           nct_id="NCT0000002", indication="NSCLC")
    store.add_competitor_program(p1)
    store.add_competitor_program(p2)
    assert len(store.get_competitor_programs("asset-001")) == 1
    assert len(store.get_competitor_programs("asset-002")) == 1


def test_get_competitor_programs_empty(store):
    assert store.get_competitor_programs("nonexistent") == []


# ---------------------------------------------------------------------------
# CompetitorDiscoveryEngine.discover
# ---------------------------------------------------------------------------


def test_discover_returns_result(store, asset_node):
    eng = _engine(store, [_raw_study()])
    result = eng.discover("asset-001", asset_node.node_id, "NSCLC")
    assert isinstance(result, CompetitorDiscoveryResult)
    assert result.asset_id == "asset-001"
    assert result.indication == "NSCLC"


def test_discover_finds_programs(store, asset_node):
    studies = [_raw_study("NCT001"), _raw_study("NCT002")]
    eng = _engine(store, studies)
    result = eng.discover("asset-001", asset_node.node_id, "NSCLC")
    assert len(result.programs_found) == 2


def test_discover_adds_kg_edges(store, asset_node):
    studies = [_raw_study("NCT001"), _raw_study("NCT002")]
    eng = _engine(store, studies)
    result = eng.discover("asset-001", asset_node.node_id, "NSCLC")
    assert result.kg_edges_added == 2
    competitors = store.find_competing_assets(asset_node.node_id)
    assert len(competitors) == 2


def test_discover_persists_programs(store, asset_node):
    eng = _engine(store, [_raw_study("NCT001")])
    eng.discover("asset-001", asset_node.node_id, "NSCLC")
    rows = store.get_competitor_programs("asset-001")
    assert len(rows) == 1
    assert rows[0]["nct_id"] == "NCT001"


def test_discover_no_duplicates_on_rerun(store, asset_node):
    eng = _engine(store, [_raw_study("NCT001")])
    eng.discover("asset-001", asset_node.node_id, "NSCLC")
    eng.discover("asset-001", asset_node.node_id, "NSCLC")
    rows = store.get_competitor_programs("asset-001")
    assert len(rows) == 1  # idempotent


def test_discover_empty_results(store, asset_node):
    eng = _engine(store, [])
    result = eng.discover("asset-001", asset_node.node_id, "NSCLC")
    assert result.programs_found == []
    assert result.kg_edges_added == 0
    assert result.errors == []


def test_discover_skips_inactive_status(store, asset_node):
    studies = [
        _raw_study("NCT001", status="RECRUITING"),
        _raw_study("NCT002", status="SUSPENDED"),   # not in _ACTIVE_STATUSES
    ]
    eng = _engine(store, studies)
    result = eng.discover("asset-001", asset_node.node_id, "NSCLC")
    assert len(result.programs_found) == 1
    assert result.programs_found[0].nct_id == "NCT001"


def test_discover_search_error_captured(store, asset_node):
    def failing_search(**kwargs):
        raise RuntimeError("Network error")

    eng = CompetitorDiscoveryEngine(store=store, search_fn=failing_search)
    result = eng.discover("asset-001", asset_node.node_id, "NSCLC")
    assert len(result.errors) == 1
    assert "search_studies failed" in result.errors[0]
    assert result.programs_found == []


def test_discover_kg_nodes_are_competitor_program_type(store, asset_node):
    eng = _engine(store, [_raw_study("NCT001")])
    eng.discover("asset-001", asset_node.node_id, "NSCLC")
    competitors = store.find_competing_assets(asset_node.node_id)
    assert all(n.node_type == NodeType.COMPETITOR_PROGRAM for n in competitors)
