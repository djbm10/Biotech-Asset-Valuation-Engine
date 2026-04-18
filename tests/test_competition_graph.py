"""Tests for competition_graph, readthrough_engine, and revaluation_triggers modules."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.intelligence.competition_graph import (
    CompetitionEdge,
    CompetitionGraph,
    CompetitionNode,
)
from bve.intelligence.readthrough_engine import (
    ReadthroughEngine,
    ReadthroughEvent,
    ReadthroughResult,
)
from bve.intelligence.revaluation_triggers import (
    RevaluationTrigger,
    RevaluationTriggerEngine,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# CompetitionNode
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
# CompetitionEdge
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
# CompetitionGraph
# ---------------------------------------------------------------------------

def test_competition_graph_basic():
    focal = CompetitionNode(
        asset_id="A1", ticker="TICK", company_name="BioCo",
        indication="NSCLC", stage="Phase 3", status="active",
    )
    graph = CompetitionGraph(
        graph_id="G1",
        asset_id="A1",
        focal_node=focal,
        built_at=_now(),
        summary="Focal asset vs 0 competitors.",
    )
    assert graph.competitor_nodes == []
    assert graph.edges == []


# ---------------------------------------------------------------------------
# ReadthroughEvent
# ---------------------------------------------------------------------------

def _make_event(event_type: str, materiality: float = 0.7) -> ReadthroughEvent:
    return ReadthroughEvent(
        event_id="EV1",
        competitor_asset_id="A2",
        event_type=event_type,
        event_date=date(2025, 6, 1),
        description="Competitor event",
        materiality_score=materiality,
    )


# ---------------------------------------------------------------------------
# ReadthroughEngine
# ---------------------------------------------------------------------------

def test_readthrough_positive_on_success():
    engine = ReadthroughEngine()
    event = _make_event("readout_success", materiality=0.8)
    result = engine.assess("A1", "A2", event)
    assert result.readthrough_direction == "positive"
    assert result.magnitude > 0


def test_readthrough_negative_on_failure():
    engine = ReadthroughEngine()
    event = _make_event("readout_failure", materiality=0.7)
    result = engine.assess("A1", "A2", event)
    assert result.readthrough_direction == "negative"
    assert result.magnitude < 0


def test_readthrough_negative_on_safety():
    engine = ReadthroughEngine()
    event = _make_event("safety", materiality=0.9)
    result = engine.assess("A1", "A2", event)
    assert result.readthrough_direction == "negative"
    assert result.market_expansion_factor < 1.0


def test_readthrough_positive_on_discontinuation():
    engine = ReadthroughEngine()
    event = _make_event("discontinuation", materiality=0.6)
    result = engine.assess("A1", "A2", event)
    assert result.readthrough_direction == "positive"
    assert result.peak_sales_delta_pct > 0


def test_readthrough_ambiguous_on_partnership():
    engine = ReadthroughEngine()
    event = _make_event("partnership", materiality=0.5)
    result = engine.assess("A1", "A2", event)
    assert result.readthrough_direction == "ambiguous"
    assert result.magnitude == 0.0


def test_readthrough_unknown_event_type():
    engine = ReadthroughEngine()
    event = _make_event("unknown_event_xyz", materiality=0.5)
    result = engine.assess("A1", "A2", event)
    assert result.readthrough_direction == "ambiguous"


# ---------------------------------------------------------------------------
# RevaluationTriggerEngine
# ---------------------------------------------------------------------------

def test_revaluation_trigger_above_threshold():
    engine = RevaluationTriggerEngine()
    trigger = engine.evaluate("A1", "competitor_event", materiality_score=0.5)
    assert trigger is not None
    assert trigger.asset_id == "A1"
    assert "competition" in trigger.modules_to_recompute


def test_revaluation_trigger_below_threshold_non_critical():
    engine = RevaluationTriggerEngine()
    trigger = engine.evaluate("A1", "competitor_event", materiality_score=0.2)
    assert trigger is None


def test_revaluation_trigger_critical_event_always_fires():
    engine = RevaluationTriggerEngine()
    trigger = engine.evaluate("A1", "thesis_break", materiality_score=0.1)
    assert trigger is not None
    assert trigger.priority == "high"


def test_revaluation_trigger_high_priority_at_high_materiality():
    engine = RevaluationTriggerEngine()
    trigger = engine.evaluate("A1", "data_refresh", materiality_score=0.8)
    assert trigger is not None
    assert trigger.priority == "high"
