"""Pre-resolution query roles for clinical grammatical negation.

The role index locates phrases; it supplies no asset disease compatibility semantics.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from bve.se.intent.intent import IntentSpan, SpanKind

_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "research/se_indication_compilation_v2/ncit_query_roles.json"
)
_NEGATOR = re.compile(r"(?<![\w-])not(?![\w-])", re.IGNORECASE)
_FOLLOWING_CLAUSE = re.compile(r"\s+([^.!?;,():]+)")
_TOKEN = re.compile(r"\b[\w]+(?:-[\w]+)*\b")


def normalize_clinical_phrase(text: str) -> str:
    """The frozen query-role index's exact whole-word comparison space."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.casefold()).split())


@lru_cache(maxsize=1)
def query_roles() -> dict:
    """Shared immutable source view; no entity lookup or acquisition."""
    data = json.loads(_SOURCE.read_text())
    data["fingerprint"] = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
    data["component_names"] = set(data["component_names"])
    data["other_names"] = set(data["other_names"])
    return data


def grammatical_negations(query: str) -> list[IntentSpan]:
    """Bind standalone not to an immediately following clinical phrase.

    NOT-directed and parenthetical/protein/target uses do not establish this syntax.
    With no clinical anchor, existing entity resolution and ambiguity remain available.
    """
    negators = list(_NEGATOR.finditer(query))
    if not negators:
        return []
    roles = query_roles()
    spans: list[IntentSpan] = []
    for negator in negators:
        following = _FOLLOWING_CLAUSE.match(query, negator.end())
        if following is None:
            continue
        phrase = following.group(1)
        tokens = list(_TOKEN.finditer(phrase))
        anchor = None
        for token_end in range(1, len(tokens) + 1):
            key = normalize_clinical_phrase(phrase[:tokens[token_end - 1].end()])
            if key in roles["disease_names"]:
                anchor = key
            elif key in roles["finding_names"] and (
                token_end > 1 or key not in roles["other_names"]
            ):
                anchor = key
        if anchor is not None:
            spans.append(IntentSpan(
                text=negator.group(), start=negator.start(), end=negator.end(),
                kind=SpanKind.GRAMMATICAL_OPERATOR, resolved_to="NOT",
                rule="grammatical_clinical_negation",
                explanation=(f"Negation scopes the immediately following clinical alias {anchor!r}; "
                             "the operator is protected before entity resolution."),
            ))
    return spans
