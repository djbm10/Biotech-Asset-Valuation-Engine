"""
Wave 1 Part A — Catalyst Calendar core data model.

CatalystEvent is the central artifact.  EV fields are populated by
CatalystEVCalculator and stored via KnowledgeStore.upsert_catalyst_event().
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CatalystType(str, Enum):
    PDUFA_DECISION       = "pdufa_decision"
    ADCOM_MEETING        = "adcom_meeting"
    TRIAL_READOUT        = "trial_readout"
    ENROLLMENT_COMPLETE  = "enrollment_complete"
    CONFERENCE_ABSTRACT  = "conference_abstract"
    COMPETITOR_READOUT   = "competitor_readout"


class CatalystEvent(BaseModel):
    """
    A single anticipated binary catalyst event and its associated EV metrics.

    EV fields
    ---------
    All Optional — absent until CatalystEVCalculator.compute() is called.

    signal_strength
        EV-to-risk ratio: ``delta_ev / std_floor``.  Analogous to a Sharpe ratio
        for a single binary bet.  Positive when the bet is EV-positive relative to
        risk; negative when the market price implies a richer probability than the
        model.

    asymmetry_ratio
        ``upside / downside``.  > 1 means the payoff is skewed toward success.
        ``inf`` when ``downside == 0`` (free option).
    """

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: Optional[str] = None
    company_id: Optional[str] = None
    catalyst_type: CatalystType
    expected_date: date
    date_confidence: Literal["exact", "quarter", "half_year", "estimate"]
    source: str
    description: str

    # EV fields (populated by CatalystEVCalculator)
    current_pos:        Optional[float] = None
    value_if_success:   Optional[float] = None
    value_if_failure:   Optional[float] = None
    current_value:      Optional[float] = None
    delta_ev:           Optional[float] = None
    upside:             Optional[float] = None
    downside:           Optional[float] = None
    std_dev:            Optional[float] = None
    signal_strength:    Optional[float] = None
    asymmetry_ratio:    Optional[float] = None

    # Lifecycle
    is_active:      bool = True
    resolved:       bool = False
    actual_outcome: Optional[Literal["positive", "negative", "partial"]] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
