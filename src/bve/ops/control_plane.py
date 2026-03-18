"""Service control-plane state for start/stop/pause/resume operations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_STAGE_ALIASES: dict[str, str] = {
    "ingestion": "watchlist",
    "pipeline": "watchlist",
    "valuation": "watchlist",
    "propagation": "watchlist",
    "scanner": "opportunity_scan",
    "opportunities": "opportunity_scan",
    "dashboard": "dashboard_cache",
    "cache": "dashboard_cache",
}


class ServiceControlState(BaseModel):
    stop_requested: bool = False
    paused_stages: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=_utcnow)


class ServiceControlPlane:
    """JSON-backed control plane for runtime operations."""

    def __init__(self, path: str | Path = "outputs/watchlist/service_control.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def canonical_stage(stage: str) -> str:
        return _STAGE_ALIASES.get(stage.strip().lower(), stage.strip())

    def load(self) -> ServiceControlState:
        if not self.path.exists():
            return ServiceControlState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return ServiceControlState.model_validate(raw)

    def save(self, state: ServiceControlState) -> ServiceControlState:
        state = state.model_copy(update={"updated_at": _utcnow()})
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.path)
        return state

    def request_stop(self) -> ServiceControlState:
        state = self.load()
        return self.save(state.model_copy(update={"stop_requested": True}))

    def clear_stop(self) -> ServiceControlState:
        state = self.load()
        return self.save(state.model_copy(update={"stop_requested": False}))

    def pause_stage(self, stage: str) -> ServiceControlState:
        canonical = self.canonical_stage(stage)
        state = self.load()
        paused = sorted(set(state.paused_stages + [canonical]))
        return self.save(state.model_copy(update={"paused_stages": paused}))

    def resume_stage(self, stage: str) -> ServiceControlState:
        canonical = self.canonical_stage(stage)
        state = self.load()
        paused = [s for s in state.paused_stages if s != canonical]
        return self.save(state.model_copy(update={"paused_stages": paused}))

    def is_stage_paused(self, stage: str) -> bool:
        canonical = self.canonical_stage(stage)
        return canonical in set(self.load().paused_stages)
