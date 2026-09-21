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
