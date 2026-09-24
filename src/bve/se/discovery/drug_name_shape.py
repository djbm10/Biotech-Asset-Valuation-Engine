"""A learned second opinion on whether a prose token is shaped like a drug name.

``drug_name_lexicon`` nominates a token when it ends in a suffix shared by at least 40
distinct ontology molecules. That threshold is what keeps the rule target-agnostic, and it
stays exactly where it is. What it cannot do is see a drug from a small class: a molecule
whose stem is shared by four siblings rather than forty is invisible to a frequency rule no
matter how the rule is spelled. Lowering the threshold after reading a list of misses, or
appending the stem those misses happen to share, would both be fitting the benchmark.

So the frequency rule gains a companion rather than a correction. A multinomial naive Bayes
model over character n-grams, trained on the frozen ontology's own molecule names against
the same snapshot's biomedical vocabulary, judges whether a previously unseen token has
drug morphology. Molecule names carry it -- the interleaved consonant-vowel shape, the
Latinate endings, the length -- and ordinary biomedical English does not.

The artifact is frozen before use and carries its own provenance: the snapshot hash it was
trained from, the hyperparameters declared before training, the deterministic train/held-out
split, the decision threshold, and the held-out precision and recall that threshold buys.
Nothing in it was chosen by looking at a benchmark score.

**Arm's length.** Every gold, trap, sibling and target-vocabulary string of PDCD1, SLC6A2,
HRH1 and HTR2A was removed from the positives, the negatives, the training set and the
calibration set alike. The model cannot have learned the shape of a molecule it is later
measured on, and its threshold cannot have been calibrated against one.

**Nomination only.** Accepting a token makes it a *mention*. It earns no identity and no
target: both remain with the identity registry and the ``CandidateTargetAssertion`` gates,
under M11's rule that co-occurrence is never identity. A false accept costs mention-layer
precision and can cost nothing else.
"""

from __future__ import annotations

import functools
import json
import pathlib
import re

_LEXICON = pathlib.Path(__file__).resolve().parents[1] / "lexicon"
MODEL_PATH = _LEXICON / "drug_name_shape_v1.json"
KNOWN_NAMES_PATH = _LEXICON / "known_drug_names_v1.json"
MULTI_TOKEN_NAMES_PATH = _LEXICON / "multi_token_drug_names_v1.json"
IDENTITY_BEARING_NAMES_PATH = _LEXICON / "identity_bearing_drug_names_v1.json"

#: Below this length a token carries too few n-grams for the model to say anything, and the
#: short-token space is where ordinary words and gene symbols live. Declared with the model.
MIN_LENGTH = 5

_ALPHABETIC = re.compile(r"[a-z]+")


@functools.lru_cache(maxsize=1)
def _model() -> dict:
    return json.loads(MODEL_PATH.read_text())


def threshold() -> float:
    return _model()["held_out_performance"]["threshold"]


def _features(token: str) -> list[str]:
    padded = f"^{token}$"
    sizes = _model()["hyperparameters"]["ngram_sizes"]
    return [padded[i : i + n] for n in sizes for i in range(len(padded) - n + 1)]


def score(value: str) -> float:
    """Length-normalized log-odds that the token is a molecule name rather than prose.

    Normalizing by the number of matched n-grams is what stops the model from scoring a
    word simply for being long, which every polysyllabic protein name would exploit.
    """

    token = value.strip().casefold()
    if not _ALPHABETIC.fullmatch(token) or len(token) < MIN_LENGTH:
        return float("-inf")
    model = _model()
    weights = model["weights"]
    grams = [gram for gram in _features(token) if gram in weights]
    if not grams:
        return float("-inf")
    return (model["prior"] + sum(weights[gram] for gram in grams)) / len(grams)


@functools.lru_cache(maxsize=1)
def known_drug_names() -> frozenset[str]:
    """Single-token drug names the frozen ontology already has a record for."""

    return frozenset(json.loads(KNOWN_NAMES_PATH.read_text())["names"])


def is_known_drug_name(value: str) -> bool:
    """True for an exact match against the ontology's own molecule names.

    Ontology-derived, and reported as such: a benchmark asset recovered by this route was
    recovered because an authority listed it, not because the engine read it out of
    evidence. The shape model is the arm's-length route.
    """

    return value.strip().casefold() in known_drug_names()


@functools.lru_cache(maxsize=1)
def identity_bearing_drug_names() -> frozenset[str]:
    """Names the ontology treats as a molecule's own identity.

    Built by ``scripts/build_identity_bearing_drug_names.py`` from ``canonical_symbol``,
    ``label``, ``APPROVED_NAME`` and ``DEVELOPMENT_CODE``.
    """

    return frozenset(json.loads(IDENTITY_BEARING_NAMES_PATH.read_text())["names"])


@functools.lru_cache(maxsize=1)
def corroborative_drug_names() -> frozenset[str]:
    """Names by which a molecule may be *referred to*: ``SYNONYM`` and ``TRADE_NAME``.

    These resolve a mention to its parent and may corroborate an identity. They may not
    qualify a string on their own -- see ``is_identity_bearing_drug_name``.
    """

    return frozenset(
        json.loads(IDENTITY_BEARING_NAMES_PATH.read_text())["corroborative_names"]
    )


def _matches_lexicon(value: str, names: frozenset[str]) -> bool:
    """Look ``value`` up in ``names``, insensitive to how its separator is written."""

    folded = " ".join(value.split()).casefold()
    # Separator-insensitive, because the separator is not part of the identity. Measured:
    # ``amg 420`` is absent from the lexicon while ``amg-420`` and ``amg420`` are present,
    # and ``allo-715`` is absent while ``allo 715`` is present -- the same record, written
    # two ways by two authorities. Folding is safe here in a way a shape rule is not: no
    # spelling of ASCO 2023, NEJM 2011, IQR 124, WHO 2022, PRISMA 2020, POD24 or bsAbs is
    # in the drug lexicon, so this recovers sponsor codes without admitting citations.
    return any(
        variant in names
        for variant in (
            folded,
            folded.replace(" ", ""),
            folded.replace(" ", "-"),
            folded.replace("-", " "),
            folded.replace("-", ""),
        )
    )


def is_identity_bearing_drug_name(value: str) -> bool:
    """Whether the ontology holds this string as a molecule's own identity.

    The distinction ``is_known_drug_name`` cannot make, and v3 narrows it again. v1 of this
    rule excluded only ``TRADE_NAME``, which removed ``frontline`` (FIPRONIL, a veterinary
    insecticide), ``choice`` (WARFARIN) and ``discase`` (CHYMOPAPAIN) -- and left ``paper``,
    a ``SYNONYM``, to reach shortlist position 10 on a live run. ``water`` is worse still:
    an ``APPROVED_NAME``, and so still here.

    So the synonym tier moved out. This loses no real brand and no legacy name: ``Keytruda``
    and old synonyms still nominate a mention and still resolve to their parent, which
    qualifies on its own evidence. What they no longer do is decide, alone, that a string
    belongs in the therapeutic-asset population. The measured cost of that narrowing was
    declared before the run in ``asset_qualification_tiered_evidence_v3.md`` §4.
    """

    return _matches_lexicon(value, identity_bearing_drug_names())


def is_corroborative_drug_name(value: str) -> bool:
    """Whether the ontology refers to some molecule by this string, as synonym or brand.

    Enough to resolve a mention to a parent and to corroborate an identity another route
    has already made plausible. Never enough on its own.
    """

    return _matches_lexicon(value, corroborative_drug_names())


@functools.lru_cache(maxsize=1)
def known_multi_token_drug_names() -> frozenset[str]:
    """Two-token drug names the frozen ontology holds as a single molecule.

    ``known_drug_names`` is single-token by construction and so cannot see that
    ``belantamab mafodotin`` is one drug -- which is how a two-word INN became two assets.
    Both halves are *also* standalone ontology records, so the fragmentation is invisible
    to any test applied to one token; only the pair can reveal it.
    """

    return frozenset(json.loads(MULTI_TOKEN_NAMES_PATH.read_text())["names"])


def is_known_multi_token_drug_name(value: str) -> bool:
    """True when the whole string is one molecule to the ontology, not two adjacent ones."""

    return " ".join(value.split()).casefold() in known_multi_token_drug_names()


def is_drug_shaped(value: str) -> bool:
    """True when the token clears the frozen threshold. A nomination, not an identity."""

    return score(value) >= threshold()


def nominates(value: str) -> bool:
    """Either route. Still a nomination: no identity, no target."""

    return is_known_drug_name(value) or is_drug_shaped(value)
