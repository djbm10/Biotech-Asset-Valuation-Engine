"""
Wave 5 — Calibrated Cross-Asset Propagation.

Implements the required sequence:
1) propagation dataset builder
2) calibration of propagation magnitudes
3) CrossAssetPropagationEngine
4) proposal generation
5) ReviewQueue integration

Design constraints
------------------
- Uses historical resolved `event_outcomes` to calibrate propagation effects.
- Produces review proposals only; no direct valuation application.
- Applies hard guardrails to prevent unstable updates from outliers.
"""
from __future__ import annotations

import math
import statistics
import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_graph import EdgeType, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.phase2 import ReviewQueue, ReviewRoutingResult
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PropagationType(str, Enum):
    """Supported calibrated propagation families."""

    COMPETITOR_FAILURE = "competitor_failure"
    CLASS_EFFECT_SAFETY = "class_effect_safety"


class PropagationGuardrails(BaseModel):
    """
    Hard caps applied after calibration.

    These values are absolute parameter deltas (not percentage-of-proposal).
    """

    max_pos_change_per_event: float = Field(default=0.10, ge=0.0)
    max_market_share_change: float = Field(default=0.15, ge=0.0)


class PropagationObservation(BaseModel):
    """One historical resolved outcome row used for calibration."""

    propagation_type: PropagationType
    event_id: str
    asset_id: str
    event_type: str
    signal_date: date
    trial_phase: Optional[str] = None
    endpoint_type: Optional[str] = None
    market_return_t30: float


class PropagationCalibration(BaseModel):
    """Calibrated magnitude summary for one propagation type."""

    propagation_type: PropagationType
    sample_size: int
    mean_market_return_t30: float
    raw_pos_delta: float
    raw_market_share_delta: float
    pos_delta: float
    market_share_delta: float
    calibration_confidence: float = Field(ge=0.0, le=1.0)
    guardrail_applied: bool = False


class GeneratedPropagationProposal(BaseModel):
    """Propagation proposal + calibration metadata for review workflows."""

    propagation_type: PropagationType
    target_asset_id: str
    sample_size: int
    calibration_confidence: float = Field(ge=0.0, le=1.0)
    proposal: AssumptionChangeProposal


class PropagationRoutingResult(BaseModel):
    """Result of routing generated propagation proposals into ReviewQueue."""

    proposals: list[GeneratedPropagationProposal] = Field(default_factory=list)
    routing: ReviewRoutingResult


class PropagationDatasetBuilder:
    """
    Build calibration observations from resolved outcomes in KnowledgeStore.

    Rows are sourced from `event_outcomes` enriched with structured signal fields
    where available (trial_phase, endpoint_type, failure markers).
    """

    def build(self, store: KnowledgeStore) -> list[PropagationObservation]:
        rows = store._conn.execute(
            """
            SELECT
                eo.event_id,
                eo.asset_id,
                eo.event_type,
                eo.signal_date,
                eo.market_return_t30,
                json_extract(ss.payload_json, '$.trial_phase') AS trial_phase,
                json_extract(ss.payload_json, '$.endpoint_type') AS endpoint_type,
                json_extract(ss.payload_json, '$.primary_endpoint_met') AS primary_endpoint_met,
                json_extract(ss.payload_json, '$.fda_action_type') AS fda_action_type
            FROM event_outcomes eo
            LEFT JOIN events e ON eo.event_id = e.id
            LEFT JOIN structured_signals ss ON e.signal_id = ss.id
            WHERE eo.resolved_t30 = 1
              AND eo.market_return_t30 IS NOT NULL
            ORDER BY eo.signal_date ASC
            """
        ).fetchall()

        out: list[PropagationObservation] = []
        for row in rows:
            row_dict = dict(row)
            propagation_type = self._classify_row(row_dict)
            if propagation_type is None:
                continue

            signal_date = row_dict["signal_date"]
            parsed_date = (
                date.fromisoformat(signal_date)
                if isinstance(signal_date, str)
                else signal_date
            )
            out.append(
                PropagationObservation(
                    propagation_type=propagation_type,
                    event_id=str(row_dict["event_id"]),
                    asset_id=str(row_dict["asset_id"]),
                    event_type=str(row_dict.get("event_type") or ""),
                    signal_date=parsed_date,
                    trial_phase=row_dict.get("trial_phase"),
                    endpoint_type=row_dict.get("endpoint_type"),
                    market_return_t30=float(row_dict["market_return_t30"]),
                )
            )
        return out

    @staticmethod
    def _classify_row(row: dict) -> Optional[PropagationType]:
        event_type = str(row.get("event_type") or "")
        if event_type == EventType.SAFETY_SIGNAL.value:
            return PropagationType.CLASS_EFFECT_SAFETY

        # Competitor failure evidence:
        # 1) explicit competitor_event with failure marker OR
        # 2) direct failure event classes (rejection/discontinuation).
        if event_type in {
            EventType.FDA_REJECTION.value,
            EventType.PROGRAM_DISCONTINUATION.value,
        }:
            return PropagationType.COMPETITOR_FAILURE

        if event_type != EventType.COMPETITOR_EVENT.value:
            return None

        primary_endpoint_met = row.get("primary_endpoint_met")
        fda_action_type = row.get("fda_action_type")
        if primary_endpoint_met in (0, False, "0", "false", "False"):
            return PropagationType.COMPETITOR_FAILURE
        if fda_action_type in {"crl", "hold"}:
            return PropagationType.COMPETITOR_FAILURE
        return None


class PropagationCalibrator:
    """Estimate propagation magnitudes from historical observations."""

    def __init__(
        self,
        *,
        guardrails: Optional[PropagationGuardrails] = None,
        full_confidence_sample_size: int = 20,
    ) -> None:
        self.guardrails = guardrails or PropagationGuardrails()
        self.full_confidence_sample_size = max(1, full_confidence_sample_size)

    def calibrate(
        self,
        observations: list[PropagationObservation],
    ) -> dict[PropagationType, PropagationCalibration]:
        grouped: dict[PropagationType, list[PropagationObservation]] = {}
        for obs in observations:
            grouped.setdefault(obs.propagation_type, []).append(obs)

        results: dict[PropagationType, PropagationCalibration] = {}
        for propagation_type, rows in grouped.items():
            sample_size = len(rows)
            mean_return = float(statistics.fmean(r.market_return_t30 for r in rows))
            direction = 1.0 if propagation_type == PropagationType.COMPETITOR_FAILURE else -1.0

            # Translate empirical mean return to assumption deltas.
            raw_pos_delta = direction * abs(mean_return)
            raw_market_share_delta = direction * abs(mean_return)

            pos_delta = self._clip(
                raw_pos_delta,
                cap=self.guardrails.max_pos_change_per_event,
            )
            market_share_delta = self._clip(
                raw_market_share_delta,
                cap=self.guardrails.max_market_share_change,
            )
            confidence = min(1.0, sample_size / float(self.full_confidence_sample_size))
            guardrail_applied = (
                not math.isclose(raw_pos_delta, pos_delta, rel_tol=0.0, abs_tol=1e-12)
                or not math.isclose(
                    raw_market_share_delta,
                    market_share_delta,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            )

            results[propagation_type] = PropagationCalibration(
                propagation_type=propagation_type,
                sample_size=sample_size,
                mean_market_return_t30=mean_return,
                raw_pos_delta=raw_pos_delta,
                raw_market_share_delta=raw_market_share_delta,
                pos_delta=pos_delta,
                market_share_delta=market_share_delta,
                calibration_confidence=confidence,
                guardrail_applied=guardrail_applied,
            )
        return results

    @staticmethod
    def _clip(value: float, *, cap: float) -> float:
        return max(-cap, min(cap, value))


CurrentValueResolver = Callable[[str, str], Optional[float]]


class CrossAssetPropagationEngine:
    """
    Generate calibrated cross-asset propagation proposals and route to review.
    """

    def __init__(
        self,
        *,
        store: KnowledgeStore,
        dataset_builder: Optional[PropagationDatasetBuilder] = None,
        calibrator: Optional[PropagationCalibrator] = None,
        guardrails: Optional[PropagationGuardrails] = None,
        current_value_resolver: Optional[CurrentValueResolver] = None,
    ) -> None:
        self.store = store
        self.guardrails = guardrails or PropagationGuardrails()
        self.dataset_builder = dataset_builder or PropagationDatasetBuilder()
        self.calibrator = calibrator or PropagationCalibrator(guardrails=self.guardrails)
        self.current_value_resolver = current_value_resolver

    def build_calibrations(self) -> dict[PropagationType, PropagationCalibration]:
        observations = self.dataset_builder.build(self.store)
        return self.calibrator.calibrate(observations)

    def generate_proposals(
        self,
        *,
        trigger_signal: StructuredSignal,
        source_asset_node_id: Optional[str] = None,
        calibrations: Optional[dict[PropagationType, PropagationCalibration]] = None,
        created_at: Optional[datetime] = None,
    ) -> list[GeneratedPropagationProposal]:
        created_at = created_at or _utcnow()
        propagation_type = self._trigger_type(trigger_signal)
        if propagation_type is None:
            return []

        calibration_map = calibrations or self.build_calibrations()
        calibration = calibration_map.get(propagation_type)
        if calibration is None or calibration.sample_size <= 0:
            return []

        edge_type = self._edge_type_for(propagation_type)
        target_asset_ids = self._target_asset_ids(
            trigger_signal=trigger_signal,
            source_asset_node_id=source_asset_node_id,
            edge_type=edge_type,
        )

        generated: list[GeneratedPropagationProposal] = []
        for target_asset_id in target_asset_ids:
            generated.extend(
                self._proposals_for_target(
                    trigger_signal=trigger_signal,
                    target_asset_id=target_asset_id,
                    calibration=calibration,
                    created_at=created_at,
                )
            )
        return generated

    def route_proposals(
        self,
        *,
        trigger_signal: StructuredSignal,
        proposals: list[GeneratedPropagationProposal],
        review_queue: Optional[ReviewQueue] = None,
        queued_at: Optional[datetime] = None,
    ) -> PropagationRoutingResult:
        queue = review_queue or ReviewQueue()
        routing = queue.route(
            trigger_signal,
            [p.proposal for p in proposals],
            queued_at=queued_at,
        )
        return PropagationRoutingResult(proposals=proposals, routing=routing)

    @staticmethod
    def _trigger_type(signal: StructuredSignal) -> Optional[PropagationType]:
        if signal.event_type == EventType.SAFETY_SIGNAL:
            return PropagationType.CLASS_EFFECT_SAFETY
        if signal.event_type != EventType.COMPETITOR_EVENT:
            return None
        if signal.primary_endpoint_met is False:
            return PropagationType.COMPETITOR_FAILURE
        if signal.fda_action_type in {"crl", "hold"}:
            return PropagationType.COMPETITOR_FAILURE
        return None

    @staticmethod
    def _edge_type_for(propagation_type: PropagationType) -> EdgeType:
        if propagation_type == PropagationType.COMPETITOR_FAILURE:
            return EdgeType.SAME_INDICATION
        return EdgeType.SAME_MECHANISM

    def _target_asset_ids(
        self,
        *,
        trigger_signal: StructuredSignal,
        source_asset_node_id: Optional[str],
        edge_type: EdgeType,
    ) -> list[str]:
        resolved_source_node_id = source_asset_node_id
        if resolved_source_node_id is None:
            source_node = self.store.find_node_by_external_id(
                NodeType.ASSET,
                trigger_signal.asset_id,
            )
            if source_node is None:
                return []
            resolved_source_node_id = source_node.node_id

        neighbors = self.store.neighbors(resolved_source_node_id, edge_type=edge_type)
        target_ids = sorted(
            {
                node.external_id
                for node in neighbors
                if node.node_type == NodeType.ASSET
                and node.external_id is not None
                and node.external_id != trigger_signal.asset_id
            }
        )
        return target_ids

    def _proposals_for_target(
        self,
        *,
        trigger_signal: StructuredSignal,
        target_asset_id: str,
        calibration: PropagationCalibration,
        created_at: datetime,
    ) -> list[GeneratedPropagationProposal]:
        proposals: list[GeneratedPropagationProposal] = []
        for parameter_path, delta in (
            ("trials[*].success_probability", calibration.pos_delta),
            ("market_model.peak_penetration", calibration.market_share_delta),
        ):
            current_value = self._resolve_current_value(
                asset_id=target_asset_id,
                parameter_path=parameter_path,
            )
            proposed_value = max(0.0, min(1.0, current_value + delta))
            if math.isclose(current_value, proposed_value, rel_tol=0.0, abs_tol=1e-12):
                continue

            proposal = AssumptionChangeProposal(
                id=self._proposal_id(
                    trigger_signal=trigger_signal,
                    target_asset_id=target_asset_id,
                    parameter_path=parameter_path,
                ),
                signal_id=trigger_signal.id,
                asset_id=target_asset_id,
                engine_asset_id=target_asset_id,
                parameter_path=parameter_path,
                current_value=float(current_value),
                proposed_value=float(proposed_value),
                change_mode=ChangeMode.BOUNDED,
                bound_pct=self._bound_pct(current_value, parameter_path),
                event_type=trigger_signal.event_type,
                rationale=(
                    f"Cross-asset propagation ({calibration.propagation_type.value}) "
                    f"from source asset {trigger_signal.asset_id}; "
                    f"sample_size={calibration.sample_size}, "
                    f"calibration_confidence={calibration.calibration_confidence:.2f}, "
                    f"mean_return_t30={calibration.mean_market_return_t30:.4f}, "
                    f"guardrail_applied={calibration.guardrail_applied}"
                ),
                supporting_signal_ids=[trigger_signal.id],
                created_at=created_at,
            )
            proposals.append(
                GeneratedPropagationProposal(
                    propagation_type=calibration.propagation_type,
                    target_asset_id=target_asset_id,
                    sample_size=calibration.sample_size,
                    calibration_confidence=calibration.calibration_confidence,
                    proposal=proposal,
                )
            )

        return proposals

    def _resolve_current_value(self, *, asset_id: str, parameter_path: str) -> float:
        if self.current_value_resolver is not None:
            resolved = self.current_value_resolver(asset_id, parameter_path)
            if resolved is not None:
                return float(resolved)
        if parameter_path == "trials[*].success_probability":
            return 0.50
        return 0.20

    def _bound_pct(self, current_value: float, parameter_path: str) -> float:
        if parameter_path == "trials[*].success_probability":
            cap = self.guardrails.max_pos_change_per_event
        else:
            cap = self.guardrails.max_market_share_change
        if current_value <= 0.0:
            return 100.0
        return abs(cap / current_value) * 100.0

    @staticmethod
    def _proposal_id(
        *,
        trigger_signal: StructuredSignal,
        target_asset_id: str,
        parameter_path: str,
    ) -> str:
        key = (
            f"propagation|{trigger_signal.id}|{trigger_signal.event_id}|"
            f"{target_asset_id}|{parameter_path}"
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
