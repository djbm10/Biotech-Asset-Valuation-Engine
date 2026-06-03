"""
Calibrated Probability Band — Block 4.

Answers: "Based on historical segment outcomes, what is the calibrated
probability of acquisition for this type of target?"

Key design rule:
  - RANK_ONLY mode when N < minimum_n (no probability number displayed)
  - SHOW_BAND mode when N >= minimum_n (Wilson interval + point estimate)
  - minimum_n is explicit and user-configurable (default: DEFAULT_MINIMUM_N)
  - Band width narrows with larger N (confidence interval property)

This module is pure statistics — no scoring logic, no layer dependencies.
It is called from the MAProbabilityScanner (Block 5) before displaying
probability ranges on the watchlist output.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MINIMUM_N: int = 10  # minimum outcomes before showing a probability band

# Confidence level for Wilson score interval (90% → z=1.645, 95% → z=1.96)
_DEFAULT_CI_Z: float = 1.645  # 90% CI default


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DisplayMode(str, Enum):
    SHOW_BAND = "show_band"   # N >= minimum_n → show probability range
    RANK_ONLY = "rank_only"   # N < minimum_n → rank only, no probability


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class CalibratedProbabilityBand(BaseModel):
    model_config = ConfigDict(frozen=True)

    display_mode: DisplayMode
    n_observations: int = Field(..., ge=0)
    minimum_n_threshold: int

    # Populated when display_mode == SHOW_BAND; None when RANK_ONLY
    point_estimate: float | None = Field(default=None, ge=0.0, le=1.0)
    lower_bound: float | None = Field(default=None, ge=0.0, le=1.0)
    upper_bound: float | None = Field(default=None, ge=0.0, le=1.0)

    # Confidence level increases with N (0–1 scale)
    confidence_level: float = Field(..., ge=0.0, le=1.0)

    label_text: str = ""
    segment_label: str = ""


# ---------------------------------------------------------------------------
# Wilson score interval
# ---------------------------------------------------------------------------

def _wilson_interval(
    successes: int,
    n: int,
    z: float = _DEFAULT_CI_Z,
) -> tuple[float, float]:
    """
    Wilson score confidence interval for a proportion.
    Returns (lower, upper) both in [0, 1].
    """
    if n == 0:
        return 0.0, 1.0
    p_hat = successes / n
    z2 = z * z
    center = (p_hat + z2 / (2 * n)) / (1 + z2 / n)
    margin = (z / (1 + z2 / n)) * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return lower, upper


def _sample_confidence(n: int, minimum_n: int, max_n: int = 100) -> float:
    """
    Confidence level that grows with N from minimum_n → max_n.
    At minimum_n: ~0.55; at max_n: ~0.90.
    """
    if n <= minimum_n:
        return 0.55
    fraction = min(1.0, (n - minimum_n) / (max_n - minimum_n))
    return round(0.55 + 0.35 * fraction, 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_probability_band(
    outcomes: Sequence[int],
    *,
    minimum_n: int = DEFAULT_MINIMUM_N,
    segment_label: str = "",
    ci_z: float = _DEFAULT_CI_Z,
) -> CalibratedProbabilityBand:
    """
    Compute a CalibratedProbabilityBand from a sequence of binary outcomes (0/1).

    Args:
        outcomes: list of 0/1 integers (1 = acquired, 0 = not acquired)
        minimum_n: minimum observations required before displaying a probability
        segment_label: optional label for the market segment
        ci_z: z-score for confidence interval (default 1.645 = 90% CI)

    Returns:
        CalibratedProbabilityBand with SHOW_BAND or RANK_ONLY display_mode.

    RANK_ONLY: when N < minimum_n. point_estimate / lower_bound / upper_bound = None.
    SHOW_BAND: Wilson score interval. Band narrows with larger N.
    """
    n = len(outcomes)

    if n < minimum_n:
        label = (
            f"Insufficient segment data (n={n}, minimum={minimum_n}). "
            "Rank-only mode: probability band not displayed."
        )
        return CalibratedProbabilityBand(
            display_mode=DisplayMode.RANK_ONLY,
            n_observations=n,
            minimum_n_threshold=minimum_n,
            point_estimate=None,
            lower_bound=None,
            upper_bound=None,
            confidence_level=0.0,
            label_text=label,
            segment_label=segment_label,
        )

    successes = sum(1 for o in outcomes if o)
    p_hat = successes / n
    lower, upper = _wilson_interval(successes, n, z=ci_z)
    confidence = _sample_confidence(n, minimum_n)

    label = (
        f"{segment_label + ': ' if segment_label else ''}"
        f"P(acquisition) = {p_hat:.0%} "
        f"[{lower:.0%}–{upper:.0%}] "
        f"(n={n}, 90% CI)"
    )

    return CalibratedProbabilityBand(
        display_mode=DisplayMode.SHOW_BAND,
        n_observations=n,
        minimum_n_threshold=minimum_n,
        point_estimate=round(p_hat, 6),
        lower_bound=round(lower, 6),
        upper_bound=round(upper, 6),
        confidence_level=confidence,
        label_text=label,
        segment_label=segment_label,
    )
