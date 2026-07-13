from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from bve.se.discovery.orchestrator import AdapterResult, DiscoveryOrchestrator
from bve.se.discovery.query import compile_problem_queries
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
    assert all(set(query.target_ids) == {"CD19", "BCMA"} for query in queries)


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


def test_later_empty_query_cannot_erase_earlier_source_success() -> None:
    adapter = FakeAdapter()
    result = DiscoveryOrchestrator([adapter], max_passes=4, max_queries=100).run(
        _problem(), run_id="run:aggregate", code_version="test", normalization_version="test"
    )
    assert result.manifest.source_status["fake_source"] == SearchOutcome.SUCCESS
