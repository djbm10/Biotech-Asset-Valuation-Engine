"""Read qualified indication names the frozen NCIt authority cannot identify (DealScreen policy v1).

Vendor exports often write a disease with a severity or extent qualifier
("Generalized Myasthenia Gravis", "Myasthenia Gravis, Generalized", "... (gMG)") that the frozen
S&E NCIt subset does not hold as a concept. The S&E gate then correctly answers UNKNOWN.

This module adds one narrow, disclosed reading: ``<qualifier> <disease>`` is a form of
``<disease>`` when the qualifier is in a closed list and ``<disease>`` identifies exactly one NCIt
concept. Every reading is returned with the observed text and rule, so the screen can show it.

It never applies when the full name already resolves, never strips a qualifier outside the list,
and only ever reads towards the parent, so a request for a subtype is not satisfied by it. The
S&E authority and gate are unchanged.
"""

from __future__ import annotations

import re

POLICY = "DealScreen qualified-indication reading v1"

#: Severity / extent qualifiers where "<q> X" is always a form of X. Deliberately excluded:
#: acute, ocular, active (active vs latent infection), population terms (adult, pediatric:
#: a different regulatory and commercial target), serostatus terms, and any negating or
#: relational prefix (non-, anti-, post-).
QUALIFIERS: tuple[str, ...] = (
    "moderate to severe", "moderate-to-severe",
    "generalized", "generalised", "refractory", "relapsed", "relapsing", "recurrent",
    "chronic", "severe", "moderate", "mild",
)

#: A reading must land on a specific disease, never a generic node (review A1-2): the NCIt
#: concept must sit at least this deep, and the remainder must not be a generic word.
MIN_CONCEPT_DEPTH = 6
GENERIC_REMAINDERS = frozenset({
    "disease", "diseases", "disorder", "disorders", "infection", "infections", "cancer", "cancers",
    "tumor", "tumors", "tumour", "tumours", "neoplasm", "neoplasms", "condition", "conditions",
    "illness", "syndrome", "pain", "inflammation",
})

_ACRONYM = re.compile(r"\s*\(([A-Za-z]{2,6})\)\s*$")


def _resolve(name: str) -> str | None:
    from bve.se.ontology.indication_compatibility import _authority, disease_id

    code = disease_id(name)
    return _authority()["nodes"][code]["label"] if code else None


def _depth(code: str, seen: frozenset[str] = frozenset()) -> int:
    from bve.se.ontology.indication_compatibility import _authority

    parents = [p for p in _authority()["nodes"].get(code, {}).get("parents", []) if p not in seen]
    return 0 if not parents else 1 + min(_depth(p, seen | {code}) for p in parents)


def _specific(name: str) -> str | None:
    """The NCIt label for a specific (non-generic, deep enough) disease name, else None."""
    from bve.se.ontology.indication_compatibility import disease_id

    if name.casefold().strip() in GENERIC_REMAINDERS:
        return None
    code = disease_id(name)
    if code is None or _depth(code) < MIN_CONCEPT_DEPTH:
        return None
    return _resolve(name)


def _strip_qualifier(text: str) -> tuple[str, str] | None:
    folded = text.casefold()
    for q in QUALIFIERS:
        if folded.startswith(q + " "):
            return q, text[len(q) + 1:].strip()
        if folded.endswith(", " + q):
            return q, text[: -len(q) - 2].strip()
    return None


def qualified_indication(text: str) -> dict[str, str] | None:
    """The parent reading of a qualified indication name, or None."""
    if not text or not text.strip() or _resolve(text):
        return None
    candidate = text.strip()
    acronym = _ACRONYM.search(candidate)
    if acronym:
        candidate = candidate[: acronym.start()].strip()
        if _resolve(candidate):
            return None  # a plain acronym gloss of a resolvable name is not a qualifier reading
    stripped = _strip_qualifier(candidate)
    if stripped is None:
        return None
    qualifier, rest = stripped
    label = _specific(rest)
    if label is None:
        return None
    return {
        "observed": text,
        "read_as": label,
        "qualifier": qualifier,
        "rule": f"{POLICY}: '{qualifier}' qualifier read as a form of the NCIt concept",
    }


POLICY_V2 = "DealScreen indication reading v2"
#: Disease-extent qualifiers ("locally advanced unresectable X" is a form of X). Stacked freely.
EXTENT_QUALIFIERS: tuple[str, ...] = ("locally advanced", "advanced", "metastatic", "unresectable",
                                      "inoperable")
_INNER_ACRONYM = re.compile(r"\s*\([A-Za-z]{2,6}\)")
#: "<marker>-positive X", "<marker>+ X", "<marker>-high X", "<marker>-expressing X": a biomarker
#: subset of X. "negative" subsets are forms of X too.
_BIOMARKER_PREFIX = re.compile(r"^(?P<marker>[\w.\-/]+?)(?:[\s-]+(?:positive|negative|high|low|expressing)|\+)\s+",
                               re.IGNORECASE)
#: The marker must look like a gene/protein symbol (a digit, or >= 2 capitals), so "Gram-negative" or
#: "Triple-negative" are not read as biomarker subsets (review C1-5).
_MARKER_SHAPE = re.compile(r"\d|[A-Z].*[A-Z]")


def _strip_all(text: str) -> tuple[str, list[str]]:
    """Strip leading severity/extent qualifiers repeatedly; return the remainder and what was removed."""
    removed: list[str] = []
    current = text.strip()
    while True:
        folded = current.casefold()
        hit = next((q for q in (*EXTENT_QUALIFIERS, *QUALIFIERS) if folded.startswith(q + " ")), None)
        if hit is None:
            return current, removed
        removed.append(hit)
        current = current[len(hit) + 1:].strip()


def _read_part(part: str) -> tuple[str, list[str]] | None:
    """A specific NCIt label for one (uncoordinated) phrase, with the steps applied."""
    if (label := _specific(part)) is not None:
        return label, []
    rest, removed = _strip_all(part)
    if removed and (label := _specific(rest)) is not None:
        return label, removed
    return None


def _coordinated(text: str) -> list[str]:
    """'A or B <head>' -> ['B <head>', 'A <head>']; 'X or Cancer' -> ['X']; qualifier coordination
    ('Locally Advanced or Metastatic X') -> ['X'] (review C1-4).

    The shared head is the LONGEST suffix of the right phrase that makes 'A <suffix>' a specific
    concept, so a suffix never cuts into the head ('Small Cell or Non-Small Cell Lung Cancer' gives
    'Small Cell Lung Cancer', not a site-less concept). Each candidate must still resolve specifically.
    """
    pieces = [p.strip() for p in re.split(r"\s+or\s+", text, flags=re.IGNORECASE) if p.strip()]
    if len(pieces) != 2:
        return [text]
    left, right = pieces
    if right.casefold() in GENERIC_REMAINDERS:
        return [left]
    qualifier_words = {*EXTENT_QUALIFIERS, *QUALIFIERS}
    if left.casefold() in qualifier_words:
        rest, _ = _strip_all(right)
        return [rest]
    words = right.split()
    out = [right]
    for k in range(len(words) - 1, 0, -1):
        candidate = f"{left} {' '.join(words[-k:])}"
        if _specific(candidate) is not None:
            out.append(candidate)
            break
    return out


def indication_readings(text: str) -> list[dict[str, str]]:
    """All disclosed NCIt readings of an indication name the authority cannot identify (v1 + v2).

    v2 adds: inline acronyms removed ("Junction (GEJ) Adenocarcinoma"), a biomarker-subset prefix
    read as the disease ("CLDN18.2-positive X" -> X), stacked extent qualifiers ("locally advanced
    unresectable X" -> X), and two-way coordination ("Gastric or GEJ adenocarcinoma" -> both). Each
    reading must land on a specific concept (same depth and generic-word guards as v1).
    """
    if not text or not text.strip() or _resolve(text):
        return []
    v1 = qualified_indication(text)
    if v1 is not None:
        return [v1]
    steps: list[str] = []
    candidate = _INNER_ACRONYM.sub("", text).strip()
    if candidate != text.strip():
        steps.append("acronym removed")
    marker = _BIOMARKER_PREFIX.match(candidate)
    if marker and _MARKER_SHAPE.search(marker.group("marker")):
        candidate = candidate[marker.end():].strip()
        steps.append(f"biomarker subset '{marker.group(0).strip()}'")
    readings: dict[str, dict[str, str]] = {}
    for part in _coordinated(candidate):
        result = _read_part(part)
        if result is None:
            continue
        label, removed = result
        detail = steps + ([f"qualifiers {removed}"] if removed else []) + (
            ["coordination expanded"] if part not in (candidate,) else [])
        if not detail:
            continue  # nothing was read beyond what the authority already knows
        readings.setdefault(label, {"observed": text, "read_as": label, "qualifier": "; ".join(detail),
                                    "rule": f"{POLICY_V2}: {'; '.join(detail)}"})
    return list(readings.values())


__all__ = ["EXTENT_QUALIFIERS", "POLICY", "POLICY_V2", "QUALIFIERS", "indication_readings",
           "qualified_indication"]
