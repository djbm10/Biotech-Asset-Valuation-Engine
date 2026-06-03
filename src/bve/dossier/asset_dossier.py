"""
Point-in-time snapshot of everything known about a drug asset.

Assembled by EvidenceDossierBuilder from evidence store records.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AssetIdentity(BaseModel):
    model_config = {"frozen": True}

    asset_id: str
    ticker: str | None = None
    drug_name: str | None = None
    company_name: str | None = None
    indication: str | None = None
    modality: str | None = None


class TrialSnapshot(BaseModel):
    model_config = {"frozen": True}

    nct_id: str
    phase: str
    status: str
    enrollment: int | None = None
    primary_endpoint: str | None = None
    completion_date: str | None = None


class CatalystSnapshot(BaseModel):
    model_config = {"frozen": True}

    description: str
    expected_date: str | None = None
    catalyst_type: str  # "trial_readout", "pdufa", "enrollment_complete", "regulatory", "other"
    source: str  # which EvidenceRecord led to this
    confidence: float = Field(ge=0.0, le=1.0)


class ScienceContext(BaseModel):
    model_config = {"frozen": True}

    mechanism_summary: str | None = None
    target: str | None = None
    biomarker_strategy: str | None = None
    key_publications: list[str] = Field(default_factory=list)  # PMIDs


class CompetitionSnapshot(BaseModel):
    model_config = {"frozen": True}

    competitor_names: list[str] = Field(default_factory=list)
    competitive_risk_level: str = "unknown"  # "low", "medium", "high", "unknown"
    notes: str | None = None


class FinancingState(BaseModel):
    model_config = {"frozen": True}

    cash_usd: float | None = None
    rd_expense_usd: float | None = None
    shares_outstanding: float | None = None
    cash_period_end: str | None = None


class MarketSnapshot(BaseModel):
    model_config = {"frozen": True}

    last_price: float | None = None
    market_cap_usd: float | None = None
    ev_usd: float | None = None
    as_of_date: str | None = None


class ThesisState(BaseModel):
    model_config = {"frozen": True}

    summary: str | None = None
    key_positives: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


def _compute_completeness(dossier: "AssetDossier") -> float:
    """
    Completeness score: 10 checks, each worth 0.1.

    1.  identity.ticker is not None
    2.  identity.drug_name is not None
    3.  identity.indication is not None
    4.  len(trials) > 0
    5.  len(catalysts) > 0
    6.  science.mechanism_summary is not None
    7.  financing.cash_usd is not None
    8.  market.last_price is not None
    9.  len(thesis.key_positives) > 0
    10. len(thesis.key_risks) > 0
    """
    checks = [
        dossier.identity.ticker is not None,
        dossier.identity.drug_name is not None,
        dossier.identity.indication is not None,
        len(dossier.trials) > 0,
        len(dossier.catalysts) > 0,
        dossier.science.mechanism_summary is not None,
        dossier.financing.cash_usd is not None,
        dossier.market.last_price is not None,
        len(dossier.thesis.key_positives) > 0,
        len(dossier.thesis.key_risks) > 0,
    ]
    return round(sum(checks) / 10.0, 4)


class AssetDossier(BaseModel):
    model_config = {"frozen": True}

    asset_id: str
    as_of: datetime
    identity: AssetIdentity
    trials: list[TrialSnapshot] = Field(default_factory=list)
    catalysts: list[CatalystSnapshot] = Field(default_factory=list)
    science: ScienceContext = Field(default_factory=ScienceContext)
    competition: CompetitionSnapshot = Field(default_factory=CompetitionSnapshot)
    financing: FinancingState = Field(default_factory=FinancingState)
    market: MarketSnapshot = Field(default_factory=MarketSnapshot)
    thesis: ThesisState = Field(default_factory=ThesisState)
    evidence_record_count: int = 0
    completeness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _recompute_completeness(self) -> "AssetDossier":
        computed = _compute_completeness(self)
        # Use object.__setattr__ because the model is frozen
        object.__setattr__(self, "completeness_score", computed)
        return self
