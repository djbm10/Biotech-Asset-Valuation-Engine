"""CLI for coverage-measured buyer-specific S&E discovery."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager, nullcontext
from datetime import date
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
from bve.se.intent.compiler import IntentNotCompilable, build_buyer_identity, compile_intent
from bve.se.intent.parser import parse_query
from bve.se.pipeline import run_acquisition, run_landscape_search
from bve.se.reporting.memo import render_search_memo
from bve.se.reporting.run_artifacts import RunDirectory, summary_payload, write_summary
from bve.se.reporting.shortlist import build_shortlist, render_shortlist
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
    entry = parser.add_mutually_exclusive_group(required=True)
    entry.add_argument("--problem", help="BuyerProblem v2 YAML")
    entry.add_argument(
        "--query",
        help=(
            "Ask in words instead: 'small molecule CHRM1 programs in phase 2'. Targets and "
            "modalities are resolved against the frozen ontology snapshot, so alias "
            "spellings are the snapshot's business rather than something to hand-type. How "
            "the question was read is printed per span; a question that does not resolve "
            "is refused with its blockers named, never completed with a plausible guess."
        ),
    )
    parser.add_argument(
        "--as-of",
        help="As-of date for a --query run (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--buyer-name",
        default="Ad-hoc query",
        help=(
            "Name recorded for a --query run. A typed question has no standing buyer "
            "profile, so the identity is synthesized and stamped 'nl_query' rather than "
            "being mistaken for a real buyer's capability profile."
        ),
    )
    parser.add_argument(
        "--therapeutic-area",
        action="append",
        default=None,
        help=(
            "Therapeutic area for a --query run, repeatable. Not inferred from the target: "
            "omitted, the compiled problem records UNSPECIFIED rather than guessing."
        ),
    )
    parser.add_argument(
        "--indication",
        action="append",
        default=None,
        help=(
            "Indication for a --query run, repeatable. Omitted, the question's unrecognized "
            "phrases are carried as free text, never promoted to resolved indications."
        ),
    )
    parser.add_argument(
        "--emit-problem",
        help=(
            "Write the problem a --query compiled to, as YAML. A typed question is an "
            "input like any other: this is what lets the same run be replayed from a file "
            "and explained after the fact."
        ),
    )
    parser.add_argument("--output", help="Write JSON result to this path")
    parser.add_argument(
        "--output-dir",
        help=(
            "Put the whole run in one directory: the compiled problem, the full result, "
            "both shortlist views, the run manifest, the acquisition ledger, the snapshots "
            "and sealed custody, the stderr log, and the exact command to reproduce it. "
            "Every path below is defaulted from it, so a question can be asked and audited "
            "without knowing which internal stage writes what. An explicit flag still wins."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("json", "memo", "shortlist", "shortlist-json"),
        default="json",
        help=(
            "'json' is the full run artifact and 'memo' the run audit. 'shortlist' is the "
            "reader's view -- the assets found, why each one is there, and the evidence "
            "behind each displayed claim -- and 'shortlist-json' is the same object, so "
            "the two can never describe different assets."
        ),
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help=(
            "How many assets the shortlist shows. The counts always describe the whole run, "
            "so a short shortlist is never mistakable for a small landscape."
        ),
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help=(
            "Expand every citation behind every displayed claim: url, structured field, "
            "content hash and evidence span. Off by default because the default view is "
            "meant to be read, not audited."
        ),
    )
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
        "--alias-probe-in",
        help=(
            "Restore the alias-admission decisions a previous run sealed, instead of "
            "probing. Required to replay a run faithfully: admission makes the search "
            "plan adaptive, so replaying a sealed corpus without the decisions that "
            "selected it falls back to the sole-claimant vocabulary and measures a "
            "different run. Restores measurements only -- a refused alias stays refused."
        ),
    )
    parser.add_argument(
        "--alias-probe-out",
        help=(
            "Probe every shared alias of every declared target before the run and write "
            "the decisions here. Without this, shared aliases stay out of the search: a "
            "string more than one gene claims is admitted only on measured evidence that "
            "this target dominates the others in the retrieved corpus."
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


def _probe_shared_aliases(problem: BuyerProblemV2, out_path: Path) -> None:
    """Decide, once per run, which shared aliases this run may search with.

    The registry is installed globally because the retrieval vocabulary is reached
    through call paths that carry no run context, and because the decision belongs to the
    run rather than to any one query -- re-deciding per query could make the plan
    disagree with itself.
    """

    from bve.se.discovery.alias_admission import install_registry, probe_and_admit
    from bve.se.discovery.alias_probe import ctgov_probe_fetcher

    as_of = str(problem.buyer.as_of_date)
    registry = probe_and_admit(
        [target.canonical_id for target in problem.strategic_gap.target_expression.targets],
        ctgov_probe_fetcher(as_of),
        as_of_date=as_of,
        source="clinicaltrials_gov",
        source_release=as_of,
    )
    install_registry(registry)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([vars(probe) for probe in registry.probes()], indent=2, default=str) + "\n"
    )


def problem_from_args(args: argparse.Namespace) -> BuyerProblemV2:
    """The problem this invocation is about, from a file or from a typed question.

    Both routes end at the same validated contract, which is the point: a question is a way
    of writing a problem down, not a second kind of input the rest of the engine has to know
    about. The compilation is deterministic, so the same question is the same problem.
    """

    if args.problem:
        args.interpretation = ()
        return BuyerProblemV2.model_validate(yaml.safe_load(Path(args.problem).read_text()))

    intent = parse_query(args.query)
    # Kept so the end-of-run summary can repeat how the question was read. The operator
    # saw it before the run; they should not have to scroll back past a long run to find it.
    args.interpretation = tuple(intent.explain())
    # Printed whether or not it compiles. An interpretation the operator cannot see is an
    # interpretation they cannot correct, and this is the layer where a wrong reading of
    # "M1" costs a whole run.
    print(f"query: {args.query!r}", file=sys.stderr)
    for line in intent.explain():
        print(f"  {line}", file=sys.stderr)

    for warning in intent.warnings:
        print(f"  warning: {warning}", file=sys.stderr)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    try:
        problem = compile_intent(
            intent,
            buyer=build_buyer_identity(args.buyer_name, as_of_date=as_of),
            therapeutic_areas=args.therapeutic_area,
            indications=args.indication,
        )
    except IntentNotCompilable as refused:
        # Refusing is the point. A question this engine cannot represent must not run as a
        # narrower question wearing the original's name.
        for blocker in refused.blockers:
            print(f"  blocked: {blocker}", file=sys.stderr)
        raise SystemExit(
            "the question was not compiled; answer the blockers above, name the target and "
            "modality explicitly, or pass --problem"
        ) from None
    if args.emit_problem:
        emitted = Path(args.emit_problem)
        emitted.parent.mkdir(parents=True, exist_ok=True)
        emitted.write_text(
            yaml.safe_dump(problem.model_dump(mode="json"), sort_keys=False)
        )
        print(f"  compiled problem written to {emitted}", file=sys.stderr)
    return problem


#: Parser defaults that ``--output-dir`` may override. An explicitly passed path always wins;
#: these are the values that mean "the user did not choose", and comparing against them is how
#: the two flags compose instead of one silently discarding the other.
_SNAPSHOT_DEFAULT = "outputs/se/snapshots/clinicaltrials_gov"
_PUBMED_SNAPSHOT_DEFAULT = "outputs/se/snapshots/pubmed"


def _apply_output_dir(args: argparse.Namespace) -> RunDirectory | None:
    """Default every artifact path from one directory, leaving explicit flags alone."""

    if not args.output_dir:
        return None
    directory = RunDirectory(Path(args.output_dir))
    directory.prepare()
    args.emit_problem = args.emit_problem or str(directory.problem)
    args.acquisition_ledger = args.acquisition_ledger or str(directory.acquisition_ledger)
    args.custody_root = args.custody_root or str(directory.custody)
    if args.snapshot_dir == _SNAPSHOT_DEFAULT:
        args.snapshot_dir = str(directory.snapshots / "clinicaltrials_gov")
    if args.pubmed_snapshot_dir == _PUBMED_SNAPSHOT_DEFAULT:
        args.pubmed_snapshot_dir = str(directory.snapshots / "pubmed")
    return directory


class _TeedStderr:
    """Everything the run says, on the terminal and in the run's own log.

    The stage progress, the query interpretation, the blockers and the fail-closed
    complaints are all written to stderr, and a run whose only record of why it stopped
    scrolled past in a terminal is a run nobody can diagnose later.
    """

    def __init__(self, stream, handle) -> None:
        self._stream = stream
        self._handle = handle

    def write(self, text: str) -> int:
        self._handle.write(text)
        return self._stream.write(text)

    def flush(self) -> None:
        self._handle.flush()
        self._stream.flush()

    def isatty(self) -> bool:
        return getattr(self._stream, "isatty", lambda: False)()


@contextmanager
def _log_to(directory: RunDirectory | None):
    if directory is None:
        yield
        return
    with directory.log.open("a") as handle:
        original = sys.stderr
        sys.stderr = _TeedStderr(original, handle)
        try:
            yield
        finally:
            sys.stderr = original


def _write_run_artifacts(result, args: argparse.Namespace, directory: RunDirectory) -> None:
    """Write every view of the run, whatever ``--format`` asked for on stdout.

    A directory that held only the format the operator happened to want would send them
    back to the sources to answer the next question; the run already has all of it in hand.
    """

    directory.result.write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n")
    directory.run_manifest.write_text(
        json.dumps(result.run_manifest.model_dump(mode="json"), indent=2) + "\n"
    )
    shortlist = build_shortlist(result, limit=args.top)
    directory.shortlist_json.write_text(
        json.dumps(shortlist.model_dump(mode="json"), indent=2) + "\n"
    )
    directory.shortlist_text.write_text(render_shortlist(shortlist, detail=args.detail) + "\n")
    directory.memo.write_text(render_search_memo(result) + "\n")


def _render_result(result, args: argparse.Namespace) -> str:
    """One run, in whichever of the four views was asked for.

    The two shortlist views are built from the same ``Shortlist`` object on purpose: a
    human-readable summary and a machine-readable payload that disagreed about which assets
    were on the list would be worse than having only one of them.
    """

    if args.format == "json":
        return json.dumps(result.model_dump(mode="json"), indent=2)
    if args.format == "memo":
        return render_search_memo(result)
    shortlist = build_shortlist(result, limit=args.top)
    if args.format == "shortlist-json":
        return json.dumps(shortlist.model_dump(mode="json"), indent=2)
    return render_shortlist(shortlist, detail=args.detail)


def _run(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    directory: RunDirectory | None,
    telemetry: StageTelemetry,
) -> tuple[int, object | None]:
    """The run itself. Returns its exit code and, if it got that far, its result."""

    problem = problem_from_args(args)
    args.problem_id = problem.problem_id
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
    if args.alias_probe_in and args.alias_probe_out:
        parser.error(
            "--alias-probe-in and --alias-probe-out are exclusive: a run either measures "
            "admission or replays a measurement, and doing both would let a fresh probe "
            "overwrite the decisions the replay is supposed to reproduce"
        )
    if args.alias_probe_in:
        from bve.se.discovery.alias_admission import install_registry, load_probe_registry

        install_registry(load_probe_registry(Path(args.alias_probe_in)))
    if args.alias_probe_out:
        if args.replay_corpus or args.offline:
            parser.error(
                "--alias-probe-out needs live retrieval; an offline or replayed run "
                "keeps the fail-closed sole-claimant vocabulary"
            )
        _probe_shared_aliases(problem, Path(args.alias_probe_out))
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
            return 5, None
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
            return 3, None
        if discovery.manifest.status != RunStatus.CONVERGED and not args.allow_incomplete:
            print("ERROR: S&E discovery is INCOMPLETE.", file=sys.stderr)
            return 2, None
        return 0, None

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
        return 5, None
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
        return 4, None
    if directory is not None:
        # Before the fail-closed gates below, for the same reason the ledger is: a run that
        # ends UNSCOREABLE is exactly the run whose artifacts someone needs to read.
        _write_run_artifacts(result, args, directory)
    rendered = _render_result(result, args)
    if args.output:
        Path(args.output).write_text(rendered + "\n")
    elif directory is None:
        sys.stdout.write(rendered + "\n")
    # With a run directory and no explicit --output, stdout belongs to the end-of-run
    # summary: every view is already in the directory, and dumping one of them over the
    # summary is how the one-command workflow would become unreadable again.
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
        return 3, result
    if result.run_manifest.status != RunStatus.CONVERGED and not args.allow_incomplete:
        print(
            "ERROR: S&E discovery is INCOMPLETE; output is diagnostic and was not promoted.",
            file=sys.stderr,
        )
        return 2, result
    return 0, result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)
    directory = _apply_output_dir(args)
    if directory is not None:
        # Written first: if the run dies in acquisition, the one thing that must survive is
        # how to run it again.
        directory.write_command(argv)
    telemetry = StageTelemetry(emit=stderr_emitter if args.progress else None)
    started = time.monotonic()
    with _log_to(directory):
        code, result = _run(args, parser, directory, telemetry)
    if directory is None:
        return code
    shortlist = (
        build_shortlist(result, limit=args.top)
        if result is not None and not args.acquire_only
        else None
    )
    manifest = getattr(result, "run_manifest", None)
    payload = summary_payload(
        run_id=args.run_id or (manifest.run_id if manifest is not None else "unstarted"),
        query=args.query,
        problem_id=getattr(args, "problem_id", ""),
        interpretation=getattr(args, "interpretation", ()),
        run_status=manifest.status.value if manifest is not None else "NOT_COMPLETED",
        incomplete_reasons=manifest.incomplete_reasons if manifest is not None else (),
        fatal_reasons=manifest.fatal_reasons if manifest is not None else (),
        shortlist=shortlist,
        elapsed_seconds=time.monotonic() - started,
        stages=[(stage.name, stage.seconds) for stage in telemetry.stages],
        directory=directory,
        exit_code=code,
    )
    sys.stdout.write(write_summary(directory, payload) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
