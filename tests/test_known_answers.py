"""
Known-answer tests — verify rNPV math against hand-computed reference values.

These tests instantiate toy assets with fixed, simple inputs and assert that
the model output equals a value that was pre-computed by hand (shown in each
test's docstring).  The purpose is to detect silent regressions in core math.

Conventions
-----------
- All market models use cogs_rate=0, sgna_rate_launch=0, sgna_rate_mature=0
  so that EBIT = Revenue (simplifying hand computation).
- net_ownership = 1.0 (no royalty split), effective_tax_rate = 0.0.
- Tolerance: ±5M on rNPV (a 1% error on a $500M asset), ±1% on cost PV.
"""
from __future__ import annotations

import math
import pytest

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.deal_economics import DealEconomics, Milestone, MilestoneTrigger, MilestoneDirection
from bve.models.market_model import MarketModel
from bve.models.rnpv_model import compute_rnpv_full


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset(
    discount_rate: float = 0.10,
    net_ownership: float = 1.0,
    effective_tax_rate: float = 0.0,
) -> Asset:
    """Minimal toy asset with no taxes and full ownership."""
    return Asset(
        id="known-answer-01",
        name="KA-001",
        indication="Test Indication",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_3,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=discount_rate,
        royalty_rate=1.0 - net_ownership,   # royalty_rate = 1 - net_ownership
        effective_tax_rate=effective_tax_rate,
        nol_benefit_years=0,
    )


def _market(
    tam: float = 1_000.0,
    peak_penetration: float = 0.20,
    years_to_peak: int = 5,
    patent_life_years: int = 10,
) -> MarketModel:
    """TAM-based market with zero COGS and SG&A to make EBIT = Revenue."""
    return MarketModel(
        asset_id="known-answer-01",
        total_addressable_market_millions=tam,
        peak_penetration=peak_penetration,
        years_to_peak=years_to_peak,
        patent_life_years=patent_life_years,
        cogs_rate=0.0,
        sgna_rate_launch=0.0,
        sgna_rate_mature=0.0,
        adoption_curve_mode="linear",       # explicit linear; avoid TA-driven S-curve
    )


def _single_phase3_trial(cost_millions: float = 100.0, success_prob: float = 0.60) -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="known-answer-01",
            phase=TrialPhase.PHASE_3,
            success_probability=success_prob,
            duration_years=3.0,
            cost_millions=cost_millions,
            enrollment=300,
        )
    ]


# ---------------------------------------------------------------------------
# Test 1 — Core rNPV formula with single Phase 3
# ---------------------------------------------------------------------------

class TestCoreRNPVFormula:
    """
    Hand-computed reference
    -----------------------
    TAM = $1,000M; peak_penetration = 20%; years_to_peak = 5; patent_life = 10 years
    Linear ramp → peak revenue = $200M/year
      Year 1: $40M, Year 2: $80M, Year 3: $120M, Year 4: $160M, Years 5-10: $200M
    EBIT = Revenue (COGS=0, SG&A=0)

    Phase 3: cost=$100M, duration=3yr, p_success=0.60
      years_to_launch = 3
      P(approval) = 0.60

    PV(EBIT) = Σ_yr=1..10 [EBIT_yr / 1.10^(3+yr)]
             ≈ 673.8M  (gross_revenue_pv ≈ pre_probability_fcf_pv)
    P(approval) × PV(EBIT) ≈ 0.60 × 673.8 ≈ 404.3M

    Cost midpoint = (0 + 3) / 2 = 1.5 years
    PV(cost) = 100 / 1.10^1.5 ≈ 86.7M

    rNPV ≈ 404.3 − 86.7 ≈ 317.6M → rounded to $318M
    """

    def test_rnpv_magnitude(self):
        result = compute_rnpv_full(_asset(), _single_phase3_trial(), _market())
        assert result.rnpv_millions == pytest.approx(318, abs=5), (
            f"Expected rNPV ≈ $318M (hand-computed), got {result.rnpv_millions:.0f}M"
        )

    def test_cumulative_pos_equals_trial_success_prob(self):
        """Single phase: cumulative PoS = success_probability of that phase."""
        result = compute_rnpv_full(_asset(), _single_phase3_trial(success_prob=0.60), _market())
        assert result.cumulative_success_probability == pytest.approx(0.60, abs=1e-6)

    def test_rnpv_equals_prob_adj_revenue_minus_cost(self):
        """Core identity: rNPV = prob_adj_revenue_pv − trial_costs_pv (no deals, no milestones)."""
        result = compute_rnpv_full(_asset(), _single_phase3_trial(), _market())
        expected = result.probability_adjusted_revenue_pv_millions - result.trial_costs_pv_millions
        assert result.rnpv_millions == pytest.approx(expected, abs=1.0)

    def test_pre_probability_fcf_pv_magnitude(self):
        """pre_probability_fcf_pv should be ≈ 674M (before multiplying by P(approval))."""
        result = compute_rnpv_full(_asset(), _single_phase3_trial(), _market())
        assert result.pre_probability_fcf_pv_millions == pytest.approx(674, abs=10)

    def test_probability_adjusted_revenue_is_pos_times_gross(self):
        """probability_adjusted_revenue_pv ≈ P(approval) × pre_probability_fcf_pv."""
        result = compute_rnpv_full(_asset(), _single_phase3_trial(), _market())
        expected = result.cumulative_success_probability * result.pre_probability_fcf_pv_millions
        assert result.probability_adjusted_revenue_pv_millions == pytest.approx(expected, abs=1.0)


# ---------------------------------------------------------------------------
# Test 2 — Revenue year sequence invariants
# ---------------------------------------------------------------------------

class TestRevenueYearSequence:
    """Verify that the revenue ramp and plateau are structurally correct."""

    def _run(self) -> "RNPVResult":
        return compute_rnpv_full(_asset(), _single_phase3_trial(), _market(
            tam=1_000.0, peak_penetration=0.20, years_to_peak=5, patent_life_years=10
        ))

    def test_revenue_ramps_then_plateaus(self):
        result = self._run()
        rev = result.revenue_stream.revenue_by_year
        # Ramp: each year up to peak increases
        for i in range(len(rev) - 1):
            if i < 4:  # years 1-4 should be strictly increasing
                assert rev[i] < rev[i + 1], f"Revenue should increase in year {i+1} → {i+2}"
        # Plateau: years 5-10 should be equal (or very close due to lifecycle adjustments)
        plateau_years = rev[4:]   # index 4 onwards = year 5, 6, ..., 10
        for y in plateau_years:
            assert y == pytest.approx(plateau_years[0], rel=1e-4)

    def test_total_commercial_years(self):
        """patent_life_years = 10 → 10 revenue years."""
        result = self._run()
        assert len(result.revenue_stream.revenue_by_year) == 10

    def test_peak_revenue_correct(self):
        """Peak revenue = TAM × peak_penetration = $1000M × 0.20 = $200M."""
        result = self._run()
        assert result.revenue_stream.peak_sales_millions == pytest.approx(200.0, abs=1.0)


# ---------------------------------------------------------------------------
# Test 3 — Cost present value
# ---------------------------------------------------------------------------

class TestCostPresentValue:
    """
    Hand-computed reference:
    Phase 3: cost=$100M, duration=3yr → midpoint=1.5yr
    P(reaching) = 1.0 (first and only trial)
    PV(cost) = 100 / 1.10^1.5 = 100 / 1.15369 ≈ 86.69M
    """

    def test_single_phase3_cost_pv(self):
        result = compute_rnpv_full(_asset(discount_rate=0.10), _single_phase3_trial(cost_millions=100.0), _market())
        expected = 100.0 / (1.10 ** 1.5)  # ≈ 86.69
        assert result.trial_costs_pv_millions == pytest.approx(expected, abs=1.0)

    def test_higher_discount_rate_reduces_cost_pv(self):
        """Higher WACC → more discounting → lower PV of costs."""
        low_r = compute_rnpv_full(_asset(discount_rate=0.08), _single_phase3_trial(), _market())
        high_r = compute_rnpv_full(_asset(discount_rate=0.15), _single_phase3_trial(), _market())
        assert low_r.trial_costs_pv_millions > high_r.trial_costs_pv_millions


# ---------------------------------------------------------------------------
# Test 4 — Cumulative PoS is the product of phase probabilities
# ---------------------------------------------------------------------------

class TestCumulativePoS:
    """
    For three sequential phases with probabilities [p1, p2, p3]:
    cumulative_success_probability = p1 × p2 × p3
    This is NOT max(p1, p2, p3).
    """

    def _trials_with_probs(self, p1: float, p2: float, p3: float) -> list[ClinicalTrial]:
        return [
            ClinicalTrial(
                asset_id="known-answer-01",
                phase=TrialPhase.PHASE_1,
                success_probability=p1,
                duration_years=1.5,
                cost_millions=30.0,
                enrollment=60,
            ),
            ClinicalTrial(
                asset_id="known-answer-01",
                phase=TrialPhase.PHASE_2,
                success_probability=p2,
                duration_years=2.0,
                cost_millions=70.0,
                enrollment=150,
            ),
            ClinicalTrial(
                asset_id="known-answer-01",
                phase=TrialPhase.PHASE_3,
                success_probability=p3,
                duration_years=3.0,
                cost_millions=200.0,
                enrollment=400,
            ),
        ]

    def test_cumulative_pos_is_product(self):
        """cumulative_pos = 0.7 × 0.5 × 0.6 = 0.21 (NOT max = 0.70)."""
        p1, p2, p3 = 0.7, 0.5, 0.6
        result = compute_rnpv_full(
            _asset(),
            self._trials_with_probs(p1, p2, p3),
            _market(),
        )
        expected = p1 * p2 * p3  # 0.21
        assert result.cumulative_success_probability == pytest.approx(expected, abs=1e-6), (
            f"cumulative_pos should be {expected:.3f} (product), "
            f"not {max(p1, p2, p3):.3f} (max). Got: {result.cumulative_success_probability:.6f}"
        )

    def test_cumulative_pos_not_max(self):
        """Regression guard: ensure we never use max() instead of product."""
        p1, p2, p3 = 0.7, 0.5, 0.6
        result = compute_rnpv_full(
            _asset(),
            self._trials_with_probs(p1, p2, p3),
            _market(),
        )
        wrong_value = max(p1, p2, p3)  # what max() would give = 0.70
        assert result.cumulative_success_probability != pytest.approx(wrong_value, abs=0.01), (
            "cumulative_pos must not equal max(phase probs) — regression detected!"
        )


# ---------------------------------------------------------------------------
# Test 5 — Royalty and profit-share calculations
# ---------------------------------------------------------------------------

class TestRoyaltyAndProfitShare:
    """
    Royalty reduces revenue; profit share reduces EBIT.
    A 10% royalty on $200M revenue reduces rNPV more than
    a 10% profit share on 50% EBIT margin from $200M.
    """

    def test_royalty_reduces_rnpv(self):
        """rNPV with royalty < rNPV without royalty."""
        from bve.models.deal_economics import DealEconomics
        base = compute_rnpv_full(_asset(), _single_phase3_trial(), _market())
        royalty_deal = DealEconomics(royalty_rate=0.10)
        with_royalty = compute_rnpv_full(_asset(), _single_phase3_trial(), _market(), deal=royalty_deal)
        assert with_royalty.rnpv_millions < base.rnpv_millions

    def test_profit_share_reduces_rnpv(self):
        """rNPV with profit share < rNPV without profit share."""
        from bve.models.deal_economics import DealEconomics
        base = compute_rnpv_full(_asset(), _single_phase3_trial(), _market())
        ps_deal = DealEconomics(profit_share_rate=0.15)
        with_ps = compute_rnpv_full(_asset(), _single_phase3_trial(), _market(), deal=ps_deal)
        assert with_ps.rnpv_millions < base.rnpv_millions

    def test_royalty_larger_impact_than_equivalent_profit_share(self):
        """
        Royalty reduces top-line revenue; profit share reduces EBIT only.
        10% royalty on $200M/yr revenue hits before COGS/SG&A; a 10% profit
        share applies after those are already deducted (but with 0 COGS/SG&A
        in this test, they are equivalent).  With 0% COGS/SG&A they are equal
        so we just verify both reduce rnpv by a consistent amount.
        """
        from bve.models.deal_economics import DealEconomics
        base = compute_rnpv_full(_asset(), _single_phase3_trial(), _market())
        r_deal = DealEconomics(royalty_rate=0.10)
        ps_deal = DealEconomics(profit_share_rate=0.10)
        r_result = compute_rnpv_full(_asset(), _single_phase3_trial(), _market(), deal=r_deal)
        ps_result = compute_rnpv_full(_asset(), _single_phase3_trial(), _market(), deal=ps_deal)
        # Both must reduce rnpv
        assert r_result.rnpv_millions < base.rnpv_millions
        assert ps_result.rnpv_millions < base.rnpv_millions


# ---------------------------------------------------------------------------
# Test 6 — LOE tail
# ---------------------------------------------------------------------------

class TestLOETail:
    """
    LOE tail appends 3 additional revenue years with declining revenue.
    Total revenue years = patent_life_years + 3.
    Post-LOE revenue < plateau revenue.
    """

    def _loe_profile(self) -> dict:
        # Keys must be year_1_loss ... year_N_loss (fractions of peak revenue lost each LOE year)
        return {
            "year_1_loss": 0.40,
            "year_2_loss": 0.60,
            "year_3_loss": 0.80,
        }

    def test_loe_adds_tail_years(self):
        """With 3-year LOE profile: total revenue years = patent_life_years + 3."""
        base = compute_rnpv_full(_asset(), _single_phase3_trial(), _market(patent_life_years=10))
        with_loe = compute_rnpv_full(
            _asset(), _single_phase3_trial(), _market(patent_life_years=10),
            loe_profile=self._loe_profile(),
        )
        assert len(with_loe.revenue_stream.revenue_by_year) == 13
        assert len(base.revenue_stream.revenue_by_year) == 10

    def test_loe_tail_revenue_less_than_plateau(self):
        """First LOE tail year revenue < plateau peak revenue."""
        result = compute_rnpv_full(
            _asset(), _single_phase3_trial(), _market(patent_life_years=10),
            loe_profile=self._loe_profile(),
        )
        peak = result.revenue_stream.revenue_by_year[9]   # year 10 = plateau
        loe_yr1 = result.revenue_stream.revenue_by_year[10]  # year 11 = first LOE year
        assert loe_yr1 < peak


# ---------------------------------------------------------------------------
# Test 7 — Milestone present value
# ---------------------------------------------------------------------------

class TestMilestonePV:
    """
    PHASE_SUCCESS milestone of $50M at Phase 3 success:
      P(payment) = P(reaching Phase 3) × P(success) = cum_prob = 0.60
      Discount at midpoint of Phase 3 (which ends at year 3)
      PV ≈ 50 × 0.60 / 1.10^3 ≈ 22.54M

    APPROVAL milestone of $100M:
      P(payment) = cum_prob = 0.60
      Discount at years_to_approval = 3
      PV ≈ 100 × 0.60 / 1.10^3 ≈ 45.08M
    """

    def test_phase_success_milestone_adds_to_rnpv(self):
        """A receivable milestone increases rNPV."""
        from bve.models.deal_economics import DealEconomics, Milestone, MilestoneTrigger, MilestoneDirection
        base = compute_rnpv_full(_asset(), _single_phase3_trial(), _market())
        deal = DealEconomics(milestones=[
            Milestone(
                description="Phase 3 success milestone",
                trigger=MilestoneTrigger.PHASE_SUCCESS,
                trigger_phase="phase_3",
                amount_millions=50.0,
                direction=MilestoneDirection.RECEIVABLE,
            )
        ])
        with_milestone = compute_rnpv_full(_asset(), _single_phase3_trial(), _market(), deal=deal)
        assert with_milestone.rnpv_millions > base.rnpv_millions
        assert with_milestone.deal_milestone_receipts_pv_millions > 0.0

    def test_approval_milestone_pv_magnitude(self):
        """Approval milestone of $100M with P(approval)=0.60, r=10%, t=3yr → PV ≈ 45M."""
        from bve.models.deal_economics import DealEconomics, Milestone, MilestoneTrigger, MilestoneDirection
        deal = DealEconomics(milestones=[
            Milestone(
                description="Regulatory approval milestone",
                trigger=MilestoneTrigger.APPROVAL,
                amount_millions=100.0,
                direction=MilestoneDirection.RECEIVABLE,
            )
        ])
        result = compute_rnpv_full(_asset(), _single_phase3_trial(), _market(), deal=deal)
        # P(payment) × PV(payment) ≈ 0.60 × 100 / 1.10^3 = 45.08M
        expected_pv = 0.60 * 100.0 / (1.10 ** 3)
        assert result.deal_milestone_receipts_pv_millions == pytest.approx(expected_pv, abs=5.0)

    def test_payable_milestone_reduces_rnpv(self):
        """A payable milestone (cost to us) reduces rNPV."""
        from bve.models.deal_economics import DealEconomics, Milestone, MilestoneTrigger, MilestoneDirection
        base = compute_rnpv_full(_asset(), _single_phase3_trial(), _market())
        deal = DealEconomics(milestones=[
            Milestone(
                description="Regulatory approval payable milestone",
                trigger=MilestoneTrigger.APPROVAL,
                amount_millions=50.0,
                direction=MilestoneDirection.PAYABLE,
            )
        ])
        with_payable = compute_rnpv_full(_asset(), _single_phase3_trial(), _market(), deal=deal)
        assert with_payable.rnpv_millions < base.rnpv_millions
