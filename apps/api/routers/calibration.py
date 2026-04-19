"""Calibration endpoint — GET /api/calibration — model metrics + pending updates."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from apps.api.schemas.responses import CalibrationSummary
from bve.persistence.models import DecisionRecord, OutcomeRecord, ParameterVersion

router = APIRouter(prefix="/api/calibration", tags=["calibration"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/", response_model=CalibrationSummary)
def get_calibration(db: DB) -> CalibrationSummary:
    """Return calibration summary: decision/outcome counts + parameter versions."""
    total_decisions = db.query(DecisionRecord).count()
    total_outcomes = db.query(OutcomeRecord).count()
    pending = db.query(ParameterVersion).filter(ParameterVersion.promoted == False).all()  # noqa: E712
    promoted = db.query(ParameterVersion).filter(ParameterVersion.promoted == True).all()  # noqa: E712

    return CalibrationSummary(
        total_decisions=total_decisions,
        total_outcomes=total_outcomes,
        pending_parameter_versions=len(pending),
        promoted_versions=[
            {
                "id": pv.id,
                "name": pv.name,
                "version": pv.version,
                "weights": pv.weights,
                "created_at": pv.created_at.isoformat(),
            }
            for pv in promoted
        ],
    )
