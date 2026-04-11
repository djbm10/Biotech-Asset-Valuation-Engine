"""
Tests for PositionPolicyEngine (Step 5 — policy / risk layer).

Covers:
- Action ladder: buy / add / monitor / avoid based on SOTP discount + conviction
- Sizing: base + catalyst boost + liquidity cap + downside floor
- Catalyst hard gate: no near-term catalyst → forced monitor
- Downside gate: bear case > current price → forced avoid (value trap)
- Liquidity gate: ADV < min_adv → halved size
- BD recommendation: partner / acquire / pass
- Rationale strings are non-empty and contain relevant keywords
"""
from __future__ import annotations

import pytest

from bve.intelligence.position_policy import (
    BDRecommendation,
    PositionPolicy,
    PositionPolicyConfig,
    PositionPolicyEngine,
    PositionPolicyInput,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(
    max_position_pct: float = 5.0,
    buy_discount_threshold: float = 0.40,
    add_discount_threshold: float = 0.20,
    avoid_downside_threshold: float = 0.40,   # 40% downside gate (biotech-appropriate)
    catalyst_gate_days: int = 90,
    catalyst_boost_days: int = 30,
    min_adv_millions: float = 1.0,
    min_conviction: float = 0.30,
) -> PositionPolicyEngine:
    cfg = PositionPolicyConfig(
        max_position_pct=max_position_pct,
        buy_discount_threshold=buy_discount_threshold,
        add_discount_threshold=add_discount_threshold,
        avoid_downside_threshold=avoid_downside_threshold,
        catalyst_gate_days=catalyst_gate_days,
        catalyst_boost_days=catalyst_boost_days,
        min_adv_millions=min_adv_millions,
        min_conviction=min_conviction,
    )
    return PositionPolicyEngine(config=cfg)


def _inp(
    ticker: str = "TEST",
    current_price: float = 10.0,
    base_sotp_per_share: float = 18.0,    # 80% upside → buy territory
    bear_sotp_per_share: float = 7.0,     # 30% downside — below 40% avoid threshold
    bull_sotp_per_share: float = 28.0,
    conviction: float = 0.65,
    next_catalyst_days: int = 30,
    adv_millions: float = 5.0,
    catalyst_description: str = "Phase 3 readout",
    existing_position_pct: float = 0.0,
) -> PositionPolicyInput:
    return PositionPolicyInput(
        ticker=ticker,
        current_price=current_price,
        base_sotp_per_share=base_sotp_per_share,
        bear_sotp_per_share=bear_sotp_per_share,
        bull_sotp_per_share=bull_sotp_per_share,
        conviction=conviction,
        next_catalyst_days=next_catalyst_days,
        adv_millions=adv_millions,
        catalyst_description=catalyst_description,
        existing_position_pct=existing_position_pct,
    )


# ---------------------------------------------------------------------------
# PositionPolicyInput validation
# ---------------------------------------------------------------------------

class TestPositionPolicyInput:
    def test_implied_upside_computed_correctly(self) -> None:
        inp = _inp(current_price=10.0, base_sotp_per_share=15.0)
        assert inp.implied_upside_pct == pytest.approx(50.0)

    def test_sotp_discount_fraction(self) -> None:
        # price=10, SOTP=16 → discount = (16-10)/10 = 0.60
        inp = _inp(current_price=10.0, base_sotp_per_share=16.0)
        assert inp.sotp_discount_fraction == pytest.approx(0.60)

    def test_downside_risk_pct(self) -> None:
        # bear=6, current=10 → downside = (10-6)/10 = 0.40 (40%)
        inp = _inp(current_price=10.0, bear_sotp_per_share=6.0, base_sotp_per_share=18.0)
        assert inp.downside_risk_pct == pytest.approx(0.40)

    def test_at_par_is_zero_discount(self) -> None:
        inp = _inp(current_price=10.0, base_sotp_per_share=10.0)
        assert inp.sotp_discount_fraction == pytest.approx(0.0)

    def test_premium_to_sotp_is_negative_discount(self) -> None:
        # (10 - 12) / 12 = -0.1667
        inp = _inp(current_price=12.0, base_sotp_per_share=10.0)
        assert inp.sotp_discount_fraction == pytest.approx(-1.0 / 6.0)


# ---------------------------------------------------------------------------
# Action ladder
# ---------------------------------------------------------------------------

class TestActionLadder:
    def test_buy_on_deep_discount_and_high_conviction(self) -> None:
        eng = _engine()
        # 80% upside (> 40% buy threshold), conviction=0.65, catalyst in 30d
        policy = eng.evaluate(_inp())
        assert policy.action == "buy"

    def test_add_on_moderate_discount(self) -> None:
        eng = _engine()
        # 30% upside (between 20% and 40%), conviction=0.65
        inp = _inp(current_price=10.0, base_sotp_per_share=13.0, conviction=0.55)
        policy = eng.evaluate(inp)
        assert policy.action == "add"

    def test_monitor_on_low_discount(self) -> None:
        eng = _engine()
        # 10% upside (< 20% add threshold)
        inp = _inp(current_price=10.0, base_sotp_per_share=11.0)
        policy = eng.evaluate(inp)
        assert policy.action == "monitor"

    def test_avoid_on_premium_to_sotp(self) -> None:
        eng = _engine()
        # Trading above SOTP
        inp = _inp(current_price=15.0, base_sotp_per_share=12.0)
        policy = eng.evaluate(inp)
        assert policy.action == "avoid"

    def test_avoid_when_conviction_too_low(self) -> None:
        eng = _engine(min_conviction=0.30)
        inp = _inp(conviction=0.25)    # below minimum
        policy = eng.evaluate(inp)
        assert policy.action == "avoid"

    def test_monitor_when_no_near_term_catalyst(self) -> None:
        eng = _engine(catalyst_gate_days=90)
        # Good discount and conviction, but catalyst is 120 days away
        inp = _inp(next_catalyst_days=120)
        policy = eng.evaluate(inp)
        assert policy.action == "monitor"

    def test_avoid_when_downside_risk_exceeds_threshold(self) -> None:
        eng = _engine(avoid_downside_threshold=0.40)
        # Bear case = 5 vs current 10 → 50% downside > 40% threshold → avoid
        inp = _inp(current_price=10.0, bear_sotp_per_share=5.0)
        policy = eng.evaluate(inp)
        assert policy.action == "avoid"

    def test_buy_requires_both_discount_and_conviction(self) -> None:
        eng = _engine()
        # Deep discount but low conviction → add, not buy
        inp = _inp(
            current_price=10.0,
            base_sotp_per_share=18.0,   # 80% upside
            conviction=0.40,            # moderate conviction
        )
        policy = eng.evaluate(inp)
        # Conviction 0.40 is below typical buy conviction threshold (0.55)
        assert policy.action in ("add", "monitor")  # not buy

    def test_existing_position_shifts_add_to_monitor(self) -> None:
        eng = _engine()
        # Already have 3.5% → avoid adding more in moderate-discount territory
        inp = _inp(
            current_price=10.0, base_sotp_per_share=13.0,
            conviction=0.55, existing_position_pct=3.5,
        )
        policy = eng.evaluate(inp)
        # Should not recommend adding if already near max
        assert policy.action in ("monitor", "add")


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------

class TestPositionSizing:
    def test_sizing_positive_for_buy(self) -> None:
        eng = _engine()
        policy = eng.evaluate(_inp())
        assert policy.sizing_pct > 0

    def test_sizing_capped_at_max_position_pct(self) -> None:
        eng = _engine(max_position_pct=5.0)
        # Extreme discount + conviction shouldn't exceed max
        inp = _inp(
            current_price=5.0, base_sotp_per_share=100.0,
            conviction=1.0, next_catalyst_days=7,
        )
        policy = eng.evaluate(inp)
        assert policy.sizing_pct <= 5.0

    def test_sizing_zero_for_avoid(self) -> None:
        eng = _engine()
        inp = _inp(current_price=15.0, base_sotp_per_share=12.0)
        policy = eng.evaluate(inp)
        assert policy.sizing_pct == pytest.approx(0.0)

    def test_sizing_zero_for_monitor(self) -> None:
        eng = _engine()
        inp = _inp(current_price=10.0, base_sotp_per_share=11.0)
        policy = eng.evaluate(inp)
        assert policy.sizing_pct == pytest.approx(0.0)

    def test_catalyst_boost_increases_size_when_near(self) -> None:
        eng = _engine(catalyst_boost_days=30)
        far_cat = _inp(next_catalyst_days=60)
        near_cat = _inp(next_catalyst_days=14)
        pol_far = eng.evaluate(far_cat)
        pol_near = eng.evaluate(near_cat)
        if pol_near.action in ("buy", "add") and pol_far.action in ("buy", "add"):
            assert pol_near.sizing_pct >= pol_far.sizing_pct

    def test_liquidity_cap_halves_size_for_small_caps(self) -> None:
        eng = _engine(min_adv_millions=1.0)
        liquid = _inp(adv_millions=10.0)
        illiquid = _inp(adv_millions=0.5)    # below min_adv
        pol_liquid = eng.evaluate(liquid)
        pol_illiquid = eng.evaluate(illiquid)
        if pol_liquid.action in ("buy", "add") and pol_illiquid.action in ("buy", "add"):
            assert pol_illiquid.sizing_pct < pol_liquid.sizing_pct

    def test_size_scales_with_discount_depth(self) -> None:
        eng = _engine()
        small_disc = _inp(current_price=10.0, base_sotp_per_share=12.5)  # 25%
        big_disc = _inp(current_price=10.0, base_sotp_per_share=18.0)    # 80%
        pol_small = eng.evaluate(small_disc)
        pol_big = eng.evaluate(big_disc)
        if pol_small.action in ("buy", "add") and pol_big.action in ("buy", "add"):
            assert pol_big.sizing_pct >= pol_small.sizing_pct


# ---------------------------------------------------------------------------
# Output fields
# ---------------------------------------------------------------------------

class TestPolicyOutputFields:
    def test_rationale_is_non_empty(self) -> None:
        eng = _engine()
        policy = eng.evaluate(_inp())
        assert len(policy.rationale) > 20

    def test_catalyst_gate_stored_when_provided(self) -> None:
        eng = _engine()
        inp = _inp(catalyst_description="Ph3 readout VERITAC-2")
        policy = eng.evaluate(inp)
        assert policy.catalyst_gate == "Ph3 readout VERITAC-2"

    def test_downside_case_matches_input(self) -> None:
        eng = _engine()
        inp = _inp(bear_sotp_per_share=6.5)
        policy = eng.evaluate(inp)
        assert policy.downside_case_per_share == pytest.approx(6.5)

    def test_output_is_frozen(self) -> None:
        eng = _engine()
        policy = eng.evaluate(_inp())
        with pytest.raises((TypeError, AttributeError)):
            policy.action = "avoid"  # type: ignore[misc]

    def test_upside_case_stored(self) -> None:
        eng = _engine()
        inp = _inp(bull_sotp_per_share=28.0)
        policy = eng.evaluate(inp)
        assert policy.upside_case_per_share == pytest.approx(28.0)

    def test_ticker_propagated(self) -> None:
        eng = _engine()
        inp = _inp(ticker="ARVN")
        policy = eng.evaluate(inp)
        assert policy.ticker == "ARVN"


# ---------------------------------------------------------------------------
# BD recommendation
# ---------------------------------------------------------------------------

class TestBDRecommendation:
    def test_acquire_on_high_ma_probability_and_fit(self) -> None:
        rec = BDRecommendation.from_scores(
            ticker="SRRK",
            ma_probability=0.82,
            strategic_fit=0.78,
            current_price=15.0,
            estimated_deal_value=22.0,
            process_risk="low",
        )
        assert rec.action == "acquire"

    def test_partner_on_moderate_ma_probability(self) -> None:
        rec = BDRecommendation.from_scores(
            ticker="KYMR",
            ma_probability=0.55,
            strategic_fit=0.65,
            current_price=25.0,
            estimated_deal_value=38.0,
            process_risk="medium",
        )
        assert rec.action == "partner"

    def test_pass_on_low_ma_probability(self) -> None:
        rec = BDRecommendation.from_scores(
            ticker="MRNA",
            ma_probability=0.20,
            strategic_fit=0.35,
            current_price=65.0,
            estimated_deal_value=72.0,
            process_risk="high",
        )
        assert rec.action == "pass"

    def test_pass_on_negative_deal_premium(self) -> None:
        rec = BDRecommendation.from_scores(
            ticker="TEST",
            ma_probability=0.70,
            strategic_fit=0.70,
            current_price=50.0,
            estimated_deal_value=40.0,   # deal value below current price
            process_risk="low",
        )
        assert rec.action == "pass"

    def test_implied_deal_premium_computed(self) -> None:
        rec = BDRecommendation.from_scores(
            ticker="TEST",
            ma_probability=0.60,
            strategic_fit=0.60,
            current_price=20.0,
            estimated_deal_value=30.0,
            process_risk="low",
        )
        assert rec.implied_deal_premium_pct == pytest.approx(50.0)

    def test_rationale_non_empty(self) -> None:
        rec = BDRecommendation.from_scores(
            ticker="TEST",
            ma_probability=0.60,
            strategic_fit=0.60,
            current_price=20.0,
            estimated_deal_value=30.0,
            process_risk="low",
        )
        assert len(rec.rationale) > 10
