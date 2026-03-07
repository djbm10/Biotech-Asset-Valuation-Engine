"""
Step 4 tests: DrugAssetProgram container.

Covers:
  - CommercialPlan three-state semantics (unset / suppressed / loaded)
  - CommercialPlan source consistency invariant (loe_profile set but loe_source='unset' rejected)
  - DrugAssetProgram construction (direct, build())
  - DrugAssetProgram is frozen (mutations raise TypeError)
  - Asset-ID consistency invariant
  - active_trials filter
  - ValuationEngine.from_program() produces same rNPV as direct construction
  - LOE flow: suppressed → no tail; loaded → tail; unset → AssumptionsLoader fallback
"""
from __future__ import annotations

import pytest

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.drug_asset_program import CommercialPlan, DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Shared fixtures  (same numeric values as test_step2 / test_step3 snapshots)
# ---------------------------------------------------------------------------

_ASSET_ID = "DAP001"


def _asset(modality: Modality = Modality.SMALL_MOLECULE) -> Asset:
    return Asset(
        id=_ASSET_ID,
        name="DAP Test Asset",
        indication="test indication",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=modality,
        discount_rate=0.10,
    )


def _trials(asset_id: str = _ASSET_ID) -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id=asset_id,
            phase=TrialPhase.PHASE_2,
            success_probability=0.37,
            duration_years=2.5,
            cost_millions=80.0,
        ),
        ClinicalTrial(
            asset_id=asset_id,
            phase=TrialPhase.PHASE_3,
            success_probability=0.55,
            duration_years=3.5,
            cost_millions=250.0,
        ),
        ClinicalTrial(
            asset_id=asset_id,
            phase=TrialPhase.NDA_BLA,
            success_probability=0.87,
            duration_years=1.5,
            cost_millions=35.0,
        ),
    ]


def _market(asset_id: str = _ASSET_ID) -> MarketModel:
    return MarketModel(
        asset_id=asset_id,
        total_addressable_market_millions=8000.0,
        peak_penetration=0.12,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.20,
    )


def _company() -> Company:
    return Company(
        id="CO_DAP",
        name="DAP Co",
        ticker="DAP",
        cash_millions=100.0,
        shares_outstanding_millions=50.0,
        asset_ids=[_ASSET_ID],
    )


# ---------------------------------------------------------------------------
# TestCommercialPlanStates — three distinct states
# ---------------------------------------------------------------------------

class TestCommercialPlanStates:
    """
    The three states must be behaviourally and semantically distinct.
    "unset" ≠ "suppressed" even though both have loe_profile=None.
    """

    def test_bare_constructor_is_unset(self):
        plan = CommercialPlan()
        assert plan.is_unset
        assert not plan.is_suppressed
        assert not plan.is_loaded
        assert plan.loe_source == "unset"
        assert plan.loe_profile is None

    def test_no_loe_is_suppressed_not_unset(self):
        plan = CommercialPlan.no_loe()
        assert plan.is_suppressed
        assert not plan.is_unset
        assert not plan.is_loaded
        assert plan.loe_source == "suppressed"
        assert plan.loe_profile is None

    def test_from_modality_is_loaded(self):
        plan = CommercialPlan.from_modality("small_molecule")
        assert plan.is_loaded
        assert not plan.is_unset
        assert not plan.is_suppressed
        assert plan.loe_source == "modality:small_molecule"
        assert plan.loe_profile is not None

    def test_unset_and_suppressed_are_different_states(self):
        unset = CommercialPlan()
        suppressed = CommercialPlan.no_loe()
        # Both have loe_profile=None but different source
        assert unset.loe_profile is None
        assert suppressed.loe_profile is None
        assert unset.loe_source != suppressed.loe_source

    def test_setting_profile_with_unset_source_raises(self):
        """loe_profile set but loe_source='unset' is inconsistent — engine would ignore the profile."""
        with pytest.raises(ValueError, match="loe_source='unset'"):
            CommercialPlan(loe_profile={"year_1_loss": 0.4}, loe_source="unset")

    def test_setting_profile_with_custom_source_is_allowed(self):
        plan = CommercialPlan(
            loe_profile={"year_1_loss": 0.4, "year_2_loss": 0.65,
                         "year_3_loss": 0.80, "terminal_loss": 0.85},
            loe_source="custom",
        )
        assert plan.is_loaded
        assert plan.loe_source == "custom"

    def test_from_modality_source_records_requested_modality(self):
        """loe_source records the requested modality, making any fallback visible."""
        plan = CommercialPlan.from_modality("biologic")
        assert plan.loe_source == "modality:biologic"

    def test_from_modality_small_molecule_losses_increase(self):
        plan = CommercialPlan.from_modality("small_molecule")
        p = plan.loe_profile
        assert p["year_1_loss"] < p["year_2_loss"] < p["year_3_loss"]

    def test_from_modality_gene_therapy_slower_erosion_than_small_molecule(self):
        sm = CommercialPlan.from_modality("small_molecule")
        gt = CommercialPlan.from_modality("gene_therapy")
        assert gt.loe_profile["year_1_loss"] < sm.loe_profile["year_1_loss"]

    def test_from_modality_values_are_plain_floats(self):
        plan = CommercialPlan.from_modality("biologic")
        for key in ("year_1_loss", "year_2_loss", "year_3_loss"):
            assert isinstance(plan.loe_profile[key], float)

    def test_from_modality_includes_post_loe_sgna_fraction(self):
        plan = CommercialPlan.from_modality("small_molecule")
        assert "post_loe_sgna_fraction" in plan.loe_profile

    def test_all_supported_modalities_load(self):
        for m in ("small_molecule", "biologic", "gene_therapy", "cell_therapy", "adc", "rna_therapy"):
            plan = CommercialPlan.from_modality(m)
            assert plan.is_loaded


# ---------------------------------------------------------------------------
# TestDrugAssetProgramConstruction
# ---------------------------------------------------------------------------

class TestDrugAssetProgramConstruction:
    def test_fields_accessible(self):
        program = DrugAssetProgram(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
        )
        assert program.asset.id == _ASSET_ID
        assert len(program.trials) == 3
        assert program.market_model.asset_id == _ASSET_ID

    def test_defaults_empty_dicts_and_unset_plan(self):
        program = DrugAssetProgram(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
        )
        assert program.pos_adjusters == {}
        assert program.design_features == {}
        assert program.commercial_plan.is_unset

    def test_frozen_rejects_field_mutation(self):
        program = DrugAssetProgram(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
        )
        with pytest.raises(Exception):  # Pydantic v2 raises ValidationError for frozen fields
            program.asset = _asset()  # type: ignore[misc]

    def test_frozen_rejects_plan_mutation(self):
        program = DrugAssetProgram(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
        )
        with pytest.raises(Exception):  # Pydantic v2 raises ValidationError for frozen fields
            program.commercial_plan = CommercialPlan.no_loe()  # type: ignore[misc]

    def test_model_copy_creates_new_instance(self):
        """Frozen models can still be derived via model_copy(update=...)."""
        program = DrugAssetProgram(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
        )
        plan2 = CommercialPlan.no_loe()
        derived = program.model_copy(update={"commercial_plan": plan2})
        assert derived.commercial_plan.is_suppressed
        assert program.commercial_plan.is_unset  # original unchanged

    def test_asset_id_mismatch_raises(self):
        wrong_market = _market(asset_id="WRONG_ID")
        with pytest.raises(ValueError, match="asset_id"):
            DrugAssetProgram(
                asset=_asset(),
                trials=_trials(),
                market_model=wrong_market,
            )

    def test_active_trials_filters_to_asset(self):
        other_trial = ClinicalTrial(
            asset_id="OTHER_ASSET",
            phase=TrialPhase.PHASE_1,
            success_probability=0.60,
            duration_years=1.5,
            cost_millions=25.0,
        )
        program = DrugAssetProgram(
            asset=_asset(),
            trials=_trials() + [other_trial],
            market_model=_market(),
        )
        active = program.active_trials
        assert len(active) == 3
        assert all(t.asset_id == _ASSET_ID for t in active)


# ---------------------------------------------------------------------------
# TestDrugAssetProgramBuild
# ---------------------------------------------------------------------------

class TestDrugAssetProgramBuild:
    def test_build_loads_loe_by_default(self):
        program = DrugAssetProgram.build(
            asset=_asset(Modality.SMALL_MOLECULE),
            trials=_trials(),
            market_model=_market(),
        )
        assert program.commercial_plan.is_loaded
        assert program.commercial_plan.loe_source == "modality:small_molecule"

    def test_build_no_loe_sets_suppressed(self):
        program = DrugAssetProgram.build(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
            load_loe=False,
        )
        assert program.commercial_plan.is_suppressed
        assert program.commercial_plan.loe_profile is None

    def test_build_modality_biologic_loads_biologic_profile(self):
        program = DrugAssetProgram.build(
            asset=_asset(Modality.BIOLOGIC),
            trials=_trials(),
            market_model=_market(),
        )
        p = program.commercial_plan.loe_profile
        sm_plan = CommercialPlan.from_modality("small_molecule")
        assert p["year_1_loss"] < sm_plan.loe_profile["year_1_loss"]
        assert program.commercial_plan.loe_source == "modality:biologic"

    def test_build_passes_pos_adjusters(self):
        from bve.models.pos_model import POSAdjusters
        adjusters = {TrialPhase.PHASE_3: POSAdjusters()}
        program = DrugAssetProgram.build(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
            pos_adjusters=adjusters,
        )
        assert TrialPhase.PHASE_3 in program.pos_adjusters

    def test_build_passes_design_features(self):
        from bve.models.trial_design_features import TrialDesignFeatureSet
        features = {TrialPhase.PHASE_3: TrialDesignFeatureSet()}
        program = DrugAssetProgram.build(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
            design_features=features,
        )
        assert TrialPhase.PHASE_3 in program.design_features

    def test_build_result_is_frozen(self):
        program = DrugAssetProgram.build(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
        )
        with pytest.raises(Exception):  # Pydantic v2 raises ValidationError for frozen fields
            program.asset = _asset()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestValuationEngineFromProgram
# ---------------------------------------------------------------------------

class TestValuationEngineFromProgram:

    def _direct_engine(self) -> ValuationEngine:
        return ValuationEngine(
            asset=_asset(),
            company=_company(),
            trials=_trials(),
            market_model=_market(),
            mc_params=MonteCarloParams(n_simulations=100, random_seed=0),
        )

    def _program_engine(self, load_loe: bool = True) -> ValuationEngine:
        program = DrugAssetProgram.build(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
            load_loe=load_loe,
        )
        return ValuationEngine.from_program(
            program=program,
            company=_company(),
            mc_params=MonteCarloParams(n_simulations=100, random_seed=0),
        )

    def test_from_program_runs_without_error(self):
        output = self._program_engine().run()
        assert output.rnpv.rnpv_millions > 0

    def test_from_program_and_direct_produce_same_rnpv(self):
        """
        Both paths should use the small_molecule LOE profile.
        Direct engine: _commercial_plan=None → plan.is_unset → AssumptionsLoader.
        Program engine: loe_source='modality:small_molecule' → stored profile.
        Same modality → same result.
        """
        direct = self._direct_engine().run()
        via_program = self._program_engine(load_loe=True).run()
        assert direct.rnpv.rnpv_millions == pytest.approx(
            via_program.rnpv.rnpv_millions, rel=1e-6
        )

    def test_suppressed_loe_matches_no_loe_wrapper(self):
        """
        A suppressed plan applies no LOE tail.
        compute_rnpv() wrapper also applies no tail → results must match.
        """
        from bve.models.rnpv_model import compute_rnpv

        output = self._program_engine(load_loe=False).run()
        wrapper_rnpv = compute_rnpv(_asset(), _trials(), _market()).rnpv_millions
        assert output.rnpv.rnpv_millions == pytest.approx(wrapper_rnpv, abs=0.5)

    def test_loaded_loe_differs_from_suppressed(self):
        """LOE tail adds revenue → loaded rNPV must exceed suppressed rNPV."""
        loaded = self._program_engine(load_loe=True).run()
        suppressed = self._program_engine(load_loe=False).run()
        assert loaded.rnpv.rnpv_millions > suppressed.rnpv.rnpv_millions

    def test_commercial_plan_stored_on_engine(self):
        program = DrugAssetProgram.build(
            asset=_asset(), trials=_trials(), market_model=_market()
        )
        engine = ValuationEngine.from_program(program=program, company=_company())
        assert engine._commercial_plan is not None
        assert engine._commercial_plan.is_loaded

    def test_from_program_preserves_asset(self):
        program = DrugAssetProgram.build(
            asset=_asset(), trials=_trials(), market_model=_market()
        )
        engine = ValuationEngine.from_program(program=program, company=_company())
        assert engine.asset.id == _ASSET_ID

    def test_from_program_filters_trials_to_asset(self):
        other_trial = ClinicalTrial(
            asset_id="OTHER",
            phase=TrialPhase.PHASE_1,
            success_probability=0.60,
            duration_years=1.5,
            cost_millions=25.0,
        )
        program = DrugAssetProgram.build(
            asset=_asset(),
            trials=_trials() + [other_trial],
            market_model=_market(),
        )
        engine = ValuationEngine.from_program(program=program, company=_company())
        assert all(t.asset_id == _ASSET_ID for t in engine.trials)
