"""Typed science evidence landing-zone schemas.

These models are the safe target for future extraction. They intentionally do
not score assets directly; adapters must conservatively map source-backed items
into ScienceThesisBuilder inputs.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ScienceEvidenceDirection(str, Enum):
    SUPPORTIVE = "supportive"
    NEGATIVE = "negative"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"


class ScienceEvidenceSourceType(str, Enum):
    COMPANY_DECK = "company_deck"
    PRESS_RELEASE = "press_release"
    CLINICAL_TRIAL_REGISTRY = "clinical_trial_registry"
    CLINICAL_READOUT = "clinical_readout"
    PAPER = "paper"
    ABSTRACT = "abstract"
    EARNINGS_CALL = "earnings_call"
    SEC_FILING = "sec_filing"
    ANALYST_REPORT = "analyst_report"
    MANUAL = "manual"
    OTHER = "other"


class ScienceEvidenceMappedComponent(str, Enum):
    T = "T"
    D = "D"
    B = "B"
    H = "H"
    M = "M"
    S = "S"
    Q = "Q"


class ScienceEvidenceMappedField(str, Enum):
    TARGET_PATHWAY = "target_pathway"
    MECHANISM_RATIONALE = "mechanism_rationale"
    GENETIC_VALIDATION = "genetic_validation"
    PKPD = "pkpd"
    EXPOSURE = "exposure"
    TISSUE_DELIVERY = "tissue_delivery"
    TARGET_ENGAGEMENT = "target_engagement"
    DOSE_RESPONSE = "dose_response"
    EXPOSURE_RESPONSE = "exposure_response"
    BIOMARKER_VALIDATION = "biomarker_validation"
    BIOMARKER_CLINICAL_BRIDGE = "biomarker_clinical_bridge"
    HUMAN_POC = "human_poc"
    EFFICACY_SIGNAL = "efficacy_signal"
    CLINICAL_MEANINGFULNESS = "clinical_meaningfulness"
    STANDARD_OF_CARE_CONTEXT = "standard_of_care_context"
    SAFETY_SIGNAL = "safety_signal"
    SAFETY_MARGIN = "safety_margin"
    TRIAL_DESIGN = "trial_design"
    ENDPOINT_VALIDITY = "endpoint_validity"
    SOURCE_QUALITY = "source_quality"
    UNSUPPORTED = "unsupported"


class ScienceEvidenceItem(BaseModel):
    """One extracted source-backed science evidence observation."""

    evidence_id: str
    asset_id: str
    source_type: ScienceEvidenceSourceType
    source_id: str | None = None
    source_uri: str | None = None
    quote: str | None = None
    text_span: str | None = None
    mapped_component: ScienceEvidenceMappedComponent
    mapped_field: ScienceEvidenceMappedField
    direction: ScienceEvidenceDirection
    confidence: float = Field(ge=0.0, le=1.0)
    document_title: str | None = None
    published_at: str | None = None
    page_number: int | None = None
    section: str | None = None
    extraction_method: str = "manual"
    rationale: str = ""
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_source_and_text(self) -> "ScienceEvidenceItem":
        if not (self.source_id or self.source_uri):
            raise ValueError("ScienceEvidenceItem requires source_id or source_uri")
        if not (self.quote or self.text_span):
            raise ValueError("ScienceEvidenceItem requires quote or text_span")
        return self


class ScienceEvidenceBundle(BaseModel):
    """Evidence items and extraction gaps for one asset."""

    asset_id: str
    asset_name: str = ""
    indication: str = ""
    phase: str = "phase2"
    modality: str = ""
    target: str = ""
    mechanism: str = ""
    items: list[ScienceEvidenceItem] = Field(default_factory=list)
    bundle_warnings: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
