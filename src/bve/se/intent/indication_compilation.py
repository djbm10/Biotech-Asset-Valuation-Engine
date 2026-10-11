"""Original-query indication spans; no asset compatibility decisions."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from bve.se.discovery.class_terms import is_class_term
from bve.se.intent.intent import SearchIntent, SpanKind
from bve.se.intent.parser import _STOPWORDS
from bve.se.ontology.indications import resolve_indication_phrase

_SOURCE = Path(__file__).resolve().parents[4] / "research/se_indication_compilation_v2/ncit_query_roles.json"
_TOKEN = re.compile(r"\b[\w]+(?:-[\w]+)*\b")
_MUTATION = re.compile(r"[ACDEFGHIKLMNPQRSTVWY][0-9]+[ACDEFGHIKLMNPQRSTVWY]", re.I)
_BOUNDARY = re.compile(r"\b(?:for|in)\b|[.!?;]", re.I)
_HARD = {SpanKind.TARGET, SpanKind.MODALITY, SpanKind.EVIDENCE, SpanKind.PHASE,
         SpanKind.STATUS, SpanKind.TARGET_LOGIC}


def _key(text: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.casefold()).split())


@lru_cache(maxsize=1)
def _roles() -> dict:
    data = json.loads(_SOURCE.read_text())
    data["fingerprint"] = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
    data["component_names"] = set(data["component_names"])
    data["other_names"] = set(data["other_names"])
    return data


def compilation_version() -> str:
    return "indication_compilation_v2_" + _roles()["fingerprint"][:12]


@dataclass(frozen=True)
class IndicationSpan:
    start: int
    end: int
    text: str
    requirement: str | None
    normalization: str
    rule: str
    aliases: tuple[str, ...]
    codes: tuple[str, ...]
    source_fingerprint: str


def _nonclinical(text: str, roles: dict) -> bool:
    key = _key(text)
    variants = {key}
    if key.endswith("ies"):
        variants.add(key[:-3] + "y")
    if key.endswith("s"):
        variants.add(key[:-1])
    return (bool(_MUTATION.fullmatch(text)) or is_class_term(text)
            or any(v in roles["other_names"] for v in variants))


def indication_spans(intent: SearchIntent) -> list[IndicationSpan]:
    """Locate clinical clauses without mutating parser output or interpreting evidence."""
    query, roles = intent.original_query, _roles()
    result: list[IndicationSpan] = []
    start, explicit = 0, False
    clauses = []
    for boundary in _BOUNDARY.finditer(query):
        clauses.append((start, boundary.start(), explicit))
        start = boundary.end()
        explicit = boundary.group().casefold() in {"for", "in"}
    clauses.append((start, len(query), explicit))
    for lo, hi, explicit in clauses:
        tokens = list(_TOKEN.finditer(query, lo, hi))
        if not tokens:
            continue
        locators = []
        for i in range(len(tokens)):
            for j in range(i + 1, len(tokens) + 1):
                key = _key(query[tokens[i].start():tokens[j - 1].end()])
                if key in roles["disease_names"]:
                    locators.append((i, j, key, roles["disease_names"][key], "disease"))
                elif key in roles["finding_names"] and (
                    j - i > 1 or key not in roles["other_names"]
                ):
                    locators.append((i, j, key, roles["finding_names"][key], "finding"))
        protected = {i for a, b, *_ in locators for i in range(a, b)}
        classes = [s for s in intent.spans if s.kind is SpanKind.UNRESOLVED_SCIENTIFIC
                   and lo <= s.start and s.end <= hi]

        def hard(i: int) -> bool:
            t = tokens[i]
            if i in protected:
                return False
            return any(s.kind in _HARD and s.start <= t.start() and t.end() <= s.end
                       and not (explicit and locators and s.kind is SpanKind.TARGET)
                       for s in intent.spans)

        def grammar(i: int) -> bool:
            return tokens[i].group().casefold() in _STOPWORDS

        def component(i: int) -> bool:
            text = tokens[i].group()
            key = _key(text)
            variants = {key, key[:-1] if key.endswith("s") else key,
                        key[:-3] + "y" if key.endswith("ies") else key}
            return (is_class_term(text) or bool(_MUTATION.fullmatch(text))
                    or bool(variants & roles["component_names"]))

        left, right = 0, len(tokens)
        # Strip complete independent query components at the edges, never clinical words.
        while left < right and left not in protected and not any(
            s.start <= tokens[left].start() < s.end for s in classes
        ) and (hard(left) or grammar(left) or component(left)):
            left += 1
        while right > left and right - 1 not in protected and not any(
            s.start < tokens[right - 1].end() <= s.end for s in classes
        ) and (hard(right - 1) or grammar(right - 1)
               or component(right - 1)):
            right -= 1
        if left == right:
            continue
        # Evidence/format spans outside a disease clause terminate it.
        for i in range(left, right):
            if hard(i):
                if any(a < i for a, *_ in locators) or explicit or classes:
                    right = i
                    break
                left = i + 1
        if left >= right:
            continue
        a, b = tokens[left].start(), tokens[right - 1].end()
        contained = [l for l in locators if left <= l[0] and l[1] <= right]
        text = query[a:b]
        delegated = any(s.start == a and s.end == b for s in classes)
        if not (contained or explicit or classes):
            continue
        if not contained and not delegated and all(
            grammar(i) or _nonclinical(tokens[i].group(), roles) or hard(i)
            for i in range(left, right)
        ):
            continue
        concept = resolve_indication_phrase(text)
        key = _key(text)
        unique = key in roles["disease_names"] and len(roles["disease_names"][key]) == 1
        normalization = "DELEGATED_CLASS" if delegated else (
            "RECOGNIZED" if concept or unique else "UNRESOLVED"
        )
        result.append(IndicationSpan(
            a, b, text, None if delegated else concept or text, normalization,
            "existing_scientific_class" if delegated else "original_clinical_clause",
            tuple(sorted({l[2] for l in contained})),
            tuple(sorted({code for l in contained for code in l[3]})), roles["fingerprint"],
        ))
    return result
