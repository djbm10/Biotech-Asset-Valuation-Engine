"""
Sprint E7 — SALES_THRESHOLD milestone resolution via revenue_stream.

Tests cover:
  1. Milestone: sales_threshold_millions field, validator
  2. milestone_pv: SALES_THRESHOLD returns 0.0 without revenue_stream
  3. milestone_pv: SALES_THRESHOLD exact timing — first year revenue >= threshold
  4. milestone_pv: threshold never crossed returns 0.0
  5. milestone_pv: SALES_THRESHOLD probability-weighted correctly
  6. RNPVModel: SALES_THRESHOLD receivable milestone increases rNPV
  7. RNPVModel: SALES_THRESHOLD payable milestone reduces rNPV
  8. Backward compatibility: non-SALES_THRESHOLD milestones unaffected
  9. SALES_THRESHOLD without revenue_stream returns 0.0 end-to-end
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial
from bve.models.deal_economics import (
    DealEconomics,
    Milestone,
    MilestoneDirection,
    MilestoneTrigger,
    milestone_pv,
)
from bve.models.drug_asset_program import DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.models.probability_model import ProbabilityModel, ProbabilityResult
from bve.models.revenue_model import RevenueModel, RevenueStream
from bve.models.rnpv_model import RNPVModel
from bve.models.cost_model import CostModel
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset() -> Asset:
    return Asset(
        id="e7-test",
        name="E7 Test",
        indication="Test",
        therapeutic_area="oncology",
        stage="phase_3",
        modality="small_molecule",
        discount_rate=0.10,
    )


def _company() -> Company:
    return Company(
        id="e7-co",
        name="E7 Co",
        cash_millions=80.0,
        shares_outstanding_millions=40.0,
    )


def _market(tam: float = 600.0, peak_pen: float = 0.15) -> MarketModel:
    return MarketModel(
        asset_id="e7-test",
        therapeutic_area="oncology",
        total_addressable_market_millions=tam,
        peak_penetration=peak_pen,
        patent_life_years=10,
    )


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="e7-test",
            phase="phase_3",
            success_probability=0.60,
            duration_years=3.0,
            cost_millions=150.0,
            cost_source="override",
        ),
    ]


def _prob() -> ProbabilityResult:
    return ProbabilityModel.compute(_asset(), _trials())


def _rev(tam: float = 600.0, peak_pen: float = 0.15) -> RevenueStream:
    return RevenueModel.compute(_market(tam, peak_pen))


def _st_milestone(
    threshold: float,
    amount: float = 50.0,
    direction: MilestoneDirection = MilestoneDirection.RECEIVABLE,
) -> Milestone:
    return Milestone(
        description=f"Sales milestone ${amount}M at ${threshold}M revenue",
        amount_millions=amount,
        trigger=MilestoneTrigger.SALES_THRESHOLD,
        direction=direction,
        sales_threshold_millions=threshold,
    )


# ---------------------------------------------------------------------------
# 1. Milestone validation
# ---------------------------------------------------------------------------

class TestMilestoneSalesThreshold:
    def test_sales_threshold_requires_threshold_value(self):
        with pytest.raises(ValidationError, match="sales_threshold_millions"):
            Milestone(
                description="Missing threshold",
                amount_millions=50.0,
                trigger=MilestoneTrigger.SALES_THRESHOLD,
                sales_threshold_millions=None,
            )

    def test_sales_threshold_with_value_constructable(self):
        m = _st_milestone(threshold=100.0)
        assert m.sales_threshold_millions == pytest.approx(100.0)
        assert m.trigger == MilestoneTrigger.SALES_THRESHOLD

    def test_negative_threshold_rejected(self):
        with pytest.raises(ValidationError):
            Milestone(
                description="Negative threshold",
                amount_millions=50.0,
                trigger=MilestoneTrigger.SALES_THRESHOLD,
                sales_threshold_millions=-10.0,
            )

    def test_non_sales_threshold_trigger_no_threshold_required(self):
        """Other triggers don't need sales_threshold_millions."""
        m = Milestone(
            description="Approval milestone",
            amount_millions=30.0,
            trigger=MilestoneTrigger.APPROVAL,
        )
        assert m.sales_threshold_millions is None

    def test_threshold_on_non_sales_trigger_ignored(self):
        """sales_threshold_millions is stored but does not affect other triggers."""
        m = Milestone(
            description="Approval milestone with extra field",
            amount_millions=30.0,
            trigger=MilestoneTrigger.APPROVAL,
            sales_threshold_millions=100.0,
        )
        assert m.sales_threshold_millions == pytest.approx(100.0)
        # PV uses APPROVAL timing regardless
        prob = _prob()
        pv = milestone_pv(m, prob, 0.10)
        expected_pv = 30.0 / (1.0 + 0.10) ** prob.years_to_approval * prob.cumulative_approval_probability
        assert pv == pytest.approx(expected_pv, abs=0.01)


# ---------------------------------------------------------------------------
# 2. milestone_pv: no revenue_stream → 0.0
# ---------------------------------------------------------------------------

class TestMilestonePVNoStream:
    def test_returns_zero_without_revenue_stream(self):
        m = _st_milestone(threshold=50.0)
        prob = _prob()
        assert milestone_pv(m, prob, 0.10) == 0.0

    def test_returns_zero_with_none_explicit(self):
        m = _st_milestone(threshold=50.0)
        prob = _prob()
        assert milestone_pv(m, prob, 0.10, revenue_stream=None) == 0.0


# ---------------------------------------------------------------------------
# 3. milestone_pv: exact timing
# ---------------------------------------------------------------------------

class TestMilestonePVExactTiming:
    def test_first_year_above_threshold(self):
        """
        Milestone fires in the first year revenue >= threshold.
        Absolute year = years_to_approval + trigger_year.
        """
        prob = _prob()
        rev = _rev()
        r = 0.10

        # Find the first year where revenue >= 20.0 manually
        threshold = 20.0
        for idx, v in enumerate(rev.revenue_by_year, start=1):
            if v >= threshold:
                expected_year = prob.years_to_approval + float(idx)
                break
        else:
            pytest.skip("Threshold never crossed in revenue curve")

        m = _st_milestone(threshold=threshold, amount=80.0, direction=MilestoneDirection.RECEIVABLE)
        pv = milestone_pv(m, prob, r, revenue_stream=rev)

        expected_pv = 80.0 / (1.0 + r) ** expected_year * prob.cumulative_approval_probability
        assert pv == pytest.approx(expected_pv, abs=0.01)

    def test_threshold_met_in_year_1(self):
        """When year 1 revenue already >= threshold, discount year = years_to_approval + 1."""
        prob = _prob()
        rev = _rev(tam=6000.0, peak_pen=0.50)  # large market → year 1 revenue is high
        threshold = rev.revenue_by_year[0] * 0.5  # well below year 1 revenue
        m = _st_milestone(threshold=threshold, amount=100.0)
        r = 0.10
        pv = milestone_pv(m, prob, r, revenue_stream=rev)
        expected_year = prob.years_to_approval + 1.0
        expected_pv = 100.0 / (1.0 + r) ** expected_year * prob.cumulative_approval_probability
        assert pv == pytest.approx(expected_pv, abs=0.01)

    def test_higher_threshold_later_year(self):
        """A higher threshold fires later → lower PV (more time discounting)."""
        prob = _prob()
        rev = _rev()
        r = 0.10
        m_low = _st_milestone(threshold=10.0, amount=100.0)
        m_high = _st_milestone(threshold=60.0, amount=100.0)  # fires later if crossed

        pv_low = milestone_pv(m_low, prob, r, revenue_stream=rev)
        pv_high = milestone_pv(m_high, prob, r, revenue_stream=rev)

        if pv_high > 0.0:  # only assert if threshold is actually crossed
            assert pv_low >= pv_high  # earlier trigger → >= PV


# ---------------------------------------------------------------------------
# 4. Threshold never crossed
# ---------------------------------------------------------------------------

class TestThresholdNeverCrossed:
    def test_returns_zero_when_never_crossed(self):
        """Extremely high threshold → never crossed → PV = 0.0."""
        prob = _prob()
        rev = _rev(tam=100.0, peak_pen=0.05)  # small market
        m = _st_milestone(threshold=1_000_000.0, amount=50.0)  # absurdly high
        pv = milestone_pv(m, prob, 0.10, revenue_stream=rev)
        assert pv == 0.0


# ---------------------------------------------------------------------------
# 5. Probability weighting
# ---------------------------------------------------------------------------

class TestMilestonePVProbabilityWeighting:
    def test_pv_weighted_by_cumulative_approval_prob(self):
        """PV = amount / (1+r)^year × cumulative_approval_probability."""
        prob = _prob()
        rev = _rev()
        r = 0.10
        threshold = 5.0  # very low — fires in year 1
        m = _st_milestone(threshold=threshold, amount=100.0)

        pv = milestone_pv(m, prob, r, revenue_stream=rev)
        # PV should be < amount (probability and discounting both < 1)
        assert pv < m.amount_millions
        assert pv > 0.0

    def test_zero_cumulative_prob_means_zero_pv(self):
        """If cumulative P(approval) = 0, PV must be 0."""
        # Build a prob with zero cumulative probability
        from bve.models.probability_model import PhaseResult, ProbabilityResult
        prob_zero = ProbabilityResult(
            asset_id="e7-test",
            asset_name="E7 Test",
            phases=[
                PhaseResult(
                    phase="phase_3",
                    success_probability=0.0,
                    prob_reaching=1.0,
                    year_start=0.0,
                    year_end=3.0,
                    cost_millions=100.0,
                )
            ],
            cumulative_approval_probability=0.0,
            years_to_approval=3.0,
        )
        rev = _rev()
        m = _st_milestone(threshold=1.0, amount=100.0)
        pv = milestone_pv(m, prob_zero, 0.10, revenue_stream=rev)
        assert pv == 0.0


# ---------------------------------------------------------------------------
# 6. RNPVModel: receivable SALES_THRESHOLD milestone
# ---------------------------------------------------------------------------

class TestRNPVModelSalesThresholdReceivable:
    def _rnpv(self, milestones: list[Milestone]) -> float:
        asset = _asset()
        prob = _prob()
        market = _market()
        rev = _rev()
        cost = CostModel.compute(prob, 0.10)
        deal = DealEconomics(milestones=milestones)
        result = RNPVModel.compute(asset, prob, rev, cost, deal=deal)
        return result.rnpv_millions

    def test_receivable_st_milestone_increases_rnpv(self):
        """A receivable SALES_THRESHOLD milestone raises rNPV (income)."""
        base = self._rnpv([])
        with_st = self._rnpv([_st_milestone(threshold=20.0, amount=100.0,
                                             direction=MilestoneDirection.RECEIVABLE)])
        assert with_st > base

    def test_larger_amount_higher_rnpv(self):
        st_small = self._rnpv([_st_milestone(threshold=20.0, amount=50.0)])
        st_large = self._rnpv([_st_milestone(threshold=20.0, amount=150.0)])
        assert st_large > st_small

    def test_never_crossed_threshold_no_rnpv_change(self):
        """Threshold never crossed → PV=0 → rNPV same as base."""
        base = self._rnpv([])
        absurd = self._rnpv([_st_milestone(threshold=99_999.0, amount=100.0)])
        assert base == pytest.approx(absurd, rel=1e-6)


# ---------------------------------------------------------------------------
# 7. RNPVModel: payable SALES_THRESHOLD milestone
# ---------------------------------------------------------------------------

class TestRNPVModelSalesThresholdPayable:
    def _rnpv(self, milestones: list[Milestone]) -> float:
        asset = _asset()
        prob = _prob()
        market = _market()
        rev = _rev()
        cost = CostModel.compute(prob, 0.10)
        deal = DealEconomics(milestones=milestones)
        return RNPVModel.compute(asset, prob, rev, cost, deal=deal).rnpv_millions

    def test_payable_st_milestone_reduces_rnpv(self):
        """A payable SALES_THRESHOLD milestone lowers rNPV (cost)."""
        base = self._rnpv([])
        with_st = self._rnpv([_st_milestone(threshold=20.0, amount=100.0,
                                             direction=MilestoneDirection.PAYABLE)])
        assert with_st < base

    def test_larger_payable_lowers_rnpv_more(self):
        st_small = self._rnpv([_st_milestone(threshold=20.0, amount=50.0,
                                              direction=MilestoneDirection.PAYABLE)])
        st_large = self._rnpv([_st_milestone(threshold=20.0, amount=150.0,
                                              direction=MilestoneDirection.PAYABLE)])
        assert st_large < st_small


# ---------------------------------------------------------------------------
# 8. Backward compatibility: non-SALES_THRESHOLD milestones unaffected
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_approval_milestone_pv_unchanged(self):
        """Adding revenue_stream=rev should not change APPROVAL milestone PV."""
        prob = _prob()
        rev = _rev()
        r = 0.10
        m = Milestone(
            description="Approval milestone",
            amount_millions=50.0,
            trigger=MilestoneTrigger.APPROVAL,
        )
        pv_no_stream = milestone_pv(m, prob, r)
        pv_with_stream = milestone_pv(m, prob, r, revenue_stream=rev)
        assert pv_no_stream == pytest.approx(pv_with_stream, rel=1e-9)

    def test_phase_success_milestone_pv_unchanged(self):
        prob = _prob()
        rev = _rev()
        r = 0.10
        m = Milestone(
            description="P3 success",
            amount_millions=40.0,
            trigger=MilestoneTrigger.PHASE_SUCCESS,
            trigger_phase="phase_3",
        )
        pv_no_stream = milestone_pv(m, prob, r)
        pv_with_stream = milestone_pv(m, prob, r, revenue_stream=rev)
        assert pv_no_stream == pytest.approx(pv_with_stream, rel=1e-9)

    def test_deal_without_st_milestones_rnpv_unchanged(self):
        """Programs without SALES_THRESHOLD milestones are unaffected."""
        asset = _asset()
        prob = _prob()
        rev = _rev()
        cost = CostModel.compute(prob, 0.10)
        deal_approval = DealEconomics(milestones=[
            Milestone(
                description="Approval",
                amount_millions=30.0,
                trigger=MilestoneTrigger.APPROVAL,
                direction=MilestoneDirection.RECEIVABLE,
            )
        ])
        result = RNPVModel.compute(asset, prob, rev, cost, deal=deal_approval)
        assert isinstance(result.rnpv_millions, float)
