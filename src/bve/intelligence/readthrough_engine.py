"""Readthrough engine — assesses how competitor events propagate to focal assets.

Heuristics applied by ReadthroughEngine.assess():
- readout_success for same mechanism/indication → positive readthrough
- readout_failure → negative readthrough
- discontinuation of the only remaining competitor → positive (class opens)
- safety event → negative class-level readthrough
- approval → positive (validates mechanism) unless same indication (negative: market taken)
- partnership → ambiguous (validates thesis, but competitor is now better resourced)
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ReadthroughEvent(BaseModel):
    """A competitor event that may propagate to the focal asset."""

    event_id: str
    competitor_asset_id: str
    event_type: str  # "readout_success" | "readout_failure" | "approval" | "crl" | "discontinuation" | "partnership" | "safety"
    event_date: date
    description: str
    materiality_score: float = Field(ge=0.0, le=1.0)


class ReadthroughResult(BaseModel):
    """Assessed readthrough impact on the focal asset."""

    focal_asset_id: str
    competitor_asset_id: str
    event: ReadthroughEvent
    readthrough_direction: str  # "positive" | "negative" | "ambiguous" | "class_expanding"
    magnitude: float = Field(ge=-1.0, le=1.0)
    rationale: str
    pos_delta: float = 0.0
    peak_sales_delta_pct: float = 0.0
    market_expansion_factor: float = 1.0


_POSITIVE_EVENTS = {"readout_success", "approval"}
_NEGATIVE_EVENTS = {"readout_failure", "crl", "safety"}
_AMBIGUOUS_EVENTS = {"partnership"}
_CLASS_POSITIVE_EVENTS = {"discontinuation"}


class ReadthroughEngine:
    """Applies simple heuristics to assess competitor event readthrough."""

    def assess(
        self,
        focal_asset_id: str,
        competitor_asset_id: str,
        event: ReadthroughEvent,
    ) -> ReadthroughResult:
        """Return a ReadthroughResult based on heuristic rules.

        Rules (in order):
        1. safety → negative, class-level
        2. discontinuation → positive (class opens)
        3. readout_success or approval → positive
        4. readout_failure or crl → negative
        5. partnership → ambiguous
        6. unknown event_type → ambiguous, zero magnitude
        """
        etype = event.event_type
        mat = event.materiality_score

        if etype == "safety":
            return ReadthroughResult(
                focal_asset_id=focal_asset_id,
                competitor_asset_id=competitor_asset_id,
                event=event,
                readthrough_direction="negative",
                magnitude=-mat,
                rationale="Class-level safety signal — negative readthrough to all assets in class.",
                pos_delta=-mat * 0.1,
                peak_sales_delta_pct=-mat * 0.05,
                market_expansion_factor=1.0 - mat * 0.05,
            )

        if etype == "discontinuation":
            return ReadthroughResult(
                focal_asset_id=focal_asset_id,
                competitor_asset_id=competitor_asset_id,
                event=event,
                readthrough_direction="positive",
                magnitude=mat * 0.5,
                rationale="Competitor discontinuation opens market share opportunity.",
                pos_delta=mat * 0.05,
                peak_sales_delta_pct=mat * 0.10,
                market_expansion_factor=1.0 + mat * 0.05,
            )

        if etype in _POSITIVE_EVENTS:
            return ReadthroughResult(
                focal_asset_id=focal_asset_id,
                competitor_asset_id=competitor_asset_id,
                event=event,
                readthrough_direction="positive",
                magnitude=mat * 0.6,
                rationale=f"Competitor {etype} validates mechanism/indication — positive class readthrough.",
                pos_delta=mat * 0.05,
                peak_sales_delta_pct=0.0,
                market_expansion_factor=1.0 + mat * 0.02,
            )

        if etype in _NEGATIVE_EVENTS:
            return ReadthroughResult(
                focal_asset_id=focal_asset_id,
                competitor_asset_id=competitor_asset_id,
                event=event,
                readthrough_direction="negative",
                magnitude=-mat * 0.5,
                rationale=f"Competitor {etype} raises class-level uncertainty — negative readthrough.",
                pos_delta=-mat * 0.05,
                peak_sales_delta_pct=-mat * 0.03,
                market_expansion_factor=1.0,
            )

        if etype in _AMBIGUOUS_EVENTS:
            return ReadthroughResult(
                focal_asset_id=focal_asset_id,
                competitor_asset_id=competitor_asset_id,
                event=event,
                readthrough_direction="ambiguous",
                magnitude=0.0,
                rationale="Partnership validates thesis but strengthens competitor — net ambiguous.",
                pos_delta=0.0,
                peak_sales_delta_pct=0.0,
                market_expansion_factor=1.0,
            )

        return ReadthroughResult(
            focal_asset_id=focal_asset_id,
            competitor_asset_id=competitor_asset_id,
            event=event,
            readthrough_direction="ambiguous",
            magnitude=0.0,
            rationale=f"Unknown event type '{etype}' — no readthrough assessed.",
            pos_delta=0.0,
            peak_sales_delta_pct=0.0,
            market_expansion_factor=1.0,
        )
