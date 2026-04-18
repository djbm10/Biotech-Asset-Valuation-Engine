"""Build recompute queues from routed events, prioritizing by materiality and staleness."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.pipeline.event_router import RoutedEvent


_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class RecomputeJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    ticker: str
    module: str
    priority: str = "medium"  # "high" / "medium" / "low"
    triggered_by_event_id: Optional[str] = None
    materiality_score: float = 0.5
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "pending"  # "pending" / "running" / "done" / "skipped"


class RecomputeQueue(BaseModel):
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    jobs: list[RecomputeJob]
    total_count: int
    high_priority_count: int
    asset_ids_affected: list[str]


def _materiality_to_priority(materiality_score: float) -> str:
    if materiality_score >= 0.8:
        return "high"
    if materiality_score >= 0.5:
        return "medium"
    return "low"


class ModelTriggerEngine:
    """Convert routed events into a prioritized recompute queue."""

    def build_queue(self, routed_events: list[RoutedEvent]) -> RecomputeQueue:
        """
        For each routed event binding, create one RecomputeJob per module.
        Priority: materiality >= 0.8 → high, >= 0.5 → medium, else low.
        Deduplicate: one job per (asset_id, module) — keep highest priority.
        Sort: high first, then medium, then low.
        """
        # Map of (asset_id, module) → best job so far
        best_jobs: dict[tuple[str, str], RecomputeJob] = {}

        for routed in routed_events:
            event_id = routed.classified_event.event_id
            for binding in routed.bindings:
                priority = _materiality_to_priority(binding.materiality_score)
                for module in routed.modules_to_recompute:
                    key = (binding.asset_id, module)
                    candidate = RecomputeJob(
                        asset_id=binding.asset_id,
                        ticker=binding.ticker,
                        module=module,
                        priority=priority,
                        triggered_by_event_id=event_id,
                        materiality_score=binding.materiality_score,
                    )
                    existing = best_jobs.get(key)
                    if existing is None:
                        best_jobs[key] = candidate
                    else:
                        # Keep highest priority (lower order number = higher priority)
                        if _PRIORITY_ORDER[priority] < _PRIORITY_ORDER[existing.priority]:
                            best_jobs[key] = candidate

        jobs = sorted(
            best_jobs.values(),
            key=lambda j: (_PRIORITY_ORDER[j.priority], j.asset_id, j.module),
        )

        asset_ids_affected = sorted({j.asset_id for j in jobs})
        high_priority_count = sum(1 for j in jobs if j.priority == "high")

        return RecomputeQueue(
            jobs=jobs,
            total_count=len(jobs),
            high_priority_count=high_priority_count,
            asset_ids_affected=asset_ids_affected,
        )
