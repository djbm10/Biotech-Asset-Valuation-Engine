"""The replay of one program's rights events, for ``rights_position`` (cycle R1).

Split from ``rights_position.py`` to keep each file under 800 lines; the rules are in that module's docstring.
``_Ledger`` applies outcomes (terminations, returns, lapses, exercises) and acquisitions to grants in date order and
records what each position rests on. Internal to the rights package: ``rights_position`` is the public interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from bve.dealscreen.rights import (
    ACQUISITION,
    AVAILABILITY_STATED,
    CO_DEVELOPMENT,
    CO_PROMOTION_OPTION,
    LICENSE,
    OPTION,
    OPTION_EXERCISED,
    OPTION_LAPSED,
    RIGHTS_RETURNED,
    TERMINATION,
    RightsEvent,
    period_end,
)
from bve.dealscreen.rights_territory import party_key

_GRANT_TYPES = frozenset({LICENSE, OPTION, CO_DEVELOPMENT, CO_PROMOTION_OPTION})
_ENDINGS = frozenset({TERMINATION, RIGHTS_RETURNED})
#: Records that can clear a grant or change the holder.
_CLEARS = frozenset({TERMINATION, RIGHTS_RETURNED, OPTION_LAPSED, ACQUISITION})
_OPTION_OUTCOMES = frozenset({OPTION_EXERCISED, OPTION_LAPSED})
_OUTCOMES = _ENDINGS | _OPTION_OUTCOMES
_OPTIONS = frozenset({OPTION, CO_PROMOTION_OPTION})
#: Shown for a grant whose licensee (or co-development partner) is not named. Never matched to a party.
UNNAMED = "a licensee not named"


@dataclass
class _Grant:
    event: RightsEvent
    kind: str  # LICENSE / OPTION / CO_DEVELOPMENT
    shared: bool
    regions: set[str] | None
    holder: str  # "" when the record names no licensee (or no second partner)
    grantor: str | None
    active: bool = True
    cleared_by: list[RightsEvent] = field(default_factory=list)
    exercised: RightsEvent | None = None
    lapsed: RightsEvent | None = None
    disputed: str | None = None
    #: Licensor and licensee became one company through these acquisitions; the owner holds the rights.
    merged_by: list[RightsEvent] = field(default_factory=list)
    #: Licensor and licensee are one company as written (names differ only by a corporate suffix).
    intra_group: bool = False
    #: Exercises for part of the option's territory; the option stays for the rest.
    partly_exercised: list[RightsEvent] = field(default_factory=list)
    #: The option a partial exercise split this license from. Option outcomes never apply to it.
    parent: _Grant | None = None
    #: One partner ended its part of a co-development; the other may hold all rights.
    partner_exit: RightsEvent | None = None


def _article(words: str) -> str:
    return "an" if words[:1].casefold() in {"a", "e", "i", "o", "u"} else "a"


def _what(e: RightsEvent) -> str:
    """'a rights return (2024) naming Example Pharma', 'an option lapse (2023-11)'."""
    party = e.grantee or e.grantor
    return f"{_article(e.words)} {e.words} ({e.when})" + (f" naming {party}" if party else "")


def _may_follow(grant: RightsEvent, outcome: RightsEvent) -> bool:
    """The grant could have been made after the outcome: both are dated (a grant dated only by its report
    counts as dated by it) and the grant's latest possible date is after the outcome's earliest."""
    g, o = grant.window, outcome.window
    return g is not None and o is not None and g[1] > o[0]


def _definitely_after(later: RightsEvent, earlier: RightsEvent) -> bool:
    a, b = later.window, earlier.window
    return a is not None and b is not None and a[0] > b[1]


def _unreadable_territory(e: RightsEvent) -> bool:
    """A territory was written but cannot be read (as opposed to no territory written)."""
    return e.territory is None and bool((e.territory_as_written or "").strip())


def _ever_covers(g: _Grant, territory: frozenset[str]) -> bool:
    """The grant as recorded (before any outcome) covers, or may cover, the territory."""
    return g.event.territory is None or bool(set(g.event.territory) & territory)


def own_date(e: RightsEvent) -> date | None:
    """When the record says the event happened: the start of its event date's period, else of the date of the
    report that records it. A later source date never moves a dated event (review R1v3 N7a)."""
    w = e.window
    return w[0] if w else None


_LEGAL_FORMS = frozenset({"inc", "incorporated", "ltd", "limited", "co", "corp", "corporation", "llc", "plc", "gmbh",
                          "ag", "sa", "nv", "bv", "kk", "pte", "pty", "spa", "kgaa", "the"})


def _one_entity(a: str | None, b: str | None) -> bool:
    """Two names for one legal entity: the same words once legal forms and punctuation are removed. Stricter than
    ``same_company``: "Acme Holdings", "Acme Bio US" and "Acme International" are other entities than "Acme"
    (review R1v10 OWNER-KEY)."""
    def words(name: str | None) -> list[str]:
        low = re.sub(r"(?<![a-z])u\.\s?s\.\s?a\.?(?![a-z])", " usa ", (name or "").casefold())
        low = re.sub(r"(?<![a-z])u\.\s?s\.?(?![a-z])", " us ", low)
        return [w for w in re.sub(r"[^\w&]+", " ", low.replace("-", " ")).split() if w not in _LEGAL_FORMS]

    wa, wb = words(a), words(b)
    return bool(wa) and wa == wb


class _Ledger:
    """Replays one program's rights events. See the module docstring for the rules."""

    def __init__(self, events: list[RightsEvent], territory: frozenset[str], as_of: date | None = None,
                 max_age_days: int = 730, company: str | None = None) -> None:
        self.territory = territory
        #: The program's company per the landscape (the registry sponsor). Never evidence of ownership; used only
        #: to refuse the top tiers when a return-only record names a different recipient (review R1v3 N4d).
        self.company = company
        self.terr = "/".join(sorted(territory))
        self.as_of, self.max_age = as_of, max_age_days
        #: Records dated after the as-of date were not known then; they are not applied (review R1v3 N10).
        self.after_as_of = [e for e in events if as_of and e.window and e.window[0] > as_of]
        #: An ending or acquisition dated only to a year or month that contains the as-of date may come after it,
        #: so it is not applied either, and it blocks (review R1v7 DATE).
        #: An availability statement so dated may also have been made after it (review R1v8 DATE-AV).
        self.straddling = [e for e in events if as_of and e.event_type in _CLEARS | {AVAILABILITY_STATED}
                           and e.window and e.window[0] <= as_of < e.window[1]]
        #: A grant dated after the as-of date that reaches the buyer territory (or names no readable territory) may
        #: have been agreed by then: unless its source is dated after the as-of date, it is not applied as a grant,
        #: and it blocks (review R1v8 FUT; R1v9 FUT2: no source date, or one dated only to a period containing the
        #: as-of date, is not evidence that it came later; in live use the row is already in today's export).
        #: An option exercise is a grant too (review R1v10 FUT3).
        self.announced = [e for e in self.after_as_of if as_of and e.event_type in _GRANT_TYPES | {OPTION_EXERCISED}
                          and not (e.source_date and e.source_date > as_of)
                          and (e.territory is None or set(e.territory) & territory)]
        later = {e.event_id for e in self.after_as_of + self.straddling}
        self.events = [e for e in events if e.event_id not in later]
        #: Why a clear position may not reach the top tiers ("check: detail"), see the module docstring.
        self.blockers: list[str] = [
            f"current: the {e.words} ({e.when}) is dated only to a period that contains the as-of date {as_of}, so "
            "it may come after it; it is not applied" for e in self.straddling]
        self.blockers += [
            f"current: the {e.words} ({e.when}) takes effect after the as-of date {as_of}, and "
            + (f"its source ({e.source_date_text}) does not show it was reported after then"
               if e.source_date else "it has no source date to show it was reported after then")
            + ", so it may have been agreed by the as-of date; it is not applied as a grant before it takes effect"
            for e in self.announced]
        #: The records a clear position rests on; the current check is judged on their own dates.
        self.deciding: list[RightsEvent] = []
        self.grants: list[_Grant] = []
        self.availability: list[RightsEvent] = []
        self.unmatched: list[RightsEvent] = []
        self.ambiguous: list[tuple[RightsEvent, list[_Grant]]] = []
        self.unordered: list[tuple[RightsEvent, _Grant]] = []
        self.earlier: list[RightsEvent] = []
        self.misdated: list[tuple[RightsEvent, _Grant]] = []
        self.repeated: list[tuple[RightsEvent, _Grant]] = []
        self.kept: list[tuple[RightsEvent, _Grant]] = []
        self.notes: list[str] = []
        self.questions: list[str] = []
        #: The events that decide the position; staleness is judged on these.
        self.decisive: list[RightsEvent] = []
        #: Acquisitions not applied (one party, unreadable or other territory); cited with their note.
        self.unapplied: list[RightsEvent] = []
        self.succession, self.owner_acquisitions = self._acquisitions()

    # -- names -----------------------------------------------------------------------------------
    def _acquisitions(self) -> tuple[dict[str, tuple[str, RightsEvent]], list[RightsEvent]]:
        holders = {party_key(e.grantee) for e in self.events if e.event_type in _GRANT_TYPES and e.grantee}
        holders |= {party_key(e.grantor) for e in self.events if e.event_type == CO_DEVELOPMENT and e.grantor}
        # The names of grant parties as written: an acquired party must be one legal entity with one of them
        # (``_one_entity``), not merely share a key ("Nerida Bio Holdings" is not "Nerida Bio"; review R1v11
        # OWNER-KEY2).
        named = [n for e in self.events if e.event_type in _GRANT_TYPES for n in (e.grantee, e.grantor) if n]
        # a party's acquirer is a party too ("Gamma acquired Alpha; Origin Bio acquired Gamma")
        while grown := [e.grantee for e in self.events if e.event_type == ACQUISITION and e.grantee and e.grantor
                        and any(_one_entity(e.grantor, n) for n in named)
                        and not any(_one_entity(e.grantee, n) for n in named)]:
            named += grown
        acquirers: dict[str, list[RightsEvent]] = {}
        for e in self.events:
            if e.event_type == ACQUISITION and e.grantee and e.grantor:
                acquirers.setdefault(party_key(e.grantor), []).append(e)
        succession: dict[str, tuple[str, RightsEvent]] = {}
        owners: list[RightsEvent] = []
        for e in self.events:
            if e.event_type != ACQUISITION:
                continue
            if not (e.grantee and e.grantor):
                self.notes.append(f"acquisition record {e.deal_id} names only one party; not applied")
                self.blockers.append(f"complete: an acquisition record ({e.when}) names only one party")
                self.unapplied.append(e)
                continue
            if _unreadable_territory(e):  # review R1v3 N3: an acquisition counts only where it applies
                self.notes.append(f"{_what(e)} names a territory that cannot be read ({e.territory_as_written}); "
                                  "not applied")
                self.questions.append(f"Does the acquisition ({e.when}, {e.territory_as_written}) include "
                                      f"{self.terr}?")
                self.blockers.append(f"specific: an acquisition ({e.when}) names a territory that cannot be read")
                self.unapplied.append(e)
                continue
            covered = set(e.territory) & self.territory if e.territory is not None else set(self.territory)
            if not covered:
                self.notes.append(f"{_what(e)} covers {e.territory_as_written} only; not applied for {self.terr}")
                self.unapplied.append(e)
                continue
            if covered != self.territory:
                self.notes.append(f"{_what(e)} covers only part of {self.terr} ({e.territory_as_written}); "
                                  "not applied")
                self.blockers.append(f"specific: an acquisition ({e.when}) covers only part of {self.terr}")
                self.unapplied.append(e)
                continue
            if own_date(e) is None:  # review R1v5 O1: an undated acquisition cannot say who the company is now
                self.notes.append(f"{_what(e)} has no date; not applied")
                self.blockers.append(f"current: an acquisition of {e.grantor} by {e.grantee} has no date, so it cannot "
                                     "show who holds the rights now")
                self.questions.append(f"When did {e.grantee} acquire {e.grantor}? Cite a dated source.")
                self.unapplied.append(e)
                continue
            rivals = [x for x in acquirers.get(party_key(e.grantor), []) if x is not e
                      and _one_entity(x.grantor, e.grantor) and not _one_entity(x.grantee, e.grantee)]
            if rivals:
                # review R1v11 ACQ-TWO: two acquirers of one party; the later record does not silently win
                others = "; ".join(f"{x.grantee} ({x.when})" for x in rivals)
                self.notes.append(f"{_what(e)}: {e.grantor} is also recorded as acquired by {others}; not applied")
                self.blockers.append(f"uncontested: {e.grantor} is recorded as acquired by {e.grantee} ({e.when}) and "
                                     f"by {others}, so who owns it is not established")
                self.questions.append(f"Who acquired {e.grantor}: {e.grantee} or {others}?")
                self.unapplied.append(e)
                continue
            if not any(_one_entity(e.grantor, n) for n in named) and not (
                    self.company and _one_entity(e.grantor, self.company)):
                # review R1v9 ACQ-X, R1v10 OWNER-KEY: the acquired party is in no grant and is not the program's
                # company itself (an affiliate, holding company or regional unit is another entity), so the record
                # does not show it is about this program's owner; it may hold rights itself. The company buying
                # someone else says nothing about who holds this program.
                self.notes.append(f"{_what(e)}: {e.grantor} is neither the program's company nor a party to a "
                                  "recorded grant; not applied")
                self.blockers.append(f"specific: an acquisition of {e.grantor} by {e.grantee} ({e.when}) names "
                                     "neither the program's company nor a party to a recorded grant, so it may "
                                     "concern rights the records do not show")
                self.questions.append(f"What rights to this program did {e.grantor} hold when {e.grantee} acquired it?")
                self.unapplied.append(e)
                continue
            succession[party_key(e.grantor)] = (e.grantee, e)
            if party_key(e.grantor) not in holders:
                owners.append(e)
        return succession, owners

    def display(self, name: str | None) -> str:
        """A party for prose: its current name after recorded acquisitions, or ``UNNAMED``."""
        return self.current(name) or UNNAMED

    def _walk(self, name: str | None) -> tuple[str, list[RightsEvent]]:
        """The current successor of ``name`` and the acquisition records that lead to it."""
        seen: set[str] = set()
        chain: list[RightsEvent] = []
        while name and party_key(name) in self.succession and party_key(name) not in seen:
            seen.add(party_key(name))
            name, event = self.succession[party_key(name)]
            chain.append(event)
        return name or "", chain

    def current(self, name: str | None) -> str:
        return self._walk(name)[0]

    def chain(self, name: str | None) -> list[RightsEvent]:
        return self._walk(name)[1]

    def same(self, a: str | None, b: str | None) -> bool:
        ka, kb = party_key(self.current(a)), party_key(self.current(b))
        return bool(ka) and ka == kb

    def grant_events(self, g: _Grant) -> list[RightsEvent]:
        """A grant and everything that shaped it: acquisitions of its parties, its exercise and outcomes."""
        out = [g.event, *self.chain(g.holder), *self.chain(g.grantor), *g.cleared_by, *g.merged_by,
               *g.partly_exercised]
        return out + [e for e in (g.exercised, g.partner_exit) if e]

    @staticmethod
    def deal_events(g: _Grant) -> list[RightsEvent]:
        """A grant's own records (no acquisitions): what its age is judged on (review R1v3 N7e)."""
        return [g.event, *g.cleared_by, *g.partly_exercised] + [e for e in (g.exercised, g.partner_exit) if e]

    # -- replay ----------------------------------------------------------------------------------
    def run(self) -> None:
        def order(e: RightsEvent) -> tuple[date, int]:
            w = e.window
            if e.event_type in _GRANT_TYPES:  # a report date bounds a grant from above only
                return (w[0] if (w and e.event_date) else date.min, 0)
            return (w[1] if w else date.max, 1)

        for e in sorted(self.events, key=order):
            if e.event_type in _GRANT_TYPES:
                self._grant(e)
            elif e.event_type == AVAILABILITY_STATED:
                self.availability.append(e)
            elif e.event_type in _OUTCOMES:
                self._outcome(e)
        self._sort_unmatched()

    def _grant(self, e: RightsEvent) -> None:
        kind = OPTION if e.event_type in _OPTIONS else e.event_type
        shared = e.event_type == CO_DEVELOPMENT or (kind == LICENSE and e.exclusivity == "NON_EXCLUSIVE")
        # A record naming only the licensor is a grant to a licensee not named, never to the licensor (R1v3 N1).
        g = _Grant(e, kind, shared, set(e.territory) if e.territory is not None else None,
                   holder=e.grantee or "", grantor=e.grantor)
        # A source dated "2025" may be from after an as-of date in 2025: judge on the end of its period (R1v7 DATE).
        reported_later = bool(self.as_of and e.source_date
                              and period_end(e.source_date, e.source_date_precision) > self.as_of)
        if e.status in {"TERMINATED", "EXPIRED"} and reported_later:  # review R1v5 E2: not known on the as-of date
            self.notes.append(f"{e.words} ({e.when}): its status '{e.status.lower()}' is reported in a source dated "
                              f"{e.source_date_text}, after the as-of date {self.as_of}; not applied")
        elif e.status in {"TERMINATED", "EXPIRED"}:
            g.active = False
            g.cleared_by.append(e)
            if self.as_of and e.source_date is None:  # review R1v6 S2: the status may describe a later export
                self.blockers.append(f"current: the {e.words} ({e.when}) is ended only by its status "
                                     f"'{e.status.lower()}', which no source date places before the as-of date "
                                     f"{self.as_of}")
            if kind == OPTION and e.status == "EXPIRED":  # an expired option lapsed (review R1v3 H5)
                g.lapsed = e
        self.grants.append(g)

    def _match(self, e: RightsEvent) -> list[_Grant]:
        # Option outcomes apply to options, never to a license split from one by a partial exercise (R1v3 P1).
        pool = [g for g in self.grants if g.event.event_type in _OPTIONS and g.parent is None] \
            if e.event_type in _OPTION_OUTCOMES else list(self.grants)
        if e.related_deal_id:
            return [g for g in pool if g.event.deal_id == e.related_deal_id]
        if e.grantee:
            return [g for g in pool if self.same(g.holder, e.grantee) or (g.shared and self.same(g.grantor, e.grantee))]
        if e.grantor:
            return [g for g in pool if self.same(g.grantor, e.grantor)]
        return []

    def _outcome(self, e: RightsEvent) -> None:
        matches = self._match(e)
        if e.event_type in _ENDINGS and e.event_date is not None:
            candidates = [g for g in matches if g.active]
        else:  # undated or report-dated endings, and option outcomes, may describe a grant that already ended
            candidates = matches
        if not matches:
            self.unmatched.append(e)
        elif len(candidates) > 1 and e.event_type in _ENDINGS and len({id(g.parent or g) for g in candidates}) == 1:
            for g in candidates:  # an option and the license split from it are one deal (review R1v3 P1)
                self._settle(g, e)
        elif len(candidates) > 1:
            self.ambiguous.append((e, candidates))
        elif not candidates and (flagged := self._dates_flag(matches, e)) is not None:
            flagged.cleared_by = [e]  # the dated record dates the end the row's status reported (review R1v4 G5b)
        elif not candidates:  # a dated ending whose every grant had already ended: a repeated record
            self.repeated.append((e, matches[-1]))
        else:
            self._settle(candidates[0], e)

    def _dates_flag(self, matches: list[_Grant], e: RightsEvent) -> _Grant | None:
        """The one matched grant ended only by its own row's status (no date for the end itself) that a dated ending
        over its whole territory, which cannot precede the grant, may date."""
        flagged = [g for g in matches if g.cleared_by == [g.event] and g.lapsed is None]
        if len(flagged) != 1 or e.event_type not in _ENDINGS:
            return None
        g = flagged[0]
        whole = e.territory is None or (g.regions is not None and g.regions <= set(e.territory))
        linked = bool(e.related_deal_id) and g.event.deal_id == e.related_deal_id
        return g if whole and (linked or not _may_follow(g.event, e)) else None

    def _settle(self, g: _Grant, e: RightsEvent) -> None:
        # One ordering rule for licenses and options: only a deal-id link orders an outcome after its grant
        # by definition (review R1v3 R1).
        follows = bool(e.related_deal_id) and g.event.deal_id == e.related_deal_id
        if e.event_type in _ENDINGS and not g.active:
            self.repeated.append((e, g))
        elif not follows and _may_follow(g.event, e):
            self.unordered.append((e, g))
        else:
            self._apply(g, e)

    def _sort_unmatched(self) -> None:
        """An outcome that matched nothing when it was replayed is dated before any grant it names."""
        unmatched, self.unmatched = self.unmatched, []
        for e in unmatched:
            later = self._match(e)
            if not later:
                self.unmatched.append(e)
            elif e.related_deal_id:
                self.misdated.append((e, later[0]))
            else:
                self.earlier.append(e)

    def _apply(self, g: _Grant, e: RightsEvent) -> None:
        if _unreadable_territory(e):
            self.kept.append((e, g))
            return
        if e.event_type in _ENDINGS and g.event.event_type == CO_DEVELOPMENT and self._one_partner(g, e):
            g.partner_exit = e  # the other partner may hold all rights now (review R1v3 N8)
            return
        scope = set(e.territory) if e.territory is not None else None  # None: the whole grant
        if scope is not None and g.regions is None:
            self.notes.append(f"{_what(e)} for {e.territory_as_written} was recorded, but the grant to "
                              f"{self.display(g.holder)} has no readable territory; it is kept")
            self.questions.append(f"Which territories does the grant to {self.display(g.holder)} cover, and did "
                                  f"the {e.words} ({e.when}) end it there?")
            return
        whole = scope is None or (g.regions is not None and g.regions <= scope)
        if e.event_type == OPTION_EXERCISED:
            self._exercise(g, e, whole, scope)
        elif e.event_type == OPTION_LAPSED and g.exercised is not None:
            g.disputed = f"the option to {self.display(g.holder)} is recorded as both exercised and lapsed ({e.when})"
        elif whole:
            g.active = False
            g.cleared_by.append(e)
            if e.event_type == OPTION_LAPSED:
                g.lapsed = e
        else:  # a termination, return or lapse for part of the grant's territory
            assert g.regions is not None and scope is not None
            g.regions -= scope
            g.cleared_by.append(e)
            g.active = bool(g.regions)

    def _exercise(self, g: _Grant, e: RightsEvent, whole: bool, scope: set[str] | None) -> None:
        if g.lapsed is not None or g.exercised is not None or not g.active:
            g.disputed = f"the option to {self.display(g.holder)} is recorded as both exercised ({e.when}) and lapsed"
            g.active = True
            return
        shared = g.shared or g.event.event_type == CO_PROMOTION_OPTION
        if whole:
            g.exercised, g.kind, g.shared = e, LICENSE, shared
            return
        part = (g.regions or set()) & (scope or set())
        if not part:
            self.notes.append(f"{_what(e)} for {e.territory_as_written} is outside the option's territory; "
                              "the option is kept")
            return
        g.regions = (g.regions or set()) - part  # the option stays for the rest of its territory
        g.partly_exercised.append(e)
        self.grants.append(_Grant(g.event, LICENSE, shared, part, holder=g.holder, grantor=g.grantor, exercised=e,
                                  parent=g))

    def _one_partner(self, g: _Grant, e: RightsEvent) -> bool:
        """The ending names one of a co-development's two named partners and not the other."""
        partners = [p for p in (g.holder, g.grantor) if p]
        named = [p for p in (e.grantee, e.grantor) if p]
        hit = {i for i, p in enumerate(partners) if any(self.same(p, n) for n in named)}
        return len(partners) == 2 and len(hit) == 1

    def merge_internal(self) -> None:
        """A grant whose licensor and licensee are now one company has ended: through recorded acquisitions
        (``merged_by``), or as written, the names differing only by a corporate suffix (``intra_group``)."""
        for g in self.grants:
            if g.active and g.grantor and g.holder and self.same(g.holder, g.grantor):
                g.active = False
                g.merged_by = [*self.chain(g.holder), *self.chain(g.grantor)]
                g.intra_group = not g.merged_by

    # -- owner -----------------------------------------------------------------------------------
    def owner(self) -> str | None:
        """The licensor at the root of the recorded grants (after succession), when there is exactly one.
        Co-development partners are holders, not owners; an owner acquisition names the acquirer."""
        licensed = [g for g in self.grants if g.event.event_type != CO_DEVELOPMENT]
        holder_keys = {party_key(self.current(g.holder)) for g in licensed if not (g.merged_by or g.intra_group)}
        roots = {party_key(self.current(g.grantor)): self.current(g.grantor) for g in licensed
                 if g.grantor and party_key(self.current(g.grantor)) not in holder_keys}
        if not roots and self.owner_acquisitions:
            roots = {party_key(self.current(a.grantor)): self.current(a.grantor) for a in self.owner_acquisitions}
        return next(iter(roots.values())) if len(roots) == 1 else None
