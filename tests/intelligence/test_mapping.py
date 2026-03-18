"""
Tests for bve.intelligence.mapping — MappingRule model and EVENT_PARAMETER_MAP.

Invariants validated:
  1. Every EventType has at least one MappingRule.
  2. No EventType is missing from the map.
  3. AUTO rules always have bound_pct set (not None).
  4. MANUAL rules always have bound_pct=None.
  5. BOUNDED rules have bound_pct in a sane range [5, 50].
  6. All parameter paths are members of LEGAL_PARAMETER_PATHS.
  7. MappingRule construction rejects bound/mode inconsistencies.
  8. Convenience helpers return correct subsets.
  9. Round-trip serialization of MappingRule is lossless.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bve.intelligence.taxonomy import ChangeMode, EventType
from bve.intelligence.mapping import (
    EVENT_PARAMETER_MAP,
    LEGAL_PARAMETER_PATHS,
    MappingRule,
    auto_rules,
    requires_review,
    rules_for,
)


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------

class TestMapCompleteness:
    def test_every_event_type_has_at_least_one_rule(self):
        for et in EventType:
            rules = EVENT_PARAMETER_MAP.get(et, [])
            assert len(rules) >= 1, (
                f"EventType.{et.name} has no MappingRule in EVENT_PARAMETER_MAP"
            )

    def test_no_extra_keys_in_map(self):
        """No EventType value should appear in the map that is not in the enum."""
        for key in EVENT_PARAMETER_MAP:
            assert isinstance(key, EventType), (
                f"Non-EventType key found in EVENT_PARAMETER_MAP: {key!r}"
            )

    def test_map_covers_all_20_event_types(self):
        assert set(EVENT_PARAMETER_MAP.keys()) == set(EventType)

    @pytest.mark.parametrize("et", list(EventType))
    def test_each_event_type_has_rules(self, et):
        rules = EVENT_PARAMETER_MAP[et]
        assert isinstance(rules, list)
        assert len(rules) >= 1


# ---------------------------------------------------------------------------
# Parameter path validity
# ---------------------------------------------------------------------------

class TestParameterPaths:
    def test_all_rule_parameters_are_legal(self):
        illegal = []
        for et, rules in EVENT_PARAMETER_MAP.items():
            for rule in rules:
                if rule.parameter not in LEGAL_PARAMETER_PATHS:
                    illegal.append((et.name, rule.parameter))
        assert not illegal, (
            f"Rules reference parameters outside LEGAL_PARAMETER_PATHS: {illegal}"
        )

    def test_legal_parameter_paths_is_frozenset(self):
        assert isinstance(LEGAL_PARAMETER_PATHS, frozenset)

    def test_legal_paths_count(self):
        """There are exactly 11 canonical parameter paths."""
        assert len(LEGAL_PARAMETER_PATHS) == 11


# ---------------------------------------------------------------------------
# Bound / mode invariants
# ---------------------------------------------------------------------------

class TestBoundModeInvariants:
    def test_auto_rules_have_bound_pct(self):
        violations = []
        for et, rules in EVENT_PARAMETER_MAP.items():
            for rule in rules:
                if rule.change_mode == ChangeMode.AUTO and rule.bound_pct is None:
                    violations.append((et.name, rule.parameter))
        assert not violations, f"AUTO rules without bound_pct: {violations}"

    def test_manual_rules_have_no_bound_pct(self):
        violations = []
        for et, rules in EVENT_PARAMETER_MAP.items():
            for rule in rules:
                if rule.change_mode == ChangeMode.MANUAL and rule.bound_pct is not None:
                    violations.append((et.name, rule.parameter, rule.bound_pct))
        assert not violations, f"MANUAL rules with bound_pct set: {violations}"

    def test_bounded_rules_have_sane_bound_pct(self):
        """BOUNDED bound_pct must be in [5, 50] — sanity range per spec."""
        violations = []
        for et, rules in EVENT_PARAMETER_MAP.items():
            for rule in rules:
                if rule.change_mode == ChangeMode.BOUNDED:
                    if rule.bound_pct is None or not (5.0 <= rule.bound_pct <= 50.0):
                        violations.append((et.name, rule.parameter, rule.bound_pct))
        assert not violations, (
            f"BOUNDED rules with bound_pct outside [5, 50]: {violations}"
        )

    def test_auto_rules_have_bound_pct_in_0_100(self):
        for et, rules in EVENT_PARAMETER_MAP.items():
            for rule in rules:
                if rule.change_mode == ChangeMode.AUTO:
                    assert 0.0 <= rule.bound_pct <= 100.0, (
                        f"{et.name}.{rule.parameter}: bound_pct={rule.bound_pct} out of [0,100]"
                    )

    def test_non_scalar_parameters_always_manual(self):
        """lifecycle_events and competition_model must always be MANUAL."""
        non_scalar = {
            "market_model.lifecycle_events",
            "market_model.competition_model",
        }
        for et, rules in EVENT_PARAMETER_MAP.items():
            for rule in rules:
                if rule.parameter in non_scalar:
                    assert rule.change_mode == ChangeMode.MANUAL, (
                        f"{et.name}.{rule.parameter} is non-scalar but has "
                        f"change_mode={rule.change_mode} (must be MANUAL)"
                    )


# ---------------------------------------------------------------------------
# MappingRule model validation
# ---------------------------------------------------------------------------

class TestMappingRuleValidation:
    def test_auto_without_bound_pct_raises(self):
        with pytest.raises(ValidationError):
            MappingRule(
                event_type=EventType.TRIAL_READOUT,
                parameter="trials[*].success_probability",
                change_mode=ChangeMode.AUTO,
                bound_pct=None,   # AUTO requires bound_pct
                rationale="Test",
            )

    def test_manual_with_bound_pct_raises(self):
        with pytest.raises(ValidationError):
            MappingRule(
                event_type=EventType.COMPETITOR_EVENT,
                parameter="market_model.competition_model",
                change_mode=ChangeMode.MANUAL,
                bound_pct=20.0,   # MANUAL must have bound_pct=None
                rationale="Test",
            )

    def test_bounded_without_bound_pct_raises(self):
        with pytest.raises(ValidationError):
            MappingRule(
                event_type=EventType.SAFETY_SIGNAL,
                parameter="trials[*].success_probability",
                change_mode=ChangeMode.BOUNDED,
                bound_pct=None,   # BOUNDED requires bound_pct
                rationale="Test",
            )

    def test_bound_pct_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            MappingRule(
                event_type=EventType.TRIAL_READOUT,
                parameter="trials[*].success_probability",
                change_mode=ChangeMode.AUTO,
                bound_pct=150.0,   # > 100
                rationale="Test",
            )

    def test_valid_auto_rule_constructs(self):
        rule = MappingRule(
            event_type=EventType.TRIAL_READOUT,
            parameter="trials[*].success_probability",
            change_mode=ChangeMode.AUTO,
            bound_pct=20.0,
            direction_hint="either",
            rationale="Test rule.",
        )
        assert rule.change_mode == ChangeMode.AUTO
        assert rule.bound_pct == 20.0

    def test_valid_manual_rule_constructs(self):
        rule = MappingRule(
            event_type=EventType.ENDPOINT_CHANGE,
            parameter="trials[*].success_probability",
            change_mode=ChangeMode.MANUAL,
            bound_pct=None,
            direction_hint="either",
            rationale="Endpoint change requires analyst judgment.",
        )
        assert rule.bound_pct is None

    def test_direction_hint_literal(self):
        with pytest.raises(ValidationError):
            MappingRule(
                event_type=EventType.TRIAL_READOUT,
                parameter="trials[*].success_probability",
                change_mode=ChangeMode.AUTO,
                bound_pct=10.0,
                direction_hint="sideways",   # not in Literal
                rationale="Test",
            )

    def test_round_trip_serialization(self):
        rule = MappingRule(
            event_type=EventType.FINANCING,
            parameter="asset.discount_rate",
            change_mode=ChangeMode.BOUNDED,
            bound_pct=10.0,
            direction_hint="either",
            rationale="Financing changes WACC.",
        )
        d = rule.model_dump()
        r2 = MappingRule.model_validate(d)
        assert r2 == rule
        assert r2.event_type is EventType.FINANCING
        assert r2.change_mode is ChangeMode.BOUNDED


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_rules_for_returns_correct_list(self):
        rules = rules_for(EventType.TRIAL_READOUT)
        assert isinstance(rules, list)
        assert len(rules) >= 1
        assert all(r.event_type == EventType.TRIAL_READOUT for r in rules)

    def test_auto_rules_filters_correctly(self):
        auto = auto_rules(EventType.TRIAL_READOUT)
        assert all(r.change_mode == ChangeMode.AUTO for r in auto)

    def test_requires_review_true_for_bounded(self):
        # SAFETY_SIGNAL has BOUNDED rules
        assert requires_review(EventType.SAFETY_SIGNAL) is True

    def test_requires_review_true_for_manual(self):
        # ENDPOINT_CHANGE has only MANUAL rules
        assert requires_review(EventType.ENDPOINT_CHANGE) is True

    def test_program_discontinuation_only_auto(self):
        """program_discontinuation has only AUTO rules — should not require review."""
        for rule in rules_for(EventType.PROGRAM_DISCONTINUATION):
            assert rule.change_mode == ChangeMode.AUTO
        # requires_review checks for MANUAL or BOUNDED only
        assert requires_review(EventType.PROGRAM_DISCONTINUATION) is False

    def test_rules_for_unknown_returns_empty(self):
        # Simulate a future unknown event type gracefully
        assert rules_for("nonexistent") == []   # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Specific event type spot checks
# ---------------------------------------------------------------------------

class TestSpotChecks:
    """Spot-check that high-stakes event types have the expected rules."""

    def test_fda_approval_sets_pos_to_auto_100(self):
        rules = [r for r in rules_for(EventType.FDA_APPROVAL)
                 if r.parameter == "trials[*].success_probability"]
        assert len(rules) == 1
        r = rules[0]
        assert r.change_mode == ChangeMode.AUTO
        assert r.bound_pct == 100.0
        assert r.direction_hint == "increase"

    def test_program_discontinuation_sets_pos_to_auto_100_decrease(self):
        rules = [r for r in rules_for(EventType.PROGRAM_DISCONTINUATION)
                 if r.parameter == "trials[*].success_probability"]
        assert len(rules) == 1
        r = rules[0]
        assert r.change_mode == ChangeMode.AUTO
        assert r.bound_pct == 100.0
        assert r.direction_hint == "decrease"

    def test_fda_rejection_sets_pos_to_auto_100_decrease(self):
        rules = [r for r in rules_for(EventType.FDA_REJECTION)
                 if r.parameter == "trials[*].success_probability"]
        assert len(rules) == 1
        assert rules[0].change_mode == ChangeMode.AUTO
        assert rules[0].direction_hint == "decrease"

    def test_label_expansion_has_lifecycle_events_manual_rule(self):
        rules = [r for r in rules_for(EventType.LABEL_EXPANSION)
                 if r.parameter == "market_model.lifecycle_events"]
        assert len(rules) == 1
        assert rules[0].change_mode == ChangeMode.MANUAL

    def test_regulatory_hold_has_duration_bounded_rule(self):
        rules = [r for r in rules_for(EventType.REGULATORY_HOLD)
                 if r.parameter == "trials[*].duration_years"]
        assert len(rules) == 1
        r = rules[0]
        assert r.change_mode == ChangeMode.BOUNDED
        assert r.direction_hint == "increase"
        assert r.bound_pct == 50.0   # high uncertainty warrants wide bound

    def test_enrollment_update_adjusts_duration_and_cost(self):
        params = {r.parameter for r in rules_for(EventType.ENROLLMENT_UPDATE)}
        assert "trials[*].duration_years" in params
        assert "trials[*].cost_millions" in params
