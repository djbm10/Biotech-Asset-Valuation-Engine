"""Tests for 0D-T — Target-Level Asset-Control / Encumbrance Profile.

Coverage:
  1.  Bucket scoring — rights control
  2.  Bucket scoring — economic control
  3.  Bucket scoring — partner encumbrance facts (target-level; no pair signals)
  4.  Bucket scoring — IP control
  5.  Bucket scoring — manufacturing readiness (no acquirer_mfg_fit)
  6.  Bucket scoring — diligence readiness
  7.  Gate treatment bands
  8.  Hard blockers (no_ownable_rights, fatal_ip_dispute, fully_licensed_away)
  9.  Output flags for Layer 3B (has_rofr_fact, has_existing_partner_fact,
      manufacturing_complexity_flag)
 10.  No pair contamination — verify pair-specific fields absent
 11.  Valuation multiplier
 12.  Mapper: asset_control_target_from_target()
 13.  Backward-compatibility legacy fields
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_eligibility import EncumbranceFlags
from bve.intelligence.ma_asset_control_target import (
    AssetControlGateTreatment,
    AssetControlTargetInput,
    AssetControlTargetResult,
    _BUCKET_WEIGHTS,
    _GATE_BANDS,
    _score_rights_control,
    _score_economic_control,
    _score_partner_encumbrance_facts,
    _score_ip_control,
    _score_manufacturing_readiness,
    _score_diligence_readiness,
    _gate_treatment,
    _encumbrance_valuation_multiplier,
    compute_asset_control_target,
    asset_control_target_from_target,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inp(**kw) -> AssetControlTargetInput:
    """Clean, high-scoring AssetControlTargetInput."""
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
        clean_governance_control=0.90,
        partner_encumbrance_severity=0.90,
        patent_strength=0.85,
        exclusivity_runway=0.80,
        freedom_to_operate=0.90,
        ownership_cleanliness=0.95,
        process_transferability=0.85,
        supply_redundancy=0.80,
        gmp_quality_readiness=0.85,
        scale_capacity=0.80,
        manufacturing_complexity="low",
        clinical_data_completeness=0.85,
        cmc_package_completeness=0.80,
        regulatory_file_completeness=0.82,
        safety_database_quality=0.80,
        data_room_readiness=0.80,
    )
    defaults.update(kw)
    return AssetControlTargetInput(**defaults)


# ---------------------------------------------------------------------------
# 1. Bucket scoring — rights control
# ---------------------------------------------------------------------------

class TestRightsControl:

    def test_formula_all_ones(self):
        inp = _inp(global_rights_control=1.0, key_geography_control=1.0,
                   indication_control=1.0, change_of_control_freedom=1.0)
        score, _ = _score_rights_control(inp)
        assert score == pytest.approx(1.0)

    def test_formula_all_zeros(self):
        inp = _inp(global_rights_control=0.0, key_geography_control=0.0,
                   indication_control=0.0, change_of_control_freedom=0.0)
        score, _ = _score_rights_control(inp)
        assert score == pytest.approx(0.0)

    def test_clean_global_rights_positive_code(self):
        inp = _inp(global_rights_control=0.95)
        _, codes = _score_rights_control(inp)
        assert "global_rights:positive" in codes

    def test_severe_restriction_code(self):
        inp = _inp(global_rights_control=0.40)
        _, codes = _score_rights_control(inp)
        assert "rights_control:severe_restriction" in codes

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

    def test_partial_global_reduces_score(self):
        high = _inp(global_rights_control=0.95)
        low = _inp(global_rights_control=0.40)
        s_high, _ = _score_rights_control(high)
        s_low, _ = _score_rights_control(low)
        assert s_low < s_high


# ---------------------------------------------------------------------------
# 2. Bucket scoring — economic control
# ---------------------------------------------------------------------------

class TestEconomicControl:

    def test_all_clean_score_one(self):
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

    def test_heavy_royalty_burden_code(self):
        inp = _inp(royalty_cleanliness=0.40)
        _, codes = _score_economic_control(inp)
        assert "economic_control:heavy_royalty_burden" in codes


# ---------------------------------------------------------------------------
# 3. Bucket scoring — partner encumbrance facts (target-level; no pair signals)
# ---------------------------------------------------------------------------

class TestPartnerEncumbranceFacts:

    def test_clean_partner_score_one(self):
        inp = _inp(no_blocking_rights=1.0, clean_governance_control=1.0,
                   partner_encumbrance_severity=1.0)
        score, _ = _score_partner_encumbrance_facts(inp)
        assert score == pytest.approx(1.0)

    def test_all_zero_score_zero(self):
        inp = _inp(no_blocking_rights=0.0, clean_governance_control=0.0,
                   partner_encumbrance_severity=0.0)
        score, _ = _score_partner_encumbrance_facts(inp)
        assert score == pytest.approx(0.0)

    def test_formula_weights(self):
        # 0.50×no_blocking + 0.30×governance + 0.20×severity
        inp = _inp(no_blocking_rights=1.0, clean_governance_control=0.0,
                   partner_encumbrance_severity=0.0)
        score, _ = _score_partner_encumbrance_facts(inp)
        assert score == pytest.approx(0.50)

    def test_rofr_fact_code_present(self):
        inp = _inp(has_right_of_first_refusal=True)
        _, codes = _score_partner_encumbrance_facts(inp)
        assert "partner_fact:rofr_present" in codes

    def test_existing_partner_fact_code_present(self):
        inp = _inp(has_existing_partnership=True)
        _, codes = _score_partner_encumbrance_facts(inp)
        assert "partner_fact:existing_partner_present" in codes

    def test_severe_blocking_rights_code(self):
        inp = _inp(no_blocking_rights=0.30)
        _, codes = _score_partner_encumbrance_facts(inp)
        assert "partner_encumbrance:generic_blocking_rights_severe" in codes

    def test_high_overall_severity_code(self):
        inp = _inp(partner_encumbrance_severity=0.30)
        _, codes = _score_partner_encumbrance_facts(inp)
        assert "partner_encumbrance:high_overall_severity" in codes

    def test_no_pair_bonus_code_ever_generated(self):
        """partner_freedom:existing_partner_bonus_applied must never appear."""
        inp = _inp()
        _, codes = _score_partner_encumbrance_facts(inp)
        assert "partner_freedom:existing_partner_bonus_applied" not in codes

    def test_no_rofr_blocks_this_acquirer_code(self):
        """ROFR blocking this acquirer is pair-specific — must not appear here."""
        inp = _inp(has_right_of_first_refusal=True)
        _, codes = _score_partner_encumbrance_facts(inp)
        assert "partner_freedom:ROFR_or_opt_in_blocks_this_acquirer" not in codes

    def test_score_unchanged_by_acquirer_identity(self):
        """Score must be the same regardless of who the acquirer is.
        (acquirer_is_existing_partner does not exist in this input.)"""
        assert not hasattr(AssetControlTargetInput, "acquirer_is_existing_partner")


# ---------------------------------------------------------------------------
# 4. Bucket scoring — IP control
# ---------------------------------------------------------------------------

class TestIpControl:

    def test_clean_ip_score_one(self):
        inp = _inp(patent_strength=1.0, exclusivity_runway=1.0,
                   freedom_to_operate=1.0, ownership_cleanliness=1.0)
        score, _ = _score_ip_control(inp)
        assert score == pytest.approx(1.0)

    def test_ip_dispute_flag_passed_through(self):
        inp = _inp(has_ip_dispute=True)
        _, codes = _score_ip_control(inp)
        assert "ip_dispute" in codes

    def test_ownership_contested_code(self):
        inp = _inp(ownership_cleanliness=0.20)
        _, codes = _score_ip_control(inp)
        assert "ip_control:ownership_fatally_contested" in codes

    def test_fto_issue_code(self):
        inp = _inp(freedom_to_operate=0.30)
        _, codes = _score_ip_control(inp)
        assert "ip_control:FTO_issue" in codes

    def test_weak_patent_code(self):
        inp = _inp(patent_strength=0.35)
        _, codes = _score_ip_control(inp)
        assert "ip_control:weak_patent_position" in codes


# ---------------------------------------------------------------------------
# 5. Bucket scoring — manufacturing readiness (no acquirer_mfg_fit)
# ---------------------------------------------------------------------------

class TestManufacturingReadiness:

    def test_no_acquirer_mfg_fit_field_in_input(self):
        """acquirer_manufacturing_fit must not exist on AssetControlTargetInput."""
        assert not hasattr(AssetControlTargetInput, "acquirer_manufacturing_fit")

    def test_formula_all_ones(self):
        inp = _inp(process_transferability=1.0, supply_redundancy=1.0,
                   gmp_quality_readiness=1.0, scale_capacity=1.0)
        score, _ = _score_manufacturing_readiness(inp)
        assert score == pytest.approx(1.0)

    def test_formula_weights_renormalised(self):
        # Weights: 0.35 + 0.30 + 0.20 + 0.15 = 1.0
        inp = _inp(process_transferability=1.0, supply_redundancy=0.0,
                   gmp_quality_readiness=0.0, scale_capacity=0.0)
        score, _ = _score_manufacturing_readiness(inp)
        assert score == pytest.approx(0.35)

    def test_mfg_dependency_flagged(self):
        inp = _inp(has_manufacturing_dependency=True)
        _, codes = _score_manufacturing_readiness(inp)
        assert "manufacturing_dependency" in codes

    def test_single_cdmo_flagged(self):
        inp = _inp(supply_redundancy=0.30)
        _, codes = _score_manufacturing_readiness(inp)
        assert "manufacturing_readiness:single_CDMO_dependency" in codes

    def test_gmp_issue_flagged(self):
        inp = _inp(gmp_quality_readiness=0.30)
        _, codes = _score_manufacturing_readiness(inp)
        assert "manufacturing_readiness:GMP_issue" in codes

    def test_high_complexity_code_present(self):
        inp = _inp(manufacturing_complexity="high")
        _, codes = _score_manufacturing_readiness(inp)
        assert "manufacturing_readiness:high_complexity_modality" in codes

    def test_low_complexity_no_complexity_code(self):
        inp = _inp(manufacturing_complexity="low")
        _, codes = _score_manufacturing_readiness(inp)
        assert "manufacturing_readiness:high_complexity_modality" not in codes

    def test_no_acquirer_capability_codes_ever(self):
        """Acquirer capability codes must never appear in target module."""
        inp = _inp()
        _, codes = _score_manufacturing_readiness(inp)
        assert "manufacturing_control:acquirer_strong_capability" not in codes
        assert "manufacturing_control:acquirer_weak_capability_amplifies_risk" not in codes


# ---------------------------------------------------------------------------
# 6. Bucket scoring — diligence readiness
# ---------------------------------------------------------------------------

class TestDiligenceReadiness:

    def test_all_clean_score_one(self):
        inp = _inp(clinical_data_completeness=1.0, cmc_package_completeness=1.0,
                   regulatory_file_completeness=1.0, safety_database_quality=1.0,
                   data_room_readiness=1.0)
        score, _ = _score_diligence_readiness(inp)
        assert score == pytest.approx(1.0)

    def test_incomplete_safety_db_flagged(self):
        inp = _inp(safety_database_quality=0.20)
        _, codes = _score_diligence_readiness(inp)
        assert "diligence_readiness:incomplete_safety_database" in codes

    def test_missing_trial_data_flagged(self):
        inp = _inp(clinical_data_completeness=0.30)
        _, codes = _score_diligence_readiness(inp)
        assert "diligence_readiness:missing_trial_data" in codes

    def test_missing_cmc_data_flagged(self):
        inp = _inp(cmc_package_completeness=0.30)
        _, codes = _score_diligence_readiness(inp)
        assert "diligence_readiness:missing_CMC_data" in codes


# ---------------------------------------------------------------------------
# 7. Gate treatment bands
# ---------------------------------------------------------------------------

class TestGateTreatment:

    def test_clean_band(self):
        t, m, c = _gate_treatment(0.90, [])
        assert t == AssetControlGateTreatment.CLEAN
        assert m == pytest.approx(1.0)
        assert c is None

    def test_mild_penalty_band(self):
        t, m, c = _gate_treatment(0.75, [])
        assert t == AssetControlGateTreatment.MILD_PENALTY
        assert m == pytest.approx(0.95)
        assert c is None

    def test_meaningful_penalty_band(self):
        t, m, c = _gate_treatment(0.60, [])
        assert t == AssetControlGateTreatment.MEANINGFUL_PENALTY
        assert m == pytest.approx(0.80)
        assert c is None

    def test_severe_cap_band(self):
        t, m, c = _gate_treatment(0.42, [])
        assert t == AssetControlGateTreatment.SEVERE_CAP
        assert m == pytest.approx(0.60)
        assert c == pytest.approx(0.55)

    def test_route_to_licensing_band(self):
        t, m, c = _gate_treatment(0.20, [])
        assert t == AssetControlGateTreatment.ROUTE_TO_LICENSING
        assert m == pytest.approx(0.40)
        assert c == pytest.approx(0.40)

    def test_no_ownable_rights_overrides_high_score(self):
        t, _, _ = _gate_treatment(0.90, ["no_ownable_rights"])
        assert t == AssetControlGateTreatment.HARD_FAIL

    def test_bucket_weights_sum_to_one(self):
        assert abs(sum(_BUCKET_WEIGHTS.values()) - 1.0) < 1e-9

    def test_gate_bands_monotone_descending(self):
        lowers = [lower for lower, *_ in _GATE_BANDS]
        for i in range(len(lowers) - 1):
            assert lowers[i] > lowers[i + 1]


# ---------------------------------------------------------------------------
# 8. Hard blockers
# ---------------------------------------------------------------------------

class TestHardBlockers:

    def test_no_ownable_rights_hard_fail(self):
        r = compute_asset_control_target(_inp(no_ownable_rights=True))
        assert r.is_hard_fail is True
        assert r.gate_treatment == AssetControlGateTreatment.HARD_FAIL
        assert "no_ownable_rights" in r.hard_blockers

    def test_fatal_ip_dispute_caps_score_at_030(self):
        r = compute_asset_control_target(_inp(fatal_ip_dispute=True))
        assert r.asset_control_score <= 0.30
        assert "fatal_ip_dispute" in r.hard_blockers

    def test_fully_licensed_away_routes_licensing(self):
        r = compute_asset_control_target(_inp(fully_licensed_away=True))
        assert r.asset_control_score <= 0.30
        assert "fully_licensed_away" in r.hard_blockers
        assert r.route_to_licensing is True

    def test_fatal_ip_dispute_not_hard_fail(self):
        """fatal_ip_dispute caps the score but does not set is_hard_fail."""
        r = compute_asset_control_target(_inp(fatal_ip_dispute=True))
        assert r.is_hard_fail is False

    def test_no_pair_level_cap_on_result(self):
        """is_pair_level_cap and pair_specific_caps must not exist on result."""
        r = compute_asset_control_target(_inp())
        assert not hasattr(r, "is_pair_level_cap")
        assert not hasattr(r, "pair_specific_caps")

    def test_hard_fail_in_one_call_does_not_affect_other(self):
        r_clean = compute_asset_control_target(_inp())
        r_blocked = compute_asset_control_target(_inp(no_ownable_rights=True))
        assert not r_clean.is_hard_fail
        assert r_blocked.is_hard_fail


# ---------------------------------------------------------------------------
# 9. Output flags for Layer 3B
# ---------------------------------------------------------------------------

class TestOutputFlags:

    def test_has_rofr_fact_true_when_rofr_present(self):
        r = compute_asset_control_target(_inp(has_right_of_first_refusal=True))
        assert r.has_rofr_fact is True

    def test_has_rofr_fact_false_by_default(self):
        r = compute_asset_control_target(_inp())
        assert r.has_rofr_fact is False

    def test_has_existing_partner_fact_true(self):
        r = compute_asset_control_target(_inp(has_existing_partnership=True))
        assert r.has_existing_partner_fact is True

    def test_has_existing_partner_fact_false_by_default(self):
        r = compute_asset_control_target(_inp())
        assert r.has_existing_partner_fact is False

    def test_manufacturing_complexity_flag_passthrough_low(self):
        r = compute_asset_control_target(_inp(manufacturing_complexity="low"))
        assert r.manufacturing_complexity_flag == "low"

    def test_manufacturing_complexity_flag_passthrough_high(self):
        r = compute_asset_control_target(_inp(manufacturing_complexity="high"))
        assert r.manufacturing_complexity_flag == "high"

    def test_manufacturing_complexity_flag_passthrough_medium(self):
        r = compute_asset_control_target(_inp(manufacturing_complexity="medium"))
        assert r.manufacturing_complexity_flag == "medium"

    def test_score_cap_property_matches_max_mna_score_cap(self):
        r = compute_asset_control_target(_inp())
        assert r.score_cap == r.max_mna_score_cap

    def test_score_cap_set_for_severe_gate(self):
        r = compute_asset_control_target(
            _inp(no_ownable_rights=False,
                 global_rights_control=0.10, key_geography_control=0.10,
                 royalty_cleanliness=0.10, no_blocking_rights=0.10,
                 patent_strength=0.10, ownership_cleanliness=0.10,
                 process_transferability=0.10, clinical_data_completeness=0.10)
        )
        if r.gate_treatment in (
            AssetControlGateTreatment.SEVERE_CAP,
            AssetControlGateTreatment.ROUTE_TO_LICENSING,
        ):
            assert r.score_cap is not None


# ---------------------------------------------------------------------------
# 10. No pair contamination
# ---------------------------------------------------------------------------

class TestNoPairContamination:

    def test_input_has_no_acquirer_is_existing_partner(self):
        assert not hasattr(AssetControlTargetInput.model_fields, "acquirer_is_existing_partner")

    def test_input_has_no_acquirer_manufacturing_fit(self):
        assert not hasattr(AssetControlTargetInput.model_fields, "acquirer_manufacturing_fit")

    def test_input_has_no_blocking_consent_right(self):
        assert not hasattr(AssetControlTargetInput.model_fields, "blocking_consent_right")

    def test_result_has_no_is_pair_level_cap(self):
        assert "is_pair_level_cap" not in AssetControlTargetResult.model_fields

    def test_result_has_no_pair_specific_caps(self):
        assert "pair_specific_caps" not in AssetControlTargetResult.model_fields

    def test_partner_encumbrance_facts_score_stable_across_acquirers(self):
        """Same target input must produce same partner score regardless of any
        downstream acquirer context — validates no pair state leaks in."""
        r1 = compute_asset_control_target(
            _inp(has_right_of_first_refusal=True, has_existing_partnership=True)
        )
        r2 = compute_asset_control_target(
            _inp(has_right_of_first_refusal=True, has_existing_partnership=True)
        )
        assert r1.partner_encumbrance_facts_score == pytest.approx(
            r2.partner_encumbrance_facts_score
        )

    def test_pair_bonus_code_never_in_triggered_encumbrances(self):
        r = compute_asset_control_target(_inp())
        assert "partner_freedom:existing_partner_bonus_applied" not in r.triggered_encumbrances

    def test_rofr_blocks_acquirer_code_never_in_triggered_encumbrances(self):
        r = compute_asset_control_target(_inp(has_right_of_first_refusal=True))
        assert (
            "partner_freedom:ROFR_or_opt_in_blocks_this_acquirer"
            not in r.triggered_encumbrances
        )

    def test_acquirer_capability_codes_never_in_triggered_encumbrances(self):
        r = compute_asset_control_target(_inp())
        assert "manufacturing_control:acquirer_strong_capability" not in r.triggered_encumbrances
        assert (
            "manufacturing_control:acquirer_weak_capability_amplifies_risk"
            not in r.triggered_encumbrances
        )


# ---------------------------------------------------------------------------
# 11. Valuation multiplier
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

    def test_rights_issue_reduces_multiplier(self):
        m_clean = _encumbrance_valuation_multiplier(1.0, 1.0, 1.0, 1.0)
        m_rights = _encumbrance_valuation_multiplier(0.0, 1.0, 1.0, 1.0)
        assert m_rights < m_clean

    def test_multiplier_in_range(self):
        for val in (0.0, 0.25, 0.50, 0.75, 1.0):
            m = _encumbrance_valuation_multiplier(val, 0.80, 0.80, 0.80)
            assert 0.0 < m <= 1.0

    def test_result_includes_valuation_multiplier(self):
        r = compute_asset_control_target(_inp())
        assert 0.0 < r.encumbrance_valuation_multiplier <= 1.0


# ---------------------------------------------------------------------------
# 12. Mapper: asset_control_target_from_target()
# ---------------------------------------------------------------------------

class _MockTarget:
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


class TestMapper:

    def test_global_rights_maps_to_high(self):
        inp = asset_control_target_from_target(_MockTarget(asset_rights_scope="global"))
        assert inp.global_rights_control >= 0.90
        assert inp.key_geography_control >= 0.85

    def test_regional_split_maps_to_low(self):
        inp = asset_control_target_from_target(_MockTarget(asset_rights_scope="regional_split"))
        assert inp.global_rights_control <= 0.55
        assert inp.key_geography_control <= 0.55

    def test_licensed_in_sets_fully_licensed_away(self):
        inp = asset_control_target_from_target(_MockTarget(asset_rights_scope="licensed_in"))
        assert inp.global_rights_control <= 0.30
        assert inp.fully_licensed_away is True

    def test_ip_dispute_lowers_ip_sub_scores(self):
        inp = asset_control_target_from_target(_MockTarget(has_ip_dispute=True))
        assert inp.ownership_cleanliness < 0.20
        assert inp.freedom_to_operate < 0.50

    def test_rofr_present_reduces_partner_severity(self):
        inp_no = asset_control_target_from_target(_MockTarget(has_right_of_first_refusal=False))
        inp_rofr = asset_control_target_from_target(_MockTarget(has_right_of_first_refusal=True))
        assert inp_rofr.partner_encumbrance_severity < inp_no.partner_encumbrance_severity

    def test_high_royalty_reduces_cleanliness(self):
        inp = asset_control_target_from_target(_MockTarget(royalty_stack_rate=0.30))
        assert inp.royalty_cleanliness < 0.30

    def test_mfg_dependency_reduces_scores(self):
        inp = asset_control_target_from_target(_MockTarget(has_manufacturing_dependency=True))
        assert inp.process_transferability < 0.50
        assert inp.supply_redundancy < 0.50

    def test_high_mfg_complexity_reduces_scores(self):
        inp_low = asset_control_target_from_target(_MockTarget(manufacturing_complexity="low"))
        inp_high = asset_control_target_from_target(_MockTarget(manufacturing_complexity="high"))
        assert inp_high.process_transferability < inp_low.process_transferability

    def test_manufacturing_complexity_passed_through(self):
        inp = asset_control_target_from_target(_MockTarget(manufacturing_complexity="high"))
        assert inp.manufacturing_complexity == "high"

    def test_mapper_does_not_set_acquirer_fields(self):
        """Mapper must not set any pair-specific fields."""
        inp = asset_control_target_from_target(_MockTarget())
        assert not hasattr(inp, "acquirer_is_existing_partner")
        assert not hasattr(inp, "acquirer_manufacturing_fit")
        assert not hasattr(inp, "blocking_consent_right")

    def test_end_to_end_global_clean_mild_or_better(self):
        r = compute_asset_control_target(
            asset_control_target_from_target(_MockTarget())
        )
        assert r.gate_treatment in (
            AssetControlGateTreatment.CLEAN,
            AssetControlGateTreatment.MILD_PENALTY,
            AssetControlGateTreatment.MEANINGFUL_PENALTY,
        )

    def test_end_to_end_licensed_in_routes_licensing(self):
        r = compute_asset_control_target(
            asset_control_target_from_target(_MockTarget(asset_rights_scope="licensed_in"))
        )
        assert r.gate_treatment == AssetControlGateTreatment.ROUTE_TO_LICENSING
        assert r.route_to_licensing is True


# ---------------------------------------------------------------------------
# 13. Backward-compatibility legacy fields
# ---------------------------------------------------------------------------

class TestBackwardCompatLegacy:

    def test_encumbrance_codes_alias(self):
        r = compute_asset_control_target(_inp())
        assert r.encumbrance_codes is r.triggered_encumbrances

    def test_legacy_flags_preserved(self):
        r = compute_asset_control_target(
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
        assert r.has_ip_dispute is True
        assert r.has_right_of_first_refusal is True
        assert r.has_existing_partnership is True
        assert r.has_co_development_obligation is True
        assert r.has_manufacturing_dependency is True
        assert r.royalty_stack_high is True
        assert r.asset_rights_scope == "regional_split"

    def test_penalty_multiplier_present(self):
        r = compute_asset_control_target(_inp())
        assert 0.0 < r.penalty_multiplier <= 1.0

    def test_result_is_frozen(self):
        r = compute_asset_control_target(_inp())
        with pytest.raises(Exception):
            r.asset_control_score = 0.5  # type: ignore[misc]

    def test_result_is_assetcontroltargetresult_instance(self):
        r = compute_asset_control_target(_inp())
        assert isinstance(r, AssetControlTargetResult)

    def test_encumbrance_flags_alias_resolves(self):
        # EncumbranceFlags in ma_eligibility must point to the same class
        assert EncumbranceFlags is AssetControlTargetResult

    def test_rationale_non_empty(self):
        r = compute_asset_control_target(_inp())
        assert len(r.rationale) >= 1

    def test_confidence_reflects_diligence(self):
        r_high = compute_asset_control_target(_inp(
            clinical_data_completeness=0.95,
            cmc_package_completeness=0.95,
            regulatory_file_completeness=0.95,
            safety_database_quality=0.95,
            data_room_readiness=0.95,
        ))
        r_low = compute_asset_control_target(_inp(
            clinical_data_completeness=0.20,
            cmc_package_completeness=0.20,
            regulatory_file_completeness=0.20,
            safety_database_quality=0.20,
            data_room_readiness=0.20,
        ))
        assert r_high.asset_control_confidence == "high"
        assert r_low.asset_control_confidence == "low"
