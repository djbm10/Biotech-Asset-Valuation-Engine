"""API response schemas for BVE platform endpoints."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None


class CompanyCard(BaseModel):
    id: str
    ticker: Optional[str]
    name: str
    company_type: str
    market_cap: Optional[float]
    cash: Optional[float]
    enterprise_value: Optional[float]


class AssetCard(BaseModel):
    id: str
    company_id: str
    company_name: Optional[str]
    ticker: Optional[str]
    name: str
    modality: Optional[str]
    therapeutic_area: Optional[str]
    indication: Optional[str]
    current_phase: Optional[str]
    status: Optional[str]
    partnered: bool


class AssetPage(BaseModel):
    asset: AssetCard
    company: Optional[CompanyCard]
    trials: list[dict]
    catalysts: list[dict]
    dossier: Optional[dict]
    implied_expectation: Optional[dict]
    variant_thesis: Optional[dict]
    latest_scenario_tree: Optional[dict]
    latest_financing_forecast: Optional[dict]


class AcquirerCard(BaseModel):
    company_id: str
    company_name: str
    ticker: Optional[str]
    cash_firepower_millions: float
    loe_urgency: float
    strategic_areas: list[str]
    top_target_count: int


class AcquirerPage(BaseModel):
    profile: dict
    top_targets: list[dict]


class DealCard(BaseModel):
    target_company_id: str
    target_name: str
    acquirer_company_id: str
    acquirer_name: str
    fit_score: float
    timing_bucket: str
    affordability_score: Optional[float]
    strategic_fit_score: Optional[float]
    confidence: Optional[float]


class AlertCard(BaseModel):
    id: str
    source_type: Optional[str]
    title: Optional[str]
    materiality_score: Optional[float]
    published_at: Optional[str]
    source_url: Optional[str]


class CalibrationSummary(BaseModel):
    total_decisions: int
    total_outcomes: int
    pending_parameter_versions: int
    promoted_versions: list[dict]


class VariantThesisInput(BaseModel):
    market_view: dict[str, Any]
    model_view: dict[str, Any]
    delta_view: dict[str, Any]
    kill_criteria: list[str]
    confidence: float = 0.5
    documented: bool = True


class PostmortemInput(BaseModel):
    realized_outcome: dict[str, Any]
    resolved_at: Optional[str] = None
