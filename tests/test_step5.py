"""
Step 5 tests: DealEconomics, Milestone, and deal-aware engine integration.

Structure
---------
TestDealEconomicsDefaults        — zero-effect defaults, has_deal_terms sentinel
TestMilestone                    — construction, field validation
TestMilestonePV                  — probability-weighted PV for each trigger type
TestCostModelWithDeal            — cdev_cost_share, payable milestones, upfront cost,
                                   backward compat (deal=None == deal=DealEconomics())
TestRNPVModelWithDeal            — royalty stacking, receivable milestones, upfront receipts,
                                   boundary (RevenueModel untouched)
TestDealBoundary                 — deal economics never enters RevenueModel
TestDrugAssetProgramDeal         — deal_economics field on container
TestValuationEngineWithDeal      — end-to-end: deal reduces/adds to rNPV correctly
TestBackwardCompatWithDeal       — compute_rnpv() wrapper unchanged; no deal applied there
"""
from __future__ import annotations

import pytest

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.cost_model import CostModel
from bve.models.deal_economics import (
    DealEconomics,
    Milestone,
    MilestoneDirection,
    MilestoneTrigger,
    milestone_pv,
)
from bve.models.drug_asset_program import DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams
from bve.models.probability_model import ProbabilityModel
from bve.models.revenue_model import RevenueModel
from bve.models.rnpv_model import RNPVModel, compute_rnpv
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ASSET_ID = "DE001"


def _asset(royalty_rate: float = 0.0) -> Asset:
    return Asset(
        id=_ASSET_ID,
        name="Deal Test Asset",
        indication="test indication",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.10,
        royalty_rate=royalty_rate,
    )


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id=_ASSET_ID,
            phase=TrialPhase.PHASE_2,
            success_probability=0.37,
            duration_years=2.5,
            cost_millions=80.0,
        ),
        ClinicalTrial(
            asset_id=_ASSET_ID,
            phase=TrialPhase.PHASE_3,
            success_probability=0.55,
            duration_years=3.5,
            cost_millions=250.0,
        ),
        ClinicalTrial(
            asset_id=_ASSET_ID,
            phase=TrialPhase.NDA_BLA,
            success_probability=0.87,
            duration_years=1.5,
            cost_millions=35.0,
        ),
    ]


def _market() -> MarketModel:
    return MarketModel(
        asset_id=_ASSET_ID,
        total_addressable_market_millions=8000.0,
        peak_penetration=0.12,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.20,
    )


def _company() -> Company:
    return Company(
        id="CO_DE",
        name="Deal Co",
        ticker="DCO",
        cash_millions=100.0,
        shares_outstanding_millions=50.0,
        asset_ids=[_ASSET_ID],
    )


def _prob() -> "ProbabilityResult":
    return ProbabilityModel.compute(_asset(), _trials())


# ---------------------------------------------------------------------------
# TestDealEconomicsDefaults
# ---------------------------------------------------------------------------

class TestDealEconomicsDefaults:
    def test_zero_cost_defaults(self):
        d = DealEconomics()
        assert d.upfront_cost_millions == 0.0
        assert d.upfront_receipt_millions == 0.0
        assert d.royalty_rate == 0.0
        assert d.cdev_cost_share == 1.0
        assert d.milestones == []

    def test_has_deal_terms_false_for_defaults(self):
        assert not DealEconomics().has_deal_terms

    def test_has_deal_terms_true_for_royalty(self):
        assert DealEconomics(royalty_rate=0.05).has_deal_terms

    def test_has_deal_terms_true_for_cdev_share(self):
        assert DealEconomics(cdev_cost_share=0.5).has_deal_terms

    def test_has_deal_terms_true_for_upfront(self):
        assert DealEconomics(upfront_cost_millions=50.0).has_deal_terms

    def test_has_deal_terms_true_for_milestone(self):
        m = Milestone(
            description="P3 start",
            amount_millions=25.0,
            trigger=MilestoneTrigger.PHASE_START,
            trigger_phase="phase_3",
        )
        assert DealEconomics(milestones=[m]).has_deal_terms

    def test_payable_milestones_filter(self):
        pay = Milestone(description="pay", amount_millions=10.0, trigger=MilestoneTrigger.APPROVAL, direction=MilestoneDirection.PAYABLE)
        recv = Milestone(description="recv", amount_millions=20.0, trigger=MilestoneTrigger.APPROVAL, direction=MilestoneDirection.RECEIVABLE)
        d = DealEconomics(milestones=[pay, recv])
        assert len(d.payable_milestones) == 1
        assert len(d.receivable_milestones) == 1

    def test_royalty_rate_bounds(self):
        with pytest.raises(Exception):
            DealEconomics(royalty_rate=1.5)
        with pytest.raises(Exception):
            DealEconomics(royalty_rate=-0.1)

    def test_cdev_cost_share_bounds(self):
        with pytest.raises(Exception):
            DealEconomics(cdev_cost_share=0.0)
        with pytest.raises(Exception):
            DealEconomics(cdev_cost_share=1.1)


# ---------------------------------------------------------------------------
# TestMilestone
# ---------------------------------------------------------------------------

class TestMilestone:
    def test_phase_start_milestone(self):
        m = Milestone(
            description="Phase 3 start",
            amount_millions=50.0,
            trigger=MilestoneTrigger.PHASE_START,
            trigger_phase="phase_3",
        )
        assert m.trigger == MilestoneTrigger.PHASE_START
        assert m.direction == MilestoneDirection.PAYABLE  # default

    def test_receivable_milestone(self):
        m = Milestone(
            description="Approval receipt",
            amount_millions=100.0,
            trigger=MilestoneTrigger.APPROVAL,
            direction=MilestoneDirection.RECEIVABLE,
        )
        assert m.direction == MilestoneDirection.RECEIVABLE

    def test_amount_must_be_positive(self):
        with pytest.raises(Exception):
            Milestone(description="bad", amount_millions=0.0, trigger=MilestoneTrigger.APPROVAL)
        with pytest.raises(Exception):
            Milestone(description="bad", amount_millions=-10.0, trigger=MilestoneTrigger.APPROVAL)


# ---------------------------------------------------------------------------
# TestMilestonePV — timing and probability weighting
# ---------------------------------------------------------------------------

class TestMilestonePV:
    """
    Verify milestone_pv() timing and probability weighting against
    manually computed expected values.

    Fixture phases:
      phase_2: year_start=0.0,  year_end=2.5,  prob_reaching=1.000, success_prob=0.37
      phase_3: year_start=2.5,  year_end=6.0,  prob_reaching=0.370, success_prob=0.55
      nda_bla: year_start=6.0,  year_end=7.5,  prob_reaching=0.2035, success_prob=0.87
      cumulative_approval_probability = 0.37 × 0.55 × 0.87 ≈ 0.177069
    """

    def test_phase_start_p2_timing_and_prob(self):
        """PHASE_START at phase_2: year=0.0 (year_start), prob=prob_reaching=1.0."""
        m = Milestone(description="p2 start", amount_millions=100.0, trigger=MilestoneTrigger.PHASE_START, trigger_phase="phase_2")
        prob = _prob()
        pv = milestone_pv(m, prob, 0.10)
        # year=0 → no discounting; P=1.0
        assert pv == pytest.approx(100.0 * 1.0, rel=1e-4)

    def test_phase_start_p3_timing_and_prob(self):
        """PHASE_START at phase_3: year=2.5 (year_start), prob=prob_reaching(phase_3)=0.37."""
        m = Milestone(description="p3 start", amount_millions=50.0, trigger=MilestoneTrigger.PHASE_START, trigger_phase="phase_3")
        prob = _prob()
        pv = milestone_pv(m, prob, 0.10)
        expected = 50.0 / (1.10 ** 2.5) * 0.37
        assert pv == pytest.approx(expected, rel=1e-3)

    def test_phase_success_p3_timing_and_prob(self):
        """PHASE_SUCCESS at phase_3: year=6.0 (year_end), prob=prob_reaching×success_prob=0.37×0.55."""
        m = Milestone(description="p3 success", amount_millions=75.0, trigger=MilestoneTrigger.PHASE_SUCCESS, trigger_phase="phase_3")
        prob = _prob()
        pv = milestone_pv(m, prob, 0.10)
        expected = 75.0 / (1.10 ** 6.0) * (0.37 * 0.55)
        assert pv == pytest.approx(expected, rel=1e-3)

    def test_approval_trigger(self):
        """APPROVAL: year=years_to_approval=7.5, prob=cumulative_approval_probability."""
        m = Milestone(description="approval", amount_millions=200.0, trigger=MilestoneTrigger.APPROVAL)
        prob = _prob()
        pv = milestone_pv(m, prob, 0.10)
        cum_prob = prob.cumulative_approval_probability
        expected = 200.0 / (1.10 ** 7.5) * cum_prob
        assert pv == pytest.approx(expected, rel=1e-3)

    def test_first_sale_same_as_approval(self):
        """FIRST_SALE uses same year and probability as APPROVAL."""
        m_approval = Milestone(description="approval", amount_millions=100.0, trigger=MilestoneTrigger.APPROVAL)
        m_first_sale = Milestone(description="first sale", amount_millions=100.0, trigger=MilestoneTrigger.FIRST_SALE)
        prob = _prob()
        assert milestone_pv(m_approval, prob, 0.10) == pytest.approx(
            milestone_pv(m_first_sale, prob, 0.10), rel=1e-6
        )

    def test_sales_threshold_returns_zero(self):
        """SALES_THRESHOLD not yet implemented — returns 0."""
        m = Milestone(description="sales", amount_millions=50.0, trigger=MilestoneTrigger.SALES_THRESHOLD)
        prob = _prob()
        assert milestone_pv(m, prob, 0.10) == 0.0

    def test_unknown_trigger_phase_returns_zero(self):
        m = Milestone(description="bad", amount_millions=50.0, trigger=MilestoneTrigger.PHASE_START, trigger_phase="phase_99")
        prob = _prob()
        assert milestone_pv(m, prob, 0.10) == 0.0

    def test_higher_discount_rate_reduces_pv(self):
        m = Milestone(description="approval", amount_millions=100.0, trigger=MilestoneTrigger.APPROVAL)
        prob = _prob()
        pv_low = milestone_pv(m, prob, 0.05)
        pv_high = milestone_pv(m, prob, 0.20)
        assert pv_low > pv_high


# ---------------------------------------------------------------------------
# TestCostModelWithDeal
# ---------------------------------------------------------------------------

class TestCostModelWithDeal:
    def test_no_deal_matches_pre_step5_baseline(self):
        """deal=None must produce identical output to the pre-Step-5 baseline."""
        prob = _prob()
        cost_no_deal = CostModel.compute(prob, 0.10, deal=None)
        cost_default = CostModel.compute(prob, 0.10, deal=DealEconomics())
        assert cost_no_deal.total_pv_weighted_millions == pytest.approx(
            cost_default.total_pv_weighted_millions, rel=1e-9
        )

    def test_cdev_half_halves_trial_rd_costs(self):
        prob = _prob()
        cost_full = CostModel.compute(prob, 0.10, deal=None)
        cost_half = CostModel.compute(prob, 0.10, deal=DealEconomics(cdev_cost_share=0.5))
        assert cost_half.trial_rd_pv_millions == pytest.approx(
            cost_full.trial_rd_pv_millions * 0.5, abs=0.02  # rounding accumulates across phases
        )

    def test_cdev_share_recorded_on_stream(self):
        prob = _prob()
        cost = CostModel.compute(prob, 0.10, deal=DealEconomics(cdev_cost_share=0.6))
        assert cost.cdev_cost_share == pytest.approx(0.6)

    def test_payable_milestone_adds_to_total(self):
        prob = _prob()
        m = Milestone(description="p3 start", amount_millions=50.0, trigger=MilestoneTrigger.PHASE_START, trigger_phase="phase_3")
        deal = DealEconomics(milestones=[m])
        cost_no_m = CostModel.compute(prob, 0.10)
        cost_with_m = CostModel.compute(prob, 0.10, deal=deal)
        expected_m_pv = milestone_pv(m, prob, 0.10)
        assert cost_with_m.milestone_costs_pv_millions == pytest.approx(expected_m_pv, abs=0.01)
        assert cost_with_m.total_pv_weighted_millions == pytest.approx(
            cost_no_m.total_pv_weighted_millions + expected_m_pv, abs=0.01
        )

    def test_upfront_cost_added_at_face_value(self):
        prob = _prob()
        deal = DealEconomics(upfront_cost_millions=30.0)
        cost_no_up = CostModel.compute(prob, 0.10)
        cost_with_up = CostModel.compute(prob, 0.10, deal=deal)
        assert cost_with_up.upfront_cost_millions == 30.0
        assert cost_with_up.total_pv_weighted_millions == pytest.approx(
            cost_no_up.total_pv_weighted_millions + 30.0, rel=1e-6
        )

    def test_receivable_milestones_not_in_cost_stream(self):
        """CostModel only handles payable milestones; receivable ones are for RNPVModel."""
        prob = _prob()
        recv = Milestone(
            description="approval receipt", amount_millions=100.0, trigger=MilestoneTrigger.APPROVAL,
            direction=MilestoneDirection.RECEIVABLE,
        )
        deal = DealEconomics(milestones=[recv])
        cost_no_deal = CostModel.compute(prob, 0.10)
        cost_with_recv = CostModel.compute(prob, 0.10, deal=deal)
        # Receivable milestone should NOT increase costs
        assert cost_with_recv.total_pv_weighted_millions == pytest.approx(
            cost_no_deal.total_pv_weighted_millions, rel=1e-9
        )
        assert cost_with_recv.milestone_costs_pv_millions == pytest.approx(0.0)

    def test_trial_rd_pv_equals_sum_of_phase_costs(self):
        prob = _prob()
        deal = DealEconomics(cdev_cost_share=0.7)
        cost = CostModel.compute(prob, 0.10, deal=deal)
        expected = sum(pc.pv_cost_weighted for pc in cost.phase_costs)
        assert cost.trial_rd_pv_millions == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# TestRNPVModelWithDeal
# ---------------------------------------------------------------------------

class TestRNPVModelWithDeal:
    def _base_results(self, deal=None):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        rev = RevenueModel.compute(_market())
        cost = CostModel.compute(prob, asset.discount_rate, deal=deal)
        rnpv = RNPVModel.compute(asset, prob, rev, cost, deal=deal)
        return rnpv

    def test_no_deal_matches_pre_step5_baseline(self):
        """deal=None must produce identical rnpv to the pre-Step-5 baseline."""
        baseline = compute_rnpv(_asset(), _trials(), _market())
        with_deal_none = self._base_results(deal=None)
        assert with_deal_none.rnpv_millions == pytest.approx(baseline.rnpv_millions, abs=0.01)

    def test_royalty_reduces_rnpv(self):
        """Adding a 10% deal royalty on top of zero asset royalty must reduce rNPV."""
        base = self._base_results(deal=None)
        with_royalty = self._base_results(deal=DealEconomics(royalty_rate=0.10))
        assert with_royalty.rnpv_millions < base.rnpv_millions

    def test_royalty_stacks_multiplicatively_with_asset_royalty(self):
        """
        asset.net_ownership=0.90, deal.royalty_rate=0.10
        effective_ownership = 0.90 × 0.90 = 0.81
        """
        asset_with_royalty = _asset(royalty_rate=0.10)
        prob = ProbabilityModel.compute(asset_with_royalty, _trials())
        rev = RevenueModel.compute(_market())
        deal = DealEconomics(royalty_rate=0.10)
        cost = CostModel.compute(prob, asset_with_royalty.discount_rate, deal=deal)
        rnpv = RNPVModel.compute(asset_with_royalty, prob, rev, cost, deal=deal)
        assert rnpv.net_ownership == pytest.approx(0.90 * 0.90, rel=1e-6)

    def test_receivable_milestone_increases_rnpv(self):
        """An approval milestone receipt (after discounting and probability weighting) increases rNPV."""
        recv = Milestone(
            description="approval receipt", amount_millions=100.0, trigger=MilestoneTrigger.APPROVAL,
            direction=MilestoneDirection.RECEIVABLE,
        )
        base = self._base_results(deal=None)
        with_recv = self._base_results(deal=DealEconomics(milestones=[recv]))
        assert with_recv.rnpv_millions > base.rnpv_millions

    def test_receivable_milestone_pv_on_result(self):
        """deal_milestone_receipts_pv_millions matches manually computed value."""
        prob = _prob()
        recv = Milestone(description="approval", amount_millions=100.0, trigger=MilestoneTrigger.APPROVAL,
                         direction=MilestoneDirection.RECEIVABLE)
        deal = DealEconomics(milestones=[recv])
        rev = RevenueModel.compute(_market())
        cost = CostModel.compute(prob, 0.10, deal=deal)
        rnpv = RNPVModel.compute(_asset(), prob, rev, cost, deal=deal)
        expected_pv = milestone_pv(recv, prob, 0.10)
        assert rnpv.deal_milestone_receipts_pv_millions == pytest.approx(expected_pv, abs=0.01)

    def test_upfront_receipt_added_at_face_value(self):
        """Upfront receipt is at t=0 so no discounting — full amount adds to rNPV."""
        deal = DealEconomics(upfront_receipt_millions=50.0)
        base = self._base_results(deal=None)
        with_receipt = self._base_results(deal=deal)
        assert with_receipt.rnpv_millions == pytest.approx(
            base.rnpv_millions + 50.0, abs=0.01
        )
        assert with_receipt.upfront_receipt_millions == 50.0

    def test_net_ownership_reflects_deal_royalty(self):
        deal = DealEconomics(royalty_rate=0.15)
        rnpv = self._base_results(deal=deal)
        # asset royalty_rate=0, deal royalty=0.15 → ownership = 1.0 × 0.85 = 0.85
        assert rnpv.net_ownership == pytest.approx(0.85, rel=1e-6)

    def test_payable_milestone_reduces_rnpv(self):
        """A payable milestone increases costs → reduces rNPV."""
        pay = Milestone(description="p3 start", amount_millions=50.0, trigger=MilestoneTrigger.PHASE_START, trigger_phase="phase_3")
        base = self._base_results(deal=None)
        with_pay = self._base_results(deal=DealEconomics(milestones=[pay]))
        assert with_pay.rnpv_millions < base.rnpv_millions


# ---------------------------------------------------------------------------
# TestDealBoundary — RevenueModel must be untouched by deal economics
# ---------------------------------------------------------------------------

class TestDealBoundary:
    def test_revenue_stream_identical_regardless_of_deal(self):
        """
        Revenue is gross commercial revenue.  Deal economics must not affect it.
        RevenueModel has no DealEconomics parameter.
        """
        rev_no_deal = RevenueModel.compute(_market())
        rev_with_deal = RevenueModel.compute(_market())  # same — no deal parameter exists
        assert rev_no_deal.revenue_by_year == rev_with_deal.revenue_by_year
        assert rev_no_deal.ebit_by_year == rev_with_deal.ebit_by_year

    def test_revenue_model_has_no_deal_parameter(self):
        """RevenueModel.compute signature must not accept a deal parameter."""
        import inspect
        sig = inspect.signature(RevenueModel.compute)
        param_names = list(sig.parameters.keys())
        assert "deal" not in param_names
        assert "deal_economics" not in param_names


# ---------------------------------------------------------------------------
# TestDrugAssetProgramDeal
# ---------------------------------------------------------------------------

class TestDrugAssetProgramDeal:
    def test_deal_economics_defaults_on_program(self):
        program = DrugAssetProgram(
            asset=_asset(), trials=_trials(), market_model=_market()
        )
        assert not program.deal_economics.has_deal_terms

    def test_build_accepts_deal_economics(self):
        deal = DealEconomics(royalty_rate=0.08, cdev_cost_share=0.5)
        program = DrugAssetProgram.build(
            asset=_asset(), trials=_trials(), market_model=_market(),
            deal_economics=deal,
        )
        assert program.deal_economics.royalty_rate == 0.08
        assert program.deal_economics.cdev_cost_share == 0.5

    def test_deal_economics_frozen_with_program(self):
        program = DrugAssetProgram.build(
            asset=_asset(), trials=_trials(), market_model=_market()
        )
        with pytest.raises(Exception):
            program.deal_economics = DealEconomics(royalty_rate=0.10)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestValuationEngineWithDeal
# ---------------------------------------------------------------------------

class TestValuationEngineWithDeal:
    def _engine(self, deal: DealEconomics) -> ValuationEngine:
        program = DrugAssetProgram.build(
            asset=_asset(), trials=_trials(), market_model=_market(),
            deal_economics=deal, load_loe=False,
        )
        return ValuationEngine.from_program(
            program=program, company=_company(),
            mc_params=MonteCarloParams(n_simulations=50, random_seed=0),
        )

    def test_no_deal_engine_runs(self):
        output = self._engine(DealEconomics()).run()
        assert output.rnpv.rnpv_millions > 0

    def test_cdev_half_lowers_costs_and_raises_rnpv(self):
        base = self._engine(DealEconomics()).run()
        half = self._engine(DealEconomics(cdev_cost_share=0.5)).run()
        assert half.rnpv.rnpv_millions > base.rnpv.rnpv_millions

    def test_royalty_lowers_rnpv(self):
        base = self._engine(DealEconomics()).run()
        royalty = self._engine(DealEconomics(royalty_rate=0.20)).run()
        assert royalty.rnpv.rnpv_millions < base.rnpv.rnpv_millions

    def test_upfront_receipt_adds_to_rnpv(self):
        base = self._engine(DealEconomics()).run()
        receipt = self._engine(DealEconomics(upfront_receipt_millions=50.0)).run()
        assert receipt.rnpv.rnpv_millions == pytest.approx(
            base.rnpv.rnpv_millions + 50.0, abs=0.01
        )

    def test_deal_stored_on_engine(self):
        deal = DealEconomics(royalty_rate=0.05)
        engine = self._engine(deal)
        assert engine._deal_economics.royalty_rate == 0.05


# ---------------------------------------------------------------------------
# TestBackwardCompatWithDeal
# ---------------------------------------------------------------------------

class TestBackwardCompatWithDeal:
    def test_compute_rnpv_wrapper_unaffected(self):
        """compute_rnpv() has no deal parameter — results are pre-Step-5 baseline."""
        result = compute_rnpv(_asset(), _trials(), _market())
        assert result.rnpv_millions > 0
        assert result.deal_milestone_receipts_pv_millions == 0.0
        assert result.upfront_receipt_millions == 0.0
        assert result.net_ownership == pytest.approx(1.0)

    def test_direct_engine_without_program_has_no_deal(self):
        """ValuationEngine constructed without from_program has _deal_economics=None."""
        engine = ValuationEngine(
            asset=_asset(), company=_company(),
            trials=_trials(), market_model=_market(),
        )
        assert engine._deal_economics is None

    def test_direct_engine_runs_correctly_with_null_deal(self):
        """Direct ValuationEngine (no program) still runs cleanly — null deal is safe."""
        engine = ValuationEngine(
            asset=_asset(), company=_company(),
            trials=_trials(), market_model=_market(),
            mc_params=MonteCarloParams(n_simulations=50, random_seed=0),
        )
        output = engine.run()
        assert output.rnpv.rnpv_millions > 0


# ---------------------------------------------------------------------------
# TestRoyaltyMathFormula
# Explicit numeric proof: captured_revenue = gross_ebit × net_ownership × (1 − royalty_rate)
# ---------------------------------------------------------------------------

class TestRoyaltyMathFormula:
    """
    Verify the royalty stacking formula numerically.

    Formula (from rnpv_model.py):
      effective_ownership = asset.net_ownership × (1 − deal.royalty_rate)
      probability_adjusted_revenue_pv = Σ [ebit_yr × effective_ownership / (1+r)^yr] × P(approval)

    Proof: ratio of gross_revenue_pv with two different royalty stacks must equal
    the ratio of their effective ownerships.
    """

    def _revenue_pv(self, asset_royalty: float, deal_royalty: float) -> tuple[float, float]:
        """Return (gross_revenue_pv_millions, effective_ownership) for given royalty params."""
        asset = _asset(royalty_rate=asset_royalty)
        deal = DealEconomics(royalty_rate=deal_royalty)
        prob = ProbabilityModel.compute(asset, _trials())
        rev = RevenueModel.compute(_market())
        cost = CostModel.compute(prob, asset.discount_rate, deal=deal)
        rnpv = RNPVModel.compute(asset, prob, rev, cost, deal=deal)
        return rnpv.gross_revenue_pv_millions, rnpv.net_ownership

    def test_zero_royalties_gives_full_ownership(self):
        _, ownership = self._revenue_pv(asset_royalty=0.0, deal_royalty=0.0)
        assert ownership == pytest.approx(1.0, rel=1e-9)

    def test_asset_royalty_reduces_ownership(self):
        """asset.royalty_rate=0.20 → net_ownership=0.80, deal royalty=0."""
        _, ownership = self._revenue_pv(asset_royalty=0.20, deal_royalty=0.0)
        assert ownership == pytest.approx(0.80, rel=1e-9)

    def test_deal_royalty_stacks_multiplicatively(self):
        """asset.royalty_rate=0.20, deal.royalty_rate=0.10 → 0.80 × 0.90 = 0.72."""
        _, ownership = self._revenue_pv(asset_royalty=0.20, deal_royalty=0.10)
        assert ownership == pytest.approx(0.80 * 0.90, rel=1e-9)

    def test_revenue_ratio_matches_ownership_ratio(self):
        """
        gross_revenue_pv encodes effective_ownership in every term.
        Ratio of gross_revenue_pv(ownership_A) / gross_revenue_pv(ownership_B)
        must equal ownership_A / ownership_B.
        """
        pv_full, own_full = self._revenue_pv(asset_royalty=0.0, deal_royalty=0.0)
        pv_half, own_half = self._revenue_pv(asset_royalty=0.0, deal_royalty=0.50)
        # own_half = 0.50; pv should be half of pv_full (abs tolerance for 2dp rounding)
        assert pv_half == pytest.approx(pv_full * (own_half / own_full), abs=0.02)

    def test_formula_explicit_numeric(self):
        """
        asset.royalty_rate=0, deal.royalty_rate=0.10.
        captured_revenue = gross_ebit × 1.0 × (1 − 0.10) = gross_ebit × 0.90
        Verify: gross_revenue_pv(royalty=0.10) = gross_revenue_pv(royalty=0) × 0.90
        """
        pv_base, _ = self._revenue_pv(asset_royalty=0.0, deal_royalty=0.0)
        pv_royalty, _ = self._revenue_pv(asset_royalty=0.0, deal_royalty=0.10)
        assert pv_royalty == pytest.approx(pv_base * 0.90, abs=0.02)


# ---------------------------------------------------------------------------
# TestTriggerSemantics
# Verify each MilestoneTrigger uses the correct timing source.
# ---------------------------------------------------------------------------

class TestTriggerSemantics:
    """
    Fixture phases (from _trials()):
      phase_2: year_start=0.0, year_end=2.5
      phase_3: year_start=2.5, year_end=6.0
      nda_bla: year_start=6.0, year_end=7.5
      years_to_approval = 7.5
    """

    def test_phase_start_uses_year_start_not_year_end(self):
        """PHASE_START: discounts at year_start (2.5), NOT year_end (6.0)."""
        prob = _prob()
        m = Milestone(description="p3 start", amount_millions=100.0,
                      trigger=MilestoneTrigger.PHASE_START, trigger_phase="phase_3")
        pv = milestone_pv(m, prob, 0.10)
        # Expected: year_start=2.5
        expected_start = 100.0 / (1.10 ** 2.5) * 0.37
        expected_end   = 100.0 / (1.10 ** 6.0) * 0.37
        assert pv == pytest.approx(expected_start, rel=1e-3)
        assert pv != pytest.approx(expected_end, rel=1e-2)

    def test_phase_success_uses_year_end_not_year_start(self):
        """PHASE_SUCCESS: discounts at year_end (6.0), NOT year_start (2.5)."""
        prob = _prob()
        m = Milestone(description="p3 success", amount_millions=100.0,
                      trigger=MilestoneTrigger.PHASE_SUCCESS, trigger_phase="phase_3")
        pv = milestone_pv(m, prob, 0.10)
        # Expected: year_end=6.0, prob = prob_reaching × success_prob = 0.37 × 0.55
        expected_end   = 100.0 / (1.10 ** 6.0) * (0.37 * 0.55)
        expected_start = 100.0 / (1.10 ** 2.5) * (0.37 * 0.55)
        assert pv == pytest.approx(expected_end, rel=1e-3)
        assert pv != pytest.approx(expected_start, rel=1e-2)

    def test_phase_success_probability_includes_success_rate(self):
        """PHASE_SUCCESS prob = prob_reaching × success_probability (not just prob_reaching)."""
        prob = _prob()
        p3 = next(p for p in prob.phases if p.phase == "phase_3")
        m = Milestone(description="p3 success", amount_millions=100.0,
                      trigger=MilestoneTrigger.PHASE_SUCCESS, trigger_phase="phase_3")
        pv = milestone_pv(m, prob, 0.10)
        # PHASE_SUCCESS: P = prob_reaching × success_prob
        expected_prob = p3.prob_reaching * p3.success_probability
        expected_pv = 100.0 / (1.10 ** p3.year_end) * expected_prob
        assert pv == pytest.approx(expected_pv, rel=1e-3)

    def test_approval_uses_years_to_approval(self):
        """APPROVAL: year=years_to_approval (7.5), prob=cumulative_approval_probability."""
        prob = _prob()
        m = Milestone(description="approval", amount_millions=100.0, trigger=MilestoneTrigger.APPROVAL)
        pv = milestone_pv(m, prob, 0.10)
        expected = 100.0 / (1.10 ** prob.years_to_approval) * prob.cumulative_approval_probability
        assert pv == pytest.approx(expected, rel=1e-4)

    def test_first_sale_with_zero_offset_equals_approval(self):
        """FIRST_SALE with launch_year_offset=0 must equal APPROVAL PV."""
        prob = _prob()
        m = Milestone(description="first sale", amount_millions=100.0, trigger=MilestoneTrigger.FIRST_SALE)
        pv_first_sale = milestone_pv(m, prob, 0.10, launch_year_offset=0.0)
        pv_approval = 100.0 / (1.10 ** prob.years_to_approval) * prob.cumulative_approval_probability
        assert pv_first_sale == pytest.approx(pv_approval, rel=1e-6)

    def test_first_sale_with_nonzero_offset_differs_from_approval(self):
        """FIRST_SALE with launch_year_offset=1.5 must produce lower PV than APPROVAL (later cash flow)."""
        prob = _prob()
        m_approval = Milestone(description="approval", amount_millions=100.0, trigger=MilestoneTrigger.APPROVAL)
        m_first_sale = Milestone(description="first sale", amount_millions=100.0, trigger=MilestoneTrigger.FIRST_SALE)
        pv_approval = milestone_pv(m_approval, prob, 0.10)
        pv_first_sale = milestone_pv(m_first_sale, prob, 0.10, launch_year_offset=1.5)
        assert pv_first_sale < pv_approval  # later → lower PV

    def test_first_sale_offset_exact_numeric(self):
        """FIRST_SALE with launch_year_offset=2: year = years_to_approval + 2."""
        prob = _prob()
        m = Milestone(description="first sale", amount_millions=100.0, trigger=MilestoneTrigger.FIRST_SALE)
        pv = milestone_pv(m, prob, 0.10, launch_year_offset=2.0)
        year = prob.years_to_approval + 2.0
        expected = 100.0 / (1.10 ** year) * prob.cumulative_approval_probability
        assert pv == pytest.approx(expected, rel=1e-4)

    def test_deal_launch_year_offset_flows_to_milestone_pv(self):
        """DealEconomics.launch_year_offset is forwarded to milestone_pv() by CostModel and RNPVModel."""
        prob = _prob()
        # Payable FIRST_SALE milestone via CostModel path
        m = Milestone(description="first sale pay", amount_millions=100.0,
                      trigger=MilestoneTrigger.FIRST_SALE, direction=MilestoneDirection.PAYABLE)
        deal_no_lag = DealEconomics(milestones=[m], launch_year_offset=0.0)
        deal_with_lag = DealEconomics(milestones=[m], launch_year_offset=2.0)
        cost_no_lag = CostModel.compute(prob, 0.10, deal=deal_no_lag)
        cost_with_lag = CostModel.compute(prob, 0.10, deal=deal_with_lag)
        # Lag → later cash flow → lower PV → lower total cost
        assert cost_with_lag.milestone_costs_pv_millions < cost_no_lag.milestone_costs_pv_millions

    def test_receivable_launch_year_offset_flows_via_rnpv(self):
        """DealEconomics.launch_year_offset also flows through RNPVModel for receivable milestones."""
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        rev = RevenueModel.compute(_market())
        m = Milestone(description="first sale recv", amount_millions=100.0,
                      trigger=MilestoneTrigger.FIRST_SALE, direction=MilestoneDirection.RECEIVABLE)
        deal_no_lag = DealEconomics(milestones=[m], launch_year_offset=0.0)
        deal_with_lag = DealEconomics(milestones=[m], launch_year_offset=2.0)
        cost_no_lag = CostModel.compute(prob, asset.discount_rate, deal=deal_no_lag)
        cost_with_lag = CostModel.compute(prob, asset.discount_rate, deal=deal_with_lag)
        rnpv_no_lag = RNPVModel.compute(asset, prob, rev, cost_no_lag, deal=deal_no_lag)
        rnpv_with_lag = RNPVModel.compute(asset, prob, rev, cost_with_lag, deal=deal_with_lag)
        # Lag → later receipt → lower PV → lower deal_milestone_receipts_pv_millions
        assert rnpv_with_lag.deal_milestone_receipts_pv_millions < rnpv_no_lag.deal_milestone_receipts_pv_millions


# ---------------------------------------------------------------------------
# TestUpfrontAtTimeZero
# Upfront cash flows are at t=0 — no discount factor applied.
# ---------------------------------------------------------------------------

class TestUpfrontAtTimeZero:
    """
    Upfront cost and receipt are time-0 cash flows.
    They are added at face value without any discount factor.
    Verify: rNPV delta == exact face value, regardless of discount rate.
    """

    def _rnpv(self, deal: DealEconomics, discount_rate: float = 0.10) -> float:
        asset = Asset(
            id=_ASSET_ID, name="T0 Test Asset", indication="test",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            discount_rate=discount_rate, royalty_rate=0.0,
        )
        prob = ProbabilityModel.compute(asset, _trials())
        rev = RevenueModel.compute(_market())
        cost = CostModel.compute(prob, discount_rate, deal=deal)
        rnpv = RNPVModel.compute(asset, prob, rev, cost, deal=deal)
        return rnpv.rnpv_millions

    def test_upfront_receipt_delta_equals_face_value(self):
        """rNPV increases by exactly upfront_receipt_millions (no discounting)."""
        base = self._rnpv(DealEconomics())
        with_receipt = self._rnpv(DealEconomics(upfront_receipt_millions=75.0))
        assert with_receipt - base == pytest.approx(75.0, rel=1e-6)

    def test_upfront_cost_delta_equals_face_value(self):
        """rNPV decreases by exactly upfront_cost_millions (no discounting)."""
        base = self._rnpv(DealEconomics())
        with_cost = self._rnpv(DealEconomics(upfront_cost_millions=40.0))
        assert base - with_cost == pytest.approx(40.0, rel=1e-6)

    def test_upfront_receipt_invariant_to_discount_rate(self):
        """
        A t=0 cash flow must add the same face value regardless of discount rate.
        If it were discounted, high-rate runs would show a smaller delta.
        """
        deal_base = DealEconomics()
        deal_recv = DealEconomics(upfront_receipt_millions=50.0)
        delta_low  = self._rnpv(deal_recv, 0.05) - self._rnpv(deal_base, 0.05)
        delta_high = self._rnpv(deal_recv, 0.30) - self._rnpv(deal_base, 0.30)
        assert delta_low  == pytest.approx(50.0, rel=1e-6)
        assert delta_high == pytest.approx(50.0, rel=1e-6)

    def test_upfront_cost_invariant_to_discount_rate(self):
        """Same invariant for upfront cost — face value always subtracted at t=0."""
        deal_base = DealEconomics()
        deal_cost = DealEconomics(upfront_cost_millions=60.0)
        delta_low  = self._rnpv(deal_base, 0.05) - self._rnpv(deal_cost, 0.05)
        delta_high = self._rnpv(deal_base, 0.30) - self._rnpv(deal_cost, 0.30)
        assert delta_low  == pytest.approx(60.0, rel=1e-6)
        assert delta_high == pytest.approx(60.0, rel=1e-6)

    def test_upfront_cost_field_recorded_on_cost_stream(self):
        """upfront_cost_millions is stored at face value on CostStream."""
        prob = _prob()
        cost = CostModel.compute(prob, 0.10, deal=DealEconomics(upfront_cost_millions=99.0))
        assert cost.upfront_cost_millions == pytest.approx(99.0, rel=1e-9)

    def test_upfront_receipt_field_recorded_on_rnpv_result(self):
        """upfront_receipt_millions is stored at face value on RNPVResult."""
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        rev = RevenueModel.compute(_market())
        deal = DealEconomics(upfront_receipt_millions=88.0)
        cost = CostModel.compute(prob, asset.discount_rate, deal=deal)
        rnpv = RNPVModel.compute(asset, prob, rev, cost, deal=deal)
        assert rnpv.upfront_receipt_millions == pytest.approx(88.0, rel=1e-9)
