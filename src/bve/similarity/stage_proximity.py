"""
Ordinal stage proximity scoring for DevelopmentStage pairs.

Score = 1.0 - (ordinal_distance / max_possible_distance)

Stages in clinical order:
  PRECLINICAL=0, PHASE_1=1, PHASE_2=2, PHASE_3=3, NDA_BLA=4, APPROVED=5

Adjacent stages score 0.80; maximum distance (PRECLINICAL vs APPROVED) = 0.0.
"""
from __future__ import annotations

from bve.entities.asset import DevelopmentStage

_STAGE_ORDER: list[DevelopmentStage] = [
    DevelopmentStage.PRECLINICAL,
    DevelopmentStage.PHASE_1,
    DevelopmentStage.PHASE_2,
    DevelopmentStage.PHASE_3,
    DevelopmentStage.NDA_BLA,
    DevelopmentStage.APPROVED,
]

_MAX_DISTANCE: int = len(_STAGE_ORDER) - 1  # 5


def stage_proximity_score(a: DevelopmentStage, b: DevelopmentStage) -> float:
    """
    Return a score in [0.0, 1.0] reflecting how close two stages are.

    Symmetric: score(a, b) == score(b, a).
    Returns 0.0 for any unknown stage value.
    """
    try:
        idx_a = _STAGE_ORDER.index(a)
        idx_b = _STAGE_ORDER.index(b)
    except ValueError:
        return 0.0
    dist = abs(idx_a - idx_b)
    return round(1.0 - dist / _MAX_DISTANCE, 4)


def stage_ordinal(stage: DevelopmentStage) -> int:
    """Return the 0-based ordinal of a stage; -1 if unknown."""
    try:
        return _STAGE_ORDER.index(stage)
    except ValueError:
        return -1
