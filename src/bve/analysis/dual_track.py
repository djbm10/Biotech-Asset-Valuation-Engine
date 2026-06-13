"""Dual-track verdict synthesis: separate Investment and BD/M&A conclusions.

The engine produces a rich valuation artifact (``ValuationOutput``) and a rich
BD/M&A artifact (``MAProbabilityRow`` / ``BDMAOutput``). Historically these were
either reported as parallel data dumps or collapsed into a single blended
"attractiveness" score. Neither serves a professional reader: a name can be a
poor *stock* (already richly priced) yet an excellent *BD target* (it fills a
strategic gap for a specific buyer).

``build_dual_track`` composes the existing artifacts into two **independent**
verdicts plus one interpretive cross-read. It never averages the two axes into a
single number — the cross-read only *describes* their relationship (the 2x2
quadrant) and emits a one-sentence headline such as:

    "Limited standalone investment upside, but high BD strategic relevance —
     Vertex is the natural acquirer."

Design notes
------------
- Pure function, no I/O. Inputs are duck-typed (``Any | None``) so this module
  imports neither ``bve.valuation`` nor ``bve.intelligence`` — zero circular
  import risk, mirroring ``reporting.decision_report``.
- Degrades gracefully: when either side's inputs are absent the corresponding
  verdict is marked ``assessed=False`` and the quadrant becomes ``incomplete``.
- Thresholds live in a small ``DualTrackThresholds`` config object (not yet
  ``industry_assumptions.yaml``); callers can override per invocation.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Literal label vocabularies
# ---------------------------------------------------------------------------

InvestmentStance = Literal["long", "neutral", "avoid", "not_assessed"]
ValuationLabel = Literal["undervalued", "fair", "overvalued", "not_assessed"]
MarketRead = Literal[
    "market_expectation_too_low",
    "market_expectation_too_high",
    "market_roughly_fair",
    "not_assessed",
]
InvestmentEvidence = Literal["full", "coarse", "not_assessed"]
StrategicRelevance = Literal["high", "moderate", "low", "not_assessed"]
BDRoute = Literal["acquire", "license", "option", "watchlist", "no_action", "not_assessed"]
BDTiming = Literal["act_now", "30_days", "90_days", "watch", "not_assessed"]
ConfidenceLabel = Literal["high", "medium", "low"]
Quadrant = Literal[
    "dual_opportunity",
    "bd_only",
    "investment_only",
    "low_conviction",
    "incomplete",
]


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

class DualTrackThresholds(BaseModel):
    """Cut points for mapping continuous signals onto verdict labels.

    Kept as a config object (rather than YAML) so the synthesis layer is
    self-contained and unit-testable; promotion to ``industry_assumptions.yaml``
    can follow once the cut points are calibrated.
    """
    model_config = ConfigDict(frozen=True)

    # Investment axis — bounds on NAV/share upside (percent).
    undervalued_upside_pct: float = Field(default=25.0)
    overvalued_upside_pct: float = Field(default=-15.0)

    # BD axis — bounds on the strategic-relevance score (0-1).
    bd_high: float = Field(default=0.60)
    bd_moderate: float = Field(default=0.40)

    # Confidence label bands (0-1).
    confidence_high: float = Field(default=0.66)
    confidence_medium: float = Field(default=0.40)


# ---------------------------------------------------------------------------
# Verdict models
# ---------------------------------------------------------------------------

class InvestmentVerdict(BaseModel):
    """Standalone equity view: is the stock undervalued?"""
    model_config = ConfigDict(frozen=True)

    assessed: bool
    stance: InvestmentStance
    valuation_label: ValuationLabel
    market_expectation_read: MarketRead
    # How the stance was derived:
    #   full        — a price-anchored ValuationOutput (NAV upside + mispricing read)
    #   coarse      — only rNPV-vs-EV was available (directional; no mispricing nuance)
    #   not_assessed — neither was available
    evidence: InvestmentEvidence = "not_assessed"

    rnpv_millions: Optional[float] = None
    comparison_ev_millions: Optional[float] = None
    comparison_ev_basis: Optional[Literal["asset_implied", "company_ev"]] = None
    rnpv_vs_ev_pct: Optional[float] = None

    nav_per_share: Optional[float] = None
    current_price: Optional[float] = None
    implied_upside_pct: Optional[float] = None

    confidence: float = 0.0
    confidence_label: ConfidenceLabel = "low"
    rationale: list[str] = Field(default_factory=list)


class BDVerdict(BaseModel):
    """Strategic view: is the asset an attractive BD / M&A target?"""
    model_config = ConfigDict(frozen=True)

    assessed: bool
    strategic_relevance: StrategicRelevance
    recommended_route: BDRoute
    timing: BDTiming

    best_acquirer: Optional[str] = None
    why_this_buyer: Optional[str] = None
    buyer_can_execute: Optional[str] = None
    recommended_action: Optional[str] = None
    p_strategic_transaction_12m: Optional[float] = None
    estimated_deal_value_low_millions: Optional[float] = None
    estimated_deal_value_high_millions: Optional[float] = None

    confidence: float = 0.0
    confidence_label: ConfidenceLabel = "low"
    rationale: list[str] = Field(default_factory=list)
    main_risks: list[str] = Field(default_factory=list)


class DualTrackAssessment(BaseModel):
    """Two independent verdicts plus the interpretive cross-read.

    There is intentionally no single blended score: ``quadrant`` and
    ``headline`` *describe* the relationship between the two axes; they do not
    collapse them.
    """
    model_config = ConfigDict(frozen=True)

    investment: InvestmentVerdict
    bd: BDVerdict
    quadrant: Quadrant
    headline: str
    divergence: bool
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _g(obj: Any, name: str, default: Any = None) -> Any:
    """getattr that tolerates ``None`` objects."""
    if obj is None:
        return default
    return getattr(obj, name, default)


def _enum_value(x: Any) -> Any:
    """Return ``x.value`` for enums, else ``x`` unchanged."""
    return getattr(x, "value", x)


def _confidence_label(value: float, t: DualTrackThresholds) -> ConfidenceLabel:
    if value >= t.confidence_high:
        return "high"
    if value >= t.confidence_medium:
        return "medium"
    return "low"


_ROUTE_MAP: dict[str, BDRoute] = {
    "full_acquisition": "acquire",
    "asset_acquisition": "acquire",
    "acquisition": "acquire",
    "license_partnership": "license",
    "license": "license",
    "global_license": "license",
    "regional_license": "license",
    "collaboration": "license",
    "co_development": "license",
    "option_to_acquire": "option",
    "option": "option",
    "option_to_license_or_acquire": "option",
    "watchlist": "watchlist",
    "monitor": "watchlist",
    "not_applicable": "no_action",
    "no_action": "no_action",
    "none": "no_action",
}


# ---------------------------------------------------------------------------
# Investment verdict
# ---------------------------------------------------------------------------

def _build_investment_verdict(
    vo: Any,
    t: DualTrackThresholds,
) -> InvestmentVerdict:
    if vo is None:
        return InvestmentVerdict(
            assessed=False,
            stance="not_assessed",
            valuation_label="not_assessed",
            market_expectation_read="not_assessed",
        )

    upside = _g(vo, "implied_upside_pct")
    market_expectation = _g(vo, "market_expectation")
    variant_perception = _g(vo, "variant_perception")

    # Investment is only assessable with a market price anchor.
    has_price = upside is not None or market_expectation is not None
    if not has_price:
        return InvestmentVerdict(
            assessed=False,
            stance="not_assessed",
            valuation_label="not_assessed",
            market_expectation_read="not_assessed",
            rnpv_millions=_g(_g(vo, "rnpv"), "rnpv_millions"),
            nav_per_share=_g(vo, "nav_per_share"),
        )

    # --- valuation label + stance from NAV/share upside ---
    if upside is not None:
        if upside >= t.undervalued_upside_pct:
            valuation_label: ValuationLabel = "undervalued"
            stance: InvestmentStance = "long"
        elif upside <= t.overvalued_upside_pct:
            valuation_label = "overvalued"
            stance = "avoid"
        else:
            valuation_label = "fair"
            stance = "neutral"
    else:
        # Fall back to the mispricing direction when upside is unavailable.
        direction = _g(market_expectation, "mispricing_direction", "aligned")
        if direction == "underpriced":
            valuation_label, stance = "undervalued", "long"
        elif direction == "overpriced":
            valuation_label, stance = "overvalued", "avoid"
        else:
            valuation_label, stance = "fair", "neutral"

    # --- market expectation read ---
    direction = _g(market_expectation, "mispricing_direction", "aligned")
    if direction == "underpriced":
        market_read: MarketRead = "market_expectation_too_low"
    elif direction == "overpriced":
        market_read = "market_expectation_too_high"
    else:
        market_read = "market_roughly_fair"

    # --- rNPV vs EV (prefer apples-to-apples asset-implied EV) ---
    rnpv = _g(_g(vo, "rnpv"), "rnpv_millions")
    asset_implied_ev = _g(_g(variant_perception, "base"), "asset_implied_ev_millions")
    company_ev = _g(variant_perception, "company_ev_millions")
    if company_ev is None:
        company_ev = _g(market_expectation, "current_ev_millions")

    comparison_ev: Optional[float] = None
    comparison_basis: Optional[Literal["asset_implied", "company_ev"]] = None
    if asset_implied_ev is not None:
        comparison_ev, comparison_basis = asset_implied_ev, "asset_implied"
    elif company_ev is not None:
        comparison_ev, comparison_basis = company_ev, "company_ev"

    rnpv_vs_ev_pct: Optional[float] = None
    if rnpv is not None and comparison_ev not in (None, 0):
        rnpv_vs_ev_pct = round((rnpv - comparison_ev) / comparison_ev * 100, 1)

    # --- confidence ---
    me_conf = _g(market_expectation, "confidence")
    confidence = float(me_conf) if me_conf is not None else (0.6 if upside is not None else 0.4)

    # --- rationale ---
    rationale: list[str] = []
    if upside is not None:
        rationale.append(f"NAV/share implies {upside:+.0f}% vs current price → {valuation_label}.")
    if rnpv_vs_ev_pct is not None:
        basis = "asset-implied EV" if comparison_basis == "asset_implied" else "company EV"
        rationale.append(f"Asset rNPV is {rnpv_vs_ev_pct:+.0f}% vs {basis}.")
    if market_read != "market_roughly_fair":
        mag = _g(market_expectation, "mispricing_magnitude")
        mag_txt = f" ({mag})" if mag and mag != "none" else ""
        rationale.append(
            "Market-implied expectations look "
            + ("too low" if market_read == "market_expectation_too_low" else "too high")
            + mag_txt
            + "."
        )
    vp_memo = _g(variant_perception, "memo_interpretation")
    if vp_memo:
        rationale.append(str(vp_memo))

    return InvestmentVerdict(
        assessed=True,
        stance=stance,
        valuation_label=valuation_label,
        market_expectation_read=market_read,
        evidence="full",
        rnpv_millions=rnpv,
        comparison_ev_millions=comparison_ev,
        comparison_ev_basis=comparison_basis,
        rnpv_vs_ev_pct=rnpv_vs_ev_pct,
        nav_per_share=_g(vo, "nav_per_share"),
        current_price=_g(_g(vo, "company"), "current_price"),
        implied_upside_pct=upside,
        confidence=confidence,
        confidence_label=_confidence_label(confidence, t),
        rationale=rationale,
    )


def _build_investment_verdict_coarse(
    rnpv: float,
    ev: float,
    t: DualTrackThresholds,
) -> InvestmentVerdict:
    """Directional investment read from rNPV vs enterprise value alone.

    Used when no price-anchored ValuationOutput is on file. The rNPV-vs-EV gap is
    a model-value-vs-market gap on the same scale as NAV upside, so the same cut
    points apply — but there is no mispricing direction or NAV nuance, so this is
    labelled ``evidence="coarse"`` and carries a lower confidence.
    """
    gap_pct = round((rnpv - ev) / ev * 100, 1)
    if gap_pct >= t.undervalued_upside_pct:
        valuation_label, stance = "undervalued", "long"
    elif gap_pct <= t.overvalued_upside_pct:
        valuation_label, stance = "overvalued", "avoid"
    else:
        valuation_label, stance = "fair", "neutral"

    return InvestmentVerdict(
        assessed=True,
        stance=stance,
        valuation_label=valuation_label,
        market_expectation_read="not_assessed",
        evidence="coarse",
        rnpv_millions=rnpv,
        comparison_ev_millions=ev,
        comparison_ev_basis="company_ev",
        rnpv_vs_ev_pct=gap_pct,
        confidence=0.35,
        confidence_label=_confidence_label(0.35, t),
        rationale=[
            f"Coarse read: rNPV is {gap_pct:+.0f}% vs enterprise value "
            "(no full price-anchored valuation on file)."
        ],
    )


# ---------------------------------------------------------------------------
# BD verdict
# ---------------------------------------------------------------------------

def _relevance_from_score(score: Optional[float], t: DualTrackThresholds) -> StrategicRelevance:
    if score is None:
        return "not_assessed"
    if score >= t.bd_high:
        return "high"
    if score >= t.bd_moderate:
        return "moderate"
    return "low"


def _route_from_structure(structure: Any) -> Optional[BDRoute]:
    if structure is None:
        return None
    key = str(_enum_value(structure)).lower()
    return _ROUTE_MAP.get(key)


def _timing_from_signals(ma_row: Any, bdma: Any) -> BDTiming:
    days = _g(ma_row, "days_to_catalyst")
    if days is not None:
        if days <= 14:
            return "act_now"
        if days <= 45:
            return "30_days"
        if days <= 120:
            return "90_days"
        return "watch"
    urgency = _g(ma_row, "gap_urgency")
    if urgency:
        u = str(urgency).lower()
        if u in ("high", "urgent"):
            return "act_now"
        if u in ("moderate", "medium"):
            return "90_days"
        return "watch"
    timing_score = _g(_g(_g(bdma, "component_scores"), "transaction_timing"), "score") if bdma else None
    # component_scores is a dict; fetch via dict access when present.
    cs = _g(bdma, "component_scores")
    if isinstance(cs, dict) and "transaction_timing" in cs:
        timing_score = _g(cs["transaction_timing"], "score")
    if timing_score is not None:
        if timing_score >= 0.6:
            return "act_now"
        if timing_score >= 0.45:
            return "90_days"
        return "watch"
    return "not_assessed"


def _build_bd_verdict(
    ma_row: Any,
    bdma: Any,
    t: DualTrackThresholds,
) -> BDVerdict:
    if ma_row is None and bdma is None:
        return BDVerdict(
            assessed=False,
            strategic_relevance="not_assessed",
            recommended_route="not_assessed",
            timing="not_assessed",
        )

    # --- strategic relevance (prefer the richer BDMAOutput composite) ---
    if bdma is not None:
        relevance_score = _g(bdma, "bd_ma_score")
    else:
        relevance_score = _g(ma_row, "strategic_fit_score")
        if relevance_score is None:
            relevance_score = _g(ma_row, "mna_probability_score")
    relevance = _relevance_from_score(relevance_score, t)

    # --- route (prefer BDMAOutput.recommended_structure) ---
    route: Optional[BDRoute] = None
    if bdma is not None:
        route = _route_from_structure(_g(bdma, "recommended_structure"))
    if route is None and ma_row is not None:
        route = _route_from_structure(_g(ma_row, "recommended_deal_structure"))
    if route is None and ma_row is not None:
        route = _route_from_structure(_g(ma_row, "watchlist_type"))
    if route is None:
        # Default by relevance: still worth tracking if it has any strategic pull.
        route = "watchlist" if relevance in ("high", "moderate") else "no_action"

    # --- timing ---
    timing = _timing_from_signals(ma_row, bdma)

    # --- acquirer + narrative ---
    best_acquirer = _g(ma_row, "best_acquirer_name") or _g(bdma, "best_acquirer_id")

    why_this_buyer: Optional[str] = None
    gap = _g(ma_row, "matched_therapeutic_gap")
    priorities = _g(ma_row, "matched_priorities") or []
    if gap:
        why_this_buyer = f"Fills {gap}"
        if priorities:
            why_this_buyer += f" (priorities: {', '.join(map(str, priorities[:3]))})"
    elif bdma is not None:
        rats = _g(bdma, "primary_rationale") or []
        fit_lines = [r for r in rats if "strategic fit" in str(r).lower()]
        if fit_lines:
            why_this_buyer = str(fit_lines[0])

    # --- buyer feasibility ---
    buyer_can_execute: Optional[str] = None
    realism = _g(ma_row, "transaction_realism_label")
    if realism:
        buyer_can_execute = str(realism).lower()
    elif bdma is not None:
        cs = _g(bdma, "component_scores")
        feas = _g(cs["deal_feasibility"], "score") if isinstance(cs, dict) and "deal_feasibility" in cs else None
        if feas is not None:
            buyer_can_execute = (
                "feasible" if feas >= 0.6 else ("conditional" if feas >= 0.4 else "constrained")
            )

    recommended_action = _enum_value(_g(bdma, "recommended_action"))
    p_takeout = _g(ma_row, "p_takeout_calibrated")

    # --- confidence ---
    if bdma is not None:
        confidence = 0.6
    elif p_takeout is not None:
        confidence = 0.55
    else:
        confidence = 0.45

    # --- rationale + risks ---
    rationale: list[str] = []
    if relevance != "not_assessed":
        score_txt = f" (score {relevance_score:.2f})" if relevance_score is not None else ""
        rationale.append(f"Strategic relevance: {relevance}{score_txt}.")
    if best_acquirer:
        rationale.append(f"Best-fit acquirer: {best_acquirer}.")
    drivers = _g(ma_row, "score_drivers") or []
    rationale.extend(str(d) for d in drivers[:2])
    if not drivers and bdma is not None:
        rationale.extend(str(r) for r in (_g(bdma, "primary_rationale") or [])[:2])

    main_risks = [str(r) for r in (_g(bdma, "main_risks") or [])]

    return BDVerdict(
        assessed=True,
        strategic_relevance=relevance,
        recommended_route=route,
        timing=timing,
        best_acquirer=best_acquirer,
        why_this_buyer=why_this_buyer,
        buyer_can_execute=buyer_can_execute,
        recommended_action=str(recommended_action) if recommended_action is not None else None,
        p_strategic_transaction_12m=p_takeout,
        estimated_deal_value_low_millions=_g(ma_row, "estimated_deal_value_low_millions"),
        estimated_deal_value_high_millions=_g(ma_row, "estimated_deal_value_high_millions"),
        confidence=confidence,
        confidence_label=_confidence_label(confidence, t),
        rationale=rationale,
        main_risks=main_risks,
    )


# ---------------------------------------------------------------------------
# Cross-read
# ---------------------------------------------------------------------------

def _cross_read(inv: InvestmentVerdict, bd: BDVerdict) -> tuple[Quadrant, str, bool]:
    if not inv.assessed or not bd.assessed:
        missing = []
        if not inv.assessed:
            missing.append("investment view (no market price anchor)")
        if not bd.assessed:
            missing.append("BD view (no M&A assessment available)")
        return ("incomplete", "Incomplete cross-read — missing " + " and ".join(missing) + ".", False)

    investment_positive = inv.stance == "long"
    bd_positive = bd.strategic_relevance == "high"

    upside_txt = f"~{inv.implied_upside_pct:+.0f}% to NAV" if inv.implied_upside_pct is not None else inv.valuation_label
    acquirer_txt = f" — {bd.best_acquirer} is the natural acquirer." if bd.best_acquirer else "."

    if investment_positive and bd_positive:
        return (
            "dual_opportunity",
            f"Undervalued ({upside_txt}) and a credible acquisition target{acquirer_txt}",
            False,
        )
    if not investment_positive and bd_positive:
        return (
            "bd_only",
            f"Limited standalone investment upside, but high BD strategic relevance{acquirer_txt}",
            True,
        )
    if investment_positive and not bd_positive:
        return (
            "investment_only",
            f"Undervalued ({upside_txt}) on fundamentals; not an obvious acquisition target.",
            True,
        )
    return (
        "low_conviction",
        "Limited appeal on both the investment and BD lenses.",
        False,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_dual_track(
    valuation_output: Any | None = None,
    *,
    ma_row: Any | None = None,
    bdma_output: Any | None = None,
    coarse_rnpv_millions: float | None = None,
    coarse_ev_millions: float | None = None,
    thresholds: DualTrackThresholds | None = None,
) -> DualTrackAssessment:
    """Compose existing artifacts into two independent verdicts + a cross-read.

    Parameters
    ----------
    valuation_output:
        A ``bve.valuation.outputs.ValuationOutput`` (or duck-typed equivalent).
        Drives the full investment verdict. ``None`` → investment not assessed
        unless a coarse fallback is supplied.
    ma_row:
        A ``bve.intelligence.ma_probability.MAProbabilityRow`` (or equivalent).
    bdma_output:
        A ``bve.intelligence.ma_bd_decomposition.BDMAOutput`` (or equivalent).
        Preferred over ``ma_row`` for route/action/feasibility when both present.
        With neither ``ma_row`` nor ``bdma_output`` → BD not assessed.
    coarse_rnpv_millions, coarse_ev_millions:
        Hybrid fallback for the investment lens: when no full price-anchored
        valuation is available, a coarse rNPV-vs-EV stance is derived from these
        (e.g. an ``MAProbabilityRow``'s ``model_rnpv_millions`` /
        ``enterprise_value_millions``). Labelled ``evidence="coarse"``.
    thresholds:
        Optional ``DualTrackThresholds`` override.
    """
    t = thresholds or DualTrackThresholds()

    investment = _build_investment_verdict(valuation_output, t)
    if (
        not investment.assessed
        and coarse_rnpv_millions is not None
        and coarse_ev_millions not in (None, 0)
    ):
        investment = _build_investment_verdict_coarse(
            coarse_rnpv_millions, coarse_ev_millions, t
        )
    bd = _build_bd_verdict(ma_row, bdma_output, t)
    quadrant, headline, divergence = _cross_read(investment, bd)

    return DualTrackAssessment(
        investment=investment,
        bd=bd,
        quadrant=quadrant,
        headline=headline,
        divergence=divergence,
    )


def build_bd_verdict(
    *,
    ma_row: Any | None = None,
    bdma_output: Any | None = None,
    thresholds: DualTrackThresholds | None = None,
) -> BDVerdict:
    """Public wrapper to build only the BD verdict (e.g. for screen surfaces)."""
    return _build_bd_verdict(ma_row, bdma_output, thresholds or DualTrackThresholds())


def compose_assessment(
    investment: InvestmentVerdict,
    bd: BDVerdict,
) -> DualTrackAssessment:
    """Assemble a pre-built investment + BD verdict into the cross-read.

    Lets callers supply an investment verdict loaded from a saved valuation
    (the ``dual_track.investment`` block in ``valuation.json``) alongside a BD
    verdict computed from a screen row, without re-deriving either.
    """
    quadrant, headline, divergence = _cross_read(investment, bd)
    return DualTrackAssessment(
        investment=investment,
        bd=bd,
        quadrant=quadrant,
        headline=headline,
        divergence=divergence,
    )


def dual_track_columns(
    valuation_output: Any | None = None,
    *,
    ma_row: Any | None = None,
    bdma_output: Any | None = None,
    coarse_rnpv_millions: float | None = None,
    coarse_ev_millions: float | None = None,
    thresholds: DualTrackThresholds | None = None,
) -> dict[str, str]:
    """Flat columns for ranking/screen tables — never the blended composite score.

    Returns ``investment_stance``, ``investment_evidence`` (full/coarse/
    not_assessed), and ``bd_route``. A thin, side-effect-free adapter over
    :func:`build_dual_track` so multi-name surfaces can show the two verdicts
    side by side **without** collapsing them into (or replacing) the existing
    composite score.
    """
    a = build_dual_track(
        valuation_output,
        ma_row=ma_row,
        bdma_output=bdma_output,
        coarse_rnpv_millions=coarse_rnpv_millions,
        coarse_ev_millions=coarse_ev_millions,
        thresholds=thresholds,
    )
    return {
        "investment_stance": a.investment.stance,
        "investment_evidence": a.investment.evidence,
        "bd_route": a.bd.recommended_route,
    }
