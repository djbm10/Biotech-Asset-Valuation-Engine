"""
P3.4 — BD/HF output mode switch: mode-filtered views of ValuationOutput.

Two analyst perspectives draw on the same underlying valuation but emphasise
different signals:

BD Mode (Business Development)
    Focus: M&A targetability, acquirer fit, deal premium, strategic rationale.
    Headline metrics: M&A score, top acquirers, implied deal premium, EV / peak-sales.
    Action question: "Who would buy this, at what premium, and why?"

Trade Mode (Hedge Fund / Equity)
    Focus: Catalyst timing, implied POS gap, variant perception, probability-adjusted
    return, option value decomposition.
    Headline metrics: variant perception POS gap, catalyst delta-EV, MC P10/P90 spread,
    implied upside from NAV.
    Action question: "Where is the market wrong, and what is the risk/reward?"

Usage
-----
>>> from bve.analysis.output_mode import OutputMode, generate_mode_view
>>> view = generate_mode_view(output, OutputMode.BD)
>>> view.action_recommendation
'Initiate BD coverage: strong acquirer fit with Pfizer (0.82) ...'
>>> view = generate_mode_view(output, OutputMode.TRADE)
>>> view.headline_metrics["vp_pos_gap_pp"]
+12.3
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from bve.valuation.outputs import ValuationOutput


# ---------------------------------------------------------------------------
# Mode enum
# ---------------------------------------------------------------------------

class OutputMode(str, Enum):
    """Analyst perspective for mode-filtered output."""
    BD = "bd"       # Business development / M&A focus
    TRADE = "trade" # Hedge fund / equity trading focus

    def label(self) -> str:
        return {"bd": "Business Development", "trade": "Equity / Trade"}[self.value]


# ---------------------------------------------------------------------------
# Mode view result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModeView:
    """
    Mode-filtered view of a ValuationOutput.

    Attributes
    ----------
    mode : OutputMode
        The perspective this view was generated for.
    headline_metrics : dict[str, Any]
        Top 5–8 most decision-relevant numbers for this mode.
    narrative_sections : list[dict]
        Ordered list of ``{"title": str, "content": str}`` narrative blocks.
    action_recommendation : str
        One-sentence action recommendation for this mode's analyst audience.
    key_risks : list[str]
        Mode-specific risks the analyst should track.
    full_summary : dict[str, Any]
        Complete flat dict of all mode-relevant metrics (superset of headline_metrics).
    asset_name : str
        Asset name for display.
    company_name : str
        Company name for display.
    ticker : Optional[str]
        Stock ticker.
    """
    mode: OutputMode
    headline_metrics: dict[str, Any]
    narrative_sections: list[dict]
    action_recommendation: str
    key_risks: list[str]
    full_summary: dict[str, Any]
    asset_name: str
    company_name: str
    ticker: Optional[str]

    @property
    def mode_label(self) -> str:
        return self.mode.label()

    def section(self, title: str) -> Optional[str]:
        """Return the content of the section with the given title, or None."""
        for s in self.narrative_sections:
            if s.get("title") == title:
                return s.get("content")
        return None


# ---------------------------------------------------------------------------
# BD mode generator
# ---------------------------------------------------------------------------

def _generate_bd_view(output: "ValuationOutput") -> ModeView:
    rnpv = output.rnpv
    company = output.company
    asset = output.asset
    sd = output.summary_dict

    # Compute deal premium: typical biotech acquisition premium is 30–80% over NAV
    # Use implied_pos gap to flag if market under-prices the asset (BD opportunity)
    nav_ps = output.nav_per_share
    price = company.current_price
    deal_premium_pct: Optional[float] = None
    if price and price > 0 and nav_ps and nav_ps > 0:
        deal_premium_pct = round((nav_ps / price - 1) * 100, 1)

    # EV / peak sales multiple (comparable deal benchmark)
    ev_to_peak_sales: Optional[float] = None
    if rnpv.peak_sales_millions and rnpv.peak_sales_millions > 0:
        market_cap = (price * company.shares_outstanding_millions) if price else None
        net_cash = company.net_cash_millions
        if market_cap is not None:
            ev = market_cap - net_cash
            ev_to_peak_sales = round(ev / rnpv.peak_sales_millions, 2)

    # Top acquirers
    top1 = output.top_acquirers[0] if output.top_acquirers else None
    top2 = output.top_acquirers[1] if len(output.top_acquirers) > 1 else None

    # M&A targetability (from summary_dict if available)
    mna_score: Optional[float] = sd.get("mna_targetability_score")

    headline = {
        "model_rnpv_millions": rnpv.rnpv_millions,
        "peak_sales_millions": rnpv.peak_sales_millions,
        "nav_per_share": nav_ps,
        "implied_deal_premium_pct": deal_premium_pct,
        "ev_to_peak_sales": ev_to_peak_sales,
        "top_acquirer_1": top1.name if top1 else None,
        "top_acquirer_1_score": top1.composite_score if top1 else None,
        "mna_targetability_score": mna_score,
    }

    full = {**headline, **{
        "prob_approval_pct": sd.get("prob_approval_pct"),
        "years_to_launch": rnpv.years_to_launch,
        "top_acquirer_2": top2.name if top2 else None,
        "top_acquirer_2_score": top2.composite_score if top2 else None,
        "top_acquirer_1_rationale": top1.rationale if top1 else None,
        "loe_urgency_flag": top1.loe_urgency if top1 else None,
        "runway_months": sd.get("runway_months"),
        "net_cash_millions": company.net_cash_millions,
        "deal_catalyst": sd.get("catalyst_ev_label"),
    }}

    # Narrative sections
    sections: list[dict] = []

    strategic_rationale = (
        f"{asset.name} is a {asset.stage.value.replace('_', ' ')} asset in "
        f"{asset.therapeutic_area.value.replace('_', ' ')} ({asset.indication}). "
        f"Model rNPV of ${rnpv.rnpv_millions:,.0f}M with "
        f"{rnpv.cumulative_success_probability:.0%} P(approval)."
    )
    sections.append({"title": "Strategic Rationale", "content": strategic_rationale})

    if top1:
        acquirer_section = (
            f"Top acquirer fit: {top1.name} (score: {top1.composite_score:.2f}). "
            f"{top1.rationale} "
        )
        if top2:
            acquirer_section += f"Also consider: {top2.name} (score: {top2.composite_score:.2f})."
        sections.append({"title": "Acquirer Fit", "content": acquirer_section})

    if deal_premium_pct is not None:
        deal_section = (
            f"Model NAV of ${nav_ps:.2f}/share implies "
            f"{'a {:.0f}% premium'.format(deal_premium_pct) if deal_premium_pct > 0 else 'at-or-below market pricing'} "
            f"to the current price. "
            f"EV/peak-sales multiple: {ev_to_peak_sales:.2f}×." if ev_to_peak_sales else ""
        )
        sections.append({"title": "Deal Economics", "content": deal_section})

    catalyst = output.catalyst_payoff
    if catalyst:
        cat_section = (
            f"Catalyst EV: delta_ev = ${catalyst.delta_ev:+,.0f}M "
            f"({catalyst.ev_label}). "
            f"Upside ${catalyst.upside:,.0f}M / downside ${catalyst.downside:,.0f}M. "
            f"Asymmetry ratio: {catalyst.asymmetry_ratio:.1f}×."
        )
        sections.append({"title": "Catalyst Value", "content": cat_section})

    # Key risks for BD
    risks = [
        f"P(approval) = {rnpv.cumulative_success_probability:.0%} — regulatory risk remains the primary binary",
        "Integration risk post-acquisition if acquirer pipeline is complex",
        f"Peak-sales assumption (${rnpv.peak_sales_millions:,.0f}M) may be mis-set if competitive dynamics evolve",
    ]
    if sd.get("runway_months") and sd["runway_months"] < 12:
        risks.append(
            f"Cash runway < 12 months ({sd['runway_months']:.0f}mo) — "
            "deal or equity raise may be forced on unfavorable terms"
        )

    # Action
    if top1 and top1.composite_score >= 0.60:
        action = (
            f"Initiate BD coverage for {asset.name}: strong strategic fit with "
            f"{top1.name} (score {top1.composite_score:.2f}). "
            f"Model implies ${nav_ps:.2f}/share; at-market price represents "
            f"{'potential acquisition discount' if deal_premium_pct and deal_premium_pct > 10 else 'fair value'}."
        )
    else:
        action = (
            f"Monitor {asset.name} for BD opportunity. "
            f"Model rNPV ${rnpv.rnpv_millions:,.0f}M. "
            f"Acquirer fit moderate; revisit when nearer pivotal data."
        )

    return ModeView(
        mode=OutputMode.BD,
        headline_metrics=headline,
        narrative_sections=sections,
        action_recommendation=action,
        key_risks=risks,
        full_summary=full,
        asset_name=asset.name,
        company_name=company.name,
        ticker=company.ticker,
    )


# ---------------------------------------------------------------------------
# Trade mode generator
# ---------------------------------------------------------------------------

def _generate_trade_view(output: "ValuationOutput") -> ModeView:
    rnpv = output.rnpv
    company = output.company
    asset = output.asset
    sd = output.summary_dict
    mc = output.monte_carlo

    # Variant perception
    vp = output.variant_perception
    vp_pos_gap = sd.get("vp_pos_gap_pp")
    vp_implied_pos = sd.get("vp_implied_pos")
    vp_category = sd.get("vp_category")

    # Implied upside from NAV
    implied_upside = output.implied_upside_pct

    # MC distribution width (P90 - P10 as % of mean)
    mc_spread_pct: Optional[float] = None
    if mc.mean_millions and mc.mean_millions > 0:
        mc_spread_pct = round(
            (mc.percentile_90_millions - mc.percentile_10_millions) / mc.mean_millions * 100, 1
        )

    # Catalyst
    catalyst = output.catalyst_payoff

    headline = {
        "model_nav_per_share": output.nav_per_share,
        "current_price": company.current_price,
        "implied_upside_pct": implied_upside,
        "vp_pos_gap_pp": vp_pos_gap,
        "vp_implied_pos": vp_implied_pos,
        "vp_category": vp_category,
        "catalyst_delta_ev_millions": catalyst.delta_ev if catalyst else None,
        "catalyst_signal_strength": catalyst.signal_strength if catalyst else None,
    }

    full = {**headline, **{
        "mc_mean_millions": mc.mean_millions,
        "mc_p10_millions": mc.percentile_10_millions,
        "mc_p90_millions": mc.percentile_90_millions,
        "mc_spread_pct": mc_spread_pct,
        "mc_prob_positive_pct": sd.get("mc_prob_positive"),
        "model_pos": rnpv.cumulative_success_probability,
        "market_implied_pos": sd.get("market_implied_pos"),
        "market_pos_gap_pct": sd.get("market_pos_gap_pct"),
        "runway_months": sd.get("runway_months"),
        "dilution_flag": sd.get("dilution_flag"),
        "analog_median_peak_sales_millions": sd.get("analog_median_peak_sales_millions"),
    }}

    # Narrative sections
    sections: list[dict] = []

    # Market expectations section
    if vp_pos_gap is not None:
        sign = "+" if vp_pos_gap >= 0 else ""
        direction = "bullish" if vp_pos_gap > 0 else "bearish"
        expectation_content = (
            f"Model is {direction} vs market: model POS {rnpv.cumulative_success_probability:.0%} "
            f"vs market-implied {vp_implied_pos:.0%} ({sign}{vp_pos_gap:.1f}pp gap). "
            f"Variant perception category: {vp_category or 'indeterminate'}. "
            f"{vp.memo_interpretation if vp else ''}"
        )
    else:
        expectation_content = (
            f"Market price unavailable — no implied POS back-solve possible. "
            f"Model POS: {rnpv.cumulative_success_probability:.0%}."
        )
    sections.append({"title": "Market Expectations", "content": expectation_content})

    # Risk / return
    price = company.current_price
    nav_ps = output.nav_per_share
    if price and nav_ps:
        rr_content = (
            f"NAV: ${nav_ps:.2f}/share vs price ${price:.2f} "
            f"({'upside' if nav_ps > price else 'downside'}: "
            f"{'+' if implied_upside and implied_upside > 0 else ''}"
            f"{implied_upside:.1f}% if positive). "
            f"MC P10: ${mc.percentile_10_millions:,.0f}M / P90: ${mc.percentile_90_millions:,.0f}M "
            f"(spread: {mc_spread_pct:.0f}% of mean)."
            if mc_spread_pct else
            f"NAV: ${nav_ps:.2f}/share vs price ${price:.2f}."
        )
    else:
        rr_content = (
            f"MC P10: ${mc.percentile_10_millions:,.0f}M / P90: ${mc.percentile_90_millions:,.0f}M. "
            f"NAV: ${nav_ps:.2f}/share."
        )
    sections.append({"title": "Risk / Return", "content": rr_content})

    # Catalyst section
    if catalyst:
        cat_content = (
            f"Binary catalyst: delta_ev ${catalyst.delta_ev:+,.0f}M "
            f"({catalyst.ev_label}). "
            f"Signal strength: {catalyst.signal_strength:+.2f}. "
            f"Upside ${catalyst.upside:,.0f}M / downside ${catalyst.downside:,.0f}M "
            f"at current POS {catalyst.current_pos:.0%}. "
            f"{'Asymmetric upside.' if catalyst.is_asymmetric_upside else 'Symmetric or asymmetric downside.'}"
        )
        sections.append({"title": "Catalyst Payoff", "content": cat_content})

    # Key risks for trading
    risks = [
        f"Binary binary event risk: {rnpv.cumulative_success_probability:.0%} P(approval) — position sizing must reflect this",
        "Market-implied assumptions may converge to model faster/slower than expected",
    ]
    if sd.get("dilution_flag") in ("high", "moderate"):
        risks.append(
            f"Dilution risk: weighted dilution {sd.get('dilution_weighted_pct', '?')}% "
            f"({sd['dilution_flag']} — equity raise likely needed)"
        )
    if sd.get("runway_months") and sd["runway_months"] < 12:
        risks.append(
            f"Liquidity risk: {sd['runway_months']:.0f}-month cash runway — forced financing event possible"
        )
    if mc_spread_pct and mc_spread_pct > 150:
        risks.append("High MC spread (>150% of mean) — substantial tail risk in both directions")

    # Action
    if vp_pos_gap and abs(vp_pos_gap) >= 15:
        action = (
            f"Variant perception trade: model is {abs(vp_pos_gap):.0f}pp "
            f"{'above' if vp_pos_gap > 0 else 'below'} market-implied POS — "
            f"{'long' if vp_pos_gap > 0 else 'short'} on {asset.name} "
            f"{'ahead of positive catalyst' if catalyst and catalyst.delta_ev > 0 else 'on POS reconvergence thesis'}."
        )
    elif implied_upside and implied_upside >= 20:
        action = (
            f"NAV-discount opportunity: model implies ${nav_ps:.2f}/share "
            f"vs ${price:.2f} market ({implied_upside:.0f}% upside). "
            f"Long entry warranted if catalyst timing supportable."
        )
    else:
        action = (
            f"Monitor {asset.name}: insufficient variant perception edge identified. "
            f"Revisit if catalyst timeline becomes clearer or price dislocates."
        )

    return ModeView(
        mode=OutputMode.TRADE,
        headline_metrics=headline,
        narrative_sections=sections,
        action_recommendation=action,
        key_risks=risks,
        full_summary=full,
        asset_name=asset.name,
        company_name=company.name,
        ticker=company.ticker,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_mode_view(
    output: "ValuationOutput",
    mode: OutputMode,
) -> ModeView:
    """
    Generate a mode-filtered view of a ValuationOutput.

    Parameters
    ----------
    output : ValuationOutput
        Full valuation output from ValuationEngine.run().
    mode : OutputMode
        OutputMode.BD for business development / M&A perspective.
        OutputMode.TRADE for hedge fund / equity trading perspective.

    Returns
    -------
    ModeView
        Mode-specific headline metrics, narrative sections, action recommendation,
        and key risks.
    """
    if mode == OutputMode.BD:
        return _generate_bd_view(output)
    if mode == OutputMode.TRADE:
        return _generate_trade_view(output)
    raise ValueError(f"Unknown output mode: {mode!r}")
