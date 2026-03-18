"""Tests for Wave M — Weighted Thesis Strength extensions to ThesisTracker."""
from __future__ import annotations

import tempfile

import pytest

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.thesis_tracker import (
    ClaimType,
    DEFAULT_CLAIM_WEIGHTS,
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


# ---------------------------------------------------------------------------
# Default weights
# ---------------------------------------------------------------------------

def test_default_weights_dict_has_all_claim_types() -> None:
    for ct in ClaimType:
        assert ct.value in DEFAULT_CLAIM_WEIGHTS, f"Missing weight for {ct}"


def test_endpoint_met_has_highest_weight() -> None:
    assert DEFAULT_CLAIM_WEIGHTS[ClaimType.ENDPOINT_MET] >= max(
        v for k, v in DEFAULT_CLAIM_WEIGHTS.items()
        if k != ClaimType.ENDPOINT_MET
    )


def test_market_reaction_has_lowest_weight() -> None:
    assert DEFAULT_CLAIM_WEIGHTS[ClaimType.MARKET_REACTION_POSITIVE] <= min(
        v for k, v in DEFAULT_CLAIM_WEIGHTS.items()
        if k != ClaimType.MARKET_REACTION_POSITIVE
    )


# ---------------------------------------------------------------------------
# add_claim uses default weights
# ---------------------------------------------------------------------------

def test_add_claim_uses_default_weight_for_endpoint_met() -> None:
    tracker, store = _make_tracker()
    try:
        claim = tracker.add_claim(
            asset_id="a-1", company_id="co-1",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="primary endpoint will be met",
        )
        assert claim.weight == DEFAULT_CLAIM_WEIGHTS[ClaimType.ENDPOINT_MET]
    finally:
        store.close()


def test_add_claim_accepts_explicit_weight() -> None:
    tracker, store = _make_tracker()
    try:
        claim = tracker.add_claim(
            asset_id="a-1", company_id="co-1",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="endpoint met",
            weight=3.0,
        )
        assert claim.weight == pytest.approx(3.0)
    finally:
        store.close()


def test_add_claim_weight_persisted() -> None:
    tracker, store = _make_tracker()
    try:
        claim = tracker.add_claim(
            asset_id="a-1", company_id="co-1",
            claim_type=ClaimType.REGULATORY_PATHWAY,
            assertion="breakthrough therapy",
            weight=2.5,
        )
        retrieved = tracker.get_claim(claim.claim_id)
        assert retrieved is not None
        assert retrieved.weight == pytest.approx(2.5)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# weighted_thesis_strength
# ---------------------------------------------------------------------------

def test_snapshot_has_weighted_thesis_strength_none_when_no_resolved() -> None:
    tracker, store = _make_tracker()
    try:
        tracker.add_claim("a-1", "co-1", ClaimType.ENDPOINT_MET, "will meet endpoint")
        snap = tracker.snapshot("a-1")
        assert snap.weighted_thesis_strength is None
    finally:
        store.close()


def test_weighted_strength_equals_unweighted_when_all_same_weight() -> None:
    """When all claims have equal weight, weighted == unweighted."""
    tracker, store = _make_tracker()
    try:
        c1 = tracker.add_claim("a-1", "co-1", ClaimType.CUSTOM, "claim 1", weight=1.0)
        c2 = tracker.add_claim("a-1", "co-1", ClaimType.CUSTOM, "claim 2", weight=1.0)
        tracker.resolve_claim(c1.claim_id, "confirmed")
        tracker.resolve_claim(c2.claim_id, "refuted")
        snap = tracker.snapshot("a-1")
        assert abs(snap.thesis_strength - snap.weighted_thesis_strength) < 1e-6
    finally:
        store.close()


def test_weighted_strength_differs_with_unequal_weights() -> None:
    """
    2 confirmed MARKET_REACTION_POSITIVE (weight=0.5 each) + 1 refuted ENDPOINT_MET (weight=2.0)
    Unweighted: 2/3 ≈ 0.667
    Weighted: (0.5+0.5) / (0.5+0.5+2.0) = 1.0 / 3.0 ≈ 0.333
    """
    tracker, store = _make_tracker()
    try:
        c1 = tracker.add_claim("a-1", "co-1", ClaimType.MARKET_REACTION_POSITIVE, "mkt reaction 1")
        c2 = tracker.add_claim("a-1", "co-1", ClaimType.MARKET_REACTION_POSITIVE, "mkt reaction 2")
        c3 = tracker.add_claim("a-1", "co-1", ClaimType.ENDPOINT_MET, "endpoint met")
        tracker.resolve_claim(c1.claim_id, "confirmed")
        tracker.resolve_claim(c2.claim_id, "confirmed")
        tracker.resolve_claim(c3.claim_id, "refuted")
        snap = tracker.snapshot("a-1")
        assert abs(snap.thesis_strength - (2 / 3)) < 0.01          # unweighted ~0.667
        assert abs(snap.weighted_thesis_strength - (1.0 / 3.0)) < 0.01  # weighted ~0.333
    finally:
        store.close()


def test_refuted_critical_claim_dominates_trivial_confirmations() -> None:
    """
    Key concern: 2 easy confirms + 1 critical refute → misleading if unweighted.
    Weighted_thesis_strength should be significantly lower than thesis_strength.
    """
    tracker, store = _make_tracker()
    try:
        # Two easy confirms
        c1 = tracker.add_claim("a-1", "co-1", ClaimType.MARKET_REACTION_POSITIVE, "mkt positive 1")
        c2 = tracker.add_claim("a-1", "co-1", ClaimType.ENROLLMENT_ON_TRACK, "enrollment on track")
        # One critical refute
        c3 = tracker.add_claim("a-1", "co-1", ClaimType.ENDPOINT_MET, "primary endpoint")
        tracker.resolve_claim(c1.claim_id, "confirmed")
        tracker.resolve_claim(c2.claim_id, "confirmed")
        tracker.resolve_claim(c3.claim_id, "refuted")

        snap = tracker.snapshot("a-1")
        # Unweighted: 2 confirmed / 3 total = 0.667 (misleadingly high)
        assert snap.thesis_strength == pytest.approx(2 / 3, abs=0.01)
        # Weighted: endpoint_met(2.0) refuted, enrollment(0.75)+market(0.5)=1.25 confirmed
        # = 1.25 / (1.25 + 2.0) = 1.25 / 3.25 ≈ 0.385
        expected_weighted = 1.25 / (1.25 + 2.0)
        assert abs(snap.weighted_thesis_strength - expected_weighted) < 0.01
        assert snap.weighted_thesis_strength < snap.thesis_strength
    finally:
        store.close()


def test_all_confirmed_weighted_strength_one() -> None:
    tracker, store = _make_tracker()
    try:
        c1 = tracker.add_claim("a-1", "co-1", ClaimType.ENDPOINT_MET, "endpoint")
        c2 = tracker.add_claim("a-1", "co-1", ClaimType.REGULATORY_PATHWAY, "BTD")
        tracker.resolve_claim(c1.claim_id, "confirmed")
        tracker.resolve_claim(c2.claim_id, "confirmed")
        snap = tracker.snapshot("a-1")
        assert snap.weighted_thesis_strength == pytest.approx(1.0)
    finally:
        store.close()


def test_thesis_strength_backward_compatible() -> None:
    """Existing thesis_strength field still works exactly as before."""
    tracker, store = _make_tracker()
    try:
        c1 = tracker.add_claim("a-1", "co-1", ClaimType.ENDPOINT_MET, "endpoint")
        c2 = tracker.add_claim("a-1", "co-1", ClaimType.COMPETITOR_FAILURE, "competitor fails")
        tracker.resolve_claim(c1.claim_id, "confirmed")
        tracker.resolve_claim(c2.claim_id, "refuted")
        snap = tracker.snapshot("a-1")
        assert snap.thesis_strength == pytest.approx(0.5)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Schema migration — idempotent
# ---------------------------------------------------------------------------

def test_schema_migration_idempotent() -> None:
    """Creating ThesisTracker twice on same DB is safe (column already exists)."""
    tracker, store = _make_tracker()
    try:
        # Second construction — ALTER TABLE weight should be caught silently
        tracker2 = ThesisTracker(store)
        claim = tracker2.add_claim("a-1", "co-1", ClaimType.CUSTOM, "claim", weight=1.5)
        assert claim.weight == pytest.approx(1.5)
    finally:
        store.close()
