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

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceVerdict(str, Enum):
    OK = "OK"
    NO_DATA = "NO_DATA"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class SourceHealth(BaseModel):
    """Per-source-family health across the five acquisition stages."""

    model_config = ConfigDict(extra="forbid")

    source_family: str
    connector_succeeded: bool
    query_returned_results: bool
    raw_record_count: int = Field(default=0, ge=0)
    documents_parsed: int = Field(default=0, ge=0)
    documents_indexed: int = Field(default=0, ge=0)
    parse_failures: int = Field(default=0, ge=0)
    # Stage 3 is corpus-level; None until the coverage evaluation attributes it.
    required_evidence_present: bool | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_stage_counts(self) -> "SourceHealth":
        if self.query_returned_results and self.raw_record_count == 0:
            raise ValueError(
                "query_returned_results requires at least one raw record"
            )
        if self.documents_parsed + self.parse_failures > self.raw_record_count:
            raise ValueError(
                "documents_parsed plus parse_failures cannot exceed raw_record_count"
            )
        if self.documents_indexed > self.documents_parsed:
            raise ValueError("documents_indexed cannot exceed documents_parsed")
        return self

    @property
    def verdict(self) -> SourceVerdict:
        if not self.connector_succeeded:
            return SourceVerdict.FAILED
        if self.raw_record_count == 0 and not self.query_returned_results:
            return SourceVerdict.NO_DATA
        if self.documents_indexed == 0 or self.parse_failures >= self.raw_record_count:
            return SourceVerdict.FAILED
        if self.parse_failures > 0 or self.documents_parsed != self.documents_indexed:
            return SourceVerdict.DEGRADED
        return SourceVerdict.OK


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

    def by_family(self) -> dict[str, SourceHealth]:
        families = [source.source_family for source in self.sources]
        if len(families) != len(set(families)):
            raise ValueError("source health report contains duplicate source families")
        return {source.source_family: source for source in self.sources}

    def production_failures(self, required_families: set[str]) -> list[str]:
        """Return fail-closed reasons; a successful zero-result query is not an outage."""

        by_family = self.by_family()
        reasons = [
            f"required source not configured: {family}"
            for family in sorted(required_families - set(by_family))
        ]
        for family in sorted(required_families & set(by_family)):
            verdict = by_family[family].verdict
            if verdict in {SourceVerdict.DEGRADED, SourceVerdict.FAILED}:
                reasons.append(f"required source {family} is {verdict.value}")
        return reasons
