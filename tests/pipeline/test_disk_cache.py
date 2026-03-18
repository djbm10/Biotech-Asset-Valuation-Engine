from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bve.pipeline.disk_cache import DiskCache


def test_disk_cache_put_get_within_ttl(tmp_path: Path) -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    cache = DiskCache(root=tmp_path / "cache", now_fn=lambda: now)

    cache.put("ctgov", "NCT123", {"phase": "phase_3"})
    out = cache.get("ctgov", "NCT123")

    assert out == {"phase": "phase_3"}


def test_disk_cache_get_returns_none_after_ttl(tmp_path: Path) -> None:
    current = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)

    def _now() -> datetime:
        return current

    cache = DiskCache(root=tmp_path / "cache", now_fn=_now)
    cache.put("market", "VRTX", {"market_cap_millions": 125000.0})

    current = current + timedelta(minutes=16)
    out = cache.get("market", "VRTX")

    assert out is None


def test_disk_cache_atomic_replace_handles_concurrent_writes(tmp_path: Path) -> None:
    cache = DiskCache(root=tmp_path / "cache")

    def _writer(writer_id: int) -> None:
        for index in range(40):
            cache.put("sec", "ALNY_2025Q4", {"writer": writer_id, "index": index})

    threads = [threading.Thread(target=_writer, args=(idx,)) for idx in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    out = cache.get("sec", "ALNY_2025Q4")
    assert isinstance(out, dict)
    assert "writer" in out
    assert "index" in out
