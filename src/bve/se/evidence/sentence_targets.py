"""A construct target set read from one sentence that names one asset: ``ASSET_SENTENCE_TARGET``.

Policy: ``docs/se_policies/asset_sentence_target_v1.md``. The third, weakest route to a
``construct_target_set``, for qualified assets that neither the drug->target authority nor
an intervention record describes. "ALLO-715, a BCMA-directed allogeneic CAR T" says what
ALLO-715 binds; a paragraph about BCMA that also mentions ALLO-715 does not.

Every rule is structural and each one refuses rather than guesses: one asset per sentence,
a cue beside its name, no frame that points at another therapy, every candidate symbol
resolved, every admitted sentence in agreement. A miss leaves the gate UNKNOWN, which a
human reviews; a false member silently decides a target question.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from bve.se.evidence.construct_targets import (
    ConstructTargetEvidence,
    attributed_reading,
    canonical_construct_targets,
    cue_positions,
    tokenize,
)
from bve.se.schemas.contracts import ExtractedClaim, NormalizedFact, VerificationStatus

EXTRACTION_METHOD = "ASSET_SENTENCE_TARGET"
EXTRACTOR_VERSION = "asset_sentence_target_v1"

#: S1: the same bound human proof of concept reads sentences under.
_MAX_SENTENCE_CHARS = 400

#: S4: the frozen cue window, measured from the asset's own name.
_NAME_CUE_WINDOW = 4

#: S5: frames that point the target at another therapy. Grammar, never drug names.
_OTHER_THERAPY_WORDS = frozenset(
    {
        "prior",
        "previous",
        "after",
        "following",
        "relapsed",
        "failure",
        "exposed",
        "versus",
        "compared",
        "unlike",
        "not",
    }
)
_OTHER_THERAPY_PHRASES = (("refractory", "to"), ("rather", "than"))
_OTHER_THERAPY_PREFIX = "post"

#: Below the authority's 0.95: a sponsor's prose is a weaker witness than a curated edge.
_CONFIDENCE = 0.7


@dataclass(frozen=True)
class SentenceTarget:
    """One admitted sentence and the complete target set it attributes to the asset."""

    document_id: str
    sentence: str
    targets: tuple[str, ...]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.;])\s+|\n+", text) if part.strip()]


def _name_spans(tokens: list[str], name: str) -> list[tuple[int, int]]:
    """Whole-token occurrences of ``name``, as inclusive token index spans."""

    wanted = [token.casefold() for token in tokenize(name)]
    if not wanted:
        return []
    lowered = [token.casefold() for token in tokens]
    width = len(wanted)
    return [
        (start, start + width - 1)
        for start in range(len(lowered) - width + 1)
        if lowered[start : start + width] == wanted
    ]


def _points_at_another_therapy(tokens: list[str]) -> bool:
    lowered = [token.casefold() for token in tokens]
    if any(token in _OTHER_THERAPY_WORDS for token in lowered):
        return True
    if any(token.split("-")[0] == _OTHER_THERAPY_PREFIX and "-" in token for token in lowered):
        return True
    return any(
        lowered[index : index + len(phrase)] == list(phrase)
        for phrase in _OTHER_THERAPY_PHRASES
        for index in range(len(lowered) - len(phrase) + 1)
    )


def _names_another_asset(
    tokens: list[str], own_spans: list[tuple[int, int]], other_names: frozenset[tuple[str, ...]], widest: int
) -> bool:
    lowered = [token.casefold() for token in tokens]
    for start in range(len(lowered)):
        for width in range(1, min(widest, len(lowered) - start) + 1):
            if tuple(lowered[start : start + width]) not in other_names:
                continue
            end = start + width - 1
            if any(own_start <= start and end <= own_end for own_start, own_end in own_spans):
                continue
            return True
    return False


def name_keys(names) -> frozenset[tuple[str, ...]]:
    """Asset names in the token space S3 compares in."""

    return frozenset(
        key
        for key in (tuple(token.casefold() for token in tokenize(str(name))) for name in names)
        if key
    )


def sentence_targets(
    text: str,
    *,
    asset_names,
    other_asset_names: frozenset[tuple[str, ...]],
    document_id: str,
) -> list[SentenceTarget]:
    """Sentences in ``text`` that attribute a complete target set to this one asset."""

    names = sorted({str(name) for name in asset_names if str(name).strip()}, key=len, reverse=True)
    own_keys = name_keys(names)
    others = other_asset_names - own_keys
    widest = max((len(key) for key in others), default=0)
    admitted: list[SentenceTarget] = []
    for sentence in _sentences(text):
        if len(sentence) > _MAX_SENTENCE_CHARS:
            continue
        tokens = tokenize(sentence)
        spans = [span for name in names for span in _name_spans(tokens, name)]
        if not spans:
            continue
        if _names_another_asset(tokens, spans, others, widest):
            continue
        if _points_at_another_therapy(tokens):
            continue
        cues = cue_positions(tokens)
        if not any(
            start - _NAME_CUE_WINDOW <= cue <= end + _NAME_CUE_WINDOW
            for cue in cues
            for start, end in spans
        ):
            continue
        own = frozenset(index for start, end in spans for index in range(start, end + 1))
        found, incomplete = attributed_reading(sentence, subject_tokens=own)
        if incomplete or not found:
            continue
        admitted.append(
            SentenceTarget(
                document_id=document_id,
                sentence=sentence,
                targets=tuple(canonical_construct_targets(found)),
            )
        )
    return admitted


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{hashlib.sha256('|'.join(parts).encode()).hexdigest()[:20]}"


def asset_sentence_target_evidence(
    asset_id: str, observations: list[SentenceTarget], *, as_of_date: date
) -> ConstructTargetEvidence | None:
    """The asset's sentence-read construct set, or ``None`` when sentences disagree or are absent.

    The documents are already in the ledger -- the asset was observed in them -- so only
    claims and the fact travel here.
    """

    if not observations:
        return None
    sets = {observation.targets for observation in observations}
    if len(sets) != 1:
        return None
    targets = sorted(next(iter(sets)))
    unique = {(o.document_id, o.sentence): o for o in observations}
    claims = [
        ExtractedClaim(
            claim_id=_id("claim", asset_id, "construct_target_set", document_id, sentence),
            subject_id=asset_id,
            predicate="construct_target_set",
            normalized_value=targets,
            source_document_id=document_id,
            supporting_passage=sentence,
            locator="sentence",
            direct_observation=True,
            extraction_method=EXTRACTION_METHOD,
            extractor_version=EXTRACTOR_VERSION,
            extraction_confidence=_CONFIDENCE,
            verification_status=VerificationStatus.MACHINE_VERIFIED,
            applicable_as_of_date=as_of_date,
        )
        for document_id, sentence in sorted(unique)
    ]
    fact = NormalizedFact(
        fact_id=_id("fact", asset_id, "construct_target_set", EXTRACTION_METHOD, *targets),
        subject_id=asset_id,
        fact_type="construct_target_set",
        value=targets,
        supporting_claim_ids=[claim.claim_id for claim in claims],
        confidence=_CONFIDENCE,
    )
    return ConstructTargetEvidence(claims=claims, fact=fact)
