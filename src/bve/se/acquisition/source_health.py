"""Five-stage source-health decomposition.

The prior "zero source failures" signal collapsed five distinct stages into one, hiding the real
bottleneck. Acquisition health is reported per source family across these independent stages:

    1. connector_succeeded      -- the connector ran without crashing
    2. query_returned_results   -- the generic target/modality query returned >0 raw records
    3. required_evidence_present-- benchmark-required evidence exists in the corpus (corpus-level;
                                   filled by the coverage evaluation, not by acquisition)
    4. documents_parsed         -- raw snapshots yielded usable searchable text
    5. documents_indexed        -- parsed evidence is available to downstream search

Stage 3 is deliberately separated: a connector can succeed, return results, parse, and index while
still failing to cover a required asset. Only the coverage evaluation can answer stage 3, and it
does so without leaking benchmark asset names back into acquisition queries.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SourceHealth(BaseModel):
    """Per-source-family health across the five acquisition stages."""

    model_config = ConfigDict(extra="forbid")

    source_family: str
    connector_succeeded: bool
    query_returned_results: bool
    raw_record_count: int = 0
    documents_parsed: int = 0
    documents_indexed: int = 0
    parse_failures: int = 0
    # Stage 3 is corpus-level; None until the coverage evaluation attributes it.
    required_evidence_present: bool | None = None
    error: str | None = None


class SourceHealthReport(BaseModel):
    """Aggregate acquisition health with an explicit five-stage rollup."""

    model_config = ConfigDict(extra="forbid")

    sources: list[SourceHealth] = Field(default_factory=list)

    def total_documents_indexed(self) -> int:
        return sum(source.documents_indexed for source in self.sources)

    def stage_summary(self) -> dict[str, int]:
        """Count source families passing each stage (stage 3 counts attributed sources)."""

        return {
            "connector_succeeded": sum(1 for s in self.sources if s.connector_succeeded),
            "query_returned_results": sum(1 for s in self.sources if s.query_returned_results),
            "required_evidence_present": sum(
                1 for s in self.sources if s.required_evidence_present is True
            ),
            "documents_parsed": sum(1 for s in self.sources if s.documents_parsed > 0),
            "documents_indexed": sum(1 for s in self.sources if s.documents_indexed > 0),
            "source_family_count": len(self.sources),
        }
