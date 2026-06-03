"""
Simple operational loop scheduler (no threading — tick-based for testability).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"   # ran too recently (within interval)


@dataclass
class ScheduledJob:
    job_id: str
    name: str
    fn: Callable[[], None]
    interval_seconds: int
    last_run: datetime | None = None
    last_status: JobStatus = JobStatus.PENDING
    run_count: int = 0
    error_count: int = 0


@dataclass
class JobResult:
    job_id: str
    status: JobStatus
    ran_at: datetime
    error: str | None = None


class Scheduler:
    """
    Tick-based scheduler. Call tick(now) to advance time and run due jobs.
    A job is due if: last_run is None OR (now - last_run).seconds >= interval_seconds.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob] = {}

    def register(self, job: ScheduledJob) -> None:
        """Register a job with the scheduler."""
        self._jobs[job.job_id] = job

    def tick(self, now: datetime | None = None) -> list[JobResult]:
        """
        Run all due jobs. Catches exceptions → marks FAILED, increments error_count.
        Returns list of JobResult for jobs that ran (due jobs only).
        Non-due jobs are silently skipped (not included in results).
        """
        if now is None:
            now = datetime.now(timezone.utc)

        results: list[JobResult] = []

        for job in self._jobs.values():
            # Check if job is due
            if job.last_run is not None:
                elapsed = (now - job.last_run).total_seconds()
                if elapsed < job.interval_seconds:
                    # Not due — skip silently
                    continue

            # Job is due — run it
            job.last_status = JobStatus.RUNNING
            try:
                job.fn()
                job.last_run = now
                job.run_count += 1
                job.last_status = JobStatus.COMPLETED
                results.append(JobResult(
                    job_id=job.job_id,
                    status=JobStatus.COMPLETED,
                    ran_at=now,
                ))
            except Exception as exc:  # noqa: BLE001
                job.last_run = now
                job.error_count += 1
                job.last_status = JobStatus.FAILED
                results.append(JobResult(
                    job_id=job.job_id,
                    status=JobStatus.FAILED,
                    ran_at=now,
                    error=str(exc),
                ))

        return results

    def job_status(self, job_id: str) -> ScheduledJob:
        """Return the ScheduledJob for a given job_id."""
        if job_id not in self._jobs:
            raise KeyError(f"Unknown job_id: {job_id!r}")
        return self._jobs[job_id]

    def all_jobs(self) -> list[ScheduledJob]:
        """Return all registered jobs."""
        return list(self._jobs.values())

    def reset_job(self, job_id: str) -> None:
        """Set last_run=None so job runs on next tick."""
        if job_id not in self._jobs:
            raise KeyError(f"Unknown job_id: {job_id!r}")
        self._jobs[job_id].last_run = None
