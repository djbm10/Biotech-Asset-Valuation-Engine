"""
Step 3 tests: LOE erosion in RevenueModel.

Covers:
  - LOE tail is applied only when loe_profile is provided
  - Tail length is exactly 3 years
  - Revenue in tail years = peak_sales × (1 - loss_fraction)
  - Revenue monotonically decreases through tail years (erosion increases)
  - EBIT in tail years is positive and less than within-patent EBIT
  - by_segment_geography invariant holds including tail years
  - rNPV with LOE > rNPV without LOE (tail adds discounted value)
  - ValuationEngine applies LOE automatically from asset modality
  - Small molecule erodes faster than biologic in tail
  - compute_rnpv() wrapper (MC/scenario path) unaffected — no LOE applied
  - Locked regression: rNPV snapshot with small_molecule LOE = 138.82
"""
from __future__ import annotations

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
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
# Shared fixtures (same canonical setup as test_step2.py snapshot)
# ---------------------------------------------------------------------------

def _canonical_asset(modality: str = "small_molecule") -> Asset:
    return Asset(
        id="snap-001", name="SNAP-001", indication="Snapshot Test",
        therapeutic_area=TherapeuticArea.ONCOLOGY, stage=DevelopmentStage.PHASE_2,
        modality=Modality(modality), discount_rate=0.10,
    )


def _canonical_trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(asset_id="snap-001", phase=TrialPhase.PHASE_2,
                      success_probability=0.37, duration_years=2.5, cost_millions=80.0),
        ClinicalTrial(asset_id="snap-001", phase=TrialPhase.PHASE_3,
                      success_probability=0.55, duration_years=3.5, cost_millions=250.0),
        ClinicalTrial(asset_id="snap-001", phase=TrialPhase.NDA_BLA,
                      success_probability=0.87, duration_years=1.5, cost_millions=35.0),
    ]


def _canonical_market() -> MarketModel:
    return MarketModel(
        asset_id="snap-001", total_addressable_market_millions=8_000.0,
        peak_penetration=0.12, years_to_peak=5, patent_life_years=12,
        cogs_rate=0.18, sgna_rate_launch=0.40, sgna_rate_mature=0.20,
    )


def _loe(modality: str = "small_molecule") -> dict:
    return dict(AssumptionsLoader.get().loe_erosion_profile(modality))


def _run_with_loe(modality: str = "small_molecule"):
    asset = _canonical_asset(modality)
    trials = _canonical_trials()
    mm = _canonical_market()
    loe = _loe(modality)
    prob = ProbabilityModel.compute(asset, trials)
    rev = RevenueModel.compute(mm, loe_profile=loe)
    cost = CostModel.compute(prob, asset.discount_rate)
    return RNPVModel.compute(asset, prob, rev, cost)


def _run_without_loe():
    asset = _canonical_asset()
    trials = _canonical_trials()
    mm = _canonical_market()
    prob = ProbabilityModel.compute(asset, trials)
    rev = RevenueModel.compute(mm)  # no loe_profile
    cost = CostModel.compute(prob, asset.discount_rate)
    return RNPVModel.compute(asset, prob, rev, cost)


# ---------------------------------------------------------------------------
# TestLOETailStructure
# ---------------------------------------------------------------------------

class TestLOETailStructure:
    def test_no_loe_gives_zero_tail_years(self):
        rev = RevenueModel.compute(_canonical_market())
        assert rev.loe_tail_years == 0
        assert rev.total_years == 12

    def test_loe_adds_exactly_five_tail_years(self):
        # Sprint 9.10: extended from 3 to 5 tail years
        rev = RevenueModel.compute(_canonical_market(), loe_profile=_loe())
        assert rev.loe_tail_years == 5
        assert rev.total_years == 17

    def test_revenue_curve_length_with_loe(self):
        mm = _canonical_market()
        rev = RevenueModel.compute(mm, loe_profile=_loe())
        assert len(rev.revenue_by_year) == mm.patent_life_years + 5
        assert len(rev.ebit_by_year) == mm.patent_life_years + 5

    def test_patent_life_years_field_unchanged(self):
        """patent_life_years still reflects the core period, not the extended total."""
        mm = _canonical_market()
        rev = RevenueModel.compute(mm, loe_profile=_loe())
        assert rev.patent_life_years == mm.patent_life_years


# ---------------------------------------------------------------------------
# TestLOETailValues
# ---------------------------------------------------------------------------

class TestLOETailValues:
    def test_tail_revenue_equals_peak_times_retention(self):
        mm = _canonical_market()
        loe = _loe("small_molecule")
        rev = RevenueModel.compute(mm, loe_profile=loe)
        peak = rev.peak_sales_millions

        tail_1 = rev.revenue_by_year[12]  # year 13 = LOE year 1
        tail_2 = rev.revenue_by_year[13]
        tail_3 = rev.revenue_by_year[14]

        assert tail_1 == pytest.approx(peak * (1.0 - loe["year_1_loss"]), rel=1e-6)
        assert tail_2 == pytest.approx(peak * (1.0 - loe["year_2_loss"]), rel=1e-6)
        assert tail_3 == pytest.approx(peak * (1.0 - loe["year_3_loss"]), rel=1e-6)

    def test_tail_revenue_decreasing(self):
        rev = RevenueModel.compute(_canonical_market(), loe_profile=_loe())
        tail = rev.revenue_by_year[12:]
        for i in range(len(tail) - 1):
            assert tail[i] >= tail[i + 1], f"tail[{i}]={tail[i]} < tail[{i+1}]={tail[i+1]}"

    def test_tail_revenue_positive(self):
        rev = RevenueModel.compute(_canonical_market(), loe_profile=_loe())
        for r in rev.revenue_by_year[12:]:
            assert r > 0

    def test_tail_ebit_positive(self):
        rev = RevenueModel.compute(_canonical_market(), loe_profile=_loe())
        for e in rev.ebit_by_year[12:]:
            assert e > 0

    def test_tail_ebit_less_than_within_patent_ebit(self):
        rev = RevenueModel.compute(_canonical_market(), loe_profile=_loe())
        max_patent_ebit = max(rev.ebit_by_year[:12])
        for tail_ebit in rev.ebit_by_year[12:]:
            assert tail_ebit < max_patent_ebit

    def test_post_loe_ebit_margin_exceeds_pre_loe(self):
        """
        At LOE, SG&A collapses → EBIT margin rises even as revenue falls.
        EBIT margin = EBIT / revenue.  Post-LOE margin > mature branded margin.
        """
        mm = _canonical_market()
        rev = RevenueModel.compute(mm, loe_profile=_loe("small_molecule"))

        # Pre-LOE mature EBIT margin (last patent year)
        patent_rev_last = rev.revenue_by_year[11]
        patent_ebit_last = rev.ebit_by_year[11]
        pre_loe_margin = patent_ebit_last / patent_rev_last if patent_rev_last > 0 else 0.0

        # Post-LOE EBIT margin (first tail year)
        tail_rev = rev.revenue_by_year[12]
        tail_ebit = rev.ebit_by_year[12]
        post_loe_margin = tail_ebit / tail_rev if tail_rev > 0 else 0.0

        assert post_loe_margin > pre_loe_margin, (
            f"Post-LOE margin {post_loe_margin:.1%} should exceed "
            f"pre-LOE margin {pre_loe_margin:.1%}"
        )

    def test_post_loe_sgna_fraction_flows_from_profile(self):
        """post_loe_sgna_fraction in the profile is used, not hardcoded."""
        mm = _canonical_market()
        # Manually provide a profile with an extreme fraction
        minimal_sgna_profile = {
            "year_1_loss": 0.40, "year_2_loss": 0.65, "year_3_loss": 0.80,
            "terminal_loss": 0.85, "post_loe_sgna_fraction": 0.0,  # zero SG&A
        }
        max_sgna_profile = {
            "year_1_loss": 0.40, "year_2_loss": 0.65, "year_3_loss": 0.80,
            "terminal_loss": 0.85, "post_loe_sgna_fraction": 1.0,  # full SG&A
        }
        rev_min = RevenueModel.compute(mm, loe_profile=minimal_sgna_profile)
        rev_max = RevenueModel.compute(mm, loe_profile=max_sgna_profile)
        # Same revenue, different EBIT
        assert rev_min.revenue_by_year[12] == pytest.approx(rev_max.revenue_by_year[12], rel=1e-9)
        assert rev_min.ebit_by_year[12] > rev_max.ebit_by_year[12]

    def test_default_fraction_applies_when_absent(self):
        """Profile without post_loe_sgna_fraction key uses 0.30 default."""
        mm = _canonical_market()
        no_fraction = {
            "year_1_loss": 0.40, "year_2_loss": 0.65, "year_3_loss": 0.80,
            "terminal_loss": 0.85,
        }
        explicit_default = {
            "year_1_loss": 0.40, "year_2_loss": 0.65, "year_3_loss": 0.80,
            "terminal_loss": 0.85, "post_loe_sgna_fraction": 0.30,
        }
        rev_no = RevenueModel.compute(mm, loe_profile=no_fraction)
        rev_ex = RevenueModel.compute(mm, loe_profile=explicit_default)
        assert rev_no.ebit_by_year[12] == pytest.approx(rev_ex.ebit_by_year[12], rel=1e-9)


# ---------------------------------------------------------------------------
# TestLOEModalities
# ---------------------------------------------------------------------------

class TestLOEModalities:
    def test_small_molecule_erodes_faster_than_biologic(self):
        mm = _canonical_market()
        rev_sm = RevenueModel.compute(mm, loe_profile=_loe("small_molecule"))
        rev_bio = RevenueModel.compute(mm, loe_profile=_loe("biologic"))
        # In LOE year 1, biologic retains more revenue
        assert rev_bio.revenue_by_year[12] > rev_sm.revenue_by_year[12]

    def test_gene_therapy_minimal_erosion(self):
        mm = _canonical_market()
        loe_gt = _loe("gene_therapy")
        loe_sm = _loe("small_molecule")
        rev_gt = RevenueModel.compute(mm, loe_profile=loe_gt)
        rev_sm = RevenueModel.compute(mm, loe_profile=loe_sm)
        # Gene therapy retains much more revenue in all tail years
        for i in range(3):
            assert rev_gt.revenue_by_year[12 + i] > rev_sm.revenue_by_year[12 + i]

    def test_all_modalities_have_positive_tail(self):
        mm = _canonical_market()
        for modality in ("small_molecule", "biologic", "gene_therapy",
                         "cell_therapy", "adc", "rna_therapy"):
            loe = _loe(modality)
            rev = RevenueModel.compute(mm, loe_profile=loe)
            for r in rev.revenue_by_year[12:]:
                assert r >= 0, f"{modality}: negative tail revenue {r}"


# ---------------------------------------------------------------------------
# TestLOEInvariants
# ---------------------------------------------------------------------------

class TestLOEInvariants:
    def test_by_segment_geography_invariant_with_loe(self):
        """sum(by_segment_geography) == combined for all years including tail."""
        mm = _canonical_market()
        rev = RevenueModel.compute(mm, loe_profile=_loe())
        for yr_idx in range(rev.total_years):
            geo_sum = sum(
                rev.diagnostics.by_segment_geography[seg]["global"][yr_idx]
                for seg in rev.diagnostics.by_segment_geography
            )
            assert geo_sum == pytest.approx(rev.diagnostics.combined[yr_idx], rel=1e-6)

    def test_by_segment_geography_invariant_with_lot_and_loe(self):
        """Multi-LOT + LOE: segment_geography sums to combined for all years."""
        from bve.models.market_model import LineOfTherapySegment
        mm = MarketModel(
            asset_id="snap-001",
            lines_of_therapy=[
                LineOfTherapySegment(line="2L", patients_annual=8000,
                                     net_price_per_patient_usd=150000,
                                     peak_penetration=0.20, years_to_peak=5),
                LineOfTherapySegment(line="3L", patients_annual=4000,
                                     net_price_per_patient_usd=150000,
                                     peak_penetration=0.35, years_to_peak=3,
                                     launch_delay_years=1.0),
            ],
        )
        rev = RevenueModel.compute(mm, loe_profile=_loe())
        assert rev.loe_tail_years == 5  # Sprint 9.10: extended to 5 tail years
        for yr_idx in range(rev.total_years):
            geo_sum = sum(
                rev.diagnostics.by_segment_geography[seg]["global"][yr_idx]
                for seg in rev.diagnostics.by_segment_geography
            )
            assert geo_sum == pytest.approx(rev.diagnostics.combined[yr_idx], rel=1e-6)

    def test_combined_length_with_loe(self):
        mm = _canonical_market()
        rev = RevenueModel.compute(mm, loe_profile=_loe())
        assert len(rev.diagnostics.combined) == rev.total_years


# ---------------------------------------------------------------------------
# TestLOEImpactOnRNPV
# ---------------------------------------------------------------------------

class TestLOEImpactOnRNPV:
    def test_rnpv_with_loe_exceeds_rnpv_without(self):
        with_loe = _run_with_loe()
        without_loe = _run_without_loe()
        assert with_loe.rnpv_millions > without_loe.rnpv_millions

    def test_rnpv_locked_snapshot_small_molecule(self):
        """Locked regression: small_molecule LOE tail with post-LOE SG&A collapse.
        Sprint 9: baseline updated to include 21% effective tax rate (UFCF fix)."""
        result = _run_with_loe("small_molecule")
        assert result.rnpv_millions == pytest.approx(83.13, abs=0.5)  # Sprint 9.10: +2.12 from 5-yr LOE

    def test_rnpv_without_loe_matches_pre_step3_snapshot(self):
        """No-LOE path baseline.
        Sprint 9: updated to include 21% effective tax rate (was 118.72 pre-Sprint-9)."""
        result = _run_without_loe()
        assert result.rnpv_millions == pytest.approx(65.13, abs=0.5)

    def test_higher_erosion_lower_rnpv(self):
        """biologic LOE > small_molecule LOE → biologic has higher rNPV with LOE."""
        result_sm = _run_with_loe("small_molecule")
        result_bio = _run_with_loe("biologic")
        assert result_bio.rnpv_millions > result_sm.rnpv_millions

    def test_compute_rnpv_wrapper_unchanged(self):
        """compute_rnpv() (MC/scenario path) returns no-LOE value.
        Sprint 9: updated to 65.13 after UFCF/tax fix (was 118.72 pre-Sprint-9)."""
        asset = _canonical_asset()
        result = compute_rnpv(asset, _canonical_trials(), _canonical_market())
        assert result.rnpv_millions == pytest.approx(65.13, abs=0.5)


# ---------------------------------------------------------------------------
# TestValuationEngineAppliesLOE
# ---------------------------------------------------------------------------

class TestValuationEngineAppliesLOE:
    def _engine(self, modality: str = "small_molecule") -> ValuationEngine:
        asset = _canonical_asset(modality)
        company = Company(
            id="CO", name="Co", ticker="CO", cash_millions=100.0,
            shares_outstanding_millions=100.0, asset_ids=["snap-001"],
        )
        return ValuationEngine(
            asset=asset, company=company,
            trials=_canonical_trials(), market_model=_canonical_market(),
            mc_params=MonteCarloParams(n_simulations=200, random_seed=0),
        )

    def test_engine_applies_loe_automatically(self):
        output = self._engine("small_molecule").run()
        # Sprint 9.10: 83.13 after LOE 3→5 extension (was 81.01 pre-9.10)
        assert output.rnpv.rnpv_millions == pytest.approx(83.13, abs=0.5)

    def test_revenue_stream_has_loe_tail(self):
        output = self._engine().run()
        assert output.rnpv.revenue_stream.loe_tail_years == 5  # Sprint 9.10: 5 tail years
        assert output.rnpv.revenue_stream.total_years == 17

    def test_biologic_asset_gets_different_loe(self):
        out_sm = self._engine("small_molecule").run()
        out_bio = self._engine("biologic").run()
        # Biologic erodes more slowly → higher rNPV
        assert out_bio.rnpv.rnpv_millions > out_sm.rnpv.rnpv_millions
