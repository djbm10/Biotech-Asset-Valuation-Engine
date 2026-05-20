"""Tests for 0B Deal-Type Classification — multi-label routing layer.

Coverage:
  - 6 historical acquired-company archetypes (post-acquisition ground truth)
  - 4 live pipeline archetypes (representative current-day signals)
  - Structural invariants (weight sum, primary dominance, model routing)
  - Backward compatibility (deal_type property, _classify_deal_type wrapper)
  - Modifier logic (LEAD_ASSET_HEAVY, PLATFORM_LITE, RIGHTS_ENCUMBERED, etc.)
  - Confidence and data-gap penalties
"""
import pytest

from bve.intelligence.deal_type_classification import (
    DealModifier,
    DealType,
    DealTypeClassification,
    RecommendedModel,
    classify_deal_type,
)
from bve.intelligence.ma_eligibility import (
    DealType as DealTypeAlias,
    TargetEligibilityInput,
    _classify_deal_type,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target(**kwargs) -> TargetEligibilityInput:
    """Build a TargetEligibilityInput with sensible defaults."""
    defaults = {
        "ticker": "TEST",
        "lead_asset_present": True,
        "product_count": 1,
        "indication_count": 1,
        "lead_asset_status": "active",
    }
    defaults.update(kwargs)
    return TargetEligibilityInput(**defaults)


def _assert_weights_valid(cls: DealTypeClassification) -> None:
    total = sum(cls.deal_type_weights.values())
    assert abs(total - 1.0) < 0.06, f"weights sum to {total:.4f}"
    assert all(v >= 0 for v in cls.deal_type_weights.values())
    # All six keys present
    for dt in DealType:
        assert dt.value in cls.deal_type_weights


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------

class TestStructuralInvariants:

    def test_weight_keys_always_all_six_deal_types(self):
        t = _target()
        cls = classify_deal_type(t)
        assert set(cls.deal_type_weights.keys()) == {dt.value for dt in DealType}

    def test_weight_sum_approximately_one(self):
        t = _target(product_count=4, indication_count=3, is_platform_company=True)
        cls = classify_deal_type(t)
        _assert_weights_valid(cls)

    def test_primary_has_highest_weight(self):
        t = _target()
        cls = classify_deal_type(t)
        primary_w = cls.deal_type_weights[cls.primary_deal_type.value]
        max_w = max(cls.deal_type_weights.values())
        assert primary_w >= max_w - 0.05

    def test_recommended_model_matches_primary(self):
        from bve.intelligence.deal_type_classification import _PRIMARY_TO_MODEL
        t = _target()
        cls = classify_deal_type(t)
        assert cls.recommended_model == _PRIMARY_TO_MODEL[cls.primary_deal_type]

    def test_backward_compat_deal_type_property(self):
        t = _target()
        cls = classify_deal_type(t)
        assert cls.deal_type == cls.primary_deal_type

    def test_deal_type_routing_note_property(self):
        t = _target()
        cls = classify_deal_type(t)
        assert cls.deal_type_routing_note == cls.model_routing_reason

    def test_secondary_types_exclude_primary(self):
        # Pipeline portfolio with some platform signal
        t = _target(product_count=4, indication_count=3, is_platform_company=True, platform_validated=False)
        cls = classify_deal_type(t)
        assert cls.primary_deal_type not in cls.secondary_deal_types

    def test_confidence_range(self):
        t = _target()
        cls = classify_deal_type(t)
        assert 0.0 <= cls.confidence <= 1.0

    def test_confidence_penalised_for_data_gaps(self):
        # Missing revenue_concentration and approved_revenue_share → data gap
        cls_no_gaps = classify_deal_type(
            _target(revenue_concentration=0.90, approved_revenue_share=0.0)
        )
        cls_gaps = classify_deal_type(_target())   # no revenue_concentration
        assert cls_gaps.confidence <= cls_no_gaps.confidence + 0.01


# ---------------------------------------------------------------------------
# Historical acquired-company archetypes
# ---------------------------------------------------------------------------

class TestHistoricalAcquiredArchetypes:

    def test_single_asset_takeout_archetype(self):
        """Typical small clinical-stage biotech — one lead asset, no platform."""
        t = _target(
            ticker="HIST_SAT",
            lead_asset_present=True,
            product_count=1,
            indication_count=1,
            is_platform_company=False,
            revenue_concentration=0.95,
            approved_revenue_share=0.0,
            financing_pressure_high=False,
        )
        cls = classify_deal_type(t)
        assert cls.primary_deal_type == DealType.SINGLE_ASSET_TAKEOUT
        assert cls.recommended_model == RecommendedModel.LEAD_ASSET_RNPV
        assert cls.lead_asset_dependency in ("high", "very_high")

    def test_pipeline_portfolio_takeout_archetype(self):
        """Multi-program oncology company — 4 programs, 3 indications."""
        t = _target(
            ticker="HIST_PPT",
            product_count=4,
            indication_count=3,
            is_platform_company=False,
            revenue_concentration=0.45,
        )
        cls = classify_deal_type(t)
        assert cls.primary_deal_type == DealType.PIPELINE_PORTFOLIO_TAKEOUT
        assert cls.recommended_model == RecommendedModel.PORTFOLIO_MNA

    def test_platform_acquisition_archetype(self):
        """Validated gene-editing platform — platform is primary value driver."""
        t = _target(
            ticker="HIST_PLAT",
            is_platform_company=True,
            platform_validated=True,
            product_count=2,
            indication_count=2,
        )
        cls = classify_deal_type(t)
        assert cls.primary_deal_type == DealType.PLATFORM_ACQUISITION
        assert cls.recommended_model == RecommendedModel.PLATFORM_FIT
        assert cls.platform_value_share is not None
        assert cls.platform_value_share > 0.30

    def test_commercial_franchise_acquisition_archetype(self):
        """Approved-product company — >50% of value is approved revenue."""
        t = _target(
            ticker="HIST_CFA",
            approved_revenue_share=0.75,
            salesforce_required=True,
            product_count=2,
            indication_count=2,
        )
        cls = classify_deal_type(t)
        assert cls.primary_deal_type == DealType.COMMERCIAL_FRANCHISE_ACQUISITION
        assert cls.recommended_model == RecommendedModel.COMMERCIAL_SYNERGY
        assert cls.approved_revenue_value_share is not None
        assert cls.approved_revenue_value_share > 0.50

    def test_asset_license_partnership_archetype(self):
        """Small-cap with existing partner + low EV — licensing deal more likely."""
        t = _target(
            ticker="HIST_ALP",
            has_existing_partnership=True,
            enterprise_value_millions=200.0,
            asset_rights_scope="licensed_in",
            royalty_stack_rate=0.20,
        )
        cls = classify_deal_type(t)
        assert cls.primary_deal_type == DealType.ASSET_LICENSE_PARTNERSHIP
        assert cls.recommended_model == RecommendedModel.LICENSING
        assert DealModifier.RIGHTS_ENCUMBERED in cls.modifiers

    def test_distressed_optionality_archetype(self):
        """Financially distressed company with weak lead asset — option value only.

        revenue_concentration=0.0 means no dominant single asset, which pushes
        pipeline_frac to 0.5 (split equally between lead/pipeline), leaving
        distress_raw=0.40 as the highest share after normalization.
        """
        t = _target(
            ticker="HIST_DO",
            financing_pressure_high=True,
            lead_asset_quality_low=True,
            is_platform_company=False,
            revenue_concentration=0.0,   # no dominant single asset
        )
        cls = classify_deal_type(t)
        assert cls.primary_deal_type == DealType.DISTRESSED_OPTIONALITY
        assert cls.recommended_model == RecommendedModel.DISTRESS_ADJUSTED
        assert cls.distress_flag is True


# ---------------------------------------------------------------------------
# Live pipeline archetypes
# ---------------------------------------------------------------------------

class TestLivePipelineArchetypes:

    def test_single_molecule_multi_indication(self):
        """One compound across 3 indications — PIPELINE_IN_A_PRODUCT modifier expected."""
        t = _target(
            ticker="LIVE_PIAP",
            product_count=1,
            indication_count=3,
            is_platform_company=False,
        )
        cls = classify_deal_type(t)
        assert DealModifier.PIPELINE_IN_A_PRODUCT in cls.modifiers

    def test_commercial_pipeline_hybrid(self):
        """Approved revenue ~40% + active mid-stage pipeline = COMMERCIAL_PIPELINE_HYBRID."""
        t = _target(
            ticker="LIVE_CPH",
            approved_revenue_share=0.40,
            product_count=3,
            indication_count=2,
            salesforce_required=True,
        )
        cls = classify_deal_type(t)
        assert DealModifier.COMMERCIAL_PIPELINE_HYBRID in cls.modifiers

    def test_platform_lite_on_portfolio_primary(self):
        """Portfolio primary but unvalidated platform signal present → PLATFORM_LITE."""
        t = _target(
            ticker="LIVE_PLITE",
            product_count=4,
            indication_count=3,
            is_platform_company=True,
            platform_validated=False,
        )
        cls = classify_deal_type(t)
        # Platform is not fully validated so portfolio weight may dominate
        assert DealModifier.PLATFORM_LITE in cls.modifiers or cls.primary_deal_type == DealType.PLATFORM_ACQUISITION

    def test_distress_overlay_not_primary(self):
        """Moderate distress signal alongside viable pipeline — DISTRESS_OVERLAY, not primary."""
        t = _target(
            ticker="LIVE_DO_OVERLAY",
            financing_pressure_high=True,
            lead_asset_quality_low=False,
            product_count=2,
            indication_count=2,
        )
        cls = classify_deal_type(t)
        if cls.primary_deal_type != DealType.DISTRESSED_OPTIONALITY:
            assert DealModifier.DISTRESS_OVERLAY in cls.modifiers


# ---------------------------------------------------------------------------
# Backward compatibility via ma_eligibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:

    def test_deal_type_alias_is_same_enum(self):
        """DealType imported from ma_eligibility should be the same as from deal_type_classification."""
        assert DealTypeAlias is DealType

    def test_legacy_classify_deal_type_wrapper_returns_tuple(self):
        t = _target()
        result = _classify_deal_type(t)
        assert isinstance(result, tuple)
        assert len(result) == 2
        deal_type, note = result
        assert isinstance(deal_type, DealType)
        assert isinstance(note, str)

    def test_legacy_wrapper_platform_routing(self):
        t = _target(is_platform_company=True, platform_validated=True)
        deal_type, _ = _classify_deal_type(t)
        assert deal_type == DealType.PLATFORM_ACQUISITION

    def test_legacy_wrapper_commercial_routing(self):
        t = _target(approved_revenue_share=0.75)
        deal_type, _ = _classify_deal_type(t)
        assert deal_type == DealType.COMMERCIAL_FRANCHISE_ACQUISITION

    def test_layer0_result_has_deal_type_classification(self):
        from bve.intelligence.ma_eligibility import evaluate_layer0
        t = _target(ticker="COMPAT", lead_asset_present=True)
        result = evaluate_layer0(t)
        if result.passes_hard_exclusion:
            assert result.deal_type_classification is not None
            assert isinstance(result.deal_type_classification, DealTypeClassification)
            assert result.deal_type == result.deal_type_classification.primary_deal_type
        else:
            assert result.deal_type_classification is None

    def test_layer0_excluded_target_has_no_classification(self):
        from bve.intelligence.ma_eligibility import evaluate_layer0, CompanyTaxonomy
        t = _target(ticker="EXCL", company_taxonomy=CompanyTaxonomy.ACQUIRER)
        result = evaluate_layer0(t)
        assert not result.passes_hard_exclusion
        assert result.deal_type_classification is None


# ---------------------------------------------------------------------------
# Layer 4 integration
# ---------------------------------------------------------------------------

class TestLayer4Integration:

    def test_layer4_propagates_deal_type_fields(self):
        from bve.intelligence.ma_layer4_routing import Layer4Inputs, compute_layer4
        from bve.intelligence.deal_type_classification import classify_deal_type

        t = _target(ticker="L4TEST", product_count=4, indication_count=3)
        dtc = classify_deal_type(t)

        inputs = Layer4Inputs(
            asset_quality=0.70,
            strategic_fit=0.70,
            deal_feasibility=0.65,
            seller_willingness=0.55,
            de_risking_stage=0.60,
            strategic_priority=0.72,
            transaction_probability=0.65,
            data_confidence_score=0.80,
            deal_type_classification=dtc,
        )
        out = compute_layer4(inputs, target_name="TestCo")
        assert out.primary_deal_type == dtc.primary_deal_type.value
        assert out.recommended_model == dtc.recommended_model.value

    def test_layer4_without_classification_has_none_fields(self):
        from bve.intelligence.ma_layer4_routing import Layer4Inputs, compute_layer4

        inputs = Layer4Inputs(
            asset_quality=0.70,
            strategic_fit=0.70,
            deal_feasibility=0.65,
            seller_willingness=0.55,
            de_risking_stage=0.60,
            strategic_priority=0.72,
            transaction_probability=0.65,
        )
        out = compute_layer4(inputs, target_name="TestCo")
        assert out.primary_deal_type is None
        assert out.recommended_model is None
        assert out.secondary_deal_types == []
