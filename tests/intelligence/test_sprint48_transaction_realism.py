"""
Sprint 48 — Block 2: TransactionRealismScore

Tests for ma_transaction_realism:
  A. SellerReadinessScore  — activist/strategic_review nuancing
  B. PriceExpectationAlignment — UNKNOWN → neutral
  C. TransactionRealismScore — full pair-level aggregation
  D. Diligence routing — UNKNOWN inputs → is_diligence_required flag, not a block

Design invariants enforced:
  - activist_present RAISES seller openness (not a negative signal)
  - strategic_review_announced is a STRONG POSITIVE timing signal
  - UNKNOWN board_openness / price_expectation / management_language → neutral (no penalty)
  - All UNKNOWN → is_diligence_required=True (route to diligence, not a hard block)
  - ROFR present → friction note in output, NOT a HARD_FAIL
  - TransactionRealismScore is NOT preliminary_transaction_friction (different scope)
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# A. SellerReadinessScore tests
# ---------------------------------------------------------------------------

class TestSellerReadinessScore:
    """Tests for ma_transaction_realism.SellerReadinessScore."""

    def test_activist_present_raises_openness(self):
        """Activist presence should increase seller openness (not lower it)."""
        from bve.intelligence.ma_transaction_realism import compute_seller_readiness

        base = compute_seller_readiness({
            "board_openness": 0.50,
            "management_language": 0.50,
            "strategic_review_announced": False,
            "activist_present": False,
            "prior_deal_rejections": 0,
        })
        with_activist = compute_seller_readiness({
            "board_openness": 0.50,
            "management_language": 0.50,
            "strategic_review_announced": False,
            "activist_present": True,
            "prior_deal_rejections": 0,
        })
        # Activist should raise openness signal, not lower it
        assert with_activist.readiness_score > base.readiness_score

    def test_strategic_review_announced_is_strong_positive(self):
        """Announced strategic review = strong positive timing signal."""
        from bve.intelligence.ma_transaction_realism import compute_seller_readiness

        without = compute_seller_readiness({
            "board_openness": 0.55,
            "management_language": 0.55,
            "strategic_review_announced": False,
            "activist_present": False,
            "prior_deal_rejections": 0,
        })
        with_review = compute_seller_readiness({
            "board_openness": 0.55,
            "management_language": 0.55,
            "strategic_review_announced": True,
            "activist_present": False,
            "prior_deal_rejections": 0,
        })
        assert with_review.readiness_score > without.readiness_score
        assert with_review.readiness_score >= 0.70

    def test_both_activist_and_strategic_review_score_high(self):
        """Both signals together should produce a high readiness score."""
        from bve.intelligence.ma_transaction_realism import compute_seller_readiness

        result = compute_seller_readiness({
            "board_openness": 0.60,
            "management_language": 0.60,
            "strategic_review_announced": True,
            "activist_present": True,
            "prior_deal_rejections": 0,
        })
        assert result.readiness_score >= 0.75

    def test_unknown_board_openness_is_neutral_no_penalty(self):
        """UNKNOWN board_openness must not penalise readiness score."""
        from bve.intelligence.ma_transaction_realism import compute_seller_readiness

        known = compute_seller_readiness({
            "board_openness": 0.55,
            "management_language": 0.55,
            "strategic_review_announced": False,
            "activist_present": False,
            "prior_deal_rejections": 0,
        })
        unknown = compute_seller_readiness({
            "board_openness": None,
            "management_language": 0.55,
            "strategic_review_announced": False,
            "activist_present": False,
            "prior_deal_rejections": 0,
        })
        # Unknown board openness must not score WORSE than known neutral
        assert unknown.readiness_score >= known.readiness_score - 0.05
        # But confidence should be lower
        assert unknown.confidence < known.confidence
        assert "board_openness" in unknown.missing_data

    def test_prior_rejections_reduce_readiness(self):
        """Prior deal rejections reduce readiness score."""
        from bve.intelligence.ma_transaction_realism import compute_seller_readiness

        no_rejection = compute_seller_readiness({
            "board_openness": 0.60,
            "management_language": 0.60,
            "strategic_review_announced": False,
            "activist_present": False,
            "prior_deal_rejections": 0,
        })
        one_rejection = compute_seller_readiness({
            "board_openness": 0.60,
            "management_language": 0.60,
            "strategic_review_announced": False,
            "activist_present": False,
            "prior_deal_rejections": 1,
        })
        assert one_rejection.readiness_score < no_rejection.readiness_score

    def test_all_unknown_inputs_produces_neutral_with_diligence_flag(self):
        """All UNKNOWN → neutral score, is_diligence_required=True."""
        from bve.intelligence.ma_transaction_realism import compute_seller_readiness

        result = compute_seller_readiness({})
        assert result.is_diligence_required is True
        assert result.readiness_score == pytest.approx(0.50, abs=0.10)


# ---------------------------------------------------------------------------
# B. PriceExpectationAlignment tests
# ---------------------------------------------------------------------------

class TestPriceExpectationAlignment:
    """Tests for ma_transaction_realism.PriceExpectationAlignment."""

    def test_aligned_price_expectations_score_high(self):
        from bve.intelligence.ma_transaction_realism import compute_price_alignment

        result = compute_price_alignment({
            "target_price_expectation_premium_pct": 30.0,
            "market_implied_premium_pct": 28.0,
            "recent_comparable_premium_pct": 32.0,
            "acquirer_offer_capacity_premium_pct": 40.0,
        })
        assert result.alignment_score >= 0.70
        assert result.is_affordable is True

    def test_price_far_above_capacity_scores_low(self):
        from bve.intelligence.ma_transaction_realism import compute_price_alignment

        result = compute_price_alignment({
            "target_price_expectation_premium_pct": 120.0,
            "market_implied_premium_pct": 45.0,
            "recent_comparable_premium_pct": 40.0,
            "acquirer_offer_capacity_premium_pct": 50.0,
        })
        assert result.alignment_score <= 0.40
        assert result.is_affordable is False

    def test_unknown_price_expectation_is_neutral(self):
        """Unknown target price expectation must not penalise alignment."""
        from bve.intelligence.ma_transaction_realism import compute_price_alignment

        known_neutral = compute_price_alignment({
            "target_price_expectation_premium_pct": 35.0,
            "market_implied_premium_pct": 35.0,
            "recent_comparable_premium_pct": 35.0,
            "acquirer_offer_capacity_premium_pct": 50.0,
        })
        unknown = compute_price_alignment({
            "target_price_expectation_premium_pct": None,
            "market_implied_premium_pct": 35.0,
            "recent_comparable_premium_pct": 35.0,
            "acquirer_offer_capacity_premium_pct": 50.0,
        })
        assert unknown.alignment_score >= known_neutral.alignment_score - 0.10
        assert unknown.confidence < known_neutral.confidence

    def test_all_price_inputs_unknown_routes_to_diligence(self):
        from bve.intelligence.ma_transaction_realism import compute_price_alignment

        result = compute_price_alignment({})
        assert result.is_diligence_required is True
        assert result.confidence <= 0.50


# ---------------------------------------------------------------------------
# C. TransactionRealismScore tests
# ---------------------------------------------------------------------------

class TestTransactionRealismScore:
    """Tests for ma_transaction_realism.TransactionRealismScore."""

    def _make_strong_inputs(self):
        return {
            "seller_readiness": {
                "board_openness": 0.75,
                "management_language": 0.70,
                "strategic_review_announced": True,
                "activist_present": False,
                "prior_deal_rejections": 0,
            },
            "price_expectation": {
                "target_price_expectation_premium_pct": 35.0,
                "market_implied_premium_pct": 38.0,
                "recent_comparable_premium_pct": 40.0,
                "acquirer_offer_capacity_premium_pct": 55.0,
            },
            "rights_clarity": {
                "rofr_present": False,
                "partner_rights_issue": None,
                "ip_licensing_barrier": None,
            },
        }

    def _make_weak_inputs(self):
        return {
            "seller_readiness": {
                "board_openness": 0.20,
                "management_language": 0.20,
                "strategic_review_announced": False,
                "activist_present": False,
                "prior_deal_rejections": 2,
            },
            "price_expectation": {
                "target_price_expectation_premium_pct": 150.0,
                "market_implied_premium_pct": 45.0,
                "recent_comparable_premium_pct": 40.0,
                "acquirer_offer_capacity_premium_pct": 50.0,
            },
            "rights_clarity": {
                "rofr_present": True,
                "partner_rights_issue": 0.80,
                "ip_licensing_barrier": 0.70,
            },
        }

    def test_strong_inputs_produce_high_realism_score(self):
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism, TransactionRealismScore

        result = compute_transaction_realism(self._make_strong_inputs())
        assert isinstance(result, TransactionRealismScore)
        assert result.realism_score >= 0.65
        assert result.realism_label in {"HIGH", "MODERATE_HIGH"}

    def test_weak_inputs_produce_low_realism_score(self):
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        result = compute_transaction_realism(self._make_weak_inputs())
        assert result.realism_score <= 0.45
        assert result.realism_label in {"LOW", "MODERATE_LOW"}

    def test_rofr_present_adds_friction_not_hard_fail(self):
        """ROFR present should NOT be a hard_fail — it's a friction note."""
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        inputs = dict(self._make_strong_inputs())
        inputs["rights_clarity"] = {"rofr_present": True, "partner_rights_issue": None, "ip_licensing_barrier": None}

        result = compute_transaction_realism(inputs)
        assert result.is_hard_fail is False
        assert "rofr" in " ".join(result.friction_notes).lower()

    def test_all_unknown_inputs_routes_to_diligence_not_block(self):
        """All UNKNOWN → is_diligence_required=True, is_hard_fail=False."""
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        result = compute_transaction_realism({})
        assert result.is_hard_fail is False
        assert result.is_diligence_required is True
        assert result.overall_confidence <= 0.50

    def test_realism_label_options(self):
        """realism_label must be one of the 5 valid labels."""
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        VALID_LABELS = {"HIGH", "MODERATE_HIGH", "MODERATE", "MODERATE_LOW", "LOW"}
        for inputs in [self._make_strong_inputs(), self._make_weak_inputs(), {}]:
            r = compute_transaction_realism(inputs)
            assert r.realism_label in VALID_LABELS

    def test_strategic_review_dramatically_improves_realism(self):
        """strategic_review_announced = True should substantially boost realism."""
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        base_inputs = {
            "seller_readiness": {
                "board_openness": 0.55,
                "management_language": 0.55,
                "strategic_review_announced": False,
                "activist_present": False,
                "prior_deal_rejections": 0,
            },
            "price_expectation": {
                "target_price_expectation_premium_pct": 35.0,
                "market_implied_premium_pct": 35.0,
                "recent_comparable_premium_pct": 35.0,
                "acquirer_offer_capacity_premium_pct": 50.0,
            },
            "rights_clarity": {"rofr_present": False, "partner_rights_issue": None, "ip_licensing_barrier": None},
        }
        review_inputs = dict(base_inputs)
        review_inputs["seller_readiness"] = dict(base_inputs["seller_readiness"])
        review_inputs["seller_readiness"]["strategic_review_announced"] = True

        result_base = compute_transaction_realism(base_inputs)
        result_review = compute_transaction_realism(review_inputs)

        assert result_review.realism_score > result_base.realism_score

    def test_transaction_realism_exposes_seller_readiness_sub_score(self):
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        result = compute_transaction_realism(self._make_strong_inputs())
        assert hasattr(result, "seller_readiness_score")
        assert 0.0 <= result.seller_readiness_score <= 1.0

    def test_transaction_realism_exposes_price_alignment_sub_score(self):
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        result = compute_transaction_realism(self._make_strong_inputs())
        assert hasattr(result, "price_alignment_score")
        assert 0.0 <= result.price_alignment_score <= 1.0

    def test_unknown_inputs_lower_confidence_not_score(self):
        """UNKNOWN inputs → lower confidence, not lower score."""
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        full_inputs = self._make_strong_inputs()
        partial_inputs = {
            "seller_readiness": {
                "board_openness": None,  # UNKNOWN
                "management_language": None,  # UNKNOWN
                "strategic_review_announced": True,  # known positive
                "activist_present": False,
                "prior_deal_rejections": 0,
            },
            "price_expectation": {
                "target_price_expectation_premium_pct": None,  # UNKNOWN
                "market_implied_premium_pct": 38.0,
                "recent_comparable_premium_pct": 40.0,
                "acquirer_offer_capacity_premium_pct": 55.0,
            },
            "rights_clarity": {"rofr_present": False, "partner_rights_issue": None, "ip_licensing_barrier": None},
        }
        result_full = compute_transaction_realism(full_inputs)
        result_partial = compute_transaction_realism(partial_inputs)

        # Score should not be WORSE just because of unknown fields
        assert result_partial.realism_score >= result_full.realism_score - 0.15
        # Confidence should be lower
        assert result_partial.overall_confidence < result_full.overall_confidence


# ---------------------------------------------------------------------------
# D. Diligence routing tests
# ---------------------------------------------------------------------------

class TestDiligenceRouting:
    """UNKNOWN inputs should route to diligence, not hard-block."""

    def test_attractive_target_with_unknown_seller_routes_to_diligence(self):
        """High realism potential blocked by unknown seller → is_diligence_required=True."""
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        inputs = {
            "seller_readiness": {
                "board_openness": None,
                "management_language": None,
                "strategic_review_announced": None,
                "activist_present": None,
                "prior_deal_rejections": None,
            },
            "price_expectation": {
                "target_price_expectation_premium_pct": 35.0,
                "market_implied_premium_pct": 35.0,
                "recent_comparable_premium_pct": 35.0,
                "acquirer_offer_capacity_premium_pct": 55.0,
            },
            "rights_clarity": {"rofr_present": False, "partner_rights_issue": None, "ip_licensing_barrier": None},
        }
        result = compute_transaction_realism(inputs)
        assert result.is_diligence_required is True
        assert result.is_hard_fail is False

    def test_diligence_items_populated_for_unknown_fields(self):
        """Missing fields should appear in diligence_items."""
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        result = compute_transaction_realism({
            "seller_readiness": {"board_openness": None, "management_language": None,
                                  "strategic_review_announced": False, "activist_present": False, "prior_deal_rejections": 0},
            "price_expectation": {},
            "rights_clarity": {},
        })
        assert len(result.diligence_items) > 0
