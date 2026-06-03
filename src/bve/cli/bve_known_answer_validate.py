"""bve-known-answer-validate CLI: run the known-answer validation suite.

Usage
-----
    bve-known-answer-validate
    bve-known-answer-validate --cases research/validation/my_cases.yaml
    bve-known-answer-validate --model-outputs outputs/ka_model_outputs.json
    bve-known-answer-validate --output outputs/known_answer_validation.md
    bve-known-answer-validate --json

Model outputs JSON format
--------------------------
A JSON object mapping case_id → output dict::

    {
      "prometheus_merck_2023": {
        "model_rnpv_millions": 9500,
        "model_deal_type": "acquisition",
        "model_top_buyers": ["Merck", "AbbVie"],
        "model_thesis_direction": "long"
      }
    }

When --model-outputs is omitted, the suite runs in definitions-only mode and
only the internal range sanity check (deal_directional) is evaluated.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-known-answer-validate",
        description="Run the BVE known-answer validation suite.",
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="Path to YAML file with case definitions. "
             "Defaults to bundled cases.yaml.",
    )
    parser.add_argument(
        "--model-outputs",
        default=None,
        dest="model_outputs",
        help="Path to JSON file with model outputs keyed by case_id.",
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
    parser.add_argument(
        "--case-id",
        default=None,
        dest="case_id",
        help="Run only a specific case by case_id.",
    )
    args = parser.parse_args(argv)

    print("[bve-known-answer-validate] Loading cases...", file=sys.stderr)

    from bve.validation.known_answer_cases import load_cases
    from bve.validation.known_answer_validator import run_suite, render_known_answer_suite

    cases = load_cases(args.cases)
    if not cases:
        print("[bve-known-answer-validate] No cases loaded. Exiting.", file=sys.stderr)
        return 1

    if args.case_id:
        cases = [c for c in cases if c.case_id == args.case_id]
        if not cases:
            print(f"[bve-known-answer-validate] Case '{args.case_id}' not found.", file=sys.stderr)
            return 1

    model_outputs: dict | None = None
    if args.model_outputs:
        try:
            model_outputs = json.loads(Path(args.model_outputs).read_text())
            print(
                f"[bve-known-answer-validate] Loaded model outputs for "
                f"{len(model_outputs)} case(s).",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"[bve-known-answer-validate] Warning: could not load model outputs: {exc}",
                file=sys.stderr,
            )

    print(
        f"[bve-known-answer-validate] Running suite against {len(cases)} case(s)...",
        file=sys.stderr,
    )

    result = run_suite(cases, model_outputs=model_outputs)

    if result.n_fail > 0:
        print(
            f"[bve-known-answer-validate] {result.n_fail} case(s) failed.",
            file=sys.stderr,
        )
    elif result.n_pass > 0:
        print(
            f"[bve-known-answer-validate] All {result.n_pass} evaluated case(s) passed.",
            file=sys.stderr,
        )
    else:
        print(
            "[bve-known-answer-validate] Running in definitions-only mode "
            "(no model outputs provided).",
            file=sys.stderr,
        )

    if args.as_json:
        rendered = json.dumps(result.to_dict(), indent=2, default=str)
    else:
        rendered = render_known_answer_suite(result)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(
            f"[bve-known-answer-validate] Output written to {out_path}",
            file=sys.stderr,
        )
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
