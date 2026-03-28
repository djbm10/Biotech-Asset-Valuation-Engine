"""CLI entry point: bve-acquirer-fit."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from bve.intelligence.acquirer_fit import (
    AcquirerFitEngine,
    AcquirerFitIntegrationConfig,
    AcquirerFitResult,
)
from bve.intelligence.acquisition_memo import AcquisitionMemoGenerator
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.pipeline.watchlist_runner import load_watchlist_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank watchlist assets by fit versus a named acquirer and optionally write memos"
    )
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument("--acquirer", required=True, help="Acquirer ID in pipeline_gaps.yaml")
    parser.add_argument(
        "--db",
        default=None,
        help="Override KnowledgeStore SQLite path (defaults to watchlist knowledge_db_path)",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Score as of YYYY-MM-DD (default: today)",
    )
    parser.add_argument("--top", type=int, default=25, help="Number of ranked rows to show")
    parser.add_argument(
        "--profiles-file",
        default="research/mna/pipeline_gaps.yaml",
        help="Acquirer profile YAML path",
    )
    parser.add_argument(
        "--comps-file",
        default="research/mna/comparable_deals.yaml",
        help="Comparable deal YAML path",
    )
    parser.add_argument(
        "--readiness-filter",
        choices=["strict", "off"],
        default="strict",
        help="Apply the Phase 2 POC-or-later acquisition-readiness gate",
    )
    parser.add_argument(
        "--output-format",
        choices=["report", "json"],
        default="report",
        help="Output format",
    )
    parser.add_argument("--output", default=None, help="Write output to file instead of stdout")
    parser.add_argument(
        "--write-memos",
        action="store_true",
        help="Write one acquisition memo per ranked target to markdown files",
    )
    parser.add_argument(
        "--memo-dir",
        default=None,
        help="Directory for markdown memos (defaults under outputs/acquirer_fit_memos/)",
    )
    parser.add_argument(
        "--persist-memos",
        action="store_true",
        help="Persist generated acquisition memos into the knowledge store",
    )
    return parser


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid --as-of value: {raw!r}; expected YYYY-MM-DD") from exc


def _resolve_watchlist_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.exists():
        return path

    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "examples" / "configs" / "watchlists" / raw_path,
        repo_root / "examples" / "configs" / "watchlists" / Path(raw_path).name,
        repo_root / "examples" / "configs" / raw_path,
        repo_root / "examples" / "configs" / Path(raw_path).name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return path


def _fmt_millions(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.1f}M"


def _fmt_ratio(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}x"


def _fmt_text(value: Optional[str], *, fallback: str = "n/a") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _fmt_status(row) -> str:
    if row.passes_hard_filters:
        return "pass"
    if row.hard_fail_reasons:
        return ",".join(row.hard_fail_reasons)
    return "fail"


def _format_report(result: AcquirerFitResult) -> str:
    if not result.rows:
        return (
            f"No acquirer-fit rows found for {result.acquirer_id} "
            f"on {result.as_of_date.isoformat()}."
        )

    widths = [4, 18, 8, 7, 20, 20, 9, 10, 8, 12, 24]
    header = (
        f"{'Rank':<{widths[0]}}  "
        f"{'Asset':<{widths[1]}}  "
        f"{'Ticker':<{widths[2]}}  "
        f"{'Score':>{widths[3]}}  "
        f"{'Gap':<{widths[4]}}  "
        f"{'Modality':<{widths[5]}}  "
        f"{'Stage':<{widths[6]}}  "
        f"{'EV':>{widths[7]}}  "
        f"{'Disc':>{widths[8]}}  "
        f"{'Headroom':>{widths[9]}}  "
        f"{'Status':<{widths[10]}}"
    )
    separator = "-" * len(header)
    lines = [
        f"Acquirer fit screen date: {result.as_of_date.isoformat()}",
        f"Acquirer: {result.acquirer_id} | "
        f"Score version: {result.score_version} | "
        f"Assets: {result.n_assets} | "
        f"Ranked: {result.n_ranked} | "
        f"With comps: {result.n_with_comps} | "
        f"Passing hard filters: {result.n_passing_hard_filters}",
        separator,
        header,
        separator,
    ]
    for row in result.rows:
        lines.append(
            f"{row.rank:<{widths[0]}}  "
            f"{row.asset_id:<{widths[1]}}  "
            f"{_fmt_text(row.ticker):<{widths[2]}}  "
            f"{row.fit_score:>{widths[3]}.3f}  "
            f"{_fmt_text(row.matched_therapeutic_gap):<{widths[4]}}  "
            f"{_fmt_text(row.matched_modality):<{widths[5]}}  "
            f"{_fmt_text(row.stage):<{widths[6]}}  "
            f"{_fmt_millions(row.enterprise_value_millions):>{widths[7]}}  "
            f"{_fmt_ratio(row.acquisition_discount):>{widths[8]}}  "
            f"{_fmt_millions(row.budget_headroom_millions):>{widths[9]}}  "
            f"{_fmt_status(row):<{widths[10]}}"
        )
        priorities = ", ".join(row.matched_priorities) if row.matched_priorities else "none"
        lines.append(
            "      "
            f"priorities={priorities}  "
            f"valuation={row.valuation_source}  "
            f"comps={row.comparable_n}  "
            f"explanation={row.explanation}"
        )
    return "\n".join(lines)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return slug.strip("_") or "memo"


def _default_memo_dir(*, acquirer_id: str, as_of_date: date) -> Path:
    return Path("outputs") / "acquirer_fit_memos" / _slugify(acquirer_id) / as_of_date.isoformat()


def _write_memos(memos: list[object], *, memo_dir: Path) -> list[Path]:
    memo_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for idx, memo in enumerate(memos, start=1):
        asset_id = _slugify(str(getattr(memo, "asset_id", f"asset_{idx}")))
        acquirer_id = _slugify(str(getattr(memo, "acquirer_id", "acquirer")))
        out_path = memo_dir / f"{idx:02d}_{asset_id}_{acquirer_id}.md"
        out_path.write_text(str(getattr(memo, "rendered_markdown", "")), encoding="utf-8")
        written_paths.append(out_path)
    return written_paths


def main() -> None:
    args = _build_parser().parse_args()
    watchlist_path = _resolve_watchlist_path(args.watchlist)
    config = load_watchlist_config(watchlist_path)

    as_of: Optional[date] = None
    if args.as_of:
        try:
            as_of = _parse_date(args.as_of)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1)

    db_path = args.db or config.knowledge_db_path
    integration_config = AcquirerFitIntegrationConfig(
        acquirer_profiles_path=args.profiles_file,
        comparable_deals_path=args.comps_file,
        top_n=args.top,
        require_acquisition_readiness=(args.readiness_filter == "strict"),
    )
    should_generate_memos = args.write_memos or args.persist_memos or args.memo_dir is not None

    knowledge = KnowledgeStore(db_path)
    try:
        fit_engine = AcquirerFitEngine(
            knowledge_store=knowledge,
            integration_config=integration_config,
        )
        result = fit_engine.screen_from_watchlist_config(
            config,
            acquirer_id=args.acquirer,
            snapshot_date=as_of,
            top_n=args.top,
        )
        if should_generate_memos:
            memo_generator = AcquisitionMemoGenerator(
                fit_engine=fit_engine,
                knowledge_store=knowledge,
            )
            memos = memo_generator.generate_from_fit_result(
                list(config.watchlist),
                fit_result=result,
                persist=args.persist_memos,
            )
            if args.write_memos or args.memo_dir is not None:
                memo_dir = (
                    Path(args.memo_dir)
                    if args.memo_dir is not None
                    else _default_memo_dir(acquirer_id=result.acquirer_id, as_of_date=result.as_of_date)
                )
                written_paths = _write_memos(memos, memo_dir=memo_dir)
                print(
                    f"Acquisition memos written: {len(written_paths)} -> {memo_dir}",
                    file=sys.stderr,
                )
            elif args.persist_memos:
                print(
                    f"Acquisition memos persisted: {len(memos)}",
                    file=sys.stderr,
                )

        output = (
            json.dumps(result.model_dump(mode="json"), indent=2)
            if args.output_format == "json"
            else _format_report(result)
        )
        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output, encoding="utf-8")
            print(f"Acquirer fit report written to {out_path}", file=sys.stderr)
            return
        print(output)
    finally:
        knowledge.close()


if __name__ == "__main__":
    main()
