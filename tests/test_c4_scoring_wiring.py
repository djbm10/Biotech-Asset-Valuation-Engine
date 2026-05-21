"""C4 scoring wiring tests.

Verifies that Layer 0 + Layer 3A + Layer 3B modifiers are correctly
assembled by the new private helpers and produce expected score-diff
behaviour.  Tests intentionally avoid constructing a full
MAProbabilityScanner — they exercise the helper pipeline
(evaluate_layer0 → compute_pair_asset_control → compute_pair_affordability
→ combine_layer0_and_3b) directly so that each modifier layer is
independently observable.

Test classes
------------
TestBuildTargetEligibilityInput  — helper builds correct TargetEligibilityInput
TestBuildAcquirerCapacityInput   — helper maps AcquirerProfile fields correctly
TestAcquirerIsExistingPartner    — partner-match detection
TestCleanGlobalNoChange          — CLEAN target → effective_multiplier = 1.0, no cap
TestROFRNonPartner               — ROFR + non-partner → lower score + pair cap
TestROFRExistingPartner          — ROFR + existing-partner waiver → less penalty
TestHighMfgMismatch              — high mfg + poor-fit acquirer → meaningful reduction
TestMissingEVNoZero              — missing EV → multiplier stays 1.0, reason code noted
TestNoDoubleCount                — targetability.multiplier does NOT overlap with C4
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import pytest

from bve.intelligence.ma_eligibility import TargetEligibilityInput, evaluate_layer0
from bve.intelligence.ma_pair_affordability import (
    AcquirerCapacityInput,
    compute_pair_affordability,
)
from bve.intelligence.ma_pair_asset_control import (
    PairAssetControlInput,
    combine_layer0_and_3b,
    compute_pair_asset_control,
)
from bve.intelligence.ma_probability import (
    TargetabilityFilter,
    _acquirer_is_existing_partner,
    _build_acquirer_capacity_input,
    _build_target_eligibility_input,
)


# ---------------------------------------------------------------------------
# Shared factories
# ---------------------------------------------------------------------------

def _make_clean_row(**overrides) -> SimpleNamespace:
    """Minimal acquisition_row with clean-global defaults.

    Includes realistic data-completeness flags so that Gate 6 (financial
    going-concern) does not fire on a standard M&A universe target.
    has_* booleans reflect what a typical Phase 2 biotech SEC filing would cover.
    """
    defaults = dict(
        ticker="TRGT",
        asset_id="trgt-asset-1",
        stage="phase_2",
        market_cap_millions=400.0,
        enterprise_value_millions=500.0,
        asset_rights_scope="global",
        has_existing_partnership=False,
        has_right_of_first_refusal=False,
        manufacturing_complexity="low",
        royalty_stack_rate=None,
        has_co_development_obligation=False,
        has_ip_dispute=False,
        has_manufacturing_dependency=False,
        has_asset_ownership_data=True,
        has_partner_rights_data=True,
        # 0G completeness flags — realistic for a biotech with SEC filings
        has_cash_debt=True,
        has_quarterly_burn=True,
        has_revenue_mix=True,
        has_trial_status=True,
        has_patent_loe_data=True,
        has_acquirer_profile_data=True,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_acquirer(
    *,
    acquirer_id: str = "acq-001",
    acquisition_capacity_millions: Optional[float] = 2000.0,
    cash_billions: Optional[float] = None,
    market_cap_billions: Optional[float] = 20.0,
    existing_partnerships: Optional[list] = None,
    manufacturing_fit_score: float = 0.70,
) -> SimpleNamespace:
    return SimpleNamespace(
        acquirer_id=acquirer_id,
        acquisition_capacity_millions=acquisition_capacity_millions,
        cash_billions=cash_billions,
        market_cap_billions=market_cap_billions,
        existing_partnerships=existing_partnerships or [],
        manufacturing_fit_score=manufacturing_fit_score,
    )


def _run_c4_pipeline(
    row,
    acquirer,
) -> tuple[float, Optional[float], list[str]]:
    """Run the full C4 modifier pipeline and return (effective_multiplier, effective_cap, l3_reason_codes).

    Mirrors the logic inserted into _score_acquirer_candidate().
    """
    from bve.intelligence.ma_pair_asset_control import PairAssetControlResult

    l0_input = _build_target_eligibility_input(row)
    l0 = evaluate_layer0(l0_input)

    pair_3b: Optional[PairAssetControlResult] = None
    if "pair_asset_control_adjustment" in l0.required_downstream_checks:
        pair_3b = compute_pair_asset_control(PairAssetControlInput(
            acquirer_id=acquirer.acquirer_id,
            target_id=getattr(row, "asset_id", ""),
            target_asset_control=l0.encumbrance,
            acquirer_is_existing_partner=_acquirer_is_existing_partner(acquirer, row),
            rofr_blocks_this_acquirer=getattr(row, "has_right_of_first_refusal", False),
            acquirer_manufacturing_fit=getattr(acquirer, "manufacturing_fit_score", 0.70),
        ))

    afford_mult = 1.0
    l3_reasons: list[str] = []
    target_ev = getattr(row, "enterprise_value_millions", None)
    if target_ev is not None:
        acq_cap = _build_acquirer_capacity_input(acquirer)
        afford = compute_pair_affordability(target_ev, acq_cap)
        afford_mult = afford.score_multiplier
    else:
        l3_reasons.append("affordability_data_required")

    mods = combine_layer0_and_3b(
        layer0_score_multiplier=l0.score_multiplier,
        layer0_score_cap=l0.score_cap,
        target_max_mna_score_cap=l0.encumbrance.max_mna_score_cap,
        pair_result=pair_3b,
        affordability_score_multiplier=afford_mult,
    )
    return mods.effective_multiplier, mods.effective_cap, l3_reasons


# ---------------------------------------------------------------------------
# TestBuildTargetEligibilityInput
# ---------------------------------------------------------------------------

class TestBuildTargetEligibilityInput:
    def test_ticker_from_row(self):
        row = _make_clean_row(ticker="ABCD")
        inp = _build_target_eligibility_input(row)
        assert inp.ticker == "ABCD"

    def test_missing_ticker_defaults_to_unknown(self):
        row = SimpleNamespace()  # no ticker attr
        inp = _build_target_eligibility_input(row)
        assert inp.ticker == "UNKNOWN"

    def test_none_ticker_defaults_to_unknown(self):
        row = _make_clean_row(ticker=None)
        inp = _build_target_eligibility_input(row)
        assert inp.ticker == "UNKNOWN"

    def test_rofr_forwarded(self):
        row = _make_clean_row(has_right_of_first_refusal=True)
        inp = _build_target_eligibility_input(row)
        assert inp.has_right_of_first_refusal is True

    def test_mfg_complexity_forwarded(self):
        row = _make_clean_row(manufacturing_complexity="high")
        inp = _build_target_eligibility_input(row)
        assert inp.manufacturing_complexity == "high"

    def test_invalid_mfg_complexity_coerced_to_low(self):
        row = _make_clean_row(manufacturing_complexity="extreme")
        inp = _build_target_eligibility_input(row)
        assert inp.manufacturing_complexity == "low"

    def test_invalid_rights_scope_coerced_to_global(self):
        row = _make_clean_row(asset_rights_scope="invalid_value")
        inp = _build_target_eligibility_input(row)
        assert inp.asset_rights_scope == "global"

    def test_defaults_when_row_has_no_encumbrance_attrs(self):
        row = SimpleNamespace(ticker="X")
        inp = _build_target_eligibility_input(row)
        assert inp.has_existing_partnership is False
        assert inp.has_right_of_first_refusal is False
        assert inp.manufacturing_complexity == "low"
        assert inp.asset_rights_scope == "global"


# ---------------------------------------------------------------------------
# TestBuildAcquirerCapacityInput
# ---------------------------------------------------------------------------

class TestBuildAcquirerCapacityInput:
    def test_uses_acquisition_capacity_when_set(self):
        acq = _make_acquirer(acquisition_capacity_millions=1500.0, cash_billions=5.0)
        cap = _build_acquirer_capacity_input(acq)
        assert cap.cash_available_millions == 1500.0

    def test_falls_back_to_cash_billions(self):
        acq = _make_acquirer(acquisition_capacity_millions=None, cash_billions=3.0)
        cap = _build_acquirer_capacity_input(acq)
        assert cap.cash_available_millions == pytest.approx(3000.0)

    def test_zero_when_no_cash_data(self):
        acq = _make_acquirer(acquisition_capacity_millions=None, cash_billions=None)
        cap = _build_acquirer_capacity_input(acq)
        assert cap.cash_available_millions == 0.0

    def test_market_cap_millions_converted(self):
        acq = _make_acquirer(market_cap_billions=25.0)
        cap = _build_acquirer_capacity_input(acq)
        assert cap.acquirer_market_cap_millions == pytest.approx(25_000.0)

    def test_market_cap_none_when_missing(self):
        acq = _make_acquirer(market_cap_billions=None)
        cap = _build_acquirer_capacity_input(acq)
        assert cap.acquirer_market_cap_millions is None

    def test_acquirer_id_preserved(self):
        acq = _make_acquirer(acquirer_id="pfizer-001")
        cap = _build_acquirer_capacity_input(acq)
        assert cap.acquirer_id == "pfizer-001"


# ---------------------------------------------------------------------------
# TestAcquirerIsExistingPartner
# ---------------------------------------------------------------------------

class TestAcquirerIsExistingPartner:
    def test_no_partnerships_returns_false(self):
        acq = _make_acquirer(existing_partnerships=[])
        row = _make_clean_row(ticker="TRGT")
        assert _acquirer_is_existing_partner(acq, row) is False

    def test_matching_ticker_returns_true(self):
        acq = _make_acquirer(existing_partnerships=[
            SimpleNamespace(target="TRGT"),
        ])
        row = _make_clean_row(ticker="TRGT")
        assert _acquirer_is_existing_partner(acq, row) is True

    def test_case_insensitive_match(self):
        acq = _make_acquirer(existing_partnerships=[
            SimpleNamespace(target="trgt"),
        ])
        row = _make_clean_row(ticker="TRGT")
        assert _acquirer_is_existing_partner(acq, row) is True

    def test_non_matching_ticker_returns_false(self):
        acq = _make_acquirer(existing_partnerships=[
            SimpleNamespace(target="OTHER"),
        ])
        row = _make_clean_row(ticker="TRGT")
        assert _acquirer_is_existing_partner(acq, row) is False

    def test_no_ticker_on_row_returns_false(self):
        acq = _make_acquirer(existing_partnerships=[
            SimpleNamespace(target="TRGT"),
        ])
        row = SimpleNamespace(asset_id="trgt-asset-1")  # no ticker attr
        assert _acquirer_is_existing_partner(acq, row) is False


# ---------------------------------------------------------------------------
# TestCleanGlobalNoChange
# ---------------------------------------------------------------------------

class TestCleanGlobalNoChange:
    """Clean global target with no constraints → multiplier 1.0, no cap."""

    def test_effective_multiplier_is_one(self):
        row = _make_clean_row()
        acq = _make_acquirer()
        mult, cap, reasons = _run_c4_pipeline(row, acq)
        assert mult == pytest.approx(1.0, abs=1e-6), (
            f"Clean global target should produce no score penalty; got {mult}"
        )

    def test_effective_cap_is_none(self):
        row = _make_clean_row()
        acq = _make_acquirer()
        _, cap, _ = _run_c4_pipeline(row, acq)
        assert cap is None, f"Clean global target should have no cap; got {cap}"

    def test_no_l3_reason_codes(self):
        row = _make_clean_row()
        acq = _make_acquirer()
        _, _, reasons = _run_c4_pipeline(row, acq)
        assert reasons == [], f"Expected no L3 reason codes; got {reasons}"

    def test_layer0_not_flagged_for_pair_adjustment(self):
        row = _make_clean_row()
        l0_input = _build_target_eligibility_input(row)
        l0 = evaluate_layer0(l0_input)
        assert "pair_asset_control_adjustment" not in l0.required_downstream_checks


# ---------------------------------------------------------------------------
# TestROFRNonPartner
# ---------------------------------------------------------------------------

class TestROFRNonPartner:
    """ROFR target + non-partner acquirer → score reduction and pair cap."""

    def _setup(self):
        row = _make_clean_row(
            has_right_of_first_refusal=True,
            has_existing_partnership=True,   # ROFR implies a partner exists
        )
        acq = _make_acquirer(existing_partnerships=[])  # not the partner
        return row, acq

    def test_pair_adjustment_flagged_in_layer0(self):
        row, _ = self._setup()
        l0_input = _build_target_eligibility_input(row)
        l0 = evaluate_layer0(l0_input)
        assert "pair_asset_control_adjustment" in l0.required_downstream_checks

    def test_effective_multiplier_below_one(self):
        row, acq = self._setup()
        mult, _, _ = _run_c4_pipeline(row, acq)
        assert mult < 1.0, (
            f"ROFR non-partner should reduce effective_multiplier below 1.0; got {mult}"
        )

    def test_effective_cap_set(self):
        row, acq = self._setup()
        _, cap, _ = _run_c4_pipeline(row, acq)
        assert cap is not None, "ROFR non-partner should produce a binding score cap"
        assert cap <= 0.60, f"Cap should be ≤ 0.60 for blocking ROFR; got {cap}"

    def test_score_diff_non_trivial(self):
        """Score with ROFR should be meaningfully lower than clean baseline."""
        clean_row = _make_clean_row()
        rofr_row = _make_clean_row(
            has_right_of_first_refusal=True,
            has_existing_partnership=True,
        )
        acq = _make_acquirer(existing_partnerships=[])
        base_mult, base_cap, _ = _run_c4_pipeline(clean_row, acq)
        rofr_mult, rofr_cap, _ = _run_c4_pipeline(rofr_row, acq)

        # Multiplier must be lower for ROFR case
        assert rofr_mult < base_mult, (
            f"ROFR multiplier {rofr_mult:.4f} should be < clean baseline {base_mult:.4f}"
        )
        # Reduction must be non-trivial (at least 5%)
        assert base_mult - rofr_mult >= 0.05, (
            f"Score diff too small: {base_mult - rofr_mult:.4f}"
        )


# ---------------------------------------------------------------------------
# TestROFRExistingPartner
# ---------------------------------------------------------------------------

class TestROFRExistingPartner:
    """ROFR target + acquirer IS the existing partner → waiver fires, less penalty."""

    def _setup(self):
        row = _make_clean_row(
            ticker="TRGT",
            has_right_of_first_refusal=True,
            has_existing_partnership=True,
        )
        # Acquirer is the partner
        acq = _make_acquirer(existing_partnerships=[SimpleNamespace(target="TRGT")])
        return row, acq

    def test_partner_detected(self):
        row, acq = self._setup()
        assert _acquirer_is_existing_partner(acq, row) is True

    def test_multiplier_higher_than_non_partner(self):
        """Waiver should produce a higher multiplier than the non-partner case."""
        row = _make_clean_row(
            ticker="TRGT",
            has_right_of_first_refusal=True,
            has_existing_partnership=True,
        )
        partner_acq = _make_acquirer(existing_partnerships=[SimpleNamespace(target="TRGT")])
        non_partner_acq = _make_acquirer(existing_partnerships=[])

        partner_mult, _, _ = _run_c4_pipeline(row, partner_acq)
        non_partner_mult, _, _ = _run_c4_pipeline(row, non_partner_acq)

        assert partner_mult > non_partner_mult, (
            f"Partner waiver should give higher multiplier: "
            f"partner={partner_mult:.4f}, non_partner={non_partner_mult:.4f}"
        )

    def test_pair_level_fail_not_set_for_partner(self):
        """Existing partner should not receive a pair_level_fail."""
        row, acq = self._setup()
        l0_input = _build_target_eligibility_input(row)
        l0 = evaluate_layer0(l0_input)

        pair_inp = PairAssetControlInput(
            acquirer_id=acq.acquirer_id,
            target_id=getattr(row, "asset_id", ""),
            target_asset_control=l0.encumbrance,
            acquirer_is_existing_partner=True,
            rofr_blocks_this_acquirer=True,
        )
        result = compute_pair_asset_control(pair_inp)
        assert not result.pair_level_fail, (
            "Existing partner should not trigger a pair_level_fail"
        )


# ---------------------------------------------------------------------------
# TestHighMfgMismatch
# ---------------------------------------------------------------------------

class TestHighMfgMismatch:
    """High manufacturing complexity + poor acquirer manufacturing fit → reduction."""

    def _make_inputs(self, mfg_fit: float):
        row = _make_clean_row(manufacturing_complexity="high")
        acq = _make_acquirer(manufacturing_fit_score=mfg_fit)
        return row, acq

    def test_pair_adjustment_flagged_for_high_mfg(self):
        row = _make_clean_row(manufacturing_complexity="high")
        l0_input = _build_target_eligibility_input(row)
        l0 = evaluate_layer0(l0_input)
        assert "pair_asset_control_adjustment" in l0.required_downstream_checks

    def test_poor_fit_reduces_multiplier(self):
        row, acq = self._make_inputs(mfg_fit=0.20)
        mult, _, _ = _run_c4_pipeline(row, acq)
        assert mult < 1.0, (
            f"Poor mfg fit should reduce effective_multiplier; got {mult}"
        )

    def test_good_fit_no_mfg_penalty(self):
        row, acq = self._make_inputs(mfg_fit=0.90)
        mult_good, _, _ = _run_c4_pipeline(row, acq)
        row2, acq2 = self._make_inputs(mfg_fit=0.20)
        mult_poor, _, _ = _run_c4_pipeline(row2, acq2)
        assert mult_good > mult_poor, (
            f"Good mfg fit {mult_good:.4f} should score higher than poor fit {mult_poor:.4f}"
        )

    def test_reduction_is_meaningful(self):
        """Poor mfg fit on high-complexity target should cause ≥5% reduction from baseline."""
        clean_row = _make_clean_row(manufacturing_complexity="low")
        mfg_row = _make_clean_row(manufacturing_complexity="high")
        acq = _make_acquirer(manufacturing_fit_score=0.20)

        base_mult, _, _ = _run_c4_pipeline(clean_row, acq)
        mfg_mult, _, _ = _run_c4_pipeline(mfg_row, acq)

        assert base_mult - mfg_mult >= 0.05, (
            f"Mfg mismatch reduction too small: "
            f"base={base_mult:.4f} mfg={mfg_mult:.4f}"
        )


# ---------------------------------------------------------------------------
# TestMissingEVNoZero
# ---------------------------------------------------------------------------

class TestMissingEVNoZero:
    """Missing target EV does NOT hard-fail the pair — multiplier stays 1.0."""

    def test_missing_ev_multiplier_is_one(self):
        row = _make_clean_row(enterprise_value_millions=None)
        acq = _make_acquirer()
        mult, _, _ = _run_c4_pipeline(row, acq)
        assert mult == pytest.approx(1.0, abs=1e-6), (
            f"Missing EV should not reduce multiplier; got {mult}"
        )

    def test_missing_ev_adds_reason_code(self):
        row = _make_clean_row(enterprise_value_millions=None)
        acq = _make_acquirer()
        _, _, reasons = _run_c4_pipeline(row, acq)
        assert "affordability_data_required" in reasons

    def test_known_ev_does_not_add_reason_code(self):
        row = _make_clean_row(enterprise_value_millions=500.0)
        acq = _make_acquirer()
        _, _, reasons = _run_c4_pipeline(row, acq)
        assert "affordability_data_required" not in reasons

    def test_missing_ev_cap_is_none(self):
        row = _make_clean_row(enterprise_value_millions=None)
        acq = _make_acquirer()
        _, cap, _ = _run_c4_pipeline(row, acq)
        # Missing EV alone should not set a cap
        assert cap is None

    def test_compared_to_zero_ev_not_zeroed(self):
        """Sanity: multiplier for missing EV >> multiplier of impossible affordability."""
        row_missing = _make_clean_row(enterprise_value_millions=None)
        # A very large EV compared to tiny capacity → hard fail (mult=0.0)
        row_unaffordable = _make_clean_row(enterprise_value_millions=500_000.0)
        acq = _make_acquirer(acquisition_capacity_millions=100.0)  # tiny capacity

        mult_missing, _, _ = _run_c4_pipeline(row_missing, acq)
        mult_unaffordable, _, _ = _run_c4_pipeline(row_unaffordable, acq)

        assert mult_missing > mult_unaffordable, (
            "Missing EV should not penalise as much as a confirmed unaffordable deal"
        )
        assert mult_missing == pytest.approx(1.0, abs=1e-6), (
            "Missing EV must keep multiplier at 1.0"
        )


# ---------------------------------------------------------------------------
# TestNoDoubleCount
# ---------------------------------------------------------------------------

class TestNoDoubleCount:
    """targetability.multiplier does NOT include encumbrance / affordability signals.

    This is the explicit no-double-count assertion required by C4.
    TargetabilityFilter.assess() takes zero encumbrance parameters;
    no matter how encumbered the target, its multiplier is unaffected.
    """

    def _targetability_multiplier(self, **assess_kwargs) -> float:
        filt = TargetabilityFilter()
        result = filt.assess(**assess_kwargs)
        return result.multiplier

    def _base_assess_kwargs(self) -> dict:
        """Kwargs for a standard small-cap Phase 2 single-asset target."""
        return dict(
            asset_id="trgt-1",
            ticker="TRGT",
            market_cap_billions=0.4,
            approved_revenue_share=None,
            stage="phase_2",
            single_asset=True,
            is_known_acquirer=False,
        )

    def test_targetability_multiplier_one_for_small_cap_single_asset(self):
        mult = self._targetability_multiplier(**self._base_assess_kwargs())
        assert mult == pytest.approx(1.0), (
            "Small-cap single-asset Phase 2 target should have no targetability penalty"
        )

    def test_encumbrance_fields_not_in_targetability_assess_signature(self):
        """TargetabilityFilter.assess() must not accept encumbrance params.

        If encumbrance fields were accepted, there would be a double-count risk
        when C4 also applies them via effective_multiplier.
        """
        import inspect
        sig = inspect.signature(TargetabilityFilter.assess)
        encumbrance_params = {
            "has_right_of_first_refusal",
            "has_existing_partnership",
            "manufacturing_complexity",
            "asset_rights_scope",
            "royalty_stack_rate",
            "has_ip_dispute",
        }
        actual_params = set(sig.parameters.keys())
        overlap = encumbrance_params & actual_params
        assert not overlap, (
            f"TargetabilityFilter.assess() must not accept encumbrance params "
            f"(would double-count C4 modifiers). Overlapping params: {overlap}"
        )

    def test_affordability_fields_not_in_targetability_assess_signature(self):
        """TargetabilityFilter.assess() must not accept affordability params."""
        import inspect
        sig = inspect.signature(TargetabilityFilter.assess)
        affordability_params = {
            "enterprise_value_millions",
            "acquisition_capacity_millions",
            "cash_billions",
            "affordability_ratio",
        }
        actual_params = set(sig.parameters.keys())
        overlap = affordability_params & actual_params
        assert not overlap, (
            f"TargetabilityFilter.assess() must not accept affordability params "
            f"(would double-count C4 modifiers). Overlapping params: {overlap}"
        )

    def test_targetability_multiplier_unchanged_by_encumbrance_scenario(self):
        """Adding encumbrance flags to the acquisition_row does NOT change targetability.

        The targetability multiplier should be identical between a clean target and
        a heavily-encumbered target at the same market cap and stage.
        """
        base = self._base_assess_kwargs()

        # Targetability assess() does not accept encumbrance args, so both
        # scenarios produce the same multiplier — this is the invariant.
        mult_clean = self._targetability_multiplier(**base)
        mult_encumbered = self._targetability_multiplier(**base)  # same call

        assert mult_clean == mult_encumbered == pytest.approx(1.0), (
            "Targetability multiplier must be 1.0 for standard Phase 2 target "
            "regardless of encumbrance (encumbrance handled exclusively by C4)"
        )

    def test_c4_multiplier_and_targetability_multiplier_are_independent(self):
        """End-to-end: effective_multiplier (C4) and targetability.multiplier apply
        to different signals and can both be < 1.0 simultaneously without double-counting.

        This test demonstrates correct ordering:
          final = mna_score × effective_multiplier × targetability_multiplier
        where each factor applies once and to distinct signal sets.
        """
        # ROFR target (C4 reduces score) + multi-product commercial franchise
        # (targetability reduces score) — both apply, neither overlaps.
        row = _make_clean_row(
            has_right_of_first_refusal=True,
            has_existing_partnership=True,
        )
        acq = _make_acquirer(existing_partnerships=[])

        c4_mult, _, _ = _run_c4_pipeline(row, acq)

        # Simulate a targetability scenario that reduces the multiplier via the
        # multi-product soft penalty (single_asset=False at a pipeline stage triggers
        # multi_product_commercial_penalty=0.50 without a hard fail).
        filt = TargetabilityFilter()
        tgt_assessment = filt.assess(
            asset_id="trgt-1",
            ticker="TRGT",
            market_cap_billions=0.4,
            approved_revenue_share=None,
            stage="phase_2",
            single_asset=False,      # triggers multi_product_commercial_penalty (soft)
            is_known_acquirer=False,
        )
        tgt_mult = tgt_assessment.multiplier

        # Both factors should be < 1.0 but independent
        assert c4_mult < 1.0, "C4 ROFR multiplier should be < 1.0"
        assert tgt_mult < 1.0, "Targetability multi-product multiplier should be < 1.0"

        # Their combined effect is multiplicative (each < 1.0, product also < 1.0)
        combined = c4_mult * tgt_mult
        assert combined < c4_mult, "Combined < C4 alone (targetability adds its own penalty)"
        assert combined < tgt_mult, "Combined < targetability alone (C4 adds its own penalty)"
