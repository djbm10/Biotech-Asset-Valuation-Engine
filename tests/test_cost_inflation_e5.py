"""
Sprint E5 — cost_inflation_rate on DrugAssetProgram / CostModel.

Tests cover:
  1. DrugAssetProgram: field default, validation, build() factory
  2. CostModel: zero inflation is bit-for-bit backward-compatible
  3. CostModel: positive inflation raises PV costs monotonically
  4. CostModel: exact arithmetic (Fisher equation: (1+infl)^t / (1+r)^t)
  5. CostModel: interaction with ANNUAL_UNIFORM spend profile
  6. ValuationEngine: inflation reduces rNPV end-to-end (from_program path)
  7. Backward compatibility: no cost_inflation_rate → identical to pre-E5
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, SpendProfile
from bve.models.cost_model import CostModel
from bve.models.drug_asset_program import DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.models.probability_model import ProbabilityModel
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset(ta: str = "oncology") -> Asset:
    return Asset(
        id=f"e5-{ta}",
        name="E5 Test",
        indication="Test",
        therapeutic_area=ta,
        stage="phase_3",
        modality="small_molecule",
        discount_rate=0.10,
    )


def _company() -> Company:
    return Company(
        id="e5-co",
        name="E5 Co",
        cash_millions=100.0,
        shares_outstanding_millions=50.0,
    )


def _market(ta: str = "oncology") -> MarketModel:
    return MarketModel(
        asset_id=f"e5-{ta}",
        therapeutic_area=ta,
        total_addressable_market_millions=500.0,
        peak_penetration=0.08,
        patent_life_years=10,
    )


def _trials(ta: str = "oncology") -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id=f"e5-{ta}",
            phase="phase_2",
            success_probability=0.45,
            duration_years=2.0,
            cost_millions=70.0,
            cost_source="override",
        ),
        ClinicalTrial(
            asset_id=f"e5-{ta}",
            phase="phase_3",
            success_probability=0.60,
            duration_years=3.0,
            cost_millions=180.0,
            cost_source="override",
        ),
    ]


def _prob(ta: str = "oncology"):
    return ProbabilityModel.compute(_asset(ta), _trials(ta))


# ---------------------------------------------------------------------------
# 1. DrugAssetProgram field
# ---------------------------------------------------------------------------

class TestDrugAssetProgramInflationField:
    def test_default_is_zero(self):
        prog = DrugAssetProgram.build(_asset(), _trials(), _market())
        assert prog.cost_inflation_rate == 0.0

    def test_positive_rate_stored(self):
        prog = DrugAssetProgram.build(
            _asset(), _trials(), _market(), cost_inflation_rate=0.04
        )
        assert prog.cost_inflation_rate == pytest.approx(0.04)

    def test_negative_rate_rejected(self):
        with pytest.raises(ValidationError):
            DrugAssetProgram.build(
                _asset(), _trials(), _market(), cost_inflation_rate=-0.01
            )

    def test_program_is_frozen(self):
        prog = DrugAssetProgram.build(
            _asset(), _trials(), _market(), cost_inflation_rate=0.03
        )
        with pytest.raises(Exception):
            prog.cost_inflation_rate = 0.05  # type: ignore

    def test_direct_construction(self):
        prog = DrugAssetProgram(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
            cost_inflation_rate=0.05,
        )
        assert prog.cost_inflation_rate == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# 2. CostModel: zero inflation is backward-compatible
# ---------------------------------------------------------------------------

class TestZeroInflationBackwardCompat:
    def test_zero_matches_no_kwarg(self):
        prob = _prob()
        cs_default = CostModel.compute(prob, 0.10)
        cs_zero = CostModel.compute(prob, 0.10, cost_inflation_rate=0.0)
        assert cs_default.total_pv_weighted_millions == pytest.approx(
            cs_zero.total_pv_weighted_millions, rel=1e-9
        )

    def test_zero_phase_costs_unchanged(self):
        prob = _prob()
        cs_default = CostModel.compute(prob, 0.10)
        cs_zero = CostModel.compute(prob, 0.10, cost_inflation_rate=0.0)
        for pc_d, pc_z in zip(cs_default.phase_costs, cs_zero.phase_costs):
            assert pc_d.pv_cost_gross == pytest.approx(pc_z.pv_cost_gross, rel=1e-9)


# ---------------------------------------------------------------------------
# 3. CostModel: positive inflation raises PV costs
# ---------------------------------------------------------------------------

class TestInflationRaisesCosts:
    def test_inflation_increases_total_pv(self):
        prob = _prob()
        cs_base = CostModel.compute(prob, 0.10)
        cs_infl = CostModel.compute(prob, 0.10, cost_inflation_rate=0.03)
        assert cs_infl.total_pv_weighted_millions > cs_base.total_pv_weighted_millions

    def test_higher_inflation_higher_cost(self):
        prob = _prob()
        cs_2 = CostModel.compute(prob, 0.10, cost_inflation_rate=0.02)
        cs_5 = CostModel.compute(prob, 0.10, cost_inflation_rate=0.05)
        assert cs_5.total_pv_weighted_millions > cs_2.total_pv_weighted_millions

    def test_later_phase_more_inflated_than_earlier(self):
        """
        P3 starts at year 2.0 → longer horizon → inflation has larger effect on P3
        than P2 (which starts at 0.0).
        """
        prob = _prob()
        r = 0.10
        inflation = 0.04

        cs_base = CostModel.compute(prob, r, cost_inflation_rate=0.0)
        cs_infl = CostModel.compute(prob, r, cost_inflation_rate=inflation)

        p2_base = next(pc for pc in cs_base.phase_costs if pc.phase == "phase_2")
        p3_base = next(pc for pc in cs_base.phase_costs if pc.phase == "phase_3")
        p2_infl = next(pc for pc in cs_infl.phase_costs if pc.phase == "phase_2")
        p3_infl = next(pc for pc in cs_infl.phase_costs if pc.phase == "phase_3")

        # Ratio of inflated/base PV gross
        ratio_p2 = p2_infl.pv_cost_gross / p2_base.pv_cost_gross
        ratio_p3 = p3_infl.pv_cost_gross / p3_base.pv_cost_gross
        # P3 midpoint is further out → inflation lifts it more
        assert ratio_p3 > ratio_p2


# ---------------------------------------------------------------------------
# 4. CostModel: exact arithmetic
# ---------------------------------------------------------------------------

class TestInflationExactArithmetic:
    def test_uniform_single_phase_exact_pv(self):
        """
        Single P3, cost=100, duration=3, year_start=0.
        mid=1.5, r=0.10, inflation=0.04.
        PV_gross = 100 * (1.04/1.10)^1.5
        """
        asset = _asset()
        trial = ClinicalTrial(
            asset_id="e5-oncology",
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=100.0,
        )
        prob = ProbabilityModel.compute(asset, [trial])
        r, inflation = 0.10, 0.04
        cs = CostModel.compute(prob, r, cost_inflation_rate=inflation)
        mid = 1.5
        expected_pv_gross = 100.0 * (1.0 + inflation) ** mid / (1.0 + r) ** mid
        assert cs.phase_costs[0].pv_cost_gross == pytest.approx(expected_pv_gross, abs=0.02)

    def test_inflation_equals_discount_rate_means_no_discounting_effect(self):
        """
        When inflation == discount_rate, (1+infl)^t / (1+r)^t == 1.
        PV_gross == cost_millions (face value).
        """
        asset = _asset()
        trial = ClinicalTrial(
            asset_id="e5-oncology",
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=100.0,
        )
        prob = ProbabilityModel.compute(asset, [trial])
        # r == inflation → factor cancels
        cs = CostModel.compute(prob, 0.10, cost_inflation_rate=0.10)
        assert cs.phase_costs[0].pv_cost_gross == pytest.approx(100.0, abs=0.01)

    def test_probability_weighting_unchanged_by_inflation(self):
        """Inflation scales pv_cost_gross; pv_cost_weighted = gross × prob_reaching."""
        prob = _prob()
        cs = CostModel.compute(prob, 0.10, cost_inflation_rate=0.03)
        for pc in cs.phase_costs:
            assert pc.pv_cost_weighted == pytest.approx(
                pc.pv_cost_gross * pc.prob_reaching, abs=0.01
            )


# ---------------------------------------------------------------------------
# 5. Interaction with ANNUAL_UNIFORM spend profile
# ---------------------------------------------------------------------------

class TestInflationWithAnnualUniform:
    def test_annual_uniform_with_inflation_higher_than_uniform_with_inflation(self):
        """
        With both inflation and ANNUAL_UNIFORM, PV > UNIFORM+inflation
        (Jensen's inequality on the inflated-but-then-discounted factor).
        """
        asset = _asset()
        trial_u = ClinicalTrial(
            asset_id="e5-oncology",
            phase="phase_3",
            success_probability=0.55,
            duration_years=4.0,
            cost_millions=200.0,
            spend_profile=SpendProfile.UNIFORM,
        )
        trial_a = ClinicalTrial(
            asset_id="e5-oncology",
            phase="phase_3",
            success_probability=0.55,
            duration_years=4.0,
            cost_millions=200.0,
            spend_profile=SpendProfile.ANNUAL_UNIFORM,
        )
        prob_u = ProbabilityModel.compute(asset, [trial_u])
        prob_a = ProbabilityModel.compute(asset, [trial_a])
        r, inflation = 0.10, 0.04
        cs_u = CostModel.compute(prob_u, r, cost_inflation_rate=inflation)
        cs_a = CostModel.compute(prob_a, r, cost_inflation_rate=inflation)
        # ANNUAL_UNIFORM > UNIFORM (Jensen convexity holds with inflation too)
        assert cs_a.phase_costs[0].pv_cost_gross > cs_u.phase_costs[0].pv_cost_gross

    def test_zero_inflation_annual_uniform_unchanged(self):
        """ANNUAL_UNIFORM with zero inflation is unaffected by the inflation param."""
        asset = _asset()
        trial = ClinicalTrial(
            asset_id="e5-oncology",
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=150.0,
            spend_profile=SpendProfile.ANNUAL_UNIFORM,
        )
        prob = ProbabilityModel.compute(asset, [trial])
        cs_base = CostModel.compute(prob, 0.10)
        cs_zero = CostModel.compute(prob, 0.10, cost_inflation_rate=0.0)
        assert cs_base.phase_costs[0].pv_cost_gross == pytest.approx(
            cs_zero.phase_costs[0].pv_cost_gross, rel=1e-9
        )


# ---------------------------------------------------------------------------
# 6. ValuationEngine end-to-end
# ---------------------------------------------------------------------------

class TestValuationEngineInflation:
    def _run(self, inflation: float) -> float:
        prog = DrugAssetProgram.build(
            _asset(), _trials(), _market(), cost_inflation_rate=inflation
        )
        engine = ValuationEngine.from_program(prog, _company())
        return engine.run().rnpv.rnpv_millions

    def test_no_inflation_baseline_runs(self):
        rnpv = self._run(0.0)
        assert isinstance(rnpv, float)

    def test_inflation_reduces_rnpv(self):
        """Higher costs from inflation reduce rNPV."""
        base = self._run(0.0)
        inflated = self._run(0.04)
        assert inflated < base

    def test_higher_inflation_lower_rnpv(self):
        rnpv_2 = self._run(0.02)
        rnpv_5 = self._run(0.05)
        assert rnpv_2 > rnpv_5

    def test_zero_inflation_equals_no_kwarg(self):
        """from_program with cost_inflation_rate=0.0 == default program."""
        prog_default = DrugAssetProgram.build(_asset(), _trials(), _market())
        prog_zero = DrugAssetProgram.build(
            _asset(), _trials(), _market(), cost_inflation_rate=0.0
        )
        rnpv_default = ValuationEngine.from_program(prog_default, _company()).run().rnpv.rnpv_millions
        rnpv_zero = ValuationEngine.from_program(prog_zero, _company()).run().rnpv.rnpv_millions
        assert rnpv_default == pytest.approx(rnpv_zero, rel=1e-6)


# ---------------------------------------------------------------------------
# 7. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_program_without_inflation_is_identical(self):
        """Programs constructed without cost_inflation_rate are backward-compatible."""
        prog = DrugAssetProgram.build(_asset(), _trials(), _market())
        assert prog.cost_inflation_rate == 0.0

    def test_cost_model_without_kwarg_is_identical(self):
        """CostModel.compute() without cost_inflation_rate kwarg is identical to rate=0.0."""
        prob = _prob()
        old = CostModel.compute(prob, 0.10)
        new = CostModel.compute(prob, 0.10, cost_inflation_rate=0.0)
        assert old.total_pv_weighted_millions == pytest.approx(
            new.total_pv_weighted_millions, rel=1e-9
        )
