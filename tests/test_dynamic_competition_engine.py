from __future__ import annotations

from datetime import date, datetime, timezone

from bve.entities.trial import TrialPhase
from bve.intelligence.dynamic_competition_engine import (
    CompetitionEventDirection,
    DynamicCompetitionEngine,
)
from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.science_engine import ScienceAssessment, ScienceSubscore
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.models.probability_stack import ProbabilityStackInputs
from bve.models.regulatory_inference import (
    ApprovalPathway,
    RegulatoryInferenceResult,
    RegulatoryProfile,
    RegulatoryScenario,
    RegulatoryScenarioProbability,
)

_NOW = datetime(2026, 4, 17, 14, 0, tzinfo=timezone.utc)


def _store() -> KnowledgeStore:
    return KnowledgeStore(db_path=":memory:")


def _seed_graph(store: KnowledgeStore) -> tuple[KGNode, KGNode, KGNode]:
    source = KGNode(
        node_type=NodeType.ASSET,
        name="CompA",
        external_id="asset-comp-a",
        properties={
            "company": "Co A",
            "phase": "phase_3",
            "status": "RECRUITING",
            "mechanism": "EGFR inhibitor",
            "moa_summary": {"target_class": "egfr"},
        },
    )
    peer = KGNode(
        node_type=NodeType.ASSET,
        name="PeerB",
        external_id="asset-peer-b",
        properties={
            "company": "Co B",
            "phase": "phase_3",
            "status": "ACTIVE_NOT_RECRUITING",
            "mechanism": "EGFR inhibitor",
            "moa_summary": {"target_class": "egfr"},
        },
    )
    adjacent = KGNode(
        node_type=NodeType.ASSET,
        name="AdjC",
        external_id="asset-adj-c",
        properties={
            "company": "Co C",
            "phase": "phase_2",
            "status": "RECRUITING",
            "mechanism": "TKI",
            "moa_summary": {"target_class": "egfr"},
        },
    )
    store.add_node(source)
    store.add_node(peer)
    store.add_node(adjacent)
    store.add_edge(
        KGEdge(
            source_node_id=source.node_id,
            target_node_id=peer.node_id,
            edge_type=EdgeType.COMPETES_WITH,
            confidence=1.0,
        )
    )
    store.add_edge(
        KGEdge(
            source_node_id=source.node_id,
            target_node_id=peer.node_id,
            edge_type=EdgeType.SAME_TARGET,
            confidence=1.0,
        )
    )
    store.add_edge(
        KGEdge(
            source_node_id=source.node_id,
            target_node_id=peer.node_id,
            edge_type=EdgeType.COMPETITOR_OVERLAPS_ASSET,
            confidence=1.0,
        )
    )
    store.add_edge(
        KGEdge(
            source_node_id=source.node_id,
            target_node_id=adjacent.node_id,
            edge_type=EdgeType.SAME_INDICATION,
            confidence=1.0,
        )
    )
    return source, peer, adjacent


def _signal(
    *,
    signal_id: str,
    asset_id: str,
    event_type: EventType,
    primary_endpoint_met: bool | None = None,
) -> StructuredSignal:
    return StructuredSignal(
        id=signal_id,
        event_id=f"evt-{signal_id}",
        asset_id=asset_id,
        company_id=f"company-{asset_id}",
        event_type=event_type,
        signal_date=date(2026, 4, 17),
        trial_phase=TrialPhase.PHASE_3,
        primary_endpoint_met=primary_endpoint_met,
        extraction_confidence=0.92,
        extraction_model="unit-test",
        created_at=_NOW,
    )


def _science_assessment() -> ScienceAssessment:
    return ScienceAssessment(
        asset_id="asset-peer-b",
        asset_name="PeerB",
        science_score=0.72,
        design_score=0.70,
        confidence_band="high",
        subscores=[
            ScienceSubscore(
                name="mechanism_plausibility",
                value=0.74,
                confidence=0.8,
                rationale="Mechanism is grounded.",
            ),
            ScienceSubscore(
                name="target_validation",
                value=0.71,
                confidence=0.8,
                rationale="Target is validated.",
            ),
            ScienceSubscore(
                name="modality_specific_risk",
                value=0.69,
                confidence=0.75,
                rationale="Modality risk is acceptable.",
            ),
            ScienceSubscore(
                name="biomarker_logic_quality",
                value=0.70,
                confidence=0.75,
                rationale="Biomarker strategy is coherent.",
            ),
            ScienceSubscore(
                name="translational_evidence_quality",
                value=0.68,
                confidence=0.72,
                rationale="Translational package is solid.",
            ),
            ScienceSubscore(
                name="analog_winners_failures_similarity",
                value=0.66,
                confidence=0.70,
                rationale="Some analog support exists.",
            ),
            ScienceSubscore(
                name="safety_signal_seriousness",
                value=0.75,
                confidence=0.75,
                rationale="Safety profile is manageable.",
            ),
            ScienceSubscore(
                name="trial_design_quality",
                value=0.69,
                confidence=0.74,
                rationale="Design quality is acceptable.",
            ),
        ],
        top_positives=["Validated target."],
        top_risks=["Crowded class."],
        nearest_analogs=[],
        kill_criteria=["Unexpected safety signal."],
        plain_english_summary="Science is credible.",
    )


def _regulatory_inference() -> RegulatoryInferenceResult:
    return RegulatoryInferenceResult(
        profile=RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            endpoint_type="surrogate_validated",
            safety_serious_events=False,
            adcom_precedent="neutral",
        ),
        scenarios=[
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.CLEAN_APPROVAL,
                probability=0.55,
                pdufa_months=7,
                rationale="Base case.",
            ),
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.NARROW_LABEL,
                probability=0.20,
                pdufa_months=8,
                rationale="Label risk.",
            ),
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.HIGH_POSTMARKET_BURDEN,
                probability=0.10,
                pdufa_months=9,
                rationale="Burden risk.",
            ),
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.DELAYED_APPROVAL,
                probability=0.10,
                pdufa_months=12,
                rationale="Delay risk.",
            ),
            RegulatoryScenarioProbability(
                scenario=RegulatoryScenario.CRL,
                probability=0.05,
                pdufa_months=7,
                rationale="CRL tail.",
            ),
        ],
        dominant_scenario=RegulatoryScenario.CLEAN_APPROVAL,
        approval_probability=0.75,
        expected_pdufa_months=8.1,
        risk_flags=[],
        pos_modifier=0.02,
    )


def test_phase_f_builds_live_competitor_map_from_graph_neighbors() -> None:
    store = _store()
    try:
        source, _, _ = _seed_graph(store)
        engine = DynamicCompetitionEngine()

        result = engine.build_live_competitor_map(store, asset_id="asset-comp-a", as_of=_NOW)

        assert result.confidence > 0.0
        assert "competitive_landscape_agent" in result.provenance
        assert result.downstream_dependencies == [
            "market_model",
            "probability_stack",
            "market_access_engine",
            "catalyst_payoff_trees",
        ]
        value = result.value
        assert value["asset_id"] == "asset-comp-a"
        assert value["entries"][0]["drug"] == "PeerB"
        assert value["entries"][0]["source_node_id"] != source.node_id
    finally:
        store.close()


def test_phase_f_positive_competitor_event_rerates_exposed_assets_downward() -> None:
    store = _store()
    try:
        source, _, _ = _seed_graph(store)
        engine = DynamicCompetitionEngine()

        result = engine.rerate_from_signal(
            store,
            trigger_signal=_signal(
                signal_id="sig-approval",
                asset_id="asset-comp-a",
                event_type=EventType.FDA_APPROVAL,
            ),
            source_asset_node_id=source.node_id,
            as_of=_NOW,
        )

        assert result.event_direction == CompetitionEventDirection.THREAT_INCREASE
        assert {item.asset_id for item in result.reratings} == {"asset-peer-b", "asset-adj-c"}

        peer = next(item for item in result.reratings if item.asset_id == "asset-peer-b")
        assert peer.market_share_delta.value < 0
        assert peer.peak_sales_delta.value < 0
        assert peer.pos_delta.value < 0
        assert peer.access_pressure_delta.value > 0
        assert peer.years_to_peak_delta.value > 0
        assert peer.catalyst_importance_delta.value > 0
        assert "probability_stack" in peer.pos_delta.downstream_dependencies
        assert "edge:same_target" in peer.pos_delta.provenance
        assert peer.exposure.overlap_score > 0.9

        updated = engine.apply_to_probability_stack_inputs(
            ProbabilityStackInputs(
                asset_id="asset-peer-b",
                asset_name="PeerB",
                base_pos=0.55,
                science_assessment=_science_assessment(),
                regulatory_inference=_regulatory_inference(),
                years_to_approval=2.5,
                financing_risk_score=0.25,
                market_access_pressure_score=0.30,
                management_execution_score=0.65,
                competitor_readthrough_score=0.60,
            ),
            peer,
        )
        assert updated.base_pos < 0.55
        assert updated.market_access_pressure_score > 0.30
        assert updated.competitor_readthrough_score < 0.60
    finally:
        store.close()


def test_phase_f_competitor_setback_rerates_exposed_assets_upward() -> None:
    store = _store()
    try:
        source, _, _ = _seed_graph(store)
        engine = DynamicCompetitionEngine()

        result = engine.rerate_from_signal(
            store,
            trigger_signal=_signal(
                signal_id="sig-fail",
                asset_id="asset-comp-a",
                event_type=EventType.COMPETITOR_EVENT,
                primary_endpoint_met=False,
            ),
            source_asset_node_id=source.node_id,
            as_of=_NOW,
        )

        peer = next(item for item in result.reratings if item.asset_id == "asset-peer-b")
        assert result.event_direction == CompetitionEventDirection.THREAT_DECREASE
        assert peer.market_share_delta.value > 0
        assert peer.peak_sales_delta.value > 0
        assert peer.pos_delta.value > 0
        assert peer.access_pressure_delta.value < 0
        assert peer.years_to_peak_delta.value < 0
        assert peer.scenario_pressure_delta.value > 0
        assert peer.market_share_delta.freshness == _NOW
        assert peer.market_share_delta.explainability
    finally:
        store.close()
