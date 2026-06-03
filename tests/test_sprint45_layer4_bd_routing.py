"""Sprint 45 — Layer 4 BD Routing & Execution Playbook tests.

Covers all 20 required test cases:
1.  Hard fail → PAIR_LEVEL_HARD_FAIL, NO_ACTION, BLOCKED
2.  Active pursuit routing
3.  High-priority diligence (high BD score + low info readiness)
4.  Partner / license routing
5.  Option-to-acquire routing
6.  Catalyst watch routing
7.  Strategic watch routing
8.  Relationship build routing
9.  Acquirer mapping needed
10. Remediation required
11. Pass routing (L1 too low + BD action too low)
12. Deal structure → FULL_ACQUISITION
13. Deal structure → REGIONAL_LICENSE
14. Deal structure → CVR_HEAVY_ACQUISITION
15. Outreach: missing rights data → DO_NOT_CONTACT_YET
16. Diligence task generation (rights, antitrust, clinical tasks generated)
17. Monitoring frequency mapping (all 12 RouteClass values)
18. Route confidence prevents ACTIVE_PURSUIT when confidence too low
19. Backward compat: LEGACY_ROUTE_MAP maps old strings to new RouteClass
20. Memo output fields present and non-empty
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_layer4_bd_routing import (
    LEGACY_ROUTE_MAP,
    EscalationLevel,
    Layer4BDInputs,
    Layer4BDOutput,
    MonitoringFrequency,
    NewDealStructure,
    OutreachStatus,
    RouteClass,
    UrgencyLevel,
    WorkflowState,
    _MONITORING_FREQUENCY,
    classify_route,
    determine_outreach_status,
    generate_diligence_tasks,
    route_layer4_opportunity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hard_fail_inputs(**kwargs) -> Layer4BDInputs:
    return Layer4BDInputs(
        target_id="tgt-hf",
        acquirer_id="acq-hf",
        hard_fail=True,
        hard_fail_reasons=["antitrust_hard_block"],
        layer1_score=0.72,
        bd_action_score=0.78,
        layer3_pair_feasibility_score=0.00,
        pair_level_cap=0.00,
        **kwargs,
    )


def _active_pursuit_inputs(**kwargs) -> Layer4BDInputs:
    return Layer4BDInputs(
        target_id="tgt-ap",
        acquirer_id="acq-ap",
        layer1_score=0.80,
        bd_action_score=0.82,
        layer3_pair_feasibility_score=0.75,
        information_readiness=0.70,
        layer1_confidence=0.80,
        layer2_confidence=0.80,
        layer3_confidence=0.80,
        **kwargs,
    )


def _pass_inputs(**kwargs) -> Layer4BDInputs:
    return Layer4BDInputs(
        target_id="tgt-pass",
        acquirer_id="acq-pass",
        layer1_score=0.35,
        bd_action_score=0.30,
        **kwargs,
    )


def _minimal(target_id: str = "tgt-x", **kwargs) -> Layer4BDInputs:
    return Layer4BDInputs(target_id=target_id, **kwargs)


# ---------------------------------------------------------------------------
# Test 1 — Hard fail produces PAIR_LEVEL_HARD_FAIL, NO_ACTION, BLOCKED
# ---------------------------------------------------------------------------

class TestHardFail:
    def test_route_is_pair_level_hard_fail(self):
        out: Layer4BDOutput = route_layer4_opportunity(_hard_fail_inputs())
        assert out.route_class == RouteClass.PAIR_LEVEL_HARD_FAIL

    def test_deal_structure_is_no_action(self):
        out = route_layer4_opportunity(_hard_fail_inputs())
        assert out.recommended_deal_structure == NewDealStructure.NO_ACTION

    def test_outreach_status_is_blocked(self):
        out = route_layer4_opportunity(_hard_fail_inputs())
        assert out.outreach_status == OutreachStatus.BLOCKED

    def test_hard_fail_reasons_propagated(self):
        out = route_layer4_opportunity(_hard_fail_inputs())
        assert "antitrust_hard_block" in out.hard_fail_reasons

    def test_workflow_state_is_blocked(self):
        out = route_layer4_opportunity(_hard_fail_inputs())
        assert out.owner_workflow_state == WorkflowState.BLOCKED

    def test_monitoring_frequency_is_none(self):
        out = route_layer4_opportunity(_hard_fail_inputs())
        assert out.monitoring_frequency == MonitoringFrequency.NONE

    def test_urgency_is_dormant(self):
        out = route_layer4_opportunity(_hard_fail_inputs())
        assert out.urgency_level == UrgencyLevel.DORMANT_OR_PASS

    def test_escalation_is_no_escalation(self):
        out = route_layer4_opportunity(_hard_fail_inputs())
        assert out.escalation_level == EscalationLevel.NO_ESCALATION


# ---------------------------------------------------------------------------
# Test 2 — Active pursuit routing
# ---------------------------------------------------------------------------

class TestActivePursuit:
    def test_route_is_active_pursuit(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert out.route_class == RouteClass.ACTIVE_PURSUIT

    def test_outreach_ready(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert out.outreach_status == OutreachStatus.OUTREACH_READY

    def test_workflow_ready_for_bd_review(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert out.owner_workflow_state == WorkflowState.READY_FOR_BD_REVIEW

    def test_monitoring_weekly(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert out.monitoring_frequency == MonitoringFrequency.WEEKLY


# ---------------------------------------------------------------------------
# Test 3 — High-priority diligence (high BD, low info readiness)
# ---------------------------------------------------------------------------

class TestHighPriorityDiligence:
    def _inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-hpd",
            acquirer_id="acq-hpd",
            layer1_score=0.75,
            bd_action_score=0.78,
            information_readiness=0.40,   # below hpd_info_readiness_max=0.60
            layer1_confidence=0.75,
            layer2_confidence=0.75,
            layer3_confidence=0.75,
        )

    def test_route_is_high_priority_diligence(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.route_class == RouteClass.HIGH_PRIORITY_DILIGENCE

    def test_outreach_do_not_contact_yet(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.outreach_status == OutreachStatus.DO_NOT_CONTACT_YET

    def test_workflow_state_diligence_needed(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.owner_workflow_state == WorkflowState.DILIGENCE_NEEDED


# ---------------------------------------------------------------------------
# Test 4 — Partner / license routing
# ---------------------------------------------------------------------------

class TestPartnerLicense:
    def _inputs(self) -> Layer4BDInputs:
        # Good asset quality but weak pair feasibility
        return Layer4BDInputs(
            target_id="tgt-pl",
            acquirer_id="acq-pl",
            layer1_score=0.70,
            bd_action_score=0.65,       # not high enough for active pursuit
            asset_quality=0.68,         # >= pl_asset_quality_min=0.65
            layer3_pair_feasibility_score=0.50,  # < pl_pair_feasibility_max=0.65
            information_readiness=0.62,
            layer1_confidence=0.70,
            layer2_confidence=0.70,
            layer3_confidence=0.70,
        )

    def test_route_is_partner_or_license(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.route_class == RouteClass.PARTNER_OR_LICENSE_CANDIDATE

    def test_outreach_soft_touch(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.outreach_status == OutreachStatus.SOFT_TOUCH_ONLY


# ---------------------------------------------------------------------------
# Test 5 — Option-to-acquire routing
# ---------------------------------------------------------------------------

class TestOptionToAcquire:
    def _inputs(self) -> Layer4BDInputs:
        # asset_quality=0.62 is BELOW pl_asset_quality_min=0.65, so partner/license
        # rule (priority 7) does not fire, allowing OTA (priority 8) to match.
        return Layer4BDInputs(
            target_id="tgt-ota",
            acquirer_id="acq-ota",
            layer1_score=0.65,
            asset_quality=0.62,           # >= ota_asset_quality_min=0.60, < pl_asset_quality_min=0.65
            catalyst_proximity=0.75,      # >= ota_catalyst_min=0.60
            clinical_uncertainty_high=True,
            layer3_pair_feasibility_score=0.60,  # >= ota_pair_feasibility_min=0.55
            information_readiness=0.62,
            layer1_confidence=0.65,
            layer2_confidence=0.65,
            layer3_confidence=0.65,
        )

    def test_route_is_option_to_acquire(self):
        # Need bd_action_score to not trigger pass or active pursuit first
        inp = self._inputs().model_copy(update={"bd_action_score": 0.62})
        out = route_layer4_opportunity(inp)
        assert out.route_class == RouteClass.OPTION_TO_ACQUIRE_CANDIDATE

    def test_outreach_soft_touch(self):
        inp = self._inputs().model_copy(update={"bd_action_score": 0.62})
        out = route_layer4_opportunity(inp)
        assert out.outreach_status == OutreachStatus.SOFT_TOUCH_ONLY


# ---------------------------------------------------------------------------
# Test 6 — Catalyst watch routing
# ---------------------------------------------------------------------------

class TestCatalystWatch:
    def _inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-cw",
            acquirer_id="acq-cw",
            layer1_score=0.65,
            strategic_priority=0.68,     # >= cw_strategic_priority_min=0.55
            catalyst_proximity=0.72,     # >= cw_catalyst_min=0.65
            bd_action_score=0.55,        # < cw_bd_action_max=0.75 → below active pursuit
            information_readiness=0.50,
            layer1_confidence=0.65,
            layer2_confidence=0.65,
            layer3_confidence=0.65,
        )

    def test_route_is_catalyst_watch(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.route_class == RouteClass.CATALYST_WATCH

    def test_outreach_monitor_only(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.outreach_status == OutreachStatus.MONITOR_ONLY


# ---------------------------------------------------------------------------
# Test 7 — Strategic watch routing
# ---------------------------------------------------------------------------

class TestStrategicWatch:
    def _inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-sw",
            acquirer_id="acq-sw",
            layer1_score=0.68,
            strategic_priority=0.75,     # >= sw_strategic_priority_min=0.70
            deal_momentum=0.30,          # < sw_deal_momentum_max=0.45
            catalyst_proximity=0.30,     # not enough for catalyst watch (< cw_catalyst_min)
            layer1_confidence=0.65,
            layer2_confidence=0.65,
            layer3_confidence=0.65,
        )

    def test_route_is_strategic_watch(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.route_class == RouteClass.STRATEGIC_WATCH

    def test_outreach_soft_touch_or_monitor(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.outreach_status in (
            OutreachStatus.SOFT_TOUCH_ONLY,
            OutreachStatus.MONITOR_ONLY,
        )


# ---------------------------------------------------------------------------
# Test 8 — Relationship build routing
# ---------------------------------------------------------------------------

class TestRelationshipBuild:
    def _inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-rb",
            acquirer_id="acq-rb",
            layer1_score=0.67,
            strategic_priority=0.68,     # >= rb_strategic_priority_min=0.65
            acquirer_pull=0.65,          # >= rb_acquirer_pull_min=0.60
            deal_momentum=0.35,          # < rb_deal_momentum_max=0.50
            existing_relationship_strength=0.25,  # < rb_relationship_max=0.40
            catalyst_proximity=0.20,     # not enough for catalyst watch
            layer1_confidence=0.65,
            layer2_confidence=0.65,
            layer3_confidence=0.65,
        )

    def test_route_is_relationship_build(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.route_class == RouteClass.RELATIONSHIP_BUILD

    def test_outreach_soft_touch(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.outreach_status == OutreachStatus.SOFT_TOUCH_ONLY


# ---------------------------------------------------------------------------
# Test 9 — Acquirer mapping needed
# ---------------------------------------------------------------------------

class TestAcquirerMappingNeeded:
    def _inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-amn",
            acquirer_id="acq-amn",
            layer1_score=0.72,           # >= amn_layer1_min=0.65
            bd_action_score=0.68,        # not high enough for active pursuit
            acquirer_pull_confidence=0.35,  # < amn_pull_confidence_max=0.50
            information_readiness=0.55,
            layer1_confidence=0.72,
            layer2_confidence=0.65,
            layer3_confidence=0.65,
        )

    def test_route_is_acquirer_mapping_needed(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.route_class == RouteClass.ACQUIRER_MAPPING_NEEDED

    def test_outreach_do_not_contact_yet(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.outreach_status == OutreachStatus.DO_NOT_CONTACT_YET


# ---------------------------------------------------------------------------
# Test 10 — Remediation required
# ---------------------------------------------------------------------------

class TestRemediationRequired:
    def _inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-rr",
            acquirer_id="acq-rr",
            layer1_score=0.68,
            bd_action_score=0.60,        # below active pursuit
            layer3_has_severe_cap=True,
            pair_level_cap=0.55,         # <= rr_severe_cap_max=0.70
            layer3_remediation_paths=["Negotiate ROFR waiver with existing partner"],
            layer1_confidence=0.65,
            layer2_confidence=0.65,
            layer3_confidence=0.65,
        )

    def test_route_is_remediation_required(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.route_class == RouteClass.REMEDIATION_REQUIRED

    def test_remediation_plan_is_populated(self):
        out = route_layer4_opportunity(self._inputs())
        assert len(out.remediation_plan) >= 1

    def test_workflow_state_is_blocked(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.owner_workflow_state == WorkflowState.BLOCKED


# ---------------------------------------------------------------------------
# Test 11 — Pass routing (L1 too low + BD action too low)
# ---------------------------------------------------------------------------

class TestPassRouting:
    def test_pass_low_layer1(self):
        out = route_layer4_opportunity(_pass_inputs())
        assert out.route_class == RouteClass.PASS_DO_NOT_PURSUE

    def test_pass_low_bd_action(self):
        inp = Layer4BDInputs(
            target_id="tgt-pass-bd",
            layer1_score=0.60,           # above pass_layer1_max=0.45
            bd_action_score=0.35,        # below pass_bd_action_max=0.40
        )
        out = route_layer4_opportunity(inp)
        assert out.route_class == RouteClass.PASS_DO_NOT_PURSUE

    def test_pass_layer0_exclusion(self):
        inp = Layer4BDInputs(
            target_id="tgt-excl",
            target_passed_layer0=False,
            hard_exclusions=["fda_refuse_to_file"],
        )
        out = route_layer4_opportunity(inp)
        assert out.route_class == RouteClass.PASS_DO_NOT_PURSUE

    def test_pass_workflow_state(self):
        out = route_layer4_opportunity(_pass_inputs())
        assert out.owner_workflow_state == WorkflowState.PASSED

    def test_pass_monitoring_annual(self):
        out = route_layer4_opportunity(_pass_inputs())
        assert out.monitoring_frequency == MonitoringFrequency.ANNUAL_REFRESH


# ---------------------------------------------------------------------------
# Test 12 — Deal structure: FULL_ACQUISITION
# ---------------------------------------------------------------------------

class TestDealStructureFullAcquisition:
    def _inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-fa",
            acquirer_id="acq-fa",
            layer1_score=0.82,
            bd_action_score=0.84,
            layer3_pair_feasibility_score=0.80,  # >= full_acq_feasibility_min=0.70
            rights_control_fit=0.78,             # >= full_acq_rights_min=0.70
            affordability_realism=0.75,          # >= full_acq_afford_min=0.70
            integration_capability=0.72,         # >= full_acq_integ_min=0.60
            antitrust_feasibility=0.72,          # >= full_acq_anti_min=0.65
            information_readiness=0.75,
            layer1_confidence=0.82,
            layer2_confidence=0.82,
            layer3_confidence=0.82,
        )

    def test_structure_is_full_acquisition(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.recommended_deal_structure == NewDealStructure.FULL_ACQUISITION

    def test_secondary_structure_present(self):
        out = route_layer4_opportunity(self._inputs())
        assert NewDealStructure.STRUCTURED_ACQUISITION_WITH_MILESTONES in out.secondary_deal_structures


# ---------------------------------------------------------------------------
# Test 13 — Deal structure: REGIONAL_LICENSE
# ---------------------------------------------------------------------------

class TestDealStructureRegionalLicense:
    def _inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-rl",
            acquirer_id="acq-rl",
            layer1_score=0.68,
            bd_action_score=0.65,
            asset_quality=0.66,
            layer3_pair_feasibility_score=0.55,
            global_rights_available=False,
            regional_rights_available=True,
            information_readiness=0.58,
            layer1_confidence=0.68,
            layer2_confidence=0.68,
            layer3_confidence=0.68,
        )

    def test_structure_is_regional_license(self):
        _, _, _, structure, _, _, _ = (
            *self._call(),
        )
        assert structure == NewDealStructure.REGIONAL_LICENSE

    def _call(self):
        out = route_layer4_opportunity(self._inputs())
        return (
            out.route_class,
            out.outreach_status,
            out.urgency_level,
            out.recommended_deal_structure,
            out.secondary_deal_structures,
            out.escalation_level,
            out.route_reason,
        )

    def test_regional_license_via_full_output(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.recommended_deal_structure == NewDealStructure.REGIONAL_LICENSE

    def test_co_development_in_secondaries(self):
        out = route_layer4_opportunity(self._inputs())
        assert NewDealStructure.CO_DEVELOPMENT in out.secondary_deal_structures


# ---------------------------------------------------------------------------
# Test 14 — Deal structure: CVR_HEAVY_ACQUISITION
# ---------------------------------------------------------------------------

class TestDealStructureCVRHeavy:
    def _inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-cvr",
            acquirer_id="acq-cvr",
            layer1_score=0.72,
            bd_action_score=0.74,
            layer3_pair_feasibility_score=0.62,  # >= 0.55 for CVR
            valuation_gap_high=True,
            binary_catalyst_risk_high=True,
            affordability_realism=0.58,          # >= 0.50 for CVR
            information_readiness=0.65,
            layer1_confidence=0.70,
            layer2_confidence=0.70,
            layer3_confidence=0.70,
        )

    def test_structure_is_cvr_heavy(self):
        out = route_layer4_opportunity(self._inputs())
        assert out.recommended_deal_structure == NewDealStructure.CVR_HEAVY_ACQUISITION

    def test_option_to_acquire_in_secondaries(self):
        out = route_layer4_opportunity(self._inputs())
        assert NewDealStructure.OPTION_TO_ACQUIRE in out.secondary_deal_structures


# ---------------------------------------------------------------------------
# Test 15 — Outreach: missing rights data → DO_NOT_CONTACT_YET
# ---------------------------------------------------------------------------

class TestOutreachMissingRights:
    def test_missing_rights_data_blocks_outreach(self):
        inp = Layer4BDInputs(
            target_id="tgt-norc",
            acquirer_id="acq-norc",
            layer1_score=0.78,
            bd_action_score=0.80,
            layer3_pair_feasibility_score=0.72,
            information_readiness=0.68,
            rights_control_data_missing=True,   # ← missing rights flag
            layer1_confidence=0.78,
            layer2_confidence=0.78,
            layer3_confidence=0.78,
        )
        status, reason = determine_outreach_status(
            inp, classify_route(inp)[0]
        )
        assert status == OutreachStatus.DO_NOT_CONTACT_YET
        assert "rights" in reason.lower() or "control" in reason.lower()

    def test_low_rights_fit_blocks_outreach(self):
        inp = Layer4BDInputs(
            target_id="tgt-lowrc",
            acquirer_id="acq-lowrc",
            layer1_score=0.78,
            bd_action_score=0.80,
            layer3_pair_feasibility_score=0.72,
            information_readiness=0.68,
            rights_control_fit=0.30,   # < 0.40 triggers DO_NOT_CONTACT_YET
            layer1_confidence=0.78,
            layer2_confidence=0.78,
            layer3_confidence=0.78,
        )
        status, _ = determine_outreach_status(inp, classify_route(inp)[0])
        assert status == OutreachStatus.DO_NOT_CONTACT_YET


# ---------------------------------------------------------------------------
# Test 16 — Diligence task generation
# ---------------------------------------------------------------------------

class TestDiligenceTaskGeneration:
    def _low_rights_inputs(self) -> Layer4BDInputs:
        return Layer4BDInputs(
            target_id="tgt-dil",
            rights_control_fit=0.40,      # < 0.65 → Rights task
            antitrust_feasibility=0.35,   # < 0.65 → Antitrust task (Critical)
            asset_quality=0.50,           # < 0.65 → Clinical task
        )

    def test_rights_task_generated(self):
        tasks = generate_diligence_tasks(self._low_rights_inputs())
        categories = [t.category for t in tasks]
        assert any("Rights" in c or "rights" in c for c in categories)

    def test_antitrust_task_generated(self):
        tasks = generate_diligence_tasks(self._low_rights_inputs())
        categories = [t.category for t in tasks]
        assert any("Antitrust" in c or "antitrust" in c for c in categories)

    def test_clinical_task_generated(self):
        tasks = generate_diligence_tasks(self._low_rights_inputs())
        categories = [t.category for t in tasks]
        assert any("Clinical" in c or "clinical" in c for c in categories)

    def test_antitrust_critical_when_very_low(self):
        tasks = generate_diligence_tasks(self._low_rights_inputs())
        antitrust_tasks = [t for t in tasks if "Antitrust" in t.category]
        assert antitrust_tasks[0].priority == "Critical"

    def test_no_duplicate_categories(self):
        tasks = generate_diligence_tasks(self._low_rights_inputs())
        categories = [t.category for t in tasks]
        # Each category should appear at most once
        assert len(categories) == len(set(categories))

    def test_rights_task_has_blocker_severity_high(self):
        tasks = generate_diligence_tasks(self._low_rights_inputs())
        rights_task = next(t for t in tasks if "Rights" in t.category)
        assert rights_task.blocker_severity == "high"


# ---------------------------------------------------------------------------
# Test 17 — Monitoring frequency mapping
# ---------------------------------------------------------------------------

class TestMonitoringFrequencyMapping:
    def test_active_pursuit_weekly(self):
        assert _MONITORING_FREQUENCY[RouteClass.ACTIVE_PURSUIT] == MonitoringFrequency.WEEKLY

    def test_high_priority_diligence_weekly(self):
        assert _MONITORING_FREQUENCY[RouteClass.HIGH_PRIORITY_DILIGENCE] == MonitoringFrequency.WEEKLY

    def test_partner_license_weekly(self):
        assert _MONITORING_FREQUENCY[RouteClass.PARTNER_OR_LICENSE_CANDIDATE] == MonitoringFrequency.WEEKLY

    def test_catalyst_watch_weekly_event(self):
        assert _MONITORING_FREQUENCY[RouteClass.CATALYST_WATCH] == MonitoringFrequency.WEEKLY_OR_EVENT_DRIVEN

    def test_strategic_watch_monthly(self):
        assert _MONITORING_FREQUENCY[RouteClass.STRATEGIC_WATCH] == MonitoringFrequency.MONTHLY

    def test_monitor_only_quarterly(self):
        assert _MONITORING_FREQUENCY[RouteClass.MONITOR_ONLY] == MonitoringFrequency.QUARTERLY

    def test_pass_annual_refresh(self):
        assert _MONITORING_FREQUENCY[RouteClass.PASS_DO_NOT_PURSUE] == MonitoringFrequency.ANNUAL_REFRESH

    def test_pair_level_hard_fail_none(self):
        assert _MONITORING_FREQUENCY[RouteClass.PAIR_LEVEL_HARD_FAIL] == MonitoringFrequency.NONE

    def test_all_route_classes_have_frequency(self):
        for route in RouteClass:
            assert route in _MONITORING_FREQUENCY, f"No frequency for {route}"


# ---------------------------------------------------------------------------
# Test 18 — Route confidence prevents ACTIVE_PURSUIT
# ---------------------------------------------------------------------------

class TestRouteConfidencePreventsActivePursuit:
    def test_low_confidence_downgrades_active_pursuit(self):
        """Active pursuit criteria met but no upstream layer scores → low confidence."""
        inp = Layer4BDInputs(
            target_id="tgt-lowconf",
            acquirer_id="acq-lowconf",
            # Active pursuit routing criteria met:
            bd_action_score=0.82,
            layer3_pair_feasibility_score=0.75,
            information_readiness=0.70,
            # But no layer1/layer2/layer3 confidence signals (all default to _NEUTRAL=0.50)
            # Force minimal confidence by providing no layer scores except bd_action_score:
            layer1_score=None,           # missing → low route confidence
            layer1_confidence=0.10,      # deliberately very low
            layer2_confidence=0.10,
            layer3_confidence=0.10,
            layer3_adjusted_score=None,  # missing → low route confidence
        )
        out = route_layer4_opportunity(inp)
        # With confidence < route_conf_min_for_ap (0.50), should be downgraded
        assert out.route_class == RouteClass.HIGH_PRIORITY_DILIGENCE
        assert any("downgraded" in w.lower() for w in out.warnings)

    def test_high_confidence_keeps_active_pursuit(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert out.route_class == RouteClass.ACTIVE_PURSUIT
        # No downgrade warning should appear
        assert not any("downgraded" in w.lower() for w in out.warnings)


# ---------------------------------------------------------------------------
# Test 19 — Backward compatibility: LEGACY_ROUTE_MAP
# ---------------------------------------------------------------------------

class TestLegacyRouteMap:
    def test_pass_maps_to_pass_do_not_pursue(self):
        assert LEGACY_ROUTE_MAP["pass"] == RouteClass.PASS_DO_NOT_PURSUE

    def test_data_insufficient_maps_to_high_priority_diligence(self):
        assert LEGACY_ROUTE_MAP["data_insufficient"] == RouteClass.HIGH_PRIORITY_DILIGENCE

    def test_strategic_radar_maps_to_strategic_watch(self):
        assert LEGACY_ROUTE_MAP["strategic_radar"] == RouteClass.STRATEGIC_WATCH

    def test_relationship_build_maps_correctly(self):
        assert LEGACY_ROUTE_MAP["relationship_build"] == RouteClass.RELATIONSHIP_BUILD

    def test_catalyst_watch_maps_correctly(self):
        assert LEGACY_ROUTE_MAP["catalyst_watch"] == RouteClass.CATALYST_WATCH

    def test_active_pursuit_maps_correctly(self):
        assert LEGACY_ROUTE_MAP["active_pursuit"] == RouteClass.ACTIVE_PURSUIT

    def test_process_ready_maps_to_active_pursuit(self):
        assert LEGACY_ROUTE_MAP["process_ready"] == RouteClass.ACTIVE_PURSUIT

    def test_hard_fail_maps_to_pair_level_hard_fail(self):
        assert LEGACY_ROUTE_MAP["hard_fail"] == RouteClass.PAIR_LEVEL_HARD_FAIL

    def test_route_to_license_maps_to_partner_or_license(self):
        assert LEGACY_ROUTE_MAP["route_to_license"] == RouteClass.PARTNER_OR_LICENSE_CANDIDATE

    def test_monitor_maps_to_monitor_only(self):
        assert LEGACY_ROUTE_MAP["monitor"] == RouteClass.MONITOR_ONLY

    def test_all_legacy_values_are_route_class(self):
        for key, val in LEGACY_ROUTE_MAP.items():
            assert isinstance(val, RouteClass), f"{key} → {val} is not RouteClass"


# ---------------------------------------------------------------------------
# Test 20 — Memo output fields present and non-empty
# ---------------------------------------------------------------------------

class TestMemoOutput:
    def test_memo_summary_present(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert isinstance(out.memo_summary, str)
        assert len(out.memo_summary) > 30

    def test_plain_english_rationale_present(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert isinstance(out.plain_english_rationale, str)
        assert len(out.plain_english_rationale) > 20

    def test_memo_contains_route_label(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert "Active Pursuit" in out.memo_summary or "active_pursuit" in out.memo_summary.lower()

    def test_memo_contains_target_id(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert "tgt-ap" in out.memo_summary

    def test_rationale_mentions_route_reason(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        # Plain English rationale should contain something about why it was routed
        assert len(out.plain_english_rationale) > 0

    def test_hard_fail_memo_mentions_hard_fail(self):
        out = route_layer4_opportunity(_hard_fail_inputs())
        lower = out.plain_english_rationale.lower()
        assert "hard" in lower or "fail" in lower or "blocker" in lower

    def test_upstream_scores_passthrough(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert out.upstream_scores.layer2_score == pytest.approx(0.82)
        assert out.upstream_scores.layer1_score == pytest.approx(0.80)

    def test_route_reason_non_empty(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert len(out.route_reason) > 0

    def test_next_best_action_non_empty(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert len(out.next_best_action) > 0

    def test_upgrade_triggers_present(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert len(out.upgrade_triggers) >= 1

    def test_downgrade_triggers_present(self):
        out = route_layer4_opportunity(_active_pursuit_inputs())
        assert len(out.downgrade_triggers) >= 1
