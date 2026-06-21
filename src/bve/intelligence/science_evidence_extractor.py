"""Deterministic extraction of structured repo objects into science evidence bundles.

Phase 6a deliberately maps only existing structured/source-backed fields into
ScienceEvidenceItem objects. It does not score assets, write theses, call LLMs,
or infer unsupported science conclusions.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable

from bve.intelligence.science_evidence import (
    ScienceEvidenceBundle,
    ScienceEvidenceDirection,
    ScienceEvidenceItem,
    ScienceEvidenceMappedComponent,
    ScienceEvidenceMappedField,
    ScienceEvidenceSourceType,
)


class ScienceEvidenceExtractor:
    """Conservative mapper from structured repo objects to ScienceEvidenceBundle."""

    def extract_bundle(
        self,
        *,
        asset_id: str,
        asset_name: str = "",
        indication: str = "",
        phase: str = "",
        modality: str = "",
        target: str = "",
        mechanism: str = "",
        structured_signals: list[object] | None = None,
        trial_readouts: list[object] | None = None,
        endpoint_evidence: list[object] | None = None,
        safety_events: list[object] | None = None,
    ) -> ScienceEvidenceBundle:
        warnings: list[str] = []
        gaps: list[str] = []
        items: list[ScienceEvidenceItem] = []

        for collection_name, objects in [
            ("structured_signal", structured_signals or []),
            ("trial_readout", trial_readouts or []),
            ("endpoint_evidence", endpoint_evidence or []),
            ("safety_event", safety_events or []),
        ]:
            for obj in objects:
                item = self._extract_item(
                    obj,
                    default_asset_id=asset_id,
                    collection_name=collection_name,
                    warnings=warnings,
                    gaps=gaps,
                )
                if item is not None:
                    items.append(item)

        return ScienceEvidenceBundle(
            asset_id=asset_id,
            asset_name=asset_name,
            indication=indication,
            phase=phase,
            modality=modality,
            target=target,
            mechanism=mechanism,
            items=items,
            bundle_warnings=warnings,
            unresolved_gaps=gaps,
        )

    def _extract_item(
        self,
        obj: object,
        *,
        default_asset_id: str,
        collection_name: str,
        warnings: list[str],
        gaps: list[str],
    ) -> ScienceEvidenceItem | None:
        text = self._event_text(obj)
        component, mapped_field = self._map_component_and_field(obj, text, collection_name)
        evidence_id = str(
            self._first(obj, ["evidence_id", "signal_id", "id", "event_id", "document_id"])
            or f"{collection_name}:{len(warnings)}"
        )

        if component is None or mapped_field is None:
            warnings.append("unsupported_structured_science_signal")
            gaps.append(f"unsupported_structured_science_signal:{evidence_id}")
            return None

        source_id = self._source_id(obj)
        source_uri = self._source_uri(obj)
        quote = self._first(
            obj,
            ["quote", "text_span", "rationale", "description", "summary", "raw_text", "headline"],
        )
        if not source_id and not source_uri:
            warnings.append("science_evidence_missing_source")
            gaps.append(f"missing_source:{evidence_id}")
            return None
        if not quote:
            warnings.append("science_evidence_missing_quote_or_span")
            gaps.append(f"missing_quote_or_span:{evidence_id}")
            return None

        try:
            return ScienceEvidenceItem(
                evidence_id=evidence_id,
                asset_id=str(self._get(obj, "asset_id") or default_asset_id),
                source_type=self._source_type(obj),
                source_id=source_id,
                source_uri=source_uri,
                quote=str(quote),
                mapped_component=component,
                mapped_field=mapped_field,
                direction=self._direction(obj, text),
                confidence=self._confidence(obj),
                document_title=self._first(obj, ["document_title", "title", "headline"]),
                published_at=self._date_text(obj),
                section=self._first(obj, ["section", "document_section"]),
                extraction_method="deterministic_structured_mapper",
                rationale=f"Mapped {collection_name} to {component.value}/{mapped_field.value}.",
                warnings=[],
            )
        except ValueError as exc:
            warnings.append(f"science_evidence_item_validation_failed:{exc}")
            gaps.append(f"invalid_evidence_item:{evidence_id}")
            return None

    def _map_component_and_field(
        self,
        obj: object,
        text: str,
        collection_name: str,
    ) -> tuple[ScienceEvidenceMappedComponent | None, ScienceEvidenceMappedField | None]:
        text_l = text.lower()
        if collection_name == "safety_event" or self._has_any(
            text_l,
            ["safety", "tolerability", " ae", "sae", "dose-limiting", "toxicity", "adverse"],
        ):
            return ScienceEvidenceMappedComponent.S, ScienceEvidenceMappedField.SAFETY_SIGNAL
        if self._has_any(
            text_l,
            ["pk/pd", "pkpd", "exposure", "dose response", "dose-response"],
        ):
            return ScienceEvidenceMappedComponent.D, ScienceEvidenceMappedField.PKPD
        if self._has_any(text_l, ["target engagement"]):
            return ScienceEvidenceMappedComponent.D, ScienceEvidenceMappedField.TARGET_ENGAGEMENT
        if self._has_any(text_l, ["tissue exposure", "tissue delivery", "delivery"]):
            return ScienceEvidenceMappedComponent.D, ScienceEvidenceMappedField.TISSUE_DELIVERY
        if self._has_any(text_l, ["exposure response", "exposure-response"]):
            return ScienceEvidenceMappedComponent.D, ScienceEvidenceMappedField.EXPOSURE_RESPONSE
        if self._has_any(
            text_l,
            ["biomarker", "mrd", "pd marker", "surrogate", "translational bridge"],
        ):
            return ScienceEvidenceMappedComponent.B, ScienceEvidenceMappedField.BIOMARKER_VALIDATION
        if self._has_any(
            text_l,
            ["endpoint validity", "standard of care", "clinically meaningful", "effect size"],
        ):
            return ScienceEvidenceMappedComponent.M, ScienceEvidenceMappedField.CLINICAL_MEANINGFULNESS
        if self._has_any(text_l, ["endpoint met", "primary endpoint met"]):
            return ScienceEvidenceMappedComponent.H, ScienceEvidenceMappedField.HUMAN_POC
        if bool(self._get(obj, "primary_endpoint_met")) is True:
            return ScienceEvidenceMappedComponent.H, ScienceEvidenceMappedField.HUMAN_POC
        if self._has_any(
            text_l,
            ["efficacy", "clinical benefit", "response rate", "pfs", "os", "remission"],
        ):
            return ScienceEvidenceMappedComponent.H, ScienceEvidenceMappedField.EFFICACY_SIGNAL
        if self._has_any(
            text_l,
            ["trial design", "randomized", "double blind", "double-blind", "controlled", "sample size"],
        ) or self._has_trial_design_fields(obj):
            return ScienceEvidenceMappedComponent.Q, ScienceEvidenceMappedField.TRIAL_DESIGN
        if self._has_any(text_l, ["target", "mechanism", "pathway", "moa", "disease biology"]):
            return ScienceEvidenceMappedComponent.T, ScienceEvidenceMappedField.TARGET_PATHWAY
        return None, None

    def _direction(self, obj: object, text: str) -> ScienceEvidenceDirection:
        explicit = self._first(obj, ["direction", "polarity", "sentiment"])
        if explicit:
            value = str(explicit).lower()
            if value in {"supportive", "supports", "positive"}:
                return ScienceEvidenceDirection.SUPPORTIVE
            if value in {"negative", "weakens", "refutes", "risk"}:
                return ScienceEvidenceDirection.NEGATIVE
            if value in {"ambiguous", "neutral", "unclear"}:
                return ScienceEvidenceDirection.AMBIGUOUS
        endpoint_met = self._get(obj, "primary_endpoint_met")
        if endpoint_met is True:
            return ScienceEvidenceDirection.SUPPORTIVE
        if endpoint_met is False:
            return ScienceEvidenceDirection.NEGATIVE
        text_l = text.lower()
        if self._has_any(text_l, ["failed", "missed", "not met", "negative", "toxicity", "hold"]):
            return ScienceEvidenceDirection.NEGATIVE
        if self._has_any(text_l, ["ambiguous", "unclear", "mixed", "immature"]):
            return ScienceEvidenceDirection.AMBIGUOUS
        return ScienceEvidenceDirection.SUPPORTIVE

    def _event_text(self, obj: object) -> str:
        values = []
        for field in [
            "mapped_field",
            "claim_type",
            "event_type",
            "event_subtype",
            "label",
            "title",
            "headline",
            "primary_endpoint",
            "endpoint_type",
            "description",
            "summary",
            "rationale",
            "quote",
            "text_span",
            "raw_text",
            "trial_design",
            "randomization",
            "blinding",
            "comparator_type",
        ]:
            value = self._get(obj, field)
            if value is not None:
                values.append(str(getattr(value, "value", value)))
        return " ".join(values)

    def _source_id(self, obj: object) -> str | None:
        value = self._first(
            obj,
            ["source_id", "document_id", "raw_document_id", "event_id", "trial_nct_id", "nct_id"],
        )
        return str(value) if value else None

    def _source_uri(self, obj: object) -> str | None:
        value = self._first(obj, ["source_uri", "source_url", "url", "uri", "path"])
        return str(value) if value else None

    def _source_type(self, obj: object) -> ScienceEvidenceSourceType:
        value = str(self._first(obj, ["source_type", "source"]) or "other").lower()
        mapping = {
            "press_release": ScienceEvidenceSourceType.PRESS_RELEASE,
            "clinicaltrials_gov": ScienceEvidenceSourceType.CLINICAL_TRIAL_REGISTRY,
            "clinical_trial_registry": ScienceEvidenceSourceType.CLINICAL_TRIAL_REGISTRY,
            "clinical_readout": ScienceEvidenceSourceType.CLINICAL_READOUT,
            "conference_abstract": ScienceEvidenceSourceType.ABSTRACT,
            "abstract": ScienceEvidenceSourceType.ABSTRACT,
            "publication": ScienceEvidenceSourceType.PAPER,
            "paper": ScienceEvidenceSourceType.PAPER,
            "sec_filing": ScienceEvidenceSourceType.SEC_FILING,
            "earnings_call": ScienceEvidenceSourceType.EARNINGS_CALL,
            "manual": ScienceEvidenceSourceType.MANUAL,
        }
        return mapping.get(value, ScienceEvidenceSourceType.OTHER)

    def _confidence(self, obj: object) -> float:
        value = self._first(
            obj,
            ["confidence", "extraction_confidence", "source_confidence", "score"],
        )
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5

    def _date_text(self, obj: object) -> str | None:
        value = self._first(obj, ["published_at", "signal_date", "observed_at", "created_at"])
        return str(value) if value else None

    def _has_trial_design_fields(self, obj: object) -> bool:
        return any(
            self._get(obj, field) is not None
            for field in ["randomization", "blinding", "comparator_type", "n_patients"]
        )

    def _get(self, obj: object, field: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(field)
        if is_dataclass(obj):
            return asdict(obj).get(field)
        return getattr(obj, field, None)

    def _first(self, obj: object, fields: Iterable[str]) -> Any:
        for field in fields:
            value = self._get(obj, field)
            if value is not None and str(value) != "":
                return value
        return None

    @staticmethod
    def _has_any(text: str, terms: list[str]) -> bool:
        return any(term in text for term in terms)
