"""
Tests for Layer 2 — BD Decision Engine (Sprint 38).

Coverage:
- Strategic priority formula
- Transaction probability formula (driver strength normalisation)
- Balance / fragility penalty thresholds
- Interaction bonus computation and 0.08 cap
- DataConfidence multiplier application (including VERY_LOW → 0)
- Classification matrix all cells
- Layer2Output fields populated correctly
- compute_bd_layer2 end-to-end integration
- Backward compat: compute_mna_composite_score still returns (float, list[str])
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_scoring import (
    AcquirerFitDecomposed,
    BDActionClassification,
    DataConfidence,
    DealLikelihoodScore,
    Layer2Output,
    TargetAttractivenessScore,
    _BONUS_CAP,
    _BALANCE_SEVERE,
    _BALANCE_WEAK,
    _N_DRIVER_MAX,
    _SP_HIGH,
    _SP_MED,
    _TP_HIGH,
    _TP_MED,
    _compute_balance_penalty,
    _compute_interaction_bonuses,
    _compute_strategic_priority,
    _compute_transaction_probability,
    _classify_bd_action,
    compute_bd_layer2,
    compute_mna_composite_score,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ta(
    score: float = 0.70,
    de_risking_stage: float = 0.70,
    valuation_discount: float = 0.70,
    scarcity: float = 0.70,
    peak_sales_signal: float = 0.70,
) -> TargetAttractivenessScore:
    return TargetAttractivenessScore(
        score=score,
        de_risking_stage=de_risking_stage,
        valuation_discount=valuation_discount,
        scarcity=scarcity,
        peak_sales_signal=peak_sales_signal,
    )


def _dl(
    score: float = 0.65,
    financing_pressure: float = 0.60,
    external_deal_activity: float = 0.55,
    insider_board_signals: float = 0.45,
    catalyst_proximity: float = 0.50,
    financing_gate_applied: bool = False,
    financing_reason_codes: list[str] | None = None,
) -> DealLikelihoodScore:
    return DealLikelihoodScore(
        score=score,
        financing_pressure=financing_pressure,
        external_deal_activity=external_deal_activity,
        insider_board_signals=insider_board_signals,
        catalyst_proximity=catalyst_proximity,
        financing_gate_applied=financing_gate_applied,
        financing_reason_codes=financing_reason_codes or [],
    )


def _af(
    score: float = 0.70,
    ta_modality_fit: float = 0.70,
    pipeline_gap_alignment: float = 0.70,
    deal_affordability: float = 0.70,
    existing_partnership_bonus: float = 0.0,
) -> AcquirerFitDecomposed:
    return AcquirerFitDecomposed(
        score=score,
        ta_modality_fit=ta_modality_fit,
        pipeline_gap_alignment=pipeline_gap_alignment,
        deal_affordability=deal_affordability,
        existing_partnership_bonus=existing_partnership_bonus,
    )


def _run(**overrides) -> Layer2Output:
    kwargs = dict(ta=_ta(), dl=_dl(), af=_af())
    kwargs.update(overrides)
    return compute_bd_layer2(**kwargs)


# ---------------------------------------------------------------------------
# Strategic Priority
# ---------------------------------------------------------------------------

class TestStrategicPriority:
    def test_formula_correctness(self):
        ta = _ta(score=0.80, scarcity=0.70)
        af = _af(score=0.60)
        expected = round(0.45 * 0.60 + 0.35 * 0.80 + 0.20 * 0.70, 6)
        result = _compute_strategic_priority(ta, af)
        assert result == pytest.approx(expected, abs=1e-6)

    def test_all_zeros(self):
        ta = _ta(score=0.0, scarcity=0.0)
        af = _af(score=0.0)
        assert _compute_strategic_priority(ta, af) == pytest.approx(0.0)

    def test_all_ones(self):
        ta = _ta(score=1.0, scarcity=1.0)
        af = _af(score=1.0)
        assert _compute_strategic_priority(ta, af) == pytest.approx(1.0)

    def test_scarcity_contributes_independently(self):
        """TA.scarcity has its own 0.20 weight, separate from TA.score."""
        ta_hi_scarcity = _ta(score=0.50, scarcity=0.90)
        ta_lo_scarcity = _ta(score=0.50, scarcity=0.10)
        af = _af(score=0.50)
        assert _compute_strategic_priority(ta_hi_scarcity, af) > _compute_strategic_priority(ta_lo_scarcity, af)

    def test_af_has_largest_weight(self):
        """AF weight is 0.45 — changing AF should move score more than same delta in TA."""
        ta_base = _ta(score=0.50, scarcity=0.50)
        delta = 0.20
        sp_af_up = _compute_strategic_priority(ta_base, _af(score=0.50 + delta))
        sp_ta_up = _compute_strategic_priority(_ta(score=0.50 + delta, scarcity=0.50), _af(score=0.50))
        assert sp_af_up > sp_ta_up


# ---------------------------------------------------------------------------
# Transaction Probability
# ---------------------------------------------------------------------------

class TestTransactionProbability:
    def test_formula_correctness(self):
        ta = _ta(score=0.60)
        dl = _dl(score=0.70)
        af = _af(score=0.65)
        n_drivers = 3
        driver_strength = n_drivers / _N_DRIVER_MAX
        expected = round(0.45 * 0.70 + 0.25 * 0.65 + 0.15 * 0.60 + 0.15 * driver_strength, 6)
        result = _compute_transaction_probability(ta, dl, af, n_drivers)
        assert result == pytest.approx(expected, abs=1e-6)

    def test_zero_drivers_lowers_score(self):
        ta, dl, af = _ta(), _dl(), _af()
        score_0 = _compute_transaction_probability(ta, dl, af, 0)
        score_3 = _compute_transaction_probability(ta, dl, af, 3)
        assert score_3 > score_0

    def test_driver_strength_capped_at_1(self):
        """Even if n_drivers > _N_DRIVER_MAX the driver_strength is 1.0."""
        ta, dl, af = _ta(score=0.60), _dl(score=0.60), _af(score=0.60)
        score_6 = _compute_transaction_probability(ta, dl, af, 6)
        score_100 = _compute_transaction_probability(ta, dl, af, 100)
        assert score_6 == pytest.approx(score_100, abs=1e-6)

    def test_dl_has_largest_weight(self):
        ta = _ta(score=0.50)
        af = _af(score=0.50)
        base_dl = _dl(score=0.50)
        high_dl = _dl(score=0.90)
        assert (
            _compute_transaction_probability(ta, high_dl, af, 2)
            > _compute_transaction_probability(ta, base_dl, af, 2)
        )


# ---------------------------------------------------------------------------
# Balance / Fragility Penalty
# ---------------------------------------------------------------------------

class TestBalancePenalty:
    def test_balanced_scores_no_penalty(self):
        assert _compute_balance_penalty(0.70, 0.65, 0.72) == pytest.approx(0.0)

    def test_severe_imbalance_gives_10pct(self):
        # min/max = 0.10/0.90 = 0.111 < 0.35
        assert _compute_balance_penalty(0.90, 0.90, 0.10) == pytest.approx(0.10)

    def test_weak_imbalance_gives_5pct(self):
        # min/max = 0.39/0.80 = 0.4875 < 0.50 → 0.05 penalty
        assert _compute_balance_penalty(0.80, 0.80, 0.39) == pytest.approx(0.05)

    def test_at_severe_boundary(self):
        # balance = 0.35 exactly → crosses into 0.05 zone
        hi = 1.0
        lo = _BALANCE_SEVERE * hi  # exactly 0.35
        # lo/hi = 0.35, NOT < 0.35, so penalty should be 0.05
        assert _compute_balance_penalty(hi, hi, lo) == pytest.approx(0.05)

    def test_at_weak_boundary(self):
        # balance = 0.50 exactly → not < 0.50, penalty = 0.0
        hi = 1.0
        lo = _BALANCE_WEAK * hi
        assert _compute_balance_penalty(hi, hi, lo) == pytest.approx(0.0)

    def test_all_zeros_no_penalty(self):
        assert _compute_balance_penalty(0.0, 0.0, 0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Interaction Bonuses
# ---------------------------------------------------------------------------

class TestInteractionBonuses:
    def test_no_bonus_when_scores_low(self):
        ta = _ta(score=0.40)
        dl = _dl(score=0.40)
        af = _af(score=0.40)
        assert _compute_interaction_bonuses(ta, dl, af) == pytest.approx(0.0)

    def test_strategic_convergence_only(self):
        # TA >= 0.65, AF >= 0.65, DL < 0.60 → only strategic_convergence fires
        ta = _ta(score=0.70)
        dl = _dl(score=0.50)
        af = _af(score=0.70)
        bonus = _compute_interaction_bonuses(ta, dl, af)
        assert bonus == pytest.approx(0.04)

    def test_actionable_buyer_only(self):
        # AF >= 0.60, DL >= 0.60, TA < 0.65 → only actionable_buyer fires
        ta = _ta(score=0.50)
        dl = _dl(score=0.65)
        af = _af(score=0.65)
        bonus = _compute_interaction_bonuses(ta, dl, af)
        assert bonus == pytest.approx(0.04)

    def test_full_convergence_all_three(self):
        # TA >= 0.65, DL >= 0.60, AF >= 0.65 → all three fire (0.04+0.04+0.05=0.13) → capped at 0.08
        ta = _ta(score=0.80)
        dl = _dl(score=0.75)
        af = _af(score=0.80)
        bonus = _compute_interaction_bonuses(ta, dl, af)
        assert bonus == pytest.approx(_BONUS_CAP)

    def test_bonus_capped_at_08(self):
        """Regardless of combination, bonus never exceeds 0.08."""
        ta = _ta(score=1.0)
        dl = _dl(score=1.0)
        af = _af(score=1.0)
        assert _compute_interaction_bonuses(ta, dl, af) <= _BONUS_CAP + 1e-9


# ---------------------------------------------------------------------------
# Classification Matrix
# ---------------------------------------------------------------------------

class TestClassificationMatrix:
    def test_high_sp_high_tp_active_pursuit(self):
        cls, action, _ = _classify_bd_action(_SP_HIGH + 0.01, _TP_HIGH + 0.01)
        assert cls == BDActionClassification.ACTIVE_PURSUIT

    def test_high_sp_medium_tp_begin_relationship(self):
        cls, _, _ = _classify_bd_action(_SP_HIGH + 0.01, (_TP_MED + _TP_HIGH) / 2)
        assert cls == BDActionClassification.BEGIN_RELATIONSHIP

    def test_high_sp_low_tp_strategic_watchlist(self):
        cls, _, _ = _classify_bd_action(_SP_HIGH + 0.01, _TP_MED - 0.01)
        assert cls == BDActionClassification.STRATEGIC_WATCHLIST

    def test_medium_sp_high_tp_opportunistic(self):
        cls, _, _ = _classify_bd_action((_SP_MED + _SP_HIGH) / 2, _TP_HIGH + 0.01)
        assert cls == BDActionClassification.OPPORTUNISTIC_OUTREACH

    def test_low_sp_high_tp_distressed(self):
        cls, _, _ = _classify_bd_action(_SP_MED - 0.01, _TP_HIGH + 0.01)
        assert cls == BDActionClassification.DISTRESSED_NON_CORE

    def test_low_sp_low_tp_pass(self):
        cls, _, _ = _classify_bd_action(_SP_MED - 0.01, _TP_MED - 0.01)
        assert cls == BDActionClassification.PASS

    def test_recommended_action_non_empty(self):
        for sp in [0.30, 0.55, 0.80]:
            for tp in [0.20, 0.50, 0.70]:
                _, action, reason = _classify_bd_action(sp, tp)
                assert len(action) > 0
                assert len(reason) > 0


# ---------------------------------------------------------------------------
# DataConfidence multiplier
# ---------------------------------------------------------------------------

class TestDataConfidence:
    def test_high_confidence_no_discount(self):
        result = _run(data_confidence=DataConfidence.HIGH)
        assert result.confidence_multiplier == pytest.approx(1.00)

    def test_medium_confidence_discount(self):
        result = _run(data_confidence=DataConfidence.MEDIUM)
        assert result.confidence_multiplier == pytest.approx(0.93)

    def test_low_confidence_discount(self):
        result = _run(data_confidence=DataConfidence.LOW)
        assert result.confidence_multiplier == pytest.approx(0.85)

    def test_very_low_confidence_zeroes_score(self):
        result = _run(data_confidence=DataConfidence.VERY_LOW)
        assert result.bd_action_score == pytest.approx(0.0)
        assert result.confidence_multiplier == pytest.approx(0.0)

    def test_medium_lowers_score_vs_high(self):
        hi = _run(data_confidence=DataConfidence.HIGH)
        med = _run(data_confidence=DataConfidence.MEDIUM)
        assert med.bd_action_score < hi.bd_action_score

    def test_data_confidence_field_preserved(self):
        result = _run(data_confidence=DataConfidence.LOW)
        assert result.data_confidence == DataConfidence.LOW


# ---------------------------------------------------------------------------
# Layer2Output field completeness
# ---------------------------------------------------------------------------

class TestLayer2OutputFields:
    def test_all_scores_in_01(self):
        result = _run()
        assert 0.0 <= result.strategic_priority <= 1.0
        assert 0.0 <= result.transaction_probability <= 1.0
        assert 0.0 <= result.bd_action_score <= 1.0
        assert 0.0 <= result.bd_action_score_raw <= 1.0
        assert 0.0 <= result.bd_action_score_pre_confidence <= 1.0

    def test_pre_confidence_gte_final_when_high_confidence(self):
        result = _run(data_confidence=DataConfidence.HIGH)
        assert result.bd_action_score_pre_confidence >= result.bd_action_score - 1e-9

    def test_n_drivers_non_negative(self):
        result = _run()
        assert result.n_drivers >= 0

    def test_driver_names_length_matches_n_drivers(self):
        result = _run()
        assert len(result.driver_names) == result.n_drivers

    def test_interaction_bonuses_capped(self):
        result = _run(ta=_ta(score=1.0), dl=_dl(score=1.0), af=_af(score=1.0))
        assert result.interaction_bonuses_applied <= _BONUS_CAP + 1e-9

    def test_imbalance_penalty_non_negative(self):
        result = _run()
        assert result.imbalance_penalty_applied >= 0.0

    def test_classification_string_non_empty(self):
        result = _run()
        assert len(result.classification) > 0

    def test_recommended_action_non_empty(self):
        result = _run()
        assert len(result.recommended_action) > 0

    def test_reason_non_empty(self):
        result = _run()
        assert len(result.reason) > 0


# ---------------------------------------------------------------------------
# End-to-end integration
# ---------------------------------------------------------------------------

class TestComputeBDLayer2Integration:
    def test_high_all_scores_gives_active_pursuit(self):
        result = compute_bd_layer2(
            ta=_ta(score=0.85, scarcity=0.80),
            dl=_dl(score=0.80, financing_pressure=0.75, external_deal_activity=0.70,
                   insider_board_signals=0.50, catalyst_proximity=0.60),
            af=_af(score=0.85),
            data_confidence=DataConfidence.HIGH,
        )
        assert result.classification == BDActionClassification.ACTIVE_PURSUIT
        assert result.bd_action_score > 0.60

    def test_high_sp_low_tp_gives_watchlist(self):
        # SP = 0.45*0.85 + 0.35*0.80 + 0.20*0.75 = 0.8125 → HIGH tier
        # TP must be < 0.40 → use very low DL and suppress all drivers
        # with dl.score=0.05 and zero driver sub-scores:
        #   tp = 0.45*0.05 + 0.25*0.85 + 0.15*0.80 + 0.15*0 = 0.0225+0.2125+0.12 = 0.355 < 0.40
        result = compute_bd_layer2(
            ta=TargetAttractivenessScore(
                score=0.80, de_risking_stage=0.10, valuation_discount=0.10,
                scarcity=0.75, peak_sales_signal=0.70,
            ),
            dl=DealLikelihoodScore(
                score=0.05, financing_pressure=0.05, external_deal_activity=0.05,
                insider_board_signals=0.05, catalyst_proximity=0.05,
            ),
            af=_af(score=0.85),
        )
        assert result.classification == BDActionClassification.STRATEGIC_WATCHLIST
        assert result.strategic_priority >= _SP_HIGH

    def test_all_zeros_gives_zero_score(self):
        # Must zero out ALL sub-scores including de_risking_stage/valuation_discount
        # so that _count_transaction_drivers finds no drivers
        result = compute_bd_layer2(
            ta=TargetAttractivenessScore(
                score=0.0, de_risking_stage=0.0, valuation_discount=0.0,
                scarcity=0.0, peak_sales_signal=0.0,
            ),
            dl=DealLikelihoodScore(
                score=0.0, financing_pressure=0.0, external_deal_activity=0.0,
                insider_board_signals=0.0, catalyst_proximity=0.0,
            ),
            af=AcquirerFitDecomposed(
                score=0.0, ta_modality_fit=0.0, pipeline_gap_alignment=0.0,
                deal_affordability=0.0, existing_partnership_bonus=0.0,
            ),
        )
        assert result.bd_action_score == pytest.approx(0.0)
        assert result.strategic_priority == pytest.approx(0.0)
        assert result.transaction_probability == pytest.approx(0.0)

    def test_bonuses_only_when_convergence_real(self):
        """Bonuses are zero when scores are moderate."""
        result = compute_bd_layer2(
            ta=_ta(score=0.50, scarcity=0.50),
            dl=_dl(score=0.50),
            af=_af(score=0.50),
        )
        assert result.interaction_bonuses_applied == pytest.approx(0.0)

    def test_severe_imbalance_penalty_fires(self):
        result = compute_bd_layer2(
            ta=_ta(score=0.90, scarcity=0.85),
            dl=_dl(score=0.05),   # very weak DL
            af=_af(score=0.85),
        )
        assert result.imbalance_penalty_applied == pytest.approx(0.10)

    def test_medium_confidence_reduces_score(self):
        high = compute_bd_layer2(_ta(), _dl(), _af(), DataConfidence.HIGH)
        med = compute_bd_layer2(_ta(), _dl(), _af(), DataConfidence.MEDIUM)
        assert med.bd_action_score < high.bd_action_score

    def test_default_confidence_is_high(self):
        result = compute_bd_layer2(_ta(), _dl(), _af())
        assert result.data_confidence == DataConfidence.HIGH


# ---------------------------------------------------------------------------
# Backward compatibility: compute_mna_composite_score
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_returns_tuple_float_list(self):
        ta, dl, af = _ta(), _dl(), _af()
        result = compute_mna_composite_score(ta, dl, af)
        assert isinstance(result, tuple)
        assert len(result) == 2
        score, caps = result
        assert isinstance(score, float)
        assert isinstance(caps, list)

    def test_score_in_01(self):
        score, _ = compute_mna_composite_score(_ta(), _dl(), _af())
        assert 0.0 <= score <= 1.0

    def test_reason_codes_list_of_strings(self):
        _, caps = compute_mna_composite_score(_ta(), _dl(), _af())
        for c in caps:
            assert isinstance(c, str)

    def test_n_drivers_code_in_reason_codes(self):
        _, caps = compute_mna_composite_score(_ta(), _dl(), _af())
        assert any(c.startswith("n_drivers:") for c in caps)

    def test_financing_gate_codes_propagated(self):
        from bve.intelligence.ma_scoring import FINANCING_REASON_NOT_PRESSURED
        dl_gated = _dl(
            score=0.25,
            financing_pressure=0.10,
            financing_gate_applied=True,
            financing_reason_codes=[FINANCING_REASON_NOT_PRESSURED],
        )
        _, caps = compute_mna_composite_score(_ta(), dl_gated, _af())
        assert FINANCING_REASON_NOT_PRESSURED in caps
        assert "composite_capped_by_dl_gate" in caps

    def test_zero_drivers_code_present_when_no_drivers(self):
        # With very low sub-scores no drivers should fire
        ta = _ta(score=0.10, scarcity=0.10, valuation_discount=0.10, de_risking_stage=0.10)
        dl = _dl(score=0.10, financing_pressure=0.10, external_deal_activity=0.05,
                  insider_board_signals=0.05, catalyst_proximity=0.05)
        af = _af(score=0.10, pipeline_gap_alignment=0.10)
        _, caps = compute_mna_composite_score(ta, dl, af)
        assert "composite_capped_zero_drivers" in caps
