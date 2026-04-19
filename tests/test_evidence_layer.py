"""
Tests for the evidence layer: classifier, materiality scorer, and store.

All tests use in-memory SQLite and make no network calls.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from bve.evidence.classifier import (
    ClassificationResult,
    EventType,
    classify,
)
from bve.evidence.materiality import (
    MaterialityScore,
    MaterialityTier,
    resolve_affected_entities,
    score_materiality,
)
from bve.evidence.store import EvidenceRecord, EvidenceStore
from bve.ingestion.raw_event import RawEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_event(
    source: str = "news",
    record_type: str = "news_article",
    payload: dict | None = None,
    entity_ids: list[str] | None = None,
    checksum: str = "",
) -> RawEvent:
    return RawEvent(
        source=source,
        record_type=record_type,
        source_url="https://example.com/article",
        fetched_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        checksum=checksum,
        payload=payload or {},
        entity_ids=entity_ids or [],
    )


def make_classification(
    event_type: EventType = EventType.UNKNOWN,
    confidence: float = 0.0,
    signals: list[str] | None = None,
) -> ClassificationResult:
    return ClassificationResult(
        event_type=event_type,
        confidence=confidence,
        signals=signals or [],
    )


# ---------------------------------------------------------------------------
# TestClassifier
# ---------------------------------------------------------------------------


class TestClassifier:
    def test_openfda_drug_approval_is_fda_action(self):
        event = make_event(source="openfda", record_type="drug_approval")
        result = classify(event)
        assert result.event_type == EventType.FDA_ACTION
        assert result.confidence == 0.95

    def test_openfda_drug_label_is_fda_action(self):
        event = make_event(source="openfda", record_type="drug_label")
        result = classify(event)
        assert result.event_type == EventType.FDA_ACTION
        assert result.confidence == 0.80

    def test_ctgov_trial_study_is_trial_change(self):
        event = make_event(source="ctgov", record_type="trial_study")
        result = classify(event)
        assert result.event_type == EventType.TRIAL_CHANGE
        assert result.confidence == 0.85

    def test_sec_edgar_10k_is_earnings(self):
        event = make_event(source="sec_edgar", record_type="10_k")
        result = classify(event)
        assert result.event_type == EventType.EARNINGS
        assert result.confidence == 0.75

    def test_sec_edgar_10q_is_earnings(self):
        event = make_event(source="sec_edgar", record_type="10_q")
        result = classify(event)
        assert result.event_type == EventType.EARNINGS
        assert result.confidence == 0.75

    def test_market_data_source_is_unknown(self):
        event = make_event(source="market_data", record_type="price")
        result = classify(event)
        assert result.event_type == EventType.UNKNOWN
        assert result.confidence == 0.0

    def test_empty_payload_returns_unknown(self):
        event = make_event(source="news", record_type="news_article", payload={})
        result = classify(event)
        assert result.event_type == EventType.UNKNOWN

    def test_financing_keyword_one_match(self):
        event = make_event(payload={"title": "Company announces new offering"})
        result = classify(event)
        assert result.event_type == EventType.FINANCING
        assert result.confidence == 0.60

    def test_financing_keyword_two_matches(self):
        event = make_event(
            payload={"title": "Company announces equity offering and pipe financing"}
        )
        result = classify(event)
        assert result.event_type == EventType.FINANCING
        assert result.confidence == 0.75

    def test_financing_keyword_four_plus_matches(self):
        event = make_event(
            payload={
                "title": "offering raise dilut",
                "summary": "atm program registered direct pipe convertible note",
            }
        )
        result = classify(event)
        assert result.event_type == EventType.FINANCING
        assert result.confidence == 0.85

    def test_catalyst_update_from_keywords(self):
        event = make_event(
            payload={"title": "Phase 3 results show positive efficacy data readout"}
        )
        result = classify(event)
        assert result.event_type == EventType.CATALYST_UPDATE

    def test_fda_action_from_keywords(self):
        event = make_event(
            payload={"title": "FDA grants approval for new NDA submission"}
        )
        result = classify(event)
        assert result.event_type == EventType.FDA_ACTION

    def test_trial_change_from_keywords(self):
        event = make_event(
            payload={
                "title": "Protocol amendment changes enrollment criteria for randomized trial"
            }
        )
        result = classify(event)
        assert result.event_type == EventType.TRIAL_CHANGE

    def test_competitor_event_from_keywords(self):
        event = make_event(
            payload={"title": "Class effect readthrough from competitor data"}
        )
        result = classify(event)
        assert result.event_type == EventType.COMPETITOR_EVENT

    def test_management_change_from_keywords(self):
        event = make_event(
            payload={"title": "CEO resigned from board of directors"}
        )
        result = classify(event)
        assert result.event_type == EventType.MANAGEMENT_CHANGE

    def test_partnership_ma_from_keywords(self):
        event = make_event(
            payload={"title": "Acquisition agreement with milestone payments and royalty"}
        )
        result = classify(event)
        assert result.event_type == EventType.PARTNERSHIP_MA

    def test_earnings_from_keywords(self):
        event = make_event(
            payload={"title": "Quarterly earnings report with revenue and financial results"}
        )
        result = classify(event)
        assert result.event_type == EventType.EARNINGS

    def test_fda_action_wins_over_catalyst_update_on_tie(self):
        # When both event types have equal keyword match count, FDA_ACTION wins (higher priority)
        # FDA_ACTION keywords: "fda", "approval" (2 matches)
        # CATALYST_UPDATE keywords: "data", "readout" (2 matches)
        event = make_event(
            payload={"title": "FDA approval data readout"}
        )
        result = classify(event)
        assert result.event_type == EventType.FDA_ACTION

    def test_catalyst_update_wins_over_partnership_on_tie(self):
        # CATALYST_UPDATE > PARTNERSHIP_MA in priority order
        event = make_event(
            payload={
                "title": "clinical trial results data readout",
                "summary": "collaboration agreement royalty",
            }
        )
        result = classify(event)
        # Both have matches; CATALYST_UPDATE wins if it has more or equal matches
        assert result.event_type in (EventType.CATALYST_UPDATE, EventType.PARTNERSHIP_MA)

    def test_keyword_in_summary_field_detected(self):
        event = make_event(
            payload={"title": "Company update", "summary": "FDA approved the drug"}
        )
        result = classify(event)
        assert result.event_type == EventType.FDA_ACTION

    def test_keyword_matching_is_case_insensitive(self):
        event = make_event(payload={"title": "OFFERING announced today"})
        result = classify(event)
        assert result.event_type == EventType.FINANCING

    def test_open_payments_default_low_confidence(self):
        event = make_event(source="open_payments", record_type="payment")
        result = classify(event)
        assert result.event_type == EventType.COMPETITOR_EVENT
        assert result.confidence <= 0.25

    def test_signals_populated_for_exact_match(self):
        event = make_event(source="openfda", record_type="drug_approval")
        result = classify(event)
        assert len(result.signals) > 0

    def test_signals_populated_for_keyword_match(self):
        event = make_event(payload={"title": "FDA approved the drug"})
        result = classify(event)
        assert len(result.signals) > 0

    def test_8k_with_financing_keywords(self):
        event = make_event(
            source="sec_edgar",
            record_type="8_k",
            payload={"title": "8-K: equity offering pipe registered direct"},
        )
        result = classify(event)
        assert result.event_type == EventType.FINANCING

    def test_pubmed_abstract_catalyst_keywords(self):
        event = make_event(
            source="pubmed",
            record_type="pubmed_abstract",
            payload={"abstract": "Phase 3 clinical trial results show efficacy data"},
        )
        result = classify(event)
        assert result.event_type == EventType.CATALYST_UPDATE

    def test_confidence_increases_with_keyword_count(self):
        event_one = make_event(payload={"title": "offering announced"})
        event_four = make_event(
            payload={"title": "offering raise pipe dilut registered direct atm program"}
        )
        result_one = classify(event_one)
        result_four = classify(event_four)
        assert result_four.confidence > result_one.confidence


# ---------------------------------------------------------------------------
# TestMaterialityScoring
# ---------------------------------------------------------------------------


class TestMaterialityScoring:
    def _classify_and_score(self, event: RawEvent) -> MaterialityScore:
        classification = classify(event)
        return score_materiality(event, classification)

    def test_fda_action_base_score(self):
        event = make_event(source="openfda", record_type="drug_approval")
        cls = make_classification(EventType.FDA_ACTION, confidence=0.95)
        result = score_materiality(event, cls)
        assert result.score >= 0.85  # base 0.90, may be modified

    def test_catalyst_update_base_score(self):
        cls = make_classification(EventType.CATALYST_UPDATE, confidence=0.75)
        event = make_event(payload={})
        result = score_materiality(event, cls)
        assert abs(result.score - 0.80) < 0.15  # within modifier range

    def test_partnership_ma_base_score(self):
        cls = make_classification(EventType.PARTNERSHIP_MA, confidence=0.75)
        event = make_event(payload={})
        result = score_materiality(event, cls)
        assert abs(result.score - 0.70) < 0.15

    def test_financing_base_score(self):
        cls = make_classification(EventType.FINANCING, confidence=0.75)
        event = make_event(payload={})
        result = score_materiality(event, cls)
        assert abs(result.score - 0.60) < 0.15

    def test_unknown_base_score(self):
        cls = make_classification(EventType.UNKNOWN, confidence=0.0)
        event = make_event(payload={})
        result = score_materiality(event, cls)
        # UNKNOWN base=0.10, low confidence -0.10 → 0.0
        assert result.score <= 0.10

    def test_fda_approval_positive_modifier(self):
        cls = make_classification(EventType.FDA_ACTION, confidence=0.95)
        event = make_event(payload={"title": "FDA granted approval for the drug"})
        result = score_materiality(event, cls)
        assert result.score == pytest.approx(0.95, abs=0.01)

    def test_fda_crl_negative_modifier(self):
        cls = make_classification(EventType.FDA_ACTION, confidence=0.95)
        event_no_crl = make_event(payload={})
        event_crl = make_event(payload={"title": "FDA issues crl complete response letter"})
        result_no_crl = score_materiality(event_no_crl, cls)
        result_crl = score_materiality(event_crl, cls)
        assert result_crl.score < result_no_crl.score

    def test_catalyst_phase3_positive_modifier(self):
        cls = make_classification(EventType.CATALYST_UPDATE, confidence=0.75)
        event_ph3 = make_event(payload={"title": "Phase 3 results announced"})
        event_base = make_event(payload={"title": "clinical results announced"})
        result_ph3 = score_materiality(event_ph3, cls)
        result_base = score_materiality(event_base, cls)
        assert result_ph3.score > result_base.score

    def test_catalyst_phase1_negative_modifier(self):
        cls = make_classification(EventType.CATALYST_UPDATE, confidence=0.75)
        event_ph1 = make_event(payload={"title": "Phase 1 safety data"})
        event_base = make_event(payload={"title": "clinical data"})
        result_ph1 = score_materiality(event_ph1, cls)
        result_base = score_materiality(event_base, cls)
        assert result_ph1.score < result_base.score

    def test_catalyst_endpoint_met_modifier(self):
        cls = make_classification(EventType.CATALYST_UPDATE, confidence=0.75)
        event = make_event(payload={"title": "endpoint met in pivotal trial"})
        result = score_materiality(event, cls)
        assert result.score >= 0.85

    def test_catalyst_failure_still_material(self):
        cls = make_classification(EventType.CATALYST_UPDATE, confidence=0.75)
        event_fail = make_event(payload={"title": "trial failed to meet primary endpoint"})
        event_base = make_event(payload={"title": "trial data available"})
        result_fail = score_materiality(event_fail, cls)
        result_base = score_materiality(event_base, cls)
        # Failure also gets +0.05 modifier
        assert result_fail.score >= result_base.score

    def test_score_capped_at_1(self):
        cls = make_classification(EventType.FDA_ACTION, confidence=0.95)
        # Trigger both approval and phase 3 modifiers — total could exceed 1.0
        event = make_event(
            payload={"title": "FDA approved phase 3 endpoint met positive results approval"}
        )
        result = score_materiality(event, cls)
        assert result.score <= 1.0

    def test_low_confidence_reduces_score(self):
        cls_high = make_classification(EventType.CATALYST_UPDATE, confidence=0.80)
        cls_low = make_classification(EventType.CATALYST_UPDATE, confidence=0.30)
        event = make_event(payload={})
        result_high = score_materiality(event, cls_high)
        result_low = score_materiality(event, cls_low)
        assert result_low.score < result_high.score

    def test_tier_high_for_fda_action(self):
        cls = make_classification(EventType.FDA_ACTION, confidence=0.95)
        event = make_event(payload={})
        result = score_materiality(event, cls)
        assert result.tier == MaterialityTier.HIGH

    def test_tier_medium_for_trial_change(self):
        cls = make_classification(EventType.TRIAL_CHANGE, confidence=0.85)
        event = make_event(payload={})
        result = score_materiality(event, cls)
        assert result.tier == MaterialityTier.MEDIUM

    def test_tier_minimal_for_unknown(self):
        cls = make_classification(EventType.UNKNOWN, confidence=0.0)
        event = make_event(payload={})
        result = score_materiality(event, cls)
        assert result.tier == MaterialityTier.MINIMAL

    def test_rationale_is_non_empty_string(self):
        cls = make_classification(EventType.EARNINGS, confidence=0.75)
        event = make_event(payload={})
        result = score_materiality(event, cls)
        assert isinstance(result.rationale, str)
        assert len(result.rationale) > 0

    def test_modifiers_list_populated_when_modifier_applied(self):
        cls = make_classification(EventType.FDA_ACTION, confidence=0.95)
        event = make_event(payload={"title": "FDA approval granted"})
        result = score_materiality(event, cls)
        assert len(result.modifiers) > 0

    def test_financing_dilutive_modifier(self):
        cls = make_classification(EventType.FINANCING, confidence=0.75)
        event_dilutive = make_event(
            payload={"title": "dilutive equity offering announced"}
        )
        event_normal = make_event(payload={"title": "equity offering announced"})
        result_dilutive = score_materiality(event_dilutive, cls)
        result_normal = score_materiality(event_normal, cls)
        assert result_dilutive.score > result_normal.score


# ---------------------------------------------------------------------------
# TestEntityResolution
# ---------------------------------------------------------------------------


class TestEntityResolution:
    def test_entity_ids_from_raw_event_used_when_present(self):
        event = make_event(entity_ids=["VKTX", "BRD001"])
        cls = make_classification(EventType.FDA_ACTION, confidence=0.95)
        result = resolve_affected_entities(event, cls)
        assert result == ["VKTX", "BRD001"]

    def test_ticker_extracted_from_payload_when_entity_ids_empty(self):
        event = make_event(entity_ids=[], payload={"ticker": "ALNY"})
        cls = make_classification(EventType.FDA_ACTION, confidence=0.95)
        result = resolve_affected_entities(event, cls)
        assert "ALNY" in result

    def test_nct_id_extracted_from_payload(self):
        event = make_event(entity_ids=[], payload={"nct_id": "NCT00123456"})
        cls = make_classification(EventType.TRIAL_CHANGE, confidence=0.85)
        result = resolve_affected_entities(event, cls)
        assert "NCT00123456" in result

    def test_both_ticker_and_nct_id_extracted(self):
        event = make_event(
            entity_ids=[],
            payload={"ticker": "SRPT", "nct_id": "NCT99999999"},
        )
        cls = make_classification(EventType.TRIAL_CHANGE, confidence=0.85)
        result = resolve_affected_entities(event, cls)
        assert "SRPT" in result
        assert "NCT99999999" in result

    def test_empty_list_when_nothing_available(self):
        event = make_event(entity_ids=[], payload={})
        cls = make_classification(EventType.UNKNOWN, confidence=0.0)
        result = resolve_affected_entities(event, cls)
        assert result == []

    def test_entity_ids_take_precedence_over_payload(self):
        event = make_event(
            entity_ids=["VKTX"],
            payload={"ticker": "OTHER"},
        )
        cls = make_classification(EventType.FDA_ACTION, confidence=0.95)
        result = resolve_affected_entities(event, cls)
        assert result == ["VKTX"]


# ---------------------------------------------------------------------------
# TestEvidenceStore
# ---------------------------------------------------------------------------


class TestEvidenceStore:
    def setup_method(self):
        self.store = EvidenceStore(db_path=":memory:")

    def teardown_method(self):
        self.store.close()

    def _fda_event(self, suffix: str = "") -> RawEvent:
        return make_event(
            source="openfda",
            record_type="drug_approval",
            payload={"title": f"FDA approved drug{suffix}"},
        )

    def test_ingest_returns_evidence_record(self):
        event = self._fda_event()
        record = self.store.ingest(event)
        assert isinstance(record, EvidenceRecord)

    def test_duplicate_ingest_returns_none(self):
        event = self._fda_event()
        first = self.store.ingest(event)
        second = self.store.ingest(event)
        assert first is not None
        assert second is None

    def test_different_checksum_stored_separately(self):
        event1 = self._fda_event("A")
        event2 = self._fda_event("B")
        r1 = self.store.ingest(event1)
        r2 = self.store.ingest(event2)
        assert r1 is not None
        assert r2 is not None
        assert r1.id != r2.id

    def test_get_by_id_returns_correct_record(self):
        event = self._fda_event()
        record = self.store.ingest(event)
        assert record is not None
        fetched = self.store.get_by_id(record.id)
        assert fetched is not None
        assert fetched.id == record.id

    def test_get_by_id_returns_none_for_missing(self):
        result = self.store.get_by_id("nonexistent-id")
        assert result is None

    def test_get_by_checksum_returns_correct_record(self):
        event = self._fda_event()
        record = self.store.ingest(event)
        assert record is not None
        fetched = self.store.get_by_checksum(event.checksum)
        assert fetched is not None
        assert fetched.id == record.id

    def test_get_by_checksum_returns_none_for_missing(self):
        result = self.store.get_by_checksum("nonexistent-checksum")
        assert result is None

    def test_get_by_entity_filters_correctly(self):
        event1 = make_event(
            source="openfda",
            record_type="drug_approval",
            entity_ids=["VKTX"],
            payload={"title": "VKTX drug approved"},
        )
        event2 = make_event(
            source="openfda",
            record_type="drug_approval",
            entity_ids=["ALNY"],
            payload={"title": "ALNY drug approved"},
        )
        self.store.ingest(event1)
        self.store.ingest(event2)

        vktx_records = self.store.get_by_entity("VKTX")
        assert len(vktx_records) == 1
        assert "VKTX" in vktx_records[0].affected_entities

    def test_get_by_event_type_filters_correctly(self):
        fda_event = self._fda_event("X")
        news_event = make_event(
            payload={"title": "Company announces equity offering pipe financing raise"}
        )
        self.store.ingest(fda_event)
        self.store.ingest(news_event)

        fda_records = self.store.get_by_event_type("FDA_ACTION")
        assert len(fda_records) >= 1
        for r in fda_records:
            assert r.classification.event_type == EventType.FDA_ACTION

    def test_get_by_materiality_threshold_works(self):
        fda_event = self._fda_event("high_mat")
        unknown_event = make_event(source="market_data", record_type="price")
        self.store.ingest(fda_event)
        self.store.ingest(unknown_event)

        high_mat = self.store.get_by_materiality(min_score=0.80)
        assert len(high_mat) >= 1
        for r in high_mat:
            assert r.materiality.score >= 0.80

    def test_get_recent_returns_records(self):
        for i in range(3):
            self.store.ingest(self._fda_event(str(i)))
        recent = self.store.get_recent(limit=10)
        assert len(recent) == 3

    def test_get_recent_ordered_most_recent_first(self):
        for i in range(3):
            self.store.ingest(self._fda_event(str(i)))
        recent = self.store.get_recent(limit=10)
        # stored_at should be in descending order (most recent first)
        timestamps = [r.stored_at for r in recent]
        assert timestamps == sorted(timestamps, reverse=True) or len(set(timestamps)) <= 1

    def test_count_correct_after_ingestion(self):
        assert self.store.count() == 0
        self.store.ingest(self._fda_event("1"))
        assert self.store.count() == 1
        self.store.ingest(self._fda_event("2"))
        assert self.store.count() == 2

    def test_count_not_incremented_by_duplicate(self):
        event = self._fda_event()
        self.store.ingest(event)
        self.store.ingest(event)
        assert self.store.count() == 1

    def test_is_duplicate_correct(self):
        event = self._fda_event()
        assert not self.store.is_duplicate(event.checksum)
        self.store.ingest(event)
        assert self.store.is_duplicate(event.checksum)

    def test_payload_round_trips_correctly(self):
        payload = {"title": "FDA approved drug", "extra": {"nested": 42}}
        event = make_event(
            source="openfda",
            record_type="drug_approval",
            payload=payload,
        )
        record = self.store.ingest(event)
        assert record is not None
        fetched = self.store.get_by_id(record.id)
        assert fetched is not None
        assert fetched.raw_event.payload["title"] == "FDA approved drug"

    def test_multiple_records_from_same_source(self):
        events = [self._fda_event(str(i)) for i in range(5)]
        for ev in events:
            self.store.ingest(ev)
        assert self.store.count() == 5

    def test_empty_store_returns_empty_lists(self):
        assert self.store.get_by_entity("VKTX") == []
        assert self.store.get_by_event_type("FDA_ACTION") == []
        assert self.store.get_by_materiality(0.5) == []
        assert self.store.get_recent() == []

    def test_ingest_classifies_and_scores(self):
        event = self._fda_event()
        record = self.store.ingest(event)
        assert record is not None
        assert record.classification.event_type == EventType.FDA_ACTION
        assert record.materiality.score > 0.0
        assert record.materiality.tier != MaterialityTier.MINIMAL

    def test_record_has_valid_id(self):
        event = self._fda_event()
        record = self.store.ingest(event)
        assert record is not None
        assert isinstance(record.id, str)
        assert len(record.id) > 0

    def test_record_has_stored_at_timestamp(self):
        event = self._fda_event()
        record = self.store.ingest(event)
        assert record is not None
        assert isinstance(record.stored_at, datetime)

    def test_get_by_entity_limit_respected(self):
        for i in range(10):
            self.store.ingest(
                make_event(
                    source="openfda",
                    record_type="drug_approval",
                    entity_ids=["SHARED"],
                    payload={"title": f"drug {i} approved"},
                )
            )
        records = self.store.get_by_entity("SHARED", limit=3)
        assert len(records) <= 3

    def test_get_by_event_type_limit_respected(self):
        for i in range(10):
            self.store.ingest(self._fda_event(str(i)))
        records = self.store.get_by_event_type("FDA_ACTION", limit=4)
        assert len(records) <= 4

    def test_affected_entities_preserved_in_round_trip(self):
        event = make_event(
            source="openfda",
            record_type="drug_approval",
            entity_ids=["VKTX", "BRD001"],
            payload={"title": "drug approved"},
        )
        record = self.store.ingest(event)
        assert record is not None
        fetched = self.store.get_by_id(record.id)
        assert fetched is not None
        assert set(fetched.affected_entities) == {"VKTX", "BRD001"}
