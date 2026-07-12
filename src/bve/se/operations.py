"""Production audit, monitoring, and revalidation controls for the S&E workflow."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from bve.se.acquisition.source_health import SourceHealthReport
from bve.se.evaluation.production_inference import QueryPrediction


PRODUCTION_SCREEN_LABEL = (
    "Production-validated public-data S&E screen; pre-diligence—not verified truth."
)


class SEAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    occurred_at: datetime
    code_version: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    specification_hash: str = Field(min_length=64, max_length=64)
    source_configuration_hash: str = Field(min_length=64, max_length=64)
    details: dict[str, object] = Field(default_factory=dict)


def append_audit_event(path: Path, event: SEAuditEvent) -> None:
    """Append and fsync one immutable JSONL audit event."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(event.model_dump_json() + "\n")
        handle.flush()
        os.fsync(handle.fileno())


class SEMonitoringBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unknown_rate: float = Field(ge=0.0, le=1.0)
    citation_failure_rate: float = Field(ge=0.0, le=1.0)
    source_failure_rate: float = Field(ge=0.0, le=1.0)
    max_absolute_rate_drift: float = Field(default=0.10, ge=0.0, le=1.0)


class SEMonitoringSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    observed_at: datetime
    query_count: int = Field(ge=0)
    candidate_route_count: int = Field(ge=0)
    unknown_rate: float = Field(ge=0.0, le=1.0)
    citation_failure_rate: float = Field(ge=0.0, le=1.0)
    source_failure_rate: float = Field(ge=0.0, le=1.0)
    route_leakage_count: int = Field(ge=0)
    performance_drift: bool
    alerts: list[str] = Field(default_factory=list)


def build_monitoring_snapshot(
    *,
    run_id: str,
    predictions: list[QueryPrediction],
    source_health: SourceHealthReport,
    baseline: SEMonitoringBaseline,
) -> SEMonitoringSnapshot:
    route_count = 0
    unknown_count = 0
    ranked_count = 0
    citation_failures = 0
    route_leakage = 0
    for prediction in predictions:
        queue_ids = [item.asset_id for item in prediction.diligence_queue]
        routes = prediction.ranked_asset_ids + queue_ids + prediction.excluded_asset_ids
        route_count += len(routes)
        unknown_count += len(queue_ids)
        ranked_count += len(prediction.ranked_asset_ids)
        citation_failures += sum(
            not prediction.citations_by_asset.get(asset)
            for asset in prediction.ranked_asset_ids
        )
        if (
            len(routes) != len(set(routes))
            or queue_ids != prediction.diligence_asset_ids
        ):
            route_leakage += 1
    source_count = len(source_health.sources)
    source_failures = sum(
        not source.connector_succeeded
        or not source.query_returned_results
        or source.documents_indexed <= 0
        for source in source_health.sources
    )
    unknown_rate = unknown_count / route_count if route_count else 0.0
    citation_failure_rate = citation_failures / ranked_count if ranked_count else 0.0
    source_failure_rate = source_failures / source_count if source_count else 1.0
    drifts = {
        "unknown_rate": abs(unknown_rate - baseline.unknown_rate),
        "citation_failure_rate": abs(
            citation_failure_rate - baseline.citation_failure_rate
        ),
        "source_failure_rate": abs(source_failure_rate - baseline.source_failure_rate),
    }
    alerts = [
        f"{metric} drift {value:.4f} exceeds {baseline.max_absolute_rate_drift:.4f}"
        for metric, value in drifts.items()
        if value > baseline.max_absolute_rate_drift
    ]
    if route_leakage:
        alerts.append(f"semantic route leakage detected in {route_leakage} queries")
    return SEMonitoringSnapshot(
        run_id=run_id,
        observed_at=datetime.now(timezone.utc),
        query_count=len(predictions),
        candidate_route_count=route_count,
        unknown_rate=unknown_rate,
        citation_failure_rate=citation_failure_rate,
        source_failure_rate=source_failure_rate,
        route_leakage_count=route_leakage,
        performance_drift=bool(alerts),
        alerts=alerts,
    )


class RevalidationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validated_code_hash: str = Field(min_length=64, max_length=64)
    validated_rubric_hash: str = Field(min_length=64, max_length=64)
    validated_source_configuration_hash: str = Field(min_length=64, max_length=64)
    validated_on: date
    interval_days: int = Field(default=180, ge=1)

    def reasons_required(
        self,
        *,
        current_code_hash: str,
        current_rubric_hash: str,
        current_source_configuration_hash: str,
        as_of: date | None = None,
    ) -> list[str]:
        reasons: list[str] = []
        if current_code_hash != self.validated_code_hash:
            reasons.append("material code hash changed")
        if current_rubric_hash != self.validated_rubric_hash:
            reasons.append("rubric hash changed")
        if current_source_configuration_hash != self.validated_source_configuration_hash:
            reasons.append("public source configuration changed")
        deadline = self.validated_on + timedelta(days=self.interval_days)
        if (as_of or date.today()) >= deadline:
            reasons.append("periodic public-source revalidation is due")
        return reasons

    def require_current(self, **current: str | date) -> None:
        reasons = self.reasons_required(**current)
        if reasons:
            raise RuntimeError("S&E production revalidation required: " + "; ".join(reasons))


def write_monitoring_snapshot(path: Path, snapshot: SEMonitoringSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
