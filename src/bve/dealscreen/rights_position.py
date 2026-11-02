"""What the rights evidence says for one program in one buyer territory (cycle R1).

Inputs are imported rights events only. Nothing is read from the registry sponsor, the FDA labeler or the
landscape's company column. Each rule below exists because a review of R1 found a failure:

- Events apply in date order. A date keeps its precision: "2024" is any day of 2024. A grant takes effect
  at the start of its period, an outcome (termination, return, option exercise or lapse) at the end, so
  an outcome sees every grant that could precede it. A grant with no event date of its own (undated, or
  dated only by the report that records it) is taken as existing from the start; its report date still
  bounds it, so an outcome dated before that report cannot be ordered against it. An outcome with no event
  date is placed at its report date, else matched last, against every grant.
- An outcome applies to exactly one grant: the one its related deal id names, or the single grant held by
  the named party (or, when only the licensor is named, the single grant from that licensor). When more
  than one grant could be meant, nothing is cleared and the ambiguity is reported with a question. An
  ending with no event date of its own (undated, or dated only by its report) may describe a grant that
  already ended, so ended grants count as candidates too: a second record of one termination never
  clears a later re-license.
- When an outcome and the grant it names fall in the same period, their order is unknown: the grant is
  kept and the evidence is conflicting. Outcomes linked by deal id, and option exercises or lapses, follow
  their grant by definition. An outcome dated before every grant to its party ended an earlier deal; it is
  reported, not applied. An outcome linked by deal id to a later deal is conflicting.
- An outcome with a stated territory changes only that territory: a termination or lapse removes it, an
  exercise turns it into a license and leaves the option elsewhere. A territory that is written but cannot
  be read changes nothing; the grant is kept and a question is asked.
- An option recorded as both exercised and lapsed is a conflict: the order cannot be trusted.
- An acquisition of a party that holds a grant passes the grant to the acquirer, and is cited. An
  acquisition that makes licensor and licensee one company ends the grant: the owner holds the rights.
  An acquisition of a party that holds no grant (the owner) changes the owner; that is not a third-party
  encumbrance.
- A license granted by a licensee is a sublicense, not a competing grant; the sublicensee and the head
  licensee are both named holders. Every other grant over the territory is named, with its holder, even
  when one grant decides the position or its territory cannot be read.
- Absence of a grant is never availability. Availability is only "stated by a source", and only when the
  statement is dated, current, active or of unknown status, and names the buyer territory or no territory.
  A statement followed by a grant over the territory (still active, or since ended) is superseded.
- A return or termination with no recorded grant is read as it would be with its grant: one with no
  territory written ended the whole deal, and one whose territory covers the buyer territory ended it
  there; either is a return, with the missing grant asked about. One for other territories, or for a
  territory that cannot be read, is a question.
- An option exercised for part of its territory stays an option elsewhere; the exercise is cited with it.
- Staleness is judged on the evidence that decides the position, not on the freshest event in the file.
  Any other grant over the territory whose own evidence is old is named as possibly ended.
- The buyer territory must be region codes (``rights_territory.REGIONS``); anything else is refused.

Revision 4 (re-review 2): each rule that cleared rights from a thin record let a program into the top
transaction tiers, so a clear position now carries ``top_tier_blockers``: the checks it fails. Only a clear
position with none reaches the two top tiers (``transaction.assess_transaction``):

- complete: every record for the program is attached and explained. An unmatched, ambiguous, unordered or
  misdated outcome, an outcome that ended a deal not in the evidence, an acquisition that could not be
  applied, or acquisitions with no deal record at all, each block.
- specific: the records the position rests on name both parties; an ending names the licensee or is linked
  to its deal by id; a return recorded without its grant states a territory covering the buyer territory;
  who holds the rights now is established. A grant that names no licensee is held by "a licensee not named",
  never by its licensor. An acquisition applies only to the territory it states. A co-development ended by one
  partner is not ended: the other partner may hold all rights.
- current: each record the position rests on has its own date (the event date, else the date of the report
  that records it) within the buyer's age limit; a later source date or an acquisition never refreshes it, and
  an undated record never qualifies. An option outcome is ordered against its option by the same rule as a
  license outcome. Records dated after the as-of date are not applied.
- uncontested is checked by ``rights_gate``: a landscape or analyst rights statement or holder that disagrees, or
  that DealScreen cannot read.

Revision 5 (re-review 3): the checks cover every clear path, not only returns.

- An availability statement does not excuse the grants it would clear: each ended grant over the territory passes
  the same specific checks as on the returned path, and each record that ended it must have a date of its own and
  come before the statement (review R1v4 A1). The statement itself is what makes the position current.
- The party a clear position rests on must be the program's company per the landscape, or its acquirer, or a party
  it acquired: the maker of an availability statement, and the owner per evidence (the licensor at the root of the
  recorded grants) on every clear path. A statement never makes its maker the owner (review R1v4 A2, H1, H2).
- A position with no grant over the territory rests on the newest recorded grant, not on every old deal elsewhere
  (review R1v4 G6). A dated ending of a grant whose own row is only marked terminated dates that ending; it is not a
  repeat (G5b). An ended co-development whose partners include the program's company is held by that company (G8).
"""

from __future__ import annotations

from datetime import date

from bve.dealscreen.rights import (
    CO_DEVELOPMENT,
    CO_PROMOTION_OPTION,
    LICENSE,
    OPTION,
    OPTION_EXERCISED,
    OPTION_LAPSED,
    RightsEvent,
)
from bve.dealscreen.rights_checks import (
    _clear_checks,
    _explain_leftovers,
    _old_grants,
    _owner_check,
    _staleness,
)
from bve.dealscreen.rights_ledger import (
    _ENDINGS,
    UNNAMED,
    _article,
    _definitely_after,
    _ever_covers,
    _Grant,
    _Ledger,
    _unreadable_territory,
    _what,
    own_date,
)
from bve.dealscreen.rights_model import (
    CLEAR_POSITIONS,
    ENCUMBRANCE_POSITIONS,
    P_AVAILABILITY,
    P_CONFLICTING,
    P_LICENSED,
    P_NONE,
    P_NOT_APPLIED,
    P_NOT_AVAILABLE,
    P_NOT_ENCUMBERED,
    P_OPTION,
    P_OWNER_ACQUIRED,
    P_RETURNED,
    P_SHARED,
    P_UNSTATED,
    SHARED_POSITIONS,
    RightsPosition,
    _cite,
    _held_by,
    _is_company,
    _kind_words,
    _not_company,
    _owner_question,
    _partners,
    _start,
    no_evidence_position,
)
from bve.dealscreen.rights_territory import REGIONS, party_key

#: Statuses under which an availability statement still counts.
_LIVE_STATUSES = frozenset({"ACTIVE", "UNKNOWN"})

def _primary(ledger: _Ledger, in_terr: list[_Grant]) -> tuple[_Grant, list[str], list[_Grant]]:
    """The grant that decides the position, why, and the head license behind it when it is a sublicense.
    Exclusive license > option > shared."""
    rank = {LICENSE: 0, OPTION: 1, CO_DEVELOPMENT: 2}
    # Among equals the newest grant decides: a re-license is the current one (review R1v3 W1).
    ordered = sorted(in_terr, key=lambda g: (g.shared, rank.get(g.kind, 3), -_start(g.event)))
    g = ordered[0]
    reasons: list[str] = []
    heads: list[_Grant] = []

    def head_of(s: _Grant) -> _Grant | None:  # the grant whose holder licensed s, when s is a sublicense
        if s.shared or s.kind != LICENSE:
            return None
        return next((h for h in in_terr if h is not s and not h.shared and ledger.same(h.holder, s.grantor)), None)

    head = head_of(g)
    if head is None:  # g's holder may have sublicensed: the sublicensee holds the rights in practice
        sub = next((s for s in in_terr if s is not g and head_of(s) is g), None)
        head, g = (g, sub) if sub is not None else (None, g)
    if head is not None:
        reasons.append(f"{ledger.display(g.holder)} holds a sublicense from {ledger.display(head.holder)}, which "
                       f"holds the head license ({head.event.territory_as_written or 'territory not stated'})")
        heads.append(head)
    if g.holder and ledger.current(g.holder) != g.holder:
        reasons.append(f"{g.holder} was acquired by {ledger.current(g.holder)} per a recorded acquisition")
    return g, reasons, heads


def _exclusive(g: _Grant) -> bool:
    """An exclusive (or exclusivity not stated) license or option over the rights themselves."""
    return (not g.shared and g.kind in {LICENSE, OPTION} and g.event.event_type != CO_PROMOTION_OPTION
            and g.event.exclusivity != "NON_EXCLUSIVE")


def _competing(ledger: _Ledger, in_terr: list[_Grant]) -> set[str]:
    """Exclusive licenses or options over the territory held by different parties (sublicenses excepted)."""
    exclusive = [g for g in in_terr if _exclusive(g)]
    holders = {party_key(ledger.current(g.holder)) for g in exclusive}
    sublicensees = {party_key(ledger.current(s.holder)) for s in exclusive if s.kind == LICENSE
                    and any(ledger.same(s.grantor, g.holder) for g in exclusive if g is not s)}
    return holders - sublicensees if len(holders - sublicensees) > 1 else set()


def _option_question(ledger: _Ledger, g: _Grant, where: str) -> str:
    holder = ledger.display(g.holder)
    done = "; ".join(f"exercised for {e.territory_as_written} ({e.when})" for e in g.partly_exercised)
    if done:
        return (f"Has {holder} exercised, declined or let lapse its option ({where}) for the rest of its territory? "
                f"Recorded so far: {done}.")
    return f"Has {holder} exercised, declined or let lapse its option ({where})? No outcome is recorded."


def _partial_reasons(ledger: _Ledger, g: _Grant) -> list[str]:
    return [f"{ledger.display(g.holder)} exercised the option for {e.territory_as_written} ({e.when}); the option is "
            "kept for the rest of its territory" for e in g.partly_exercised]


def _also(ledger: _Ledger, pos: RightsPosition, in_terr: list[_Grant], g: _Grant, terr: str) -> None:
    """Name every other grant over the territory: a second license or option is still an encumbrance."""
    for o in in_terr:
        if o is g or ledger.same(o.holder, g.holder) or (not o.shared and ledger.same(o.holder, g.grantor)):
            continue  # the deciding grant, another grant to its holder, or the license it sublicenses
        names = _partners(ledger, o)
        where = o.event.territory_as_written or "territory not stated"
        pos.reasons.append(f"also recorded over {terr}: {_kind_words(o)} to {' and '.join(names)} ({where})")
        pos.holders += [n for n in names if n not in pos.holders]
        if o.kind == OPTION:
            pos.reasons += _partial_reasons(ledger, o)
            pos.questions.append(_option_question(ledger, o, where))


def _also_unstated(ledger: _Ledger, pos: RightsPosition, unstated: list[_Grant], terr: str) -> None:
    """Grants whose territory cannot be read may also cover the buyer territory: name them and ask."""
    for o in unstated:
        names = _partners(ledger, o)
        where = o.event.territory_as_written or "not stated"
        pos.reasons.append(f"also recorded: {_kind_words(o)} to {' and '.join(names)} with no readable territory "
                           f"({where}); it may cover {terr}")
        pos.holders += [n for n in names if n not in pos.holders]
        pos.questions.append(f"Which territories does the grant to {names[0]} cover?")


def _encumbered(ledger: _Ledger, in_terr: list[_Grant], terr: str) -> RightsPosition:
    g, extra, heads = _primary(ledger, in_terr)
    ledger.decisive += ledger.grant_events(g) + [e for h in heads for e in ledger.grant_events(h)]
    holder = ledger.display(g.holder)
    where = g.event.territory_as_written or "territory not stated"
    if g.shared:
        holders = _partners(ledger, g)
        pos = RightsPosition(P_SHARED, holder=" and ".join(holders) + " (shared)", holders=list(holders))
        what = "co-development" if g.event.event_type == CO_DEVELOPMENT else "non-exclusive or co-promotion rights"
        pos.reasons.append(f"{what} shared by {' and '.join(holders)} covering {terr} ({where})")
        pos.questions.append(f"Would a transaction need both {' and '.join(holders)}? Rights are shared.")
        if (x := g.partner_exit) is not None:
            left = ledger.display(x.grantee or x.grantor)
            stay = next((h for h in holders if party_key(h) != party_key(left)), "the other partner")
            pos.reasons.append(f"{left} ended its part of the co-development ({x.when}); whether {stay} now holds "
                               f"all {terr} rights is not in the evidence")
            pos.questions.append(f"Does {stay} hold all {terr} rights after {left}'s exit ({x.when})?")
    else:
        head_names = [ledger.display(h.holder) for h in heads]
        pos = RightsPosition(P_OPTION if g.kind == OPTION else P_LICENSED, holder=holder,
                             holders=list(dict.fromkeys([holder, *head_names])))
        pos.reasons.append(f"{'option' if g.kind == OPTION else 'license'} to {holder} covering {terr} ({where})")
        if g.kind == OPTION:
            pos.reasons += _partial_reasons(ledger, g)
            pos.questions.append(_option_question(ledger, g, where))
        elif not g.holder:
            pos.questions.append(f"Who holds the license over {terr} from {ledger.display(g.grantor)} ({g.event.when})? "
                                 "The record names no licensee.")
        else:
            if g.event.exclusivity == "UNSTATED":
                pos.questions.append(f"Is the license to {holder} exclusive? The source does not say.")
            pos.questions.append(f"Is {holder}'s license over {terr} still in force, and would {holder} "
                                 "sublicense or transfer it?")
            pos.questions += [f"Would {head}, the head licensee, need to consent to a transaction?" for head in head_names]
    pos.reasons += extra
    _also(ledger, pos, in_terr, g, terr)
    return pos


def _conflict(ledger: _Ledger, blocking: list[_Grant], disputed: list[_Grant], competing: set[str],
              stated: list[RightsEvent], terr: str, exercised: list[RightsEvent]) -> RightsPosition:
    holders = sorted({h for g in blocking for h in _partners(ledger, g)}
                     | {ledger.display(e.grantee) for e in exercised})
    pos = RightsPosition(P_CONFLICTING, holders=holders,
                         holder=("; ".join(holders) + " (recorded; conflicting)") if holders else None)
    pos.reasons += [g.disputed for g in disputed if g.disputed]
    for e in exercised:  # an exercise is evidence of a license, even when its option is missing (review R1v3 N2)
        who = ledger.display(e.grantee)
        pos.reasons.append(f"{_what(e)} matches no recorded option; {who} may hold {terr} rights through it")
        pos.questions.append(f"Does {who} hold {terr} rights through the option it exercised ({e.when})? The option "
                             "is not in the evidence.")
    if competing:
        named = sorted({f"{_kind_words(g)} to {ledger.display(g.holder)}" for g in blocking if _exclusive(g)})
        pos.reasons.append(f"exclusive licenses or options covering {terr} to different parties (or exclusivity not "
                           "stated): " + "; ".join(named))
        pos.questions.append(f"Which license or option over {terr} is in force, and is any non-exclusive?")
    if stated and blocking:
        pos.reasons.append(f"a source states availability while an active grant covers {terr}")
        pos.questions.append("Has the recorded grant ended? A source also says the program is available.")
    if disputed:
        pos.questions.append("Was the option exercised or did it lapse? The records disagree.")
    return pos


def _statements(ledger: _Ledger, territory: frozenset[str], terr: str, used: list[RightsEvent]) -> list[RightsEvent]:
    """Availability statements that can count for the territory: live status, and a readable territory that
    covers it (or none written)."""
    usable = []
    for a in ledger.availability:
        if a.status not in _LIVE_STATUSES:
            ledger.notes.append(f"{_what(a)} has status {a.status.lower()}; not counted")
            used.append(a)
        elif _unreadable_territory(a):
            ledger.notes.append(f"{_what(a)} names a territory that cannot be read ({a.territory_as_written}); "
                                f"not counted for {terr}")
            ledger.questions.append(f"Does the availability statement ({a.when}) for {a.territory_as_written} "
                                    f"include {terr}?")
            used.append(a)
        elif a.territory is None or set(a.territory) & territory:
            if _current_record(ledger, a):
                usable.append(a)
            else:  # judged on its own date: a later report never refreshes it (review R1v3 N6, N7a)
                age = "undated" if own_date(a) is None else f"older than {ledger.max_age} days by its own date"
                ledger.notes.append(f"{_what(a)} is {age}; not counted")
                ledger.questions.append("When was availability stated, and is it current?")
                used.append(a)
    return usable


def _current_record(ledger: _Ledger, e: RightsEvent) -> bool:
    """Dated by its own date (event date, else report date) within the age limit. Without an as-of date age
    cannot be judged; the current check then blocks the top tiers anyway."""
    d = own_date(e)
    return d is not None and (ledger.as_of is None or (ledger.as_of - d).days <= ledger.max_age)


def _lapsed(g: _Grant) -> bool:
    """An option that lapsed: an option lapse, or its own row marked expired (review R1v3 H5)."""
    return bool(g.cleared_by) and all(c.event_type == OPTION_LAPSED or c is g.lapsed for c in g.cleared_by)


def _superseded(ledger: _Ledger, a: RightsEvent, blocking: list[_Grant], territory: frozenset[str]) -> bool:
    """A grant over the territory made after the statement means the search it announced has concluded."""
    if blocking and all(_definitely_after(g.event, a) for g in blocking):
        return True
    return any(not g.active and _ever_covers(g, territory) and _definitely_after(g.event, a) for g in ledger.grants)


def _ended_reason(ledger: _Ledger, g: _Grant, terr: str) -> str:
    if _lapsed(g):
        return f"option to {_held_by(ledger, g)} lapsed in {terr} per source; not a statement of availability"
    if g.event.event_type == CO_DEVELOPMENT:
        return (f"co-development between {' and '.join(_partners(ledger, g))} ended in {terr} per source; "
                "not a statement of availability")
    return f"grant to {_held_by(ledger, g)} ended in {terr} per source; not a statement of availability"


def _return_only(ledger: _Ledger, territory: frozenset[str], terr: str, used: list[RightsEvent]) -> RightsPosition | None:
    """A return or termination recorded without the grant it ended. Read as it would be with its grant: no
    territory written ends the whole deal; a readable territory over the buyer territory ends it there. With the
    grant missing, it can reach the top tiers only when it names both parties and a territory covering the buyer
    territory (review R1v3 N4)."""
    endings = [e for e in ledger.unmatched if e.event_type in _ENDINGS]
    whole = [e for e in endings if not (e.territory_as_written or "").strip()]
    covering = [e for e in endings if e.territory is not None and set(e.territory) & territory]
    if ledger.grants or not (covering or whole):
        return None
    e = (covering or whole)[-1]
    ledger.unmatched.remove(e)
    used.append(e)
    ledger.decisive.append(e)
    ledger.deciding.append(e)
    by = e.grantee or UNNAMED
    to = e.grantor or "the owner (not named)"
    if e in covering:
        reason = f"{_what(e)}: {by} returned rights covering {terr} to {to} per source"
        question = (f"Confirm that {to} holds the returned {terr} rights and has not licensed them since; the "
                    f"original grant to {by} is not in the evidence.")
    else:
        reason = (f"{_what(e)}: the deal between {by} and {to} ended per source; no territory is written, so it is "
                  "read as the whole deal")
        question = (f"Which territories did the deal with {by} cover, and does {to} hold the {terr} rights now? The "
                    "original grant is not in the evidence.")
    if not (e.grantee and e.grantor):
        ledger.blockers.append(f"specific: {_what(e)} does not name both parties, and the grant it ended is not in "
                               "the evidence")
    if e.territory is None:
        ledger.blockers.append(f"specific: {_what(e)} states no territory, and the grant it ended is not in the "
                               "evidence")
    elif not territory <= set(e.territory):
        ledger.blockers.append(f"specific: {_what(e)} covers only part of {terr}")
    # The recipient may be a licensee itself (a sublicense returned to its head licensee): it is the owner per
    # evidence only when it is the program's company per the landscape (review R1v3 N4d).
    owner = e.grantor if _is_company(ledger, e.grantor) else None
    questions = [question]
    if e.grantor and owner is None:
        ledger.blockers.append(_not_company(ledger, f"{_what(e)} returns the rights to {e.grantor}", e.grantor))
        questions.append(_owner_question(ledger, e.grantor))
    return RightsPosition(
        P_RETURNED, holder=e.grantor, holders=[e.grantor] if e.grantor else [], owner=owner,
        reasons=[f"{reason}; the original grant is not in the evidence; not a statement of availability"],
        questions=questions)


def _endings(g: _Grant, territory: frozenset[str]) -> list[RightsEvent]:
    return [c for c in g.cleared_by if c is g.event or c.territory is None or set(c.territory) & territory]


def _check_ended(ledger: _Ledger, g: _Grant, territory: frozenset[str], stated: list[RightsEvent] | None = None
                 ) -> None:
    """Record what an ended grant's clear position rests on (its endings over the territory) and what they lack:
    both parties of the grant, and an ending that names the licensee or is linked to the deal by id. Beside an
    availability statement (``stated``) the statement is what the position rests on; each ending must still have a
    date of its own and come before every statement (review R1v4 A1)."""
    endings = _endings(g, territory)
    if stated is None:
        ledger.deciding += endings
    else:
        for c in endings:
            ended = f"the end of the {_kind_words(g)} to {_held_by(ledger, g)} ({_what(c)})"
            if c is g.event:  # review R1v5 E1, E3: a status on the grant's own record dates the grant, not its end
                ledger.blockers.append(f"current: {ended} is stated only by the record's status, which gives the end "
                                       "no date of its own, so it cannot be ordered against the availability statement")
            elif own_date(c) is None:
                ledger.blockers.append(f"current: {ended} has no date of its own, so it cannot be ordered against "
                                       "the availability statement")
            elif any(not _definitely_after(a, c) for a in stated):
                ledger.blockers.append(f"complete: {ended} is not dated before every availability statement; a "
                                       "statement made while the grant was in force may not describe the rights now")
    what = f"the {_kind_words(g)} ({g.event.when})"
    if not g.holder:
        ledger.blockers.append(f"specific: {what} names no licensee")
    if not g.grantor:
        ledger.blockers.append(f"specific: {what} to {_held_by(ledger, g)} names no licensor")
    unlinked = [c for c in endings if c is not g.event and not (c.related_deal_id and c.related_deal_id == g.event.deal_id)]
    for c in unlinked:
        if not c.grantee:
            ledger.blockers.append(f"specific: {_what(c)} names only the licensor and is not linked to its deal by id")
    if unlinked and own_date(g.event) is None:  # review R1v3 N5, N9b: an undated grant cannot be ordered
        ledger.blockers.append(f"current: {what} to {_held_by(ledger, g)} has no date, so its ending cannot be "
                               "ordered against it")


def _merged_reason(g: _Grant) -> str:
    if g.intra_group:
        return (f"the grant from {g.grantor} to {g.holder} ({g.event.when}) is within one company as written (the "
                "names differ only by a corporate suffix); no third-party grant recorded")
    steps = "; ".join(f"{a.grantee} acquired {a.grantor} ({a.when})" for a in g.merged_by)  # review R1v3 H6
    return (f"{steps}; the grant between {g.grantor} and {g.holder} is now held within one company per source; no "
            "third-party grant recorded")


def _cleared(ledger: _Ledger, returned: list[_Grant], merged: list[_Grant], territory: frozenset[str],
             terr: str) -> RightsPosition | None:
    """Grants over the territory that ended: by a termination, return or lapse, or by a merger of the parties."""
    owner = ledger.owner()
    if returned:
        ledger.decisive += [e for g in returned for e in ledger.grant_events(g)]
        for g in returned:
            _check_ended(ledger, g, territory)
        reasons = [_ended_reason(ledger, g, terr) for g in returned]
        if not owner and (partner := _codevelopment_owner(ledger, returned)):
            owner = partner
            reasons.append(f"{partner}, a partner in the ended co-development, is the program's company per the "
                           "landscape")
        if not owner:
            ledger.blockers.append(f"specific: who holds the {terr} rights now is not established")
        lapsed_only = all(_lapsed(g) for g in returned)
        holders = [] if lapsed_only or not owner else [owner]
        pos = RightsPosition(P_NOT_ENCUMBERED if lapsed_only else P_RETURNED, holder=None if lapsed_only else owner,
                             holders=holders, owner=owner, reasons=reasons)
        if not owner:
            pos.questions.append(f"Who holds {terr} rights now (owner not established)?" if lapsed_only else
                                 f"Who holds the returned {terr} rights now (owner not established), and have they "
                                 "been re-licensed since?")
        else:
            pos.questions.append(f"Does {owner} hold the {terr} rights now?" if lapsed_only else
                                 f"Does {owner} hold the returned {terr} rights now, and have they been re-licensed "
                                 "since?")
        return pos
    if merged:
        ledger.decisive += [e for g in merged for e in [*g.merged_by, g.event]]
        ledger.deciding += [e for g in merged for e in (g.merged_by or [g.event])]
        if not owner:
            ledger.blockers.append(f"specific: who holds the {terr} rights now is not established")
        return RightsPosition(P_OWNER_ACQUIRED, holder=owner, holders=[owner] if owner else [],
                              reasons=[_merged_reason(g) for g in merged],
                              questions=[f"Would {owner or 'the owner'} license or sell {terr} rights?"])
    return None


def _codevelopment_owner(ledger: _Ledger, returned: list[_Grant]) -> str | None:
    """An ended co-development leaves the rights with the partner that is the program's company per the landscape,
    when exactly one partner is (review R1v4 G8). Otherwise who holds them is not established."""
    if not all(g.event.event_type == CO_DEVELOPMENT for g in returned):
        return None
    partners = {ledger.display(p) for g in returned for p in (g.holder, g.grantor) if p}
    company = [p for p in partners if _is_company(ledger, p)]
    return company[0] if len(company) == 1 else None


def _decide(ledger: _Ledger, territory: frozenset[str], used: list[RightsEvent]) -> RightsPosition:
    terr = ledger.terr
    ledger.merge_internal()
    covering = [g for g in ledger.grants if g.active and g.regions is not None and g.regions & territory]
    unstated = [g for g in ledger.grants if g.active and g.regions is None]
    blocking = covering + unstated
    disputed = [g for g in ledger.grants if g.disputed and (g.regions is None or g.regions & territory)]
    merged = [g for g in ledger.grants if (g.merged_by or g.intra_group) and _ever_covers(g, territory)]
    returned = [g for g in ledger.grants if g.cleared_by and not (g.merged_by or g.intra_group) and g not in covering
                and _ever_covers(g, territory)]
    # An exercise with no recorded option still evidences a license (review R1v3 N2, H1).
    exercised = [e for e in ledger.unmatched if e.event_type == OPTION_EXERCISED
                 and (e.territory is None or set(e.territory) & territory)]
    stated = _statements(ledger, territory, terr, used)
    superseded = [a for a in stated if _superseded(ledger, a, blocking, territory)]
    stated = [a for a in stated if a not in superseded]
    ledger.notes += [f"{_what(a)} was followed by a grant over {terr}; superseded" for a in superseded]
    unordered = [g for _, g in ledger.unordered if g in blocking]
    competing = _competing(ledger, covering)
    for g in blocking + disputed + returned + merged:
        used += ledger.grant_events(g)
    used += stated + superseded
    if disputed or competing or exercised or (blocking and (stated or ledger.unmatched or ledger.misdated or unordered)):
        # the outcomes that make it a conflict are decisive too, though they are cited later
        ledger.decisive += [*used, *ledger.unmatched, *(e for e, _ in ledger.misdated),
                            *(e for e, g in ledger.unordered if g in blocking)]
        ledger.unmatched = [e for e in ledger.unmatched if e not in exercised]  # explained by the conflict
        used += exercised
        return _conflict(ledger, blocking, disputed, competing, stated, terr, exercised)
    if covering:
        pos = _encumbered(ledger, covering, terr)
        _also_unstated(ledger, pos, unstated, terr)
        return pos
    if unstated:
        holder = ledger.display(unstated[0].holder)
        ledger.decisive += ledger.grant_events(unstated[0])
        pos = RightsPosition(P_UNSTATED, holder=holder, holders=[holder], reasons=[
            (f"active {unstated[0].kind.lower().replace('_', '-')} to {holder} with no readable territory "
             f"({unstated[0].event.territory_as_written or 'not stated'}); it may cover {terr}")],
            questions=[f"Which territories does the grant to {holder} cover?"])
        _also_unstated(ledger, pos, unstated[1:], terr)
        return pos
    if stated:
        pos = _available(ledger, stated, terr)
        _ended_beside_statement(ledger, pos, returned, merged, territory, stated)
        return pos
    if (cleared := _cleared(ledger, returned, merged, territory, terr)) is not None:
        return cleared
    if ledger.owner_acquisitions:
        return _owner_acquired(ledger, terr, used)
    if ledger.grants:
        owner = ledger.owner()
        used += [e for g in ledger.grants for e in ledger.grant_events(g)]
        ledger.decisive += [g.event for g in ledger.grants]
        # The newest recorded grant shows the record is current; an old deal elsewhere says nothing about the
        # buyer territory now (review R1v4 G6).
        newest = max(ledger.grants, key=lambda g: _start(g.event))
        ledger.deciding += ledger.deal_events(newest)
        if not owner:
            ledger.blockers.append(f"specific: who holds the {terr} rights now is not established")
        licensor = f" (licensor per evidence: {owner})" if owner else " (owner not established)"
        # A grant reported before the as-of date but effective after it is not "another territory" (review R1v8
        # Q-FUT): the question says only what the deals in force show.
        scope = "Recorded deals in force on the as-of date" if ledger.announced else "Recorded deals"
        return RightsPosition(P_NOT_ENCUMBERED, holder=None, holders=[], reasons=[
            f"recorded grants do not cover {terr}; this is not a statement of availability"],
            questions=[f"Who holds {terr} rights? {scope} cover other territories only{licensor}."])
    if (returned_only := _return_only(ledger, territory, terr, used)) is not None:
        return returned_only
    recorded = "; ".join(_what(e) for e in ledger.unmatched)
    # review R1v9 LBL-NONE, R1v10 LBL-NONE2: rows are recorded (this path is reached only with events), but none
    # applies on the as-of date or gives a position; that is not the absence of rights evidence
    return RightsPosition(P_NOT_APPLIED, reasons=[
        "rights rows are recorded, but none applies on the as-of date to give a position"], questions=[
        f"Who holds {terr} rights now?" + (f" Recorded without the grant it concerns: {recorded}." if recorded else "")])


def _available(ledger: _Ledger, stated: list[RightsEvent], terr: str) -> RightsPosition:
    """Availability stated by a current source. Each counted statement must name its maker, the maker must be the
    program's company per the landscape (a statement by another party may be a licensee's; review R1v4 A2), and its
    territory must cover the whole buyer territory (A7a). Only a statement by the company names an owner or holder."""
    ledger.decisive += stated
    ledger.deciding += stated
    makers: list[str] = []
    for a in stated:
        party = a.grantor or a.grantee
        if not party:
            ledger.blockers.append("specific: the availability statement names no party")
            continue
        makers.append(party)
        if not _is_company(ledger, party):
            ledger.blockers.append(_not_company(ledger, f"{_article(a.words)} {a.words} ({a.when}) is made by {party}",
                                                party))
            ledger.questions.append(_owner_question(ledger, party))
        if a.territory is not None and not ledger.territory <= set(a.territory):
            ledger.blockers.append(f"specific: {_what(a)} covers only part of {terr} ({a.territory_as_written})")
    company = next((m for m in reversed(makers) if _is_company(ledger, m)), None)
    pos = RightsPosition(P_AVAILABILITY, holder=company, holders=[company] if company else [], owner=company, reasons=[
        "a source states the program is available or a partner is sought (unverified)"],
        questions=[(f"Confirm with {company or 'the owner'} that {terr} rights are unencumbered and available, and on "
                   "what terms.")])
    pos.reasons += [f"stated by {m}" + ("" if _is_company(ledger, m) else ", which the landscape does not name as the "
                                        "program's company") for m in dict.fromkeys(makers)]
    if all(not a.territory_as_written for a in stated):
        pos.reasons.append("the statement does not name a territory")
        pos.questions.append(f"Which territories are offered? The statement does not say whether {terr} is included.")
    return pos


def _ended_beside_statement(ledger: _Ledger, pos: RightsPosition, returned: list[_Grant], merged: list[_Grant],
                            territory: frozenset[str], stated: list[RightsEvent]) -> None:
    """Grants over the territory that ended, beside an availability statement: the statement does not excuse them
    from the checks a return must pass (review R1v4 A1), and the position says they are treated as ended (O-1)."""
    ledger.decisive += [e for g in returned for e in ledger.grant_events(g)]
    for g in returned:
        _check_ended(ledger, g, territory, stated)
        pos.reasons.append(_ended_reason(ledger, g, ledger.terr))
    for g in merged:
        ledger.decisive += [*g.merged_by, g.event]
        for a in g.merged_by:
            if own_date(a) is None:
                ledger.blockers.append(f"current: {_what(a)} has no date of its own, so it cannot be ordered against "
                                       "the availability statement")
        pos.reasons.append(_merged_reason(g))


def _owner_acquired(ledger: _Ledger, terr: str, used: list[RightsEvent]) -> RightsPosition:
    """The owner was acquired and no grant covers the territory. An acquisition alone says nothing about
    licenses (review R1v3 N3c)."""
    owner = ledger.owner()
    a = ledger.owner_acquisitions[-1]
    used += [a, *(e for g in ledger.grants for e in ledger.grant_events(g))]
    ledger.decisive.append(a)
    ledger.deciding += [a, *(e for g in ledger.grants for e in ledger.deal_events(g))]
    if not ledger.grants:
        ledger.blockers.append(f"complete: only an acquisition is recorded ({a.when}); it says nothing about licenses "
                               f"over {terr}")
    if not owner:
        ledger.blockers.append(f"specific: who holds the {terr} rights now is not established")
    reason = (f"{a.grantee} acquired {a.grantor} (the company or its rights to this program) per source; no "
              "third-party grant recorded")
    return RightsPosition(P_OWNER_ACQUIRED, holder=owner, holders=[owner] if owner else [], reasons=[reason],
                          questions=[f"Would {ledger.current(a.grantor)} license or sell {terr} rights?"])


def rights_position(events: list[RightsEvent], *, territory: frozenset[str], as_of: date | None,
                    max_age_days: int, first_contact: str | None = None) -> RightsPosition:
    """``first_contact`` (the registry sponsor) is shown as a contact suggestion and never establishes ownership.
    It is used only to refuse: a return recorded without its grant reaches the top tiers only when it returns the
    rights to this company (review R1v3 N4d).
    ``territory`` must be region codes: an unknown code would match no grant and read every licensed
    program as unencumbered (review R1v2 B1)."""
    unknown = sorted(territory - REGIONS)
    if not territory or unknown:
        raise ValueError(f"buyer territory must be region codes from {sorted(REGIONS)}; got {sorted(territory)}")
    if not events:
        return no_evidence_position(first_contact)
    ledger = _Ledger(events, territory, as_of, max_age_days, company=first_contact)
    ledger.run()
    used: list[RightsEvent] = []
    pos = _decide(ledger, territory, used)
    _explain_leftovers(ledger, pos, used)
    pos.owner = ledger.owner() or pos.owner
    if pos.position in CLEAR_POSITIONS:
        _owner_check(ledger, pos)
        _clear_checks(ledger, pos)
        # review R1v10 UNCITED: a clear position cites every applied row, so the gate reads every quote (a grant
        # over another territory beside a return may name who holds the buyer territory)
        used += ledger.events
    else:
        _staleness(pos, ledger.decisive or used, as_of, max_age_days)
    _old_grants(ledger, pos, territory, as_of, max_age_days)
    unique = {e.event_id: e for e in used}
    pos.event_ids = list(unique)
    pos.evidence = [_cite(e) for e in unique.values()]
    pos.questions = list(dict.fromkeys(pos.questions))
    pos.reasons = list(dict.fromkeys(pos.reasons))
    return pos


__all__ = [
    "CLEAR_POSITIONS", "ENCUMBRANCE_POSITIONS", "P_AVAILABILITY", "P_CONFLICTING", "P_LICENSED", "P_NONE",
    "P_NOT_APPLIED", "P_NOT_AVAILABLE", "P_NOT_ENCUMBERED", "P_OPTION", "P_OWNER_ACQUIRED", "P_RETURNED", "P_SHARED",
    "P_UNSTATED", "SHARED_POSITIONS",
    "UNNAMED", "RightsPosition", "no_evidence_position", "own_date", "rights_position",
]
