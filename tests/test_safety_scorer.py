"""Tests for safety_scorer.score_safety()."""
from __future__ import annotations

import pytest

from bve.models.pos_model import SafetyProfile
from bve.models.safety_scorer import (
    SafetyParams,
    SafetyScoringResult,
    _CAP_MAX,
    _CAP_MIN,
    score_safety,
)


# ---------------------------------------------------------------------------
# Helper: params with no modifiers active
# ---------------------------------------------------------------------------

def _params(category: SafetyProfile, **kwargs) -> SafetyParams:
    """Build SafetyParams with all positive modifiers disabled by default."""
    defaults = dict(
        reversible=False,
        monitorable=False,
        comparable_to_control=False,
    )
    defaults.update(kwargs)
    return SafetyParams(category=category, **defaults)


# ---------------------------------------------------------------------------
# Base category scores (no modifiers)
# ---------------------------------------------------------------------------

class TestBaseCategoryScores:
    def test_clean(self):
        r = score_safety(_params(SafetyProfile.CLEAN))
        assert r.adjustment == pytest.approx(+0.10)
        assert r.base_adjustment == pytest.approx(+0.10)

    def test_manageable(self):
        r = score_safety(_params(SafetyProfile.MANAGEABLE))
        assert r.adjustment == pytest.approx(0.00)

    def test_monitorable_concern(self):
        r = score_safety(_params(SafetyProfile.MONITORABLE_CONCERN))
        assert r.adjustment == pytest.approx(-0.20)

    def test_dose_limiting(self):
        r = score_safety(_params(SafetyProfile.DOSE_LIMITING))
        assert r.adjustment == pytest.approx(-0.40)

    def test_serious(self):
        r = score_safety(_params(SafetyProfile.SERIOUS))
        assert r.adjustment == pytest.approx(-0.65)

    def test_mechanism_linked_severe(self):
        r = score_safety(_params(SafetyProfile.MECHANISM_LINKED_SEVERE))
        assert r.adjustment == pytest.approx(-0.80)

    def test_legacy_minor_equals_manageable(self):
        r = score_safety(_params(SafetyProfile.MINOR))
        assert r.adjustment == pytest.approx(0.00)

    def test_legacy_concerning_equals_dose_limiting(self):
        r = score_safety(_params(SafetyProfile.CONCERNING))
        assert r.adjustment == pytest.approx(-0.40)

    def test_categories_monotonically_decrease(self):
        order = [
            SafetyProfile.CLEAN,
            SafetyProfile.MANAGEABLE,
            SafetyProfile.MONITORABLE_CONCERN,
            SafetyProfile.DOSE_LIMITING,
            SafetyProfile.SERIOUS,
            SafetyProfile.MECHANISM_LINKED_SEVERE,
        ]
        scores = [score_safety(_params(c)).adjustment for c in order]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]


# ---------------------------------------------------------------------------
# Positive modifiers
# ---------------------------------------------------------------------------

class TestPositiveModifiers:
    def test_reversible_adds_005(self):
        r_off = score_safety(_params(SafetyProfile.MANAGEABLE, reversible=False))
        r_on  = score_safety(_params(SafetyProfile.MANAGEABLE, reversible=True))
        assert r_on.adjustment - r_off.adjustment == pytest.approx(+0.05)

    def test_monitorable_adds_005(self):
        r_off = score_safety(_params(SafetyProfile.MANAGEABLE, monitorable=False))
        r_on  = score_safety(_params(SafetyProfile.MANAGEABLE, monitorable=True))
        assert r_on.adjustment - r_off.adjustment == pytest.approx(+0.05)

    def test_comparable_to_control_adds_005(self):
        r_off = score_safety(_params(SafetyProfile.MANAGEABLE, comparable_to_control=False))
        r_on  = score_safety(_params(SafetyProfile.MANAGEABLE, comparable_to_control=True))
        assert r_on.adjustment - r_off.adjustment == pytest.approx(+0.05)

    def test_all_three_positive_mods_sum_to_015(self):
        r = score_safety(_params(
            SafetyProfile.MANAGEABLE,
            reversible=True,
            monitorable=True,
            comparable_to_control=True,
        ))
        # base=0.00 + 0.05+0.05+0.05 = 0.15, capped at 0.15
        assert r.modifier_delta == pytest.approx(+0.15)
        assert r.adjustment == pytest.approx(+0.15)


# ---------------------------------------------------------------------------
# Negative modifiers
# ---------------------------------------------------------------------------

class TestNegativeModifiers:
    def test_high_discontinuation_subtracts_010(self):
        r_low  = score_safety(_params(SafetyProfile.DOSE_LIMITING, discontinuation_rate=0.10))
        r_high = score_safety(_params(SafetyProfile.DOSE_LIMITING, discontinuation_rate=0.20))
        assert r_low.adjustment - r_high.adjustment == pytest.approx(+0.10)
        assert "high_discontinuation_rate" in r_high.modifiers_applied
        assert "high_discontinuation_rate" not in r_low.modifiers_applied

    def test_discontinuation_at_threshold_not_triggered(self):
        r = score_safety(_params(SafetyProfile.MANAGEABLE, discontinuation_rate=0.15))
        assert "high_discontinuation_rate" not in r.modifiers_applied

    def test_treatment_related_death_subtracts_020(self):
        r_none = score_safety(_params(SafetyProfile.SERIOUS, treatment_related_deaths=0))
        r_one  = score_safety(_params(SafetyProfile.SERIOUS, treatment_related_deaths=1))
        assert r_none.adjustment - r_one.adjustment == pytest.approx(+0.20)
        assert "treatment_related_death_signal" in r_one.modifiers_applied

    def test_organ_toxicity_subtracts_015(self):
        r_off = score_safety(_params(SafetyProfile.DOSE_LIMITING, organ_toxicity_signal=False))
        r_on  = score_safety(_params(SafetyProfile.DOSE_LIMITING, organ_toxicity_signal=True))
        assert r_off.adjustment - r_on.adjustment == pytest.approx(+0.15)

    def test_class_known_risk_subtracts_015(self):
        r_off = score_safety(_params(SafetyProfile.DOSE_LIMITING, class_known_risk=False))
        r_on  = score_safety(_params(SafetyProfile.DOSE_LIMITING, class_known_risk=True))
        assert r_off.adjustment - r_on.adjustment == pytest.approx(+0.15)


# ---------------------------------------------------------------------------
# Cap behaviour
# ---------------------------------------------------------------------------

class TestCap:
    def test_positive_cap_at_015(self):
        # clean (+0.10) + all positive mods (+0.15) = +0.25 → capped at +0.15
        r = score_safety(_params(
            SafetyProfile.CLEAN,
            reversible=True,
            monitorable=True,
            comparable_to_control=True,
        ))
        assert r.adjustment == pytest.approx(_CAP_MAX)
        assert r.capped is True

    def test_negative_cap_at_minus_090(self):
        # mechanism_linked_severe (−0.80) + all negatives → capped at −0.90
        r = score_safety(SafetyParams(
            category=SafetyProfile.MECHANISM_LINKED_SEVERE,
            reversible=False,
            monitorable=False,
            comparable_to_control=False,
            discontinuation_rate=0.30,
            treatment_related_deaths=2,
            organ_toxicity_signal=True,
            class_known_risk=True,
        ))
        assert r.adjustment == pytest.approx(_CAP_MIN)
        assert r.capped is True

    def test_no_cap_within_range(self):
        r = score_safety(_params(SafetyProfile.MANAGEABLE))
        assert r.capped is False
        assert r.adjustment == pytest.approx(0.00)

    def test_raw_total_exceeds_cap_but_result_does_not(self):
        r = score_safety(_params(
            SafetyProfile.CLEAN,
            reversible=True,
            monitorable=True,
            comparable_to_control=True,
        ))
        assert r.base_adjustment + r.modifier_delta > _CAP_MAX
        assert r.adjustment <= _CAP_MAX


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    def test_returns_scoring_result(self):
        r = score_safety(_params(SafetyProfile.MANAGEABLE))
        assert isinstance(r, SafetyScoringResult)

    def test_rationale_non_empty(self):
        r = score_safety(_params(SafetyProfile.DOSE_LIMITING))
        assert isinstance(r.rationale, str)
        assert len(r.rationale) > 0

    def test_modifiers_applied_list(self):
        r = score_safety(_params(
            SafetyProfile.MANAGEABLE,
            reversible=True,
            monitorable=True,
        ))
        assert "reversible" in r.modifiers_applied
        assert "monitorable" in r.modifiers_applied
        assert "comparable_to_control" not in r.modifiers_applied

    def test_modifier_delta_sums_correctly(self):
        r = score_safety(_params(
            SafetyProfile.MANAGEABLE,
            reversible=True,
            monitorable=True,
            organ_toxicity_signal=True,
        ))
        # +0.05 + 0.05 − 0.15 = −0.05
        assert r.modifier_delta == pytest.approx(-0.05)
        assert r.adjustment == pytest.approx(-0.05)


# ---------------------------------------------------------------------------
# Default SafetyParams (all positives on by default)
# ---------------------------------------------------------------------------

class TestDefaultParams:
    def test_manageable_defaults_to_015(self):
        # Default: reversible=True, monitorable=True, comparable_to_control=True
        r = score_safety(SafetyParams(category=SafetyProfile.MANAGEABLE))
        assert r.adjustment == pytest.approx(+0.15)

    def test_dose_limiting_defaults_are_negative_offset(self):
        # base=-0.40 + 0.15 = -0.25
        r = score_safety(SafetyParams(category=SafetyProfile.DOSE_LIMITING))
        assert r.adjustment == pytest.approx(-0.25)
