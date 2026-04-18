"""Competition graph — nodes and edges for competitive landscape mapping."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CompetitionEdge(BaseModel):
    """Directed edge representing a competitive relationship between two assets."""

    edge_id: str
    source_asset_id: str
    target_asset_id: str
    relationship_type: str  # "same_indication" | "same_target" | "same_mechanism" | "same_modality" | "same_lot" | "adjacent"
    overlap_score: float = Field(ge=0.0, le=1.0)
    created_at: datetime


class CompetitionNode(BaseModel):
    """A single asset node in the competition graph."""

    asset_id: str
    ticker: str
    company_name: str
    indication: str
    target: Optional[str] = None
    mechanism: Optional[str] = None
    modality: Optional[str] = None
    stage: str
    status: str  # "active" | "approved" | "discontinued"
    approval_probability: Optional[float] = None


class CompetitionGraph(BaseModel):
    """Full competition graph centered on a focal asset."""

    graph_id: str
    asset_id: str
    focal_node: CompetitionNode
    competitor_nodes: list[CompetitionNode] = Field(default_factory=list)
    edges: list[CompetitionEdge] = Field(default_factory=list)
    built_at: datetime
    summary: str
