"""The plain forms a rights text may take beside a clear rights position (cycle R1, revision 6; review R1v5 §13).

Revision 5's gate blocked what its reader marked as contrary or unread, and passed the rest. Review R1v5 showed the
reader marking wrong readings as understood: a date read as a program code ("Available 2H27"), another party's offer
("The licensee is seeking a partner"), a U.S. grant erased as a party name ("with an option to U.S. rights"). The
gate now inverts the default: beside a clear position, a rights text counts as consistent only if every clause has
one of the forms below. Anything else keeps the program out of the top tiers, quoted and cited.

- a placeholder ("not reported", "N/A") or a bare no-grant phrase ("unpartnered", "no licensees", "not licensed in
  the U.S.");
- an offer in plain present words, with no digits, no "to ..." and no party but the program's company: "U.S.
  rights available", "seeking a co-development partner", "Ex-China rights available", "Acme Bio is open to
  partnering". A role noun ("partner", "licensee", "collaborator") may only be what is sought, never who seeks;
- the company keeping the rights: "rights retained", "Acme Bio retains all rights outside Greater China",
  "wholly owned by Acme Bio";
- a return to the company: "U.S. rights returned to Acme Bio (2024)", "Acme Bio regained U.S. rights". A return to
  anyone else, or to no one named, is not one;
- a grant over named places other than the U.S. only: "licensed in Greater China", "out-licensed for Japan only".

"The company" means the landscape company, by name (``same_company``) or as "the company"; "we" and "it" count only
in a text of one clause (review R1v6 PF2). Places are read on the text as written, before it is lower-cased, and
compared with the buyer territory, not with the U.S. (PF1, PF4): a grant passes only if every place in the clause is
outside the buyer territory, and an "ex-" or "outside" place only if it is outside the buyer territory too. A clause
with a note in parentheses or brackets is never a plain form (PF3); a year, an "ex-" place and a plural "(s)" are not
notes. The forms are word patterns, not facts: a text in one of them still says only what its source says.
"""

from __future__ import annotations

import re
from datetime import date

from bve.dealscreen.rights_reader import _NEGATED_GRANT, _NO_GRANT, _PLACEHOLDER, _TRIVIAL, _clauses
from bve.dealscreen.rights_territory import (
    GENERIC_NAME_WORDS,
    _is_region,
    regions_named,
    same_company,
)

#: Places after "ex-", "outside" or "excluding" ("Ex-China rights") become one token, kept only for a place the
#: territory reader knows that is not the U.S.
_EXCLUDED_PLACE = re.compile(r"\b(?:ex-?\s*|outside\s+(?:of\s+)?|excluding\s+|other than\s+)(?:the\s+)?"
                             r"(?P<place>[a-z][a-z .&-]*?)(?=\s+(?:rights?|territor\w*|markets?|commercial|"
                             r"development|available)\b|\s*$|\s*,)", re.IGNORECASE)
_GENERIC_SUBJECT = frozenset({"the company", "company"})
#: Pronoun subjects: the company only when the text has one clause, so "it" cannot point at a party named before.
_PRONOUN_SUBJECT = frozenset({"we", "it"})
US_ONLY = frozenset({"US"})
#: Parentheticals that are not notes: a year, an "ex-" place, a plural "(s)".
_NOT_A_NOTE = re.compile(r"\(\s*(?:(?:in\s+)?(?:19|20)\d{2}|(?:ex-?\s*|excluding\s+|outside\s+(?:of\s+)?)"
                         r"[A-Za-z][A-Za-z .&-]*|s)\s*\)", re.IGNORECASE)
_NOTE = re.compile(r"[()\[\]]")
_SUBJECT_VERB = re.compile(r"^(?P<who>.+?)\s+(?P<verb>is|are|remains|has|have|seeks|retains|has retained|holds|"
                           r"owns|keeps|regained|reacquired)\b\s*(?P<rest>.*)$")
_SEEK = frozenset({"seeking", "seeks", "seek", "looking", "search"})
_ROLE = frozenset({"partner", "partners", "licensee", "licensees", "collaborator", "collaborators"})
#: Every word a plain offer may contain. No "to", no digits, no "product", no buyer or acquirer.
_OFFER_WORDS = frozenset({
    "available", "availability", "seeking", "seeks", "seek", "sought", "looking", "search", "open", "for", "yes",
    "partner", "partners", "partnership", "partnerships", "partnering", "licensee", "licensees", "licensing",
    "license", "licence", "out-licensing", "out-license", "outlicensing", "co-development", "codevelopment",
    "co-commercialization", "co-commercialisation", "collaboration", "collaborations", "collaborator",
    "collaborators", "commercialization", "commercialisation", "development", "exclusive", "non-exclusive", "new",
    "potential", "strategic", "rights", "right", "program", "programme", "asset", "candidate", "compound", "us",
    "worldwide", "global", "globally", "territories", "territory", "markets", "all", "the", "a", "an", "of", "and",
    "in", "is", "are", "remains", "currently", "now", "actively", "opportunity", "opportunities", "deal", "deals",
    "its", "our", "exregion", ":", "or", "discussions", "discussion", "offers", "co-promotion", "copromotion",
    "out-licence"})
#: "open to partnering" is an offer; "open to 3SBio" names a party.
_OPEN_TO = re.compile(r"\bopen to (?=(?:a |new |potential |strategic )?(?:partner|licens|out-licens|collaborat|"
                      r"co-?(?:promot|develop|commerciali)|discussions|offers|deals?\b))")
_CORE = frozenset({"available", "seeking", "seeks", "seek", "sought", "looking", "open", "opportunity"})
_TOKEN = re.compile(r"[a-z][a-z'’&\-]*|\d+|[:?=()]")
_YEAR = r"(?:\s*\(?\s*(?:in\s+)?(?P<year>(?:19|20)\d{2})\s*\)?)?"
_RIGHTS = r"(?:(?:the\s+)?(?:(?:us|global|worldwide|all|commercial|full|exregion)\s+)*rights?)"
_RETURNED = re.compile(rf"^{_RIGHTS}\s+(?:were\s+|have\s+been\s+|has\s+been\s+)?(?:returned|reverted)\s+to\s+"
                       rf"(?P<who>.+?){_YEAR}$")
_REGAINED = re.compile(rf"^(?P<who>.+?)\s+(?:regained|reacquired)\s+{_RIGHTS}{_YEAR}$")
#: Places the company may keep rights in: the U.S., the rest of the world, or both (review R1v8 usefulness).
_KEPT_PLACE = r"(?:the\s+)?(?:us|u\.s\.?|united states|rest of (?:the )?world|row|exregion)"
_KEPT_PLACES = rf"{_KEPT_PLACE}(?:\s*(?:,|and|,\s*and)\s*{_KEPT_PLACE})*"
_RETAINS = re.compile(rf"^(?P<who>.+?)\s+(?:retains?|ha(?:s|ve) retained|holds?|owns?|keeps?)\s+(?:all\s+|full\s+|the\s+)?"
                      rf"{_RIGHTS}(?:\s+(?:to the (?:program|asset)|exregion|(?:in|for)\s+{_KEPT_PLACES}))?$")
_RETAINED = re.compile(rf"^(?:{_RIGHTS}\s+(?:are\s+|is\s+)?)?retained(?:\s+by\s+(?P<who>.+))?$")
_OWNED = re.compile(r"^(?:(?:wholly|fully)\s+)?owned(?:\s+by\s+(?P<who>.+))?$")
#: A grant over named places other than the U.S., to a named party or none: "licensed in China only", "exclusive
#: China license to ChinaCo", "licensed to ChinaCo for Japan".
#: Matched on the clause as written (case kept), so the party span can be checked as a name (review R1v7 PLACE).
_OTHER_PLACES = (
    re.compile(r"^(?:exclusive(?:ly)?\s+)?(?:(?:out-?)?licen[cs]ed|partnered)\s+(?:in|for)\s+(?:the\s+)?(?P<place>.+?)"
               r"(?:\s+only)?(?:\s+to\s+(?P<party>.+))?$", re.IGNORECASE),
    re.compile(r"^(?:an?\s+)?(?:exclusive\s+)?(?P<place>.+?)\s+(?:out-?)?licen[cs]e(?:\s+(?:to|with)\s+(?P<party>.+))?$",
               re.IGNORECASE),
    re.compile(r"^(?:exclusive(?:ly)?\s+)?(?:out-?)?licen[cs]ed\s+to\s+(?P<party>.+?)\s+(?:in|for)\s+(?:the\s+)?"
               r"(?P<place>.+?)(?:\s+only)?$", re.IGNORECASE),
)
#: A party written as a name and nothing else: capitalised words, digits and corporate punctuation ("Chinaco
#: Pharma", "Acme Bio Co., Ltd."). A lower-case word, a dash or a second "to"/"in" is more text, which may name
#: another place or party ("... and in the Americas to X", "... - X has the rest"), so it is not a name.
_NAME_TOKEN = (r"(?:[A-Z0-9][A-Za-z0-9.&'’]*(?:-[A-Za-z0-9.&'’]+)*|(?:plc|ltd|inc|gmbh|llc|co|sa|ag|bv|nv|spa|srl|kk)"
               r"\.?),?")
#: "&" may join two name words ("L & M Bio"); the word "and" may not (review R1v8 usefulness).
_PARTY_NAME = re.compile(rf"{_NAME_TOKEN}(?:\s+(?:&\s+)?{_NAME_TOKEN})*")
#: Capitalised words that name a place the territory reader does not know, inside what looks like a name.
_PLACE_WORD = re.compile(r"\b(?:americas?|american|europe(?:an)?|asian?|africa(?:n)?|pacific|world|worldwide|global|"
                         r"row|international|latam|apac|emea|nordics?|oceania|australia|states)\b", re.IGNORECASE)


#: Words that join, place or condition a clause, read in any letter case: inside a party span they mean more text
#: ("AND ELSEWHERE TO X", "And In California To X", "X Has ROFN", "Subject To X Approval"; review R1v8 PN-CASE,
#: PN-WORD). A name containing one ("Kappa and Kappa") is refused too: an over-caution cost.
_NOT_IN_NAME = frozenset({
    "and", "or", "in", "to", "the", "for", "with", "by", "from", "at", "on", "into", "under", "via", "has", "have",
    "had", "holds", "hold", "held", "gets", "got", "keeps", "retains", "owns", "is", "are", "was", "were", "be",
    "rest", "remaining", "other", "others", "elsewhere", "stateside", "abroad", "overseas", "territory",
    "territories", "region", "regions", "market", "markets", "country", "countries", "rofn", "rofr", "rofo", "first",
    "look", "opt", "opt-in", "option", "options", "right", "rights", "negotiation", "refusal", "subject", "pending",
    "consent", "approval", "approve", "until", "unless", "except", "excluding", "but", "after", "before", "if",
    "only"})


def _party_ok(party: str | None) -> bool:
    name = re.sub(r"\s+only$", "", (party or "").strip(" ,"), flags=re.IGNORECASE)
    if not name:
        return True
    words = {w.strip(".,'’").casefold() for w in name.split()}
    if "&" in name and {w.strip(".,'’").casefold() for w in name.split("&", 1)[0].split()} & GENERIC_NAME_WORDS:
        return False  # "&" after a company word joins two companies ("Chinaco Pharma & Tessaly Pharma")
    return (bool(_PARTY_NAME.fullmatch(name)) and not regions_named(name) and not _PLACE_WORD.search(name)
            and not _RIGHTS_TEXT.search(name) and not words & _NOT_IN_NAME)


def _is_company(who: str | None, company: str | None, alone: bool = True) -> bool:
    """``alone``: the text has one clause, so a pronoun can only mean the company."""
    if who is None:
        return True
    who = who.strip(" ,")
    if who in _PRONOUN_SUBJECT:
        return alone
    return who in _GENERIC_SUBJECT or bool(company and same_company(who, company))


def _mark_places(clause: str, territory: frozenset[str]) -> str:
    """Run on the text as written: "ex-US" is a place only in capitals."""
    def mark(m: re.Match[str]) -> str:
        place = m["place"].strip()
        return " exregion " if _is_region(place) and not regions_named(place) & territory else m.group(0)

    return " ".join(_EXCLUDED_PLACE.sub(mark, clause).split())


def _has_note(clause: str, company: str | None) -> bool:
    """A parenthesis or bracket that is not a year, an "ex-" place, a plural or part of the company's own name."""
    text = clause
    if company:
        text = re.sub(re.escape(company), " ", text, flags=re.IGNORECASE)
    return bool(_NOTE.search(_NOT_A_NOTE.sub(" ", text)))


def _offer(clause: str, company: str | None, alone: bool = True) -> bool:
    found = _SUBJECT_VERB.match(clause)
    rest = clause
    if found and found["verb"] in {"is", "are", "remains", "seeks", "has", "have"}:
        if not _is_company(found["who"], company, alone):
            return False
        rest = ("seeks " if found["verb"] == "seeks" else "") + found["rest"]
    tokens = _TOKEN.findall(_OPEN_TO.sub("open for ", rest))
    if not tokens or not set(tokens) & _CORE:
        return False
    sought = False
    for i, token in enumerate(tokens):
        if token not in _OFFER_WORDS:
            return False
        if token in _SEEK:
            sought = True
        if token in _ROLE and not sought and not (i + 1 < len(tokens) and tokens[i + 1] == "sought"):
            return False
    return True


def _year_ok(found: re.Match[str], as_of: date | None) -> bool:
    year = found.groupdict().get("year")
    return not (year and as_of and int(year) > as_of.year)


def _clause_form(clause: str, company: str | None, as_of: date | None, territory: frozenset[str],
                 alone: bool) -> str | None:
    if _has_note(clause, company):
        return None
    written = _mark_places(_NOT_A_NOTE.sub(lambda m: m.group(0)[1:-1], clause).strip(" .,"), territory)
    named = regions_named(written)  # as written: "U.S." after a party name is still the U.S. (review R1v6 PF1)
    text = written.casefold()
    if _PLACEHOLDER.fullmatch(text) or _NO_GRANT.fullmatch(text):
        return "no grant stated" if not named or named <= territory else None
    rest = _NEGATED_GRANT.sub(" ", text)
    if rest != text and all(w in _TRIVIAL for w in _TOKEN.findall(rest)):
        return "no grant stated"
    for pattern in (_RETURNED, _REGAINED):
        found = pattern.fullmatch(text)
        if found and found["who"] not in _PRONOUN_SUBJECT and \
                _is_company(found["who"], company, alone) and _year_ok(found, as_of):
            return "rights returned to the company"
    for pattern in (_RETAINS, _RETAINED, _OWNED):
        found = pattern.fullmatch(text)
        if found and _is_company(found.groupdict().get("who"), company, alone):
            return "rights kept by the company"
    for pattern in _OTHER_PLACES:
        found = pattern.fullmatch(written)
        if found and _is_region(found["place"]) and named and not named & territory and \
                _party_ok(found.groupdict().get("party")):
            return "a grant over other places only"
    if _offer(text, company, alone):
        # An offer that names places must cover the buyer territory (review R1v7 QT).
        return "an offer" if not named or territory <= named else None
    return None


def plain_form(text: str | None, company: str | None, as_of: date | None = None,
               territory: frozenset[str] = US_ONLY) -> str | None:
    """The form a rights text has when every clause is one of the plain forms (module docstring), else None. An
    empty text is a placeholder. ``territory``: the buyer territory (region codes)."""
    clauses = _clauses((text or "").replace("[", "(").replace("]", ")"))
    if not clauses:
        return "no grant stated"
    forms = [_clause_form(c, company, as_of, territory, len(clauses) == 1) for c in clauses]
    if any(f is None for f in forms):
        return None
    return "; ".join(dict.fromkeys(f for f in forms if f))


#: Words that make a Partnerships or Geographic Notes value a rights text rather than a list of names.
_RIGHTS_TEXT = re.compile(
    r"licen[cs]|\brights?\b|\boption|co-?promot|co-?develop|co-?commerciali|commerciali[sz]|territor|exclusiv|"
    r"worldwide|\bglobal\b|\bex-|acqui|royalt|milestone|distribut|\bmarket|return|revert|terminat|\bpartnered\b|"
    r"\bpartnership\b|collaborat|\bdeal\b|\bagreement\b|\bsold\b|\bassigned\b|\btransferred\b|\bown(?:s|ed|er|ership)\b|"
    r"\bbought\b|\bpurchas|\bmerge|\bspun\b|spin-?off|\bsubsidiar|\bparent\b|\bholds?\b|\bheld\b", re.IGNORECASE)


def is_rights_text(text: str | None) -> bool:
    """Whether a Partnerships value says something about rights (a deal, a territory, a right), rather than only
    naming organisations: "Exclusive U.S. license to Acme" is; "Acme Pharma; Beta Bio" is not."""
    value = text or ""
    return bool(_RIGHTS_TEXT.search(value) or regions_named(value))


__all__ = ["US_ONLY", "is_rights_text", "plain_form"]
