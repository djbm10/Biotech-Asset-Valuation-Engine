"""CLI for coverage-measured buyer-specific S&E discovery."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from contextlib import nullcontext
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from bve.se.discovery.custody import CustodyError
from bve.se.discovery.replay import (
    ReplayTrialsGovAdapter,
    SealedCorpusReplay,
    block_network,
    replay_pubmed_adapter,
)
from bve.se.discovery.adapters import (
    ClinicalTrialsGovAdapter,
    IndexedDocumentAdapter,
    PubMedDiscoveryAdapter,
    UnavailableSourceAdapter,
    UrlDocumentAdapter,
)
from bve.se.discovery.query import AmbiguousTargetError
from bve.se.pipeline import run_acquisition, run_landscape_search
from bve.se.reporting.memo import render_search_memo
from bve.se.schemas.contracts import BuyerProblemV2, RunStatus
from bve.se.telemetry import StageTelemetry, stderr_emitter
from bve.se.universe.factory import TrialBackendNotConfigured, build_trial_provider

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
        "--trial-backend",
        choices=("rest", "aact", "hybrid"),
        default="rest",
        help=(
            "Trial universe backend. 'rest' is the CT.gov REST v2 API and needs no local "
            "infrastructure; 'aact' and 'hybrid' require a configured AACT mirror and fail "
            "rather than falling back to the API"
        ),
    )
    parser.add_argument(
        "--max-trial-records",
        type=int,
        default=None,
        help=(
            "Stop after this many trials. Omitted, the sweep is exhaustive. A bounded "
            "run is stamped truncated and evaluation refuses to score its recall."
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
        help=(
            "Research-only: return zero when convergence or an unconfigured mandatory "
            "source is the only complaint. Cannot waive a source that failed acquisition."
        ),
    )
    parser.add_argument(
        "--acquisition-ledger",
        help=(
            "Write one JSON line per issued query (source, query, attempts, pages, "
            "records, outcome, error) so a short corpus can be traced to the query that "
            "produced it without re-reading the whole result."
        ),
    )
    parser.add_argument(
        "--run-id",
        help=(
            "Immutable identity for this run. Defaults to a fresh uuid; pass one to tie a "
            "sealed acquisition and its replay to the same declared run."
        ),
    )
    parser.add_argument(
        "--custody-root",
        help=(
            "Seal the acquisition into this directory between discovery and identity: "
            "query attempts, query->record mapping, ledger, source health, corpus "
            "manifest and a validated seal. Downstream stages do not run unless it "
            "validates. The directory must not already exist or must be empty; a sealed "
            "acquisition is immutable."
        ),
    )
    parser.add_argument(
        "--acquire-only",
        action="store_true",
        help=(
            "Stop at the custody boundary: acquire, seal, validate, and exit. Requires "
            "--custody-root. Everything downstream then runs from the sealed bytes with "
            "--replay-corpus, so a crash in extraction or scoring is never a reason to "
            "touch a live source again."
        ),
    )
    parser.add_argument(
        "--custody-pins",
        help="JSON file of frozen-input pins to record in the sealed corpus manifest",
    )
    parser.add_argument(
        "--replay-corpus",
        help=(
            "Replay a sealed acquisition offline. Each semantic query is served the "
            "records that query actually received, from the sealed mapping -- not the "
            "union of the snapshot tree, which is what made the previous --offline path "
            "unable to reproduce a run. Network access is blocked for the whole run."
        ),
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help=(
            "Emit per-stage record counts and elapsed time to stderr, so a long run can "
            "be told apart from a hung one without attaching a profiler."
        ),
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
    parser = build_parser()
    args = parser.parse_args(argv)
    problem = BuyerProblemV2.model_validate(yaml.safe_load(Path(args.problem).read_text()))
    source_index = (yaml.safe_load(Path(args.source_index).read_text()) or {}) if args.source_index else {}
    url_index = (yaml.safe_load(Path(args.url_index).read_text()) or {}) if args.url_index else {}
    if args.replay_corpus and args.offline:
        parser.error(
            "--replay-corpus supersedes --offline; pass only the sealed corpus. The "
            "snapshot-union --offline path cannot reproduce a run's query membership."
        )
    if args.replay_corpus:
        replay = SealedCorpusReplay(Path(args.replay_corpus))
        ct_adapter = ReplayTrialsGovAdapter(replay, snapshot_root=Path(args.snapshot_dir))
        pubmed_adapter = replay_pubmed_adapter(
            replay, snapshot_root=Path(args.pubmed_snapshot_dir)
        )
    elif args.offline:
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
        try:
            provider = build_trial_provider(
                args.trial_backend, snapshot_root=Path(args.snapshot_dir)
            )
        except TrialBackendNotConfigured as exc:
            # An unavailable backend is a configuration error, not a reason to quietly
            # query a different universe than the one asked for.
            parser.error(str(exc))
        ct_adapter = ClinicalTrialsGovAdapter(
            provider=provider,
            max_records=args.max_trial_records,
            snapshot_root=Path(args.snapshot_dir),
        )
        pubmed_adapter = PubMedDiscoveryAdapter(snapshot_root=Path(args.pubmed_snapshot_dir))
    # Every family the index names, not only the mandatory ones. The mandatory tuple says
    # which sources a run is *required* to have reached -- it is the completeness contract,
    # not the admissions list. Filtering the index by it dropped any newly built family
    # (conference_aacr_bulk, company_press_release_sec_filed) with no error at all: the run
    # completed, the scores looked plausible, and the tranche under test had contributed
    # nothing. A silently absent source is the one failure this pipeline must never have.
    indexed_adapters = [
        IndexedDocumentAdapter(
            source_name,
            records,
            snapshot_root=Path(args.snapshot_dir).parent / source_name,
        )
        for source_name, records in source_index.items()
        if source_name != "clinicaltrials_gov"
    ]
    url_adapters = [
        UrlDocumentAdapter(
            source_name,
            urls,
            snapshot_root=Path(args.snapshot_dir).parent / source_name,
        )
        for source_name, urls in url_index.items()
        if source_name not in {adapter.source_name for adapter in indexed_adapters}
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
    if args.acquire_only and not args.custody_root:
        parser.error("--acquire-only requires --custody-root; there is nothing to stop at")
    pins = json.loads(Path(args.custody_pins).read_text()) if args.custody_pins else None
    # A replayed run is offline by construction; the guard makes a regression in that
    # construction fatal rather than silently live.
    network_guard = block_network() if args.replay_corpus else nullcontext()
    adapters = [
        ct_adapter,
        pubmed_adapter,
        *indexed_adapters,
        *url_adapters,
        *unavailable_adapters,
    ]
    run_id = args.run_id or f"se:{uuid.uuid4()}"
    telemetry = StageTelemetry(emit=stderr_emitter if args.progress else None)
    if args.acquire_only:
        try:
            with network_guard:
                discovery, seal = run_acquisition(
                    problem,
                    adapters,
                    run_id=run_id,
                    code_version=_code_version(),
                    normalization_version="cd19_bcma_v1+t_cell_engager_v1",
                    declared_mandatory_sources=_MANDATORY_SOURCES,
                    telemetry=telemetry,
                    custody_root=Path(args.custody_root),
                    custody_pins=pins,
                )
        except CustodyError as exc:
            print(f"ERROR: acquisition custody boundary failed: {exc}", file=sys.stderr)
            return 5
        summary = {
            "run_id": run_id,
            "custody_root": args.custody_root,
            "seal": seal.model_dump(mode="json") if seal is not None else None,
            "run_manifest": discovery.manifest.model_dump(mode="json"),
        }
        rendered = json.dumps(summary, indent=2)
        if args.output:
            Path(args.output).write_text(rendered + "\n")
        else:
            sys.stdout.write(rendered + "\n")
        # The same fail-closed rule as a full run: a failed mandatory source means an
        # unknown share of the universe is missing, and sealing it does not make it whole.
        if discovery.manifest.fatal_reasons:
            print(
                "ERROR: S&E acquisition FAILED; this corpus is UNSCOREABLE.",
                file=sys.stderr,
            )
            for reason in discovery.manifest.fatal_reasons:
                print(f"  - {reason}", file=sys.stderr)
            return 3
        if discovery.manifest.status != RunStatus.CONVERGED and not args.allow_incomplete:
            print("ERROR: S&E discovery is INCOMPLETE.", file=sys.stderr)
            return 2
        return 0

    try:
        with network_guard:
            result = run_landscape_search(
                problem,
                adapters,
                run_id=run_id,
                code_version=_code_version(),
                normalization_version="cd19_bcma_v1+t_cell_engager_v1",
                declared_mandatory_sources=_MANDATORY_SOURCES,
                telemetry=telemetry,
                custody_root=Path(args.custody_root) if args.custody_root else None,
                custody_pins=pins,
            )
    except CustodyError as exc:
        # The custody boundary did not validate, so nothing downstream ran. This is the
        # structural prohibition, reported as its own exit code so a harness cannot
        # mistake it for an ordinary incomplete run.
        print(f"ERROR: acquisition custody boundary failed: {exc}", file=sys.stderr)
        return 5
    except AmbiguousTargetError as exc:
        # A clarification request, not a crash. The ontology knows this string and knows
        # it is not enough; the useful answer is the list of things it could mean.
        print(f"NEEDS_CLARIFICATION: target {exc.query!r} is ambiguous.", file=sys.stderr)
        for candidate in exc.candidates:
            print(f"  - {candidate}", file=sys.stderr)
        print(
            "Re-run with one of these canonical ids as the declared target. An ambiguous "
            "target is never searched literally.",
            file=sys.stderr,
        )
        return 4
    rendered = (
        json.dumps(result.model_dump(mode="json"), indent=2)
        if args.format == "json"
        else render_search_memo(result)
    )
    if args.output:
        Path(args.output).write_text(rendered + "\n")
    else:
        sys.stdout.write(rendered + "\n")
    if args.acquisition_ledger:
        # Written before the gates below so a failed run still leaves the evidence that
        # explains why it failed.
        with Path(args.acquisition_ledger).open("w") as handle:
            for attempt in result.search_attempts:
                handle.write(
                    json.dumps(
                        {
                            "source": attempt.source,
                            "query": attempt.query,
                            "pass_number": attempt.pass_number,
                            "attempts_made": attempt.attempts_made,
                            "pages_fetched": attempt.pages_fetched,
                            "candidates_found": attempt.candidates_found,
                            "unique_candidates_added": attempt.unique_candidates_added,
                            "outcome": attempt.outcome.value,
                            "error": attempt.error,
                            "retrieval_date": attempt.retrieval_date.isoformat(),
                        }
                    )
                    + "\n"
                )

    # Checked before --allow-incomplete, which may waive a declared blind spot but not a
    # source that failed mid-acquisition: the corpus is then short an unknown number of
    # trials, and a recall figure measured on it is not a measurement. Run B5 scored
    # nothing for this reason -- it lost 86% of the CT.gov universe to one timed-out
    # query and still produced a plausible-looking partial run.
    if result.run_manifest.fatal_reasons:
        print(
            "ERROR: S&E acquisition FAILED; this run is UNSCOREABLE and was not promoted.",
            file=sys.stderr,
        )
        for reason in result.run_manifest.fatal_reasons:
            print(f"  - {reason}", file=sys.stderr)
        print(
            "  --allow-incomplete cannot waive a failed mandatory source.",
            file=sys.stderr,
        )
        return 3
    if result.run_manifest.status != RunStatus.CONVERGED and not args.allow_incomplete:
        print(
            "ERROR: S&E discovery is INCOMPLETE; output is diagnostic and was not promoted.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
