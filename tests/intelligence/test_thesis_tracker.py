"""Tests for Wave I — ThesisTracker structured claims."""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta, timezone

import pytest

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.thesis_tracker import (
    ClaimType,
    ThesisClaim,
    ThesisSnapshot,
    ThesisTracker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker() -> tuple[ThesisTracker, KnowledgeStore]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    store = KnowledgeStore(tmp.name)
    tracker = ThesisTracker(store)
    return tracker, store


_TODAY = date(2026, 3, 17)


def _add_claim(
    tracker: ThesisTracker,
    idx: int = 0,
    *,
    claim_type: ClaimType = ClaimType.ENDPOINT_MET,
    assertion: str = "primary endpoint will be met",
    resolution_date: date | None = None,
) -> ThesisClaim:
    return tracker.add_claim(
        asset_id=f"asset-{idx}",
        company_id=f"co-{idx}",
        claim_type=claim_type,
        assertion=assertion,
        resolution_date=resolution_date,
        created_by_signal_id=f"sig-{idx}",
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schema_creates_table() -> None:
    tracker, store = _make_tracker()
    try:
        row = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='thesis_claims'"
        ).fetchone()
        assert row is not None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# add_claim
# ---------------------------------------------------------------------------

def test_add_claim_returns_thesis_claim() -> None:
    tracker, store = _make_tracker()
    try:
        claim = _add_claim(tracker)
        assert isinstance(claim, ThesisClaim)
        assert claim.status == "open"
        assert claim.assertion == "primary endpoint will be met"
    finally:
        store.close()


def test_add_claim_persisted() -> None:
    tracker, store = _make_tracker()
    try:
        claim = _add_claim(tracker)
        retrieved = tracker.get_claim(claim.claim_id)
        assert retrieved is not None
        assert retrieved.claim_id == claim.claim_id
    finally:
        store.close()


def test_add_claim_idempotent_by_claim_id() -> None:
    """INSERT OR IGNORE — re-inserting same claim_id is safe."""
    tracker, store = _make_tracker()
    try:
        claim = _add_claim(tracker)
        # Manually try to re-insert
        store._conn.execute(
            "INSERT OR IGNORE INTO thesis_claims (claim_id, asset_id, company_id, claim_type, assertion, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (claim.claim_id, "asset-0", "co-0", "endpoint_met", "different assertion",
             datetime.now(timezone.utc).isoformat()),
        )
        store._conn.commit()
        # Original should be preserved
        retrieved = tracker.get_claim(claim.claim_id)
        assert retrieved.assertion == "primary endpoint will be met"
    finally:
        store.close()


def test_add_claim_with_numeric_threshold() -> None:
    tracker, store = _make_tracker()
    try:
        claim = tracker.add_claim(
            asset_id="a-1",
            company_id="co-1",
            claim_type=ClaimType.POS_ABOVE_THRESHOLD,
            assertion="PoS will be above 60%",
            numeric_threshold=0.60,
        )
        retrieved = tracker.get_claim(claim.claim_id)
        assert retrieved.numeric_threshold == 0.60
    finally:
        store.close()


def test_add_claim_with_categorical_value() -> None:
    tracker, store = _make_tracker()
    try:
        claim = tracker.add_claim(
            asset_id="a-1",
            company_id="co-1",
            claim_type=ClaimType.REGULATORY_PATHWAY,
            assertion="Will receive Breakthrough Therapy designation",
            categorical_value="breakthrough_therapy",
        )
        retrieved = tracker.get_claim(claim.claim_id)
        assert retrieved.categorical_value == "breakthrough_therapy"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# resolve_claim
# ---------------------------------------------------------------------------

def test_resolve_confirmed() -> None:
    tracker, store = _make_tracker()
    try:
        claim = _add_claim(tracker)
        updated = tracker.resolve_claim(
            claim.claim_id, "confirmed",
            evidence="Phase 3 ORR 58% vs 29% control (p<0.001)",
        )
        assert updated.status == "confirmed"
        assert "ORR" in updated.resolution_evidence
    finally:
        store.close()


def test_resolve_refuted() -> None:
    tracker, store = _make_tracker()
    try:
        claim = _add_claim(tracker)
        updated = tracker.resolve_claim(claim.claim_id, "refuted", evidence="Trial missed primary endpoint")
        assert updated.status == "refuted"
    finally:
        store.close()


def test_resolve_unknown_claim_returns_none() -> None:
    tracker, store = _make_tracker()
    try:
        result = tracker.resolve_claim("nonexistent-id", "confirmed")
        assert result is None
    finally:
        store.close()


def test_resolve_invalid_status_raises() -> None:
    tracker, store = _make_tracker()
    try:
        claim = _add_claim(tracker)
        with pytest.raises(ValueError):
            tracker.resolve_claim(claim.claim_id, "open")   # type: ignore[arg-type]
    finally:
        store.close()


def test_resolve_persisted() -> None:
    tracker, store = _make_tracker()
    try:
        claim = _add_claim(tracker)
        tracker.resolve_claim(claim.claim_id, "confirmed", evidence="Positive data")
        retrieved = tracker.get_claim(claim.claim_id)
        assert retrieved.status == "confirmed"
        assert retrieved.resolution_evidence == "Positive data"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# supersede_claim
# ---------------------------------------------------------------------------

def test_supersede_marks_old_superseded() -> None:
    tracker, store = _make_tracker()
    try:
        old = _add_claim(tracker, assertion="PoS above 50%")
        new_claim = ThesisClaim(
            asset_id="asset-0",
            company_id="co-0",
            claim_type=ClaimType.POS_ABOVE_THRESHOLD,
            assertion="PoS above 60% (updated after interim)",
            numeric_threshold=0.60,
        )
        tracker.supersede_claim(old.claim_id, new_claim)
        old_retrieved = tracker.get_claim(old.claim_id)
        assert old_retrieved.status == "superseded"
    finally:
        store.close()


def test_supersede_new_claim_is_open() -> None:
    tracker, store = _make_tracker()
    try:
        old = _add_claim(tracker)
        new_claim = ThesisClaim(
            asset_id="asset-0",
            company_id="co-0",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="Revised endpoint met claim",
        )
        new_stored = tracker.supersede_claim(old.claim_id, new_claim)
        assert new_stored.status == "open"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# expire_overdue_claims
# ---------------------------------------------------------------------------

def test_expire_overdue_claims() -> None:
    tracker, store = _make_tracker()
    try:
        past_date = _TODAY - timedelta(days=10)
        future_date = _TODAY + timedelta(days=30)
        overdue = _add_claim(tracker, idx=0, resolution_date=past_date)
        future = _add_claim(tracker, idx=1, resolution_date=future_date)
        n = tracker.expire_overdue_claims(as_of=_TODAY)
        assert n == 1
        assert tracker.get_claim(overdue.claim_id).status == "expired"
        assert tracker.get_claim(future.claim_id).status == "open"
    finally:
        store.close()


def test_expire_overdue_no_resolution_date_unaffected() -> None:
    tracker, store = _make_tracker()
    try:
        claim = _add_claim(tracker, resolution_date=None)
        n = tracker.expire_overdue_claims(as_of=_TODAY)
        assert n == 0
        assert tracker.get_claim(claim.claim_id).status == "open"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

def test_snapshot_empty_asset() -> None:
    tracker, store = _make_tracker()
    try:
        snap = tracker.snapshot("nonexistent-asset")
        assert snap.n_open == 0
        assert snap.thesis_strength is None
    finally:
        store.close()


def test_snapshot_counts() -> None:
    tracker, store = _make_tracker()
    try:
        c1 = _add_claim(tracker, idx=0)
        c2 = _add_claim(tracker, idx=0, claim_type=ClaimType.MARKET_REACTION_POSITIVE,
                         assertion="Market will react positively")
        c3 = _add_claim(tracker, idx=0, claim_type=ClaimType.COMPETITOR_FAILURE,
                         assertion="Competitor will fail")
        tracker.resolve_claim(c1.claim_id, "confirmed", evidence="Data positive")
        tracker.resolve_claim(c2.claim_id, "refuted", evidence="Market sold off")
        snap = tracker.snapshot("asset-0")
        assert snap.n_open == 1
        assert snap.n_confirmed == 1
        assert snap.n_refuted == 1
        assert snap.n_expired == 0
    finally:
        store.close()


def test_snapshot_thesis_strength() -> None:
    tracker, store = _make_tracker()
    try:
        c1 = _add_claim(tracker, idx=0)
        c2 = _add_claim(tracker, idx=0, claim_type=ClaimType.MARKET_REACTION_POSITIVE,
                         assertion="Market reaction positive")
        tracker.resolve_claim(c1.claim_id, "confirmed")
        tracker.resolve_claim(c2.claim_id, "refuted")
        snap = tracker.snapshot("asset-0")
        # 1 confirmed, 1 refuted → strength = 0.5
        assert abs(snap.thesis_strength - 0.5) < 1e-9
    finally:
        store.close()


def test_snapshot_all_confirmed_strength_one() -> None:
    tracker, store = _make_tracker()
    try:
        c1 = _add_claim(tracker, idx=0)
        c2 = _add_claim(tracker, idx=0, claim_type=ClaimType.COMPETITOR_FAILURE,
                         assertion="Competitor fails")
        tracker.resolve_claim(c1.claim_id, "confirmed")
        tracker.resolve_claim(c2.claim_id, "confirmed")
        snap = tracker.snapshot("asset-0")
        assert snap.thesis_strength == 1.0
    finally:
        store.close()


# ---------------------------------------------------------------------------
# get_claims
# ---------------------------------------------------------------------------

def test_get_claims_filter_by_status() -> None:
    tracker, store = _make_tracker()
    try:
        c1 = _add_claim(tracker, idx=0)
        _add_claim(tracker, idx=0, claim_type=ClaimType.ENDPOINT_MET,
                   assertion="Another endpoint claim")
        tracker.resolve_claim(c1.claim_id, "confirmed")
        confirmed = tracker.get_claims(status="confirmed")
        assert len(confirmed) == 1
    finally:
        store.close()


def test_get_claims_filter_by_type() -> None:
    tracker, store = _make_tracker()
    try:
        _add_claim(tracker, idx=0, claim_type=ClaimType.ENDPOINT_MET)
        _add_claim(tracker, idx=0, claim_type=ClaimType.COMPETITOR_FAILURE,
                   assertion="Competitor fails")
        endpoint_claims = tracker.get_claims(claim_type=ClaimType.ENDPOINT_MET)
        assert len(endpoint_claims) == 1
        assert endpoint_claims[0].claim_type == ClaimType.ENDPOINT_MET
    finally:
        store.close()
