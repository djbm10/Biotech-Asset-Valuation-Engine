"""Phase M continuous monitoring and daily scanning engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.ops.data_quality import DataQualityScore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContinuousMonitoringModuleOutput(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class MonitoringEvent(BaseModel):
    asset_id: str
    company_id: Optional[str] = None
    event_type: str
    occurred_at: datetime
    source: str = "system"
    payload: dict[str, Any] = Field(default_factory=dict)


class MonitoringJobStatus(BaseModel):
    job_name: str
    last_successful_at: Optional[datetime] = None
    cadence_hours: int = Field(ge=1, default=24)
    healthy: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)


class RecomputeInstruction(BaseModel):
    asset_id: str
    reason: str
    priority: str
    trigger_event_type: Optional[str] = None
    affected_by: list[str] = Field(default_factory=list)


class MaterialMonitoringAlert(BaseModel):
    asset_id: str
    alert_type: str
    severity: str
    message: str
    evidence: list[str] = Field(default_factory=list)


class ContinuousMonitoringValue(BaseModel):
    refreshed_assets: list[str] = Field(default_factory=list)
    recompute_queue: list[RecomputeInstruction] = Field(default_factory=list)
    material_alerts: list[MaterialMonitoringAlert] = Field(default_factory=list)
    stale_assets: list[str] = Field(default_factory=list)
    degraded_jobs: list[str] = Field(default_factory=list)


class ContinuousMonitoringAssessment(BaseModel):
    output: ContinuousMonitoringModuleOutput
    plain_english_summary: str


class ContinuousMonitoringEngine:
    """Plan daily refreshes and event-driven reruns for only affected assets."""

    _HIGH_PRIORITY_EVENTS = {
        "8k",
        "press_release",
        "trial_registry_change",
        "fda_action",
        "competitor_readout",
        "financing_announcement",
        "large_stock_move",
        "analyst_estimate_revision",
        "insider_sale",
        "insider_buy",
    }
    _ALERT_TYPE_MAP = {
        "financing_announcement": ("financing_risk_increased", "high"),
        "competitor_readout": ("competitor_threat_rose", "high"),
        "fda_action": ("thesis_broken", "critical"),
        "trial_registry_change": ("model_confidence_dropped", "medium"),
        "large_stock_move": ("material_upside_gap_opened", "medium"),
    }

    def build(
        self,
        *,
        asset_ids: list[str],
        recent_events: list[MonitoringEvent],
        job_statuses: list[MonitoringJobStatus],
        dependency_map: Optional[dict[str, list[str]]] = None,
        data_quality_scores: Optional[list[DataQualityScore]] = None,
        freshness: Optional[datetime] = None,
    ) -> ContinuousMonitoringAssessment:
        now = freshness or _utcnow()
        dependency_map = dependency_map or {}
        dq_by_asset = {score.asset_id: score for score in (data_quality_scores or [])}

        stale_assets = sorted(
            {
                asset_id
                for asset_id, score in dq_by_asset.items()
                if score.gated or "doc_freshness" in set(score.failing_checks)
            }
        )
        degraded_jobs = sorted(
            {
                job.job_name
                for job in job_statuses
                if self._job_degraded(job=job, reference_time=now)
            }
        )
        recompute_queue = self._build_recompute_queue(
            asset_ids=asset_ids,
            recent_events=recent_events,
            dependency_map=dependency_map,
            stale_assets=stale_assets,
        )
        refreshed_assets = sorted({item.asset_id for item in recompute_queue})
        alerts = self._build_alerts(
            recent_events=recent_events,
            stale_assets=stale_assets,
            degraded_jobs=degraded_jobs,
            dq_by_asset=dq_by_asset,
        )

        value = ContinuousMonitoringValue(
            refreshed_assets=refreshed_assets,
            recompute_queue=recompute_queue,
            material_alerts=alerts,
            stale_assets=stale_assets,
            degraded_jobs=degraded_jobs,
        )
        output = ContinuousMonitoringModuleOutput(
            value=value.model_dump(),
            confidence=self._confidence(job_statuses, dq_by_asset, alerts),
            provenance=self._provenance(job_statuses, recent_events),
            freshness=now,
            explainability=(
                "Continuous monitoring reruns only assets directly touched by new events, "
                "plus downstream dependencies and stale-input names, while emitting alerts only "
                "when the event type or data-quality state is material."
            ),
            downstream_dependencies=["calibration_feedback_loop", "operating_layer"],
        )
        summary = (
            f"Monitoring queued {len(recompute_queue)} recompute(s), flagged {len(alerts)} material "
            f"alert(s), and found {len(stale_assets)} stale asset(s)."
        )
        return ContinuousMonitoringAssessment(output=output, plain_english_summary=summary)

    def _build_recompute_queue(
        self,
        *,
        asset_ids: list[str],
        recent_events: list[MonitoringEvent],
        dependency_map: dict[str, list[str]],
        stale_assets: list[str],
    ) -> list[RecomputeInstruction]:
        queued: dict[str, RecomputeInstruction] = {}

        for event in sorted(recent_events, key=lambda item: item.occurred_at, reverse=True):
            affected_assets = [event.asset_id, *(dependency_map.get(event.asset_id) or [])]
            for affected_asset in affected_assets:
                if affected_asset not in asset_ids:
                    continue
                existing = queued.get(affected_asset)
                new_priority = (
                    "high" if event.event_type in self._HIGH_PRIORITY_EVENTS else "medium"
                )
                reason = (
                    "direct_event_refresh"
                    if affected_asset == event.asset_id
                    else "dependency_propagation"
                )
                trigger_ref = f"{event.event_type}:{event.asset_id}"
                if existing is None:
                    queued[affected_asset] = RecomputeInstruction(
                        asset_id=affected_asset,
                        reason=reason,
                        priority=new_priority,
                        trigger_event_type=event.event_type,
                        affected_by=[trigger_ref],
                    )
                else:
                    if new_priority == "high":
                        existing.priority = "high"
                    if reason == "direct_event_refresh":
                        existing.reason = reason
                    if trigger_ref not in existing.affected_by:
                        existing.affected_by.append(trigger_ref)

        for asset_id in stale_assets:
            if asset_id not in asset_ids:
                continue
            existing = queued.get(asset_id)
            if existing is None:
                queued[asset_id] = RecomputeInstruction(
                    asset_id=asset_id,
                    reason="stale_input_refresh",
                    priority="medium",
                    trigger_event_type=None,
                    affected_by=["data_quality:stale_input"],
                )
            elif "data_quality:stale_input" not in existing.affected_by:
                existing.affected_by.append("data_quality:stale_input")

        return sorted(
            queued.values(),
            key=lambda item: (0 if item.priority == "high" else 1, item.asset_id),
        )

    def _build_alerts(
        self,
        *,
        recent_events: list[MonitoringEvent],
        stale_assets: list[str],
        degraded_jobs: list[str],
        dq_by_asset: dict[str, DataQualityScore],
    ) -> list[MaterialMonitoringAlert]:
        alerts: list[MaterialMonitoringAlert] = []
        seen: set[tuple[str, str]] = set()

        for event in recent_events:
            mapped = self._ALERT_TYPE_MAP.get(event.event_type)
            if mapped is None:
                continue
            alert_type, severity = mapped
            key = (event.asset_id, alert_type)
            if key in seen:
                continue
            seen.add(key)
            alerts.append(
                MaterialMonitoringAlert(
                    asset_id=event.asset_id,
                    alert_type=alert_type,
                    severity=severity,
                    message=f"{event.asset_id} triggered {alert_type} via {event.event_type}.",
                    evidence=[f"source:{event.source}", f"event:{event.event_type}"],
                )
            )

        for asset_id in stale_assets:
            key = (asset_id, "model_confidence_dropped")
            if key in seen:
                continue
            score = dq_by_asset.get(asset_id)
            seen.add(key)
            alerts.append(
                MaterialMonitoringAlert(
                    asset_id=asset_id,
                    alert_type="model_confidence_dropped",
                    severity="medium",
                    message=f"{asset_id} has stale or gated inputs and should be refreshed.",
                    evidence=[
                        f"overall_score:{score.overall_score:.2f}" if score else "overall_score:unknown",
                        *(score.failing_checks if score else []),
                    ],
                )
            )

        for job_name in degraded_jobs:
            alerts.append(
                MaterialMonitoringAlert(
                    asset_id="system",
                    alert_type="job_health_degraded",
                    severity="medium",
                    message=f"Monitoring job {job_name} is stale or unhealthy.",
                    evidence=[f"job:{job_name}"],
                )
            )
        return alerts

    @staticmethod
    def _job_degraded(*, job: MonitoringJobStatus, reference_time: datetime) -> bool:
        if not job.healthy:
            return True
        if job.last_successful_at is None:
            return True
        return (reference_time - job.last_successful_at) > timedelta(hours=job.cadence_hours)

    @staticmethod
    def _provenance(
        job_statuses: list[MonitoringJobStatus],
        recent_events: list[MonitoringEvent],
    ) -> list[str]:
        provenance = [f"job:{job.job_name}" for job in job_statuses]
        provenance.extend(
            f"event:{event.event_type}:{event.asset_id}"
            for event in recent_events[:20]
        )
        return provenance

    @staticmethod
    def _confidence(
        job_statuses: list[MonitoringJobStatus],
        dq_by_asset: dict[str, DataQualityScore],
        alerts: list[MaterialMonitoringAlert],
    ) -> float:
        confidence = 0.60
        if job_statuses:
            healthy_ratio = sum(1 for job in job_statuses if job.healthy) / len(job_statuses)
            confidence += 0.20 * healthy_ratio
        if dq_by_asset:
            avg_quality = sum(score.overall_score for score in dq_by_asset.values()) / len(dq_by_asset)
            confidence += 0.15 * avg_quality
        confidence -= min(0.15, 0.02 * len(alerts))
        return round(max(0.40, min(0.95, confidence)), 4)
