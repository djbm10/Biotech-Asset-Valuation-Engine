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


__all__ = ["POLICY", "QUALIFIERS", "qualified_indication"]
