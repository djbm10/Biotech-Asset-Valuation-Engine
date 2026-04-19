"""Runway forecast — cash burn scenarios and capital adequacy assessment."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Legacy models (preserved for backward compatibility)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Step 4 spec: new runway forecast models with compute functions
# ---------------------------------------------------------------------------


class BurnRateEstimate(BaseModel):
    """Estimated monthly burn rate with provenance and confidence."""

    model_config = {"frozen": True}

    monthly_burn_usd: float
    annualized_burn_usd: float
    source: str  # "rd_expense_annualized" | "opex_estimate" | "direct"
    confidence: float  # 0-1


class RunwayForecastV2(BaseModel):
    """
    Point-in-time runway forecast — Step 4 spec version.

    Captures cash, burn rate, runway horizon, risk classification,
    and the date by which financing is needed.
    """

    model_config = {"frozen": True}

    asset_id: str
    as_of_date: str
    cash_usd: float
    burn_rate: BurnRateEstimate
    runway_months: float
    runway_date: str        # ISO date when cash runs out
    next_financing_needed_by: str | None  # ISO date — 3 months before runway_date
    runway_risk: str        # "critical" | "high" | "medium" | "low" | "comfortable"
    notes: str


def estimate_burn_rate(
    rd_expense_annual_usd: float | None = None,
    opex_annual_usd: float | None = None,
    direct_monthly_usd: float | None = None,
) -> BurnRateEstimate:
    """
    Estimate monthly burn rate from available financial data.

    Priority: direct > rd_expense_annualized > opex_estimate.

    R&D expense is typically 60-70% of total opex for clinical-stage biotechs,
    so when derived from R&D spend it is grossed up by 1/0.65.

    Raises
    ------
    ValueError
        If none of the three inputs are provided.
    """
    if direct_monthly_usd is not None:
        monthly = direct_monthly_usd
        source = "direct"
        confidence = 0.90
    elif rd_expense_annual_usd is not None:
        # R&D is ~65% of total opex; gross up to capture full burn
        monthly = (rd_expense_annual_usd / 12.0) * (1.0 / 0.65)
        source = "rd_expense_annualized"
        confidence = 0.75
    elif opex_annual_usd is not None:
        monthly = opex_annual_usd / 12.0
        source = "opex_estimate"
        confidence = 0.60
    else:
        raise ValueError("At least one burn rate input required")

    return BurnRateEstimate(
        monthly_burn_usd=monthly,
        annualized_burn_usd=monthly * 12.0,
        source=source,
        confidence=confidence,
    )


def _add_months(base: date, months: float) -> date:
    """
    Add a fractional number of months to a date.

    Uses whole-month integer arithmetic plus a remainder converted to days.
    """
    whole_months = int(months)
    remainder_days = int(round((months - whole_months) * 30.44))  # avg days/month

    # Advance whole months
    month = base.month - 1 + whole_months
    year = base.year + month // 12
    month = month % 12 + 1
    # Clamp day to valid range for the target month
    import calendar

    max_day = calendar.monthrange(year, month)[1]
    day = min(base.day, max_day)
    result = date(year, month, day)
    return result + timedelta(days=remainder_days)


def _subtract_months(base: date, months: int) -> date:
    """Subtract an integer number of months from a date."""
    month = base.month - 1 - months
    year = base.year + month // 12
    month = month % 12 + 1
    import calendar

    max_day = calendar.monthrange(year, month)[1]
    day = min(base.day, max_day)
    return date(year, month, day)


def _runway_risk_label(runway_months: float) -> str:
    if runway_months < 6:
        return "critical"
    if runway_months < 12:
        return "high"
    if runway_months < 18:
        return "medium"
    if runway_months < 30:
        return "low"
    return "comfortable"


def compute_runway(
    asset_id: str,
    cash_usd: float,
    burn_rate: BurnRateEstimate,
    as_of_date: str = "",
) -> RunwayForecastV2:
    """
    Compute a RunwayForecastV2 from cash and burn rate.

    Parameters
    ----------
    asset_id    : asset identifier
    cash_usd    : current cash on hand (USD)
    burn_rate   : BurnRateEstimate (from estimate_burn_rate)
    as_of_date  : ISO date string; defaults to today if empty
    """
    # Resolve base date
    if as_of_date:
        base_date = date.fromisoformat(as_of_date)
    else:
        base_date = date.today()
        as_of_date = base_date.isoformat()

    runway_months = cash_usd / burn_rate.monthly_burn_usd
    runway_date = _add_months(base_date, runway_months)

    next_financing_needed_by: str | None
    if runway_months > 3:
        next_financing_needed_by = _subtract_months(runway_date, 3).isoformat()
    else:
        next_financing_needed_by = None

    runway_risk = _runway_risk_label(runway_months)

    notes = (
        f"Cash ${cash_usd:,.0f} at {as_of_date}. "
        f"Monthly burn ${burn_rate.monthly_burn_usd:,.0f} "
        f"(source: {burn_rate.source}, confidence {burn_rate.confidence:.0%}). "
        f"Runway {runway_months:.1f} months — {runway_risk} risk."
    )

    return RunwayForecastV2(
        asset_id=asset_id,
        as_of_date=as_of_date,
        cash_usd=cash_usd,
        burn_rate=burn_rate,
        runway_months=runway_months,
        runway_date=runway_date.isoformat(),
        next_financing_needed_by=next_financing_needed_by,
        runway_risk=runway_risk,
        notes=notes,
    )
