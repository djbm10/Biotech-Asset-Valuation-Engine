"""Tests for Phase 3 Trading Layer modules."""
from __future__ import annotations

from datetime import date

import pytest

from bve.trading.instrument_selector import (
    Instrument,
    InstrumentSelectionInput,
    InstrumentSelector,
)
from bve.trading.position_sizer import (
    PositionSizerInput,
    PositionSizer,
)
from bve.trading.exposure_decomposer import (
    ExposureBreakdown,
    ExposureDecomposer,
    HoldingRecord,
)
from bve.trading.trade_signal import (
    TradeSignalBuilder,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_instrument_input(**kwargs) -> InstrumentSelectionInput:
    defaults = dict(
        asset_id="asset-001",
        asymmetry_score=0.30,
        ev_gap_direction="underpriced",
    )
    defaults.update(kwargs)
    return InstrumentSelectionInput(**defaults)


def _make_sizer_input(**kwargs) -> PositionSizerInput:
    defaults = dict(
        asset_id="asset-001",
        asymmetry_score=0.50,
        conviction=0.80,
        portfolio_nav=10_000_000.0,
    )
    defaults.update(kwargs)
    return PositionSizerInput(**defaults)


def _make_holding(**kwargs) -> HoldingRecord:
    defaults = dict(
        asset_id="asset-001",
        ticker="TICK",
        position_pct=0.05,
        therapeutic_area="oncology",
        phase="2",
        has_binary_catalyst=False,
    )
    defaults.update(kwargs)
    return HoldingRecord(**defaults)


# =============================================================================
# InstrumentSelector — 20 tests
# =============================================================================

class TestInstrumentSelectorDistress:
    def test_distress_returns_no_trade(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(financing_risk_tier="distress", asymmetry_score=0.90)
        result = sel.select(inp)
        assert result.instrument == Instrument.NO_TRADE

    def test_distress_overrides_bullish_signal(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            financing_risk_tier="distress",
            asymmetry_score=0.95,
            days_to_catalyst=5,
            iv_richness="cheap",
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.NO_TRADE

    def test_distress_has_high_confidence(self):
        result = InstrumentSelector().select(_make_instrument_input(financing_risk_tier="distress"))
        assert result.confidence >= 0.85

    def test_distress_rationale_mentions_financing(self):
        result = InstrumentSelector().select(_make_instrument_input(financing_risk_tier="distress"))
        assert "financing" in result.rationale.lower() or "distress" in result.rationale.lower()


class TestInstrumentSelectorFairlyPriced:
    def test_fairly_priced_low_asymmetry_no_trade(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(ev_gap_direction="fairly_priced", asymmetry_score=0.05)
        result = sel.select(inp)
        assert result.instrument == Instrument.NO_TRADE

    def test_fairly_priced_high_asymmetry_not_no_trade(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(ev_gap_direction="fairly_priced", asymmetry_score=0.50)
        result = sel.select(inp)
        assert result.instrument != Instrument.NO_TRADE

    def test_fairly_priced_negative_asymmetry_above_threshold_not_no_trade(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(ev_gap_direction="fairly_priced", asymmetry_score=-0.25)
        result = sel.select(inp)
        assert result.instrument != Instrument.NO_TRADE

    def test_fairly_priced_exactly_at_threshold_is_no_trade(self):
        sel = InstrumentSelector()
        # |0.099| < 0.10 → no trade
        inp = _make_instrument_input(ev_gap_direction="fairly_priced", asymmetry_score=0.099)
        result = sel.select(inp)
        assert result.instrument == Instrument.NO_TRADE


class TestInstrumentSelectorNearCatalyst:
    def test_near_catalyst_rich_iv_bullish_returns_equity(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=0.40,
            days_to_catalyst=10,
            iv_richness="rich",
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.EQUITY

    def test_near_catalyst_rich_iv_bearish_returns_put(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=-0.40,
            days_to_catalyst=10,
            iv_richness="rich",
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.PUT

    def test_near_catalyst_cheap_iv_high_abs_score_returns_straddle(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=0.45,
            days_to_catalyst=15,
            iv_richness="cheap",
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.STRADDLE

    def test_near_catalyst_none_iv_high_abs_score_returns_straddle(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=-0.50,
            days_to_catalyst=20,
            iv_richness=None,
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.STRADDLE

    def test_near_catalyst_cheap_iv_bullish_moderate_returns_call(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=0.25,
            days_to_catalyst=20,
            iv_richness="cheap",
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.CALL

    def test_near_catalyst_cheap_iv_bearish_moderate_returns_put(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=-0.25,
            days_to_catalyst=28,
            iv_richness="cheap",
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.PUT

    def test_near_catalyst_weak_signal_returns_equity(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=0.10,
            days_to_catalyst=25,
            iv_richness="cheap",
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.EQUITY

    def test_catalyst_exactly_30_days_triggers_near_catalyst_path(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=0.25,
            days_to_catalyst=30,
            iv_richness="cheap",
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.CALL


class TestInstrumentSelectorNoCatalyst:
    def test_no_catalyst_bullish_returns_equity(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(asymmetry_score=0.20, days_to_catalyst=None)
        result = sel.select(inp)
        assert result.instrument == Instrument.EQUITY

    def test_no_catalyst_bearish_returns_put(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(asymmetry_score=-0.20, days_to_catalyst=None)
        result = sel.select(inp)
        assert result.instrument == Instrument.PUT

    def test_no_catalyst_weak_signal_returns_no_trade(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(asymmetry_score=0.05, days_to_catalyst=None)
        result = sel.select(inp)
        assert result.instrument == Instrument.NO_TRADE

    def test_model_move_exceeds_implied_bullish_returns_call(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=0.10,
            days_to_catalyst=None,
            model_expected_move_pct=0.40,
            implied_move_pct=0.25,
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.CALL

    def test_model_move_exceeds_implied_bearish_returns_put(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(
            asymmetry_score=-0.10,
            days_to_catalyst=None,
            model_expected_move_pct=0.40,
            implied_move_pct=0.25,
        )
        result = sel.select(inp)
        assert result.instrument == Instrument.PUT

    def test_result_has_asset_id(self):
        sel = InstrumentSelector()
        inp = _make_instrument_input(asset_id="my-asset", asymmetry_score=0.30, days_to_catalyst=None)
        result = sel.select(inp)
        assert result.asset_id == "my-asset"

    def test_confidence_in_valid_range(self):
        sel = InstrumentSelector()
        for score in [-0.80, -0.30, 0.0, 0.30, 0.80]:
            inp = _make_instrument_input(asymmetry_score=score)
            result = sel.select(inp)
            assert 0.0 <= result.confidence <= 1.0


# =============================================================================
# PositionSizer — 15 tests
# =============================================================================

class TestPositionSizerBaseFormula:
    def test_base_formula(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(asymmetry_score=1.0, conviction=1.0)
        result = sizer.size(inp)
        # base = 1.0 * 1.0 * 0.10 = 0.10, but capped at 0.08
        assert result.target_position_pct == pytest.approx(0.08, abs=1e-6)
        assert result.capped_by == "max_single_position_pct"

    def test_base_formula_uncapped(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(asymmetry_score=0.50, conviction=0.60)
        result = sizer.size(inp)
        expected = 0.50 * 0.60 * 0.10  # = 0.03
        assert result.target_position_pct == pytest.approx(expected, abs=1e-6)
        assert result.capped_by is None

    def test_incremental_equals_target_minus_current(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(asymmetry_score=0.50, conviction=0.80, current_position_pct=0.02)
        result = sizer.size(inp)
        expected_incremental = result.target_position_pct - 0.02
        assert result.incremental_position_pct == pytest.approx(expected_incremental, abs=1e-6)

    def test_position_dollars_matches_incremental(self):
        sizer = PositionSizer()
        nav = 5_000_000.0
        inp = _make_sizer_input(portfolio_nav=nav, asymmetry_score=0.40, conviction=0.70)
        result = sizer.size(inp)
        expected_dollars = result.incremental_position_pct * nav
        assert result.position_dollars == pytest.approx(expected_dollars, abs=0.01)

    def test_negative_asymmetry_gives_zero_target(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(asymmetry_score=-0.50, conviction=0.80, current_position_pct=0.0)
        result = sizer.size(inp)
        # negative base clipped to 0
        assert result.target_position_pct == pytest.approx(0.0, abs=1e-6)


class TestPositionSizerAdjustments:
    def test_financing_high_applies_half_multiplier(self):
        sizer = PositionSizer()
        inp_base = _make_sizer_input(asymmetry_score=0.40, conviction=0.80)
        inp_high = _make_sizer_input(asymmetry_score=0.40, conviction=0.80, financing_risk_tier="high")
        base_result = sizer.size(inp_base)
        high_result = sizer.size(inp_high)
        assert high_result.target_position_pct == pytest.approx(
            base_result.target_position_pct * 0.50, abs=1e-6
        )
        assert any("high" in adj.lower() for adj in high_result.risk_adjustments)

    def test_financing_distress_applies_tenth_multiplier(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(asymmetry_score=0.80, conviction=1.0, financing_risk_tier="distress")
        result = sizer.size(inp)
        expected = min(0.80 * 1.0 * 0.10 * 0.10, 0.08)
        assert result.target_position_pct == pytest.approx(expected, abs=1e-6)
        assert any("distress" in adj.lower() for adj in result.risk_adjustments)

    def test_liquidity_below_2m_applies_half_haircut(self):
        sizer = PositionSizer()
        inp_liq = _make_sizer_input(asymmetry_score=0.40, conviction=0.80, liquidity_adtv_millions=1.0)
        inp_base = _make_sizer_input(asymmetry_score=0.40, conviction=0.80)
        liq_result = sizer.size(inp_liq)
        base_result = sizer.size(inp_base)
        assert liq_result.target_position_pct == pytest.approx(
            base_result.target_position_pct * 0.50, abs=1e-6
        )

    def test_liquidity_between_2m_5m_applies_75pct_haircut(self):
        sizer = PositionSizer()
        inp_liq = _make_sizer_input(asymmetry_score=0.40, conviction=0.80, liquidity_adtv_millions=3.0)
        inp_base = _make_sizer_input(asymmetry_score=0.40, conviction=0.80)
        liq_result = sizer.size(inp_liq)
        base_result = sizer.size(inp_base)
        assert liq_result.target_position_pct == pytest.approx(
            base_result.target_position_pct * 0.75, abs=1e-6
        )

    def test_liquidity_above_5m_no_haircut(self):
        sizer = PositionSizer()
        inp_liq = _make_sizer_input(asymmetry_score=0.40, conviction=0.80, liquidity_adtv_millions=10.0)
        inp_base = _make_sizer_input(asymmetry_score=0.40, conviction=0.80)
        liq_result = sizer.size(inp_liq)
        base_result = sizer.size(inp_base)
        assert liq_result.target_position_pct == pytest.approx(base_result.target_position_pct, abs=1e-6)


class TestPositionSizerHardCaps:
    def test_single_position_cap_binding(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(
            asymmetry_score=1.0, conviction=1.0, max_single_position_pct=0.08
        )
        result = sizer.size(inp)
        assert result.target_position_pct <= 0.08
        assert result.capped_by == "max_single_position_pct"

    def test_sector_headroom_cap_binding(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(
            asymmetry_score=1.0,
            conviction=1.0,
            max_sector_pct=0.30,
            current_sector_pct=0.27,  # only 3% headroom
            current_position_pct=0.0,
        )
        result = sizer.size(inp)
        # Max allowed by sector: 0.0 + (0.30 - 0.27) = 0.03
        assert result.target_position_pct <= 0.03 + 1e-9
        assert result.capped_by == "sector_headroom"

    def test_minimum_threshold_zeroed_out(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(asymmetry_score=0.05, conviction=0.05)
        # base = 0.05 * 0.05 * 0.10 = 0.00025 < 0.005
        result = sizer.size(inp)
        assert result.target_position_pct == pytest.approx(0.0, abs=1e-6)
        assert any("50bps" in adj for adj in result.risk_adjustments)

    def test_negative_incremental_trim(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(
            asymmetry_score=-0.50,
            conviction=0.80,
            current_position_pct=0.05,
        )
        result = sizer.size(inp)
        # target clipped to 0; current=0.05 → incremental = -0.05
        assert result.incremental_position_pct == pytest.approx(-0.05, abs=1e-6)
        assert result.position_dollars < 0

    def test_asset_id_propagated(self):
        sizer = PositionSizer()
        inp = _make_sizer_input(asset_id="xyz-789")
        result = sizer.size(inp)
        assert result.asset_id == "xyz-789"


# =============================================================================
# ExposureDecomposer — 12 tests
# =============================================================================

class TestExposureDecomposer:
    def test_empty_holdings(self):
        decomposer = ExposureDecomposer()
        result = decomposer.decompose([])
        assert result.num_holdings == 0
        assert result.binary_risk_pct == pytest.approx(0.0)
        assert result.concentration_score == pytest.approx(0.0)

    def test_by_ta_aggregation(self):
        decomposer = ExposureDecomposer()
        holdings = [
            _make_holding(asset_id="a1", therapeutic_area="oncology", position_pct=0.05),
            _make_holding(asset_id="a2", therapeutic_area="oncology", position_pct=0.03),
            _make_holding(asset_id="a3", therapeutic_area="rare", position_pct=0.04),
        ]
        result = decomposer.decompose(holdings)
        assert result.by_ta["oncology"] == pytest.approx(0.08)
        assert result.by_ta["rare"] == pytest.approx(0.04)

    def test_by_phase_aggregation(self):
        decomposer = ExposureDecomposer()
        holdings = [
            _make_holding(asset_id="a1", phase="2", position_pct=0.06),
            _make_holding(asset_id="a2", phase="3", position_pct=0.04),
            _make_holding(asset_id="a3", phase="2", position_pct=0.02),
        ]
        result = decomposer.decompose(holdings)
        assert result.by_phase["2"] == pytest.approx(0.08)
        assert result.by_phase["3"] == pytest.approx(0.04)

    def test_binary_risk_pct(self):
        decomposer = ExposureDecomposer()
        holdings = [
            _make_holding(asset_id="a1", position_pct=0.05, has_binary_catalyst=True),
            _make_holding(asset_id="a2", position_pct=0.03, has_binary_catalyst=False),
            _make_holding(asset_id="a3", position_pct=0.04, has_binary_catalyst=True),
        ]
        result = decomposer.decompose(holdings)
        assert result.binary_risk_pct == pytest.approx(0.09)

    def test_near_term_catalyst_pct_exactly_30_days(self):
        decomposer = ExposureDecomposer()
        holdings = [
            _make_holding(asset_id="a1", position_pct=0.05, days_to_next_catalyst=30),
            _make_holding(asset_id="a2", position_pct=0.03, days_to_next_catalyst=31),
            _make_holding(asset_id="a3", position_pct=0.04, days_to_next_catalyst=None),
        ]
        result = decomposer.decompose(holdings)
        assert result.near_term_catalyst_pct == pytest.approx(0.05)

    def test_near_term_catalyst_pct_multiple_within_30(self):
        decomposer = ExposureDecomposer()
        holdings = [
            _make_holding(asset_id="a1", position_pct=0.05, days_to_next_catalyst=10),
            _make_holding(asset_id="a2", position_pct=0.03, days_to_next_catalyst=25),
        ]
        result = decomposer.decompose(holdings)
        assert result.near_term_catalyst_pct == pytest.approx(0.08)

    def test_concentration_score_hhi(self):
        decomposer = ExposureDecomposer()
        # HHI = 0.05^2 + 0.05^2 = 0.005
        holdings = [
            _make_holding(asset_id="a1", position_pct=0.05),
            _make_holding(asset_id="a2", position_pct=0.05),
        ]
        result = decomposer.decompose(holdings)
        assert result.concentration_score == pytest.approx(0.0050, abs=1e-6)

    def test_largest_position_pct(self):
        decomposer = ExposureDecomposer()
        holdings = [
            _make_holding(asset_id="a1", position_pct=0.05),
            _make_holding(asset_id="a2", position_pct=0.10),
            _make_holding(asset_id="a3", position_pct=0.02),
        ]
        result = decomposer.decompose(holdings)
        assert result.largest_position_pct == pytest.approx(0.10)

    def test_num_holdings_count(self):
        decomposer = ExposureDecomposer()
        holdings = [_make_holding(asset_id=f"a{i}") for i in range(7)]
        result = decomposer.decompose(holdings)
        assert result.num_holdings == 7

    def test_concentration_label_well_diversified(self):
        decomposer = ExposureDecomposer()
        breakdown = ExposureBreakdown(concentration_score=0.05)
        assert decomposer.concentration_label(breakdown) == "well-diversified"

    def test_concentration_label_moderate(self):
        decomposer = ExposureDecomposer()
        breakdown = ExposureBreakdown(concentration_score=0.15)
        assert decomposer.concentration_label(breakdown) == "moderate"

    def test_concentration_label_high(self):
        decomposer = ExposureDecomposer()
        breakdown = ExposureBreakdown(concentration_score=0.30)
        assert decomposer.concentration_label(breakdown) == "high"


# =============================================================================
# TradeSignalBuilder — 10 tests
# =============================================================================

def _make_instrument_result(**kwargs):
    from bve.trading.instrument_selector import InstrumentSelectionResult
    defaults = dict(
        asset_id="asset-001",
        instrument=Instrument.EQUITY,
        rationale="Bullish asymmetry; equity preferred.",
        confidence=0.75,
        notes=["some note"],
    )
    defaults.update(kwargs)
    return InstrumentSelectionResult(**defaults)


def _make_size_result(**kwargs):
    from bve.trading.position_sizer import PositionSizeResult
    defaults = dict(
        asset_id="asset-001",
        target_position_pct=0.04,
        incremental_position_pct=0.04,
        position_dollars=400_000.0,
        sizing_rationale="base=0.04",
        risk_adjustments=[],
        capped_by=None,
    )
    defaults.update(kwargs)
    return PositionSizeResult(**defaults)


class TestTradeSignalBuilder:
    def test_action_initiate_new_position(self):
        builder = TradeSignalBuilder()
        signal = builder.build(
            instrument_result=_make_instrument_result(),
            size_result=_make_size_result(target_position_pct=0.04, incremental_position_pct=0.04),
            signal_date=date(2026, 4, 1),
            current_position_pct=0.0,
        )
        assert signal.action == "initiate"

    def test_action_add_existing_position(self):
        builder = TradeSignalBuilder()
        signal = builder.build(
            instrument_result=_make_instrument_result(),
            size_result=_make_size_result(target_position_pct=0.06, incremental_position_pct=0.02),
            signal_date=date(2026, 4, 1),
            current_position_pct=0.04,
        )
        assert signal.action == "add"

    def test_action_trim(self):
        builder = TradeSignalBuilder()
        signal = builder.build(
            instrument_result=_make_instrument_result(),
            size_result=_make_size_result(
                target_position_pct=0.02,
                incremental_position_pct=-0.02,
                position_dollars=-200_000.0,
            ),
            signal_date=date(2026, 4, 1),
            current_position_pct=0.04,
        )
        assert signal.action == "trim"

    def test_action_exit(self):
        builder = TradeSignalBuilder()
        signal = builder.build(
            instrument_result=_make_instrument_result(instrument=Instrument.NO_TRADE),
            size_result=_make_size_result(
                target_position_pct=0.0,
                incremental_position_pct=-0.04,
                position_dollars=-400_000.0,
            ),
            signal_date=date(2026, 4, 1),
            current_position_pct=0.04,
        )
        assert signal.action == "exit"

    def test_action_no_trade(self):
        builder = TradeSignalBuilder()
        signal = builder.build(
            instrument_result=_make_instrument_result(instrument=Instrument.NO_TRADE),
            size_result=_make_size_result(
                target_position_pct=0.0,
                incremental_position_pct=0.0,
                position_dollars=0.0,
            ),
            signal_date=date(2026, 4, 1),
            current_position_pct=0.0,
        )
        assert signal.action == "no_trade"

    def test_risk_flags_assembled_from_both_sources(self):
        builder = TradeSignalBuilder()
        instrument_result = _make_instrument_result(notes=["note-from-instrument"])
        size_result = _make_size_result(risk_adjustments=["adjustment-from-sizer"])
        signal = builder.build(
            instrument_result=instrument_result,
            size_result=size_result,
            signal_date=date(2026, 4, 1),
        )
        assert "note-from-instrument" in signal.risk_flags
        assert "adjustment-from-sizer" in signal.risk_flags

    def test_signal_preserves_ticker(self):
        builder = TradeSignalBuilder()
        signal = builder.build(
            instrument_result=_make_instrument_result(),
            size_result=_make_size_result(),
            signal_date=date(2026, 4, 1),
            ticker="VKTX",
        )
        assert signal.ticker == "VKTX"

    def test_signal_date_preserved(self):
        builder = TradeSignalBuilder()
        signal_date = date(2026, 3, 15)
        signal = builder.build(
            instrument_result=_make_instrument_result(),
            size_result=_make_size_result(),
            signal_date=signal_date,
        )
        assert signal.signal_date == signal_date

    def test_signal_instrument_from_selection(self):
        builder = TradeSignalBuilder()
        signal = builder.build(
            instrument_result=_make_instrument_result(instrument=Instrument.CALL),
            size_result=_make_size_result(incremental_position_pct=0.03),
            signal_date=date(2026, 4, 1),
            current_position_pct=0.0,
        )
        assert signal.instrument == "call"

    def test_asymmetry_score_captured(self):
        builder = TradeSignalBuilder()
        signal = builder.build(
            instrument_result=_make_instrument_result(),
            size_result=_make_size_result(),
            signal_date=date(2026, 4, 1),
            asymmetry_score=0.42,
        )
        assert signal.asymmetry_score == pytest.approx(0.42)
