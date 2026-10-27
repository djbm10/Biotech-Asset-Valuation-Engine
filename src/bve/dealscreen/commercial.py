"""Commercial diligence status, kept independent of scientific eligibility.

U.S. licensing availability is the field most easily over-read. The rules:

- AVAILABLE only when a source explicitly says rights are available or a partner is
  sought, and then it is still "source-provided, unverified" until an analyst confirms it.
- Silence, "not reported" or an empty cell is UNKNOWN. No license recorded is not a
  license available, and a trial sponsor is not shown to be the rights owner.
- A recorded license, option or partnership covering the market is ENCUMBERED.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bve.dealscreen.models import LandscapeAsset, SourceClaim

AVAILABLE = "AVAILABLE_PER_SOURCE"
AVAILABLE_CONFIRMED = "AVAILABLE_ANALYST_CONFIRMED"
NOT_AVAILABLE = "NOT_AVAILABLE_PER_SOURCE"
ENCUMBERED = "ENCUMBERED_PER_SOURCE"
UNKNOWN = "UNKNOWN"
CONFLICTING = "CONFLICTING"

_NEGATED = re.compile(r"\b(not available|unavailable|no rights|rights retained by)\b", re.IGNORECASE)
_ENCUMBERED = re.compile(r"\b(licen[cs]ed|partnered|option(ed)?|co-?develop\w*|co-?promot\w*|exclusive|encumber\w*)\b", re.IGNORECASE)
_AVAILABLE = re.compile(r"\b(available|seeking (a )?partner\w*|open to partner\w*)\b", re.IGNORECASE)
#: "Unpartnered" says no license is recorded. That is not availability.
_UNKNOWN = re.compile(
    r"\b(not reported|unknown|undisclosed|n/?a|none recorded|unpartnered|no partner\w*)\b", re.IGNORECASE
)


def rights_status(text: str) -> str:
    if not text.strip() or _UNKNOWN.search(text):
        return UNKNOWN
    if _NEGATED.search(text):
        return NOT_AVAILABLE
    if _ENCUMBERED.search(text):
        return ENCUMBERED
    if _AVAILABLE.search(text):
        return AVAILABLE
    return UNKNOWN


@dataclass
class CommercialAssessment:
    asset_id: str
    ownership_per_source: str | None
    ownership_note: str
    us_rights_status: str
    us_rights_claim_ids: list[str]
    partnerships: list[str]
    open_questions: list[str] = field(default_factory=list)

    @property
    def display(self) -> str:
        return {
            AVAILABLE: "AVAILABLE (source-provided, unverified)",
            AVAILABLE_CONFIRMED: "AVAILABLE (analyst-confirmed)",
            NOT_AVAILABLE: "NOT AVAILABLE (source-provided)",
            ENCUMBERED: "ENCUMBERED (source-provided)",
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
    statuses = {rights_status(c.value_as_written) for c in (confirmed[-1:] or claims)}
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
    ]
    if status == AVAILABLE and partnerships:
        status = CONFLICTING  # "available" alongside a recorded partnership needs a human
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
    )
