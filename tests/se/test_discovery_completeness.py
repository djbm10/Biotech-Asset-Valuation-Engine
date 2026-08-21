"""M9E1/M9E2: transport paging is not an evaluation policy, and an ambiguous
target may not silently become a search term.

Both invariants come from the first PDCD1 baseline, where a hardcoded 250 doubled as
a recall ceiling and the bare nickname "PD-1" ran a literal search after the ontology
had explicitly abstained on it.
"""

from __future__ import annotations

import pytest

from bve.se.discovery.query import AmbiguousTargetError, compile_problem_queries
from bve.se.evaluation.ontology_gate import (
    TruncatedUniverseError,
    require_untruncated_universe,
)
from bve.se.schemas.contracts import (
    BuyerProblemV2,
    RunManifest,
    RunStatus,
    SearchOutcome,
)
from bve.se.universe import ClinicalTrialsGovProvider, TrialQuery
from bve.se.universe.provenance import TrialUniverseProvenance


def _study(index: int) -> dict:
    return {
        "identificationModule": {"nctId": f"NCT{index:08d}", "briefTitle": "t"},
        "statusModule": {},
        "designModule": {},
    }


def _provider(total: int):
    """A search_fn that honours ``max_records`` the way the real client's paging does."""

    def search_fn(**kwargs):
        search_fn.calls.append(kwargs)
        cap = kwargs.get("max_records")
        studies = [_study(i) for i in range(total)]
        return studies if cap is None else studies[:cap]

    search_fn.calls = []
    return ClinicalTrialsGovProvider(search_fn), search_fn


class TestRecordCapIsPolicyNotTransport:
    def test_page_size_does_not_cap_the_universe(self):
        provider, search_fn = _provider(700)
        result = provider.fetch(TrialQuery(terms=["PDCD1"]))
        assert len(result.records) == 700
        assert result.truncated is False
        assert search_fn.calls[0]["page_size"] == provider.page_size
        assert search_fn.calls[0]["max_records"] is None

    def test_an_unbounded_query_is_exhaustive_by_default(self):
        assert TrialQuery(terms=["PDCD1"]).max_records is None

    def test_a_declared_bound_truncates_and_says_so(self):
        provider, search_fn = _provider(700)
        result = provider.fetch(TrialQuery(terms=["PDCD1"], max_records=250))
        assert len(result.records) == 250
        assert result.truncated is True
        # One record past the bound is requested so "cut short" can be told apart from
        # "the universe happened to be exactly this size".
        assert search_fn.calls[0]["max_records"] == 251

    def test_a_bound_larger_than_the_universe_is_not_truncation(self):
        provider, _ = _provider(40)
        result = provider.fetch(TrialQuery(terms=["PDCD1"], max_records=250))
        assert len(result.records) == 40
        assert result.truncated is False

    def test_the_bound_applies_across_split_batches_not_per_batch(self):
        provider, _ = _provider(100)
        wide = [f"term{i}" for i in range(30)]
        result = provider.fetch(TrialQuery(terms=wide, max_records=10))
        assert len(result.records) == 10
        assert result.truncated is True


def _manifest(truncated: bool) -> RunManifest:
    return RunManifest(
        run_id="se:test",
        problem_id="p",
        problem_version="1",
        as_of_date="2026-08-21",
        started_at="2026-08-21T00:00:00Z",
        code_version="test",
        normalization_version="test",
        status=RunStatus.CONVERGED,
        ontology_version="chembl_ChEMBL_37__open_targets_26.06__resolver_v1",
        trial_universe=TrialUniverseProvenance(
            backend="ctgov_rest",
            records_considered=250,
            records_returned=250,
            truncated=truncated,
        ),
    )


class TestTruncationFailsClosedForScoring:
    def test_a_truncated_universe_may_not_be_scored(self):
        with pytest.raises(TruncatedUniverseError) as excinfo:
            require_untruncated_universe(_manifest(True), reference_set="pdcd1")
        assert "pdcd1" in str(excinfo.value)

    def test_a_complete_universe_scores(self):
        require_untruncated_universe(_manifest(False), reference_set="pdcd1")

    def test_a_run_with_no_trial_universe_is_not_silently_complete(self):
        # The offline path cannot state its universe. Scoring it is allowed -- refusing
        # would break replay benchmarks -- but the weaker claim is said out loud.
        manifest = _manifest(False).model_copy(update={"trial_universe": None})
        with pytest.warns(UserWarning, match="cannot be shown to be complete"):
            require_untruncated_universe(manifest, reference_set="pdcd1")


def _problem(canonical_id: str) -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        {
            "problem_id": "p",
            "version": "1",
            "buyer": {"buyer_id": "b", "name": "B", "as_of_date": "2026-08-21"},
            "strategic_gap": {
                "therapeutic_areas": ["oncology"],
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": canonical_id, "label": canonical_id}],
                },
                "modalities": ["MONOCLONAL_ANTIBODY"],
            },
        }
    )


class TestAmbiguousTargetsDoNotBecomeSearchTerms:
    def test_an_ambiguous_target_refuses_instead_of_searching_literally(self, monkeypatch):
        monkeypatch.setattr(
            "bve.se.discovery.query.resolve_target",
            lambda value: _ambiguous(value, ["TARGET:PDCD1", "TARGET:RPL17"]),
        )
        with pytest.raises(AmbiguousTargetError) as excinfo:
            compile_problem_queries(_problem("PD-1"))
        assert excinfo.value.query == "PD-1"
        assert excinfo.value.candidates == ("TARGET:PDCD1", "TARGET:RPL17")
        assert "PD-1" in str(excinfo.value)

    def test_a_resolved_target_compiles_as_before(self, monkeypatch):
        monkeypatch.setattr("bve.se.discovery.query.resolve_target", lambda value: None)
        assert compile_problem_queries(_problem("PDCD1"))

    def test_an_unresolved_target_is_allowed_as_a_literal_search(self, monkeypatch):
        monkeypatch.setattr(
            "bve.se.discovery.query.resolve_target",
            lambda value: _unresolved(value),
        )
        with pytest.warns(UserWarning, match="not present in the ontology"):
            queries = compile_problem_queries(_problem("XYZ9"))
        assert queries


def _ambiguous(value, ids):
    from bve.se.ontology.resolver import (
        CanonicalEntity,
        EntityType,
        ResolutionResult,
        ResolutionStatus,
    )

    return ResolutionResult(
        query=value,
        status=ResolutionStatus.AMBIGUOUS,
        candidates=[
            CanonicalEntity(canonical_id=i, entity_type=EntityType.TARGET) for i in ids
        ],
    )


def _unresolved(value):
    from bve.se.ontology.resolver import ResolutionResult, ResolutionStatus

    return ResolutionResult(query=value, status=ResolutionStatus.UNRESOLVED)


def test_search_outcome_enum_is_unchanged():
    assert SearchOutcome.SUCCESS
