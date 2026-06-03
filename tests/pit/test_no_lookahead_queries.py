"""Tests for point-in-time fact store and no-lookahead invariant."""

import pytest
from datetime import date, datetime, timedelta

from bve.pit.fact_store import FactStore, PointInTimeFact
from bve.pit.query_engine import PITQueryEngine


def make_fact(
    entity_id="VKTX",
    fact_type="close_price",
    value=42.50,
    valid_from=date(2024, 1, 1),
    valid_to=None,
    known_at=None,
    source="yfinance",
    doc_id="yf-001",
) -> PointInTimeFact:
    if known_at is None:
        known_at = datetime(valid_from.year, valid_from.month, valid_from.day, 12, 0, 0)
    return PointInTimeFact(
        entity_id=entity_id,
        fact_type=fact_type,
        value=value,
        valid_from=valid_from,
        valid_to=valid_to,
        known_at=known_at,
        ingested_at=datetime.utcnow(),
        source=source,
        source_document_id=doc_id,
    )


@pytest.fixture
def store():
    return FactStore(db_path=":memory:")


@pytest.fixture
def populated_store():
    store = FactStore(db_path=":memory:")
    # Historical price: valid Jan 2024
    store.insert(make_fact(
        value=42.50,
        valid_from=date(2024, 1, 1),
        valid_to=date(2024, 2, 1),
        known_at=datetime(2024, 1, 1, 12, 0),
    ))
    # Updated price: valid Feb 2024 onwards
    store.insert(make_fact(
        value=55.00,
        valid_from=date(2024, 2, 1),
        valid_to=None,
        known_at=datetime(2024, 2, 1, 12, 0),
    ))
    # Future fact: won't be known until June 2024
    store.insert(make_fact(
        fact_type="phase_3_result",
        value="success",
        valid_from=date(2024, 6, 1),
        valid_to=None,
        known_at=datetime(2024, 6, 1, 12, 0),
    ))
    return store


class TestFactStore:
    def test_insert_and_retrieve(self, store):
        fact = make_fact()
        fact_id = store.insert(fact)
        assert fact_id > 0

    def test_query_as_of_returns_fact_in_range(self, populated_store):
        facts = populated_store.query_as_of(
            "VKTX", "close_price",
            as_of_date=date(2024, 1, 15),
            knowledge_cutoff=datetime(2024, 1, 15, 23, 59, 59),
        )
        assert len(facts) == 1
        assert facts[0].value == "42.5"

    def test_query_as_of_returns_updated_value(self, populated_store):
        facts = populated_store.query_as_of(
            "VKTX", "close_price",
            as_of_date=date(2024, 3, 1),
            knowledge_cutoff=datetime(2024, 3, 1, 23, 59, 59),
        )
        assert len(facts) == 1
        assert facts[0].value == "55.0"

    def test_query_excludes_future_known_at(self, populated_store):
        """Knowledge cutoff in Jan 2024 must not reveal Feb 2024 fact."""
        facts = populated_store.query_as_of(
            "VKTX", "close_price",
            as_of_date=date(2024, 3, 1),
            knowledge_cutoff=datetime(2024, 1, 20, 23, 59, 59),
        )
        # Only Jan fact should be accessible with Jan cutoff
        assert all(float(f.value) == 42.5 for f in facts)

    def test_no_lookahead_future_result_not_visible(self, populated_store):
        """Phase 3 result from June 2024 must not be visible with March 2024 cutoff."""
        facts = populated_store.query_as_of(
            "VKTX", "phase_3_result",
            as_of_date=date(2024, 3, 1),
            knowledge_cutoff=datetime(2024, 3, 1, 23, 59, 59),
        )
        assert len(facts) == 0

    def test_latest_as_of_returns_most_recent(self, populated_store):
        fact = populated_store.latest_as_of(
            "VKTX", "close_price",
            as_of_date=date(2024, 3, 1),
            knowledge_cutoff=datetime(2024, 3, 1, 23, 59, 59),
        )
        assert fact is not None
        assert fact.value == "55.0"

    def test_latest_as_of_returns_none_when_not_found(self, store):
        result = store.latest_as_of(
            "UNKNOWN", "close_price",
            as_of_date=date(2024, 1, 1),
            knowledge_cutoff=datetime(2024, 1, 1, 23, 59, 59),
        )
        assert result is None

    def test_insert_batch(self, store):
        facts = [make_fact(doc_id=f"doc-{i}") for i in range(3)]
        ids = store.insert_batch(facts)
        assert len(ids) == 3


class TestPITQueryEngine:
    def test_get_returns_value(self, populated_store):
        engine = PITQueryEngine(
            populated_store,
            as_of_date=date(2024, 1, 15),
        )
        val = engine.get("VKTX", "close_price")
        assert val == "42.5"

    def test_get_returns_default_when_missing(self, populated_store):
        engine = PITQueryEngine(populated_store, as_of_date=date(2024, 1, 15))
        val = engine.get("VKTX", "nonexistent", default="N/A")
        assert val == "N/A"

    def test_no_lookahead_future_fact_not_accessible(self, populated_store):
        engine = PITQueryEngine(
            populated_store,
            as_of_date=date(2024, 3, 1),
        )
        val = engine.get("VKTX", "phase_3_result")
        assert val is None

    def test_get_history_returns_list(self, populated_store):
        engine = PITQueryEngine(populated_store, as_of_date=date(2024, 3, 1))
        history = engine.get_history("VKTX", "close_price")
        assert isinstance(history, list)

    def test_assert_no_future_data_invariant(self, populated_store):
        engine = PITQueryEngine(populated_store, as_of_date=date(2024, 3, 1))
        # Future fact has valid_from = 2024-06-01 — should not be accessible
        ok = engine.assert_no_future_data("VKTX", "phase_3_result", date(2024, 12, 31))
        assert ok  # no future data accessible from March cutoff


class TestPITFact:
    def test_as_of_check_passes_for_valid_fact(self):
        fact = make_fact(
            valid_from=date(2024, 1, 1),
            valid_to=None,
            known_at=datetime(2024, 1, 1, 12, 0),
        )
        assert fact.as_of_check(date(2024, 6, 1), datetime(2024, 6, 1, 23, 59))

    def test_as_of_check_fails_for_future_known_at(self):
        fact = make_fact(
            valid_from=date(2024, 6, 1),
            known_at=datetime(2024, 6, 1, 12, 0),
        )
        assert not fact.as_of_check(date(2024, 6, 15), datetime(2024, 3, 1, 23, 59))

    def test_as_of_check_fails_when_expired(self):
        fact = make_fact(
            valid_from=date(2024, 1, 1),
            valid_to=date(2024, 3, 1),
            known_at=datetime(2024, 1, 1, 12, 0),
        )
        assert not fact.as_of_check(date(2024, 4, 1), datetime(2024, 4, 1, 23, 59))
