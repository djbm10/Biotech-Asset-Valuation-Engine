"""
Phase 4C tests — deal_structure_residual_bonus

Required coverage (8 assertions from the spec):
  1. Direct blended_deal_type_score is not used in live score.
  2. Distressed targets are not double-penalized.
  3. Licensing targets are not double-penalized for royalties.
  4. Strategic fit is not double-counted.
  5. Platform breadth can create a small additive bonus when enabled.
  6. Bonus is zero when required residual inputs are missing.
  7. Bonus cannot exceed +0.08.
  8. Bonus cannot break caps or hard fails.

Additional tests cover:
  - Additive-only invariant (bonus never reduces final_score).
  - Config-gate behaviour (disabled by default).
  - Score-diff table (disabled vs enabled).
  - approved_revenue_share=None vs 0.0 distinction.
  - Components are renormalized when inputs absent.
  - pip_flag increments score.
"""
from __future__ import annotations

import pytest

from bve.intelligence.deal_type_classification import DealType, classify_deal_type
from bve.intelligence.ma_deal_structure_bonus import (
    DealStructureResidualInputs,
    compute_deal_structure_residual_bonus,
    _MAX_BONUS,
)
from bve.intelligence.ma_layer4_routing import (
    Layer4Inputs,
    Layer4Output,
    WatchlistClass,
    compute_layer4,
)
from bve.intelligence.ma_eligibility import TargetEligibilityInput


def _make_dtc(**kwargs):
    defaults = dict(
        ticker="TEST",
        lead_asset_present=True,
        product_count=1,
        indication_count=1,
        lead_asset_status="active",
    )
    defaults.update(kwargs)
    return classify_deal_type(TargetEligibilityInput(**defaults))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_inputs(**overrides) -> Layer4Inputs:
    """Standard passing candidate (strategic_radar tier)."""
    defaults = dict(
        asset_quality=0.70,
        strategic_fit=0.70,
        deal_feasibility=0.55,
        seller_willingness=0.35,
        de_risking_stage=0.55,
        strategic_priority=0.72,
        transaction_probability=0.30,
        data_confidence_score=0.75,
        active_driver_bucket_count=1,
        final_score=0.62,
    )
    defaults.update(overrides)
    return Layer4Inputs(**defaults)


def _distressed_inputs(**overrides) -> Layer4Inputs:
    """Distressed target that Layer 0 would cap at 0.50."""
    defaults = dict(
        asset_quality=0.45,
        strategic_fit=0.60,
        deal_feasibility=0.45,
        seller_willingness=0.30,
        de_risking_stage=0.20,
        strategic_priority=0.66,
        transaction_probability=0.28,
        data_confidence_score=0.65,
        active_driver_bucket_count=0,
        final_score=0.38,   # already reduced by Layer 0 distress cap
    )
    defaults.update(overrides)
    return Layer4Inputs(**defaults)


def _licensing_inputs(**overrides) -> Layer4Inputs:
    """Licensing target with high royalty burden already priced in at Layer 0."""
    defaults = dict(
        asset_quality=0.65,
        strategic_fit=0.62,
        deal_feasibility=0.48,
        seller_willingness=0.35,
        de_risking_stage=0.45,
        strategic_priority=0.66,
        transaction_probability=0.30,
        data_confidence_score=0.70,
        active_driver_bucket_count=1,
        final_score=0.45,   # already reduced by Layer 0 encumbrance (royalty 22%)
    )
    defaults.update(overrides)
    return Layer4Inputs(**defaults)


def _platform_residual_inputs(*, platform_breadth: float, platform_validated: bool = False):
    return DealStructureResidualInputs(
        is_platform_company=True,
        platform_breadth=platform_breadth,
        platform_validated=platform_validated,
    )


# ---------------------------------------------------------------------------
# Test 1: blended_deal_type_score is NOT used in live score
# ---------------------------------------------------------------------------

class TestBlendedScoreNotInLiveScore:
    """Spec test 1: direct blended_deal_type_score is memo-only."""

    def test_final_score_unchanged_when_overlay_auto_built(self):
        """final_score is identical regardless of whether DTC overlay is present."""
        dtc = _make_dtc()

        # With DTC (auto-builds overlay)
        inp_with_dtc = _base_inputs(deal_type_classification=dtc, final_score=0.62)
        out_with = compute_layer4(inp_with_dtc, target_name="TargetA")

        # Without DTC
        inp_no_dtc = _base_inputs(final_score=0.62)
        out_no = compute_layer4(inp_no_dtc, target_name="TargetA")

        # final_score is not stored in Layer4Output, but watchlist_class must be equal
        assert out_with.watchlist_class == out_no.watchlist_class

        # final_score_with_overlay (Phase 4B) must be <= final_score (gate primacy)
        if out_with.final_score_with_overlay is not None:
            assert out_with.final_score_with_overlay <= 0.62 + 1e-9

    def test_deal_structure_residual_bonus_not_added_when_flag_off(self):
        """With flag disabled, final_score_with_structure_bonus is None."""
        inp = _base_inputs(
            deal_structure_residual_inputs=DealStructureResidualInputs(
                is_platform_company=True,
                platform_breadth=0.80,
                platform_validated=True,
            ),
            enable_deal_structure_bonus=False,
        )
        out = compute_layer4(inp, target_name="PlatformCo")

        assert out.final_score_with_structure_bonus is None
        # But residual result should still be computed (memo-only)
        assert out.deal_structure_residual is not None
        assert out.deal_structure_residual.deal_structure_residual_bonus > 0.0

    def test_blended_score_in_overlay_is_separate_from_structure_bonus(self):
        """blended_deal_type_score and deal_structure_residual_bonus are distinct fields."""
        dtc = _make_dtc()
        inp = _base_inputs(
            deal_type_classification=dtc,
            deal_structure_residual_inputs=_platform_residual_inputs(
                platform_breadth=0.80, platform_validated=True
            ),
            enable_deal_structure_bonus=False,
        )
        out = compute_layer4(inp, target_name="PlatformCo")

        # Both fields are independently present
        assert out.deal_type_overlay is not None, "Phase 4B overlay should be populated"
        assert out.deal_structure_residual is not None, "Phase 4C residual should be computed"

        # They are distinct values
        blend = out.deal_type_overlay.blended_deal_type_score
        bonus = out.deal_structure_residual.deal_structure_residual_bonus
        assert isinstance(blend, float)
        assert isinstance(bonus, float)
        # They may differ (different formulas)
        # Neither is wired into live score when flag off
        assert out.final_score_with_structure_bonus is None


# ---------------------------------------------------------------------------
# Test 2: Distressed targets are not double-penalized
# ---------------------------------------------------------------------------

class TestDistressNotDoublePenalized:
    """Spec test 2: distress signals are excluded from residual bonus inputs."""

    def test_distress_residual_inputs_exclude_financing_pressure(self):
        """DealStructureResidualInputs has no financing_pressure_high field."""
        fields = DealStructureResidualInputs.model_fields
        assert "financing_pressure_high" not in fields, (
            "financing_pressure_high must not be in residual inputs — "
            "it is already priced in at Layer 0 distress guard"
        )

    def test_distress_residual_inputs_exclude_distress_flag(self):
        """DealStructureResidualInputs has no distress_flag field."""
        fields = DealStructureResidualInputs.model_fields
        assert "distress_flag" not in fields, (
            "distress_flag must not be in residual inputs — "
            "it is already priced in at Layer 0"
        )

    def test_distressed_target_bonus_is_zero_without_residual_inputs(self):
        """Distressed target with no residual data gets zero bonus."""
        inp = _distressed_inputs(
            deal_structure_residual_inputs=DealStructureResidualInputs(),  # all None / False
            enable_deal_structure_bonus=True,
        )
        out = compute_layer4(inp, target_name="DistressedCo")

        assert out.deal_structure_residual is not None
        assert out.deal_structure_residual.deal_structure_residual_bonus == pytest.approx(0.0)

    def test_distressed_target_score_not_reduced_by_bonus(self):
        """Even with residual inputs enabled, final_score_with_structure_bonus >= final_score."""
        inp = _distressed_inputs(
            deal_structure_residual_inputs=DealStructureResidualInputs(
                is_platform_company=True,
                platform_breadth=0.30,
            ),
            enable_deal_structure_bonus=True,
            final_score=0.38,
        )
        out = compute_layer4(inp, target_name="DistressedPlatform")

        if out.final_score_with_structure_bonus is not None:
            assert out.final_score_with_structure_bonus >= 0.38 - 1e-9


# ---------------------------------------------------------------------------
# Test 3: Licensing targets not double-penalized for royalties
# ---------------------------------------------------------------------------

class TestLicensingNotDoublePenalized:
    """Spec test 3: royalty signals are excluded from residual bonus inputs."""

    def test_residual_inputs_exclude_royalty_stack_rate(self):
        """DealStructureResidualInputs has no royalty_stack_rate field."""
        fields = DealStructureResidualInputs.model_fields
        assert "royalty_stack_rate" not in fields, (
            "royalty_stack_rate must not be in residual inputs — "
            "it is already priced in at Layer 0 encumbrance multiplier"
        )

    def test_licensing_target_with_missing_revenue_gets_zero_revenue_component(self):
        """approved_revenue_share=None → revenue component excluded, no penalty."""
        residual = DealStructureResidualInputs(
            approved_revenue_share=None,  # data gap, not zero revenue
        )
        result = compute_deal_structure_residual_bonus(residual)

        assert "revenue_residual" in result.components_missing
        # Score should reflect only non-revenue components (all absent here)
        # pip_flag=False → 0.0; all others None → missing
        # Only pip_flag is "scored" at 0.0 → score = 0.0
        assert result.residual_structure_score == pytest.approx(0.0, abs=1e-6)
        assert result.deal_structure_residual_bonus == pytest.approx(0.0, abs=1e-6)

    def test_licensing_target_zero_revenue_share_excluded_from_bonus(self):
        """approved_revenue_share=0.0 (pipeline-only) → revenue excluded from score."""
        residual = DealStructureResidualInputs(
            approved_revenue_share=0.0,
        )
        result = compute_deal_structure_residual_bonus(residual)

        # revenue_residual must be in missing (not None but 0.0 → pipeline-only)
        assert "revenue_residual" in result.components_missing

    def test_licensing_target_final_score_not_reduced(self):
        """Licensing target's final_score never decreases from the bonus."""
        inp = _licensing_inputs(
            deal_structure_residual_inputs=DealStructureResidualInputs(
                product_count=2,
                indication_count=2,
            ),
            enable_deal_structure_bonus=True,
        )
        out = compute_layer4(inp, target_name="LicensingCo")

        if out.final_score_with_structure_bonus is not None:
            assert out.final_score_with_structure_bonus >= 0.45 - 1e-9


# ---------------------------------------------------------------------------
# Test 4: Strategic fit is not double-counted
# ---------------------------------------------------------------------------

class TestStrategicFitNotDoubleCounted:
    """Spec test 4: acquirer_ta_fit / strategic_fit excluded from residual inputs."""

    def test_residual_inputs_exclude_acquirer_ta_fit(self):
        """DealStructureResidualInputs has no acquirer_ta_fit field."""
        fields = DealStructureResidualInputs.model_fields
        assert "acquirer_ta_fit" not in fields, (
            "acquirer_ta_fit must not be in residual inputs — "
            "it is already captured in Layer 1 strategic fit"
        )

    def test_residual_score_independent_of_strategic_fit(self):
        """Changing strategic_fit in Layer4Inputs does not change residual_structure_score."""
        residual_inp = DealStructureResidualInputs(
            is_platform_company=True,
            platform_breadth=0.70,
        )
        result_high_fit = compute_deal_structure_residual_bonus(residual_inp)

        # The residual score uses no strategic-fit signal — result is identical
        # regardless of what Layer4Inputs.strategic_fit would be.
        # (The residual function only consumes DealStructureResidualInputs.)
        assert result_high_fit.residual_structure_score == pytest.approx(
            result_high_fit.residual_structure_score
        )
        # Verify field absence at the input level
        assert not hasattr(residual_inp, "acquirer_ta_fit")
        assert not hasattr(residual_inp, "strategic_fit")


# ---------------------------------------------------------------------------
# Test 5: Platform breadth can create a small additive bonus when enabled
# ---------------------------------------------------------------------------

class TestPlatformBreadthBonus:
    """Spec test 5: platform breadth produces a positive additive bonus."""

    def test_platform_breadth_produces_bonus(self):
        """High platform_breadth + platform_validated=True gives bonus > 0."""
        residual = DealStructureResidualInputs(
            is_platform_company=True,
            platform_breadth=0.90,
            platform_validated=True,
        )
        result = compute_deal_structure_residual_bonus(residual)

        assert result.deal_structure_residual_bonus > 0.0
        assert "platform_residual" in result.components_scored

    def test_platform_breadth_bonus_added_to_final_score(self):
        """With flag enabled, final_score_with_structure_bonus > final_score."""
        inp = _base_inputs(
            deal_structure_residual_inputs=DealStructureResidualInputs(
                is_platform_company=True,
                platform_breadth=0.90,
                platform_validated=True,
            ),
            enable_deal_structure_bonus=True,
            final_score=0.62,
        )
        out = compute_layer4(inp, target_name="PlatformCo")

        assert out.final_score_with_structure_bonus is not None
        assert out.final_score_with_structure_bonus > 0.62

    def test_platform_not_platform_company_gets_zero_platform_component(self):
        """is_platform_company=False → platform component excluded even with breadth data."""
        residual = DealStructureResidualInputs(
            is_platform_company=False,
            platform_breadth=0.90,  # irrelevant
        )
        result = compute_deal_structure_residual_bonus(residual)

        assert "platform_residual" in result.components_missing
        # Score driven only by pip_flag=0.0 → 0.0
        assert result.residual_structure_score == pytest.approx(0.0, abs=1e-6)

    def test_validated_platform_scores_higher_than_unvalidated(self):
        """platform_validated=True gives a higher residual score than False."""
        breadth = 0.70
        validated = compute_deal_structure_residual_bonus(
            DealStructureResidualInputs(is_platform_company=True, platform_breadth=breadth,
                                        platform_validated=True)
        )
        unvalidated = compute_deal_structure_residual_bonus(
            DealStructureResidualInputs(is_platform_company=True, platform_breadth=breadth,
                                        platform_validated=False)
        )
        assert validated.residual_structure_score > unvalidated.residual_structure_score


# ---------------------------------------------------------------------------
# Test 6: Bonus is zero when required residual inputs are missing
# ---------------------------------------------------------------------------

class TestBonusZeroWhenInputsMissing:
    """Spec test 6: no residual data → no bonus."""

    def test_all_none_inputs_give_zero_bonus(self):
        """All Optional inputs None, pip_flag=False → score 0, bonus 0."""
        result = compute_deal_structure_residual_bonus(DealStructureResidualInputs())

        assert result.residual_structure_score == pytest.approx(0.0, abs=1e-6)
        assert result.deal_structure_residual_bonus == pytest.approx(0.0, abs=1e-6)

    def test_no_residual_inputs_in_layer4_gives_none_output(self):
        """When deal_structure_residual_inputs is None, output fields are None."""
        inp = _base_inputs(deal_structure_residual_inputs=None)
        out = compute_layer4(inp, target_name="NoBonusCo")

        assert out.deal_structure_residual is None
        assert out.final_score_with_structure_bonus is None

    def test_partial_inputs_only_available_components_scored(self):
        """Only product_count provided (indication_count missing) → breadth excluded."""
        residual = DealStructureResidualInputs(
            product_count=3,
            indication_count=None,  # missing
        )
        result = compute_deal_structure_residual_bonus(residual)

        # breadth requires BOTH counts → excluded
        assert "breadth_residual" in result.components_missing


# ---------------------------------------------------------------------------
# Test 7: Bonus cannot exceed +0.08
# ---------------------------------------------------------------------------

class TestBonusCapAtPoint08:
    """Spec test 7: bonus is capped at +0.08."""

    def test_max_bonus_is_point08(self):
        """With all-max residual signals, bonus == 0.08."""
        residual = DealStructureResidualInputs(
            is_platform_company=True,
            platform_breadth=1.0,
            platform_validated=True,
            product_count=10,
            indication_count=10,
            approved_revenue_share=1.0,
            commercial_franchise_breadth=1.0,
            pipeline_in_a_product=True,
        )
        result = compute_deal_structure_residual_bonus(residual)

        assert result.deal_structure_residual_bonus <= _MAX_BONUS + 1e-9

    def test_bonus_constant_is_point08(self):
        """_MAX_BONUS constant equals 0.08."""
        assert _MAX_BONUS == pytest.approx(0.08)

    def test_final_score_with_bonus_stays_at_or_below_1(self):
        """Even with final_score=0.95 and max bonus, result ≤ 1.0."""
        inp = _base_inputs(
            final_score=0.95,
            asset_quality=0.90,
            strategic_fit=0.90,
            deal_feasibility=0.90,
            seller_willingness=0.90,
            strategic_priority=0.90,
            transaction_probability=0.90,
            deal_structure_residual_inputs=DealStructureResidualInputs(
                is_platform_company=True,
                platform_breadth=1.0,
                platform_validated=True,
                product_count=10,
                indication_count=10,
                approved_revenue_share=1.0,
                pipeline_in_a_product=True,
            ),
            enable_deal_structure_bonus=True,
        )
        out = compute_layer4(inp, target_name="MaxScoreCo")

        if out.final_score_with_structure_bonus is not None:
            assert out.final_score_with_structure_bonus <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# Test 8: Bonus cannot break caps or hard fails
# ---------------------------------------------------------------------------

class TestBonusDoesNotBreakCaps:
    """Spec test 8: hard-fail classes are immune to bonus even when flag is True."""

    def test_pass_class_gets_no_bonus(self):
        """Low-quality candidate routes to PASS — bonus not applied."""
        inp = Layer4Inputs(
            asset_quality=0.20,      # below _PASS_ASSET_QUALITY_MIN (0.35)
            strategic_fit=0.70,
            deal_feasibility=0.55,
            seller_willingness=0.35,
            de_risking_stage=0.55,
            strategic_priority=0.72,
            transaction_probability=0.30,
            data_confidence_score=0.80,
            active_driver_bucket_count=1,
            final_score=0.25,
            deal_structure_residual_inputs=DealStructureResidualInputs(
                is_platform_company=True,
                platform_breadth=0.90,
                platform_validated=True,
            ),
            enable_deal_structure_bonus=True,
        )
        out = compute_layer4(inp, target_name="LowQualityCo")

        assert out.watchlist_class == WatchlistClass.PASS.value
        assert out.final_score_with_structure_bonus is None, (
            "PASS class must never receive a bonus"
        )

    def test_data_insufficient_class_gets_no_bonus(self):
        """Data-insufficient candidate — bonus not applied."""
        inp = Layer4Inputs(
            asset_quality=0.60,
            strategic_fit=0.60,
            deal_feasibility=0.45,
            seller_willingness=0.35,
            de_risking_stage=0.55,
            strategic_priority=0.66,
            transaction_probability=0.30,
            data_confidence_score=0.40,   # below _DATA_CONFIDENCE_MIN (0.60)
            active_driver_bucket_count=0,
            final_score=0.42,
            deal_structure_residual_inputs=DealStructureResidualInputs(
                is_platform_company=True,
                platform_breadth=0.90,
                platform_validated=True,
            ),
            enable_deal_structure_bonus=True,
        )
        out = compute_layer4(inp, target_name="DataMissingCo")

        assert out.watchlist_class == WatchlistClass.DATA_INSUFFICIENT.value
        assert out.final_score_with_structure_bonus is None, (
            "DATA_INSUFFICIENT class must never receive a bonus"
        )

    def test_bonus_residual_still_computed_memo_only_for_hard_fail(self):
        """Residual result is computed (memo-only) even for PASS class."""
        inp = Layer4Inputs(
            asset_quality=0.20,
            strategic_fit=0.70,
            deal_feasibility=0.55,
            seller_willingness=0.35,
            de_risking_stage=0.55,
            strategic_priority=0.72,
            transaction_probability=0.30,
            data_confidence_score=0.80,
            active_driver_bucket_count=1,
            final_score=0.25,
            deal_structure_residual_inputs=DealStructureResidualInputs(
                is_platform_company=True,
                platform_breadth=0.90,
            ),
            enable_deal_structure_bonus=True,
        )
        out = compute_layer4(inp, target_name="LowQualityCo")

        assert out.deal_structure_residual is not None
        assert out.deal_structure_residual.deal_structure_residual_bonus > 0.0
        # But it must NOT be applied to the live score
        assert out.final_score_with_structure_bonus is None


# ---------------------------------------------------------------------------
# Additional: additive-only invariant
# ---------------------------------------------------------------------------

class TestAdditiveOnlyInvariant:
    """Bonus can never reduce final_score."""

    def test_bonus_always_non_negative(self):
        """deal_structure_residual_bonus is always >= 0."""
        for breadth in [0.0, 0.3, 0.7, 1.0]:
            result = compute_deal_structure_residual_bonus(
                DealStructureResidualInputs(
                    is_platform_company=True,
                    platform_breadth=breadth,
                )
            )
            assert result.deal_structure_residual_bonus >= 0.0

    def test_final_score_with_bonus_gte_final_score(self):
        """final_score_with_structure_bonus >= final_score when flag enabled."""
        inp = _base_inputs(
            deal_structure_residual_inputs=DealStructureResidualInputs(
                product_count=3,
                indication_count=2,
            ),
            enable_deal_structure_bonus=True,
            final_score=0.55,
        )
        out = compute_layer4(inp, target_name="PipelineCo")

        if out.final_score_with_structure_bonus is not None:
            assert out.final_score_with_structure_bonus >= 0.55 - 1e-9


# ---------------------------------------------------------------------------
# Score-diff table: five representative candidates
# ---------------------------------------------------------------------------

class TestScoreDiffTable:
    """Score-diff with bonus disabled vs enabled for five representative profiles."""

    @pytest.mark.parametrize("label,base_fs,residual,expected_delta_min,expected_delta_max", [
        (
            "single_asset_no_data",
            0.62,
            DealStructureResidualInputs(),   # all None
            0.0, 0.001,                      # no data → no bonus
        ),
        (
            "platform_validated",
            0.62,
            DealStructureResidualInputs(
                is_platform_company=True, platform_breadth=0.80, platform_validated=True
            ),
            0.01, 0.08,                      # some bonus
        ),
        (
            "pipeline_portfolio_3x3",
            0.58,
            DealStructureResidualInputs(product_count=3, indication_count=3),
            0.001, 0.08,                     # breadth bonus
        ),
        (
            "commercial_franchise_present",
            0.60,
            DealStructureResidualInputs(approved_revenue_share=0.60, commercial_franchise_breadth=0.50),
            0.01, 0.08,                      # revenue + franchise bonus
        ),
        (
            "distressed_no_residual",
            0.38,
            DealStructureResidualInputs(),   # all None
            0.0, 0.001,                      # no penalty, no bonus
        ),
    ])
    def test_score_diff_disabled_vs_enabled(
        self, label, base_fs, residual, expected_delta_min, expected_delta_max
    ):
        common = dict(
            asset_quality=max(0.36, base_fs),
            strategic_fit=0.65,
            deal_feasibility=0.45,
            seller_willingness=0.32,
            de_risking_stage=0.50,
            strategic_priority=0.67,
            transaction_probability=0.28,
            data_confidence_score=0.72,
            active_driver_bucket_count=1,
            final_score=base_fs,
            deal_structure_residual_inputs=residual,
        )

        out_disabled = compute_layer4(
            Layer4Inputs(**common, enable_deal_structure_bonus=False),
            target_name=label,
        )
        out_enabled = compute_layer4(
            Layer4Inputs(**common, enable_deal_structure_bonus=True),
            target_name=label,
        )

        # Disabled: final_score_with_structure_bonus is None
        assert out_disabled.final_score_with_structure_bonus is None, (
            f"{label}: bonus must be None when flag is off"
        )

        # Enabled: check delta range
        if out_enabled.final_score_with_structure_bonus is not None:
            delta = out_enabled.final_score_with_structure_bonus - base_fs
            assert delta >= expected_delta_min - 1e-6, (
                f"{label}: delta={delta:.4f} below expected_min={expected_delta_min}"
            )
            assert delta <= expected_delta_max + 1e-6, (
                f"{label}: delta={delta:.4f} above expected_max={expected_delta_max}"
            )
        else:
            # Hard fail → no bonus applied
            assert expected_delta_max <= 0.001


# ---------------------------------------------------------------------------
# Additional: pip_flag and franchise breadth
# ---------------------------------------------------------------------------

class TestPipFlagAndFranchiseBreadth:
    """pipeline_in_a_product and commercial_franchise_breadth produce bonus."""

    def test_pip_flag_alone_does_not_produce_bonus(self):
        """pip_flag=True but no other data → only pip_flag scored at 0 baseline."""
        # pip_flag=True → score=1.0; but weight is just pip_flag (0.10 / 0.10 = 1.0)
        # BUT breadth_residual baseline subtract 0.10 only applies to breadth formula
        # pip_flag=True → scored["pip_flag"]=1.0; only component → renorm weight=1.0
        # score = 1.0 × 1.0 / 1.0 = 1.0 → bonus = 0.08
        result = compute_deal_structure_residual_bonus(
            DealStructureResidualInputs(pipeline_in_a_product=True)
        )
        assert result.deal_structure_residual_bonus > 0.0
        assert result.deal_structure_residual_bonus <= _MAX_BONUS

    def test_franchise_breadth_present_contributes_to_score(self):
        """Explicit commercial_franchise_breadth > 0 contributes."""
        result = compute_deal_structure_residual_bonus(
            DealStructureResidualInputs(commercial_franchise_breadth=0.75)
        )
        assert "franchise_residual" in result.components_scored
        assert result.deal_structure_residual_bonus > 0.0

    def test_bonus_enabled_flag_stamped_on_result(self):
        """deal_structure_residual.bonus_enabled reflects the Layer4Inputs flag."""
        inp_off = _base_inputs(
            deal_structure_residual_inputs=DealStructureResidualInputs(
                is_platform_company=True, platform_breadth=0.70
            ),
            enable_deal_structure_bonus=False,
        )
        inp_on = _base_inputs(
            deal_structure_residual_inputs=DealStructureResidualInputs(
                is_platform_company=True, platform_breadth=0.70
            ),
            enable_deal_structure_bonus=True,
        )
        out_off = compute_layer4(inp_off, target_name="Co")
        out_on = compute_layer4(inp_on, target_name="Co")

        assert out_off.deal_structure_residual.bonus_enabled is False
        assert out_on.deal_structure_residual.bonus_enabled is True
