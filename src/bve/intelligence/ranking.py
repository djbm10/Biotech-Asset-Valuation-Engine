"""
Opportunity ranking for tracked assets.

Sprint 5 scoring contract:

    mispricing = (model_rnpv - market_cap) / market_cap

    score = (
        mispricing * 0.50
        + confidence * 0.25
        + recency * 0.15
        + event_priority * 0.10
    )

Ranking is DB-backed only on the read path:
valuation_diffs -> structured_signals -> market_prices.

No live market-data lookups or LLM calls occur here.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, PrivateAttr

from bve.intelligence.knowledge_layer import KnowledgeStore, StoredValuationDiff
from bve.intelligence.market_expectations import (
    ImpliedPoSEstimator,
    compute_market_mispricing,
)
from bve.intelligence.schemas.signals import StructuredSignal
from bve.models.catalyst_model import CatalystValuation

DEFAULT_EVENT_TYPE_SCORES: dict[str, float] = {
    "fda_approval": 1.0,
    "safety_signal": 1.0,
    "program_discontinuation": 1.0,
    "fda_rejection": 0.9,
    "regulatory_hold": 0.9,
    "trial_readout": 0.8,
    "interim_analysis": 0.7,
    "fda_designation": 0.7,
    "label_expansion": 0.6,
    "partnership": 0.5,
    "endpoint_change": 0.5,
    "publication": 0.4,
    "conference_presentation": 0.4,
    "competitor_event": 0.35,
    "payer_coverage": 0.35,
    "enrollment_update": 0.3,
    "patent_event": 0.25,
    "sec_filing": 0.2,
    "financing": 0.15,
    "management_change": 0.1,
}
_DEFAULT_EVENT_SCORE = 0.3
_DEFAULT_CONFIDENCE_SCALING = 1.0
_MAX_CONFIDENCE_SCALING = 2.0
_DEFAULT_RANKING_CALIBRATION_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "ranking_calibration.yaml"
)


class RankingConfig(BaseModel):
    valuation_weight: float = Field(default=0.50, ge=0.0)
    confidence_weight: float = Field(default=0.25, ge=0.0)
    recency_weight: float = Field(default=0.15, ge=0.0)
    event_type_weight: float = Field(default=0.10, ge=0.0)
    recency_half_life_days: float = Field(default=14.0, gt=0.0)
    valuation_sigmoid_scale: float = Field(default=50.0, gt=0.0)
    use_market_cap_normalization: bool = True
    top_n: int = Field(default=10, ge=1)
    event_type_scores: dict[str, float] = Field(default_factory=dict)
    calibration_path: Optional[str] = None
    use_calibration_file: bool = True

    _calibration_loaded: bool = PrivateAttr(default=False)
    _calibrated_event_scores: dict[str, float] = PrivateAttr(default_factory=dict)
    _calibrated_confidence_scaling_factor: float = PrivateAttr(
        default=_DEFAULT_CONFIDENCE_SCALING
    )

    def _ensure_calibration_loaded(self) -> None:
        if self._calibration_loaded:
            return
        self._calibration_loaded = True
        if not self.use_calibration_file:
            return

        path = (
            Path(self.calibration_path)
            if self.calibration_path
            else _DEFAULT_RANKING_CALIBRATION_PATH
        )
        if not path.exists():
            return
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return

        raw_weights = payload.get("event_type_weights") or {}
        if isinstance(raw_weights, dict):
            for key, value in raw_weights.items():
                try:
                    parsed = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(parsed):
                    self._calibrated_event_scores[str(key)] = max(parsed, 0.0)

        raw_scaling = payload.get("confidence_scaling_factor")
        if raw_scaling is None:
            return
        try:
            scaling = float(raw_scaling)
        except (TypeError, ValueError):
            return
        if scaling > 0 and math.isfinite(scaling):
            self._calibrated_confidence_scaling_factor = min(scaling, _MAX_CONFIDENCE_SCALING)

    def resolved_event_score(self, event_type: Optional[str]) -> float:
        self._ensure_calibration_loaded()
        merged = {
            **DEFAULT_EVENT_TYPE_SCORES,
            **self._calibrated_event_scores,
            **self.event_type_scores,
        }
        return merged.get(event_type or "", _DEFAULT_EVENT_SCORE)

    def resolved_confidence_scaling_factor(self) -> float:
        self._ensure_calibration_loaded()
        return self._calibrated_confidence_scaling_factor


class RankedOpportunity(BaseModel):
    rank: int
    asset_id: str
    company_id: str
    event_id: str
    ticker: Optional[str] = None

    score: float
    composite_score: float

    valuation_component: float
    confidence_component: float
    recency_component: float
    event_type_component: float

    mispricing: Optional[float] = None
    mispricing_score: Optional[float] = None
    confidence: float
    extraction_confidence: float
    days_since_event: int
    event_priority: float

    delta_npv_millions: float
    after_rnpv_millions: Optional[float] = None
    market_cap_millions: Optional[float] = None
    signal_date: Optional[date] = None
    signal_id: Optional[str] = None
    signal_trial_phase: Optional[str] = None
    signal_event_type: Optional[str] = None
    last_diff_at: Optional[datetime] = None
    intrinsic_value_millions: Optional[float] = None
    base_rank_score: Optional[float] = None
    final_rank_score: Optional[float] = None
    catalyst_score: Optional[float] = None
    catalyst_boost_weight: Optional[float] = None
    catalyst_type: Optional[str] = None
    catalyst_date: Optional[date] = None
    days_to_catalyst: Optional[int] = None
    catalyst_importance: Optional[float] = None
    catalyst_valuation: Optional[CatalystValuation] = None

    implied_pos: Optional[float] = None
    model_pos: Optional[float] = None
    pos_gap: Optional[float] = None

    explanation: str


class RankingResult(BaseModel):
    ranked_at: datetime
    config: RankingConfig
    since_filter: Optional[datetime] = None
    opportunities: list[RankedOpportunity] = Field(default_factory=list)
    assets_evaluated: int = 0
    assets_with_diffs: int = 0
    assets_skipped_no_diffs: int = 0


class AssetRankingEngine:
    def __init__(
        self,
        config: Optional[RankingConfig] = None,
        *,
        knowledge_store: Optional[KnowledgeStore] = None,
    ) -> None:
        self.config = config or RankingConfig()
        self.knowledge = knowledge_store
        self._expectation_estimator = ImpliedPoSEstimator()

    def rank_from_watchlist_config(
        self,
        watchlist_config,
        *,
        ranked_at: Optional[datetime] = None,
        since: Optional[datetime] = None,
    ) -> RankingResult:
        if ranked_at is None:
            ranked_at = datetime.now(timezone.utc)

        assets = watchlist_config.watchlist
        diffs_by_asset: dict[str, list[StoredValuationDiff]] = {}
        signals_by_asset: dict[str, Optional[StructuredSignal]] = {}
        market_caps: dict[str, Optional[float]] = {}
        date_from = since.date() if since else None

        for asset in assets:
            key = _asset_key(asset)

            if self.knowledge is None:
                diffs_by_asset[key] = []
                signals_by_asset[key] = None
                market_caps[key] = None
                continue

            diffs = self.knowledge.get_valuation_diffs(
                company_id=asset.company_id,
                asset_id=asset.asset_id,
                date_from=date_from,
                limit=50,
            )
            latest = max(diffs, key=lambda d: d.created_at) if diffs else None
            signal = (
                self.knowledge.get_structured_signal_by_event_id(latest.event_id)
                if latest is not None
                else None
            )

            diffs_by_asset[key] = diffs
            signals_by_asset[key] = signal
            market_caps[key] = self._resolve_market_cap(
                asset=asset,
                latest_diff=latest,
                signal=signal,
            )

        return self.rank_assets(
            assets,
            diffs_by_asset=diffs_by_asset,
            market_caps=market_caps,
            signals_by_asset=signals_by_asset,
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
        ranked_at: Optional[datetime] = None,
        since: Optional[datetime] = None,
    ) -> RankingResult:
        if ranked_at is None:
            ranked_at = datetime.now(timezone.utc)
        if market_caps is None:
            market_caps = {}
        if signals_by_asset is None:
            signals_by_asset = {}

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
            )
            if opp is not None:
                scored.append(opp)

        scored.sort(key=lambda opp: opp.composite_score, reverse=True)
        ranked = [opp.model_copy(update={"rank": idx + 1}) for idx, opp in enumerate(scored[: self.config.top_n])]

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
        market_cap: Optional[float],
        signal: Optional[StructuredSignal],
    ) -> Optional[RankedOpportunity]:
        latest = max(diffs, key=lambda diff: diff.created_at)

        cfg = self.config
        overrides: dict = getattr(asset, "ranking_overrides", None) or {}
        if overrides:
            valid = {key: value for key, value in overrides.items() if hasattr(cfg, key)}
            if valid:
                cfg = cfg.model_copy(update=valid)

        after_rnpv = latest.valuation_after.get("rnpv_millions")
        after_rnpv_millions = float(after_rnpv) if after_rnpv is not None else None
        delta_npv = float(latest.delta_npv)

        market_mispricing = (
            compute_market_mispricing(
                model_rnpv_millions=after_rnpv_millions,
                market_cap_millions=market_cap,
            )
            if cfg.use_market_cap_normalization
            else None
        )
        if market_mispricing is not None:
            valuation_component = market_mispricing.mispricing
            mispricing = market_mispricing.mispricing
        elif cfg.use_market_cap_normalization:
            valuation_component = 0.0
            mispricing = None
        else:
            valuation_component = _sigmoid(abs(delta_npv) / cfg.valuation_sigmoid_scale)
            mispricing = None

        raw_confidence = float(signal.extraction_confidence) if signal is not None else 0.5
        confidence_component = max(
            0.0,
            min(1.0, raw_confidence * cfg.resolved_confidence_scaling_factor()),
        )

        model_pos = _resolve_model_pos(latest)
        expectation = self._expectation_estimator.compute_from_snapshot(
            asset_id=asset.asset_id,
            ticker=getattr(asset, "ticker", None) or asset.asset_id,
            model_rnpv_millions=after_rnpv_millions,
            market_cap_millions=market_cap,
            model_pos=model_pos,
            expectation_date=ranked_at.date(),
        )
        event_type = _resolve_event_type(signal=signal, latest=latest)
        event_priority = cfg.resolved_event_score(event_type)
        signal_date = signal.signal_date if signal is not None else latest.created_at.date()
        days_since_event = max(0, (ranked_at.date() - signal_date).days)
        recency_component = _recency_score_from_days(days_since_event, cfg.recency_half_life_days)

        composite = (
            valuation_component * cfg.valuation_weight
            + confidence_component * cfg.confidence_weight
            + recency_component * cfg.recency_weight
            + event_priority * cfg.event_type_weight
        )
        composite = round(composite, 6)

        # Urgency multiplier: catalysts within 60 days boost the score.
        # score *= (1 + 0.5 * exp(−days_to_catalyst / 30))
        days_to_catalyst: Optional[int] = None
        catalyst_type_str: Optional[str] = None
        catalyst_date_val: Optional[date] = None
        if self.knowledge is not None:
            upcoming = self.knowledge.get_catalyst_events(
                asset_id=asset.asset_id,
                active_only=True,
                days_ahead=60,
            )
            if upcoming:
                next_cat = upcoming[0]
                catalyst_date_val = next_cat.expected_date
                catalyst_type_str = next_cat.catalyst_type.value
                days_to_catalyst = max(0, (catalyst_date_val - ranked_at.date()).days)
                urgency = 1.0 + 0.5 * math.exp(-days_to_catalyst / 30.0)
                composite = round(composite * urgency, 6)

        return RankedOpportunity(
            rank=0,
            asset_id=asset.asset_id,
            company_id=asset.company_id,
            event_id=latest.event_id,
            ticker=getattr(asset, "ticker", None),
            score=composite,
            composite_score=composite,
            valuation_component=round(valuation_component, 6),
            confidence_component=round(confidence_component, 6),
            recency_component=round(recency_component, 6),
            event_type_component=round(event_priority, 6),
            mispricing=mispricing,
            mispricing_score=round(mispricing, 4) if mispricing is not None else None,
            confidence=round(raw_confidence, 6),
            extraction_confidence=round(raw_confidence, 6),
            days_since_event=days_since_event,
            event_priority=round(event_priority, 6),
            delta_npv_millions=delta_npv,
            after_rnpv_millions=after_rnpv_millions,
            market_cap_millions=market_cap,
            signal_date=signal_date,
            signal_id=signal.id if signal is not None else None,
            signal_trial_phase=(
                signal.trial_phase.value
                if signal is not None and signal.trial_phase is not None
                else None
            ),
            signal_event_type=event_type,
            last_diff_at=latest.created_at,
            intrinsic_value_millions=after_rnpv_millions,
            base_rank_score=round(
                valuation_component * cfg.valuation_weight
                + confidence_component * cfg.confidence_weight
                + recency_component * cfg.recency_weight
                + event_priority * cfg.event_type_weight,
                6,
            ),
            final_rank_score=composite,
            catalyst_type=catalyst_type_str,
            catalyst_date=catalyst_date_val,
            days_to_catalyst=days_to_catalyst,
            implied_pos=expectation.implied_success_probability,
            model_pos=expectation.model_pos,
            pos_gap=expectation.pos_gap,
            explanation=_build_explanation(
                asset_id=asset.asset_id,
                company_id=asset.company_id,
                event_id=latest.event_id,
                after_rnpv=after_rnpv_millions,
                market_cap=market_cap,
                mispricing=mispricing,
                confidence=raw_confidence,
                recency=recency_component,
                days_since_event=days_since_event,
                event_type=event_type,
                event_priority=event_priority,
                score=composite,
            ),
        )

    def _resolve_market_cap(
        self,
        *,
        asset,
        latest_diff: Optional[StoredValuationDiff],
        signal: Optional[StructuredSignal],
    ) -> Optional[float]:
        if latest_diff is not None and latest_diff.market_cap_snapshot_millions:
            snapshot = float(latest_diff.market_cap_snapshot_millions)
            if snapshot > 0:
                return snapshot

        ticker = getattr(asset, "ticker", None)
        if self.knowledge is not None and ticker:
            as_of = signal.signal_date if signal is not None else None
            if as_of is None and latest_diff is not None:
                as_of = latest_diff.created_at.date()
            if as_of is not None:
                price = self.knowledge.get_price_on_or_before(ticker, as_of)
                if price is not None and price.market_cap_millions and price.market_cap_millions > 0:
                    return float(price.market_cap_millions)
            latest_price = self.knowledge.get_latest_price(ticker)
            if (
                latest_price is not None
                and latest_price.market_cap_millions
                and latest_price.market_cap_millions > 0
            ):
                return float(latest_price.market_cap_millions)
        return None


def _asset_key(asset) -> str:
    return f"{asset.company_id}::{asset.asset_id}"


def _resolve_event_type(
    *,
    signal: Optional[StructuredSignal],
    latest: StoredValuationDiff,
) -> Optional[str]:
    if signal is not None:
        return signal.event_type.value
    if latest.assumptions_changed:
        return latest.assumptions_changed[0].get("event_type")
    return None


def _resolve_model_pos(latest: StoredValuationDiff) -> Optional[float]:
    for key in ("approval_probability", "cumulative_success_probability", "model_pos"):
        raw = latest.valuation_after.get(key)
        if raw is None:
            continue
        value = float(raw)
        if 0.0 <= value <= 1.0:
            return value
    return None


def _sigmoid(x: float) -> float:
    return 2.0 / (1.0 + math.exp(-max(0.0, x))) - 1.0


def _recency_score(last_diff_at: datetime, ranked_at: datetime, half_life_days: float) -> float:
    if last_diff_at.tzinfo is None:
        last_diff_at = last_diff_at.replace(tzinfo=timezone.utc)
    elapsed_days = max(0.0, (ranked_at - last_diff_at).total_seconds() / 86400.0)
    return _recency_score_from_days(elapsed_days, half_life_days)


def _recency_score_from_days(days_since_event: float, half_life_days: float) -> float:
    return 0.5 ** (max(0.0, days_since_event) / half_life_days)


def _build_explanation(
    *,
    asset_id: str,
    company_id: str,
    event_id: str,
    after_rnpv: Optional[float],
    market_cap: Optional[float],
    mispricing: Optional[float],
    confidence: float,
    recency: float,
    days_since_event: int,
    event_type: Optional[str],
    event_priority: float,
    score: float,
) -> str:
    parts = [f"{asset_id} ({company_id}) event={event_id}"]
    if mispricing is not None and market_cap is not None and after_rnpv is not None:
        parts.append(
            f"mispricing={(mispricing * 100):+.1f}% from model_rnpv=${after_rnpv:.1f}M "
            f"vs market_cap=${market_cap:.1f}M"
        )
    else:
        parts.append("market cap unavailable for mispricing")
    if event_type:
        parts.append(f"event_type={event_type} priority={event_priority:.2f}")
    parts.append(
        f"confidence={confidence:.2f} recency={recency:.2f} days_since_event={days_since_event}"
    )
    parts.append(f"score={score:.4f}")
    return ". ".join(parts) + "."
