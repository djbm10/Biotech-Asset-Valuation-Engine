"""
Tests for bve.intelligence.taxonomy — EventType and ChangeMode enums.
"""
import pytest
from bve.intelligence.taxonomy import ChangeMode, EventType


class TestEventType:
    """Taxonomy completeness and serialization."""

    EXPECTED_EVENT_TYPES = {
        "trial_readout",
        "interim_analysis",
        "enrollment_update",
        "endpoint_change",
        "safety_signal",
        "conference_presentation",
        "publication",
        "fda_approval",
        "fda_rejection",
        "fda_designation",
        "regulatory_hold",
        "label_expansion",
        "payer_coverage",
        "partnership",
        "financing",
        "sec_filing",
        "management_change",
        "competitor_event",
        "patent_event",
        "program_discontinuation",
    }

    def test_exactly_20_event_types(self):
        assert len(EventType) == 20

    def test_all_expected_values_present(self):
        actual = {e.value for e in EventType}
        assert actual == self.EXPECTED_EVENT_TYPES

    def test_no_value_collisions(self):
        values = [e.value for e in EventType]
        assert len(values) == len(set(values))

    def test_string_coercion_from_json(self):
        """String constructor must work for JSON ingestion."""
        assert EventType("trial_readout") is EventType.TRIAL_READOUT
        assert EventType("program_discontinuation") is EventType.PROGRAM_DISCONTINUATION

    def test_all_values_are_lowercase_snake_case(self):
        for e in EventType:
            assert e.value == e.value.lower(), f"{e.name} has mixed-case value: {e.value!r}"
            assert " " not in e.value, f"{e.name} has space in value: {e.value!r}"

    def test_round_trip_serialization(self):
        for e in EventType:
            assert EventType(e.value) is e

    @pytest.mark.parametrize("value", [
        "trial_readout", "fda_approval", "program_discontinuation", "label_expansion",
    ])
    def test_specific_members_accessible(self, value):
        e = EventType(value)
        assert isinstance(e, EventType)
        assert e.value == value

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            EventType("unknown_event_type")


class TestChangeMode:
    """ChangeMode enum — three canonical values."""

    def test_exactly_three_modes(self):
        assert len(ChangeMode) == 3

    def test_values_uppercase(self):
        assert ChangeMode.AUTO.value   == "AUTO"
        assert ChangeMode.BOUNDED.value == "BOUNDED"
        assert ChangeMode.MANUAL.value  == "MANUAL"

    def test_string_coercion(self):
        assert ChangeMode("AUTO")    is ChangeMode.AUTO
        assert ChangeMode("BOUNDED") is ChangeMode.BOUNDED
        assert ChangeMode("MANUAL")  is ChangeMode.MANUAL

    def test_round_trip(self):
        for mode in ChangeMode:
            assert ChangeMode(mode.value) is mode

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            ChangeMode("auto")   # wrong case
        with pytest.raises(ValueError):
            ChangeMode("SEMI_AUTO")
