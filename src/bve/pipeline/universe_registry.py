"""Universe registry loader for staged watchlist expansion."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class UniverseRegistryEntry(BaseModel):
    """One universe seed entry used for auto-config generation."""

    ticker: str
    company_name: str
    asset_id: str
    drug_name: str
    indication: str
    therapeutic_area: str
    stage: str
    modality: str
    nct_id: str | None = None
    tam_millions: float | None = Field(default=None, ge=0.0)
    net_price_per_patient_usd: float | None = Field(default=None, ge=0.0)
    addressable_patients_annual: int | None = Field(default=None, ge=0)
    peak_penetration: float | None = Field(default=None, ge=0.0, le=1.0)
    patent_life_years: int | None = Field(default=None, ge=0)
    discount_rate: float | None = Field(default=None, ge=0.0, le=1.0)


def load_universe_registry(path: Path | str) -> list[UniverseRegistryEntry]:
    """Load and validate the universe registry YAML file."""

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        records = raw.get("assets", [])
    else:
        records = raw

    if not isinstance(records, list):
        raise ValueError("Universe registry must be a list or contain an 'assets' list")
    return [UniverseRegistryEntry.model_validate(item) for item in records]
