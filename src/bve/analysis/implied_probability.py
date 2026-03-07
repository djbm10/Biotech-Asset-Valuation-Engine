"""
Market-implied probability analysis.

The core question for every biotech investment decision:

  "What does the market believe, and where does our model disagree?"

This module back-solves implied assumptions from market price, enabling
the "variant perception" table that separates institutional analysis
from basic DCF work.

Two back-solve directions
--------------------------
1. Implied P(approval): given model peak sales, what POS does the market price?
   => P_implied = (market_cap - net_cash + trial_costs_pv) / gross_revenue_pv

2. Implied peak sales: given model POS, what peak sales does the market price?
   => implied_peak = model_peak × (market_implied_rnpv + trial_costs_pv)
                                  / (model_pos × gross_revenue_pv)

Usage
-----
    from bve.analysis.implied_probability import compute_implied_market_assumptions

    result = compute_implied_market_assumptions(valuation_output)
    print(result.summary())
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ImpliedMarketAssumptions:
    """
    The market's implicit assumptions, back-solved from current stock price.

    All values are derived; none are modeled. They represent what must be
    true for the current stock price to be "fair value" under each
    back-solve assumption.
    """
    # Inputs from market
    current_price: float
    shares_outstanding_millions: float
    market_cap_millions: float
    net_cash_millions: float
    implied_enterprise_value_millions: float    # market_cap - net_cash (asset-level proxy)

    # Back-solve 1: given model peak sales, what POS does market imply?
    model_peak_sales_millions: float
    implied_pos: Optional[float]                # None if < 0 or > 1 (extreme mispricing)
    model_pos: float                            # our model's P(approval)
    pos_gap_pp: Optional[float]                 # implied - model, in percentage points

    # Back-solve 2: given model POS, what peak sales does market imply?
    implied_peak_sales_millions: Optional[float]
    peak_sales_gap_millions: Optional[float]    # implied - model

    # Structural inputs used in the derivation
    gross_revenue_pv_millions: float            # PV of commercial cash flows if approved
    trial_costs_pv_millions: float              # weighted PV of remaining trial costs

    def is_undervalued(self) -> Optional[bool]:
        """True if market-implied POS < model POS (market too pessimistic)."""
        if self.implied_pos is None:
            return None
        return self.implied_pos < self.model_pos

    def mispricing_direction(self) -> str:
        if self.implied_pos is None:
            return "indeterminate"
        if self.implied_pos < self.model_pos:
            return "undervalued (market too pessimistic)"
        elif self.implied_pos > self.model_pos:
            return "overvalued (market too optimistic)"
        return "fairly valued"

    def summary(self) -> str:
        lines = [
            "\nMarket-Implied vs. Model Assumptions",
            "=" * 50,
            f"  Market cap:                    ${self.market_cap_millions:>8,.0f}M",
            f"  Net cash:                      ${self.net_cash_millions:>8,.0f}M",
            f"  Implied EV (asset):            ${self.implied_enterprise_value_millions:>8,.0f}M",
            "",
            "  Back-solve 1 — Given model peak sales, what POS does market imply?",
            f"  Model peak sales:              ${self.model_peak_sales_millions:>8,.0f}M",
            f"  Model P(approval):             {self.model_pos:>9.1%}",
            f"  Market-implied P(approval):    {self.implied_pos:>9.1%}" if self.implied_pos is not None
                else "  Market-implied P(approval):    <0% (deep discount to model)",
        ]
        if self.pos_gap_pp is not None:
            sign = "+" if self.pos_gap_pp >= 0 else ""
            lines.append(f"  POS gap (model − implied):     {sign}{self.pos_gap_pp:>7.1f}pp")
        lines += [
            "",
            "  Back-solve 2 — Given model POS, what peak sales does market imply?",
            f"  Model POS used:                {self.model_pos:>9.1%}",
        ]
        if self.implied_peak_sales_millions is not None:
            lines.append(f"  Implied peak sales:            ${self.implied_peak_sales_millions:>8,.0f}M")
        if self.peak_sales_gap_millions is not None:
            sign = "+" if self.peak_sales_gap_millions >= 0 else ""
            lines.append(f"  Peak sales gap (model − mkt):  ${sign}{self.peak_sales_gap_millions:>7,.0f}M")
        lines += [
            "",
            f"  Verdict: {self.mispricing_direction()}",
            "=" * 50,
        ]
        return "\n".join(lines)


def compute_implied_market_assumptions(output) -> Optional[ImpliedMarketAssumptions]:
    """
    Back-solve market-implied probability and peak sales from a ValuationOutput.

    Parameters
    ----------
    output: ValuationOutput

    Returns
    -------
    ImpliedMarketAssumptions, or None if current_price is not available.
    """
    price = output.company.current_price
    if not price or price <= 0:
        return None

    shares = output.company.shares_outstanding_millions
    net_cash = output.company.net_cash_millions
    market_cap = price * shares
    implied_ev = market_cap - net_cash        # market's implied rNPV

    gross_pv = output.rnpv.gross_revenue_pv_millions
    costs_pv = output.rnpv.trial_costs_pv_millions
    model_pos = output.rnpv.cumulative_success_probability
    model_peak = output.rnpv.peak_sales_millions

    # Back-solve 1: implied POS
    # rNPV = P × gross_pv - costs_pv  => P = (implied_ev + costs_pv) / gross_pv
    if gross_pv > 0:
        raw_pos = (implied_ev + costs_pv) / gross_pv
        implied_pos = round(max(0.0, min(1.0, raw_pos)), 4) if raw_pos > 0 else None
        pos_gap_pp = round((model_pos - (raw_pos if raw_pos > 0 else 0)) * 100, 1)
    else:
        implied_pos = None
        pos_gap_pp = None

    # Back-solve 2: implied peak sales (given model POS)
    # rNPV = model_pos × gross_pv(peak) - costs_pv
    # gross_pv ∝ peak_sales (linear scaling)
    # => implied_peak = model_peak × (implied_ev + costs_pv) / (model_pos × gross_pv)
    if model_pos > 0 and gross_pv > 0:
        implied_gross_pv = (implied_ev + costs_pv) / model_pos
        implied_peak = round(model_peak * implied_gross_pv / gross_pv, 1)
        peak_gap = round(model_peak - implied_peak, 1)
    else:
        implied_peak = None
        peak_gap = None

    return ImpliedMarketAssumptions(
        current_price=price,
        shares_outstanding_millions=shares,
        market_cap_millions=round(market_cap, 1),
        net_cash_millions=round(net_cash, 1),
        implied_enterprise_value_millions=round(implied_ev, 1),
        model_peak_sales_millions=model_peak,
        implied_pos=implied_pos,
        model_pos=model_pos,
        pos_gap_pp=pos_gap_pp,
        implied_peak_sales_millions=implied_peak,
        peak_sales_gap_millions=peak_gap,
        gross_revenue_pv_millions=round(gross_pv, 1),
        trial_costs_pv_millions=round(costs_pv, 1),
    )
