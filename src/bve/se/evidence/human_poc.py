"""Decide whether a human efficacy result exists for one asset, and cite it.

``human_poc_required`` asks a narrow question -- has this drug helped a person -- and
almost everything a corpus offers about a clinical-stage asset answers a different one.
A trial exists. A phase is listed. Patients enrolled. The drug was tolerated. Exposure
reached the expected range. Every one of those is true of an asset that has never shown a
benefit, so none of them may produce this fact.

What may produce it is a *reported* result on a disease-relevant endpoint: a response
rate, a remission count, a disease-activity improvement, with a value attached. The
distinction that does most of the work is between an endpoint and a result. Registry
protocols name endpoints in bulk and report nothing, and reading those as evidence would
mark the whole corpus proven.

The second rule is attribution, and it is the same rule the construct target set needed.
A combination trial reports one regimen's outcome. Giving that outcome to each component
would let an asset inherit evidence it never earned -- and inherit it from precisely the
kind of study a dual-target question is full of. So a result reaches an asset only when
the sentence reporting it names that asset and no other, or when the candidate *is* the
combination the result is about.

Silence stays silence. No result produces no fact, and the gate reads that as UNKNOWN, so
an asset goes to review rather than being excluded for evidence nobody published.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

from pydantic import BaseModel, Field

from bve.se.schemas.contracts import (
    ClinicalResult,
    ExtractedClaim,
    NormalizedFact,
    VerificationStatus,
)

EXTRACTOR_VERSION = "human_poc_v1"

#: Endpoint vocabulary that describes a disease outcome. Deliberately about the *kind* of
#: measurement, never about a particular disease or drug.
_EFFICACY_TERMS = (
    "response rate",
    "overall response",
    "objective response",
    "complete response",
    "partial response",
    "complete remission",
    "remission",
    "responder",
    "response",
    "survival",
    "progression-free",
    "disease activity",
    "disease control",
    "clinical improvement",
    "clinical benefit",
    "clinical response",
    "symptom improvement",
    "efficacy",
    "relapse-free",
    "event-free",
    "cure",
    "healing",
    "flare",
)

#: Measurements that say how much drug there was, or how the patient tolerated it. These
#: are what an asset has instead of efficacy, so a match here overrides a match above:
#: "incidence of adverse events" contains no efficacy term, but "response to treatment
#: and incidence of cytokine release syndrome" contains both.
_NON_EFFICACY_TERMS = (
    "adverse event",
    "adverse reaction",
    "toxicity",
    "toxicities",
    "tolerability",
    "tolerated",
    "safety",
    "dose-limiting",
    "dose limiting",
    "cytokine release",
    "neurotoxicity",
    "mortality rate",
    "pharmacokinetic",
    "pharmacodynamic",
    "concentration",
    "cmax",
    "auc",
    "half-life",
    "expansion",
    "persistence",
    "biomarker",
    "immunogenicity",
    "anti-drug antibod",
    "feasibility",
    "number of participants with",
    "incidence of",
)

#: Words that put a measurement in the future or the conditional. A plan to measure a
#: response rate is the single most common thing a registry says, and it is not a result.
_UNREPORTED_TERMS = (
    "will be",
    "will receive",
    "is planned",
    "are planned",
    "plan to",
    "aim to",
    "intend",
    "is to evaluate",
    "to assess",
    "to determine",
    "primary endpoint is",
    "primary outcome is",
    "endpoint is",
    # Past tense reads as a result and is not one: "the primary outcome was the response
    # rate at 16 weeks, defined as a 50% reduction" describes the ruler, not the reading.
    "primary endpoint was",
    "primary outcome was",
    "secondary endpoint",
    "secondary outcome",
    # A sentence comparing pre-specified groups is characterising a population.
    "were compared",
    "was compared",
    "outcome measure",
    "potential to",
    "promising",
    "may improve",
    "could improve",
    "need for",
    "warrant",
    "hypothesis",
    "we will",
)

#: Non-human evidence. An animal or dish result can be reported as precisely as a human
#: one, so the distinction has to be read from the sentence rather than from its form.
_NONHUMAN_TERMS = (
    "in vitro",
    "in-vitro",
    "ex vivo",
    "preclinical",
    "pre-clinical",
    "murine",
    "mouse",
    "mice",
    "rat ",
    "rats",
    "canine",
    "primate",
    "xenograft",
    "cell line",
    "animal model",
    "in a model of",
    "target cells",
)

#: Signals that the sentence is about people. Required rather than assumed: an abstract
#: that never says who was treated has not said the result is human.
_HUMAN_TERMS = (
    "patient",
    "participant",
    "subject",
    "recipient",
    "volunteer",
    "human",
    "individuals treated",
    "cohort",
    "case series",
)

#: Words joining one product to another, read *after* the asset's name. A sentence saying
#: the asset plus something else is reporting a regimen, and the regimen's outcome is not
#: the component's -- unless the candidate itself is that combination, which is handled by
#: matching the asset name first and longest.
_COMBINATION_TERMS = (
    " plus ",
    " and ",
    " with ",
    " combined with ",
    " in combination with ",
    " followed by ",
    " added to ",
    " alongside ",
)

#: The same test read *before* the name, minus the words that normally introduce the
#: treated asset rather than join it to another. "Treatment with X" and "patients treated
#: with X" are how a single-agent result is written, so " with " cannot be read leftwards
#: as coordination; " plus " can.
_PRECEDING_COMBINATION_TERMS = (
    " plus ",
    " combined with ",
    " in combination with ",
    " followed by ",
    " added to ",
    " alongside ",
)

#: Patient-selection prose. Eligibility criteria are written in the same vocabulary as
#: results -- "inadequate response to at least one prior therapy", "documented remission"
#: -- while describing who may enrol rather than what happened. On the live corpus this was
#: the *only* thing the prose route matched, so it is a first-class exclusion, not an edge
#: case.
_ELIGIBILITY_TERMS = (
    "inclusion criteria",
    "exclusion criteria",
    "eligib",
    "must have",
    "subject to sponsor review",
    "inadequate response",
    "refractory to",
    "failed at least",
    "prior to enrol",
    "at screening",
    "willing to",
    "able to provide",
)

#: A sentence long enough to be a concatenated field rather than a sentence has not said
#: that its number belongs to its verb. Registry text arrives as multi-thousand-character
#: blobs where a percentage and an efficacy word coincide by accident.
_MAX_SENTENCE_CHARS = 400

#: A reported quantity: a percentage, a proportion, or a count out of a total.
_VALUE = re.compile(
    r"\d+(?:\.\d+)?\s*%|\b\d+\s*(?:of|/|out of)\s*\d+\b|\bn\s*=\s*\d+\b", re.IGNORECASE
)


class EfficacyStatement(BaseModel):
    """One sentence that reports a human efficacy result for one named asset."""

    asset_name: str
    endpoint: str
    sentence: str
    value: str
    #: The document the sentence was read from, so the claim can be checked against it.
    document_id: str = ""


class HumanPoCEvidence(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)
    fact: NormalizedFact


def _id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _contains(text: str, terms) -> str | None:
    lowered = text.casefold()
    for term in terms:
        if term in lowered:
            return term
    return None


def result_supports_human_poc(result: ClinicalResult) -> bool:
    """Whether a structured clinical result reports human efficacy.

    Two independent reasons to refuse: the endpoint measures something other than
    benefit, or the endpoint measures benefit and no value was reported. Registry
    protocols supply the second case in bulk -- an outcome measure is an intention.
    """

    endpoint = f"{result.endpoint} {result.endpoint_family or ''}"
    if _contains(endpoint, _NON_EFFICACY_TERMS):
        return False
    if not _contains(endpoint, _EFFICACY_TERMS):
        return False
    if result.incomplete_reporting:
        return False
    return result.effect_size is not None


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.;])\s+|\n+", text) if part.strip()]


def efficacy_statements(
    text: str, *, asset_names, document_id: str = ""
) -> list[EfficacyStatement]:
    """Sentences in ``text`` that report a human efficacy result for one of these assets.

    Sentence-scoped on purpose. An abstract naming an asset in one sentence and a response
    rate in another has not said the second is about the first, and stitching them is the
    inference this layer exists to refuse.
    """

    names = sorted({str(name) for name in asset_names if str(name).strip()}, key=len, reverse=True)
    if not names:
        return []
    statements: list[EfficacyStatement] = []
    for sentence in _sentences(text):
        if len(sentence) > _MAX_SENTENCE_CHARS:
            continue
        if _contains(sentence, _ELIGIBILITY_TERMS):
            continue
        lowered = sentence.casefold()
        named = next((name for name in names if name.casefold() in lowered), None)
        if named is None:
            continue
        endpoint = _contains(sentence, _EFFICACY_TERMS)
        if endpoint is None:
            continue
        if _contains(sentence, _NON_EFFICACY_TERMS):
            continue
        if _contains(sentence, _UNREPORTED_TERMS):
            continue
        if _contains(sentence, _NONHUMAN_TERMS):
            continue
        if not _contains(sentence, _HUMAN_TERMS):
            continue
        value = _VALUE.search(sentence)
        if value is None:
            continue
        if _reports_a_regimen(sentence, named, names):
            continue
        statements.append(
            EfficacyStatement(
                asset_name=named,
                endpoint=endpoint,
                sentence=sentence,
                value=value.group(0),
                document_id=document_id,
            )
        )
    return statements


def _reports_a_regimen(sentence: str, named: str, names) -> bool:
    """Whether the sentence gives the result to more than the named asset.

    The test is what the sentence says *around the asset's own name*: a coordinator
    immediately after it joins it to another product. When the matched name is itself a
    combination -- the candidate being the combination product -- its own internal joining
    words are part of the name and are not read as coordination.
    """

    lowered = sentence.casefold()
    position = lowered.find(named.casefold())
    tail = lowered[position + len(named) :]
    head = lowered[:position]
    if any(tail.startswith(term) or tail.startswith(term.rstrip()) for term in _COMBINATION_TERMS):
        return True
    if any(head.endswith(term) for term in _PRECEDING_COMBINATION_TERMS):
        return True
    # Another asset named in the same sentence with its own result attached.
    others = [name for name in names if name.casefold() != named.casefold()]
    return any(name.casefold() in lowered for name in others)


def human_poc_evidence(
    asset_id: str,
    *,
    results,
    statements,
    as_of_date: date,
    claim_documents=None,
) -> HumanPoCEvidence | None:
    """One asset's ``human_poc_present`` fact, or ``None`` when nothing reports one.

    Both routes are admissible and mean the same thing: a structured clinical result that
    reports an efficacy endpoint, and a source sentence that reports one in prose. The
    structured route is preferred where a source publishes it, because it carries its own
    population and endpoint rather than having them read out of a sentence.
    """

    # A structured result cites the claims it was built from, so the document to check it
    # against is whichever document those claims came from.
    documents = dict(claim_documents or {})
    claims: list[ExtractedClaim] = []
    for result in results:
        if not result_supports_human_poc(result):
            continue
        source_document_id = next(
            (documents[claim_id] for claim_id in result.supporting_claim_ids if claim_id in documents),
            "",
        )
        passage = (
            f"{result.endpoint}: {result.effect_size}"
            f"{result.effect_unit or ''}"
            f" in {result.evaluable_patients or 'an unreported number of'} evaluable patients"
        )
        claims.append(
            ExtractedClaim(
                claim_id=_id(
                    "claim", asset_id, "human_poc_present", source_document_id, result.result_id
                ),
                subject_id=asset_id,
                predicate="human_poc_present",
                normalized_value=True,
                source_document_id=source_document_id,
                supporting_passage=passage,
                locator=f"clinical_result:{result.result_id}",
                direct_observation=True,
                extraction_method="structured_clinical_result",
                extractor_version=EXTRACTOR_VERSION,
                extraction_confidence=0.9,
                verification_status=VerificationStatus.MACHINE_VERIFIED,
                applicable_as_of_date=as_of_date,
                indication=result.indication or None,
                population=result.population or None,
                endpoint=result.endpoint,
            )
        )
    for statement in statements:
        claims.append(
            ExtractedClaim(
                # The document is part of the identity: two papers can report the same
                # sentence, and a claim is a statement *by a source*, not a string.
                claim_id=_id(
                    "claim", asset_id, "human_poc_present", statement.document_id, statement.sentence
                ),
                subject_id=asset_id,
                predicate="human_poc_present",
                normalized_value=True,
                source_document_id=statement.document_id,
                supporting_passage=statement.sentence,
                locator="abstract",
                direct_observation=True,
                extraction_method="reported_efficacy_sentence",
                extractor_version=EXTRACTOR_VERSION,
                extraction_confidence=0.7,
                verification_status=VerificationStatus.MACHINE_VERIFIED,
                applicable_as_of_date=as_of_date,
                endpoint=statement.endpoint,
            )
        )
    if not claims:
        return None
    fact = NormalizedFact(
        fact_id=_id("fact", asset_id, "human_poc_present"),
        subject_id=asset_id,
        fact_type="human_poc_present",
        value=True,
        supporting_claim_ids=[claim.claim_id for claim in claims],
        confidence=max(claim.extraction_confidence for claim in claims),
    )
    return HumanPoCEvidence(claims=claims, fact=fact)
