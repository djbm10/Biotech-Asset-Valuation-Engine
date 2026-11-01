"""Commercial diligence status, kept independent of scientific eligibility.

U.S. licensing availability is the field most easily over-read. The rules:

- AVAILABLE only when a source explicitly says rights are available or a partner is
  sought, and then it is still "source-provided, unverified" until an analyst confirms it.
- Silence, "not reported" or an empty cell is UNKNOWN. No license recorded is not a
  license available, and a trial sponsor is not shown to be the rights owner.
- A recorded license, option or partnership covering the market is ENCUMBERED.

The text reader is ``rights_reader`` (strict since cycle R1 revision 5); its names are re-exported here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bve.dealscreen.models import LandscapeAsset, SourceClaim
from bve.dealscreen.rights_reader import (
    AVAILABLE,
    AVAILABLE_CONFIRMED,
    CONFLICTING,
    ENCUMBERED,
    NOT_AVAILABLE,
    OPTION,
    RETURNED,
    RIGHTS_STATUS_WORDS,
    UNKNOWN,
    rights_reading,
    rights_status,
)


@dataclass
class CommercialAssessment:
    asset_id: str
    ownership_per_source: str | None
    ownership_note: str
    us_rights_status: str
    us_rights_claim_ids: list[str]
    partnerships: list[str]
    open_questions: list[str] = field(default_factory=list)
    #: Who holds U.S. rights, per the cited evidence. Independent of availability: knowing the
    #: holder says nothing about whether it would license.
    us_rights_holder: str | None = None
    us_rights_holder_claim_ids: list[str] = field(default_factory=list)
    us_rights_holder_conflict: list[str] = field(default_factory=list)
    #: The claims each status was read from, with their citations and dates (review R1v3 F1-analyst, E2-holder).
    us_rights_basis: list[dict[str, Any]] = field(default_factory=list)
    us_rights_holder_basis: list[dict[str, Any]] = field(default_factory=list)
    #: Every U.S.-rights statement and holder not rejected, with how each reads; the top-tier gate checks them all,
    #: not only the one the status was taken from (review R1v4 A3d, A3e, A6).
    us_rights_all: list[dict[str, Any]] = field(default_factory=list)
    us_rights_holder_all: list[dict[str, Any]] = field(default_factory=list)

    @property
    def holder_display(self) -> str:
        if self.us_rights_holder_conflict:
            return "CONFLICTING: " + " | ".join(self.us_rights_holder_conflict)
        return self.us_rights_holder or "UNKNOWN"

    @property
    def display(self) -> str:
        return {
            AVAILABLE: "AVAILABLE (source-provided, unverified)",
            AVAILABLE_CONFIRMED: "AVAILABLE (analyst-asserted or -confirmed from a cited source; verify)",
            NOT_AVAILABLE: "NOT AVAILABLE (source-provided)",
            ENCUMBERED: "ENCUMBERED (source-provided)",
            RETURNED: "RIGHTS RETURNED TO ORIGINATOR (source-provided; not a statement of availability)",
            OPTION: "OPTION HELD BY A THIRD PARTY (source-provided; exercise not stated)",
            CONFLICTING: "CONFLICTING SOURCES",
            UNKNOWN: "UNKNOWN",
        }[self.us_rights_status]


def assess(
    asset: LandscapeAsset,
    *,
    questions: list[str],
    rejected_claim_ids: frozenset[str] = frozenset(),
    confirmed_claim_ids: frozenset[str] = frozenset(),
    confirmed_findings: tuple[SourceClaim, ...] = (),
) -> CommercialAssessment:
    """``confirmed_findings`` are analyst-confirmed agent findings already shaped as claims."""
    claims: list[SourceClaim] = [
        c for c in asset.claims_for("us_rights") if c.claim_id not in rejected_claim_ids
    ]
    extra = [c for c in confirmed_findings if c.field == "us_rights" and c.asset_id == asset.asset_id]
    claims.extend(extra)
    confirmed = [c for c in claims if c.claim_id in confirmed_claim_ids or c in extra]
    basis = confirmed[-1:] or claims
    statuses = {rights_status(c.value_as_written) for c in basis}
    if not statuses:
        status = UNKNOWN
    elif len(statuses) > 1:
        status = CONFLICTING
    else:
        status = statuses.pop()
    if status == AVAILABLE and confirmed:
        status = AVAILABLE_CONFIRMED
    partnerships = [
        p.value_as_written for p in asset.claims_for("partnerships")
        if p.claim_id not in rejected_claim_ids
    ] + [c.value_as_written for c in confirmed_findings
         if c.field == "partnerships" and c.asset_id == asset.asset_id]
    if status in {AVAILABLE, AVAILABLE_CONFIRMED} and partnerships:
        # "Available" alongside a recorded partnership needs a human, confirmed or not.
        status = CONFLICTING
    holder_claims = [c for c in asset.claims_for("us_rights_holder") if c.claim_id not in rejected_claim_ids]
    holder_claims += [c for c in confirmed_findings
                      if c.field == "us_rights_holder" and c.asset_id == asset.asset_id]
    decisive = [c for c in holder_claims if c.claim_id in confirmed_claim_ids
                or c in confirmed_findings]
    chosen = decisive[-1:] or holder_claims
    holders = list(dict.fromkeys(c.value_as_written.strip() for c in chosen))
    open_questions = [] if status in {AVAILABLE_CONFIRMED} else list(questions)
    return CommercialAssessment(
        asset_id=asset.asset_id,
        ownership_per_source=asset.company,
        ownership_note=(
            "Company as named by the source (originator/sponsor). Ownership of rights is "
            "not inferred from sponsorship and is unverified."
        ),
        us_rights_status=status,
        us_rights_claim_ids=[c.claim_id for c in claims],
        partnerships=partnerships,
        open_questions=open_questions,
        us_rights_holder=holders[0] if len(holders) == 1 else None,
        us_rights_holder_claim_ids=[c.claim_id for c in chosen],
        us_rights_holder_conflict=holders if len(holders) > 1 else [],
        us_rights_basis=[_cited(c) for c in basis],
        us_rights_holder_basis=[_cited(c) for c in chosen],
        us_rights_all=[_cited(c) | _reading(c.value_as_written) for c in claims],
        us_rights_holder_all=[_cited(c) for c in holder_claims],
    )


def _reading(text: str) -> dict[str, Any]:
    reading = rights_reading(text)
    return {"reads": reading.status, "understood": reading.understood, "parties": list(reading.parties),
            "unread": list(reading.unread)}


def _cited(claim: SourceClaim) -> dict[str, Any]:
    return {"claim_id": claim.claim_id, "value": claim.value_as_written, "origin": claim.origin.value,
            "source_system": claim.source_system, "row": claim.row_number, "column": claim.column,
            "source": claim.source_reference, "source_date": claim.source_date.isoformat() if claim.source_date else None,
            "quote": claim.evidence_span}


__all__ = [
    "AVAILABLE", "AVAILABLE_CONFIRMED", "CONFLICTING", "ENCUMBERED", "NOT_AVAILABLE", "OPTION", "RETURNED",
    "RIGHTS_STATUS_WORDS", "UNKNOWN", "CommercialAssessment", "assess", "rights_reading", "rights_status",
]
