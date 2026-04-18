"""Tests for the Phase 3 monitoring pipeline: news_monitor, event_router, model_trigger_engine, alert_dispatcher."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from bve.pipeline.news_monitor import ClassifiedEvent, NewsMonitor, RawFeedEvent
from bve.pipeline.event_router import AssetEventBinding, EventRouter, RoutedEvent
from bve.pipeline.model_trigger_engine import ModelTriggerEngine
from bve.pipeline.alert_dispatcher import AlertDispatcher, MonitoringAlertPayload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw(
    headline: str,
    source: str = "press_release",
    asset_id: str | None = None,
    ticker: str | None = None,
) -> RawFeedEvent:
    return RawFeedEvent(
        source=source,
        asset_id=asset_id,
        ticker=ticker,
        headline=headline,
        published_at=datetime.now(timezone.utc),
    )


def _make_alert(
    ticker: str = "EXMP",
    asset_id: str = "asset-1",
    alert_type: str = "thesis_broken",
    severity: str = "high",
) -> MonitoringAlertPayload:
    return MonitoringAlertPayload(
        asset_id=asset_id,
        ticker=ticker,
        alert_type=alert_type,
        severity=severity,
        headline="Test alert",
        detail="Some detail about the alert",
    )


UNIVERSE = [
    {"asset_id": "asset-1", "ticker": "EXMP", "indication": "oncology"},
    {"asset_id": "asset-2", "ticker": "DRUG", "indication": "oncology"},
    {"asset_id": "asset-3", "ticker": "BIOX", "indication": "rare_disease"},
]


# ---------------------------------------------------------------------------
# NewsMonitor tests
# ---------------------------------------------------------------------------

class TestNewsMonitorClassify:
    def test_trial_update_event_type_and_materiality(self):
        monitor = NewsMonitor()
        event = _make_raw("Company announces positive Phase 3 trial results for lead drug")
        classified = monitor.classify(event)
        assert classified.event_type == "trial_update"
        assert classified.materiality_score >= 0.8

    def test_financing_event_type_and_materiality(self):
        monitor = NewsMonitor()
        event = _make_raw("Company completes $200M financing offering")
        classified = monitor.classify(event)
        assert classified.event_type == "financing"
        assert 0.5 <= classified.materiality_score <= 0.75

    def test_fda_event_gets_high_materiality(self):
        monitor = NewsMonitor()
        event = _make_raw("FDA grants approval for novel oncology therapy")
        classified = monitor.classify(event)
        assert classified.event_type == "fda_action"
        assert classified.materiality_score >= 0.85

    def test_duplicate_detection_same_headline(self):
        monitor = NewsMonitor()
        event1 = _make_raw("Company announces partnership deal with BigPharma")
        event2 = _make_raw("Company announces partnership deal with BigPharma")
        c1 = monitor.classify(event1)
        c2 = monitor.classify(event2)
        assert not c1.is_duplicate
        assert c2.is_duplicate

    def test_safety_event_type_and_materiality(self):
        monitor = NewsMonitor()
        event = _make_raw("Trial halted due to adverse safety signals in patients")
        classified = monitor.classify(event)
        assert classified.event_type == "safety"
        assert classified.materiality_score >= 0.8

    def test_partnership_event_type(self):
        monitor = NewsMonitor()
        event = _make_raw("Company enters collaboration agreement with Roche")
        classified = monitor.classify(event)
        assert classified.event_type == "partnership"
        assert classified.materiality_score >= 0.6

    def test_default_event_type_for_unrecognized(self):
        monitor = NewsMonitor()
        event = _make_raw("Company updates investor relations website")
        classified = monitor.classify(event)
        assert classified.event_type == "other"
        assert classified.materiality_score == pytest.approx(0.3)

    def test_dedupe_key_is_deterministic(self):
        monitor = NewsMonitor()
        event = _make_raw("Phase 2 interim data shows promising efficacy")
        c1 = monitor.classify(event)
        monitor.reset_seen()
        c2 = monitor.classify(event)
        assert c1.dedupe_key == c2.dedupe_key

    def test_classified_event_carries_asset_id_and_ticker(self):
        monitor = NewsMonitor()
        event = _make_raw("FDA NDA filing accepted", asset_id="asset-99", ticker="TICK")
        classified = monitor.classify(event)
        assert classified.asset_id == "asset-99"
        assert classified.ticker == "TICK"


class TestNewsMonitorBatch:
    def test_classify_batch_deduplication_within_batch(self):
        monitor = NewsMonitor()
        events = [
            _make_raw("Phase 3 results announced"),
            _make_raw("Phase 3 results announced"),
            _make_raw("Phase 3 results announced"),
        ]
        results = monitor.classify_batch(events)
        assert len(results) == 3
        duplicates = [r for r in results if r.is_duplicate]
        assert len(duplicates) == 2

    def test_classify_batch_returns_all(self):
        monitor = NewsMonitor()
        events = [_make_raw(f"Headline {i}") for i in range(5)]
        results = monitor.classify_batch(events)
        assert len(results) == 5

    def test_reset_seen_clears_history(self):
        monitor = NewsMonitor()
        event = _make_raw("FDA approval for compound X")
        c1 = monitor.classify(event)
        assert not c1.is_duplicate
        monitor.reset_seen()
        c2 = monitor.classify(event)
        assert not c2.is_duplicate


# ---------------------------------------------------------------------------
# EventRouter tests
# ---------------------------------------------------------------------------

class TestEventRouter:
    def _classified(
        self,
        event_type: str = "trial_update",
        materiality: float = 0.9,
        asset_id: str | None = None,
        ticker: str | None = None,
    ) -> ClassifiedEvent:
        raw = _make_raw("Phase 3 trial update", asset_id=asset_id, ticker=ticker)
        import hashlib
        key = hashlib.sha256(f"press_release:{raw.headline[:80]}".encode()).hexdigest()
        return ClassifiedEvent(
            event_id=raw.event_id,
            source=raw.source,
            asset_id=asset_id,
            ticker=ticker,
            event_type=event_type,
            materiality_score=materiality,
            headline=raw.headline,
            dedupe_key=key,
        )

    def test_direct_asset_id_binding(self):
        router = EventRouter()
        event = self._classified(asset_id="asset-1")
        routed = router.route(event, UNIVERSE)
        assert any(b.asset_id == "asset-1" and b.bind_reason == "direct_mention" for b in routed.bindings)

    def test_ticker_binding_from_universe(self):
        router = EventRouter()
        event = self._classified(ticker="DRUG")
        routed = router.route(event, UNIVERSE)
        assert any(b.asset_id == "asset-2" and b.bind_reason == "direct_mention" for b in routed.bindings)

    def test_competitor_event_binds_same_indication(self):
        router = EventRouter()
        event = self._classified(event_type="competitor_event", materiality=0.8)
        routed = router.route(event, UNIVERSE)
        oncology_assets = {"asset-1", "asset-2"}
        bound_ids = {b.asset_id for b in routed.bindings}
        assert oncology_assets.issubset(bound_ids)

    def test_modules_to_recompute_correct_for_trial_update(self):
        router = EventRouter()
        event = self._classified(event_type="trial_update", asset_id="asset-1")
        routed = router.route(event, UNIVERSE)
        assert "pos" in routed.modules_to_recompute
        assert "catalyst_tree" in routed.modules_to_recompute
        assert "variant_thesis" in routed.modules_to_recompute
        assert "science" in routed.modules_to_recompute

    def test_no_universe_match_empty_bindings(self):
        router = EventRouter()
        event = self._classified(asset_id="unknown-asset")
        routed = router.route(event, UNIVERSE)
        # asset_id "unknown-asset" is not in universe — no match
        assert all(b.asset_id != "unknown-asset" for b in routed.bindings)

    def test_routed_event_is_valid_model(self):
        router = EventRouter()
        event = self._classified(asset_id="asset-3")
        routed = router.route(event, UNIVERSE)
        assert isinstance(routed, RoutedEvent)
        assert routed.classified_event.event_id == event.event_id

    def test_fda_action_modules(self):
        router = EventRouter()
        event = self._classified(event_type="fda_action", asset_id="asset-1")
        routed = router.route(event, UNIVERSE)
        assert "pos" in routed.modules_to_recompute
        assert "market_expectations" in routed.modules_to_recompute
        assert "catalyst_tree" in routed.modules_to_recompute

    def test_other_event_type_empty_modules(self):
        router = EventRouter()
        event = self._classified(event_type="other", asset_id="asset-1")
        routed = router.route(event, UNIVERSE)
        assert routed.modules_to_recompute == []


# ---------------------------------------------------------------------------
# ModelTriggerEngine tests
# ---------------------------------------------------------------------------

class TestModelTriggerEngine:
    def _make_routed(
        self,
        asset_id: str = "asset-1",
        ticker: str = "EXMP",
        event_type: str = "trial_update",
        materiality: float = 0.9,
        modules: list[str] | None = None,
    ) -> RoutedEvent:
        import hashlib
        headline = "Phase 3 results positive"
        key = hashlib.sha256(f"press_release:{headline[:80]}".encode()).hexdigest()
        classified = ClassifiedEvent(
            event_id="evt-001",
            source="press_release",
            asset_id=asset_id,
            ticker=ticker,
            event_type=event_type,
            materiality_score=materiality,
            headline=headline,
            dedupe_key=key,
        )
        binding = AssetEventBinding(
            event_id="evt-001",
            asset_id=asset_id,
            ticker=ticker,
            bind_reason="direct_mention",
            materiality_score=materiality,
        )
        if modules is None:
            modules = ["pos", "catalyst_tree", "variant_thesis", "science"]
        return RoutedEvent(
            classified_event=classified,
            bindings=[binding],
            modules_to_recompute=modules,
        )

    def test_one_routed_event_creates_correct_jobs(self):
        engine = ModelTriggerEngine()
        routed = self._make_routed()
        queue = engine.build_queue([routed])
        assert queue.total_count == 4
        modules = {j.module for j in queue.jobs}
        assert modules == {"pos", "catalyst_tree", "variant_thesis", "science"}

    def test_deduplication_across_events_same_asset_module(self):
        engine = ModelTriggerEngine()
        r1 = self._make_routed(materiality=0.9, modules=["pos"])
        r2 = self._make_routed(materiality=0.6, modules=["pos"])
        queue = engine.build_queue([r1, r2])
        pos_jobs = [j for j in queue.jobs if j.module == "pos" and j.asset_id == "asset-1"]
        assert len(pos_jobs) == 1

    def test_priority_high_for_materiality_08_plus(self):
        engine = ModelTriggerEngine()
        routed = self._make_routed(materiality=0.9, modules=["pos"])
        queue = engine.build_queue([routed])
        assert queue.jobs[0].priority == "high"
        assert queue.high_priority_count == 1

    def test_priority_medium_for_materiality_05_to_08(self):
        engine = ModelTriggerEngine()
        routed = self._make_routed(materiality=0.6, modules=["pos"])
        queue = engine.build_queue([routed])
        assert queue.jobs[0].priority == "medium"

    def test_priority_low_for_low_materiality(self):
        engine = ModelTriggerEngine()
        routed = self._make_routed(materiality=0.3, modules=["pos"])
        queue = engine.build_queue([routed])
        assert queue.jobs[0].priority == "low"

    def test_dedup_keeps_highest_priority(self):
        engine = ModelTriggerEngine()
        r_low = self._make_routed(materiality=0.3, modules=["pos"])
        r_high = self._make_routed(materiality=0.9, modules=["pos"])
        queue = engine.build_queue([r_low, r_high])
        pos_jobs = [j for j in queue.jobs if j.module == "pos"]
        assert len(pos_jobs) == 1
        assert pos_jobs[0].priority == "high"

    def test_asset_ids_affected_populated(self):
        engine = ModelTriggerEngine()
        r1 = self._make_routed(asset_id="asset-1", ticker="EXMP", modules=["pos"])
        r2 = self._make_routed(asset_id="asset-2", ticker="DRUG", modules=["pos"])
        queue = engine.build_queue([r1, r2])
        assert set(queue.asset_ids_affected) == {"asset-1", "asset-2"}

    def test_empty_routed_events_returns_empty_queue(self):
        engine = ModelTriggerEngine()
        queue = engine.build_queue([])
        assert queue.total_count == 0
        assert queue.jobs == []


# ---------------------------------------------------------------------------
# AlertDispatcher tests
# ---------------------------------------------------------------------------

class TestAlertDispatcher:
    def test_log_channel_dispatches_successfully(self, caplog):
        import logging
        dispatcher = AlertDispatcher(channel="log")
        alert = _make_alert()
        with caplog.at_level(logging.INFO, logger="bve.pipeline.alert_dispatcher"):
            result = dispatcher.dispatch(alert)
        assert result.dispatched
        assert result.channel == "log"
        assert result.error is None

    def test_file_channel_writes_to_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AlertDispatcher(channel="file", output_dir=tmpdir)
            alert = _make_alert()
            result = dispatcher.dispatch(alert)
            assert result.dispatched
            alerts_file = os.path.join(tmpdir, "alerts.jsonl")
            assert os.path.exists(alerts_file)
            with open(alerts_file, "r") as fh:
                line = fh.readline()
            data = json.loads(line)
            assert data["alert_id"] == alert.alert_id
            assert data["ticker"] == alert.ticker

    def test_dispatch_batch_multiple_alerts(self):
        dispatcher = AlertDispatcher(channel="log")
        alerts = [_make_alert(ticker=f"TK{i}") for i in range(3)]
        results = dispatcher.dispatch_batch(alerts)
        assert len(results) == 3
        assert all(r.dispatched for r in results)

    def test_dispatched_alerts_returns_history(self):
        dispatcher = AlertDispatcher(channel="log")
        alert1 = _make_alert(ticker="AAA")
        alert2 = _make_alert(ticker="BBB")
        dispatcher.dispatch(alert1)
        dispatcher.dispatch(alert2)
        history = dispatcher.dispatched_alerts()
        assert len(history) == 2
        tickers = {r.alert.ticker for r in history}
        assert tickers == {"AAA", "BBB"}

    def test_unknown_channel_marks_not_dispatched(self):
        dispatcher = AlertDispatcher(channel="slack_future")
        alert = _make_alert()
        result = dispatcher.dispatch(alert)
        assert not result.dispatched
        assert result.error is not None

    def test_file_channel_without_output_dir_fails_gracefully(self):
        dispatcher = AlertDispatcher(channel="file", output_dir=None)
        alert = _make_alert()
        result = dispatcher.dispatch(alert)
        assert not result.dispatched
        assert result.error is not None

    def test_file_channel_appends_multiple_alerts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AlertDispatcher(channel="file", output_dir=tmpdir)
            for i in range(3):
                dispatcher.dispatch(_make_alert(ticker=f"TK{i}"))
            alerts_file = os.path.join(tmpdir, "alerts.jsonl")
            with open(alerts_file, "r") as fh:
                lines = [ln for ln in fh.readlines() if ln.strip()]
            assert len(lines) == 3
