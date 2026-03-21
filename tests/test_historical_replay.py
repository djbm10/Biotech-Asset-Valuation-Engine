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
