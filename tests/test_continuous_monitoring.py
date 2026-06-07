from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bve.intelligence.continuous_monitoring import (
    ContinuousMonitoringEngine,
    ContinuousMonitoringValue,
    MonitoringEvent,
    MonitoringJobStatus,
)
from bve.ops.data_quality import DataQualityCheck, DataQualityScore


def _score(
    asset_id: str,
    *,
    overall: float,
    failing: list[str],
    gated: bool,
) -> DataQualityScore:
    return DataQualityScore(
        asset_id=asset_id,
        overall_score=overall,
        checks=[
            DataQualityCheck(
                check_type="doc_freshness",
                asset_id=asset_id,
                value=5.0 if "doc_freshness" in failing else 1.0,
                threshold="<=3d",
                passed="doc_freshness" not in failing,
                severity="warning",
                reason="stale_source_documents" if "doc_freshness" in failing else "ok",
            )
        ],
        failing_checks=failing,
        gated=gated,
        generated_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )


def test_phase_m_builds_recompute_queue_from_events_dependencies_and_staleness() -> None:
    now = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    assessment = ContinuousMonitoringEngine().build(
        asset_ids=["asset-a", "asset-b", "asset-c"],
        recent_events=[
            MonitoringEvent(
                asset_id="asset-a",
                company_id="company-a",
                event_type="competitor_readout",
                occurred_at=now - timedelta(hours=2),
                source="press_release",
            ),
            MonitoringEvent(
                asset_id="asset-c",
                company_id="company-c",
                event_type="large_stock_move",
                occurred_at=now - timedelta(hours=1),
                source="market_data",
            ),
        ],
        job_statuses=[
            MonitoringJobStatus(
                job_name="daily_refresh",
                last_successful_at=now - timedelta(hours=4),
                cadence_hours=24,
                healthy=True,
            ),
            MonitoringJobStatus(
                job_name="catalyst_calendar_refresh",
                last_successful_at=now - timedelta(hours=30),
                cadence_hours=24,
                healthy=True,
            ),
        ],
        dependency_map={"asset-a": ["asset-b"]},
        data_quality_scores=[
            _score("asset-a", overall=0.8, failing=[], gated=False),
            _score("asset-b", overall=0.45, failing=["doc_freshness"], gated=True),
            _score("asset-c", overall=0.9, failing=[], gated=False),
        ],
        freshness=now,
    )

    value = ContinuousMonitoringValue.model_validate(assessment.output.value)
    assert value.refreshed_assets == ["asset-a", "asset-b", "asset-c"]
    assert len(value.recompute_queue) == 3
    assert value.recompute_queue[0].asset_id == "asset-a"
    assert value.recompute_queue[0].priority == "high"
    asset_b = next(item for item in value.recompute_queue if item.asset_id == "asset-b")
    assert asset_b.reason == "dependency_propagation"
    assert "data_quality:stale_input" in asset_b.affected_by
    assert "asset-b" in value.stale_assets
    assert "catalyst_calendar_refresh" in value.degraded_jobs
    assert any(alert.alert_type == "competitor_threat_rose" for alert in value.material_alerts)
    assert any(alert.alert_type == "job_health_degraded" for alert in value.material_alerts)
    assert "operating_layer" in assessment.output.downstream_dependencies


def test_phase_m_confidence_falls_with_unhealthy_jobs_and_many_alerts() -> None:
    now = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    assessment = ContinuousMonitoringEngine().build(
        asset_ids=["asset-a"],
        recent_events=[
            MonitoringEvent(
                asset_id="asset-a",
                company_id="company-a",
                event_type="fda_action",
                occurred_at=now,
                source="fda",
            )
        ],
        job_statuses=[
            MonitoringJobStatus(
                job_name="daily_refresh",
                last_successful_at=None,
                cadence_hours=24,
                healthy=False,
            )
        ],
        dependency_map={},
        data_quality_scores=[_score("asset-a", overall=0.3, failing=["doc_freshness"], gated=True)],
        freshness=now,
    )
    value = ContinuousMonitoringValue.model_validate(assessment.output.value)

    assert assessment.output.confidence < 0.75
    assert value.material_alerts
    assert any(alert.alert_type == "thesis_broken" for alert in value.material_alerts)
    assert any(alert.asset_id == "system" for alert in value.material_alerts)
