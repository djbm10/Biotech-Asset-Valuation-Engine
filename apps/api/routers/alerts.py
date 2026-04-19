"""Alerts endpoint — GET /api/alerts — high-materiality recent evidence."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from apps.api.schemas.responses import AlertCard
from bve.persistence.models import EvidenceItem

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
DB = Annotated[Session, Depends(get_db)]


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
    return [
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
