"""
Sprint 31A — ScenarioShock data model tests.

Covers:
- All 6 category sub-models: ClinicalShock, RegulatoryShock, CommercialShock,
  CompetitionShock, CostsFCFShock, DealEconomicsShock
- ScenarioShock composite: zero-effect defaults, categories_modified, per-phase key validation
- Canonical named shocks: SHOCK_BULL, SHOCK_BASE, SHOCK_BEAR
- Immutability (frozen models)
- Field range validators
"""
import pytest
from pydantic import ValidationError

from bve.models.scenario_shock import (
    ClinicalShock,
    CommercialShock,
    CompetitionShock,
    CostsFCFShock,
    DealEconomicsShock,
    RegulatoryShock,
    ScenarioShock,
    SHOCK_BASE,
    SHOCK_BEAR,
    SHOCK_BULL,
)


# ---------------------------------------------------------------------------
# ClinicalShock
# ---------------------------------------------------------------------------

class TestClinicalShock:
    def test_defaults_are_zero_effect(self):
        s = ClinicalShock()
        assert s.is_zero_effect

    def test_pos_mult_default_one(self):
        assert ClinicalShock().pos_mult == 1.0

    def test_pos_mult_change_breaks_zero_effect(self):
        assert not ClinicalShock(pos_mult=1.3).is_zero_effect

    def test_per_phase_pos_mult_breaks_zero_effect(self):
        assert not ClinicalShock(per_phase_pos_mult={"phase_2": 1.2}).is_zero_effect

    def test_safety_profile_override_breaks_zero_effect(self):
        assert not ClinicalShock(safety_profile_override="manageable").is_zero_effect

    def test_biomarker_override_breaks_zero_effect(self):
        assert not ClinicalShock(biomarker_selection_override="validated").is_zero_effect

    def test_breakthrough_override_breaks_zero_effect(self):
        assert not ClinicalShock(breakthrough_designation_override=True).is_zero_effect

    def test_logodds_delta_breaks_zero_effect(self):
        assert not ClinicalShock(prior_phase_data_logodds_delta=0.3).is_zero_effect

    def test_pos_mult_lower_bound(self):
        s = ClinicalShock(pos_mult=0.0)
        assert s.pos_mult == 0.0

    def test_pos_mult_upper_bound(self):
        s = ClinicalShock(pos_mult=5.0)
        assert s.pos_mult == 5.0

    def test_pos_mult_above_max_raises(self):
        with pytest.raises(ValidationError):
            ClinicalShock(pos_mult=6.0)

    def test_frozen(self):
        s = ClinicalShock()
        with pytest.raises(Exception):
            s.pos_mult = 2.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RegulatoryShock
# ---------------------------------------------------------------------------

class TestRegulatoryShock:
    def test_defaults_are_zero_effect(self):
        assert RegulatoryShock().is_zero_effect

    def test_duration_delta_breaks_zero_effect(self):
        assert not RegulatoryShock(duration_add_years=1.0).is_zero_effect

    def test_approval_pathway_override_breaks_zero_effect(self):
        assert not RegulatoryShock(approval_pathway_override="accelerated").is_zero_effect

    def test_label_breadth_mult_breaks_zero_effect(self):
        assert not RegulatoryShock(label_breadth_mult=0.7).is_zero_effect

    def test_confirmatory_cost_breaks_zero_effect(self):
        assert not RegulatoryShock(confirmatory_trial_cost_millions=50.0).is_zero_effect

    def test_crl_delay_breaks_zero_effect(self):
        assert not RegulatoryShock(crl_delay_add_years=0.5).is_zero_effect

    def test_label_breadth_default_one(self):
        assert RegulatoryShock().label_breadth_mult == 1.0

    def test_confirmatory_cost_nonnegative(self):
        with pytest.raises(ValidationError):
            RegulatoryShock(confirmatory_trial_cost_millions=-1.0)

    def test_crl_delay_nonnegative(self):
        with pytest.raises(ValidationError):
            RegulatoryShock(crl_delay_add_years=-0.5)


# ---------------------------------------------------------------------------
# CommercialShock
# ---------------------------------------------------------------------------

class TestCommercialShock:
    def test_defaults_are_zero_effect(self):
        assert CommercialShock().is_zero_effect

    def test_patients_mult_breaks_zero_effect(self):
        assert not CommercialShock(addressable_patients_mult=1.2).is_zero_effect

    def test_penetration_mult_breaks_zero_effect(self):
        assert not CommercialShock(peak_penetration_mult=0.65).is_zero_effect

    def test_net_price_mult_breaks_zero_effect(self):
        assert not CommercialShock(net_price_mult=0.90).is_zero_effect

    def test_gross_to_net_delta_breaks_zero_effect(self):
        assert not CommercialShock(gross_to_net_rate_delta=0.05).is_zero_effect

    def test_price_erosion_delta_breaks_zero_effect(self):
        assert not CommercialShock(annual_price_erosion_delta=0.03).is_zero_effect

    def test_years_to_peak_breaks_zero_effect(self):
        assert not CommercialShock(years_to_peak_add=1.0).is_zero_effect

    def test_archetype_override_breaks_zero_effect(self):
        assert not CommercialShock(launch_archetype_override="primary_care_broad").is_zero_effect

    def test_geo_delay_breaks_zero_effect(self):
        assert not CommercialShock(ex_us_launch_delay_add_years=0.5).is_zero_effect

    def test_payer_access_mult_breaks_zero_effect(self):
        assert not CommercialShock(payer_access_probability_mult=0.80).is_zero_effect

    def test_prior_auth_breaks_zero_effect(self):
        assert not CommercialShock(prior_auth_burden_delta=0.20).is_zero_effect

    def test_reimbursement_mult_breaks_zero_effect(self):
        assert not CommercialShock(reimbursement_probability_mult=0.90).is_zero_effect

    def test_payer_access_mult_capped_at_one(self):
        with pytest.raises(ValidationError):
            CommercialShock(payer_access_probability_mult=1.1)

    def test_patients_mult_nonnegative(self):
        with pytest.raises(ValidationError):
            CommercialShock(addressable_patients_mult=-0.1)


# ---------------------------------------------------------------------------
# CompetitionShock
# ---------------------------------------------------------------------------

class TestCompetitionShock:
    def test_defaults_are_zero_effect(self):
        assert CompetitionShock().is_zero_effect

    def test_approval_prob_mult_breaks_zero_effect(self):
        assert not CompetitionShock(competitor_approval_prob_mult=1.25).is_zero_effect

    def test_launch_timing_breaks_zero_effect(self):
        assert not CompetitionShock(competitor_launch_timing_add_years=1.0).is_zero_effect

    def test_market_share_mult_breaks_zero_effect(self):
        assert not CompetitionShock(competitor_market_share_mult=1.20).is_zero_effect

    def test_price_pressure_breaks_zero_effect(self):
        assert not CompetitionShock(competition_price_pressure_delta=0.03).is_zero_effect

    def test_price_pressure_range(self):
        with pytest.raises(ValidationError):
            CompetitionShock(competition_price_pressure_delta=1.5)


# ---------------------------------------------------------------------------
# CostsFCFShock
# ---------------------------------------------------------------------------

class TestCostsFCFShock:
    def test_defaults_are_zero_effect(self):
        assert CostsFCFShock().is_zero_effect

    def test_rd_cost_mult_breaks_zero_effect(self):
        assert not CostsFCFShock(rd_cost_mult=1.20).is_zero_effect

    def test_cmc_cost_mult_breaks_zero_effect(self):
        assert not CostsFCFShock(cmc_cost_mult=1.10).is_zero_effect

    def test_cost_inflation_breaks_zero_effect(self):
        assert not CostsFCFShock(cost_inflation_delta=0.02).is_zero_effect

    def test_cogs_delta_breaks_zero_effect(self):
        assert not CostsFCFShock(cogs_rate_delta=0.03).is_zero_effect

    def test_sgna_delta_breaks_zero_effect(self):
        assert not CostsFCFShock(sgna_rate_delta=0.05).is_zero_effect

    def test_maintenance_capex_breaks_zero_effect(self):
        assert not CostsFCFShock(maintenance_capex_rate_delta=0.01).is_zero_effect

    def test_working_capital_breaks_zero_effect(self):
        assert not CostsFCFShock(working_capital_rate_delta=0.02).is_zero_effect

    def test_tax_rate_delta_breaks_zero_effect(self):
        assert not CostsFCFShock(tax_rate_delta=0.03).is_zero_effect

    def test_discount_rate_delta_breaks_zero_effect(self):
        assert not CostsFCFShock(discount_rate_delta=0.02).is_zero_effect

    def test_rd_cost_mult_nonnegative(self):
        with pytest.raises(ValidationError):
            CostsFCFShock(rd_cost_mult=-0.1)

    def test_discount_rate_range(self):
        with pytest.raises(ValidationError):
            CostsFCFShock(discount_rate_delta=1.0)


# ---------------------------------------------------------------------------
# DealEconomicsShock
# ---------------------------------------------------------------------------

class TestDealEconomicsShock:
    def test_defaults_are_zero_effect(self):
        assert DealEconomicsShock().is_zero_effect

    def test_royalty_override_breaks_zero_effect(self):
        assert not DealEconomicsShock(royalty_rate_override=0.08).is_zero_effect

    def test_profit_share_override_breaks_zero_effect(self):
        assert not DealEconomicsShock(profit_share_rate_override=0.15).is_zero_effect

    def test_cdev_cost_share_override_breaks_zero_effect(self):
        assert not DealEconomicsShock(cdev_cost_share_override=0.50).is_zero_effect

    def test_milestone_payment_mult_breaks_zero_effect(self):
        assert not DealEconomicsShock(milestone_payment_mult=0.80).is_zero_effect

    def test_milestone_receipt_mult_breaks_zero_effect(self):
        assert not DealEconomicsShock(milestone_receipt_mult=1.20).is_zero_effect

    def test_royalty_override_range(self):
        with pytest.raises(ValidationError):
            DealEconomicsShock(royalty_rate_override=1.5)

    def test_milestone_mult_nonnegative(self):
        with pytest.raises(ValidationError):
            DealEconomicsShock(milestone_payment_mult=-0.1)


# ---------------------------------------------------------------------------
# ScenarioShock composite
# ---------------------------------------------------------------------------

class TestScenarioShock:
    def test_empty_shock_is_zero_effect(self):
        s = ScenarioShock()
        assert s.is_zero_effect

    def test_categories_modified_empty_for_base(self):
        assert ScenarioShock().categories_modified == []

    def test_categories_modified_clinical(self):
        s = ScenarioShock(clinical=ClinicalShock(pos_mult=1.3))
        assert s.categories_modified == ["clinical"]

    def test_categories_modified_multiple(self):
        s = ScenarioShock(
            clinical=ClinicalShock(pos_mult=1.2),
            costs_fcf=CostsFCFShock(rd_cost_mult=1.1),
        )
        mods = s.categories_modified
        assert "clinical" in mods
        assert "costs_fcf" in mods
        assert len(mods) == 2

    def test_all_six_categories_can_be_modified(self):
        s = ScenarioShock(
            clinical=ClinicalShock(pos_mult=1.1),
            regulatory=RegulatoryShock(duration_add_years=0.5),
            commercial=CommercialShock(net_price_mult=0.9),
            competition=CompetitionShock(competitor_approval_prob_mult=1.1),
            costs_fcf=CostsFCFShock(rd_cost_mult=1.1),
            deal_economics=DealEconomicsShock(royalty_rate_override=0.05),
        )
        assert len(s.categories_modified) == 6
        assert not s.is_zero_effect

    def test_label_and_description_stored(self):
        s = ScenarioShock(label="Endpoint Miss", description="Phase 3 primary endpoint missed")
        assert s.label == "Endpoint Miss"
        assert s.description == "Phase 3 primary endpoint missed"

    def test_default_label(self):
        assert ScenarioShock().label == "Custom"

    def test_frozen(self):
        s = ScenarioShock()
        with pytest.raises(Exception):
            s.label = "Modified"  # type: ignore[misc]

    def test_invalid_per_phase_key_raises(self):
        with pytest.raises(ValidationError, match="unknown phase keys"):
            ScenarioShock(clinical=ClinicalShock(per_phase_pos_mult={"phase_99": 1.2}))

    def test_valid_per_phase_keys_accepted(self):
        s = ScenarioShock(clinical=ClinicalShock(
            per_phase_pos_mult={"phase_1": 1.0, "phase_2": 1.2, "phase_3": 1.3}
        ))
        assert s.clinical.per_phase_pos_mult["phase_3"] == 1.3

    def test_nda_bla_phase_key_valid(self):
        s = ScenarioShock(clinical=ClinicalShock(per_phase_pos_mult={"nda_bla": 1.1}))
        assert "nda_bla" in s.clinical.per_phase_pos_mult


# ---------------------------------------------------------------------------
# Canonical named shocks
# ---------------------------------------------------------------------------

class TestCanonicalShocks:
    def test_base_is_zero_effect(self):
        assert SHOCK_BASE.is_zero_effect

    def test_base_label(self):
        assert SHOCK_BASE.label == "Base"

    def test_bull_is_not_zero_effect(self):
        assert not SHOCK_BULL.is_zero_effect

    def test_bear_is_not_zero_effect(self):
        assert not SHOCK_BEAR.is_zero_effect

    def test_bull_label(self):
        assert SHOCK_BULL.label == "Bull"

    def test_bear_label(self):
        assert SHOCK_BEAR.label == "Bear"

    def test_bull_pos_mult_gt_one(self):
        assert SHOCK_BULL.clinical.pos_mult > 1.0

    def test_bear_pos_mult_lt_one(self):
        assert SHOCK_BEAR.clinical.pos_mult < 1.0

    def test_bull_positive_label_breadth(self):
        assert SHOCK_BULL.regulatory.label_breadth_mult > 1.0

    def test_bear_negative_label_breadth(self):
        assert SHOCK_BEAR.regulatory.label_breadth_mult < 1.0

    def test_bull_higher_penetration_than_bear(self):
        assert SHOCK_BULL.commercial.peak_penetration_mult > SHOCK_BEAR.commercial.peak_penetration_mult

    def test_bull_lower_rd_cost_than_bear(self):
        assert SHOCK_BULL.costs_fcf.rd_cost_mult < SHOCK_BEAR.costs_fcf.rd_cost_mult

    def test_bull_lower_wacc_than_bear(self):
        assert SHOCK_BULL.costs_fcf.discount_rate_delta < SHOCK_BEAR.costs_fcf.discount_rate_delta

    def test_bull_delayed_competitors(self):
        assert SHOCK_BULL.competition.competitor_launch_timing_add_years > 0.0

    def test_bear_more_competitive_pressure(self):
        assert SHOCK_BEAR.competition.competition_price_pressure_delta > 0.0

    def test_bear_higher_payer_restrictions(self):
        assert SHOCK_BEAR.commercial.prior_auth_burden_delta > 0.0
        assert SHOCK_BEAR.commercial.payer_access_probability_mult < 1.0

    def test_canonical_shocks_are_frozen(self):
        for shock in (SHOCK_BULL, SHOCK_BASE, SHOCK_BEAR):
            with pytest.raises(Exception):
                shock.label = "Mutated"  # type: ignore[misc]

    def test_bull_categories_include_clinical_regulatory_commercial_competition_costs(self):
        mods = SHOCK_BULL.categories_modified
        assert "clinical" in mods
        assert "regulatory" in mods
        assert "commercial" in mods
        assert "competition" in mods
        assert "costs_fcf" in mods

    def test_bear_categories_include_all_core(self):
        mods = SHOCK_BEAR.categories_modified
        for cat in ("clinical", "regulatory", "commercial", "competition", "costs_fcf"):
            assert cat in mods, f"Expected '{cat}' in bear categories_modified"
