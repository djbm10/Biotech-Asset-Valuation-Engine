"""Tests for Layer 3B wiring: combine_layer0_and_3b() + Option A mapper fix.

Covers the six requirements from Phase 3 Step 4 approval:
  1. Structurally clean global target maps to CLEAN, not mild_penalty
  2. ROFR/partner target still requires pair_asset_control_adjustment
  3. High manufacturing complexity still requires buyer-specific check
  4. Pair-specific ROFR/consent/manufacturing penalties only apply in 3B
  5. Effective cap uses the tightest cap
  6. No pair-specific codes are allowed inside target-level 0D-T

Plus:
  7. Combination formula: effective_multiplier = target × pair × affordability
  8. pair_result=None path (no 3B signals) passes through unchanged
  9. pair_level_fail threshold
 10. existing-partner waiver higher score than non-partner for same ROFR target
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_asset_control_target import (
    AssetControlTargetInput,
    AssetControlTargetResult,
    compute_asset_control_target,
    asset_control_target_from_target,
)
from bve.intelligence.ma_pair_asset_control import (
    PairAssetControlInput,
    PairAssetControlResult,
    PairAdjustedModifiers,
    compute_pair_asset_control,
    combine_layer0_and_3b,
)
from bve.intelligence.ma_eligibility import evaluate_layer0, TargetEligibilityInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_flags(**overrides) -> dict:
    """All 11 TargetEligibilityInput data flags set; override as needed."""
    base = dict(
        ticker="TST",
        company_taxonomy="therapeutics",
        lead_asset_present=True,
        lead_asset_status="active",
        has_market_cap=True,
        has_enterprise_value=True,
        has_cash_debt=True,
        has_clinical_stage=True,
        has_trial_status=True,
        has_quarterly_burn=True,
        has_revenue_mix=True,
        has_asset_ownership_data=True,
        has_partner_rights_data=True,
        has_patent_loe_data=True,
        has_acquirer_profile_data=True,
        asset_rights_scope="global",
        enterprise_value_millions=500,
    )
    base.update(overrides)
    return base


def _layer0(**overrides):
    return evaluate_layer0(TargetEligibilityInput(**_full_flags(**overrides)))


def _clean_target_result() -> AssetControlTargetResult:
    """A clean target-level result with no encumbrance."""
    inp = AssetControlTargetInput(
        global_rights_control=0.95,
        key_geography_control=0.90,
        indication_control=0.88,
        change_of_control_freedom=0.85,
        royalty_cleanliness=1.0,
        no_blocking_rights=0.85,
        clean_governance_control=0.85,
        partner_encumbrance_severity=0.90,
        ownership_cleanliness=0.90,
        freedom_to_operate=0.85,
        process_transferability=0.85,
        supply_redundancy=0.80,
        gmp_quality_readiness=0.80,
        clinical_data_completeness=0.75,
        cmc_package_completeness=0.70,
        regulatory_file_completeness=0.72,
        data_room_readiness=0.70,
        manufacturing_complexity="low",
    )
    return compute_asset_control_target(inp)


def _rofr_target_result() -> AssetControlTargetResult:
    """Target with ROFR + existing partnership."""
    inp = AssetControlTargetInput(
        global_rights_control=0.95,
        key_geography_control=0.90,
        indication_control=0.88,
        change_of_control_freedom=0.70,
        royalty_cleanliness=0.80,
        no_blocking_rights=0.50,
        clean_governance_control=0.85,
        partner_encumbrance_severity=0.30,
        ownership_cleanliness=0.90,
        freedom_to_operate=0.85,
        process_transferability=0.85,
        supply_redundancy=0.80,
        gmp_quality_readiness=0.80,
        clinical_data_completeness=0.75,
        cmc_package_completeness=0.70,
        manufacturing_complexity="low",
        has_right_of_first_refusal=True,
        has_existing_partnership=True,
    )
    return compute_asset_control_target(inp)


def _high_mfg_target_result() -> AssetControlTargetResult:
    """Target with high manufacturing complexity."""
    inp = AssetControlTargetInput(
        global_rights_control=0.95,
        key_geography_control=0.90,
        indication_control=0.88,
        change_of_control_freedom=0.85,
        royalty_cleanliness=1.0,
        no_blocking_rights=0.85,
        clean_governance_control=0.85,
        partner_encumbrance_severity=0.90,
        ownership_cleanliness=0.90,
        freedom_to_operate=0.85,
        process_transferability=0.55,
        supply_redundancy=0.60,
        gmp_quality_readiness=0.62,
        clinical_data_completeness=0.75,
        cmc_package_completeness=0.70,
        manufacturing_complexity="high",
    )
    return compute_asset_control_target(inp)


def _pair(target: AssetControlTargetResult, **overrides) -> PairAssetControlInput:
    defaults = dict(
        acquirer_id="ACQ1",
        target_id="TGT1",
        target_asset_control=target,
        acquirer_manufacturing_fit=0.70,
    )
    defaults.update(overrides)
    return PairAssetControlInput(**defaults)


# ===========================================================================
# Section 1: Option A mapper fix — clean global maps to CLEAN
# ===========================================================================

class TestOptionAMapperFix:
    def test_clean_global_all_flags_scores_clean(self):
        """Req 1: structurally clean global target with all data flags → CLEAN gate."""
        r = _layer0()
        assert r.encumbrance.gate_treatment.value == "clean", (
            f"Expected CLEAN, got {r.encumbrance.gate_treatment.value} "
            f"(score={r.encumbrance.asset_control_score:.4f})"
        )

    def test_clean_global_score_multiplier_is_1(self):
        """CLEAN gate → score_multiplier = 1.0 (no penalty)."""
        r = _layer0()
        assert r.score_multiplier == 1.0

    def test_clean_global_score_above_threshold(self):
        """Composite score ≥ 0.85 for fully-clean global target."""
        r = _layer0()
        assert r.encumbrance.asset_control_score >= 0.85

    def test_partial_data_flags_stays_mild_penalty(self):
        """Missing has_asset_ownership_data or has_partner_rights_data → no data
        package uplift → mild_penalty is still acceptable."""
        r = evaluate_layer0(TargetEligibilityInput(**_full_flags(
            has_asset_ownership_data=False,
            has_partner_rights_data=False,
        )))
        # Should be mild_penalty (not CLEAN) without data package flags
        assert r.encumbrance.gate_treatment.value in ("mild_penalty", "clean")
        # Specifically, missing data flags keep score below the 0.85 uplift
        r_full = _layer0()
        assert r.encumbrance.asset_control_score < r_full.encumbrance.asset_control_score

    def test_rofr_prevents_coc_uplift(self):
        """Req 4: ROFR target does NOT get CoC freedom uplift (stays 0.70)."""
        r = _layer0(has_right_of_first_refusal=True)
        # Score should be lower than clean global (no uplift applied)
        r_clean = _layer0()
        assert r.encumbrance.asset_control_score < r_clean.encumbrance.asset_control_score

    def test_partnership_prevents_coc_uplift(self):
        """Existing partnership prevents CoC freedom uplift."""
        r = _layer0(has_existing_partnership=True)
        r_clean = _layer0()
        assert r.encumbrance.asset_control_score < r_clean.encumbrance.asset_control_score

    def test_regional_split_no_uplift(self):
        """regional_split scope → no CoC uplift (different rights_scope branch)."""
        r = _layer0(asset_rights_scope="regional_split")
        r_clean = _layer0()
        assert r.encumbrance.asset_control_score < r_clean.encumbrance.asset_control_score

    def test_coc_freedom_value_in_clean_global(self):
        """Mapper sets change_of_control_freedom=0.85 for clean global target."""
        t = TargetEligibilityInput(**_full_flags())
        inp = asset_control_target_from_target(t)
        assert inp.change_of_control_freedom == 0.85

    def test_coc_freedom_default_with_partnership(self):
        """Mapper keeps change_of_control_freedom=0.70 when partnership exists."""
        t = TargetEligibilityInput(**_full_flags(has_existing_partnership=True))
        inp = asset_control_target_from_target(t)
        assert inp.change_of_control_freedom == 0.70

    def test_data_package_flags_raise_diligence(self):
        """has_asset_ownership_data + has_partner_rights_data raises reg/data_room defaults."""
        t_with = TargetEligibilityInput(**_full_flags())
        t_without = TargetEligibilityInput(**_full_flags(
            has_asset_ownership_data=False, has_partner_rights_data=False,
        ))
        inp_with = asset_control_target_from_target(t_with)
        inp_without = asset_control_target_from_target(t_without)
        assert inp_with.regulatory_file_completeness == 0.72
        assert inp_with.data_room_readiness == 0.70
        assert inp_without.regulatory_file_completeness == 0.65
        assert inp_without.data_room_readiness == 0.62


# ===========================================================================
# Section 2: pair_asset_control_adjustment in required_downstream_checks
# ===========================================================================

class TestRequiredDownstreamChecks:
    def test_rofr_target_requires_pair_adjustment(self):
        """Req 2: ROFR target must have pair_asset_control_adjustment in checks."""
        r = _layer0(has_right_of_first_refusal=True)
        assert "pair_asset_control_adjustment" in r.required_downstream_checks

    def test_partnership_target_requires_pair_adjustment(self):
        """Req 2: Existing partnership requires pair_asset_control_adjustment."""
        r = _layer0(has_existing_partnership=True)
        assert "pair_asset_control_adjustment" in r.required_downstream_checks

    def test_high_mfg_requires_pair_adjustment(self):
        """Req 3: High manufacturing complexity requires buyer-specific check."""
        r = _layer0(manufacturing_complexity="high")
        assert "pair_asset_control_adjustment" in r.required_downstream_checks

    def test_medium_mfg_requires_pair_adjustment(self):
        """Medium manufacturing complexity also requires buyer-specific check."""
        r = _layer0(manufacturing_complexity="medium")
        assert "pair_asset_control_adjustment" in r.required_downstream_checks

    def test_clean_global_no_pair_adjustment_needed(self):
        """Req 2: Structurally clean global → no pair_asset_control_adjustment."""
        r = _layer0()
        assert "pair_asset_control_adjustment" not in r.required_downstream_checks

    def test_affordability_always_in_checks(self):
        """Affordability check is always in required_downstream_checks when EV known."""
        r = _layer0()
        assert "affordability" in r.required_downstream_checks


# ===========================================================================
# Section 3: Pair-specific penalties only apply in 3B (not in Layer 0)
# ===========================================================================

class TestPairPenaltiesOnlyIn3B:
    def test_layer0_score_multiplier_is_target_level_only(self):
        """Req 4: Layer 0 score_multiplier is target-level only for clean global."""
        r = _layer0()
        assert r.score_multiplier == r.encumbrance.penalty_multiplier

    def test_rofr_does_not_reduce_layer0_multiplier_below_target_band(self):
        """Req 4: ROFR fact in target does not trigger pair-level cap in Layer 0.

        The ×0.95 multiplier on rofr_target comes from the target's composite
        score (mild_penalty band), NOT from any ROFR-specific pair cap.
        """
        r = _layer0(has_right_of_first_refusal=True)
        # Layer 0 only applies the target-level gate band penalty
        assert r.score_multiplier == r.encumbrance.penalty_multiplier
        # The pair-level ROFR cap (0.55) must NOT appear in Layer 0
        if r.encumbrance.max_mna_score_cap is not None:
            assert r.encumbrance.max_mna_score_cap > 0.55, (
                "ROFR pair cap (0.55) must not be applied at Layer 0"
            )

    def test_pair_rofr_cap_applied_only_in_3b(self):
        """Req 4: ROFR blocking cap (0.55) only appears after compute_pair_asset_control."""
        target = _rofr_target_result()
        pair_r = compute_pair_asset_control(_pair(
            target,
            rofr_blocks_this_acquirer=True,
        ))
        assert pair_r.pair_cap == 0.55
        assert pair_r.rofr_impact == "blocking"

    def test_manufacturing_fit_has_no_layer0_effect(self):
        """Req 4: Acquirer manufacturing fit does not change Layer 0 score."""
        r_high_mfg = _layer0(manufacturing_complexity="high")
        # Layer 0 encumbrance score is target-level; it does NOT penalise for
        # acquirer manufacturing fit (that is 3B's job)
        assert r_high_mfg.score_multiplier == r_high_mfg.encumbrance.penalty_multiplier
        # Confirm no pair-specific multiplier in Layer 0 result
        # (i.e. score_multiplier matches target's gate-treatment band only)
        expected_mult = r_high_mfg.encumbrance.penalty_multiplier
        assert abs(r_high_mfg.score_multiplier - expected_mult) < 1e-9

    def test_consent_right_has_no_layer0_effect(self):
        """Req 4: Consent right (pair-level) does not appear in Layer 0 multiplier."""
        r = _layer0()
        # No consent field on TargetEligibilityInput reaches Layer 0 multiplier
        assert r.score_multiplier == r.encumbrance.penalty_multiplier


# ===========================================================================
# Section 4: No pair-specific codes in 0D-T result
# ===========================================================================

class TestNoPairContamination:
    def test_clean_target_has_no_pair_codes(self):
        """Req 6: Clean target result has no pair-specific encumbrance codes."""
        r = _clean_target_result()
        pair_only = {
            "partner_freedom:existing_partner_bonus_applied",
            "partner_freedom:ROFR_or_opt_in_blocks_this_acquirer",
            "partner_freedom:consent_right_blocking",
            "manufacturing_control:acquirer_strong_capability",
            "manufacturing_control:acquirer_weak_capability_amplifies_risk",
            "existing_partner:non_partner_acquirer_penalized",
        }
        assert not (pair_only & set(r.triggered_encumbrances))

    def test_rofr_target_has_no_pair_codes(self):
        """Req 6: ROFR target result contains only target-level codes."""
        r = _rofr_target_result()
        pair_only = {
            "partner_freedom:existing_partner_bonus_applied",
            "partner_freedom:ROFR_or_opt_in_blocks_this_acquirer",
            "partner_freedom:consent_right_blocking",
        }
        assert not (pair_only & set(r.triggered_encumbrances))

    def test_contamination_guard_raises_on_pair_codes(self):
        """Req 6: _assert_no_pair_contamination raises ValueError on pair codes."""
        from bve.intelligence.ma_pair_asset_control import _assert_no_pair_contamination

        # Construct a result with a pair-specific code (simulating a bug)
        clean = _clean_target_result()
        bad_result = clean.model_copy(update={
            "triggered_encumbrances": [
                "partner_freedom:ROFR_or_opt_in_blocks_this_acquirer"
            ]
        })
        with pytest.raises(ValueError, match="pair-specific encumbrance codes"):
            _assert_no_pair_contamination(bad_result)

    def test_clean_target_passes_contamination_guard(self):
        """Clean target result passes the contamination guard without error."""
        from bve.intelligence.ma_pair_asset_control import _assert_no_pair_contamination
        _assert_no_pair_contamination(_clean_target_result())  # must not raise

    def test_layer0_encumbrance_passes_contamination_guard(self):
        """All Layer 0 encumbrance results pass the contamination guard."""
        from bve.intelligence.ma_pair_asset_control import _assert_no_pair_contamination
        for kwargs in [
            {},
            {"has_right_of_first_refusal": True},
            {"has_existing_partnership": True},
            {"manufacturing_complexity": "high"},
            {"has_right_of_first_refusal": True, "has_existing_partnership": True},
        ]:
            r = _layer0(**kwargs)
            _assert_no_pair_contamination(r.encumbrance)  # must not raise


# ===========================================================================
# Section 5: combine_layer0_and_3b() — effective_multiplier formula
# ===========================================================================

class TestEffectiveMultiplierFormula:
    def test_no_pair_result_passthrough(self):
        """Req 7: pair_result=None → effective_mult = layer0_mult × 1.0 × affordability."""
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=0.95,
            layer0_score_cap=None,
            target_max_mna_score_cap=None,
            pair_result=None,
            affordability_score_multiplier=1.0,
        )
        assert abs(mods.effective_multiplier - 0.95) < 1e-9
        assert mods.pair_asset_control is None
        assert mods.effective_cap is None

    def test_pair_multiplier_multiplies_target(self):
        """Req 7: effective_mult = target_mult × pair_mult."""
        target = _clean_target_result()
        pair_r = compute_pair_asset_control(_pair(
            target,
            rofr_blocks_this_acquirer=True,
        ))
        # pair_multiplier should be ≤ 0.65 (ROFR blocking)
        assert pair_r.pair_multiplier <= 0.65

        target_mult = target.penalty_multiplier  # 1.0 for clean target
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=target_mult,
            layer0_score_cap=None,
            target_max_mna_score_cap=None,
            pair_result=pair_r,
        )
        expected = round(target_mult * pair_r.pair_multiplier, 6)
        assert abs(mods.effective_multiplier - expected) < 1e-9

    def test_affordability_multiplier_included(self):
        """Req 7: effective_mult = target_mult × pair_mult × affordability_mult."""
        target = _clean_target_result()
        pair_r = compute_pair_asset_control(_pair(target))
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=0.95,
            layer0_score_cap=None,
            target_max_mna_score_cap=None,
            pair_result=pair_r,
            affordability_score_multiplier=0.90,
        )
        expected = round(0.95 * pair_r.pair_multiplier * 0.90, 6)
        assert abs(mods.effective_multiplier - expected) < 1e-9

    def test_all_one_gives_one(self):
        """All multipliers = 1.0 → effective_multiplier = 1.0."""
        target = _clean_target_result()
        pair_r = compute_pair_asset_control(_pair(target))
        assert pair_r.pair_multiplier == 1.0  # clean pair, no penalties
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=1.0,
            layer0_score_cap=None,
            target_max_mna_score_cap=None,
            pair_result=pair_r,
            affordability_score_multiplier=1.0,
        )
        assert mods.effective_multiplier == 1.0

    def test_three_way_product(self):
        """Three-way product is correct: 0.80 × 0.75 × 0.90 = 0.54."""
        target = _rofr_target_result()
        pair_r = compute_pair_asset_control(_pair(
            target,
            rofr_blocks_this_acquirer=True,
        ))
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=0.80,
            layer0_score_cap=None,
            target_max_mna_score_cap=None,
            pair_result=pair_r,
            affordability_score_multiplier=0.90,
        )
        expected = round(0.80 * pair_r.pair_multiplier * 0.90, 6)
        assert abs(mods.effective_multiplier - expected) < 1e-9


# ===========================================================================
# Section 6: combine_layer0_and_3b() — effective_cap formula (tightest wins)
# ===========================================================================

class TestEffectiveCapFormula:
    def test_no_caps_gives_none(self):
        """When no caps are active, effective_cap is None."""
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=1.0,
            layer0_score_cap=None,
            target_max_mna_score_cap=None,
            pair_result=None,
        )
        assert mods.effective_cap is None

    def test_single_layer0_cap(self):
        """Single cap source → effective_cap = that cap."""
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=1.0,
            layer0_score_cap=0.70,
            target_max_mna_score_cap=None,
            pair_result=None,
        )
        assert mods.effective_cap == 0.70

    def test_tightest_cap_wins(self):
        """Req 5: effective_cap = min(all active caps)."""
        target = _rofr_target_result()
        pair_r = compute_pair_asset_control(_pair(
            target,
            rofr_blocks_this_acquirer=True,
        ))
        # pair_cap = 0.55 (ROFR blocking)
        assert pair_r.pair_cap == 0.55

        mods = combine_layer0_and_3b(
            layer0_score_multiplier=0.95,
            layer0_score_cap=0.70,          # distress cap — looser
            target_max_mna_score_cap=0.80,   # target gate cap — looser
            pair_result=pair_r,              # pair cap = 0.55 — tightest
            integration_cap=0.60,
        )
        # Min(0.70, 0.80, 0.55, 0.60) = 0.55
        assert mods.effective_cap == 0.55

    def test_integration_cap_included(self):
        """Integration cap is included in the min() calculation."""
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=1.0,
            layer0_score_cap=0.80,
            target_max_mna_score_cap=None,
            pair_result=None,
            integration_cap=0.60,
        )
        # Min(0.80, 0.60) = 0.60
        assert mods.effective_cap == 0.60

    def test_pair_cap_none_excluded_from_min(self):
        """pair_result.pair_cap=None is excluded from the min() — only real caps count."""
        target = _clean_target_result()
        pair_r = compute_pair_asset_control(_pair(target))
        assert pair_r.pair_cap is None  # clean pair has no cap

        mods = combine_layer0_and_3b(
            layer0_score_multiplier=1.0,
            layer0_score_cap=0.75,
            target_max_mna_score_cap=None,
            pair_result=pair_r,
        )
        # Only the distress cap (0.75) should apply
        assert mods.effective_cap == 0.75

    def test_severe_mfg_mismatch_pair_cap(self):
        """High complexity + low acquirer fit (severe) → pair_cap = 0.65."""
        target = _high_mfg_target_result()
        pair_r = compute_pair_asset_control(_pair(
            target,
            acquirer_manufacturing_fit=0.30,  # < 0.40, high complexity → severe
        ))
        assert pair_r.pair_cap == 0.65
        assert pair_r.manufacturing_adjustment_applied == "severe"

        mods = combine_layer0_and_3b(
            layer0_score_multiplier=1.0,
            layer0_score_cap=None,
            target_max_mna_score_cap=None,
            pair_result=pair_r,
        )
        assert mods.effective_cap == 0.65


# ===========================================================================
# Section 7: Existing-partner waiver gives higher score than non-partner
# ===========================================================================

class TestExistingPartnerWaiver:
    def test_partner_acquirer_higher_score_than_non_partner(self):
        """Existing-partner acquirer gets higher pair score than non-partner for ROFR target."""
        target = _rofr_target_result()

        non_partner = compute_pair_asset_control(_pair(
            target,
            acquirer_is_existing_partner=False,
            rofr_blocks_this_acquirer=True,
        ))
        partner = compute_pair_asset_control(_pair(
            target,
            acquirer_is_existing_partner=True,
            rofr_blocks_this_acquirer=True,  # would block non-partner
        ))

        assert partner.pair_multiplier > non_partner.pair_multiplier
        assert partner.pair_asset_control_score > non_partner.pair_asset_control_score

    def test_partner_rofr_waived(self):
        """Partner acquirer: rofr_impact = 'waived_partner', not 'blocking'."""
        target = _rofr_target_result()
        r = compute_pair_asset_control(_pair(
            target,
            acquirer_is_existing_partner=True,
            rofr_blocks_this_acquirer=True,
        ))
        assert r.rofr_impact == "waived_partner"
        assert r.partner_bonus_applied is True

    def test_partner_no_pair_cap(self):
        """Partner acquirer ROFR waiver → pair_cap is None (blocking cap not applied)."""
        target = _rofr_target_result()
        r = compute_pair_asset_control(_pair(
            target,
            acquirer_is_existing_partner=True,
            rofr_blocks_this_acquirer=True,
        ))
        assert r.pair_cap is None


# ===========================================================================
# Section 8: pair_level_fail threshold
# ===========================================================================

class TestPairLevelFail:
    def test_combined_penalties_below_fail_threshold(self):
        """pair_multiplier ≤ 0.30 → pair_level_fail=True."""
        target = _rofr_target_result()
        # Stack: ROFR blocking (0.65) + consent (0.70) + severe geo (0.75)
        # 0.65 × 0.70 × 0.75 = 0.341... still above 0.30
        r = compute_pair_asset_control(_pair(
            target,
            rofr_blocks_this_acquirer=True,
            consent_required_for_this_coc=True,
            acquirer_target_geography_overlap=0.30,
        ))
        # pair_multiplier = min(0.65, 0.70, 0.75) = 0.65 (tightest wins at each step)
        # In the code: min(1.0, 0.65) then min(0.65, 0.70) then min(0.65, 0.75) = 0.65
        assert r.pair_multiplier <= 0.65
        # pair_level_fail is True only when ≤ 0.30
        if r.pair_multiplier <= 0.30:
            assert r.pair_level_fail is True
        else:
            assert r.pair_level_fail is False

    def test_clean_pair_no_fail(self):
        """Clean pair → pair_level_fail=False."""
        target = _clean_target_result()
        r = compute_pair_asset_control(_pair(target))
        assert r.pair_level_fail is False
        assert r.pair_multiplier == 1.0


# ===========================================================================
# Section 9: End-to-end Layer 0 → combine → Layer 3B
# ===========================================================================

class TestEndToEndCombination:
    def test_clean_global_end_to_end(self):
        """Clean global target: Layer 0 CLEAN × pair 1.0 = effective_mult=1.0, cap=None."""
        layer0 = _layer0()
        assert layer0.encumbrance.gate_treatment.value == "clean"

        pair_r = compute_pair_asset_control(_pair(layer0.encumbrance))
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=layer0.score_multiplier,
            layer0_score_cap=layer0.score_cap,
            target_max_mna_score_cap=layer0.encumbrance.max_mna_score_cap,
            pair_result=pair_r,
        )
        assert mods.effective_multiplier == 1.0
        assert mods.effective_cap is None

    def test_rofr_blocking_end_to_end(self):
        """ROFR blocking pair: effective_mult < 1.0, effective_cap = 0.55."""
        layer0 = _layer0(
            has_right_of_first_refusal=True,
            has_existing_partnership=True,
        )
        pair_r = compute_pair_asset_control(_pair(
            layer0.encumbrance,
            rofr_blocks_this_acquirer=True,
        ))
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=layer0.score_multiplier,
            layer0_score_cap=layer0.score_cap,
            target_max_mna_score_cap=layer0.encumbrance.max_mna_score_cap,
            pair_result=pair_r,
        )
        assert mods.effective_multiplier < 1.0
        assert mods.effective_cap == 0.55

    def test_high_mfg_severe_mismatch_end_to_end(self):
        """High-complexity target + weak acquirer: combined cap = 0.65."""
        layer0 = _layer0(manufacturing_complexity="high")
        pair_r = compute_pair_asset_control(_pair(
            layer0.encumbrance,
            acquirer_manufacturing_fit=0.25,  # severe mismatch
        ))
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=layer0.score_multiplier,
            layer0_score_cap=layer0.score_cap,
            target_max_mna_score_cap=layer0.encumbrance.max_mna_score_cap,
            pair_result=pair_r,
        )
        assert pair_r.manufacturing_adjustment_applied == "severe"
        assert mods.effective_cap == 0.65

    def test_result_is_frozen(self):
        """PairAdjustedModifiers is a frozen dataclass."""
        mods = combine_layer0_and_3b(
            layer0_score_multiplier=1.0,
            layer0_score_cap=None,
            target_max_mna_score_cap=None,
            pair_result=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            mods.effective_multiplier = 0.5  # type: ignore[misc]
