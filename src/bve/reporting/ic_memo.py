"""
P3.6 — IC-ready memo generator: IC/BD best-practice section structure.

Generates structured Investment Committee (IC) memos from a ValuationOutput.
Two memo types mirror the BD/TRADE output mode distinction:

IC_BD (Business Development IC Memo)
    Audience: BD team, deal committee, acquirer relationship managers.
    Sections: Executive Summary → Asset Profile → Market Opportunity →
              Competitive Landscape → Deal Valuation → Acquirer Analysis →
              Risk Factors → Recommendation
    Focus: deal rationale, synergy case, acquirer fit, premium analysis.

IC_TRADE (Equity Trading IC Memo)
    Audience: Portfolio manager, investment committee, risk committee.
    Sections: Executive Summary → Investment Thesis → Clinical Evidence →
              Market Opportunity → Variant Perception → Risk / Return →
              Catalyst Analysis → Recommendation
    Focus: variant perception, POS gap, risk/reward, catalyst timing.

Usage
-----
>>> from bve.reporting.ic_memo import generate_ic_memo, ICMemoType
>>> memo = generate_ic_memo(output, ICMemoType.BD)
>>> print(memo.full_text)
>>> print(memo.section("Recommendation"))
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bve.valuation.outputs import ValuationOutput


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ICMemoType(str, Enum):
    BD = "ic_bd"
    TRADE = "ic_trade"


@dataclass(frozen=True)
class ICMemoSection:
    """A single section in an IC memo."""
    title: str
    content: str
    required: bool = True


@dataclass(frozen=True)
class ICMemo:
    """
    Structured IC memo output.

    Attributes
    ----------
    memo_type : ICMemoType
        BD or TRADE perspective.
    sections : list[ICMemoSection]
        Ordered sections of the memo.
    asset_name : str
    company_name : str
    ticker : Optional[str]
    """
    memo_type: ICMemoType
    sections: tuple  # tuple[ICMemoSection, ...]
    asset_name: str
    company_name: str
    ticker: Optional[str]

    @property
    def full_text(self) -> str:
        """Render all sections as Markdown."""
        parts = [
            f"# {self.asset_name} — {'BD' if self.memo_type == ICMemoType.BD else 'Equity'} IC Memo",
            f"**Company:** {self.company_name}"
            + (f" ({self.ticker})" if self.ticker else ""),
            "",
        ]
        for s in self.sections:
            parts.append(f"## {s.title}")
            parts.append(s.content)
            parts.append("")
        return "\n".join(parts)

    def as_markdown(self) -> str:
        """Alias for full_text."""
        return self.full_text

    @property
    def word_count(self) -> int:
        return len(self.full_text.split())

    def section(self, title: str) -> Optional[str]:
        """Return content of named section, or None."""
        for s in self.sections:
            if s.title == title:
                return s.content
        return None


# ---------------------------------------------------------------------------
# BD IC memo builder
# ---------------------------------------------------------------------------

def _build_bd_memo(output: "ValuationOutput") -> ICMemo:
    asset = output.asset
    company = output.company
    rnpv = output.rnpv
    sd = output.summary_dict
    mc = output.monte_carlo

    nav_ps = output.nav_per_share
    price = company.current_price
    top1 = output.top_acquirers[0] if output.top_acquirers else None
    top2 = output.top_acquirers[1] if len(output.top_acquirers) > 1 else None
    mna_score = sd.get("mna_targetability_score")
    prob_approval = rnpv.cumulative_success_probability

    sections: list[ICMemoSection] = []

    # 1. Executive Summary
    deal_premium_str = ""
    if price and price > 0 and nav_ps:
        prem = (nav_ps / price - 1) * 100
        deal_premium_str = (
            f" Model NAV of ${nav_ps:.2f}/share implies a "
            f"{'%.0f%%' % prem} {'premium' if prem > 0 else 'discount'} to market."
        )
    exec_summary = (
        f"{asset.name} is a {asset.stage.value.replace('_', ' ').title()} "
        f"{asset.modality.value.replace('_', ' ')} in "
        f"{asset.indication} ({asset.therapeutic_area.value.replace('_', ' ').title()}). "
        f"Model rNPV: **${rnpv.rnpv_millions:,.0f}M** with "
        f"**{prob_approval:.0%}** cumulative P(approval)."
        f"{deal_premium_str}"
        + (f" M&A targetability score: {mna_score:.2f}." if mna_score else "")
    )
    sections.append(ICMemoSection("Executive Summary", exec_summary, required=True))

    # 2. Asset Profile
    asset_profile = (
        f"**Asset:** {asset.name}  \n"
        f"**Indication:** {asset.indication}  \n"
        f"**Modality:** {asset.modality.value.replace('_', ' ').title()}  \n"
        f"**Stage:** {asset.stage.value.replace('_', ' ').title()}  \n"
        f"**Therapeutic area:** {asset.therapeutic_area.value.replace('_', ' ').title()}  \n"
        f"**Cumulative P(approval):** {prob_approval:.0%}  \n"
        f"**Years to launch:** {rnpv.years_to_launch:.1f}y"
    )
    sections.append(ICMemoSection("Asset Profile", asset_profile, required=True))

    # 3. Market Opportunity
    peak_sales = rnpv.peak_sales_millions
    market_opp = (
        f"Peak sales assumption: **${peak_sales:,.0f}M** at model penetration. "
        f"Total addressable market (TAM): ${output.market_model.total_addressable_market_millions:,.0f}M. "
    )
    if sd.get("analog_median_peak_sales_millions"):
        market_opp += (
            f"Launch analog median peak sales: ${sd['analog_median_peak_sales_millions']:,.0f}M."
        )
    sections.append(ICMemoSection("Market Opportunity", market_opp, required=True))

    # 4. Competitive Landscape
    n_comp = len(asset.competitor_assets) if hasattr(asset, "competitor_assets") else 0
    comp_section = (
        f"Competitive set includes {n_comp} tracked asset(s). "
        f"Market share analysis and crowding assumptions are embedded in the revenue model."
    )
    sections.append(ICMemoSection("Competitive Landscape", comp_section, required=False))

    # 5. Deal Valuation
    bull = sd.get("scenario_bull_rnpv_millions")
    bear = sd.get("scenario_bear_rnpv_millions")
    deal_val = (
        f"**Model rNPV:** ${rnpv.rnpv_millions:,.0f}M  \n"
        + (f"**Bull case NAV:** ${bull:,.0f}M  \n" if bull is not None else "")
        + (f"**Bear case NAV:** ${bear:,.0f}M  \n" if bear is not None else "")
        + f"**MC P10:** ${mc.percentile_10_millions:,.0f}M  \n"
        + f"**MC P90:** ${mc.percentile_90_millions:,.0f}M  \n"
    )
    if nav_ps:
        deal_val += f"**NAV/share:** ${nav_ps:.2f}  \n"
    if price and price > 0:
        ev_ps = price * company.shares_outstanding_millions - company.net_cash_millions
        deal_val += f"**Current EV:** ${ev_ps:,.0f}M (@ ${price:.2f}/share)  \n"
    sections.append(ICMemoSection("Deal Valuation", deal_val, required=True))

    # 6. Acquirer Analysis
    if top1:
        acq_text = (
            f"**Top acquirer fit:** {top1.name} (score: {top1.composite_score:.2f}).  \n"
            f"{top1.rationale}  \n"
        )
        if top2:
            acq_text += f"\n**Runner-up:** {top2.name} (score: {top2.composite_score:.2f})."
    else:
        acq_text = "No acquirer universe loaded. Run acquirer matrix analysis for targeted BD outreach."
    sections.append(ICMemoSection("Acquirer Analysis", acq_text, required=True))

    # 7. Risk Factors
    risks = [
        f"**Regulatory/clinical:** P(approval) = {prob_approval:.0%} — trial failure is the primary binary risk",
        f"**Commercial:** Peak-sales assumption of ${peak_sales:,.0f}M may prove optimistic if competitive dynamics shift",
        "**Integration:** Post-deal value realization depends on acquirer execution capability",
    ]
    if sd.get("runway_months") and sd["runway_months"] < 18:
        risks.append(
            f"**Liquidity:** Cash runway {sd['runway_months']:.0f} months — "
            f"equity raise or deal required within 18 months"
        )
    risk_text = "\n".join(f"- {r}" for r in risks)
    sections.append(ICMemoSection("Risk Factors", risk_text, required=True))

    # 8. Recommendation
    if top1 and top1.composite_score >= 0.55:
        rec = (
            f"**Initiate BD engagement.** {asset.name} represents a compelling "
            f"acquisition target with {prob_approval:.0%} P(approval) and "
            f"${peak_sales:,.0f}M peak-sales potential. Strong strategic fit "
            f"with {top1.name} (score {top1.composite_score:.2f}). "
            f"Recommend proceeding to NDA/term-sheet discussions."
        )
    elif mna_score and mna_score >= 0.40:
        rec = (
            f"**Monitor and prepare.** {asset.name} scores {mna_score:.2f} on M&A "
            f"targetability. Begin preliminary BD outreach but await Phase 3 data "
            f"readout before formal term-sheet discussions."
        )
    else:
        rec = (
            f"**Watch list.** {asset.name} does not yet meet threshold for active BD engagement. "
            f"Revisit when nearer pivotal data or if competitive landscape shifts."
        )
    sections.append(ICMemoSection("Recommendation", rec, required=True))

    return ICMemo(
        memo_type=ICMemoType.BD,
        sections=tuple(sections),
        asset_name=asset.name,
        company_name=company.name,
        ticker=company.ticker,
    )


# ---------------------------------------------------------------------------
# TRADE IC memo builder
# ---------------------------------------------------------------------------

def _build_trade_memo(output: "ValuationOutput") -> ICMemo:
    asset = output.asset
    company = output.company
    rnpv = output.rnpv
    sd = output.summary_dict
    mc = output.monte_carlo
    vp = output.variant_perception

    nav_ps = output.nav_per_share
    price = company.current_price
    prob_approval = rnpv.cumulative_success_probability
    implied_upside = output.implied_upside_pct

    sections: list[ICMemoSection] = []

    # 1. Executive Summary
    upside_str = ""
    if implied_upside is not None:
        upside_str = f" Implied upside to NAV: **{implied_upside:+.0f}%**."
    exec_summary = (
        f"{asset.name} ({company.ticker or company.name}) — "
        f"{asset.stage.value.replace('_', ' ').title()} {asset.modality.value.replace('_', ' ')} "
        f"in {asset.indication}. "
        f"Model P(approval): **{prob_approval:.0%}**. "
        f"Model NAV: **${nav_ps:.2f}/share** vs "
        f"{'${:.2f} market price'.format(price) if price else 'N/A market price'}."
        f"{upside_str}"
    )
    sections.append(ICMemoSection("Executive Summary", exec_summary, required=True))

    # 2. Investment Thesis
    vp_gap = sd.get("vp_pos_gap_pp")
    if vp_gap and abs(vp_gap) >= 10:
        thesis = (
            f"Model P(approval) ({prob_approval:.0%}) is "
            f"{'above' if vp_gap > 0 else 'below'} market-implied "
            f"({sd.get('vp_implied_pos', 'N/A'):.0%} implied POS) by "
            f"**{abs(vp_gap):.0f}pp**. "
            f"This variant perception gap is the primary investment edge. "
            f"Category: **{sd.get('vp_category', 'indeterminate')}**."
        )
    elif implied_upside and implied_upside >= 15:
        thesis = (
            f"NAV discount thesis: model NAV of ${nav_ps:.2f}/share vs "
            f"${price:.2f} current price ({implied_upside:+.0f}% upside). "
            f"Risk/reward is asymmetric given {prob_approval:.0%} P(approval)."
        )
    else:
        thesis = (
            f"Opportunistic catalyst play: {asset.name} presents a binary event "
            f"with {prob_approval:.0%} P(approval). Position sizing should reflect "
            f"the binary nature of the upcoming catalyst."
        )
    sections.append(ICMemoSection("Investment Thesis", thesis, required=True))

    # 3. Clinical Evidence
    clinical = (
        f"**Stage:** {asset.stage.value.replace('_', ' ').title()}  \n"
        f"**Indication:** {asset.indication}  \n"
        f"**Modality:** {asset.modality.value.replace('_', ' ').title()}  \n"
        f"**Cumulative P(approval):** {prob_approval:.0%}  \n"
        f"**Years to launch:** {rnpv.years_to_launch:.1f}y  \n"
        f"**Model rNPV:** ${rnpv.rnpv_millions:,.0f}M"
    )
    sections.append(ICMemoSection("Clinical Evidence", clinical, required=True))

    # 4. Market Opportunity
    market_opp = (
        f"Peak sales: **${rnpv.peak_sales_millions:,.0f}M** at modeled penetration. "
        f"TAM: ${output.market_model.total_addressable_market_millions:,.0f}M."
    )
    sections.append(ICMemoSection("Market Opportunity", market_opp, required=False))

    # 5. Variant Perception
    if vp:
        vp_text = (
            f"Market-implied POS back-solve: "
            f"**{sd.get('vp_implied_pos', 0.0):.0%}** implied vs "
            f"**{prob_approval:.0%}** model POS "
            f"(**{vp_gap:+.1f}pp** gap).  \n"
            f"Category: {sd.get('vp_category', 'indeterminate')}.  \n"
            f"{vp.memo_interpretation}"
        )
    else:
        vp_text = (
            "Market price unavailable — variant perception back-solve cannot be computed. "
            f"Model P(approval): {prob_approval:.0%}."
        )
    sections.append(ICMemoSection("Variant Perception", vp_text, required=True))

    # 6. Risk / Return
    mc_spread = (
        round((mc.percentile_90_millions - mc.percentile_10_millions) / mc.mean_millions * 100, 0)
        if mc.mean_millions else None
    )
    rr_text = (
        f"**NAV/share:** ${nav_ps:.2f}  \n"
        + (f"**Current price:** ${price:.2f}  \n" if price else "")
        + (f"**Implied upside:** {implied_upside:+.0f}%  \n" if implied_upside else "")
        + f"**MC P10:** ${mc.percentile_10_millions:,.0f}M  \n"
        + f"**MC P90:** ${mc.percentile_90_millions:,.0f}M  \n"
        + (f"**MC spread:** {mc_spread:.0f}% of mean  \n" if mc_spread else "")
    )
    sections.append(ICMemoSection("Risk / Return", rr_text, required=True))

    # 7. Catalyst Analysis
    catalyst = output.catalyst_payoff
    if catalyst:
        cat_text = (
            f"Binary catalyst: delta-EV **${catalyst.delta_ev:+,.0f}M** "
            f"({catalyst.ev_label}).  \n"
            f"Upside ${catalyst.upside:,.0f}M / downside ${catalyst.downside:,.0f}M.  \n"
            f"{'Asymmetric upside.' if catalyst.is_asymmetric_upside else 'Symmetric / asymmetric downside.'}  \n"
            f"Signal strength: {catalyst.signal_strength:+.2f}."
        )
    else:
        cat_text = "No catalyst payoff data loaded. Assess upcoming trial readout timing."
    sections.append(ICMemoSection("Catalyst Analysis", cat_text, required=False))

    # 8. Recommendation
    if vp_gap and abs(vp_gap) >= 15:
        direction = "long" if vp_gap > 0 else "short"
        rec = (
            f"**Initiate {direction.upper()} position.** {abs(vp_gap):.0f}pp variant "
            f"perception gap warrants a {direction} in {asset.name}. "
            f"Size at 1–2% of portfolio given {prob_approval:.0%} binary risk. "
            f"Exit at data readout or on POS gap convergence."
        )
    elif implied_upside and implied_upside >= 20:
        rec = (
            f"**Add / initiate long.** NAV discount of {implied_upside:.0f}% offers "
            f"favorable risk/reward. Position 1–3% of portfolio. "
            f"Stop-loss at 20–25% below entry."
        )
    else:
        rec = (
            f"**Monitor / hold.** Insufficient variant perception edge at current price. "
            f"Revisit if price dislocates meaningfully from NAV or catalyst timeline firms up."
        )
    sections.append(ICMemoSection("Recommendation", rec, required=True))

    return ICMemo(
        memo_type=ICMemoType.TRADE,
        sections=tuple(sections),
        asset_name=asset.name,
        company_name=company.name,
        ticker=company.ticker,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_ic_memo(
    output: "ValuationOutput",
    memo_type: ICMemoType,
) -> ICMemo:
    """
    Generate an IC-ready memo from a ValuationOutput.

    Parameters
    ----------
    output : ValuationOutput
        Full valuation output from ValuationEngine.run().
    memo_type : ICMemoType
        ICMemoType.BD for business development / deal committee.
        ICMemoType.TRADE for equity trading / investment committee.

    Returns
    -------
    ICMemo
        Structured memo with ordered sections, full_text, and section() accessor.
    """
    if memo_type == ICMemoType.BD:
        return _build_bd_memo(output)
    if memo_type == ICMemoType.TRADE:
        return _build_trade_memo(output)
    raise ValueError(f"Unknown IC memo type: {memo_type!r}")
