"""
Score explainer — audit report generator for M&A attractiveness scores.

Purpose
-------
For each scored ticker, generate a human-readable explanation of:
  1. What the current score is and which dimension drives it
  2. Which events contributed the most (top drivers)
  3. What evidence is missing (coverage gaps = risk flags)
  4. How confident the model is (based on evidence volume and quality)
  5. What version of the scoring rules produced this score

Output formats
--------------
  ScoreExplanation   — structured Python dataclass (machine-readable + display)
  to_text()          — compact plain-text summary for console / API responses
  to_dict()          — JSON-serialisable dict for downstream consumers
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# DriverEntry — one event contribution explained
# ---------------------------------------------------------------------------


@dataclass
class DriverEntry:
    """
    One event's contribution to the score.

    Fields
    ------
    event_type      : classified event type
    feature         : which score dimension was affected
    delta           : the actual change applied (post-context-modifier)
    direction       : "positive" | "negative" | "neutral"
    headline_snippet: first 80 chars of the raw text
    event_date      : ISO date string (or published_date if use_published_date)
    source_type     : evidence source
    cluster_id      : semantic cluster ID (None if not yet clustered)
    """

    event_type: str
    feature: str
    delta: float
    direction: str
    headline_snippet: str
    event_date: str
    source_type: str
    cluster_id: Optional[str] = None


# ---------------------------------------------------------------------------
# RiskFlag — a structured warning about score reliability
# ---------------------------------------------------------------------------


@dataclass
class RiskFlag:
    """
    A warning that reduces confidence in the score.

    severity  : "high" | "medium" | "low"
    category  : "coverage_gap" | "stale_evidence" | "pending_review" |
                "version_mismatch" | "low_volume"
    message   : human-readable explanation
    """

    severity: str
    category: str
    message: str


# ---------------------------------------------------------------------------
# ScoreExplanation — full audit for one ticker
# ---------------------------------------------------------------------------


@dataclass
class ScoreExplanation:
    """
    Full score explanation for one ticker at one point in time.

    Fields
    ------
    ticker              : asset ticker
    as_of_date          : ISO date string
    scores              : dict of feature_name → score value
    top_drivers         : list of DriverEntry sorted by |delta| desc
    risk_flags          : list of RiskFlag
    evidence_count      : total number of evidence records used
    coverage_summary    : dict of domain → coverage_score
    pipeline_version    : version string from model_versions.py
    score_mode          : "approved_only" | "provisional" | "all_auto"
    confidence_bands    : dict of feature_name → {lower, upper, half_width}
    """

    ticker: str
    as_of_date: str
    scores: dict[str, float]
    top_drivers: list[DriverEntry]
    risk_flags: list[RiskFlag]
    evidence_count: int
    coverage_summary: dict[str, float]
    pipeline_version: str
    score_mode: str
    confidence_bands: dict[str, dict] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def to_text(self, max_drivers: int = 5) -> str:
        """Compact plain-text representation for console output."""
        lines = [
            f"Score Explanation — {self.ticker} (as of {self.as_of_date})",
            f"Pipeline: {self.pipeline_version}  |  Mode: {self.score_mode}",
            f"Evidence: {self.evidence_count} records",
            "",
            "Scores:",
        ]
        for feat, val in sorted(self.scores.items()):
            band = self.confidence_bands.get(feat)
            if band:
                lines.append(
                    f"  {feat:<25} {val:.3f}  [{band['lower']:.2f}–{band['upper']:.2f}]"
                )
            else:
                lines.append(f"  {feat:<25} {val:.3f}")

        if self.top_drivers:
            lines.append("")
            lines.append(f"Top Drivers (showing {min(max_drivers, len(self.top_drivers))}):")
            for d in self.top_drivers[:max_drivers]:
                sign = "+" if d.delta >= 0 else ""
                lines.append(
                    f"  [{d.event_date}] {d.event_type:<28} "
                    f"{d.feature}: {sign}{d.delta:+.3f}  "
                    f"({d.source_type})  \"{d.headline_snippet[:60]}...\""
                )

        if self.risk_flags:
            lines.append("")
            lines.append("Risk Flags:")
            for f in self.risk_flags:
                lines.append(f"  [{f.severity.upper()}] {f.category}: {f.message}")

        if self.coverage_summary:
            lines.append("")
            lines.append("Coverage:")
            for domain, score in sorted(self.coverage_summary.items()):
                bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
                lines.append(f"  {domain:<15} {bar}  {score:.2f}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON-serialisable representation."""
        return {
            "ticker": self.ticker,
            "as_of_date": self.as_of_date,
            "pipeline_version": self.pipeline_version,
            "score_mode": self.score_mode,
            "evidence_count": self.evidence_count,
            "scores": self.scores,
            "confidence_bands": self.confidence_bands,
            "coverage_summary": self.coverage_summary,
            "top_drivers": [
                {
                    "event_type": d.event_type,
                    "feature": d.feature,
                    "delta": d.delta,
                    "direction": d.direction,
                    "event_date": d.event_date,
                    "source_type": d.source_type,
                    "headline_snippet": d.headline_snippet,
                    "cluster_id": d.cluster_id,
                }
                for d in self.top_drivers
            ],
            "risk_flags": [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "message": f.message,
                }
                for f in self.risk_flags
            ],
        }


# ---------------------------------------------------------------------------
# ScoreExplainer
# ---------------------------------------------------------------------------


# Coverage threshold below which a domain is flagged as low-coverage
_LOW_COVERAGE_THRESHOLD = 0.30
_STALE_EVIDENCE_DAYS    = 180
_LOW_VOLUME_THRESHOLD   = 2


class ScoreExplainer:
    """
    Generate structured score explanations from scored evidence data.

    Usage::

        explainer = ScoreExplainer()
        explanation = explainer.explain(
            ticker="ALNY",
            as_of_date="2025-06-01",
            scores={"ma_attractiveness": 0.72, "asset_quality": 0.68},
            events=[...],   # list of dicts from EvidenceLedger
            coverage={"clinical": 0.80, "regulatory": 0.20, "financial": 0.10},
            pipeline_version="v2.1/v2.1/v1.2",
        )
    """

    def explain(
        self,
        ticker: str,
        as_of_date: str,
        scores: dict[str, float],
        events: Optional[list[dict]] = None,
        coverage: Optional[dict[str, float]] = None,
        pipeline_version: str = "",
        score_mode: str = "provisional",
        confidence_bands: Optional[dict[str, dict]] = None,
    ) -> ScoreExplanation:
        """
        Build a ScoreExplanation.

        Parameters
        ----------
        ticker           : asset ticker
        as_of_date       : ISO date of the score snapshot
        scores           : feature → score dict
        events           : list of event dicts (from ledger); each may have:
                             event_type, feature, delta, raw_text,
                             event_date, source_type, cluster_id
        coverage         : domain → coverage score dict
        pipeline_version : version string for audit
        score_mode       : score mode used
        confidence_bands : feature → {lower, upper, half_width}
        """
        evts = events or []
        cov = coverage or {}

        drivers = self._extract_drivers(evts)
        risk_flags = self._build_risk_flags(evts, cov, as_of_date, scores)

        return ScoreExplanation(
            ticker=ticker,
            as_of_date=as_of_date,
            scores=scores,
            top_drivers=drivers,
            risk_flags=risk_flags,
            evidence_count=len(evts),
            coverage_summary=cov,
            pipeline_version=pipeline_version,
            score_mode=score_mode,
            confidence_bands=confidence_bands or {},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_drivers(self, events: list[dict]) -> list[DriverEntry]:
        """Extract DriverEntry list from event dicts, sorted by |delta| desc."""
        drivers = []
        for evt in events:
            delta = evt.get("delta", 0.0)
            if delta == 0.0:
                continue
            text = evt.get("raw_text", "")
            drivers.append(DriverEntry(
                event_type=evt.get("event_type", "unclassified"),
                feature=evt.get("feature", "unknown"),
                delta=delta,
                direction="positive" if delta > 0 else "negative",
                headline_snippet=text[:80] if text else "",
                event_date=evt.get("event_date", "") or evt.get("published_date", ""),
                source_type=evt.get("source_type", "unknown"),
                cluster_id=evt.get("cluster_id"),
            ))
        return sorted(drivers, key=lambda d: abs(d.delta), reverse=True)

    def _build_risk_flags(
        self,
        events: list[dict],
        coverage: dict[str, float],
        as_of_date: str,
        scores: dict[str, float],
    ) -> list[RiskFlag]:
        flags = []

        # Low evidence volume
        if len(events) < _LOW_VOLUME_THRESHOLD:
            flags.append(RiskFlag(
                severity="medium",
                category="low_volume",
                message=f"Only {len(events)} evidence record(s) available — score has wide uncertainty.",
            ))

        # Coverage gaps
        for domain, score in coverage.items():
            if score < _LOW_COVERAGE_THRESHOLD:
                flags.append(RiskFlag(
                    severity="high" if score < 0.10 else "medium",
                    category="coverage_gap",
                    message=f"{domain} coverage is {score:.0%} — score may not reflect recent events.",
                ))

        # Stale evidence
        stale_count = 0
        for evt in events:
            age = evt.get("age_days", 0)
            if age and age > _STALE_EVIDENCE_DAYS:
                stale_count += 1
        if stale_count > 0:
            flags.append(RiskFlag(
                severity="low",
                category="stale_evidence",
                message=f"{stale_count} evidence record(s) older than {_STALE_EVIDENCE_DAYS} days.",
            ))

        # Pending review events
        pending = sum(1 for e in events if e.get("review_status") == "pending")
        if pending > 0:
            flags.append(RiskFlag(
                severity="medium",
                category="pending_review",
                message=f"{pending} high-materiality event(s) pending human review — excluded from approved_only mode.",
            ))

        return flags
