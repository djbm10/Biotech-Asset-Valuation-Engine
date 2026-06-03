"""
Tests for 0G Data Confidence module (ma_data_confidence.py).

Coverage:
  - Source quality helper
  - Per-category scoring (completeness × reliability)
  - Freshness penalty
  - Composite weighted score
  - Label thresholds (HIGH / MEDIUM / LOW / VERY_LOW)
  - Rights/IP gate: cap at MEDIUM when rights_ip < 0.50
  - Ranking treatment mapping
  - Missing / stale / low-reliability field reporting
  - Source quality summary
  - Rationale list content
  - Backward-compatibility aliases (grade, score, eligible_*)
  - Target adapter (data_confidence_from_target)
  - Edge cases: all flags True + all False; freshness combinations
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_data_confidence import (
    DataConfidenceInput,
    DataConfidenceLabel,
    DataConfidenceResult,
    RankingTreatment,
    SOURCE_QUALITY_SCORES,
    _CATEGORY_WEIGHTS,
    _FRESHNESS_PENALTY,
    _RIGHTS_IP_CAP_THRESHOLD,
    compute_data_confidence,
    data_confidence_from_target,
    source_quality,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_flags(**overrides) -> DataConfidenceInput:
    """All has_* flags True, default source qualities, all fresh."""
    defaults = dict(
        has_market_cap=True,
        has_enterprise_value=True,
        has_cash_debt=True,
        has_quarterly_burn=True,
        has_revenue_mix=True,
        has_clinical_stage=True,
        has_trial_status=True,
        has_asset_ownership_data=True,
        has_partner_rights_data=True,
        has_patent_loe_data=True,
        has_acquirer_profile_data=True,
    )
    defaults.update(overrides)
    return DataConfidenceInput(**defaults)


def _no_flags(**overrides) -> DataConfidenceInput:
    """All has_* flags False, default source qualities, all fresh."""
    return DataConfidenceInput(**overrides)


def _sec_quality() -> dict:
    """Source quality kwargs that push all categories to sec_filing level."""
    return dict(
        market_data_source_quality=0.95,
        financial_data_source_quality=0.95,
        asset_data_source_quality=0.95,
        rights_ip_source_quality=0.95,
        acquirer_data_source_quality=0.95,
    )


# ---------------------------------------------------------------------------
# source_quality helper
# ---------------------------------------------------------------------------

class TestSourceQualityHelper:
    def test_known_sources_match_table(self):
        for name, expected in SOURCE_QUALITY_SCORES.items():
            assert source_quality(name) == expected

    def test_case_insensitive(self):
        assert source_quality("SEC_FILING") == source_quality("sec_filing")
        assert source_quality("Annual_Report") == source_quality("annual_report")

    def test_unknown_source_returns_0_50(self):
        assert source_quality("made_up_source") == 0.50

    def test_sec_filing_highest(self):
        assert source_quality("sec_filing") == max(SOURCE_QUALITY_SCORES.values())

    def test_manual_note_very_low(self):
        assert source_quality("manual_note") < 0.40


# ---------------------------------------------------------------------------
# Category weights
# ---------------------------------------------------------------------------

class TestCategoryWeights:
    def test_weights_sum_to_one(self):
        assert abs(sum(_CATEGORY_WEIGHTS.values()) - 1.0) < 1e-9

    def test_financial_has_highest_weight(self):
        assert _CATEGORY_WEIGHTS["financial"] == max(_CATEGORY_WEIGHTS.values())

    def test_acquirer_has_lowest_weight(self):
        assert _CATEGORY_WEIGHTS["acquirer"] == min(_CATEGORY_WEIGHTS.values())

    def test_five_categories_present(self):
        assert set(_CATEGORY_WEIGHTS.keys()) == {"financial", "asset", "rights_ip", "market", "acquirer"}


# ---------------------------------------------------------------------------
# Score computation — all flags True
# ---------------------------------------------------------------------------

class TestAllFlagsTrue:
    def test_default_quality_gives_medium(self):
        """All fields present + default source qualities → MEDIUM (not HIGH)."""
        inp = _all_flags()
        result = compute_data_confidence(inp)
        assert result.confidence_label == DataConfidenceLabel.MEDIUM

    def test_sec_quality_gives_high(self):
        """All fields + SEC-level source quality → HIGH."""
        inp = _all_flags(**_sec_quality())
        result = compute_data_confidence(inp)
        assert result.confidence_label == DataConfidenceLabel.HIGH

    def test_score_bounded_0_1(self):
        inp = _all_flags(**_sec_quality())
        result = compute_data_confidence(inp)
        assert 0.0 <= result.data_confidence_score <= 1.0

    def test_no_missing_fields_when_all_present(self):
        inp = _all_flags()
        result = compute_data_confidence(inp)
        assert result.missing_fields == []

    def test_no_stale_fields_when_all_fresh(self):
        inp = _all_flags()
        result = compute_data_confidence(inp)
        assert result.stale_fields == []

    def test_eligible_for_ranked_output_when_high(self):
        inp = _all_flags(**_sec_quality())
        result = compute_data_confidence(inp)
        assert result.eligible_for_ranked_output is True
        assert result.ranking_treatment == RankingTreatment.ELIGIBLE_RANKED

    def test_eligible_flagged_when_medium(self):
        inp = _all_flags()
        result = compute_data_confidence(inp)
        assert result.eligible_for_ranked_output is True
        assert result.ranking_treatment == RankingTreatment.ELIGIBLE_FLAGGED


# ---------------------------------------------------------------------------
# Score computation — no flags
# ---------------------------------------------------------------------------

class TestNoFlags:
    def test_no_flags_gives_very_low(self):
        result = compute_data_confidence(_no_flags())
        assert result.confidence_label == DataConfidenceLabel.VERY_LOW

    def test_score_is_zero_when_completeness_zero(self):
        result = compute_data_confidence(_no_flags())
        assert result.data_confidence_score == 0.0

    def test_all_fields_listed_as_missing(self):
        result = compute_data_confidence(_no_flags())
        expected_fields = {
            "market_cap", "enterprise_value",
            "cash_debt", "quarterly_burn", "revenue_mix",
            "clinical_stage", "trial_status", "asset_ownership_data",
            "partner_rights_data", "patent_loe_data",
            "acquirer_profile_data",
        }
        assert set(result.missing_fields) == expected_fields

    def test_excluded_treatment_when_very_low(self):
        result = compute_data_confidence(_no_flags())
        assert result.ranking_treatment == RankingTreatment.EXCLUDE
        assert result.eligible_for_ranked_output is False
        assert result.eligible_for_diligence_queue is False


# ---------------------------------------------------------------------------
# Freshness penalty
# ---------------------------------------------------------------------------

class TestFreshnessPenalty:
    def test_stale_financial_data_reduces_score(self):
        fresh = compute_data_confidence(_all_flags())
        stale = compute_data_confidence(_all_flags(financial_data_fresh=False))
        assert stale.data_confidence_score < fresh.data_confidence_score

    def test_stale_category_appears_in_stale_list(self):
        result = compute_data_confidence(_all_flags(market_data_fresh=False))
        assert "market_data" in result.stale_fields

    def test_stale_applies_80pct_multiplier(self):
        # rights_ip: 1 flag each → completeness varies; check reliability
        # Set rights_ip stale + all flags True + known source quality
        inp = DataConfidenceInput(
            has_partner_rights_data=True,
            has_patent_loe_data=True,
            rights_ip_source_quality=0.80,
            rights_ip_data_fresh=False,
        )
        result = compute_data_confidence(inp)
        # rights_ip cat reliability = 0.80 × 0.80 = 0.64; completeness=1.0 → cat_score=0.64
        expected_rights_ip = round(1.0 * 0.80 * _FRESHNESS_PENALTY, 4)
        assert abs(result.category_scores["rights_ip"] - expected_rights_ip) < 1e-4

    def test_multiple_stale_categories_all_listed(self):
        inp = _all_flags(financial_data_fresh=False, asset_data_fresh=False)
        result = compute_data_confidence(inp)
        assert "financial_data" in result.stale_fields
        assert "asset_data" in result.stale_fields


# ---------------------------------------------------------------------------
# Rights / IP gate
# ---------------------------------------------------------------------------

class TestRightsIPGate:
    def test_rights_ip_below_threshold_caps_at_medium(self):
        """Even with SEC-level source quality elsewhere, low rights_ip → cap at MEDIUM."""
        inp = _all_flags(
            market_data_source_quality=0.95,
            financial_data_source_quality=0.95,
            asset_data_source_quality=0.95,
            rights_ip_source_quality=0.30,  # low → rights_ip cat < 0.50
            acquirer_data_source_quality=0.95,
        )
        result = compute_data_confidence(inp)
        assert result.confidence_label != DataConfidenceLabel.HIGH
        assert result.confidence_label == DataConfidenceLabel.MEDIUM

    def test_rights_ip_gate_rationale_message_present(self):
        inp = _all_flags(
            market_data_source_quality=0.95,
            financial_data_source_quality=0.95,
            asset_data_source_quality=0.95,
            rights_ip_source_quality=0.30,
            acquirer_data_source_quality=0.95,
        )
        result = compute_data_confidence(inp)
        gate_msgs = [r for r in result.rationale if "rights_ip_gate" in r]
        assert gate_msgs, "Expected rights_ip_gate rationale line"

    def test_rights_ip_above_threshold_no_cap(self):
        """rights_ip confidence ≥ 0.50 → no cap applied."""
        inp = _all_flags(**_sec_quality())
        result = compute_data_confidence(inp)
        assert result.confidence_label == DataConfidenceLabel.HIGH
        gate_msgs = [r for r in result.rationale if "rights_ip_gate" in r]
        assert not gate_msgs

    def test_rights_ip_threshold_boundary(self):
        """rights_ip_score == threshold is NOT capped (strictly less-than rule)."""
        # Force rights_ip cat_score exactly at threshold: completeness=1.0, reliability=0.50
        inp = _all_flags(
            rights_ip_source_quality=0.50,  # reliability=0.50×1.0=0.50; completeness=1.0 → 0.50
            # All others at SEC quality to push composite high enough to matter
            market_data_source_quality=0.95,
            financial_data_source_quality=0.95,
            asset_data_source_quality=0.95,
            acquirer_data_source_quality=0.95,
        )
        result = compute_data_confidence(inp)
        # rights_ip cat_score = 0.50, threshold = 0.50 → not strictly less → no cap
        gate_msgs = [r for r in result.rationale if "rights_ip_gate" in r]
        assert not gate_msgs


# ---------------------------------------------------------------------------
# Label thresholds
# ---------------------------------------------------------------------------

class TestLabelThresholds:
    def _score_with_target(self, target_score: float) -> DataConfidenceLabel:
        """Create an input that produces approximately target_score."""
        # Only way to directly test label function is by constructing realistic inputs.
        # Use rights_ip both present (completeness=1.0) and vary source quality.
        # Simplest: all flags True, tune source qualities.
        # cat_score = completeness × source_quality (all fresh)
        # composite = sum(cat_score × weight)
        # With all completeness=1: composite = sum(sq × weight)
        # Solve: sq = target_score for all categories
        sq = min(max(target_score, 0.0), 1.0)
        inp = _all_flags(
            market_data_source_quality=sq,
            financial_data_source_quality=sq,
            asset_data_source_quality=sq,
            rights_ip_source_quality=sq,
            acquirer_data_source_quality=sq,
        )
        return compute_data_confidence(inp).confidence_label

    def test_score_above_80_is_high(self):
        label = self._score_with_target(0.90)
        assert label == DataConfidenceLabel.HIGH

    def test_score_60_to_79_is_medium(self):
        label = self._score_with_target(0.70)
        assert label == DataConfidenceLabel.MEDIUM

    def test_score_40_to_59_is_low(self):
        # sq=0.45 → composite ≈ 0.45 (< 0.60) → LOW
        inp = _all_flags(
            market_data_source_quality=0.45,
            financial_data_source_quality=0.45,
            asset_data_source_quality=0.45,
            rights_ip_source_quality=0.45,
            acquirer_data_source_quality=0.45,
        )
        result = compute_data_confidence(inp)
        assert result.confidence_label == DataConfidenceLabel.LOW

    def test_very_low_below_40(self):
        # No flags → score=0 → VERY_LOW
        assert compute_data_confidence(_no_flags()).confidence_label == DataConfidenceLabel.VERY_LOW


# ---------------------------------------------------------------------------
# Ranking treatment mapping
# ---------------------------------------------------------------------------

class TestRankingTreatment:
    def test_high_maps_to_eligible_ranked(self):
        inp = _all_flags(**_sec_quality())
        result = compute_data_confidence(inp)
        if result.confidence_label == DataConfidenceLabel.HIGH:
            assert result.ranking_treatment == RankingTreatment.ELIGIBLE_RANKED

    def test_medium_maps_to_eligible_flagged(self):
        inp = _all_flags()
        result = compute_data_confidence(inp)
        if result.confidence_label == DataConfidenceLabel.MEDIUM:
            assert result.ranking_treatment == RankingTreatment.ELIGIBLE_FLAGGED

    def test_low_maps_to_diligence_queue(self):
        inp = _all_flags(
            market_data_source_quality=0.45,
            financial_data_source_quality=0.45,
            asset_data_source_quality=0.45,
            rights_ip_source_quality=0.45,
            acquirer_data_source_quality=0.45,
        )
        result = compute_data_confidence(inp)
        if result.confidence_label == DataConfidenceLabel.LOW:
            assert result.ranking_treatment == RankingTreatment.DILIGENCE_QUEUE
            assert result.eligible_for_diligence_queue is True

    def test_very_low_maps_to_exclude(self):
        result = compute_data_confidence(_no_flags())
        assert result.ranking_treatment == RankingTreatment.EXCLUDE
        assert result.eligible_for_ranked_output is False
        assert result.eligible_for_diligence_queue is False


# ---------------------------------------------------------------------------
# Missing / stale / low-reliability fields
# ---------------------------------------------------------------------------

class TestFieldReporting:
    def test_partial_missing_fields(self):
        inp = DataConfidenceInput(
            has_market_cap=True,
            has_cash_debt=True,
        )
        result = compute_data_confidence(inp)
        missing = set(result.missing_fields)
        assert "market_cap" not in missing
        assert "cash_debt" not in missing
        assert "enterprise_value" in missing
        assert "quarterly_burn" in missing

    def test_stale_fields_passthrough(self):
        inp = _all_flags(stale_fields=["custom_field_A"])
        result = compute_data_confidence(inp)
        assert "custom_field_A" in result.stale_fields

    def test_low_reliability_fields_passthrough(self):
        inp = _all_flags(low_reliability_fields=["custom_source_B"])
        result = compute_data_confidence(inp)
        assert "custom_source_B" in result.low_reliability_fields

    def test_low_reliability_auto_detected_from_source_quality(self):
        """Category with source_quality < 0.50 → added to low_reliability_fields."""
        inp = _all_flags(rights_ip_source_quality=0.40)
        result = compute_data_confidence(inp)
        assert "rights_ip_data" in result.low_reliability_fields


# ---------------------------------------------------------------------------
# Source quality summary
# ---------------------------------------------------------------------------

class TestSourceQualitySummary:
    def test_summary_has_all_five_categories(self):
        result = compute_data_confidence(_all_flags())
        assert set(result.source_quality_summary.keys()) == {
            "financial", "asset", "rights_ip", "market", "acquirer"
        }

    def test_summary_reflects_input_quality(self):
        inp = _all_flags(financial_data_source_quality=0.90)
        result = compute_data_confidence(inp)
        assert result.source_quality_summary["financial"] == 0.90


# ---------------------------------------------------------------------------
# Category scores
# ---------------------------------------------------------------------------

class TestCategoryScores:
    def test_category_scores_keys(self):
        result = compute_data_confidence(_all_flags())
        assert set(result.category_scores.keys()) == {"financial", "asset", "rights_ip", "market", "acquirer"}

    def test_category_scores_bounded(self):
        result = compute_data_confidence(_all_flags(**_sec_quality()))
        for score in result.category_scores.values():
            assert 0.0 <= score <= 1.0

    def test_completeness_drives_category_score(self):
        """Category with 0/3 flags = score 0; category with 3/3 flags = score > 0."""
        # financial: all 3 flags False
        inp = DataConfidenceInput(
            has_cash_debt=False,
            has_quarterly_burn=False,
            has_revenue_mix=False,
            financial_data_source_quality=0.95,
        )
        result = compute_data_confidence(inp)
        assert result.category_scores["financial"] == 0.0

    def test_partial_completeness(self):
        """1 of 3 financial flags → completeness = 1/3."""
        inp = DataConfidenceInput(has_cash_debt=True, financial_data_source_quality=0.90)
        result = compute_data_confidence(inp)
        expected = round((1 / 3) * 0.90, 4)
        assert abs(result.category_scores["financial"] - expected) < 1e-4


# ---------------------------------------------------------------------------
# Rationale
# ---------------------------------------------------------------------------

class TestRationale:
    def test_rationale_is_nonempty_list(self):
        result = compute_data_confidence(_all_flags())
        assert isinstance(result.rationale, list)
        assert len(result.rationale) >= 1

    def test_rationale_contains_score_line(self):
        result = compute_data_confidence(_all_flags())
        assert any("data_confidence=" in r for r in result.rationale)

    def test_rationale_contains_category_scores(self):
        result = compute_data_confidence(_all_flags())
        assert any("category_scores:" in r for r in result.rationale)

    def test_missing_fields_appear_in_rationale_when_present(self):
        result = compute_data_confidence(_no_flags())
        assert any("missing_fields" in r for r in result.rationale)


# ---------------------------------------------------------------------------
# Backward-compatibility aliases
# ---------------------------------------------------------------------------

class TestBackwardCompatAliases:
    def test_grade_equals_confidence_label(self):
        result = compute_data_confidence(_all_flags())
        assert result.grade == result.confidence_label

    def test_score_equals_data_confidence_score(self):
        result = compute_data_confidence(_all_flags())
        assert result.score == result.data_confidence_score

    def test_eligible_for_ranked_output_high(self):
        inp = _all_flags(**_sec_quality())
        result = compute_data_confidence(inp)
        if result.confidence_label == DataConfidenceLabel.HIGH:
            assert result.eligible_for_ranked_output is True

    def test_eligible_for_ranked_output_medium(self):
        result = compute_data_confidence(_all_flags())
        if result.confidence_label == DataConfidenceLabel.MEDIUM:
            assert result.eligible_for_ranked_output is True

    def test_not_eligible_for_ranked_when_very_low(self):
        result = compute_data_confidence(_no_flags())
        assert result.eligible_for_ranked_output is False

    def test_eligible_for_diligence_queue_medium(self):
        result = compute_data_confidence(_all_flags())
        if result.confidence_label == DataConfidenceLabel.MEDIUM:
            assert result.eligible_for_diligence_queue is True

    def test_not_eligible_for_diligence_queue_very_low(self):
        result = compute_data_confidence(_no_flags())
        assert result.eligible_for_diligence_queue is False


# ---------------------------------------------------------------------------
# Target adapter
# ---------------------------------------------------------------------------

class _MockTarget:
    """Minimal duck-type compatible with TargetEligibilityInput for adapter tests."""
    has_market_cap = True
    has_enterprise_value = True
    has_cash_debt = True
    has_quarterly_burn = True
    has_revenue_mix = True
    has_clinical_stage = True
    has_trial_status = True
    has_asset_ownership_data = True
    has_partner_rights_data = True
    has_patent_loe_data = True
    has_acquirer_profile_data = True
    market_data_source_quality = 0.70
    financial_data_source_quality = 0.70
    asset_data_source_quality = 0.70
    rights_ip_source_quality = 0.50
    acquirer_data_source_quality = 0.60
    market_data_fresh = True
    financial_data_fresh = True
    asset_data_fresh = True
    rights_ip_data_fresh = True
    acquirer_data_fresh = True
    stale_field_names: list = []
    low_reliability_field_names: list = []


class TestTargetAdapter:
    def test_adapter_returns_data_confidence_input(self):
        result = data_confidence_from_target(_MockTarget())
        assert isinstance(result, DataConfidenceInput)

    def test_adapter_maps_flags_correctly(self):
        t = _MockTarget()
        inp = data_confidence_from_target(t)
        assert inp.has_market_cap is True
        assert inp.has_cash_debt is True
        assert inp.rights_ip_source_quality == 0.50

    def test_adapter_missing_attrs_use_defaults(self):
        """Object with no M&A fields → all defaults."""

        class MinimalTarget:
            pass

        inp = data_confidence_from_target(MinimalTarget())
        assert inp.has_market_cap is False
        assert inp.rights_ip_source_quality == 0.50  # default

    def test_adapter_stale_fields_passthrough(self):
        class TargetWithStale:
            stale_field_names = ["partner_contract"]
            low_reliability_field_names = []

        inp = data_confidence_from_target(TargetWithStale())
        assert "partner_contract" in inp.stale_fields

    def test_adapter_result_is_computable(self):
        """Adapter output fed to compute_data_confidence produces a valid result."""
        inp = data_confidence_from_target(_MockTarget())
        result = compute_data_confidence(inp)
        assert isinstance(result, DataConfidenceResult)
        assert 0.0 <= result.data_confidence_score <= 1.0


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------

class TestMonotonicity:
    def test_more_fields_gives_higher_score(self):
        r0 = compute_data_confidence(_no_flags())
        r1 = compute_data_confidence(DataConfidenceInput(has_cash_debt=True))
        r2 = compute_data_confidence(DataConfidenceInput(has_cash_debt=True, has_quarterly_burn=True))
        assert r0.data_confidence_score <= r1.data_confidence_score <= r2.data_confidence_score

    def test_higher_source_quality_gives_higher_score(self):
        low_sq = compute_data_confidence(_all_flags(financial_data_source_quality=0.45))
        high_sq = compute_data_confidence(_all_flags(financial_data_source_quality=0.95))
        assert low_sq.data_confidence_score < high_sq.data_confidence_score

    def test_stale_data_gives_lower_score_than_fresh(self):
        fresh = compute_data_confidence(_all_flags())
        stale = compute_data_confidence(_all_flags(
            financial_data_fresh=False,
            asset_data_fresh=False,
        ))
        assert stale.data_confidence_score < fresh.data_confidence_score
