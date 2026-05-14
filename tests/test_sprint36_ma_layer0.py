"""Sprint 36 — Layer 0 M&A Eligibility, Deal-Type Routing, and Data-Quality Gate.

Covers:
  0A. Hard Exclusion Rules (taxonomy-driven, not just ticker-driven)
  0B. Deal-Type Classification (commercial franchise routing, not hard fail)
  0C. Pair-Specific Affordability Gate (per acquirer-target pair)
  0D. Asset-Control / Encumbrance Gate
  0E. Commercial Complexity / Integration Penalty (function-based)
  0F. Distress Quality Guard
  0G. Data Confidence Output
  Integration: evaluate_layer0 end-to-end
"""
import pytest

from bve.intelligence.ma_eligibility import (
    AffordabilityBand,
    AcquirerCapacityInput,
    CommercialComplexityScore,
    CompanyTaxonomy,
    DataConfidenceGrade,
    DealType,
    EncumbranceFlags,
    ExclusionCode,
    Layer0Result,
    TargetEligibilityInput,
    _affordability_band,
    _compute_commercial_complexity,
    _compute_data_confidence,
    _evaluate_affordability,
    _evaluate_distress_guard,
    _evaluate_encumbrance,
    _evaluate_hard_exclusion,
    _classify_deal_type,
    evaluate_layer0,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _target(**kw) -> TargetEligibilityInput:
    """Minimal valid target: therapeutics, active lead, decent data."""
    defaults = dict(
        ticker="XYZ",
        company_taxonomy=CompanyTaxonomy.THERAPEUTICS,
        lead_asset_present=True,
        lead_asset_status="active",
        has_market_cap=True,
        has_enterprise_value=True,
        has_cash_debt=True,
        has_clinical_stage=True,
        has_trial_status=True,
        has_revenue_mix=True,
        has_asset_ownership_data=True,
        has_quarterly_burn=True,
        has_partner_rights_data=True,
        has_patent_loe_data=True,
        has_acquirer_profile_data=True,
        enterprise_value_millions=500.0,
    )
    defaults.update(kw)
    return TargetEligibilityInput(**defaults)


def _acquirer(acq_id="BIGPHARMA", *, cash=5000.0, debt_cap=2000.0,
              stock=1000.0, buffer=500.0, premium=0.35) -> AcquirerCapacityInput:
    return AcquirerCapacityInput(
        acquirer_id=acq_id,
        cash_available_millions=cash,
        estimated_debt_capacity_millions=debt_cap,
        realistic_stock_component_millions=stock,
        minimum_balance_buffer_millions=buffer,
        expected_takeout_premium=premium,
    )


def _dc(target: TargetEligibilityInput):
    return _compute_data_confidence(target)


# ===========================================================================
# 0A — Hard Exclusion Rules
# ===========================================================================

class TestHardExclusion:
    def test_non_biotech_diversified_excluded(self):
        t = _target(company_taxonomy=CompanyTaxonomy.DIVERSIFIED_CONGLOMERATE)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.NON_BIOTECH_PHARMA

    def test_other_taxonomy_excluded(self):
        t = _target(company_taxonomy=CompanyTaxonomy.OTHER)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.NON_BIOTECH_PHARMA

    def test_known_acquirer_taxonomy_excluded(self):
        t = _target(company_taxonomy=CompanyTaxonomy.ACQUIRER)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.KNOWN_ACQUIRER

    def test_spac_shell_excluded(self):
        t = _target(company_taxonomy=CompanyTaxonomy.SPAC_SHELL)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.SPAC_SHELL

    def test_self_acquisition_excluded(self):
        t = _target(ticker="ACME", acquirer_ticker="ACME")
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.SELF_ACQUISITION

    def test_self_acquisition_case_insensitive(self):
        t = _target(ticker="acme", acquirer_ticker="ACME")
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.SELF_ACQUISITION

    def test_different_acquirer_ticker_passes(self):
        t = _target(ticker="ACME", acquirer_ticker="BIGPHARMA")
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert passes
        assert code is None

    def test_no_lead_asset_no_platform_excluded(self):
        t = _target(lead_asset_present=False, is_platform_company=False)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.NO_IDENTIFIABLE_ASSET

    def test_no_lead_asset_but_platform_passes(self):
        t = _target(lead_asset_present=False, is_platform_company=True)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert passes

    def test_failed_lead_no_replacement_excluded(self):
        t = _target(lead_asset_status="failed", has_replacement_asset=False)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.PERMANENTLY_IMPAIRED_LEAD

    def test_failed_lead_with_replacement_passes(self):
        t = _target(lead_asset_status="failed", has_replacement_asset=True)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert passes

    def test_discontinued_no_replacement_excluded(self):
        t = _target(lead_asset_status="discontinued", has_replacement_asset=False)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.PERMANENTLY_IMPAIRED_LEAD

    def test_safety_blocked_no_replacement_excluded(self):
        t = _target(lead_asset_status="safety_blocked", has_replacement_asset=False)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.PERMANENTLY_IMPAIRED_LEAD

    def test_insufficient_data_excluded(self):
        # Only 2 fields present → LOW confidence → excluded
        t = TargetEligibilityInput(
            ticker="XYZ",
            company_taxonomy=CompanyTaxonomy.THERAPEUTICS,
            has_market_cap=True,
            has_enterprise_value=True,
        )
        dc = _dc(t)
        assert dc.grade == DataConfidenceGrade.LOW
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert not passes
        assert code == ExclusionCode.INSUFFICIENT_DATA

    def test_diagnostics_taxonomy_passes(self):
        t = _target(company_taxonomy=CompanyTaxonomy.DIAGNOSTICS)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert passes

    def test_tools_taxonomy_passes(self):
        t = _target(company_taxonomy=CompanyTaxonomy.TOOLS)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert passes

    def test_platform_taxonomy_passes(self):
        t = _target(company_taxonomy=CompanyTaxonomy.PLATFORM)
        dc = _dc(t)
        passes, code, _ = _evaluate_hard_exclusion(t, dc)
        assert passes


# ===========================================================================
# 0B — Deal-Type Classification
# ===========================================================================

class TestDealTypeClassification:
    def test_platform_validated_routes_platform(self):
        t = _target(is_platform_company=True, platform_validated=True)
        dt, _ = _classify_deal_type(t)
        assert dt == DealType.PLATFORM_ACQUISITION

    def test_platform_unvalidated_does_not_route_platform(self):
        t = _target(is_platform_company=True, platform_validated=False)
        dt, _ = _classify_deal_type(t)
        assert dt != DealType.PLATFORM_ACQUISITION

    def test_approved_revenue_over_50pct_routes_commercial_franchise(self):
        # Not a hard fail — routes to commercial_franchise_acquisition model
        t = _target(approved_revenue_share=0.65)
        dt, note = _classify_deal_type(t)
        assert dt == DealType.COMMERCIAL_FRANCHISE_ACQUISITION
        assert "65%" in note

    def test_approved_revenue_exactly_50pct_does_not_route_commercial(self):
        # 50% is not >50%
        t = _target(approved_revenue_share=0.50)
        dt, _ = _classify_deal_type(t)
        assert dt != DealType.COMMERCIAL_FRANCHISE_ACQUISITION

    def test_distressed_optionality_routing(self):
        t = _target(financing_pressure_high=True, lead_asset_quality_low=True)
        dt, _ = _classify_deal_type(t)
        assert dt == DealType.DISTRESSED_OPTIONALITY

    def test_pipeline_portfolio_routing(self):
        t = _target(product_count=4, indication_count=3)
        dt, _ = _classify_deal_type(t)
        assert dt == DealType.PIPELINE_PORTFOLIO_TAKEOUT

    def test_asset_license_routing_small_ev_with_partnership(self):
        t = _target(
            has_existing_partnership=True,
            enterprise_value_millions=300.0,
            product_count=1,
        )
        dt, _ = _classify_deal_type(t)
        assert dt == DealType.ASSET_LICENSE_PARTNERSHIP

    def test_default_single_asset_takeout(self):
        t = _target(product_count=1, indication_count=1)
        dt, _ = _classify_deal_type(t)
        assert dt == DealType.SINGLE_ASSET_TAKEOUT

    def test_platform_takes_priority_over_commercial(self):
        # Platform + high approved revenue → Platform wins (checked first)
        t = _target(is_platform_company=True, platform_validated=True,
                    approved_revenue_share=0.80)
        dt, _ = _classify_deal_type(t)
        assert dt == DealType.PLATFORM_ACQUISITION


# ===========================================================================
# 0C — Pair-Specific Affordability Gate
# ===========================================================================

class TestAffordabilityGate:
    def test_no_penalty_band_at_low_ratio(self):
        # deal_capacity = 5000+2000+1000-500 = 7500; cost = 500*1.35=675; ratio=0.09
        acq = _acquirer(cash=5000, debt_cap=2000, stock=1000, buffer=500, premium=0.35)
        results = _evaluate_affordability(500.0, [acq])
        assert len(results) == 1
        r = results[0]
        assert r.band == AffordabilityBand.NO_PENALTY
        assert r.score_multiplier == pytest.approx(1.0)

    def test_mild_penalty_band(self):
        # capacity = 1000, target_ev=600, premium=0.35 → cost=810, ratio=0.81 → mild
        acq = _acquirer(cash=1000, debt_cap=0, stock=0, buffer=0, premium=0.35)
        results = _evaluate_affordability(600.0, [acq])
        r = results[0]
        assert r.band == AffordabilityBand.MILD_PENALTY
        assert r.score_multiplier == pytest.approx(0.90)

    def test_severe_penalty_band(self):
        # capacity=1000, ev=700, cost=945, ratio=0.945 → severe
        acq = _acquirer(cash=1000, debt_cap=0, stock=0, buffer=0, premium=0.35)
        results = _evaluate_affordability(700.0, [acq])
        r = results[0]
        assert r.band == AffordabilityBand.SEVERE_PENALTY
        assert r.score_multiplier == pytest.approx(0.60)

    def test_hard_fail_band(self):
        # capacity=500, ev=500, cost=675, ratio=1.35 → hard fail
        acq = _acquirer(cash=500, debt_cap=0, stock=0, buffer=0, premium=0.35)
        results = _evaluate_affordability(500.0, [acq])
        r = results[0]
        assert r.band == AffordabilityBand.HARD_FAIL
        assert r.score_multiplier == pytest.approx(0.0)
        assert r.is_hard_fail is True

    def test_band_boundary_050_no_penalty(self):
        # ratio exactly 0.50 → NO_PENALTY
        band, mult = _affordability_band(0.50)
        assert band == AffordabilityBand.NO_PENALTY
        assert mult == pytest.approx(1.0)

    def test_band_boundary_085_mild(self):
        # ratio exactly 0.85 → MILD_PENALTY
        band, mult = _affordability_band(0.85)
        assert band == AffordabilityBand.MILD_PENALTY

    def test_band_boundary_110_severe(self):
        # ratio exactly 1.10 → SEVERE_PENALTY
        band, mult = _affordability_band(1.10)
        assert band == AffordabilityBand.SEVERE_PENALTY

    def test_band_just_over_110_hard_fail(self):
        band, mult = _affordability_band(1.11)
        assert band == AffordabilityBand.HARD_FAIL

    def test_none_ev_returns_empty(self):
        acq = _acquirer()
        results = _evaluate_affordability(None, [acq])
        assert results == []

    def test_multiple_acquirers_independent_results(self):
        rich = _acquirer("RICH", cash=10000, debt_cap=5000, stock=2000, buffer=0, premium=0.35)
        poor = _acquirer("POOR", cash=200, debt_cap=0, stock=0, buffer=0, premium=0.35)
        results = _evaluate_affordability(500.0, [rich, poor])
        assert len(results) == 2
        rich_r = next(r for r in results if r.acquirer_id == "RICH")
        poor_r = next(r for r in results if r.acquirer_id == "POOR")
        assert rich_r.band == AffordabilityBand.NO_PENALTY
        assert poor_r.band == AffordabilityBand.HARD_FAIL


# ===========================================================================
# 0D — Asset-Control / Encumbrance Gate
# ===========================================================================

class TestEncumbranceGate:
    def test_global_rights_no_penalty(self):
        t = _target(asset_rights_scope="global")
        enc = _evaluate_encumbrance(t)
        assert enc.penalty_multiplier == pytest.approx(1.0)
        assert "global_rights:positive" in enc.encumbrance_codes

    def test_regional_split_penalty(self):
        t = _target(asset_rights_scope="regional_split")
        enc = _evaluate_encumbrance(t)
        assert enc.penalty_multiplier == pytest.approx(0.90)
        assert "regional_rights_split" in enc.encumbrance_codes

    def test_ip_dispute_severe_penalty(self):
        t = _target(has_ip_dispute=True)
        enc = _evaluate_encumbrance(t)
        # global (0) + ip_dispute (0.25) → multiplier = 0.75
        assert enc.penalty_multiplier == pytest.approx(0.75)
        assert enc.has_ip_dispute is True

    def test_rofr_penalty(self):
        t = _target(has_right_of_first_refusal=True)
        enc = _evaluate_encumbrance(t)
        assert enc.has_right_of_first_refusal is True
        assert enc.penalty_multiplier == pytest.approx(0.88)

    def test_royalty_stack_below_threshold_not_flagged(self):
        t = _target(royalty_stack_rate=0.10)  # 10% < 15% threshold
        enc = _evaluate_encumbrance(t)
        assert enc.royalty_stack_high is False

    def test_royalty_stack_above_threshold_flagged(self):
        t = _target(royalty_stack_rate=0.20)  # 20% > 15%
        enc = _evaluate_encumbrance(t)
        assert enc.royalty_stack_high is True
        assert "royalty_stack_high" in enc.encumbrance_codes

    def test_co_development_obligation_penalty(self):
        t = _target(has_co_development_obligation=True)
        enc = _evaluate_encumbrance(t)
        assert enc.has_co_development_obligation is True
        assert enc.penalty_multiplier < 1.0

    def test_manufacturing_dependency_penalty(self):
        t = _target(has_manufacturing_dependency=True)
        enc = _evaluate_encumbrance(t)
        assert enc.has_manufacturing_dependency is True
        assert enc.penalty_multiplier < 1.0

    def test_cumulative_penalties_floor(self):
        # Pile on every issue — penalty_multiplier should not fall below 0.20
        t = _target(
            asset_rights_scope="regional_split",
            has_right_of_first_refusal=True,
            royalty_stack_rate=0.25,
            has_co_development_obligation=True,
            has_ip_dispute=True,
            has_manufacturing_dependency=True,
        )
        enc = _evaluate_encumbrance(t)
        assert enc.penalty_multiplier >= 0.20

    def test_no_encumbrances_multiplier_1(self):
        t = _target()
        enc = _evaluate_encumbrance(t)
        assert enc.penalty_multiplier == pytest.approx(1.0)


# ===========================================================================
# 0E — Commercial Complexity / Integration Penalty
# ===========================================================================

class TestCommercialComplexity:
    def test_single_product_low_complexity(self):
        t = _target(product_count=1, indication_count=1,
                    manufacturing_complexity="low", geographic_complexity="local",
                    payer_access_complexity="low", salesforce_required=False,
                    revenue_concentration=1.0)   # 100% concentrated → dispersion=0
        cc = _compute_commercial_complexity(t)
        assert cc.complexity_score < 0.10   # very simple
        assert cc.penalty_multiplier == pytest.approx(1.0)  # no meaningful penalty

    def test_max_complexity_reduces_multiplier(self):
        t = _target(
            product_count=15, indication_count=5,
            manufacturing_complexity="high", geographic_complexity="global",
            payer_access_complexity="high", salesforce_required=True,
            revenue_concentration=0.10,
        )
        cc = _compute_commercial_complexity(t)
        assert cc.complexity_score > 0.70
        assert cc.penalty_multiplier < 0.70

    def test_approved_revenue_offsets_complexity_penalty(self):
        # High complexity + high approved revenue → penalty partially offset
        t_no_rev = _target(
            product_count=10, manufacturing_complexity="high",
            geographic_complexity="global", payer_access_complexity="high",
            approved_revenue_share=None,
        )
        t_with_rev = _target(
            product_count=10, manufacturing_complexity="high",
            geographic_complexity="global", payer_access_complexity="high",
            approved_revenue_share=0.70,
        )
        cc_no = _compute_commercial_complexity(t_no_rev)
        cc_with = _compute_commercial_complexity(t_with_rev)
        # With approved revenue, penalty is 60% of what it would be otherwise
        assert cc_with.penalty_multiplier > cc_no.penalty_multiplier

    def test_penalty_multiplier_floor_50pct(self):
        t = _target(
            product_count=20, indication_count=10,
            manufacturing_complexity="high", geographic_complexity="global",
            payer_access_complexity="high", salesforce_required=True,
            revenue_concentration=0.0,
        )
        cc = _compute_commercial_complexity(t)
        assert cc.penalty_multiplier >= 0.50

    def test_dual_execution_risk_note(self):
        t = _target(salesforce_required=True, manufacturing_complexity="high")
        cc = _compute_commercial_complexity(t)
        assert any("dual_execution_risk" in n for n in cc.notes)

    def test_high_complexity_concentrated_revenue_note(self):
        t = _target(
            product_count=10, manufacturing_complexity="high",
            geographic_complexity="global", payer_access_complexity="high",
            revenue_concentration=0.85, salesforce_required=False,
        )
        cc = _compute_commercial_complexity(t)
        if cc.complexity_score > 0.60:
            assert any("manageable" in n for n in cc.notes)

    def test_components_keys_present(self):
        t = _target()
        cc = _compute_commercial_complexity(t)
        assert set(cc.components.keys()) == {
            "product_count", "indication_count", "revenue_dispersion",
            "salesforce", "manufacturing", "geography", "payer_access",
        }


# ===========================================================================
# 0F — Distress Quality Guard
# ===========================================================================

class TestDistressGuard:
    def test_guard_fires_when_all_conditions_met(self):
        t = _target(
            financing_pressure_high=True,
            lead_asset_quality_low=True,
            is_platform_company=False,
        )
        dg = _evaluate_distress_guard(t)
        assert dg.guard_active is True
        assert dg.mna_probability_cap == pytest.approx(0.25)
        assert dg.reason_code == "distress_without_strategic_asset"

    def test_guard_not_active_when_platform(self):
        # Platform companies retain strategic value even under distress
        t = _target(
            financing_pressure_high=True,
            lead_asset_quality_low=True,
            is_platform_company=True,
        )
        dg = _evaluate_distress_guard(t)
        assert dg.guard_active is False

    def test_guard_not_active_quality_ok(self):
        t = _target(financing_pressure_high=True, lead_asset_quality_low=False)
        dg = _evaluate_distress_guard(t)
        assert dg.guard_active is False

    def test_guard_not_active_no_pressure(self):
        t = _target(financing_pressure_high=False, lead_asset_quality_low=True)
        dg = _evaluate_distress_guard(t)
        assert dg.guard_active is False

    def test_guard_cap_value(self):
        t = _target(financing_pressure_high=True, lead_asset_quality_low=True)
        dg = _evaluate_distress_guard(t)
        assert dg.guard_active is True
        assert dg.mna_probability_cap == pytest.approx(0.25)


# ===========================================================================
# 0G — Data Confidence Output
# ===========================================================================

class TestDataConfidence:
    def test_all_fields_present_high_confidence(self):
        t = _target()   # fixture has all 11 data flags True
        dc = _compute_data_confidence(t)
        assert dc.grade == DataConfidenceGrade.HIGH
        assert dc.score == pytest.approx(1.0)
        assert dc.eligible_for_ranked_output is True
        assert dc.eligible_for_diligence_queue is False

    def test_no_fields_low_confidence(self):
        t = TargetEligibilityInput(ticker="XYZ")
        dc = _compute_data_confidence(t)
        assert dc.grade == DataConfidenceGrade.LOW
        assert dc.score == pytest.approx(0.0)
        assert dc.eligible_for_ranked_output is False
        assert dc.eligible_for_diligence_queue is True

    def test_medium_confidence_eligible_ranked_and_diligence(self):
        # has_market_cap (0.12) + has_ev (0.12) + has_cash (0.10) +
        # has_clinical_stage (0.12) + has_trial_status (0.09) = 0.55 → MEDIUM
        t = TargetEligibilityInput(
            ticker="XYZ",
            has_market_cap=True,
            has_enterprise_value=True,
            has_cash_debt=True,
            has_clinical_stage=True,
            has_trial_status=True,
        )
        dc = _compute_data_confidence(t)
        assert dc.grade == DataConfidenceGrade.MEDIUM
        assert dc.eligible_for_ranked_output is True
        assert dc.eligible_for_diligence_queue is True

    def test_missing_fields_listed(self):
        t = TargetEligibilityInput(ticker="XYZ", has_market_cap=True)
        dc = _compute_data_confidence(t)
        assert "enterprise_value" in dc.missing_fields
        assert "clinical_stage" in dc.missing_fields
        assert "market_cap" not in dc.missing_fields

    def test_score_monotone_with_fields(self):
        t1 = TargetEligibilityInput(ticker="XYZ", has_market_cap=True)
        t2 = TargetEligibilityInput(ticker="XYZ", has_market_cap=True, has_enterprise_value=True)
        dc1 = _compute_data_confidence(t1)
        dc2 = _compute_data_confidence(t2)
        assert dc2.score > dc1.score


# ===========================================================================
# Integration — evaluate_layer0
# ===========================================================================

class TestEvaluateLayer0:
    def test_valid_target_passes_exclusion(self):
        t = _target()
        r = evaluate_layer0(t)
        assert r.passes_hard_exclusion is True
        assert r.exclusion_code is None

    def test_excluded_target_has_no_deal_type(self):
        t = _target(company_taxonomy=CompanyTaxonomy.ACQUIRER)
        r = evaluate_layer0(t)
        assert r.passes_hard_exclusion is False
        assert r.deal_type is None

    def test_commercial_target_routes_not_excluded(self):
        # Key regression: approved_revenue > 50% must NOT hard-fail
        t = _target(approved_revenue_share=0.75)
        r = evaluate_layer0(t)
        assert r.passes_hard_exclusion is True
        assert r.deal_type == DealType.COMMERCIAL_FRANCHISE_ACQUISITION

    def test_affordability_populated_with_acquirers(self):
        t = _target()
        acq = _acquirer()
        r = evaluate_layer0(t, acquirers=[acq])
        assert len(r.affordability) == 1

    def test_affordability_empty_without_acquirers(self):
        t = _target()
        r = evaluate_layer0(t)
        assert r.affordability == []

    def test_combined_multiplier_product_of_encumbrance_and_complexity(self):
        t = _target(has_ip_dispute=True, manufacturing_complexity="high",
                    geographic_complexity="global")
        r = evaluate_layer0(t)
        expected = r.encumbrance.penalty_multiplier * r.commercial_complexity.penalty_multiplier
        assert r.score_multiplier == pytest.approx(expected, rel=1e-5)

    def test_distress_guard_cap_propagated(self):
        t = _target(financing_pressure_high=True, lead_asset_quality_low=True)
        r = evaluate_layer0(t)
        assert r.score_cap == pytest.approx(0.25)
        assert any("distress_guard_cap" in n for n in r.layer0_notes)

    def test_no_distress_guard_score_cap_is_none(self):
        t = _target(financing_pressure_high=False)
        r = evaluate_layer0(t)
        assert r.score_cap is None

    def test_result_is_frozen(self):
        t = _target()
        r = evaluate_layer0(t)
        with pytest.raises(Exception):
            r.passes_hard_exclusion = False  # type: ignore[misc]

    def test_encumbrance_computed_even_for_excluded(self):
        # Diagnostics available even when excluded
        t = _target(
            company_taxonomy=CompanyTaxonomy.ACQUIRER,
            has_ip_dispute=True,
        )
        r = evaluate_layer0(t)
        assert r.passes_hard_exclusion is False
        assert r.encumbrance.has_ip_dispute is True

    def test_layer0_result_fields_types(self):
        t = _target()
        r = evaluate_layer0(t)
        assert isinstance(r, Layer0Result)
        assert isinstance(r.encumbrance, EncumbranceFlags)
        assert isinstance(r.commercial_complexity, CommercialComplexityScore)
        assert isinstance(r.data_confidence.grade, DataConfidenceGrade)
