"""
Phase 1 v2 improvements — test suite.

Covers all 6 issues identified in the Phase 1 review:
  1. Universe targetability filter (is_drug_developer, target_type, include_in_ma_screen)
  2. Multi-label classification with severity hierarchy
  3. Contextual hedging (global 'did not' removed; positive safety language preserved)
  4. FDA approval multi-feature delta (asset_quality, seller_willingness, catalyst_timing)
  5. Acquirer feature split (acquirer_appetite, integration_capacity, acquirer_urgency)
  6. Evidence coverage score (penalise low-information names)

Plus Phase 2 prerequisites:
  - Event deduplication (event_hash)
  - published_date no-lookahead discipline
  - Stale evidence decay (opt-in)
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import pytest

# ── Universe scanner ──────────────────────────────────────────────────────────
from bve.ingestion.universe_scanner import (
    MARKET_CAP_LARGE,
    MARKET_CAP_MICRO,
    MARKET_CAP_MID,
    MARKET_CAP_SMALL,
    TARGET_TYPE_DIAGNOSTICS,
    TARGET_TYPE_DRUG_DEVELOPER,
    TARGET_TYPE_TOOLS_SERVICES,
    TARGET_TYPE_UNKNOWN,
    UniverseEntry,
    _infer_target_type,
    _market_cap_bucket,
    apply_targetability_filter,
)

# ── Event classifier ──────────────────────────────────────────────────────────
from bve.ingestion.event_classifier import (
    ACQUIRER_BD_APPETITE,
    ACQUIRER_LARGE_DEAL,
    CLINICAL_NEGATIVE_PH3,
    CLINICAL_POSITIVE_PH2,
    CLINICAL_POSITIVE_PH3,
    FDA_APPROVAL,
    PATENT_CLIFF,
    SEVERITY_ORDER,
    STRATEGIC_REVIEW,
    UNCLASSIFIED,
    MultiLabelClassification,
    classify_headline,
    classify_headline_multi,
)

# ── Evidence ledger ───────────────────────────────────────────────────────────
from bve.ingestion.evidence_ledger import (
    DECAY_HALF_LIFE_DAYS,
    DEFAULT_SEED_SCORES,
    SOURCE_PRIORITY,
    EvidenceLedger,
    EvidenceRecord,
    _compute_event_hash,
)


# =============================================================================
# 1. Universe targetability filter
# =============================================================================


class TestInferTargetType:
    def test_pharma_sic_2836_is_drug_developer(self):
        assert _infer_target_type(2836, "Relay Therapeutics") == TARGET_TYPE_DRUG_DEVELOPER

    def test_pharma_sic_2833_is_drug_developer(self):
        assert _infer_target_type(2833, "Acme Biopharma Inc") == TARGET_TYPE_DRUG_DEVELOPER

    def test_diagnostics_sic_2835(self):
        assert _infer_target_type(2835, "Exact Sciences Corp") == TARGET_TYPE_DIAGNOSTICS

    def test_sic_8731_therapeutics_name_is_drug_developer(self):
        assert _infer_target_type(8731, "Protagonist Therapeutics") == TARGET_TYPE_DRUG_DEVELOPER

    def test_sic_8731_biotech_name_is_drug_developer(self):
        assert _infer_target_type(8731, "Alnylam Biotech Research") == TARGET_TYPE_DRUG_DEVELOPER

    def test_sic_8731_diagnostics_keyword_is_tools_services(self):
        assert _infer_target_type(8731, "Genomics Diagnostics Corp") == TARGET_TYPE_TOOLS_SERVICES

    def test_sic_8731_cro_is_tools_services(self):
        assert _infer_target_type(8731, "MedChem Contract Research Organization") == TARGET_TYPE_TOOLS_SERVICES

    def test_sic_8731_generic_research_name_is_unknown(self):
        result = _infer_target_type(8731, "Alpha Research Group")
        assert result == TARGET_TYPE_UNKNOWN

    def test_pharma_sic_with_diagnostics_keyword_is_tools(self):
        # A company with pharma SIC but diagnostics-focused name → tools/services
        result = _infer_target_type(2836, "BioAnalytics Laboratory Services")
        assert result == TARGET_TYPE_TOOLS_SERVICES


class TestMarketCapBucket:
    def test_none_is_micro(self):
        assert _market_cap_bucket(None) == MARKET_CAP_MICRO

    def test_below_300_is_micro(self):
        assert _market_cap_bucket(150.0) == MARKET_CAP_MICRO
        assert _market_cap_bucket(299.9) == MARKET_CAP_MICRO

    def test_300_to_2000_is_small(self):
        assert _market_cap_bucket(300.0) == MARKET_CAP_SMALL
        assert _market_cap_bucket(1500.0) == MARKET_CAP_SMALL

    def test_2000_to_10000_is_mid(self):
        assert _market_cap_bucket(2000.0) == MARKET_CAP_MID
        assert _market_cap_bucket(8000.0) == MARKET_CAP_MID

    def test_above_10000_is_large(self):
        assert _market_cap_bucket(10_001.0) == MARKET_CAP_LARGE
        assert _market_cap_bucket(50_000.0) == MARKET_CAP_LARGE


def _make_universe_entry(ticker: str, sic: int, name: str) -> UniverseEntry:
    return UniverseEntry(
        ticker=ticker, cik="0000000001", company_name=name,
        sic=sic, sic_description="test", exchange="Nasdaq",
    )


class TestApplyTargetabilityFilter:
    def test_drug_developer_included(self):
        entries = [_make_universe_entry("RVMD", 2836, "Revolution Medicines")]
        result = apply_targetability_filter(entries)
        assert len(result) == 1
        assert result[0].target_type == TARGET_TYPE_DRUG_DEVELOPER
        assert result[0].include_in_ma_screen is True

    def test_diagnostics_excluded(self):
        entries = [_make_universe_entry("EXAS", 2835, "Exact Sciences")]
        result = apply_targetability_filter(entries)
        assert len(result) == 0

    def test_tools_services_excluded(self):
        entries = [_make_universe_entry("ICON", 8731, "ICON Clinical Research Services")]
        result = apply_targetability_filter(entries)
        assert len(result) == 0

    def test_large_cap_excluded(self):
        entries = [_make_universe_entry("AMGN", 2836, "Amgen Therapeutics")]
        mcap = {"AMGN": 130_000.0}
        result = apply_targetability_filter(entries, market_cap_lookup=mcap)
        assert len(result) == 0

    def test_market_cap_fields_set(self):
        entries = [_make_universe_entry("RVMD", 2836, "Revolution Medicines")]
        mcap = {"RVMD": 1500.0}
        apply_targetability_filter(entries, market_cap_lookup=mcap)
        assert entries[0].market_cap_bucket == MARKET_CAP_SMALL

    def test_mixed_universe_filtered(self):
        entries = [
            _make_universe_entry("DRUG", 2836, "Drug Therapeutics Inc"),
            _make_universe_entry("DIAG", 2835, "Diagnostics Corp"),
            _make_universe_entry("TOOL", 8731, "Genomics Sequencing Services"),
            _make_universe_entry("BIOT", 8731, "Biotech Oncology Partners"),
        ]
        result = apply_targetability_filter(entries)
        tickers = {e.ticker for e in result}
        assert "DRUG" in tickers
        assert "BIOT" in tickers
        assert "DIAG" not in tickers
        assert "TOOL" not in tickers

    def test_include_in_ma_screen_field_populated_on_all_entries(self):
        entries = [
            _make_universe_entry("AA", 2836, "Good Therapeutics"),
            _make_universe_entry("BB", 2835, "Bad Diagnostics"),
        ]
        apply_targetability_filter(entries)
        assert entries[0].include_in_ma_screen is True
        assert entries[1].include_in_ma_screen is False


# =============================================================================
# 2. Multi-label classification & severity hierarchy
# =============================================================================


class TestSeverityOrder:
    def test_clinical_failure_highest_severity(self):
        assert SEVERITY_ORDER[CLINICAL_NEGATIVE_PH3] >= 95

    def test_fda_approval_high_severity(self):
        assert SEVERITY_ORDER[FDA_APPROVAL] >= 88

    def test_clinical_positive_ph3_high_severity(self):
        assert SEVERITY_ORDER[CLINICAL_POSITIVE_PH3] >= 75

    def test_strategic_review_lower_than_clinical(self):
        assert SEVERITY_ORDER[STRATEGIC_REVIEW] < SEVERITY_ORDER[CLINICAL_NEGATIVE_PH3]
        assert SEVERITY_ORDER[STRATEGIC_REVIEW] < SEVERITY_ORDER[CLINICAL_POSITIVE_PH3]

    def test_unclassified_lowest(self):
        assert SEVERITY_ORDER[UNCLASSIFIED] == 0


class TestMultiLabelClassification:
    def test_returns_multi_label_object(self):
        multi = classify_headline_multi(
            "Phase 3 trial met primary endpoint", ticker="TEST"
        )
        assert isinstance(multi, MultiLabelClassification)

    def test_single_event_no_secondary(self):
        multi = classify_headline_multi(
            "Phase 3 trial met primary endpoint", ticker="TEST"
        )
        assert multi.primary_event == CLINICAL_POSITIVE_PH3
        assert multi.secondary_events == []

    def test_clinical_failure_dominates_strategic_review(self):
        """
        Key issue fix: 'Company announces Phase 3 failure and strategic review'
        should classify as clinical_negative_ph3, not strategic_review.
        Old priority-based system (Financial before Clinical) would pick strategic_review.
        Severity-based system correctly picks clinical_negative_ph3.
        """
        multi = classify_headline_multi(
            "Company announces Phase 3 trial did not meet primary endpoint; "
            "exploring strategic alternatives",
            ticker="FAIL",
        )
        assert multi.primary_event == CLINICAL_NEGATIVE_PH3
        assert STRATEGIC_REVIEW in multi.secondary_events

    def test_fda_approval_with_strategic_review_primary_is_approval(self):
        multi = classify_headline_multi(
            "FDA approved Company X's drug; company exploring strategic alternatives",
            ticker="APRX",
        )
        assert multi.primary_event == FDA_APPROVAL

    def test_multi_event_has_combined_deltas(self):
        multi = classify_headline_multi(
            "Phase 3 trial failed to meet primary endpoint; company exploring strategic alternatives",
            ticker="FAIL",
        )
        # Combined deltas should include contributions from both events
        # Phase 3 failure: asset_quality very negative
        assert multi.combined_score_deltas.get("asset_quality", 0) < -0.10
        # Strategic review contributes seller_willingness (at 0.5x secondary weight)
        assert multi.combined_score_deltas.get("seller_willingness", 0) > 0

    def test_unclassified_headline_returns_unclassified(self):
        multi = classify_headline_multi(
            "Company announces Q3 earnings call date",
            ticker="TEST",
        )
        assert multi.primary_event == UNCLASSIFIED
        assert multi.confidence == 0.0


class TestClassifyHeadlineBackwardCompat:
    def test_secondary_events_field_exists(self):
        ev = classify_headline("Phase 3 met primary endpoint", ticker="T")
        assert hasattr(ev, "secondary_events")
        assert isinstance(ev.secondary_events, list)

    def test_single_event_secondary_events_empty(self):
        ev = classify_headline("Phase 3 met primary endpoint", ticker="T")
        assert ev.secondary_events == []

    def test_combined_deltas_in_score_deltas(self):
        ev = classify_headline(
            "Phase 3 failed to meet primary endpoint; exploring strategic alternatives",
            ticker="FAIL",
        )
        # Primary: clinical_negative_ph3 (with secondary strategic_review)
        assert ev.event_type == CLINICAL_NEGATIVE_PH3
        assert ev.score_deltas.get("asset_quality", 0) < 0
        # seller_willingness from both clinical_negative_ph3 and strategic_review
        assert ev.score_deltas.get("seller_willingness", 0) > 0


# =============================================================================
# 3. Contextual hedging
# =============================================================================


class TestContextualHedging:
    def test_positive_safety_did_not_observe_toxicities_not_hedged(self):
        """
        'Did not observe dose-limiting toxicities' is positive safety language.
        The rule-based classifier may not extract a positive signal (no explicit
        efficacy pattern), but it must NOT classify it as negative — the phrase
        should not trigger hedging that suppresses or inverts direction.
        """
        ev = classify_headline(
            "Phase 1 dose escalation study: drug was well tolerated, "
            "did not observe dose-limiting toxicities at any dose level",
            ticker="SAFE",
        )
        # Key invariant: this must NOT be classified as negative.
        # Positive safety language should not cause a false-negative event_type.
        assert ev.direction != "negative"
        assert ev.event_type not in {
            "clinical_negative_ph1", "clinical_negative",
            "trial_discontinuation", "clinical_mixed",
        }

    def test_did_not_meet_primary_endpoint_is_negative(self):
        """
        'Did not meet primary endpoint' is still correctly classified as negative
        (captured by specific _CLINICAL_NEG patterns, not hedge detection).
        """
        ev = classify_headline(
            "Phase 3 study did not meet its primary endpoint",
            ticker="FAIL",
        )
        assert ev.event_type == CLINICAL_NEGATIVE_PH3
        assert ev.direction == "negative"

    def test_no_saes_observed_not_penalised(self):
        ev = classify_headline(
            "Phase 1 trial: no serious adverse events observed in cohort 1",
            ticker="SAFE2",
        )
        # Should not be classified as negative; SAE-clear is positive safety.
        # The classifier may return unclassified (no explicit efficacy signal),
        # but it must never return a negative clinical event.
        assert ev.direction != "negative"
        assert ev.event_type not in {"clinical_negative_ph1", "clinical_negative", "clinical_mixed"}

    def test_not_statistically_significant_still_hedges_positive(self):
        """
        'Not statistically significant' should still reduce confidence
        for a positive-leaning headline.
        """
        ev_hedged = classify_headline(
            "Phase 2 showed numerically better but not statistically significant improvement",
            ticker="MIXD",
        )
        ev_clean = classify_headline(
            "Phase 2 showed statistically significant improvement",
            ticker="MIXD",
        )
        assert ev_hedged.confidence < ev_clean.confidence


# =============================================================================
# 4. FDA approval multi-feature delta
# =============================================================================


class TestFDAApprovalDelta:
    def test_asset_quality_positive(self):
        ev = classify_headline(
            "FDA approved Company X's treatment for relapsed lymphoma",
            ticker="APRX",
        )
        assert ev.score_deltas.get("asset_quality", 0) > 0

    def test_seller_willingness_reduced(self):
        """
        Approval means catalyst has passed; seller less desperate to sell.
        """
        ev = classify_headline(
            "FDA approved Company X's treatment for relapsed lymphoma",
            ticker="APRX",
        )
        assert ev.score_deltas.get("seller_willingness", 0) < 0

    def test_catalyst_timing_reduced(self):
        """
        Catalyst has already occurred — timing window has passed.
        """
        ev = classify_headline(
            "FDA approved Company X's treatment for relapsed lymphoma",
            ticker="APRX",
        )
        assert ev.score_deltas.get("catalyst_timing", 0) < 0


# =============================================================================
# 5. Acquirer feature split
# =============================================================================


class TestAcquirerFeatureSplit:
    def test_bd_appetite_event_hits_acquirer_appetite(self):
        ev = classify_headline(
            "CEO says bolt-on acquisitions remain a key business development priority",
            ticker="AZN",
        )
        assert ev.event_type == ACQUIRER_BD_APPETITE
        # Should now populate acquirer_appetite, not acquirer_fit
        assert ev.score_deltas.get("acquirer_appetite", 0) > 0

    def test_large_deal_hits_appetite_and_integration_capacity(self):
        ev = classify_headline(
            "Pfizer completed acquisition of Seagen for $43 billion",
            ticker="PFE",
        )
        assert ev.event_type == ACQUIRER_LARGE_DEAL
        assert ev.score_deltas.get("acquirer_appetite", 0) < 0
        assert ev.score_deltas.get("integration_capacity", 0) < 0

    def test_patent_cliff_hits_urgency_and_appetite(self):
        ev = classify_headline(
            "MRK faces significant patent cliff in 2028 with loss of exclusivity on Keytruda",
            ticker="MRK",
        )
        assert ev.event_type == PATENT_CLIFF
        assert ev.score_deltas.get("acquirer_urgency", 0) > 0
        assert ev.score_deltas.get("acquirer_appetite", 0) > 0

    def test_acquirer_fit_not_used_for_large_deal(self):
        ev = classify_headline(
            "Pfizer completed acquisition of Seagen for $43 billion",
            ticker="PFE",
        )
        # acquirer_fit should NOT be present (was the old overloaded key)
        assert "acquirer_fit" not in ev.score_deltas

    def test_acquirer_fit_not_used_for_patent_cliff(self):
        ev = classify_headline(
            "Company faces loss of exclusivity in 2027",
            ticker="MRK",
        )
        assert "acquirer_fit" not in ev.score_deltas


# =============================================================================
# 6. Evidence coverage score
# =============================================================================


class TestEvidenceCoverage:
    def test_zero_events_all_domains_zero(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        cov = ledger.compute_evidence_coverage("NODATA")
        assert cov["clinical"] == 0.0
        assert cov["regulatory"] == 0.0
        assert cov["financial"] == 0.0
        assert cov["acquirer"] == 0.0
        assert cov["overall"] == 0.0
        assert cov["n_events"] == 0

    def test_clinical_event_increases_clinical_coverage(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = EvidenceRecord(
            ticker="RVMD", event_date="2025-01-01",
            event_type="clinical_positive_ph3", direction="positive",
            source_type="press_release", source_url="https://example.com",
            raw_text="Phase 3 met endpoint", confidence=0.80,
            match_reasons=["clinical_positive_ph3"],
            phase_detected="Phase 3", score_deltas={"asset_quality": 0.12},
        )
        ledger.append(rec)
        cov = ledger.compute_evidence_coverage("RVMD")
        assert cov["clinical"] > 0.0
        assert cov["n_events"] == 1

    def test_multi_domain_events_raise_overall(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        for evt_type in ["clinical_positive_ph3", "fda_approval", "strategic_review", "patent_cliff"]:
            rec = EvidenceRecord(
                ticker="MULTI", event_date="2025-01-01",
                event_type=evt_type, direction="positive",
                source_type="press_release", source_url="https://example.com",
                raw_text=f"Event: {evt_type}", confidence=0.80,
                match_reasons=[evt_type], phase_detected=None,
                score_deltas={},
            )
            ledger.append(rec)
        cov = ledger.compute_evidence_coverage("MULTI")
        assert cov["overall"] > 0.0
        assert cov["n_events"] == 4

    def test_overall_is_mean_of_domains(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = EvidenceRecord(
            ticker="ONE", event_date="2025-01-01",
            event_type="fda_approval", direction="positive",
            source_type="fda_website", source_url="https://fda.gov",
            raw_text="FDA approved", confidence=0.95,
            match_reasons=["fda_approval"], phase_detected=None,
            score_deltas={"asset_quality": 0.12},
        )
        ledger.append(rec)
        cov = ledger.compute_evidence_coverage("ONE")
        expected = round((cov["clinical"] + cov["regulatory"] + cov["financial"] + cov["acquirer"]) / 4, 4)
        assert cov["overall"] == expected


# =============================================================================
# Event deduplication (event_hash)
# =============================================================================


class TestEventHash:
    def test_same_inputs_same_hash(self):
        h1 = _compute_event_hash("RVMD", "Phase 3 met endpoint", "2025-01-01", "clinical_positive_ph3")
        h2 = _compute_event_hash("RVMD", "Phase 3 met endpoint", "2025-01-01", "clinical_positive_ph3")
        assert h1 == h2

    def test_different_ticker_different_hash(self):
        h1 = _compute_event_hash("RVMD", "Phase 3 met endpoint", "2025-01-01", "clinical_positive_ph3")
        h2 = _compute_event_hash("ALNY", "Phase 3 met endpoint", "2025-01-01", "clinical_positive_ph3")
        assert h1 != h2

    def test_hash_is_16_chars(self):
        h = _compute_event_hash("TEST", "headline", "2025-01-01", "unclassified")
        assert len(h) == 16

    def test_whitespace_normalised(self):
        h1 = _compute_event_hash("TEST", "Phase   3   met  endpoint", "2025-01-01", "cp3")
        h2 = _compute_event_hash("TEST", "Phase 3 met endpoint", "2025-01-01", "cp3")
        assert h1 == h2

    def test_from_classification_sets_hash(self):
        from bve.ingestion.event_classifier import classify_headline
        ev = classify_headline("Phase 3 met primary endpoint", ticker="RVMD")
        rec = EvidenceRecord.from_classification(ev, event_date="2025-01-01", source_url="https://x.com")
        assert len(rec.event_hash) == 16
        assert rec.event_hash != ""


class TestDeduplication:
    def test_is_duplicate_false_for_empty_ledger(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = EvidenceRecord(
            ticker="T", event_date="2025-01-01", event_type="crl", direction="negative",
            source_type="sec_filing", source_url="", raw_text="CRL received",
            confidence=0.9, match_reasons=["crl"], phase_detected=None,
            score_deltas={}, event_hash="abc123def456ab12",
        )
        assert not ledger.is_duplicate(rec)

    def test_is_duplicate_true_after_append(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = EvidenceRecord(
            ticker="T", event_date="2025-01-01", event_type="crl", direction="negative",
            source_type="sec_filing", source_url="", raw_text="CRL received",
            confidence=0.9, match_reasons=["crl"], phase_detected=None,
            score_deltas={}, event_hash="abc123def456ab12",
        )
        ledger.append(rec)
        assert ledger.is_duplicate(rec)

    def test_append_if_not_duplicate_returns_true_first_time(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = EvidenceRecord(
            ticker="T", event_date="2025-01-01", event_type="btd", direction="positive",
            source_type="press_release", source_url="", raw_text="BTD granted",
            confidence=0.8, match_reasons=["btd"], phase_detected=None,
            score_deltas={}, event_hash="deadbeef12345678",
        )
        assert ledger.append_if_not_duplicate(rec) is True

    def test_append_if_not_duplicate_returns_false_second_time(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = EvidenceRecord(
            ticker="T", event_date="2025-01-01", event_type="btd", direction="positive",
            source_type="press_release", source_url="", raw_text="BTD granted",
            confidence=0.8, match_reasons=["btd"], phase_detected=None,
            score_deltas={}, event_hash="deadbeef12345678",
        )
        ledger.append(rec)
        assert ledger.append_if_not_duplicate(rec) is False

    def test_same_event_different_sources_deduped_by_hash(self, tmp_path):
        """
        Two records from different sources (news + press_release) with same
        content should share the same hash and the second should be rejected.
        """
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        hash_val = _compute_event_hash("RVMD", "Phase 3 positive results", "2025-06-01", "clinical_positive_ph3")
        rec1 = EvidenceRecord(
            ticker="RVMD", event_date="2025-06-01",
            event_type="clinical_positive_ph3", direction="positive",
            source_type="press_release", source_url="https://pr.com",
            raw_text="Phase 3 positive results", confidence=0.80,
            match_reasons=["clinical_positive_ph3"], phase_detected="Phase 3",
            score_deltas={"asset_quality": 0.12}, event_hash=hash_val,
        )
        rec2 = EvidenceRecord(
            ticker="RVMD", event_date="2025-06-01",
            event_type="clinical_positive_ph3", direction="positive",
            source_type="news_article", source_url="https://news.com",
            raw_text="Phase 3 positive results", confidence=0.70,
            match_reasons=["clinical_positive_ph3"], phase_detected="Phase 3",
            score_deltas={"asset_quality": 0.12}, event_hash=hash_val,
        )
        ledger.append(rec1)
        added = ledger.append_if_not_duplicate(rec2)
        assert added is False
        assert len(ledger.all_tickers()) == 1


# =============================================================================
# published_date no-lookahead discipline
# =============================================================================


class TestPublishedDateNoLookahead:
    def _make_rec(self, ticker: str, event_date: str, published_date: str | None, **kwargs) -> EvidenceRecord:
        return EvidenceRecord(
            ticker=ticker,
            event_date=event_date,
            event_type="clinical_positive_ph3",
            direction="positive",
            source_type="press_release",
            source_url="https://example.com",
            raw_text="Phase 3 positive",
            confidence=0.80,
            match_reasons=["clinical_positive_ph3"],
            phase_detected="Phase 3",
            score_deltas={"asset_quality": 0.12},
            published_date=published_date,
            **kwargs,
        )

    def test_published_date_set_on_from_classification(self):
        from bve.ingestion.event_classifier import classify_headline
        ev = classify_headline("Phase 3 met primary endpoint", ticker="RVMD")
        rec = EvidenceRecord.from_classification(
            ev, event_date="2025-06-01",
            source_url="https://x.com",
            published_date="2025-06-02",
        )
        assert rec.published_date == "2025-06-02"

    def test_use_published_date_excludes_future_unpublished(self, tmp_path):
        """
        Event occurred on 2025-06-01 but won't be published until 2025-06-05.
        As of 2025-06-03, it should NOT appear in no-lookahead replay.
        """
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = self._make_rec("RVMD", event_date="2025-06-01", published_date="2025-06-05")
        ledger.append(rec)

        # Without no-lookahead: event_date <= 2025-06-03 → included
        records_all = ledger.get_records(ticker="RVMD", until_date=date(2025, 6, 3))
        assert len(records_all) == 1

        # With no-lookahead: published_date 2025-06-05 > 2025-06-03 → excluded
        records_nla = ledger.get_records(
            ticker="RVMD", until_date=date(2025, 6, 3), use_published_date=True
        )
        assert len(records_nla) == 0

    def test_use_published_date_includes_after_publish(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = self._make_rec("RVMD", event_date="2025-06-01", published_date="2025-06-05")
        ledger.append(rec)

        records = ledger.get_records(
            ticker="RVMD", until_date=date(2025, 6, 10), use_published_date=True
        )
        assert len(records) == 1

    def test_compute_score_state_with_published_date(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = self._make_rec("RVMD", event_date="2025-06-01", published_date="2025-06-10")
        ledger.append(rec)

        # Before publication: score should be unchanged from seed
        scores_before = ledger.compute_score_state(
            "RVMD", as_of_date=date(2025, 6, 5), use_published_date=True
        )
        assert scores_before["asset_quality"] == DEFAULT_SEED_SCORES["asset_quality"]

        # After publication: score updated
        scores_after = ledger.compute_score_state(
            "RVMD", as_of_date=date(2025, 6, 15), use_published_date=True
        )
        assert scores_after["asset_quality"] > DEFAULT_SEED_SCORES["asset_quality"]


# =============================================================================
# Stale evidence decay
# =============================================================================


class TestStaleEvidenceDecay:
    def _make_acquirer_rec(self, event_date: str) -> EvidenceRecord:
        return EvidenceRecord(
            ticker="AZN", event_date=event_date,
            event_type="acquirer_bd_appetite", direction="positive",
            source_type="news_article", source_url="",
            raw_text="BD appetite remains priority", confidence=0.70,
            match_reasons=["acquirer_bd_appetite"], phase_detected=None,
            score_deltas={"acquirer_appetite": 0.05},
        )

    def test_decay_half_life_defined_for_acquirer_events(self):
        assert "acquirer_bd_appetite" in DECAY_HALF_LIFE_DAYS
        assert DECAY_HALF_LIFE_DAYS["acquirer_bd_appetite"] > 0

    def test_fresh_event_no_decay(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = self._make_acquirer_rec("2025-06-01")
        ledger.append(rec)
        # As of same day: decay weight = 1.0 (age_days = 0)
        scores = ledger.compute_score_state(
            "AZN", as_of_date=date(2025, 6, 1), apply_decay=True
        )
        expected = DEFAULT_SEED_SCORES["acquirer_appetite"] + 0.05
        assert abs(scores["acquirer_appetite"] - expected) < 0.001

    def test_stale_event_decays(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = self._make_acquirer_rec("2024-01-01")
        ledger.append(rec)
        half_life = DECAY_HALF_LIFE_DAYS["acquirer_bd_appetite"]  # 90 days
        age = (date(2025, 6, 1) - date(2024, 1, 1)).days
        expected_decay = math.exp(-math.log(2) * age / half_life)
        # 18-month-old event with 90d half-life: ~6 half-lives → decay ≈ 0.019
        assert expected_decay < 0.05  # well below 1.0, significantly decayed

        scores_decayed = ledger.compute_score_state(
            "AZN", as_of_date=date(2025, 6, 1), apply_decay=True
        )
        scores_no_decay = ledger.compute_score_state(
            "AZN", as_of_date=date(2025, 6, 1), apply_decay=False
        )
        # Decayed score should be closer to seed than no-decay score
        seed = DEFAULT_SEED_SCORES["acquirer_appetite"]
        assert abs(scores_decayed["acquirer_appetite"] - seed) < abs(scores_no_decay["acquirer_appetite"] - seed)

    def test_clinical_failure_does_not_decay(self, tmp_path):
        ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
        rec = EvidenceRecord(
            ticker="FAIL", event_date="2020-01-01",
            event_type="clinical_negative_ph3", direction="negative",
            source_type="press_release", source_url="",
            raw_text="Phase 3 failed", confidence=0.90,
            match_reasons=["clinical_negative_ph3"], phase_detected="Phase 3",
            score_deltas={"asset_quality": -0.25},
        )
        ledger.append(rec)
        # clinical_negative_ph3 has no entry in DECAY_HALF_LIFE_DAYS → no decay
        assert "clinical_negative_ph3" not in DECAY_HALF_LIFE_DAYS
        scores_decayed = ledger.compute_score_state(
            "FAIL", as_of_date=date(2025, 6, 1), apply_decay=True
        )
        scores_no_decay = ledger.compute_score_state(
            "FAIL", as_of_date=date(2025, 6, 1), apply_decay=False
        )
        # Should be identical — no decay for clinical failures
        assert scores_decayed["asset_quality"] == scores_no_decay["asset_quality"]


# =============================================================================
# DEFAULT_SEED_SCORES and SOURCE_PRIORITY constants
# =============================================================================


class TestNewConstants:
    def test_acquirer_appetite_in_default_seed_scores(self):
        assert "acquirer_appetite" in DEFAULT_SEED_SCORES

    def test_acquirer_urgency_in_default_seed_scores(self):
        assert "acquirer_urgency" in DEFAULT_SEED_SCORES

    def test_integration_capacity_in_default_seed_scores(self):
        assert "integration_capacity" in DEFAULT_SEED_SCORES

    def test_source_priority_fda_highest(self):
        assert SOURCE_PRIORITY["fda_website"] > SOURCE_PRIORITY["news_article"]
        assert SOURCE_PRIORITY["sec_filing"] > SOURCE_PRIORITY["news_article"]
        assert SOURCE_PRIORITY["fda_website"] > SOURCE_PRIORITY["press_release"]
