"""
Tests for SignalExtractor, ExtractionResult, and ExtractionValidator.

Validates:
  1. Successful extraction with a FakeLLMClient returning valid JSON.
  2. ExtractionResult fields are correctly populated on success.
  3. StructuredSignal identity fields come from context, not LLM.
  4. All failure statuses are handled gracefully (no exceptions).
  5. PromptBuilder includes document text and entity context.
  6. Batch extraction maintains positional alignment.
  7. ExtractionValidator JSON parsing handles common LLM artifacts.
  8. ExtractionValidator.build_signal() rejects invalid field values.
  9. ExtractionResult is frozen (immutable).
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

import pytest

from bve.intelligence.extraction.extractor import SignalExtractor
from bve.intelligence.extraction.llm_client import (
    FakeLLMClient,
    LLMClientError,
    LLMRateLimitError,
    LLMRefusalError,
)
from bve.intelligence.extraction.prompt_builder import PromptBuilder
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.extraction.validation import ExtractionValidator
from bve.intelligence.taxonomy import EventType


_NOW   = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
_TODAY = date(2024, 6, 1)

_HINTS = EntityHints(
    asset_id="asset-test-001",
    company_id="company-test-001",
    drug_name="AXD-101",
    indication="Psoriasis",
    ticker="ACME",
)

_VALID_LLM_JSON = json.dumps({
    "event_type": "trial_readout",
    "signal_date": "2024-03-15",
    "confidence": 0.92,
    "ambiguity_flag": False,
    "rationale": "Document describes a Phase 3 trial readout with primary endpoint met.",
    "trial_phase": "phase_3",
    "trial_nct_id": "NCT04567890",
    "primary_endpoint_met": True,
    "interim_flag": False,
    "hazard_ratio": 0.72,
    "p_value": 0.0001,
    "response_rate": 0.52,
    "safety_grade": None,
    "fda_action_type": None,
    "designation_type": None,
    "deal_value_millions": None,
    "deal_type": None,
    "payer_name": None,
})

_MINIMAL_LLM_JSON = json.dumps({
    "event_type": "fda_approval",
    "signal_date": "2024-06-01",
    "confidence": 0.95,
    "ambiguity_flag": False,
    "rationale": "Clear FDA approval announcement.",
    "fda_action_type": "approval",
    "interim_flag": False,
})


def _make_doc(text: str = "Phase 3 trial met primary endpoint.", source: str = "press_release") -> RawDocument:
    return RawDocument.from_text(
        id=str(uuid.uuid4()),
        source=source,
        title="Test Document",
        raw_text=text,
        entity_hints=_HINTS,
        retrieved_at=_NOW,
        source_url="https://example.com/test",
        published_at=_NOW,
    )


# ---------------------------------------------------------------------------
# ExtractionResult
# ---------------------------------------------------------------------------

class TestExtractionResult:
    def test_frozen(self, tmp_path):
        result = ExtractionResult(
            document_id="doc-001",
            asset_id="a",
            company_id="c",
            status=ExtractionStatus.LLM_REFUSED,
            extracted_at=_NOW,
        )
        with pytest.raises(Exception):
            result.status = ExtractionStatus.SUCCESS  # type: ignore[misc]

    def test_default_fields(self):
        result = ExtractionResult(
            document_id="doc-001",
            asset_id="a",
            company_id="c",
            status=ExtractionStatus.PARSE_ERROR,
            extracted_at=_NOW,
        )
        assert result.signal is None
        assert result.validation_errors == []
        assert result.extraction_confidence == 0.0
        assert result.ambiguity_flag is False
        assert result.rationale == ""
        assert result.raw_llm_response == ""

    def test_all_statuses_constructable(self):
        for status in ExtractionStatus:
            result = ExtractionResult(
                document_id="d",
                asset_id="a",
                company_id="c",
                status=status,
                extracted_at=_NOW,
            )
            assert result.status == status


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_system_prompt_non_empty(self):
        pb = PromptBuilder()
        system = pb.build_system_prompt()
        assert len(system) > 50
        assert "JSON" in system

    def test_user_prompt_contains_document_text(self):
        doc = _make_doc("This is very specific trial data for testing.")
        pb = PromptBuilder()
        prompt = pb.build_user_prompt(doc)
        assert "very specific trial data" in prompt

    def test_user_prompt_contains_entity_context(self):
        doc = _make_doc()
        pb = PromptBuilder()
        prompt = pb.build_user_prompt(doc)
        assert "AXD-101" in prompt
        assert "Psoriasis" in prompt
        assert "ACME" in prompt

    def test_user_prompt_contains_taxonomy(self):
        doc = _make_doc()
        pb = PromptBuilder()
        prompt = pb.build_user_prompt(doc)
        assert "trial_readout" in prompt
        assert "fda_approval" in prompt
        assert "program_discontinuation" in prompt

    def test_user_prompt_contains_schema_fields(self):
        doc = _make_doc()
        pb = PromptBuilder()
        prompt = pb.build_user_prompt(doc)
        assert "hazard_ratio" in prompt
        assert "p_value" in prompt
        assert "response_rate" in prompt
        assert "fda_action_type" in prompt

    def test_long_document_truncated(self):
        long_text = "word " * 5000  # ~25000 chars
        doc = _make_doc(long_text)
        pb = PromptBuilder()
        prompt = pb.build_user_prompt(doc)
        # Prompt should contain truncation indicator
        assert "truncated" in prompt.lower()

    def test_version_constant_non_empty(self):
        assert PromptBuilder.CURRENT_VERSION
        assert PromptBuilder.CURRENT_VERSION.startswith("v")


# ---------------------------------------------------------------------------
# ExtractionValidator — JSON parsing
# ---------------------------------------------------------------------------

class TestExtractionValidator:
    def setup_method(self):
        self.validator = ExtractionValidator()

    def test_valid_json_parsed(self):
        parsed, err = self.validator.parse_llm_response('{"event_type": "trial_readout"}')
        assert parsed == {"event_type": "trial_readout"}
        assert err is None

    def test_empty_response_fails(self):
        parsed, err = self.validator.parse_llm_response("")
        assert parsed is None
        assert err is not None

    def test_whitespace_only_fails(self):
        parsed, err = self.validator.parse_llm_response("   \n  ")
        assert parsed is None
        assert err is not None

    def test_non_json_prose_fails(self):
        parsed, err = self.validator.parse_llm_response(
            "I cannot extract structured data from this document."
        )
        assert parsed is None
        assert err is not None

    def test_markdown_code_fence_stripped(self):
        raw = "```json\n{\"event_type\": \"fda_approval\"}\n```"
        parsed, err = self.validator.parse_llm_response(raw)
        assert err is None
        assert parsed == {"event_type": "fda_approval"}

    def test_code_fence_without_json_tag_stripped(self):
        raw = "```\n{\"event_type\": \"partnership\"}\n```"
        parsed, err = self.validator.parse_llm_response(raw)
        assert err is None
        assert parsed is not None
        assert parsed.get("event_type") == "partnership"

    def test_leading_prose_stripped(self):
        raw = 'Here is the extraction result:\n{"event_type": "financing"}'
        parsed, err = self.validator.parse_llm_response(raw)
        assert err is None
        assert parsed is not None

    def test_invalid_json_returns_error(self):
        parsed, err = self.validator.parse_llm_response("{invalid json}")
        assert parsed is None
        assert "JSON parse error" in (err or "")

    def test_array_not_object_fails(self):
        parsed, err = self.validator.parse_llm_response('[{"event_type": "trial_readout"}]')
        assert parsed is None
        assert err is not None

    def test_truncated_json_fails(self):
        parsed, err = self.validator.parse_llm_response('{"event_type": "trial_readou')
        assert parsed is None
        assert err is not None

    def test_build_signal_success(self):
        doc = _make_doc()
        llm_json = {
            "event_type": "trial_readout",
            "signal_date": "2024-03-15",
            "trial_phase": "phase_3",
            "primary_endpoint_met": True,
            "hazard_ratio": 0.72,
            "p_value": 0.0001,
            "confidence": 0.9,
            "interim_flag": False,
        }
        signal, errors = self.validator.build_signal(
            llm_json=llm_json,
            document=doc,
            event_id="evt-001",
            extraction_model="fake-llm",
            extracted_at=_NOW,
        )
        assert signal is not None
        assert errors == []
        # Identity from context, not LLM
        assert signal.asset_id == "asset-test-001"
        assert signal.company_id == "company-test-001"
        assert signal.event_id == "evt-001"
        assert signal.extraction_model == "fake-llm"
        # Clinical fields from LLM
        assert signal.hazard_ratio == pytest.approx(0.72)
        assert signal.p_value == pytest.approx(0.0001)

    def test_build_signal_identity_always_from_context(self):
        """LLM cannot override asset_id or company_id."""
        doc = _make_doc()
        # Even if LLM JSON contains these fields, context wins
        llm_json = {
            "event_type": "fda_approval",
            "signal_date": "2024-06-01",
            "fda_action_type": "approval",
            "confidence": 0.9,
            "asset_id": "hacked-asset-id",      # LLM injection attempt
            "company_id": "hacked-company-id",  # LLM injection attempt
        }
        signal, errors = self.validator.build_signal(
            llm_json=llm_json,
            document=doc,
            event_id="evt-002",
            extraction_model="fake",
            extracted_at=_NOW,
        )
        assert signal is not None
        # Context always wins
        assert signal.asset_id == "asset-test-001"
        assert signal.company_id == "company-test-001"

    def test_build_signal_invalid_event_type_fails(self):
        doc = _make_doc()
        llm_json = {
            "event_type": "not_a_valid_event",
            "signal_date": "2024-06-01",
            "confidence": 0.5,
        }
        signal, errors = self.validator.build_signal(
            llm_json=llm_json, document=doc,
            event_id="evt-003", extraction_model="fake", extracted_at=_NOW,
        )
        assert signal is None
        assert len(errors) > 0

    def test_build_signal_invalid_hazard_ratio_fails(self):
        """hazard_ratio must be > 0."""
        doc = _make_doc()
        llm_json = {
            "event_type": "trial_readout",
            "signal_date": "2024-06-01",
            "hazard_ratio": -0.5,   # invalid: must be positive
            "confidence": 0.9,
        }
        signal, errors = self.validator.build_signal(
            llm_json=llm_json, document=doc,
            event_id="evt-004", extraction_model="fake", extracted_at=_NOW,
        )
        assert signal is None
        assert len(errors) > 0

    def test_build_signal_invalid_p_value_fails(self):
        """p_value must be in [0, 1]."""
        doc = _make_doc()
        llm_json = {
            "event_type": "trial_readout",
            "signal_date": "2024-06-01",
            "p_value": 1.5,  # invalid
            "confidence": 0.9,
        }
        signal, errors = self.validator.build_signal(
            llm_json=llm_json, document=doc,
            event_id="evt-005", extraction_model="fake", extracted_at=_NOW,
        )
        assert signal is None
        assert len(errors) > 0

    def test_signal_date_falls_back_to_published_at(self):
        """When LLM omits signal_date, fall back to document.published_at."""
        doc = RawDocument.from_text(
            id=str(uuid.uuid4()),
            source="manual",
            title="Test",
            raw_text="Text",
            entity_hints=_HINTS,
            published_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        )
        llm_json = {
            "event_type": "financing",
            "confidence": 0.8,
            # No signal_date
        }
        signal, errors = self.validator.build_signal(
            llm_json=llm_json, document=doc,
            event_id="evt-006", extraction_model="fake", extracted_at=_NOW,
        )
        assert signal is not None
        assert signal.signal_date == date(2024, 3, 1)


# ---------------------------------------------------------------------------
# SignalExtractor — integration (with FakeLLMClient)
# ---------------------------------------------------------------------------

class TestSignalExtractor:
    def test_successful_extraction(self):
        llm = FakeLLMClient(default_response=_VALID_LLM_JSON)
        extractor = SignalExtractor(llm_client=llm)
        doc = _make_doc()
        result = extractor.extract(doc, event_id="evt-001")

        assert result.status == ExtractionStatus.SUCCESS
        assert result.signal is not None
        assert result.signal.event_type == EventType.TRIAL_READOUT
        assert result.signal.asset_id == "asset-test-001"
        assert result.signal.company_id == "company-test-001"
        assert result.signal.event_id == "evt-001"
        assert result.extraction_confidence == pytest.approx(0.92)
        assert result.ambiguity_flag is False

    def test_result_provenance_fields(self):
        llm = FakeLLMClient(default_response=_VALID_LLM_JSON)
        extractor = SignalExtractor(llm_client=llm)
        doc = _make_doc()
        result = extractor.extract(doc, event_id="evt-001")

        assert result.document_id == doc.id
        assert result.asset_id == "asset-test-001"
        assert result.company_id == "company-test-001"
        assert result.source_url == "https://example.com/test"
        assert result.extraction_model == "fake-llm"
        assert result.prompt_version == PromptBuilder.CURRENT_VERSION

    def test_event_type_detected_on_success(self):
        llm = FakeLLMClient(default_response=_VALID_LLM_JSON)
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc())
        assert result.event_type_detected == "trial_readout"

    def test_minimal_valid_json_succeeds(self):
        llm = FakeLLMClient(default_response=_MINIMAL_LLM_JSON)
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc())
        assert result.status == ExtractionStatus.SUCCESS
        assert result.signal.event_type == EventType.FDA_APPROVAL

    def test_auto_generated_event_id_when_none(self):
        llm = FakeLLMClient(default_response=_VALID_LLM_JSON)
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc(), event_id=None)
        assert result.status == ExtractionStatus.SUCCESS
        # event_id should be a valid UUID
        assert result.signal is not None
        import uuid as _uuid
        _uuid.UUID(result.signal.event_id)  # raises if invalid

    def test_parse_error_on_non_json(self):
        llm = FakeLLMClient(default_response="Here is my analysis of the document.")
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc())
        assert result.status == ExtractionStatus.PARSE_ERROR
        assert result.signal is None
        assert len(result.validation_errors) > 0

    def test_validation_error_on_bad_fields(self):
        bad_json = json.dumps({
            "event_type": "completely_unknown_event",
            "signal_date": "2024-01-01",
            "confidence": 0.9,
        })
        llm = FakeLLMClient(default_response=bad_json)
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc())
        assert result.status == ExtractionStatus.VALIDATION_ERROR
        assert result.signal is None
        assert result.raw_llm_json is not None
        assert len(result.validation_errors) > 0

    def test_llm_refused_on_empty_response(self):
        llm = FakeLLMClient(default_response="")
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc())
        assert result.status == ExtractionStatus.LLM_REFUSED
        assert result.signal is None

    def test_llm_error_does_not_raise(self):
        class FailingLLM:
            model_id = "failing"
            def complete(self, system_prompt, user_prompt, **kw):
                raise LLMClientError("API timeout")

        extractor = SignalExtractor(llm_client=FailingLLM())
        result = extractor.extract(_make_doc())
        assert result.status == ExtractionStatus.LLM_ERROR
        assert result.signal is None

    def test_rate_limit_maps_to_llm_error(self):
        class RateLimitedLLM:
            model_id = "rate-limited"
            def complete(self, system_prompt, user_prompt, **kw):
                raise LLMRateLimitError("429 Too Many Requests")

        extractor = SignalExtractor(llm_client=RateLimitedLLM())
        result = extractor.extract(_make_doc())
        assert result.status == ExtractionStatus.LLM_ERROR

    def test_refusal_maps_to_llm_refused(self):
        class RefusingLLM:
            model_id = "refusing"
            def complete(self, system_prompt, user_prompt, **kw):
                raise LLMRefusalError("Content policy violation")

        extractor = SignalExtractor(llm_client=RefusingLLM())
        result = extractor.extract(_make_doc())
        assert result.status == ExtractionStatus.LLM_REFUSED

    def test_raw_llm_response_always_preserved(self):
        """Even on failure, raw_llm_response is preserved for debugging."""
        bad_json = "This is not JSON at all, just prose."
        llm = FakeLLMClient(default_response=bad_json)
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc())
        assert result.raw_llm_response == bad_json

    def test_prompt_includes_document_content(self):
        """Verify the LLM sees the document text."""
        llm = FakeLLMClient(default_response=_VALID_LLM_JSON)
        extractor = SignalExtractor(llm_client=llm)
        doc = _make_doc("unique_phrase_for_testing_1234")
        extractor.extract(doc)
        assert "unique_phrase_for_testing_1234" in llm.last_user

    def test_llm_call_count(self):
        llm = FakeLLMClient(default_response=_VALID_LLM_JSON)
        extractor = SignalExtractor(llm_client=llm)
        extractor.extract(_make_doc())
        extractor.extract(_make_doc())
        assert llm.call_count == 2

    def test_ambiguity_flag_propagated(self):
        ambiguous_json = json.dumps({
            "event_type": "trial_readout",
            "signal_date": "2024-03-15",
            "confidence": 0.55,
            "ambiguity_flag": True,
            "rationale": "Document contains both trial readout and partnership announcement.",
            "interim_flag": False,
        })
        llm = FakeLLMClient(default_response=ambiguous_json)
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc())
        assert result.ambiguity_flag is True
        assert result.extraction_confidence == pytest.approx(0.55)

    def test_rationale_preserved(self):
        llm = FakeLLMClient(default_response=_VALID_LLM_JSON)
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc())
        assert "Phase 3 trial readout" in result.rationale

    def test_batch_extraction_positional_alignment(self):
        fda_json = json.dumps({
            "event_type": "fda_approval",
            "signal_date": "2024-06-01",
            "fda_action_type": "approval",
            "confidence": 0.95,
            "ambiguity_flag": False,
            "rationale": "FDA approval.",
            "interim_flag": False,
        })
        trial_json = _VALID_LLM_JSON
        llm = FakeLLMClient(
            responses={"fda_approval": fda_json, "phase 3": trial_json},
            default_response=trial_json,
        )
        extractor = SignalExtractor(llm_client=llm)
        docs = [_make_doc("fda_approval announcement"), _make_doc("phase 3 trial readout")]
        event_ids = ["evt-batch-1", "evt-batch-2"]
        results = extractor.extract_batch(docs, event_ids=event_ids)

        assert len(results) == 2
        assert results[0].signal.event_id == "evt-batch-1"
        assert results[1].signal.event_id == "evt-batch-2"

    def test_batch_event_ids_length_mismatch_raises(self):
        llm = FakeLLMClient(default_response=_VALID_LLM_JSON)
        extractor = SignalExtractor(llm_client=llm)
        with pytest.raises(ValueError, match="event_ids length"):
            extractor.extract_batch([_make_doc()], event_ids=["a", "b"])

    def test_confidence_clamped_to_0_1(self):
        """LLM-reported confidence outside [0,1] is clamped."""
        json_with_bad_confidence = json.dumps({
            "event_type": "trial_readout",
            "signal_date": "2024-03-15",
            "confidence": 1.5,  # out of range — should be clamped
            "ambiguity_flag": False,
            "rationale": "Test.",
            "interim_flag": False,
        })
        llm = FakeLLMClient(default_response=json_with_bad_confidence)
        extractor = SignalExtractor(llm_client=llm)
        result = extractor.extract(_make_doc())
        assert result.extraction_confidence <= 1.0
