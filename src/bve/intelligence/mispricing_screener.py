"""Unified mispricing screener built on top of ranking, acquisition, and catalyst data."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.intelligence.acquisition_screen import (
    DEFAULT_ACQUISITION_THRESHOLD,
    AcquisitionScreenConfig,
    AcquisitionScreenResult,
    AcquisitionScreener,
)
from bve.intelligence.catalyst_calendar import CatalystEvent
from bve.intelligence.market_expectations import compute_market_mispricing
from bve.intelligence.ranking import AssetRankingEngine, RankedOpportunity, RankingConfig, RankingResult

_NEUTRAL_RANKING_SCORE = 0.25
_NEUTRAL_ACQUISITION_SCORE = 0.35
_NEUTRAL_STAGE_SCORE = 0.40
_NEUTRAL_POS_SCORE = 0.50

SCORE_VERSIONS: dict[str, dict[str, float]] = {
    "v1.0": {
        "ranking": 0.60,
        "acquisition": 0.25,
        "stage": 0.05,
        "pos_adjustment": 0.10,
    }
}

_STAGE_SCORES: dict[str, float] = {
    "preclinical": 0.10,
    "phase_1": 0.25,
    "phase_2": 0.55,
    "phase_3": 0.80,
    "nda_bla": 0.95,
    "approved": 1.00,
}

_CATALYST_IMPORTANCE: dict[str, float] = {
    "pdufa_decision": 1.0,
    "adcom_meeting": 0.9,
    "trial_readout": 1.0,
    "enrollment_complete": 0.4,
    "conference_abstract": 0.3,
    "competitor_readout": 0.0,
    "fda_decision": 1.0,
    "conference_presentation": 0.3,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MispricingScreenConfig(BaseModel):
    """Config for the unified mispricing screener."""

    score_version: str = "v1.0"
    top_n: int = Field(default=25, ge=1)
    catalyst_days_ahead: int = Field(default=180, ge=1)
    acquisition_threshold: float = Field(default=DEFAULT_ACQUISITION_THRESHOLD, gt=0.0)
    require_acquisition_readiness: bool = True
    persist_acquisition_snapshots: bool = False
    max_catalyst_modifier_pct: float = Field(default=0.10, ge=0.0, le=0.50)

    def resolved_weights(self) -> dict[str, float]:
        try:
            return dict(SCORE_VERSIONS[self.score_version])
        except KeyError as exc:
            raise ValueError(
                f"Unknown score version {self.score_version!r}. Valid: {sorted(SCORE_VERSIONS)}"
            ) from exc


class MispricingScreenRow(BaseModel):
    """One asset-level row in the unified screener output."""

    rank: int = 0
    asset_id: str
    company_id: str
    ticker: Optional[str] = None
    drug_name: Optional[str] = None
    indication: Optional[str] = None
    stage: Optional[str] = None

    unified_score: float
    score_version: str

    ranking_rank: Optional[int] = None
    ranking_score: float
    acquisition_score: float
    stage_score: float
    pos_adjustment_score: float

    ranking_component: float
    acquisition_component: float
    stage_component: float
    pos_adjustment_component: float
    catalyst_modifier: float

    rnpv_millions: Optional[float] = None
    market_cap_millions: Optional[float] = None
    enterprise_value_millions: Optional[float] = None
    acquisition_discount: Optional[float] = None
    acquisition_ready: Optional[bool] = None
    acquisition_exclusion_reason: Optional[str] = None
    market_cap_source: Optional[str] = None

    mispricing: Optional[float] = None
    mispricing_pct: Optional[float] = None
    model_pos: Optional[float] = None
    implied_pos: Optional[float] = None
    pos_gap: Optional[float] = None
    pos_adjustment_value: Optional[float] = None
    pos_adjustment_source: Optional[str] = None

    catalyst_type: Optional[str] = None
    catalyst_date: Optional[date] = None
    catalyst_source: Optional[str] = None
    catalyst_signal_strength: Optional[float] = None
    days_to_catalyst: Optional[int] = None

    data_notes: list[str] = Field(default_factory=list)
    explanation: str


class MispricingScreenResult(BaseModel):
    """Full output of a unified screen run."""

    screened_at: datetime
    as_of_date: date
    score_version: str
    score_weights: dict[str, float]
    n_assets: int
    n_with_ranking: int
    n_with_acquisition_discount: int
    n_with_catalyst: int
    rows: list[MispricingScreenRow] = Field(default_factory=list)


class UnifiedMispricingScreener:
    """Compose existing ranking, acquisition, and catalyst layers into one report."""

    def __init__(
        self,
        *,
        knowledge_store,
        config: Optional[MispricingScreenConfig] = None,
        context_provider: Optional[object] = None,
    ) -> None:
        self.knowledge = knowledge_store
        self.config = config or MispricingScreenConfig()
        self.acquisition_screener = AcquisitionScreener(
            AcquisitionScreenConfig(
                threshold=self.config.acquisition_threshold,
                persist_snapshots=self.config.persist_acquisition_snapshots,
                require_acquisition_readiness=self.config.require_acquisition_readiness,
            ),
            knowledge_store=knowledge_store,
            context_provider=context_provider,
        )

    def screen_from_watchlist_config(
        self,
        watchlist_config: Any,
        *,
        screened_at: Optional[datetime] = None,
    ) -> MispricingScreenResult:
        screened_at = screened_at or _utcnow()
        as_of = screened_at.date()
        watchlist = list(getattr(watchlist_config, "watchlist", []))

        ranking_cfg = _resolve_ranking_config(watchlist_config)
        ranking_cfg = ranking_cfg.model_copy(update={"top_n": max(len(watchlist), ranking_cfg.top_n)})
        ranking = AssetRankingEngine(
            config=ranking_cfg,
            knowledge_store=self.knowledge,
        ).rank_from_watchlist_config(
            watchlist_config,
            ranked_at=screened_at,
        )
        acquisition = self.acquisition_screener.screen_watchlist(
            watchlist,
            snapshot_date=as_of,
            persist=self.config.persist_acquisition_snapshots,
        )
        return self._build_result(
            watchlist=watchlist,
            ranking=ranking,
            acquisition=acquisition,
            screened_at=screened_at,
        )

    def _build_result(
        self,
        *,
        watchlist: list[object],
        ranking: RankingResult,
        acquisition: AcquisitionScreenResult,
        screened_at: datetime,
    ) -> MispricingScreenResult:
        ranking_by_asset = {opp.asset_id: opp for opp in ranking.opportunities}
        acquisition_by_asset = {row.asset_id: row for row in acquisition.rows}
        full_rows = [
            self._build_row(
                asset=asset,
                ranking=ranking_by_asset.get(asset.asset_id),
                acquisition_row=acquisition_by_asset.get(asset.asset_id),
                as_of=screened_at.date(),
            )
            for asset in watchlist
        ]

        full_rows.sort(
            key=lambda row: (
                -row.unified_score,
                0 if row.acquisition_discount is not None else 1,
                -(row.acquisition_discount or 0.0),
                -(row.ranking_score or 0.0),
                row.asset_id,
            )
        )
        rows = [
            row.model_copy(update={"rank": idx + 1})
            for idx, row in enumerate(full_rows[: self.config.top_n])
        ]

        return MispricingScreenResult(
            screened_at=screened_at,
            as_of_date=screened_at.date(),
            score_version=self.config.score_version,
            score_weights=self.config.resolved_weights(),
            n_assets=len(watchlist),
            n_with_ranking=sum(1 for row in full_rows if row.ranking_rank is not None),
            n_with_acquisition_discount=sum(
                1 for row in full_rows if row.acquisition_discount is not None
            ),
            n_with_catalyst=sum(1 for row in full_rows if row.catalyst_date is not None),
            rows=rows,
        )

    def _build_row(
        self,
        *,
        asset: object,
        ranking: Optional[RankedOpportunity],
        acquisition_row,
        as_of: date,
    ) -> MispricingScreenRow:
        notes: list[str] = []
        weights = self.config.resolved_weights()
        catalyst = self._lookup_catalyst(asset_id=getattr(asset, "asset_id"))

        stage = _resolve_stage(acquisition_row=acquisition_row, ranking=ranking)
        stage_score = _stage_score(stage)
        if stage is None:
            notes.append("missing_stage")

        ranking_score = float(ranking.composite_score) if ranking is not None else _NEUTRAL_RANKING_SCORE
        if ranking is None:
            notes.append("missing_ranking_signal")

        acquisition_score = _normalize_acquisition_discount(
            acquisition_discount=(
                getattr(acquisition_row, "acquisition_discount", None)
                if acquisition_row is not None
                else None
            )
        )
        if acquisition_row is None:
            notes.append("missing_acquisition_row")
        else:
            if acquisition_row.exclusion_reason is not None:
                notes.append(acquisition_row.exclusion_reason)
            if acquisition_row.acquisition_discount is None:
                notes.append("acquisition_discount_unavailable")

        pos_adjustment_score, pos_adjustment_value, pos_adjustment_source = _resolve_pos_adjustment(
            ranking=ranking,
            acquisition_row=acquisition_row,
        )
        if pos_adjustment_source == "neutral":
            notes.append("missing_pos_adjustment_context")

        ranking_component = ranking_score * weights["ranking"]
        acquisition_component = acquisition_score * weights["acquisition"]
        stage_component = stage_score * weights["stage"]
        pos_adjustment_component = pos_adjustment_score * weights["pos_adjustment"]
        base_score = (
            ranking_component
            + acquisition_component
            + stage_component
            + pos_adjustment_component
        )
        catalyst_modifier = _catalyst_modifier(
            catalyst=catalyst,
            as_of=as_of,
            days_ahead=self.config.catalyst_days_ahead,
            max_modifier_pct=self.config.max_catalyst_modifier_pct,
        )
        unified_score = round(max(0.0, min(1.0, base_score * catalyst_modifier)), 6)

        mispricing = _resolve_mispricing(ranking=ranking, acquisition_row=acquisition_row)
        if catalyst is None:
            notes.append("no_active_catalyst_within_window")

        return MispricingScreenRow(
            asset_id=getattr(asset, "asset_id"),
            company_id=getattr(asset, "company_id"),
            ticker=_first_non_null(
                getattr(asset, "ticker", None),
                getattr(ranking, "ticker", None) if ranking is not None else None,
                getattr(acquisition_row, "ticker", None) if acquisition_row is not None else None,
            ),
            drug_name=getattr(acquisition_row, "drug_name", None) if acquisition_row is not None else None,
            indication=getattr(acquisition_row, "indication", None) if acquisition_row is not None else None,
            stage=stage,
            unified_score=unified_score,
            score_version=self.config.score_version,
            ranking_rank=ranking.rank if ranking is not None else None,
            ranking_score=round(ranking_score, 6),
            acquisition_score=round(acquisition_score, 6),
            stage_score=round(stage_score, 6),
            pos_adjustment_score=round(pos_adjustment_score, 6),
            ranking_component=round(ranking_component, 6),
            acquisition_component=round(acquisition_component, 6),
            stage_component=round(stage_component, 6),
            pos_adjustment_component=round(pos_adjustment_component, 6),
            catalyst_modifier=round(catalyst_modifier, 6),
            rnpv_millions=_first_non_null(
                getattr(acquisition_row, "model_rnpv_millions", None) if acquisition_row is not None else None,
                getattr(ranking, "after_rnpv_millions", None) if ranking is not None else None,
            ),
            market_cap_millions=_first_non_null(
                getattr(acquisition_row, "market_cap_millions", None) if acquisition_row is not None else None,
                getattr(ranking, "market_cap_millions", None) if ranking is not None else None,
            ),
            enterprise_value_millions=(
                getattr(acquisition_row, "enterprise_value_millions", None)
                if acquisition_row is not None
                else None
            ),
            acquisition_discount=(
                getattr(acquisition_row, "acquisition_discount", None)
                if acquisition_row is not None
                else None
            ),
            acquisition_ready=(
                getattr(acquisition_row, "acquisition_ready", None)
                if acquisition_row is not None
                else None
            ),
            acquisition_exclusion_reason=(
                getattr(acquisition_row, "exclusion_reason", None)
                if acquisition_row is not None
                else None
            ),
            market_cap_source=(
                getattr(acquisition_row, "market_cap_source", None)
                if acquisition_row is not None
                else None
            ),
            mispricing=mispricing,
            mispricing_pct=round(mispricing * 100.0, 4) if mispricing is not None else None,
            model_pos=_first_non_null(
                getattr(ranking, "model_pos", None) if ranking is not None else None,
                getattr(acquisition_row, "model_pos", None) if acquisition_row is not None else None,
            ),
            implied_pos=getattr(ranking, "implied_pos", None) if ranking is not None else None,
            pos_gap=getattr(ranking, "pos_gap", None) if ranking is not None else None,
            pos_adjustment_value=pos_adjustment_value,
            pos_adjustment_source=pos_adjustment_source,
            catalyst_type=_catalyst_type_value(catalyst),
            catalyst_date=catalyst.expected_date if catalyst is not None else None,
            catalyst_source=catalyst.source if catalyst is not None else None,
            catalyst_signal_strength=getattr(catalyst, "signal_strength", None) if catalyst is not None else None,
            days_to_catalyst=(
                max(0, (catalyst.expected_date - as_of).days) if catalyst is not None else None
            ),
            data_notes=notes,
            explanation=_build_explanation(
                asset_id=getattr(asset, "asset_id"),
                unified_score=unified_score,
                ranking_score=ranking_score,
                acquisition_discount=(
                    getattr(acquisition_row, "acquisition_discount", None)
                    if acquisition_row is not None
                    else None
                ),
                pos_adjustment_value=pos_adjustment_value,
                catalyst=catalyst,
                as_of=as_of,
            ),
        )

    def _lookup_catalyst(self, *, asset_id: str) -> Optional[CatalystEvent]:
        events = self.knowledge.get_catalyst_events(
            asset_id=asset_id,
            active_only=True,
            days_ahead=self.config.catalyst_days_ahead,
        )
        if not events:
            return None
        return min(events, key=lambda event: event.expected_date)


def _resolve_ranking_config(watchlist_config: Any) -> RankingConfig:
    base = getattr(watchlist_config, "ranking", None)
    if base is None:
        return RankingConfig()
    if isinstance(base, RankingConfig):
        return RankingConfig.model_validate(base.model_dump(mode="json"))
    if hasattr(base, "model_dump"):
        return RankingConfig.model_validate(base.model_dump(mode="json"))
    return RankingConfig.model_validate(base)


def _first_non_null(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _resolve_stage(
    *,
    acquisition_row,
    ranking: Optional[RankedOpportunity],
) -> Optional[str]:
    if acquisition_row is not None and acquisition_row.stage is not None:
        return str(acquisition_row.stage)
    if ranking is not None and ranking.signal_trial_phase is not None:
        return str(ranking.signal_trial_phase)
    return None


def _stage_score(stage: Optional[str]) -> float:
    if stage is None:
        return _NEUTRAL_STAGE_SCORE
    return _STAGE_SCORES.get(stage, _NEUTRAL_STAGE_SCORE)


def _normalize_acquisition_discount(acquisition_discount: Optional[float]) -> float:
    if acquisition_discount is None:
        return _NEUTRAL_ACQUISITION_SCORE
    if acquisition_discount <= 0:
        return 0.0
    return max(0.0, min(1.0, (float(acquisition_discount) - 1.0) / 1.5))


def _resolve_pos_adjustment(
    *,
    ranking: Optional[RankedOpportunity],
    acquisition_row,
) -> tuple[float, Optional[float], str]:
    if ranking is not None and ranking.pos_gap is not None:
        beneficial_delta = -float(ranking.pos_gap)
        score = _bounded_centered_score(beneficial_delta, clip_abs=0.30)
        return score, round(beneficial_delta, 6), "pos_gap"

    prior = (
        getattr(acquisition_row, "acquisition_readiness_prior_pos", None)
        if acquisition_row is not None
        else None
    )
    posterior = (
        getattr(acquisition_row, "acquisition_readiness_posterior_pos", None)
        if acquisition_row is not None
        else None
    )
    if prior is not None and posterior is not None:
        beneficial_delta = float(posterior) - float(prior)
        score = _bounded_centered_score(beneficial_delta, clip_abs=0.25)
        return score, round(beneficial_delta, 6), "phase_update"

    return _NEUTRAL_POS_SCORE, None, "neutral"


def _bounded_centered_score(value: float, *, clip_abs: float) -> float:
    clipped = max(-clip_abs, min(clip_abs, value))
    return max(0.0, min(1.0, 0.5 + (clipped / (2.0 * clip_abs))))


def _resolve_mispricing(
    *,
    ranking: Optional[RankedOpportunity],
    acquisition_row,
) -> Optional[float]:
    if ranking is not None and ranking.mispricing is not None:
        return float(ranking.mispricing)

    if acquisition_row is None:
        return None

    mispricing_record = compute_market_mispricing(
        model_rnpv_millions=getattr(acquisition_row, "model_rnpv_millions", None),
        market_cap_millions=getattr(acquisition_row, "market_cap_millions", None),
    )
    if mispricing_record is None:
        return None
    return float(mispricing_record.mispricing)


def _catalyst_modifier(
    *,
    catalyst: Optional[CatalystEvent],
    as_of: date,
    days_ahead: int,
    max_modifier_pct: float,
) -> float:
    if catalyst is None:
        return 1.0

    days = max(0, (catalyst.expected_date - as_of).days)
    urgency = max(0.0, 1.0 - (min(days, days_ahead) / float(days_ahead)))
    event_type = _catalyst_type_value(catalyst)
    importance = _CATALYST_IMPORTANCE.get(event_type or "", 0.5)

    raw_strength = getattr(catalyst, "signal_strength", None)
    if raw_strength is None:
        directional = 0.5
    else:
        directional = max(-1.0, min(1.0, float(raw_strength) / 2.0))

    delta = urgency * max_modifier_pct * importance * directional
    modifier = 1.0 + delta
    return max(1.0 - max_modifier_pct, min(1.0 + max_modifier_pct, modifier))


def _catalyst_type_value(catalyst: Optional[CatalystEvent]) -> Optional[str]:
    if catalyst is None:
        return None
    value = getattr(catalyst.catalyst_type, "value", None)
    if isinstance(value, str):
        return value
    return str(catalyst.catalyst_type)


def _build_explanation(
    *,
    asset_id: str,
    unified_score: float,
    ranking_score: float,
    acquisition_discount: Optional[float],
    pos_adjustment_value: Optional[float],
    catalyst: Optional[CatalystEvent],
    as_of: date,
) -> str:
    parts = [
        f"score={unified_score:.3f}",
        f"ranking={ranking_score:.3f}",
    ]
    if acquisition_discount is not None:
        parts.append(f"acq_discount={acquisition_discount:.2f}x")
    if pos_adjustment_value is not None:
        parts.append(f"pos_adj={pos_adjustment_value:+.3f}")
    if catalyst is not None:
        parts.append(
            f"catalyst={_catalyst_type_value(catalyst)} in {max(0, (catalyst.expected_date - as_of).days)}d"
        )
    return f"{asset_id}: " + ", ".join(parts)
