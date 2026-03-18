"""
Wave 6B — automated literature review agent.

Deterministic, retrieval-first review over ingested raw documents.
No LLM calls and no external network calls.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import KnowledgeStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LiteratureTopic(str, Enum):
    EFFICACY = "efficacy"
    SAFETY = "safety"
    MECHANISM = "mechanism"
    BIOMARKERS = "biomarkers"
    TRIAL_OUTCOMES = "trial_outcomes"


_TOPIC_KEYWORDS: dict[LiteratureTopic, tuple[str, ...]] = {
    LiteratureTopic.EFFICACY: (
        "efficacy",
        "overall survival",
        "progression-free survival",
        "response rate",
        "orr",
        "hazard ratio",
        "clinical benefit",
    ),
    LiteratureTopic.SAFETY: (
        "safety",
        "adverse event",
        "serious adverse",
        "toxicity",
        "grade 3",
        "grade 4",
        "tolerability",
    ),
    LiteratureTopic.MECHANISM: (
        "mechanism",
        "target",
        "pathway",
        "inhibitor",
        "agonist",
        "antibody",
        "binding",
    ),
    LiteratureTopic.BIOMARKERS: (
        "biomarker",
        "mutation",
        "expression",
        "companion diagnostic",
        "pd-l1",
        "ctdna",
        "mrd",
    ),
    LiteratureTopic.TRIAL_OUTCOMES: (
        "trial outcome",
        "primary endpoint",
        "secondary endpoint",
        "met endpoint",
        "did not meet",
        "readout",
        "interim analysis",
    ),
}

_TOKEN_CACHE: dict[str, re.Pattern[str]] = {}


def _token_count(text: str, token: str) -> int:
    pattern = _TOKEN_CACHE.get(token)
    if pattern is None:
        pattern = re.compile(
            rf"(?<![a-z0-9]){re.escape(token.lower())}(?![a-z0-9])",
            re.IGNORECASE,
        )
        _TOKEN_CACHE[token] = pattern
    return len(pattern.findall(text))


def _count_keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(_token_count(text, keyword) for keyword in keywords)


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"[.!?\n]+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


class ClusteredDocument(BaseModel):
    doc_id: str
    text: str
    pmid: Optional[str] = None
    topic_scores: dict[LiteratureTopic, int] = Field(default_factory=dict)


class LiteratureReviewSection(BaseModel):
    topic: LiteratureTopic
    summary: str
    supporting_document_ids: list[str] = Field(default_factory=list)
    supporting_pmids: list[str] = Field(default_factory=list)
    evidence_sentence_count: int = 0
    topic_keyword_hits: int = 0


class LiteratureReview(BaseModel):
    review_id: str
    asset_id: str
    company_id: Optional[str] = None
    generated_at: datetime
    efficacy_summary: str
    safety_summary: str
    mechanism_summary: str
    biomarker_summary: str
    trial_outcomes_summary: str
    knowledge_gaps: list[str] = Field(default_factory=list)
    sections: list[LiteratureReviewSection] = Field(default_factory=list)
    cited_raw_document_ids: list[str] = Field(default_factory=list)
    cited_signal_ids: list[str] = Field(default_factory=list)


class DocumentTopicGrouper:
    """Rule-based topic clustering for literature documents."""

    def group(self, documents: list[dict[str, str]]) -> dict[LiteratureTopic, list[ClusteredDocument]]:
        grouped: dict[LiteratureTopic, list[ClusteredDocument]] = {
            topic: [] for topic in LiteratureTopic
        }
        for doc in documents:
            text = doc["text"].lower()
            scores = {
                topic: _count_keyword_hits(text, keywords)
                for topic, keywords in _TOPIC_KEYWORDS.items()
            }
            max_score = max(scores.values()) if scores else 0
            if max_score <= 0:
                continue
            clustered = ClusteredDocument(
                doc_id=doc["id"],
                text=doc["text"],
                pmid=doc.get("pmid"),
                topic_scores=scores,
            )
            winners = sorted(
                [topic for topic, score in scores.items() if score == max_score],
                key=lambda t: t.value,
            )
            for topic in winners:
                grouped[topic].append(clustered)

        for topic in LiteratureTopic:
            grouped[topic].sort(
                key=lambda item: (-item.topic_scores.get(topic, 0), item.doc_id),
            )
        return grouped


class LiteratureReviewAgent:
    """
    Deterministic literature review synthesizer.

    Implementation order (Wave 6B):
      1) LiteratureReview model
      2) document grouping (topic clustering)
      3) LiteratureReviewAgent synthesis
    """

    def __init__(
        self,
        *,
        max_documents: int = 500,
        max_signal_citations: int = 100,
        max_sentences_per_topic: int = 2,
        grouper: Optional[DocumentTopicGrouper] = None,
    ) -> None:
        self.max_documents = max_documents
        self.max_signal_citations = max_signal_citations
        self.max_sentences_per_topic = max_sentences_per_topic
        self.grouper = grouper or DocumentTopicGrouper()

    def generate(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str] = None,
        generated_at: Optional[datetime] = None,
    ) -> LiteratureReview:
        generated_at = generated_at or _utcnow()
        documents = self._load_documents(store, asset_id=asset_id, company_id=company_id)
        signal_ids = self._load_signal_ids(store, asset_id=asset_id, company_id=company_id)
        grouped = self.grouper.group(documents)

        sections: list[LiteratureReviewSection] = []
        knowledge_gaps: list[str] = []
        for topic in LiteratureTopic:
            section = self._build_section(topic, grouped.get(topic, []))
            sections.append(section)
            if not section.supporting_document_ids:
                knowledge_gaps.append(f"{topic.value}: no supporting documents.")

        section_map = {section.topic: section for section in sections}
        cited_doc_ids = sorted(
            {
                doc_id
                for section in sections
                for doc_id in section.supporting_document_ids
            }
        )

        review_id = self._review_id(
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
            cited_doc_ids=cited_doc_ids,
        )
        return LiteratureReview(
            review_id=review_id,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
            efficacy_summary=section_map[LiteratureTopic.EFFICACY].summary,
            safety_summary=section_map[LiteratureTopic.SAFETY].summary,
            mechanism_summary=section_map[LiteratureTopic.MECHANISM].summary,
            biomarker_summary=section_map[LiteratureTopic.BIOMARKERS].summary,
            trial_outcomes_summary=section_map[LiteratureTopic.TRIAL_OUTCOMES].summary,
            knowledge_gaps=knowledge_gaps,
            sections=sections,
            cited_raw_document_ids=cited_doc_ids,
            cited_signal_ids=signal_ids,
        )

    def _load_documents(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str],
    ) -> list[dict[str, Optional[str]]]:
        clauses = ["json_extract(payload_json, '$.entity_hints.asset_id') = ?"]
        params: list[object] = [asset_id]
        if company_id is not None:
            clauses.append("json_extract(payload_json, '$.entity_hints.company_id') = ?")
            params.append(company_id)

        sql = (
            "SELECT id, payload_json FROM raw_documents "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at ASC, id ASC LIMIT ?"
        )
        params.append(self.max_documents)
        rows = store._conn.execute(sql, params).fetchall()

        docs: list[dict[str, Optional[str]]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            text = " ".join(
                [
                    str(payload.get("title") or "").strip(),
                    str(payload.get("raw_text") or "").strip(),
                ]
            ).strip()
            if not text:
                continue
            docs.append(
                {
                    "id": str(row["id"]),
                    "text": text,
                    "pmid": self._extract_pmid(payload),
                }
            )
        return docs

    def _load_signal_ids(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str],
    ) -> list[str]:
        clauses = ["asset_id = ?"]
        params: list[object] = [asset_id]
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        sql = (
            "SELECT id FROM structured_signals "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY signal_date DESC, created_at DESC, id ASC LIMIT ?"
        )
        params.append(self.max_signal_citations)
        rows = store._conn.execute(sql, params).fetchall()
        return [str(row["id"]) for row in rows]

    def _build_section(
        self,
        topic: LiteratureTopic,
        clustered_docs: list[ClusteredDocument],
    ) -> LiteratureReviewSection:
        if not clustered_docs:
            return LiteratureReviewSection(
                topic=topic,
                summary=f"No {topic.value.replace('_', ' ')} evidence identified in reviewed documents.",
            )

        keyword_hits = sum(
            doc.topic_scores.get(topic, 0)
            for doc in clustered_docs
        )
        candidates: list[tuple[int, int, str, str]] = []
        keywords = _TOPIC_KEYWORDS[topic]
        for doc in clustered_docs:
            for sentence in _split_sentences(doc.text):
                score = _count_keyword_hits(sentence.lower(), keywords)
                if score <= 0:
                    continue
                normalized = " ".join(sentence.split())
                if len(normalized) > 220:
                    normalized = normalized[:217].rstrip() + "..."
                candidates.append((score, len(normalized), normalized, doc.doc_id))

        if not candidates:
            for doc in clustered_docs:
                first_sentence = _split_sentences(doc.text)
                if not first_sentence:
                    continue
                normalized = " ".join(first_sentence[0].split())
                if len(normalized) > 220:
                    normalized = normalized[:217].rstrip() + "..."
                candidates.append((0, len(normalized), normalized, doc.doc_id))

        candidates.sort(key=lambda item: (-item[0], -item[1], item[3], item[2].lower()))

        selected: list[tuple[str, str]] = []
        seen_sentence_doc: set[tuple[str, str]] = set()
        for _, _, sentence, doc_id in candidates:
            key = (sentence, doc_id)
            if key in seen_sentence_doc:
                continue
            selected.append((sentence, doc_id))
            seen_sentence_doc.add(key)
            if len(selected) >= self.max_sentences_per_topic:
                break

        summary_parts = [f"{sentence} [doc:{doc_id}]" for sentence, doc_id in selected]
        summary = "; ".join(summary_parts) if summary_parts else (
            f"No {topic.value.replace('_', ' ')} evidence identified in reviewed documents."
        )
        supporting_doc_ids = sorted({doc_id for _, doc_id in selected})
        pmid_by_doc = {doc.doc_id: doc.pmid for doc in clustered_docs}
        supporting_pmids = sorted(
            {
                pmid_by_doc.get(doc_id)
                for _, doc_id in selected
                if pmid_by_doc.get(doc_id)
            }
        )

        return LiteratureReviewSection(
            topic=topic,
            summary=summary,
            supporting_document_ids=supporting_doc_ids,
            supporting_pmids=supporting_pmids,
            evidence_sentence_count=len(selected),
            topic_keyword_hits=keyword_hits,
        )

    @staticmethod
    def _extract_pmid(payload: dict) -> Optional[str]:
        source_url = str(payload.get("source_url") or "")
        match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", source_url)
        if match:
            return match.group(1)
        if str(payload.get("source") or "").lower() == "pubmed":
            doc_id = str(payload.get("id") or "")
            if doc_id.isdigit():
                return doc_id
        return None

    @staticmethod
    def _review_id(
        *,
        asset_id: str,
        company_id: Optional[str],
        generated_at: datetime,
        cited_doc_ids: list[str],
    ) -> str:
        key = (
            f"literature_review|{asset_id}|{company_id or ''}|"
            f"{generated_at.isoformat()}|{','.join(cited_doc_ids)}"
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
