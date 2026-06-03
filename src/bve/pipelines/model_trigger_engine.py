"""
Routes RoutedEvents to the appropriate modules and deduplicates recompute requests.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from bve.pipelines.event_router import RoutedEvent
from bve.evidence.classifier import EventType
from bve.evidence.materiality import MaterialityTier


class RecomputeModule(str, Enum):
    PROBABILITY_STACK = "probability_stack"
    MARKET_EXPECTATIONS = "market_expectations"
    SCIENCE_SCORE = "science_score"
    FINANCING_RISK = "financing_risk"
    COMPETITION_GRAPH = "competition_graph"
    RECOMMENDATION = "recommendation"
    DOSSIER = "dossier"


# Event type → modules to recompute (deterministic routing table)
EVENT_MODULE_MAP: dict[EventType, list[RecomputeModule]] = {
    EventType.CATALYST_UPDATE: [
        RecomputeModule.PROBABILITY_STACK,
        RecomputeModule.MARKET_EXPECTATIONS,
        RecomputeModule.RECOMMENDATION,
    ],
    EventType.FDA_ACTION: [
        RecomputeModule.PROBABILITY_STACK,
        RecomputeModule.MARKET_EXPECTATIONS,
        RecomputeModule.RECOMMENDATION,
        RecomputeModule.DOSSIER,
    ],
    EventType.TRIAL_CHANGE: [
        RecomputeModule.PROBABILITY_STACK,
        RecomputeModule.SCIENCE_SCORE,
        RecomputeModule.RECOMMENDATION,
    ],
    EventType.FINANCING: [
        RecomputeModule.FINANCING_RISK,
        RecomputeModule.MARKET_EXPECTATIONS,
        RecomputeModule.RECOMMENDATION,
    ],
    EventType.COMPETITOR_EVENT: [
        RecomputeModule.COMPETITION_GRAPH,
        RecomputeModule.MARKET_EXPECTATIONS,
        RecomputeModule.RECOMMENDATION,
    ],
    EventType.PARTNERSHIP_MA: [
        RecomputeModule.MARKET_EXPECTATIONS,
        RecomputeModule.RECOMMENDATION,
        RecomputeModule.DOSSIER,
    ],
    EventType.EARNINGS: [
        RecomputeModule.FINANCING_RISK,
        RecomputeModule.DOSSIER,
    ],
    EventType.MANAGEMENT_CHANGE: [
        RecomputeModule.DOSSIER,
    ],
    EventType.REGULATORY_OTHER: [
        RecomputeModule.PROBABILITY_STACK,
        RecomputeModule.RECOMMENDATION,
    ],
    EventType.UNKNOWN: [],
}


@dataclass(frozen=True)
class RecomputeRequest:
    request_id: str              # UUID
    asset_id: str
    modules: list[str]           # RecomputeModule.value strings
    triggered_by_event_type: str
    materiality_tier: str
    created_at: datetime
    processed: bool = False


class ModelTriggerEngine:
    """
    Converts RoutedEvents to RecomputeRequests.
    Deduplicates: if the same (asset_id, module) already has a pending request, skip.
    """

    def __init__(self) -> None:
        self._requests: dict[str, RecomputeRequest] = {}  # request_id -> request
        # Track which (asset_id, module) pairs have pending requests for dedup
        self._pending_pairs: set[tuple[str, str]] = set()

    def process(self, event: RoutedEvent) -> list[RecomputeRequest]:
        """
        For each affected_asset_id × module in EVENT_MODULE_MAP[event.event_type]:
        - Skip if (asset_id, module) already pending (dedup)
        - Skip EventType.UNKNOWN (no modules)
        - Skip MINIMAL materiality events
        Returns list of new requests created.
        """
        # Skip MINIMAL materiality events
        if event.materiality_tier == MaterialityTier.MINIMAL:
            return []

        modules = EVENT_MODULE_MAP.get(event.event_type, [])
        # Skip UNKNOWN (no modules)
        if not modules:
            return []

        new_requests: list[RecomputeRequest] = []

        for asset_id in event.affected_asset_ids:
            # Collect all non-duplicate modules for this asset
            new_modules: list[str] = []
            for module in modules:
                pair = (asset_id, module.value)
                if pair not in self._pending_pairs:
                    new_modules.append(module.value)

            if not new_modules:
                continue

            # Create one request per asset with all new modules
            # (per task spec: one request per asset_id, listing all new modules)
            # Actually, looking at the spec more carefully - it says
            # "for each affected_asset_id × module" which implies per-module requests
            # But "modules: list[str]" on RecomputeRequest suggests one per asset
            # The spec says "dedup: same (asset_id, module) not added twice"
            # and "multiple asset_ids from one event → separate requests"
            # This implies one request per asset, with a list of modules
            # But dedup is at the (asset_id, module) level
            # Let's create one request per asset with all applicable (non-dup) modules
            for module_val in new_modules:
                pair = (asset_id, module_val)
                self._pending_pairs.add(pair)

            request = RecomputeRequest(
                request_id=str(uuid.uuid4()),
                asset_id=asset_id,
                modules=new_modules,
                triggered_by_event_type=event.event_type.value,
                materiality_tier=event.materiality_tier.value,
                created_at=datetime.now(timezone.utc),
                processed=False,
            )
            self._requests[request.request_id] = request
            new_requests.append(request)

        return new_requests

    def pending(self, asset_id: str | None = None) -> list[RecomputeRequest]:
        """Return pending (unprocessed) requests, optionally filtered by asset_id."""
        results = [
            r for r in self._requests.values()
            if not r.processed
        ]
        if asset_id is not None:
            results = [r for r in results if r.asset_id == asset_id]
        return results

    def mark_processed(self, request_id: str) -> None:
        """Mark a request as processed."""
        if request_id not in self._requests:
            raise KeyError(f"Unknown request_id: {request_id!r}")
        # RecomputeRequest is frozen so we replace it
        old = self._requests[request_id]
        updated = RecomputeRequest(
            request_id=old.request_id,
            asset_id=old.asset_id,
            modules=old.modules,
            triggered_by_event_type=old.triggered_by_event_type,
            materiality_tier=old.materiality_tier,
            created_at=old.created_at,
            processed=True,
        )
        self._requests[request_id] = updated
        # Remove from pending pairs
        for module in old.modules:
            self._pending_pairs.discard((old.asset_id, module))

    def pending_count(self) -> int:
        """Count only unprocessed requests."""
        return sum(1 for r in self._requests.values() if not r.processed)

    def clear_processed(self) -> None:
        """Remove processed requests from store."""
        to_remove = [rid for rid, r in self._requests.items() if r.processed]
        for rid in to_remove:
            del self._requests[rid]
