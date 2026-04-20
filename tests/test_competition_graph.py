"""Tests for competition_graph module — legacy Pydantic types and new CompetitionGraph class."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bve.intelligence.competition_graph import (
    CompetitionEdge,
    CompetitionGraph,
    CompetitionNode,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# CompetitionNode (legacy Pydantic model)
# ---------------------------------------------------------------------------

def test_competition_node_basic():
    node = CompetitionNode(
        asset_id="A1",
        ticker="TICK",
        company_name="BioCo",
        indication="NSCLC",
        stage="Phase 3",
        status="active",
        approval_probability=0.55,
    )
    assert node.status == "active"
    assert node.target is None


# ---------------------------------------------------------------------------
# CompetitionEdge (legacy Pydantic model)
# ---------------------------------------------------------------------------

def test_competition_edge_basic():
    edge = CompetitionEdge(
        edge_id="E1",
        source_asset_id="A1",
        target_asset_id="A2",
        relationship_type="same_indication",
        overlap_score=0.8,
        created_at=_now(),
    )
    assert edge.relationship_type == "same_indication"
    assert 0.0 <= edge.overlap_score <= 1.0


def test_competition_edge_overlap_bounds():
    with pytest.raises(Exception):
        CompetitionEdge(
            edge_id="E1",
            source_asset_id="A1",
            target_asset_id="A2",
            relationship_type="same_indication",
            overlap_score=1.5,
            created_at=_now(),
        )


# ---------------------------------------------------------------------------
# CompetitionGraph (new plain-class interface)
# ---------------------------------------------------------------------------

def test_competition_graph_empty():
    graph = CompetitionGraph()
    assert graph.all_nodes() == []
    assert graph.get_competitors("MISSING") == []
