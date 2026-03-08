"""Persistent state for watchlist pipeline idempotency and scheduling."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class AssetPipelineState(BaseModel):
    """Per-asset pipeline state persisted across runs."""

    company_id: str
    asset_id: str
    processed_document_ids: list[str] = Field(default_factory=list)
    processed_event_ids: list[str] = Field(default_factory=list)
    last_fetch_by_source: dict[str, str] = Field(default_factory=dict)
    last_run_started_at: Optional[datetime] = None
    last_run_completed_at: Optional[datetime] = None
    last_error: Optional[str] = None


class PipelineStateSnapshot(BaseModel):
    """Top-level persisted pipeline state."""

    assets: dict[str, AssetPipelineState] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PipelineStateStore:
    """JSON-backed state store used by the watchlist runner."""

    def __init__(self, path: str | Path = "outputs/watchlist/pipeline_state.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot = self._load_snapshot()

    @staticmethod
    def asset_key(company_id: str, asset_id: str) -> str:
        return f"{company_id}::{asset_id}"

    @staticmethod
    def _coerce_datetime(value: Optional[str]) -> Optional[datetime]:
        if value is None:
            return None
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _load_snapshot(self) -> PipelineStateSnapshot:
        if not self.path.exists():
            return PipelineStateSnapshot()
        return PipelineStateSnapshot.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self._snapshot.updated_at = datetime.now(timezone.utc)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(self._snapshot.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get_asset_state(self, company_id: str, asset_id: str) -> AssetPipelineState:
        key = self.asset_key(company_id, asset_id)
        state = self._snapshot.assets.get(key)
        if state is None:
            state = AssetPipelineState(company_id=company_id, asset_id=asset_id)
            self._snapshot.assets[key] = state
        return state

    def seen_document(self, company_id: str, asset_id: str, document_id: str) -> bool:
        state = self.get_asset_state(company_id, asset_id)
        return document_id in state.processed_document_ids

    def seen_event(self, company_id: str, asset_id: str, event_id: str) -> bool:
        state = self.get_asset_state(company_id, asset_id)
        return event_id in state.processed_event_ids

    def mark_document_processed(self, company_id: str, asset_id: str, document_id: str) -> None:
        state = self.get_asset_state(company_id, asset_id)
        if document_id not in state.processed_document_ids:
            state.processed_document_ids.append(document_id)

    def mark_event_processed(self, company_id: str, asset_id: str, event_id: str) -> None:
        state = self.get_asset_state(company_id, asset_id)
        if event_id not in state.processed_event_ids:
            state.processed_event_ids.append(event_id)

    def get_since(self, company_id: str, asset_id: str, source: str) -> Optional[datetime]:
        state = self.get_asset_state(company_id, asset_id)
        return self._coerce_datetime(state.last_fetch_by_source.get(source))

    def set_last_fetch(self, company_id: str, asset_id: str, source: str, fetched_at: datetime) -> None:
        state = self.get_asset_state(company_id, asset_id)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        state.last_fetch_by_source[source] = fetched_at.isoformat()

    def mark_run_started(self, company_id: str, asset_id: str, started_at: Optional[datetime] = None) -> None:
        state = self.get_asset_state(company_id, asset_id)
        now = started_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        state.last_run_started_at = now
        state.last_error = None

    def mark_run_succeeded(self, company_id: str, asset_id: str, completed_at: Optional[datetime] = None) -> None:
        state = self.get_asset_state(company_id, asset_id)
        now = completed_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        state.last_run_completed_at = now
        state.last_error = None

    def mark_run_failed(
        self,
        company_id: str,
        asset_id: str,
        error: str,
        completed_at: Optional[datetime] = None,
    ) -> None:
        state = self.get_asset_state(company_id, asset_id)
        now = completed_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        state.last_run_completed_at = now
        state.last_error = error

    def model_dump(self) -> dict:
        return self._snapshot.model_dump(mode="json")

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=True, indent=2)
