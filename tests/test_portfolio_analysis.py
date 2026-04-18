"""Tests for portfolio_context, recommendation_engine, and risk_budget modules."""

from __future__ import annotations

from datetime import date

import pytest

from bve.analysis.portfolio_context import (
    HoldingExposure,
    PortfolioContext,
    PortfolioSnapshot,
)
from bve.analysis.recommendation_engine import (
    Recommendation,
    RecommendationEngine,
    RecommendationInput,
)
from bve.analysis.risk_budget import RiskBudget, RiskBudgetAllocation


# ---------------------------------------------------------------------------
# HoldingExposure
# ---------------------------------------------------------------------------

def test_holding_exposure_basic():
    h = HoldingExposure(
        asset_id="A1",
        ticker="TICK",
        position_size_pct=0.08,
        therapeutic_area="oncology",
        modality="small_molecule",
        catalyst_month="2026-03",
        risk_bucket="late",
        market_cap_tier="small",
    )
    assert h.position_size_pct == 0.08
    assert h.market_cap_tier == "small"


def test_holding_exposure_no_catalyst():
    h = HoldingExposure(
        asset_id="A1",
        ticker="TICK",
        position_size_pct=0.05,
        therapeutic_area="rare_disease",
        modality="biologic",
        risk_bucket="early",
        market_cap_tier="micro",
    )
    assert h.catalyst_month is None


# ---------------------------------------------------------------------------
# PortfolioSnapshot
# ---------------------------------------------------------------------------

def _make_snapshot() -> PortfolioSnapshot:
    h = HoldingExposure(
        asset_id="A1", ticker="TICK", position_size_pct=0.08,
        therapeutic_area="oncology", modality="small_molecule",
        risk_bucket="late", market_cap_tier="small",
    )
    return PortfolioSnapshot(
        snapshot_date=date(2025, 6, 1),
        holdings=[h],
        gross_exposure_pct=0.80,
        net_exposure_pct=0.70,
        ta_concentration={"oncology": 0.50},
        modality_concentration={"small_molecule": 0.60},
        catalyst_month_concentration={},
        risk_bucket_concentration={"late": 0.60},
    )


def test_portfolio_snapshot_basic():
    snap = _make_snapshot()
    assert snap.gross_exposure_pct == 0.80
    assert "oncology" in snap.ta_concentration


# ---------------------------------------------------------------------------
# PortfolioContext
# ---------------------------------------------------------------------------

def test_portfolio_context_basic():
    snap = _make_snapshot()
    ctx = PortfolioContext(
        asset_id="A1",
        snapshot=snap,
        current_position_pct=0.08,
        ta_remaining_budget_pct=0.10,
        modality_remaining_budget_pct=0.15,
        catalyst_cluster_count=2,
        liquidity_score=0.75,
        crowding_score=0.30,
    )
    assert ctx.catalyst_cluster_count == 2
    assert ctx.liquidity_score == 0.75


# ---------------------------------------------------------------------------
# RecommendationInput / RecommendationEngine
# ---------------------------------------------------------------------------

def _make_input(
    valuation_gap_pct: float = 40.0,
    thesis_confidence: float = 0.70,
    catalyst_return_pct: float = 25.0,
    financing_risk: float = 0.20,
    science_score: float = 0.75,
    competition_risk: float = 0.30,
) -> RecommendationInput:
    return RecommendationInput(
        asset_id="A1",
        ticker="TICK",
        valuation_gap_pct=valuation_gap_pct,
        thesis_confidence=thesis_confidence,
        catalyst_expected_return_pct=catalyst_return_pct,
        financing_risk_score=financing_risk,
        science_score=science_score,
        competition_risk_score=competition_risk,
    )


def test_recommendation_engine_add_action():
    engine = RecommendationEngine()
    rec = engine.recommend(_make_input())
    assert rec.action in ("add", "hold", "watchlist", "avoid")
    assert 0.0 <= rec.composite_score <= 1.0
    assert rec.ticker == "TICK"


def test_recommendation_engine_high_composite_gives_add():
    engine = RecommendationEngine()
    rec = engine.recommend(_make_input(
        valuation_gap_pct=80.0,
        thesis_confidence=0.90,
        catalyst_return_pct=60.0,
        financing_risk=0.05,
        science_score=0.90,
    ))
    assert rec.action == "add"
    assert rec.conviction == "high"


def test_recommendation_engine_avoid_on_bad_inputs():
    engine = RecommendationEngine()
    rec = engine.recommend(_make_input(
        valuation_gap_pct=-80.0,
        thesis_confidence=0.10,
        catalyst_return_pct=-60.0,
        financing_risk=0.95,
        science_score=0.10,
    ))
    assert rec.action == "avoid"


def test_recommendation_engine_composite_clipped():
    engine = RecommendationEngine()
    rec = engine.recommend(_make_input(valuation_gap_pct=10000.0, thesis_confidence=1.0))
    assert rec.composite_score <= 1.0


# ---------------------------------------------------------------------------
# RiskBudgetAllocation / RiskBudget
# ---------------------------------------------------------------------------

def test_risk_budget_allocation_basic():
    alloc = RiskBudgetAllocation(
        bucket="oncology",
        max_pct=0.40,
        current_pct=0.35,
        remaining_pct=0.05,
        is_breached=False,
    )
    assert alloc.is_breached is False


def test_risk_budget_allocation_breached():
    alloc = RiskBudgetAllocation(
        bucket="oncology",
        max_pct=0.40,
        current_pct=0.45,
        remaining_pct=0.0,
        is_breached=True,
    )
    assert alloc.is_breached is True


def test_risk_budget_defaults():
    rb = RiskBudget(
        portfolio_id="P1",
        budget_date=date(2025, 6, 1),
        total_risk_utilization_pct=0.65,
        remaining_gross_budget_pct=0.35,
    )
    assert rb.gross_limit_pct == 1.0
    assert rb.single_name_max_pct == 0.15
    assert rb.catalyst_cluster_max == 5
    assert rb.allocations == []


def test_risk_budget_with_allocations():
    alloc = RiskBudgetAllocation(
        bucket="oncology", max_pct=0.40, current_pct=0.30,
        remaining_pct=0.10, is_breached=False,
    )
    rb = RiskBudget(
        portfolio_id="P1",
        budget_date=date(2025, 6, 1),
        allocations=[alloc],
        total_risk_utilization_pct=0.60,
        remaining_gross_budget_pct=0.40,
    )
    assert len(rb.allocations) == 1
