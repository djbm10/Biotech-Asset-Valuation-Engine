"""Tests for Layer 0E — Target Integration Complexity Flag + Pair-Specific G8 Adjustment.

8 required scenarios:
  1. Simple target → LOW complexity, no buyer check
  2. Complex commercial target → HIGH/SEVERE, requires buyer check
  3. Complex target + strong acquirer → low penalty, no cap
  4. Complex target + weak acquirer → high penalty, G8 cap
  5. Manufacturing-heavy target → high mfg_transfer component
  6. Missing data → conservative score + data_gaps populated
  7. Double-count prevention test
  8. G8 gate test (adjusted_integration_penalty >= 0.50 triggers G8)
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_integration_complexity import (
    AcquirerIntegrationProfile,
    IntegrationComplexityLevel,
    PairIntegrationAdjustment,
    TargetIntegrationComplexityFlag,
    compute_pair_integration_adjustment,
    compute_target_integration_complexity,
)
from bve.intelligence.ma_eligibility import (
    evaluate_layer0,
    TargetEligibilityInput,
    CompanyTaxonomy,
)
from bve.intelligence.ma_layer3_gate import (
    GateInputs,
    DriverBucketInputs,
    compute_layer3,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target(**kwargs) -> TargetEligibilityInput:
    defaults = dict(
        ticker="TEST",
        company_taxonomy=CompanyTaxonomy.THERAPEUTICS,
        enterprise_value_millions=500.0,
        product_count=1,
        indication_count=1,
        manufacturing_complexity="low",
        geographic_complexity="local",
        payer_access_complexity="low",
        salesforce_required=False,
    )
    defaults.update(kwargs)
    return TargetEligibilityInput(**defaults)


def _acquirer(
    acquirer_id: str = "AQ-TEST",
    commercial: float = 0.70,
    manufacturing: float = 0.70,
    payer: float = 0.70,
    geo: float = 0.70,
    systems: float = 0.70,
    experience: float = 0.70,
) -> AcquirerIntegrationProfile:
    return AcquirerIntegrationProfile(
        acquirer_id=acquirer_id,
        commercial_infrastructure_fit=commercial,
        manufacturing_capability_fit=manufacturing,
        payer_access_capability_fit=payer,
        geographic_footprint_fit=geo,
        systems_compliance_capability_fit=systems,
        prior_integration_experience=experience,
    )


def _gate_inputs(
    adjusted_integration_penalty: float | None = None,
    integration_complexity_severe: bool = False,
    affordability: float = 0.80,
    antitrust_risk_high: bool = False,
) -> GateInputs:
    return GateInputs(
        asset_quality=0.70,
        acquirer_right_to_win=0.70,
        seller_willingness=0.60,
        financing_pressure=0.20,
        no_active_process_signal=False,
        asset_control=0.80,
        affordability=affordability,
        antitrust_risk_high=antitrust_risk_high,
        integration_complexity_severe=integration_complexity_severe,
        adjusted_integration_penalty=adjusted_integration_penalty,
    )


def _driver_inputs() -> DriverBucketInputs:
    return DriverBucketInputs(
        financing_pressure=0.20,
        external_deal_activity=0.70,
        pipeline_gap_urgency=0.70,
        activist_signal=0.00,
        strategic_review_signal=0.00,
        catalyst_proximity=0.70,
        scarcity_score=0.80,
        acquirer_fit_score=0.80,
        valuation_discount=0.60,
        de_risking_stage=0.60,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — Simple target → LOW complexity, no buyer capability check
# ---------------------------------------------------------------------------

class TestScenario1SimpleTarget:
    """Single-product, single-indication, local ops, no specialty salesforce."""

    def test_complexity_level_is_low(self):
        t = _target()
        cc = compute_target_integration_complexity(t)
        assert cc.complexity_level == IntegrationComplexityLevel.LOW

    def test_raw_score_below_low_threshold(self):
        t = _target()
        cc = compute_target_integration_complexity(t)
        assert cc.raw_integration_complexity_score < 0.25

    def test_no_buyer_capability_check_required(self):
        t = _target()
        cc = compute_target_integration_complexity(t)
        assert cc.requires_buyer_capability_check is False

    def test_no_complexity_flags_for_simple_target(self):
        t = _target()
        cc = compute_target_integration_complexity(t)
        # Simple target should have minimal flags
        assert len(cc.complexity_flags) == 0

    def test_layer0_propagates_low_complexity(self):
        t = _target()
        r = evaluate_layer0(t)
        assert r.raw_integration_complexity_score < 0.25
        assert r.requires_buyer_capability_check is False


# ---------------------------------------------------------------------------
# Scenario 2 — Complex commercial target → HIGH/SEVERE, requires buyer check
# ---------------------------------------------------------------------------

class TestScenario2ComplexTarget:
    """Multi-product, multi-indication, global ops, specialty salesforce."""

    def test_complexity_level_is_high_or_severe(self):
        t = _target(
            product_count=10,
            indication_count=3,
            manufacturing_complexity="high",
            geographic_complexity="global",
            payer_access_complexity="high",
            salesforce_required=True,
        )
        cc = compute_target_integration_complexity(t)
        assert cc.complexity_level in (
            IntegrationComplexityLevel.HIGH, IntegrationComplexityLevel.SEVERE
        )

    def test_raw_score_above_high_threshold(self):
        t = _target(
            product_count=10,
            indication_count=3,
            manufacturing_complexity="high",
            geographic_complexity="global",
            payer_access_complexity="high",
            salesforce_required=True,
        )
        cc = compute_target_integration_complexity(t)
        assert cc.raw_integration_complexity_score >= 0.45

    def test_buyer_capability_check_required(self):
        t = _target(
            product_count=8,
            manufacturing_complexity="high",
            geographic_complexity="global",
            payer_access_complexity="high",
        )
        cc = compute_target_integration_complexity(t)
        assert cc.requires_buyer_capability_check is True

    def test_multiple_complexity_flags_present(self):
        t = _target(
            product_count=10,
            manufacturing_complexity="high",
            geographic_complexity="global",
            payer_access_complexity="high",
            salesforce_required=True,
        )
        cc = compute_target_integration_complexity(t)
        assert len(cc.complexity_flags) >= 3

    def test_component_scores_reflect_complexity(self):
        t = _target(
            manufacturing_complexity="high",
            geographic_complexity="global",
            payer_access_complexity="high",
        )
        cc = compute_target_integration_complexity(t)
        assert cc.component_scores["manufacturing_transfer_complexity"] == pytest.approx(0.85)
        assert cc.component_scores["geographic_complexity"] == pytest.approx(0.80)
        assert cc.component_scores["payer_access_complexity"] == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# Scenario 3 — Complex target + strong acquirer → low penalty, no G8 cap
# ---------------------------------------------------------------------------

class TestScenario3StrongAcquirer:
    """High complexity target but acquirer has strong integration capability."""

    def setup_method(self):
        t = _target(
            product_count=8,
            manufacturing_complexity="high",
            geographic_complexity="global",
            payer_access_complexity="high",
            salesforce_required=True,
        )
        cc = compute_target_integration_complexity(t)
        # Strong acquirer: all dims 0.85+
        acq = _acquirer(
            commercial=0.90, manufacturing=0.90, payer=0.90,
            geo=0.90, systems=0.85, experience=0.85,
        )
        self.adj = compute_pair_integration_adjustment(cc, acq)

    def test_high_buyer_capability(self):
        assert self.adj.buyer_integration_capability >= 0.85

    def test_penalty_below_g8_trigger(self):
        # Strong buyer capability neutralises raw complexity → penalty < 0.50
        assert self.adj.adjusted_integration_penalty < 0.50

    def test_no_g8_cap_applied(self):
        assert self.adj.max_score_cap is None

    def test_pair_level_fail_false(self):
        assert self.adj.pair_level_fail is False

    def test_multiplier_near_one(self):
        # Low penalty → multiplier should be >= 0.85
        assert self.adj.multiplier >= 0.85

    def test_g8_not_triggered_for_strong_acquirer(self):
        gate_inputs = _gate_inputs(
            adjusted_integration_penalty=self.adj.adjusted_integration_penalty
        )
        result = compute_layer3(0.75, _driver_inputs(), gate_inputs)
        assert "G8" not in result.active_gate_ids


# ---------------------------------------------------------------------------
# Scenario 4 — Complex target + weak acquirer → high penalty, G8 cap applied
# ---------------------------------------------------------------------------

class TestScenario4WeakAcquirer:
    """High complexity target + weak acquirer → G8 triggered with tiered cap."""

    def setup_method(self):
        t = _target(
            product_count=10,
            indication_count=3,
            manufacturing_complexity="high",
            geographic_complexity="global",
            payer_access_complexity="high",
            salesforce_required=True,
        )
        cc = compute_target_integration_complexity(t)
        # Weak acquirer: all dims 0.20
        acq = _acquirer(
            commercial=0.20, manufacturing=0.20, payer=0.20,
            geo=0.20, systems=0.20, experience=0.20,
        )
        self.cc = cc
        self.adj = compute_pair_integration_adjustment(cc, acq)

    def test_low_buyer_capability(self):
        assert self.adj.buyer_integration_capability <= 0.25

    def test_penalty_above_g8_trigger(self):
        assert self.adj.adjusted_integration_penalty >= 0.50

    def test_g8_triggered(self):
        gate_inputs = _gate_inputs(
            adjusted_integration_penalty=self.adj.adjusted_integration_penalty
        )
        result = compute_layer3(0.80, _driver_inputs(), gate_inputs)
        assert "G8" in result.active_gate_ids

    def test_tiered_cap_applied(self):
        """Penalty > 0.70 → cap = 0.50; 0.50–0.70 → cap = 0.60."""
        gate_inputs = _gate_inputs(
            adjusted_integration_penalty=self.adj.adjusted_integration_penalty
        )
        result = compute_layer3(0.80, _driver_inputs(), gate_inputs)
        # At extreme penalty levels with weak acquirer, cap should be 0.50 or 0.60
        assert result.integration_cap_applied in (0.50, 0.60)
        assert result.final_score <= result.integration_cap_applied

    def test_score_capped_below_pre_gate(self):
        gate_inputs = _gate_inputs(
            adjusted_integration_penalty=self.adj.adjusted_integration_penalty
        )
        result = compute_layer3(0.80, _driver_inputs(), gate_inputs)
        assert result.final_score < result.pre_gate_score


# ---------------------------------------------------------------------------
# Scenario 5 — Manufacturing-heavy target → high mfg_transfer component
# ---------------------------------------------------------------------------

class TestScenario5ManufacturingHeavy:
    """Biologic / complex process → manufacturing_transfer_complexity dominates."""

    def test_high_mfg_produces_high_mfg_component(self):
        t = _target(manufacturing_complexity="high")
        cc = compute_target_integration_complexity(t)
        assert cc.component_scores["manufacturing_transfer_complexity"] == pytest.approx(0.85)

    def test_mfg_flag_present(self):
        t = _target(manufacturing_complexity="high")
        cc = compute_target_integration_complexity(t)
        assert "complex_manufacturing_transfer" in cc.complexity_flags

    def test_cdev_obligation_raises_systems_risk(self):
        t_no_cdev = _target(manufacturing_complexity="high")
        t_with_cdev = _target(
            manufacturing_complexity="high",
            has_co_development_obligation=True,
        )
        cc_no = compute_target_integration_complexity(t_no_cdev)
        cc_with = compute_target_integration_complexity(t_with_cdev)
        assert (
            cc_with.component_scores["systems_compliance_transfer_risk"]
            > cc_no.component_scores["systems_compliance_transfer_risk"]
        )

    def test_mfg_dependency_raises_systems_risk(self):
        t_no_dep = _target(manufacturing_complexity="medium")
        t_with_dep = _target(
            manufacturing_complexity="medium",
            has_manufacturing_dependency=True,
        )
        cc_no = compute_target_integration_complexity(t_no_dep)
        cc_with = compute_target_integration_complexity(t_with_dep)
        assert (
            cc_with.component_scores["systems_compliance_transfer_risk"]
            > cc_no.component_scores["systems_compliance_transfer_risk"]
        )

    def test_low_mfg_produces_low_component(self):
        t = _target(manufacturing_complexity="low")
        cc = compute_target_integration_complexity(t)
        assert cc.component_scores["manufacturing_transfer_complexity"] == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Scenario 6 — Missing data → conservative score + data_gaps populated
# ---------------------------------------------------------------------------

class TestScenario6MissingData:
    """Object with minimal attributes → defaults used, data_gaps populated."""

    class _BareTarget:
        """Simulates a target with only the most minimal attribute set."""
        target_id = "T-BARE"
        company_name = "BareCo"
        taxonomy = CompanyTaxonomy.THERAPEUTICS
        enterprise_value_millions = 300.0
        # Missing: product_count, salesforce_required, etc.

    def test_data_gaps_populated_when_attributes_missing(self):
        t = self._BareTarget()
        cc = compute_target_integration_complexity(t)
        # At least product_count gap should be noted
        assert len(cc.data_gaps) >= 1
        assert any("product_count" in g for g in cc.data_gaps)

    def test_score_uses_conservative_defaults(self):
        t = self._BareTarget()
        cc = compute_target_integration_complexity(t)
        # Defaults are conservative (not zero) so score > 0
        assert cc.raw_integration_complexity_score > 0.0

    def test_rationale_is_populated_even_with_missing_data(self):
        t = self._BareTarget()
        cc = compute_target_integration_complexity(t)
        assert len(cc.rationale) >= 1

    def test_component_scores_all_present_even_with_missing_data(self):
        t = self._BareTarget()
        cc = compute_target_integration_complexity(t)
        assert len(cc.component_scores) == 8


# ---------------------------------------------------------------------------
# Scenario 7 — Double-count prevention
# ---------------------------------------------------------------------------

class TestScenario7DoubleCountPrevention:
    """Layer 0E must NOT apply a score penalty. Layer 3 G8 applies the penalty.

    If both were applied, the same complexity burden would be penalised twice —
    once as score_multiplier at Layer 0, again as G8 cap at Layer 3.
    """

    def test_layer0_score_multiplier_excludes_0e_contribution(self):
        """score_multiplier on Layer0Result is encumbrance only (0D), never 0E."""
        t = _target(
            product_count=10,
            manufacturing_complexity="high",
            geographic_complexity="global",
            payer_access_complexity="high",
            salesforce_required=True,
        )
        r = evaluate_layer0(t)
        # score_multiplier must equal encumbrance penalty_multiplier
        assert r.score_multiplier == pytest.approx(r.encumbrance.penalty_multiplier, rel=1e-5)

    def test_layer0_score_multiplier_is_not_reduced_by_complexity(self):
        """A complex target and a simple target with identical encumbrance
        must have identical score_multiplier values.
        """
        t_simple = _target(product_count=1, manufacturing_complexity="low")
        t_complex = _target(
            product_count=10,
            manufacturing_complexity="high",
            geographic_complexity="global",
            salesforce_required=True,
        )
        r_simple = evaluate_layer0(t_simple)
        r_complex = evaluate_layer0(t_complex)
        # Both have default (clean) encumbrance, so score_multiplier should be equal
        assert r_simple.score_multiplier == pytest.approx(r_complex.score_multiplier, abs=0.05)

    def test_no_score_cap_from_0e_at_layer0(self):
        """Layer 0E must not apply score_cap. Caps belong only in Layer 3 G8."""
        t = _target(
            product_count=15,
            manufacturing_complexity="high",
            geographic_complexity="global",
            payer_access_complexity="high",
            salesforce_required=True,
        )
        r = evaluate_layer0(t)
        # No score_cap should be set by 0E alone (distress guard is inactive)
        assert r.score_cap is None

    def test_complexity_flags_in_layer0_notes_are_informational_only(self):
        """complexity_flags appear in layer0_notes but cause no score penalty."""
        t = _target(
            product_count=10,
            manufacturing_complexity="high",
            geographic_complexity="global",
            salesforce_required=True,
        )
        r1 = evaluate_layer0(t)
        t_simple = _target(product_count=1)
        r2 = evaluate_layer0(t_simple)
        # Complex target has more notes but same score_multiplier (encumbrance only)
        assert r1.score_multiplier == pytest.approx(r2.score_multiplier, abs=0.05)


# ---------------------------------------------------------------------------
# Scenario 8 — G8 gate test (adjusted_integration_penalty ≥ 0.50 triggers G8)
# ---------------------------------------------------------------------------

class TestScenario8G8GateTrigger:
    """G8 is triggered by adjusted_integration_penalty >= 0.50 (pair-specific path)."""

    def test_penalty_below_threshold_does_not_trigger_g8(self):
        gate_inputs = _gate_inputs(adjusted_integration_penalty=0.40)
        result = compute_layer3(0.75, _driver_inputs(), gate_inputs)
        assert "G8" not in result.active_gate_ids

    def test_penalty_exactly_at_threshold_triggers_g8(self):
        gate_inputs = _gate_inputs(adjusted_integration_penalty=0.50)
        result = compute_layer3(0.75, _driver_inputs(), gate_inputs)
        assert "G8" in result.active_gate_ids

    def test_penalty_above_threshold_triggers_g8(self):
        gate_inputs = _gate_inputs(adjusted_integration_penalty=0.65)
        result = compute_layer3(0.75, _driver_inputs(), gate_inputs)
        assert "G8" in result.active_gate_ids

    def test_tiered_cap_050_to_070_applies_0_60_cap(self):
        gate_inputs = _gate_inputs(adjusted_integration_penalty=0.60)
        result = compute_layer3(0.80, _driver_inputs(), gate_inputs)
        assert result.integration_cap_applied == pytest.approx(0.60)
        assert result.final_score <= 0.60

    def test_tiered_cap_above_070_applies_0_50_cap(self):
        gate_inputs = _gate_inputs(adjusted_integration_penalty=0.75)
        result = compute_layer3(0.80, _driver_inputs(), gate_inputs)
        assert result.integration_cap_applied == pytest.approx(0.50)
        assert result.final_score <= 0.50

    def test_legacy_integration_complexity_severe_still_triggers_g8(self):
        """Backward-compat: the old boolean flag still fires G8 at default 0.60 cap."""
        gate_inputs = _gate_inputs(
            integration_complexity_severe=True,
            adjusted_integration_penalty=None,  # legacy path
        )
        result = compute_layer3(0.75, _driver_inputs(), gate_inputs)
        assert "G8" in result.active_gate_ids

    def test_legacy_path_uses_default_060_cap(self):
        gate_inputs = _gate_inputs(
            integration_complexity_severe=True,
            adjusted_integration_penalty=None,
        )
        result = compute_layer3(0.80, _driver_inputs(), gate_inputs)
        assert result.integration_cap_applied == pytest.approx(0.60)

    def test_adjusted_penalty_field_propagated_to_output(self):
        penalty = 0.55
        gate_inputs = _gate_inputs(adjusted_integration_penalty=penalty)
        result = compute_layer3(0.80, _driver_inputs(), gate_inputs)
        assert result.adjusted_integration_penalty == pytest.approx(penalty)

    def test_no_penalty_field_is_none_in_output(self):
        gate_inputs = _gate_inputs(adjusted_integration_penalty=None)
        result = compute_layer3(0.80, _driver_inputs(), gate_inputs)
        assert result.adjusted_integration_penalty is None

    def test_affordability_still_triggers_g8_independently(self):
        """G8 affordability path unaffected by integration penalty field."""
        gate_inputs = _gate_inputs(
            adjusted_integration_penalty=None,
            integration_complexity_severe=False,
            affordability=0.30,  # below 0.40 threshold
        )
        result = compute_layer3(0.80, _driver_inputs(), gate_inputs)
        assert "G8" in result.active_gate_ids
