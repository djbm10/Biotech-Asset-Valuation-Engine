"""Tests for stage proximity scoring."""
import pytest
from bve.entities.asset import DevelopmentStage
from bve.similarity.stage_proximity import stage_proximity_score, stage_ordinal


class TestStageProximityScore:
    def test_same_stage_returns_1(self):
        for stage in DevelopmentStage:
            assert stage_proximity_score(stage, stage) == 1.0

    def test_adjacent_stages_score_0_8(self):
        assert stage_proximity_score(DevelopmentStage.PHASE_1, DevelopmentStage.PHASE_2) == 0.8
        assert stage_proximity_score(DevelopmentStage.PHASE_2, DevelopmentStage.PHASE_3) == 0.8

    def test_two_apart_score_0_6(self):
        assert stage_proximity_score(DevelopmentStage.PHASE_1, DevelopmentStage.PHASE_3) == 0.6

    def test_max_distance_returns_0(self):
        assert stage_proximity_score(DevelopmentStage.PRECLINICAL, DevelopmentStage.APPROVED) == 0.0

    def test_symmetry(self):
        stages = list(DevelopmentStage)
        for i, a in enumerate(stages):
            for b in stages[i:]:
                assert stage_proximity_score(a, b) == stage_proximity_score(b, a)

    def test_preclinical_vs_phase1(self):
        assert stage_proximity_score(DevelopmentStage.PRECLINICAL, DevelopmentStage.PHASE_1) == 0.8

    def test_phase3_vs_nda(self):
        assert stage_proximity_score(DevelopmentStage.PHASE_3, DevelopmentStage.NDA_BLA) == 0.8

    def test_score_monotonically_decreases_with_distance(self):
        # Phase 2 as reference; distance to each stage should be monotonically correct
        ref = DevelopmentStage.PHASE_2
        assert (
            stage_proximity_score(ref, DevelopmentStage.PHASE_2)
            > stage_proximity_score(ref, DevelopmentStage.PHASE_3)
            > stage_proximity_score(ref, DevelopmentStage.NDA_BLA)
            > stage_proximity_score(ref, DevelopmentStage.APPROVED)
        )


class TestStageOrdinal:
    def test_ordinals_are_ordered(self):
        stages = [
            DevelopmentStage.PRECLINICAL,
            DevelopmentStage.PHASE_1,
            DevelopmentStage.PHASE_2,
            DevelopmentStage.PHASE_3,
            DevelopmentStage.NDA_BLA,
            DevelopmentStage.APPROVED,
        ]
        ordinals = [stage_ordinal(s) for s in stages]
        assert ordinals == sorted(ordinals)

    def test_all_stages_have_valid_ordinal(self):
        for stage in DevelopmentStage:
            assert stage_ordinal(stage) >= 0
