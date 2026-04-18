"""Fuse multi-source signals into a unified per-asset intelligence card."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class AssetSignalBundle(BaseModel):
    """All available signals for one asset at a point in time."""

    asset_id: str
    ticker: str
    as_of: datetime
    # Market signals
    model_pos: Optional[float] = None
    implied_pos: Optional[float] = None
    pos_gap: Optional[float] = None  # model - implied (positive = underpriced on PoS)
    model_peak_sales_millions: Optional[float] = None
    implied_peak_sales_millions: Optional[float] = None
    peak_sales_gap_millions: Optional[float] = None
    model_ev_millions: Optional[float] = None
    market_ev_millions: Optional[float] = None
    ev_gap_pct: Optional[float] = None  # (model_ev - market_ev) / market_ev
    # Thesis signals
    thesis_confidence: Optional[float] = None  # 0-1
    thesis_conviction: Optional[str] = None  # "high"/"medium"/"low"
    active_kill_criteria_count: int = 0
    # Catalyst signals
    best_catalyst_expected_return_pct: Optional[float] = None
    best_catalyst_downside_pct: Optional[float] = None
    best_catalyst_setup_score: Optional[float] = None
    days_to_next_catalyst: Optional[int] = None
    # Financing signals
    financing_risk_score: Optional[float] = None  # 0-1
    months_runway: Optional[float] = None
    pre_catalyst_financing_probability: Optional[float] = None
    # Science signals
    science_score: Optional[float] = None  # 0-1
    design_score: Optional[float] = None  # 0-1
    safety_risk_tier: Optional[str] = None
    # Competition signals
    competition_risk_score: Optional[float] = None  # 0-1 (1 = highest risk)
    competitor_count: int = 0
    # Portfolio signals
    current_position_pct: float = 0.0
    ta_remaining_budget_pct: Optional[float] = None
    liquidity_score: Optional[float] = None  # 0-1


class FusedSignalCard(BaseModel):
    """One unified intelligence card per asset."""

    asset_id: str
    ticker: str
    fused_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    bundle: AssetSignalBundle
    # Composite sub-scores (0-1)
    valuation_score: float  # from ev_gap_pct + pos_gap
    catalyst_score: float  # from catalyst expected return + setup score
    risk_score: float  # from financing + competition (1 = highest risk; invert for ranking)
    science_score: float  # from science + design scores
    portfolio_score: float  # from remaining budget + liquidity
    # Final composite (0-1, higher = better opportunity)
    composite_score: float
    # Recommendation
    action: str  # "add" / "hold" / "reduce" / "avoid" / "watchlist"
    conviction: str  # "high" / "medium" / "low"
    rationale: str
    top_positives: list[str]
    top_risks: list[str]


# ---------------------------------------------------------------------------
# Weight constants
# ---------------------------------------------------------------------------

_WEIGHT_VALUATION = 0.30
_WEIGHT_CATALYST = 0.25
_WEIGHT_RISK = 0.20
_WEIGHT_SCIENCE = 0.15
_WEIGHT_PORTFOLIO = 0.10


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class SignalFusionEngine:
    """
    Fuse AssetSignalBundle → FusedSignalCard.

    Weights:
      valuation:  0.30
      catalyst:   0.25
      risk:       0.20  (inverted — higher risk = lower score)
      science:    0.15
      portfolio:  0.10

    Action thresholds:
      composite >= 0.65 → add
      composite >= 0.50 → hold
      composite >= 0.35 → watchlist
      else            → avoid

    Conviction:
      composite >= 0.70 → high
      composite >= 0.50 → medium
      else             → low
    """

    # ------------------------------------------------------------------
    # Sub-score computation
    # ------------------------------------------------------------------

    def _valuation_score(self, b: AssetSignalBundle) -> float:
        scores: list[float] = []
        if b.ev_gap_pct is not None:
            scores.append(_clamp(0.5 + b.ev_gap_pct * 2))
        if b.pos_gap is not None:
            scores.append(_clamp(0.5 + b.pos_gap * 5))
        if not scores:
            return 0.5
        return sum(scores) / len(scores)

    def _catalyst_score(self, b: AssetSignalBundle) -> float:
        if b.best_catalyst_setup_score is not None:
            return _clamp(b.best_catalyst_setup_score)
        if b.best_catalyst_expected_return_pct is not None:
            return _clamp(b.best_catalyst_expected_return_pct / 50.0)
        return 0.5

    def _risk_score(self, b: AssetSignalBundle) -> float:
        components: list[float] = []
        if b.financing_risk_score is not None:
            components.append(1.0 - _clamp(b.financing_risk_score))
        if b.competition_risk_score is not None:
            components.append(1.0 - _clamp(b.competition_risk_score))
        if not components:
            return 0.5
        return sum(components) / len(components)

    def _science_score(self, b: AssetSignalBundle) -> float:
        components: list[float] = []
        if b.science_score is not None:
            components.append(_clamp(b.science_score))
        if b.design_score is not None:
            components.append(_clamp(b.design_score))
        if not components:
            return 0.5
        return sum(components) / len(components)

    def _portfolio_score(self, b: AssetSignalBundle) -> float:
        components: list[float] = []
        if b.ta_remaining_budget_pct is not None:
            components.append(_clamp(b.ta_remaining_budget_pct))
        if b.liquidity_score is not None:
            components.append(_clamp(b.liquidity_score))
        if not components:
            return 0.5
        return sum(components) / len(components)

    # ------------------------------------------------------------------
    # Rationale builder
    # ------------------------------------------------------------------

    def _build_positives(self, b: AssetSignalBundle) -> list[str]:
        positives: list[str] = []
        if b.ev_gap_pct is not None and b.ev_gap_pct > 0.2:
            positives.append(f"model EV exceeds market by {b.ev_gap_pct:.0%}")
        if b.pos_gap is not None and b.pos_gap > 0.1:
            positives.append(f"PoS gap {b.pos_gap:.0%} above implied")
        if b.best_catalyst_setup_score is not None and b.best_catalyst_setup_score > 0.6:
            positives.append("strong catalyst setup")
        if b.science_score is not None and b.science_score > 0.7:
            positives.append("high science confidence")
        return positives

    def _build_risks(self, b: AssetSignalBundle) -> list[str]:
        risks: list[str] = []
        if b.financing_risk_score is not None and b.financing_risk_score > 0.6:
            risks.append("elevated financing risk")
        if b.active_kill_criteria_count > 0:
            risks.append(f"{b.active_kill_criteria_count} kill criteria active")
        if b.competition_risk_score is not None and b.competition_risk_score > 0.6:
            risks.append("competitive pressure high")
        return risks

    def _build_rationale(
        self,
        composite: float,
        action: str,
        positives: list[str],
        risks: list[str],
    ) -> str:
        parts: list[str] = [f"Composite score {composite:.2f} → {action}."]
        if positives:
            parts.append("Positives: " + "; ".join(positives[:2]) + ".")
        if risks:
            parts.append("Risks: " + "; ".join(risks[:2]) + ".")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Main fuse
    # ------------------------------------------------------------------

    def fuse(self, bundle: AssetSignalBundle) -> FusedSignalCard:
        val_score = self._valuation_score(bundle)
        cat_score = self._catalyst_score(bundle)
        risk_score = self._risk_score(bundle)
        sci_score = self._science_score(bundle)
        port_score = self._portfolio_score(bundle)

        composite = _clamp(
            val_score * _WEIGHT_VALUATION
            + cat_score * _WEIGHT_CATALYST
            + risk_score * _WEIGHT_RISK
            + sci_score * _WEIGHT_SCIENCE
            + port_score * _WEIGHT_PORTFOLIO
        )

        # Action
        if composite >= 0.65:
            action = "add"
        elif composite >= 0.50:
            action = "hold"
        elif composite >= 0.35:
            action = "watchlist"
        else:
            action = "avoid"

        # Conviction
        if composite >= 0.70:
            conviction = "high"
        elif composite >= 0.50:
            conviction = "medium"
        else:
            conviction = "low"

        top_positives = self._build_positives(bundle)
        top_risks = self._build_risks(bundle)
        rationale = self._build_rationale(composite, action, top_positives, top_risks)

        return FusedSignalCard(
            asset_id=bundle.asset_id,
            ticker=bundle.ticker,
            bundle=bundle,
            valuation_score=val_score,
            catalyst_score=cat_score,
            risk_score=risk_score,
            science_score=sci_score,
            portfolio_score=port_score,
            composite_score=composite,
            action=action,
            conviction=conviction,
            rationale=rationale,
            top_positives=top_positives,
            top_risks=top_risks,
        )

    def fuse_batch(self, bundles: list[AssetSignalBundle]) -> list[FusedSignalCard]:
        return sorted(
            [self.fuse(b) for b in bundles],
            key=lambda c: c.composite_score,
            reverse=True,
        )
