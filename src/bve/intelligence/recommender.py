"""7-domain signal fusion engine that produces a final recommendation."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from bve.trading.signal_generator import TradeSignal


class DomainSignal(BaseModel, frozen=True):
    domain: str      # e.g. "valuation_gap", "science", "catalyst_ev"
    score: float     # 0.0-1.0
    weight: float    # domain weight in fusion
    present: bool    # False = data missing → use neutral 0.5


class RecommendationStrength(str, Enum):
    STRONG = "strong"      # fused_score >= 0.70
    MODERATE = "moderate"  # fused_score >= 0.55
    WEAK = "weak"          # fused_score >= 0.40
    NEUTRAL = "neutral"    # fused_score >= 0.30
    NEGATIVE = "negative"  # fused_score < 0.30


class FusedRecommendation(BaseModel, frozen=True):
    asset_id: str
    fused_score: float                    # weighted average of domain signals
    strength: RecommendationStrength      # auto-derived from fused_score
    domain_signals: list[DomainSignal]
    missing_domains: list[str]            # domains where present=False
    trade_signal: TradeSignal | None      # None if no trade warranted
    rationale: str


# Domain weights (must sum to 1.0):
DOMAIN_WEIGHTS: dict[str, float] = {
    "valuation_gap":   0.25,   # pos_delta from implied expectations
    "science":         0.20,   # science diligence score
    "catalyst_ev":     0.20,   # expected value from catalyst tree
    "financing":       0.15,   # financing risk (inverted — low risk = high score)
    "competition":     0.10,   # readthrough + competition graph
    "portfolio_fit":   0.05,   # concentration + capacity
    "ma_premium":      0.05,   # acquisition fit score
}

_NEUTRAL_SCORE = 0.5


def _derive_strength(fused_score: float) -> RecommendationStrength:
    if fused_score >= 0.70:
        return RecommendationStrength.STRONG
    if fused_score >= 0.55:
        return RecommendationStrength.MODERATE
    if fused_score >= 0.40:
        return RecommendationStrength.WEAK
    if fused_score >= 0.30:
        return RecommendationStrength.NEUTRAL
    return RecommendationStrength.NEGATIVE


def fuse_signals(
    asset_id: str,
    signals: dict[str, float | None],   # domain -> score (None = missing)
    trade_signal: TradeSignal | None = None,
) -> FusedRecommendation:
    """
    For each domain:
    - If signals[domain] is None: use 0.5 (neutral), mark as missing
    - fused_score = sum(weight × score) / sum(weights)
      [equals weighted avg since weights sum to 1.0]
    - strength derived from fused_score thresholds
    """
    domain_signals: list[DomainSignal] = []
    missing_domains: list[str] = []

    total_weight = 0.0
    weighted_sum = 0.0

    for domain, weight in DOMAIN_WEIGHTS.items():
        raw_score = signals.get(domain)
        present = raw_score is not None
        score = raw_score if raw_score is not None else _NEUTRAL_SCORE

        if not present:
            missing_domains.append(domain)

        domain_signals.append(DomainSignal(
            domain=domain,
            score=score,
            weight=weight,
            present=present,
        ))

        weighted_sum += weight * score
        total_weight += weight

    # Weighted average (total_weight should equal 1.0)
    fused_score = weighted_sum / total_weight if total_weight > 0 else _NEUTRAL_SCORE
    fused_score = min(1.0, max(0.0, fused_score))

    strength = _derive_strength(fused_score)

    if missing_domains:
        missing_note = f"Missing domains (neutral 0.5 used): {', '.join(missing_domains)}. "
    else:
        missing_note = "All 7 domains present. "

    rationale = (
        f"{missing_note}"
        f"fused_score={fused_score:.4f}, strength={strength.value}."
    )

    return FusedRecommendation(
        asset_id=asset_id,
        fused_score=fused_score,
        strength=strength,
        domain_signals=domain_signals,
        missing_domains=missing_domains,
        trade_signal=trade_signal,
        rationale=rationale,
    )


def screen_recommendations(
    recommendations: list[FusedRecommendation],
    min_strength: RecommendationStrength = RecommendationStrength.WEAK,
    require_trade_signal: bool = False,
) -> list[FusedRecommendation]:
    """Filter and sort by fused_score descending."""
    _strength_order = {
        RecommendationStrength.NEGATIVE: 0,
        RecommendationStrength.NEUTRAL: 1,
        RecommendationStrength.WEAK: 2,
        RecommendationStrength.MODERATE: 3,
        RecommendationStrength.STRONG: 4,
    }

    min_strength_rank = _strength_order[min_strength]

    filtered = [
        rec for rec in recommendations
        if _strength_order[rec.strength] >= min_strength_rank
        and (not require_trade_signal or rec.trade_signal is not None)
    ]

    return sorted(filtered, key=lambda r: r.fused_score, reverse=True)
