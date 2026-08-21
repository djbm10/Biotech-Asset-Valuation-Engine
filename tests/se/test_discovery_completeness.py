"""M9E1/M9E2: transport paging is not an evaluation policy, and an ambiguous
target may not silently become a search term.

Both invariants come from the first PDCD1 baseline, where a hardcoded 250 doubled as
a recall ceiling and the bare nickname "PD-1" ran a literal search after the ontology
had explicitly abstained on it.
"""

from __future__ import annotations

from unittest import mock

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


#: A v2 problem whose only declared target is the bare nickname the ontology
#: abstains on. Inlined rather than read from disk so the test travels with the repo.
_AMBIGUOUS_PROBLEM_YAML = """\
schema_version: se_buyer_problem_v2
problem_id: smoke_pd1_nickname
version: "1.0.0"
buyer:
  buyer_id: baseline_buyer
  name: PDCD1 Baseline Buyer
  as_of_date: 2026-08-20
strategic_gap:
  therapeutic_areas: [oncology]
  indications: []
  target_expression:
    operator: ANY
    targets:
      # Product-behaviour smoke test ONLY. The user types the bare nickname
      # "PD-1". Expected behaviour is an ambiguity/abstention signal, not a
      # silent guess. NOT scored for candidate recall.
      - canonical_id: PD-1
        label: PD-1
        aliases: []
  # The M8 PDCD1 benchmark places no modality restriction on its 224 canonical
  # candidates, so the baseline declares the full supported modality ontology
  # (modality_v2) rather than a subset. The schema requires at least one entry.
  modalities:
    - ANTIBODY_DRUG_CONJUGATE
    - BISPECIFIC_ANTIBODY
    - CAR_T
    - CELL_THERAPY
    - FUSION_PROTEIN
    - GENE_EDITING
    - GENE_THERAPY
    - MOLECULAR_GLUE_OR_DEGRADER
    - MONOCLONAL_ANTIBODY
    - MULTISPECIFIC_ANTIBODY
    - ONCOLYTIC_VIRUS
    - PEPTIDE
    - RADIOLIGAND
    - RNA_THERAPEUTIC
    - SMALL_MOLECULE
    - T_CELL_ENGAGER
    - VACCINE
  required_biology: []
  capability_constraints:
    manufacturing: []
    delivery: []
    clinical_operations: []
    commercial: []
    integration: []
  evidence_floor:
    minimum_stage: PHASE_1
    human_poc_required: true
    evaluable_patients_minimum: null
    follow_up_minimum_days: null
    required_evidence_types: [HUMAN_CLINICAL_RESULT]
  clinical_effect_bar: {}
  acceptable_deal_routes: [LICENSE, COLLABORATION, OPTION, ACQUISITION]
  geographic_rights_requirements: []
  missing_evidence_policy: REVIEW
output:
  landscape_mode: SEPARATE
  group_by: COHORT
ranking_cohort_required: true
"""


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


class TestAmbiguousTargetsReachTheUserAsAQuestion:
    """The CLI has to turn the refusal into a clarification, not a traceback."""

    def test_the_cli_lists_the_candidates_and_exits_four(self, tmp_path, capsys):
        from bve.cli import se_search

        problem = tmp_path / "ambiguous.yaml"
        problem.write_text(_AMBIGUOUS_PROBLEM_YAML)

        def _explode(*args, **kwargs):
            raise AmbiguousTargetError("PD-1", ("TARGET:PDCD1", "TARGET:RPL17"))

        with mock.patch.object(se_search, "run_landscape_search", _explode):
            code = se_search.main(["--problem", str(problem), "--allow-incomplete"])

        assert code == 4
        err = capsys.readouterr().err
        assert "NEEDS_CLARIFICATION" in err
        # The point of the exit is the list -- a bare refusal would not be actionable.
        assert "TARGET:PDCD1" in err
        assert "TARGET:RPL17" in err
