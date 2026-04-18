"""Route classified events to affected assets and flag which modules need recomputation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.pipeline.news_monitor import ClassifiedEvent


class AssetEventBinding(BaseModel):
    event_id: str
    asset_id: str
    ticker: str
    bind_reason: str  # "direct_mention" / "competitor_overlap" / "same_ta" / "same_target"
    materiality_score: float


class RoutedEvent(BaseModel):
    classified_event: ClassifiedEvent
    bindings: list[AssetEventBinding]
    modules_to_recompute: list[str]  # e.g. ["pos", "market_expectations", "variant_thesis"]
    routed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventRouter:
    """Route a classified event to affected assets and modules."""

    # Module trigger map — which event types trigger which modules
    _MODULE_TRIGGERS: dict[str, list[str]] = {
        "trial_update":     ["pos", "catalyst_tree", "variant_thesis", "science"],
        "financing":        ["financing_forecast", "market_expectations", "variant_thesis"],
        "fda_action":       ["pos", "market_expectations", "catalyst_tree"],
        "competitor_event": ["competition_graph", "pos", "market_expectations"],
        "safety":           ["pos", "science", "variant_thesis"],
        "partnership":      ["financing_forecast", "market_expectations"],
        "earnings":         ["financing_forecast", "market_expectations"],
        "other":            [],
    }

    def route(
        self,
        event: ClassifiedEvent,
        asset_universe: list[dict],  # list of {"asset_id": str, "ticker": str, "indication": str}
    ) -> RoutedEvent:
        """
        Bind event to relevant assets and determine which modules to recompute.

        Binding rules:
        - If event.asset_id is set → direct_mention binding
        - If event.ticker matches universe ticker → direct_mention
        - If event_type == "competitor_event" → bind to all assets in same indication (same_ta)
        - Any asset with materiality_score >= 0.5 gets binding
        """
        bindings: list[AssetEventBinding] = []
        seen_asset_ids: set[str] = set()

        for asset in asset_universe:
            asset_id = asset["asset_id"]
            ticker = asset["ticker"]
            indication = asset.get("indication", "")
            bind_reason: Optional[str] = None

            # Direct match by asset_id
            if event.asset_id and event.asset_id == asset_id:
                bind_reason = "direct_mention"
            # Direct match by ticker
            elif event.ticker and event.ticker.upper() == ticker.upper():
                bind_reason = "direct_mention"
            # Competitor event — bind to all assets in same indication if indication matches
            elif event.event_type == "competitor_event" and indication:
                bind_reason = "same_ta"

            if bind_reason and asset_id not in seen_asset_ids:
                # For non-direct bindings, only include if materiality >= 0.5
                if bind_reason == "direct_mention" or event.materiality_score >= 0.5:
                    bindings.append(
                        AssetEventBinding(
                            event_id=event.event_id,
                            asset_id=asset_id,
                            ticker=ticker,
                            bind_reason=bind_reason,
                            materiality_score=event.materiality_score,
                        )
                    )
                    seen_asset_ids.add(asset_id)

        modules = list(self._MODULE_TRIGGERS.get(event.event_type, []))

        return RoutedEvent(
            classified_event=event,
            bindings=bindings,
            modules_to_recompute=modules,
        )
