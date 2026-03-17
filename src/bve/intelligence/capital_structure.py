"""
Wave 7 — Capital Structure Modeling.

Flags catalysts where the company may need to raise capital before the event,
computes dilution-adjusted EV, and accounts for market liquidity constraints
on raise sizing.

Logic flow
----------
1. compute_capital_risk()  — compare catalyst date to cash runway
2. estimate_raise()        — size the required offering with post-raise buffer
3. expected_offer_discount() — discount tier based on raise / market_cap ratio
4. capital_structure_assessment() — top-level function returning a full
   CapitalStructureAssessment for a catalyst

No new external API calls.  All inputs come from the Company entity + yfinance
fundamentals that are already fetched by the pipeline.
"""
from __future__ import annotations

import math
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

_CONFIG_DEFAULTS: dict = {
    "buffer_months":                   12.0,
    "min_raise_months":                 3,
    "adv_multiplier_small_cap":        20.0,
    "adv_multiplier_large_cap":        30.0,
    "multi_offering_discount_increment": 0.05,
    "max_effective_discount":           0.35,
    "risk_thresholds": {
        "medium_gap_months": 0,
        "high_gap_months":   6,
    },
}


# ---------------------------------------------------------------------------
# Capital risk level
# ---------------------------------------------------------------------------

class CapitalRiskLevel(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Assessment model
# ---------------------------------------------------------------------------

class CapitalStructureAssessment(BaseModel, frozen=True):
    """
    Full capital-structure risk assessment for a single catalyst event.

    Attributes
    ----------
    asset_id:
        Intelligence layer asset ID of the tracked program.
    catalyst_id:
        ID of the CatalystEvent being assessed.
    months_to_catalyst:
        Calendar months between today and the catalyst expected_date.
    runway_months:
        Cash runway in months (cash_runway_quarters × 3).
    gap_months:
        months_to_catalyst − runway_months.  Positive = shortfall.
    capital_risk:
        Risk level: LOW / MEDIUM / HIGH / CRITICAL.
    raise_amount_millions:
        Estimated raise size in $M, or None when risk is LOW.
    n_offerings_required:
        Number of separate offerings needed given liquidity constraints.
    effective_discount_pct:
        Blended offer discount (including multi-offering increment).
    dilution_pct:
        Fraction of new shares issued relative to post-raise share count.
    diluted_delta_ev:
        catalyst.delta_ev scaled by (1 − dilution_pct).
    liquidity_constrained:
        True when raise_amount > max_single_raise (ADV × multiplier).
    raise_exceeds_single_offering:
        True when n_offerings_required > 1.
    """
    asset_id:                  str
    catalyst_id:               str
    months_to_catalyst:        float
    runway_months:             float
    gap_months:                float
    capital_risk:              CapitalRiskLevel
    raise_amount_millions:     Optional[float]
    n_offerings_required:      int
    effective_discount_pct:    float
    dilution_pct:              float
    diluted_delta_ev:          Optional[float]
    liquidity_constrained:     bool
    raise_exceeds_single_offering: bool


# ---------------------------------------------------------------------------
# Step 1: Risk level
# ---------------------------------------------------------------------------

def compute_capital_risk(
    catalyst_expected_date: date,
    cash_runway_quarters: float,
    burn_rate_monthly_millions: float,
    *,
    cfg: Optional[dict] = None,
) -> tuple[CapitalRiskLevel, float]:
    """
    Classify capital risk for a catalyst based on cash runway vs time to event.

    Parameters
    ----------
    catalyst_expected_date:
        Expected date of the catalyst event.
    cash_runway_quarters:
        Company's cash runway expressed in quarters.
    burn_rate_monthly_millions:
        Monthly cash burn in $M.  Used for context (not consumed here).
    cfg:
        Optional config dict; falls back to ``_CONFIG_DEFAULTS``.

    Returns
    -------
    (CapitalRiskLevel, gap_months)
        gap_months > 0 means runway runs out before the catalyst.
    """
    thresholds = (_cfg(cfg).get("risk_thresholds") or
                  _CONFIG_DEFAULTS["risk_thresholds"])
    high_gap   = float(thresholds.get("high_gap_months",   6))

    months_to_catalyst = (catalyst_expected_date - date.today()).days / 30.0
    runway_months      = cash_runway_quarters * 3.0
    gap_months         = months_to_catalyst - runway_months

    if gap_months <= 0:
        return CapitalRiskLevel.LOW, gap_months
    elif gap_months <= high_gap:
        return CapitalRiskLevel.MEDIUM, gap_months
    else:
        return CapitalRiskLevel.HIGH, gap_months


# ---------------------------------------------------------------------------
# Step 2: Raise sizing
# ---------------------------------------------------------------------------

def estimate_raise(
    gap_months: float,
    burn_rate_monthly: float,
    buffer_months: float = 12.0,
    min_raise_months: int = 3,
) -> float:
    """
    Estimate the required offering size in $M.

    Biotechs raise to fund *past* the catalyst, not just to reach it.

    Parameters
    ----------
    gap_months:
        Shortfall months (months_to_catalyst − runway_months).
        A negative gap is treated as 0.
    burn_rate_monthly:
        Monthly cash burn in $M.
    buffer_months:
        Post-raise cash buffer target (default 12 months).
    min_raise_months:
        Floor: minimum raise expressed as months of burn (default 3).

    Returns
    -------
    Raise amount in $M.
    """
    raise_amount = burn_rate_monthly * (max(gap_months, 0.0) + buffer_months)
    return max(raise_amount, burn_rate_monthly * min_raise_months)


# ---------------------------------------------------------------------------
# Step 3: Discount tiers
# ---------------------------------------------------------------------------

def expected_offer_discount(
    raise_amount_millions: float,
    market_cap_millions: float,
) -> float:
    """
    Return the expected offering discount based on raise / market-cap ratio.

    Tiers:
      raise/mktcap > 0.30 → 20% (large dilutive offering)
      raise/mktcap > 0.15 → 12% (standard follow-on)
      else                → 8%  (ATM / small block)
    """
    ratio = raise_amount_millions / market_cap_millions if market_cap_millions > 0 else 1.0
    if ratio > 0.30:
        return 0.20
    elif ratio > 0.15:
        return 0.12
    else:
        return 0.08


# ---------------------------------------------------------------------------
# Top-level assessment
# ---------------------------------------------------------------------------

def capital_structure_assessment(
    catalyst,
    company_cash_runway_quarters: float,
    company_burn_rate_monthly: float,
    current_price: float,
    shares_outstanding_millions: float,
    market_cap_millions: float,
    daily_dollar_volume_millions: float,
    delta_ev: float,
    *,
    cfg: Optional[dict] = None,
) -> CapitalStructureAssessment:
    """
    Full capital-structure assessment for a CatalystEvent.

    Parameters
    ----------
    catalyst:
        CatalystEvent being assessed.
    company_cash_runway_quarters:
        Company cash runway in quarters (from Company entity or SEC EDGAR).
    company_burn_rate_monthly:
        Monthly cash burn in $M.
    current_price:
        Current stock price ($).
    shares_outstanding_millions:
        Shares outstanding (millions).
    market_cap_millions:
        Current market capitalisation ($M).
    daily_dollar_volume_millions:
        Average daily trading dollar volume ($M, from yfinance).
    delta_ev:
        Catalyst delta EV in $M (from CatalystEVCalculator or CatalystEvent).
    cfg:
        Optional config override; falls back to ``_CONFIG_DEFAULTS``.

    Returns
    -------
    CapitalStructureAssessment
    """
    c = _cfg(cfg)
    buffer_months   = float(c.get("buffer_months",     12.0))
    min_raise_months = int(c.get("min_raise_months",   3))
    adv_mult_small  = float(c.get("adv_multiplier_small_cap", 20.0))
    adv_mult_large  = float(c.get("adv_multiplier_large_cap", 30.0))
    disc_increment  = float(c.get("multi_offering_discount_increment", 0.05))
    max_discount    = float(c.get("max_effective_discount", 0.35))

    risk, gap_months = compute_capital_risk(
        catalyst.expected_date,
        company_cash_runway_quarters,
        company_burn_rate_monthly,
        cfg=c,
    )

    months_to_catalyst = (catalyst.expected_date - date.today()).days / 30.0
    runway_months      = company_cash_runway_quarters * 3.0

    # -- LOW risk: no raise needed -------------------------------------------
    if risk == CapitalRiskLevel.LOW:
        return CapitalStructureAssessment(
            asset_id                   = catalyst.asset_id or "",
            catalyst_id                = catalyst.id,
            months_to_catalyst         = round(months_to_catalyst, 2),
            runway_months              = round(runway_months, 2),
            gap_months                 = round(gap_months, 2),
            capital_risk               = risk,
            raise_amount_millions      = None,
            n_offerings_required       = 0,
            effective_discount_pct     = 0.0,
            dilution_pct               = 0.0,
            diluted_delta_ev           = delta_ev,
            liquidity_constrained      = False,
            raise_exceeds_single_offering = False,
        )

    # -- Raise sizing --------------------------------------------------------
    raise_amount = estimate_raise(
        gap_months, company_burn_rate_monthly, buffer_months, min_raise_months
    )

    # -- Liquidity constraint ------------------------------------------------
    adv_mult        = adv_mult_small if market_cap_millions < 500.0 else adv_mult_large
    max_single_raise = adv_mult * daily_dollar_volume_millions

    if raise_amount > max_single_raise and max_single_raise > 0:
        n_offerings      = math.ceil(raise_amount / max_single_raise)
        base_discount    = expected_offer_discount(raise_amount, market_cap_millions)
        effective_disc   = min(base_discount + disc_increment * (n_offerings - 1), max_discount)
        liquidity_const  = True
        if n_offerings >= 3:
            risk = CapitalRiskLevel.CRITICAL
        else:
            risk = CapitalRiskLevel.HIGH
    else:
        n_offerings    = 1
        effective_disc = expected_offer_discount(raise_amount, market_cap_millions)
        liquidity_const = False

    # -- Dilution ------------------------------------------------------------
    offer_price = current_price * (1.0 - effective_disc)
    if offer_price > 0 and shares_outstanding_millions > 0:
        new_shares  = (raise_amount / offer_price)           # millions of new shares
        dilution    = new_shares / (shares_outstanding_millions + new_shares)
    else:
        dilution = 0.0

    diluted_delta_ev = delta_ev * (1.0 - dilution)

    return CapitalStructureAssessment(
        asset_id                   = catalyst.asset_id or "",
        catalyst_id                = catalyst.id,
        months_to_catalyst         = round(months_to_catalyst, 2),
        runway_months              = round(runway_months, 2),
        gap_months                 = round(gap_months, 2),
        capital_risk               = risk,
        raise_amount_millions      = round(raise_amount, 2),
        n_offerings_required       = n_offerings,
        effective_discount_pct     = round(effective_disc, 4),
        dilution_pct               = round(dilution, 6),
        diluted_delta_ev           = round(diluted_delta_ev, 2),
        liquidity_constrained      = liquidity_const,
        raise_exceeds_single_offering = n_offerings > 1,
    )


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _cfg(override: Optional[dict]) -> dict:
    if override is not None:
        return override
    try:
        from bve.config.assumptions_loader import AssumptionsLoader
        from bve.intelligence.trial_design_feature_extractor import _unfreeze
        data  = AssumptionsLoader.get()._data
        section = data.get("capital_structure")
        if section:
            return _unfreeze(section)
    except Exception:
        pass
    return dict(_CONFIG_DEFAULTS)
