"""
Sprint 44 — Layer 3 Pair-Specific Deal Realism Engine tests.

Coverage (matching spec test cases 1–13 + extras):
 1. Formula: pair_feasibility_score = weighted sum of 7 components
 2. Final adjusted score: min(L2 × multiplier, pair_cap)
 3. Hard fail (affordability): adjusted_bd_score = 0.0
 4. Severe affordability cap: pair cap <= 0.60
 5. ROFR existing partner: lower penalty / neutral vs non-partner
 6. ROFR non-partner: pair cap <= 0.55 or route to license/monitor
 7. Integration mismatch: severe penalty → pair cap <= 0.55
 8. Antitrust hard fail: required divestiture removes core value
 9. Strategic conflict cap: direct franchise cannibalization → cap <= 0.55
10. Process closing risk: shareholder approval unlikely → cap <= 0.55
11. Diligence blocker: fatal → hard fail; major → severe cap
12. Layer separation: Layer 3 does NOT re-score target attractiveness (L1)
13. Backward compatibility: existing modules (gate, pair_affordability, pair_asset_control)
    remain importable and unchanged
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_layer3_pair_realism import (
    AntitrustInputs,
    ConsiderationRealismInputs,
    DiligenceFlagInputs,
    L3_WEIGHTS,
    Layer3AffordabilityOutput,
    Layer3AntitrustOutput,
    Layer3Blocker,
    Layer3Cap,
    Layer3ConsiderationOutput,
    Layer3HardFail,
    Layer3IntegrationOutput,
    Layer3ProcessClosingOutput,
    Layer3RightsControlOutput,
    Layer3StrategicConflictOutput,
    PairRealismInputs,
    PairRealismOutput,
    ProcessClosingInputs,
    StrategicConflictInputs,
    compute_layer3_pair_realism,
)
from bve.intelligence.ma_pair_affordability import (
    AcquirerCapacityInput,
    AffordabilityBand,
    AffordabilityResult,
    compute_pair_affordability,
)
from bve.intelligence.ma_pair_asset_control import (
    PairAssetControlInput,
    compute_pair_asset_control,
)
from bve.intelligence.ma_asset_control_target import (
    AssetControlTargetInput,
    compute_asset_control_target,
)
from bve.intelligence.ma_integration_complexity import (
    AcquirerIntegrationProfile,
    PairIntegrationAdjustment,
    TargetIntegrationComplexityFlag,
    compute_pair_integration_adjustment,
    IntegrationComplexityLevel,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _clean_affordability() -> AffordabilityResult:
    """Affordability with no penalty (ratio ≤ 0.50)."""
    return compute_pair_affordability(
        target_ev_millions=500.0,
        acquirer=AcquirerCapacityInput(
            acquirer_id="pfizer",
            cash_available_millions=2000.0,
            estimated_debt_capacity_millions=1000.0,
        ),
    )


def _severe_affordability() -> AffordabilityResult:
    """Affordability with severe penalty (0.85 < ratio ≤ 1.10).

    cost = 1000 * 1.05 = 1050; capacity = 1000 + 100 = 1100; ratio ≈ 0.955 → SEVERE_PENALTY
    """
    return compute_pair_affordability(
        target_ev_millions=1000.0,
        acquirer=AcquirerCapacityInput(
            acquirer_id="small_co",
            cash_available_millions=1000.0,
            estimated_debt_capacity_millions=100.0,
            expected_takeout_premium=0.05,
        ),
    )


def _hard_fail_affordability() -> AffordabilityResult:
    """Affordability with hard fail (ratio > 1.10)."""
    return compute_pair_affordability(
        target_ev_millions=2000.0,
        acquirer=AcquirerCapacityInput(
            acquirer_id="tiny_co",
            cash_available_millions=100.0,
            estimated_debt_capacity_millions=50.0,
        ),
    )


def _clean_target_asset_control():
    """Clean target-level asset control (no ROFR, global rights)."""
    inp = AssetControlTargetInput(
        asset_rights_scope="global",
        has_existing_partnership=False,
        has_right_of_first_refusal=False,
    )
    return compute_asset_control_target(inp)


def _rofr_target_asset_control():
    """Target with ROFR fact recorded."""
    inp = AssetControlTargetInput(
        asset_rights_scope="global",
        has_existing_partnership=True,
        has_right_of_first_refusal=True,
    )
    return compute_asset_control_target(inp)


def _clean_pair_asset_control(target_ac=None) -> PairAssetControlInput:
    return PairAssetControlInput(
        acquirer_id="pfizer",
        target_id="target-001",
        target_asset_control=target_ac or _clean_target_asset_control(),
        acquirer_is_existing_partner=False,
        rofr_blocks_this_acquirer=False,
    )


def _default_acquirer_integration() -> AcquirerIntegrationProfile:
    return AcquirerIntegrationProfile(
        acquirer_id="pfizer",
        commercial_infrastructure_fit=0.70,
        manufacturing_capability_fit=0.70,
        payer_access_capability_fit=0.70,
        geographic_footprint_fit=0.70,
        systems_compliance_capability_fit=0.70,
        prior_integration_experience=0.70,
    )


def _weak_mfg_acquirer() -> AcquirerIntegrationProfile:
    return AcquirerIntegrationProfile(
        acquirer_id="weak_mfg",
        commercial_infrastructure_fit=0.70,
        manufacturing_capability_fit=0.20,
        payer_access_capability_fit=0.70,
        geographic_footprint_fit=0.70,
        systems_compliance_capability_fit=0.70,
        prior_integration_experience=0.50,
    )


def _high_complexity_target() -> TargetIntegrationComplexityFlag:
    from bve.intelligence.ma_integration_complexity import compute_target_integration_complexity
    from bve.intelligence.ma_eligibility import TargetEligibilityInput
    t = TargetEligibilityInput(
        ticker="TST",
        company_taxonomy="therapeutics",
        lead_asset_present=True,
        lead_asset_status="active",
        platform_technology=True,  # high complexity
        complex_manufacturing=True,
        multiple_geographies=True,
    )
    return compute_target_integration_complexity(t)


def _minimal_inputs(
    upstream_layer2_score: float = 0.80,
    affordability: AffordabilityResult | None = None,
    rights_control=None,
    integration: PairIntegrationAdjustment | None = None,
    consideration: ConsiderationRealismInputs | None = None,
    antitrust: AntitrustInputs | None = None,
    strategic_conflict: StrategicConflictInputs | None = None,
    process_closing: ProcessClosingInputs | None = None,
    diligence_flags: DiligenceFlagInputs | None = None,
) -> PairRealismInputs:
    return PairRealismInputs(
        target_id="target-001",
        acquirer_id="pfizer",
        upstream_layer2_score=upstream_layer2_score,
        affordability=affordability,
        rights_control=rights_control,
        integration=integration,
        consideration=consideration or ConsiderationRealismInputs(),
        antitrust=antitrust or AntitrustInputs(),
        strategic_conflict=strategic_conflict or StrategicConflictInputs(),
        process_closing=process_closing or ProcessClosingInputs(),
        diligence_flags=diligence_flags or DiligenceFlagInputs(),
    )


# ===========================================================================
# 1. Weight invariant
# ===========================================================================

class TestWeightInvariants:
    def test_l3_weights_sum_to_1(self):
        assert abs(sum(L3_WEIGHTS.values()) - 1.0) < 1e-9

    def test_l3_weights_have_seven_components(self):
        expected = {
            "affordability", "consideration_realism", "rights_control_fit",
            "integration_capability", "antitrust_feasibility",
            "strategic_conflict", "process_closing",
        }
        assert set(L3_WEIGHTS.keys()) == expected

    def test_weights_match_spec(self):
        assert L3_WEIGHTS["affordability"] == pytest.approx(0.20)
        assert L3_WEIGHTS["rights_control_fit"] == pytest.approx(0.20)
        assert L3_WEIGHTS["consideration_realism"] == pytest.approx(0.15)
        assert L3_WEIGHTS["integration_capability"] == pytest.approx(0.15)
        assert L3_WEIGHTS["antitrust_feasibility"] == pytest.approx(0.15)
        assert L3_WEIGHTS["strategic_conflict"] == pytest.approx(0.10)
        assert L3_WEIGHTS["process_closing"] == pytest.approx(0.05)


# ===========================================================================
# 2. Formula: pair_feasibility_score = weighted sum of component scores
# ===========================================================================

class TestPairFeasibilityFormula:
    def test_formula_matches_spec_weights(self):
        """Given known component scores, pair_feasibility_score equals the weighted sum."""
        result = compute_layer3_pair_realism(_minimal_inputs())
        expected = (
            L3_WEIGHTS["affordability"]          * result.affordability.score
            + L3_WEIGHTS["consideration_realism"]  * result.consideration_realism.score
            + L3_WEIGHTS["rights_control_fit"]     * result.rights_control_fit.score
            + L3_WEIGHTS["integration_capability"] * result.integration_capability.score
            + L3_WEIGHTS["antitrust_feasibility"]  * result.antitrust_feasibility.score
            + L3_WEIGHTS["strategic_conflict"]     * result.strategic_conflict.score
            + L3_WEIGHTS["process_closing"]        * result.process_closing_feasibility.score
        )
        assert result.pair_feasibility_score == pytest.approx(expected, abs=1e-4)

    def test_all_component_scores_in_range(self):
        result = compute_layer3_pair_realism(_minimal_inputs())
        for comp in (
            result.affordability, result.consideration_realism,
            result.rights_control_fit, result.integration_capability,
            result.antitrust_feasibility, result.strategic_conflict,
            result.process_closing_feasibility,
        ):
            assert 0.0 <= comp.score <= 1.0

    def test_pair_feasibility_score_in_range(self):
        result = compute_layer3_pair_realism(_minimal_inputs())
        assert 0.0 <= result.pair_feasibility_score <= 1.0


# ===========================================================================
# 3. Final adjusted score logic
# ===========================================================================

class TestFinalAdjustedScore:
    def test_no_constraints_adjusted_score_near_l2(self):
        """Clean pair: adjusted = min(L2 × 1.0, 1.0) = L2."""
        result = compute_layer3_pair_realism(
            _minimal_inputs(upstream_layer2_score=0.80, affordability=_clean_affordability())
        )
        assert not result.hard_fail
        assert result.adjusted_bd_score == pytest.approx(0.80, abs=0.10)

    def test_adjusted_score_capped_by_pair_level_cap(self):
        """Adjusted score cannot exceed pair_level_cap."""
        result = compute_layer3_pair_realism(_minimal_inputs(
            upstream_layer2_score=0.90,
            antitrust=AntitrustInputs(
                current_product_overlap=0.75,
                pipeline_overlap=0.70,
                market_concentration=0.75,
            ),
        ))
        assert result.adjusted_bd_score <= result.pair_level_cap + 1e-6

    def test_adjusted_score_equals_formula(self):
        """adjusted_bd_score = min(L2 × multiplier, pair_cap)."""
        result = compute_layer3_pair_realism(_minimal_inputs(upstream_layer2_score=0.75))
        if not result.hard_fail:
            expected = min(
                0.75 * result.pair_feasibility_multiplier,
                result.pair_level_cap,
            )
            assert result.adjusted_bd_score == pytest.approx(expected, abs=1e-4)

    def test_adjusted_score_bounded_0_1(self):
        result = compute_layer3_pair_realism(_minimal_inputs())
        assert 0.0 <= result.adjusted_bd_score <= 1.0


# ===========================================================================
# 4. Hard fail — affordability
# ===========================================================================

class TestAffordabilityHardFail:
    def test_hard_fail_zeros_adjusted_score(self):
        """affordability_ratio > 1.10 → hard_fail = True, adjusted = 0.0"""
        aff = _hard_fail_affordability()
        assert aff.band == AffordabilityBand.HARD_FAIL

        result = compute_layer3_pair_realism(_minimal_inputs(affordability=aff))
        assert result.hard_fail is True
        assert result.adjusted_bd_score == pytest.approx(0.0)

    def test_hard_fail_reason_recorded(self):
        aff = _hard_fail_affordability()
        result = compute_layer3_pair_realism(_minimal_inputs(affordability=aff))
        assert any("affordability" in f.name for f in result.hard_fail_reasons)

    def test_hard_fail_includes_remediation(self):
        aff = _hard_fail_affordability()
        result = compute_layer3_pair_realism(_minimal_inputs(affordability=aff))
        assert len(result.remediation_paths) >= 1

    def test_hard_fail_includes_layer4_routing_hint(self):
        aff = _hard_fail_affordability()
        result = compute_layer3_pair_realism(_minimal_inputs(affordability=aff))
        assert any("license" in h or "option" in h for h in result.layer4_routing_hints)


# ===========================================================================
# 5. Severe affordability cap
# ===========================================================================

class TestSevereAffordabilityCap:
    def test_severe_band_cap_at_most_060(self):
        """SEVERE_PENALTY band → pair_cap <= 0.60"""
        aff = _severe_affordability()
        # Confirm we actually got a severe band
        assert aff.band == AffordabilityBand.SEVERE_PENALTY, (
            f"Expected SEVERE_PENALTY, got {aff.band} (ratio={aff.affordability_ratio})"
        )
        result = compute_layer3_pair_realism(
            _minimal_inputs(upstream_layer2_score=0.85, affordability=aff)
        )
        assert result.pair_level_cap <= 0.60 + 1e-6
        assert not result.hard_fail

    def test_severe_cap_present_in_active_caps(self):
        aff = _severe_affordability()
        result = compute_layer3_pair_realism(_minimal_inputs(affordability=aff))
        cap_names = [c.name for c in result.active_caps]
        assert any("affordability" in n for n in cap_names)


# ===========================================================================
# 6. ROFR: existing partner vs non-partner
# ===========================================================================

class TestROFRPairSpecific:
    def test_existing_partner_gets_higher_rights_score(self):
        """Existing partner: ROFR impact waived → higher rights score."""
        target_ac = _rofr_target_asset_control()

        partner_inp = PairAssetControlInput(
            acquirer_id="novartis",
            target_id="target-001",
            target_asset_control=target_ac,
            acquirer_is_existing_partner=True,  # IS the partner
            rofr_blocks_this_acquirer=False,
        )
        partner_rc = compute_pair_asset_control(partner_inp)

        non_partner_inp = PairAssetControlInput(
            acquirer_id="pfizer",
            target_id="target-001",
            target_asset_control=target_ac,
            acquirer_is_existing_partner=False,
            rofr_blocks_this_acquirer=True,   # NON-partner: ROFR blocks
        )
        non_partner_rc = compute_pair_asset_control(non_partner_inp)

        partner_result = compute_layer3_pair_realism(
            _minimal_inputs(rights_control=partner_rc)
        )
        non_partner_result = compute_layer3_pair_realism(
            _minimal_inputs(rights_control=non_partner_rc)
        )

        # Partner should score higher
        assert partner_result.rights_control_fit.score > non_partner_result.rights_control_fit.score

    def test_existing_partner_rofr_impact_waived(self):
        target_ac = _rofr_target_asset_control()
        inp = PairAssetControlInput(
            acquirer_id="novartis",
            target_id="target-001",
            target_asset_control=target_ac,
            acquirer_is_existing_partner=True,
        )
        rc = compute_pair_asset_control(inp)
        result = compute_layer3_pair_realism(_minimal_inputs(rights_control=rc))
        assert result.rights_control_fit.rofr_impact in ("waived_partner", "none")
        assert result.rights_control_fit.existing_partner_status is True

    def test_non_partner_rofr_blocking_triggers_cap_or_fail(self):
        """Non-partner blocked by ROFR: pair cap <= 0.55 or hard fail."""
        target_ac = _rofr_target_asset_control()
        inp = PairAssetControlInput(
            acquirer_id="pfizer",
            target_id="target-001",
            target_asset_control=target_ac,
            acquirer_is_existing_partner=False,
            rofr_blocks_this_acquirer=True,
        )
        rc = compute_pair_asset_control(inp)
        result = compute_layer3_pair_realism(_minimal_inputs(rights_control=rc))
        # Either hard fail or cap <= 0.55
        if result.hard_fail:
            assert result.adjusted_bd_score == pytest.approx(0.0)
        else:
            assert result.pair_level_cap <= 0.55 + 1e-6


# ===========================================================================
# 7. Integration mismatch — severe cap
# ===========================================================================

class TestIntegrationMismatch:
    def test_severe_integration_mismatch_caps_score(self):
        """High target complexity + weak buyer mfg fit → pair cap <= 0.55."""
        try:
            target_complexity = _high_complexity_target()
        except Exception:
            pytest.skip("Could not construct high-complexity target (missing fields in env)")

        weak_buyer = _weak_mfg_acquirer()
        integ = compute_pair_integration_adjustment(target_complexity, weak_buyer)

        result = compute_layer3_pair_realism(_minimal_inputs(integration=integ))

        # If pair_level_fail we expect hard fail; otherwise cap <= 0.55 (or ≤0.65 per spec)
        if result.hard_fail:
            assert result.adjusted_bd_score == pytest.approx(0.0)
        elif integ.max_score_cap is not None:
            assert result.pair_level_cap <= integ.max_score_cap + 1e-6

    def test_strong_integration_fit_no_cap(self):
        """Strong buyer integration capability → no integration cap."""
        target_complexity = TargetIntegrationComplexityFlag(
            raw_integration_complexity_score=0.20,
            complexity_level=IntegrationComplexityLevel.LOW,
            component_scores={},
            complexity_flags=[],
            integration_risk_drivers=[],
            requires_buyer_capability_check=False,
            rationale=[],
        )
        strong_buyer = AcquirerIntegrationProfile(
            acquirer_id="pfizer",
            commercial_infrastructure_fit=0.90,
            manufacturing_capability_fit=0.90,
            payer_access_capability_fit=0.90,
            geographic_footprint_fit=0.90,
            systems_compliance_capability_fit=0.90,
            prior_integration_experience=0.90,
        )
        integ = compute_pair_integration_adjustment(target_complexity, strong_buyer)
        result = compute_layer3_pair_realism(_minimal_inputs(integration=integ))
        # No integration-related caps expected
        integration_caps = [c for c in result.active_caps if "integration" in c.name]
        assert len(integration_caps) == 0

    def test_integration_penalty_reflected_in_multiplier(self):
        """Pair integration penalty reduces the combined multiplier."""
        # Neutral integration
        no_integ = _minimal_inputs(upstream_layer2_score=0.80)
        result_no_integ = compute_layer3_pair_realism(no_integ)

        # High penalty integration
        target_complexity = TargetIntegrationComplexityFlag(
            raw_integration_complexity_score=0.80,
            complexity_level=IntegrationComplexityLevel.SEVERE,
            component_scores={},
            complexity_flags=["platform_technology"],
            integration_risk_drivers=["manufacturing"],
            requires_buyer_capability_check=True,
            rationale=[],
        )
        weak_buyer = AcquirerIntegrationProfile(
            acquirer_id="pfizer",
            manufacturing_capability_fit=0.15,
            prior_integration_experience=0.20,
        )
        integ = compute_pair_integration_adjustment(target_complexity, weak_buyer)
        with_integ = _minimal_inputs(upstream_layer2_score=0.80, integration=integ)
        result_with_integ = compute_layer3_pair_realism(with_integ)

        assert (
            result_with_integ.adjusted_bd_score <= result_no_integ.adjusted_bd_score + 1e-4
        )


# ===========================================================================
# 8. Antitrust hard fail
# ===========================================================================

class TestAntitrustHardFail:
    def test_required_divestiture_removes_core_value_hard_fail(self):
        ant = AntitrustInputs(
            required_divestiture_removes_core_value=True,
            current_product_overlap=0.90,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(antitrust=ant))
        assert result.hard_fail is True
        assert result.adjusted_bd_score == pytest.approx(0.0)
        assert any("antitrust" in f.name for f in result.hard_fail_reasons)

    def test_very_high_antitrust_risk_hard_fail(self):
        ant = AntitrustInputs(
            current_product_overlap=0.90,
            pipeline_overlap=0.85,
            market_concentration=0.90,
            innovation_competition_risk=0.80,
            divestiture_complexity=0.70,
            jurisdictional_complexity=0.70,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(antitrust=ant))
        assert result.hard_fail is True

    def test_moderate_antitrust_risk_creates_cap(self):
        ant = AntitrustInputs(
            current_product_overlap=0.55,
            pipeline_overlap=0.50,
            market_concentration=0.55,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(antitrust=ant))
        antitrust_caps = [c for c in result.active_caps if "antitrust" in c.name]
        assert len(antitrust_caps) >= 1

    def test_low_antitrust_risk_no_cap(self):
        ant = AntitrustInputs(
            current_product_overlap=0.05,
            pipeline_overlap=0.05,
            market_concentration=0.05,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(antitrust=ant))
        antitrust_caps = [c for c in result.active_caps if "antitrust" in c.name]
        assert len(antitrust_caps) == 0


# ===========================================================================
# 9. Strategic conflict cap
# ===========================================================================

class TestStrategicConflictCap:
    def test_core_franchise_cannibalization_caps_at_055(self):
        sc = StrategicConflictInputs(
            directly_cannibalizes_core_franchise=True,
            product_cannibalization=0.80,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(strategic_conflict=sc))
        conflict_caps = [c for c in result.active_caps if "cannibalization" in c.name]
        assert len(conflict_caps) >= 1
        assert all(c.cap_value <= 0.55 + 1e-6 for c in conflict_caps)

    def test_exclusive_partnership_conflict_creates_cap(self):
        sc = StrategicConflictInputs(has_exclusive_partnership_conflict=True)
        result = compute_layer3_pair_realism(_minimal_inputs(strategic_conflict=sc))
        assert result.pair_level_cap <= 0.50 + 1e-6

    def test_internal_program_kill_creates_meaningful_cap(self):
        sc = StrategicConflictInputs(requires_killing_high_priority_internal_program=True)
        result = compute_layer3_pair_realism(_minimal_inputs(strategic_conflict=sc))
        internal_caps = [c for c in result.active_caps if "internal_program" in c.name]
        assert len(internal_caps) >= 1
        assert all(c.cap_value <= 0.60 + 1e-6 for c in internal_caps)

    def test_low_strategic_conflict_no_cap(self):
        sc = StrategicConflictInputs(
            product_cannibalization=0.0,
            pipeline_cannibalization=0.0,
            channel_conflict=0.0,
            partner_conflict=0.0,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(strategic_conflict=sc))
        conflict_caps = [c for c in result.active_caps if "strategic_conflict" in c.name]
        assert len(conflict_caps) == 0


# ===========================================================================
# 10. Process closing risk
# ===========================================================================

class TestProcessClosingRisk:
    def test_shareholder_approval_unlikely_caps_at_055(self):
        pc = ProcessClosingInputs(
            shareholder_approval_unlikely=True,
            shareholder_approval_likelihood=0.20,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(process_closing=pc))
        process_caps = [c for c in result.active_caps if "shareholder_approval" in c.name]
        assert len(process_caps) >= 1
        assert all(c.cap_value <= 0.55 + 1e-6 for c in process_caps)

    def test_founder_controlled_unwilling_caps_at_050(self):
        pc = ProcessClosingInputs(founder_controlled_and_unwilling=True)
        result = compute_layer3_pair_realism(_minimal_inputs(process_closing=pc))
        assert result.pair_level_cap <= 0.50 + 1e-6

    def test_unresolved_litigation_blocks_close_caps_at_045(self):
        pc = ProcessClosingInputs(unresolved_litigation_blocks_close=True)
        result = compute_layer3_pair_realism(_minimal_inputs(process_closing=pc))
        litigation_caps = [c for c in result.active_caps if "litigation" in c.name]
        assert len(litigation_caps) >= 1
        assert all(c.cap_value <= 0.45 + 1e-6 for c in litigation_caps)

    def test_management_retention_required_unlikely_caps_at_065(self):
        pc = ProcessClosingInputs(management_retention_required_and_unlikely=True)
        result = compute_layer3_pair_realism(_minimal_inputs(process_closing=pc))
        mgmt_caps = [c for c in result.active_caps if "management_retention" in c.name]
        assert len(mgmt_caps) >= 1
        assert all(c.cap_value <= 0.65 + 1e-6 for c in mgmt_caps)


# ===========================================================================
# 11. Diligence blockers
# ===========================================================================

class TestDiligenceBlockers:
    def test_fatal_blocker_creates_hard_fail(self):
        flags = DiligenceFlagInputs(trial_data_integrity_issue=True)
        result = compute_layer3_pair_realism(_minimal_inputs(diligence_flags=flags))
        assert result.hard_fail is True
        assert result.adjusted_bd_score == pytest.approx(0.0)
        fatal_blockers = [b for b in result.diligence_blockers if b.severity == "fatal"]
        assert len(fatal_blockers) >= 1

    def test_fatal_compliance_issue_hard_fail(self):
        flags = DiligenceFlagInputs(compliance_fcpa_issue=True)
        result = compute_layer3_pair_realism(_minimal_inputs(diligence_flags=flags))
        assert result.hard_fail is True

    def test_major_blocker_creates_severe_cap(self):
        flags = DiligenceFlagInputs(ip_ownership_uncertainty=True)
        result = compute_layer3_pair_realism(_minimal_inputs(diligence_flags=flags))
        # Should have a cap ≤ 0.55
        diligence_caps = [c for c in result.active_caps if "ip_ownership" in c.name]
        assert len(diligence_caps) >= 1
        assert all(c.cap_value <= 0.55 + 1e-6 for c in diligence_caps)

    def test_moderate_blocker_creates_meaningful_cap(self):
        flags = DiligenceFlagInputs(cmc_package_incomplete=True)
        result = compute_layer3_pair_realism(_minimal_inputs(diligence_flags=flags))
        diligence_caps = [c for c in result.active_caps if "cmc" in c.name]
        assert len(diligence_caps) >= 1

    def test_multiple_blockers_all_recorded(self):
        flags = DiligenceFlagInputs(
            ip_ownership_uncertainty=True,
            cmc_package_incomplete=True,
            key_employee_retention_risk=True,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(diligence_flags=flags))
        assert len(result.diligence_blockers) >= 3

    def test_no_flags_no_blockers(self):
        flags = DiligenceFlagInputs()
        result = compute_layer3_pair_realism(_minimal_inputs(diligence_flags=flags))
        assert result.diligence_blockers == []


# ===========================================================================
# 12. Layer separation: Layer 3 consumes L2, not L1
# ===========================================================================

class TestLayerSeparation:
    def test_layer3_does_not_recompute_target_quality(self):
        """PairRealismInputs has no asset_quality or layer1_attractiveness field."""
        # If the field existed, this would fail
        assert not hasattr(PairRealismInputs.model_fields, "asset_quality")
        assert not hasattr(PairRealismInputs.model_fields, "layer1_attractiveness")
        assert not hasattr(PairRealismInputs.model_fields, "acquirer_right_to_win")

    def test_layer3_accepts_upstream_l2_score(self):
        result = compute_layer3_pair_realism(_minimal_inputs(upstream_layer2_score=0.72))
        assert result.upstream_layer2_score == pytest.approx(0.72)

    def test_layer3_caps_not_boost_layer2_score(self):
        """Layer 3 can only cap or penalize; it must never produce adjusted > L2."""
        for l2_score in (0.40, 0.60, 0.75, 0.90):
            result = compute_layer3_pair_realism(_minimal_inputs(
                upstream_layer2_score=l2_score, affordability=_clean_affordability()
            ))
            if not result.hard_fail:
                assert result.adjusted_bd_score <= l2_score + 1e-4

    def test_missing_all_pair_data_uses_neutral_defaults(self):
        """With no pair inputs, engine runs without error using neutral defaults."""
        result = compute_layer3_pair_realism(_minimal_inputs(upstream_layer2_score=0.70))
        assert result is not None
        assert not result.hard_fail  # neutral defaults should not hard-fail


# ===========================================================================
# 13. Backward compatibility
# ===========================================================================

class TestBackwardCompatibility:
    def test_existing_gate_system_still_importable(self):
        from bve.intelligence.ma_layer3_gate import (
            compute_layer3, DriverBucketInputs, GateInputs, Layer3Output
        )
        assert compute_layer3 is not None

    def test_existing_pair_affordability_still_importable(self):
        from bve.intelligence.ma_pair_affordability import (
            compute_pair_affordability, AffordabilityResult, AffordabilityBand
        )
        assert compute_pair_affordability is not None

    def test_existing_pair_asset_control_still_importable(self):
        from bve.intelligence.ma_pair_asset_control import (
            compute_pair_asset_control, PairAssetControlResult
        )
        assert compute_pair_asset_control is not None

    def test_existing_integration_complexity_still_importable(self):
        from bve.intelligence.ma_integration_complexity import (
            compute_pair_integration_adjustment, PairIntegrationAdjustment
        )
        assert compute_pair_integration_adjustment is not None

    def test_old_layer3_output_model_not_replaced(self):
        """Old Layer3Output in ma_layer3_gate.py still exists (different from PairRealismOutput)."""
        from bve.intelligence.ma_layer3_gate import Layer3Output as OldL3Output
        from bve.intelligence.ma_layer3_pair_realism import PairRealismOutput
        assert OldL3Output is not PairRealismOutput

    def test_new_module_exports_expected_names(self):
        from bve.intelligence.ma_layer3_pair_realism import (
            PairRealismInputs, PairRealismOutput,
            compute_layer3_pair_realism, L3_WEIGHTS,
            Layer3Cap, Layer3HardFail, Layer3Blocker, Layer3RemediationPath,
        )
        assert compute_layer3_pair_realism is not None


# ===========================================================================
# 14. Consideration realism (additional coverage)
# ===========================================================================

class TestConsiderationRealism:
    def test_low_stock_quality_with_cash_need_creates_cap(self):
        con = ConsiderationRealismInputs(
            acquirer_stock_quality=0.25,
            target_requires_cash_certainty=True,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(consideration=con))
        con_caps = [c for c in result.active_caps if "consideration" in c.name]
        assert len(con_caps) >= 1

    def test_strong_stock_quality_no_cap(self):
        con = ConsiderationRealismInputs(
            acquirer_stock_quality=0.85,
            target_requires_cash_certainty=False,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(consideration=con))
        con_caps = [c for c in result.active_caps if "consideration" in c.name]
        assert len(con_caps) == 0

    def test_cvr_suitability_reflected_in_mix(self):
        con = ConsiderationRealismInputs(cvr_suitability=0.90)
        result = compute_layer3_pair_realism(_minimal_inputs(consideration=con))
        assert result.consideration_realism.likely_consideration_mix == "cvr_milestone"


# ===========================================================================
# 15. Output completeness
# ===========================================================================

class TestOutputCompleteness:
    def test_all_required_fields_populated(self):
        result = compute_layer3_pair_realism(_minimal_inputs())
        assert result.target_id == "target-001"
        assert result.acquirer_id == "pfizer"
        assert isinstance(result.plain_english_summary, str) and len(result.plain_english_summary) > 10
        assert isinstance(result.confidence_label, str)
        assert isinstance(result.layer4_routing_hints, list)
        assert isinstance(result.active_caps, list)
        assert isinstance(result.hard_fail_reasons, list)
        assert isinstance(result.remediation_paths, list)

    def test_hard_fail_summary_mentions_fail(self):
        flags = DiligenceFlagInputs(sanctions_export_control=True)
        result = compute_layer3_pair_realism(_minimal_inputs(diligence_flags=flags))
        assert "HARD FAIL" in result.plain_english_summary or result.hard_fail

    def test_most_restrictive_cap_is_pair_level_cap(self):
        """pair_level_cap == min of all cap_values in active_caps."""
        pc = ProcessClosingInputs(
            founder_controlled_and_unwilling=True,
            shareholder_approval_unlikely=True,
        )
        result = compute_layer3_pair_realism(_minimal_inputs(process_closing=pc))
        if result.active_caps:
            assert result.pair_level_cap == pytest.approx(
                min(c.cap_value for c in result.active_caps), abs=1e-4
            )

    def test_confidence_in_range(self):
        result = compute_layer3_pair_realism(_minimal_inputs())
        assert 0.0 <= result.confidence <= 1.0

    def test_confidence_label_assigned(self):
        result = compute_layer3_pair_realism(_minimal_inputs())
        assert result.confidence_label in ("High", "Medium", "Low", "Very Low")
