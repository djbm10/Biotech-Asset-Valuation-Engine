"""Runway forecast — cash burn scenarios and capital adequacy assessment."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class BurnScenario(BaseModel):
    """A single burn rate scenario."""

    label: str  # "bull" | "base" | "bear"
    quarterly_burn_millions: float
    annual_burn_millions: float
    burn_rate_change_pct: float = 0.0


class RunwayForecast(BaseModel):
    """Forward-looking runway forecast for a company."""

    company_id: str
    forecast_date: date
    cash_millions: float
    debt_millions: float
    net_cash_millions: float
    burn_scenarios: list[BurnScenario] = Field(default_factory=list)
    runway_months_bull: float
    runway_months_base: float
    runway_months_bear: float
    next_catalyst_date: Optional[date] = None
    capital_needed_to_next_catalyst_millions: float
    capital_needed_to_approval_millions: float
    cash_adequate_for_next_catalyst: bool
