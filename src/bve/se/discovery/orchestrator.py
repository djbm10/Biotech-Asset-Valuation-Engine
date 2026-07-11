"""Iterative discovery orchestration with explicit coverage and convergence semantics."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field

from bve.se.discovery.query import compile_problem_queries
from bve.se.schemas.contracts import (
    BuyerProblemV2,
    CandidateHit,
    CompiledQuery,
    CoveragePass,
    RunManifest,
    RunStatus,
    SearchAttempt,
    SearchOutcome,
    SourceDocument,
)


class AdapterResult(BaseModel):
    hits: list[CandidateHit] = Field(default_factory=list)
    outcome: SearchOutcome
    error: str | None = None
    snapshot_ids: list[str] = Field(default_factory=list)
    discovered_aliases: list[str] = Field(default_factory=list)
    follow_up_queries: list[str] = Field(default_factory=list)
    source_documents: list[SourceDocument] = Field(default_factory=list)


class SourceAdapter(Protocol):
    source_name: str
    mandatory: bool

    def search(self, query: CompiledQuery, *, as_of_date) -> AdapterResult:
        ...


class DiscoveryResult(BaseModel):
    hits: list[CandidateHit]
    attempts: list[SearchAttempt]
    manifest: RunManifest
    source_documents: list[SourceDocument] = Field(default_factory=list)


def _stable_id(prefix: str, *parts: str) -> str:
    value = "\x1f".join(parts)
    return f"{prefix}:{hashlib.sha256(value.encode()).hexdigest()[:20]}"


class DiscoveryOrchestrator:
    """Search all declared sources until convergence or a declared safety limit."""

    def __init__(
        self,
        adapters: Sequence[SourceAdapter],
        *,
        max_passes: int = 8,
        max_queries: int = 5000,
        required_zero_growth_passes: int = 2,
        declared_mandatory_sources: Sequence[str] | None = None,
    ) -> None:
        if max_passes < required_zero_growth_passes:
            raise ValueError("max_passes must allow the configured zero-growth convergence window")
        self.adapters = list(adapters)
        self.max_passes = max_passes
        self.max_queries = max_queries
        self.required_zero_growth_passes = required_zero_growth_passes
        self.declared_mandatory_sources = list(declared_mandatory_sources or [])

    def run(
        self,
        problem: BuyerProblemV2,
        *,
        run_id: str,
        code_version: str,
        normalization_version: str,
        extractor_versions: dict[str, str] | None = None,
    ) -> DiscoveryResult:
        queue = list(compile_problem_queries(problem))
        known_query_strings: set[str] = {query.query for query in queue}
        seen_queries: set[tuple[int, str, str]] = set()
        seen_hits: dict[str, CandidateHit] = {}
        attempts: list[SearchAttempt] = []
        coverage: list[CoveragePass] = []
        source_status: dict[str, SearchOutcome] = {}
        failed_sources: set[str] = set()
        snapshot_ids: list[str] = []
        source_documents: dict[str, SourceDocument] = {}
        zero_growth_passes = 0
        limit_reason: str | None = None

        for pass_number in range(1, self.max_passes + 1):
            pass_queries = list({query.query: query for query in queue}.values())
            queue = []
            new_hit_count = 0
            new_aliases: set[str] = set()
            source_contributions: dict[str, int] = {}

            for query in pass_queries:
                for adapter in self.adapters:
                    if adapter.source_name in failed_sources:
                        continue
                    key = (pass_number, adapter.source_name, query.query)
                    if key in seen_queries:
                        continue
                    if len(seen_queries) >= self.max_queries:
                        limit_reason = f"maximum query attempts reached ({self.max_queries})"
                        break
                    seen_queries.add(key)
                    started = datetime.now(timezone.utc)
                    try:
                        result = adapter.search(query, as_of_date=problem.buyer.as_of_date)
                    except Exception as exc:  # adapters are an external boundary
                        result = AdapterResult(outcome=SearchOutcome.FAILED, error=str(exc))
                    previous_outcome = source_status.get(adapter.source_name)
                    source_status[adapter.source_name] = _aggregate_source_outcome(
                        previous_outcome, result.outcome
                    )
                    if result.outcome == SearchOutcome.FAILED:
                        failed_sources.add(adapter.source_name)
                    snapshot_ids.extend(result.snapshot_ids)
                    for document in result.source_documents:
                        source_documents.setdefault(document.document_id, document)
                    before = len(seen_hits)
                    for hit in result.hits:
                        seen_hits.setdefault(hit.hit_id, hit)
                    added = len(seen_hits) - before
                    new_hit_count += added
                    source_contributions[adapter.source_name] = (
                        source_contributions.get(adapter.source_name, 0) + added
                    )
                    new_aliases.update(result.discovered_aliases)
                    attempts.append(
                        SearchAttempt(
                            attempt_id=_stable_id(
                                "attempt", run_id, str(pass_number), adapter.source_name, query.query
                            ),
                            run_id=run_id,
                            pass_number=pass_number,
                            source=adapter.source_name,
                            query=query.query,
                            aliases_searched=query.aliases,
                            outcome=result.outcome,
                            candidates_found=len(result.hits),
                            unique_candidates_added=added,
                            error=result.error,
                            retrieval_date=started,
                            applicable_as_of_date=problem.buyer.as_of_date,
                            snapshot_ids=result.snapshot_ids,
                        )
                    )
                    for follow_up in result.follow_up_queries:
                        if follow_up in known_query_strings:
                            continue
                        known_query_strings.add(follow_up)
                        queue.append(
                            CompiledQuery(
                                query_id=_stable_id("query", follow_up),
                                query=follow_up,
                                aliases=result.discovered_aliases,
                                expansion_depth=query.expansion_depth + 1,
                            )
                        )
                if limit_reason:
                    break

            coverage.append(
                CoveragePass(
                    pass_number=pass_number,
                    new_mentions=new_hit_count,
                    new_provisional_identities=new_hit_count,
                    new_aliases=len(new_aliases),
                    unresolved_mentions=0,
                    remaining_frontier=[query.query for query in queue],
                    source_unique_contributions=source_contributions,
                )
            )
            if limit_reason:
                break
            if new_hit_count == 0 and not queue:
                zero_growth_passes += 1
                # Re-run the original compiled frontier to prove a second complete no-growth pass.
                if zero_growth_passes < self.required_zero_growth_passes:
                    queue = list(compile_problem_queries(problem))
            else:
                zero_growth_passes = 0
            if zero_growth_passes >= self.required_zero_growth_passes:
                break
        else:
            limit_reason = f"maximum discovery passes reached ({self.max_passes})"

        mandatory_failures = [
            adapter.source_name
            for adapter in self.adapters
            if adapter.mandatory
            and source_status.get(adapter.source_name) not in {
                SearchOutcome.SUCCESS,
                SearchOutcome.NO_EVIDENCE_FOUND,
            }
        ]
        configured_sources = {adapter.source_name for adapter in self.adapters}
        missing_mandatory = sorted(set(self.declared_mandatory_sources) - configured_sources)
        incomplete_reasons: list[str] = []
        if limit_reason:
            incomplete_reasons.append(limit_reason)
        if mandatory_failures:
            incomplete_reasons.append(
                "mandatory source failures: " + ", ".join(sorted(mandatory_failures))
            )
        if missing_mandatory:
            incomplete_reasons.append(
                "mandatory sources not configured: " + ", ".join(missing_mandatory)
            )
        if zero_growth_passes < self.required_zero_growth_passes:
            incomplete_reasons.append("discovery did not complete two zero-growth passes")
        status = RunStatus.INCOMPLETE if incomplete_reasons else RunStatus.CONVERGED
        manifest = RunManifest(
            run_id=run_id,
            problem_id=problem.problem_id,
            problem_version=problem.version,
            as_of_date=problem.buyer.as_of_date,
            started_at=attempts[0].retrieval_date if attempts else datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            code_version=code_version,
            extractor_versions=extractor_versions or {},
            normalization_version=normalization_version,
            source_status=source_status,
            query_log_ids=[attempt.attempt_id for attempt in attempts],
            evidence_snapshot_ids=list(dict.fromkeys(snapshot_ids)),
            coverage_passes=coverage,
            known_blind_spots=[],
            status=status,
            incomplete_reasons=incomplete_reasons,
        )
        return DiscoveryResult(
            hits=list(seen_hits.values()),
            attempts=attempts,
            manifest=manifest,
            source_documents=list(source_documents.values()),
        )


def _aggregate_source_outcome(
    previous: SearchOutcome | None, current: SearchOutcome
) -> SearchOutcome:
    """Aggregate per-query outcomes so a later empty query cannot erase earlier success."""

    if previous is None:
        return current
    if previous == SearchOutcome.FAILED and current == SearchOutcome.SUCCESS:
        return SearchOutcome.PARTIAL
    if previous == SearchOutcome.SUCCESS and current == SearchOutcome.FAILED:
        return SearchOutcome.PARTIAL
    if previous == SearchOutcome.PARTIAL or current == SearchOutcome.PARTIAL:
        return SearchOutcome.PARTIAL
    if previous == SearchOutcome.SUCCESS or current == SearchOutcome.SUCCESS:
        return SearchOutcome.SUCCESS
    if previous == SearchOutcome.FAILED or current == SearchOutcome.FAILED:
        return SearchOutcome.FAILED
    return SearchOutcome.NO_EVIDENCE_FOUND


def unique_provisional_identities(hits: Iterable[CandidateHit]) -> set[str]:
    return {hit.provisional_identity_key for hit in hits}
