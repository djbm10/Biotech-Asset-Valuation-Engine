"""Derive one asset's construct target set from its own direct mechanism evidence.

``TargetOperator.ALL`` -- "one molecule that hits all of these" -- is decided against a
``construct_target_set`` fact. The question it answers is about a construct, so the
evidence behind it has to be about that construct too, and almost everything a corpus
offers is not: two targets named in one trial record, two drugs co-administered in one
regimen, and the target a query was scoped to all describe a context rather than a
molecule. A set assembled from any of them would be an inference the sources never made,
and it would fail in the direction that matters -- admitting single-target assets to a
dual-target shortlist.

So this reads nothing but :attr:`CanonicalAsset.target_assertions`: per-asset assertions
already earned against the drug->target authority, from ``DIRECT_TARGET`` rows only. Family
and complex association rows reach the assertion as non-decisional supporting evidence and
are never part of a set, because a row naming a family asserts nothing about any one member.

The second rule is that silence is not denial. A set is emitted only when every requested
target has an answer. If the authority has never heard of an asset, or two authorities
disagree, no fact is produced and the gate returns UNKNOWN -- because a fact *is* read as a
complete description of the construct, so publishing a partial one would exclude the asset
for a reason the evidence never gave.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from bve.se.schemas.contracts import (
    CanonicalAsset,
    CandidateTargetAssertion,
    ExtractedClaim,
    NormalizedFact,
    SourceDocument,
    SourceTier,
    TargetAssertionStatus,
    TargetEvidenceRef,
    VerificationStatus,
)

#: Statuses that mean the authority answered the question, either way. Anything else --
#: silence, or a disagreement between sources -- leaves the construct undescribed.
_ANSWERED = frozenset(
    {TargetAssertionStatus.CONFIRMED_TARGET, TargetAssertionStatus.CONFIRMED_OTHER_TARGET}
)

EXTRACTOR_VERSION = "construct_target_authority_v1"

#: The authority is a pinned ontology snapshot, not a retrieval. Its claims carry the
#: snapshot's own release rather than a wall-clock time, so a rerun of the same snapshot
#: produces byte-identical claims and the fact ids stay stable.
_SNAPSHOT_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class ConstructTargetEvidence(BaseModel):
    """The fact, and everything needed to audit it, as one unit.

    The documents and claims travel with the fact because the ledger refuses a fact whose
    claims it has not seen -- which is the property that stops a conclusion from being
    recorded without the rows it rests on.
    """

    documents: list[SourceDocument] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    fact: NormalizedFact


def _id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _authority_document(ref: TargetEvidenceRef) -> SourceDocument:
    """One document per authority release, standing for the snapshot rows themselves."""

    return SourceDocument(
        document_id=_id("doc", "ontology", ref.source, ref.source_release),
        source_url=f"urn:ontology:{ref.source}:{ref.source_release}",
        publisher=ref.source,
        document_type="ontology_snapshot",
        retrieval_date=_SNAPSHOT_EPOCH,
        content_hash=_id("hash", ref.source, ref.source_release),
        source_tier=SourceTier.REGISTRY,
        public_only=True,
    )


def _passage(ref: TargetEvidenceRef) -> str:
    return json.dumps(
        {
            "source": ref.source,
            "source_release": ref.source_release,
            "source_record_id": ref.source_record_id,
            "relationship_type": ref.relationship_type,
            "canonical_target_id": ref.canonical_target_id,
            "evidence_hash": ref.evidence_hash,
        },
        sort_keys=True,
    )


def _decisive_evidence(
    assertions: list[CandidateTargetAssertion],
) -> list[TargetEvidenceRef]:
    """The direct rows behind the assertions, deduplicated and in a stable order.

    ``supporting_associations`` is deliberately not read. It is carried on an assertion so
    a reviewer can see why an UNRESOLVED candidate surfaced, and giving it any weight here
    would turn "this drug is in a family that includes the target" into "this drug binds
    the target".
    """

    seen: dict[str, TargetEvidenceRef] = {}
    for assertion in assertions:
        for ref in assertion.evidence:
            seen.setdefault(ref.evidence_hash, ref)
    return [seen[key] for key in sorted(seen)]


#: Words a record uses when it is saying what a product acts on, rather than merely
#: naming something. None of them is a target, so a cue token is never read as one.
_ATTRIBUTIVE_CUES = frozenset(
    {
        "directed",
        "targeting",
        "targeted",
        "targets",
        "against",
        "anti",
        "specific",
        "bispecific",
        "trispecific",
        "multispecific",
        "engager",
        "engaging",
        "car",
        "cart",
        "binding",
        "binder",
        "agonist",
        "antagonist",
        "inhibitor",
        "blocking",
        "blockade",
        "redirected",
    }
)

#: A symbol as sources write one: CD19, HER2, TNFRSF17, IL-2R. Prose words are lowercase
#: and so never qualify, which is what keeps "cells" and "infusion" out without naming
#: a single target.
_SYMBOL_SHAPE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")

#: How near an attributive cue a symbol has to sit to be attributed by it. Four tokens
#: spans "CD19-directed CD3 bispecific T-cell engager" without reaching across a sentence.
_CUE_WINDOW = 4


def attributed_targets_in(text: str) -> list[str]:
    """Targets a piece of text attributes to the product it is describing.

    Whole-token, cue-anchored and deliberately low-recall. A construct target set is one
    of the few facts where a miss is cheap -- the gate answers UNKNOWN and a human looks
    -- and a false member is not, because it silently satisfies a conjunction the asset
    does not satisfy.
    """

    tokens = re.split(r"[^A-Za-z0-9-]+", text)
    tokens = [token.strip("-") for token in tokens if token.strip("-")]
    cue_positions = [
        index
        for index, token in enumerate(tokens)
        for part in token.casefold().split("-")
        if part in _ATTRIBUTIVE_CUES
    ]
    if not cue_positions:
        return []
    found: set[str] = set()
    for index, token in enumerate(tokens):
        if not any(abs(index - cue) <= _CUE_WINDOW for cue in cue_positions):
            continue
        # The whole token first, because hyphens belong inside some symbols (IL-2R). If
        # it does not resolve the token is a compound, and *every* part is considered --
        # sources write dual constructs as "CD19-BCMA", and stopping at the first
        # resolving part silently turned those into single-target assets.
        # The length floor applies to the whole token too. The gene symbol "T" is real
        # (TBXT), and every "CAR T cell" in the corpus would otherwise assert it.
        whole = (
            _resolve_symbol(token)
            if len(token) >= 2 and _SYMBOL_SHAPE.match(token)
            else None
        )
        if whole:
            found.add(whole)
            continue
        for part in token.split("-"):
            if len(part) < 2 or part.casefold() in _ATTRIBUTIVE_CUES:
                continue
            if not _SYMBOL_SHAPE.match(part):
                continue
            resolved = _resolve_symbol(part)
            if resolved:
                found.add(resolved)
    return sorted(found)


def _resolve_symbol(symbol: str) -> str | None:
    from bve.se.ontology.targets import resolve_target

    result = resolve_target(symbol)
    if result is None or not result.canonical_id:
        return None
    return result.canonical_id


#: Nouns naming the product itself. A coordinated phrase that repeats one of these on
#: both sides is describing two products, not one with two arms.
_PRODUCT_HEADS = frozenset(
    {"car", "cart", "cells", "cell", "antibody", "engager", "injection", "infusion", "therapy"}
)

#: Coordinators a registry uses between two separately-administered products. "/" is
#: deliberately absent: "CD19/BCMA CAR-T" is how one dual construct is normally written.
_COORDINATORS = re.compile(r"\band\b|\bplus\b|\bor\b|\+|;|&", re.IGNORECASE)


def denotes_more_than_one_product(name: str) -> bool:
    """Whether a name coordinates two constructs rather than describing one.

    "Autologous BCMA CAR-T cells and CD19 CAR-T cells" is two infusions whose targets a
    dual-target question must never see unioned. "anti-CD19 and anti-BCMA CAR-T" is one
    construct with two binding arms, and reads differently for a reason a rule can see:
    the product noun appears once and is shared, rather than once on each side.
    """

    segments = [segment for segment in _COORDINATORS.split(name) if segment.strip()]
    if len(segments) < 2:
        return False
    described = 0
    for segment in segments:
        words = {word.strip("-").casefold() for word in re.split(r"[^A-Za-z0-9-]+", segment)}
        parts = {part for word in words for part in word.split("-")}
        if parts & _PRODUCT_HEADS and attributed_targets_in(segment):
            described += 1
    return described >= 2


#: Source-declared product structure that says outright this is more than one construct.
_COMBINATION_TYPES = frozenset({"COMBINATION_PRODUCT"})

#: Intervention types that denote a molecule. Radiation, procedures and devices have no
#: construct target set to describe, and in the live run a radiotherapy arm was attributed
#: the CAR-T its description said it was a bridge to -- a neighbour's target, not its own.
_MOLECULAR_TYPES = frozenset({"DRUG", "BIOLOGICAL", "GENETIC"})


def intervention_construct_targets(
    intervention: dict, *, intervention_type: str | None, vocabulary=None
) -> list[str] | None:
    """Targets an intervention record states about itself, or ``None``.

    The second admissible route, for the large majority of clinical-stage assets that a
    drug dictionary has never heard of. A registry intervention reading "CLN-978:
    CD19-directed CD3 bispecific T-cell engager" is a structured statement by the sponsor
    about one product, which is a different kind of evidence from two targets appearing
    somewhere in the same protocol.

    The boundary is the whole point, so it is drawn twice. Only the intervention's own
    ``name``, ``description`` and ``otherNames`` are read -- never the protocol, whose
    title and summary describe the study and therefore every arm in it. And nothing is
    returned for a record that denotes more than one molecule, because the union of a
    regimen's targets is exactly the false positive a dual-target question is most
    vulnerable to.

    Reading the right text is only half of it. The ontology vocabulary matches by
    substring, which is the right trade for discovery recall and catastrophic here: the
    description "CD19-targeting 2nd generation CAR t cells infusion" contains ``ar``,
    ``si`` and ninety more symbols as substrings, and a set of ninety targets is not a
    construct. It is also not merely noisy -- a large enough junk set eventually contains
    both halves of a dual-target question and passes it. So targets are read as whole
    symbol-shaped tokens, and only where the record attributes them to the product:
    "CD19-directed", "anti-CD19", "CD19xCD3". A symbol mentioned with no attributive cue
    is a mention, and mentions are what this route exists to not believe.

    ``vocabulary`` is accepted so callers can keep passing the one they hold, and is
    deliberately unused: substring recall is the thing this route must not inherit.
    """

    from bve.se.discovery.adapters import extract_observed_asset_names

    declared_type = (intervention_type or str(intervention.get("type", "") or "")).upper()
    if declared_type in _COMBINATION_TYPES:
        return None
    if declared_type and declared_type not in _MOLECULAR_TYPES:
        return None
    name = str(intervention.get("name", "") or "")
    other_names = intervention.get("otherNames") or []
    other_names_text = (
        " ".join(other_names) if isinstance(other_names, list) else str(other_names)
    )
    if len(extract_observed_asset_names(name)) > 1:
        return None
    if denotes_more_than_one_product(name):
        return None
    text = " ".join([name, str(intervention.get("description", "") or ""), other_names_text])
    targets = attributed_targets_in(text)
    if not targets:
        return None
    return canonical_construct_targets(targets)


def canonical_construct_targets(values) -> list[str]:
    """Target identifiers in the one space construct facts are written in.

    Both producers have to agree on spelling. The authority speaks canonical ids and the
    registry vocabulary speaks approved symbols, and two facts naming the same target in
    two spellings do not read as agreement -- they read as a contradiction, which the gate
    resolves as UNKNOWN. Normalizing here is what keeps a second producer from looking
    like a disagreement with the first.
    """

    from bve.se.ontology.targets import resolve_target

    canonical = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        result = resolve_target(text)
        canonical.add(
            result.canonical_id
            if result is not None and result.canonical_id
            else text.upper()
        )
    return sorted(canonical)


def supersede_construct_targets(
    facts: list[NormalizedFact], authority_fact: NormalizedFact
) -> list[NormalizedFact]:
    """Let the authority's construct set replace any other asset's construct set.

    Both routes are admissible, so an asset can end up with two. They are not merged and
    not left to argue: the gate treats competing target facts as UNKNOWN, so preserving a
    disagreement costs the asset the decision it would otherwise have had, and a curated
    drug->target edge is the better witness to what a molecule binds than a sponsor's
    description of it. The superseded claims remain in the evidence ledger.
    """

    kept = [fact for fact in facts if fact.fact_type != "construct_target_set"]
    return [*kept, authority_fact]


def construct_target_evidence(
    asset: CanonicalAsset, *, as_of_date: date
) -> ConstructTargetEvidence | None:
    """The asset's construct target set, or ``None`` when its evidence cannot say.

    ``None`` is not a negative answer and must not be turned into an empty set: an empty
    ``construct_target_set`` would satisfy no requirement and read as a construct
    documented to bind nothing.
    """

    assertions = list(asset.target_assertions)
    if not assertions:
        return None
    if any(assertion.status not in _ANSWERED for assertion in assertions):
        return None

    refs = _decisive_evidence(assertions)
    targets = sorted({ref.canonical_target_id for ref in refs if ref.canonical_target_id})
    if not targets:
        return None

    documents = {
        document.document_id: document
        for document in (_authority_document(ref) for ref in refs)
    }
    claims = [
        ExtractedClaim(
            claim_id=_id("claim", asset.asset_id, "construct_target_set", ref.evidence_hash),
            subject_id=asset.asset_id,
            predicate="construct_target_set",
            normalized_value=[ref.canonical_target_id],
            source_document_id=_authority_document(ref).document_id,
            supporting_passage=_passage(ref),
            locator=f"{ref.source}.{ref.relationship_type}.{ref.source_record_id}",
            direct_observation=True,
            extraction_method="drug_target_authority_direct_edge",
            extractor_version=EXTRACTOR_VERSION,
            extraction_confidence=0.95,
            verification_status=VerificationStatus.MACHINE_VERIFIED,
            applicable_as_of_date=as_of_date,
        )
        for ref in refs
        if ref.canonical_target_id
    ]
    fact = NormalizedFact(
        fact_id=_id("fact", asset.asset_id, "construct_target_set", *targets),
        subject_id=asset.asset_id,
        fact_type="construct_target_set",
        value=targets,
        supporting_claim_ids=[claim.claim_id for claim in claims],
        confidence=0.95,
    )
    return ConstructTargetEvidence(
        documents=list(documents.values()), claims=claims, fact=fact
    )
