"""
Phase 1 — Universe foundation tests.

Covers:
  - event_classifier: headline → event_type, direction, score_deltas
  - evidence_ledger: append, replay, score history, clamping
  - universe_scanner: SIC filter, cache, YAML output (mocked network)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bve.ingestion.event_classifier import (
    ACQUIRER_BD_APPETITE,
    ACQUIRER_LARGE_DEAL,
    ADCOM_NEGATIVE,
    ADCOM_POSITIVE,
    BTD,
    CASH_LOW,
    CLINICAL_MIXED,
    CLINICAL_NEGATIVE,
    CLINICAL_NEGATIVE_PH2,
    CLINICAL_NEGATIVE_PH3,
    CLINICAL_POSITIVE,
    CLINICAL_POSITIVE_PH1,
    CLINICAL_POSITIVE_PH2,
    CLINICAL_POSITIVE_PH3,
    CRL,
    EQUITY_RAISE,
    FAST_TRACK,
    FDA_APPROVAL,
    LICENSING_DEAL,
    MAX_SINGLE_EVENT_DELTA,
    NDA_ACCEPTED,
    ORPHAN,
    PARTNERSHIP,
    PATENT_CLIFF,
    RESTRUCTURING,
    SCORE_DELTA_MAP,
    SOURCE_CONFIDENCE_WEIGHTS,
    STRATEGIC_REVIEW,
    TRIAL_DELAY,
    TRIAL_DISCONTINUATION,
    TRIAL_START,
    UNCLASSIFIED,
    classify_headline,
)
from bve.ingestion.evidence_ledger import DEFAULT_SEED_SCORES, EvidenceLedger, EvidenceRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    ticker: str = "TEST",
    event_date: str = "2025-06-01",
    event_type: str = CLINICAL_POSITIVE_PH2,
    direction: str = "positive",
    score_deltas: dict | None = None,
    confidence: float = 0.80,
) -> EvidenceRecord:
    return EvidenceRecord(
        ticker=ticker,
        event_date=event_date,
        event_type=event_type,
        direction=direction,
        source_type="press_release",
        source_url="https://example.com",
        raw_text="positive phase 2",
        confidence=confidence,
        match_reasons=[event_type],
        phase_detected="Phase 2",
        score_deltas=score_deltas or {"asset_quality": 0.07},
    )


# ===========================================================================
# event_classifier tests
# ===========================================================================


class TestClinicalPositive:
    def test_phase3_met_primary_endpoint(self):
        ev = classify_headline(
            "Company X announces Phase 3 trial met primary endpoint",
            ticker="XXXX",
        )
        assert ev.event_type == CLINICAL_POSITIVE_PH3
        assert ev.direction == "positive"
        assert ev.phase_detected == "Phase 3"
        assert ev.score_deltas.get("asset_quality", 0) > 0

    def test_phase2_statistically_significant(self):
        ev = classify_headline(
            "Phase 2 study demonstrated statistically significant improvement in DLBCL",
            ticker="YYYY",
        )
        assert ev.event_type == CLINICAL_POSITIVE_PH2
        assert ev.direction == "positive"
        assert ev.score_deltas.get("asset_quality", 0) > 0

    def test_phase1_positive(self):
        ev = classify_headline(
            "Phase 1 trial showed positive results for Drug Y",
            ticker="AAAA",
        )
        assert ev.event_type == CLINICAL_POSITIVE_PH1
        assert ev.direction == "positive"

    def test_pivotal_treated_as_phase3(self):
        ev = classify_headline(
            "Pivotal trial met primary endpoint with statistically significant reduction",
            ticker="PVTL",
        )
        assert ev.event_type == CLINICAL_POSITIVE_PH3
        assert ev.phase_detected == "Phase 3"

    def test_superiority_positive(self):
        ev = classify_headline(
            "Phase 3 trial demonstrated superiority over standard of care",
            ticker="SUPR",
        )
        assert ev.event_type == CLINICAL_POSITIVE_PH3


class TestClinicalNegative:
    def test_phase3_did_not_meet(self):
        ev = classify_headline(
            "Phase 3 trial did not meet its primary endpoint in NSCLC",
            ticker="ZZZZ",
        )
        assert ev.event_type == CLINICAL_NEGATIVE_PH3
        assert ev.direction == "negative"
        assert ev.score_deltas.get("asset_quality", 0) < 0
        assert ev.score_deltas.get("seller_willingness", 0) > 0

    def test_phase2_failed_to_meet(self):
        ev = classify_headline(
            "Phase 2 study failed to meet its primary endpoint",
            ticker="FAIL",
        )
        assert ev.event_type == CLINICAL_NEGATIVE_PH2
        assert ev.direction == "negative"

    def test_missed_primary(self):
        ev = classify_headline(
            "Company announces Phase 3 missed primary endpoint — shares plunge 60%",
            ticker="MISS",
        )
        assert ev.event_type == CLINICAL_NEGATIVE_PH3
        assert ev.direction == "negative"


class TestClinicalMixed:
    def test_trend_not_significant(self):
        ev = classify_headline(
            "Phase 2 showed trend but not statistically significant improvement",
            ticker="MIXD",
        )
        assert ev.event_type == CLINICAL_MIXED
        assert ev.direction == "mixed"

    def test_exploratory_endpoint(self):
        ev = classify_headline(
            "Phase 2 results based on exploratory endpoint analysis",
            ticker="EXPL",
        )
        assert ev.event_type == CLINICAL_MIXED


class TestRegulatoryEvents:
    def test_fda_approval(self):
        ev = classify_headline(
            "FDA approved Company X's treatment for relapsed/refractory lymphoma",
            ticker="APRX",
        )
        assert ev.event_type == FDA_APPROVAL
        assert ev.direction == "positive"
        assert ev.score_deltas.get("asset_quality", 0) > 0

    def test_crl_full(self):
        ev = classify_headline(
            "FDA issues complete response letter for Company NDA",
            ticker="CRLX",
        )
        assert ev.event_type == CRL
        assert ev.direction == "negative"

    def test_crl_abbreviation(self):
        ev = classify_headline(
            "Company receives CRL from FDA",
            ticker="CRLY",
        )
        assert ev.event_type == CRL

    def test_btd(self):
        ev = classify_headline(
            "FDA grants Breakthrough Therapy Designation for Drug X in AML",
            ticker="BTDX",
        )
        assert ev.event_type == BTD
        assert ev.direction == "positive"
        assert ev.score_deltas.get("asset_quality", 0) > 0

    def test_btd_abbreviation(self):
        ev = classify_headline(
            "Company announces BTD from FDA for lead program",
            ticker="BTDA",
        )
        assert ev.event_type == BTD

    def test_fast_track(self):
        ev = classify_headline(
            "FDA grants Fast Track Designation for Drug Y in glioblastoma",
            ticker="FSTK",
        )
        assert ev.event_type == FAST_TRACK

    def test_orphan(self):
        ev = classify_headline(
            "Company receives Orphan Drug Designation for treatment of rare disease",
            ticker="ORPH",
        )
        assert ev.event_type == ORPHAN

    def test_nda_accepted(self):
        ev = classify_headline(
            "FDA accepts NDA for review for Company's lead compound",
            ticker="NDAX",
        )
        assert ev.event_type == NDA_ACCEPTED
        assert ev.score_deltas.get("catalyst_timing", 0) > 0

    def test_adcom_positive(self):
        ev = classify_headline(
            "FDA advisory committee voted in favor of approval of Drug Z",
            ticker="ADCP",
        )
        assert ev.event_type == ADCOM_POSITIVE
        assert ev.direction == "positive"

    def test_adcom_negative(self):
        ev = classify_headline(
            "Advisory committee voted against approval, citing safety concerns",
            ticker="ADCN",
        )
        assert ev.event_type == ADCOM_NEGATIVE
        assert ev.direction == "negative"


class TestFinancialEvents:
    def test_strategic_review(self):
        ev = classify_headline(
            "Company X announces strategic review of options including potential sale",
            ticker="STRX",
        )
        assert ev.event_type == STRATEGIC_REVIEW
        assert ev.score_deltas.get("seller_willingness", 0) > 0

    def test_exploring_strategic_alternatives(self):
        ev = classify_headline(
            "Board announces it is exploring strategic alternatives",
            ticker="EXPL",
        )
        assert ev.event_type == STRATEGIC_REVIEW

    def test_equity_raise(self):
        ev = classify_headline(
            "Company prices public offering of 10M shares at $12.50",
            ticker="RAIS",
        )
        assert ev.event_type == EQUITY_RAISE
        assert ev.score_deltas.get("seller_willingness", 0) < 0  # more cash = less pressure

    def test_private_placement(self):
        ev = classify_headline(
            "Company closes $150 million private placement financing",
            ticker="PPCE",
        )
        assert ev.event_type == EQUITY_RAISE

    def test_cash_low(self):
        ev = classify_headline(
            "Company has cash runway of less than 12 months",
            ticker="CLOW",
        )
        assert ev.event_type == CASH_LOW
        assert ev.score_deltas.get("seller_willingness", 0) > 0

    def test_restructuring_reduction_in_force(self):
        ev = classify_headline(
            "Company announces reduction in force affecting 30% of employees",
            ticker="REST",
        )
        assert ev.event_type == RESTRUCTURING
        assert ev.score_deltas.get("seller_willingness", 0) > 0

    def test_layoffs(self):
        ev = classify_headline(
            "Biotech announces layoffs and pipeline reprioritization",
            ticker="LAYX",
        )
        assert ev.event_type == RESTRUCTURING

    def test_licensing_deal(self):
        ev = classify_headline(
            "Company enters into license agreement with major pharma for $500M deal",
            ticker="LICX",
        )
        assert ev.event_type == LICENSING_DEAL
        assert ev.score_deltas.get("asset_quality", 0) > 0
        assert ev.score_deltas.get("seller_willingness", 0) < 0

    def test_partnership(self):
        ev = classify_headline(
            "Company announces co-development agreement with AstraZeneca",
            ticker="PRTN",
        )
        assert ev.event_type == PARTNERSHIP

    def test_trial_start(self):
        ev = classify_headline(
            "Company doses first patient in Phase 2 clinical trial of Drug X",
            ticker="TSTR",
        )
        assert ev.event_type == TRIAL_START

    def test_trial_delay(self):
        ev = classify_headline(
            "FDA places clinical hold on Phase 2 trial",
            ticker="TDLY",
        )
        assert ev.event_type == TRIAL_DELAY

    def test_trial_discontinuation(self):
        ev = classify_headline(
            "Company discontinues Phase 3 trial due to lack of efficacy",
            ticker="TDSC",
        )
        assert ev.event_type == TRIAL_DISCONTINUATION
        assert ev.score_deltas.get("asset_quality", 0) < 0
        assert ev.score_deltas.get("seller_willingness", 0) > 0


class TestAcquirerEvents:
    def test_bd_appetite(self):
        ev = classify_headline(
            "CEO says business development remains a priority with bolt-on acquisitions in focus",
            ticker="AZN",
        )
        assert ev.event_type == ACQUIRER_BD_APPETITE
        assert ev.direction == "positive"

    def test_large_deal_completed(self):
        ev = classify_headline(
            "Pfizer completed acquisition of Seagen for $43 billion",
            ticker="PFE",
        )
        assert ev.event_type == ACQUIRER_LARGE_DEAL
        assert ev.direction == "negative"

    def test_patent_cliff(self):
        ev = classify_headline(
            "Company faces significant patent cliff in 2027 on lead product",
            ticker="MRK",
        )
        assert ev.event_type == PATENT_CLIFF


class TestUnclassified:
    def test_generic_financial_result(self):
        ev = classify_headline(
            "Company X announces Q3 2025 financial results",
            ticker="GENX",
        )
        assert ev.event_type == UNCLASSIFIED
        assert ev.confidence == 0.0
        assert ev.score_deltas == {}

    def test_conference_presentation(self):
        ev = classify_headline(
            "Company to present at JP Morgan Healthcare Conference",
            ticker="CONF",
        )
        assert ev.event_type == UNCLASSIFIED

    def test_leadership_change(self):
        ev = classify_headline(
            "Company appoints new Chief Medical Officer",
            ticker="LEAD",
        )
        assert ev.event_type == UNCLASSIFIED


class TestConfidenceAndCaps:
    def test_hedging_reduces_confidence(self):
        clean = classify_headline(
            "Phase 2 trial met primary endpoint with statistically significant results",
            ticker="CLEN",
        )
        hedged = classify_headline(
            "Phase 2 trial showed trend but not statistically significant",
            ticker="HEDG",
        )
        assert clean.confidence > hedged.confidence

    def test_source_type_affects_confidence(self):
        from_fda = classify_headline(
            "FDA approved Company's treatment",
            ticker="FDA1",
            source_type="fda_website",
        )
        from_news = classify_headline(
            "FDA approved Company's treatment",
            ticker="FDA2",
            source_type="news_article",
        )
        assert from_fda.confidence > from_news.confidence

    def test_all_deltas_within_caps(self):
        """Every headline must produce deltas within MAX_SINGLE_EVENT_DELTA."""
        headlines = [
            "Phase 3 trial met primary endpoint — statistically significant reduction",
            "Phase 3 trial failed to meet primary endpoint",
            "FDA issues complete response letter for NDA",
            "Company announces strategic alternatives including potential sale",
            "Reduction in force announced — company restructuring",
            "Phase 2 showed statistically significant improvement in overall survival",
        ]
        for text in headlines:
            ev = classify_headline(text, ticker="TEST")
            for feature, delta in ev.score_deltas.items():
                cap = MAX_SINGLE_EVENT_DELTA.get(feature, 0.20)
                assert abs(delta) <= cap + 1e-9, (
                    f"Headline: {text!r}\n"
                    f"  delta for {feature} = {delta:.4f} exceeds cap {cap}"
                )

    def test_ticker_is_preserved(self):
        ev = classify_headline("Phase 3 met primary endpoint", ticker="RVMD")
        assert ev.ticker == "RVMD"

    def test_raw_text_is_preserved(self):
        text = "Company announces Phase 3 trial met primary endpoint"
        ev = classify_headline(text, ticker="RVMD")
        assert ev.raw_text == text


class TestScoreDeltaMap:
    def test_all_features_are_valid(self):
        # acquirer_fit kept for legacy; new acquirer keys added in Phase 1 v2
        valid = {
            "asset_quality", "seller_willingness", "catalyst_timing",
            "acquirer_fit",           # legacy composite
            "acquirer_appetite",      # v2: willingness to do deals
            "integration_capacity",   # v2: capacity to absorb a deal
            "acquirer_urgency",       # v2: pipeline gap / patent cliff pressure
        }
        for event_type, deltas in SCORE_DELTA_MAP.items():
            for feature in deltas:
                assert feature in valid, (
                    f"Event '{event_type}': unknown feature '{feature}'"
                )

    def test_base_deltas_within_caps(self):
        for event_type, deltas in SCORE_DELTA_MAP.items():
            for feature, delta in deltas.items():
                cap = MAX_SINGLE_EVENT_DELTA.get(feature, 0.20)
                assert abs(delta) <= cap + 1e-9, (
                    f"Base delta for '{event_type}'.{feature} = {delta} exceeds cap {cap}"
                )


# ===========================================================================
# evidence_ledger tests
# ===========================================================================


class TestEvidenceLedgerAppend:
    def test_append_and_retrieve(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        ledger.append(_make_record("RVMD"))
        records = ledger.get_records("RVMD")
        assert len(records) == 1
        assert records[0].ticker == "RVMD"
        assert records[0].event_type == CLINICAL_POSITIVE_PH2

    def test_ticker_filter(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        for ticker in ["AAAA", "BBBB", "AAAA"]:
            ledger.append(_make_record(ticker))
        assert len(ledger.get_records("AAAA")) == 2
        assert len(ledger.get_records("BBBB")) == 1

    def test_date_filter_since(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        for d in ["2024-01-01", "2025-01-01", "2026-01-01"]:
            ledger.append(_make_record(event_date=d))
        records = ledger.get_records(since_date=date(2025, 1, 1))
        assert all(r.event_date >= "2025-01-01" for r in records)
        assert len(records) == 2

    def test_date_filter_until(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        for d in ["2024-01-01", "2025-01-01", "2026-01-01"]:
            ledger.append(_make_record(event_date=d))
        records = ledger.get_records(until_date=date(2024, 12, 31))
        assert len(records) == 1
        assert records[0].event_date == "2024-01-01"

    def test_event_type_filter(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        ledger.append(_make_record(event_type=CLINICAL_POSITIVE_PH2))
        ledger.append(_make_record(event_type=CRL))
        records = ledger.get_records(event_types=[CRL])
        assert len(records) == 1
        assert records[0].event_type == CRL

    def test_empty_ledger_returns_empty_list(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        assert ledger.get_records("RVMD") == []

    def test_all_tickers(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        for ticker in ["AAAA", "BBBB", "CCCC", "AAAA"]:
            ledger.append(_make_record(ticker))
        tickers = ledger.all_tickers()
        assert set(tickers) == {"AAAA", "BBBB", "CCCC"}
        assert tickers == sorted(tickers)


class TestEvidenceLedgerScoreReplay:
    def test_apply_positive_delta(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        seed = {"asset_quality": 0.50, "seller_willingness": 0.30}
        ledger.append(_make_record(score_deltas={"asset_quality": 0.07}))
        scores = ledger.compute_score_state("TEST", seed_scores=seed)
        assert scores["asset_quality"] == pytest.approx(0.57)
        assert scores["seller_willingness"] == pytest.approx(0.30)

    def test_apply_negative_delta(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        seed = {"asset_quality": 0.60}
        ledger.append(_make_record(score_deltas={"asset_quality": -0.25}))
        scores = ledger.compute_score_state("TEST", seed_scores=seed)
        assert scores["asset_quality"] == pytest.approx(0.35)

    def test_scores_clamped_above_one(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        seed = {"asset_quality": 0.95}
        for _ in range(5):
            ledger.append(_make_record(score_deltas={"asset_quality": 0.15}))
        scores = ledger.compute_score_state("TEST", seed_scores=seed)
        assert scores["asset_quality"] <= 1.0

    def test_scores_clamped_below_zero(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        seed = {"asset_quality": 0.05}
        for _ in range(5):
            ledger.append(_make_record(score_deltas={"asset_quality": -0.25}))
        scores = ledger.compute_score_state("TEST", seed_scores=seed)
        assert scores["asset_quality"] >= 0.0

    def test_as_of_date_excludes_future_events(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        seed = {"asset_quality": 0.50}
        ledger.append(_make_record(event_date="2025-01-01", score_deltas={"asset_quality": 0.07}))
        ledger.append(_make_record(event_date="2025-12-01", score_deltas={"asset_quality": 0.07}))
        scores_jan = ledger.compute_score_state("TEST", as_of_date=date(2025, 6, 1), seed_scores=seed)
        scores_all = ledger.compute_score_state("TEST", seed_scores=seed)
        assert scores_jan["asset_quality"] < scores_all["asset_quality"]

    def test_empty_ledger_returns_seed_scores(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        seed = {"asset_quality": 0.50}
        scores = ledger.compute_score_state("EMPTY", seed_scores=seed)
        assert scores["asset_quality"] == pytest.approx(0.50)

    def test_uses_default_seeds_when_none_provided(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        scores = ledger.compute_score_state("EMPTY")
        assert scores == DEFAULT_SEED_SCORES

    def test_multiple_tickers_isolated(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        ledger.append(_make_record("AAAA", score_deltas={"asset_quality": 0.10}))
        ledger.append(_make_record("BBBB", score_deltas={"asset_quality": -0.10}))
        seed = {"asset_quality": 0.50}
        a_scores = ledger.compute_score_state("AAAA", seed_scores=seed)
        b_scores = ledger.compute_score_state("BBBB", seed_scores=seed)
        assert a_scores["asset_quality"] == pytest.approx(0.60)
        assert b_scores["asset_quality"] == pytest.approx(0.40)


class TestEvidenceLedgerHistory:
    def test_score_history_ordered_by_date(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        for d in ["2025-03-01", "2025-01-01", "2025-06-01"]:
            ledger.append(_make_record(event_date=d))
        history = ledger.get_score_history("TEST")
        dates = [h["event_date"] for h in history]
        assert dates == sorted(dates)

    def test_score_history_contains_score_fields(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        ledger.append(_make_record(score_deltas={"asset_quality": 0.05}))
        history = ledger.get_score_history("TEST")
        assert len(history) == 1
        assert "asset_quality" in history[0]
        assert "event_type" in history[0]
        assert "direction" in history[0]

    def test_ticker_summary_no_events(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        summary = ledger.ticker_summary("EMPTY")
        assert summary["n_events"] == 0
        assert "asset_quality" in summary["scores"]

    def test_ticker_summary_with_events(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        ledger.append(_make_record(event_date="2025-06-01"))
        summary = ledger.ticker_summary("TEST")
        assert summary["n_events"] == 1
        assert summary["last_event_date"] == "2025-06-01"
        assert "asset_quality" in summary["scores"]

    def test_from_classification_round_trip(self, tmp_path: Path):
        ledger = EvidenceLedger(path=tmp_path / "l.jsonl")
        ev = classify_headline(
            "Phase 3 trial met primary endpoint in relapsed lymphoma",
            ticker="RNDX",
        )
        rec = EvidenceRecord.from_classification(ev, event_date="2025-06-01", source_url="https://ir.example.com")
        ledger.append(rec)
        retrieved = ledger.get_records("RNDX")
        assert len(retrieved) == 1
        assert retrieved[0].event_type == CLINICAL_POSITIVE_PH3
        assert retrieved[0].source_url == "https://ir.example.com"


# ===========================================================================
# universe_scanner tests (mocked network)
# ===========================================================================


class TestUniverseScanner:
    """Tests for universe_scanner with mocked EDGAR responses."""

    _EXCHANGE_DATA = {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [
            [12345, "Biotech Inc", "BIOX", "Nasdaq"],
            [12346, "Pharma Research Corp", "PHRM", "NYSE"],
            [12347, "Software Tech Co", "TECH", "Nasdaq"],  # not biotech
            [12348, "Penny Biotech", "PBIO", "OTC"],        # OTC → filtered
            [12349, "Another Biotech", "ABIO", "Nasdaq"],
        ],
    }

    _SUBMISSIONS = {
        "0000012345": {"cik": "0000012345", "sic": 2836, "sicDescription": "Pharmaceutical Preparations"},
        "0000012346": {"cik": "0000012346", "sic": 8731, "sicDescription": "Commercial Physical & Biological Research"},
        "0000012347": {"cik": "0000012347", "sic": 7372, "sicDescription": "Prepackaged Software"},
        "0000012349": {"cik": "0000012349", "sic": 2836, "sicDescription": "Pharmaceutical Preparations"},
    }

    def _mock_get(self, url: str, **kwargs) -> MagicMock:
        from bve.ingestion.universe_scanner import (
            COMPANY_TICKERS_EXCHANGE_URL,
            SUBMISSIONS_BASE,
        )
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        if url == COMPANY_TICKERS_EXCHANGE_URL:
            resp.json.return_value = self._EXCHANGE_DATA
        else:
            cik_padded = url.split("CIK")[1].split(".json")[0] if "CIK" in url else ""
            resp.json.return_value = self._SUBMISSIONS.get(cik_padded, {})
        return resp

    def test_filters_to_biotech_sic(self, tmp_path: Path):
        from bve.ingestion.universe_scanner import scan_biotech_universe
        with patch("requests.get", side_effect=self._mock_get):
            entries = scan_biotech_universe(
                cache_path=tmp_path / ".cache.db",
                output_path=None,
                requests_per_second=10.0,
                verbose=False,
            )
        tickers = {e.ticker for e in entries}
        assert "BIOX" in tickers    # SIC 2836
        assert "PHRM" in tickers    # SIC 8731
        assert "ABIO" in tickers    # SIC 2836
        assert "TECH" not in tickers  # SIC 7372
        assert "PBIO" not in tickers  # OTC

    def test_sic_cache_prevents_repeated_api_calls(self, tmp_path: Path):
        from bve.ingestion.universe_scanner import scan_biotech_universe
        call_counts = [0]

        def counting_get(url: str, **kwargs) -> MagicMock:
            if "submissions" in url or "CIK" in url:
                call_counts[0] += 1
            return self._mock_get(url, **kwargs)

        cache_path = tmp_path / ".cache.db"
        with patch("requests.get", side_effect=counting_get):
            scan_biotech_universe(cache_path=cache_path, output_path=None, requests_per_second=10.0, verbose=False)
            first_calls = call_counts[0]
            scan_biotech_universe(cache_path=cache_path, output_path=None, requests_per_second=10.0, verbose=False)
            second_calls = call_counts[0]

        assert first_calls > 0
        assert second_calls == first_calls  # all served from cache

    def test_writes_yaml_output(self, tmp_path: Path):
        import yaml
        from bve.ingestion.universe_scanner import scan_biotech_universe
        output = tmp_path / "universe.yaml"
        with patch("requests.get", side_effect=self._mock_get):
            entries = scan_biotech_universe(
                cache_path=tmp_path / ".cache.db",
                output_path=output,
                requests_per_second=10.0,
                verbose=False,
            )
        assert output.exists()
        with output.open() as fh:
            data = yaml.safe_load(fh)
        assert data["n_companies"] == len(entries)
        assert len(data["companies"]) == len(entries)
        assert "scanned_at" in data

    def test_rate_limit_validation(self, tmp_path: Path):
        from bve.ingestion.universe_scanner import scan_biotech_universe
        with pytest.raises(ValueError, match="10"):
            scan_biotech_universe(
                cache_path=tmp_path / ".cache.db",
                output_path=None,
                requests_per_second=11.0,
                verbose=False,
            )

    def test_load_universe_yaml_round_trip(self, tmp_path: Path):
        import yaml
        from bve.ingestion.universe_scanner import load_universe_yaml
        output = tmp_path / "universe.yaml"
        with patch("requests.get", side_effect=self._mock_get):
            from bve.ingestion.universe_scanner import scan_biotech_universe
            written = scan_biotech_universe(
                cache_path=tmp_path / ".cache.db",
                output_path=output,
                requests_per_second=10.0,
                verbose=False,
            )
        loaded = load_universe_yaml(output)
        assert {e.ticker for e in loaded} == {e.ticker for e in written}

    def test_load_universe_yaml_missing_file(self, tmp_path: Path):
        from bve.ingestion.universe_scanner import load_universe_yaml
        result = load_universe_yaml(tmp_path / "nonexistent.yaml")
        assert result == []
