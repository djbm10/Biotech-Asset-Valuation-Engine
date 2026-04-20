"""Revaluation trigger engine — emits structured recompute records from readthrough signals.

Priority thresholds:
  IMMEDIATE  : magnitude >= 0.15 or abs(pos_delta) >= 0.12
  HIGH       : magnitude >= 0.10 or abs(pos_delta) >= 0.08
  MEDIUM     : magnitude >= 0.05 or abs(pos_delta) >= 0.04
  LOW        : everything else above minimum threshold
  SUPPRESSED : magnitude < 0.02 and abs(pos_delta) < 0.02

Modules to recompute per priority:
  IMMEDIATE : probability_stack, market_expectations, recommendation, financing_risk
  HIGH      : probability_stack, market_expectations, recommendation
  MEDIUM    : probability_stack, market_expectations
  LOW       : market_expectations
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel

from bve.intelligence.readthrough_engine import ReadthroughDirection, ReadthroughSignal


class TriggerPriority(str, Enum):
    IMMEDIATE = "immediate"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SUPPRESSED = "suppressed"


_MODULES_BY_PRIORITY: dict[TriggerPriority, list[str]] = {
    TriggerPriority.IMMEDIATE: [
        "probability_stack",
        "market_expectations",
        "recommendation",
        "financing_risk",
    ],
    TriggerPriority.HIGH: [
        "probability_stack",
        "market_expectations",
        "recommendation",
    ],
    TriggerPriority.MEDIUM: [
        "probability_stack",
        "market_expectations",
    ],
    TriggerPriority.LOW: [
        "market_expectations",
    ],
    TriggerPriority.SUPPRESSED: [],
}


class RevaluationTrigger(BaseModel, frozen=True):
    trigger_id: str
    asset_id: str
    source_event_asset_id: str
    readthrough: ReadthroughSignal
    priority: TriggerPriority
    modules_to_recompute: list[str]
    created_at: datetime
    rationale: str


# ---------------------------------------------------------------------------
# Priority classification
# ---------------------------------------------------------------------------

def _classify_priority(signal: ReadthroughSignal) -> TriggerPriority:
    """Classify a readthrough signal into a trigger priority tier."""
    mag = signal.magnitude
    abs_delta = abs(signal.pos_delta)

    # NEUTRAL signals with zero values → SUPPRESSED
    if signal.direction == ReadthroughDirection.NEUTRAL:
        return TriggerPriority.SUPPRESSED

    if mag < 0.02 and abs_delta < 0.02:
        return TriggerPriority.SUPPRESSED

    if mag >= 0.15 or abs_delta >= 0.12:
        return TriggerPriority.IMMEDIATE

    if mag >= 0.10 or abs_delta >= 0.08:
        return TriggerPriority.HIGH

    if mag >= 0.05 or abs_delta >= 0.04:
        return TriggerPriority.MEDIUM

    return TriggerPriority.LOW


_PRIORITY_ORDER = {
    TriggerPriority.IMMEDIATE: 0,
    TriggerPriority.HIGH: 1,
    TriggerPriority.MEDIUM: 2,
    TriggerPriority.LOW: 3,
    TriggerPriority.SUPPRESSED: 4,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def emit_triggers(
    signals: list[ReadthroughSignal],
    asset_id_filter: str | None = None,
) -> list[RevaluationTrigger]:
    """Convert readthrough signals to revaluation triggers, sorted by priority.

    NEUTRAL/SUPPRESSED signals produce no triggers.
    If asset_id_filter is provided, only signals targeting that asset are processed.
    """
    now = datetime.now(timezone.utc)
    triggers: list[RevaluationTrigger] = []

    for signal in signals:
        if asset_id_filter is not None and signal.target_asset_id != asset_id_filter:
            continue

        priority = _classify_priority(signal)

        if priority == TriggerPriority.SUPPRESSED:
            continue

        modules = list(_MODULES_BY_PRIORITY[priority])
        trigger = RevaluationTrigger(
            trigger_id=str(uuid4()),
            asset_id=signal.target_asset_id,
            source_event_asset_id=signal.source_asset_id,
            readthrough=signal,
            priority=priority,
            modules_to_recompute=modules,
            created_at=now,
            rationale=(
                f"Readthrough {signal.direction.value} (magnitude={signal.magnitude:.3f}, "
                f"pos_delta={signal.pos_delta:+.3f}) from {signal.source_asset_id} "
                f"→ {signal.target_asset_id}. {signal.rationale}"
            ),
        )
        triggers.append(trigger)

    triggers.sort(key=lambda t: _PRIORITY_ORDER[t.priority])
    return triggers


class TriggerStore:
    """In-memory store for triggers (ephemeral — no SQLite needed)."""

    def __init__(self) -> None:
        self._triggers: dict[str, RevaluationTrigger] = {}
        self._processed: set[str] = set()

    def add(self, trigger: RevaluationTrigger) -> None:
        """Add a trigger to the store."""
        self._triggers[trigger.trigger_id] = trigger

    def pending(
        self, priority: TriggerPriority | None = None
    ) -> list[RevaluationTrigger]:
        """Return unprocessed triggers, optionally filtered by priority.

        Results are sorted by priority (IMMEDIATE first).
        """
        results = [
            t
            for tid, t in self._triggers.items()
            if tid not in self._processed
            and (priority is None or t.priority == priority)
        ]
        results.sort(key=lambda t: _PRIORITY_ORDER[t.priority])
        return results

    def mark_processed(self, trigger_id: str) -> None:
        """Mark a trigger as processed so it no longer appears in pending()."""
        self._processed.add(trigger_id)

    def count(self) -> int:
        """Return total number of triggers (processed + pending)."""
        return len(self._triggers)
