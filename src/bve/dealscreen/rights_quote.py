"""The quote on a rights row, read fail closed beside a clear position (cycle R1 revisions 10-11).

Earlier revisions blocked a quote when it matched a list of bad words; each review found a wording the lists missed.
Revision 10 required every capitalised name to be placed but let any other word through (review R1v10 LOWER,
PLACE). Revision 11 reads every word. A clause of the quote passes only when it is one of these:

- a plain form saying no grant was made or that the company kept its rights (``rights_allow``);
- a restatement of its own row:
  - every capitalised name is the row's grantor or grantee or the program's company (with corporate words after
    it, never a place word), the program itself, a place, or an agency, exchange or currency code;
  - every other word is a grammar word, an amount or a date, a generic drug-development word, a word that restates
    the row's own type, or a word from the program's own landscape record (``rights_vocab``);
  - no date in it is after the as-of date, and on an ending no year is after the row's own year;
  - and it reaches no place in the buyer territory that the row does not cover.

Before reading, text that cannot hold rights is removed, each only when anchored to a known party or to the start
of the quote: a dateline ("BOSTON, March 3, 2025 /PRNewswire/ --"), a speaker attribution ("said Jane Doe, Chief
Executive Officer of <known party>"), an adviser ("<Name> advised <known party>") and a description of a known party
("<known party>, a global biopharmaceutical company"). Everything else blocks with the word or name that stopped it.

A company whose name is made only of allowed words ("Novel Grant", with no corporate word) is read as words; a name
with any corporate word ("Pharma", "Bio", "Inc") or any word outside the lists is read as a name and must be placed.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any

from bve.dealscreen.rights import (
    ACQUISITION,
    CO_DEVELOPMENT,
    CO_PROMOTION_OPTION,
    LICENSE,
    OPTION,
    OPTION_EXERCISED,
    OPTION_LAPSED,
    RIGHTS_RETURNED,
    TERMINATION,
)
from bve.dealscreen.rights_allow import plain_form
from bve.dealscreen.rights_reader import _clauses, _prepare
from bve.dealscreen.rights_signals import (
    CAP_SIGNALS,
    GRANT_TIME,
    ORDINARY_OPTION,
    SUB_PLACE,
    signal,
    sub_places,
)
from bve.dealscreen.rights_territory import (
    GENERIC_NAME_WORDS,
    _strip_regions,
    parse_territory,
    regions_named,
    same_company,
)
from bve.dealscreen.rights_vocab import (
    DATED_ENDING_WORDS,
    FUNCTION_WORDS,
    GENERAL_WORDS,
    ROW_WORDS,
    is_number,
)

_GRANTS = frozenset({LICENSE, OPTION, OPTION_EXERCISED, CO_DEVELOPMENT, CO_PROMOTION_OPTION})
_ENDS = frozenset({TERMINATION, RIGHTS_RETURNED, OPTION_LAPSED, ACQUISITION})
#: Rows announced in the future tense ("X will receive rights", "Y will pay ... to acquire Z, subject to closing").
_ANNOUNCED = _GRANTS | {ACQUISITION}
_QUOTE_FORMS = frozenset({"rights kept by the company", "no grant stated"})

_MONTHS = {m.casefold(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS |= {m.casefold(): i for i, m in enumerate(calendar.month_abbr) if m} | {"sept": 9}
_MONTH_WORDS = frozenset(_MONTHS) | frozenset({"q1", "q2", "q3", "q4", "h1", "h2", "monday", "tuesday", "wednesday",
                                               "thursday", "friday"})
#: Agencies, exchanges, meetings, currencies and science acronyms, read only when written in capitals: none holds
#: rights to a program.
_NOT_HOLDERS = frozenset({
    "FDA", "EMA", "NMPA", "PMDA", "MHRA", "CDE", "CHMP", "NIH", "NCI", "IND", "BLA", "NDA", "MAA", "NASDAQ", "NYSE",
    "HKEX", "SSE", "SZSE", "TSE", "KOSDAQ", "KRX", "LSE", "ASX", "TSX", "ASCO", "ESMO", "AACR", "ASH", "ADC", "ADCS",
    "MAB", "CAR-T", "TCR", "ORR", "PFS", "OS", "DCR", "R&D", "USD", "EUR", "GBP", "JPY", "CNY", "RMB", "CHF", "HKD",
    "KRW", "CAD", "AUD", "SEK", "DKK", "NOK", "INR", "SGD", "I", "II", "III", "IV", "NCT"})
#: Corporate words: a capitalised one is part of a name, whatever the lists say ("Grant Therapeutics").
_LEGAL = frozenset({"inc", "ltd", "limited", "llc", "plc", "gmbh", "ag", "sa", "co", "corp", "corporation", "group",
                    "holdings", "kk", "nv", "bv", "pte", "pty", "spa", "kgaa", "srl", "labs", "laboratories",
                    "partners", "capital", "ventures", "biotherapeutics", "biopharmaceuticals", "pharmaceuticals"})
_PLACE_NAME_WORDS = frozenset({"us", "usa", "america", "americas", "japan", "europe", "china", "global",
                               "international"})
_NAME_WORDS = (GENERIC_NAME_WORDS - _PLACE_NAME_WORDS) | _LEGAL
#: Corporate words that may follow a known name and still name it ("Chinaco Pharma Co., Ltd"). No place word:
#: "Chinaco Pharma U.S." names the U.S. (review R1v10 MASK).
_COMPANY_WORDS = "|".join(sorted(map(re.escape, _NAME_WORDS), key=len, reverse=True))
_EXCHANGE_NOTE = re.compile(r"\([^()]*\b(?:Nasdaq|NASDAQ|NYSE|HKEX|SSE|SZSE|TSE|KOSDAQ|KRX|LSE|ASX|TSX|SIX|"
                            r"Euronext|STAR)\b[^()]*\)")
_MONTH_RX = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_PLACE_RX = r"[A-Z][A-Za-z.\-]*(?:\s+[A-Z][A-Za-z.\-]*){0,3}"
#: "BOSTON, March 3, 2025 /PRNewswire/ --" or "OSAKA, Japan and CAMBRIDGE, Mass., October 21, 2025 –" at the start
#: of a quote: where and when the release was issued.
_DATELINE = re.compile(rf"^\s*{_PLACE_RX}(?:,\s*{_PLACE_RX})*(?:\s+and\s+{_PLACE_RX}(?:,\s*{_PLACE_RX})*)*,\s+"
                       rf"(?:{_MONTH_RX}\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+{_MONTH_RX}\s+\d{{4}})\s*"
                       rf"(?:/[^/]{{1,40}}/)?\s*(?:--|–|—|-)\s*")
_CAPS = r"(?:[A-Z][\w.'’\-]*\s+){0,3}[A-Z][\w.'’\-]*"
_TITLE_WORDS = (r"(?:(?:the|and|&|of|Chief|Executive|Officer|President|Vice|Senior|Head|Global|Director|Chair\w*|"
                r"Founder|Co-founder|Medical|Scientific|Business|Development|Commercial|Operating|Financial|"
                r"Technology|General|Manager|Managing|Corporate|Strategy|CEO|CFO|COO|CSO|CMO|SVP|EVP)\b[\s,&]*)+")
_SAID = r"(?:said|says|added|commented|stated|noted)"
_HONORIFIC = r"(?:(?:Dr|Mr|Ms|Mrs|Prof)\.?\s+)?"
#: '..., said Jane Doe, Chief Executive Officer of <known>' and 'Jane Doe, Chief Executive Officer of <known>, said'.
_ATTRIBUTION = re.compile(rf",?\s*{_SAID}\s+{_HONORIFIC}{_CAPS}\s*,\s*{_TITLE_WORDS}(?:of|at)\s+\x00"
                          rf"|{_HONORIFIC}{_CAPS}\s*,\s*{_TITLE_WORDS}(?:of|at)\s+\x00\s*,?\s*{_SAID}\b")
#: '<Name> advised <known>', '<Name> is acting as financial advisor to <known>'.
_ADVISER = re.compile(rf"{_CAPS}\s+(?:(?:advised|is\s+advising)\s+\x00|(?:is|are|acted)\s+(?:acting\s+|serving\s+)?"
                      rf"as\s+(?:the\s+)?(?:exclusive\s+|lead\s+|sole\s+)?(?:financial|legal)\s+advis[oe]rs?\s+"
                      rf"(?:to\s+)\x00)")
#: '<known>, a global biopharmaceutical company' and '<known>, a wholly owned subsidiary of <known>'.
_APPOSITIVE = re.compile(r"\x00\s*,\s*(?:a|an)\s+(?:leading\s+)?(?:(?:global|clinical-stage|commercial-stage|"
                         r"biopharmaceutical|biotechnology|pharmaceutical)\s+){1,3}company\b")
#: "<known>, a subsidiary of <Name>": the name is the known party's parent, named only directly after it (review
#: R1v9 A8).
_PARENT = re.compile(rf"\x00\s*,?\s*(?:a|an|the)\s+(?:wholly[\s\-]owned\s+)?(?:subsidiary|unit|division)\s+of\s+{_CAPS}"
                     r"(?=\s*(?:[,.;)]|$)|\s+(?:for|in|to|and)\s)")
_SUBSIDIARY = re.compile(r"\x00\s*,?\s*(?:a|an|the)\s+(?:wholly[\s\-]owned\s+)?(?:subsidiary|affiliate)\s+of\s+\x00")
_IDIOMS = re.compile(r"\bin\s+a\s+row\b", re.IGNORECASE)
#: "a potential new treatment option": not an option over rights, and "new" there is not a new holder.
_TREATMENT_OPTION = re.compile(r"\b(?:(?:potential|new|novel|important)\s+)*(?:treatment|therapeutic|therapy|"
                               r"therapies|care|dosing|standard)\s+options?\b", re.IGNORECASE)
#: "its third China deal": the count of the company's own deals, not a third party.
_DEAL_COUNT = re.compile(r"\bits\s+(?:first|second|third|fourth|fifth|sixth|\d+(?:st|nd|rd|th))\b(?=\s+(?:[A-Z][\w.]*"
                         r"\s+)?(?:deal|licen[cs]e|licensing|transaction|agreement)s?\b)", re.IGNORECASE)
#: "..., Biotech Wire has learned" at the end of a clause: a news byline, not a holder (review R1v10 PLACE keeps
#: "has confirmed" and "reported" out: those can be a party speaking).
_BYLINE = re.compile(rf",\s*{_CAPS}\s+(?:has|have)\s+learned\s*\.?\s*$")
_TOKEN = re.compile(r"[A-Za-z0-9$€£¥][\w.&'’%\-]*")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_DAY_MONTH_YEAR = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_RX})\s+(\d{{4}})\b")
_MONTH_DAY_YEAR = re.compile(rf"\b({_MONTH_RX})\s+(\d{{1,2}}),?\s+(\d{{4}})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH_YEAR = re.compile(rf"\b({_MONTH_RX})\s+(\d{{4}})\b")
#: A program code ("NB-7", "XYZ-1234A"): letters then digits. Alone it names a molecule, not a holder; with any other
#: word in its run ("T7 Bio") the run is a name and must be placed (review R1v10 PLACE).
_CODE = re.compile(r"^[A-Z]{1,6}[-‐]?\d{1,6}[A-Za-z]?$")
_KNOWN = "\x00"  # stands in for a known party or the program in the text being read


def _month(word: str) -> int:
    return _MONTHS[word.casefold().rstrip(".")]


def _clause_dates(clause: str) -> list[date]:
    """The dates a clause gives: a day, or the last day of a month or of a year. Each span is read once."""
    out: list[date] = []

    def take(rx: re.Pattern[str], make: Any) -> None:
        nonlocal clause
        for m in rx.finditer(clause):
            try:
                out.append(make(m))
            except (KeyError, ValueError):
                continue
        clause = rx.sub(" ", clause)

    take(_DAY_MONTH_YEAR, lambda m: date(int(m[3]), _month(m[2]), int(m[1])))
    take(_MONTH_DAY_YEAR, lambda m: date(int(m[3]), _month(m[1]), int(m[2])))
    take(_ISO, lambda m: date(int(m[1]), int(m[2]), int(m[3])))
    take(_MONTH_YEAR, lambda m: date(int(m[2]), _month(m[1]),
                                     calendar.monthrange(int(m[2]), _month(m[1]))[1]))
    take(_YEAR, lambda m: date(int(m[0]), 12, 31))
    return out


def _initials(name: str) -> str | None:
    words = [w for w in re.split(r"[\s,.\-]+", name) if w and w.casefold() not in _LEGAL]
    return "".join(w[0] for w in words).upper() if len(words) > 1 else None


def _mask(text: str, names: list[str]) -> str:
    """The text with each known name (longest first, any case), the corporate words after it and an acronym of its
    initials in parentheses ("Kappa Nerida Bio (KNB)"), replaced by one marker."""
    for name in sorted({_prepare(n).strip() for n in names if n and n.strip()}, key=len, reverse=True):
        acronym = _initials(name)
        defined = rf"(?:\s*\(\s*[\"“]?{re.escape(acronym)}[\"”]?\s*\))?" if acronym else ""
        text = re.sub(rf"(?<![\w]){re.escape(name)}(?:[\s,]+(?:{_COMPANY_WORDS})\b\.?)*{defined}(?:'s|’s)?(?![\w])",
                      f" {_KNOWN} ", text, flags=re.IGNORECASE)
        if acronym:
            text = re.sub(rf"(?<![\w]){re.escape(acronym)}(?:'s|’s)?(?![\w])", f" {_KNOWN} ", text)
    return text


def _variants(text: str, names: list[str]) -> str | None:
    """Two forms of one known name with different business words ("Chinaco Pharma" and "Chinaco Bio") may be two
    companies (review R1v10 PC5): the quote names both, and the second may hold rights."""
    business = "|".join(sorted(map(re.escape, GENERIC_NAME_WORDS - _PLACE_NAME_WORDS), key=len, reverse=True))
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


def _clean(token: str) -> str:
    return re.sub(r"(?:'s|’s)$", "", token.casefold().strip(".,'’"))


class _Reader:
    """The names and words of one clause, against what the row may say."""

    def __init__(self, kind: str, known: list[str], vocabulary: frozenset[str], dated_ok: bool) -> None:
        self.kind = kind
        self.known = known
        self.allowed = FUNCTION_WORDS | GENERAL_WORDS | ROW_WORDS.get(kind, frozenset()) | vocabulary
        self.dated_ok = dated_ok
        self.unknown: list[str] = []
        self.words: list[str] = []

    def word_ok(self, word: str) -> bool:
        if word in self.allowed or is_number(word) or word in _MONTH_WORDS:
            return True
        if self.kind in _ANNOUNCED and word in GRANT_TIME:
            return True
        if self.kind in _ENDS and word in DATED_ENDING_WORDS and self.dated_ok:
            return True
        if self.kind in _GRANTS and word == "only":
            return True
        parts = [p for p in word.split("-") if p]
        return len(parts) > 1 and all(self.word_ok(p) for p in parts)

    def _name_like(self, token: str, word: str) -> bool:
        if not token[0].isupper():
            return False
        if word in _NAME_WORDS:
            return True
        if token.isupper() and word in CAP_SIGNALS:
            return False
        return not self.word_ok(word) and not signal(word)

    def read(self, clause: str) -> None:
        run: list[re.Match[str]] = []
        lead: list[re.Match[str]] = []  # capitalised allowed words just before a possible name
        last_end = 0
        for m in _TOKEN.finditer(clause):
            token, word = m.group(0), _clean(m.group(0))
            joined = clause[last_end:m.start()].strip() in ("", "&")
            last_end = m.end()
            if self._name_like(token, word):
                if run and not joined:
                    self._run(clause, lead, run)
                    run, lead = [], []
                if not run and lead and not joined:
                    self.words += [_clean(x.group(0)) for x in lead]
                    lead = []
                run.append(m)
                continue
            if run:
                self._run(clause, lead, run)
                run, lead = [], []
            self.words += [_clean(x.group(0)) for x in lead]
            lead = []
            if token[0].isupper():
                lead.append(m)
            else:
                self.words.append(word)
        if run:
            self._run(clause, lead, run)
        else:
            self.words += [_clean(x.group(0)) for x in lead]

    def _run(self, clause: str, lead: list[re.Match[str]], run: list[re.Match[str]]) -> None:
        core = re.sub(r"(?:'s|’s)$", "", clause[run[0].start():run[-1].end()].strip(" .,'’"))
        if all(m.group(0).strip(".,") in _NOT_HOLDERS for m in run) or (
                len(run) == 1 and _CODE.match(re.sub(r"(?:'s|’s)$", "", run[0].group(0).strip(".,")))):
            self.words += [_clean(x.group(0)) for x in lead]
            return
        full = re.sub(r"(?:'s|’s)$", "", clause[(lead or run)[0].start():run[-1].end()].strip(" .,'’"))
        bare = any(_clean(m.group(0)) not in _NAME_WORDS for m in run)
        if any(same_company(full, k) for k in self.known):
            return
        if bare and any(same_company(core, k) for k in self.known):
            self.words += [_clean(x.group(0)) for x in lead]
            return
        self.unknown.append(full)


def _clause_problem(clause: str, e: dict[str, Any], known: list[str], own: frozenset[str], territory: frozenset[str],
                    as_of: date | None, vocabulary: frozenset[str]) -> str | None:
    kind = str(e.get("type") or "")
    dates = _clause_dates(clause)
    later = [d for d in dates if as_of and d > as_of]
    if later:
        return (f"gives the date {max(later).isoformat()}, after the as-of date {as_of}, so what it describes may not "
                "have happened by then")
    year = _row_year(e)
    if kind in _ENDS and year and any(d.year > year for d in dates):
        return "gives a year after the row's own date, so the ending may not yet be in effect"
    places = (regions_named(clause) | sub_places(clause)) & territory
    reader = _Reader(kind, known, vocabulary, dated_ok=bool(dates))
    reader.read(SUB_PLACE.sub(" ", _strip_regions(clause)[1]))
    if reader.unknown:
        names = ", ".join(dict.fromkeys(reader.unknown))
        return (f"names {names}, which DealScreen cannot place as a party to the row, the program's company, the "
                "program or a place, so it may hold rights the row does not show")
    covers = territory <= own
    for word in reader.words:
        if reader.word_ok(word):
            continue
        why = signal(word)
        if why == "wide" and covers:
            continue
        if why == "time":
            what = "ending" if kind in _ENDS else "grant"
            return f"says '{word}', so the {what} may be later, conditional or contested"
        if why == "hedge" and kind in _ENDS:
            return f"says '{word}', so the ending may be partial"
        if why == "wide":
            return f"says '{word}', which may reach beyond the row's own territory"
        row = kind.lower().replace("_", " ")
        return (f"says '{word}', which DealScreen does not read as restating the row ({row}), so it may show a "
                "holder, a reach or a condition the row does not")
    extra = places - own
    if extra:
        return f"names {'/'.join(sorted(extra))}, in the buyer territory, which the row's own territory does not"
    return None


def _row_year(e: dict[str, Any]) -> int | None:
    found = _YEAR.match(str(e.get("date") or ""))
    return int(found.group(0)) if found else None


def _prepare_text(text: str) -> str:
    """The quote without its dateline, exchange notes and idioms that look like rights words."""
    text = _DATELINE.sub("", text)
    text = _EXCHANGE_NOTE.sub(" ", text)
    text = _DEAL_COUNT.sub("its", _TREATMENT_OPTION.sub(" ", text))
    return _IDIOMS.sub(" ", ORDINARY_OPTION.sub(" ", text))


def _strip_known(masked: str) -> str:
    """Remove speaker attributions, advisers and descriptions anchored to a known party."""
    for rx in (_ATTRIBUTION, _ADVISER, _SUBSIDIARY, _PARENT, _APPOSITIVE):
        masked = rx.sub(f" {_KNOWN} ", masked)
    return _BYLINE.sub(" ", masked)


def quote_problem(text: str, e: dict[str, Any], company: str | None, as_of: date | None, territory: frozenset[str],
                  names: list[str] | None = None, vocabulary: frozenset[str] = frozenset()) -> str | None:
    """Why the quote of a rights row (not an availability statement) blocks a clear position, or None.
    ``text`` is the quote with any speaker prefix already handled; ``names`` are the program's own names and ids;
    ``vocabulary`` the words of the program's own landscape record (``rights_vocab.program_vocabulary``)."""
    own = parse_territory(str(e.get("territory") or "")) or frozenset()
    known = [str(x) for x in (e.get("grantor"), e.get("grantee"), company) if x]
    text = _prepare_text(text)
    names_known = known + [n for n in (names or []) if n]
    if why := _variants(_prepare(text), known):
        return why
    for clause in _clauses(text) or [text]:
        if plain_form(clause, company, as_of, territory) in _QUOTE_FORMS:
            continue
        masked = _strip_known(_mask(clause, names_known))
        why = _clause_problem(masked, e, known, own, territory, as_of, vocabulary)
        if why:
            return why
    return None


__all__ = ["quote_problem"]
