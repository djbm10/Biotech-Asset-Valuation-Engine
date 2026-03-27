"""
Step 2 tests: four-engine architecture.

Covers:
  - ProbabilityModel: parity with old rNPV, timing, prob-reaching sequence
  - RevenueModel: invariants (segment sums, non-negativity), parity
  - CostModel: total == sum of phases, timing, parity with old rNPV
  - RNPVModel: parity with compute_rnpv() pre-refactor snapshot
  - End-to-end regression: ValuationEngine still reproduces locked outputs
"""
from __future__ import annotations

import pytest

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.cost_model import CostModel
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams
from bve.models.probability_model import ProbabilityModel
from bve.models.revenue_model import RevenueModel
from bve.models.rnpv_model import RNPVModel, compute_rnpv
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _asset(discount_rate: float = 0.10, asset_id: str = "TST001") -> Asset:
    return Asset(
        id=asset_id,
        name="Test Asset",
        indication="test indication",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=discount_rate,
    )


def _trials(asset_id: str = "TST001") -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id=asset_id,
            phase=TrialPhase.PHASE_2,
            success_probability=0.40,
            duration_years=2.5,
            cost_millions=75.0,
        ),
        ClinicalTrial(
            asset_id=asset_id,
            phase=TrialPhase.PHASE_3,
            success_probability=0.60,
            duration_years=3.5,
            cost_millions=225.0,
        ),
        ClinicalTrial(
            asset_id=asset_id,
            phase=TrialPhase.NDA_BLA,
            success_probability=0.87,
            duration_years=1.5,
            cost_millions=35.0,
        ),
    ]


def _market_model(asset_id: str = "TST001") -> MarketModel:
    return MarketModel(
        asset_id=asset_id,
        total_addressable_market_millions=2000.0,
        peak_penetration=0.15,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.20,
    )


def _company(asset_id: str = "TST001") -> Company:
    return Company(
        id="CO001",
        name="Test Co",
        ticker="TST",
        cash_millions=200.0,
        shares_outstanding_millions=100.0,
        asset_ids=[asset_id],
    )


# ---------------------------------------------------------------------------
# TestProbabilityModel
# ---------------------------------------------------------------------------

class TestProbabilityModel:
    def test_cumulative_prob_equals_product(self):
        asset = _asset()
        trials = _trials()
        prob = ProbabilityModel.compute(asset, trials)
        expected = 0.40 * 0.60 * 0.87
        assert prob.cumulative_approval_probability == pytest.approx(expected, rel=1e-5)

    def test_years_to_approval_equals_sum_of_durations(self):
        asset = _asset()
        trials = _trials()
        prob = ProbabilityModel.compute(asset, trials)
        expected = 2.5 + 3.5 + 1.5
        assert prob.years_to_approval == pytest.approx(expected, rel=1e-5)

    def test_phases_sorted_by_phase_order(self):
        asset = _asset()
        # Deliberately pass out of order
        trials = list(reversed(_trials()))
        prob = ProbabilityModel.compute(asset, trials)
        phases = [p.phase for p in prob.phases]
        assert phases == ["phase_2", "phase_3", "nda_bla"]

    def test_first_phase_prob_reaching_is_one(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        assert prob.phases[0].prob_reaching == pytest.approx(1.0)

    def test_prob_reaching_decreases_monotonically(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        reaching = [p.prob_reaching for p in prob.phases]
        for i in range(len(reaching) - 1):
            assert reaching[i] >= reaching[i + 1]

    def test_prob_reaching_sequence_correct(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        assert prob.phases[0].prob_reaching == pytest.approx(1.0)
        assert prob.phases[1].prob_reaching == pytest.approx(0.40, rel=1e-5)
        assert prob.phases[2].prob_reaching == pytest.approx(0.40 * 0.60, rel=1e-5)

    def test_phase_timing_windows_contiguous(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        for i in range(len(prob.phases) - 1):
            assert prob.phases[i].year_end == pytest.approx(
                prob.phases[i + 1].year_start, rel=1e-6
            )

    def test_parity_with_old_rnpv_prob(self):
        """cumulative_approval_probability must match old compute_rnpv output."""
        asset = _asset()
        trials = _trials()
        old = compute_rnpv(asset, trials, _market_model())
        new = ProbabilityModel.compute(asset, trials)
        assert new.cumulative_approval_probability == pytest.approx(
            old.cumulative_success_probability, rel=1e-5
        )

    def test_parity_with_old_rnpv_years_to_launch(self):
        asset = _asset()
        trials = _trials()
        old = compute_rnpv(asset, trials, _market_model())
        new = ProbabilityModel.compute(asset, trials)
        assert new.years_to_approval == pytest.approx(old.years_to_launch, rel=1e-4)

    def test_expected_time_to_approval_alias(self):
        prob = ProbabilityModel.compute(_asset(), _trials())
        assert prob.expected_time_to_approval == prob.years_to_approval

    def test_phase_transition_times_keys_and_values(self):
        prob = ProbabilityModel.compute(_asset(), _trials())
        tt = prob.phase_transition_times
        assert set(tt.keys()) == {"phase_2", "phase_3", "nda_bla"}
        assert tt["phase_2"] == pytest.approx(2.5, rel=1e-5)
        assert tt["phase_3"] == pytest.approx(6.0, rel=1e-5)
        assert tt["nda_bla"] == pytest.approx(7.5, rel=1e-5)

    def test_final_transition_time_equals_years_to_approval(self):
        prob = ProbabilityModel.compute(_asset(), _trials())
        tt = prob.phase_transition_times
        last_phase = prob.phases[-1].phase
        assert tt[last_phase] == pytest.approx(prob.years_to_approval, rel=1e-5)

    def test_filters_trials_to_asset(self):
        asset = _asset(asset_id="A1")
        trials = _trials("A1") + _trials("A2")  # two assets
        prob = ProbabilityModel.compute(asset, trials)
        assert all(p.phase in {"phase_2", "phase_3", "nda_bla"} for p in prob.phases)
        assert len(prob.phases) == 3  # only A1 trials


# ---------------------------------------------------------------------------
# TestRevenueModel
# ---------------------------------------------------------------------------

class TestRevenueModel:
    def test_curve_length_equals_patent_life(self):
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        assert len(rev.revenue_by_year) == mm.patent_life_years
        assert len(rev.ebit_by_year) == mm.patent_life_years
        assert len(rev.gross_profit_by_year) == mm.patent_life_years

    def test_revenue_non_negative(self):
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        assert all(r >= 0.0 for r in rev.revenue_by_year)

    def test_ebit_lte_revenue(self):
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        for r, e in zip(rev.revenue_by_year, rev.ebit_by_year):
            assert e <= r + 1e-9, f"EBIT {e} > revenue {r}"

    def test_gross_profit_between_ebit_and_revenue(self):
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        for r, gp, e in zip(rev.revenue_by_year, rev.gross_profit_by_year, rev.ebit_by_year):
            assert e <= gp <= r + 1e-9

    def test_by_segment_sums_to_combined(self):
        """Key invariant: sum of by_segment == revenue_by_year at every year."""
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        for yr_idx in range(mm.patent_life_years):
            seg_sum = sum(
                rev.diagnostics.by_segment[seg][yr_idx]
                for seg in rev.diagnostics.by_segment
            )
            assert seg_sum == pytest.approx(rev.revenue_by_year[yr_idx], rel=1e-9)

    def test_by_segment_geography_sums_to_combined(self):
        """Key invariant: sum of by_segment_geography (all segs, 'global' geo) == combined."""
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        for yr_idx in range(mm.patent_life_years):
            geo_sum = sum(
                rev.diagnostics.by_segment_geography[seg]["global"][yr_idx]
                for seg in rev.diagnostics.by_segment_geography
            )
            assert geo_sum == pytest.approx(rev.diagnostics.combined[yr_idx], rel=1e-9)

    def test_combined_matches_revenue_by_year(self):
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        assert rev.diagnostics.combined == rev.revenue_by_year

    def test_peak_revenue_alias(self):
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        assert rev.peak_revenue_millions == rev.peak_sales_millions

    def test_loe_tail_years_zero_without_profile(self):
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        assert rev.loe_tail_years == 0
        assert rev.total_years == mm.patent_life_years

    def test_peak_sales_positive(self):
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        assert rev.peak_sales_millions > 0

    def test_peak_sales_matches_market_model(self):
        mm = _market_model()
        rev = RevenueModel.compute(mm)
        assert rev.peak_sales_millions == pytest.approx(mm.peak_sales_millions, rel=1e-6)

    def test_lot_segment_invariants(self):
        """With multi-LOT model, by_segment_geography sums to combined for every year."""
        from bve.models.market_model import LineOfTherapySegment
        mm = MarketModel(
            asset_id="TST001",
            lines_of_therapy=[
                LineOfTherapySegment(line="2L", patients_annual=10000,
                                     net_price_per_patient_usd=150000,
                                     peak_penetration=0.20, years_to_peak=5),
                LineOfTherapySegment(line="3L", patients_annual=5000,
                                     net_price_per_patient_usd=150000,
                                     peak_penetration=0.35, years_to_peak=3,
                                     launch_delay_years=1.0),
            ],
        )
        rev = RevenueModel.compute(mm)
        for yr_idx in range(mm.patent_life_years):
            geo_sum = sum(
                rev.diagnostics.by_segment_geography[seg]["global"][yr_idx]
                for seg in rev.diagnostics.by_segment_geography
            )
            assert geo_sum == pytest.approx(rev.diagnostics.combined[yr_idx], rel=1e-9)


# ---------------------------------------------------------------------------
# TestCostModel
# ---------------------------------------------------------------------------

class TestCostModel:
    def test_total_equals_sum_of_phase_weighted_costs(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        cost = CostModel.compute(prob, asset.discount_rate)
        recomputed = sum(pc.pv_cost_weighted for pc in cost.phase_costs)
        assert cost.total_pv_weighted_millions == pytest.approx(recomputed, rel=1e-4)

    def test_first_phase_prob_reaching_is_one(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        cost = CostModel.compute(prob, asset.discount_rate)
        assert cost.phase_costs[0].prob_reaching == pytest.approx(1.0)

    def test_prob_reaching_decreasing(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        cost = CostModel.compute(prob, asset.discount_rate)
        reaching = [pc.prob_reaching for pc in cost.phase_costs]
        for i in range(len(reaching) - 1):
            assert reaching[i] >= reaching[i + 1]

    def test_discounting_reduces_cost_gross(self):
        """pv_cost_gross < nominal cost for phases > 0 years from now."""
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        cost = CostModel.compute(prob, asset.discount_rate)
        # First phase starts at year 0; midpoint at 1.25 yrs — still discounted
        for i, (phase, pc) in enumerate(zip(prob.phases, cost.phase_costs)):
            assert pc.pv_cost_gross <= phase.cost_millions + 1e-9

    def test_parity_with_old_rnpv_costs(self):
        """total_pv_weighted_millions must match old compute_rnpv trial_costs_pv_millions."""
        asset = _asset()
        trials = _trials()
        mm = _market_model()
        old = compute_rnpv(asset, trials, mm)
        prob = ProbabilityModel.compute(asset, trials)
        cost = CostModel.compute(prob, asset.discount_rate)
        assert cost.total_pv_weighted_millions == pytest.approx(
            old.trial_costs_pv_millions, rel=1e-4
        )

    def test_phase_costs_carry_year_start_end(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        cost = CostModel.compute(prob, asset.discount_rate)
        # First phase: year_start=0, year_end=2.5
        assert cost.phase_costs[0].year_start == pytest.approx(0.0)
        assert cost.phase_costs[0].year_end == pytest.approx(2.5)
        # Last phase year_end = total time to approval
        assert cost.phase_costs[-1].year_end == pytest.approx(prob.years_to_approval, rel=1e-5)

    def test_cost_stream_pv_costs_alias(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        cost = CostModel.compute(prob, asset.discount_rate)
        assert cost.pv_costs_millions == cost.total_pv_weighted_millions

    def test_higher_discount_rate_lowers_pv(self):
        asset_lo = _asset(discount_rate=0.05)
        asset_hi = _asset(discount_rate=0.20)
        trials = _trials()
        prob = ProbabilityModel.compute(asset_lo, trials)
        cost_lo = CostModel.compute(prob, asset_lo.discount_rate)
        cost_hi = CostModel.compute(prob, asset_hi.discount_rate)
        assert cost_lo.total_pv_weighted_millions > cost_hi.total_pv_weighted_millions


# ---------------------------------------------------------------------------
# TestRNPVModel
# ---------------------------------------------------------------------------

class TestRNPVModel:
    def _run_new(self, asset=None, trials=None, mm=None):
        a = asset or _asset()
        t = trials or _trials()
        m = mm or _market_model()
        prob = ProbabilityModel.compute(a, t)
        rev = RevenueModel.compute(m)
        cost = CostModel.compute(prob, a.discount_rate)
        return RNPVModel.compute(a, prob, rev, cost)

    def test_rnpv_matches_old_compute_rnpv(self):
        asset = _asset()
        trials = _trials()
        mm = _market_model()
        old = compute_rnpv(asset, trials, mm)
        new = self._run_new(asset, trials, mm)
        assert new.rnpv_millions == pytest.approx(old.rnpv_millions, rel=1e-5)

    def test_gross_revenue_pv_matches(self):
        asset = _asset()
        trials = _trials()
        mm = _market_model()
        old = compute_rnpv(asset, trials, mm)
        new = self._run_new(asset, trials, mm)
        assert new.gross_revenue_pv_millions == pytest.approx(old.gross_revenue_pv_millions, rel=1e-5)

    def test_trial_costs_pv_matches(self):
        asset = _asset()
        trials = _trials()
        mm = _market_model()
        old = compute_rnpv(asset, trials, mm)
        new = self._run_new(asset, trials, mm)
        assert new.trial_costs_pv_millions == pytest.approx(old.trial_costs_pv_millions, rel=1e-4)

    def test_sub_objects_populated(self):
        result = self._run_new()
        assert result.probability_result is not None
        assert result.revenue_stream is not None
        assert result.cost_stream is not None

    def test_phase_breakdown_backward_compat(self):
        result = self._run_new()
        assert len(result.phase_breakdown) == len(_trials())
        for pb in result.phase_breakdown:
            assert pb.phase in {"phase_2", "phase_3", "nda_bla"}
            assert pb.prob_reaching > 0
            assert pb.pv_cost_gross > 0

    def test_higher_pos_raises_rnpv(self):
        asset = _asset()
        t_lo = [t.model_copy(update={"success_probability": t.success_probability * 0.5}) for t in _trials()]
        t_hi = _trials()
        mm = _market_model()
        result_lo = self._run_new(asset, t_lo, mm)
        result_hi = self._run_new(asset, t_hi, mm)
        assert result_hi.rnpv_millions > result_lo.rnpv_millions

    def test_higher_discount_rate_lowers_rnpv(self):
        t = _trials()
        mm = _market_model()
        result_lo = self._run_new(_asset(discount_rate=0.05), t, mm)
        result_hi = self._run_new(_asset(discount_rate=0.20), t, mm)
        assert result_lo.rnpv_millions > result_hi.rnpv_millions

    def test_rnpv_equals_revenue_minus_costs(self):
        result = self._run_new()
        expected = (
            result.probability_adjusted_revenue_pv_millions
            - result.trial_costs_pv_millions
        )
        assert result.rnpv_millions == pytest.approx(expected, rel=1e-5)

    def test_pv_revenue_alias(self):
        result = self._run_new()
        assert result.pv_revenue_millions == result.probability_adjusted_revenue_pv_millions

    def test_pv_costs_alias(self):
        result = self._run_new()
        assert result.pv_costs_millions == result.trial_costs_pv_millions


# ---------------------------------------------------------------------------
# TestRevenueModelInvariantsNonNegativity
# ---------------------------------------------------------------------------

class TestRevenueModelNonNegativity:
    def test_patients_treated_never_exceeds_addressable(self):
        """
        In patient-based mode, revenue / (price × compliance) == patients_treated.
        Penetration is bounded ≤ 1, so patients_treated ≤ addressable_patients.
        """
        mm = MarketModel(
            asset_id="TST001",
            addressable_patients_annual=10_000,
            net_price_per_patient_usd=200_000,
            peak_penetration=0.30,
            years_to_peak=4,
            patent_life_years=12,
        )
        rev = RevenueModel.compute(mm)
        addressable_revenue_cap = (
            mm.addressable_patients_annual
            * mm.net_price_per_patient_usd
            * mm.compliance_rate
            / 1e6
        )
        for r in rev.revenue_by_year:
            assert r <= addressable_revenue_cap + 1e-6


# ---------------------------------------------------------------------------
# TestEndToEndRegression
# ---------------------------------------------------------------------------

class TestEndToEndRegression:
    """
    Lock the engine outputs to values matching the pre-Step 2 snapshot.
    Snapshot from MEMORY.md: rNPV=118.72, POS=0.55 (seed=0, n=1000).
    """

    def _build_engine(self) -> ValuationEngine:
        # Exact same setup as TestBackwardCompatSnapshot._make_base_setup() in test_phase1.py
        # so that snapshot values are reproducible. Sprint 9: 81.01 rNPV, ~85.96 MC mean with LOE.
        asset = Asset(
            id="snap-001",
            name="SNAP-001",
            indication="Snapshot Test",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            discount_rate=0.10,
        )
        trials = [
            ClinicalTrial(
                asset_id="snap-001",
                phase=TrialPhase.PHASE_2,
                success_probability=0.37,
                duration_years=2.5,
                cost_millions=80.0,
                enrollment=150,
            ),
            ClinicalTrial(
                asset_id="snap-001",
                phase=TrialPhase.PHASE_3,
                success_probability=0.55,
                duration_years=3.5,
                cost_millions=250.0,
                enrollment=450,
            ),
            ClinicalTrial(
                asset_id="snap-001",
                phase=TrialPhase.NDA_BLA,
                success_probability=0.87,
                duration_years=1.5,
                cost_millions=35.0,
            ),
        ]
        market_model = MarketModel(
            asset_id="snap-001",
            total_addressable_market_millions=8_000.0,
            peak_penetration=0.12,
            years_to_peak=5,
            patent_life_years=12,
            cogs_rate=0.18,
            sgna_rate_launch=0.40,
            sgna_rate_mature=0.20,
        )
        company = Company(
            id="SNAPCO",
            name="Snapshot Co",
            ticker="SNAP",
            cash_millions=100.0,
            shares_outstanding_millions=100.0,
            asset_ids=["snap-001"],
        )
        return ValuationEngine(
            asset=asset,
            company=company,
            trials=trials,
            market_model=market_model,
            mc_params=MonteCarloParams(n_simulations=1000, random_seed=0),
        )

    def test_rnpv_snapshot(self):
        # Sprint 9.12: updated to 83.0 after 0dp rounding (was 83.13 pre-9.12; was 81.01 pre-9.10)
        output = self._build_engine().run()
        assert output.rnpv.rnpv_millions == pytest.approx(83.0, abs=0.5)

    def test_pos_snapshot(self):
        output = self._build_engine().run()
        expected_pos = 0.37 * 0.55 * 0.87  # matches _build_engine() phase 3 POS=0.55
        assert output.rnpv.cumulative_success_probability == pytest.approx(expected_pos, rel=1e-4)

    def test_mc_snapshot(self):
        # Sprint 9: updated to 85.96 after UFCF/tax fix (was 144.57 with LOE, 123.75 no-LOE).
        output = self._build_engine().run()
        assert output.monte_carlo.mean_millions == pytest.approx(85.96, abs=5.0)

    def test_sub_objects_in_output(self):
        output = self._build_engine().run()
        assert output.rnpv.probability_result is not None
        assert output.rnpv.revenue_stream is not None
        assert output.rnpv.cost_stream is not None

    def test_engine_produces_valuation_output(self):
        output = self._build_engine().run()
        assert output.nav_millions > 0
        assert output.nav_per_share > 0
        assert len(output.sensitivities) == 8  # Sprint 9.13: expanded to 8 (added G2N rate + competition entries)
        assert output.monte_carlo.n_simulations == 1000

    def test_intermediate_results_inspectable(self):
        """Intermediate ProbabilityResult, RevenueStream, CostStream are accessible."""
        output = self._build_engine().run()
        prob = output.rnpv.probability_result
        rev = output.rnpv.revenue_stream
        cost = output.rnpv.cost_stream

        # ProbabilityResult
        assert len(prob.phases) == 3
        assert prob.years_to_approval == pytest.approx(7.5, rel=1e-4)

        # RevenueStream (ValuationEngine applies LOE → total_years = 15 for small_molecule)
        assert len(rev.ebit_by_year) == rev.total_years
        assert all(e >= 0 for e in rev.ebit_by_year)

        # CostStream
        assert len(cost.phase_costs) == 3
        assert cost.total_pv_weighted_millions > 0

    def test_rNPV_equals_rev_minus_cost_in_output(self):
        # Sprint 9.12: each field is independently rounded (rnpv→0dp, rev→0dp, costs→1dp),
        # so the accounting identity holds only within rounding tolerance (≤2.0).
        output = self._build_engine().run()
        r = output.rnpv
        expected = r.probability_adjusted_revenue_pv_millions - r.trial_costs_pv_millions
        assert r.rnpv_millions == pytest.approx(expected, abs=2.0)
