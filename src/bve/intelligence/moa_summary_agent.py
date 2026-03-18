"""
Wave 6A — Mechanism of Action (MoA) summary agent.

This module is deterministic and retrieval-first:
  - Uses only persisted records in KnowledgeStore
  - No LLM calls, no network calls
  - Produces a typed MoA summary for one asset
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_graph import KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_TARGET_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "PD-1/PD-L1": ("pd-1", "pd1", "pd-l1", "pdl1"),
    "EGFR": ("egfr", "erbb1"),
    "HER2": ("her2", "erbb2"),
    "BTK": ("btk", "bruton's tyrosine kinase", "bruton tyrosine kinase"),
    "JAK": ("jak1", "jak2", "jak3", "janus kinase"),
    "VEGF/VEGFR": ("vegf", "vegfr"),
    "KRAS": ("kras",),
    "BCL2": ("bcl2", "bcl-2"),
    "CD19": ("cd19",),
    "BCMA": ("bcma",),
}

_MECHANISM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "inhibitor": ("inhibitor", "inhibition"),
    "agonist": ("agonist", "agonism"),
    "antagonist": ("antagonist", "antagonism"),
    "degrader": ("degrader", "degradation"),
    "antibody": ("antibody", "monoclonal", "bispecific"),
    "cell therapy": ("car-t", "cell therapy"),
    "gene therapy": ("gene therapy", "aav", "lentiviral"),
    "rna therapy": ("sirna", "antisense", "aso", "mrna"),
}

_POSITIVE_NOVELTY_CUES: tuple[str, ...] = (
    "first-in-class",
    "novel",
    "differentiated",
    "selective",
    "best-in-class",
    "highly selective",
)

_NEGATIVE_NOVELTY_CUES: tuple[str, ...] = (
    "me-too",
    "biosimilar",
    "follow-on",
    "class parity",
)

_DIFFERENTIATION_CUES: tuple[str, ...] = (
    "differentiated",
    "selective",
    "first-in-class",
    "best-in-class",
    "improved",
    "potent",
    "tolerability",
    "versus",
    "vs ",
    "compared with",
)

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


def _best_label(text: str, mapping: dict[str, tuple[str, ...]]) -> Optional[str]:
    scores = {
        label: _count_keyword_hits(text, keywords)
        for label, keywords in mapping.items()
    }
    best = sorted(
        (
            (label, score)
            for label, score in scores.items()
            if score > 0
        ),
        key=lambda item: (-item[1], item[0]),
    )
    return best[0][0] if best else None


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"[.!?\n]+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class MoASummary(BaseModel):
    """Typed output for Wave 6A MoA synthesis."""

    asset_id: str
    company_id: Optional[str] = None
    target_class: str
    mechanism_description: str
    novelty_score: float = Field(ge=0.0, le=1.0)
    moa_confidence: float = Field(ge=0.0, le=1.0)
    competitive_differentiation: str
    generated_at: datetime
    cited_raw_document_ids: list[str] = Field(default_factory=list)
    cited_signal_ids: list[str] = Field(default_factory=list)


class MechanismOfActionSummaryAgent:
    """
    Deterministic MoA summarizer over ingested records.

    Output fields align to Wave 6A:
      - target_class
      - mechanism_description
      - novelty_score
      - competitive_differentiation
    """

    def __init__(
        self,
        *,
        max_documents: int = 500,
        max_signal_citations: int = 50,
    ) -> None:
        self.max_documents = max_documents
        self.max_signal_citations = max_signal_citations

    def summarize(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str] = None,
        generated_at: Optional[datetime] = None,
        persist_to_kg: bool = True,
    ) -> MoASummary:
        generated_at = generated_at or _utcnow()
        docs = self._load_documents(store, asset_id=asset_id, company_id=company_id)
        signal_ids = self._load_signal_ids(store, asset_id=asset_id, company_id=company_id)
        moa_confidence = self._moa_confidence(len(docs))

        if not docs:
            summary = MoASummary(
                asset_id=asset_id,
                company_id=company_id,
                target_class="undetermined",
                mechanism_description="Insufficient ingested mechanism evidence for this asset.",
                novelty_score=0.50,
                moa_confidence=moa_confidence,
                competitive_differentiation=(
                    "No differentiation cues available because no raw documents were found."
                ),
                generated_at=generated_at,
                cited_raw_document_ids=[],
                cited_signal_ids=signal_ids,
            )
            if persist_to_kg:
                self._persist_summary_to_kg(store, summary)
            return summary

        combined_text = "\n".join(doc["text"] for doc in docs).lower()
        target_class = _best_label(combined_text, _TARGET_CLASS_KEYWORDS) or "undetermined"
        mechanism_mode = _best_label(combined_text, _MECHANISM_KEYWORDS) or "unspecified modality"

        mechanism_description = self._mechanism_description(
            n_docs=len(docs),
            target_class=target_class,
            mechanism_mode=mechanism_mode,
        )
        novelty_score = self._novelty_score(
            store=store,
            asset_id=asset_id,
            target_class=target_class,
            combined_text=combined_text,
        )
        competitive_differentiation = self._competitive_differentiation(docs)

        summary = MoASummary(
            asset_id=asset_id,
            company_id=company_id,
            target_class=target_class,
            mechanism_description=mechanism_description,
            novelty_score=novelty_score,
            moa_confidence=moa_confidence,
            competitive_differentiation=competitive_differentiation,
            generated_at=generated_at,
            cited_raw_document_ids=[doc["id"] for doc in docs],
            cited_signal_ids=signal_ids,
        )
        if persist_to_kg:
            self._persist_summary_to_kg(store, summary)
        return summary

    def _load_documents(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str],
    ) -> list[dict[str, str]]:
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

        docs: list[dict[str, str]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            title = str(payload.get("title") or "").strip()
            raw_text = str(payload.get("raw_text") or "").strip()
            text = f"{title}. {raw_text}".strip()
            if not text:
                continue
            docs.append({"id": str(row["id"]), "text": text})
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

    @staticmethod
    def _mechanism_description(
        *,
        n_docs: int,
        target_class: str,
        mechanism_mode: str,
    ) -> str:
        if target_class == "undetermined" and mechanism_mode == "unspecified modality":
            return (
                f"Reviewed {n_docs} documents; target class and mechanism modality "
                "were not explicitly stated."
            )
        if target_class == "undetermined":
            return (
                f"Reviewed {n_docs} documents; evidence indicates a {mechanism_mode}-based "
                "approach, but target class is not explicit."
            )
        if mechanism_mode == "unspecified modality":
            return (
                f"Reviewed {n_docs} documents; evidence consistently references target "
                f"class {target_class}, with limited modality detail."
            )
        return (
            f"Reviewed {n_docs} documents; evidence indicates a {mechanism_mode}-driven "
            f"approach targeting {target_class}."
        )

    def _novelty_score(
        self,
        *,
        store: KnowledgeStore,
        asset_id: str,
        target_class: str,
        combined_text: str,
    ) -> float:
        positive_hits = _count_keyword_hits(combined_text, _POSITIVE_NOVELTY_CUES)
        negative_hits = _count_keyword_hits(combined_text, _NEGATIVE_NOVELTY_CUES)

        novelty = 0.50
        novelty += min(0.25, 0.05 * positive_hits)
        novelty -= min(0.25, 0.05 * negative_hits)

        if target_class != "undetermined":
            prevalence = self._target_prevalence_among_other_assets(
                store=store,
                asset_id=asset_id,
                target_class=target_class,
            )
            # Range impact: [-0.10, +0.10] from target prevalence.
            novelty += (0.5 - prevalence) * 0.20
        else:
            novelty -= 0.10

        return round(_clamp01(novelty), 3)

    def _target_prevalence_among_other_assets(
        self,
        *,
        store: KnowledgeStore,
        asset_id: str,
        target_class: str,
    ) -> float:
        tokens = _TARGET_CLASS_KEYWORDS.get(target_class)
        if not tokens:
            return 0.5

        rows = store._conn.execute(
            """
            SELECT payload_json
              FROM raw_documents
             WHERE json_extract(payload_json, '$.entity_hints.asset_id') != ?
            """,
            (asset_id,),
        ).fetchall()
        if not rows:
            return 0.5

        total_docs = 0
        matched_docs = 0
        for row in rows:
            payload = json.loads(row["payload_json"])
            text = f"{payload.get('title', '')} {payload.get('raw_text', '')}".lower()
            if not text.strip():
                continue
            total_docs += 1
            if any(_token_count(text, token) > 0 for token in tokens):
                matched_docs += 1

        if total_docs == 0:
            return 0.5
        return matched_docs / float(total_docs)

    @staticmethod
    def _competitive_differentiation(docs: list[dict[str, str]]) -> str:
        candidates: dict[str, int] = {}
        for doc in docs:
            for sentence in _split_sentences(doc["text"]):
                lowered = sentence.lower()
                cue_hits = sum(1 for cue in _DIFFERENTIATION_CUES if cue in lowered)
                if cue_hits <= 0:
                    continue
                normalized = " ".join(sentence.split())
                if len(normalized) > 240:
                    normalized = normalized[:237].rstrip() + "..."
                candidates[normalized] = max(candidates.get(normalized, 0), cue_hits)

        if not candidates:
            return (
                "No explicit differentiation wording found in ingested documents; "
                "analyst review required for competitive positioning."
            )

        ranked = sorted(
            candidates.items(),
            key=lambda item: (-item[1], len(item[0]), item[0].lower()),
        )
        top_sentences = [item[0] for item in ranked[:2]]
        return "Differentiation cues: " + "; ".join(top_sentences)

    @staticmethod
    def _moa_confidence(document_count: int) -> float:
        if document_count <= 0:
            return 0.0
        confidence = min(1.0, math.log(document_count + 1) / math.log(10))
        return round(confidence, 3)

    def _persist_summary_to_kg(self, store: KnowledgeStore, summary: MoASummary) -> None:
        payload = {
            "target_class": summary.target_class,
            "mechanism_description": summary.mechanism_description,
            "novelty_score": summary.novelty_score,
            "moa_confidence": summary.moa_confidence,
            "competitive_differentiation": summary.competitive_differentiation,
            "generated_at": summary.generated_at.isoformat(),
            "cited_raw_document_ids": summary.cited_raw_document_ids,
            "cited_signal_ids": summary.cited_signal_ids,
        }
        node = store.find_node_by_external_id(NodeType.ASSET, summary.asset_id)
        if node is None:
            store.upsert_node(
                KGNode(
                    node_type=NodeType.ASSET,
                    name=summary.asset_id,
                    external_id=summary.asset_id,
                    properties={"moa_summary": payload},
                )
            )
            return

        properties = dict(node.properties or {})
        properties["moa_summary"] = payload
        store.upsert_node(node.model_copy(update={"properties": properties}))
