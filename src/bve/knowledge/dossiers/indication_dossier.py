"""Persistent knowledge dossier for a disease indication."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class StandardOfCareEntry(BaseModel):
    line: str                   # "1L" / "2L" / "3L+"
    regimen: str
    typical_outcome: Optional[str] = None
    as_of_year: Optional[int] = None


class IndicationDossier(BaseModel):
    indication_id: str
    indication_name: str
    therapeutic_area: str
    disease_biology_summary: str = ""
    unmet_need_summary: str = ""
    standard_of_care: list[StandardOfCareEntry] = Field(default_factory=list)
    commonly_used_endpoints: list[str] = Field(default_factory=list)
    endpoint_controversies: list[str] = Field(default_factory=list)
    approved_therapies: list[str] = Field(default_factory=list)
    key_biomarkers: list[str] = Field(default_factory=list)
    patient_population_estimate: Optional[str] = None
    regulatory_precedent_summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_refreshed_at: Optional[datetime] = None
    source: str = "manual"


class IndicationDossierStore:
    """In-memory store for indication dossiers."""

    def __init__(self) -> None:
        self._dossiers: dict[str, IndicationDossier] = {}

    def upsert(self, dossier: IndicationDossier) -> None:
        self._dossiers[dossier.indication_id] = dossier

    def get(self, indication_id: str) -> Optional[IndicationDossier]:
        return self._dossiers.get(indication_id)

    def find_by_name(self, name: str) -> list[IndicationDossier]:
        nl = name.lower()
        return [d for d in self._dossiers.values() if nl in d.indication_name.lower()]

    def all(self) -> list[IndicationDossier]:
        return list(self._dossiers.values())
