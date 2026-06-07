"""Deals endpoint — GET /api/deals — ranked M&A targets across all acquirers."""

from __future__ import annotations

import os
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from apps.api.schemas.responses import DealCard
from bve.persistence.models import AcquisitionScore, Company

router = APIRouter(prefix="/api/deals", tags=["deals"])
DB = Annotated[Session, Depends(get_db)]


def _list_deals_from_knowledge_store(
    *,
    acquirer: Optional[str],
    min_fit_score: float,
    limit: int,
) -> list[DealCard]:
    if acquirer:
        return []
    db_path = os.environ.get("BVE_KNOWLEDGE_DB_PATH")
    if not db_path:
        return []
    from bve.intelligence.knowledge_layer import KnowledgeStore

    store = KnowledgeStore(db_path)
    try:
        entries = store.list_asset_registry()
        raw_documents = store.get_raw_documents(limit=limit)
    finally:
        store.close()
    cards: list[DealCard] = []
    for entry in entries[:limit]:
        score = 0.5
        if score < min_fit_score:
            continue
        cards.append(
            DealCard(
                target_company_id=entry.company_id or entry.asset_id,
                target_name=entry.drug_name or entry.ticker or entry.asset_id,
                acquirer_company_id="knowledge_store",
                acquirer_name="Knowledge Store Candidate",
                fit_score=score,
                timing_bucket="unknown",
                affordability_score=None,
                strategic_fit_score=None,
                confidence=None,
            )
        )
    if cards:
        return cards
    for document in raw_documents[:limit]:
        payload = document.payload_json
        hints = payload.get("entity_hints") or {}
        asset_id = str(hints.get("asset_id") or payload.get("asset_id") or document.id)
        cards.append(
            DealCard(
                target_company_id=str(hints.get("company_id") or asset_id),
                target_name=asset_id,
                acquirer_company_id="knowledge_store",
                acquirer_name="Knowledge Store Candidate",
                fit_score=0.5,
                timing_bucket="unknown",
                affordability_score=None,
                strategic_fit_score=None,
                confidence=None,
            )
        )
    return cards


@router.get("/", response_model=list[DealCard])
def list_deals(
    db: DB,
    acquirer: Optional[str] = Query(None, description="Filter by acquirer company_id"),
    timing_bucket: Optional[str] = Query(None, description="Filter by timing bucket"),
    min_fit_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
) -> list[DealCard]:
    """List ranked M&A target-acquirer pairs with optional filters."""
    q = db.query(AcquisitionScore)

    if min_fit_score > 0:
        q = q.filter(AcquisitionScore.fit_score >= min_fit_score)
    if timing_bucket:
        q = q.filter(AcquisitionScore.timing_bucket == timing_bucket)

    if acquirer:
        # Filter by acquirer ticker or company_id via Company table
        acquirer_co = (
            db.query(Company)
            .filter(
                (Company.ticker == acquirer.upper()) | (Company.id == acquirer)
            )
            .first()
        )
        if acquirer_co:
            q = q.filter(AcquisitionScore.acquirer_company_id == acquirer_co.id)
        else:
            return []

    scores = q.order_by(AcquisitionScore.fit_score.desc()).limit(limit).all()

    cards = []
    for s in scores:
        target_co = db.get(Company, s.target_company_id)
        acquirer_co = db.get(Company, s.acquirer_company_id)
        cards.append(
            DealCard(
                target_company_id=s.target_company_id,
                target_name=target_co.name if target_co else s.target_company_id,
                acquirer_company_id=s.acquirer_company_id,
                acquirer_name=acquirer_co.name if acquirer_co else s.acquirer_company_id,
                fit_score=s.fit_score or 0.0,
                timing_bucket=s.timing_bucket or "unknown",
                affordability_score=s.affordability_score,
                strategic_fit_score=s.strategic_fit_score,
                confidence=s.confidence,
            )
        )
    if not cards:
        return _list_deals_from_knowledge_store(
            acquirer=acquirer,
            min_fit_score=min_fit_score,
            limit=limit,
        )
    return cards
