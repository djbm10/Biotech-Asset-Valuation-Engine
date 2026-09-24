"""A class label denotes a set of assets. It cannot be a member of that set.

The two invariants before this one asked whether a *string* was a drug name, and whether an
*evidence record* was about the object it was attached to. Both were satisfied, and
``CART19`` still held a human proof-of-concept verdict. Nothing was wrong with its evidence:
33 trials, 14 owners, a confirmed CD19 target assertion, the ontology carrying the string as
an identity name. The defect is that the 33 trials are 33 *different constructs*. "CD19
CAR-T" is a category with excellent evidence for being a category, and a decision about a
category is not a decision about an asset.

What separates the two is mechanical. Read a name as tokens and strike out everything that
describes a *kind* of therapy -- the modality it belongs to, the target it is aimed at, the
grammar joining them. Whatever is left is what individuates one molecule from its
neighbours. ``TAC01-CD19`` leaves ``TAC01``; ``ABBV-383`` leaves ``ABBV``;
``tisagenlecleucel`` leaves itself. ``CD19-targeted CAR-T cells`` leaves nothing, and
neither does ``CART19``, whose ``19`` is the target designation with the ``CD`` elided.

The one place this needs care is a number, because a sponsor serial and a CD antigen look
alike. ``CD19`` resolves in the ontology and ``CD088`` does not, which is the whole
discriminator -- and the ontology is the authority here rather than a list of CD numbers,
for the same reason the drug-shape model is trained rather than enumerated: a list only
knows the corpus it was written against. Zero padding decides the residual cases, since a
serial is quoted to a fixed width (``CAR088``) and an antigen never is.

Nothing here deletes. A class term keeps its trials, its owners and its target edges,
because grouping assets is the useful thing a class label does; it simply cannot stand in
the population as one of them.
"""

from __future__ import annotations

import re

from bve.se.ontology.targets import normalize_target

#: Vocabulary naming a *kind* of therapy. A name built only from these describes a class.
#: Plurals are listed rather than stemmed: "cells" is modality vocabulary, and a stemmer
#: that reached "cell" from it would also reach "celecoxib" from nothing in particular.
_MODALITY = frozenset(
    {
        "car",
        "cars",
        "cart",
        "carts",
        "t",
        "nk",
        "nkt",
        "tcr",
        "tcrs",
        "til",
        "tils",
        "bite",
        "bites",
        "adc",
        "adcs",
        "mab",
        "mabs",
        "bsab",
        "bsabs",
        "bispecific",
        "bispecifics",
        "trispecific",
        "monoclonal",
        "antibody",
        "antibodies",
        "cell",
        "cells",
        "therapy",
        "therapies",
        "vaccine",
        "vaccines",
        "degrader",
        "degraders",
        "aso",
        "asos",
        "sirna",
        "sirnas",
        "crispr",
        "lymphocyte",
        "lymphocytes",
        "construct",
        "constructs",
        "infusion",
        "product",
    }
)

#: Grammar that joins a modality to a target without naming anything. Struck out, but never
#: sufficient on its own -- a name made only of filler is not a class term, it is junk, and
#: junk is the previous milestone's business.
_FILLER = frozenset(
    {
        "anti",
        "dual",
        "target",
        "targeted",
        "targeting",
        "specific",
        "directed",
        "redirected",
        "autologous",
        "allogeneic",
        "humanized",
        "human",
        "murine",
        "chimeric",
        "armored",
        "positive",
        "based",
        "engineered",
        "modified",
        "derived",
        "receptor",
        "antigen",
        "and",
        "or",
        "the",
        "of",
        "with",
        "against",
    }
)

#: Token separators. Includes the registered-mark glyphs, which appear attached to trade
#: names in acquired prose and are not part of any name.
_SEPARATORS = re.compile(r"[\s\-/+(),\.;:_®™–—]+")

#: A modality glued to a number with no separator, as sponsors write it: ``CART19``,
#: ``CAR19``, ``ADC22``. Split here because tokenisation cannot see the boundary.
_GLUED_MODALITY_NUMBER = re.compile(
    r"^(car[-\s]?t|cart|car|bite|adc|tcr|tac|mab)[-\s]?(\d{1,3})$", re.IGNORECASE
)

#: A serial is quoted to a fixed width; an antigen designation is not. ``CAR088`` is the
#: eighty-eighth thing its sponsor numbered, and no ``CD088`` exists to confuse it with.
_ZERO_PADDED = re.compile(r"^0\d+$")


def _is_target_designation(token: str) -> bool:
    """Whether a token designates a target rather than individuating a molecule.

    A symbol counts when the ontology resolves it. A bare number counts when ``CD<n>``
    resolves -- the elision in ``CART19`` -- and never when it is zero padded.
    """

    token = token.strip()
    if not token:
        return False
    if token.isdigit():
        if _ZERO_PADDED.match(token):
            return False
        return normalize_target(f"CD{token}") is not None
    return normalize_target(token) is not None


def individuating_residue(name: str) -> tuple[str, ...]:
    """The tokens of *name* that individuate a molecule.

    Empty means every token described the kind of therapy rather than which one. This is
    the whole decision, exposed separately from :func:`is_class_term` so that a demotion can
    be explained in terms of what the engine did and did not find in the name.
    """

    stripped = name.strip()
    if not stripped:
        return ()

    glued = _GLUED_MODALITY_NUMBER.match(stripped)
    if glued is not None:
        number = glued.group(2)
        if _is_target_designation(number):
            return ()
        return (stripped,)

    residue: list[str] = []
    for token in _SEPARATORS.split(stripped):
        if not token:
            continue
        lowered = token.lower()
        if lowered in _MODALITY or lowered in _FILLER:
            continue
        if _is_target_designation(token):
            continue
        residue.append(token)
    return tuple(residue)


def is_class_term(name: str) -> bool:
    """Whether *name* denotes a category of assets rather than one asset.

    True when modality vocabulary, ontology-resolved target designations and grammatical
    filler exhaust the name, *and* at least one token was modality vocabulary. The second
    condition is what keeps this rule out of the junk-rejection business: ``CD19`` alone is
    a target symbol, not a class of therapies, and a bare filler word is an ordinary English
    word that the qualification layer already refuses for its own reasons.
    """

    stripped = name.strip()
    if not stripped:
        return False
    if individuating_residue(stripped):
        return False

    glued = _GLUED_MODALITY_NUMBER.match(stripped)
    if glued is not None:
        return True

    return any(
        token.lower() in _MODALITY for token in _SEPARATORS.split(stripped) if token
    )
