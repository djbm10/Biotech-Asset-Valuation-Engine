"""Buyer specification: hard requirements, ranking preferences, commercial diligence.

The three are deliberately separate objects so none can leak into another:

- ``problem`` is an S&E ``BuyerProblemV2`` and is the *only* input to eligibility.
- ``preferences`` order candidates; they never change a PASS/FAIL/UNKNOWN.
- ``commercial`` names the rights questions to ask; it never changes scientific status.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from bve.dealscreen.transaction import TransactionPreferences
from bve.se.schemas.contracts import PHASE_STAGE_ORDER, BuyerProblemV2


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    preferred_minimum_phase: str | None = "PHASE2"
    prefer_active_development: bool = True
    prefer_more_registered_trials: bool = True
    #: Modalities the buyer can already manufacture or deliver.
    buyer_capability_modalities: list[str] = Field(default_factory=list)
    relevant_market: str = "US"

    @model_validator(mode="after")
    def _phase(self) -> Preferences:
        if self.preferred_minimum_phase and self.preferred_minimum_phase.upper() not in PHASE_STAGE_ORDER:
            raise ValueError(f"unknown preferred phase {self.preferred_minimum_phase!r}")
        return self

    @property
    def preferred_stage_order(self) -> int | None:
        if not self.preferred_minimum_phase:
            return None
        return PHASE_STAGE_ORDER[self.preferred_minimum_phase.upper()]


class CommercialDiligence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_market: str = "US"
    questions: list[str] = Field(
        default_factory=lambda: [
            "Who owns the program and its U.S. development and commercialization rights?",
            "Are there existing licenses, options, co-development or co-promotion agreements?",
            "Is the owner explicitly seeking a partner for the U.S.?",
        ]
    )



class BuyerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(min_length=1)
    problem: BuyerProblemV2
    preferences: Preferences = Field(default_factory=Preferences)
    commercial: CommercialDiligence = Field(default_factory=CommercialDiligence)
    #: Optional buyer-declared transaction preferences (cycle C1 X5); never affect scientific gates.
    transaction: TransactionPreferences | None = None
    max_finalists: int = Field(default=10, ge=1, le=10)
    max_valuations: int = Field(default=3, ge=1, le=3)

    @classmethod
    def from_yaml(cls, path: str | Path) -> BuyerSpec:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"{path}: a buyer spec must be a YAML mapping")
        return cls(**data)
