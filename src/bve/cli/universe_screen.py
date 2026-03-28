"""
CLI entry point: bve-universe-screen

Standalone universe-level implied PoS screen.
Requires no KnowledgeStore or pre-seeded database — fetches live market data
from yfinance at run time.

Output columns:
  TICKER  STAGE  MODEL_POS  IMPLIED_POS  SPREAD  rNPV($M)  EV($M)  ACQ_DISC%  NEXT_CATALYST  D2CAT

Sort: SPREAD descending (biggest mispricing first) by default.

Usage
-----
    bve-universe-screen
    bve-universe-screen --sort rnpv
    bve-universe-screen --min-spread 10
    bve-universe-screen --single-asset-only
    bve-universe-screen --json
    bve-universe-screen --no-live           # offline mode; zero financials
    bve-universe-screen --mna               # add FIT column (strategic fit vs 3 acquirers)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from bve.analysis.implied_pos_batch import ScreenRow, run_screen
from bve.ops.weekly_runner import UNIVERSE

_SPREAD_GREEN = "\033[92m"  # green
_SPREAD_RED   = "\033[91m"  # red
_WARN_YELLOW  = "\033[93m"  # yellow
_RESET        = "\033[0m"

_APPROX_MARKER = "~"    # shown next to tickers where single_asset=False


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Universe-level implied PoS screen. "
            "Ranks 27 names by model_pos − implied_pos spread."
        )
    )
    p.add_argument(
        "--sort",
        choices=["spread", "rnpv", "ev", "d2cat", "ticker"],
        default="spread",
        help="Sort column (default: spread, descending)",
    )
    p.add_argument(
        "--min-spread",
        type=float,
        default=None,
        metavar="PP",
        help="Only show rows with spread ≥ PP percentage points",
    )
    p.add_argument(
        "--single-asset-only",
        action="store_true",
        help="Exclude multi-program companies where implied PoS is approximate",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of table",
    )
    p.add_argument(
        "--no-live",
        action="store_true",
        help="Offline mode: skip yfinance calls; implied_pos will be n/a",
    )
    p.add_argument(
        "--params",
        default=None,
        metavar="PATH",
        help="Override path to research/universe_params.yaml",
    )
    p.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Write output to file instead of stdout",
    )
    p.add_argument(
        "--as-of",
        default=None,
        metavar="YYYY-MM-DD",
        help="Show archived screen from KnowledgeStore instead of running live",
    )
    p.add_argument(
        "--mna",
        action="store_true",
        help=(
            "Show M&A strategic fit column (FIT score vs Pfizer, Lilly, Novo Nordisk). "
            "Adds FIT and BEST_FIT_FOR columns."
        ),
    )
    return p


def _fmt_pos(v: Optional[float]) -> str:
    if v is None:
        return " n/a  "
    return f"{v * 100:5.1f}%"


def _fmt_spread(v: Optional[float], use_color: bool = True) -> str:
    if v is None:
        return "  n/a   "
    sign = "+" if v >= 0 else ""
    s = f"{sign}{v:.1f}pp"
    if not use_color:
        return f"{s:>8}"
    color = _SPREAD_GREEN if v > 0 else (_SPREAD_RED if v < 0 else "")
    return f"{color}{s:>8}{_RESET}"


def _fmt_millions(v: Optional[float]) -> str:
    if v is None:
        return "   n/a"
    return f"${v:>7,.0f}"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "  n/a"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _fmt_catalyst(row: ScreenRow) -> str:
    cat = row.next_catalyst or ""
    # Truncate long catalyst descriptions
    return cat[:32] if len(cat) > 32 else cat


def _fmt_d2cat(row: ScreenRow) -> str:
    if row.days_to_catalyst is None:
        return " n/a"
    return f"{row.days_to_catalyst:>4d}"


def _ticker_label(row: ScreenRow) -> str:
    label = row.ticker
    if not row.single_asset:
        label = label + _APPROX_MARKER
    return f"{label:<7}"


def _format_table(rows: list[ScreenRow], use_color: bool = True) -> str:
    header = (
        f"{'TICKER':<7}  {'STAGE':<9}  "
        f"{'MODEL%':>6}  {'IMP%':>6}  {'SPREAD':>8}  "
        f"{'rNPV($M)':>9}  {'EV($M)':>9}  {'ACQ%':>6}  "
        f"{'NEXT_CATALYST':<34}  {'D2CAT':>5}"
    )
    sep = "─" * len(header)
    lines = [
        f"Universe implied PoS screen  |  {date.today().isoformat()}  |  N={len(rows)}",
        f"Sorted by: spread descending  |  {_APPROX_MARKER} = multi-program (spread approximate)",
        sep,
        header,
        sep,
    ]
    for row in rows:
        line = (
            f"{_ticker_label(row)}  "
            f"{row.stage:<9}  "
            f"{_fmt_pos(row.model_pos):>6}  "
            f"{_fmt_pos(row.implied_pos):>6}  "
            f"{_fmt_spread(row.spread_pp, use_color)}  "
            f"{_fmt_millions(row.rnpv_millions):>9}  "
            f"{_fmt_millions(row.ev_millions):>9}  "
            f"{_fmt_pct(row.acquisition_discount_pct):>6}  "
            f"{_fmt_catalyst(row):<34}  "
            f"{_fmt_d2cat(row):>5}"
        )
        lines.append(line)
    lines.append(sep)
    lines.append(
        "Spread = model_pos − implied_pos  |  +pp = market too pessimistic (potential upside)  |  −pp = market too optimistic"
    )
    return "\n".join(lines)


def _to_json(rows: list[ScreenRow]) -> str:
    out = []
    for row in rows:
        out.append({
            "ticker": row.ticker,
            "program_label": row.program_label,
            "stage": row.stage,
            "ta": row.ta,
            "model_pos": row.model_pos,
            "implied_pos": row.implied_pos,
            "spread_pp": row.spread_pp,
            "rnpv_millions": row.rnpv_millions,
            "ev_millions": row.ev_millions,
            "acquisition_discount_pct": row.acquisition_discount_pct,
            "next_catalyst": row.next_catalyst,
            "catalyst_date": row.catalyst_date.isoformat() if row.catalyst_date else None,
            "days_to_catalyst": row.days_to_catalyst,
            "single_asset": row.single_asset,
            "approximation_warning": row.approximation_warning,
            "data_date": row.data_date.isoformat(),
        })
    return json.dumps(out, indent=2)


def _load_mna_scores(
    rows: list[ScreenRow],
    params_path: Optional[Path] = None,
) -> dict[str, tuple[float, str]]:
    """
    Return {ticker: (max_fit_score, best_acquirer_name)} for each row.

    Loads universe_params.yaml for asset profiles and acquirer_profiles.yaml
    for acquirer profiles. Returns empty dict on any error (MNA is additive).
    """
    try:
        import yaml as _yaml
        from bve.intelligence.strategic_fit.strategic_fit import (
            load_acquirer_profiles,
            score_all_acquirers,
        )

        _params_path = params_path or (
            Path(__file__).parents[3] / "research" / "universe_params.yaml"
        )
        with open(_params_path) as fh:
            params_data = _yaml.safe_load(fh)

        universe_params: dict = params_data.get("universe", {})
        profiles = load_acquirer_profiles()

        out: dict[str, tuple[float, str]] = {}
        for row in rows:
            ticker = row.ticker
            asset_cfg = universe_params.get(ticker, {})
            asset_profile = {
                "ticker": ticker,
                "ta": asset_cfg.get("ta", row.ta or "other"),
                "phase": asset_cfg.get("phase", row.stage or ""),
                "program_label": asset_cfg.get("program_label", row.program_label or ""),
                "peak_sales_millions": asset_cfg.get("peak_sales_millions", row.rnpv_millions or 0),
                "modality": asset_cfg.get("modality", ""),
            }
            scores = score_all_acquirers(asset_profile, profiles)
            best = scores[0]
            out[ticker] = (best.total, best.acquirer_name)
        return out
    except Exception:  # noqa: BLE001
        return {}


def _format_mna_table(
    rows: list[ScreenRow],
    mna_scores: dict[str, tuple[float, str]],
    use_color: bool = True,
) -> str:
    header = (
        f"{'TICKER':<7}  {'STAGE':<9}  "
        f"{'SPREAD':>8}  {'rNPV($M)':>9}  "
        f"{'FIT':>5}  {'BEST_FIT_FOR':<16}  "
        f"{'NEXT_CATALYST':<34}  {'D2CAT':>5}"
    )
    sep = "─" * len(header)
    lines = [
        f"Universe M&A Strategic Fit  |  {date.today().isoformat()}  |  N={len(rows)}",
        "Acquirers: Pfizer, Lilly, Novo Nordisk  |  FIT = max score across all 3",
        sep,
        header,
        sep,
    ]
    for row in rows:
        fit, best_acq = mna_scores.get(row.ticker, (0.0, "n/a"))
        fit_str = f"{fit:.2f}" if fit else " n/a"
        line = (
            f"{_ticker_label(row)}  "
            f"{row.stage:<9}  "
            f"{_fmt_spread(row.spread_pp, use_color)}  "
            f"{_fmt_millions(row.rnpv_millions):>9}  "
            f"{fit_str:>5}  "
            f"{best_acq:<16}  "
            f"{_fmt_catalyst(row):<34}  "
            f"{_fmt_d2cat(row):>5}"
        )
        lines.append(line)
    lines.append(sep)
    lines.append(
        "FIT: 0.0 = no fit  |  1.0 = perfect fit  |  ta_match×0.35 + stage×0.20 + mech×0.30 + commercial×0.15"
    )
    return "\n".join(lines)


def _rows_from_store(as_of_str: str) -> list[ScreenRow]:
    """Load historical screen rows from KnowledgeStore for --as-of mode."""
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.ops.weekly_runner import DB_PATH

    as_of = date.fromisoformat(as_of_str)
    store = KnowledgeStore(DB_PATH)
    raw = store.get_screen_snapshots(snapshot_date=as_of)
    store.close()

    rows: list[ScreenRow] = []
    for r in raw:
        rows.append(ScreenRow(
            ticker=r["ticker"],
            program_label=r["program_label"] or r["ticker"],
            stage=r["stage"] or "unknown",
            ta=r["ta"] or "other",
            model_pos=r["model_pos"] or 0.0,
            implied_pos=r["implied_pos"],
            spread_pp=r["spread_pp"],
            rnpv_millions=r["rnpv_millions"] or 0.0,
            ev_millions=r["ev_millions"],
            acquisition_discount_pct=r["acquisition_discount_pct"],
            next_catalyst=r["next_catalyst"] or "",
            catalyst_date=(
                date.fromisoformat(r["catalyst_date"]) if r["catalyst_date"] else None
            ),
            days_to_catalyst=r["days_to_catalyst"],
            single_asset=bool(r["single_asset"]),
            approximation_warning=r["approximation_warning"],
            data_date=as_of,
        ))
    return rows


def main() -> None:
    args = _build_parser().parse_args()

    # --as-of mode: read historical snapshot from KnowledgeStore
    if getattr(args, "as_of", None):
        print(
            f"Loading archived screen for {args.as_of} from KnowledgeStore...",
            file=sys.stderr,
        )
        rows = _rows_from_store(args.as_of)
        if not rows:
            print(f"No screen snapshot found for {args.as_of}.", file=sys.stderr)
            sys.exit(1)
    else:
        params_path = Path(args.params) if args.params else None
        fetch_live = not args.no_live

        print(
            f"Running universe screen ({len(UNIVERSE)} names, "
            f"{'live market data' if fetch_live else 'offline mode'})...",
            file=sys.stderr,
        )

        rows = run_screen(
            UNIVERSE,
            params_path=params_path,
            fetch_live=fetch_live,
            sort_by=args.sort,
            single_asset_only=args.single_asset_only,
        )

    # Apply min-spread filter
    if args.min_spread is not None:
        rows = [r for r in rows if r.spread_pp is not None and r.spread_pp >= args.min_spread]

    # Sort (already sorted by run_screen; re-sort for --as-of mode)
    if getattr(args, "as_of", None) and args.sort != "spread":
        def _sort_key(r: ScreenRow):
            if args.sort == "rnpv":
                return -r.rnpv_millions
            if args.sort == "ev":
                return -(r.ev_millions or 0)
            if args.sort == "d2cat":
                return (r.days_to_catalyst is None, r.days_to_catalyst or 9999)
            return r.ticker
        rows.sort(key=_sort_key)

    # Format
    use_color = sys.stdout.isatty() and not args.output
    if args.json:
        output = _to_json(rows)
    elif getattr(args, "mna", False):
        params_path = Path(args.params) if args.params else None
        mna_scores = _load_mna_scores(rows, params_path=params_path)
        output = _format_mna_table(rows, mna_scores, use_color=use_color)
    else:
        output = _format_table(rows, use_color=use_color)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Screen written to {out_path}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
