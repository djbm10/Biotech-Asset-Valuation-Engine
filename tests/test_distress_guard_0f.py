"""Tests for Layer 0F — Distress Quality Guard (composite model).

Coverage:
  - distress_pressure_score composite (5 signals)
  - distress_quality_score composite (5 signals)
  - clinical_salvageability from sub-components
  - Guardrail rules: NONE / FLAG_ONLY / CAP_025 / CAP_015 / ROUTE
  - Backward-compat mapping from TargetEligibilityInput boolean fields
  - Float fields override boolean inference
  - Hard red flags (fatal safety, mechanism invalidated)
  - evaluate_layer0 integration
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_distress_guard import (
    ClinicalSalvageabilityInput,
    DistressClassification,
    DistressGuardInput,
    DistressGuardTreatment,
    compute_distress_guard,
    distress_guard_from_target,
)
from bve.intelligence.ma_eligibility import (
    CompanyTaxonomy,
    TargetEligibilityInput,
    evaluate_layer0,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inp(
    financing_pressure: float = 0.0,
    runway_pressure: float = 0.0,
    valuation_distress: float = 0.0,
    capital_market_access_risk: float = 0.0,
    near_term_funding_need: float = 0.0,
    lead_asset_quality: float = 0.65,
    platform_validation: float = 0.10,
    clinical_salvageability: float | None = None,
    strategic_scarcity: float = 0.50,
    asset_control_cleanliness: float = 0.70,
    salvageability_components: ClinicalSalvageabilityInput | None = None,
) -> DistressGuardInput:
    return DistressGuardInput(
        financing_pressure=financing_pressure,
        runway_pressure=runway_pressure,
        valuation_distress=valuation_distress,
        capital_market_access_risk=capital_market_access_risk,
        near_term_funding_need=near_term_funding_need,
        lead_asset_quality=lead_asset_quality,
        platform_validation=platform_validation,
        clinical_salvageability=clinical_salvageability,
        strategic_scarcity=strategic_scarcity,
        asset_control_cleanliness=asset_control_cleanliness,
        salvageability_components=salvageability_components,
    )


def _target(**kwargs) -> TargetEligibilityInput:
    defaults = dict(
        ticker="TEST",
        company_taxonomy=CompanyTaxonomy.THERAPEUTICS,
    )
    defaults.update(kwargs)
    return TargetEligibilityInput(**defaults)


def _high_pressure_inp(**kwargs) -> DistressGuardInput:
    """Helper for high-distress scenarios (pressure ≈ 0.70)."""
    defaults = dict(
        financing_pressure=0.80,
        runway_pressure=0.75,
        valuation_distress=0.65,
        capital_market_access_risk=0.60,
        near_term_funding_need=0.70,
    )
    defaults.update(kwargs)
    return _inp(**defaults)


# ---------------------------------------------------------------------------
# Section 1 — Distress Pressure Score
# ---------------------------------------------------------------------------

class TestDistressPressureScore:
    def test_no_pressure_signals_gives_low_score(self):
        r = compute_distress_guard(_inp())
        assert r.distress_pressure_score < 0.35

    def test_all_pressure_signals_at_one_gives_score_one(self):
        r = compute_distress_guard(_inp(
            financing_pressure=1.0,
            runway_pressure=1.0,
            valuation_distress=1.0,
            capital_market_access_risk=1.0,
            near_term_funding_need=1.0,
        ))
        assert r.distress_pressure_score == pytest.approx(1.0)

    def test_financing_pressure_weight_35pct(self):
        # Only financing_pressure=1.0, rest=0 → pressure = 0.35
        r = compute_distress_guard(_inp(financing_pressure=1.0))
        assert r.distress_pressure_score == pytest.approx(0.35, abs=0.001)

    def test_runway_pressure_weight_25pct(self):
        r = compute_distress_guard(_inp(runway_pressure=1.0))
        assert r.distress_pressure_score == pytest.approx(0.25, abs=0.001)

    def test_pressure_classification_not_distressed(self):
        r = compute_distress_guard(_inp(financing_pressure=0.30))
        assert r.distress_classification == DistressClassification.NOT_DISTRESSED

    def test_pressure_classification_mild(self):
        # pressure = 0.35*0.80 + 0.25*0.55 + 0.20*0.40 = 0.28+0.1375+0.08 = 0.4975 → MILD
        r = compute_distress_guard(_inp(
            financing_pressure=0.80,
            runway_pressure=0.55,
            valuation_distress=0.40,
        ))
        assert r.distress_classification == DistressClassification.MILD_PRESSURE

    def test_pressure_classification_high(self):
        r = compute_distress_guard(_high_pressure_inp())
        assert r.distress_classification in (
            DistressClassification.HIGH_DISTRESS, DistressClassification.SEVERE_DISTRESS
        )

    def test_pressure_classification_severe(self):
        r = compute_distress_guard(_inp(
            financing_pressure=1.0, runway_pressure=1.0,
            valuation_distress=1.0, capital_market_access_risk=0.80,
            near_term_funding_need=0.90,
        ))
        assert r.distress_classification == DistressClassification.SEVERE_DISTRESS


# ---------------------------------------------------------------------------
# Section 2 — Distress Quality Score
# ---------------------------------------------------------------------------

class TestDistressQualityScore:
    def test_high_lead_asset_quality_gives_high_score(self):
        r = compute_distress_guard(_inp(
            lead_asset_quality=0.90,
            platform_validation=0.80,
            clinical_salvageability=0.80,
            strategic_scarcity=0.80,
            asset_control_cleanliness=0.90,
        ))
        assert r.distress_quality_score >= 0.70

    def test_low_quality_all_signals_gives_low_score(self):
        r = compute_distress_guard(_inp(
            lead_asset_quality=0.10,
            platform_validation=0.05,
            clinical_salvageability=0.10,
            strategic_scarcity=0.10,
            asset_control_cleanliness=0.10,
        ))
        assert r.distress_quality_score < 0.20

    def test_lead_asset_weight_35pct(self):
        # Only lead_asset_quality=1.0, others=0
        r = compute_distress_guard(_inp(
            lead_asset_quality=1.0,
            platform_validation=0.0,
            clinical_salvageability=0.0,
            strategic_scarcity=0.0,
            asset_control_cleanliness=0.0,
        ))
        assert r.distress_quality_score == pytest.approx(0.35, abs=0.001)

    def test_platform_validation_weight_20pct(self):
        r = compute_distress_guard(_inp(
            lead_asset_quality=0.0,
            platform_validation=1.0,
            clinical_salvageability=0.0,
            strategic_scarcity=0.0,
            asset_control_cleanliness=0.0,
        ))
        assert r.distress_quality_score == pytest.approx(0.20, abs=0.001)


# ---------------------------------------------------------------------------
# Section 3 — Clinical Salvageability
# ---------------------------------------------------------------------------

class TestClinicalSalvageability:
    def test_underpowered_failure_is_salvageable(self):
        comp = ClinicalSalvageabilityInput(failed_trial_reason="underpowered")
        r = compute_distress_guard(_inp(salvageability_components=comp))
        assert r.clinical_salvageability_score >= 0.55

    def test_fatal_safety_is_low_salvageability(self):
        comp = ClinicalSalvageabilityInput(
            failed_trial_reason="fatal_safety",
            safety_reversibility=False,
        )
        r = compute_distress_guard(_inp(salvageability_components=comp))
        assert r.clinical_salvageability_score < 0.20

    def test_mechanism_invalidated_is_very_low(self):
        comp = ClinicalSalvageabilityInput(failed_trial_reason="mechanism_invalidated")
        r = compute_distress_guard(_inp(salvageability_components=comp))
        assert r.clinical_salvageability_score < 0.25

    def test_subgroup_signal_raises_score(self):
        comp_without = ClinicalSalvageabilityInput(failed_trial_reason="endpoint_miss")
        comp_with = ClinicalSalvageabilityInput(
            failed_trial_reason="endpoint_miss",
            subgroup_signal=True,
        )
        r1 = compute_distress_guard(_inp(salvageability_components=comp_without))
        r2 = compute_distress_guard(_inp(salvageability_components=comp_with))
        assert r2.clinical_salvageability_score > r1.clinical_salvageability_score

    def test_multiple_positive_signals_raise_score(self):
        comp = ClinicalSalvageabilityInput(
            failed_trial_reason="endpoint_miss",
            subgroup_signal=True,
            dose_response_exists=True,
            alternative_indications_available=True,
            regulatory_path_remaining=True,
            mechanism_still_valid=True,
        )
        r = compute_distress_guard(_inp(salvageability_components=comp))
        assert r.clinical_salvageability_score >= 0.75

    def test_no_components_gives_conservative_default(self):
        r = compute_distress_guard(_inp(salvageability_components=None))
        assert r.clinical_salvageability_score == pytest.approx(0.45)
        assert any("clinical_salvageability" in g for g in r.data_gaps)

    def test_direct_score_overrides_components(self):
        comp = ClinicalSalvageabilityInput(failed_trial_reason="mechanism_invalidated")
        r = compute_distress_guard(_inp(
            clinical_salvageability=0.80,  # direct override
            salvageability_components=comp,  # would produce ~0.10
        ))
        assert r.clinical_salvageability_score == pytest.approx(0.80)

    def test_score_clamped_at_1(self):
        comp = ClinicalSalvageabilityInput(
            failed_trial_reason="underpowered",
            subgroup_signal=True,
            dose_response_exists=True,
            safety_reversibility=True,
            alternative_indications_available=True,
            regulatory_path_remaining=True,
            mechanism_still_valid=True,
        )
        r = compute_distress_guard(_inp(salvageability_components=comp))
        assert r.clinical_salvageability_score <= 1.0


# ---------------------------------------------------------------------------
# Section 4 — Guardrail Rules
# ---------------------------------------------------------------------------

class TestGuardrailRules:
    def test_no_distress_applies_none_treatment(self):
        r = compute_distress_guard(_inp(financing_pressure=0.10))
        assert r.guardrail_applied == DistressGuardTreatment.NONE
        assert r.guard_active is False
        assert r.mna_probability_cap is None

    def test_mild_pressure_applies_flag_only(self):
        r = compute_distress_guard(_inp(
            financing_pressure=0.60,  # pressure ≈ 0.21 + some runway = ~0.35-0.40
            runway_pressure=0.40,
        ))
        # pressure ≈ 0.35*0.60 + 0.25*0.40 = 0.21+0.10 = 0.31 — borderline; add more
        r2 = compute_distress_guard(_inp(
            financing_pressure=0.70,
            runway_pressure=0.60,
            valuation_distress=0.30,
        ))
        # pressure = 0.35*0.70 + 0.25*0.60 + 0.20*0.30 = 0.245+0.15+0.06=0.455
        assert r2.guardrail_applied == DistressGuardTreatment.FLAG_ONLY
        assert r2.guard_active is False

    def test_high_distress_low_quality_caps_025(self):
        r = compute_distress_guard(_high_pressure_inp(
            lead_asset_quality=0.15,
            platform_validation=0.05,
            clinical_salvageability=0.10,
            strategic_scarcity=0.10,
            asset_control_cleanliness=0.10,
        ))
        assert r.guardrail_applied == DistressGuardTreatment.CAP_025
        assert r.guard_active is True
        assert r.mna_probability_cap == pytest.approx(0.25)
        assert r.reason_code == "distress_without_strategic_asset"

    def test_severe_distress_no_quality_caps_015(self):
        r = compute_distress_guard(_inp(
            financing_pressure=1.0,
            runway_pressure=1.0,
            valuation_distress=1.0,
            capital_market_access_risk=1.0,
            near_term_funding_need=1.0,
            lead_asset_quality=0.10,
            platform_validation=0.05,
            clinical_salvageability=0.05,
            strategic_scarcity=0.05,
            asset_control_cleanliness=0.05,
        ))
        assert r.guardrail_applied == DistressGuardTreatment.CAP_015
        assert r.guard_active is True
        assert r.mna_probability_cap == pytest.approx(0.15)
        assert r.reason_code == "broken_distress_case"

    def test_high_distress_high_quality_routes(self):
        r = compute_distress_guard(_high_pressure_inp(
            lead_asset_quality=0.80,
            platform_validation=0.75,
            clinical_salvageability=0.70,
            strategic_scarcity=0.75,
            asset_control_cleanliness=0.80,
        ))
        assert r.guardrail_applied == DistressGuardTreatment.ROUTE_DISTRESSED_OPTIONALITY
        assert r.guard_active is True
        assert r.mna_probability_cap is None
        assert r.route_to == "distressed_optionality_model"
        assert r.reason_code == "distress_with_viable_asset"

    def test_high_distress_medium_quality_flags_only(self):
        r = compute_distress_guard(_high_pressure_inp(
            lead_asset_quality=0.45,
            platform_validation=0.30,
            clinical_salvageability=0.45,
            strategic_scarcity=0.45,
            asset_control_cleanliness=0.50,
        ))
        assert r.guardrail_applied == DistressGuardTreatment.FLAG_ONLY
        assert r.guard_active is False
        assert r.mna_probability_cap is None

    def test_severe_rule_takes_precedence_over_cap_025(self):
        """pressure > 0.80 AND quality < 0.25 → CAP_015, not CAP_025."""
        r = compute_distress_guard(_inp(
            financing_pressure=1.0,
            runway_pressure=0.90,
            valuation_distress=0.90,
            capital_market_access_risk=0.80,
            near_term_funding_need=0.90,
            lead_asset_quality=0.10,
            platform_validation=0.05,
            clinical_salvageability=0.10,
            strategic_scarcity=0.10,
            asset_control_cleanliness=0.10,
        ))
        # quality ≈ 0.35*0.10+0.20*0.05+0.15*0.10+0.15*0.10+0.15*0.10
        # = 0.035+0.01+0.015+0.015+0.015 = 0.09 < 0.25 → broken
        assert r.guardrail_applied == DistressGuardTreatment.CAP_015

    def test_rationale_populated(self):
        r = compute_distress_guard(_high_pressure_inp(
            lead_asset_quality=0.10, clinical_salvageability=0.10,
        ))
        assert len(r.rationale) >= 3


# ---------------------------------------------------------------------------
# Section 5 — Boolean → Float inference (backward compat mapping)
# ---------------------------------------------------------------------------

class TestTargetAdapter:
    def test_financing_pressure_high_maps_to_075(self):
        t = _target(financing_pressure_high=True)
        inp = distress_guard_from_target(t)
        assert inp.financing_pressure == pytest.approx(0.75)

    def test_financing_pressure_low_maps_to_010(self):
        t = _target(financing_pressure_high=False)
        inp = distress_guard_from_target(t)
        assert inp.financing_pressure == pytest.approx(0.10)

    def test_lead_asset_quality_low_maps_to_020(self):
        t = _target(lead_asset_quality_low=True)
        inp = distress_guard_from_target(t)
        assert inp.lead_asset_quality == pytest.approx(0.20)

    def test_lead_asset_quality_ok_maps_to_065(self):
        t = _target(lead_asset_quality_low=False)
        inp = distress_guard_from_target(t)
        assert inp.lead_asset_quality == pytest.approx(0.65)

    def test_platform_validated_maps_to_080(self):
        t = _target(platform_validated=True)
        inp = distress_guard_from_target(t)
        assert inp.platform_validation == pytest.approx(0.80)

    def test_platform_company_not_validated_maps_to_040(self):
        t = _target(is_platform_company=True, platform_validated=False)
        inp = distress_guard_from_target(t)
        assert inp.platform_validation == pytest.approx(0.40)

    def test_no_platform_maps_to_010(self):
        t = _target(is_platform_company=False, platform_validated=False)
        inp = distress_guard_from_target(t)
        assert inp.platform_validation == pytest.approx(0.10)

    def test_float_financing_pressure_overrides_bool(self):
        t = _target(financing_pressure_high=False, financing_pressure=0.90)
        inp = distress_guard_from_target(t)
        assert inp.financing_pressure == pytest.approx(0.90)

    def test_float_lead_asset_quality_overrides_bool(self):
        t = _target(lead_asset_quality_low=True, lead_asset_quality=0.85)
        inp = distress_guard_from_target(t)
        assert inp.lead_asset_quality == pytest.approx(0.85)

    def test_salvageability_components_passed_when_present(self):
        t = _target(
            failed_trial_reason="underpowered",
            subgroup_signal=True,
        )
        inp = distress_guard_from_target(t)
        assert inp.salvageability_components is not None
        assert inp.salvageability_components.failed_trial_reason == "underpowered"
        assert inp.salvageability_components.subgroup_signal is True

    def test_no_salvageability_signals_gives_no_components(self):
        t = _target()
        inp = distress_guard_from_target(t)
        assert inp.salvageability_components is None


# ---------------------------------------------------------------------------
# Section 6 — Float field override paths through evaluate_layer0
# ---------------------------------------------------------------------------

class TestFloatFieldOverride:
    def test_high_float_pressure_overrides_boolean_false(self):
        """float financing_pressure=0.90 triggers guard even with bool flag False."""
        t = _target(
            financing_pressure_high=False,  # old bool says not distressed
            financing_pressure=0.90,        # new float says severe distress
            runway_pressure=0.85,
            valuation_distress=0.80,
            capital_market_access_risk=0.75,
            near_term_funding_need=0.85,
            lead_asset_quality=0.10,
            lead_asset_quality_low=False,   # old bool says ok
            platform_validation_score=0.05,
            clinical_salvageability_score=0.05,
            strategic_scarcity=0.05,
            asset_control_cleanliness_score=0.05,
        )
        r = evaluate_layer0(t)
        assert r.distress_guard.guard_active is True
        assert r.distress_guard.mna_probability_cap is not None

    def test_route_to_appears_in_layer0_notes(self):
        """When guard routes to distressed_optionality_model, note is added."""
        t = _target(
            financing_pressure=0.90,
            runway_pressure=0.85,
            valuation_distress=0.80,
            capital_market_access_risk=0.75,
            near_term_funding_need=0.85,
            lead_asset_quality=0.85,
            platform_validation_score=0.80,
            clinical_salvageability_score=0.75,
            strategic_scarcity=0.80,
            asset_control_cleanliness_score=0.80,
        )
        r = evaluate_layer0(t)
        if r.distress_guard.route_to is not None:
            assert any("distress_route" in n for n in r.layer0_notes)


# ---------------------------------------------------------------------------
# Section 7 — Hard red flag scenarios
# ---------------------------------------------------------------------------

class TestHardRedFlags:
    def test_fatal_safety_under_severe_distress_broken(self):
        """Fatal irreversible safety + severe distress = broken_distress_case."""
        comp = ClinicalSalvageabilityInput(
            failed_trial_reason="fatal_safety",
            safety_reversibility=False,
        )
        r = compute_distress_guard(_inp(
            financing_pressure=1.0,
            runway_pressure=1.0,
            valuation_distress=1.0,
            capital_market_access_risk=0.90,
            near_term_funding_need=1.0,
            lead_asset_quality=0.10,
            platform_validation=0.05,
            strategic_scarcity=0.05,
            asset_control_cleanliness=0.05,
            salvageability_components=comp,
        ))
        assert r.guardrail_applied == DistressGuardTreatment.CAP_015
        assert r.clinical_salvageability_score < 0.10

    def test_mechanism_invalidated_under_high_distress(self):
        """Mechanism invalidated + high distress + no platform = value trap."""
        comp = ClinicalSalvageabilityInput(failed_trial_reason="mechanism_invalidated")
        r = compute_distress_guard(_high_pressure_inp(
            lead_asset_quality=0.10,
            platform_validation=0.05,
            strategic_scarcity=0.10,
            asset_control_cleanliness=0.20,
            salvageability_components=comp,
        ))
        assert r.guard_active is True
        assert r.mna_probability_cap is not None
        assert r.mna_probability_cap <= 0.25

    def test_underpowered_trial_with_viable_asset_may_route(self):
        """Underpowered failure but strong asset quality → may route, not hard cap."""
        comp = ClinicalSalvageabilityInput(
            failed_trial_reason="underpowered",
            subgroup_signal=True,
            dose_response_exists=True,
            regulatory_path_remaining=True,
            mechanism_still_valid=True,
        )
        r = compute_distress_guard(_high_pressure_inp(
            lead_asset_quality=0.75,
            platform_validation=0.60,
            strategic_scarcity=0.70,
            asset_control_cleanliness=0.75,
            salvageability_components=comp,
        ))
        # With salvageable asset and high quality, should route or flag — not hard cap
        assert r.guardrail_applied in (
            DistressGuardTreatment.ROUTE_DISTRESSED_OPTIONALITY,
            DistressGuardTreatment.FLAG_ONLY,
        )
        assert r.mna_probability_cap is None
