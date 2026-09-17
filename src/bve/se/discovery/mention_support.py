"""Route nominated names by how much evidence stands behind them.

Extraction is deliberately permissive: it nominates anything that might be a molecule and
lets the identity and assertion gates decide. That is the right division of labour for
correctness --- M17 asserted zero false targets across 8,080 candidates --- but it means
the default analyst path inherits every mistake extraction makes. In M17 that was 4,480
prose tokens and 7,966 unresolved assets.

This module sorts nominations into three dispositions. **None of them is deletion.**

The reason is a measurement blind spot rather than caution for its own sake. Benchmark
gold sets are cut from ontology DIRECT_TARGET edges, so every gold asset is ontology-known
by construction, and the unprotected population of every benchmark run contains no gold at
all. A hard support threshold would therefore score a perfect zero false-reject rate while
being completely untested against the case that matters: a genuinely novel asset,
mentioned once, absent from the ontology. Optimizing against a blind spot is not
optimization. So support decides which path a name takes, and everything keeps its
provenance either way.

Support is the number of distinct source documents mentioning the name, which the registry
already knows --- ``IdentityMention.source_document_id``. Nothing here reads the corpus.
"""

from __future__ import annotations

import enum
import re

from bve.se.discovery import drug_name_shape

#: Declared before measurement, not fitted to an observed cut. A name the ontology does
#: not know needs real corroboration to earn the default path.
MIN_SUPPORT_UNKNOWN = 5
#: A name that also looks like a molecule needs less, but not none: one document is a
#: mention, two is the weakest thing that can be called corroboration.
MIN_SUPPORT_DRUG_SHAPED = 2

#: Letters adjacent to digits. Development codes are not words and are never judged as
#: prose --- the ontology knows few of them by code, so shape and frequency both fail here.
_HAS_DIGIT = re.compile(r"\d")


class MentionDisposition(enum.Enum):
    """Where a nominated name goes. Every value is retained somewhere."""

    #: Exact ontology drug/alias match, or development-code shape. Kept unconditionally.
    PROTECTED = "protected"
    #: Not known to the ontology, but corroborated across enough documents.
    SUPPORTED_UNKNOWN = "supported_unknown"
    #: Below the support thresholds. Held for review with full provenance and kept out of
    #: the default scoring path until something promotes it.
    LOW_SUPPORT_UNKNOWN = "low_support_unknown"


def is_protected(name: str) -> bool:
    """True when evidence outside the corpus already vouches for this name."""
    folded = name.casefold()
    return drug_name_shape.is_known_drug_name(folded) or bool(_HAS_DIGIT.search(name))


def classify_mention_support(
    name: str,
    *,
    support: int,
    drug_shaped: bool | None = None,
) -> MentionDisposition:
    """Sort one nominated name into a disposition.

    ``support`` is the count of distinct documents mentioning it. ``drug_shaped`` may be
    passed when the caller already scored the name, to avoid re-running the model over a
    population the size of a corpus; it is computed on demand otherwise.
    """
    if is_protected(name):
        return MentionDisposition.PROTECTED

    if support >= MIN_SUPPORT_UNKNOWN:
        return MentionDisposition.SUPPORTED_UNKNOWN

    if drug_shaped is None:
        drug_shaped = drug_name_shape.is_drug_shaped(name.casefold())
    if drug_shaped and support >= MIN_SUPPORT_DRUG_SHAPED:
        return MentionDisposition.SUPPORTED_UNKNOWN

    return MentionDisposition.LOW_SUPPORT_UNKNOWN
