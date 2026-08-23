"""Stage-level progress and provenance counters for a landscape run.

A long S&E run used to be opaque: the process either finished or it did not, and
deciding whether a five-hour run was hung, silently re-fetching, or merely slow meant
attaching a profiler, reading socket byte counters and comparing snapshot mtimes. The
counters here are the cheap answer to the same questions -- how much has each stage
seen, how much of it came off disk rather than the wire, and how long it took.

Emission is opt-in. A library caller that passes no emitter gets the recorded stages
back as data and prints nothing.
"""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator, Sequence

from bve.se.schemas.contracts import SearchAttempt


@dataclass
class StageRecord:
    """What one stage saw and what it cost."""

    name: str
    counters: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    failed: bool = False

    def count(self, **counters: int) -> None:
        """Add to this stage's counters. Repeated calls accumulate."""

        for key, value in counters.items():
            self.counters[key] = self.counters.get(key, 0) + value

    def render(self) -> str:
        parts = [f"{value} {key.replace('_', ' ')}" for key, value in self.counters.items()]
        if self.failed:
            parts.append("failed")
        parts.append(f"{self.seconds:.1f}s")
        return f"{self.name}: " + " | ".join(parts)


class StageTelemetry:
    """Records stages, and optionally reports each one as it closes."""

    def __init__(self, emit: Callable[[str], None] | None = None) -> None:
        self.emit = emit
        self.stages: list[StageRecord] = []

    @contextmanager
    def stage(self, name: str) -> Iterator[StageRecord]:
        record = StageRecord(name=name)
        self.stages.append(record)
        started = time.monotonic()
        try:
            yield record
        except BaseException:
            # The run that fails is the one whose progress matters most; report the
            # partial counters rather than losing them with the exception.
            record.failed = True
            raise
        finally:
            record.seconds = time.monotonic() - started
            if self.emit is not None:
                self.emit(record.render())


def stderr_emitter(line: str) -> None:
    """Progress belongs on stderr, so it never contaminates a JSON result on stdout."""

    print(line, file=sys.stderr, flush=True)


def summarize_attempts(attempts: Sequence[SearchAttempt]) -> dict[str, dict[str, int]]:
    """Per-source discovery counters, derived from the attempts the run already records.

    ``records`` counts *distinct* snapshot ids. Summing the per-query snapshot lists
    would count a trial once per query that retrieved it, which is the same double
    counting that made a 2,908-trial corpus look an order of magnitude larger.
    """

    summary: dict[str, dict[str, int]] = {}
    snapshots_by_source: dict[str, set[str]] = {}
    for attempt in attempts:
        bucket = summary.setdefault(
            attempt.source,
            {"queries": 0, "candidates": 0, "unique_candidates": 0, "records": 0, "failed": 0},
        )
        bucket["queries"] += 1
        bucket["candidates"] += attempt.candidates_found
        bucket["unique_candidates"] += attempt.unique_candidates_added
        if attempt.error is not None:
            bucket["failed"] += 1
        snapshots_by_source.setdefault(attempt.source, set()).update(attempt.snapshot_ids)
    for source, snapshots in snapshots_by_source.items():
        summary[source]["records"] = len(snapshots)
    return summary
