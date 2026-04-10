"""Acquisition discount screener built on the existing rNPV engine."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from bve.config.assumptions_loader import AssumptionsLoader
from bve.intelligence.acquisition_readiness import AcquisitionReadinessAssessor
from bve.models.cost_model import CostModel
from bve.models.probability_model import ProbabilityModel
from bve.models.revenue_model import RevenueModel
from bve.models.rnpv_model import RNPVModel

if TYPE_CHECKING:  # pragma: no cover
    from bve.connectors.market_prices import MarketPriceRecord
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.pipeline.watchlist_runner import AssetContextProvider, AssetValuationContext, WatchlistAsset


DEFAULT_ACQUISITION_THRESHOLD = 1.5
DEFAULT_FORMULA_VERSION = "rnpv_over_ev_v1"
DEFAULT_EV_METHODOLOGY = "market_cap_minus_net_cash_v1"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: object) -> Optional[str]:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    if isinstance(value, str):
        return value
    return None


class AcquisitionScreenConfig(BaseModel):
    """Configuration for the acquisition discount screener."""

    threshold: float = Field(default=DEFAULT_ACQUISITION_THRESHOLD, gt=0.0)
    formula_version: str = DEFAULT_FORMULA_VERSION
    ev_methodology: str = DEFAULT_EV_METHODOLOGY
    persist_snapshots: bool = True
    require_acquisition_readiness: bool = False


class AcquisitionDiscountSnapshot(BaseModel):
    """Persisted snapshot of one acquisition discount computation."""

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    ticker: Optional[str] = None
    snapshot_date: date
    formula_version: str = DEFAULT_FORMULA_VERSION
    model_rnpv_millions: Optional[float] = None
    model_pos: Optional[float] = None
    market_cap_millions: Optional[float] = None
    market_cap_as_of: Optional[date] = None
    market_cap_source: Optional[str] = None
    enterprise_value_millions: Optional[float] = None
    net_cash_millions: Optional[float] = None
    ev_methodology: str = DEFAULT_EV_METHODOLOGY
    acquisition_discount: Optional[float] = None
    passes_threshold: bool = False
    exclusion_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)


class AcquisitionScreenRow(AcquisitionDiscountSnapshot):
    """User-facing acquisition screen row with watchlist metadata."""

    company_id: Optional[str] = None
    drug_name: Optional[str] = None
    indication: Optional[str] = None
    valuation_config: Optional[str] = None
    therapeutic_area: Optional[str] = None
    stage: Optional[str] = None
    peak_sales_millions: Optional[float] = None
    ev_to_peak_sales: Optional[float] = None
    acquisition_ready: Optional[bool] = None
    acquisition_readiness_bucket: Optional[str] = None
    acquisition_readiness_source: Optional[str] = None
    acquisition_readiness_reason: Optional[str] = None
    acquisition_readiness_design_tier: Optional[str] = None
    acquisition_readiness_low_power: bool = False
    acquisition_readiness_prior_pos: Optional[float] = None
    acquisition_readiness_posterior_pos: Optional[float] = None
    comps_match_tier: Optional[str] = None
    comps_n: int = 0
    comps_percentile_vs_peers: Optional[float] = None
    comps_peer_min_ev_to_peak_sales: Optional[float] = None
    comps_peer_median_ev_to_peak_sales: Optional[float] = None
    comps_peer_max_ev_to_peak_sales: Optional[float] = None


class AcquisitionScreenResult(BaseModel):
    """Universe-wide acquisition screen output."""

    screened_at: datetime = Field(default_factory=_utcnow)
    snapshot_date: date
    threshold: float
    formula_version: str
    n_assets: int
    n_candidates: int
    n_excluded: int
    rows: list[AcquisitionScreenRow] = Field(default_factory=list)


class AcquisitionValuationContext(BaseModel):
    """Valuation inputs plus optional YAML-driven adjustment layers."""

    asset: object
    company: object
    trials: list[object]
    market_model: object
    pos_adjusters: Optional[dict] = None
    apply_pos_model: bool = False
    design_adjusters: Optional[dict] = None
    apply_design_model: bool = False

    model_config = {"arbitrary_types_allowed": True}


@dataclass(frozen=True)
class _ResolvedMarketCap:
    market_cap_millions: Optional[float]
    market_cap_as_of: Optional[date]
    market_cap_source: Optional[str]


class AcquisitionScreener:
    """
    Screen watchlist assets for acquisition discount using the existing rNPV math.

    Important:
    ``RNPVModel.compute()`` already returns a risk-adjusted value, so the default
    formula here is:

        acquisition_discount = rnpv_millions / enterprise_value

    The screener intentionally does not multiply by approval probability again.
    """

    def __init__(
        self,
        config: Optional[AcquisitionScreenConfig] = None,
        *,
        knowledge_store: Optional["KnowledgeStore"] = None,
        context_provider: Optional["AssetContextProvider"] = None,
    ) -> None:
        self.config = config or AcquisitionScreenConfig()
        self.knowledge = knowledge_store
        self.context_provider = context_provider
        self.readiness = AcquisitionReadinessAssessor(knowledge_store=knowledge_store)

    def screen_watchlist(
        self,
        watchlist: list["WatchlistAsset"],
        *,
        snapshot_date: Optional[date] = None,
        persist: Optional[bool] = None,
        comparable_deals: Optional[list[object]] = None,
    ) -> AcquisitionScreenResult:
        """Compute acquisition discount rows for every watchlist asset."""
        as_of = snapshot_date or _utcnow().date()
        should_persist = self.config.persist_snapshots if persist is None else persist

        rows = [
            self._screen_asset(
                asset,
                snapshot_date=as_of,
                comparable_deals=comparable_deals,
            )
            for asset in watchlist
        ]
        rows = sorted(rows, key=self._sort_key)

        if should_persist and self.knowledge is not None:
            for row in rows:
                self.knowledge.upsert_acquisition_discount_snapshot(self._to_snapshot(row))

        return AcquisitionScreenResult(
            snapshot_date=as_of,
            threshold=self.config.threshold,
            formula_version=self.config.formula_version,
            n_assets=len(rows),
            n_candidates=sum(1 for row in rows if row.passes_threshold),
            n_excluded=sum(1 for row in rows if row.exclusion_reason is not None),
            rows=rows,
        )

    def _screen_asset(
        self,
        asset: "WatchlistAsset",
        *,
        snapshot_date: date,
        comparable_deals: Optional[list[object]] = None,
    ) -> AcquisitionScreenRow:
        ticker = getattr(asset, "ticker", None)
        base = {
            "asset_id": asset.asset_id,
            "company_id": asset.company_id,
            "drug_name": getattr(asset, "drug_name", None),
            "indication": getattr(asset, "indication", None),
            "valuation_config": getattr(asset, "valuation_config", None),
            "snapshot_date": snapshot_date,
            "formula_version": self.config.formula_version,
            "ev_methodology": self.config.ev_methodology,
        }

        if not getattr(asset, "valuation_config", None):
            return AcquisitionScreenRow(
                **base,
                ticker=ticker,
                exclusion_reason="missing_valuation_config",
            )

        try:
            context = self._get_context(asset)
        except Exception:
            return AcquisitionScreenRow(
                **base,
                ticker=ticker,
                exclusion_reason="valuation_context_error",
            )

        resolved_ticker = ticker or context.company.ticker
        base.update(
            {
                "therapeutic_area": _enum_value(getattr(context.asset, "therapeutic_area", None)),
                "stage": _enum_value(getattr(context.asset, "stage", None)),
            }
        )

        try:
            rnpv = self._run_rnpv(context)
        except Exception:
            return AcquisitionScreenRow(
                **base,
                ticker=resolved_ticker,
                exclusion_reason="valuation_error",
                net_cash_millions=context.company.net_cash_millions,
            )

        market_cap = self._resolve_market_cap(asset, context, snapshot_date=snapshot_date)
        if market_cap.market_cap_millions is None:
            return AcquisitionScreenRow(
                **base,
                ticker=resolved_ticker,
                model_rnpv_millions=round(float(rnpv.rnpv_millions), 6),
                model_pos=round(float(rnpv.cumulative_success_probability), 6),
                net_cash_millions=round(float(context.company.net_cash_millions), 6),
                market_cap_source=market_cap.market_cap_source,
                exclusion_reason="missing_market_cap",
            )

        enterprise_value = float(market_cap.market_cap_millions) - float(context.company.net_cash_millions)
        peak_sales_raw = getattr(rnpv, "peak_sales_millions", None)
        peak_sales = float(peak_sales_raw) if peak_sales_raw is not None else None
        ev_to_peak_sales = None
        if peak_sales is not None and peak_sales > 0 and enterprise_value > 0:
            ev_to_peak_sales = enterprise_value / peak_sales
        if enterprise_value <= 0:
            return AcquisitionScreenRow(
                **base,
                ticker=resolved_ticker,
                model_rnpv_millions=round(float(rnpv.rnpv_millions), 6),
                model_pos=round(float(rnpv.cumulative_success_probability), 6),
                market_cap_millions=round(float(market_cap.market_cap_millions), 6),
                market_cap_as_of=market_cap.market_cap_as_of,
                market_cap_source=market_cap.market_cap_source,
                enterprise_value_millions=round(enterprise_value, 6),
                net_cash_millions=round(float(context.company.net_cash_millions), 6),
                peak_sales_millions=round(peak_sales, 6) if peak_sales is not None else None,
                exclusion_reason="non_positive_enterprise_value",
            )

        acquisition_discount = float(rnpv.rnpv_millions) / enterprise_value
        row = AcquisitionScreenRow(
            **base,
            ticker=resolved_ticker,
            model_rnpv_millions=round(float(rnpv.rnpv_millions), 6),
            model_pos=round(float(rnpv.cumulative_success_probability), 6),
            market_cap_millions=round(float(market_cap.market_cap_millions), 6),
            market_cap_as_of=market_cap.market_cap_as_of,
            market_cap_source=market_cap.market_cap_source,
            enterprise_value_millions=round(enterprise_value, 6),
            net_cash_millions=round(float(context.company.net_cash_millions), 6),
            peak_sales_millions=round(peak_sales, 6) if peak_sales is not None else None,
            ev_to_peak_sales=round(ev_to_peak_sales, 6) if ev_to_peak_sales is not None else None,
            acquisition_discount=round(acquisition_discount, 6),
            passes_threshold=acquisition_discount > self.config.threshold,
        )
        row = self._enrich_with_readiness(
            row,
            asset=asset,
            context=context,
            snapshot_date=snapshot_date,
        )
        if comparable_deals:
            row = self._enrich_with_comps(row, comparable_deals=comparable_deals)
        return row

    def _run_rnpv(self, context: AcquisitionValuationContext):
        """Run only the core rNPV layers needed for the acquisition screen."""
        from bve.valuation.valuation_engine import ValuationEngine

        engine = ValuationEngine(
            asset=context.asset,
            company=context.company,
            trials=context.trials,
            market_model=context.market_model,
            pos_adjusters=context.pos_adjusters,
            design_adjusters=context.design_adjusters,
            apply_pos_model=context.apply_pos_model,
            apply_design_model=context.apply_design_model,
        )
        trials = engine._prepare_trials()
        loe_profile = AssumptionsLoader.get().loe_erosion_profile(context.asset.modality.value)
        prob = ProbabilityModel.compute(context.asset, trials)
        rev = RevenueModel.compute(context.market_model, loe_profile=loe_profile)
        cost = CostModel.compute(prob, context.asset.discount_rate)
        return RNPVModel.compute(context.asset, prob, rev, cost)

    def _get_context(self, asset: "WatchlistAsset") -> AcquisitionValuationContext:
        if self.context_provider is not None:
            raw = self.context_provider.get_context(asset)
            return self._normalize_context(raw)
        return self._load_context_from_config(asset)

    @staticmethod
    def _normalize_context(raw: object) -> AcquisitionValuationContext:
        if isinstance(raw, AcquisitionValuationContext):
            return raw
        return AcquisitionValuationContext(
            asset=getattr(raw, "asset"),
            company=getattr(raw, "company"),
            trials=list(getattr(raw, "trials")),
            market_model=getattr(raw, "market_model"),
        )

    @staticmethod
    def _load_context_from_config(asset: "WatchlistAsset") -> AcquisitionValuationContext:
        from pathlib import Path

        from bve.cli.run_asset import (
            _build_design_adjusters,
            _build_objects,
            _build_pos_adjusters,
            _load_config,
        )

        if not asset.valuation_config:
            raise ValueError(f"Asset {asset.asset_id} is missing valuation_config")

        cfg = _load_config(Path(asset.valuation_config).expanduser().resolve())
        built_asset, company, trials, market_model = _build_objects(cfg)
        pos_adjusters, apply_pos_model = _build_pos_adjusters(cfg)
        design_adjusters, apply_design_model = _build_design_adjusters(cfg)
        return AcquisitionValuationContext(
            asset=built_asset,
            company=company,
            trials=trials,
            market_model=market_model,
            pos_adjusters=pos_adjusters,
            apply_pos_model=apply_pos_model,
            design_adjusters=design_adjusters,
            apply_design_model=apply_design_model,
        )

    def _resolve_market_cap(
        self,
        asset: "WatchlistAsset",
        context: "AssetValuationContext",
        *,
        snapshot_date: date,
    ) -> _ResolvedMarketCap:
        ticker = getattr(asset, "ticker", None) or context.company.ticker
        price: Optional["MarketPriceRecord"] = None
        if self.knowledge is not None and ticker:
            price = self.knowledge.get_price_on_or_before(ticker, snapshot_date)
            if (
                price is not None
                and price.market_cap_millions is not None
                and price.market_cap_millions > 0
            ):
                return _ResolvedMarketCap(
                    market_cap_millions=float(price.market_cap_millions),
                    market_cap_as_of=price.price_date,
                    market_cap_source="knowledge_store_price",
                )

        watchlist_market_cap = getattr(asset, "market_cap_millions", None)
        if watchlist_market_cap is not None and watchlist_market_cap > 0:
            return _ResolvedMarketCap(
                market_cap_millions=float(watchlist_market_cap),
                market_cap_as_of=snapshot_date,
                market_cap_source="watchlist_override",
            )

        company_market_cap = getattr(context.company, "market_cap_millions", None)
        if company_market_cap is not None and company_market_cap > 0:
            return _ResolvedMarketCap(
                market_cap_millions=float(company_market_cap),
                market_cap_as_of=snapshot_date,
                market_cap_source="company_snapshot",
            )

        if (
            context.company.current_price is not None
            and context.company.current_price > 0
            and context.company.shares_outstanding_millions > 0
        ):
            derived_market_cap = (
                float(context.company.current_price)
                * float(context.company.shares_outstanding_millions)
            )
            return _ResolvedMarketCap(
                market_cap_millions=round(derived_market_cap, 6),
                market_cap_as_of=snapshot_date,
                market_cap_source="company_price_x_shares",
            )

        return _ResolvedMarketCap(
            market_cap_millions=None,
            market_cap_as_of=price.price_date if price is not None else None,
            market_cap_source="missing",
        )

    @staticmethod
    def _sort_key(row: AcquisitionScreenRow) -> tuple[int, float, str]:
        if row.acquisition_discount is None:
            return (2, 0.0, row.asset_id)
        if row.exclusion_reason is not None:
            return (1, -row.acquisition_discount, row.asset_id)
        return (0, -row.acquisition_discount, row.asset_id)

    def _enrich_with_readiness(
        self,
        row: AcquisitionScreenRow,
        *,
        asset: "WatchlistAsset",
        context: AcquisitionValuationContext,
        snapshot_date: date,
    ) -> AcquisitionScreenRow:
        assessment = self.readiness.assess(
            asset_id=asset.asset_id,
            asset_stage=context.asset.stage,
            engine_asset_id=getattr(context.asset, "id", asset.asset_id),
            trials=context.trials,
            as_of_date=snapshot_date,
        )
        updated = row.model_copy(
            update={
                "acquisition_ready": assessment.is_acquisition_ready,
                "acquisition_readiness_bucket": assessment.readiness_bucket,
                "acquisition_readiness_source": assessment.evidence_source,
                "acquisition_readiness_reason": assessment.exclusion_reason,
                "acquisition_readiness_design_tier": assessment.trial_design_tier,
                "acquisition_readiness_low_power": assessment.low_power_flag,
                "acquisition_readiness_prior_pos": assessment.phase_prior_pos,
                "acquisition_readiness_posterior_pos": assessment.phase_posterior_pos,
            }
        )
        if (
            self.config.require_acquisition_readiness
            and updated.exclusion_reason is None
            and not assessment.is_acquisition_ready
        ):
            updated = updated.model_copy(
                update={
                    "passes_threshold": False,
                    "exclusion_reason": assessment.exclusion_reason or "not_acquisition_ready",
                }
            )
        return updated

    @staticmethod
    def _enrich_with_comps(
        row: AcquisitionScreenRow,
        *,
        comparable_deals: list[object],
    ) -> AcquisitionScreenRow:
        from bve.intelligence.comparable_deals import ComparableDealMatcher

        analysis = ComparableDealMatcher.analyze(
            asset_indication=row.indication,
            asset_therapeutic_area=row.therapeutic_area,
            asset_stage=row.stage,
            asset_ev_to_peak_sales=row.ev_to_peak_sales,
            deals=comparable_deals,
        )
        return row.model_copy(
            update={
                "comps_match_tier": analysis.match_tier,
                "comps_n": analysis.n_comps,
                "comps_percentile_vs_peers": analysis.percentile_vs_comps,
                "comps_peer_min_ev_to_peak_sales": analysis.peer_min_ev_to_peak_sales,
                "comps_peer_median_ev_to_peak_sales": analysis.peer_median_ev_to_peak_sales,
                "comps_peer_max_ev_to_peak_sales": analysis.peer_max_ev_to_peak_sales,
            }
        )

    @staticmethod
    def _to_snapshot(row: AcquisitionScreenRow) -> AcquisitionDiscountSnapshot:
        payload = row.model_dump()
        payload.pop("company_id", None)
        payload.pop("drug_name", None)
        payload.pop("indication", None)
        payload.pop("valuation_config", None)
        return AcquisitionDiscountSnapshot(**payload)
