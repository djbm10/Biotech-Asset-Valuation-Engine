from __future__ import annotations

import time

from bve.services.rate_limiter import RateLimitPolicy, ServiceRateLimiter


def test_rate_limiter_enforces_min_interval():
    limiter = ServiceRateLimiter(
        policies={"pubmed": RateLimitPolicy(min_interval_seconds=0.05)}
    )
    t0 = time.monotonic()
    limiter.wait("pubmed")
    limiter.wait("pubmed")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.045
