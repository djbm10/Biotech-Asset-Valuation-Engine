"""
Sprint 51 — Block 5: Scanner/API Integration

Tests for exposing Block 1-4 outputs on MAProbabilityRow:
  - New optional fields on MAProbabilityRow (all None by default)
  - enrich_row_with_buyer_thesis() populates new fields without breaking existing ones
  - RANK_ONLY mode when segment_n < minimum_n
  - SHOW_BAND mode when segment_n >= minimum_n
  - Backward compat: row without enrichment still validates
"""
from __future__ import annotations

import pytest
from datetime import date


def _make_minimal_row(**overrides):
    """Build a minimal valid MAProbabilityRow for testing."""
    from bve.intelligence.ma_probability import MAProbabilityRow
    defaults = {
        "asset_id": "test-001",
        "mna_probability_score": 0.65,
        "mna_targetability_score": 0.65,
        "p_acquisition": 0.65,
        "raw_probability": 0.65,
        "above_alert_threshold": False,
        "score_version": "v1.0",
        "best_acquirer_id": "pfizer",
        "best_acquirer_name": "Pfizer",
        "best_acquirer_fit_score": 0.70,
        "valuation_discount_score": 0.50,
        "strategic_fit_score": 0.60,
        "de_risking_stage_score": 0.55,
        "capital_vulnerability_score": 0.40,
        "scarcity_score": 0.65,
        "scarcity_peer_count": 3,
        "scarcity_bucket": "low",
        "vulnerability_score": 0.45,
        "explanation": "Test row",
    }
    defaults.update(overrides)
    return MAProbabilityRow(**defaults)


class TestMAProbabilityRowNewFields:
    """New optional fields on MAProbabilityRow are None by default."""

    def test_buyer_thesis_tier_defaults_none(self):
        from bve.intelligence.ma_probability import MAProbabilityRow
        row = _make_minimal_row()
        assert row.buyer_thesis_tier is None

    def test_transaction_realism_label_defaults_none(self):
        from bve.intelligence.ma_probability import MAProbabilityRow
        row = _make_minimal_row()
        assert row.transaction_realism_label is None

    def test_recommended_structure_defaults_none(self):
        from bve.intelligence.ma_probability import MAProbabilityRow
        row = _make_minimal_row()
        assert row.recommended_deal_structure is None

    def test_probability_band_display_defaults_none(self):
        from bve.intelligence.ma_probability import MAProbabilityRow
        row = _make_minimal_row()
        assert row.probability_band_display is None

    def test_existing_row_still_validates_without_new_fields(self):
        """Backward compat: existing row construction must still work."""
        row = _make_minimal_row()
        assert row.mna_probability_score == 0.65


class TestEnrichRowWithBuyerThesis:
    """enrich_row_with_buyer_thesis() populates new fields."""

    def _make_mandate_inputs(self):
        return {
            "bd_guidance_statements": [
                {"text": "Active BD mandate.", "date": "2026-01-10", "source": "Conf"}
            ],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.80,
            "recent_ma_cadence": 0.75,
        }

    def _make_conflict_inputs(self):
        return {
            "existing_pipeline_overlap": 0.10,
            "commercial_channel_conflict": 0.10,
            "partner_rofr_present": False,
            "pending_portfolio_acquisition": False,
        }

    def _make_realism_inputs(self):
        return {
            "seller_readiness": {
                "board_openness": 0.70,
                "management_language": 0.65,
                "strategic_review_announced": True,
                "activist_present": False,
                "prior_deal_rejections": 0,
            },
            "price_expectation": {
                "target_price_expectation_premium_pct": 35.0,
                "market_implied_premium_pct": 35.0,
                "recent_comparable_premium_pct": 38.0,
                "acquirer_offer_capacity_premium_pct": 55.0,
            },
            "rights_clarity": {"rofr_present": False, "partner_rights_issue": None, "ip_licensing_barrier": None},
        }

    def test_enrich_populates_buyer_thesis_tier(self):
        from bve.intelligence.ma_probability import enrich_row_with_buyer_thesis

        row = _make_minimal_row()
        enriched = enrich_row_with_buyer_thesis(
            row,
            mandate_inputs=self._make_mandate_inputs(),
            conflict_inputs=self._make_conflict_inputs(),
            relationship_inputs={},
            realism_inputs=self._make_realism_inputs(),
        )
        assert enriched.buyer_thesis_tier is not None
        assert enriched.buyer_thesis_tier in {"strong_buy", "buy", "monitor", "pass"}

    def test_enrich_populates_transaction_realism_label(self):
        from bve.intelligence.ma_probability import enrich_row_with_buyer_thesis

        row = _make_minimal_row()
        enriched = enrich_row_with_buyer_thesis(
            row,
            mandate_inputs=self._make_mandate_inputs(),
            conflict_inputs=self._make_conflict_inputs(),
            relationship_inputs={},
            realism_inputs=self._make_realism_inputs(),
        )
        assert enriched.transaction_realism_label is not None
        assert enriched.transaction_realism_label in {"HIGH", "MODERATE_HIGH", "MODERATE", "MODERATE_LOW", "LOW"}

    def test_enrich_populates_recommended_structure(self):
        from bve.intelligence.ma_probability import enrich_row_with_buyer_thesis

        row = _make_minimal_row()
        enriched = enrich_row_with_buyer_thesis(
            row,
            mandate_inputs=self._make_mandate_inputs(),
            conflict_inputs=self._make_conflict_inputs(),
            relationship_inputs={},
            realism_inputs=self._make_realism_inputs(),
        )
        assert enriched.recommended_deal_structure is not None

    def test_enrich_preserves_existing_fields(self):
        """Enrichment must not change existing scoring fields."""
        from bve.intelligence.ma_probability import enrich_row_with_buyer_thesis

        row = _make_minimal_row(mna_probability_score=0.72)
        enriched = enrich_row_with_buyer_thesis(
            row,
            mandate_inputs=self._make_mandate_inputs(),
            conflict_inputs=self._make_conflict_inputs(),
            relationship_inputs={},
            realism_inputs=self._make_realism_inputs(),
        )
        assert enriched.mna_probability_score == 0.72
        assert enriched.score_version == row.score_version

    def test_enrich_with_rank_only_segment(self):
        """When segment_outcomes has < minimum_n → probability_band_display shows RANK_ONLY."""
        from bve.intelligence.ma_probability import enrich_row_with_buyer_thesis

        row = _make_minimal_row()
        enriched = enrich_row_with_buyer_thesis(
            row,
            mandate_inputs=self._make_mandate_inputs(),
            conflict_inputs=self._make_conflict_inputs(),
            relationship_inputs={},
            realism_inputs=self._make_realism_inputs(),
            segment_outcomes=[1, 0, 1],  # N=3 < minimum_n=10
        )
        assert enriched.probability_band_display is not None
        assert "rank" in enriched.probability_band_display.lower() or "insufficient" in enriched.probability_band_display.lower()

    def test_enrich_with_show_band_segment(self):
        """When segment_outcomes has >= minimum_n → probability_band_display shows a range."""
        from bve.intelligence.ma_probability import enrich_row_with_buyer_thesis

        row = _make_minimal_row()
        outcomes = [1] * 9 + [0] * 6  # N=15 >= minimum_n=10
        enriched = enrich_row_with_buyer_thesis(
            row,
            mandate_inputs=self._make_mandate_inputs(),
            conflict_inputs=self._make_conflict_inputs(),
            relationship_inputs={},
            realism_inputs=self._make_realism_inputs(),
            segment_outcomes=outcomes,
        )
        assert enriched.probability_band_display is not None
        assert "%" in enriched.probability_band_display  # should show a probability

    def test_enrich_without_segment_outcomes_no_band_display(self):
        """No segment_outcomes → probability_band_display is None."""
        from bve.intelligence.ma_probability import enrich_row_with_buyer_thesis

        row = _make_minimal_row()
        enriched = enrich_row_with_buyer_thesis(
            row,
            mandate_inputs=self._make_mandate_inputs(),
            conflict_inputs=self._make_conflict_inputs(),
            relationship_inputs={},
            realism_inputs=self._make_realism_inputs(),
        )
        assert enriched.probability_band_display is None
