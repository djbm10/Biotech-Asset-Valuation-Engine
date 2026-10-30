"""Buyer-declared transaction preferences and the transaction view (cycle C1 X5, cycle R1).

Scientific eligibility answers "does this program fit the biology the buyer wants?". The transaction
view answers "is it an opportunity this buyer can pursue?", from the rights evidence and the buyer's
declared preferences only. It never changes a gate, a disposition or the scientific rank.

Cycle R1 removed the ``OPEN`` tier. It read as "pursuable" while it only meant "no obstacle declared",
including when the tool held no rights evidence at all. The tiers now say what the evidence shows:

- ``AVAILABILITY_STATED_UNVERIFIED``: a current source states availability or a partner search.
- ``NO_OBSTACLE_IN_RIGHTS_EVIDENCE``: rights evidence exists and shows no grant over the buyer territory
  (e.g. rights returned, or deals that cover other territories). Not availability.
- ``RIGHTS_UNRESOLVED``: no rights evidence, conflicting evidence, or a grant whose territory is unstated.
- ``DEPRIORITIZED`` / ``EXCLUDED_BY_BUYER_PREFERENCE``: per the buyer's declared preferences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bve.dealscreen import rights as r
from bve.dealscreen.commercial import (
    AVAILABLE,
    AVAILABLE_CONFIRMED,
    CONFLICTING,
    ENCUMBERED,
    NOT_AVAILABLE,
    OPTION,
    RETURNED,
)


class TransactionPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: What to do with a program marketed in the U.S. per source.
    marketed: Literal["exclude", "deprioritize", "ignore"] = "ignore"
    #: Holders the buyer considers unattractive counterparties. Matched against the rights holder per
    #: evidence first, then (flagged as not a rights statement) the registry sponsor / labeler.
    deprioritized_holders: list[str] = Field(default_factory=list)
    #: Rights licensed, optioned, shared or acquired by a third party in the buyer territory, per evidence.
    encumbered_rights: Literal["exclude", "deprioritize", "ignore"] = "ignore"
    #: Whether rights returned to the originator sort ahead of other no-obstacle programs.
    returned_rights: Literal["prefer", "neutral"] = "neutral"
    #: Buyer territory (region codes, see ``rights.REGIONS``). Empty -> the buyer's ``required_market``.
    territory: list[str] = Field(default_factory=list)
    #: Rights evidence older than this (relative to the rights file's latest date) is flagged stale.
    max_evidence_age_days: int = Field(default=730, ge=1)


TIER_ORDER = {
    "AVAILABILITY_STATED_UNVERIFIED": 0,
    "NO_OBSTACLE_IN_RIGHTS_EVIDENCE": 1,
    "RIGHTS_UNRESOLVED": 2,
    "DEPRIORITIZED": 3,
    "EXCLUDED_BY_BUYER_PREFERENCE": 4,
}


@dataclass
class TransactionView:
    tier: str
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    position: str = r.P_NONE
    holder: str | None = None
    questions: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    stale: bool = False
    sort_bonus: int = 0


def _matches(name: str | None, holders: list[str]) -> str | None:
    """Whole-word match of a declared holder name (review C1-7): "Ono" does not match "Sonoma"."""
    for holder in holders:
        if holder.strip() and re.search(rf"(?<!\w){re.escape(holder.strip())}(?!\w)", name or "", re.IGNORECASE):
            return holder
    return None


_FROM_FIELD = {  # the landscape's free-text U.S.-rights field, when no rights file covers the program
    ENCUMBERED: r.P_LICENSED, OPTION: r.P_OPTION, RETURNED: r.P_RETURNED, AVAILABLE: r.P_AVAILABILITY,
    AVAILABLE_CONFIRMED: r.P_AVAILABILITY, CONFLICTING: r.P_CONFLICTING, NOT_AVAILABLE: r.P_LICENSED,
}


def position_from_field(rights_status: str, holder: str | None) -> r.RightsPosition:
    position = _FROM_FIELD.get(rights_status, r.P_NONE)
    if position == r.P_NONE:
        return r.RightsPosition(r.P_NONE, reasons=[("no rights evidence (landscape rights field empty or "
                                                   "uninformative; no rights file record)")],
                                questions=[("Who holds rights in the buyer territory? The registry sponsor "
                                           "is not evidence of ownership.")])
    return r.RightsPosition(position, holder=holder,
                            reasons=[f"landscape U.S.-rights field reads {rights_status} (no rights file record)"],
                            questions=["Confirm the landscape's rights statement against a primary source."])


def assess_transaction(
    prefs: TransactionPreferences | None,
    *,
    market_status: str | None,
    rights_status: str,
    rights_holder: str | None,
    company: str | None,
    identity_twins: list[str],
    position: r.RightsPosition | None = None,
) -> TransactionView:
    notes = [f"may be the same molecule as {', '.join(identity_twins)} (identity flag; check its resolution)"] if identity_twins else []
    pos = position or position_from_field(rights_status, rights_holder)
    if pos.position == r.P_RETURNED:
        notes.append("rights returned to the originator per source (not a statement of availability)")
    if pos.stale:
        notes.append("rights evidence is stale; confirm it is current")
    base = {"position": pos.position, "holder": pos.holder, "questions": list(pos.questions),
            "evidence": list(pos.evidence), "stale": pos.stale}
    if prefs is None:
        return TransactionView("NOT_DECLARED", [], notes, **base)
    excluded: list[str] = []
    deprioritized: list[str] = []
    if market_status == "US_MARKETED" and prefs.marketed != "ignore":
        (excluded if prefs.marketed == "exclude" else deprioritized).append("marketed in the U.S. per source")
    holder = pos.holder if pos.position in r.ENCUMBRANCE_POSITIONS | {r.P_UNSTATED} else None
    if (hit := _matches(holder or rights_holder, prefs.deprioritized_holders)):
        deprioritized.append(f"rights holder per cited evidence matches '{hit}'")
    elif (hit := _matches(company, prefs.deprioritized_holders)):
        deprioritized.append(f"registry sponsor / labeler matches '{hit}' (not a rights statement; verify)")
    if pos.position in r.ENCUMBRANCE_POSITIONS and prefs.encumbered_rights != "ignore":
        (excluded if prefs.encumbered_rights == "exclude" else deprioritized).extend(pos.reasons)
    if excluded:
        return TransactionView("EXCLUDED_BY_BUYER_PREFERENCE", excluded + deprioritized, notes, **base)
    if deprioritized:
        return TransactionView("DEPRIORITIZED", deprioritized + [x for x in pos.reasons if x not in deprioritized],
                               notes, **base)
    if pos.position == r.P_AVAILABILITY:
        tier = "AVAILABILITY_STATED_UNVERIFIED"
    elif pos.position in {r.P_RETURNED, r.P_NOT_ENCUMBERED}:
        tier = "NO_OBSTACLE_IN_RIGHTS_EVIDENCE"
    elif pos.position in r.ENCUMBRANCE_POSITIONS:
        tier = "RIGHTS_UNRESOLVED"  # encumbered but the buyer chose to ignore encumbrance
    else:
        tier = "RIGHTS_UNRESOLVED"
    bonus = 1 if (pos.position == r.P_RETURNED and prefs.returned_rights == "prefer") else 0
    reasons = list(pos.reasons)
    if tier != "AVAILABILITY_STATED_UNVERIFIED":
        reasons.append("availability not evidenced")
    return TransactionView(tier, reasons, notes, sort_bonus=bonus, **base)


def transaction_ranks(screens: list[dict[str, Any]]) -> dict[str, int]:
    """Rank ELIGIBLE programs by tier, then buyer-declared bonus, then scientific rank."""
    eligible = [s for s in screens if s["disposition"] == "ELIGIBLE" and s.get("transaction", {}).get("tier")
                and s["transaction"]["tier"] != "NOT_DECLARED"]
    ordered = sorted(eligible, key=lambda s: (TIER_ORDER.get(s["transaction"]["tier"], 9),
                                              -s["transaction"].get("sort_bonus", 0), s["rank"] or 10**6))
    return {s["asset_id"]: i + 1 for i, s in enumerate(ordered)}


__all__ = ["TIER_ORDER", "TransactionPreferences", "TransactionView", "assess_transaction",
           "position_from_field", "transaction_ranks"]
