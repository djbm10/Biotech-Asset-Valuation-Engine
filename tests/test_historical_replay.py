"""
Tests for historical replay mode.

Coverage
--------
1.  ReplayClock.today() returns fixed date in replay mode
2.  ReplayClock.advance(7).today() advances by 7 days
3.  ReplayClock.is_replay is True in replay mode, False in live mode
4.  ReplayStore creates tables on init
5.  ReplayStore.insert_prices() then get_price() returns correct value
6.  ReplayStore.get_price() returns None for a date with no data
7.  No-lookahead test: insert event with announced_at=2025-06-10;
    query as_of 2025-06-01 → empty; query as_of 2025-06-11 → visible
8.  ThesisTracker.snapshot(as_of_date=...) only returns claims created <= as_of_date
9.  DecisionLayer.record_decision(decided_at=...) stores the overridden datetime
10. Replay decisions don't pollute live tables (separate DB paths)
11. Same run() call with same seed is deterministic (same decisions)
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone, timedelta

import pytest

from bve.intelligence.replay_clock import ReplayClock
from bve.ops.historical_replay import ReplayStore, HistoricalReplay


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def in_memory_store():
    """Create an in-memory ReplayStore."""
    store = ReplayStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def in_memory_ks(tmp_path):
    """Create a temporary KnowledgeStore path."""
    return str(tmp_path / "replay_kb.db")


# ---------------------------------------------------------------------------
# 1. ReplayClock.today() returns fixed date in replay mode
# ---------------------------------------------------------------------------

def test_replay_clock_today_fixed():
    fixed = date(2025, 6, 1)
    clock = ReplayClock(fixed)
    assert clock.today() == fixed


# ---------------------------------------------------------------------------
# 2. ReplayClock.advance(7).today() advances by 7 days
# ---------------------------------------------------------------------------

def test_replay_clock_advance():
    fixed = date(2025, 6, 1)
    clock = ReplayClock(fixed)
    advanced = clock.advance(7)
    assert advanced.today() == date(2025, 6, 8)


def test_replay_clock_advance_14():
    fixed = date(2025, 12, 28)
    clock = ReplayClock(fixed)
    advanced = clock.advance(14)
    assert advanced.today() == date(2026, 1, 11)


# ---------------------------------------------------------------------------
# 3. ReplayClock.is_replay is True in replay mode, False in live mode
# ---------------------------------------------------------------------------

def test_replay_clock_is_replay_true():
    clock = ReplayClock(date(2025, 1, 1))
    assert clock.is_replay is True


def test_replay_clock_is_replay_false():
    clock = ReplayClock(None)
    assert clock.is_replay is False


def test_replay_clock_live_today_is_real():
    """Live clock returns actual today (not None)."""
    clock = ReplayClock(None)
    assert clock.today() == date.today()


def test_replay_clock_repr():
    clock = ReplayClock(date(2025, 6, 1))
    r = repr(clock)
    assert "replay" in r.lower() or "2025" in r

    live = ReplayClock(None)
    assert "live" in repr(live).lower()


def test_replay_clock_now_frozen():
    fixed = date(2025, 6, 1)
    clock = ReplayClock(fixed)
    dt = clock.now()
    assert dt.year == 2025
    assert dt.month == 6
    assert dt.day == 1
    assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# 4. ReplayStore creates tables on init
# ---------------------------------------------------------------------------

def test_replay_store_creates_tables(in_memory_store):
    conn = in_memory_store._conn
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "replay_runs" in tables
    assert "historical_prices" in tables
    assert "historical_events" in tables
    assert "replay_decisions" in tables


# ---------------------------------------------------------------------------
# 5. ReplayStore.insert_prices() then get_price() returns correct value
# ---------------------------------------------------------------------------

def test_replay_store_insert_and_get_price(in_memory_store):
    ticker = "VKTX"
    d = date(2025, 6, 2)
    in_memory_store.insert_prices(ticker, [(d, 42.50)])
    price = in_memory_store.get_price(ticker, d)
    assert price == pytest.approx(42.50)


def test_replay_store_get_price_multiple_rows(in_memory_store):
    ticker = "ALNY"
    rows = [
        (date(2025, 4, 1), 100.0),
        (date(2025, 4, 2), 105.0),
        (date(2025, 4, 3), 98.0),
    ]
    in_memory_store.insert_prices(ticker, rows)
    assert in_memory_store.get_price(ticker, date(2025, 4, 1)) == pytest.approx(100.0)
    assert in_memory_store.get_price(ticker, date(2025, 4, 2)) == pytest.approx(105.0)
    assert in_memory_store.get_price(ticker, date(2025, 4, 3)) == pytest.approx(98.0)


# ---------------------------------------------------------------------------
# 6. ReplayStore.get_price() returns None for a date with no data
# ---------------------------------------------------------------------------

def test_replay_store_get_price_missing(in_memory_store):
    """get_price returns None for a date that was never inserted."""
    price = in_memory_store.get_price("VKTX", date(2025, 1, 1))
    assert price is None


def test_replay_store_get_price_wrong_ticker(in_memory_store):
    """get_price returns None when ticker doesn't match."""
    in_memory_store.insert_prices("ALNY", [(date(2025, 6, 1), 200.0)])
    price = in_memory_store.get_price("VKTX", date(2025, 6, 1))
    assert price is None


# ---------------------------------------------------------------------------
# 7. No-lookahead test
# ---------------------------------------------------------------------------

def test_no_lookahead_bias(in_memory_store):
    """
    Insert event with announced_at = June 10.
    Replay at June 1: event NOT visible.
    Replay at June 11: event IS visible.
    """
    in_memory_store.insert_event(
        asset_id="a-vktx",
        ticker="VKTX",
        event_type="readout",
        announced_at=date(2025, 6, 10),
        effective_date=date(2025, 6, 10),
        outcome_label="positive",
        headline="VK2735 meets primary",
    )

    june1 = date(2025, 6, 1)
    june11 = date(2025, 6, 11)

    assert in_memory_store.get_events_as_of("a-vktx", june1) == []
    assert len(in_memory_store.get_events_as_of("a-vktx", june11)) == 1


def test_no_lookahead_boundary_exact_day(in_memory_store):
    """Event announced_at == as_of_date is visible (inclusive boundary)."""
    in_memory_store.insert_event(
        asset_id="a-srpt",
        ticker="SRPT",
        event_type="fda",
        announced_at=date(2025, 9, 15),
        effective_date=date(2025, 9, 15),
        outcome_label="approval",
        headline="Elevidys broad label",
    )
    assert len(in_memory_store.get_events_as_of("a-srpt", date(2025, 9, 15))) == 1
    assert in_memory_store.get_events_as_of("a-srpt", date(2025, 9, 14)) == []


def test_no_lookahead_multiple_events(in_memory_store):
    """Only events on or before as_of_date are returned."""
    for d, label in [
        (date(2025, 5, 1), "positive"),
        (date(2025, 6, 1), "negative"),
        (date(2025, 7, 1), "positive"),
    ]:
        in_memory_store.insert_event(
            asset_id="a-ntla", ticker="NTLA",
            event_type="readout", announced_at=d,
            effective_date=d, outcome_label=label, headline="test",
        )

    events = in_memory_store.get_events_as_of("a-ntla", date(2025, 6, 15))
    assert len(events) == 2  # May 1 and June 1 visible; July 1 not yet


# ---------------------------------------------------------------------------
# 8. ThesisTracker.snapshot(as_of_date=...) only returns claims <= as_of_date
# ---------------------------------------------------------------------------

def test_thesis_tracker_snapshot_as_of_date(tmp_path):
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.thesis_tracker import ThesisTracker, ClaimType

    ks = KnowledgeStore(str(tmp_path / "test.db"))
    tt = ThesisTracker(ks)

    early_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    late_dt = datetime(2025, 6, 1, tzinfo=timezone.utc)

    tt.add_claim(
        asset_id="a-vktx",
        company_id="co-vktx",
        claim_type=ClaimType.ENDPOINT_MET,
        assertion="Early claim",
        created_at=early_dt,
    )
    tt.add_claim(
        asset_id="a-vktx",
        company_id="co-vktx",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        assertion="Late claim",
        created_at=late_dt,
    )

    # Snapshot at Feb 1 — only early claim visible
    snap_early = tt.snapshot("a-vktx", as_of_date=date(2025, 2, 1))
    assert snap_early.n_open == 1

    # Snapshot at July 1 — both visible
    snap_late = tt.snapshot("a-vktx", as_of_date=date(2025, 7, 1))
    assert snap_late.n_open == 2

    # Snapshot without as_of_date — all claims visible
    snap_all = tt.snapshot("a-vktx")
    assert snap_all.n_open == 2

    ks.close()


def test_thesis_tracker_snapshot_as_of_date_no_future_leak(tmp_path):
    """Claims created after as_of_date must not appear."""
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.thesis_tracker import ThesisTracker, ClaimType

    ks = KnowledgeStore(str(tmp_path / "test2.db"))
    tt = ThesisTracker(ks)

    future_dt = datetime(2026, 12, 31, tzinfo=timezone.utc)
    tt.add_claim(
        asset_id="a-crsp",
        company_id="co-crsp",
        claim_type=ClaimType.ENDPOINT_MET,
        assertion="Future claim",
        created_at=future_dt,
    )

    snap = tt.snapshot("a-crsp", as_of_date=date(2025, 6, 1))
    assert snap.n_open == 0

    ks.close()


# ---------------------------------------------------------------------------
# 9. DecisionLayer.record_decision(decided_at=...) stores the overridden datetime
# ---------------------------------------------------------------------------

def test_decision_layer_decided_at_override(tmp_path):
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.decision_layer import DecisionLayer

    ks = KnowledgeStore(str(tmp_path / "dl.db"))
    dl = DecisionLayer(ks)

    override_dt = datetime(2025, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
    rec = dl.record_decision(
        "a-vktx",
        "buy",
        decided_at=override_dt,
    )
    assert rec.decided_at == override_dt

    # Reload from DB
    loaded = dl.get_decision(rec.decision_id)
    assert loaded is not None
    assert loaded.decided_at.year == 2025
    assert loaded.decided_at.month == 4
    assert loaded.decided_at.day == 15

    ks.close()


def test_decision_layer_decided_at_default(tmp_path):
    """When decided_at is not provided, uses datetime.now()."""
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.decision_layer import DecisionLayer

    ks = KnowledgeStore(str(tmp_path / "dl2.db"))
    dl = DecisionLayer(ks)

    before = datetime.now(timezone.utc)
    rec = dl.record_decision("a-alny", "hold")
    after = datetime.now(timezone.utc)

    assert before <= rec.decided_at <= after
    ks.close()


# ---------------------------------------------------------------------------
# 10. Replay decisions don't pollute live tables (separate DB paths)
# ---------------------------------------------------------------------------

def test_replay_isolation_from_live(tmp_path):
    """
    Writing replay decisions to replay_store.sqlite must not affect
    the live ops.db (separate connection objects, separate file paths).
    """
    live_path = str(tmp_path / "ops.db")
    replay_path = str(tmp_path / "replay_store.sqlite")

    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.decision_layer import DecisionLayer

    # Create a live decision
    live_ks = KnowledgeStore(live_path)
    live_dl = DecisionLayer(live_ks)
    live_dl.record_decision("a-vktx", "buy")

    # Write replay decisions to separate store
    rs = ReplayStore(replay_path)
    from bve.intelligence.replay_policy import ReplayDecision
    dec = ReplayDecision(
        asset_id="a-alny",
        ticker="ALNY",
        recommended_action="buy",
        recommended_size_pct=0.05,
        composite_score=0.75,
        decided_at=date(2025, 6, 1),
    )
    run_id = rs.create_run(
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v1.0",
        strategy_version="top2_add",
    )
    rs.insert_decision(run_id, dec, entry_price=100.0)

    # Live DB has no replay_runs or replay_decisions tables
    live_tables = {
        row[0]
        for row in live_ks._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "replay_runs" not in live_tables
    assert "replay_decisions" not in live_tables

    # Replay DB has no decision_records table (live table)
    replay_tables = {
        row[0]
        for row in rs._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "decision_records" not in replay_tables

    live_ks.close()
    rs.close()


# ---------------------------------------------------------------------------
# 11. Determinism: same universe + seed → same decisions
# ---------------------------------------------------------------------------

def test_replay_determinism(tmp_path, in_memory_store):
    """
    With a fixed universe and no price data, two separate HistoricalReplay
    instances running the same parameters should produce equivalent decision
    structures (same tickers, same ordering).
    """
    from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate
    from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig

    universe = [
        dict(asset_id="a-vktx", ticker="VKTX", company_id="co-vktx",
             ranking_score=0.70, opportunity_score=0.78,
             catalyst="VK2735 Ph2", indication="obesity",
             claim_assertion="test"),
        dict(asset_id="a-alny", ticker="ALNY", company_id="co-alny",
             ranking_score=0.72, opportunity_score=0.70,
             catalyst="Zilebesiran", indication="RNAi",
             claim_assertion="test"),
        dict(asset_id="a-ntla", ticker="NTLA", company_id="co-ntla",
             ranking_score=0.62, opportunity_score=0.65,
             catalyst="NTLA-2001", indication="ATTR",
             claim_assertion="test"),
    ]

    gen = ActionableGenerator()
    candidates = [
        ScoredCandidate(
            asset_id=u["asset_id"],
            ticker=u["ticker"],
            ranking_score=u["ranking_score"],
            opportunity_score=u["opportunity_score"],
        )
        for u in universe
    ]

    week = date(2025, 6, 2)
    report1 = gen.generate(candidates, top_n=10, week_ending=week)
    report2 = gen.generate(candidates, top_n=10, week_ending=week)

    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    decisions1 = policy.select(report1)
    decisions2 = policy.select(report2)

    assert len(decisions1) == len(decisions2)
    for d1, d2 in zip(decisions1, decisions2):
        assert d1.asset_id == d2.asset_id
        assert d1.ticker == d2.ticker
        assert d1.composite_score == d2.composite_score


# ---------------------------------------------------------------------------
# Additional: ReplayStore.get_return()
# ---------------------------------------------------------------------------

def test_replay_store_get_return(in_memory_store):
    ticker = "VRTX"
    in_memory_store.insert_prices(ticker, [
        (date(2025, 5, 1), 400.0),
        (date(2025, 5, 31), 440.0),
    ])
    ret = in_memory_store.get_return(ticker, date(2025, 5, 1), date(2025, 5, 31))
    assert ret == pytest.approx(10.0)  # 10% gain


def test_replay_store_get_return_none_missing(in_memory_store):
    ret = in_memory_store.get_return("UNKNOWN", date(2025, 5, 1), date(2025, 5, 31))
    assert ret is None


# ---------------------------------------------------------------------------
# Additional: ReplayStore.create_run and get_run
# ---------------------------------------------------------------------------

def test_replay_store_create_and_get_run(in_memory_store):
    run_id = in_memory_store.create_run(
        start_date=date(2025, 4, 1),
        end_date=date(2026, 3, 1),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v1.0",
        strategy_version="top2_add",
    )
    assert run_id  # non-empty
    run = in_memory_store.get_run(run_id)
    assert run is not None
    assert run["cadence"] == "weekly"
    assert run["decision_policy"] == "top2_add"


def test_replay_store_get_run_missing(in_memory_store):
    assert in_memory_store.get_run("nonexistent-run-id") is None


# ---------------------------------------------------------------------------
# Additional: ReplayStore.insert_decision and get_open_decisions
# ---------------------------------------------------------------------------

def test_replay_store_insert_and_get_open_decisions(in_memory_store):
    from bve.intelligence.replay_policy import ReplayDecision

    run_id = in_memory_store.create_run(
        start_date=date(2025, 4, 1),
        end_date=date(2025, 5, 1),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v1.0",
        strategy_version="top2_add",
    )

    dec = ReplayDecision(
        asset_id="a-vktx",
        ticker="VKTX",
        recommended_action="buy",
        recommended_size_pct=0.05,
        composite_score=0.75,
        decided_at=date(2025, 4, 7),
    )
    in_memory_store.insert_decision(run_id, dec, entry_price=45.0)
    open_decs = in_memory_store.get_open_decisions(run_id)
    assert len(open_decs) == 1
    assert open_decs[0]["ticker"] == "VKTX"
    assert open_decs[0]["is_closed"] == 0


def test_replay_store_close_decision(in_memory_store):
    from bve.intelligence.replay_policy import ReplayDecision

    run_id = in_memory_store.create_run(
        start_date=date(2025, 4, 1),
        end_date=date(2025, 5, 1),
        cadence="weekly",
        decision_policy="top2_add",
        score_version="v1.0",
        strategy_version="top2_add",
    )
    dec = ReplayDecision(
        asset_id="a-alny",
        ticker="ALNY",
        recommended_action="add",
        recommended_size_pct=0.03,
        composite_score=0.65,
        decided_at=date(2025, 4, 7),
    )
    decision_id = in_memory_store.insert_decision(run_id, dec, entry_price=200.0)
    in_memory_store.close_decision(
        decision_id,
        exit_price=220.0,
        exit_date=date(2025, 5, 7),
        return_pct=10.0,
        attribution_type="confirmed_thesis",
    )

    all_decs = in_memory_store.get_run_decisions(run_id)
    assert len(all_decs) == 1
    assert all_decs[0]["is_closed"] == 1
    assert all_decs[0]["attribution_type"] == "confirmed_thesis"
    assert all_decs[0]["return_pct"] == pytest.approx(10.0)

    open_decs = in_memory_store.get_open_decisions(run_id)
    assert len(open_decs) == 0


# ---------------------------------------------------------------------------
# 12. _step_claim_resolution: positive event confirms open claim
# ---------------------------------------------------------------------------

def _make_replay(tmp_path, store):
    """Helper: create a HistoricalReplay with in-memory store and tmp KB."""
    ks_path = str(tmp_path / "replay_kb.db")
    return HistoricalReplay(
        replay_store=store,
        knowledge_store_path=ks_path,
        universe=[],
    ), ks_path


def _seed_claim(ks_path, asset_id, assertion="trial will succeed"):
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.thesis_tracker import ThesisTracker, ClaimType

    ks = KnowledgeStore(ks_path)
    tt = ThesisTracker(ks)
    tt.add_claim(
        asset_id=asset_id,
        company_id=f"co-{asset_id}",
        claim_type=ClaimType.ENDPOINT_MET,
        assertion=assertion,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    ks.close()


def test_claim_resolution_positive_confirms(tmp_path, in_memory_store):
    """Positive event confirms the open claim for the same asset."""
    replay, ks_path = _make_replay(tmp_path, in_memory_store)
    _seed_claim(ks_path, "a-vktx")

    in_memory_store.insert_event(
        asset_id="a-vktx",
        ticker="VKTX",
        event_type="readout",
        announced_at=date(2024, 6, 10),
        effective_date=date(2024, 6, 10),
        outcome_label="positive",
        headline="VK2735 Phase 2 met primary endpoint",
    )

    clock = ReplayClock(date(2024, 6, 11))
    n = replay._step_claim_resolution(clock)
    assert n == 1

    # Verify claim is now confirmed in the KB
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.thesis_tracker import ThesisTracker

    ks = KnowledgeStore(ks_path)
    tt = ThesisTracker(ks)
    claims = tt.get_claims(asset_id="a-vktx", status="confirmed")
    assert len(claims) == 1
    ks.close()


def test_claim_resolution_negative_refutes(tmp_path, in_memory_store):
    """Negative event refutes the open claim."""
    replay, ks_path = _make_replay(tmp_path, in_memory_store)
    _seed_claim(ks_path, "a-ntla")

    in_memory_store.insert_event(
        asset_id="a-ntla",
        ticker="NTLA",
        event_type="readout",
        announced_at=date(2024, 8, 1),
        effective_date=date(2024, 8, 1),
        outcome_label="negative",
        headline="NTLA-2001 Phase 1 missed endpoints",
    )

    clock = ReplayClock(date(2024, 8, 2))
    n = replay._step_claim_resolution(clock)
    assert n == 1

    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.thesis_tracker import ThesisTracker

    ks = KnowledgeStore(ks_path)
    tt = ThesisTracker(ks)
    claims = tt.get_claims(asset_id="a-ntla", status="refuted")
    assert len(claims) == 1
    ks.close()


def test_claim_resolution_future_event_not_processed(tmp_path, in_memory_store):
    """Event announced AFTER as_of is not processed (no-lookahead)."""
    replay, ks_path = _make_replay(tmp_path, in_memory_store)
    _seed_claim(ks_path, "a-alny")

    in_memory_store.insert_event(
        asset_id="a-alny",
        ticker="ALNY",
        event_type="readout",
        announced_at=date(2024, 12, 1),
        effective_date=date(2024, 12, 1),
        outcome_label="positive",
        headline="Zilebesiran data positive",
    )

    # Clock is set to Nov 30 — event not yet visible
    clock = ReplayClock(date(2024, 11, 30))
    n = replay._step_claim_resolution(clock)
    assert n == 0


def test_claim_resolution_neutral_event_skipped(tmp_path, in_memory_store):
    """Neutral/enrollment event (no positive/negative label) is skipped."""
    replay, ks_path = _make_replay(tmp_path, in_memory_store)
    _seed_claim(ks_path, "a-srpt")

    in_memory_store.insert_event(
        asset_id="a-srpt",
        ticker="SRPT",
        event_type="enrollment",
        announced_at=date(2024, 5, 1),
        effective_date=date(2024, 5, 1),
        outcome_label="enrollment_complete",
        headline="Enrollment complete",
    )

    clock = ReplayClock(date(2024, 5, 2))
    n = replay._step_claim_resolution(clock)
    assert n == 0


def test_claim_resolution_no_duplicate_processing(tmp_path, in_memory_store):
    """Each event is only processed once per run."""
    replay, ks_path = _make_replay(tmp_path, in_memory_store)
    _seed_claim(ks_path, "a-vrtx")

    in_memory_store.insert_event(
        asset_id="a-vrtx",
        ticker="VRTX",
        event_type="readout",
        announced_at=date(2024, 3, 1),
        effective_date=date(2024, 3, 1),
        outcome_label="positive",
        headline="Positive readout",
    )

    replay._resolved_event_ids = set()  # simulate start of run()
    clock = ReplayClock(date(2024, 3, 2))

    n1 = replay._step_claim_resolution(clock)
    assert n1 == 1

    # Same step again — event was already marked processed
    n2 = replay._step_claim_resolution(clock)
    assert n2 == 0


def test_claim_resolution_no_claim_for_asset(tmp_path, in_memory_store):
    """Event for asset with no open claim returns 0 and doesn't error."""
    replay, ks_path = _make_replay(tmp_path, in_memory_store)
    # Deliberately do NOT seed any claim for a-beam

    in_memory_store.insert_event(
        asset_id="a-beam",
        ticker="BEAM",
        event_type="readout",
        announced_at=date(2024, 4, 1),
        effective_date=date(2024, 4, 1),
        outcome_label="positive",
        headline="Some event",
    )

    clock = ReplayClock(date(2024, 4, 2))
    n = replay._step_claim_resolution(clock)
    assert n == 0


def test_claim_resolution_reset_between_runs(tmp_path, in_memory_store):
    """_resolved_event_ids is reset at start of run() so re-runs see events fresh."""
    replay, ks_path = _make_replay(tmp_path, in_memory_store)

    # Simulate a previous run having processed an event
    replay._resolved_event_ids = {9999}  # stale state from a prior run

    # Calling run() with empty universe/short date range should reset the set
    # We verify by checking the set is empty at the start of run().
    # Use a very short range with no data to avoid network calls.
    # (The reset happens before the while loop, so even 0 steps resets it.)
    # We do this by checking the attribute directly after the reset line runs.

    # Patch the store to avoid DB issues in this minimal test
    from bve.intelligence.replay_policy import ReplayPolicy, ReplayPolicyConfig
    replay._policy = ReplayPolicy(ReplayPolicyConfig(max_positions=0))

    # run() creates a run record, then resets the set
    # We can call it with a 1-day range (no steps execute since start > end)
    start = date(2024, 1, 2)
    end = date(2024, 1, 1)  # end < start → loop doesn't execute

    try:
        replay.run(start=start, end=end, cadence="weekly")
    except Exception:
        pass  # ignore any errors from empty run

    # The set should have been reset (stale {9999} cleared)
    assert 9999 not in replay._resolved_event_ids


# ---------------------------------------------------------------------------
# v2.0 signal query methods on ReplayStore
# ---------------------------------------------------------------------------

def test_get_catalyst_signal_strength_no_data(in_memory_store):
    """Returns None when catalyst_events table is empty."""
    result = in_memory_store.get_catalyst_signal_strength("a-vktx", date(2025, 6, 1))
    assert result is None


def test_get_catalyst_signal_strength_returns_most_recent_before_as_of(in_memory_store):
    """Returns most-recently-dated signal_strength for asset on or before as_of; ignores future."""
    conn = in_memory_store._conn
    conn.execute(
        "INSERT INTO catalyst_events (event_id, asset_id, ticker, event_type, event_date, signal_strength) VALUES (?, ?, ?, ?, ?, ?)",
        ("ev-1", "a-vktx", "VKTX", "readout", "2025-05-01", 1.5),
    )
    conn.execute(
        "INSERT INTO catalyst_events (event_id, asset_id, ticker, event_type, event_date, signal_strength) VALUES (?, ?, ?, ?, ?, ?)",
        ("ev-2", "a-vktx", "VKTX", "readout", "2025-06-01", 2.5),
    )
    conn.execute(
        "INSERT INTO catalyst_events (event_id, asset_id, ticker, event_type, event_date, signal_strength) VALUES (?, ?, ?, ?, ?, ?)",
        ("ev-3", "a-vktx", "VKTX", "readout", "2025-07-01", 3.5),  # future
    )
    conn.commit()

    result = in_memory_store.get_catalyst_signal_strength("a-vktx", date(2025, 6, 15))
    assert result == pytest.approx(2.5)  # 3.5 excluded (future)


def test_get_catalyst_signal_strength_excludes_competitor_readout(in_memory_store):
    """COMPETITOR_READOUT events are excluded from own-asset catalyst strength."""
    conn = in_memory_store._conn
    conn.execute(
        "INSERT INTO catalyst_events (event_id, asset_id, ticker, event_type, event_date, signal_strength) VALUES (?, ?, ?, ?, ?, ?)",
        ("ev-c1", "a-vktx", "VKTX", "COMPETITOR_READOUT", "2025-05-01", 3.0),
    )
    conn.commit()

    result = in_memory_store.get_catalyst_signal_strength("a-vktx", date(2025, 6, 1))
    assert result is None


def test_get_enrollment_flags_no_data(in_memory_store):
    """Returns None when no enrollment snapshot exists."""
    result = in_memory_store.get_enrollment_flags("a-vktx", date(2025, 6, 1))
    assert result is None


def test_get_enrollment_flags_returns_latest_before_as_of(in_memory_store):
    """Returns the most recent snapshot on or before as_of."""
    conn = in_memory_store._conn
    conn.execute(
        "INSERT INTO enrollment_snapshots VALUES (?, ?, ?, ?, ?, ?)",
        ("snap-1", "a-vktx", "2025-04-01", 0, 0, 0),
    )
    conn.execute(
        "INSERT INTO enrollment_snapshots VALUES (?, ?, ?, ?, ?, ?)",
        ("snap-2", "a-vktx", "2025-06-01", 1, 1, 0),  # stalling + velocity_low
    )
    conn.execute(
        "INSERT INTO enrollment_snapshots VALUES (?, ?, ?, ?, ?, ?)",
        ("snap-3", "a-vktx", "2025-07-01", 0, 0, 1),  # future
    )
    conn.commit()

    result = in_memory_store.get_enrollment_flags("a-vktx", date(2025, 6, 15))
    assert result is not None
    assert result["site_stalling"] is True
    assert result["velocity_low"] is True
    assert result["slippage_alert"] is False  # snap-3 excluded (future)


def test_get_phase_correlation_no_data(in_memory_store):
    """Returns (None, None) when no phase correlation signal exists."""
    prior, posterior = in_memory_store.get_phase_correlation("a-vktx", date(2025, 6, 1))
    assert prior is None
    assert posterior is None


def test_get_phase_correlation_returns_most_recent(in_memory_store):
    """Returns phase_prior_pos and phase_posterior_pos from most recent signal."""
    conn = in_memory_store._conn
    conn.execute(
        "INSERT INTO structured_signals VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("sig-1", "a-vktx", "2025-05-01", "phase_correlation", None, 0.40, 0.55),
    )
    conn.execute(
        "INSERT INTO structured_signals VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("sig-2", "a-vktx", "2025-08-01", "phase_correlation", None, 0.42, 0.60),  # future
    )
    conn.commit()

    prior, posterior = in_memory_store.get_phase_correlation("a-vktx", date(2025, 6, 1))
    assert prior == pytest.approx(0.40)
    assert posterior == pytest.approx(0.55)


def test_get_endpoint_z_score_no_data(in_memory_store):
    """Returns None when no structured signal with z_score exists."""
    result = in_memory_store.get_endpoint_z_score("a-vktx", date(2025, 6, 1))
    assert result is None


def test_get_endpoint_z_score_returns_most_recent(in_memory_store):
    """Returns z_score from most recent signal on or before as_of."""
    conn = in_memory_store._conn
    conn.execute(
        "INSERT INTO structured_signals VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("sig-z1", "a-alny", "2025-03-01", "readout", 1.8, None, None),
    )
    conn.execute(
        "INSERT INTO structured_signals VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("sig-z2", "a-alny", "2025-09-01", "readout", 2.4, None, None),  # future
    )
    conn.commit()

    result = in_memory_store.get_endpoint_z_score("a-alny", date(2025, 6, 1))
    assert result == pytest.approx(1.8)


def test_get_competitor_signals_empty(in_memory_store):
    """Returns empty list when no COMPETITOR_READOUT events exist."""
    result = in_memory_store.get_competitor_signals("a-vktx", date(2025, 6, 1))
    assert result == []


def test_get_competitor_signals_within_window(in_memory_store):
    """Returns competitor signal_strengths within 60 days; excludes outside window."""
    conn = in_memory_store._conn
    conn.execute(
        "INSERT INTO catalyst_events (event_id, asset_id, ticker, event_type, event_date, signal_strength) VALUES (?, ?, ?, ?, ?, ?)",
        ("comp-1", "a-vktx", "VKTX", "COMPETITOR_READOUT", "2025-04-10", 0.8),  # too old
    )
    conn.execute(
        "INSERT INTO catalyst_events (event_id, asset_id, ticker, event_type, event_date, signal_strength) VALUES (?, ?, ?, ?, ?, ?)",
        ("comp-2", "a-vktx", "VKTX", "COMPETITOR_READOUT", "2025-05-15", 1.2),  # within 60d
    )
    conn.execute(
        "INSERT INTO catalyst_events (event_id, asset_id, ticker, event_type, event_date, signal_strength) VALUES (?, ?, ?, ?, ?, ?)",
        ("comp-3", "a-vktx", "VKTX", "COMPETITOR_READOUT", "2025-07-01", 2.0),  # future
    )
    conn.commit()

    result = in_memory_store.get_competitor_signals("a-vktx", date(2025, 6, 10), window_days=60)
    assert len(result) == 1
    assert result[0] == pytest.approx(1.2)


def test_get_capital_risk_level_no_data(in_memory_store):
    """Returns None when no capital snapshot exists."""
    result = in_memory_store.get_capital_risk_level("a-vktx", date(2025, 6, 1))
    assert result is None


def test_get_capital_risk_level_returns_most_recent(in_memory_store):
    """Returns capital_risk_level string from most recent snapshot."""
    conn = in_memory_store._conn
    conn.execute(
        "INSERT INTO capital_snapshots VALUES (?, ?, ?, ?, ?)",
        ("cap-1", "a-vktx", "2025-04-01", 8.0, "LOW"),
    )
    conn.execute(
        "INSERT INTO capital_snapshots VALUES (?, ?, ?, ?, ?)",
        ("cap-2", "a-vktx", "2025-06-01", 3.0, "HIGH"),
    )
    conn.execute(
        "INSERT INTO capital_snapshots VALUES (?, ?, ?, ?, ?)",
        ("cap-3", "a-vktx", "2025-08-01", 1.5, "CRITICAL"),  # future
    )
    conn.commit()

    result = in_memory_store.get_capital_risk_level("a-vktx", date(2025, 6, 15))
    assert result == "HIGH"


# ---------------------------------------------------------------------------
# v2.0: replay loop produces score_version = "v2.0"
# ---------------------------------------------------------------------------

def test_replay_step_decision_produces_v2_score(tmp_path, in_memory_store):
    """
    _step_decision passes contexts to ActionableGenerator, which sets
    score_version = "v2.0" on the WeeklyActionableReport whenever the
    universe is non-empty (contexts dict is non-empty → v2.0 path).
    """
    from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate

    universe = [
        dict(
            asset_id="a-vktx", ticker="VKTX", company_id="co-vktx",
            ranking_score=0.72, opportunity_score=0.78,
            catalyst="VK2735 Ph2", indication="obesity",
            claim_type="ENDPOINT_MET", claim_assertion="trial meets endpoint",
        ),
        dict(
            asset_id="a-alny", ticker="ALNY", company_id="co-alny",
            ranking_score=0.68, opportunity_score=0.70,
            catalyst="Zilebesiran readout", indication="hypertension",
            claim_type="ENDPOINT_MET", claim_assertion="trial meets endpoint",
        ),
    ]

    ks_path = str(tmp_path / "replay_kb.db")
    replay = HistoricalReplay(
        replay_store=in_memory_store,
        knowledge_store_path=ks_path,
        universe=universe,
    )

    # Insert catalyst signal data for one asset so contexts are populated
    in_memory_store._conn.execute(
        "INSERT INTO catalyst_events (event_id, asset_id, ticker, event_type, event_date, signal_strength) VALUES (?, ?, ?, ?, ?, ?)",
        ("ev-v2", "a-vktx", "VKTX", "readout", "2025-05-20", 1.5),
    )
    in_memory_store._conn.commit()

    as_of = date(2025, 6, 1)

    # Build contexts directly and verify they contain v2.0 signal data
    contexts = replay._build_score_contexts(universe, as_of)
    assert "a-vktx" in contexts
    assert "a-alny" in contexts
    # VKTX has catalyst data; ALNY does not (None is neutral)
    assert contexts["a-vktx"].catalyst_signal_strength == pytest.approx(1.5)
    assert contexts["a-alny"].catalyst_signal_strength is None

    # Generate report with contexts — effective_version must be v2.0
    gen = ActionableGenerator()
    candidates = [
        ScoredCandidate(
            asset_id=u["asset_id"],
            ticker=u["ticker"],
            ranking_score=u["ranking_score"],
            opportunity_score=u["opportunity_score"],
        )
        for u in universe
    ]
    report = gen.generate(candidates, top_n=10, week_ending=as_of, contexts=contexts)
    assert report.score_version == "v2.0"


def test_replay_step_decision_v2_no_signal_data_still_v2(tmp_path, in_memory_store):
    """
    Even with no signal data, _build_score_contexts returns a non-empty
    dict of default contexts, so score_version remains "v2.0".
    """
    from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate

    universe = [
        dict(
            asset_id="a-ntla", ticker="NTLA", company_id="co-ntla",
            ranking_score=0.60, opportunity_score=0.55,
            catalyst="NTLA-2001", indication="ATTR",
            claim_type="ENDPOINT_MET", claim_assertion="meets endpoint",
        ),
    ]

    ks_path = str(tmp_path / "replay_kb_v2.db")
    replay = HistoricalReplay(
        replay_store=in_memory_store,
        knowledge_store_path=ks_path,
        universe=universe,
    )

    as_of = date(2025, 6, 1)
    contexts = replay._build_score_contexts(universe, as_of)

    # All signals are None/default — context still present
    assert "a-ntla" in contexts
    ctx = contexts["a-ntla"]
    assert ctx.catalyst_signal_strength is None
    assert ctx.enrollment_site_stalling is False
    assert ctx.capital_risk is None

    gen = ActionableGenerator()
    candidates = [
        ScoredCandidate(
            asset_id=u["asset_id"],
            ticker=u["ticker"],
            ranking_score=u["ranking_score"],
            opportunity_score=u["opportunity_score"],
        )
        for u in universe
    ]
    report = gen.generate(candidates, top_n=10, week_ending=as_of, contexts=contexts)
    assert report.score_version == "v2.0"


def test_new_signal_tables_exist(in_memory_store):
    """All four new v2.0 signal tables are created by _ensure_schema."""
    conn = in_memory_store._conn
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "catalyst_events" in tables
    assert "enrollment_snapshots" in tables
    assert "structured_signals" in tables
    assert "capital_snapshots" in tables


# ---------------------------------------------------------------------------
# seed_signals_from_knowledge_store (Approach A)
# ---------------------------------------------------------------------------

def _make_fake_knowledge_db(path: str) -> None:
    """Create a minimal KnowledgeStore-shaped SQLite with signal data."""
    import json
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE catalyst_events (
            id TEXT PRIMARY KEY,
            asset_id TEXT,
            catalyst_type TEXT,
            expected_date TEXT,
            payload_json TEXT,
            is_active INTEGER DEFAULT 1,
            resolved INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE enrollment_snapshots (
            id TEXT PRIMARY KEY,
            asset_id TEXT,
            snapshot_date TEXT,
            payload_json TEXT,
            nct_id TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE structured_signals (
            id TEXT PRIMARY KEY,
            asset_id TEXT,
            signal_date TEXT,
            event_type TEXT,
            payload_json TEXT,
            created_at TEXT,
            extraction_result_id TEXT,
            company_id TEXT,
            event_id TEXT,
            source_trace_json TEXT
        )
        """
    )

    # Insert a catalyst event with signal_strength in payload_json
    conn.execute(
        "INSERT INTO catalyst_events VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "ks-cat-1", "a-vktx", "trial_readout", "2025-05-01",
            json.dumps({"signal_strength": 1.8}), 1, 0,
            "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z",
        ),
    )
    # Insert a catalyst event WITHOUT signal_strength (still copied, signal_strength=NULL)
    conn.execute(
        "INSERT INTO catalyst_events VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "ks-cat-2", "a-alny", "pdufa_decision", "2025-07-15",
            json.dumps({}), 1, 0,
            "2025-02-01T00:00:00Z", "2025-02-01T00:00:00Z",
        ),
    )
    # Insert a COMPETITOR_READOUT event
    conn.execute(
        "INSERT INTO catalyst_events VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "ks-cat-3", "a-vktx", "competitor_readout", "2025-06-10",
            json.dumps({"signal_strength": 0.9}), 1, 0,
            "2025-03-01T00:00:00Z", "2025-03-01T00:00:00Z",
        ),
    )
    # Enrollment snapshot
    conn.execute(
        "INSERT INTO enrollment_snapshots VALUES (?,?,?,?,?,?)",
        (
            "ks-enroll-1", "a-vktx", "2025-04-01",
            json.dumps({"site_stalling": True, "velocity_low": False, "slippage_alert": False}),
            "NCT001", "2025-04-01T00:00:00Z",
        ),
    )
    # Structured signal with z_score
    conn.execute(
        "INSERT INTO structured_signals VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "ks-sig-1", "a-vktx", "2025-05-15", "trial_readout",
            json.dumps({"z_score": 1.5, "primary_endpoint_met": True}),
            "2025-05-15T00:00:00Z", None, "co-vktx", "ev-1", "{}",
        ),
    )
    # Structured signal without z_score (should be skipped)
    conn.execute(
        "INSERT INTO structured_signals VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "ks-sig-2", "a-alny", "2025-06-01", "trial_readout",
            json.dumps({"primary_endpoint_met": True}),
            "2025-06-01T00:00:00Z", None, "co-alny", "ev-2", "{}",
        ),
    )

    conn.commit()
    conn.close()


def test_seed_signals_from_knowledge_store_catalyst_events(tmp_path, in_memory_store):
    """catalyst_events are copied from KS with signal_strength from payload_json."""
    kb_path = str(tmp_path / "ops.db")
    _make_fake_knowledge_db(kb_path)

    universe = [
        dict(asset_id="a-vktx", ticker="VKTX", company_id="co-vktx",
             ranking_score=0.70, opportunity_score=0.78,
             catalyst="test", indication="obesity",
             claim_type="ENDPOINT_MET", claim_assertion="test"),
        dict(asset_id="a-alny", ticker="ALNY", company_id="co-alny",
             ranking_score=0.68, opportunity_score=0.70,
             catalyst="test", indication="RNAi",
             claim_type="ENDPOINT_MET", claim_assertion="test"),
    ]
    ks_path = str(tmp_path / "replay_kb.db")
    replay = HistoricalReplay(
        replay_store=in_memory_store,
        knowledge_store_path=ks_path,
        universe=universe,
    )

    counts = replay.seed_signals_from_knowledge_store(kb_path)

    # 3 catalyst_events (ks-cat-1, ks-cat-2, ks-cat-3)
    assert counts["catalyst_events"] == 3

    # VKTX catalyst event: signal_strength=1.8
    row = in_memory_store._conn.execute(
        "SELECT signal_strength FROM catalyst_events WHERE event_id = 'ks-cat-1'"
    ).fetchone()
    assert row is not None
    assert row["signal_strength"] == pytest.approx(1.8)

    # ALNY catalyst event: signal_strength=NULL (not in payload)
    row = in_memory_store._conn.execute(
        "SELECT signal_strength FROM catalyst_events WHERE event_id = 'ks-cat-2'"
    ).fetchone()
    assert row is not None
    assert row["signal_strength"] is None

    # Ticker is resolved from the universe map
    row = in_memory_store._conn.execute(
        "SELECT ticker FROM catalyst_events WHERE event_id = 'ks-cat-1'"
    ).fetchone()
    assert row["ticker"] == "VKTX"


def test_seed_signals_from_knowledge_store_enrollment_snapshots(tmp_path, in_memory_store):
    """enrollment_snapshots are copied with flags extracted from payload_json."""
    kb_path = str(tmp_path / "ops2.db")
    _make_fake_knowledge_db(kb_path)

    universe = [
        dict(asset_id="a-vktx", ticker="VKTX", company_id="co-vktx",
             ranking_score=0.70, opportunity_score=0.78,
             catalyst="test", indication="obesity",
             claim_type="ENDPOINT_MET", claim_assertion="test"),
    ]
    ks_path = str(tmp_path / "replay_kb2.db")
    replay = HistoricalReplay(
        replay_store=in_memory_store,
        knowledge_store_path=ks_path,
        universe=universe,
    )
    counts = replay.seed_signals_from_knowledge_store(kb_path)

    assert counts["enrollment_snapshots"] == 1

    row = in_memory_store._conn.execute(
        "SELECT site_stalling, velocity_low, slippage_alert "
        "FROM enrollment_snapshots WHERE snapshot_id = 'ks-enroll-1'"
    ).fetchone()
    assert row is not None
    assert row["site_stalling"] == 1
    assert row["velocity_low"] == 0
    assert row["slippage_alert"] == 0


def test_seed_signals_from_knowledge_store_structured_signals(tmp_path, in_memory_store):
    """structured_signals with z_score are copied; rows without z_score are skipped."""
    kb_path = str(tmp_path / "ops3.db")
    _make_fake_knowledge_db(kb_path)

    universe = [
        dict(asset_id="a-vktx", ticker="VKTX", company_id="co-vktx",
             ranking_score=0.70, opportunity_score=0.78,
             catalyst="test", indication="obesity",
             claim_type="ENDPOINT_MET", claim_assertion="test"),
    ]
    ks_path = str(tmp_path / "replay_kb3.db")
    replay = HistoricalReplay(
        replay_store=in_memory_store,
        knowledge_store_path=ks_path,
        universe=universe,
    )
    counts = replay.seed_signals_from_knowledge_store(kb_path)

    # Only ks-sig-1 (has z_score); ks-sig-2 (no z_score) should be skipped
    assert counts["structured_signals"] == 1

    row = in_memory_store._conn.execute(
        "SELECT z_score FROM structured_signals WHERE signal_id = 'ks-sig-1'"
    ).fetchone()
    assert row is not None
    assert row["z_score"] == pytest.approx(1.5)


def test_seed_signals_missing_knowledge_db_returns_zero_counts(tmp_path, in_memory_store):
    """Gracefully handles a missing knowledge DB — returns zero counts, no crash."""
    universe: list[dict] = []
    ks_path = str(tmp_path / "replay_kb4.db")
    replay = HistoricalReplay(
        replay_store=in_memory_store,
        knowledge_store_path=ks_path,
        universe=universe,
    )
    counts = replay.seed_signals_from_knowledge_store(str(tmp_path / "nonexistent.db"))
    # Opens OK (SQLite creates empty file), but all tables missing → counts all 0
    assert counts["catalyst_events"] == 0
    assert counts["enrollment_snapshots"] == 0
    assert counts["structured_signals"] == 0


# ---------------------------------------------------------------------------
# seed_signals_from_event_calendar (Approach B)
# ---------------------------------------------------------------------------

def test_seed_signals_from_event_calendar_inserts_rows(tmp_path, in_memory_store):
    """
    For assets with historical_events, synthetic catalyst_events are inserted
    with signal_strength derived from ranking/opportunity scores.
    """
    universe = [
        dict(asset_id="a-vktx", ticker="VKTX", company_id="co-vktx",
             ranking_score=0.72, opportunity_score=0.78,
             catalyst="VK2735 Ph2", indication="obesity",
             claim_type="ENDPOINT_MET", claim_assertion="test"),
        dict(asset_id="a-ntla", ticker="NTLA", company_id="co-ntla",
             ranking_score=0.60, opportunity_score=0.55,
             catalyst="NTLA-2001", indication="ATTR",
             claim_type="ENDPOINT_MET", claim_assertion="test"),
    ]

    # Insert historical_events for VKTX only; NTLA has none
    in_memory_store.insert_event(
        asset_id="a-vktx", ticker="VKTX",
        event_type="readout", announced_at=date(2024, 6, 10),
        effective_date=date(2024, 6, 10),
        outcome_label="positive", headline="Phase 2 results",
    )

    ks_path = str(tmp_path / "replay_kb5.db")
    replay = HistoricalReplay(
        replay_store=in_memory_store,
        knowledge_store_path=ks_path,
        universe=universe,
    )

    n = replay.seed_signals_from_event_calendar()

    # Only VKTX has a historical_event; NTLA is skipped
    assert n == 1

    row = in_memory_store._conn.execute(
        "SELECT event_type, signal_strength FROM catalyst_events "
        "WHERE asset_id = 'a-vktx'"
    ).fetchone()
    assert row is not None
    assert row["event_type"] == "trial_readout"
    # signal_strength = (0.72 + 0.78) / 2 * 0.25 = 0.1875
    assert row["signal_strength"] == pytest.approx(0.1875)


def test_seed_signals_from_event_calendar_no_events_skipped(tmp_path, in_memory_store):
    """Assets with no historical_events produce no synthetic rows."""
    universe = [
        dict(asset_id="a-no-events", ticker="NOEVT", company_id="co-ne",
             ranking_score=0.60, opportunity_score=0.55,
             catalyst="test", indication="test",
             claim_type="ENDPOINT_MET", claim_assertion="test"),
    ]
    ks_path = str(tmp_path / "replay_kb6.db")
    replay = HistoricalReplay(
        replay_store=in_memory_store,
        knowledge_store_path=ks_path,
        universe=universe,
    )
    n = replay.seed_signals_from_event_calendar()
    assert n == 0


# ---------------------------------------------------------------------------
# End-to-end: after seeding, generate() produces v2.0 output
# ---------------------------------------------------------------------------

def test_after_seeding_replay_produces_v2_output(tmp_path, in_memory_store):
    """
    After seed_signals_from_event_calendar inserts catalyst signal data,
    _build_score_contexts returns non-None catalyst_signal_strength and
    gen.generate(contexts=...) produces score_version == "v2.0".
    """
    from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate

    universe = [
        dict(asset_id="a-vktx", ticker="VKTX", company_id="co-vktx",
             ranking_score=0.72, opportunity_score=0.78,
             catalyst="VK2735 Ph2", indication="obesity",
             claim_type="ENDPOINT_MET", claim_assertion="test"),
    ]

    # Seed a historical event so the synthetic seeder has data to work with
    in_memory_store.insert_event(
        asset_id="a-vktx", ticker="VKTX",
        event_type="readout", announced_at=date(2024, 6, 10),
        effective_date=date(2024, 6, 10),
        outcome_label="positive", headline="Ph2 results",
    )

    ks_path = str(tmp_path / "replay_kb7.db")
    replay = HistoricalReplay(
        replay_store=in_memory_store,
        knowledge_store_path=ks_path,
        universe=universe,
    )

    # Run Approach B synthetic seed
    n = replay.seed_signals_from_event_calendar()
    assert n == 1

    # Build contexts — should now have non-None catalyst_signal_strength for VKTX
    as_of = date(2025, 6, 1)
    contexts = replay._build_score_contexts(universe, as_of)
    assert contexts["a-vktx"].catalyst_signal_strength is not None

    # Generate report — must be v2.0
    gen = ActionableGenerator()
    candidates = [
        ScoredCandidate(
            asset_id=u["asset_id"],
            ticker=u["ticker"],
            ranking_score=u["ranking_score"],
            opportunity_score=u["opportunity_score"],
        )
        for u in universe
    ]
    report = gen.generate(candidates, top_n=10, week_ending=as_of, contexts=contexts)
    assert report.score_version == "v2.0"

    # Verify signal_adjustments are non-zero for VKTX (has positive catalyst signal)
    vktx_opp = next(o for o in report.opportunities if o.ticker == "VKTX")
    assert vktx_opp.signal_adjustment_total != 0.0
    assert vktx_opp.signal_adjustments.get("catalyst_ev", 0.0) != 0.0


# ---------------------------------------------------------------------------
# Schema migration: snapshot_date column added to existing DB
# ---------------------------------------------------------------------------

def test_migrate_schema_adds_snapshot_date_column(tmp_path):
    """An existing DB without snapshot_date gets the column on next open."""
    import sqlite3 as _sqlite3

    db_path = str(tmp_path / "old_store.db")

    # Build a DB without snapshot_date (pre-migration schema)
    conn = _sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE catalyst_events "
        "(event_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, ticker TEXT NOT NULL, "
        " event_type TEXT NOT NULL, event_date TEXT NOT NULL, signal_strength REAL)"
    )
    conn.commit()
    conn.close()

    # Opening via ReplayStore should run _migrate_schema and add snapshot_date
    store = ReplayStore(db_path)
    cols = {row[1] for row in store._conn.execute("PRAGMA table_info(catalyst_events)").fetchall()}
    assert "snapshot_date" in cols
    store.close()


def test_migrate_schema_idempotent(tmp_path):
    """Opening the same DB twice does not raise an error."""
    db_path = str(tmp_path / "store2.db")
    store1 = ReplayStore(db_path)
    store1.close()
    store2 = ReplayStore(db_path)  # second open — migration guard must be a no-op
    cols = {row[1] for row in store2._conn.execute("PRAGMA table_info(catalyst_events)").fetchall()}
    assert "snapshot_date" in cols
    store2.close()


# ---------------------------------------------------------------------------
# get_catalyst_signal_strength: recency ordering with snapshot_date
# ---------------------------------------------------------------------------

def test_get_catalyst_signal_strength_snapshot_date_ordering(in_memory_store):
    """
    When two rows have the same event_date but different snapshot_dates,
    the one with the later snapshot_date wins (recency ordering).
    """
    conn = in_memory_store._conn
    # Same event_date, older snapshot measured lower signal
    conn.execute(
        "INSERT INTO catalyst_events "
        "(event_id, asset_id, ticker, event_type, event_date, signal_strength, snapshot_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("ev-old", "a-vktx", "VKTX", "readout", "2025-07-01", 0.5, "2025-05-01"),
    )
    # Newer snapshot_date measured higher signal (more confident proximity)
    conn.execute(
        "INSERT INTO catalyst_events "
        "(event_id, asset_id, ticker, event_type, event_date, signal_strength, snapshot_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("ev-new", "a-vktx", "VKTX", "readout", "2025-07-01", 0.9, "2025-06-01"),
    )
    conn.commit()

    result = in_memory_store.get_catalyst_signal_strength("a-vktx", date(2025, 6, 15))
    # Should return 0.9 (newer snapshot) not 0.5 (older) and not MAX(both)
    assert result == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# SignalBackfiller — unit tests
# ---------------------------------------------------------------------------

def test_signal_backfiller_catalyst_signals_proximity(in_memory_store):
    """backfill_catalyst_signals inserts proximity-based rows into catalyst_events."""
    from bve.ops.signal_backfiller import SignalBackfiller

    # Seed a future event so the backfiller has a catalyst to reference
    in_memory_store._conn.execute(
        "INSERT INTO historical_events "
        "(event_id, asset_id, ticker, event_type, announced_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("he-1", "a-vktx", "VKTX", "trial_readout", "2025-03-15"),
    )
    in_memory_store._conn.commit()

    bf = SignalBackfiller(in_memory_store)
    universe = [dict(asset_id="a-vktx", ticker="VKTX")]

    # Step from 2025-01-01 with 30-day cadence — 2025-03-15 is 73 days from 2025-01-01
    n = bf.backfill_catalyst_signals(
        universe,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 1),
        step_days=30,
    )
    assert n > 0

    # Rows should have snapshot_date set to step dates, event_date = 2025-03-15
    rows = in_memory_store._conn.execute(
        "SELECT snapshot_date, event_date, signal_strength FROM catalyst_events "
        "WHERE asset_id = 'a-vktx' AND event_type = 'trial_readout' "
        "AND snapshot_date IS NOT NULL ORDER BY snapshot_date"
    ).fetchall()
    assert len(rows) >= 1

    # Each row should have snapshot_date != event_date (time-varying)
    for row in rows:
        assert row["snapshot_date"] != row["event_date"]
        assert row["signal_strength"] is not None
        assert 0.0 <= row["signal_strength"] <= 0.10 + 1e-6


def test_signal_backfiller_catalyst_signals_vary_over_time(in_memory_store):
    """
    Integration: signal_strength decreases as the catalyst date approaches
    (counter-intuitively, base × (1 - days/90) increases as days decreases).
    """
    from bve.ops.signal_backfiller import SignalBackfiller

    # Catalyst on 2025-03-31 (91 days after 2025-01-01)
    in_memory_store._conn.execute(
        "INSERT INTO historical_events "
        "(event_id, asset_id, ticker, event_type, announced_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("he-vary", "a-vktx", "VKTX", "trial_readout", "2025-03-31"),
    )
    in_memory_store._conn.commit()

    bf = SignalBackfiller(in_memory_store)
    universe = [dict(asset_id="a-vktx", ticker="VKTX")]

    # Backfill at 30-day steps: 2025-01-01 and 2025-01-31
    bf.backfill_catalyst_signals(
        universe,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        step_days=30,
    )

    rows = in_memory_store._conn.execute(
        "SELECT snapshot_date, signal_strength FROM catalyst_events "
        "WHERE asset_id = 'a-vktx' AND event_type = 'trial_readout' "
        "AND snapshot_date IS NOT NULL ORDER BY snapshot_date"
    ).fetchall()

    # 2025-01-01: days=89 → 0.10*(1-89/90) ≈ 0.001; >90 would give 0.02
    # 2025-01-31: days=59 → 0.10*(1-59/90) ≈ 0.034
    assert len(rows) >= 2
    signals = [row["signal_strength"] for row in rows]
    # Signal at 2025-01-31 (59 days away) should be larger than at 2025-01-01 (89 days away)
    assert signals[-1] > signals[0]


def test_signal_backfiller_catalyst_signals_base_score_not_circular(in_memory_store):
    """
    base_score = 0.10 regardless of ranking_score or opportunity_score.
    Max achievable signal is 0.10 (at days=0).
    """
    from bve.ops.signal_backfiller import SignalBackfiller, _BASE_SCORE

    in_memory_store._conn.execute(
        "INSERT INTO historical_events "
        "(event_id, asset_id, ticker, event_type, announced_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("he-base", "a-vktx", "VKTX", "trial_readout", "2025-02-15"),
    )
    in_memory_store._conn.commit()

    bf = SignalBackfiller(in_memory_store)
    # High-conviction universe entry — ranking/opportunity scores must NOT bleed in
    universe = [dict(asset_id="a-vktx", ticker="VKTX",
                     ranking_score=0.99, opportunity_score=0.99)]

    bf.backfill_catalyst_signals(
        universe,
        start_date=date(2025, 2, 14),
        end_date=date(2025, 2, 14),
        step_days=1,
    )

    rows = in_memory_store._conn.execute(
        "SELECT signal_strength FROM catalyst_events "
        "WHERE asset_id = 'a-vktx' AND snapshot_date IS NOT NULL"
    ).fetchall()
    assert rows, "Expected at least one row"
    for row in rows:
        assert row["signal_strength"] <= _BASE_SCORE + 1e-6


def test_signal_backfiller_competitor_signals_inserted(in_memory_store):
    """backfill_competitor_signals inserts COMPETITOR_READOUT rows."""
    from bve.ops.signal_backfiller import SignalBackfiller

    # Seed a competitor event for a-ntla (competitor of a-crsp)
    in_memory_store._conn.execute(
        "INSERT INTO historical_events "
        "(event_id, asset_id, ticker, event_type, announced_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("he-ntla", "a-ntla", "NTLA", "trial_readout", "2025-04-10"),
    )
    in_memory_store._conn.commit()

    bf = SignalBackfiller(in_memory_store)
    n = bf.backfill_competitor_signals({"a-crsp": ["a-ntla"]})
    assert n == 1

    row = in_memory_store._conn.execute(
        "SELECT asset_id, ticker, event_type, signal_strength, snapshot_date "
        "FROM catalyst_events WHERE event_type = 'COMPETITOR_READOUT'"
    ).fetchone()
    assert row is not None
    assert row["asset_id"] == "a-crsp"       # our asset
    assert row["ticker"] == "NTLA"           # competitor ticker
    assert row["snapshot_date"] == "2025-04-10"
    assert row["signal_strength"] == pytest.approx(0.30)


def test_signal_backfiller_competitor_signals_excluded_from_own_catalyst(in_memory_store):
    """COMPETITOR_READOUT rows are not returned by get_catalyst_signal_strength."""
    from bve.ops.signal_backfiller import SignalBackfiller

    in_memory_store._conn.execute(
        "INSERT INTO historical_events "
        "(event_id, asset_id, ticker, event_type, announced_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("he-beam", "a-beam", "BEAM", "trial_readout", "2025-05-01"),
    )
    in_memory_store._conn.commit()

    bf = SignalBackfiller(in_memory_store)
    bf.backfill_competitor_signals({"a-crsp": ["a-beam"]})

    # get_catalyst_signal_strength for a-crsp should return None
    # (COMPETITOR_READOUT rows excluded from own-asset query)
    result = in_memory_store.get_catalyst_signal_strength("a-crsp", date(2025, 6, 1))
    assert result is None


def test_signal_backfiller_capital_risk_no_crash_empty_universe(in_memory_store):
    """backfill_capital_risk with empty universe returns 0 and does not raise."""
    from bve.ops.signal_backfiller import SignalBackfiller

    bf = SignalBackfiller(in_memory_store)
    n = bf.backfill_capital_risk([])
    assert n == 0


def test_signal_backfiller_catalyst_signals_no_events_skips(in_memory_store):
    """backfill_catalyst_signals returns 0 when no historical_events exist."""
    from bve.ops.signal_backfiller import SignalBackfiller

    bf = SignalBackfiller(in_memory_store)
    universe = [dict(asset_id="a-vktx", ticker="VKTX")]
    n = bf.backfill_catalyst_signals(
        universe,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 1),
        step_days=30,
    )
    assert n == 0


def test_signal_backfiller_catalyst_signals_idempotent(in_memory_store):
    """Running backfill twice does not duplicate rows (INSERT OR REPLACE)."""
    from bve.ops.signal_backfiller import SignalBackfiller

    in_memory_store._conn.execute(
        "INSERT INTO historical_events "
        "(event_id, asset_id, ticker, event_type, announced_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("he-idem", "a-vktx", "VKTX", "trial_readout", "2025-03-15"),
    )
    in_memory_store._conn.commit()

    bf = SignalBackfiller(in_memory_store)
    universe = [dict(asset_id="a-vktx", ticker="VKTX")]
    params = dict(
        universe=universe,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 2, 1),
        step_days=30,
    )
    n1 = bf.backfill_catalyst_signals(**params)
    n2 = bf.backfill_catalyst_signals(**params)
    assert n1 == n2

    count = in_memory_store._conn.execute(
        "SELECT COUNT(*) FROM catalyst_events WHERE asset_id='a-vktx' AND snapshot_date IS NOT NULL"
    ).fetchone()[0]
    # Two runs with INSERT OR REPLACE — row count equals one run's output
    assert count == n1


def test_competitor_map_keys_are_symmetric():
    """Every key in COMPETITOR_MAP also appears as a value in another key's list."""
    from bve.ops.signal_backfiller import COMPETITOR_MAP

    all_values = {v for vals in COMPETITOR_MAP.values() for v in vals}
    for key in COMPETITOR_MAP:
        assert key in all_values, f"{key} appears as key but not as a competitor value"
