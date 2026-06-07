"""Sprint 22 tests — acquirer-specific urgency weighting, BD pattern adjustments,
two-trigger requirement, reason codes, and strategic_fit cap rate <10%."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from bve.intelligence.ma_probability import (
    _GAP_URGENCY_MULTIPLIERS,
    _GAP_URGENCY_NONE_MULTIPLIER,
    _BD_PATTERN_BONUS_3_PLUS,
    _BD_PATTERN_PENALTY_ZERO,
    _STRATEGIC_FIT_HARD_CAP,
    _MNA_PROB_DUAL_GATE_CAP,
    _MNA_PROB_NO_TRIGGER_CAP,
    _MNA_PROB_HIGH_SCORE_FLOOR,
    _TRIGGER_FINANCING_MIN,
    _TRIGGER_EXTERNAL_MIN,
    _TRIGGER_ACTIVIST_MIN,
    _TRIGGER_VALUATION_MIN,
    _TRIGGER_DERISKING_MIN,
    _gap_urgency_for_match,
    _bd_pattern_adjustment,
    _apply_transaction_likelihood_gate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_acquirer(*, gaps=None, recent_deals=None):
    """Build a minimal AcquirerProfile-like namespace for unit tests."""
    if gaps is None:
        gaps = []
    if recent_deals is None:
        recent_deals = []

    gap_objs = []
    for g in gaps:
        gap_objs.append(SimpleNamespace(
            therapeutic_area=g["ta"],
            sub_area=g.get("sub_area"),
            exposure_level=g["urgency"],
        ))
    deal_objs = [SimpleNamespace() for _ in recent_deals]
    return SimpleNamespace(
        therapeutic_area_gaps=gap_objs,
        recent_deal_history=deal_objs,
    )


def _compute_strategic_fit_with_urgency(
    ta_score: float,
    modality_score: float,
    strategic_priority_score: float,
    budget_score: float,
    *,
    urgency_mult: float,
    bd_adj: float = 0.0,
    ta_weight: float = 0.25,
    modality_weight: float = 0.20,
    strat_weight: float = 0.15,
    budget_weight: float = 0.15,
) -> float:
    """Reproduce _strategic_fit_score logic (Sprint 22) for unit testing.

    Uses acquirer_fit.py v1.0 weights (ta=0.25, mod=0.20, strat=0.15, budget=0.15).
    """
    from bve.intelligence.ma_probability import (
        _STRATEGIC_FIT_HARD_CAP,
        _STRATEGIC_FIT_PENALTY_WEAK_TA,
        _STRATEGIC_FIT_PENALTY_POOR_MODALITY,
        _STRATEGIC_FIT_PENALTY_NO_PIPELINE_GAP,
        _STRATEGIC_FIT_PENALTY_POOR_DEAL_SIZE,
        _STRATEGIC_FIT_WEAK_TA_THRESHOLD,
        _STRATEGIC_FIT_POOR_MODALITY_THRESHOLD,
        _STRATEGIC_FIT_NO_GAP_THRESHOLD,
        _STRATEGIC_FIT_POOR_DEAL_SIZE_THRESHOLD,
    )
    strategic_weight = ta_weight + modality_weight + strat_weight + budget_weight
    if strategic_weight <= 0:
        return 0.0

    adjusted_ta_comp = ta_score * ta_weight * urgency_mult
    component = (
        adjusted_ta_comp
        + modality_score * modality_weight
        + strategic_priority_score * strat_weight
        + budget_score * budget_weight
    )
    base = min(max(component / strategic_weight, 0.0), 1.0)
    base = min(max(base + bd_adj, 0.0), 1.0)

    penalty = 0.0
    if ta_score < _STRATEGIC_FIT_WEAK_TA_THRESHOLD:
        penalty += _STRATEGIC_FIT_PENALTY_WEAK_TA
    if modality_score < _STRATEGIC_FIT_POOR_MODALITY_THRESHOLD:
        penalty += _STRATEGIC_FIT_PENALTY_POOR_MODALITY
    if strategic_priority_score < _STRATEGIC_FIT_NO_GAP_THRESHOLD:
        penalty += _STRATEGIC_FIT_PENALTY_NO_PIPELINE_GAP
    if budget_score < _STRATEGIC_FIT_POOR_DEAL_SIZE_THRESHOLD:
        penalty += _STRATEGIC_FIT_PENALTY_POOR_DEAL_SIZE

    penalized = max(base - penalty, 0.0)
    return round(min(penalized, _STRATEGIC_FIT_HARD_CAP), 6)


def _gate(score, *, fp=0.10, eda=0.10, activist=0.10,
          catalyst_days=None, vd=0.20, dr=0.40):
    result_score, reason_codes, _ = _apply_transaction_likelihood_gate(
        score,
        financing_pressure=fp,
        external_deal_activity=eda,
        activist_signal=activist,
        catalyst_days=catalyst_days,
        valuation_discount=vd,
        de_risking_stage=dr,
    )
    return result_score, reason_codes


# ---------------------------------------------------------------------------
# Gap urgency constants
# ---------------------------------------------------------------------------

class TestGapUrgencyConstants:
    def test_high_urgency_multiplier_is_one(self):
        assert _GAP_URGENCY_MULTIPLIERS["high"] == 1.00

    def test_medium_urgency_multiplier_below_high(self):
        assert _GAP_URGENCY_MULTIPLIERS["medium"] < _GAP_URGENCY_MULTIPLIERS["high"]

    def test_low_urgency_multiplier_below_medium(self):
        assert _GAP_URGENCY_MULTIPLIERS["low"] < _GAP_URGENCY_MULTIPLIERS["medium"]

    def test_none_multiplier_below_low(self):
        assert _GAP_URGENCY_NONE_MULTIPLIER <= _GAP_URGENCY_MULTIPLIERS["low"]

    def test_none_multiplier_positive(self):
        assert _GAP_URGENCY_NONE_MULTIPLIER > 0.0

    def test_bd_bonus_positive(self):
        assert _BD_PATTERN_BONUS_3_PLUS > 0.0

    def test_bd_penalty_negative(self):
        assert _BD_PATTERN_PENALTY_ZERO < 0.0

    def test_hard_cap_at_070(self):
        """Sprint 22: cap lowered to 0.70."""
        assert _STRATEGIC_FIT_HARD_CAP == 0.70


# ---------------------------------------------------------------------------
# _gap_urgency_for_match
# ---------------------------------------------------------------------------

class TestGapUrgencyForMatch:
    def test_high_urgency_exact_match(self):
        acquirer = _make_acquirer(gaps=[{"ta": "oncology", "urgency": "high"}])
        assert _gap_urgency_for_match(acquirer, "oncology") == "high"

    def test_medium_urgency_match(self):
        acquirer = _make_acquirer(gaps=[{"ta": "rare disease", "urgency": "medium"}])
        assert _gap_urgency_for_match(acquirer, "rare disease") == "medium"

    def test_low_urgency_match(self):
        acquirer = _make_acquirer(gaps=[{"ta": "dermatology", "urgency": "low"}])
        assert _gap_urgency_for_match(acquirer, "dermatology") == "low"

    def test_sub_area_label_match(self):
        acquirer = _make_acquirer(gaps=[
            {"ta": "oncology", "sub_area": "ADC", "urgency": "high"},
        ])
        assert _gap_urgency_for_match(acquirer, "oncology:ADC") == "high"

    def test_sub_area_full_label_required(self):
        """Partial label (no sub_area) does not match a gap with sub_area."""
        acquirer = _make_acquirer(gaps=[
            {"ta": "oncology", "sub_area": "ADC", "urgency": "high"},
        ])
        assert _gap_urgency_for_match(acquirer, "oncology") is None

    def test_no_acquirer_returns_none(self):
        assert _gap_urgency_for_match(None, "oncology") is None

    def test_no_matched_gap_returns_none(self):
        acquirer = _make_acquirer(gaps=[{"ta": "oncology", "urgency": "high"}])
        assert _gap_urgency_for_match(acquirer, None) is None

    def test_no_gap_match_returns_none(self):
        acquirer = _make_acquirer(gaps=[{"ta": "oncology", "urgency": "high"}])
        assert _gap_urgency_for_match(acquirer, "immunology") is None

    def test_first_matching_gap_returned(self):
        acquirer = _make_acquirer(gaps=[
            {"ta": "oncology", "urgency": "high"},
            {"ta": "immunology", "urgency": "low"},
        ])
        assert _gap_urgency_for_match(acquirer, "oncology") == "high"
        assert _gap_urgency_for_match(acquirer, "immunology") == "low"


# ---------------------------------------------------------------------------
# _bd_pattern_adjustment
# ---------------------------------------------------------------------------

class TestBdPatternAdjustment:
    def test_three_or_more_deals_gives_bonus(self):
        acquirer = _make_acquirer(recent_deals=[1, 2, 3])
        assert _bd_pattern_adjustment(acquirer) == _BD_PATTERN_BONUS_3_PLUS

    def test_five_deals_gives_bonus(self):
        acquirer = _make_acquirer(recent_deals=[1, 2, 3, 4, 5])
        assert _bd_pattern_adjustment(acquirer) == _BD_PATTERN_BONUS_3_PLUS

    def test_zero_deals_gives_penalty(self):
        acquirer = _make_acquirer(recent_deals=[])
        assert _bd_pattern_adjustment(acquirer) == _BD_PATTERN_PENALTY_ZERO

    def test_one_deal_neutral(self):
        acquirer = _make_acquirer(recent_deals=[1])
        assert _bd_pattern_adjustment(acquirer) == 0.0

    def test_two_deals_neutral(self):
        acquirer = _make_acquirer(recent_deals=[1, 2])
        assert _bd_pattern_adjustment(acquirer) == 0.0

    def test_none_acquirer_returns_zero(self):
        assert _bd_pattern_adjustment(None) == 0.0


# ---------------------------------------------------------------------------
# Strategic fit score — urgency effect
# ---------------------------------------------------------------------------

class TestStrategicFitUrgencyEffect:
    """Verify urgency multiplier produces genuine score differentiation."""

    # Typical all-good sub-scores (ta=0.80, mod=0.65, strat=1.00, budget=0.80)
    _TA = 0.80
    _MOD = 0.65
    _STRAT = 1.00
    _BUDGET = 0.80

    def _score(self, urgency_mult, bd_adj=0.0):
        return _compute_strategic_fit_with_urgency(
            self._TA, self._MOD, self._STRAT, self._BUDGET,
            urgency_mult=urgency_mult, bd_adj=bd_adj,
        )

    def test_high_urgency_capped_at_hard_cap(self):
        """With all-good sub-scores and high urgency, base > 0.70 → capped."""
        score = self._score(urgency_mult=_GAP_URGENCY_MULTIPLIERS["high"])
        assert score == _STRATEGIC_FIT_HARD_CAP

    def test_medium_urgency_below_cap(self):
        """With all-good sub-scores and medium urgency, base ≈ 0.68 < 0.70."""
        score = self._score(urgency_mult=_GAP_URGENCY_MULTIPLIERS["medium"])
        assert score < _STRATEGIC_FIT_HARD_CAP

    def test_low_urgency_substantially_below_cap(self):
        """With low urgency, base ≈ 0.61 — noticeably below cap."""
        score = self._score(urgency_mult=_GAP_URGENCY_MULTIPLIERS["low"])
        assert score < 0.65

    def test_no_gap_urgency_lowest_score(self):
        """No matched gap → lowest urgency multiplier → lowest score."""
        score = self._score(urgency_mult=_GAP_URGENCY_NONE_MULTIPLIER)
        assert score < 0.60

    def test_urgency_monotone_high_to_none(self):
        """Score decreases: high > medium > low > none."""
        scores = [
            self._score(urgency_mult=_GAP_URGENCY_MULTIPLIERS["high"]),
            self._score(urgency_mult=_GAP_URGENCY_MULTIPLIERS["medium"]),
            self._score(urgency_mult=_GAP_URGENCY_MULTIPLIERS["low"]),
            self._score(urgency_mult=_GAP_URGENCY_NONE_MULTIPLIER),
        ]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Not monotone at position {i}: {scores}"
            )

    def test_bd_bonus_increases_score(self):
        """Active BD (3+ deals) increases score vs neutral."""
        base = self._score(urgency_mult=_GAP_URGENCY_MULTIPLIERS["medium"])
        bonus = self._score(
            urgency_mult=_GAP_URGENCY_MULTIPLIERS["medium"],
            bd_adj=_BD_PATTERN_BONUS_3_PLUS,
        )
        assert bonus >= base

    def test_bd_penalty_decreases_score(self):
        """Zero BD history decreases score vs neutral."""
        base = self._score(urgency_mult=_GAP_URGENCY_MULTIPLIERS["medium"])
        penalized = self._score(
            urgency_mult=_GAP_URGENCY_MULTIPLIERS["medium"],
            bd_adj=_BD_PATTERN_PENALTY_ZERO,
        )
        assert penalized < base


# ---------------------------------------------------------------------------
# Strategic fit cap rate
# ---------------------------------------------------------------------------

class TestStrategicFitCapRate:
    """Verify cap rate <10% across a realistic acquirer-target population."""

    def test_cap_rate_below_10pct_realistic_population(self):
        """Realistic urgency mix: mostly medium → <10% at cap."""
        # Population: 12 pairs with realistic urgency and sub-score variation.
        # (urgency, ta, mod, strat, budget)
        population = [
            # high urgency — 2 out of 12 (16.7%); these may hit cap only if sub-scores perfect
            (_GAP_URGENCY_MULTIPLIERS["high"], 0.80, 0.65, 1.00, 0.80),  # at cap (all-good)
            (_GAP_URGENCY_MULTIPLIERS["high"], 0.60, 0.50, 0.70, 0.65),  # below cap (modest)
            # medium urgency — 6 out of 12 (typical)
            (_GAP_URGENCY_MULTIPLIERS["medium"], 0.80, 0.65, 1.00, 0.80),
            (_GAP_URGENCY_MULTIPLIERS["medium"], 0.70, 0.60, 0.90, 0.70),
            (_GAP_URGENCY_MULTIPLIERS["medium"], 0.65, 0.55, 0.80, 0.75),
            (_GAP_URGENCY_MULTIPLIERS["medium"], 0.80, 0.70, 0.65, 0.80),
            (_GAP_URGENCY_MULTIPLIERS["medium"], 0.50, 0.60, 0.70, 0.60),
            (_GAP_URGENCY_MULTIPLIERS["medium"], 0.70, 0.45, 0.65, 0.55),
            # low urgency — 2 out of 12
            (_GAP_URGENCY_MULTIPLIERS["low"], 0.75, 0.60, 0.80, 0.75),
            (_GAP_URGENCY_MULTIPLIERS["low"], 0.50, 0.50, 0.50, 0.50),
            # no gap — 2 out of 12
            (_GAP_URGENCY_NONE_MULTIPLIER, 0.80, 0.70, 0.90, 0.80),
            (_GAP_URGENCY_NONE_MULTIPLIER, 0.60, 0.55, 0.70, 0.60),
        ]
        scores = [
            _compute_strategic_fit_with_urgency(ta, mod, strat, budget, urgency_mult=um)
            for um, ta, mod, strat, budget in population
        ]
        n_at_cap = sum(1 for s in scores if s >= _STRATEGIC_FIT_HARD_CAP)
        cap_rate = n_at_cap / len(scores)
        assert cap_rate < 0.10, (
            f"Cap rate too high: {cap_rate:.1%} ({n_at_cap}/{len(scores)})\n"
            f"Scores: {[round(s, 3) for s in scores]}"
        )


# ---------------------------------------------------------------------------
# Transaction-likelihood gate — Sprint 22 changes
# ---------------------------------------------------------------------------

class TestTransactionGateNoTriggerCap:
    """Verify the no-trigger cap (new in Sprint 22)."""

    def test_no_triggers_caps_at_no_trigger_cap(self):
        """No trigger firing → score capped at _MNA_PROB_NO_TRIGGER_CAP."""
        score, codes = _gate(0.70, fp=0.10, eda=0.10, activist=0.10,
                             catalyst_days=None, vd=0.10, dr=0.20)
        assert score <= _MNA_PROB_NO_TRIGGER_CAP
        assert "missing_trigger:all" in codes

    def test_no_triggers_low_score_unaffected(self):
        """Score already ≤ 0.55 → no-trigger cap does not reduce it."""
        score, codes = _gate(0.40, fp=0.10, eda=0.10, activist=0.10,
                             catalyst_days=None, vd=0.10, dr=0.20)
        assert score == 0.40

    def test_dual_gate_and_no_trigger_same_cap(self):
        """Both caps are 0.55: dual gate + no-trigger converge on same value."""
        assert _MNA_PROB_DUAL_GATE_CAP == _MNA_PROB_NO_TRIGGER_CAP


class TestTransactionGateTwoDriverRequirement:
    """Verify that two transaction drivers are required to exceed 0.75."""

    def test_zero_triggers_capped_at_no_trigger_cap(self):
        score, codes = _gate(0.80, fp=0.10, eda=0.10, activist=0.10,
                             catalyst_days=None, vd=0.20, dr=0.40)
        # No triggers → no-trigger cap fires first
        assert score == _MNA_PROB_NO_TRIGGER_CAP

    def test_one_trigger_capped_at_floor(self):
        """Exactly 1 trigger → capped at high-score floor (0.75)."""
        # fp fires (1 trigger), eda low, no others
        score, codes = _gate(0.80, fp=_TRIGGER_FINANCING_MIN, eda=0.05,
                             activist=0.05, catalyst_days=None, vd=0.20, dr=0.40)
        assert score == _MNA_PROB_HIGH_SCORE_FLOOR
        assert "missing_trigger:second" in codes

    def test_two_triggers_allow_high_score(self):
        """Two triggers → score passes through unchanged (if dual gate doesn't fire)."""
        score, codes = _gate(0.80, fp=_TRIGGER_FINANCING_MIN,
                             eda=_TRIGGER_EXTERNAL_MIN,
                             activist=0.05, catalyst_days=None, vd=0.20, dr=0.40)
        assert score == 0.80
        assert codes == []

    def test_three_triggers_allow_high_score(self):
        """Three triggers → score is unaffected."""
        score, codes = _gate(0.85, fp=_TRIGGER_FINANCING_MIN,
                             eda=_TRIGGER_EXTERNAL_MIN,
                             activist=_TRIGGER_ACTIVIST_MIN, catalyst_days=None,
                             vd=0.20, dr=0.40)
        assert score == 0.85
        assert codes == []

    def test_catalyst_plus_financing_two_triggers(self):
        """Catalyst + financing pressure = 2 triggers → passes."""
        score, codes = _gate(0.80, fp=_TRIGGER_FINANCING_MIN, eda=0.05,
                             activist=0.05, catalyst_days=30,
                             vd=0.20, dr=0.40)
        assert score == 0.80
        assert codes == []

    def test_valuation_distress_plus_activist_two_triggers(self):
        """Valuation distress + activist signal = 2 triggers → passes.

        eda=0.25 is above the dual-gate threshold (0.20) so dual gate won't fire,
        but below the external-deal trigger threshold (0.30) so it doesn't count
        as a trigger — two triggers come from activist + valuation_distress.
        """
        score, codes = _gate(0.80, fp=0.10, eda=0.25,
                             activist=_TRIGGER_ACTIVIST_MIN,
                             catalyst_days=None,
                             vd=_TRIGGER_VALUATION_MIN, dr=_TRIGGER_DERISKING_MIN)
        assert score == 0.80
        assert codes == []


class TestTransactionGateReasonCodes:
    """Verify reason_codes accurately describe which gates fired."""

    def test_no_gate_fired_empty_codes(self):
        score, codes = _gate(0.50, fp=0.10, eda=0.10)
        assert codes == []

    def test_missing_trigger_all_when_no_triggers(self):
        score, codes = _gate(0.70, fp=0.10, eda=0.10, vd=0.10, dr=0.20)
        assert "missing_trigger:all" in codes

    def test_dual_gate_code_fires_when_both_low_pressure(self):
        score, codes = _gate(0.90, fp=0.10, eda=0.10)
        assert "dual_gate:low_pressure" in codes or "missing_trigger:all" in codes

    def test_missing_trigger_second_for_one_trigger_high_score(self):
        score, codes = _gate(0.80, fp=_TRIGGER_FINANCING_MIN, eda=0.05,
                             activist=0.05, catalyst_days=None, vd=0.20, dr=0.40)
        assert "missing_trigger:second" in codes

    def test_no_redundant_codes(self):
        """Reason codes list should not contain duplicates."""
        score, codes = _gate(0.90, fp=0.10, eda=0.10)
        assert len(codes) == len(set(codes)), f"Duplicate codes: {codes}"


class TestTransactionGateNewCaps:
    """Verify new Sprint 22 cap values."""

    def test_dual_gate_cap_tightened_to_055(self):
        assert _MNA_PROB_DUAL_GATE_CAP == 0.55

    def test_no_trigger_cap_at_055(self):
        assert _MNA_PROB_NO_TRIGGER_CAP == 0.55

    def test_high_score_floor_still_at_075(self):
        assert _MNA_PROB_HIGH_SCORE_FLOOR == 0.75

    def test_dual_gate_leq_high_score_floor(self):
        assert _MNA_PROB_DUAL_GATE_CAP <= _MNA_PROB_HIGH_SCORE_FLOOR
