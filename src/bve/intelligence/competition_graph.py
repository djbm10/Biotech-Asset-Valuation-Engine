"""Competition graph — nodes and pairwise similarity scoring across 5 dimensions.

Similarity is computed using Jaccard overlap on tokenized field values.
Dimension weights: target=30%, mechanism=25%, indication=20%, lot=15%, modality=10%.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SimilarityDimension(str, Enum):
    TARGET = "target"
    MECHANISM = "mechanism"
    INDICATION = "indication"
    LOT = "lot"
    MODALITY = "modality"


# Weights must sum to 1.0
_DIMENSION_WEIGHTS: dict[str, float] = {
    SimilarityDimension.TARGET.value: 0.30,
    SimilarityDimension.MECHANISM.value: 0.25,
    SimilarityDimension.INDICATION.value: 0.20,
    SimilarityDimension.LOT.value: 0.15,
    SimilarityDimension.MODALITY.value: 0.10,
}

_DIRECT_COMPETITOR_THRESHOLD = 0.60


@dataclass(frozen=True)
class CompetitorNode:
    asset_id: str
    ticker: str
    target: str          # e.g. "PD-1", "VEGF", "KRAS G12C"
    mechanism: str       # e.g. "checkpoint_inhibitor", "ADC", "small_molecule"
    indication: str      # e.g. "NSCLC", "breast_cancer", "AML"
    lot: str             # e.g. "1L", "2L", "relapsed_refractory"
    modality: str        # e.g. "antibody", "small_molecule", "cell_therapy"
    phase: str           # e.g. "Phase 1", "Phase 2", "Phase 3", "Approved"
    approval_probability: float = 0.5


class SimilarityScore(BaseModel, frozen=True):
    asset_id_a: str
    asset_id_b: str
    dimension_scores: dict[str, float]  # SimilarityDimension.value -> 0.0-1.0
    composite_score: float
    is_direct_competitor: bool

    @field_validator("composite_score")
    @classmethod
    def _validate_composite(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"composite_score must be in [0.0, 1.0], got {v}")
        return v


def _tokenize(text: str) -> frozenset[str]:
    """Split on underscores, hyphens, and spaces then lowercase."""
    import re
    tokens = re.split(r"[_\-\s]+", text.lower())
    return frozenset(t for t in tokens if t)


def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity between token sets of two strings."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


class CompetitionGraph:
    """Stores CompetitorNodes and computes pairwise similarity on demand."""

    def __init__(self) -> None:
        self._nodes: dict[str, CompetitorNode] = {}

    def add_node(self, node: CompetitorNode) -> None:
        """Add or replace a node in the graph."""
        self._nodes[node.asset_id] = node

    def all_nodes(self) -> list[CompetitorNode]:
        """Return all nodes currently in the graph."""
        return list(self._nodes.values())

    def compute_similarity(self, a: CompetitorNode, b: CompetitorNode) -> SimilarityScore:
        """Compute weighted Jaccard similarity across all 5 dimensions."""
        dim_scores: dict[str, float] = {
            SimilarityDimension.TARGET.value: _jaccard(a.target, b.target),
            SimilarityDimension.MECHANISM.value: _jaccard(a.mechanism, b.mechanism),
            SimilarityDimension.INDICATION.value: _jaccard(a.indication, b.indication),
            SimilarityDimension.LOT.value: _jaccard(a.lot, b.lot),
            SimilarityDimension.MODALITY.value: _jaccard(a.modality, b.modality),
        }
        composite = sum(
            dim_scores[dim] * weight
            for dim, weight in _DIMENSION_WEIGHTS.items()
        )
        return SimilarityScore(
            asset_id_a=a.asset_id,
            asset_id_b=b.asset_id,
            dimension_scores=dim_scores,
            composite_score=composite,
            is_direct_competitor=composite >= _DIRECT_COMPETITOR_THRESHOLD,
        )

    def get_competitors(
        self, asset_id: str, min_score: float = 0.30
    ) -> list[SimilarityScore]:
        """Return similarity scores for all other assets with composite >= min_score.

        Results are sorted descending by composite_score.
        """
        node = self._nodes.get(asset_id)
        if node is None:
            return []

        results: list[SimilarityScore] = []
        for other_id, other_node in self._nodes.items():
            if other_id == asset_id:
                continue
            score = self.compute_similarity(node, other_node)
            if score.composite_score >= min_score:
                results.append(score)

        results.sort(key=lambda s: s.composite_score, reverse=True)
        return results

    def get_direct_competitors(self, asset_id: str) -> list[SimilarityScore]:
        """Return only assets with composite_score >= 0.60 (direct competitors)."""
        return self.get_competitors(asset_id, min_score=_DIRECT_COMPETITOR_THRESHOLD)


# ---------------------------------------------------------------------------
# Legacy Pydantic types — kept for backward compatibility with existing code
# that imports CompetitionEdge and CompetitionNode (Pydantic) by name.
# ---------------------------------------------------------------------------

class CompetitionEdge(BaseModel):
    """Directed edge representing a competitive relationship (legacy type)."""

    edge_id: str
    source_asset_id: str
    target_asset_id: str
    relationship_type: str
    overlap_score: float = Field(ge=0.0, le=1.0)
    created_at: datetime


class CompetitionNode(BaseModel):
    """A single asset node (legacy Pydantic type)."""

    asset_id: str
    ticker: str
    company_name: str
    indication: str
    target: Optional[str] = None
    mechanism: Optional[str] = None
    modality: Optional[str] = None
    stage: str
    status: str
    approval_probability: Optional[float] = None
