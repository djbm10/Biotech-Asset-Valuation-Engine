"""
Opportunity ranking engine for tracked assets.

Ranks assets by a composite score combining:
  1. Valuation component — mispricing mode (model vs market cap) when market
     cap is available; sigmoid(|delta_npv|/scale) otherwise.
  2. Confidence component — extraction confidence from the most recent signal.
  3. Recency component — exponential decay: 0.5^(days_elapsed / half_life).
  4. Event-type component — configurable priority weight per event type.

The mispricing score makes ranking market-centric:
    mispricing = (after_rnpv - market_cap) / market_cap
    opportunity = f(|mispricing|) × confidence × recency × event_weight

This surfaces assets where the model says the market is wrong — which is the
actual signal an investor cares about. Pure delta-based ranking only measures
internal model changes, not market opportunities.

All computation is deterministic and reproducible: identical inputs → identical
output every time.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import KnowledgeStore, StoredValuationDiff
from bve.intelligence.market_expectations import MarketExpectation
from bve.intelligence.schemas.signals import StructuredSignal

# ---------------------------------------------------------------------------
# Default event-type priority scores (0.0–1.0)
# Override per-key via RankingConfig.event_type_scores in watchlist.yaml.
# ---------------------------------------------------------------------------
DEFAULT_EVENT_TYPE_SCORES: dict[str, float] = {
    "fda_approval":            1.0,
    "safety_signal":           1.0,
    "program_discontinuation": 1.0,
    "fda_rejection":           0.9,
    "regulatory_hold":         0.9,
    "trial_readout":           0.8,
    "interim_analysis":        0.7,
    "fda_designation":         0.7,
    "label_expansion":         0.6,
    "partnership":             0.5,
    "endpoint_change":         0.5,
    "publication":             0.4,
    "conference_presentation": 0.4,
    "competitor_event":        0.35,
    "payer_coverage":          0.35,
    "enrollment_update":       0.3,
    "patent_event":            0.25,
    "sec_filing":              0.2,
    "financing":               0.15,
    "management_change":       0.1,
}
_DEFAULT_EVENT_SCORE = 0.3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class RankingConfig(BaseModel):
    """
    Weights and parameters for the composite opportunity score.

    Weights are unnormalized — they are divided by their sum, so only relative
    magnitudes matter. Setting a weight to 0 excludes that component entirely.
    """

    valuation_weight: float = Field(default=0.50, ge=0.0)
    confidence_weight: float = Field(default=0.25, ge=0.0)
    recency_weight: float = Field(default=0.15, ge=0.0)
    event_type_weight: float = Field(default=0.10, ge=0.0)

    recency_half_life_days: float = Field(default=14.0, gt=0.0)

    # Sigmoid scale for delta-mode normalization (in $M).
    # A delta of `valuation_sigmoid_scale` maps to sigmoid midpoint (~0.46).
    valuation_sigmoid_scale: float = Field(default=50.0, gt=0.0)

    # When True and market_cap_millions is available, use mispricing mode.
    use_market_cap_normalization: bool = True

    top_n: int = Field(default=10, ge=1)

    # Per-event-type score overrides (merged with DEFAULT_EVENT_TYPE_SCORES).
    # Example in YAML:
    #   event_type_scores:
    #     fda_approval: 1.0
    #     trial_readout: 0.9
    event_type_scores: dict[str, float] = Field(default_factory=dict)

    def resolved_event_score(self, event_type: Optional[str]) -> float:
        """Return priority score for *event_type*, merging defaults with config overrides."""
        merged = {**DEFAULT_EVENT_TYPE_SCORES, **self.event_type_scores}
        return merged.get(event_type or "", _DEFAULT_EVENT_SCORE)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class RankedOpportunity(BaseModel):
    """One ranked asset with full score decomposition for auditability."""

    rank: int
    asset_id: str
    company_id: str
    ticker: Optional[str] = None
    composite_score: float

    # Normalized components (each 0.0–1.0 before weighting)
    valuation_component: float
    confidence_component: float
    recency_component: float
    event_type_component: float

    # Underlying raw data
    delta_npv_millions: float
    after_rnpv_millions: Optional[float] = None
    market_cap_millions: Optional[float] = None
    # Positive = model says undervalued vs market; negative = overvalued.
    mispricing_score: Optional[float] = None

    extraction_confidence: float
    signal_event_type: Optional[str] = None
    last_diff_at: Optional[datetime] = None

    # Market expectation gap (Wave 1D): positive = market more pessimistic than model.
    # None when no market expectation data is available.
    implied_pos: Optional[float] = None
    model_pos: Optional[float] = None
    pos_gap: Optional[float] = None

    explanation: str


class RankingResult(BaseModel):
    """Full ranking run output."""

    ranked_at: datetime
    config: RankingConfig
    since_filter: Optional[datetime] = None
    opportunities: list[RankedOpportunity] = Field(default_factory=list)
    assets_evaluated: int = 0
    assets_with_diffs: int = 0
    assets_skipped_no_diffs: int = 0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class AssetRankingEngine:
    """
    Deterministic, reproducible opportunity scorer.

    Pass *knowledge_store* for production use (loads diffs from the DB).
    Omit it for testing (pass pre-loaded data to rank_assets() directly).
    """

    def __init__(
        self,
        config: Optional[RankingConfig] = None,
        *,
        knowledge_store: Optional[KnowledgeStore] = None,
    ) -> None:
        self.config = config or RankingConfig()
        self.knowledge = knowledge_store

    def rank_from_watchlist_config(
        self,
        watchlist_config,
        *,
        ranked_at: Optional[datetime] = None,
        since: Optional[datetime] = None,
    ) -> RankingResult:
        """
        Primary entry point — loads diffs and signals from the knowledge store
        for every asset in *watchlist_config*.
        """
        if ranked_at is None:
            ranked_at = datetime.now(timezone.utc)

        assets = watchlist_config.watchlist
        diffs_by_asset: dict[str, list[StoredValuationDiff]] = {}
        signals_by_asset: dict[str, Optional[StructuredSignal]] = {}
        expectations_by_asset: dict[str, Optional[MarketExpectation]] = {}
        market_caps: dict[str, Optional[float]] = {}
        date_from = since.date() if since else None

        for asset in assets:
            key = _asset_key(asset)

            # Market cap: explicit config field takes priority; fall back to yfinance.
            mc: Optional[float] = getattr(asset, "market_cap_millions", None)
            if mc is None and asset.ticker and self.config.use_market_cap_normalization:
                mc = _fetch_market_cap_millions(asset.ticker)
            market_caps[key] = mc

            # Load diffs from knowledge store.
            if self.knowledge is not None:
                diffs = self.knowledge.get_valuation_diffs(
                    company_id=asset.company_id,
                    asset_id=asset.asset_id,
                    date_from=date_from,
                    limit=50,
                )
                # Fetch signal for the most recent diff to get event_type + confidence.
                if diffs:
                    sig = self.knowledge.get_structured_signal_by_event_id(diffs[0].event_id)
                    signals_by_asset[key] = sig

                # Load latest market expectation (implied PoS gap).
                exp = self.knowledge.get_latest_expectation(asset.asset_id)
                expectations_by_asset[key] = exp
            else:
                diffs = []
                signals_by_asset[key] = None
                expectations_by_asset[key] = None

            diffs_by_asset[key] = diffs

        return self.rank_assets(
            assets,
            diffs_by_asset=diffs_by_asset,
            market_caps=market_caps,
            signals_by_asset=signals_by_asset,
            expectations_by_asset=expectations_by_asset,
            ranked_at=ranked_at,
            since=since,
        )

    def rank_assets(
        self,
        assets,
        diffs_by_asset: dict[str, list[StoredValuationDiff]],
        *,
        market_caps: Optional[dict[str, Optional[float]]] = None,
        signals_by_asset: Optional[dict[str, Optional[StructuredSignal]]] = None,
        expectations_by_asset: Optional[dict[str, Optional[MarketExpectation]]] = None,
        ranked_at: Optional[datetime] = None,
        since: Optional[datetime] = None,
    ) -> RankingResult:
        """
        Lower-level entry point for testing: accepts pre-loaded data.
        Stateless — identical inputs always produce identical output.
        """
        if ranked_at is None:
            ranked_at = datetime.now(timezone.utc)
        if market_caps is None:
            market_caps = {}
        if signals_by_asset is None:
            signals_by_asset = {}
        if expectations_by_asset is None:
            expectations_by_asset = {}

        scored: list[RankedOpportunity] = []
        assets_with_diffs = 0
        assets_skipped = 0

        for asset in assets:
            key = _asset_key(asset)
            diffs = diffs_by_asset.get(key, [])
            if not diffs:
                assets_skipped += 1
                continue
            assets_with_diffs += 1
            opp = self._score_asset(
                asset,
                diffs,
                ranked_at=ranked_at,
                market_cap=market_caps.get(key),
                signal=signals_by_asset.get(key),
                expectation=expectations_by_asset.get(key),
            )
            if opp is not None:
                scored.append(opp)

        # Sort descending by composite score (stable — preserves insert order on ties).
        scored.sort(key=lambda o: o.composite_score, reverse=True)
        top = scored[: self.config.top_n]
        # Assign ranks after sort (frozen model — reconstruct with rank set).
        ranked = [opp.model_copy(update={"rank": i + 1}) for i, opp in enumerate(top)]

        return RankingResult(
            ranked_at=ranked_at,
            config=self.config,
            since_filter=since,
            opportunities=ranked,
            assets_evaluated=len(assets),
            assets_with_diffs=assets_with_diffs,
            assets_skipped_no_diffs=assets_skipped,
        )

    def _score_asset(
        self,
        asset,
        diffs: list[StoredValuationDiff],
        *,
        ranked_at: datetime,
        market_cap: Optional[float] = None,
        signal: Optional[StructuredSignal] = None,
        expectation: Optional[MarketExpectation] = None,
    ) -> Optional[RankedOpportunity]:
        if not diffs:
            return None

        # Most recent diff is the primary signal.
        latest = max(diffs, key=lambda d: d.created_at)

        # Per-asset ranking config overrides (e.g. event_type_weight: 0.2).
        cfg = self.config
        overrides: dict = getattr(asset, "ranking_overrides", None) or {}
        if overrides:
            valid = {k: v for k, v in overrides.items() if hasattr(cfg, k)}
            if valid:
                cfg = cfg.model_copy(update=valid)

        after_rnpv = latest.valuation_after.get("rnpv_millions")
        delta_npv = latest.delta_npv

        # --- Valuation component ---
        mispricing: Optional[float] = None
        if (
            cfg.use_market_cap_normalization
            and market_cap is not None
            and market_cap > 0
            and after_rnpv is not None
        ):
            # Mispricing mode: (model_value - market_cap) / market_cap
            # Positive → model says undervalued; negative → overvalued.
            mispricing = (float(after_rnpv) - market_cap) / market_cap
            # Normalize: sigmoid anchored so 50% mispricing ≈ midpoint.
            valuation_component = _sigmoid(abs(mispricing) / 0.5)
        else:
            # Delta mode: fallback when no market cap available.
            valuation_component = _sigmoid(abs(delta_npv) / cfg.valuation_sigmoid_scale)

        # --- Confidence component ---
        # Prefer signal.extraction_confidence; fall back to a neutral 0.5.
        if signal is not None:
            conf = float(signal.extraction_confidence or 0.5)
        else:
            conf = 0.5
        confidence_component = max(0.0, min(1.0, conf))

        # --- Recency component ---
        recency_component = _recency_score(
            latest.created_at, ranked_at, cfg.recency_half_life_days
        )

        # --- Event-type component ---
        event_type_str: Optional[str] = None
        if signal is not None:
            event_type_str = signal.event_type.value
        elif latest.assumptions_changed:
            event_type_str = latest.assumptions_changed[0].get("event_type")
        event_type_component = cfg.resolved_event_score(event_type_str)

        # --- Composite score (weighted sum, normalized by total weight) ---
        weights = [
            cfg.valuation_weight,
            cfg.confidence_weight,
            cfg.recency_weight,
            cfg.event_type_weight,
        ]
        components = [
            valuation_component,
            confidence_component,
            recency_component,
            event_type_component,
        ]
        total_weight = sum(weights)
        composite = (
            sum(w * c for w, c in zip(weights, components)) / total_weight
            if total_weight > 0
            else 0.0
        )

        explanation = _build_explanation(
            asset_id=asset.asset_id,
            company_id=asset.company_id,
            delta_npv=delta_npv,
            after_rnpv=float(after_rnpv) if after_rnpv is not None else None,
            market_cap=market_cap,
            mispricing=mispricing,
            confidence=confidence_component,
            recency=recency_component,
            event_type_str=event_type_str,
            event_type_score=event_type_component,
            composite=composite,
        )

        return RankedOpportunity(
            rank=0,  # assigned after sort
            asset_id=asset.asset_id,
            company_id=asset.company_id,
            ticker=getattr(asset, "ticker", None),
            composite_score=round(composite, 6),
            valuation_component=round(valuation_component, 6),
            confidence_component=round(confidence_component, 6),
            recency_component=round(recency_component, 6),
            event_type_component=round(event_type_component, 6),
            delta_npv_millions=delta_npv,
            after_rnpv_millions=float(after_rnpv) if after_rnpv is not None else None,
            market_cap_millions=market_cap,
            mispricing_score=round(mispricing, 4) if mispricing is not None else None,
            extraction_confidence=confidence_component,
            signal_event_type=event_type_str,
            last_diff_at=latest.created_at,
            implied_pos=expectation.implied_pos if expectation is not None else None,
            model_pos=expectation.model_pos if expectation is not None else None,
            pos_gap=expectation.pos_gap if expectation is not None else None,
            explanation=explanation,
        )


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def _asset_key(asset) -> str:
    return f"{asset.company_id}::{asset.asset_id}"


def _sigmoid(x: float) -> float:
    """Maps [0, ∞) → [0, 1) via 2/(1+exp(-x)) - 1."""
    return 2.0 / (1.0 + math.exp(-max(0.0, x))) - 1.0


def _recency_score(last_diff_at: datetime, ranked_at: datetime, half_life_days: float) -> float:
    """
    Exponential half-life decay.
    score = 0.5^(elapsed_days / half_life_days)
    At t=0: 1.0. At t=half_life: 0.5. At t=2×half_life: 0.25.
    """
    if last_diff_at.tzinfo is None:
        last_diff_at = last_diff_at.replace(tzinfo=timezone.utc)
    elapsed_days = max(0.0, (ranked_at - last_diff_at).total_seconds() / 86400.0)
    return 0.5 ** (elapsed_days / half_life_days)


def _build_explanation(
    *,
    asset_id: str,
    company_id: str,
    delta_npv: float,
    after_rnpv: Optional[float],
    market_cap: Optional[float],
    mispricing: Optional[float],
    confidence: float,
    recency: float,
    event_type_str: Optional[str],
    event_type_score: float,
    composite: float,
) -> str:
    parts = [f"{asset_id} ({company_id})"]
    if mispricing is not None and market_cap is not None and after_rnpv is not None:
        direction = "undervalued" if mispricing > 0 else "overvalued"
        parts.append(
            f"Model rNPV ${after_rnpv:.0f}M vs market cap ${market_cap:.0f}M"
            f" → {abs(mispricing) * 100:.0f}% {direction}"
        )
    else:
        sign = "+" if delta_npv >= 0 else ""
        parts.append(f"rNPV delta {sign}${delta_npv:.1f}M (no market cap for mispricing)")
    if event_type_str:
        parts.append(f"Event: {event_type_str} (priority={event_type_score:.2f})")
    parts.append(f"Confidence {confidence:.2f}, recency {recency:.2f}")
    parts.append(f"Composite score {composite:.4f}")
    return ". ".join(parts) + "."


def _fetch_market_cap_millions(ticker: str, timeout: int = 10) -> Optional[float]:
    """Fetch market cap via yfinance. Returns None on any failure (no raise)."""
    try:
        import yfinance as yf  # type: ignore[import-untyped]
        info = yf.Ticker(ticker).fast_info
        mc = getattr(info, "market_cap", None)
        if mc and float(mc) > 0:
            return float(mc) / 1_000_000.0
    except Exception:
        pass
    return None
