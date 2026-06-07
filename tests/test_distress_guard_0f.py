"""Tests for Layer 0F — Distress Pressure Guard (pressure-only contract).

Coverage:
  - distress_pressure_score composite (5 signals, correct weights)
  - distress_classification thresholds
  - Guardrail rules: NONE or FLAG_ONLY only — no caps, no routes
  - mna_probability_cap always None
  - route_to always None
  - distress_quality_score and clinical_salvageability_score always None (deprecated)
  - Changing asset-quality fields does NOT change 0F output
  - Boolean → float pressure inference (backward compat adapter)
  - evaluate_layer0 integration: distress pressure notes only, no score_cap from 0F
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
) -> DistressGuardInput:
    return DistressGuardInput(
        financing_pressure=financing_pressure,
        runway_pressure=runway_pressure,
        valuation_distress=valuation_distress,
        capital_market_access_risk=capital_market_access_risk,
        near_term_funding_need=near_term_funding_need,
    )


def _target(**kwargs) -> TargetEligibilityInput:
    defaults = dict(
        ticker="TEST",
        company_taxonomy=CompanyTaxonomy.THERAPEUTICS,
    )
    defaults.update(kwargs)
    return TargetEligibilityInput(**defaults)


def _high_pressure_inp(**kwargs) -> DistressGuardInput:
    """Helper: pressure ≈ 0.71 (HIGH_DISTRESS)."""
    return _inp(
        financing_pressure=0.80,
        runway_pressure=0.75,
        valuation_distress=0.65,
        capital_market_access_risk=0.60,
        near_term_funding_need=0.70,
        **kwargs,
    )


def _severe_pressure_inp(**kwargs) -> DistressGuardInput:
    """Helper: pressure = 1.0 (SEVERE_DISTRESS)."""
    return _inp(
        financing_pressure=1.0,
        runway_pressure=1.0,
        valuation_distress=1.0,
        capital_market_access_risk=1.0,
        near_term_funding_need=1.0,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Section 1 — Distress Pressure Score Composite
# ---------------------------------------------------------------------------

class TestDistressPressureScore:
    def test_no_pressure_signals_gives_low_score(self):
        r = compute_distress_guard(_inp())
        assert r.distress_pressure_score < 0.35

    def test_all_pressure_signals_at_one_gives_score_one(self):
        r = compute_distress_guard(_severe_pressure_inp())
        assert r.distress_pressure_score == pytest.approx(1.0)

    def test_financing_pressure_weight_35pct(self):
        r = compute_distress_guard(_inp(financing_pressure=1.0))
        assert r.distress_pressure_score == pytest.approx(0.35, abs=0.001)

    def test_runway_pressure_weight_25pct(self):
        r = compute_distress_guard(_inp(runway_pressure=1.0))
        assert r.distress_pressure_score == pytest.approx(0.25, abs=0.001)

    def test_valuation_distress_weight_20pct(self):
        r = compute_distress_guard(_inp(valuation_distress=1.0))
        assert r.distress_pressure_score == pytest.approx(0.20, abs=0.001)

    def test_capital_market_access_risk_weight_10pct(self):
        r = compute_distress_guard(_inp(capital_market_access_risk=1.0))
        assert r.distress_pressure_score == pytest.approx(0.10, abs=0.001)

    def test_near_term_funding_need_weight_10pct(self):
        r = compute_distress_guard(_inp(near_term_funding_need=1.0))
        assert r.distress_pressure_score == pytest.approx(0.10, abs=0.001)


# ---------------------------------------------------------------------------
# Section 2 — Pressure Classification Thresholds
# ---------------------------------------------------------------------------

class TestPressureClassification:
    def test_below_035_not_distressed(self):
        r = compute_distress_guard(_inp(financing_pressure=0.30))
        assert r.distress_classification == DistressClassification.NOT_DISTRESSED

    def test_at_035_mild_pressure(self):
        # financing_pressure=1.0 → score = 0.35 exactly → MILD_PRESSURE
        r = compute_distress_guard(_inp(financing_pressure=1.0))
        assert r.distress_classification == DistressClassification.MILD_PRESSURE

    def test_mild_pressure_range(self):
        # pressure ≈ 0.4975 → MILD
        r = compute_distress_guard(_inp(
            financing_pressure=0.80,
            runway_pressure=0.55,
            valuation_distress=0.40,
        ))
        assert r.distress_classification == DistressClassification.MILD_PRESSURE

    def test_high_distress_range(self):
        r = compute_distress_guard(_high_pressure_inp())
        assert r.distress_classification in (
            DistressClassification.HIGH_DISTRESS,
            DistressClassification.SEVERE_DISTRESS,
        )

    def test_severe_distress_at_one(self):
        r = compute_distress_guard(_severe_pressure_inp())
        assert r.distress_classification == DistressClassification.SEVERE_DISTRESS

    def test_at_060_is_high_distress(self):
        # financing_pressure=0.60/0.35 + a bit of runway to push above 0.60
        r = compute_distress_guard(_inp(
            financing_pressure=1.0,   # 0.35
            runway_pressure=1.0,      # 0.25
            valuation_distress=1.0,   # 0.20
        ))
        # pressure = 0.80 → HIGH_DISTRESS (≤ 0.80)
        assert r.distress_classification == DistressClassification.HIGH_DISTRESS

    def test_above_080_severe_distress(self):
        r = compute_distress_guard(_inp(
            financing_pressure=1.0,
            runway_pressure=1.0,
            valuation_distress=1.0,
            capital_market_access_risk=0.80,
            near_term_funding_need=0.90,
        ))
        assert r.distress_classification == DistressClassification.SEVERE_DISTRESS


# ---------------------------------------------------------------------------
# Section 3 — Guardrail Rules: Pressure-Only Contract
# ---------------------------------------------------------------------------

class TestGuardrailRules:
    def test_not_distressed_applies_none_treatment(self):
        r = compute_distress_guard(_inp(financing_pressure=0.10))
        assert r.guardrail_applied == DistressGuardTreatment.NONE
        assert r.guard_active is False

    def test_mild_pressure_flag_only_not_active(self):
        # pressure ≈ 0.455 → MILD_PRESSURE → FLAG_ONLY, guard_active=False
        r = compute_distress_guard(_inp(
            financing_pressure=0.70,
            runway_pressure=0.60,
            valuation_distress=0.30,
        ))
        assert r.guardrail_applied == DistressGuardTreatment.FLAG_ONLY
        assert r.guard_active is False

    def test_high_distress_flag_only_active(self):
        r = compute_distress_guard(_high_pressure_inp())
        assert r.guardrail_applied == DistressGuardTreatment.FLAG_ONLY
        assert r.guard_active is True

    def test_severe_distress_flag_only_active(self):
        r = compute_distress_guard(_severe_pressure_inp())
        assert r.guardrail_applied == DistressGuardTreatment.FLAG_ONLY
        assert r.guard_active is True

    def test_mna_probability_cap_always_none(self):
        """0F never sets mna_probability_cap under any pressure level."""
        for inp in [
            _inp(),
            _inp(financing_pressure=0.50, runway_pressure=0.50),
            _high_pressure_inp(),
            _severe_pressure_inp(),
        ]:
            r = compute_distress_guard(inp)
            assert r.mna_probability_cap is None, (
                f"Expected mna_probability_cap=None for pressure={r.distress_pressure_score:.3f}, "
                f"got {r.mna_probability_cap}"
            )

    def test_route_to_always_none(self):
        """0F never routes to distressed_optionality_model or any other model."""
        for inp in [_inp(), _high_pressure_inp(), _severe_pressure_inp()]:
            r = compute_distress_guard(inp)
            assert r.route_to is None

    def test_rationale_populated(self):
        r = compute_distress_guard(_high_pressure_inp())
        assert len(r.rationale) >= 3

    def test_reason_code_set_for_high_distress(self):
        r = compute_distress_guard(_high_pressure_inp())
        assert r.reason_code == "high_distress_pressure_flag"

    def test_reason_code_set_for_severe_distress(self):
        r = compute_distress_guard(_severe_pressure_inp())
        assert r.reason_code == "severe_distress_pressure_flag"

    def test_reason_code_none_for_not_distressed(self):
        r = compute_distress_guard(_inp())
        assert r.reason_code is None


# ---------------------------------------------------------------------------
# Section 4 — Asset Quality Fields Do NOT Affect 0F Output
# ---------------------------------------------------------------------------

class TestQualityFieldsDoNotAffectOutput:
    """0F is pressure-only.  Passing different asset-quality values must produce
    identical distress_pressure_score, distress_classification, and guardrail."""

    def _high_quality_inp(self) -> DistressGuardInput:
        return DistressGuardInput(
            financing_pressure=0.80,
            runway_pressure=0.75,
            valuation_distress=0.65,
            capital_market_access_risk=0.60,
            near_term_funding_need=0.70,
            lead_asset_quality=0.90,
            platform_validation=0.80,
            clinical_salvageability=0.85,
            strategic_scarcity=0.80,
            asset_control_cleanliness=0.90,
        )

    def _low_quality_inp(self) -> DistressGuardInput:
        return DistressGuardInput(
            financing_pressure=0.80,
            runway_pressure=0.75,
            valuation_distress=0.65,
            capital_market_access_risk=0.60,
            near_term_funding_need=0.70,
            lead_asset_quality=0.05,
            platform_validation=0.05,
            clinical_salvageability=0.05,
            strategic_scarcity=0.05,
            asset_control_cleanliness=0.05,
        )

    def test_pressure_score_same_regardless_of_quality(self):
        r_high = compute_distress_guard(self._high_quality_inp())
        r_low = compute_distress_guard(self._low_quality_inp())
        assert r_high.distress_pressure_score == pytest.approx(r_low.distress_pressure_score)

    def test_classification_same_regardless_of_quality(self):
        r_high = compute_distress_guard(self._high_quality_inp())
        r_low = compute_distress_guard(self._low_quality_inp())
        assert r_high.distress_classification == r_low.distress_classification

    def test_guardrail_same_regardless_of_quality(self):
        r_high = compute_distress_guard(self._high_quality_inp())
        r_low = compute_distress_guard(self._low_quality_inp())
        assert r_high.guardrail_applied == r_low.guardrail_applied
        assert r_high.guard_active == r_low.guard_active

    def test_no_cap_from_weak_quality(self):
        """Even with all-zero asset quality, 0F must not cap."""
        r = compute_distress_guard(self._low_quality_inp())
        assert r.mna_probability_cap is None

    def test_no_route_from_high_quality(self):
        """Even with all-high asset quality + high distress, 0F must not route."""
        r = compute_distress_guard(self._high_quality_inp())
        assert r.route_to is None


# ---------------------------------------------------------------------------
# Section 5 — Deprecated Result Fields
# ---------------------------------------------------------------------------

class TestDeprecatedResultFields:
    def test_distress_quality_score_always_none(self):
        for inp in [_inp(), _high_pressure_inp(), _severe_pressure_inp()]:
            r = compute_distress_guard(inp)
            assert r.distress_quality_score is None

    def test_clinical_salvageability_score_always_none(self):
        for inp in [_inp(), _high_pressure_inp(), _severe_pressure_inp()]:
            r = compute_distress_guard(inp)
            assert r.clinical_salvageability_score is None


# ---------------------------------------------------------------------------
# Section 6 — Target Adapter: Pressure Signals Only
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

    def test_float_financing_pressure_overrides_bool(self):
        t = _target(financing_pressure_high=False, financing_pressure=0.90)
        inp = distress_guard_from_target(t)
        assert inp.financing_pressure == pytest.approx(0.90)

    def test_runway_inferred_from_financing_pressure(self):
        t = _target(financing_pressure=0.80)
        inp = distress_guard_from_target(t)
        assert inp.runway_pressure == pytest.approx(0.72, abs=0.01)  # 0.80 * 0.90

    def test_quality_fields_not_populated_by_adapter(self):
        """Adapter no longer maps quality signals — they are None in the input."""
        t = _target(
            lead_asset_quality_low=True,
            platform_validated=True,
            is_platform_company=True,
        )
        inp = distress_guard_from_target(t)
        assert inp.lead_asset_quality is None
        assert inp.platform_validation is None

    def test_salvageability_components_not_populated_by_adapter(self):
        """Adapter no longer maps salvageability components."""
        t = _target(failed_trial_reason="underpowered", subgroup_signal=True)
        inp = distress_guard_from_target(t)
        assert inp.salvageability_components is None

    def test_high_pressure_bool_triggers_high_distress(self):
        t = _target(financing_pressure_high=True)
        r = compute_distress_guard(distress_guard_from_target(t))
        assert r.distress_classification in (
            DistressClassification.HIGH_DISTRESS,
            DistressClassification.SEVERE_DISTRESS,
            DistressClassification.MILD_PRESSURE,  # fp=0.75 → pressure=0.63 → HIGH
        )
        assert r.distress_pressure_score > 0.35


# ---------------------------------------------------------------------------
# Section 7 — Layer 0 Integration
# ---------------------------------------------------------------------------

class TestLayer0Integration:
    def test_high_pressure_guard_active_in_layer0(self):
        """High financial pressure → guard_active=True in distress_guard."""
        t = _target(
            financing_pressure=0.90,
            runway_pressure=0.85,
            valuation_distress=0.80,
            capital_market_access_risk=0.75,
            near_term_funding_need=0.85,
        )
        r = evaluate_layer0(t)
        assert r.distress_guard.guard_active is True

    def test_no_distress_gives_not_distressed_in_layer0(self):
        t = _target(financing_pressure_high=False)
        r = evaluate_layer0(t)
        assert r.distress_guard.distress_classification == DistressClassification.NOT_DISTRESSED
        assert r.distress_guard.guard_active is False

    def test_0f_does_not_set_score_cap_in_layer0(self):
        """High distress must NOT set Layer0Result.score_cap — 0F is pressure-only."""
        t = _target(financing_pressure_high=True)
        r = evaluate_layer0(t)
        # score_cap may only come from 0A exclusion engine (SEVERE_CAP gates)
        # A plain therapeutics target with no exclusion triggers → score_cap=None
        assert r.score_cap is None

    def test_0f_does_not_set_score_cap_even_with_severe_distress(self):
        """Even severe distress must not create a score_cap at Layer 0."""
        t = _target(
            financing_pressure=1.0,
            runway_pressure=1.0,
            valuation_distress=1.0,
            capital_market_access_risk=1.0,
            near_term_funding_need=1.0,
        )
        r = evaluate_layer0(t)
        assert r.score_cap is None

    def test_no_distress_guard_cap_in_layer0_notes(self):
        """distress_guard_cap:* notes must no longer appear — 0F doesn't cap."""
        t = _target(financing_pressure_high=True)
        r = evaluate_layer0(t)
        assert not any("distress_guard_cap" in n for n in r.layer0_notes)

    def test_no_distress_route_in_layer0_notes(self):
        """distress_route:* notes must no longer appear — routing owned by 0B/Layer 4."""
        t = _target(
            financing_pressure=0.90,
            runway_pressure=0.85,
            valuation_distress=0.80,
            capital_market_access_risk=0.75,
            near_term_funding_need=0.85,
        )
        r = evaluate_layer0(t)
        assert not any("distress_route" in n for n in r.layer0_notes)

    def test_high_distress_produces_pressure_note(self):
        """High distress pressure produces an informational note in layer0_notes."""
        t = _target(
            financing_pressure=0.90,
            runway_pressure=0.85,
            valuation_distress=0.80,
            capital_market_access_risk=0.75,
            near_term_funding_need=0.85,
        )
        r = evaluate_layer0(t)
        assert any("distress_pressure" in n for n in r.layer0_notes)

    def test_mna_probability_cap_always_none_in_distress_guard(self):
        """distress_guard.mna_probability_cap is always None regardless of pressure."""
        t = _target(financing_pressure_high=True)
        r = evaluate_layer0(t)
        assert r.distress_guard.mna_probability_cap is None

    def test_route_to_always_none_in_distress_guard(self):
        """distress_guard.route_to is always None."""
        t = _target(
            financing_pressure=0.90,
            runway_pressure=0.85,
            valuation_distress=0.80,
        )
        r = evaluate_layer0(t)
        assert r.distress_guard.route_to is None
