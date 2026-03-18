"""Continuous scheduler for the daily/weekly intelligence pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from bve.services.intelligence_service import IntelligenceService, IntelligenceServiceConfig
from bve.services.scheduler import Scheduler, SchedulerConfig


class PipelineSchedulerConfig(BaseModel):
    """Config for the operational daily/weekly pipeline scheduler."""

    watchlist_path: Optional[str] = None
    watchlist_dir: Optional[str] = None
    dashboard_cache_path: str = "outputs/dashboard/cache.json"
    control_state_path: str = "outputs/watchlist/service_control.json"
    metrics_path: str = "logs/run_metrics.json"
    scheduler: SchedulerConfig = Field(
        default_factory=lambda: SchedulerConfig(
            interval_seconds=3600,
            lock_path="outputs/watchlist/pipeline_scheduler.lock",
        )
    )

    @model_validator(mode="after")
    def _validate_watchlist_input(self) -> "PipelineSchedulerConfig":
        has_path = bool(self.watchlist_path)
        has_dir = bool(self.watchlist_dir)
        if has_path == has_dir:
            raise ValueError("Exactly one of watchlist_path or watchlist_dir must be set")
        return self


class PipelineScheduler:
    """Runs the scheduled daily/weekly pipeline in a non-overlapping loop."""

    def __init__(
        self,
        config: PipelineSchedulerConfig,
        *,
        service: Optional[IntelligenceService] = None,
        scheduler: Optional[Scheduler] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("bve.services.pipeline_scheduler")
        self.service = service or IntelligenceService(
            IntelligenceServiceConfig(
                watchlist_path=config.watchlist_path,
                watchlist_dir=config.watchlist_dir,
                dashboard_cache_path=config.dashboard_cache_path,
                control_state_path=config.control_state_path,
                metrics_path=config.metrics_path,
                scheduler=config.scheduler,
            )
        )
        self.scheduler = scheduler or Scheduler(config=config.scheduler, logger=self.logger)

    @classmethod
    def from_watchlist(
        cls,
        watchlist_path: str | Path,
        *,
        lock_path: str = "outputs/watchlist/pipeline_scheduler.lock",
        dashboard_cache_path: str = "outputs/dashboard/cache.json",
        control_state_path: str = "outputs/watchlist/service_control.json",
        metrics_path: str = "logs/run_metrics.json",
    ) -> "PipelineScheduler":
        return cls(
            PipelineSchedulerConfig(
                watchlist_path=str(watchlist_path),
                dashboard_cache_path=dashboard_cache_path,
                control_state_path=control_state_path,
                metrics_path=metrics_path,
                scheduler=SchedulerConfig(lock_path=lock_path),
            )
        )

    def run_once(self) -> bool:
        """Run one scheduled cycle if lock acquisition succeeds."""
        return self.scheduler.run_once(self.service.run_cycle)

    def run_forever(self, *, max_cycles: Optional[int] = None) -> None:
        """Run continuously using the configured polling interval."""
        self.scheduler.run_forever(self.service.run_cycle, max_cycles=max_cycles)

    def close(self) -> None:
        self.service.close()
