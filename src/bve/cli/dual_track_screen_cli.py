"""bve-dual-track CLI: the dedicated dual-track screen artifact.

Joins the BD/M&A screen rows (``MAProbabilityRow`` — rich: rNPV, EV,
recommended deal structure, best acquirer) with the investment lens
(``outputs/<TICKER>/valuation.json`` when present, else a coarse rNPV-vs-EV
read), and writes:

    <output-dir>/dual_track.csv
    <output-dir>/dual_track_report.md

The two lenses are kept separate; a missing lens is shown as not_assessed /
not_run, never a negative verdict. The legacy M&A screen and its composite
score are not touched.

Usage
-----
    bve-dual-track
    bve-dual-track --limit 50 --output-dir outputs/dual_track
    bve-dual-track --outputs-dir outputs --db outputs/intelligence/ops.db
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


def _load_ma_rows(db_path: str, top_n: int) -> list:
    """Load ranked MAProbabilityRow rows from the canonical watchlist scan.

    Reuses ``weekly_runner._run_mna_scan`` — the single source of truth for
    scanning the tracked UNIVERSE (it builds the WatchlistAsset list, wires the
    research-file config, and returns an ``MAProbabilityResult``). Returns an
    empty list when the M&A research files are unavailable.
    """
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.ops.weekly_runner import _run_mna_scan

    store = KnowledgeStore(db_path)
    result = _run_mna_scan(store, top_n=top_n)
    if result is None:
        return []
    return list(getattr(result, "rows", []))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-dual-track",
        description="Generate the dedicated dual-track (investment + BD) screen.",
    )
    parser.add_argument("--output-dir", default="outputs/dual_track",
                        help="Where to write dual_track.csv + dual_track_report.md.")
    parser.add_argument("--outputs-dir", default="outputs",
                        help="Root holding <TICKER>/valuation.json for the investment lens.")
    parser.add_argument("--db", default="outputs/intelligence/ops.db",
                        help="KnowledgeStore path for the M&A watchlist scan.")
    parser.add_argument("--top-n", type=int, default=30, dest="top_n",
                        help="Number of ranked targets to assess.")
    parser.add_argument("--as-of", default=None, help="Report date (YYYY-MM-DD).")
    args = parser.parse_args(argv)

    as_of = args.as_of or date.today().isoformat()

    if not Path(args.db).exists():
        print(f"ERROR: knowledge store not found: {args.db}", file=sys.stderr)
        print("Run the weekly/M&A scan first to populate the watchlist.", file=sys.stderr)
        return 1

    print(f"[bve-dual-track] Scanning M&A watchlist (top_n={args.top_n})...", file=sys.stderr)
    try:
        rows = _load_ma_rows(args.db, args.top_n)
    except Exception as e:  # pragma: no cover - environment dependent
        print(f"ERROR: M&A scan failed: {e}", file=sys.stderr)
        return 1

    if not rows:
        print("[bve-dual-track] No targets returned by the scan.", file=sys.stderr)
        return 1

    from bve.analysis.dual_track_screen import (
        assess_targets,
        render_dual_track_report,
        write_dual_track_csv,
    )

    assessed = assess_targets(rows, outputs_dir=args.outputs_dir)

    out_dir = Path(args.output_dir)
    csv_path = write_dual_track_csv(assessed, out_dir / "dual_track.csv")
    report = render_dual_track_report(assessed, as_of=as_of)
    report_path = out_dir / "dual_track_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    n_full = sum(1 for _, a in assessed if a.investment.evidence == "full")
    n_coarse = sum(1 for _, a in assessed if a.investment.evidence == "coarse")
    n_div = sum(1 for _, a in assessed if a.divergence)
    print(
        f"[bve-dual-track] {len(assessed)} names "
        f"({n_full} full / {n_coarse} coarse investment; {n_div} divergent).",
        file=sys.stderr,
    )
    print(f"[bve-dual-track] Wrote {csv_path}", file=sys.stderr)
    print(f"[bve-dual-track] Wrote {report_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
