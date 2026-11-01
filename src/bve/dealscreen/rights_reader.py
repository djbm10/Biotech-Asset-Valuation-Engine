"""How DealScreen reads a free-text rights statement: a landscape U.S.-rights cell, an analyst assertion or an agent
sentence (cycle R1; strict reader since revision 5, review R1v4 T, T2, A4 and FE).

The reader is an allow-list. The text is split into clauses (at ";", sentence ends, "but", "however") and each
clause is read as one of:

- an offer: rights are available, or a partner is sought, in plain present words about U.S. rights or rights with no
  place named ("U.S. rights available", "available for exclusive licensing", "seeking a co-development partner",
  "open to partnering", "partner sought", "available: yes"). Every word must be in the reader's vocabulary, except
  a leading company name followed by a verb ("Acme Bio is seeking a partner"), which is kept as the offering
  party, and program codes ("SKB-315");
- a contest: not available ("not available", "no U.S. rights available", "available: no", "none available"), or a
  license, sublicense, option, partnership, collaboration or co-development that covers the U.S., the world or no
  place named;
- a return of rights;
- consistent with no third-party U.S. grant: a placeholder ("not reported", "undisclosed"), a negated grant ("not
  licensed in the U.S.", "unencumbered"), U.S. rights retained, a grant over other places only ("licensed in China
  only"), or an offer of other places only ("available in Europe");
- unread: anything else. A hedge, a condition, a question, a future or past tense, a place the reader does not
  know, or an offer that excludes the U.S. is unread.

The statement reads AVAILABLE only when every clause is read and at least one is an offer: an unread clause beside
an offer may qualify it. Different readings together are CONFLICTING. ``understood`` is False when any clause is
unread; the top-tier gate treats such text as a possible contest (``rights_gate``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bve.dealscreen.rights_territory import _EXCLUSION, _WORLD, regions_named

AVAILABLE = "AVAILABLE_PER_SOURCE"
AVAILABLE_CONFIRMED = "AVAILABLE_ANALYST_CONFIRMED"
NOT_AVAILABLE = "NOT_AVAILABLE_PER_SOURCE"
ENCUMBERED = "ENCUMBERED_PER_SOURCE"
UNKNOWN = "UNKNOWN"
#: Cycle C1 X4: neither is availability.
RETURNED = "RIGHTS_RETURNED_TO_ORIGINATOR_PER_SOURCE"
OPTION = "OPTION_HELD_BY_THIRD_PARTY_PER_SOURCE"
CONFLICTING = "CONFLICTING"
#: Statuses that say a third party holds, or may hold, U.S. rights, or that rights are not available.
CONTESTS = frozenset({NOT_AVAILABLE, ENCUMBERED, OPTION, CONFLICTING})

_OFFER, _CONTEST, _RETURN, _CONSISTENT, _UNREAD = "offer", "contest", "return", "consistent", "unread"


@dataclass(frozen=True)
class RightsReading:
    status: str
    #: False when any clause could not be read.
    understood: bool = True
    #: Named parties making an offer ("Acme Bio is seeking a partner"); empty for "the company" or no subject.
    parties: tuple[str, ...] = ()
    #: The clauses that could not be read, as written.
    unread: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Clause:
    kind: str
    text: str
    status: str | None = None
    party: str | None = None


# -- text preparation ---------------------------------------------------------------------------------------
#: "U.S.", "U. S.", "U.S.A." (any case) and "U.S", "USA" read as "US"; lowercase "us" stays a pronoun.
_US_DOTTED = re.compile(r"(?<![A-Za-z])[Uu]\.\s?[Ss]\.(?:\s?[Aa]\.)?|(?<![A-Za-z.])U\.S(?![A-Za-z.])")
_US_WORDS = re.compile(r"(?<![A-Za-z])(?:united states of america|united states|USA)(?![A-Za-z])", re.IGNORECASE)
_ABBREVIATION = re.compile(r"\b(inc|ltd|co|corp|llc|plc|bros|ltda|approx|incl|excl)\.", re.IGNORECASE)
_SPLIT = re.compile(r";|\.(?=\s|$)|!|,?\s+\b(?:but|however|whereas|although)\b,?", re.IGNORECASE)


def _prepare(text: str) -> str:
    text = _US_DOTTED.sub("US", text)
    text = _US_WORDS.sub("US", text)
    return _ABBREVIATION.sub(r"\1", text)


def _clauses(text: str) -> list[str]:
    return [c.strip(" ,:-\t\n") for c in _SPLIT.split(_prepare(text)) if c.strip(" ,:-\t\n.")]


# -- clause patterns ----------------------------------------------------------------------------------------
_PLACEHOLDER = re.compile(
    r"^(?:(?:us|ex-us|global|worldwide|all)\s+)?(?:rights?\s*:?\s*)?"
    r"(?:-+|\?+|n/?a|na|none|nil|unknown|undisclosed|not disclosed|not reported|not stated|not specified|no data|"
    r"tbd|tbc|to be determined|to be confirmed|not applicable|none recorded|none reported|no information)$",
    re.IGNORECASE)
_NO_GRANT = re.compile(
    r"^(?:(?:us|global|worldwide)\s+)?(?:rights?\s+)?(?:(?:are|is)\s+)?"
    r"(?:unpartnered|unencumbered|unlicensed|wholly owned|fully owned|"
    r"no\s+(?:known\s+|current\s+)?(?:partners?|partnerships?|licen[cs]es?|licensees?|deals?|encumbrances?|options?)"
    r"(?:\s+(?:recorded|reported|disclosed|announced|known|yet))?)"
    r"(?:\s+(?:in|for)\s+(?:the\s+)?US)?$", re.IGNORECASE)
#: A negated grant ("not licensed", "never partnered", "no longer optioned") says no grant is recorded. That is
#: neither an encumbrance nor availability, so it is removed before the clause is read (review R1v3).
_NEGATED_GRANT = re.compile(
    r"\b(?:not|never|no longer)\s+(?:(?:yet|been|currently|ever)\s+){0,2}"
    r"(?:out-?|sub)?(?:licen[cs]ed|partnered|optioned|encumbered|co-?develop\w*|co-?promot\w*)\b",
    re.IGNORECASE)
_TRIVIAL = frozenset({"in", "the", "us", "for", "rights", "right", "yet", "to", "a", "any", "third", "party",
                      "parties", "anyone", "and", "is", "are", "currently", "program", "asset"})
_NOT_AVAILABLE = re.compile(
    r"\b(?:not|no longer|never)\b[^.;]{0,25}\bavailable\b"
    r"|\bunavailable\b|\bno rights\b|\brights retained by\b"
    r"|\b(?:no|none|nothing)\b(?:\s+(?:us|worldwide|global|other|further|more|commercial|development|licensing|"
    r"rights?|territor(?:y|ies)|of|the|program|asset|is|are|currently|now))*\s+available\b"
    r"|\bavailable\b[^.;]{0,30}?(?:[:?=(]|\s[-–—])\s*(?:no|n|none|not anymore|not at this time|"
    r"not currently)\b", re.IGNORECASE)
#: A return of RIGHTS (review C1-6): the verb must sit next to "rights", or a license/deal must be
#: terminated. "Patients returned to the clinic" is not a rights statement.
_RETURNED = re.compile(
    r"\brights?\b[^.;]{0,40}\b(?:returned|handed back|reverted|regained)\b"
    r"|\b(?:returned|handed back|reverted|regained)\b[^.;]{0,40}\brights?\b"
    r"|\bterminat\w* (?:the |its |our |their )?(?:license|licence|licensing|agreement|deal|collaboration)\b",
    re.IGNORECASE)
#: An option over rights, not "a treatment option".
_OPTION = re.compile(r"\boption (?:to|on|for) (?:\w+ ){0,2}(?:licen[cs]\w*|rights|acquir\w*|exclusive)",
                     re.IGNORECASE)
_EXERCISED = re.compile(r"\bexercis\w*\b", re.IGNORECASE)
#: A grant, transfer or shared deal. "Option" alone is not one ("a treatment option").
_GRANT = re.compile(
    r"(?<![A-Za-z])(?:re-|out-|sub)?licen[cs]ed\b|\bsublicen[cs]\w*|\bpartnered\b|\boptioned\b|\bco-?develop\w*"
    r"|\bco-?promot\w*|\bexclusiv\w*|\bencumbered\b|\bcollaborat\w*|\bpartnership with\b"
    r"|\bexercis\w*\b[^.;]{0,30}\boption\b|\b(?:sold|assigned|transferred|divested)\s+to\b", re.IGNORECASE)
_RETAINED = re.compile(r"^(?:the\s+)?(?:(?:US|worldwide|global|all)\s+)?(?:commercial\s+)?rights?\s+(?:are\s+|is\s+)?"
                       r"(?:retained|kept)$", re.IGNORECASE)
_CORE = re.compile(r"\b(?:available|seek(?:s|ing)?|sought|open to)\b", re.IGNORECASE)
#: Party names follow these words in deal text ("licensed to ChinaCo"); places in them are not territories.
_PARTY_SPAN = re.compile(r"\b(?:to|with|by|from)\s+(?:the\s+)?(?:[A-Z0-9][\w.&'’-]*\s*)+")
_US_EXCLUDED = re.compile(r"(?:\b(?:excluding|outside(?:\s+of)?|except(?:\s+for)?|other than|not in|but not)\s+"
                          r"(?:the\s+)?|(?<![A-Za-z])ex-\s*)US\b", re.IGNORECASE)
_CODE = re.compile(r"(?=[a-z0-9-]*[a-z])(?=[a-z0-9-]*\d)[a-z0-9-]+")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’&\-]*|[?:=()]")
#: Every word an offer may contain (lower case). Anything else leaves the clause unread.
_VOCAB = frozenset({
    "available", "availability", "seeking", "seeks", "seek", "sought", "open", "to", "for", "yes", "offers",
    "discussions", "partner", "partners", "partnership", "partnerships", "partnering", "licensee", "licensees",
    "licensing", "license", "licence", "out-licensing", "out-license", "out-licence", "outlicensing",
    "co-development", "codevelopment", "co-promotion", "copromotion", "co-commercialization", "co-commercialisation",
    "collaboration", "collaborations", "collaborator", "collaborators", "acquisition", "acquirer", "acquirers",
    "buyer", "buyers", "sale", "deal", "deals", "transaction", "transactions", "strategic", "commercial",
    "commercialization", "commercialisation", "development", "exclusive", "non-exclusive", "new", "potential",
    "suitable", "rights", "right", "program", "programme", "asset", "candidate", "compound", "product", "its", "our",
    "us", "worldwide", "global", "globally", "world", "territories", "territory", "markets", "all", "the", "a", "an",
    "of", "and", "in", "is", "are", "remains", "remain", "currently", "now", "actively", "company", "it", "we", "that",
    "stated", "states", "says", "said", "per", ":", "owner",
})
_GENERIC_SUBJECT = frozenset({"the", "company", "it", "we", "owner", "our", "its"})
_SUBJECT_VERBS = frozenset({"is", "are", "remains", "has", "have", "stated", "states", "says", "said", "seeks",
                            "announced", "confirmed"})


def _covers_us(clause: str) -> bool:
    """Whether a clause about a grant, an offer or a refusal may concern the U.S.: it names the U.S. (not excluded),
    the world, the rest of the world after an exclusion ("ex-China"), or no place at all. Place words inside a party
    name ("licensed to Origin Bio China") are not territories."""
    text = _PARTY_SPAN.sub(" ", clause)
    if _US_EXCLUDED.search(text):
        return False
    named = regions_named(text)
    if "US" in named or _WORLD.search(text) or _EXCLUSION.search(text):
        return True
    return not named


def _subject(tokens: list[str]) -> tuple[str | None, int]:
    """A leading company name followed by a verb ("Acme Bio is ..."): (name, index after the verb). Generic subjects
    ("The Company is ...") name no party."""
    for i, token in enumerate(tokens):
        if token.casefold() in _SUBJECT_VERBS and i > 0:
            head = tokens[:i]
            if all(t[0].isupper() or t[0].isdigit() or t == "&" for t in head):
                if all(t.casefold() in _GENERIC_SUBJECT for t in head):
                    return None, 0
                return " ".join(head), i + 1
            return None, 0
    return None, 0


def _offer(clause: str) -> tuple[bool, str | None]:
    """A plain present offer of U.S. rights or of rights with no place named, and the named party making it."""
    if not _CORE.search(clause):
        return False, None
    tokens = _TOKEN.findall(clause)
    party, start = _subject(tokens)
    rest = [t.casefold() for t in tokens[start:]]
    has_us = "us" in rest
    for token in rest:
        if token in _VOCAB or (token == "only" and has_us) or _CODE.fullmatch(token):
            continue
        return False, None
    return True, party


def _read_clause(clause: str) -> list[_Clause]:
    if _PLACEHOLDER.fullmatch(clause) or _NO_GRANT.fullmatch(clause):
        return [_Clause(_CONSISTENT, clause)]
    rest = _NEGATED_GRANT.sub(" ", clause)
    if rest != clause:
        left = [w.casefold() for w in _TOKEN.findall(rest)]
        if all(w in _TRIVIAL for w in left):
            return [_Clause(_CONSISTENT, clause)]
        clause = " ".join(rest.split())
    if _NOT_AVAILABLE.search(clause):
        return [_Clause(_CONTEST, clause, NOT_AVAILABLE) if _covers_us(clause) else _Clause(_CONSISTENT, clause)]
    is_offer, party = _offer(clause)
    if is_offer:
        return [_Clause(_OFFER, clause, AVAILABLE, party)]
    if _CORE.search(clause) and _GRANT.search(clause):  # "licensed in China and available in the U.S."
        parts = [p for p in re.split(r",?\s+\band\b\s+|,\s*", clause) if p.strip()]
        read = [c for p in parts for c in _read_clause(p)] if len(parts) > 1 else []
        if read and all(c.kind != _UNREAD for c in read):
            return read
    if _RETURNED.search(clause):
        return [_Clause(_RETURN, clause, RETURNED)]
    if _OPTION.search(clause) and not _EXERCISED.search(clause):
        return [_Clause(_CONTEST, clause, OPTION) if _covers_us(clause) else _Clause(_CONSISTENT, clause)]
    if _GRANT.search(clause):
        return [_Clause(_CONTEST, clause, ENCUMBERED) if _covers_us(clause) else _Clause(_CONSISTENT, clause)]
    if _RETAINED.fullmatch(clause):
        return [_Clause(_CONSISTENT, clause)]
    if _CORE.search(clause) and not _US_EXCLUDED.search(clause):
        named = regions_named(_PARTY_SPAN.sub(" ", clause))
        if named and "US" not in named:  # an offer of other places only says nothing about the U.S.
            return [_Clause(_CONSISTENT, clause)]
    return [_Clause(_UNREAD, clause)]


def rights_reading(text: str) -> RightsReading:
    """How a rights statement reads, clause by clause (module docstring)."""
    clauses = [c for clause in _clauses(text or "") for c in _read_clause(clause)]
    unread = tuple(c.text for c in clauses if c.kind == _UNREAD)
    statuses = {c.status for c in clauses if c.status}
    if unread:
        statuses.discard(AVAILABLE)
    status = UNKNOWN if not statuses else (statuses.pop() if len(statuses) == 1 else CONFLICTING)
    parties = tuple(dict.fromkeys(c.party for c in clauses if c.party)) if status == AVAILABLE else ()
    return RightsReading(status, not unread, parties, unread)


def rights_status(text: str) -> str:
    return rights_reading(text).status


#: How each U.S.-rights status reads in prose. The codes stay in the JSON and the workbook.
RIGHTS_STATUS_WORDS = {
    AVAILABLE: "available (source-provided, unverified)",
    AVAILABLE_CONFIRMED: "available (analyst-asserted or -confirmed from a cited source)",
    NOT_AVAILABLE: "not available (source-provided)",
    ENCUMBERED: "licensed, optioned or partnered (source-provided)",
    RETURNED: "rights returned (source-provided)",
    OPTION: "an option held by a third party (source-provided)",
    CONFLICTING: "conflicting statements",
    UNKNOWN: "unknown",
}

__all__ = [
    "AVAILABLE", "AVAILABLE_CONFIRMED", "CONFLICTING", "CONTESTS", "ENCUMBERED", "NOT_AVAILABLE", "OPTION", "RETURNED",
    "RIGHTS_STATUS_WORDS", "UNKNOWN", "RightsReading", "rights_reading", "rights_status",
]
