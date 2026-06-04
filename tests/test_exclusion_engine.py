"""Tests for the 11-gate M&A hard exclusion / routing layer.

Covers the acceptance criteria specified in the implementation brief:

1.  Already acquired company (INBX) → HISTORICAL_ONLY, live_ranking_eligible=False,
    historical_training_eligible=True.
2.  TPTX / RETA historical examples → HISTORICAL_ONLY.
3.  Self-acquisition pair → PAIR_LEVEL_FAIL.
4.  Company with no identifiable lead asset / platform → HARD_FAIL.
5.  Lead asset fully licensed away → ROUTE_TO_OTHER_MODEL (licensing model).
6.  Severe going-concern warning → ROUTE_TO_OTHER_MODEL (distressed optionality).
7.  Stale market data → REFRESH_REQUIRED.
8.  Weak IP / short exclusivity → SEVERE_CAP with cap ≤ 0.55.
9.  Commercial-only company → ROUTE_TO_OTHER_MODEL (commercial franchise).
10. Valid company with clean data → PASS and eligible for live scoring.

Additional tests cover:
- Gate 0: SPAC, holding company, CRO, royalty, nonprofit, government
- Gate 2: antitrust, affordability, existing majority control
- Gate 4: failed pivotal with/without salvage, abandoned, clinical hold
- Gate 7: illiquid, OTC/pink sheet, very stale data
- Gate 8: sanctions, confirmed fraud, data integrity, SEC enforcement
- Gate 9: tiny market, no unmet need, undifferentiated asset
- Gate 10: explicit routing via deal_type_classification
- apply_exclusion_assessment_to_score: PASS, SEVERE_CAP, HARD_FAIL, HISTORICAL_ONLY
- most_severe helper
- ExclusionRuleConfigLoader: YAML load, get_rule
- Integration: ma_eligibility.evaluate_layer0 uses engine via _evaluate_hard_exclusion
"""
from __future__ import annotations

import pytest

from bve.intelligence.exclusions import (
    AcquirerProfile,
    CompanyProfile,
    ExclusionAssessment,
    ExclusionEngine,
    ExclusionStatus,
    GateName,
    RoutingModel,
    apply_exclusion_assessment_to_score,
    evaluate_company_exclusions,
    evaluate_pair_exclusions,
    most_severe,
)
from bve.intelligence.exclusions.enums import _SEVERITY_RANK


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_company(company_id: str = "CLEAN", ticker: str = "CLEAN") -> CompanyProfile:
    """Minimal valid company profile that should PASS all gates."""
    return CompanyProfile(
        company_id=company_id,
        ticker=ticker,
        entity_type="biotech",
        corporate_status="active",
        has_lead_asset=True,
        has_platform=False,
        has_active_pipeline=True,
        lead_asset_status="active",
        ip_ownership_status="owned",
        ip_durability="strong",
        financial_status="healthy",
        listing_type="major_exchange",
    )


def _clean_acquirer(acquirer_id: str = "BIG_PHARMA", ticker: str = "BPH") -> AcquirerProfile:
    return AcquirerProfile(
        acquirer_id=acquirer_id,
        ticker=ticker,
        cash_available_millions=10_000.0,
        debt_capacity_millions=5_000.0,
    )


engine = ExclusionEngine()


# ===========================================================================
# Acceptance Criteria Tests (AC1–AC10)
# ===========================================================================

class TestAcceptanceCriteria:
    """Verify the 10 acceptance criteria from the implementation brief."""

    # AC1 — already acquired company
    def test_ac1_inbx_already_acquired(self):
        profile = CompanyProfile(
            company_id="INBX",
            ticker="INBX",
            entity_type="biotech",
            corporate_status="acquired",
        )
        result = evaluate_company_exclusions(profile)
        assert result.overall_status == ExclusionStatus.HISTORICAL_ONLY
        assert result.live_ranking_eligible is False
        assert result.historical_training_eligible is True
        assert apply_exclusion_assessment_to_score(0.85, result) is None

    # AC2 — TPTX and RETA historical examples
    @pytest.mark.parametrize("ticker,status", [
        ("TPTX", "acquired"),
        ("RETA", "merged"),
    ])
    def test_ac2_historical_acquired_tickers(self, ticker, status):
        profile = CompanyProfile(
            company_id=ticker,
            ticker=ticker,
            entity_type="biotech",
            corporate_status=status,
        )
        result = evaluate_company_exclusions(profile)
        assert result.overall_status == ExclusionStatus.HISTORICAL_ONLY
        assert result.live_ranking_eligible is False
        assert result.historical_training_eligible is True

    # AC3 — self-acquisition pair
    def test_ac3_self_acquisition_pair(self):
        target = _clean_company("SELF", "SELF")
        acquirer = AcquirerProfile(
            acquirer_id="SELF",
            ticker="SELF",
            cash_available_millions=10_000.0,
        )
        result = evaluate_pair_exclusions(target, acquirer)
        # Pair-level fail: the pair is invalid but company can rank with others
        pair_gate = next(
            g for g in result.all_gate_results
            if g.gate_name == GateName.GATE_2_BUYER_TARGET_VALIDITY
        )
        assert pair_gate.status == ExclusionStatus.PAIR_LEVEL_FAIL
        assert "G2.SELF_ACQUISITION" in pair_gate.triggered_rules
        # pair-level fail → score is None
        assert apply_exclusion_assessment_to_score(0.85, result) is None

    # AC4 — no identifiable lead asset or platform
    def test_ac4_no_identifiable_asset(self):
        profile = CompanyProfile(
            company_id="NOASSET",
            ticker="NOASSET",
            entity_type="biotech",
            has_lead_asset=False,
            has_platform=False,
            has_active_pipeline=False,
            has_commercial_product=False,
        )
        result = evaluate_company_exclusions(profile)
        assert result.overall_status == ExclusionStatus.HARD_FAIL
        assert result.live_ranking_eligible is False
        assert apply_exclusion_assessment_to_score(0.80, result) is None

    # AC5 — lead asset fully licensed away → ROUTE_TO_OTHER_MODEL (licensing)
    def test_ac5_fully_licensed_away(self):
        profile = CompanyProfile(
            company_id="LICENSED",
            ticker="LIC",
            entity_type="biotech",
            ip_ownership_status="fully_licensed_away",
        )
        result = evaluate_company_exclusions(profile)
        assert result.overall_status == ExclusionStatus.ROUTE_TO_OTHER_MODEL
        assert result.routed_model == RoutingModel.LICENSING_MODEL
        assert result.live_ranking_eligible is False
        assert apply_exclusion_assessment_to_score(0.80, result) is None

    # AC6 — severe going-concern warning → ROUTE_TO_OTHER_MODEL (distressed)
    def test_ac6_going_concern_warning(self):
        profile = CompanyProfile(
            company_id="DISTRESS",
            ticker="DIST",
            entity_type="biotech",
            financial_status="going_concern_warning",
        )
        result = evaluate_company_exclusions(profile)
        assert result.overall_status == ExclusionStatus.ROUTE_TO_OTHER_MODEL
        assert result.routed_model == RoutingModel.DISTRESSED_OPTIONALITY_MODEL
        assert result.live_ranking_eligible is False

    # AC7 — stale market data → REFRESH_REQUIRED
    def test_ac7_stale_market_data(self):
        profile = CompanyProfile(
            company_id="STALE",
            ticker="STA",
            entity_type="biotech",
            market_data_staleness_days=45,
        )
        result = evaluate_company_exclusions(profile)
        # 45 days > 30d threshold → REFRESH_REQUIRED
        gate = next(
            g for g in result.all_gate_results
            if g.gate_name == GateName.GATE_7_MARKET_DATA_QUALITY
        )
        assert gate.status == ExclusionStatus.REFRESH_REQUIRED
        assert result.live_ranking_eligible is False

    # AC8 — weak IP → SEVERE_CAP with cap ≤ 0.55
    def test_ac8_weak_ip_severe_cap(self):
        profile = CompanyProfile(
            company_id="WEAKIP",
            ticker="WIP",
            entity_type="biotech",
            ip_durability="weak",
        )
        result = evaluate_company_exclusions(profile)
        assert result.overall_status == ExclusionStatus.SEVERE_CAP
        assert result.max_score_cap is not None
        assert result.max_score_cap <= 0.55
        # Score above cap is reduced to cap
        assert apply_exclusion_assessment_to_score(0.80, result) == pytest.approx(result.max_score_cap)
        # Score below cap is unchanged
        assert apply_exclusion_assessment_to_score(0.30, result) == pytest.approx(0.30)

    # AC9 — commercial-only classification → ROUTE_TO_OTHER_MODEL (commercial franchise)
    def test_ac9_commercial_only_routing(self):
        profile = CompanyProfile(
            company_id="COMM",
            ticker="COMM",
            entity_type="biotech",
            deal_type_classification="commercial_only",
        )
        result = evaluate_company_exclusions(profile)
        assert result.overall_status == ExclusionStatus.ROUTE_TO_OTHER_MODEL
        assert result.routed_model == RoutingModel.COMMERCIAL_FRANCHISE_MODEL

    # AC10 — clean company → PASS
    def test_ac10_valid_company_pass(self):
        result = evaluate_company_exclusions(_clean_company())
        assert result.overall_status == ExclusionStatus.PASS
        assert result.live_ranking_eligible is True
        assert result.historical_training_eligible is True
        assert result.max_score_cap is None
        assert apply_exclusion_assessment_to_score(0.85, result) == pytest.approx(0.85)


# ===========================================================================
# Gate 0 — Entity Validity
# ===========================================================================

class TestGate0EntityValidity:
    def test_spac_hard_fail(self):
        p = CompanyProfile(company_id="SPAC1", entity_type="spac_shell")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL
        assert "G0.SPAC_SHELL" in r.triggered_exclusion_rules

    def test_holding_company_hard_fail(self):
        p = CompanyProfile(company_id="HC", entity_type="holding_company")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_royalty_company_routed(self):
        p = CompanyProfile(company_id="RC", entity_type="royalty_company")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.ROUTE_TO_OTHER_MODEL
        assert r.routed_model == RoutingModel.ROYALTY_MODEL

    def test_cro_cdmo_routed(self):
        p = CompanyProfile(company_id="CRO", entity_type="cro_cdmo")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.ROUTE_TO_OTHER_MODEL
        assert r.routed_model == RoutingModel.SERVICES_MA_MODEL

    def test_nonprofit_hard_fail(self):
        p = CompanyProfile(company_id="NP", entity_type="research_nonprofit")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_government_restricted_hard_fail(self):
        p = CompanyProfile(company_id="GOV", entity_type="government_controlled",
                           is_government_restricted=True)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_government_uncertain_diligence(self):
        p = CompanyProfile(company_id="GOV2", entity_type="government_controlled",
                           is_government_restricted=False)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.DILIGENCE_QUEUE

    def test_known_acquirer_hard_fail(self):
        p = CompanyProfile(company_id="BIG", entity_type="biotech", is_known_acquirer=True)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL
        assert "G0.KNOWN_ACQUIRER" in r.triggered_exclusion_rules

    def test_valid_biotech_passes_gate0(self):
        p = _clean_company()
        r = evaluate_company_exclusions(p)
        g0 = next(g for g in r.all_gate_results if g.gate_name == GateName.GATE_0_ENTITY_VALIDITY)
        assert g0.status == ExclusionStatus.PASS


# ===========================================================================
# Gate 1 — Corporate Status
# ===========================================================================

class TestGate1CorporateStatus:
    @pytest.mark.parametrize("status", ["acquired", "merged", "delisted_takeout"])
    def test_historical_only_statuses(self, status):
        p = CompanyProfile(company_id="X", entity_type="biotech", corporate_status=status)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HISTORICAL_ONLY
        assert r.historical_training_eligible is True

    def test_pending_acquisition_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           corporate_status="pending_acquisition")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_bankrupt_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           corporate_status="bankrupt")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_post_spin_diligence_queue(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           corporate_status="post_spin")
        r = evaluate_company_exclusions(p)
        gate1 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_1_CORPORATE_STATUS)
        assert gate1.status == ExclusionStatus.DILIGENCE_QUEUE

    def test_ticker_mismatch_refresh(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           corporate_status="ticker_mismatch")
        r = evaluate_company_exclusions(p)
        gate1 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_1_CORPORATE_STATUS)
        assert gate1.status == ExclusionStatus.REFRESH_REQUIRED


# ===========================================================================
# Gate 2 — Buyer-Target Validity (pair-level)
# ===========================================================================

class TestGate2BuyerTargetValidity:
    def test_self_acquisition_via_company_id(self):
        target = _clean_company("SAME", "SAME")
        acq = AcquirerProfile(acquirer_id="SAME", ticker="SAME",
                              cash_available_millions=5_000.0)
        r = evaluate_pair_exclusions(target, acq)
        gate2 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_2_BUYER_TARGET_VALIDITY)
        assert gate2.status == ExclusionStatus.PAIR_LEVEL_FAIL

    def test_existing_majority_control_pair_fail(self):
        target = _clean_company("TARGET", "TGT")
        acq = AcquirerProfile(acquirer_id="ACQ", ticker="ACQ",
                              cash_available_millions=5_000.0,
                              has_majority_control=True)
        r = evaluate_pair_exclusions(target, acq)
        gate2 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_2_BUYER_TARGET_VALIDITY)
        assert gate2.status == ExclusionStatus.PAIR_LEVEL_FAIL
        assert "G2.EXISTING_CONTROL" in gate2.triggered_rules

    def test_affordability_fail_when_capacity_tiny(self):
        # market cap $10B, acquirer has only $100M total
        target = CompanyProfile(company_id="BIG", ticker="BIG",
                                entity_type="biotech",
                                market_cap_millions=10_000.0)
        acq = AcquirerProfile(acquirer_id="TINY", ticker="TINY",
                              cash_available_millions=100.0,
                              expected_premium=0.35)
        r = evaluate_pair_exclusions(target, acq)
        gate2 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_2_BUYER_TARGET_VALIDITY)
        assert gate2.status == ExclusionStatus.PAIR_LEVEL_FAIL
        assert "G2.AFFORDABILITY" in gate2.triggered_rules

    def test_antitrust_block_pair_fail(self):
        target = _clean_company("TGT", "TGT")
        acq = AcquirerProfile(acquirer_id="ACQ", ticker="ACQ",
                              cash_available_millions=50_000.0,
                              antitrust_block_probability=0.90)
        r = evaluate_pair_exclusions(target, acq)
        gate2 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_2_BUYER_TARGET_VALIDITY)
        assert gate2.status == ExclusionStatus.PAIR_LEVEL_FAIL
        assert "G2.ANTITRUST" in gate2.triggered_rules

    def test_merger_of_equals_routed(self):
        target = _clean_company("TGT", "TGT")
        acq = AcquirerProfile(acquirer_id="ACQ", ticker="ACQ",
                              cash_available_millions=50_000.0,
                              is_merger_of_equals=True)
        r = evaluate_pair_exclusions(target, acq)
        gate2 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_2_BUYER_TARGET_VALIDITY)
        assert gate2.status == ExclusionStatus.ROUTE_TO_OTHER_MODEL
        assert gate2.route_to_model == RoutingModel.MERGER_OF_EQUALS_MODEL

    def test_valid_pair_passes_gate2(self):
        target = _clean_company("TGT", "TGT")
        acq = _clean_acquirer()
        r = evaluate_pair_exclusions(target, acq)
        gate2 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_2_BUYER_TARGET_VALIDITY)
        assert gate2.status == ExclusionStatus.PASS


# ===========================================================================
# Gate 3 — Asset Visibility
# ===========================================================================

class TestGate3AssetVisibility:
    def test_no_value_driver_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           has_lead_asset=False, has_platform=False,
                           has_active_pipeline=False, has_commercial_product=False)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL
        assert "G3.NO_VALUE_DRIVER" in r.triggered_exclusion_rules

    def test_missing_pipeline_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           has_lead_asset=True,
                           pipeline_description_quality="missing")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL
        assert "G3.MISSING_PIPELINE" in r.triggered_exclusion_rules

    def test_vague_pipeline_diligence(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           has_lead_asset=True,
                           pipeline_description_quality="vague")
        r = evaluate_company_exclusions(p)
        gate3 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_3_ASSET_VISIBILITY)
        assert gate3.status == ExclusionStatus.DILIGENCE_QUEUE


# ===========================================================================
# Gate 4 — Asset Viability
# ===========================================================================

class TestGate4AssetViability:
    def test_discontinued_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           lead_asset_status="discontinued")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_failed_pivotal_no_path_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           lead_asset_status="failed_pivotal",
                           has_salvage_path=False)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_failed_pivotal_with_salvage_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           lead_asset_status="failed_pivotal",
                           has_salvage_path=True)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.40)

    def test_safety_blocked_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           lead_asset_status="safety_blocked")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_mechanism_invalidated_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           lead_asset_status="mechanism_invalidated")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.40)

    def test_weak_signal_severe_cap_060(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           lead_asset_status="weak_signal_single_study")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.60)

    def test_clinical_hold_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           clinical_hold_unresolved=True)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.40)

    def test_abandoned_with_salvage_refresh(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           lead_asset_status="abandoned",
                           has_salvage_path=True)
        r = evaluate_company_exclusions(p)
        gate4 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_4_ASSET_VIABILITY)
        assert gate4.status == ExclusionStatus.REFRESH_REQUIRED


# ===========================================================================
# Gate 5 — Rights / IP / Ownership
# ===========================================================================

class TestGate5RightsIP:
    def test_fully_licensed_away_routes_to_licensing(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           ip_ownership_status="fully_licensed_away")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.ROUTE_TO_OTHER_MODEL
        assert r.routed_model == RoutingModel.LICENSING_MODEL

    def test_territory_unavailable_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           ip_ownership_status="key_territory_unavailable")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.55)

    def test_co_owned_disputed_diligence(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           ip_ownership_status="co_owned_disputed")
        r = evaluate_company_exclusions(p)
        gate5 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_5_RIGHTS_IP_OWNERSHIP)
        assert gate5.status == ExclusionStatus.DILIGENCE_QUEUE

    def test_short_exclusivity_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           ip_durability="short_exclusivity")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.55)

    def test_royalty_stack_high_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           royalty_stack_rate=0.25)  # > 20% threshold
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.55)

    def test_royalty_stack_low_passes(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           royalty_stack_rate=0.10)  # < 20% threshold
        r = evaluate_company_exclusions(p)
        gate5 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_5_RIGHTS_IP_OWNERSHIP)
        assert gate5.status == ExclusionStatus.PASS


# ===========================================================================
# Gate 6 — Financial / Going-Concern
# ===========================================================================

class TestGate6Financial:
    def test_bankrupt_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           financial_status="bankrupt")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_liquidating_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           financial_status="liquidating")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_going_concern_routes_to_distress(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           financial_status="going_concern_warning")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.ROUTE_TO_OTHER_MODEL
        assert r.routed_model == RoutingModel.DISTRESSED_OPTIONALITY_MODEL

    def test_negative_ev_distressed_routes_to_distress(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           financial_status="negative_ev_distressed")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.ROUTE_TO_OTHER_MODEL
        assert r.routed_model == RoutingModel.DISTRESSED_OPTIONALITY_MODEL

    def test_missing_financial_data_diligence(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           financial_data_missing=True)
        r = evaluate_company_exclusions(p)
        gate6 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_6_FINANCIAL_GOING_CONCERN)
        assert gate6.status == ExclusionStatus.DILIGENCE_QUEUE


# ===========================================================================
# Gate 7 — Market Data Quality
# ===========================================================================

class TestGate7MarketData:
    def test_stale_30d_refresh_required(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           market_data_staleness_days=35)
        r = evaluate_company_exclusions(p)
        gate7 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_7_MARKET_DATA_QUALITY)
        assert gate7.status == ExclusionStatus.REFRESH_REQUIRED

    def test_very_stale_90d_diligence(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           market_data_staleness_days=100)
        r = evaluate_company_exclusions(p)
        gate7 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_7_MARKET_DATA_QUALITY)
        assert gate7.status == ExclusionStatus.DILIGENCE_QUEUE

    def test_otc_pink_diligence(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           listing_type="otc_pink")
        r = evaluate_company_exclusions(p)
        gate7 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_7_MARKET_DATA_QUALITY)
        assert gate7.status == ExclusionStatus.DILIGENCE_QUEUE

    def test_illiquid_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           avg_daily_volume_usd_millions=0.2)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.65)

    def test_corporate_action_unresolved_refresh(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           recent_corporate_action_unresolved=True)
        r = evaluate_company_exclusions(p)
        gate7 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_7_MARKET_DATA_QUALITY)
        assert gate7.status == ExclusionStatus.REFRESH_REQUIRED


# ===========================================================================
# Gate 8 — Legal / Integrity
# ===========================================================================

class TestGate8Legal:
    def test_sanctions_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech", has_sanctions=True)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL
        assert "G8.SANCTIONS" in r.triggered_exclusion_rules

    def test_confirmed_fraud_hard_fail(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           fraud_severity="confirmed")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HARD_FAIL
        assert "G8.FRAUD_CONFIRMED" in r.triggered_exclusion_rules

    def test_fraud_allegation_severe_cap_035(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           has_fraud_allegation=True, fraud_severity="allegation")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.35)

    def test_clinical_data_integrity_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           has_clinical_data_integrity_issue=True)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.50)

    def test_sec_enforcement_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           has_sec_enforcement_cloud=True)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.50)

    def test_major_asset_litigation_diligence(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           has_major_asset_litigation=True)
        r = evaluate_company_exclusions(p)
        gate8 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_8_LEGAL_INTEGRITY)
        assert gate8.status == ExclusionStatus.DILIGENCE_QUEUE

    def test_gmp_failure_diligence(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           has_gmp_failure=True)
        r = evaluate_company_exclusions(p)
        gate8 = next(g for g in r.all_gate_results
                     if g.gate_name == GateName.GATE_8_LEGAL_INTEGRITY)
        assert gate8.status == ExclusionStatus.DILIGENCE_QUEUE


# ===========================================================================
# Gate 9 — Commercial Relevance
# ===========================================================================

class TestGate9CommercialRelevance:
    def test_tiny_market_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           addressable_market_size="tiny")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.60)

    def test_no_unmet_need_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech", has_unmet_need=False)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP

    def test_undifferentiated_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech", is_differentiated=False)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP

    def test_reimbursement_impossible_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           reimbursement_feasibility="impossible")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP

    def test_severe_generic_pressure_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           generic_biosimilar_pressure="severe")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP

    def test_high_adoption_barriers_severe_cap(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           adoption_barriers="high")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP


# ===========================================================================
# Gate 10 — Model Routing
# ===========================================================================

class TestGate10ModelRouting:
    """Gate 10 behaviour after the 0A/0B refactor (2026-06-04).

    Gate 10 is now a pure pass-through for all deal-type classifications.
    Model routing is owned by Layer 0B (classify_deal_structure_route).
    Only the 'historical_training' sentinel triggers a non-PASS outcome.
    """

    # ── All deal-type values now PASS Gate 10 ────────────────────────────────
    @pytest.mark.parametrize("dtc", [
        # Legacy Gate 10 literals — normalise via _LEGACY_GATE10_MAP then PASS
        "licensing_only",
        "distress_only",
        "commercial_only",
        "platform_only",
        # Canonical DealType values
        "asset_license_partnership",
        "distressed_optionality",
        "commercial_franchise_acquisition",
        "platform_acquisition",
        "single_asset_takeout",
        "pipeline_portfolio_takeout",
    ])
    def test_all_deal_type_values_pass_gate10(self, dtc):
        """After 0A/0B refactor: all deal-type values PASS Gate 10.
        Model routing is now owned by Layer 0B (DealStructureRoute).
        """
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           deal_type_classification=dtc)
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.PASS, (
            f"{dtc!r} should PASS Gate 10 after 0A/0B refactor; got {r.overall_status}. "
            "Model routing for deal types is now owned by Layer 0B."
        )
        assert r.routed_model is None, (
            f"{dtc!r} should not produce a routed_model in Gate 10; got {r.routed_model}. "
            "DealStructureRoute in Layer 0B owns routing."
        )

    def test_historical_training_classification(self):
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           deal_type_classification="historical_training")
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.HISTORICAL_ONLY
        assert r.historical_training_eligible is True

    def test_standard_pipeline_passes(self):
        """Legacy 'standard_pipeline' maps to PASS via _LEGACY_GATE10_MAP."""
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           deal_type_classification="standard_pipeline")
        r = evaluate_company_exclusions(p)
        gate10 = next(g for g in r.all_gate_results
                      if g.gate_name == GateName.GATE_10_MODEL_ROUTING)
        assert gate10.status == ExclusionStatus.PASS

    @pytest.mark.parametrize("dtc", [
        "single_asset_takeout",
        "pipeline_portfolio_takeout",
    ])
    def test_canonical_standard_types_pass(self, dtc):
        """Canonical types that run through the standard M&A model → PASS at Gate 10."""
        p = CompanyProfile(company_id="X", entity_type="biotech",
                           deal_type_classification=dtc)
        r = evaluate_company_exclusions(p)
        gate10 = next(g for g in r.all_gate_results
                      if g.gate_name == GateName.GATE_10_MODEL_ROUTING)
        assert gate10.status == ExclusionStatus.PASS
        # Must not route away from the standard M&A model
        assert r.routed_model is None

    def test_legacy_and_canonical_both_pass_gate10(self):
        """Legacy 'licensing_only' and canonical 'asset_license_partnership' both PASS Gate 10."""
        from bve.intelligence.exclusions import evaluate_company_exclusions as ece
        p_legacy = CompanyProfile(company_id="X", entity_type="biotech",
                                  deal_type_classification="licensing_only")
        p_canonical = CompanyProfile(company_id="X", entity_type="biotech",
                                     deal_type_classification="asset_license_partnership")
        r_legacy = ece(p_legacy)
        r_canonical = ece(p_canonical)
        assert r_legacy.overall_status == ExclusionStatus.PASS
        assert r_canonical.overall_status == ExclusionStatus.PASS
        assert r_legacy.routed_model is None
        assert r_canonical.routed_model is None

    def test_none_classification_passes(self):
        p = _clean_company()
        r = evaluate_company_exclusions(p)
        gate10 = next(g for g in r.all_gate_results
                      if g.gate_name == GateName.GATE_10_MODEL_ROUTING)
        assert gate10.status == ExclusionStatus.PASS


# ===========================================================================
# Score application
# ===========================================================================

class TestApplyExclusionAssessmentToScore:
    def _make_assessment(self, status: ExclusionStatus,
                         cap: float | None = None,
                         routed: RoutingModel | None = None) -> ExclusionAssessment:
        return ExclusionAssessment(
            company_id="X",
            overall_status=status,
            live_ranking_eligible=status == ExclusionStatus.PASS,
            historical_training_eligible=status in (
                ExclusionStatus.PASS, ExclusionStatus.HISTORICAL_ONLY,
                ExclusionStatus.SEVERE_CAP,
            ),
            max_score_cap=cap,
            routed_model=routed,
        )

    def test_pass_returns_raw_score(self):
        a = self._make_assessment(ExclusionStatus.PASS)
        assert apply_exclusion_assessment_to_score(0.85, a) == pytest.approx(0.85)

    def test_hard_fail_returns_none(self):
        a = self._make_assessment(ExclusionStatus.HARD_FAIL)
        assert apply_exclusion_assessment_to_score(0.85, a) is None

    def test_historical_only_returns_none(self):
        a = self._make_assessment(ExclusionStatus.HISTORICAL_ONLY)
        assert apply_exclusion_assessment_to_score(0.85, a) is None

    def test_route_returns_none(self):
        a = self._make_assessment(ExclusionStatus.ROUTE_TO_OTHER_MODEL,
                                  routed=RoutingModel.LICENSING_MODEL)
        assert apply_exclusion_assessment_to_score(0.85, a) is None

    def test_severe_cap_clamps_score(self):
        a = self._make_assessment(ExclusionStatus.SEVERE_CAP, cap=0.55)
        assert apply_exclusion_assessment_to_score(0.85, a) == pytest.approx(0.55)
        assert apply_exclusion_assessment_to_score(0.40, a) == pytest.approx(0.40)

    def test_pair_level_fail_returns_none(self):
        a = self._make_assessment(ExclusionStatus.PAIR_LEVEL_FAIL)
        assert apply_exclusion_assessment_to_score(0.85, a) is None

    def test_pair_level_cap_clamps_score(self):
        a = self._make_assessment(ExclusionStatus.PAIR_LEVEL_CAP, cap=0.50)
        assert apply_exclusion_assessment_to_score(0.85, a) == pytest.approx(0.50)

    def test_diligence_queue_returns_none(self):
        a = self._make_assessment(ExclusionStatus.DILIGENCE_QUEUE)
        assert apply_exclusion_assessment_to_score(0.70, a) is None

    def test_refresh_required_returns_none(self):
        a = self._make_assessment(ExclusionStatus.REFRESH_REQUIRED)
        assert apply_exclusion_assessment_to_score(0.70, a) is None


# ===========================================================================
# most_severe helper
# ===========================================================================

class TestMostSevere:
    def test_empty_returns_pass(self):
        assert most_severe([]) == ExclusionStatus.PASS

    def test_single_element(self):
        assert most_severe([ExclusionStatus.SEVERE_CAP]) == ExclusionStatus.SEVERE_CAP

    def test_hard_fail_wins_over_severe_cap(self):
        statuses = [ExclusionStatus.SEVERE_CAP, ExclusionStatus.HARD_FAIL,
                    ExclusionStatus.DILIGENCE_QUEUE]
        assert most_severe(statuses) == ExclusionStatus.HARD_FAIL

    def test_historical_only_wins_over_route(self):
        statuses = [ExclusionStatus.ROUTE_TO_OTHER_MODEL, ExclusionStatus.HISTORICAL_ONLY]
        assert most_severe(statuses) == ExclusionStatus.HISTORICAL_ONLY

    def test_severity_rank_ordering(self):
        """Verify severity rank is monotonically assigned."""
        from bve.intelligence.exclusions.enums import _SEVERITY_ORDER, _SEVERITY_RANK
        for i, status in enumerate(_SEVERITY_ORDER):
            assert _SEVERITY_RANK[status] == i


# ===========================================================================
# Pair-level vs company-level independence
# ===========================================================================

class TestPairLevelVsCompanyLevel:
    """Pair-level fail must not incorrectly exclude the company from all buyers."""

    def test_pair_fail_does_not_block_company_against_other_buyers(self):
        """PAIR_LEVEL_FAIL is recorded on gate2; other company gates still PASS."""
        target = _clean_company("TGT", "TGT")
        bad_acq = AcquirerProfile(acquirer_id="TGT", ticker="TGT",  # self-acquisition
                                  cash_available_millions=10_000.0)

        pair_result = evaluate_pair_exclusions(target, bad_acq)

        # Company itself is valid
        company_result = evaluate_company_exclusions(target)
        assert company_result.live_ranking_eligible is True

        # Only the bad pair is excluded
        gate2 = next(g for g in pair_result.all_gate_results
                     if g.gate_name == GateName.GATE_2_BUYER_TARGET_VALIDITY)
        assert gate2.is_pair_level is True
        assert gate2.is_company_level is False


# ===========================================================================
# Multi-gate severity collapse
# ===========================================================================

class TestMultiGateSeverityCollapse:
    def test_hard_fail_overrides_severe_cap(self):
        """A company with both a failed asset AND stale data → HARD_FAIL wins."""
        p = CompanyProfile(
            company_id="X",
            entity_type="biotech",
            lead_asset_status="safety_blocked",        # Gate 4: HARD_FAIL
            avg_daily_volume_usd_millions=0.1,         # Gate 7: SEVERE_CAP
        )
        r = evaluate_company_exclusions(p)
        # Engine short-circuits at HARD_FAIL from Gate 4
        assert r.overall_status == ExclusionStatus.HARD_FAIL

    def test_most_restrictive_cap_selected(self):
        """When multiple SEVERE_CAP gates fire, the lowest cap wins."""
        p = CompanyProfile(
            company_id="X",
            entity_type="biotech",
            lead_asset_status="weak_signal_single_study",  # G4: cap 0.60
            ip_durability="weak",                           # G5: cap 0.55
        )
        r = evaluate_company_exclusions(p)
        assert r.overall_status == ExclusionStatus.SEVERE_CAP
        assert r.max_score_cap == pytest.approx(0.55)  # lower cap wins


# ===========================================================================
# Config loader
# ===========================================================================

class TestExclusionRuleConfigLoader:
    def test_loader_returns_rules_when_yaml_present(self):
        from bve.intelligence.exclusions.config_loader import ExclusionRuleConfigLoader
        loader = ExclusionRuleConfigLoader()
        rules = loader.all_rules()
        # The YAML has many rules; just verify basic structure
        assert len(rules) > 0
        for r in rules:
            assert r.rule_id
            assert r.gate_name
            assert r.default_status in (
                "HARD_FAIL", "HISTORICAL_ONLY", "ROUTE_TO_OTHER_MODEL",
                "SEVERE_CAP", "DILIGENCE_QUEUE", "REFRESH_REQUIRED",
                "PAIR_LEVEL_FAIL", "PAIR_LEVEL_CAP",
            )

    def test_get_rule_by_id(self):
        from bve.intelligence.exclusions.config_loader import ExclusionRuleConfigLoader
        loader = ExclusionRuleConfigLoader()
        rule = loader.get_rule("G4.FAILED_PIVOTAL_SALVAGE")
        assert rule is not None
        assert rule.default_cap == pytest.approx(0.40)
        assert rule.default_status == "SEVERE_CAP"

    def test_get_rule_missing_returns_none(self):
        from bve.intelligence.exclusions.config_loader import ExclusionRuleConfigLoader
        loader = ExclusionRuleConfigLoader()
        assert loader.get_rule("NONEXISTENT.RULE") is None

    def test_loader_handles_missing_file_gracefully(self):
        from bve.intelligence.exclusions.config_loader import ExclusionRuleConfigLoader
        loader = ExclusionRuleConfigLoader(config_path="/nonexistent/path.yaml")
        # Should return empty list, not raise
        assert loader.all_rules() == []


# ===========================================================================
# Integration: ma_eligibility.evaluate_layer0 uses exclusion engine
# ===========================================================================

class TestMaEligibilityIntegration:
    """Verify Layer0Result.hard_exclusion_assessment is populated."""

    def test_layer0_attaches_assessment_for_valid_company(self):
        from bve.intelligence.ma_eligibility import evaluate_layer0, TargetEligibilityInput
        target = TargetEligibilityInput(
            ticker="VALID",
            company_taxonomy="therapeutics",
            lead_asset_present=True,
            lead_asset_status="active",
            has_market_cap=True,
            has_enterprise_value=True,
            has_cash_debt=True,
            has_clinical_stage=True,
            has_trial_status=True,
            # All remaining data fields required for HIGH data confidence
            # (avoids Gate 6 financial_data_missing — added after Phase 1
            # tightened data confidence scoring with critical field caps)
            has_quarterly_burn=True,
            has_revenue_mix=True,
            has_asset_ownership_data=True,
            has_partner_rights_data=True,
            has_patent_loe_data=True,
            has_acquirer_profile_data=True,
        )
        result = evaluate_layer0(target)
        assert result.passes_hard_exclusion is True
        # Assessment should be attached
        assert result.hard_exclusion_assessment is not None
        assert result.hard_exclusion_assessment.live_ranking_eligible is True

    def test_layer0_hard_fail_for_spac(self):
        from bve.intelligence.ma_eligibility import evaluate_layer0, TargetEligibilityInput, ExclusionCode
        target = TargetEligibilityInput(
            ticker="SPAC1",
            company_taxonomy="spac_shell",
        )
        result = evaluate_layer0(target)
        assert result.passes_hard_exclusion is False
        assert result.exclusion_code == ExclusionCode.SPAC_SHELL

    def test_layer0_historical_only_for_acquired_company(self):
        from bve.intelligence.ma_eligibility import evaluate_layer0, TargetEligibilityInput, ExclusionCode
        # The old Layer0 doesn't have corporate_status; test via ExclusionCode mapping
        # This test verifies the bridge works even when only entity/asset data is known
        target = TargetEligibilityInput(
            ticker="INBX",
            company_taxonomy="therapeutics",
            lead_asset_present=False,        # triggers Gate 3 NO_VALUE_DRIVER
            is_platform_company=False,
        )
        result = evaluate_layer0(target)
        assert result.passes_hard_exclusion is False
        assert result.exclusion_code == ExclusionCode.NO_IDENTIFIABLE_ASSET
