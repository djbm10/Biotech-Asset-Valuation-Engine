"""
Point-in-time company-level SOTP builder for the top biotech universe.

This is the first institutional-grade bridge between:
  - asset-level valuation outputs
  - point-in-time market cap snapshots
  - explicit company-level adjustment buckets

It intentionally exposes coverage / provenance limitations instead of hiding
them. Market cap can be dated via replay or knowledge-store prices, while the
balance sheet now prefers dated replay balance-sheet snapshots with explicit
source refs and falls back to the latest config snapshot when unavailable.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

from bve.cli.run_asset import (
    _build_design_adjusters,
    _build_objects,
    _build_pos_adjusters,
    _load_config,
)
from bve.entities.company import Company
from bve.ingestion.market_data import get_fundamentals
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore
from bve.pipeline.watchlist_runner import WatchlistAsset, load_watchlist_config
from bve.valuation.valuation_engine import ValuationEngine

PriceFundamentalsFetcher = Callable[[str], dict]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPORT_SEPARATOR = "=" * 72
_CONFIG_QUALITY_CONFIDENCE: dict[str, float] = {
    "gold": 0.95,
    "curated": 0.85,
    "screening_grade": 0.60,
    "auto_generated": 0.50,
}
_STRUCTURED_SOURCE_CONFIDENCE_FLOORS: dict[str, float] = {
    "sec_filing": 0.90,
    "contractual": 0.90,
    "company_disclosure": 0.80,
    "investor_day": 0.80,
    "analyst_bridge": 0.65,
    "inferred": 0.65,
}
_LOW_EVIDENCE_SOURCE_KINDS = {"analyst_bridge", "inferred"}


class CompanySOTPBucket(BaseModel, frozen=True):
    bucket_id: str
    bucket_type: Literal[
        "modeled_asset",
        "net_cash",
        "platform",
        "unmodeled_pipeline",
        "royalty",
        "dilution_reserve",
    ]
    label: str
    value_millions: float
    source: str
    source_kind: Literal[
        "modeled",
        "sec_filing",
        "contractual",
        "company_disclosure",
        "investor_day",
        "analyst_bridge",
        "inferred",
    ]
    source_as_of: Optional[date] = None
    source_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_ref: Optional[str] = None
    notes: Optional[str] = None
    modeled: bool = True


class CompanySOTPResult(BaseModel, frozen=True):
    rank: int
    company_id: str
    company_name: str
    ticker: str
    snapshot_date: date
    asset_count_modeled: int
    modeled_asset_ids: list[str]
    market_cap_millions: float
    enterprise_value_millions: float
    net_cash_millions: float
    shares_outstanding_millions: float
    modeled_asset_value_millions: float
    platform_value_millions: float
    unmodeled_pipeline_value_millions: float
    royalty_value_millions: float
    dilution_reserve_millions: float
    sotp_equity_value_millions: float
    sotp_per_share: float
    sotp_discount: float
    ranked_sotp_discount: float
    reconciliation_gap_millions: float
    reconciliation_gap_pct: float
    reconciliation_status: Literal[
        "extreme_premium",
        "premium",
        "discounted",
        "extreme_discount",
    ]
    reconciliation_passes_gate: bool
    mcap_trend_3m_pct: Optional[float] = None
    sotp_tier: Literal["normal", "watch", "needs_manual_review", "avoid"]
    sotp_action: Literal["surface", "flag", "exclude"]
    sotp_confidence_tier: Literal["high", "medium_flagged", "low", "very_low"]
    sotp_tier_reason: str
    modeled_asset_coverage_pct: float
    actionable_coverage_pct: float = 0.0
    actionable_confidence_pct: float = 0.0
    structured_input_count: int = 0
    structured_input_confidence_min: Optional[float] = None
    structured_input_confidence_avg: Optional[float] = None
    manual_bucket_share_pct: float = 0.0
    manual_bucket_confidence_avg: Optional[float] = None
    n_bucket_sources: int = 0
    market_cap_source: str
    balance_sheet_source: str
    balance_sheet_source_ref: Optional[str]
    balance_sheet_snapshot_date: Optional[date]
    balance_sheet_period_end_date: Optional[date]
    balance_sheet_form_type: Optional[str]
    balance_sheet_is_point_in_time: bool
    balance_sheet_age_days: Optional[int]
    balance_sheet_passes_recency_gate: bool
    balance_sheet_recency_penalty: float
    config_quality_summary: Optional[str] = None
    modeled_asset_confidence_min: float
    modeled_asset_confidence_avg: float
    action_policy: Literal["buy", "watch", "avoid", "needs_manual_review"]
    action_reason: str
    buckets: list[CompanySOTPBucket]
    limitations: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @property
    def extreme_discount(self) -> bool:
        return self.sotp_tier in {"needs_manual_review", "avoid"}


class _ResolvedMarketCap(BaseModel, frozen=True):
    market_cap_millions: float
    source: str


class _ResolvedBalanceSheet(BaseModel, frozen=True):
    company: Company
    source: str
    source_ref: Optional[str] = None
    snapshot_date: Optional[date] = None
    period_end_date: Optional[date] = None
    form_type: Optional[str] = None
    is_point_in_time: bool = False
    limitations: list[str] = Field(default_factory=list)


class _BalanceSheetRecency(BaseModel, frozen=True):
    age_days: Optional[int]
    passes_gate: bool
    penalty: float
    limitations: list[str] = Field(default_factory=list)


class _ActionPolicyDecision(BaseModel, frozen=True):
    policy: Literal["buy", "watch", "avoid", "needs_manual_review"]
    reason: str


class SotpTierResult(BaseModel, frozen=True):
    tier: Literal["normal", "watch", "needs_manual_review", "avoid"]
    action: Literal["surface", "flag", "exclude"]
    reason: str
    confidence_tier: Literal["high", "medium_flagged", "low", "very_low"]


class _ReconciliationAssessment(BaseModel, frozen=True):
    gap_millions: float
    gap_pct: float
    ratio: float
    status: Literal[
        "extreme_premium",
        "premium",
        "discounted",
        "extreme_discount",
    ]
    passes_gate: bool
    mcap_trend_3m_pct: Optional[float] = None
    tier_result: SotpTierResult
    limitations: list[str] = Field(default_factory=list)

    @property
    def extreme_discount(self) -> bool:
        return self.tier_result.tier in {"needs_manual_review", "avoid"}


class _PackQualityMetrics(BaseModel, frozen=True):
    manual_bucket_share_pct: float = 0.0
    manual_bucket_confidence_avg: Optional[float] = None
    n_bucket_sources: int = 0
    largest_manual_bucket_share_pct: float = 0.0
    largest_manual_bucket_source_ref_count: int = 0


class _OverrideDefaults(BaseModel):
    dilution_reserve_quarters: float = 0.0


class CompanySOTPStructuredInput(BaseModel):
    bucket_id: str
    bucket_type: Literal[
        "platform",
        "unmodeled_pipeline",
        "royalty",
        "dilution_reserve",
    ]
    label: Optional[str] = None
    value_millions: float
    as_of_date: date
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_kind: Literal[
        "manual",
        "sec_filing",
        "contractual",
        "company_disclosure",
        "investor_day",
        "analyst_bridge",
        "inferred",
    ]
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _normalize_source_hierarchy(self) -> "CompanySOTPStructuredInput":
        canonical_kind = _normalize_structured_source_kind(self.source_kind, self.source)
        minimum_confidence = _STRUCTURED_SOURCE_CONFIDENCE_FLOORS[canonical_kind]
        if float(self.confidence) < minimum_confidence:
            raise ValueError(
                "structured input confidence "
                f"{float(self.confidence):.2f} below minimum "
                f"{minimum_confidence:.2f} for source_kind={canonical_kind}"
            )
        self.source_kind = canonical_kind
        return self


class CompanySOTPInputSnapshot(BaseModel):
    as_of_date: date
    inputs: list[CompanySOTPStructuredInput] = Field(default_factory=list)
    notes: Optional[str] = None


class CompanySOTPOverride(BaseModel):
    platform_value_millions: float = 0.0
    unmodeled_pipeline_value_millions: float = 0.0
    royalty_value_millions: float = 0.0
    dilution_reserve_millions: Optional[float] = None
    dilution_reserve_quarters: Optional[float] = None
    inputs: list[CompanySOTPStructuredInput] = Field(default_factory=list)
    snapshots: list[CompanySOTPInputSnapshot] = Field(default_factory=list)
    notes: Optional[str] = None


class CompanySOTPOverrideSet(BaseModel):
    defaults: _OverrideDefaults = Field(default_factory=_OverrideDefaults)
    companies: dict[str, CompanySOTPOverride] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None) -> "CompanySOTPOverrideSet":
        if path is None:
            return cls()
        override_path = Path(path)
        if not override_path.is_absolute():
            override_path = (_REPO_ROOT / override_path).resolve()
        if not override_path.exists():
            return cls()
        raw = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
        defaults = _OverrideDefaults.model_validate(raw.get("defaults") or {})
        companies = {
            str(key).upper(): CompanySOTPOverride.model_validate(value or {})
            for key, value in (raw.get("companies") or {}).items()
        }
        return cls(defaults=defaults, companies=companies)

    def for_ticker(self, ticker: str) -> CompanySOTPOverride:
        return self.companies.get(ticker.upper(), CompanySOTPOverride())


class CompanySOTPBuilder:
    def __init__(
        self,
        *,
        as_of_date: Optional[date] = None,
        output_dir: str | Path = "outputs/analysis",
        knowledge_db_path: str | Path | None = None,
        replay_store_path: str | Path | None = None,
        overrides_path: str | Path | None = "research/company_sotp_overrides.yaml",
        prefer_stored_screen_context: bool = True,
        persist_company_snapshots: bool = False,
        fundamentals_fetcher: Optional[PriceFundamentalsFetcher] = None,
        asset_rnpv_cache: Optional[dict[str, float]] = None,
        balance_sheet_soft_stale_days: int = 180,
        balance_sheet_hard_stale_days: int = 540,
        config_balance_sheet_penalty: float = 0.5,
        min_stale_balance_sheet_penalty: float = 0.25,
        min_modeled_asset_coverage_pct: float = 0.70,
        min_modeled_asset_confidence_for_auto_action: float = 0.55,
        min_actionable_coverage_pct: float = 0.70,
        min_actionable_confidence_pct: float = 0.60,
        min_structured_input_confidence_for_auto_action: float = 0.60,
        min_platform_bucket_confidence_for_auto_action: float = 0.60,
        min_unmodeled_pipeline_bucket_confidence_for_auto_action: float = 0.60,
        min_royalty_bucket_confidence_for_auto_action: float = 0.55,
        min_dilution_bucket_confidence_for_auto_action: float = 0.75,
        max_manual_bucket_share_for_auto_action: float = 0.35,
        min_manual_bucket_confidence_avg: float = 0.80,
        max_single_manual_bucket_share_without_multi_source: float = 0.25,
        min_bucket_sources_for_high_manual_share: int = 2,
        min_reconciliation_discount_for_auto_action: float = 0.25,
        max_reconciliation_discount_for_auto_action: float = 5.0,
        require_structured_inputs_above_market_cap_millions: float = 1000.0,
        min_market_cap_millions: float = 200.0,
        max_market_cap_millions: float = 10000.0,
        buy_discount_threshold: float = 1.50,
        watch_discount_threshold: float = 1.10,
    ) -> None:
        self.as_of_date = as_of_date or date.today()
        self.output_dir = Path(output_dir)
        self.knowledge_db_path = Path(knowledge_db_path) if knowledge_db_path else None
        self._replay_store_explicit = replay_store_path is not None
        self.replay_store_path = (
            Path(replay_store_path) if replay_store_path else REPLAY_STORE_PATH
        )
        self.overrides = CompanySOTPOverrideSet.load(overrides_path)
        self.prefer_stored_screen_context = bool(prefer_stored_screen_context)
        self.persist_company_snapshots = bool(persist_company_snapshots)
        self.fundamentals_fetcher = fundamentals_fetcher or get_fundamentals
        self.asset_rnpv_cache = asset_rnpv_cache if asset_rnpv_cache is not None else {}
        self.balance_sheet_soft_stale_days = max(int(balance_sheet_soft_stale_days), 0)
        self.balance_sheet_hard_stale_days = max(
            int(balance_sheet_hard_stale_days),
            self.balance_sheet_soft_stale_days + 1,
        )
        self.config_balance_sheet_penalty = float(config_balance_sheet_penalty)
        self.min_stale_balance_sheet_penalty = float(min_stale_balance_sheet_penalty)
        self.min_modeled_asset_coverage_pct = float(min_modeled_asset_coverage_pct)
        self.min_modeled_asset_confidence_for_auto_action = float(
            min_modeled_asset_confidence_for_auto_action
        )
        self.min_actionable_coverage_pct = float(min_actionable_coverage_pct)
        self.min_actionable_confidence_pct = float(min_actionable_confidence_pct)
        self.min_structured_input_confidence_for_auto_action = float(
            max(min_structured_input_confidence_for_auto_action, 0.65)
        )
        self.min_platform_bucket_confidence_for_auto_action = float(
            min_platform_bucket_confidence_for_auto_action
        )
        self.min_unmodeled_pipeline_bucket_confidence_for_auto_action = float(
            min_unmodeled_pipeline_bucket_confidence_for_auto_action
        )
        self.min_royalty_bucket_confidence_for_auto_action = float(
            min_royalty_bucket_confidence_for_auto_action
        )
        self.min_dilution_bucket_confidence_for_auto_action = float(
            min_dilution_bucket_confidence_for_auto_action
        )
        self.max_manual_bucket_share_for_auto_action = float(
            max_manual_bucket_share_for_auto_action
        )
        self.min_manual_bucket_confidence_avg = float(min_manual_bucket_confidence_avg)
        self.max_single_manual_bucket_share_without_multi_source = float(
            max_single_manual_bucket_share_without_multi_source
        )
        self.min_bucket_sources_for_high_manual_share = int(
            min_bucket_sources_for_high_manual_share
        )
        self.min_reconciliation_discount_for_auto_action = float(
            min_reconciliation_discount_for_auto_action
        )
        self.max_reconciliation_discount_for_auto_action = float(
            max_reconciliation_discount_for_auto_action
        )
        self.require_structured_inputs_above_market_cap_millions = float(
            require_structured_inputs_above_market_cap_millions
        )
        self.min_market_cap_millions = float(min_market_cap_millions)
        self.max_market_cap_millions = float(max_market_cap_millions)
        self.buy_discount_threshold = float(buy_discount_threshold)
        self.watch_discount_threshold = float(watch_discount_threshold)
        self.last_csv_path: Optional[Path] = None

    def build(
        self,
        watchlist_path: str,
        *,
        price_source: str = "replay_store",
        include_tickers: Optional[set[str]] = None,
    ) -> list[CompanySOTPResult]:
        if price_source not in {"replay_store", "yfinance"}:
            raise ValueError("price_source must be 'replay_store' or 'yfinance'")

        resolved_watchlist = _resolve_watchlist_path(watchlist_path)
        watchlist_cfg = load_watchlist_config(resolved_watchlist)
        knowledge_db_path = self._resolve_knowledge_db_path(watchlist_cfg.knowledge_db_path)
        knowledge = self._open_knowledge_store(
            knowledge_db_path,
            create=self.persist_company_snapshots,
        )
        replay = self._open_replay_store(
            required=(price_source == "replay_store"),
            enabled=(price_source == "replay_store" or self._replay_store_explicit),
        )

        try:
            groups = _group_watchlist_by_ticker(watchlist_cfg.watchlist)
            if include_tickers is not None:
                allowed = {str(ticker).upper() for ticker in include_tickers}
                groups = {
                    ticker: assets
                    for ticker, assets in groups.items()
                    if ticker.upper() in allowed
                }
            rows: list[CompanySOTPResult] = []
            for ticker, assets in sorted(groups.items()):
                built = self._build_company(
                    ticker=ticker,
                    assets=assets,
                    watchlist_path=resolved_watchlist,
                    price_source=price_source,
                    knowledge=knowledge,
                    replay=replay,
                )
                if built is not None:
                    rows.append(built)

            rows.sort(key=lambda row: (-row.ranked_sotp_discount, row.ticker))
            ranked = [
                row.model_copy(update={"rank": idx + 1})
                for idx, row in enumerate(rows)
            ]
            if self.persist_company_snapshots and knowledge is not None:
                knowledge.write_company_sotp_snapshots(ranked, snapshot_date=self.as_of_date)
            self.last_csv_path = self._write_csv(ranked)
            return ranked
        finally:
            if knowledge is not None:
                knowledge.close()
            if replay is not None:
                replay.close()

    def load_from_store(
        self,
        watchlist_path: str,
    ) -> tuple[Optional[date], list[CompanySOTPResult]]:
        resolved_watchlist = _resolve_watchlist_path(watchlist_path)
        watchlist_cfg = load_watchlist_config(resolved_watchlist)
        knowledge_db_path = self._resolve_knowledge_db_path(watchlist_cfg.knowledge_db_path)
        knowledge = self._open_knowledge_store(knowledge_db_path, create=False)
        if knowledge is None:
            return None, []
        try:
            reference_date, raw_rows = knowledge.get_company_sotp_snapshots_on_or_before(
                self.as_of_date,
                limit=10000,
            )
        finally:
            knowledge.close()
        if reference_date is None or not raw_rows:
            return None, []

        allowed_tickers = {
            str(asset.ticker or asset.company_id or asset.asset_id).upper()
            for asset in watchlist_cfg.watchlist
        }
        filtered = [
            self._result_from_stored_snapshot(raw)
            for raw in raw_rows
            if str(raw.get("ticker") or "").upper() in allowed_tickers
        ]
        filtered.sort(key=lambda row: (-row.ranked_sotp_discount, row.ticker))
        ranked = [
            row.model_copy(update={"rank": idx + 1})
            for idx, row in enumerate(filtered)
        ]
        return reference_date, ranked

    @staticmethod
    def _result_from_stored_snapshot(raw: dict) -> CompanySOTPResult:
        data = dict(raw)
        buckets = [
            CompanySOTPBucket.model_validate(item)
            for item in data.get("buckets", [])
        ]
        if data.get("net_cash_millions") is None:
            data["net_cash_millions"] = round(
                sum(
                    bucket.value_millions
                    for bucket in buckets
                    if bucket.bucket_type == "net_cash"
                ),
                6,
            )
        if data.get("modeled_asset_value_millions") is None:
            data["modeled_asset_value_millions"] = round(
                sum(
                    bucket.value_millions
                    for bucket in buckets
                    if bucket.bucket_type == "modeled_asset"
                ),
                6,
            )
        if data.get("platform_value_millions") is None:
            data["platform_value_millions"] = round(
                sum(
                    bucket.value_millions
                    for bucket in buckets
                    if bucket.bucket_type == "platform"
                ),
                6,
            )
        if data.get("unmodeled_pipeline_value_millions") is None:
            data["unmodeled_pipeline_value_millions"] = round(
                sum(
                    bucket.value_millions
                    for bucket in buckets
                    if bucket.bucket_type == "unmodeled_pipeline"
                ),
                6,
            )
        if data.get("royalty_value_millions") is None:
            data["royalty_value_millions"] = round(
                sum(
                    bucket.value_millions
                    for bucket in buckets
                    if bucket.bucket_type == "royalty"
                ),
                6,
            )
        if data.get("dilution_reserve_millions") is None:
            data["dilution_reserve_millions"] = round(
                sum(
                    -bucket.value_millions
                    for bucket in buckets
                    if bucket.bucket_type == "dilution_reserve"
                ),
                6,
            )
        if data.get("shares_outstanding_millions") is None:
            sotp_equity = float(data.get("sotp_equity_value_millions") or 0.0)
            sotp_per_share = float(data.get("sotp_per_share") or 0.0)
            data["shares_outstanding_millions"] = round(
                (sotp_equity / sotp_per_share) if sotp_per_share else 0.0,
                6,
            )
        market_cap_value = float(data.get("market_cap_millions") or 0.0)
        sotp_equity_value = float(data.get("sotp_equity_value_millions") or 0.0)
        ratio = round((sotp_equity_value / market_cap_value), 6) if market_cap_value else 0.0
        if data.get("reconciliation_status") in {None, ""}:
            data["reconciliation_gap_millions"] = round(
                sotp_equity_value - market_cap_value,
                6,
            )
            data["reconciliation_gap_pct"] = round((ratio - 1.0), 6) if market_cap_value else 0.0
            if ratio < 0.25:
                data["reconciliation_status"] = "extreme_premium"
            elif ratio > 5.0:
                data["reconciliation_status"] = "extreme_discount"
            elif ratio < 1.0:
                data["reconciliation_status"] = "premium"
            else:
                data["reconciliation_status"] = "discounted"
        if data.get("mcap_trend_3m_pct") in {"", None}:
            data["mcap_trend_3m_pct"] = None
        if data.get("sotp_tier") in {None, ""}:
            tier_result = classify_sotp_tier(
                ratio=ratio,
                mcap_trend_3m=(
                    float(data["mcap_trend_3m_pct"])
                    if data.get("mcap_trend_3m_pct") is not None
                    else None
                ),
                weighted_confidence=float(
                    data.get("actionable_confidence_pct")
                    or data.get("modeled_asset_confidence_avg")
                    or 0.0
                ),
            )
            data["sotp_tier"] = tier_result.tier
            data["sotp_action"] = tier_result.action
            data["sotp_confidence_tier"] = tier_result.confidence_tier
            data["sotp_tier_reason"] = tier_result.reason
            data["reconciliation_passes_gate"] = tier_result.tier not in {"needs_manual_review", "avoid"}
        data["buckets"] = buckets
        return CompanySOTPResult.model_validate(data)

    def _build_company(
        self,
        *,
        ticker: str,
        assets: list[WatchlistAsset],
        watchlist_path: Path,
        price_source: str,
        knowledge: Optional[KnowledgeStore],
        replay: Optional[ReplayStore],
    ) -> Optional[CompanySOTPResult]:
        loaded_configs: list[tuple[WatchlistAsset, Path, dict]] = []
        for watchlist_asset in assets:
            if not watchlist_asset.valuation_config:
                continue
            config_path = _resolve_config_path(watchlist_asset.valuation_config, watchlist_path)
            try:
                cfg = _load_config(config_path)
            except Exception:  # noqa: BLE001
                continue
            loaded_configs.append((watchlist_asset, config_path, cfg))
        if not loaded_configs:
            return None

        base_company = self._pick_company_snapshot(loaded_configs)
        limitations = self._collect_company_limitations(loaded_configs, base_company)
        balance_sheet = self._resolve_balance_sheet_snapshot(
            ticker=ticker,
            company=base_company,
            replay=replay,
        )
        limitations.extend(balance_sheet.limitations)
        asset_buckets = self._resolve_asset_buckets(
            ticker=ticker,
            loaded_configs=loaded_configs,
            company_snapshot=balance_sheet.company,
            knowledge=knowledge,
            limitations=limitations,
        )
        if not asset_buckets:
            return None

        market_cap = self._resolve_market_cap(
            ticker=ticker,
            company=balance_sheet.company,
            price_source=price_source,
            knowledge=knowledge,
            replay=replay,
        )
        if market_cap is None:
            return None

        override = self.overrides.for_ticker(ticker)
        config_quality_summary = _summarize_config_qualities(
            [
                _infer_config_quality(raw_cfg, config_path)
                for _, config_path, raw_cfg in loaded_configs
            ]
        )
        adjustment_buckets = self._build_adjustment_buckets(
            company=balance_sheet.company,
            balance_sheet=balance_sheet,
            override=override,
        )
        if override.notes:
            limitations.append(f"override_note:{override.notes}")

        buckets = asset_buckets + adjustment_buckets
        modeled_asset_value = round(
            sum(bucket.value_millions for bucket in asset_buckets),
            6,
        )
        platform_value = round(
            sum(
                bucket.value_millions
                for bucket in adjustment_buckets
                if bucket.bucket_type == "platform"
            ),
            6,
        )
        unmodeled_value = round(
            sum(
                bucket.value_millions
                for bucket in adjustment_buckets
                if bucket.bucket_type == "unmodeled_pipeline"
            ),
            6,
        )
        royalty_value = round(
            sum(
                bucket.value_millions
                for bucket in adjustment_buckets
                if bucket.bucket_type == "royalty"
            ),
            6,
        )
        dilution_reserve = round(
            sum(
                -bucket.value_millions
                for bucket in adjustment_buckets
                if bucket.bucket_type == "dilution_reserve"
            ),
            6,
        )
        sotp_equity_value = round(sum(bucket.value_millions for bucket in buckets), 6)
        if sotp_equity_value <= 0:
            return None

        shares = float(balance_sheet.company.shares_outstanding_millions)
        market_cap_value = float(market_cap.market_cap_millions)
        net_cash = float(balance_sheet.company.net_cash_millions)
        enterprise_value = round(market_cap_value - net_cash, 6)
        sotp_per_share = round(sotp_equity_value / shares, 6)
        sotp_discount = round(sotp_equity_value / market_cap_value, 6)
        recency = self._assess_balance_sheet_recency(balance_sheet)
        ranked_sotp_discount = round(sotp_discount * recency.penalty, 6)
        modeled_coverage = round(
            max(modeled_asset_value, 0.0) / sotp_equity_value,
            6,
        )
        modeled_confidences = [bucket.source_confidence for bucket in asset_buckets]
        modeled_asset_confidence_min = round(min(modeled_confidences), 6)
        modeled_asset_confidence_avg = round(
            sum(modeled_confidences) / len(modeled_confidences),
            6,
        )
        (
            actionable_coverage_pct,
            actionable_confidence_pct,
            structured_input_count,
            structured_input_confidence_min,
            structured_input_confidence_avg,
            has_structured_inputs,
        ) = self._compute_actionability_metrics(buckets)
        mcap_trend_3m_pct = self._resolve_mcap_trend_3m(
            ticker=ticker,
            knowledge=knowledge,
            replay=replay,
        )
        reconciliation = self._assess_reconciliation(
            sotp_equity_value_millions=sotp_equity_value,
            market_cap_millions=market_cap_value,
            mcap_trend_3m_pct=mcap_trend_3m_pct,
            weighted_confidence=actionable_confidence_pct,
        )
        limitations.extend(recency.limitations)
        limitations.extend(reconciliation.limitations)
        pack_quality = self._compute_pack_quality_metrics(
            buckets=buckets,
            sotp_equity_value=sotp_equity_value,
        )
        action_policy = self._determine_action_policy(
            market_cap_millions=market_cap_value,
            ranked_sotp_discount=ranked_sotp_discount,
            modeled_asset_coverage_pct=modeled_coverage,
            modeled_asset_confidence_min=modeled_asset_confidence_min,
            actionable_coverage_pct=actionable_coverage_pct,
            actionable_confidence_pct=actionable_confidence_pct,
            asset_count_modeled=len(asset_buckets),
            has_structured_inputs=has_structured_inputs,
            pack_quality=pack_quality,
            recency=recency,
            reconciliation=reconciliation,
        )

        if not balance_sheet.is_point_in_time:
            limitations.append(
                "balance_sheet_latest_config_snapshot_not_point_in_time"
            )
        if len(asset_buckets) == 1 and platform_value == 0 and unmodeled_value == 0:
            limitations.append("single_modeled_asset_company_no_extra_sotp_bucket")
        if len(loaded_configs) > 1 and any(
            bucket.source != "stored_screen_snapshot" for bucket in asset_buckets
        ):
            limitations.append(
                "multi_asset_company_uses_config_valuations_not_per_asset_historical_snapshots"
            )

        return CompanySOTPResult(
            rank=0,
            company_id=balance_sheet.company.id,
            company_name=balance_sheet.company.name,
            ticker=ticker,
            snapshot_date=self.as_of_date,
            asset_count_modeled=len(asset_buckets),
            modeled_asset_ids=[bucket.bucket_id for bucket in asset_buckets],
            market_cap_millions=round(market_cap_value, 6),
            enterprise_value_millions=enterprise_value,
            net_cash_millions=round(net_cash, 6),
            shares_outstanding_millions=round(shares, 6),
            modeled_asset_value_millions=modeled_asset_value,
            platform_value_millions=platform_value,
            unmodeled_pipeline_value_millions=unmodeled_value,
            royalty_value_millions=royalty_value,
            dilution_reserve_millions=dilution_reserve,
            sotp_equity_value_millions=sotp_equity_value,
            sotp_per_share=sotp_per_share,
            sotp_discount=sotp_discount,
            ranked_sotp_discount=ranked_sotp_discount,
            reconciliation_gap_millions=reconciliation.gap_millions,
            reconciliation_gap_pct=reconciliation.gap_pct,
            reconciliation_status=reconciliation.status,
            reconciliation_passes_gate=reconciliation.passes_gate,
            mcap_trend_3m_pct=reconciliation.mcap_trend_3m_pct,
            sotp_tier=reconciliation.tier_result.tier,
            sotp_action=reconciliation.tier_result.action,
            sotp_confidence_tier=reconciliation.tier_result.confidence_tier,
            sotp_tier_reason=reconciliation.tier_result.reason,
            modeled_asset_coverage_pct=modeled_coverage,
            actionable_coverage_pct=actionable_coverage_pct,
            actionable_confidence_pct=actionable_confidence_pct,
            structured_input_count=structured_input_count,
            structured_input_confidence_min=structured_input_confidence_min,
            structured_input_confidence_avg=structured_input_confidence_avg,
            manual_bucket_share_pct=pack_quality.manual_bucket_share_pct,
            manual_bucket_confidence_avg=pack_quality.manual_bucket_confidence_avg,
            n_bucket_sources=pack_quality.n_bucket_sources,
            market_cap_source=market_cap.source,
            balance_sheet_source=balance_sheet.source,
            balance_sheet_source_ref=balance_sheet.source_ref,
            balance_sheet_snapshot_date=balance_sheet.snapshot_date,
            balance_sheet_period_end_date=balance_sheet.period_end_date,
            balance_sheet_form_type=balance_sheet.form_type,
            balance_sheet_is_point_in_time=balance_sheet.is_point_in_time,
            balance_sheet_age_days=recency.age_days,
            balance_sheet_passes_recency_gate=recency.passes_gate,
            balance_sheet_recency_penalty=recency.penalty,
            config_quality_summary=config_quality_summary,
            modeled_asset_confidence_min=modeled_asset_confidence_min,
            modeled_asset_confidence_avg=modeled_asset_confidence_avg,
            action_policy=action_policy.policy,
            action_reason=action_policy.reason,
            buckets=buckets,
            limitations=sorted(set(limitations)),
            notes=override.notes,
        )

    @staticmethod
    def _pick_company_snapshot(
        loaded_configs: list[tuple[WatchlistAsset, Path, dict]],
    ) -> Company:
        snapshots: list[Company] = []
        for _, _, raw_cfg in loaded_configs:
            _, company, _, _ = _build_objects(raw_cfg)
            snapshots.append(company)
        snapshots.sort(
            key=lambda company: (
                company.cash_millions,
                company.shares_outstanding_millions,
                company.name,
            ),
            reverse=True,
        )
        return snapshots[0]

    @staticmethod
    def _collect_company_limitations(
        loaded_configs: list[tuple[WatchlistAsset, Path, dict]],
        base_company: Company,
    ) -> list[str]:
        limitations: list[str] = []
        for _, config_path, raw_cfg in loaded_configs:
            company_cfg = raw_cfg.get("company", {})
            shares = float(company_cfg.get("shares_outstanding_millions") or 0.0)
            cash = float(company_cfg.get("cash_millions") or 0.0)
            debt = float(company_cfg.get("debt_millions") or 0.0)
            if abs(shares - base_company.shares_outstanding_millions) > 1e-6:
                limitations.append(
                    f"inconsistent_shares_outstanding:{config_path.name}"
                )
            if abs(cash - base_company.cash_millions) > 1e-6:
                limitations.append(f"inconsistent_cash_snapshot:{config_path.name}")
            if abs(debt - base_company.debt_millions) > 1e-6:
                limitations.append(f"inconsistent_debt_snapshot:{config_path.name}")
        return limitations

    def _resolve_asset_buckets(
        self,
        *,
        ticker: str,
        loaded_configs: list[tuple[WatchlistAsset, Path, dict]],
        company_snapshot: Company,
        knowledge: Optional[KnowledgeStore],
        limitations: list[str],
    ) -> list[CompanySOTPBucket]:
        buckets: list[CompanySOTPBucket] = []
        allow_stored_snapshot = self.prefer_stored_screen_context and knowledge is not None

        for watchlist_asset, config_path, raw_cfg in loaded_configs:
            asset_cfg = raw_cfg.get("asset", {})
            asset_id = str(asset_cfg.get("id") or watchlist_asset.asset_id)
            label = str(
                asset_cfg.get("name")
                or watchlist_asset.drug_name
                or watchlist_asset.asset_id
            )
            config_quality = _infer_config_quality(raw_cfg, config_path)
            valid_from = _config_valid_from(raw_cfg)
            if valid_from is not None and self.as_of_date < valid_from:
                limitations.append(
                    f"config_not_applicable_pre_thesis:{asset_id}:{valid_from.isoformat()}"
                )
                continue
            stored_snapshot = (
                knowledge.get_screen_snapshot_for_asset_on_or_before(
                    asset_id=asset_id,
                    as_of=self.as_of_date,
                )
                if allow_stored_snapshot
                else None
            )
            if (
                stored_snapshot is None
                and allow_stored_snapshot
                and len(loaded_configs) == 1
            ):
                stored_snapshot = knowledge.get_screen_snapshot_for_ticker_on_or_before(
                    ticker=ticker,
                    as_of=self.as_of_date,
                )
            if stored_snapshot is not None and stored_snapshot.get("rnpv_millions") is not None:
                buckets.append(
                    CompanySOTPBucket(
                        bucket_id=asset_id,
                        bucket_type="modeled_asset",
                        label=label,
                        value_millions=round(float(stored_snapshot["rnpv_millions"]), 6),
                        source="stored_screen_snapshot",
                        source_kind="modeled",
                        source_as_of=_parse_optional_date(stored_snapshot.get("snapshot_date")),
                        source_confidence=_bucket_confidence_from_quality(
                            _prefer_higher_confidence_quality(
                                stored_snapshot.get("config_quality"),
                                config_quality,
                            )
                        ),
                        source_ref=(
                            f"screen_snapshot:{stored_snapshot.get('ticker') or ticker}:"
                            f"{asset_id}:{stored_snapshot.get('snapshot_date') or self.as_of_date.isoformat()}"
                        ),
                        notes=f"snapshot_date={stored_snapshot['snapshot_date']}",
                        modeled=True,
                    )
                )
                continue

            cache_key = str(config_path.resolve())
            if cache_key in self.asset_rnpv_cache:
                rnpv_millions = self.asset_rnpv_cache[cache_key]
            else:
                rnpv_millions = self._compute_asset_rnpv(
                    raw_cfg=raw_cfg,
                    config_path=config_path,
                    company=company_snapshot,
                )
                if rnpv_millions is not None:
                    self.asset_rnpv_cache[cache_key] = rnpv_millions
            if rnpv_millions is None:
                limitations.append(f"asset_valuation_failed:{asset_id}")
                continue
            buckets.append(
                CompanySOTPBucket(
                    bucket_id=asset_id,
                    bucket_type="modeled_asset",
                    label=label,
                    value_millions=round(rnpv_millions, 6),
                    source="config_valuation",
                    source_kind="modeled",
                    source_as_of=self.as_of_date,
                    source_confidence=_bucket_confidence_from_quality(config_quality),
                    source_ref=str(config_path),
                    notes=(
                        f"{config_path}; config_quality={config_quality}"
                        if config_quality is not None
                        else str(config_path)
                    ),
                    modeled=True,
                )
            )
        return buckets

    @staticmethod
    def _compute_asset_rnpv(
        *,
        raw_cfg: dict,
        config_path: Path,
        company: Company,
    ) -> Optional[float]:
        try:
            asset, _, trials, market_model = _build_objects(raw_cfg)
            pos_adjusters, apply_pos_model = _build_pos_adjusters(raw_cfg)
            design_adjusters, apply_design_model = _build_design_adjusters(raw_cfg)
            engine = ValuationEngine(
                asset=asset,
                company=company,
                trials=trials,
                market_model=market_model,
                pos_adjusters=pos_adjusters,
                design_adjusters=design_adjusters,
                apply_pos_model=apply_pos_model,
                apply_design_model=apply_design_model,
                analyst_notes=raw_cfg.get("analyst_notes"),
                config_path=str(config_path),
                limitations=raw_cfg.get("limitations"),
                thesis_changers=raw_cfg.get("thesis_changers"),
            )
            output = engine.run()
        except Exception:  # noqa: BLE001
            return None
        return float(output.rnpv.rnpv_millions)

    def _resolve_market_cap(
        self,
        *,
        ticker: str,
        company: Company,
        price_source: str,
        knowledge: Optional[KnowledgeStore],
        replay: Optional[ReplayStore],
    ) -> Optional[_ResolvedMarketCap]:
        if price_source == "yfinance":
            return self._market_cap_from_yfinance(ticker=ticker, company=company)
        return self._market_cap_from_replay(
            ticker=ticker,
            company=company,
            knowledge=knowledge,
            replay=replay,
        )

    def _market_cap_from_yfinance(
        self,
        *,
        ticker: str,
        company: Company,
    ) -> Optional[_ResolvedMarketCap]:
        try:
            fundamentals = self.fundamentals_fetcher(ticker)
        except Exception:  # noqa: BLE001
            fundamentals = {}
        market_cap = fundamentals.get("market_cap_millions")
        if market_cap is not None and float(market_cap) > 0:
            return _ResolvedMarketCap(
                market_cap_millions=round(float(market_cap), 6),
                source="yfinance_market_cap",
            )
        price = fundamentals.get("current_price")
        if price is not None and float(price) > 0 and company.shares_outstanding_millions > 0:
            return _ResolvedMarketCap(
                market_cap_millions=round(
                    float(price) * float(company.shares_outstanding_millions),
                    6,
                ),
                source="yfinance_price_x_shares",
            )
        return self._fallback_company_market_cap(company)

    def _market_cap_from_replay(
        self,
        *,
        ticker: str,
        company: Company,
        knowledge: Optional[KnowledgeStore],
        replay: Optional[ReplayStore],
    ) -> Optional[_ResolvedMarketCap]:
        if knowledge is not None:
            price_row = knowledge.get_price_on_or_before(ticker, self.as_of_date)
            if price_row is not None:
                if price_row.market_cap_millions is not None and price_row.market_cap_millions > 0:
                    return _ResolvedMarketCap(
                        market_cap_millions=round(float(price_row.market_cap_millions), 6),
                        source="knowledge_store_market_cap",
                    )
                if price_row.close_usd > 0 and company.shares_outstanding_millions > 0:
                    return _ResolvedMarketCap(
                        market_cap_millions=round(
                            float(price_row.close_usd)
                            * float(company.shares_outstanding_millions),
                            6,
                        ),
                        source="knowledge_store_price_x_shares",
                    )
        if replay is not None:
            price = replay.get_price(ticker, self.as_of_date)
            if price is not None and price > 0 and company.shares_outstanding_millions > 0:
                return _ResolvedMarketCap(
                    market_cap_millions=round(
                        float(price) * float(company.shares_outstanding_millions),
                        6,
                    ),
                    source="replay_store_price_x_shares",
                )
        return self._fallback_company_market_cap(company)

    @staticmethod
    def _fallback_company_market_cap(company: Company) -> Optional[_ResolvedMarketCap]:
        if company.market_cap_millions is not None and company.market_cap_millions > 0:
            return _ResolvedMarketCap(
                market_cap_millions=round(float(company.market_cap_millions), 6),
                source="config_market_cap",
            )
        if company.current_price is not None and company.current_price > 0:
            return _ResolvedMarketCap(
                market_cap_millions=round(
                    float(company.current_price)
                    * float(company.shares_outstanding_millions),
                    6,
                ),
                source="config_price_x_shares",
            )
        return None

    def _resolve_mcap_trend_3m(
        self,
        *,
        ticker: str,
        knowledge: Optional[KnowledgeStore],
        replay: Optional[ReplayStore],
    ) -> Optional[float]:
        if knowledge is not None:
            trend = compute_mcap_trend_3m(
                ticker=ticker,
                snapshot_date=self.as_of_date,
                knowledge_store=knowledge,
            )
            if trend is not None:
                return trend
        if replay is not None:
            lookback_date = self.as_of_date - timedelta(days=90)
            current_price = replay.get_price(ticker, self.as_of_date)
            past_price = replay.get_price(ticker, lookback_date)
            if current_price is not None and past_price is not None and past_price > 0:
                return round((current_price / past_price - 1.0) * 100.0, 6)
        return None

    def _build_adjustment_buckets(
        self,
        *,
        company: Company,
        balance_sheet: _ResolvedBalanceSheet,
        override: CompanySOTPOverride,
    ) -> list[CompanySOTPBucket]:
        buckets: list[CompanySOTPBucket] = [
            CompanySOTPBucket(
                bucket_id=f"{company.id}:net_cash",
                bucket_type="net_cash",
                label="Net cash",
                value_millions=round(float(company.net_cash_millions), 6),
                source=balance_sheet.source,
                source_kind="inferred",
                source_as_of=balance_sheet.snapshot_date,
                source_confidence=(
                    0.95 if balance_sheet.is_point_in_time else self.config_balance_sheet_penalty
                ),
                source_ref=balance_sheet.source_ref,
                modeled=False,
            )
        ]
        structured_inputs = self._resolve_structured_inputs(override)
        if structured_inputs:
            for item in structured_inputs:
                label = item.label or item.bucket_type.replace("_", " ").title()
                value = float(item.value_millions)
                if item.bucket_type == "dilution_reserve":
                    value = -abs(value)
                buckets.append(
                    CompanySOTPBucket(
                        bucket_id=item.bucket_id,
                        bucket_type=item.bucket_type,
                        label=label,
                        value_millions=round(value, 6),
                        source=item.source,
                        source_kind=item.source_kind,
                        source_as_of=item.as_of_date,
                        source_confidence=round(float(item.confidence), 6),
                        source_ref=item.source_ref,
                        notes=item.notes,
                        modeled=False,
                    )
                )
            return buckets

        for bucket_type, label, value in (
            ("platform", "Platform value", override.platform_value_millions),
            (
                "unmodeled_pipeline",
                "Unmodeled pipeline value",
                override.unmodeled_pipeline_value_millions,
            ),
            ("royalty", "Royalty / milestone value", override.royalty_value_millions),
        ):
            if value == 0:
                continue
            buckets.append(
                CompanySOTPBucket(
                    bucket_id=f"{company.id}:{bucket_type}",
                    bucket_type=bucket_type,
                    label=label,
                    value_millions=round(float(value), 6),
                    source="company_sotp_legacy_override",
                    source_kind="analyst_bridge",
                    source_as_of=None,
                    source_confidence=0.65,
                    modeled=False,
                )
            )

        reserve_millions = override.dilution_reserve_millions
        if reserve_millions is None:
            reserve_quarters = override.dilution_reserve_quarters
            if reserve_quarters is None:
                reserve_quarters = self.overrides.defaults.dilution_reserve_quarters
            if (
                reserve_quarters
                and company.burn_rate_millions_per_quarter is not None
                and company.burn_rate_millions_per_quarter > 0
            ):
                reserve_millions = (
                    float(company.burn_rate_millions_per_quarter)
                    * float(reserve_quarters)
                )
        if reserve_millions and reserve_millions > 0:
            buckets.append(
                CompanySOTPBucket(
                    bucket_id=f"{company.id}:dilution_reserve",
                    bucket_type="dilution_reserve",
                    label="Dilution reserve",
                    value_millions=round(-float(reserve_millions), 6),
                    source="company_sotp_legacy_override",
                    source_kind="analyst_bridge",
                    source_as_of=None,
                    source_confidence=0.65,
                    modeled=False,
                )
            )
        return buckets

    def _resolve_balance_sheet_snapshot(
        self,
        *,
        ticker: str,
        company: Company,
        replay: Optional[ReplayStore],
    ) -> _ResolvedBalanceSheet:
        if replay is None:
            return _ResolvedBalanceSheet(
                company=company,
                source="config_company_snapshot",
                is_point_in_time=False,
            )

        snapshot = replay.get_balance_sheet_snapshot(ticker, self.as_of_date)
        if snapshot is None:
            return _ResolvedBalanceSheet(
                company=company,
                source="config_company_snapshot",
                is_point_in_time=False,
            )

        limitations: list[str] = []
        updated_company = company.model_copy(
            update={
                "cash_millions": (
                    float(snapshot.get("cash_millions"))
                    if snapshot.get("cash_millions") is not None
                    else company.cash_millions
                ),
                "debt_millions": (
                    float(snapshot.get("debt_millions"))
                    if snapshot.get("debt_millions") is not None
                    else company.debt_millions
                ),
                "shares_outstanding_millions": (
                    float(snapshot.get("shares_outstanding_millions"))
                    if snapshot.get("shares_outstanding_millions") is not None
                    else company.shares_outstanding_millions
                ),
                "burn_rate_millions_per_quarter": (
                    float(snapshot.get("burn_rate_millions_per_quarter"))
                    if snapshot.get("burn_rate_millions_per_quarter") is not None
                    else company.burn_rate_millions_per_quarter
                ),
            }
        )
        if snapshot.get("debt_millions") is None:
            limitations.append("balance_sheet_debt_fallback_to_config")
        if snapshot.get("cash_millions") is None:
            limitations.append("balance_sheet_cash_fallback_to_config")
        if snapshot.get("shares_outstanding_millions") is None:
            limitations.append("balance_sheet_shares_fallback_to_config")
        if snapshot.get("burn_rate_millions_per_quarter") is None:
            limitations.append("balance_sheet_burn_fallback_to_config")

        return _ResolvedBalanceSheet(
            company=updated_company,
            source=str(snapshot.get("source_type") or "balance_sheet_snapshot"),
            source_ref=str(snapshot.get("source_ref") or ""),
            snapshot_date=_parse_optional_date(snapshot.get("snapshot_date")),
            period_end_date=_parse_optional_date(snapshot.get("period_end_date")),
            form_type=snapshot.get("form_type"),
            is_point_in_time=True,
            limitations=limitations,
        )

    def _assess_balance_sheet_recency(
        self,
        balance_sheet: _ResolvedBalanceSheet,
    ) -> _BalanceSheetRecency:
        if not balance_sheet.is_point_in_time or balance_sheet.snapshot_date is None:
            return _BalanceSheetRecency(
                age_days=None,
                passes_gate=False,
                penalty=round(self.config_balance_sheet_penalty, 6),
                limitations=["balance_sheet_recency_gate_not_met"],
            )

        age_days = max((self.as_of_date - balance_sheet.snapshot_date).days, 0)
        if age_days <= self.balance_sheet_soft_stale_days:
            return _BalanceSheetRecency(
                age_days=age_days,
                passes_gate=True,
                penalty=1.0,
            )
        if age_days > self.balance_sheet_hard_stale_days:
            return _BalanceSheetRecency(
                age_days=age_days,
                passes_gate=False,
                penalty=round(self.min_stale_balance_sheet_penalty, 6),
                limitations=[f"balance_sheet_recency_gate_exceeded:{age_days}d"],
            )

        span = self.balance_sheet_hard_stale_days - self.balance_sheet_soft_stale_days
        progress = (age_days - self.balance_sheet_soft_stale_days) / span
        penalty = 1.0 - ((1.0 - self.min_stale_balance_sheet_penalty) * progress)
        return _BalanceSheetRecency(
            age_days=age_days,
            passes_gate=True,
            penalty=round(max(self.min_stale_balance_sheet_penalty, penalty), 6),
            limitations=[f"balance_sheet_stale_penalty:{age_days}d"],
        )

    def _resolve_structured_inputs(
        self,
        override: CompanySOTPOverride,
    ) -> list[CompanySOTPStructuredInput]:
        if override.snapshots:
            eligible_snapshots = [
                snapshot
                for snapshot in override.snapshots
                if snapshot.as_of_date <= self.as_of_date
            ]
            if eligible_snapshots:
                latest_snapshot = max(
                    eligible_snapshots,
                    key=lambda snapshot: snapshot.as_of_date,
                )
                return self._select_latest_structured_inputs(latest_snapshot.inputs)
            return []
        return self._select_latest_structured_inputs(override.inputs)

    def _select_latest_structured_inputs(
        self,
        inputs: list[CompanySOTPStructuredInput],
    ) -> list[CompanySOTPStructuredInput]:
        if not inputs:
            return []
        selected: dict[str, CompanySOTPStructuredInput] = {}
        for item in inputs:
            if item.as_of_date is not None and item.as_of_date > self.as_of_date:
                continue
            current = selected.get(item.bucket_id)
            if current is None:
                selected[item.bucket_id] = item
                continue
            current_date = current.as_of_date or date.min
            item_date = item.as_of_date or date.min
            if item_date >= current_date:
                selected[item.bucket_id] = item
        return [
            selected[key]
            for key in sorted(
                selected,
                key=lambda value: (
                    selected[value].bucket_type,
                    value,
                ),
            )
        ]

    def _compute_actionability_metrics(
        self,
        buckets: list[CompanySOTPBucket],
    ) -> tuple[float, float, int, Optional[float], Optional[float], bool]:
        total_abs_value = sum(abs(bucket.value_millions) for bucket in buckets)
        if total_abs_value <= 0:
            return 0.0, 0.0, 0, None, None, False

        covered_abs_value = 0.0
        confidence_weighted_abs_value = 0.0
        structured_confidences: list[float] = []

        for bucket in buckets:
            magnitude = abs(bucket.value_millions)
            if magnitude <= 0:
                continue
            confidence = float(bucket.source_confidence)
            confidence_weighted_abs_value += magnitude * confidence

            is_structured_bucket = self._is_structured_adjustment_bucket(bucket)
            if is_structured_bucket:
                structured_confidences.append(confidence)

            qualifies_for_coverage = bucket.bucket_type in {"modeled_asset", "net_cash"} or (
                is_structured_bucket
                and self._structured_bucket_meets_evidence_standard(bucket)
            )
            if qualifies_for_coverage:
                covered_abs_value += magnitude

        structured_input_count = len(structured_confidences)
        structured_input_confidence_min = (
            round(min(structured_confidences), 6) if structured_confidences else None
        )
        structured_input_confidence_avg = (
            round(sum(structured_confidences) / len(structured_confidences), 6)
            if structured_confidences
            else None
        )
        return (
            round(min(1.0, covered_abs_value / total_abs_value), 6),
            round(min(1.0, confidence_weighted_abs_value / total_abs_value), 6),
            structured_input_count,
            structured_input_confidence_min,
            structured_input_confidence_avg,
            structured_input_count > 0,
        )

    @staticmethod
    def _is_structured_adjustment_bucket(bucket: CompanySOTPBucket) -> bool:
        return (
            bucket.bucket_type
            in {"platform", "unmodeled_pipeline", "royalty", "dilution_reserve"}
            and bucket.source != "company_sotp_legacy_override"
            and bucket.source_as_of is not None
            and bool(bucket.source)
            and bool(bucket.source_ref)
        )

    def _structured_bucket_meets_evidence_standard(
        self,
        bucket: CompanySOTPBucket,
    ) -> bool:
        minimum = max(
            self.min_structured_input_confidence_for_auto_action,
            _STRUCTURED_SOURCE_CONFIDENCE_FLOORS.get(bucket.source_kind, 0.0),
        )
        if bucket.bucket_type == "platform":
            minimum = max(minimum, self.min_platform_bucket_confidence_for_auto_action)
        elif bucket.bucket_type == "unmodeled_pipeline":
            minimum = max(
                minimum,
                self.min_unmodeled_pipeline_bucket_confidence_for_auto_action,
            )
        elif bucket.bucket_type == "royalty":
            minimum = max(minimum, self.min_royalty_bucket_confidence_for_auto_action)
        elif bucket.bucket_type == "dilution_reserve":
            minimum = max(minimum, self.min_dilution_bucket_confidence_for_auto_action)
        return float(bucket.source_confidence) >= minimum

    def _compute_pack_quality_metrics(
        self,
        *,
        buckets: list[CompanySOTPBucket],
        sotp_equity_value: float,
    ) -> _PackQualityMetrics:
        if sotp_equity_value <= 0:
            return _PackQualityMetrics()

        manual_abs_value = 0.0
        manual_confidence_weighted_abs_value = 0.0
        largest_manual_abs_value = 0.0
        largest_manual_bucket_source_ref_count = 0
        bucket_sources: set[str] = set()

        for bucket in buckets:
            if not self._is_structured_adjustment_bucket(bucket):
                continue
            source_refs = _split_source_refs(bucket.source_ref)
            bucket_sources.update(source_refs)
            if bucket.source_kind not in _LOW_EVIDENCE_SOURCE_KINDS:
                continue
            magnitude = abs(bucket.value_millions)
            manual_abs_value += magnitude
            manual_confidence_weighted_abs_value += magnitude * float(bucket.source_confidence)
            if magnitude > largest_manual_abs_value:
                largest_manual_abs_value = magnitude
                largest_manual_bucket_source_ref_count = len(source_refs)
            elif magnitude == largest_manual_abs_value:
                largest_manual_bucket_source_ref_count = max(
                    largest_manual_bucket_source_ref_count,
                    len(source_refs),
                )

        manual_confidence_avg = (
            round(manual_confidence_weighted_abs_value / manual_abs_value, 6)
            if manual_abs_value > 0
            else None
        )
        return _PackQualityMetrics(
            manual_bucket_share_pct=round(min(1.0, manual_abs_value / sotp_equity_value), 6),
            manual_bucket_confidence_avg=manual_confidence_avg,
            n_bucket_sources=len(bucket_sources),
            largest_manual_bucket_share_pct=round(
                min(1.0, largest_manual_abs_value / sotp_equity_value),
                6,
            ),
            largest_manual_bucket_source_ref_count=largest_manual_bucket_source_ref_count,
        )

    def _determine_action_policy(
        self,
        *,
        market_cap_millions: float,
        ranked_sotp_discount: float,
        modeled_asset_coverage_pct: float,
        modeled_asset_confidence_min: float,
        actionable_coverage_pct: float,
        actionable_confidence_pct: float,
        asset_count_modeled: int,
        has_structured_inputs: bool,
        pack_quality: _PackQualityMetrics,
        recency: _BalanceSheetRecency,
        reconciliation: _ReconciliationAssessment,
    ) -> _ActionPolicyDecision:
        if not recency.passes_gate:
            return _ActionPolicyDecision(
                policy="needs_manual_review",
                reason="balance_sheet_recency_gate_failed",
            )
        if reconciliation.tier_result.tier == "avoid":
            return _ActionPolicyDecision(
                policy="avoid",
                reason=reconciliation.tier_result.reason,
            )
        if (
            market_cap_millions < self.min_market_cap_millions
            or market_cap_millions > self.max_market_cap_millions
        ):
            return _ActionPolicyDecision(
                policy="avoid",
                reason=f"market_cap_outside_band:{market_cap_millions:.0f}M",
            )
        if reconciliation.tier_result.tier == "needs_manual_review":
            return _ActionPolicyDecision(
                policy="needs_manual_review",
                reason=reconciliation.tier_result.reason,
            )
        if (
            asset_count_modeled == 1
            and market_cap_millions >= self.require_structured_inputs_above_market_cap_millions
            and not has_structured_inputs
            and modeled_asset_coverage_pct < self.min_modeled_asset_coverage_pct
        ):
            return _ActionPolicyDecision(
                policy="needs_manual_review",
                reason="missing_structured_company_inputs_for_large_cap_single_asset",
            )
        if (
            pack_quality.largest_manual_bucket_share_pct
            >= self.max_single_manual_bucket_share_without_multi_source
            and pack_quality.largest_manual_bucket_source_ref_count
            < self.min_bucket_sources_for_high_manual_share
        ):
            return _ActionPolicyDecision(
                policy="needs_manual_review",
                reason=(
                    "manual_bucket_source_concentration:"
                    f"{pack_quality.largest_manual_bucket_share_pct:.2f}x/"
                    f"{pack_quality.largest_manual_bucket_source_ref_count}src"
                ),
            )
        if (
            pack_quality.manual_bucket_share_pct >= self.max_manual_bucket_share_for_auto_action
            and (
                pack_quality.manual_bucket_confidence_avg is None
                or pack_quality.manual_bucket_confidence_avg
                < self.min_manual_bucket_confidence_avg
            )
        ):
            confidence = (
                f"{pack_quality.manual_bucket_confidence_avg:.2f}"
                if pack_quality.manual_bucket_confidence_avg is not None
                else "n/a"
            )
            return _ActionPolicyDecision(
                policy="needs_manual_review",
                reason=(
                    "manual_bucket_quality_below_threshold:"
                    f"{pack_quality.manual_bucket_share_pct:.2f}x/{confidence}"
                ),
            )
        if actionable_coverage_pct < self.min_actionable_coverage_pct:
            return _ActionPolicyDecision(
                policy="needs_manual_review",
                reason=f"actionable_coverage_below_threshold:{actionable_coverage_pct:.2f}",
            )
        if actionable_confidence_pct < self.min_actionable_confidence_pct:
            return _ActionPolicyDecision(
                policy="needs_manual_review",
                reason=f"actionable_confidence_below_threshold:{actionable_confidence_pct:.2f}",
            )
        if modeled_asset_confidence_min < self.min_modeled_asset_confidence_for_auto_action:
            return _ActionPolicyDecision(
                policy="needs_manual_review",
                reason=f"modeled_asset_confidence_below_threshold:{modeled_asset_confidence_min:.2f}",
            )
        if reconciliation.tier_result.tier == "watch":
            return _ActionPolicyDecision(
                policy="watch",
                reason=reconciliation.tier_result.reason,
            )
        if ranked_sotp_discount < self.watch_discount_threshold:
            return _ActionPolicyDecision(
                policy="avoid",
                reason=f"ranked_discount_below_watch_threshold:{ranked_sotp_discount:.2f}x",
            )
        if ranked_sotp_discount >= self.buy_discount_threshold:
            return _ActionPolicyDecision(
                policy="buy",
                reason=f"ranked_discount_above_buy_threshold:{ranked_sotp_discount:.2f}x",
            )
        if ranked_sotp_discount >= self.watch_discount_threshold:
            return _ActionPolicyDecision(
                policy="watch",
                reason=f"ranked_discount_above_watch_threshold:{ranked_sotp_discount:.2f}x",
            )
        return _ActionPolicyDecision(
            policy="avoid",
            reason=f"ranked_discount_below_watch_threshold:{ranked_sotp_discount:.2f}x",
        )

    def _resolve_knowledge_db_path(self, config_path: str | None) -> Optional[Path]:
        if self.knowledge_db_path is not None:
            return self.knowledge_db_path
        if config_path:
            candidate = Path(config_path)
            if not candidate.is_absolute():
                candidate = (_REPO_ROOT / candidate).resolve()
            return candidate
        return None

    @staticmethod
    def _open_knowledge_store(
        db_path: Optional[Path],
        *,
        create: bool = False,
    ) -> Optional[KnowledgeStore]:
        if db_path is None:
            return None
        path = Path(db_path)
        if not path.exists() and not create:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        return KnowledgeStore(path)

    def _open_replay_store(self, *, required: bool, enabled: bool) -> Optional[ReplayStore]:
        if not enabled:
            return None
        if not self.replay_store_path.exists():
            if required:
                raise FileNotFoundError(f"ReplayStore DB not found: {self.replay_store_path}")
            return None
        return ReplayStore(str(self.replay_store_path))

    def _assess_reconciliation(
        self,
        *,
        sotp_equity_value_millions: float,
        market_cap_millions: float,
        mcap_trend_3m_pct: Optional[float],
        weighted_confidence: float,
    ) -> _ReconciliationAssessment:
        gap_millions = round(sotp_equity_value_millions - market_cap_millions, 6)
        gap_pct = round(gap_millions / market_cap_millions, 6)
        ratio = round(sotp_equity_value_millions / market_cap_millions, 6)
        tier_result = classify_sotp_tier(
            ratio=ratio,
            mcap_trend_3m=mcap_trend_3m_pct,
            weighted_confidence=weighted_confidence,
        )
        limitations: list[str] = []
        if ratio < self.min_reconciliation_discount_for_auto_action:
            limitations.append(f"reconciliation_extreme_premium:{ratio:.2f}x")
            status = "extreme_premium"
        elif ratio > self.max_reconciliation_discount_for_auto_action:
            limitations.append(f"reconciliation_extreme_discount:{ratio:.2f}x")
            status = "extreme_discount"
        elif ratio < 1.0:
            status = "premium"
        else:
            status = "discounted"
        return _ReconciliationAssessment(
            gap_millions=gap_millions,
            gap_pct=gap_pct,
            ratio=ratio,
            status=status,
            passes_gate=tier_result.tier not in {"needs_manual_review", "avoid"},
            mcap_trend_3m_pct=mcap_trend_3m_pct,
            tier_result=tier_result,
            limitations=limitations,
        )

    def _write_csv(self, rows: list[CompanySOTPResult]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f"company_sotp_{self.as_of_date.isoformat()}.csv"
        fieldnames = [
            "rank",
            "ticker",
            "company_name",
            "snapshot_date",
            "asset_count_modeled",
            "market_cap_millions",
            "enterprise_value_millions",
            "net_cash_millions",
            "modeled_asset_value_millions",
            "platform_value_millions",
            "unmodeled_pipeline_value_millions",
            "royalty_value_millions",
            "dilution_reserve_millions",
            "sotp_equity_value_millions",
            "sotp_per_share",
            "sotp_discount",
            "ranked_sotp_discount",
            "reconciliation_gap_millions",
            "reconciliation_gap_pct",
            "reconciliation_status",
            "reconciliation_passes_gate",
            "mcap_trend_3m_pct",
            "sotp_tier",
            "sotp_action",
            "sotp_confidence_tier",
            "sotp_tier_reason",
            "extreme_discount",
            "modeled_asset_coverage_pct",
            "actionable_coverage_pct",
            "actionable_confidence_pct",
            "structured_input_count",
            "structured_input_confidence_min",
            "structured_input_confidence_avg",
            "manual_bucket_share_pct",
            "manual_bucket_confidence_avg",
            "n_bucket_sources",
            "market_cap_source",
            "balance_sheet_source",
            "balance_sheet_source_ref",
            "balance_sheet_snapshot_date",
            "balance_sheet_period_end_date",
            "balance_sheet_form_type",
            "balance_sheet_is_point_in_time",
            "balance_sheet_age_days",
            "balance_sheet_passes_recency_gate",
            "balance_sheet_recency_penalty",
            "config_quality_summary",
            "modeled_asset_confidence_min",
            "modeled_asset_confidence_avg",
            "action_policy",
            "action_reason",
            "modeled_asset_ids",
            "limitations",
            "notes",
        ]
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "rank": row.rank,
                        "ticker": row.ticker,
                        "company_name": row.company_name,
                        "snapshot_date": row.snapshot_date.isoformat(),
                        "asset_count_modeled": row.asset_count_modeled,
                        "market_cap_millions": row.market_cap_millions,
                        "enterprise_value_millions": row.enterprise_value_millions,
                        "net_cash_millions": row.net_cash_millions,
                        "modeled_asset_value_millions": row.modeled_asset_value_millions,
                        "platform_value_millions": row.platform_value_millions,
                        "unmodeled_pipeline_value_millions": row.unmodeled_pipeline_value_millions,
                        "royalty_value_millions": row.royalty_value_millions,
                        "dilution_reserve_millions": row.dilution_reserve_millions,
                        "sotp_equity_value_millions": row.sotp_equity_value_millions,
                        "sotp_per_share": row.sotp_per_share,
                        "sotp_discount": row.sotp_discount,
                        "ranked_sotp_discount": row.ranked_sotp_discount,
                        "reconciliation_gap_millions": row.reconciliation_gap_millions,
                        "reconciliation_gap_pct": row.reconciliation_gap_pct,
                        "reconciliation_status": row.reconciliation_status,
                        "reconciliation_passes_gate": row.reconciliation_passes_gate,
                        "mcap_trend_3m_pct": (
                            row.mcap_trend_3m_pct
                            if row.mcap_trend_3m_pct is not None
                            else ""
                        ),
                        "sotp_tier": row.sotp_tier,
                        "sotp_action": row.sotp_action,
                        "sotp_confidence_tier": row.sotp_confidence_tier,
                        "sotp_tier_reason": row.sotp_tier_reason,
                        "extreme_discount": row.extreme_discount,
                        "modeled_asset_coverage_pct": row.modeled_asset_coverage_pct,
                        "actionable_coverage_pct": row.actionable_coverage_pct,
                        "actionable_confidence_pct": row.actionable_confidence_pct,
                        "structured_input_count": row.structured_input_count,
                        "structured_input_confidence_min": (
                            row.structured_input_confidence_min
                            if row.structured_input_confidence_min is not None
                            else ""
                        ),
                        "structured_input_confidence_avg": (
                            row.structured_input_confidence_avg
                            if row.structured_input_confidence_avg is not None
                            else ""
                        ),
                        "manual_bucket_share_pct": row.manual_bucket_share_pct,
                        "manual_bucket_confidence_avg": (
                            row.manual_bucket_confidence_avg
                            if row.manual_bucket_confidence_avg is not None
                            else ""
                        ),
                        "n_bucket_sources": row.n_bucket_sources,
                        "market_cap_source": row.market_cap_source,
                        "balance_sheet_source": row.balance_sheet_source,
                        "balance_sheet_source_ref": row.balance_sheet_source_ref or "",
                        "balance_sheet_snapshot_date": (
                            row.balance_sheet_snapshot_date.isoformat()
                            if row.balance_sheet_snapshot_date
                            else ""
                        ),
                        "balance_sheet_period_end_date": (
                            row.balance_sheet_period_end_date.isoformat()
                            if row.balance_sheet_period_end_date
                            else ""
                        ),
                        "balance_sheet_form_type": row.balance_sheet_form_type or "",
                        "balance_sheet_is_point_in_time": row.balance_sheet_is_point_in_time,
                        "balance_sheet_age_days": (
                            row.balance_sheet_age_days
                            if row.balance_sheet_age_days is not None
                            else ""
                        ),
                        "balance_sheet_passes_recency_gate": row.balance_sheet_passes_recency_gate,
                        "balance_sheet_recency_penalty": row.balance_sheet_recency_penalty,
                        "config_quality_summary": row.config_quality_summary or "",
                        "modeled_asset_confidence_min": row.modeled_asset_confidence_min,
                        "modeled_asset_confidence_avg": row.modeled_asset_confidence_avg,
                        "action_policy": row.action_policy,
                        "action_reason": row.action_reason,
                        "modeled_asset_ids": "|".join(row.modeled_asset_ids),
                        "limitations": "|".join(row.limitations),
                        "notes": row.notes or "",
                    }
                )
        return out_path

    @staticmethod
    def render_report(
        rows: list[CompanySOTPResult],
        *,
        watchlist_path: str,
        source_mode: str = "live_recomputed",
        reference_snapshot_date: Optional[date] = None,
    ) -> str:
        lines = [
            _REPORT_SEPARATOR,
            f"COMPANY SOTP SCREEN — {rows[0].snapshot_date.isoformat() if rows else 'n/a'}",
            f"Watchlist: {watchlist_path} ({len(rows)} companies)",
            (
                f"Source mode: {source_mode} | Reference snapshot: "
                f"{reference_snapshot_date.isoformat() if reference_snapshot_date else 'n/a'}"
            ),
            _REPORT_SEPARATOR,
            "Rank  Ticker  MCap($M)  SOTP($M)  DiscAdj  Recon  Tier    BSAge  Cov%  Conf  Action   Notes",
        ]
        for row in rows:
            age = str(row.balance_sheet_age_days) if row.balance_sheet_age_days is not None else "n/a"
            lines.append(
                f"{row.rank:<5} {row.ticker:<6} "
                f"{row.market_cap_millions:>8.0f}  "
                f"{row.sotp_equity_value_millions:>8.0f}  "
                f"{row.ranked_sotp_discount:>7.2f}x  "
                f"{_short_reconciliation_label(row.reconciliation_status):<5}  "
                f"{row.sotp_tier[:7]:<7} "
                f"{age:>5}  "
                f"{row.modeled_asset_coverage_pct * 100:>4.0f}%  "
                f"{row.modeled_asset_confidence_min:>4.2f}  "
                f"{row.action_policy[:8]:<8} "
                f"{(row.notes or '')[:20]}"
            )
        summary = summarize_sotp_tiers(rows)
        lines.extend(
            [
                _REPORT_SEPARATOR,
                "SOTP Reconciliation Summary:",
                f"  Normal:                 {summary['normal']} assets",
                f"  Watch (mispricing):     {summary['watch_mispricing']} assets",
                f"  Watch (declining):      {summary['watch_declining']} assets",
                f"  Needs manual review:    {summary['needs_manual_review']} assets",
                f"  Avoid (model broken):   {summary['avoid']} assets",
                _REPORT_SEPARATOR,
                "  DiscAdj = SOTP equity value / market cap after balance-sheet recency penalty",
                "  Recon = SOTP-vs-market-cap reconciliation status",
                "  Tier = trend-aware SOTP confidence ladder",
                "  BSAge = days between as-of date and dated balance-sheet snapshot",
                "  Cov% = modeled asset value / SOTP equity value",
                "  Conf = minimum modeled-asset bucket confidence",
                "  Balance sheet source fields show dated replay/SEC provenance when available",
            ]
        )
        return "\n".join(lines)


def _short_reconciliation_label(status: str) -> str:
    labels = {
        "extreme_premium": "xprem",
        "premium": "prem",
        "discounted": "disc",
        "extreme_discount": "xdisc",
    }
    return labels.get(str(status), str(status)[:5])


def _market_trend_value(price_row: object) -> Optional[float]:
    market_cap = getattr(price_row, "market_cap_millions", None)
    if market_cap is not None and float(market_cap) > 0:
        return float(market_cap)
    close = getattr(price_row, "close_usd", None)
    if close is not None and float(close) > 0:
        return float(close)
    return None


def compute_mcap_trend_3m(
    ticker: str,
    snapshot_date: date,
    knowledge_store: KnowledgeStore,
) -> Optional[float]:
    """Compute 3-month market-cap trend using dated market-price history."""
    lookback_date = snapshot_date - timedelta(days=90)
    current_price = knowledge_store.get_price_on_or_before(ticker, snapshot_date)
    past_price = knowledge_store.get_price_on_or_before(ticker, lookback_date)
    if current_price is None or past_price is None:
        return None
    current_value = _market_trend_value(current_price)
    past_value = _market_trend_value(past_price)
    if current_value is None or past_value is None or past_value <= 0:
        return None
    return round((current_value / past_value - 1.0) * 100.0, 6)


def classify_sotp_tier(
    ratio: float,
    mcap_trend_3m: Optional[float],
    weighted_confidence: float,
) -> SotpTierResult:
    _ = float(weighted_confidence)
    if ratio > 15.0:
        return SotpTierResult(
            tier="avoid",
            action="exclude",
            reason=f"extreme_ratio:{ratio:.1f}x",
            confidence_tier="very_low",
        )
    if ratio > 8.0:
        return SotpTierResult(
            tier="needs_manual_review",
            action="flag",
            reason=f"high_ratio:{ratio:.1f}x",
            confidence_tier="low",
        )
    if ratio > 5.0:
        if mcap_trend_3m is not None and mcap_trend_3m < -30.0:
            return SotpTierResult(
                tier="needs_manual_review",
                action="flag",
                reason=f"crashing_mcap:{mcap_trend_3m:.0f}%",
                confidence_tier="low",
            )
        if mcap_trend_3m is None or mcap_trend_3m > -10.0:
            return SotpTierResult(
                tier="watch",
                action="surface",
                reason=f"possible_mispricing:{ratio:.1f}x",
                confidence_tier="medium_flagged",
            )
        return SotpTierResult(
            tier="watch",
            action="surface",
            reason=f"declining_mcap:{mcap_trend_3m:.0f}%",
            confidence_tier="medium_flagged",
        )
    return SotpTierResult(
        tier="normal",
        action="surface",
        reason="within_range",
        confidence_tier="high",
    )


def summarize_sotp_tiers(rows: list[CompanySOTPResult]) -> Counter[str]:
    counts: Counter[str] = Counter(
        {
            "normal": 0,
            "watch_mispricing": 0,
            "watch_declining": 0,
            "needs_manual_review": 0,
            "avoid": 0,
        }
    )
    for row in rows:
        tier = str(getattr(row, "sotp_tier", "normal"))
        reason = str(getattr(row, "sotp_tier_reason", "within_range"))
        if tier == "watch":
            if reason.startswith("possible_mispricing"):
                counts["watch_mispricing"] += 1
            else:
                counts["watch_declining"] += 1
        elif tier in counts:
            counts[tier] += 1
        else:
            counts["normal"] += 1
    return counts


def _resolve_watchlist_path(path: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.exists():
        return candidate.resolve()
    repo_candidate = (_REPO_ROOT / path).resolve()
    if repo_candidate.exists():
        return repo_candidate
    raise FileNotFoundError(f"Watchlist not found: {path}")


def _resolve_config_path(path: str, watchlist_path: Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    repo_candidate = (_REPO_ROOT / path).resolve()
    if repo_candidate.exists():
        return repo_candidate
    return (watchlist_path.parent / candidate).resolve()


def _group_watchlist_by_ticker(
    watchlist: list[WatchlistAsset],
) -> dict[str, list[WatchlistAsset]]:
    grouped: dict[str, list[WatchlistAsset]] = defaultdict(list)
    for asset in watchlist:
        ticker = str(asset.ticker or asset.company_id or asset.asset_id).upper()
        grouped[ticker].append(asset)
    return grouped


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def _parse_optional_date(raw: object) -> Optional[date]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def _config_valid_from(raw_cfg: dict) -> Optional[date]:
    """Return the earliest date this config's thesis is considered valid, if set."""
    if not isinstance(raw_cfg, dict):
        return None
    meta = raw_cfg.get("_meta", {})
    if not isinstance(meta, dict):
        return None
    val = meta.get("config_valid_from")
    if val is None:
        return None
    try:
        return date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None


def _infer_config_quality(raw_cfg: dict, config_path: Path) -> Optional[str]:
    meta = raw_cfg.get("_meta", {}) if isinstance(raw_cfg, dict) else {}
    if isinstance(meta, dict):
        explicit = meta.get("config_quality") or meta.get("quality_tier")
        if explicit is not None:
            return str(explicit)
        source = meta.get("config_version")
        if source is not None and "auto" in str(source).lower():
            return "auto_generated"

    path_text = str(config_path).lower()
    if "replay_generated" in path_text or "auto_generated" in path_text:
        return "screening_grade"
    if "examples/configs" in path_text:
        return "curated"
    return None


def _split_source_refs(raw: Optional[str]) -> set[str]:
    if raw is None:
        return set()
    refs: set[str] = set()
    for part in str(raw).replace(";", "|").replace(",", "|").split("|"):
        token = part.strip()
        if token:
            refs.add(token)
    return refs


def _normalize_structured_source_kind(raw_kind: str, source: str) -> Literal[
    "sec_filing",
    "contractual",
    "company_disclosure",
    "investor_day",
    "analyst_bridge",
    "inferred",
]:
    kind = str(raw_kind).strip().lower()
    source_text = str(source).strip().lower()
    if kind == "manual":
        if any(token in source_text for token in ("edgar", "sec", "10-k", "10-q")):
            return "sec_filing"
        if any(token in source_text for token in ("contract", "royalty_agreement", "milestone")):
            return "contractual"
        if "investor_day" in source_text:
            return "investor_day"
        if any(token in source_text for token in ("company_disclosure", "earnings", "investor_relations")):
            return "company_disclosure"
        return "analyst_bridge"
    if kind not in _STRUCTURED_SOURCE_CONFIDENCE_FLOORS:
        return "analyst_bridge"
    return kind


def _bucket_confidence_from_quality(config_quality: object) -> float:
    if config_quality is None:
        return 0.55
    key = str(config_quality).strip().lower()
    return _CONFIG_QUALITY_CONFIDENCE.get(key, 0.55)


def _prefer_higher_confidence_quality(*qualities: object) -> Optional[str]:
    best_quality: Optional[str] = None
    best_confidence = -1.0
    for quality in qualities:
        if quality is None:
            continue
        candidate = str(quality).strip()
        if not candidate:
            continue
        confidence = _bucket_confidence_from_quality(candidate)
        if confidence > best_confidence:
            best_quality = candidate
            best_confidence = confidence
    return best_quality


def _summarize_config_qualities(values: list[Optional[str]]) -> Optional[str]:
    unique = sorted({value for value in values if value})
    if not unique:
        return None
    return "|".join(unique)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a company-level SOTP screen")
    parser.add_argument("--watchlist", required=True, help="Watchlist YAML path")
    parser.add_argument(
        "--price-source",
        choices=["replay_store", "yfinance"],
        default="replay_store",
    )
    parser.add_argument("--as-of", default=None, help="Optional YYYY-MM-DD snapshot date")
    parser.add_argument("--knowledge-db", default=None, help="Optional KnowledgeStore path")
    parser.add_argument("--replay-db", default=None, help="Optional ReplayStore path")
    parser.add_argument(
        "--overrides",
        default="research/company_sotp_overrides.yaml",
        help="Optional company SOTP override YAML",
    )
    parser.add_argument(
        "--persist-company-snapshots",
        action="store_true",
        help="Persist company-level SOTP rows into KnowledgeStore company_sotp_snapshots",
    )
    parser.add_argument(
        "--recompute",
        action="store_true",
        help="Recompute company SOTP instead of loading stored company_sotp_snapshots on or before --as-of",
    )
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a report")
    args = parser.parse_args()

    builder = CompanySOTPBuilder(
        as_of_date=_parse_date(args.as_of) if args.as_of else None,
        knowledge_db_path=args.knowledge_db,
        replay_store_path=args.replay_db,
        overrides_path=args.overrides,
        persist_company_snapshots=args.persist_company_snapshots,
    )
    reference_snapshot_date: Optional[date] = None
    source_mode = "live_recomputed"
    if not args.recompute:
        reference_snapshot_date, rows = builder.load_from_store(args.watchlist)
        if rows:
            source_mode = "stored_company_snapshot"
        else:
            rows = builder.build(args.watchlist, price_source=args.price_source)
            reference_snapshot_date = builder.as_of_date
    else:
        rows = builder.build(args.watchlist, price_source=args.price_source)
        reference_snapshot_date = builder.as_of_date
    top_rows = rows[: max(args.top, 0)]
    if args.json:
        import json

        print(json.dumps([row.model_dump(mode="json") for row in top_rows], indent=2))
        return
    print(
        CompanySOTPBuilder.render_report(
            top_rows,
            watchlist_path=args.watchlist,
            source_mode=source_mode,
            reference_snapshot_date=reference_snapshot_date,
        )
    )
    if builder.last_csv_path is not None:
        print(f"\nCSV -> {builder.last_csv_path}")


if __name__ == "__main__":
    main()
