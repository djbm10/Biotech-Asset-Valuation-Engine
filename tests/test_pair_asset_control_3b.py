"""Tests for Layer 3B — Pair-Specific Asset-Control / Partner-Control Adjustment.

Coverage:
  1.  ROFR / opt-in caps (blocking, soft, waived)
  2.  Consent right impact
  3.  Existing partner waiver (suppresses ROFR and consent penalties)
  4.  Manufacturing mismatch rules (high/medium complexity vs low/moderate/strong fit)
  5.  Regional rights mismatch (severe and partial)
  6.  Exclusivity conflict penalty
  7.  No double-counting: pair_multiplier is ADDITIONAL to target-level baseline
  8.  Combined scenarios
  9.  Pair scope and result fields
 10.  Double-count guard (raises if target result contains pair-specific codes)
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_asset_control_target import (
    AssetControlTargetInput,
    AssetControlTargetResult,
    compute_asset_control_target,
)
from bve.intelligence.ma_pair_asset_control import (
    PairAssetControlInput,
    PairAssetControlResult,
    _PAIR_ONLY_ENCUMBRANCE_CODES,
    _assert_no_pair_contamination,
    compute_pair_asset_control,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_target_inp(**kw) -> AssetControlTargetInput:
    """High-scoring, clean target input."""
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


def _target(**kw) -> AssetControlTargetResult:
    """Compute a clean target result with optional overrides."""
    return compute_asset_control_target(_clean_target_inp(**kw))


def _pair(
    acquirer_id: str = "ACQ",
    target_id: str = "TGT",
    target_complexity: str = "low",
    target_has_rofr: bool = False,
    target_has_partner: bool = False,
    **kw,
) -> PairAssetControlInput:
    t = _target(
        manufacturing_complexity=target_complexity,
        has_right_of_first_refusal=target_has_rofr,
        has_existing_partnership=target_has_partner,
    )
    return PairAssetControlInput(
        acquirer_id=acquirer_id,
        target_id=target_id,
        target_asset_control=t,
        **kw,
    )


# ---------------------------------------------------------------------------
# 1. ROFR / opt-in caps
# ---------------------------------------------------------------------------

class TestRofrOptIn:

    def test_rofr_blocking_sets_multiplier_at_most_065(self):
        r = compute_pair_asset_control(
            _pair(rofr_blocks_this_acquirer=True)
        )
        assert r.pair_multiplier <= 0.65

    def test_rofr_blocking_sets_cap_at_most_055(self):
        r = compute_pair_asset_control(
            _pair(rofr_blocks_this_acquirer=True)
        )
        assert r.pair_cap is not None
        assert r.pair_cap <= 0.55

    def test_rofr_blocking_impact_is_blocking(self):
        r = compute_pair_asset_control(
            _pair(rofr_blocks_this_acquirer=True)
        )
        assert r.rofr_impact == "blocking"

    def test_opt_in_active_sets_multiplier_at_most_080(self):
        r = compute_pair_asset_control(
            _pair(opt_in_right_active=True)
        )
        assert r.pair_multiplier <= 0.80

    def test_opt_in_impact_is_soft(self):
        r = compute_pair_asset_control(
            _pair(opt_in_right_active=True)
        )
        assert r.rofr_impact == "soft"

    def test_no_rofr_no_opt_in_no_penalty(self):
        r = compute_pair_asset_control(_pair())
        assert r.rofr_impact == "none"
        assert r.pair_multiplier == pytest.approx(1.0)
        assert r.pair_cap is None

    def test_target_rofr_fact_without_blocking_flag_is_soft(self):
        """ROFR exists on target but buyer-specific blocking not confirmed → soft."""
        r = compute_pair_asset_control(
            _pair(target_has_rofr=True, rofr_blocks_this_acquirer=False)
        )
        assert r.rofr_impact == "soft"
        # No hard multiplier applied (not confirmed blocking)
        assert r.pair_multiplier == pytest.approx(1.0)

    def test_target_rofr_fact_unconfirmed_adds_data_gap(self):
        r = compute_pair_asset_control(
            _pair(target_has_rofr=True, rofr_blocks_this_acquirer=False)
        )
        assert any("rofr_impact_unconfirmed" in gap for gap in r.data_gaps)


# ---------------------------------------------------------------------------
# 2. Consent right impact
# ---------------------------------------------------------------------------

class TestConsentRight:

    def test_consent_required_sets_multiplier_at_most_070(self):
        r = compute_pair_asset_control(
            _pair(consent_required_for_this_coc=True)
        )
        assert r.pair_multiplier <= 0.70

    def test_consent_right_impact_required(self):
        r = compute_pair_asset_control(
            _pair(consent_required_for_this_coc=True)
        )
        assert r.consent_right_impact == "required"

    def test_no_consent_no_impact(self):
        r = compute_pair_asset_control(_pair())
        assert r.consent_right_impact == "none"

    def test_rofr_and_consent_compound(self):
        """Both blocking ROFR and consent → tightest constraint wins."""
        r = compute_pair_asset_control(
            _pair(rofr_blocks_this_acquirer=True, consent_required_for_this_coc=True)
        )
        # ROFR cap (0.65) is tighter than consent (0.70)
        assert r.pair_multiplier <= 0.65
        assert r.rofr_impact == "blocking"
        assert r.consent_right_impact == "required"


# ---------------------------------------------------------------------------
# 3. Existing partner waiver
# ---------------------------------------------------------------------------

class TestExistingPartnerWaiver:

    def test_existing_partner_waives_blocking_rofr(self):
        r = compute_pair_asset_control(
            _pair(
                target_has_rofr=True,
                rofr_blocks_this_acquirer=True,
                acquirer_is_existing_partner=True,
            )
        )
        assert r.rofr_impact == "waived_partner"
        # No ROFR multiplier applied
        assert r.pair_multiplier == pytest.approx(1.0)

    def test_existing_partner_waives_consent(self):
        r = compute_pair_asset_control(
            _pair(
                target_has_partner=True,
                consent_required_for_this_coc=True,
                acquirer_is_existing_partner=True,
            )
        )
        assert r.consent_right_impact == "waived_partner"
        assert r.pair_multiplier == pytest.approx(1.0)

    def test_existing_partner_match_true_on_result(self):
        r = compute_pair_asset_control(
            _pair(acquirer_is_existing_partner=True)
        )
        assert r.existing_partner_match is True

    def test_partner_bonus_applied_true_when_existing_partner(self):
        r = compute_pair_asset_control(
            _pair(acquirer_is_existing_partner=True, target_has_rofr=True)
        )
        assert r.partner_bonus_applied is True

    def test_partner_bonus_applied_false_for_non_partner(self):
        r = compute_pair_asset_control(_pair())
        assert r.partner_bonus_applied is False

    def test_non_partner_rofr_still_blocks(self):
        """Confirm waiver only applies when acquirer IS existing partner."""
        r = compute_pair_asset_control(
            _pair(rofr_blocks_this_acquirer=True, acquirer_is_existing_partner=False)
        )
        assert r.rofr_impact == "blocking"
        assert r.pair_multiplier <= 0.65


# ---------------------------------------------------------------------------
# 4. Manufacturing mismatch rules
# ---------------------------------------------------------------------------

class TestManufacturingMismatch:

    def test_high_complexity_low_fit_severe_multiplier(self):
        """High complexity + acquirer_mfg_fit < 0.40 → pair_multiplier ≤ 0.75."""
        r = compute_pair_asset_control(
            _pair(target_complexity="high", acquirer_manufacturing_fit=0.30)
        )
        assert r.pair_multiplier <= 0.75

    def test_high_complexity_low_fit_cap_065(self):
        """High complexity + low fit → pair_cap ≤ 0.65."""
        r = compute_pair_asset_control(
            _pair(target_complexity="high", acquirer_manufacturing_fit=0.30)
        )
        assert r.pair_cap is not None
        assert r.pair_cap <= 0.65

    def test_high_complexity_low_fit_adjustment_is_severe(self):
        r = compute_pair_asset_control(
            _pair(target_complexity="high", acquirer_manufacturing_fit=0.30)
        )
        assert r.manufacturing_adjustment_applied == "severe"

    def test_high_complexity_low_fit_sets_mismatch_flag(self):
        r = compute_pair_asset_control(
            _pair(target_complexity="high", acquirer_manufacturing_fit=0.30)
        )
        assert r.manufacturing_mismatch_flag is True

    def test_high_complexity_low_fit_rationale_includes_mismatch(self):
        r = compute_pair_asset_control(
            _pair(target_complexity="high", acquirer_manufacturing_fit=0.30)
        )
        assert any("manufacturing_complexity_buyer_mismatch" in line for line in r.rationale)

    def test_medium_complexity_low_fit_moderate_multiplier(self):
        """Medium complexity + acquirer_mfg_fit < 0.40 → pair_multiplier ≤ 0.85."""
        r = compute_pair_asset_control(
            _pair(target_complexity="medium", acquirer_manufacturing_fit=0.30)
        )
        assert r.pair_multiplier <= 0.85

    def test_medium_complexity_low_fit_no_cap(self):
        """Medium mismatch does not set a pair_cap."""
        r = compute_pair_asset_control(
            _pair(target_complexity="medium", acquirer_manufacturing_fit=0.30)
        )
        assert r.manufacturing_adjustment_applied == "moderate"

    def test_high_complexity_moderate_fit_mild_penalty(self):
        """High complexity + 0.40 ≤ fit < 0.80 → mild penalty only (≤ 0.90)."""
        r = compute_pair_asset_control(
            _pair(target_complexity="high", acquirer_manufacturing_fit=0.60)
        )
        assert r.pair_multiplier <= 0.90
        assert r.manufacturing_adjustment_applied == "mild"

    def test_strong_fit_no_manufacturing_penalty(self):
        """acquirer_mfg_fit >= 0.80 → no manufacturing penalty regardless of complexity."""
        r_high = compute_pair_asset_control(
            _pair(target_complexity="high", acquirer_manufacturing_fit=0.85)
        )
        r_medium = compute_pair_asset_control(
            _pair(target_complexity="medium", acquirer_manufacturing_fit=0.90)
        )
        assert r_high.manufacturing_adjustment_applied == "none"
        assert r_medium.manufacturing_adjustment_applied == "none"
        # pair_multiplier should still be 1.0 when only strong mfg fit is a signal
        assert r_high.pair_multiplier == pytest.approx(1.0)
        assert r_medium.pair_multiplier == pytest.approx(1.0)

    def test_low_complexity_low_fit_no_penalty(self):
        """Low-complexity target is accessible regardless of acquirer mfg fit."""
        r = compute_pair_asset_control(
            _pair(target_complexity="low", acquirer_manufacturing_fit=0.20)
        )
        assert r.manufacturing_adjustment_applied == "none"
        assert r.manufacturing_mismatch_flag is False

    def test_mfg_fit_threshold_exactly_040_is_not_low(self):
        """fit=0.40 is NOT < 0.40 → moderate fit path, not severe/moderate mismatch."""
        r = compute_pair_asset_control(
            _pair(target_complexity="high", acquirer_manufacturing_fit=0.40)
        )
        # Should be mild (0.40–0.80 range), not severe
        assert r.manufacturing_adjustment_applied == "mild"

    def test_mfg_fit_threshold_exactly_080_no_penalty(self):
        """fit=0.80 → strong capability, no penalty."""
        r = compute_pair_asset_control(
            _pair(target_complexity="high", acquirer_manufacturing_fit=0.80)
        )
        assert r.manufacturing_adjustment_applied == "none"


# ---------------------------------------------------------------------------
# 5. Regional rights mismatch
# ---------------------------------------------------------------------------

class TestRegionalRightsMismatch:

    def test_severe_mismatch_below_050_multiplier(self):
        """Geographic overlap < 0.50 → pair_multiplier ≤ 0.75."""
        r = compute_pair_asset_control(
            _pair(acquirer_target_geography_overlap=0.30)
        )
        assert r.pair_multiplier <= 0.75

    def test_severe_mismatch_cap_065(self):
        r = compute_pair_asset_control(
            _pair(acquirer_target_geography_overlap=0.30)
        )
        assert r.pair_cap is not None
        assert r.pair_cap <= 0.65

    def test_partial_mismatch_050_to_080_multiplier(self):
        """Geographic overlap 0.50 ≤ x < 0.80 → pair_multiplier ≤ 0.90."""
        r = compute_pair_asset_control(
            _pair(acquirer_target_geography_overlap=0.65)
        )
        assert r.pair_multiplier <= 0.90

    def test_partial_mismatch_no_cap(self):
        r = compute_pair_asset_control(
            _pair(acquirer_target_geography_overlap=0.65)
        )
        # Partial mismatch does not force a hard cap
        assert r.pair_cap is None

    def test_full_overlap_no_penalty(self):
        r = compute_pair_asset_control(
            _pair(acquirer_target_geography_overlap=1.0)
        )
        # No geo penalty; pair_multiplier should be 1.0 in a clean pair
        assert r.pair_multiplier == pytest.approx(1.0)

    def test_regional_rights_fit_on_result(self):
        r = compute_pair_asset_control(
            _pair(acquirer_target_geography_overlap=0.70)
        )
        assert r.regional_rights_fit == pytest.approx(0.70)

    def test_exact_050_is_not_severe(self):
        """Overlap = 0.50 is not < 0.50, so partial mismatch path applies."""
        r = compute_pair_asset_control(
            _pair(acquirer_target_geography_overlap=0.50)
        )
        assert r.pair_multiplier <= 0.90
        assert r.pair_cap is None  # partial, not severe


# ---------------------------------------------------------------------------
# 6. Exclusivity conflict
# ---------------------------------------------------------------------------

class TestExclusivityConflict:

    def test_conflict_sets_multiplier_at_most_080(self):
        r = compute_pair_asset_control(
            _pair(exclusivity_conflict_for_this_acquirer=True)
        )
        assert r.pair_multiplier <= 0.80

    def test_no_conflict_no_penalty(self):
        r = compute_pair_asset_control(_pair())
        # Exclusivity not flagged
        assert not any("exclusivity" in line for line in r.rationale)


# ---------------------------------------------------------------------------
# 7. No double-counting
# ---------------------------------------------------------------------------

class TestNoDoubleCount:

    def test_clean_pair_pair_multiplier_is_one(self):
        """A clean pair with no pair-specific issues should have multiplier=1.0."""
        r = compute_pair_asset_control(_pair())
        assert r.pair_multiplier == pytest.approx(1.0)
        assert r.pair_cap is None

    def test_pair_multiplier_independent_of_target_composite(self):
        """Different target composite scores → same pair_multiplier when pair has no issues."""
        target_clean = compute_asset_control_target(_clean_target_inp())
        target_encumbered = compute_asset_control_target(
            _clean_target_inp(royalty_cleanliness=0.30, milestone_burden=0.30)
        )
        r_clean = compute_pair_asset_control(
            PairAssetControlInput(acquirer_id="A", target_id="T",
                                  target_asset_control=target_clean)
        )
        r_enc = compute_pair_asset_control(
            PairAssetControlInput(acquirer_id="A", target_id="T",
                                  target_asset_control=target_encumbered)
        )
        # With no pair-specific signals, both pairs have multiplier=1.0
        assert r_clean.pair_multiplier == pytest.approx(1.0)
        assert r_enc.pair_multiplier == pytest.approx(1.0)

    def test_target_encumbrance_not_double_penalised_through_pair(self):
        """If a target has heavy royalties (already penalised in 0D-T),
        the pair result should not also apply a royalty penalty."""
        target = compute_asset_control_target(
            _clean_target_inp(royalty_cleanliness=0.20)  # penalised in 0D-T
        )
        assert target.penalty_multiplier < 1.0  # confirm 0D-T penalised it

        r = compute_pair_asset_control(
            PairAssetControlInput(acquirer_id="A", target_id="T",
                                  target_asset_control=target)
        )
        # Pair should not add further royalty penalty
        assert r.pair_multiplier == pytest.approx(1.0)
        assert "royalty" not in " ".join(r.rationale)

    def test_no_partner_bonus_in_target_result_codes(self):
        """Double-count guard: if target result somehow contained a pair code,
        _assert_no_pair_contamination should raise."""
        # Manually construct a contaminated target result by injecting a pair code
        clean = compute_asset_control_target(_clean_target_inp())
        # Patch triggered_encumbrances with a pair-only code
        contaminated = clean.model_copy(update={
            "triggered_encumbrances": list(clean.triggered_encumbrances) +
                                      ["partner_freedom:existing_partner_bonus_applied"]
        })
        with pytest.raises(ValueError, match="pair-specific encumbrance codes"):
            _assert_no_pair_contamination(contaminated)

    def test_pair_only_codes_set_is_non_empty(self):
        """Verify the guard set is populated."""
        assert len(_PAIR_ONLY_ENCUMBRANCE_CODES) >= 4


# ---------------------------------------------------------------------------
# 8. Combined scenarios
# ---------------------------------------------------------------------------

class TestCombinedScenarios:

    def test_rofr_plus_mfg_mismatch_compounds(self):
        """ROFR blocking (≤0.65) + high complexity/low fit (≤0.75) → tightest wins."""
        r = compute_pair_asset_control(
            _pair(
                target_complexity="high",
                rofr_blocks_this_acquirer=True,
                acquirer_manufacturing_fit=0.30,
            )
        )
        # ROFR cap is tighter (0.65 < 0.75)
        assert r.pair_multiplier <= 0.65
        assert r.pair_cap is not None
        assert r.pair_cap <= 0.55  # ROFR cap (0.55) tighter than mfg cap (0.65)

    def test_existing_partner_bypasses_rofr_not_mfg(self):
        """Existing partner waives ROFR but manufacturing mismatch still applies."""
        r = compute_pair_asset_control(
            _pair(
                target_complexity="high",
                target_has_rofr=True,       # ROFR must exist on target for waiver to fire
                acquirer_is_existing_partner=True,
                rofr_blocks_this_acquirer=True,
                acquirer_manufacturing_fit=0.30,
            )
        )
        assert r.rofr_impact == "waived_partner"
        # Manufacturing mismatch still applies
        assert r.pair_multiplier <= 0.75
        assert r.manufacturing_mismatch_flag is True

    def test_geo_mismatch_plus_consent_required(self):
        r = compute_pair_asset_control(
            _pair(
                acquirer_target_geography_overlap=0.30,  # severe geo
                consent_required_for_this_coc=True,
            )
        )
        # Severe geo: mult ≤ 0.75, cap ≤ 0.65
        # Consent: mult ≤ 0.70
        # min(0.75, 0.70) = 0.70
        assert r.pair_multiplier <= 0.70
        assert r.pair_cap is not None
        assert r.pair_cap <= 0.65

    def test_all_issues_clean_pair_multiplier_one(self):
        """Completely clean pair — no adjustments whatsoever."""
        r = compute_pair_asset_control(
            _pair(
                target_complexity="low",
                acquirer_manufacturing_fit=0.85,
                acquirer_target_geography_overlap=1.0,
                acquirer_is_existing_partner=False,
                rofr_blocks_this_acquirer=False,
                consent_required_for_this_coc=False,
                exclusivity_conflict_for_this_acquirer=False,
            )
        )
        assert r.pair_multiplier == pytest.approx(1.0)
        assert r.pair_cap is None
        assert r.pair_level_fail is False
        assert r.manufacturing_mismatch_flag is False
        assert r.partner_bonus_applied is False


# ---------------------------------------------------------------------------
# 9. Pair scope and result fields
# ---------------------------------------------------------------------------

class TestPairScopeAndFields:

    def test_is_pair_scope_true(self):
        r = compute_pair_asset_control(_pair())
        assert r.is_pair_scope is True

    def test_acquirer_id_propagated(self):
        r = compute_pair_asset_control(_pair(acquirer_id="PFE"))
        assert r.acquirer_id == "PFE"

    def test_target_id_propagated(self):
        r = compute_pair_asset_control(_pair(target_id="KARUNA"))
        assert r.target_id == "KARUNA"

    def test_result_is_frozen(self):
        r = compute_pair_asset_control(_pair())
        with pytest.raises(Exception):
            r.pair_multiplier = 0.5  # type: ignore[misc]

    def test_pair_level_fail_false_for_clean_pair(self):
        r = compute_pair_asset_control(_pair())
        assert r.pair_level_fail is False

    def test_pair_asset_control_score_is_float_in_range(self):
        r = compute_pair_asset_control(_pair())
        assert 0.0 <= r.pair_asset_control_score <= 1.0

    def test_pair_asset_control_score_respects_cap(self):
        """Score must not exceed pair_cap when cap is set."""
        r = compute_pair_asset_control(
            _pair(rofr_blocks_this_acquirer=True)  # cap ≤ 0.55
        )
        if r.pair_cap is not None:
            assert r.pair_asset_control_score <= r.pair_cap + 1e-6

    def test_manufacturing_fit_on_result(self):
        r = compute_pair_asset_control(
            _pair(acquirer_manufacturing_fit=0.65)
        )
        assert r.acquirer_manufacturing_fit == pytest.approx(0.65)

    def test_rationale_non_empty_when_issues_present(self):
        r = compute_pair_asset_control(
            _pair(rofr_blocks_this_acquirer=True)
        )
        assert len(r.rationale) > 0

    def test_rationale_empty_for_clean_pair(self):
        """No rationale entries when no pair-specific issues."""
        r = compute_pair_asset_control(_pair())
        assert r.rationale == []

    def test_result_is_pairassetcontrolresult_instance(self):
        r = compute_pair_asset_control(_pair())
        assert isinstance(r, PairAssetControlResult)


# ---------------------------------------------------------------------------
# 10. Double-count guard enforcement
# ---------------------------------------------------------------------------

class TestDoubleCountGuard:

    def test_clean_target_passes_guard(self):
        """Clean target result passes _assert_no_pair_contamination without error."""
        target = compute_asset_control_target(_clean_target_inp())
        _assert_no_pair_contamination(target)  # must not raise

    def test_contaminated_target_raises_valueerror(self):
        target = compute_asset_control_target(_clean_target_inp())
        bad = target.model_copy(update={
            "triggered_encumbrances": ["manufacturing_control:acquirer_strong_capability"]
        })
        with pytest.raises(ValueError):
            _assert_no_pair_contamination(bad)

    def test_compute_pair_raises_on_contaminated_target(self):
        target = compute_asset_control_target(_clean_target_inp())
        bad = target.model_copy(update={
            "triggered_encumbrances": ["partner_freedom:ROFR_or_opt_in_blocks_this_acquirer"]
        })
        with pytest.raises(ValueError):
            compute_pair_asset_control(
                PairAssetControlInput(
                    acquirer_id="A", target_id="T", target_asset_control=bad
                )
            )
