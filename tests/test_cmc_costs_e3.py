"""
Sprint E3 — CMCCosts model and CostModel integration.

Tests cover:
  1. CMCCosts model: construction, total_millions, validation
  2. _compute_cmc_pv: discount year and probability weight for each timing mode
  3. CostModel.compute integration: CMC PV in CostStream
  4. DrugAssetProgram: cmc_costs field
  5. ValuationEngine: CMC costs reduce rNPV end-to-end (from_program path)
  6. Backward compatibility: no cmc_costs → zero CMC PV, identical to pre-E3
"""
from __future__ import annotations


import pytest
from pydantic import ValidationError

from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial
from bve.models.cmc_costs import CMCCosts, CMCTimingMode
from bve.models.cost_model import CostModel, _compute_cmc_pv
from bve.models.deal_economics import DealEconomics
from bve.models.drug_asset_program import DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.models.probability_model import ProbabilityModel
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset(ta: str = "oncology") -> Asset:
    return Asset(
        id=f"e3-{ta}",
        name="E3 Test",
        indication="Test",
        therapeutic_area=ta,
        stage="phase_3",
        modality="small_molecule",
        discount_rate=0.10,
    )


def _company() -> Company:
    return Company(
        id="e3-co",
        name="E3 Co",
        cash_millions=150.0,
        shares_outstanding_millions=40.0,
    )


def _market(ta: str = "oncology") -> MarketModel:
    return MarketModel(
        asset_id=f"e3-{ta}",
        therapeutic_area=ta,
        total_addressable_market_millions=600.0,
        peak_penetration=0.10,
        patent_life_years=10,
    )


def _trials(ta: str = "oncology") -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id=f"e3-{ta}",
            phase="phase_2",
            success_probability=0.40,
            duration_years=2.5,
            cost_millions=60.0,
            cost_source="override",
        ),
        ClinicalTrial(
            asset_id=f"e3-{ta}",
            phase="phase_3",
            success_probability=0.60,
            duration_years=3.5,
            cost_millions=200.0,
            cost_source="override",
        ),
        ClinicalTrial(
            asset_id=f"e3-{ta}",
            phase="nda_bla",
            success_probability=0.90,
            duration_years=1.0,
            cost_millions=30.0,
            cost_source="override",
        ),
    ]


def _prob(ta: str = "oncology"):
    return ProbabilityModel.compute(_asset(ta), _trials(ta))


# ---------------------------------------------------------------------------
# 1. CMCCosts model
# ---------------------------------------------------------------------------

class TestCMCCostsModel:
    def test_all_defaults_zero(self):
        cmc = CMCCosts()
        assert cmc.total_millions == 0.0

    def test_total_is_sum_of_components(self):
        cmc = CMCCosts(
            api_development_millions=10.0,
            formulation_millions=5.0,
            manufacturing_scale_up_millions=30.0,
            regulatory_cmc_millions=8.0,
        )
        assert cmc.total_millions == pytest.approx(53.0, rel=1e-6)

    def test_default_timing_mode(self):
        assert CMCCosts().timing_mode == CMCTimingMode.PARALLEL_TO_PHASE_3

    def test_custom_year_required_for_custom_mode(self):
        with pytest.raises(ValidationError, match="custom_year"):
            CMCCosts(
                manufacturing_scale_up_millions=50.0,
                timing_mode=CMCTimingMode.CUSTOM_YEAR,
                custom_year=None,
            )

    def test_custom_year_ok_with_custom_mode(self):
        cmc = CMCCosts(
            manufacturing_scale_up_millions=50.0,
            timing_mode=CMCTimingMode.CUSTOM_YEAR,
            custom_year=2.0,
        )
        assert cmc.custom_year == 2.0

    def test_negative_component_rejected(self):
        with pytest.raises(ValidationError):
            CMCCosts(api_development_millions=-5.0)

    def test_frozen_model(self):
        cmc = CMCCosts(api_development_millions=10.0)
        with pytest.raises(Exception):
            cmc.api_development_millions = 20.0  # type: ignore

    def test_all_timing_modes_constructable(self):
        for mode in CMCTimingMode:
            if mode == CMCTimingMode.CUSTOM_YEAR:
                cmc = CMCCosts(timing_mode=mode, custom_year=3.0)
            else:
                cmc = CMCCosts(timing_mode=mode)
            assert cmc.timing_mode == mode


# ---------------------------------------------------------------------------
# 2. _compute_cmc_pv — discount year and probability weight
# ---------------------------------------------------------------------------

class TestComputeCMCPV:
    """Tests for the _compute_cmc_pv helper in cost_model.py."""

    def test_zero_cost_returns_zero(self):
        prob = _prob()
        cmc = CMCCosts()  # all zeros
        assert _compute_cmc_pv(cmc, prob, 0.10) == 0.0

    def test_parallel_phase3_discount_year_is_p3_midpoint(self):
        """PV with PARALLEL_TO_PHASE_3 uses Phase 3 midpoint for discounting."""
        prob = _prob()
        p3 = next(p for p in prob.phases if p.phase == "phase_3")
        expected_year = (p3.year_start + p3.year_end) / 2.0
        r = 0.10
        cmc = CMCCosts(manufacturing_scale_up_millions=100.0,
                       timing_mode=CMCTimingMode.PARALLEL_TO_PHASE_3)

        pv = _compute_cmc_pv(cmc, prob, r)
        expected_pv = 100.0 / (1 + r) ** expected_year * p3.prob_reaching
        assert pv == pytest.approx(expected_pv, abs=0.02)

    def test_post_phase2_discount_year_is_p2_year_end(self):
        """POST_PHASE_2 discounts at Phase 2 year_end."""
        prob = _prob()
        p2 = next(p for p in prob.phases if p.phase == "phase_2")
        p3 = next(p for p in prob.phases if p.phase == "phase_3")
        r = 0.10
        cmc = CMCCosts(manufacturing_scale_up_millions=80.0,
                       timing_mode=CMCTimingMode.POST_PHASE_2)

        pv = _compute_cmc_pv(cmc, prob, r)
        expected_pv = 80.0 / (1 + r) ** p2.year_end * p3.prob_reaching
        assert pv == pytest.approx(expected_pv, abs=0.02)

    def test_pre_phase3_start_discount_year_is_p3_year_start(self):
        """PRE_PHASE_3_START discounts at Phase 3 year_start."""
        prob = _prob()
        p3 = next(p for p in prob.phases if p.phase == "phase_3")
        r = 0.10
        cmc = CMCCosts(manufacturing_scale_up_millions=60.0,
                       timing_mode=CMCTimingMode.PRE_PHASE_3_START)

        pv = _compute_cmc_pv(cmc, prob, r)
        expected_pv = 60.0 / (1 + r) ** p3.year_start * p3.prob_reaching
        assert pv == pytest.approx(expected_pv, rel=1e-4)

    def test_custom_year_discounts_at_specified_year(self):
        prob = _prob()
        p3 = next(p for p in prob.phases if p.phase == "phase_3")
        r = 0.10
        custom = 4.0
        cmc = CMCCosts(manufacturing_scale_up_millions=50.0,
                       timing_mode=CMCTimingMode.CUSTOM_YEAR,
                       custom_year=custom)

        pv = _compute_cmc_pv(cmc, prob, r)
        expected_pv = 50.0 / (1 + r) ** custom * p3.prob_reaching
        assert pv == pytest.approx(expected_pv, rel=1e-4)

    def test_higher_discount_rate_lower_pv(self):
        cmc = CMCCosts(manufacturing_scale_up_millions=100.0)
        prob = _prob()
        pv_lo = _compute_cmc_pv(cmc, prob, 0.05)
        pv_hi = _compute_cmc_pv(cmc, prob, 0.20)
        assert pv_lo > pv_hi

    def test_parallel_earlier_than_post_phase2(self):
        """
        For a Phase 2 → Phase 3 program, PARALLEL_TO_PHASE_3 occurs later than
        POST_PHASE_2, so its PV (discounted at a later year) should be lower.
        """
        cmc_parallel = CMCCosts(manufacturing_scale_up_millions=100.0,
                                timing_mode=CMCTimingMode.PARALLEL_TO_PHASE_3)
        cmc_post2 = CMCCosts(manufacturing_scale_up_millions=100.0,
                             timing_mode=CMCTimingMode.POST_PHASE_2)
        prob = _prob()
        r = 0.10
        pv_parallel = _compute_cmc_pv(cmc_parallel, prob, r)
        pv_post2 = _compute_cmc_pv(cmc_post2, prob, r)
        # POST_PHASE_2 is discounted to an earlier year → higher PV
        assert pv_post2 > pv_parallel


# ---------------------------------------------------------------------------
# 3. CostModel.compute integration
# ---------------------------------------------------------------------------

class TestCostModelCMCIntegration:
    def test_no_cmc_backwards_compatible(self):
        """cmc_costs=None produces zero cmc_pv_millions and identical total."""
        prob = _prob()
        cost_no_cmc = CostModel.compute(prob, 0.10)
        cost_with_none = CostModel.compute(prob, 0.10, cmc_costs=None)
        assert cost_no_cmc.cmc_pv_millions == 0.0
        assert cost_with_none.cmc_pv_millions == 0.0
        assert cost_no_cmc.total_pv_weighted_millions == pytest.approx(
            cost_with_none.total_pv_weighted_millions, rel=1e-6
        )

    def test_cmc_pv_in_cost_stream(self):
        """Non-zero CMC costs appear in cmc_pv_millions."""
        prob = _prob()
        cmc = CMCCosts(manufacturing_scale_up_millions=100.0)
        cost = CostModel.compute(prob, 0.10, cmc_costs=cmc)
        assert cost.cmc_pv_millions > 0.0

    def test_cmc_increases_total_cost(self):
        """Adding CMC costs raises total_pv_weighted_millions."""
        prob = _prob()
        base = CostModel.compute(prob, 0.10)
        with_cmc = CostModel.compute(prob, 0.10,
                                     cmc_costs=CMCCosts(manufacturing_scale_up_millions=100.0))
        assert with_cmc.total_pv_weighted_millions > base.total_pv_weighted_millions

    def test_total_includes_cmc_correctly(self):
        """total = trial_rd + milestones + upfront + post_approval + cmc."""
        prob = _prob()
        cmc = CMCCosts(manufacturing_scale_up_millions=80.0)
        cost = CostModel.compute(prob, 0.10, cmc_costs=cmc)
        expected_total = (
            cost.trial_rd_pv_millions
            + cost.milestone_costs_pv_millions
            + cost.upfront_cost_millions
            + cost.post_approval_rd_pv_millions
            + cost.cmc_pv_millions
        )
        assert cost.total_pv_weighted_millions == pytest.approx(expected_total, rel=1e-4)

    def test_zero_total_cmc_has_zero_pv(self):
        """CMCCosts with all zeros contributes nothing."""
        prob = _prob()
        cost = CostModel.compute(prob, 0.10, cmc_costs=CMCCosts())
        assert cost.cmc_pv_millions == 0.0

    def test_cmc_pv_is_probability_weighted(self):
        """CMC PV should be less than the nominal cost (probability discounted)."""
        prob = _prob()
        nominal = 200.0
        cmc = CMCCosts(manufacturing_scale_up_millions=nominal)
        cost = CostModel.compute(prob, 0.0, cmc_costs=cmc)
        # r=0: only probability weighting applies
        assert cost.cmc_pv_millions < nominal


# ---------------------------------------------------------------------------
# 4. DrugAssetProgram
# ---------------------------------------------------------------------------

class TestDrugAssetProgramCMC:
    def test_cmc_costs_defaults_to_none(self):
        asset = _asset()
        prog = DrugAssetProgram.build(asset, _trials(), _market())
        assert prog.cmc_costs is None

    def test_cmc_costs_stored_on_program(self):
        asset = _asset()
        cmc = CMCCosts(manufacturing_scale_up_millions=50.0)
        prog = DrugAssetProgram.build(asset, _trials(), _market(), cmc_costs=cmc)
        assert prog.cmc_costs is cmc

    def test_program_is_frozen(self):
        asset = _asset()
        cmc = CMCCosts(manufacturing_scale_up_millions=50.0)
        prog = DrugAssetProgram.build(asset, _trials(), _market(), cmc_costs=cmc)
        with pytest.raises(Exception):
            prog.cmc_costs = None  # type: ignore


# ---------------------------------------------------------------------------
# 5. ValuationEngine end-to-end (from_program path)
# ---------------------------------------------------------------------------

class TestValuationEngineCMC:
    def _run(self, cmc: CMCCosts | None) -> float:
        asset = _asset()
        prog = DrugAssetProgram.build(asset, _trials(), _market(), cmc_costs=cmc)
        engine = ValuationEngine.from_program(prog, _company())
        return engine.run().rnpv.rnpv_millions

    def test_no_cmc_baseline_runs(self):
        rnpv = self._run(None)
        assert isinstance(rnpv, float)

    def test_cmc_reduces_rnpv(self):
        """Adding CMC costs lowers rNPV (more costs → less value)."""
        base = self._run(None)
        with_cmc = self._run(CMCCosts(manufacturing_scale_up_millions=150.0))
        assert with_cmc < base

    def test_larger_cmc_lowers_rnpv_more(self):
        rnpv_small = self._run(CMCCosts(manufacturing_scale_up_millions=50.0))
        rnpv_large = self._run(CMCCosts(manufacturing_scale_up_millions=200.0))
        assert rnpv_small > rnpv_large

    def test_zero_cmc_equals_no_cmc(self):
        """CMCCosts with all zero components = no CMC costs."""
        base = self._run(None)
        zero = self._run(CMCCosts())
        assert base == pytest.approx(zero, rel=1e-6)


# ---------------------------------------------------------------------------
# 6. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_cost_model_no_cmc_kwarg_identical(self):
        """CostModel.compute() without cmc_costs kwarg = no CMC cost (pre-E3 behavior)."""
        prob = _prob()
        old_style = CostModel.compute(prob, 0.10, DealEconomics(), 0.0)
        new_style = CostModel.compute(prob, 0.10, DealEconomics(), 0.0, cmc_costs=None)
        assert old_style.total_pv_weighted_millions == pytest.approx(
            new_style.total_pv_weighted_millions, rel=1e-6
        )

    def test_cost_stream_cmc_pv_default_is_zero(self):
        prob = _prob()
        cost = CostModel.compute(prob, 0.10)
        assert cost.cmc_pv_millions == 0.0
