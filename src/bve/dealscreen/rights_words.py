"""How rights evidence and positions are worded in the memo and the workbook (cycle R1).

The JSON and the workbook keep the codes, so they can be filtered; prose uses these words."""

from __future__ import annotations

from bve.dealscreen.rights import (
    ACQUISITION,
    AVAILABILITY_STATED,
    CO_DEVELOPMENT,
    OPTION_EXERCISED,
    OPTION_LAPSED,
    RIGHTS_RETURNED,
    TERMINATION,
)
from bve.dealscreen.rights_position import (
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
)

_OUTCOMES = frozenset({TERMINATION, RIGHTS_RETURNED, OPTION_EXERCISED, OPTION_LAPSED})

#: The positions in words, for prose.
POSITION_WORDS = {
    P_CONFLICTING: "conflicting evidence",
    P_LICENSED: "licensed in the buyer territory per evidence",
    P_OPTION: "option held in the buyer territory per evidence",
    P_SHARED: "rights shared in the buyer territory per evidence",
    P_UNSTATED: "a grant whose territory cannot be read",
    P_AVAILABILITY: "availability stated by a source (unverified)",
    P_RETURNED: "rights returned per evidence",
    P_OWNER_ACQUIRED: "owner acquired per evidence",
    P_NOT_ENCUMBERED: "no grant over the buyer territory per evidence",
    P_NONE: "no rights evidence",
    P_NOT_APPLIED: "rights rows recorded, none gives a position on the as-of date",
    P_NOT_AVAILABLE: "not available per source",
}
#: A cited landscape cell or analyst statement, as opposed to a rights-file row.
FIELD_STATEMENT = "FIELD_STATEMENT"
_ORIGIN_WORDS = {"ANALYST_ASSERTED": "analyst assertion", "AGENT_PROPOSED": "analyst-confirmed finding"}


def evidence_label(cite: dict[str, object]) -> str:
    """Where a cited item comes from: a rights-file row, a landscape cell or an analyst statement."""
    if cite.get("type") == FIELD_STATEMENT:
        origin = _ORIGIN_WORDS.get(str(cite.get("origin")))
        if origin:
            return origin
        return f"landscape row {cite['row']}" if cite.get("row") else "landscape"
    return f"rights row {cite.get('row')}"


def evidence_when(cite: dict[str, object]) -> str:
    """A cited event's date as written, with the source date when it differs."""
    d, src = cite.get("date"), cite.get("source_date")
    if d:
        return f"{d} (source {src})" if src and src != d else str(d)
    return f"undated (source {src})" if src else "undated"


def evidence_parties(cite: dict[str, object]) -> str:
    """Who a cited event names, worded for its type."""
    grantee, grantor, kind = cite.get("grantee"), cite.get("grantor"), cite.get("type")
    if kind == FIELD_STATEMENT:
        return f"reads '{cite.get('value')}'"
    if kind == ACQUISITION:
        return f"{grantee} acquired {grantor}"
    if kind == AVAILABILITY_STATED:
        return f"stated by {grantor or grantee}"
    if kind == CO_DEVELOPMENT:
        return f"partners {' and '.join(str(p) for p in (grantee, grantor) if p)}"
    if kind in _OUTCOMES:
        return f"licensee {grantee or 'not named'}, licensor {grantor or 'not named'}"
    return f"{grantee or '-'} from {grantor or '-'}"


def unapplied_row_words(row: dict[str, object]) -> str:
    """What a rights row that was applied to no program names, as written: program id, type, date, parties,
    territory, and the programs whose id is close to its own (review R1v4 O-9, R-lost). An accepted row's parties
    are worded for its type; a rejected row's type was not read, so its parties are given as grantee and grantor."""
    program = f"'{row['program_id']}'" if row.get("program_id") else "no program id"
    kind = row.get("type_words") or (f"'{row['type_as_written']}'" if row.get("type_as_written") else "type not stated")
    if row.get("type"):
        parties = evidence_parties(row)
    else:
        parties = f"grantee {row.get('grantee') or 'not named'}, grantor {row.get('grantor') or 'not named'}"
    bits = [f"{program}, {kind}, {row.get('when') or 'undated'}", parties,
            str(row.get("territory") or "territory not stated")]
    listed = row.get("near_programs")
    near = [str(n) for n in listed] if isinstance(listed, list) else []
    if near:
        bits.append("id close to " + ", ".join(near))
    return "; ".join(bits)


def evidence_quote(cite: dict[str, object], limit: int) -> str:
    """A cited quote, whitespace collapsed, clipped to ``limit`` characters with an ellipsis when cut."""
    quote = " ".join(str(cite.get("quote") or "").split())
    return quote if len(quote) <= limit else quote[: limit - 1].rstrip() + "\u2026"


__all__ = ["FIELD_STATEMENT", "POSITION_WORDS", "evidence_label", "evidence_parties", "evidence_quote",
           "evidence_when", "unapplied_row_words"]
