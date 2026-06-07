"""Server-rendered UI pages for Step 13."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from bve.entities.acquirer import ACQUIRER_BY_ID
from bve.persistence.models import (
    AcquisitionScore,
    Asset,
    Catalyst,
    Company,
    DecisionRecord,
    EvidenceItem,
    FinancingForecast,
    ImpliedExpectation,
    MarketSnapshot,
    OutcomeRecord,
    ParameterVersion,
    ScenarioTree,
    Trial,
    VariantThesis,
)

router = APIRouter(tags=["ui"], include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
DB = Annotated[Session, Depends(get_db)]


def _nav_context(active_page: str) -> dict[str, str]:
    return {
        "dashboard_href": "/",
        "acquirers_href": "/acquirers",
        "deals_href": "/deals",
        "alerts_href": "/alerts",
        "calibration_href": "/calibration",
        "active_page": active_page,
    }


def _acquirer_href_for_company(company: Company | None) -> str | None:
    if not company or not company.ticker:
        return None
    for slug, profile in ACQUIRER_BY_ID.items():
        if profile.ticker == company.ticker:
            return f"/acquirers/{slug}"
    return None


@router.get("/")
def dashboard_page(request: Request, db: DB):
    top_assets = (
        db.query(Asset, Company)
        .join(Company, Company.id == Asset.company_id)
        .order_by(Asset.updated_at.desc())
        .limit(8)
        .all()
    )
    recent_alerts = (
        db.query(EvidenceItem)
        .order_by(EvidenceItem.created_at.desc())
        .limit(6)
        .all()
    )
    pending_catalysts = db.query(Catalyst).filter(Catalyst.status == "pending").count()
    active_theses = db.query(VariantThesis).filter(VariantThesis.status == "active").count()

    deal_rows = (
        db.query(AcquisitionScore)
        .order_by(AcquisitionScore.fit_score.desc())
        .limit(6)
        .all()
    )
    deals = []
    for row in deal_rows:
        target = db.get(Company, row.target_company_id)
        acquirer = db.get(Company, row.acquirer_company_id)
        deals.append(
            {
                "target_name": target.name if target else row.target_company_id,
                "target_ticker": target.ticker if target else None,
                "acquirer_name": acquirer.name if acquirer else row.acquirer_company_id,
                "acquirer_ticker": acquirer.ticker if acquirer else None,
                "fit_score": row.fit_score,
                "timing_bucket": row.timing_bucket,
                "target_href": f"/assets/{target.ticker}" if target and target.ticker else None,
                "acquirer_href": _acquirer_href_for_company(acquirer),
            }
        )

    assets = [
        {
            "name": asset.name,
            "ticker": company.ticker,
            "company_name": company.name,
            "indication": asset.indication,
            "current_phase": asset.current_phase,
            "detail_href": f"/assets/{company.ticker}" if company.ticker else None,
        }
        for asset, company in top_assets
    ]

    alerts = [
        {
            "title": item.title or "Untitled evidence item",
            "source_type": item.source_type or "unknown",
            "materiality_score": item.materiality_score,
            "source_url": item.source_url,
        }
        for item in recent_alerts
    ]

    context = {
        "request": request,
        "page_title": "BVE Dashboard",
        "summary_cards": [
            {"label": "Tracked Assets", "value": db.query(Asset).count(), "tone": "primary"},
            {"label": "Pending Catalysts", "value": pending_catalysts, "tone": "warning"},
            {"label": "Active Theses", "value": active_theses, "tone": "primary"},
            {"label": "Logged Decisions", "value": db.query(DecisionRecord).count(), "tone": "muted"},
        ],
        "assets": assets,
        "deals": deals,
        "alerts": alerts,
        **_nav_context("dashboard"),
    }
    return templates.TemplateResponse(request, "dashboard.html", context)


@router.get("/assets/{ticker}")
def asset_page(request: Request, ticker: str, db: DB):
    company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company with ticker {ticker!r} not found")

    asset = db.query(Asset).filter(Asset.company_id == company.id).order_by(Asset.updated_at.desc()).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"No assets found for ticker {ticker!r}")

    thesis = (
        db.query(VariantThesis)
        .filter(VariantThesis.asset_id == asset.id, VariantThesis.status == "active")
        .order_by(VariantThesis.updated_at.desc())
        .first()
    )
    financing = (
        db.query(FinancingForecast)
        .filter(FinancingForecast.company_id == company.id)
        .order_by(FinancingForecast.as_of.desc())
        .first()
    )
    scenario_tree = (
        db.query(ScenarioTree)
        .filter(ScenarioTree.asset_id == asset.id)
        .order_by(ScenarioTree.created_at.desc())
        .first()
    )
    market_snapshot = (
        db.query(MarketSnapshot)
        .filter(MarketSnapshot.company_id == company.id)
        .order_by(MarketSnapshot.as_of.desc())
        .first()
    )
    implied = None
    if market_snapshot:
        implied = (
            db.query(ImpliedExpectation)
            .filter(
                ImpliedExpectation.asset_id == asset.id,
                ImpliedExpectation.market_snapshot_id == market_snapshot.id,
            )
            .first()
        )

    related_deals = (
        db.query(AcquisitionScore)
        .filter(AcquisitionScore.target_company_id == company.id)
        .order_by(AcquisitionScore.fit_score.desc())
        .limit(5)
        .all()
    )
    deal_rows: list[dict[str, object]] = []
    for row in related_deals:
        acquirer = db.get(Company, row.acquirer_company_id)
        deal_rows.append(
            {
                "acquirer_name": acquirer.name if acquirer else row.acquirer_company_id,
                "acquirer_ticker": acquirer.ticker if acquirer else None,
                "fit_score": row.fit_score,
                "timing_bucket": row.timing_bucket,
                "acquirer_href": _acquirer_href_for_company(acquirer),
            }
        )

    context = {
        "request": request,
        "page_title": f"{company.ticker} Asset Page",
        "company": company,
        "asset": asset,
        "trials": db.query(Trial).filter(Trial.asset_id == asset.id).order_by(Trial.created_at.desc()).all(),
        "catalysts": db.query(Catalyst)
        .filter(Catalyst.asset_id == asset.id)
        .order_by(Catalyst.expected_date.asc())
        .all(),
        "thesis": thesis,
        "implied": implied,
        "financing": financing,
        "scenario_tree": scenario_tree,
        "related_deals": deal_rows,
        **_nav_context("dashboard"),
    }
    return templates.TemplateResponse(request, "asset.html", context)


@router.get("/acquirers")
def acquirer_index_page(request: Request, db: DB):
    cards: list[dict[str, object]] = []
    for slug, profile in ACQUIRER_BY_ID.items():
        company = db.query(Company).filter(Company.ticker == profile.ticker).first()
        top_target_count = 0
        if company:
            top_target_count = (
                db.query(AcquisitionScore)
                .filter(AcquisitionScore.acquirer_company_id == company.id)
                .count()
            )
        cards.append(
            {
                "slug": slug,
                "name": profile.name,
                "ticker": profile.ticker,
                "bd_style": profile.bd_style.value,
                "preferred_phase": profile.preferred_phase,
                "cash_firepower_millions": profile.cash_firepower_millions,
                "loe_urgency": profile.loe_urgency,
                "top_target_count": top_target_count,
                "detail_href": f"/acquirers/{slug}",
            }
        )

    cards.sort(key=lambda item: (-(item["top_target_count"]), str(item["name"])))

    context = {
        "request": request,
        "page_title": "Acquirers",
        "acquirers": cards,
        **_nav_context("acquirers"),
    }
    return templates.TemplateResponse(request, "acquirers.html", context)


@router.get("/acquirers/{slug}")
def acquirer_page(request: Request, slug: str, db: DB, limit: int = Query(20, ge=1, le=100)):
    profile = ACQUIRER_BY_ID.get(slug)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Acquirer {slug!r} not found")

    company = db.query(Company).filter(Company.ticker == profile.ticker).first()
    top_targets: list[dict] = []
    if company:
        score_rows = (
            db.query(AcquisitionScore)
            .filter(AcquisitionScore.acquirer_company_id == company.id)
            .order_by(AcquisitionScore.fit_score.desc())
            .limit(limit)
            .all()
        )
        for row in score_rows:
            target = db.get(Company, row.target_company_id)
            top_targets.append(
                {
                    "target_name": target.name if target else row.target_company_id,
                    "target_ticker": target.ticker if target else None,
                    "fit_score": row.fit_score,
                    "timing_bucket": row.timing_bucket,
                    "affordability_score": row.affordability_score,
                    "strategic_fit_score": row.strategic_fit_score,
                    "confidence": row.confidence,
                }
            )

    context = {
        "request": request,
        "page_title": f"{profile.name} Acquirer Page",
        "profile": profile,
        "top_targets": top_targets,
        **_nav_context("acquirers"),
    }
    return templates.TemplateResponse(request, "acquirer.html", context)


@router.get("/deals")
def deals_page(
    request: Request,
    db: DB,
    acquirer: str | None = Query(None),
    timing_bucket: str | None = Query(None),
    min_fit_score: float = Query(0.0, ge=0.0, le=1.0),
):
    query = db.query(AcquisitionScore)
    if min_fit_score > 0.0:
        query = query.filter(AcquisitionScore.fit_score >= min_fit_score)
    if timing_bucket:
        query = query.filter(AcquisitionScore.timing_bucket == timing_bucket)
    if acquirer:
        acquirer_company = (
            db.query(Company)
            .filter((Company.ticker == acquirer.upper()) | (Company.id == acquirer))
            .first()
        )
        if acquirer_company:
            query = query.filter(AcquisitionScore.acquirer_company_id == acquirer_company.id)
        else:
            query = query.filter(AcquisitionScore.acquirer_company_id == "__none__")

    score_rows = query.order_by(AcquisitionScore.fit_score.desc()).limit(100).all()
    deals = []
    for row in score_rows:
        target = db.get(Company, row.target_company_id)
        acquirer_company = db.get(Company, row.acquirer_company_id)
        deals.append(
            {
                "target_name": target.name if target else row.target_company_id,
                "target_ticker": target.ticker if target else None,
                "acquirer_name": acquirer_company.name if acquirer_company else row.acquirer_company_id,
                "acquirer_ticker": acquirer_company.ticker if acquirer_company else None,
                "fit_score": row.fit_score,
                "timing_bucket": row.timing_bucket,
                "affordability_score": row.affordability_score,
                "strategic_fit_score": row.strategic_fit_score,
                "confidence": row.confidence,
                "target_href": f"/assets/{target.ticker}" if target and target.ticker else None,
                "acquirer_href": _acquirer_href_for_company(acquirer_company),
            }
        )

    context = {
        "request": request,
        "page_title": "Deals",
        "deals": deals,
        "filters": {
            "acquirer": acquirer or "",
            "timing_bucket": timing_bucket or "",
            "min_fit_score": min_fit_score,
        },
        **_nav_context("deals"),
    }
    return templates.TemplateResponse(request, "deals.html", context)


@router.get("/alerts")
def alerts_page(
    request: Request,
    db: DB,
    source_type: str | None = Query(None),
    min_materiality: float = Query(0.5, ge=0.0, le=1.0),
):
    query = db.query(EvidenceItem).filter(EvidenceItem.materiality_score >= min_materiality)
    if source_type:
        query = query.filter(EvidenceItem.source_type == source_type)
    alerts = query.order_by(EvidenceItem.created_at.desc()).limit(100).all()
    context = {
        "request": request,
        "page_title": "Alerts",
        "alerts": alerts,
        "filters": {"source_type": source_type or "", "min_materiality": min_materiality},
        **_nav_context("alerts"),
    }
    return templates.TemplateResponse(request, "alerts.html", context)


@router.get("/calibration")
def calibration_page(request: Request, db: DB):
    promoted_versions = (
        db.query(ParameterVersion)
        .filter(ParameterVersion.promoted == True)  # noqa: E712
        .order_by(ParameterVersion.created_at.desc())
        .all()
    )
    pending_versions = (
        db.query(ParameterVersion)
        .filter(ParameterVersion.promoted == False)  # noqa: E712
        .order_by(ParameterVersion.created_at.desc())
        .all()
    )
    recent_decisions = (
        db.query(DecisionRecord)
        .order_by(DecisionRecord.created_at.desc())
        .limit(12)
        .all()
    )
    context = {
        "request": request,
        "page_title": "Calibration",
        "metrics": {
            "total_decisions": db.query(DecisionRecord).count(),
            "total_outcomes": db.query(OutcomeRecord).count(),
            "pending_parameter_versions": len(pending_versions),
        },
        "promoted_versions": promoted_versions,
        "pending_versions": pending_versions,
        "recent_decisions": recent_decisions,
        **_nav_context("calibration"),
    }
    return templates.TemplateResponse(request, "calibration.html", context)
