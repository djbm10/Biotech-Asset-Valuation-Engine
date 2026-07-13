"""bve-config-quality CLI: corpus-wide config provenance + completeness dashboard.

Scans the static valuation config corpus and ranks configs worst-first by how
much of each valuation rests on coerced defaults vs. sourced evidence. Use it to
decide which configs deserve analyst curation before spending compute on
backtests.

Usage
-----
    bve-config-quality
    bve-config-quality --root examples/configs/auto_generated
    bve-config-quality --output outputs/config_quality.md
    bve-config-quality --json
    bve-config-quality --score-version v1.0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bve.ops.config_quality import (
    CURRENT_QUALITY_VERSION,
    QUALITY_SCORE_VERSIONS,
    scan_corpus,
    to_json,
    to_markdown,
)

_DEFAULT_ROOTS = (
    "examples/configs/auto_generated",
    "examples/configs/replay_generated",
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bve-config-quality",
        description="Corpus-wide config provenance + completeness dashboard.",
    )
    p.add_argument(
        "--root",
        action="append",
        dest="roots",
        default=None,
        help="Config directory to scan (repeatable). Defaults to the "
        "auto_generated + replay_generated corpora.",
    )
    p.add_argument(
        "--score-version",
        default=CURRENT_QUALITY_VERSION,
        choices=sorted(QUALITY_SCORE_VERSIONS),
        help="Completeness weight regime to use.",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Output file path. If omitted, prints to stdout.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of Markdown.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    roots = args.roots or list(_DEFAULT_ROOTS)

    records = scan_corpus(roots, score_version=args.score_version)
    if not records:
        print(f"No configs found under: {', '.join(roots)}", file=sys.stderr)
        return 1

    rendered = (
        json.dumps(to_json(records), indent=2)
        if args.json
        else to_markdown(records)
    )

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote {len(records)} config records → {out_path}", file=sys.stderr)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
