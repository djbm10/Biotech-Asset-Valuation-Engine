"""Structured variant thesis for portfolio managers — model PoS vs market-implied PoS."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, model_validator


class ThesisStrength(str, Enum):
    STRONG_BULL = "strong_bull"    # model PoS >> market implied PoS (+15%+)
    BULL = "bull"                  # model PoS > market implied PoS (+5% to +15%)
    NEUTRAL = "neutral"            # within ±5%
    BEAR = "bear"                  # model PoS < market implied PoS (-5% to -15%)
    STRONG_BEAR = "strong_bear"    # model PoS << market implied PoS (-15%+)


def _strength_from_delta(pos_delta: float) -> ThesisStrength:
    if pos_delta >= 0.15:
        return ThesisStrength.STRONG_BULL
    if pos_delta >= 0.05:
        return ThesisStrength.BULL
    if pos_delta > -0.05:
        return ThesisStrength.NEUTRAL
    if pos_delta > -0.15:
        return ThesisStrength.BEAR
    return ThesisStrength.STRONG_BEAR


class KillCriterion(BaseModel, frozen=True):
    """A specific falsifiable condition that would invalidate the thesis."""
    criterion_id: str          # short slug, e.g. "safety_signal_grade3"
    description: str           # human-readable
    threshold: str             # what exactly triggers kill, e.g. "Grade 3+ AE rate > 15%"
    is_triggered: bool = False
    triggered_at: datetime | None = None


class FalsifierEvent(BaseModel, frozen=True):
    """An observable event that would falsify the variant view."""
    event_id: str
    description: str
    expected_direction: str    # "positive" or "negative" — what would CONFIRM the thesis
    weight: float              # 0.0-1.0, importance to the thesis


class VariantView(BaseModel, frozen=True):
    """
    Structured variant thesis for a single asset.
    Requires at least one kill criterion before a trade signal can be generated.
    """
    asset_id: str
    model_pos: float           # our model's probability of approval (0.0-1.0)
    market_implied_pos: float  # market-implied PoS from stock price (0.0-1.0)
    pos_delta: float           # model_pos - market_implied_pos (auto-computed)
    thesis_strength: ThesisStrength   # auto-computed from pos_delta
    kill_criteria: list[KillCriterion]
    falsifiers: list[FalsifierEvent]
    narrative: str             # free-text thesis summary
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def compute_derived(cls, data: dict) -> dict:
        model_pos = data.get("model_pos")
        market_implied_pos = data.get("market_implied_pos")
        if model_pos is not None and market_implied_pos is not None:
            pos_delta = round(model_pos - market_implied_pos, 10)
            data["pos_delta"] = pos_delta
            data["thesis_strength"] = _strength_from_delta(pos_delta)
        return data


def thesis_is_actionable(view: VariantView) -> bool:
    """Returns True only if thesis has >= 1 kill criterion AND pos_delta abs >= 0.05."""
    return len(view.kill_criteria) >= 1 and abs(view.pos_delta) >= 0.05


def apply_kill_criteria(
    view: VariantView,
    triggered_ids: list[str],
    triggered_at: datetime,
) -> VariantView:
    """Return updated VariantView with specified kill criteria marked triggered."""
    updated_criteria = []
    for kc in view.kill_criteria:
        if kc.criterion_id in triggered_ids:
            updated_criteria.append(
                KillCriterion(
                    criterion_id=kc.criterion_id,
                    description=kc.description,
                    threshold=kc.threshold,
                    is_triggered=True,
                    triggered_at=triggered_at,
                )
            )
        else:
            updated_criteria.append(kc)

    return VariantView(
        asset_id=view.asset_id,
        model_pos=view.model_pos,
        market_implied_pos=view.market_implied_pos,
        pos_delta=view.pos_delta,
        thesis_strength=view.thesis_strength,
        kill_criteria=updated_criteria,
        falsifiers=list(view.falsifiers),
        narrative=view.narrative,
        created_at=view.created_at,
        updated_at=triggered_at,
    )


def thesis_is_killed(view: VariantView) -> bool:
    """Returns True if any kill criterion is_triggered."""
    return any(kc.is_triggered for kc in view.kill_criteria)
