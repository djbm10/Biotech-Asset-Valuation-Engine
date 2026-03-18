"""Small TTL-aware disk cache used by auto config generation."""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Optional

try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


class DiskCache:
    """JSON disk cache with namespace-specific TTLs and atomic writes."""

    def __init__(
        self,
        root: Path = Path("outputs/cache"),
        *,
        now_fn: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._thread_lock = threading.Lock()
        self.ttls: dict[str, timedelta] = {
            "ctgov": timedelta(days=7),
            "sec": timedelta(days=1),
            "market": timedelta(minutes=15),
        }

    def _now(self) -> datetime:
        now = self._now_fn()
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now

    @staticmethod
    def _validate_segment(value: str) -> str:
        if not value:
            raise ValueError("cache namespace/key cannot be empty")
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("cache namespace/key must be a relative safe path")
        return value

    def _cache_path(self, namespace: str, key: str) -> Path:
        ns = self._validate_segment(namespace)
        k = self._validate_segment(key)
        path = self.root / ns / k
        if path.suffix != ".json":
            path = path.with_suffix(".json")
        return path

    @contextmanager
    def _file_lock(self, path: Path):
        lock_path = path.with_suffix(path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        text = value
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def get(self, namespace: str, key: str) -> Optional[dict]:
        """Read a cached payload, returning None when missing or expired."""
        path = self._cache_path(namespace, key)
        with self._thread_lock:
            with self._file_lock(path):
                if not path.exists():
                    return None
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    return None

                fetched_at_raw = payload.get("fetched_at")
                data = payload.get("data")
                if fetched_at_raw is None or not isinstance(data, dict):
                    return None

                fetched_at = self._parse_dt(str(fetched_at_raw))
                ttl = self.ttls.get(namespace, timedelta(days=1))
                if (self._now() - fetched_at) > ttl:
                    return None
                return data

    def put(self, namespace: str, key: str, data: dict) -> None:
        """Atomically write a cached payload with fetched_at timestamp."""
        path = self._cache_path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "fetched_at": self._now().isoformat(),
            "data": data,
        }

        with self._thread_lock:
            with self._file_lock(path):
                with NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    delete=False,
                    dir=str(path.parent),
                    suffix=".tmp",
                ) as tmp:
                    json.dump(payload, tmp, ensure_ascii=True)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                    tmp_path = Path(tmp.name)

                os.replace(tmp_path, path)
