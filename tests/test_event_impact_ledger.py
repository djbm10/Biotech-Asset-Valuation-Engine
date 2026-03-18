"""Tests for Wave 3A — Event Impact Ledger."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

import pytest

from bve.intelligence.event_impact_ledger import (
    MIN_OBSERVATIONS,
    HALF_LIFE_DAYS,
    DEFAULT_EVENT_TYPE_SCORES,
    EventCategory,
    EventImpactScore,
    EventImpactLedger,
    _ewm_score,
    effective_t30_score,
    get_default_score,
)
from bve.intelligence.knowledge_layer import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    ks = KnowledgeStore(db_path=":memory:")
    yield ks
    ks.close()


@pytest.fixture
def ref_date() -> date:
    return date(2025, 1, 1)


def _seed_outcomes(store: KnowledgeStore, rows: list[dict]) -> None:
    """Insert synthetic event_outcomes rows directly for testing."""
    for row in rows:
        store._conn.execute(
            """
            INSERT OR IGNORE INTO event_outcomes
                (outcome_id, event_id, asset_id, event_type, signal_date,
                 market_return_t30, market_return_t180,
                 resolved_t30, resolved_t180, fully_resolved,
                 created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["outcome_id"],
                row["event_id"],
                row.get("asset_id", "test-asset"),
                row["event_type"],
                row["signal_date"],
                row.get("market_return_t30"),
                row.get("market_return_t180"),
                row.get("resolved_t30", 1),
                row.get("resolved_t180", 0),
                row.get("fully_resolved", 0),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    store._conn.commit()


def _make_rows(
    n: int,
    event_type: str = "trial_results",
    return_t30: float = 0.05,
    signal_date: str = "2024-01-01",
    resolved_t30: int = 1,
    id_offset: int = 0,
) -> list[dict]:
    return [
        {
            "outcome_id": f"oc-{id_offset + i}",
            "event_id": f"ev-{id_offset + i}",
            "event_type": event_type,
            "signal_date": signal_date,
            "market_return_t30": return_t30,
            "market_return_t180": None,
            "resolved_t30": resolved_t30,
            "resolved_t180": 0,
            "fully_resolved": 0,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# EventCategory
# ---------------------------------------------------------------------------


def test_event_category_hash_equality():
    c1 = EventCategory(event_type="trial_results", trial_phase="PHASE3", endpoint_type="os")
    c2 = EventCategory(event_type="trial_results", trial_phase="PHASE3", endpoint_type="os")
    assert c1 == c2
    assert hash(c1) == hash(c2)


def test_event_category_hash_differs():
    c1 = EventCategory(event_type="trial_results", trial_phase="PHASE3")
    c2 = EventCategory(event_type="trial_results", trial_phase="PHASE2")
    assert c1 != c2
    assert hash(c1) != hash(c2)


def test_event_category_usable_as_dict_key():
    d: dict[EventCategory, int] = {}
    cat = EventCategory(event_type="approval", trial_phase=None, endpoint_type=None)
    d[cat] = 42
    assert d[cat] == 42


def test_event_category_optional_fields_default_none():
    cat = EventCategory(event_type="fda_decision")
    assert cat.trial_phase is None
    assert cat.endpoint_type is None


# ---------------------------------------------------------------------------
# EventImpactScore
# ---------------------------------------------------------------------------


def test_event_impact_score_auto_uuid():
    cat = EventCategory(event_type="trial_results")
    s1 = EventImpactScore(category=cat, observation_count=5, active=False)
    s2 = EventImpactScore(category=cat, observation_count=5, active=False)
    assert s1.score_id != s2.score_id


def test_event_impact_score_defaults():
    cat = EventCategory(event_type="trial_results")
    s = EventImpactScore(category=cat, observation_count=10, active=False)
    assert s.mean_return_t30 is None
    assert s.mean_return_t180 is None
    assert s.half_life_days == HALF_LIFE_DAYS
    assert isinstance(s.computed_at, datetime)


def test_event_impact_score_active_flag():
    cat = EventCategory(event_type="trial_results")
    active = EventImpactScore(category=cat, observation_count=MIN_OBSERVATIONS, active=True)
    inactive = EventImpactScore(category=cat, observation_count=MIN_OBSERVATIONS - 1, active=False)
    assert active.active is True
    assert inactive.active is False


# ---------------------------------------------------------------------------
# _ewm_score
# ---------------------------------------------------------------------------


def test_ewm_score_equal_weights_same_day():
    """All signals on same day → equal weights → simple mean."""
    ref = date(2025, 1, 1)
    returns = [0.10, 0.20, 0.30]
    dates = [ref, ref, ref]
    score = _ewm_score(returns, dates, ref, half_life_days=180.0)
    assert abs(score - 0.20) < 1e-9


def test_ewm_score_older_observations_weighted_less():
    """Recent +0.10 vs old -0.10 → score should be > 0 (recent dominates)."""
    ref = date(2025, 1, 1)
    recent = date(2024, 12, 1)   # 31 days ago
    old = date(2024, 1, 1)       # ~365 days ago
    score = _ewm_score([0.10, -0.10], [recent, old], ref, half_life_days=180.0)
    assert score > 0.0


def test_ewm_score_half_life_at_180_days():
    """Observation at exactly half_life_days ago has weight = 0.5."""
    ref = date(2025, 1, 1)
    half_life = 180.0
    # age = 180 days → w = exp(-ln2) = 0.5; current → w = 1.0
    old_date = date(2024, 7, 5)   # 180 days before 2025-01-01
    assert (ref - old_date).days == 180
    score = _ewm_score(
        [0.0, 1.0],
        [ref, old_date],
        ref,
        half_life_days=half_life,
    )
    # w_current = 1.0, w_old = 0.5 → score = (0*1 + 1*0.5)/(1+0.5) = 1/3
    expected = 0.5 / 1.5
    assert abs(score - expected) < 1e-9


def test_ewm_score_zero_total_weight_returns_zero():
    """Edge: if all weights are 0 (shouldn't happen), returns 0."""
    # Simulate by using extremely old dates and very short half-life
    # Actually _ewm_score always has total_weight > 0 unless no items,
    # but test the empty-list guard path by calling with empty lists.
    ref = date(2025, 1, 1)
    score = _ewm_score([], [], ref, half_life_days=180.0)
    assert score == 0.0


def test_ewm_score_single_observation():
    ref = date(2025, 1, 1)
    score = _ewm_score([0.07], [ref], ref, half_life_days=180.0)
    assert abs(score - 0.07) < 1e-9


# ---------------------------------------------------------------------------
# KnowledgeStore — event_scores table
# ---------------------------------------------------------------------------


def test_upsert_event_score_stores(store):
    cat = EventCategory(event_type="trial_results", trial_phase="PHASE3")
    score = EventImpactScore(
        category=cat,
        observation_count=25,
        mean_return_t30=0.05,
        active=True,
    )
    store.upsert_event_score(score)
    retrieved = store.get_event_score("trial_results", "PHASE3", None)
    assert retrieved is not None
    assert retrieved["observation_count"] == 25
    assert abs(retrieved["mean_return_t30"] - 0.05) < 1e-9
    assert retrieved["active"] == 1


def test_upsert_event_score_overwrites(store):
    cat = EventCategory(event_type="trial_results")
    s1 = EventImpactScore(category=cat, observation_count=5, mean_return_t30=0.01, active=False)
    s2 = EventImpactScore(category=cat, observation_count=25, mean_return_t30=0.08, active=True)
    store.upsert_event_score(s1)
    store.upsert_event_score(s2)
    retrieved = store.get_event_score("trial_results", None, None)
    assert retrieved["observation_count"] == 25
    assert abs(retrieved["mean_return_t30"] - 0.08) < 1e-9


def test_get_event_score_returns_none_when_missing(store):
    result = store.get_event_score("nonexistent", None, None)
    assert result is None


def test_list_event_scores_returns_all(store):
    for et in ("trial_results", "fda_decision", "approval"):
        cat = EventCategory(event_type=et)
        s = EventImpactScore(category=cat, observation_count=5, active=False)
        store.upsert_event_score(s)
    scores = store.list_event_scores(active_only=False)
    assert len(scores) == 3


def test_list_event_scores_active_only(store):
    cat_active = EventCategory(event_type="trial_results")
    cat_inactive = EventCategory(event_type="fda_decision")
    store.upsert_event_score(
        EventImpactScore(category=cat_active, observation_count=25, active=True)
    )
    store.upsert_event_score(
        EventImpactScore(category=cat_inactive, observation_count=5, active=False)
    )
    active = store.list_event_scores(active_only=True)
    assert len(active) == 1
    assert active[0]["event_type"] == "trial_results"


# ---------------------------------------------------------------------------
# EventImpactLedger — compute_scores
# ---------------------------------------------------------------------------


def test_compute_scores_empty_store_returns_empty(store, ref_date):
    ledger = EventImpactLedger(reference_date=ref_date)
    scores = ledger.compute_scores(store)
    assert scores == []


def test_compute_scores_below_min_obs_is_inactive(store, ref_date):
    rows = _make_rows(MIN_OBSERVATIONS - 1, return_t30=0.05)
    _seed_outcomes(store, rows)
    ledger = EventImpactLedger(reference_date=ref_date)
    scores = ledger.compute_scores(store)
    assert len(scores) == 1
    assert scores[0].active is False
    assert scores[0].observation_count == MIN_OBSERVATIONS - 1


def test_compute_scores_at_min_obs_is_active(store, ref_date):
    rows = _make_rows(MIN_OBSERVATIONS, return_t30=0.05)
    _seed_outcomes(store, rows)
    ledger = EventImpactLedger(reference_date=ref_date)
    scores = ledger.compute_scores(store)
    assert scores[0].active is True


def test_compute_scores_groups_by_event_type(store, ref_date):
    _seed_outcomes(store, _make_rows(5, event_type="trial_results", id_offset=0))
    _seed_outcomes(store, _make_rows(5, event_type="fda_decision", id_offset=100))
    ledger = EventImpactLedger(reference_date=ref_date)
    scores = ledger.compute_scores(store)
    assert len(scores) == 2
    types = {s.category.event_type for s in scores}
    assert "trial_results" in types
    assert "fda_decision" in types


def test_compute_scores_mean_t30_is_ewm(store, ref_date):
    """Uniform returns → mean_return_t30 equals that return value."""
    rows = _make_rows(5, return_t30=0.10, signal_date=str(ref_date))
    _seed_outcomes(store, rows)
    ledger = EventImpactLedger(reference_date=ref_date)
    scores = ledger.compute_scores(store)
    assert abs(scores[0].mean_return_t30 - 0.10) < 1e-9


def test_compute_scores_excludes_unresolved(store, ref_date):
    """Rows with resolved_t30=0 must not appear in scores."""
    rows = _make_rows(5, return_t30=0.10, resolved_t30=0)
    _seed_outcomes(store, rows)
    ledger = EventImpactLedger(reference_date=ref_date)
    scores = ledger.compute_scores(store)
    assert scores == []


def test_compute_scores_mean_t180_none_when_not_resolved(store, ref_date):
    rows = _make_rows(MIN_OBSERVATIONS, return_t30=0.05)
    _seed_outcomes(store, rows)
    ledger = EventImpactLedger(reference_date=ref_date)
    scores = ledger.compute_scores(store)
    assert scores[0].mean_return_t180 is None


def test_compute_scores_custom_half_life(store, ref_date):
    """Custom half_life stored on returned score."""
    rows = _make_rows(5, return_t30=0.05)
    _seed_outcomes(store, rows)
    ledger = EventImpactLedger(half_life_days=90.0, reference_date=ref_date)
    scores = ledger.compute_scores(store)
    assert scores[0].half_life_days == 90.0


def test_compute_scores_custom_min_obs(store, ref_date):
    """Lower min_obs threshold activates score sooner."""
    rows = _make_rows(5, return_t30=0.05)
    _seed_outcomes(store, rows)
    ledger = EventImpactLedger(min_observations=5, reference_date=ref_date)
    scores = ledger.compute_scores(store)
    assert scores[0].active is True


# ---------------------------------------------------------------------------
# EventImpactLedger — run (compute + save)
# ---------------------------------------------------------------------------


def test_run_persists_scores(store, ref_date):
    rows = _make_rows(MIN_OBSERVATIONS, return_t30=0.07)
    _seed_outcomes(store, rows)
    ledger = EventImpactLedger(reference_date=ref_date)
    returned = ledger.run(store)
    assert len(returned) == 1
    stored = store.get_event_score("trial_results", None, None)
    assert stored is not None
    assert abs(stored["mean_return_t30"] - 0.07) < 1e-9


def test_run_idempotent(store, ref_date):
    rows = _make_rows(MIN_OBSERVATIONS, return_t30=0.05)
    _seed_outcomes(store, rows)
    ledger = EventImpactLedger(reference_date=ref_date)
    ledger.run(store)
    ledger.run(store)  # second run should not duplicate
    all_scores = store.list_event_scores(active_only=False)
    assert len(all_scores) == 1


# ---------------------------------------------------------------------------
# Static fallback (small-sample protection)
# ---------------------------------------------------------------------------


def test_default_event_type_scores_covers_all_canonical_types():
    """All 20 EventType values must have a static prior."""
    from bve.intelligence.taxonomy import EventType
    for et in EventType:
        assert et.value in DEFAULT_EVENT_TYPE_SCORES, f"Missing prior for {et.value}"


def test_get_default_score_known_type():
    assert get_default_score("fda_approval") == DEFAULT_EVENT_TYPE_SCORES["fda_approval"]
    assert get_default_score("fda_rejection") == DEFAULT_EVENT_TYPE_SCORES["fda_rejection"]


def test_get_default_score_unknown_type_returns_zero():
    assert get_default_score("totally_unknown_event") == 0.0


def test_effective_t30_score_returns_static_when_no_active_scores():
    """N < MIN_OBSERVATIONS → no active score → static prior used."""
    cat = EventCategory(event_type="fda_approval")
    inactive = EventImpactScore(
        category=cat, observation_count=5, mean_return_t30=0.99, active=False
    )
    result = effective_t30_score("fda_approval", [inactive])
    assert result == DEFAULT_EVENT_TYPE_SCORES["fda_approval"]


def test_effective_t30_score_returns_computed_when_active():
    cat = EventCategory(event_type="fda_approval")
    active = EventImpactScore(
        category=cat, observation_count=MIN_OBSERVATIONS, mean_return_t30=0.25, active=True
    )
    result = effective_t30_score("fda_approval", [active])
    assert abs(result - 0.25) < 1e-9


def test_effective_t30_score_prefers_none_phase_when_multiple_active():
    """Broad (phase=None) score preferred over stratified when both active."""
    broad = EventImpactScore(
        category=EventCategory(event_type="trial_readout", trial_phase=None),
        observation_count=MIN_OBSERVATIONS, mean_return_t30=0.10, active=True,
    )
    stratified = EventImpactScore(
        category=EventCategory(event_type="trial_readout", trial_phase="PHASE3"),
        observation_count=MIN_OBSERVATIONS, mean_return_t30=0.20, active=True,
    )
    result = effective_t30_score("trial_readout", [stratified, broad])
    assert abs(result - 0.10) < 1e-9


def test_effective_t30_score_empty_list_returns_static():
    result = effective_t30_score("fda_rejection", [])
    assert result == DEFAULT_EVENT_TYPE_SCORES["fda_rejection"]
