"""LLM schema-filling extractor for science evidence bundles.

Phase 6b keeps the LLM behind the ScienceEvidenceBundle schema. The LLM may
extract source-backed evidence items, but it may not score science, modify POS,
recommend BD actions, or write ScienceThesis objects directly.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import ValidationError

from bve.intelligence.science_evidence import (
    ScienceEvidenceBundle,
    ScienceEvidenceMappedField,
    ScienceEvidenceSourceType,
)


class ScienceEvidenceLLMClient(Protocol):
    """Minimal protocol for mocked or real LLM clients."""

    def generate(self, prompt: str) -> str: ...


class ScienceEvidenceLLMExtractor:
    """Fill ScienceEvidenceBundle from document text using an injected LLM client."""

    def __init__(self, llm_client: object) -> None:
        self.llm_client = llm_client

    def extract_bundle(
        self,
        *,
        asset_id: str,
        document_text: str,
        source_id: str | None = None,
        source_uri: str | None = None,
        source_type: ScienceEvidenceSourceType | str = ScienceEvidenceSourceType.OTHER,
        asset_name: str = "",
        indication: str = "",
        phase: str = "",
        modality: str = "",
        target: str = "",
        mechanism: str = "",
        document_title: str | None = None,
        published_at: str | None = None,
    ) -> ScienceEvidenceBundle:
        """Extract a validated evidence bundle from one source document.

        Invalid LLM output returns an empty bundle with warnings instead of
        raising. Item-level validation failures skip only the invalid item.
        """
        warnings: list[str] = []
        if not document_text.strip():
            return self._empty_bundle(
                asset_id=asset_id,
                asset_name=asset_name,
                indication=indication,
                phase=phase,
                modality=modality,
                target=target,
                mechanism=mechanism,
                warnings=["empty_document_text"],
            )
        if not (source_id or source_uri):
            return self._empty_bundle(
                asset_id=asset_id,
                asset_name=asset_name,
                indication=indication,
                phase=phase,
                modality=modality,
                target=target,
                mechanism=mechanism,
                warnings=["llm_extraction_missing_document_source"],
            )

        prompt = self._build_prompt(
            asset_id=asset_id,
            asset_name=asset_name,
            indication=indication,
            phase=phase,
            modality=modality,
            target=target,
            mechanism=mechanism,
            source_id=source_id,
            source_uri=source_uri,
            source_type=source_type,
            document_title=document_title,
            published_at=published_at,
            document_text=document_text,
        )
        raw_response = self._call_client(prompt)
        payload = self._parse_json(raw_response, warnings)
        if payload is None:
            return self._empty_bundle(
                asset_id=asset_id,
                asset_name=asset_name,
                indication=indication,
                phase=phase,
                modality=modality,
                target=target,
                mechanism=mechanism,
                warnings=warnings,
            )

        raw_items = payload.get("items", []) if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            warnings.append("llm_evidence_items_not_list")
            raw_items = []

        items = []
        source_type_value = self._source_type_value(source_type)
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                warnings.append("llm_evidence_item_not_object")
                continue
            item_data = {
                **raw_item,
                "asset_id": raw_item.get("asset_id") or asset_id,
                "source_type": raw_item.get("source_type") or source_type_value,
                "source_id": raw_item.get("source_id") or source_id,
                "source_uri": raw_item.get("source_uri") or source_uri,
                "document_title": raw_item.get("document_title") or document_title,
                "published_at": raw_item.get("published_at") or published_at,
                "extraction_method": raw_item.get("extraction_method") or "llm_schema_fill",
            }
            if not item_data.get("evidence_id"):
                item_data["evidence_id"] = f"llm_{asset_id}_{index}"
                warnings.append("llm_evidence_missing_evidence_id")
            if not (item_data.get("quote") or item_data.get("text_span")):
                warnings.append("llm_evidence_missing_quote_or_span")
                continue
            if item_data.get("mapped_field") == ScienceEvidenceMappedField.UNSUPPORTED.value:
                warnings.append("unsupported_llm_science_claim")
                item_data["warnings"] = [
                    *list(item_data.get("warnings") or []),
                    "unsupported_llm_science_claim",
                ]
            try:
                items.append(self._item_model().model_validate(item_data))
            except ValidationError as exc:
                warnings.append(f"llm_evidence_item_validation_failed:{exc.errors()[0]['type']}")
                continue

        bundle_warnings = [
            *list(payload.get("bundle_warnings", []) or []),
            *warnings,
        ]
        unresolved_gaps = list(payload.get("unresolved_gaps", []) or [])
        return ScienceEvidenceBundle(
            asset_id=asset_id,
            asset_name=asset_name or str(payload.get("asset_name") or ""),
            indication=indication or str(payload.get("indication") or ""),
            phase=phase or str(payload.get("phase") or ""),
            modality=modality or str(payload.get("modality") or ""),
            target=target or str(payload.get("target") or ""),
            mechanism=mechanism or str(payload.get("mechanism") or ""),
            items=items,
            bundle_warnings=bundle_warnings,
            unresolved_gaps=unresolved_gaps,
        )

    def _build_prompt(self, **kwargs: Any) -> str:
        schema_instructions = {
            "required_output": "JSON object with items, bundle_warnings, unresolved_gaps",
            "item_required_fields": [
                "evidence_id",
                "source_id or source_uri",
                "quote or text_span",
                "mapped_component",
                "mapped_field",
                "direction",
                "confidence",
            ],
            "hard_rules": [
                "Extract evidence only; do not score science.",
                "Do not estimate POS or recommend BD actions.",
                "Every item must include source-backed quote/span.",
                "Unsupported claims must use mapped_field='unsupported' and warnings.",
            ],
        }
        return json.dumps(
            {
                "task": "fill_science_evidence_bundle_schema",
                "schema_instructions": schema_instructions,
                "metadata": {key: value for key, value in kwargs.items() if key != "document_text"},
                "document_text": kwargs["document_text"],
            },
            sort_keys=True,
        )

    def _call_client(self, prompt: str) -> str:
        if hasattr(self.llm_client, "generate"):
            return self._response_content(self.llm_client.generate(prompt))
        if hasattr(self.llm_client, "complete"):
            try:
                response = self.llm_client.complete(
                    "Extract source-backed science evidence into the requested JSON schema.",
                    prompt,
                    temperature=0.0,
                    max_tokens=2048,
                )
            except TypeError:
                response = self.llm_client.complete(prompt)
            return self._response_content(response)
        if callable(self.llm_client):
            return self._response_content(self.llm_client(prompt))
        raise TypeError("llm_client must expose generate(), complete(), or be callable")

    @staticmethod
    def _response_content(response: object) -> str:
        return str(getattr(response, "content", response))

    def _parse_json(self, raw_response: str, warnings: list[str]) -> dict[str, Any] | None:
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            warnings.append("llm_evidence_invalid_json")
            return None
        if not isinstance(parsed, dict):
            warnings.append("llm_evidence_response_not_object")
            return None
        if any(key in parsed for key in ["science_score", "science_modifier", "bd_actionability"]):
            warnings.append("llm_output_contained_forbidden_scoring_fields")
        return parsed

    @staticmethod
    def _source_type_value(source_type: ScienceEvidenceSourceType | str) -> str:
        return source_type.value if isinstance(source_type, ScienceEvidenceSourceType) else str(source_type)

    @staticmethod
    def _item_model():
        from bve.intelligence.science_evidence import ScienceEvidenceItem

        return ScienceEvidenceItem

    @staticmethod
    def _empty_bundle(
        *,
        asset_id: str,
        asset_name: str,
        indication: str,
        phase: str,
        modality: str,
        target: str,
        mechanism: str,
        warnings: list[str],
    ) -> ScienceEvidenceBundle:
        return ScienceEvidenceBundle(
            asset_id=asset_id,
            asset_name=asset_name,
            indication=indication,
            phase=phase,
            modality=modality,
            target=target,
            mechanism=mechanism,
            items=[],
            bundle_warnings=warnings,
            unresolved_gaps=[],
        )
