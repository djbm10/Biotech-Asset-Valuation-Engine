"""Checks run after a rights position is decided (cycle R1): leftover records explained, the company and top-tier
checks on a clear position, and staleness.

Split from ``rights_position.py`` (revision 5) to keep each file under 800 lines; the rules are in that module's
docstring.
"""

from __future__ import annotations

from datetime import date

from bve.dealscreen.rights import ACQUISITION, RightsEvent
from bve.dealscreen.rights_ledger import _ENDINGS, _GRANT_TYPES, _Ledger, _what, own_date
from bve.dealscreen.rights_model import (
    CLEAR_POSITIONS,
    P_CONFLICTING,
    RightsPosition,
    _is_company,
    _kind_words,
    _not_company,
    _owner_question,
)
from bve.dealscreen.rights_territory import party_key


def _returned_to_company(ledger: _Ledger, e: RightsEvent) -> bool:
    """An ending recorded without its grant that meets the standard a return-only record needs on its own (review
    R1v3 N4): both parties named, a date of its own, a territory covering the buyer's, and the rights returned to the
    program's company. Beside a clear position it is explained, not missing evidence (the "returned, now seeking a
    partner" case, REREVIEW K3)."""
    return (e.event_type in _ENDINGS and bool(e.grantee and e.grantor) and own_date(e) is not None
            and e.territory is not None and ledger.territory <= set(e.territory)
            and _is_company(ledger, e.grantor))


def _explain_leftovers(ledger: _Ledger, pos: RightsPosition, used: list[RightsEvent]) -> None:
    """Explain every outcome that was not applied. Each one also means the record is not complete."""
    for e, grants in ledger.ambiguous:
        pos.reasons.append(f"{_what(e)} could apply to {len(grants)} grants; none was cleared")
        pos.questions.append(f"Which of the grants to {e.grantee or e.grantor} did the {e.words} ({e.when}) end?")
        ledger.blockers.append(f"complete: {_what(e)} could apply to {len(grants)} grants")
        used.append(e)
    for e, g in ledger.unordered:
        grant = f"the grant to {ledger.display(g.holder)} ({g.event.when})"
        pos.reasons.append(f"{_what(e)} may predate {grant}: the dates cannot order them, so the grant is kept")
        pos.questions.append(f"Did the {e.words} ({e.when}) end {grant}? The dates cannot order them.")
        ledger.blockers.append(f"complete: {_what(e)} cannot be ordered against {grant}")
        used.append(e)
    for e in ledger.earlier:
        pos.reasons.append(f"{_what(e)} is dated before every recorded grant to that party; it is read as ending "
                           "an earlier deal not in the evidence")
        pos.questions.append(f"Which deal did the {e.words} ({e.when}) end?")
        ledger.blockers.append(f"complete: {_what(e)} ended a deal that is not in the evidence")
        used.append(e)
    for e, g in ledger.misdated:
        pos.reasons.append(f"{_what(e)} is linked to deal {e.related_deal_id} but dated before it ({g.event.when})")
        pos.questions.append(f"Which date is wrong: the {e.words} ({e.when}) or deal {e.related_deal_id} "
                             f"({g.event.when})?")
        ledger.blockers.append(f"complete: {_what(e)} is dated before deal {e.related_deal_id}, which it is linked to")
        used.append(e)
    for e, g in ledger.repeated:
        pos.reasons.append(f"{_what(e)} repeats the end of the grant to {ledger.display(g.holder)} "
                           f"({g.event.when}), which had already ended")
        used.append(e)
    for e, g in ledger.kept:
        pos.reasons.append(f"{_what(e)} names a territory that cannot be read ({e.territory_as_written}); the grant "
                           f"to {ledger.display(g.holder)} is kept")
        pos.questions.append(f"Which territories did the {e.words} ({e.when}, {e.territory_as_written}) cover?")
        ledger.blockers.append(f"complete: {_what(e)} names a territory that cannot be read")
        used.append(e)
    for e in ledger.unmatched:
        if pos.position in CLEAR_POSITIONS and _returned_to_company(ledger, e):
            pos.reasons.append(f"{_what(e)} ended a grant that is not in the evidence and returned the rights "
                               f"covering {ledger.terr} to {e.grantor}, the program's company per the landscape")
            used.append(e)
            continue
        pos.reasons.append(f"{_what(e)} matches no recorded grant")
        party = e.grantee or e.grantor
        others = [h for h in pos.holders if not ledger.same(h, party)]
        if pos.position == P_CONFLICTING and others:  # never "is X the successor of X" (review R1v4 O-12)
            pos.questions.append(f"Is {party} the successor of {', '.join(others)}? If so, the grant has ended: "
                                 "record the acquisition or link the deal id.")
        ledger.blockers.append(f"complete: {_what(e)} matches no recorded grant")
        used.append(e)
    if ledger.after_as_of:  # review R1v3 N10: not known on the as-of date
        assert ledger.as_of is not None
        pos.reasons.append(f"not applied, dated after the as-of date {ledger.as_of.isoformat()}: "
                           + "; ".join(_what(e) for e in ledger.after_as_of))
        used += ledger.after_as_of
    used += ledger.unapplied
    pos.reasons += ledger.notes
    pos.questions += ledger.questions


def _owner_check(ledger: _Ledger, pos: RightsPosition) -> None:
    """The owner per evidence (the licensor at the root of the recorded grants, after acquisitions) must be the
    program's company per the landscape on every clear path; otherwise it may hold the rights under a license from
    the company (review R1v4 H1, H2)."""
    owner = ledger.owner()
    if owner and not _is_company(ledger, owner):
        ledger.blockers.append(_not_company(ledger, f"the owner per the rights evidence is {owner}", owner))
        pos.questions.append(_owner_question(ledger, owner))


def _clear_checks(ledger: _Ledger, pos: RightsPosition) -> None:
    """A clear position reaches the top tiers only if it is complete, specific and current (module docstring).
    Age is judged on the own date of each record the position rests on, never on a later report or an
    unrelated acquisition (review R1v3 N7)."""
    blockers = list(ledger.blockers)
    if ledger.as_of is None:
        blockers.append("current: no as-of date, so the age of the evidence cannot be judged")
    old: list[RightsEvent] = []
    for e in {e.event_id: e for e in ledger.deciding}.values():
        d = own_date(e)
        if d is None:
            blockers.append(f"current: {_what(e)} has no date of its own")
        elif ledger.as_of is not None and (ledger.as_of - d).days > ledger.max_age:
            old.append(e)
            blockers.append(f"current: {_what(e)} is more than {ledger.max_age} days before "
                            f"{ledger.as_of.isoformat()}")
    if old and ledger.as_of is not None:
        pos.stale = True
        pos.reasons += [f"{_what(e)}, which this position rests on, is more than {ledger.max_age} days before "
                        f"{ledger.as_of.isoformat()}" for e in old]
        pos.questions.append("Is this rights evidence still current?")
    pos.top_tier_blockers = list(dict.fromkeys(blockers))


def _old_grants(ledger: _Ledger, pos: RightsPosition, territory: frozenset[str], as_of: date | None,
                max_age_days: int) -> None:
    """Name active grants over the territory whose own newest evidence is old. In a conflict, or beside the
    deciding grant, an old grant may simply have ended (review R1v2 S2). The deciding grant of a settled
    position, and an older grant to the same holder (a re-license, review R1v3 W1), are covered by the
    position's own staleness. Acquisitions never make a grant's evidence newer (review R1v3 N7e)."""
    if as_of is None:
        return
    deciding = {party_key(ledger.current(e.grantee)) for e in ledger.decisive
                if e.event_type in _GRANT_TYPES and e.grantee}
    for g in ledger.grants:
        if not g.active or not (g.regions is None or g.regions & territory):
            continue
        if pos.position != P_CONFLICTING and (g.event in ledger.decisive
                                              or (g.holder and party_key(ledger.current(g.holder)) in deciding)):
            continue
        dated = [e for e in ledger.deal_events(g) if e.evidence_date]
        if not dated:
            continue
        newest = max(dated, key=lambda e: e.evidence_date or date.min)
        if (as_of - (newest.evidence_date or as_of)).days > max_age_days:
            what = f"{_kind_words(g)} to {ledger.display(g.holder)}"
            pos.reasons.append(f"the newest evidence for the {what} is dated {newest.evidence_date_text}, more than "
                               f"{max_age_days} days before {as_of.isoformat()}; it may have ended since")
            pos.questions.append(f"Is the {what} ({g.event.when}) still in force?")


def _staleness(pos: RightsPosition, decisive: list[RightsEvent], as_of: date | None, max_age_days: int) -> None:
    """For a position that is not clear: evidence age is measured from when it was stated (the source date, else
    the event date), on the evidence that decides the position. An acquisition is not evidence that a grant is
    still in force (review R1v3 N7e)."""
    dated = [e for e in decisive if e.evidence_date and e.event_type != ACQUISITION]
    if as_of and dated:
        latest = max(dated, key=lambda e: e.evidence_date or date.min)
        if (as_of - (latest.evidence_date or as_of)).days > max_age_days:
            pos.stale = True
            pos.reasons.append(f"latest evidence for this position is dated {latest.evidence_date_text}, more than "
                               f"{max_age_days} days before {as_of.isoformat()}")
            pos.questions.append("Is this rights evidence still current?")
