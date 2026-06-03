"""
Step 6 tests: unified valuation entry path.

Monte Carlo, scenario analysis, and sensitivity analysis now run the same
economic stack as the deterministic base case — including LOE and deal economics.

Structure
---------
TestBackwardCompat           — compute_rnpv() wrapper still returns no-LOE/no-deal baseline
TestComputeRnpvFull          — compute_rnpv_full() drives full economic stack
TestMCWithLOE                — MC mean shifts consistently with LOE
TestMCWithDeal               — MC mean reflects deal economics (royalty / cdev)
TestScenariosWithLOE         — scenario base = deterministic rNPV when no perturbation
TestScenariosWithDeal        — deal economics flow through all three scenario runs
TestSensitivityWithFullStack — sensitivity uses same economic stack as base case
TestEngineUnification        — ValuationEngine.run() sends same context to all paths
TestSnapshotLOEIncludedMC    — locked regression: MC mean with LOE, seed=0, n=1000

Step 6 verification (post-review)
----------------------------------
TestWrapperEquivalence       — compute_rnpv() == compute_rnpv_full(loe=None, deal=None), all fields
TestMCContextImmutability    — loe_profile dict and deal object not mutated during MC runs
TestSensitivityContextInvariance — each sensitivity perturbation changes only the shocked variable;
                                   deal terms and LOE are identical across all perturbations
"""
from __future__ import annotations

import pytest

from bve.config.assumptions_loader import AssumptionsLoader

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.cost_model import CostModel
from bve.models.deal_economics import DealEconomics, Milestone, MilestoneDirection, MilestoneTrigger
from bve.models.drug_asset_program import CommercialPlan, DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams, run_monte_carlo
from bve.models.probability_model import ProbabilityModel
from bve.models.revenue_model import RevenueModel
from bve.models.rnpv_model import RNPVModel, compute_rnpv, compute_rnpv_full
from bve.valuation.scenario import SCENARIO_BASE, build_scenarios
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Shared fixtures — identical to the canonical snapshot setup
# ---------------------------------------------------------------------------

_ASSET_ID = "S6-001"


def _asset(royalty_rate: float = 0.0) -> Asset:
    return Asset(
        id=_ASSET_ID, name="S6-Asset", indication="test",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.10,
        royalty_rate=royalty_rate,
    )


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(asset_id=_ASSET_ID, phase=TrialPhase.PHASE_2,
                      success_probability=0.37, duration_years=2.5, cost_millions=80.0),
        ClinicalTrial(asset_id=_ASSET_ID, phase=TrialPhase.PHASE_3,
                      success_probability=0.55, duration_years=3.5, cost_millions=250.0),
        ClinicalTrial(asset_id=_ASSET_ID, phase=TrialPhase.NDA_BLA,
                      success_probability=0.87, duration_years=1.5, cost_millions=35.0),
    ]


def _market() -> MarketModel:
    return MarketModel(
        asset_id=_ASSET_ID, total_addressable_market_millions=8_000.0,
        peak_penetration=0.12, years_to_peak=5, patent_life_years=12,
        cogs_rate=0.18, sgna_rate_launch=0.40, sgna_rate_mature=0.20,
    )


def _company() -> Company:
    return Company(
        id="CO_S6", name="Step6 Co", ticker="S6",
        cash_millions=100.0, shares_outstanding_millions=50.0,
        asset_ids=[_ASSET_ID],
    )


def _loe() -> dict:
    return dict(AssumptionsLoader.get().loe_erosion_profile("small_molecule"))


# ---------------------------------------------------------------------------
# TestBackwardCompat
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """compute_rnpv() must remain unchanged — no LOE, no deal."""

    def test_compute_rnpv_returns_no_loe_baseline(self):
        """compute_rnpv() without LOE baseline. Sprint 9: updated to 65.13 after UFCF/tax fix."""
        result = compute_rnpv(_asset(), _trials(), _market())
        assert result.rnpv_millions == pytest.approx(65.13, abs=0.5)

    def test_compute_rnpv_no_milestone_receipts(self):
        result = compute_rnpv(_asset(), _trials(), _market())
        assert result.deal_milestone_receipts_pv_millions == 0.0
        assert result.upfront_receipt_millions == 0.0

    def test_compute_rnpv_full_with_no_context_equals_compute_rnpv(self):
        """compute_rnpv_full(loe_profile=None, deal=None) == compute_rnpv()."""
        baseline = compute_rnpv(_asset(), _trials(), _market())
        full_no_ctx = compute_rnpv_full(_asset(), _trials(), _market())
        assert full_no_ctx.rnpv_millions == pytest.approx(baseline.rnpv_millions, rel=1e-9)

    def test_run_monte_carlo_no_loe_param_unchanged(self):
        """Existing run_monte_carlo() calls without loe_profile still return no-LOE results."""
        mc = run_monte_carlo(_asset(), _trials(), _market(),
                             MonteCarloParams(n_simulations=200, random_seed=0))
        mc_with_loe = run_monte_carlo(_asset(), _trials(), _market(),
                                      MonteCarloParams(n_simulations=200, random_seed=0),
                                      loe_profile=_loe())
        assert mc.mean_millions < mc_with_loe.mean_millions  # LOE adds value

    def test_build_scenarios_no_loe_param_unchanged(self):
        """build_scenarios() without loe_profile returns no-LOE results."""
        scenarios_no_loe = build_scenarios(_asset(), _trials(), _market())
        scenarios_with_loe = build_scenarios(_asset(), _trials(), _market(), loe_profile=_loe())
        assert scenarios_no_loe.base.rnpv_millions < scenarios_with_loe.base.rnpv_millions


# ---------------------------------------------------------------------------
# TestComputeRnpvFull
# ---------------------------------------------------------------------------

class TestComputeRnpvFull:
    """compute_rnpv_full() is the unified stack used by all internal paths."""

    def test_loe_increases_rnpv(self):
        no_loe = compute_rnpv_full(_asset(), _trials(), _market())
        with_loe = compute_rnpv_full(_asset(), _trials(), _market(), loe_profile=_loe())
        assert with_loe.rnpv_millions > no_loe.rnpv_millions

    def test_loe_value_matches_step3_snapshot(self):
        # Sprint 9.10: 83.13 after LOE 3→5 extension (was 81.01 pre-9.10)
        result = compute_rnpv_full(_asset(), _trials(), _market(), loe_profile=_loe())
        assert result.rnpv_millions == pytest.approx(83.13, abs=0.5)

    def test_deal_royalty_reduces_rnpv(self):
        no_deal = compute_rnpv_full(_asset(), _trials(), _market(), loe_profile=_loe())
        with_deal = compute_rnpv_full(_asset(), _trials(), _market(),
                                      loe_profile=_loe(),
                                      deal=DealEconomics(royalty_rate=0.15))
        assert with_deal.rnpv_millions < no_deal.rnpv_millions

    def test_combined_loe_and_deal_is_consistent(self):
        """LOE and deal effects compound correctly — both apply independently."""
        base = compute_rnpv_full(_asset(), _trials(), _market())
        with_loe = compute_rnpv_full(_asset(), _trials(), _market(), loe_profile=_loe())
        deal = DealEconomics(royalty_rate=0.10, cdev_cost_share=0.5)
        with_both = compute_rnpv_full(_asset(), _trials(), _market(),
                                      loe_profile=_loe(), deal=deal)
        # LOE alone: higher than base
        assert with_loe.rnpv_millions > base.rnpv_millions
        # cdev=0.5 cuts costs → raises rNPV; royalty=0.10 cuts revenue → reduces rNPV
        # The direction of combined effect depends on magnitudes; just check it runs and differs
        assert with_both.rnpv_millions != base.rnpv_millions


# ---------------------------------------------------------------------------
# TestMCWithLOE
# ---------------------------------------------------------------------------

class TestMCWithLOE:
    """MC mean with LOE exceeds MC mean without LOE (LOE adds discounted tail value)."""

    def test_mc_mean_higher_with_loe(self):
        params = MonteCarloParams(n_simulations=500, random_seed=42)
        mc_no_loe = run_monte_carlo(_asset(), _trials(), _market(), params)
        mc_with_loe = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=_loe())
        assert mc_with_loe.mean_millions > mc_no_loe.mean_millions

    def test_mc_percentiles_all_higher_with_loe(self):
        """All percentiles shift up with LOE (tail adds value at every draw)."""
        params = MonteCarloParams(n_simulations=500, random_seed=7)
        mc_no = run_monte_carlo(_asset(), _trials(), _market(), params)
        mc_loe = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=_loe())
        for attr in ("percentile_25_millions", "percentile_50_millions", "percentile_75_millions"):
            assert getattr(mc_loe, attr) > getattr(mc_no, attr)

    def test_mc_seed_reproducible_with_loe(self):
        """Same seed and context must reproduce identical results."""
        params = MonteCarloParams(n_simulations=300, random_seed=123)
        mc1 = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=_loe())
        mc2 = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=_loe())
        assert mc1.mean_millions == mc2.mean_millions

    def test_mc_loe_mean_near_deterministic_rnpv(self):
        """MC mean (with same LOE) should be in the same ballpark as deterministic rNPV."""
        det = compute_rnpv_full(_asset(), _trials(), _market(), loe_profile=_loe())
        params = MonteCarloParams(n_simulations=2000, random_seed=0)
        mc = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=_loe())
        assert abs(mc.mean_millions - det.rnpv_millions) / max(1, abs(det.rnpv_millions)) < 0.50


# ---------------------------------------------------------------------------
# TestMCWithDeal
# ---------------------------------------------------------------------------

class TestMCWithDeal:
    """MC reflects deal economics consistently across all simulations."""

    def test_mc_royalty_reduces_mean(self):
        params = MonteCarloParams(n_simulations=500, random_seed=0)
        mc_base = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=_loe())
        mc_royalty = run_monte_carlo(_asset(), _trials(), _market(), params,
                                     loe_profile=_loe(), deal=DealEconomics(royalty_rate=0.20))
        assert mc_royalty.mean_millions < mc_base.mean_millions

    def test_mc_cdev_half_increases_mean(self):
        """cdev_cost_share=0.5 halves trial costs → higher rNPV at every draw."""
        params = MonteCarloParams(n_simulations=500, random_seed=0)
        mc_base = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=_loe())
        mc_cdev = run_monte_carlo(_asset(), _trials(), _market(), params,
                                  loe_profile=_loe(), deal=DealEconomics(cdev_cost_share=0.5))
        assert mc_cdev.mean_millions > mc_base.mean_millions

    def test_mc_upfront_receipt_shifts_all_values(self):
        """
        An upfront receipt (t=0, face value) shifts all MC simulation values by
        exactly upfront_receipt_millions — since it's not stochastic.
        """
        params = MonteCarloParams(n_simulations=300, random_seed=99)
        upfront = 50.0
        mc_base = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=_loe())
        mc_upfr = run_monte_carlo(_asset(), _trials(), _market(), params,
                                  loe_profile=_loe(),
                                  deal=DealEconomics(upfront_receipt_millions=upfront))
        # Every simulation adds the same face-value upfront → mean shifts by exactly upfront
        assert mc_upfr.mean_millions == pytest.approx(mc_base.mean_millions + upfront, abs=0.01)


# ---------------------------------------------------------------------------
# TestScenariosWithLOE
# ---------------------------------------------------------------------------

class TestScenariosWithLOE:
    """
    Scenario base case (no perturbation) must equal deterministic rNPV when
    both use the same economic stack.  This was NOT true before Step 6.
    """

    def test_base_scenario_equals_deterministic_rnpv(self):
        """
        SCENARIO_BASE applies no multipliers.  With the same LOE profile,
        scenario_base.rnpv_millions must equal compute_rnpv_full().rnpv_millions.
        """
        loe = _loe()
        det = compute_rnpv_full(_asset(), _trials(), _market(), loe_profile=loe)
        scenarios = build_scenarios(_asset(), _trials(), _market(), loe_profile=loe)
        assert scenarios.base.rnpv_millions == pytest.approx(det.rnpv_millions, abs=0.01)

    def test_base_scenario_no_loe_equals_compute_rnpv(self):
        """Without LOE, scenario base still matches compute_rnpv() baseline."""
        det = compute_rnpv(_asset(), _trials(), _market())
        scenarios = build_scenarios(_asset(), _trials(), _market())  # no loe_profile
        assert scenarios.base.rnpv_millions == pytest.approx(det.rnpv_millions, abs=0.01)

    def test_scenario_ordering_preserved_with_loe(self):
        loe = _loe()
        scenarios = build_scenarios(_asset(), _trials(), _market(), loe_profile=loe)
        assert scenarios.bull.rnpv_millions > scenarios.base.rnpv_millions
        assert scenarios.base.rnpv_millions > scenarios.bear.rnpv_millions

    def test_scenarios_with_loe_all_exceed_without_loe(self):
        """With LOE, all three scenario rNPVs are higher than without."""
        s_no = build_scenarios(_asset(), _trials(), _market())
        s_lo = build_scenarios(_asset(), _trials(), _market(), loe_profile=_loe())
        for attr in ("bull", "base", "bear"):
            assert getattr(s_lo, attr).rnpv_millions > getattr(s_no, attr).rnpv_millions


# ---------------------------------------------------------------------------
# TestScenariosWithDeal
# ---------------------------------------------------------------------------

class TestScenariosWithDeal:
    """Deal economics apply uniformly across all scenario runs."""

    def test_royalty_reduces_all_scenarios(self):
        loe = _loe()
        deal = DealEconomics(royalty_rate=0.15)
        s_base = build_scenarios(_asset(), _trials(), _market(), loe_profile=loe)
        s_deal = build_scenarios(_asset(), _trials(), _market(), loe_profile=loe, deal=deal)
        for attr in ("bull", "base", "bear"):
            assert getattr(s_deal, attr).rnpv_millions < getattr(s_base, attr).rnpv_millions

    def test_cdev_half_raises_all_scenarios(self):
        loe = _loe()
        deal = DealEconomics(cdev_cost_share=0.5)
        s_base = build_scenarios(_asset(), _trials(), _market(), loe_profile=loe)
        s_deal = build_scenarios(_asset(), _trials(), _market(), loe_profile=loe, deal=deal)
        for attr in ("bull", "base", "bear"):
            assert getattr(s_deal, attr).rnpv_millions > getattr(s_base, attr).rnpv_millions

    def test_deal_base_scenario_equals_deterministic(self):
        """With deal terms, scenario base still equals compute_rnpv_full() (no multipliers)."""
        loe = _loe()
        deal = DealEconomics(royalty_rate=0.10, cdev_cost_share=0.7)
        det = compute_rnpv_full(_asset(), _trials(), _market(), loe_profile=loe, deal=deal)
        scenarios = build_scenarios(_asset(), _trials(), _market(), loe_profile=loe, deal=deal)
        assert scenarios.base.rnpv_millions == pytest.approx(det.rnpv_millions, abs=0.01)


# ---------------------------------------------------------------------------
# TestSensitivityWithFullStack
# ---------------------------------------------------------------------------

class TestSensitivityWithFullStack:
    """
    Sensitivity analysis (tornado) uses the same economic stack as the base case.
    Verify by checking that the engine's sensitivities match the correct LOE/deal context.
    """

    def _run(self, loe: bool = True, deal: DealEconomics | None = None) -> "ValuationOutput":
        plan = CommercialPlan.from_modality("small_molecule") if loe else CommercialPlan.no_loe()
        program = DrugAssetProgram(
            asset=_asset(), trials=_trials(), market_model=_market(),
            commercial_plan=plan,
            deal_economics=deal or DealEconomics(),
        )
        engine = ValuationEngine.from_program(
            program=program, company=_company(),
            mc_params=MonteCarloParams(n_simulations=100, random_seed=0),
        )
        return engine.run()

    def test_sensitivities_present(self):
        output = self._run()
        assert len(output.sensitivities) > 0

    def test_peak_sales_sensitivity_ordered(self):
        """Peak sales high must give higher rNPV than peak sales low."""
        output = self._run()
        ps = next(s for s in output.sensitivities if "Peak Sales" in s.parameter)
        assert ps.high_rnpv > ps.low_rnpv

    def test_discount_rate_sensitivity_ordered(self):
        """Lower discount rate must give higher rNPV (higher_rnpv = lower rate side)."""
        output = self._run()
        dr = next(s for s in output.sensitivities if "Discount" in s.parameter)
        assert dr.high_rnpv > dr.low_rnpv  # high_rnpv stores lower-rate result

    def test_base_sensitivity_consistent_with_loe(self):
        """
        With LOE: sensitivity base rNPV should be close to the LOE-inclusive deterministic value.
        The sensitivity base_rnpv is computed inside ValuationEngine using the same context.
        We proxy this by checking the tornado's base reflects LOE (check via output.rnpv).
        """
        out_loe = self._run(loe=True)
        out_no_loe = self._run(loe=False)
        # Deterministic rNPV should differ between runs
        assert out_loe.rnpv.rnpv_millions > out_no_loe.rnpv.rnpv_millions
        # Tornado swings should also differ (sensitivity runs on full economic stack)
        ps_loe = next(s for s in out_loe.sensitivities if "Peak Sales" in s.parameter)
        ps_no = next(s for s in out_no_loe.sensitivities if "Peak Sales" in s.parameter)
        assert ps_loe.swing != ps_no.swing


# ---------------------------------------------------------------------------
# TestEngineUnification
# ---------------------------------------------------------------------------

class TestEngineUnification:
    """
    ValuationEngine.run() sends the same loe_profile and deal to all paths.
    Verify by comparing outputs: scenario base should match deterministic rNPV,
    and MC mean should be consistent with the LOE-inclusive stack.
    """

    def _engine_with_loe_and_deal(self, deal: DealEconomics = None) -> ValuationEngine:
        program = DrugAssetProgram.build(
            asset=_asset(), trials=_trials(), market_model=_market(),
            load_loe=True,
            deal_economics=deal or DealEconomics(),
        )
        return ValuationEngine.from_program(
            program=program, company=_company(),
            mc_params=MonteCarloParams(n_simulations=300, random_seed=42),
        )

    def test_scenario_base_equals_deterministic_rnpv(self):
        """After Step 6, scenario base must equal the engine's own deterministic rNPV."""
        output = self._engine_with_loe_and_deal().run()
        assert output.scenarios.base.rnpv_millions == pytest.approx(
            output.rnpv.rnpv_millions, abs=0.02
        )

    def test_mc_mean_near_deterministic_rnpv_with_loe(self):
        """MC mean (with LOE) should be in the same range as deterministic rNPV (with LOE)."""
        output = self._engine_with_loe_and_deal().run()
        det = output.rnpv.rnpv_millions
        mc_mean = output.monte_carlo.mean_millions
        # Allow 50% deviation (sampling noise at 300 sims)
        assert abs(mc_mean - det) / max(1, abs(det)) < 0.50

    def test_deal_royalty_reduces_all_engine_outputs(self):
        """A deal royalty reduces: deterministic rNPV, scenario base, and MC mean."""
        out_base = self._engine_with_loe_and_deal().run()
        out_deal = self._engine_with_loe_and_deal(DealEconomics(royalty_rate=0.20)).run()
        assert out_deal.rnpv.rnpv_millions < out_base.rnpv.rnpv_millions
        assert out_deal.scenarios.base.rnpv_millions < out_base.scenarios.base.rnpv_millions
        assert out_deal.monte_carlo.mean_millions < out_base.monte_carlo.mean_millions

    def test_cdev_half_raises_all_engine_outputs(self):
        """cdev_cost_share=0.5 raises: deterministic rNPV, scenario base, and MC mean."""
        out_base = self._engine_with_loe_and_deal().run()
        out_cdev = self._engine_with_loe_and_deal(DealEconomics(cdev_cost_share=0.5)).run()
        assert out_cdev.rnpv.rnpv_millions > out_base.rnpv.rnpv_millions
        assert out_cdev.scenarios.base.rnpv_millions > out_base.scenarios.base.rnpv_millions
        assert out_cdev.monte_carlo.mean_millions > out_base.monte_carlo.mean_millions

    def test_suppressed_loe_propagates_to_scenario_and_mc(self):
        """CommercialPlan.no_loe() propagates to scenarios and MC (no LOE tail anywhere)."""
        program_no_loe = DrugAssetProgram.build(
            asset=_asset(), trials=_trials(), market_model=_market(), load_loe=False,
        )
        engine_no_loe = ValuationEngine.from_program(
            program=program_no_loe, company=_company(),
            mc_params=MonteCarloParams(n_simulations=200, random_seed=0),
        )
        program_with_loe = DrugAssetProgram.build(
            asset=_asset(), trials=_trials(), market_model=_market(), load_loe=True,
        )
        engine_with_loe = ValuationEngine.from_program(
            program=program_with_loe, company=_company(),
            mc_params=MonteCarloParams(n_simulations=200, random_seed=0),
        )
        out_no = engine_no_loe.run()
        out_lo = engine_with_loe.run()
        # All three paths should reflect the LOE difference
        assert out_lo.rnpv.rnpv_millions > out_no.rnpv.rnpv_millions
        assert out_lo.scenarios.base.rnpv_millions > out_no.scenarios.base.rnpv_millions
        assert out_lo.monte_carlo.mean_millions > out_no.monte_carlo.mean_millions


# ---------------------------------------------------------------------------
# TestSnapshotLOEIncludedMC
# ---------------------------------------------------------------------------

class TestSnapshotLOEIncludedMC:
    """
    Locked regression snapshot for MC with LOE.

    Sprint 9 update: all values reflect 21% effective tax rate (UFCF fix, Task 9.1).
    Pre-Sprint-9 values: no-LOE mean ≈ 123.75, LOE mean ≈ 144.57.
    Post-Sprint-9 values: no-LOE mean ≈ 69.51, LOE mean ≈ 85.96.
    """

    def test_mc_snapshot_with_loe_seed0_n1000(self):
        loe = _loe()
        mc = run_monte_carlo(
            _asset(), _trials(), _market(),
            MonteCarloParams(n_simulations=1000, random_seed=0),
            loe_profile=loe,
        )
        # Sprint 9: updated to 85.96 (was 144.57 pre-Sprint-9)
        assert mc.mean_millions == pytest.approx(85.96, abs=5.0)

    def test_mc_snapshot_without_loe_still_matches_old_baseline(self):
        """Sprint 9: no-LOE MC baseline updated to 69.51 after UFCF/tax fix (was 123.75)."""
        mc = run_monte_carlo(
            _asset(), _trials(), _market(),
            MonteCarloParams(n_simulations=1000, random_seed=0),
        )
        assert mc.mean_millions == pytest.approx(69.51, abs=5.0)


# ---------------------------------------------------------------------------
# TestWrapperEquivalence (Step 6 verification)
# compute_rnpv() == compute_rnpv_full(loe_profile=None, deal=None) — all fields
# ---------------------------------------------------------------------------

class TestWrapperEquivalence:
    """
    compute_rnpv() delegates to compute_rnpv_full() with no context.
    Every field in the result must be bit-for-bit identical.
    """

    def _both(self):
        r1 = compute_rnpv(_asset(), _trials(), _market())
        r2 = compute_rnpv_full(_asset(), _trials(), _market(), loe_profile=None, deal=None)
        return r1, r2

    def test_rnpv_millions_identical(self):
        r1, r2 = self._both()
        assert r1.rnpv_millions == r2.rnpv_millions

    def test_gross_revenue_pv_identical(self):
        r1, r2 = self._both()
        assert r1.gross_revenue_pv_millions == r2.gross_revenue_pv_millions

    def test_probability_adjusted_revenue_pv_identical(self):
        r1, r2 = self._both()
        assert r1.probability_adjusted_revenue_pv_millions == r2.probability_adjusted_revenue_pv_millions

    def test_trial_costs_pv_identical(self):
        r1, r2 = self._both()
        assert r1.trial_costs_pv_millions == r2.trial_costs_pv_millions

    def test_cumulative_success_probability_identical(self):
        r1, r2 = self._both()
        assert r1.cumulative_success_probability == r2.cumulative_success_probability

    def test_years_to_launch_identical(self):
        r1, r2 = self._both()
        assert r1.years_to_launch == r2.years_to_launch

    def test_peak_sales_identical(self):
        r1, r2 = self._both()
        assert r1.peak_sales_millions == r2.peak_sales_millions

    def test_net_ownership_identical(self):
        r1, r2 = self._both()
        assert r1.net_ownership == r2.net_ownership

    def test_deal_fields_zero_in_both(self):
        r1, r2 = self._both()
        assert r1.deal_milestone_receipts_pv_millions == 0.0
        assert r2.deal_milestone_receipts_pv_millions == 0.0
        assert r1.upfront_receipt_millions == 0.0
        assert r2.upfront_receipt_millions == 0.0

    def test_phase_breakdown_identical(self):
        r1, r2 = self._both()
        assert len(r1.phase_breakdown) == len(r2.phase_breakdown)
        for pb1, pb2 in zip(r1.phase_breakdown, r2.phase_breakdown):
            assert pb1.pv_cost_weighted == pb2.pv_cost_weighted
            assert pb1.prob_reaching == pb2.prob_reaching


# ---------------------------------------------------------------------------
# TestMCContextImmutability (Step 6 verification)
# loe_profile dict and deal are not mutated during MC runs
# ---------------------------------------------------------------------------

class TestMCContextImmutability:
    """
    loe_profile is a plain dict (mutable).  deal is a Pydantic model.
    Neither must be modified across MC simulations.
    """

    def test_loe_profile_dict_unchanged_after_mc(self):
        loe = _loe()
        original = dict(loe)  # snapshot before run
        run_monte_carlo(
            _asset(), _trials(), _market(),
            MonteCarloParams(n_simulations=200, random_seed=0),
            loe_profile=loe,
        )
        assert loe == original, f"loe_profile mutated during MC: {loe} != {original}"

    def test_loe_profile_keys_unchanged_after_mc(self):
        loe = _loe()
        keys_before = set(loe.keys())
        run_monte_carlo(
            _asset(), _trials(), _market(),
            MonteCarloParams(n_simulations=200, random_seed=0),
            loe_profile=loe,
        )
        assert set(loe.keys()) == keys_before

    def test_deal_fields_unchanged_after_mc(self):
        deal = DealEconomics(royalty_rate=0.12, cdev_cost_share=0.6, upfront_cost_millions=10.0)
        royalty_before = deal.royalty_rate
        cdev_before = deal.cdev_cost_share
        upfront_before = deal.upfront_cost_millions
        run_monte_carlo(
            _asset(), _trials(), _market(),
            MonteCarloParams(n_simulations=200, random_seed=0),
            loe_profile=_loe(), deal=deal,
        )
        assert deal.royalty_rate == royalty_before
        assert deal.cdev_cost_share == cdev_before
        assert deal.upfront_cost_millions == upfront_before

    def test_loe_profile_same_reference_produces_same_mc_results(self):
        """Same object passed twice must produce identical results (no internal mutation)."""
        loe = _loe()
        params = MonteCarloParams(n_simulations=300, random_seed=42)
        mc1 = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=loe)
        mc2 = run_monte_carlo(_asset(), _trials(), _market(), params, loe_profile=loe)
        assert mc1.mean_millions == mc2.mean_millions


# ---------------------------------------------------------------------------
# TestSensitivityContextInvariance (Step 6 verification)
# Each sensitivity perturbation changes exactly one variable.
# deal terms and LOE profile are identical across all perturbations.
# ---------------------------------------------------------------------------

class TestSensitivityContextInvariance:
    """
    The sensitivity _rnpv() lambda captures loe_profile and deal by closure.
    We verify that:
      1. The sensitivity value for a specific perturbation matches what
         compute_rnpv_full() returns when we apply that same perturbation
         manually with the identical LOE and deal context.
      2. Non-perturbed assumptions (market, trials) are unchanged in each call.
    """

    def _engine_output(self, deal: DealEconomics) -> "ValuationOutput":
        program = DrugAssetProgram(
            asset=_asset(), trials=_trials(), market_model=_market(),
            commercial_plan=CommercialPlan.from_modality("small_molecule"),
            deal_economics=deal,
        )
        return ValuationEngine.from_program(
            program=program, company=_company(),
            mc_params=MonteCarloParams(n_simulations=50, random_seed=0),
        ).run()

    def test_discount_rate_sensitivity_uses_correct_loe_and_deal(self):
        """
        Discount rate sensitivity: engine perturbs rate by ±2pp.
        With a non-trivial deal, the sensitivity values must reflect that deal.
        Verify by manually computing compute_rnpv_full() with the same perturbation
        and the same LOE + deal context.
        """
        deal = DealEconomics(royalty_rate=0.15, cdev_cost_share=0.70)
        loe = dict(AssumptionsLoader.get().loe_erosion_profile("small_molecule"))
        output = self._engine_output(deal)
        dr_sens = next(s for s in output.sensitivities if "Discount" in s.parameter)

        r = _asset().discount_rate  # 0.10
        asset_rate_hi = _asset().model_copy(update={"discount_rate": min(0.50, r + 0.02)})
        asset_rate_lo = _asset().model_copy(update={"discount_rate": max(0.01, r - 0.02)})

        # In the engine: low_rnpv=_rnpv(asset=a_hi), high_rnpv=_rnpv(asset=a_lo)
        expected_low = compute_rnpv_full(
            asset_rate_hi, _trials(), _market(), loe_profile=loe, deal=deal
        ).rnpv_millions
        expected_high = compute_rnpv_full(
            asset_rate_lo, _trials(), _market(), loe_profile=loe, deal=deal
        ).rnpv_millions

        assert dr_sens.low_rnpv == pytest.approx(expected_low, abs=0.01)
        assert dr_sens.high_rnpv == pytest.approx(expected_high, abs=0.01)

    def test_peak_sales_sensitivity_uses_correct_loe_and_deal(self):
        """
        Peak sales sensitivity perturbs TAM ±30%.
        The discount rate, trials, LOE, and deal must remain unchanged.
        Verify by manually computing the high and low values.
        """
        deal = DealEconomics(royalty_rate=0.10)
        loe = dict(AssumptionsLoader.get().loe_erosion_profile("small_molecule"))
        output = self._engine_output(deal)
        ps_sens = next(s for s in output.sensitivities if "Peak Sales" in s.parameter)

        tam = _market().total_addressable_market_millions
        m_lo = _market().model_copy(update={"total_addressable_market_millions": tam * 0.70, "uptake_curve": None})
        m_hi = _market().model_copy(update={"total_addressable_market_millions": tam * 1.30, "uptake_curve": None})

        expected_low = compute_rnpv_full(_asset(), _trials(), m_lo, loe_profile=loe, deal=deal).rnpv_millions
        expected_high = compute_rnpv_full(_asset(), _trials(), m_hi, loe_profile=loe, deal=deal).rnpv_millions

        assert ps_sens.low_rnpv == pytest.approx(expected_low, abs=0.01)
        assert ps_sens.high_rnpv == pytest.approx(expected_high, abs=0.01)

    def test_perturbing_market_does_not_change_deal_terms(self):
        """
        A market perturbation (peak sales low) must produce a result that
        reflects the deal royalty — proving the deal closure is intact.
        """
        deal_with = DealEconomics(royalty_rate=0.20)
        deal_none = DealEconomics()
        out_with = self._engine_output(deal_with)
        out_none = self._engine_output(deal_none)

        ps_with = next(s for s in out_with.sensitivities if "Peak Sales" in s.parameter)
        ps_none = next(s for s in out_none.sensitivities if "Peak Sales" in s.parameter)

        # With 20% royalty, both low and high sensitivity values must be lower
        assert ps_with.low_rnpv < ps_none.low_rnpv
        assert ps_with.high_rnpv < ps_none.high_rnpv

    def test_perturbing_trials_does_not_change_market_or_deal(self):
        """
        A POS perturbation (trials scaled ±20%) must not touch the market or deal.
        Verify by checking that the POS sensitivity delta is proportional to
        what compute_rnpv_full() produces for the same trial perturbation.
        """
        deal = DealEconomics(cdev_cost_share=0.5)
        loe = dict(AssumptionsLoader.get().loe_erosion_profile("small_molecule"))
        output = self._engine_output(deal)
        pos_sens = next(s for s in output.sensitivities if "POS" in s.parameter)

        trials_lo = [t.model_copy(update={"success_probability": min(0.99, t.success_probability * 0.80)}) for t in _trials()]
        trials_hi = [t.model_copy(update={"success_probability": min(0.99, t.success_probability * 1.20)}) for t in _trials()]

        expected_low = compute_rnpv_full(_asset(), trials_lo, _market(), loe_profile=loe, deal=deal).rnpv_millions
        expected_high = compute_rnpv_full(_asset(), trials_hi, _market(), loe_profile=loe, deal=deal).rnpv_millions

        assert pos_sens.low_rnpv == pytest.approx(expected_low, abs=0.01)
        assert pos_sens.high_rnpv == pytest.approx(expected_high, abs=0.01)
