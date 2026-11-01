"""The rights position and the helpers shared by the rights modules (cycle R1).

Split from ``rights_position.py`` (revision 5) to keep each file under 800 lines. ``rights_position`` is the public
interface and re-exports the public names.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bve.dealscreen.rights import CO_DEVELOPMENT, OPTION, RightsEvent
from bve.dealscreen.rights_ledger import UNNAMED, _Grant, _Ledger, own_date
from bve.dealscreen.rights_territory import party_key, same_company

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


def no_evidence_position(first_contact: str | None = None) -> RightsPosition:
    contact = (f" First contact: registry sponsor '{first_contact}' (not evidence of ownership)."
               if first_contact else " The registry sponsor is not evidence of ownership.")
    return RightsPosition(P_NONE, reasons=["no rights or deal record for this program in the imported rights evidence"],
                          questions=["Who holds rights in the buyer territory, and are any licensed, optioned or "
                                     "shared?" + contact])


def _is_company(ledger: _Ledger, name: str | None) -> bool:
    """The party is the program's company per the landscape: by name, or through recorded acquisitions (the
    company's acquirer, or a party the company acquired). The landscape company is used only to refuse."""
    if not (name and ledger.company):
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


def _cite(e: RightsEvent) -> dict[str, object]:
    return {"event_id": e.event_id, "deal_id": e.deal_id, "type": e.event_type, "type_words": e.words,
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
    "P_NOT_AVAILABLE", "P_NOT_ENCUMBERED", "P_OPTION", "P_OWNER_ACQUIRED", "P_RETURNED", "P_SHARED", "P_UNSTATED",
    "SHARED_POSITIONS", "RightsPosition", "no_evidence_position",
]
