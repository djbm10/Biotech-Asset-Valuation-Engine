"""bve-trial-diff CLI: compare stored trial records against live ClinicalTrials.gov status.

Usage
-----
    bve-trial-diff --nct NCT12345678 NCT98765432
    bve-trial-diff --config examples/configs/relay_rly2608.yaml
    bve-trial-diff --nct NCT12345678 --output outputs/trial_diff.md
    bve-trial-diff --nct NCT12345678 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_nct_ids_from_config(config_path: str) -> list[str]:
    """Extract NCT IDs from a YAML asset config."""
    try:
        import yaml
        data = yaml.safe_load(Path(config_path).read_text())
        trials = data.get("trials") or []
        nct_ids = []
        for t in trials:
            nct_id = t.get("nct_id") or t.get("nct_number")
            if nct_id:
                nct_ids.append(str(nct_id).strip())
        return nct_ids
    except Exception as exc:
        print(f"[bve-trial-diff] Warning: could not load config: {exc}", file=sys.stderr)
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-trial-diff",
        description="Compare stored trial records against live ClinicalTrials.gov status.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--nct",
        nargs="+",
        dest="nct_ids",
        help="One or more NCT IDs to check (e.g. NCT12345678).",
    )
    group.add_argument(
        "--config",
        dest="config_path",
        help="Path to a YAML asset config file to extract NCT IDs from.",
    )
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
    args = parser.parse_args(argv)

    if args.config_path:
        nct_ids = _load_nct_ids_from_config(args.config_path)
        if not nct_ids:
            print("[bve-trial-diff] No NCT IDs found in config. Exiting.", file=sys.stderr)
            return 1
    else:
        nct_ids = args.nct_ids

    print(f"[bve-trial-diff] Diffing {len(nct_ids)} trial(s) against CT.gov...", file=sys.stderr)

    from bve.refresh.trial_diff import StoredTrialRecord, run_trial_diff, render_trial_diff

    # Build minimal stored records (no stored state — diff checks live vs None)
    stored = [StoredTrialRecord(nct_id=nct_id) for nct_id in nct_ids]
    result = run_trial_diff(stored)

    if result.high_severity_changes:
        print(
            f"[bve-trial-diff] {len(result.high_severity_changes)} high-severity change(s) detected.",
            file=sys.stderr,
        )

    if args.as_json:
        rendered = json.dumps(result.to_dict(), indent=2, default=str)
    else:
        rendered = render_trial_diff(result)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(f"[bve-trial-diff] Output written to {out_path}", file=sys.stderr)
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
