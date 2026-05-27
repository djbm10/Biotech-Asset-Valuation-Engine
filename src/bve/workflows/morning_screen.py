"""Block 12 — morning_screen workflow.

Produces a daily ranked screen showing all actionable items across the
tracked universe.  Sections (all optional / degrade gracefully):

  1. Top M&A / BD Action Candidates   — ranked by M&A probability score
  2. Top Valuation Dislocations       — tickers with valuation output + implied upside
  3. Catalyst / Watchlist Items       — upcoming catalysts from UNIVERSE
  4. ClinicalTrials.gov Changes       — trial status diffs if trial_diff available
  5. Stale / Low-Integrity Inputs     — tickers with staleness warnings
  6. Unresolved Prediction Log Items  — open predictions awaiting resolution

Usage (Python)
--------------
    from bve.workflows.morning_screen import morning_screen
    report = morning_screen()
    print(report)

Usage (CLI)
-----------
    bve-morning-screen
    bve-morning-screen --output outputs/screen_2026-05-27.md
    bve-morning-screen --top 15 --no-trial-diff
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Section 1: M&A / BD candidates
# ---------------------------------------------------------------------------

def _load_ma_rows(ops_db: Path, top_n: int) -> list[object]:
    """Load top M&A probability rows from ops.db snapshot store."""
    try:
        if not ops_db.exists():
            return []
        from bve.intelligence.ma_probability import MAProbabilityScanner
        from bve.intelligence.knowledge_layer import KnowledgeStore
        kb = KnowledgeStore(str(ops_db))
        scanner = MAProbabilityScanner(knowledge_store=kb)
        rows = scanner.scan_watchlist(limit=top_n * 4)
        # Sort by mna_probability_score desc, take top_n
        sorted_rows = sorted(
            rows,
            key=lambda r: getattr(r, "mna_probability_score", 0.0),
            reverse=True,
        )
        return sorted_rows[:top_n]
    except Exception:
        return []


def _render_ma_section(rows: list[object], top_n: int) -> str:
    lines = ["## Top M&A / BD Action Candidates", ""]
    if not rows:
        lines += ["_No M&A probability data available. Run `bve-ma-probability` to populate._", ""]
        return "\n".join(lines)

    lines += [
        "| # | Ticker | Score | P(acq) | Best Acquirer | Watchlist | Stage |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(rows, 1):
        ticker    = getattr(row, "ticker", None) or getattr(row, "asset_id", "—")
        score     = getattr(row, "mna_probability_score", None)
        score_s   = f"{score:.3f}" if score is not None else "—"
        p_acq     = getattr(row, "p_acquisition", None)
        p_acq_s   = f"{p_acq:.3f}" if p_acq is not None else "—"
        acquirer  = getattr(row, "best_acquirer_name", None) or "—"
        watchlist = getattr(row, "watchlist_type", None) or "—"
        stage     = getattr(row, "stage", None) or "—"
        lines.append(f"| {i} | {ticker} | {score_s} | {p_acq_s} | {acquirer} | {watchlist} | {stage} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 2: Valuation dislocations
# ---------------------------------------------------------------------------

def _load_valuation_dislocations(outputs_dir: Path, top_n: int) -> list[dict]:
    """Scan outputs/<TICKER>/valuation.json files for implied upside."""
    results = []
    try:
        if not outputs_dir.exists():
            return []
        for ticker_dir in sorted(outputs_dir.iterdir()):
            if not ticker_dir.is_dir():
                continue
            vj = ticker_dir / "valuation.json"
            if not vj.exists():
                continue
            try:
                raw = json.loads(vj.read_text())
                upside = raw.get("implied_upside_pct")
                base_rnpv = raw.get("base_rnpv")
                nav_ps = raw.get("nav_per_share")
                if upside is not None or base_rnpv is not None:
                    results.append({
                        "ticker": ticker_dir.name,
                        "implied_upside_pct": upside,
                        "base_rnpv": base_rnpv,
                        "nav_per_share": nav_ps,
                        "prob_approval_pct": raw.get("prob_approval_pct"),
                        "as_of": raw.get("as_of") or raw.get("run_date"),
                    })
            except Exception:
                continue
    except Exception:
        pass

    # Sort by absolute implied upside desc (largest discrepancy = most actionable)
    results.sort(key=lambda x: abs(x.get("implied_upside_pct") or 0), reverse=True)
    return results[:top_n]


def _render_valuation_section(dislocations: list[dict]) -> str:
    lines = ["## Top Valuation Dislocations", ""]
    if not dislocations:
        lines += [
            "_No valuation outputs found. Run `bve-asset --config <yaml>` "
            "to generate outputs/<TICKER>/valuation.json._",
            "",
        ]
        return "\n".join(lines)

    lines += [
        "| Ticker | rNPV Base ($M) | NAV/share ($) | Implied Upside | P(approval) | As of |",
        "|---|---|---|---|---|---|",
    ]
    for d in dislocations:
        ticker   = d["ticker"]
        rnpv     = f"{d['base_rnpv']:.0f}" if d["base_rnpv"] is not None else "—"
        nav      = f"{d['nav_per_share']:.2f}" if d["nav_per_share"] is not None else "—"
        upside   = d["implied_upside_pct"]
        upside_s = f"{upside:+.0f}%" if upside is not None else "—"
        prob     = d.get("prob_approval_pct") or "—"
        as_of    = d.get("as_of") or "—"
        lines.append(f"| {ticker} | {rnpv} | {nav} | {upside_s} | {prob} | {as_of} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 3: Catalysts from UNIVERSE
# ---------------------------------------------------------------------------

def _load_catalysts(top_n: int) -> list[dict]:
    """Pull upcoming catalysts from UNIVERSE watchlist."""
    try:
        from bve.ops.universe_data import UNIVERSE
        items = []
        for asset in UNIVERSE:
            ticker = asset.get("ticker", "")
            catalyst = asset.get("catalyst", "")
            if catalyst:
                items.append({
                    "ticker": ticker,
                    "catalyst": catalyst,
                    "conviction": asset.get("conviction", "—"),
                    "ranking_score": asset.get("ranking_score"),
                })
        return items[:top_n]
    except Exception:
        return []


def _render_catalyst_section(items: list[dict]) -> str:
    lines = ["## Catalyst / Watchlist Items", ""]
    if not items:
        lines += ["_No watchlist catalyst data available._", ""]
        return "\n".join(lines)

    lines += [
        "| Ticker | Catalyst | Conviction | Score |",
        "|---|---|---|---|",
    ]
    for item in items:
        ticker     = item["ticker"]
        catalyst   = item["catalyst"][:80]
        conviction = item.get("conviction", "—")
        score      = item.get("ranking_score")
        score_s    = f"{score:.2f}" if score is not None else "—"
        lines.append(f"| {ticker} | {catalyst} | {conviction} | {score_s} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 4: CT.gov trial diffs
# ---------------------------------------------------------------------------

def _load_trial_diffs() -> list[object]:
    """Attempt to load recent high/medium severity trial changes."""
    try:
        # No stored records available yet — return empty list gracefully
        return []
    except Exception:
        return []


def _render_trial_diff_section(changes: list[object]) -> str:
    lines = ["## ClinicalTrials.gov Changes", ""]
    if not changes:
        lines += [
            "_No CT.gov diff data available. Run `bve-trial-diff --nct <NCT_ID>` "
            "to check specific trials._",
            "",
        ]
        return "\n".join(lines)

    lines += ["| NCT ID | Change Type | Severity | Detail |", "|---|---|---|---|"]
    for ch in changes:
        nct      = getattr(ch, "nct_id", "—")
        ctype    = getattr(ch, "change_type", "—")
        severity = getattr(ch, "severity", "—")
        detail   = getattr(ch, "detail", "")[:60]
        lines.append(f"| {nct} | {ctype} | {severity} | {detail} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 5: Stale / low-integrity inputs
# ---------------------------------------------------------------------------

def _load_stale_inputs(outputs_dir: Path) -> list[dict]:
    """Scan outputs directory for staleness markers in valuation JSONs."""
    stale = []
    try:
        if not outputs_dir.exists():
            return []
        for ticker_dir in sorted(outputs_dir.iterdir()):
            if not ticker_dir.is_dir():
                continue
            vj = ticker_dir / "valuation.json"
            if not vj.exists():
                continue
            try:
                raw = json.loads(vj.read_text())
                warnings = raw.get("staleness_warnings") or []
                if warnings:
                    stale.append({
                        "ticker": ticker_dir.name,
                        "warnings": warnings if isinstance(warnings, list) else [warnings],
                    })
            except Exception:
                continue
    except Exception:
        pass
    return stale


def _render_stale_section(stale: list[dict]) -> str:
    lines = ["## Stale / Low-Integrity Inputs", ""]
    if not stale:
        lines += ["_All tracked inputs appear current._", ""]
        return "\n".join(lines)

    for item in stale:
        ticker = item["ticker"]
        for w in item["warnings"]:
            lines.append(f"- ⚠ **{ticker}**: {w}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 6: Unresolved prediction log items
# ---------------------------------------------------------------------------

def _load_unresolved_predictions(pred_db: Path) -> list[dict]:
    try:
        if not pred_db.exists():
            return []
        from bve.ops.prediction_log import PredictionLog
        log = PredictionLog(str(pred_db))
        return log.unresolved()
    except Exception:
        return []


def _render_prediction_log_section(entries: list[dict]) -> str:
    lines = ["## Unresolved Prediction Log Items", ""]
    if not entries:
        lines += ["_No unresolved predictions._", ""]
        return "\n".join(lines)

    lines += ["| Ticker | Type | Score | Logged At | Notes |", "|---|---|---|---|---|"]
    for e in entries[:20]:  # cap at 20
        ticker     = e.get("ticker") or "—"
        log_type   = e.get("log_type") or "—"
        score      = e.get("score")
        score_s    = f"{score:.3f}" if score is not None else "—"
        logged_at  = str(e.get("logged_at") or "—").split("T")[0]
        notes      = str(e.get("notes") or "—")[:50]
        lines.append(f"| {ticker} | {log_type} | {score_s} | {logged_at} | {notes} |")
    if len(entries) > 20:
        lines.append(f"_... and {len(entries) - 20} more_")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DISCLAIMER = (
    "> ⚠ **Research-grade output only.** Not investment advice. "
    "All scores are model estimates. Validate before acting."
)


def morning_screen(
    *,
    as_of_date: Optional[date] = None,
    outputs_dir: Optional[Path] = None,
    ops_db: Optional[Path] = None,
    prediction_log_db: Optional[Path] = None,
    top_n: int = 10,
    include_trial_diff: bool = True,
) -> str:
    """Build and return the morning screen Markdown report.

    Parameters
    ----------
    as_of_date:
        Screen date; defaults to today.
    outputs_dir:
        Root outputs directory; defaults to ``outputs/``.
    ops_db:
        Path to intelligence ops SQLite; defaults to
        ``outputs/intelligence/ops.db``.
    prediction_log_db:
        Path to prediction log SQLite; defaults to
        ``outputs/intelligence/prediction_log.db``.
    top_n:
        Maximum rows per section.
    include_trial_diff:
        When False, skips CT.gov diff section entirely.

    Returns
    -------
    str
        Complete Markdown morning screen.
    """
    as_of = as_of_date or date.today()
    root = Path("outputs")
    outputs_dir = outputs_dir or root
    ops_db = ops_db or (root / "intelligence" / "ops.db")
    pred_db = prediction_log_db or (root / "intelligence" / "prediction_log.db")

    ma_rows      = _load_ma_rows(ops_db, top_n)
    dislocations = _load_valuation_dislocations(outputs_dir, top_n)
    catalysts    = _load_catalysts(top_n)
    changes      = _load_trial_diffs() if include_trial_diff else []
    stale        = _load_stale_inputs(outputs_dir)
    predictions  = _load_unresolved_predictions(pred_db)

    header = "\n".join([
        f"# BVE Morning Screen — {as_of.isoformat()}",
        "",
        _DISCLAIMER,
        "",
        "---",
        "",
    ])

    parts = [
        header,
        _render_ma_section(ma_rows, top_n),
        _render_valuation_section(dislocations),
        _render_catalyst_section(catalysts),
    ]
    if include_trial_diff:
        parts.append(_render_trial_diff_section(changes))
    parts += [
        _render_stale_section(stale),
        _render_prediction_log_section(predictions),
        f"*Generated: {as_of.isoformat()}*\n",
    ]

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="bve-morning-screen",
        description=(
            "Generate the BVE daily ranked morning screen: top M&A candidates, "
            "valuation dislocations, catalysts, CT.gov changes, stale inputs, "
            "and unresolved predictions."
        ),
    )
    parser.add_argument("--output", default=None, help="Output file. If omitted, prints to stdout.")
    parser.add_argument(
        "--as-of", default=None, dest="as_of",
        help="Screen date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument("--top", type=int, default=10, help="Max rows per section (default: 10).")
    parser.add_argument(
        "--outputs-dir", default=None, dest="outputs_dir",
        help="Root outputs directory. Defaults to outputs/.",
    )
    parser.add_argument(
        "--ops-db", default=None, dest="ops_db",
        help="Path to ops.db.",
    )
    parser.add_argument(
        "--prediction-log", default=None, dest="prediction_log",
        help="Path to prediction_log.db.",
    )
    parser.add_argument(
        "--no-trial-diff", action="store_true", dest="no_trial_diff",
        help="Skip CT.gov trial diff section.",
    )
    args = parser.parse_args(argv)

    as_of_date: Optional[date] = None
    if args.as_of:
        try:
            as_of_date = date.fromisoformat(args.as_of)
        except ValueError:
            print(f"ERROR: invalid --as-of date: {args.as_of!r}", file=sys.stderr)
            return 1

    print("[bve-morning-screen] Generating morning screen...", file=sys.stderr)

    report = morning_screen(
        as_of_date=as_of_date,
        outputs_dir=Path(args.outputs_dir) if args.outputs_dir else None,
        ops_db=Path(args.ops_db) if args.ops_db else None,
        prediction_log_db=Path(args.prediction_log) if args.prediction_log else None,
        top_n=args.top,
        include_trial_diff=not args.no_trial_diff,
    )

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"[bve-morning-screen] Screen written to {out}", file=sys.stderr)
    else:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
