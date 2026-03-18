from __future__ import annotations

from pathlib import Path

import pytest

from bve.services.pipeline_scheduler import PipelineScheduler, PipelineSchedulerConfig


class _FakeService:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    def run_cycle(self) -> None:
        self.calls += 1

    def close(self) -> None:
        self.closed = True


def test_pipeline_scheduler_run_once_executes_service_cycle(tmp_path: Path) -> None:
    service = _FakeService()
    scheduler = PipelineScheduler(
        PipelineSchedulerConfig(
            watchlist_path="watchlist.yaml",
            scheduler={
                "interval_seconds": 1,
                "lock_path": str(tmp_path / "pipeline_scheduler.lock"),
            },
        ),
        service=service,  # type: ignore[arg-type]
    )
    try:
        executed = scheduler.run_once()
        assert executed is True
        assert service.calls == 1
    finally:
        scheduler.close()

    assert service.closed is True


def test_pipeline_scheduler_config_requires_exactly_one_watchlist_input() -> None:
    cfg = PipelineSchedulerConfig(watchlist_path="watchlist.yaml")
    assert cfg.watchlist_path == "watchlist.yaml"

    with pytest.raises(Exception):
        PipelineSchedulerConfig(
            watchlist_path="watchlist.yaml",
            watchlist_dir="watchlists/",
        )
