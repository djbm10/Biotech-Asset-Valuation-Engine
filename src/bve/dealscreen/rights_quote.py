"""The quote on a cited rights row, read fail closed beside a clear position (cycle R1 revision 10, review R1v9).

Earlier revisions blocked a quote when it matched a list of bad words: a company word, a verb, a hedge, a wider
place. Each review found a wording the lists missed. This reader inverts that. A clause of a cited quote passes only
when it is one of these:

- a plain form saying no grant was made or that the company kept its rights (``rights_allow``);
- a restatement of its own row: every name in it is the row's grantor or grantee, the program's company, the
  program itself, a place, a date, a defined acronym, a person or an adviser; every rights word is one of the kinds
  that restate the row's type (``rights_signals.RESTATES``); it has no word that makes an ending later, conditional
  or partial; and it reaches no place in the buyer territory that the row does not cover.

A clause with no names and no rights, place, time or hedge words is a restatement of nothing, and passes.
Everything else blocks with the word or name that stopped it. Lists still decide which words are recognised, but a
word they miss is suspect, not harmless: a capitalised name nobody can place blocks, whatever verb it comes with.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from bve.dealscreen.rights import (
    ACQUISITION,
    CO_DEVELOPMENT,
    CO_PROMOTION_OPTION,
    LICENSE,
    OPTION,
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
    ORDINARY_WIDE,
    RESTATES,
    SUB_PLACE,
    signal,
    sub_places,
)
from bve.dealscreen.rights_territory import (
    GENERIC_NAME_WORDS,
    _strip_regions,
    name_matches,
    parse_territory,
    regions_named,
    same_company,
)

_GRANTS = frozenset({LICENSE, OPTION, CO_DEVELOPMENT, CO_PROMOTION_OPTION})
_ENDS = frozenset({TERMINATION, RIGHTS_RETURNED, OPTION_LAPSED, ACQUISITION})
#: Rows announced in the future tense ("X will receive rights", "Y will pay ... to acquire Z, subject to closing").
#: An acquisition changes the owner; while it is pending the rights stay with the acquirer's target, not a third party.
_ANNOUNCED = _GRANTS | {ACQUISITION}
_QUOTE_FORMS = frozenset({"rights kept by the company", "no grant stated"})

#: Capitalised words that are not names: function words at a sentence start or in a headline.
_FUNCTION = frozenset({
    "the", "a", "an", "under", "on", "in", "as", "after", "following", "today", "this", "these", "those", "its",
    "their", "our", "we", "it", "they", "both", "each", "with", "by", "for", "at", "from", "per", "pursuant",
    "according", "separately", "additionally", "meanwhile", "also", "any", "no", "there", "here", "when", "while",
    "if", "since", "during", "before", "prior", "through", "to", "and", "or", "so", "thus", "further", "furthermore",
    "moreover", "of", "new", "is", "are", "was", "were", "has", "have", "had", "be", "been", "that", "which", "who",
    "company", "companies", "product", "products", "field", "date", "parties", "party", "compound", "asset", "assets",
    "program", "programme", "licensee", "licensor", "agreement", "collaboration", "press", "release", "inc", "ltd",
    "limited", "llc", "plc", "gmbh", "ag", "sa", "co", "corp", "corporation", "kgaa", "bv", "nv", "spa", "srl", "kk",
})
_MONTHS = frozenset({"january", "february", "march", "april", "may", "june", "july", "august", "september",
                     "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
                     "sept", "oct", "nov", "dec", "monday", "tuesday", "wednesday", "thursday", "friday", "q1", "q2",
                     "q3", "q4", "h1", "h2"})
#: Agencies, exchanges and common science or corporate acronyms: none holds rights to a program.
_NOT_HOLDERS = frozenset({
    "fda", "ema", "nmpa", "pmda", "mhra", "cde", "chmp", "nice", "who", "nih", "nci", "ind", "bla", "nda", "maa",
    "nasdaq", "nyse", "hkex", "sse", "szse", "tse", "kosdaq", "krx", "lse", "asx", "tsx", "six", "euronext", "star",
    "adc", "adcs", "mab", "mabs", "car-t", "car", "tcr", "tce", "bsab", "sirna", "aso", "orr", "pfs", "os", "dcr",
    "ceo", "cfo", "coo", "cso", "cmo", "r&d", "phase", "dr", "mr", "ms", "mrs", "prof", "i", "ii", "iii", "iv",
    # currency codes: "will pay EUR 422 million" names an amount, not a party
    "usd", "eur", "gbp", "jpy", "cny", "rmb", "chf", "hkd", "krw", "cad", "aud", "sek", "dkk", "nok", "inr", "sgd",
})
_TITLE = re.compile(r"^\s*,?\s*(?:the\s+)?(?:chief|ceo|cfo|cso|cmo|coo|president|founder|co-founder|head|director|"
                    r"vice|senior|executive|general counsel|chairman|chair|chairwoman|managing|partner at|svp|evp)\b",
                    re.IGNORECASE)
_SAID = re.compile(r"\b(?:said|says|stated|commented|added|noted)\s*,?\s*$", re.IGNORECASE)
_ADVISER = re.compile(r"^\s*,?\s*(?:\([^)]*\)\s*)?(?:advised|advises|advising|is advising|are advising|"
                      r"acted as|acts as|served as|serves as|is acting as|are acting as|is serving as)\b",
                      re.IGNORECASE)
#: "<known party>, a subsidiary of <Name>": the name describes the row's own party (review R1v9 A8: only directly
#: after a known party, never elsewhere in the clause).
_DESCRIBES = re.compile(r"\x00\s*,?\s*(?:a|an|the)\s+(?:wholly[\s\-]owned\s+)?\x01\s+of\s+$", re.IGNORECASE)
_DESCRIBED_BY = re.compile(r"(\x00\s*,?\s*(?:a|an|the)\s+(?:wholly[\s\-]owned\s+)?)(?:subsidiary|affiliate|unit|"
                           r"division|parent)(\s+of\s+)", re.IGNORECASE)
#: "X has learned", "X reported": a news source, not a holder.
_SOURCE = re.compile(r"^\s*,?\s*(?:has|have)\s+(?:learned|learnt|reported|confirmed)\b|^\s*reports?\b|"
                     r"^\s*reported\b", re.IGNORECASE)
_EXCHANGE_NOTE = re.compile(r"\([^()]*\b(?:Nasdaq|NASDAQ|NYSE|HKEX|SSE|SZSE|TSE|KOSDAQ|KRX|LSE|ASX|TSX|SIX|"
                            r"Euronext|STAR)\b[^()]*\)")
_DEFINED = re.compile(r"[a-z][\w\-]*\s*\(([A-Z][A-Za-z0-9\-]{1,9})\)")
_TOKEN = re.compile(r"[A-Za-z0-9][\w.&'’\-]*")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_KNOWN = "\x00"  # stands in for a known party or the program in the text being read


def _tokens(name: str) -> set[str]:
    return {w.strip(".,'’()").casefold() for w in re.split(r"[\s,]+", name) if w.strip(".,'’()")}


def _cap_signal(word: str) -> str | None:
    if word in ("rofn", "rofr", "rofo"):
        return "right:reach"
    if word in ("tbd", "tba", "tbc"):
        return "time"
    if word == "plus":
        return "hedge"
    return "wide"


_COMPANY_WORDS = "|".join(sorted(map(re.escape, GENERIC_NAME_WORDS | {"inc", "ltd", "limited", "llc", "plc", "gmbh",
                                                                       "ag", "sa", "co", "corp", "corporation",
                                                                       "group", "holdings", "kk", "nv", "bv",
                                                                       "pte", "pty", "spa", "kgaa"}),
                                  key=len, reverse=True))


def _mask(text: str, names: list[str]) -> str:
    """The text with each known name (longest first, any case), and the business words after it ("Chinaco" in
    "Chinaco Pharma Co., Ltd"), replaced by one marker, as ``same_company`` reads them."""
    for name in sorted({_prepare(n).strip() for n in names if n and n.strip()}, key=len, reverse=True):
        text = re.sub(rf"(?<![\w]){re.escape(name)}(?:[\s,]+(?:{_COMPANY_WORDS})\b\.?)*(?:'s|’s)?(?![\w])",
                      f" {_KNOWN} ", text, flags=re.IGNORECASE)
    return text


class _Scan:
    """Unknown names and suspect words of one clause."""

    def __init__(self, clause: str, known: list[str], defined: set[str]) -> None:
        self.known_tokens = set().union(*(_tokens(k) for k in known)) - {"inc", "ltd", "co", "the"}
        self.known = known
        self.defined = defined
        self.unknown: list[str] = []
        self.words: list[tuple[str, str]] = []  # (word, signal)
        self._read(clause)

    def _word(self, word: str, cap: bool = False) -> None:
        w = word.casefold().strip(".'’")
        w = re.sub(r"(?:'s|’s)$", "", w)
        why = _cap_signal(w) if cap and w in CAP_SIGNALS else signal(w)
        if why:
            self.words.append((w, why))

    def _neutral(self, token: str) -> bool:
        w = _clean(token)
        return (any(c.isdigit() for c in w) or w in _MONTHS or w in _NOT_HOLDERS or token in self.defined
                or w in _FUNCTION)

    def _read(self, clause: str) -> None:
        run: list[re.Match[str]] = []
        for m in _TOKEN.finditer(clause):
            token = m.group(0)
            if token[0].isupper():
                if run and clause[run[-1].end():m.start()].strip() not in ("", "&"):
                    self._run(clause, run)
                    run = []
                run.append(m)
                continue
            if run:
                self._run(clause, run)
                run = []
            self._word(token)
        if run:
            self._run(clause, run)

    def _run(self, clause: str, run: list[re.Match[str]]) -> None:
        """A run of capitalised words: a name as a whole if it can be placed; otherwise its signal and function
        words are read as words and each remaining part must be placed ("Alpha Bio Returns U.S. Rights")."""
        while run and _clean(run[0].group(0)) in _FUNCTION:
            self._word(run[0].group(0))
            run = run[1:]
        if not run or self._placed(clause, run):
            return
        part: list[re.Match[str]] = []
        for m in run:
            if self._pulled(m.group(0)):
                if part and not self._placed(clause, part):
                    self.unknown.append(_span(clause, part))
                part = []
            else:
                part.append(m)
        if part and not self._placed(clause, part):
            self.unknown.append(_span(clause, part))

    def _pulled(self, token: str) -> bool:
        """A capitalised token that is not part of a name: a signal word, a function word, a code, a month."""
        w = _clean(token)
        if w in CAP_SIGNALS and token.isupper():
            self._word(token, cap=True)
            return True
        if signal(w):
            self._word(token)
            return True
        return self._neutral(token)

    def _placed(self, clause: str, run: list[re.Match[str]]) -> bool:
        """A run DealScreen can place: a place, a known party, the program, codes and acronyms, a person, an adviser
        or a news source, or a name described as a known party's parent or subsidiary."""
        span = _span(clause, run)
        if not span:
            return True
        if regions_named(span) or sub_places(span):
            # A place is read by the place check, but only the place: "Tessaly's U.S." still names Tessaly
            # (review R1v9 A10).
            rest = [t for t in _TOKEN.findall(SUB_PLACE.sub(" ", _strip_regions(span)[1])) if t.strip(".'’")]
            return all(self._neutral(t) or _clean(t) in self.known_tokens for t in rest)
        if all(self._neutral(m.group(0)) for m in run):
            return True
        words = _tokens(span)
        if words <= self.known_tokens or any(same_company(span, k) or name_matches(span, k) for k in self.known):
            return True
        before, after = clause[:run[0].start()], clause[run[-1].end():]
        return bool(_DESCRIBES.search(before) or _SAID.search(before) or _TITLE.match(after)
                    or _ADVISER.match(after) or _SOURCE.match(after))


def _clean(token: str) -> str:
    return re.sub(r"(?:'s|’s)$", "", token.casefold().strip(".'’"))


def _span(clause: str, run: list[re.Match[str]]) -> str:
    return re.sub(r"(?:'s|’s)$", "", clause[run[0].start():run[-1].end()].strip(" .,'’"))


def _row_year(e: dict[str, Any]) -> int | None:
    found = _YEAR.match(str(e.get("date") or ""))
    return int(found.group(0)) if found else None


def _clause_problem(clause: str, e: dict[str, Any], known: list[str], defined: set[str], own: frozenset[str],
                    territory: frozenset[str]) -> str | None:
    kind = str(e.get("type") or "")
    clause = _DESCRIBED_BY.sub("\\1\x01\\2", clause)
    scan = _Scan(clause, known, defined)
    if scan.unknown:
        names = ", ".join(dict.fromkeys(scan.unknown))
        return (f"names {names}, which DealScreen cannot place as a party to the row, the program's company, the "
                "program or a place, so it may hold rights the row does not show")
    covers = territory <= own
    allowed = RESTATES.get(kind, frozenset())
    for word, why in scan.words:
        if why.startswith("right:") and why[6:] not in allowed:
            return (f"says '{word}', which does not restate the row ({kind.lower().replace('_', ' ')}), so it may show "
                    "rights, a holder or a reach the row does not")
        if why == "time" and not (kind in _ANNOUNCED and word in GRANT_TIME):
            what = "ending" if kind in _ENDS else "grant"
            return f"says '{word}', so the {what} may be later, conditional or contested"
        if why == "hedge" and kind in _ENDS:
            return f"says '{word}', so the ending may be partial"
        if why == "wide" and not covers:
            return f"says '{word}', which may reach beyond the row's own territory"
    extra = ((regions_named(clause) | sub_places(clause)) & territory) - own
    if extra:
        return f"names {'/'.join(sorted(extra))}, in the buyer territory, which the row's own territory does not"
    year = _row_year(e)
    later = [int(y) for y in _YEAR.findall(clause)]
    if kind in _ENDS and year and any(y > year for y in later):
        return f"gives the year {max(later)}, after the row's own date, so the ending may not yet be in effect"
    return None


def quote_problem(text: str, e: dict[str, Any], company: str | None, as_of: date | None, territory: frozenset[str],
                  names: list[str] | None = None) -> str | None:
    """Why the quote of a cited rights row (not an availability statement) blocks a clear position, or None.
    ``text`` is the quote with any speaker prefix already handled; ``names`` are the program's own names and ids."""
    own = parse_territory(str(e.get("territory") or "")) or frozenset()
    known = [str(x) for x in (e.get("grantor"), e.get("grantee"), company) if x]
    text = _EXCHANGE_NOTE.sub(" ", text)
    text = ORDINARY_OPTION.sub(" ", ORDINARY_WIDE.sub(" ", text))
    defined = {m.group(1) for m in _DEFINED.finditer(text) if m.group(1).casefold() not in CAP_SIGNALS}
    for clause in _clauses(text) or [text]:
        if plain_form(clause, company, as_of, territory) in _QUOTE_FORMS:
            continue
        masked = _mask(clause, known + [n for n in (names or []) if n])
        why = _clause_problem(masked, e, known, defined, own, territory)
        if why:
            return why
    return None


__all__ = ["quote_problem"]
