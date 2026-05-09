"""Tests for the expanded SampleSizeAdequacy 6-tier table."""
from __future__ import annotations

import pytest

from bve.entities.asset import TherapeuticArea
from bve.entities.trial import TrialPhase
from bve.models.pos_model import (
    POSAdjusters,
    SampleSizeAdequacy,
    _SAMPLE_LOGODDS,
    compute_pos,
)


class TestSampleLogoddsValues:
    def test_well_powered_is_positive(self):
        assert _SAMPLE_LOGODDS[SampleSizeAdequacy.WELL_POWERED] == pytest.approx(+0.20)

    def test_adequate_is_zero_reference(self):
        assert _SAMPLE_LOGODDS[SampleSizeAdequacy.ADEQUATE] == 0.00

    def test_borderline_updated_to_minus_020(self):
        assert _SAMPLE_LOGODDS[SampleSizeAdequacy.BORDERLINE] == pytest.approx(-0.20)

    def test_underpowered_updated_to_minus_045(self):
        assert _SAMPLE_LOGODDS[SampleSizeAdequacy.UNDERPOWERED] == pytest.approx(-0.45)

    def test_unverifiable_at_minus_025(self):
        assert _SAMPLE_LOGODDS[SampleSizeAdequacy.UNVERIFIABLE] == pytest.approx(-0.25)

    def test_exploratory_most_negative(self):
        assert _SAMPLE_LOGODDS[SampleSizeAdequacy.EXPLORATORY] == pytest.approx(-0.50)

    def test_all_six_tiers_present(self):
        assert len(_SAMPLE_LOGODDS) == 6
        for tier in SampleSizeAdequacy:
            assert tier in _SAMPLE_LOGODDS, f"Missing: {tier}"


class TestSampleLogoddsOrdering:
    def test_descending_from_well_powered_to_exploratory(self):
        ordered = [
            SampleSizeAdequacy.WELL_POWERED,
            SampleSizeAdequacy.ADEQUATE,
            SampleSizeAdequacy.BORDERLINE,   # −0.20
            SampleSizeAdequacy.UNVERIFIABLE,  # −0.25
            SampleSizeAdequacy.UNDERPOWERED,  # −0.45
            SampleSizeAdequacy.EXPLORATORY,   # −0.50
        ]
        scores = [_SAMPLE_LOGODDS[t] for t in ordered]
        assert scores == sorted(scores, reverse=True)

    def test_unverifiable_between_borderline_and_underpowered(self):
        assert (
            _SAMPLE_LOGODDS[SampleSizeAdequacy.UNDERPOWERED]
            < _SAMPLE_LOGODDS[SampleSizeAdequacy.UNVERIFIABLE]
            < _SAMPLE_LOGODDS[SampleSizeAdequacy.ADEQUATE]
        )

    def test_exploratory_at_or_below_underpowered(self):
        assert (
            _SAMPLE_LOGODDS[SampleSizeAdequacy.EXPLORATORY]
            <= _SAMPLE_LOGODDS[SampleSizeAdequacy.UNDERPOWERED]
        )


class TestBackwardCompatibility:
    def test_well_powered_string_parseable(self):
        assert SampleSizeAdequacy("well_powered") == SampleSizeAdequacy.WELL_POWERED

    def test_adequate_string_parseable(self):
        assert SampleSizeAdequacy("adequate") == SampleSizeAdequacy.ADEQUATE

    def test_borderline_string_parseable(self):
        assert SampleSizeAdequacy("borderline") == SampleSizeAdequacy.BORDERLINE

    def test_underpowered_string_parseable(self):
        assert SampleSizeAdequacy("underpowered") == SampleSizeAdequacy.UNDERPOWERED

    def test_new_values_parseable(self):
        assert SampleSizeAdequacy("unverifiable") == SampleSizeAdequacy.UNVERIFIABLE
        assert SampleSizeAdequacy("exploratory") == SampleSizeAdequacy.EXPLORATORY


class TestPOSIntegration:
    """Verify tiers shift POS in correct direction at Phase 3 oncology baseline."""

    def _pos(self, tier: SampleSizeAdequacy) -> float:
        adj = POSAdjusters(sample_size_adequacy=tier)
        return compute_pos(TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY, adj)

    def test_well_powered_highest(self):
        assert self._pos(SampleSizeAdequacy.WELL_POWERED) > self._pos(SampleSizeAdequacy.ADEQUATE)

    def test_adequate_above_borderline(self):
        assert self._pos(SampleSizeAdequacy.ADEQUATE) > self._pos(SampleSizeAdequacy.BORDERLINE)

    def test_borderline_above_unverifiable(self):
        assert self._pos(SampleSizeAdequacy.BORDERLINE) > self._pos(SampleSizeAdequacy.UNVERIFIABLE)

    def test_unverifiable_above_underpowered(self):
        assert self._pos(SampleSizeAdequacy.UNVERIFIABLE) > self._pos(SampleSizeAdequacy.UNDERPOWERED)

    def test_underpowered_at_or_above_exploratory(self):
        assert self._pos(SampleSizeAdequacy.UNDERPOWERED) >= self._pos(SampleSizeAdequacy.EXPLORATORY)

    def test_exploratory_lowest(self):
        for tier in SampleSizeAdequacy:
            if tier != SampleSizeAdequacy.EXPLORATORY:
                assert self._pos(SampleSizeAdequacy.EXPLORATORY) <= self._pos(tier)

    def test_well_powered_vs_exploratory_gap_meaningful(self):
        """~14pp gap at oncology Phase 3 baseline is plausible."""
        gap = self._pos(SampleSizeAdequacy.WELL_POWERED) - self._pos(SampleSizeAdequacy.EXPLORATORY)
        assert 0.08 < gap < 0.25
