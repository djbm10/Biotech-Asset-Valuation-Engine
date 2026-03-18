"""Unified connector rate limiter."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RateLimitPolicy:
    min_interval_seconds: float


class ServiceRateLimiter:
    """Per-source min-interval limiter for connector calls."""

    def __init__(
        self,
        policies: Optional[dict[str, RateLimitPolicy]] = None,
    ) -> None:
        self.policies = policies or {
            "fda_website": RateLimitPolicy(min_interval_seconds=1.0),
            "clinicaltrials_gov": RateLimitPolicy(min_interval_seconds=0.5),
            "pubmed": RateLimitPolicy(min_interval_seconds=0.4),
            "sec_filing": RateLimitPolicy(min_interval_seconds=1.0),
            "press_release": RateLimitPolicy(min_interval_seconds=0.2),
        }
        self._lock = threading.Lock()
        self._last_call: dict[str, float] = {}

    def wait(self, source: str) -> None:
        policy = self.policies.get(source)
        if policy is None:
            return
        with self._lock:
            now = time.monotonic()
            last = self._last_call.get(source)
            if last is not None:
                remaining = policy.min_interval_seconds - (now - last)
                if remaining > 0:
                    time.sleep(remaining)
                    now = time.monotonic()
            self._last_call[source] = now
