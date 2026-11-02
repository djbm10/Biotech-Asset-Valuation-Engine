"""The top-tier gate: what a clear rights position must survive beyond the rights file (cycle R1, revision 6).

A clear position (rights returned, no third-party grant over the buyer territory, owner acquired, availability
stated) reaches the two top transaction tiers only if ``rights_position`` finds it complete, specific and current,
and this gate finds nothing in the rest of the program's record that contests it or that DealScreen cannot read. It
runs on the rights-file path and the landscape-field path alike. Since revision 6 (review R1v5) the default is
inverted: a rights-bearing text beside a clear position passes only if it is one of the plain forms of
``rights_allow``; everything else blocks, quoted and cited.

- Statements: every landscape and analyst U.S.-rights statement for the program. One whose reading says rights are
  not available, licensed or optioned contests the position (CONFLICTING) when the buyer territory includes the
  U.S.; any other that is not a plain form blocks. A statement dated after the as-of date is not applied, and is
  listed.
- Other rights text: every Partnerships and Geographic Notes value (landscape or analyst) that says something about
  rights must be a plain form too, or it blocks. A Partnerships value that only names organisations is not read.
- Names: a note beside the program's company name, a rights row's grantor or grantee, or a named holder, in
  parentheses or brackets, blocks: it is content and may name a third party. A one-word place inside a legal name
  ("Acme Bio (Basel) Co., Ltd.") is not a note. A holder that is neither the program's company nor a party the
  rights evidence names contests the position (U.S. buyer) or blocks (other territories).
- Rows: rights rows that were not applied and could belong to the program keep it out of the top tiers
  (``row_guards``): a rejected row whose program id matches no program may concern any program; an unattached row
  may concern a program when its id is close to the program's id (``ids_close``), or, when its id is close to no
  program, when it names the program's company as a party.

The gate only refuses. It never moves a position into a top tier, never decides a gate and never reads the registry
sponsor as an owner. A position that is not clear gets only the older check: a statement of availability beside a
recorded grant is a conflict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from bve.dealscreen.rights import (
    AVAILABILITY_STATED,
    RightsEvent,
)
from bve.dealscreen.rights_allow import is_rights_text, plain_form
from bve.dealscreen.rights_position import (
    CLEAR_POSITIONS,
    ENCUMBRANCE_POSITIONS,
    P_CONFLICTING,
    SHARED_POSITIONS,
    RightsPosition,
)
from bve.dealscreen.rights_quote import quote_problem
from bve.dealscreen.rights_reader import (
    AVAILABLE,
    AVAILABLE_CONFIRMED,
    CONTESTS,
    RIGHTS_STATUS_WORDS,
    UNKNOWN,
)
from bve.dealscreen.rights_reader import rights_reading as _rights_reading
from bve.dealscreen.rights_territory import (
    content_note,
    regions_named,
    same_company,
    split_note,
)
from bve.dealscreen.rights_words import FIELD_STATEMENT

_OFFERS = frozenset({AVAILABLE, AVAILABLE_CONFIRMED})
_PLACEHOLDER = re.compile(r"^\s*(?:|-+|\?+|n/?a|na|none|nil|unknown|undisclosed|not disclosed|not reported|"
                          r"not stated|tbd|tbc)\s*$", re.IGNORECASE)


def field_source(basis: list[dict[str, Any]]) -> str:
    """Who made a U.S.-rights statement or named a holder, for prose."""
    origins = {c.get("origin") for c in basis}
    if "ANALYST_ASSERTED" in origins:
        return "an analyst assertion"
    if "AGENT_PROPOSED" in origins:
        return "an analyst-confirmed finding"
    return "the landscape"


def field_evidence(basis: list[dict[str, Any]] | None, words: str = "U.S.-rights statement") -> list[dict[str, Any]]:
    """The claims behind a landscape or analyst statement, cited beside rights rows."""
    return [{"event_id": c.get("claim_id"), "type": FIELD_STATEMENT, "type_words": words,
             "origin": c.get("origin"), "value": c.get("value"), "grantee": None, "grantor": None,
             "territory": "U.S. (the field's market)", "date": c.get("source_date"), "source_date": c.get("source_date"),
             "source": c.get("source") or "no URL", "quote": c.get("quote") or c.get("value"), "row": c.get("row"),
             "column": c.get("column"), "source_system": c.get("source_system")} for c in basis or []]


def _with_reading(claim: dict[str, Any]) -> dict[str, Any]:
    reading = _rights_reading(str(claim.get("value") or ""))
    return {"reads": reading.status, "understood": reading.understood, "parties": list(reading.parties)} | claim


def _statements(commercial: Any) -> list[dict[str, Any]]:
    """Every U.S.-rights statement with its reading. A caller built before revision 5 carries only the status
    basis, or only the status."""
    listed = getattr(commercial, "us_rights_all", None)
    if listed:
        return [_with_reading(c) if "reads" not in c else c for c in listed]
    basis = list(getattr(commercial, "us_rights_basis", None) or [])
    if basis:
        return [_with_reading(c) for c in basis]
    status = commercial.us_rights_status
    return [] if status == UNKNOWN else [{"value": RIGHTS_STATUS_WORDS.get(status, status), "reads": status,
                                          "understood": True, "parties": []}]


def _holders(commercial: Any) -> list[dict[str, Any]]:
    listed = getattr(commercial, "us_rights_holder_all", None)
    if listed:
        return list(listed)
    basis = list(getattr(commercial, "us_rights_holder_basis", None) or [])
    names = commercial.us_rights_holder_conflict or ([commercial.us_rights_holder] if commercial.us_rights_holder
                                                     else [])
    return [{**(basis[0] if basis else {}), "value": n} for n in names]


def _later(claim: dict[str, Any], as_of: date | None) -> bool:
    raw = claim.get("source_date")
    if as_of is None or not raw:
        return False
    return date.fromisoformat(str(raw)) > as_of


def _quoted(claim: dict[str, Any]) -> str:
    return " ".join(str(claim.get("value") or "").split())


class _Findings:
    """What the gate found: contests make the position CONFLICTING; blocks keep a clear position out of the top
    tiers. Each carries its reason, its question and the claim it cites."""

    def __init__(self) -> None:
        self.contests: list[tuple[str, str, list[dict[str, Any]]]] = []
        self.blocks: list[tuple[str, str, list[dict[str, Any]]]] = []
        self.holders: list[str] = []
        #: Statements in a plain form, shown and cited beside the position (review R1v5 K8).
        self.consistent: list[tuple[str, list[dict[str, Any]]]] = []


def _not_plain(source: str, value: str, field_words: str, claim: dict[str, Any]) -> tuple[str, str]:
    if not claim.get("understood", True):
        why = "which DealScreen cannot read as a rights statement"
    else:
        why = ("which is not one of the plain forms DealScreen accepts beside a clear position (it may carry a date, a "
               "condition, another party or a place)")
    return ((f"uncontested: {source} reads '{value}' ({field_words}), {why}; it may name a third-party holder, a "
             "condition or another place"),
            f"What does {source}'s {field_words} '{value}' say about rights in the buyer territory, and who holds them?")


_KEPT = "rights kept by the company"


def accepted_form(value: str, company: str | None, as_of: date | None, territory: frozenset[str],
              understood: bool) -> str | None:
    """The plain form of a text the gate accepts beside a clear position, else None. A text the reader cannot read
    passes only as the company keeping its rights (review R1v6 §11.3): a plain form never widens the reader."""
    form = plain_form(value, company, as_of, territory)
    if form and not understood and set(form.split("; ")) - {_KEPT}:
        return None
    return form


def _read_statements(found: _Findings, claims: list[dict[str, Any]], company: str | None,
                     rests_on: dict[str, Any] | None, territory: frozenset[str], as_of: date | None) -> None:
    """``rests_on``: on the field path, the statement the position was read from; None on the rights-file path.
    Every statement must contest the position (only for a buyer territory with the U.S.), or have a plain form
    (``rights_allow``) in the buyer's terms; anything else blocks (review R1v5 §13, R1v6 PF1-PF4)."""
    covers_us = "US" in territory
    if rests_on is None:
        basis, other = "the rights evidence records no third-party grant over the buyer territory", "the rights evidence"
    else:
        other = f"{field_source([rests_on])}'s statement ('{_quoted(rests_on)}')"
        basis = f"the position rests on {other}"
    for claim in claims:
        source, value, cite = field_source([claim]), _quoted(claim), field_evidence([claim])
        reads = claim.get("reads", UNKNOWN)
        form = accepted_form(value, company, as_of, territory, bool(claim.get("understood", True)))
        if reads in CONTESTS and covers_us:
            found.contests.append((f"{source} reads '{value}' ({RIGHTS_STATUS_WORDS.get(reads, reads)}); {basis}",
                                   (f"Which is current: {source}'s U.S.-rights statement ('{value}') or {other}? "
                                    "Reject the one that is wrong."), cite))
        elif reads not in CONTESTS and form:
            if not _PLACEHOLDER.match(value) and (rests_on is None or claim.get("claim_id") != rests_on.get("claim_id")):
                found.consistent.append((f"{source} also states '{value}' ({form})", cite))
        else:
            blocker, question = _not_plain(source, value, "U.S.-rights statement", claim)
            found.blocks.append((blocker, question, cite))


def _read_other(found: _Findings, claims: list[dict[str, Any]], company: str | None, as_of: date | None,
                territory: frozenset[str]) -> None:
    """Partnerships and Geographic Notes values (review R1v5 P). A Partnerships value that only names organisations
    is not rights evidence. A value the reader reads as a grant, option or "not available" over the U.S. contests
    the position (review R1v6 LBL); any other value must have a plain form, or it blocks."""
    for claim in claims:
        value = _quoted(claim)
        if _PLACEHOLDER.match(value):
            continue
        partnerships = claim.get("field") == "partnerships"
        if partnerships and not is_rights_text(value):
            continue
        words = "Partnerships value" if partnerships else "geographic rights note"
        cite = field_evidence([claim], words)
        source = field_source([claim])
        reading = _rights_reading(value)
        if reading.status in CONTESTS and reading.understood and "US" in territory:
            found.contests.append(((f"{source} {words} reads '{value}' "
                                   f"({RIGHTS_STATUS_WORDS.get(reading.status, reading.status)})"),
                                   (f"Which is current: {source}'s {words} ('{value}') or the rights evidence? Reject "
                                   "the one that is wrong."), cite))
            continue
        form = accepted_form(value, company, as_of, territory, reading.understood)
        if form:
            found.consistent.append((f"{source} {words} '{value}' ({form})", cite))
            continue
        blocker, question = _not_plain(source, value, words, {} if reading.understood else {"understood": False})
        found.blocks.append((blocker, question, cite))


#: A speaker before a colon ("Acme Bio: U.S. rights available") is not part of the statement.
_SPEAKER = re.compile(r"^\s*[A-Z][^:;()\[\]]{0,60}:\s+")


#: Words in a quote that reach beyond the places a row names: an option or a wider territory (review R1v7 QW,
#: R1v8 QW2). Ordinary press words ("a treatment option", "International" in a name, "global development", "in a
#: row") are not on it (review R1v8 usefulness); "ROW" counts only in capitals.
_WIDER = re.compile(r"\b(?:worldwide|world-wide|rest of (?:the )?world|all (?:other )?territories|all other (?:markets|"
                    r"countries|regions|territories)|remaining (?:territories|markets|countries|regions|rights)|ex-|"
                    r"ex\s+(?-i:(?=[A-Z]))|non-(?-i:(?=[A-Z]))|outside|excluding|except|beyond|further territories|"
                    r"right of first|first (?:negotiation|refusal|look)|right to negotiate|ROF[NRO]|buy-?out|opt-?in|"
                    r"north american?|americas?|elsewhere)\b|\bglobal(?:ly)?\s+(?:rights|licen[cs]es?|"
                    r"territor\w*|commerciali[sz]ation)\b|\binternational\s+(?:rights|territor\w*|markets?)\b|"
                    r"\boptions?\s+(?:to|on|for|over)\b(?=[^;.]{0,60}?\b(?:rights?|licen[cs]\w*|territor\w*|acqui\w*|"
                    r"negotiat\w*|commerciali\w*|programs?|assets?|markets?|countr\w*|regions?)\b)|(?-i:\bROW\b)",
                    re.IGNORECASE)
_QUOTE_FORMS = frozenset({_KEPT, "no grant stated"})


def _speaker_stripped(quote: str, e: dict[str, Any], company: str | None) -> str:
    """A quote without a leading "Name:" when the name is the row's own grantor or the program's company. Any other
    prefix stays, so a condition ("Subject to X consent: ...") or a third party speaking is read (review R1v7 SPK)."""
    found = _SPEAKER.match(quote)
    if not found:
        return quote
    speaker = found.group(0).strip().rstrip(":").strip()
    own = [x for x in (company, e.get("grantor")) if x]
    return quote[found.end():] if any(same_company(speaker, str(x)) for x in own) else quote


def _quote_problem(quote: str, e: dict[str, Any], company: str | None, as_of: date | None,
                   territory: frozenset[str], names: list[str] | None = None,
                   vocabulary: frozenset[str] = frozenset()) -> str | None:
    """Why a cited row's quote blocks, or None. An availability statement's quote must be a plain form in the
    buyer's terms. Any other row's quote is read fail closed, whatever the row's own territory: each clause must be
    a plain form, a restatement of its own row, or say nothing about rights (``rights_quote``, review R1v9)."""
    text = _speaker_stripped(quote, e, company)
    if e.get("type") == AVAILABILITY_STATED:
        if accepted_form(text, company, as_of, territory, _rights_reading(text).understood):
            return None
        return ("is not one of the plain forms DealScreen accepts beside a clear position (it may carry a date, a "
                "condition, another party or a place)")
    return quote_problem(text, e, company, as_of, territory, names, vocabulary)


def _read_quotes(found: _Findings, position: RightsPosition, company: str | None, as_of: date | None,
                 territory: frozenset[str], names: list[str] | None = None,
                 vocabulary: frozenset[str] = frozenset()) -> None:
    """The quote on each cited rights row (review R1v6 QUOTE, R1v7 SPK/QW/QT). A quote that says nothing about rights
    or places adds nothing; otherwise see ``_quote_problem``."""
    for e in position.evidence:
        quote = str(e.get("quote") or "").strip()
        if e.get("type") == FIELD_STATEMENT or not quote:
            continue
        if e.get("type") == AVAILABILITY_STATED and not (is_rights_text(quote) or regions_named(quote)
                                                        or _WIDER.search(quote)):
            continue  # an availability quote that says nothing about rights adds nothing to the row
        # every other cited quote is read, whatever it says (review R1v8 COVER, QW2)
        why = _quote_problem(quote, e, company, as_of, territory, names, vocabulary)
        if why is None:
            continue
        row = f"rights row {e.get('row')} ({e.get('type_words') or e.get('type')})"
        found.blocks.append(((f"uncontested: the quote on {row} reads '{quote}', which {why}; DealScreen does not "
                             "read the quote further"),
                             (f"What does the quote on {row} ('{quote}') say about rights in the buyer territory, and "
                             "who holds them?"), []))


def _read_names(found: _Findings, position: RightsPosition, company: str | None) -> None:
    """A note written beside a party on a cited rights row, or beside the landscape company, is content and may name a
    third party (review R1v5 N, CN)."""
    if company and content_note(company):
        note = content_note(company)
        found.blocks.append(((f"uncontested: the landscape names the program's company as '{company}'; the note "
                              f"'{note}' is not read, and it may name a licensor or a licensee"),
                             f"Does the note '{note}' beside the company name mean that a third party holds rights?",
                             []))
    seen: set[str] = set()
    for e in position.evidence:
        if e.get("type") == FIELD_STATEMENT:
            continue
        for role in ("grantor", "grantee"):
            name = str(e.get(role) or "")
            note = content_note(name)
            if note and name not in seen:
                seen.add(name)
                found.blocks.append(((f"uncontested: rights row {e.get('row')} names '{name}'; the note '{note}' is "
                                      "not read, and it may name a third party"),
                                     (f"Does the note '{note}' beside {split_note(name)[0]} mean that a third party "
                                     "holds rights in the buyer territory?"), []))


def _read_holders(found: _Findings, position: RightsPosition, holders: list[dict[str, Any]],
                  company: str | None, rests_on: dict[str, Any] | None, covers_us: bool = True) -> None:
    known = [n for n in (company, position.owner, position.holder, *position.holders) if n]
    others: dict[str, list[dict[str, Any]]] = {}
    for claim in holders:
        value = _quoted(claim)
        if _PLACEHOLDER.match(value):
            continue
        name, note = split_note(value)[0], content_note(value)
        source, cite = field_source([claim]), field_evidence([claim], "U.S. rights holder")
        if note:
            found.blocks.append(((f"uncontested: {source} names the U.S. rights holder as '{value}'; the note "
                                 f"'{note}' is not read, and it may name a third party"),
                                 (f"Does the note '{note}' that {source} writes beside {name or 'the holder'} mean "
                                  "that a third party holds U.S. rights?"), cite))
        if name and not any(same_company(name, k) for k in known):
            others.setdefault(name, []).append(claim)
    if others and not covers_us:  # a U.S. holder says nothing sure about another territory: it blocks
        claims = [c for cs in others.values() for c in cs]
        found.blocks.append(((f"uncontested: {field_source(claims)} names {' and '.join(others)} as the U.S. rights "
                              "holder; the buyer territory does not include the U.S., and the holder may hold more"),
                             f"Does {' or '.join(others)} hold rights in the buyer territory?",
                             field_evidence(claims, "U.S. rights holder")))
        return
    if others:
        claims = [c for cs in others.values() for c in cs]
        names = list(others)
        found.holders += names
        if rests_on is None:
            basis = ("the rights evidence records no third-party grant over the U.S. (owner per evidence: "
                     f"{position.owner or 'not established'})")
        else:
            basis = (f"the position rests on {field_source([rests_on])}'s statement ('{_quoted(rests_on)}'), and no "
                     f"rights record shows a grant to {' or '.join(names)}")
        found.contests.append((f"{field_source(claims)} names {' and '.join(names)} as the U.S. rights holder; {basis}",
                               (f"Does {' or '.join(names)} hold U.S. rights, and under which deal? No rights record "
                                "shows one."), field_evidence(claims, "U.S. rights holder")))


def _offer_beside_grant(position: RightsPosition, claims: list[dict[str, Any]]) -> None:
    """A statement of availability beside a recorded grant: neither silently wins (review R1v2 E2)."""
    offers = [c for c in claims if c.get("reads") in _OFFERS and c.get("understood", True)]
    if not offers:
        return
    source = field_source(offers)
    recorded = position.holder or "a recorded holder"
    position.position = P_CONFLICTING
    position.holder = f"{recorded} (recorded; conflicting)"
    position.reasons.append(f"{source} states availability ('{_quoted(offers[0])}'); the rights evidence records an "
                            f"active grant to {recorded}")
    position.questions.append(f"Which is current: {source}'s availability statement or the grant to {recorded}?")
    position.evidence += field_evidence(offers)


def reconcile(position: RightsPosition, commercial: Any, territory: frozenset[str], *, company: str | None = None,
              as_of: date | None = None, names: list[str] | None = None,
              vocabulary: frozenset[str] = frozenset()) -> None:
    """Apply the gate to ``position`` in place (``rights_position`` and ``position_from_field`` build it fresh for
    each program). ``commercial`` is the program's ``CommercialAssessment``; ``company`` the landscape company,
    used only to refuse; ``names`` the program's own names and ids, which a rights row's quote may name;
    ``vocabulary`` the words of the program's own landscape record, which a quote may use
    (``rights_vocab.program_vocabulary``)."""
    statements = _statements(commercial)
    on_ledger = any(e.get("type") != FIELD_STATEMENT for e in position.evidence)
    if position.position in ENCUMBRANCE_POSITIONS | SHARED_POSITIONS:
        if on_ledger:  # on the field path the status already weighs the statements (a confirmed one decides)
            _offer_beside_grant(position, statements)
        return
    if position.position not in CLEAR_POSITIONS:
        return
    covers_us = "US" in territory  # every territory is read since revision 6 (review R1v5 TER-G)
    holders = _holders(commercial)
    other = list(getattr(commercial, "other_rights_all", None) or [])
    later = [c for c in statements + holders + other if _later(c, as_of)]
    if later:  # not known on the as-of date (review R1v4 A3c)
        position.reasons.append(f"not applied, dated after the as-of date {as_of}: " + "; ".join(
            f"{field_source([c])} '{_quoted(c)}' ({c.get('source_date')})" for c in later))
    found = _Findings()
    basis = list(getattr(commercial, "us_rights_basis", None) or [])
    rests_on = None if on_ledger or not basis else basis[-1]
    _read_statements(found, [c for c in statements if c not in later], company, rests_on, territory, as_of)
    _read_holders(found, position, [c for c in holders if c not in later], company, rests_on, covers_us)
    _read_other(found, [c for c in other if c not in later], company, as_of, territory)
    _read_quotes(found, position, company, as_of, territory, names, vocabulary)
    _read_names(found, position, company)
    for reason, cite in found.consistent:
        position.reasons.append(reason)
        _cite_once(position, cite)
    for blocker, question, cite in found.blocks:
        position.top_tier_blockers.append(blocker)
        position.questions.append(question)
        _cite_once(position, cite)
    if found.contests:
        position.position = P_CONFLICTING
        position.holders = list(dict.fromkeys([*position.holders, *found.holders]))
        position.holder = ("; ".join(position.holders) + " (recorded; conflicting)") if position.holders else None
        # the contest reason replaces a plain "names a U.S. rights holder" line for the same holder
        position.reasons = [x for x in position.reasons
                            if not any(f"names a U.S. rights holder or labeler: {n}" in x for n in found.holders)]
        for reason, question, cite in found.contests:
            position.reasons.append(reason)
            position.questions.append(question)
            _cite_once(position, cite)
        position.reasons += [b.split(": ", 1)[-1] for b, _, _ in found.blocks]


def _cite_once(position: RightsPosition, cite: list[dict[str, Any]]) -> None:
    """Add cited statements the position does not already cite (one claim is cited once)."""
    seen = {(e.get("claim_id"), e.get("value")) for e in position.evidence if e.get("type") == FIELD_STATEMENT}
    for c in cite:
        if (c.get("claim_id"), c.get("value")) not in seen:
            position.evidence.append(c)
            seen.add((c.get("claim_id"), c.get("value")))


def also_named(position: RightsPosition, commercial: Any) -> None:
    """A named U.S. holder that the position does not already name is shown beside it, with its source."""
    for claim in _holders(commercial):
        value = _quoted(claim)
        if _PLACEHOLDER.match(value) or any(same_company(split_note(value)[0], h) and not split_note(value)[1]
                                             for h in position.holders):
            continue
        position.holders.append(value)
        position.reasons.append(f"{field_source([claim])} also names a U.S. rights holder or labeler: {value}")


# -- rows that were not applied ------------------------------------------------------------------------------------
def program_key(value: object) -> str:
    """Program ids match without regard to case or surrounding spaces (review R1v3 E3-ids)."""
    return str(value or "").strip().casefold()


def near_key(value: object) -> str:
    """A looser id: case, spaces, punctuation and leading zeros ignored ("AB 24" and "AB-024" are near "AB-24")."""
    return "".join(_id_tokens(value))


def _id_tokens(value: object) -> list[str]:
    parts = re.findall(r"[a-z]+|\d+", program_key(value))
    return [p.lstrip("0") or "0" if p.isdigit() else p for p in parts]


def ids_close(a: object, b: object) -> bool:
    """Whether two program ids may name the same program (review R1v5 ROW). Near keys equal; or one id is the other
    with tokens added ("AB-24 (ADC)", "AB-24A", "XY9910-01" beside "AB-24", "XY9910"), when the shorter has a letter
    and a number; or the numbers are the same and each letter group starts the other's ("ABDN-24" beside "AB-24")."""
    x, y = _id_tokens(a), _id_tokens(b)
    if not x or not y:
        return False
    if "".join(x) == "".join(y):
        return True
    short, long_ = sorted((x, y), key=len)
    if long_[:len(short)] == short and any(t.isdigit() for t in short) and any(t.isalpha() for t in short):
        return True
    if len(x) != len(y) or not any(t.isdigit() for t in x):
        return False
    return all(p == q if p.isdigit() or q.isdigit() else (p.startswith(q) or q.startswith(p)) for p, q in zip(x, y))


def _reasons_text(row: dict[str, Any]) -> str:
    return "; ".join(map(str, row.get("reasons", [])))


@dataclass
class RowGuards:
    """Rights rows that were not applied, and the programs each may concern (review R1v4 R-lost, §6)."""

    #: (row number, guard reason) per program key: unattached or rejected rows whose id is near the program's id.
    per_program: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    #: (row number, guard reason) for every program: rejected rows that name no program, or an id that matches none.
    everywhere: list[tuple[int, str]] = field(default_factory=list)
    unlinked_rows: list[dict[str, Any]] = field(default_factory=list)
    unattributed_rejected_rows: list[dict[str, Any]] = field(default_factory=list)
    #: Rejected rows whose id is a program's own id.
    rejected_by_program: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def row_guards(program_keys: set[str], events: list[RightsEvent], rejected: list[dict[str, Any]],
               companies: dict[str, str] | None = None, territory: frozenset[str] | None = None) -> RowGuards:
    """``program_keys``: every program's own key (``program_key``). ``events``: accepted rows whose id is none of
    them. ``companies``: each program key's landscape company. A rejected row whose id matches no program may concern
    any program, so it guards all of them. An unattached accepted row was read in full, so it guards only programs
    whose id is close to its own (``ids_close``), or, when its id is close to none, whose company it names as a
    party and whose territory is unreadable or overlaps ``territory`` (review R1v6 R9: a company's deals for other
    programs in other places do not hold every program of that company)."""
    companies = companies or {}
    out = RowGuards()
    for e in events:
        close = sorted(k for k in program_keys if ids_close(e.external_id, k))
        parties = [p for p in (e.grantor, e.grantee) if p]
        # A row whose id is close to a program is about that program; only a row whose id points nowhere may be
        # about any program of a company it names.
        reaches = territory is None or e.territory is None or bool(set(e.territory) & territory)
        by_party = [] if close or not reaches else sorted(k for k in program_keys if companies.get(k)
                                                          and any(same_company(p, companies[k]) for p in parties))
        out.unlinked_rows.append({"row": e.row_number, "program_id": e.external_id, "event_id": e.event_id,
                                  "type": e.event_type, "type_words": e.words, "when": e.when,
                                  "source": e.source_reference,
                                  "grantee": e.grantee, "grantor": e.grantor, "territory": e.territory_as_written,
                                  "near_program_keys": close + by_party})
        for k in close:
            out.per_program.setdefault(k, []).append((e.row_number,
                (f"rights row {e.row_number} ({e.words}, {e.when}) names program id '{e.external_id}', close to this "
                "program's id; it was not attached and may concern this program")))
        for k in by_party:
            out.per_program.setdefault(k, []).append((e.row_number,
                (f"rights row {e.row_number} ({e.words}, {e.when}) names this program's company "
                f"({companies[k]}) as a party, under program id '{e.external_id}', which matches no program; it was "
                "not attached and may concern this program")))
    for row in rejected:
        key = program_key(row.get("external_id"))
        if key in program_keys:
            out.rejected_by_program.setdefault(key, []).append(row)
            continue
        close = sorted(k for k in program_keys if ids_close(key, k)) if key else []
        out.unattributed_rejected_rows.append({
            "row": row["row_number"], "program_id": row.get("external_id") or None,
            "reasons": list(row.get("reasons", [])), "type_as_written": row.get("type_as_written"),
            "grantee": row.get("grantee"), "grantor": row.get("grantor"), "territory": row.get("territory"),
            "when": row.get("event_date"), "near_program_keys": close})
        named = f"names program id '{row.get('external_id')}', which matches no program," if key else "names no program"
        for k in close:
            out.per_program.setdefault(k, []).append((row["row_number"],
                (f"rights row {row['row_number']} names program id '{row.get('external_id')}', close to this program's "
                f"id, and was rejected at import ({_reasons_text(row)}); it may concern this program")))
        out.everywhere.append((row["row_number"], (f"rights row {row['row_number']} {named} and was rejected at "
                                                  f"import ({_reasons_text(row)}); it may concern any program")))
    return out


def guards_for(rows: RowGuards, key: str, rejected: list[dict[str, Any]]) -> list[str]:
    """The guard reasons for one program: its own rejected rows, rows whose id is close to its id, then rows that may
    concern any program. A row is named once, in its most specific reason."""
    own = rows.per_program.get(key, [])
    named = {n for n, _ in own} | {r["row_number"] for r in rejected}
    return ([rejected_guard(r) for r in rejected] + [text for _, text in own]
            + [text for n, text in rows.everywhere if n not in named])


def rejected_guard(row: dict[str, Any]) -> str:
    return (f"rights row {row['row_number']} for this program was rejected at import ({_reasons_text(row)}); the "
            "rights evidence is incomplete")


__all__ = ["RowGuards", "accepted_form", "also_named", "field_evidence", "field_source", "guards_for", "ids_close",
           "near_key", "program_key",
           "reconcile", "rejected_guard", "row_guards"]
