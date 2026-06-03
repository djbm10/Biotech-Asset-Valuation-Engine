"""Ingest raw events from external feeds and classify them for the asset universe."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class RawFeedEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str  # "sec_filing" / "press_release" / "clinicaltrials" / "fda" / "pubmed" / "news"
    asset_id: Optional[str] = None
    ticker: Optional[str] = None
    headline: str
    body: Optional[str] = None
    published_at: datetime
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    url: Optional[str] = None
    raw_payload: dict = Field(default_factory=dict)


class ClassifiedEvent(BaseModel):
    event_id: str
    source: str
    asset_id: Optional[str] = None
    ticker: Optional[str] = None
    event_type: str  # "trial_update" / "financing" / "fda_action" / "competitor_event" / "safety" / "partnership" / "earnings" / "other"
    materiality_score: float = Field(ge=0.0, le=1.0)
    headline: str
    classified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dedupe_key: str  # hash of (source, headline[:80])
    is_duplicate: bool = False


def _dedupe_key(source: str, headline: str) -> str:
    """Compute a deduplication key from source and first 80 chars of headline."""
    raw = f"{source}:{headline[:80]}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _classify_event_type(headline_lower: str) -> str:
    """Classify event type from headline using keyword heuristics."""
    if any(kw in headline_lower for kw in ("fda", "approval", "nda", "bla", "pdufa", "breakthrough designation")):
        return "fda_action"
    if any(kw in headline_lower for kw in ("phase 3", "phase iii", "phase 2", "phase ii", "phase 1", "phase i", "trial results", "clinical trial", "trial update", "enrollment")):
        return "trial_update"
    if any(kw in headline_lower for kw in ("safety", "adverse", "toxicity", "side effect", "warning", "black box")):
        return "safety"
    if any(kw in headline_lower for kw in ("financing", "offering", "raises", "capital raise", "private placement", "public offering", "ipo", "follow-on")):
        return "financing"
    if any(kw in headline_lower for kw in ("partnership", "collaboration", "license", "agreement", "deal")):
        return "partnership"
    if any(kw in headline_lower for kw in ("earnings", "revenue", "quarterly", "q1", "q2", "q3", "q4", "annual results")):
        return "earnings"
    if any(kw in headline_lower for kw in ("competitor", "rival", "competing")):
        return "competitor_event"
    return "other"


def _classify_materiality(headline_lower: str, event_type: str) -> float:
    """Compute materiality score from headline keywords and event type."""
    if event_type == "fda_action":
        return 0.9
    if event_type == "safety":
        return 0.8
    if any(kw in headline_lower for kw in ("phase 3", "phase iii", "trial results", "fda")):
        return 0.9
    if any(kw in headline_lower for kw in ("phase 2", "phase ii", "interim")):
        return 0.7
    if event_type == "partnership":
        return 0.65
    if event_type == "financing":
        return 0.6
    if event_type in ("trial_update",):
        return 0.7
    if event_type in ("earnings",):
        return 0.5
    return 0.3


class NewsMonitor:
    """Fetch, classify, and deduplicate events from external feeds."""

    def __init__(self) -> None:
        self._seen_keys: set[str] = set()

    def classify(self, event: RawFeedEvent) -> ClassifiedEvent:
        """Classify one raw event — heuristic keyword matching."""
        headline_lower = event.headline.lower()
        event_type = _classify_event_type(headline_lower)
        materiality = _classify_materiality(headline_lower, event_type)
        dedupe_key = _dedupe_key(event.source, event.headline)
        is_duplicate = dedupe_key in self._seen_keys
        self._seen_keys.add(dedupe_key)
        return ClassifiedEvent(
            event_id=event.event_id,
            source=event.source,
            asset_id=event.asset_id,
            ticker=event.ticker,
            event_type=event_type,
            materiality_score=materiality,
            headline=event.headline,
            dedupe_key=dedupe_key,
            is_duplicate=is_duplicate,
        )

    def classify_batch(self, events: list[RawFeedEvent]) -> list[ClassifiedEvent]:
        """Classify a batch, deduplicating within the batch and against history."""
        return [self.classify(e) for e in events]

    def reset_seen(self) -> None:
        self._seen_keys.clear()
