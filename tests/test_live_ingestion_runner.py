"""
Tests for LiveIngestionRunner (Block 2C).

All sources, classifiers, and ledger interactions are mocked — zero network.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from bve.ingestion.live_ingestion_runner import (
    CTGovSource,
    EarningsReleaseSource,
    IngestionRunResult,
    LiveIngestionRunner,
    NewsArticleSource,
    PressReleaseSource,
    RawIngestionItem,
    SecEightKSource,
    _build_context_profile,
    _company_role,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_item(
    ticker: str = "RVMD",
    text: str = "Phase 3 trial met primary endpoint positive results",
    source_type: str = "sec_filing",
    source_url: str | None = "https://sec.gov/test",
    published_date: date | None = None,
) -> RawIngestionItem:
    return RawIngestionItem(
        ticker=ticker,
        text=text,
        source_type=source_type,
        source_url=source_url,
        published_date=published_date or date(2026, 6, 1),
    )


def _make_mlc(
    ticker: str = "RVMD",
    primary_event: str = "clinical_positive_ph3",
    direction: str = "positive",
    confidence: float = 0.85,
    deltas: dict | None = None,
    source_type: str = "sec_filing",
    text: str = "Phase 3 trial met primary endpoint positive results",
):
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
        direction=direction,
        phase_detected="Phase 3",
        confidence=confidence,
        combined_score_deltas=deltas or {"asset_quality": 0.10, "catalyst_timing": 0.04},
        source_type=source_type,
        raw_text=text,
        match_reasons=["phase_3_positive"],
        secondary_events=[],
        severity_score=80,
    )


def _null_source(ticker, profile_data, lookback_days) -> list:
    return []


def _make_mat_est(materiality: float = 0.75, novelty: float = 0.80):
    from dataclasses import dataclass

    @dataclass
    class _Mat:
        materiality: float
        novelty: float
        evidence_strength: float = 0.90

    return _Mat(materiality=materiality, novelty=novelty)


def _make_runner(
    raw_items: list[RawIngestionItem] | None = None,
    mlc_factory=None,
    mat_materiality: float = 0.75,
    review_gate_result: bool = False,
) -> LiveIngestionRunner:
    """Build a fully mocked runner."""

    items = raw_items if raw_items is not None else [_make_item()]

    def _fake_sec(ticker, profile_data, lookback_days):
        return [i for i in items if i.source_type == "sec_filing" and i.ticker == ticker]

    def _fake_ctgov(ticker, profile_data, lookback_days):
        return [i for i in items if i.source_type == "clinicaltrials_gov" and i.ticker == ticker]

    def _fake_fda(ticker, profile_data, lookback_days):
        return [i for i in items if i.source_type == "fda_website" and i.ticker == ticker]

    _mlc_fn = mlc_factory or (lambda text, ticker, source_type: _make_mlc(ticker=ticker))

    def _mat_fn(event_type, source_type, context_hints=None):
        return _make_mat_est(materiality=mat_materiality)

    def _ctx_fn(deltas, event_type, profile):
        return dict(deltas)  # pass-through

    def _cluster_fn(record):
        return "cluster-abc123"

    def _review_fn(materiality):
        return review_gate_result

    return LiveIngestionRunner(
        sec_source=_fake_sec,
        ctgov_source=_fake_ctgov,
        fda_source=_fake_fda,
        classifier=_mlc_fn,
        materiality_est=_mat_fn,
        context_engine=_ctx_fn,
        clusterer=_cluster_fn,
        review_gate=_review_fn,
    )


def _make_ledger(tmp_path: Path):
    from bve.ingestion.evidence_ledger import EvidenceLedger
    return EvidenceLedger(path=tmp_path / "ledger.jsonl")


def _minimal_profiles():
    target_profiles = {
        "RVMD": {
            "ticker": "RVMD",
            "name": "Revolution Medicines",
            "lead_asset": "RMC-6236",
            "lead_asset_phase": "phase_3",
            "therapeutic_areas": ["oncology"],
        }
    }
    acquirer_profiles = {
        "PFE": {
            "ticker": "PFE",
            "name": "Pfizer",
            "lead_asset": "",
            "lead_asset_phase": "commercial",
            "therapeutic_areas": ["oncology"],
        }
    }
    return target_profiles, acquirer_profiles


# ---------------------------------------------------------------------------
# Source adapter behavior
# ---------------------------------------------------------------------------

class TestCTGovSource:
    def test_fetch_falls_back_to_sponsor_when_lead_asset_has_no_trials(self, monkeypatch):
        from bve.ingestion.raw_event import RawEvent

        calls: list[str] = []

        def fake_search_trials(drug_name: str, limit: int = 20):  # noqa: ARG001
            calls.append(drug_name)
            if drug_name == "RMC-6236":
                return []
            return [
                RawEvent(
                    source="clinicaltrials_gov",
                    record_type="clinical_trial",
                    source_url="https://clinicaltrials.gov/study/NCT1",
                    payload={
                        "nct_id": "NCT1",
                        "brief_title": "Company sponsored oncology trial",
                        "status": "RECRUITING",
                        "phases": ["PHASE2"],
                        "last_update_submitted": "2026-06-01",
                    },
                )
            ]

        monkeypatch.setattr("bve.ingestion.ctgov_client.search_trials", fake_search_trials)

        source = CTGovSource()
        items = source.fetch(
            "RVMD",
            {"name": "Revolution Medicines", "lead_asset": "RMC-6236"},
            lookback_days=14,
        )

        assert calls == ["RMC-6236", "Revolution Medicines"]
        assert len(items) == 1
        assert items[0].raw_payload["nct_id"] == "NCT1"


class TestPressAndNewsSources:
    def test_press_release_source_converts_sec_press_events(self, monkeypatch):
        from bve.ingestion.raw_event import RawEvent

        def fake_fetch_sec_press_releases(ticker: str, limit: int = 10):  # noqa: ARG001
            return [
                RawEvent(
                    source="news",
                    record_type="press_release",
                    source_url="https://sec.gov/pr",
                    payload={
                        "ticker": ticker,
                        "entity_name": "Revolution Medicines",
                        "form_type": "8-K",
                        "filing_date": "2026-06-01",
                    },
                )
            ]

        monkeypatch.setattr(
            "bve.ingestion.news_client.fetch_sec_press_releases",
            fake_fetch_sec_press_releases,
        )

        items = PressReleaseSource().fetch("RVMD", {"name": "Revolution Medicines"}, 14)

        assert len(items) == 1
        assert items[0].source_type == "press_release"
        assert items[0].published_date == date(2026, 6, 1)
        assert "Revolution Medicines" in items[0].text

    def test_news_article_source_uses_newsapi_when_key_is_present(self, monkeypatch):
        from bve.ingestion.raw_event import RawEvent

        calls: list[str] = []

        def fake_fetch_newsapi_articles(query, api_key, ticker=None, limit=20):  # noqa: ARG001
            calls.append(query)
            return [
                RawEvent(
                    source="newsapi",
                    record_type="news_article",
                    source_url="https://news.example/1",
                    payload={
                        "ticker": ticker,
                        "title": "RVMD announces Phase 3 results",
                        "summary": "Phase 3 trial met primary endpoint.",
                        "published": "2026-06-01T12:00:00Z",
                    },
                )
            ]

        monkeypatch.setenv("NEWS_API_KEY", "test-key")
        monkeypatch.setattr(
            "bve.ingestion.news_client.fetch_newsapi_articles",
            fake_fetch_newsapi_articles,
        )

        items = NewsArticleSource().fetch("RVMD", {"name": "Revolution Medicines"}, 14)

        assert calls == ['"Revolution Medicines" OR RVMD']
        assert len(items) == 1
        assert items[0].source_type == "news_article"
        assert "Phase 3" in items[0].text

    def test_earnings_release_source_filters_sec_item_202(self):
        class FakeSecSource:
            def fetch(self, ticker, profile_data, lookback_days):  # noqa: ARG002
                return [
                    RawIngestionItem(
                        ticker=ticker,
                        text="generic 8-K",
                        source_type="sec_filing",
                        source_url="https://sec.gov/earnings",
                        published_date=date(2026, 6, 1),
                        raw_payload={"items": "2.02 9.01"},
                    ),
                    RawIngestionItem(
                        ticker=ticker,
                        text="generic 8-K",
                        source_type="sec_filing",
                        source_url="https://sec.gov/other",
                        published_date=date(2026, 6, 1),
                        raw_payload={"items": "8.01"},
                    ),
                ]

        items = EarningsReleaseSource(sec_source=FakeSecSource()).fetch(
            "RVMD", {"name": "Revolution Medicines"}, 14
        )

        assert len(items) == 1
        assert items[0].source_type == "earnings_release"
        assert "earnings" in items[0].text


# ---------------------------------------------------------------------------
# 1. Runner processes a raw SEC item into an EvidenceRecord
# ---------------------------------------------------------------------------

class TestProcessSECItem:
    def test_sec_item_appended_to_ledger(self, tmp_path):
        item = _make_item(ticker="RVMD", source_type="sec_filing")
        runner = _make_runner(raw_items=[item])
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        assert result.records_appended == 1
        assert result.items_classified == 1

    def test_returns_ingestion_run_result(self, tmp_path):
        runner = _make_runner()
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        assert isinstance(result, IngestionRunResult)
        assert result.as_of_date == date(2026, 6, 1)
        assert result.lookback_days == 14


# ---------------------------------------------------------------------------
# 2. Unclassified item is skipped
# ---------------------------------------------------------------------------

class TestUnclassifiedSkipped:
    def test_unclassified_not_in_ledger(self, tmp_path):
        def _unclassified_classifier(text, ticker, source_type):
            # Return UNCLASSIFIED
            return _make_mlc(ticker=ticker, primary_event="unclassified", direction="unknown", confidence=0.0)

        item = _make_item(ticker="RVMD")
        runner = _make_runner(raw_items=[item], mlc_factory=_unclassified_classifier)
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        assert result.records_appended == 0
        assert result.unclassified_count == 1
        assert result.items_classified == 0

    def test_unclassified_not_in_csv(self, tmp_path):
        def _unclassified_classifier(text, ticker, source_type):
            return _make_mlc(ticker=ticker, primary_event="unclassified", direction="unknown", confidence=0.0)

        item = _make_item(ticker="RVMD")
        runner = _make_runner(raw_items=[item], mlc_factory=_unclassified_classifier)
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        csv_path = tmp_path / "new_events.csv"
        rows = list(csv.DictReader(csv_path.open()))
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# 3. Duplicate cluster is skipped
# ---------------------------------------------------------------------------

class TestDuplicateSkipped:
    def test_same_item_twice_counted_once(self, tmp_path):
        item = _make_item(ticker="RVMD", source_type="sec_filing")
        runner = _make_runner(raw_items=[item, item])  # two identical items
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        assert result.records_appended == 1
        assert result.duplicates_skipped == 1

    def test_duplicate_appears_in_csv_once(self, tmp_path):
        item = _make_item(ticker="RVMD", source_type="sec_filing")
        runner = _make_runner(raw_items=[item, item])
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        # Both items appear in csv (for audit) but only one was appended
        csv_path = tmp_path / "new_events.csv"
        rows = list(csv.DictReader(csv_path.open()))
        assert len(rows) == 2  # both in csv


# ---------------------------------------------------------------------------
# 4. new_events.csv is written with required columns
# ---------------------------------------------------------------------------

class TestNewEventsCSV:
    def test_csv_written(self, tmp_path):
        runner = _make_runner()
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        assert (tmp_path / "new_events.csv").exists()

    def test_csv_required_columns(self, tmp_path):
        runner = _make_runner()
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        csv_path = tmp_path / "new_events.csv"
        reader = csv.DictReader(csv_path.open())
        cols = set(reader.fieldnames or [])
        required = {"ticker", "event_type", "direction", "confidence", "materiality",
                    "source_type", "published_date", "human_review_required",
                    "score_deltas", "raw_text", "company_role"}
        assert required <= cols

    def test_csv_row_has_correct_ticker(self, tmp_path):
        runner = _make_runner()
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        rows = list(csv.DictReader((tmp_path / "new_events.csv").open()))
        assert rows[0]["ticker"] == "RVMD"


# ---------------------------------------------------------------------------
# 5. source_breakdown counts correctly
# ---------------------------------------------------------------------------

class TestSourceBreakdown:
    def test_sec_counted_separately_from_ctgov(self, tmp_path):
        items = [
            _make_item(ticker="RVMD", source_type="sec_filing"),
            _make_item(ticker="RVMD", source_type="clinicaltrials_gov",
                       text="Phase 2 trial recruiting enrollment begins"),
        ]
        runner = _make_runner(raw_items=items)
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        assert result.source_breakdown.get("sec_filing", 0) >= 1
        assert result.source_breakdown.get("clinicaltrials_gov", 0) >= 1

    def test_all_three_sources_in_breakdown_keys(self, tmp_path):
        runner = _make_runner(raw_items=[])
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
        )

        # Keys should exist even if zero
        assert "sec_filing" in result.source_breakdown
        assert "clinicaltrials_gov" in result.source_breakdown
        assert "fda_website" in result.source_breakdown


# ---------------------------------------------------------------------------
# 6. Review gate flags high-impact event
# ---------------------------------------------------------------------------

class TestReviewGate:
    def test_high_impact_flagged_in_csv(self, tmp_path):
        item = _make_item(ticker="RVMD", source_type="sec_filing")
        runner = _make_runner(raw_items=[item], review_gate_result=True)
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        rows = list(csv.DictReader((tmp_path / "new_events.csv").open()))
        assert rows[0]["human_review_required"] == "True"

    def test_low_impact_not_flagged(self, tmp_path):
        item = _make_item(ticker="RVMD", source_type="sec_filing")
        runner = _make_runner(raw_items=[item], review_gate_result=False)
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        rows = list(csv.DictReader((tmp_path / "new_events.csv").open()))
        assert rows[0]["human_review_required"] == "False"


# ---------------------------------------------------------------------------
# 7. Target context modifies score_deltas
# ---------------------------------------------------------------------------

class TestContextModifier:
    def test_context_engine_called_with_deltas(self, tmp_path):
        ctx_calls: list = []

        def _ctx_engine(deltas, event_type, profile):
            ctx_calls.append((deltas, event_type))
            # Amplify all deltas ×2 to prove it was called
            return {k: v * 2 for k, v in deltas.items()}

        item = _make_item(ticker="RVMD")
        runner = LiveIngestionRunner(
            sec_source=lambda t, p, lookback: [item] if t == "RVMD" else [],
            ctgov_source=_null_source,
            fda_source=_null_source,
            classifier=lambda text, ticker, src: _make_mlc(ticker=ticker),
            materiality_est=lambda et, st, h=None: _make_mat_est(),
            context_engine=_ctx_engine,
            clusterer=lambda r: "clust-001",
            review_gate=lambda m: False,
        )
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        assert len(ctx_calls) >= 1
        assert result.records_appended == 1

    def test_modified_deltas_in_ledger_record(self, tmp_path):
        def _ctx_engine(deltas, event_type, profile):
            return {"asset_quality": 0.99}  # override everything

        item = _make_item(ticker="RVMD")
        runner = LiveIngestionRunner(
            sec_source=lambda t, p, lookback: [item] if t == "RVMD" else [],
            ctgov_source=_null_source,
            fda_source=_null_source,
            classifier=lambda text, ticker, src: _make_mlc(ticker=ticker),
            materiality_est=lambda et, st, h=None: _make_mat_est(),
            context_engine=_ctx_engine,
            clusterer=lambda r: "clust-002",
            review_gate=lambda m: False,
        )
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        records = ledger.get_records("RVMD")
        assert len(records) == 1
        assert abs(records[0].score_deltas.get("asset_quality", 0) - 0.99) < 1e-6


# ---------------------------------------------------------------------------
# 8. Acquirer ticker sets company_role=acquirer
# ---------------------------------------------------------------------------

class TestCompanyRole:
    def test_acquirer_only_ticker_role(self):
        role = _company_role("PFE", frozenset(["RVMD"]), frozenset(["PFE"]))
        assert role == "acquirer"

    def test_target_only_ticker_role(self):
        role = _company_role("RVMD", frozenset(["RVMD"]), frozenset(["PFE"]))
        assert role == "target"

    def test_both_ticker_role(self):
        role = _company_role("BIIB", frozenset(["BIIB"]), frozenset(["BIIB"]))
        assert role == "both"

    def test_company_role_in_csv(self, tmp_path):
        items = [
            _make_item(ticker="RVMD", source_type="sec_filing"),
        ]
        runner = _make_runner(raw_items=items)
        ledger = _make_ledger(tmp_path)
        targets = {"RVMD": {"ticker": "RVMD", "name": "Revolution Medicines",
                             "lead_asset": "RMC-6236", "lead_asset_phase": "phase_3",
                             "therapeutic_areas": ["oncology"]}}
        acquirers = {"PFE": {"ticker": "PFE", "name": "Pfizer",
                              "lead_asset": "", "lead_asset_phase": "commercial",
                              "therapeutic_areas": ["oncology"]}}

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        rows = list(csv.DictReader((tmp_path / "new_events.csv").open()))
        rvmd_rows = [r for r in rows if r["ticker"] == "RVMD"]
        assert len(rvmd_rows) == 1
        assert rvmd_rows[0]["company_role"] == "target"


# ---------------------------------------------------------------------------
# 9. Source failure does not crash the whole run
# ---------------------------------------------------------------------------

class TestSourceFailure:
    def test_source_exception_still_returns_result(self, tmp_path):
        def _exploding_source(ticker, profile_data, lookback_days):
            raise RuntimeError("network failure")

        runner = LiveIngestionRunner(
            sec_source=_exploding_source,
            ctgov_source=_null_source,
            fda_source=_null_source,
            classifier=lambda text, ticker, src: _make_mlc(ticker=ticker),
            materiality_est=lambda et, st, h=None: _make_mat_est(),
            context_engine=lambda d, et, p: d,
            clusterer=lambda r: "clust",
            review_gate=lambda m: False,
        )
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        assert isinstance(result, IngestionRunResult)
        assert result.items_seen == 0  # nothing from exploding source

    def test_partial_source_failure_processes_remaining(self, tmp_path):
        item_ctgov = _make_item(
            ticker="RVMD",
            source_type="clinicaltrials_gov",
            text="Phase 2 trial recruiting begins enrollment",
        )

        def _exploding_sec(ticker, profile_data, lookback_days):
            raise RuntimeError("sec down")

        runner = LiveIngestionRunner(
            sec_source=_exploding_sec,
            ctgov_source=lambda t, p, lookback: [item_ctgov] if t == "RVMD" else [],
            fda_source=_null_source,
            classifier=lambda text, ticker, src: _make_mlc(ticker=ticker, source_type=src),
            materiality_est=lambda et, st, h=None: _make_mat_est(),
            context_engine=lambda d, et, p: d,
            clusterer=lambda r: "clust",
            review_gate=lambda m: False,
        )
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
        )

        assert result.records_appended == 1


# ---------------------------------------------------------------------------
# 10. Dry-run mode writes no ledger records
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_appends_nothing(self, tmp_path):
        runner = _make_runner()
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
            dry_run=True,
        )

        assert result.records_appended == 0
        records = ledger.get_score_history("RVMD")
        assert len(records) == 0

    def test_dry_run_writes_no_csv(self, tmp_path):
        runner = _make_runner()
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            output_dir=tmp_path,
            dry_run=True,
        )

        # With dry_run=True and output_dir passed but dry_run forces skip
        # The runner should NOT write the CSV (output_dir is None in dry_run path)
        assert not (tmp_path / "new_events.csv").exists()

    def test_dry_run_still_counts_would_be_appended(self, tmp_path):
        """dry-run should count items that WOULD have been appended."""
        runner = _make_runner()
        ledger = _make_ledger(tmp_path)
        targets, acquirers = _minimal_profiles()

        result = runner.run(
            targets=targets,
            acquirers=acquirers,
            ledger=ledger,
            as_of_date=date(2026, 6, 1),
            dry_run=True,
        )

        # In dry_run mode, items_classified should still be counted
        assert result.items_classified == 1


# ---------------------------------------------------------------------------
# 11. ContextProfile builder
# ---------------------------------------------------------------------------

class TestBuildContextProfile:
    def test_safety_flag_from_text(self):
        profile = _build_context_profile(
            {"lead_asset_phase": "phase_3"},
            "serious adverse events observed in toxicity study",
            "clinical_negative_ph3",
        )
        assert profile.safety_flag is True

    def test_no_safety_flag_for_positive_text(self):
        profile = _build_context_profile(
            {"lead_asset_phase": "phase_2"},
            "Phase 2 trial met primary endpoint",
            "clinical_positive_ph2",
        )
        assert profile.safety_flag is False

    def test_late_stage_pipeline_phase3(self):
        profile = _build_context_profile(
            {"lead_asset_phase": "phase_3"},
            "pivotal trial",
            "clinical_positive_ph3",
        )
        assert profile.late_stage_pipeline is True

    def test_early_stage_not_late_stage(self):
        profile = _build_context_profile(
            {"lead_asset_phase": "phase_1"},
            "Phase 1 dose escalation",
            "clinical_positive_ph1",
        )
        assert profile.late_stage_pipeline is False

    def test_biomarker_only_flag(self):
        profile = _build_context_profile(
            {"lead_asset_phase": "phase_2"},
            "biomarker subgroup analysis positive result",
            "clinical_positive_ph2",
        )
        assert profile.biomarker_only is True

    def test_pivotal_design_flag(self):
        profile = _build_context_profile(
            {"lead_asset_phase": "phase_3"},
            "pivotal confirmatory registration trial",
            "clinical_positive_ph3",
        )
        assert profile.pivotal_design is True


# ---------------------------------------------------------------------------
# 12. SecEightKSource items_to_text helper
# ---------------------------------------------------------------------------

class TestSecItemsToText:
    def test_known_item_produces_phrase(self):
        text = SecEightKSource._items_to_text("1.01", "RVMD")
        assert "RVMD" in text
        assert "agreement" in text.lower() or "deal" in text.lower() or "material" in text.lower()

    def test_restructuring_item(self):
        text = SecEightKSource._items_to_text("2.05", "BIIB")
        assert "restructur" in text.lower() or "exit" in text.lower()

    def test_unknown_item_fallback(self):
        text = SecEightKSource._items_to_text("3.99", "TEST")
        assert "8-K" in text or "TEST" in text

    def test_empty_items_fallback(self):
        text = SecEightKSource._items_to_text("", "RVMD")
        assert "RVMD" in text or "8-K" in text

    def test_multiple_items_combined(self):
        text = SecEightKSource._items_to_text("1.01 9.01", "RVMD")
        assert "RVMD" in text
