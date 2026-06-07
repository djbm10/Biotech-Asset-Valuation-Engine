"""Asset endpoints — GET /api/assets, GET /api/assets/{ticker}."""

from __future__ import annotations

import os
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from apps.api.schemas.responses import AssetCard, AssetPage, CompanyCard
from bve.persistence.models import (
    Asset,
    AssetDossierRecord,
    Catalyst,
    Company,
    FinancingForecast,
    ImpliedExpectation,
    MarketSnapshot,
    ScenarioTree,
    Trial,
    VariantThesis,
)

router = APIRouter(prefix="/api/assets", tags=["assets"])

DB = Annotated[Session, Depends(get_db)]


def _asset_to_card(asset: Asset, db: Session) -> AssetCard:
    company = db.get(Company, asset.company_id)
    return AssetCard(
        id=asset.id,
        company_id=asset.company_id,
        company_name=company.name if company else None,
        ticker=company.ticker if company else None,
        name=asset.name,
        modality=asset.modality,
        therapeutic_area=asset.therapeutic_area,
        indication=asset.indication,
        current_phase=asset.current_phase,
        status=asset.status,
        partnered=asset.partnered,
    )


def _list_assets_from_knowledge_store(
    *,
    ta: Optional[str],
    phase: Optional[str],
    ticker: Optional[str],
    limit: int,
    offset: int,
) -> list[AssetCard]:
    db_path = os.environ.get("BVE_KNOWLEDGE_DB_PATH")
    if not db_path:
        return []
    from bve.intelligence.knowledge_layer import KnowledgeStore

    store = KnowledgeStore(db_path)
    try:
        entries = store.list_asset_registry(ta=ta, stage=phase)
        alerts = store.get_opportunity_alerts(limit=limit)
        raw_documents = store.get_raw_documents(limit=limit)
    finally:
        store.close()
    if ticker:
        entries = [entry for entry in entries if (entry.ticker or "").upper() == ticker.upper()]
    entries = entries[offset : offset + limit]
    cards = [
        AssetCard(
            id=entry.asset_id,
            company_id=entry.company_id,
            company_name=None,
            ticker=entry.ticker,
            name=entry.drug_name or entry.asset_id,
            modality=entry.modality,
            therapeutic_area=entry.therapeutic_area,
            indication=entry.indication,
            current_phase=entry.stage,
            status="tracked",
            partnered=False,
        )
        for entry in entries
    ]
    if cards:
        return cards
    if ta or phase or ticker:
        return []
    seen: set[str] = set()
    fallback_cards: list[AssetCard] = []
    for alert in alerts:
        if alert.asset_id in seen:
            continue
        seen.add(alert.asset_id)
        fallback_cards.append(
            AssetCard(
                id=alert.asset_id,
                company_id=None,
                company_name=None,
                ticker=None,
                name=alert.asset_id,
                modality=None,
                therapeutic_area=None,
                indication=None,
                current_phase=None,
                status="tracked",
                partnered=False,
            )
        )
    if fallback_cards:
        return fallback_cards[offset : offset + limit]
    for document in raw_documents:
        payload = document.payload_json
        hints = payload.get("entity_hints") or {}
        asset_id = hints.get("asset_id") or payload.get("asset_id") or payload.get("id")
        if not asset_id or asset_id in seen:
            continue
        seen.add(str(asset_id))
        fallback_cards.append(
            AssetCard(
                id=str(asset_id),
                company_id=hints.get("company_id"),
                company_name=None,
                ticker=None,
                name=str(asset_id),
                modality=None,
                therapeutic_area=None,
                indication=None,
                current_phase=None,
                status="tracked",
                partnered=False,
            )
        )
    return fallback_cards[offset : offset + limit]


@router.get("/", response_model=list[AssetCard])
def list_assets(
    db: DB,
    ta: Optional[str] = Query(None, description="Filter by therapeutic area"),
    phase: Optional[str] = Query(None, description="Filter by phase"),
    ticker: Optional[str] = Query(None, description="Filter by company ticker"),
    has_catalyst: Optional[bool] = Query(None, description="Only assets with pending catalysts"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[AssetCard]:
    """List assets with optional filters."""
    q = db.query(Asset)

    if ta:
        q = q.filter(Asset.therapeutic_area.ilike(f"%{ta}%"))
    if phase:
        q = q.filter(Asset.current_phase == phase)
    if ticker:
        company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
        if company:
            q = q.filter(Asset.company_id == company.id)
        else:
            return []
    if has_catalyst:
        from sqlalchemy import exists
        q = q.filter(
            exists().where(
                (Catalyst.asset_id == Asset.id) & (Catalyst.status == "pending")
            )
        )

    assets = q.offset(offset).limit(limit).all()
    cards = [_asset_to_card(a, db) for a in assets]
    if not cards:
        return _list_assets_from_knowledge_store(
            ta=ta,
            phase=phase,
            ticker=ticker,
            limit=limit,
            offset=offset,
        )
    return cards


@router.get("/{ticker}", response_model=AssetPage)
def get_asset_page(ticker: str, db: DB) -> AssetPage:
    """Full asset page payload — includes dossier, expectations, thesis, catalyst tree."""
    # Find company by ticker first, then get first asset
    company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company with ticker {ticker!r} not found")

    assets = db.query(Asset).filter(Asset.company_id == company.id).all()
    if not assets:
        raise HTTPException(status_code=404, detail=f"No assets found for ticker {ticker!r}")

    asset = assets[0]  # primary asset

    # Trials
    trials = db.query(Trial).filter(Trial.asset_id == asset.id).all()

    # Catalysts
    catalysts = db.query(Catalyst).filter(Catalyst.asset_id == asset.id).all()

    # Dossier
    dossier_rec = db.query(AssetDossierRecord).filter(
        AssetDossierRecord.asset_id == asset.id
    ).first()

    # Latest implied expectation
    latest_snapshot = (
        db.query(MarketSnapshot)
        .filter(MarketSnapshot.company_id == company.id)
        .order_by(MarketSnapshot.as_of.desc())
        .first()
    )
    implied_exp = None
    if latest_snapshot:
        ie = (
            db.query(ImpliedExpectation)
            .filter(
                ImpliedExpectation.asset_id == asset.id,
                ImpliedExpectation.market_snapshot_id == latest_snapshot.id,
            )
            .first()
        )
        if ie:
            implied_exp = {
                "implied_pos": ie.implied_pos,
                "implied_peak_sales": ie.implied_peak_sales,
                "valuation_gap_pct": ie.valuation_gap_pct,
                "solver_confidence": ie.solver_confidence,
            }

    # Latest variant thesis
    thesis = (
        db.query(VariantThesis)
        .filter(VariantThesis.asset_id == asset.id, VariantThesis.status == "active")
        .order_by(VariantThesis.updated_at.desc())
        .first()
    )

    # Latest scenario tree
    tree = (
        db.query(ScenarioTree)
        .filter(ScenarioTree.asset_id == asset.id)
        .order_by(ScenarioTree.created_at.desc())
        .first()
    )

    # Latest financing forecast
    fin = (
        db.query(FinancingForecast)
        .filter(FinancingForecast.company_id == company.id)
        .order_by(FinancingForecast.as_of.desc())
        .first()
    )

    company_card = CompanyCard(
        id=company.id,
        ticker=company.ticker,
        name=company.name,
        company_type=company.company_type,
        market_cap=company.market_cap,
        cash=company.cash,
        enterprise_value=company.enterprise_value,
    )

    return AssetPage(
        asset=_asset_to_card(asset, db),
        company=company_card,
        trials=[
            {
                "id": t.id, "nct_id": t.nct_id, "phase": t.phase,
                "endpoint_primary": t.endpoint_primary, "status": t.status,
            }
            for t in trials
        ],
        catalysts=[
            {
                "id": c.id, "catalyst_type": c.catalyst_type,
                "expected_date": c.expected_date, "status": c.status,
                "confidence": c.confidence,
            }
            for c in catalysts
        ],
        dossier=dossier_rec.jsonb_state if dossier_rec else None,
        implied_expectation=implied_exp,
        variant_thesis={
            "market_view": thesis.market_view,
            "model_view": thesis.model_view,
            "delta_view": thesis.delta_view,
            "confidence": thesis.confidence,
            "status": thesis.status,
        } if thesis else None,
        latest_scenario_tree=tree.tree_json if tree else None,
        latest_financing_forecast={
            "runway_months": fin.runway_months,
            "pre_catalyst_raise_prob": fin.pre_catalyst_raise_prob,
            "expected_dilution_low": fin.expected_dilution_low,
            "expected_dilution_high": fin.expected_dilution_high,
            "distress_risk": fin.distress_risk,
        } if fin else None,
    )
