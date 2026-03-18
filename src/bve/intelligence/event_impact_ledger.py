"""
Wave 3A — Event Impact Ledger.

Computes exponentially weighted mean (EWM) market return scores from resolved
event_outcomes, stratified by (event_type, trial_phase, endpoint_type).

Algorithm
---------
- Reads resolved rows from event_outcomes joined to structured_signals.
- Groups by (event_type, trial_phase, endpoint_type).
- For each group, computes EWM using time-based decay:

      w_i = exp(-ln(2) * age_days_i / half_life_days)
      score = Σ(w_i * r_i) / Σ(w_i)

  where age_days_i is the number of calendar days from signal_date to today.
  Older observations receive exponentially smaller weight.

- A score is only marked ``active=True`` when the group has ≥ MIN_OBSERVATIONS
  resolved outcomes.  Below the gate, the score is stored but flagged inactive
  to prevent premature model automation.

Persistence
-----------
Scores are upserted to the ``event_scores`` table in KnowledgeStore.
UNIQUE(event_type, trial_phase, endpoint_type) so re-running overwrites.

CLI
---
``bve-compute-event-scores`` calls ``EventImpactLedger.run(store)`` and
prints a summary table.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Optional
import uuid

from pydantic import BaseModel, Field


MIN_OBSERVATIONS: int = 20
HALF_LIFE_DAYS: float = 180.0

# Literature-informed static priors used when N < MIN_OBSERVATIONS.
# Source: published biotech event-study medians (approximate).
# These are intentionally conservative — the system replaces them with
# empirical EWM estimates as resolved outcome data accumulates.
DEFAULT_EVENT_TYPE_SCORES: dict[str, float] = {
    "trial_readout":           0.00,   # mixed pos/neg → mean ≈ 0 without context
    "interim_analysis":        0.05,   # positive interims dominate public announcements
    "enrollment_update":       0.00,   # small, directionally ambiguous
    "endpoint_change":        -0.05,   # usually perceived as protocol weakness
    "safety_signal":          -0.15,   # negative by definition
    "conference_presentation": 0.03,   # modest; curated toward positive data
    "publication":             0.02,   # peer review adds credibility, limited surprise
    "fda_approval":            0.12,   # well-established median uplift
    "fda_rejection":          -0.30,   # CRL → significant downside
    "fda_designation":         0.05,   # BTD/FTD/ODD positive signal
    "regulatory_hold":        -0.18,   # clinical hold → uncertainty premium
    "label_expansion":         0.08,   # incremental TAM expansion
    "payer_coverage":          0.04,   # formulary inclusion narrows commercial risk
    "partnership":             0.07,   # deal validates asset; upfront receipt
    "financing":              -0.05,   # typically dilutive
    "sec_filing":              0.00,   # neutral absent unusual disclosures
    "management_change":       0.00,   # directionally ambiguous
    "competitor_event":       -0.03,   # positive competitor news is negative for us
    "patent_event":            0.03,   # patent grants are modestly positive
    "program_discontinuation": -0.40,  # pipeline asset written off
}


def get_default_score(event_type: str) -> float:
    """
    Return the static prior T+30 return for *event_type*.

    Used when ``EventImpactScore.active is False`` (N < MIN_OBSERVATIONS).
    Falls back to 0.0 for unrecognised event types.
    """
    return DEFAULT_EVENT_TYPE_SCORES.get(event_type, 0.0)


def effective_t30_score(
    event_type: str,
    computed_scores: "list[EventImpactScore]",
) -> float:
    """
    Return the best available T+30 impact estimate for *event_type*.

    Checks *computed_scores* for an active score matching *event_type* (any
    phase/endpoint stratification).  If none is active, falls back to the
    static ``DEFAULT_EVENT_TYPE_SCORES`` prior.  This implements the
    small-sample protection gate required by the Wave 3 roadmap.

    Parameters
    ----------
    event_type:
        The event type string (e.g. ``"trial_readout"``, ``"fda_approval"``).
    computed_scores:
        Output of ``EventImpactLedger.compute_scores()`` or ``run()``.

    Returns
    -------
    float
        Effective T+30 mean return to use in downstream models.
    """
    active = [
        s for s in computed_scores
        if s.active and s.category.event_type == event_type
        and s.mean_return_t30 is not None
    ]
    if active:
        # Use the most broadly applicable active score (prefer None-phase as fallback)
        none_phase = [s for s in active if s.category.trial_phase is None]
        return (none_phase or active)[0].mean_return_t30  # type: ignore[return-value]
    return get_default_score(event_type)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EventCategory(BaseModel):
    """Stratification key — identifies one scoring group."""

    event_type: str
    trial_phase: Optional[str] = None
    endpoint_type: Optional[str] = None

    def __hash__(self) -> int:
        return hash((self.event_type, self.trial_phase, self.endpoint_type))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EventCategory):
            return NotImplemented
        return (
            self.event_type == other.event_type
            and self.trial_phase == other.trial_phase
            and self.endpoint_type == other.endpoint_type
        )


class EventImpactScore(BaseModel):
    """EWM impact score for one event category."""

    score_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: EventCategory
    observation_count: int
    mean_return_t30: Optional[float] = None    # EWM of T+30 abnormal market returns
    mean_return_t180: Optional[float] = None   # EWM of T+180 abnormal market returns
    active: bool                               # True only when count >= MIN_OBSERVATIONS
    half_life_days: float = HALF_LIFE_DAYS
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# EWM computation
# ---------------------------------------------------------------------------


def _ewm_score(
    returns: list[float],
    signal_dates: list[date],
    reference_date: date,
    half_life_days: float,
) -> float:
    """
    Time-weighted EWM.

    w_i = exp(-ln2 * age_days_i / half_life_days)
    score = Σ(w_i * r_i) / Σ(w_i)

    Older observations receive exponentially smaller weight.
    """
    ln2 = math.log(2.0)
    total_weight = 0.0
    weighted_sum = 0.0
    for r, d in zip(returns, signal_dates):
        age_days = (reference_date - d).days
        age_days = max(0, age_days)
        w = math.exp(-ln2 * age_days / half_life_days)
        weighted_sum += w * r
        total_weight += w
    if total_weight == 0.0:
        return 0.0
    return weighted_sum / total_weight


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


class EventImpactLedger:
    """
    Computes, stores, and retrieves event impact scores.

    Parameters
    ----------
    min_observations:
        Minimum resolved outcomes required before a score is marked active.
    half_life_days:
        EWM half-life in calendar days.
    reference_date:
        Date relative to which ages are computed.  Defaults to today (UTC).
        Override in tests for determinism.
    """

    def __init__(
        self,
        min_observations: int = MIN_OBSERVATIONS,
        half_life_days: float = HALF_LIFE_DAYS,
        reference_date: Optional[date] = None,
    ) -> None:
        self.min_observations = min_observations
        self.half_life_days = half_life_days
        self._reference_date = reference_date or datetime.now(timezone.utc).date()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_scores(self, store: "KnowledgeStore") -> list[EventImpactScore]:  # type: ignore[name-defined]
        """
        Read resolved event_outcomes from *store* and compute EWM scores.

        Joins event_outcomes → events → structured_signals to enrich with
        trial_phase and endpoint_type when available.

        Returns a list of EventImpactScore (one per category group).
        """
        rows = self._fetch_resolved_outcomes(store)
        return self._compute_from_rows(rows)

    def save_scores(
        self,
        scores: list[EventImpactScore],
        store: "KnowledgeStore",  # type: ignore[name-defined]
    ) -> None:
        """Upsert all scores into the event_scores table."""
        for score in scores:
            store.upsert_event_score(score)

    def run(
        self, store: "KnowledgeStore"  # type: ignore[name-defined]
    ) -> list[EventImpactScore]:
        """Compute and persist scores in one call. Returns the computed scores."""
        scores = self.compute_scores(store)
        self.save_scores(scores, store)
        return scores

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_resolved_outcomes(self, store: "KnowledgeStore") -> list[dict]:  # type: ignore[name-defined]
        """
        Query event_outcomes joined to structured_signals for enrichment.

        Only includes rows where resolved_t30 = 1 (T+30 window closed).
        """
        rows = store._conn.execute(
            """
            SELECT
                eo.event_type,
                eo.signal_date,
                eo.market_return_t30,
                eo.market_return_t180,
                eo.resolved_t30,
                eo.resolved_t180,
                json_extract(ss.payload_json, '$.trial_phase')   AS trial_phase,
                json_extract(ss.payload_json, '$.endpoint_type') AS endpoint_type
            FROM event_outcomes eo
            LEFT JOIN events e ON eo.event_id = e.id
            LEFT JOIN structured_signals ss ON e.signal_id = ss.id
            WHERE eo.resolved_t30 = 1
            ORDER BY eo.signal_date ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def _compute_from_rows(self, rows: list[dict]) -> list[EventImpactScore]:
        """Group rows by category and compute EWM scores."""
        # Group
        groups: dict[EventCategory, list[dict]] = {}
        for row in rows:
            cat = EventCategory(
                event_type=row["event_type"] or "unknown",
                trial_phase=row.get("trial_phase"),
                endpoint_type=row.get("endpoint_type"),
            )
            groups.setdefault(cat, []).append(row)

        scores: list[EventImpactScore] = []
        for cat, group_rows in groups.items():
            n = len(group_rows)

            # T+30 returns (always present when resolved_t30=1)
            t30_pairs = [
                (r["market_return_t30"], r["signal_date"])
                for r in group_rows
                if r["market_return_t30"] is not None
            ]
            mean_t30: Optional[float] = None
            if t30_pairs:
                returns_t30, dates_t30 = zip(*t30_pairs)
                parsed_dates = [
                    date.fromisoformat(d) if isinstance(d, str) else d
                    for d in dates_t30
                ]
                mean_t30 = _ewm_score(
                    list(returns_t30), parsed_dates,
                    self._reference_date, self.half_life_days,
                )

            # T+180 returns (only for fully-resolved rows)
            t180_pairs = [
                (r["market_return_t180"], r["signal_date"])
                for r in group_rows
                if r.get("resolved_t180") and r["market_return_t180"] is not None
            ]
            mean_t180: Optional[float] = None
            if t180_pairs:
                returns_t180, dates_t180 = zip(*t180_pairs)
                parsed_dates_180 = [
                    date.fromisoformat(d) if isinstance(d, str) else d
                    for d in dates_t180
                ]
                mean_t180 = _ewm_score(
                    list(returns_t180), parsed_dates_180,
                    self._reference_date, self.half_life_days,
                )

            scores.append(
                EventImpactScore(
                    category=cat,
                    observation_count=n,
                    mean_return_t30=mean_t30,
                    mean_return_t180=mean_t180,
                    active=n >= self.min_observations,
                    half_life_days=self.half_life_days,
                )
            )

        return scores
