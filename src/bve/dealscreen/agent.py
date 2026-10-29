"""Bounded diligence agent: investigates open questions, proposes facts, decides nothing.

A provider receives one asset and one question and returns :class:`AgentFinding` objects.
Each finding has:
- a citation (URL and title) and the document date;
- the exact evidence span;
- the extraction's limitations;
- any imported claims it contradicts.

Findings are proposals. They change nothing until an analyst confirms one in the decision
log (``CONFIRM_FINDING``), and a model or extractor confidence score is never stored as a
substitute for that.

Providers:
- ``OfflineEvidenceProvider``: reads a local evidence library (JSON) with deterministic
  extractors. Used by tests and by the demo, and it works with no network or key.
- ``ClinicalTrialsGovProvider``: public ClinicalTrials.gov records for the asset's own
  registered trial IDs, via BVE's existing fetch and normalizer. Public data only, and
  bounded to ``max_trials`` requests per question.
- An LLM provider can implement the same protocol later. None is bundled, and no provider
  here claims access to commercial databases.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

from bve.dealscreen.commercial import rights_status
from bve.dealscreen.facts import TargetNormalizer, mechanism_direction
from bve.dealscreen.models import AgentFinding, LandscapeAsset

logger = logging.getLogger(__name__)


class Question(str, Enum):
    TARGET = "Is this program actually directed at the specified target?"
    STAGE = "What is its verified clinical development stage?"
    US_RIGHTS = "Are there known restrictions on U.S. development or commercialization rights?"
    MECHANISM = "What evidence supports or contradicts the claimed mechanism?"
    PRIORITY = "Which diligence questions would most affect this opportunity?"


class DiligenceProvider(Protocol):
    name: str

    def investigate(self, asset: LandscapeAsset, question: Question) -> list[AgentFinding]: ...


@dataclass(frozen=True)
class Document:
    url: str
    title: str
    document_date: date | None
    text: str
    #: The date as written when it is not a full ISO date ("2016-10", "2016"), else None.
    date_as_written: str | None = None


def parse_document_date(raw: object) -> tuple[date | None, str | None]:
    """A full ISO date, or (None, the text) for a partial or unreadable date (cycle C1 X2)."""
    text = str(raw or "").strip()
    if not text:
        return None, None
    try:
        return date.fromisoformat(text), None
    except ValueError:
        return None, text


#: Split after sentence punctuation that follows a lowercase letter, digit or ")", so an
#: abbreviation such as "U.S." does not end a sentence.
_SENTENCE = re.compile(r"(?<=[a-z0-9)][.!?])\s+(?=[A-Z])")
_TARGET_PHRASE = re.compile(
    r"\b(?:targeting|targets|directed (?:at|against)|binds(?: to)?|anti-)\s*([A-Za-z0-9][A-Za-z0-9\-]{1,15})",
    re.IGNORECASE,
)
_PHASE = re.compile(r"\bphase\s*(1/2|2/3|1b?|2a?|2b|3|i{1,3})\b", re.IGNORECASE)
_PHASE_ORDER = {"1": 2, "1b": 2, "1/2": 2, "i": 2, "2": 3, "2a": 3, "2b": 3, "2/3": 3, "ii": 3,
                "3": 4, "iii": 4}
_PHASE_LABEL = {2: "Phase 1", 3: "Phase 2", 4: "Phase 3"}


#: A stated U.S. FDA approval of the named asset (cycle A5 K2).
#: U.S. approval phrasings (cycle A5 K2, widened after review A5-3).
_US_APPROVAL_PHRASE = re.compile(
    r"\bapproved by (?:the )?(?:\w+ and )?(?:the )?(?:u\.?s\.? )?(?:food and drug administration|fda)\b"
    r"|\b(?:u\.?s\.? )?(?:fda|food and drug administration)(?: has)? approved\b"
    r"|\b(?:fda|u\.?s\.?) approval (?:of|for)\b"
    r"|\breceived (?:u\.?s\.? )?(?:fda|food and drug administration) approval\b"
    r"|\bapproved in the (?:u\.?s\.?|united states)\b",
    re.IGNORECASE)
#: Hedges, negations and non-initial approvals, checked inside the approval clause only (review A5-3/4).
_NOT_APPROVED = re.compile(
    r"\b(?:not|no longer|seeking|submitted|submission|accepted for|under review|pending|plans? to|"
    r"expect(?:s|ed)?|anticipat\w*|potential|if approved|supplemental|sbla|snda|label expansion)\b",
    re.IGNORECASE)
_APPROVAL_CLAUSE = re.compile(r"[;,]|\bwhile\b|\bwhereas\b|\bbut\b|\bwith\b", re.IGNORECASE)
US_MARKETED_VALUE = "Marketed in U.S. (FDA approval stated in source)"


def us_approval_stated(sentence: str, names: list[str]) -> bool:
    """A clause of the sentence names the asset and states its U.S. FDA approval (cycle A5 K2).

    The name, the approval phrase and the absence of hedges are all checked inside one clause, so
    "X is used with Y, approved by the FDA" or "following FDA approval of Y, X entered Phase 3" do
    not count for X. Conservative: a name separated from the phrase by a comma is missed.
    """
    keys = [n.casefold() for n in names if len(n) >= 3]
    for clause in _APPROVAL_CLAUSE.split(sentence):
        if not _US_APPROVAL_PHRASE.search(clause) or _NOT_APPROVED.search(clause):
            continue
        if any(k in clause.casefold() for k in keys):
            return True
    return False


def _names(asset: LandscapeAsset) -> list[str]:
    return [asset.program_name, *asset.aliases]


def _mentions(sentence: str, names: list[str]) -> bool:
    folded = sentence.casefold()
    return any(name.casefold() in folded for name in names if len(name) >= 3)


def _finding_id(asset_id: str, field: str, url: str, value: str, span: str) -> str:
    digest = hashlib.sha256(f"{asset_id}|{field}|{url}|{value}|{span}".encode()).hexdigest()[:16]
    return f"finding:{digest}"


class TextExtractor:
    """Deterministic, sentence-level extraction. Its limits are written into each finding."""

    LIMITS: tuple[str, ...] = (
        "Pattern-based extraction from one document sentence; not a human reading.",
        "A statement in a public document is not independent confirmation.",
    )

    def __init__(self, target_normalizer: TargetNormalizer, provider: str) -> None:
        self.normalize_target = target_normalizer
        self.provider = provider

    def extract(
        self,
        asset: LandscapeAsset,
        question: Question,
        documents: list[Document],
        now: str,
    ) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        names = _names(asset)
        for doc in documents:
            for sentence in _SENTENCE.split(doc.text):
                if not _mentions(sentence, names):
                    continue
                for field, value in self._read(question, sentence, names):
                    findings.append(self._finding(asset, question, field, value, doc, sentence, now))
        unique = {f.finding_id: f for f in findings}
        return [unique[k] for k in sorted(unique)]

    def _read(self, question: Question, sentence: str, names: list[str] | None = None) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if question in (Question.TARGET, Question.PRIORITY):
            for match in _TARGET_PHRASE.finditer(sentence):
                symbol = self.normalize_target(match.group(1))
                if symbol:
                    out.append(("target", symbol))
        if question in (Question.STAGE, Question.PRIORITY):
            orders = [_PHASE_ORDER[m.group(1).casefold()] for m in _PHASE.finditer(sentence)]
            if orders:
                out.append(("phase", _PHASE_LABEL[max(orders)]))
            if question is Question.STAGE and us_approval_stated(sentence, names or []):
                out.append(("development_status", US_MARKETED_VALUE))
        if question in (Question.US_RIGHTS, Question.PRIORITY) and re.search(r"\brights?\b|licen", sentence, re.IGNORECASE):
            status = rights_status(sentence)
            if status != "UNKNOWN":
                out.append(("us_rights", sentence.strip()))
        if question in (Question.MECHANISM, Question.PRIORITY):
            direction = mechanism_direction(sentence)
            if direction:
                out.append(("mechanism", sentence.strip()))
        return out

    def _finding(
        self, asset: LandscapeAsset, question: Question, field: str, value: str,
        doc: Document, sentence: str, now: str,
    ) -> AgentFinding:
        limitations = list(self.LIMITS)
        if doc.document_date is None and doc.date_as_written:
            limitations.append(f"Partial or unreadable date {doc.date_as_written!r}: exact date not known.")
        elif doc.document_date is None:
            limitations.append("The document has no date; currency cannot be judged.")
        current = [c for c in asset.claims_for(field)]
        contradicts = [c.claim_id for c in current if not _agrees(field, c.value_as_written, value, self)]
        if contradicts:
            limitations.append("Contradicts the imported source value; analyst must reconcile.")
        span = sentence.strip()
        return AgentFinding(
            finding_id=_finding_id(asset.asset_id, field, doc.url, value, span),
            asset_id=asset.asset_id,
            question=question.value,
            field=field,
            proposed_value=value,
            source_url=doc.url,
            source_title=doc.title,
            document_date=doc.document_date,
            evidence_span=span,
            provider=self.provider,
            limitations=limitations,
            contradicts_claim_ids=contradicts,
            retrieved_at=now,
        )


def _agrees(field: str, imported: str, proposed: str, extractor: TextExtractor) -> bool:
    if field == "target":
        return extractor.normalize_target(imported) == proposed
    if field == "phase":
        orders = [_PHASE_ORDER[m.group(1).casefold()] for m in _PHASE.finditer(imported)]
        return bool(orders) and _PHASE_LABEL.get(max(orders)) == proposed
    if field == "us_rights":
        return rights_status(imported) == rights_status(proposed)
    if field == "mechanism":
        return mechanism_direction(imported) == mechanism_direction(proposed)
    return imported == proposed


class OfflineEvidenceProvider:
    """Deterministic provider over a local JSON evidence library.

    Library format: ``{"documents": [{"url", "title", "date", "text"}]}``. Sentences that do
    not name the asset are ignored, so a library can hold documents for many assets.
    """

    name = "offline_evidence_library"

    def __init__(self, library: str | Path, target_normalizer: TargetNormalizer,
                 clock: Callable[[], str] | None = None) -> None:
        data = json.loads(Path(library).read_text(encoding="utf-8"))
        self.documents = [
            Document(url=d["url"], title=d["title"], document_date=parsed[0], text=d["text"],
                     date_as_written=parsed[1])
            for d in data["documents"]
            for parsed in [parse_document_date(d.get("date"))]
        ]
        self.extractor = TextExtractor(target_normalizer, self.name)
        self.clock = clock or (lambda: "offline")

    def investigate(self, asset: LandscapeAsset, question: Question) -> list[AgentFinding]:
        return self.extractor.extract(asset, question, self.documents, self.clock())


class ClinicalTrialsGovProvider:
    """Public ClinicalTrials.gov records for the asset's own registered trial IDs."""

    name = "clinicaltrials_gov_public"

    def __init__(self, target_normalizer: TargetNormalizer, *, max_trials: int = 5,
                 fetch: Callable[[str], dict] | None = None) -> None:
        if fetch is None:
            from bve.ingestion.clinicaltrials_gov import fetch_study

            fetch = fetch_study
        self.fetch = fetch
        self.max_trials = max_trials
        #: Fetch failures, kept so a caller can report what could not be checked.
        self.errors: list[str] = []
        self.extractor = TextExtractor(target_normalizer, self.name)

    def investigate(self, asset: LandscapeAsset, question: Question) -> list[AgentFinding]:
        from bve.se.universe.ctgov import normalize_study

        now = datetime.now(UTC).isoformat(timespec="seconds")
        trial_ids = sorted({
            t.strip() for c in asset.claims_for("trial_ids")
            for t in c.value_as_written.replace(",", ";").split(";") if t.strip().upper().startswith("NCT")
        })[: self.max_trials]
        documents: list[Document] = []
        for nct in trial_ids:
            try:
                record = normalize_study(self.fetch(nct))
            except Exception as exc:  # noqa: BLE001 - one unreachable record must not stop the rest
                logger.warning("ClinicalTrials.gov fetch failed for %s: %s", nct, exc)
                self.errors.append(f"{nct}: {exc}")
                continue
            if record is None:
                continue
            phases = ", ".join(str(p) for p in record.phases)
            interventions = "; ".join(
                f"{i.name} ({', '.join(i.other_names)})" if i.other_names else i.name
                for i in record.interventions
            )
            text = (
                f"{record.brief_title or ''}. Interventions: {interventions}. "
                f"Registered phase for {interventions}: {phases.replace('PHASE', 'Phase ')}. "
                f"{record.brief_summary or ''}"
            )
            documents.append(
                Document(url=record.url or f"https://clinicaltrials.gov/study/{nct}", title=record.brief_title or record.trial_id,
                         document_date=record.last_update_date, text=text)
            )
        findings = self.extractor.extract(asset, question, documents, now)
        note = ("A trial sponsor is not evidence of rights ownership; registry text is "
                "sponsor-maintained and may be out of date.")
        return [f.model_copy(update={"limitations": [*f.limitations, note]}) for f in findings]
