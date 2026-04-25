"""Strict point-in-time historical backtest workflow.

Runs a reproducible train/validation/test evaluation over the replay stores
using only dated historical artifacts. The workflow intentionally avoids live
API reads and uses replay-store prices for return calculations.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from bve.analysis.alpha_validation import AlphaValidationReport, AlphaValidator
from bve.analysis.mna_probability_scanner import _evaluate
from bve.analysis.portfolio_backtest import (
    PortfolioBacktestConfig,
    PortfolioBacktester,
)
from bve.intelligence.knowledge_layer import AssetRegistryEntry, BacktestSnapshot, KnowledgeStore
from bve.intelligence.ma_calibration import (
    MACalibrationDataset,
    MACalibrationDatasetBuilder,
    MACalibrationRow,
)
from bve.learning.calibration import ProbabilityCalibrator, fit_platt_calibrator
from bve.ops.company_sotp_backfiller import CompanySOTPBackfiller
from bve.ops.deal_event_backfiller import DealEventBackfiller
from bve.ops.historical_replay import (
    REPLAY_KNOWLEDGE_PATH,
    REPLAY_STORE_PATH,
    HistoricalReplay,
    ReplayStore,
    load_replay_universe,
)
from bve.ops.ma_probability_backfiller import backfill_ma_probability_snapshots
from bve.ops.price_backfiller import PriceBackfiller
from bve.ops.replay_universe_builder import DEFAULT_OUTPUT_PATH, ReplayUniverseBuilder
from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller
from bve.ops.trial_event_backfiller import TrialEventBackfiller

DEFAULT_WATCHLIST = "examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml"
DEFAULT_OUTPUT_DIR = Path("outputs/analysis")


@dataclass(frozen=True)
class DateSplit:
    name: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class StepStatus:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class SplitReport:
    split: str
    start_date: date
    end_date: date
    replay_run_id: str
    portfolio_backtest_baseline: dict[str, Any]
    replay_summary: dict[str, Any]
    portfolio_backtest: dict[str, Any]
    alpha_validation: dict[str, Any]
    mna_validation: dict[str, Any]
    mna_validation_baseline: dict[str, Any]


@dataclass(frozen=True)
class StrictBacktestReport:
    generated_at: datetime
    universe_file: str
    watchlist_path: str
    replay_db_path: str
    replay_knowledge_path: str
    price_source: str
    split_scheme: str
    holdout_split: str
    tuning_scope: str
    holdout_untouched_during_tuning: bool
    steps: list[StepStatus]
    splits: list[SplitReport]
    train_metrics: dict[str, Any]
    validation_metrics: dict[str, Any]
    holdout_metrics: dict[str, Any]
    tuning_summary: dict[str, Any]
    robustness_report: dict[str, Any]
    final_test_metrics: dict[str, Any]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_created_at(snapshot_date: date) -> datetime:
    return datetime.combine(snapshot_date, time(12, 0), tzinfo=timezone.utc)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _company_sotp_score(row: dict[str, Any]) -> float:
    action_base = {
        "buy": 0.85,
        "watch": 0.65,
        "needs_manual_review": 0.40,
        "avoid": 0.20,
    }.get(str(row.get("action_policy") or "avoid"), 0.20)
    raw_discount = row.get("ranked_sotp_discount")
    try:
        discount = float(raw_discount) if raw_discount is not None else 0.0
    except (TypeError, ValueError):
        discount = 0.0
    # Compress the long-tailed SOTP discount into a stable 0-1 feature.
    discount_component = min(math.log1p(max(discount, 0.0)) / math.log1p(10.0), 1.0)
    return round(_clamp((0.7 * action_base) + (0.3 * discount_component)), 6)


def _build_local_price_series_fetcher(replay_db_path: str) -> Callable[[str, date, date], dict[date, float]]:
    def _fetch(ticker: str, start_date: date, end_date: date) -> dict[date, float]:
        store = ReplayStore(replay_db_path)
        try:
            rows = store._conn.execute(
                """
                SELECT price_date, close_usd
                FROM historical_prices
                WHERE ticker = ? AND price_date >= ? AND price_date <= ?
                ORDER BY price_date ASC
                """,
                (ticker.upper(), start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        finally:
            store.close()
        return {
            date.fromisoformat(str(row["price_date"])[:10]): float(row["close_usd"])
            for row in rows
        }

    return _fetch


def _build_local_price_return_fetcher(replay_db_path: str) -> Callable[[str, date, date], Optional[float]]:
    def _fetch(ticker: str, start_date: date, end_date: date) -> Optional[float]:
        store = ReplayStore(replay_db_path)
        try:
            result = store.get_return(ticker.upper(), start_date, end_date)
        finally:
            store.close()
        if result is None:
            return None
        return result / 100.0

    return _fetch


def _build_date_splits(snapshot_dates: list[date]) -> list[DateSplit]:
    ordered = sorted(snapshot_dates)
    if len(ordered) < 9:
        raise ValueError("Need at least 9 dated snapshots to build train/validation/test splits")
    n_dates = len(ordered)
    train_end_idx = max(2, int(n_dates * 0.6) - 1)
    validation_end_idx = max(train_end_idx + 2, int(n_dates * 0.8) - 1)
    validation_end_idx = min(validation_end_idx, n_dates - 2)
    return [
        DateSplit("train", ordered[0], ordered[train_end_idx]),
        DateSplit("validation", ordered[train_end_idx + 1], ordered[validation_end_idx]),
        DateSplit("holdout", ordered[validation_end_idx + 1], ordered[-1]),
    ]


def _public_metric_bundle(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "hit_rate": result.get("win_rate"),
        "avg_return_by_tier": result.get("avg_return_by_tier"),
        "sharpe": result.get("sharpe_ratio"),
        "max_drawdown": result.get("max_drawdown"),
        "brier_score": result.get("brier_score"),
        "calibration_error": result.get("calibration_error"),
    }


def _mna_metric_bundle(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "precision_at_k": result.get("precision_at_k"),
        "top1_accuracy": result.get("acquirer_top1_accuracy"),
        "top3_accuracy": result.get("acquirer_top3_accuracy"),
        "top5_accuracy": result.get("acquirer_top5_accuracy"),
        "mrr": result.get("acquirer_mrr"),
        "median_lead_days": result.get("median_lead_days_at_k"),
        "false_positive_rate": result.get("false_positive_rate_at_k"),
    }


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _portfolio_objective(result: dict[str, Any]) -> float:
    """Conservative objective that heavily penalises drawdown.

    Drawdown is weighted at 2x Sharpe so that a policy must offer a material
    Sharpe improvement to compensate for any drawdown increase.  Calibration
    error receives a small penalty to break ties.
    """
    sharpe = _safe_float(result.get("sharpe_ratio")) or 0.0
    max_drawdown = _safe_float(result.get("max_drawdown")) or 0.0
    calibration_error = _safe_float(result.get("calibration_error")) or 0.0
    return round(sharpe - (2.0 * max_drawdown) - (0.25 * calibration_error), 6)


def _drawdown_improved_enough(
    candidate_result: dict[str, Any],
    baseline_result: dict[str, Any],
    *,
    min_improvement: float = 0.02,
) -> bool:
    """Return True if candidate drawdown is at least min_improvement lower than baseline."""
    candidate_dd = _safe_float(candidate_result.get("max_drawdown")) or 0.0
    baseline_dd = _safe_float(baseline_result.get("max_drawdown")) or 0.0
    return (baseline_dd - candidate_dd) >= min_improvement


def _mna_objective(result: dict[str, Any]) -> float:
    precision = _safe_float(result.get("precision_at_k")) or 0.0
    top3 = _safe_float(result.get("acquirer_top3_accuracy")) or 0.0
    top5 = _safe_float(result.get("acquirer_top5_accuracy")) or 0.0
    mrr = _safe_float(result.get("acquirer_mrr")) or 0.0
    false_positive = _safe_float(result.get("false_positive_rate_at_k")) or 0.0
    return round(
        (0.45 * precision)
        + (0.20 * top3)
        + (0.15 * top5)
        + (0.20 * mrr)
        - (0.20 * false_positive),
        6,
    )


def _choose_calibrator(
    train_pairs: list[tuple[float, float]],
    validation_pairs: list[tuple[float, float]],
) -> tuple[ProbabilityCalibrator, dict[str, Any]]:
    candidates = {
        "identity": ProbabilityCalibrator(method="identity"),
        "platt": fit_platt_calibrator(train_pairs),
    }
    scored: dict[str, dict[str, float]] = {}
    best_name = "identity"
    best_score = float("inf")
    for name, calibrator in candidates.items():
        transformed = calibrator.transform_pairs(validation_pairs)
        brier = sum((pred - actual) ** 2 for pred, actual in transformed) / max(len(transformed), 1)
        ece = PortfolioBacktester._expected_calibration_error(transformed)
        score = (0.7 * brier) + (0.3 * ece)
        scored[name] = {
            "brier_score": round(brier, 6),
            "calibration_error": round(ece, 6),
        }
        if score < best_score:
            best_name = name
            best_score = score
    return candidates[best_name], {
        "selected_method": best_name,
        "candidates": scored,
        "train_pairs": len(train_pairs),
        "validation_pairs": len(validation_pairs),
    }


def _build_public_pairs(position_log: list[dict[str, Any]]) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for row in position_log:
        predicted = _safe_float(row.get("composite_score"))
        actual_return = _safe_float(row.get("net_return"))
        if predicted is None or actual_return is None:
            continue
        pairs.append((max(0.0, min(1.0, predicted)), 1.0 if actual_return > 0 else 0.0))
    return pairs


def _build_mna_pairs(rows: list[dict[str, Any]]) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for row in rows:
        predicted = _safe_float(row.get("probability"))
        label = _safe_float(row.get("label"))
        if predicted is None or label is None:
            continue
        pairs.append((max(0.0, min(1.0, predicted)), 1.0 if label >= 0.5 else 0.0))
    return pairs


def _build_financing_risk_lookup(
    knowledge_db_path: str,
) -> Callable[[BacktestSnapshot], dict[str, Any]]:
    store = KnowledgeStore(knowledge_db_path)
    rows = store._conn.execute(
        """
        SELECT ticker, snapshot_date, capital_vulnerability_score, therapeutic_area
        FROM ma_probability_snapshots
        ORDER BY ticker ASC, snapshot_date ASC
        """
    ).fetchall()
    store.close()
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticker = str(row["ticker"] or "").upper()
        if not ticker:
            continue
        by_ticker.setdefault(ticker, []).append(dict(row))

    def _fetch(snapshot: BacktestSnapshot) -> dict[str, Any]:
        ticker = str(snapshot.asset_id.split("::")[-1]).upper()
        matches = by_ticker.get(ticker, [])
        latest: dict[str, Any] | None = None
        for item in matches:
            snapshot_date = date.fromisoformat(str(item["snapshot_date"]))
            if snapshot_date <= snapshot.signal_date:
                latest = item
        return {
            "therapeutic_area": latest.get("therapeutic_area") if latest else None,
            "modality": None,
            "catalyst_bucket": snapshot.catalyst_type,
            "financing_risk_score": (
                float(latest["capital_vulnerability_score"])
                if latest and latest.get("capital_vulnerability_score") is not None
                else None
            ),
            "confidence": snapshot.extraction_confidence,
        }

    return _fetch


def _subset_metric_summary(*, context_rows: dict[str, Any]) -> dict[str, Any]:
    return {
        "precision_at_k": context_rows.get("precision_at_k"),
        "top3_accuracy": context_rows.get("acquirer_top3_accuracy"),
        "top5_accuracy": context_rows.get("acquirer_top5_accuracy"),
    }


def materialize_backtest_snapshots_from_company_sotp(
    *,
    knowledge_db_path: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    universe_rows: Optional[list[dict[str, Any]]] = None,
) -> int:
    store = KnowledgeStore(knowledge_db_path)
    try:
        metadata_by_ticker: dict[str, dict[str, Any]] = {}
        for raw in universe_rows or []:
            ticker = str(raw.get("ticker") or "").upper()
            if ticker and ticker not in metadata_by_ticker:
                metadata_by_ticker[ticker] = raw
        snapshot_dates = store.list_company_sotp_snapshot_dates()
        if start_date is not None:
            snapshot_dates = [item for item in snapshot_dates if item >= start_date]
        if end_date is not None:
            snapshot_dates = [item for item in snapshot_dates if item <= end_date]
        written = 0
        for snapshot_date in sorted(snapshot_dates):
            rows = store.get_company_sotp_snapshots(snapshot_date=snapshot_date, limit=10_000)
            for row in rows:
                ticker = str(row.get("ticker") or "").upper()
                if not ticker:
                    continue
                asset_id = f"sotp::{ticker}"
                store.upsert_asset_registry_entry(
                    AssetRegistryEntry(
                        asset_id=asset_id,
                        ticker=ticker,
                        company_id=row.get("company_id"),
                        therapeutic_area=metadata_by_ticker.get(ticker, {}).get("therapeutic_area"),
                        modality=metadata_by_ticker.get(ticker, {}).get("modality"),
                        stage=metadata_by_ticker.get(ticker, {}).get("stage"),
                        source="strict_backtest_company_sotp_bridge",
                    )
                )
                created_at = _snapshot_created_at(snapshot_date)
                store.write_backtest_snapshot(
                    BacktestSnapshot(
                        snapshot_id=f"strict-sotp:{ticker}:{snapshot_date.isoformat()}",
                        alert_id=f"strict-sotp:{ticker}:{snapshot_date.isoformat()}",
                        asset_id=asset_id,
                        signal_date=snapshot_date,
                        signal_timestamp=created_at,
                        composite_score=_company_sotp_score(row),
                        extraction_confidence=(
                            float(row["modeled_asset_confidence_avg"])
                            if row.get("modeled_asset_confidence_avg") is not None
                            else None
                        ),
                        intrinsic_value_millions=(
                            float(row["sotp_equity_value_millions"])
                            if row.get("sotp_equity_value_millions") is not None
                            else None
                        ),
                        mispricing_score=(
                            float(row["ranked_sotp_discount"])
                            if row.get("ranked_sotp_discount") is not None
                            else None
                        ),
                        catalyst_type="company_sotp",
                        rank_at_signal=(
                            int(row["rank"]) if row.get("rank") is not None else None
                        ),
                        model_version="strict_backtest_company_sotp_bridge_v1",
                        created_at=created_at,
                    )
                )
                written += 1
        return written
    finally:
        store.close()


class StrictBacktestWorkflow:
    def __init__(
        self,
        *,
        universe_file: str = str(DEFAULT_OUTPUT_PATH),
        watchlist_path: str = DEFAULT_WATCHLIST,
        replay_db_path: str = str(REPLAY_STORE_PATH),
        replay_knowledge_path: str = str(REPLAY_KNOWLEDGE_PATH),
        output_dir: str | Path = DEFAULT_OUTPUT_DIR,
        top_k: int = 10,
        refresh_remote_backfills: bool = False,
        refresh_local_seeds: bool = True,
    ) -> None:
        self.universe_file = universe_file
        self.watchlist_path = watchlist_path
        self.replay_db_path = replay_db_path
        self.replay_knowledge_path = replay_knowledge_path
        self.output_dir = Path(output_dir)
        self.top_k = top_k
        self.refresh_remote_backfills = refresh_remote_backfills
        self.refresh_local_seeds = refresh_local_seeds

    def run(self) -> StrictBacktestReport:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        steps: list[StepStatus] = []

        universe_result = ReplayUniverseBuilder().build()
        ReplayUniverseBuilder.write(self.universe_file, universe_result)
        steps.append(
            StepStatus(
                name="build_replay_universe",
                status="completed",
                detail=f"{len(universe_result.universe)} names -> {self.universe_file}",
            )
        )

        if self.refresh_remote_backfills:
            price_summary = PriceBackfiller(replay_db_path=self.replay_db_path, reporter=None).backfill(
                self.universe_file,
                start_date=universe_result.recommended_backfill_start,
                end_date=universe_result.recommended_backfill_end,
            )
            steps.append(
                StepStatus(
                    name="price_backfill",
                    status="completed",
                    detail=f"{price_summary.tickers_backfilled} tickers backfilled",
                )
            )
        else:
            steps.append(
                StepStatus(
                    name="price_backfill",
                    status="reused",
                    detail="using existing replay_store historical_prices only",
                )
            )

        if self.refresh_local_seeds:
            deal_summary = DealEventBackfiller(replay_db_path=self.replay_db_path).backfill(
                universe_file=self.universe_file,
            )
            TrialEventBackfiller(replay_db_path=self.replay_db_path).backfill(dry_run=False)
            ThesisClaimsBackfiller(self.replay_knowledge_path).seed()
            sotp_summary = CompanySOTPBackfiller(
                knowledge_db_path=self.replay_knowledge_path,
                replay_db_path=self.replay_db_path,
                output_dir=self.output_dir,
                reporter=None,
            ).backfill_watchlist(self.watchlist_path)
            ma_summary = backfill_ma_probability_snapshots(
                watchlist_path=self.watchlist_path,
                knowledge_db_path=self.replay_knowledge_path,
                output_dir=self.output_dir,
                dataset_mode="historical_snapshot",
                top_k=self.top_k,
            )
            steps.extend(
                [
                    StepStatus(
                        name="deal_event_backfill",
                        status="completed",
                        detail=f"{deal_summary.inserted_events} acquisition events present",
                    ),
                    StepStatus(
                        name="seed_replay_events",
                        status="completed",
                        detail="trial replay events seeded from local YAML",
                    ),
                    StepStatus(
                        name="seed_replay_claims",
                        status="completed",
                        detail="historical thesis claims seeded from local YAML",
                    ),
                    StepStatus(
                        name="company_sotp_backfill",
                        status="completed",
                        detail=f"{sotp_summary.n_snapshot_dates} dated SOTP snapshots refreshed",
                    ),
                    StepStatus(
                        name="ma_probability_backfill",
                        status="completed",
                        detail=f"{ma_summary.snapshot_dates} dated M&A snapshot dates refreshed",
                    ),
                ]
            )
        else:
            steps.extend(
                [
                    StepStatus("deal_event_backfill", "reused", "using existing local replay events"),
                    StepStatus("seed_replay_events", "reused", "using existing trial events"),
                    StepStatus("seed_replay_claims", "reused", "using existing thesis claims"),
                    StepStatus(
                        "company_sotp_backfill",
                        "reused",
                        "using existing company_sotp_snapshots from replay knowledge DB",
                    ),
                    StepStatus(
                        "ma_probability_backfill",
                        "reused",
                        "using existing ma_probability_snapshots from replay knowledge DB",
                    ),
                ]
            )

        bridge_written = materialize_backtest_snapshots_from_company_sotp(
            knowledge_db_path=self.replay_knowledge_path,
            universe_rows=list(universe_result.universe),
        )
        steps.append(
            StepStatus(
                name="materialize_portfolio_signals",
                status="completed",
                detail=f"{bridge_written} backtest snapshots bridged from company_sotp_snapshots",
            )
        )

        knowledge_store = KnowledgeStore(self.replay_knowledge_path)
        try:
            snapshot_dates = knowledge_store.list_company_sotp_snapshot_dates()
        finally:
            knowledge_store.close()
        splits = _build_date_splits(snapshot_dates)
        steps.append(
            StepStatus(
                name="build_walk_forward_splits",
                status="completed",
                detail=", ".join(
                    f"{split.name}:{split.start_date.isoformat()}->{split.end_date.isoformat()}"
                    for split in splits
                ),
            )
        )

        universe = load_replay_universe(self.universe_file)
        replay_price_series_fetcher = _build_local_price_series_fetcher(self.replay_db_path)
        replay_price_return_fetcher = _build_local_price_return_fetcher(self.replay_db_path)
        risk_metadata_fetcher = _build_financing_risk_lookup(self.replay_knowledge_path)
        split_reports: list[SplitReport] = []
        split_context: dict[str, dict[str, Any]] = {}

        baseline_portfolio_by_split: dict[str, dict[str, Any]] = {}
        baseline_mna_by_split: dict[str, dict[str, Any]] = {}
        public_pairs_by_split: dict[str, list[tuple[float, float]]] = {}
        mna_pairs_by_split: dict[str, list[tuple[float, float]]] = {}

        for split in splits:
            replay = HistoricalReplay(
                ReplayStore(self.replay_db_path),
                self.replay_knowledge_path,
                universe=universe,
            )
            try:
                run_id = replay.run(
                    start=split.start_date,
                    end=split.end_date,
                    cadence="quarterly",
                    decision_policy=f"strict_walkforward_{split.name}",
                    profile="standard",
                )
                replay_summary = replay.summarize(run_id).to_dict()
            finally:
                replay._rs.close()

            split_store = KnowledgeStore(self.replay_knowledge_path)
            try:
                portfolio_result = PortfolioBacktester(
                    split_store,
                    PortfolioBacktestConfig(
                        start_date=split.start_date,
                        end_date=split.end_date,
                        n_holdings=self.top_k,
                        rebalance_freq_days=90,
                    ),
                    price_fetcher=replay_price_return_fetcher,
                    risk_metadata_fetcher=risk_metadata_fetcher,
                ).run()
            finally:
                split_store.close()

            alpha_report = AlphaValidator(
                replay_db_path=self.replay_db_path,
                price_fetcher=replay_price_series_fetcher,
                bootstrap_seed=42,
            ).validate(run_id, today=split.end_date)

            mna_store = KnowledgeStore(self.replay_knowledge_path)
            try:
                mna_dataset = MACalibrationDatasetBuilder(
                    knowledge_store=mna_store,
                ).build_dataset(
                    lookahead_days=365,
                    start_date=split.start_date,
                    end_date=split.end_date,
                    replay_store_path=self.replay_db_path,
                )
            finally:
                mna_store.close()
            mna_metrics = _evaluate(mna_dataset, top_k=self.top_k)
            baseline_portfolio_by_split[split.name] = portfolio_result.model_dump(mode="json")
            baseline_mna_by_split[split.name] = mna_metrics.model_dump(mode="json")
            public_pairs_by_split[split.name] = _build_public_pairs(portfolio_result.position_log)
            mna_pairs_by_split[split.name] = _build_mna_pairs(
                [row.model_dump(mode="json") for row in mna_dataset.rows]
            )
            split_context[split.name] = {
                "run_id": run_id,
                "replay_summary": replay_summary,
                "alpha_validation": _alpha_to_dict(alpha_report),
                "mna_rows": [row.model_dump(mode="json") for row in mna_dataset.rows],
            }

        public_calibrator, public_calibration_summary = _choose_calibrator(
            public_pairs_by_split.get("train", []),
            public_pairs_by_split.get("validation", []),
        )
        mna_calibrator, mna_calibration_summary = _choose_calibrator(
            mna_pairs_by_split.get("train", []),
            mna_pairs_by_split.get("validation", []),
        )

        risk_policy_grid = [
            (
                "baseline",
                PortfolioBacktestConfig(
                    n_holdings=self.top_k,
                    rebalance_freq_days=90,
                ),
            ),
            (
                "single_pos_cap",
                PortfolioBacktestConfig(
                    n_holdings=self.top_k,
                    rebalance_freq_days=90,
                    max_single_position_weight=0.15,
                ),
            ),
            (
                "catalyst_cluster_limit",
                PortfolioBacktestConfig(
                    n_holdings=self.top_k,
                    rebalance_freq_days=90,
                    max_weight_per_catalyst_bucket=0.30,
                    max_single_position_weight=0.15,
                ),
            ),
            (
                "ta_modality_caps",
                PortfolioBacktestConfig(
                    n_holdings=self.top_k,
                    rebalance_freq_days=90,
                    max_weight_per_therapeutic_area=0.25,
                    max_weight_per_modality=0.35,
                    max_single_position_weight=0.15,
                ),
            ),
            (
                "confidence_financing_caps",
                PortfolioBacktestConfig(
                    n_holdings=self.top_k,
                    rebalance_freq_days=90,
                    confidence_scaled_sizing=True,
                    financing_risk_haircut_multiplier=0.35,
                    max_weight_per_therapeutic_area=0.30,
                    min_calibrated_score=0.35,
                    max_single_position_weight=0.15,
                ),
            ),
            (
                "defensive",
                PortfolioBacktestConfig(
                    n_holdings=self.top_k,
                    rebalance_freq_days=90,
                    confidence_scaled_sizing=True,
                    financing_risk_haircut_multiplier=0.50,
                    max_weight_per_therapeutic_area=0.25,
                    min_calibrated_score=0.40,
                    max_single_position_weight=0.12,
                ),
            ),
            (
                "combined_drawdown_focus",
                PortfolioBacktestConfig(
                    n_holdings=self.top_k,
                    rebalance_freq_days=90,
                    confidence_scaled_sizing=True,
                    financing_risk_haircut_multiplier=0.40,
                    max_weight_per_therapeutic_area=0.25,
                    max_weight_per_modality=0.35,
                    max_weight_per_catalyst_bucket=0.30,
                    min_calibrated_score=0.35,
                    max_single_position_weight=0.12,
                ),
            ),
        ]
        validation_candidates: list[dict[str, Any]] = []
        baseline_validation_metrics: dict[str, Any] = {}
        for policy_name, template in risk_policy_grid:
            validation_store = KnowledgeStore(self.replay_knowledge_path)
            try:
                validation_result = PortfolioBacktester(
                    validation_store,
                    template.model_copy(
                        update={
                            "start_date": next(s.start_date for s in splits if s.name == "validation"),
                            "end_date": next(s.end_date for s in splits if s.name == "validation"),
                        }
                    ),
                    price_fetcher=replay_price_return_fetcher,
                    probability_calibrator=public_calibrator.predict,
                    risk_metadata_fetcher=risk_metadata_fetcher,
                ).run()
            finally:
                validation_store.close()
            metrics_dict = validation_result.model_dump(mode="json")
            validation_candidates.append(
                {
                    "policy_name": policy_name,
                    "objective": _portfolio_objective(metrics_dict),
                    "metrics": metrics_dict,
                }
            )
            if policy_name == "baseline":
                baseline_validation_metrics = metrics_dict

        # Conservative selection: a non-baseline policy is only preferred if it reduces
        # drawdown by at least 2pp on validation.  If no policy achieves this, keep baseline.
        non_baseline = [
            item for item in validation_candidates if item["policy_name"] != "baseline"
        ]
        drawdown_improving = [
            item for item in non_baseline
            if _drawdown_improved_enough(item["metrics"], baseline_validation_metrics)
        ]
        if drawdown_improving:
            best_validation_policy = max(drawdown_improving, key=lambda item: item["objective"])
        else:
            best_validation_policy = next(
                item for item in validation_candidates if item["policy_name"] == "baseline"
            )
        selected_policy_name = str(best_validation_policy["policy_name"])
        selected_policy = next(
            template for policy_name, template in risk_policy_grid if policy_name == selected_policy_name
        )

        for split in splits:
            context = split_context[split.name]
            split_store = KnowledgeStore(self.replay_knowledge_path)
            try:
                tuned_portfolio = PortfolioBacktester(
                    split_store,
                    selected_policy.model_copy(
                        update={
                            "start_date": split.start_date,
                            "end_date": split.end_date,
                        }
                    ),
                    price_fetcher=replay_price_return_fetcher,
                    probability_calibrator=public_calibrator.predict,
                    risk_metadata_fetcher=risk_metadata_fetcher,
                ).run()
            finally:
                split_store.close()

            tuned_mna_rows: list[dict[str, Any]] = []
            for row in context["mna_rows"]:
                tuned = dict(row)
                probability = _safe_float(tuned.get("probability"))
                if probability is not None:
                    tuned["probability"] = round(mna_calibrator.predict(probability), 6)
                tuned_mna_rows.append(tuned)
            tuned_mna_dataset = MACalibrationDataset(
                start_date=split.start_date,
                end_date=split.end_date,
                lookahead_days=365,
                n_rows=len(tuned_mna_rows),
                n_positive_rows=sum(1 for row in tuned_mna_rows if int(row.get("label", 0)) == 1),
                n_control_rows=sum(1 for row in tuned_mna_rows if int(row.get("label", 0)) == 0),
                n_unique_targets=len({str(row.get("ticker")) for row in tuned_mna_rows}),
                dataset_mode="historical_snapshot",
                rows=[MACalibrationRow.model_validate(row) for row in tuned_mna_rows],
            )
            tuned_mna_metrics = _evaluate(tuned_mna_dataset, top_k=self.top_k)

            split_reports.append(
                SplitReport(
                    split=split.name,
                    start_date=split.start_date,
                    end_date=split.end_date,
                    replay_run_id=str(context["run_id"]),
                    replay_summary=dict(context["replay_summary"]),
                    portfolio_backtest_baseline=dict(baseline_portfolio_by_split[split.name]),
                    portfolio_backtest=tuned_portfolio.model_dump(mode="json"),
                    alpha_validation=dict(context["alpha_validation"]),
                    mna_validation=tuned_mna_metrics.model_dump(mode="json"),
                    mna_validation_baseline=dict(baseline_mna_by_split[split.name]),
                )
            )

        train_split = next(item for item in split_reports if item.split == "train")
        validation_split = next(item for item in split_reports if item.split == "validation")
        holdout_split = next(item for item in split_reports if item.split == "holdout")
        robustness_report = {
            "walk_forward_public_objectives": {
                item.split: _portfolio_objective(item.portfolio_backtest)
                for item in split_reports
            },
            "walk_forward_drawdown": {
                item.split: item.portfolio_backtest.get("max_drawdown")
                for item in split_reports
            },
            "walk_forward_sharpe": {
                item.split: item.portfolio_backtest.get("sharpe_ratio")
                for item in split_reports
            },
            "threshold_sensitivity_validation": {
                item["policy_name"]: {
                    "objective": item["objective"],
                    "max_drawdown": item["metrics"].get("max_drawdown"),
                    "sharpe_ratio": item["metrics"].get("sharpe_ratio"),
                }
                for item in validation_candidates
            },
            "drawdown_improving_policies": [
                item["policy_name"] for item in drawdown_improving
            ],
            "subset_checks_validation": {
                "mna_by_stage": _subset_metric_summary(context_rows=validation_split.mna_validation),
                "mna_acquisition_likelihood": validation_split.mna_validation.get(
                    "acquisition_likelihood_precision"
                ),
                "mna_conditional_acquirer_mrr": validation_split.mna_validation.get(
                    "acquirer_mrr"
                ),
            },
            "stability": {
                "selected_policy": selected_policy_name,
                "validation_drawdown_improved": (
                    _safe_float(validation_split.portfolio_backtest.get("max_drawdown"))
                    or 0.0
                )
                <= (
                    _safe_float(validation_split.portfolio_backtest_baseline.get("max_drawdown"))
                    or 0.0
                ),
                "validation_sharpe_improved": (
                    _safe_float(validation_split.portfolio_backtest.get("sharpe_ratio"))
                    or 0.0
                )
                >= (
                    _safe_float(validation_split.portfolio_backtest_baseline.get("sharpe_ratio"))
                    or 0.0
                ),
                "policy_consistency_across_splits": {
                    item.split: _portfolio_objective(item.portfolio_backtest)
                    > _portfolio_objective(item.portfolio_backtest_baseline)
                    for item in split_reports
                },
            },
        }
        final_metrics = {
            "public_markets": {
                "hit_rate": holdout_split.portfolio_backtest["win_rate"],
                "avg_return_by_signal_tier": holdout_split.portfolio_backtest["avg_return_by_tier"],
                "sharpe": holdout_split.portfolio_backtest["sharpe_ratio"],
                "max_drawdown": holdout_split.portfolio_backtest["max_drawdown"],
                "brier_score": holdout_split.portfolio_backtest["brier_score"],
                "calibration_error": holdout_split.portfolio_backtest["calibration_error"],
                "alpha_survives_corrections": holdout_split.alpha_validation["alpha_survives_corrections"],
            },
            "mna": {
                "precision_at_k": holdout_split.mna_validation["precision_at_k"],
                "acquirer_top1_accuracy": holdout_split.mna_validation["acquirer_top1_accuracy"],
                "acquirer_top3_accuracy": holdout_split.mna_validation["acquirer_top3_accuracy"],
                "acquirer_top5_accuracy": holdout_split.mna_validation["acquirer_top5_accuracy"],
                "acquirer_mrr": holdout_split.mna_validation["acquirer_mrr"],
                "median_lead_days": holdout_split.mna_validation["median_lead_days_at_k"],
                "false_positive_rate": holdout_split.mna_validation["false_positive_rate_at_k"],
            },
        }
        return StrictBacktestReport(
            generated_at=_utcnow(),
            universe_file=self.universe_file,
            watchlist_path=self.watchlist_path,
            replay_db_path=self.replay_db_path,
            replay_knowledge_path=self.replay_knowledge_path,
            price_source="replay_store.historical_prices_only",
            split_scheme="60/20/20 dated train/validation/holdout",
            holdout_split="holdout",
            tuning_scope="train+validation_only",
            holdout_untouched_during_tuning=True,
            steps=steps,
            splits=split_reports,
            train_metrics={
                "public_markets": _public_metric_bundle(train_split.portfolio_backtest),
                "mna": _mna_metric_bundle(train_split.mna_validation),
            },
            validation_metrics={
                "public_markets": _public_metric_bundle(validation_split.portfolio_backtest),
                "mna": _mna_metric_bundle(validation_split.mna_validation),
                "baseline_public_markets": _public_metric_bundle(validation_split.portfolio_backtest_baseline),
                "baseline_mna": _mna_metric_bundle(validation_split.mna_validation_baseline),
            },
            holdout_metrics={
                "public_markets": _public_metric_bundle(holdout_split.portfolio_backtest),
                "mna": _mna_metric_bundle(holdout_split.mna_validation),
                "baseline_public_markets": _public_metric_bundle(holdout_split.portfolio_backtest_baseline),
                "baseline_mna": _mna_metric_bundle(holdout_split.mna_validation_baseline),
            },
            tuning_summary={
                "public_probability_calibration": public_calibration_summary,
                "mna_probability_calibration": mna_calibration_summary,
                "selected_risk_policy": selected_policy_name,
                "validation_risk_policy_candidates": validation_candidates,
            },
            robustness_report=robustness_report,
            final_test_metrics=final_metrics,
        )


def _alpha_to_dict(report: AlphaValidationReport) -> dict[str, Any]:
    return {
        "run_id": report.run_id,
        "start_date": report.start_date.isoformat(),
        "end_date": report.end_date.isoformat(),
        "benchmark_ticker": report.benchmark_ticker,
        "hold_days": report.hold_days,
        "n_trades": report.stats.n_trades,
        "mean_excess_return": report.stats.mean_excess_return,
        "hit_rate": report.stats.hit_rate,
        "overlap_p_value": report.overlap.p_value,
        "cluster_p_value": report.clusters.p_value,
        "bootstrap_p_value": report.bootstrap.p_value,
        "alpha_survives_corrections": report.alpha_survives_corrections,
        "csv_path": str(report.csv_path) if report.csv_path is not None else None,
    }


def render_report(report: StrictBacktestReport) -> str:
    final_public = report.holdout_metrics["public_markets"]
    final_mna = report.holdout_metrics["mna"]
    lines = [
        "Strict Point-in-Time Backtest",
        f"  Generated at: {report.generated_at.isoformat()}",
        f"  Universe: {report.universe_file}",
        f"  Replay DB: {report.replay_db_path}",
        f"  Replay KB: {report.replay_knowledge_path}",
        f"  Price source: {report.price_source}",
        f"  Split scheme: {report.split_scheme}",
        f"  Holdout split: {report.holdout_split}",
        f"  Tuning scope: {report.tuning_scope}",
        f"  Holdout untouched during tuning: {report.holdout_untouched_during_tuning}",
        "",
        "Steps",
    ]
    for step in report.steps:
        lines.append(f"  - {step.name}: {step.status} ({step.detail})")
    lines.extend(
        [
            "",
            "Tuning",
            f"  Public calibrator: {report.tuning_summary['public_probability_calibration']['selected_method']}",
            f"  M&A calibrator: {report.tuning_summary['mna_probability_calibration']['selected_method']}",
            f"  Selected risk policy: {report.tuning_summary['selected_risk_policy']}",
            "",
            "Train Metrics",
            f"  Public-markets: {report.train_metrics['public_markets']}",
            f"  M&A: {report.train_metrics['mna']}",
            "",
            "Validation Metrics",
            f"  Public-markets: {report.validation_metrics['public_markets']}",
            f"  M&A: {report.validation_metrics['mna']}",
            "",
            "Holdout Metrics",
            "  Public-markets:",
            f"    hit rate: {final_public['hit_rate']}",
            f"    avg return by signal tier: {final_public['avg_return_by_tier']}",
            f"    Sharpe: {final_public['sharpe']}",
            f"    max drawdown: {final_public['max_drawdown']}",
            f"    Brier score: {final_public['brier_score']}",
            f"    calibration error: {final_public['calibration_error']}",
            "  M&A:",
            f"    precision@k: {final_mna['precision_at_k']}",
            f"    acquirer top-1 accuracy: {final_mna['top1_accuracy']}",
            f"    acquirer top-3 accuracy: {final_mna['top3_accuracy']}",
            f"    acquirer top-5 accuracy: {final_mna['top5_accuracy']}",
            f"    acquirer MRR: {final_mna['mrr']}",
            f"    median lead days: {final_mna['median_lead_days']}",
            f"    false positive rate: {final_mna['false_positive_rate']}",
        ]
    )
    return "\n".join(lines)


def _write_outputs(report: StrictBacktestReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "strict_backtest_report.json"
    payload = {
        **asdict(report),
        "generated_at": report.generated_at.isoformat(),
        "splits": [
            {
                **asdict(item),
                "start_date": item.start_date.isoformat(),
                "end_date": item.end_date.isoformat(),
            }
            for item in report.splits
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run strict point-in-time backtest workflow")
    parser.add_argument("--universe-file", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--watchlist", default=DEFAULT_WATCHLIST)
    parser.add_argument("--replay-db", default=str(REPLAY_STORE_PATH))
    parser.add_argument("--replay-knowledge", default=str(REPLAY_KNOWLEDGE_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--refresh-remote-backfills",
        action="store_true",
        help="Refresh replay prices from remote sources before evaluation",
    )
    parser.add_argument(
        "--reuse-local-seeds",
        action="store_true",
        help="Reuse existing local replay events/claims instead of reseeding local YAML artifacts",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    workflow = StrictBacktestWorkflow(
        universe_file=args.universe_file,
        watchlist_path=args.watchlist,
        replay_db_path=args.replay_db,
        replay_knowledge_path=args.replay_knowledge,
        output_dir=args.output_dir,
        top_k=args.top_k,
        refresh_remote_backfills=args.refresh_remote_backfills,
        refresh_local_seeds=not args.reuse_local_seeds,
    )
    report = workflow.run()
    output_path = _write_outputs(report, Path(args.output_dir))
    print(render_report(report))
    print(f"\nJSON report: {output_path}")


if __name__ == "__main__":
    main()
