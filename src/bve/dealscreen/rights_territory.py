"""Territory text and party names for rights evidence (cycle R1, rewritten after the R1 adversarial review).

A territory is read into coarse regions, or ``None`` when it cannot be read with confidence. ``None``
means "territory unstated": the caller treats it as a possible encumbrance and asks. The reader never
guesses towards "not covered":

- An exclusion ("excluding", "outside", "ex-", "other than", ...) subtracts only from its base: the
  words before it ("North America excluding Mexico" is North America less Mexico, never the world
  less North America). A base with no region ("ex-Greater China", "territories outside China") is the
  world.
- Any word the reader does not know ("Puerto Rico", "Asia", "co-promotion retained") makes the whole
  text unreadable. An unknown excluded place could be part of a known region, and an unknown base could
  be anything.
- "US" is read only as written in capitals ("US", "U.S.", "U.S", "USA"); lowercase "us" is a pronoun.
"""

from __future__ import annotations

import re

REGIONS = frozenset({"US", "CA", "EU", "UK", "JP", "CN", "HK", "MO", "TW", "KR", "ROW"})
GREATER_CHINA = frozenset({"CN", "HK", "MO", "TW"})

#: (pattern, regions, case_sensitive). Longest phrases first; each match is removed before the next.
_REGION_TERMS: tuple[tuple[str, frozenset[str], bool], ...] = (
    (r"greater china", GREATER_CHINA, False),
    (r"mainland china|china'?s mainland|china mainland|the prc|prc", frozenset({"CN"}), False),
    (r"china", frozenset({"CN"}), False),
    (r"hong kong", frozenset({"HK"}), False),
    (r"maca[ou]", frozenset({"MO"}), False),
    (r"taiwan", frozenset({"TW"}), False),
    (r"south korea|republic of korea|korea", frozenset({"KR"}), False),
    (r"japan", frozenset({"JP"}), False),
    (r"north america", frozenset({"US", "CA"}), False),
    (r"united states of america|united states", frozenset({"US"}), False),
    (r"U\.S\.A\.?|U\.S\.?|USA|US", frozenset({"US"}), True),
    (r"canada", frozenset({"CA"}), False),
    (r"europe", frozenset({"EU", "UK"}), False),
    (r"european union|eea|eu", frozenset({"EU"}), False),
    (r"united kingdom|great britain|uk", frozenset({"UK"}), False),
)
_EU5 = re.compile(r"(?<![A-Za-z])eu5(?![A-Za-z0-9])", re.IGNORECASE)
_WORLD = re.compile(r"(?<![A-Za-z])(worldwide|world-wide|world wide|global(ly)?|all (global )?territories|"
                    r"all countries|throughout the world)(?![A-Za-z])", re.IGNORECASE)
_REST_OF_WORLD = re.compile(r"(?<![A-Za-z])((?i:rest of (the )?world)|ROW)(?![A-Za-z])")
_EXCLUSION = re.compile(r"(?<![A-Za-z])(excluding|excludes|exclude|outside( of)?|except( for)?|other than|"
                        r"exclusive of|not including|with the exception of|ex-)", re.IGNORECASE)
#: Words that carry no territorial meaning in deal text. Anything else makes the text unreadable.
_FILLER = frozenset({
    "the", "of", "and", "or", "in", "for", "all", "its", "their", "territory", "territories", "region",
    "regions", "rights", "right", "basis", "only", "country", "countries", "including", "includes",
    "include", "but", "whole", "entire", "sar", "a", "an", "to", "on", "s", "mainland",
})


def _strip_regions(text: str) -> tuple[set[str], str]:
    """Regions named in ``text`` and the text with those names removed."""
    found: set[str] = set()
    rest = f" {text} "
    if _EU5.search(rest):  # France, Germany, Italy, Spain and the UK
        found |= {"EU", "UK"}
        rest = _EU5.sub(" ", rest)
    for pattern, regions, case_sensitive in _REGION_TERMS:
        flags = 0 if case_sensitive else re.IGNORECASE
        rx = re.compile(rf"(?<![A-Za-z.]){pattern}(?![A-Za-z])", flags)
        if rx.search(rest):
            found |= regions
            rest = rx.sub(" ", rest)
    return found, rest


def _unknown_words(text: str) -> list[str]:
    """Words the reader does not know. Single letters count too: a stray "U" or "S" left behind by an
    abbreviation the reader missed must make the text unreadable, not vanish (review R1v2 P)."""
    words = re.findall(r"[a-z]+", text.casefold())
    return [w for w in words if w not in _FILLER]


def _read_base(base: str, has_exclusion: bool) -> frozenset[str] | None:
    world = bool(_WORLD.search(base))
    rest_of_world = bool(_REST_OF_WORLD.search(base))
    regions, rest = _strip_regions(_REST_OF_WORLD.sub(" ", _WORLD.sub(" ", base)))
    if _unknown_words(rest):
        return None
    if world:
        return REGIONS
    if rest_of_world:  # "rest of world" means nothing without the list it is the rest of
        return REGIONS if has_exclusion else None
    if regions:
        return frozenset(regions)
    return REGIONS if has_exclusion else None  # "ex-China", "territories outside China"


def parse_territory(text: str | None) -> frozenset[str] | None:
    """Territory text -> covered regions, or None when it cannot be read with confidence."""
    if not text or not text.strip():
        return None
    clauses = [c for c in re.split(r"[;]", text) if c.strip()]
    if len(clauses) != 1:  # a second clause qualifies the first ("...; US co-promotion retained")
        return None
    clause = " ".join(clauses[0].replace("(", " , ").replace(")", " , ").split())
    match = _EXCLUSION.search(clause)
    base, excluded_text = (clause[: match.start()], clause[match.end():]) if match else (clause, "")
    covered = _read_base(base, has_exclusion=bool(match))
    if covered is None:
        return None
    if not match:
        return covered
    if _EXCLUSION.search(excluded_text) or re.search(r"(?i)\binclud", excluded_text):
        return None  # nested exclusions or re-inclusions: too complex to read safely
    excluded, rest = _strip_regions(excluded_text)
    if _unknown_words(rest):
        return None
    result = frozenset(covered - excluded)
    return result or None


def regions_named(text: str | None) -> frozenset[str]:
    """The regions a text names, without reading "worldwide" or "rest of world": which places a statement is
    about ("China rights available" names CN only)."""
    return frozenset(_strip_regions(text or "")[0])


# --- party names --------------------------------------------------------------------------------------

_SUFFIX = re.compile(
    r"\b(inc|incorporated|ltd|limited|co|company|corp|corporation|llc|plc|gmbh|s\.?a|n\.?v|b\.?v|"
    r"holdings?|group)\b\.?")


def party_key(name: str | None) -> str:
    """Comparable party name: case, punctuation, hyphens and generic corporate suffixes removed.
    "Acme KGaA" and "Acme & Co" stay distinct ("& co" reduces to "acme &"). "U.S." and "U.S.A." read as
    "us" and "usa" (review R1v4 G10: "Acme U.S., Inc." is Acme's U.S. affiliate, not "Acme U S")."""
    if not name:
        return ""
    low = re.sub(r"(?<![a-z])u\.\s?s\.\s?a\.?(?![a-z])", " usa ", name.casefold())
    low = re.sub(r"(?<![a-z])u\.\s?s\.?(?![a-z])", " us ", low)
    low = low.replace(",", " ").replace("-", " ")
    low = _SUFFIX.sub(" ", low)
    return " ".join(re.sub(r"[^\w&]+", " ", low).split())


#: Words that name a business line or a country, not a different company: "Acme" and "Acme Pharma US" are one.
#: One list for every name comparison (review R1v4: two lists gave two answers).
GENERIC_NAME_WORDS = frozenset({
    "pharma", "pharmaceutical", "pharmaceuticals", "bio", "biotech", "biotechnology", "bioscience", "biosciences",
    "biologics", "biopharma", "biopharmaceutical", "biopharmaceuticals", "therapeutics", "oncology", "medicines",
    "sciences", "development", "research", "holding", "us", "usa", "america", "americas", "japan", "europe", "china",
    "global", "international"})
_NOTE = re.compile(r"\(([^)]*)\)|\[([^\]]*)\]")


def split_note(name: str | None) -> tuple[str, str]:
    """A party name and the notes written beside it in parentheses or square brackets: ("Acme Pharma US, Inc.",
    "U.S. labeler per FDA label"). A note is content: a caller that compares only the name must report the note
    (review R1v4 A5: "Origin Bio (U.S. rights licensed to BigPharma Inc.)" names a third party in its note)."""
    text = name or ""
    notes = [(m.group(1) if m.group(1) is not None else m.group(2)).strip() for m in _NOTE.finditer(text)]
    return " ".join(_NOTE.sub(" ", text).split()), "; ".join(n for n in notes if n)


_CORPORATE_FORM = re.compile(r"(?<![A-Za-z])(?:inc|incorporated|ltd|limited|co|corp|corporation|llc|plc|gmbh|ag|"
                             r"s\.?a|n\.?v|b\.?v)(?![A-Za-z])\.?", re.IGNORECASE)


def _is_region(text: str) -> bool:
    found, rest = _strip_regions(text)
    return bool(found) and not _unknown_words(rest)


def drop_address(name: str) -> str:
    """A party name without an address written after its corporate form: "Acme Bio Co., Ltd., Lakeside, China" is
    "Acme Bio Co., Ltd.". Only a comma-separated tail after the corporate form whose items are single words and whose
    last item is a country or region the territory reader knows is dropped. Anything else ("Acme Inc., Beta Bio",
    "Acme Inc. / Beta Bio", "Acme GmbH, Germany") is kept, so a second party is never cut off (review R1v4 section 4:
    real legal names carry an address)."""
    text = name.strip()
    for match in _CORPORATE_FORM.finditer(text):
        tail = text[match.end():].strip()
        if not tail.startswith(","):
            continue
        items = [item.strip() for item in tail.rstrip(".").split(",")[1:]]
        if not items or not all(items):
            continue
        *places, region = items
        if all(re.fullmatch(r"[A-Za-z]+", place) for place in places) and _is_region(region):
            return text[: match.end()]
    return name


def same_company(a: str | None, b: str | None) -> bool:
    """Two party names for one company: equal after normalisation, or one is the other followed only by business-line
    or country words ("Acme" and "Acme Pharma US, Inc."). Only the names are compared: notes in parentheses or
    brackets are not (``split_note``), so a caller must report them. Any other extra word keeps the names apart
    ("Acme" and "Acme KGaA"; "Acme" and "Acme Partners"): a near-namesake is never read as the same company, so a
    holder it names is not silently absorbed (review R1v3 E2-holder)."""
    ka, kb = (party_key(drop_address(split_note(n)[0])) for n in (a, b))
    if not ka or not kb:
        return False
    short, long = sorted((ka, kb), key=len)
    return ka == kb or (long.startswith(f"{short} ") and set(long[len(short):].split()) <= GENERIC_NAME_WORDS)


def name_matches(declared: str, name: str | None) -> bool:
    """Whole-word match of a declared counterparty name inside a party name, after normalisation.
    "Ono" does not match "Sonoma"; "Example-Pharma Labs" matches "Example Pharma Labs Company"."""
    key, target = party_key(declared), party_key(name)
    if not key or not target:
        return False
    return re.search(rf"(?<!\w){re.escape(key)}(?!\w)", target) is not None


__all__ = ["GENERIC_NAME_WORDS", "GREATER_CHINA", "REGIONS", "drop_address", "name_matches", "parse_territory",
           "party_key", "regions_named", "same_company", "split_note"]
