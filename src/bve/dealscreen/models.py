"""Data contracts for DealScreen.

Every value that came from an imported landscape is a :class:`SourceClaim`: what the
vendor file said, where it said it, and who has since confirmed or rejected it. Nothing in
this package turns a claim into a BVE finding without an analyst decision.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClaimOrigin(str, Enum):
    #: Read from an imported vendor/analyst landscape file. Not confirmed by BVE.
    SOURCE_PROVIDED = "SOURCE_PROVIDED"
    #: Proposed by the diligence agent from a cited public document. Not confirmed.
    AGENT_PROPOSED = "AGENT_PROPOSED"


class SourceClaim(Frozen):
    claim_id: str
    asset_id: str
    field: str
    value_as_written: str
    origin: ClaimOrigin = ClaimOrigin.SOURCE_PROVIDED
    source_system: str
    dataset_version: str
    #: 1-based data row in the source file (header excluded), or None for agent claims.
    row_number: int | None = None
    column: str | None = None
    source_reference: str | None = None
    source_date: date | None = None
    #: For agent claims: the quoted span the claim was read from.
    evidence_span: str | None = None


class ImportedRow(Frozen):
    row_number: int
    row_hash: str
    raw: dict[str, str]
    fields: dict[str, str]


class RejectedRow(Frozen):
    row_number: int
    row_hash: str
    raw: dict[str, str]
    reasons: list[str]


class DuplicateRow(Frozen):
    row_number: int
    row_hash: str
    duplicate_of_row: int


class LandscapeAsset(Frozen):
    """One program as a source system identifies it: (source_system, external_id)."""

    asset_id: str
    source_system: str
    external_id: str
    program_name: str
    aliases: list[str] = Field(default_factory=list)
    company: str | None = None
    row_numbers: list[int]
    claims: list[SourceClaim]

    def claims_for(self, field: str) -> list[SourceClaim]:
        return [claim for claim in self.claims if claim.field == field]

    def first_value(self, field: str) -> str | None:
        values = self.claims_for(field)
        return values[0].value_as_written if values else None


class ImportManifest(Frozen):
    dataset_version: str
    source_system: str
    source_file: str
    source_sha256: str
    profile_name: str
    profile_sha256: str
    license_status: str
    allowed_use: str
    rows_read: int
    rows_imported: int
    rows_rejected: int
    rows_exact_duplicate: int
    assets: int
    importer_version: str


class ImportResult(Frozen):
    manifest: ImportManifest
    rows: list[ImportedRow]
    rejected: list[RejectedRow]
    duplicates: list[DuplicateRow]
    assets: list[LandscapeAsset]
    warnings: list[str] = Field(default_factory=list)


class IdentityFlag(Frozen):
    """A reviewable identity question. Never applied automatically."""

    flag_id: str
    kind: str  # SHARED_CODE | PROPOSED_MERGE
    asset_ids: list[str]
    shared_value: str
    relationship: str  # an IdentityRelationship value
    basis: str


class AgentFinding(Frozen):
    finding_id: str
    asset_id: str
    question: str
    field: str
    proposed_value: str
    source_url: str
    source_title: str
    document_date: date | None
    evidence_span: str
    provider: str
    limitations: list[str]
    contradicts_claim_ids: list[str] = Field(default_factory=list)
    retrieved_at: str

