"""Back-solve market-implied probability of success and peak sales from EV."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ImpliedPoSResult(BaseModel):
    asset_id: str
    ticker: str
    as_of_date: date
    current_ev_millions: float
    net_cash_millions: float
    pipeline_ev_millions: float          # ev - net_cash
    model_peak_sales_millions: float
    model_pos: float                     # 0-1
    gross_revenue_pv_millions: float     # PV of peak-sales stream at model assumptions
    trial_costs_pv_millions: float       # PV of R&D spend
    implied_pos: float                   # back-solved
    implied_peak_sales_millions: float   # back-solved holding pos constant
    pos_gap: float                       # model_pos - implied_pos  (positive = model bullish vs market)
    peak_sales_gap_millions: float       # model_peak - implied_peak
    mispricing_direction: str            # "underpriced" / "overpriced" / "aligned"
    mispricing_magnitude: str            # "large" / "moderate" / "small" / "none"
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    methodology: str = "pipeline_ev_backsolve"
    notes: list[str] = Field(default_factory=list)


def compute_implied_pos(
    *,
    asset_id: str,
    ticker: str,
    as_of_date: date,
    current_ev_millions: float,
    net_cash_millions: float,
    model_peak_sales_millions: float,
    model_pos: float,
    years_to_peak: float = 8.0,
    discount_rate: float = 0.10,
    peak_duration_years: float = 10.0,
    trial_costs_pv_millions: float = 0.0,
) -> ImpliedPoSResult:
    """
    Back-solve implied PoS and implied peak sales.

    Gross revenue PV = model_peak_sales × annuity_factor(discount_rate, peak_duration_years)
                       × discount(years_to_peak)
    Pipeline EV      = current_ev - net_cash
    Implied PoS      = (pipeline_ev + trial_costs_pv) / gross_revenue_pv
                       clamped to [0.0, 1.0]
    Implied peak     = model_peak × implied_pos / model_pos   (when model_pos > 0)

    pos_gap > 0.10      → "underpriced" / magnitude from gap size
    pos_gap < -0.10     → "overpriced"
    else                → "aligned"
    Magnitude: |gap| >= 0.30 → large, >= 0.15 → moderate, >= 0.05 → small, else none
    """
    pipeline_ev = current_ev_millions - net_cash_millions

    # Annuity factor at midpoint of commercial period
    # PV = peak × (1 - (1+r)^-n) / r × (1+r)^-years_to_peak
    if discount_rate > 0:
        annuity = (1 - (1 + discount_rate) ** (-peak_duration_years)) / discount_rate
    else:
        annuity = peak_duration_years
    discount_factor = (1 + discount_rate) ** (-years_to_peak)
    gross_revenue_pv = model_peak_sales_millions * annuity * discount_factor

    if gross_revenue_pv <= 0:
        implied_pos = 0.0
    else:
        implied_pos = max(0.0, min(1.0, (pipeline_ev + trial_costs_pv_millions) / gross_revenue_pv))

    if model_pos > 0:
        implied_peak = model_peak_sales_millions * implied_pos / model_pos
    else:
        implied_peak = 0.0

    pos_gap = model_pos - implied_pos
    peak_gap = model_peak_sales_millions - implied_peak

    abs_gap = abs(pos_gap)
    if abs_gap >= 0.10:
        direction = "underpriced" if pos_gap > 0 else "overpriced"
    else:
        direction = "aligned"
    if abs_gap >= 0.30:
        magnitude = "large"
    elif abs_gap >= 0.15:
        magnitude = "moderate"
    elif abs_gap >= 0.05:
        magnitude = "small"
    else:
        magnitude = "none"

    notes = []
    if pipeline_ev < 0:
        notes.append("Pipeline EV is negative — net cash exceeds market cap; implied PoS not meaningful")
    if trial_costs_pv_millions == 0:
        notes.append("Trial cost PV not provided; implied PoS may be understated")

    return ImpliedPoSResult(
        asset_id=asset_id, ticker=ticker, as_of_date=as_of_date,
        current_ev_millions=current_ev_millions, net_cash_millions=net_cash_millions,
        pipeline_ev_millions=pipeline_ev,
        model_peak_sales_millions=model_peak_sales_millions, model_pos=model_pos,
        gross_revenue_pv_millions=gross_revenue_pv, trial_costs_pv_millions=trial_costs_pv_millions,
        implied_pos=implied_pos, implied_peak_sales_millions=implied_peak,
        pos_gap=pos_gap, peak_sales_gap_millions=peak_gap,
        mispricing_direction=direction, mispricing_magnitude=magnitude,
        notes=notes,
    )
