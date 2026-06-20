"""Review-first gate for live scanner score movements (commit 2).

Conservative by default: a score movement is held for human review unless it is
clearly immaterial. Two triggers force review:

1. magnitude — ``abs(delta) >= AUTO_APPLY_THRESHOLD`` (0.05 to start);
2. event substance — any contributing event is a major clinical/regulatory event
   (trial readout, interim, endpoint change, safety, FDA decision/designation,
   regulatory hold, discontinuation), regardless of delta.

Everything else auto-applies. Auto-apply is therefore restricted to small moves
driven by lesser event types (e.g. enrollment updates) — material or consequential
moves never publish without a human.

Note: this gate intentionally uses an explicit major-event set rather than the
valuation-layer ``mapping.requires_review`` (whose MANUAL/BOUNDED rules cover nearly
every type and would make the delta threshold meaningless here). The two contracts
are kept separate.
"""
from __future__ import annotations

from bve.intelligence.taxonomy import EventType

#: Absolute composite-score delta at/above which a move is always reviewed.
AUTO_APPLY_THRESHOLD = 0.05

DECISION_AUTO_APPLY = "auto_apply"
DECISION_REVIEW = "review"

#: Major clinical/regulatory event types that force review regardless of delta.
_MAJOR_EVENT_TYPES: frozenset[str] = frozenset({
    EventType.TRIAL_READOUT.value,
    EventType.INTERIM_ANALYSIS.value,
    EventType.ENDPOINT_CHANGE.value,
    EventType.SAFETY_SIGNAL.value,
    EventType.FDA_APPROVAL.value,
    EventType.FDA_REJECTION.value,
    EventType.FDA_DESIGNATION.value,
    EventType.REGULATORY_HOLD.value,
    EventType.PROGRAM_DISCONTINUATION.value,
})


def _is_major(event_type: str) -> bool:
    return event_type in _MAJOR_EVENT_TYPES


def decide(delta: float, event_types: tuple[str, ...] | list[str]) -> tuple[str, str]:
    """Return (decision, reason) for a score movement.

    ``review`` when the move is material (``abs(delta) >= AUTO_APPLY_THRESHOLD``) or
    any contributing event is major; otherwise ``auto_apply``.
    """
    major = [et for et in event_types if _is_major(et)]
    if major:
        return DECISION_REVIEW, f"major event(s): {', '.join(sorted(set(major)))}"
    if abs(delta) >= AUTO_APPLY_THRESHOLD:
        return DECISION_REVIEW, f"|delta|={abs(delta):.3f} ≥ {AUTO_APPLY_THRESHOLD}"
    return DECISION_AUTO_APPLY, f"|delta|={abs(delta):.3f} < {AUTO_APPLY_THRESHOLD}, no major event"
