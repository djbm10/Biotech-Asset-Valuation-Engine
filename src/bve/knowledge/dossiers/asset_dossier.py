"""Persistent knowledge dossier for a drug asset/program."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from bve.knowledge.dossiers.target_dossier import KeyPaper


class ClinicalDataPoint(BaseModel):
    study_id: Optional[str] = None
    phase: str
    population: str
    n: Optional[int] = None
    primary_endpoint: str
    result_summary: str
    key_safety_findings: Optional[str] = None
    reported_date: Optional[str] = None


class AssetDossier(BaseModel):
    asset_id: str
    asset_name: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    indication: str
    target: Optional[str] = None
    mechanism: Optional[str] = None
    modality: str = "unknown"
    current_phase: str = "unknown"
    mechanism_summary: str = ""
    clinical_data: list[ClinicalDataPoint] = Field(default_factory=list)
    key_papers: list[KeyPaper] = Field(default_factory=list)
    known_safety_issues: list[str] = Field(default_factory=list)
    competitive_context: str = ""
    bull_case: str = ""
    bear_case: str = ""
    key_upcoming_catalysts: list[str] = Field(default_factory=list)
    kill_criteria: list[str] = Field(default_factory=list)
    regulatory_strategy: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_refreshed_at: Optional[datetime] = None
    source: str = "manual"


class AssetDossierStore:
    """In-memory store for asset dossiers."""

    def __init__(self) -> None:
        self._dossiers: dict[str, AssetDossier] = {}

    def upsert(self, dossier: AssetDossier) -> None:
        self._dossiers[dossier.asset_id] = dossier

    def get(self, asset_id: str) -> Optional[AssetDossier]:
        return self._dossiers.get(asset_id)

    def find_by_indication(self, indication: str) -> list[AssetDossier]:
        il = indication.lower()
        return [d for d in self._dossiers.values() if il in d.indication.lower()]

    def find_by_company(self, company_id: str) -> list[AssetDossier]:
        return [d for d in self._dossiers.values() if d.company_id == company_id]

    def all(self) -> list[AssetDossier]:
        return list(self._dossiers.values())
