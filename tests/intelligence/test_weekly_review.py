"""Tests for Wave L — Weekly Review Engine."""
from __future__ import annotations

import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.decision_layer import DecisionLayer
from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
from bve.intelligence.weekly_review import (
    FundamentalAccuracy,
    MarketTimingAccuracy,
    SizingQuality,
    ThesisAccuracy,
    WeeklyReviewEngine,
    WeeklyReviewReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY = date(2026, 3, 17)
_START = _TODAY - timedelta(days=7)


def _make_engine(
    *,
    with_decision_layer: bool = False,
    with_thesis_tracker: bool = False,
) -> tuple[WeeklyReviewEngine, KnowledgeStore]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    store = KnowledgeStore(tmp.name)
    dl = DecisionLayer(store) if with_decision_layer else None
    tt = ThesisTracker(store) if with_thesis_tracker else None
    engine = WeeklyReviewEngine(store, decision_layer=dl, thesis_tracker=tt)
    return engine, store


def _insert_forecast(
    store: KnowledgeStore,
    *,
    asset_id: str = "a-1",
    event_type: str = "trial_readout",
    outcome_correct: int = 1,
    actual_return: float = 0.10,
    signal_age_days: int = 5,
    predicted_at_offset_days: int = 0,
) -> str:
    """Insert a resolved forecast_record and return its forecast_id."""
    fid = str(uuid.uuid4())[:8]
    sid = str(uuid.uuid4())[:8]
    signal_date = _TODAY - timedelta(days=signal_age_days + predicted_at_offset_days)
    predicted_at = _TODAY - timedelta(days=predicted_at_offset_days)
    now = datetime.now(timezone.utc).isoformat()
    store._conn.execute(
        """
        INSERT INTO forecast_records
            (forecast_id, signal_id, event_id, asset_id, event_type,
             signal_date, trial_phase, indication, predicted_direction,
             outcome_correct, actual_market_return_t30, resolved,
             predicted_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            f"fc-{fid}",
            f"sig-{sid}",
            f"evt-{fid}",
            asset_id,
            event_type,
            signal_date.isoformat(),
            "phase_3",
            "oncology",
            "up" if outcome_correct else "down",
            outcome_correct,
            actual_return,
            predicted_at.isoformat(),
            now,
        ),
    )
    store._conn.commit()
    return f"fc-{fid}"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schema_creates_weekly_review_table() -> None:
    engine, store = _make_engine()
    try:
        row = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='weekly_review_records'"
        ).fetchone()
        assert row is not None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# run_review — empty store
# ---------------------------------------------------------------------------

def test_run_review_empty_store_returns_report() -> None:
    engine, store = _make_engine()
    try:
        report = engine.run_review(week_ending=_TODAY)
        assert isinstance(report, WeeklyReviewReport)
        assert report.fundamental.n_resolved == 0
        assert report.fundamental.hit_rate is None
    finally:
        store.close()


def test_run_review_stored_and_retrievable() -> None:
    engine, store = _make_engine()
    try:
        engine.run_review(week_ending=_TODAY)
        retrieved = engine.get_stored_report(_TODAY)
        assert retrieved is not None
        assert retrieved.week_ending == _TODAY
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Fundamental accuracy
# ---------------------------------------------------------------------------

def test_fundamental_counts_correct_forecast() -> None:
    engine, store = _make_engine()
    try:
        _insert_forecast(store, outcome_correct=1)
        report = engine.run_review(week_ending=_TODAY)
        assert report.fundamental.n_resolved == 1
        assert report.fundamental.n_correct == 1
        assert report.fundamental.hit_rate == pytest.approx(1.0)
    finally:
        store.close()


def test_fundamental_counts_pos_error() -> None:
    engine, store = _make_engine()
    try:
        _insert_forecast(store, outcome_correct=0, actual_return=-0.15, event_type="trial_readout")
        report = engine.run_review(week_ending=_TODAY)
        assert report.fundamental.n_pos_error == 1
    finally:
        store.close()


def test_fundamental_hit_rate_mixed() -> None:
    engine, store = _make_engine()
    try:
        _insert_forecast(store, asset_id="a1", outcome_correct=1)
        _insert_forecast(store, asset_id="a2", outcome_correct=1)
        _insert_forecast(store, asset_id="a3", outcome_correct=0, actual_return=-0.10)
        report = engine.run_review(week_ending=_TODAY)
        assert report.fundamental.n_resolved == 3
        assert report.fundamental.n_correct == 2
        assert report.fundamental.hit_rate == pytest.approx(2 / 3, abs=0.01)
    finally:
        store.close()


def test_fundamental_confirmed_thesis_requires_thesis_tracker() -> None:
    """Without thesis_tracker, confirmed_thesis is never assigned."""
    engine, store = _make_engine(with_thesis_tracker=False)
    try:
        _insert_forecast(store, outcome_correct=1, actual_return=0.20)
        report = engine.run_review(week_ending=_TODAY)
        # Without thesis tracker, cannot confirm — goes to unclassified or market_drift
        assert report.fundamental.n_confirmed_thesis == 0
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Strict confirmed_thesis
# ---------------------------------------------------------------------------

def test_positive_return_without_thesis_claim_is_market_drift() -> None:
    """Return > 0 but no thesis claim confirmed → market_drift, not confirmed_thesis."""
    engine, store = _make_engine(with_thesis_tracker=True)
    try:
        _insert_forecast(store, outcome_correct=1, actual_return=0.15, event_type="trial_readout")
        # No thesis claims added → thesis_tracker has no confirmed claims
        report = engine.run_review(week_ending=_TODAY)
        assert report.fundamental.n_confirmed_thesis == 0
    finally:
        store.close()


def test_positive_return_with_confirmed_key_claim_is_confirmed_thesis() -> None:
    engine, store = _make_engine(with_thesis_tracker=True)
    try:
        tt = ThesisTracker(store)
        _insert_forecast(store, asset_id="a-1", outcome_correct=1, actual_return=0.20,
                         event_type="trial_readout")
        # Add and confirm an ENDPOINT_MET claim in the same window
        claim = tt.add_claim("a-1", "co-1", ClaimType.ENDPOINT_MET, "primary endpoint met")
        _resolved_at = datetime(_TODAY.year, _TODAY.month, _TODAY.day, tzinfo=timezone.utc).isoformat()
        store._conn.execute(
            "UPDATE thesis_claims SET status='confirmed', resolved_at=? WHERE claim_id=?",
            (_resolved_at, claim.claim_id),
        )
        store._conn.commit()
        report = engine.run_review(week_ending=_TODAY)
        assert report.fundamental.n_confirmed_thesis == 1
    finally:
        store.close()


def test_refuted_key_claim_blocks_confirmed_thesis() -> None:
    """Even with positive return, refuted ENDPOINT_MET blocks confirmed_thesis."""
    engine, store = _make_engine(with_thesis_tracker=True)
    try:
        tt = ThesisTracker(store)
        _insert_forecast(store, asset_id="a-1", outcome_correct=1, actual_return=0.10,
                         event_type="trial_readout")
        # Confirm a minor claim
        c1 = tt.add_claim("a-1", "co-1", ClaimType.MARKET_REACTION_POSITIVE, "mkt positive")
        store._conn.execute(
            "UPDATE thesis_claims SET status='confirmed', resolved_at=? WHERE claim_id=?",
            (datetime.now(timezone.utc).isoformat(), c1.claim_id),
        )
        # Refute the key claim
        c2 = tt.add_claim("a-1", "co-1", ClaimType.ENDPOINT_MET, "primary endpoint")
        store._conn.execute(
            "UPDATE thesis_claims SET status='refuted', resolved_at=? WHERE claim_id=?",
            (datetime.now(timezone.utc).isoformat(), c2.claim_id),
        )
        store._conn.commit()
        report = engine.run_review(week_ending=_TODAY)
        assert report.fundamental.n_confirmed_thesis == 0
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Market timing accuracy
# ---------------------------------------------------------------------------

def test_market_timing_counts_stale_signals() -> None:
    engine, store = _make_engine()
    try:
        _insert_forecast(store, signal_age_days=60)   # stale: 60 > 30d threshold
        _insert_forecast(store, asset_id="a2", signal_age_days=5)   # fresh
        report = engine.run_review(week_ending=_TODAY)
        assert report.market_timing.n_stale_signals == 1
        assert report.market_timing.n_forecasts_checked == 2
    finally:
        store.close()


def test_market_timing_avg_age_computed() -> None:
    engine, store = _make_engine()
    try:
        _insert_forecast(store, signal_age_days=10)
        _insert_forecast(store, asset_id="a2", signal_age_days=20)
        report = engine.run_review(week_ending=_TODAY)
        assert report.market_timing.avg_signal_age_days == pytest.approx(15.0)
    finally:
        store.close()


def test_market_timing_empty() -> None:
    engine, store = _make_engine()
    try:
        report = engine.run_review(week_ending=_TODAY)
        assert report.market_timing.n_forecasts_checked == 0
        assert report.market_timing.pct_stale is None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Thesis accuracy
# ---------------------------------------------------------------------------

def test_thesis_accuracy_empty_without_tracker() -> None:
    engine, store = _make_engine(with_thesis_tracker=False)
    try:
        report = engine.run_review(week_ending=_TODAY)
        assert report.thesis.n_key_claims_confirmed == 0
        assert report.thesis.n_key_claims_refuted == 0
    finally:
        store.close()


def test_thesis_accuracy_counts_key_claims() -> None:
    engine, store = _make_engine(with_thesis_tracker=True)
    try:
        tt = ThesisTracker(store)
        c1 = tt.add_claim("a-1", "co-1", ClaimType.ENDPOINT_MET, "endpoint")
        c2 = tt.add_claim("a-1", "co-1", ClaimType.REGULATORY_PATHWAY, "BTD")
        # Resolve both in window using _TODAY to stay within lookback window
        in_window = datetime(_TODAY.year, _TODAY.month, _TODAY.day, tzinfo=timezone.utc).isoformat()
        store._conn.execute(
            "UPDATE thesis_claims SET status='confirmed', resolved_at=? WHERE claim_id=?",
            (in_window, c1.claim_id),
        )
        store._conn.execute(
            "UPDATE thesis_claims SET status='refuted', resolved_at=? WHERE claim_id=?",
            (in_window, c2.claim_id),
        )
        store._conn.commit()
        report = engine.run_review(week_ending=_TODAY)
        assert report.thesis.n_key_claims_confirmed == 1
        assert report.thesis.n_key_claims_refuted == 1
        assert report.thesis.n_assets_with_refuted_key_claim == 1
    finally:
        store.close()


def test_thesis_accuracy_net_score() -> None:
    engine, store = _make_engine(with_thesis_tracker=True)
    try:
        tt = ThesisTracker(store)
        # Use _TODAY to stay within the review window
        in_window = datetime(_TODAY.year, _TODAY.month, _TODAY.day, tzinfo=timezone.utc).isoformat()
        for i in range(3):
            c = tt.add_claim(f"a-{i}", "co-1", ClaimType.ENDPOINT_MET, f"endpoint {i}")
            store._conn.execute(
                "UPDATE thesis_claims SET status='confirmed', resolved_at=? WHERE claim_id=?",
                (in_window, c.claim_id),
            )
        c_bad = tt.add_claim("a-bad", "co-1", ClaimType.REGULATORY_PATHWAY, "pathway")
        store._conn.execute(
            "UPDATE thesis_claims SET status='refuted', resolved_at=? WHERE claim_id=?",
            (in_window, c_bad.claim_id),
        )
        store._conn.commit()
        report = engine.run_review(week_ending=_TODAY)
        # 3 confirmed, 1 refuted → net = (3-1)/4 = 0.5
        assert report.thesis.net_thesis_score == pytest.approx(0.5)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Sizing quality
# ---------------------------------------------------------------------------

def test_sizing_quality_empty_without_decision_layer() -> None:
    engine, store = _make_engine(with_decision_layer=False)
    try:
        report = engine.run_review(week_ending=_TODAY)
        assert report.sizing.n_decisions_checked == 0
    finally:
        store.close()


def test_sizing_quality_counts_divergence() -> None:
    engine, store = _make_engine(with_decision_layer=True)
    try:
        dl = DecisionLayer(store)
        d1 = dl.record_decision("a1", "buy", recommended_size_pct=0.05)
        d2 = dl.record_decision("a2", "buy", recommended_size_pct=0.05)
        dl.update_execution(d1.decision_id, "buy", 0.05)    # same
        dl.update_execution(d2.decision_id, "hold", 0.08)   # different size + action
        report = engine.run_review(week_ending=_TODAY)
        assert report.sizing.n_recommended_vs_executed_diverged == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# top_miss / top_win
# ---------------------------------------------------------------------------

def test_top_miss_and_win() -> None:
    engine, store = _make_engine()
    try:
        _insert_forecast(store, asset_id="winner", actual_return=0.30, outcome_correct=1)
        _insert_forecast(store, asset_id="loser", actual_return=-0.20, outcome_correct=0)
        report = engine.run_review(week_ending=_TODAY)
        assert report.top_win == "winner"
        assert report.top_miss == "loser"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Stored reports
# ---------------------------------------------------------------------------

def test_get_stored_report_not_found() -> None:
    engine, store = _make_engine()
    try:
        result = engine.get_stored_report(date(2020, 1, 1))
        assert result is None
    finally:
        store.close()


def test_stored_report_overwrites_same_week() -> None:
    engine, store = _make_engine()
    try:
        engine.run_review(week_ending=_TODAY)
        engine.run_review(week_ending=_TODAY)  # second run same week
        # Should not raise; latest stored
        report = engine.get_stored_report(_TODAY)
        assert report is not None
    finally:
        store.close()
