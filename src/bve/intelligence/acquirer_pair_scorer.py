"""
Acquirer-target pair scorer using a logit (log-odds) formula.

Purpose
-------
Score a specific (acquirer, target) pair rather than target attractiveness in
isolation.  A target may be highly attractive but a poor fit for a specific
acquirer if their pipelines overlap, they already have a large deal outstanding,
or their TA focus is misaligned.

Formula
-------
    log_odds = intercept
             + w_asset_quality      × asset_quality
             + w_acquirer_appetite  × acquirer_appetite
             + w_ta_overlap         × ta_overlap
             + w_ta_strategic_fit   × ta_strategic_fit
             + w_size_fit           × size_fit
             + w_urgency            × acquirer_urgency
             + w_integration        × integration_capacity
             + w_interaction_urgency_quality × (acquirer_urgency × asset_quality)

    probability = sigmoid(log_odds)

Weights are evidence-informed priors, not statistically estimated coefficients.
They encode the relative importance of each factor for deal completion, drawing
on the academic M&A literature and BD practitioner judgement.

PairFeatures
------------
All inputs to the formula in one typed, immutable container.

TA fit — two complementary terms
---------------------------------
  ta_overlap         — raw Jaccard similarity of TA sets [0, 1]; weight +0.90
  ta_strategic_fit   — tiered non-linear transform of ta_overlap; weight +1.80

  The tiered transform creates a much larger log-odds spread between weak and
  strong TA alignment than the raw linear term alone:

    ta_overlap ≥ 0.60  →  ta_strategic_fit = 1.00  (clear strategic overlap)
    ta_overlap 0.40–0.60 →  ta_strategic_fit = 0.70  (adjacent / partial overlap)
    ta_overlap 0.20–0.40 →  ta_strategic_fit = 0.40  (tangential overlap)
    ta_overlap < 0.20   →  ta_strategic_fit = 0.15  (no meaningful alignment)

  Combined TA spread (raw + tiered):
    strong TA (overlap=0.80):  0.90×0.80 + 1.80×1.00 = +2.52 log-odds
    weak TA   (overlap=0.10):  0.90×0.10 + 1.80×0.15 = +0.36 log-odds
    → 2.16 log-odds differentiation, making TA a first-class gating factor.

Interaction terms
-----------------
  urgency × quality  — acquirer urgency matters MORE when the asset quality is high
                       (bidding wars for clean late-stage assets in patent-cliff scenarios)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from bve.ingestion.model_versions import PAIR_SCORER_VERSION


# ---------------------------------------------------------------------------
# Logit weights (evidence-informed priors)
# ---------------------------------------------------------------------------

INTERCEPT: float = -3.00   # prior log-odds well below 0.5; calibrated so median-quality
                           # pairs score ~0.90 rather than saturating near 1.0

WEIGHTS: dict[str, float] = {
    "asset_quality":          +1.80,  # strongest predictor of deal completion
    "acquirer_appetite":      +1.20,  # acquirer actively in-market
    "ta_overlap":             +0.90,  # raw Jaccard TA similarity
    "ta_strategic_fit":       +1.80,  # tiered non-linear TA alignment (see module doc)
    "size_fit":               +0.70,  # target size fits acquirer's deal range
    "acquirer_urgency":       +1.10,  # patent cliff / pipeline gap
    "integration_capacity":   +0.60,  # acquirer can absorb the deal
}

# Tiered breakpoints for ta_strategic_fit conversion
_TA_STRATEGIC_FIT_TIERS: tuple[tuple[float, float], ...] = (
    (0.60, 1.00),  # clear strategic overlap
    (0.40, 0.70),  # adjacent / partial overlap
    (0.20, 0.40),  # tangential overlap
    (0.00, 0.15),  # no meaningful alignment
)


def ta_strategic_fit_score(ta_overlap: float) -> float:
    """Convert raw Jaccard ta_overlap [0, 1] to a tiered strategic fit score [0.15, 1.0].

    Encodes the non-linear reality that TA alignment below 0.20 represents a
    fundamentally different (and much weaker) strategic rationale than 0.40+.
    """
    for threshold, score in _TA_STRATEGIC_FIT_TIERS:
        if ta_overlap >= threshold:
            return score
    return 0.15

# Interaction term weight
W_URGENCY_QUALITY_INTERACTION: float = +0.80


# ---------------------------------------------------------------------------
# PairFeatures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairFeatures:
    """
    Input features for one (acquirer, target) pair.

    All continuous features are normalised to [0, 1].

    Fields
    ------
    asset_quality        : 0–1, quality/de-risking of the target asset
    acquirer_appetite    : 0–1, how actively the acquirer is deal-hunting
    ta_overlap           : 0–1, raw Jaccard therapeutic area alignment
    ta_strategic_fit     : 0–1, tiered non-linear TA fit (see ta_strategic_fit_score())
    size_fit             : 0–1, target size fits acquirer's preferred deal range
    acquirer_urgency     : 0–1, patent cliff / gap pressure driving urgency
    integration_capacity : 0–1, acquirer has bandwidth for a new deal
    acquirer_id          : optional acquirer identifier
    target_ticker        : optional target identifier
    as_of_date           : optional ISO date (for audit / backtest)
    """

    asset_quality: float
    acquirer_appetite: float
    ta_overlap: float
    ta_strategic_fit: float
    size_fit: float
    acquirer_urgency: float
    integration_capacity: float
    acquirer_id: Optional[str] = None
    target_ticker: Optional[str] = None
    as_of_date: Optional[str] = None

    def __post_init__(self) -> None:
        for fname in ("asset_quality", "acquirer_appetite", "ta_overlap",
                      "ta_strategic_fit", "size_fit", "acquirer_urgency",
                      "integration_capacity"):
            v = getattr(self, fname)
            if not 0.0 <= v <= 1.0:
                raise ValueError(
                    f"PairFeatures.{fname} must be in [0, 1], got {v}"
                )


# ---------------------------------------------------------------------------
# PairScore output
# ---------------------------------------------------------------------------


@dataclass
class PairScore:
    """
    Output of the pair scorer for one (acquirer, target) pair.

    Fields
    ------
    probability    : P(deal | features) from sigmoid(log_odds)
    log_odds       : raw log-odds value
    feature_contributions : dict mapping feature → contribution to log_odds
    interaction_contribution : contribution of the urgency×quality term
    version        : PAIR_SCORER_VERSION stamp
    """

    probability: float
    log_odds: float
    feature_contributions: dict[str, float]
    interaction_contribution: float
    version: str = PAIR_SCORER_VERSION


# ---------------------------------------------------------------------------
# AcquirerPairScorer
# ---------------------------------------------------------------------------


class AcquirerPairScorer:
    """
    Score a specific (acquirer, target) pair using a logit formula.

    Usage::

        scorer = AcquirerPairScorer()
        features = PairFeatures(
            asset_quality=0.80,
            acquirer_appetite=0.70,
            ta_overlap=0.90,
            ta_strategic_fit=ta_strategic_fit_score(0.90),  # 1.00
            size_fit=0.65,
            acquirer_urgency=0.75,
            integration_capacity=0.50,
        )
        result = scorer.score(features)
        # result.probability ≈ 0.97
    """

    def score(self, features: PairFeatures) -> PairScore:
        """Compute the pair probability and return a full PairScore."""
        contributions = {}

        log_odds = INTERCEPT

        for feature, weight in WEIGHTS.items():
            value = getattr(features, feature)
            contrib = weight * value
            contributions[feature] = round(contrib, 5)
            log_odds += contrib

        # Interaction term: urgency × quality
        interaction = (
            W_URGENCY_QUALITY_INTERACTION
            * features.acquirer_urgency
            * features.asset_quality
        )
        log_odds += interaction

        prob = self._sigmoid(log_odds)

        return PairScore(
            probability=round(prob, 5),
            log_odds=round(log_odds, 5),
            feature_contributions=contributions,
            interaction_contribution=round(interaction, 5),
        )

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Numerically stable sigmoid."""
        if x >= 0:
            return 1.0 / (1.0 + math.exp(-x))
        exp_x = math.exp(x)
        return exp_x / (1.0 + exp_x)
