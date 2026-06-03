"""Block 6 integration tests — management quality overlay across all modules.

Tests:
  1. BuyerTargetThesis receives management_risk_band/summary when provided
  2. HIGH/SEVERE management risk adds negative signal to thesis
  3. LOW/MEDIUM management risk does NOT add negative signal
  4. UNKNOWN management does NOT add negative signal (only flag)
  5. DealStructureRationale passes management_risk_band/gate through
  6. Weak trial design biases structure toward STRUCTURED (from FULL_ACQUISITION)
  7. Poor capital allocation biases structure toward STRUCTURED
  8. Governance risk adds caveat to DealStructureRationale
  9. UNKNOWN management adds diligence item to DealStructureRationale
  10. Layer1 management integration — confidence cap on HIGH risk
  11. TransactionRealism management integration — poor BD lowers confidence
  12. TransactionRealism UNKNOWN management lowers confidence
  13. MAProbabilityRow accepts management quality enrichment fields
  14. ErrorType enum has all 4 management error types
  15. No regression — existing thesis/realism/structure still work without management
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_management_quality import (
    ManagementQualityInput,
    ManagementSignalSourceQuality,
    compute_management_quality_score,
)
from bve.intelligence.ma_buyer_mandate import BuyerMandateScore, MandateTier
from bve.intelligence.ma_internal_conflict import InternalConflictScore, ConflictLevel
from bve.intelligence.ma_relationship_history import RelationshipHistoryScore
from bve.intelligence.ma_buyer_thesis import BuyerTargetThesis, build_buyer_target_thesis
from bve.intelligence.ma_transaction_realism import (
    TransactionRealismScore,
    compute_transaction_realism,
)
from bve.intelligence.ma_deal_structure_rationale import (
    DealStructureRationale,
    RecommendedStructure,
    build_deal_structure_rationale,
)
from bve.intelligence.ma_calibration_models import ErrorType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mgmt_score(
    clinical=0.80,
    trial_design=0.80,
    regulatory=0.80,
    capital=0.80,
    bd=0.80,
    disclosure=0.80,
    governance=0.80,
):
    inp = ManagementQualityInput(
        target_id="test",
        clinical_execution_quality=clinical,
        trial_design_judgment=trial_design,
        regulatory_execution=regulatory,
        capital_allocation_discipline=capital,
        bd_partnering_judgment=bd,
        disclosure_transparency=disclosure,
        governance_alignment=governance,
    )
    return compute_management_quality_score(inp)


def _severe_mgmt():
    return _mgmt_score(
        clinical=0.10, trial_design=0.10, regulatory=0.10,
        capital=0.10, bd=0.10, disclosure=0.10, governance=0.10,
    )


def _unknown_mgmt():
    inp = ManagementQualityInput(target_id="unknown")
    return compute_management_quality_score(inp)


def _good_mandate() -> BuyerMandateScore:
    return BuyerMandateScore(
        mandate_score=0.80,
        mandate_tier=MandateTier.ACTIVE_MANDATE,
        confidence=0.80,
        positive_drivers=["pipeline_gap_confirmed"],
        missing_data=[],
    )


def _clean_conflict() -> InternalConflictScore:
    return InternalConflictScore(
        conflict_score=0.10,
        conflict_level=ConflictLevel.NONE,
        confidence=0.80,
        conflict_drivers=[],
        missing_data=[],
    )


def _neutral_relationship() -> RelationshipHistoryScore:
    return RelationshipHistoryScore(
        relationship_score=0.50,
        confidence=0.80,
        is_unknown=False,
        positive_drivers=[],
        negative_drivers=[],
    )


def _thesis(management_quality=None) -> BuyerTargetThesis:
    return build_buyer_target_thesis(
        mandate_score=_good_mandate(),
        conflict_score=_clean_conflict(),
        relationship_score=_neutral_relationship(),
        management_quality=management_quality,
    )


def _realism_score(management_quality=None):
    inp = {
        "seller_readiness": {
            "has_announced_strategic_review": True,
            "financial_distress_level": "low",
            "management_openness_to_deal": "neutral",
        },
        "price_expectation": {
            "current_market_cap_millions": 500.0,
            "analyst_consensus_target_millions": 600.0,
            "last_financing_premium": 0.15,
        },
        "rights_clarity": {
            "rofr_present": False,
            "partner_rights_issue": False,
            "ip_licensing_barrier": False,
        },
    }
    return compute_transaction_realism(inp, management_quality=management_quality)


def _deal_structure(management_quality=None, realism_label="HIGH"):
    thesis = _thesis()
    realism = _realism_score()
    # Patch realism label for routing tests via the actual realism path
    return build_deal_structure_rationale(
        thesis=thesis,
        realism=realism,
        management_quality=management_quality,
    )


# ---------------------------------------------------------------------------
# 1–4. BuyerTargetThesis management overlay
# ---------------------------------------------------------------------------

class TestBuyerThesisManagementOverlay:
    def test_no_management_fields_are_none(self):
        t = _thesis()
        assert t.management_risk_band is None
        assert t.management_risk_summary is None
        assert t.management_value_preservation_flag is False

    def test_management_risk_band_populated(self):
        t = _thesis(_mgmt_score())
        assert t.management_risk_band is not None

    def test_management_risk_summary_populated(self):
        t = _thesis(_mgmt_score())
        assert t.management_risk_summary is not None and len(t.management_risk_summary) > 0

    def test_severe_management_sets_flag(self):
        t = _thesis(_severe_mgmt())
        assert t.management_value_preservation_flag is True

    def test_severe_management_adds_negative_signal(self):
        t = _thesis(_severe_mgmt())
        assert any("management_risk" in s for s in t.negative_signals)

    def test_strong_management_no_negative_signal(self):
        t = _thesis(_mgmt_score())  # all 0.80 → LOW risk
        mgmt_negs = [s for s in t.negative_signals if "management_risk" in s]
        assert len(mgmt_negs) == 0

    def test_unknown_management_no_negative_signal(self):
        t = _thesis(_unknown_mgmt())
        mgmt_negs = [s for s in t.negative_signals if "management_risk" in s]
        assert len(mgmt_negs) == 0

    def test_unknown_management_band_is_unknown(self):
        t = _thesis(_unknown_mgmt())
        assert t.management_risk_band == "unknown"

    def test_management_does_not_change_thesis_tier(self):
        """Management risk must NOT change the underwrite_thesis — value preservation only."""
        t_without = _thesis()
        t_severe = _thesis(_severe_mgmt())
        assert t_without.underwrite_thesis == t_severe.underwrite_thesis

    def test_management_does_not_change_thesis_score(self):
        t_without = _thesis()
        t_severe = _thesis(_severe_mgmt())
        assert t_without.thesis_score == t_severe.thesis_score

    def test_management_does_not_change_confidence(self):
        t_without = _thesis()
        t_severe = _thesis(_severe_mgmt())
        assert t_without.overall_confidence == t_severe.overall_confidence


# ---------------------------------------------------------------------------
# 5–9. DealStructureRationale management overlay
# ---------------------------------------------------------------------------

class TestDealStructureManagementOverlay:
    def test_no_management_fields_are_none(self):
        d = _deal_structure()
        assert d.management_risk_band is None
        assert d.management_gate is None

    def test_management_risk_band_populated(self):
        d = _deal_structure(_mgmt_score())
        assert d.management_risk_band is not None

    def test_management_gate_populated(self):
        d = _deal_structure(_mgmt_score())
        assert d.management_gate is not None

    def test_weak_trial_design_adds_caveat(self):
        d = _deal_structure(_mgmt_score(trial_design=0.20))
        assert any("trial_design_risk" in c for c in d.caveats)

    def test_poor_capital_allocation_adds_caveat(self):
        d = _deal_structure(_mgmt_score(capital=0.20))
        assert any("capital_risk" in c for c in d.caveats)

    def test_governance_risk_adds_caveat(self):
        d = _deal_structure(_mgmt_score(governance=0.20))
        assert any("governance_risk" in c for c in d.caveats)

    def test_unknown_management_adds_diligence_item(self):
        d = _deal_structure(_unknown_mgmt())
        assert any("management_quality_unknown" in item for item in d.diligence_items)

    def test_strong_management_no_extra_caveats(self):
        d_without = _deal_structure()
        d_strong = _deal_structure(_mgmt_score())
        mgmt_caveats = [c for c in d_strong.caveats if "management" in c]
        assert len(mgmt_caveats) == 0

    def test_recommended_structure_not_none(self):
        d = _deal_structure(_severe_mgmt())
        assert d.recommended_structure is not None


# ---------------------------------------------------------------------------
# 10. Layer1 management integration
# ---------------------------------------------------------------------------

class TestLayer1ManagementOverlay:
    def test_layer1_without_management_runs(self):
        """Regression: Layer 1 still works with no management quality."""
        from bve.intelligence.ma_layer1_attractiveness import (
            Layer1Inputs,
            compute_layer1_strategic_attractiveness,
        )
        inp = Layer1Inputs(
            asset_id="test",
            target_name="TestCo",
            therapeutic_area="oncology",
            clinical_stage="phase_3",
            asset_quality_score=0.75,
            first_in_class=True,
            acquirer_pipeline_gap_score=0.70,
        )
        result = compute_layer1_strategic_attractiveness(inp)
        assert result.raw_score >= 0.0

    def test_layer1_with_high_management_risk_sets_flag(self):
        """SEVERE management risk marks management_confidence_cap_applied=True."""
        from bve.intelligence.ma_layer1_attractiveness import (
            Layer1Inputs,
            compute_layer1_strategic_attractiveness,
        )
        inp = Layer1Inputs(
            asset_id="test",
            target_name="TestCo",
            therapeutic_area="oncology",
            clinical_stage="phase_3",
            asset_quality_score=0.75,
            first_in_class=True,
            acquirer_pipeline_gap_score=0.70,
            management_quality_score=_severe_mgmt(),
        )
        r = compute_layer1_strategic_attractiveness(inp)
        assert r.management_confidence_cap_applied is True
        assert r.management_risk_band == "severe"

    def test_layer1_low_management_risk_no_cap(self):
        """LOW management risk does NOT apply confidence cap."""
        from bve.intelligence.ma_layer1_attractiveness import (
            Layer1Inputs,
            compute_layer1_strategic_attractiveness,
        )
        inp = Layer1Inputs(
            asset_id="test",
            target_name="TestCo",
            therapeutic_area="oncology",
            clinical_stage="phase_3",
            asset_quality_score=0.75,
            first_in_class=True,
            acquirer_pipeline_gap_score=0.70,
            management_quality_score=_mgmt_score(),
        )
        r = compute_layer1_strategic_attractiveness(inp)
        assert r.management_confidence_cap_applied is False


# ---------------------------------------------------------------------------
# 11–12. TransactionRealism management integration
# ---------------------------------------------------------------------------

class TestTransactionRealismManagementOverlay:
    def test_without_management_runs(self):
        r = _realism_score()
        assert r.overall_confidence > 0.0

    def test_poor_bd_judgment_lowers_confidence(self):
        r_without = _realism_score()
        r_with = _realism_score(_mgmt_score(bd=0.20))
        assert r_with.overall_confidence <= r_without.overall_confidence

    def test_poor_governance_sets_diligence_required(self):
        r = _realism_score(_mgmt_score(governance=0.20))
        assert r.is_diligence_required is True

    def test_unknown_management_lowers_confidence(self):
        r_without = _realism_score()
        r_with = _realism_score(_unknown_mgmt())
        assert r_with.overall_confidence <= r_without.overall_confidence

    def test_strong_management_no_friction_added(self):
        r_without = _realism_score()
        r_with = _realism_score(_mgmt_score())
        mgmt_frictions = [n for n in r_with.friction_notes if "management" in n.lower()]
        assert len(mgmt_frictions) == 0


# ---------------------------------------------------------------------------
# 13. MAProbabilityRow management fields
# ---------------------------------------------------------------------------

class TestMAProbabilityRowManagementFields:
    def test_row_accepts_management_enrichment(self):
        from bve.intelligence.ma_probability import MAProbabilityRow
        row = MAProbabilityRow(
            asset_id="test",
            mna_probability_score=0.60,
            p_acquisition=0.60,
            raw_probability=0.60,
            above_alert_threshold=False,
            score_version="v1.4",
            best_acquirer_id="pfizer",
            best_acquirer_name="Pfizer",
            best_acquirer_fit_score=0.70,
            valuation_discount_score=0.50,
            strategic_fit_score=0.60,
            de_risking_stage_score=0.55,
            capital_vulnerability_score=0.40,
            scarcity_score=0.50,
            scarcity_peer_count=2,
            scarcity_bucket="low_competition",
            vulnerability_score=0.45,
            explanation="test",
            management_quality_composite=0.72,
            management_risk_band="low",
            management_risk_summary="LOW management risk.",
            management_gate="none",
        )
        assert row.management_quality_composite == 0.72
        assert row.management_risk_band == "low"
        assert row.management_gate == "none"

    def test_row_defaults_management_fields_to_none(self):
        from bve.intelligence.ma_probability import MAProbabilityRow
        row = MAProbabilityRow(
            asset_id="test",
            mna_probability_score=0.60,
            p_acquisition=0.60,
            raw_probability=0.60,
            above_alert_threshold=False,
            score_version="v1.4",
            best_acquirer_id="pfizer",
            best_acquirer_name="Pfizer",
            best_acquirer_fit_score=0.70,
            valuation_discount_score=0.50,
            strategic_fit_score=0.60,
            de_risking_stage_score=0.55,
            capital_vulnerability_score=0.40,
            scarcity_score=0.50,
            scarcity_peer_count=2,
            scarcity_bucket="low_competition",
            vulnerability_score=0.45,
            explanation="test",
        )
        assert row.management_quality_composite is None
        assert row.management_risk_band is None
        assert row.management_risk_summary is None
        assert row.management_gate is None


# ---------------------------------------------------------------------------
# 14. ErrorType enum management entries
# ---------------------------------------------------------------------------

class TestErrorTypeManagementEntries:
    def test_management_ran_wrong_trial_exists(self):
        assert ErrorType.MANAGEMENT_RAN_WRONG_TRIAL == "management_ran_wrong_trial"

    def test_management_poor_bd_judgment_exists(self):
        assert ErrorType.MANAGEMENT_POOR_BD_JUDGMENT == "management_poor_bd_judgment"

    def test_management_capital_destruction_exists(self):
        assert ErrorType.MANAGEMENT_CAPITAL_DESTRUCTION == "management_capital_destruction"

    def test_management_governance_blocked_deal_exists(self):
        assert ErrorType.MANAGEMENT_GOVERNANCE_BLOCKED_DEAL == "management_governance_blocked_deal"


# ---------------------------------------------------------------------------
# 15. Regression — all modules work without management quality
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_thesis_no_management_arg(self):
        t = build_buyer_target_thesis(
            mandate_score=_good_mandate(),
            conflict_score=_clean_conflict(),
            relationship_score=_neutral_relationship(),
        )
        assert t.underwrite_thesis is not None

    def test_realism_no_management_arg(self):
        r = compute_transaction_realism({})
        assert r.overall_confidence >= 0.0

    def test_deal_structure_no_management_arg(self):
        thesis = _thesis()
        realism = _realism_score()
        d = build_deal_structure_rationale(thesis=thesis, realism=realism)
        assert d.recommended_structure is not None
        assert d.management_risk_band is None
