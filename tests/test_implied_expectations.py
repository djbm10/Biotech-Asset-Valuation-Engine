"""Tests for implied_expectations and market_vs_model modules."""

from __future__ import annotations

from datetime import date

import pytest

from bve.analysis.implied_expectations import (
    ConsensusEstimate,
    ImpliedExpectations,
    ImpliedExpectationsRecord,
    MarketSnapshot,
)
from bve.analysis.market_vs_model import (
    LearningRecord,
    MarketVsModel,
    MarketVsModelComparison,
)


# ---------------------------------------------------------------------------
# MarketSnapshot
# ---------------------------------------------------------------------------

def test_market_snapshot_basic():
    snap = MarketSnapshot(
        asset_id="A1",
        ticker="TICK",
        snapshot_date=date(2025, 1, 1),
        market_cap_millions=500.0,
        ev_millions=450.0,
        share_price=10.0,
        shares_outstanding_millions=50.0,
        cash_millions=80.0,
        debt_millions=30.0,
    )
    assert snap.asset_id == "A1"
    assert snap.ev_millions == 450.0


# ---------------------------------------------------------------------------
# ConsensusEstimate
# ---------------------------------------------------------------------------

def test_consensus_estimate_basic():
    est = ConsensusEstimate(
        asset_id="A1",
        ticker="TICK",
        estimate_date=date(2025, 1, 1),
        source="StreetAccount",
        model_pos=0.45,
        model_peak_sales_millions=800.0,
        analyst_count=5,
        consensus_rnpv_millions=300.0,
    )
    assert est.model_pos == 0.45
    assert est.analyst_count == 5


def test_consensus_estimate_pos_bounds():
    with pytest.raises(Exception):
        ConsensusEstimate(
            asset_id="A1",
            ticker="TICK",
            estimate_date=date(2025, 1, 1),
            source="X",
            model_pos=1.5,  # out of range
            model_peak_sales_millions=100.0,
            analyst_count=1,
            consensus_rnpv_millions=50.0,
        )


# ---------------------------------------------------------------------------
# ImpliedExpectationsRecord
# ---------------------------------------------------------------------------

def _make_record() -> ImpliedExpectationsRecord:
    return ImpliedExpectationsRecord(
        asset_id="A1",
        ticker="TICK",
        snapshot_date=date(2025, 6, 1),
        implied_pos=0.60,
        implied_peak_sales_millions=1200.0,
        implied_dilution_pct=0.15,
        implied_timeline_years=3.5,
        model_pos=0.45,
        model_peak_sales_millions=800.0,
        model_rnpv_millions=350.0,
        current_ev_millions=450.0,
        upside_pct=30.0,
        downside_pct=-20.0,
        valuation_gap_millions=100.0,
    )


def test_implied_expectations_record_defaults():
    rec = _make_record()
    assert rec.methodology == "nav_backsolve"
    assert rec.valuation_gap_millions == 100.0


# ---------------------------------------------------------------------------
# ImpliedExpectations container
# ---------------------------------------------------------------------------

def test_implied_expectations_container():
    rec = _make_record()
    ie = ImpliedExpectations(asset_id="A1", records=[rec], latest=rec)
    assert len(ie.records) == 1
    assert ie.latest is not None
    assert ie.latest.implied_pos == 0.60


def test_implied_expectations_empty():
    ie = ImpliedExpectations(asset_id="A1")
    assert ie.records == []
    assert ie.latest is None


# ---------------------------------------------------------------------------
# MarketVsModelComparison
# ---------------------------------------------------------------------------

def test_market_vs_model_comparison_basic():
    comp = MarketVsModelComparison(
        asset_id="A1",
        ticker="TICK",
        comparison_date=date(2025, 6, 1),
        model_pos=0.45,
        implied_pos=0.60,
        pos_gap=0.15,
        model_peak_sales_millions=800.0,
        implied_peak_sales_millions=1200.0,
        peak_sales_gap_millions=400.0,
        model_ev_millions=350.0,
        market_ev_millions=450.0,
        ev_gap_millions=100.0,
        ev_gap_pct=28.6,
        pos_direction="underpriced",
        summary="Model is more pessimistic than market.",
    )
    assert comp.pos_gap == 0.15
    assert comp.pos_direction == "underpriced"


# ---------------------------------------------------------------------------
# LearningRecord
# ---------------------------------------------------------------------------

def test_learning_record_basic():
    lr = LearningRecord(
        asset_id="A1",
        comparison_date=date(2025, 1, 1),
        catalyst_date=date(2025, 3, 1),
        realized_outcome="positive",
        predicted_gap_direction="underpriced",
        was_correct=True,
        return_30d=12.5,
        return_90d=22.0,
    )
    assert lr.was_correct is True


# ---------------------------------------------------------------------------
# MarketVsModel container
# ---------------------------------------------------------------------------

def test_market_vs_model_container_empty():
    mvm = MarketVsModel(asset_id="A1")
    assert mvm.comparisons == []
    assert mvm.learning_records == []
