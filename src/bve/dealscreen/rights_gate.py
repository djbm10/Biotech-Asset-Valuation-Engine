"""The top-tier gate: what a clear rights position must survive beyond the rights file (cycle R1, revision 5).

Review R1v4 found that the top-tier checks ran in full on one path only: text DealScreen could not read was dropped,
a holder's note was ignored, and the landscape-field path was never contested. A clear position (rights returned, no
third-party grant over the buyer territory, owner acquired, availability stated) now reaches the two top transaction
tiers only if ``rights_position`` finds it complete, specific and current, and this gate finds nothing in the rest of
the program's record that contests it or that DealScreen cannot read. It runs on the rights-file path and the
landscape-field path alike, and it never passes what it cannot read:

- Statements: every landscape and analyst U.S.-rights statement for the program is read (``rights_reader``), not only
  the one the field status was taken from. One that says rights are not available, licensed or optioned, or several
  things at once, contests the position (CONFLICTING, quoted and cited). One DealScreen cannot read blocks (quoted and
  cited). An offer made by a named party other than the program's company blocks. A statement dated after the as-of
  date is not applied, and is listed.
- Holders: every named U.S. rights holder. A note beside the name, in parentheses or brackets, blocks: it is content
  and may name a third party. A holder that is neither the program's company nor a party the rights evidence names
  contests the position.
- Rows: rights rows that were not applied and could belong to the program keep it out of the top tiers
  (``row_guards``): a rejected row whose program id matches no program may concern any program; an unattached row
  whose id differs from this program's only in case, spaces, punctuation or leading zeros may concern this one.

The gate only refuses. It never moves a position into a top tier, never decides a gate and never reads the registry
sponsor as an owner. A position that is not clear gets only the older check: a statement of availability beside a
recorded grant is a conflict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from bve.dealscreen.rights import RightsEvent
from bve.dealscreen.rights_position import (
    CLEAR_POSITIONS,
    ENCUMBRANCE_POSITIONS,
    P_CONFLICTING,
    SHARED_POSITIONS,
    RightsPosition,
)
from bve.dealscreen.rights_reader import (
    AVAILABLE,
    AVAILABLE_CONFIRMED,
    CONTESTS,
    RIGHTS_STATUS_WORDS,
    UNKNOWN,
)
from bve.dealscreen.rights_reader import rights_reading as _rights_reading
from bve.dealscreen.rights_territory import same_company, split_note
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


def _read_statements(found: _Findings, claims: list[dict[str, Any]], company: str | None,
                     rests_on: dict[str, Any] | None) -> None:
    """``rests_on``: on the field path, the statement the position was read from; None on the rights-file path."""
    if rests_on is None:
        basis, other = "the rights evidence records no third-party grant over the U.S.", "the rights evidence"
    else:
        other = f"{field_source([rests_on])}'s statement ('{_quoted(rests_on)}')"
        basis = f"the position rests on {other}"
    for claim in claims:
        source, value, cite = field_source([claim]), _quoted(claim), field_evidence([claim])
        reads = claim.get("reads", UNKNOWN)
        if reads in CONTESTS:
            found.contests.append((f"{source} reads '{value}' ({RIGHTS_STATUS_WORDS.get(reads, reads)}); {basis}",
                                   (f"Which is current: {source}'s U.S.-rights statement ('{value}') or {other}? "
                                    "Reject the one that is wrong."), cite))
        elif not claim.get("understood", True):
            found.blocks.append(((f"uncontested: {source} reads '{value}', which DealScreen cannot read as a rights "
                                 "statement; it may name a third-party holder, a condition or another place"),
                                 (f"What does {source}'s U.S.-rights statement '{value}' say about U.S. rights? "
                                 "DealScreen cannot read it."), cite))
        elif reads in _OFFERS:
            for party in claim.get("parties") or []:
                if company and same_company(party, company):
                    continue
                named = (f"the landscape names {company} as the program's company; {party} may be a licensee"
                         if company else f"no program company is named to show that {party} owns the program")
                found.blocks.append((f"specific: {source}'s statement '{value}' is made by {party}, but {named}",
                                     f"Does {party} own this program, or hold it under a license"
                                     + (f" from {company}?" if company else "?"), cite))


def _read_holders(found: _Findings, position: RightsPosition, holders: list[dict[str, Any]],
                  company: str | None, rests_on: dict[str, Any] | None) -> None:
    known = [n for n in (company, position.owner, position.holder, *position.holders) if n]
    others: dict[str, list[dict[str, Any]]] = {}
    for claim in holders:
        value = _quoted(claim)
        if _PLACEHOLDER.match(value):
            continue
        name, note = split_note(value)
        source, cite = field_source([claim]), field_evidence([claim], "U.S. rights holder")
        if note:
            found.blocks.append(((f"uncontested: {source} names the U.S. rights holder as '{value}'; the note "
                                 f"'{note}' is not read, and it may name a third party"),
                                 (f"Does the note '{note}' that {source} writes beside {name or 'the holder'} mean "
                                  "that a third party holds U.S. rights?"), cite))
        if name and not any(same_company(name, k) for k in known):
            others.setdefault(name, []).append(claim)
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
              as_of: date | None = None) -> None:
    """Apply the gate to ``position`` in place (``rights_position`` and ``position_from_field`` build it fresh for
    each program). ``commercial`` is the program's ``CommercialAssessment``; ``company`` the landscape company,
    used only to refuse."""
    statements = _statements(commercial)
    on_ledger = any(e.get("type") != FIELD_STATEMENT for e in position.evidence)
    if position.position in ENCUMBRANCE_POSITIONS | SHARED_POSITIONS:
        if on_ledger:  # on the field path the status already weighs the statements (a confirmed one decides)
            _offer_beside_grant(position, statements)
        return
    if "US" not in territory or position.position not in CLEAR_POSITIONS:
        return
    holders = _holders(commercial)
    later = [c for c in statements + holders if _later(c, as_of)]
    if later:  # not known on the as-of date (review R1v4 A3c)
        position.reasons.append(f"not applied, dated after the as-of date {as_of}: " + "; ".join(
            f"{field_source([c])} '{_quoted(c)}' ({c.get('source_date')})" for c in later))
    found = _Findings()
    basis = list(getattr(commercial, "us_rights_basis", None) or [])
    rests_on = None if on_ledger or not basis else basis[-1]
    _read_statements(found, [c for c in statements if c not in later], company, rests_on)
    _read_holders(found, position, [c for c in holders if c not in later], company, rests_on)
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
    """A looser id: case, spaces, punctuation and leading zeros ignored ("CL 24" and "CL-024" are near "CL-24")."""
    parts = re.findall(r"[a-z]+|\d+", program_key(value))
    return "".join(p.lstrip("0") or "0" if p.isdigit() else p for p in parts)


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


def row_guards(program_keys: set[str], events: list[RightsEvent], rejected: list[dict[str, Any]]) -> RowGuards:
    """``program_keys``: every program's own key (``program_key``). ``events``: accepted rows whose id is none of
    them. A rejected row whose id matches no program may concern any program, so it guards all of them; an
    unattached accepted row was read in full, so it guards only programs whose id is near its own."""
    near: dict[str, set[str]] = {}
    for key in program_keys:
        near.setdefault(near_key(key), set()).add(key)
    out = RowGuards()
    for e in events:
        close = sorted(near.get(near_key(e.external_id), set()))
        out.unlinked_rows.append({"row": e.row_number, "program_id": e.external_id, "event_id": e.event_id,
                                  "type": e.event_type, "type_words": e.words, "when": e.when,
                                  "source": e.source_reference,
                                  "grantee": e.grantee, "grantor": e.grantor, "territory": e.territory_as_written,
                                  "near_program_keys": close})
        for k in close:
            out.per_program.setdefault(k, []).append((e.row_number,
                (f"rights row {e.row_number} ({e.words}, {e.when}) names program id '{e.external_id}', close to this "
                "program's id; it was not attached and may concern this program")))
    for row in rejected:
        key = program_key(row.get("external_id"))
        if key in program_keys:
            out.rejected_by_program.setdefault(key, []).append(row)
            continue
        close = sorted(near.get(near_key(key), set())) if key else []
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


__all__ = ["RowGuards", "also_named", "field_evidence", "field_source", "guards_for", "near_key", "program_key",
           "reconcile", "rejected_guard", "row_guards"]
