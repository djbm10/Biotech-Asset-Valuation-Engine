"""Block 11 — Management Quality & Value Preservation tests.

Covers:
  Sprint 52A — ManagementReceptivity model + acquisition cap gate
  Sprint 52B — Value-destruction flags + postmortem ErrorType codes
  Sprint 52C — Decision report management quality section
"""
from __future__ import annotations

import pytest


# ===========================================================================
# Sprint 52A: ManagementReceptivity model
# ===========================================================================

class TestManagementReceptivityEnum:
    def test_all_values_exist(self):
        from bve.intelligence.ma_management_receptivity import ManagementReceptivity
        assert ManagementReceptivity.OPEN.value == "open"
        assert ManagementReceptivity.NEUTRAL.value == "neutral"
        assert ManagementReceptivity.RESISTANT.value == "resistant"
        assert ManagementReceptivity.ENTRENCHED.value == "entrenched"
        assert ManagementReceptivity.UNKNOWN.value == "unknown"

    def test_is_string_enum(self):
        from bve.intelligence.ma_management_receptivity import ManagementReceptivity
        assert isinstance(ManagementReceptivity.OPEN, str)
        assert ManagementReceptivity.ENTRENCHED == "entrenched"


class TestReceptivityContext:
    def test_default_is_unknown(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity,
        )
        ctx = ReceptivityContext()
        assert ctx.receptivity == ManagementReceptivity.UNKNOWN

    def test_all_fields_accessible(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity,
        )
        ctx = ReceptivityContext(
            receptivity=ManagementReceptivity.OPEN,
            has_activist_pressure=True,
            has_strategic_review=False,
            has_prior_partnership_history=True,
            founder_on_board=False,
            data_confidence=0.75,
        )
        assert ctx.receptivity == ManagementReceptivity.OPEN
        assert ctx.has_activist_pressure is True
        assert ctx.data_confidence == 0.75

    def test_frozen(self):
        from bve.intelligence.ma_management_receptivity import ReceptivityContext
        ctx = ReceptivityContext()
        with pytest.raises((AttributeError, TypeError)):
            ctx.founder_on_board = True  # type: ignore[misc]


class TestApplyReceptivityGateUnknown:
    def test_unknown_returns_no_cap(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.UNKNOWN,
        ))
        assert gate.acquisition_probability_cap is None

    def test_unknown_returns_no_boost(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.UNKNOWN,
        ))
        assert gate.partner_realism_boost == 0.0

    def test_unknown_confidence_capped_at_040(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.UNKNOWN,
            data_confidence=0.90,
        ))
        assert gate.confidence <= 0.40

    def test_unknown_no_flags(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.UNKNOWN,
        ))
        assert gate.flags == []


class TestApplyReceptivityGateEntrenched:
    def test_entrenched_no_catalyst_cap_025(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.ENTRENCHED,
            has_activist_pressure=False,
            has_strategic_review=False,
        ))
        assert gate.acquisition_probability_cap == pytest.approx(0.25)

    def test_entrenched_activist_relaxes_cap(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.ENTRENCHED,
            has_activist_pressure=True,
            has_strategic_review=False,
        ))
        assert gate.acquisition_probability_cap == pytest.approx(0.55)
        assert gate.cap_catalyst_present is True

    def test_entrenched_strategic_review_relaxes_cap(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.ENTRENCHED,
            has_activist_pressure=False,
            has_strategic_review=True,
        ))
        assert gate.acquisition_probability_cap == pytest.approx(0.55)
        assert gate.cap_catalyst_present is True

    def test_entrenched_no_catalyst_no_catalyst_present_flag(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.ENTRENCHED,
        ))
        assert gate.cap_catalyst_present is False

    def test_entrenched_founder_on_board_adds_flag(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.ENTRENCHED,
            founder_on_board=True,
        ))
        assert "founder_entrenchment" in gate.flags

    def test_entrenched_no_founder_no_flag(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.ENTRENCHED,
            founder_on_board=False,
        ))
        assert "founder_entrenchment" not in gate.flags

    def test_entrenched_no_boost(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.ENTRENCHED,
        ))
        assert gate.partner_realism_boost == 0.0


class TestApplyReceptivityGateResistant:
    def test_resistant_cap_050(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.RESISTANT,
        ))
        assert gate.acquisition_probability_cap == pytest.approx(0.50)

    def test_resistant_founder_adds_flag(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.RESISTANT,
            founder_on_board=True,
        ))
        assert "founder_entrenchment" in gate.flags

    def test_resistant_no_founder_no_flag(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.RESISTANT,
            founder_on_board=False,
        ))
        assert "founder_entrenchment" not in gate.flags


class TestApplyReceptivityGateOpen:
    def test_open_no_history_no_cap_no_boost(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.OPEN,
            has_prior_partnership_history=False,
        ))
        assert gate.acquisition_probability_cap is None
        assert gate.partner_realism_boost == 0.0

    def test_open_with_history_boost_010(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.OPEN,
            has_prior_partnership_history=True,
        ))
        assert gate.partner_realism_boost == pytest.approx(0.10)

    def test_open_with_history_adds_value_preserving_flag(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.OPEN,
            has_prior_partnership_history=True,
        ))
        assert "value_preserving_management" in gate.flags

    def test_open_no_history_no_value_preserving_flag(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.OPEN,
            has_prior_partnership_history=False,
        ))
        assert "value_preserving_management" not in gate.flags


class TestApplyReceptivityGateNeutral:
    def test_neutral_no_cap(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.NEUTRAL,
        ))
        assert gate.acquisition_probability_cap is None

    def test_neutral_with_history_small_boost(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.NEUTRAL,
            has_prior_partnership_history=True,
        ))
        assert gate.partner_realism_boost == pytest.approx(0.05)

    def test_neutral_no_history_no_boost(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.NEUTRAL,
            has_prior_partnership_history=False,
        ))
        assert gate.partner_realism_boost == 0.0


class TestReceptivityToProcessClosingCap:
    def test_none_when_open(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity,
            apply_receptivity_gate, receptivity_to_process_closing_cap,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.OPEN,
        ))
        assert receptivity_to_process_closing_cap(gate) is None

    def test_returns_cap_when_entrenched(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity,
            apply_receptivity_gate, receptivity_to_process_closing_cap,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.ENTRENCHED,
        ))
        cap = receptivity_to_process_closing_cap(gate)
        assert cap is not None
        assert cap <= 0.30


class TestReceptivityGateResult:
    def test_result_has_rationale(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        for receptivity in ManagementReceptivity:
            gate = apply_receptivity_gate(ReceptivityContext(receptivity=receptivity))
            assert isinstance(gate.rationale, str)
            assert len(gate.rationale) > 10

    def test_result_is_frozen(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.OPEN,
        ))
        with pytest.raises((AttributeError, TypeError)):
            gate.partner_realism_boost = 0.99  # type: ignore[misc]


# ===========================================================================
# Sprint 52B: Value-destruction flags
# ===========================================================================

class TestValueDestructionFlags:
    def _input_with(self, **overrides):
        from bve.intelligence.ma_management_quality import ManagementQualityInput
        defaults = dict(
            target_id="test",
            clinical_execution_quality=0.80,
            trial_design_judgment=0.80,
            regulatory_execution=0.80,
            capital_allocation_discipline=0.80,
            bd_partnering_judgment=0.80,
            disclosure_transparency=0.80,
            governance_alignment=0.80,
        )
        defaults.update(overrides)
        return ManagementQualityInput(**defaults)

    def test_overpromotional_disclosure_flag_on_low_transparency(self):
        from bve.intelligence.ma_management_quality import compute_management_quality_score
        score = compute_management_quality_score(
            self._input_with(disclosure_transparency=0.20)
        )
        assert "overpromotional_disclosure" in score.negative_drivers

    def test_bad_financing_timing_flag_on_low_capital_discipline(self):
        from bve.intelligence.ma_management_quality import compute_management_quality_score
        score = compute_management_quality_score(
            self._input_with(capital_allocation_discipline=0.20)
        )
        assert "bad_financing_timing" in score.negative_drivers

    def test_legacy_flags_still_present(self):
        from bve.intelligence.ma_management_quality import compute_management_quality_score
        score = compute_management_quality_score(
            self._input_with(
                disclosure_transparency=0.20,
                capital_allocation_discipline=0.20,
            )
        )
        # Legacy names preserved for backward compatibility
        assert "low_disclosure_transparency" in score.negative_drivers
        assert "financing_value_destruction_risk" in score.negative_drivers

    def test_value_preserving_management_flag_on_high_composite(self):
        from bve.intelligence.ma_management_quality import compute_management_quality_score
        score = compute_management_quality_score(self._input_with())  # all 0.80 → composite ~0.80
        assert "value_preserving_management" in score.positive_drivers

    def test_no_value_preserving_flag_on_medium_composite(self):
        from bve.intelligence.ma_management_quality import compute_management_quality_score
        score = compute_management_quality_score(
            self._input_with(
                clinical_execution_quality=0.60,
                trial_design_judgment=0.60,
                regulatory_execution=0.60,
                capital_allocation_discipline=0.60,
                bd_partnering_judgment=0.60,
                disclosure_transparency=0.60,
                governance_alignment=0.60,
            )
        )
        assert "value_preserving_management" not in score.positive_drivers

    def test_wrong_trial_risk_still_present(self):
        from bve.intelligence.ma_management_quality import compute_management_quality_score
        score = compute_management_quality_score(
            self._input_with(trial_design_judgment=0.20)
        )
        assert "wrong_trial_risk" in score.negative_drivers

    def test_poor_partnering_history_still_present(self):
        from bve.intelligence.ma_management_quality import compute_management_quality_score
        score = compute_management_quality_score(
            self._input_with(bd_partnering_judgment=0.20)
        )
        assert "poor_partnering_history" in score.negative_drivers


class TestPostmortemErrorTypeCodes:
    def test_management_diluted_before_catalyst(self):
        from bve.intelligence.ma_calibration_models import ErrorType
        assert ErrorType.MANAGEMENT_DILUTED_BEFORE_CATALYST == "management_diluted_before_catalyst"

    def test_management_overpromoted_weak_data(self):
        from bve.intelligence.ma_calibration_models import ErrorType
        assert ErrorType.MANAGEMENT_OVERPROMOTED_WEAK_DATA == "management_overpromoted_weak_data"

    def test_management_partnered_too_early(self):
        from bve.intelligence.ma_calibration_models import ErrorType
        assert ErrorType.MANAGEMENT_PARTNERED_TOO_EARLY == "management_partnered_too_early"

    def test_management_refused_value_maximizing_deal(self):
        from bve.intelligence.ma_calibration_models import ErrorType
        assert ErrorType.MANAGEMENT_REFUSED_VALUE_MAXIMIZING_DEAL == "management_refused_value_maximizing_deal"

    def test_management_executed_better_than_expected(self):
        from bve.intelligence.ma_calibration_models import ErrorType
        assert ErrorType.MANAGEMENT_EXECUTED_BETTER_THAN_EXPECTED == "management_executed_better_than_expected"

    def test_legacy_codes_still_present(self):
        from bve.intelligence.ma_calibration_models import ErrorType
        # Verify Block 6 codes not broken
        assert ErrorType.MANAGEMENT_RAN_WRONG_TRIAL == "management_ran_wrong_trial"
        assert ErrorType.MANAGEMENT_POOR_BD_JUDGMENT == "management_poor_bd_judgment"
        assert ErrorType.MANAGEMENT_CAPITAL_DESTRUCTION == "management_capital_destruction"
        assert ErrorType.MANAGEMENT_GOVERNANCE_BLOCKED_DEAL == "management_governance_blocked_deal"

    def test_all_management_codes_are_strings(self):
        from bve.intelligence.ma_calibration_models import ErrorType
        management_codes = [e for e in ErrorType if e.value.startswith("management_")]
        assert len(management_codes) >= 9  # 4 existing + 5 new
        for code in management_codes:
            assert isinstance(code.value, str)


# ===========================================================================
# Sprint 52C: DecisionReport management quality section
# ===========================================================================

class TestDecisionReportManagementSection:
    def _make_mgmt_score(self, **overrides):
        from bve.intelligence.ma_management_quality import (
            ManagementQualityInput, compute_management_quality_score,
        )
        defaults = dict(
            target_id="test",
            clinical_execution_quality=0.75,
            trial_design_judgment=0.75,
            regulatory_execution=0.75,
            capital_allocation_discipline=0.75,
            bd_partnering_judgment=0.75,
            disclosure_transparency=0.75,
            governance_alignment=0.75,
        )
        defaults.update(overrides)
        return compute_management_quality_score(ManagementQualityInput(**defaults))

    def _make_report(self, management_quality=None, management_diligence_questions=None):
        from bve.reporting.decision_report import DecisionReportInput
        return DecisionReportInput(
            ticker="TEST",
            management_quality=management_quality,
            management_diligence_questions=management_diligence_questions or [],
        )

    def test_no_management_section_when_none(self):
        from bve.reporting.decision_report import render_decision_report
        report = self._make_report(management_quality=None)
        output = render_decision_report(report)
        assert "## Management Quality" not in output

    def test_management_section_present_when_provided(self):
        from bve.reporting.decision_report import render_decision_report
        score = self._make_mgmt_score()
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        assert "## Management Quality" in output

    def test_renders_risk_band(self):
        from bve.reporting.decision_report import render_decision_report
        score = self._make_mgmt_score()
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        assert "Risk band" in output

    def test_renders_composite_score(self):
        from bve.reporting.decision_report import render_decision_report
        score = self._make_mgmt_score()
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        assert "Composite score" in output

    def test_renders_gate(self):
        from bve.reporting.decision_report import render_decision_report
        score = self._make_mgmt_score()
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        assert "Gate" in output

    def test_renders_value_destruction_flags(self):
        from bve.reporting.decision_report import render_decision_report
        score = self._make_mgmt_score(disclosure_transparency=0.20)
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        assert "Value-Destruction Flags" in output
        assert "overpromotional_disclosure" in output

    def test_renders_positive_indicators(self):
        from bve.reporting.decision_report import render_decision_report
        # All components high → value_preserving_management flag
        score = self._make_mgmt_score(
            clinical_execution_quality=0.90,
            trial_design_judgment=0.90,
            regulatory_execution=0.90,
            capital_allocation_discipline=0.90,
            bd_partnering_judgment=0.90,
            disclosure_transparency=0.90,
            governance_alignment=0.90,
        )
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        assert "Positive Indicators" in output

    def test_renders_diligence_questions_when_weak_component(self):
        from bve.reporting.decision_report import render_decision_report
        score = self._make_mgmt_score(trial_design_judgment=0.20)
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        assert "Diligence Questions" in output

    def test_supplied_diligence_questions_used(self):
        from bve.reporting.decision_report import render_decision_report
        from bve.intelligence.ma_management_diligence import ManagementDiligenceQuestion
        score = self._make_mgmt_score()
        q = ManagementDiligenceQuestion(
            category="bd_partnering",
            question="Would management partner before Phase 3 readout?",
            priority="HIGH",
            owner="BD",
            source_needed=["management meeting note"],
            trigger="test",
        )
        report = self._make_report(
            management_quality=score,
            management_diligence_questions=[q],
        )
        output = render_decision_report(report)
        assert "Would management partner before Phase 3 readout?" in output

    def test_max_5_diligence_questions_rendered(self):
        from bve.reporting.decision_report import render_decision_report
        from bve.intelligence.ma_management_diligence import ManagementDiligenceQuestion
        score = self._make_mgmt_score()
        questions = [
            ManagementDiligenceQuestion(
                category="bd_partnering",
                question=f"Question {i}?",
                priority="HIGH",
                owner="BD",
                source_needed=["management note"],
                trigger="test",
            )
            for i in range(10)
        ]
        report = self._make_report(
            management_quality=score,
            management_diligence_questions=questions,
        )
        output = render_decision_report(report)
        # Count question lines rendered (each starts with "- **[HIGH")
        rendered_questions = [ln for ln in output.split("\n") if "Question " in ln and "**[HIGH" in ln]
        assert len(rendered_questions) <= 5

    def test_staleness_warning_rendered(self):
        from bve.reporting.decision_report import render_decision_report
        from bve.intelligence.ma_management_quality import (
            ManagementQualityInput, compute_management_quality_score,
        )
        score = compute_management_quality_score(ManagementQualityInput(
            target_id="test",
            clinical_execution_quality=0.75,
            trial_design_judgment=0.75,
            regulatory_execution=0.75,
            capital_allocation_discipline=0.75,
            bd_partnering_judgment=0.75,
            disclosure_transparency=0.75,
            governance_alignment=0.75,
            data_staleness_days=200,  # > 180 day threshold
        ))
        assert score.staleness_warning is True
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        assert "Staleness" in output

    def test_unknown_management_gate_shows_diligence_required(self):
        from bve.reporting.decision_report import render_decision_report
        from bve.intelligence.ma_management_quality import (
            ManagementQualityInput, compute_management_quality_score,
        )
        # < 4 components → UNKNOWN band
        score = compute_management_quality_score(ManagementQualityInput(
            target_id="test",
            clinical_execution_quality=0.75,
            trial_design_judgment=0.75,
        ))
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        assert "Management Quality" in output
        assert "diligence_required" in output.lower() or "UNKNOWN" in output

    def test_decision_report_input_has_management_fields(self):
        from bve.reporting.decision_report import DecisionReportInput
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(DecisionReportInput)}
        assert "management_quality" in field_names
        assert "management_diligence_questions" in field_names

    def test_report_sections_order(self):
        """Management section appears after input_integrity, before provenance."""
        from bve.reporting.decision_report import render_decision_report
        score = self._make_mgmt_score()
        report = self._make_report(management_quality=score)
        output = render_decision_report(report)
        mgmt_pos = output.find("## Management Quality")
        prov_pos = output.find("## Assumption Provenance")
        assert mgmt_pos != -1
        assert prov_pos != -1
        assert mgmt_pos < prov_pos


# ===========================================================================
# Cross-cutting: ReceptivityGateResult flags flow
# ===========================================================================

class TestFlagPropagation:
    """Verify that flags from the receptivity gate are the right names to
    use downstream in BuyerTargetThesis and DecisionReport."""

    def test_founder_entrenchment_flag_name(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.ENTRENCHED,
            founder_on_board=True,
        ))
        # The flag name must be exactly this string for downstream consumers
        assert "founder_entrenchment" in gate.flags

    def test_value_preserving_management_flag_name(self):
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.OPEN,
            has_prior_partnership_history=True,
        ))
        assert "value_preserving_management" in gate.flags

    def test_quality_score_value_preserving_flag_matches_receptivity_flag(self):
        """Both layers use the same canonical flag name."""
        from bve.intelligence.ma_management_quality import (
            ManagementQualityInput, compute_management_quality_score,
        )
        from bve.intelligence.ma_management_receptivity import (
            ReceptivityContext, ManagementReceptivity, apply_receptivity_gate,
        )
        q_score = compute_management_quality_score(ManagementQualityInput(
            target_id="test",
            clinical_execution_quality=0.95,
            trial_design_judgment=0.95,
            regulatory_execution=0.95,
            capital_allocation_discipline=0.95,
            bd_partnering_judgment=0.95,
            disclosure_transparency=0.95,
            governance_alignment=0.95,
        ))
        r_gate = apply_receptivity_gate(ReceptivityContext(
            receptivity=ManagementReceptivity.OPEN,
            has_prior_partnership_history=True,
        ))
        # Both should use the same flag name
        assert "value_preserving_management" in q_score.positive_drivers
        assert "value_preserving_management" in r_gate.flags
