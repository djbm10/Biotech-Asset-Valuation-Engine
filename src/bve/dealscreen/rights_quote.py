"""The quote on a rights row, read beside a clear position (cycle R1 revisions 10-13).

Revisions 9 to 11 passed a clause when each of its words was on a list; every review found a listed word that carried
a holder, a reach or a condition (review R1v11 §8). Since revision 12 each clause is read as a whole, and since
revision 13 the fixed sentences of ``rights_template`` are the only reader: a clause passes only when it is one of a
few fixed sentences for the row's own type, its slots filled by the row's own parties in their roles, the program, a
place inside the row's territory, a date not after the as-of date and an amount, or the sentence "<grantor> retains
rights ...". The plain-form reader (``rights_allow``) no longer reads quotes: it read "it", "we" and "the company" as
the program's company (review R1v12 PF-PRONOUN, SUFFIX2).

Every character is read. Typographic punctuation is written in ASCII first; any other character outside ASCII
(Chinese text, full-width letters) blocks with the clause quoted (review R1v12 NONLATIN).

Before reading, press furniture is removed, each only when anchored: a dateline on the first line of the quote whose
city is in capitals and whose region parts are places ("BOSTON, Mass., March 3, 2025 /PRNewswire/ --"), a stock
exchange note of the form "(Nasdaq: TICK)", a speaker attribution whose title is "of <known party>", an adviser of a
known party, a description of a known party ("<known party>, a global biopharmaceutical company") and a news byline
at the end of a clause. A stripped name may not contain a template, rights or place word (review R1v12 HEADLINE2,
STRIP-CAPS). Everything else blocks with the clause quoted. A human analyst who has read the source can confirm the row
(``review.Action.CONFIRM_RIGHTS_ROW``); a confirmed row's quote is not read again until the row changes.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

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
    template_words,
    to_slots,
)
from bve.dealscreen.rights_territory import GENERIC_NAME_WORDS, parse_territory

#: Typographic characters written in ASCII before reading; any other non-ASCII character blocks.
_TYPOGRAPHY = str.maketrans({
    **dict.fromkeys("\u2018\u2019\u201a\u201b\u2032\u00b4\u0060", "'"),
    **dict.fromkeys("\u201c\u201d\u201e\u201f\u2033\u00ab\u00bb", '"'),
    **dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63", "-"),
    **dict.fromkeys("\u00a0\u2002\u2003\u2007\u2009\u200a\u202f", " "),
    **dict.fromkeys("\u00ae\u2122\u00a9\u2120\u200b\u200c\u200d\ufeff", ""),
    "\u2026": "...",
})
#: Characters a quote may hold after the typography is written in ASCII: printable ASCII and ordinary whitespace.
_READABLE = re.compile(r"[\x20-\x7e\t\n\r]*")
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
#: A city in capitals on one line: "SAN DIEGO", "SOUTH SAN FRANCISCO" (review R1v12 HEADLINE2: never across a line).
_CITY = r"[A-Z][A-Z.\-']+(?:[ \t]+[A-Z][A-Z.\-']+){0,3}"
_REGION_PART = r"[A-Z][A-Za-z.]+(?:[ \t]+[A-Z][A-Za-z.]+){0,2}"  # "China", "Mass.", "United Kingdom": checked below
#: A dateline at the start of a quote: a city in capitals, up to two place parts, a full date, an optional wire and a
#: dash (review R1v11 HEADLINE: a title-case headline is not a place).
_WIRES = (r"(?:PRNewswire(?:-[A-Za-z]+)?|PR Newswire|BUSINESS WIRE|Business Wire|GLOBE NEWSWIRE|GlobeNewswire|"
          r"ACCESSWIRE|ACCESS Newswire|EINPresswire|Newsfile Corp\.?|CNW)")
_PLACE_LIST = rf"{_CITY}(?:,[ \t]*{_REGION_PART}){{0,2}}(?:[ \t]+and[ \t]+{_CITY}(?:,[ \t]*{_REGION_PART}){{0,2}})*"
_DATELINE = re.compile(rf"^[ \t]*(?P<places>{_PLACE_LIST}),[ \t]+"
                       rf"(?:{_MONTH_RX}[ \t]+\d{{1,2}},?[ \t]+\d{{4}}|\d{{1,2}}[ \t]+{_MONTH_RX}[ \t]+\d{{4}})[ \t]*"
                       rf"(?:/[ \t]*{_WIRES}[ \t]*/)?[ \t]*(?:--|-)[ \t]*"
                       rf"|^[ \t]*(?P<places2>{_PLACE_LIST})[ \t]*--[ \t]*\([ \t]*{_WIRES}[ \t]*\)[ \t]*--[ \t]*")
#: Region parts a dateline may give after its city: U.S. states (names, AP and postal abbreviations), provinces and
#: countries. Any other part is not a place, and the dateline is read as text (review R1v12 HEADLINE2).
_STATE_NAMES = ("Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho "
              "Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota "
              "Mississippi Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania Tennessee Texas Utah "
              "Vermont Virginia Washington Wisconsin Wyoming")
_US_STATES = _STATE_NAMES.split() + [
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Rhode Island",
    "South Carolina", "South Dakota", "West Virginia", "D.C.", "Puerto Rico"]
_ABBR_TEXT = ("Ala. Ariz. Ark. Calif. Colo. Conn. Del. Fla. Ga. Ill. Ind. Kan. Ky. La. Md. Mass. Mich. Minn. Miss. "
               "Mo. Mont. Neb. Nev. N.H. N.J. N.M. N.Y. N.C. N.D. Okla. Ore. Pa. R.I. S.C. S.D. Tenn. Vt. Va. Wash. "
               "W.Va. Wis. Wyo. AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
               "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC")
_STATE_ABBR = _ABBR_TEXT.split()
_COUNTRIES = ["China", "P.R. China", "PRC", "Japan", "Korea", "South Korea", "Republic of Korea", "Taiwan",
              "Hong Kong", "Singapore", "Australia", "Canada", "Israel", "India", "Switzerland", "Germany", "France",
              "Italy", "Spain", "Ireland", "Belgium", "Netherlands", "The Netherlands", "Denmark", "Sweden", "Norway",
              "Finland", "Austria", "United Kingdom", "U.K.", "UK", "England", "Scotland", "United States", "U.S.",
              "US", "USA", "U.S.A.", "Ontario", "Quebec", "British Columbia", "Jiangsu", "Zhejiang", "Guangdong",
              "Shandong", "Sichuan", "Hubei", "Shanghai", "Beijing"]
_DATELINE_REGIONS = frozenset(x.casefold() for x in [*_US_STATES, *_STATE_ABBR, *_COUNTRIES])
_K = f"[{KNOWN_MARKS}]"
_CAPS = r"(?:[A-Z][\w.'’\-]*\s+){0,3}[A-Z][\w.'’\-]*"
_TITLE_WORDS = (r"(?:(?:the|and|&|of|Chief|Executive|Officer|President|Vice|Senior|Head|Global|Director|Chair\w*|"
                r"Founder|Co-founder|Medical|Scientific|Business|Development|Commercial|Operating|Financial|"
                r"Technology|General|Manager|Managing|Corporate|Strategy|CEO|CFO|COO|CSO|CMO|SVP|EVP)\b[\s,&]*)+")
_SAID = r"(?:said|says|added|commented|stated|noted)"
_HONORIFIC = r"(?:(?:Dr|Mr|Ms|Mrs|Prof)\.?\s+)?"
#: '..., said Jane Doe, Chief Executive Officer of <known>' and 'Jane Doe, Chief Executive Officer of <known>, said'.
_ATTRIBUTION = re.compile(rf",?\s*{_SAID}\s+{_HONORIFIC}(?P<n1>{_CAPS})\s*,\s*{_TITLE_WORDS}(?:of|at)\s+{_K}(?:'s|’s)?\s*$"
                          rf"|^\s*{_HONORIFIC}(?P<n2>{_CAPS})\s*,\s*{_TITLE_WORDS}(?:of|at)\s+{_K}\s*,?\s*{_SAID}\b\s*,?")
#: '<Name> advised <known>', '<Name> is acting as financial advisor to <known>': the whole clause.
_ADVISER = re.compile(rf"^\s*(?P<n>{_CAPS})\s+(?:(?:advised|is\s+advising)\s+{_K}|(?:is|are|acted)\s+(?:acting\s+|serving\s+)?"
                      rf"as\s+(?:the\s+)?(?:exclusive\s+|lead\s+|sole\s+)?(?:financial|legal)\s+advis[oe]rs?\s+"
                      rf"(?:to\s+){_K})(?:\s+(?:and|,)\s+{_K})?[\s,.]*(?:on\s+the\s+(?:transaction|deal|agreement))?"
                      r"[\s.]*$")
#: '<known>, a global biopharmaceutical company[,]' -> '<known>'.
_APPOSITIVE = re.compile(rf"({_K})\s*,\s*(?:a|an)\s+(?:leading\s+)?(?:(?:global|clinical-stage|commercial-stage|"
                         r"late-stage|privately-held|private|publicly-traded|biopharmaceutical|biotechnology|"
                         r"pharmaceutical|biotech)\s+){1,3}company\b(?:\s*,)?")
#: '<known>, a wholly owned subsidiary of <known>' -> the first, only when the parent is the program's company
#: (review R1v13 SUBSID): a licensee or other party that controls the licensor controls its rights.
_SUBSIDIARY = re.compile(rf"({_K})\s*,?\s*(?:a|an|the)\s+(?:wholly[\s\-]owned\s+)?(?:subsidiary|affiliate)\s+of\s+({_K})"
                         r"(?:\s*,)?")
#: "..., Biotech Wire has learned" at the end of a clause.
_BYLINE = re.compile(rf",\s*(?P<n>{_CAPS})\s+(?:has|have)\s+learned\s*\.?\s*$")
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


#: Words that hold, grant or place rights: never part of a stripped city, adviser, byline or speaker name.
_HOLD_WORDS = frozenset({"rights", "right", "holds", "hold", "held", "holding", "owns", "own", "owned", "owner",
                         "retains", "retain", "retained", "keeps", "keep", "kept", "licensed", "licenses", "license",
                         "licence", "licensee", "licensor", "option", "options", "partner", "partnered", "exclusive",
                         "global", "worldwide", "territory", "acquired", "acquires", "us", "usa", "u.s", "ex-us",
                         "china", "japan", "europe", "korea", "row", "world", "granted", "grants", "sold", "returned",
                         "regained", "commercial", "commercialization", "development"})


def _name_ok(name: str) -> bool:
    """A name taken out with press furniture holds no template, rights or place word (review R1v12 STRIP-CAPS)."""
    words = {w.casefold().strip(".'") for w in re.split(r"[\s\-/,]+", name) if w}
    return not (words & (_HOLD_WORDS | template_words()))


def _strip_dateline(text: str) -> str:
    """The quote without a dateline whose city words are not template or rights words and whose region parts are
    places (review R1v12 HEADLINE2)."""
    m = _DATELINE.match(text)
    if not m:
        return text
    places = m.group("places") or m.group("places2") or ""
    for group in re.split(r"[ \t]+and[ \t]+", places):
        city, *regions = [x.strip() for x in group.split(",")]
        if not _city_ok(city) or not all(_region_ok(r) for r in regions):
            return text
    return text[m.end():]


#: Dateline cities of more than one word. A city of one word may be any name; a longer one must be on this list, so
#: a headline ("TESSALY BUYS NERIDA") is never removed as a city (review R1v13 HEADLINE3). An unlisted city leaves
#: the dateline in the text, where its words block the quote: a usefulness cost, never a pass.
_MULTI_WORD_CITIES = frozenset(" ".join(c.casefold().split()) for c in (
    "South San Francisco", "San Francisco", "San Diego", "San Mateo", "San Carlos", "San Jose", "San Rafael",
    "Santa Clara", "Santa Monica", "Santa Barbara", "Palo Alto", "Menlo Park", "Redwood City", "Foster City",
    "Mountain View", "La Jolla", "Los Angeles", "Newport Beach", "Thousand Oaks", "Emeryville", "New York",
    "New Haven", "New Brunswick", "East Hanover", "Basking Ridge", "Jersey City", "Short Hills", "Fort Lee",
    "King of Prussia", "West Chester", "Blue Bell", "Plymouth Meeting", "Spring House", "Research Triangle Park",
    "Chapel Hill", "Salt Lake City", "St. Louis", "Saint Louis", "Ann Arbor", "Kansas City", "Lake Forest",
    "North Chicago", "Deerfield", "Silver Spring", "College Park", "White Plains", "Hong Kong", "Tel Aviv",
    "Abu Dhabi", "New Delhi", "Mexico City", "Sao Paulo", "Kuala Lumpur", "Rio de Janeiro", "Frankfurt am Main",
    "The Hague", "Saint-Prex", "Bad Homburg"))


def _city_ok(city: str) -> bool:
    words = city.split()
    if not words or not _name_ok(city):
        return False
    return len(words) == 1 or " ".join(w.casefold() for w in words) in _MULTI_WORD_CITIES


def _region_ok(region: str) -> bool:
    """A region part of a dateline: a listed state, province or country, with "Province" allowed after it."""
    low = " ".join(region.casefold().split())
    return low in _DATELINE_REGIONS or (low.endswith(" province") and low[: -len(" province")] in _DATELINE_REGIONS)


def _sub_named(rx: re.Pattern[str], text: str, keep: str = "") -> str:
    """``rx.sub`` that takes out a match only when its named parts (groups called ``n``...) are names."""
    def take(m: re.Match[str]) -> str:
        names = [v for k, v in m.groupdict().items() if k.startswith("n") and v]
        if not all(_name_ok(n) for n in names):
            return m.group(0)
        return m.expand(keep) if keep else " "
    return rx.sub(take, text)


def _prepare_text(text: str) -> str:
    """The quote without its dateline, exchange notes and treatment options."""
    text = _strip_dateline(text)
    text = _EXCHANGE_NOTE.sub(" ", text)
    return ORDINARY_OPTION.sub(" ", _TREATMENT_OPTION.sub(" ", text))


def _strip_known(masked: str, owner_mark: str | None = None) -> str:
    """Remove speaker attributions, advisers, bylines and descriptions anchored to a known party. ``owner_mark`` is
    the marker of the program's company."""
    masked = _sub_named(_ADVISER, masked)
    masked = _sub_named(_ATTRIBUTION, masked)
    masked = _SUBSIDIARY.sub(lambda m: m.group(1) if owner_mark and m.group(2) == owner_mark else m.group(0), masked)
    masked = _APPOSITIVE.sub(r"\1", masked)
    return _sub_named(_BYLINE, masked)


def _unreadable(text: str, names: list[str]) -> str | None:
    """Text outside ASCII that is not part of a known name: DealScreen cannot read it, so it may say anything
    (review R1v12 NONLATIN). The text around it is quoted."""
    rest = text
    for name in sorted({n.translate(_TYPOGRAPHY).strip() for n in names if n.strip()}, key=len, reverse=True):
        rest = re.sub(re.escape(name), " ", rest, flags=re.IGNORECASE)
    if _READABLE.fullmatch(rest):
        return None
    bad = next(i for i, c in enumerate(rest) if not _READABLE.fullmatch(c))
    piece = rest[max(0, bad - 20): bad + 40].strip()
    return (f"has text DealScreen cannot read ('{piece}'): characters outside plain English text may say who holds "
            "rights, so the quote is not read further")


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
    text = text.translate(_TYPOGRAPHY)
    if why := _unreadable(text, parties + [n for n in (names or []) if n]):
        return why
    if "?" in text:  # review R1v13 PUNCT: a question states nothing
        at = text.index("?")
        return (f"asks a question ('{text[max(0, at - 50): at + 1].strip()}'), so it does not state who holds "
                "rights")
    text = _prepare_text(text)
    if why := _variants(_prepare(text), parties):
        return why
    roles = _roles(e, company)
    named = roles + [(n, PROGRAM) for n in (names or []) if n]
    owner_mark = next((m for n, m in roles if company and n == company), None)
    grantor_owns = bool(company) and _one_entity(company, str(e.get("grantor") or ""))
    for clause in _clauses(text) or [text]:
        masked = _strip_known(_mask(_prepare(clause), named), owner_mark).strip(" ,.")
        if not masked:
            continue
        slots = to_slots(masked, vocabulary)
        read = read_clause(slots, kind, own, territory, as_of, _row_day(e), vocabulary, grantor_owns=grantor_owns)
        if not read.ok:
            whole = clause.strip(" .;") == text.strip(" .;")
            return read.why if whole else f"has the clause '{clause.strip()}', which {read.why}"
    return None


__all__ = ["quote_problem"]
