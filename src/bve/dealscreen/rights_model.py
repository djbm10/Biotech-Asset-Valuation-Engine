"""The rights position and the helpers shared by the rights modules (cycle R1).

Split from ``rights_position.py`` (revision 5) to keep each file under 800 lines. ``rights_position`` is the public
interface and re-exports the public names.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from bve.dealscreen.rights import CO_DEVELOPMENT, OPTION, RightsEvent
from bve.dealscreen.rights_ledger import UNNAMED, _Grant, _Ledger, own_date
from bve.dealscreen.rights_territory import content_note, party_key, same_company

P_CONFLICTING = "CONFLICTING_EVIDENCE"
P_LICENSED = "LICENSED_IN_TERRITORY_PER_EVIDENCE"
P_OPTION = "OPTION_HELD_IN_TERRITORY_PER_EVIDENCE"
P_SHARED = "RIGHTS_SHARED_IN_TERRITORY_PER_EVIDENCE"
P_UNSTATED = "GRANT_TERRITORY_UNSTATED"
P_AVAILABILITY = "AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED"
P_RETURNED = "RIGHTS_RETURNED_PER_EVIDENCE"
P_OWNER_ACQUIRED = "OWNER_ACQUIRED_PER_EVIDENCE"
P_NOT_ENCUMBERED = "NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE"
P_NONE = "NO_RIGHTS_EVIDENCE"
#: Rights rows exist, but none gives a position on the as-of date (reviews R1v9 LBL-NONE, R1v11 LBL-DATE).
P_NOT_APPLIED = "RIGHTS_ROWS_NOT_APPLIED"
#: A landscape or analyst statement that rights are not available (no rights record; review R1v3 NA-label).
P_NOT_AVAILABLE = "NOT_AVAILABLE_PER_SOURCE"
#: Third-party rights in the buyer territory, or rights not available (governed by ``encumbered_rights``).
ENCUMBRANCE_POSITIONS = frozenset({P_LICENSED, P_OPTION, P_NOT_AVAILABLE})
#: Rights shared with a partner (governed by the buyer's ``shared_rights``).
SHARED_POSITIONS = frozenset({P_SHARED})
#: Positions that say no third party holds the buyer territory. Only these reach the two top transaction tiers.
CLEAR_POSITIONS = frozenset({P_RETURNED, P_NOT_ENCUMBERED, P_OWNER_ACQUIRED, P_AVAILABILITY})

@dataclass
class RightsPosition:
    position: str
    holder: str | None = None
    holders: list[str] = field(default_factory=list)
    owner: str | None = None
    event_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    stale: bool = False
    evidence: list[dict[str, object]] = field(default_factory=list)
    #: Why a clear position may not reach the two top transaction tiers ("check: detail"). Empty otherwise.
    top_tier_blockers: list[str] = field(default_factory=list)
    #: Holders or labelers added from the landscape's U.S.-rights holder field beside a rights-row position
    #: (``rights_gate.also_named``): named by the landscape, not shown by a rights row (review R1v11 LBL-OWNER).
    field_named: list[str] = field(default_factory=list)


def no_evidence_position(first_contact: str | None = None) -> RightsPosition:
    contact = (f" First contact: registry sponsor '{first_contact}' (not evidence of ownership)."
               if first_contact else " The registry sponsor is not evidence of ownership.")
    return RightsPosition(P_NONE, reasons=["no rights or deal record for this program in the imported rights evidence"],
                          questions=["Who holds rights in the buyer territory, and are any licensed, optioned or "
                                     "shared?" + contact])


def _is_company(ledger: _Ledger, name: str | None) -> bool:
    """The party is the program's company per the landscape: by name, or through recorded acquisitions (the
    company's acquirer, or a party the company acquired). The landscape company is used only to refuse."""
    if not (name and ledger.company) or content_note(name):  # a note may name a licensee (review R1v5 N)
        return False
    names = {name, ledger.current(name)}
    companies = {ledger.company, ledger.current(ledger.company)}
    return any(same_company(n, c) for n in names for c in companies if n and c)


def _not_company(ledger: _Ledger, what: str, party: str) -> str:
    if ledger.company:
        return (f"specific: {what}, but the landscape names {ledger.company} as the program's company; {party} may "
                "hold the rights under a license")
    return f"specific: {what}, and no program company is named to show that {party} owns the program"


def _owner_question(ledger: _Ledger, party: str) -> str:
    return (f"Does {party} own this program, or hold it under a license from {ledger.company}?" if ledger.company
            else f"Does {party} own this program, or hold it under a license?")


#: The fields of a cited rights row that a human confirmation of the row is tied to (cycle R1 revisions 12-13). The
#: event id (which holds the rights file's hash and the row number), the dataset version and wording labels are not:
#: a re-import of an unchanged row keeps its confirmation, and a row for another program or deal never shares it
#: (review R1v12 CONFIRM-REIMPORT).
_CONFIRMED_FIELDS = ("external_id", "deal_id", "related_deal_id", "type", "grantee", "grantor", "territory",
                     "exclusivity", "date", "source_date", "status", "source", "quote")
#: The fields that name a row across versions: a confirmation recorded for a row with these values and other content
#: is "for an earlier version of this row".
_ROW_KEY_FIELDS = ("external_id", "deal_id", "type")


def row_sha256(cite: dict[str, object]) -> str:
    """Hash of what an analyst confirms about a rights row: its parties, type, territory, dates, status, source and
    quote. Any change to these after the confirmation means the confirmation no longer applies."""
    body = {k: str(cite.get(k)) for k in _CONFIRMED_FIELDS}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def row_key(cite: dict[str, object]) -> str:
    """Hash of what names a rights row across versions: its program, deal and type."""
    body = {k: str(cite.get(k)) for k in _ROW_KEY_FIELDS}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def cite_event(e: RightsEvent) -> dict[str, object]:
    """A rights row as it is cited beside a position."""
    return _cite(e)


def _cite(e: RightsEvent) -> dict[str, object]:
    return {"event_id": e.event_id, "external_id": e.external_id, "deal_id": e.deal_id,
            "related_deal_id": e.related_deal_id, "type": e.event_type, "type_words": e.words,
            "grantee": e.grantee, "grantor": e.grantor, "territory": e.territory_as_written,
            "exclusivity": e.exclusivity, "date": e.event_date_text, "source_date": e.source_date_text,
            "status": e.status, "source_system": e.source_system, "source": e.source_reference,
            "quote": e.evidence_quote, "row": e.row_number}


def _start(e: RightsEvent) -> int:
    d = own_date(e)
    return d.toordinal() if d else 0


def _partners(ledger: _Ledger, g: _Grant) -> list[str]:
    """Who holds a grant: its holder, plus the partner when rights are shared."""
    holder = ledger.display(g.holder)
    if not g.shared:
        return [holder]
    partner = ledger.display(g.grantor) if g.event.event_type == CO_DEVELOPMENT else ledger.owner()
    return [h for h in dict.fromkeys((holder, partner)) if h]


def _held_by(ledger: _Ledger, g: _Grant) -> str:
    """The holder as recorded, with its current name when an acquisition changed it (review R1v3 H3)."""
    if not g.holder:
        return UNNAMED
    now = ledger.current(g.holder)
    return g.holder if party_key(now) == party_key(g.holder) else f"{g.holder} (now {now})"


def _kind_words(g: _Grant) -> str:
    return "option" if g.kind == OPTION else ("shared rights" if g.shared else "license")


__all__ = [
    "CLEAR_POSITIONS", "ENCUMBRANCE_POSITIONS", "P_AVAILABILITY", "P_CONFLICTING", "P_LICENSED", "P_NONE",
    "P_NOT_APPLIED", "P_NOT_AVAILABLE", "P_NOT_ENCUMBERED", "P_OPTION", "P_OWNER_ACQUIRED", "P_RETURNED", "P_SHARED", "P_UNSTATED",
    "SHARED_POSITIONS", "RightsPosition", "no_evidence_position",
]
