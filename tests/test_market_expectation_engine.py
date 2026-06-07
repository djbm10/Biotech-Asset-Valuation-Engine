from __future__ import annotations

from bve.intelligence.market_expectations import (
    MarketExpectationComparisonValue,
    MarketExpectationEngine,
    compute_implied_peak_sales,
)


def test_phase_i_can_backsolve_implied_peak_sales() -> None:
    implied = compute_implied_peak_sales(
        market_cap_millions=600.0,
        cash_estimate_millions=100.0,
        model_pos=0.50,
        patent_life_years=10,
        discount_rate=0.0,
        margin_rate=0.40,
    )
    assert implied == 250.0


def test_phase_i_builds_primary_market_expectation_card() -> None:
    engine = MarketExpectationEngine()
    comparison = engine.build_comparison(
        asset_id="asset-rly2608",
        ticker="RLAY",
        model_pos=0.55,
        model_peak_sales_millions=1200.0,
        market_cap_millions=700.0,
        cash_estimate_millions=200.0,
        financing_adjusted_intrinsic_value_millions=1100.0,
        model_dilution_pct=0.18,
        implied_dilution_pct=0.10,
        consensus_valuation_range_low_millions=650.0,
        consensus_valuation_range_high_millions=900.0,
        patent_life_years=10,
        discount_rate=0.0,
        margin_rate=0.40,
    )

    value = MarketExpectationComparisonValue.model_validate(comparison.output.value)
    assert value.model_pos == 0.55
    assert value.implied_pos is not None
    assert value.pos_delta is not None
    assert value.implied_peak_sales_millions is not None
    assert value.peak_sales_delta_millions is not None
    assert value.financing_adjusted_intrinsic_value_millions == 1100.0
    assert value.current_ev_millions == 500.0
    assert value.upside_downside_pct == 1.2
    assert value.optionality_not_reflected_millions == 200.0
    assert comparison.output.confidence > 0.8
    assert "variant_view_engine" in comparison.output.downstream_dependencies


def test_phase_i_handles_missing_inputs_gracefully() -> None:
    engine = MarketExpectationEngine()
    comparison = engine.build_comparison(
        asset_id="asset-x",
        ticker="TEST",
        model_pos=None,
        model_peak_sales_millions=None,
        market_cap_millions=None,
        financing_adjusted_intrinsic_value_millions=None,
    )
    value = MarketExpectationComparisonValue.model_validate(comparison.output.value)
    assert value.implied_pos is None
    assert value.implied_peak_sales_millions is None
    assert value.current_ev_millions is None
    assert comparison.output.confidence == 0.55
