"""
Sprint 9 Phase 2 acceptance tests — Tasks 9.5–9.10.

Each test class maps to one task:

  TestSCurveWarning         (9.5) — linear uptake UserWarning
  TestComplianceRateLoader  (9.6) — per-modality compliance rates + engine advisory
  TestSGnAAutoSelection     (9.7) — SG&A profile auto-selection in ValuationEngine
  TestAcceleratedApproval   (9.8) — AA NDA/BLA 18% base-rate discount
  TestPostApprovalRD        (9.9) — post-approval R&D cost in CostStream
  TestLOEFiveYear           (9.10) — 5-year LOE tail + backward compat with 3-key profiles
"""
from __future__ import annotations

import warnings

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.entities.asset import (
    ApprovalPathwayType,
    Asset,
    DevelopmentStage,
    Modality,
    TherapeuticArea,
)
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.cost_model import CostModel
from bve.models.market_model import MarketModel
from bve.models.pos_model import POSAdjusters, compute_pos
from bve.models.probability_model import ProbabilityModel
from bve.models.revenue_model import RevenueModel
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ASSET_ID = "sp9p2-001"


def _basic_asset(
    modality: Modality = Modality.SMALL_MOLECULE,
    ta: TherapeuticArea = TherapeuticArea.ONCOLOGY,
    approval_pathway: ApprovalPathwayType = ApprovalPathwayType.STANDARD,
    post_approval_rd_millions: float = 0.0,
) -> Asset:
    return Asset(
        id=_ASSET_ID,
        name="Test Asset",
        indication="test",
        therapeutic_area=ta,
        stage=DevelopmentStage.PHASE_2,
        modality=modality,
        discount_rate=0.10,
        approval_pathway=approval_pathway,
        post_approval_rd_millions=post_approval_rd_millions,
    )


def _basic_trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id=_ASSET_ID,
            phase=TrialPhase.PHASE_2,
            success_probability=0.40,
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
            success_probability=0.83,
            duration_years=1.5,
            cost_millions=20.0,
        ),
    ]


def _patient_market_model(
    compliance_rate: float = 0.80,
    use_s_curve: bool = True,
) -> MarketModel:
    return MarketModel(
        asset_id=_ASSET_ID,
        addressable_patients_annual=50_000,
        net_price_per_patient_usd=80_000.0,
        peak_penetration=0.25,
        years_to_peak=5,
        patent_life_years=12,
        compliance_rate=compliance_rate,
        use_s_curve=use_s_curve,
    )


def _company() -> Company:
    return Company(
        id="co-01",
        name="Test Co",
        cash_millions=200.0,
        shares_outstanding_millions=100.0,
    )


# ---------------------------------------------------------------------------
# Task 9.5 — S-curve warning
# ---------------------------------------------------------------------------

class TestSCurveWarning:
    """Linear uptake (use_s_curve=False) should emit a UserWarning."""

    def test_linear_uptake_patient_based_emits_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            MarketModel(
                asset_id=_ASSET_ID,
                addressable_patients_annual=50_000,
                net_price_per_patient_usd=80_000.0,
                peak_penetration=0.25,
                years_to_peak=5,
                patent_life_years=12,
                use_s_curve=False,
            )
        user_warns = [x for x in w if issubclass(x.category, UserWarning)]
        assert any("linear uptake" in str(x.message).lower() or "s-curve" in str(x.message).lower() for x in user_warns), \
            "Expected UserWarning about linear uptake / S-curve"

    def test_s_curve_enabled_no_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            MarketModel(
                asset_id=_ASSET_ID,
                addressable_patients_annual=50_000,
                net_price_per_patient_usd=80_000.0,
                peak_penetration=0.25,
                years_to_peak=5,
                patent_life_years=12,
                use_s_curve=True,
            )
        scurve_warns = [
            x for x in w
            if issubclass(x.category, UserWarning) and (
                "linear uptake" in str(x.message).lower()
                or "s-curve" in str(x.message).lower()
            )
        ]
        assert len(scurve_warns) == 0, "S-curve enabled should not emit uptake warning"

    def test_lines_of_therapy_no_uptake_warning(self):
        """LoT market models skip the S-curve check (validator returns early for LoT)."""
        from bve.models.market_model import LineOfTherapySegment
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mm = MarketModel(
                asset_id=_ASSET_ID,
                lines_of_therapy=[
                    LineOfTherapySegment(
                        line="1L",
                        patients_annual=10_000,
                        net_price_per_patient_usd=100_000.0,
                        peak_penetration=0.30,
                        years_to_peak=4,
                    )
                ],
                patent_life_years=12,
                use_s_curve=False,
            )
        # LoT model has lines_of_therapy populated — validator returns early
        assert mm.lines_of_therapy is not None and len(mm.lines_of_therapy) > 0
        scurve_warns = [
            x for x in w
            if issubclass(x.category, UserWarning) and (
                "linear uptake" in str(x.message).lower()
                or "s-curve" in str(x.message).lower()
            )
        ]
        # Validator returns early when lines_of_therapy is set; no uptake warning
        assert len(scurve_warns) == 0

    def test_tam_based_linear_emits_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            MarketModel(
                asset_id=_ASSET_ID,
                total_addressable_market_millions=2_000.0,
                peak_penetration=0.15,
                years_to_peak=5,
                patent_life_years=10,
                use_s_curve=False,
            )
        user_warns = [x for x in w if issubclass(x.category, UserWarning)]
        assert any("linear uptake" in str(x.message).lower() or "s-curve" in str(x.message).lower() for x in user_warns)


# ---------------------------------------------------------------------------
# Task 9.6 — Compliance rate loader + engine advisory
# ---------------------------------------------------------------------------

class TestComplianceRateLoader:
    """AssumptionsLoader.compliance_rate() returns correct values per modality."""

    def setup_method(self):
        self.loader = AssumptionsLoader.get()

    def test_gene_therapy_compliance_is_one(self):
        assert self.loader.compliance_rate("gene_therapy") == 1.0

    def test_cell_therapy_compliance_is_one(self):
        assert self.loader.compliance_rate("cell_therapy") == 1.0

    def test_small_molecule_compliance(self):
        assert self.loader.compliance_rate("small_molecule") == 0.78

    def test_biologic_iv_compliance(self):
        assert self.loader.compliance_rate("biologic_iv") == 0.95

    def test_biologic_sc_compliance(self):
        assert self.loader.compliance_rate("biologic_sc") == 0.83

    def test_adc_compliance(self):
        assert self.loader.compliance_rate("adc") == 0.95

    def test_rna_therapy_compliance(self):
        assert self.loader.compliance_rate("rna_therapy") == 0.85

    def test_unknown_modality_returns_other(self):
        """Unknown modality falls back to 'other' (0.80) without raising."""
        rate = self.loader.compliance_rate("exotic_modality")
        assert rate == 0.80

    def test_biologic_alias_maps_to_biologic_iv(self):
        """'biologic' (without suffix) maps to biologic_iv compliance."""
        assert self.loader.compliance_rate("biologic") == 0.95


class TestComplianceEngineAdvisory:
    """Engine warns when gene/cell therapy asset has compliance_rate < 1.0."""

    def _gene_therapy_engine(self, compliance_rate: float) -> ValuationEngine:
        asset = Asset(
            id="gt-advisory",
            name="Gene Therapy",
            indication="SCD",
            therapeutic_area=TherapeuticArea.RARE_DISEASE,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.GENE_THERAPY,
            discount_rate=0.12,
        )
        mm = MarketModel(
            asset_id="gt-advisory",
            addressable_patients_annual=5_000,
            net_price_per_patient_usd=500_000.0,
            peak_penetration=0.30,
            years_to_peak=5,
            patent_life_years=10,
            compliance_rate=compliance_rate,
            use_s_curve=True,
        )
        trials = [
            ClinicalTrial(asset_id="gt-advisory", phase=TrialPhase.PHASE_3, success_probability=0.55, duration_years=3.0, cost_millions=200.0),
            ClinicalTrial(asset_id="gt-advisory", phase=TrialPhase.NDA_BLA, success_probability=0.83, duration_years=1.5, cost_millions=30.0),
        ]
        return ValuationEngine(asset=asset, trials=trials, market_model=mm, company=_company())

    def test_gene_therapy_with_low_compliance_warns(self):
        """compliance_rate < 1.0 for a gene therapy should trigger advisory warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            engine = self._gene_therapy_engine(compliance_rate=0.85)
            engine._check_compliance_rate()
        compliance_warns = [
            x for x in w
            if issubclass(x.category, UserWarning) and "compliance_rate" in str(x.message)
        ]
        assert len(compliance_warns) >= 1

    def test_gene_therapy_with_full_compliance_no_warn(self):
        """compliance_rate=1.0 for gene therapy should not trigger advisory."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            engine = self._gene_therapy_engine(compliance_rate=1.0)
            engine._check_compliance_rate()
        compliance_warns = [
            x for x in w
            if issubclass(x.category, UserWarning) and "compliance_rate" in str(x.message)
        ]
        assert len(compliance_warns) == 0


# ---------------------------------------------------------------------------
# Task 9.7 — SG&A profile auto-selection
# ---------------------------------------------------------------------------

class TestSGnAAutoSelection:
    """ValuationEngine._resolve_market_model_with_sgna() picks correct profile."""

    def _engine(
        self,
        modality: Modality = Modality.SMALL_MOLECULE,
        ta: TherapeuticArea = TherapeuticArea.ONCOLOGY,
        sgna_rate_launch: float = 0.40,
        sgna_rate_mature: float = 0.20,
    ) -> ValuationEngine:
        asset = Asset(
            id="sgna-test",
            name="SG&A Test",
            indication="test",
            therapeutic_area=ta,
            stage=DevelopmentStage.PHASE_3,
            modality=modality,
            discount_rate=0.12,
        )
        mm = MarketModel(
            asset_id="sgna-test",
            addressable_patients_annual=20_000,
            net_price_per_patient_usd=100_000.0,
            peak_penetration=0.20,
            years_to_peak=5,
            patent_life_years=12,
            sgna_rate_launch=sgna_rate_launch,
            sgna_rate_mature=sgna_rate_mature,
            use_s_curve=True,
        )
        trials = [
            ClinicalTrial(asset_id="sgna-test", phase=TrialPhase.PHASE_3, success_probability=0.55, duration_years=3.0, cost_millions=200.0),
            ClinicalTrial(asset_id="sgna-test", phase=TrialPhase.NDA_BLA, success_probability=0.83, duration_years=1.5, cost_millions=30.0),
        ]
        return ValuationEngine(asset=asset, trials=trials, market_model=mm, company=_company())

    def test_gene_therapy_gets_gene_cell_profile(self):
        engine = self._engine(modality=Modality.GENE_THERAPY, ta=TherapeuticArea.RARE_DISEASE)
        mm = engine._resolve_market_model_with_sgna()
        assert mm.sgna_rate_launch == pytest.approx(0.55)
        assert mm.sgna_rate_mature == pytest.approx(0.28)
        assert mm.sgna_ramp_years == 7

    def test_cell_therapy_gets_gene_cell_profile(self):
        engine = self._engine(modality=Modality.CELL_THERAPY, ta=TherapeuticArea.ONCOLOGY)
        mm = engine._resolve_market_model_with_sgna()
        assert mm.sgna_rate_launch == pytest.approx(0.55)
        assert mm.sgna_rate_mature == pytest.approx(0.28)
        assert mm.sgna_ramp_years == 7

    def test_rare_disease_small_molecule_gets_rare_disease_profile(self):
        engine = self._engine(modality=Modality.SMALL_MOLECULE, ta=TherapeuticArea.RARE_DISEASE)
        mm = engine._resolve_market_model_with_sgna()
        assert mm.sgna_rate_launch == pytest.approx(0.45)
        assert mm.sgna_rate_mature == pytest.approx(0.22)
        assert mm.sgna_ramp_years == 4

    def test_oncology_small_molecule_uses_default(self):
        """Standard oncology asset keeps the default SG&A profile (no auto-select)."""
        from bve.config.constants import SGNA_RATE_LAUNCH, SGNA_RATE_MATURE
        engine = self._engine(modality=Modality.SMALL_MOLECULE, ta=TherapeuticArea.ONCOLOGY)
        mm = engine._resolve_market_model_with_sgna()
        # Should be unchanged (default profile = specialty_pharma = same as hardcoded defaults)
        assert mm.sgna_rate_launch == pytest.approx(SGNA_RATE_LAUNCH)
        assert mm.sgna_rate_mature == pytest.approx(SGNA_RATE_MATURE)

    def test_explicit_sgna_override_not_auto_selected(self):
        """When user sets explicit (non-default) SG&A, engine must not override it."""
        engine = self._engine(
            modality=Modality.GENE_THERAPY,
            ta=TherapeuticArea.RARE_DISEASE,
            sgna_rate_launch=0.30,   # intentionally different from gene_cell_therapy profile
            sgna_rate_mature=0.15,
        )
        mm = engine._resolve_market_model_with_sgna()
        # User override should be preserved — NOT replaced by auto-selection
        assert mm.sgna_rate_launch == pytest.approx(0.30)
        assert mm.sgna_rate_mature == pytest.approx(0.15)

    def test_auto_selection_emits_warning(self):
        """Auto-selection emits a UserWarning so the analyst knows."""
        engine = self._engine(modality=Modality.GENE_THERAPY, ta=TherapeuticArea.RARE_DISEASE)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            engine._resolve_market_model_with_sgna()
        profile_warns = [
            x for x in w
            if issubclass(x.category, UserWarning) and "gene_cell_therapy" in str(x.message)
        ]
        assert len(profile_warns) >= 1


# ---------------------------------------------------------------------------
# Task 9.8 — Accelerated Approval NDA discount
# ---------------------------------------------------------------------------

class TestAcceleratedApproval:
    """Accelerated pathway applies ~18% base-rate discount at NDA/BLA phase only."""

    # Oncology NDA base rate = 0.83; discounted = 0.83 × (1 - 0.18) = 0.6806
    _ONCOLOGY_NDA_STANDARD = 0.83
    _ONCOLOGY_NDA_ACCELERATED = 0.6806

    def test_standard_pathway_nda_unchanged(self):
        pos = compute_pos(TrialPhase.NDA_BLA, TherapeuticArea.ONCOLOGY)
        assert pos == pytest.approx(self._ONCOLOGY_NDA_STANDARD)

    def test_accelerated_pathway_nda_discounted(self):
        pos = compute_pos(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY,
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        assert pos == pytest.approx(self._ONCOLOGY_NDA_ACCELERATED, abs=1e-3)

    def test_priority_review_pathway_no_discount(self):
        """Priority review is a process designation; POS should equal standard."""
        pos = compute_pos(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY,
            approval_pathway=ApprovalPathwayType.PRIORITY_REVIEW,
        )
        assert pos == pytest.approx(self._ONCOLOGY_NDA_STANDARD)

    def test_accelerated_discount_only_at_nda_bla(self):
        """Discount must NOT affect Phase 2 or Phase 3 POS, only NDA/BLA."""
        pos_p2_std = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY)
        pos_p2_aa = compute_pos(
            TrialPhase.PHASE_2,
            TherapeuticArea.ONCOLOGY,
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        assert pos_p2_std == pos_p2_aa

        pos_p3_std = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY)
        pos_p3_aa = compute_pos(
            TrialPhase.PHASE_3,
            TherapeuticArea.ONCOLOGY,
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        assert pos_p3_std == pos_p3_aa

    def test_accelerated_discount_magnitude(self):
        """Discount factor = 1 - 0.18 = 0.82 exactly."""
        pos_std = compute_pos(TrialPhase.NDA_BLA, TherapeuticArea.ONCOLOGY)
        pos_aa = compute_pos(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY,
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        ratio = pos_aa / pos_std
        assert ratio == pytest.approx(0.82, abs=1e-3)

    def test_adjusters_still_applied_with_accelerated_pathway(self):
        """Log-odds adjusters are applied on top of the discounted base rate."""
        adj = POSAdjusters(has_breakthrough_designation=True)
        pos_plain = compute_pos(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY,
            adjusters=adj,
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        pos_no_adj = compute_pos(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY,
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        # BTD adds a small positive log-odds; BTD POS should be slightly higher
        assert pos_plain > pos_no_adj

    def test_asset_approval_pathway_field_default_standard(self):
        asset = _basic_asset()
        assert asset.approval_pathway == ApprovalPathwayType.STANDARD

    def test_asset_approval_pathway_field_accelerated(self):
        asset = _basic_asset(approval_pathway=ApprovalPathwayType.ACCELERATED)
        assert asset.approval_pathway == ApprovalPathwayType.ACCELERATED


# ---------------------------------------------------------------------------
# Task 9.9 — Post-approval R&D cost in CostStream
# ---------------------------------------------------------------------------

class TestPostApprovalRD:
    """post_approval_rd_millions is probability-weighted PV discounted at years_to_approval."""

    def _prob_result(self):
        asset = _basic_asset()
        return ProbabilityModel.compute(asset, _basic_trials())

    def test_default_zero_no_cost(self):
        prob = self._prob_result()
        cost = CostModel.compute(prob, 0.10)
        assert cost.post_approval_rd_pv_millions == 0.0

    def test_explicit_zero_no_cost(self):
        prob = self._prob_result()
        cost = CostModel.compute(prob, 0.10, post_approval_rd_millions=0.0)
        assert cost.post_approval_rd_pv_millions == 0.0

    def test_nonzero_adds_pv_to_total(self):
        prob = self._prob_result()
        cost_base = CostModel.compute(prob, 0.10)
        cost_rd = CostModel.compute(prob, 0.10, post_approval_rd_millions=50.0)
        assert cost_rd.post_approval_rd_pv_millions > 0.0
        assert cost_rd.total_pv_weighted_millions > cost_base.total_pv_weighted_millions

    def test_post_rd_pv_approximate_value(self):
        """50M post-approval R&D, 10% discount, 7.5yr approval, ~18.3% cum prob → ~4.47M PV."""
        prob = self._prob_result()
        # years_to_approval from trials: 2.5+3.5+1.5=7.5; cum_prob ≈ 0.1826
        cost = CostModel.compute(prob, 0.10, post_approval_rd_millions=50.0)
        assert cost.post_approval_rd_pv_millions == pytest.approx(4.47, abs=0.10)

    def test_total_equals_sum_of_components(self):
        """total is approximately sum of trial_rd + milestone_costs + upfront + post_approval_rd."""
        prob = self._prob_result()
        cost = CostModel.compute(prob, 0.10, post_approval_rd_millions=50.0)
        component_sum = (
            cost.trial_rd_pv_millions
            + cost.milestone_costs_pv_millions
            + cost.upfront_cost_millions
            + cost.post_approval_rd_pv_millions
        )
        assert cost.total_pv_weighted_millions == pytest.approx(component_sum, abs=0.02)

    def test_asset_field_default_zero(self):
        asset = _basic_asset()
        assert asset.post_approval_rd_millions == 0.0

    def test_asset_field_ge_zero_constraint(self):
        with pytest.raises(Exception):
            _basic_asset(post_approval_rd_millions=-10.0)

    def test_engine_passes_post_rd_to_cost_model(self):
        """ValuationEngine.run() passes post_approval_rd_millions through to CostModel."""
        asset = _basic_asset(
            modality=Modality.SMALL_MOLECULE,
            post_approval_rd_millions=100.0,
        )
        engine = ValuationEngine(
            asset=asset,
            trials=_basic_trials(),
            market_model=_patient_market_model(),
            company=_company(),
        )
        result = engine.run()
        # CostStream is accessible via result.rnpv.cost_stream
        assert result.rnpv.cost_stream.post_approval_rd_pv_millions > 0.0


# ---------------------------------------------------------------------------
# Task 9.10 — LOE 5-year tail extension
# ---------------------------------------------------------------------------

class TestLOEFiveYear:
    """RevenueModel supports up to 5 LOE tail years; old 3-key profiles remain valid."""

    def _market_model(self) -> MarketModel:
        return MarketModel(
            asset_id=_ASSET_ID,
            addressable_patients_annual=10_000,
            net_price_per_patient_usd=50_000.0,
            peak_penetration=0.20,
            years_to_peak=5,
            patent_life_years=10,
            use_s_curve=True,
        )

    def _full_5yr_profile(self) -> dict:
        return {
            "year_1_loss": 0.40,
            "year_2_loss": 0.60,
            "year_3_loss": 0.75,
            "year_4_loss": 0.85,
            "year_5_loss": 0.92,
            "terminal_loss": 0.95,
        }

    def _old_3yr_profile(self) -> dict:
        return {
            "year_1_loss": 0.40,
            "year_2_loss": 0.60,
            "year_3_loss": 0.80,
            "terminal_loss": 0.90,
        }

    def test_five_year_profile_produces_five_tail_years(self):
        mm = self._market_model()
        stream = RevenueModel.compute(mm, loe_profile=self._full_5yr_profile())
        assert stream.loe_tail_years == 5

    def test_five_year_profile_total_years(self):
        mm = self._market_model()
        stream = RevenueModel.compute(mm, loe_profile=self._full_5yr_profile())
        # patent_life=10 + 5 tail = 15
        assert stream.total_years == 15

    def test_three_year_profile_backward_compat(self):
        """Old 3-key profiles must still produce exactly 3 tail years."""
        mm = self._market_model()
        stream = RevenueModel.compute(mm, loe_profile=self._old_3yr_profile())
        assert stream.loe_tail_years == 3

    def test_three_year_profile_total_years(self):
        """patent_life=10 + 3 tail = 13 total years."""
        mm = self._market_model()
        stream = RevenueModel.compute(mm, loe_profile=self._old_3yr_profile())
        assert stream.total_years == 13

    def test_no_loe_profile_no_tail(self):
        mm = self._market_model()
        stream = RevenueModel.compute(mm)
        assert stream.loe_tail_years == 0
        assert stream.total_years == 10

    def test_five_year_profile_revenue_length(self):
        """revenue_by_year dict should have patent_life + 5 entries."""
        mm = self._market_model()
        stream = RevenueModel.compute(mm, loe_profile=self._full_5yr_profile())
        assert len(stream.revenue_by_year) == 15

    def test_five_year_tail_revenue_declines(self):
        """Each LOE year should have lower revenue than the previous."""
        mm = self._market_model()
        stream = RevenueModel.compute(mm, loe_profile=self._full_5yr_profile())
        # revenue_by_year is a list ordered by year; tail is the last 5 entries
        revs = stream.revenue_by_year
        tail = revs[-5:]
        for i in range(len(tail) - 1):
            assert tail[i] >= tail[i + 1], \
                f"LOE year {i+1} revenue should be >= year {i+2}"

    def test_five_year_profile_adds_more_value_than_three_year(self):
        """5-year tail should produce higher total revenue than 3-year tail."""
        mm = self._market_model()
        stream_3yr = RevenueModel.compute(mm, loe_profile=self._old_3yr_profile())
        stream_5yr = RevenueModel.compute(mm, loe_profile=self._full_5yr_profile())
        rev_3 = sum(stream_3yr.revenue_by_year)
        rev_5 = sum(stream_5yr.revenue_by_year)
        assert rev_5 > rev_3, "5-year LOE tail should yield more total revenue than 3-year"

    def test_real_yaml_small_molecule_profile_has_five_keys(self):
        """The live industry_assumptions.yaml small_molecule profile now has year_4/5."""
        loader = AssumptionsLoader.get()
        profile = loader.loe_erosion_profile("small_molecule")
        assert "year_4_loss" in profile
        assert "year_5_loss" in profile

    def test_real_yaml_biologic_profile_has_five_keys(self):
        loader = AssumptionsLoader.get()
        profile = loader.loe_erosion_profile("biologic")
        assert "year_4_loss" in profile
        assert "year_5_loss" in profile
