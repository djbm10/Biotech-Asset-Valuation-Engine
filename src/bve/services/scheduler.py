"""Simple non-overlapping scheduler with file-lock protection."""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SchedulerConfig(BaseModel):
    """Runtime scheduling and lock behavior."""

    interval_seconds: int = Field(default=3600, ge=1)
    lock_path: str = "outputs/watchlist/intelligence_service.lock"
    stale_lock_seconds: int = Field(default=21600, ge=60)


class Scheduler:
    """Runs periodic jobs with a non-overlapping file lock."""

    def __init__(
        self,
        *,
        config: Optional[SchedulerConfig] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config or SchedulerConfig()
        self.logger = logger or logging.getLogger("bve.scheduler")
        self._lock_path = Path(self.config.lock_path)
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)

    def run_once(self, fn: Callable[[], None]) -> bool:
        """Run one cycle if lock acquisition succeeds; return whether executed."""
        with self._non_overlapping_lock() as acquired:
            if not acquired:
                return False
            fn()
            return True

    def run_forever(
        self,
        fn: Callable[[], None],
        *,
        max_cycles: Optional[int] = None,
    ) -> None:
        cycle = 0
        while True:
            cycle += 1
            executed = self.run_once(fn)
            self.logger.info(
                "scheduler_cycle cycle=%d executed=%s interval_seconds=%d",
                cycle,
                executed,
                self.config.interval_seconds,
            )
            if max_cycles is not None and cycle >= max_cycles:
                return
            time.sleep(self.config.interval_seconds)

    @contextmanager
    def _non_overlapping_lock(self) -> Iterator[bool]:
        fd: Optional[int] = None
        try:
            fd = os.open(
                str(self._lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
            payload = {
                "pid": os.getpid(),
                "acquired_at": _utcnow().isoformat(),
            }
            os.write(fd, json.dumps(payload, ensure_ascii=True).encode("utf-8"))
            os.fsync(fd)
            yield True
        except FileExistsError:
            if self._break_stale_lock_if_needed():
                with self._non_overlapping_lock() as reacquired:
                    yield reacquired
            else:
                self.logger.info("scheduler_lock_busy path=%s", self._lock_path)
                yield False
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                try:
                    self._lock_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _break_stale_lock_if_needed(self) -> bool:
        try:
            stat = self._lock_path.stat()
        except FileNotFoundError:
            return False
        age_seconds = _utcnow().timestamp() - stat.st_mtime
        if age_seconds < self.config.stale_lock_seconds:
            return False
        self.logger.warning(
            "scheduler_lock_stale_break path=%s age_seconds=%.1f",
            self._lock_path,
            age_seconds,
        )
        try:
            self._lock_path.unlink(missing_ok=True)
            return True
        except OSError:
            return False
