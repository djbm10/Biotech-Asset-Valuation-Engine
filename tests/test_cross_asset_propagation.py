"""Tests for Wave 5 — calibrated cross-asset propagation."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.entities.trial import TrialPhase
from bve.intelligence.cross_asset_propagation import (
    CrossAssetPropagationEngine,
    GeneratedPropagationProposal,
    PropagationCalibration,
    PropagationCalibrator,
    PropagationDatasetBuilder,
    PropagationGuardrails,
    PropagationObservation,
    PropagationType,
)
from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.phase2 import ReviewQueue
from bve.intelligence.schemas.signals import Event, StructuredSignal
from bve.intelligence.taxonomy import EventType

_NOW = datetime(2026, 3, 9, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def store() -> KnowledgeStore:
    ks = KnowledgeStore(db_path=":memory:")
    yield ks
    ks.close()


def _trace(ref: str) -> SourceTrace:
    return SourceTrace(source_type="unit_test", source_ref=ref, ingested_at=_NOW)


def _signal(
    *,
    signal_id: str,
    event_id: str,
    asset_id: str,
    event_type: EventType,
    primary_endpoint_met: bool | None = None,
    fda_action_type: str | None = None,
) -> StructuredSignal:
    return StructuredSignal(
        id=signal_id,
        event_id=event_id,
        asset_id=asset_id,
        company_id=f"company-{asset_id}",
        event_type=event_type,
        signal_date=date(2026, 3, 9),
        trial_phase=TrialPhase.PHASE_3,
        primary_endpoint_met=primary_endpoint_met,
        fda_action_type=fda_action_type,  # type: ignore[arg-type]
        extraction_confidence=0.90,
        extraction_model="unit-test",
        created_at=_NOW,
    )


def _event(signal: StructuredSignal) -> Event:
    return Event(
        id=signal.event_id,
        event_type=signal.event_type,
        asset_id=signal.asset_id,
        company_id=signal.company_id,
        observed_at=_NOW,
        ingested_at=_NOW,
        source_type="press_release",
        source_url=f"https://example.org/{signal.event_id}",
        headline="event",
        confidence=0.90,
    )


def _persist_signal_event_outcome(
    store: KnowledgeStore,
    *,
    signal: StructuredSignal,
    market_return_t30: float,
    resolved_t30: int = 1,
) -> None:
    store.add_structured_signal(
        signal,
        _trace(f"signal:{signal.id}"),
        extraction_result_id=f"x-{signal.id}",
    )
    store.add_event(_event(signal), _trace(f"event:{signal.event_id}"), signal_id=signal.id)
    store._conn.execute(
        """
        INSERT INTO event_outcomes(
            outcome_id, event_id, asset_id, signal_date, event_type,
            market_return_t30, resolved_t30, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"oc-{signal.event_id}",
            signal.event_id,
            signal.asset_id,
            signal.signal_date.isoformat(),
            signal.event_type.value,
            market_return_t30,
            resolved_t30,
            _NOW.isoformat(),
        ),
    )
    store._conn.commit()


def test_dataset_builder_uses_resolved_event_outcomes(store: KnowledgeStore):
    competitor_fail = _signal(
        signal_id="sig-comp-fail",
        event_id="evt-comp-fail",
        asset_id="asset-a",
        event_type=EventType.COMPETITOR_EVENT,
        primary_endpoint_met=False,
    )
    safety = _signal(
        signal_id="sig-safety",
        event_id="evt-safety",
        asset_id="asset-b",
        event_type=EventType.SAFETY_SIGNAL,
    )
    unresolved = _signal(
        signal_id="sig-unresolved",
        event_id="evt-unresolved",
        asset_id="asset-c",
        event_type=EventType.SAFETY_SIGNAL,
    )
    _persist_signal_event_outcome(store, signal=competitor_fail, market_return_t30=0.07, resolved_t30=1)
    _persist_signal_event_outcome(store, signal=safety, market_return_t30=-0.05, resolved_t30=1)
    _persist_signal_event_outcome(store, signal=unresolved, market_return_t30=-0.20, resolved_t30=0)

    observations = PropagationDatasetBuilder().build(store)
    assert len(observations) == 2

    by_event = {o.event_id: o for o in observations}
    assert by_event["evt-comp-fail"].propagation_type == PropagationType.COMPETITOR_FAILURE
    assert by_event["evt-safety"].propagation_type == PropagationType.CLASS_EFFECT_SAFETY


def test_calibrator_applies_guardrails_and_confidence():
    observations = [
        PropagationObservation(
            propagation_type=PropagationType.COMPETITOR_FAILURE,
            event_id=f"evt-c-{i}",
            asset_id="asset-x",
            event_type=EventType.COMPETITOR_EVENT.value,
            signal_date=date(2026, 1, i + 1),
            market_return_t30=0.40,
        )
        for i in range(4)
    ] + [
        PropagationObservation(
            propagation_type=PropagationType.CLASS_EFFECT_SAFETY,
            event_id=f"evt-s-{i}",
            asset_id="asset-y",
            event_type=EventType.SAFETY_SIGNAL.value,
            signal_date=date(2026, 2, i + 1),
            market_return_t30=-0.50,
        )
        for i in range(4)
    ]

    calibrator = PropagationCalibrator(
        guardrails=PropagationGuardrails(
            max_pos_change_per_event=0.10,
            max_market_share_change=0.15,
        ),
        full_confidence_sample_size=20,
    )
    calibrated = calibrator.calibrate(observations)

    comp = calibrated[PropagationType.COMPETITOR_FAILURE]
    safety = calibrated[PropagationType.CLASS_EFFECT_SAFETY]

    assert comp.pos_delta == pytest.approx(0.10)
    assert comp.market_share_delta == pytest.approx(0.15)
    assert comp.calibration_confidence == pytest.approx(0.20)
    assert comp.guardrail_applied is True

    assert safety.pos_delta == pytest.approx(-0.10)
    assert safety.market_share_delta == pytest.approx(-0.15)
    assert safety.calibration_confidence == pytest.approx(0.20)
    assert safety.guardrail_applied is True


def _seed_asset_graph(store: KnowledgeStore):
    a = KGNode(node_type=NodeType.ASSET, name="Asset A", external_id="asset-a")
    b = KGNode(node_type=NodeType.ASSET, name="Asset B", external_id="asset-b")
    c = KGNode(node_type=NodeType.ASSET, name="Asset C", external_id="asset-c")
    store.add_node(a)
    store.add_node(b)
    store.add_node(c)
    store.add_edge(
        KGEdge(
            source_node_id=a.node_id,
            target_node_id=b.node_id,
            edge_type=EdgeType.SAME_INDICATION,
            confidence=1.0,
        )
    )
    store.add_edge(
        KGEdge(
            source_node_id=a.node_id,
            target_node_id=c.node_id,
            edge_type=EdgeType.SAME_MECHANISM,
            confidence=1.0,
        )
    )
    return a, b, c


def test_engine_generates_proposals_for_related_assets(store: KnowledgeStore):
    src, _, _ = _seed_asset_graph(store)
    signal = _signal(
        signal_id="sig-trigger",
        event_id="evt-trigger",
        asset_id="asset-a",
        event_type=EventType.COMPETITOR_EVENT,
        primary_endpoint_met=False,
    )
    calibration = PropagationCalibration(
        propagation_type=PropagationType.COMPETITOR_FAILURE,
        sample_size=12,
        mean_market_return_t30=0.06,
        raw_pos_delta=0.06,
        raw_market_share_delta=0.06,
        pos_delta=0.06,
        market_share_delta=0.06,
        calibration_confidence=0.60,
        guardrail_applied=False,
    )
    engine = CrossAssetPropagationEngine(store=store)
    generated = engine.generate_proposals(
        trigger_signal=signal,
        source_asset_node_id=src.node_id,
        calibrations={PropagationType.COMPETITOR_FAILURE: calibration},
        created_at=_NOW,
    )
    assert len(generated) == 2
    assert all(isinstance(p, GeneratedPropagationProposal) for p in generated)
    assert {p.target_asset_id for p in generated} == {"asset-b"}
    assert {p.proposal.parameter_path for p in generated} == {
        "trials[*].success_probability",
        "market_model.peak_penetration",
    }
    assert all(p.proposal.asset_id == "asset-b" for p in generated)
    assert all(p.proposal.change_mode.value == "BOUNDED" for p in generated)


def test_engine_review_queue_integration_routes_to_manual_review(store: KnowledgeStore):
    src, _, _ = _seed_asset_graph(store)
    signal = _signal(
        signal_id="sig-safety-trigger",
        event_id="evt-safety-trigger",
        asset_id="asset-a",
        event_type=EventType.SAFETY_SIGNAL,
    )
    calibration = PropagationCalibration(
        propagation_type=PropagationType.CLASS_EFFECT_SAFETY,
        sample_size=15,
        mean_market_return_t30=-0.07,
        raw_pos_delta=-0.07,
        raw_market_share_delta=-0.07,
        pos_delta=-0.07,
        market_share_delta=-0.07,
        calibration_confidence=0.75,
        guardrail_applied=False,
    )
    engine = CrossAssetPropagationEngine(store=store)
    proposals = engine.generate_proposals(
        trigger_signal=signal,
        source_asset_node_id=src.node_id,
        calibrations={PropagationType.CLASS_EFFECT_SAFETY: calibration},
        created_at=_NOW,
    )
    routing = engine.route_proposals(
        trigger_signal=signal,
        proposals=proposals,
        review_queue=ReviewQueue(),
        queued_at=_NOW,
    )
    assert routing.routing.auto_apply == []
    assert len(routing.routing.queued) == len(proposals)


def test_engine_clamps_proposed_values_with_current_value_resolver(store: KnowledgeStore):
    src, _, _ = _seed_asset_graph(store)
    signal = _signal(
        signal_id="sig-trigger-2",
        event_id="evt-trigger-2",
        asset_id="asset-a",
        event_type=EventType.COMPETITOR_EVENT,
        primary_endpoint_met=False,
    )
    calibration = PropagationCalibration(
        propagation_type=PropagationType.COMPETITOR_FAILURE,
        sample_size=50,
        mean_market_return_t30=0.30,
        raw_pos_delta=0.30,
        raw_market_share_delta=0.30,
        pos_delta=0.10,
        market_share_delta=0.15,
        calibration_confidence=1.0,
        guardrail_applied=True,
    )

    def resolver(asset_id: str, parameter_path: str) -> float:
        if parameter_path == "trials[*].success_probability":
            return 0.97
        return 0.94

    engine = CrossAssetPropagationEngine(store=store, current_value_resolver=resolver)
    generated = engine.generate_proposals(
        trigger_signal=signal,
        source_asset_node_id=src.node_id,
        calibrations={PropagationType.COMPETITOR_FAILURE: calibration},
        created_at=_NOW,
    )
    by_path = {p.proposal.parameter_path: p.proposal for p in generated}
    assert by_path["trials[*].success_probability"].proposed_value == pytest.approx(1.0)
    assert by_path["market_model.peak_penetration"].proposed_value == pytest.approx(1.0)
