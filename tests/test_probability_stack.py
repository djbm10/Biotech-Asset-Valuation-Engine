from __future__ import annotations

from bve.intelligence.science_engine import ScienceAssessment, ScienceSubscore
from bve.models.approval_scenarios import ApprovalScenario
from bve.models.label_breadth_model import LabelBreadthInputs, infer_label_breadth
from bve.models.probability_stack import ProbabilityStackInputs, build_probability_stack
from bve.models.regulatory_inference import (
    ApprovalPathway,
    RegulatoryInferenceResult,
    RegulatoryProfile,
    RegulatoryScenario,
    RegulatoryScenarioProbability,
)
from bve.models.timeline_distribution_model import TimelineDistributionInputs, infer_timeline_distribution


def _science_assessment() -> ScienceAssessment:
    subscores = [
        ScienceSubscore(name="mechanism_plausibility", value=0.78, confidence=0.8, rationale="Mechanism defined."),
        ScienceSubscore(name="target_validation", value=0.75, confidence=0.75, rationale="Target linked to thesis."),
        ScienceSubscore(name="modality_specific_risk", value=0.72, confidence=0.8, rationale="Familiar modality."),
        ScienceSubscore(name="biomarker_logic_quality", value=0.74, confidence=0.76, rationale="Selected population."),
        ScienceSubscore(name="translational_evidence_quality", value=0.68, confidence=0.7, rationale="Clinical bridge exists."),
        ScienceSubscore(name="analog_winners_failures_similarity", value=0.7, confidence=0.72, rationale="Good analog support."),
        ScienceSubscore(name="safety_signal_seriousness", value=0.78, confidence=0.75, rationale="Manageable safety."),
        ScienceSubscore(name="trial_design_quality", value=0.72, confidence=0.72, rationale="Reasonable design."),
    ]
    return ScienceAssessment(
        asset_id="asset-rly2608",
        asset_name="RLY-2608",
        science_score=0.74,
        design_score=0.72,
        confidence_band="high",
        subscores=subscores,
        top_positives=["Mechanism and target are explicit."],
        top_risks=["Commercial and regulatory uncertainty remain."],
        nearest_analogs=[],
        kill_criteria=["Safety burden must remain manageable."],
        plain_english_summary="Science package is attractive.",
    )


def _regulatory_inference() -> RegulatoryInferenceResult:
    profile = RegulatoryProfile(
        approval_pathway=ApprovalPathway.PRIORITY,
        endpoint_type="surrogate_validated",
        safety_serious_events=False,
        adcom_precedent="positive",
    )
    scenarios = [
        RegulatoryScenarioProbability(
            scenario=RegulatoryScenario.CLEAN_APPROVAL,
            probability=0.62,
            pdufa_months=6,
            rationale="Clean path.",
        ),
        RegulatoryScenarioProbability(
            scenario=RegulatoryScenario.NARROW_LABEL,
            probability=0.16,
            pdufa_months=7,
            rationale="Some label risk.",
        ),
        RegulatoryScenarioProbability(
            scenario=RegulatoryScenario.HIGH_POSTMARKET_BURDEN,
            probability=0.10,
            pdufa_months=8,
            rationale="Burden possible.",
        ),
        RegulatoryScenarioProbability(
            scenario=RegulatoryScenario.DELAYED_APPROVAL,
            probability=0.07,
            pdufa_months=12,
            rationale="Delay risk.",
        ),
        RegulatoryScenarioProbability(
            scenario=RegulatoryScenario.CRL,
            probability=0.05,
            pdufa_months=6,
            rationale="CRL risk.",
        ),
    ]
    return RegulatoryInferenceResult(
        profile=profile,
        scenarios=scenarios,
        dominant_scenario=RegulatoryScenario.CLEAN_APPROVAL,
        approval_probability=0.88,
        expected_pdufa_months=6.8,
        risk_flags=[],
        pos_modifier=0.04,
    )


def test_phase_e_label_breadth_model_returns_bounded_outputs() -> None:
    result = infer_label_breadth(
        LabelBreadthInputs(
            design_score=0.72,
            biomarker_logic_score=0.74,
            safety_score=0.78,
            regulatory_approval_probability=0.88,
            endpoint_strength_score=0.82,
        )
    )
    assert 0.0 <= result.broad_label_probability <= 1.0
    assert 0.0 <= result.narrow_label_probability <= 1.0


def test_phase_e_timeline_distribution_model_returns_delay_profile() -> None:
    result = infer_timeline_distribution(
        TimelineDistributionInputs(
            years_to_approval=3.5,
            regulatory_risk_score=0.88,
            design_score=0.72,
            financing_risk_score=0.25,
        )
    )
    assert result.delayed_years >= result.on_time_years
    assert 0.0 <= result.delay_probability <= 1.0


def test_phase_e_probability_stack_builds_four_layers_and_scenarios() -> None:
    result = build_probability_stack(
        ProbabilityStackInputs(
            asset_id="asset-rly2608",
            asset_name="RLY-2608",
            base_pos=0.49,
            science_assessment=_science_assessment(),
            regulatory_inference=_regulatory_inference(),
            years_to_approval=3.5,
            financing_risk_score=0.25,
            market_access_pressure_score=0.35,
            management_execution_score=0.7,
            competitor_readthrough_score=0.55,
        )
    )
    assert result.technical_success_probability.probability > 0.0
    assert result.regulatory_approval_probability.probability > 0.0
    assert result.label_breadth_probability.probability > 0.0
    assert result.commercial_realization_probability.probability > 0.0
    assert len(result.approval_scenarios) == 5
    assert abs(sum(item.probability for item in result.approval_scenarios) - 1.0) <= 0.001
    assert any(item.scenario == ApprovalScenario.FULL_APPROVAL for item in result.approval_scenarios)
    assert "composite approval probability" in result.plain_english_summary


# ---------------------------------------------------------------------------
# Step 7 tests: ProbabilityStack, LabelBreadthEstimate, TimelineDistributionV2
# ---------------------------------------------------------------------------

import pytest

from bve.models.financing_risk import DistressTier, FinancingRiskV2
from bve.models.label_breadth_model import LabelScope, LabelBreadthEstimate, estimate_label_breadth
from bve.models.probability_stack import (
    ApprovalScenarioV2,
    ProbabilityStack,
    compute_probability_stack,
)
from bve.models.science_score import ScienceDiligenceResult, ScienceSubScore
from bve.models.timeline_distribution_model import (
    TimelineDistributionV2,
    TimelineRisk,
    compute_timeline_distribution,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_science_result(overall_score: float = 0.75) -> ScienceDiligenceResult:
    sub = ScienceSubScore(
        name="endpoint_validity",
        score=overall_score,
        confidence=0.80,
        top_positives=["Good endpoint"],
        top_risks=[],
        rationale="Test sub-score.",
    )
    return ScienceDiligenceResult(
        asset_id="test-asset",
        overall_score=overall_score,
        confidence=0.80,
        sub_scores={"endpoint_validity": sub},
        top_positives=["Good endpoint"],
        top_risks=[],
        rationale="Test science result.",
        endpoint_validity=None,
        trial_design=None,
        analog_result=None,
        safety=None,
    )


def _make_financing_risk(distress_tier: DistressTier) -> FinancingRiskV2:
    return FinancingRiskV2(
        asset_id="test-asset",
        as_of_date="2026-01-01",
        distress_tier=distress_tier,
        partnership_flag=distress_tier in (DistressTier.CRITICAL, DistressTier.HIGH),
        financing_adjusted_value_haircut=1.0,
        rationale="Test financing risk.",
        assumptions={},
    )


# ---------------------------------------------------------------------------
# TestProbabilityStack
# ---------------------------------------------------------------------------


class TestProbabilityStack:
    def test_runs_for_phase1(self) -> None:
        result = compute_probability_stack("asset-1", "phase1")
        assert isinstance(result, ProbabilityStack)

    def test_runs_for_phase2(self) -> None:
        result = compute_probability_stack("asset-1", "phase2")
        assert isinstance(result, ProbabilityStack)

    def test_runs_for_phase3(self) -> None:
        result = compute_probability_stack("asset-1", "phase3")
        assert isinstance(result, ProbabilityStack)

    def test_runs_for_nda_bla(self) -> None:
        result = compute_probability_stack("asset-1", "nda_bla")
        assert isinstance(result, ProbabilityStack)

    def test_runs_for_approved(self) -> None:
        result = compute_probability_stack("asset-1", "approved")
        assert isinstance(result, ProbabilityStack)

    def test_runs_for_unknown_phase_defaults_to_phase2(self) -> None:
        result = compute_probability_stack("asset-1", "unknown_phase")
        from bve.models.probability_stack import PHASE_BASE_RATES
        assert result.technical_success_prob.probability == pytest.approx(
            PHASE_BASE_RATES["phase2"]["technical"] * 1.0, abs=0.05
        )

    def test_composite_pos_equals_technical_times_regulatory(self) -> None:
        result = compute_probability_stack("asset-1", "phase2")
        expected = result.technical_success_prob.probability * result.regulatory_approval_prob.probability
        assert result.composite_pos == pytest.approx(expected, rel=1e-6)

    def test_scenario_probs_sum_to_one(self) -> None:
        result = compute_probability_stack("asset-1", "phase2")
        total = sum(result.scenario_probs.values())
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_scenario_probs_sum_to_one_with_breakthrough(self) -> None:
        result = compute_probability_stack("asset-1", "phase3", has_breakthrough_designation=True)
        total = sum(result.scenario_probs.values())
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_all_scenario_keys_present(self) -> None:
        result = compute_probability_stack("asset-1", "phase2")
        expected_keys = {s.value for s in ApprovalScenarioV2}
        assert set(result.scenario_probs.keys()) == expected_keys

    def test_breakthrough_designation_increases_composite_pos(self) -> None:
        baseline = compute_probability_stack("asset-1", "phase2")
        with_bt = compute_probability_stack("asset-1", "phase2", has_breakthrough_designation=True)
        assert with_bt.composite_pos > baseline.composite_pos

    def test_fast_track_reduces_delay_prob(self) -> None:
        baseline = compute_probability_stack("asset-1", "phase2")
        with_ft = compute_probability_stack("asset-1", "phase2", has_fast_track=True)
        assert with_ft.delay_prob < baseline.delay_prob

    def test_orphan_designation_increases_label_breadth(self) -> None:
        baseline = compute_probability_stack("asset-1", "phase2")
        with_orphan = compute_probability_stack("asset-1", "phase2", has_orphan_designation=True)
        assert with_orphan.label_breadth_prob.probability > baseline.label_breadth_prob.probability

    def test_financing_critical_reduces_commercial_realization(self) -> None:
        baseline = compute_probability_stack("asset-1", "phase2")
        critical = _make_financing_risk(DistressTier.CRITICAL)
        with_critical = compute_probability_stack("asset-1", "phase2", financing_risk=critical)
        assert with_critical.commercial_realization_prob.probability < baseline.commercial_realization_prob.probability

    def test_financing_none_does_not_change_commercial(self) -> None:
        baseline = compute_probability_stack("asset-1", "phase2")
        none_risk = _make_financing_risk(DistressTier.NONE)
        with_none = compute_probability_stack("asset-1", "phase2", financing_risk=none_risk)
        assert with_none.commercial_realization_prob.probability == pytest.approx(
            baseline.commercial_realization_prob.probability, rel=1e-6
        )

    def test_high_science_score_increases_technical_prob(self) -> None:
        baseline = compute_probability_stack("asset-1", "phase2")
        high_science = _make_science_result(overall_score=0.95)
        with_science = compute_probability_stack("asset-1", "phase2", science_result=high_science)
        assert with_science.technical_success_prob.probability > baseline.technical_success_prob.probability

    def test_low_science_score_decreases_technical_prob(self) -> None:
        baseline = compute_probability_stack("asset-1", "phase2")
        low_science = _make_science_result(overall_score=0.10)
        with_low = compute_probability_stack("asset-1", "phase2", science_result=low_science)
        assert with_low.technical_success_prob.probability < baseline.technical_success_prob.probability

    def test_prior_phase_success_true_increases_technical(self) -> None:
        baseline = compute_probability_stack("asset-1", "phase3")
        with_success = compute_probability_stack("asset-1", "phase3", prior_phase_success=True)
        assert with_success.technical_success_prob.probability > baseline.technical_success_prob.probability

    def test_prior_phase_success_false_decreases_technical(self) -> None:
        baseline = compute_probability_stack("asset-1", "phase3")
        with_failure = compute_probability_stack("asset-1", "phase3", prior_phase_success=False)
        assert with_failure.technical_success_prob.probability < baseline.technical_success_prob.probability

    def test_all_probabilities_strictly_within_0_and_1(self) -> None:
        result = compute_probability_stack("asset-1", "phase2")
        assert 0.01 <= result.technical_success_prob.probability <= 0.99
        assert 0.01 <= result.regulatory_approval_prob.probability <= 0.99
        assert 0.01 <= result.label_breadth_prob.probability <= 0.99
        assert 0.01 <= result.commercial_realization_prob.probability <= 0.99
        assert 0.01 <= result.delay_prob <= 0.99
        assert 0.01 <= result.crl_prob <= 0.99

    def test_full_value_prob_le_composite_pos(self) -> None:
        result = compute_probability_stack("asset-1", "phase2")
        assert result.full_value_prob <= result.composite_pos

    def test_delay_and_crl_in_reasonable_range(self) -> None:
        for phase in ("phase1", "phase2", "phase3", "nda_bla"):
            result = compute_probability_stack("asset-1", phase)
            assert 0.0 < result.delay_prob < 1.0
            assert 0.0 < result.crl_prob < 1.0

    def test_rationale_is_non_empty(self) -> None:
        result = compute_probability_stack("asset-1", "phase2")
        assert len(result.rationale) > 0

    def test_financing_modifier_stored_on_result(self) -> None:
        critical = _make_financing_risk(DistressTier.CRITICAL)
        result = compute_probability_stack("asset-1", "phase2", financing_risk=critical)
        assert result.financing_modifier == pytest.approx(0.70)

    def test_science_modifier_stored_on_result(self) -> None:
        science = _make_science_result(overall_score=0.80)
        result = compute_probability_stack("asset-1", "phase2", science_result=science)
        expected_modifier = 0.70 + 0.80 * 0.40
        assert result.science_modifier == pytest.approx(expected_modifier, rel=1e-6)

    def test_scenario_probs_all_non_negative(self) -> None:
        result = compute_probability_stack("asset-1", "phase2")
        for v in result.scenario_probs.values():
            assert v >= 0.0


# ---------------------------------------------------------------------------
# TestLabelBreadth
# ---------------------------------------------------------------------------


class TestLabelBreadth:
    def test_default_no_flags_returns_standard(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2")
        assert result.scope == LabelScope.STANDARD

    def test_biomarker_selection_returns_restricted(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", has_biomarker_selection=True)
        assert result.scope == LabelScope.RESTRICTED

    def test_rare_disease_returns_narrow(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", is_rare_disease=True)
        assert result.scope == LabelScope.NARROW

    def test_n_indications_3_or_more_returns_broad(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", n_indications_in_pipeline=3)
        assert result.scope == LabelScope.BROAD

    def test_indication_breadth_platform_returns_broad(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", indication_breadth="platform")
        assert result.scope == LabelScope.BROAD

    def test_indication_breadth_multiple_increases_p_broad(self) -> None:
        baseline = estimate_label_breadth("asset-1", "phase2")
        with_multiple = estimate_label_breadth("asset-1", "phase2", indication_breadth="multiple")
        assert with_multiple.p_broad_label >= baseline.p_broad_label

    def test_companion_diagnostic_increases_p_restricted(self) -> None:
        baseline = estimate_label_breadth("asset-1", "phase2")
        with_cdx = estimate_label_breadth("asset-1", "phase2", has_companion_diagnostic=True)
        assert with_cdx.p_restricted_label > baseline.p_restricted_label

    def test_p_broad_and_p_restricted_within_0_and_1(self) -> None:
        result = estimate_label_breadth(
            "asset-1", "phase2",
            has_biomarker_selection=True,
            is_rare_disease=False,
            n_indications_in_pipeline=1,
            has_companion_diagnostic=True,
        )
        assert 0.0 <= result.p_broad_label <= 1.0
        assert 0.0 <= result.p_restricted_label <= 1.0

    def test_p_broad_plus_p_restricted_le_1(self) -> None:
        for combo in [
            dict(has_biomarker_selection=True, has_companion_diagnostic=True),
            dict(n_indications_in_pipeline=3),
            dict(indication_breadth="platform"),
            dict(is_rare_disease=True),
        ]:
            result = estimate_label_breadth("asset-1", "phase2", **combo)
            assert result.p_broad_label + result.p_restricted_label <= 1.0 + 1e-9

    def test_commercial_multiplier_broad(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", n_indications_in_pipeline=3)
        assert result.commercial_multiplier == pytest.approx(1.3)

    def test_commercial_multiplier_standard(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2")
        assert result.commercial_multiplier == pytest.approx(1.0)

    def test_commercial_multiplier_restricted(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", has_biomarker_selection=True)
        assert result.commercial_multiplier == pytest.approx(0.7)

    def test_commercial_multiplier_narrow(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", is_rare_disease=True)
        assert result.commercial_multiplier == pytest.approx(0.4)

    def test_breadth_score_broad(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", indication_breadth="platform")
        assert result.breadth_score == pytest.approx(0.9)

    def test_breadth_score_standard(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2")
        assert result.breadth_score == pytest.approx(0.7)

    def test_breadth_score_restricted(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", has_biomarker_selection=True)
        assert result.breadth_score == pytest.approx(0.5)

    def test_breadth_score_narrow(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2", is_rare_disease=True)
        assert result.breadth_score == pytest.approx(0.3)

    def test_key_factors_non_empty(self) -> None:
        result = estimate_label_breadth("asset-1", "phase2")
        assert len(result.key_factors) > 0

    def test_rare_disease_with_3_indications_returns_broad(self) -> None:
        # n_indications >= 3 overrides rare_disease narrow
        result = estimate_label_breadth("asset-1", "phase2", is_rare_disease=True, n_indications_in_pipeline=3)
        assert result.scope == LabelScope.BROAD


# ---------------------------------------------------------------------------
# TestTimelineDistribution
# ---------------------------------------------------------------------------


class TestTimelineDistribution:
    def test_runs_for_phase1(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase1")
        assert isinstance(result, TimelineDistributionV2)

    def test_runs_for_phase2(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase2")
        assert isinstance(result, TimelineDistributionV2)

    def test_runs_for_phase3(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase3")
        assert isinstance(result, TimelineDistributionV2)

    def test_runs_for_nda_bla(self) -> None:
        result = compute_timeline_distribution("asset-1", "nda_bla")
        assert isinstance(result, TimelineDistributionV2)

    def test_phases_remaining_for_phase1_contains_all_phases(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase1")
        phase_names = [pt.phase for pt in result.phases_remaining]
        assert phase_names == ["phase1", "phase2", "phase3", "nda_bla"]

    def test_phases_remaining_for_phase3_contains_phase3_and_nda(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase3")
        phase_names = [pt.phase for pt in result.phases_remaining]
        assert phase_names == ["phase3", "nda_bla"]

    def test_phases_remaining_for_nda_bla_contains_only_nda(self) -> None:
        result = compute_timeline_distribution("asset-1", "nda_bla")
        phase_names = [pt.phase for pt in result.phases_remaining]
        assert phase_names == ["nda_bla"]

    def test_approved_phase_has_no_remaining_phases(self) -> None:
        result = compute_timeline_distribution("asset-1", "approved")
        assert result.phases_remaining == []
        assert result.expected_approval_months == 0.0

    def test_expected_approval_months_positive_for_phase1(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase1")
        assert result.expected_approval_months > 0.0

    def test_p10_less_than_p50_less_than_p90(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase2")
        assert result.p10_approval_months < result.p50_approval_months < result.p90_approval_months

    def test_fast_track_reduces_expected_approval_months(self) -> None:
        baseline = compute_timeline_distribution("asset-1", "phase2")
        with_ft = compute_timeline_distribution("asset-1", "phase2", has_fast_track=True)
        assert with_ft.expected_approval_months < baseline.expected_approval_months

    def test_breakthrough_reduces_more_than_fast_track(self) -> None:
        baseline = compute_timeline_distribution("asset-1", "phase2")
        with_ft = compute_timeline_distribution("asset-1", "phase2", has_fast_track=True)
        with_bt = compute_timeline_distribution("asset-1", "phase2", has_breakthrough=True)
        assert with_bt.expected_approval_months < baseline.expected_approval_months
        # breakthrough should reduce p50 more than fast_track alone (both reduce p50)
        assert with_bt.p50_approval_months <= with_ft.p50_approval_months

    def test_enrollment_off_track_increases_p90(self) -> None:
        baseline = compute_timeline_distribution("asset-1", "phase2")
        off_track = compute_timeline_distribution("asset-1", "phase2", enrollment_on_track=False)
        assert off_track.p90_approval_months > baseline.p90_approval_months

    def test_overall_delay_prob_in_0_to_1(self) -> None:
        for phase in ("phase1", "phase2", "phase3", "nda_bla"):
            result = compute_timeline_distribution("asset-1", phase)
            assert 0.0 <= result.overall_delay_prob <= 1.0

    def test_catalyst_months_away_equals_p50_of_current_phase(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase2")
        assert result.catalyst_months_away == result.phases_remaining[0].p50_months

    def test_prior_hold_increases_p90(self) -> None:
        baseline = compute_timeline_distribution("asset-1", "phase2")
        with_hold = compute_timeline_distribution("asset-1", "phase2", prior_hold=True)
        assert with_hold.p90_approval_months > baseline.p90_approval_months

    def test_rationale_non_empty(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase2")
        assert len(result.rationale) > 0

    def test_catalyst_months_away_none_for_approved(self) -> None:
        result = compute_timeline_distribution("asset-1", "approved")
        assert result.catalyst_months_away is None

    def test_phase_timeline_delay_risk_is_valid_enum_value(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase2")
        valid_risks = set(TimelineRisk)
        for pt in result.phases_remaining:
            assert pt.delay_risk in valid_risks

    def test_phase_timelines_have_positive_duration(self) -> None:
        result = compute_timeline_distribution("asset-1", "phase1")
        for pt in result.phases_remaining:
            assert pt.p10_months > 0
            assert pt.p50_months > 0
            assert pt.p90_months > 0
