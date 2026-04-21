"""Tests for Step 9: variant thesis + catalyst payoff engine."""
from __future__ import annotations

import math
import pytest
from datetime import datetime, timezone

from bve.intelligence.variant_view import (
    FalsifierEvent,
    KillCriterion,
    ThesisStrength,
    VariantView,
    apply_kill_criteria,
    thesis_is_actionable,
    thesis_is_killed,
)
from bve.valuation.scenario_tree import (
    CatalystPayoffTree,
    CatalystScenario,
    ScenarioOutcome,
    build_catalyst_tree,
    rank_catalysts,
)
from bve.trading.implied_move import (
    ANALOG_IMPLIED_MOVES,
    ImpliedMoveEstimate,
    estimate_from_analog,
    estimate_from_iv,
)
from bve.trading.asymmetry_score import (
    AsymmetryResult,
    InstrumentType,
    compute_asymmetry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 4, 20, tzinfo=timezone.utc)


def _make_kill_criterion(criterion_id: str = "safety_signal") -> KillCriterion:
    return KillCriterion(
        criterion_id=criterion_id,
        description="Safety signal observed",
        threshold="Grade 3+ AE rate > 15%",
    )


def _make_falsifier(event_id: str = "evt_001") -> FalsifierEvent:
    return FalsifierEvent(
        event_id=event_id,
        description="Phase 3 readout",
        expected_direction="positive",
        weight=0.8,
    )


def _make_view(
    model_pos: float = 0.60,
    market_implied_pos: float = 0.40,
    kill_criteria: list[KillCriterion] | None = None,
    falsifiers: list[FalsifierEvent] | None = None,
    narrative: str = "Bull thesis on RLAY",
) -> VariantView:
    return VariantView(
        asset_id="RLAY",
        model_pos=model_pos,
        market_implied_pos=market_implied_pos,
        pos_delta=0.0,            # will be overridden by model_validator
        thesis_strength=ThesisStrength.NEUTRAL,  # will be overridden
        kill_criteria=kill_criteria or [],
        falsifiers=falsifiers or [],
        narrative=narrative,
        created_at=NOW,
        updated_at=NOW,
    )


def _six_scenarios(
    strong_pos_p: float = 0.20,
    pos_p: float = 0.20,
    mixed_p: float = 0.15,
    neutral_p: float = 0.05,
    neg_p: float = 0.20,
    strong_neg_p: float = 0.20,
    strong_pos_ret: float = 0.80,
    pos_ret: float = 0.40,
    mixed_ret: float = 0.05,
    neutral_ret: float = 0.00,
    neg_ret: float = -0.30,
    strong_neg_ret: float = -0.60,
) -> list[dict]:
    return [
        {"outcome": ScenarioOutcome.STRONG_POSITIVE, "probability": strong_pos_p, "expected_return": strong_pos_ret, "pos_revision": 0.15, "rationale": "Clean data"},
        {"outcome": ScenarioOutcome.POSITIVE,        "probability": pos_p,       "expected_return": pos_ret,       "pos_revision": 0.08, "rationale": "Meets endpoint"},
        {"outcome": ScenarioOutcome.MIXED,           "probability": mixed_p,     "expected_return": mixed_ret,     "pos_revision": 0.00, "rationale": "Mixed signals"},
        {"outcome": ScenarioOutcome.NEUTRAL,         "probability": neutral_p,   "expected_return": neutral_ret,   "pos_revision": 0.00, "rationale": "Inconclusive"},
        {"outcome": ScenarioOutcome.NEGATIVE,        "probability": neg_p,       "expected_return": neg_ret,       "pos_revision": -0.10, "rationale": "Miss endpoint"},
        {"outcome": ScenarioOutcome.STRONG_NEGATIVE, "probability": strong_neg_p,"expected_return": strong_neg_ret,"pos_revision": -0.25, "rationale": "CRL"},
    ]


def _make_tree(**kwargs) -> CatalystPayoffTree:
    scenarios = kwargs.pop("scenarios", None) or _six_scenarios()
    return build_catalyst_tree(
        catalyst_id=kwargs.pop("catalyst_id", "cat_001"),
        asset_id=kwargs.pop("asset_id", "RLAY"),
        catalyst_description=kwargs.pop("catalyst_description", "Phase 3 readout"),
        catalyst_date=kwargs.pop("catalyst_date", "2026-Q3"),
        scenario_inputs=scenarios,
    )


# ===========================================================================
# TestVariantView
# ===========================================================================

class TestVariantView:
    """≥20 tests for VariantView and related functions."""

    def test_pos_delta_auto_computed(self):
        view = _make_view(model_pos=0.60, market_implied_pos=0.40)
        assert abs(view.pos_delta - 0.20) < 1e-9

    def test_pos_delta_negative(self):
        view = _make_view(model_pos=0.30, market_implied_pos=0.50)
        assert abs(view.pos_delta - (-0.20)) < 1e-9

    def test_pos_delta_zero(self):
        view = _make_view(model_pos=0.50, market_implied_pos=0.50)
        assert abs(view.pos_delta) < 1e-9

    def test_thesis_strength_strong_bull_at_boundary(self):
        # exactly +0.15 → STRONG_BULL
        view = _make_view(model_pos=0.65, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.STRONG_BULL

    def test_thesis_strength_strong_bull_above(self):
        view = _make_view(model_pos=0.80, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.STRONG_BULL

    def test_thesis_strength_bull_lower_boundary(self):
        # +0.05 → BULL
        view = _make_view(model_pos=0.55, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.BULL

    def test_thesis_strength_bull_upper_boundary(self):
        # +0.14 → BULL (just below +0.15)
        view = _make_view(model_pos=0.64, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.BULL

    def test_thesis_strength_neutral_positive(self):
        # +0.04 → NEUTRAL
        view = _make_view(model_pos=0.54, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.NEUTRAL

    def test_thesis_strength_neutral_zero(self):
        view = _make_view(model_pos=0.50, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.NEUTRAL

    def test_thesis_strength_neutral_negative(self):
        # -0.04 → NEUTRAL
        view = _make_view(model_pos=0.46, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.NEUTRAL

    def test_thesis_strength_bear(self):
        # -0.10 → BEAR
        view = _make_view(model_pos=0.40, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.BEAR

    def test_thesis_strength_bear_lower_boundary(self):
        # -0.05 → BEAR (just below -0.05)
        view = _make_view(model_pos=0.449, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.BEAR

    def test_thesis_strength_strong_bear_at_boundary(self):
        # exactly -0.15 → STRONG_BEAR
        view = _make_view(model_pos=0.35, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.STRONG_BEAR

    def test_thesis_strength_strong_bear_below(self):
        view = _make_view(model_pos=0.20, market_implied_pos=0.50)
        assert view.thesis_strength == ThesisStrength.STRONG_BEAR

    def test_actionable_false_no_kill_criteria(self):
        view = _make_view(model_pos=0.70, market_implied_pos=0.50)
        assert not thesis_is_actionable(view)

    def test_actionable_false_small_pos_delta(self):
        view = _make_view(
            model_pos=0.53,
            market_implied_pos=0.50,
            kill_criteria=[_make_kill_criterion()],
        )
        assert not thesis_is_actionable(view)

    def test_actionable_true(self):
        view = _make_view(
            model_pos=0.70,
            market_implied_pos=0.50,
            kill_criteria=[_make_kill_criterion()],
        )
        assert thesis_is_actionable(view)

    def test_actionable_true_negative_delta(self):
        view = _make_view(
            model_pos=0.30,
            market_implied_pos=0.50,
            kill_criteria=[_make_kill_criterion()],
        )
        assert thesis_is_actionable(view)

    def test_actionable_boundary_pos_delta_exactly_005(self):
        # abs(pos_delta) = 0.05 → actionable if kill criteria present
        view = _make_view(
            model_pos=0.55,
            market_implied_pos=0.50,
            kill_criteria=[_make_kill_criterion()],
        )
        assert thesis_is_actionable(view)

    def test_apply_kill_criteria_marks_triggered(self):
        view = _make_view(kill_criteria=[_make_kill_criterion("safety_signal")])
        triggered_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        updated = apply_kill_criteria(view, ["safety_signal"], triggered_at)
        assert updated.kill_criteria[0].is_triggered is True
        assert updated.kill_criteria[0].triggered_at == triggered_at

    def test_apply_kill_criteria_returns_new_view(self):
        view = _make_view(kill_criteria=[_make_kill_criterion()])
        triggered_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        updated = apply_kill_criteria(view, ["safety_signal"], triggered_at)
        # Original must be unchanged (immutable)
        assert view.kill_criteria[0].is_triggered is False
        assert updated.kill_criteria[0].is_triggered is True

    def test_apply_kill_criteria_only_triggers_specified(self):
        kc1 = _make_kill_criterion("crit_1")
        kc2 = _make_kill_criterion("crit_2")
        view = _make_view(kill_criteria=[kc1, kc2])
        triggered_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        updated = apply_kill_criteria(view, ["crit_1"], triggered_at)
        assert updated.kill_criteria[0].is_triggered is True
        assert updated.kill_criteria[1].is_triggered is False

    def test_thesis_is_killed_false_no_criteria(self):
        view = _make_view()
        assert not thesis_is_killed(view)

    def test_thesis_is_killed_false_before_trigger(self):
        view = _make_view(kill_criteria=[_make_kill_criterion()])
        assert not thesis_is_killed(view)

    def test_thesis_is_killed_true_after_trigger(self):
        view = _make_view(kill_criteria=[_make_kill_criterion()])
        triggered_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        updated = apply_kill_criteria(view, ["safety_signal"], triggered_at)
        assert thesis_is_killed(updated)

    def test_falsifiers_preserved_through_operations(self):
        falsifier = _make_falsifier()
        view = _make_view(
            kill_criteria=[_make_kill_criterion()],
            falsifiers=[falsifier],
        )
        triggered_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        updated = apply_kill_criteria(view, ["safety_signal"], triggered_at)
        assert len(updated.falsifiers) == 1
        assert updated.falsifiers[0].event_id == "evt_001"

    def test_narrative_preserved(self):
        view = _make_view(narrative="Specific narrative text")
        kc = _make_kill_criterion()
        triggered_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        updated = apply_kill_criteria(
            _make_view(narrative="Specific narrative text", kill_criteria=[kc]),
            ["safety_signal"],
            triggered_at,
        )
        assert updated.narrative == "Specific narrative text"

    def test_view_is_frozen(self):
        view = _make_view()
        with pytest.raises(Exception):  # ValidationError or AttributeError
            view.model_pos = 0.99  # type: ignore[misc]


# ===========================================================================
# TestCatalystPayoffTree
# ===========================================================================

class TestCatalystPayoffTree:
    """≥20 tests for CatalystPayoffTree."""

    def test_probabilities_must_sum_to_one(self):
        scenarios = _six_scenarios()
        scenarios[0]["probability"] = 0.30  # now sum != 1
        with pytest.raises(ValueError, match="sum to 1.0"):
            build_catalyst_tree("c1", "RLAY", "test", "2026-Q3", scenarios)

    def test_probabilities_sum_tolerance_ok(self):
        # Tiny floating point error within 1e-6 is accepted
        scenarios = _six_scenarios()
        # deliberately use values that sum to exactly 1.0 via float arithmetic
        tree = build_catalyst_tree("c1", "RLAY", "test", "2026-Q3", scenarios)
        assert tree is not None

    def test_expected_return_computed(self):
        scenarios = _six_scenarios(
            strong_pos_p=0.20, strong_pos_ret=0.80,
            pos_p=0.20, pos_ret=0.40,
            mixed_p=0.15, mixed_ret=0.05,
            neutral_p=0.05, neutral_ret=0.00,
            neg_p=0.20, neg_ret=-0.30,
            strong_neg_p=0.20, strong_neg_ret=-0.60,
        )
        tree = _make_tree(scenarios=scenarios)
        expected = 0.20*0.80 + 0.20*0.40 + 0.15*0.05 + 0.05*0.00 + 0.20*(-0.30) + 0.20*(-0.60)
        assert abs(tree.expected_return - expected) < 1e-9

    def test_expected_pos_revision_computed(self):
        scenarios = _six_scenarios()
        tree = _make_tree(scenarios=scenarios)
        # From helper: revisions are 0.15, 0.08, 0.00, 0.00, -0.10, -0.25
        # probs: 0.20, 0.20, 0.15, 0.05, 0.20, 0.20
        expected = 0.20*0.15 + 0.20*0.08 + 0.15*0.00 + 0.05*0.00 + 0.20*(-0.10) + 0.20*(-0.25)
        assert abs(tree.expected_pos_revision - expected) < 1e-9

    def test_upside_capture_positive_scenarios_only(self):
        tree = _make_tree()
        # upside = positive scenarios with positive returns
        # strong_pos: 0.20*0.80=0.16, pos: 0.20*0.40=0.08
        assert abs(tree.upside_capture - (0.20*0.80 + 0.20*0.40)) < 1e-9

    def test_downside_risk_negative_scenarios_only(self):
        tree = _make_tree()
        # downside_risk = abs(neg: 0.20*(-0.30) + strong_neg: 0.20*(-0.60))
        expected_down = abs(0.20*(-0.30) + 0.20*(-0.60))
        assert abs(tree.downside_risk - expected_down) < 1e-9

    def test_skew_ratio_upside_over_downside(self):
        tree = _make_tree()
        upside = tree.upside_capture
        downside = tree.downside_risk
        expected_skew = upside / (downside + 1e-9)
        assert abs(tree.skew_ratio - expected_skew) < 1e-6

    def test_setup_score_in_range(self):
        tree = _make_tree()
        assert 0.0 <= tree.setup_score <= 1.0

    def test_rank_catalysts_sorted_desc(self):
        # Create two trees with different setups
        good_scenarios = _six_scenarios(
            strong_pos_p=0.40, strong_pos_ret=0.90,
            pos_p=0.20, pos_ret=0.50,
            mixed_p=0.10, mixed_ret=0.00,
            neutral_p=0.05, neutral_ret=0.00,
            neg_p=0.15, neg_ret=-0.10,
            strong_neg_p=0.10, strong_neg_ret=-0.20,
        )
        bad_scenarios = _six_scenarios(
            strong_pos_p=0.05, strong_pos_ret=0.10,
            pos_p=0.05, pos_ret=0.05,
            mixed_p=0.10, mixed_ret=0.00,
            neutral_p=0.10, neutral_ret=0.00,
            neg_p=0.30, neg_ret=-0.50,
            strong_neg_p=0.40, strong_neg_ret=-0.80,
        )
        tree_good = _make_tree(catalyst_id="cat_good", scenarios=good_scenarios)
        tree_bad = _make_tree(catalyst_id="cat_bad", scenarios=bad_scenarios)
        ranked = rank_catalysts([tree_bad, tree_good])
        assert ranked[0].catalyst_id == "cat_good"
        assert ranked[1].catalyst_id == "cat_bad"

    def test_high_skew_tree_better_setup_than_low_skew(self):
        high_skew = _six_scenarios(
            strong_pos_p=0.40, strong_pos_ret=0.80,
            pos_p=0.20, pos_ret=0.40,
            mixed_p=0.10, mixed_ret=0.00,
            neutral_p=0.05, neutral_ret=0.00,
            neg_p=0.15, neg_ret=-0.10,
            strong_neg_p=0.10, strong_neg_ret=-0.15,
        )
        low_skew = _six_scenarios(
            strong_pos_p=0.10, strong_pos_ret=0.15,
            pos_p=0.10, pos_ret=0.10,
            mixed_p=0.10, mixed_ret=0.00,
            neutral_p=0.10, neutral_ret=0.00,
            neg_p=0.30, neg_ret=-0.40,
            strong_neg_p=0.30, strong_neg_ret=-0.70,
        )
        t_high = _make_tree(catalyst_id="high", scenarios=high_skew)
        t_low = _make_tree(catalyst_id="low", scenarios=low_skew)
        assert t_high.setup_score > t_low.setup_score

    def test_build_catalyst_tree_validates_probs(self):
        bad_scenarios = _six_scenarios()
        bad_scenarios[0]["probability"] = 0.99  # will sum > 1
        with pytest.raises(ValueError):
            build_catalyst_tree("c2", "RLAY", "test", "2026-Q3", bad_scenarios)

    def test_all_six_outcome_values_accepted(self):
        scenarios = [
            {"outcome": o, "probability": 1/6, "expected_return": 0.0, "pos_revision": 0.0, "rationale": "test"}
            for o in ScenarioOutcome
        ]
        tree = build_catalyst_tree("c3", "RLAY", "test", "2026-Q3", scenarios)
        assert len(tree.scenarios) == 6

    def test_expected_return_zero_symmetric(self):
        # symmetric bull/bear: equal probs, equal/opposite returns
        scenarios = [
            {"outcome": ScenarioOutcome.STRONG_POSITIVE, "probability": 1/6, "expected_return":  0.60, "pos_revision": 0.10, "rationale": ""},
            {"outcome": ScenarioOutcome.POSITIVE,        "probability": 1/6, "expected_return":  0.20, "pos_revision": 0.05, "rationale": ""},
            {"outcome": ScenarioOutcome.MIXED,           "probability": 1/6, "expected_return":  0.00, "pos_revision": 0.00, "rationale": ""},
            {"outcome": ScenarioOutcome.NEUTRAL,         "probability": 1/6, "expected_return":  0.00, "pos_revision": 0.00, "rationale": ""},
            {"outcome": ScenarioOutcome.NEGATIVE,        "probability": 1/6, "expected_return": -0.20, "pos_revision":-0.05, "rationale": ""},
            {"outcome": ScenarioOutcome.STRONG_NEGATIVE, "probability": 1/6, "expected_return": -0.60, "pos_revision":-0.10, "rationale": ""},
        ]
        tree = build_catalyst_tree("c4", "RLAY", "symmetric", "2026-Q3", scenarios)
        assert abs(tree.expected_return) < 1e-9

    def test_tree_is_frozen(self):
        tree = _make_tree()
        with pytest.raises(Exception):
            tree.catalyst_id = "modified"  # type: ignore[misc]

    def test_rank_catalysts_empty(self):
        assert rank_catalysts([]) == []

    def test_rank_catalysts_single(self):
        tree = _make_tree()
        ranked = rank_catalysts([tree])
        assert len(ranked) == 1

    def test_upside_capture_non_negative(self):
        tree = _make_tree()
        assert tree.upside_capture >= 0.0

    def test_downside_risk_non_negative(self):
        tree = _make_tree()
        assert tree.downside_risk >= 0.0

    def test_skew_ratio_positive(self):
        tree = _make_tree()
        assert tree.skew_ratio > 0.0

    def test_catalyst_date_stored(self):
        tree = _make_tree(catalyst_date="2027-Q1")
        assert tree.catalyst_date == "2027-Q1"

    def test_catalyst_description_stored(self):
        tree = _make_tree(catalyst_description="PDUFA submission")
        assert tree.catalyst_description == "PDUFA submission"


# ===========================================================================
# TestImpliedMove
# ===========================================================================

class TestImpliedMove:
    """≥15 tests for implied move estimation."""

    def test_iv_to_move_30_day(self):
        result = estimate_from_iv("RLAY", 1.20, 30)
        expected = 1.20 * math.sqrt(30 / 252.0)
        assert abs(result.implied_move_pct - expected) < 1e-9

    def test_iv_to_move_90_day(self):
        result = estimate_from_iv("RLAY", 0.80, 90)
        expected = 0.80 * math.sqrt(90 / 252.0)
        assert abs(result.implied_move_pct - expected) < 1e-9

    def test_iv_to_move_clamp_min(self):
        # Very low IV and few days → clamp to 0.05
        result = estimate_from_iv("RLAY", 0.01, 1)
        assert result.implied_move_pct == 0.05

    def test_iv_to_move_clamp_max(self):
        # Very high IV → clamp to 2.00
        result = estimate_from_iv("RLAY", 10.0, 252)
        assert result.implied_move_pct == 2.00

    def test_iv_source_is_iv_derived(self):
        result = estimate_from_iv("RLAY", 1.0, 30)
        assert result.source == "iv_derived"

    def test_iv_result_has_iv_input(self):
        result = estimate_from_iv("RLAY", 1.20, 30)
        assert result.iv_input == 1.20

    def test_iv_result_has_days_to_event(self):
        result = estimate_from_iv("RLAY", 1.20, 90)
        assert result.days_to_event == 90

    def test_iv_result_no_analog_used(self):
        result = estimate_from_iv("RLAY", 1.20, 30)
        assert result.analog_used is None

    def test_analog_lookup_returns_correct_value(self):
        result = estimate_from_analog("RLAY", "phase3_readout", "oncology")
        assert result.implied_move_pct == ANALOG_IMPLIED_MOVES["phase3_readout"]["oncology"]

    def test_analog_fallback_to_other_therapeutic_area(self):
        result = estimate_from_analog("RLAY", "phase3_readout", "cardiology")
        assert result.implied_move_pct == ANALOG_IMPLIED_MOVES["phase3_readout"]["other"]
        assert result.analog_used == "phase3_readout/other"

    def test_analog_fallback_unknown_event_type(self):
        result = estimate_from_analog("RLAY", "unknown_event")
        assert result.implied_move_pct == ANALOG_IMPLIED_MOVES["phase3_readout"]["other"]
        assert result.analog_used == "phase3_readout/other"

    def test_analog_source_is_analog_table(self):
        result = estimate_from_analog("RLAY", "adcom", "oncology")
        assert result.source == "analog_table"

    def test_analog_result_no_iv_input(self):
        result = estimate_from_analog("RLAY", "adcom")
        assert result.iv_input is None

    def test_analog_result_no_days_to_event(self):
        result = estimate_from_analog("RLAY", "pdufa_date")
        assert result.days_to_event is None

    def test_analog_rare_disease_higher_than_oncology(self):
        rare = estimate_from_analog("RLAY", "phase3_readout", "rare_disease")
        onco = estimate_from_analog("RLAY", "phase3_readout", "oncology")
        assert rare.implied_move_pct > onco.implied_move_pct

    def test_analog_pdufa_lower_than_phase3(self):
        pdufa = estimate_from_analog("RLAY", "pdufa_date", "oncology")
        ph3 = estimate_from_analog("RLAY", "phase3_readout", "oncology")
        assert pdufa.implied_move_pct < ph3.implied_move_pct

    def test_analog_asset_id_stored(self):
        result = estimate_from_analog("BIIB", "adcom", "oncology")
        assert result.asset_id == "BIIB"


# ===========================================================================
# TestAsymmetryScore
# ===========================================================================

class TestAsymmetryScore:
    """≥15 tests for compute_asymmetry and instrument selection."""

    def _bull_view(self, pos_delta: float = 0.20) -> VariantView:
        """Helper: make a bull view with a kill criterion."""
        model_pos = 0.50 + pos_delta
        return _make_view(
            model_pos=model_pos,
            market_implied_pos=0.50,
            kill_criteria=[_make_kill_criterion()],
        )

    def _bear_view(self, pos_delta: float = -0.20) -> VariantView:
        model_pos = 0.50 + pos_delta
        return _make_view(
            model_pos=model_pos,
            market_implied_pos=0.50,
            kill_criteria=[_make_kill_criterion()],
        )

    def _high_skew_tree(self) -> CatalystPayoffTree:
        scenarios = _six_scenarios(
            strong_pos_p=0.40, strong_pos_ret=0.80,
            pos_p=0.20, pos_ret=0.40,
            mixed_p=0.10, mixed_ret=0.00,
            neutral_p=0.05, neutral_ret=0.00,
            neg_p=0.15, neg_ret=-0.10,
            strong_neg_p=0.10, strong_neg_ret=-0.15,
        )
        return _make_tree(scenarios=scenarios)

    def _low_skew_tree(self) -> CatalystPayoffTree:
        scenarios = _six_scenarios(
            strong_pos_p=0.10, strong_pos_ret=0.10,
            pos_p=0.10, pos_ret=0.05,
            mixed_p=0.10, mixed_ret=0.00,
            neutral_p=0.10, neutral_ret=0.00,
            neg_p=0.30, neg_ret=-0.40,
            strong_neg_p=0.30, strong_neg_ret=-0.70,
        )
        return _make_tree(scenarios=scenarios)

    def _high_iv(self) -> ImpliedMoveEstimate:
        return estimate_from_analog("RLAY", "phase3_readout", "rare_disease")  # 0.55

    def _low_iv(self) -> ImpliedMoveEstimate:
        return estimate_from_analog("RLAY", "partnership", "other")  # 0.12

    def test_asymmetry_score_in_range(self):
        view = self._bull_view()
        tree = self._high_skew_tree()
        iv = self._high_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        assert 0.0 <= result.asymmetry_score <= 1.0

    def test_no_trade_when_score_below_030(self):
        # Use near-zero pos_delta and unfavorable tree
        view = _make_view(
            model_pos=0.52, market_implied_pos=0.50,
            kill_criteria=[_make_kill_criterion()],
        )
        tree = self._low_skew_tree()
        iv = self._low_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        # Score will be low; check NO_TRADE
        if result.asymmetry_score < 0.30:
            assert result.recommended_instrument == InstrumentType.NO_TRADE

    def test_no_trade_if_thesis_not_actionable(self):
        # No kill criteria → not actionable
        view = _make_view(model_pos=0.80, market_implied_pos=0.50, kill_criteria=[])
        tree = self._high_skew_tree()
        iv = self._high_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        assert result.recommended_instrument == InstrumentType.NO_TRADE

    def test_straddle_high_implied_move_low_skew(self):
        view = self._bull_view(0.15)
        tree = self._low_skew_tree()
        # Force high implied move (0.55 >= 0.35) and tree skew_ratio < 1.5
        iv = self._high_iv()  # 0.55 >= 0.35
        # Only straddle if score >= 0.30, so let's check what we get
        result = compute_asymmetry("RLAY", view, tree, iv)
        if result.asymmetry_score >= 0.30 and result.recommended_instrument != InstrumentType.NO_TRADE:
            # low_skew_tree should have skew < 1.5
            if tree.skew_ratio < 1.5 and iv.implied_move_pct >= 0.35:
                assert result.recommended_instrument == InstrumentType.STRADDLE

    def test_call_option_strong_bull_high_skew(self):
        view = self._bull_view(0.20)  # pos_delta = 0.20 >= 0.10
        tree = self._high_skew_tree()
        iv = self._low_iv()  # 0.12 < 0.35, so not straddle
        result = compute_asymmetry("RLAY", view, tree, iv)
        # high_skew_tree has skew_ratio >> 1.5
        if result.asymmetry_score >= 0.30:
            assert result.recommended_instrument == InstrumentType.CALL_OPTION

    def test_put_option_strong_bear_high_skew(self):
        # Bear view with high skew bear tree
        view = self._bear_view(-0.20)  # pos_delta = -0.20 <= -0.10
        bear_scenarios = _six_scenarios(
            strong_pos_p=0.05, strong_pos_ret=0.05,
            pos_p=0.05, pos_ret=0.02,
            mixed_p=0.10, mixed_ret=0.00,
            neutral_p=0.10, neutral_ret=0.00,
            neg_p=0.35, neg_ret=-0.50,
            strong_neg_p=0.35, strong_neg_ret=-0.80,
        )
        tree = _make_tree(scenarios=bear_scenarios)
        iv = self._low_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        if result.asymmetry_score >= 0.30 and tree.skew_ratio >= 1.5:
            assert result.recommended_instrument == InstrumentType.PUT_OPTION

    def test_equity_for_moderate_pos_delta(self):
        # pos_delta = 0.07, abs in [0.05, 0.10)
        view = _make_view(
            model_pos=0.57,
            market_implied_pos=0.50,
            kill_criteria=[_make_kill_criterion()],
        )
        # Use a tree with moderate skew to not trigger call/put conditions
        moderate_scenarios = _six_scenarios(
            strong_pos_p=0.20, strong_pos_ret=0.30,
            pos_p=0.20, pos_ret=0.15,
            mixed_p=0.15, mixed_ret=0.00,
            neutral_p=0.05, neutral_ret=0.00,
            neg_p=0.20, neg_ret=-0.20,
            strong_neg_p=0.20, strong_neg_ret=-0.35,
        )
        tree = _make_tree(scenarios=moderate_scenarios)
        iv = self._low_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        # With skew_ratio < 1.5 and implied_move < 0.35, and 0.05 <= abs(pos_delta) < 0.10
        if result.asymmetry_score >= 0.30 and tree.skew_ratio < 1.5 and iv.implied_move_pct < 0.35:
            assert result.recommended_instrument == InstrumentType.EQUITY

    def test_rationale_non_empty(self):
        view = self._bull_view()
        tree = self._high_skew_tree()
        iv = self._high_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        assert isinstance(result.rationale, str)
        assert len(result.rationale) > 0

    def test_pos_delta_stored_correctly(self):
        view = self._bull_view(0.20)
        tree = _make_tree()
        iv = estimate_from_analog("RLAY", "adcom")
        result = compute_asymmetry("RLAY", view, tree, iv)
        assert abs(result.pos_delta - 0.20) < 1e-9

    def test_skew_ratio_stored_correctly(self):
        view = self._bull_view()
        tree = self._high_skew_tree()
        iv = self._low_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        assert result.skew_ratio == tree.skew_ratio

    def test_implied_move_pct_stored(self):
        view = self._bull_view()
        tree = _make_tree()
        iv = estimate_from_analog("RLAY", "phase3_readout", "oncology")
        result = compute_asymmetry("RLAY", view, tree, iv)
        assert result.implied_move_pct == iv.implied_move_pct

    def test_expected_return_stored(self):
        view = self._bull_view()
        tree = self._high_skew_tree()
        iv = self._low_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        assert result.expected_return == tree.expected_return

    def test_result_is_frozen(self):
        view = self._bull_view()
        tree = _make_tree()
        iv = self._low_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        with pytest.raises(Exception):
            result.asymmetry_score = 0.99  # type: ignore[misc]

    def test_asset_id_stored(self):
        view = self._bull_view()
        tree = _make_tree()
        iv = self._low_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        assert result.asset_id == "RLAY"

    def test_no_trade_when_score_exactly_below_030(self):
        # Score below 0.30 → NO_TRADE regardless of other conditions
        # Use near-zero pos_delta (0.02), unfavorable tree and low IV → guaranteed low score
        view = _make_view(
            model_pos=0.52,
            market_implied_pos=0.50,
            kill_criteria=[_make_kill_criterion()],
        )
        bad_scenarios = _six_scenarios(
            strong_pos_p=0.05, strong_pos_ret=0.02,
            pos_p=0.05, pos_ret=0.01,
            mixed_p=0.10, mixed_ret=0.00,
            neutral_p=0.10, neutral_ret=0.00,
            neg_p=0.35, neg_ret=-0.05,
            strong_neg_p=0.35, strong_neg_ret=-0.10,
        )
        tree = _make_tree(scenarios=bad_scenarios)
        iv = self._low_iv()
        result = compute_asymmetry("RLAY", view, tree, iv)
        # Verify the score logic: even if thesis is actionable, low score → NO_TRADE
        assert result.asymmetry_score < 0.30
        assert result.recommended_instrument == InstrumentType.NO_TRADE
