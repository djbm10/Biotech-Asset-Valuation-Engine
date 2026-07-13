"""CLI for coverage-measured buyer-specific S&E discovery."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from bve.se.discovery.adapters import (
    ClinicalTrialsGovAdapter,
    IndexedDocumentAdapter,
    PubMedDiscoveryAdapter,
    UnavailableSourceAdapter,
    UrlDocumentAdapter,
)
from bve.se.pipeline import run_landscape_search
from bve.se.reporting.memo import render_search_memo
from bve.se.schemas.contracts import BuyerProblemV2, RunStatus

_MANDATORY_SOURCES = (
    "clinicaltrials_gov",
    "company_pipeline_or_presentation",
    "company_press_release",
    "sec_edgar",
    "conference_ash",
    "conference_asco",
    "conference_aacr",
    "conference_eha",
)


def _code_version() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bve-se-search",
        description="Discover a coverage-measured public landscape for one BuyerProblem v2.",
    )
    parser.add_argument("--problem", required=True, help="BuyerProblem v2 YAML")
    parser.add_argument("--output", help="Write JSON result to this path")
    parser.add_argument("--format", choices=("json", "memo"), default="json")
    parser.add_argument(
        "--snapshot-dir",
        default="outputs/se/snapshots/clinicaltrials_gov",
        help="Content-addressed ClinicalTrials.gov snapshot directory",
    )
    parser.add_argument(
        "--pubmed-snapshot-dir",
        default="outputs/se/snapshots/pubmed",
        help="Content-addressed PubMed snapshot directory",
    )
    parser.add_argument(
        "--source-index",
        help=(
            "Optional YAML mapping source family names to public document records; this is a "
            "document index, not an asset universe"
        ),
    )
    parser.add_argument(
        "--url-index",
        help=(
            "Optional YAML mapping source family names to declared public URLs; fetched pages are "
            "snapshotted and filtered by the query compiler"
        ),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Replay local CT.gov snapshots instead of making CT.gov/PubMed network requests",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Research-only: return zero even when mandatory-source/convergence checks fail.",
    )
    return parser


def _load_json_snapshots(directory: Path) -> list[dict]:
    records: list[dict] = []
    if not directory.exists():
        return records
    for path in sorted(directory.glob("*.json")):
        try:
            records.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return records


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problem = BuyerProblemV2.model_validate(yaml.safe_load(Path(args.problem).read_text()))
    source_index = (yaml.safe_load(Path(args.source_index).read_text()) or {}) if args.source_index else {}
    url_index = (yaml.safe_load(Path(args.url_index).read_text()) or {}) if args.url_index else {}
    if args.offline:
        ct_records = _load_json_snapshots(Path(args.snapshot_dir))

        def ct_search(**_kwargs):
            return ct_records

        ct_adapter = ClinicalTrialsGovAdapter(
            search_fn=ct_search, snapshot_root=Path(args.snapshot_dir)
        )
        pubmed_records = _load_json_snapshots(Path(args.pubmed_snapshot_dir))

        def pubmed_search(_query, _limit):
            return pubmed_records

        pubmed_adapter = PubMedDiscoveryAdapter(
            search_fn=pubmed_search, snapshot_root=Path(args.pubmed_snapshot_dir)
        )
    else:
        ct_adapter = ClinicalTrialsGovAdapter(snapshot_root=Path(args.snapshot_dir))
        pubmed_adapter = PubMedDiscoveryAdapter(snapshot_root=Path(args.pubmed_snapshot_dir))
    indexed_adapters = [
        IndexedDocumentAdapter(
            source_name,
            source_index[source_name],
            snapshot_root=Path(args.snapshot_dir).parent / source_name,
        )
        for source_name in _MANDATORY_SOURCES
        if source_name in source_index and source_name != "clinicaltrials_gov"
    ]
    url_adapters = [
        UrlDocumentAdapter(
            source_name,
            urls,
            snapshot_root=Path(args.snapshot_dir).parent / source_name,
        )
        for source_name, urls in url_index.items()
        if source_name in _MANDATORY_SOURCES
        and source_name not in {adapter.source_name for adapter in indexed_adapters}
        and source_name != "clinicaltrials_gov"
    ]
    configured_indexed_names = {
        "clinicaltrials_gov",
        *{source_name for source_name in source_index if source_name in _MANDATORY_SOURCES},
        *{source_name for source_name in url_index if source_name in _MANDATORY_SOURCES},
    }
    unavailable_adapters = [
        UnavailableSourceAdapter(source_name)
        for source_name in _MANDATORY_SOURCES
        if source_name not in configured_indexed_names
    ]
    result = run_landscape_search(
        problem,
        [
            ct_adapter,
            pubmed_adapter,
            *indexed_adapters,
            *url_adapters,
            *unavailable_adapters,
        ],
        run_id=f"se:{uuid.uuid4()}",
        code_version=_code_version(),
        normalization_version="cd19_bcma_v1+t_cell_engager_v1",
        declared_mandatory_sources=_MANDATORY_SOURCES,
    )
    rendered = (
        json.dumps(result.model_dump(mode="json"), indent=2)
        if args.format == "json"
        else render_search_memo(result)
    )
    if args.output:
        Path(args.output).write_text(rendered + "\n")
    else:
        sys.stdout.write(rendered + "\n")
    if result.run_manifest.status != RunStatus.CONVERGED and not args.allow_incomplete:
        print(
            "ERROR: S&E discovery is INCOMPLETE; output is diagnostic and was not promoted.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
