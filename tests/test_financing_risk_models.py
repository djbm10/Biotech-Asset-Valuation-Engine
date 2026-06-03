"""Tests for financing_risk, dilution_model, and runway_forecast modules."""

from __future__ import annotations

from datetime import date

import pytest

from bve.models.dilution_model import DilutionModel, DilutionScenario
from bve.models.financing_risk import (
    FinancingRisk,
    FinancingRiskAssessment,
    FinancingScenario,
)
from bve.models.runway_forecast import BurnScenario, RunwayForecast


# ---------------------------------------------------------------------------
# FinancingScenario
# ---------------------------------------------------------------------------

def test_financing_scenario_basic():
    sc = FinancingScenario(
        label="follow_on",
        probability=0.50,
        raise_size_millions=75.0,
        dilution_pct=0.12,
        timing_months=6.0,
    )
    assert sc.label == "follow_on"
    assert sc.dilution_pct == 0.12


def test_financing_scenario_defaults():
    sc = FinancingScenario(label="no_raise", probability=0.30)
    assert sc.raise_size_millions == 0.0
    assert sc.timing_months == 0.0


def test_financing_scenario_prob_bounds():
    with pytest.raises(Exception):
        FinancingScenario(label="x", probability=1.5)


# ---------------------------------------------------------------------------
# FinancingRiskAssessment
# ---------------------------------------------------------------------------

def _make_assessment() -> FinancingRiskAssessment:
    sc = FinancingScenario(label="follow_on", probability=0.60, raise_size_millions=60.0, dilution_pct=0.10)
    return FinancingRiskAssessment(
        asset_id="A1",
        company_id="C1",
        assessment_date=date(2025, 6, 1),
        risk_score=0.55,
        risk_tier="medium",
        scenarios=[sc],
        primary_scenario="follow_on",
        distress_probability=0.10,
        commentary="Adequate runway to next catalyst.",
    )


def test_financing_risk_assessment_basic():
    fa = _make_assessment()
    assert fa.risk_tier == "medium"
    assert len(fa.scenarios) == 1


def test_financing_risk_container():
    fa = _make_assessment()
    risk = FinancingRisk(asset_id="A1", company_id="C1", current_assessment=fa)
    assert risk.current_assessment is not None
    assert risk.history == []


def test_financing_risk_empty():
    risk = FinancingRisk(asset_id="A1", company_id="C1")
    assert risk.current_assessment is None


# ---------------------------------------------------------------------------
# DilutionScenario
# ---------------------------------------------------------------------------

def test_dilution_scenario_basic():
    sc = DilutionScenario(
        label="10% ATM",
        share_count_before=100.0,
        share_count_after=110.0,
        dilution_pct=0.10,
        offering_price=8.0,
        gross_proceeds_millions=80.0,
        discount_to_market_pct=0.05,
    )
    assert sc.dilution_pct == 0.10
    assert sc.offering_price == 8.0


def test_dilution_model_basic():
    sc = DilutionScenario(
        label="base",
        share_count_before=100.0,
        share_count_after=115.0,
        dilution_pct=0.15,
    )
    dm = DilutionModel(
        company_id="C1",
        current_shares_millions=100.0,
        current_market_cap_millions=500.0,
        scenarios=[sc],
        expected_dilution_pct_low=0.05,
        expected_dilution_pct_base=0.15,
        expected_dilution_pct_high=0.30,
    )
    assert dm.expected_dilution_pct_base == 0.15
    assert dm.total_authorized_shares_millions is None


# ---------------------------------------------------------------------------
# BurnScenario / RunwayForecast
# ---------------------------------------------------------------------------

def test_burn_scenario_basic():
    bs = BurnScenario(
        label="base",
        quarterly_burn_millions=15.0,
        annual_burn_millions=60.0,
    )
    assert bs.burn_rate_change_pct == 0.0


def test_runway_forecast_basic():
    bull = BurnScenario(label="bull", quarterly_burn_millions=10.0, annual_burn_millions=40.0)
    base = BurnScenario(label="base", quarterly_burn_millions=15.0, annual_burn_millions=60.0)
    bear = BurnScenario(label="bear", quarterly_burn_millions=20.0, annual_burn_millions=80.0)

    rf = RunwayForecast(
        company_id="C1",
        forecast_date=date(2025, 6, 1),
        cash_millions=150.0,
        debt_millions=0.0,
        net_cash_millions=150.0,
        burn_scenarios=[bull, base, bear],
        runway_months_bull=45.0,
        runway_months_base=30.0,
        runway_months_bear=22.5,
        next_catalyst_date=date(2026, 3, 1),
        capital_needed_to_next_catalyst_millions=0.0,
        capital_needed_to_approval_millions=120.0,
        cash_adequate_for_next_catalyst=True,
    )
    assert rf.cash_adequate_for_next_catalyst is True
    assert rf.runway_months_base == 30.0


def test_runway_forecast_no_next_catalyst():
    rf = RunwayForecast(
        company_id="C1",
        forecast_date=date(2025, 6, 1),
        cash_millions=50.0,
        debt_millions=10.0,
        net_cash_millions=40.0,
        burn_scenarios=[],
        runway_months_bull=0.0,
        runway_months_base=0.0,
        runway_months_bear=0.0,
        capital_needed_to_next_catalyst_millions=0.0,
        capital_needed_to_approval_millions=0.0,
        cash_adequate_for_next_catalyst=False,
    )
    assert rf.next_catalyst_date is None
