"""Fixed sentence templates for the quote on a rights row (cycle R1 revision 12).

Revisions 9 to 11 decided that a quote restates its row by checking its words against lists. Every review found a
word on a list that could carry a holder, a reach or a condition in some sentence ("has", "all", "after", "not",
"may"). Revision 12 reads the clause as a whole instead (review R1v11 §8). A clause passes only when it is one of a
few fixed sentences for the row's own type, with these slots:

- a party: the row's own grantor or grantee, or the program's company when it is one legal entity with one of them.
  The role must be the row's: on a license the grantor licenses and the grantee receives;
- the program: one of its own names or ids, optionally followed by a short description made of drug-development
  words and the program's own target, mechanism, modality and indication words;
- a place: a territory phrase whose regions are all inside the row's own territory;
- a date: a day, month or year that ends on or before the as-of date, or a period that contains the row's own date;
- an amount of money, on grants and acquisitions.

There is no slot for a modal ("may", "will"), a hold verb ("has the rights"), a negation (except the fixed lapse
phrase "did not exercise"), a quantifier ("all", "full") outside a row that covers the buyer territory, or a
condition ("after", "following", "upon", "subject to"). Every other clause blocks, with the clause quoted, until a
human analyst records a confirmation of the row (``review.Action.CONFIRM_RIGHTS_ROW``).
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

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
from bve.dealscreen.rights_territory import parse_territory

# -- slot markers -------------------------------------------------------------------------------------------------
GRANTOR, GRANTEE, COMPANY, PROGRAM = "\x01", "\x02", "\x03", "\x04"
DATE_MARK, PLACE_MARK, MONEY_MARK = "\x05", "\x06", "\x07"
PARTY_MARKS = GRANTOR + GRANTEE + COMPANY
KNOWN_MARKS = PARTY_MARKS + PROGRAM
_SYMBOL = {GRANTOR: "G", GRANTEE: "E", COMPANY: "C", PROGRAM: "P", DATE_MARK: "D", PLACE_MARK: "R", MONEY_MARK: "N"}

# -- dates --------------------------------------------------------------------------------------------------------
_MONTHS = {m.casefold(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS |= {m.casefold(): i for i, m in enumerate(calendar.month_abbr) if m}
_MONTHS["sept"] = 9
#: A month name, capitalised. "may" in lower case is the modal and is never a month (review R1v11 MAY).
_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|" \
         r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_DATES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"(?<![\w]){_DAY}\s+({_MONTH})\s*,?\s+((?:19|20)\d{{2}})(?![\w])"), "dmy"),
    (re.compile(rf"(?<![\w])({_MONTH})\s+{_DAY}\s*,?\s+((?:19|20)\d{{2}})(?![\w])"), "mdy"),
    (re.compile(r"(?<![\w])((?:19|20)\d{2})-(\d{2})-(\d{2})(?![\w])"), "iso"),
    (re.compile(rf"(?<![\w])({_MONTH})\s+(?:of\s+)?((?:19|20)\d{{2}})(?![\w])"), "my"),
    (re.compile(r"(?<![\w$€£¥.,])((?:19|20)\d{2})(?![\w%]|[.,]\d)"), "y"),
)


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    def text(self) -> str:
        return self.start.isoformat() if self.start == self.end else f"{self.start.isoformat()} to {self.end.isoformat()}"


def _month_no(word: str) -> int:
    return _MONTHS[word.casefold().rstrip(".")]


def _period(kind: str, m: re.Match[str]) -> Period:
    if kind == "dmy":
        d = date(int(m[3]), _month_no(m[2]), int(m[1]))
        return Period(d, d)
    if kind == "mdy":
        d = date(int(m[3]), _month_no(m[1]), int(m[2]))
        return Period(d, d)
    if kind == "iso":
        d = date(int(m[1]), int(m[2]), int(m[3]))
        return Period(d, d)
    if kind == "my":
        year, month = int(m[2]), _month_no(m[1])
        return Period(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]))
    year = int(m[1])
    return Period(date(year, 1, 1), date(year, 12, 31))


def mark_dates(text: str) -> tuple[str, list[Period]]:
    """The text with each full date (a year in it) replaced by one marker, and the periods in order of the markers.
    A date without a year ("December 1", "Q4", "Friday") is not a date here: its words match no template."""
    found: list[tuple[int, Period]] = []
    for rx, kind in _DATES:
        def take(m: re.Match[str], kind: str = kind) -> str:
            try:
                found.append((m.start(), _period(kind, m)))
            except (KeyError, ValueError):
                return m.group(0)
            return f" {DATE_MARK} "
        text = rx.sub(take, text)
    return text, [p for _, p in found]


def date_problem(periods: Iterable[Period], as_of: date | None, row_day: date | None) -> str | None:
    """A date that may be after the as-of date. A period that ends after it passes only when it contains the row's own
    date and that date is on or before the as-of date ("returned in 2025", row dated 2025-01-15)."""
    if as_of is None:
        return None
    for p in periods:
        if p.end <= as_of:
            continue
        if row_day and p.start <= row_day <= p.end and row_day <= as_of:
            continue
        return (f"gives the date {p.text()}, which may be after the as-of date {as_of}, so what it describes may not "
                "have happened by then")
    return None


# -- money ----------------------------------------------------------------------------------------------------------
_MONEY = re.compile(r"(?<![\w])(?:US\$|USD\s?|EUR\s?|RMB\s?|CNY\s?|JPY\s?|\$|€|£|¥)\s?\d[\d,]*(?:\.\d+)?"
                    r"(?:\s?(?:million|billion|mn|bn|m|b)\b)?", re.IGNORECASE)


# -- places ---------------------------------------------------------------------------------------------------------
_REGION_WORDS = (r"greater china|mainland china|china'?s mainland|china mainland|the prc|prc|china|hong kong|"
                 r"maca[ou]|taiwan|south korea|republic of korea|korea|japan|north america|"
                 r"united states of america|united states|canada|europe|european union|eea|eu5|eu|"
                 r"united kingdom|great britain|uk|worldwide|world-wide|world wide|globally|global|"
                 r"rest of (?:the )?world|ROW|US|USA")
_REGION = rf"(?:(?<![A-Za-z])(?:{_REGION_WORDS})(?![A-Za-z]))"
_PLACE_JOIN = (r"(?:(?:\s*,\s*|\s+and\s+|\s*\(\s*|\s*\)\s*|\s+(?:on\s+a\s+)?basis\b|\s*(?:the\s+)?"
               r"(?:excluding|outside(?:\s+of)?|except(?:\s+for)?|other\s+than|ex-|not\s+including)(?=\s)|"
               r"\s+including(?=\s)|\s+the(?=\s)|\s+|-)+)")
_PLACE_SPAN = re.compile(rf"(?:(?:(?:outside(?:\s+of)?|excluding|except(?:\s+for)?)\s+(?:the\s+)?|ex-\s*)?{_REGION}(?:\s+(?:territory|territories|region|regions|SAR))?)"
                         rf"(?:{_PLACE_JOIN}(?:the\s+)?(?:ex-\s*)?{_REGION}(?:\s+(?:territory|territories|region|"
                         rf"regions|SAR))?)*(?:\s*\))?", re.IGNORECASE)
_CASE_PLACE = re.compile(r"(?<![A-Za-z])(?:ROW|US|USA|UK|EU|EEA|PRC)(?![A-Za-z])")


#: The words after "global" that make it a place ("global rights", "global development and commercialization").
_GLOBAL_PLACE_NEXT = frozenset({"rights", "right", "license", "licence", "licensing", "development",
                                "commercial", "commercialization", "commercialisation", "basis", "territory",
                                "exclusive", "and", "or"})


def mark_places(text: str) -> tuple[str, list[frozenset[str] | None]]:
    """The text with each territory phrase replaced by one marker, and the regions of each (None: unreadable)."""
    regions: list[frozenset[str] | None] = []

    def take(m: re.Match[str]) -> str:
        span = m.group(0)
        after = re.match(r"\s*([A-Za-z][\w\-]*)", m.string[m.end():])
        if (span.strip().casefold() == "global" and after
                and after.group(1).casefold() not in _GLOBAL_PLACE_NEXT):
            return span  # "a global partnership", "a global biopharmaceutical company": not a place
        # case-sensitive abbreviations only in capitals ("us" is a pronoun)
        for word in re.findall(r"[A-Za-z]+", span):
            if word.casefold() in {"us", "row", "uk", "eu", "eea", "prc", "usa"} and not word.isupper():
                return span
        if span.count("(") != span.count(")"):
            span = span.replace("(", " ").replace(")", " ")
        regions.append(parse_territory(span.strip(" ,")))
        return f" {PLACE_MARK} "

    return _PLACE_SPAN.sub(take, text), regions


# -- the program's description ------------------------------------------------------------------------------------
#: Words that describe a drug and cannot name a holder, a place or a time.
DESCRIPTOR_WORDS = frozenset(["a", "an", "the", "its", "our", "their", "investigational", "novel", "potential", "first-in-class", "best-in-class", "proprietary", "lead", "next-generation", "targeted", "promising", "target", "targets", "humanized", "humanised", "fully", "human", "chimeric", "monoclonal", "antibody", "antibodies", "antibody-drug", "drug", "drugs", "conjugate", "conjugates", "adc", "adcs", "bispecific", "trispecific", "t-cell", "engager", "engagers", "cell", "cells", "therapy", "therapies", "car-t", "car", "small", "molecule", "molecules", "inhibitor", "inhibitors", "agonist", "antagonist", "degrader", "vaccine", "candidate", "candidates", "product", "compound", "asset", "program", "programme", "targeting", "directed", "against", "anti", "for", "of", "in", "with", "and", "or", "treatment", "treat", "treating", "patients", "advanced", "metastatic", "unresectable", "locally", "relapsed", "refractory", "solid", "tumor", "tumors", "tumour", "tumours", "cancer", "cancers", "carcinoma", "carcinomas", "adenocarcinoma", "clinical-stage", "clinical", "preclinical", "early-stage", "late-stage", "mid-stage", "phase", "stage", "development", "1", "2", "3", "i", "ii", "iii", "1/2", "2/3", "1b", "2a", "2b", "first-line", "second-line", "later-line", "line", "lines", "intravenous", "subcutaneous", "oral"])


def descriptor_words(texts: Iterable[str]) -> frozenset[str]:
    """Words from the program's own target, mechanism, modality, therapeutic area and indication fields that may
    describe it in a quote: written in lower case, or a symbol with a digit or in capitals ("HER2", "TROP2",
    "ADC"). A capitalised word ("American", "Tessaly") is never one (review R1v11 VOCAB). A spaced form
    "Trop 2" also gives "trop2"."""
    out: set[str] = set()
    for text in texts:
        joined = re.sub(r"(?<=[A-Za-z])\s+(?=\d)", "", text or "")
        for source in (text or "", joined):
            for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-/]*[A-Za-z0-9]|[A-Za-z0-9]", source):
                plain = token.strip(".-")
                if not plain:
                    continue
                if plain.islower() or any(c.isdigit() for c in plain) or (plain.isupper() and len(plain) > 1):
                    out.add(plain.casefold())
    # A field may not add a connective or a template word: "from", "outside" or "rights" in an indication field
    # would let a description carry a party, a place or a grant.
    return frozenset(w for w in out if not _function_word(w) and (w in DESCRIPTOR_WORDS or w not in template_words()))


def _function_word(word: str) -> bool:
    """A field word that could carry a holder, a reach, a condition or a time: the word or any of its hyphen or slash
    parts ("co-owned", "jointly-owned") is a function word (review R1v12 VOCAB2)."""
    return word in _FUNCTION_WORDS or any(p in _FUNCTION_WORDS for p in re.split(r"[-/]", word) if p)


_FUNCTION_WORDS = frozenset(["from", "on", "to", "by", "at", "as", "via", "which", "that", "who", "whose", "is", "are",
                             "was", "were", "be", "been", "has", "have", "had", "not", "no", "nor", "but", "all",
                             "any", "each", "every", "outside", "except", "excluding", "ex", "other", "others", "also",
                             "only", "under", "between", "per", "it", "they", "them", "this", "these", "those", "than",
                             "rights", "right", "license", "licence", "licensed", "partner", "partnered", "owned",
                             "holds", "held", "holder", "worldwide", "global", "territory", "territories",
                             # conditions and times (review R1v12 VOCAB2)
                             "after", "before", "following", "upon", "until", "unless", "pending", "subject", "prior",
                             "once", "when", "whenever", "if", "whether", "while", "during", "provided", "conditional",
                             "contingent", "progression", "then", "later", "future", "will", "would", "may", "might",
                             "can", "could", "should", "shall",
                             # holders and holding
                             "co-owned", "owner", "owners", "own", "owns", "jointly", "joint", "shared", "share",
                             "shares", "co", "licensee", "licensees", "licensor", "licensors", "licensing", "partners",
                             "partnership", "partnering", "sublicense", "sublicensee", "sublicensed", "sublicensing",
                             "retained", "retains", "retain", "keeps", "kept", "option", "options", "optioned",
                             "returned", "terminated", "acquired", "acquirer", "sold", "transferred", "assigned",
                             "granted", "exclusive", "exclusively", "non-exclusive", "collaboration", "collaborator",
                             "collaborators", "third", "party", "parties", "company", "companies", "sponsor",
                             "sponsors", "affiliate", "affiliates", "subsidiary", "we", "us", "our", "its", "their",
                             "his", "her", "he", "she", "never", "without", "neither", "either"])


# -- clause into slots ------------------------------------------------------------------------------------------------
@dataclass
class Slots:
    """A clause as template text: words in lower case (a capitalised word inside the clause is kept as ``^word`` and
    matches nothing), slots as single letters."""

    text: str
    places: list[frozenset[str] | None] = field(default_factory=list)
    periods: list[Period] = field(default_factory=list)
    capitalised: list[str] = field(default_factory=list)


_WORD = re.compile(rf"[{KNOWN_MARKS}{DATE_MARK}{PLACE_MARK}{MONEY_MARK}](?:'s|’s)?|[A-Za-z0-9][\w'’\-/.]*[\w]|"
                   r"[A-Za-z0-9]|,")
#: Words that may open a sentence in capitals.
_OPENERS = frozenset({"the", "on", "in", "under", "as", "effective", "today", "its", "pursuant", "a", "an", "all"})


@lru_cache(maxsize=1)
def template_words() -> frozenset[str]:
    """The literal words of every template: a headline may capitalise them. A capitalised word that is in no
    template stays a name, so a headline still cannot hide a holder."""
    found: set[str] = set()
    for kind in (LICENSE, OPTION, OPTION_EXERCISED, CO_DEVELOPMENT, CO_PROMOTION_OPTION, TERMINATION,
                 RIGHTS_RETURNED, OPTION_LAPSED, ACQUISITION):
        for rx, _ in _templates(kind, all_ok=True):
            found |= set(re.findall(r"[a-z][a-z\-]+", re.sub(r"\(\?[:!=<]", "", rx.pattern)))
    for rx in _retention():
        found |= set(re.findall(r"[a-z][a-z\-]+", re.sub(r"\(\?[:!=<]", "", rx.pattern)))
    return frozenset(found)


def _symbol_word(token: str, descriptors: frozenset[str]) -> bool:
    """A capitalised token that is a description word: each part a symbol with a digit or in capitals from the
    program's record or the description words ("HER2", "ADC", "HER2-targeting"), or a lower-case
    description word. A title-case word alone ("Trop", "American") is never one."""
    allowed = descriptors | DESCRIPTOR_WORDS
    symbol = False
    for part in (p for p in re.split(r"[-/]", token.rstrip(".")) if p):
        low = part.casefold()
        if (any(c.isdigit() for c in part) or (part.isupper() and len(part) > 1)) and low in allowed:
            symbol = True
        elif not (part.islower() and low in allowed):
            return False
    return symbol


def to_slots(clause: str, descriptors: frozenset[str]) -> Slots:
    clause, periods = mark_dates(clause)
    clause = _MONEY.sub(f" {MONEY_MARK} ", clause)
    clause, places = mark_places(clause)
    # "Trop 2" written spaced is the program's own "trop2" when the record gives it (review R1v11 §3)
    clause = re.sub(r"(?<![\w])([A-Za-z]+)\s+(\d[\d.]*\d|\d)(?![\w])",
                    lambda m: m.group(1) + m.group(2) if (m.group(1) + m.group(2)).casefold() in descriptors
                    else m.group(0), clause)
    out: list[str] = []
    capitalised: list[str] = []
    words = re.findall(r"[A-Za-z][A-Za-z\-']+", clause)
    long = [w for w in words if len(w) > 3]
    headline = (len(long) >= 2 and all(w[0].isupper() for w in long)) or (  # title case, or all capitals
        bool(words) and not any(c.islower() for w in words for c in w))
    for i, m in enumerate(_WORD.finditer(clause)):
        token = m.group(0)
        if token == ",":
            out.append(",")
            continue
        if token[0] in _SYMBOL:
            out.append(_SYMBOL[token[0]] + ("_s" if len(token) > 1 else ""))
            continue
        word = token.casefold().rstrip(".")
        if headline and word in template_words():
            out.append(word)  # a headline ("Alpha Bio Returns U.S. Rights to NB-7") capitalises template words
            continue
        if token[0].isupper() and not (i == 0 and word in _OPENERS):
            if _symbol_word(token, descriptors):
                out.append(word)  # a target symbol or a modality acronym, checked as a description below
            else:
                out.append("^" + word)
                capitalised.append(token)
            continue
        out.append(word)
    return Slots(" ".join(out), places, periods, capitalised)


#: "P for gastric cancer": what the program treats, made only of description words, before the next slot word.
_PURPOSE = re.compile(r"(?<![^ ])([PR]) for (?:the treatment of )?((?:[^ ,^A-Z]+ ){0,5}?[^ ,^A-Z]+)(?= (?:to|in|from|for|with) "
                      r"| ,|$)")
#: "the claudin18.2-targeting adc P": up to four description words directly before the program.
_BEFORE = re.compile(r"((?:^| )(?:the|its|an?) )((?:[^ ,^A-Z]+ ){1,4})P(?= |$)")
_DESCRIPTION = re.compile(r"(?:(?<=^)|(?<= ))P(?:_s)? , ((?:[^ ,^]+ ){0,11}[^ ,^]+)(?: ,(?= )|$)")


def fold_descriptions(slots: Slots, descriptors: frozenset[str]) -> str:
    """"P , an anti-claudin18.2 adc ," -> "P": a description of the program made only of description words."""
    allowed = DESCRIPTOR_WORDS | descriptors

    def ok(words: str) -> bool:
        for w in words.split():
            parts = [p for p in re.split(r"[-/]", w) if p]
            if w not in allowed and not (parts and all(p in allowed for p in parts)):
                return False
        return True

    def take(m: re.Match[str]) -> str:
        return "P" if ok(m.group(1)) else m.group(0)

    def before(m: re.Match[str]) -> str:
        # "the claudin18.2 antibody P" -> "P"; "its" stays, since it says whose program it is
        if not ok(m.group(2)):
            return m.group(0)
        lead = " " if m.group(1).startswith(" ") else ""
        return m.group(1) + "P" if m.group(1).strip() == "its" else lead + "P"

    def purpose(m: re.Match[str]) -> str:
        # "P for gastric cancer" or "R for gastric cancer": an indication, after the program or the place
        return m.group(1) if ok(m.group(2)) else m.group(0)

    text = _DESCRIPTION.sub(take, slots.text)
    text = _PURPOSE.sub(purpose, text)
    return _BEFORE.sub(before, text)


# -- templates --------------------------------------------------------------------------------------------------------
def _alt(*items: str) -> str:
    return "(?:" + "|".join(items) + ")"


_D_PRE = r"(?:(?:on|in|as of|effective(?: as of| on)?) D(?: ,)? |D , )?"
_D_POST = r"(?:(?: ,)?(?: (?:on|in|as of|effective(?: as of| on)?))? D)?"
_R = r"R(?: rights)?"
_PLACE = r"(?: (?:in|for|across|covering|throughout)(?: the)? R(?: territory| territories| region| regions)?| R)?"
_DEV = r"(?:research|develop|manufacture|commercialize|commercialise|market|sell)"
_DEV_LIST = rf"{_DEV}(?:(?: ,)? (?:and )?{_DEV})*"
_RIGHT_KIND = r"(?:(?:exclusive |sole )?(?:R )?(?:development(?: and commercial(?:ization)?)? |commercial(?:ization)? |" \
              r"development and commercialization )?)"
#: "rights to NB-7", "the exclusive rights to develop and commercialize NB-7", "an exclusive license to NB-7".
_RIGHTS_TO = (rf"(?:(?:the |its |{{ALL}})?{_RIGHT_KIND}rights? (?:to |for |of )(?:{_DEV_LIST} )?(?:the )?)")
_LICENSE_TO = (r"(?:an? (?:(?:exclusive |sole )?(?:R )?|R (?:exclusive |sole )?)licen[cs]e (?:to |for |under )"
               r"(?:{DEV} )?)").replace("{DEV}", _DEV_LIST)
_PROGRAM = r"P(?: R)?"  # "NB-7 in mainland China" reads the place as the row's
_PAY_KIND = r"(?:development|regulatory|commercial|sales|sales-based|clinical)"
_MONEY_TAIL = (rf"(?: (?:for|in exchange for) (?:an? )?(?:upfront (?:payment|fee) of )?N(?: upfront)?(?: in cash)?"
               rf"(?: (?:and|plus) (?:up to |potential )?N(?: in (?:potential )?(?:{_PAY_KIND}(?:(?: ,)? (?:and )?"
               rf"{_PAY_KIND})* )?(?:milestones?|milestone payments))?)?(?: (?:and|plus) (?:tiered )?royalties"
               r"(?: on (?:net )?sales)?)?)?")
_ANNOUNCE = r"(?:(?:{S}) (?:today )?(?:announced|announces|said|says|reported|reports|disclosed|discloses)(?: that)? )?"
_UNDER = r"(?:under (?:the terms of )?(?:the|this|its|that) (?:license |licence |collaboration |option )?agreement ,? )?"


def _frame(core: str, subject: str = "G|E|G and E|E and G") -> str:
    return (rf"^{_D_PRE}{_ANNOUNCE.format(S=subject)}{_D_PRE}{_UNDER}{core}{_PLACE}{_D_POST}"
            rf"(?: ,? (?:pursuant to|under) (?:the|an?|its) (?:exclusive )?(?:license |licence |collaboration )?"
            rf"agreement)?{_PLACE}{_D_POST}$")


def _endings(allp: str) -> list[str]:
    """Templates for a termination or a return of rights: the grant from G to E ended, or E gave its rights back."""
    has = r"(?:has |have )?"
    party = r"(?:G|E)"
    agreement = r"(?:agreement|deal|transaction)"
    t: list[str] = []
    # only a license ends a license: "the option agreement" or "the co-development agreement" may be another deal
    # (review R1v12 DEAL-KIND); a bare "the agreement" names no other kind
    deal = (r"(?:(?:license|licence|licensing|license and collaboration|collaboration and license)"
            r"(?: {agreement})?|{agreement})").replace("{agreement}", agreement)
    t += [
        (rf"{party}(?: and {party})? {has}(?:terminated|terminates|ended|ends) (?:the|its|their) (?:exclusive )?"
        rf"(?:R )?{deal}(?: (?:with|between) {party}(?: and {party})?)?(?: (?:for|covering|on|to) {_PROGRAM})?"
        r"(?: for convenience)?"),
        (rf"(?:the|E_s|G_s) (?:exclusive )?(?:R )?{deal}(?: (?:with|between) {party}(?: and {party})?)?"
        rf"(?: (?:for|covering|on|to) {_PROGRAM})? (?:was |has been |is )?(?:terminated|ended)(?: by {party})?"
        r"(?: for convenience)?"),
    ]
    back = r"(?:returned|returns|handed back|hands back|relinquished|relinquishes|gave back|gives back)"
    rights = rf"(?:the |its |{allp})?(?:R )?(?:development (?:and commercial(?:ization)? )?|commercial )?rights"
    t += [
        rf"E {has}{back} {rights}(?: (?:to|for|of) {_PROGRAM})?{_PLACE} to G",
        rf"E {has}{back} {_PROGRAM}(?: rights)?{_PLACE} to G",
        (rf"{rights}(?: (?:to|for|of) {_PROGRAM})?{_PLACE} (?:have |has )?(?:reverted|returned|"
        rf"were returned|was returned|have been returned)(?: back)? to G(?: from E)?"),
        (rf"G {has}(?:regained|regains|reacquired|reacquires|recovered|recovers|reclaimed) {rights}"
        rf"(?: (?:to|for|of) {_PROGRAM})?{_PLACE}(?: from E)?"),
    ]
    return t


@lru_cache(maxsize=1)
def _retention() -> tuple[re.Pattern[str], ...]:
    """"G retains all rights to P outside R": the grantor keeps rights (review R1v12 PF-PRONOUN). The subject is the
    masked grantor only, never a pronoun, "the company" or a name read as the company. Whatever place it names stays
    with the grantor, so the place is not checked against the row; "all" is allowed."""
    keep = r"(?:retains|retained|keeps|kept|will retain|will keep|has retained|has kept)"
    what = (r"(?:all (?:other )?|the |its |all of its )?(?:exclusive |sole )?(?:R )?"
            r"(?:development and commercial(?:ization)? |commercial(?:ization)? |development )?rights")
    obj = rf"{what}(?: (?:to|for|of) (?:{_DEV_LIST} )?(?:the )?{_PROGRAM})?"
    where = r"(?: R| (?:in|for|across|throughout)(?: the)? R(?: territory| territories| region| regions)?)?"
    return tuple(re.compile(_frame(c, subject="G")) for c in (rf"G {keep} {obj}{where}",
                                                                 rf"{_PROGRAM}{where} (?:rights )?(?:remain|remains) with G"))


@lru_cache(maxsize=32)
def _templates(kind: str, all_ok: bool) -> tuple[tuple[re.Pattern[str], bool], ...]:
    """The templates for a row type, each with whether it must name a place when the row does not cover the buyer
    territory: a grant of rights, an option or an exercise with no place reads, to a BD analyst, as the whole
    program (review R1v12 UNPLACED, ACQ-OPT)."""
    allp = "(?:all )?" if all_ok else ""
    rights_to = _RIGHTS_TO.replace("{ALL}", allp)
    # rights named without the program ("licenses rights in mainland China") restate a row that is the program's own;
    # never "all rights" outside a row that covers the buyer territory
    bare = r"(?:the |its )?(?:exclusive |sole )?(?:R )?(?:development and commercial(?:ization)? |commercial )?rights"
    obj = rf"(?:(?:{rights_to}|{_LICENSE_TO})?{_PROGRAM}|{bare})"
    rights_obj = rf"(?:(?:{rights_to}|{_LICENSE_TO}){_PROGRAM}|{bare})"
    has = r"(?:has |have )?"
    agreement = r"(?:agreement|deal|transaction)"
    t: list[str] = []  # templates that need no place: an agreement was signed, an option ended
    tp: list[str] = []  # grants: a place is required unless the row covers the buyer territory
    if kind == LICENSE:
        tp += [
            (rf"G {has}(?:exclusively )?(?:licensed|licenses|out-licensed|out-licenses|licenced|licences) "
            rf"(?:its )?{obj}{_PLACE} to E{_PLACE}{_MONEY_TAIL}"),  # "its": the grantor's own program
            rf"G {has}(?:granted|grants) E {rights_obj}{_PLACE}{_MONEY_TAIL}",
            rf"(?:the|this) (?:license |licence )?agreement (?:granted|grants) E {rights_obj}{_PLACE}",
            (rf"E {has}(?:exclusively )?(?:in-licensed|in-licenses|licensed|licenses) {obj}{_PLACE}(?: from G)?"
            rf"{_PLACE}{_MONEY_TAIL}"),
            (rf"E {has}(?:obtained|obtains|acquired|acquires|received|receives|secured|secures|gained|gains) "
            rf"{rights_obj}{_PLACE}(?: from G)?{_PLACE}{_MONEY_TAIL}"),
            # the signing-day sentence, only after "under the terms of the agreement" (review R1v12 UC2)
            (rf"under the terms of (?:the|this) (?:license |licence )?agreement ,? E will (?:receive|obtain|be granted) "
             rf"{rights_obj}{_PLACE}{_MONEY_TAIL}"),
            rf"{_PROGRAM} (?:is|was|has been) (?:exclusively )?licensed(?: by G)? to E{_PLACE}{_MONEY_TAIL}",
        ]
        t += [
            (rf"G and E {has}(?:today )?(?:entered into|signed|executed|enter into|sign|announced|announce) an? "
            rf"(?:exclusive )?(?:R )?"
            rf"(?:license|licence|licensing|license and collaboration|collaboration and license) {agreement}"
            rf"(?: (?:for|covering|to (?:{_DEV_LIST})) {_PROGRAM})?{_MONEY_TAIL}"),
            (rf"G {has}(?:today )?(?:entered into|signed|executed|announced) an? (?:exclusive )?(?:R )?(?:license|licence|licensing) "
             rf"{agreement} with E (?:for|covering|on) (?:the (?:development|commercialization|development and "
             rf"commercialization|research , development and commercialization) of )?{_PROGRAM}{_MONEY_TAIL}"),
            (rf"E {has}(?:today )?(?:entered into|signed|executed|announced) an? (?:exclusive )?(?:R )?(?:license|licence|licensing) "
             rf"{agreement} with G (?:for|covering|on) (?:the (?:development|commercialization|development and "
             rf"commercialization|research , development and commercialization) of )?{_PROGRAM}{_MONEY_TAIL}"),
        ]
    elif kind in (OPTION, CO_PROMOTION_OPTION):
        # never "an option to acquire NB-7": that is an option over the whole program (review R1v12 ACQ-OPT)
        what = (r"(?:an? (?:exclusive )?option to (?:license|in-license|obtain|co-promote) "
                rf"(?:{rights_to})?{_PROGRAM}|an? (?:exclusive )?option (?:on|over|for) {_PROGRAM})")
        if kind == CO_PROMOTION_OPTION:
            what = (rf"(?:an? (?:exclusive )?option to co-promote {_PROGRAM}|an? co-promotion option(?: (?:on|over|"
                    rf"for) {_PROGRAM})?)")
        tp += [
            rf"G {has}(?:granted|grants) E {what}{_PLACE}{_MONEY_TAIL}",
            (rf"E {has}(?:obtained|obtains|received|receives|secured|secures|acquired|acquires) {what}{_PLACE}"
             rf"(?: from G)?{_PLACE}{_MONEY_TAIL}"),
        ]
        t += [
            (rf"G and E {has}(?:entered into|signed|executed) an? (?:exclusive )?(?:option|option and license|"
            rf"co-promotion option) {agreement}(?: (?:for|covering) {_PROGRAM})?{_MONEY_TAIL}"),
        ]
    elif kind == OPTION_EXERCISED:
        tp += [
            (rf"E {has}exercised (?:its|the|an|their) (?:exclusive )?(?:R )?option(?: to (?:license|in-license|"
            rf"obtain) (?:{rights_to})?{_PROGRAM}| (?:on|over|for) {_PROGRAM})?{_PLACE}(?: from G)?{_PLACE}"
            rf"{_MONEY_TAIL}"),
            (rf"(?:the|E_s) (?:exclusive )?(?:R )?option(?: to (?:license) (?:{rights_to})?{_PROGRAM}| (?:on|over|for) "
            rf"{_PROGRAM})? (?:was|has been) exercised(?: by E)?"),
        ]
    elif kind == CO_DEVELOPMENT:
        t += [
            (rf"G and E {has}(?:entered into|signed|executed|formed) an? (?:R )?(?:co-development|collaboration|"
            rf"partnership|joint development|co-development and co-commercialization|collaboration and license) "
            rf"(?:{agreement} )?(?:(?:for|covering|on) {_PROGRAM}|to (?:co-develop|jointly develop|develop) {_PROGRAM})?"),
            rf"G and E (?:co-develop|co-developed|jointly develop|jointly developed) {_PROGRAM}",
        ]
    if kind in (TERMINATION, RIGHTS_RETURNED):  # a termination and a return are two words for one ending
        t += _endings(allp)
    elif kind == OPTION_LAPSED:
        # an option to acquire that lapsed leaves nothing held, whatever it covered
        opt = (rf"(?:exclusive )?(?:R )?option(?: to (?:license|acquire|in-license|obtain) (?:{rights_to})?{_PROGRAM}|"
               rf" (?:on|over|for|to) (?:(?:the )?(?:R )?rights (?:to|for|of) )?{_PROGRAM})?")
        t += [
            rf"(?:the|E_s|its) {opt} {has}(?:lapsed|expired)(?: unexercised)?",
            rf"E (?:declined|elected not|chose not|decided not) to exercise (?:its|the) {opt}",
            rf"E did not exercise (?:its|the) {opt}",
            rf"E (?:let|allowed) (?:its|the) {opt} (?:to )?(?:lapse|expire)",
            rf"E (?:declined|elected not|chose not|decided not) to take up (?:the |its )?(?:R )?rights (?:to|for|of) {_PROGRAM}",
        ]
    elif kind == ACQUISITION:
        whole = r"(?:all (?:of )?(?:the )?(?:issued and )?outstanding (?:shares|stock|equity) of |)"
        price = r"(?: for N(?: per share)?(?: in cash)?(?: ,? or (?:approximately )?N(?: in total)?)?)?"
        t += [
            (rf"E {has}(?:acquired|(?:completed|completes|closed|closes) (?:its |the )?(?:acquisition|purchase) of)"
             rf" {whole}G{price}"),
            rf"G (?:was|has been) acquired by E{price}",
            rf"E {has}(?:completed|completes|closed|closes) (?:its |the )?tender offer for {whole}G{price}",
            rf"E (?:today )?(?:announced|announces) (?:the )?(?:completion|closing) of (?:its|the) acquisition of G{price}",
        ]
    # a quote that is only the row's rights ("China rights", "exclusive U.S. rights to NB-7")
    tp.append(rf"(?:the |{allp})?(?:exclusive |sole )?(?:R )?rights(?: (?:to|for|of) {_PROGRAM})?")
    return tuple((re.compile(_frame(c.replace("G and E", "(?:G and E|E and G)"))), place)
                 for group, place in ((t, False), (tp, True)) for c in group)


def _template_text(slots: Slots, descriptors: frozenset[str]) -> str:
    text = fold_descriptions(slots, descriptors)
    # "G today announced that it has licensed ..." : the pronoun is the announcing party
    text = re.sub(r"^((?:D , |on D , )?(G|E|G and E|E and G)(?: today)? (?:announced|announces|said|says)(?: that)?) "
                  r"(?:it|they)(?= )", lambda m: f"{m.group(1)} {m.group(2)}", text)
    text = re.sub(r" ,(?= |$)", " ,", text).strip()
    return re.sub(r"\s+", " ", text)


@dataclass(frozen=True)
class TemplateRead:
    ok: bool
    why: str | None = None


def read_clause(slots: Slots, kind: str, own: frozenset[str], buyer: frozenset[str], as_of: date | None,
                row_day: date | None, descriptors: frozenset[str]) -> TemplateRead:
    """Whether a clause, already in slots, is one of the templates for ``kind`` and its slots fit the row."""
    why = date_problem(slots.periods, as_of, row_day)
    if why:
        return TemplateRead(False, why)
    text = _template_text(slots, descriptors)
    if kind != ACQUISITION and any(rx.match(text) or rx.match(text.replace(" ,", "")) for rx in _retention()):
        return TemplateRead(True)  # the grantor keeps rights, wherever they are
    for regions in slots.places:
        if regions is None:
            return TemplateRead(False, "names a territory DealScreen cannot read")
        if not regions <= own:
            extra = "/".join(sorted(regions - own))
            return TemplateRead(False, f"names {extra}, which the row's own territory ({'/'.join(sorted(own)) or 'unstated'}) "
                                       "does not cover")
    all_ok = bool(own) and buyer <= own
    placed = "R" in text.split()
    for rx, needs_place in _templates(kind, all_ok=all_ok):
        if rx.match(text) or rx.match(text.replace(" ,", "")):
            if needs_place and not all_ok and not placed:
                return TemplateRead(False, ("grants rights without naming a place, which reads as the whole program; "
                                            f"the row's own territory is {'/'.join(sorted(own)) or 'unstated'}"))
            return TemplateRead(True)
    if slots.capitalised:
        names = ", ".join(dict.fromkeys(slots.capitalised))
        return TemplateRead(False, f"names {names}, which is not a party to the row, the program's company, the program "
                                   "or a place in the row's territory, so it may hold rights the row does not show")
    return TemplateRead(False, "is not one of the sentences DealScreen reads as restating the row")


__all__ = ["KNOWN_MARKS", "PARTY_MARKS", "Slots", "TemplateRead", "descriptor_words", "read_clause", "to_slots"]
