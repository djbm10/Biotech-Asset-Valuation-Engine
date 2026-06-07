"""Phase C automated evidence ingestion pipeline."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.dossier.asset_graph import CanonicalAssetGraph
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace

_AMOUNT_RE = r"([0-9]+(?:\.[0-9]+)?)\s*(million|billion)"
_CASH_RE = re.compile(
    rf"(?:cash(?: and cash equivalents)?(?:, cash equivalents and investments)?)[^$]{{0,80}}\$?\s*{_AMOUNT_RE}",
    re.IGNORECASE,
)
_DEBT_RE = re.compile(
    rf"(?:debt|long-term debt|total debt)[^$]{{0,80}}\$?\s*{_AMOUNT_RE}",
    re.IGNORECASE,
)
_SHARES_RE = re.compile(
    rf"(?:shares outstanding|diluted share count)[^0-9]{{0,30}}{_AMOUNT_RE}",
    re.IGNORECASE,
)
_BURN_RE = re.compile(
    rf"(?:quarterly burn|burn(?:ed)? approximately|cash burn)[^$]{{0,80}}\$?\s*{_AMOUNT_RE}",
    re.IGNORECASE,
)
_PROCEEDS_RE = re.compile(
    rf"(?:gross proceeds|proceeds of approximately|raised approximately)[^$]{{0,80}}\$?\s*{_AMOUNT_RE}",
    re.IGNORECASE,
)
_OFFERING_SHARES_RE = re.compile(
    r"(?:offering of|sold)\s+([0-9]+(?:\.[0-9]+)?)\s+million\s+shares",
    re.IGNORECASE,
)

_SOURCE_PRIORITY = {
    "clinicaltrials_gov": 1.0,
    "fda_website": 1.0,
    "sec_filing": 0.98,
    "pubmed": 0.93,
    "publication": 0.9,
    "conference_abstract": 0.82,
    "press_release": 0.8,
    "manual": 0.75,
}

_STALE_AFTER_DAYS = {
    "clinicaltrials_gov": 14,
    "fda_website": 30,
    "sec_filing": 95,
    "pubmed": 365,
    "publication": 365,
    "conference_abstract": 180,
    "press_release": 90,
    "manual": 30,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_status(value: str) -> str:
    normalized = "_".join(value.strip().lower().split())
    return normalized.replace("-", "_")


def _amount_to_millions(number: str, unit: str) -> float:
    value = float(number)
    if unit.lower() == "billion":
        value *= 1000.0
    return round(value, 4)


class EvidenceProvenance(BaseModel):
    source_type: str
    source_url: Optional[str] = None
    raw_document_id: Optional[str] = None
    parser_name: str
    extractor_name: str
    field_path: Optional[str] = None
    published_at: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None
    source_priority: float = Field(default=0.5, ge=0.0, le=1.0)


class EvidenceFreshness(BaseModel):
    observed_at: datetime
    stale_after: datetime
    is_stale: bool
    freshness_days: int = Field(ge=0)


class EvidenceFact(BaseModel):
    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    asset_id: str
    fact_namespace: str
    fact_key: str
    entity_type: str
    entity_id: str
    value: Any
    normalized_value: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: EvidenceProvenance
    freshness: EvidenceFreshness
    conflict_status: str = "pending"
    is_active: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class ParsedDocument(BaseModel):
    document: RawDocument
    metadata: dict[str, Any] = Field(default_factory=dict)
    sections: dict[str, str] = Field(default_factory=dict)


class EvidenceIngestionResult(BaseModel):
    fetched_documents: int = 0
    stored_documents: int = 0
    deduped_documents: int = 0
    extracted_facts: int = 0
    winner_facts: int = 0
    conflicts: int = 0
    errors: list[str] = Field(default_factory=list)


class DocumentParser:
    def parse(self, document: RawDocument) -> ParsedDocument:
        lines = [line.strip() for line in document.raw_text.splitlines() if line.strip()]
        metadata: dict[str, Any] = {}
        for line in lines:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip().lower()] = value.strip()
        return ParsedDocument(document=document, metadata=metadata, sections={"lines": "\n".join(lines)})


class RuleBasedEvidenceExtractor:
    parser_name = "DocumentParser.v1"
    extractor_name = "RuleBasedEvidenceExtractor.v1"

    def extract(self, parsed: ParsedDocument) -> list[EvidenceFact]:
        if parsed.document.source == "clinicaltrials_gov":
            return self._extract_clinical_trials(parsed)
        if parsed.document.source == "sec_filing":
            return self._extract_sec(parsed)
        if parsed.document.source == "press_release":
            return self._extract_press_release(parsed)
        return []

    def _freshness(self, document: RawDocument) -> EvidenceFreshness:
        observed_at = document.published_at or document.retrieved_at
        stale_after = observed_at + timedelta(days=_STALE_AFTER_DAYS.get(document.source, 90))
        today = _utcnow()
        freshness_days = max((today - observed_at).days, 0)
        return EvidenceFreshness(
            observed_at=observed_at,
            stale_after=stale_after,
            is_stale=today > stale_after,
            freshness_days=freshness_days,
        )

    def _provenance(self, document: RawDocument, field_path: str) -> EvidenceProvenance:
        return EvidenceProvenance(
            source_type=document.source,
            source_url=document.source_url,
            raw_document_id=document.id,
            parser_name=self.parser_name,
            extractor_name=self.extractor_name,
            field_path=field_path,
            published_at=document.published_at,
            retrieved_at=document.retrieved_at,
            source_priority=_SOURCE_PRIORITY.get(document.source, 0.5),
        )

    def _fact(
        self,
        parsed: ParsedDocument,
        *,
        namespace: str,
        key: str,
        entity_type: str,
        entity_id: str,
        value: Any,
        confidence: float,
        field_path: str,
    ) -> EvidenceFact:
        return EvidenceFact(
            company_id=parsed.document.entity_hints.company_id,
            asset_id=parsed.document.entity_hints.asset_id,
            fact_namespace=namespace,
            fact_key=key,
            entity_type=entity_type,
            entity_id=entity_id,
            value=value,
            normalized_value=str(value).strip().lower(),
            confidence=confidence,
            provenance=self._provenance(parsed.document, field_path),
            freshness=self._freshness(parsed.document),
        )

    def _extract_clinical_trials(self, parsed: ParsedDocument) -> list[EvidenceFact]:
        metadata = parsed.metadata
        document = parsed.document
        nct_id = str(metadata.get("nct id") or document.entity_hints.nct_id or f"{document.entity_hints.asset_id}:trial")
        facts: list[EvidenceFact] = []

        phase = metadata.get("phases")
        if phase:
            facts.append(self._fact(parsed, namespace="trial", key="trial_phase", entity_type="trial", entity_id=nct_id, value=_normalize_status(phase.split(",")[0]), confidence=0.99, field_path="metadata.phases"))
        status = metadata.get("status")
        if status:
            facts.append(self._fact(parsed, namespace="trial", key="trial_status", entity_type="trial", entity_id=nct_id, value=_normalize_status(status), confidence=0.99, field_path="metadata.status"))
        primary_outcomes = metadata.get("primary outcomes")
        if primary_outcomes:
            facts.append(self._fact(parsed, namespace="trial", key="primary_endpoint", entity_type="trial", entity_id=nct_id, value=primary_outcomes, confidence=0.95, field_path="metadata.primary outcomes"))
        enrollment = metadata.get("enrollment")
        if enrollment:
            numeric = re.sub(r"[^0-9]", "", enrollment)
            if numeric:
                facts.append(self._fact(parsed, namespace="trial", key="enrollment_target", entity_type="trial", entity_id=nct_id, value=int(numeric), confidence=0.97, field_path="metadata.enrollment"))
        return facts

    def _extract_sec(self, parsed: ParsedDocument) -> list[EvidenceFact]:
        text = parsed.document.raw_text
        company_id = parsed.document.entity_hints.company_id
        facts: list[EvidenceFact] = []
        patterns = [
            ("cash_millions", _CASH_RE, 0.98),
            ("debt_millions", _DEBT_RE, 0.97),
            ("shares_outstanding_millions", _SHARES_RE, 0.95),
            ("quarterly_burn_musd", _BURN_RE, 0.90),
        ]
        for key, pattern, confidence in patterns:
            match = pattern.search(text)
            if not match:
                continue
            facts.append(self._fact(parsed, namespace="company_financial", key=key, entity_type="company", entity_id=company_id, value=_amount_to_millions(match.group(1), match.group(2)), confidence=confidence, field_path=f"regex.{key}"))
        if "at-the-market" in text.lower() or "atm facility" in text.lower():
            facts.append(self._fact(parsed, namespace="company_financial", key="atm_present", entity_type="company", entity_id=company_id, value=True, confidence=0.9, field_path="keyword.atm_present"))
        return facts

    def _extract_press_release(self, parsed: ParsedDocument) -> list[EvidenceFact]:
        text = parsed.document.raw_text
        company_id = parsed.document.entity_hints.company_id
        facts: list[EvidenceFact] = []
        proceeds = _PROCEEDS_RE.search(text)
        if proceeds:
            facts.append(self._fact(parsed, namespace="financing_event", key="financing_gross_proceeds_musd", entity_type="company", entity_id=company_id, value=_amount_to_millions(proceeds.group(1), proceeds.group(2)), confidence=0.82, field_path="regex.financing_gross_proceeds_musd"))
        shares = _OFFERING_SHARES_RE.search(text)
        if shares:
            facts.append(self._fact(parsed, namespace="financing_event", key="financing_offering_share_count_millions", entity_type="company", entity_id=company_id, value=float(shares.group(1)), confidence=0.8, field_path="regex.financing_offering_share_count_millions"))
        return facts


class EvidenceConflictResolver:
    def rank(self, fact: EvidenceFact) -> float:
        source_score = fact.provenance.source_priority * 0.45
        confidence_score = fact.confidence * 0.45
        freshness_score = max(0.0, 1.0 - (fact.freshness.freshness_days / 3650.0)) * 0.10
        return round(source_score + confidence_score + freshness_score, 6)

    def resolve(self, facts: list[EvidenceFact]) -> list[EvidenceFact]:
        ranked = sorted(facts, key=self.rank, reverse=True)
        if not ranked:
            return []
        winner = ranked[0]
        winner.conflict_status = "winner"
        winner.is_active = True
        for fact in ranked[1:]:
            fact.is_active = False
            fact.conflict_status = "corroborated" if fact.normalized_value == winner.normalized_value else "conflict"
        return ranked


class AutomatedEvidenceIngestionPipeline:
    def __init__(
        self,
        store: KnowledgeStore,
        *,
        connectors: Optional[list[Any]] = None,
        parser: Optional[DocumentParser] = None,
        extractor: Optional[RuleBasedEvidenceExtractor] = None,
        resolver: Optional[EvidenceConflictResolver] = None,
        graph: Optional[CanonicalAssetGraph] = None,
    ) -> None:
        self.store = store
        self.connectors = connectors or []
        self.parser = parser or DocumentParser()
        self.extractor = extractor or RuleBasedEvidenceExtractor()
        self.resolver = resolver or EvidenceConflictResolver()
        self.graph = graph or CanonicalAssetGraph(store)

    def fetch_and_ingest(
        self,
        entity_hints: EntityHints,
        *,
        since: Optional[datetime] = None,
        limit_per_connector: int = 10,
    ) -> EvidenceIngestionResult:
        documents: list[RawDocument] = []
        errors: list[str] = []
        for connector in self.connectors:
            try:
                outcome = connector.fetch(entity_hints, since=since, limit=limit_per_connector)
                documents.extend(outcome.documents)
                errors.extend(outcome.fetch_errors)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{connector.__class__.__name__}: {exc}")
        result = self.ingest_documents(documents)
        result.errors.extend(errors)
        return result

    def ingest_documents(self, documents: list[RawDocument]) -> EvidenceIngestionResult:
        result = EvidenceIngestionResult(fetched_documents=len(documents))
        for document in documents:
            if self.store.processed_document_hash_exists(source=document.source, document_hash=document.document_hash):
                result.deduped_documents += 1
                continue
            raw_record = self.store.add_raw_document(
                document,
                SourceTrace(source_type=document.source, source_ref=document.source_url or document.id, ingested_at=document.retrieved_at),
            )
            result.stored_documents += 1
            parsed = self.parser.parse(document)
            extracted_facts = self.extractor.extract(parsed)
            result.extracted_facts += len(extracted_facts)

            grouped: dict[tuple[str, str, str], list[EvidenceFact]] = defaultdict(list)
            for fact in extracted_facts:
                grouped[(fact.company_id, fact.asset_id, fact.fact_key)].append(fact)

            for (company_id, asset_id, fact_key), batch in grouped.items():
                prior_payloads = self.store.get_evidence_facts(company_id=company_id, asset_id=asset_id, fact_key=fact_key)
                prior = [EvidenceFact.model_validate(payload) for payload in prior_payloads]
                resolved = self.resolver.resolve(prior + batch)
                for fact in resolved:
                    self.store.add_evidence_fact(
                        fact,
                        SourceTrace(
                            source_type=fact.provenance.source_type,
                            source_ref=fact.provenance.source_url or fact.provenance.raw_document_id or fact.fact_id,
                            ingested_at=fact.created_at,
                        ),
                    )
                self._apply_resolved_facts_to_graph([fact for fact in resolved if fact.is_active])
                result.winner_facts += sum(1 for fact in resolved if fact.conflict_status == "winner")
                result.conflicts += sum(1 for fact in resolved if fact.conflict_status == "conflict")

            self.store.mark_document_hash_processed_explicit(
                source=document.source,
                document_hash=document.document_hash,
                raw_document_id=raw_record.id,
                processed_at=document.retrieved_at,
            )
        return result

    def _upsert_graph_node(self, *, node_type: NodeType, external_id: str, name: str, properties: dict[str, Any]) -> KGNode:
        existing = self.store.find_node_by_external_id(node_type, external_id)
        kwargs: dict[str, Any] = {
            "node_type": node_type,
            "name": name,
            "external_id": external_id,
            "properties": properties,
            "created_at": existing.created_at if existing else _utcnow(),
        }
        if existing is not None:
            kwargs["node_id"] = existing.node_id
            merged = dict(existing.properties)
            merged.update(properties)
            kwargs["properties"] = merged
        return self.store.upsert_node(KGNode(**kwargs))

    def _apply_resolved_facts_to_graph(self, facts: list[EvidenceFact]) -> None:
        trial_groups: dict[str, list[EvidenceFact]] = defaultdict(list)
        financial_groups: dict[str, list[EvidenceFact]] = defaultdict(list)
        for fact in facts:
            if fact.fact_namespace == "trial":
                trial_groups[fact.entity_id].append(fact)
            elif fact.fact_namespace in {"company_financial", "financing_event"}:
                financial_groups[fact.entity_id].append(fact)

        for trial_id, trial_facts in trial_groups.items():
            payload = {fact.fact_key: fact.value for fact in trial_facts}
            first = trial_facts[0]
            trial_node = self._upsert_graph_node(
                node_type=NodeType.TRIAL,
                external_id=trial_id,
                name=trial_id,
                properties={
                    **payload,
                    "source": first.provenance.source_type,
                    "confidence": max(fact.confidence for fact in trial_facts),
                    "last_verified": max(fact.freshness.observed_at for fact in trial_facts).date().isoformat(),
                },
            )
            asset_node = self.store.find_node_by_external_id(NodeType.ASSET, first.asset_id)
            if asset_node is not None:
                self.store.add_edge(
                    KGEdge(
                        source_node_id=trial_node.node_id,
                        target_node_id=asset_node.node_id,
                        edge_type=EdgeType.TRIAL_BELONGS_TO_ASSET,
                        confidence=max(fact.confidence for fact in trial_facts),
                    )
                )

        for company_id, financial_facts in financial_groups.items():
            payload = {fact.fact_key: fact.value for fact in financial_facts}
            existing_node = self.store.find_node_by_external_id(
                NodeType.FINANCING_STATE, f"financing:{company_id}"
            )
            existing_props = dict(existing_node.properties) if existing_node is not None else {}
            merged_for_calc = {**existing_props, **payload}
            cash_value = merged_for_calc.get("cash_millions")
            burn_value = merged_for_calc.get("quarterly_burn_musd") or merged_for_calc.get(
                "burn_rate_millions_per_quarter"
            )
            if cash_value not in (None, 0) and burn_value not in (None, 0):
                payload["months_of_runway"] = round((float(cash_value) / float(burn_value)) * 3.0, 2)
            first = financial_facts[0]
            financing_node = self._upsert_graph_node(
                node_type=NodeType.FINANCING_STATE,
                external_id=f"financing:{company_id}",
                name=f"{company_id} financing state",
                properties={
                    **payload,
                    "source": first.provenance.source_type,
                    "confidence": max(fact.confidence for fact in financial_facts),
                    "last_verified": max(fact.freshness.observed_at for fact in financial_facts).date().isoformat(),
                },
            )
            company_node = self.store.find_node_by_external_id(NodeType.COMPANY, company_id)
            if company_node is not None:
                self.store.add_edge(
                    KGEdge(
                        source_node_id=company_node.node_id,
                        target_node_id=financing_node.node_id,
                        edge_type=EdgeType.FINANCING_APPLIES_TO_COMPANY,
                        confidence=max(fact.confidence for fact in financial_facts),
                    )
                )
