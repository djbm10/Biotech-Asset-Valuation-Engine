"""Versioned dashboard cache artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DashboardCacheMetadata(BaseModel):
    """
    Dashboard cache metadata contract.

    Required fields:
      - cache_version
      - source_run_id
      - source_model_version
      - generated_at
    """

    cache_version: str
    source_run_id: str
    source_model_version: str
    generated_at: datetime


class DashboardCacheRecord(BaseModel):
    """Persisted dashboard cache payload."""

    metadata: DashboardCacheMetadata
    payload: dict[str, Any]


class DashboardCacheStore:
    """JSON-backed dashboard cache store."""

    def __init__(self, path: str | Path = "outputs/dashboard/cache.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> Optional[DashboardCacheRecord]:
        if not self.path.exists():
            return None
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return DashboardCacheRecord.model_validate(raw)

    def write(
        self,
        *,
        source_run_id: str,
        source_model_version: str,
        payload: dict[str, Any],
        generated_at: Optional[datetime] = None,
    ) -> DashboardCacheRecord:
        generated_at = generated_at or _utcnow()
        cache_version = self._next_cache_version()
        record = DashboardCacheRecord(
            metadata=DashboardCacheMetadata(
                cache_version=cache_version,
                source_run_id=source_run_id,
                source_model_version=source_model_version,
                generated_at=generated_at,
            ),
            payload=payload,
        )
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.path)
        return record

    def _next_cache_version(self) -> str:
        existing = self.read()
        if existing is None:
            return "1"
        prev = existing.metadata.cache_version
        try:
            return str(int(prev) + 1)
        except (TypeError, ValueError):
            return f"{prev}.1"
