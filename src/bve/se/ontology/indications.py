"""Controlled vocabulary for clinical indication concepts.

The ``strategy.indication`` gate compared registry condition strings for exact equality with
the query's leftover words. "relapsed or refractory B-cell lymphoma" compiled to four
independent literals, and "Relapsed/Refractory Diffuse Large B-cell Lymphoma" is none of
them, so every reference CD19 CAR-T was excluded from a CD19 lymphoma question
(``docs/se_parser_defects.md`` #3).

A disease phrase is one concept, and a condition satisfies it when it names the concept or a
subtype. A condition that names only an ancestor ("Lymphoma") cannot confirm or rule out the
subtype, so it is undetermined, not a match.

Frozen by ``docs/se_policies/indication_gate_semantics.md``. A change to any term is a
declared change.
"""

from __future__ import annotations

import re
import json
from functools import lru_cache
from pathlib import Path
from enum import Enum

B_CELL_LYMPHOMA = "INDICATION:B_CELL_LYMPHOMA"

#: Disease-status words recognised in a query phrase and not enforced: a registry condition
#: field does not reliably state disease status, so requiring it would exclude on missing data.
_QUALIFIERS = ("relapsed", "refractory", "recurrent", "r r")
_CONNECTORS = ("or", "and")

#: Phrases in a question that mean the concept, once qualifiers and connectors are removed.
_REQUEST_SURFACES: dict[str, tuple[str, ...]] = {
    B_CELL_LYMPHOMA: ("b cell lymphoma", "b cell non hodgkin lymphoma", "b cell nhl", "b nhl"),
}

#: The condition names the concept or one of its subtypes.
_MATCH_TERMS: dict[str, tuple[str, ...]] = {
    B_CELL_LYMPHOMA: (
        "b cell lymphoma", "lymphoma b cell", "b cell non hodgkin", "b cell nhl", "b nhl",
        "large b cell", "dlbcl", "lbcl", "follicular lymphoma", "lymphoma follicular",
        "mantle cell lymphoma", "lymphoma mantle cell", "marginal zone lymphoma",
        "lymphoma marginal zone", "malt lymphoma", "burkitt", "primary mediastinal", "pmbcl",
        "small lymphocytic lymphoma", "high grade b cell", "hgbl", "transformed follicular",
    ),
}

#: The condition names a sibling of the concept, which rules it out.
_DISJOINT_TERMS: dict[str, tuple[str, ...]] = {
    B_CELL_LYMPHOMA: (
        "hodgkin", "t cell lymphoma", "lymphoma t cell", "peripheral t cell", "cutaneous t cell",
        "mycosis fungoides", "sezary", "anaplastic large cell", "nk t cell",
    ),
}

#: The condition names an ancestor, which neither confirms nor rules out the concept.
_BROADER_TERMS: dict[str, tuple[str, ...]] = {
    B_CELL_LYMPHOMA: (
        "lymphoma", "non hodgkin", "nhl", "lymphoproliferative", "hematologic malignan",
        "hematological malignan", "haematolog", "b cell malignan", "b cell neoplasm",
    ),
}

#: Terms that are word prefixes rather than whole words.
_STEMS = ("malignan", "haematolog")


class ConditionMatch(str, Enum):
    MATCH = "MATCH"
    UNDETERMINED = "UNDETERMINED"
    NO = "NO"


def normalize(text: str) -> str:
    """Casefold, turn every non-alphanumeric into a space, collapse whitespace."""

    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.casefold()).split())


def _pattern(term: str) -> str:
    tail = "" if term.endswith(_STEMS) else r"\b"
    # "hodgkin" is a sibling only when it is not the tail of "non hodgkin".
    head = r"(?<!\bnon )" if term == "hodgkin" else ""
    return rf"{head}\b{re.escape(term)}{tail}"


def _has_any(normalized: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(_pattern(term), normalized) for term in terms)


def is_indication_concept(value: object) -> bool:
    return isinstance(value, str) and (
        value in _REQUEST_SURFACES or value.startswith("INDICATION:NCIT:")
    )


def resolve_indication_phrase(phrase: str) -> str | None:
    """The concept a query phrase names, or ``None`` when it is not exactly one surface."""

    words = normalize(phrase)
    for term in (*_QUALIFIERS, *_CONNECTORS):
        words = re.sub(rf"\b{term}\b", " ", words)
    remainder = " ".join(words.split())
    for concept, surfaces in _REQUEST_SURFACES.items():
        if remainder in surfaces:
            return concept
    codes = _diseases()["names"].get(normalize(phrase), [])
    return f"INDICATION:NCIT:{codes[0]}" if len(codes) == 1 else None


@lru_cache(maxsize=1)
def _diseases() -> dict:
    """Frozen NCIt 26.08e disease-typed view, including source digest and parent edges."""
    path = Path(__file__).resolve().parents[4] / "research/se_indication_semantics_v1/ncit_diseases.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=65536)
def _ancestors(code: str) -> frozenset[str]:
    nodes = _diseases()["nodes"]
    seen: set[str] = set()
    pending = [code]
    while pending:
        current = pending.pop()
        if current not in seen:
            seen.add(current)
            pending.extend(p for p in nodes.get(current, {}).get("parents", []) if p in nodes)
    return frozenset(seen)


@lru_cache(maxsize=1)
def _children() -> dict[str, set[str]]:
    children: dict[str, set[str]] = {}
    for code, node in _diseases()["nodes"].items():
        for parent in node["parents"]:
            children.setdefault(parent, set()).add(code)
    return children


@lru_cache(maxsize=65536)
def _descendants(code: str) -> frozenset[str]:
    seen: set[str] = set()
    pending = [code]
    while pending:
        current = pending.pop()
        if current not in seen:
            seen.add(current)
            pending.extend(_children().get(current, ()))
    return frozenset(seen)


def _disease_mentions(phrase: str) -> list[list[str]]:
    """Maximal non-overlapping whole-word aliases; ambiguous aliases stay ambiguous."""
    words = normalize(phrase).split()
    names = _diseases()["names"]
    found: list[list[str]] = []
    start = 0
    while start < len(words):
        for end in range(len(words), start, -1):
            codes = names.get(" ".join(words[start:end]))
            if codes:
                found.append(codes)
                start = end
                break
        else:
            start += 1
    return found


def indication_concepts_in_phrase(phrase: str) -> list[str]:
    """Compile disease concepts only; ordinary residual terms never become requirements."""
    concept = resolve_indication_phrase(phrase)
    if concept:
        return [concept]
    return list(dict.fromkeys(
        f"INDICATION:NCIT:{codes[0]}" for codes in _disease_mentions(phrase) if len(codes) == 1
    ))


def _compare_codes(observed: str, requested: str) -> ConditionMatch:
    if requested in _ancestors(observed):
        return ConditionMatch.MATCH
    if observed in _ancestors(requested) or _descendants(observed) & _descendants(requested):
        return ConditionMatch.UNDETERMINED
    return ConditionMatch.NO


def classify_condition(condition: str, concept: str) -> ConditionMatch:
    """Authority same/subtype evidence confirms; only explicit incompatibility excludes.

    Unknown names, ambiguous names and unexplained surrounding text cannot refute a
    requested disease. Whole-condition diagnoses can refute only a comparable concept.
    """
    normalized = normalize(condition)
    if set(normalized.split()) & {"not", "without", "excluding", "negative"}:
        return ConditionMatch.UNDETERMINED
    if concept == B_CELL_LYMPHOMA:
        if _has_any(normalized, _MATCH_TERMS[concept]):
            return ConditionMatch.MATCH
        if _has_any(normalized, _DISJOINT_TERMS[concept]):
            return ConditionMatch.NO
        if _has_any(normalized, _BROADER_TERMS[concept]):
            return ConditionMatch.UNDETERMINED
        concept = resolve_indication_phrase("B-cell lymphoma")
        # The legacy request resolver returns its legacy ID; use the typed NCIt name.
        codes = _diseases()["names"].get("b cell lymphoma", [])
        concept = f"INDICATION:NCIT:{codes[0]}" if len(codes) == 1 else None
    elif not is_indication_concept(concept):
        concept = resolve_indication_phrase(concept)
    if not concept or not concept.startswith("INDICATION:NCIT:"):
        return ConditionMatch.UNDETERMINED
    requested = concept.removeprefix("INDICATION:NCIT:")
    if requested not in _diseases()["nodes"]:
        return ConditionMatch.UNDETERMINED
    names = _diseases()["names"]
    whole = names.get(normalized, [])
    if len(whole) == 1:
        return _compare_codes(whole[0], requested)
    if whole:
        return ConditionMatch.UNDETERMINED
    mentions = _disease_mentions(condition)
    if any(len(codes) == 1 and requested in _ancestors(codes[0]) for codes in mentions):
        return ConditionMatch.MATCH
    return ConditionMatch.UNDETERMINED
