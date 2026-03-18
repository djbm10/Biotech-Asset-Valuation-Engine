"""Structured run-metrics persistence for pipeline observability."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunMetrics(BaseModel):
    run_id: str
    measured_at: datetime = Field(default_factory=_utcnow)
    ingestion_docs: int = 0
    signals_extracted: int = 0
    valuations_updated: int = 0
    alerts_generated: int = 0
    opportunities_detected: int = 0
    pipeline_failures: int = 0
    stage_metrics: dict[str, Any] = Field(default_factory=dict)
    stage_latencies: list["StageLatencyMetrics"] = Field(default_factory=list)
    connector_health: list["ConnectorHealthMetrics"] = Field(default_factory=list)


class ConnectorHealthMetrics(BaseModel):
    connector: str
    success_rate: float = Field(ge=0.0, le=1.0)
    error_rate: float = Field(ge=0.0, le=1.0)
    avg_latency_ms: float = Field(ge=0.0)
    n_runs_sampled: int = Field(ge=0)
    last_failure_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    health_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    healthy: bool


class StageLatencyMetrics(BaseModel):
    stage: str
    avg_ms: float = Field(ge=0.0)
    p50_ms: float = Field(ge=0.0)
    p95_ms: float = Field(ge=0.0)
    p99_ms: float = Field(ge=0.0)
    n_observations: int = Field(ge=0)


class RunMetricsStore:
    """Append-only JSON metrics file at logs/run_metrics.json."""

    def __init__(self, path: str | Path = "logs/run_metrics.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, metrics: RunMetrics) -> None:
        current = self.load_all()
        current.append(metrics)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps([m.model_dump(mode="json") for m in current], ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def load_all(self) -> list[RunMetrics]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [RunMetrics.model_validate(item) for item in raw]

    def latest(self) -> Optional[RunMetrics]:
        rows = self.load_all()
        if not rows:
            return None
        return rows[-1]
