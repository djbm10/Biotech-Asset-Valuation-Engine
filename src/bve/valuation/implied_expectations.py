"""
Implied-expectations engine — Step 5.

Back-solves market-implied PoS and peak-sales from observed market cap
and net cash, then compares them against the model's own estimates to
produce an actionable cheapness/richness signal.

Design principles
-----------------
- Pure functions; no network or LLM calls.
- Division-by-zero always returns None rather than raising.
- Frozen Pydantic v2 models throughout.
"""
from __future__ import annotations

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Input / output containers
# ---------------------------------------------------------------------------


class ImpliedExpectationsInput(BaseModel):
    """All parameters needed to compute implied market expectations."""

    model_config = {"frozen": True}

    asset_id: str
    market_cap_usd: float
    net_cash_usd: float
    discount_rate: float = 0.10
    years_to_approval: float = 3.0
    peak_sales_millions: float | None = None
    model_pos: float | None = None
    royalty_rate: float = 0.0
    tax_rate: float = 0.25
    ebit_margin: float = 0.40
    patent_life_years: float = 10.0


class ImpliedExpectationsResult(BaseModel):
    """
    Output of the implied-expectations engine.

    All monetary units in USD (not millions) unless the field name says
    ``_millions``.  ``pipeline_value_usd`` is the raw equity value attributed
    to the pipeline (market_cap - net_cash).
    """

    model_config = {"frozen": True}

    asset_id: str
    pipeline_value_usd: float
    implied_pos: float | None
    implied_peak_sales_millions: float | None
    model_pos: float | None
    model_peak_sales_millions: float | None
    pos_gap: float | None
    peak_sales_gap_millions: float | None
    signal: str
    confidence: str
    low_confidence_reason: str | None
    platform_residual_usd: float | None


# ---------------------------------------------------------------------------
# Core math helpers
# ---------------------------------------------------------------------------


def _npv_per_dollar_peak_sales(
    discount_rate: float,
    years_to_approval: float,
    ebit_margin: float,
    patent_life_years: float,
    tax_rate: float,
    royalty_rate: float,
) -> float:
    """
    Return the NPV of $1M of peak annual sales as an annuity.

    Revenue ramp: triangle up to peak over 5 years, then flat.
    Each year t (1-indexed from launch):
        revenue_fraction  = min(t / 5, 1.0)
        ebit_t            = 1M * revenue_fraction * ebit_margin * (1 - royalty_rate)
        after_tax_t       = ebit_t * (1 - tax_rate)
        discount factor   = 1 / (1 + discount_rate)^(years_to_approval + t)

    Returns the sum of all discounted after-tax cash flows per $1M peak sales.
    If patent_life_years is 0 the sum is 0.
    """
    total = 0.0
    n = int(patent_life_years)
    for t in range(1, n + 1):
        revenue_fraction = min(t / 5.0, 1.0)
        ebit_t = revenue_fraction * ebit_margin * (1.0 - royalty_rate)
        after_tax_t = ebit_t * (1.0 - tax_rate)
        exponent = years_to_approval + float(t)
        discount_factor = (1.0 + discount_rate) ** exponent
        if discount_factor > 0:
            total += after_tax_t / discount_factor
    return total


# ---------------------------------------------------------------------------
# Back-solvers
# ---------------------------------------------------------------------------


def solve_implied_pos(inp: ImpliedExpectationsInput) -> float | None:
    """
    Given pipeline_value and model peak_sales, back-solve for P(approval).

    Returns None when peak_sales_millions is None or <= 0.
    Allows up to 1.5 to accommodate platform optionality; caller detects
    values above 1.0 and may flag a platform residual.
    """
    if inp.peak_sales_millions is None or inp.peak_sales_millions <= 0:
        return None

    npv_factor = _npv_per_dollar_peak_sales(
        discount_rate=inp.discount_rate,
        years_to_approval=inp.years_to_approval,
        ebit_margin=inp.ebit_margin,
        patent_life_years=inp.patent_life_years,
        tax_rate=inp.tax_rate,
        royalty_rate=inp.royalty_rate,
    )
    if npv_factor <= 0:
        return None

    pipeline_value_usd = inp.market_cap_usd - inp.net_cash_usd
    # Convert peak_sales_millions to USD-denominated pipeline value
    pipeline_value_per_million = npv_factor * 1_000_000.0  # NPV per $1M peak in USD

    denominator = inp.peak_sales_millions * pipeline_value_per_million
    if denominator == 0:
        return None

    raw = pipeline_value_usd / denominator
    # Clamp to [0.0, 1.5] — values above 1 indicate platform optionality
    return float(max(0.0, min(1.5, raw)))


def solve_implied_peak_sales(inp: ImpliedExpectationsInput) -> float | None:
    """
    Given pipeline_value and model PoS, back-solve for peak sales.

    Returns None when model_pos is None or <= 0.
    Returned value is in millions (USD).  Can be negative when pipeline_value < 0.
    """
    if inp.model_pos is None or inp.model_pos <= 0:
        return None

    npv_factor = _npv_per_dollar_peak_sales(
        discount_rate=inp.discount_rate,
        years_to_approval=inp.years_to_approval,
        ebit_margin=inp.ebit_margin,
        patent_life_years=inp.patent_life_years,
        tax_rate=inp.tax_rate,
        royalty_rate=inp.royalty_rate,
    )
    if npv_factor <= 0:
        return None

    pipeline_value_usd = inp.market_cap_usd - inp.net_cash_usd
    # denominator: model_pos * npv_factor * 1M (to express in millions)
    denominator = inp.model_pos * npv_factor * 1_000_000.0

    if denominator == 0:
        return None

    return pipeline_value_usd / denominator  # in millions


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def compute_implied_expectations(inp: ImpliedExpectationsInput) -> ImpliedExpectationsResult:
    """
    Produce a full implied-expectations report for one asset.

    Steps:
    1. Compute pipeline_value = market_cap - net_cash (can be negative).
    2. Back-solve implied_pos (if peak_sales provided).
    3. Back-solve implied_peak_sales (if model_pos provided).
    4. Derive gaps and signal.
    5. Assess confidence and platform residual.
    """
    pipeline_value_usd = inp.market_cap_usd - inp.net_cash_usd

    implied_pos = solve_implied_pos(inp)
    implied_peak_sales_millions = solve_implied_peak_sales(inp)

    # Gaps
    pos_gap: float | None = None
    if implied_pos is not None and inp.model_pos is not None:
        pos_gap = implied_pos - inp.model_pos

    peak_sales_gap_millions: float | None = None
    if implied_peak_sales_millions is not None and inp.peak_sales_millions is not None:
        peak_sales_gap_millions = implied_peak_sales_millions - inp.peak_sales_millions

    # Signal
    if implied_pos is None and implied_peak_sales_millions is None:
        signal = "INSUFFICIENT_DATA"
    elif pos_gap is not None and pos_gap < -0.10:
        signal = "UNDERPRICED"
    elif peak_sales_gap_millions is not None and peak_sales_gap_millions < -200:
        signal = "UNDERPRICED"
    elif pos_gap is not None and pos_gap > 0.10:
        signal = "OVERPRICED"
    elif peak_sales_gap_millions is not None and peak_sales_gap_millions > 200:
        signal = "OVERPRICED"
    else:
        signal = "FAIRLY_VALUED"

    # Confidence
    low_confidence_reason: str | None = None
    if pipeline_value_usd < 0:
        confidence = "LOW"
        low_confidence_reason = (
            "Net cash exceeds market cap — pipeline value is negative, "
            "signal is unreliable."
        )
    elif implied_pos is not None and implied_pos > 1.0:
        confidence = "LOW"
        low_confidence_reason = (
            "Implied PoS exceeds 1.0, suggesting significant platform optionality "
            "not captured by the single-asset model."
        )
    elif 0 <= pipeline_value_usd < 50_000_000:
        confidence = "MEDIUM"
        low_confidence_reason = (
            "Pipeline value is below $50M — small-cap noise may dominate the signal."
        )
    else:
        confidence = "HIGH"

    # Platform residual
    platform_residual_usd: float | None = None
    if implied_pos is not None and implied_pos > 1.0 and inp.peak_sales_millions is not None:
        npv_factor = _npv_per_dollar_peak_sales(
            discount_rate=inp.discount_rate,
            years_to_approval=inp.years_to_approval,
            ebit_margin=inp.ebit_margin,
            patent_life_years=inp.patent_life_years,
            tax_rate=inp.tax_rate,
            royalty_rate=inp.royalty_rate,
        )
        single_asset_value_usd = inp.peak_sales_millions * npv_factor * 1_000_000.0 * 1.0
        platform_residual_usd = pipeline_value_usd - single_asset_value_usd

    return ImpliedExpectationsResult(
        asset_id=inp.asset_id,
        pipeline_value_usd=pipeline_value_usd,
        implied_pos=implied_pos,
        implied_peak_sales_millions=implied_peak_sales_millions,
        model_pos=inp.model_pos,
        model_peak_sales_millions=inp.peak_sales_millions,
        pos_gap=pos_gap,
        peak_sales_gap_millions=peak_sales_gap_millions,
        signal=signal,
        confidence=confidence,
        low_confidence_reason=low_confidence_reason,
        platform_residual_usd=platform_residual_usd,
    )
