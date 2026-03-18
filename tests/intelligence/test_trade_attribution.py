"""Tests for Wave P2 — TradeAttributionTracker and AttributionReport."""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone

import pytest

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.trade_attribution import (
    AttributionReport,
    TradeAttributionTracker,
    TradeDecision,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_store() -> KnowledgeStore:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return KnowledgeStore(tmp.name)


def _make_tracker() -> tuple[TradeAttributionTracker, KnowledgeStore]:
    store = _make_store()
    tracker = TradeAttributionTracker(store)
    return tracker, store


_TODAY = date(2026, 3, 17)


def _decision(tracker: TradeAttributionTracker, idx: int = 0) -> TradeDecision:
    return tracker.record_decision(
        signal_id=f"sig-{idx}",
        asset_id=f"asset-{idx}",
        event_type="trial_readout",
        signal_date=_TODAY,
        composite_score=0.7 + idx * 0.05,
        mispricing_score=0.20,
        position_weight=0.10,
        sizing_method="half_kelly",
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schema_creates_table() -> None:
    tracker, store = _make_tracker()
    try:
        rows = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_decisions'"
        ).fetchone()
        assert rows is not None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# record_decision
# ---------------------------------------------------------------------------

def test_record_decision_returns_trade_decision() -> None:
    tracker, store = _make_tracker()
    try:
        d = _decision(tracker)
        assert isinstance(d, TradeDecision)
        assert d.signal_id == "sig-0"
        assert d.asset_id == "asset-0"
        assert d.status == "pending"
    finally:
        store.close()


def test_record_decision_idempotent() -> None:
    tracker, store = _make_tracker()
    try:
        d1 = _decision(tracker, idx=0)
        d2 = _decision(tracker, idx=0)
        assert d1.decision_id == d2.decision_id
    finally:
        store.close()


def test_record_decision_persisted() -> None:
    tracker, store = _make_tracker()
    try:
        d = _decision(tracker)
        retrieved = tracker.get_decision(d.decision_id)
        assert retrieved is not None
        assert retrieved.signal_id == d.signal_id
    finally:
        store.close()


def test_record_decision_fields() -> None:
    tracker, store = _make_tracker()
    try:
        d = tracker.record_decision(
            signal_id="sig-x",
            asset_id="asset-x",
            event_type="fda_decision",
            signal_date=_TODAY,
            position_weight=0.15,
            composite_score=0.85,
            mispricing_score=0.35,
            sizing_method="half_kelly",
            analyst_id="analyst-1",
            rationale="Strong Ph3 data above bar",
        )
        assert d.event_type == "fda_decision"
        assert d.position_weight == 0.15
        assert d.analyst_id == "analyst-1"
        assert d.rationale == "Strong Ph3 data above bar"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# record_outcome
# ---------------------------------------------------------------------------

def test_record_outcome_updates_status() -> None:
    tracker, store = _make_tracker()
    try:
        d = _decision(tracker)
        updated = tracker.record_outcome(d.decision_id, realised_return_pct=0.25)
        assert updated is not None
        assert updated.status == "attributed"
        assert updated.realised_return_pct == 0.25
    finally:
        store.close()


def test_record_outcome_attribution_score_uses_weight() -> None:
    tracker, store = _make_tracker()
    try:
        d = _decision(tracker)  # position_weight=0.10
        updated = tracker.record_outcome(d.decision_id, realised_return_pct=0.30)
        assert updated is not None
        # attribution_score = 0.30 × 0.10 = 0.03
        assert abs(updated.attribution_score - 0.03) < 1e-9
    finally:
        store.close()


def test_record_outcome_attribution_score_without_weight() -> None:
    tracker, store = _make_tracker()
    try:
        d = tracker.record_decision(
            signal_id="sig-w",
            asset_id="asset-w",
            event_type="trial_readout",
            signal_date=_TODAY,
            position_weight=None,   # no weight
        )
        updated = tracker.record_outcome(d.decision_id, realised_return_pct=0.20)
        assert updated is not None
        # attribution_score = realised_return_pct when no weight
        assert abs(updated.attribution_score - 0.20) < 1e-9
    finally:
        store.close()


def test_record_outcome_unknown_id_returns_none() -> None:
    tracker, store = _make_tracker()
    try:
        result = tracker.record_outcome("nonexistent-id", 0.10)
        assert result is None
    finally:
        store.close()


def test_record_outcome_persisted() -> None:
    tracker, store = _make_tracker()
    try:
        d = _decision(tracker)
        tracker.record_outcome(d.decision_id, realised_return_pct=0.15)
        retrieved = tracker.get_decision(d.decision_id)
        assert retrieved is not None
        assert retrieved.realised_return_pct == 0.15
        assert retrieved.status == "attributed"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# AttributionReport
# ---------------------------------------------------------------------------

def test_report_empty_store() -> None:
    tracker, store = _make_tracker()
    try:
        report = tracker.report()
        assert report.n_total_decisions == 0
        assert report.n_attributed == 0
        assert report.coverage is None
    finally:
        store.close()


def test_report_pending_only() -> None:
    tracker, store = _make_tracker()
    try:
        _decision(tracker, idx=0)
        _decision(tracker, idx=1)
        report = tracker.report()
        assert report.n_total_decisions == 2
        assert report.n_attributed == 0
        assert report.n_pending == 2
        assert report.avg_realised_return_pct is None
    finally:
        store.close()


def test_report_full_attribution() -> None:
    tracker, store = _make_tracker()
    try:
        d1 = _decision(tracker, idx=0)
        d2 = _decision(tracker, idx=1)
        tracker.record_outcome(d1.decision_id, realised_return_pct=0.30)
        tracker.record_outcome(d2.decision_id, realised_return_pct=-0.10)

        report = tracker.report()
        assert report.n_total_decisions == 2
        assert report.n_attributed == 2
        assert report.coverage == 1.0
        assert abs(report.avg_realised_return_pct - 0.10) < 1e-6
        assert report.hit_rate == 0.5   # 1 win out of 2
    finally:
        store.close()


def test_report_per_signal() -> None:
    tracker, store = _make_tracker()
    try:
        d = _decision(tracker)
        tracker.record_outcome(d.decision_id, realised_return_pct=0.40)
        report = tracker.report()
        assert len(report.per_signal) == 1
        ps = report.per_signal[0]
        assert ps.signal_id == "sig-0"
        assert ps.n_decisions == 1
        assert abs(ps.avg_realised_return_pct - 0.40) < 1e-9
    finally:
        store.close()


def test_report_per_event_type() -> None:
    tracker, store = _make_tracker()
    try:
        d1 = tracker.record_decision(
            signal_id="sig-t1", asset_id="a-1",
            event_type="trial_readout", signal_date=_TODAY,
        )
        d2 = tracker.record_decision(
            signal_id="sig-t2", asset_id="a-2",
            event_type="fda_decision", signal_date=_TODAY,
        )
        tracker.record_outcome(d1.decision_id, realised_return_pct=0.20)
        tracker.record_outcome(d2.decision_id, realised_return_pct=0.50)

        report = tracker.report()
        assert "trial_readout" in report.per_event_type
        assert "fda_decision" in report.per_event_type
        assert abs(report.per_event_type["trial_readout"] - 0.20) < 1e-9
        assert abs(report.per_event_type["fda_decision"] - 0.50) < 1e-9
    finally:
        store.close()


def test_report_total_attribution_score() -> None:
    tracker, store = _make_tracker()
    try:
        d1 = _decision(tracker, idx=0)  # weight=0.10
        d2 = _decision(tracker, idx=1)  # weight=0.10
        tracker.record_outcome(d1.decision_id, realised_return_pct=0.30)
        tracker.record_outcome(d2.decision_id, realised_return_pct=0.20)

        report = tracker.report()
        # total = 0.30×0.10 + 0.20×0.10 = 0.03 + 0.02 = 0.05
        assert abs(report.total_attribution_score - 0.05) < 1e-9
    finally:
        store.close()


# ---------------------------------------------------------------------------
# get_decisions
# ---------------------------------------------------------------------------

def test_get_decisions_filter_by_asset() -> None:
    tracker, store = _make_tracker()
    try:
        _decision(tracker, idx=0)
        _decision(tracker, idx=1)
        results = tracker.get_decisions(asset_id="asset-0")
        assert len(results) == 1
        assert results[0].asset_id == "asset-0"
    finally:
        store.close()


def test_get_decisions_filter_by_status() -> None:
    tracker, store = _make_tracker()
    try:
        d = _decision(tracker)
        _decision(tracker, idx=1)
        tracker.record_outcome(d.decision_id, realised_return_pct=0.10)
        attributed = tracker.get_decisions(status="attributed")
        pending = tracker.get_decisions(status="pending")
        assert len(attributed) == 1
        assert len(pending) == 1
    finally:
        store.close()
