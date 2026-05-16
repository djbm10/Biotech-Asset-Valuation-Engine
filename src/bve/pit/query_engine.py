"""PITQueryEngine — high-level no-lookahead query interface."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .fact_store import FactStore, PointInTimeFact


class PITQueryEngine:
    """
    Enforces point-in-time semantics for all model queries.

    Usage:
        engine = PITQueryEngine(fact_store, as_of_date=date(2024, 3, 15))
        price = engine.get("VKTX", "close_price")
    """

    def __init__(
        self,
        fact_store: FactStore,
        as_of_date: date,
        knowledge_cutoff: datetime | None = None,
    ) -> None:
        self._store = fact_store
        self._as_of_date = as_of_date
        # Default: knowledge_cutoff = end of as_of_date
        self._knowledge_cutoff = knowledge_cutoff or datetime(
            as_of_date.year, as_of_date.month, as_of_date.day, 23, 59, 59
        )

    @property
    def as_of_date(self) -> date:
        return self._as_of_date

    def get(
        self,
        entity_id: str,
        fact_type: str,
        default: Any = None,
    ) -> Any:
        """Return the most recent known value as of the PIT date."""
        fact = self._store.latest_as_of(
            entity_id, fact_type, self._as_of_date, self._knowledge_cutoff
        )
        if fact is None:
            return default
        return fact.value

    def get_history(self, entity_id: str, fact_type: str) -> list[PointInTimeFact]:
        """Return all known facts for an entity/type as of the PIT date."""
        return self._store.query_as_of(
            entity_id, fact_type, self._as_of_date, self._knowledge_cutoff
        )

    def get_fact(self, entity_id: str, fact_type: str) -> PointInTimeFact | None:
        return self._store.latest_as_of(
            entity_id, fact_type, self._as_of_date, self._knowledge_cutoff
        )

    def assert_no_future_data(
        self, entity_id: str, fact_type: str, future_date: date
    ) -> bool:
        """
        Assert that no fact for this entity/type was known before future_date
        but has a valid_from after as_of_date.
        Returns True if the no-lookahead invariant holds (no future data accessible).
        """
        # If any fact with valid_from > as_of_date is accessible at our cutoff, that's lookahead
        future_facts = self._store.query_as_of(
            entity_id, fact_type, future_date, self._knowledge_cutoff
        )
        for f in future_facts:
            if f.valid_from > self._as_of_date:
                return False  # lookahead detected
        return True
