"""Continuous runtime orchestrator for the intelligence-to-valuation pipeline."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from bve.analysis.ranking_calibrator import RankingCalibrator
from bve.intelligence.kg_integrity import KGIntegrityChecker
from bve.intelligence.opportunity_scanner import (
    OpportunityScanResult,
    OpportunityScanner,
    OpportunityScannerConfig,
)
from bve.models.catalyst_model import CatalystModel
from bve.pipeline.history_replay import HistoryReplayRunner, HistoryReplaySummary
from bve.pipeline.watchlist_runner import (
    AssetRunSummary,
    WatchlistPipelineRunner,
    WatchlistRunSummary,
    load_watchlist_config,
)
from bve.ops.control_plane import ServiceControlPlane
from bve.ops.data_quality import DataQualityMonitor, DataQualityScore
from bve.ops.metrics_dashboard import MetricsDashboard, RunHealthMonitor, RunHealthMonitorConfig
from bve.ops.metrics import (
    RunMetrics,
    RunMetricsStore,
    StageLatencyMetrics,
)
from bve.services.scheduler import Scheduler, SchedulerConfig
from bve.ui.dashboard.cache import DashboardCacheMetadata, DashboardCacheStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntelligenceServiceConfig(BaseModel):
    """Service-level config wrapping watchlist + runtime behavior."""

    watchlist_path: Optional[str] = None
    watchlist_dir: Optional[str] = None
    dashboard_cache_path: str = "outputs/dashboard/cache.json"
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    scanner: OpportunityScannerConfig = Field(default_factory=OpportunityScannerConfig)
    source_model_version: str = "intelligence_service_v1"
    control_state_path: str = "outputs/watchlist/service_control.json"
    metrics_path: str = "logs/run_metrics.json"
    data_quality_gate_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    run_health: RunHealthMonitorConfig = Field(default_factory=RunHealthMonitorConfig)
    raw_document_retention_days: int = Field(default=90, ge=1)
    ranking_calibration_min_resolved_forecasts: int = Field(default=50, ge=1)
    kg_integrity_check_interval_days: int = Field(default=7, ge=1)

    @model_validator(mode="after")
    def _validate_watchlist_input(self) -> "IntelligenceServiceConfig":
        has_path = bool(self.watchlist_path)
        has_dir = bool(self.watchlist_dir)
        if has_path == has_dir:
            raise ValueError("Exactly one of watchlist_path or watchlist_dir must be set")
        return self


class IntelligenceServiceRun(BaseModel):
    """One full service-cycle output."""

    run_id: str
    started_at: datetime
    finished_at: datetime
    watchlist_summary: WatchlistRunSummary
    opportunity_scan: OpportunityScanResult
    dashboard_cache_metadata: DashboardCacheMetadata


class IntelligenceService:
    """Orchestrates watchlist runner -> opportunity scanner -> dashboard cache."""

    def __init__(
        self,
        config: IntelligenceServiceConfig,
        *,
        runner: Optional[WatchlistPipelineRunner] = None,
        scanner: Optional[OpportunityScanner] = None,
        cache_store: Optional[DashboardCacheStore] = None,
        scheduler: Optional[Scheduler] = None,
        control_plane: Optional[ServiceControlPlane] = None,
        metrics_store: Optional[RunMetricsStore] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("bve.services.intelligence")
        watchlist_input = config.watchlist_dir or config.watchlist_path
        assert watchlist_input is not None
        self.watchlist_config = load_watchlist_config(watchlist_input)
        if runner is None:
            alert_router = None
            alerts_cfg = getattr(self.watchlist_config, "alerts", None)
            if alerts_cfg is not None:
                from bve.alerts.alert_config import AlertsConfig
                from bve.alerts.alert_router import AlertRouter

                resolved_alerts = (
                    alerts_cfg
                    if isinstance(alerts_cfg, AlertsConfig)
                    else AlertsConfig.model_validate(alerts_cfg)
                )
                self.watchlist_config = self.watchlist_config.model_copy(
                    update={"alerts": resolved_alerts}
                )
                if resolved_alerts.enabled:
                    alert_router = AlertRouter.from_config(resolved_alerts)
            self.runner = WatchlistPipelineRunner(
                self.watchlist_config,
                alert_router=alert_router,
            )
        else:
            self.runner = runner
        self.scanner = scanner or OpportunityScanner(
            knowledge_store=self.runner.knowledge,
            config=config.scanner,
            catalyst_model=CatalystModel(self.runner.knowledge),
        )
        self._last_ranking_calibration_date: Optional[str] = None
        self._last_kg_integrity_check_at: Optional[datetime] = None
        self._last_event_impact_ledger_date: Optional[str] = None
        self._last_pos_calibration_date: Optional[str] = None
        self.data_quality_monitor = DataQualityMonitor(
            self.runner.knowledge,
            gate_threshold=config.data_quality_gate_threshold,
        )
        self.cache_store = cache_store or DashboardCacheStore(config.dashboard_cache_path)
        self.control_plane = control_plane or ServiceControlPlane(config.control_state_path)
        self.metrics_store = metrics_store or RunMetricsStore(config.metrics_path)
        self.run_health_monitor = RunHealthMonitor(
            self.runner.knowledge,
            metrics_store=self.metrics_store,
            config=config.run_health,
        )
        self.metrics_dashboard = MetricsDashboard(
            self.runner.knowledge,
            metrics_store=self.metrics_store,
            health_monitor=self.run_health_monitor,
        )
        scheduler_cfg = config.scheduler.model_copy(
            update={"interval_seconds": self.watchlist_config.polling_interval_seconds}
        )
        self.scheduler = scheduler or Scheduler(config=scheduler_cfg, logger=self.logger)

    @classmethod
    def from_watchlist(
        cls,
        watchlist_path: str | Path,
        *,
        dashboard_cache_path: str = "outputs/dashboard/cache.json",
        lock_path: str = "outputs/watchlist/intelligence_service.lock",
        control_state_path: str = "outputs/watchlist/service_control.json",
        metrics_path: str = "logs/run_metrics.json",
    ) -> "IntelligenceService":
        cfg = IntelligenceServiceConfig(
            watchlist_path=str(watchlist_path),
            dashboard_cache_path=dashboard_cache_path,
            control_state_path=control_state_path,
            metrics_path=metrics_path,
            scheduler=SchedulerConfig(lock_path=lock_path),
        )
        return cls(cfg)

    def close(self) -> None:
        self.runner.close()

    def _last_task_execution_at(self, metric_key: str) -> Optional[datetime]:
        for metrics in reversed(self.metrics_store.load_all()):
            if bool(metrics.stage_metrics.get(metric_key)):
                return metrics.measured_at
        return None

    def _daily_ingestion_due(self, *, reference_time: datetime) -> bool:
        schedule = self.watchlist_config.schedule
        last = self._last_task_execution_at("daily_ingestion_executed")
        if last is None:
            return True
        elapsed = (reference_time - last).total_seconds()
        return elapsed >= schedule.daily_ingestion_interval_hours * 3600

    def _weekly_maintenance_due(self, *, reference_time: datetime) -> bool:
        schedule = self.watchlist_config.schedule
        if reference_time.weekday() != schedule.weekly_maintenance_weekday:
            return False
        last = self._last_task_execution_at("weekly_maintenance_executed")
        if last is None:
            return True
        last_iso = last.isocalendar()
        current_iso = reference_time.isocalendar()
        return (last_iso.year, last_iso.week) != (current_iso.year, current_iso.week)

    def _run_weekly_replay(
        self,
        *,
        watchlist_config,
        run_id: str,
    ) -> HistoryReplaySummary:
        replay_runner = HistoryReplayRunner(watchlist_config)
        try:
            return replay_runner.replay(
                since=watchlist_config.schedule.weekly_replay_since,
                run_id=run_id,
            )
        finally:
            replay_runner.close()

    def run_cycle(self) -> IntelligenceServiceRun:
        started = _utcnow()
        control = self.control_plane.load()
        paused_stages = set(control.paused_stages)
        run_id = str(uuid.uuid4())
        knowledge = self.runner.knowledge
        schedule_enabled = bool(self.watchlist_config.schedule.enabled)
        daily_ingestion_due = (
            self._daily_ingestion_due(reference_time=started) if schedule_enabled else True
        )
        weekly_maintenance_due = (
            self._weekly_maintenance_due(reference_time=started) if schedule_enabled else False
        )
        daily_ingestion_executed = False
        weekly_maintenance_executed = False

        data_quality_scores = self.data_quality_monitor.check_all(
            [asset.asset_id for asset in self.watchlist_config.watchlist]
        )
        dq_by_asset = {score.asset_id: score for score in data_quality_scores}
        gated_asset_ids = {score.asset_id for score in data_quality_scores if score.gated}
        for score in data_quality_scores:
            if score.gated:
                self.logger.warning(
                    "data_quality_gate asset_id=%s overall_score=%.3f failing_checks=%s",
                    score.asset_id,
                    score.overall_score,
                    score.failing_checks,
                )
        active_watchlist = [
            asset
            for asset in self.watchlist_config.watchlist
            if asset.asset_id not in gated_asset_ids
        ]
        active_watchlist_cfg = self.watchlist_config.model_copy(update={"watchlist": active_watchlist})

        if "watchlist" in paused_stages:
            watchlist_summary = self._build_skipped_watchlist_summary(
                run_id=run_id,
                ts=started,
                reason="paused_by_control_plane",
            )
        elif not active_watchlist:
            watchlist_summary = WatchlistRunSummary(
                run_id=run_id,
                started_at=started,
                finished_at=_utcnow(),
                assets=[],
                stage_logs=[],
            )
        elif schedule_enabled and not daily_ingestion_due:
            watchlist_summary = self._build_skipped_watchlist_summary(
                run_id=run_id,
                ts=started,
                reason="schedule_not_due_daily_ingestion",
            )
        else:
            original_runner_config = getattr(self.runner, "config", None)
            runner_config_replaced = False
            if original_runner_config is not None and hasattr(original_runner_config, "model_copy"):
                self.runner.config = original_runner_config.model_copy(  # type: ignore[attr-defined]
                    update={"watchlist": active_watchlist}
                )
                runner_config_replaced = True
            elif len(active_watchlist) != len(self.watchlist_config.watchlist):
                self.logger.warning(
                    "runner_config_not_mutable; data_quality_gate applied at scan stage only"
                )
            try:
                try:
                    if schedule_enabled:
                        watchlist_summary = self.runner.run_once(  # type: ignore[call-arg]
                            run_id=run_id,
                            enable_valuation=False,
                            enable_memos=False,
                            refresh_market_prices=False,
                        )
                    else:
                        watchlist_summary = self.runner.run_once(run_id=run_id)  # type: ignore[call-arg]
                except TypeError:
                    watchlist_summary = self.runner.run_once()
            finally:
                if runner_config_replaced and original_runner_config is not None:
                    self.runner.config = original_runner_config  # type: ignore[attr-defined]
            run_id = watchlist_summary.run_id or run_id
            daily_ingestion_executed = True

        for score in data_quality_scores:
            knowledge.log_data_quality(score, run_id=run_id)

        for asset in self.watchlist_config.watchlist:
            if asset.asset_id not in gated_asset_ids:
                continue
            dq = dq_by_asset.get(asset.asset_id)
            checkpoint = {
                "reason": "data_quality_gate",
                "overall_score": dq.overall_score if dq is not None else None,
                "failing_checks": dq.failing_checks if dq is not None else [],
            }
            knowledge.mark_run_state_started(
                run_id=run_id,
                stage="watchlist",
                asset_id=asset.asset_id,
                started_at=started,
                checkpoint_json=checkpoint,
            )
            knowledge.mark_run_state_finished(
                run_id=run_id,
                stage="watchlist",
                asset_id=asset.asset_id,
                status="skipped",
                started_at=started,
                finished_at=_utcnow(),
                checkpoint_json=checkpoint,
            )

        scan_watchlist = [
            asset
            for asset in self.watchlist_config.watchlist
            if asset.asset_id not in gated_asset_ids
        ]
        scan_watchlist_cfg = self.watchlist_config.model_copy(update={"watchlist": scan_watchlist})

        weekly_replay_summary: Optional[HistoryReplaySummary] = None
        if schedule_enabled and weekly_maintenance_due and "watchlist" not in paused_stages and scan_watchlist:
            try:
                weekly_replay_summary = self._run_weekly_replay(
                    watchlist_config=active_watchlist_cfg,
                    run_id=run_id,
                )
                weekly_maintenance_executed = True
                self.logger.info(
                    "weekly_replay_completed run_id=%s assets=%d documents=%d diffs=%d memos=%d",
                    run_id,
                    len(weekly_replay_summary.assets),
                    weekly_replay_summary.documents_replayed,
                    weekly_replay_summary.valuation_diffs_persisted,
                    weekly_replay_summary.memos_persisted,
                )
            except Exception as exc:
                self.logger.warning("weekly_replay_failed run_id=%s: %s", run_id, exc)

        for asset in self.watchlist_config.watchlist:
            knowledge.mark_run_state_started(
                run_id=run_id,
                stage="opportunity_scan",
                asset_id=asset.asset_id,
                started_at=started,
                checkpoint_json={
                    "company_id": asset.company_id,
                    "data_quality_gated": asset.asset_id in gated_asset_ids,
                },
            )

        scan: OpportunityScanResult
        scan_error: Optional[Exception] = None
        scan_stage_started = time.perf_counter()
        if "opportunity_scan" in paused_stages:
            scan = OpportunityScanResult(
                run_id=run_id,
                scanned_at=watchlist_summary.finished_at,
                config=self.config.scanner,
                opportunities=[],
                alerts_emitted=[],
                alerts_suppressed_as_duplicate=0,
            )
            for asset in self.watchlist_config.watchlist:
                knowledge.mark_run_state_finished(
                    run_id=run_id,
                    stage="opportunity_scan",
                    asset_id=asset.asset_id,
                    status="skipped",
                    started_at=started,
                    finished_at=_utcnow(),
                    checkpoint_json={"reason": "paused_by_control_plane"},
                )
        elif schedule_enabled and not (daily_ingestion_due or weekly_maintenance_due):
            scan = OpportunityScanResult(
                run_id=run_id,
                scanned_at=watchlist_summary.finished_at,
                config=self.config.scanner,
                opportunities=[],
                alerts_emitted=[],
                alerts_suppressed_as_duplicate=0,
            )
            for asset in self.watchlist_config.watchlist:
                knowledge.mark_run_state_finished(
                    run_id=run_id,
                    stage="opportunity_scan",
                    asset_id=asset.asset_id,
                    status="skipped",
                    started_at=started,
                    finished_at=_utcnow(),
                    checkpoint_json={"reason": "schedule_not_due_weekly_maintenance"},
                )
        else:
            for asset in self.watchlist_config.watchlist:
                if asset.asset_id not in gated_asset_ids:
                    continue
                dq = dq_by_asset.get(asset.asset_id)
                checkpoint = {
                    "reason": "data_quality_gate",
                    "overall_score": dq.overall_score if dq is not None else None,
                    "failing_checks": dq.failing_checks if dq is not None else [],
                }
                knowledge.mark_run_state_finished(
                    run_id=run_id,
                    stage="opportunity_scan",
                    asset_id=asset.asset_id,
                    status="skipped",
                    started_at=started,
                    finished_at=_utcnow(),
                    checkpoint_json=checkpoint,
                )
            try:
                if scan_watchlist:
                    scan = self.scanner.scan_from_watchlist_config(
                        scan_watchlist_cfg,
                        run_id=run_id,
                        scanned_at=watchlist_summary.finished_at,
                    )
                else:
                    scan = OpportunityScanResult(
                        run_id=run_id,
                        scanned_at=watchlist_summary.finished_at,
                        config=self.config.scanner,
                        opportunities=[],
                        alerts_emitted=[],
                        alerts_suppressed_as_duplicate=0,
                    )
            except Exception as exc:  # pragma: no cover - defensive service guard
                scan_error = exc
                scan = OpportunityScanResult(
                    run_id=run_id,
                    scanned_at=watchlist_summary.finished_at,
                    config=self.config.scanner,
                    opportunities=[],
                    alerts_emitted=[],
                    alerts_suppressed_as_duplicate=0,
                )
            for asset in scan_watchlist:
                emitted = sum(1 for a in scan.alerts_emitted if a.asset_id == asset.asset_id)
                knowledge.mark_run_state_finished(
                    run_id=run_id,
                    stage="opportunity_scan",
                    asset_id=asset.asset_id,
                    status="failure" if scan_error is not None else "success",
                    started_at=started,
                    finished_at=_utcnow(),
                    checkpoint_json={
                        "alerts_emitted": emitted,
                        "opportunities_scored": len(scan.opportunities),
                    },
                    error_json={"error": str(scan_error)} if scan_error is not None else {},
                )
        scan_latency_ms = (time.perf_counter() - scan_stage_started) * 1000.0

        cache_started = _utcnow()
        for asset in self.watchlist_config.watchlist:
            knowledge.mark_run_state_started(
                run_id=run_id,
                stage="dashboard_cache",
                asset_id=asset.asset_id,
                started_at=cache_started,
                checkpoint_json={},
            )

        cache_error: Optional[Exception] = None
        cache_meta: Optional[DashboardCacheMetadata] = None
        cache_stage_started = time.perf_counter()
        if "dashboard_cache" in paused_stages:
            cache_meta = DashboardCacheMetadata(
                cache_version="paused",
                source_run_id=run_id,
                source_model_version=self.config.source_model_version,
                generated_at=_utcnow(),
            )
            for asset in self.watchlist_config.watchlist:
                knowledge.mark_run_state_finished(
                    run_id=run_id,
                    stage="dashboard_cache",
                    asset_id=asset.asset_id,
                    status="skipped",
                    started_at=cache_started,
                    finished_at=_utcnow(),
                    checkpoint_json={"reason": "paused_by_control_plane"},
                )
        else:
            try:
                metrics_dashboard = self.metrics_dashboard.build(
                    as_of=_utcnow().date(),
                    reference_time=_utcnow(),
                )
                cache = self.cache_store.write(
                    source_run_id=run_id,
                    source_model_version=self.config.source_model_version,
                    payload={
                        "watchlist_summary": watchlist_summary.model_dump(mode="json"),
                        "opportunity_scan": scan.model_dump(mode="json"),
                        "metrics_dashboard": metrics_dashboard.model_dump(mode="json"),
                    },
                    generated_at=_utcnow(),
                )
                cache_meta = cache.metadata
            except Exception as exc:  # pragma: no cover - defensive service guard
                cache_error = exc
                cache_meta = DashboardCacheMetadata(
                    cache_version="error",
                    source_run_id=run_id,
                    source_model_version=self.config.source_model_version,
                    generated_at=_utcnow(),
                )
            for asset in self.watchlist_config.watchlist:
                knowledge.mark_run_state_finished(
                    run_id=run_id,
                    stage="dashboard_cache",
                    asset_id=asset.asset_id,
                    status="failure" if cache_error is not None else "success",
                    started_at=cache_started,
                    finished_at=_utcnow(),
                    checkpoint_json=cache_meta.model_dump(mode="json"),
                    error_json={"error": str(cache_error)} if cache_error is not None else {},
                )
        cache_latency_ms = (time.perf_counter() - cache_stage_started) * 1000.0

        retention_result = knowledge.apply_retention_policy(
            raw_documents_days=self.config.raw_document_retention_days,
            reference_time=_utcnow(),
        )

        metrics = self._build_metrics(
            run_id=run_id,
            watchlist_summary=watchlist_summary,
            scan=scan,
            scan_error=scan_error,
            cache_error=cache_error,
            paused_stages=paused_stages,
            data_quality_scores=data_quality_scores,
            scan_latency_ms=scan_latency_ms,
            cache_latency_ms=cache_latency_ms,
            daily_ingestion_due=daily_ingestion_due,
            daily_ingestion_executed=daily_ingestion_executed,
            weekly_maintenance_due=weekly_maintenance_due,
            weekly_maintenance_executed=weekly_maintenance_executed,
            raw_documents_deleted=retention_result.raw_documents_deleted,
        )
        self.metrics_store.append(metrics)
        self.logger.info(
            "run_metrics %s",
            metrics.model_dump_json(),
        )
        finished = _utcnow()
        self.run_health_monitor.emit_alerts(
            router=getattr(self.runner, "alert_router", None),
            run_id=run_id,
            reference_time=finished,
            latest_metrics=metrics,
        )
        self._maybe_run_weekly_kg_integrity(
            run_id=run_id,
            reference_time=finished,
        )
        self._maybe_run_weekly_ranking_calibration(reference_time=finished)
        self._maybe_run_weekly_event_impact_ledger(reference_time=finished)
        self._maybe_run_weekly_pos_calibration(reference_time=finished)
        self.logger.info(
            "intelligence_service_cycle run_id=%s assets=%d alerts=%d",
            run_id,
            len(self.watchlist_config.watchlist),
            len(scan.alerts_emitted),
        )
        return IntelligenceServiceRun(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            watchlist_summary=watchlist_summary,
            opportunity_scan=scan,
            dashboard_cache_metadata=cache_meta,
        )

    def run_once(self) -> bool:
        control = self.control_plane.load()
        if control.stop_requested:
            self.logger.info("service_stop_requested_pre_run")
            return False
        return self.scheduler.run_once(self.run_cycle)

    def run_forever(self, *, max_cycles: Optional[int] = None) -> None:
        cycle = 0
        while True:
            cycle += 1
            control = self.control_plane.load()
            if control.stop_requested:
                self.logger.info("service_stop_requested cycle=%d", cycle)
                return
            self.scheduler.run_once(self.run_cycle)
            if max_cycles is not None and cycle >= max_cycles:
                return
            time.sleep(self.scheduler.config.interval_seconds)

    def _build_skipped_watchlist_summary(
        self,
        *,
        run_id: str,
        ts: datetime,
        reason: str,
    ) -> WatchlistRunSummary:
        assets = []
        for item in self.watchlist_config.watchlist:
            assets.append(
                AssetRunSummary(
                    run_id=run_id,
                    company_id=item.company_id,
                    asset_id=item.asset_id,
                    status="success",
                    documents_fetched=0,
                    documents_processed=0,
                    events_created=0,
                    signals_created=0,
                    proposals_generated=0,
                    valuation_runs=0,
                    valuation_diffs_persisted=0,
                    review_decisions_logged=0,
                    memo_generated=False,
                    memo_id=None,
                    dossier_id=None,
                    alerts_fired=0,
                    errors=[],
                )
            )
        for asset in self.watchlist_config.watchlist:
            self.runner.knowledge.mark_run_state_started(
                run_id=run_id,
                stage="watchlist",
                asset_id=asset.asset_id,
                started_at=ts,
                checkpoint_json={"reason": reason},
            )
            self.runner.knowledge.mark_run_state_finished(
                run_id=run_id,
                stage="watchlist",
                asset_id=asset.asset_id,
                status="skipped",
                started_at=ts,
                finished_at=_utcnow(),
                checkpoint_json={"reason": reason},
            )
        return WatchlistRunSummary(
            run_id=run_id,
            started_at=ts,
            finished_at=_utcnow(),
            assets=assets,
            stage_logs=[],
        )

    @staticmethod
    def _build_metrics(
        *,
        run_id: str,
        watchlist_summary: WatchlistRunSummary,
        scan: OpportunityScanResult,
        scan_error: Optional[Exception],
        cache_error: Optional[Exception],
        paused_stages: set[str],
        data_quality_scores: list[DataQualityScore],
        scan_latency_ms: float,
        cache_latency_ms: float,
        daily_ingestion_due: bool,
        daily_ingestion_executed: bool,
        weekly_maintenance_due: bool,
        weekly_maintenance_executed: bool,
        raw_documents_deleted: int,
    ) -> RunMetrics:
        assets = watchlist_summary.assets
        stage_latencies = list(watchlist_summary.stage_latencies)
        stage_latencies.extend(
            [
                StageLatencyMetrics(
                    stage="opportunity_scan",
                    avg_ms=round(scan_latency_ms, 6),
                    p50_ms=round(scan_latency_ms, 6),
                    p95_ms=round(scan_latency_ms, 6),
                    p99_ms=round(scan_latency_ms, 6),
                    n_observations=1,
                ),
                StageLatencyMetrics(
                    stage="dashboard_cache",
                    avg_ms=round(cache_latency_ms, 6),
                    p50_ms=round(cache_latency_ms, 6),
                    p95_ms=round(cache_latency_ms, 6),
                    p99_ms=round(cache_latency_ms, 6),
                    n_observations=1,
                ),
            ]
        )
        return RunMetrics(
            run_id=run_id,
            ingestion_docs=sum(a.documents_processed for a in assets),
            signals_extracted=sum(a.signals_created for a in assets),
            valuations_updated=sum(a.valuation_diffs_persisted for a in assets),
            alerts_generated=len(scan.alerts_emitted),
            opportunities_detected=len(scan.opportunities),
            pipeline_failures=(
                sum(1 for a in assets if a.status == "failure")
                + (1 if scan_error is not None else 0)
                + (1 if cache_error is not None else 0)
            ),
            stage_metrics={
                "assets_total": len(assets),
                "assets_failed": sum(1 for a in assets if a.status == "failure"),
                "paused_stages": sorted(paused_stages),
                "assets_gated_data_quality": sum(1 for score in data_quality_scores if score.gated),
                "assets_scored_data_quality": len(data_quality_scores),
                "daily_ingestion_due": daily_ingestion_due,
                "daily_ingestion_executed": daily_ingestion_executed,
                "weekly_maintenance_due": weekly_maintenance_due,
                "weekly_maintenance_executed": weekly_maintenance_executed,
                "raw_documents_deleted": raw_documents_deleted,
            },
            stage_latencies=stage_latencies,
            connector_health=watchlist_summary.connector_health,
        )

    def _maybe_run_weekly_ranking_calibration(self, *, reference_time: datetime) -> None:
        # Sunday (weekday=6) post-run calibration.
        if reference_time.weekday() != 6:
            return
        run_date = reference_time.date().isoformat()
        if self._last_ranking_calibration_date == run_date:
            return
        try:
            calibrator = RankingCalibrator(self.runner.knowledge)
            report = calibrator.calibrate()
            if report.n_resolved_forecasts < self.config.ranking_calibration_min_resolved_forecasts:
                self._last_ranking_calibration_date = run_date
                self.logger.info(
                    "ranking_calibration_skipped run_date=%s n_resolved=%d min_required=%d",
                    report.run_date.isoformat(),
                    report.n_resolved_forecasts,
                    self.config.ranking_calibration_min_resolved_forecasts,
                )
                return
            calibrator.write_calibration(report)
            self._last_ranking_calibration_date = run_date
            self.logger.info(
                "ranking_calibration_updated run_date=%s n_resolved=%d drift_alerts=%d",
                report.run_date.isoformat(),
                report.n_resolved_forecasts,
                len(report.drift_alerts),
            )
        except Exception as exc:
            self.logger.warning("ranking_calibration_failed: %s", exc)

    def _maybe_run_weekly_event_impact_ledger(self, *, reference_time: datetime) -> None:
        # Sunday (weekday=6) post-run event impact ledger update.
        if reference_time.weekday() != 6:
            return
        run_date = reference_time.date().isoformat()
        if self._last_event_impact_ledger_date == run_date:
            return
        try:
            from bve.intelligence.event_impact_ledger import EventImpactLedger
            ledger = EventImpactLedger()
            scores = ledger.run(self.runner.knowledge)
            self._last_event_impact_ledger_date = run_date
            self.logger.info(
                "event_impact_ledger_updated run_date=%s n_scores=%d",
                run_date,
                len(scores),
            )
        except Exception as exc:
            self.logger.warning("event_impact_ledger_failed: %s", exc)

    def _maybe_run_weekly_pos_calibration(self, *, reference_time: datetime) -> None:
        # Sunday post-run PoS recalibration by (trial_phase × indication).
        if reference_time.weekday() != 6:
            return
        run_date = reference_time.date().isoformat()
        if self._last_pos_calibration_date == run_date:
            return
        try:
            from bve.analysis.pos_recalibrator import PoSRecalibrator
            calibrator = PoSRecalibrator(self.runner.knowledge)
            report = calibrator.calibrate()
            if report.n_resolved_forecasts > 0:
                calibrator.write_calibration(report)
            self._last_pos_calibration_date = run_date
            self.logger.info(
                "pos_calibration_updated run_date=%s n_forecasts=%d n_segments=%d drift_alerts=%d",
                run_date,
                report.n_resolved_forecasts,
                report.n_segments,
                len(report.drift_alerts),
            )
        except Exception as exc:
            self.logger.warning("pos_calibration_failed: %s", exc)

    def _maybe_run_weekly_kg_integrity(
        self,
        *,
        run_id: str,
        reference_time: datetime,
    ) -> None:
        last = self._last_kg_integrity_check_at
        interval_days = self.config.kg_integrity_check_interval_days
        if last is not None and (reference_time - last).total_seconds() < interval_days * 86400:
            return

        checker = KGIntegrityChecker(self.runner.knowledge)
        asset_ids = [asset.asset_id for asset in self.watchlist_config.watchlist]
        report = checker.check(asset_ids)
        self.runner.knowledge.log_kg_integrity(report)
        self._last_kg_integrity_check_at = reference_time

        if report.passed:
            self.logger.info(
                "kg_integrity_passed nodes=%d edges=%d missing_asset_nodes=%d",
                report.n_nodes,
                report.n_edges,
                len(report.missing_asset_nodes),
            )
            return

        self.logger.warning(
            "kg_integrity_failed orphan_edges=%d duplicate_nodes=%d invalid_confidence=%d",
            len(report.orphan_edges),
            len(report.duplicate_nodes),
            len(report.invalid_confidence),
        )
        router = getattr(self.runner, "alert_router", None)
        if router is None:
            return

        from bve.alerts.alert_model import AlertSeverity

        router.enqueue_system_alert(
            key="kg_integrity_failed",
            message=(
                "KG integrity check failed: "
                f"{len(report.orphan_edges)} orphan edges, "
                f"{len(report.duplicate_nodes)} duplicate nodes"
            ),
            detail={
                "orphan_edges": report.orphan_edges,
                "duplicate_nodes": report.duplicate_nodes,
                "invalid_confidence": report.invalid_confidence,
                "missing_asset_nodes": report.missing_asset_nodes,
            },
            run_id=run_id,
            asset_id="kg_integrity",
            severity=AlertSeverity.HIGH,
        )
        router.flush_all(run_id=run_id)
