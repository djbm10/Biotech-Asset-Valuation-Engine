"""What a nominated prose token has to show before it can bear a decision.

Extraction nominates permissively and lets later gates decide; that division of labour is
right, and it is why this engine asserts so few false targets. But every gate downstream
had until now taken the nomination itself on trust, and the first stage to hand a nominated
name a decisive answer -- human proof of concept -- revealed what had been accumulating:
ordinary English words, promoted to decision-bearing assets, each correctly attributed an
efficacy result from a sentence it appeared in because appearing in sentences is what
ordinary words do.

Two things that look like evidence are not.

**Frequency is not evidence.** The commonest words are the most frequent tokens in any
corpus, so a support threshold selects *for* them. That is backwards, and it is why the old
``MIN_SUPPORT_UNKNOWN`` route let a preposition onto the default path.

**Shape is not evidence either.** The drug-shape model scores ordinary words and real
molecules alike, and it should: it was trained for recall across a space where molecules are
spelled inconsistently, and a model that could reject every English word would reject the
oddly-spelled drugs too. Shape nominates. It cannot qualify.

What separates a molecule from a word is that documents *treat it as a drug*: patients
receive it, it inhibits something, it is given at a dose. That is positive asset evidence,
it is observable in the text without a lexicon, and -- this is the point -- it is available
to real molecules the ontology has never heard of. A rule that rejects the observed junk is
worthless if it also rejects a drug whose only failing is being absent from ChEMBL.

None of this deletes anything. A name that fails qualification is routed to review with its
provenance intact and is promoted the moment qualifying evidence arrives.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from bve.se.discovery import drug_name_shape

#: A development code is a shape, not the presence of a digit. Letters and digits adjacent
#: within a single token, optionally hyphenated: ``CCS1477``, ``SB-773812``, ``MK-3475A``.
#: The old test -- a digit anywhere in the string -- protected every statistic printed next
#: to a number, which is how a quartile range became an asset.
_DEVELOPMENT_CODE = re.compile(
    r"^[A-Za-z]{1,6}-?\d{2,6}[A-Za-z]?(?:-[A-Za-z0-9]{1,6})?$"
)

#: How a document says, in prose, that a thing is a drug. Each is a syntactic relation
#: between the name and a pharmacologic verb or head noun -- not a keyword anywhere in the
#: document, which is why the patterns are anchored to the name itself.
#:
#: ``{name}`` is substituted with the escaped name at match time. Kept as templates rather
#: than one alternation so each relation can be read, and argued with, on its own.
_CONTEXT_LEFT = (
    r"treated with\s+{name}\b",
    r"treatment with\s+{name}\b",
    r"received\s+{name}\b",
    r"receiving\s+{name}\b",
    r"administration of\s+{name}\b",
    r"administered\s+{name}\b",
    r"dose of\s+{name}\b",
    r"doses of\s+{name}\b",
    r"therapy with\s+{name}\b",
    r"\bon\s+{name}\s+(?:were|was|for|at)\b",
    r"response to\s+{name}\b",
    r"efficacy of\s+{name}\b",
    r"safety of\s+{name}\b",
    r"\bwith\s+{name}\s+(?:continued|monotherapy)\b",
)

#: The same relation read rightwards: the name as the head of a pharmacologic phrase.
_CONTEXT_RIGHT = (
    r"{name}\s+(?:is|was|are|were)\s+(?:an?\s+)?(?:selective\s+|potent\s+|novel\s+)*"
    r"(?:inhibitor|antagonist|agonist|antibody|blocker|modulator|conjugate|prodrug)\b",
    r"{name}\s+(?:inhibitor|antagonist|agonist|antibody|blocker|modulator|conjugate)\b",
    r"{name}\s+(?:monotherapy|therapy|treatment|infusion|injection|tablets?|capsules?)\b",
    r"{name}\s+was\s+(?:administered|given|dosed|initiated|infused)\b",
    r"{name}\s+\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|mg/kg|mg/m2|units?)\b",
    r"{name}-treated\b",
    r"{name}\s+arm\b",
)

#: Read only when the name is the *head* of the phrase, so a qualifier in front of it does
#: not lend it the noun's authority: "the {name} antibody" describes {name}, while "the
#: monoclonal antibody" describes nothing nominated.
_CONTEXT_HEAD = (r"\b(?:the|a|an)\s+{name}\s+(?:antibody|inhibitor|conjugate|regimen)\b",)


_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]*")


def document_frequencies(texts) -> dict[str, int]:
    """How many documents each word token appears in, over the whole corpus.

    The generic stand-in for a dictionary, which this environment does not have. A function
    word occurs in a large fraction of any corpus; a molecule the ontology has never heard
    of occurs in the few documents that study it. Counting documents rather than
    occurrences keeps one verbose paper from looking like a language.
    """

    frequencies: dict[str, int] = {}
    for text in texts:
        for token in set(_TOKEN.findall(text.casefold())):
            frequencies[token] = frequencies.get(token, 0) + 1
    return frequencies


#: A ceiling, not a floor -- the opposite of the support rule this layer replaced, and it
#: is applied only to names with no external authority. Nothing outside the corpus vouches
#: for such a name, so the corpus is the only witness available, and what it says is this:
#: a function word occurs in a large fraction of every corpus ever assembled, while a
#: molecule the ontology has never heard of occurs in the handful of documents that study
#: it. Declared before measurement. A name that exceeds it is routed to review, not deleted.
MAX_DOCUMENT_FRACTION = 0.05


class AssetEvidence(BaseModel):
    """Everything known about a nominated name that bears on whether it is an asset."""

    name: str
    #: Distinct documents mentioning it. Recorded, but never sufficient on its own.
    support: int = 0
    #: A source declared, in a structured field of its own schema, that this names a drug.
    structurally_typed_drug: bool = False
    #: A document used the name the way documents use drug names. See the module docstring.
    pharmacologic_context: bool = False
    #: Another identity-bearing authority vouched for the name.
    identity_authority: bool = False
    #: Documents in the run. Zero disables the saturation ceiling, which is what a caller
    #: that does not know the corpus size should get: the ceiling is a veto on prose
    #: context, and a veto nobody can size is one that should not fire.
    corpus_documents: int = 0
    #: Documents containing this name as a word, from ``document_frequencies``. This is a
    #: property of the language, not of what the extractor happened to nominate -- the
    #: mention count measures the latter and a common word can have a low one.
    document_frequency: int = 0


def is_development_code(name: str) -> bool:
    """Whether the name has the shape of a development code.

    A shape claim about one token. ``IQR 72`` is two tokens and a statistic; ``SB-773812``
    is a code no lexicon will carry and no prose context may be required to vouch for.
    """

    return bool(_DEVELOPMENT_CODE.match(name.strip()))


def _patterns(name: str) -> list[str]:
    escaped = re.escape(name.strip())
    return [
        template.replace("{name}", escaped)
        for template in (*_CONTEXT_LEFT, *_CONTEXT_RIGHT, *_CONTEXT_HEAD)
    ]


def has_pharmacologic_context(text: str, name: str) -> bool:
    """Whether ``text`` uses ``name`` the way documents use the name of a drug.

    Anchored to the name on purpose. A document can describe a real drug in one sentence
    and a measurement timepoint in the next, and reading "treated with" as a property of
    the document rather than of the name is exactly how a timepoint becomes an asset.
    """

    if not name.strip():
        return False
    return any(
        re.search(pattern, text, re.IGNORECASE) for pattern in _patterns(name)
    )


def qualifies_as_asset(evidence: AssetEvidence) -> bool:
    """Whether this name may carry a decision.

    Any one positive route is enough, and the routes are alternatives rather than a score:
    each is independently sufficient evidence that something outside a frequency count
    considers this string a molecule. Support appears nowhere, deliberately.
    """

    name = evidence.name.strip()
    if not name:
        return False
    if (
        drug_name_shape.is_known_drug_name(name.casefold())
        or is_development_code(name)
        or evidence.structurally_typed_drug
        or evidence.identity_authority
    ):
        return True
    # Prose context is the weakest route and the only one a word can occupy by accident:
    # "received before" and "although antibody" are ordinary sentences in which an ordinary
    # word fills the slot a drug name would fill. No pattern can tell those apart from
    # "received benzhexol" by looking at the sentence, because the sentences are identical
    # in shape. What separates them is how much of the corpus the token appears in.
    return evidence.pharmacologic_context and not _saturates_corpus(evidence)


def _saturates_corpus(evidence: AssetEvidence) -> bool:
    """Whether the name is too common in the corpus to be a name."""

    if evidence.corpus_documents <= 0:
        return False
    # A multi-token name is a phrase, and a phrase made of common words is a different
    # failure with a different remedy; the ceiling declines to judge it.
    if len(_TOKEN.findall(evidence.name.casefold())) != 1:
        return False
    return evidence.document_frequency > MAX_DOCUMENT_FRACTION * evidence.corpus_documents
