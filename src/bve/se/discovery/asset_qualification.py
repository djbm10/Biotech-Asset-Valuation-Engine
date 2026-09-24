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

import enum
import re

from pydantic import BaseModel

from bve.se.discovery import class_terms, drug_name_shape

#: A development code is a shape, not the presence of a digit. Letters and digits adjacent
#: within a single token, optionally hyphenated: ``CCS1477``, ``SB-773812``, ``MK-3475A``.
#: The old test -- a digit anywhere in the string -- protected every statistic printed next
#: to a number, which is how a quartile range became an asset.
#:
#: A space is a separator too -- ``AMG 420`` is the same naming convention as ``SB-773812``,
#: written by a sponsor that does not hyphenate -- but it is admitted on stricter terms,
#: because with a space the string is two tokens and looks exactly like a statistic beside
#: its value. ``IQR 72`` is three letters and a number, as is ``AMG 420``; what separates
#: them is that a serial number is not quoted to two digits. Declared before measurement,
#: and the reason it is not simply "allow a space" is the regression the narrow form exists
#: to prevent, which is kept as a test.
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
    # "{name} therapy|treatment|injection|capsules" used to live here. It was the single
    # source of every ordinary word that reached the shortlist -- "safer therapy",
    # "cornerstone treatment", "frontline therapy" across 48 documents -- because it reads
    # the name in modifier position, where English admits any adjective. Removed rather than
    # patched: the construction is not evidence about the modifier, whatever fills it.
    r"{name}\s+was\s+(?:administered|given|dosed|initiated|infused)\b",
    r"{name}\s+\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|mg/kg|mg/m2|units?)\b",
    r"{name}-treated\b",
    r"{name}\s+arm\b",
)

#: Read only when the name is the *head* of the phrase, so a qualifier in front of it does
#: not lend it the noun's authority: "the {name} antibody" describes {name}, while "the
#: monoclonal antibody" describes nothing nominated.
_CONTEXT_HEAD = (r"\b(?:the|a|an)\s+{name}\s+(?:antibody|inhibitor|conjugate|regimen)\b",)


#: Nouns that name *care* rather than a molecule. A name immediately in front of one of these
#: is modifying it, and modifier position is a slot English grants to any adjective: "safer
#: therapy", "cornerstone treatment", "frontline chemotherapy" are the same construction as
#: "pembrolizumab therapy" and carry none of its evidence.
#:
#: This is the principle ``_CONTEXT_HEAD`` above already states -- a qualifier in front of a
#: noun does not borrow the noun's authority -- applied in the direction ``_CONTEXT_RIGHT``
#: was reading it backwards. One pattern, ``{name} (therapy|treatment|...)``, was the sole
#: source of every ordinary word that reached the shortlist.
#:
#: The veto is per-occurrence and deliberately blind to whether the name is real:
#: "Pomalidomide capsules" earns nothing, and pomalidomide qualifies through "treatment with
#: pomalidomide" instead. A rule that excused real drugs here would be a lexicon, not a rule.
_MODIFIED_HEAD = re.compile(
    r"\s+(?:mono)?(?:therapy|therapies|treatments?|chemotherapy|chemotherapies|regimens?"
    r"|settings?|agents?|options?|approach(?:es)?|strateg(?:y|ies)|care|management"
    r"|lines?|arms?|cohorts?|populations?|status|era"
    # Dosage forms belong here for the same reason, even though "Pomalidomide capsules"
    # really is a drug: the evidence is about the form, and "a safer injection" fills the
    # slot identically. Pomalidomide qualifies through "treatment with pomalidomide".
    r"|injections?|infusions?|tablets?|capsules?|solutions?)\b",
    re.IGNORECASE,
)

#: A parenthetical whose letters spell the words before it is an abbreviation of that phrase,
#: not a name of its own. This is one rule for two failures that looked unrelated:
#: "bispecific antibodies (bsAbs)" mints a class term, and "progression of disease within 24
#: months (POD24)" mints an outcome category through the development-code route.
#:
#: It must not catch a code in apposition to its own molecule -- "Inobrodib (CCS1477)" and
#: "etentamig (ABBV-383)" are synonyms, and their letters spell nothing. That asymmetry is
#: what makes the test mechanical rather than a judgement about which strings look like
#: outcomes, and it matters because measurement showed AMG 420 and CCS1477 have no
#: pharmacologic use evidence at all: the code route cannot be made conditional on use
#: without deleting them.
_GLOSS = re.compile(r"([^()]*?)\(\s*{name}\s*[,)\]]", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z]+|\d+")


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

#: Independent documents that must witness pharmacologic use before prose alone qualifies a
#: name. Two, because one is an accident: the live corpus contains exactly one "treated with
#: bsAbs", and a class abbreviation should not become an asset on the strength of a single
#: author's shorthand. Declared before measurement and not to be traded against anything --
#: this is a count of witnesses to one relation, not the frequency rule it replaced.
MIN_PHARMACOLOGIC_DOCUMENTS = 2


class AssetEvidence(BaseModel):
    """Everything known about a nominated name that bears on whether it is an asset."""

    name: str
    #: Distinct documents mentioning it. Recorded, but never sufficient on its own.
    support: int = 0
    #: A source declared, in a structured field of its own schema, that this names a drug.
    structurally_typed_drug: bool = False
    #: A document used the name the way documents use drug names. See the module docstring.
    pharmacologic_context: bool = False
    #: How many *distinct* documents did so. Corroboration, not frequency: the count is of
    #: independent witnesses to one relation, and it is never traded against anything. One
    #: unlucky sentence -- "treated with bsAbs" exists exactly once in the live corpus --
    #: must not qualify a class abbreviation.
    pharmacologic_documents: int = 0
    #: Structured observations of this name's role in a trial arm, counted rather than
    #: reduced. A registry genuinely does type placebo as a ``DRUG`` intervention, so the
    #: structured route is true and the conclusion is still wrong: a control arm is
    #: information about a trial, not a therapeutic asset.
    #:
    #: These are counts and not a boolean because v2's boolean was merged with ``all()``,
    #: so a single trial declaring no arm relationship retracted 34 explicit placebo arms
    #: and bare ``Placebo`` kept canonical status. ``unknown_observations`` exists to be
    #: counted and ignored: silence is not a therapeutic declaration.
    comparator_observations: int = 0
    specific_comparator_observations: int = 0
    therapeutic_observations: int = 0
    unknown_observations: int = 0
    #: An entity-specific link: a trial, an owner, or an attributed target for *this* name.
    #: Deliberately excludes ``discovery_target_context`` and modality, which are
    #: co-occurrence: measured on live data, ``bsAbs``, ``frontline``, ``cornerstone`` and
    #: ``ASCO 2023`` all carry those and no entity link at all.
    entity_specific_link: bool = False
    #: Every occurrence of the name is a parenthetical abbreviation of the phrase before it.
    #: Applied to the routes that need no corpus evidence, because those are exactly the
    #: routes a gloss can otherwise walk through: "(POD24)" has the shape of a sponsor code.
    #: A construct or target description vouched for this name. Corroboration only since
    #: v3: ``choice`` reached the default path and carried a human-PoC PASS on nothing but
    #: this, having been matched to the warfarin brand and credited with a VKORC1 assertion.
    #: A statement about a target does not establish that a string denotes a therapeutic.
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
    for pattern in _patterns(name):
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if not _is_modifier_occurrence(text, name, match):
                return True
    return False


def _is_modifier_occurrence(text: str, name: str, match: re.Match[str]) -> bool:
    """Whether this occurrence has the name modifying a head noun that follows it.

    Located from the end of the *name* rather than the end of the match, because the leaking
    patterns come in both directions: "safer therapy" ends at the head noun, while "treated
    with frontline chemotherapy" matches only as far as "frontline" and leaves the head noun
    outside the match entirely.
    """

    occurrence = re.search(re.escape(name.strip()), match.group(0), re.IGNORECASE)
    if occurrence is None:
        return False
    return _MODIFIED_HEAD.match(text, match.start() + occurrence.end()) is not None


def is_abbreviation_gloss(text: str, name: str) -> bool:
    """Whether ``text`` introduces ``name`` as a parenthetical abbreviation of the phrase
    immediately before it.

    Compares the name's letters against the initials of the preceding words, and its digits
    against a number in that phrase, so "progression of disease within 24 months (POD24)"
    is recognised and "Inobrodib (CCS1477)" is not.
    """

    cleaned = " ".join(name.split())
    if not cleaned:
        return False
    for match in re.finditer(
        _GLOSS.pattern.replace("{name}", re.escape(cleaned)), text, re.IGNORECASE
    ):
        if _initials_spell(match.group(1), cleaned):
            return True
    return False


def _initials_spell(phrase: str, name: str) -> bool:
    """Whether the words of ``phrase`` begin with the letters of ``name``, in order.

    Function words are skipped when they do not help, because an expansion writes "of" and
    "within" into the phrase and not into the abbreviation. Digits must appear in the phrase
    as a number; "POD24" needs a 24 in front of it, which is what separates an outcome
    definition from a sponsor's code.
    """

    letters = "".join(character for character in name if character.isalpha()).lower()
    digits = "".join(character for character in name if character.isdigit())
    words = _WORD.findall(phrase)
    if not letters or not words:
        return False
    if digits and digits not in words:
        return False
    alphabetic = [word.lower() for word in words if word.isalpha()]
    # The expansion need not sit flush against the parenthesis: "progression of disease
    # within 24 months (POD24)" spells POD in its first three words and then qualifies
    # itself for four more. So every starting word is tried, and the match may end before
    # the phrase does.
    return any(_spells(alphabetic[start:], letters) for start in range(len(alphabetic)))


def _spells(words: list[str], letters: str) -> bool:
    """Whether ``words`` in order account for every letter of ``letters``.

    A word may supply more than one letter, because expansions are not always initialisms:
    "bispecific antibodies" gives "bsAbs", where *bispecific* supplies ``bs`` and
    *antibodies* supplies ``abs``. Each word's letters must appear in it in order and start
    at its first character, which is what keeps "Inobrodib" from spelling "CCS1477".
    """

    if not letters:
        return True
    if not words:
        return False
    word, rest = words[0], words[1:]
    for take in range(1, len(letters) + 1):
        if not _is_ordered_prefix(word, letters[:take]):
            break
        if _spells(rest, letters[take:]):
            return True
    return False


def _is_ordered_prefix(word: str, letters: str) -> bool:
    """Whether ``letters`` occur in ``word`` in order, beginning at its first character."""

    if not word.startswith(letters[:1]):
        return False
    position = 0
    for letter in letters:
        position = word.find(letter, position)
        if position < 0:
            return False
        position += 1
    return True


class QualificationReason(str, enum.Enum):
    """Why a name is allowed to carry a decision.

    Every default-path asset must expose one. v2 made the qualification decision single but
    left it anonymous, and an anonymous decision cannot be audited: ``paper`` and ``choice``
    both reached the default path through routes nobody could see from the output, and
    finding out which took a trace through four modules. A named reason turns that into a
    field.

    Absence is itself a decision: :func:`qualification_reason` returns ``None`` and the
    caller fails closed to review.
    """

    #: The ontology holds this string as a molecule's own identity.
    DIRECT_APPROVED_NAME = "DIRECT_APPROVED_NAME"
    #: Development-code shape, corroborated by an entity-specific link.
    DEVELOPMENT_CODE_AUTHORITY = "DEVELOPMENT_CODE_AUTHORITY"
    #: A structured source placed this intervention in an experimental or active arm.
    STRUCTURED_THERAPEUTIC = "STRUCTURED_THERAPEUTIC"
    #: A synonym or trade name of some molecule, plus an independent entity link.
    ENTITY_CORROBORATED_SYNONYM = "ENTITY_CORROBORATED_SYNONYM"
    #: A construct or target description, plus an independent entity link.
    CONSTRUCT_CORROBORATED = "CONSTRUCT_CORROBORATED"
    #: Pharmacologic use across independent documents, plus an entity link.
    ENTITY_CORROBORATED_PROSE = "ENTITY_CORROBORATED_PROSE"


def is_comparator_only(evidence: AssetEvidence) -> bool:
    """Whether every structured observation of this name made it control material.

    Conservative on purpose, and asymmetric on purpose. One genuine therapeutic observation
    is enough to establish that a molecule is a therapy, because a drug used as a control in
    one trial is still that drug. An *unknown* observation establishes nothing and must not
    cancel an explicit comparator declaration -- which is exactly what ``all()`` did to bare
    ``Placebo``, whose 35 trials include one that types no arm.
    """

    # v4 §3a. An entity-specific comparator observation -- this intervention alone occupying
    # a control arm -- is dominant, and one is enough. It does not have to beat the
    # therapeutic count, because those observations come from arm type, and arm type is a
    # property of the arm: a blinded ``EXPERIMENTAL`` arm listing the active drug beside its
    # own placebo says nothing about the placebo. Bare ``Placebo`` is the sole occupant of 28
    # control arms and sits inside 12 such blinded arms, and v3 admitted it on the 12.
    if evidence.specific_comparator_observations > 0:
        return True
    return evidence.comparator_observations > 0 and evidence.therapeutic_observations == 0


def qualification_reason(evidence: AssetEvidence) -> QualificationReason | None:
    """The single authority. Returns *why* the name qualifies, or ``None``.

    The routes are alternatives rather than a score, but they are no longer peers: v3 splits
    them into evidence that decides on its own and evidence that may only corroborate. The
    invariant is that no single weak evidence type may independently promote an ambiguous
    string into the therapeutic-asset population.

    Order matters only for reporting -- the strongest true reason is the one returned, so
    the distribution reads as an audit rather than as an accident of evaluation order.
    """

    name = evidence.name.strip()
    if not name:
        return None

    # v4 §3c. The abbreviation-gloss veto is deliberately absent. v2 and v3 preregistered it
    # for the human-PoC fact -- "bispecific antibodies (bsAbs)" does not report an outcome for
    # bsAbs -- and v3 then carried it into routing, where nothing had been declared. It cost
    # SYNCAR-001, a real asset every one of whose mentions is parenthetical, and it bought
    # nothing: `POD24` and `bsAbs` were already held for review by the fix-off control. Routing
    # is decided by the evidence below, and the gloss test stays in ``human_poc`` where it was
    # written to act.

    # --- vetoes that precede every route -------------------------------------------------

    # v5. A class label denotes a set of assets and cannot be a member of it. This sits above
    # the ontology route rather than below it because the ontology is exactly what admitted
    # the class term: `CART19` is carried as an identity-bearing name, so every route below
    # would return before any of them could be asked whether the name names one molecule.
    # Its trials, owners and target edges survive -- grouping is what a class label is for --
    # but it does not stand in the population it groups.
    if class_terms.is_class_term(name):
        return None

    # --- routes that decide on their own -------------------------------------------------

    # The ontology's own identity for a molecule: APPROVED_NAME, canonical symbol or label,
    # or a development code. Narrowed in v3 -- SYNONYM and TRADE_NAME moved below, because
    # `paper` is a ChEMBL synonym and reached shortlist position 10 on the strength of it.
    if drug_name_shape.is_identity_bearing_drug_name(name):
        return QualificationReason.DIRECT_APPROVED_NAME

    # Control material does not become an asset by being well documented. The veto sits
    # below the ontology route -- a real molecule used as a control is in the lexicon and has
    # already returned -- and above everything else, because `Placebo` carries 35 trials and
    # 30 owners and would otherwise qualify on those.
    if is_comparator_only(evidence):
        return None

    # A structured source that says, in a field of its own schema, both that this is a drug
    # and that it is being *given as a therapy*. The second half is new in v3: structured
    # typing alone typed placebo as a DRUG, which is true and not the question.
    if evidence.structurally_typed_drug and evidence.therapeutic_observations > 0:
        return QualificationReason.STRUCTURED_THERAPEUTIC

    # --- routes that need corroboration --------------------------------------------------

    # Everything below is a guess about a string, and a guess needs an entity. A class term
    # has pharmacologic grammar and no entity: measured live, `bsAbs` occurs in argument
    # position across independent documents -- correctly, since bispecific antibodies really
    # are given to patients -- with no trial, no owner and no attributed target.
    if not evidence.entity_specific_link:
        return None

    # A synonym or brand, now that something else has established there is an entity here.
    # This is what keeps Keytruda, Enhertu and legacy INN spellings while dropping `paper`,
    # `choice` and `frontline`, which carry no entity of their own.
    if drug_name_shape.is_corroborative_drug_name(name):
        return QualificationReason.ENTITY_CORROBORATED_SYNONYM

    # A construct or target description. Corroboration since v3 and never a route of its
    # own: a VKORC1 assertion about the warfarin brand says nothing about whether the
    # English word "choice" denotes a therapeutic.
    if evidence.identity_authority:
        return QualificationReason.CONSTRUCT_CORROBORATED

    # Code shape is a fallback, never a route of its own. Standing alone it protected
    # `POD24`, and widening it to catch `AMG 420`'s space separator promoted `NEJM 2011`,
    # `ASCO 2023` and `WHO 2022`. Sponsor codes are recovered by the ontology route above,
    # under a separator-insensitive lookup; this catches a code no authority knows yet.
    if is_development_code(name):
        return QualificationReason.DEVELOPMENT_CODE_AUTHORITY

    # Prose context is the weakest route and the only one a word can occupy by accident:
    # "received before" and "although antibody" are ordinary sentences in which an ordinary
    # word fills the slot a drug name would fill. No pattern can tell those apart from
    # "received benzhexol" by looking at the sentence, because the sentences are identical
    # in shape. What separates them is the name's grammatical position -- the modifier veto
    # in ``has_pharmacologic_context`` -- then corroboration across documents, then the
    # entity link above.
    #
    # The corpus ceiling stays and can no longer be the main guard. The measurement that
    # shows why is worth keeping: over the live corpus `gemcitabine` occurs in 30 documents
    # against `cornerstone`'s 34, `safer`'s 39 and `bsAbs`'s 48. Any ceiling low enough to
    # veto the junk deletes real drugs.
    witnessed = max(evidence.pharmacologic_documents, int(evidence.pharmacologic_context))
    if witnessed >= MIN_PHARMACOLOGIC_DOCUMENTS and not _saturates_corpus(evidence):
        return QualificationReason.ENTITY_CORROBORATED_PROSE
    return None


def qualifies_by_authority(evidence: AssetEvidence) -> bool:
    """Whether the name qualifies through evidence that decides on its own.

    Kept so routing can tell an authority-grade name from a corroborated one, without any
    caller getting to keep its own idea of what an authority is.
    """

    return qualification_reason(evidence) in {
        QualificationReason.DIRECT_APPROVED_NAME,
        QualificationReason.STRUCTURED_THERAPEUTIC,
    }


def qualifies_as_asset(evidence: AssetEvidence) -> bool:
    """Whether this name may carry a decision. See :func:`qualification_reason`."""

    return qualification_reason(evidence) is not None


def _saturates_corpus(evidence: AssetEvidence) -> bool:
    """Whether the name is too common in the corpus to be a name."""

    if evidence.corpus_documents <= 0:
        return False
    # A multi-token name is a phrase, and a phrase made of common words is a different
    # failure with a different remedy; the ceiling declines to judge it.
    if len(_TOKEN.findall(evidence.name.casefold())) != 1:
        return False
    return evidence.document_frequency > MAX_DOCUMENT_FRACTION * evidence.corpus_documents
