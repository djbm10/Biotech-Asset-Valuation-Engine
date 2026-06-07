"""Event deduplication — one primary trade per independent catalyst event.

Problem: Without deduplication, the same catalyst can generate multiple
correlated decisions (e.g. weekly re-entries before the same PDUFA date).
These are NOT independent observations and inflate the effective N.

Rule: Only one primary trade per (company_id, asset_id, catalyst_type, catalyst_date).
This prevents:
  - overlapping 28-day holds counted as independent
  - multiple entries into same catalyst counted separately
  - same asset re-entered weekly before same event

Usage
-----
    from bve.validation.event_dedup import EventIdBuilder, EventDeduplicator

    builder = EventIdBuilder()
    eid = builder.make("co-vktx", "a-vktx", "phase_2_readout", date(2025, 6, 15))
    # → "co-vktx:a-vktx:phase_2_readout:2025-06-15"

    dedup = EventDeduplicator()
    dedup.register(eid, decision_id="dec-001", entry_date=date(2025, 6, 10))
    is_duplicate = dedup.is_duplicate(eid)  # False for first; True for subsequent
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


class EventIdBuilder:
    """Deterministic event ID construction.

    Format: ``{company_id}:{asset_id}:{catalyst_type}:{catalyst_date_iso}``

    The catalyst_date is snapped to the nearest Monday so that events
    with slightly different date estimates (e.g. "mid-June 2025") that
    refer to the same biological event are not double-counted.
    """

    def make(
        self,
        company_id: str,
        asset_id: str,
        catalyst_type: str,
        catalyst_date: date,
    ) -> str:
        """Return the canonical event_id for this (company, asset, catalyst) tuple."""
        # Snap to Monday of the catalyst week
        snapped = _snap_to_monday(catalyst_date)
        return f"{company_id}:{asset_id}:{catalyst_type}:{snapped.isoformat()}"

    def make_hash(
        self,
        company_id: str,
        asset_id: str,
        catalyst_type: str,
        catalyst_date: date,
    ) -> str:
        """Return a short 12-char hex hash of the event_id (for compact storage)."""
        raw = self.make(company_id, asset_id, catalyst_type, catalyst_date)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _snap_to_monday(d: date) -> date:
    """Snap date to the Monday of its ISO week."""
    import datetime
    days_since_monday = d.weekday()
    return d - datetime.timedelta(days=days_since_monday)


@dataclass
class EventRegistration:
    """Record of a registered trade for a given event_id."""
    event_id: str
    decision_id: str
    entry_date: date
    is_primary: bool   # True for the first registration; False for duplicates


@dataclass
class EventDeduplicator:
    """Track registered events and flag duplicates.

    Only the first registration for a given event_id is marked primary
    (``is_primary=True``). All subsequent registrations for the same
    event_id are duplicates and should NOT be counted as independent
    observations in statistical tests.

    Thread safety: not safe for concurrent access (single-process use).
    """

    _registry: dict[str, EventRegistration] = field(default_factory=dict)

    def register(
        self,
        event_id: str,
        *,
        decision_id: str,
        entry_date: date,
    ) -> EventRegistration:
        """Register a decision for an event. Returns the registration record."""
        if event_id not in self._registry:
            reg = EventRegistration(
                event_id=event_id,
                decision_id=decision_id,
                entry_date=entry_date,
                is_primary=True,
            )
            self._registry[event_id] = reg
        else:
            reg = EventRegistration(
                event_id=event_id,
                decision_id=decision_id,
                entry_date=entry_date,
                is_primary=False,
            )
        return reg

    def is_duplicate(self, event_id: str) -> bool:
        """Return True if this event_id already has a primary registration."""
        return event_id in self._registry

    def get_primary_decisions(self) -> list[EventRegistration]:
        """Return only the primary (first) registrations."""
        return [r for r in self._registry.values() if r.is_primary]

    def n_unique_events(self) -> int:
        return len(self._registry)

    def n_primary(self) -> int:
        return len(self.get_primary_decisions())

    def dedup_rate(self) -> Optional[float]:
        """Fraction of decisions that were duplicates (0–1)."""
        n_primary = self.n_primary()
        if n_primary == 0:
            return None
        n_total_registered = sum(
            1 for _ in self._registry  # count unique events = count primaries
        )
        return 1.0 - (n_primary / n_total_registered) if n_total_registered > 0 else 0.0


def filter_to_independent_decisions(
    decisions: list[dict],
    *,
    company_key: str = "company_id",
    asset_key: str = "asset_id",
    catalyst_type_key: str = "catalyst_type",
    catalyst_date_key: str = "catalyst_date",
    entry_date_key: str = "entry_date",
    decision_id_key: str = "decision_id",
) -> tuple[list[dict], dict]:
    """Filter a list of decision dicts to one primary trade per event.

    Returns
    -------
    (primary_decisions, dedup_report)
      primary_decisions — list of dicts that are unique by event_id
      dedup_report — summary stats about the deduplication
    """
    builder = EventIdBuilder()
    dedup = EventDeduplicator()
    primary: list[dict] = []

    for d in decisions:
        company_id = d.get(company_key, "")
        asset_id = d.get(asset_key, "")
        catalyst_type = d.get(catalyst_type_key, "unknown")
        catalyst_date_raw = d.get(catalyst_date_key)
        entry_date_raw = d.get(entry_date_key)

        if catalyst_date_raw is None:
            # No catalyst date → treat as independent (can't deduplicate)
            primary.append(d)
            continue

        cat_date = _parse_date(catalyst_date_raw)
        entry_date = _parse_date(entry_date_raw) if entry_date_raw else cat_date
        decision_id = str(d.get(decision_id_key, id(d)))

        event_id = builder.make(company_id, asset_id, catalyst_type, cat_date)
        reg = dedup.register(event_id, decision_id=decision_id, entry_date=entry_date)
        if reg.is_primary:
            primary.append({**d, "_event_id": event_id})

    report = {
        "n_total": len(decisions),
        "n_primary": len(primary),
        "n_duplicates_removed": len(decisions) - len(primary),
        "n_unique_events": dedup.n_unique_events(),
        "dedup_pct": round(
            (len(decisions) - len(primary)) / max(len(decisions), 1) * 100, 1
        ),
    }
    return primary, report


def _parse_date(value: object) -> date:
    """Parse date or date string to date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# ---------------------------------------------------------------------------
# Point-in-time timestamp validation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionTimestamps:
    """Required timestamps for a lookahead-free decision record.

    Invariants
    ----------
    - data_known_timestamp <= decision_timestamp
    - price_timestamp <= decision_timestamp
    - next_available_trade_timestamp >= decision_timestamp
    - next_available_trade_timestamp must be the NEXT market open after the
      press release or data event (if release is after close, trade is T+1).
    """
    decision_timestamp: str     # ISO datetime when decision was logged
    data_known_timestamp: str   # ISO datetime of latest data used
    price_timestamp: str        # ISO datetime of price used for position sizing
    next_available_trade_timestamp: str  # ISO datetime of earliest allowed entry

    def validate(self) -> list[str]:
        """Return list of violations. Empty = valid."""
        violations = []
        try:
            from datetime import datetime
            dt_dec = datetime.fromisoformat(self.decision_timestamp)
            dt_data = datetime.fromisoformat(self.data_known_timestamp)
            dt_price = datetime.fromisoformat(self.price_timestamp)
            dt_trade = datetime.fromisoformat(self.next_available_trade_timestamp)

            if dt_data > dt_dec:
                violations.append(
                    f"data_known ({self.data_known_timestamp}) is AFTER decision "
                    f"({self.decision_timestamp}) — lookahead bias!"
                )
            if dt_price > dt_dec:
                violations.append(
                    f"price_timestamp ({self.price_timestamp}) is AFTER decision "
                    f"({self.decision_timestamp}) — lookahead bias!"
                )
            if dt_trade < dt_dec:
                violations.append(
                    f"next_available_trade ({self.next_available_trade_timestamp}) "
                    f"is BEFORE decision ({self.decision_timestamp}) — "
                    f"same-day execution not allowed unless market was open."
                )
        except (ValueError, TypeError) as e:
            violations.append(f"Timestamp parse error: {e}")
        return violations
