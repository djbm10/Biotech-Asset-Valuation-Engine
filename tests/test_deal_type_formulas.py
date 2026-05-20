"""Tests for the deal-type formula scoring engine (ma_deal_type_formulas.py).

Coverage:
  A — Single-asset takeout: strong lead asset → high single_asset score
  B — Pipeline portfolio: multi-asset coherent TA → high portfolio score
  C — Platform acquisition: validated platform → high platform score
  D — Commercial franchise: approved revenue + durability → high commercial score
  E — Asset license / partnership: encumbered rights → high licensing score
  F — Distressed optionality: short runway + viable asset → high distress score
  G — Hybrid blend: Revolution-like 0.55/0.25/0.20 weights verified
  H — Hybrid blend: Alpine-like 0.80/0.15/0.05 weights verified
  I — Platform-primary: platform formula drives blended score
  J — Gate primacy: final_score_with_overlay never exceeds final_score
  K — Severe cap: formula overlay cannot raise score above Layer 3 cap

Structural invariants tested throughout:
  - blended_deal_type_score in [0, 1]
  - confidence in [0, 1]
  - weighted_score == raw_score × weight
  - all 6 DealType formula_scores present in overlay
  - data_gaps propagated correctly
"""
from __future__ import annotations

import pytest

from bve.intelligence.deal_type_classification import DealType
from bve.intelligence.ma_deal_type_formulas import (
    DealTypeFormulaInput,
    DealTypeOverlayResult,
    compute_deal_type_overlay,
    score_commercial_franchise,
    score_distress,
    score_licensing,
    score_pipeline_portfolio,
    score_platform,
    score_single_asset,
)
from bve.intelligence.ma_layer4_routing import Layer4Inputs, compute_layer4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _equal_weights() -> dict[str, float]:
    return {dt.value: 1.0 / 6 for dt in DealType}


def _single_weight(primary: DealType, w: float = 0.70) -> dict[str, float]:
    """Concentrate most weight on one deal type, spread the rest equally."""
    rest = (1.0 - w) / (len(DealType) - 1)
    return {dt.value: (w if dt == primary else rest) for dt in DealType}


def _strong_quality() -> dict:
    """High-quality base asset sub-scores."""
    return dict(
        clinical_evidence=0.85,
        differentiation=0.80,
        regulatory_path=0.80,
        ip_durability=0.75,
        cmc_feasibility=0.75,
        commercial_meaningfulness=0.80,
    )


def _assert_overlay_valid(overlay: DealTypeOverlayResult) -> None:
    assert 0.0 <= overlay.blended_deal_type_score <= 1.0
    assert 0.0 <= overlay.confidence <= 1.0
    assert len(overlay.formula_scores) == len(list(DealType))
    for fs in overlay.formula_scores:
        assert 0.0 <= fs.raw_score <= 1.0
        assert abs(fs.weighted_score - fs.raw_score * fs.weight) < 1e-9


# ---------------------------------------------------------------------------
# A — Single-asset takeout
# ---------------------------------------------------------------------------

class TestFormulaA_SingleAsset:

    def test_strong_lead_asset_scores_high(self):
        inp = DealTypeFormulaInput(
            **_strong_quality(),
            product_count=1,
            indication_count=1,
        )
        fs = score_single_asset(inp, weight=1.0)
        assert fs.raw_score >= 0.70

    def test_multi_product_reduces_lead_concentration(self):
        inp_single = DealTypeFormulaInput(**_strong_quality(), product_count=1)
        inp_multi = DealTypeFormulaInput(**_strong_quality(), product_count=5)
        fs_single = score_single_asset(inp_single, weight=1.0)
        fs_multi = score_single_asset(inp_multi, weight=1.0)
        assert fs_single.raw_score > fs_multi.raw_score

    def test_components_present(self):
        inp = DealTypeFormulaInput(**_strong_quality(), product_count=1)
        fs = score_single_asset(inp, weight=0.60)
        assert "base_quality" in fs.components
        assert "lead_concentration" in fs.components
        assert "regulatory_path" in fs.components

    def test_weighted_score_correct(self):
        inp = DealTypeFormulaInput(**_strong_quality(), product_count=1)
        w = 0.55
        fs = score_single_asset(inp, weight=w)
        assert abs(fs.weighted_score - fs.raw_score * w) < 1e-9

    def test_deal_type_label(self):
        inp = DealTypeFormulaInput(**_strong_quality())
        fs = score_single_asset(inp, weight=1.0)
        assert fs.deal_type == DealType.SINGLE_ASSET_TAKEOUT.value


# ---------------------------------------------------------------------------
# B — Pipeline portfolio takeout
# ---------------------------------------------------------------------------

class TestFormulaB_PipelinePortfolio:

    def test_high_breadth_high_ta_fit_scores_high(self):
        inp = DealTypeFormulaInput(
            **_strong_quality(),
            product_count=5,
            indication_count=4,
            acquirer_ta_fit=0.90,
        )
        fs = score_pipeline_portfolio(inp, weight=1.0)
        assert fs.raw_score >= 0.70

    def test_single_product_scores_lower_than_multi(self):
        common = dict(**_strong_quality(), acquirer_ta_fit=0.80)
        inp_single = DealTypeFormulaInput(**common, product_count=1, indication_count=1)
        inp_multi = DealTypeFormulaInput(**common, product_count=5, indication_count=4)
        fs_single = score_pipeline_portfolio(inp_single, weight=1.0)
        fs_multi = score_pipeline_portfolio(inp_multi, weight=1.0)
        assert fs_multi.raw_score > fs_single.raw_score

    def test_data_gap_flagged_when_ta_fit_default(self):
        # Default acquirer_ta_fit=0.50 with empty weights → data gap flagged
        inp = DealTypeFormulaInput(**_strong_quality(), product_count=3)
        fs = score_pipeline_portfolio(inp, weight=1.0)
        assert any("acquirer_ta_fit" in g for g in fs.data_gaps)

    def test_deal_type_label(self):
        inp = DealTypeFormulaInput(**_strong_quality(), product_count=4)
        fs = score_pipeline_portfolio(inp, weight=1.0)
        assert fs.deal_type == DealType.PIPELINE_PORTFOLIO_TAKEOUT.value


# ---------------------------------------------------------------------------
# C — Platform acquisition
# ---------------------------------------------------------------------------

class TestFormulaC_Platform:

    def test_validated_platform_scores_high(self):
        inp = DealTypeFormulaInput(
            **_strong_quality(),
            is_platform_company=True,
            platform_validated=True,
            platform_breadth=0.85,
        )
        fs = score_platform(inp, weight=1.0)
        assert fs.raw_score >= 0.70

    def test_validation_bonus_increases_score(self):
        common = dict(**_strong_quality(), is_platform_company=True, platform_breadth=0.70)
        inp_unvalidated = DealTypeFormulaInput(**common, platform_validated=False)
        inp_validated = DealTypeFormulaInput(**common, platform_validated=True)
        fs_unvalidated = score_platform(inp_unvalidated, weight=1.0)
        fs_validated = score_platform(inp_validated, weight=1.0)
        assert fs_validated.raw_score > fs_unvalidated.raw_score

    def test_data_gap_when_platform_breadth_default(self):
        inp = DealTypeFormulaInput(**_strong_quality(), is_platform_company=True,
                                   platform_validated=True)
        fs = score_platform(inp, weight=1.0)
        assert any("platform_breadth" in g for g in fs.data_gaps)

    def test_deal_type_label(self):
        inp = DealTypeFormulaInput(**_strong_quality(), is_platform_company=True)
        fs = score_platform(inp, weight=1.0)
        assert fs.deal_type == DealType.PLATFORM_ACQUISITION.value


# ---------------------------------------------------------------------------
# D — Commercial franchise acquisition
# ---------------------------------------------------------------------------

class TestFormulaD_CommercialFranchise:

    def test_high_approved_revenue_durable_scores_high(self):
        inp = DealTypeFormulaInput(
            **_strong_quality(),
            approved_revenue_share=0.80,
            revenue_durability=0.85,
            salesforce_required=True,
        )
        fs = score_commercial_franchise(inp, weight=1.0)
        assert fs.raw_score >= 0.65

    def test_no_approved_revenue_scores_lower(self):
        common = _strong_quality()
        inp_commercial = DealTypeFormulaInput(**common, approved_revenue_share=0.80,
                                               revenue_durability=0.80)
        inp_pipeline = DealTypeFormulaInput(**common, approved_revenue_share=0.0,
                                             revenue_durability=0.80)
        fs_commercial = score_commercial_franchise(inp_commercial, weight=1.0)
        fs_pipeline = score_commercial_franchise(inp_pipeline, weight=1.0)
        assert fs_commercial.raw_score > fs_pipeline.raw_score

    def test_salesforce_required_higher_than_not(self):
        common = dict(**_strong_quality(), approved_revenue_share=0.60, revenue_durability=0.70)
        fs_with = score_commercial_franchise(
            DealTypeFormulaInput(**common, salesforce_required=True), weight=1.0)
        fs_without = score_commercial_franchise(
            DealTypeFormulaInput(**common, salesforce_required=False), weight=1.0)
        assert fs_with.raw_score > fs_without.raw_score

    def test_deal_type_label(self):
        inp = DealTypeFormulaInput(**_strong_quality(), approved_revenue_share=0.75)
        fs = score_commercial_franchise(inp, weight=1.0)
        assert fs.deal_type == DealType.COMMERCIAL_FRANCHISE_ACQUISITION.value


# ---------------------------------------------------------------------------
# E — Asset license / partnership
# ---------------------------------------------------------------------------

class TestFormulaE_Licensing:

    def test_encumbered_rights_high_partnership_scores_reasonably(self):
        inp = DealTypeFormulaInput(
            **_strong_quality(),
            has_existing_partnership=True,
            asset_rights_scope="licensed_in",
            royalty_stack_rate=0.20,
        )
        fs = score_licensing(inp, weight=1.0)
        # Encumbrance reduces rights_fit, but quality + partnership should keep score moderate
        assert fs.raw_score >= 0.45

    def test_clean_title_scores_higher_than_encumbered(self):
        common = dict(**_strong_quality(), has_existing_partnership=True)
        inp_clean = DealTypeFormulaInput(**common, asset_rights_scope="owned",
                                          royalty_stack_rate=0.0)
        inp_encumbered = DealTypeFormulaInput(**common, asset_rights_scope="licensed_in",
                                               royalty_stack_rate=0.30)
        fs_clean = score_licensing(inp_clean, weight=1.0)
        fs_enc = score_licensing(inp_encumbered, weight=1.0)
        assert fs_clean.raw_score > fs_enc.raw_score

    def test_rights_encumbered_reduces_rights_fit(self):
        inp = DealTypeFormulaInput(**_strong_quality(), asset_rights_scope="licensed_in",
                                    royalty_stack_rate=0.30)
        fs = score_licensing(inp, weight=1.0)
        # rights_fit = 1 - min(1, 0.30 + 0.20) = 0.50
        assert abs(fs.components["rights_fit"] - 0.50) < 1e-9

    def test_deal_type_label(self):
        inp = DealTypeFormulaInput(**_strong_quality(), has_existing_partnership=True)
        fs = score_licensing(inp, weight=1.0)
        assert fs.deal_type == DealType.ASSET_LICENSE_PARTNERSHIP.value


# ---------------------------------------------------------------------------
# F — Distressed optionality
# ---------------------------------------------------------------------------

class TestFormulaF_Distress:

    def test_high_pressure_short_runway_scores_high_on_pressure(self):
        inp = DealTypeFormulaInput(
            **_strong_quality(),
            financing_pressure_high=True,
            months_cash_runway=6.0,
            lead_asset_quality_low=False,
            catalyst_within_90_days=True,
        )
        fs = score_distress(inp, weight=1.0)
        assert fs.raw_score >= 0.60

    def test_low_quality_lead_reduces_optionality(self):
        common = dict(**_strong_quality(), financing_pressure_high=True, months_cash_runway=8.0)
        inp_good = DealTypeFormulaInput(**common, lead_asset_quality_low=False)
        inp_bad = DealTypeFormulaInput(**common, lead_asset_quality_low=True)
        fs_good = score_distress(inp_good, weight=1.0)
        fs_bad = score_distress(inp_bad, weight=1.0)
        assert fs_good.raw_score > fs_bad.raw_score

    def test_catalyst_boosts_signal(self):
        common = dict(**_strong_quality(), financing_pressure_high=True, months_cash_runway=10.0)
        fs_cat = score_distress(DealTypeFormulaInput(**common, catalyst_within_90_days=True),
                                weight=1.0)
        fs_no_cat = score_distress(DealTypeFormulaInput(**common, catalyst_within_90_days=False),
                                   weight=1.0)
        assert fs_cat.raw_score > fs_no_cat.raw_score

    def test_deal_type_label(self):
        inp = DealTypeFormulaInput(**_strong_quality(), financing_pressure_high=True)
        fs = score_distress(inp, weight=1.0)
        assert fs.deal_type == DealType.DISTRESSED_OPTIONALITY.value


# ---------------------------------------------------------------------------
# G — Hybrid blending: Revolution-like (single_asset dominant)
# ---------------------------------------------------------------------------

class TestFormulaG_RevolutionHybrid:

    def test_revolution_like_blend(self):
        """55% single-asset / 25% platform / 20% pipeline blend."""
        weights = {
            DealType.SINGLE_ASSET_TAKEOUT.value: 0.55,
            DealType.PLATFORM_ACQUISITION.value: 0.25,
            DealType.PIPELINE_PORTFOLIO_TAKEOUT.value: 0.20,
            DealType.COMMERCIAL_FRANCHISE_ACQUISITION.value: 0.0,
            DealType.ASSET_LICENSE_PARTNERSHIP.value: 0.0,
            DealType.DISTRESSED_OPTIONALITY.value: 0.0,
        }
        inp = DealTypeFormulaInput(
            **_strong_quality(),
            product_count=1,
            indication_count=1,
            is_platform_company=True,
            platform_validated=True,
            platform_breadth=0.70,
            deal_type_weights=weights,
        )
        overlay = compute_deal_type_overlay(inp)
        _assert_overlay_valid(overlay)
        # Single-asset carries most weight → its contribution should dominate
        sat_score = next(
            fs for fs in overlay.formula_scores
            if fs.deal_type == DealType.SINGLE_ASSET_TAKEOUT.value
        )
        assert sat_score.weight == pytest.approx(0.55)
        assert sat_score.weighted_score > 0.0

    def test_blended_score_is_weighted_sum(self):
        weights = {
            DealType.SINGLE_ASSET_TAKEOUT.value: 0.55,
            DealType.PLATFORM_ACQUISITION.value: 0.25,
            DealType.PIPELINE_PORTFOLIO_TAKEOUT.value: 0.20,
            DealType.COMMERCIAL_FRANCHISE_ACQUISITION.value: 0.0,
            DealType.ASSET_LICENSE_PARTNERSHIP.value: 0.0,
            DealType.DISTRESSED_OPTIONALITY.value: 0.0,
        }
        inp = DealTypeFormulaInput(**_strong_quality(), deal_type_weights=weights)
        overlay = compute_deal_type_overlay(inp)
        manual_blend = sum(fs.raw_score * fs.weight for fs in overlay.formula_scores)
        assert abs(overlay.blended_deal_type_score - manual_blend) < 1e-9


# ---------------------------------------------------------------------------
# H — Hybrid blending: Alpine-like (single_asset heavy)
# ---------------------------------------------------------------------------

class TestFormulaH_AlpineHybrid:

    def test_alpine_like_80_15_5_blend(self):
        """80% single-asset / 15% portfolio / 5% distress."""
        weights = {
            DealType.SINGLE_ASSET_TAKEOUT.value: 0.80,
            DealType.PIPELINE_PORTFOLIO_TAKEOUT.value: 0.15,
            DealType.DISTRESSED_OPTIONALITY.value: 0.05,
            DealType.PLATFORM_ACQUISITION.value: 0.0,
            DealType.COMMERCIAL_FRANCHISE_ACQUISITION.value: 0.0,
            DealType.ASSET_LICENSE_PARTNERSHIP.value: 0.0,
        }
        inp = DealTypeFormulaInput(
            **_strong_quality(),
            product_count=1,
            indication_count=2,
            financing_pressure_high=False,
            deal_type_weights=weights,
        )
        overlay = compute_deal_type_overlay(inp)
        _assert_overlay_valid(overlay)

        sat_fs = next(fs for fs in overlay.formula_scores
                      if fs.deal_type == DealType.SINGLE_ASSET_TAKEOUT.value)
        assert sat_fs.weight == pytest.approx(0.80)
        # With 80% weight on single-asset and strong quality, blended should be high
        assert overlay.blended_deal_type_score >= 0.50

    def test_all_six_formulas_present(self):
        inp = DealTypeFormulaInput(**_strong_quality())
        overlay = compute_deal_type_overlay(inp)
        deal_types_present = {fs.deal_type for fs in overlay.formula_scores}
        expected = {dt.value for dt in DealType}
        assert deal_types_present == expected


# ---------------------------------------------------------------------------
# I — Platform primary drives blended score
# ---------------------------------------------------------------------------

class TestFormulaI_PlatformPrimary:

    def test_platform_primary_with_validated_platform(self):
        weights = _single_weight(DealType.PLATFORM_ACQUISITION, w=0.70)
        inp = DealTypeFormulaInput(
            **_strong_quality(),
            is_platform_company=True,
            platform_validated=True,
            platform_breadth=0.85,
            deal_type_weights=weights,
        )
        overlay = compute_deal_type_overlay(inp)
        _assert_overlay_valid(overlay)

        platform_fs = next(fs for fs in overlay.formula_scores
                           if fs.deal_type == DealType.PLATFORM_ACQUISITION.value)
        # Platform has 70% weight and high score → should be the largest contributor
        max_weighted = max(fs.weighted_score for fs in overlay.formula_scores)
        assert platform_fs.weighted_score == pytest.approx(max_weighted, abs=1e-9)

    def test_overlay_primary_type_set(self):
        weights = _single_weight(DealType.PLATFORM_ACQUISITION, w=0.70)
        inp = DealTypeFormulaInput(**_strong_quality(), is_platform_company=True,
                                    platform_validated=True, deal_type_weights=weights)
        overlay = compute_deal_type_overlay(
            inp,
            primary_deal_type=DealType.PLATFORM_ACQUISITION.value,
        )
        assert overlay.primary_deal_type == DealType.PLATFORM_ACQUISITION.value


# ---------------------------------------------------------------------------
# J — Gate primacy: final_score_with_overlay never exceeds final_score
# ---------------------------------------------------------------------------

class TestFormulaJ_GatePrimacy:

    def _layer4_inputs(self, formula_inp: DealTypeFormulaInput,
                       final_score: float) -> Layer4Inputs:
        return Layer4Inputs(
            asset_quality=0.70,
            strategic_fit=0.70,
            deal_feasibility=0.65,
            seller_willingness=0.55,
            de_risking_stage=0.60,
            strategic_priority=0.72,
            transaction_probability=0.65,
            data_confidence_score=0.80,
            final_score=final_score,
            deal_type_formula_input=formula_inp,
        )

    def test_overlay_does_not_exceed_final_score(self):
        inp = DealTypeFormulaInput(**_strong_quality(),
                                    deal_type_weights=_equal_weights())
        l4 = self._layer4_inputs(inp, final_score=0.55)
        out = compute_layer4(l4)
        assert out.final_score_with_overlay is not None
        assert out.final_score_with_overlay <= 0.55

    def test_overlay_present_when_formula_input_provided(self):
        inp = DealTypeFormulaInput(**_strong_quality())
        l4 = self._layer4_inputs(inp, final_score=0.60)
        out = compute_layer4(l4)
        assert out.deal_type_overlay is not None
        assert out.final_score_with_overlay is not None

    def test_no_overlay_when_formula_input_absent(self):
        l4 = Layer4Inputs(
            asset_quality=0.70,
            strategic_fit=0.70,
            deal_feasibility=0.65,
            seller_willingness=0.55,
            de_risking_stage=0.60,
            strategic_priority=0.72,
            transaction_probability=0.65,
        )
        out = compute_layer4(l4)
        assert out.deal_type_overlay is None
        assert out.final_score_with_overlay is None


# ---------------------------------------------------------------------------
# K — Severe cap: formula overlay cannot raise score above Layer 3 cap
# ---------------------------------------------------------------------------

class TestFormulaK_SevereCap:

    def test_high_formula_score_capped_by_final_score(self):
        """Even with maximum quality inputs, the overlay cannot raise final_score_with_overlay
        above the incoming final_score."""
        # Perfect quality — formulas will score near 1.0
        perfect = dict(
            clinical_evidence=1.0, differentiation=1.0, regulatory_path=1.0,
            ip_durability=1.0, cmc_feasibility=1.0, commercial_meaningfulness=1.0,
        )
        inp = DealTypeFormulaInput(**perfect, deal_type_weights=_equal_weights())

        # Simulate a severely capped score (e.g. Gate 1 applied)
        capped_final_score = 0.40

        l4 = Layer4Inputs(
            asset_quality=0.30,   # triggers Gate 1 cap
            strategic_fit=0.50,
            deal_feasibility=0.50,
            seller_willingness=0.50,
            de_risking_stage=0.50,
            strategic_priority=0.60,
            transaction_probability=0.50,
            data_confidence_score=0.80,
            final_score=capped_final_score,
            deal_type_formula_input=inp,
        )
        out = compute_layer4(l4)
        assert out.final_score_with_overlay is not None
        assert out.final_score_with_overlay <= capped_final_score + 1e-9

    def test_formula_overlay_blended_score_in_range(self):
        inp = DealTypeFormulaInput(
            clinical_evidence=1.0, differentiation=1.0, regulatory_path=1.0,
            ip_durability=1.0, cmc_feasibility=1.0, commercial_meaningfulness=1.0,
            deal_type_weights=_equal_weights(),
        )
        overlay = compute_deal_type_overlay(inp)
        assert 0.0 <= overlay.blended_deal_type_score <= 1.0


# ---------------------------------------------------------------------------
# Structural invariants across all scenarios
# ---------------------------------------------------------------------------

class TestStructuralInvariants:

    def test_empty_weights_uses_equal_fallback(self):
        inp = DealTypeFormulaInput(**_strong_quality(), deal_type_weights={})
        overlay = compute_deal_type_overlay(inp)
        expected_w = pytest.approx(1.0 / 6, abs=1e-9)
        for fs in overlay.formula_scores:
            assert fs.weight == expected_w

    def test_confidence_penalised_for_data_gaps(self):
        # Default values trigger data gaps (acquirer_ta_fit=0.50 etc.)
        inp_default = DealTypeFormulaInput(**_strong_quality())
        inp_complete = DealTypeFormulaInput(
            **_strong_quality(),
            acquirer_ta_fit=0.80,
            platform_breadth=0.75,
            months_cash_runway=18.0,
            revenue_durability=0.70,
            royalty_stack_rate=0.10,
            deal_type_weights=_equal_weights(),
        )
        overlay_default = compute_deal_type_overlay(inp_default)
        overlay_complete = compute_deal_type_overlay(inp_complete)
        # Complete input should have equal or higher confidence
        assert overlay_complete.confidence >= overlay_default.confidence - 0.01

    def test_all_formula_scores_in_range(self):
        for dt in DealType:
            inp = DealTypeFormulaInput(**_strong_quality(),
                                        deal_type_weights=_single_weight(dt))
            overlay = compute_deal_type_overlay(inp)
            for fs in overlay.formula_scores:
                assert 0.0 <= fs.raw_score <= 1.0, f"{fs.deal_type} raw_score out of range"
                assert 0.0 <= fs.weighted_score <= 1.0, f"{fs.deal_type} weighted_score out of range"

    def test_blended_score_is_sum_of_weighted_scores(self):
        inp = DealTypeFormulaInput(**_strong_quality(), deal_type_weights=_equal_weights())
        overlay = compute_deal_type_overlay(inp)
        manual = sum(fs.raw_score * fs.weight for fs in overlay.formula_scores)
        assert abs(overlay.blended_deal_type_score - manual) < 1e-9
