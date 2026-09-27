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
    return isinstance(value, str) and value in _REQUEST_SURFACES


def resolve_indication_phrase(phrase: str) -> str | None:
    """The concept a query phrase names, or ``None`` when it is not exactly one surface."""

    words = normalize(phrase)
    for term in (*_QUALIFIERS, *_CONNECTORS):
        words = re.sub(rf"\b{term}\b", " ", words)
    remainder = " ".join(words.split())
    for concept, surfaces in _REQUEST_SURFACES.items():
        if remainder in surfaces:
            return concept
    return None


def classify_condition(condition: str, concept: str) -> ConditionMatch:
    """Whether one condition string names ``concept``; the first applicable rule wins."""

    normalized = normalize(condition)
    if _has_any(normalized, _MATCH_TERMS[concept]):
        return ConditionMatch.MATCH
    if _has_any(normalized, _DISJOINT_TERMS[concept]):
        return ConditionMatch.NO
    if _has_any(normalized, _BROADER_TERMS[concept]):
        return ConditionMatch.UNDETERMINED
    return ConditionMatch.NO
