"""A mandatory source that fails acquisition must abort the run, not shorten the corpus.

Run B5 of the PDCD1 baseline lost 86% of its CT.gov universe to one timed-out query and
still produced a plausible partial result: the first failure blacklisted the source, the
eight modality queries behind it were never issued, and 527 of ~2,900 trials went on to
identity and scoring. These tests pin the two halves of the fix -- retry the query rather
than surrender its source, and refuse to score a run whose mandatory source failed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import yaml

from bve.se.discovery.orchestrator import AdapterResult, DiscoveryOrchestrator
from bve.se.schemas.contracts import (
    BuyerProblemV2,
    CandidateHit,
    RunStatus,
    SearchOutcome,
)


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        {
            "schema_version": "se_buyer_problem_v2",
            "problem_id": "test_fail_closed",
            "version": "1.0.0",
            "buyer": {
                "buyer_id": "b",
                "name": "B",
                "as_of_date": "2026-08-20",
            },
            "strategic_gap": {
                "therapeutic_areas": ["oncology"],
                "indications": [],
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": "PDCD1", "label": "PDCD1", "aliases": []}],
                },
                "modalities": ["MONOCLONAL_ANTIBODY", "VACCINE", "PEPTIDE"],
                "required_biology": [],
                "capability_constraints": {},
                "evidence_floor": {
                    "minimum_stage": "PHASE_1",
                    "human_poc_required": True,
                    "required_evidence_types": ["HUMAN_CLINICAL_RESULT"],
                },
                "clinical_effect_bar": {},
                "acceptable_deal_routes": ["LICENSE"],
                "geographic_rights_requirements": [],
                "missing_evidence_policy": "REVIEW",
            },
            "output": {"landscape_mode": "SEPARATE", "group_by": "COHORT"},
            "ranking_cohort_required": True,
        }
    )


def _hit(name: str) -> CandidateHit:
    return CandidateHit(
        hit_id=f"hit:{name}",
        source="clinicaltrials_gov",
        source_document_id=f"doc:{name}",
        query="q",
        asset_name=name,
        trial_id=f"NCT{abs(hash(name)) % 10**8:08d}",
        provisional_identity_key=name.casefold(),
        retrieved_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        applicable_as_of_date=date(2026, 8, 20),
    )


class _ScriptedAdapter:
    """A CT.gov stand-in whose Nth query fails a configurable number of times."""

    source_name = "clinicaltrials_gov"
    mandatory = True

    def __init__(self, *, fail_on: str, failures: int) -> None:
        self.fail_on = fail_on
        self.failures_remaining = failures
        self.queries_seen: list[str] = []
        self.last_page_count = 1

    def search(self, query, *, as_of_date) -> AdapterResult:
        self.queries_seen.append(query.query)
        if self.fail_on in query.query and self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise TimeoutError("Read timed out. (read timeout=30)")
        return AdapterResult(hits=[_hit(query.query[:24])], outcome=SearchOutcome.SUCCESS)


def _orchestrator(adapter, **kwargs) -> DiscoveryOrchestrator:
    defaults = {
        "max_passes": 2,
        "required_zero_growth_passes": 2,
        "retry_backoff_seconds": 0.0,
        "declared_mandatory_sources": ["clinicaltrials_gov"],
    }
    defaults.update(kwargs)
    return DiscoveryOrchestrator([adapter], **defaults)


def _run(orchestrator):
    return orchestrator.run(
        _problem(),
        run_id="run:test",
        code_version="test",
        normalization_version="test",
    )


def test_permanent_query_failure_makes_the_run_unscoreable() -> None:
    """A query that fails every retry: source FAILED, run INCOMPLETE and fatal."""

    adapter = _ScriptedAdapter(fail_on="MONOCLONAL_ANTIBODY", failures=99)
    result = _run(_orchestrator(adapter, query_attempts=3, source_failure_threshold=1))

    manifest = result.manifest
    assert manifest.source_status["clinicaltrials_gov"] is SearchOutcome.FAILED
    assert manifest.status is RunStatus.INCOMPLETE
    # The whole point: --allow-incomplete may not waive this.
    assert manifest.fatal_reasons, "a failed mandatory source must be fatal, not merely incomplete"
    assert not manifest.scoreable
    assert any("clinicaltrials_gov" in reason for reason in manifest.fatal_reasons)


def test_a_failed_query_does_not_abandon_the_rest_of_the_plan() -> None:
    """The B5 defect itself: queries behind the failure must still be issued."""

    adapter = _ScriptedAdapter(fail_on="MONOCLONAL_ANTIBODY", failures=99)
    _run(_orchestrator(adapter, query_attempts=1, source_failure_threshold=3))

    issued = {q for q in adapter.queries_seen}
    assert any("VACCINE" in q for q in issued), "queries after the failure were dropped"
    assert any("PEPTIDE" in q for q in issued), "queries after the failure were dropped"


def test_transient_failure_recovers_on_retry_and_the_union_is_complete() -> None:
    """One timeout, then success: full plan, complete deduped union, run scoreable."""

    adapter = _ScriptedAdapter(fail_on="MONOCLONAL_ANTIBODY", failures=1)
    result = _run(_orchestrator(adapter, query_attempts=3, source_failure_threshold=1))

    manifest = result.manifest
    assert manifest.source_status["clinicaltrials_gov"] is SearchOutcome.SUCCESS
    assert not manifest.fatal_reasons
    assert manifest.scoreable

    # All three modality queries contributed, and the retry did not duplicate a hit.
    modalities = {"MONOCLONAL_ANTIBODY", "VACCINE", "PEPTIDE"}
    for modality in modalities:
        assert any(modality in attempt.query for attempt in result.attempts)
    trial_ids = [hit.trial_id for hit in result.hits]
    assert len(trial_ids) == len(set(trial_ids)), "retry duplicated a trial into the union"

    retried = [a for a in result.attempts if "MONOCLONAL_ANTIBODY" in a.query]
    assert retried and retried[0].attempts_made == 2, "the retry was not recorded in the ledger"
    assert retried[0].outcome is SearchOutcome.SUCCESS


def test_query_attempts_must_be_positive() -> None:
    with pytest.raises(ValueError):
        DiscoveryOrchestrator([_ScriptedAdapter(fail_on="x", failures=0)], query_attempts=0)


class TestTheCLIRefusesToPromoteAFailedAcquisition:
    """--allow-incomplete waives a declared blind spot; it may not waive a failure."""

    @staticmethod
    def _result(*, fatal: list[str]):
        from bve.se.pipeline import SESearchResult
        from bve.se.schemas.contracts import RunManifest

        reasons = ["mandatory source failures: clinicaltrials_gov (1 queries failed)"]
        return SESearchResult(
            problem_id="test_fail_closed",
            run_manifest=RunManifest(
                run_id="run:test",
                problem_id="test_fail_closed",
                problem_version="1.0.0",
                as_of_date=date(2026, 8, 20),
                started_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                completed_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                code_version="test",
                normalization_version="test",
                status=RunStatus.INCOMPLETE,
                incomplete_reasons=reasons,
                fatal_reasons=fatal,
            ),
        )

    def test_a_failed_mandatory_source_exits_three_even_with_allow_incomplete(
        self, tmp_path, capsys
    ) -> None:
        from unittest import mock

        from bve.cli import se_search

        problem = tmp_path / "p.yaml"
        problem.write_text(yaml.safe_dump(_problem().model_dump(mode="json")))
        out = tmp_path / "result.json"
        result = self._result(
            fatal=["mandatory source failures: clinicaltrials_gov (1 queries failed)"]
        )

        with mock.patch.object(se_search, "run_landscape_search", lambda *a, **k: result):
            code = se_search.main(
                ["--problem", str(problem), "--allow-incomplete", "--output", str(out)]
            )

        assert code == 3, "a failed mandatory source must not be waivable"
        err = capsys.readouterr().err
        assert "UNSCOREABLE" in err
        assert "--allow-incomplete cannot waive" in err

    def test_an_unconfigured_mandatory_source_is_still_waivable(self, tmp_path) -> None:
        """The baseline legitimately runs with 7 unbuilt connectors; that must still pass."""

        from unittest import mock

        from bve.cli import se_search

        problem = tmp_path / "p.yaml"
        problem.write_text(yaml.safe_dump(_problem().model_dump(mode="json")))
        out = tmp_path / "result.json"
        result = self._result(fatal=[])

        with mock.patch.object(se_search, "run_landscape_search", lambda *a, **k: result):
            code = se_search.main(
                ["--problem", str(problem), "--allow-incomplete", "--output", str(out)]
            )

        assert code == 0
