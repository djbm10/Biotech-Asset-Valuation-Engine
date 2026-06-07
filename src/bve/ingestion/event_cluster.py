"""
Semantic event clustering — deduplication beyond hash-based matching.

Problem
-------
Three paraphrases of the same readout carry different event_hashes but are one event:
  "Company X reports positive Phase 2 data"
  "Company X announces Phase 2 study met endpoint"
  "Company X shares positive mid-stage results"

Solution
--------
Cluster by (ticker, event_type_family, phase, [trial_id or asset], date_bucket).

Tiered key logic:
  1. trial_id present  → cluster by trial_id (most precise)
  2. asset present     → cluster by normalised asset name + phase + week
  3. fallback          → ticker + event_family + phase + week

Within each cluster:
  - canonical record   = highest source-priority record (only this affects scores)
  - supporting records = additional sources; increase CONFIDENCE only, not materiality
    (multiple outlets covering an event makes us more sure it happened, but a routine
     orphan designation mentioned by 5 news sites is still a routine orphan designation)

Multi-source confidence boosts
-------------------------------
  sec_filing + press_release   → +0.04 to canonical confidence
  fda_website + press_release  → +0.04
  clinicaltrials_gov + press_release → +0.03
  pubmed + press_release       → +0.03
  Cap: max total boost = 0.05 (not additive — take max matching rule)
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Event-type family grouping — coarser than event_type to prevent over-splitting
# ---------------------------------------------------------------------------

EVENT_TYPE_FAMILY: dict[str, str] = {
    "clinical_positive_ph3": "clinical_positive",
    "clinical_positive_ph2": "clinical_positive",
    "clinical_positive_ph1": "clinical_positive",
    "clinical_positive":     "clinical_positive",
    "clinical_mixed":        "clinical_mixed",
    "clinical_negative_ph3": "clinical_negative",
    "clinical_negative_ph2": "clinical_negative",
    "clinical_negative_ph1": "clinical_negative",
    "clinical_negative":     "clinical_negative",
    "trial_start":           "trial_operational",
    "trial_delay":           "trial_operational",
    "trial_discontinuation": "trial_operational",
    "fda_approval":          "regulatory_positive",
    "btd":                   "regulatory_positive",
    "fast_track":            "regulatory_positive",
    "orphan":                "regulatory_positive",
    "adcom_positive":        "regulatory_positive",
    "nda_accepted":          "regulatory_positive",
    "pdufa":                 "regulatory_milestone",
    "crl":                   "regulatory_negative",
    "adcom_negative":        "regulatory_negative",
    "equity_raise":          "financial",
    "cash_low":              "financial",
    "restructuring":         "financial",
    "strategic_review":      "strategic",
    "licensing_deal":        "bd",
    "partnership":           "bd",
    "asset_sale":            "bd",
    "acquirer_bd_appetite":  "acquirer",
    "acquirer_large_deal":   "acquirer",
    "patent_cliff":          "acquirer",
    "unclassified":          "unclassified",
}

# Source priority — higher = preferred canonical
SOURCE_RANK: dict[str, int] = {
    "fda_website":        100,
    "sec_filing":         90,
    "clinicaltrials_gov": 85,
    "pubmed":             80,
    "press_release":      60,
    "news_article":       40,
    "manual":             50,
}

# Multi-source confidence boost rules.
# Boost applies to canonical confidence only, not materiality.
# Take max matching rule — do not stack boosts.
_MULTI_SOURCE_BOOSTS: list[tuple[frozenset[str], float]] = [
    (frozenset({"sec_filing",        "press_release"}), 0.04),
    (frozenset({"fda_website",       "press_release"}), 0.04),
    (frozenset({"clinicaltrials_gov","press_release"}), 0.03),
    (frozenset({"pubmed",            "press_release"}), 0.03),
    (frozenset({"sec_filing",        "news_article"}),  0.03),
]
_MAX_CONFIDENCE_BOOST = 0.05


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _date_bucket(date_str: Optional[str]) -> str:
    """Convert ISO date string → ISO year-week bucket, e.g. '2025-W23'."""
    if not date_str:
        return "unknown"
    try:
        d = date.fromisoformat(date_str[:10])
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    except (ValueError, AttributeError):
        return "unknown"


def _normalize_name(s: Optional[str], maxlen: int = 40) -> Optional[str]:
    if not s:
        return None
    return " ".join(s.lower().strip().split())[:maxlen]


# ---------------------------------------------------------------------------
# EventClusterKey — immutable, hashable cluster discriminator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventClusterKey:
    """
    Immutable cluster key used to group semantically identical events.

    Tiered construction (see from_record):
      trial_id present  → (ticker, family, phase, date_bucket, trial_id)
      asset present     → (ticker, family, phase, date_bucket, asset_normalized)
      fallback          → (ticker, family, phase, date_bucket)

    This prevents merging Drug A Ph2 positive with Drug B Ph2 negative at
    the same company in the same week — a failure mode of flat keys.
    """

    ticker: str
    event_type_family: str
    phase: Optional[str]
    date_bucket: str
    trial_id: Optional[str] = None
    asset_normalized: Optional[str] = None

    @classmethod
    def from_record(cls, record: Any) -> "EventClusterKey":
        """
        Build a cluster key from any object with the EvidenceRecord interface.
        Missing optional attributes are handled gracefully.
        """
        family = EVENT_TYPE_FAMILY.get(
            getattr(record, "event_type", "unclassified"), "unclassified"
        )
        # Prefer published_date for bucketing (when did the world know?)
        date_str = getattr(record, "published_date", None) or getattr(record, "event_date", None)
        bucket = _date_bucket(date_str)
        phase = getattr(record, "phase_detected", None) or None
        trial_id = getattr(record, "trial_id", None) or None
        asset_norm = _normalize_name(getattr(record, "asset", None))

        if trial_id:
            return cls(
                ticker=record.ticker,
                event_type_family=family,
                phase=phase,
                date_bucket=bucket,
                trial_id=trial_id,
            )
        if asset_norm:
            return cls(
                ticker=record.ticker,
                event_type_family=family,
                phase=phase,
                date_bucket=bucket,
                asset_normalized=asset_norm,
            )
        return cls(
            ticker=record.ticker,
            event_type_family=family,
            phase=phase,
            date_bucket=bucket,
        )

    def to_cluster_id(self) -> str:
        """Stable 12-char hex ID derived from this key."""
        parts = [self.ticker, self.event_type_family, self.phase or "", self.date_bucket]
        if self.trial_id:
            parts.append(f"trial:{self.trial_id}")
        elif self.asset_normalized:
            parts.append(f"asset:{self.asset_normalized}")
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# EventCluster — groups records; exposes canonical + supporting evidence
# ---------------------------------------------------------------------------


@dataclass
class EventCluster:
    """
    A group of evidence records that represent the same real-world event.

    Only canonical is used for scoring. Supporting records increase
    canonical.confidence via multi_source_confidence_boost, but do NOT
    increase materiality — that would introduce media-hype bias.
    """

    key: EventClusterKey
    cluster_id: str
    canonical: Any                          # EvidenceRecord — scores from this only
    supporting: list[Any] = field(default_factory=list)
    best_source_type: str = "news_article"
    supporting_source_types: list[str] = field(default_factory=list)
    multi_source_confidence_boost: float = 0.0

    @property
    def supporting_evidence_count(self) -> int:
        return len(self.supporting)

    @property
    def all_source_types(self) -> frozenset[str]:
        return frozenset([self.best_source_type] + self.supporting_source_types)

    @property
    def canonical_for_scoring(self) -> bool:
        """Always True — the canonical record is the scoring record by definition."""
        return True

    @property
    def boosted_confidence(self) -> float:
        """
        Canonical confidence after multi-source boost, clamped to [0, 1].
        Call this instead of canonical.confidence when computing effective deltas.
        """
        raw = getattr(self.canonical, "confidence", 0.0)
        return min(1.0, raw + self.multi_source_confidence_boost)

    def summary(self) -> dict:
        """Human-readable summary dict for audit/reporting."""
        return {
            "cluster_id": self.cluster_id,
            "ticker": self.key.ticker,
            "event_family": self.key.event_type_family,
            "phase": self.key.phase,
            "date_bucket": self.key.date_bucket,
            "canonical_event_type": getattr(self.canonical, "event_type", ""),
            "canonical_source": self.best_source_type,
            "supporting_evidence_count": self.supporting_evidence_count,
            "supporting_sources": self.supporting_source_types,
            "multi_source_boost": self.multi_source_confidence_boost,
            "boosted_confidence": round(self.boosted_confidence, 4),
        }


# ---------------------------------------------------------------------------
# EventClusterer — groups records and selects canonical
# ---------------------------------------------------------------------------


class EventClusterer:
    """
    Group evidence records into semantic clusters and select a canonical record
    per cluster for scoring.

    Usage::

        clusterer = EventClusterer()
        clusters = clusterer.cluster(records)
        for cluster in clusters:
            # Only cluster.canonical contributes to score_state
            effective_conf = cluster.boosted_confidence
    """

    def cluster(self, records: list[Any]) -> list[EventCluster]:
        """Group records and return one EventCluster per semantic group."""
        groups: dict[EventClusterKey, list[Any]] = defaultdict(list)
        for record in records:
            key = EventClusterKey.from_record(record)
            groups[key].append(record)

        return [self._build_cluster(key, recs) for key, recs in groups.items()]

    def assign_cluster_id(self, record: Any) -> str:
        """Return the cluster_id for a single record without building the full cluster."""
        return EventClusterKey.from_record(record).to_cluster_id()

    def _build_cluster(self, key: EventClusterKey, records: list[Any]) -> EventCluster:
        # Sort by source rank desc, then by published_date desc as tiebreak
        sorted_recs = sorted(
            records,
            key=lambda r: (
                -SOURCE_RANK.get(getattr(r, "source_type", "news_article"), 0),
                -(getattr(r, "published_date", None) or getattr(r, "event_date", "") or ""),
            ),
        )
        canonical = sorted_recs[0]
        supporting = sorted_recs[1:]
        all_source_types = frozenset(
            getattr(r, "source_type", "news_article") for r in sorted_recs
        )
        boost = self._compute_confidence_boost(all_source_types)

        return EventCluster(
            key=key,
            cluster_id=key.to_cluster_id(),
            canonical=canonical,
            supporting=supporting,
            best_source_type=getattr(canonical, "source_type", "news_article"),
            supporting_source_types=[
                getattr(r, "source_type", "news_article") for r in supporting
            ],
            multi_source_confidence_boost=boost,
        )

    @staticmethod
    def _compute_confidence_boost(source_types: frozenset[str]) -> float:
        """
        Return multi-source confidence boost.
        Takes the maximum matching rule (not additive) to prevent stacking.
        """
        best = 0.0
        for required_sources, boost in _MULTI_SOURCE_BOOSTS:
            if required_sources.issubset(source_types):
                best = max(best, boost)
        return min(best, _MAX_CONFIDENCE_BOOST)
