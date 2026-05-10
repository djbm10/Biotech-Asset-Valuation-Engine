"""
Tests for revenue model sanity checks (revenue_sanity.py).

Each of the 7 checks has:
  - A test that does NOT trigger the warning (clean config)
  - A test that DOES trigger the warning (problematic config)
  - Where relevant, a boundary-value test
"""
from __future__ import annotations

import pytest

from bve.models.commercial_inputs import CommercialInputs, PatientPool, PricingModel, ShareModel
from bve.models.competition_model import CompetitionModel, CompetitorLaunch
from bve.models.geography import GeographySplit, RegionalProfile
from bve.models.launch_archetype import LaunchArchetype
from bve.models.market_model import MarketModel
from bve.models.payer_access import PayerAccessModel
from bve.models.revenue_sanity import SanityWarning, check_commercial_assumptions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market(**kw) -> MarketModel:
    base = dict(
        asset_id="sanity-test",
        therapeutic_area="oncology",
        total_addressable_market_millions=1000.0,
        peak_penetration=0.10,
        patent_life_years=10,
    )
    base.update(kw)
    return MarketModel(**base)


def _codes(issues: list[SanityWarning]) -> set[str]:
    return {w.code for w in issues}


# ---------------------------------------------------------------------------
# Check 1: global_peak_exceeds_5x_us
# ---------------------------------------------------------------------------

class TestGlobalExceeds5xUS:
    def test_no_geo_no_warning(self):
        mm = _market()
        assert "global_peak_exceeds_5x_us" not in _codes(check_commercial_assumptions(mm))

    def test_normal_global_ratio_no_warning(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=2.0),
            japan=RegionalProfile(revenue_ratio=0.15, launch_delay_years=2.5),
        )
        mm = _market(geography_split=geo)
        assert "global_peak_exceeds_5x_us" not in _codes(check_commercial_assumptions(mm))

    def test_very_high_ratio_triggers_warning(self):
        # 6 ex-US regions each with revenue_ratio=1.0 → global = 7× US
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=2.0, launch_delay_years=0.0),
            japan=RegionalProfile(revenue_ratio=2.0, launch_delay_years=0.0),
            china=RegionalProfile(revenue_ratio=2.0, launch_delay_years=0.0),
        )
        mm = _market(geography_split=geo)
        issues = check_commercial_assumptions(mm)
        assert "global_peak_exceeds_5x_us" in _codes(issues)

    def test_warning_message_contains_ratio(self):
        geo = GeographySplit(
            eu5=RegionalProfile(revenue_ratio=3.0, launch_delay_years=0.0),
            japan=RegionalProfile(revenue_ratio=2.5, launch_delay_years=0.0),
        )
        mm = _market(geography_split=geo)
        issues = check_commercial_assumptions(mm)
        matching = [w for w in issues if w.code == "global_peak_exceeds_5x_us"]
        assert len(matching) == 1
        assert "×" in matching[0].message or "x" in matching[0].message.lower()


# ---------------------------------------------------------------------------
# Check 2: eu5_exceeds_us_revenue
# ---------------------------------------------------------------------------

class TestEU5ExceedsUS:
    def test_no_geo_no_warning(self):
        mm = _market()
        assert "eu5_exceeds_us_revenue" not in _codes(check_commercial_assumptions(mm))

    def test_normal_eu5_ratio_no_warning(self):
        geo = GeographySplit(eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=2.0))
        mm = _market(geography_split=geo)
        assert "eu5_exceeds_us_revenue" not in _codes(check_commercial_assumptions(mm))

    def test_eu5_ratio_exactly_one_no_warning(self):
        geo = GeographySplit(eu5=RegionalProfile(revenue_ratio=1.0, launch_delay_years=0.0))
        mm = _market(geography_split=geo)
        assert "eu5_exceeds_us_revenue" not in _codes(check_commercial_assumptions(mm))

    def test_eu5_ratio_above_one_triggers_warning(self):
        geo = GeographySplit(eu5=RegionalProfile(revenue_ratio=1.5, launch_delay_years=2.0))
        mm = _market(geography_split=geo)
        issues = check_commercial_assumptions(mm)
        assert "eu5_exceeds_us_revenue" in _codes(issues)

    def test_no_eu5_region_no_warning(self):
        geo = GeographySplit(
            japan=RegionalProfile(revenue_ratio=0.15, launch_delay_years=2.0),
        )
        mm = _market(geography_split=geo)
        assert "eu5_exceeds_us_revenue" not in _codes(check_commercial_assumptions(mm))


# ---------------------------------------------------------------------------
# Check 3: china_ratio_high
# ---------------------------------------------------------------------------

class TestChinaRatioHigh:
    def test_no_china_no_warning(self):
        geo = GeographySplit(eu5=RegionalProfile(revenue_ratio=0.35, launch_delay_years=2.0))
        mm = _market(geography_split=geo)
        assert "china_ratio_high" not in _codes(check_commercial_assumptions(mm))

    def test_normal_china_ratio_no_warning(self):
        geo = GeographySplit(
            china=RegionalProfile(revenue_ratio=0.10, launch_delay_years=3.0,
                                  reimbursement_probability=0.70, probability_of_regional_approval=0.80),
        )
        mm = _market(geography_split=geo)
        assert "china_ratio_high" not in _codes(check_commercial_assumptions(mm))

    def test_china_ratio_high_triggers_warning(self):
        geo = GeographySplit(
            china=RegionalProfile(revenue_ratio=0.60, launch_delay_years=3.0),
        )
        mm = _market(geography_split=geo)
        issues = check_commercial_assumptions(mm)
        assert "china_ratio_high" in _codes(issues)

    def test_china_effective_scalar_threshold(self):
        # revenue_ratio=0.60 × reimb=0.5 → effective=0.30 → below threshold, no warning
        geo = GeographySplit(
            china=RegionalProfile(revenue_ratio=0.60, launch_delay_years=3.0,
                                  reimbursement_probability=0.50, probability_of_regional_approval=0.80),
        )
        mm = _market(geography_split=geo)
        # 0.60 × 0.50 × 0.80 = 0.24 < 0.40 threshold
        assert "china_ratio_high" not in _codes(check_commercial_assumptions(mm))

    def test_china_warning_is_info_severity(self):
        geo = GeographySplit(
            china=RegionalProfile(revenue_ratio=0.60, launch_delay_years=3.0),
        )
        mm = _market(geography_split=geo)
        issues = [w for w in check_commercial_assumptions(mm) if w.code == "china_ratio_high"]
        assert issues[0].severity == "info"


# ---------------------------------------------------------------------------
# Check 4: payer_low_penetration_high
# ---------------------------------------------------------------------------

class TestPayerLowPenetrationHigh:
    def test_no_payer_no_warning(self):
        mm = _market(peak_penetration=0.30)
        assert "payer_low_penetration_high" not in _codes(check_commercial_assumptions(mm))

    def test_high_access_no_warning(self):
        payer = PayerAccessModel(access_probability=0.80, prior_auth_burden=0.30)
        mm = _market(payer_access=payer, peak_penetration=0.30)
        assert "payer_low_penetration_high" not in _codes(check_commercial_assumptions(mm))

    def test_low_penetration_no_warning(self):
        payer = PayerAccessModel(access_probability=0.30, prior_auth_burden=0.50)
        mm = _market(payer_access=payer, peak_penetration=0.10)
        assert "payer_low_penetration_high" not in _codes(check_commercial_assumptions(mm))

    def test_both_threshold_triggers_warning(self):
        payer = PayerAccessModel(access_probability=0.30, prior_auth_burden=0.50)
        mm = _market(payer_access=payer, peak_penetration=0.25)
        issues = check_commercial_assumptions(mm)
        assert "payer_low_penetration_high" in _codes(issues)

    def test_boundary_access_exactly_50_no_warning(self):
        payer = PayerAccessModel(access_probability=0.50)
        mm = _market(payer_access=payer, peak_penetration=0.30)
        assert "payer_low_penetration_high" not in _codes(check_commercial_assumptions(mm))

    def test_boundary_penetration_exactly_20_no_warning(self):
        payer = PayerAccessModel(access_probability=0.30)
        mm = _market(payer_access=payer, peak_penetration=0.20)
        assert "payer_low_penetration_high" not in _codes(check_commercial_assumptions(mm))


# ---------------------------------------------------------------------------
# Check 5: step_edit_double_counted
# ---------------------------------------------------------------------------

class TestStepEditDoubleCounted:
    def test_no_archetype_no_warning(self):
        payer = PayerAccessModel(step_edit_risk=0.50)
        mm = _market(payer_access=payer)
        assert "step_edit_double_counted" not in _codes(check_commercial_assumptions(mm))

    def test_archetype_no_payer_no_warning(self):
        mm = _market(launch_archetype=LaunchArchetype.STEP_EDIT_RESTRICTED)
        assert "step_edit_double_counted" not in _codes(check_commercial_assumptions(mm))

    def test_archetype_payer_no_step_edit_risk_no_warning(self):
        payer = PayerAccessModel(access_probability=0.70, prior_auth_burden=0.30, step_edit_risk=0.0)
        mm = _market(launch_archetype=LaunchArchetype.STEP_EDIT_RESTRICTED, payer_access=payer)
        assert "step_edit_double_counted" not in _codes(check_commercial_assumptions(mm))

    def test_archetype_plus_step_edit_risk_triggers_warning(self):
        payer = PayerAccessModel(step_edit_risk=0.50)
        mm = _market(launch_archetype=LaunchArchetype.STEP_EDIT_RESTRICTED, payer_access=payer)
        issues = check_commercial_assumptions(mm)
        assert "step_edit_double_counted" in _codes(issues)

    def test_different_archetype_with_step_edit_risk_no_warning(self):
        payer = PayerAccessModel(step_edit_risk=0.50)
        mm = _market(launch_archetype=LaunchArchetype.COMPETITIVE_LATE, payer_access=payer)
        assert "step_edit_double_counted" not in _codes(check_commercial_assumptions(mm))


# ---------------------------------------------------------------------------
# Check 6: gene_therapy_bolus_wrong_model
# ---------------------------------------------------------------------------

def _gene_therapy_ci(disease_model: str) -> CommercialInputs:
    pool_kwargs = dict(
        indication="SMA",
        disease_model=disease_model,
        prevalence_thousands=30.0,
        diagnosed_fraction=0.90,
        eligible_rate=0.80,
        treated_fraction=0.60,
    )
    if disease_model in ("incident_one_time", "incident_chronic"):
        pool_kwargs["annual_incidence_k"] = 0.5
    pool = PatientPool(**pool_kwargs)
    pricing = PricingModel.from_wac(wac_per_year_usd=2_000_000, gross_to_net_rate=0.05)
    share = ShareModel(peak_share=0.40, years_to_peak=1)
    return CommercialInputs(patient_pool=pool, pricing=pricing, share=share)


class TestGeneTherapyBolus:
    def test_bolus_archetype_correct_model_no_warning(self):
        ci = _gene_therapy_ci("incident_one_time")
        mm = _market(launch_archetype=LaunchArchetype.GENE_THERAPY_BOLUS, commercial_inputs=ci)
        assert "gene_therapy_bolus_wrong_model" not in _codes(check_commercial_assumptions(mm))

    def test_bolus_archetype_prevalent_triggers_warning(self):
        ci = _gene_therapy_ci("prevalent")
        mm = _market(launch_archetype=LaunchArchetype.GENE_THERAPY_BOLUS, commercial_inputs=ci)
        issues = check_commercial_assumptions(mm)
        assert "gene_therapy_bolus_wrong_model" in _codes(issues)

    def test_bolus_archetype_incident_chronic_triggers_warning(self):
        ci = _gene_therapy_ci("incident_chronic")
        mm = _market(launch_archetype=LaunchArchetype.GENE_THERAPY_BOLUS, commercial_inputs=ci)
        issues = check_commercial_assumptions(mm)
        assert "gene_therapy_bolus_wrong_model" in _codes(issues)

    def test_different_archetype_prevalent_no_warning(self):
        ci = _gene_therapy_ci("prevalent")
        mm = _market(launch_archetype=LaunchArchetype.ONCOLOGY_SPECIALIST, commercial_inputs=ci)
        assert "gene_therapy_bolus_wrong_model" not in _codes(check_commercial_assumptions(mm))

    def test_bolus_archetype_no_commercial_inputs_no_warning(self):
        mm = _market(launch_archetype=LaunchArchetype.GENE_THERAPY_BOLUS)
        assert "gene_therapy_bolus_wrong_model" not in _codes(check_commercial_assumptions(mm))


# ---------------------------------------------------------------------------
# Check 7: incident_one_time_missing_data
# ---------------------------------------------------------------------------

class TestIncidentOneTimeMissingData:
    def test_no_commercial_inputs_no_warning(self):
        mm = _market()
        assert "incident_one_time_missing_data" not in _codes(check_commercial_assumptions(mm))

    def test_prevalent_model_no_warning(self):
        ci = _gene_therapy_ci("prevalent")
        mm = _market(commercial_inputs=ci)
        assert "incident_one_time_missing_data" not in _codes(check_commercial_assumptions(mm))

    def test_incident_one_time_with_incidence_no_warning(self):
        ci = _gene_therapy_ci("incident_one_time")
        mm = _market(commercial_inputs=ci)
        assert "incident_one_time_missing_data" not in _codes(check_commercial_assumptions(mm))

    def test_incident_one_time_missing_incidence_raises(self):
        """PatientPool enforces annual_incidence_k at construction — no silent pass-through."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="annual_incidence_k"):
            PatientPool(
                indication="SMA",
                disease_model="incident_one_time",
                prevalence_thousands=30.0,
                diagnosed_fraction=0.90,
                eligible_rate=0.80,
                treated_fraction=0.60,
                # annual_incidence_k deliberately omitted
            )


# ---------------------------------------------------------------------------
# Multi-issue: verify multiple warnings can fire simultaneously
# ---------------------------------------------------------------------------

class TestMultipleIssues:
    def test_multiple_independent_warnings(self):
        """A config with several problems should return one warning per problem."""
        payer = PayerAccessModel(
            access_probability=0.30,   # → payer_low_penetration_high (with high penetration)
            step_edit_risk=0.50,       # → step_edit_double_counted (with archetype)
        )
        mm = _market(
            launch_archetype=LaunchArchetype.STEP_EDIT_RESTRICTED,
            payer_access=payer,
            peak_penetration=0.30,
        )
        issues = check_commercial_assumptions(mm)
        codes = _codes(issues)
        assert "step_edit_double_counted" in codes
        assert "payer_low_penetration_high" in codes

    def test_clean_config_no_warnings(self):
        """Minimal config with no optional features should produce no warnings."""
        mm = _market()
        assert check_commercial_assumptions(mm) == []
