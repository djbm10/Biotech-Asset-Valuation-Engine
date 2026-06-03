"""
Tests for the Step 11 monitoring + recompute pipeline:
  bve.pipelines.news_monitor
  bve.pipelines.event_router
  bve.pipelines.model_trigger_engine
  bve.pipelines.alert_dispatcher
  bve.pipelines.scheduler
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest

from bve.ingestion.raw_event import RawEvent
from bve.evidence.classifier import EventType
from bve.evidence.materiality import MaterialityTier

from bve.pipelines.news_monitor import (
    MonitorConfig,
    NewsMonitor,
    SourceHealth,
    SourceStatus,
)
from bve.pipelines.event_router import (
    EntityRegistry,
    EventRouter,
    RoutedEvent,
)
from bve.pipelines.model_trigger_engine import (
    EVENT_MODULE_MAP,
    ModelTriggerEngine,
    RecomputeModule,
    RecomputeRequest,
)
from bve.pipelines.alert_dispatcher import (
    Alert,
    AlertChannel,
    AlertDispatcher,
    AlertRule,
    AlertSeverity,
    check_operator,
)
from bve.pipelines.scheduler import (
    JobResult,
    JobStatus,
    ScheduledJob,
    Scheduler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_event(
    source: str = "sec_edgar",
    record_type: str = "10_k",
    payload: dict | None = None,
    entity_ids: list[str] | None = None,
) -> RawEvent:
    return RawEvent(
        source=source,
        record_type=record_type,
        source_url=f"https://example.com/{source}/{record_type}",
        payload=payload or {"title": "quarterly earnings revenue financial results"},
        entity_ids=entity_ids or [],
    )


def _make_fda_event(entity_ids: list[str] | None = None) -> RawEvent:
    return RawEvent(
        source="openfda",
        record_type="drug_approval",
        source_url="https://fda.gov/approvals/123",
        payload={"title": "FDA grants approval for drug X", "summary": "approved nda bla"},
        entity_ids=entity_ids or [],
    )


def _make_monitor(sources: list[str] | None = None, max_failures: int = 3) -> NewsMonitor:
    cfg = MonitorConfig(sources=sources or ["sec", "fda"], max_consecutive_failures=max_failures)
    return NewsMonitor(cfg)


def _make_registry_with_assets() -> EntityRegistry:
    reg = EntityRegistry()
    reg.register("asset-1", ["EXMP", "EXM"], ["NCT001"])
    reg.register("asset-2", ["DRUG"], ["NCT002"])
    reg.register("asset-3", ["BIOX"], [])
    return reg


def _make_alert_rule(
    rule_id: str = "rule-1",
    metric: str = "pos_delta",
    threshold: float = 0.1,
    operator: str = "gt",
    severity: AlertSeverity = AlertSeverity.HIGH,
) -> AlertRule:
    return AlertRule(
        rule_id=rule_id,
        name=f"Rule {rule_id}",
        metric=metric,
        threshold=threshold,
        operator=operator,
        severity=severity,
        channels=[AlertChannel.LOG],
    )


# ---------------------------------------------------------------------------
# TestNewsMonitor
# ---------------------------------------------------------------------------

class TestNewsMonitor:
    def test_register_fetcher_and_poll_returns_new_event_count(self):
        monitor = _make_monitor(["sec"])
        events = [_make_raw_event()]
        monitor.register_fetcher("sec", lambda: events)
        result = monitor.poll("sec")
        assert result["sec"] == 1

    def test_deduplication_same_event_processed_once(self):
        monitor = _make_monitor(["sec"])
        event = _make_raw_event()
        monitor.register_fetcher("sec", lambda: [event, event])
        result = monitor.poll("sec")
        assert result["sec"] == 1  # only 1 new event despite 2 identical

    def test_deduplication_across_polls(self):
        monitor = _make_monitor(["sec"])
        event = _make_raw_event()
        monitor.register_fetcher("sec", lambda: [event])
        monitor.poll("sec")
        result2 = monitor.poll("sec")
        assert result2["sec"] == 0  # already seen

    def test_handler_called_for_each_new_event(self):
        monitor = _make_monitor(["sec"])
        received: list[RawEvent] = []
        monitor.register_handler(received.append)
        events = [_make_raw_event(record_type="10_k"), _make_raw_event(record_type="8_k")]
        monitor.register_fetcher("sec", lambda: events)
        monitor.poll("sec")
        assert len(received) == 2

    def test_multiple_handlers_all_called(self):
        monitor = _make_monitor(["sec"])
        log1: list[RawEvent] = []
        log2: list[RawEvent] = []
        monitor.register_handler(log1.append)
        monitor.register_handler(log2.append)
        monitor.register_fetcher("sec", lambda: [_make_raw_event()])
        monitor.poll("sec")
        assert len(log1) == 1
        assert len(log2) == 1

    def test_handler_not_called_for_duplicate(self):
        monitor = _make_monitor(["sec"])
        received: list[RawEvent] = []
        monitor.register_handler(received.append)
        event = _make_raw_event()
        monitor.register_fetcher("sec", lambda: [event])
        monitor.poll("sec")
        monitor.poll("sec")
        assert len(received) == 1  # handler not called second time

    def test_failed_fetch_marks_source_degraded(self):
        monitor = _make_monitor(["fda"], max_failures=3)

        def bad_fetch() -> list[RawEvent]:
            raise RuntimeError("network timeout")

        monitor.register_fetcher("fda", bad_fetch)
        monitor.poll("fda")
        health = monitor.source_health("fda")
        assert health.status == SourceStatus.DEGRADED
        assert health.consecutive_failures == 1

    def test_consecutive_failures_incremented(self):
        monitor = _make_monitor(["fda"], max_failures=5)

        def bad_fetch() -> list[RawEvent]:
            raise RuntimeError("error")

        monitor.register_fetcher("fda", bad_fetch)
        monitor.poll("fda")
        monitor.poll("fda")
        monitor.poll("fda")
        health = monitor.source_health("fda")
        assert health.consecutive_failures == 3

    def test_source_marked_down_after_max_failures(self):
        monitor = _make_monitor(["fda"], max_failures=3)

        def bad_fetch() -> list[RawEvent]:
            raise RuntimeError("down")

        monitor.register_fetcher("fda", bad_fetch)
        for _ in range(3):
            monitor.poll("fda")
        health = monitor.source_health("fda")
        assert health.status == SourceStatus.DOWN

    def test_poll_specific_source_only_polls_that_source(self):
        monitor = _make_monitor(["sec", "fda"])
        sec_calls = []
        fda_calls = []
        monitor.register_fetcher("sec", lambda: sec_calls.append(1) or [])
        monitor.register_fetcher("fda", lambda: fda_calls.append(1) or [])
        monitor.poll("sec")
        assert len(sec_calls) == 1
        assert len(fda_calls) == 0

    def test_poll_none_polls_all_sources(self):
        monitor = _make_monitor(["sec", "fda"])
        calls: dict[str, int] = {"sec": 0, "fda": 0}
        monitor.register_fetcher("sec", lambda: (calls.__setitem__("sec", calls["sec"] + 1) or []))
        monitor.register_fetcher("fda", lambda: (calls.__setitem__("fda", calls["fda"] + 1) or []))
        monitor.poll()
        assert calls["sec"] == 1
        assert calls["fda"] == 1

    def test_seen_count_increments(self):
        monitor = _make_monitor(["sec"])
        events = [_make_raw_event(record_type=str(i)) for i in range(5)]
        monitor.register_fetcher("sec", lambda: events)
        monitor.poll("sec")
        assert monitor.seen_count() == 5

    def test_reset_seen_clears_dedup_set(self):
        monitor = _make_monitor(["sec"])
        event = _make_raw_event()
        monitor.register_fetcher("sec", lambda: [event])
        monitor.poll("sec")
        assert monitor.seen_count() == 1
        monitor.reset_seen()
        assert monitor.seen_count() == 0

    def test_reset_seen_allows_reprocessing(self):
        monitor = _make_monitor(["sec"])
        received: list[RawEvent] = []
        monitor.register_handler(received.append)
        event = _make_raw_event()
        monitor.register_fetcher("sec", lambda: [event])
        monitor.poll("sec")
        monitor.reset_seen()
        monitor.poll("sec")
        assert len(received) == 2  # processed twice after reset

    def test_source_health_returns_source_health(self):
        monitor = _make_monitor(["sec"])
        monitor.register_fetcher("sec", lambda: [])
        monitor.poll("sec")
        health = monitor.source_health("sec")
        assert isinstance(health, SourceHealth)
        assert health.source_name == "sec"

    def test_all_health_returns_all_sources(self):
        monitor = _make_monitor(["sec", "fda"])
        monitor.register_fetcher("sec", lambda: [])
        monitor.register_fetcher("fda", lambda: [])
        monitor.poll()
        health = monitor.all_health()
        assert "sec" in health
        assert "fda" in health

    def test_source_starts_healthy(self):
        monitor = _make_monitor(["sec"])
        health = monitor.source_health("sec")
        assert health.status == SourceStatus.HEALTHY

    def test_degraded_after_first_failure(self):
        monitor = _make_monitor(["sec"], max_failures=3)

        def bad_fetch() -> list[RawEvent]:
            raise RuntimeError("err")

        monitor.register_fetcher("sec", bad_fetch)
        monitor.poll("sec")
        health = monitor.source_health("sec")
        assert health.status == SourceStatus.DEGRADED

    def test_success_resets_consecutive_failures(self):
        monitor = _make_monitor(["sec"], max_failures=5)
        fail = True

        def toggle_fetch() -> list[RawEvent]:
            nonlocal fail
            if fail:
                raise RuntimeError("err")
            return []

        monitor.register_fetcher("sec", toggle_fetch)
        monitor.poll("sec")  # fail
        assert monitor.source_health("sec").consecutive_failures == 1
        fail = False
        monitor.poll("sec")  # success
        assert monitor.source_health("sec").consecutive_failures == 0
        assert monitor.source_health("sec").status == SourceStatus.HEALTHY

    def test_last_error_recorded_on_failure(self):
        monitor = _make_monitor(["sec"])

        def bad_fetch() -> list[RawEvent]:
            raise RuntimeError("specific error message")

        monitor.register_fetcher("sec", bad_fetch)
        monitor.poll("sec")
        health = monitor.source_health("sec")
        assert health.last_error == "specific error message"


# ---------------------------------------------------------------------------
# TestEventRouter
# ---------------------------------------------------------------------------

class TestEventRouter:
    def test_entity_registry_register_and_resolve_ticker(self):
        reg = EntityRegistry()
        reg.register("asset-1", ["EXMP"])
        assert reg.resolve_ticker("EXMP") == "asset-1"

    def test_entity_registry_ticker_case_insensitive(self):
        reg = EntityRegistry()
        reg.register("asset-1", ["EXMP"])
        assert reg.resolve_ticker("exmp") == "asset-1"
        assert reg.resolve_ticker("Exmp") == "asset-1"

    def test_entity_registry_resolve_nct(self):
        reg = EntityRegistry()
        reg.register("asset-1", [], ["NCT001"])
        assert reg.resolve_nct("NCT001") == "asset-1"

    def test_entity_registry_resolve_event_uses_entity_ids_first(self):
        reg = _make_registry_with_assets()
        event = _make_raw_event(
            payload={"ticker": "DRUG"},  # would resolve to asset-2
            entity_ids=["asset-1"],      # should take precedence
        )
        result = reg.resolve_event(event)
        assert result == ["asset-1"]

    def test_entity_registry_resolve_event_falls_back_to_ticker(self):
        reg = _make_registry_with_assets()
        event = _make_raw_event(
            payload={"ticker": "DRUG"},
            entity_ids=[],
        )
        result = reg.resolve_event(event)
        assert "asset-2" in result

    def test_entity_registry_resolve_event_falls_back_to_nct_id(self):
        reg = _make_registry_with_assets()
        event = _make_raw_event(
            payload={"nct_id": "NCT001"},
            entity_ids=[],
        )
        result = reg.resolve_event(event)
        assert "asset-1" in result

    def test_entity_registry_resolve_event_returns_empty_for_unknown(self):
        reg = EntityRegistry()
        event = _make_raw_event(payload={"ticker": "UNKNOWN_XYZ"})
        result = reg.resolve_event(event)
        assert result == []

    def test_event_router_route_produces_routed_event(self):
        reg = _make_registry_with_assets()
        router = EventRouter(reg)
        event = _make_fda_event(entity_ids=["asset-1"])
        routed = router.route(event)
        assert isinstance(routed, RoutedEvent)

    def test_routing_confidence_from_classifier(self):
        reg = _make_registry_with_assets()
        router = EventRouter(reg)
        event = _make_fda_event()
        routed = router.route(event)
        # openfda + drug_approval gives confidence 0.95
        assert routed.routing_confidence == pytest.approx(0.95)

    def test_route_batch_skips_minimal_tier(self):
        reg = EntityRegistry()
        router = EventRouter(reg)
        # market_data source → UNKNOWN event type → MINIMAL materiality (score 0.10 with low conf)
        event = RawEvent(
            source="market_data",
            record_type="price",
            source_url="https://example.com/price",
            payload={"close": 42.0},
        )
        results = router.route_batch([event])
        # UNKNOWN with confidence 0.0 → score 0.10 - 0.10 = 0.0 → MINIMAL
        assert all(r.materiality_tier != MaterialityTier.MINIMAL for r in results)

    def test_filter_by_tier_returns_only_at_or_above_min(self):
        reg = _make_registry_with_assets()
        router = EventRouter(reg)
        fda_event = _make_fda_event(entity_ids=["asset-1"])
        earnings_event = _make_raw_event(
            source="sec_edgar",
            record_type="10_k",
            payload={"title": "quarterly earnings revenue"},
            entity_ids=["asset-1"],
        )
        routed = [router.route(fda_event), router.route(earnings_event)]
        high_only = router.filter_by_tier(routed, MaterialityTier.HIGH)
        assert all(r.materiality_tier == MaterialityTier.HIGH for r in high_only)

    def test_event_type_from_classifier(self):
        reg = _make_registry_with_assets()
        router = EventRouter(reg)
        event = _make_fda_event()
        routed = router.route(event)
        assert routed.event_type == EventType.FDA_ACTION

    def test_materiality_score_populated(self):
        reg = _make_registry_with_assets()
        router = EventRouter(reg)
        event = _make_fda_event(entity_ids=["asset-1"])
        routed = router.route(event)
        assert 0.0 <= routed.materiality_score <= 1.0

    def test_affected_asset_ids_resolved(self):
        reg = _make_registry_with_assets()
        router = EventRouter(reg)
        event = _make_fda_event(entity_ids=["asset-1"])
        routed = router.route(event)
        assert "asset-1" in routed.affected_asset_ids

    def test_route_batch_returns_multiple_events(self):
        reg = _make_registry_with_assets()
        router = EventRouter(reg)
        events = [
            _make_fda_event(entity_ids=["asset-1"]),
            _make_fda_event(entity_ids=["asset-2"]),
        ]
        results = router.route_batch(events)
        assert len(results) == 2

    def test_filter_by_tier_medium_includes_high_and_medium(self):
        reg = _make_registry_with_assets()
        router = EventRouter(reg)
        fda_event = _make_fda_event(entity_ids=["asset-1"])
        earnings_event = _make_raw_event(
            source="sec_edgar",
            record_type="10_k",
            payload={"title": "quarterly earnings revenue financial"},
            entity_ids=["asset-1"],
        )
        routed = [router.route(fda_event), router.route(earnings_event)]
        medium_and_above = router.filter_by_tier(routed, MaterialityTier.MEDIUM)
        tiers = {r.materiality_tier for r in medium_and_above}
        assert tiers.issubset({MaterialityTier.HIGH, MaterialityTier.MEDIUM})


# ---------------------------------------------------------------------------
# TestModelTriggerEngine
# ---------------------------------------------------------------------------

class TestModelTriggerEngine:
    def _make_routed_event(
        self,
        event_type: EventType = EventType.CATALYST_UPDATE,
        materiality_tier: MaterialityTier = MaterialityTier.HIGH,
        asset_ids: list[str] | None = None,
    ) -> RoutedEvent:
        raw = _make_raw_event(entity_ids=asset_ids or ["asset-1"])
        return RoutedEvent(
            raw_event=raw,
            event_type=event_type,
            materiality_tier=materiality_tier,
            materiality_score=0.85 if materiality_tier == MaterialityTier.HIGH else 0.10,
            affected_asset_ids=asset_ids or ["asset-1"],
            routing_confidence=0.80,
        )

    def test_catalyst_update_routes_to_correct_modules(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.CATALYST_UPDATE)
        requests = engine.process(event)
        assert len(requests) == 1
        modules = set(requests[0].modules)
        assert RecomputeModule.PROBABILITY_STACK.value in modules
        assert RecomputeModule.MARKET_EXPECTATIONS.value in modules
        assert RecomputeModule.RECOMMENDATION.value in modules

    def test_fda_action_routes_to_four_modules_including_dossier(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.FDA_ACTION)
        requests = engine.process(event)
        modules = set(requests[0].modules)
        assert RecomputeModule.DOSSIER.value in modules
        assert len(modules) == 4

    def test_financing_routes_to_financing_risk(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.FINANCING)
        requests = engine.process(event)
        modules = set(requests[0].modules)
        assert RecomputeModule.FINANCING_RISK.value in modules

    def test_competitor_event_routes_to_competition_graph(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.COMPETITOR_EVENT)
        requests = engine.process(event)
        modules = set(requests[0].modules)
        assert RecomputeModule.COMPETITION_GRAPH.value in modules

    def test_unknown_event_type_produces_no_requests(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.UNKNOWN)
        requests = engine.process(event)
        assert requests == []

    def test_minimal_materiality_produces_no_requests(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(
            EventType.CATALYST_UPDATE,
            materiality_tier=MaterialityTier.MINIMAL,
        )
        requests = engine.process(event)
        assert requests == []

    def test_dedup_same_asset_id_and_module_not_added_twice(self):
        engine = ModelTriggerEngine()
        event1 = self._make_routed_event(EventType.CATALYST_UPDATE, asset_ids=["asset-1"])
        event2 = self._make_routed_event(EventType.CATALYST_UPDATE, asset_ids=["asset-1"])
        engine.process(event1)
        new_requests = engine.process(event2)
        # Second call should produce no new requests (all modules already pending)
        assert len(new_requests) == 0

    def test_pending_returns_all_unprocessed_requests(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.CATALYST_UPDATE, asset_ids=["asset-1"])
        engine.process(event)
        pending = engine.pending()
        assert len(pending) >= 1
        assert all(not r.processed for r in pending)

    def test_pending_filters_by_asset_id(self):
        engine = ModelTriggerEngine()
        engine.process(self._make_routed_event(EventType.FDA_ACTION, asset_ids=["asset-1"]))
        engine.process(self._make_routed_event(EventType.FINANCING, asset_ids=["asset-2"]))
        pending_1 = engine.pending("asset-1")
        pending_2 = engine.pending("asset-2")
        assert all(r.asset_id == "asset-1" for r in pending_1)
        assert all(r.asset_id == "asset-2" for r in pending_2)

    def test_mark_processed_changes_processed_flag(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.CATALYST_UPDATE)
        requests = engine.process(event)
        req_id = requests[0].request_id
        engine.mark_processed(req_id)
        processed = [r for r in engine.pending() if r.request_id == req_id]
        assert len(processed) == 0  # no longer in pending

    def test_pending_count_counts_only_unprocessed(self):
        engine = ModelTriggerEngine()
        event1 = self._make_routed_event(EventType.CATALYST_UPDATE, asset_ids=["asset-1"])
        event2 = self._make_routed_event(EventType.FINANCING, asset_ids=["asset-2"])
        reqs1 = engine.process(event1)
        engine.process(event2)
        count_before = engine.pending_count()
        engine.mark_processed(reqs1[0].request_id)
        count_after = engine.pending_count()
        assert count_after == count_before - 1

    def test_clear_processed_removes_processed_requests(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.CATALYST_UPDATE)
        requests = engine.process(event)
        engine.mark_processed(requests[0].request_id)
        engine.clear_processed()
        # All remaining requests should be unprocessed
        assert all(not r.processed for r in engine.pending())

    def test_multiple_asset_ids_one_event_separate_requests(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(
            EventType.CATALYST_UPDATE,
            asset_ids=["asset-1", "asset-2"],
        )
        requests = engine.process(event)
        asset_ids = {r.asset_id for r in requests}
        assert "asset-1" in asset_ids
        assert "asset-2" in asset_ids

    def test_request_id_is_unique_uuid(self):
        engine = ModelTriggerEngine()
        event1 = self._make_routed_event(EventType.CATALYST_UPDATE, asset_ids=["asset-1"])
        event2 = self._make_routed_event(EventType.FDA_ACTION, asset_ids=["asset-2"])
        reqs1 = engine.process(event1)
        reqs2 = engine.process(event2)
        ids = [r.request_id for r in reqs1 + reqs2]
        # All IDs are valid UUIDs and unique
        assert len(set(ids)) == len(ids)
        for rid in ids:
            uuid.UUID(rid)  # raises if invalid

    def test_trial_change_routes_to_science_score(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.TRIAL_CHANGE)
        requests = engine.process(event)
        modules = set(requests[0].modules)
        assert RecomputeModule.SCIENCE_SCORE.value in modules

    def test_partnership_ma_routes_to_dossier(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.PARTNERSHIP_MA)
        requests = engine.process(event)
        modules = set(requests[0].modules)
        assert RecomputeModule.DOSSIER.value in modules

    def test_earnings_routes_to_financing_risk_and_dossier(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.EARNINGS)
        requests = engine.process(event)
        modules = set(requests[0].modules)
        assert RecomputeModule.FINANCING_RISK.value in modules
        assert RecomputeModule.DOSSIER.value in modules

    def test_management_change_routes_only_to_dossier(self):
        engine = ModelTriggerEngine()
        event = self._make_routed_event(EventType.MANAGEMENT_CHANGE)
        requests = engine.process(event)
        modules = set(requests[0].modules)
        assert modules == {RecomputeModule.DOSSIER.value}


# ---------------------------------------------------------------------------
# TestAlertDispatcher
# ---------------------------------------------------------------------------

class TestAlertDispatcher:
    def test_check_operator_gt_true(self):
        assert check_operator(0.5, "gt", 0.3) is True

    def test_check_operator_gt_false(self):
        assert check_operator(0.1, "gt", 0.3) is False

    def test_check_operator_lt_true(self):
        assert check_operator(0.2, "lt", 0.5) is True

    def test_check_operator_lt_false(self):
        assert check_operator(0.8, "lt", 0.5) is False

    def test_check_operator_gte_equal(self):
        assert check_operator(0.5, "gte", 0.5) is True

    def test_check_operator_lte_equal(self):
        assert check_operator(0.5, "lte", 0.5) is True

    def test_check_operator_eq(self):
        assert check_operator(1.0, "eq", 1.0) is True
        assert check_operator(1.0, "eq", 0.5) is False

    def test_register_rule_and_evaluate_fires_alert_when_threshold_crossed(self):
        dispatcher = AlertDispatcher(cooldown_minutes=60)
        rule = _make_alert_rule(operator="gt", threshold=0.1)
        dispatcher.register_rule(rule)
        alerts = dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        assert len(alerts) == 1
        assert alerts[0].rule_id == "rule-1"

    def test_no_alert_when_threshold_not_crossed(self):
        dispatcher = AlertDispatcher(cooldown_minutes=60)
        rule = _make_alert_rule(operator="gt", threshold=0.9)
        dispatcher.register_rule(rule)
        alerts = dispatcher.evaluate("asset-1", {"pos_delta": 0.1})
        assert len(alerts) == 0

    def test_cooldown_prevents_refiring_within_window(self):
        dispatcher = AlertDispatcher(cooldown_minutes=60)
        rule = _make_alert_rule(operator="gt", threshold=0.1)
        dispatcher.register_rule(rule)
        dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        alerts2 = dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        assert len(alerts2) == 0  # cooldown active

    def test_fires_again_after_cooldown_expires(self):
        dispatcher = AlertDispatcher(cooldown_minutes=0)
        rule = _make_alert_rule(operator="gt", threshold=0.1)
        dispatcher.register_rule(rule)
        dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        # With 0-minute cooldown, should fire again immediately
        alerts2 = dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        assert len(alerts2) == 1

    def test_fired_alerts_filter_by_asset_id(self):
        dispatcher = AlertDispatcher(cooldown_minutes=0)
        rule = _make_alert_rule(operator="gt", threshold=0.1)
        dispatcher.register_rule(rule)
        dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        dispatcher.evaluate("asset-2", {"pos_delta": 0.5})
        alerts_1 = dispatcher.fired_alerts(asset_id="asset-1")
        assert all(a.asset_id == "asset-1" for a in alerts_1)

    def test_fired_alerts_filter_by_severity(self):
        dispatcher = AlertDispatcher(cooldown_minutes=0)
        high_rule = _make_alert_rule("r-high", severity=AlertSeverity.HIGH, operator="gt", threshold=0.1)
        low_rule = _make_alert_rule("r-low", severity=AlertSeverity.LOW, operator="gt", threshold=0.1)
        dispatcher.register_rule(high_rule)
        dispatcher.register_rule(low_rule)
        dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        high_alerts = dispatcher.fired_alerts(severity=AlertSeverity.HIGH)
        assert all(a.severity == AlertSeverity.HIGH for a in high_alerts)

    def test_alert_count_increments(self):
        dispatcher = AlertDispatcher(cooldown_minutes=0)
        rule = _make_alert_rule(operator="gt", threshold=0.1)
        dispatcher.register_rule(rule)
        dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        dispatcher.evaluate("asset-2", {"pos_delta": 0.5})
        assert dispatcher.alert_count() == 2

    def test_clear_alerts_empties_store(self):
        dispatcher = AlertDispatcher(cooldown_minutes=0)
        rule = _make_alert_rule(operator="gt", threshold=0.1)
        dispatcher.register_rule(rule)
        dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        dispatcher.clear_alerts()
        assert dispatcher.alert_count() == 0

    def test_alert_id_is_uuid(self):
        dispatcher = AlertDispatcher(cooldown_minutes=0)
        rule = _make_alert_rule(operator="gt", threshold=0.1)
        dispatcher.register_rule(rule)
        alerts = dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        uuid.UUID(alerts[0].alert_id)  # raises if invalid

    def test_severity_from_rule(self):
        dispatcher = AlertDispatcher(cooldown_minutes=0)
        rule = _make_alert_rule(severity=AlertSeverity.CRITICAL, operator="gt", threshold=0.1)
        dispatcher.register_rule(rule)
        alerts = dispatcher.evaluate("asset-1", {"pos_delta": 0.5})
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_missing_metric_does_not_fire(self):
        dispatcher = AlertDispatcher(cooldown_minutes=0)
        rule = _make_alert_rule(metric="pos_delta", operator="gt", threshold=0.1)
        dispatcher.register_rule(rule)
        alerts = dispatcher.evaluate("asset-1", {"other_metric": 0.9})
        assert len(alerts) == 0

    def test_multiple_rules_can_fire_independently(self):
        dispatcher = AlertDispatcher(cooldown_minutes=0)
        rule1 = _make_alert_rule("r1", metric="pos_delta", operator="gt", threshold=0.1)
        rule2 = _make_alert_rule("r2", metric="financing_distress_tier", operator="gte", threshold=3.0)
        dispatcher.register_rule(rule1)
        dispatcher.register_rule(rule2)
        alerts = dispatcher.evaluate("asset-1", {"pos_delta": 0.5, "financing_distress_tier": 3.0})
        assert len(alerts) == 2


# ---------------------------------------------------------------------------
# TestScheduler
# ---------------------------------------------------------------------------

class TestScheduler:
    def test_job_due_on_first_tick_last_run_none(self):
        scheduler = Scheduler()
        ran = []
        job = ScheduledJob(job_id="j1", name="Test", fn=lambda: ran.append(1), interval_seconds=60)
        scheduler.register(job)
        results = scheduler.tick(now=datetime.now(timezone.utc))
        assert len(results) == 1
        assert results[0].status == JobStatus.COMPLETED
        assert len(ran) == 1

    def test_job_not_due_within_interval(self):
        scheduler = Scheduler()
        ran = []
        now = datetime.now(timezone.utc)
        job = ScheduledJob(
            job_id="j1", name="Test", fn=lambda: ran.append(1),
            interval_seconds=300, last_run=now,
        )
        scheduler.register(job)
        # Tick only 10 seconds later
        results = scheduler.tick(now=now + timedelta(seconds=10))
        assert len(results) == 0
        assert len(ran) == 0

    def test_job_due_after_interval_elapsed(self):
        scheduler = Scheduler()
        ran = []
        now = datetime.now(timezone.utc)
        job = ScheduledJob(
            job_id="j1", name="Test", fn=lambda: ran.append(1),
            interval_seconds=60, last_run=now - timedelta(seconds=61),
        )
        scheduler.register(job)
        results = scheduler.tick(now=now)
        assert len(results) == 1
        assert results[0].status == JobStatus.COMPLETED

    def test_fn_called_on_due_tick(self):
        scheduler = Scheduler()
        ran = []
        job = ScheduledJob(job_id="j1", name="Test", fn=lambda: ran.append(42), interval_seconds=0)
        scheduler.register(job)
        scheduler.tick()
        assert 42 in ran

    def test_exception_caught_marks_failed_status(self):
        scheduler = Scheduler()

        def bad_fn() -> None:
            raise ValueError("job error")

        job = ScheduledJob(job_id="j1", name="BadJob", fn=bad_fn, interval_seconds=0)
        scheduler.register(job)
        results = scheduler.tick()
        assert results[0].status == JobStatus.FAILED
        assert results[0].error == "job error"

    def test_error_count_incremented_on_failure(self):
        scheduler = Scheduler()

        def bad_fn() -> None:
            raise RuntimeError("err")

        job = ScheduledJob(job_id="j1", name="BadJob", fn=bad_fn, interval_seconds=0)
        scheduler.register(job)
        scheduler.tick()
        scheduler.tick()
        assert scheduler.job_status("j1").error_count == 2

    def test_run_count_incremented_on_success(self):
        scheduler = Scheduler()
        job = ScheduledJob(job_id="j1", name="Test", fn=lambda: None, interval_seconds=0)
        scheduler.register(job)
        scheduler.tick()
        scheduler.tick()
        assert scheduler.job_status("j1").run_count == 2

    def test_multiple_jobs_only_due_ones_run(self):
        scheduler = Scheduler()
        now = datetime.now(timezone.utc)
        ran = []
        due_job = ScheduledJob(
            job_id="j1", name="Due", fn=lambda: ran.append("due"),
            interval_seconds=60, last_run=now - timedelta(seconds=120),
        )
        not_due_job = ScheduledJob(
            job_id="j2", name="NotDue", fn=lambda: ran.append("not_due"),
            interval_seconds=300, last_run=now - timedelta(seconds=10),
        )
        scheduler.register(due_job)
        scheduler.register(not_due_job)
        results = scheduler.tick(now=now)
        assert len(results) == 1
        assert "due" in ran
        assert "not_due" not in ran

    def test_reset_job_sets_last_run_none(self):
        scheduler = Scheduler()
        now = datetime.now(timezone.utc)
        job = ScheduledJob(
            job_id="j1", name="Test", fn=lambda: None,
            interval_seconds=300, last_run=now,
        )
        scheduler.register(job)
        scheduler.reset_job("j1")
        assert scheduler.job_status("j1").last_run is None

    def test_reset_job_causes_run_on_next_tick(self):
        scheduler = Scheduler()
        now = datetime.now(timezone.utc)
        ran = []
        job = ScheduledJob(
            job_id="j1", name="Test", fn=lambda: ran.append(1),
            interval_seconds=300, last_run=now,
        )
        scheduler.register(job)
        scheduler.tick(now=now + timedelta(seconds=10))  # not due
        assert len(ran) == 0
        scheduler.reset_job("j1")
        scheduler.tick(now=now + timedelta(seconds=11))  # now due (last_run=None)
        assert len(ran) == 1

    def test_all_jobs_returns_registered_jobs(self):
        scheduler = Scheduler()
        j1 = ScheduledJob(job_id="j1", name="A", fn=lambda: None, interval_seconds=60)
        j2 = ScheduledJob(job_id="j2", name="B", fn=lambda: None, interval_seconds=120)
        scheduler.register(j1)
        scheduler.register(j2)
        all_jobs = scheduler.all_jobs()
        ids = {j.job_id for j in all_jobs}
        assert "j1" in ids
        assert "j2" in ids

    def test_job_result_has_correct_job_id_and_ran_at(self):
        scheduler = Scheduler()
        now = datetime.now(timezone.utc)
        job = ScheduledJob(job_id="j99", name="Test", fn=lambda: None, interval_seconds=0)
        scheduler.register(job)
        results = scheduler.tick(now=now)
        assert results[0].job_id == "j99"
        assert results[0].ran_at == now
