"""
Polls ingestion sources and emits RawEvent records.
No live HTTP in tests — designed for dependency injection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from bve.ingestion.raw_event import RawEvent


class SourceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"   # last fetch had errors but partially succeeded
    DOWN = "down"           # last fetch completely failed


@dataclass
class SourceHealth:
    source_name: str
    status: SourceStatus
    last_checked: datetime
    consecutive_failures: int = 0
    last_error: str | None = None


@dataclass
class MonitorConfig:
    sources: list[str]                  # e.g. ["sec", "ctgov", "news", "fda"]
    poll_interval_seconds: int = 300    # 5 minutes default
    max_consecutive_failures: int = 3   # mark DOWN after this many


class NewsMonitor:
    """
    Polls registered fetch functions, deduplicates by RawEvent.dedup_key(),
    and delivers new events to registered handlers.
    """

    def __init__(self, config: MonitorConfig) -> None:
        self._config = config
        self._fetchers: dict[str, Callable[[], list[RawEvent]]] = {}
        self._handlers: list[Callable[[RawEvent], None]] = []
        self._seen: set[str] = set()
        self._health: dict[str, SourceHealth] = {
            source: SourceHealth(
                source_name=source,
                status=SourceStatus.HEALTHY,
                last_checked=datetime.now(timezone.utc),
            )
            for source in config.sources
        }

    def register_fetcher(
        self,
        source_name: str,
        fetch_fn: Callable[[], list[RawEvent]],
    ) -> None:
        """Register a fetch function for a named source."""
        self._fetchers[source_name] = fetch_fn
        # Ensure health entry exists for this source
        if source_name not in self._health:
            self._health[source_name] = SourceHealth(
                source_name=source_name,
                status=SourceStatus.HEALTHY,
                last_checked=datetime.now(timezone.utc),
            )

    def register_handler(
        self,
        handler_fn: Callable[[RawEvent], None],
    ) -> None:
        """Register a callback to receive new (non-duplicate) events."""
        self._handlers.append(handler_fn)

    def poll(self, source_name: str | None = None) -> dict[str, int]:
        """
        Poll one or all sources. For each fetched RawEvent:
        - Skip if dedup_key() already seen (in-memory set)
        - Call all handlers with the new event
        - Update source health
        Returns: {source_name: new_event_count}
        """
        sources_to_poll: list[str]
        if source_name is not None:
            sources_to_poll = [source_name]
        else:
            sources_to_poll = list(self._fetchers.keys())

        results: dict[str, int] = {}

        for src in sources_to_poll:
            fetch_fn = self._fetchers.get(src)
            if fetch_fn is None:
                results[src] = 0
                continue

            now = datetime.now(timezone.utc)
            try:
                events = fetch_fn()
                new_count = 0
                for event in events:
                    key = event.dedup_key()
                    if key not in self._seen:
                        self._seen.add(key)
                        new_count += 1
                        for handler in self._handlers:
                            handler(event)

                # Update health: success resets consecutive_failures
                health = self._health.get(src)
                if health is None:
                    health = SourceHealth(
                        source_name=src,
                        status=SourceStatus.HEALTHY,
                        last_checked=now,
                    )
                    self._health[src] = health
                health.consecutive_failures = 0
                health.status = SourceStatus.HEALTHY
                health.last_checked = now
                health.last_error = None

                results[src] = new_count

            except Exception as exc:  # noqa: BLE001
                health = self._health.get(src)
                if health is None:
                    health = SourceHealth(
                        source_name=src,
                        status=SourceStatus.DEGRADED,
                        last_checked=now,
                        consecutive_failures=1,
                        last_error=str(exc),
                    )
                    self._health[src] = health
                else:
                    health.consecutive_failures += 1
                    health.last_checked = now
                    health.last_error = str(exc)
                    if health.consecutive_failures >= self._config.max_consecutive_failures:
                        health.status = SourceStatus.DOWN
                    else:
                        health.status = SourceStatus.DEGRADED

                results[src] = 0

        return results

    def source_health(self, source_name: str) -> SourceHealth:
        """Return health for a specific source."""
        if source_name not in self._health:
            raise KeyError(f"Unknown source: {source_name!r}")
        return self._health[source_name]

    def all_health(self) -> dict[str, SourceHealth]:
        """Return health for all sources."""
        return dict(self._health)

    def seen_count(self) -> int:
        """Total deduplicated events seen."""
        return len(self._seen)

    def reset_seen(self) -> None:
        """Clear dedup set (for testing)."""
        self._seen.clear()
