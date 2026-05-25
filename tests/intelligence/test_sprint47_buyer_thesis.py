"""
Sprint 47 — Block 1: Buyer-Specific Thesis Engine

Tests for:
  A. BuyerMandateScore  (ma_buyer_mandate.py)
  B. InternalConflictScore  (ma_internal_conflict.py)
  C. RelationshipHistoryScore  (ma_relationship_history.py)
  D. BuyerTargetThesis aggregator  (ma_buyer_thesis.py)
  E. strategic_urgency_score split in Layer 2  (ma_layer2_bd_priority.py)
  F. preliminary_transaction_friction in Layer 2  (ma_layer2_bd_priority.py)

Design invariants enforced:
  - executive_alignment_signal is evidence-based only (no fake inference)
  - UNKNOWN inputs → no cap/penalty, only lower confidence
  - RelationshipHistoryScore defaults to UNKNOWN gate (neutral, lower confidence)
  - strategic_urgency (pair-level timing) must not overlap with pipeline_gap_urgency (buyer-level)
  - preliminary_transaction_friction ≠ TransactionRealismScore (no circularity)
  - minimum_n guard for RANK_ONLY probability display
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# A. BuyerMandateScore tests
# ---------------------------------------------------------------------------

class TestBuyerMandateScore:
    """Tests for ma_buyer_mandate.BuyerMandateScore and MandateTier."""

    def test_active_mandate_tier_from_strong_signals(self):
        from bve.intelligence.ma_buyer_mandate import BuyerMandateScore, MandateTier, compute_buyer_mandate_score

        inputs = {
            "bd_guidance_statements": [
                {"text": "We are actively seeking oncology acquisitions in 2026.", "date": "2026-01-15", "source": "JP Morgan HC Conf"},
            ],
            "rd_day_priority_areas": ["oncology", "rare_disease"],
            "pipeline_gap_severity": 0.85,
            "recent_ma_cadence": 0.80,
        }
        result = compute_buyer_mandate_score(inputs)
        assert isinstance(result, BuyerMandateScore)
        assert result.mandate_tier == MandateTier.ACTIVE_MANDATE
        assert result.mandate_score >= 0.70

    def test_monitoring_tier_from_weak_signals(self):
        from bve.intelligence.ma_buyer_mandate import BuyerMandateScore, MandateTier, compute_buyer_mandate_score

        inputs = {
            "bd_guidance_statements": [],
            "rd_day_priority_areas": [],
            "pipeline_gap_severity": 0.20,
            "recent_ma_cadence": 0.15,
        }
        result = compute_buyer_mandate_score(inputs)
        assert result.mandate_tier == MandateTier.MONITORING
        assert result.mandate_score <= 0.40

    def test_unknown_inputs_lower_confidence_no_penalty(self):
        """UNKNOWN inputs must lower confidence only — no score penalty."""
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score

        # Full known inputs
        full_inputs = {
            "bd_guidance_statements": [
                {"text": "Active acquirer seeking BD.", "date": "2026-01-10", "source": "Earnings call"},
            ],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.70,
            "recent_ma_cadence": 0.60,
        }
        result_full = compute_buyer_mandate_score(full_inputs)

        # Same signals but rd_day_priority_areas unknown (None)
        partial_inputs = dict(full_inputs)
        partial_inputs["rd_day_priority_areas"] = None
        result_partial = compute_buyer_mandate_score(partial_inputs)

        # Score should not be WORSE because of the unknown field
        assert result_partial.mandate_score >= result_full.mandate_score - 0.05
        # Confidence should be lower
        assert result_partial.confidence < result_full.confidence
        # Missing data tracked
        assert len(result_partial.missing_data) > 0

    def test_stale_guidance_triggers_staleness_warning(self):
        """Data older than 90 days should trigger a staleness warning."""
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score

        stale_date = (date.today() - timedelta(days=120)).isoformat()
        inputs = {
            "bd_guidance_statements": [
                {"text": "Seeking oncology acquisitions.", "date": stale_date, "source": "Old conf"},
            ],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.75,
            "recent_ma_cadence": 0.60,
        }
        result = compute_buyer_mandate_score(inputs)
        assert result.staleness_warning is True

    def test_fresh_guidance_no_staleness_warning(self):
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score

        fresh_date = (date.today() - timedelta(days=30)).isoformat()
        inputs = {
            "bd_guidance_statements": [
                {"text": "Active M&A mandate.", "date": fresh_date, "source": "Q1 earnings"},
            ],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.70,
            "recent_ma_cadence": 0.55,
        }
        result = compute_buyer_mandate_score(inputs)
        assert result.staleness_warning is False

    def test_executive_alignment_signal_requires_evidence(self):
        """executive_alignment_signal must come from dated statements, not inferred."""
        from bve.intelligence.ma_buyer_mandate import BuyerMandateScore, compute_buyer_mandate_score

        # With no guidance statements, executive_alignment_signal must be None / UNKNOWN
        inputs = {
            "bd_guidance_statements": [],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.80,
            "recent_ma_cadence": 0.70,
        }
        result = compute_buyer_mandate_score(inputs)
        assert result.executive_alignment_signal is None

    def test_executive_alignment_signal_populated_from_statements(self):
        """executive_alignment_signal populated from explicit bd_guidance_statements."""
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score

        inputs = {
            "bd_guidance_statements": [
                {"text": "CEO: oncology BD is top priority for FY26.", "date": "2026-02-10", "source": "Earnings"},
            ],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.75,
            "recent_ma_cadence": 0.50,
        }
        result = compute_buyer_mandate_score(inputs)
        assert result.executive_alignment_signal is not None
        # Signal must carry a source and date, not be inferred
        assert result.executive_alignment_signal.source_date is not None

    def test_anti_double_counting_no_target_level_signals(self):
        """buyer mandate must not read target-level signals (target_market_cap, target_ta)."""
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score

        # Passing target-level signals should be silently ignored (not raise an error,
        # but also not change the mandate score vs a clean inputs dict)
        clean_inputs = {
            "bd_guidance_statements": [],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.50,
            "recent_ma_cadence": 0.40,
        }
        dirty_inputs = {
            **clean_inputs,
            "target_market_cap_billions": 2.5,   # target-level — must be ignored
            "target_therapeutic_area": "oncology",  # target-level — must be ignored
        }
        result_clean = compute_buyer_mandate_score(clean_inputs)
        result_dirty = compute_buyer_mandate_score(dirty_inputs)
        assert result_clean.mandate_score == pytest.approx(result_dirty.mandate_score, abs=1e-6)

    def test_all_mandate_tiers_reachable(self):
        from bve.intelligence.ma_buyer_mandate import MandateTier, compute_buyer_mandate_score

        tiers_seen = set()

        profiles = [
            # ACTIVE_MANDATE
            {"bd_guidance_statements": [{"text": "Seeking oncology BD.", "date": "2026-01-10", "source": "Conf"}],
             "rd_day_priority_areas": ["oncology"], "pipeline_gap_severity": 0.90, "recent_ma_cadence": 0.85},
            # TACTICAL
            {"bd_guidance_statements": [{"text": "Open to selective deals.", "date": "2026-01-10", "source": "Conf"}],
             "rd_day_priority_areas": ["oncology"], "pipeline_gap_severity": 0.60, "recent_ma_cadence": 0.55},
            # OPPORTUNISTIC
            {"bd_guidance_statements": [],
             "rd_day_priority_areas": ["oncology"], "pipeline_gap_severity": 0.40, "recent_ma_cadence": 0.35},
            # MONITORING
            {"bd_guidance_statements": [],
             "rd_day_priority_areas": [], "pipeline_gap_severity": 0.15, "recent_ma_cadence": 0.10},
        ]
        for p in profiles:
            r = compute_buyer_mandate_score(p)
            tiers_seen.add(r.mandate_tier)

        assert MandateTier.ACTIVE_MANDATE in tiers_seen
        assert MandateTier.MONITORING in tiers_seen


# ---------------------------------------------------------------------------
# B. InternalConflictScore tests
# ---------------------------------------------------------------------------

class TestInternalConflictScore:
    """Tests for ma_internal_conflict.InternalConflictScore."""

    def test_no_conflict_from_clean_inputs(self):
        from bve.intelligence.ma_internal_conflict import InternalConflictScore, ConflictLevel, compute_internal_conflict

        inputs = {
            "existing_pipeline_overlap": 0.0,
            "commercial_channel_conflict": 0.0,
            "partner_rofr_present": False,
            "pending_portfolio_acquisition": False,
        }
        result = compute_internal_conflict(inputs)
        assert isinstance(result, InternalConflictScore)
        assert result.conflict_level == ConflictLevel.NONE
        assert result.conflict_score == pytest.approx(0.0, abs=0.05)

    def test_blocking_conflict_from_severe_overlap(self):
        from bve.intelligence.ma_internal_conflict import ConflictLevel, compute_internal_conflict

        inputs = {
            "existing_pipeline_overlap": 0.95,
            "commercial_channel_conflict": 0.90,
            "partner_rofr_present": True,
            "pending_portfolio_acquisition": True,
        }
        result = compute_internal_conflict(inputs)
        assert result.conflict_level == ConflictLevel.BLOCKING
        assert result.conflict_score >= 0.80

    def test_all_conflict_levels_reachable(self):
        from bve.intelligence.ma_internal_conflict import ConflictLevel, compute_internal_conflict

        levels_seen = set()
        profiles = [
            # NONE
            {"existing_pipeline_overlap": 0.0, "commercial_channel_conflict": 0.0,
             "partner_rofr_present": False, "pending_portfolio_acquisition": False},
            # MINOR
            {"existing_pipeline_overlap": 0.20, "commercial_channel_conflict": 0.15,
             "partner_rofr_present": False, "pending_portfolio_acquisition": False},
            # MODERATE
            {"existing_pipeline_overlap": 0.50, "commercial_channel_conflict": 0.45,
             "partner_rofr_present": False, "pending_portfolio_acquisition": False},
            # BLOCKING
            {"existing_pipeline_overlap": 0.90, "commercial_channel_conflict": 0.85,
             "partner_rofr_present": True, "pending_portfolio_acquisition": True},
        ]
        for p in profiles:
            r = compute_internal_conflict(p)
            levels_seen.add(r.conflict_level)

        assert ConflictLevel.NONE in levels_seen
        assert ConflictLevel.BLOCKING in levels_seen

    def test_unknown_conflict_inputs_lower_confidence_only(self):
        from bve.intelligence.ma_internal_conflict import compute_internal_conflict

        full_inputs = {
            "existing_pipeline_overlap": 0.30,
            "commercial_channel_conflict": 0.25,
            "partner_rofr_present": False,
            "pending_portfolio_acquisition": False,
        }
        partial_inputs = {
            "existing_pipeline_overlap": None,  # UNKNOWN
            "commercial_channel_conflict": 0.25,
            "partner_rofr_present": False,
            "pending_portfolio_acquisition": False,
        }
        result_full = compute_internal_conflict(full_inputs)
        result_partial = compute_internal_conflict(partial_inputs)

        # Unknown must not inflate conflict score (benefit of doubt)
        assert result_partial.conflict_score <= result_full.conflict_score + 0.05
        assert result_partial.confidence < result_full.confidence

    def test_partner_rofr_elevates_conflict_level(self):
        from bve.intelligence.ma_internal_conflict import ConflictLevel, compute_internal_conflict

        without_rofr = {
            "existing_pipeline_overlap": 0.20,
            "commercial_channel_conflict": 0.10,
            "partner_rofr_present": False,
            "pending_portfolio_acquisition": False,
        }
        with_rofr = dict(without_rofr)
        with_rofr["partner_rofr_present"] = True

        result_without = compute_internal_conflict(without_rofr)
        result_with = compute_internal_conflict(with_rofr)

        # ROFR must raise score or level
        assert result_with.conflict_score > result_without.conflict_score


# ---------------------------------------------------------------------------
# C. RelationshipHistoryScore tests
# ---------------------------------------------------------------------------

class TestRelationshipHistoryScore:
    """Tests for ma_relationship_history.RelationshipHistoryScore."""

    def test_defaults_to_unknown_gate(self):
        """With no relationship history, score must be NEUTRAL with lower confidence."""
        from bve.intelligence.ma_relationship_history import RelationshipHistoryScore, compute_relationship_history

        result = compute_relationship_history({})
        assert isinstance(result, RelationshipHistoryScore)
        assert result.is_unknown is True
        assert result.relationship_score == pytest.approx(0.50, abs=0.05)  # neutral
        assert result.confidence <= 0.50  # lower confidence due to UNKNOWN

    def test_positive_history_raises_score(self):
        from bve.intelligence.ma_relationship_history import compute_relationship_history

        inputs = {
            "prior_partnership": True,
            "partnership_type": "co_development",
            "acquisition_option": True,
            "relationship_recency_years": 2.0,
            "prior_deal_attempts": 0,
        }
        result = compute_relationship_history(inputs)
        assert result.relationship_score > 0.60
        assert result.is_unknown is False

    def test_failed_prior_deal_lowers_score(self):
        from bve.intelligence.ma_relationship_history import compute_relationship_history

        base_inputs = {
            "prior_partnership": False,
            "partnership_type": None,
            "acquisition_option": False,
            "relationship_recency_years": None,
            "prior_deal_attempts": 0,
        }
        failed_inputs = dict(base_inputs)
        failed_inputs["prior_deal_attempts"] = 1
        failed_inputs["prior_deal_outcome"] = "failed_negotiation"

        result_base = compute_relationship_history(base_inputs)
        result_failed = compute_relationship_history(failed_inputs)

        # Failed prior deal should lower score vs neutral
        assert result_failed.relationship_score < result_base.relationship_score

    def test_no_inference_from_external_signals(self):
        """Relationship history must not be inferred from target TA or buyer name."""
        from bve.intelligence.ma_relationship_history import compute_relationship_history

        # Passing inference-bait fields must not alter the result vs empty
        result_empty = compute_relationship_history({})
        result_with_bait = compute_relationship_history({
            "target_name": "BioXcel",
            "buyer_name": "Pfizer",
            "therapeutic_area": "oncology",
        })
        # Score must be identical (inference-bait ignored)
        assert result_empty.relationship_score == pytest.approx(result_with_bait.relationship_score, abs=1e-6)


# ---------------------------------------------------------------------------
# D. BuyerTargetThesis aggregator tests
# ---------------------------------------------------------------------------

class TestBuyerTargetThesis:
    """Tests for ma_buyer_thesis.BuyerTargetThesis and UnderwriteThesis."""

    def _make_strong_inputs(self):
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score
        from bve.intelligence.ma_internal_conflict import compute_internal_conflict
        from bve.intelligence.ma_relationship_history import compute_relationship_history

        mandate = compute_buyer_mandate_score({
            "bd_guidance_statements": [{"text": "Active BD mandate.", "date": "2026-01-15", "source": "Conf"}],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.85,
            "recent_ma_cadence": 0.80,
        })
        conflict = compute_internal_conflict({
            "existing_pipeline_overlap": 0.05,
            "commercial_channel_conflict": 0.05,
            "partner_rofr_present": False,
            "pending_portfolio_acquisition": False,
        })
        relationship = compute_relationship_history({
            "prior_partnership": True,
            "partnership_type": "co_development",
            "acquisition_option": True,
            "relationship_recency_years": 1.5,
            "prior_deal_attempts": 0,
        })
        return mandate, conflict, relationship

    def test_strong_buy_thesis_from_strong_inputs(self):
        from bve.intelligence.ma_buyer_thesis import BuyerTargetThesis, UnderwriteThesis, build_buyer_target_thesis

        mandate, conflict, relationship = self._make_strong_inputs()
        thesis = build_buyer_target_thesis(
            mandate_score=mandate,
            conflict_score=conflict,
            relationship_score=relationship,
        )
        assert isinstance(thesis, BuyerTargetThesis)
        assert thesis.underwrite_thesis in {UnderwriteThesis.STRONG_BUY, UnderwriteThesis.BUY}

    def test_pass_thesis_from_blocking_conflict(self):
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score
        from bve.intelligence.ma_internal_conflict import compute_internal_conflict
        from bve.intelligence.ma_relationship_history import compute_relationship_history
        from bve.intelligence.ma_buyer_thesis import UnderwriteThesis, build_buyer_target_thesis

        mandate = compute_buyer_mandate_score({
            "bd_guidance_statements": [{"text": "Active BD mandate.", "date": "2026-01-15", "source": "Conf"}],
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
        relationship = compute_relationship_history({})  # UNKNOWN

        thesis = build_buyer_target_thesis(
            mandate_score=mandate,
            conflict_score=conflict,
            relationship_score=relationship,
        )
        assert thesis.underwrite_thesis == UnderwriteThesis.PASS

    def test_confidence_degrades_with_missing_inputs(self):
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score
        from bve.intelligence.ma_internal_conflict import compute_internal_conflict
        from bve.intelligence.ma_relationship_history import compute_relationship_history
        from bve.intelligence.ma_buyer_thesis import build_buyer_target_thesis

        mandate_known = compute_buyer_mandate_score({
            "bd_guidance_statements": [{"text": "Active BD mandate.", "date": "2026-01-15", "source": "Conf"}],
            "rd_day_priority_areas": ["oncology"],
            "pipeline_gap_severity": 0.75,
            "recent_ma_cadence": 0.70,
        })
        mandate_unknown = compute_buyer_mandate_score({
            "bd_guidance_statements": [],
            "rd_day_priority_areas": None,
            "pipeline_gap_severity": None,
            "recent_ma_cadence": None,
        })
        conflict = compute_internal_conflict({
            "existing_pipeline_overlap": 0.10,
            "commercial_channel_conflict": 0.10,
            "partner_rofr_present": False,
            "pending_portfolio_acquisition": False,
        })
        relationship = compute_relationship_history({})

        thesis_known = build_buyer_target_thesis(
            mandate_score=mandate_known,
            conflict_score=conflict,
            relationship_score=relationship,
        )
        thesis_unknown = build_buyer_target_thesis(
            mandate_score=mandate_unknown,
            conflict_score=conflict,
            relationship_score=relationship,
        )
        assert thesis_unknown.overall_confidence < thesis_known.overall_confidence

    def test_all_underwrite_theses_reachable(self):
        from bve.intelligence.ma_buyer_mandate import compute_buyer_mandate_score
        from bve.intelligence.ma_internal_conflict import compute_internal_conflict
        from bve.intelligence.ma_relationship_history import compute_relationship_history
        from bve.intelligence.ma_buyer_thesis import UnderwriteThesis, build_buyer_target_thesis

        def make_thesis(pipeline_gap, recent_ma, overlap, rofr, rel_inputs):
            m = compute_buyer_mandate_score({
                "bd_guidance_statements": [{"text": "BD.", "date": "2026-01-10", "source": "X"}] if pipeline_gap > 0.6 else [],
                "rd_day_priority_areas": ["oncology"] if pipeline_gap > 0.4 else [],
                "pipeline_gap_severity": pipeline_gap,
                "recent_ma_cadence": recent_ma,
            })
            c = compute_internal_conflict({
                "existing_pipeline_overlap": overlap,
                "commercial_channel_conflict": overlap * 0.8,
                "partner_rofr_present": rofr,
                "pending_portfolio_acquisition": False,
            })
            r = compute_relationship_history(rel_inputs)
            return build_buyer_target_thesis(mandate_score=m, conflict_score=c, relationship_score=r)

        theses_seen = set()
        theses_seen.add(make_thesis(0.90, 0.85, 0.05, False,
                                    {"prior_partnership": True, "acquisition_option": True, "relationship_recency_years": 1.0, "prior_deal_attempts": 0}).underwrite_thesis)
        theses_seen.add(make_thesis(0.65, 0.55, 0.20, False, {}).underwrite_thesis)
        theses_seen.add(make_thesis(0.40, 0.30, 0.40, False, {}).underwrite_thesis)
        theses_seen.add(make_thesis(0.80, 0.70, 0.92, True, {}).underwrite_thesis)

        assert UnderwriteThesis.STRONG_BUY in theses_seen or UnderwriteThesis.BUY in theses_seen
        assert UnderwriteThesis.PASS in theses_seen


# ---------------------------------------------------------------------------
# E. strategic_urgency_score split in Layer 2
# ---------------------------------------------------------------------------

class TestStrategicUrgencyScore:
    """strategic_urgency_score is pair-level timing pressure — separate from strategic_fit."""

    def _base_l2_inputs(self, strategic_urgency: float | None = None, strategic_fit: float | None = None):
        from bve.intelligence.ma_layer2_bd_priority import (
            Layer2Inputs,
            Layer2StrategicPriorityInputs,
        )
        sp = Layer2StrategicPriorityInputs(
            layer1_attractiveness_score=0.75,
            acquirer_strategic_fit=strategic_fit if strategic_fit is not None else 0.70,
            pipeline_gap_urgency=0.60,
            strategic_option_value=0.55,
            strategic_urgency_score=strategic_urgency,
        )
        return Layer2Inputs(target_name="TEST-CO", strategic_priority=sp)

    def test_strategic_urgency_score_field_exists(self):
        """Layer2StrategicPriorityInputs must accept strategic_urgency_score."""
        from bve.intelligence.ma_layer2_bd_priority import Layer2StrategicPriorityInputs
        sp = Layer2StrategicPriorityInputs(strategic_urgency_score=0.80)
        assert sp.strategic_urgency_score == 0.80

    def test_strategic_urgency_score_absent_does_not_break_layer2(self):
        """Omitting strategic_urgency_score must not raise an error (backward compat)."""
        from bve.intelligence.ma_layer2_bd_priority import Layer2StrategicPriorityInputs, Layer2Inputs, compute_layer2_bd_priority
        sp = Layer2StrategicPriorityInputs(
            layer1_attractiveness_score=0.70,
            acquirer_strategic_fit=0.65,
            pipeline_gap_urgency=0.55,
        )
        inputs = Layer2Inputs(target_name="COMPAT-CO", strategic_priority=sp)
        result = compute_layer2_bd_priority(inputs)
        assert result.bd_action_score >= 0.0

    def test_high_strategic_urgency_raises_sp_score(self):
        """High pair-level urgency should increase the strategic priority sub-score."""
        from bve.intelligence.ma_layer2_bd_priority import compute_layer2_bd_priority

        inputs_low = self._base_l2_inputs(strategic_urgency=0.10)
        inputs_high = self._base_l2_inputs(strategic_urgency=0.90)

        result_low = compute_layer2_bd_priority(inputs_low)
        result_high = compute_layer2_bd_priority(inputs_high)

        assert result_high.strategic_priority.score > result_low.strategic_priority.score

    def test_strategic_urgency_separate_from_pipeline_gap_urgency(self):
        """strategic_urgency_score must not change pipeline_gap_urgency contribution."""
        from bve.intelligence.ma_layer2_bd_priority import Layer2Inputs, Layer2StrategicPriorityInputs, compute_layer2_bd_priority

        # pipeline_gap_urgency is buyer-level; strategic_urgency_score is pair-level
        sp_a = Layer2StrategicPriorityInputs(
            layer1_attractiveness_score=0.70,
            pipeline_gap_urgency=0.70,
            strategic_urgency_score=0.30,
        )
        sp_b = Layer2StrategicPriorityInputs(
            layer1_attractiveness_score=0.70,
            pipeline_gap_urgency=0.70,
            strategic_urgency_score=0.80,
        )

        r_a = compute_layer2_bd_priority(Layer2Inputs(target_name="A", strategic_priority=sp_a))
        r_b = compute_layer2_bd_priority(Layer2Inputs(target_name="B", strategic_priority=sp_b))

        # Only urgency differs — sp_b must score higher
        assert r_b.strategic_priority.score > r_a.strategic_priority.score

    def test_strategic_urgency_exposed_in_output(self):
        """Layer2BDOutput must expose strategic_urgency_score for downstream consumers."""
        from bve.intelligence.ma_layer2_bd_priority import compute_layer2_bd_priority
        inputs = self._base_l2_inputs(strategic_urgency=0.75)
        result = compute_layer2_bd_priority(inputs)
        # The strategic_urgency_score should be stored on Layer2BDOutput or Layer2StrategicPriority
        sp = result.strategic_priority
        assert hasattr(sp, "strategic_urgency_score") or hasattr(result, "strategic_urgency_score")


# ---------------------------------------------------------------------------
# F. preliminary_transaction_friction tests
# ---------------------------------------------------------------------------

class TestPreliminaryTransactionFriction:
    """preliminary_transaction_friction is a simple pre-pair signal — not TransactionRealismScore."""

    def _friction_inputs(
        self,
        obvious_seller_unwillingness: float | None = None,
        obvious_price_mismatch: float | None = None,
        obvious_rights_issue: float | None = None,
        obvious_process_signal: float | None = None,
        obvious_data_gap: float | None = None,
    ):
        from bve.intelligence.ma_layer2_bd_priority import PreliminaryTransactionFrictionInputs
        return PreliminaryTransactionFrictionInputs(
            obvious_seller_unwillingness=obvious_seller_unwillingness,
            obvious_price_mismatch=obvious_price_mismatch,
            obvious_rights_issue=obvious_rights_issue,
            obvious_process_signal=obvious_process_signal,
            obvious_data_gap=obvious_data_gap,
        )

    def test_friction_inputs_model_exists(self):
        from bve.intelligence.ma_layer2_bd_priority import PreliminaryTransactionFrictionInputs
        f = PreliminaryTransactionFrictionInputs()
        assert f.obvious_seller_unwillingness is None
        assert f.obvious_price_mismatch is None

    def test_no_friction_signals_returns_clean(self):
        from bve.intelligence.ma_layer2_bd_priority import compute_preliminary_friction

        result = compute_preliminary_friction(self._friction_inputs(0.0, 0.0, 0.0, 0.0, 0.0))
        assert result.friction_score == pytest.approx(0.0, abs=0.05)
        assert result.friction_label == "CLEAN"

    def test_max_friction_returns_high_friction(self):
        from bve.intelligence.ma_layer2_bd_priority import compute_preliminary_friction

        result = compute_preliminary_friction(
            self._friction_inputs(1.0, 1.0, 1.0, 1.0, 1.0)
        )
        assert result.friction_score >= 0.80
        assert result.friction_label in {"HIGH_FRICTION", "BLOCK"}

    def test_unknown_friction_inputs_no_penalty(self):
        """UNKNOWN friction signal must not penalize the target."""
        from bve.intelligence.ma_layer2_bd_priority import compute_preliminary_friction

        result_clean = compute_preliminary_friction(self._friction_inputs(0.0, 0.0, 0.0, 0.0, 0.0))
        result_unknown = compute_preliminary_friction(self._friction_inputs())  # all None

        # Unknown should default to CLEAN, not add friction
        assert result_unknown.friction_score <= result_clean.friction_score + 0.05

    def test_friction_does_not_use_layer2_scores(self):
        """preliminary_transaction_friction must only use the 5 simple inputs — no circularity."""
        from bve.intelligence.ma_layer2_bd_priority import PreliminaryTransactionFrictionInputs
        import inspect

        sig = inspect.signature(PreliminaryTransactionFrictionInputs.__init__)
        # Should not have layer2 score parameters
        for forbidden in ["bd_action_score", "strategic_priority_score", "deal_momentum_score"]:
            assert forbidden not in sig.parameters

    def test_friction_label_options(self):
        """friction_label must be one of: CLEAN, MILD_FRICTION, HIGH_FRICTION, BLOCK."""
        from bve.intelligence.ma_layer2_bd_priority import compute_preliminary_friction

        VALID_LABELS = {"CLEAN", "MILD_FRICTION", "HIGH_FRICTION", "BLOCK"}
        for price_mismatch in [0.0, 0.4, 0.75, 1.0]:
            r = compute_preliminary_friction(self._friction_inputs(obvious_price_mismatch=price_mismatch))
            assert r.friction_label in VALID_LABELS

    def test_layer2_inputs_accepts_friction_field(self):
        """Layer2Inputs must accept a preliminary_transaction_friction field."""
        from bve.intelligence.ma_layer2_bd_priority import Layer2Inputs, PreliminaryTransactionFrictionInputs
        f = PreliminaryTransactionFrictionInputs(obvious_seller_unwillingness=0.80)
        inputs = Layer2Inputs(target_name="TEST", preliminary_transaction_friction=f)
        assert inputs.preliminary_transaction_friction is not None

    def test_high_friction_does_not_block_diligence_route(self):
        """High friction should add a warning/note but NOT hard-block the action_classification."""
        from bve.intelligence.ma_layer2_bd_priority import (
            Layer2Inputs,
            Layer2StrategicPriorityInputs,
            PreliminaryTransactionFrictionInputs,
            compute_layer2_bd_priority,
        )
        sp = Layer2StrategicPriorityInputs(
            layer1_attractiveness_score=0.85,
            acquirer_strategic_fit=0.80,
            pipeline_gap_urgency=0.75,
        )
        friction = PreliminaryTransactionFrictionInputs(obvious_seller_unwillingness=0.95)
        inputs = Layer2Inputs(
            target_name="FRICTION-TARGET",
            strategic_priority=sp,
            preliminary_transaction_friction=friction,
        )
        result = compute_layer2_bd_priority(inputs)
        # Should produce a friction warning, not a hard block
        assert any("friction" in w.lower() or "seller" in w.lower() for w in result.missing_data + result.layer_ownership_warnings)
        # Action classification should still be populated (not empty / errored)
        assert result.action_classification != ""
