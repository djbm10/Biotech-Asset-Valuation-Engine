"""
bve-reproduce-run — compare two run_context.json files to assess reproducibility.

Usage::

    # Compare the most recent run against an earlier reference run
    bve-reproduce-run \\
      --reference outputs/daily/2026-05-30/run_context.json \\
      --current   outputs/daily/2026-06-02/run_context.json

    # Exit 1 if any key dimension changed (CI gate)
    bve-reproduce-run --reference ... --current ... --strict
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-reproduce-run",
        description="Compare two run_context.json files to assess reproducibility.",
    )
    parser.add_argument("--reference", required=True, help="Reference run_context.json")
    parser.add_argument("--current", required=True, help="Current run_context.json")
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit 1 if any dimension differs.",
    )
    args = parser.parse_args(argv)

    ref_path = Path(args.reference)
    cur_path = Path(args.current)

    if not ref_path.exists():
        print(f"bve-reproduce-run: reference file not found: {ref_path}")
        return 1
    if not cur_path.exists():
        print(f"bve-reproduce-run: current file not found: {cur_path}")
        return 1

    from bve.run.run_context import RunContext, compare_contexts

    ref = RunContext.load(ref_path)
    cur = RunContext.load(cur_path)
    diff = compare_contexts(ref, cur)

    sep = "─" * 52
    print("\nRun reproducibility comparison")
    print(sep)
    print(f"  reference: {ref_path}")
    print(f"  current:   {cur_path}")
    print()

    if diff["changed"]:
        print("  Changed dimensions")
        for d in diff["changed"]:
            print(f"    CHANGED  {d}")
    else:
        print("  All dimensions identical — run is reproducible.")

    if diff["same"]:
        print("\n  Unchanged dimensions")
        for d in diff["same"][:10]:
            print(f"    ok       {d}")
        if len(diff["same"]) > 10:
            print(f"    … +{len(diff['same']) - 10} more")

    print()
    if diff["changed"]:
        print(f"  STATUS: {len(diff['changed'])} dimension(s) changed")
        if args.strict:
            return 1
    else:
        print("  STATUS: REPRODUCIBLE")

    return 0
