"""bve-input-integrity CLI: compute and display the InputIntegrityScore for a ticker.

Usage
-----
    bve-input-integrity TICKER
    bve-input-integrity TICKER --output outputs/integrity.md
    bve-input-integrity TICKER --json
    bve-input-integrity TICKER --no-market --no-financials
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-input-integrity",
        description="Compute the InputIntegrityScore for a ticker.",
    )
    parser.add_argument("ticker", help="Stock ticker (e.g. SRPT).")
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output JSON instead of Markdown.",
    )
    parser.add_argument("--no-market", action="store_true", help="Skip market data refresh.")
    parser.add_argument("--no-financials", action="store_true", help="Skip financial refresh.")
    parser.add_argument("--no-profiles", action="store_true", help="Skip acquirer profile audit.")
    parser.add_argument("--no-trials", action="store_true", help="Skip trial diff.")
    parser.add_argument(
        "--profiles",
        default=None,
        help="Path to pipeline_gaps.yaml. Defaults to research/mna/pipeline_gaps.yaml.",
    )
    parser.add_argument(
        "--nct",
        nargs="*",
        dest="nct_ids",
        default=None,
        help="NCT IDs to check for trial diff.",
    )
    args = parser.parse_args(argv)

    ticker = args.ticker.upper()
    print(f"[bve-input-integrity] Computing input integrity score for {ticker}...", file=sys.stderr)

    market_snap = None
    fin_snap = None
    profile_audit = None
    trial_diff = None

    # Market data
    if not args.no_market:
        try:
            from bve.refresh.market_data_refresh import fetch_market_snapshot
            print("[bve-input-integrity] Fetching market data...", file=sys.stderr)
            market_snap = fetch_market_snapshot(ticker)
        except Exception as exc:
            print(f"[bve-input-integrity] Market data fetch failed: {exc}", file=sys.stderr)

    # Financials
    if not args.no_financials:
        try:
            from bve.refresh.financial_refresh import fetch_financial_snapshot
            print("[bve-input-integrity] Fetching financials...", file=sys.stderr)
            fin_snap = fetch_financial_snapshot(ticker)
        except Exception as exc:
            print(f"[bve-input-integrity] Financial fetch failed: {exc}", file=sys.stderr)

    # Profile audit
    if not args.no_profiles:
        try:
            from bve.refresh.profile_audit import audit_profiles_from_yaml
            print("[bve-input-integrity] Auditing acquirer profiles...", file=sys.stderr)
            profile_audit = audit_profiles_from_yaml(args.profiles)
        except Exception as exc:
            print(f"[bve-input-integrity] Profile audit failed: {exc}", file=sys.stderr)

    # Trial diff
    if not args.no_trials and args.nct_ids:
        try:
            from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff
            print("[bve-input-integrity] Running trial diff...", file=sys.stderr)
            stored = [StoredTrialRecord(nct_id=nct_id) for nct_id in args.nct_ids]
            trial_diff = run_trial_diff(stored)
        except Exception as exc:
            print(f"[bve-input-integrity] Trial diff failed: {exc}", file=sys.stderr)

    from bve.refresh.input_integrity import build_input_integrity_score, render_input_integrity

    score = build_input_integrity_score(
        market_snapshot=market_snap,
        financial_snapshot=fin_snap,
        profile_audit=profile_audit,
        trial_diff=trial_diff,
    )

    print(
        f"[bve-input-integrity] Grade: {score.overall_grade} "
        f"({score.overall_score:.2f}/1.00)",
        file=sys.stderr,
    )

    if args.as_json:
        rendered = json.dumps(score.to_dict(), indent=2, default=str)
    else:
        rendered = render_input_integrity(score)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(f"[bve-input-integrity] Output written to {out_path}", file=sys.stderr)
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
