"""RunContext — captures all inputs and provenance for a single valuation run."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _dict_hash(d: dict) -> str:
    serialized = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


@dataclass
class RunMetadata:
    """Immutable provenance record for a single run."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    git_commit: str | None = field(default_factory=_git_commit)
    config_hash: str | None = None
    assumptions_hash: str | None = None
    data_snapshot_id: str | None = None
    model_version: str = "1.0.0"
    user_id: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    runtime_environment: str = field(default_factory=lambda: os.environ.get("BVE_ENV", "development"))

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "git_commit": self.git_commit,
            "config_hash": self.config_hash,
            "assumptions_hash": self.assumptions_hash,
            "data_snapshot_id": self.data_snapshot_id,
            "model_version": self.model_version,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat(),
            "runtime_environment": self.runtime_environment,
        }


class RunContext:
    """Context manager for a single valuation run."""

    def __init__(
        self,
        config: dict | None = None,
        assumptions: dict | None = None,
        user_id: str | None = None,
        model_version: str = "1.0.0",
    ) -> None:
        config_hash = _dict_hash(config) if config else None
        assumptions_hash = _dict_hash(assumptions) if assumptions else None
        self.metadata = RunMetadata(
            config_hash=config_hash,
            assumptions_hash=assumptions_hash,
            user_id=user_id,
            model_version=model_version,
        )
        self._completed_at: datetime | None = None
        self._failed_assets: list[str] = []
        self._stale_data_warnings: list[str] = []
        self._score_deltas: dict[str, float] = {}

    @property
    def run_id(self) -> str:
        return self.metadata.run_id

    def record_failure(self, asset_id: str, reason: str) -> None:
        self._failed_assets.append(f"{asset_id}: {reason}")

    def record_stale_warning(self, field_path: str) -> None:
        self._stale_data_warnings.append(field_path)

    def record_score_delta(self, asset_id: str, delta: float) -> None:
        self._score_deltas[asset_id] = delta

    def complete(self) -> None:
        self._completed_at = datetime.utcnow()

    @property
    def duration_seconds(self) -> float | None:
        if self._completed_at is None:
            return None
        return (self._completed_at - self.metadata.started_at).total_seconds()

    def to_observation_dict(self) -> dict:
        return {
            **self.metadata.to_dict(),
            "completed_at": self._completed_at.isoformat() if self._completed_at else None,
            "duration_seconds": self.duration_seconds,
            "failed_assets": self._failed_assets,
            "stale_data_warnings": self._stale_data_warnings,
            "score_deltas": self._score_deltas,
        }
