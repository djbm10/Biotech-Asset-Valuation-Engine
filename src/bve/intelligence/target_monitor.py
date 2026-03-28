"""Loader for the M&A live-target monitor research file."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class TargetMonitorEntry(BaseModel):
    """One current or recently resolved public-target monitor entry."""

    company_name: str
    ticker: str
    status: str
    therapeutic_area: str
    lead_assets: str
    stage: str
    source_url: str
    notes: str | None = None


class TargetMonitorDataset(BaseModel):
    """Typed representation of `research/mna/target_monitor.yaml`."""

    as_of_date: date
    targets: list[TargetMonitorEntry] = Field(default_factory=list)


class TargetMonitorLoader:
    """Load and validate the M&A live-target monitor YAML."""

    @staticmethod
    def load(path: Path | str) -> TargetMonitorDataset:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("Target monitor YAML must be a mapping with 'as_of_date' and 'targets'")
        return TargetMonitorDataset.model_validate(raw)
