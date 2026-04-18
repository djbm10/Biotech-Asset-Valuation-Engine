"""Dilution model — scenarios for equity offering impact on per-share value."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DilutionScenario(BaseModel):
    """A single dilution scenario from an equity raise."""

    label: str
    share_count_before: float
    share_count_after: float
    dilution_pct: float
    offering_price: Optional[float] = None
    gross_proceeds_millions: Optional[float] = None
    discount_to_market_pct: Optional[float] = None


class DilutionModel(BaseModel):
    """Dilution model for a company across multiple raise scenarios."""

    company_id: str
    current_shares_millions: float
    current_market_cap_millions: float
    scenarios: list[DilutionScenario] = Field(default_factory=list)
    expected_dilution_pct_low: float = Field(ge=0.0, le=1.0)
    expected_dilution_pct_base: float = Field(ge=0.0, le=1.0)
    expected_dilution_pct_high: float = Field(ge=0.0, le=1.0)
    total_authorized_shares_millions: Optional[float] = None
    atm_facility_size_millions: Optional[float] = None
