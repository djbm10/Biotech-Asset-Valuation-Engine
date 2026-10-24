"""bve-se-pilot: export -> seal -> score for the blinded S&E pilot.

export and seal never take a reference path, so they cannot read labels.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from bve.se.evaluation.blinded_pilot import (
    SealReceipt,
    export_candidates,
    preregister,
    score,
    seal,
)
from bve.se.pipeline import SESearchResult


def _repo_root() -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bve-se-pilot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="engine result.json -> sealed candidate format")
    ex.add_argument("--result", type=Path, required=True)
    ex.add_argument("--spec-id", required=True)
    ex.add_argument("--engine-commit", required=True)
    ex.add_argument("--out", type=Path, required=True)
    pr = sub.add_parser("prereg", help="hash spec + criteria BEFORE the engine runs")
    for flag in ("--spec", "--criteria", "--out"):
        pr.add_argument(flag, type=Path, required=True)
    se = sub.add_parser("seal", help="hash spec + criteria + candidates (no reference)")
    for flag in ("--spec", "--criteria", "--candidates", "--prereg", "--out"):
        se.add_argument(flag, type=Path, required=True)
    sc = sub.add_parser("score", help="verify receipt, then open the reference and score")
    for flag in ("--receipt", "--spec", "--criteria", "--candidates", "--reference", "--out"):
        sc.add_argument(flag, type=Path, required=True)
    sc.add_argument(
        "--allow-reference-in-repo", action="store_true", help="synthetic self-tests only"
    )
    args = parser.parse_args(argv)
    try:
        if args.cmd == "export":
            result = SESearchResult.model_validate_json(args.result.read_text())
            export = export_candidates(
                result, spec_id=args.spec_id, engine_commit=args.engine_commit
            )
            args.out.write_text(export.model_dump_json(indent=2))
        elif args.cmd == "prereg":
            args.out.write_text(preregister(args.spec, args.criteria).model_dump_json(indent=2))
        elif args.cmd == "seal":
            root = _repo_root()
            if root is None:
                raise ValueError("seal must run inside the git repository holding the prereg")
            receipt = seal(
                args.spec, args.criteria, args.candidates, prereg_path=args.prereg, repo_root=root
            )
            args.out.write_text(receipt.model_dump_json(indent=2))
        else:
            receipt = SealReceipt.model_validate_json(args.receipt.read_text())
            report = score(
                receipt,
                spec_path=args.spec,
                criteria_path=args.criteria,
                candidates_path=args.candidates,
                reference_path=args.reference,
                repo_root=None if args.allow_reference_in_repo else _repo_root(),
            )
            args.out.write_text(report.model_dump_json(indent=2))
            print(json.dumps({"status": report.status, "passes": report.passes_thresholds}))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"bve-se-pilot: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
