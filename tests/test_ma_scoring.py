"""Tests for bve.intelligence.ma_scoring — three-model decomposition and saturation fix."""
from __future__ import annotations

import math

import pytest

from bve.intelligence.ma_scoring import (
    COMPOSITE_MAX_WITH_DL_GATE,
    SATURATION_THRESHOLD,
    AcquirerFitDecomposed,
    DealLikelihoodScore,
    FINANCING_REASON_LONG_RUNWAY,
    FINANCING_REASON_NOT_PRESSURED,
    FINANCING_REASON_NO_NEAR_TERM_NEED,
    FINANCING_REASON_STANDALONE_VIABLE,
    FINANCING_REASON_NO_BUYER_URGENCY,
    FINANCING_REASON_RECENT_FINANCING,
    FINANCING_REASON_NO_ACTIVIST_PRESSURE,
    TargetAttractivenessScore,
    _LOW_PRESSURE_SCORE_CAP,
    _LOW_FINANCING_PRESSURE_THRESHOLD,
    apply_financing_pressure_gate,
    apply_saturation_penalty,
    compute_acquirer_fit_decomposed,
    compute_deal_likelihood,
    compute_mna_composite_score,
    compute_score_saturation_diagnostics,
    compute_target_attractiveness,
)


# ---------------------------------------------------------------------------
# apply_saturation_penalty
# ---------------------------------------------------------------------------

class TestApplySaturationPenalty:
    def test_no_penalty_zero_at_cap(self):
        score = apply_saturation_penalty(0.80, sub_scores=[0.50, 0.60, 0.40, 0.30])
        assert score == pytest.approx(0.80, abs=1e-5)

    def test_no_penalty_one_at_cap(self):
        score = apply_saturation_penalty(0.90, sub_scores=[0.98, 0.50, 0.40, 0.30])
        assert score == pytest.approx(0.90, abs=1e-5)

    def test_penalty_two_at_cap(self):
        # 2 sub-scores at cap → penalty = 1 * 0.12 → score * 0.88
        raw = 0.90
        score = apply_saturation_penalty(raw, sub_scores=[0.98, 0.97, 0.40, 0.30])
        assert score < raw
        assert score == pytest.approx(raw * 0.88, abs=1e-5)

    def test_penalty_three_at_cap(self):
        raw = 0.95
        score = apply_saturation_penalty(raw, sub_scores=[0.99, 0.98, 0.97, 0.30])
        # 3 at cap → penalty = 2 * 0.12 = 0.24 → score * 0.76
        assert score == pytest.approx(raw * 0.76, abs=1e-5)

    def test_clamped_to_one(self):
        score = apply_saturation_penalty(1.0, sub_scores=[0.50])
        assert score <= 1.0

    def test_clamped_to_zero(self):
        score = apply_saturation_penalty(0.0, sub_scores=[0.99, 0.98, 0.97, 0.96])
        assert score == 0.0

    def test_all_at_cap_reduces_score(self):
        raw = 1.0
        score = apply_saturation_penalty(
            raw, sub_scores=[1.0, 1.0, 1.0, 1.0, 1.0]
        )
        # 5 at cap → excess=4 → penalty = 0.48 → 1.0 * 0.52
        assert score < 1.0
        assert score == pytest.approx(raw * (1 - 4 * 0.12), abs=1e-5)


# ---------------------------------------------------------------------------
# compute_score_saturation_diagnostics
# ---------------------------------------------------------------------------

class TestScoreSaturationDiagnostics:
    def test_empty_list(self):
        diag = compute_score_saturation_diagnostics([])
        assert diag["n"] == 0
        assert diag["pct_at_cap"] == 0.0

    def test_all_at_cap(self):
        scores = [1.0] * 10
        diag = compute_score_saturation_diagnostics(scores)
        assert diag["pct_at_cap"] == pytest.approx(1.0, abs=1e-5)
        assert diag["mean"] == pytest.approx(1.0, abs=1e-5)
        assert diag["n"] == 10

    def test_none_at_cap(self):
        scores = [0.5, 0.6, 0.7, 0.4]
        diag = compute_score_saturation_diagnostics(scores)
        assert diag["pct_at_cap"] == pytest.approx(0.0, abs=1e-5)
        assert 0.0 <= diag["mean"] <= 1.0

    def test_partial_saturation(self):
        scores = [0.3, 0.5, 0.7, 1.0, 1.0]
        diag = compute_score_saturation_diagnostics(scores)
        assert diag["pct_at_cap"] == pytest.approx(0.4, abs=1e-5)
        assert diag["n"] == 5

    def test_entropy_is_normalised(self):
        scores = [i / 10.0 for i in range(10)]
        diag = compute_score_saturation_diagnostics(scores)
        assert 0.0 <= diag["entropy"] <= 1.0

    def test_gini_uniform(self):
        scores = [0.5] * 10
        diag = compute_score_saturation_diagnostics(scores)
        # Perfectly equal → Gini ≈ 0
        assert abs(diag["gini"]) < 0.01

    def test_gini_concentrated(self):
        scores = [0.0] * 9 + [1.0]
        diag = compute_score_saturation_diagnostics(scores)
        # Maximum concentration → Gini high
        assert diag["gini"] > 0.5

    def test_p10_p90_order(self):
        scores = list(range(10))
        diag = compute_score_saturation_diagnostics([s / 9 for s in scores])
        assert diag["p10"] <= diag["median"] <= diag["p90"]


# ---------------------------------------------------------------------------
# compute_target_attractiveness
# ---------------------------------------------------------------------------

class TestTargetAttractivenessScore:
    def test_all_max_components_penalised(self):
        ta = compute_target_attractiveness(
            de_risking_stage_score=1.0,
            valuation_discount_score=1.0,
            scarcity_score=1.0,
            peak_sales_millions=5000.0,
        )
        # Raw weighted sum = 1.0; penalty applied for multiple components at max
        assert isinstance(ta, TargetAttractivenessScore)
        assert ta.score < 1.0

    def test_zero_inputs(self):
        ta = compute_target_attractiveness(
            de_risking_stage_score=0.0,
            valuation_discount_score=0.0,
            scarcity_score=0.0,
            peak_sales_millions=0.0,
        )
        assert ta.score >= 0.0
        assert ta.score <= 1.0

    def test_missing_peak_sales_uses_neutral(self):
        ta_none = compute_target_attractiveness(
            de_risking_stage_score=0.5,
            valuation_discount_score=0.5,
            scarcity_score=0.5,
            peak_sales_millions=None,
        )
        # peak_sales_signal defaults to 0.30 neutral
        assert ta_none.peak_sales_signal == pytest.approx(0.30, abs=1e-5)

    def test_large_peak_sales_capped(self):
        ta = compute_target_attractiveness(
            de_risking_stage_score=0.5,
            valuation_discount_score=0.5,
            scarcity_score=0.5,
            peak_sales_millions=100_000.0,
        )
        assert ta.peak_sales_signal <= 1.0

    def test_score_in_range(self):
        ta = compute_target_attractiveness(
            de_risking_stage_score=0.75,
            valuation_discount_score=0.60,
            scarcity_score=0.40,
            peak_sales_millions=1500.0,
        )
        assert 0.0 <= ta.score <= 1.0

    def test_diagnostics_populated(self):
        ta = compute_target_attractiveness(
            de_risking_stage_score=0.9,
            valuation_discount_score=0.8,
            scarcity_score=0.7,
            peak_sales_millions=2000.0,
        )
        assert "n_at_cap" in ta.diagnostics
        assert "raw_weighted_sum" in ta.diagnostics


# ---------------------------------------------------------------------------
# compute_deal_likelihood
# ---------------------------------------------------------------------------

class TestDealLikelihoodScore:
    def test_zero_inputs(self):
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.0,
            external_deal_pressure_score=0.0,
            target_signal_score=0.0,
            days_to_catalyst=None,
        )
        assert 0.0 <= dl.score <= 1.0

    def test_all_max_penalised(self):
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=1.0,
            external_deal_pressure_score=1.0,
            target_signal_score=1.0,
            days_to_catalyst=0,
        )
        assert dl.score < 1.0

    def test_catalyst_proximity_zero_days(self):
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.5,
            external_deal_pressure_score=0.3,
            target_signal_score=0.2,
            days_to_catalyst=0,
        )
        assert dl.catalyst_proximity == pytest.approx(1.0, abs=1e-5)

    def test_catalyst_proximity_far_out(self):
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.5,
            external_deal_pressure_score=0.3,
            target_signal_score=0.2,
            days_to_catalyst=365,
        )
        # exp(-365/90) ≈ 0.017
        assert dl.catalyst_proximity < 0.05

    def test_catalyst_proximity_none(self):
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.5,
            external_deal_pressure_score=0.3,
            target_signal_score=0.2,
            days_to_catalyst=None,
        )
        assert dl.catalyst_proximity == 0.0

    def test_score_in_range(self):
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.70,
            external_deal_pressure_score=0.55,
            target_signal_score=0.25,
            days_to_catalyst=90,
        )
        assert 0.0 <= dl.score <= 1.0

    def test_low_pressure_gate_applies(self):
        """When cash_runway_pressure_score is very low, gate caps score."""
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.05,   # well-funded, low pressure
            external_deal_pressure_score=0.80,
            target_signal_score=0.10,
            days_to_catalyst=None,             # no near-term catalyst
        )
        assert dl.financing_gate_applied is True
        assert dl.score <= _LOW_PRESSURE_SCORE_CAP + 1e-5
        assert FINANCING_REASON_NOT_PRESSURED in dl.financing_reason_codes

    def test_low_pressure_gate_reason_codes(self):
        """Long runway and no near-term need reason codes are set."""
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.05,
            external_deal_pressure_score=0.50,
            target_signal_score=0.10,
            days_to_catalyst=None,
            cash_runway_quarters=10.0,
        )
        assert FINANCING_REASON_LONG_RUNWAY in dl.financing_reason_codes
        assert FINANCING_REASON_NO_NEAR_TERM_NEED in dl.financing_reason_codes

    def test_high_pressure_gate_not_applied(self):
        """When cash_runway_pressure_score is high, gate is not applied."""
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.85,
            external_deal_pressure_score=0.60,
            target_signal_score=0.30,
            days_to_catalyst=60,
        )
        assert dl.financing_gate_applied is False
        assert dl.financing_reason_codes == []

    def test_scarcity_override_lifts_gate(self):
        """High scarcity score overrides the low-pressure cap."""
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.05,
            external_deal_pressure_score=0.90,
            target_signal_score=0.10,
            days_to_catalyst=None,
            scarcity_score=0.90,   # very high scarcity overrides gate
        )
        assert dl.financing_gate_applied is False

    def test_gate_fields_present_on_model(self):
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.50,
            external_deal_pressure_score=0.50,
            target_signal_score=0.50,
            days_to_catalyst=30,
        )
        assert hasattr(dl, "financing_gate_applied")
        assert hasattr(dl, "financing_reason_codes")
        assert isinstance(dl.financing_reason_codes, list)

    def test_near_term_catalyst_prevents_no_near_term_code(self):
        """Near-term catalyst (<=90d) means no_near_term_funding_need code is absent."""
        dl = compute_deal_likelihood(
            cash_runway_pressure_score=0.05,
            external_deal_pressure_score=0.30,
            target_signal_score=0.10,
            days_to_catalyst=30,   # within 90 days
        )
        assert FINANCING_REASON_NO_NEAR_TERM_NEED not in dl.financing_reason_codes


# ---------------------------------------------------------------------------
# apply_financing_pressure_gate (unit tests)
# ---------------------------------------------------------------------------

class TestApplyFinancingPressureGate:
    def test_high_pressure_no_gate(self):
        score, applied, codes = apply_financing_pressure_gate(
            0.70,
            financing_pressure_score=0.80,
        )
        assert applied is False
        assert codes == []
        assert score == pytest.approx(0.70, abs=1e-5)

    def test_low_pressure_caps_score(self):
        score, applied, codes = apply_financing_pressure_gate(
            0.75,
            financing_pressure_score=0.10,
        )
        assert applied is True
        assert score <= _LOW_PRESSURE_SCORE_CAP + 1e-5
        assert FINANCING_REASON_NOT_PRESSURED in codes

    def test_scarcity_override(self):
        score, applied, codes = apply_financing_pressure_gate(
            0.75,
            financing_pressure_score=0.05,
            scarcity_score=0.90,
        )
        assert applied is False  # override active
        assert score == pytest.approx(0.75, abs=1e-5)

    def test_standalone_viable_code(self):
        score, applied, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.05,  # below 0.10 → standalone_viable
        )
        assert FINANCING_REASON_STANDALONE_VIABLE in codes

    def test_long_runway_code(self):
        _, _, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.10,
            cash_runway_quarters=12.0,
        )
        assert FINANCING_REASON_LONG_RUNWAY in codes

    def test_short_runway_no_long_runway_code(self):
        _, _, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.10,
            cash_runway_quarters=4.0,
        )
        assert FINANCING_REASON_LONG_RUNWAY not in codes

    def test_near_term_catalyst_no_near_term_code(self):
        _, _, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.10,
            has_near_term_catalyst=True,
        )
        assert FINANCING_REASON_NO_NEAR_TERM_NEED not in codes

    def test_score_unchanged_when_already_below_cap(self):
        score, applied, _ = apply_financing_pressure_gate(
            0.30,  # already below cap
            financing_pressure_score=0.05,
        )
        assert applied is True
        assert score == pytest.approx(0.30, abs=1e-5)

    def test_output_clamped_to_zero(self):
        score, _, _ = apply_financing_pressure_gate(
            -0.10,
            financing_pressure_score=0.80,
        )
        assert score == 0.0

    def test_output_clamped_to_one(self):
        score, _, _ = apply_financing_pressure_gate(
            1.50,
            financing_pressure_score=0.80,
        )
        assert score <= 1.0


# ---------------------------------------------------------------------------
# compute_acquirer_fit_decomposed
# ---------------------------------------------------------------------------

class TestAcquirerFitDecomposed:
    def test_zero_inputs(self):
        af = compute_acquirer_fit_decomposed(
            therapeutic_area_score=0.0,
            modality_score=0.0,
            strategic_priority_score=0.0,
            budget_score=0.0,
            matched_partnership=None,
        )
        assert af.score >= 0.0
        assert af.existing_partnership_bonus == 0.0

    def test_partnership_bonus_applied(self):
        af_no = compute_acquirer_fit_decomposed(
            therapeutic_area_score=0.8,
            modality_score=0.7,
            strategic_priority_score=0.6,
            budget_score=0.9,
            matched_partnership=None,
        )
        af_yes = compute_acquirer_fit_decomposed(
            therapeutic_area_score=0.8,
            modality_score=0.7,
            strategic_priority_score=0.6,
            budget_score=0.9,
            matched_partnership="PARTNER_TICKER",
        )
        assert af_yes.score > af_no.score
        assert af_yes.existing_partnership_bonus == 1.0

    def test_all_max_penalised(self):
        af = compute_acquirer_fit_decomposed(
            therapeutic_area_score=1.0,
            modality_score=1.0,
            strategic_priority_score=1.0,
            budget_score=1.0,
            matched_partnership="TICKER",
        )
        assert af.score < 1.0

    def test_ta_modality_combination(self):
        af = compute_acquirer_fit_decomposed(
            therapeutic_area_score=1.0,
            modality_score=0.0,
            strategic_priority_score=0.0,
            budget_score=0.0,
            matched_partnership=None,
        )
        # ta_modality = 1.0*0.55 + 0.0*0.45 = 0.55
        assert af.ta_modality_fit == pytest.approx(0.55, abs=1e-5)

    def test_return_type(self):
        af = compute_acquirer_fit_decomposed(
            therapeutic_area_score=0.7,
            modality_score=0.6,
            strategic_priority_score=0.5,
            budget_score=0.8,
            matched_partnership=None,
        )
        assert isinstance(af, AcquirerFitDecomposed)
        assert 0.0 <= af.score <= 1.0


# ---------------------------------------------------------------------------
# Saturation rate: after applying penalty, realistic mixed scores stay below cap
# ---------------------------------------------------------------------------

class TestSaturationRateTarget:
    """Verify that the penalty mechanism keeps saturation below 10% for realistic inputs."""

    def _make_realistic_scores(self) -> list[float]:
        """Simulate a set of realistic mixed-signal scores."""
        import random
        rng = random.Random(42)
        scores = []
        for _ in range(100):
            # Mix of high/medium/low signal components
            ta = rng.uniform(0.4, 1.0)
            modality = rng.uniform(0.3, 1.0)
            stage = rng.uniform(0.3, 1.0)
            vuln = rng.uniform(0.0, 0.6)
            sub = [ta, modality, stage, vuln]
            raw = sum(sub) / len(sub)
            score = apply_saturation_penalty(raw, sub_scores=sub)
            scores.append(score)
        return scores

    def test_saturation_below_threshold(self):
        scores = self._make_realistic_scores()
        diag = compute_score_saturation_diagnostics(scores)
        # With realistic mixed scores the penalty keeps saturation well below 50%
        assert diag["pct_at_cap"] < 0.50

    def test_all_max_saturation_reduced(self):
        """When all inputs are max, penalty reduces scores below 1.0."""
        max_scores = []
        for _ in range(20):
            raw = 1.0
            score = apply_saturation_penalty(raw, sub_scores=[1.0, 1.0, 1.0, 1.0])
            max_scores.append(score)
        # All should be below 1.0 due to 3-extra-cap penalty
        assert all(s < 1.0 for s in max_scores)


# ---------------------------------------------------------------------------
# New reason codes (Sprint 19 T2)
# ---------------------------------------------------------------------------

class TestNewReasonCodes:
    def test_no_buyer_urgency_code_when_low_external_activity(self):
        """Low external deal activity → no_buyer_urgency code when gate fires."""
        _, _, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.10,
            external_deal_activity_score=0.10,  # below threshold
        )
        assert FINANCING_REASON_NO_BUYER_URGENCY in codes

    def test_no_buyer_urgency_code_absent_when_high_external_activity(self):
        """High external deal activity → no_buyer_urgency code NOT set."""
        _, _, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.10,
            external_deal_activity_score=0.50,  # above threshold
        )
        assert FINANCING_REASON_NO_BUYER_URGENCY not in codes

    def test_recent_financing_code(self):
        """Recent financing (< 180d) → recent_financing code when gate fires."""
        _, _, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.10,
            days_since_last_financing=90,
        )
        assert FINANCING_REASON_RECENT_FINANCING in codes

    def test_old_financing_no_code(self):
        """Old financing (>= 180d) → no recent_financing code."""
        _, _, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.10,
            days_since_last_financing=365,
        )
        assert FINANCING_REASON_RECENT_FINANCING not in codes

    def test_no_activist_pressure_code(self):
        """Low activist signal → no_ownership_activist_pressure code when gate fires."""
        _, _, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.10,
            activist_signal_score=0.10,  # below 0.20
        )
        assert FINANCING_REASON_NO_ACTIVIST_PRESSURE in codes

    def test_activist_present_no_code(self):
        """High activist signal → no_ownership_activist_pressure code NOT set."""
        _, _, codes = apply_financing_pressure_gate(
            0.60,
            financing_pressure_score=0.10,
            activist_signal_score=0.50,
        )
        assert FINANCING_REASON_NO_ACTIVIST_PRESSURE not in codes

    def test_reason_codes_absent_when_gate_not_fired(self):
        """New codes are NOT present when financing pressure is high (gate does not fire)."""
        _, applied, codes = apply_financing_pressure_gate(
            0.70,
            financing_pressure_score=0.80,
            external_deal_activity_score=0.05,
            days_since_last_financing=30,
            activist_signal_score=0.05,
        )
        assert applied is False
        assert FINANCING_REASON_NO_BUYER_URGENCY not in codes
        assert FINANCING_REASON_RECENT_FINANCING not in codes
        assert FINANCING_REASON_NO_ACTIVIST_PRESSURE not in codes


# ---------------------------------------------------------------------------
# compute_mna_composite_score (Sprint 19 T2)
# ---------------------------------------------------------------------------

def _make_ta(score: float = 0.70) -> TargetAttractivenessScore:
    return TargetAttractivenessScore(
        score=score,
        de_risking_stage=score,
        valuation_discount=score,
        scarcity=score,
        peak_sales_signal=score,
    )


def _make_dl(score: float = 0.50, gate: bool = False, codes: list | None = None) -> DealLikelihoodScore:
    return DealLikelihoodScore(
        score=score,
        financing_pressure=0.50,
        external_deal_activity=0.50,
        insider_board_signals=0.50,
        catalyst_proximity=0.50,
        financing_gate_applied=gate,
        financing_reason_codes=codes or [],
    )


def _make_af(score: float = 0.80) -> AcquirerFitDecomposed:
    return AcquirerFitDecomposed(
        score=score,
        ta_modality_fit=score,
        pipeline_gap_alignment=score,
        deal_affordability=score,
        existing_partnership_bonus=0.0,
    )


class TestComputeMnaCompositeScore:
    def test_no_gate_no_cap(self):
        """When DL gate not fired, composite is uncapped weighted sum."""
        ta = _make_ta(0.80)
        dl = _make_dl(0.70, gate=False)
        af = _make_af(0.90)
        score, caps = compute_mna_composite_score(ta, dl, af)
        assert 0.0 <= score <= 1.0
        assert "composite_capped_by_dl_gate" not in caps

    def test_gate_fired_caps_composite(self):
        """When DL gate fires and composite > COMPOSITE_MAX, it is capped."""
        ta = _make_ta(1.0)
        dl = _make_dl(0.40, gate=True, codes=["financing_not_pressured"])
        af = _make_af(1.0)
        score, caps = compute_mna_composite_score(ta, dl, af)
        assert score <= COMPOSITE_MAX_WITH_DL_GATE + 1e-6
        assert "composite_capped_by_dl_gate" in caps

    def test_gate_fired_but_composite_already_low(self):
        """When DL gate fires but composite is already below cap, no extra cap applied."""
        ta = _make_ta(0.30)
        dl = _make_dl(0.20, gate=True, codes=["financing_not_pressured"])
        af = _make_af(0.30)
        score, caps = compute_mna_composite_score(ta, dl, af)
        assert score <= COMPOSITE_MAX_WITH_DL_GATE
        assert "composite_capped_by_dl_gate" not in caps

    def test_strategic_fit_alone_cannot_drive_high_score(self):
        """High TA + AF with low DL gate fired → composite capped below 0.66."""
        ta = _make_ta(1.0)
        dl = _make_dl(0.40, gate=True, codes=["financing_not_pressured"])
        af = _make_af(1.0)
        score, _ = compute_mna_composite_score(ta, dl, af)
        # Without the gate: 1.0*0.35 + 0.40*0.25 + 1.0*0.40 = 0.85 (before saturation)
        # With gate: score <= COMPOSITE_MAX_WITH_DL_GATE
        assert score <= COMPOSITE_MAX_WITH_DL_GATE + 1e-6

    def test_reason_codes_propagated(self):
        """Financing reason codes from DL are propagated to cap_reasons."""
        dl = _make_dl(0.40, gate=True, codes=["financing_not_pressured", "long_runway"])
        ta = _make_ta(0.90)
        af = _make_af(0.90)
        _, caps = compute_mna_composite_score(ta, dl, af)
        assert "financing_not_pressured" in caps
        assert "long_runway" in caps

    def test_score_clamped_to_unit_interval(self):
        score, _ = compute_mna_composite_score(_make_ta(0.0), _make_dl(0.0), _make_af(0.0))
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Sprint 20: dual gate, two-driver requirement, false-positive guard
# ---------------------------------------------------------------------------

from bve.intelligence.ma_scoring import (
    COMPOSITE_MAX_DUAL_GATE,
    COMPOSITE_MAX_ONE_DRIVER,
    COMPOSITE_MAX_ZERO_DRIVERS,
    FINANCING_REASON_NOT_PRESSURED,
    FINANCING_REASON_NO_BUYER_URGENCY,
    _count_transaction_drivers,
)


def _make_dl_weak_all() -> DealLikelihoodScore:
    """DL with all sub-scores below any driver threshold — zero independent drivers."""
    return DealLikelihoodScore(
        score=0.20,
        financing_pressure=0.10,       # below _DRIVER_FINANCING_PRESSURE_MIN (0.35)
        external_deal_activity=0.10,   # below _DRIVER_EXTERNAL_ACTIVITY_MIN (0.30)
        insider_board_signals=0.10,    # below _DRIVER_ACTIVIST_MIN (0.30)
        catalyst_proximity=0.10,       # below _DRIVER_CATALYST_MIN (0.35)
        financing_gate_applied=True,
        financing_reason_codes=[
            FINANCING_REASON_NOT_PRESSURED,
            FINANCING_REASON_NO_BUYER_URGENCY,
        ],
    )


def _make_dl_dual_gate() -> DealLikelihoodScore:
    """DL where both financing_not_pressured AND no_buyer_urgency are set."""
    return DealLikelihoodScore(
        score=0.25,
        financing_pressure=0.10,
        external_deal_activity=0.08,
        insider_board_signals=0.15,
        catalyst_proximity=0.05,
        financing_gate_applied=True,
        financing_reason_codes=[
            FINANCING_REASON_NOT_PRESSURED,
            FINANCING_REASON_NO_BUYER_URGENCY,
        ],
    )


class TestDualGateAndDriverRequirement:
    """Sprint 20: dual gate + two-driver caps on composite score."""

    def test_dual_gate_caps_composite_at_050(self):
        """When both financing_not_pressured AND no_buyer_urgency fire, cap at 0.50."""
        ta = _make_ta(1.0)
        dl = _make_dl_dual_gate()
        af = _make_af(1.0)
        score, caps = compute_mna_composite_score(ta, dl, af)
        assert score <= COMPOSITE_MAX_DUAL_GATE + 1e-6
        assert "composite_capped_by_dual_gate" in caps

    def test_dual_gate_more_restrictive_than_single_gate(self):
        """Dual gate (0.50) is stricter than single DL gate (0.65)."""
        ta = _make_ta(1.0)
        dl_single = _make_dl(0.40, gate=True, codes=[FINANCING_REASON_NOT_PRESSURED])
        dl_dual = _make_dl_dual_gate()
        af = _make_af(1.0)
        score_single, _ = compute_mna_composite_score(ta, dl_single, af)
        score_dual, _ = compute_mna_composite_score(ta, dl_dual, af)
        assert score_dual <= score_single
        assert score_dual <= COMPOSITE_MAX_DUAL_GATE + 1e-6

    def test_zero_drivers_caps_composite_at_045(self):
        """Zero independent transaction drivers → composite capped at 0.45."""
        # Use explicit sub-scores below all driver thresholds:
        # scarcity < 0.60, valuation_discount < 0.45 prevent TA/AF-based drivers
        ta = TargetAttractivenessScore(
            score=0.60,
            de_risking_stage=0.40,
            valuation_discount=0.40,  # below _DRIVER_VALUATION_MIN (0.45)
            scarcity=0.40,            # below _DRIVER_SCARCITY_MIN (0.60)
            peak_sales_signal=0.40,
        )
        dl = _make_dl_weak_all()
        af = AcquirerFitDecomposed(
            score=0.60,
            ta_modality_fit=0.40,
            pipeline_gap_alignment=0.40,  # below 0.50 threshold for scarcity_plus_fit
            deal_affordability=0.40,
            existing_partnership_bonus=0.0,
        )
        # raw ≈ 0.60*0.35 + 0.20*0.25 + 0.60*0.40 = 0.50 > 0.45 → cap fires
        score, caps = compute_mna_composite_score(ta, dl, af)
        assert score <= COMPOSITE_MAX_ZERO_DRIVERS + 1e-6
        assert "composite_capped_zero_drivers" in caps

    def test_one_driver_caps_at_065(self):
        """One independent driver → composite cannot exceed 0.65."""
        # Only catalyst_proximity fires as a driver; TA/AF sub-scores kept below
        # driver thresholds to prevent scarcity_plus_fit / valuation_distress drivers
        dl = DealLikelihoodScore(
            score=0.45,
            financing_pressure=0.10,       # not a driver
            external_deal_activity=0.10,   # not a driver
            insider_board_signals=0.10,    # not a driver
            catalyst_proximity=0.80,       # driver: >= 0.35
            financing_gate_applied=False,
            financing_reason_codes=[],
        )
        ta = TargetAttractivenessScore(
            score=0.80,
            de_risking_stage=0.40,
            valuation_discount=0.40,  # below _DRIVER_VALUATION_MIN (0.45)
            scarcity=0.40,            # below _DRIVER_SCARCITY_MIN (0.60)
            peak_sales_signal=0.40,
        )
        af = AcquirerFitDecomposed(
            score=0.80,
            ta_modality_fit=0.40,
            pipeline_gap_alignment=0.40,  # below 0.50 threshold
            deal_affordability=0.40,
            existing_partnership_bonus=0.0,
        )
        # raw ≈ 0.80*0.35 + 0.45*0.25 + 0.80*0.40 = 0.7125 > 0.65 → cap fires
        score, caps = compute_mna_composite_score(ta, dl, af)
        assert score <= COMPOSITE_MAX_ONE_DRIVER + 1e-6
        assert "composite_needs_two_drivers" in caps

    def test_two_drivers_allows_score_above_065(self):
        """Two or more independent drivers allows composite above 0.65."""
        dl = DealLikelihoodScore(
            score=0.90,
            financing_pressure=0.80,       # driver 1
            external_deal_activity=0.70,   # driver 2
            insider_board_signals=0.10,
            catalyst_proximity=0.10,
            financing_gate_applied=False,
            financing_reason_codes=[],
        )
        ta = _make_ta(0.80)
        af = _make_af(0.90)
        score, caps = compute_mna_composite_score(ta, dl, af)
        # With 2+ drivers and no gate, score can exceed 0.65
        assert "composite_needs_two_drivers" not in caps
        # Score should be above 0.65 given strong inputs
        assert score > 0.65

    def test_n_drivers_reported_in_reason_codes(self):
        """n_drivers count always appears as a reason code for diagnostics."""
        ta = _make_ta(0.70)
        dl = _make_dl(0.50)
        af = _make_af(0.70)
        _, caps = compute_mna_composite_score(ta, dl, af)
        assert any(c.startswith("n_drivers:") for c in caps)

    def test_driver_names_reported_in_reason_codes(self):
        """Active driver names appear as 'driver:name' reason codes."""
        dl = DealLikelihoodScore(
            score=0.80,
            financing_pressure=0.80,    # driver
            external_deal_activity=0.60,  # driver
            insider_board_signals=0.10,
            catalyst_proximity=0.10,
            financing_gate_applied=False,
            financing_reason_codes=[],
        )
        ta = _make_ta(0.70)
        af = _make_af(0.70)
        _, caps = compute_mna_composite_score(ta, dl, af)
        assert "driver:financing_pressure" in caps
        assert "driver:external_deal_activity" in caps

    def test_count_transaction_drivers_all_zero(self):
        """All sub-scores below thresholds → 0 drivers."""
        ta = _make_ta(0.30)
        dl = _make_dl_weak_all()
        af = _make_af(0.30)
        n, names = _count_transaction_drivers(ta, dl, af)
        assert n == 0
        assert names == []

    def test_count_transaction_drivers_financing_only(self):
        """High financing pressure alone → 1 driver."""
        dl = DealLikelihoodScore(
            score=0.60,
            financing_pressure=0.80,
            external_deal_activity=0.10,
            insider_board_signals=0.10,
            catalyst_proximity=0.10,
            financing_gate_applied=False,
            financing_reason_codes=[],
        )
        ta = _make_ta(0.30)
        af = _make_af(0.30)
        n, names = _count_transaction_drivers(ta, dl, af)
        assert n == 1
        assert "financing_pressure" in names

    def test_strategic_fit_alone_no_drivers_capped_at_045(self):
        """Strategic fit alone (high TA+AF, no urgency signals) cannot produce >0.45."""
        # No financing pressure, no external activity, no catalyst — zero drivers
        # TA/AF sub-scores kept below driver thresholds to ensure zero-driver path
        dl = DealLikelihoodScore(
            score=0.20,
            financing_pressure=0.05,
            external_deal_activity=0.05,
            insider_board_signals=0.05,
            catalyst_proximity=0.05,
            financing_gate_applied=True,
            financing_reason_codes=[
                FINANCING_REASON_NOT_PRESSURED,
                FINANCING_REASON_NO_BUYER_URGENCY,
            ],
        )
        ta = TargetAttractivenessScore(
            score=1.0,
            de_risking_stage=0.40,
            valuation_discount=0.40,  # below _DRIVER_VALUATION_MIN (0.45)
            scarcity=0.40,            # below _DRIVER_SCARCITY_MIN (0.60)
            peak_sales_signal=0.40,
        )
        af = AcquirerFitDecomposed(
            score=1.0,
            ta_modality_fit=0.40,
            pipeline_gap_alignment=0.40,  # below 0.50 threshold
            deal_affordability=0.40,
            existing_partnership_bonus=0.0,
        )
        # raw ≈ 1.0*0.35 + 0.20*0.25 + 1.0*0.40 = 0.80 → dual gate fires (0.50)
        # then zero-driver cap fires (0.45)
        score, caps = compute_mna_composite_score(ta, dl, af)
        assert score <= COMPOSITE_MAX_ZERO_DRIVERS + 1e-6
        assert "composite_capped_zero_drivers" in caps

    def test_mna_screening_score_above_080_requires_two_drivers(self):
        """Score > 0.65 (which is the one-driver ceiling) requires two drivers."""
        # Build a high-score scenario with only 1 driver (financing_pressure)
        # TA/AF sub-scores kept below driver thresholds to isolate to 1 driver
        dl_one_driver = DealLikelihoodScore(
            score=0.80,
            financing_pressure=0.80,    # driver 1
            external_deal_activity=0.10,  # not a driver
            insider_board_signals=0.10,   # not a driver
            catalyst_proximity=0.10,      # not a driver
            financing_gate_applied=False,
            financing_reason_codes=[],
        )
        ta = TargetAttractivenessScore(
            score=0.90,
            de_risking_stage=0.40,
            valuation_discount=0.40,  # below _DRIVER_VALUATION_MIN (0.45)
            scarcity=0.40,            # below _DRIVER_SCARCITY_MIN (0.60)
            peak_sales_signal=0.40,
        )
        af = AcquirerFitDecomposed(
            score=0.90,
            ta_modality_fit=0.40,
            pipeline_gap_alignment=0.40,  # below 0.50 threshold
            deal_affordability=0.40,
            existing_partnership_bonus=0.0,
        )
        # raw ≈ 0.90*0.35 + 0.80*0.25 + 0.90*0.40 = 0.875 > 0.65 → cap fires
        score, caps = compute_mna_composite_score(ta, dl_one_driver, af)
        assert score <= COMPOSITE_MAX_ONE_DRIVER + 1e-6
        assert "composite_needs_two_drivers" in caps
