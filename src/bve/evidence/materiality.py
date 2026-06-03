"""
Materiality scoring for classified evidence events.

Produces a 0.0–1.0 score plus a tier (HIGH/MEDIUM/LOW/MINIMAL)
and a human-readable rationale string.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from bve.evidence.classifier import ClassificationResult, EventType
from bve.ingestion.raw_event import RawEvent


class MaterialityTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    MINIMAL = "MINIMAL"


class MaterialityScore(BaseModel):
    """Materiality scoring result for an evidence record."""

    model_config = {"frozen": True}

    score: float = Field(ge=0.0, le=1.0)
    tier: MaterialityTier
    rationale: str
    modifiers: list[str] = Field(default_factory=list)


_BASE_SCORES: dict[EventType, float] = {
    EventType.FDA_ACTION: 0.90,
    EventType.CATALYST_UPDATE: 0.80,
    EventType.PARTNERSHIP_MA: 0.70,
    EventType.FINANCING: 0.60,
    EventType.TRIAL_CHANGE: 0.50,
    EventType.COMPETITOR_EVENT: 0.45,
    EventType.MANAGEMENT_CHANGE: 0.40,
    EventType.EARNINGS: 0.35,
    EventType.REGULATORY_OTHER: 0.30,
    EventType.UNKNOWN: 0.10,
}


def _tier_from_score(score: float) -> MaterialityTier:
    if score >= 0.70:
        return MaterialityTier.HIGH
    if score >= 0.45:
        return MaterialityTier.MEDIUM
    if score >= 0.25:
        return MaterialityTier.LOW
    return MaterialityTier.MINIMAL


def _extract_all_text(payload: dict[str, Any]) -> str:
    """Extract all searchable text from payload (lowercase)."""
    text_fields = ["title", "summary", "description", "abstract", "text", "body"]
    parts: list[str] = []
    for field in text_fields:
        value = payload.get(field)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def score_materiality(
    raw_event: RawEvent,
    classification: ClassificationResult,
) -> MaterialityScore:
    """
    Compute a materiality score for a classified event.

    Base score comes from the EventType. Modifiers adjust up or down
    based on keywords found in the payload text.
    """
    event_type = classification.event_type
    base_score = _BASE_SCORES[event_type]

    text = _extract_all_text(raw_event.payload)
    applied_modifiers: list[str] = []
    delta = 0.0

    # FDA_ACTION modifiers
    if event_type == EventType.FDA_ACTION:
        if "approval" in text or "approved" in text:
            delta += 0.05
            applied_modifiers.append("+0.05: FDA approval keyword detected")
        if "crl" in text or "complete response" in text:
            delta -= 0.05
            applied_modifiers.append("-0.05: CRL/complete response detected")

    # CATALYST_UPDATE modifiers
    if event_type == EventType.CATALYST_UPDATE:
        if "phase 3" in text:
            delta += 0.05
            applied_modifiers.append("+0.05: Phase 3 trial data")
        if "phase 1" in text:
            delta -= 0.10
            applied_modifiers.append("-0.10: Phase 1 trial data (early stage)")
        if "endpoint met" in text or "positive" in text:
            delta += 0.05
            applied_modifiers.append("+0.05: Positive outcome keyword detected")
        if "missed" in text or "failed" in text or "negative" in text:
            delta += 0.05
            applied_modifiers.append("+0.05: Failure/negative outcome (still material)")

    # FINANCING modifiers
    if event_type == EventType.FINANCING:
        if "dilutive" in text:
            delta += 0.05
            applied_modifiers.append("+0.05: Dilutive financing detected")

    # Low-confidence penalty
    if classification.confidence < 0.5:
        delta -= 0.10
        applied_modifiers.append(
            f"-0.10: Low classification confidence ({classification.confidence:.2f})"
        )

    raw_score = base_score + delta
    final_score = min(1.0, max(0.0, raw_score))
    tier = _tier_from_score(final_score)

    rationale = _build_rationale(event_type, base_score, delta, final_score, tier)

    return MaterialityScore(
        score=final_score,
        tier=tier,
        rationale=rationale,
        modifiers=applied_modifiers,
    )


def _build_rationale(
    event_type: EventType,
    base_score: float,
    delta: float,
    final_score: float,
    tier: MaterialityTier,
) -> str:
    """Build a short human-readable rationale for the materiality score."""
    type_label = event_type.value.replace("_", " ").title()
    parts = [f"{type_label} event (base score {base_score:.2f})"]
    if delta > 0:
        parts.append(f"increased by modifiers (+{delta:.2f})")
    elif delta < 0:
        parts.append(f"reduced by modifiers ({delta:.2f})")
    parts.append(f"final score {final_score:.2f} → {tier.value} materiality")
    return "; ".join(parts) + "."


def resolve_affected_entities(
    raw_event: RawEvent,
    classification: ClassificationResult,  # noqa: ARG001
) -> list[str]:
    """
    Resolve the list of affected entity IDs for a raw event.

    Precedence:
    1. raw_event.entity_ids (if non-empty)
    2. payload["ticker"]
    3. payload["nct_id"]
    4. Empty list
    """
    if raw_event.entity_ids:
        return list(raw_event.entity_ids)

    entities: list[str] = []

    ticker = raw_event.payload.get("ticker")
    if isinstance(ticker, str) and ticker:
        entities.append(ticker)

    nct_id = raw_event.payload.get("nct_id")
    if isinstance(nct_id, str) and nct_id:
        entities.append(nct_id)

    return entities
