"""The provider is the acquisition boundary, and a bound universe reproduces a run.

Two separable claims live here:

* discovery no longer acquires trials itself — it asks a provider and opens the envelopes
  it is entitled to, refusing payload shapes it cannot read
* fixing the inputs fixes the outputs, which is the reproducibility contract the whole
  product rests on: an answer can be re-derived against the universe it was actually
  computed from, not against whatever the registry serves today
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.cli.se_search import build_parser
from bve.se.discovery.adapters import (
    CTGOV_EXTRACTOR,
    ClinicalTrialsGovAdapter,
)
from bve.se.schemas.contracts import CompiledQuery, SearchOutcome
from bve.se.universe.ctgov import ClinicalTrialsGovProvider
from bve.se.universe.factory import (
    TrialBackendNotConfigured,
    build_trial_provider,
)
from bve.se.universe.frozen import FrozenTrialProvider
from bve.se.universe.provenance import provenance_hash
from bve.se.universe.provider import (
    PayloadKind,
    TrialQuery,
    TrialRecord,
    TrialSnapshot,
)

AS_OF = date(2026, 7, 12)


def _protocol(nct_id: str = "NCT00000001") -> dict:
    return {
        "identificationModule": {"nctId": nct_id, "briefTitle": "CLN-978 CD19 T-cell engager"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-05-01"}},
        "armsInterventionsModule": {
            "interventions": [
                {
                    "name": "CLN-978",
                    "description": "CD19-directed CD3 bispecific T-cell engager",
                    "otherNames": ["CLN978"],
                }
            ]
        },
    }


def _query() -> CompiledQuery:
    return CompiledQuery(
        query_id="query:test",
        query="CD19 T-cell engager",
        target_ids=["CD19"],
        modality_ids=["T_CELL_ENGAGER"],
    )


def _provider(*protocols: dict) -> ClinicalTrialsGovProvider:
    return ClinicalTrialsGovProvider(search_fn=lambda **_: list(protocols))


class TestAcquisitionBoundary:
    def test_adapter_discovers_through_a_provider(self, se_ontology_snapshot) -> None:
        adapter = ClinicalTrialsGovAdapter(provider=_provider(_protocol()))
        result = adapter.search(_query(), as_of_date=AS_OF)

        assert result.outcome is SearchOutcome.SUCCESS
        assert [hit.asset_name for hit in result.hits] == ["CLN-978"]

    def test_provider_and_search_fn_are_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="not both"):
            ClinicalTrialsGovAdapter(search_fn=lambda **_: [], provider=_provider())

    def test_unreadable_payload_kind_is_refused_not_guessed(self, se_ontology_snapshot) -> None:
        """An AACT row mis-parsed as CT.gov JSON would look like an empty trial, not an error."""

        record = TrialRecord(
            trial_id="NCT00000002",
            brief_title="CD19 T-cell engager",
            snapshot=TrialSnapshot(
                content_hash="0" * 64,
                backend="aact",
                payload_kind=PayloadKind.AACT_RELATIONAL_RECORD,
            ),
            raw_payload={"nct_id": "NCT00000002"},
        )
        provider = FrozenTrialProvider([record])
        result = ClinicalTrialsGovAdapter(provider=provider).search(_query(), as_of_date=AS_OF)

        assert result.outcome is SearchOutcome.FAILED
        assert "payload kind" in (result.error or "")

    def test_provider_failure_is_reported_not_swallowed(self, se_ontology_snapshot) -> None:
        def explode(**_):
            raise RuntimeError("offline")

        adapter = ClinicalTrialsGovAdapter(provider=ClinicalTrialsGovProvider(search_fn=explode))
        result = adapter.search(_query(), as_of_date=AS_OF)

        assert result.outcome is SearchOutcome.FAILED
        assert "offline" in (result.error or "")


class TestBackendSelection:
    def test_rest_is_operational(self) -> None:
        assert build_trial_provider("rest").backend_name == "ctgov_rest"

    @pytest.mark.parametrize("backend", ["aact", "hybrid"])
    def test_unconfigured_backends_refuse_rather_than_fall_back(
        self, backend: str, monkeypatch
    ) -> None:
        monkeypatch.delenv("BVE_AACT_DSN", raising=False)
        with pytest.raises(TrialBackendNotConfigured, match="AACT"):
            build_trial_provider(backend)

    def test_unknown_backend_is_a_configuration_error(self) -> None:
        with pytest.raises(ValueError, match="unknown trial backend"):
            build_trial_provider("postgres")

    def test_cli_defaults_to_rest_and_rejects_unknown_names(self) -> None:
        parser = build_parser()

        assert parser.parse_args(["--problem", "p.yaml"]).trial_backend == "rest"
        assert (
            parser.parse_args(["--problem", "p.yaml", "--trial-backend", "aact"]).trial_backend
            == "aact"
        )
        with pytest.raises(SystemExit):
            parser.parse_args(["--problem", "p.yaml", "--trial-backend", "postgres"])


class TestUniverseProvenance:
    def test_provenance_describes_the_universe_the_run_saw(self, se_ontology_snapshot) -> None:
        adapter = ClinicalTrialsGovAdapter(provider=_provider(_protocol()))
        adapter.search(_query(), as_of_date=AS_OF)
        provenance = adapter.trial_universe

        assert provenance is not None
        assert provenance.backend == "ctgov_rest"
        assert provenance.records_returned == 1
        assert provenance.extractor == CTGOV_EXTRACTOR
        assert provenance.snapshot_ids
        assert provenance.query["terms"]
        assert provenance.provenance_hash

    def test_a_run_without_a_provider_states_no_universe(self, se_ontology_snapshot) -> None:
        """The legacy path cannot describe where its records came from, and says so."""

        adapter = ClinicalTrialsGovAdapter(search_fn=lambda **_: [_protocol()])
        adapter.search(_query(), as_of_date=AS_OF)

        assert adapter.trial_universe is None

    def test_provenance_hash_ignores_wall_clock(self, se_ontology_snapshot) -> None:
        """Two runs over one universe are one universe, whenever they happened.

        Binding the clock into the digest would make every run trivially unique, which is
        the same as having no identity at all.
        """

        adapter = ClinicalTrialsGovAdapter(provider=_provider(_protocol()))
        adapter.search(_query(), as_of_date=AS_OF)
        provenance = adapter.trial_universe

        later = provenance.model_copy(
            update={
                "retrieval_started_at": datetime(2030, 1, 1, tzinfo=timezone.utc),
                "retrieval_completed_at": datetime(2030, 1, 2, tzinfo=timezone.utc),
            }
        )

        assert provenance.retrieval_started_at is not None
        assert provenance_hash(later) == provenance.provenance_hash

    def test_a_different_universe_gets_a_different_hash(self, se_ontology_snapshot) -> None:
        one = ClinicalTrialsGovAdapter(provider=_provider(_protocol()))
        two = ClinicalTrialsGovAdapter(
            provider=_provider(_protocol(), _protocol("NCT00000009"))
        )
        one.search(_query(), as_of_date=AS_OF)
        two.search(_query(), as_of_date=AS_OF)

        assert one.trial_universe.provenance_hash != two.trial_universe.provenance_hash


class TestDeterministicRun:
    def test_same_inputs_give_the_same_discovered_identities(self, se_ontology_snapshot) -> None:
        """Bind problem, ontology snapshot, universe and extractor; outputs must not move.

        The ontology snapshot is bound by the fixture, the extractor by the adapter, and
        the universe by replaying identical payloads. Anything that varies across these
        two runs is non-determinism the manifest could not explain.
        """

        runs = []
        for _ in range(2):
            adapter = ClinicalTrialsGovAdapter(provider=_provider(_protocol()))
            result = adapter.search(_query(), as_of_date=AS_OF)
            runs.append(
                {
                    "assets": [hit.asset_name for hit in result.hits],
                    "identities": sorted(hit.provisional_identity_key for hit in result.hits),
                    # Evidence identity: which record, which stored document, under
                    # which hit id. ``retrieved_at`` is deliberately excluded — it is
                    # wall-clock provenance, and pinning it would test the clock.
                    "evidence": sorted(
                        (hit.hit_id, hit.trial_id or "", hit.source_document_id or "")
                        for hit in result.hits
                    ),
                    "aliases": sorted(result.discovered_aliases),
                    "follow_ups": sorted(result.follow_up_queries),
                    "snapshots": sorted(result.snapshot_ids),
                    "documents": sorted(
                        document.content_hash for document in result.source_documents
                    ),
                    "outcome": result.outcome,
                    "universe": adapter.trial_universe.provenance_hash,
                }
            )

        assert runs[0] == runs[1]

    def test_query_is_translated_for_the_backend_not_by_it(self, se_ontology_snapshot) -> None:
        """Alias expansion happens above the provider; providers translate, not reason."""

        seen: list[TrialQuery] = []

        class Recording(FrozenTrialProvider):
            def fetch(self, query: TrialQuery):
                seen.append(query)
                return super().fetch(query)

        ClinicalTrialsGovAdapter(provider=Recording([])).search(_query(), as_of_date=AS_OF)

        assert seen and seen[0].as_of_date == AS_OF
        assert "CD19" in seen[0].terms


def test_rest_provider_tags_the_payload_it_preserves() -> None:
    result = _provider(_protocol()).fetch(TrialQuery(terms=["CD19"]))
    record = result.records[0]

    assert record.snapshot is not None
    assert record.snapshot.payload_kind is PayloadKind.CTGOV_PROTOCOL_JSON
    assert record.raw_payload == _protocol()
