"""Persistent knowledge dossier for a biological target."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class KeyPaper(BaseModel):
    title: str
    authors: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[int] = None
    pmid: Optional[str] = None
    summary: Optional[str] = None
    evidence_type: str = "mechanistic"   # "mechanistic" / "translational" / "clinical" / "review"


class TargetDossier(BaseModel):
    target_id: str
    target_name: str
    gene_symbol: Optional[str] = None
    target_class: Optional[str] = None   # "kinase" / "GPCR" / "ion_channel" / "transcription_factor" / "other"
    pathway: Optional[str] = None
    mechanism_summary: str = ""
    historical_success_patterns: list[str] = Field(default_factory=list)
    historical_failure_patterns: list[str] = Field(default_factory=list)
    known_safety_issues: list[str] = Field(default_factory=list)
    approved_drugs_on_target: list[str] = Field(default_factory=list)
    key_papers: list[KeyPaper] = Field(default_factory=list)
    open_scientific_controversies: list[str] = Field(default_factory=list)
    biomarker_context: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_refreshed_at: Optional[datetime] = None
    source: str = "manual"


class TargetDossierStore:
    """In-memory store for target dossiers."""

    def __init__(self) -> None:
        self._dossiers: dict[str, TargetDossier] = {}

    def upsert(self, dossier: TargetDossier) -> None:
        self._dossiers[dossier.target_id] = dossier

    def get(self, target_id: str) -> Optional[TargetDossier]:
        return self._dossiers.get(target_id)

    def find_by_name(self, name: str) -> list[TargetDossier]:
        nl = name.lower()
        return [d for d in self._dossiers.values()
                if nl in d.target_name.lower() or (d.gene_symbol and nl in d.gene_symbol.lower())]

    def all(self) -> list[TargetDossier]:
        return list(self._dossiers.values())
