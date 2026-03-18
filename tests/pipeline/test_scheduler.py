from __future__ import annotations

import os
from pathlib import Path

from bve.services.scheduler import Scheduler, SchedulerConfig


def test_scheduler_run_once_executes_with_lock(tmp_path: Path):
    lock_path = tmp_path / "lockfile.lock"
    scheduler = Scheduler(config=SchedulerConfig(interval_seconds=1, lock_path=str(lock_path)))
    calls = {"n": 0}

    def _job() -> None:
        calls["n"] += 1

    executed = scheduler.run_once(_job)
    assert executed is True
    assert calls["n"] == 1
    assert not lock_path.exists()


def test_scheduler_skips_when_lock_is_active(tmp_path: Path):
    lock_path = tmp_path / "active.lock"
    lock_path.write_text("busy", encoding="utf-8")
    scheduler = Scheduler(
        config=SchedulerConfig(
            interval_seconds=1,
            lock_path=str(lock_path),
            stale_lock_seconds=3600,
        )
    )
    executed = scheduler.run_once(lambda: None)
    assert executed is False


def test_scheduler_breaks_stale_lock(tmp_path: Path):
    lock_path = tmp_path / "stale.lock"
    lock_path.write_text("stale", encoding="utf-8")
    old = lock_path.stat().st_mtime - 7200
    os.utime(lock_path, times=(old, old))
    scheduler = Scheduler(
        config=SchedulerConfig(
            interval_seconds=1,
            lock_path=str(lock_path),
            stale_lock_seconds=60,
        )
    )
    calls = {"n": 0}
    executed = scheduler.run_once(lambda: calls.__setitem__("n", calls["n"] + 1))
    assert executed is True
    assert calls["n"] == 1
