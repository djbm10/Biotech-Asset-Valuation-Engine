import json

from bve.intelligence.science_evidence import (
    ScienceEvidenceMappedComponent,
    ScienceEvidenceMappedField,
    ScienceEvidenceSourceType,
)
from bve.intelligence.science_evidence_llm_extractor import ScienceEvidenceLLMExtractor
from bve.intelligence.science_thesis_builder import ScienceThesisBuilder


class FakeLLMClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response if isinstance(self.response, str) else json.dumps(self.response)


def payload_item(**overrides):
    item = {
        "evidence_id": "ev-1",
        "quote": "Phase 2 patients showed dose-dependent target engagement.",
        "mapped_component": "D",
        "mapped_field": "target_engagement",
        "direction": "supportive",
        "confidence": 0.82,
        "rationale": "Direct source-backed PK/PD evidence.",
    }
    item.update(overrides)
    return item


def extract(response: object):
    client = FakeLLMClient(response)
    bundle = ScienceEvidenceLLMExtractor(client).extract_bundle(
        asset_id="asset-1",
        asset_name="Asset 1",
        indication="ulcerative colitis",
        phase="phase2",
        modality="small_molecule",
        target="JAK1",
        mechanism="JAK1 inhibition",
        source_id="doc-1",
        source_uri="https://example.com/doc-1",
        source_type=ScienceEvidenceSourceType.CLINICAL_READOUT,
        document_title="Clinical update",
        published_at="2026-01-01",
        document_text="Phase 2 patients showed dose-dependent target engagement.",
    )
    return bundle, client


def test_llm_valid_response_produces_science_evidence_bundle() -> None:
    bundle, client = extract({"items": [payload_item()], "bundle_warnings": [], "unresolved_gaps": []})

    assert len(bundle.items) == 1
    item = bundle.items[0]
    assert item.asset_id == "asset-1"
    assert item.source_id == "doc-1"
    assert item.source_type == ScienceEvidenceSourceType.CLINICAL_READOUT
    assert item.mapped_component == ScienceEvidenceMappedComponent.D
    assert item.mapped_field == ScienceEvidenceMappedField.TARGET_ENGAGEMENT
    assert "science_score" not in client.prompts[0]


def test_llm_invalid_json_returns_empty_bundle_with_warning() -> None:
    bundle, _ = extract("not json")

    assert bundle.items == []
    assert "llm_evidence_invalid_json" in bundle.bundle_warnings


def test_llm_response_with_forbidden_scoring_fields_warns_without_scoring_output() -> None:
    bundle, _ = extract(
        {
            "science_score": 0.99,
            "items": [payload_item()],
            "bundle_warnings": [],
            "unresolved_gaps": [],
        }
    )

    assert len(bundle.items) == 1
    assert "llm_output_contained_forbidden_scoring_fields" in bundle.bundle_warnings
    assert not hasattr(bundle, "science_score")
    assert not hasattr(bundle, "modifier_result")


def test_llm_missing_quote_or_span_rejects_item_and_warns() -> None:
    bundle, _ = extract(
        {
            "items": [payload_item(quote=None, text_span=None)],
            "bundle_warnings": [],
            "unresolved_gaps": [],
        }
    )

    assert bundle.items == []
    assert "llm_evidence_missing_quote_or_span" in bundle.bundle_warnings


def test_llm_unsupported_claim_is_preserved_as_warning_no_credit_path() -> None:
    bundle, _ = extract(
        {
            "items": [
                payload_item(
                    mapped_component="T",
                    mapped_field="unsupported",
                    quote="The company has an ambitious platform vision.",
                )
            ],
            "bundle_warnings": [],
            "unresolved_gaps": [],
        }
    )

    assert len(bundle.items) == 1
    assert "unsupported_llm_science_claim" in bundle.bundle_warnings
    assert "unsupported_llm_science_claim" in bundle.items[0].warnings

    thesis = ScienceThesisBuilder().from_existing_evidence(science_evidence_bundle=bundle)
    assert thesis.components["T"].score < 0.5
    assert "unsupported_extracted_science_claim" in thesis.modifier_result.warnings


def test_llm_low_confidence_bundle_feeds_builder_without_full_credit() -> None:
    bundle, _ = extract(
        {
            "items": [
                payload_item(
                    mapped_component="H",
                    mapped_field="human_poc",
                    quote="The trial showed a preliminary clinical signal.",
                    confidence=0.45,
                )
            ],
            "bundle_warnings": [],
            "unresolved_gaps": ["confirm durable clinical benefit"],
        }
    )

    thesis = ScienceThesisBuilder().from_existing_evidence(science_evidence_bundle=bundle)
    assert thesis.components["H"].score < 0.5
    assert "low_confidence_extracted_science_evidence" in thesis.modifier_result.warnings
    assert "confirm durable clinical benefit" in thesis.missing_critical_evidence


def test_llm_missing_document_source_returns_empty_bundle() -> None:
    client = FakeLLMClient({"items": [payload_item()]})
    bundle = ScienceEvidenceLLMExtractor(client).extract_bundle(
        asset_id="asset-1",
        document_text="Target engagement was observed.",
    )

    assert bundle.items == []
    assert "llm_extraction_missing_document_source" in bundle.bundle_warnings
    assert client.prompts == []


def test_llm_prompt_states_schema_filling_boundaries() -> None:
    _, client = extract({"items": [payload_item()], "bundle_warnings": [], "unresolved_gaps": []})
    prompt = client.prompts[0]

    assert "fill_science_evidence_bundle_schema" in prompt
    assert "Do not estimate POS or recommend BD actions" in prompt
    assert "Every item must include source-backed quote/span" in prompt
