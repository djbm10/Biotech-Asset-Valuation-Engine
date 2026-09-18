"""The suffix lexicon the prose extractor reads drug names with.

Generic names are built from stems -- ``-olol``, ``-pril``, ``-adine``, ``-mab`` -- and a
stem is shared by many chemically distinct molecules precisely because that is what a stem
is for. The lexicon shipped here counts them off the 71,506 DRUG entities of the frozen
ontology snapshot rather than listing them by hand, because a list chosen after seeing
which drugs a benchmark missed would be hand-mapping wearing a lexicon's clothes. The
derivation, its thresholds and the snapshot hash travel inside the artifact.

Two vocabularies come out of that derivation:

``stems``
    Suffixes shared by at least 40 distinct drug names and not themselves ending many
    ordinary words.
``prose_words``
    Ordinary words of biomedical English -- ``membrane``, ``cytokine``, ``phosphatase`` --
    sampled from the same snapshot's TARGET labels. Several admitted stems also end
    everyday words, and this is what stops an abstract's prose from reading as molecules.

Matching a stem is not an identity claim and not a target claim. It says a token is shaped
like a drug name, which is the weakest thing that can be said about it; assertion and
corroboration remain entirely downstream.
"""

from __future__ import annotations

import functools
import json
import pathlib
import re

LEXICON_PATH = pathlib.Path(__file__).resolve().parents[1] / "lexicon" / "drug_name_stems_v1.json"

# The six suffixes the extractor knew before the lexicon existed. They are unioned into the
# pattern rather than deleted, so replacing the hand-written regex with a derived lexicon
# can only widen what can be read, never narrow it. Two of them -- parib, lisib -- name
# drug classes too small to clear the 40-name derivation threshold on their own.
LEGACY_STEMS = ("mab", "cept", "parib", "tinib", "lisib", "nib")

# Closed, universal sets: the twenty proteinogenic amino acids in their three-letter form,
# and the constants an assay is reported in. Both are code-shaped, both were being returned
# as assets, and neither has anything to do with any particular target.
AMINO_ACID_CODES = frozenset(
    """ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL""".split()
)
ASSAY_CONSTANT_CODES = frozenset({"IC50", "EC50", "LD50", "LC50", "GI50", "TD50", "CC50", "KD"})


@functools.lru_cache(maxsize=1)
def _lexicon() -> dict:
    return json.loads(LEXICON_PATH.read_text())


def stems() -> tuple[str, ...]:
    return tuple(_lexicon()["stems"])


def prose_words() -> frozenset[str]:
    return frozenset(_lexicon()["prose_words"])


@functools.lru_cache(maxsize=1)
def drug_name_pattern() -> re.Pattern[str]:
    """A word of at least five letters ending in a derived stem, or a legacy stem."""

    alternatives = sorted({*stems(), *LEGACY_STEMS}, key=len, reverse=True)
    return re.compile(
        r"\b[a-z][a-z-]{3,40}(?:" + "|".join(alternatives) + r")(?:-[a-z]{3,5})?\b",
        re.IGNORECASE,
    )


def is_prose_word(value: str) -> bool:
    """True when the token is an ordinary word rather than a name shaped like one."""

    return value.casefold() in prose_words()


def is_residue_or_assay_code(value: str) -> bool:
    """True for ``LYS191``, ``IC 50`` and friends -- code-shaped, never an asset."""

    compact = re.sub(r"[^A-Za-z0-9]+", "", value).upper()
    if compact in ASSAY_CONSTANT_CODES:
        return True
    residue = re.fullmatch(r"([A-Z]{3})(\d{1,4})", compact)
    return bool(residue and residue.group(1) in AMINO_ACID_CODES)
