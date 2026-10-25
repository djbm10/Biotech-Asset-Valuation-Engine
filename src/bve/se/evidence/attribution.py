"""Asset-specific attribution of area and modality from free text (evidence_attribution_v1).

A document that discusses an indication or a modality, and a document that names an
asset, are both context. Only a passage that ties *this* asset to the indication or
modality is a fact about the asset. The rules are grammatical and per sentence: an
indication cue between the name and the area term, or apposition or a head noun for
modality, and no coordination joining the asset to another product. No rule names a
product, disease or target.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import lru_cache

from bve.se.ontology.modality import known_modalities, modality_aliases
from bve.se.ontology.records import normalize_lookup_key
from bve.se.ontology.therapeutic_areas import CLASSIFIED_AREAS, area_terms

#: Tokens after which an area term is the asset's indication: "X in patients with ...",
#: "X for the treatment of ...".
_INDICATION_CUES = frozenset(
    {"in", "for", "against", "treat", "treats", "treating", "treatment", "patients"}
)
#: Tokens that join the asset to another product. Next to the name they mean the sentence
#: is about a regimen or a list, so nothing in it is attributed to one member.
_COORDINATORS = frozenset(
    {"and", "or", "plus", "with", "versus", "vs", "combined", "combination", "+", "/"}
)
_DETERMINERS = frozenset({"a", "an", "the"})
_AREA_WINDOW = 12
_APPOSITION_WINDOW = 8
_HEAD_WINDOW = 4

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*|[,+/]")


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(text) if part.strip()]


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def _name_positions(tokens: list[str], name: str) -> Iterator[tuple[int, int]]:
    """(start, end) token spans where the whole name occurs, case-insensitively."""

    wanted = [token.casefold() for token in _tokens(name)]
    if not wanted:
        return
    folded = [token.casefold() for token in tokens]
    for start in range(len(folded) - len(wanted) + 1):
        if folded[start : start + len(wanted)] == wanted:
            yield start, start + len(wanted)


def _coordinated(tokens: list[str], start: int, end: int) -> bool:
    before = tokens[start - 1].casefold() if start > 0 else ""
    after = tokens[end].casefold() if end < len(tokens) else ""
    return before in _COORDINATORS or after in _COORDINATORS


def _has_term(words: str, terms: tuple[str, ...]) -> bool:
    return any(term in words for term in terms)


def attributed_areas(text: str, asset_name: str) -> list[tuple[str, str]]:
    """``(area, sentence)`` for every area a sentence attributes to this asset (R1)."""

    found: dict[str, str] = {}
    for sentence in sentences(text):
        tokens = _tokens(sentence)
        for start, end in _name_positions(tokens, asset_name):
            if _coordinated(tokens, start, end):
                continue
            window = tokens[end : end + _AREA_WINDOW]
            folded = [token.casefold() for token in window]
            for cue_index, token in enumerate(folded):
                if token not in _INDICATION_CUES:
                    continue
                after_cue = " ".join(folded[cue_index + 1 :])
                for area in CLASSIFIED_AREAS:
                    if area not in found and _has_term(after_cue, area_terms(area)):
                        found[area] = sentence
                break
    return sorted(found.items())


@lru_cache(maxsize=1)
def _modality_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    patterns = []
    for canonical in known_modalities():
        terms = sorted({normalize_lookup_key(a) for a in modality_aliases(canonical)} - {""},
                       key=len, reverse=True)
        alternation = "|".join(re.escape(term) for term in terms)
        patterns.append((canonical, re.compile(rf"(?<![a-z0-9])(?:{alternation})s?(?![a-z0-9])")))
    return tuple(patterns)


def _modality_of(span: str) -> str | None:
    """The most specific modality a short span names, by longest whole-word alias."""

    folded = normalize_lookup_key(span)
    best: tuple[int, str] | None = None
    for canonical, pattern in _modality_patterns():
        for match in pattern.finditer(folded):
            score = (len(match.group(0)), canonical)
            if best is None or score > best:
                best = score
    return best[1] if best else None


def _modality_ending(span: str) -> str | None:
    """A modality whose alias ends the span exactly: the head noun right before a name."""

    folded = normalize_lookup_key(span)
    best: tuple[int, str] | None = None
    for canonical, pattern in _modality_patterns():
        for match in pattern.finditer(folded):
            if match.end() == len(folded):
                score = (len(match.group(0)), canonical)
                if best is None or score > best:
                    best = score
    return best[1] if best else None


def _modality_starting(span: str) -> bool:
    """Whether a modality alias starts the span: the whole phrase is the modality noun."""

    folded = normalize_lookup_key(span)
    return any(pattern.match(folded) for _, pattern in _modality_patterns())


def attributed_modality(text: str, asset_name: str) -> str | None:
    """The modality a sentence attributes to this asset by apposition or head noun (R2)."""

    for sentence in sentences(text):
        tokens = _tokens(sentence)
        for start, end in _name_positions(tokens, asset_name):
            # "X, an investigational antibody-drug conjugate": the appositive runs to the end
            # of its clause (Amendment 1: a 5-token cut turned "Antibody-Drug Conjugate"
            # into "antibody").
            if end + 1 < len(tokens) and tokens[end] == "," and tokens[end + 1].casefold() in _DETERMINERS:
                span = tokens[end + 2 : end + 2 + _APPOSITION_WINDOW]
                cut = next((i for i, t in enumerate(span) if t == ","), len(span))
                modality = _modality_of(" ".join(span[:cut]))
                if modality:
                    return modality
            # "the antibody-drug conjugate X": a determiner, then the modality phrase, then the
            # name (Amendment 1: without the determiner, "peptide drugs" named "drugs").
            if _coordinated(tokens, start, end):
                continue
            for width in range(1, _HEAD_WINDOW + 1):
                if start - width - 1 < 0:
                    break
                if tokens[start - width - 1].casefold() not in _DETERMINERS:
                    continue
                phrase = " ".join(tokens[start - width : start])
                modality = _modality_ending(phrase)
                if modality and _modality_starting(phrase):
                    return modality
    return None
