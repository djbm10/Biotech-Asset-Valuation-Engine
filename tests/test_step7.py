"""
Step 7 regression fixtures — protected platform baselines.

Each fixture is a fully specified named asset with locked expected outputs.
Any change to model logic, discounting, LOE profiles, or deal math that
shifts these values will cause a test failure here.

Fixture inventory
-----------------
Sprint 9 note: All rNPV values updated after UFCF/tax fix (Task 9.1).
Effective tax rate 21% applied to EBIT before discounting. Pre-Sprint-9
values in parentheses for reference.

CANONICAL_NO_LOE        oncology / small_molecule, Phase 2 entry, no LOE, no deal
                        rNPV=65.0 (was 65.13 pre-9.12; was 118.72 pre-Sprint-9), POS=17.70%, trial_costs=136.4, rev_pv=202.0

CANONICAL_LOE           same asset + small_molecule LOE tail (5-year tail post Sprint 9.10)
                        rNPV=83.0 (was 83.13 pre-9.12; was 81.01 pre-9.10; was 138.82 pre-Sprint-9)

CANONICAL_LOE_DEAL      same asset + LOE + deal (royalty=10%, cdev=70%, upfront_cost=20,
                        payable milestone $50M on approval, receivable milestone $75M on approval)
                        rNPV=84.0 (was 84.27 pre-9.12; was 82.36 pre-9.10), net_ownership=0.90
                        Note: at 21% tax rate, cost-sharing benefit (30% of 136M costs = 41M)
                        slightly exceeds royalty + deal cost drag → deal is marginally accretive.

RARE_DISEASE            rare_disease / biologic, Phase 2 entry, smaller market / higher POS
                        no-LOE: rNPV=204.0 (was 204.38 pre-9.12; was 270.33 pre-Sprint-9), POS=24.83%
                        biologic LOE: rNPV=228.0 (was 228.04 pre-9.12; was 223.19 pre-9.10; was 294.15 pre-Sprint-9)

COMPETITIVE_ONCOLOGY    canonical oncology + two competitors (1 approved, 1 phase_3)
                        LOE: rNPV=3.0 (was 2.71 pre-9.12; was 1.41 pre-9.10; was 38.06 pre-Sprint-9; competition erodes market)

NEGATIVE_ASSET          CNS Phase 3 entry, low POS (10.5%), very high costs, small market
                        rNPV=-318.0 (was -318.42 pre-9.12; was -317.69; costs dominate; pipeline value is negative)

MC distribution snapshots (seed=0, n=1000) — locked percentile vectors
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.competition_model import CompetitionModel, CompetitorLaunch
from bve.models.deal_economics import DealEconomics, Milestone, MilestoneDirection, MilestoneTrigger
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams, run_monte_carlo
from bve.models.rnpv_model import RNPVResult, compute_rnpv_full


# ---------------------------------------------------------------------------
# Fixture definitions — all inputs are explicit and deterministic
# ---------------------------------------------------------------------------

def _loe(modality: str = "small_molecule") -> dict:
    return dict(AssumptionsLoader.get().loe_erosion_profile(modality))


# --- CANONICAL ---

def _canonical_asset() -> Asset:
    return Asset(
        id="reg-canonical", name="Canonical Oncology", indication="advanced solid tumors",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.10,
    )


def _canonical_trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(asset_id="reg-canonical", phase=TrialPhase.PHASE_2,
                      success_probability=0.37, duration_years=2.5, cost_millions=80.0),
        ClinicalTrial(asset_id="reg-canonical", phase=TrialPhase.PHASE_3,
                      success_probability=0.55, duration_years=3.5, cost_millions=250.0),
        ClinicalTrial(asset_id="reg-canonical", phase=TrialPhase.NDA_BLA,
                      success_probability=0.87, duration_years=1.5, cost_millions=35.0),
    ]


def _canonical_market() -> MarketModel:
    return MarketModel(
        asset_id="reg-canonical",
        total_addressable_market_millions=8_000.0,
        peak_penetration=0.12,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.18,
        sgna_rate_launch=0.40,
        sgna_rate_mature=0.20,
    )


# --- RARE DISEASE ---

def _rare_asset() -> Asset:
    return Asset(
        id="reg-rare", name="Rare Disease Biologic", indication="ultra-rare metabolic",
        therapeutic_area=TherapeuticArea.RARE_DISEASE,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.BIOLOGIC,
        discount_rate=0.10,
    )


def _rare_trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(asset_id="reg-rare", phase=TrialPhase.PHASE_2,
                      success_probability=0.45, duration_years=2.0, cost_millions=25.0),
        ClinicalTrial(asset_id="reg-rare", phase=TrialPhase.PHASE_3,
                      success_probability=0.62, duration_years=3.0, cost_millions=60.0),
        ClinicalTrial(asset_id="reg-rare", phase=TrialPhase.NDA_BLA,
                      success_probability=0.89, duration_years=1.0, cost_millions=10.0),
    ]


def _rare_market() -> MarketModel:
    # Small patient population, orphan pricing, longer patent life
    return MarketModel(
        asset_id="reg-rare",
        total_addressable_market_millions=1_500.0,
        peak_penetration=0.45,
        years_to_peak=4,
        patent_life_years=15,
        cogs_rate=0.25,
    )


# --- COMPETITIVE ONCOLOGY ---

def _competitive_market() -> MarketModel:
    comp = CompetitionModel(competitors=[
        CompetitorLaunch(
            name="Established SoC",
            status="approved",
            launch_year_relative=-1.0,
            peak_market_share=0.25,
            years_to_peak=3,
        ),
        CompetitorLaunch(
            name="Late Pipeline Rival",
            status="phase_3",
            launch_year_relative=2.0,
            peak_market_share=0.20,
            years_to_peak=3,
            approval_probability=0.70,
        ),
    ])
    return _canonical_market().model_copy(update={"competition_model": comp, "uptake_curve": None})


# --- NEGATIVE ASSET ---

def _negative_asset() -> Asset:
    return Asset(
        id="reg-neg", name="Late CNS Candidate", indication="treatment-resistant depression",
        therapeutic_area=TherapeuticArea.CNS,
        stage=DevelopmentStage.PHASE_3,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.15,
    )


def _negative_trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(asset_id="reg-neg", phase=TrialPhase.PHASE_3,
                      success_probability=0.15, duration_years=5.0, cost_millions=450.0),
        ClinicalTrial(asset_id="reg-neg", phase=TrialPhase.NDA_BLA,
                      success_probability=0.70, duration_years=2.0, cost_millions=60.0),
    ]


def _negative_market() -> MarketModel:
    return MarketModel(
        asset_id="reg-neg",
        total_addressable_market_millions=1_200.0,
        peak_penetration=0.06,
        years_to_peak=6,
        patent_life_years=8,
        cogs_rate=0.30,
    )


# --- DEAL TERMS for CANONICAL_LOE_DEAL ---

def _canonical_deal() -> DealEconomics:
    return DealEconomics(
        royalty_rate=0.10,
        cdev_cost_share=0.70,
        upfront_cost_millions=20.0,
        milestones=[
            Milestone(
                description="Approval milestone (payable)",
                amount_millions=50.0,
                trigger=MilestoneTrigger.APPROVAL,
                direction=MilestoneDirection.PAYABLE,
            ),
            Milestone(
                description="Approval receipt (receivable)",
                amount_millions=75.0,
                trigger=MilestoneTrigger.APPROVAL,
                direction=MilestoneDirection.RECEIVABLE,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# TestCanonicalNoLOE — rNPV=118.72, POS=17.70%, 7.5yr to launch
# ---------------------------------------------------------------------------

# FIXTURE PROVENANCE:
#   Why:         Establishes the zero-point reference for all other fixtures.
#                No LOE tail, no deal overlay — the simplest possible valuation.
#                Every other fixture is measured as a delta from this baseline.
#   Protects:    Core rNPV formula: probability weighting, phase-by-phase cost
#                discounting at midpoint, SG&A ramp (40% → 20% over 5yr), and
#                EBIT-based revenue projection.
#   Should change: If the core discounting formula, SG&A ramp, or cost-midpoint
#                  convention changes. Re-lock values after deliberate model update.
#   Must not change: Without a documented, intentional model change. A drift here
#                    implicates ProbabilityModel, CostModel, or RevenueModel.
class TestCanonicalNoLOE:
    """
    Baseline: no LOE tail, no deal.  Every other fixture is measured against this.
    This is the canonical pre-LOE, pre-deal reference point.
    """

    def _result(self) -> RNPVResult:
        return compute_rnpv_full(_canonical_asset(), _canonical_trials(), _canonical_market())

    def test_rnpv_locked(self):
        # Sprint 9.12: updated to 65.0 after 0dp rounding (was 65.13 pre-9.12; was 118.72 pre-Sprint-9)
        assert self._result().rnpv_millions == pytest.approx(65.0, abs=0.5)

    def test_cumulative_pos_locked(self):
        # 0.37 × 0.55 × 0.87 — pure float multiplication, no stored rounding
        assert self._result().cumulative_success_probability == pytest.approx(0.177045, rel=1e-9)

    def test_years_to_launch_locked(self):
        assert self._result().years_to_launch == pytest.approx(7.5, rel=1e-6)

    def test_trial_costs_pv_locked(self):
        assert self._result().trial_costs_pv_millions == pytest.approx(136.4, abs=0.1)

    def test_prob_adjusted_revenue_pv_locked(self):
        # Sprint 9.12: updated to 202.0 after 0dp rounding (was 201.58 pre-9.12; was 255.17 pre-Sprint-9)
        assert self._result().probability_adjusted_revenue_pv_millions == pytest.approx(202.0, abs=0.5)

    def test_no_loe_tail_in_revenue_stream(self):
        r = self._result()
        assert r.revenue_stream.loe_tail_years == 0
        assert r.revenue_stream.total_years == 12

    def test_no_deal_fields_are_zero(self):
        r = self._result()
        assert r.deal_milestone_receipts_pv_millions == 0.0
        assert r.upfront_receipt_millions == 0.0
        assert r.net_ownership == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# TestCanonicalLOE — rNPV=138.82, 3-year small_molecule tail
# ---------------------------------------------------------------------------

# FIXTURE PROVENANCE:
#   Why:         Verifies that the LOE tail revenue is correctly computed and
#                threaded from ValuationEngine → RevenueModel → revenue_stream.
#                Captures the small_molecule 3-year tail with its specific
#                erosion curve from AssumptionsLoader.
#   Protects:    loe_profile dict threading (ValuationEngine.run → RevenueModel.compute),
#                RevenueModel._build_revenue_stream() LOE tail logic,
#                revenue_stream.loe_tail_years / total_years accounting.
#   Should change: If LOE tail year count or erosion coefficients in settings.yaml
#                  are updated. Re-lock rNPV after any assumption recalibration.
#   Must not change: LOE rNPV must always exceed no-LOE rNPV (tail is additive revenue).
#                    POS and trial costs must be identical to no-LOE fixture.
class TestCanonicalLOE:
    """LOE tail adds ~20M to rNPV relative to no-LOE baseline."""

    def _result(self) -> RNPVResult:
        return compute_rnpv_full(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            loe_profile=_loe("small_molecule"),
        )

    def test_rnpv_locked(self):
        # Sprint 9.12: updated to 83.0 after 0dp rounding (was 83.13 pre-9.12; was 81.01 pre-9.10)
        assert self._result().rnpv_millions == pytest.approx(83.0, abs=0.5)

    def test_loe_exceeds_no_loe(self):
        no_loe = compute_rnpv_full(_canonical_asset(), _canonical_trials(), _canonical_market())
        assert self._result().rnpv_millions > no_loe.rnpv_millions

    def test_loe_tail_years_is_5(self):
        # Sprint 9.10: extended from 3 to 5 tail years
        assert self._result().revenue_stream.loe_tail_years == 5

    def test_total_years_is_17(self):
        # patent_life=12 + 5 tail = 17 (Sprint 9.10)
        assert self._result().revenue_stream.total_years == 17

    def test_pos_unchanged_by_loe(self):
        """LOE only affects revenue, not POS or costs."""
        r_loe = self._result()
        r_no  = compute_rnpv_full(_canonical_asset(), _canonical_trials(), _canonical_market())
        assert r_loe.cumulative_success_probability == pytest.approx(
            r_no.cumulative_success_probability, rel=1e-9
        )
        assert r_loe.trial_costs_pv_millions == pytest.approx(
            r_no.trial_costs_pv_millions, rel=1e-9
        )


# ---------------------------------------------------------------------------
# TestCanonicalLOEDeal — rNPV=134.39, royalty=10%, cdev=70%
# ---------------------------------------------------------------------------

# FIXTURE PROVENANCE:
#   Why:         Exercises every branch of the DealEconomics stack on top of LOE:
#                royalty (reduces net_ownership), cost-share (reduces trial costs),
#                upfront payment (face-value subtraction), payable milestone
#                (probability-weighted + discounted cost), receivable milestone
#                (probability-weighted + discounted receipt).
#   Protects:    DealEconomics threading through CostModel and RNPVModel,
#                milestone_pv() discounting logic, net_ownership calculation,
#                upfront_cost_millions face-value subtraction.
#   Should change: If milestone discounting, cost-share treatment, or royalty
#                  application logic changes. Re-lock after deliberate model update.
#   Must not change: Deal must reduce rNPV vs LOE-only (net outflows > inflows).
#                    LOE+deal must still exceed no-LOE/no-deal baseline.
class TestCanonicalLOEDeal:
    """
    LOE + deal overlay.

    Deal terms:
      - royalty_rate=10%   → effective_ownership = 1.0 × 0.90 = 0.90
      - cdev_cost_share=70% → trial R&D costs at 70% of gross
      - upfront_cost=20M   → subtracted at face value (t=0)
      - payable milestone: $50M on approval (probability-weighted, discounted)
      - receivable milestone: $75M on approval (probability-weighted, discounted)

    Net effect: royalty and upfront+payable milestones reduce rNPV vs LOE-only baseline.
    The receivable milestone partially offsets costs.
    """

    def _result(self) -> RNPVResult:
        return compute_rnpv_full(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            loe_profile=_loe("small_molecule"),
            deal=_canonical_deal(),
        )

    def test_rnpv_locked(self):
        # Sprint 9.12: updated to 84.0 after 0dp rounding (was 84.27 pre-9.12; was 82.36 pre-9.10)
        assert self._result().rnpv_millions == pytest.approx(84.0, abs=0.5)

    def test_net_ownership_reflects_deal_royalty(self):
        # asset.royalty_rate=0, deal.royalty_rate=0.10 → 1.0 × 0.90 = 0.90 (exact)
        assert self._result().net_ownership == 0.90

    def test_milestone_payable_pv_locked(self):
        # $50M on approval, P(approval)=0.177045, discounted 7.5yr at 10%
        assert self._result().cost_stream.milestone_costs_pv_millions == pytest.approx(4.33, abs=0.05)

    def test_milestone_receivable_pv_locked(self):
        # $75M on approval, P(approval)=0.177045, discounted 7.5yr at 10%
        assert self._result().deal_milestone_receipts_pv_millions == pytest.approx(6.50, abs=0.05)

    def test_upfront_cost_at_face_value(self):
        assert self._result().cost_stream.upfront_cost_millions == pytest.approx(20.0)

    def test_deal_rnpv_close_to_loe_only(self):
        """Sprint 9 note: at 21% effective tax rate, cost-sharing benefit (30% of ~136M costs)
        slightly exceeds royalty + net deal cost drag → deal is marginally accretive vs loe-only.
        Pre-Sprint-9 pre-tax: deal reduced rNPV (royalty dominated). Post-Sprint-9 after-tax:
        cost savings dominate because they are pre-tax cash flows. Both cases are economically valid.
        Test verifies the deal rNPV stays within ±10M of the loe-only baseline."""
        loe_only = compute_rnpv_full(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            loe_profile=_loe("small_molecule"),
        )
        assert abs(self._result().rnpv_millions - loe_only.rnpv_millions) < 10.0

    def test_deal_rnpv_exceeds_no_loe_no_deal(self):
        """Despite deal costs, LOE tail still adds net value over the no-LOE/no-deal baseline."""
        baseline = compute_rnpv_full(_canonical_asset(), _canonical_trials(), _canonical_market())
        assert self._result().rnpv_millions > baseline.rnpv_millions


# ---------------------------------------------------------------------------
# TestRareDisease — higher POS, orphan market, biologic modality
# ---------------------------------------------------------------------------

# FIXTURE PROVENANCE:
#   Why:         Validates the biologic modality LOE profile and the rare_disease
#                therapeutic area's higher base POS rates. Also exercises the
#                longer patent life (15yr) and orphan pricing structure.
#   Protects:    TherapeuticArea.RARE_DISEASE POS base rates in PHASE_SUCCESS_RATES,
#                Modality.BIOLOGIC LOE profile from AssumptionsLoader,
#                patent_life_years interaction with LOE tail (15 + 3 = 18 total years).
#   Should change: If rare_disease POS assumptions are recalibrated, or if biologic
#                  LOE erosion rates are updated. Re-lock both no-LOE and LOE rNPV.
#   Must not change: Biologic LOE > no-LOE. Biologic LOE > small_molecule LOE for
#                    the same asset. Rare disease POS must exceed canonical oncology POS.
class TestRareDisease:
    """
    Rare disease fixture:
      - Higher base POS (rare_disease TA: P2=0.45, P3=0.62, NDA=0.89 → cumPOS≈0.2483)
      - Small patient population (TAM=1500M, pen=0.45 → peak_sales=675M)
      - Longer patent life (15yr) vs canonical (12yr)
      - Biologic modality → slower LOE erosion

    Expected: much higher rNPV than canonical despite smaller market, driven by
    high POS and favorable patent+LOE profile.
    """

    def _no_loe(self) -> RNPVResult:
        return compute_rnpv_full(_rare_asset(), _rare_trials(), _rare_market())

    def _with_loe(self) -> RNPVResult:
        return compute_rnpv_full(
            _rare_asset(), _rare_trials(), _rare_market(),
            loe_profile=_loe("biologic"),
        )

    def test_no_loe_rnpv_locked(self):
        # Sprint 9.12: updated to 204.0 after 0dp rounding (was 204.38 pre-9.12; was 270.33 pre-Sprint-9)
        assert self._no_loe().rnpv_millions == pytest.approx(204.0, abs=0.5)

    def test_biologic_loe_rnpv_locked(self):
        # Sprint 9.12: updated to 228.0 after 0dp rounding (was 228.04 pre-9.12; was 223.19 pre-9.10)
        assert self._with_loe().rnpv_millions == pytest.approx(228.0, abs=0.5)

    def test_cumulative_pos_locked(self):
        # 0.45 × 0.62 × 0.89 — pure float multiplication, no stored rounding
        assert self._no_loe().cumulative_success_probability == pytest.approx(0.24831, rel=1e-9)

    def test_years_to_launch_locked(self):
        # 2.0 + 3.0 + 1.0 = 6.0yr
        assert self._no_loe().years_to_launch == pytest.approx(6.0, rel=1e-6)

    def test_rare_disease_higher_pos_than_canonical(self):
        rare = self._no_loe()
        canonical = compute_rnpv_full(_canonical_asset(), _canonical_trials(), _canonical_market())
        assert rare.cumulative_success_probability > canonical.cumulative_success_probability

    def test_biologic_loe_exceeds_no_loe(self):
        assert self._with_loe().rnpv_millions > self._no_loe().rnpv_millions

    def test_biologic_loe_exceeds_sm_loe_for_same_asset(self):
        """Biologic erodes more slowly than small_molecule → higher LOE rNPV."""
        # Use rare asset but switch to sm LOE profile (hypothetical comparison)
        sm_loe_result = compute_rnpv_full(
            _rare_asset(), _rare_trials(), _rare_market(),
            loe_profile=_loe("small_molecule"),
        )
        assert self._with_loe().rnpv_millions > sm_loe_result.rnpv_millions

    def test_loe_tail_years_is_5(self):
        # Sprint 9.10: extended from 3 to 5 tail years
        assert self._with_loe().revenue_stream.loe_tail_years == 5

    def test_total_years_with_loe(self):
        # patent_life=15 + 5 tail = 20 (Sprint 9.10)
        assert self._with_loe().revenue_stream.total_years == 20


# ---------------------------------------------------------------------------
# TestCompetitiveOncology — market haircut from two competitors
# ---------------------------------------------------------------------------

# FIXTURE PROVENANCE:
#   Why:         Validates that CompetitionModel market haircuts flow correctly
#                through the full valuation stack. Uses a mix of an approved
#                competitor (always present) and a phase_3 rival (approval_probability=0.70).
#                The deterministic base case uses the full pipeline competitor
#                (approval_probability not sampled in compute_rnpv_full).
#   Protects:    CompetitionModel.our_available_market_fraction() computation,
#                MarketModel → RevenueModel market-share reduction,
#                confirmed that competition affects revenue but NOT POS or costs.
#   Should change: If the competition model timing logic or market-share ramp
#                  algorithm changes. Re-lock rNPV and peak_sales.
#   Must not change: Competition must reduce rNPV. POS and trial costs must be
#                    identical to the no-competition canonical fixture.
class TestCompetitiveOncology:
    """
    Same canonical asset/trials, but with an approved competitor (-25% market share)
    and a Phase 3 pipeline rival (P(approval)=70%, +20% market share at peak).

    Competition substantially reduces available market fraction → much lower rNPV.
    """

    def _result(self) -> RNPVResult:
        return compute_rnpv_full(
            _canonical_asset(), _canonical_trials(), _competitive_market(),
            loe_profile=_loe("small_molecule"),
        )

    def _no_comp_result(self) -> RNPVResult:
        return compute_rnpv_full(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            loe_profile=_loe("small_molecule"),
        )

    def test_rnpv_locked(self):
        # Sprint 9.12: updated to 3.0 after 0dp rounding (was 2.71 pre-9.12; was 1.41 pre-9.10)
        assert self._result().rnpv_millions == pytest.approx(3.0, abs=0.5)

    def test_competition_reduces_rnpv_vs_no_competition(self):
        assert self._result().rnpv_millions < self._no_comp_result().rnpv_millions

    def test_competition_reduces_peak_sales(self):
        assert self._result().peak_sales_millions < self._no_comp_result().peak_sales_millions

    def test_peak_sales_locked(self):
        # canonical peak_sales = 960M; competition reduces available fraction
        assert self._result().peak_sales_millions == pytest.approx(586.0, abs=0.5)

    def test_pos_unchanged_by_competition(self):
        """Competition affects revenue, not POS or trial timing."""
        assert self._result().cumulative_success_probability == pytest.approx(
            self._no_comp_result().cumulative_success_probability, rel=1e-9
        )

    def test_trial_costs_unchanged_by_competition(self):
        """Competition affects revenue, not costs."""
        assert self._result().trial_costs_pv_millions == pytest.approx(
            self._no_comp_result().trial_costs_pv_millions, rel=1e-9
        )


# ---------------------------------------------------------------------------
# TestNegativeAsset — costs exceed revenue; rNPV is negative
# ---------------------------------------------------------------------------

# FIXTURE PROVENANCE:
#   Why:         Verifies the engine correctly handles negative rNPV without
#                flooring at zero. High trial costs ($450M Phase 3 + $60M NDA),
#                very low POS (10.5%), and a small market produce a deeply
#                negative expected value. Ensures cost-dominated pipelines are
#                faithfully represented.
#   Protects:    RNPVModel subtraction (rNPV = prob_adj_revenue - prob_weighted_costs),
#                no accidental clamping or abs() of the final result,
#                MC probability_positive ≈ 0 for cost-dominated assets.
#   Should change: If CNS base POS rates, cost discounting, or revenue model
#                  changes shift the magnitude. Re-lock rNPV and cost/rev PVs.
#   Must not change: rNPV must remain negative for these inputs. The engine must
#                    not floor or truncate negative values anywhere in the pipeline.
class TestNegativeAsset:
    """
    Late-stage CNS asset with very low POS (10.5%) and high costs.
    Revenue (probability-adjusted) is far below probability-weighted costs.

    This fixture verifies the engine handles negative rNPV correctly:
      - rNPV=-317.69 (locked)
      - MC mean near -318M (locked)
      - probability_positive ≈ 0.0 (essentially zero chance of positive NPV)
    """

    def _result(self) -> RNPVResult:
        return compute_rnpv_full(_negative_asset(), _negative_trials(), _negative_market())

    def test_rnpv_is_negative(self):
        assert self._result().rnpv_millions < 0

    def test_rnpv_locked(self):
        # Sprint 9.12: updated to -318.0 after 0dp rounding (was -318.42 pre-9.12; was -317.69 pre-Sprint-9)
        assert self._result().rnpv_millions == pytest.approx(-318.0, abs=0.5)

    def test_cumulative_pos_locked(self):
        # 0.15 × 0.70 = 0.105 — pure float multiplication, no stored rounding
        assert self._result().cumulative_success_probability == pytest.approx(0.105, rel=1e-9)

    def test_costs_exceed_revenue(self):
        r = self._result()
        assert r.trial_costs_pv_millions > r.probability_adjusted_revenue_pv_millions

    def test_trial_costs_pv_locked(self):
        assert self._result().trial_costs_pv_millions == pytest.approx(321.19, abs=0.02)

    def test_prob_adjusted_revenue_pv_locked(self):
        """Very low POS × modest revenue = tiny probability-adjusted revenue.
        Sprint 9.12: updated to 3.0 after 0dp rounding (was 2.77 pre-9.12; was 3.50 pre-Sprint-9)."""
        assert self._result().probability_adjusted_revenue_pv_millions == pytest.approx(3.0, abs=0.5)

    def test_loe_does_not_rescue_negative_asset(self):
        """Even with LOE tail, asset remains deeply negative."""
        with_loe = compute_rnpv_full(
            _negative_asset(), _negative_trials(), _negative_market(),
            loe_profile=_loe("small_molecule"),
        )
        assert with_loe.rnpv_millions < 0


# ---------------------------------------------------------------------------
# TestMCDistributionSnapshots — locked percentile vectors (seed=0, n=1000)
# ---------------------------------------------------------------------------

class TestMCDistributionSnapshots:
    """
    Lock the full percentile distribution shape for key fixtures.
    Tolerances are wider (abs=5) to accommodate sampling noise at n=1000,
    but still detect material model changes.

    These also verify qualitative properties:
      - CANONICAL_LOE: wide distribution (binary POS × stochastic market), p_pos < 1
      - RARE_DISEASE_LOE: high POS → most simulations are positive, p_pos ≈ 1.0
      - NEGATIVE_ASSET: essentially all simulations negative, p_pos ≈ 0.0
    """

    _PARAMS = MonteCarloParams(n_simulations=1000, random_seed=0)

    def test_canonical_loe_mean_locked(self):
        mc = run_monte_carlo(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            self._PARAMS, loe_profile=_loe("small_molecule"),
        )
        # Sprint 9: updated to 85.96 after UFCF/tax fix (was 144.57 pre-Sprint-9)
        assert mc.mean_millions == pytest.approx(85.96, abs=5.0)

    def test_canonical_loe_p50_locked(self):
        mc = run_monte_carlo(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            self._PARAMS, loe_profile=_loe("small_molecule"),
        )
        # Sprint 9.19: updated to 45.0 after stage-conditional CV (Phase 2 CV: 0.35→0.45)
        # Wider CV increases peak_sales spread → lower P50; was 55.39 post-UFCF/tax fix
        assert mc.percentile_50_millions == pytest.approx(45.0, abs=8.0)

    def test_canonical_loe_p95_locked(self):
        mc = run_monte_carlo(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            self._PARAMS, loe_profile=_loe("small_molecule"),
        )
        # Sprint 9.19: updated to 360.0 after stage-conditional CV (Phase 2 CV: 0.35→0.45)
        # Wider CV raises the 95th percentile upside tail; was 310.09 post-UFCF/tax fix
        assert mc.percentile_95_millions == pytest.approx(360.0, abs=20.0)

    def test_canonical_loe_p5_locked(self):
        mc = run_monte_carlo(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            self._PARAMS, loe_profile=_loe("small_molecule"),
        )
        # Sprint 9: updated to -47.50 after UFCF/tax fix (was -28.68 pre-Sprint-9)
        assert mc.percentile_5_millions == pytest.approx(-47.50, abs=8.0)

    def test_canonical_loe_probability_positive_locked(self):
        mc = run_monte_carlo(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            self._PARAMS, loe_profile=_loe("small_molecule"),
        )
        # Sprint 9.19: updated to 0.719 after stage-conditional CV (Phase 2 CV: 0.35→0.45)
        # Wider CV pushes more simulations below zero; was 0.749 post-UFCF/tax fix
        assert mc.probability_positive == pytest.approx(0.719, abs=0.03)

    def test_canonical_loe_distribution_is_right_skewed(self):
        """Mean > median indicates right skew (log-normal peak sales distribution)."""
        mc = run_monte_carlo(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            self._PARAMS, loe_profile=_loe("small_molecule"),
        )
        assert mc.mean_millions > mc.median_millions

    def test_rare_disease_loe_mean_locked(self):
        mc = run_monte_carlo(
            _rare_asset(), _rare_trials(), _rare_market(),
            self._PARAMS, loe_profile=_loe("biologic"),
        )
        # Sprint 9: updated to 228.70 after UFCF/tax fix (was 301.02 pre-Sprint-9)
        assert mc.mean_millions == pytest.approx(228.70, abs=10.0)

    def test_rare_disease_loe_p50_locked(self):
        mc = run_monte_carlo(
            _rare_asset(), _rare_trials(), _rare_market(),
            self._PARAMS, loe_profile=_loe("biologic"),
        )
        # Sprint 9: updated to 194.57 after UFCF/tax fix (was 257.98 pre-Sprint-9)
        assert mc.percentile_50_millions == pytest.approx(194.57, abs=15.0)

    def test_rare_disease_loe_probability_positive_is_near_1(self):
        """High POS rare disease: essentially all simulations are positive."""
        mc = run_monte_carlo(
            _rare_asset(), _rare_trials(), _rare_market(),
            self._PARAMS, loe_profile=_loe("biologic"),
        )
        assert mc.probability_positive == pytest.approx(1.0, abs=0.01)

    def test_negative_asset_mean_locked(self):
        mc = run_monte_carlo(_negative_asset(), _negative_trials(), _negative_market(), self._PARAMS)
        assert mc.mean_millions == pytest.approx(-318.39, abs=5.0)

    def test_negative_asset_probability_positive_is_zero(self):
        """All simulations negative for a cost-dominated, low-POS asset."""
        mc = run_monte_carlo(_negative_asset(), _negative_trials(), _negative_market(), self._PARAMS)
        # Very small tolerance: effectively zero but not strict equality — a rare
        # positive draw from model evolution should not silently pass unnoticed
        assert mc.probability_positive == pytest.approx(0.0, abs=1e-6)

    def test_negative_asset_p50_locked(self):
        mc = run_monte_carlo(_negative_asset(), _negative_trials(), _negative_market(), self._PARAMS)
        assert mc.percentile_50_millions == pytest.approx(-318.31, abs=5.0)

    def test_negative_asset_tight_distribution(self):
        """
        Negative asset: costs are near-deterministic (low stochastic variance in costs).
        Very low POS means most draws fail → tight negative distribution.
        p95 - p5 should be much smaller than for canonical (which has wide POS × market spread).
        """
        mc_neg = run_monte_carlo(_negative_asset(), _negative_trials(), _negative_market(), self._PARAMS)
        mc_can = run_monte_carlo(
            _canonical_asset(), _canonical_trials(), _canonical_market(),
            self._PARAMS, loe_profile=_loe("small_molecule"),
        )
        spread_neg = mc_neg.percentile_95_millions - mc_neg.percentile_5_millions
        spread_can = mc_can.percentile_95_millions - mc_can.percentile_5_millions
        assert spread_neg < spread_can


# ---------------------------------------------------------------------------
# TestCrossFixtureInvariants — properties that must hold across all fixtures
# ---------------------------------------------------------------------------

class TestCrossFixtureInvariants:
    """
    Invariants that must hold regardless of which fixture is evaluated.
    These catch broad model changes that would affect all assets.
    """

    def test_loe_always_increases_rnpv(self):
        """Across all fixtures, adding LOE tail must never decrease rNPV."""
        for asset_fn, trials_fn, market_fn, loe_mod in [
            (_canonical_asset, _canonical_trials, _canonical_market, "small_molecule"),
            (_rare_asset, _rare_trials, _rare_market, "biologic"),
        ]:
            no_loe = compute_rnpv_full(asset_fn(), trials_fn(), market_fn())
            with_loe = compute_rnpv_full(asset_fn(), trials_fn(), market_fn(),
                                          loe_profile=_loe(loe_mod))
            assert with_loe.rnpv_millions > no_loe.rnpv_millions, \
                f"LOE should increase rNPV for {asset_fn().name}"

    def test_royalty_always_reduces_rnpv(self):
        """Adding a royalty must reduce rNPV for all positive-rNPV fixtures."""
        deal = DealEconomics(royalty_rate=0.10)
        for asset_fn, trials_fn, market_fn in [
            (_canonical_asset, _canonical_trials, _canonical_market),
            (_rare_asset, _rare_trials, _rare_market),
        ]:
            no_deal = compute_rnpv_full(asset_fn(), trials_fn(), market_fn(),
                                        loe_profile=_loe())
            with_deal = compute_rnpv_full(asset_fn(), trials_fn(), market_fn(),
                                          loe_profile=_loe(), deal=deal)
            assert with_deal.rnpv_millions < no_deal.rnpv_millions, \
                f"Royalty should reduce rNPV for {asset_fn().name}"

    def test_higher_discount_rate_always_reduces_positive_rnpv(self):
        """Higher discount rate → lower rNPV for positive-value assets."""
        for asset_fn, trials_fn, market_fn in [
            (_canonical_asset, _canonical_trials, _canonical_market),
            (_rare_asset, _rare_trials, _rare_market),
        ]:
            a_lo = asset_fn().model_copy(update={"discount_rate": 0.08})
            a_hi = asset_fn().model_copy(update={"discount_rate": 0.15})
            r_lo = compute_rnpv_full(a_lo, trials_fn(), market_fn()).rnpv_millions
            r_hi = compute_rnpv_full(a_hi, trials_fn(), market_fn()).rnpv_millions
            assert r_lo > r_hi, f"Higher rate should reduce rNPV for {asset_fn().name}"

    def test_competition_always_reduces_positive_rnpv(self):
        """Competition reduces available market fraction → lower rNPV."""
        comp = CompetitionModel(competitors=[
            CompetitorLaunch(name="Rival", status="approved",
                             launch_year_relative=0.0, peak_market_share=0.30, years_to_peak=3),
        ])
        for asset_fn, trials_fn, market_fn in [
            (_canonical_asset, _canonical_trials, _canonical_market),
            (_rare_asset, _rare_trials, _rare_market),
        ]:
            no_comp = compute_rnpv_full(asset_fn(), trials_fn(), market_fn())
            comp_market = market_fn().model_copy(update={"competition_model": comp, "uptake_curve": None})
            with_comp = compute_rnpv_full(asset_fn(), trials_fn(), comp_market)
            assert with_comp.rnpv_millions < no_comp.rnpv_millions, \
                f"Competition should reduce rNPV for {asset_fn().name}"

    def test_mc_mean_near_deterministic_across_fixtures(self):
        """
        MC mean (same context) should be within 60% of deterministic rNPV
        for positive-value assets (captures sampling noise at n=500).
        """
        params = MonteCarloParams(n_simulations=500, random_seed=0)
        for asset_fn, trials_fn, market_fn, loe_mod in [
            (_canonical_asset, _canonical_trials, _canonical_market, "small_molecule"),
            (_rare_asset, _rare_trials, _rare_market, "biologic"),
        ]:
            loe = _loe(loe_mod)
            det = compute_rnpv_full(asset_fn(), trials_fn(), market_fn(), loe_profile=loe).rnpv_millions
            mc = run_monte_carlo(asset_fn(), trials_fn(), market_fn(), params, loe_profile=loe)
            ratio = abs(mc.mean_millions - det) / max(1.0, abs(det))
            assert ratio < 0.60, \
                f"MC mean {mc.mean_millions:.1f} too far from det {det:.1f} for {asset_fn().name}"


# ---------------------------------------------------------------------------
# TestSerializationRoundTrip — DrugAssetProgram JSON round-trip
# ---------------------------------------------------------------------------

# FIXTURE PROVENANCE:
#   Why:         DrugAssetProgram is the institutional container for a valuation.
#                If its Pydantic schema cannot round-trip through JSON (e.g., a new
#                field type breaks serialization, or enum dict-keys lose their type),
#                stored programs become unreproducible. This test enforces that the
#                container is stable as a durable artifact.
#   Protects:    DrugAssetProgram.model_dump(mode='json') / model_validate() fidelity,
#                nested model serialization (Asset, ClinicalTrial, MarketModel,
#                CommercialPlan, DealEconomics, milestones),
#                TrialPhase enum keys in pos_adjusters/design_features dicts,
#                ValuationEngine.from_program() producing identical output for both.
#   Should change: If new field types are added that require custom serializers,
#                  update this test to verify the new fields round-trip correctly.
#   Must not change: rNPV and all derived outputs must be bit-identical after
#                    round-trip. Canonical JSON must be deterministically reproducible.
class TestSerializationRoundTrip:
    """DrugAssetProgram survives JSON serialization with identical valuation output."""

    import json as _json  # module-level for use in methods

    _COMPANY_KWARGS = dict(
        id="co-roundtrip", name="RoundTrip Co", ticker="RT",
        cash_millions=50.0, shares_outstanding_millions=100.0,
    )
    _MC = MonteCarloParams(n_simulations=100, random_seed=42)

    def _build_program(self, load_loe: bool = True, with_deal: bool = True):
        from bve.models.drug_asset_program import DrugAssetProgram
        return DrugAssetProgram.build(
            asset=_canonical_asset(),
            trials=_canonical_trials(),
            market_model=_canonical_market(),
            deal_economics=_canonical_deal() if with_deal else None,
            load_loe=load_loe,
        )

    def _run(self, program):
        from bve.entities.company import Company
        from bve.models.drug_asset_program import DrugAssetProgram
        from bve.valuation.valuation_engine import ValuationEngine
        company = Company(**self._COMPANY_KWARGS)
        return ValuationEngine.from_program(program, company, mc_params=self._MC).run()

    def test_round_trip_produces_identical_rnpv(self):
        from bve.models.drug_asset_program import DrugAssetProgram
        program = self._build_program()
        program2 = DrugAssetProgram.model_validate(program.model_dump(mode="json"))
        out1, out2 = self._run(program), self._run(program2)
        assert out1.rnpv.rnpv_millions == out2.rnpv.rnpv_millions

    def test_round_trip_produces_identical_revenue_pv(self):
        from bve.models.drug_asset_program import DrugAssetProgram
        program = self._build_program()
        program2 = DrugAssetProgram.model_validate(program.model_dump(mode="json"))
        out1, out2 = self._run(program), self._run(program2)
        assert (out1.rnpv.probability_adjusted_revenue_pv_millions
                == out2.rnpv.probability_adjusted_revenue_pv_millions)

    def test_round_trip_produces_identical_costs_pv(self):
        from bve.models.drug_asset_program import DrugAssetProgram
        program = self._build_program()
        program2 = DrugAssetProgram.model_validate(program.model_dump(mode="json"))
        out1, out2 = self._run(program), self._run(program2)
        assert out1.rnpv.trial_costs_pv_millions == out2.rnpv.trial_costs_pv_millions

    def test_round_trip_produces_identical_peak_sales(self):
        from bve.models.drug_asset_program import DrugAssetProgram
        program = self._build_program()
        program2 = DrugAssetProgram.model_validate(program.model_dump(mode="json"))
        out1, out2 = self._run(program), self._run(program2)
        assert out1.rnpv.peak_sales_millions == out2.rnpv.peak_sales_millions

    def test_round_trip_produces_identical_pos_and_launch(self):
        from bve.models.drug_asset_program import DrugAssetProgram
        program = self._build_program()
        program2 = DrugAssetProgram.model_validate(program.model_dump(mode="json"))
        out1, out2 = self._run(program), self._run(program2)
        assert out1.rnpv.cumulative_success_probability == out2.rnpv.cumulative_success_probability
        assert out1.rnpv.years_to_launch == out2.rnpv.years_to_launch

    def test_round_trip_preserves_loe_source(self):
        from bve.models.drug_asset_program import DrugAssetProgram
        program = self._build_program(load_loe=True)
        program2 = DrugAssetProgram.model_validate(program.model_dump(mode="json"))
        assert program2.commercial_plan.loe_source == program.commercial_plan.loe_source
        assert program2.commercial_plan.loe_profile == program.commercial_plan.loe_profile

    def test_round_trip_preserves_deal_terms(self):
        from bve.models.drug_asset_program import DrugAssetProgram
        program = self._build_program(with_deal=True)
        program2 = DrugAssetProgram.model_validate(program.model_dump(mode="json"))
        assert program2.deal_economics.royalty_rate == program.deal_economics.royalty_rate
        assert program2.deal_economics.cdev_cost_share == program.deal_economics.cdev_cost_share
        assert len(program2.deal_economics.milestones) == len(program.deal_economics.milestones)
        for m1, m2 in zip(program.deal_economics.milestones, program2.deal_economics.milestones):
            assert m1.amount_millions == m2.amount_millions
            assert m1.direction == m2.direction
            assert m1.trigger == m2.trigger

    def test_round_trip_preserves_enum_keys_in_pos_adjusters(self):
        """
        TrialPhase enum keys must survive JSON serialization.
        If Pydantic serializes them as strings and can't coerce them back,
        the dict will be empty after reload — silently breaking POS adjustments.
        """
        import json
        from bve.models.drug_asset_program import DrugAssetProgram
        from bve.models.pos_model import POSAdjusters

        # Build a program that has non-empty pos_adjusters
        from bve.entities.trial import TrialPhase
        pos = {TrialPhase.PHASE_2: POSAdjusters(), TrialPhase.PHASE_3: POSAdjusters()}
        program = DrugAssetProgram(
            asset=_canonical_asset(),
            trials=_canonical_trials(),
            market_model=_canonical_market(),
            pos_adjusters=pos,
        )
        program2 = DrugAssetProgram.model_validate(program.model_dump(mode="json"))
        assert set(program2.pos_adjusters.keys()) == set(program.pos_adjusters.keys())

    def test_canonical_json_is_deterministic(self):
        """
        Serializing the same program twice must produce identical JSON.
        Ensures the container has a stable representation for storage/caching.
        """
        import json
        from bve.models.drug_asset_program import DrugAssetProgram
        program = self._build_program()
        json1 = json.dumps(program.model_dump(mode="json"), sort_keys=True)
        json2 = json.dumps(program.model_dump(mode="json"), sort_keys=True)
        assert json1 == json2

    def test_reloaded_json_matches_original_canonical_json(self):
        """
        After one round-trip, the reloaded program's canonical JSON must match
        the original. Catches cases where round-trip silently transforms values
        (e.g., float precision loss, enum coercion side-effects).
        """
        import json
        from bve.models.drug_asset_program import DrugAssetProgram
        program = self._build_program()
        data = program.model_dump(mode="json")
        program2 = DrugAssetProgram.model_validate(data)
        json1 = json.dumps(data, sort_keys=True)
        json2 = json.dumps(program2.model_dump(mode="json"), sort_keys=True)
        assert json1 == json2
