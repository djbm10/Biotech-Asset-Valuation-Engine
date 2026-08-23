"""Stage telemetry: a run should say what it is doing while it does it.

Diagnosing whether a long run was hung, re-fetching, or simply slow took hours of
forensics -- strace, socket byte counters, snapshot mtimes -- because the pipeline
emitted nothing between "started" and "finished". These tests pin the counters that
would have answered it at a glance, and pin that emitting them is opt-in so library
callers stay silent.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from bve.se.telemetry import StageTelemetry


def _telemetry() -> tuple[StageTelemetry, list[str]]:
    lines: list[str] = []
    return StageTelemetry(emit=lines.append), lines


class TestAStageReportsItsWorkAndItsCost:
    def test_a_stage_emits_its_counters_and_elapsed_time(self):
        telemetry, lines = _telemetry()
        with telemetry.stage("CTGOV") as stage:
            stage.count(records=2908, cache_hits=2908, live_fetches=0)

        assert len(lines) == 1
        assert lines[0].startswith("CTGOV: ")
        assert "2908 records" in lines[0]
        assert "2908 cache hits" in lines[0]
        assert "0 live fetches" in lines[0]
        # Elapsed is what distinguishes "slow" from "hung"; it is never optional.
        assert lines[0].rstrip().endswith("s")

    def test_counters_accumulate_across_calls_within_a_stage(self):
        telemetry, lines = _telemetry()
        with telemetry.stage("EXTRACTION") as stage:
            stage.count(claims=3)
            stage.count(claims=4, facts=1)

        assert "7 claims" in lines[0]
        assert "1 facts" in lines[0]

    def test_a_stage_that_raises_still_reports_what_it_had_done(self):
        """The failing run is the one whose progress you most need to see."""

        telemetry, lines = _telemetry()
        try:
            with telemetry.stage("IDENTITY") as stage:
                stage.count(hits=41)
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        assert "41 hits" in lines[0]
        assert "failed" in lines[0]

    def test_no_emitter_means_no_output_and_no_error(self):
        """Library callers and tests must not be forced to become noisy."""

        telemetry = StageTelemetry()
        with telemetry.stage("SCORING") as stage:
            stage.count(candidates=12)
        assert telemetry.stages[0].counters == {"candidates": 12}


class TestDiscoveryCountersComeFromTheRunItself:
    def test_search_attempts_are_summarized_per_source(self):
        from bve.se.schemas.contracts import SearchAttempt, SearchOutcome
        from bve.se.telemetry import summarize_attempts

        def attempt(source: str, found: int, added: int, snapshots: int) -> SearchAttempt:
            return SearchAttempt(
                attempt_id=f"a{found}{added}{source}",
                run_id="r",
                pass_number=1,
                source=source,
                query="q",
                outcome=SearchOutcome.SUCCESS,
                candidates_found=found,
                unique_candidates_added=added,
                retrieval_date=datetime.now(timezone.utc),
                applicable_as_of_date=date(2026, 8, 23),
                snapshot_ids=[f"snapshot:{source}{i}" for i in range(snapshots)],
            )

        summary = summarize_attempts(
            [
                attempt("clinicaltrials_gov", 10, 10, 3),
                attempt("clinicaltrials_gov", 4, 1, 3),
                attempt("pubmed", 2, 2, 1),
            ]
        )

        assert summary["clinicaltrials_gov"]["queries"] == 2
        assert summary["clinicaltrials_gov"]["candidates"] == 14
        assert summary["clinicaltrials_gov"]["unique_candidates"] == 11
        # Distinct payloads examined, not the sum of per-query snapshot lists: the same
        # trial retrieved by six queries is one record, and counting it six times is
        # exactly the illusion that made the corpus look 6x larger than it was.
        assert summary["clinicaltrials_gov"]["records"] == 3
        assert summary["pubmed"]["queries"] == 1
