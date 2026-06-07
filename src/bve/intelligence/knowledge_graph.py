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
    MODALITY = "modality"
    FINANCING_STATE = "financing_state"
    MANAGEMENT_TEAM = "management_team"
    THESIS_SNAPSHOT = "thesis_snapshot"
    CATALYST = "catalyst"


class EdgeType(str, Enum):
    TREATS = "treats"
    TARGETS = "targets"
    COMPETES_WITH = "competes_with"
    COMPANY_OWNS_ASSET = "company_owns_asset"
    ASSET_TREATS_INDICATION = "asset_treats_indication"
    ASSET_TARGETS_TARGET = "asset_targets_target"
    HAS_MECHANISM = "has_mechanism"
    HAS_MODALITY = "has_modality"
    FINANCING_APPLIES_TO_COMPANY = "financing_applies_to_company"
    MANAGEMENT_RUNS_COMPANY = "management_runs_company"
    THESIS_SNAPSHOT_FOR_ASSET = "thesis_snapshot_for_asset"
    TRIAL_BELONGS_TO_ASSET = "trial_belongs_to_asset"
    COMPETITOR_OVERLAPS_ASSET = "competitor_overlaps_asset"
    CATALYST_FOR_ASSET = "catalyst_for_asset"
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
