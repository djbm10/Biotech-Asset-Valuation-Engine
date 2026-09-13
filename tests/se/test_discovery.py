from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from bve.se.discovery.orchestrator import AdapterResult, DiscoveryOrchestrator
from bve.se.discovery.query import compile_problem_queries
from bve.se.discovery.seeding import SeedProvenance
from bve.se.schemas.contracts import (
    BuyerProblemV2,
    CandidateHit,
    RunStatus,
    SearchOutcome,
)


ROOT = Path(__file__).resolve().parents[2]


def _problem(name: str = "cd19_or_bcma_tce.yaml") -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        yaml.safe_load((ROOT / "examples/configs/se/benchmarks" / name).read_text())
    )


class FakeAdapter:
    source_name = "fake_source"
    mandatory = True

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def search(self, query, *, as_of_date):
        self.calls += 1
        if self.fail:
            return AdapterResult(outcome=SearchOutcome.FAILED, error="offline")
        hit = CandidateHit(
            hit_id="hit:asset-a",
            source=self.source_name,
            source_document_id="doc:1",
            query=query.query,
            asset_name="Asset A",
            target_terms=query.target_ids,
            modality_terms=query.modality_ids,
            provisional_identity_key="asset a",
            retrieved_at=datetime.now(timezone.utc),
            applicable_as_of_date=as_of_date,
        )
        return AdapterResult(hits=[hit], outcome=SearchOutcome.SUCCESS, snapshot_ids=["snap:1"])


def test_query_compiler_keeps_any_targets_separate() -> None:
    problem = _problem()
    queries = compile_problem_queries(problem)
    assert queries
    assert all(len(query.target_ids) == 1 for query in queries)
    assert {target for query in queries for target in query.target_ids} == {"CD19", "BCMA"}


def test_exact_combination_queries_include_both_targets() -> None:
    queries = compile_problem_queries(_problem("cd19_bcma_dual_target.yaml"))
    assert queries
    # Target-vocabulary queries carry the whole conjunction. Asset-seeded queries do not:
    # a seed is one drug the authority ties to one target, so binding it to both would
    # claim a dual-target association the authority never asserted.
    combination = [
        query
        for query in queries
        if query.seed_provenance == SeedProvenance.TARGET_VOCABULARY
    ]
    assert combination
    assert all(set(query.target_ids) == {"CD19", "BCMA"} for query in combination)
    assert all(
        len(query.target_ids) == 1
        for query in queries
        if query.seed_provenance == SeedProvenance.AUTHORITY_SEEDED_ASSET
    )


def test_orchestrator_converges_after_two_complete_zero_growth_passes() -> None:
    adapter = FakeAdapter()
    result = DiscoveryOrchestrator([adapter], max_passes=4, max_queries=100).run(
        _problem(), run_id="run:1", code_version="test", normalization_version="test"
    )
    assert result.manifest.status == RunStatus.CONVERGED
    assert len(result.hits) == 1
    assert len(result.manifest.coverage_passes) >= 3
    assert adapter.calls > len(compile_problem_queries(_problem()))


def test_mandatory_source_failure_forces_incomplete() -> None:
    result = DiscoveryOrchestrator([FakeAdapter(fail=True)], max_passes=3).run(
        _problem(), run_id="run:2", code_version="test", normalization_version="test"
    )
    assert result.manifest.status == RunStatus.INCOMPLETE
    assert any("mandatory source failures" in reason for reason in result.manifest.incomplete_reasons)


def test_query_limit_is_never_reported_as_convergence() -> None:
    result = DiscoveryOrchestrator([FakeAdapter()], max_passes=4, max_queries=1).run(
        _problem(), run_id="run:3", code_version="test", normalization_version="test"
    )
    assert result.manifest.status == RunStatus.INCOMPLETE
    assert any("maximum query attempts" in reason for reason in result.manifest.incomplete_reasons)


class TestEnablingASourceDoesNotStarveTheSourcesAlreadyEnabled:
    """The query limit bounds each source's own depth, not a pool they compete for.

    ``max_queries`` counted ``(pass, source, query)`` tuples globally while the adapter loop sat
    inside the query loop, so exhausting the pool truncated every source to the same prefix of
    the query plan. Adding a source therefore silently took retrieval depth away from the
    sources already configured: the M12 combined evaluation gave each of eight sources 625
    queries where the same plan had given each of three sources 955, and PubMed returned 3768
    fewer records than it had in the runs the comparison was being made against. The run
    reported success and the scores stayed comparable, so the loss showed up as 78 apparently
    missing identity edges -- a conclusion about the newly added families that was really an
    artifact of starving PubMed.

    A source's depth has to depend on that source alone, or no multi-source result can be
    attributed to the sources in it.
    """

    class _CountingAdapter:
        mandatory = True

        def __init__(self, source_name: str) -> None:
            self.source_name = source_name
            self.calls = 0

        def search(self, query, *, as_of_date):
            self.calls += 1
            hit = CandidateHit(
                hit_id=f"hit:{self.source_name}",
                source=self.source_name,
                source_document_id=f"doc:{self.source_name}",
                query=query.query,
                asset_name=f"Asset {self.source_name}",
                target_terms=query.target_ids,
                modality_terms=query.modality_ids,
                provisional_identity_key=f"asset {self.source_name}",
                retrieved_at=datetime.now(timezone.utc),
                applicable_as_of_date=as_of_date,
            )
            return AdapterResult(
                hits=[hit], outcome=SearchOutcome.SUCCESS, snapshot_ids=["snap:1"]
            )

    def _run(self, adapters, limit: int):
        return DiscoveryOrchestrator(adapters, max_passes=4, max_queries=limit).run(
            _problem(),
            run_id="run:budget",
            code_version="test",
            normalization_version="test",
        )

    def test_a_second_source_does_not_reduce_the_first_sources_queries(self) -> None:
        # The limit has to be low enough to bind before convergence does, or both readings
        # agree trivially and the test proves nothing.
        alone = self._CountingAdapter("source_a")
        self._run([alone], 4)

        together_a = self._CountingAdapter("source_a")
        together_b = self._CountingAdapter("source_b")
        self._run([together_a, together_b], 4)

        assert together_a.calls == alone.calls, (
            "adding source_b changed how deeply source_a was searched; the limit is being "
            "shared rather than applied per source"
        )

    def test_each_source_may_reach_the_limit_independently(self) -> None:
        # Three sources at a binding limit each get the full allowance, rather than a third of
        # it. The pooled implementation produced [2, 2, 1] here -- unequal as well as short,
        # because the leftover went to whichever adapter the loop reached first.
        adapters = [self._CountingAdapter(f"source_{i}") for i in range(3)]
        self._run(adapters, 3)
        assert [adapter.calls for adapter in adapters] == [3, 3, 3]

    def test_depth_per_source_is_independent_of_how_many_sources_there_are(self) -> None:
        solo = self._CountingAdapter("source_a")
        self._run([solo], 3)
        many = [self._CountingAdapter(f"source_{i}") for i in range(5)]
        self._run(many, 3)
        assert {adapter.calls for adapter in many} == {solo.calls}

    def test_a_single_source_is_bounded_exactly_as_before(self) -> None:
        # The frozen runs all sat far below the limit, so the fix must not move them: with one
        # source the pooled and per-source readings are identical by construction.
        adapter = self._CountingAdapter("source_a")
        result = self._run([adapter], 3)
        assert adapter.calls == 3
        assert result.manifest.status == RunStatus.INCOMPLETE
        assert any(
            "maximum query attempts" in reason
            for reason in result.manifest.incomplete_reasons
        )


def test_later_empty_query_cannot_erase_earlier_source_success() -> None:
    adapter = FakeAdapter()
    result = DiscoveryOrchestrator([adapter], max_passes=4, max_queries=100).run(
        _problem(), run_id="run:aggregate", code_version="test", normalization_version="test"
    )
    assert result.manifest.source_status["fake_source"] == SearchOutcome.SUCCESS
