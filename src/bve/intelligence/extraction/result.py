"""
ExtractionResult — the canonical output of one extraction attempt.

Wraps the validated ``StructuredSignal`` (or failure metadata) together with
full audit fields: raw LLM output, prompt version, latency, confidence, and
source provenance.  One ``RawDocument`` → one ``ExtractionResult``, always.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.intelligence.schemas.signals import StructuredSignal


class ExtractionStatus(str, Enum):
    """Outcome of a single extraction attempt."""

    SUCCESS          = "success"           # JSON parsed; Pydantic validation passed
    PARSE_ERROR      = "parse_error"       # LLM output was not valid JSON
    VALIDATION_ERROR = "validation_error"  # JSON parsed; Pydantic rejected it
    LLM_REFUSED      = "llm_refused"       # Model refused or returned empty text
    LLM_ERROR        = "llm_error"         # API error (rate limit, timeout, etc.)
    CONNECTOR_ERROR  = "connector_error"   # Source fetch failed upstream


class ExtractionResult(BaseModel):
    """
    Immutable record of one document extraction attempt.

    If ``status == SUCCESS``, ``signal`` is guaranteed to be a fully
    schema-validated ``StructuredSignal``.  For all other statuses,
    ``signal`` is ``None`` and ``validation_errors`` / ``raw_llm_response``
    contain actionable debug information.

    Attributes
    ----------
    document_id:
        FK → ``RawDocument.id``.
    asset_id, company_id:
        Denormalized from ``RawDocument.entity_hints`` for efficient filtering.
    source_url:
        Copied from ``RawDocument.source_url`` for provenance tracing.
    status:
        Outcome of the extraction attempt.
    signal:
        Fully validated ``StructuredSignal`` when ``status == SUCCESS``.
        ``None`` otherwise.
    event_type_detected:
        The event type the LLM classified this document as.
        Populated even on ``VALIDATION_ERROR`` (classification may have
        succeeded even if field validation failed).  ``None`` on parse failure.
    raw_llm_response:
        Literal text returned by the LLM.  Always stored for auditability,
        even on failure.
    raw_llm_json:
        Parsed JSON dict from the LLM response.  ``None`` when parsing failed.
    validation_errors:
        Pydantic or JSON error messages on failure.  Empty on success.
    ambiguity_flag:
        ``True`` if the LLM indicated the event type was unclear or multiple
        events were detected in the same document.
    extraction_confidence:
        Model-reported confidence from 0.0 to 1.0.  0.0 on failure.
    rationale:
        LLM's one-to-two sentence explanation of its classification choices.
        Empty string on failure.
    extraction_model:
        Model identifier (e.g., ``"claude-sonnet-4-6"``).
    prompt_version:
        Version tag of the prompt template used (e.g., ``"v1.0"``).
        Allows signal quality to be traced back to the prompt that generated it.
    latency_ms:
        Wall-clock duration of the LLM API call in milliseconds.
    extracted_at:
        UTC timestamp when the extraction completed.
    """

    model_config = {"frozen": True}

    # Provenance
    document_id:          str
    asset_id:             str
    company_id:           str
    source_url:           Optional[str]              = None

    # Outcome
    status:               ExtractionStatus
    signal:               Optional[StructuredSignal] = None
    event_type_detected:  Optional[str]              = None

    # Raw LLM output — always preserved
    raw_llm_response:     str                        = ""
    raw_llm_json:         Optional[dict[str, Any]]   = None

    # Failure details
    validation_errors:    list[str]                  = Field(default_factory=list)

    # Quality metadata
    ambiguity_flag:       bool                       = False
    extraction_confidence: float                     = Field(default=0.0, ge=0.0, le=1.0)
    rationale:            str                        = ""

    # Execution metadata
    extraction_model:     str                        = ""
    prompt_version:       str                        = ""
    latency_ms:           int                        = Field(default=0, ge=0)
    extracted_at:         datetime
