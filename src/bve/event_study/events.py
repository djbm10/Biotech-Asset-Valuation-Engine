"""
Event database for biotech catalyst tracking.

Stores trial readout events, FDA actions, and other binary catalysts
with their associated metadata for event-study analysis.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    TOPLINE_READOUT = "topline_readout"          # Phase 2/3 primary endpoint result
    INTERIM_ANALYSIS = "interim_analysis"         # Planned interim look
    FDA_SUBMISSION = "fda_submission"             # NDA/BLA submission
    FDA_ACCEPTANCE = "fda_acceptance"             # Filing acceptance
    FDA_APPROVAL = "fda_approval"                 # Full approval
    FDA_CRL = "fda_crl"                          # Complete Response Letter (rejection)
    ADCOM = "adcom"                               # Advisory committee vote
    PARTNERSHIP = "partnership"                   # Deal announcement
    CLINICAL_HOLD = "clinical_hold"               # Safety-related hold
    DATA_PRESENTATION = "data_presentation"       # Conference abstract/poster


class EventOutcome(str, Enum):
    POSITIVE = "positive"      # Met primary endpoint / approved / deal closed
    NEGATIVE = "negative"      # Failed / CRL / rejected / hold
    MIXED = "mixed"            # Met some but not all endpoints
    PENDING = "pending"        # Event has not yet occurred
    UNKNOWN = "unknown"        # Outcome not yet classified


class CatalystEvent(BaseModel):
    """A single catalyst event associated with an asset."""

    id: str
    asset_id: str
    company_ticker: str

    event_type: EventType
    event_date: str                   # ISO date, e.g. "2024-11-15"
    announcement_date: Optional[str] = None   # May differ from event date

    # Context
    trial_phase: Optional[str] = None
    nct_id: Optional[str] = None
    indication: Optional[str] = None
    primary_endpoint: Optional[str] = None

    # Outcome (populated after the event)
    outcome: EventOutcome = EventOutcome.PENDING
    outcome_notes: Optional[str] = None

    # Market expectations (optional — for HF analysis)
    iv_skew_pre: Optional[float] = Field(
        default=None,
        description="Options-implied vol skew as proxy for market expectation"
    )
    consensus_pos_pct: Optional[float] = Field(
        default=None, ge=0.0, le=100.0,
        description="Analyst consensus POS estimate (%) pre-event"
    )

    data_source: str = "manual"
    notes: Optional[str] = None

    @property
    def is_binary(self) -> bool:
        return self.event_type in {
            EventType.TOPLINE_READOUT,
            EventType.FDA_APPROVAL,
            EventType.FDA_CRL,
            EventType.ADCOM,
        }


class EventDatabase:
    """In-memory event store with filtering helpers."""

    def __init__(self, events: list[CatalystEvent] | None = None):
        self._events: list[CatalystEvent] = events or []

    def add(self, event: CatalystEvent) -> None:
        self._events.append(event)

    def extend(self, events: list[CatalystEvent]) -> None:
        self._events.extend(events)

    def all(self) -> list[CatalystEvent]:
        return list(self._events)

    def by_ticker(self, ticker: str) -> list[CatalystEvent]:
        return [e for e in self._events if e.company_ticker.upper() == ticker.upper()]

    def by_asset(self, asset_id: str) -> list[CatalystEvent]:
        return [e for e in self._events if e.asset_id == asset_id]

    def by_type(self, event_type: EventType) -> list[CatalystEvent]:
        return [e for e in self._events if e.event_type == event_type]

    def completed(self) -> list[CatalystEvent]:
        return [e for e in self._events if e.outcome != EventOutcome.PENDING]

    def pending(self) -> list[CatalystEvent]:
        return [e for e in self._events if e.outcome == EventOutcome.PENDING]

    def topline_readouts(self, outcome: Optional[EventOutcome] = None) -> list[CatalystEvent]:
        events = self.by_type(EventType.TOPLINE_READOUT)
        if outcome:
            events = [e for e in events if e.outcome == outcome]
        return events

    def to_dataframe(self):
        import pandas as pd
        return pd.DataFrame([e.model_dump() for e in self._events])
