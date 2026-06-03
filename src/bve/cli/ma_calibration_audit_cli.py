"""CLI entry point: bve-ma-audit — no-lookahead audit for calibration cases.

Checks every case in ``historical_calibration_cases.yaml`` for lookahead
violations and exits with code 1 if any are found.

Usage::

    bve-ma-audit
    bve-ma-audit --cases research/mna/historical_calibration_cases.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_cases_path() -> Path:
    return _repo_root() / "research" / "mna" / "historical_calibration_cases.yaml"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="No-lookahead audit for historical M&A calibration cases"
    )
    parser.add_argument(
        "--cases",
        default=None,
        help=(
            "Path to historical_calibration_cases.yaml "
            "(default: research/mna/historical_calibration_cases.yaml)"
        ),
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    cases_path = Path(args.cases) if args.cases else _default_cases_path()

    if not cases_path.exists():
        print(
            f"ERROR: calibration cases file not found at {cases_path}.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from bve.intelligence.ma_calibration_audit import (
            print_audit_report,
            run_no_lookahead_audit,
        )
    except ImportError as exc:
        print(f"ERROR: import failed — {exc}", file=sys.stderr)
        sys.exit(1)

    result = run_no_lookahead_audit(cases_path)
    print_audit_report(result)

    sys.exit(1 if result.has_violations else 0)


if __name__ == "__main__":
    main()
