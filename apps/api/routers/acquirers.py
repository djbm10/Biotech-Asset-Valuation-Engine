"""Acquirer endpoints — GET /api/acquirers, GET /api/acquirers/{slug}."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from apps.api.schemas.responses import AcquirerCard, AcquirerPage
from bve.entities.acquirer import ACQUIRER_UNIVERSE, ACQUIRER_BY_ID
from bve.intelligence.acquisition_fit import AcquisitionFitEngine
from bve.persistence.models import AcquisitionScore, Company

router = APIRouter(prefix="/api/acquirers", tags=["acquirers"])
DB = Annotated[Session, Depends(get_db)]

_fit_engine = AcquisitionFitEngine()


def _get_or_create_acquirer_company(
    db: Session, company_id: str, profile
) -> Company:
    c = db.query(Company).filter(Company.ticker == profile.ticker).first()
    if not c:
        c = Company(
            name=profile.name,
            ticker=profile.ticker,
            company_type="big_pharma",
            cash=profile.cash_millions,
        )
        db.add(c)
        db.flush()
    return c


@router.get("/", response_model=list[AcquirerCard])
def list_acquirers(db: DB) -> list[AcquirerCard]:
    """List all tracked acquirers with high-level metrics."""
    cards = []
    for profile in ACQUIRER_UNIVERSE:
        # Count top targets stored in DB for this acquirer
        co = db.query(Company).filter(Company.ticker == profile.ticker).first()
        target_count = 0
        if co:
            target_count = (
                db.query(AcquisitionScore)
                .filter(AcquisitionScore.acquirer_company_id == co.id)
                .count()
            )
        cards.append(
            AcquirerCard(
                company_id=profile.company_id,
                company_name=profile.name,
                ticker=profile.ticker,
                cash_firepower_millions=profile.cash_firepower_millions,
                loe_urgency=profile.loe_urgency,
                strategic_areas=profile.strategic_areas,
                top_target_count=target_count,
            )
        )
    return cards


@router.get("/{slug}", response_model=AcquirerPage)
def get_acquirer_page(slug: str, db: DB, limit: int = 20) -> AcquirerPage:
    """Full acquirer page: profile + top ranked targets."""
    profile = ACQUIRER_BY_ID.get(slug)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Acquirer {slug!r} not found")

    # Load stored acquisition scores
    company = db.query(Company).filter(Company.ticker == profile.ticker).first()
    stored_scores: list[dict] = []
    if company:
        scores = (
            db.query(AcquisitionScore)
            .filter(AcquisitionScore.acquirer_company_id == company.id)
            .order_by(AcquisitionScore.fit_score.desc())
            .limit(limit)
            .all()
        )
        for s in scores:
            target_co = db.get(Company, s.target_company_id)
            stored_scores.append({
                "target_company_id": s.target_company_id,
                "target_name": target_co.name if target_co else s.target_company_id,
                "fit_score": s.fit_score,
                "timing_bucket": s.timing_bucket,
                "affordability_score": s.affordability_score,
                "strategic_fit_score": s.strategic_fit_score,
                "confidence": s.confidence,
            })

    return AcquirerPage(
        profile={
            "company_id": profile.company_id,
            "name": profile.name,
            "ticker": profile.ticker,
            "cash_firepower_millions": profile.cash_firepower_millions,
            "strategic_areas": profile.strategic_areas,
            "preferred_modalities": profile.preferred_modalities,
            "loe_urgency": profile.loe_urgency,
            "bd_style": profile.bd_style.value,
            "preferred_phase": profile.preferred_phase,
            "loe_cliffs": [
                {
                    "product": c.product_name,
                    "indication": c.indication,
                    "loe_year": c.loe_year,
                    "revenue_at_risk_millions": c.revenue_at_risk_millions,
                }
                for c in profile.loe_cliffs
            ],
            "pipeline_gaps": [
                {
                    "therapeutic_area": g.therapeutic_area,
                    "modality": g.modality,
                    "priority": g.priority,
                    "rationale": g.rationale,
                }
                for g in profile.pipeline_gaps
            ],
        },
        top_targets=stored_scores,
    )
