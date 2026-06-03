"""Scientific controversy and counterargument tracker for a drug asset thesis."""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ControversyType(str, Enum):
    TARGET_VALIDITY = "target_validity"  # Is the target druggable / causal?
    MECHANISM_DEBATE = "mechanism_debate"  # Competing mechanism hypotheses
    BIOMARKER_DISPUTE = "biomarker_dispute"  # Does the biomarker select responders?
    TRANSLATIONAL_GAP = "translational_gap"  # Animal → human translation concerns
    TRIAL_DESIGN_FLAW = "trial_design_flaw"  # Endpoint, population, or design weakness
    SAFETY_CONCERN = "safety_concern"  # Class or drug-specific safety signal
    COMPETITIVE_OBSOLESCENCE = "competitive_obsolescence"  # Better drug already exists


_SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 1.0,
    "high": 0.6,
    "medium": 0.3,
    "low": 0.1,
}


class Counterargument(BaseModel):
    counterargument_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    controversy_type: ControversyType
    argument: str  # The bearish / skeptical view
    rebuttal: Optional[str] = None  # Bull rebuttal if available
    source: str = ""  # Paper, analyst, management comment
    severity: str = "medium"  # "low" | "medium" | "high" | "critical"
    resolved: bool = False
    added_date: Optional[date] = None


class ControversyAssessment(BaseModel):
    asset_id: str
    total_counterarguments: int
    unresolved: int
    critical_count: int
    high_count: int
    controversy_score: float  # 0-1; higher = more contested thesis
    dominant_controversy: Optional[ControversyType] = None


class ControversyLayer:
    """In-memory scientific controversy tracker per asset."""

    def __init__(self) -> None:
        self._store: dict[str, Counterargument] = {}  # keyed by counterargument_id

    def add_counterargument(self, ca: Counterargument) -> None:
        """Persist a counterargument."""
        self._store[ca.counterargument_id] = ca

    def resolve(self, counterargument_id: str, rebuttal: str) -> None:
        """Mark a counterargument as resolved and attach a rebuttal.

        Raises KeyError if the counterargument_id is not found.
        """
        ca = self._store[counterargument_id]
        # Pydantic v2: use model_copy to derive updated instance (immutable-friendly)
        self._store[counterargument_id] = ca.model_copy(update={"resolved": True, "rebuttal": rebuttal})

    def get_for_asset(self, asset_id: str) -> list[Counterargument]:
        """Return all counterarguments for a given asset, newest (by insertion order) first."""
        return [ca for ca in self._store.values() if ca.asset_id == asset_id]

    def assess(self, asset_id: str) -> ControversyAssessment:
        """Compute a controversy assessment for the asset.

        Scoring formula (unresolved items only):
            numerator = critical*1.0 + high*0.6 + medium*0.3 + low*0.1
            controversy_score = min(1.0, numerator / max(1, total))

        dominant_controversy is the ControversyType with the most unresolved items.
        """
        all_cas = self.get_for_asset(asset_id)
        total = len(all_cas)

        unresolved_cas = [ca for ca in all_cas if not ca.resolved]
        unresolved = len(unresolved_cas)

        critical_count = sum(1 for ca in all_cas if ca.severity == "critical")
        high_count = sum(1 for ca in all_cas if ca.severity == "high")

        # Score based on unresolved items only
        numerator = sum(_SEVERITY_WEIGHTS.get(ca.severity, 0.3) for ca in unresolved_cas)
        controversy_score = min(1.0, numerator / max(1, total))

        dominant_controversy: Optional[ControversyType] = None
        if unresolved_cas:
            type_counts: Counter[ControversyType] = Counter(ca.controversy_type for ca in unresolved_cas)
            dominant_controversy = type_counts.most_common(1)[0][0]

        return ControversyAssessment(
            asset_id=asset_id,
            total_counterarguments=total,
            unresolved=unresolved,
            critical_count=critical_count,
            high_count=high_count,
            controversy_score=controversy_score,
            dominant_controversy=dominant_controversy,
        )

    def unresolved_critical(self, asset_id: str) -> list[Counterargument]:
        """Return all unresolved counterarguments with severity='critical' for the asset."""
        return [
            ca for ca in self.get_for_asset(asset_id)
            if not ca.resolved and ca.severity == "critical"
        ]
