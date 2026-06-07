"""
Wave 6C — deterministic competitive landscape agent.

This module reads competitor context from the knowledge graph and outputs a
structured comparison table without LLM synthesis.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_graph import EdgeType, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompetitiveProgramEntry(BaseModel):
    """One row in the competitive landscape output table."""

    source_node_id: str
    relationship: str
    drug: str
    company: Optional[str] = None
    phase: Optional[str] = None
    mechanism: Optional[str] = None
    status: Optional[str] = None
    source_nct_id: Optional[str] = None
    mechanism_similarity: str = "different_mechanism"
    mechanism_similarity_score: float = Field(default=0.2, ge=0.0, le=1.0)
    estimated_months_to_completion: Optional[float] = Field(default=None, ge=0.0)
    distance_to_market: float = Field(default=1.5, ge=0.0)
    risk_score: float = Field(ge=0.0, le=1.0)


class CompetitiveLandscape(BaseModel):
    """Competitive landscape output for one tracked asset."""

    landscape_id: str
    asset_id: str
    company_id: Optional[str] = None
    generated_at: datetime
    entries: list[CompetitiveProgramEntry] = Field(default_factory=list)
    cited_node_ids: list[str] = Field(default_factory=list)


class CompetitiveLandscapeAgent:
    """
    Deterministic KG-driven competitive landscape builder.

    Retrieval strategy:
      1) direct `competes_with` neighbors
      2) `same_indication` asset neighbors
    """

    def generate(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str] = None,
        generated_at: Optional[datetime] = None,
    ) -> CompetitiveLandscape:
        generated_at = generated_at or _utcnow()
        asset_node = store.find_node_by_external_id(NodeType.ASSET, asset_id)
        if asset_node is None:
            landscape_id = self._landscape_id(
                asset_id=asset_id,
                company_id=company_id,
                generated_at=generated_at,
                cited_node_ids=[],
            )
            return CompetitiveLandscape(
                landscape_id=landscape_id,
                asset_id=asset_id,
                company_id=company_id,
                generated_at=generated_at,
                entries=[],
                cited_node_ids=[],
            )

        same_mechanism_ids = {
            node.node_id
            for node in store.neighbors(asset_node.node_id, edge_type=EdgeType.SAME_MECHANISM)
        }
        same_target_ids = {
            node.node_id
            for node in store.neighbors(asset_node.node_id, edge_type=EdgeType.SAME_TARGET)
        }
        source_target_class = (
            str((asset_node.properties or {}).get("moa_summary", {}).get("target_class") or "").lower()
        )
        source_mechanism_text = str((asset_node.properties or {}).get("mechanism") or "").lower()

        entries: list[CompetitiveProgramEntry] = []
        competitor_nodes = store.neighbors(asset_node.node_id, edge_type=EdgeType.COMPETES_WITH)
        for node in competitor_nodes:
            if node.node_id == asset_node.node_id:
                continue
            entries.append(
                self._entry_from_node(
                    node=node,
                    relationship="competes_with",
                    same_mechanism_ids=same_mechanism_ids,
                    same_target_ids=same_target_ids,
                    source_target_class=source_target_class,
                    source_mechanism_text=source_mechanism_text,
                    as_of=generated_at.date(),
                )
            )

        same_indication_nodes = store.neighbors(
            asset_node.node_id,
            edge_type=EdgeType.SAME_INDICATION,
        )
        for node in same_indication_nodes:
            if node.node_id == asset_node.node_id or node.node_type != NodeType.ASSET:
                continue
            entries.append(
                self._entry_from_node(
                    node=node,
                    relationship="same_indication_asset",
                    same_mechanism_ids=same_mechanism_ids,
                    same_target_ids=same_target_ids,
                    source_target_class=source_target_class,
                    source_mechanism_text=source_mechanism_text,
                    as_of=generated_at.date(),
                )
            )

        deduped = self._dedupe_entries(entries)
        deduped.sort(key=lambda row: (-row.risk_score, row.drug.lower(), (row.company or "").lower()))
        cited_node_ids = sorted({entry.source_node_id for entry in deduped})
        landscape_id = self._landscape_id(
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
            cited_node_ids=cited_node_ids,
        )
        return CompetitiveLandscape(
            landscape_id=landscape_id,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
            entries=deduped,
            cited_node_ids=cited_node_ids,
        )

    def _entry_from_node(
        self,
        *,
        node,
        relationship: str,
        same_mechanism_ids: set[str],
        same_target_ids: set[str],
        source_target_class: str,
        source_mechanism_text: str,
        as_of: date,
    ) -> CompetitiveProgramEntry:
        properties = dict(node.properties or {})
        phase = properties.get("phase") or properties.get("stage")
        status = properties.get("status")
        mechanism = properties.get("mechanism")
        company = properties.get("company")
        mechanism_similarity, mechanism_similarity_score = self._mechanism_similarity(
            node=node,
            mechanism=mechanism,
            source_target_class=source_target_class,
            source_mechanism_text=source_mechanism_text,
            same_mechanism_ids=same_mechanism_ids,
            same_target_ids=same_target_ids,
        )
        months_to_completion = self._estimated_months_to_completion(
            phase=phase,
            properties=properties,
            as_of=as_of,
        )
        distance_to_market = self._distance_to_market(
            phase=phase,
            months_to_completion=months_to_completion,
        )
        risk = self._risk_score(
            phase=phase,
            status=status,
            relationship=relationship,
            mechanism_similarity_score=mechanism_similarity_score,
            distance_to_market=distance_to_market,
        )
        return CompetitiveProgramEntry(
            source_node_id=node.node_id,
            relationship=relationship,
            drug=node.name,
            company=company,
            phase=phase,
            mechanism=mechanism,
            status=status,
            source_nct_id=node.external_id,
            mechanism_similarity=mechanism_similarity,
            mechanism_similarity_score=mechanism_similarity_score,
            estimated_months_to_completion=months_to_completion,
            distance_to_market=distance_to_market,
            risk_score=risk,
        )

    @staticmethod
    def _risk_score(
        *,
        phase: Optional[str],
        status: Optional[str],
        relationship: str,
        mechanism_similarity_score: float,
        distance_to_market: float,
    ) -> float:
        phase_text = (phase or "").lower()
        if "approved" in phase_text or "phase4" in phase_text or "phase 4" in phase_text:
            phase_score = 0.95
        elif "phase3" in phase_text or "phase 3" in phase_text:
            phase_score = 0.85
        elif "phase2" in phase_text or "phase 2" in phase_text:
            phase_score = 0.70
        elif "phase1" in phase_text or "phase 1" in phase_text:
            phase_score = 0.45
        else:
            phase_score = 0.60 if relationship == "same_indication_asset" else 0.55

        status_text = (status or "").upper()
        if status_text in {"RECRUITING", "ACTIVE_NOT_RECRUITING"}:
            status_mult = 1.00
        elif status_text in {"NOT_YET_RECRUITING"}:
            status_mult = 0.85
        elif status_text in {"COMPLETED"}:
            status_mult = 0.75
        elif status_text in {"TERMINATED", "WITHDRAWN", "SUSPENDED"}:
            status_mult = 0.30
        else:
            status_mult = 0.90

        phase_status_score = max(0.0, min(1.0, phase_score * status_mult))
        # Lower distance_to_market means nearer to launch and therefore more threatening.
        distance_urgency = max(0.0, min(1.0, 1.0 - (distance_to_market / 2.5)))
        raw_score = (
            0.45 * phase_status_score
            + 0.40 * distance_urgency
            + 0.15 * mechanism_similarity_score
        )
        clamped = max(0.0, min(1.0, raw_score))
        return round(clamped, 3)

    @staticmethod
    def _mechanism_similarity(
        *,
        node,
        mechanism: Optional[str],
        source_target_class: str,
        source_mechanism_text: str,
        same_mechanism_ids: set[str],
        same_target_ids: set[str],
    ) -> tuple[str, float]:
        if node.node_id in same_target_ids:
            return "same_target", 1.0
        if node.node_id in same_mechanism_ids:
            return "same_pathway", 0.75

        mechanism_text = str(mechanism or "").lower()
        node_name_text = str(node.name or "").lower()
        haystack = f"{mechanism_text} {node_name_text}".strip()

        if source_target_class and source_target_class in haystack:
            return "same_pathway", 0.60

        src_tokens = {t for t in source_mechanism_text.split() if len(t) >= 4}
        if src_tokens and any(token in haystack for token in src_tokens):
            return "same_pathway", 0.55

        return "different_mechanism", 0.20

    @staticmethod
    def _estimated_months_to_completion(
        *,
        phase: Optional[str],
        properties: dict,
        as_of: date,
    ) -> Optional[float]:
        for key in ("months_to_completion", "estimated_months_to_completion", "time_to_estimated_completion"):
            value = properties.get(key)
            if value is None:
                continue
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                continue

        for key in ("primary_completion_date", "estimated_completion_date"):
            value = properties.get(key)
            if not value:
                continue
            try:
                completion_date = date.fromisoformat(str(value)[:10])
            except ValueError:
                continue
            delta_days = (completion_date - as_of).days
            return max(0.0, round(delta_days / 30.44, 2))

        phase_text = (phase or "").lower()
        if "approved" in phase_text or "phase4" in phase_text or "phase 4" in phase_text:
            return 0.0
        if "phase3" in phase_text or "phase 3" in phase_text:
            return 18.0
        if "phase2" in phase_text or "phase 2" in phase_text:
            return 36.0
        if "phase1" in phase_text or "phase 1" in phase_text:
            return 54.0
        return None

    @staticmethod
    def _distance_to_market(
        *,
        phase: Optional[str],
        months_to_completion: Optional[float],
    ) -> float:
        phase_text = (phase or "").lower()
        if "approved" in phase_text or "phase4" in phase_text or "phase 4" in phase_text:
            phase_weight = 0.05
        elif "phase3" in phase_text or "phase 3" in phase_text:
            phase_weight = 0.20
        elif "phase2" in phase_text or "phase 2" in phase_text:
            phase_weight = 0.50
        elif "phase1" in phase_text or "phase 1" in phase_text:
            phase_weight = 0.80
        else:
            phase_weight = 0.65

        if months_to_completion is None:
            return round(phase_weight + 1.0, 3)

        time_component = min(2.0, max(0.0, months_to_completion) / 24.0)
        return round(phase_weight + time_component, 3)

    @staticmethod
    def _dedupe_entries(entries: list[CompetitiveProgramEntry]) -> list[CompetitiveProgramEntry]:
        by_key: dict[tuple[str, str, str, str, str], CompetitiveProgramEntry] = {}
        for entry in entries:
            key = (
                entry.drug.lower(),
                (entry.company or "").lower(),
                (entry.phase or "").lower(),
                entry.relationship,
                (entry.source_nct_id or "").lower(),
            )
            current = by_key.get(key)
            if current is None or entry.risk_score > current.risk_score:
                by_key[key] = entry
        return list(by_key.values())

    @staticmethod
    def _landscape_id(
        *,
        asset_id: str,
        company_id: Optional[str],
        generated_at: datetime,
        cited_node_ids: list[str],
    ) -> str:
        key = (
            f"competitive_landscape|{asset_id}|{company_id or ''}|"
            f"{generated_at.isoformat()}|{','.join(cited_node_ids)}"
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
