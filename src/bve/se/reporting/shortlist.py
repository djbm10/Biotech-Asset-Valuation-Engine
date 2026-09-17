"""A ranked, cited shortlist of the assets a run found.

``memo.render_search_memo`` reports on the *run*: coverage, gate audit, limitations. This
module reports on the *assets*, which is the question an operator actually asked. It composes
records the pipeline already produced --- candidates, gate evaluations, target assertions,
identity mentions, source documents, extracted claims, the review queue, the low-support
handle and the pairwise ranking --- and invents no new science.

Two disciplines run through it.

**Ordering declares what kind of thing it is.** ``ranking.rank_profiles`` is the scientific
ranker; when it produced entries, they win. A discovery-mode run produces none, because it has
no comparative clinical profiles to compare, so the fallback is a *declared display order*:
disposition, then the existing ``TargetAssertionStatus`` precedence, then evidence volume,
then the asset id. It carries no score and is not one. Inventing a weighted score here would
have created a second, unvalidated ranking model that looked exactly like the real one.

**Nothing is displayed without saying where it came from.** Three origins, because the engine
really does know these three different ways: a source document, a structured authority
(ChEMBL/Open Targets release records, which is how target attribution is established --- there
is no document to quote), and discovery context (``modality_id`` is read from the surrounding
trial text, which is why a junk candidate can carry one). A fact with no evidence is rendered
unresolved rather than omitted, because silence reads as absence of the property rather than
absence of knowledge.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from bve.se.gates.engine import PHASE_REQUIREMENT_ID
from bve.se.schemas.contracts import (
    CanonicalAsset,
    OverallDisposition,
    SourceEvidenceType,
    TargetAssertionStatus,
)

__all__ = [
    "Citation",
    "DisplayedFact",
    "EvidenceOrigin",
    "Shortlist",
    "ShortlistEntry",
    "build_shortlist",
    "render_shortlist",
]

DEFAULT_LIMIT = 10

#: Declared precedence for the display order, reusing the enum's own ordering rather than
#: attaching weights to it. Target-specific weighting is deliberately absent: the shortlist
#: must order a run about any target the same way.
_TARGET_PRECEDENCE = {
    status: index for index, status in enumerate(TargetAssertionStatus)
}

_NCT = re.compile(r"(NCT\d{8})")
_PUBMED = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)")
_DOI = re.compile(r"doi\.org/(10\.\S+)")


class EvidenceOrigin(str, Enum):
    """How the engine came to know a displayed fact."""

    SOURCE_DOCUMENT = "SOURCE_DOCUMENT"
    STRUCTURED_AUTHORITY = "STRUCTURED_AUTHORITY"
    DISCOVERY_CONTEXT = "DISCOVERY_CONTEXT"


class Citation(BaseModel):
    """One evidence record behind one displayed claim.

    Mirrors ``SourceEvidenceClaim``'s fields without being one: that contract is producer-side
    and minting it in a renderer would make the reporting layer look like a source of
    evidence. This is a projection of records that already exist.
    """

    model_config = ConfigDict(frozen=True)

    evidence_type: SourceEvidenceType
    origin: EvidenceOrigin
    source_family: str
    document_id: str | None = None
    #: The identifier the source itself uses -- NCT number, PMID, DOI, authority record id.
    #: ``document_id`` is an internal content hash and means nothing outside this engine.
    native_id: str | None = None
    url: str | None = None
    effective_date: str | None = None
    content_hash: str | None = None
    evidence_span: str | None = None
    structured_field: str | None = None


class DisplayedFact(BaseModel):
    """One line of an asset card, with the evidence for it and the reason it is believed."""

    model_config = ConfigDict(frozen=True)

    label: str
    evidence_type: SourceEvidenceType
    value: str | None
    origin: EvidenceOrigin | None = None
    citations: tuple[Citation, ...] = ()
    note: str | None = None


class ShortlistEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_id: str
    name: str
    position: int
    section: str
    disposition: str
    #: Only ever the scientific ranker's rank. The display order does not produce one.
    rank: int | None = None
    tier: str | None = None
    #: Always ``None`` for a display-ordered shortlist; the field exists so that a consumer
    #: cannot mistake position for score by finding nothing to check.
    score: float | None = None
    target_id: str | None = None
    target_status: str
    low_support: bool = False
    review_reasons: tuple[str, ...] = ()
    why: tuple[str, ...] = ()
    facts: tuple[DisplayedFact, ...] = ()
    citations: tuple[Citation, ...] = ()


class Shortlist(BaseModel):
    model_config = ConfigDict(frozen=True)

    problem_id: str
    run_id: str
    as_of_date: str
    ordering_basis: str
    entries: tuple[ShortlistEntry, ...] = ()
    #: Kept out of the shortlist but not out of the run: low-support nominations, visible on
    #: request. M18 routes them, it never deletes them.
    deferred: tuple[ShortlistEntry, ...] = ()
    counts: dict[str, int] = Field(default_factory=dict)
    notes: tuple[str, ...] = ()


def _native_id(url: str | None, locator: str | None = None) -> str | None:
    for text in (url or "", locator or ""):
        if match := _NCT.search(text):
            return match.group(1)
        if match := _PUBMED.search(text):
            return f"PMID:{match.group(1)}"
        if match := _DOI.search(text):
            return f"DOI:{match.group(1)}"
    if locator and ":" in locator:
        family, _, value = locator.partition(":")
        return f"PMID:{value}" if family.casefold() == "pubmed" else locator
    return locator or None


class _Index:
    """Lookup tables over one result, built once."""

    def __init__(self, result) -> None:
        self.documents = {doc.document_id: doc for doc in result.source_documents}
        self.mentions = {m.mention_id: m for m in result.identity_mentions}
        self.claims = {c.claim_id: c for c in result.claims}
        self.companies = {c.company_id: c for c in result.companies}
        self.gates = {g.subject_id: g for g in result.gate_evaluations}
        self.reviews: dict[str, list] = {}
        for item in result.review_queue:
            self.reviews.setdefault(item.subject_id, []).append(item)
        self.claims_by_subject: dict[str, list] = {}
        for claim in result.claims:
            self.claims_by_subject.setdefault(claim.subject_id, []).append(claim)

    def phase_decision(self, asset_id: str):
        """The phase gate's decision for this asset, or ``None`` if the query set no phase."""

        gate = self.gates.get(asset_id)
        if gate is None:
            return None
        return next(
            (
                decision
                for decision in gate.decisions
                if decision.requirement_id == PHASE_REQUIREMENT_ID
            ),
            None,
        )

    def documents_for(self, asset: CanonicalAsset) -> list:
        seen: dict[str, object] = {}
        for mention_id in asset.mention_ids:
            mention = self.mentions.get(mention_id)
            if mention is None:
                continue
            document = self.documents.get(mention.source_document_id)
            if document is not None:
                seen.setdefault(document.document_id, document)
        return list(seen.values())

    def document_citation(
        self,
        document,
        evidence_type: SourceEvidenceType,
        *,
        span: str | None = None,
        structured_field: str | None = None,
        locator: str | None = None,
    ) -> Citation:
        return Citation(
            evidence_type=evidence_type,
            origin=EvidenceOrigin.SOURCE_DOCUMENT,
            source_family=document.publisher,
            document_id=document.document_id,
            native_id=_native_id(document.source_url, locator),
            url=document.source_url,
            effective_date=(
                document.publication_date.isoformat() if document.publication_date else None
            ),
            content_hash=document.content_hash,
            evidence_span=span,
            structured_field=structured_field,
        )


def _identity_fact(asset: CanonicalAsset, index: _Index) -> DisplayedFact:
    citations = tuple(
        index.document_citation(document, SourceEvidenceType.IDENTITY_EVIDENCE)
        for document in index.documents_for(asset)
    )
    return DisplayedFact(
        label="Name",
        evidence_type=SourceEvidenceType.IDENTITY_EVIDENCE,
        value=asset.canonical_name,
        origin=EvidenceOrigin.SOURCE_DOCUMENT if citations else None,
        citations=citations,
        note=None if citations else "no source document is attached to this nomination",
    )


def _company_fact(asset: CanonicalAsset, index: _Index) -> DisplayedFact:
    citations = []
    for mention_id in asset.mention_ids:
        mention = index.mentions.get(mention_id)
        if mention is None or not mention.raw_company_name:
            continue
        document = index.documents.get(mention.source_document_id)
        if document is not None:
            citations.append(
                index.document_citation(
                    document,
                    SourceEvidenceType.COMPANY_OWNERSHIP_EVIDENCE,
                    span=mention.raw_company_name,
                    structured_field="lead_sponsor",
                )
            )
    names = [
        index.companies[company_id].canonical_name
        for company_id in asset.company_ids
        if company_id in index.companies
    ]
    if not citations:
        # A company id with nothing in the corpus naming the company is a linkage, not an
        # ownership claim. Printing the name anyway is the fabrication this layer exists to
        # avoid; naming the linkage keeps the information without asserting it.
        note = (
            f"linked to {', '.join(asset.company_ids)} by identity resolution, with no "
            "ownership evidence in this corpus"
            if asset.company_ids
            else "no company named in this corpus"
        )
        return DisplayedFact(
            label="Company",
            evidence_type=SourceEvidenceType.COMPANY_OWNERSHIP_EVIDENCE,
            value=None,
            note=note,
        )
    return DisplayedFact(
        label="Company",
        evidence_type=SourceEvidenceType.COMPANY_OWNERSHIP_EVIDENCE,
        value=", ".join(names) if names else citations[0].evidence_span,
        origin=EvidenceOrigin.SOURCE_DOCUMENT,
        citations=tuple(citations),
    )


def _modality_fact(asset: CanonicalAsset) -> DisplayedFact:
    if not asset.modality_id:
        return DisplayedFact(
            label="Modality",
            evidence_type=SourceEvidenceType.DISCOVERY_EVIDENCE,
            value=None,
            note="no modality was read from the surrounding text",
        )
    return DisplayedFact(
        label="Modality",
        evidence_type=SourceEvidenceType.DISCOVERY_EVIDENCE,
        value=asset.modality_id,
        origin=EvidenceOrigin.DISCOVERY_CONTEXT,
        note=(
            "read from the trial/protocol text this asset was discovered in, not asserted "
            "as a property of the molecule"
        ),
    )


_STAGE_PREDICATES = ("development_stage_order", "development_status", "development_stage")


def _phase_fact(asset: CanonicalAsset, index: _Index) -> DisplayedFact:
    value = asset.development_stage or asset.development_status
    citations = tuple(
        index.document_citation(
            index.documents[claim.source_document_id],
            SourceEvidenceType.DEVELOPMENT_STAGE_EVIDENCE,
            span=claim.supporting_passage,
            structured_field=claim.predicate,
            locator=claim.locator,
        )
        for claim in index.claims_by_subject.get(asset.asset_id, ())
        if claim.predicate in _STAGE_PREDICATES and claim.source_document_id in index.documents
    )
    # The gate, not the renderer, decides whether the phase matches. The decision is shown
    # beside the evidence that produced it rather than restated.
    decision = index.phase_decision(asset.asset_id)
    verdict = (
        f"phase gate {decision.status.value}: {decision.rationale}" if decision is not None else None
    )
    if value is None or not citations:
        note = (
            "no development stage was established for this candidate"
            if value is None
            else f"{value} carries no traceable stage claim in this corpus"
        )
        return DisplayedFact(
            label="Phase",
            evidence_type=SourceEvidenceType.DEVELOPMENT_STAGE_EVIDENCE,
            value=None,
            note=f"{note}; {verdict}" if verdict else note,
        )
    return DisplayedFact(
        label="Phase",
        evidence_type=SourceEvidenceType.DEVELOPMENT_STAGE_EVIDENCE,
        value=value,
        origin=EvidenceOrigin.SOURCE_DOCUMENT,
        citations=citations,
        note=verdict,
    )


def _target_fact(asset: CanonicalAsset) -> DisplayedFact:
    assertion = asset.target_assertions[0] if asset.target_assertions else None
    if assertion is None:
        return DisplayedFact(
            label="Target",
            evidence_type=SourceEvidenceType.TARGET_EVIDENCE,
            value=None,
            note="no target assertion was made for this candidate",
        )
    citations = tuple(
        Citation(
            evidence_type=SourceEvidenceType.TARGET_EVIDENCE,
            origin=EvidenceOrigin.STRUCTURED_AUTHORITY,
            source_family=ref.source,
            native_id=ref.source_record_id,
            effective_date=ref.source_release,
            content_hash=ref.evidence_hash,
            structured_field=(
                f"{ref.relationship_type} -> {ref.canonical_target_id}"
                if ref.canonical_target_id
                else ref.relationship_type
            ),
        )
        for ref in assertion.evidence
    )
    status = assertion.status
    value = (
        f"{status.value} {assertion.canonical_target_id}"
        if status is TargetAssertionStatus.CONFIRMED_TARGET
        else status.value
    )
    return DisplayedFact(
        label="Target",
        evidence_type=SourceEvidenceType.TARGET_EVIDENCE,
        value=value if citations else None,
        origin=EvidenceOrigin.STRUCTURED_AUTHORITY if citations else None,
        citations=citations,
        note=(
            None
            if citations
            else (
                f"{status.value}: no drug->target authority record backs this candidate, so "
                "the target is inferred from nothing stronger than discovery context"
            )
        ),
    )


def _why(asset: CanonicalAsset, index: _Index, *, low_support: bool) -> tuple[str, ...]:
    lines: list[str] = []
    documents = index.documents_for(asset)
    if asset.discovery_target_context:
        lines.append(
            "found while searching "
            + ", ".join(asset.discovery_target_context)
            + f"; named in {len(documents)} source documents"
        )
    assertion = asset.target_assertions[0] if asset.target_assertions else None
    if assertion is not None:
        sources = sorted({ref.source for ref in assertion.evidence})
        lines.append(
            f"target {assertion.canonical_target_id} is {assertion.status.value}"
            + (
                f", from {len(assertion.evidence)} authority records ({', '.join(sources)})"
                if sources
                else ", with no authority record backing it"
            )
        )
    if documents:
        families = sorted({document.publisher for document in documents})
        lines.append(f"{len(documents)} source documents: {', '.join(families)}")
    phase = index.phase_decision(asset.asset_id)
    if phase is not None and phase.status.value == "PASS":
        # Non-PASS decisions already surface through the gate loop below.
        lines.append(f"phase gate PASS: {phase.rationale}")
    gate = index.gates.get(asset.asset_id)
    if gate is not None:
        for decision in gate.decisions:
            if decision.status.value != "PASS" and decision.next_action:
                lines.append(f"{decision.gate_id}: {decision.rationale} {decision.next_action}")
    if low_support:
        lines.append(
            "held back from the shortlist: too few documents mention this name to tell a "
            "thin asset from an extraction artefact"
        )
    return tuple(lines)


def _entry(
    asset: CanonicalAsset,
    index: _Index,
    *,
    section: str,
    disposition: OverallDisposition,
    low_support: bool,
    position: int,
    ranked,
) -> ShortlistEntry:
    facts = (
        _identity_fact(asset, index),
        _company_fact(asset, index),
        _modality_fact(asset),
        _phase_fact(asset, index),
        _target_fact(asset),
    )
    citations: dict[tuple, Citation] = {}
    for fact in facts:
        for citation in fact.citations:
            citations.setdefault(
                (citation.evidence_type, citation.source_family, citation.native_id), citation
            )
    assertion = asset.target_assertions[0] if asset.target_assertions else None
    return ShortlistEntry(
        asset_id=asset.asset_id,
        name=asset.canonical_name,
        position=position,
        section=section,
        disposition=disposition.value,
        rank=ranked.rank if ranked is not None else None,
        tier=ranked.tier.value if ranked is not None else None,
        target_id=assertion.canonical_target_id if assertion else None,
        target_status=assertion.status.value if assertion else "NO_ASSERTION",
        low_support=low_support,
        review_reasons=tuple(item.reason for item in index.reviews.get(asset.asset_id, ())),
        why=_why(asset, index, low_support=low_support),
        facts=facts,
        citations=tuple(citations.values()),
    )


def build_shortlist(result, *, limit: int = DEFAULT_LIMIT) -> Shortlist:
    """Compose one run's records into the assets it found, in a declared order.

    ``limit`` caps what is *shown*; the counts always describe the whole run, so a short
    shortlist can never be mistaken for a small landscape.
    """

    index = _Index(result)
    by_id = {asset.asset_id: asset for asset in result.candidates}
    eligible = set(result.eligible_asset_ids)
    excluded = set(result.excluded_asset_ids)
    low_support = set(result.low_support_asset_ids or ())
    ranked_by_id = {entry.asset_id: entry for entry in result.ranking.ranked}
    ordering_basis = "pairwise_ranking" if ranked_by_id else "declared_display_order"

    shortlisted: list[tuple[tuple, CanonicalAsset, str, OverallDisposition, bool]] = []
    deferred: list[tuple[tuple, CanonicalAsset, str, OverallDisposition, bool]] = []
    for asset in result.candidates:
        if asset.asset_id in excluded:
            continue
        gate = index.gates.get(asset.asset_id)
        disposition = gate.disposition if gate is not None else OverallDisposition.UNRESOLVED
        thin = asset.asset_id in low_support
        section = "eligible" if asset.asset_id in eligible else "review"
        assertion = asset.target_assertions[0] if asset.target_assertions else None
        precedence = (
            _TARGET_PRECEDENCE[assertion.status] if assertion else len(_TARGET_PRECEDENCE)
        )
        ranked = ranked_by_id.get(asset.asset_id)
        key = (
            # A real rank supersedes the display order entirely, including across sections:
            # the scientific contract is not a tiebreak inside a presentation decision.
            0 if ranked is not None and ranked.rank is not None else 1,
            ranked.rank if ranked is not None and ranked.rank is not None else 0,
            0 if section == "eligible" else 1,
            precedence,
            -len(index.documents_for(asset)),
            -len(asset.mention_ids),
            asset.canonical_name.casefold(),
            asset.asset_id,
        )
        (deferred if thin else shortlisted).append((key, asset, section, disposition, thin))

    shortlisted.sort(key=lambda row: row[0])
    deferred.sort(key=lambda row: row[0])
    entries = tuple(
        _entry(
            asset,
            index,
            section=section,
            disposition=disposition,
            low_support=thin,
            position=position,
            ranked=ranked_by_id.get(asset.asset_id),
        )
        for position, (_key, asset, section, disposition, thin) in enumerate(
            shortlisted[:limit], start=1
        )
    )
    deferred_entries = tuple(
        _entry(
            asset,
            index,
            section="low_support",
            disposition=disposition,
            low_support=True,
            position=position,
            ranked=ranked_by_id.get(asset.asset_id),
        )
        for position, (_key, asset, section, disposition, thin) in enumerate(
            deferred[:limit], start=1
        )
    )
    counts = {
        "total_candidates": len(result.candidates),
        "eligible": len(eligible),
        "review": sum(1 for row in shortlisted if row[2] == "review"),
        "excluded": len(excluded),
        "low_support": len(low_support),
        "shown": len(entries),
    }
    notes: list[str] = []
    if ordering_basis == "declared_display_order":
        notes.append(
            "Order is a declared display order, not a score: this run produced no pairwise "
            "comparative profiles, so no asset has been ranked against another."
        )
    if not eligible and by_id:
        notes.append(
            "No candidate passed every gate; the shortlist is the review population, which "
            "is where an unresolved target or modality gate leaves an otherwise real asset."
        )
    return Shortlist(
        problem_id=result.problem_id,
        run_id=result.run_manifest.run_id,
        as_of_date=result.run_manifest.as_of_date.isoformat(),
        ordering_basis=ordering_basis,
        entries=entries,
        deferred=deferred_entries,
        counts=counts,
        notes=tuple(notes),
    )


#: How much of each list the default view shows. A real run attaches 145 documents to a
#: well-covered asset and repeats a gate rationale once per gate; printing all of it is how a
#: summary stops being read at all. Nothing is dropped from the object -- only from this view.
_BRIEF_CITATIONS = 6
_BRIEF_REASONS = 3
_BRIEF_WHY = 5


def _render_citation(citation: Citation, *, detail: bool = False) -> str:
    bits = [citation.source_family]
    if citation.native_id:
        native = citation.native_id
        if not detail and len(native) > 16:
            # Authority record ids are content hashes. The prefix locates the record in the
            # expanded view; the full value is one --detail away.
            native = native[:12] + "..."
        bits.append(native)
    if citation.effective_date:
        bits.append(f"({citation.effective_date})")
    return " ".join(bits)


def _brief(items: list[str], limit: int, noun: str) -> list[str]:
    if len(items) <= limit:
        return items
    return [*items[:limit], f"   ... and {len(items) - limit} more {noun} (--detail)"]


def _render_entry(entry: ShortlistEntry, *, detail: bool) -> list[str]:
    header = f"{entry.position}. {entry.name}"
    if entry.rank is not None:
        header += f"  [rank {entry.rank}, {entry.tier}]"
    if entry.section != "eligible":
        header += f"  [{entry.section.upper()}]"
    lines = [header]
    for fact in entry.facts:
        if fact.label == "Name":
            continue
        value = fact.value if fact.value is not None else "unresolved"
        line = f"   {fact.label}: {value}"
        if fact.note:
            line += f"  -- {fact.note}"
        lines.append(line)
    lines.append(f"   Disposition: {entry.disposition}")
    reasons = [f"   Review: {reason}" for reason in entry.review_reasons]
    lines.extend(reasons if detail else _brief(reasons, _BRIEF_REASONS, "review items"))
    why = [f"   Why: {line}" for line in entry.why]
    lines.extend(why if detail else _brief(why, _BRIEF_WHY, "reasons"))
    shown = entry.citations if detail else entry.citations[:_BRIEF_CITATIONS]
    citations = ", ".join(_render_citation(citation, detail=detail) for citation in shown)
    if not detail and len(entry.citations) > len(shown):
        citations += f", ... and {len(entry.citations) - len(shown)} more"
    lines.append(f"   Evidence: {citations or 'none'}")
    if detail:
        for fact in entry.facts:
            for citation in fact.citations:
                lines.append(
                    f"     - [{fact.label}/{citation.evidence_type.value}] "
                    f"{_render_citation(citation)}"
                )
                if citation.url:
                    lines.append(f"       {citation.url}")
                if citation.structured_field:
                    lines.append(f"       field: {citation.structured_field}")
                if citation.content_hash:
                    lines.append(f"       hash: {citation.content_hash}")
                if citation.evidence_span:
                    lines.append(f"       span: {citation.evidence_span}")
    return lines


def render_shortlist(shortlist: Shortlist, *, detail: bool = False) -> str:
    """The default human view: the assets, why each is there, and what backs each claim."""

    lines = [
        f"S&E shortlist for {shortlist.problem_id} (run {shortlist.run_id}, "
        f"as of {shortlist.as_of_date})",
        f"ordering: {shortlist.ordering_basis}",
        "",
    ]
    if not shortlist.entries:
        lines.append("No candidate survived to the shortlist.")
    for entry in shortlist.entries:
        lines.extend(_render_entry(entry, detail=detail))
        lines.append("")
    if shortlist.deferred:
        lines.append(
            f"Held back as low-support ({shortlist.counts.get('low_support', 0)} total, "
            f"{len(shortlist.deferred)} shown):"
        )
        for entry in shortlist.deferred:
            lines.append(f"   - {entry.name} ({entry.target_status})")
            if detail:
                lines.extend(_render_entry(entry, detail=True))
        lines.append("")
    counts = shortlist.counts
    lines.append(
        "Counts: "
        + ", ".join(
            f"{label} {counts.get(label, 0)}"
            for label in (
                "eligible",
                "review",
                "excluded",
                "low_support",
                "total_candidates",
                "shown",
            )
        )
    )
    for note in shortlist.notes:
        lines.append(f"Note: {note}")
    return "\n".join(lines)
