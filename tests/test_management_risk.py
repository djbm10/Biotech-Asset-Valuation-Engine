"""
Unit tests for bve.models.management_risk.

Coverage goals:
  - Default record produces an expected tier
  - Prior approvals increase score
  - Prior failures decrease score
  - CEO turnover and operational stumble both reduce score
  - Score is clipped to [0.10, 0.95]
  - Tier thresholds are correct
  - All three modifier types are returned and in range
  - data_completeness is in [0.0, 1.0]
  - strengths and concerns are lists of strings
"""
import pytest

from bve.models.management_risk import ManagementRecord, score_management


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_record() -> ManagementRecord:
    """All defaults — represents a completely unknown management team."""
    return ManagementRecord()


@pytest.fixture
def strong_record() -> ManagementRecord:
    return ManagementRecord(
        prior_fda_approvals=2,
        prior_fda_failures=0,
        years_experience_oncology=15,
        dilution_events_3yr=1,
        guidance_hits_3yr=4,
        guidance_misses_3yr=0,
        strategic_partnerships=2,
        insider_buying_recent=True,
        ceo_turnover_2yr=False,
        operational_stumble=False,
    )


@pytest.fixture
def weak_record() -> ManagementRecord:
    return ManagementRecord(
        prior_fda_approvals=0,
        prior_fda_failures=3,
        years_experience_oncology=2,
        dilution_events_3yr=5,
        guidance_hits_3yr=0,
        guidance_misses_3yr=4,
        strategic_partnerships=0,
        insider_buying_recent=False,
        ceo_turnover_2yr=True,
        operational_stumble=True,
    )


# ---------------------------------------------------------------------------
# Default record
# ---------------------------------------------------------------------------

class TestDefaultRecord:
    def test_default_tier_is_unknown_or_adequate(self, default_record):
        result = score_management(default_record)
        # All defaults means data_completeness == 0 → "unknown" tier
        assert result.tier in ("unknown", "adequate")

    def test_default_record_tier_is_unknown(self, default_record):
        """With zero non-default fields, data_completeness < 0.30 → unknown."""
        result = score_management(default_record)
        assert result.tier == "unknown"

    def test_default_data_completeness_is_zero(self, default_record):
        result = score_management(default_record)
        assert result.data_completeness == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Score direction: approvals and failures
# ---------------------------------------------------------------------------

class TestApprovalAndFailureSignals:
    def test_prior_approvals_increase_score(self):
        no_approvals = score_management(ManagementRecord(years_experience_oncology=10))
        with_approvals = score_management(
            ManagementRecord(prior_fda_approvals=2, years_experience_oncology=10)
        )
        assert with_approvals.raw_score > no_approvals.raw_score

    def test_prior_failures_decrease_score(self):
        no_failures = score_management(ManagementRecord(years_experience_oncology=10))
        with_failures = score_management(
            ManagementRecord(prior_fda_failures=2, years_experience_oncology=10)
        )
        assert with_failures.raw_score < no_failures.raw_score

    def test_two_approvals_better_than_one(self):
        one = score_management(
            ManagementRecord(prior_fda_approvals=1, years_experience_oncology=10)
        )
        two = score_management(
            ManagementRecord(prior_fda_approvals=2, years_experience_oncology=10)
        )
        assert two.raw_score > one.raw_score

    def test_approval_bonus_caps_at_two_approvals(self):
        two = score_management(
            ManagementRecord(prior_fda_approvals=2, years_experience_oncology=10)
        )
        ten = score_management(
            ManagementRecord(prior_fda_approvals=10, years_experience_oncology=10)
        )
        # Cap means delta is identical beyond 2 approvals; scores should be equal
        assert two.raw_score == pytest.approx(ten.raw_score)

    def test_failure_penalty_caps_at_two_failures(self):
        two = score_management(
            ManagementRecord(prior_fda_failures=2, years_experience_oncology=10)
        )
        ten = score_management(
            ManagementRecord(prior_fda_failures=10, years_experience_oncology=10)
        )
        assert two.raw_score == pytest.approx(ten.raw_score)


# ---------------------------------------------------------------------------
# Red flag signals
# ---------------------------------------------------------------------------

class TestRedFlagSignals:
    def test_ceo_turnover_reduces_score(self):
        stable = score_management(ManagementRecord(years_experience_oncology=10))
        turnover = score_management(
            ManagementRecord(ceo_turnover_2yr=True, years_experience_oncology=10)
        )
        assert turnover.raw_score < stable.raw_score

    def test_operational_stumble_reduces_score(self):
        clean = score_management(ManagementRecord(years_experience_oncology=10))
        stumble = score_management(
            ManagementRecord(operational_stumble=True, years_experience_oncology=10)
        )
        assert stumble.raw_score < clean.raw_score

    def test_ceo_turnover_and_stumble_both_reduce_score(self):
        clean = score_management(ManagementRecord(years_experience_oncology=10))
        both = score_management(
            ManagementRecord(
                ceo_turnover_2yr=True,
                operational_stumble=True,
                years_experience_oncology=10,
            )
        )
        assert both.raw_score < clean.raw_score

    def test_low_experience_reduces_score(self):
        experienced = score_management(ManagementRecord(years_experience_oncology=10))
        inexperienced = score_management(ManagementRecord(years_experience_oncology=2))
        assert inexperienced.raw_score < experienced.raw_score


# ---------------------------------------------------------------------------
# Score clipping
# ---------------------------------------------------------------------------

class TestScoreClipping:
    def test_score_never_below_floor(self, weak_record):
        result = score_management(weak_record)
        assert result.raw_score >= 0.10

    def test_score_never_above_ceiling(self, strong_record):
        result = score_management(strong_record)
        assert result.raw_score <= 0.95


# ---------------------------------------------------------------------------
# Tier thresholds
# ---------------------------------------------------------------------------

class TestTierThresholds:
    def test_strong_tier_for_strong_record(self, strong_record):
        result = score_management(strong_record)
        assert result.tier == "strong"

    def test_weak_tier_for_weak_record(self, weak_record):
        result = score_management(weak_record)
        assert result.tier in ("weak", "unknown")

    def test_unknown_when_data_completeness_low(self, default_record):
        result = score_management(default_record)
        assert result.tier == "unknown"

    def test_adequate_tier_for_mid_range_record(self):
        mid = ManagementRecord(
            prior_fda_approvals=1,
            years_experience_oncology=8,
            guidance_hits_3yr=2,
            guidance_misses_3yr=1,
        )
        result = score_management(mid)
        assert result.tier in ("adequate", "strong")


# ---------------------------------------------------------------------------
# Modifiers
# ---------------------------------------------------------------------------

class TestModifiers:
    def test_all_three_modifiers_returned(self, strong_record):
        result = score_management(strong_record)
        assert isinstance(result.timeline_confidence_modifier, float)
        assert isinstance(result.financing_risk_modifier, float)
        assert isinstance(result.execution_risk_modifier, float)

    def test_strong_tier_has_best_modifiers(self, strong_record):
        result = score_management(strong_record)
        assert result.timeline_confidence_modifier > 1.0
        assert result.execution_risk_modifier > 0.0

    def test_weak_tier_has_worst_modifiers(self, weak_record):
        result = score_management(weak_record)
        # weak or unknown tier; both have execution_risk_modifier <= 0
        assert result.execution_risk_modifier <= 0.0


# ---------------------------------------------------------------------------
# data_completeness
# ---------------------------------------------------------------------------

class TestDataCompleteness:
    def test_data_completeness_in_unit_interval(self, strong_record):
        result = score_management(strong_record)
        assert 0.0 <= result.data_completeness <= 1.0

    def test_fully_populated_record_has_high_completeness(self, strong_record):
        result = score_management(strong_record)
        # strong_record has all non-default values except operational_stumble=False
        assert result.data_completeness > 0.50

    def test_default_record_has_zero_completeness(self, default_record):
        result = score_management(default_record)
        assert result.data_completeness == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# strengths and concerns
# ---------------------------------------------------------------------------

class TestStrengthsAndConcerns:
    def test_strengths_is_list_of_strings(self, strong_record):
        result = score_management(strong_record)
        assert isinstance(result.strengths, list)
        assert all(isinstance(s, str) for s in result.strengths)

    def test_concerns_is_list_of_strings(self, weak_record):
        result = score_management(weak_record)
        assert isinstance(result.concerns, list)
        assert all(isinstance(c, str) for c in result.concerns)

    def test_strong_record_has_no_concerns_about_approvals(self, strong_record):
        result = score_management(strong_record)
        assert not any("failure" in c.lower() for c in result.concerns)

    def test_weak_record_has_concerns(self, weak_record):
        result = score_management(weak_record)
        assert len(result.concerns) > 0

    def test_ceo_turnover_appears_in_concerns(self):
        record = ManagementRecord(ceo_turnover_2yr=True, years_experience_oncology=10)
        result = score_management(record)
        assert any("ceo" in c.lower() or "turnover" in c.lower() for c in result.concerns)
