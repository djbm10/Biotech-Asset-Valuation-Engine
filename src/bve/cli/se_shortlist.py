"""CLI entry point: bve-shortlist — Search & Evaluation shortlist for one buyer problem.

Loads a buyer-problem YAML and an assets YAML, ranks the eligible set, and lists
gate-failers with the gate they tripped. This is Chris's S&E deliverable: a
ranked, gated shortlist for a single buyer problem.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from bve.intelligence.science_thesis import BuyerProblem
from bve.intelligence.se_shortlist import ShortlistAssetInput, build_se_shortlist


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank a universe of assets against one buyer problem (Search & Evaluation mode).",
    )
    parser.add_argument("--problem", required=True, help="Path to buyer-problem YAML")
    parser.add_argument("--assets", required=True, help="Path to assets YAML (list of asset specs)")
    parser.add_argument("--limit", type=int, default=None, help="Truncate the ranked list to N")
    parser.add_argument("--format", choices=["table", "json", "memo"], default="table")
    parser.add_argument("--output", default=None, help="Write output to a file instead of stdout")
    return parser


def _load_problem(path: str) -> BuyerProblem:
    data = yaml.safe_load(Path(path).expanduser().read_text())
    return BuyerProblem(**data)


def _load_assets(path: str) -> list[ShortlistAssetInput]:
    data = yaml.safe_load(Path(path).expanduser().read_text())
    if isinstance(data, dict) and "assets" in data:
        data = data["assets"]
    return [ShortlistAssetInput(**row) for row in data]


def _render_table(shortlist) -> str:
    lines = [f"Ranked ({len(shortlist.ranked)} passed hard gates)"]
    for i, entry in enumerate(shortlist.ranked, 1):
        killer = entry.decisive_killer_question or "—"
        flag = " (pre-diligence)" if entry.pre_diligence else ""
        lines.append(
            f"{i:>2}. {entry.asset_name or entry.asset_id}  "
            f"{entry.bd_actionability:.2f}  {entry.recommended_bd_route.value}  "
            f"{entry.evidence_grade.value}{flag}  | {killer}"
        )
    lines.append("")
    lines.append(f"Excluded ({len(shortlist.excluded)} failed a hard gate — never scored)")
    for excluded in shortlist.excluded:
        gates = ", ".join(excluded.failed_gates) or "—"
        lines.append(f"  - {excluded.asset_name or excluded.asset_id}: {gates}")
    return "\n".join(lines)


def _render_memo(shortlist, problem) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    template_dir = Path(__file__).resolve().parents[1] / "reporting" / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template("se_shortlist.md.j2").render(shortlist=shortlist, problem=problem)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    problem = _load_problem(args.problem)
    assets = _load_assets(args.assets)
    shortlist = build_se_shortlist(problem, assets, limit=args.limit)

    if args.format == "json":
        rendered = json.dumps(shortlist.model_dump(mode="json"), indent=2)
    elif args.format == "memo":
        rendered = _render_memo(shortlist, problem)
    else:
        rendered = _render_table(shortlist)

    if args.output:
        Path(args.output).expanduser().write_text(rendered)
    else:
        sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
