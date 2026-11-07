"""The quote on a rights row, read beside a clear position (cycle R1 revisions 10-12).

Revisions 9 to 11 passed a clause when each of its words was on a list; every review found a listed word that carried
a holder, a reach or a condition (review R1v11 §8). Revision 12 reads each clause as a whole. A clause passes only
when it is one of these:

- a plain form saying no grant was made or that the company kept its rights (``rights_allow``);
- one of a few fixed sentences for the row's own type, its slots filled by the row's own parties in their roles,
  the program, a place inside the row's territory, a date not after the as-of date and an amount
  (``rights_template``).

Before reading, press furniture is removed, each only when anchored: a dateline at the start of the quote whose
place is in capitals ("BOSTON, March 3, 2025 /PRNewswire/ --"), a stock exchange note of the form "(Nasdaq: TICK)",
a speaker attribution whose title is "of <known party>", an adviser of a known party, a description of a known party
("<known party>, a global biopharmaceutical company") and a news byline at the end of a clause. Everything else
blocks with the clause quoted. A human analyst who has read the source can confirm the row
(``review.Action.CONFIRM_RIGHTS_ROW``); a confirmed row's quote is not read again until the row changes.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from bve.dealscreen.rights_allow import plain_form
from bve.dealscreen.rights_ledger import _one_entity
from bve.dealscreen.rights_reader import _clauses, _prepare
from bve.dealscreen.rights_signals import ORDINARY_OPTION
from bve.dealscreen.rights_template import (
    COMPANY,
    GRANTEE,
    GRANTOR,
    KNOWN_MARKS,
    PROGRAM,
    read_clause,
    to_slots,
)
from bve.dealscreen.rights_territory import GENERIC_NAME_WORDS, parse_territory

_QUOTE_FORMS = frozenset({"rights kept by the company", "no grant stated"})
#: Legal forms that do not change the entity ("Chinaco Pharma Co., Ltd."). "Holdings", "Group", "International",
#: "US" and "Company" make another entity and are never absorbed into a known name (review R1v11 SUFFIX).
_LEGAL_SUFFIX = r"(?:,?\s*(?:Inc|Incorporated|Ltd|Limited|LLC|L\.L\.C|PLC|GmbH|AG|S\.?A|N\.?V|B\.?V|K\.?K|Co|Corp|" \
                r"Corporation|Pte|Pty|S\.?p\.?A|KGaA)\b\.?)*"
#: Business words after a known name ("ChinaCo" written "Chinaco Pharma"): the same company, as revision 11 read it.
#: Never "Holdings", "Group", "International", "Development", "Research" or a place word, which can make another
#: entity (review R1v10 OWNER-KEY, R1v11 SUFFIX). Two different business words on one root block (``_variants``).
_BUSINESS = r"(?:\s+(?:Pharma|Pharmaceuticals?|Bio|Biotech|Biotechnology|Biosciences?|Biologics|Biopharma|" \
            r"Biopharmaceuticals?|Therapeutics|Oncology|Medicines|Sciences)\b)*"
_PLACE_NAME_WORDS = frozenset({"us", "usa", "america", "americas", "japan", "europe", "china", "global",
                               "international", "asia", "korea", "canada", "uk", "eu"})
_EXCHANGES = r"(?:Nasdaq|NASDAQ|NYSE|NYSE American|HKEX|SEHK|SSE|SZSE|TSE|TYO|KOSDAQ|KRX|LSE|ASX|TSX|SIX|Euronext|STAR)"
#: "(Nasdaq: TICK)", "(NYSE: TICK; HKEX: 1234)": only an exchange and a ticker (review R1v11 NOTE).
_EXCHANGE_NOTE = re.compile(rf"\(\s*{_EXCHANGES}\s*:\s*[A-Z0-9.]{{1,8}}(?:\s*[;,/]\s*{_EXCHANGES}\s*:\s*[A-Z0-9.]{{1,8}})*"
                            r"\s*\)")
_MONTH_RX = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|" \
            r"Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
_CITY = r"[A-Z][A-Z.\-']+(?:\s+[A-Z][A-Z.\-']+){0,3}"  # a city in capitals: "SAN DIEGO", "SOUTH SAN FRANCISCO"
_REGION_PART = r"[A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,2}"  # "China", "Mass.", "United Kingdom"
#: A dateline at the start of a quote: a city in capitals, up to two place parts, a full date, an optional wire and a
#: dash (review R1v11 HEADLINE: a title-case headline is not a place).
_WIRES = (r"(?:PRNewswire(?:-[A-Za-z]+)?|PR Newswire|BUSINESS WIRE|Business Wire|GLOBE NEWSWIRE|GlobeNewswire|"
          r"ACCESSWIRE|ACCESS Newswire|EINPresswire|Newsfile Corp\.?|CNW)")
_DATELINE = re.compile(rf"^\s*{_CITY}(?:,\s*{_REGION_PART}){{0,2}}(?:\s+and\s+{_CITY}(?:,\s*{_REGION_PART}){{0,2}})*,\s+"
                       rf"(?:{_MONTH_RX}\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+{_MONTH_RX}\s+\d{{4}})\s*"
                       rf"(?:/\s*{_WIRES}\s*/)?\s*(?:--|–|—|-)\s*"
                       rf"|^\s*{_CITY}(?:,\s*{_REGION_PART}){{0,2}}\s*--\s*\(\s*{_WIRES}\s*\)\s*--\s*")
_K = f"[{KNOWN_MARKS}]"
_CAPS = r"(?:[A-Z][\w.'’\-]*\s+){0,3}[A-Z][\w.'’\-]*"
_TITLE_WORDS = (r"(?:(?:the|and|&|of|Chief|Executive|Officer|President|Vice|Senior|Head|Global|Director|Chair\w*|"
                r"Founder|Co-founder|Medical|Scientific|Business|Development|Commercial|Operating|Financial|"
                r"Technology|General|Manager|Managing|Corporate|Strategy|CEO|CFO|COO|CSO|CMO|SVP|EVP)\b[\s,&]*)+")
_SAID = r"(?:said|says|added|commented|stated|noted)"
_HONORIFIC = r"(?:(?:Dr|Mr|Ms|Mrs|Prof)\.?\s+)?"
#: '..., said Jane Doe, Chief Executive Officer of <known>' and 'Jane Doe, Chief Executive Officer of <known>, said'.
_ATTRIBUTION = re.compile(rf",?\s*{_SAID}\s+{_HONORIFIC}{_CAPS}\s*,\s*{_TITLE_WORDS}(?:of|at)\s+{_K}(?:'s|’s)?\s*$"
                          rf"|^\s*{_HONORIFIC}{_CAPS}\s*,\s*{_TITLE_WORDS}(?:of|at)\s+{_K}\s*,?\s*{_SAID}\b\s*,?")
#: '<Name> advised <known>', '<Name> is acting as financial advisor to <known>': the whole clause.
_ADVISER = re.compile(rf"^\s*{_CAPS}\s+(?:(?:advised|is\s+advising)\s+{_K}|(?:is|are|acted)\s+(?:acting\s+|serving\s+)?"
                      rf"as\s+(?:the\s+)?(?:exclusive\s+|lead\s+|sole\s+)?(?:financial|legal)\s+advis[oe]rs?\s+"
                      rf"(?:to\s+){_K})(?:\s+(?:and|,)\s+{_K})?[\s,.]*(?:on\s+the\s+(?:transaction|deal|agreement))?"
                      r"[\s.]*$")
#: '<known>, a global biopharmaceutical company[,]' -> '<known>'.
_APPOSITIVE = re.compile(rf"({_K})\s*,\s*(?:a|an)\s+(?:leading\s+)?(?:(?:global|clinical-stage|commercial-stage|"
                         r"late-stage|privately-held|private|publicly-traded|biopharmaceutical|biotechnology|"
                         r"pharmaceutical|biotech)\s+){1,3}company\b(?:\s*,)?")
#: '<known>, a wholly owned subsidiary of <known>' -> the first.
_SUBSIDIARY = re.compile(rf"({_K})\s*,?\s*(?:a|an|the)\s+(?:wholly[\s\-]owned\s+)?(?:subsidiary|affiliate)\s+of\s+{_K}"
                         r"(?:\s*,)?")
#: "..., Biotech Wire has learned" at the end of a clause.
_BYLINE = re.compile(rf",\s*{_CAPS}\s+(?:has|have)\s+learned\s*\.?\s*$")
#: "a potential new treatment option": not an option over rights.
_TREATMENT_OPTION = re.compile(r"\b(?:(?:potential|new|novel|important)\s+)*(?:treatment|therapeutic|therapy|"
                               r"therapies|care|dosing|standard)\s+options?\b", re.IGNORECASE)


def _initials(name: str) -> str | None:
    words = [w for w in re.split(r"[\s,.\-]+", name) if w and not re.fullmatch(_LEGAL_SUFFIX.strip("*") + "?", w)]
    words = [w for w in words if w.casefold() not in {"inc", "ltd", "llc", "co", "corp", "plc"}]
    return "".join(w[0] for w in words).upper() if len(words) > 1 else None


def _mask(text: str, named: list[tuple[str, str]]) -> str:
    """The text with each known name (program names first, then longest first, any case), any legal form after it
    and an acronym of its initials replaced by its role marker. A bare acronym ("KNB") counts only after the quote
    defines it ("Kappa Nerida Bio (KNB)"): otherwise "NB" in "NB-7" would be read as "Nerida Bio"."""
    order = sorted({(_prepare(n).strip(), m) for n, m in named if n and n.strip()},
                   key=lambda x: (x[1] != PROGRAM, -len(x[0])))
    for name, mark in order:
        acronym = _initials(name) if mark != PROGRAM else None
        defined = rf"\s*\(\s*[\"“]?{re.escape(acronym)}[\"”]?\s*\)" if acronym else ""
        pattern = rf"(?<![\w\x01-\x04]){re.escape(name)}{_BUSINESS if mark != PROGRAM else ''}{_LEGAL_SUFFIX}"
        has_definition = bool(acronym) and re.search(pattern + defined, text, flags=re.IGNORECASE) is not None
        text = re.sub(pattern + (f"(?:{defined})?" if acronym else "") + r"(?=(?:'s|’s)?(?![\w]))", f" {mark}", text,
                      flags=re.IGNORECASE)
        if has_definition:
            text = re.sub(rf"(?<![\w]){re.escape(acronym or '')}(?=(?:'s|’s)?(?![\w]))", f" {mark}", text)
    return re.sub(rf"({_K})\s+(?=['’]s)", r"\1", text)


def _variants(text: str, names: list[str]) -> str | None:
    """Two forms of one known name with different business words ("Chinaco Pharma" and "Chinaco Bio") may be two
    companies (review R1v10 PC5): the quote names both, and the second may hold rights."""
    business = "|".join(sorted(map(re.escape, (GENERIC_NAME_WORDS - _PLACE_NAME_WORDS) | {"holdings", "group"}),
                               key=len, reverse=True))
    for name in {_prepare(n).strip() for n in names if n and n.strip()}:
        root = re.sub(rf"(?:[\s,]+(?:{business})\b\.?)+$", "", name, flags=re.IGNORECASE).strip()
        if not root:
            continue
        forms = {" ".join(m.group(1).casefold().split())
                 for m in re.finditer(rf"(?<![\w]){re.escape(root)}((?:[\s,]+(?:{business})\b)+)", text,
                                      flags=re.IGNORECASE)}
        if len(forms) > 1:
            shown = " and ".join(f"'{root}{f if f.startswith(',') else ' ' + f}'" for f in sorted(forms))
            return f"names {shown}, which may be different companies, so one may hold rights the row does not show"
    return None


def _roles(e: dict[str, Any], company: str | None) -> list[tuple[str, str]]:
    """Each known party name with its role marker. The program's company takes the role of the row party it is one
    legal entity with (``rights_ledger._one_entity``); otherwise it has its own marker, which no template uses."""
    grantor, grantee = (str(e.get(k) or "") for k in ("grantor", "grantee"))
    out = [(grantor, GRANTOR), (grantee, GRANTEE)]
    if company:
        mark = GRANTOR if _one_entity(company, grantor) else GRANTEE if _one_entity(company, grantee) else COMPANY
        out.append((company, mark))
    return [(n, m) for n, m in out if n]


def _prepare_text(text: str) -> str:
    """The quote without its dateline, exchange notes and treatment options."""
    text = _DATELINE.sub("", text)
    text = _EXCHANGE_NOTE.sub(" ", text)
    return ORDINARY_OPTION.sub(" ", _TREATMENT_OPTION.sub(" ", text))


def _strip_known(masked: str) -> str:
    """Remove speaker attributions, advisers, bylines and descriptions anchored to a known party."""
    masked = _ADVISER.sub(" ", masked)
    masked = _ATTRIBUTION.sub(" ", masked)
    masked = _SUBSIDIARY.sub(r"\1", masked)
    masked = _APPOSITIVE.sub(r"\1", masked)
    return _BYLINE.sub(" ", masked)


def _row_day(e: dict[str, Any]) -> date | None:
    raw = str(e.get("date") or "")
    found = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    return date(int(found[1]), int(found[2]), int(found[3])) if found else None


def quote_problem(text: str, e: dict[str, Any], company: str | None, as_of: date | None, territory: frozenset[str],
                  names: list[str] | None = None, vocabulary: frozenset[str] = frozenset()) -> str | None:
    """Why the quote of a rights row (not an availability statement) blocks a clear position, or None.
    ``text`` is the quote with any speaker prefix already handled; ``names`` are the program's own names and ids;
    ``vocabulary`` the words that may describe the program (``rights_template.descriptor_words``)."""
    own = parse_territory(str(e.get("territory") or "")) or frozenset()
    kind = str(e.get("type") or "")
    parties = [str(x) for x in (e.get("grantor"), e.get("grantee"), company) if x]
    text = _prepare_text(text)
    if why := _variants(_prepare(text), parties):
        return why
    named = _roles(e, company) + [(n, PROGRAM) for n in (names or []) if n]
    for clause in _clauses(text) or [text]:
        if plain_form(clause, company, as_of, territory) in _QUOTE_FORMS:
            continue
        masked = _strip_known(_mask(_prepare(clause), named)).strip(" ,.")
        if not masked:
            continue
        slots = to_slots(masked, vocabulary)
        read = read_clause(slots, kind, own, territory, as_of, _row_day(e), vocabulary)
        if not read.ok:
            whole = clause.strip(" .;") == text.strip(" .;")
            return read.why if whole else f"has the clause '{clause.strip()}', which {read.why}"
    return None


__all__ = ["quote_problem"]
