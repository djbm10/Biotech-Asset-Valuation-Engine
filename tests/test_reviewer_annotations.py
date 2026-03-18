"""Tests for Wave 3C — Reviewer Annotations + Audit Log."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.schemas.runs import ReviewDecision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_NOW = datetime.now(timezone.utc)

_TRACE = SourceTrace(source_type="test", source_ref="doc-001")


@pytest.fixture
def store():
    ks = KnowledgeStore(db_path=":memory:")
    yield ks
    ks.close()


def _make_decision(
    decision_id: str = "dec-001",
    proposal_id: str = "prop-001",
    decision: str = "accepted",
    reviewer_id: str = "analyst-dj",
    reviewer_confidence: float | None = None,
    analyst_tags: list[str] | None = None,
    supporting_quote: str | None = None,
) -> ReviewDecision:
    return ReviewDecision(
        id=decision_id,
        proposal_id=proposal_id,
        decision=decision,
        reviewer_id=reviewer_id,
        reviewed_at=_NOW,
        rationale="Test rationale.",
        reviewer_confidence=reviewer_confidence,
        analyst_tags=analyst_tags or [],
        supporting_quote=supporting_quote,
    )


def _record(store: KnowledgeStore, dec: ReviewDecision) -> None:
    store.add_review_decision(
        dec,
        company_id="co-001",
        asset_id="asset-001",
        source_trace=_TRACE,
    )


# ---------------------------------------------------------------------------
# ReviewDecision schema extensions
# ---------------------------------------------------------------------------


def test_review_decision_new_fields_default_to_none_or_empty():
    dec = _make_decision()
    assert dec.reviewer_confidence is None
    assert dec.analyst_tags == []
    assert dec.supporting_quote is None


def test_review_decision_reviewer_confidence_valid():
    dec = _make_decision(reviewer_confidence=0.85)
    assert abs(dec.reviewer_confidence - 0.85) < 1e-9


def test_review_decision_reviewer_confidence_bounds():
    with pytest.raises(ValidationError):
        _make_decision(reviewer_confidence=1.5)
    with pytest.raises(ValidationError):
        _make_decision(reviewer_confidence=-0.1)


def test_review_decision_analyst_tags_stored():
    dec = _make_decision(analyst_tags=["interim_only", "high_quality_data"])
    assert "interim_only" in dec.analyst_tags
    assert len(dec.analyst_tags) == 2


def test_review_decision_supporting_quote():
    dec = _make_decision(supporting_quote="OS HR=0.72 (95% CI 0.58–0.90), p=0.003")
    assert "HR=0.72" in dec.supporting_quote


def test_review_decision_frozen_still_enforced():
    """frozen=True must still hold after adding new fields."""
    dec = _make_decision(reviewer_confidence=0.9)
    with pytest.raises(Exception):  # ValidationError or AttributeError
        dec.reviewer_confidence = 0.5  # type: ignore[misc]


def test_review_decision_existing_fields_unchanged():
    """Ensure backward compatibility — existing fields still work."""
    dec = ReviewDecision(
        id="d", proposal_id="p", decision="rejected",
        reviewer_id="a", reviewed_at=_NOW, rationale="x",
    )
    assert dec.decision == "rejected"
    assert dec.run_id is None
    assert dec.override_value is None


# ---------------------------------------------------------------------------
# KnowledgeStore — review_decisions column persistence
# ---------------------------------------------------------------------------


def test_add_review_decision_persists_reviewer_confidence(store):
    dec = _make_decision(reviewer_confidence=0.75)
    _record(store, dec)
    row = store._conn.execute(
        "SELECT reviewer_confidence FROM review_decisions WHERE id = ?", (dec.id,)
    ).fetchone()
    assert row is not None
    assert abs(row["reviewer_confidence"] - 0.75) < 1e-9


def test_add_review_decision_persists_analyst_tags(store):
    dec = _make_decision(analyst_tags=["small_sample", "surrogate_endpoint"])
    _record(store, dec)
    row = store._conn.execute(
        "SELECT analyst_tags_json FROM review_decisions WHERE id = ?", (dec.id,)
    ).fetchone()
    tags = json.loads(row["analyst_tags_json"])
    assert "small_sample" in tags
    assert "surrogate_endpoint" in tags


def test_add_review_decision_persists_supporting_quote(store):
    quote = "ORR 42% vs 8% placebo, p<0.001"
    dec = _make_decision(supporting_quote=quote)
    _record(store, dec)
    row = store._conn.execute(
        "SELECT supporting_quote FROM review_decisions WHERE id = ?", (dec.id,)
    ).fetchone()
    assert row["supporting_quote"] == quote


def test_add_review_decision_null_new_fields_allowed(store):
    dec = _make_decision()  # all new fields at defaults
    _record(store, dec)
    row = store._conn.execute(
        "SELECT reviewer_confidence, analyst_tags_json, supporting_quote "
        "FROM review_decisions WHERE id = ?", (dec.id,)
    ).fetchone()
    assert row["reviewer_confidence"] is None
    assert row["analyst_tags_json"] == "[]"
    assert row["supporting_quote"] is None


# ---------------------------------------------------------------------------
# Audit log — append behaviour
# ---------------------------------------------------------------------------


def test_audit_log_entry_created_on_review_decision(store):
    dec = _make_decision(reviewer_confidence=0.8)
    _record(store, dec)
    entries = store.query_audit_log()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["event_type"] == "review_decision"
    assert entry["entity_type"] == "proposal"
    assert entry["entity_id"] == dec.proposal_id
    assert entry["actor_id"] == dec.reviewer_id
    assert entry["action"] == dec.decision


def test_audit_log_payload_contains_reviewer_confidence(store):
    dec = _make_decision(reviewer_confidence=0.9, analyst_tags=["high_quality"])
    _record(store, dec)
    entry = store.query_audit_log()[0]
    payload = json.loads(entry["payload_json"])
    assert abs(payload["reviewer_confidence"] - 0.9) < 1e-9
    assert "high_quality" in payload["analyst_tags"]


def test_audit_log_is_append_only(store):
    """Two decisions → two separate audit rows, oldest preserved."""
    dec1 = _make_decision("dec-001", "prop-001", "accepted")
    dec2 = _make_decision("dec-002", "prop-002", "rejected")
    _record(store, dec1)
    _record(store, dec2)
    entries = store.query_audit_log()
    assert len(entries) == 2
    actions = {e["action"] for e in entries}
    assert "accepted" in actions
    assert "rejected" in actions


def test_audit_log_query_filter_by_action(store):
    _record(store, _make_decision("d1", "p1", "accepted"))
    _record(store, _make_decision("d2", "p2", "rejected"))
    _record(store, _make_decision("d3", "p3", "deferred"))
    accepted = store.query_audit_log(action="accepted")
    assert len(accepted) == 1
    assert accepted[0]["action"] == "accepted"


def test_audit_log_query_filter_by_actor(store):
    dec_a = _make_decision("d1", "p1", reviewer_id="alice")
    dec_b = _make_decision("d2", "p2", reviewer_id="bob")
    _record(store, dec_a)
    _record(store, dec_b)
    alice_entries = store.query_audit_log(actor_id="alice")
    assert len(alice_entries) == 1
    assert alice_entries[0]["actor_id"] == "alice"


def test_audit_log_query_filter_by_entity_id(store):
    dec = _make_decision(proposal_id="prop-target")
    _record(store, dec)
    _record(store, _make_decision("d2", "prop-other"))
    target = store.query_audit_log(entity_id="prop-target")
    assert len(target) == 1
    assert target[0]["entity_id"] == "prop-target"


def test_audit_log_query_limit(store):
    for i in range(5):
        _record(store, _make_decision(f"d{i}", f"p{i}"))
    rows = store.query_audit_log(limit=3)
    assert len(rows) == 3


def test_audit_log_newest_first(store):
    """query_audit_log returns entries in descending created_at order."""
    _record(store, _make_decision("d1", "p1"))
    _record(store, _make_decision("d2", "p2"))
    entries = store.query_audit_log()
    # Newest first — last inserted should appear first
    assert entries[0]["entity_id"] == "p2"
    assert entries[1]["entity_id"] == "p1"


def test_audit_log_query_no_filters_returns_all(store):
    _record(store, _make_decision("d1", "p1", "accepted"))
    _record(store, _make_decision("d2", "p2", "rejected"))
    assert len(store.query_audit_log()) == 2


# ---------------------------------------------------------------------------
# Forecast improvements (horizon_days + predicted_at)
# ---------------------------------------------------------------------------


def test_forecast_record_horizon_days_default():
    from bve.intelligence.forecast_tracker import ForecastRecord
    rec = ForecastRecord(
        signal_id="s", event_id="e", asset_id="a",
        event_type="trial_readout", signal_date="2024-01-01",
        predicted_direction="up",
    )
    assert rec.horizon_days == 30


def test_forecast_record_custom_horizon():
    from bve.intelligence.forecast_tracker import ForecastRecord
    rec = ForecastRecord(
        signal_id="s", event_id="e", asset_id="a",
        event_type="trial_readout", signal_date="2024-01-01",
        predicted_direction="up", horizon_days=180,
    )
    assert rec.horizon_days == 180


def test_forecast_record_predicted_at_defaults_to_now():
    from bve.intelligence.forecast_tracker import ForecastRecord
    rec = ForecastRecord(
        signal_id="s", event_id="e", asset_id="a",
        event_type="trial_readout", signal_date="2024-01-01",
        predicted_direction="up",
    )
    assert isinstance(rec.predicted_at, datetime)
    assert rec.predicted_at.tzinfo is not None


def test_forecast_record_predicted_at_independent_of_created_at():
    """predicted_at and created_at are separate timestamps."""
    from bve.intelligence.forecast_tracker import ForecastRecord
    t_pred = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t_write = datetime(2024, 1, 2, tzinfo=timezone.utc)
    rec = ForecastRecord(
        signal_id="s", event_id="e", asset_id="a",
        event_type="trial_readout", signal_date="2024-01-01",
        predicted_direction="up",
        predicted_at=t_pred,
        created_at=t_write,
    )
    assert rec.predicted_at == t_pred
    assert rec.created_at == t_write
    assert rec.predicted_at != rec.created_at


def test_forecast_record_horizon_and_predicted_at_persisted(store):
    from bve.intelligence.forecast_tracker import ForecastRecord
    import uuid
    rec = ForecastRecord(
        signal_id=str(uuid.uuid4()),
        event_id=str(uuid.uuid4()),
        asset_id="a",
        event_type="trial_readout",
        signal_date="2024-01-01",
        predicted_direction="up",
        horizon_days=180,
        predicted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    store.record_forecast(rec)
    row = store.get_forecast(rec.forecast_id)
    assert row["horizon_days"] == 180
    assert "2024-01-01" in row["predicted_at"]
