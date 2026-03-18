"""
Knowledge graph models for Wave 2A.

Defines node/edge types and Pydantic models used by KnowledgeStore
graph methods. No database logic lives here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NodeType(str, Enum):
    ASSET = "asset"
    COMPANY = "company"
    INDICATION = "indication"
    TARGET = "target"
    MECHANISM = "mechanism"
    TRIAL = "trial"
    COMPETITOR_PROGRAM = "competitor_program"


class EdgeType(str, Enum):
    TREATS = "treats"
    TARGETS = "targets"
    COMPETES_WITH = "competes_with"
    SAME_INDICATION = "same_indication"
    SAME_TARGET = "same_target"
    SAME_MECHANISM = "same_mechanism"
    SAME_TRIAL_PHASE = "same_trial_phase"
    SAME_ENDPOINT = "same_endpoint"
    SAME_POPULATION = "same_population"
    PARTNERED_WITH = "partnered_with"


class KGNode(BaseModel):
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_type: NodeType
    name: str
    external_id: Optional[str] = None  # asset_id, nct_id, company_id, etc.
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class KGEdge(BaseModel):
    edge_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)  # clamped [0, 1]
    source_signal_id: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
