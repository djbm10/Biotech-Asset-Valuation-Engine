"""Catalyst payoff tree — scenario-weighted expected returns for upcoming catalysts."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class CatalystScenario(BaseModel):
    """A single outcome scenario for a catalyst event."""

    scenario_id: str
    label: str  # e.g. "clear_win"
    probability: float = Field(ge=0.0, le=1.0)
    expected_price_move_pct: float
    post_event_ev_millions: Optional[float] = None
    post_event_financing_state: str  # "no_need" | "bridge" | "follow_on" | "distressed"
    post_event_thesis_state: str  # "confirmed" | "partial" | "broken"
    next_catalyst: Optional[str] = None


class CatalystPayoffTree(BaseModel):
    """Expected-value tree for a single catalyst."""

    catalyst_id: str
    asset_id: str
    catalyst_label: str
    catalyst_date: date
    catalyst_type: str
    scenarios: list[CatalystScenario] = Field(default_factory=list)
    expected_return_pct: float
    downside_severity_pct: float
    skew_ratio: float
    setup_score: float = Field(ge=0.0, le=1.0)
    pre_event_recommendation: str
    post_event_action_map: dict[str, str] = Field(default_factory=dict)


class CatalystEVResult(BaseModel):
    """Aggregated EV result across all catalyst trees for an asset."""

    asset_id: str
    ticker: str
    trees: list[CatalystPayoffTree] = Field(default_factory=list)
    composite_expected_return_pct: float
    max_downside_pct: float
    best_risk_reward_catalyst_id: Optional[str] = None


class Catalyst(BaseModel):
    """A single upcoming catalyst event."""

    catalyst_id: str
    asset_id: str
    label: str
    expected_date: date
    catalyst_type: str
    importance: str  # "primary" | "secondary"
    source: str
