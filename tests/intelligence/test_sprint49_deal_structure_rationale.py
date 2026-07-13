"""
Sprint 49 — Block 3: DealStructureRationale

Tests for ma_deal_structure_rationale:
  - Connects BuyerTargetThesis + TransactionRealismScore → recommended deal structure
  - STRONG_BUY + HIGH realism → full acquisition recommendation
  - PASS thesis → no_action
  - LOW realism but BUY thesis → option_to_acquire or structured approach
  - UNKNOWN realism → diligence-first recommendation
  - rationale_text must be non-empty human-readable string
  - DealStructureRationale exposes confidence from both inputs
"""
from __future__ import annotations

import pytest


def _make_thesis(pipeline_gap=0.80, recent_ma=0.75, overlap=0.05, sr_announced=True):
    from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score
    from bve.intelligence.ma_internal_conflict import compute_internal_conflict
    from bve.intelligence.ma_relationship_history import compute_relationship_history
    from bve.intelligence.ma_buyer_thesis import build_buyer_target_thesis

    mandate = compute_buyer_mandate_score({
        "bd_guidance_statements": [{"text": "Active BD mandate.", "date": "2026-01-10", "source": "Conf"}] if pipeline_gap > 0.6 else [],
        "rd_day_priority_areas": ["oncology"],
        "pipeline_gap_severity": pipeline_gap,
        "recent_ma_cadence": recent_ma,
    })
    conflict = compute_internal_conflict({
        "existing_pipeline_overlap": overlap,
        "commercial_channel_conflict": overlap * 0.8,
        "partner_rofr_present": False,
        "pending_portfolio_acquisition": False,
    })
    relationship = compute_relationship_history(
        {
            "prior_partnership": True,
            "partnership_type": "option_to_acquire",
            "acquisition_option": True,
            "relationship_recency_years": 1.0,
            "prior_deal_attempts": 0,
        }
    )
    return build_buyer_target_thesis(mandate_score=mandate, conflict_score=conflict, relationship_score=relationship)


def _make_realism(seller_open=0.75, sr_announced=True, price_gap=0, capacity=55):
    from bve.intelligence.ma_transaction_realism import compute_transaction_realism
    return compute_transaction_realism({
        "seller_readiness": {
            "board_openness": seller_open,
            "management_language": seller_open * 0.90,
            "strategic_review_announced": sr_announced,
            "activist_present": False,
            "prior_deal_rejections": 0,
        },
        "price_expectation": {
            "target_price_expectation_premium_pct": 35.0 + price_gap,
            "market_implied_premium_pct": 35.0,
            "recent_comparable_premium_pct": 38.0,
            "acquirer_offer_capacity_premium_pct": capacity,
        },
        "rights_clarity": {"rofr_present": False, "partner_rights_issue": None, "ip_licensing_barrier": None},
    })


class TestDealStructureRationale:

    def test_strong_buy_high_realism_recommends_full_acquisition(self):
        from bve.intelligence.ma_deal_structure_rationale import build_deal_structure_rationale, RecommendedStructure

        thesis = _make_thesis(pipeline_gap=0.90, recent_ma=0.85, overlap=0.05)
        realism = _make_realism(seller_open=0.80, sr_announced=True)

        result = build_deal_structure_rationale(thesis=thesis, realism=realism)
        assert result.recommended_structure in {
            RecommendedStructure.FULL_ACQUISITION,
            RecommendedStructure.STRUCTURED_ACQUISITION_WITH_MILESTONES,
        }

    def test_pass_thesis_recommends_no_action(self):
        from bve.intelligence.ma_deal_structure_rationale import build_deal_structure_rationale, RecommendedStructure

        # Force PASS thesis via blocking conflict
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score
        from bve.intelligence.ma_internal_conflict import compute_internal_conflict
        from bve.intelligence.ma_relationship_history import compute_relationship_history
        from bve.intelligence.ma_buyer_thesis import build_buyer_target_thesis

        mandate = compute_buyer_mandate_score({
            "bd_guidance_statements": [{"text": "Active BD.", "date": "2026-01-10", "source": "Conf"}],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.85,
            "recent_ma_cadence": 0.80,
        })
        conflict = compute_internal_conflict({
            "existing_pipeline_overlap": 0.95,
            "commercial_channel_conflict": 0.90,
            "partner_rofr_present": True,
            "pending_portfolio_acquisition": True,
        })
        relationship = compute_relationship_history({})
        pass_thesis = build_buyer_target_thesis(
            mandate_score=mandate, conflict_score=conflict, relationship_score=relationship
        )
        realism = _make_realism(seller_open=0.80, sr_announced=True)

        result = build_deal_structure_rationale(thesis=pass_thesis, realism=realism)
        assert result.recommended_structure == RecommendedStructure.NO_ACTION

    def test_buy_thesis_low_realism_recommends_option_or_diligence(self):
        from bve.intelligence.ma_deal_structure_rationale import build_deal_structure_rationale, RecommendedStructure

        thesis = _make_thesis(pipeline_gap=0.70, recent_ma=0.65, overlap=0.10)
        realism = _make_realism(seller_open=0.30, sr_announced=False, price_gap=60)  # low realism

        result = build_deal_structure_rationale(thesis=thesis, realism=realism)
        assert result.recommended_structure in {
            RecommendedStructure.OPTION_TO_ACQUIRE,
            RecommendedStructure.DILIGENCE_FIRST,
            RecommendedStructure.MONITOR_ONLY,
        }

    def test_rationale_text_is_non_empty(self):
        from bve.intelligence.ma_deal_structure_rationale import build_deal_structure_rationale

        thesis = _make_thesis()
        realism = _make_realism()
        result = build_deal_structure_rationale(thesis=thesis, realism=realism)
        assert result.rationale_text != ""
        assert len(result.rationale_text) > 20

    def test_confidence_reflects_both_inputs(self):
        from bve.intelligence.ma_deal_structure_rationale import build_deal_structure_rationale
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        thesis = _make_thesis()
        # Low confidence realism (all unknown)
        low_conf_realism = compute_transaction_realism({})
        high_conf_realism = _make_realism()

        result_low = build_deal_structure_rationale(thesis=thesis, realism=low_conf_realism)
        result_high = build_deal_structure_rationale(thesis=thesis, realism=high_conf_realism)

        assert result_high.overall_confidence > result_low.overall_confidence

    def test_rofr_present_recommends_structured_approach(self):
        """ROFR present should steer toward option or structured deal, not full acquisition."""
        from bve.intelligence.ma_deal_structure_rationale import build_deal_structure_rationale, RecommendedStructure
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        thesis = _make_thesis(pipeline_gap=0.85, recent_ma=0.80)
        realism_with_rofr = compute_transaction_realism({
            "seller_readiness": {
                "board_openness": 0.70, "management_language": 0.70,
                "strategic_review_announced": True, "activist_present": False, "prior_deal_rejections": 0,
            },
            "price_expectation": {
                "target_price_expectation_premium_pct": 35.0, "market_implied_premium_pct": 35.0,
                "recent_comparable_premium_pct": 38.0, "acquirer_offer_capacity_premium_pct": 55.0,
            },
            "rights_clarity": {"rofr_present": True, "partner_rights_issue": None, "ip_licensing_barrier": None},
        })
        result = build_deal_structure_rationale(thesis=thesis, realism=realism_with_rofr)
        # Should NOT be a clean full acquisition (ROFR adds complexity)
        assert result.recommended_structure != RecommendedStructure.FULL_ACQUISITION or result.caveats

    def test_output_has_expected_fields(self):
        from bve.intelligence.ma_deal_structure_rationale import DealStructureRationale, build_deal_structure_rationale

        thesis = _make_thesis()
        realism = _make_realism()
        result = build_deal_structure_rationale(thesis=thesis, realism=realism)
        assert isinstance(result, DealStructureRationale)
        assert hasattr(result, "recommended_structure")
        assert hasattr(result, "rationale_text")
        assert hasattr(result, "overall_confidence")
        assert hasattr(result, "caveats")
        assert hasattr(result, "diligence_items")

    def test_diligence_items_populated_from_unknown_inputs(self):
        from bve.intelligence.ma_deal_structure_rationale import build_deal_structure_rationale
        from bve.intelligence.ma_transaction_realism import compute_transaction_realism

        thesis = _make_thesis()
        partial_realism = compute_transaction_realism({
            "seller_readiness": {"board_openness": None, "management_language": None,
                                  "strategic_review_announced": False, "activist_present": False,
                                  "prior_deal_rejections": 0},
            "price_expectation": {}, "rights_clarity": {},
        })
        result = build_deal_structure_rationale(thesis=thesis, realism=partial_realism)
        assert len(result.diligence_items) > 0
