"""Biomedical knowledge graph linking targets, pathways, disease biology, and mechanism-level relationships."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class BiologicalNode(BaseModel):
    node_id: str
    node_type: str   # "target" / "pathway" / "disease" / "mechanism" / "biomarker" / "safety_liability"
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    source: str = "manual"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BiologicalEdge(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relationship: str  # "target_in_pathway" / "pathway_drives_disease" / "mechanism_activates_target"
                       # "mechanism_causes_liability" / "biomarker_predicts_response"
                       # "drug_hits_target" / "indication_uses_endpoint"
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    source: str = "manual"


class PathwayGraph:
    """In-memory biomedical knowledge graph with typed nodes and edges."""

    def __init__(self) -> None:
        self._nodes: dict[str, BiologicalNode] = {}
        self._edges: list[BiologicalEdge] = []

    def add_node(self, node: BiologicalNode) -> BiologicalNode:
        self._nodes[node.node_id] = node
        return node

    def add_edge(self, edge: BiologicalEdge) -> BiologicalEdge:
        self._edges.append(edge)
        return edge

    def get_node(self, node_id: str) -> Optional[BiologicalNode]:
        return self._nodes.get(node_id)

    def neighbors(self, node_id: str, relationship: Optional[str] = None) -> list[BiologicalNode]:
        """Return all nodes connected to node_id (optionally filtered by relationship type)."""
        connected_ids = [
            e.target_id for e in self._edges
            if e.source_id == node_id and (relationship is None or e.relationship == relationship)
        ] + [
            e.source_id for e in self._edges
            if e.target_id == node_id and (relationship is None or e.relationship == relationship)
        ]
        return [self._nodes[nid] for nid in connected_ids if nid in self._nodes]

    def find_by_type(self, node_type: str) -> list[BiologicalNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def targets_for_mechanism(self, mechanism_node_id: str) -> list[BiologicalNode]:
        return self.neighbors(mechanism_node_id, relationship="mechanism_activates_target")

    def liabilities_for_mechanism(self, mechanism_node_id: str) -> list[BiologicalNode]:
        return self.neighbors(mechanism_node_id, relationship="mechanism_causes_liability")

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return len(self._edges)
