from __future__ import annotations

from datetime import date, datetime, timezone

from bve.alerts.alert_config import AlertThresholdsConfig, AlertsConfig
from bve.alerts.alert_router import AlertRouter
from bve.alerts.channels.base import FakeChannel
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.knowledge_layer import (
    KnowledgeStore,
    OpportunityAlertRecord,
    SourceTrace,
)
from bve.intelligence.opportunity_snapshot import OpportunitySnapshotRecord, OpportunitySnapshotStore
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.ops.metrics import ConnectorHealthMetrics, RunMetrics, RunMetricsStore
from bve.ops.metrics_dashboard import MetricsDashboard, RunHealthMonitor


def _trace(ref: str) -> SourceTrace:
    return SourceTrace(source_type="unit_test", source_ref=ref)


def _doc(*, doc_id: str, asset_id: str, retrieved_at: datetime) -> RawDocument:
    return RawDocument.from_text(
        id=doc_id,
        source="press_release",
        title=f"{asset_id} update",
        raw_text=f"{asset_id} payload {doc_id}",
        source_url=f"https://example.org/{doc_id}",
        retrieved_at=retrieved_at,
        published_at=retrieved_at,
        entity_hints=EntityHints(asset_id=asset_id, company_id=f"co-{asset_id}"),
    )


def _signal(
    *,
    signal_id: str,
    event_id: str,
    asset_id: str,
    signal_date: date,
    created_at: datetime,
) -> StructuredSignal:
    return StructuredSignal(
        id=signal_id,
        event_id=event_id,
        asset_id=asset_id,
        company_id=f"co-{asset_id}",
        event_type=EventType.TRIAL_READOUT,
        signal_date=signal_date,
        extraction_confidence=0.78,
        created_at=created_at,
    )


def test_metrics_dashboard_builds_daily_counts_and_top_opportunities(tmp_path) -> None:
    db_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(str(db_path))
    try:
        doc_day_1 = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
        doc_day_3 = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)
        store.add_raw_document(_doc(doc_id="doc-1", asset_id="asset-a", retrieved_at=doc_day_1), _trace("doc-1"))
        store.add_raw_document(_doc(doc_id="doc-2", asset_id="asset-a", retrieved_at=doc_day_3), _trace("doc-2"))

        signal_created = datetime(2026, 3, 9, 13, 0, tzinfo=timezone.utc)
        signal = _signal(
            signal_id="signal-a",
            event_id="event-a",
            asset_id="asset-a",
            signal_date=date(2026, 3, 9),
            created_at=signal_created,
        )
        store.add_structured_signal(signal, _trace("signal-a"), extraction_result_id="extract-a")
        store.add_valuation_diff(
            {
                "run_id": "diff-a",
                "event_id": "event-a",
                "asset_id": "asset-a",
                "created_at": datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc).isoformat(),
                "valuation_before": {"rnpv_millions": 100.0},
                "valuation_after": {"rnpv_millions": 142.0},
                "delta_npv": 42.0,
            },
            company_id="co-asset-a",
            source_trace=_trace("diff-a"),
        )
        store.add_opportunity_alert(
            OpportunityAlertRecord(
                asset_id="asset-a",
                event_type="trial_readout",
                window="2026-03-10",
                run_id="run-a",
                created_at=datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc),
                payload_json={"score": 0.16},
            )
        )

        snapshot_store = OpportunitySnapshotStore(store)
        snapshot_store.write_snapshot(
            OpportunitySnapshotRecord(
                snapshot_date=date(2026, 3, 10),
                asset_id="asset-a",
                score=0.16,
                mispricing=0.42,
                confidence=0.78,
                event_type="trial_readout",
                rank=1,
                run_id="run-a",
                created_at=datetime(2026, 3, 10, 16, 0, tzinfo=timezone.utc),
            )
        )

        dashboard = MetricsDashboard(store)
        snapshot = dashboard.build(
            days=3,
            top_n=5,
            as_of=date(2026, 3, 10),
            reference_time=datetime(2026, 3, 10, 16, 0, tzinfo=timezone.utc),
        )

        assert [point.count for point in snapshot.documents_per_day] == [1, 0, 1]
        assert [point.count for point in snapshot.signals_per_day] == [0, 1, 0]
        assert [point.count for point in snapshot.diffs_per_day] == [0, 0, 1]
        assert [point.count for point in snapshot.alerts_per_day] == [0, 0, 1]
        assert len(snapshot.top_opportunities) == 1
        assert snapshot.top_opportunities[0].asset_id == "asset-a"
        assert snapshot.top_opportunities[0].days_since_event == 1
        assert all(check.passed for check in snapshot.health_checks)
    finally:
        store.close()


def test_run_health_monitor_emits_stall_and_connector_alerts(tmp_path) -> None:
    db_path = tmp_path / "knowledge.db"
    metrics_path = tmp_path / "run_metrics.json"
    store = KnowledgeStore(str(db_path))
    metrics_store = RunMetricsStore(metrics_path)
    try:
        old_dt = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        store.add_raw_document(_doc(doc_id="doc-old", asset_id="asset-a", retrieved_at=old_dt), _trace("doc-old"))
        store.add_structured_signal(
            _signal(
                signal_id="signal-old",
                event_id="event-old",
                asset_id="asset-a",
                signal_date=date(2026, 3, 1),
                created_at=old_dt,
            ),
            _trace("signal-old"),
            extraction_result_id="extract-old",
        )
        metrics_store.append(
            RunMetrics(
                run_id="run-health",
                measured_at=datetime(2026, 3, 11, 9, 0, tzinfo=timezone.utc),
                connector_health=[
                    ConnectorHealthMetrics(
                        connector="press_release",
                        success_rate=0.75,
                        error_rate=0.25,
                        avg_latency_ms=120.0,
                        n_runs_sampled=20,
                        last_failure_at=datetime(2026, 3, 11, 8, 0, tzinfo=timezone.utc),
                        last_success_at=datetime(2026, 3, 11, 7, 0, tzinfo=timezone.utc),
                        health_threshold=0.80,
                        healthy=False,
                    )
                ],
            )
        )

        router = AlertRouter(
            config=AlertsConfig(
                thresholds=AlertThresholdsConfig(
                    dedup_window_hours=0.0,
                    dedup_state_path=str(tmp_path / "health_dedup.json"),
                )
            ),
            channels=[FakeChannel()],
        )
        channel = router.channels[0]
        monitor = RunHealthMonitor(store, metrics_store=metrics_store)
        checks = monitor.emit_alerts(
            router=router,
            run_id="run-health",
            reference_time=datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc),
        )

        assert sum(1 for check in checks if not check.passed) == 3
        messages = [alert.message for alert in channel.sent]
        assert any("No documents ingested" in message for message in messages)
        assert any("No structured signals created" in message for message in messages)
        assert any("Connector health degraded: press_release" in message for message in messages)
    finally:
        store.close()
