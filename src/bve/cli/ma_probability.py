"""CLI entry point: bve-ma-probability."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ma_probability import (
    MAProbabilityConfig,
    MAProbabilityResult,
    MAProbabilityRow,
    MAProbabilityScanner,
)
from bve.pipeline.watchlist_runner import load_watchlist_config


def _default_calibration_model_path() -> str | None:
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "outputs" / "analysis" / "ma_calibration_fit_post_step2.json",
        repo_root / "outputs" / "analysis" / "ma_calibration_fit.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank watchlist assets by acquisition likelihood across all configured acquirers"
    )
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument(
        "--db",
        default=None,
        help="Override KnowledgeStore SQLite path (defaults to watchlist knowledge_db_path)",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Score as of YYYY-MM-DD (default: today)",
    )
    parser.add_argument("--top", type=int, default=15, help="Number of ranked rows to show")
    parser.add_argument(
        "--alert-threshold",
        type=float,
        default=0.70,
        help="Threshold used for above-alert highlighting and emitted alert checks",
    )
    parser.add_argument(
        "--profiles-file",
        default="examples/research/acquirer_profiles",
        help="Acquirer profile YAML file or directory path",
    )
    parser.add_argument(
        "--comps-file",
        default="research/mna/comparable_deals.yaml",
        help="Comparable deal YAML path",
    )
    parser.add_argument(
        "--vulnerability-file",
        default="research/mna/vulnerability_signals.yaml",
        help="Vulnerability signal YAML path",
    )
    parser.add_argument(
        "--readiness-filter",
        choices=["strict", "off"],
        default="strict",
        help="Apply the Phase 2 POC-or-later acquisition-readiness gate",
    )
    parser.add_argument(
        "--emit-alerts",
        action="store_true",
        help="Persist daily snapshots and emit idempotent threshold/top-entry alerts",
    )
    parser.add_argument(
        "--calibration-model",
        default=_default_calibration_model_path(),
        help="Optional MALogisticFitResult JSON used for calibrated takeout probabilities",
    )
    parser.add_argument(
        "--calibration-policy",
        choices=["display_only", "threshold_filter", "tie_breaker"],
        default="display_only",
        help="How calibrated probability should affect the live ranked output",
    )
    parser.add_argument(
        "--calibration-threshold",
        type=float,
        default=0.10,
        help="Threshold used by the threshold_filter calibration policy",
    )
    parser.add_argument(
        "--output-format",
        choices=["report", "json"],
        default="report",
        help="Output format",
    )
    parser.add_argument("--output", default=None, help="Write output to file instead of stdout")
    return parser


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid --as-of value: {raw!r}; expected YYYY-MM-DD") from exc


def _resolve_watchlist_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.exists():
        return path

    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "examples" / "configs" / "watchlists" / raw_path,
        repo_root / "examples" / "configs" / "watchlists" / Path(raw_path).name,
        repo_root / "examples" / "configs" / raw_path,
        repo_root / "examples" / "configs" / Path(raw_path).name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return path


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _fmt_ratio(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}x"


def _fmt_millions(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if value >= 1000:
        return f"${value / 1000.0:.1f}B"
    return f"${value:,.0f}M"


def _fmt_deal_range(row) -> str:
    low = getattr(row, "estimated_deal_value_low_millions", None)
    high = getattr(row, "estimated_deal_value_high_millions", None)
    if low is None or high is None:
        return "n/a"
    return f"{_fmt_millions(low)}-{_fmt_millions(high)}"


def _fmt_score(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _fmt_text(value: Optional[str], *, fallback: str = "n/a") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _fmt_flags(row) -> str:
    flags: list[str] = []
    if row.above_alert_threshold:
        flags.append("alert")
    flags.extend(row.hard_fail_reasons)
    return ",".join(flags) if flags else "none"


# ---------------------------------------------------------------------------
# Stage-based industry POS approximations (Biomedtracker averages)
# ---------------------------------------------------------------------------
_STAGE_POS_APPROX: dict[str, float] = {
    "preclinical": 0.05,
    "phase 1": 0.10,
    "phase_1": 0.10,
    "phase 2": 0.25,
    "phase_2": 0.25,
    "phase 3": 0.60,
    "phase_3": 0.60,
    "nda bla": 0.85,
    "nda_bla": 0.85,
    "approved": 1.00,
    "commercial": 1.00,
}

# Revenue-to-NPV multiple: NPV_if_approved ≈ peak_sales × this factor.
# Assumes 12yr patent life, 75% gross margin, 15% discount, 8yr ramp.
_PEAK_SALES_TO_NPV_MULTIPLE = 4.5

# Acquisition process timeline by stage (min_months, max_months to close).
# Based on public deal timelines: exploratory (2-4m) + DD (2-4m) + legal (1-3m)
# + regulatory clearance (2-4m).
_STAGE_TIMELINE_MONTHS: dict[str, tuple[int, int]] = {
    "preclinical": (30, 48),
    "phase 1": (24, 36),
    "phase_1": (24, 36),
    "phase 2": (12, 24),
    "phase_2": (12, 24),
    "phase 3": (6, 18),
    "phase_3": (6, 18),
    "nda bla": (3, 12),
    "nda_bla": (3, 12),
    "approved": (3, 9),
    "commercial": (3, 9),
}


def _npv_if_approved(row: "MAProbabilityRow") -> Optional[float]:
    """Estimate NPV at 100% approval probability.

    Preference order:
    1. peak_sales_millions × DCF multiple (most transparent).
    2. model_rnpv_millions ÷ stage-industry POS (rNPV already has POS baked in).
    """
    ps = row.peak_sales_millions
    if ps is not None and ps > 0:
        return ps * _PEAK_SALES_TO_NPV_MULTIPLE

    rnpv = row.model_rnpv_millions
    stage_pos = _STAGE_POS_APPROX.get((row.stage or "").lower().strip(), 0.0)
    if rnpv is not None and rnpv > 0 and stage_pos > 0:
        return rnpv / stage_pos

    return None


def _derive_model_pos(row: "MAProbabilityRow", npv_if_approved: float) -> float:
    """Back-derive model POS from rNPV and NPV_if_approved."""
    rnpv = row.model_rnpv_millions
    if rnpv is not None and rnpv > 0 and npv_if_approved > 0:
        return min(1.0, rnpv / npv_if_approved)
    return _STAGE_POS_APPROX.get((row.stage or "").lower().strip(), 0.25)


def _derive_implied_pos(row: "MAProbabilityRow", npv_if_approved: float) -> Optional[float]:
    """Back-solve market-implied POS from current EV."""
    ev = row.enterprise_value_millions
    if ev is None or npv_if_approved <= 0:
        return None
    return min(1.0, max(0.0, ev / npv_if_approved))


def _timeline_for_row(row: "MAProbabilityRow") -> tuple[int, int]:
    """Estimate (min_months, max_months) to acquisition close."""
    stage_key = (row.stage or "").lower().strip()
    base_min, base_max = _STAGE_TIMELINE_MONTHS.get(stage_key, (18, 30))

    adj = 0
    if getattr(row, "watchlist_type", None) == "near_term_transaction":
        adj -= 5
    if getattr(row, "gap_urgency", None) == "high":
        adj -= 3
    if (getattr(row, "transaction_driver_count", None) or 0) >= 2:
        adj -= 3
    dtc = getattr(row, "days_to_catalyst", None)
    if dtc is not None and dtc < 90:
        adj -= 3
    if row.capital_vulnerability_score > 0.70:
        adj -= 4  # distressed → faster process

    min_m = max(3, base_min + adj)
    max_m = max(min_m + 3, base_max + adj)
    return min_m, max_m


def _format_variant_perception(result: "MAProbabilityResult") -> str:
    """Section 2: Market mispricing ranked by implied-POS gap.

    Back-solves the market's implicit P(approval) from the current enterprise
    value and the model's NPV-if-approved estimate, then surfaces the largest
    gaps as explicit investment edges.
    """
    entries: list[tuple[float, str]] = []  # (gap_pp, formatted_line)

    for row in result.rows:
        npv_approved = _npv_if_approved(row)
        if npv_approved is None or npv_approved <= 0:
            continue
        implied = _derive_implied_pos(row, npv_approved)
        if implied is None:
            continue
        model_pos = _derive_model_pos(row, npv_approved)
        gap_pp = (model_pos - implied) * 100.0

        ticker = row.ticker or row.asset_id
        ev_str = _fmt_millions(row.enterprise_value_millions)
        npv_str = _fmt_millions(npv_approved)
        ps_str = _fmt_millions(row.peak_sales_millions) if row.peak_sales_millions else f"rNPV/{_fmt_pct(_STAGE_POS_APPROX.get((row.stage or '').lower().strip(), 0.0))}"

        if gap_pp > 0:
            direction = "UNDERPRICED"
            edge_str = f"+{gap_pp:.0f}pp edge"
        elif gap_pp < -2:
            direction = "OVERPRICED"
            edge_str = f"{gap_pp:.0f}pp risk"
        else:
            direction = "FAIR"
            edge_str = "at model"

        line = (
            f"  {ticker:<8}  EV={ev_str:<9}  NPV(approved)={npv_str:<9}  "
            f"market_POS={_fmt_pct(implied):<7}  model_POS={_fmt_pct(model_pos):<7}  "
            f"gap={edge_str:<15}  [{direction}]"
        )
        if row.peak_sales_millions:
            line += f"  (peak_sales={ps_str})"
        entries.append((gap_pp, line))

    if not entries:
        return ""

    # Sort: largest positive gap (most underpriced) first; overpriced last
    entries.sort(key=lambda t: -t[0])

    lines = [
        "",
        "=" * 100,
        "VARIANT PERCEPTION — MARKET MISPRICING SCREEN",
        "  Back-solving implied P(approval) = EV / NPV(approved) vs model P(approval) = rNPV / NPV(approved)",
        f"  NPV(approved) derived from peak_sales × {_PEAK_SALES_TO_NPV_MULTIPLE}x multiple, or rNPV ÷ stage-industry POS",
        "  Positive gap = market underprices relative to model → long edge",
        "=" * 100,
        f"  {'Ticker':<8}  {'EV':<9}  {'NPV(approved)':<13}  {'Market POS':<7}  {'Model POS':<7}  {'Edge':<15}  Direction",
        "-" * 100,
    ]
    for _, line in entries:
        lines.append(line)
    lines.append("-" * 100)
    lines.append(
        f"  Note: NPV(approved) = peak_sales × {_PEAK_SALES_TO_NPV_MULTIPLE}x where available, else rNPV ÷ stage-POS."
        "  Model POS = rNPV ÷ NPV(approved).  Larger gap = larger disagreement = larger edge."
    )
    return "\n".join(lines)


def _format_acquisition_timeline(result: "MAProbabilityResult") -> str:
    """Section 3: Acquisition probability ranking with estimated timeline.

    Covers all companies with a realistic chance of acquisition within 2 years.
    Timeline = process duration from first approach to regulatory close,
    based on median observed biotech deal timelines (exploratory 2-4m +
    due diligence 2-4m + legal 1-3m + HSR/regulatory 2-4m = 7-15m base).
    """
    rows_with_timeline: list[tuple[float, int, str]] = []  # (score, min_m, line)

    for row in result.rows:
        score = row.mna_probability_score
        if score < 0.15:
            continue
        min_m, max_m = _timeline_for_row(row)
        if max_m > 30:
            continue  # outside 2-year window

        ticker = row.ticker or row.asset_id
        stage = row.stage or "unknown"
        acquirer = row.best_acquirer_name or row.best_acquirer_id or "unknown"
        gap = row.matched_therapeutic_gap or "unknown"
        urgency = getattr(row, "gap_urgency", None) or "—"
        watchlist = getattr(row, "watchlist_type", None) or "strategic_watch"
        drivers = getattr(row, "transaction_driver_count", None)
        dtc = row.days_to_catalyst

        # Timeline label
        if max_m <= 9:
            timeline_label = f"{min_m}-{max_m}m (NEAR TERM)"
        elif max_m <= 18:
            timeline_label = f"{min_m}-{max_m}m"
        else:
            timeline_label = f"{min_m}-{max_m}m (MEDIUM)"

        # Conviction label
        if score >= 0.65:
            conviction = "HIGH"
        elif score >= 0.45:
            conviction = "MED"
        else:
            conviction = "LOW"

        # Key signal summary
        signals: list[str] = []
        if urgency == "high":
            signals.append("gap-urgency:HIGH")
        if drivers and drivers >= 2:
            signals.append(f"{drivers}-drivers")
        if row.capital_vulnerability_score > 0.60:
            signals.append("capital-stress")
        if dtc is not None and dtc < 90:
            signals.append(f"catalyst-in-{dtc}d")
        if watchlist == "near_term_transaction":
            signals.append("near-term-flag")
        signal_str = " | ".join(signals) if signals else "no-near-term-triggers"

        line = (
            f"  {ticker:<8}  {_fmt_pct(score):<7}  [{conviction}]  "
            f"timeline={timeline_label:<22}  stage={stage:<10}  "
            f"best_acquirer={acquirer:<22}  gap={gap:<30}  {signal_str}"
        )
        rows_with_timeline.append((score, min_m, line))

    if not rows_with_timeline:
        return ""

    rows_with_timeline.sort(key=lambda t: (-t[0], t[1]))

    lines = [
        "",
        "=" * 130,
        "ACQUISITION PROBABILITY RANKING — 2-YEAR SCOPE",
        "  All companies with realistic acquisition chance within 24 months.",
        "  Timeline = estimated months from first approach to regulatory close.",
        "  Process breakdown: exploratory (2-4m) + DD (2-4m) + legal (1-3m) + clearance (2-4m).",
        "  Adjustments: near_term_transaction flag (−5m), gap_urgency=high (−3m),",
        "               ≥2 drivers (−3m), catalyst within 90d (−3m), capital stress (−4m).",
        "=" * 130,
        f"  {'Ticker':<8}  {'M&A%':<7}  Conv  {'Timeline':<22}  {'Stage':<10}  {'Best Acquirer':<22}  {'Gap':<30}  Signals",
        "-" * 130,
    ]
    for _, _, line in rows_with_timeline:
        lines.append(line)
    lines.append("-" * 130)
    lines.append(
        f"  {len(rows_with_timeline)} companies in 2-year acquisition scope  |  "
        f"Threshold: M&A score ≥ 15% and estimated close ≤ 30 months"
    )
    return "\n".join(lines)


def _format_report(result: MAProbabilityResult) -> str:
    if not result.rows:
        return f"No M&A probability rows found for {result.as_of_date.isoformat()}."

    widths = [4, 18, 8, 8, 8, 14, 17, 8, 8, 8, 10, 18]
    header = (
        f"{'Rank':<{widths[0]}}  "
        f"{'Asset':<{widths[1]}}  "
        f"{'Ticker':<{widths[2]}}  "
        f"{'M&A':>{widths[3]}}  "
        f"{'Cal':>{widths[4]}}  "
        f"{'Acquirer':<{widths[5]}}  "
        f"{'Deal Range':<{widths[6]}}  "
        f"{'Disc':>{widths[7]}}  "
        f"{'Fit':>{widths[8]}}  "
        f"{'D-Risk':>{widths[9]}}  "
        f"{'CapV':>{widths[10]}}  "
        f"{'Flags':<{widths[11]}}"
    )
    separator = "-" * len(header)
    threshold_pct = int(round(result.alert_threshold * 100))
    lines = [
        f"WEEKLY M&A TARGETING SCAN — {result.as_of_date.isoformat()}",
        f"Score version: {result.score_version} | "
        f"Assets: {result.n_assets} | "
        f"Ranked: {result.n_ranked} | "
        f"Above {threshold_pct}%: {result.n_above_alert_threshold} | "
        f"Snapshots written: {result.snapshots_written} | "
        f"Alerts emitted: {len(result.alerts_emitted)}",
    ]
    if result.calibration_threshold is not None:
        lines.append(
            f"Calibration: {result.calibration_policy} | "
            f"Threshold: {result.calibration_threshold:.2f}"
        )
    if result.reference_snapshot_date is not None:
        lines.append(
            f"Reference snapshot: {result.reference_snapshot_date} | "
            f"Duplicate alerts suppressed: {result.alerts_suppressed_as_duplicate}"
        )
    lines.extend([separator, header, separator])
    for row in result.rows:
        lines.append(
            f"{row.rank:<{widths[0]}}  "
            f"{row.asset_id:<{widths[1]}}  "
            f"{_fmt_text(row.ticker):<{widths[2]}}  "
            f"{_fmt_pct(row.mna_probability_score):>{widths[3]}}  "
            f"{_fmt_pct(row.p_takeout_calibrated):>{widths[4]}}  "
            f"{row.best_acquirer_id:<{widths[5]}}  "
            f"{_fmt_deal_range(row):<{widths[6]}}  "
            f"{_fmt_ratio(row.acquisition_discount):>{widths[7]}}  "
            f"{_fmt_score(row.strategic_fit_score):>{widths[8]}}  "
            f"{_fmt_score(row.de_risking_stage_score):>{widths[9]}}  "
            f"{_fmt_score(row.capital_vulnerability_score):>{widths[10]}}  "
            f"{_fmt_flags(row):<{widths[11]}}"
        )
        lines.append(
            "      "
            f"runner_up={_fmt_text(row.runner_up_acquirer_id)}  "
            f"fit={row.best_acquirer_fit_score:.3f}  "
            f"source={_fmt_text(row.estimated_deal_value_source)}  "
            f"runway={_fmt_text(row.cash_runway_risk_level)}  "
            f"signals={','.join(row.target_signal_ids + row.external_deal_signal_ids) or 'none'}  "
            f"explanation={row.explanation}"
        )

    mispricing_section = _format_variant_perception(result)
    if mispricing_section:
        lines.append(mispricing_section)

    timeline_section = _format_acquisition_timeline(result)
    if timeline_section:
        lines.append(timeline_section)

    return "\n".join(lines)


def main() -> None:
    args = _build_parser().parse_args()
    watchlist_path = _resolve_watchlist_path(args.watchlist)
    config = load_watchlist_config(watchlist_path)

    as_of: Optional[date] = None
    if args.as_of:
        try:
            as_of = _parse_date(args.as_of)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1)

    db_path = args.db or config.knowledge_db_path
    knowledge = KnowledgeStore(db_path)
    try:
        result = MAProbabilityScanner(
            knowledge_store=knowledge,
            config=MAProbabilityConfig(
                top_n=args.top,
                alert_threshold=args.alert_threshold,
                vulnerability_signals_path=args.vulnerability_file,
                persist_daily_snapshots=args.emit_alerts,
                enable_monitor=args.emit_alerts,
                calibration_model_path=args.calibration_model,
                calibration_policy=args.calibration_policy,
                calibration_threshold=args.calibration_threshold,
                fit_integration_config={
                    "acquirer_profiles_path": args.profiles_file,
                    "comparable_deals_path": args.comps_file,
                    "top_n": args.top,
                    "require_acquisition_readiness": args.readiness_filter == "strict",
                },
            ),
        ).scan_from_watchlist_config(
            config,
            snapshot_date=as_of,
            top_n=args.top,
        )
    finally:
        knowledge.close()

    output = (
        json.dumps(result.model_dump(mode="json"), indent=2)
        if args.output_format == "json"
        else _format_report(result)
    )
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"M&A probability report written to {out_path}", file=sys.stderr)
        return
    print(output)


if __name__ == "__main__":
    main()
