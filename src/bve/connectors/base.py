"""
Source connector base types.

``SourceConnector`` is a structural ``Protocol`` — connectors do not inherit
from it.  ``FetchResult`` is the typed return value of every ``fetch()`` call.

Connector responsibilities
--------------------------
1. Fetch raw content from a specific external source.
2. Normalize content into ``RawDocument`` objects (HTML stripped, text only).
3. Preserve all available provenance: source URL, published timestamps, entity hints.
4. Return partial results when some documents fail — never raise on empty results.

What connectors must NOT do
---------------------------
- Call LLM APIs.
- Create ``StructuredSignal`` objects.
- Modify ``entity_hints`` after receiving them from the caller.
- Suppress all errors silently — record them in ``FetchResult.fetch_errors``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.schemas.signals import SourceType


class FetchResult(BaseModel):
    """
    Typed outcome of one connector fetch operation.

    Attributes
    ----------
    documents:
        Normalized documents successfully fetched.  May be empty if all
        fetches failed, but the list itself is never ``None``.
    fetch_errors:
        Human-readable error messages for failed fetches.  Non-empty does
        not mean total failure — partial results are valid.
    source:
        ``SourceType`` value of the connector that produced this result.
    fetched_at:
        UTC timestamp of the fetch operation.
    """

    model_config = {"frozen": True}

    documents:    list[RawDocument] = Field(default_factory=list)
    fetch_errors: list[str]         = Field(default_factory=list)
    source:       str               = "manual"
    fetched_at:   datetime          = Field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class SourceConnector(Protocol):
    """
    Structural protocol for data source connectors.

    Any class implementing ``fetch()`` and ``source_type`` satisfies
    this protocol.  No inheritance required.
    """

    @property
    def source_type(self) -> str:
        """``SourceType`` value produced by this connector."""
        ...

    def fetch(
        self,
        entity_hints: EntityHints,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> FetchResult:
        """
        Fetch raw documents for the given entity.

        Parameters
        ----------
        entity_hints:
            Asset / company identity context.  Connectors use ``drug_name``,
            ``nct_id``, and ``ticker`` for their source-specific queries.
        since:
            Exclude documents published before this UTC timestamp.
            ``None`` means no date filter.
        limit:
            Maximum number of documents to return.

        Returns
        -------
        FetchResult
            Always returns a ``FetchResult`` — never raises.
        """
        ...
