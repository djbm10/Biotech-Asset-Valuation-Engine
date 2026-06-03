"""Tests for signal_fusion and unified_recommendation modules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bve.analysis.signal_fusion import AssetSignalBundle, FusedSignalCard, SignalFusionEngine
from bve.analysis.unified_recommendation import UnifiedRecommendationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _minimal_bundle(**kwargs) -> AssetSignalBundle:
    defaults = {
        "asset_id": "asset-test",
        "ticker": "TEST",
        "as_of": _now(),
    }
    defaults.update(kwargs)
    return AssetSignalBundle(**defaults)


def _full_bundle() -> AssetSignalBundle:
    return AssetSignalBundle(
        asset_id="asset-full",
        ticker="FULL",
        as_of=_now(),
        model_pos=0.65,
        implied_pos=0.45,
        pos_gap=0.20,
        model_peak_sales_millions=1200.0,
        implied_peak_sales_millions=900.0,
        peak_sales_gap_millions=300.0,
        model_ev_millions=800.0,
        market_ev_millions=600.0,
        ev_gap_pct=0.333,
        thesis_confidence=0.75,
        thesis_conviction="high",
        active_kill_criteria_count=0,
        best_catalyst_expected_return_pct=35.0,
        best_catalyst_downside_pct=-20.0,
        best_catalyst_setup_score=0.72,
        days_to_next_catalyst=14,
        financing_risk_score=0.30,
        months_runway=24.0,
        pre_catalyst_financing_probability=0.15,
        science_score=0.80,
        design_score=0.70,
        safety_risk_tier="low",
        competition_risk_score=0.40,
        competitor_count=3,
        current_position_pct=0.05,
        ta_remaining_budget_pct=0.60,
        liquidity_score=0.85,
    )


# ---------------------------------------------------------------------------
# AssetSignalBundle tests
# ---------------------------------------------------------------------------


def test_asset_signal_bundle_minimal_instantiation() -> None:
    bundle = _minimal_bundle()
    assert bundle.asset_id == "asset-test"
    assert bundle.ticker == "TEST"
    assert bundle.model_pos is None
    assert bundle.active_kill_criteria_count == 0
    assert bundle.current_position_pct == 0.0


def test_asset_signal_bundle_all_fields() -> None:
    bundle = _full_bundle()
    assert bundle.model_pos == 0.65
    assert bundle.ev_gap_pct == pytest.approx(0.333, abs=0.001)
    assert bundle.science_score == 0.80
    assert bundle.competitor_count == 3
    assert bundle.thesis_conviction == "high"


# ---------------------------------------------------------------------------
# SignalFusionEngine — basic fuse
# ---------------------------------------------------------------------------


def test_fuse_minimal_bundle_returns_valid_card() -> None:
    engine = SignalFusionEngine()
    card = engine.fuse(_minimal_bundle())
    assert isinstance(card, FusedSignalCard)
    assert card.asset_id == "asset-test"
    assert card.ticker == "TEST"
    assert card.action in {"add", "hold", "watchlist", "avoid"}
    assert card.conviction in {"high", "medium", "low"}


def test_fuse_positive_ev_gap_increases_valuation_score() -> None:
    engine = SignalFusionEngine()
    card = engine.fuse(_minimal_bundle(ev_gap_pct=0.3))
    assert card.valuation_score > 0.5


def test_fuse_negative_ev_gap_decreases_valuation_score() -> None:
    engine = SignalFusionEngine()
    card = engine.fuse(_minimal_bundle(ev_gap_pct=-0.3))
    assert card.valuation_score < 0.5


def test_fuse_composite_score_in_unit_interval() -> None:
    engine = SignalFusionEngine()
    for bundle in [_minimal_bundle(), _full_bundle()]:
        card = engine.fuse(bundle)
        assert 0.0 <= card.composite_score <= 1.0


def test_fuse_high_composite_yields_add_action() -> None:
    engine = SignalFusionEngine()
    # Construct a very favourable bundle
    bundle = _minimal_bundle(
        ev_gap_pct=0.8,
        best_catalyst_setup_score=0.95,
        financing_risk_score=0.05,
        competition_risk_score=0.05,
        science_score=0.95,
        design_score=0.90,
        ta_remaining_budget_pct=0.90,
        liquidity_score=0.90,
    )
    card = engine.fuse(bundle)
    assert card.action == "add"


def test_fuse_low_composite_yields_avoid_or_watchlist_action() -> None:
    engine = SignalFusionEngine()
    bundle = _minimal_bundle(
        ev_gap_pct=-0.8,
        best_catalyst_setup_score=0.05,
        financing_risk_score=0.95,
        competition_risk_score=0.95,
        science_score=0.05,
        design_score=0.05,
    )
    card = engine.fuse(bundle)
    assert card.action in {"avoid", "watchlist"}


def test_fuse_high_financing_risk_reduces_composite() -> None:
    engine = SignalFusionEngine()
    low_risk = engine.fuse(_minimal_bundle(financing_risk_score=0.1))
    high_risk = engine.fuse(_minimal_bundle(financing_risk_score=0.95))
    assert high_risk.composite_score < low_risk.composite_score


def test_fuse_high_science_score_increases_composite() -> None:
    engine = SignalFusionEngine()
    low_sci = engine.fuse(_minimal_bundle(science_score=0.1))
    high_sci = engine.fuse(_minimal_bundle(science_score=0.9))
    assert high_sci.composite_score > low_sci.composite_score


def test_fuse_high_catalyst_setup_increases_composite() -> None:
    engine = SignalFusionEngine()
    low_cat = engine.fuse(_minimal_bundle(best_catalyst_setup_score=0.05))
    high_cat = engine.fuse(_minimal_bundle(best_catalyst_setup_score=0.80))
    assert high_cat.composite_score > low_cat.composite_score


def test_fuse_high_composite_yields_high_conviction() -> None:
    engine = SignalFusionEngine()
    bundle = _minimal_bundle(
        ev_gap_pct=0.9,
        best_catalyst_setup_score=0.95,
        financing_risk_score=0.02,
        competition_risk_score=0.02,
        science_score=0.95,
        ta_remaining_budget_pct=0.95,
        liquidity_score=0.95,
    )
    card = engine.fuse(bundle)
    assert card.conviction == "high"


def test_fuse_rationale_is_non_empty_string() -> None:
    engine = SignalFusionEngine()
    card = engine.fuse(_minimal_bundle())
    assert isinstance(card.rationale, str)
    assert len(card.rationale) > 0


def test_fuse_top_positives_and_risks_are_lists() -> None:
    engine = SignalFusionEngine()
    card = engine.fuse(_full_bundle())
    assert isinstance(card.top_positives, list)
    assert isinstance(card.top_risks, list)


# ---------------------------------------------------------------------------
# SignalFusionEngine — fuse_batch
# ---------------------------------------------------------------------------


def test_fuse_batch_returns_sorted_by_composite_descending() -> None:
    engine = SignalFusionEngine()
    bundles = [
        _minimal_bundle(asset_id="low", ticker="LOW", ev_gap_pct=-0.5, best_catalyst_setup_score=0.1),
        _minimal_bundle(asset_id="high", ticker="HIGH", ev_gap_pct=0.5, best_catalyst_setup_score=0.9),
        _minimal_bundle(asset_id="mid", ticker="MID"),
    ]
    cards = engine.fuse_batch(bundles)
    scores = [c.composite_score for c in cards]
    assert scores == sorted(scores, reverse=True)


def test_fuse_batch_two_bundles_correct_ordering() -> None:
    engine = SignalFusionEngine()
    bad = _minimal_bundle(asset_id="bad", ticker="BAD", ev_gap_pct=-0.8, financing_risk_score=0.95)
    good = _minimal_bundle(asset_id="good", ticker="GOOD", ev_gap_pct=0.8, financing_risk_score=0.05)
    cards = engine.fuse_batch([bad, good])
    assert cards[0].asset_id == "good"
    assert cards[1].asset_id == "bad"


# ---------------------------------------------------------------------------
# UnifiedRecommendationEngine — no store
# ---------------------------------------------------------------------------


def test_unified_recommend_no_store_with_overrides_returns_card() -> None:
    engine = UnifiedRecommendationEngine(store=None)
    card = engine.recommend(
        "asset-abc",
        "ABC",
        model_ev_millions=500.0,
        market_ev_millions=400.0,
        science_score_override=0.75,
        financing_risk_override=0.30,
        catalyst_setup_score=0.65,
    )
    assert isinstance(card, FusedSignalCard)


def test_unified_recommend_returns_fused_signal_card() -> None:
    engine = UnifiedRecommendationEngine()
    card = engine.recommend("asset-xyz", "XYZ")
    assert isinstance(card, FusedSignalCard)
    assert card.asset_id == "asset-xyz"
    assert card.ticker == "XYZ"


def test_unified_recommend_positive_ev_gap_when_model_exceeds_market() -> None:
    engine = UnifiedRecommendationEngine()
    card = engine.recommend(
        "asset-ev",
        "EV",
        model_ev_millions=1000.0,
        market_ev_millions=600.0,
    )
    assert card.bundle.ev_gap_pct is not None
    assert card.bundle.ev_gap_pct > 0.0


def test_unified_recommend_universe_returns_sorted_list() -> None:
    engine = UnifiedRecommendationEngine()
    assets = [
        {"asset_id": "a1", "ticker": "A1", "model_ev_millions": 200.0, "market_ev_millions": 500.0},
        {"asset_id": "a2", "ticker": "A2", "model_ev_millions": 800.0, "market_ev_millions": 300.0},
        {"asset_id": "a3", "ticker": "A3"},
    ]
    cards = engine.recommend_universe(assets)
    assert len(cards) == 3
    scores = [c.composite_score for c in cards]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# FusedSignalCard — field access
# ---------------------------------------------------------------------------


def test_fused_signal_card_fields_accessible() -> None:
    engine = SignalFusionEngine()
    card = engine.fuse(_full_bundle())
    # All named fields must be accessible without error
    _ = card.asset_id
    _ = card.ticker
    _ = card.fused_at
    _ = card.bundle
    _ = card.valuation_score
    _ = card.catalyst_score
    _ = card.risk_score
    _ = card.science_score
    _ = card.portfolio_score
    _ = card.composite_score
    _ = card.action
    _ = card.conviction
    _ = card.rationale
    _ = card.top_positives
    _ = card.top_risks


# ---------------------------------------------------------------------------
# Weight sum check
# ---------------------------------------------------------------------------


def test_equal_sub_scores_produce_weighted_average() -> None:
    """When all sub-scores equal S, composite == S (weights sum to 1)."""
    engine = SignalFusionEngine()
    # Force all sub-components to produce 0.7
    # ev_gap_pct=0.1 → val_score = clamp(0.5 + 0.1*2) = 0.7
    # best_catalyst_setup_score=0.7 → cat_score = 0.7
    # financing_risk_score=0.3, competition_risk_score=0.3 → risk = (0.7+0.7)/2 = 0.7
    # science_score=0.7, design_score=0.7 → science = 0.7
    # ta_remaining_budget_pct=0.7, liquidity_score=0.7 → portfolio = 0.7
    bundle = _minimal_bundle(
        ev_gap_pct=0.1,
        best_catalyst_setup_score=0.7,
        financing_risk_score=0.3,
        competition_risk_score=0.3,
        science_score=0.7,
        design_score=0.7,
        ta_remaining_budget_pct=0.7,
        liquidity_score=0.7,
    )
    card = engine.fuse(bundle)
    # Each sub-score == 0.7; composite should equal 0.7
    assert card.composite_score == pytest.approx(0.7, abs=1e-6)
