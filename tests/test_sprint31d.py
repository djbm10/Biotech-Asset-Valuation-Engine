"""
Sprint 31D — ScenarioResult extended fields tests.

Tests cover:
- All 8 extended output fields populated by build_scenarios_from_shocks
- delta_vs_base: base=0, bull>0, bear<0 under normal assumptions
- key_assumption_changes: non-empty for non-base shocks
- top_value_drivers: non-empty, max 5 entries
- kill_criteria_triggered: True when rNPV<0 or P(approval)<=0.01
- memo_interpretation: non-empty, informative content
- NAV and NAV/share math
- Base case delta_vs_base is None (not 0.0 — it's the reference)
"""
import pytest

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.market_model import MarketModel
from bve.models.scenario_shock import (
    ClinicalShock,
    CostsFCFShock,
    RegulatoryShock,
    ScenarioShock,
    SHOCK_BASE,
    SHOCK_BEAR,
    SHOCK_BULL,
)
from bve.valuation.scenario import ScenarioResult, build_scenarios_from_shocks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _asset(**kwargs) -> Asset:
    defaults = dict(
        id="s31d-001",
        name="Test Drug",
        indication="Oncology",
        therapeutic_area="oncology",
        stage="phase_3",
        modality="small_molecule",
        launch_year=2028,
        patent_expiry_year=2040,
        discount_rate=0.10,
        effective_tax_rate=0.21,
        royalty_rate=0.0,
    )
    defaults.update(kwargs)
    return Asset(**defaults)


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="s31d-001",
            phase=TrialPhase.PHASE_3,
            success_probability=0.60,
            duration_years=4.0,
            cost_millions=120.0,
        ),
    ]


def _market() -> MarketModel:
    return MarketModel(
        asset_id="s31d-001",
        therapeutic_area="oncology",
        addressable_patients_annual=40_000,
        net_price_per_patient_usd=100_000,
        peak_penetration=0.20,
        years_to_peak=4,
        patent_life_years=12,
        cogs_rate=0.12,
        sgna_rate_launch=0.35,
        sgna_rate_mature=0.18,
    )


def _result_set(net_cash=0.0, shares=1.0, shocks=None):
    return build_scenarios_from_shocks(
        _asset(), _trials(), _market(),
        net_cash_millions=net_cash,
        shares_outstanding_millions=shares,
        shocks=shocks,
    )


# ---------------------------------------------------------------------------
# ScenarioResult has all 8 extended fields
# ---------------------------------------------------------------------------

class TestScenarioResultFields:
    def test_has_delta_vs_base(self):
        rs = _result_set()
        assert hasattr(rs.bull, "delta_vs_base")
        assert hasattr(rs.base, "delta_vs_base")
        assert hasattr(rs.bear, "delta_vs_base")

    def test_has_key_assumption_changes(self):
        rs = _result_set()
        assert isinstance(rs.bull.key_assumption_changes, list)

    def test_has_top_value_drivers(self):
        rs = _result_set()
        assert isinstance(rs.bull.top_value_drivers, list)

    def test_has_kill_criteria_triggered(self):
        rs = _result_set()
        assert isinstance(rs.bull.kill_criteria_triggered, bool)

    def test_has_memo_interpretation(self):
        rs = _result_set()
        assert isinstance(rs.bull.memo_interpretation, str)

    def test_has_nav_millions(self):
        rs = _result_set(net_cash=100.0)
        assert rs.base.nav_millions == pytest.approx(rs.base.rnpv_millions + 100.0, abs=1e-4)

    def test_has_nav_per_share(self):
        rs = _result_set(net_cash=100.0, shares=50.0)
        assert rs.base.nav_per_share == pytest.approx(rs.base.nav_millions / 50.0, abs=1e-4)


# ---------------------------------------------------------------------------
# delta_vs_base
# ---------------------------------------------------------------------------

class TestDeltaVsBase:
    def test_base_delta_is_none(self):
        """Base case is the reference point — delta is undefined for itself."""
        rs = _result_set()
        assert rs.base.delta_vs_base is None

    def test_bull_delta_positive(self):
        rs = _result_set()
        assert rs.bull.delta_vs_base is not None
        assert rs.bull.delta_vs_base > 0.0

    def test_bear_delta_negative(self):
        rs = _result_set()
        assert rs.bear.delta_vs_base is not None
        assert rs.bear.delta_vs_base < 0.0

    def test_bull_delta_equals_rnpv_diff(self):
        rs = _result_set()
        expected = rs.bull.rnpv_millions - rs.base.rnpv_millions
        assert rs.bull.delta_vs_base == pytest.approx(expected, abs=1e-4)

    def test_bear_delta_equals_rnpv_diff(self):
        rs = _result_set()
        expected = rs.bear.rnpv_millions - rs.base.rnpv_millions
        assert rs.bear.delta_vs_base == pytest.approx(expected, abs=1e-4)


# ---------------------------------------------------------------------------
# key_assumption_changes
# ---------------------------------------------------------------------------

class TestKeyAssumptionChanges:
    def test_base_changes_empty(self):
        rs = _result_set()
        assert rs.base.key_assumption_changes == []

    def test_bull_changes_non_empty(self):
        rs = _result_set()
        assert len(rs.bull.key_assumption_changes) > 0

    def test_bear_changes_non_empty(self):
        rs = _result_set()
        assert len(rs.bear.key_assumption_changes) > 0

    def test_pos_mult_appears_in_changes(self):
        shock = ScenarioShock(clinical=ClinicalShock(pos_mult=1.30))
        rs = _result_set(shocks=[shock, SHOCK_BASE, SHOCK_BEAR])
        assert any("POS" in c for c in rs.bull.key_assumption_changes)

    def test_wacc_delta_appears_in_changes(self):
        shock = ScenarioShock(costs_fcf=CostsFCFShock(discount_rate_delta=0.02))
        rs = _result_set(shocks=[shock, SHOCK_BASE, SHOCK_BEAR])
        assert any("WACC" in c for c in rs.bull.key_assumption_changes)

    def test_label_breadth_appears_in_changes(self):
        shock = ScenarioShock(regulatory=RegulatoryShock(label_breadth_mult=0.70))
        rs = _result_set(shocks=[shock, SHOCK_BASE, SHOCK_BEAR])
        assert any("Label breadth" in c or "breadth" in c.lower() for c in rs.bull.key_assumption_changes)


# ---------------------------------------------------------------------------
# top_value_drivers
# ---------------------------------------------------------------------------

class TestTopValueDrivers:
    def test_base_drivers_empty(self):
        rs = _result_set()
        assert rs.base.top_value_drivers == []

    def test_bull_has_drivers(self):
        rs = _result_set()
        assert len(rs.bull.top_value_drivers) > 0

    def test_bear_has_drivers(self):
        rs = _result_set()
        assert len(rs.bear.top_value_drivers) > 0

    def test_max_5_drivers(self):
        rs = _result_set()
        assert len(rs.bull.top_value_drivers) <= 5
        assert len(rs.bear.top_value_drivers) <= 5

    def test_drivers_are_strings(self):
        rs = _result_set()
        for d in rs.bull.top_value_drivers:
            assert isinstance(d, str)


# ---------------------------------------------------------------------------
# kill_criteria_triggered
# ---------------------------------------------------------------------------

class TestKillCriteria:
    def test_base_not_killed_for_normal_asset(self):
        rs = _result_set()
        assert not rs.base.kill_criteria_triggered

    def test_bull_not_killed(self):
        rs = _result_set()
        assert not rs.bull.kill_criteria_triggered

    def test_kill_triggered_when_negative_rnpv(self):
        # Force bear to produce negative rNPV: zero-out POS, keep costs
        extreme_bear = ScenarioShock(
            label="Extreme Bear",
            clinical=ClinicalShock(pos_mult=0.01),
            costs_fcf=CostsFCFShock(rd_cost_mult=3.0),
        )
        rs = _result_set(shocks=[SHOCK_BULL, SHOCK_BASE, extreme_bear])
        assert rs.bear.kill_criteria_triggered

    def test_kill_triggered_when_near_zero_approval(self):
        # Endpoint miss: pos_mult=0.0 → P(approval) clamped to 0.01
        failure_shock = ScenarioShock(
            label="Failure",
            clinical=ClinicalShock(pos_mult=0.0),
        )
        rs = _result_set(shocks=[SHOCK_BULL, SHOCK_BASE, failure_shock])
        assert rs.bear.kill_criteria_triggered

    def test_kill_criteria_consistent_with_rnpv(self):
        rs = _result_set()
        for scenario in [rs.bull, rs.base, rs.bear]:
            expected_kill = scenario.rnpv_millions < 0.0 or scenario.cumulative_success_probability <= 0.01
            assert scenario.kill_criteria_triggered == expected_kill


# ---------------------------------------------------------------------------
# memo_interpretation
# ---------------------------------------------------------------------------

class TestMemoInterpretation:
    def test_memo_non_empty_for_all_scenarios(self):
        rs = _result_set()
        for scenario in [rs.bull, rs.base, rs.bear]:
            assert len(scenario.memo_interpretation) > 0

    def test_memo_contains_rnpv(self):
        rs = _result_set()
        # rNPV value appears somewhere in the memo
        rnpv_str = f"${rs.base.rnpv_millions:.0f}M"
        assert rnpv_str in rs.base.memo_interpretation

    def test_failure_memo_mentions_endpoint_miss(self):
        failure_shock = ScenarioShock(
            label="Failure",
            clinical=ClinicalShock(pos_mult=0.0),
        )
        rs = _result_set(shocks=[SHOCK_BULL, SHOCK_BASE, failure_shock])
        assert "endpoint" in rs.bear.memo_interpretation.lower() or "P(approval)" in rs.bear.memo_interpretation

    def test_kill_scenario_memo_mentions_kill(self):
        extreme_bear = ScenarioShock(
            label="Extreme Bear",
            clinical=ClinicalShock(pos_mult=0.01),
            costs_fcf=CostsFCFShock(rd_cost_mult=3.0),
        )
        rs = _result_set(shocks=[SHOCK_BULL, SHOCK_BASE, extreme_bear])
        if rs.bear.kill_criteria_triggered:
            assert (
                "kill" in rs.bear.memo_interpretation.lower()
                or "negative" in rs.bear.memo_interpretation.lower()
                or "cost" in rs.bear.memo_interpretation.lower()
            )

    def test_positive_scenario_memo_mentions_positive(self):
        rs = _result_set()
        assert "positive" in rs.bull.memo_interpretation.lower() or "rNPV" in rs.bull.memo_interpretation
