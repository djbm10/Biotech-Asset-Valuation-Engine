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

INTERCEPT: float = -0.40   # prior log-odds slightly below 0.5 (deals are rare)

WEIGHTS: dict[str, float] = {
    "asset_quality":          +1.80,  # strongest predictor of deal completion
    "acquirer_appetite":      +1.20,  # acquirer actively in-market
    "ta_overlap":             +0.90,  # same TA = easier due diligence
    "size_fit":               +0.70,  # target size fits acquirer's deal range
    "acquirer_urgency":       +1.10,  # patent cliff / pipeline gap
    "integration_capacity":   +0.60,  # acquirer can absorb the deal
}

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
    ta_overlap           : 0–1, therapeutic area / indication alignment
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
    size_fit: float
    acquirer_urgency: float
    integration_capacity: float
    acquirer_id: Optional[str] = None
    target_ticker: Optional[str] = None
    as_of_date: Optional[str] = None

    def __post_init__(self) -> None:
        for fname in ("asset_quality", "acquirer_appetite", "ta_overlap",
                      "size_fit", "acquirer_urgency", "integration_capacity"):
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
            size_fit=0.65,
            acquirer_urgency=0.75,
            integration_capacity=0.50,
        )
        result = scorer.score(features)
        # result.probability ≈ 0.82
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
