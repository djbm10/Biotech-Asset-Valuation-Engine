"""
Event type classifier for raw ingestion events.

Uses deterministic rules only — no LLM calls.
Rules are applied in priority order when multiple keyword groups match.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from bve.ingestion.raw_event import RawEvent


class EventType(str, Enum):
    FINANCING = "FINANCING"
    CATALYST_UPDATE = "CATALYST_UPDATE"
    TRIAL_CHANGE = "TRIAL_CHANGE"
    FDA_ACTION = "FDA_ACTION"
    COMPETITOR_EVENT = "COMPETITOR_EVENT"
    MANAGEMENT_CHANGE = "MANAGEMENT_CHANGE"
    PARTNERSHIP_MA = "PARTNERSHIP_MA"
    EARNINGS = "EARNINGS"
    REGULATORY_OTHER = "REGULATORY_OTHER"
    UNKNOWN = "UNKNOWN"


# Priority order for tie-breaking (lower index = higher priority)
_PRIORITY_ORDER: list[EventType] = [
    EventType.FDA_ACTION,
    EventType.CATALYST_UPDATE,
    EventType.PARTNERSHIP_MA,
    EventType.FINANCING,
    EventType.TRIAL_CHANGE,
    EventType.COMPETITOR_EVENT,
    EventType.MANAGEMENT_CHANGE,
    EventType.EARNINGS,
    EventType.REGULATORY_OTHER,
    EventType.UNKNOWN,
]

_KEYWORD_RULES: dict[EventType, list[str]] = {
    EventType.FINANCING: [
        "offering",
        "raise",
        "atm program",
        "equity offering",
        "secondary offering",
        "dilut",
        "registered direct",
        "pipe",
        "convertible note",
        "credit facility",
        "cash runway",
    ],
    EventType.CATALYST_UPDATE: [
        "data",
        "results",
        "topline",
        "top-line",
        "readout",
        "efficacy",
        "endpoint met",
        "missed endpoint",
        "phase 2",
        "phase 3",
        "clinical trial results",
        "interim analysis",
        "primary endpoint",
    ],
    EventType.FDA_ACTION: [
        "fda",
        "pdufa",
        "approval",
        "approved",
        "nda",
        "bla",
        "breakthrough",
        "fast track",
        "orphan",
        "crl",
        "complete response",
        "advisory committee",
        "adcom",
        "label expansion",
    ],
    EventType.TRIAL_CHANGE: [
        "enrollment",
        "protocol amendment",
        "trial design",
        "dosing",
        "cohort",
        "arm",
        "randomized",
        "placebo",
        "investigational",
    ],
    EventType.COMPETITOR_EVENT: [
        "competitor",
        "rival",
        "competing",
        "class effect",
        "readthrough",
        "class data",
    ],
    EventType.MANAGEMENT_CHANGE: [
        "ceo",
        "chief executive",
        "cfo",
        "coo",
        "president",
        "board of directors",
        "appointed",
        "resigned",
        "departure",
    ],
    EventType.PARTNERSHIP_MA: [
        "partnership",
        "collaboration",
        "license",
        "acquisition",
        "merger",
        "deal",
        "agreement",
        "milestone",
        "royalty",
    ],
    EventType.EARNINGS: [
        "revenue",
        "earnings",
        "quarterly",
        "annual report",
        "financial results",
        "cash position",
        "burn rate",
        "operating expenses",
    ],
}


class ClassificationResult(BaseModel):
    """Result of classifying a raw event into an EventType."""

    model_config = {"frozen": True}

    event_type: EventType
    confidence: float = Field(ge=0.0, le=1.0)
    signals: list[str] = Field(default_factory=list)


def _extract_text(payload: dict[str, Any]) -> str:
    """Extract all searchable text from the payload (lowercase)."""
    text_fields = ["title", "summary", "description", "abstract", "text", "body"]
    parts: list[str] = []
    for field in text_fields:
        value = payload.get(field)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def _count_keyword_matches(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    """Return (match_count, matched_keywords) for a text and keyword list."""
    matched: list[str] = []
    for kw in keywords:
        if kw in text:
            matched.append(kw)
    return len(matched), matched


def _confidence_from_match_count(count: int) -> float:
    """Confidence score based on number of keyword matches."""
    if count >= 4:
        return 0.85
    if count >= 2:
        return 0.75
    if count == 1:
        return 0.60
    return 0.0


def classify(raw_event: RawEvent) -> ClassificationResult:
    """
    Classify a RawEvent into an EventType using deterministic rules.

    Rule priority:
    1. Source + record_type exact matches (highest confidence)
    2. Keyword matching in payload text fields
    3. Low-confidence source-level defaults
    4. UNKNOWN fallback
    """
    source = raw_event.source
    record_type = raw_event.record_type
    payload = raw_event.payload

    # --- Source + record_type exact rules ---

    if source == "openfda" and record_type == "drug_approval":
        return ClassificationResult(
            event_type=EventType.FDA_ACTION,
            confidence=0.95,
            signals=["source=openfda, record_type=drug_approval"],
        )

    if source == "openfda" and record_type == "drug_label":
        return ClassificationResult(
            event_type=EventType.FDA_ACTION,
            confidence=0.80,
            signals=["source=openfda, record_type=drug_label"],
        )

    if source == "ctgov" and record_type == "trial_study":
        return ClassificationResult(
            event_type=EventType.TRIAL_CHANGE,
            confidence=0.85,
            signals=["source=ctgov, record_type=trial_study"],
        )

    if source == "sec_edgar" and record_type in ("10_k", "10_q"):
        return ClassificationResult(
            event_type=EventType.EARNINGS,
            confidence=0.75,
            signals=[f"source=sec_edgar, record_type={record_type}"],
        )

    if source == "market_data":
        return ClassificationResult(
            event_type=EventType.UNKNOWN,
            confidence=0.0,
            signals=["source=market_data: not an event"],
        )

    # --- Keyword-based classification ---
    text = _extract_text(payload)

    # For open_payments, apply keyword matching but with lower base confidence
    is_open_payments = source == "open_payments"

    if text:
        # Count matches for each event type
        match_counts: dict[EventType, tuple[int, list[str]]] = {}
        for event_type, keywords in _KEYWORD_RULES.items():
            count, matched = _count_keyword_matches(text, keywords)
            if count > 0:
                match_counts[event_type] = (count, matched)

        if match_counts:
            # Find the maximum match count
            max_count = max(cnt for cnt, _ in match_counts.values())

            # Filter to event types with the max count (tie-breaking candidates)
            top_types = [
                et for et, (cnt, _) in match_counts.items() if cnt == max_count
            ]

            # Pick highest-priority type among ties
            best_type = min(
                top_types,
                key=lambda et: _PRIORITY_ORDER.index(et),
            )

            count, matched_keywords = match_counts[best_type]
            confidence = _confidence_from_match_count(count)

            if is_open_payments:
                # Reduce confidence for open_payments source
                confidence = min(confidence, 0.50)

            signals = [f"keyword match: '{kw}'" for kw in matched_keywords]
            return ClassificationResult(
                event_type=best_type,
                confidence=confidence,
                signals=signals,
            )

    # --- Source-level low-confidence defaults ---

    if source == "open_payments":
        # Without keyword matches, default to COMPETITOR_EVENT
        return ClassificationResult(
            event_type=EventType.COMPETITOR_EVENT,
            confidence=0.20,
            signals=["source=open_payments: default low-confidence"],
        )

    # --- Fallback ---
    return ClassificationResult(
        event_type=EventType.UNKNOWN,
        confidence=0.0,
        signals=[],
    )
