"""Tests for Layer 0C — Target-Size Pre-Screen (ma_target_size.py).

Coverage:
  1. Bucket classification — all five buckets + unknown
  2. Reference source precedence (EV > MC; MC fallback; neither = unknown)
  3. Negative EV (net-cash companies) handled without error
  4. Boundary values at exact thresholds
  5. Buyer-universe flags (requires_large_cap_buyer, mega_deal_flag,
     sub_scale_flag, small_cap_flag)
  6. Minimum buyer capacity by bucket
  7. Data gaps list population
  8. Rationale text content
  9. Result is frozen (immutable)
 10. No score effect — module exposes no multiplier or cap
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_target_size import (
    TargetSizeBucket,
    TargetSizeInput,
    TargetSizeResult,
    compute_target_size,
    _SIZE_THRESHOLDS,
    _MIN_BUYER_CAPACITY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inp(
    ev: float | None = None,
    mc: float | None = None,
    target_id: str = "TGT",
) -> TargetSizeInput:
    return TargetSizeInput(
        target_id=target_id,
        enterprise_value_millions=ev,
        market_cap_millions=mc,
    )


# ---------------------------------------------------------------------------
# 1. Bucket classification
# ---------------------------------------------------------------------------

class TestBucketClassification:

    def test_sub_scale_below_100m(self):
        r = compute_target_size(_inp(ev=50.0))
        assert r.size_bucket == TargetSizeBucket.SUB_SCALE

    def test_small_cap_100m_to_500m(self):
        r = compute_target_size(_inp(ev=300.0))
        assert r.size_bucket == TargetSizeBucket.SMALL_CAP

    def test_mid_cap_500m_to_5b(self):
        r = compute_target_size(_inp(ev=2_000.0))
        assert r.size_bucket == TargetSizeBucket.MID_CAP

    def test_large_cap_5b_to_25b(self):
        r = compute_target_size(_inp(ev=10_000.0))
        assert r.size_bucket == TargetSizeBucket.LARGE_CAP

    def test_mega_deal_above_25b(self):
        r = compute_target_size(_inp(ev=50_000.0))
        assert r.size_bucket == TargetSizeBucket.MEGA_DEAL

    def test_unknown_when_no_data(self):
        r = compute_target_size(_inp())
        assert r.size_bucket == TargetSizeBucket.UNKNOWN


# ---------------------------------------------------------------------------
# 2. Reference source precedence
# ---------------------------------------------------------------------------

class TestReferenceSourcePrecedence:

    def test_ev_preferred_over_mc(self):
        # EV=2000 → mid-cap; MC=50 → would be sub-scale if MC used
        r = compute_target_size(_inp(ev=2_000.0, mc=50.0))
        assert r.reference_source == "enterprise_value"
        assert r.size_bucket == TargetSizeBucket.MID_CAP

    def test_mc_used_when_ev_absent(self):
        r = compute_target_size(_inp(mc=300.0))
        assert r.reference_source == "market_cap"
        assert r.size_bucket == TargetSizeBucket.SMALL_CAP

    def test_none_source_when_both_absent(self):
        r = compute_target_size(_inp())
        assert r.reference_source == "none"
        assert r.reference_value_millions is None

    def test_reference_value_matches_ev(self):
        r = compute_target_size(_inp(ev=1_500.0))
        assert r.reference_value_millions == pytest.approx(1_500.0)

    def test_reference_value_matches_mc_when_ev_absent(self):
        r = compute_target_size(_inp(mc=400.0))
        assert r.reference_value_millions == pytest.approx(400.0)


# ---------------------------------------------------------------------------
# 3. Negative EV (net-cash companies)
# ---------------------------------------------------------------------------

class TestNegativeEV:

    def test_negative_ev_maps_to_sub_scale(self):
        # Net-cash company: EV = -50M → abs(-50) = 50 < 100 → SUB_SCALE
        r = compute_target_size(_inp(ev=-50.0))
        assert r.size_bucket == TargetSizeBucket.SUB_SCALE

    def test_negative_ev_does_not_raise(self):
        r = compute_target_size(_inp(ev=-500.0))
        assert r.size_bucket is not None

    def test_negative_ev_reference_value_preserved(self):
        r = compute_target_size(_inp(ev=-150.0))
        assert r.reference_value_millions == pytest.approx(-150.0)


# ---------------------------------------------------------------------------
# 4. Boundary values
# ---------------------------------------------------------------------------

class TestBoundaryValues:

    def test_exactly_100m_is_small_cap_not_sub_scale(self):
        # < 100 → sub_scale; ≥ 100 → small_cap
        r = compute_target_size(_inp(ev=100.0))
        assert r.size_bucket == TargetSizeBucket.SMALL_CAP

    def test_just_below_100m_is_sub_scale(self):
        r = compute_target_size(_inp(ev=99.99))
        assert r.size_bucket == TargetSizeBucket.SUB_SCALE

    def test_exactly_500m_is_mid_cap(self):
        r = compute_target_size(_inp(ev=500.0))
        assert r.size_bucket == TargetSizeBucket.MID_CAP

    def test_just_below_500m_is_small_cap(self):
        r = compute_target_size(_inp(ev=499.99))
        assert r.size_bucket == TargetSizeBucket.SMALL_CAP

    def test_exactly_5000m_is_large_cap(self):
        r = compute_target_size(_inp(ev=5_000.0))
        assert r.size_bucket == TargetSizeBucket.LARGE_CAP

    def test_just_below_5000m_is_mid_cap(self):
        r = compute_target_size(_inp(ev=4_999.99))
        assert r.size_bucket == TargetSizeBucket.MID_CAP

    def test_exactly_25000m_is_mega_deal(self):
        r = compute_target_size(_inp(ev=25_000.0))
        assert r.size_bucket == TargetSizeBucket.MEGA_DEAL

    def test_just_below_25000m_is_large_cap(self):
        r = compute_target_size(_inp(ev=24_999.99))
        assert r.size_bucket == TargetSizeBucket.LARGE_CAP


# ---------------------------------------------------------------------------
# 5. Buyer-universe flags
# ---------------------------------------------------------------------------

class TestBuyerUniverseFlags:

    def test_sub_scale_flag_true_below_100m(self):
        r = compute_target_size(_inp(ev=50.0))
        assert r.sub_scale_flag is True
        assert r.small_cap_flag is False
        assert r.requires_large_cap_buyer is False
        assert r.mega_deal_flag is False

    def test_small_cap_flag_true_100m_to_500m(self):
        r = compute_target_size(_inp(ev=300.0))
        assert r.small_cap_flag is True
        assert r.sub_scale_flag is False
        assert r.requires_large_cap_buyer is False
        assert r.mega_deal_flag is False

    def test_mid_cap_all_flags_false(self):
        r = compute_target_size(_inp(ev=2_000.0))
        assert r.sub_scale_flag is False
        assert r.small_cap_flag is False
        assert r.requires_large_cap_buyer is False
        assert r.mega_deal_flag is False

    def test_large_cap_requires_large_cap_buyer(self):
        r = compute_target_size(_inp(ev=10_000.0))
        assert r.requires_large_cap_buyer is True
        assert r.mega_deal_flag is False
        assert r.sub_scale_flag is False

    def test_mega_deal_sets_both_mega_and_large_cap_flags(self):
        r = compute_target_size(_inp(ev=50_000.0))
        assert r.mega_deal_flag is True
        assert r.requires_large_cap_buyer is True

    def test_unknown_all_flags_false(self):
        r = compute_target_size(_inp())
        assert r.sub_scale_flag is False
        assert r.small_cap_flag is False
        assert r.requires_large_cap_buyer is False
        assert r.mega_deal_flag is False

    def test_small_cap_flag_is_not_a_penalty_signal(self):
        """Small-cap is a valid M&A target — the flag is informational only."""
        r = compute_target_size(_inp(ev=200.0))
        # No score multiplier or cap exists on TargetSizeResult
        assert not hasattr(r, "score_multiplier")
        assert not hasattr(r, "mna_probability_cap")
        assert not hasattr(r, "penalty")


# ---------------------------------------------------------------------------
# 6. Minimum buyer capacity
# ---------------------------------------------------------------------------

class TestMinimumBuyerCapacity:

    def test_sub_scale_no_minimum(self):
        r = compute_target_size(_inp(ev=50.0))
        assert r.minimum_buyer_capacity_needed_millions is None

    def test_small_cap_minimum_135m(self):
        r = compute_target_size(_inp(ev=300.0))
        assert r.minimum_buyer_capacity_needed_millions == pytest.approx(135.0)

    def test_mid_cap_minimum_675m(self):
        r = compute_target_size(_inp(ev=2_000.0))
        assert r.minimum_buyer_capacity_needed_millions == pytest.approx(675.0)

    def test_large_cap_minimum_6750m(self):
        r = compute_target_size(_inp(ev=10_000.0))
        assert r.minimum_buyer_capacity_needed_millions == pytest.approx(6_750.0)

    def test_mega_deal_minimum_33750m(self):
        r = compute_target_size(_inp(ev=50_000.0))
        assert r.minimum_buyer_capacity_needed_millions == pytest.approx(33_750.0)

    def test_unknown_no_minimum(self):
        r = compute_target_size(_inp())
        assert r.minimum_buyer_capacity_needed_millions is None


# ---------------------------------------------------------------------------
# 7. Data gaps
# ---------------------------------------------------------------------------

class TestDataGaps:

    def test_no_data_gaps_when_ev_present(self):
        r = compute_target_size(_inp(ev=1_000.0))
        assert r.data_gaps == []

    def test_data_gap_when_only_mc_present(self):
        r = compute_target_size(_inp(mc=300.0))
        assert any("enterprise_value_missing" in g for g in r.data_gaps)

    def test_two_gaps_when_both_absent(self):
        r = compute_target_size(_inp())
        assert any("enterprise_value_missing" in g for g in r.data_gaps)
        assert any("market_cap_missing" in g for g in r.data_gaps)

    def test_mc_fallback_note_in_gaps(self):
        r = compute_target_size(_inp(mc=500.0))
        assert any("proxy" in g or "market_cap" in g for g in r.data_gaps)


# ---------------------------------------------------------------------------
# 8. Rationale text
# ---------------------------------------------------------------------------

class TestRationaleText:

    def test_rationale_non_empty(self):
        for ev in [50.0, 300.0, 2_000.0, 10_000.0, 50_000.0]:
            r = compute_target_size(_inp(ev=ev))
            assert r.rationale != ""

    def test_unknown_rationale_present(self):
        r = compute_target_size(_inp())
        assert r.rationale != ""

    def test_rationale_contains_value(self):
        r = compute_target_size(_inp(ev=2_000.0))
        assert "2,000" in r.rationale or "2000" in r.rationale

    def test_rationale_mentions_ev_source(self):
        r = compute_target_size(_inp(ev=300.0))
        assert "EV" in r.rationale

    def test_rationale_mentions_mc_when_mc_used(self):
        r = compute_target_size(_inp(mc=300.0))
        assert "MC" in r.rationale

    def test_sub_scale_rationale_mentions_bolt_on(self):
        r = compute_target_size(_inp(ev=50.0))
        assert "bolt-on" in r.rationale.lower() or "sub-scale" in r.rationale.lower()

    def test_mega_deal_rationale_mentions_pharma(self):
        r = compute_target_size(_inp(ev=50_000.0))
        assert "pharma" in r.rationale.lower() or "mega" in r.rationale.lower()


# ---------------------------------------------------------------------------
# 9. Immutability
# ---------------------------------------------------------------------------

class TestImmutability:

    def test_result_is_frozen(self):
        r = compute_target_size(_inp(ev=500.0))
        with pytest.raises(Exception):
            r.size_bucket = TargetSizeBucket.SUB_SCALE  # type: ignore[misc]

    def test_input_is_frozen(self):
        inp = _inp(ev=500.0)
        with pytest.raises(Exception):
            inp.enterprise_value_millions = 100.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 10. No score effect
# ---------------------------------------------------------------------------

class TestNoScoreEffect:

    def test_result_has_no_score_multiplier(self):
        r = compute_target_size(_inp(ev=500.0))
        assert not hasattr(r, "score_multiplier")

    def test_result_has_no_probability_cap(self):
        r = compute_target_size(_inp(ev=500.0))
        assert not hasattr(r, "mna_probability_cap")

    def test_result_has_no_penalty(self):
        r = compute_target_size(_inp(ev=500.0))
        assert not hasattr(r, "penalty_multiplier")
        assert not hasattr(r, "penalty")

    def test_module_exports_no_scoring_function(self):
        """The module must not export any function that returns a score penalty."""
        import bve.intelligence.ma_target_size as mod
        export_names = [n for n in dir(mod) if not n.startswith("__")]
        # The only callable that computes something is compute_target_size
        # It returns TargetSizeResult which has no score fields
        assert "compute_target_size" in export_names
        assert "score_multiplier" not in export_names
        assert "penalty_multiplier" not in export_names


# ---------------------------------------------------------------------------
# 11. Consistency invariants
# ---------------------------------------------------------------------------

class TestInvariants:

    def test_all_buckets_have_min_capacity_entry(self):
        for bucket in TargetSizeBucket:
            assert bucket in _MIN_BUYER_CAPACITY

    def test_size_thresholds_are_monotone_increasing(self):
        uppers = [upper for upper, _ in _SIZE_THRESHOLDS]
        for i in range(len(uppers) - 1):
            assert uppers[i] < uppers[i + 1]

    def test_last_threshold_is_inf(self):
        last_upper, _ = _SIZE_THRESHOLDS[-1]
        assert last_upper == float("inf")

    def test_requires_large_cap_buyer_iff_large_or_mega(self):
        for bucket, upper in [
            (TargetSizeBucket.SUB_SCALE, 50.0),
            (TargetSizeBucket.SMALL_CAP, 300.0),
            (TargetSizeBucket.MID_CAP, 2_000.0),
            (TargetSizeBucket.LARGE_CAP, 10_000.0),
            (TargetSizeBucket.MEGA_DEAL, 50_000.0),
        ]:
            r = compute_target_size(_inp(ev=upper))
            expected = bucket in (TargetSizeBucket.LARGE_CAP, TargetSizeBucket.MEGA_DEAL)
            assert r.requires_large_cap_buyer == expected, (
                f"requires_large_cap_buyer should be {expected} for {bucket.value}"
            )

    def test_exactly_one_size_flag_true_per_bucket(self):
        """At most one of sub_scale/small_cap/mega_deal/requires_large_cap is True
        in a mutually exclusive way for the five non-unknown buckets."""
        cases = [
            (50.0,     True,  False, False, False),   # SUB_SCALE
            (300.0,    False, True,  False, False),   # SMALL_CAP
            (2_000.0,  False, False, False, False),   # MID_CAP
            (10_000.0, False, False, True,  False),   # LARGE_CAP (requires_large_cap)
            (50_000.0, False, False, True,  True),    # MEGA_DEAL (requires + mega)
        ]
        for ev, sub, small, large, mega in cases:
            r = compute_target_size(_inp(ev=ev))
            assert r.sub_scale_flag == sub,  f"sub_scale_flag wrong for ev={ev}"
            assert r.small_cap_flag == small, f"small_cap_flag wrong for ev={ev}"
            assert r.requires_large_cap_buyer == large, f"requires_large_cap_buyer wrong for ev={ev}"
            assert r.mega_deal_flag == mega,  f"mega_deal_flag wrong for ev={ev}"
