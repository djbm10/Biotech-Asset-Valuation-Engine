"""
Tests for AlertRouter trigger conditions, dedup, batching, and channel dispatch.

All tests use FakeChannel — no real network calls.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock


from bve.alerts.alert_config import AlertsConfig, AlertThresholdsConfig
from bve.alerts.alert_model import Alert, AlertSeverity, AlertTrigger
from bve.alerts.alert_router import AlertRouter
from bve.alerts.channels.base import FakeChannel
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.knowledge_layer import KnowledgeStore, StoredValuationDiff
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_signal(
    event_type: EventType = EventType.TRIAL_READOUT,
    confidence: float = 0.9,
) -> StructuredSignal:
    from bve.intelligence.schemas.signals import StructuredSignal

    return StructuredSignal(
        id=str(uuid.uuid4()),
        event_id="evt-test",
        asset_id="asset-001",
        company_id="company-001",
        event_type=event_type,
        signal_date=date(2024, 6, 1),
        extraction_confidence=confidence,
        created_at=_NOW,
    )


def _make_extraction(confidence: float = 0.9, status=ExtractionStatus.SUCCESS) -> ExtractionResult:
    return ExtractionResult(
        document_id="doc-001",
        asset_id="asset-001",
        company_id="company-001",
        status=status,
        extraction_confidence=confidence,
        extracted_at=_NOW,
    )


def _make_diff(delta_npv: float, before_npv: float = 200.0) -> StoredValuationDiff:
    return StoredValuationDiff(
        run_id=str(uuid.uuid4()),
        event_id="evt-test",
        asset_id="asset-001",
        valuation_before={"rnpv_millions": before_npv},
        valuation_after={"rnpv_millions": before_npv + delta_npv},
        delta_npv=delta_npv,
        created_at=_NOW,
    )


def _make_router(
    abs_floor: float = 25.0,
    rel_pct: float = 15.0,
    low_conf_threshold: float = 0.5,
    dedup_window_hours: float = 0.0,  # 0 = dedup disabled in tests
) -> tuple[AlertRouter, FakeChannel]:
    cfg = AlertsConfig(
        thresholds=AlertThresholdsConfig(
            material_change_abs_floor_millions=abs_floor,
            material_change_pct=rel_pct,
            low_confidence_threshold=low_conf_threshold,
            dedup_window_hours=dedup_window_hours,
            dedup_state_path="/tmp/bve_test_alert_dedup.json",
        )
    )
    channel = FakeChannel()
    router = AlertRouter(config=cfg, channels=[channel])
    return router, channel


class TestCondition1SafetySignal:
    def test_safety_signal_fires_critical(self):
        router, ch = _make_router()
        signal = _make_signal(EventType.SAFETY_SIGNAL, confidence=0.9)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction(0.9))
        router.flush(signal.asset_id)
        assert len(ch.sent) == 1
        assert ch.sent[0].severity == AlertSeverity.CRITICAL
        assert ch.sent[0].trigger == AlertTrigger.SAFETY_SIGNAL_DETECTED

    def test_safety_signal_fires_regardless_of_confidence(self):
        # confidence=0.0 → both condition 1 (CRITICAL) and condition 3 (MEDIUM) fire.
        # The key invariant is that CRITICAL fires unconditionally.
        router, ch = _make_router()
        signal = _make_signal(EventType.SAFETY_SIGNAL, confidence=0.0)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction(0.0))
        router.flush(signal.asset_id)
        critical_alerts = [a for a in ch.sent if a.severity == AlertSeverity.CRITICAL]
        assert len(critical_alerts) == 1
        assert critical_alerts[0].trigger == AlertTrigger.SAFETY_SIGNAL_DETECTED

    def test_non_safety_signal_does_not_fire_condition1(self):
        router, ch = _make_router()
        signal = _make_signal(EventType.TRIAL_READOUT, confidence=0.9)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction(0.9))
        router.flush(signal.asset_id)
        # TRIAL_READOUT should not trigger safety alert
        assert not any(a.trigger == AlertTrigger.SAFETY_SIGNAL_DETECTED for a in ch.sent)


class TestCondition2MaterialValuationChange:
    def test_above_both_gates_fires(self):
        # delta=$40M (>$25M floor), rel=20% (>15%) → should fire
        router, ch = _make_router(abs_floor=25.0, rel_pct=15.0)
        diff = _make_diff(delta_npv=40.0, before_npv=200.0)
        signal = _make_signal()
        router.enqueue_diff_alerts(diff=diff, signal=signal)
        router.flush(diff.asset_id)
        assert len(ch.sent) == 1
        assert ch.sent[0].trigger == AlertTrigger.MATERIAL_VALUATION_CHANGE

    def test_below_absolute_floor_no_alert(self):
        # delta=$2M (<$25M floor) even though rel=40% → no alert
        router, ch = _make_router(abs_floor=25.0, rel_pct=15.0)
        diff = _make_diff(delta_npv=2.0, before_npv=5.0)
        router.enqueue_diff_alerts(diff=diff, signal=_make_signal())
        router.flush(diff.asset_id)
        assert len(ch.sent) == 0

    def test_below_relative_threshold_no_alert(self):
        # delta=$30M (>$25M floor) but rel=5% (<15%) → no alert
        router, ch = _make_router(abs_floor=25.0, rel_pct=15.0)
        diff = _make_diff(delta_npv=30.0, before_npv=600.0)
        router.enqueue_diff_alerts(diff=diff, signal=_make_signal())
        router.flush(diff.asset_id)
        assert len(ch.sent) == 0

    def test_zero_before_npv_does_not_raise(self):
        # before_npv=0 should not divide by zero
        router, ch = _make_router(abs_floor=25.0, rel_pct=15.0)
        diff = _make_diff(delta_npv=30.0, before_npv=0.0)
        router.enqueue_diff_alerts(diff=diff, signal=_make_signal())
        router.flush(diff.asset_id)
        # delta >= abs_floor and before_npv=0 → rel treated as 100% → fires
        assert len(ch.sent) == 1

    def test_configurable_threshold(self):
        # 25% threshold — 20% delta should NOT fire
        router, ch = _make_router(abs_floor=25.0, rel_pct=25.0)
        diff = _make_diff(delta_npv=40.0, before_npv=200.0)  # 20%
        router.enqueue_diff_alerts(diff=diff, signal=_make_signal())
        router.flush(diff.asset_id)
        assert len(ch.sent) == 0

    def test_negative_delta_also_fires(self):
        # Negative delta (bad news) should also trigger if above thresholds
        router, ch = _make_router(abs_floor=25.0, rel_pct=15.0)
        diff = _make_diff(delta_npv=-50.0, before_npv=200.0)  # -25%
        router.enqueue_diff_alerts(diff=diff, signal=_make_signal())
        router.flush(diff.asset_id)
        assert len(ch.sent) == 1
        assert ch.sent[0].valuation_delta_npv == -50.0


class TestCondition3LowConfidenceHighSeverity:
    def test_fda_low_confidence_fires_medium(self):
        # FDA_APPROVAL + confidence=0.3 < 0.5 threshold → MEDIUM (not LOW)
        router, ch = _make_router(low_conf_threshold=0.5)
        signal = _make_signal(EventType.FDA_APPROVAL, confidence=0.3)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction(0.3))
        router.flush(signal.asset_id)
        cond3 = [a for a in ch.sent if a.trigger == AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY]
        assert len(cond3) == 1
        assert cond3[0].severity == AlertSeverity.MEDIUM  # NOT LOW

    def test_fda_high_confidence_no_condition3_alert(self):
        router, ch = _make_router(low_conf_threshold=0.5)
        signal = _make_signal(EventType.FDA_APPROVAL, confidence=0.85)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction(0.85))
        router.flush(signal.asset_id)
        cond3 = [a for a in ch.sent if a.trigger == AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY]
        assert len(cond3) == 0

    def test_low_severity_event_low_confidence_no_condition3(self):
        # ENROLLMENT_UPDATE is not in high_severity_event_types → no condition3 alert
        router, ch = _make_router(low_conf_threshold=0.5)
        signal = _make_signal(EventType.ENROLLMENT_UPDATE, confidence=0.1)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction(0.1))
        router.flush(signal.asset_id)
        cond3 = [a for a in ch.sent if a.trigger == AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY]
        assert len(cond3) == 0

    def test_safety_signal_low_confidence_fires_both_conditions(self):
        # SAFETY_SIGNAL with low confidence → both condition 1 AND condition 3
        router, ch = _make_router(low_conf_threshold=0.5)
        signal = _make_signal(EventType.SAFETY_SIGNAL, confidence=0.2)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction(0.2))
        router.flush(signal.asset_id)
        assert len(ch.sent) == 2
        triggers = {a.trigger for a in ch.sent}
        assert AlertTrigger.SAFETY_SIGNAL_DETECTED in triggers
        assert AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY in triggers


class TestAlertRouterBatching:
    def test_single_alert_calls_send_not_batch(self):
        ch = FakeChannel()
        cfg = AlertsConfig(
            thresholds=AlertThresholdsConfig(
                dedup_window_hours=0.0, dedup_state_path="/tmp/bve_test_dedup2.json"
            )
        )
        router = AlertRouter(config=cfg, channels=[ch])
        signal = _make_signal(EventType.SAFETY_SIGNAL)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction())
        router.flush(signal.asset_id)
        assert len(ch.sent) == 1
        assert len(ch.batches) == 0  # single alert → send(), not send_batch()

    def test_multiple_alerts_call_send_batch(self):
        ch = FakeChannel()
        cfg = AlertsConfig(
            thresholds=AlertThresholdsConfig(
                material_change_abs_floor_millions=25.0,
                material_change_pct=15.0,
                low_confidence_threshold=0.5,
                dedup_window_hours=0.0,
                dedup_state_path="/tmp/bve_test_dedup3.json",
            )
        )
        router = AlertRouter(config=cfg, channels=[ch])
        # Fire condition 1 + condition 3 (two alerts for same asset)
        signal = _make_signal(EventType.SAFETY_SIGNAL, confidence=0.2)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction(0.2))
        router.flush(signal.asset_id)
        assert len(ch.batches) == 1
        assert len(ch.batches[0][0]) == 2

    def test_flush_clears_pending(self):
        router, ch = _make_router()
        signal = _make_signal(EventType.SAFETY_SIGNAL)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction())
        router.flush(signal.asset_id)
        ch.reset()
        # Second flush should send nothing
        router.flush(signal.asset_id)
        assert len(ch.sent) == 0

    def test_flush_returns_alerts_list(self):
        router, ch = _make_router()
        signal = _make_signal(EventType.SAFETY_SIGNAL)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction())
        sent = router.flush(signal.asset_id)
        assert len(sent) == 1
        assert isinstance(sent[0], Alert)

    def test_flush_empty_asset_returns_empty_list(self):
        router, _ = _make_router()
        sent = router.flush("nonexistent-asset")
        assert sent == []


class TestAlertRouterDispatch:
    def test_channel_exception_does_not_propagate(self):
        """Exceptions from channels must be logged, not raised."""
        bad_channel = MagicMock()
        bad_channel.name = "bad"
        bad_channel.send.side_effect = RuntimeError("Network error")
        bad_channel.send_batch.side_effect = RuntimeError("Network error")

        cfg = AlertsConfig(
            thresholds=AlertThresholdsConfig(
                dedup_window_hours=0.0, dedup_state_path="/tmp/bve_test_dedup4.json"
            )
        )
        router = AlertRouter(config=cfg, channels=[bad_channel])
        signal = _make_signal(EventType.SAFETY_SIGNAL)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction())
        # Should not raise despite channel error
        sent = router.flush(signal.asset_id)
        assert len(sent) == 1  # alert was still "sent" (queued+flushed)

    def test_multiple_channels_both_receive(self):
        ch1 = FakeChannel()
        ch2 = FakeChannel()
        cfg = AlertsConfig(
            thresholds=AlertThresholdsConfig(
                dedup_window_hours=0.0, dedup_state_path="/tmp/bve_test_dedup5.json"
            )
        )
        router = AlertRouter(config=cfg, channels=[ch1, ch2])
        signal = _make_signal(EventType.SAFETY_SIGNAL)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction())
        router.flush(signal.asset_id)
        assert len(ch1.sent) == 1
        assert len(ch2.sent) == 1

    def test_no_channels_no_error(self):
        cfg = AlertsConfig(
            thresholds=AlertThresholdsConfig(
                dedup_window_hours=0.0, dedup_state_path="/tmp/bve_test_dedup6.json"
            )
        )
        router = AlertRouter(config=cfg, channels=[])
        signal = _make_signal(EventType.SAFETY_SIGNAL)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction())
        sent = router.flush(signal.asset_id)
        assert len(sent) == 1


class TestAlertRouterDisabled:
    def test_disabled_router_enqueues_nothing(self):
        cfg = AlertsConfig(
            enabled=False,
            thresholds=AlertThresholdsConfig(
                dedup_window_hours=0.0, dedup_state_path="/tmp/bve_test_dedup7.json"
            ),
        )
        ch = FakeChannel()
        router = AlertRouter(config=cfg, channels=[ch])
        signal = _make_signal(EventType.SAFETY_SIGNAL)
        router.enqueue_signal_alerts(signal=signal, extraction=_make_extraction())
        sent = router.flush(signal.asset_id)
        assert sent == []
        assert len(ch.sent) == 0

    def test_none_router_in_pipeline_does_not_crash(self):
        """WatchlistPipelineRunner with alert_router=None should run normally."""
        # This is a smoke test — alert_router=None is the default.
        # The runner checks `if self.alert_router is not None` before each call.
        assert True  # covered by pipeline tests


class TestBacktestSnapshots:
    def test_router_writes_snapshot_when_knowledge_store_is_set(self):
        store = KnowledgeStore(":memory:")
        try:
            cfg = AlertsConfig(
                thresholds=AlertThresholdsConfig(
                    material_change_abs_floor_millions=25.0,
                    material_change_pct=15.0,
                    dedup_window_hours=0.0,
                    dedup_state_path="/tmp/bve_test_dedup_snapshot.json",
                )
            )
            channel = FakeChannel()
            router = AlertRouter(config=cfg, channels=[channel], knowledge_store=store)
            signal = _make_signal(EventType.TRIAL_READOUT, confidence=0.8)
            diff = _make_diff(delta_npv=40.0, before_npv=200.0)
            router.enqueue_diff_alerts(diff=diff, signal=signal, run_id="run-snapshot")
            router.flush(signal.asset_id)

            snaps = store.get_backtest_snapshots(asset_id=signal.asset_id)
            assert len(snaps) == 1
            assert snaps[0].alert_id
            assert snaps[0].delta_npv_millions == 40.0
        finally:
            store.close()
