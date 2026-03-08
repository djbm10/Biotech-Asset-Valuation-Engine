"""
CLI: run commercial calibration for a historical case study.

Usage
-----
    bve-calibrate case_studies/ivacaftor_vertex/IVAC
    python -m bve.cli.calibrate case_studies/ruxolitinib_incyte/RUXO
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-calibrate",
        description="Compare engine predictions against historical asset revenue.",
    )
    parser.add_argument(
        "case_dir",
        help="Path to case directory containing inputs.yaml and actual_revenue.yaml",
    )
    args = parser.parse_args(argv)

    case_dir = Path(args.case_dir)
    if not case_dir.is_dir():
        print(f"ERROR: Not a directory: {case_dir}", file=sys.stderr)
        return 1

    from bve.analysis.commercial_calibration import run_calibration, print_calibration_report

    try:
        report = run_calibration(case_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR running calibration: {e}", file=sys.stderr)
        raise

    print(print_calibration_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
