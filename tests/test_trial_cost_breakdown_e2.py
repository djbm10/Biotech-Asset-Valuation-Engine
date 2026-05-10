"""
Sprint E2 — TrialCostBreakdown audit model.

Tests cover:
  1. TrialCostBreakdown: construction, total_millions, field validation
  2. ClinicalTrial.cost_breakdown: field presence, no-warning cases
  3. Warning logic: deviation > 5% emits UserWarning; ≤ 5% does not
  4. Breakdown has zero impact on CostModel computation
  5. Backward compatibility: trials without cost_breakdown behave identically
"""
from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from bve.entities.trial import ClinicalTrial, TrialCostBreakdown, _BREAKDOWN_DEVIATION_THRESHOLD
from bve.models.cost_model import CostModel
from bve.models.probability_model import ProbabilityModel
from bve.entities.asset import Asset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset() -> Asset:
    return Asset(
        id="e2-test",
        name="E2 Test",
        indication="Test",
        therapeutic_area="oncology",
        stage="phase_3",
        modality="small_molecule",
        discount_rate=0.10,
    )


def _trial(cost: float = 100.0, breakdown: TrialCostBreakdown | None = None) -> ClinicalTrial:
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        return ClinicalTrial(
            asset_id="e2-test",
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=cost,
            cost_source="override",
            cost_breakdown=breakdown,
        )


def _matching_breakdown(cost: float) -> TrialCostBreakdown:
    """Breakdown that sums to exactly cost."""
    return TrialCostBreakdown(
        cro_fees_millions=cost * 0.40,
        investigator_fees_millions=cost * 0.25,
        clinical_supply_millions=cost * 0.15,
        data_management_millions=cost * 0.10,
        regulatory_millions=cost * 0.05,
        internal_overhead_millions=cost * 0.05,
    )


# ---------------------------------------------------------------------------
# 1. TrialCostBreakdown model
# ---------------------------------------------------------------------------

class TestTrialCostBreakdown:
    def test_all_zeros_by_default(self):
        bd = TrialCostBreakdown()
        assert bd.total_millions == 0.0

    def test_total_is_sum_of_components(self):
        bd = TrialCostBreakdown(
            cro_fees_millions=40.0,
            investigator_fees_millions=25.0,
            clinical_supply_millions=15.0,
            data_management_millions=10.0,
            regulatory_millions=5.0,
            internal_overhead_millions=5.0,
        )
        assert bd.total_millions == pytest.approx(100.0, rel=1e-6)

    def test_other_millions_included_in_total(self):
        bd = TrialCostBreakdown(cro_fees_millions=80.0, other_millions=20.0)
        assert bd.total_millions == pytest.approx(100.0, rel=1e-6)

    def test_negative_component_rejected(self):
        with pytest.raises(ValidationError):
            TrialCostBreakdown(cro_fees_millions=-1.0)

    def test_source_and_notes_optional(self):
        bd = TrialCostBreakdown(
            cro_fees_millions=100.0,
            source="CRO bid grid Q1-2026",
            notes="Includes manufacturing scale-up.",
        )
        assert bd.source == "CRO bid grid Q1-2026"

    def test_frozen(self):
        bd = TrialCostBreakdown(cro_fees_millions=50.0)
        with pytest.raises(Exception):
            bd.cro_fees_millions = 100.0  # type: ignore

    def test_all_components_summed(self):
        bd = TrialCostBreakdown(
            cro_fees_millions=10.0,
            investigator_fees_millions=10.0,
            clinical_supply_millions=10.0,
            data_management_millions=10.0,
            regulatory_millions=10.0,
            internal_overhead_millions=10.0,
            other_millions=10.0,
        )
        assert bd.total_millions == pytest.approx(70.0, rel=1e-6)


# ---------------------------------------------------------------------------
# 2. ClinicalTrial.cost_breakdown field
# ---------------------------------------------------------------------------

class TestClinicalTrialBreakdownField:
    def test_breakdown_defaults_to_none(self):
        trial = _trial()
        assert trial.cost_breakdown is None

    def test_breakdown_stored_on_trial(self):
        bd = _matching_breakdown(100.0)
        trial = _trial(cost=100.0, breakdown=bd)
        assert trial.cost_breakdown is bd

    def test_breakdown_components_accessible(self):
        bd = TrialCostBreakdown(cro_fees_millions=40.0, investigator_fees_millions=60.0)
        trial = _trial(cost=100.0, breakdown=bd)
        assert trial.cost_breakdown.cro_fees_millions == pytest.approx(40.0)

    def test_trial_is_not_frozen(self):
        """ClinicalTrial is NOT frozen — supports model_copy updates in engine."""
        trial = _trial()
        updated = trial.model_copy(update={"cost_millions": 200.0})
        assert updated.cost_millions == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# 3. Warning logic
# ---------------------------------------------------------------------------

class TestBreakdownWarning:
    def test_no_breakdown_no_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _trial(cost=100.0, breakdown=None)
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) == 0

    def test_exact_match_no_warning(self):
        bd = _matching_breakdown(100.0)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ClinicalTrial(
                asset_id="e2-test",
                phase="phase_3",
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=100.0,
                cost_source="override",
                cost_breakdown=bd,
            )
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)
                         and "breakdown" in str(w.message).lower()]
        assert len(user_warnings) == 0

    def test_within_threshold_no_warning(self):
        """Deviation of exactly 4% should not trigger warning (< 5% threshold)."""
        total = 100.0
        bd = TrialCostBreakdown(cro_fees_millions=total * (1 - 0.04))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ClinicalTrial(
                asset_id="e2-test",
                phase="phase_3",
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=total,
                cost_source="override",
                cost_breakdown=bd,
            )
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)
                         and "breakdown" in str(w.message).lower()]
        assert len(user_warnings) == 0

    def test_over_threshold_emits_warning(self):
        """Deviation of 10% (> 5%) must emit a UserWarning."""
        bd = TrialCostBreakdown(cro_fees_millions=110.0)  # 10% above 100.0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ClinicalTrial(
                asset_id="e2-test",
                phase="phase_3",
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=100.0,
                cost_source="override",
                cost_breakdown=bd,
            )
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) >= 1

    def test_warning_message_contains_deviation(self):
        bd = TrialCostBreakdown(cro_fees_millions=120.0)  # 20% above 100.0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ClinicalTrial(
                asset_id="e2-test",
                phase="phase_3",
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=100.0,
                cost_source="override",
                cost_breakdown=bd,
            )
        breakdown_warnings = [w for w in caught if issubclass(w.category, UserWarning)
                               and "breakdown" in str(w.message).lower()]
        assert len(breakdown_warnings) == 1
        msg = str(breakdown_warnings[0].message)
        assert "phase_3" in msg
        assert "e2-test" in msg

    def test_warning_below_cost_also_triggers(self):
        """Breakdown total 15% BELOW cost_millions also triggers warning."""
        bd = TrialCostBreakdown(cro_fees_millions=85.0)  # 15% below 100.0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ClinicalTrial(
                asset_id="e2-test",
                phase="phase_3",
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=100.0,
                cost_source="override",
                cost_breakdown=bd,
            )
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) >= 1

    def test_all_zeros_breakdown_no_warning(self):
        """A breakdown with all zeros is informational — no warning."""
        bd = TrialCostBreakdown()  # total = 0.0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ClinicalTrial(
                asset_id="e2-test",
                phase="phase_3",
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=100.0,
                cost_source="override",
                cost_breakdown=bd,
            )
        breakdown_warnings = [w for w in caught if issubclass(w.category, UserWarning)
                               and "breakdown" in str(w.message).lower()]
        assert len(breakdown_warnings) == 0

    def test_threshold_constant_is_five_percent(self):
        """The documented 5% threshold is the actual constant."""
        assert _BREAKDOWN_DEVIATION_THRESHOLD == pytest.approx(0.05, rel=1e-6)


# ---------------------------------------------------------------------------
# 4. No impact on CostModel computation
# ---------------------------------------------------------------------------

class TestBreakdownNoComputationalImpact:
    def _make_prob(self, cost: float, breakdown: TrialCostBreakdown | None):
        asset = _asset()
        trial = ClinicalTrial(
            asset_id=asset.id,
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=cost,
            cost_source="override",
            cost_breakdown=breakdown,
        )
        return ProbabilityModel.compute(asset, [trial])

    def test_breakdown_does_not_change_pv_cost(self):
        """CostModel produces identical results with and without a breakdown."""
        r = 0.10
        prob_no_bd = self._make_prob(200.0, None)
        prob_with_bd = self._make_prob(200.0, _matching_breakdown(200.0))

        cost_no_bd = CostModel.compute(prob_no_bd, r)
        cost_with_bd = CostModel.compute(prob_with_bd, r)

        assert cost_no_bd.total_pv_weighted_millions == pytest.approx(
            cost_with_bd.total_pv_weighted_millions, rel=1e-6
        )

    def test_breakdown_mismatch_does_not_change_pv(self):
        """Even a mismatched breakdown has zero effect on computed cost."""
        r = 0.10
        bd_high = TrialCostBreakdown(cro_fees_millions=300.0)  # 50% above 200
        prob_no_bd = self._make_prob(200.0, None)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            prob_with_bd = self._make_prob(200.0, bd_high)

        cost_no_bd = CostModel.compute(prob_no_bd, r)
        cost_with_bd = CostModel.compute(prob_with_bd, r)

        assert cost_no_bd.total_pv_weighted_millions == pytest.approx(
            cost_with_bd.total_pv_weighted_millions, rel=1e-6
        )

    def test_cost_stream_phase_cost_uses_cost_millions(self):
        """PhaseCost.pv_cost_gross reflects cost_millions, not breakdown total."""
        r = 0.10
        cost = 200.0
        bd = TrialCostBreakdown(cro_fees_millions=999.0)  # deliberately wrong
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            prob = self._make_prob(cost, bd)
        cost_stream = CostModel.compute(prob, r)
        # The phase cost should reflect cost_millions=200, not bd.total=999
        phase_cost = cost_stream.phase_costs[0]
        expected_pv_gross = cost / (1 + r) ** ((phase_cost.year_start + phase_cost.year_end) / 2)
        assert phase_cost.pv_cost_gross == pytest.approx(expected_pv_gross, abs=0.02)


# ---------------------------------------------------------------------------
# 5. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_trial_without_breakdown_unchanged(self):
        """Trials without cost_breakdown are fully backward compatible."""
        trial = ClinicalTrial(
            asset_id="compat-test",
            phase="phase_2",
            success_probability=0.40,
            duration_years=2.5,
            cost_millions=75.0,
            cost_source="override",
        )
        assert trial.cost_breakdown is None

    def test_model_copy_preserves_none_breakdown(self):
        """model_copy(update=...) on a trial with no breakdown works correctly."""
        trial = ClinicalTrial(
            asset_id="compat-test",
            phase="phase_2",
            success_probability=0.40,
            duration_years=2.5,
            cost_millions=75.0,
        )
        updated = trial.model_copy(update={"cost_millions": 90.0})
        assert updated.cost_breakdown is None
        assert updated.cost_millions == pytest.approx(90.0)
