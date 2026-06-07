"""Phase F dynamic competition engine."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.intelligence.competitive_landscape_agent import (
    CompetitiveLandscape,
    CompetitiveLandscapeAgent,
)
from bve.intelligence.knowledge_graph import EdgeType, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.models.probability_stack import ProbabilityStackInputs


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompetitionEventDirection(str, Enum):
    THREAT_INCREASE = "threat_increase"
    THREAT_DECREASE = "threat_decrease"


class CompetitionModuleOutput(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class CompetitionExposure(BaseModel):
    asset_id: str
    asset_name: str
    tags: list[str] = Field(default_factory=list)
    overlap_score: float = Field(ge=0.0, le=1.0)


class DynamicCompetitionRerating(BaseModel):
    asset_id: str
    asset_name: str
    source_asset_id: str
    source_asset_name: str
    trigger_event_type: EventType
    event_direction: CompetitionEventDirection
    exposure: CompetitionExposure
    market_share_delta: CompetitionModuleOutput
    years_to_peak_delta: CompetitionModuleOutput
    peak_sales_delta: CompetitionModuleOutput
    access_pressure_delta: CompetitionModuleOutput
    pos_delta: CompetitionModuleOutput
    catalyst_importance_delta: CompetitionModuleOutput
    scenario_pressure_delta: CompetitionModuleOutput
    competitor_readthrough_score_delta: CompetitionModuleOutput
    plain_english_summary: str


class DynamicCompetitionResult(BaseModel):
    source_asset_id: str
    source_asset_name: str
    trigger_event_type: EventType
    event_direction: CompetitionEventDirection
    live_competitor_map: CompetitionModuleOutput
    reratings: list[DynamicCompetitionRerating] = Field(default_factory=list)
    plain_english_summary: str


class DynamicCompetitionEngine:
    """
    Event-driven competition rerating layer.

    Phase F requires two things:
    1) maintain a live competitor map for every asset
    2) re-rate exposed assets when meaningful competitor events occur

    This engine keeps both pieces in one place by reusing the deterministic
    competitive landscape agent as the asset map and layering bounded
    assumption deltas on top when a competitor event lands.
    """

    _TAG_WEIGHTS: dict[str, float] = {
        "competitor_overlaps_asset": 0.95,
        "same_target": 0.90,
        "competes_with": 0.85,
        "same_mechanism": 0.75,
        "same_indication": 0.65,
    }

    _DOWNSTREAMS: dict[str, list[str]] = {
        "market_share_delta": ["market_model.peak_penetration", "commercialization_engine"],
        "years_to_peak_delta": ["market_model.uptake_curve", "commercialization_engine"],
        "peak_sales_delta": ["market_expectations_engine", "valuation"],
        "access_pressure_delta": ["market_access_engine", "probability_stack"],
        "pos_delta": ["probability_stack", "approval_scenarios"],
        "catalyst_importance_delta": ["catalyst_payoff_trees", "portfolio_decision_engine"],
        "scenario_pressure_delta": ["approval_scenarios", "catalyst_payoff_trees"],
        "competitor_readthrough_score_delta": ["probability_stack"],
    }

    def __init__(
        self,
        *,
        landscape_agent: Optional[CompetitiveLandscapeAgent] = None,
    ) -> None:
        self.landscape_agent = landscape_agent or CompetitiveLandscapeAgent()

    def build_live_competitor_map(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> CompetitionModuleOutput:
        as_of = as_of or _utcnow()
        landscape = self.landscape_agent.generate(
            store,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=as_of,
        )
        confidence = self._map_confidence(landscape)
        return CompetitionModuleOutput(
            value=landscape.model_dump(),
            confidence=confidence,
            provenance=[f"knowledge_graph:asset:{asset_id}", "competitive_landscape_agent"],
            freshness=as_of,
            explainability=(
                "Live competitor map is built from graph neighbors connected by direct "
                "competition, shared indication, mechanism, or target overlap."
            ),
            downstream_dependencies=[
                "market_model",
                "probability_stack",
                "market_access_engine",
                "catalyst_payoff_trees",
            ],
        )

    def rerate_from_signal(
        self,
        store: KnowledgeStore,
        *,
        trigger_signal: StructuredSignal,
        source_asset_node_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> DynamicCompetitionResult:
        as_of = as_of or _utcnow()
        source_node = (
            store.get_node(source_asset_node_id)
            if source_asset_node_id is not None
            else store.find_node_by_external_id(NodeType.ASSET, trigger_signal.asset_id)
        )
        source_asset_name = source_node.name if source_node is not None else trigger_signal.asset_id
        direction, severity, rationale = self._classify_event(trigger_signal)
        live_map = self.build_live_competitor_map(
            store,
            asset_id=trigger_signal.asset_id,
            company_id=trigger_signal.company_id,
            as_of=as_of,
        )

        if source_node is None:
            return DynamicCompetitionResult(
                source_asset_id=trigger_signal.asset_id,
                source_asset_name=source_asset_name,
                trigger_event_type=trigger_signal.event_type,
                event_direction=direction,
                live_competitor_map=live_map,
                reratings=[],
                plain_english_summary=(
                    f"No asset node was found for trigger asset {trigger_signal.asset_id}; "
                    "the live competitor map was produced but no peer reratings were generated."
                ),
            )

        reratings: list[DynamicCompetitionRerating] = []
        for target_node, tags in self._exposed_assets(store, source_node):
            overlap = self._overlap_score(tags)
            confidence = round(min(0.95, 0.30 + overlap * 0.35 + severity * 0.35), 4)
            magnitude = severity * overlap
            reratings.append(
                self._build_rerating(
                    target_node=target_node,
                    source_node=source_node,
                    trigger_signal=trigger_signal,
                    direction=direction,
                    overlap=overlap,
                    tags=tags,
                    confidence=confidence,
                    magnitude=magnitude,
                    rationale=rationale,
                    as_of=as_of,
                )
            )

        summary = (
            f"Triggered {len(reratings)} dynamic competition rerating(s) from "
            f"{source_asset_name} {trigger_signal.event_type.value}."
        )
        return DynamicCompetitionResult(
            source_asset_id=trigger_signal.asset_id,
            source_asset_name=source_asset_name,
            trigger_event_type=trigger_signal.event_type,
            event_direction=direction,
            live_competitor_map=live_map,
            reratings=sorted(reratings, key=lambda item: (-item.exposure.overlap_score, item.asset_name)),
            plain_english_summary=summary,
        )

    def apply_to_probability_stack_inputs(
        self,
        inputs: ProbabilityStackInputs,
        rerating: DynamicCompetitionRerating,
    ) -> ProbabilityStackInputs:
        return inputs.model_copy(
            update={
                "base_pos": self._clamp01(inputs.base_pos + float(rerating.pos_delta.value)),
                "market_access_pressure_score": self._clamp01(
                    inputs.market_access_pressure_score
                    + float(rerating.access_pressure_delta.value)
                ),
                "competitor_readthrough_score": self._clamp01(
                    inputs.competitor_readthrough_score
                    + float(rerating.competitor_readthrough_score_delta.value)
                ),
            }
        )

    def _build_rerating(
        self,
        *,
        target_node: KGNode,
        source_node: KGNode,
        trigger_signal: StructuredSignal,
        direction: CompetitionEventDirection,
        overlap: float,
        tags: list[str],
        confidence: float,
        magnitude: float,
        rationale: str,
        as_of: datetime,
    ) -> DynamicCompetitionRerating:
        sign = -1.0 if direction == CompetitionEventDirection.THREAT_INCREASE else 1.0
        asset_id = target_node.external_id or target_node.node_id
        source_asset_id = source_node.external_id or source_node.node_id
        provenance = [
            f"signal:{trigger_signal.id}",
            f"source_asset:{source_asset_id}",
            f"target_asset:{asset_id}",
            *[f"edge:{tag}" for tag in tags],
        ]
        exposure = CompetitionExposure(
            asset_id=asset_id,
            asset_name=target_node.name,
            tags=tags,
            overlap_score=round(overlap, 4),
        )
        market_share_delta = sign * min(0.15, 0.15 * magnitude)
        years_to_peak_delta = -sign * min(1.5, 1.5 * magnitude)
        peak_sales_delta = sign * min(0.20, 0.20 * magnitude)
        access_pressure_delta = -sign * min(0.12, 0.12 * magnitude)
        pos_delta = sign * min(0.08, 0.08 * magnitude)
        catalyst_importance_delta = min(0.10, 0.10 * magnitude)
        scenario_pressure_delta = sign * min(0.18, 0.18 * magnitude)
        competitor_readthrough_delta = sign * min(0.20, 0.20 * magnitude)
        summary = (
            f"{target_node.name} rerated because {source_node.name} had a {trigger_signal.event_type.value}. "
            f"Exposure tags: {', '.join(tags)}. {rationale}"
        )
        return DynamicCompetitionRerating(
            asset_id=asset_id,
            asset_name=target_node.name,
            source_asset_id=source_asset_id,
            source_asset_name=source_node.name,
            trigger_event_type=trigger_signal.event_type,
            event_direction=direction,
            exposure=exposure,
            market_share_delta=self._delta_output(
                value=market_share_delta,
                confidence=confidence,
                provenance=provenance,
                freshness=as_of,
                explainability="Competitor threat changes expected share capture in overlapping segments.",
                key="market_share_delta",
            ),
            years_to_peak_delta=self._delta_output(
                value=years_to_peak_delta,
                confidence=confidence,
                provenance=provenance,
                freshness=as_of,
                explainability="Competitive pressure changes the time needed to reach peak share.",
                key="years_to_peak_delta",
            ),
            peak_sales_delta=self._delta_output(
                value=peak_sales_delta,
                confidence=confidence,
                provenance=provenance,
                freshness=as_of,
                explainability="Peak sales move with expected share availability and class pressure.",
                key="peak_sales_delta",
            ),
            access_pressure_delta=self._delta_output(
                value=access_pressure_delta,
                confidence=confidence,
                provenance=provenance,
                freshness=as_of,
                explainability="Competitor wins or setbacks alter payer pressure and access assumptions.",
                key="access_pressure_delta",
            ),
            pos_delta=self._delta_output(
                value=pos_delta,
                confidence=confidence,
                provenance=provenance,
                freshness=as_of,
                explainability="Meaningful competitor events change approval odds through readthrough and market context.",
                key="pos_delta",
            ),
            catalyst_importance_delta=self._delta_output(
                value=catalyst_importance_delta,
                confidence=confidence,
                provenance=provenance,
                freshness=as_of,
                explainability="Competitor moves raise the information value of the next catalyst for exposed assets.",
                key="catalyst_importance_delta",
            ),
            scenario_pressure_delta=self._delta_output(
                value=scenario_pressure_delta,
                confidence=confidence,
                provenance=provenance,
                freshness=as_of,
                explainability="Scenario trees shift when competitor evidence changes the base case for class dynamics.",
                key="scenario_pressure_delta",
            ),
            competitor_readthrough_score_delta=self._delta_output(
                value=competitor_readthrough_delta,
                confidence=confidence,
                provenance=provenance,
                freshness=as_of,
                explainability="Commercial realization in the PoS stack should move with competitor readthrough.",
                key="competitor_readthrough_score_delta",
            ),
            plain_english_summary=summary,
        )

    def _delta_output(
        self,
        *,
        value: float,
        confidence: float,
        provenance: list[str],
        freshness: datetime,
        explainability: str,
        key: str,
    ) -> CompetitionModuleOutput:
        return CompetitionModuleOutput(
            value=round(value, 4),
            confidence=confidence,
            provenance=provenance,
            freshness=freshness,
            explainability=explainability,
            downstream_dependencies=self._DOWNSTREAMS[key],
        )

    def _exposed_assets(
        self,
        store: KnowledgeStore,
        source_node: KGNode,
    ) -> list[tuple[KGNode, list[str]]]:
        tag_sets: dict[str, set[str]] = {}
        for edge_type, label in (
            (EdgeType.COMPETITOR_OVERLAPS_ASSET, "competitor_overlaps_asset"),
            (EdgeType.SAME_TARGET, "same_target"),
            (EdgeType.COMPETES_WITH, "competes_with"),
            (EdgeType.SAME_MECHANISM, "same_mechanism"),
            (EdgeType.SAME_INDICATION, "same_indication"),
        ):
            for node in store.neighbors(source_node.node_id, edge_type=edge_type):
                if node.node_type != NodeType.ASSET or node.node_id == source_node.node_id:
                    continue
                tag_sets.setdefault(node.node_id, set()).add(label)

        results: list[tuple[KGNode, list[str]]] = []
        for node_id, tags in tag_sets.items():
            node = store.get_node(node_id)
            if node is None:
                continue
            results.append((node, sorted(tags)))
        return results

    def _classify_event(
        self,
        trigger_signal: StructuredSignal,
    ) -> tuple[CompetitionEventDirection, float, str]:
        event_type = trigger_signal.event_type
        if event_type == EventType.COMPETITOR_EVENT:
            if trigger_signal.primary_endpoint_met is False:
                return (
                    CompetitionEventDirection.THREAT_DECREASE,
                    0.90,
                    "Competitor setback should relieve pressure on overlapping assets.",
                )
            if trigger_signal.primary_endpoint_met is True:
                return (
                    CompetitionEventDirection.THREAT_INCREASE,
                    0.85,
                    "Competitor readout success should increase pressure on overlapping assets.",
                )
            return (
                CompetitionEventDirection.THREAT_INCREASE,
                0.60,
                "Generic competitor event is treated as a moderate increase in pressure.",
            )
        if event_type in {
            EventType.FDA_APPROVAL,
            EventType.LABEL_EXPANSION,
            EventType.PAYER_COVERAGE,
            EventType.PARTNERSHIP,
            EventType.FINANCING,
        }:
            severity = {
                EventType.FDA_APPROVAL: 0.95,
                EventType.LABEL_EXPANSION: 0.85,
                EventType.PAYER_COVERAGE: 0.70,
                EventType.PARTNERSHIP: 0.60,
                EventType.FINANCING: 0.45,
            }[event_type]
            return (
                CompetitionEventDirection.THREAT_INCREASE,
                severity,
                "Competitor de-risking or commercial momentum should raise pressure on peers.",
            )
        if event_type in {
            EventType.FDA_REJECTION,
            EventType.REGULATORY_HOLD,
            EventType.PROGRAM_DISCONTINUATION,
            EventType.SAFETY_SIGNAL,
        }:
            severity = {
                EventType.FDA_REJECTION: 0.90,
                EventType.REGULATORY_HOLD: 0.85,
                EventType.PROGRAM_DISCONTINUATION: 0.95,
                EventType.SAFETY_SIGNAL: 0.75,
            }[event_type]
            return (
                CompetitionEventDirection.THREAT_DECREASE,
                severity,
                "Competitor regulatory or safety setbacks should relieve pressure on peers.",
            )
        return (
            CompetitionEventDirection.THREAT_INCREASE,
            0.50,
            "Unsupported event types default to a low-confidence moderate pressure increase.",
        )

    def _map_confidence(self, landscape: CompetitiveLandscape) -> float:
        if not landscape.entries:
            return 0.35
        top_risk = max((entry.risk_score for entry in landscape.entries), default=0.0)
        return round(min(0.95, 0.45 + min(0.40, top_risk * 0.4)), 4)

    def _overlap_score(self, tags: list[str]) -> float:
        if not tags:
            return 0.0
        weighted = max(self._TAG_WEIGHTS.get(tag, 0.5) for tag in tags)
        bonus = min(0.05, 0.02 * max(0, len(tags) - 1))
        return min(1.0, weighted + bonus)

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, round(value, 4)))
