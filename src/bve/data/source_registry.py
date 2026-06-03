"""DataSourceRegistry — catalogue of all approved data sources."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class DataSourceContract(BaseModel):
    """Contract specification for a single data source."""

    source_name: str
    source_type: str
    license_status: Literal["public", "licensed", "proprietary", "scraped"]
    allowed_use: Literal["commercial", "research_only", "internal_only"]
    refresh_frequency: str
    primary_key: str
    point_in_time_available: Literal["full", "partial", "none"]
    survivorship_bias_risk: Literal["low", "medium", "high"]
    restatement_policy: str
    fallback_source: str | None = None
    confidence_weight: float = Field(ge=0.0, le=1.0)
    fields_used: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @property
    def is_pit_safe(self) -> bool:
        return self.point_in_time_available == "full"

    @property
    def requires_legal_review(self) -> bool:
        return self.license_status in ("scraped", "licensed")

    @property
    def requires_bias_mitigation(self) -> bool:
        return self.survivorship_bias_risk == "high"


class DataSourceRegistry:
    """Registry of all data source contracts loaded from YAML."""

    def __init__(self, contracts_path: str | Path | None = None) -> None:
        if contracts_path is None:
            contracts_path = Path(__file__).parent / "source_contracts.yaml"
        self._path = Path(contracts_path)
        self._contracts: dict[str, DataSourceContract] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with open(self._path) as f:
            raw = yaml.safe_load(f)
        for name, spec in raw.items():
            spec["source_name"] = name
            self._contracts[name] = DataSourceContract(**spec)

    def get(self, source_name: str) -> DataSourceContract | None:
        return self._contracts.get(source_name)

    def all(self) -> list[DataSourceContract]:
        return list(self._contracts.values())

    def pit_safe_sources(self) -> list[DataSourceContract]:
        return [c for c in self._contracts.values() if c.is_pit_safe]

    def requires_legal_review(self) -> list[DataSourceContract]:
        return [c for c in self._contracts.values() if c.requires_legal_review]

    def validate_field(self, source_name: str, field_name: str) -> bool:
        """Check if a field is explicitly listed for this source."""
        contract = self.get(source_name)
        if contract is None:
            return False
        return field_name in contract.fields_used


_default_registry: DataSourceRegistry | None = None


def get_registry() -> DataSourceRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = DataSourceRegistry()
    return _default_registry
