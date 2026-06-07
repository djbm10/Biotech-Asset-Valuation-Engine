"""Alerts endpoint — GET /api/alerts — high-materiality recent evidence."""

from __future__ import annotations

import os
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from apps.api.schemas.responses import AlertCard
from bve.persistence.models import EvidenceItem

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
DB = Annotated[Session, Depends(get_db)]


def _list_alerts_from_knowledge_store(
    *,
    source_type: Optional[str],
    limit: int,
) -> list[AlertCard]:
    db_path = os.environ.get("BVE_KNOWLEDGE_DB_PATH")
    if not db_path:
        return []
    from bve.intelligence.knowledge_layer import KnowledgeStore

    store = KnowledgeStore(db_path)
    try:
        alerts = store.get_opportunity_alerts(event_type=source_type, limit=limit)
        raw_documents = store.get_raw_documents(limit=limit)
    finally:
        store.close()
    cards = [
        AlertCard(
            id=f"{alert.asset_id}:{alert.event_type}:{alert.window}",
            source_type=alert.event_type,
            title=str(alert.payload_json.get("title") or alert.event_type),
            materiality_score=float(alert.payload_json.get("score") or 0.5),
            published_at=alert.created_at.isoformat(),
            source_url=None,
        )
        for alert in alerts
    ]
    if cards:
        return cards
    if source_type:
        return []
    return [
        AlertCard(
            id=document.id,
            source_type=str(document.payload_json.get("source") or "raw_document"),
            title=str(document.payload_json.get("title") or document.id),
            materiality_score=0.5,
            published_at=document.created_at.isoformat(),
            source_url=document.payload_json.get("source_url"),
        )
        for document in raw_documents
    ]


@router.get("/", response_model=list[AlertCard])
def list_alerts(
    db: DB,
    source_type: Optional[str] = Query(None),
    min_materiality: float = Query(0.5, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
) -> list[AlertCard]:
    """List recent high-materiality evidence items (alerts)."""
    q = (
        db.query(EvidenceItem)
        .filter(EvidenceItem.materiality_score >= min_materiality)
        .order_by(EvidenceItem.created_at.desc())
    )
    if source_type:
        q = q.filter(EvidenceItem.source_type == source_type)

    items = q.limit(limit).all()
    cards = [
        AlertCard(
            id=item.id,
            source_type=item.source_type,
            title=item.title,
            materiality_score=item.materiality_score,
            published_at=item.published_at.isoformat() if item.published_at else None,
            source_url=item.source_url,
        )
        for item in items
    ]
    if not cards:
        return _list_alerts_from_knowledge_store(source_type=source_type, limit=limit)
    return cards
