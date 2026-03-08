"""
Normalized raw document model for the intelligence extraction pipeline.

``RawDocument`` is the canonical, source-agnostic representation of a single
fetched artifact (press release, SEC filing, FDA announcement, ClinicalTrials.gov
record, etc.) produced by any source connector and consumed by the
``SignalExtractor``.

It carries complete provenance so every downstream ``StructuredSignal`` can be
traced back to the original source URL and fetch timestamp.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from bve.intelligence.schemas.signals import SourceType

# Legal values mirrored from SourceType Literal for validation
_SOURCE_TYPES: frozenset[str] = frozenset({
    "press_release",
    "sec_filing",
    "clinicaltrials_gov",
    "conference_abstract",
    "publication",
    "fda_website",
    "news_aggregator",
    "manual",
})


class EntityHints(BaseModel):
    """
    Caller-provided entity context injected into the extraction prompt.

    These fields are *never* derived from the document text by the LLM.
    They are assigned by the connector or the CLI operator before extraction
    begins, and they become the ``asset_id`` / ``company_id`` FK fields in
    the resulting ``StructuredSignal``.

    Attributes
    ----------
    asset_id:
        FK → ``IntelligenceAsset.id``.  Required — every document must be
        associated with a monitored asset before extraction.
    company_id:
        FK → ``IntelligenceCompany.id``.  Required.
    drug_name:
        INN or brand name for prompt injection (reduces hallucination risk).
    indication:
        Free-text indication description for prompt context.
    ticker:
        Exchange ticker (e.g., ``"REGN"``).
    nct_id:
        ClinicalTrials.gov NCT ID when the document is a trial record.
    """

    model_config = {"frozen": True}

    asset_id:   str
    company_id: str
    drug_name:  Optional[str] = None
    indication: Optional[str] = None
    ticker:     Optional[str] = None
    nct_id:     Optional[str] = None


class RawDocument(BaseModel):
    """
    Source-agnostic normalized document produced by a ``SourceConnector``.

    Attributes
    ----------
    id:
        UUIDv4 document identifier assigned at fetch time.
    source:
        Controlled-vocabulary channel identifier (matches ``SourceType``).
    source_url:
        Canonical permalink of the source document.  ``None`` only when the
        document originates from a local file or stdin (``--text`` CLI flag).
    title:
        Document headline or filing type; max 500 characters.
    raw_text:
        Full UTF-8 plain text (HTML stripped).  Never empty.
    published_at:
        Publication or filing date from the source.  ``None`` when the source
        does not expose a publication date.
    retrieved_at:
        UTC timestamp when the connector fetched this document.
    entity_hints:
        Caller-provided entity context; passed through unchanged to the extractor.
    word_count:
        Approximate word count computed from ``raw_text`` at construction time.
    document_hash:
        SHA-256 hash of normalized ``raw_text`` used for deterministic dedupe.
    """

    model_config = {"frozen": True}

    id:            str
    source:        str   # validated against _SOURCE_TYPES
    source_url:    Optional[str]       = None
    title:         str
    raw_text:      str
    published_at:  Optional[datetime]  = None
    retrieved_at:  datetime
    entity_hints:  EntityHints
    word_count:    int                 = Field(default=0, ge=0)
    document_hash: str

    @field_validator("source")
    @classmethod
    def _valid_source(cls, v: str) -> str:
        if v not in _SOURCE_TYPES:
            raise ValueError(
                f"source must be one of {sorted(_SOURCE_TYPES)}, got {v!r}"
            )
        return v

    @field_validator("title")
    @classmethod
    def _title_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace only")
        return stripped[:500]

    @field_validator("raw_text")
    @classmethod
    def _text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("raw_text must not be empty")
        return v

    @field_validator("document_hash")
    @classmethod
    def _valid_document_hash(cls, v: str) -> str:
        text = v.strip().lower()
        if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
            raise ValueError("document_hash must be a 64-char lowercase SHA-256 hex digest")
        return text

    @model_validator(mode="before")
    @classmethod
    def _inject_document_hash(cls, values):
        if isinstance(values, dict):
            if values.get("document_hash") is None and values.get("raw_text") is not None:
                values["document_hash"] = hashlib.sha256(
                    str(values["raw_text"]).encode("utf-8")
                ).hexdigest()
        return values

    @classmethod
    def from_text(
        cls,
        *,
        id: str,
        source: str,
        title: str,
        raw_text: str,
        entity_hints: EntityHints,
        retrieved_at: Optional[datetime] = None,
        source_url: Optional[str] = None,
        published_at: Optional[datetime] = None,
        document_hash: Optional[str] = None,
    ) -> "RawDocument":
        """
        Convenience constructor that computes ``word_count`` automatically.

        Parameters
        ----------
        retrieved_at:
            Defaults to ``datetime.now(UTC)`` when not provided.
        """
        if retrieved_at is None:
            retrieved_at = datetime.now(timezone.utc)
        doc_hash = (document_hash or hashlib.sha256(raw_text.encode("utf-8")).hexdigest()).lower()
        return cls(
            id=id,
            source=source,
            source_url=source_url,
            title=title,
            raw_text=raw_text,
            published_at=published_at,
            retrieved_at=retrieved_at,
            entity_hints=entity_hints,
            word_count=len(raw_text.split()),
            document_hash=doc_hash,
        )
