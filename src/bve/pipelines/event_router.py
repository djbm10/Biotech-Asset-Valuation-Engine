"""
Classifies incoming RawEvents and resolves them to affected asset_ids.
"""
from __future__ import annotations

from dataclasses import dataclass

from bve.ingestion.raw_event import RawEvent
from bve.evidence.classifier import EventType, classify
from bve.evidence.materiality import MaterialityTier, score_materiality


@dataclass(frozen=True)
class RoutedEvent:
    raw_event: RawEvent
    event_type: EventType
    materiality_tier: MaterialityTier
    materiality_score: float
    affected_asset_ids: list[str]
    routing_confidence: float   # from classification confidence


class EntityRegistry:
    """
    In-memory registry mapping tickers and NCT IDs to asset_ids.
    Used for entity resolution in routing.
    """

    def __init__(self) -> None:
        self._ticker_map: dict[str, str] = {}   # ticker (upper) -> asset_id
        self._nct_map: dict[str, str] = {}       # nct_id -> asset_id

    def register(self, asset_id: str, tickers: list[str], nct_ids: list[str] = []) -> None:
        """Register an asset with its tickers and NCT IDs."""
        for ticker in tickers:
            self._ticker_map[ticker.upper()] = asset_id
        for nct_id in nct_ids:
            self._nct_map[nct_id] = asset_id

    def resolve_ticker(self, ticker: str) -> str | None:
        """Return asset_id for a ticker, or None if not found."""
        return self._ticker_map.get(ticker.upper())

    def resolve_nct(self, nct_id: str) -> str | None:
        """Return asset_id for an NCT ID, or None if not found."""
        return self._nct_map.get(nct_id)

    def resolve_event(self, raw_event: RawEvent) -> list[str]:
        """
        Returns list of asset_ids affected by this event.
        Resolution order:
        1. raw_event.entity_ids (already resolved)
        2. payload.get("ticker") → resolve_ticker()
        3. payload.get("nct_id") → resolve_nct()
        Falls back to [] if nothing resolves.
        """
        # 1. Use entity_ids already on the event
        if raw_event.entity_ids:
            return list(raw_event.entity_ids)

        results: list[str] = []

        # 2. Resolve from ticker in payload
        ticker = raw_event.payload.get("ticker")
        if isinstance(ticker, str) and ticker:
            resolved = self.resolve_ticker(ticker)
            if resolved is not None and resolved not in results:
                results.append(resolved)

        # 3. Resolve from nct_id in payload
        nct_id = raw_event.payload.get("nct_id")
        if isinstance(nct_id, str) and nct_id:
            resolved = self.resolve_nct(nct_id)
            if resolved is not None and resolved not in results:
                results.append(resolved)

        return results


class EventRouter:
    def __init__(self, registry: EntityRegistry) -> None:
        self._registry = registry

    def route(self, raw_event: RawEvent) -> RoutedEvent:
        """Classify event, score materiality, resolve entities, return RoutedEvent."""
        classification = classify(raw_event)
        materiality = score_materiality(raw_event, classification)
        affected = self._registry.resolve_event(raw_event)

        return RoutedEvent(
            raw_event=raw_event,
            event_type=classification.event_type,
            materiality_tier=materiality.tier,
            materiality_score=materiality.score,
            affected_asset_ids=affected,
            routing_confidence=classification.confidence,
        )

    def route_batch(self, events: list[RawEvent]) -> list[RoutedEvent]:
        """Route all events; skip MINIMAL materiality tier events."""
        routed: list[RoutedEvent] = []
        for event in events:
            result = self.route(event)
            if result.materiality_tier != MaterialityTier.MINIMAL:
                routed.append(result)
        return routed

    def filter_by_tier(
        self,
        events: list[RoutedEvent],
        min_tier: MaterialityTier,
    ) -> list[RoutedEvent]:
        """Return events at or above the given materiality tier."""
        tier_order = [
            MaterialityTier.MINIMAL,
            MaterialityTier.LOW,
            MaterialityTier.MEDIUM,
            MaterialityTier.HIGH,
        ]
        min_idx = tier_order.index(min_tier)
        return [
            e for e in events
            if tier_order.index(e.materiality_tier) >= min_idx
        ]
