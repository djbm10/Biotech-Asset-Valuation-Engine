from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from bve.alerts.alert_config import AlertThresholdsConfig, AlertsConfig
from bve.alerts.alert_router import AlertRouter
from bve.alerts.channels.base import FakeChannel
from bve.analysis.ranking_calibrator import CalibrationReport
from bve.intelligence.kg_integrity import KGIntegrityReport
from bve.intelligence.opportunity_scanner import OpportunityScanResult, OpportunityScannerConfig
from bve.intelligence.knowledge_layer import KnowledgeStore, OpportunityAlertRecord
from bve.ops.data_quality import DataQualityCheck, DataQualityScore
from bve.ops.metrics import ConnectorHealthMetrics
from bve.pipeline.history_replay import HistoryReplaySummary
from bve.pipeline.watchlist_runner import AssetRunSummary, WatchlistRunSummary
from bve.services.intelligence_service import IntelligenceService, IntelligenceServiceConfig
from bve.ops.control_plane import ServiceControlPlane
from bve.ui.dashboard.cache import DashboardCacheStore


class _FakeRunner:
    def __init__(self, knowledge: KnowledgeStore) -> None:
        self.knowledge = knowledge

    def run_once(self) -> WatchlistRunSummary:
        t0 = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 3, 9, 12, 1, tzinfo=timezone.utc)
        return WatchlistRunSummary(
            run_id="run-123",
            started_at=t0,
            finished_at=t1,
            assets=[
                AssetRunSummary(
                    run_id="run-123",
                    company_id="company-1",
                    asset_id="asset-1",
                    status="success",
                )
            ],
            stage_logs=[],
        )

    def close(self) -> None:
        self.knowledge.close()


class _FakeScanner:
    def __init__(self) -> None:
        self.config = OpportunityScannerConfig()

    def scan_from_watchlist_config(self, watchlist_config, *, run_id: str, scanned_at: datetime):
        return OpportunityScanResult(
            run_id=run_id,
            scanned_at=scanned_at,
            config=self.config,
            opportunities=[],
            alerts_emitted=[
                OpportunityAlertRecord(
                    asset_id="asset-1",
                    event_type="trial_readout",
                    window="2026-03-09T00:00:00+00:00__2026-03-10T00:00:00+00:00",
                    run_id=run_id,
                    created_at=scanned_at,
                    payload_json={"score": 0.7},
                )
            ],
            alerts_suppressed_as_duplicate=0,
        )


def _write_watchlist(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "polling_interval_seconds": 60,
                "watchlist": [
                    {
                        "company_id": "company-1",
                        "asset_id": "asset-1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_watchlist_two_assets(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "polling_interval_seconds": 60,
                "watchlist": [
                    {"company_id": "company-1", "asset_id": "asset-1"},
                    {"company_id": "company-2", "asset_id": "asset-2"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_intelligence_service_run_cycle_writes_cache_and_run_state(tmp_path: Path):
    watchlist_path = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist_path)

    knowledge = KnowledgeStore(":memory:")
    cfg = IntelligenceServiceConfig(
        watchlist_path=str(watchlist_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(tmp_path / "control.json"),
        metrics_path=str(tmp_path / "run_metrics.json"),
    )
    service = IntelligenceService(
        cfg,
        runner=_FakeRunner(knowledge),
        scanner=_FakeScanner(),
        cache_store=DashboardCacheStore(tmp_path / "cache.json"),
    )
    try:
        out = service.run_cycle()
        assert out.run_id == "run-123"
        assert out.dashboard_cache_metadata.cache_version == "1"

        rows = knowledge.get_run_states(run_id="run-123", asset_id="asset-1", limit=20)
        stages = {r.stage: r.status for r in rows}
        assert stages["opportunity_scan"] == "success"
        assert stages["dashboard_cache"] == "success"
    finally:
        service.close()


def test_intelligence_service_honors_pause_and_stop_controls(tmp_path: Path):
    watchlist_path = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist_path)
    control_path = tmp_path / "control.json"
    metrics_path = tmp_path / "run_metrics.json"

    knowledge = KnowledgeStore(":memory:")
    cfg = IntelligenceServiceConfig(
        watchlist_path=str(watchlist_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(control_path),
        metrics_path=str(metrics_path),
    )
    service = IntelligenceService(
        cfg,
        runner=_FakeRunner(knowledge),
        scanner=_FakeScanner(),
        cache_store=DashboardCacheStore(tmp_path / "cache.json"),
    )
    try:
        cp = ServiceControlPlane(control_path)
        cp.pause_stage("scanner")
        out = service.run_cycle()
        rows = knowledge.get_run_states(
            run_id=out.run_id, asset_id="asset-1", stage="opportunity_scan"
        )
        assert rows[0].status == "skipped"

        cp.request_stop()
        assert service.run_once() is False
    finally:
        service.close()


def test_intelligence_service_config_requires_exactly_one_watchlist_input(tmp_path: Path):
    watchlist_path = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist_path)

    cfg = IntelligenceServiceConfig(
        watchlist_dir=str(tmp_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(tmp_path / "control.json"),
        metrics_path=str(tmp_path / "run_metrics.json"),
    )
    assert cfg.watchlist_dir == str(tmp_path)

    with pytest.raises(Exception):
        IntelligenceServiceConfig(
            watchlist_path=str(watchlist_path),
            watchlist_dir=str(tmp_path),
        )


def test_intelligence_service_data_quality_gate_filters_scanner_assets(tmp_path: Path):
    watchlist_path = tmp_path / "watchlist.yaml"
    _write_watchlist_two_assets(watchlist_path)

    class _Runner:
        def __init__(self, knowledge: KnowledgeStore) -> None:
            self.knowledge = knowledge
            self.alert_router = None

        def run_once(self) -> WatchlistRunSummary:
            t0 = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
            t1 = datetime(2026, 3, 9, 12, 1, tzinfo=timezone.utc)
            return WatchlistRunSummary(
                run_id="run-dq",
                started_at=t0,
                finished_at=t1,
                assets=[
                    AssetRunSummary(
                        run_id="run-dq",
                        company_id="company-1",
                        asset_id="asset-1",
                        status="success",
                    ),
                    AssetRunSummary(
                        run_id="run-dq",
                        company_id="company-2",
                        asset_id="asset-2",
                        status="success",
                    ),
                ],
                stage_logs=[],
            )

        def close(self) -> None:
            self.knowledge.close()

    class _RecordingScanner:
        def __init__(self) -> None:
            self.config = OpportunityScannerConfig()
            self.seen_asset_ids: list[str] = []

        def scan_from_watchlist_config(
            self, watchlist_config, *, run_id: str, scanned_at: datetime
        ):
            self.seen_asset_ids = [a.asset_id for a in watchlist_config.watchlist]
            return OpportunityScanResult(
                run_id=run_id,
                scanned_at=scanned_at,
                config=self.config,
                opportunities=[],
                alerts_emitted=[],
                alerts_suppressed_as_duplicate=0,
            )

    class _FakeDQMonitor:
        def check_all(self, asset_ids: list[str]) -> list[DataQualityScore]:
            assert asset_ids == ["asset-1", "asset-2"]
            return [
                DataQualityScore(
                    asset_id="asset-1",
                    overall_score=0.5,
                    checks=[
                        DataQualityCheck(
                            check_type="doc_freshness",
                            asset_id="asset-1",
                            value=10.0,
                            threshold="<=3d",
                            passed=False,
                            details="old docs",
                        )
                    ],
                    failing_checks=["doc_freshness"],
                    gated=True,
                ),
                DataQualityScore(
                    asset_id="asset-2",
                    overall_score=1.0,
                    checks=[],
                    failing_checks=[],
                    gated=False,
                ),
            ]

    knowledge = KnowledgeStore(":memory:")
    scanner = _RecordingScanner()
    cfg = IntelligenceServiceConfig(
        watchlist_path=str(watchlist_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(tmp_path / "control.json"),
        metrics_path=str(tmp_path / "run_metrics.json"),
    )
    service = IntelligenceService(
        cfg,
        runner=_Runner(knowledge),
        scanner=scanner,
        cache_store=DashboardCacheStore(tmp_path / "cache.json"),
    )
    service.data_quality_monitor = _FakeDQMonitor()  # type: ignore[assignment]
    try:
        out = service.run_cycle()
        assert out.run_id == "run-dq"
        assert scanner.seen_asset_ids == ["asset-2"]

        gated_rows = knowledge.get_run_states(
            run_id="run-dq",
            asset_id="asset-1",
            stage="opportunity_scan",
        )
        assert gated_rows
        assert gated_rows[0].status == "skipped"
        assert gated_rows[0].checkpoint_json["reason"] == "data_quality_gate"

        watchlist_rows = knowledge.get_run_states(
            run_id="run-dq",
            asset_id="asset-1",
            stage="watchlist",
        )
        assert watchlist_rows
        assert watchlist_rows[0].status == "skipped"
        assert watchlist_rows[0].checkpoint_json["reason"] == "data_quality_gate"
    finally:
        service.close()


def test_intelligence_service_emits_connector_health_alert(tmp_path: Path):
    watchlist_path = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist_path)

    class _Runner:
        def __init__(self, knowledge: KnowledgeStore, alert_router: AlertRouter) -> None:
            self.knowledge = knowledge
            self.alert_router = alert_router

        def run_once(self) -> WatchlistRunSummary:
            t0 = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
            t1 = datetime(2026, 3, 9, 12, 1, tzinfo=timezone.utc)
            return WatchlistRunSummary(
                run_id="run-health",
                started_at=t0,
                finished_at=t1,
                assets=[
                    AssetRunSummary(
                        run_id="run-health",
                        company_id="company-1",
                        asset_id="asset-1",
                        status="success",
                    )
                ],
                stage_logs=[],
                connector_health=[
                    ConnectorHealthMetrics(
                        connector="clinicaltrials_gov",
                        success_rate=0.75,
                        error_rate=0.25,
                        avg_latency_ms=120.0,
                        n_runs_sampled=20,
                        last_failure_at=t1,
                        last_success_at=t0,
                        health_threshold=0.80,
                        healthy=False,
                    )
                ],
            )

        def close(self) -> None:
            self.knowledge.close()

    class _Scanner:
        def __init__(self) -> None:
            self.config = OpportunityScannerConfig()

        def scan_from_watchlist_config(
            self, watchlist_config, *, run_id: str, scanned_at: datetime
        ):
            return OpportunityScanResult(
                run_id=run_id,
                scanned_at=scanned_at,
                config=self.config,
                opportunities=[],
                alerts_emitted=[],
                alerts_suppressed_as_duplicate=0,
            )

    channel = FakeChannel()
    alerts_cfg = AlertsConfig(
        thresholds=AlertThresholdsConfig(
            dedup_window_hours=0.0,
            dedup_state_path=str(tmp_path / "dedup.json"),
        )
    )
    router = AlertRouter(config=alerts_cfg, channels=[channel])
    knowledge = KnowledgeStore(":memory:")
    cfg = IntelligenceServiceConfig(
        watchlist_path=str(watchlist_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(tmp_path / "control.json"),
        metrics_path=str(tmp_path / "run_metrics.json"),
    )
    service = IntelligenceService(
        cfg,
        runner=_Runner(knowledge, router),
        scanner=_Scanner(),
        cache_store=DashboardCacheStore(tmp_path / "cache.json"),
    )
    try:
        service.run_cycle()
        assert channel.sent
        assert any("No documents ingested" in alert.message for alert in channel.sent)
        assert any("No structured signals created" in alert.message for alert in channel.sent)
        connector_alerts = [
            alert for alert in channel.sent if "Connector health degraded: clinicaltrials_gov" in alert.message
        ]
        assert connector_alerts
        assert connector_alerts[0].severity.value == "medium"
        latest = service.metrics_store.latest()
        assert latest is not None
        assert any(metric.stage == "opportunity_scan" for metric in latest.stage_latencies)
        assert any(metric.stage == "dashboard_cache" for metric in latest.stage_latencies)
        assert latest.connector_health
        assert latest.connector_health[0].healthy is False
    finally:
        service.close()


def test_weekly_ranking_calibration_skips_when_sample_too_small(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    watchlist_path = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist_path)
    knowledge = KnowledgeStore(":memory:")
    cfg = IntelligenceServiceConfig(
        watchlist_path=str(watchlist_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(tmp_path / "control.json"),
        metrics_path=str(tmp_path / "run_metrics.json"),
        ranking_calibration_min_resolved_forecasts=100,
    )
    writes = {"count": 0}

    class _SmallSampleCalibrator:
        def __init__(self, store) -> None:
            self.store = store

        def calibrate(self) -> CalibrationReport:
            return CalibrationReport(
                run_date=datetime(2026, 3, 8, tzinfo=timezone.utc).date(),
                n_resolved_forecasts=10,
                event_type_weights={"trial_readout": 0.8},
                event_type_weights_prior={"trial_readout": 0.8},
                confidence_scaling_factor=1.0,
                brier_score=0.2,
                calibration_curve=[],
                drift_alerts=[],
            )

        def write_calibration(self, report: CalibrationReport) -> None:
            writes["count"] += 1

    monkeypatch.setattr(
        "bve.services.intelligence_service.RankingCalibrator",
        _SmallSampleCalibrator,
    )

    service = IntelligenceService(
        cfg,
        runner=_FakeRunner(knowledge),
        scanner=_FakeScanner(),
        cache_store=DashboardCacheStore(tmp_path / "cache.json"),
    )
    try:
        # Sunday calibration checkpoint
        service._maybe_run_weekly_ranking_calibration(  # noqa: SLF001
            reference_time=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
        )
        assert writes["count"] == 0
    finally:
        service.close()


def test_weekly_kg_integrity_runs_on_interval_and_logs_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    watchlist_path = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist_path)
    knowledge = KnowledgeStore(":memory:")
    cfg = IntelligenceServiceConfig(
        watchlist_path=str(watchlist_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(tmp_path / "control.json"),
        metrics_path=str(tmp_path / "run_metrics.json"),
        kg_integrity_check_interval_days=7,
    )
    calls = {"count": 0}

    class _PassingChecker:
        def __init__(self, store) -> None:
            self.store = store

        def check(self, watchlist_asset_ids: list[str]) -> KGIntegrityReport:
            calls["count"] += 1
            assert watchlist_asset_ids == ["asset-1"]
            return KGIntegrityReport(
                n_nodes=1,
                n_edges=0,
                orphan_edges=[],
                duplicate_nodes=[],
                invalid_confidence=[],
                missing_asset_nodes=[],
                passed=True,
            )

    monkeypatch.setattr(
        "bve.services.intelligence_service.KGIntegrityChecker",
        _PassingChecker,
    )

    service = IntelligenceService(
        cfg,
        runner=_FakeRunner(knowledge),
        scanner=_FakeScanner(),
        cache_store=DashboardCacheStore(tmp_path / "cache.json"),
    )
    try:
        service._maybe_run_weekly_kg_integrity(  # noqa: SLF001
            run_id="run-kg-1",
            reference_time=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        )
        service._maybe_run_weekly_kg_integrity(  # noqa: SLF001
            run_id="run-kg-2",
            reference_time=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        )
        service._maybe_run_weekly_kg_integrity(  # noqa: SLF001
            run_id="run-kg-3",
            reference_time=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
        )
        assert calls["count"] == 2
        latest = knowledge.get_latest_kg_integrity()
        assert latest is not None
        assert latest["passed"] is True
    finally:
        service.close()


def test_weekly_kg_integrity_failure_emits_high_alert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    watchlist_path = tmp_path / "watchlist.yaml"
    _write_watchlist(watchlist_path)
    channel = FakeChannel()
    router = AlertRouter(
        config=AlertsConfig(
            thresholds=AlertThresholdsConfig(
                dedup_window_hours=0.0,
                dedup_state_path=str(tmp_path / "kg_integrity_dedup.json"),
            )
        ),
        channels=[channel],
    )
    knowledge = KnowledgeStore(":memory:")
    runner = _FakeRunner(knowledge)
    runner.alert_router = router  # type: ignore[attr-defined]

    cfg = IntelligenceServiceConfig(
        watchlist_path=str(watchlist_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(tmp_path / "control.json"),
        metrics_path=str(tmp_path / "run_metrics.json"),
        kg_integrity_check_interval_days=7,
    )

    class _FailingChecker:
        def __init__(self, store) -> None:
            self.store = store

        def check(self, watchlist_asset_ids: list[str]) -> KGIntegrityReport:
            assert watchlist_asset_ids == ["asset-1"]
            return KGIntegrityReport(
                n_nodes=2,
                n_edges=1,
                orphan_edges=["edge-1"],
                duplicate_nodes=["asset::asset-1 (count=2)"],
                invalid_confidence=[],
                missing_asset_nodes=[],
                passed=False,
            )

    monkeypatch.setattr(
        "bve.services.intelligence_service.KGIntegrityChecker",
        _FailingChecker,
    )

    service = IntelligenceService(
        cfg,
        runner=runner,
        scanner=_FakeScanner(),
        cache_store=DashboardCacheStore(tmp_path / "cache.json"),
    )
    try:
        service._maybe_run_weekly_kg_integrity(  # noqa: SLF001
            run_id="run-kg-fail",
            reference_time=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        )
        assert channel.sent
        assert channel.sent[0].severity.value == "high"
        assert (
            "KG integrity check failed: 1 orphan edges, 1 duplicate nodes"
            in channel.sent[0].message
        )
        latest = knowledge.get_latest_kg_integrity()
        assert latest is not None
        assert latest["passed"] is False
    finally:
        service.close()


def test_schedule_enabled_runs_daily_ingestion_without_weekly_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    watchlist_path = tmp_path / "watchlist_schedule.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "polling_interval_seconds": 60,
                "schedule": {
                    "enabled": True,
                    "daily_ingestion_interval_hours": 24,
                    "weekly_maintenance_weekday": 6,
                    "weekly_replay_since": "7d",
                },
                "watchlist": [{"company_id": "company-1", "asset_id": "asset-1"}],
            }
        ),
        encoding="utf-8",
    )

    class _ScheduleRunner:
        def __init__(self, knowledge: KnowledgeStore) -> None:
            self.knowledge = knowledge
            self.calls: list[dict] = []
            self.alert_router = None

        def run_once(self, **kwargs) -> WatchlistRunSummary:
            self.calls.append(dict(kwargs))
            t0 = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
            t1 = datetime(2026, 3, 10, 12, 1, tzinfo=timezone.utc)
            return WatchlistRunSummary(
                run_id=kwargs.get("run_id", "run-daily"),
                started_at=t0,
                finished_at=t1,
                assets=[
                    AssetRunSummary(
                        run_id=kwargs.get("run_id", "run-daily"),
                        company_id="company-1",
                        asset_id="asset-1",
                        status="success",
                    )
                ],
                stage_logs=[],
            )

        def close(self) -> None:
            self.knowledge.close()

    class _CountingScanner(_FakeScanner):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def scan_from_watchlist_config(self, watchlist_config, *, run_id: str, scanned_at: datetime):
            self.calls += 1
            return super().scan_from_watchlist_config(
                watchlist_config,
                run_id=run_id,
                scanned_at=scanned_at,
            )

    knowledge = KnowledgeStore(":memory:")
    runner = _ScheduleRunner(knowledge)
    scanner = _CountingScanner()
    cfg = IntelligenceServiceConfig(
        watchlist_path=str(watchlist_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(tmp_path / "control.json"),
        metrics_path=str(tmp_path / "run_metrics.json"),
    )
    monkeypatch.setattr(
        "bve.services.intelligence_service._utcnow",
        lambda: datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
    )

    service = IntelligenceService(
        cfg,
        runner=runner,
        scanner=scanner,
        cache_store=DashboardCacheStore(tmp_path / "cache.json"),
    )
    try:
        out = service.run_cycle()
        assert runner.calls
        assert runner.calls[0]["enable_valuation"] is False
        assert runner.calls[0]["enable_memos"] is False
        assert runner.calls[0]["refresh_market_prices"] is False
        assert scanner.calls == 1
        rows = knowledge.get_run_states(
            run_id=out.run_id,
            asset_id="asset-1",
            stage="opportunity_scan",
        )
        assert rows[0].status == "success"
        latest = service.metrics_store.latest()
        assert latest is not None
        assert latest.stage_metrics["daily_ingestion_executed"] is True
        assert latest.stage_metrics["weekly_maintenance_executed"] is False
    finally:
        service.close()


def test_schedule_enabled_runs_weekly_replay_and_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    watchlist_path = tmp_path / "watchlist_schedule.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "polling_interval_seconds": 60,
                "schedule": {
                    "enabled": True,
                    "daily_ingestion_interval_hours": 24,
                    "weekly_maintenance_weekday": 6,
                    "weekly_replay_since": "7d",
                },
                "watchlist": [{"company_id": "company-1", "asset_id": "asset-1"}],
            }
        ),
        encoding="utf-8",
    )

    class _ScheduleRunner:
        def __init__(self, knowledge: KnowledgeStore) -> None:
            self.knowledge = knowledge
            self.alert_router = None

        def run_once(self, **kwargs) -> WatchlistRunSummary:
            t0 = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
            t1 = datetime(2026, 3, 8, 12, 1, tzinfo=timezone.utc)
            return WatchlistRunSummary(
                run_id=kwargs.get("run_id", "run-weekly"),
                started_at=t0,
                finished_at=t1,
                assets=[
                    AssetRunSummary(
                        run_id=kwargs.get("run_id", "run-weekly"),
                        company_id="company-1",
                        asset_id="asset-1",
                        status="success",
                    )
                ],
                stage_logs=[],
            )

        def close(self) -> None:
            self.knowledge.close()

    class _CountingScanner(_FakeScanner):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def scan_from_watchlist_config(self, watchlist_config, *, run_id: str, scanned_at: datetime):
            self.calls += 1
            return super().scan_from_watchlist_config(
                watchlist_config,
                run_id=run_id,
                scanned_at=scanned_at,
            )

    replay_calls = {"count": 0, "since": None}

    class _FakeReplayRunner:
        def __init__(self, config) -> None:
            self.config = config

        def replay(self, *, since=None, run_id=None) -> HistoryReplaySummary:
            replay_calls["count"] += 1
            replay_calls["since"] = since
            return HistoryReplaySummary(
                run_id=run_id or "weekly-replay",
                started_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 3, 8, 12, 5, tzinfo=timezone.utc),
                documents_replayed=3,
                valuation_diffs_persisted=1,
                memos_persisted=1,
                assets=[
                    AssetRunSummary(
                        run_id=run_id or "weekly-replay",
                        company_id="company-1",
                        asset_id="asset-1",
                        status="success",
                    )
                ],
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "bve.services.intelligence_service._utcnow",
        lambda: datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        "bve.services.intelligence_service.HistoryReplayRunner",
        _FakeReplayRunner,
    )

    knowledge = KnowledgeStore(":memory:")
    cfg = IntelligenceServiceConfig(
        watchlist_path=str(watchlist_path),
        dashboard_cache_path=str(tmp_path / "cache.json"),
        control_state_path=str(tmp_path / "control.json"),
        metrics_path=str(tmp_path / "run_metrics.json"),
    )
    service = IntelligenceService(
        cfg,
        runner=_ScheduleRunner(knowledge),
        scanner=_CountingScanner(),
        cache_store=DashboardCacheStore(tmp_path / "cache.json"),
    )
    try:
        service.run_cycle()
        assert replay_calls["count"] == 1
        assert replay_calls["since"] == "7d"
        assert service.scanner.calls == 1  # type: ignore[attr-defined]
        latest = service.metrics_store.latest()
        assert latest is not None
        assert latest.stage_metrics["weekly_maintenance_executed"] is True
    finally:
        service.close()
