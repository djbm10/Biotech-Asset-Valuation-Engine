"""
Ingestion source-health reporting — test suite.

Validates that a run produces a per-source health record answering
"did SEC / FDA / news actually work, or silently return nothing?"

Verdict semantics:
  OK       fetched and processed normally
  NO_DATA  no records found, no failures (legitimately quiet window)
  DEGRADED some fetch failures, or an abnormally high unclassified rate
  FAILED   every fetch attempt raised
"""
from __future__ import annotations

from datetime import date

import pytest

from bve.ingestion.live_ingestion_runner import (
    IngestionRunResult,
    LiveIngestionRunner,
    RawIngestionItem,
    SourceHealth,
)
from bve.reporting.ingestion_health import (
    render_health_report,
    write_health_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(ticker: str = "RVMD", source_type: str = "sec_filing", text: str = "x") -> RawIngestionItem:
    return RawIngestionItem(
        ticker=ticker,
        text=text,
        source_type=source_type,
        source_url="https://sec.gov/test",
        published_date=date(2026, 6, 1),
    )


def _mlc(ticker="RVMD", primary_event="clinical_positive_ph3"):
    from dataclasses import dataclass

    @dataclass
    class _MLC:
        ticker: str
        primary_event: str
        direction: str
        phase_detected: str | None
        confidence: float
        combined_score_deltas: dict
        source_type: str
        raw_text: str
        match_reasons: list
        secondary_events: list
        severity_score: int

    return _MLC(
        ticker=ticker,
        primary_event=primary_event,
        direction="positive",
        phase_detected="Phase 3",
        confidence=0.85,
        combined_score_deltas={"asset_quality": 0.10},
        source_type="sec_filing",
        raw_text="x",
        match_reasons=["r"],
        secondary_events=[],
        severity_score=80,
    )


def _runner(*, sec=None, ctgov=None, fda=None, mlc_factory=None):
    return LiveIngestionRunner(
        sec_source=sec or (lambda t, p, lb: []),
        ctgov_source=ctgov or (lambda t, p, lb: []),
        fda_source=fda or (lambda t, p, lb: []),
        classifier=mlc_factory or (lambda text, ticker, source_type: _mlc(ticker=ticker)),
        materiality_est=lambda et, st, ch=None: _mat(),
        context_engine=lambda d, et, prof: dict(d),
        clusterer=lambda rec: "cluster-1",
        review_gate=lambda mat: False,
    )


def _mat(materiality: float = 0.75):
    from dataclasses import dataclass

    @dataclass
    class _Mat:
        materiality: float
        novelty: float = 0.8
        evidence_strength: float = 0.9

    return _Mat(materiality=materiality)


def _profiles():
    return ({"RVMD": {"ticker": "RVMD", "name": "Revolution Medicines"}}, {})


def _run(runner, tmp_path, dry_run=True, sources=None):
    from bve.ingestion.evidence_ledger import EvidenceLedger

    targets, acquirers = _profiles()
    return runner.run(
        targets=targets,
        acquirers=acquirers,
        ledger=EvidenceLedger(path=tmp_path / "ledger.jsonl"),
        as_of_date=date(2026, 6, 1),
        lookback_days=14,
        dry_run=dry_run,
        sources=sources,
    )


# ---------------------------------------------------------------------------
# Verdict logic (unit — SourceHealth in isolation)
# ---------------------------------------------------------------------------


class TestVerdict:
    def test_ok(self):
        h = SourceHealth(source_key="sec_filing", tickers_attempted=2,
                         records_fetched=3, records_classified=3)
        assert h.verdict == "OK"

    def test_no_data_when_quiet(self):
        h = SourceHealth(source_key="fda_website", tickers_attempted=2,
                         records_fetched=0, fetch_failures=0)
        assert h.verdict == "NO_DATA"

    def test_failed_when_all_fetches_raise(self):
        h = SourceHealth(source_key="news_article", tickers_attempted=2,
                         fetch_failures=2, records_fetched=0)
        assert h.verdict == "FAILED"

    def test_degraded_on_partial_failure(self):
        h = SourceHealth(source_key="sec_filing", tickers_attempted=3,
                         fetch_failures=1, records_fetched=2, records_classified=2)
        assert h.verdict == "DEGRADED"

    def test_degraded_on_high_unclassified_rate(self):
        h = SourceHealth(source_key="news_article", tickers_attempted=2,
                         records_fetched=10, records_classified=0, unclassified=10)
        assert h.verdict == "DEGRADED"

    def test_small_unclassified_sample_not_degraded(self):
        # A couple of unclassified records is not a classifier problem.
        h = SourceHealth(source_key="news_article", tickers_attempted=1,
                         records_fetched=2, records_classified=0, unclassified=2)
        assert h.verdict == "OK"

    def test_expected_sec_non_events_do_not_trigger_classifier_degradation(self):
        h = SourceHealth(
            source_key="sec_filing", tickers_attempted=2,
            records_fetched=10, records_classified=0, unclassified=10,
            expected_unclassified=10,
        )
        assert h.verdict == "OK"

    def test_degraded_on_partial_processing_failure(self):
        h = SourceHealth(
            source_key="sec_filing",
            tickers_attempted=1,
            records_fetched=2,
            records_classified=1,
            processing_failures=1,
        )
        assert h.verdict == "DEGRADED"

    def test_failed_when_every_fetched_item_fails_processing(self):
        h = SourceHealth(
            source_key="sec_filing",
            tickers_attempted=1,
            records_fetched=2,
            processing_failures=2,
        )
        assert h.verdict == "FAILED"


# ---------------------------------------------------------------------------
# Run-loop integration
# ---------------------------------------------------------------------------


class TestRunHealth:
    def test_result_has_source_health_for_each_active_source(self, tmp_path):
        result = _run(_runner(), tmp_path)
        assert set(result.source_health) == {"sec_filing", "clinicaltrials_gov", "fda_website"}

    def test_silent_source_is_no_data(self, tmp_path):
        # All three default sources return nothing → NO_DATA, not OK.
        result = _run(_runner(), tmp_path)
        assert result.source_health["fda_website"].verdict == "NO_DATA"

    def test_failing_source_is_failed_with_samples(self, tmp_path):
        def _boom(t, p, lb):
            raise RuntimeError("HTTP 503")

        result = _run(_runner(fda=_boom), tmp_path)
        fda = result.source_health["fda_website"]
        assert fda.verdict == "FAILED"
        assert fda.fetch_failures == fda.tickers_attempted
        assert any("503" in s for s in fda.failure_samples)

    def test_healthy_source_counts(self, tmp_path):
        def _sec(t, p, lb):
            return [_item(ticker=t), _item(ticker=t)]

        result = _run(_runner(sec=_sec), tmp_path, dry_run=True)
        sec = result.source_health["sec_filing"]
        assert sec.records_fetched == 2
        assert sec.records_classified == 2
        assert sec.verdict == "OK"

    def test_unclassified_attributed_to_source(self, tmp_path):
        def _sec(t, p, lb):
            return [_item(ticker=t) for _ in range(6)]

        result = _run(
            _runner(sec=_sec, mlc_factory=lambda text, ticker, source_type: _mlc(ticker=ticker, primary_event="unclassified")),
            tmp_path,
        )
        sec = result.source_health["sec_filing"]
        assert sec.records_fetched == 6
        assert sec.unclassified == 6
        assert sec.records_classified == 0
        assert sec.verdict == "DEGRADED"

    def test_item_failure_is_isolated_and_reported(self, tmp_path):
        def _sec(ticker, profile_data, lookback_days):  # noqa: ARG001
            return [
                _item(ticker=ticker, text="bad item"),
                _item(ticker=ticker, text="good item"),
            ]

        def _classify(text, ticker, source_type):  # noqa: ARG001
            if text == "bad item":
                raise RuntimeError("classifier exploded")
            return _mlc(ticker=ticker)

        result = _run(
            _runner(sec=_sec, mlc_factory=_classify),
            tmp_path,
            dry_run=False,
            sources=["sec"],
        )

        sec = result.source_health["sec_filing"]
        assert result.items_seen == 2
        assert result.items_classified == 1
        assert result.records_appended == 1
        assert result.processing_failures == 1
        assert "classifier exploded" in result.processing_failure_samples[0]
        assert sec.processing_failures == 1
        assert "classifier exploded" in sec.processing_failure_samples[0]
        assert sec.verdict == "DEGRADED"


class TestSourceConfiguration:
    def test_unknown_source_fails_fast(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown live ingestion source"):
            _run(_runner(), tmp_path, sources=["sec", "not-a-source"])

    def test_empty_source_list_fails_fast(self, tmp_path):
        with pytest.raises(ValueError, match="At least one live ingestion source"):
            _run(_runner(), tmp_path, sources=[])


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_result_constructs_without_source_health(self):
        r = IngestionRunResult(
            as_of_date=date(2026, 6, 1),
            lookback_days=14,
            items_seen=0,
            items_classified=0,
            records_appended=0,
            duplicates_skipped=0,
            unclassified_count=0,
            source_breakdown={},
            output_paths=[],
        )
        assert r.source_health == {}


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def _sample_result() -> IngestionRunResult:
    return IngestionRunResult(
        as_of_date=date(2026, 6, 1),
        lookback_days=14,
        items_seen=5,
        items_classified=3,
        records_appended=2,
        duplicates_skipped=1,
        unclassified_count=2,
        source_breakdown={"sec_filing": 5, "fda_website": 0},
        output_paths=[],
        source_health={
            "sec_filing": SourceHealth(
                source_key="sec_filing", tickers_attempted=3, records_fetched=5,
                records_classified=3, records_appended=2, duplicates_skipped=1,
                unclassified=2,
            ),
            "fda_website": SourceHealth(
                source_key="fda_website", tickers_attempted=3, fetch_failures=3,
                failure_samples=("PFE: HTTP 503",),
            ),
        },
    )


class TestRenderer:
    def test_render_contains_sources_and_verdicts(self):
        md = render_health_report(_sample_result())
        assert "sec_filing" in md
        assert "fda_website" in md
        assert "OK" in md
        assert "DEGRADED" in md or "FAILED" in md

    def test_render_includes_failure_samples(self):
        md = render_health_report(_sample_result())
        assert "503" in md

    def test_write_emits_md_and_json(self, tmp_path):
        paths = write_health_report(_sample_result(), tmp_path)
        assert (tmp_path / "ingestion_health.md").exists()
        assert (tmp_path / "ingestion_health.json").exists()
        assert any(str(p).endswith(".json") for p in paths)

    def test_json_is_machine_readable(self, tmp_path):
        import json

        write_health_report(_sample_result(), tmp_path)
        data = json.loads((tmp_path / "ingestion_health.json").read_text())
        assert data["sources"]["sec_filing"]["verdict"] == "OK"
        assert data["sources"]["fda_website"]["verdict"] == "FAILED"
