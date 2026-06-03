"""Risk budget — portfolio-level risk limit tracking and utilization."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class RiskBudgetAllocation(BaseModel):
    """Risk budget allocation for a single bucket (TA, modality, etc.)."""

    bucket: str
    max_pct: float = Field(ge=0.0, le=1.0)
    current_pct: float = Field(ge=0.0, le=1.0)
    remaining_pct: float = Field(ge=0.0, le=1.0)
    is_breached: bool


class RiskBudget(BaseModel):
    """Portfolio-level risk budget constraints and utilization."""

    portfolio_id: str
    budget_date: date
    gross_limit_pct: float = 1.0
    net_limit_pct: float = 0.8
    single_name_max_pct: float = 0.15
    ta_max_pct: float = 0.4
    modality_max_pct: float = 0.5
    catalyst_cluster_max: int = 5
    allocations: list[RiskBudgetAllocation] = Field(default_factory=list)
    total_risk_utilization_pct: float = Field(ge=0.0, le=1.0)
    remaining_gross_budget_pct: float = Field(ge=0.0, le=1.0)
