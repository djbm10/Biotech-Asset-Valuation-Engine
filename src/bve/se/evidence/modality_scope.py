"""Additive, diagnostic modality scope. Never produces legacy facts or gate input."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from bve.se.ontology.modality import known_modalities, modality_aliases

Scope = Literal["PRODUCT_LEVEL", "COMPONENT_LEVEL", "RELATIONAL_COMPOSITE", "AMBIGUOUS"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Span(FrozenModel):
    start: int
    end: int
    text: str


class ScopeSource(FrozenModel):
    artifact: str
    artifact_sha256: str
    record_id: str
    field: str
    product_names: tuple[str, ...]
    product_locator: str


class ScopedModalityAssertion(FrozenModel):
    assertion_id: str
    candidate_id: str
    modality: str | None
    scope: Scope
    mention: Span
    product_span: Span | None
    component_span: Span | None
    relation_span: Span | None
    relations: tuple[str, ...]
    source: ScopeSource
    raw_text: str
    rule: str
    version: str = "modality_scope_v1"
    status: str
    transformations: tuple[str, ...] = (
        "case_insensitive_literal_alias_separator_matching_raw_offsets",
    )
    legacy_fact_ids: tuple[str, ...] = ()
    legacy_decision_bearing: Literal[False] = False


class ProductPhrase(FrozenModel):
    phrase: Span
    head: Span
    coordinated: bool


# Frozen in docs/se_policies/modality_scope_head_attachment_v1.md.
_PHRASE_BOUNDARIES = frozenset(
    "with containing comprising comprised consisting delivered conjugated linked that which who "
    "targeting for in against of to by from via using after before plus versus vs as at on under "
    "when while".split()
)
_COORDINATORS = frozenset({"and", "or", "nor"})
_GENERIC_HEADS = (
    "therapeutic|therapeutics|therapy|therapies|drug|agent|product|treatment|medicine|candidate"
)
_TOKEN = r"[^\W_]+(?:-[^\W_]+)*"


def product_phrase(text: str, start: int, end: int) -> ProductPhrase | None:
    """Predicate noun phrase after the copula; its grammatical head is the last token."""
    tokens = []
    coordinated = False
    for match in re.finditer(r"[,:()]|" + _TOKEN, text[start:end]):
        word = match.group().casefold()
        if word in ",:()" or word in _PHRASE_BOUNDARIES:
            break
        coordinated |= word in _COORDINATORS
        tokens.append(match)
    if not tokens:
        return None
    return ProductPhrase(
        phrase=_span(text, start + tokens[0].start(), start + tokens[-1].end()),
        head=_span(text, start + tokens[-1].start(), start + tokens[-1].end()),
        coordinated=coordinated,
    )


# Frozen in docs/se_policies/modality_scope_product_description_v1.md.
_PRE_ITEM = r"(?:[^\W_]+(?:[-/][^\W_]+)*|\([^()]*\))"
_PRE = r"(?P<pre>(?:" + _PRE_ITEM + r",?\s+)*)"
_POST = (
    r"(?:\s+(?:" + _GENERIC_HEADS + r"))*(?:\s*\([^()]*\))?"
    r"(?=\s*$|\s*[,;:)]|\s+(?P<next>[^\W_]+))"
)
_HEDGE = r"\b(?:not|no|without|may|might|could)\b"


def _embedded(text: str, start: int, end: int, left: int) -> bool:
    token_start = start
    while token_start > left and text[token_start - 1].isalnum():
        token_start -= 1
    return token_start < start or (end < len(text) and text[end].isalnum())


def _product_description(text, start, end, modality, hits, names):
    """Appositive naming the whole product's modality (rule A)."""
    left = max(text.rfind(c, 0, start) for c in ".;\n") + 1
    right = min([p for c in ".;\n" if (p := text.find(c, end)) >= 0] or [len(text)])
    sentence = text[left:right]
    if modality is None or _embedded(text, start, end, left) or re.search(_HEDGE, sentence, re.I):
        return None
    if any(e == end and s < start for s, e, _ in hits):
        return None
    post = re.match(_POST, text[end:right], re.I)
    if not post:
        return None
    nxt = post.group("next")
    if nxt and not (nxt.casefold() in _PHRASE_BOUNDARIES or re.search(r"(?:ed|ing)$", nxt, re.I)):
        return None
    # Rule B (premodified copula) was removed under the preregistered per-rule fallback: it
    # certified a radioconjugate and a class-label subject in the independent sample.
    for name in sorted(names, key=lambda n: (-len(n), n)):
        for occurrence in re.finditer(
            r"(?<!\w)" + re.escape(name) + r"(?!\w)", text[left:start], re.I
        ):
            at = left + occurrence.start()
            between = r"(?:\s*\([^()]*\))?"
            form = ("explicit_product_appositive", r"\s*,\s+an?\s+")
            described = _described(
                text,
                at,
                occurrence.end() - occurrence.start(),
                start,
                between,
                form,
                modality,
                hits,
            )
            if described:
                return described
    return None


def _described(text, at, length, start, between, form, modality, hits):
    rule, link = form
    m = re.fullmatch(between + link + _PRE, text[at + length : start], re.I)
    if not m:
        return None
    pre = m.group("pre")
    words = {w.casefold() for w in re.findall(r"[^\W_]+", re.sub(r"\([^()]*\)", " ", pre))}
    if words & (_PHRASE_BOUNDARIES | _COORDINATORS):
        return None
    if any(start - len(pre) <= s < start and other != modality for s, _, other in hits):
        return None
    product = _span(text, at, at + length)
    return (
        "PRODUCT_LEVEL",
        product,
        None,
        _span(text, product.end, start),
        ("PRODUCT_IS_MODALITY",),
        rule,
    )


def _pattern(term: str) -> str:
    return r"[\s_-]+".join(re.escape(x) for x in re.split(r"[\s_-]+", term))


def _span(text: str, start: int, end: int) -> Span:
    return Span(start=start, end=end, text=text[start:end])


def _scope(text: str, start: int, end: int, names: tuple[str, ...]):
    left = max(text.rfind(c, 0, start) for c in ".;\n") + 1
    right = min([p for c in ".;\n" if (p := text.find(c, end)) >= 0] or [len(text)])
    sentence = text[left:right]
    product = None
    for name in sorted(names, key=lambda n: (-len(n), n)):
        m = re.match(r"\s*" + re.escape(name) + r"(?=\W|$)", sentence, re.I)
        if m:
            product = _span(text, left + m.end() - len(name), left + m.end())
            break
    ambiguous = ("AMBIGUOUS", product, None, None, (), "unproven_subject_or_relation")
    if product is None or re.search(r"\b(?:not|no|without|may|might|could)\b", sentence, re.I):
        return ambiguous
    # Invalid embedded aliases remain visible without semantic authority.
    token_start = start
    while token_start > left and text[token_start - 1].isalnum():
        token_start -= 1
    prefix = text[token_start:start].casefold()
    suffix_inside = end < len(text) and text[end].isalnum()
    peptide_prefix = text[start:end].casefold() == "peptide" and prefix in {
        "di",
        "tri",
        "tetra",
        "penta",
        "hexa",
        "hepta",
        "octa",
        "nona",
        "deca",
        "oligo",
        "poly",
    }
    if suffix_inside or (prefix and not peptide_prefix):
        return ambiguous
    pred = text[product.end : right]
    conjugated = re.search(r"\bconjugated\s+to\b", pred, re.I)
    is_product = re.match(r"\s+is\s+(?:(?:a|an)\s+)?", pred, re.I)
    if is_product and conjugated:
        rel = _span(text, product.end + conjugated.start(), product.end + conjugated.end())
        return (
            "RELATIONAL_COMPOSITE",
            product,
            None,
            rel,
            ("PRODUCT_IS_COMPOSITE",),
            "explicit_conjugation",
        )
    phrase = is_product and product_phrase(text, product.end + is_product.end(), right)
    if phrase and phrase.phrase.start <= start < phrase.phrase.end:
        if phrase.coordinated:
            return ("AMBIGUOUS", product, None, None, (), "product_phrase_coordination")
        # Only the head designation types the product: hyphenated premodifiers before it,
        # semantically empty product nouns after it.
        before = re.fullmatch(r"(?:" + _TOKEN + r"-[^\W_]+\s+)*", text[phrase.phrase.start : start])
        after = re.fullmatch(
            r"(?:\s+(?:" + _GENERIC_HEADS + r"))*", text[end : phrase.phrase.end], re.I
        )
        if before and after:
            return (
                "PRODUCT_LEVEL",
                product,
                None,
                _span(text, product.end, start),
                ("PRODUCT_IS_MODALITY",),
                "explicit_product_predicate",
            )
        return ("AMBIGUOUS", product, None, None, (), "product_phrase_not_head")
    possession = re.match(r"\s+(?:contains|carries)\s+", pred, re.I)
    relation = possession
    if is_product:
        relation = re.search(
            r"\b(?:with|containing|comprised\s+of|delivered\s+using)\b", pred, re.I
        )
    if relation is None or product.end + relation.end() > start:
        return ambiguous
    rel = _span(text, product.end + relation.start(), product.end + relation.end())
    tail = text[end:right]
    head = re.match(
        r"(?:-derived)?\s+(?:(?:binding)\s+)?(?:linker|payload|domain|vector|component)\b",
        tail,
        re.I,
    )
    vector = text[start:end].casefold() == "viral vector"
    comprised = relation.group().casefold().startswith("comprised")
    if head or vector or comprised:
        component_end = end + head.end() if head else end
        return (
            "COMPONENT_LEVEL",
            product,
            _span(text, token_start, component_end),
            rel,
            ("PRODUCT_HAS_COMPONENT", "COMPONENT_HAS_MODALITY"),
            "explicit_component_relation",
        )
    return ambiguous


def scoped_modality_assertions(
    candidate_id: str, text: str, source: ScopeSource, *, legacy_fact_ids: tuple[str, ...] = ()
) -> list[ScopedModalityAssertion]:
    """Observe one raw field with source-declared product names; never alter decisions."""
    inventory = {
        (modality, alias) for modality in known_modalities() for alias in modality_aliases(modality)
    }
    inventory.update((None, term) for term in ("viral vector", "radionuclide", "cytotoxic"))
    hits = set()
    for modality, alias in sorted(inventory, key=lambda pair: (pair[0] or "", pair[1])):
        for match in re.finditer(_pattern(alias), text, re.I):
            hits.add((match.start(), match.end(), modality))
    records = []
    for start, end, modality in sorted(hits, key=lambda h: (h[0], h[1], h[2] or "")):
        scope, product, component, relation, relations, rule = _scope(
            text, start, end, source.product_names
        )
        if rule in {"unproven_subject_or_relation", "product_phrase_not_head"}:
            described = _product_description(text, start, end, modality, hits, source.product_names)
            if described:
                scope, product, component, relation, relations, rule = described
        payload = dict(
            candidate_id=candidate_id,
            modality=modality,
            scope=scope,
            mention=_span(text, start, end),
            product_span=product,
            component_span=component,
            relation_span=relation,
            relations=relations,
            source=source,
            raw_text=text,
            rule=rule,
            status="AMBIGUOUS" if scope == "AMBIGUOUS" else "EXPLICIT_RELATION",
            legacy_fact_ids=tuple(sorted(set(legacy_fact_ids))),
        )
        temporary = ScopedModalityAssertion(assertion_id="", **payload)
        encoded = json.dumps(
            temporary.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        records.append(
            temporary.model_copy(
                update={"assertion_id": hashlib.sha256(encoded.encode()).hexdigest()}
            )
        )
    return records
