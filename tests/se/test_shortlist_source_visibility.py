"""Productization step 4 — the reader can see which corpus the shortlist came from.

The shortlist told a reader everything about each asset and nothing about the run that found
them. That is the one omission with real consequences: a run that lost a mandatory source
mid-acquisition is short an unknown number of records, and a shortlist rendered from it looks
exactly like a shortlist rendered from a clean sweep. `RunManifest` has carried the
distinction since B6 --- `NOT_CONFIGURED` (a declared blind spot, waivable) versus `FAILED`
(unscoreable) --- and the audit memo prints it. The reader's view did not.

So these tests pin what the shortlist must say about its own corpus, and pin that it says it
*before* the assets rather than in a footnote. They also pin what it must not do: invent a
source-family attribution for documents, which the run does not record.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist, render_shortlist
from bve.se.schemas.contracts import (
    RunManifest,
    RunStatus,
    SearchAttempt,
    SearchOutcome,
    SourceDocument,
    SourceTier,
)

NOW = datetime(2026, 9, 17, tzinfo=timezone.utc)


def _document(number: int, publisher: str) -> SourceDocument:
    return SourceDocument(
        document_id=f"document:{number:020d}",
        source_url=f"https://example.invalid/{number}",
        publisher=publisher,
        document_type="registry_record",
        publication_date=date(2024, 5, 1),
        retrieval_date=NOW,
        content_hash=f"hash{number:04d}",
        source_tier=SourceTier.REGISTRY,
    )


def _attempt(
    number: int,
    source: str,
    outcome: SearchOutcome,
    *,
    found: int = 0,
    added: int = 0,
    attempts_made: int = 1,
    error: str | None = None,
) -> SearchAttempt:
    return SearchAttempt(
        attempt_id=f"attempt:{number}",
        run_id="se:sources",
        pass_number=1,
        source=source,
        query=f"query {number}",
        outcome=outcome,
        candidates_found=found,
        unique_candidates_added=added,
        error=error,
        attempts_made=attempts_made,
        retrieval_date=NOW,
        applicable_as_of_date=date(2026, 9, 1),
    )


def _result(
    *,
    status: RunStatus = RunStatus.CONVERGED,
    incomplete_reasons: list[str] | None = None,
    fatal_reasons: list[str] | None = None,
    blind_spots: list[str] | None = None,
) -> SESearchResult:
    return SESearchResult(
        problem_id="problem_sources",
        run_manifest=RunManifest(
            run_id="se:sources",
            problem_id="problem_sources",
            problem_version="v2",
            as_of_date=date(2026, 9, 16),
            started_at=NOW,
            code_version="deadbeef",
            normalization_version="v1",
            status=status,
            incomplete_reasons=list(incomplete_reasons or []),
            fatal_reasons=list(fatal_reasons or []),
            known_blind_spots=list(blind_spots or []),
            source_status={
                "clinicaltrials_gov": SearchOutcome.SUCCESS,
                "pubmed": SearchOutcome.PARTIAL,
                "sec_edgar": SearchOutcome.NOT_CONFIGURED,
                "conference_ash": SearchOutcome.FAILED,
            },
        ),
        source_documents=[
            _document(1, "ClinicalTrials.gov"),
            _document(2, "ClinicalTrials.gov"),
            _document(3, "PubMed"),
        ],
        search_attempts=[
            _attempt(1, "clinicaltrials_gov", SearchOutcome.SUCCESS, found=40, added=12),
            _attempt(2, "clinicaltrials_gov", SearchOutcome.SUCCESS, found=8, added=1),
            _attempt(3, "pubmed", SearchOutcome.PARTIAL, found=5, added=5, attempts_made=3),
            _attempt(
                4,
                "conference_ash",
                SearchOutcome.FAILED,
                error="HTTP 503 after 5 attempts",
            ),
        ],
    )


class TestTheRunDescribesItsOwnCorpus:
    def test_every_declared_source_family_is_listed_with_its_outcome(self) -> None:
        sources = {source.family: source for source in build_shortlist(_result()).sources}
        assert set(sources) == {
            "clinicaltrials_gov",
            "pubmed",
            "sec_edgar",
            "conference_ash",
        }
        assert sources["clinicaltrials_gov"].outcome == "SUCCESS"
        # A declared blind spot and a broken source are different answers and stay different.
        assert sources["sec_edgar"].outcome == "NOT_CONFIGURED"
        assert sources["conference_ash"].outcome == "FAILED"

    def test_per_family_counts_come_from_the_attempts_that_were_made(self) -> None:
        sources = {source.family: source for source in build_shortlist(_result()).sources}
        ctgov = sources["clinicaltrials_gov"]
        assert (ctgov.queries, ctgov.candidates_found, ctgov.unique_candidates_added) == (2, 48, 13)
        assert sources["sec_edgar"].queries == 0

    def test_a_failed_source_carries_the_error_that_explains_it(self) -> None:
        sources = {source.family: source for source in build_shortlist(_result()).sources}
        assert sources["conference_ash"].errors == ("HTTP 503 after 5 attempts",)

    def test_documents_are_counted_by_publisher_not_by_an_invented_family_mapping(self) -> None:
        shortlist = build_shortlist(_result())
        assert shortlist.documents_by_publisher == {"ClinicalTrials.gov": 2, "PubMed": 1}
        # The run records no attempt->document mapping, so no source family claims a
        # document count it cannot support.
        assert all(source.documents is None for source in shortlist.sources)


class TestAnUnsoundCorpusIsImpossibleToMiss:
    def test_a_fatal_source_failure_is_stated_before_the_assets(self) -> None:
        rendered = render_shortlist(
            build_shortlist(
                _result(
                    status=RunStatus.INCOMPLETE,
                    incomplete_reasons=["conference_ash failed mid-acquisition"],
                    fatal_reasons=["conference_ash failed mid-acquisition"],
                )
            )
        )
        head = rendered.split("Counts:")[0]
        assert "UNSCOREABLE" in head
        assert "conference_ash failed mid-acquisition" in head

    def test_an_incomplete_run_says_so_even_when_nothing_failed_fatally(self) -> None:
        shortlist = build_shortlist(
            _result(
                status=RunStatus.INCOMPLETE,
                incomplete_reasons=["sec_edgar is not configured"],
                blind_spots=["sec_edgar"],
            )
        )
        assert shortlist.run_status == "INCOMPLETE"
        assert shortlist.blind_spots == ("sec_edgar",)
        rendered = render_shortlist(shortlist)
        assert "INCOMPLETE" in rendered
        assert "sec_edgar is not configured" in rendered
        # Not fatal, so it must not be dressed up as fatal.
        assert "UNSCOREABLE" not in rendered

    def test_a_clean_run_raises_no_alarm(self) -> None:
        rendered = render_shortlist(build_shortlist(_result()))
        assert "UNSCOREABLE" not in rendered
        assert "INCOMPLETE" not in rendered
        # But the sources are still shown: a reader should never have to ask.
        assert "clinicaltrials_gov" in rendered


class TestTheTwoViewsStillAgree:
    @pytest.mark.parametrize("status", [RunStatus.CONVERGED, RunStatus.INCOMPLETE])
    def test_the_json_view_carries_everything_the_human_view_asserts(
        self, status: RunStatus
    ) -> None:
        shortlist = build_shortlist(
            _result(
                status=status,
                incomplete_reasons=["sec_edgar is not configured"]
                if status is RunStatus.INCOMPLETE
                else [],
            )
        )
        payload = json.loads(json.dumps(shortlist.model_dump(mode="json")))
        assert payload["run_status"] == status.value
        assert {source["family"] for source in payload["sources"]} == {
            source.family for source in shortlist.sources
        }
