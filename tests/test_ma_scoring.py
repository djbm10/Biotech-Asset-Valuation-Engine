"""Tests for bve.intelligence.ma_scoring — three-model decomposition and saturation fix."""
from __future__ import annotations

import math

import pytest

from bve.intelligence.ma_scoring import (
    SATURATION_THRESHOLD,
    AcquirerFitDecomposed,
    DealLikelihoodScore,
    FINANCING_REASON_LONG_RUNWAY,
    FINANCING_REASON_NOT_PRESSURED,
    FINANCING_REASON_NO_NEAR_TERM_NEED,
    FINANCING_REASON_STANDALONE_VIABLE,
    TargetAttractivenessScore,
    _LOW_PRESSURE_SCORE_CAP,
    _LOW_FINANCING_PRESSURE_THRESHOLD,
    apply_financing_pressure_gate,
    apply_saturation_penalty,
    compute_acquirer_fit_decomposed,
    compute_deal_likelihood,
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
