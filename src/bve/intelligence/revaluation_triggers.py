"""Revaluation trigger engine — detects when a module recompute is warranted."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

_CRITICAL_EVENT_TYPES = {
    "thesis_break",
    "regulatory_event",
    "financing_event",
}


class RevaluationTrigger(BaseModel):
    """A signal that one or more valuation modules should be recomputed."""

    trigger_id: str
    asset_id: str
    trigger_type: str  # "competitor_event" | "financing_event" | "regulatory_event" | "thesis_break" | "data_refresh" | "stale_input"
    source_event_id: Optional[str] = None
    priority: str  # "high" | "medium" | "low"
    triggered_at: datetime
    description: str
    modules_to_recompute: list[str] = Field(default_factory=list)


class RevaluationTriggerEngine:
    """Evaluates incoming events and emits revaluation triggers when warranted."""

    def evaluate(
        self,
        asset_id: str,
        event_type: str,
        materiality_score: float,
        source_event_id: Optional[str] = None,
    ) -> Optional[RevaluationTrigger]:
        """Return a trigger when materiality_score > 0.3 or event_type is critical.

        Priority rules:
        - materiality >= 0.7 or critical event type → high
        - materiality >= 0.4 → medium
        - otherwise → low
        """
        is_critical = event_type in _CRITICAL_EVENT_TYPES
        if materiality_score <= 0.3 and not is_critical:
            return None

        if materiality_score >= 0.7 or is_critical:
            priority = "high"
        elif materiality_score >= 0.4:
            priority = "medium"
        else:
            priority = "low"

        modules = _modules_for_event(event_type)

        return RevaluationTrigger(
            trigger_id=str(uuid4()),
            asset_id=asset_id,
            trigger_type=event_type,
            source_event_id=source_event_id,
            priority=priority,
            triggered_at=datetime.now(timezone.utc),
            description=f"Event '{event_type}' (materiality={materiality_score:.2f}) triggered revaluation.",
            modules_to_recompute=modules,
        )


def _modules_for_event(event_type: str) -> list[str]:
    mapping: dict[str, list[str]] = {
        "competitor_event": ["competition", "market_access", "peak_sales"],
        "financing_event": ["financing_risk", "dilution", "runway"],
        "regulatory_event": ["pos", "timeline", "market_access"],
        "thesis_break": ["pos", "peak_sales", "recommendation"],
        "data_refresh": ["pos", "peak_sales", "timeline"],
        "stale_input": ["all"],
    }
    return mapping.get(event_type, ["pos"])
