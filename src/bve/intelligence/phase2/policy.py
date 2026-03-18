"""
Phase 2 mapping policy configuration.

This module defines the typed policy layer that sits on top of the static
event-to-parameter mapping table in ``bve.intelligence.mapping``.

Policy controls:
  - allowed parameters per event type
  - minimum extraction confidence for auto-application
  - materiality threshold for mandatory manual review
  - review routing mode (rule-based vs manual-only)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from bve.intelligence.mapping import rules_for
from bve.intelligence.taxonomy import EventType


class EventRoutingPolicy(BaseModel):
    """Per-event routing policy for Phase 2."""

    event_type: EventType
    allowed_parameters: tuple[str, ...]
    min_confidence_score: float = Field(default=0.60, ge=0.0, le=1.0)
    materiality_threshold_pct: float = Field(default=12.0, ge=0.0, le=100.0)
    review_requirement: Literal["rule_based", "manual_only"] = "rule_based"


class MappingPolicy(BaseModel):
    """Typed policy registry keyed by EventType."""

    default_min_confidence_score: float = Field(default=0.60, ge=0.0, le=1.0)
    default_materiality_threshold_pct: float = Field(default=12.0, ge=0.0, le=100.0)
    events: dict[EventType, EventRoutingPolicy]

    def for_event(self, event_type: EventType) -> EventRoutingPolicy:
        """Return routing policy for one event type."""
        try:
            return self.events[event_type]
        except KeyError as exc:
            raise KeyError(f"No routing policy configured for event_type={event_type.value!r}") from exc

    @classmethod
    def default(cls) -> "MappingPolicy":
        """
        Build default policy from the canonical mapping table.

        Allowed parameters are sourced from ``rules_for(event_type)`` to keep
        policy and mapping coverage aligned.
        """
        events: dict[EventType, EventRoutingPolicy] = {}

        # Event-specific thresholds tuned for practical routing behavior.
        confidence_overrides: dict[EventType, float] = {
            EventType.INTERIM_ANALYSIS: 0.70,
            EventType.CONFERENCE_PRESENTATION: 0.70,
            EventType.SEC_FILING: 0.65,
            EventType.MANAGEMENT_CHANGE: 0.65,
            EventType.PATENT_EVENT: 0.70,
        }
        threshold_overrides: dict[EventType, float] = {
            # High-signal regulatory/clinical events need enough room for their
            # auto rules to execute, otherwise they are all routed to review and
            # never reach valuation in unattended runs.
            EventType.TRIAL_READOUT: 20.0,
            EventType.INTERIM_ANALYSIS: 12.0,
            EventType.SAFETY_SIGNAL: 12.0,
            EventType.REGULATORY_HOLD: 20.0,
            EventType.FDA_REJECTION: 100.0,
            EventType.FDA_APPROVAL: 100.0,
            EventType.FDA_DESIGNATION: 20.0,
            EventType.PROGRAM_DISCONTINUATION: 5.0,
            EventType.COMPETITOR_EVENT: 10.0,
        }

        for event_type in EventType:
            allowed = tuple(r.parameter for r in rules_for(event_type))
            events[event_type] = EventRoutingPolicy(
                event_type=event_type,
                allowed_parameters=allowed,
                min_confidence_score=confidence_overrides.get(event_type, 0.60),
                materiality_threshold_pct=threshold_overrides.get(event_type, 12.0),
                review_requirement="rule_based",
            )

        return cls(
            default_min_confidence_score=0.60,
            default_materiality_threshold_pct=12.0,
            events=events,
        )
