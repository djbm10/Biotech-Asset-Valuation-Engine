"""Tests for Layer 3B route-aware scoring.

Coverage:
  A. REGIONAL_LICENSE + matching geography  → route relief, no geo penalty
  B. REGIONAL_LICENSE + wrong geography     → still penalized (wrong region = wrong region)
  C. FULL_COMPANY_TAKEOUT + regional split  → no route relief, geo mismatch penalized
  D1. MINORITY_EQUITY + encumbrances        → control penalty reduced
  D2. Fatal hard blocker (no_ownable_rights)→ overrides route, always fails
  E. fully_licensed_away + licensing route + economics retained → warning only
  F. fully_licensed_away + no economics     → still severe even on licensing route
  G. Route weight invariants and audit fields
"""
from __future__ import annotations

import pytest

from bve.intelligence.deal_type_classification import DealStructureRoute
from bve.intelligence.ma_asset_control_target import (
    AssetControlTargetInput,
    compute_asset_control_target,
)
from bve.intelligence.ma_pair_asset_control import (
    PairAssetControlInput,
    PairAssetControlResult,
    compute_pair_asset_control,
)


# ---------------------------------------------------------------------------
# Shared target builders
# ---------------------------------------------------------------------------

def _regional_target_inp(**kw) -> AssetControlTargetInput:
    """Target that only controls EU rights — poor global_rights/key_geography,
    but decent economics, IP, and manufacturing."""
    defaults = dict(
        global_rights_control=0.30,    # only regional rights, not global
        key_geography_control=0.40,    # US not available to buyer
        indication_control=0.85,
        change_of_control_freedom=0.75,
        royalty_cleanliness=0.80,
        milestone_burden=0.78,
        profit_share_cleanliness=0.82,
        cost_obligation_cleanliness=0.80,
        no_blocking_rights=0.80,
        clean_governance_control=0.80,
        partner_encumbrance_severity=0.80,
        patent_strength=0.82,
        exclusivity_runway=0.78,
        freedom_to_operate=0.85,
        ownership_cleanliness=0.88,
        process_transferability=0.78,
        supply_redundancy=0.72,
        gmp_quality_readiness=0.80,
        scale_capacity=0.75,
        manufacturing_complexity="low",
        clinical_data_completeness=0.75,
        cmc_package_completeness=0.72,
        regulatory_file_completeness=0.75,
        safety_database_quality=0.75,
        data_room_readiness=0.72,
        asset_rights_scope="regional_split",
    )
    defaults.update(kw)
    return AssetControlTargetInput(**defaults)


def _encumbered_target_inp(**kw) -> AssetControlTargetInput:
    """Target with ROFR, governance issues, consent complexity — but strong IP."""
    defaults = dict(
        global_rights_control=0.70,
        key_geography_control=0.70,
        indication_control=0.85,
        change_of_control_freedom=0.50,    # consent / CoC friction
        royalty_cleanliness=0.75,
        milestone_burden=0.72,
        profit_share_cleanliness=0.75,
        cost_obligation_cleanliness=0.72,
        no_blocking_rights=0.55,           # partner veto risk
        clean_governance_control=0.50,     # shared governance
        partner_encumbrance_severity=0.55,
        patent_strength=0.88,
        exclusivity_runway=0.85,
        freedom_to_operate=0.90,
        ownership_cleanliness=0.92,
        process_transferability=0.80,
        supply_redundancy=0.75,
        gmp_quality_readiness=0.82,
        scale_capacity=0.78,
        manufacturing_complexity="low",
        clinical_data_completeness=0.82,
        cmc_package_completeness=0.80,
        regulatory_file_completeness=0.82,
        safety_database_quality=0.80,
        data_room_readiness=0.80,
        has_existing_partnership=True,
        has_right_of_first_refusal=True,
    )
    defaults.update(kw)
    return AssetControlTargetInput(**defaults)


def _licensed_away_with_economics_inp() -> AssetControlTargetInput:
    """Fully licensed away but target retains royalties and profit-share economics."""
    return AssetControlTargetInput(
        global_rights_control=0.10,
        key_geography_control=0.10,
        indication_control=0.85,
        change_of_control_freedom=0.60,
        royalty_cleanliness=0.72,          # still receives royalties
        milestone_burden=0.74,
        profit_share_cleanliness=0.76,     # profit-share retained
        cost_obligation_cleanliness=0.75,
        no_blocking_rights=0.60,
        clean_governance_control=0.65,
        partner_encumbrance_severity=0.60,
        patent_strength=0.82,
        exclusivity_runway=0.78,
        freedom_to_operate=0.85,
        ownership_cleanliness=0.88,
        process_transferability=0.78,
        supply_redundancy=0.72,
        gmp_quality_readiness=0.80,
        scale_capacity=0.75,
        manufacturing_complexity="low",
        clinical_data_completeness=0.75,
        cmc_package_completeness=0.72,
        regulatory_file_completeness=0.75,
        safety_database_quality=0.75,
        data_room_readiness=0.72,
        fully_licensed_away=True,
    )


def _licensed_away_no_economics_inp() -> AssetControlTargetInput:
    """Fully licensed away AND no controllable economics retained."""
    return AssetControlTargetInput(
        global_rights_control=0.10,
        key_geography_control=0.10,
        indication_control=0.85,
        change_of_control_freedom=0.40,
        royalty_cleanliness=0.20,          # no royalty income
        milestone_burden=0.20,             # milestone obligations dominate
        profit_share_cleanliness=0.20,     # no profit share retained
        cost_obligation_cleanliness=0.20,
        no_blocking_rights=0.50,
        clean_governance_control=0.55,
        partner_encumbrance_severity=0.55,
        patent_strength=0.70,
        exclusivity_runway=0.65,
        freedom_to_operate=0.80,
        ownership_cleanliness=0.85,
        process_transferability=0.75,
        supply_redundancy=0.70,
        gmp_quality_readiness=0.78,
        scale_capacity=0.72,
        manufacturing_complexity="low",
        clinical_data_completeness=0.70,
        cmc_package_completeness=0.68,
        regulatory_file_completeness=0.70,
        safety_database_quality=0.70,
        data_room_readiness=0.68,
        fully_licensed_away=True,
    )


def _pair_inp(
    target_inp: AssetControlTargetInput,
    route: DealStructureRoute | None = None,
    buyer_desired_geography: str | None = None,
    target_controlled_geography: str | None = None,
    **kw,
) -> PairAssetControlInput:
    target = compute_asset_control_target(target_inp)
    return PairAssetControlInput(
        acquirer_id="ACQ",
        target_id="TGT",
        target_asset_control=target,
        deal_structure_route=route,
        buyer_desired_geography=buyer_desired_geography,
        target_controlled_geography=target_controlled_geography,
        **kw,
    )


# ---------------------------------------------------------------------------
# A. REGIONAL_LICENSE + matching geography → relief, no geo penalty
# ---------------------------------------------------------------------------

class TestRegionalLicenseMatchingGeo:

    def test_route_adjusted_score_higher_for_regional_license(self):
        """Regional license down-weights rights_control (0.15 vs 0.25).
        Same target with poor global rights scores higher under regional license."""
        r_no_route = compute_pair_asset_control(
            _pair_inp(_regional_target_inp(), route=None)
        )
        r_regional = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="EU",
                target_controlled_geography="EU",
            )
        )
        assert r_regional.route_adjusted_base_score > r_no_route.route_adjusted_base_score, (
            "Regional license reweights rights_control from 0.25 → 0.15; "
            "target with poor global rights but decent IP/economics should score higher"
        )

    def test_geography_fit_detail_full_match(self):
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="EU",
                target_controlled_geography="EU",
            )
        )
        assert r.geography_fit_detail == "full_match"

    def test_no_geo_pair_penalty_when_regions_match(self):
        """Exact match → pair_multiplier stays at 1.0 from geo (no other issues)."""
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="EU",
                target_controlled_geography="EU",
            )
        )
        assert r.pair_multiplier == pytest.approx(1.0)

    def test_superset_geo_no_penalty(self):
        """Target controls US+EU, buyer only wants EU → superset, no penalty."""
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="EU",
                target_controlled_geography="US+EU",
            )
        )
        assert r.geography_fit_detail == "superset"
        assert r.pair_multiplier == pytest.approx(1.0)

    def test_route_adjustment_applied_label(self):
        r = compute_pair_asset_control(
            _pair_inp(_regional_target_inp(), route=DealStructureRoute.REGIONAL_LICENSE)
        )
        assert r.route_adjustment_applied == "route_regional_license"

    def test_pair_asset_control_score_improved_vs_no_route(self):
        """Final score (base × multiplier) higher for REGIONAL_LICENSE with matching geo."""
        r_no_route = compute_pair_asset_control(
            _pair_inp(_regional_target_inp(), route=None)
        )
        r_regional = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="EU",
                target_controlled_geography="EU",
            )
        )
        assert r_regional.pair_asset_control_score > r_no_route.pair_asset_control_score


# ---------------------------------------------------------------------------
# B. REGIONAL_LICENSE + wrong geography → still penalized
# ---------------------------------------------------------------------------

class TestRegionalLicenseWrongGeo:

    def test_mismatch_geography_penalized(self):
        """Buyer wants US, target only has EU — mismatch regardless of route."""
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="US",
                target_controlled_geography="EU",
            )
        )
        assert r.geography_fit_detail == "mismatch"
        assert r.pair_multiplier <= 0.75

    def test_mismatch_sets_cap(self):
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="US",
                target_controlled_geography="EU",
            )
        )
        assert r.pair_cap is not None
        assert r.pair_cap <= 0.65

    def test_mismatch_appears_in_rationale(self):
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="US",
                target_controlled_geography="EU",
            )
        )
        assert any("mismatch" in line for line in r.rationale)

    def test_disjoint_regions_is_mismatch(self):
        """APAC buyer vs EU target — completely disjoint regions."""
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="APAC",
                target_controlled_geography="EU",
            )
        )
        assert r.geography_fit_detail == "mismatch"
        assert r.pair_multiplier <= 0.75

    def test_wrong_region_score_lower_than_matching_region(self):
        """Same route, same target — wrong region scores lower than matching region."""
        r_match = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="EU",
                target_controlled_geography="EU",
            )
        )
        r_mismatch = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="US",
                target_controlled_geography="EU",
            )
        )
        assert r_mismatch.pair_asset_control_score < r_match.pair_asset_control_score


# ---------------------------------------------------------------------------
# C. FULL_COMPANY_TAKEOUT + regional rights split → no route relief, penalized
# ---------------------------------------------------------------------------

class TestFullTakeoutRegionalRightsSplit:

    def test_full_takeout_uses_same_weights_as_no_route(self):
        """FULL_COMPANY_TAKEOUT uses the same bucket weights as the 0D-T default.
        route_adjusted_base_score should be close to target.asset_control_score."""
        target = compute_asset_control_target(_regional_target_inp())
        r = compute_pair_asset_control(
            PairAssetControlInput(
                acquirer_id="A", target_id="T",
                target_asset_control=target,
                deal_structure_route=DealStructureRoute.FULL_COMPANY_TAKEOUT,
            )
        )
        # Same bucket weights as 0D-T (0.25 rights) → composite should be very close
        assert abs(r.route_adjusted_base_score - target.asset_control_score) < 0.02

    def test_full_takeout_global_buyer_eu_target_is_mismatch(self):
        """Full takeout buyer wants global rights; target only has EU → mismatch."""
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.FULL_COMPANY_TAKEOUT,
                buyer_desired_geography="global",
                target_controlled_geography="EU",
            )
        )
        assert r.geography_fit_detail == "mismatch"

    def test_full_takeout_mismatch_applies_pair_penalty(self):
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.FULL_COMPANY_TAKEOUT,
                buyer_desired_geography="global",
                target_controlled_geography="EU",
            )
        )
        assert r.pair_multiplier <= 0.75
        assert r.pair_cap is not None and r.pair_cap <= 0.65

    def test_route_adjustment_applied_label_full_takeout(self):
        r = compute_pair_asset_control(
            _pair_inp(_regional_target_inp(), route=DealStructureRoute.FULL_COMPANY_TAKEOUT)
        )
        assert r.route_adjustment_applied == "route_full_company_takeout"

    def test_full_takeout_scores_lower_than_regional_license_on_regional_target(self):
        """For a regional-rights target, FULL_COMPANY_TAKEOUT should score worse
        than REGIONAL_LICENSE with matching geography — the route-aware reweighting matters."""
        r_full = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.FULL_COMPANY_TAKEOUT,
                buyer_desired_geography="global",
                target_controlled_geography="EU",
            )
        )
        r_regional = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="EU",
                target_controlled_geography="EU",
            )
        )
        assert r_full.pair_asset_control_score < r_regional.pair_asset_control_score


# ---------------------------------------------------------------------------
# D1. MINORITY_EQUITY + encumbrances → control penalty reduced
# ---------------------------------------------------------------------------

class TestMinorityEquityReducedControl:

    def test_minority_equity_base_score_higher_than_full_takeout(self):
        """Minority equity: rights=0.08, partner=0.12 vs full takeout: rights=0.25, partner=0.20.
        Encumbered target (poor rights/governance, strong IP) scores higher."""
        r_full = compute_pair_asset_control(
            _pair_inp(_encumbered_target_inp(), route=DealStructureRoute.FULL_COMPANY_TAKEOUT)
        )
        r_minority = compute_pair_asset_control(
            _pair_inp(_encumbered_target_inp(), route=DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION)
        )
        assert r_minority.route_adjusted_base_score > r_full.route_adjusted_base_score

    def test_minority_equity_route_adjustment_applied_label(self):
        r = compute_pair_asset_control(
            _pair_inp(_encumbered_target_inp(), route=DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION)
        )
        assert r.route_adjustment_applied == "route_minority_equity_plus_collaboration"

    def test_minority_equity_geo_mismatch_milder_penalty(self):
        """Mismatch for minority equity: mult ≤ 0.85, not the full 0.75 cap."""
        r = compute_pair_asset_control(
            _pair_inp(
                _encumbered_target_inp(),
                route=DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION,
                buyer_desired_geography="US",
                target_controlled_geography="EU",
            )
        )
        assert r.geography_fit_detail == "mismatch"
        # Mild penalty (0.85) for minority equity, not the hard 0.75
        assert r.pair_multiplier <= 0.85
        # Geographic mismatch alone should not force a hard cap for minority equity
        assert r.pair_cap is None

    def test_minority_equity_partial_geo_no_penalty(self):
        """Partial match (buyer wants US+EU, target has EU) → no geo penalty for minority equity."""
        r = compute_pair_asset_control(
            _pair_inp(
                _encumbered_target_inp(),
                route=DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION,
                buyer_desired_geography="US+EU",
                target_controlled_geography="EU",
            )
        )
        assert r.geography_fit_detail == "partial_match"
        # No geo penalty for partial match in minority equity route
        assert r.pair_multiplier == pytest.approx(1.0)

    def test_minority_equity_ip_heavy_benefits_ip_strong_target(self):
        """IP weight: minority equity = 0.24, full takeout = 0.15.
        IP-strong, rights-weak target scores better under minority equity."""
        inp = _encumbered_target_inp(
            patent_strength=0.95,
            exclusivity_runway=0.92,
            freedom_to_operate=0.95,
            ownership_cleanliness=0.98,
        )
        r_full = compute_pair_asset_control(
            _pair_inp(inp, route=DealStructureRoute.FULL_COMPANY_TAKEOUT)
        )
        r_minority = compute_pair_asset_control(
            _pair_inp(inp, route=DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION)
        )
        assert r_minority.route_adjusted_base_score >= r_full.route_adjusted_base_score


# ---------------------------------------------------------------------------
# D2. Fatal hard blocker overrides route
# ---------------------------------------------------------------------------

class TestHardBlockerOverridesRoute:

    def test_no_ownable_rights_fails_regardless_of_minority_equity(self):
        """no_ownable_rights is a hard fail even when minority equity doesn't need full control."""
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(no_ownable_rights=True),
                route=DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION,
            )
        )
        assert r.pair_level_fail is True

    def test_no_ownable_rights_zeroes_score(self):
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(no_ownable_rights=True),
                route=DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION,
            )
        )
        assert r.pair_asset_control_score == pytest.approx(0.0)

    def test_no_ownable_rights_fails_on_regional_license_too(self):
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(no_ownable_rights=True),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="EU",
                target_controlled_geography="EU",
            )
        )
        assert r.pair_level_fail is True

    def test_hard_fail_rationale_mentions_override(self):
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(no_ownable_rights=True),
                route=DealStructureRoute.FULL_COMPANY_TAKEOUT,
            )
        )
        assert any("hard fail" in line.lower() for line in r.rationale)

    def test_clean_target_does_not_trigger_hard_fail(self):
        """Sanity check: valid target with minority equity route should not fail."""
        r = compute_pair_asset_control(
            _pair_inp(_encumbered_target_inp(), route=DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION)
        )
        assert r.pair_level_fail is False


# ---------------------------------------------------------------------------
# E. fully_licensed_away + licensing route + economics retained → warning
# ---------------------------------------------------------------------------

class TestFullyLicensedAwayRouteConsistent:

    def test_route_consistent_adds_data_gap_marker(self):
        """Licensing route + economics retained → data_gap 'route_consistent'."""
        r = compute_pair_asset_control(
            _pair_inp(
                _licensed_away_with_economics_inp(),
                route=DealStructureRoute.GLOBAL_LICENSE,
            )
        )
        assert any("route_consistent" in gap for gap in r.data_gaps)

    def test_route_consistent_does_not_pair_fail(self):
        r = compute_pair_asset_control(
            _pair_inp(
                _licensed_away_with_economics_inp(),
                route=DealStructureRoute.GLOBAL_LICENSE,
            )
        )
        assert r.pair_level_fail is False

    def test_route_consistent_no_additional_pair_penalty(self):
        """Route-consistent fully_licensed_away should not add an extra pair_multiplier hit
        beyond what 0D-T already applied."""
        r = compute_pair_asset_control(
            _pair_inp(
                _licensed_away_with_economics_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                buyer_desired_geography="EU",
                target_controlled_geography="EU",
            )
        )
        # pair_multiplier itself should be 1.0 — 0D-T penalty flows through orchestrator
        assert r.pair_multiplier == pytest.approx(1.0)

    def test_route_consistent_holds_for_all_licensing_routes(self):
        """All five licensing routes should demote fully_licensed_away to a warning
        when economics are retained."""
        licensing_routes = [
            DealStructureRoute.GLOBAL_LICENSE,
            DealStructureRoute.REGIONAL_LICENSE,
            DealStructureRoute.OPTION_TO_LICENSE_OR_ACQUIRE,
            DealStructureRoute.CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION,
            DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION,
        ]
        inp = _licensed_away_with_economics_inp()
        for route in licensing_routes:
            r = compute_pair_asset_control(_pair_inp(inp, route=route))
            assert any("route_consistent" in gap for gap in r.data_gaps), (
                f"Route {route.value} should mark fully_licensed_away as route_consistent "
                "when economics are retained"
            )


# ---------------------------------------------------------------------------
# F. fully_licensed_away + no economics → still severe
# ---------------------------------------------------------------------------

class TestFullyLicensedAwayNoEconomics:

    def test_no_economics_adds_pair_penalty_even_on_licensing_route(self):
        """No controllable economics: Layer 3B applies additional pair penalty
        even when the route is a licensing route."""
        r = compute_pair_asset_control(
            _pair_inp(
                _licensed_away_no_economics_inp(),
                route=DealStructureRoute.GLOBAL_LICENSE,
            )
        )
        # Pair multiplier should be reduced — no economics means even license is not viable
        assert r.pair_multiplier <= 0.55

    def test_no_economics_no_route_consistent_marker(self):
        """No economics case should NOT add the route_consistent data gap."""
        r = compute_pair_asset_control(
            _pair_inp(
                _licensed_away_no_economics_inp(),
                route=DealStructureRoute.GLOBAL_LICENSE,
            )
        )
        assert not any("route_consistent" in gap for gap in r.data_gaps)

    def test_no_economics_non_licensing_route_also_severe(self):
        """Non-licensing route + no economics → severe regardless."""
        r = compute_pair_asset_control(
            _pair_inp(
                _licensed_away_no_economics_inp(),
                route=DealStructureRoute.FULL_COMPANY_TAKEOUT,
            )
        )
        assert r.pair_multiplier <= 0.55

    def test_no_economics_rationale_explains_severity(self):
        r = compute_pair_asset_control(
            _pair_inp(
                _licensed_away_no_economics_inp(),
                route=DealStructureRoute.GLOBAL_LICENSE,
            )
        )
        assert any("economics" in line.lower() for line in r.rationale)


# ---------------------------------------------------------------------------
# G. Route weight invariants and audit fields
# ---------------------------------------------------------------------------

class TestRouteWeightInvariants:

    def test_no_route_base_score_equals_raw_asset_control_score(self):
        """When deal_structure_route is None, route_adjusted_base_score == target.asset_control_score."""
        target = compute_asset_control_target(_regional_target_inp())
        r = compute_pair_asset_control(
            PairAssetControlInput(
                acquirer_id="A", target_id="T",
                target_asset_control=target,
                deal_structure_route=None,
            )
        )
        assert r.route_adjusted_base_score == pytest.approx(target.asset_control_score, abs=1e-4)

    def test_no_route_adjustment_applied_is_none(self):
        r = compute_pair_asset_control(
            _pair_inp(_regional_target_inp(), route=None)
        )
        assert r.route_adjustment_applied == "none"

    def test_geography_fit_detail_not_provided_when_strings_absent(self):
        """geography_fit_detail='not_provided' when buyer/target geography strings are absent."""
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                # no buyer_desired_geography or target_controlled_geography
            )
        )
        assert r.geography_fit_detail == "not_provided"

    def test_float_geo_fallback_still_penalizes_low_overlap(self):
        """Without string geography, overlap=0.30 still triggers the float-path penalty."""
        r = compute_pair_asset_control(
            _pair_inp(
                _regional_target_inp(),
                route=DealStructureRoute.REGIONAL_LICENSE,
                acquirer_target_geography_overlap=0.30,
                # no buyer/target geography strings
            )
        )
        assert r.pair_multiplier <= 0.75
        assert r.pair_cap is not None and r.pair_cap <= 0.65

    def test_existing_tests_unaffected_no_route_no_geography(self):
        """Regression guard: when no new fields are passed, behavior is identical
        to the pre-route-aware version."""
        from tests.test_pair_asset_control_3b import _pair as legacy_pair
        r_legacy = compute_pair_asset_control(legacy_pair(rofr_blocks_this_acquirer=True))
        assert r_legacy.pair_multiplier <= 0.65
        assert r_legacy.pair_cap is not None and r_legacy.pair_cap <= 0.55
        # New fields exist and have sensible defaults
        assert r_legacy.route_adjusted_base_score > 0.0
        assert r_legacy.route_adjustment_applied == "none"
        assert r_legacy.geography_fit_detail == "not_provided"

    def test_lead_asset_takeout_same_weights_as_full_company(self):
        """LEAD_ASSET_TAKEOUT and FULL_COMPANY_TAKEOUT use identical bucket weights."""
        target = compute_asset_control_target(_regional_target_inp())
        r_full = compute_pair_asset_control(
            PairAssetControlInput(
                acquirer_id="A", target_id="T",
                target_asset_control=target,
                deal_structure_route=DealStructureRoute.FULL_COMPANY_TAKEOUT,
            )
        )
        r_lead = compute_pair_asset_control(
            PairAssetControlInput(
                acquirer_id="A", target_id="T",
                target_asset_control=target,
                deal_structure_route=DealStructureRoute.LEAD_ASSET_TAKEOUT,
            )
        )
        assert r_full.route_adjusted_base_score == pytest.approx(r_lead.route_adjusted_base_score, abs=1e-4)

    def test_new_output_fields_present_on_all_paths(self):
        """Smoke test: all new fields exist on result regardless of inputs."""
        for route in [None, DealStructureRoute.FULL_COMPANY_TAKEOUT, DealStructureRoute.REGIONAL_LICENSE,
                      DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION]:
            r = compute_pair_asset_control(_pair_inp(_regional_target_inp(), route=route))
            assert hasattr(r, "route_adjusted_base_score")
            assert hasattr(r, "route_adjustment_applied")
            assert hasattr(r, "geography_fit_detail")
            assert isinstance(r.route_adjusted_base_score, float)
            assert isinstance(r.route_adjustment_applied, str)
            assert isinstance(r.geography_fit_detail, str)
