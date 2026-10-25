"""Controlled vocabulary for therapeutic area.

One canonical space for both sides of the ``strategy.therapeutic_area`` gate: the areas a
buyer requests and the areas a source document supports. Before this module the request was
``ONCOLOGY`` and the evidence was ``oncology``, compared case-sensitively, so an oncology
request excluded every oncology asset. And the evidence could only ever say ``oncology``, so
an autoimmune request could never pass.

Frozen by ``docs/se_policies/ta_gate_semantics.md``. The lexicon is a taxonomy of disease
classes. No entry may encode a target, programme or company, and a change to it is a
declared change.
"""

from __future__ import annotations

import re

ONCOLOGY = "ONCOLOGY"
AUTOIMMUNE = "AUTOIMMUNE"
#: Non-malignant digestive disease (gi_area_evidence_v1). GI cancers stay ONCOLOGY;
#: Crohn's disease and ulcerative colitis stay AUTOIMMUNE.
GASTROINTESTINAL = "GASTROINTESTINAL"

#: The compiler's placeholder for "no area stated". It is the absence of a constraint,
#: not an area, and no requirement is built from it.
UNSPECIFIED = "UNSPECIFIED"

#: Substring terms matched on casefolded text. ONCOLOGY is the pre-existing extractor list
#: unchanged. AUTOIMMUNE avoids bare fragments (``sclerosis``, ``sle``, ``itp``, ``anca``)
#: that also occur inside unrelated disease names or ordinary words.
_AREA_TERMS: dict[str, tuple[str, ...]] = {
    ONCOLOGY: ("cancer", "leukemia", "lymphoma", "malignancy", "myeloma", "oncology", "tumor"),
    AUTOIMMUNE: (
        "autoimmun",
        "lupus",
        "rheumatoid arthritis",
        "multiple sclerosis",
        "systemic sclerosis",
        "scleroderma",
        "myasthenia gravis",
        "neuromyelitis optica",
        "nmosd",
        "sjogren",
        "sjögren",
        "vasculitis",
        "myositis",
        "immune thrombocytopeni",
        "pemphig",
        "igg4-related",
        "antiphospholipid",
        "chronic inflammatory demyelinating",
        "cidp",
        "psoriasis",
        "psoriatic",
        "ankylosing spondylitis",
        "crohn",
        "ulcerative colitis",
        "type 1 diabetes",
        "graves",
        "hashimoto",
        "celiac",
        "vitiligo",
        "alopecia areata",
    ),
    # Bare "colitis" (DSS model induction), "diarrhea"/"nausea" (oncology adverse events)
    # and "bowel preparation" (a procedure) are deliberately absent.
    GASTROINTESTINAL: (
        "constipation",
        "irritable bowel",
        "gastroparesis",
        "functional dyspepsia",
        "gastroesophageal reflux",
        "fecal incontinence",
        "faecal incontinence",
        "functional gastrointestinal",
    ),
}

#: Areas the evidence layer can observe. A requested area outside this set can never be
#: seen in evidence, so its absence there is not a negative.
CLASSIFIED_AREAS = frozenset(_AREA_TERMS)

_ALIASES = {
    "CANCER": ONCOLOGY,
    "AUTOIMMUNITY": AUTOIMMUNE,
    "AUTOIMMUNE_DISEASE": AUTOIMMUNE,
    "GI": GASTROINTESTINAL,
    "GASTROENTEROLOGY": GASTROINTESTINAL,
}

_SEPARATORS = re.compile(r"[\s\-]+")


def canonical_therapeutic_area(value: object) -> str:
    """Return the canonical area for a requested or observed value.

    An unrecognised area keeps its normalised literal form and matches only itself.
    """

    key = _SEPARATORS.sub("_", str(value).strip().casefold()).upper()
    return _ALIASES.get(key, key)


def classify_therapeutic_areas(text: str) -> list[str]:
    """Every classified area the text supports, sorted. Empty when it supports none."""

    folded = text.casefold()
    return sorted(
        area for area, terms in _AREA_TERMS.items() if any(term in folded for term in terms)
    )


def area_terms(area: str) -> tuple[str, ...]:
    """The lexicon terms that evidence a classified area; empty for any other value."""

    return _AREA_TERMS.get(canonical_therapeutic_area(area), ())
