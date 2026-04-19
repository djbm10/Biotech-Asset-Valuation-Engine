"""Theses + postmortems endpoints — POST /api/theses, POST /api/postmortems."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from apps.api.schemas.responses import PostmortemInput, VariantThesisInput
from bve.persistence.models import Asset, DecisionRecord, OutcomeRecord, VariantThesis

router = APIRouter(prefix="/api", tags=["theses"])
DB = Annotated[Session, Depends(get_db)]


@router.post("/theses/{asset_id}", status_code=201)
def create_or_update_thesis(
    asset_id: str, body: VariantThesisInput, db: DB
) -> dict:
    """Create or update a variant thesis for an asset."""
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id!r} not found")

    if not body.documented:
        raise HTTPException(
            status_code=422,
            detail="Thesis must be documented (documented=true) before saving",
        )

    # Deactivate existing active theses
    existing = (
        db.query(VariantThesis)
        .filter(VariantThesis.asset_id == asset_id, VariantThesis.status == "active")
        .all()
    )
    for t in existing:
        t.status = "resolved"

    thesis = VariantThesis(
        asset_id=asset_id,
        market_view=body.market_view,
        model_view=body.model_view,
        delta_view=body.delta_view,
        kill_criteria=body.kill_criteria,
        confidence=body.confidence,
        documented=body.documented,
        status="active",
    )
    db.add(thesis)
    db.commit()
    db.refresh(thesis)
    return {"id": thesis.id, "status": "created"}


@router.post("/postmortems/{decision_id}", status_code=201)
def create_postmortem(decision_id: str, body: PostmortemInput, db: DB) -> dict:
    """Log a postmortem outcome for a prior decision."""
    decision = db.get(DecisionRecord, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id!r} not found")

    existing = db.query(OutcomeRecord).filter(
        OutcomeRecord.decision_record_id == decision_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409, detail="Outcome already recorded for this decision"
        )

    resolved_at = (
        datetime.fromisoformat(body.resolved_at)
        if body.resolved_at
        else datetime.now(timezone.utc)
    )

    outcome = OutcomeRecord(
        decision_record_id=decision_id,
        realized_outcome=body.realized_outcome,
        resolved_at=resolved_at,
    )
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return {"id": outcome.id, "status": "created"}
