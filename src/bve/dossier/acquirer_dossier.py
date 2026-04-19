"""
Point-in-time snapshot of an acquiring company's strategic profile.

Assembled by EvidenceDossierBuilder from evidence store records.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class TherapeuticFocus(BaseModel):
    model_config = {"frozen": True}

    therapeutic_area: str
    priority_level: str  # "primary", "secondary", "emerging"
    rationale: str | None = None


class PipelineGap(BaseModel):
    model_config = {"frozen": True}

    description: str
    phase_needed: str | None = None  # "phase2", "phase3", "approved"
    indication: str | None = None
    urgency: str  # "high", "medium", "low"


class LOEExposure(BaseModel):
    model_config = {"frozen": True}

    product_name: str
    loe_year: int | None = None
    peak_sales_usd: float | None = None
    urgency: str  # "critical" (< 3yr), "near" (3-5yr), "medium" (5-10yr), "low" (10yr+)


class BalanceSheet(BaseModel):
    model_config = {"frozen": True}

    cash_usd: float | None = None
    debt_usd: float | None = None
    market_cap_usd: float | None = None
    ev_usd: float | None = None
    as_of_date: str | None = None


class BDActivity(BaseModel):
    model_config = {"frozen": True}

    recent_deals: list[str] = Field(default_factory=list)
    preferred_stages: list[str] = Field(default_factory=list)
    typical_deal_size_usd: float | None = None
    notes: str | None = None


def _compute_acquirer_completeness(dossier: "AcquirerDossier") -> float:
    """
    Completeness score: 5 checks, each worth 0.2.

    1. len(therapeutic_focus) > 0
    2. len(pipeline_gaps) > 0
    3. balance_sheet.cash_usd is not None
    4. len(bd_activity.recent_deals) > 0
    5. len(loe_exposure) > 0
    """
    checks = [
        len(dossier.therapeutic_focus) > 0,
        len(dossier.pipeline_gaps) > 0,
        dossier.balance_sheet.cash_usd is not None,
        len(dossier.bd_activity.recent_deals) > 0,
        len(dossier.loe_exposure) > 0,
    ]
    return round(sum(checks) / 5.0, 4)


class AcquirerDossier(BaseModel):
    model_config = {"frozen": True}

    acquirer_id: str
    company_name: str
    as_of: datetime
    therapeutic_focus: list[TherapeuticFocus] = Field(default_factory=list)
    pipeline_gaps: list[PipelineGap] = Field(default_factory=list)
    loe_exposure: list[LOEExposure] = Field(default_factory=list)
    balance_sheet: BalanceSheet = Field(default_factory=BalanceSheet)
    bd_activity: BDActivity = Field(default_factory=BDActivity)
    completeness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _recompute_completeness(self) -> "AcquirerDossier":
        computed = _compute_acquirer_completeness(self)
        object.__setattr__(self, "completeness_score", computed)
        return self
