"""Dilution model — scenarios for equity offering impact on per-share value."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Legacy models (preserved for backward compatibility)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Step 4 spec: new dilution models with compute function
# ---------------------------------------------------------------------------


class DilutionScenarioV2(BaseModel):
    """
    A single dilution scenario for a prospective equity raise.

    Attributes
    ----------
    label                   : "bull", "base", or "bear"
    shares_before           : shares outstanding before the raise
    new_shares_issued       : new shares issued in the raise
    price_per_share         : offering price per share (USD)
    gross_proceeds_usd      : total gross proceeds from the raise (USD)
    dilution_pct            : new_shares / (shares_before + new_shares) * 100
    post_raise_ownership_pct: existing holder's % ownership after raise
    """

    model_config = {"frozen": True}

    label: str
    shares_before: float
    new_shares_issued: float
    price_per_share: float
    gross_proceeds_usd: float
    dilution_pct: float
    post_raise_ownership_pct: float


class DilutionAnalysis(BaseModel):
    """Full dilution analysis across bull/base/bear scenarios."""

    model_config = {"frozen": True}

    asset_id: str
    as_of_date: str
    current_shares: float
    current_price: float
    scenarios: list[DilutionScenarioV2]
    weighted_dilution_pct: float
    summary: str


def _build_scenario(
    label: str,
    shares_before: float,
    current_price: float,
    price_multiplier: float,
    capital_needed_usd: float,
) -> DilutionScenarioV2:
    """Build a single DilutionScenarioV2 from a price multiplier."""
    price_per_share = current_price * price_multiplier
    if price_per_share <= 0:
        # Guard against degenerate inputs; treat as no raise possible
        new_shares = 0.0
        gross_proceeds = 0.0
    else:
        new_shares = capital_needed_usd / price_per_share
        gross_proceeds = new_shares * price_per_share

    total_shares = shares_before + new_shares
    if total_shares <= 0:
        dilution_pct = 0.0
        post_raise_ownership_pct = 100.0
    else:
        dilution_pct = new_shares / total_shares * 100.0
        post_raise_ownership_pct = shares_before / total_shares * 100.0

    return DilutionScenarioV2(
        label=label,
        shares_before=shares_before,
        new_shares_issued=new_shares,
        price_per_share=price_per_share,
        gross_proceeds_usd=gross_proceeds,
        dilution_pct=dilution_pct,
        post_raise_ownership_pct=post_raise_ownership_pct,
    )


def compute_dilution_scenarios(
    asset_id: str,
    current_shares: float,
    current_price: float,
    capital_needed_usd: float,
    as_of_date: str = "",
) -> DilutionAnalysis:
    """
    Compute bull / base / bear dilution scenarios for an equity raise.

    Parameters
    ----------
    asset_id            : asset identifier
    current_shares      : shares outstanding before raise
    current_price       : current share price (USD)
    capital_needed_usd  : amount to raise (USD)
    as_of_date          : ISO date string for the analysis
    """
    bull = _build_scenario("bull", current_shares, current_price, 1.20, capital_needed_usd)
    base = _build_scenario("base", current_shares, current_price, 0.90, capital_needed_usd)
    bear = _build_scenario("bear", current_shares, current_price, 0.70, capital_needed_usd)

    weighted_dilution_pct = (
        0.25 * bull.dilution_pct
        + 0.50 * base.dilution_pct
        + 0.25 * bear.dilution_pct
    )

    summary = (
        f"Capital needed: ${capital_needed_usd:,.0f}. "
        f"Bull dilution {bull.dilution_pct:.1f}%, "
        f"base {base.dilution_pct:.1f}%, "
        f"bear {bear.dilution_pct:.1f}%. "
        f"Probability-weighted dilution: {weighted_dilution_pct:.1f}%."
    )

    return DilutionAnalysis(
        asset_id=asset_id,
        as_of_date=as_of_date,
        current_shares=current_shares,
        current_price=current_price,
        scenarios=[bull, base, bear],
        weighted_dilution_pct=weighted_dilution_pct,
        summary=summary,
    )
