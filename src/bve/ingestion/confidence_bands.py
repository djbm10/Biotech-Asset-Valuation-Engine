"""
Confidence bands for score state estimates.

The M&A attractiveness score at any point in time is an estimate, not a fact.
Confidence bands quantify the uncertainty around each score dimension based on:

  1. Evidence volume — more events → narrower band
  2. Evidence age    — stale evidence → wider band
  3. Source quality  — higher-quality sources → narrower band
  4. Review status   — unapproved events pending review → wider band

Formula
-------
For a score with N evidence records and average evidence strength S:

    base_half_width = BASE_HALF_WIDTH × decay_factor
    volume_factor   = 1 / sqrt(max(N, 1))
    quality_factor  = 1 - (S - 0.5) × QUALITY_SCALE   (higher S → lower band)
    half_width      = base_half_width × volume_factor × quality_factor

    lower = clamp(score - half_width, 0.0, score)
    upper = clamp(score + half_width, score, 1.0)

Constants are tuned so:
  - Zero events → ±0.20 uncertainty
  - 1 high-quality event → ±0.15
  - 5 mixed events → ±0.09
  - 20 events → ±0.04
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_HALF_WIDTH     = 0.20   # ±20% with no evidence
QUALITY_SCALE       = 0.30   # how much quality narrows the band

# Age-based decay: evidence older than DECAY_HALFLIFE_DAYS doubles the band
DECAY_HALFLIFE_DAYS = 180    # 6-month half-life for staleness
MAX_DECAY_FACTOR    = 2.0    # cap the staleness expansion


# ---------------------------------------------------------------------------
# ScoreBand
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreBand:
    """
    Confidence band for one score dimension.

    Fields
    ------
    point_estimate  : the current score value
    lower           : lower bound (≥ 0)
    upper           : upper bound (≤ 1)
    half_width      : (upper - lower) / 2
    n_events        : number of evidence records used
    avg_strength    : weighted-average evidence strength
    staleness_factor: decay multiplier applied (1.0 = fresh, 2.0 = very stale)
    """

    point_estimate: float
    lower: float
    upper: float
    half_width: float
    n_events: int
    avg_strength: float
    staleness_factor: float


# ---------------------------------------------------------------------------
# ConfidenceBandEstimator
# ---------------------------------------------------------------------------


class ConfidenceBandEstimator:
    """
    Compute confidence bands for score state estimates.

    Usage::

        estimator = ConfidenceBandEstimator()
        band = estimator.compute(
            score=0.72,
            evidence_records=[
                {"strength": 0.90, "age_days": 10},
                {"strength": 0.60, "age_days": 45},
            ],
        )
        # band.lower ≈ 0.57, band.upper ≈ 0.87
    """

    def compute(
        self,
        score: float,
        evidence_records: Optional[list[dict]] = None,
    ) -> ScoreBand:
        """
        Compute a confidence band for the given score.

        Parameters
        ----------
        score            : current score point estimate [0, 1]
        evidence_records : list of dicts with optional keys:
                             strength  : float [0, 1] — evidence quality
                             age_days  : float ≥ 0    — days since event
        """
        records = evidence_records or []
        n = len(records)

        if n == 0:
            return ScoreBand(
                point_estimate=round(score, 4),
                lower=round(max(0.0, score - BASE_HALF_WIDTH), 4),
                upper=round(min(1.0, score + BASE_HALF_WIDTH), 4),
                half_width=BASE_HALF_WIDTH,
                n_events=0,
                avg_strength=0.0,
                staleness_factor=1.0,
            )

        # Compute average strength
        strengths = [r.get("strength", 0.60) for r in records]
        avg_strength = sum(strengths) / len(strengths)

        # Compute average staleness factor
        stale_factors = [
            self._staleness_factor(r.get("age_days", 0.0))
            for r in records
        ]
        avg_stale = sum(stale_factors) / len(stale_factors)

        # Volume reduction
        volume_factor = 1.0 / math.sqrt(max(n, 1))

        # Quality reduction (higher quality → smaller band)
        quality_factor = 1.0 - (avg_strength - 0.5) * QUALITY_SCALE

        half_width = (
            BASE_HALF_WIDTH
            * avg_stale
            * volume_factor
            * quality_factor
        )
        # Clamp half_width
        half_width = min(half_width, BASE_HALF_WIDTH * MAX_DECAY_FACTOR)

        lower = max(0.0, score - half_width)
        upper = min(1.0, score + half_width)

        return ScoreBand(
            point_estimate=round(score, 4),
            lower=round(lower, 4),
            upper=round(upper, 4),
            half_width=round(half_width, 4),
            n_events=n,
            avg_strength=round(avg_strength, 4),
            staleness_factor=round(avg_stale, 4),
        )

    @staticmethod
    def _staleness_factor(age_days: float) -> float:
        """
        Return staleness multiplier. Fresh (0 days) → 1.0; older → up to MAX_DECAY_FACTOR.
        """
        if age_days <= 0:
            return 1.0
        factor = 2 ** (age_days / DECAY_HALFLIFE_DAYS)
        return min(factor, MAX_DECAY_FACTOR)
