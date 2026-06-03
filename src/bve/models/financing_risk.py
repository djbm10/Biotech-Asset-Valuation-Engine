"""Financing risk assessment models — scenario-based capital runway risk."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Legacy models (preserved for backward compatibility)
# ---------------------------------------------------------------------------


class FinancingScenario(BaseModel):
    """A single financing scenario with probability and terms."""

    label: str  # "no_raise" | "bridge" | "follow_on" | "dilutive" | "partnership" | "distressed"
    probability: float = Field(ge=0.0, le=1.0)
    raise_size_millions: float = 0.0
    dilution_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    timing_months: float = 0.0


class FinancingRiskAssessment(BaseModel):
    """Point-in-time financing risk assessment for a company."""

    asset_id: str
    company_id: str
    assessment_date: date
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_tier: str  # "low" | "medium" | "high" | "critical"
    scenarios: list[FinancingScenario] = Field(default_factory=list)
    primary_scenario: str
    distress_probability: float = Field(ge=0.0, le=1.0)
    commentary: str


class FinancingRisk(BaseModel):
    """Financing risk container with current assessment and historical records."""

    asset_id: str
    company_id: str
    current_assessment: Optional[FinancingRiskAssessment] = None
    history: list[FinancingRiskAssessment] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 4 spec: new financing risk models with compute function
# ---------------------------------------------------------------------------


class DistressTier(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


_HAIRCUT_BY_TIER: dict[DistressTier, float] = {
    DistressTier.NONE: 1.00,
    DistressTier.LOW: 0.95,
    DistressTier.MEDIUM: 0.85,
    DistressTier.HIGH: 0.70,
    DistressTier.CRITICAL: 0.50,
}


class FinancingRiskV2(BaseModel):
    """
    Financing risk model — Step 4 spec version.

    Captures runway, dilution estimates, distress tier, and a
    multiplicative value haircut for use in valuation.
    """

    model_config = {"frozen": True}

    asset_id: str
    as_of_date: str
    runway_months: float | None = None
    capital_needed_usd: float | None = None
    p_pre_catalyst_raise: float | None = None
    dilution_low_pct: float | None = None
    dilution_mid_pct: float | None = None
    dilution_high_pct: float | None = None
    distress_tier: DistressTier
    partnership_flag: bool
    financing_adjusted_value_haircut: float
    rationale: str
    assumptions: dict[str, float]


def compute_financing_risk(
    cash_usd: float,
    monthly_burn_usd: float,
    market_cap_usd: float | None,
    catalyst_months_away: float | None,
    trial_cost_remaining_usd: float | None = None,
    asset_id: str = "",
    as_of_date: str = "",
) -> FinancingRiskV2:
    """
    Compute a FinancingRiskV2 from cash, burn, and catalyst timing inputs.

    Parameters
    ----------
    cash_usd                : current cash on hand (USD)
    monthly_burn_usd        : monthly cash burn (USD); if 0, runway is None
    market_cap_usd          : current market cap (USD); may be None
    catalyst_months_away    : months until next catalyst; may be None
    trial_cost_remaining_usd: remaining trial cost (USD); optional
    asset_id                : identifier for the asset
    as_of_date              : ISO date string for the assessment
    """
    # ------------------------------------------------------------------
    # Runway
    # ------------------------------------------------------------------
    runway_months: float | None
    if monthly_burn_usd > 0:
        runway_months = cash_usd / monthly_burn_usd
    else:
        runway_months = None

    # ------------------------------------------------------------------
    # Capital needed
    # ------------------------------------------------------------------
    capital_needed_usd: float | None
    if trial_cost_remaining_usd is not None:
        capital_needed_usd = max(0.0, trial_cost_remaining_usd - cash_usd)
    elif catalyst_months_away is not None:
        raw = monthly_burn_usd * catalyst_months_away - cash_usd
        capital_needed_usd = max(0.0, raw)
    else:
        capital_needed_usd = None

    # ------------------------------------------------------------------
    # p_pre_catalyst_raise
    # ------------------------------------------------------------------
    p_pre_catalyst_raise: float | None
    if catalyst_months_away is None or runway_months is None:
        p_pre_catalyst_raise = None
    else:
        if runway_months > catalyst_months_away * 1.5:
            p_pre_catalyst_raise = 0.05
        elif runway_months > catalyst_months_away * 1.2:
            p_pre_catalyst_raise = 0.30
        elif runway_months > catalyst_months_away * 0.8:
            p_pre_catalyst_raise = 0.60
        elif runway_months > catalyst_months_away * 0.5:
            p_pre_catalyst_raise = 0.85
        else:
            p_pre_catalyst_raise = 0.95

    # ------------------------------------------------------------------
    # Dilution estimates
    # ------------------------------------------------------------------
    dilution_low_pct: float | None
    dilution_mid_pct: float | None
    dilution_high_pct: float | None

    if (
        capital_needed_usd is None
        or market_cap_usd is None
        or market_cap_usd == 0
    ):
        dilution_low_pct = None
        dilution_mid_pct = None
        dilution_high_pct = None
    else:
        raw_dilution = capital_needed_usd / market_cap_usd
        dilution_low_pct = min(raw_dilution * 0.85 * 100, 200.0)
        dilution_mid_pct = min(raw_dilution * 1.10 * 100, 200.0)
        dilution_high_pct = min(raw_dilution * 1.40 * 100, 200.0)

    # ------------------------------------------------------------------
    # Distress tier
    # ------------------------------------------------------------------
    distress_tier: DistressTier
    if runway_months is None:
        distress_tier = DistressTier.MEDIUM
    elif runway_months < 6 or (
        dilution_high_pct is not None and dilution_high_pct > 100
    ):
        distress_tier = DistressTier.CRITICAL
    elif runway_months < 12 or (
        dilution_high_pct is not None and dilution_high_pct > 50
    ):
        distress_tier = DistressTier.HIGH
    elif runway_months < 18 or (
        dilution_high_pct is not None and dilution_high_pct > 25
    ):
        distress_tier = DistressTier.MEDIUM
    elif runway_months < 30:
        distress_tier = DistressTier.LOW
    else:
        distress_tier = DistressTier.NONE

    # ------------------------------------------------------------------
    # Partnership flag
    # ------------------------------------------------------------------
    partnership_flag = distress_tier in (DistressTier.CRITICAL, DistressTier.HIGH) and (
        market_cap_usd is None or market_cap_usd < 500_000_000
    )

    # ------------------------------------------------------------------
    # Value haircut
    # ------------------------------------------------------------------
    financing_adjusted_value_haircut = _HAIRCUT_BY_TIER[distress_tier]

    # ------------------------------------------------------------------
    # Rationale
    # ------------------------------------------------------------------
    parts: list[str] = []
    if runway_months is not None:
        parts.append(f"Runway {runway_months:.1f} months")
    if capital_needed_usd is not None:
        parts.append(f"capital needed ${capital_needed_usd:,.0f}")
    if p_pre_catalyst_raise is not None:
        parts.append(f"P(raise before catalyst) {p_pre_catalyst_raise:.0%}")
    parts.append(f"distress tier {distress_tier.value}")
    if partnership_flag:
        parts.append("partnership alternative likely")
    rationale = "; ".join(parts) + "."

    # ------------------------------------------------------------------
    # Assumptions dict
    # ------------------------------------------------------------------
    assumptions: dict[str, float] = {
        "monthly_burn_usd": monthly_burn_usd,
        "cash_usd": cash_usd,
    }
    if runway_months is not None:
        assumptions["runway_months"] = runway_months
    if catalyst_months_away is not None:
        assumptions["catalyst_months_away"] = catalyst_months_away
    if market_cap_usd is not None:
        assumptions["market_cap_usd"] = market_cap_usd
    if trial_cost_remaining_usd is not None:
        assumptions["trial_cost_remaining_usd"] = trial_cost_remaining_usd

    return FinancingRiskV2(
        asset_id=asset_id,
        as_of_date=as_of_date,
        runway_months=runway_months,
        capital_needed_usd=capital_needed_usd,
        p_pre_catalyst_raise=p_pre_catalyst_raise,
        dilution_low_pct=dilution_low_pct,
        dilution_mid_pct=dilution_mid_pct,
        dilution_high_pct=dilution_high_pct,
        distress_tier=distress_tier,
        partnership_flag=partnership_flag,
        financing_adjusted_value_haircut=financing_adjusted_value_haircut,
        rationale=rationale,
        assumptions=assumptions,
    )
