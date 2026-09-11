"""Acquisition custody and native offline replay.

The failure these tests exist for is specific. A live run retried a CT.gov query that had
already materialized protocols; only the final attempt's result was kept; the superseded
attempt's bytes stayed on disk belonging to nobody. The run then could not be replayed at
any boundary, because no record said which query had seen which record — and a replay
built from the union of the snapshot tree answered every query with every file, finding
3,385 hits where the run had found 3,321.

So the tests below check two things that are easy to conflate: that a retry leaves no
unexplained snapshot, and that replay *reproduces* membership rather than re-deriving it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from bve.se.discovery.custody import (
    CustodyError,
    unexplained_snapshots,
    validate_seal,
)
from bve.se.discovery.replay import (
    NetworkBlocked,
    ReplayDivergence,
    ReplayTrialsGovAdapter,
    SealedCorpusReplay,
    block_network,
)
from bve.se.discovery.adapters import ClinicalTrialsGovAdapter, UnavailableSourceAdapter
from bve.se.pipeline import run_landscape_search
from bve.se.schemas.contracts import BuyerProblemV2, RunStatus, SearchOutcome
from bve.se.universe.provider import (
    PayloadKind,
    TrialRecord,
    TrialSnapshot,
    TrialUniverseResult,
    payload_digest,
)

ROOT = Path(__file__).resolve().parents[2]
CODE_VERSION = "test-custody"
NORMALIZATION_VERSION = "test-normalization"


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        yaml.safe_load(
            (ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml").read_text()
        )
    )


def _protocol(nct_id: str, title: str) -> dict:
    return {
        "identificationModule": {"nctId": nct_id, "briefTitle": title},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Fixture Bio"}},
        "statusModule": {"overallStatus": "RECRUITING"},
        "descriptionModule": {"briefSummary": title},
        "conditionsModule": {"conditions": ["Lymphoma"]},
        "armsInterventionsModule": {
            "interventions": [{"name": title.split()[0], "type": "DRUG"}]
        },
        "designModule": {"phases": ["PHASE1"]},
    }


PROTOCOLS = [
    _protocol(
        "NCT00000001",
        "FXB-101 a CD19 bispecific T-cell engager in relapsed lymphoma",
    ),
    _protocol(
        "NCT00000002",
        "FXB-202 a BCMA bispecific T-cell engager in multiple myeloma",
    ),
]


#: Never returned by a successful fetch — only by a failed attempt that is later
#: superseded, which is how a record ends up on disk that no accepted query explains.
LEAKED_PROTOCOL = _protocol(
    "NCT00000099", "FXB-999 a CD19 bispecific T-cell engager, partial fetch only"
)

#: Snapshotted by the backend and then excluded by the as-of cutoff. The bytes are on
#: disk and no query admits the record, which is the second way B7 grew files nothing
#: could explain.
WITHHELD_PROTOCOL = _protocol(
    "NCT00000077", "FXB-777 a CD19 bispecific T-cell engager updated after the cutoff"
)


def _record(protocol: dict) -> TrialRecord:
    return TrialRecord(
        trial_id=protocol["identificationModule"]["nctId"],
        brief_title=protocol["identificationModule"]["briefTitle"],
        brief_summary=protocol["identificationModule"]["briefTitle"],
        raw_payload=protocol,
        snapshot=TrialSnapshot(
            content_hash=payload_digest(protocol),
            backend="fixture",
            payload_kind=PayloadKind.CTGOV_PROTOCOL_JSON,
        ),
    )


class FixtureProvider:
    """Deterministic CT.gov-shaped universe. Optionally flaky the first time per query.

    ``flaky`` reproduces the B7 failure mode exactly: the first attempt at a query pulls a
    record down and *then* reports failure, so the bytes exist before anything succeeds.
    """

    backend_name = "fixture"

    def __init__(
        self, *, flaky: bool = False, leak: bool = False, withhold: bool = False
    ) -> None:
        self.flaky = flaky
        #: When set, every successful fetch also reports a record it materialized and then
        #: excluded, the way the CT.gov backend does for a post-cutoff update.
        self.withhold = withhold
        #: When set, the failed attempt materializes a record no later attempt accepts —
        #: a record whose only explanation is an attempt that was superseded.
        self.leak = leak
        self.seen: set[str] = set()
        self.last_page_count = 1

    def fetch(self, query):
        key = "|".join(sorted(t for facet in query.facets() for t in facet))
        if self.flaky and key not in self.seen:
            self.seen.add(key)
            partial = self._matched(query)
            if self.leak:
                partial = [_record(LEAKED_PROTOCOL)]
            return TrialUniverseResult(
                # Materialized, then failed: the partial records are real and on their way
                # to disk whatever this attempt's outcome turns out to be.
                records=partial,
                outcome=SearchOutcome.FAILED,
                backend=self.backend_name,
                error="fixture transport failure after partial materialization",
            )
        matched = self._matched(query)
        return TrialUniverseResult(
            records=matched,
            withheld_records=(
                [_record(WITHHELD_PROTOCOL)] if self.withhold and matched else []
            ),
            outcome=SearchOutcome.SUCCESS if matched else SearchOutcome.NO_EVIDENCE_FOUND,
            backend=self.backend_name,
        )

    def _matched(self, query) -> list[TrialRecord]:
        return [
            _record(protocol)
            for protocol in PROTOCOLS
            if any(
                all(
                    term.casefold() in protocol["identificationModule"]["briefTitle"].casefold()
                    for term in (facet[0],)
                )
                for facet in query.facets()
            )
        ]


def _live_run(
    tmp_path: Path,
    *,
    flaky: bool,
    leak: bool = False,
    withhold: bool = False,
    run_id: str = "run:live",
):
    snapshots = tmp_path / "snapshots"
    adapter = ClinicalTrialsGovAdapter(
        provider=FixtureProvider(flaky=flaky, leak=leak, withhold=withhold),
        snapshot_root=snapshots,
    )
    result = run_landscape_search(
        _problem(),
        [adapter],
        run_id=run_id,
        code_version=CODE_VERSION,
        normalization_version=NORMALIZATION_VERSION,
        declared_mandatory_sources=["clinicaltrials_gov"],
        custody_root=tmp_path / "custody",
        custody_pins={"fixture": "v1"},
    )
    return result, snapshots


def _replay_run(tmp_path: Path, custody_root: Path, snapshots: Path, run_id: str):
    replay = SealedCorpusReplay(custody_root)
    adapter = ReplayTrialsGovAdapter(replay, snapshot_root=snapshots)
    with block_network():
        result = run_landscape_search(
            _problem(),
            [adapter],
            run_id=run_id,
            code_version=CODE_VERSION,
            normalization_version=NORMALIZATION_VERSION,
            declared_mandatory_sources=["clinicaltrials_gov"],
            custody_root=tmp_path / "custody_replay",
            custody_pins={"fixture": "v1"},
        )
    return result, replay


def _signature(result) -> dict:
    """Everything a scoreable run depends on at the pre-EXTRACTION boundary."""

    return {
        # Hits are not carried on the result, so they are compared through everything
        # they produce: identity mentions are one row per hit, and claims/facts are the
        # per-hit extraction output.
        "identity_mentions": sorted(
            (mention.hit_id, mention.raw_asset_name, mention.source_document_id)
            for mention in result.identity_mentions
        ),
        "claims": sorted(claim.claim_id for claim in result.claims),
        "facts": sorted(fact.fact_id for fact in result.facts),
        "eligible": sorted(result.eligible_asset_ids),
        "excluded": sorted(result.excluded_asset_ids),
        "review_queue": sorted((item.subject_id, item.reason) for item in result.review_queue),
        "assets": sorted(asset.asset_id for asset in result.candidates),
        "asset_names": sorted(asset.canonical_name for asset in result.candidates),
        "documents": sorted(result.run_manifest.evidence_snapshot_ids),
        "source_status": {
            name: status.value for name, status in result.run_manifest.source_status.items()
        },
        "status": result.run_manifest.status.value,
    }


class TestRetryLeavesNoOrphan:
    def test_superseded_attempt_still_owns_its_bytes(self, tmp_path: Path) -> None:
        result, snapshots = _live_run(tmp_path, flaky=True)
        sealed = validate_seal(tmp_path / "custody")

        failed = [a for a in sealed.attempts if a.outcome is SearchOutcome.FAILED]
        assert failed, "the fixture is supposed to fail the first attempt at each query"
        assert any(a.materializations for a in failed), (
            "a failed attempt that fetched records must still declare them"
        )
        assert all(a.superseded_by_attempt is not None for a in failed if not a.accepted)

        # The B7 symptom, checked directly: no file on disk that no attempt explains.
        assert unexplained_snapshots(sealed, [snapshots]) == []
        assert result.run_manifest.status is not None

    def test_every_record_is_attributed_to_the_query_that_accepted_it(
        self, tmp_path: Path
    ) -> None:
        _live_run(tmp_path, flaky=True)
        sealed = validate_seal(tmp_path / "custody")
        assert sealed.seal.orphan_record_count == 0
        for entry in sealed.ledger:
            assert entry.accepted_by_queries

    def test_a_record_only_a_superseded_attempt_saw_is_labelled_not_hidden(
        self, tmp_path: Path
    ) -> None:
        """The disposition B7 could not state: bytes owned by an attempt nobody accepted.

        The right answer is not to suppress the record or to smuggle it into the accepted
        membership — either would change what the run saw. It is to keep it, mark it
        orphaned, and leave the count on the seal where a reader cannot miss it.
        """

        _live_run(tmp_path, flaky=True, leak=True)
        sealed = validate_seal(tmp_path / "custody")
        orphans = [entry for entry in sealed.ledger if entry.is_orphan]
        assert [entry.record_id for entry in orphans] == ["NCT00000099"]
        assert sealed.seal.orphan_record_count == 1
        assert orphans[0].materialized_by_attempts >= 1
        # Still fully explained: the file traces to the attempt that fetched it.
        assert unexplained_snapshots(sealed, [tmp_path / "snapshots"]) == []


class TestCutoffExcludedRecordsStayAccounted:
    """The second orphan mechanism: bytes written before the as-of cutoff is applied.

    The CT.gov backend snapshots every study it normalizes and only then asks whether the
    query admits it, so a trial updated after the as-of date leaves a file that no accepted
    query can claim. Declaring it withheld is the difference between a stated exclusion and
    an unexplained file; admitting it would silently widen the universe the run scored.
    """

    def test_withheld_record_is_named_but_not_admitted(self, tmp_path: Path) -> None:
        _live_run(tmp_path, flaky=False, withhold=True)
        sealed = validate_seal(tmp_path / "custody")

        withheld = [entry for entry in sealed.ledger if not entry.admitted]
        assert [entry.record_id for entry in withheld] == ["NCT00000077"]
        assert sealed.seal.withheld_record_count == 1
        # Named, so not an orphan; not admitted, so not part of the universe.
        assert sealed.seal.orphan_record_count == 0
        assert "NCT00000077" not in {
            record_id for attempt in sealed.attempts for record_id in attempt.record_ids
        }
        assert unexplained_snapshots(sealed, [tmp_path / "snapshots"]) == []

    def test_replay_reproduces_the_withheld_disposition(self, tmp_path: Path) -> None:
        live, snapshots = _live_run(tmp_path, flaky=False, withhold=True)
        replayed, replay = _replay_run(
            tmp_path, tmp_path / "custody", snapshots, run_id="run:live"
        )

        assert _signature(replayed) == _signature(live)
        assert replay.unconsumed() == {}
        live_seal = validate_seal(tmp_path / "custody").seal
        replay_seal = validate_seal(tmp_path / "custody_replay").seal
        assert replay_seal.withheld_record_count == live_seal.withheld_record_count
        assert replay_seal.universe_hash == live_seal.universe_hash


class TestSealIsFailClosed:
    def test_mutated_corpus_fails_validation(self, tmp_path: Path) -> None:
        _live_run(tmp_path, flaky=False)
        ledger = (tmp_path / "custody" / "acquisition_ledger.jsonl")
        ledger.write_text(ledger.read_text() + "\n")
        with pytest.raises(CustodyError):
            validate_seal(tmp_path / "custody")

    def test_unexpected_file_in_custody_root_fails_validation(self, tmp_path: Path) -> None:
        _live_run(tmp_path, flaky=False)
        (tmp_path / "custody" / "notes.txt").write_text("hello\n")
        with pytest.raises(CustodyError):
            validate_seal(tmp_path / "custody")

    def test_sealing_twice_into_one_root_is_refused(self, tmp_path: Path) -> None:
        _live_run(tmp_path, flaky=False)
        with pytest.raises(CustodyError):
            _live_run(tmp_path, flaky=False, run_id="run:second")


class TestOfflineReplayReproducesTheRun:
    @pytest.mark.parametrize("flaky", [False, True])
    def test_replay_matches_the_live_run_exactly(self, tmp_path: Path, flaky: bool) -> None:
        live, snapshots = _live_run(tmp_path, flaky=flaky)
        replayed, replay = _replay_run(
            tmp_path, tmp_path / "custody", snapshots, run_id="run:live"
        )

        assert _signature(replayed) == _signature(live)
        assert replay.unconsumed() == {}, "replay skipped attempts the run had recorded"

        live_seal = validate_seal(tmp_path / "custody").seal
        replay_seal = validate_seal(tmp_path / "custody_replay").seal
        assert replay_seal.universe_hash == live_seal.universe_hash
        assert replay_seal.record_count == live_seal.record_count
        assert replay_seal.semantic_query_count == live_seal.semantic_query_count
        assert replay_seal.orphan_record_count == 0

    def test_replay_reproduces_query_membership_not_the_union(self, tmp_path: Path) -> None:
        live, snapshots = _live_run(tmp_path, flaky=False)
        live_sealed = validate_seal(tmp_path / "custody")
        memberships = {
            (m.semantic_query_id, m.pass_number): tuple(m.record_ids)
            for m in live_sealed.mappings
        }
        # The corpus has more records than any one query returned; a union-based replay
        # would hand every query the whole corpus and inflate every membership.
        corpus = {entry.record_id for entry in live_sealed.ledger}
        assert any(set(ids) != corpus for ids in memberships.values())

        _replay_run(tmp_path, tmp_path / "custody", snapshots, run_id="run:live")
        replay_sealed = validate_seal(tmp_path / "custody_replay")
        assert {
            (m.semantic_query_id, m.pass_number): tuple(m.record_ids)
            for m in replay_sealed.mappings
        } == memberships

    def test_replay_does_not_write_into_the_sealed_snapshot_tree(
        self, tmp_path: Path
    ) -> None:
        _live_run(tmp_path, flaky=True)
        snapshots = tmp_path / "snapshots"
        before = {
            path.name: (path.stat().st_mtime_ns, path.read_bytes())
            for path in snapshots.glob("*.json")
        }
        _replay_run(tmp_path, tmp_path / "custody", snapshots, run_id="run:live")
        after = {
            path.name: (path.stat().st_mtime_ns, path.read_bytes())
            for path in snapshots.glob("*.json")
        }
        assert after == before

    def test_replay_of_an_unrecorded_query_is_fatal(self, tmp_path: Path) -> None:
        _live_run(tmp_path, flaky=False)
        replay = SealedCorpusReplay(tmp_path / "custody")
        adapter = ReplayTrialsGovAdapter(replay, snapshot_root=tmp_path / "snapshots")

        class _Query:
            query = "a question this acquisition was never asked"
            target_ids: list[str] = []
            modality_ids: list[str] = []
            aliases: list[str] = []

        with pytest.raises(ReplayDivergence):
            adapter._acquire(None, _Query(), datetime.now(timezone.utc).date())

    def test_network_is_blocked_during_replay(self, tmp_path: Path) -> None:
        with block_network():
            with pytest.raises(NetworkBlocked):
                import socket

                socket.getaddrinfo("clinicaltrials.gov", 443)
        # and restored afterwards, so one replay cannot disarm the rest of the process
        import socket

        assert socket.getaddrinfo("localhost", 80)


class TestSourceStateSemanticsSurviveCustody:
    def test_not_configured_source_is_recorded_as_a_blind_spot(self, tmp_path: Path) -> None:
        adapter = ClinicalTrialsGovAdapter(
            provider=FixtureProvider(), snapshot_root=tmp_path / "snapshots"
        )
        unavailable = UnavailableSourceAdapter("sec_edgar", "no connector configured")
        result = run_landscape_search(
            _problem(),
            [adapter, unavailable],
            run_id="run:blind",
            code_version=CODE_VERSION,
            normalization_version=NORMALIZATION_VERSION,
            declared_mandatory_sources=["clinicaltrials_gov", "sec_edgar"],
            custody_root=tmp_path / "custody",
        )
        assert result.run_manifest.status is RunStatus.INCOMPLETE
        assert any("sec_edgar" in spot for spot in result.run_manifest.known_blind_spots)

        sealed = validate_seal(tmp_path / "custody")
        health = {
            entry["source"]: entry
            for entry in _read_health(tmp_path / "custody")["sources"]
        }
        assert health["sec_edgar"]["status"] == SearchOutcome.NOT_CONFIGURED.value
        assert health["sec_edgar"]["records"] == 0
        assert sealed.seal.source_counts.get("sec_edgar", 0) == 0

    def test_no_evidence_found_is_a_completed_acquisition(self, tmp_path: Path) -> None:
        class EmptyProvider(FixtureProvider):
            def fetch(self, query):
                return TrialUniverseResult(
                    records=[],
                    outcome=SearchOutcome.NO_EVIDENCE_FOUND,
                    backend=self.backend_name,
                )

        adapter = ClinicalTrialsGovAdapter(
            provider=EmptyProvider(), snapshot_root=tmp_path / "snapshots"
        )
        result = run_landscape_search(
            _problem(),
            [adapter],
            run_id="run:empty",
            code_version=CODE_VERSION,
            normalization_version=NORMALIZATION_VERSION,
            declared_mandatory_sources=["clinicaltrials_gov"],
            custody_root=tmp_path / "custody",
        )
        assert result.run_manifest.fatal_reasons == []
        sealed = validate_seal(tmp_path / "custody")
        assert sealed.seal.record_count == 0
        assert sealed.attempts, "an empty acquisition still has to record that it asked"


class TestCliRefusesToProceedPastABadBoundary:
    def test_a_failed_seal_stops_the_run_with_its_own_exit_code(
        self, tmp_path: Path, capsys
    ) -> None:
        from unittest import mock

        from bve.cli import se_search

        problem = tmp_path / "p.yaml"
        problem.write_text(yaml.safe_dump(_problem().model_dump(mode="json")))

        def _fail(*_args, **_kwargs):
            raise CustodyError("seal did not validate")

        with mock.patch.object(se_search, "run_landscape_search", _fail):
            code = se_search.main(
                [
                    "--problem",
                    str(problem),
                    "--allow-incomplete",
                    "--custody-root",
                    str(tmp_path / "custody"),
                ]
            )

        assert code == 5, "a custody failure must not be reported as a merely incomplete run"
        assert "custody boundary failed" in capsys.readouterr().err

    def test_replay_and_the_snapshot_union_path_are_mutually_exclusive(
        self, tmp_path: Path
    ) -> None:
        from bve.cli import se_search

        problem = tmp_path / "p.yaml"
        problem.write_text(yaml.safe_dump(_problem().model_dump(mode="json")))
        with pytest.raises(SystemExit):
            se_search.main(
                [
                    "--problem",
                    str(problem),
                    "--offline",
                    "--replay-corpus",
                    str(tmp_path / "custody"),
                ]
            )


def _read_health(custody_root: Path) -> dict:
    import json

    return json.loads((custody_root / "source_health.json").read_text())
