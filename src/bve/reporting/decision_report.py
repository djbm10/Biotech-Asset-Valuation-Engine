"""Decision-grade Markdown report builder for a single ticker.

Produces a structured ``bve-report`` output that a BD professional, analyst,
or IC reviewer can read directly from the command line or share as a document.

Report sections
---------------
1. Header           — ticker, date, validation disclaimer
2. POS Summary      — model POS, market-implied POS, gap
3. rNPV Summary     — base/bull/bear, MC distribution, peak sales
4. M&A / BD Action  — p_acquisition, score, best acquirer, drivers/suppressors
5. Staleness Alerts — any stale inputs surfaced by the staleness checker
6. Provenance       — key assumption sources and confidence
7. Prediction Log   — recent logged predictions and resolved outcomes
8. Validation       — replay alpha, M&A backtest, POS calibration status

Design principles
-----------------
- All sections degrade gracefully: missing data → "Not available".
- No fabrication: values that cannot be determined are never estimated.
- The validation disclaimer appears in every report and cannot be removed.
- Pure functions — callers supply data objects; this module does no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from bve.reporting.provenance import ProvenanceItem, render_provenance_table
from bve.reporting.validation_summary import ValidationSummaryData, render_validation_summary
from bve.refresh.input_integrity import InputIntegrityScore, render_input_integrity


_NA = "Not available"
_DISCLAIMER = (
    "> ⚠ **Research-grade output only.** Not investment advice. "
    "All probabilities are model estimates subject to material uncertainty. "
    "Validate against primary sources before making decisions."
)


# ---------------------------------------------------------------------------
# Input container
# ---------------------------------------------------------------------------

@dataclass
class DecisionReportInput:
    """All data needed to build one decision report.

    All fields except ``ticker`` and ``as_of_date`` are optional — the report
    renders "Not available" for any section whose data is absent.

    Parameters
    ----------
    ticker:
        Stock ticker (used in the report header).
    as_of_date:
        Date of the report; defaults to today.
    valuation_output:
        ``bve.valuation.outputs.ValuationOutput`` (or None if not run).
    ma_row:
        ``bve.intelligence.ma_probability.MAProbabilityRow`` (or None).
    prediction_log_entries:
        List of dicts from ``PredictionLog.unresolved()`` or similar.
        Each dict should have: id, log_type, asset_id, ticker, score,
        confidence, notes, logged_at, outcome, outcome_notes.
    validation_summary:
        Pre-assembled ``ValidationSummaryData`` (or None).
    provenance_items:
        Pre-built provenance items (or empty — auto-populated from
        valuation_output/ma_row when None).
    staleness_warnings:
        Pre-built staleness warning strings (or empty).
    notes:
        Free-text notes to append at the end of the report.
    """

    ticker: str
    as_of_date: date = field(default_factory=date.today)
    valuation_output: Optional[Any] = None
    ma_row: Optional[Any] = None
    prediction_log_entries: list[dict] = field(default_factory=list)
    validation_summary: Optional[ValidationSummaryData] = None
    provenance_items: list[ProvenanceItem] = field(default_factory=list)
    staleness_warnings: list[str] = field(default_factory=list)
    input_integrity: Optional[InputIntegrityScore] = None
    management_quality: Optional[Any] = None   # ManagementQualityScore
    management_diligence_questions: list[Any] = field(default_factory=list)  # ManagementDiligenceQuestion
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Section builders (all return str, never raise on missing data)
# ---------------------------------------------------------------------------

def _header(report_input: DecisionReportInput) -> str:
    ticker = report_input.ticker.upper()
    as_of = report_input.as_of_date.isoformat()
    lines = [
        f"# BVE Decision Report — {ticker}",
        "",
        f"**As of:** {as_of}",
        "",
        _DISCLAIMER,
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def _coerce_valuation_for_dual_track(vo: Any) -> Any:
    """Return an object ``build_dual_track`` can read.

    Live ``ValuationOutput`` objects are passed through unchanged (they expose
    ``.rnpv``, ``.market_expectation``, etc.). When the report is built from a
    saved ``valuation.json`` the loader supplies a shim whose only structured
    view is ``summary_dict`` — we rebuild the minimal attribute surface from it
    so the investment verdict still renders.
    """
    if vo is None:
        return None
    rnpv_obj = getattr(vo, "rnpv", None)
    if rnpv_obj is not None and getattr(rnpv_obj, "rnpv_millions", None) is not None:
        return vo  # live object

    from types import SimpleNamespace

    try:
        sd = vo.summary_dict
        if not isinstance(sd, dict):
            return vo
    except Exception:
        return vo

    direction = sd.get("market_mispricing_direction")
    has_price = sd.get("current_price") is not None
    market_expectation = (
        SimpleNamespace(
            mispricing_direction=direction,
            mispricing_magnitude=sd.get("market_mispricing_magnitude"),
            confidence=None,
            current_ev_millions=None,
            implied_peak_sales_millions=sd.get("market_implied_peak_sales_millions"),
        )
        if (direction is not None or has_price)
        else None
    )
    variant_perception = (
        SimpleNamespace(
            company_ev_millions=None,
            base=SimpleNamespace(asset_implied_ev_millions=None),
            variant_perception_category=sd.get("vp_category"),
            memo_interpretation=sd.get("vp_memo"),
        )
        if sd.get("vp_category")
        else None
    )
    return SimpleNamespace(
        implied_upside_pct=sd.get("implied_upside_pct"),
        rnpv=SimpleNamespace(rnpv_millions=sd.get("rnpv_millions")),
        nav_per_share=sd.get("nav_per_share"),
        company=SimpleNamespace(
            current_price=sd.get("current_price"),
            shares_outstanding_millions=sd.get("shares_outstanding_millions"),
            net_cash_millions=sd.get("net_cash_millions"),
        ),
        market_expectation=market_expectation,
        variant_perception=variant_perception,
        monte_carlo=SimpleNamespace(probability_positive=sd.get("mc_prob_positive")),
    )


def _dual_track_section(report_input: DecisionReportInput) -> str:
    """Section 1.5: Dual-track verdict — separate Investment and BD conclusions.

    Composes the existing valuation and M&A artifacts into two independent
    verdicts plus an interpretive cross-read. Never blends the two into one
    score. Degrades to "Not assessed" when either side's inputs are absent.
    """
    from bve.analysis.dual_track import build_dual_track

    vo = _coerce_valuation_for_dual_track(report_input.valuation_output)
    try:
        dt = build_dual_track(vo, ma_row=report_input.ma_row)
    except Exception:
        return ""

    iv, bd = dt.investment, dt.bd
    lines = ["## Dual-Track Verdict", ""]
    lines += [f"> **{dt.headline}**", ""]

    def _inv_cell() -> str:
        if not iv.assessed:
            return "⚠ Not assessed (no price anchor)"
        return f"{iv.stance.upper()} ({iv.valuation_label})"

    def _inv_reads() -> str:
        if not iv.assessed:
            return "No market price anchor"
        bits = []
        if iv.implied_upside_pct is not None:
            bits.append(f"NAV {iv.implied_upside_pct:+.0f}%")
        if iv.rnpv_vs_ev_pct is not None:
            bits.append(f"rNPV vs EV {iv.rnpv_vs_ev_pct:+.0f}%")
        read_map = {
            "market_expectation_too_low": "mkt expectation too low",
            "market_expectation_too_high": "mkt expectation too high",
            "market_roughly_fair": "mkt roughly fair",
        }
        if iv.market_expectation_read in read_map:
            bits.append(read_map[iv.market_expectation_read])
        return "; ".join(bits) or _NA

    def _bd_cell() -> str:
        if not bd.assessed:
            return "⚠ Not run (no M&A scan)"
        return f"{bd.strategic_relevance} relevance → {bd.recommended_route}"

    def _bd_reads() -> str:
        if not bd.assessed:
            return "Run `bve-ma-probability` to populate"
        bits = []
        if bd.best_acquirer:
            bits.append(f"buyer: {bd.best_acquirer}")
        if bd.timing != "not_assessed":
            bits.append(f"timing: {bd.timing}")
        if bd.p_strategic_transaction_12m is not None:
            bits.append(f"p(deal,12m): {bd.p_strategic_transaction_12m:.0%}")
        return "; ".join(bits) or _NA

    lines += [
        "| Lens | Verdict | Key reads |",
        "|---|---|---|",
        f"| **Investment** | {_inv_cell()} | {_inv_reads()} |",
        f"| **BD / M&A** | {_bd_cell()} | {_bd_reads()} |",
        "",
        f"**Quadrant:** `{dt.quadrant}`"
        + ("  ⚠ _the two lenses diverge_" if dt.divergence else ""),
        "",
    ]

    # Make a one-sided assessment unmistakable: a missing lens is "not run",
    # never a negative verdict.
    if iv.assessed and not bd.assessed:
        lines += [
            "> ⚠ _Investment lens only. The BD/M&A verdict was **not run** in this "
            "report — this is not a negative BD conclusion. Run `bve-ma-probability` "
            "for the BD lens._",
            "",
        ]
    elif bd.assessed and not iv.assessed:
        lines += [
            "> ⚠ _BD lens only. The investment verdict was **not assessed** (no market "
            "price anchor) — this is not a negative investment conclusion._",
            "",
        ]

    return "\n".join(lines)


def _pos_section(report_input: DecisionReportInput) -> str:
    """Section 2: POS comparison."""
    vo = report_input.valuation_output
    lines = ["## Model vs. Market POS", ""]

    if vo is None:
        lines += [
            "| Metric | Value |",
            "|---|---|",
            f"| Model POS | {_NA} |",
            f"| Market-implied POS | {_NA} |",
            f"| POS gap | {_NA} |",
            f"| Mispricing direction | {_NA} |",
            "",
        ]
        return "\n".join(lines)

    try:
        sd = vo.summary_dict
        if not isinstance(sd, dict):
            sd = {}
    except Exception:
        sd = {}
    if not isinstance(sd, dict):
        try:
            sd = dict(sd)
        except Exception:
            sd = {}

    model_pos_raw = sd.get("model_pos")
    model_pos_str = (
        f"{model_pos_raw:.1%}" if model_pos_raw is not None else _NA
    )

    implied_pos_raw = sd.get("market_implied_pos")
    implied_pos_str = f"{implied_pos_raw:.1%}" if implied_pos_raw is not None else _NA

    gap_str = sd.get("market_pos_gap_pct") or _NA
    direction = sd.get("market_mispricing_direction") or _NA

    pos_text = getattr(vo, "pos_comparison_text", None)

    lines += [
        "| Metric | Value |",
        "|---|---|",
        f"| Model POS | {model_pos_str} |",
        f"| Market-implied POS | {implied_pos_str} |",
        f"| POS gap (model − market) | {gap_str} |",
        f"| Mispricing direction | {direction} |",
        "",
    ]
    if pos_text:
        lines += [f"> {pos_text}", ""]

    return "\n".join(lines)


def _rnpv_section(report_input: DecisionReportInput) -> str:
    """Section 3: rNPV summary."""
    vo = report_input.valuation_output
    lines = ["## rNPV Summary", ""]

    def _fmt(v: Any, fmt: str = ".0f") -> str:
        if v is None:
            return _NA
        try:
            return format(float(v), fmt)
        except (TypeError, ValueError):
            return str(v)

    if vo is None:
        lines += [
            "| Scenario | rNPV ($M) | NAV/share ($) |",
            "|---|---|---|",
            f"| Bull | {_NA} | {_NA} |",
            f"| Base | {_NA} | {_NA} |",
            f"| Bear | {_NA} | {_NA} |",
            "",
        ]
        return "\n".join(lines)

    try:
        sd = vo.summary_dict
        if not isinstance(sd, dict):
            sd = {}
    except Exception:
        sd = {}

    bull_rnpv = _fmt(sd.get("bull_rnpv"))
    base_rnpv = _fmt(sd.get("base_rnpv"))
    bear_rnpv = _fmt(sd.get("bear_rnpv"))
    bull_nav = _fmt(sd.get("bull_nav_ps"), ".2f")
    base_nav = _fmt(sd.get("base_nav_ps"), ".2f")
    bear_nav = _fmt(sd.get("bear_nav_ps"), ".2f")

    peak_sales = _fmt(sd.get("peak_sales_millions"))
    years_to_launch = _fmt(sd.get("years_to_launch"), ".1f")
    prob_approval = sd.get("prob_approval_pct") or _NA

    mc_p25 = _fmt(sd.get("mc_p25"))
    mc_p75 = _fmt(sd.get("mc_p75"))
    mc_mean = _fmt(sd.get("mc_mean"))
    mc_prob_pos = sd.get("mc_prob_positive") or _NA

    current_price = _fmt(sd.get("current_price"), ".2f")
    nav_per_share = _fmt(sd.get("nav_per_share"), ".2f")
    implied_upside = sd.get("implied_upside_pct")
    implied_upside_str = f"{implied_upside:+.0f}%" if implied_upside is not None else _NA

    lines += [
        "### Scenario Analysis",
        "",
        "| Scenario | rNPV ($M) | NAV/share ($) |",
        "|---|---|---|",
        f"| Bull | {bull_rnpv} | {bull_nav} |",
        f"| Base | {base_rnpv} | {base_nav} |",
        f"| Bear | {bear_rnpv} | {bear_nav} |",
        "",
        "### Monte Carlo (10,000 simulations)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Mean ($M) | {mc_mean} |",
        f"| P25–P75 range ($M) | {mc_p25} – {mc_p75} |",
        f"| P(positive) | {mc_prob_pos} |",
        "",
        "### Key Drivers",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| P(approval) | {prob_approval} |",
        f"| Peak sales ($M) | {peak_sales} |",
        f"| Years to launch | {years_to_launch} |",
        f"| Current price ($) | {current_price} |",
        f"| Base NAV/share ($) | {nav_per_share} |",
        f"| Implied upside | {implied_upside_str} |",
        "",
    ]
    return "\n".join(lines)


def _ma_section(report_input: DecisionReportInput) -> str:
    """Section 4: M&A / BD Action Assessment."""
    row = report_input.ma_row
    lines = ["## M&A / BD Action Assessment", ""]

    def _fmt(v: Any, fmt: str = ".4f") -> str:
        if v is None:
            return _NA
        try:
            return format(float(v), fmt)
        except (TypeError, ValueError):
            return str(v)

    if row is None:
        lines += [
            "| Metric | Value |",
            "|---|---|",
            f"| M&A probability score | {_NA} |",
            f"| P(acquisition) | {_NA} |",
            f"| Best acquirer | {_NA} |",
            f"| Watchlist type | {_NA} |",
            "",
            "_Run `bve-ma-probability` to populate M&A scores._",
            "",
        ]
        return "\n".join(lines)

    score = _fmt(getattr(row, "mna_probability_score", None))
    p_acq = _fmt(getattr(row, "p_acquisition", None))
    p_cal = _fmt(getattr(row, "p_takeout_calibrated", None))
    acquirer = getattr(row, "best_acquirer_name", _NA) or _NA
    acquirer_fit = _fmt(getattr(row, "best_acquirer_fit_score", None))
    watchlist = getattr(row, "watchlist_type", None) or _NA
    rank = getattr(row, "rank", None)
    rank_str = str(rank) if rank else _NA

    # Component scores
    strat_fit = _fmt(getattr(row, "strategic_fit_score", None))
    val_disc = _fmt(getattr(row, "valuation_discount_score", None))
    de_risk = _fmt(getattr(row, "de_risking_stage_score", None))
    cap_vuln = _fmt(getattr(row, "capital_vulnerability_score", None))

    lines += [
        "| Metric | Value |",
        "|---|---|",
        f"| M&A probability score | {score} |",
        f"| P(acquisition) raw | {p_acq} |",
        f"| P(takeout) calibrated | {p_cal} |",
        f"| Best acquirer | {acquirer} |",
        f"| Acquirer fit score | {acquirer_fit} |",
        f"| Watchlist type | {watchlist} |",
        f"| Rank | {rank_str} |",
        "",
        "### Component Scores",
        "",
        "| Component | Score |",
        "|---|---|",
        f"| Strategic fit | {strat_fit} |",
        f"| Valuation discount | {val_disc} |",
        f"| De-risking stage | {de_risk} |",
        f"| Capital vulnerability | {cap_vuln} |",
        "",
    ]

    # Score drivers
    drivers = getattr(row, "score_drivers", []) or []
    suppressors = getattr(row, "score_suppressors", []) or []

    if drivers:
        lines += ["### Top Score Drivers", ""]
        for d in drivers:
            lines.append(f"- {d}")
        lines.append("")
    if suppressors:
        lines += ["### Top Score Suppressors", ""]
        for s in suppressors:
            lines.append(f"- {s}")
        lines.append("")

    return "\n".join(lines)


def _staleness_section(report_input: DecisionReportInput) -> str:
    """Section 5: Staleness warnings."""
    warnings = report_input.staleness_warnings
    lines = ["## Staleness Warnings", ""]
    if not warnings:
        lines += ["_No staleness warnings. All inputs are within freshness thresholds._", ""]
    else:
        for w in warnings:
            lines.append(f"- ⚠ {w}")
        lines.append("")
    return "\n".join(lines)


def _prediction_log_section(report_input: DecisionReportInput) -> str:
    """Section 7: Prediction log history."""
    entries = report_input.prediction_log_entries
    lines = ["## Prediction Log History", ""]

    if not entries:
        lines += ["_No prediction log entries available for this ticker._", ""]
        return "\n".join(lines)

    lines += [
        "| ID | Type | Score | Confidence | Logged At | Outcome | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        eid = str(e.get("id", "—"))
        log_type = e.get("log_type", "—")
        score = e.get("score")
        score_str = f"{score:.4f}" if score is not None else "—"
        conf = e.get("confidence")
        conf_str = f"{conf:.2f}" if conf is not None else "—"
        logged_at = e.get("logged_at", "—")
        # Truncate to date for readability
        if logged_at and "T" in str(logged_at):
            logged_at = str(logged_at).split("T")[0]
        outcome = e.get("outcome") or "pending"
        notes = e.get("notes") or "—"
        # Cap notes length for table readability
        if len(str(notes)) > 60:
            notes = str(notes)[:57] + "..."
        lines.append(
            f"| {eid} | {log_type} | {score_str} | {conf_str} | "
            f"{logged_at} | {outcome} | {notes} |"
        )
    lines.append("")

    # Summary counts
    n_pending = sum(1 for e in entries if not e.get("outcome"))
    n_correct = sum(1 for e in entries if e.get("outcome") == "correct")
    n_resolved = sum(1 for e in entries if e.get("outcome") and e.get("outcome") != "pending")
    accuracy_str = (
        f"{n_correct / n_resolved:.0%}" if n_resolved > 0 else _NA
    )
    lines += [
        f"**Total entries:** {len(entries)} | "
        f"**Pending:** {n_pending} | "
        f"**Resolved:** {n_resolved} | "
        f"**Accuracy (correct/resolved):** {accuracy_str}",
        "",
    ]
    return "\n".join(lines)


def _management_section(report_input: DecisionReportInput) -> str:
    """Management Quality section — risk band, composite, gate, drivers, diligence."""
    mq = report_input.management_quality
    if mq is None:
        return ""

    lines = ["## Management Quality", ""]

    risk_band = getattr(mq, "risk_band", None)
    band_str = risk_band.value.upper() if hasattr(risk_band, "value") else str(risk_band) if risk_band else _NA
    composite = getattr(mq, "composite", None)
    composite_str = f"{composite:.2f}" if composite is not None else _NA
    confidence = getattr(mq, "confidence", None)
    conf_str = confidence.value if hasattr(confidence, "value") else str(confidence) if confidence else _NA
    gate = getattr(mq, "gate", None)
    gate_str = gate.value if hasattr(gate, "value") else str(gate) if gate else _NA
    staleness = getattr(mq, "staleness_warning", False)
    summary = getattr(mq, "management_risk_summary", "") or ""

    lines += [
        "| Metric | Value |",
        "|---|---|",
        f"| Risk band | `{band_str}` |",
        f"| Composite score | {composite_str} |",
        f"| Confidence | {conf_str} |",
        f"| Gate | `{gate_str}` |",
    ]
    if staleness:
        lines.append("| ⚠ Staleness warning | Data > 180 days old — confidence degraded |")
    lines.append("")

    if summary:
        lines += [f"> {summary}", ""]

    positive = getattr(mq, "positive_drivers", []) or []
    negative = getattr(mq, "negative_drivers", []) or []

    if positive:
        lines += ["### Positive Indicators", ""]
        for p in positive:
            lines.append(f"- {p}")
        lines.append("")

    if negative:
        lines += ["### Value-Destruction Flags", ""]
        for n in negative:
            lines.append(f"- ⚠ {n}")
        lines.append("")

    # Diligence questions (CRITICAL/HIGH only, max 5)
    questions = report_input.management_diligence_questions or []
    if not questions:
        # Auto-generate from the score if questions weren't pre-supplied
        try:
            from bve.intelligence.ma_management_diligence import (
                generate_management_diligence_questions,
            )
            questions = generate_management_diligence_questions(mq)
        except Exception:
            questions = []

    priority_filter = {"CRITICAL", "HIGH"}
    high_priority = [q for q in questions if getattr(q, "priority", "") in priority_filter][:5]
    if high_priority:
        lines += ["### Key Diligence Questions", ""]
        for q in high_priority:
            owner = getattr(q, "owner", "")
            priority = getattr(q, "priority", "")
            question = getattr(q, "question", str(q))
            lines.append(f"- **[{priority} / {owner}]** {question}")
        lines.append("")

    return "\n".join(lines)


def _notes_section(report_input: DecisionReportInput) -> str:
    """Footer notes."""
    notes = report_input.notes
    if not notes:
        return ""
    lines = ["## Notes", ""]
    for note in notes:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main report renderer
# ---------------------------------------------------------------------------

def render_decision_report(report_input: DecisionReportInput) -> str:
    """Build and return a complete Markdown decision report.

    Assembles all sections in order:
    1. Header + disclaimer
    2. POS (model vs. market)
    3. rNPV summary
    4. M&A / BD action assessment
    5. Staleness warnings
    6. Assumption provenance
    7. Prediction log history
    8. Validation evidence
    9. Notes (if any)

    Missing data in any section renders as "Not available" — no section is
    omitted and no values are fabricated.

    Parameters
    ----------
    report_input:
        Fully (or partially) populated ``DecisionReportInput``.

    Returns
    -------
    str
        Complete Markdown report as a single string.
    """
    # Auto-populate provenance if not supplied and we have a valuation output
    provenance = report_input.provenance_items
    if not provenance and report_input.valuation_output is not None:
        from bve.reporting.provenance import (
            build_pos_provenance,
            build_valuation_provenance,
        )
        vo = report_input.valuation_output
        asset = getattr(vo, "asset", None)
        trials = getattr(vo, "trials", [])
        if asset is not None:
            provenance = build_pos_provenance(
                asset, trials, as_of_date=report_input.as_of_date
            )
        provenance += build_valuation_provenance(
            vo, as_of_date=report_input.as_of_date
        )

    parts: list[str] = [
        _header(report_input),
        _dual_track_section(report_input),
        _pos_section(report_input),
        _rnpv_section(report_input),
        _ma_section(report_input),
        _staleness_section(report_input),
    ]

    # Input integrity section (when available)
    if report_input.input_integrity is not None:
        parts.append(render_input_integrity(report_input.input_integrity))

    # Management quality section (when available)
    mgmt_section = _management_section(report_input)
    if mgmt_section:
        parts.append(mgmt_section)

    parts += [
        render_provenance_table(
            provenance,
            section_title="Assumption Provenance",
        ),
        _prediction_log_section(report_input),
    ]

    # Validation section — use supplied data or empty summary
    vs = report_input.validation_summary
    if vs is None:
        from bve.reporting.validation_summary import build_validation_summary
        vs = build_validation_summary()
    parts.append(render_validation_summary(vs))

    if report_input.notes:
        parts.append(_notes_section(report_input))

    return "\n".join(parts)
