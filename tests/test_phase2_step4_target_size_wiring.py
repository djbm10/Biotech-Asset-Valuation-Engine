"""Tests for Phase 2 Step 4 — target_size wired into evaluate_layer0().

Coverage:
  1. Layer0Result.target_size is always populated (even for excluded targets)
  2. target_size uses EV when present; falls back to market cap
  3. target_size.bucket matches expected for each size tier
  4. required_downstream_checks gains "large_cap_buyer_required" for large/mega targets
  5. required_downstream_checks gains "sub_scale_target_review" for sub-scale targets
  6. mid-cap target: neither flag appears
  7. Target size does NOT contribute to score_multiplier or score_cap
  8. Target size does NOT exclude any target on its own
  9. Layer0DecisionSummary.target_size_bucket and .target_size_reference_millions populated
 10. Plain-English verdict mentions size for mega-deal / sub-scale / large-cap
 11. Backward compatibility: acquirers= path still works, no new warnings from target_size
 12. target_size is computed even when passes_hard_exclusion is False
 13. Unknown bucket when no market data
 14. Affordability check still present when EV known
 15. affordability_data_required still fires when EV absent (MC fallback only)
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_eligibility import (
    evaluate_layer0,
    TargetEligibilityInput,
    CompanyTaxonomy,
)
from bve.intelligence.ma_target_size import TargetSizeBucket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_data_target(
    ticker: str = "TGT",
    ev: float | None = 2_000.0,
    mc: float | None = 1_800.0,
    **kwargs,
) -> TargetEligibilityInput:
    """A target with all 11 data flags set — passes all gates cleanly."""
    return TargetEligibilityInput(
        ticker=ticker,
        enterprise_value_millions=ev,
        market_cap_millions=mc,
        has_market_cap=True,
        has_enterprise_value=True,
        has_cash_debt=True,
        has_quarterly_burn=True,
        has_revenue_mix=True,
        has_asset_ownership_data=True,
        has_clinical_stage=True,
        has_trial_status=True,
        has_partner_rights_data=True,
        has_patent_loe_data=True,
        has_acquirer_profile_data=True,
        **kwargs,
    )


def _excluded_target() -> TargetEligibilityInput:
    """A SPAC/shell target that fails Gate 1 (SPAC_SHELL exclusion)."""
    return TargetEligibilityInput(
        ticker="SPAC",
        company_taxonomy=CompanyTaxonomy.SPAC_SHELL,
        enterprise_value_millions=500.0,
        market_cap_millions=480.0,
        has_market_cap=True,
        has_enterprise_value=True,
        has_cash_debt=True,
        has_clinical_stage=True,
        has_trial_status=True,
    )


# ---------------------------------------------------------------------------
# 1. target_size always populated
# ---------------------------------------------------------------------------

class TestTargetSizeAlwaysPopulated:

    def test_target_size_present_for_passing_target(self):
        r = evaluate_layer0(_full_data_target())
        assert r.target_size is not None

    def test_target_size_present_for_excluded_target(self):
        r = evaluate_layer0(_excluded_target())
        assert r.target_size is not None

    def test_target_size_present_when_no_ev_or_mc(self):
        t = _full_data_target(ev=None, mc=None)
        r = evaluate_layer0(t)
        assert r.target_size is not None
        assert r.target_size.size_bucket == TargetSizeBucket.UNKNOWN

    def test_target_size_is_target_size_result(self):
        from bve.intelligence.ma_target_size import TargetSizeResult
        r = evaluate_layer0(_full_data_target())
        assert isinstance(r.target_size, TargetSizeResult)


# ---------------------------------------------------------------------------
# 2. EV vs MC reference source
# ---------------------------------------------------------------------------

class TestReferenceSourcePrecedence:

    def test_ev_used_when_present(self):
        r = evaluate_layer0(_full_data_target(ev=3_000.0, mc=1_000.0))
        assert r.target_size.reference_source == "enterprise_value"
        assert r.target_size.reference_value_millions == pytest.approx(3_000.0)

    def test_mc_fallback_when_ev_absent(self):
        r = evaluate_layer0(_full_data_target(ev=None, mc=400.0))
        assert r.target_size.reference_source == "market_cap"
        assert r.target_size.reference_value_millions == pytest.approx(400.0)

    def test_unknown_when_both_absent(self):
        r = evaluate_layer0(_full_data_target(ev=None, mc=None))
        assert r.target_size.reference_source == "none"
        assert r.target_size.size_bucket == TargetSizeBucket.UNKNOWN


# ---------------------------------------------------------------------------
# 3. Bucket classification end-to-end
# ---------------------------------------------------------------------------

class TestBucketClassificationViaEvaluateLayer0:

    def test_sub_scale_bucket(self):
        r = evaluate_layer0(_full_data_target(ev=50.0))
        assert r.target_size.size_bucket == TargetSizeBucket.SUB_SCALE

    def test_small_cap_bucket(self):
        r = evaluate_layer0(_full_data_target(ev=300.0))
        assert r.target_size.size_bucket == TargetSizeBucket.SMALL_CAP

    def test_mid_cap_bucket(self):
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        assert r.target_size.size_bucket == TargetSizeBucket.MID_CAP

    def test_large_cap_bucket(self):
        r = evaluate_layer0(_full_data_target(ev=10_000.0))
        assert r.target_size.size_bucket == TargetSizeBucket.LARGE_CAP

    def test_mega_deal_bucket(self):
        r = evaluate_layer0(_full_data_target(ev=50_000.0))
        assert r.target_size.size_bucket == TargetSizeBucket.MEGA_DEAL


# ---------------------------------------------------------------------------
# 4. large_cap_buyer_required check
# ---------------------------------------------------------------------------

class TestLargeCapBuyerRequiredCheck:

    def test_large_cap_target_adds_check(self):
        r = evaluate_layer0(_full_data_target(ev=10_000.0))
        assert "large_cap_buyer_required" in r.required_downstream_checks

    def test_mega_deal_adds_check(self):
        r = evaluate_layer0(_full_data_target(ev=50_000.0))
        assert "large_cap_buyer_required" in r.required_downstream_checks

    def test_mid_cap_does_not_add_check(self):
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        assert "large_cap_buyer_required" not in r.required_downstream_checks

    def test_small_cap_does_not_add_check(self):
        r = evaluate_layer0(_full_data_target(ev=300.0))
        assert "large_cap_buyer_required" not in r.required_downstream_checks

    def test_large_cap_check_in_decision_summary(self):
        r = evaluate_layer0(_full_data_target(ev=10_000.0))
        assert "large_cap_buyer_required" in r.decision_summary.required_downstream_checks


# ---------------------------------------------------------------------------
# 5. sub_scale_target_review check
# ---------------------------------------------------------------------------

class TestSubScaleTargetReviewCheck:

    def test_sub_scale_target_adds_check(self):
        r = evaluate_layer0(_full_data_target(ev=50.0))
        assert "sub_scale_target_review" in r.required_downstream_checks

    def test_small_cap_does_not_add_sub_scale_check(self):
        r = evaluate_layer0(_full_data_target(ev=300.0))
        assert "sub_scale_target_review" not in r.required_downstream_checks

    def test_mid_cap_does_not_add_sub_scale_check(self):
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        assert "sub_scale_target_review" not in r.required_downstream_checks

    def test_sub_scale_check_in_decision_summary(self):
        r = evaluate_layer0(_full_data_target(ev=50.0))
        assert "sub_scale_target_review" in r.decision_summary.required_downstream_checks


# ---------------------------------------------------------------------------
# 6. Mid-cap: neither size flag in checks
# ---------------------------------------------------------------------------

class TestMidCapNoSizeChecks:

    def test_mid_cap_has_no_size_routing_checks(self):
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        size_checks = {
            "large_cap_buyer_required",
            "sub_scale_target_review",
        }
        assert size_checks.isdisjoint(set(r.required_downstream_checks))


# ---------------------------------------------------------------------------
# 7. No score effect from target_size
# ---------------------------------------------------------------------------

class TestNoScoreEffectFromTargetSize:

    def _base_score_multiplier(self) -> float:
        """score_multiplier for a clean mid-cap target (no encumbrance)."""
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        return r.score_multiplier

    def test_sub_scale_does_not_change_score_multiplier(self):
        r_mid = evaluate_layer0(_full_data_target(ev=2_000.0))
        r_sub = evaluate_layer0(_full_data_target(ev=50.0))
        # Both should have identical multipliers (assuming same encumbrance inputs)
        assert r_sub.score_multiplier == pytest.approx(r_mid.score_multiplier)

    def test_mega_deal_does_not_change_score_multiplier(self):
        r_mid = evaluate_layer0(_full_data_target(ev=2_000.0))
        r_mega = evaluate_layer0(_full_data_target(ev=50_000.0))
        assert r_mega.score_multiplier == pytest.approx(r_mid.score_multiplier)

    def test_large_cap_does_not_apply_score_cap(self):
        r = evaluate_layer0(_full_data_target(ev=10_000.0))
        # score_cap should be None unless 0F distress guard fires
        # With a clean target, no cap should be set by size alone
        assert r.score_cap is None

    def test_sub_scale_does_not_apply_score_cap(self):
        r = evaluate_layer0(_full_data_target(ev=50.0))
        assert r.score_cap is None

    def test_target_size_not_in_layer0_notes(self):
        """Size annotations must not appear in layer0_notes as penalty codes."""
        r = evaluate_layer0(_full_data_target(ev=50_000.0))
        # Notes may contain size info but should not carry a penalty multiplier entry
        penalty_notes = [n for n in r.layer0_notes if "score_multiplier" in n or "penalty" in n]
        assert not any("size" in n for n in penalty_notes)


# ---------------------------------------------------------------------------
# 8. Target size never excludes a target
# ---------------------------------------------------------------------------

class TestSizeNeverExcludes:

    def test_sub_scale_passes_hard_exclusion(self):
        r = evaluate_layer0(_full_data_target(ev=10.0))
        # A tiny EV does not trigger hard exclusion
        assert r.passes_hard_exclusion is True

    def test_mega_deal_passes_hard_exclusion(self):
        r = evaluate_layer0(_full_data_target(ev=100_000.0))
        assert r.passes_hard_exclusion is True

    def test_sub_scale_is_live_ranking_eligible(self):
        r = evaluate_layer0(_full_data_target(ev=10.0))
        assert r.live_ranking_eligible is True

    def test_mega_deal_is_live_ranking_eligible(self):
        r = evaluate_layer0(_full_data_target(ev=100_000.0))
        assert r.live_ranking_eligible is True


# ---------------------------------------------------------------------------
# 9. decision_summary fields populated
# ---------------------------------------------------------------------------

class TestDecisionSummaryTargetSizeFields:

    def test_target_size_bucket_in_summary(self):
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        assert r.decision_summary.target_size_bucket == "mid_cap"

    def test_target_size_reference_in_summary(self):
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        assert r.decision_summary.target_size_reference_millions == pytest.approx(2_000.0)

    def test_unknown_bucket_in_summary_when_no_data(self):
        r = evaluate_layer0(_full_data_target(ev=None, mc=None))
        assert r.decision_summary.target_size_bucket == "unknown"
        assert r.decision_summary.target_size_reference_millions is None

    def test_summary_bucket_for_large_cap(self):
        r = evaluate_layer0(_full_data_target(ev=10_000.0))
        assert r.decision_summary.target_size_bucket == "large_cap"

    def test_summary_bucket_for_excluded_target(self):
        """Excluded targets still get a target_size_bucket in the summary."""
        r = evaluate_layer0(_excluded_target())
        # excluded → passes=False → decision summary still has bucket
        assert r.decision_summary.target_size_bucket is not None


# ---------------------------------------------------------------------------
# 10. Plain-English verdict size notes
# ---------------------------------------------------------------------------

class TestPlainEnglishVerdictSizeNotes:

    def test_mega_deal_mentioned_in_verdict(self):
        r = evaluate_layer0(_full_data_target(ev=50_000.0))
        verdict = r.decision_summary.plain_english_verdict.lower()
        assert "mega" in verdict or "pharma" in verdict or "50,000" in verdict

    def test_sub_scale_mentioned_in_verdict(self):
        r = evaluate_layer0(_full_data_target(ev=50.0))
        verdict = r.decision_summary.plain_english_verdict.lower()
        assert "bolt-on" in verdict or "sub-scale" in verdict or "50" in verdict

    def test_large_cap_mentioned_in_verdict(self):
        r = evaluate_layer0(_full_data_target(ev=10_000.0))
        verdict = r.decision_summary.plain_english_verdict.lower()
        assert "large-cap" in verdict or "investment-grade" in verdict or "10,000" in verdict

    def test_mid_cap_verdict_has_no_size_warning(self):
        """Mid-cap is the normal case; verdict should not contain size warnings."""
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        verdict = r.decision_summary.plain_english_verdict.lower()
        assert "bolt-on" not in verdict
        assert "mega" not in verdict
        assert "investment-grade" not in verdict


# ---------------------------------------------------------------------------
# 11. Backward compat: acquirers= still works, no extra warnings
# ---------------------------------------------------------------------------

class TestAffordabilityFieldCompat:

    def test_affordability_always_empty_list(self):
        """Layer0Result.affordability is always []; pair affordability is Layer 3A."""
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        assert r.affordability == []
        # target_size still populated
        assert r.target_size is not None

    def test_no_deprecation_warnings_from_evaluate_layer0(self):
        """evaluate_layer0() emits no DeprecationWarnings."""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            evaluate_layer0(_full_data_target(ev=2_000.0))
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep_warnings) == 0


# ---------------------------------------------------------------------------
# 12. target_size computed for excluded targets
# ---------------------------------------------------------------------------

class TestTargetSizeComputedForExcludedTargets:

    def test_excluded_target_has_target_size(self):
        r = evaluate_layer0(_excluded_target())
        assert r.passes_hard_exclusion is False
        assert r.target_size is not None

    def test_excluded_target_target_size_bucket_correct(self):
        r = evaluate_layer0(_excluded_target())
        # excluded_target has EV=500 → MID_CAP (boundary: < 500 → SMALL_CAP, ≥ 500 → MID_CAP)
        assert r.target_size.size_bucket == TargetSizeBucket.MID_CAP

    def test_excluded_target_required_checks_empty(self):
        """Required downstream checks are empty for excluded targets."""
        r = evaluate_layer0(_excluded_target())
        # _compute_required_downstream_checks returns [] when passes=False
        assert r.required_downstream_checks == []


# ---------------------------------------------------------------------------
# 13. Unknown bucket when no market data
# ---------------------------------------------------------------------------

class TestUnknownBucketNoMarketData:

    def test_unknown_bucket_when_both_none(self):
        r = evaluate_layer0(_full_data_target(ev=None, mc=None))
        assert r.target_size.size_bucket == TargetSizeBucket.UNKNOWN

    def test_unknown_bucket_has_no_size_checks(self):
        r = evaluate_layer0(_full_data_target(ev=None, mc=None))
        assert "large_cap_buyer_required" not in r.required_downstream_checks
        assert "sub_scale_target_review" not in r.required_downstream_checks

    def test_unknown_target_size_reference_is_none(self):
        r = evaluate_layer0(_full_data_target(ev=None, mc=None))
        assert r.target_size.reference_value_millions is None


# ---------------------------------------------------------------------------
# 14. Affordability check still present when EV known
# ---------------------------------------------------------------------------

class TestAffordabilityCheckCoexistsWithSizeCheck:

    def test_affordability_and_large_cap_both_present(self):
        r = evaluate_layer0(_full_data_target(ev=10_000.0))
        assert "affordability" in r.required_downstream_checks
        assert "large_cap_buyer_required" in r.required_downstream_checks

    def test_affordability_and_sub_scale_both_present(self):
        r = evaluate_layer0(_full_data_target(ev=50.0))
        assert "affordability" in r.required_downstream_checks
        assert "sub_scale_target_review" in r.required_downstream_checks

    def test_affordability_present_for_mid_cap(self):
        r = evaluate_layer0(_full_data_target(ev=2_000.0))
        assert "affordability" in r.required_downstream_checks


# ---------------------------------------------------------------------------
# 15. affordability_data_required when EV absent (MC fallback only)
# ---------------------------------------------------------------------------

class TestAffordabilityDataRequiredWithMCFallback:

    def test_affordability_data_required_when_ev_none(self):
        # No EV → affordability_data_required
        r = evaluate_layer0(_full_data_target(ev=None, mc=400.0))
        assert "affordability_data_required" in r.required_downstream_checks
        assert "affordability" not in r.required_downstream_checks

    def test_affordability_data_required_even_with_mc_present(self):
        """MC alone is not sufficient for pair affordability (EV is required)."""
        r = evaluate_layer0(_full_data_target(ev=None, mc=600.0))
        assert "affordability_data_required" in r.required_downstream_checks

    def test_small_cap_mc_fallback_no_size_check_override(self):
        """MC fallback should not suppress sub_scale or large_cap checks."""
        # MC = 50 → sub_scale bucket, even with MC-only reference
        r = evaluate_layer0(_full_data_target(ev=None, mc=50.0))
        assert r.target_size.size_bucket == TargetSizeBucket.SUB_SCALE
        assert "sub_scale_target_review" in r.required_downstream_checks
