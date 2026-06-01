"""Tests for the deal premium estimation engine (Block 3A)."""
from __future__ import annotations

from pathlib import Path

import pytest

from bve.analysis.deal_premium import (
    DealPremiumEngine,
    DealPremiumEstimate,
    _phase_score,
    _ta_specificity,
)

DEALS_PATH = Path("research/mna/comparable_deals.yaml")


@pytest.fixture(scope="module")
def engine() -> DealPremiumEngine:
    return DealPremiumEngine.from_file(DEALS_PATH)


# ── Phase/TA helpers ─────────────────────────────────────────────────────────

def test_phase_score_ordering() -> None:
    assert _phase_score("phase_1") < _phase_score("phase_2")
    assert _phase_score("phase_2") < _phase_score("phase_3")
    assert _phase_score("phase_3") < _phase_score("approved")


def test_ta_specificity_rare_disease_highest() -> None:
    assert _ta_specificity("rare_disease") > _ta_specificity("oncology")
    assert _ta_specificity("ophthalmology") > _ta_specificity("metabolic")


# ── Engine loading ───────────────────────────────────────────────────────────

def test_engine_loads_deals(engine: DealPremiumEngine) -> None:
    assert len(engine._deals) >= 80


def test_engine_fits_regression(engine: DealPremiumEngine) -> None:
    b0, b1, b2, b3 = engine._coeffs
    # Intercept should produce a reasonable baseline EV/peak-sales
    import math
    baseline = math.exp(b0)
    assert 0.5 < baseline < 10.0


def test_phase_summary_keys(engine: DealPremiumEngine) -> None:
    summary = engine.phase_summary()
    assert "phase_2" in summary
    assert "phase_3" in summary
    assert "approved" in summary


def test_phase_summary_approved_median_above_phase2(engine: DealPremiumEngine) -> None:
    """Approved assets command higher EV/peak-sales than early-phase assets."""
    summary = engine.phase_summary()
    assert summary["approved"]["median"] > summary["phase_2"]["median"]


# ── Estimate correctness ─────────────────────────────────────────────────────

def test_estimate_returns_valid_result(engine: DealPremiumEngine) -> None:
    est = engine.estimate(
        phase="phase_2",
        therapeutic_area="oncology",
        acquirer_fit_score=0.7,
    )
    assert isinstance(est, DealPremiumEstimate)
    assert est.ev_to_peak_sales_p25 > 0
    assert est.ev_to_peak_sales_p25 <= est.ev_to_peak_sales_median
    assert est.ev_to_peak_sales_median <= est.ev_to_peak_sales_p75
    assert est.ev_to_peak_sales_regression > 0
    assert est.ev_to_peak_sales_blended > 0


def test_estimate_with_peak_sales_produces_implied_ev(engine: DealPremiumEngine) -> None:
    est = engine.estimate(
        phase="phase_2",
        therapeutic_area="immunology",
        acquirer_fit_score=0.5,
        peak_sales_millions=1000,
    )
    assert est.implied_ev_blended_millions is not None
    assert est.implied_ev_blended_millions > 0
    assert est.implied_ev_p25_millions <= est.implied_ev_blended_millions
    assert est.implied_ev_blended_millions <= est.implied_ev_p75_millions


def test_estimate_without_peak_sales_no_implied_ev(engine: DealPremiumEngine) -> None:
    est = engine.estimate(
        phase="phase_3",
        therapeutic_area="cardiovascular",
        acquirer_fit_score=0.6,
    )
    assert est.implied_ev_blended_millions is None


def test_higher_fit_score_higher_regression(engine: DealPremiumEngine) -> None:
    """Higher acquirer-fit score → higher regression estimate (strategic urgency premium)."""
    est_low = engine.estimate(phase="phase_2", therapeutic_area="oncology", acquirer_fit_score=0.1)
    est_high = engine.estimate(phase="phase_2", therapeutic_area="oncology", acquirer_fit_score=0.9)
    assert est_high.ev_to_peak_sales_regression >= est_low.ev_to_peak_sales_regression


def test_approved_assets_higher_than_phase2(engine: DealPremiumEngine) -> None:
    """Approved assets should have higher median EV/peak-sales than phase_2."""
    est_approved = engine.estimate(phase="approved", therapeutic_area="oncology", acquirer_fit_score=0.5)
    est_phase2 = engine.estimate(phase="phase_2", therapeutic_area="oncology", acquirer_fit_score=0.5)
    assert est_approved.ev_to_peak_sales_median > est_phase2.ev_to_peak_sales_median


# ── Alpine/Vertex validation ─────────────────────────────────────────────────

def test_alpine_vertex_deal_in_upper_half(engine: DealPremiumEngine) -> None:
    """
    Alpine actual deal: $4,900M EV, ~$2,000M peak sales = 2.45x EV/peak-sales.
    This was a strategic premium — should be above the median of phase_2 immunology comps.
    """
    est = engine.estimate(
        phase="phase_2",
        therapeutic_area="immunology",
        acquirer_fit_score=0.975,
        peak_sales_millions=2000,
    )
    actual_ev_ps = 2.45  # Vertex paid $4.9B for ~$2B peak-sales
    # Actual should be above the median (i.e. this was a strategic premium deal)
    assert actual_ev_ps > est.ev_to_peak_sales_median, (
        f"Alpine deal (2.45x) should be above median ({est.ev_to_peak_sales_median:.2f}x)"
    )
    # Actual should be within the P25–P75 range or above it (franchise premium)
    assert actual_ev_ps >= est.ev_to_peak_sales_p25, (
        f"Alpine deal (2.45x) should be at or above P25 ({est.ev_to_peak_sales_p25:.2f}x)"
    )


def test_premium_tier_field_is_valid(engine: DealPremiumEngine) -> None:
    for phase in ["phase_1", "phase_2", "phase_3", "approved"]:
        est = engine.estimate(phase=phase, therapeutic_area="oncology", acquirer_fit_score=0.5)
        assert est.premium_tier in {"strategic_premium", "market_rate", "below_market"}


def test_comparables_list_populated(engine: DealPremiumEngine) -> None:
    est = engine.estimate(phase="phase_2", therapeutic_area="immunology", acquirer_fit_score=0.6)
    assert len(est.comparables) > 0
    assert est.n_comparables > 0
