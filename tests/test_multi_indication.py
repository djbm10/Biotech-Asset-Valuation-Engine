"""Tests for MultiIndicationProgram and run_multi_indication_valuation."""
import pytest

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.drug_asset_program import DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.models.multi_indication import (
    FranchiseCostSharing,
    MultiIndicationProgram,
    SecondaryIndication,
    run_multi_indication_valuation,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def company():
    return Company(
        id="test-co",
        name="Test Co",
        ticker="TEST",
        cash_millions=200.0,
        shares_outstanding_millions=100.0,
    )


def _make_asset(asset_id: str, indication: str) -> Asset:
    return Asset(
        id=asset_id,
        name=asset_id.upper(),
        indication=indication,
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_3,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.10,
    )


def _make_market(asset_id: str, peak_sales: float = 500.0) -> MarketModel:
    return MarketModel(
        asset_id=asset_id,
        total_addressable_market_millions=peak_sales / 0.30,
        peak_penetration=0.30,
        years_to_peak=3,
        patent_life_years=10,
        net_price_per_patient_usd=None,
        addressable_patients_annual=None,
    )


def _make_trial(asset_id: str, pos: float = 0.60) -> ClinicalTrial:
    return ClinicalTrial(
        asset_id=asset_id,
        phase=TrialPhase.PHASE_3,
        success_probability=pos,
        duration_years=2.0,
        cost_millions=50.0,
    )


def _make_program(asset_id: str, indication: str, pos: float = 0.60) -> DrugAssetProgram:
    asset = _make_asset(asset_id, indication)
    market = _make_market(asset_id)
    trial = _make_trial(asset_id, pos)
    return DrugAssetProgram.build(asset=asset, trials=[trial], market_model=market, load_loe=False)


# ---------------------------------------------------------------------------
# MultiIndicationProgram construction
# ---------------------------------------------------------------------------

class TestMultiIndicationProgram:
    def test_primary_only(self):
        program = MultiIndicationProgram(primary_program=_make_program("drug-a", "Indication A"))
        assert len(program.secondary_programs) == 0

    def test_with_secondary(self):
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")
        program = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[
                SecondaryIndication(label="Ind B Phase 3", drug_asset_program=secondary)
            ],
        )
        assert len(program.secondary_programs) == 1
        assert program.secondary_programs[0].cascade_pos is True  # default

    def test_secondary_independent_pos(self):
        secondary = SecondaryIndication(
            label="Ind B",
            drug_asset_program=_make_program("drug-b", "Indication B"),
            cascade_pos=False,
        )
        assert secondary.cascade_pos is False

    def test_secondary_conditional_pos_override(self):
        secondary = SecondaryIndication(
            label="Ind B",
            drug_asset_program=_make_program("drug-b", "Indication B"),
            cascade_pos=True,
            conditional_pos_override=0.40,
        )
        assert secondary.conditional_pos_override == 0.40


# ---------------------------------------------------------------------------
# run_multi_indication_valuation
# ---------------------------------------------------------------------------

class TestRunMultiIndication:
    def test_primary_only_matches_single_engine(self, company):
        """Primary-only multi-indication result equals a single ValuationEngine."""
        from bve.valuation.valuation_engine import ValuationEngine

        primary = _make_program("drug-a", "Indication A")
        program = MultiIndicationProgram(primary_program=primary)

        result = run_multi_indication_valuation(program, company)

        single_output = ValuationEngine.from_program(primary, company).run()
        assert abs(result.total_rnpv_millions - single_output.rnpv.rnpv_millions) < 0.01

    def test_cascade_pos_reduces_secondary_rnpv(self, company):
        """cascade_pos=True multiplies secondary rNPV by primary P(approval) < 1."""
        primary = _make_program("drug-a", "Indication A", pos=0.60)
        secondary = _make_program("drug-b", "Indication B", pos=0.70)

        program_cascade = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=True
            )],
        )
        program_independent = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=False
            )],
        )

        result_cascade = run_multi_indication_valuation(program_cascade, company)
        result_independent = run_multi_indication_valuation(program_independent, company)

        # Cascade should produce lower total because secondary rNPV is multiplied by primary P < 1
        assert result_cascade.total_rnpv_millions < result_independent.total_rnpv_millions

    def test_cascade_multiplier_is_primary_pos(self, company):
        """When cascade_pos=True and no override, multiplier == primary cumulative_success_probability."""
        primary = _make_program("drug-a", "Indication A", pos=0.60)
        secondary = _make_program("drug-b", "Indication B", pos=0.70)

        program = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=True
            )],
        )
        result = run_multi_indication_valuation(program, company)

        primary_pos = result.primary.cumulative_pos
        sec = result.secondaries[0]
        assert abs(sec.cascade_multiplier - primary_pos) < 1e-6
        assert abs(sec.adjusted_rnpv_millions - sec.rnpv_millions * primary_pos) < 0.01

    def test_conditional_pos_override(self, company):
        """conditional_pos_override replaces primary_pos as the cascade multiplier."""
        primary = _make_program("drug-a", "Indication A", pos=0.60)
        secondary = _make_program("drug-b", "Indication B", pos=0.70)

        override = 0.25
        program = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary,
                cascade_pos=True, conditional_pos_override=override
            )],
        )
        result = run_multi_indication_valuation(program, company)
        sec = result.secondaries[0]
        assert abs(sec.cascade_multiplier - override) < 1e-6

    def test_total_rnpv_is_sum(self, company):
        """total_rnpv_millions equals primary.adjusted + sum(secondary.adjusted)."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        program = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=True
            )],
        )
        result = run_multi_indication_valuation(program, company)
        expected = round(
            result.primary.adjusted_rnpv_millions
            + sum(s.adjusted_rnpv_millions for s in result.secondaries),
            2,
        )
        assert abs(result.total_rnpv_millions - expected) < 0.01

    def test_independent_secondary_not_double_counted(self, company):
        """cascade_pos=False: adjusted_rnpv == raw rnpv (multiplier=1.0)."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        program = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=False
            )],
        )
        result = run_multi_indication_valuation(program, company)
        sec = result.secondaries[0]
        assert sec.cascade_multiplier == 1.0
        assert abs(sec.adjusted_rnpv_millions - sec.rnpv_millions) < 0.01

    def test_summary_string(self, company):
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")
        program = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Indication B — Phase 3", drug_asset_program=secondary
            )],
        )
        result = run_multi_indication_valuation(program, company)
        summary = result.summary()
        assert "Combined rNPV" in summary
        assert "Indication B — Phase 3" in summary


# ---------------------------------------------------------------------------
# Label Expansion Cost Sharing
# ---------------------------------------------------------------------------

class TestFranchiseCostSharing:
    def test_default_no_sharing(self):
        sharing = FranchiseCostSharing()
        assert sharing.sga_share == 0.0
        assert sharing.manufacturing_share == 0.0
        assert sharing.development_share == 0.0

    def test_sga_share_increases_rnpv(self, company):
        """SG&A sharing reduces costs → secondary rNPV is higher than without sharing."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        program_shared = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B",
                drug_asset_program=secondary,
                cascade_pos=False,
                cost_sharing=FranchiseCostSharing(sga_share=0.70),
            )],
        )
        program_base = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=False
            )],
        )
        result_shared = run_multi_indication_valuation(program_shared, company)
        result_base = run_multi_indication_valuation(program_base, company)

        sec_shared = result_shared.secondaries[0]
        sec_base = result_base.secondaries[0]
        assert sec_shared.rnpv_millions > sec_base.rnpv_millions

    def test_manufacturing_share_increases_rnpv(self, company):
        """Manufacturing cost sharing reduces COGS → higher secondary rNPV."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        program_shared = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B",
                drug_asset_program=secondary,
                cascade_pos=False,
                cost_sharing=FranchiseCostSharing(manufacturing_share=0.30),
            )],
        )
        program_base = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=False
            )],
        )
        result_shared = run_multi_indication_valuation(program_shared, company)
        result_base = run_multi_indication_valuation(program_base, company)
        assert result_shared.secondaries[0].rnpv_millions > result_base.secondaries[0].rnpv_millions

    def test_development_share_increases_rnpv(self, company):
        """Development cost sharing reduces trial costs → higher secondary rNPV."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        program_shared = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B",
                drug_asset_program=secondary,
                cascade_pos=False,
                cost_sharing=FranchiseCostSharing(development_share=0.50),
            )],
        )
        program_base = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=False
            )],
        )
        result_shared = run_multi_indication_valuation(program_shared, company)
        result_base = run_multi_indication_valuation(program_base, company)
        assert result_shared.secondaries[0].rnpv_millions > result_base.secondaries[0].rnpv_millions

    def test_cost_sharing_benefit_reported(self, company):
        """cost_sharing_benefit_millions == adjusted_rnpv - baseline_rnpv > 0 when sharing > 0."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        program = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B",
                drug_asset_program=secondary,
                cascade_pos=False,
                cost_sharing=FranchiseCostSharing(sga_share=0.70),
            )],
        )
        result = run_multi_indication_valuation(program, company)
        sec = result.secondaries[0]
        assert sec.cost_sharing_benefit_millions > 0.0

    def test_no_sharing_benefit_is_zero(self, company):
        """Without cost sharing configured, benefit is exactly 0."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        program = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=False
            )],
        )
        result = run_multi_indication_valuation(program, company)
        assert result.secondaries[0].cost_sharing_benefit_millions == 0.0

    def test_primary_rnpv_unaffected_by_secondary_sharing(self, company):
        """Cost sharing only applies to secondaries; primary rNPV is unchanged."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        program_shared = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B",
                drug_asset_program=secondary,
                cost_sharing=FranchiseCostSharing(sga_share=0.70, development_share=0.50),
            )],
        )
        program_base = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(label="Ind B", drug_asset_program=secondary)],
        )
        result_shared = run_multi_indication_valuation(program_shared, company)
        result_base = run_multi_indication_valuation(program_base, company)
        assert abs(result_shared.primary.rnpv_millions - result_base.primary.rnpv_millions) < 0.01

    def test_default_cost_sharing_applied_when_no_per_secondary_override(self, company):
        """default_cost_sharing on MultiIndicationProgram applies when secondary.cost_sharing is None."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        program_with_default = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=False
            )],
            default_cost_sharing=FranchiseCostSharing(sga_share=0.60),
        )
        program_no_sharing = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=False
            )],
        )
        result_default = run_multi_indication_valuation(program_with_default, company)
        result_none = run_multi_indication_valuation(program_no_sharing, company)
        # Default sharing should boost rNPV
        assert result_default.secondaries[0].rnpv_millions > result_none.secondaries[0].rnpv_millions

    def test_per_secondary_sharing_overrides_default(self, company):
        """Per-secondary cost_sharing takes precedence over default_cost_sharing."""
        primary = _make_program("drug-a", "Indication A")
        secondary = _make_program("drug-b", "Indication B")

        # Default = small sharing; per-secondary = large sharing → should get large sharing
        program = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B",
                drug_asset_program=secondary,
                cascade_pos=False,
                cost_sharing=FranchiseCostSharing(sga_share=0.80),
            )],
            default_cost_sharing=FranchiseCostSharing(sga_share=0.10),
        )
        program_default_only = MultiIndicationProgram(
            primary_program=primary,
            secondary_programs=[SecondaryIndication(
                label="Ind B", drug_asset_program=secondary, cascade_pos=False
            )],
            default_cost_sharing=FranchiseCostSharing(sga_share=0.10),
        )
        result = run_multi_indication_valuation(program, company)
        result_default = run_multi_indication_valuation(program_default_only, company)
        # Per-secondary 80% SGA share >> default 10% → higher rNPV
        assert result.secondaries[0].rnpv_millions > result_default.secondaries[0].rnpv_millions
