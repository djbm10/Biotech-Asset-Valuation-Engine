"""
Common raw-event schema for all ingestion clients.

Every client returns RawEvent instances — never free text.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator


class RawEvent(BaseModel):
    """
    Canonical container for a single record fetched from any data source.

    Fields
    ------
    source        : source system identifier (e.g. "sec_edgar", "ctgov", "openfda")
    record_type   : sub-type within the source (e.g. "10-K", "trial_update", "approval")
    source_url    : full URL of the resource that was fetched
    fetched_at    : UTC timestamp of when the fetch occurred
    checksum      : SHA-256 of the canonical JSON payload (for deduplication)
    payload       : raw parsed dict — no free text blobs at the top level
    entity_ids    : asset / company IDs this record pertains to (may be empty before resolution)
    """

    source: str
    record_type: str
    source_url: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    checksum: str = ""
    payload: dict[str, Any]
    entity_ids: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _compute_checksum(self) -> "RawEvent":
        if not self.checksum:
            raw = json.dumps(self.payload, sort_keys=True, default=str)
            digest = hashlib.sha256(raw.encode()).hexdigest()
            object.__setattr__(self, "checksum", digest)
        return self

    def dedup_key(self) -> str:
        """Stable key for deduplication: (source, record_type, checksum)."""
        return f"{self.source}:{self.record_type}:{self.checksum}"
