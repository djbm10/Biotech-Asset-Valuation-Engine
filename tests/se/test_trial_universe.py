"""M9B — the trial universe boundary must hide which backend supplied a trial."""

from __future__ import annotations

import json
from datetime import date

import pytest

from bve.se.schemas.contracts import SearchOutcome
from bve.se.universe import (
    AACTProvider,
    CTGOV_MAX_QUERY_WORDS,
    ClinicalTrialsGovProvider,
    FrozenTrialProvider,
    HybridTrialProvider,
    TrialQuery,
    TrialRecord,
    build_trial_provider,
    normalize_study,
    parse_registry_date,
)

# Trimmed from a live /api/v2/studies response; field names and nesting are verbatim.
CTGOV_STUDY = {
    "protocolSection": {
        "identificationModule": {
            "nctId": "NCT05000000",
            "briefTitle": "Study of ABC-123 in Advanced Solid Tumors",
            "officialTitle": "A Phase 1/2 Study of ABC-123",
        },
        "statusModule": {
            "overallStatus": "RECRUITING",
            "startDateStruct": {"date": "2023-06"},
            "primaryCompletionDateStruct": {"date": "2026-01-31"},
            "lastUpdatePostDateStruct": {"date": "2026-05-14"},
        },
        "descriptionModule": {"briefSummary": "ABC-123 targets PDCD1 in solid tumors."},
        "conditionsModule": {"conditions": ["Non-Small Cell Lung Cancer"]},
        "designModule": {
            "studyType": "INTERVENTIONAL",
            "phases": ["PHASE1", "PHASE2"],
            "enrollmentInfo": {"count": 120},
        },
        "armsInterventionsModule": {
            "interventions": [
                {
                    "type": "DRUG",
                    "name": "ABC-123",
                    "description": "anti-PD-1 monoclonal antibody",
                    "otherNames": ["ABC123"],
                }
            ]
        },
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": "Example Therapeutics"},
            "collaborators": [{"name": "Example University"}],
        },
    }
}

AACT_ROWS = [
    {
        "nct_id": "NCT05000000",
        "intervention_id": 991,
        "brief_title": "Study of ABC-123 in Advanced Solid Tumors",
        "official_title": "A Phase 1/2 Study of ABC-123",
        "overall_status": "Recruiting",
        "study_type": "Interventional",
        "phase": "Phase 1/Phase 2",
        "enrollment": 120,
        "start_date": date(2023, 6, 1),
        "primary_completion_date": date(2026, 1, 31),
        "completion_date": None,
        "last_update_posted_date": date(2026, 5, 14),
        "brief_summary": "ABC-123 targets PDCD1 in solid tumors.",
        "detailed_description": None,
        "lead_sponsor": "Example Therapeutics",
        "intervention_name": "ABC-123",
        "intervention_type": "Drug",
        "intervention_description": "anti-PD-1 monoclonal antibody",
    }
]


AACT_OTHER_NAMES = [{"intervention_id": 991, "name": "ABC123"}]


class _StubCursor:
    def __init__(self, rows, conditions, other_names=()):
        self.rows = rows
        self.conditions = conditions
        self.other_names = list(other_names)
        self._result: list[dict] = []
        self.statements: list[str] = []
        self.params: list = []

    def execute(self, sql, params=None):
        self.statements.append(sql)
        self.params.append(params)
        if "intervention_other_names" in sql:
            self._result = self.other_names
        elif "FROM conditions" in sql:
            self._result = self.conditions
        else:
            self._result = self.rows

    def fetchall(self):
        return self._result

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _StubConnection:
    def __init__(self, rows, conditions, other_names=()):
        self._cursor = _StubCursor(rows, conditions, other_names)

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _ctgov_provider(studies=(CTGOV_STUDY,)):
    def search_fn(**kwargs):
        search_fn.calls.append(kwargs)
        return [study["protocolSection"] for study in studies]

    search_fn.calls = []
    return ClinicalTrialsGovProvider(search_fn), search_fn


def _aact_provider(rows=AACT_ROWS, conditions=None):
    conditions = conditions if conditions is not None else [
        {"nct_id": "NCT05000000", "name": "Non-Small Cell Lung Cancer"}
    ]
    return AACTProvider(
        lambda: _StubConnection(rows, conditions, AACT_OTHER_NAMES),
        snapshot_release="2026-07-30",
    )


class TestRegistryDateParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2024-05-01", date(2024, 5, 1)),
            ("2024-05", date(2024, 5, 1)),
            ("2024", date(2024, 1, 1)),
            ("", None),
            (None, None),
            ("not a date", None),
        ],
    )
    def test_partial_registry_dates(self, raw, expected):
        assert parse_registry_date(raw) == expected

    def test_impossible_date_is_none_not_an_exception(self):
        assert parse_registry_date("2024-13-45") is None


class TestClinicalTrialsGovBackend:
    def test_normalizes_a_real_response_shape(self):
        record = normalize_study(CTGOV_STUDY["protocolSection"])
        assert record is not None
        assert record.trial_id == "NCT05000000"
        assert record.lead_sponsor == "Example Therapeutics"
        assert record.collaborators == ["Example University"]
        assert record.phases == ["PHASE1", "PHASE2"]
        assert record.enrollment == 120
        assert record.start_date == date(2023, 6, 1)
        assert record.interventions[0].other_names == ["ABC123"]

    def test_study_without_an_nct_id_is_dropped(self):
        assert normalize_study({"identificationModule": {"briefTitle": "anonymous"}}) is None

    def test_expanded_terms_become_one_intervention_query(self):
        provider, search_fn = _ctgov_provider()
        provider.fetch(TrialQuery(terms=["PDCD1", "PD-1", "CD279"]))
        assert len(search_fn.calls) == 1
        assert search_fn.calls[0]["intervention"] == "PDCD1 PD-1 CD279"

    def test_a_wide_alias_set_is_split_below_the_ctgov_complexity_limit(self):
        # The real PDCD1 alias expansion 400s with "Too complicated query": CT.gov's
        # Essie parser counts words, not terms, and refuses past roughly ten of them.
        provider, search_fn = _ctgov_provider()
        provider.fetch(
            TrialQuery(
                terms=[
                    "PDCD1", "PD-1", "PD1", "CD279", "SLEB2", "hSLE1", "hPD-1",
                    "programmed cell death 1", "Programmed cell death protein 1",
                    "systemic lupus erythematosus susceptibility 2",
                ]
            )
        )
        assert len(search_fn.calls) > 1
        for call in search_fn.calls:
            assert len(call["intervention"].split()) <= CTGOV_MAX_QUERY_WORDS
        searched = [term for call in search_fn.calls for term in call["intervention"].split()]
        assert "PDCD1" in searched
        assert "susceptibility" in searched

    def test_split_batches_are_deduped_into_one_universe(self):
        provider, search_fn = _ctgov_provider()
        result = provider.fetch(TrialQuery(terms="a b c d e f g h i j k l".split()))
        assert len(search_fn.calls) > 1
        # Every batch returns the same stub study; the union must not repeat it.
        assert [record.trial_id for record in result.records] == ["NCT05000000"]

    def test_one_failed_batch_does_not_look_like_a_complete_universe(self):
        def flaky(**kwargs):
            if "l" in kwargs["intervention"].split():
                raise RuntimeError("400 Too complicated query")
            return [CTGOV_STUDY["protocolSection"]]

        result = ClinicalTrialsGovProvider(flaky).fetch(
            TrialQuery(terms="a b c d e f g h i j k l".split())
        )
        assert result.outcome is SearchOutcome.FAILED
        assert "400" in (result.error or "")

    def test_upstream_failure_is_reported_not_swallowed(self):
        def boom(**_kwargs):
            raise RuntimeError("503 from CT.gov")

        result = ClinicalTrialsGovProvider(boom).fetch(TrialQuery(terms=["PDCD1"]))
        assert result.outcome is SearchOutcome.FAILED
        assert "503" in (result.error or "")
        assert result.records == []

    def test_as_of_date_excludes_later_updates(self):
        provider, _ = _ctgov_provider()
        result = provider.fetch(TrialQuery(terms=["PDCD1"], as_of_date=date(2026, 1, 1)))
        assert result.records == []
        assert result.outcome is SearchOutcome.NO_EVIDENCE_FOUND

    def test_records_carry_a_snapshot_reference(self, tmp_path):
        def search_fn(**_kwargs):
            return [CTGOV_STUDY["protocolSection"]]

        provider = ClinicalTrialsGovProvider(search_fn, snapshot_root=tmp_path)
        record = provider.fetch(TrialQuery(terms=["PDCD1"])).records[0]
        assert record.snapshot is not None
        assert record.snapshot.snapshot_id.startswith("snapshot:")
        assert json.loads(open(record.snapshot.snapshot_path).read())["identificationModule"]

    def test_max_records_reports_truncation(self):
        studies = []
        for index in range(3):
            study = json.loads(json.dumps(CTGOV_STUDY))
            study["protocolSection"]["identificationModule"]["nctId"] = f"NCT0500000{index}"
            studies.append(study)
        provider, _ = _ctgov_provider(studies)
        result = provider.fetch(TrialQuery(terms=["PDCD1"], max_records=2))
        assert len(result.records) == 2
        assert result.truncated is True


class TestAACTBackend:
    def test_normalizes_rows_into_the_same_record_shape(self):
        result = _aact_provider().fetch(TrialQuery(terms=["PDCD1"]))
        record = result.records[0]
        assert record.phases == ["PHASE1", "PHASE2"]
        assert record.overall_status == "RECRUITING"
        assert record.trial_id == "NCT05000000"
        assert record.lead_sponsor == "Example Therapeutics"
        assert record.conditions == ["Non-Small Cell Lung Cancer"]
        assert record.interventions[0].name == "ABC-123"
        assert result.backend_version == "2026-07-30"

    def test_alias_terms_are_bound_parameters_not_interpolated_sql(self):
        provider = _aact_provider()
        connection = _StubConnection(AACT_ROWS, [])
        provider.connector = lambda: connection
        provider.fetch(TrialQuery(terms=["PDCD1'; DROP TABLE studies;--"]))
        statement, params = connection._cursor.statements[0], connection._cursor.params[0]
        assert "DROP TABLE" not in statement
        assert params == ["%PDCD1'; DROP TABLE studies;--%"]

    def test_duplicate_intervention_rows_collapse_to_one_record(self):
        rows = [dict(AACT_ROWS[0]), dict(AACT_ROWS[0], intervention_name="Pembrolizumab")]
        result = _aact_provider(rows).fetch(TrialQuery(terms=["PDCD1"]))
        assert len(result.records) == 1
        assert [i.name for i in result.records[0].interventions] == ["ABC-123", "Pembrolizumab"]

    def test_missing_database_is_a_failure_not_an_empty_universe(self):
        provider = AACTProvider(dsn=None)
        provider.connector = provider._default_connector
        result = provider.fetch(TrialQuery(terms=["PDCD1"]))
        assert result.outcome is SearchOutcome.FAILED
        assert "BVE_AACT_DSN" in (result.error or "")


class TestBackendInterchangeability:
    """The point of M9B: downstream cannot tell the backends apart."""

    def test_both_backends_produce_the_same_normalized_record(self):
        ctgov_provider, _ = _ctgov_provider()
        ctgov = ctgov_provider.fetch(TrialQuery(terms=["PDCD1"])).records[0]
        aact = _aact_provider().fetch(TrialQuery(terms=["PDCD1"])).records[0]

        # Snapshot, retrieval metadata and the preserved payload are provenance and
        # legitimately differ — the payload is backend-shaped by definition, which is why
        # it travels tagged and opaque. Every field a downstream consumer reasons about
        # must not differ.
        ignored = {"snapshot", "retrieved_at", "raw_payload"}
        left = ctgov.model_dump(exclude=ignored)
        right = aact.model_dump(exclude=ignored | {"collaborators"})
        left.pop("collaborators")
        assert left == right

    def test_record_type_is_identical_across_backends(self):
        ctgov_provider, _ = _ctgov_provider()
        for provider in (ctgov_provider, _aact_provider()):
            for record in provider.fetch(TrialQuery(terms=["PDCD1"])).records:
                assert isinstance(record, TrialRecord)

    def test_searchable_text_does_not_depend_on_backend_json_shape(self):
        ctgov_provider, _ = _ctgov_provider()
        ctgov = ctgov_provider.fetch(TrialQuery(terms=["PDCD1"])).records[0]
        aact = _aact_provider().fetch(TrialQuery(terms=["PDCD1"])).records[0]
        for text in (ctgov.searchable_text(), aact.searchable_text()):
            assert "anti-PD-1 monoclonal antibody" in text
            assert "Example Therapeutics" in text
            # No backend field names leak into the text a matcher sees.
            assert "protocolSection" not in text
            assert "nct_id" not in text


class TestHybridBackend:
    def test_merges_both_backends_and_dedupes_by_trial_id(self):
        ctgov_provider, _ = _ctgov_provider()
        hybrid = HybridTrialProvider([_aact_provider(), ctgov_provider])
        result = hybrid.fetch(TrialQuery(terms=["PDCD1"]))
        assert [record.trial_id for record in result.records] == ["NCT05000000"]
        assert result.outcome is SearchOutcome.SUCCESS

    def test_first_provider_wins_on_conflict(self):
        primary = FrozenTrialProvider(
            [TrialRecord(trial_id="NCT05000000", brief_title="from primary")]
        )
        ctgov_provider, _ = _ctgov_provider()
        result = HybridTrialProvider([primary, ctgov_provider]).fetch(TrialQuery())
        assert result.records[0].brief_title == "from primary"

    def test_one_failed_backend_degrades_to_partial_not_success(self):
        broken = AACTProvider(lambda: (_ for _ in ()).throw(RuntimeError("mirror offline")))
        ctgov_provider, _ = _ctgov_provider()
        result = HybridTrialProvider([broken, ctgov_provider]).fetch(TrialQuery(terms=["PDCD1"]))
        assert result.outcome is SearchOutcome.PARTIAL
        assert "mirror offline" in (result.error or "")
        assert len(result.records) == 1

    def test_all_backends_failing_is_a_failure(self):
        broken = AACTProvider(lambda: (_ for _ in ()).throw(RuntimeError("mirror offline")))
        result = HybridTrialProvider([broken]).fetch(TrialQuery(terms=["PDCD1"]))
        assert result.outcome is SearchOutcome.FAILED
        assert result.records == []

    def test_requires_at_least_one_provider(self):
        with pytest.raises(ValueError):
            HybridTrialProvider([])


class TestFrozenBackend:
    def test_round_trips_through_jsonl(self, tmp_path):
        path = tmp_path / "fixture.jsonl"
        record = normalize_study(CTGOV_STUDY["protocolSection"])
        path.write_text(record.model_dump_json() + "\n")
        provider = FrozenTrialProvider.from_jsonl(path)
        result = provider.fetch(TrialQuery(terms=["ABC-123"]))
        assert [r.trial_id for r in result.records] == ["NCT05000000"]

    def test_non_matching_term_returns_no_evidence(self):
        provider = FrozenTrialProvider([normalize_study(CTGOV_STUDY["protocolSection"])])
        result = provider.fetch(TrialQuery(terms=["KRAS G12C"]))
        assert result.outcome is SearchOutcome.NO_EVIDENCE_FOUND


class TestFactory:
    def test_default_backend_needs_no_local_infrastructure(self):
        assert build_trial_provider().backend_name == "ctgov_rest"

    @pytest.mark.parametrize("backend", ["aact", "hybrid"])
    def test_named_backends_are_constructible(self, backend):
        assert build_trial_provider(backend, aact_dsn="postgresql://localhost/aact")

    def test_unknown_backend_names_the_valid_options(self):
        with pytest.raises(ValueError, match="unknown trial backend"):
            build_trial_provider("bigquery")

    def test_frozen_backend_requires_a_fixture(self):
        with pytest.raises(ValueError, match="fixture_path"):
            build_trial_provider("frozen")
