"""Tests for 0D — Asset-Control / Encumbrance Gate (6-bucket scoring system).

Covers:
1. Individual bucket scoring formulas (rights, economic, partner, IP, mfg, diligence)
2. Composite scoring and gate treatment bands
3. Hard blockers (no_ownable_rights, fatal_ip_dispute, fully_licensed_away, blocking_consent_right)
4. Pair-specific behavior (existing partner bonus, acquirer mfg fit)
5. Encumbrance valuation multiplier
6. Mapper from coarse TargetEligibilityInput → AssetControlInput
7. Backward-compatibility (legacy flag fields, encumbrance_codes alias)
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_asset_control import (
    AssetControlGateTreatment,
    AssetControlInput,
    AssetControlResult,
    _score_rights_control,
    _score_economic_control,
    _score_partner_freedom,
    _score_ip_control,
    _score_manufacturing_control,
    _score_diligence_readiness,
    _gate_treatment,
    _encumbrance_valuation_multiplier,
    compute_asset_control,
    asset_control_from_target,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inp(**kw) -> AssetControlInput:
    """Minimal clean AssetControlInput: all sub-scores at high defaults."""
    defaults = dict(
        global_rights_control=0.95,
        key_geography_control=0.90,
        indication_control=0.90,
        change_of_control_freedom=0.85,
        royalty_cleanliness=0.95,
        milestone_burden=0.90,
        profit_share_cleanliness=0.95,
        cost_obligation_cleanliness=0.90,
        no_blocking_rights=0.90,
        no_rofr_or_opt_in=0.90,
        no_consent_requirement=0.90,
        clean_governance_control=0.90,
        no_exclusivity_conflict=0.95,
        patent_strength=0.85,
        exclusivity_runway=0.80,
        freedom_to_operate=0.90,
        ownership_cleanliness=0.95,
        process_transferability=0.85,
        supply_redundancy=0.80,
        acquirer_manufacturing_fit=0.80,
        gmp_quality_readiness=0.85,
        scale_capacity=0.80,
        clinical_data_completeness=0.85,
        cmc_package_completeness=0.80,
        regulatory_file_completeness=0.82,
        safety_database_quality=0.80,
        data_room_readiness=0.80,
    )
    defaults.update(kw)
    return AssetControlInput(**defaults)


# ---------------------------------------------------------------------------
# 1. Bucket scoring — rights control
# ---------------------------------------------------------------------------

class TestRightsControl:

    def test_clean_global_rights_high_score(self):
        inp = _inp()
        score, codes = _score_rights_control(inp)
        assert score >= 0.85
        assert "global_rights:positive" in codes

    def test_partial_global_rights_reduces_score(self):
        inp_full = _inp(global_rights_control=0.95)
        inp_partial = _inp(global_rights_control=0.40)
        s_full, _ = _score_rights_control(inp_full)
        s_partial, codes_partial = _score_rights_control(inp_partial)
        assert s_partial < s_full
        assert "rights_control:severe_restriction" in codes_partial

    def test_key_geography_missing_flagged(self):
        inp = _inp(key_geography_control=0.40)
        _, codes = _score_rights_control(inp)
        assert "key_geography:major_market_unavailable" in codes

    def test_regional_split_code(self):
        inp = _inp(asset_rights_scope="regional_split")
        _, codes = _score_rights_control(inp)
        assert "regional_rights_split" in codes

    def test_licensed_in_code(self):
        inp = _inp(asset_rights_scope="licensed_in")
        _, codes = _score_rights_control(inp)
        assert "licensed_in_rights" in codes

    def test_formula_weights(self):
        # Verify exact formula: 0.40×global + 0.25×key_geo + 0.20×indication + 0.15×coc
        inp = _inp(global_rights_control=1.0, key_geography_control=1.0,
                   indication_control=1.0, change_of_control_freedom=1.0)
        score, _ = _score_rights_control(inp)
        assert score == pytest.approx(1.0)

        inp_zero = _inp(global_rights_control=0.0, key_geography_control=0.0,
                        indication_control=0.0, change_of_control_freedom=0.0)
        score_zero, _ = _score_rights_control(inp_zero)
        assert score_zero == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 2. Bucket scoring — economic control
# ---------------------------------------------------------------------------

class TestEconomicControl:

    def test_no_obligations_high_score(self):
        inp = _inp(royalty_cleanliness=1.0, milestone_burden=1.0,
                   profit_share_cleanliness=1.0, cost_obligation_cleanliness=1.0)
        score, _ = _score_economic_control(inp)
        assert score == pytest.approx(1.0)

    def test_high_royalty_flagged(self):
        inp = _inp(royalty_cleanliness=0.30, royalty_stack_high=True)
        score, codes = _score_economic_control(inp)
        assert score < 0.80
        assert "royalty_stack_high" in codes

    def test_heavy_milestone_flagged(self):
        inp = _inp(milestone_burden=0.30)
        _, codes = _score_economic_control(inp)
        assert "economic_control:large_milestone_burden" in codes

    def test_cdev_obligation_flagged(self):
        inp = _inp(has_co_development_obligation=True)
        _, codes = _score_economic_control(inp)
        assert "co_development_obligation" in codes


# ---------------------------------------------------------------------------
# 3. Bucket scoring — partner freedom (pair-specific)
# ---------------------------------------------------------------------------

class TestPartnerFreedom:

    def test_no_partner_issues_high_score(self):
        inp = _inp(no_blocking_rights=1.0, no_rofr_or_opt_in=1.0,
                   no_consent_requirement=1.0, clean_governance_control=1.0,
                   no_exclusivity_conflict=1.0)
        score, _ = _score_partner_freedom(inp)
        assert score == pytest.approx(1.0)

    def test_existing_partner_bonus_applied(self):
        inp_no_partner = _inp(acquirer_is_existing_partner=False)
        inp_partner = _inp(acquirer_is_existing_partner=True)
        s_no, _ = _score_partner_freedom(inp_no_partner)
        s_partner, codes_partner = _score_partner_freedom(inp_partner)
        assert s_partner >= s_no
        assert "partner_freedom:existing_partner_bonus_applied" in codes_partner

    def test_existing_partner_score_capped_at_one(self):
        inp = _inp(acquirer_is_existing_partner=True,
                   no_blocking_rights=1.0, no_rofr_or_opt_in=1.0,
                   no_consent_requirement=1.0, clean_governance_control=1.0,
                   no_exclusivity_conflict=1.0)
        score, _ = _score_partner_freedom(inp)
        assert score <= 1.0

    def test_blocking_rofr_flagged(self):
        inp = _inp(no_rofr_or_opt_in=0.20)
        _, codes = _score_partner_freedom(inp)
        assert "partner_freedom:ROFR_or_opt_in_blocks_this_acquirer" in codes

    def test_consent_right_blocking_flagged(self):
        inp = _inp(no_consent_requirement=0.20)
        _, codes = _score_partner_freedom(inp)
        assert "partner_freedom:consent_right_blocking" in codes


# ---------------------------------------------------------------------------
# 4. Bucket scoring — IP control
# ---------------------------------------------------------------------------

class TestIpControl:

    def test_clean_ip_high_score(self):
        inp = _inp(patent_strength=1.0, exclusivity_runway=1.0,
                   freedom_to_operate=1.0, ownership_cleanliness=1.0)
        score, _ = _score_ip_control(inp)
        assert score == pytest.approx(1.0)

    def test_ip_dispute_flag_passed_through(self):
        inp = _inp(has_ip_dispute=True)
        _, codes = _score_ip_control(inp)
        assert "ip_dispute" in codes

    def test_ownership_contested_flagged(self):
        inp = _inp(ownership_cleanliness=0.20)
        _, codes = _score_ip_control(inp)
        assert "ip_control:ownership_fatally_contested" in codes

    def test_fto_issue_flagged(self):
        inp = _inp(freedom_to_operate=0.30)
        _, codes = _score_ip_control(inp)
        assert "ip_control:FTO_issue" in codes

    def test_weak_patent_flagged(self):
        inp = _inp(patent_strength=0.35)
        _, codes = _score_ip_control(inp)
        assert "ip_control:weak_patent_position" in codes


# ---------------------------------------------------------------------------
# 5. Bucket scoring — manufacturing control (pair-specific)
# ---------------------------------------------------------------------------

class TestManufacturingControl:

    def test_strong_acquirer_capability_code(self):
        inp = _inp(acquirer_manufacturing_fit=0.90)
        _, codes = _score_manufacturing_control(inp)
        assert "manufacturing_control:acquirer_strong_capability" in codes

    def test_weak_acquirer_capability_code(self):
        inp = _inp(acquirer_manufacturing_fit=0.30)
        _, codes = _score_manufacturing_control(inp)
        assert "manufacturing_control:acquirer_weak_capability_amplifies_risk" in codes

    def test_mfg_dependency_flagged(self):
        inp = _inp(has_manufacturing_dependency=True)
        _, codes = _score_manufacturing_control(inp)
        assert "manufacturing_dependency" in codes

    def test_single_cdmo_dependency_flagged(self):
        inp = _inp(supply_redundancy=0.30)
        _, codes = _score_manufacturing_control(inp)
        assert "manufacturing_control:single_CDMO_dependency" in codes


# ---------------------------------------------------------------------------
# 6. Gate treatment bands
# ---------------------------------------------------------------------------

class TestGateTreatment:

    def test_clean_band(self):
        treatment, mult, cap = _gate_treatment(0.90, [])
        assert treatment == AssetControlGateTreatment.CLEAN
        assert mult == pytest.approx(1.0)
        assert cap is None

    def test_mild_penalty_band(self):
        treatment, mult, cap = _gate_treatment(0.75, [])
        assert treatment == AssetControlGateTreatment.MILD_PENALTY
        assert mult == pytest.approx(0.95)
        assert cap is None

    def test_meaningful_penalty_band(self):
        treatment, mult, cap = _gate_treatment(0.60, [])
        assert treatment == AssetControlGateTreatment.MEANINGFUL_PENALTY
        assert mult == pytest.approx(0.80)
        assert cap is None

    def test_severe_cap_band(self):
        treatment, mult, cap = _gate_treatment(0.42, [])
        assert treatment == AssetControlGateTreatment.SEVERE_CAP
        assert mult == pytest.approx(0.60)
        assert cap == pytest.approx(0.55)

    def test_route_to_licensing_band(self):
        treatment, mult, cap = _gate_treatment(0.20, [])
        assert treatment == AssetControlGateTreatment.ROUTE_TO_LICENSING
        assert mult == pytest.approx(0.40)
        assert cap == pytest.approx(0.40)

    def test_no_ownable_rights_hard_fail_override(self):
        """Hard blocker overrides numeric gate regardless of composite score."""
        treatment, mult, cap = _gate_treatment(0.90, ["no_ownable_rights"])
        assert treatment == AssetControlGateTreatment.HARD_FAIL


# ---------------------------------------------------------------------------
# 7. Hard blockers
# ---------------------------------------------------------------------------

class TestHardBlockers:

    def test_no_ownable_rights_hard_fail(self):
        inp = _inp(no_ownable_rights=True)
        result = compute_asset_control(inp)
        assert result.is_hard_fail is True
        assert result.gate_treatment == AssetControlGateTreatment.HARD_FAIL
        assert "no_ownable_rights" in result.hard_blockers

    def test_fatal_ip_dispute_caps_composite(self):
        inp = _inp(fatal_ip_dispute=True)
        result = compute_asset_control(inp)
        assert result.asset_control_score <= 0.30
        assert "fatal_ip_dispute" in result.hard_blockers

    def test_fully_licensed_away_routes_licensing(self):
        inp = _inp(fully_licensed_away=True)
        result = compute_asset_control(inp)
        assert result.asset_control_score <= 0.30
        assert "fully_licensed_away" in result.hard_blockers

    def test_blocking_consent_right_pair_level_cap(self):
        """Non-partner acquirer with blocking_consent_right → pair-level cap."""
        inp = _inp(blocking_consent_right=True, acquirer_is_existing_partner=False)
        result = compute_asset_control(inp)
        assert result.is_pair_level_cap is True
        assert result.max_mna_score_cap is not None
        assert result.max_mna_score_cap <= 0.55
        assert result.penalty_multiplier <= 0.65
        assert "blocking_consent_right" in result.hard_blockers

    def test_blocking_consent_right_waived_for_existing_partner(self):
        """Existing partner waives ROFR/consent → pair-level cap does not apply."""
        inp = _inp(blocking_consent_right=True, acquirer_is_existing_partner=True)
        result = compute_asset_control(inp)
        assert result.is_pair_level_cap is False

    def test_hard_fail_pair_does_not_affect_global_score(self):
        """Two independent compute_asset_control calls — blocker in one does not spill over."""
        inp_clean = _inp()
        inp_blocked = _inp(no_ownable_rights=True)
        r_clean = compute_asset_control(inp_clean)
        r_blocked = compute_asset_control(inp_blocked)
        assert not r_clean.is_hard_fail
        assert r_blocked.is_hard_fail


# ---------------------------------------------------------------------------
# 8. Composite scoring and result fields
# ---------------------------------------------------------------------------

class TestCompositeAndResult:

    def test_clean_target_mild_or_better(self):
        inp = _inp()
        result = compute_asset_control(inp)
        assert result.gate_treatment in (
            AssetControlGateTreatment.CLEAN,
            AssetControlGateTreatment.MILD_PENALTY,
        )
        assert result.penalty_multiplier >= 0.95

    def test_all_buckets_low_meaningful_or_worse(self):
        inp = _inp(
            global_rights_control=0.20,
            key_geography_control=0.20,
            royalty_cleanliness=0.20,
            no_blocking_rights=0.20,
            no_rofr_or_opt_in=0.20,
            patent_strength=0.20,
            ownership_cleanliness=0.20,
            process_transferability=0.20,
            clinical_data_completeness=0.20,
        )
        result = compute_asset_control(inp)
        assert result.asset_control_score < 0.60
        assert result.gate_treatment in (
            AssetControlGateTreatment.MEANINGFUL_PENALTY,
            AssetControlGateTreatment.SEVERE_CAP,
            AssetControlGateTreatment.ROUTE_TO_LICENSING,
            AssetControlGateTreatment.HARD_FAIL,
        )
        assert result.penalty_multiplier <= 0.80

    def test_bucket_scores_present(self):
        result = compute_asset_control(_inp())
        assert 0.0 <= result.rights_control_score <= 1.0
        assert 0.0 <= result.economic_control_score <= 1.0
        assert 0.0 <= result.partner_freedom_score <= 1.0
        assert 0.0 <= result.ip_control_score <= 1.0
        assert 0.0 <= result.manufacturing_control_score <= 1.0
        assert 0.0 <= result.diligence_readiness_score <= 1.0

    def test_result_is_frozen(self):
        result = compute_asset_control(_inp())
        with pytest.raises(Exception):
            result.asset_control_score = 0.5  # type: ignore[misc]

    def test_rationale_non_empty(self):
        result = compute_asset_control(_inp())
        assert len(result.rationale) >= 1

    def test_recommended_action_non_empty(self):
        result = compute_asset_control(_inp())
        assert len(result.recommended_action) > 0

    def test_confidence_reflects_diligence(self):
        high_diligence = _inp(
            clinical_data_completeness=0.90, cmc_package_completeness=0.90,
            regulatory_file_completeness=0.90, safety_database_quality=0.90,
            data_room_readiness=0.90,
        )
        low_diligence = _inp(
            clinical_data_completeness=0.20, cmc_package_completeness=0.20,
            regulatory_file_completeness=0.20, safety_database_quality=0.20,
            data_room_readiness=0.20,
        )
        r_high = compute_asset_control(high_diligence)
        r_low = compute_asset_control(low_diligence)
        assert r_high.asset_control_confidence == "high"
        assert r_low.asset_control_confidence == "low"


# ---------------------------------------------------------------------------
# 9. Encumbrance valuation multiplier
# ---------------------------------------------------------------------------

class TestEncumbranceValuationMultiplier:

    def test_all_ones_near_one(self):
        mult = _encumbrance_valuation_multiplier(1.0, 1.0, 1.0, 1.0)
        assert mult == pytest.approx(1.0)

    def test_all_zeros_at_floor(self):
        # floors: rights=0.50, economic=0.55, ip=0.60, mfg=0.70
        mult = _encumbrance_valuation_multiplier(0.0, 0.0, 0.0, 0.0)
        expected = 0.50 * 0.55 * 0.60 * 0.70
        assert mult == pytest.approx(expected, abs=1e-4)

    def test_only_rights_issue_reduces(self):
        mult_clean = _encumbrance_valuation_multiplier(1.0, 1.0, 1.0, 1.0)
        mult_rights = _encumbrance_valuation_multiplier(0.0, 1.0, 1.0, 1.0)
        assert mult_rights < mult_clean

    def test_in_range(self):
        for r in (0.0, 0.25, 0.50, 0.75, 1.0):
            for e in (0.0, 0.50, 1.0):
                m = _encumbrance_valuation_multiplier(r, e, 0.80, 0.80)
                assert 0.0 < m <= 1.0


# ---------------------------------------------------------------------------
# 10. Mapper: asset_control_from_target
# ---------------------------------------------------------------------------

class _MockTarget:
    """Minimal mock for TargetEligibilityInput."""
    def __init__(self, **kw):
        defaults = dict(
            asset_rights_scope="global",
            has_existing_partnership=False,
            has_right_of_first_refusal=False,
            royalty_stack_rate=None,
            has_co_development_obligation=False,
            has_ip_dispute=False,
            has_manufacturing_dependency=False,
            manufacturing_complexity="low",
            has_clinical_stage=True,
            has_trial_status=True,
            has_patent_loe_data=True,
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


class TestAssetControlFromTarget:

    def test_global_rights_maps_to_high_sub_scores(self):
        inp = asset_control_from_target(_MockTarget(asset_rights_scope="global"))
        assert inp.global_rights_control >= 0.90
        assert inp.key_geography_control >= 0.85

    def test_regional_split_maps_to_low_sub_scores(self):
        inp = asset_control_from_target(_MockTarget(asset_rights_scope="regional_split"))
        assert inp.global_rights_control <= 0.55
        assert inp.key_geography_control <= 0.55

    def test_licensed_in_very_low_rights(self):
        inp = asset_control_from_target(_MockTarget(asset_rights_scope="licensed_in"))
        assert inp.global_rights_control <= 0.30
        assert inp.fully_licensed_away is True

    def test_ip_dispute_lowers_ip_sub_scores(self):
        inp = asset_control_from_target(_MockTarget(has_ip_dispute=True))
        assert inp.ownership_cleanliness < 0.20
        assert inp.freedom_to_operate < 0.50

    def test_rofr_lowers_partner_sub_scores(self):
        inp = asset_control_from_target(_MockTarget(has_right_of_first_refusal=True))
        assert inp.no_rofr_or_opt_in < 0.25

    def test_high_royalty_reduces_royalty_cleanliness(self):
        inp = asset_control_from_target(_MockTarget(royalty_stack_rate=0.30))
        assert inp.royalty_cleanliness < 0.30

    def test_mfg_dependency_reduces_mfg_sub_scores(self):
        inp = asset_control_from_target(_MockTarget(has_manufacturing_dependency=True))
        assert inp.process_transferability < 0.50
        assert inp.supply_redundancy < 0.50

    def test_high_mfg_complexity_reduces_mfg_sub_scores(self):
        inp_low = asset_control_from_target(_MockTarget(manufacturing_complexity="low"))
        inp_high = asset_control_from_target(_MockTarget(manufacturing_complexity="high"))
        assert inp_high.process_transferability < inp_low.process_transferability

    def test_clinical_data_present_raises_diligence(self):
        inp_no = asset_control_from_target(_MockTarget(has_clinical_stage=False, has_trial_status=False))
        inp_yes = asset_control_from_target(_MockTarget(has_clinical_stage=True, has_trial_status=True))
        assert inp_yes.clinical_data_completeness > inp_no.clinical_data_completeness

    def test_end_to_end_global_clean_gives_mild_or_clean(self):
        result = compute_asset_control(
            asset_control_from_target(_MockTarget())
        )
        assert result.gate_treatment in (
            AssetControlGateTreatment.CLEAN,
            AssetControlGateTreatment.MILD_PENALTY,
            AssetControlGateTreatment.MEANINGFUL_PENALTY,
        )

    def test_end_to_end_licensed_in_routes_licensing(self):
        result = compute_asset_control(
            asset_control_from_target(_MockTarget(asset_rights_scope="licensed_in"))
        )
        # licensed_in triggers fully_licensed_away → ROUTE_TO_LICENSING
        assert result.gate_treatment == AssetControlGateTreatment.ROUTE_TO_LICENSING


# ---------------------------------------------------------------------------
# 11. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:

    def test_encumbrance_codes_alias(self):
        result = compute_asset_control(_inp())
        assert result.encumbrance_codes is result.triggered_encumbrances

    def test_legacy_flags_preserved(self):
        result = compute_asset_control(
            _inp(
                has_ip_dispute=True,
                has_right_of_first_refusal=True,
                has_existing_partnership=True,
                has_co_development_obligation=True,
                has_manufacturing_dependency=True,
                royalty_stack_high=True,
                asset_rights_scope="regional_split",
            )
        )
        assert result.has_ip_dispute is True
        assert result.has_right_of_first_refusal is True
        assert result.has_existing_partnership is True
        assert result.has_co_development_obligation is True
        assert result.has_manufacturing_dependency is True
        assert result.royalty_stack_high is True
        assert result.asset_rights_scope == "regional_split"

    def test_penalty_multiplier_field_present(self):
        result = compute_asset_control(_inp())
        assert 0.0 < result.penalty_multiplier <= 1.0

    def test_is_asset_control_result_instance(self):
        result = compute_asset_control(_inp())
        assert isinstance(result, AssetControlResult)

    def test_encumbrance_flags_alias_resolves(self):
        """EncumbranceFlags imported from ma_eligibility is AssetControlResult."""
        from bve.intelligence.ma_eligibility import EncumbranceFlags
        assert EncumbranceFlags is AssetControlResult
