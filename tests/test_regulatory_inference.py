"""
Unit tests for bve.models.regulatory_inference.

Coverage goals:
  - Default profile produces a reasonable approval probability
  - Each downward adjuster reduces approval_probability
  - Each upward adjuster increases approval_probability
  - approval_probability is clipped to [0.30, 0.97]
  - Scenario probabilities sum to 1.0
  - dominant_scenario is the highest-probability scenario
  - pos_modifier is within [-0.40, +0.15]
  - risk_flags is a list of strings
  - expected_pdufa_months is a positive float
  - prior_crl adds to risk_flags
"""
import pytest

from bve.models.regulatory_inference import (
    ApprovalPathway,
    RegulatoryProfile,
    RegulatoryScenario,
    infer_regulatory_risk,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def standard_profile() -> RegulatoryProfile:
    """Default profile: standard pathway, no red flags."""
    return RegulatoryProfile(approval_pathway=ApprovalPathway.STANDARD)


@pytest.fixture
def breakthrough_profile() -> RegulatoryProfile:
    return RegulatoryProfile(approval_pathway=ApprovalPathway.BREAKTHROUGH)


@pytest.fixture
def accelerated_profile() -> RegulatoryProfile:
    return RegulatoryProfile(
        approval_pathway=ApprovalPathway.ACCELERATED,
        confirmatory_study_required=True,
    )


# ---------------------------------------------------------------------------
# Default profile sanity checks
# ---------------------------------------------------------------------------

class TestDefaultProfile:
    def test_default_approval_probability_in_range(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        assert 0.30 <= result.approval_probability <= 0.97

    def test_default_approval_probability_near_base_rate(self, standard_profile):
        """Standard pathway base is 0.85; default adjusters should stay close."""
        result = infer_regulatory_risk(standard_profile)
        assert 0.75 <= result.approval_probability <= 0.97

    def test_default_risk_flags_empty(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        assert isinstance(result.risk_flags, list)
        assert len(result.risk_flags) == 0

    def test_default_pos_modifier_near_zero(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        assert -0.10 <= result.pos_modifier <= 0.10

    def test_expected_pdufa_months_positive(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        assert result.expected_pdufa_months > 0.0


# ---------------------------------------------------------------------------
# Downward adjusters
# ---------------------------------------------------------------------------

class TestDownwardAdjusters:
    def test_prior_crl_reduces_approval_probability(self):
        clean = RegulatoryProfile(approval_pathway=ApprovalPathway.STANDARD)
        with_crl = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, prior_crl_count=1
        )
        assert (
            infer_regulatory_risk(with_crl).approval_probability
            < infer_regulatory_risk(clean).approval_probability
        )

    def test_two_crls_reduce_more_than_one(self):
        one_crl = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, prior_crl_count=1
        )
        two_crls = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, prior_crl_count=2
        )
        assert (
            infer_regulatory_risk(two_crls).approval_probability
            < infer_regulatory_risk(one_crl).approval_probability
        )

    def test_safety_serious_events_reduces_approval_probability(self):
        clean = RegulatoryProfile(approval_pathway=ApprovalPathway.STANDARD)
        unsafe = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, safety_serious_events=True
        )
        assert (
            infer_regulatory_risk(unsafe).approval_probability
            < infer_regulatory_risk(clean).approval_probability
        )

    def test_negative_adcom_reduces_approval_probability(self):
        no_adcom = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, adcom_precedent="none"
        )
        neg_adcom = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, adcom_precedent="negative"
        )
        assert (
            infer_regulatory_risk(neg_adcom).approval_probability
            < infer_regulatory_risk(no_adcom).approval_probability
        )

    def test_mixed_adcom_reduces_less_than_negative(self):
        neg = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, adcom_precedent="negative"
        )
        mixed = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, adcom_precedent="mixed"
        )
        assert (
            infer_regulatory_risk(neg).approval_probability
            < infer_regulatory_risk(mixed).approval_probability
        )

    def test_manufacturing_fail_reduces_approval_probability(self):
        clear = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            manufacturing_inspections_clear=True,
        )
        flagged = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            manufacturing_inspections_clear=False,
        )
        assert (
            infer_regulatory_risk(flagged).approval_probability
            < infer_regulatory_risk(clear).approval_probability
        )

    def test_high_class_crl_rate_reduces_approval_probability(self):
        low_rate = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, class_prior_crl_rate=0.10
        )
        high_rate = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, class_prior_crl_rate=0.25
        )
        assert (
            infer_regulatory_risk(high_rate).approval_probability
            < infer_regulatory_risk(low_rate).approval_probability
        )

    def test_biomarker_only_endpoint_reduces_approval_probability(self):
        validated = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            endpoint_type="surrogate_validated",
        )
        biomarker = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            endpoint_type="biomarker_only",
        )
        assert (
            infer_regulatory_risk(biomarker).approval_probability
            < infer_regulatory_risk(validated).approval_probability
        )

    def test_surrogate_novel_endpoint_reduces_approval_probability(self):
        validated = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            endpoint_type="surrogate_validated",
        )
        novel = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            endpoint_type="surrogate_novel",
        )
        assert (
            infer_regulatory_risk(novel).approval_probability
            < infer_regulatory_risk(validated).approval_probability
        )


# ---------------------------------------------------------------------------
# Upward adjusters
# ---------------------------------------------------------------------------

class TestUpwardAdjusters:
    def test_positive_adcom_increases_approval_probability(self):
        no_adcom = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, adcom_precedent="none"
        )
        pos_adcom = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, adcom_precedent="positive"
        )
        assert (
            infer_regulatory_risk(pos_adcom).approval_probability
            >= infer_regulatory_risk(no_adcom).approval_probability
        )

    def test_hard_clinical_endpoint_increases_approval_probability(self):
        surrogate = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            endpoint_type="surrogate_validated",
        )
        hard = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            endpoint_type="hard_clinical",
        )
        assert (
            infer_regulatory_risk(hard).approval_probability
            >= infer_regulatory_risk(surrogate).approval_probability
        )


# ---------------------------------------------------------------------------
# Clipping
# ---------------------------------------------------------------------------

class TestProbabilityClipping:
    def test_approval_probability_never_below_floor(self):
        """Stack all downward adjusters; result must stay >= 0.30."""
        worst_case = RegulatoryProfile(
            approval_pathway=ApprovalPathway.ACCELERATED,
            prior_crl_count=5,
            safety_serious_events=True,
            adcom_precedent="negative",
            manufacturing_inspections_clear=False,
            class_prior_crl_rate=0.50,
            endpoint_type="biomarker_only",
        )
        result = infer_regulatory_risk(worst_case)
        assert result.approval_probability >= 0.30

    def test_approval_probability_never_above_ceiling(self):
        """Stack all upward adjusters; result must stay <= 0.97."""
        best_case = RegulatoryProfile(
            approval_pathway=ApprovalPathway.BREAKTHROUGH,
            adcom_precedent="positive",
            endpoint_type="hard_clinical",
        )
        result = infer_regulatory_risk(best_case)
        assert result.approval_probability <= 0.97


# ---------------------------------------------------------------------------
# Scenario distribution
# ---------------------------------------------------------------------------

class TestScenarioDistribution:
    def test_scenario_probabilities_sum_to_one(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        total = sum(s.probability for s in result.scenarios)
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_five_scenarios_returned(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        assert len(result.scenarios) == 5

    def test_dominant_scenario_is_highest_probability(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        max_prob = max(s.probability for s in result.scenarios)
        dominant_prob = next(
            s.probability for s in result.scenarios
            if s.scenario == result.dominant_scenario
        )
        assert dominant_prob == pytest.approx(max_prob)

    def test_clean_approval_is_dominant_for_strong_profile(self, breakthrough_profile):
        result = infer_regulatory_risk(breakthrough_profile)
        assert result.dominant_scenario == RegulatoryScenario.CLEAN_APPROVAL

    def test_all_scenario_probabilities_non_negative(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        for s in result.scenarios:
            assert s.probability >= 0.0


# ---------------------------------------------------------------------------
# POS modifier
# ---------------------------------------------------------------------------

class TestPosModifier:
    def test_pos_modifier_within_bounds(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        assert -0.40 <= result.pos_modifier <= 0.15

    def test_pos_modifier_worst_case_within_bounds(self):
        worst_case = RegulatoryProfile(
            approval_pathway=ApprovalPathway.ACCELERATED,
            prior_crl_count=5,
            safety_serious_events=True,
            adcom_precedent="negative",
            manufacturing_inspections_clear=False,
            class_prior_crl_rate=0.50,
            endpoint_type="biomarker_only",
        )
        result = infer_regulatory_risk(worst_case)
        assert -0.40 <= result.pos_modifier <= 0.15

    def test_adverse_profile_has_negative_pos_modifier(self):
        adverse = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD,
            safety_serious_events=True,
            adcom_precedent="negative",
        )
        result = infer_regulatory_risk(adverse)
        assert result.pos_modifier < 0.0


# ---------------------------------------------------------------------------
# Risk flags
# ---------------------------------------------------------------------------

class TestRiskFlags:
    def test_prior_crl_adds_risk_flag(self):
        profile = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, prior_crl_count=1
        )
        result = infer_regulatory_risk(profile)
        assert any("CRL" in flag for flag in result.risk_flags)

    def test_safety_events_add_risk_flag(self):
        profile = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, safety_serious_events=True
        )
        result = infer_regulatory_risk(profile)
        assert any("adverse" in flag.lower() for flag in result.risk_flags)

    def test_risk_flags_are_all_strings(self, standard_profile):
        result = infer_regulatory_risk(standard_profile)
        assert all(isinstance(f, str) for f in result.risk_flags)

    def test_accelerated_with_confirmatory_adds_flag(self, accelerated_profile):
        result = infer_regulatory_risk(accelerated_profile)
        assert any("confirmatory" in flag.lower() for flag in result.risk_flags)

    def test_negative_adcom_adds_risk_flag(self):
        profile = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, adcom_precedent="negative"
        )
        result = infer_regulatory_risk(profile)
        assert any("adcom" in flag.lower() or "AdCom" in flag for flag in result.risk_flags)


# ---------------------------------------------------------------------------
# PDUFA months
# ---------------------------------------------------------------------------

class TestPdufaMonths:
    def test_priority_pathway_shorter_than_standard(self):
        standard = infer_regulatory_risk(
            RegulatoryProfile(approval_pathway=ApprovalPathway.STANDARD)
        )
        priority = infer_regulatory_risk(
            RegulatoryProfile(approval_pathway=ApprovalPathway.PRIORITY)
        )
        assert priority.expected_pdufa_months < standard.expected_pdufa_months

    def test_safety_events_increase_pdufa_months(self):
        clean = RegulatoryProfile(approval_pathway=ApprovalPathway.STANDARD)
        unsafe = RegulatoryProfile(
            approval_pathway=ApprovalPathway.STANDARD, safety_serious_events=True
        )
        assert (
            infer_regulatory_risk(unsafe).expected_pdufa_months
            > infer_regulatory_risk(clean).expected_pdufa_months
        )
