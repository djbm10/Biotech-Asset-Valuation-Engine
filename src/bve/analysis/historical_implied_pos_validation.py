"""
Historical validation of the market-implied PoS signal.

This module replays config-backed assets across historical dates, computes the
market-implied PoS using the existing ImpliedPoSSolver, and tests whether the
highest-spread names outperformed XBI over a fixed forward holding window.

Usage
-----
    python -m bve.analysis.historical_implied_pos_validation \
        --watchlist examples/configs/watchlists/watchlist_stage1.yaml \
        --start 2021-01-01 \
        --end 2025-03-20 \
        --hold-days 365
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
import random
from typing import Optional, Protocol

import yaml

from bve.analysis.alpha_validation import (
    OUTPUT_DIR,
    BootstrapDiagnostics,
    ClusterDiagnostics,
    ExcessReturnStats,
    OverlapDiagnostics,
    PairedExcessTrade,
    _compute_block_bootstrap,
    _compute_cluster_diagnostics,
    _compute_excess_return_stats,
    _compute_overlap_diagnostics,
)
from bve.analysis.implied_pos import ImpliedPoSResult, ImpliedPoSSolver, _SolverContext
from bve.analysis.implied_pos_batch import ScreenRow
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.historical_replay import REPLAY_KNOWLEDGE_PATH, REPLAY_STORE_PATH, ReplayStore


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRICE_LOOKBACK_DAYS = 7
_STAGE_RANK = {
    "preclinical": 0,
    "phase_1": 1,
    "phase_2": 2,
    "phase_3": 3,
    "nda_bla": 4,
    "approved": 5,
}
_VALID_CADENCES = {"weekly", "monthly", "quarterly"}


class _SolverProtocol(Protocol):
    def solve(self, config_path: str, current_ev_millions: float) -> Optional[ImpliedPoSResult]:
        ...


@dataclass(frozen=True)
class HistoricalConfigAsset:
    ticker: str
    asset_id: str
    config_path: Path
    program_label: str
    therapeutic_area: str
    stage: str
    shares_outstanding_millions: float
    cash_millions: float
    debt_millions: float
    single_asset: bool
    approximation_warning: Optional[str]


@dataclass(frozen=True)
class HistoricalScreenObservation:
    snapshot_date: date
    exit_date: date
    ticker: str
    asset_id: str
    config_path: str
    program_label: str
    therapeutic_area: str
    clinical_stage: str
    market_cap_millions: float
    daily_dollar_volume_millions: Optional[float]
    enterprise_value_millions: float
    model_pos: float
    implied_pos: float
    pos_spread: float
    model_rnpv_millions: float
    implied_rnpv_millions: float
    acquisition_discount: float
    market_exceeds_model: bool
    asset_return_pct: float
    xbi_return_pct: float
    excess_return_pct: float
    single_asset: bool
    approximation_warning: Optional[str]
    selected: bool = False


@dataclass(frozen=True)
class PlaceboDiagnostics:
    reverse_signal_n_trades: int
    reverse_signal_mean_excess_return_pct: Optional[float]
    shuffle_iterations: int
    shuffled_mean_excess_return_pct: Optional[float]
    shuffled_ci_low_pct: Optional[float]
    shuffled_ci_high_pct: Optional[float]
    shuffled_beats_actual_p_value: Optional[float]


@dataclass(frozen=True)
class LeaveOneOutDiagnostics:
    n_clusters_evaluated: int
    worst_excluded_asset_id: Optional[str]
    worst_case_mean_excess_return_pct: Optional[float]
    best_excluded_asset_id: Optional[str]
    best_case_mean_excess_return_pct: Optional[float]
    min_remaining_clusters: int


@dataclass(frozen=True)
class StageRobustnessRow:
    stage: str
    n_selected_trades: int
    mean_excess_return_pct: Optional[float]


@dataclass(frozen=True)
class HistoricalImpliedPoSValidationReport:
    watchlist_path: str
    start_date: date
    end_date: date
    hold_days: int
    cadence: str
    top_n: int
    require_phase2_plus: bool
    min_market_cap_millions: Optional[float]
    max_market_cap_millions: Optional[float]
    min_adv_millions: Optional[float]
    n_assets_in_watchlist: int
    n_assets_screenable: int
    n_snapshot_dates: int
    n_observations: int
    n_adv_covered_observations: int
    n_selected_trades: int
    n_unique_selected_tickers: int
    mean_selected_pos_spread_pp: Optional[float]
    mean_selected_excess_return_pct: Optional[float]
    mean_all_excess_return_pct: Optional[float]
    mean_bottom_excess_return_pct: Optional[float]
    persisted_snapshot_rows: int
    persisted_snapshot_dates: int
    knowledge_db_path: Optional[str]
    stats: ExcessReturnStats
    overlap: OverlapDiagnostics
    clusters: ClusterDiagnostics
    bootstrap: BootstrapDiagnostics
    placebo: PlaceboDiagnostics
    leave_one_out: LeaveOneOutDiagnostics
    stage_robustness: list[StageRobustnessRow]
    meets_cluster_target: bool
    meets_bootstrap_target: bool
    observations_csv_path: Path
    selected_csv_path: Path
    observations: list[HistoricalScreenObservation]
    selected_trades: list[PairedExcessTrade]


class HistoricalImpliedPoSValidator:
    def __init__(
        self,
        *,
        solver: Optional[_SolverProtocol] = None,
        replay_db_path: str | Path = REPLAY_STORE_PATH,
        output_dir: str | Path = OUTPUT_DIR,
        hold_days: int = 365,
        cadence: str = "monthly",
        top_n: int = 5,
        require_phase2_plus: bool = True,
        min_market_cap_millions: Optional[float] = None,
        max_market_cap_millions: Optional[float] = None,
        min_adv_millions: Optional[float] = None,
        adv_lookback_days: int = 20,
        benchmark_ticker: str = "XBI",
        knowledge_db_path: str | Path = REPLAY_KNOWLEDGE_PATH,
        persist_screen_snapshots: bool = False,
        shuffle_iterations: int = 1_000,
        shuffle_seed: int = 42,
        bootstrap_iterations: int = 10_000,
        bootstrap_block_days: int = 28,
        bootstrap_seed: int = 42,
    ) -> None:
        if cadence not in _VALID_CADENCES:
            raise ValueError(f"cadence must be one of {sorted(_VALID_CADENCES)}")
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        if hold_days <= 0:
            raise ValueError("hold_days must be positive")

        self.solver = solver or ImpliedPoSSolver(mc_simulations=1, random_seed=42)
        self.replay_db_path = Path(replay_db_path)
        self.output_dir = Path(output_dir)
        self.hold_days = int(hold_days)
        self.cadence = cadence
        self.top_n = int(top_n)
        self.require_phase2_plus = bool(require_phase2_plus)
        self.min_market_cap_millions = min_market_cap_millions
        self.max_market_cap_millions = max_market_cap_millions
        self.min_adv_millions = min_adv_millions
        self.adv_lookback_days = int(adv_lookback_days)
        self.benchmark_ticker = benchmark_ticker.upper()
        self.knowledge_db_path = Path(knowledge_db_path)
        self.persist_screen_snapshots = bool(persist_screen_snapshots)
        self.shuffle_iterations = int(shuffle_iterations)
        self.shuffle_seed = int(shuffle_seed)
        self.bootstrap_iterations = int(bootstrap_iterations)
        self.bootstrap_block_days = int(bootstrap_block_days)
        self.bootstrap_seed = int(bootstrap_seed)
        self._context_cache: dict[str, Optional[_SolverContext]] = {}

    def validate(
        self,
        watchlist_path: str,
        *,
        start_date: date,
        end_date: date,
    ) -> HistoricalImpliedPoSValidationReport:
        watchlist = self._resolve_watchlist_path(watchlist_path)
        assets = self._load_assets(watchlist)
        last_entry_date = end_date - timedelta(days=self.hold_days)
        snapshot_dates = (
            self._schedule_dates(start_date, last_entry_date, self.cadence)
            if start_date <= last_entry_date
            else []
        )

        observations: list[HistoricalScreenObservation] = []
        selected_trades: list[PairedExcessTrade] = []

        store = ReplayStore(str(self.replay_db_path))
        try:
            for snapshot_date in snapshot_dates:
                daily = self._build_observations_for_date(store, assets, snapshot_date)
                observations.extend(daily)
                selected = self._select_top_spread(daily)
                for obs in selected:
                    selected_trades.append(
                        PairedExcessTrade(
                            trade_id=f"{obs.asset_id}:{snapshot_date.isoformat()}",
                            asset_id=obs.asset_id,
                            ticker=obs.ticker,
                            entry_date=obs.snapshot_date,
                            exit_date=obs.exit_date,
                            trade_return=obs.asset_return_pct,
                            xbi_return=obs.xbi_return_pct,
                            excess_return=obs.excess_return_pct,
                        )
                    )
        finally:
            store.close()

        stats = _compute_excess_return_stats(selected_trades)
        overlap = _compute_overlap_diagnostics(selected_trades, stats)
        clusters = _compute_cluster_diagnostics(selected_trades)
        bootstrap = _compute_block_bootstrap(
            selected_trades,
            iterations=self.bootstrap_iterations,
            block_size_days=self.bootstrap_block_days,
            seed=self.bootstrap_seed,
        )

        selected_trade_ids = {trade.trade_id for trade in selected_trades}
        annotated = [
            HistoricalScreenObservation(
                **{
                    **asdict(obs),
                    "selected": f"{obs.asset_id}:{obs.snapshot_date.isoformat()}" in selected_trade_ids,
                }
            )
            for obs in observations
        ]
        persisted_rows = self._persist_screen_snapshots(annotated)
        placebo = self._compute_placebo_diagnostics(
            observations=annotated,
            actual_mean_excess_return_pct=_mean_or_none(
                [trade.excess_return for trade in selected_trades]
            ),
        )
        leave_one_out = self._compute_leave_one_out_diagnostics(selected_trades)
        stage_robustness = self._compute_stage_robustness(annotated)

        suffix = self._output_suffix(start_date, end_date)
        observations_csv = self._write_observations_csv(annotated, suffix=suffix)
        selected_csv = self._write_selected_csv(selected_trades, suffix=suffix)

        return HistoricalImpliedPoSValidationReport(
            watchlist_path=str(watchlist),
            start_date=start_date,
            end_date=end_date,
            hold_days=self.hold_days,
            cadence=self.cadence,
            top_n=self.top_n,
            require_phase2_plus=self.require_phase2_plus,
            min_market_cap_millions=self.min_market_cap_millions,
            max_market_cap_millions=self.max_market_cap_millions,
            min_adv_millions=self.min_adv_millions,
            n_assets_in_watchlist=self._watchlist_count(watchlist),
            n_assets_screenable=len(assets),
            n_snapshot_dates=len(snapshot_dates),
            n_observations=len(annotated),
            n_adv_covered_observations=sum(
                1 for obs in annotated if obs.daily_dollar_volume_millions is not None
            ),
            n_selected_trades=len(selected_trades),
            n_unique_selected_tickers=len({trade.ticker for trade in selected_trades}),
            mean_selected_pos_spread_pp=_mean_or_none(
                [obs.pos_spread * 100.0 for obs in annotated if obs.selected]
            ),
            mean_selected_excess_return_pct=_mean_or_none(
                [trade.excess_return for trade in selected_trades]
            ),
            mean_all_excess_return_pct=_mean_or_none(
                [obs.excess_return_pct for obs in annotated]
            ),
            mean_bottom_excess_return_pct=_mean_or_none(
                [obs.excess_return_pct for obs in self._bottom_cohort(annotated)]
            ),
            persisted_snapshot_rows=persisted_rows,
            persisted_snapshot_dates=len({obs.snapshot_date for obs in annotated}) if persisted_rows else 0,
            knowledge_db_path=str(self.knowledge_db_path) if self.persist_screen_snapshots else None,
            stats=stats,
            overlap=overlap,
            clusters=clusters,
            bootstrap=bootstrap,
            placebo=placebo,
            leave_one_out=leave_one_out,
            stage_robustness=stage_robustness,
            meets_cluster_target=clusters.n_assets >= 20,
            meets_bootstrap_target=(
                bootstrap.p_value is not None and bootstrap.p_value < 0.05
            ),
            observations_csv_path=observations_csv,
            selected_csv_path=selected_csv,
            observations=annotated,
            selected_trades=selected_trades,
        )

    def _build_observations_for_date(
        self,
        store: ReplayStore,
        assets: list[HistoricalConfigAsset],
        snapshot_date: date,
    ) -> list[HistoricalScreenObservation]:
        exit_date = snapshot_date + timedelta(days=self.hold_days)
        xbi_return = _bounded_return(
            store,
            self.benchmark_ticker,
            snapshot_date,
            exit_date,
        )
        if xbi_return is None:
            return []

        observations: list[HistoricalScreenObservation] = []
        for asset in assets:
            obs = self._evaluate_asset(store, asset, snapshot_date, exit_date, xbi_return)
            if obs is not None:
                observations.append(obs)
        observations.sort(key=lambda obs: (-obs.pos_spread, obs.ticker, obs.asset_id))
        return observations

    def _output_suffix(self, start_date: date, end_date: date) -> str:
        stage_scope = "phase2plus" if self.require_phase2_plus else "allstages"
        filters: list[str] = []
        if self.min_market_cap_millions is not None or self.max_market_cap_millions is not None:
            min_cap = (
                f"{int(self.min_market_cap_millions)}"
                if self.min_market_cap_millions is not None
                else "none"
            )
            max_cap = (
                f"{int(self.max_market_cap_millions)}"
                if self.max_market_cap_millions is not None
                else "none"
            )
            filters.append(f"mcap{min_cap}to{max_cap}")
        if self.min_adv_millions is not None:
            filters.append(f"adv{_suffix_number(self.min_adv_millions)}")

        filter_scope = f"_{'_'.join(filters)}" if filters else ""
        return (
            f"{start_date.isoformat()}_{end_date.isoformat()}_"
            f"{self.cadence}_{stage_scope}{filter_scope}_hold{self.hold_days}d_top{self.top_n}"
        )

    def _evaluate_asset(
        self,
        store: ReplayStore,
        asset: HistoricalConfigAsset,
        snapshot_date: date,
        exit_date: date,
        xbi_return: float,
    ) -> Optional[HistoricalScreenObservation]:
        if self.require_phase2_plus and _stage_rank(asset.stage) < _STAGE_RANK["phase_2"]:
            return None

        entry_price = _bounded_price(store, asset.ticker, snapshot_date)
        exit_price = _bounded_price(store, asset.ticker, exit_date)
        if entry_price is None or exit_price is None:
            return None

        market_cap = float(entry_price) * asset.shares_outstanding_millions
        if (
            self.min_market_cap_millions is not None
            and market_cap < self.min_market_cap_millions
        ):
            return None
        if (
            self.max_market_cap_millions is not None
            and market_cap > self.max_market_cap_millions
        ):
            return None

        adv_millions = _historical_adv_millions(
            store,
            asset.ticker,
            snapshot_date,
            lookback_days=self.adv_lookback_days,
        )
        if self.min_adv_millions is not None:
            if adv_millions is None or adv_millions < self.min_adv_millions:
                return None

        enterprise_value = market_cap - asset.cash_millions + asset.debt_millions
        if enterprise_value <= 0:
            return None

        solved = self._solve(asset.config_path, enterprise_value)
        if solved is None:
            return None

        asset_return = ReplayStore.compute_return_pct(entry_price, exit_price)
        if asset_return is None:
            return None

        return HistoricalScreenObservation(
            snapshot_date=snapshot_date,
            exit_date=exit_date,
            ticker=asset.ticker,
            asset_id=solved.asset_id,
            config_path=str(asset.config_path),
            program_label=asset.program_label,
            therapeutic_area=asset.therapeutic_area,
            clinical_stage=asset.stage,
            market_cap_millions=round(market_cap, 6),
            daily_dollar_volume_millions=(
                round(float(adv_millions), 6) if adv_millions is not None else None
            ),
            enterprise_value_millions=round(enterprise_value, 6),
            model_pos=solved.model_pos,
            implied_pos=solved.implied_pos,
            pos_spread=solved.pos_spread,
            model_rnpv_millions=solved.model_rnpv_millions,
            implied_rnpv_millions=solved.implied_rnpv_millions,
            acquisition_discount=solved.acquisition_discount,
            market_exceeds_model=solved.market_exceeds_model,
            asset_return_pct=round(asset_return, 6),
            xbi_return_pct=round(float(xbi_return), 6),
            excess_return_pct=round(float(asset_return) - float(xbi_return), 6),
            single_asset=asset.single_asset,
            approximation_warning=asset.approximation_warning,
        )

    def _solve(self, config_path: Path, enterprise_value_millions: float) -> Optional[ImpliedPoSResult]:
        if not isinstance(self.solver, ImpliedPoSSolver):
            return self.solver.solve(str(config_path), enterprise_value_millions)

        key = str(config_path.resolve())
        if key not in self._context_cache:
            self._context_cache[key] = self.solver._build_context(config_path)
        context = self._context_cache[key]
        if context is None:
            return None
        return _solve_with_cached_context(
            self.solver,
            context,
            enterprise_value_millions,
        )

    def _select_top_spread(
        self,
        observations: list[HistoricalScreenObservation],
    ) -> list[HistoricalScreenObservation]:
        ranked = sorted(
            observations,
            key=lambda obs: (-obs.pos_spread, obs.ticker, obs.asset_id),
        )
        return ranked[: self.top_n]

    def _bottom_cohort(
        self,
        observations: list[HistoricalScreenObservation],
    ) -> list[HistoricalScreenObservation]:
        grouped: dict[date, list[HistoricalScreenObservation]] = {}
        for obs in observations:
            grouped.setdefault(obs.snapshot_date, []).append(obs)
        bottom: list[HistoricalScreenObservation] = []
        for daily in grouped.values():
            ranked = sorted(daily, key=lambda obs: (obs.pos_spread, obs.ticker, obs.asset_id))
            bottom.extend(ranked[: self.top_n])
        return bottom

    def _persist_screen_snapshots(
        self,
        observations: list[HistoricalScreenObservation],
    ) -> int:
        if not self.persist_screen_snapshots or not observations:
            return 0

        rows = [
            ScreenRow(
                ticker=obs.ticker,
                program_label=obs.program_label,
                stage=obs.clinical_stage,
                ta=obs.therapeutic_area,
                model_pos=obs.model_pos,
                implied_pos=obs.implied_pos,
                spread_pp=round(obs.pos_spread * 100.0, 4),
                rnpv_millions=obs.model_rnpv_millions,
                ev_millions=obs.enterprise_value_millions,
                acquisition_discount_pct=_discount_multiple_to_pct(obs.acquisition_discount),
                next_catalyst="historical_snapshot",
                catalyst_date=None,
                days_to_catalyst=None,
                single_asset=obs.single_asset,
                approximation_warning=obs.approximation_warning,
                data_date=obs.snapshot_date,
                asset_id=obs.asset_id,
                thesis_strength=None,
                market_exceeds_model=obs.market_exceeds_model,
                config_quality=None,
            )
            for obs in observations
        ]
        store = KnowledgeStore(self.knowledge_db_path)
        try:
            return store.write_screen_snapshots(rows)
        finally:
            store.close()

    def _compute_placebo_diagnostics(
        self,
        *,
        observations: list[HistoricalScreenObservation],
        actual_mean_excess_return_pct: Optional[float],
    ) -> PlaceboDiagnostics:
        reverse = self._bottom_cohort(observations)
        reverse_mean = _mean_or_none([obs.excess_return_pct for obs in reverse])

        grouped: dict[date, list[HistoricalScreenObservation]] = {}
        for obs in observations:
            grouped.setdefault(obs.snapshot_date, []).append(obs)

        if not grouped or self.shuffle_iterations <= 0:
            return PlaceboDiagnostics(
                reverse_signal_n_trades=len(reverse),
                reverse_signal_mean_excess_return_pct=reverse_mean,
                shuffle_iterations=0,
                shuffled_mean_excess_return_pct=None,
                shuffled_ci_low_pct=None,
                shuffled_ci_high_pct=None,
                shuffled_beats_actual_p_value=None,
            )

        rng = random.Random(self.shuffle_seed)
        shuffled_means: list[float] = []
        for _ in range(self.shuffle_iterations):
            sampled_excess: list[float] = []
            for daily in grouped.values():
                if not daily:
                    continue
                k = min(self.top_n, len(daily))
                sampled_excess.extend(obs.excess_return_pct for obs in rng.sample(daily, k=k))
            mean_value = _mean_or_none(sampled_excess)
            if mean_value is not None:
                shuffled_means.append(mean_value)

        shuffled_means.sort()
        shuffled_mean = _mean_or_none(shuffled_means)
        shuffled_ci_low = _percentile(shuffled_means, 0.05)
        shuffled_ci_high = _percentile(shuffled_means, 0.95)
        beats_actual = None
        if actual_mean_excess_return_pct is not None and shuffled_means:
            beats_actual = sum(
                1 for value in shuffled_means if value >= actual_mean_excess_return_pct
            ) / len(shuffled_means)

        return PlaceboDiagnostics(
            reverse_signal_n_trades=len(reverse),
            reverse_signal_mean_excess_return_pct=reverse_mean,
            shuffle_iterations=len(shuffled_means),
            shuffled_mean_excess_return_pct=shuffled_mean,
            shuffled_ci_low_pct=shuffled_ci_low,
            shuffled_ci_high_pct=shuffled_ci_high,
            shuffled_beats_actual_p_value=(
                round(float(beats_actual), 6) if beats_actual is not None else None
            ),
        )

    @staticmethod
    def _compute_leave_one_out_diagnostics(
        selected_trades: list[PairedExcessTrade],
    ) -> LeaveOneOutDiagnostics:
        asset_ids = sorted({trade.asset_id for trade in selected_trades})
        if len(asset_ids) <= 1:
            return LeaveOneOutDiagnostics(
                n_clusters_evaluated=len(asset_ids),
                worst_excluded_asset_id=None,
                worst_case_mean_excess_return_pct=None,
                best_excluded_asset_id=None,
                best_case_mean_excess_return_pct=None,
                min_remaining_clusters=max(0, len(asset_ids) - 1),
            )

        worst_asset: Optional[str] = None
        worst_mean: Optional[float] = None
        best_asset: Optional[str] = None
        best_mean: Optional[float] = None
        min_remaining_clusters = len(asset_ids)

        for asset_id in asset_ids:
            subset = [trade for trade in selected_trades if trade.asset_id != asset_id]
            subset_mean = _mean_or_none([trade.excess_return for trade in subset])
            remaining_clusters = len({trade.asset_id for trade in subset})
            min_remaining_clusters = min(min_remaining_clusters, remaining_clusters)
            if subset_mean is None:
                continue
            if worst_mean is None or subset_mean < worst_mean:
                worst_mean = subset_mean
                worst_asset = asset_id
            if best_mean is None or subset_mean > best_mean:
                best_mean = subset_mean
                best_asset = asset_id

        return LeaveOneOutDiagnostics(
            n_clusters_evaluated=len(asset_ids),
            worst_excluded_asset_id=worst_asset,
            worst_case_mean_excess_return_pct=worst_mean,
            best_excluded_asset_id=best_asset,
            best_case_mean_excess_return_pct=best_mean,
            min_remaining_clusters=min_remaining_clusters,
        )

    @staticmethod
    def _compute_stage_robustness(
        observations: list[HistoricalScreenObservation],
    ) -> list[StageRobustnessRow]:
        grouped: dict[str, list[HistoricalScreenObservation]] = {}
        for obs in observations:
            if not obs.selected:
                continue
            grouped.setdefault(obs.clinical_stage, []).append(obs)

        rows = [
            StageRobustnessRow(
                stage=stage,
                n_selected_trades=len(group),
                mean_excess_return_pct=_mean_or_none([obs.excess_return_pct for obs in group]),
            )
            for stage, group in grouped.items()
        ]
        rows.sort(key=lambda row: (-_stage_rank(row.stage), row.stage))
        return rows

    def _load_assets(self, watchlist_path: Path) -> list[HistoricalConfigAsset]:
        config = _load_watchlist(watchlist_path)
        assets: list[HistoricalConfigAsset] = []
        seen_tickers: set[str] = set()
        for watchlist_asset in config:
            raw_config_path = watchlist_asset.get("valuation_config")
            if not raw_config_path:
                continue
            cfg_path = _resolve_config_path(str(raw_config_path), watchlist_path)
            asset = _load_config_asset(cfg_path)
            if asset is None or asset.ticker in seen_tickers:
                continue
            seen_tickers.add(asset.ticker)
            assets.append(asset)
        assets.sort(key=lambda asset: asset.ticker)
        return assets

    @staticmethod
    def _schedule_dates(start_date: date, end_date: date, cadence: str) -> list[date]:
        if start_date > end_date:
            return []
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            if cadence == "weekly":
                current += timedelta(days=7)
            elif cadence == "monthly":
                current = _add_months(current, 1)
            else:
                current = _add_months(current, 3)
        return dates

    @staticmethod
    def _resolve_watchlist_path(raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if path.exists():
            return path
        candidates = [
            _REPO_ROOT / raw_path,
            _REPO_ROOT / "examples" / "configs" / "watchlists" / raw_path,
            _REPO_ROOT / "examples" / "configs" / "watchlists" / Path(raw_path).name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return path

    @staticmethod
    def _watchlist_count(watchlist_path: Path) -> int:
        return len(_load_watchlist(watchlist_path))

    def _write_observations_csv(
        self,
        observations: list[HistoricalScreenObservation],
        *,
        suffix: str,
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"historical_implied_pos_validation_{suffix}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "snapshot_date",
                    "exit_date",
                    "ticker",
                    "asset_id",
                    "config_path",
                    "program_label",
                    "therapeutic_area",
                    "clinical_stage",
                    "market_cap_millions",
                    "daily_dollar_volume_millions",
                    "enterprise_value_millions",
                    "model_pos",
                    "implied_pos",
                    "pos_spread",
                    "model_rnpv_millions",
                    "implied_rnpv_millions",
                    "acquisition_discount",
                    "market_exceeds_model",
                    "asset_return_pct",
                    "xbi_return_pct",
                    "excess_return_pct",
                    "single_asset",
                    "approximation_warning",
                    "selected",
                ],
            )
            writer.writeheader()
            for obs in observations:
                writer.writerow(
                    {
                        **asdict(obs),
                        "snapshot_date": obs.snapshot_date.isoformat(),
                        "exit_date": obs.exit_date.isoformat(),
                    }
                )
        return path

    def _write_selected_csv(
        self,
        trades: list[PairedExcessTrade],
        *,
        suffix: str,
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"historical_implied_pos_selected_{suffix}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "trade_id",
                    "asset_id",
                    "ticker",
                    "entry_date",
                    "exit_date",
                    "trade_return",
                    "xbi_return",
                    "excess_return",
                ],
            )
            writer.writeheader()
            for trade in trades:
                writer.writerow(
                    {
                        "trade_id": trade.trade_id,
                        "asset_id": trade.asset_id,
                        "ticker": trade.ticker,
                        "entry_date": trade.entry_date.isoformat(),
                        "exit_date": trade.exit_date.isoformat(),
                        "trade_return": f"{trade.trade_return:.6f}",
                        "xbi_return": f"{trade.xbi_return:.6f}",
                        "excess_return": f"{trade.excess_return:.6f}",
                    }
                )
        return path


def _resolve_config_path(raw_path: str, watchlist_path: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.exists():
        return path
    if not path.is_absolute():
        candidate = (watchlist_path.parent / path).resolve()
        if candidate.exists():
            return candidate
        repo_candidate = (_REPO_ROOT / path).resolve()
        if repo_candidate.exists():
            return repo_candidate
    return path


def _bounded_price(
    store: ReplayStore,
    ticker: str,
    target_date: date,
    *,
    lookback_days: int = _PRICE_LOOKBACK_DAYS,
) -> Optional[float]:
    lower_bound = (target_date - timedelta(days=lookback_days)).isoformat()
    row = store._conn.execute(
        "SELECT close_usd FROM historical_prices "
        "WHERE ticker = ? AND price_date >= ? AND price_date <= ? "
        "ORDER BY price_date DESC LIMIT 1",
        (ticker, lower_bound, target_date.isoformat()),
    ).fetchone()
    if row is None:
        return None
    return float(row["close_usd"])


def _bounded_return(
    store: ReplayStore,
    ticker: str,
    from_date: date,
    to_date: date,
    *,
    lookback_days: int = _PRICE_LOOKBACK_DAYS,
) -> Optional[float]:
    entry_price = _bounded_price(store, ticker, from_date, lookback_days=lookback_days)
    exit_price = _bounded_price(store, ticker, to_date, lookback_days=lookback_days)
    return ReplayStore.compute_return_pct(entry_price, exit_price)


def _historical_adv_millions(
    store: ReplayStore,
    ticker: str,
    target_date: date,
    *,
    lookback_days: int = 20,
) -> Optional[float]:
    if not _table_exists(store, "market_prices"):
        return None

    rows = store._conn.execute(
        "SELECT close_usd, volume FROM market_prices "
        "WHERE ticker = ? AND price_date <= ? "
        "AND close_usd IS NOT NULL AND volume IS NOT NULL "
        "ORDER BY price_date DESC LIMIT ?",
        (ticker, target_date.isoformat(), int(lookback_days)),
    ).fetchall()
    if len(rows) < max(5, lookback_days // 2):
        return None

    dollar_volumes = [float(row["close_usd"]) * float(row["volume"]) / 1e6 for row in rows]
    if not dollar_volumes:
        return None
    return float(sum(dollar_volumes) / len(dollar_volumes))


def _table_exists(store: ReplayStore, table_name: str) -> bool:
    row = store._conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _load_watchlist(path: Path) -> list[dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(raw, dict):
        records = raw.get("watchlist", [])
    else:
        records = raw
    if not isinstance(records, list):
        raise ValueError("Watchlist YAML must be a list or contain a 'watchlist' list")
    return [record for record in records if isinstance(record, dict)]


def _load_config_asset(config_path: Path) -> Optional[HistoricalConfigAsset]:
    if not config_path.exists():
        return None

    from bve.cli.run_asset import _load_config

    try:
        cfg = _load_config(config_path)
    except Exception:  # noqa: BLE001
        return None

    asset_cfg = cfg.get("asset", {})
    company_cfg = cfg.get("company", {})
    ticker = str(company_cfg.get("ticker") or "").strip().upper()
    asset_id = str(asset_cfg.get("id") or "").strip()
    shares = company_cfg.get("shares_outstanding_millions")
    if not ticker or not asset_id or shares is None or float(shares) <= 0:
        return None

    return HistoricalConfigAsset(
        ticker=ticker,
        asset_id=asset_id,
        config_path=config_path.resolve(),
        program_label=str(asset_cfg.get("name") or asset_id),
        therapeutic_area=str(asset_cfg.get("therapeutic_area") or "other"),
        stage=str(asset_cfg.get("stage") or "unknown"),
        shares_outstanding_millions=float(shares),
        cash_millions=float(company_cfg.get("cash_millions") or 0.0),
        debt_millions=float(company_cfg.get("debt_millions") or 0.0),
        single_asset=bool(company_cfg.get("single_asset", True)),
        approximation_warning=(
            str(company_cfg.get("approximation_warning"))
            if company_cfg.get("approximation_warning") is not None
            else None
        ),
    )


def _stage_rank(raw_stage: str) -> int:
    text = str(raw_stage or "").strip().lower().replace(" ", "_")
    if "approved" in text:
        return _STAGE_RANK["approved"]
    if "nda" in text or "bla" in text:
        return _STAGE_RANK["nda_bla"]
    if "phase_3" in text:
        return _STAGE_RANK["phase_3"]
    if "phase_2" in text:
        return _STAGE_RANK["phase_2"]
    if "phase_1" in text:
        return _STAGE_RANK["phase_1"]
    return _STAGE_RANK["preclinical"]


def _mean_or_none(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    last_day = _month_last_day(year, month)
    return date(year, month, min(value.day, last_day))


def _month_last_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _solve_with_cached_context(
    solver: ImpliedPoSSolver,
    context: _SolverContext,
    current_ev_millions: float,
) -> Optional[ImpliedPoSResult]:
    if current_ev_millions <= 0:
        return None

    tolerance = solver._tolerance_for_ev(current_ev_millions)
    if not context.base_trials:
        return solver._solve_no_remaining_trials(
            context.base_output,
            current_ev_millions=current_ev_millions,
            tolerance=tolerance,
        )

    lo_pos = solver.min_pos
    hi_pos = solver.max_pos
    lo_actual_pos, lo_rnpv = solver._value_at_target_pos(context, lo_pos)
    hi_actual_pos, hi_rnpv = solver._value_at_target_pos(context, hi_pos)

    best_pos = lo_actual_pos
    best_rnpv = lo_rnpv
    best_error = abs(lo_rnpv - current_ev_millions)

    if abs(hi_rnpv - current_ev_millions) < best_error:
        best_pos = hi_actual_pos
        best_rnpv = hi_rnpv
        best_error = abs(hi_rnpv - current_ev_millions)

    if hi_rnpv < current_ev_millions - tolerance:
        return solver._build_result(
            context.base_output,
            current_ev_millions=current_ev_millions,
            implied_pos=hi_actual_pos,
            implied_rnpv_millions=hi_rnpv,
            iterations=0,
            market_exceeds_model=True,
        )

    if lo_rnpv > current_ev_millions + tolerance:
        return solver._build_result(
            context.base_output,
            current_ev_millions=current_ev_millions,
            implied_pos=lo_actual_pos,
            implied_rnpv_millions=lo_rnpv,
            iterations=0,
            market_exceeds_model=False,
        )

    iterations = 0
    for iterations in range(1, solver.max_iterations + 1):
        mid_pos = (lo_pos + hi_pos) / 2.0
        actual_pos, mid_rnpv = solver._value_at_target_pos(context, mid_pos)
        error = abs(mid_rnpv - current_ev_millions)

        if error < best_error:
            best_pos = actual_pos
            best_rnpv = mid_rnpv
            best_error = error

        if error <= tolerance:
            best_pos = actual_pos
            best_rnpv = mid_rnpv
            break

        if mid_rnpv > current_ev_millions:
            hi_pos = mid_pos
        else:
            lo_pos = mid_pos

    return solver._build_result(
        context.base_output,
        current_ev_millions=current_ev_millions,
        implied_pos=best_pos,
        implied_rnpv_millions=best_rnpv,
        iterations=iterations,
        market_exceeds_model=False,
    )


def render_historical_implied_pos_report(
    report: HistoricalImpliedPoSValidationReport,
) -> str:
    if (
        report.min_market_cap_millions is not None
        and report.max_market_cap_millions is not None
    ):
        market_cap_filter = (
            f"${report.min_market_cap_millions:.0f}M to ${report.max_market_cap_millions:.0f}M"
        )
    elif report.min_market_cap_millions is not None:
        market_cap_filter = f"min ${report.min_market_cap_millions:.0f}M"
    elif report.max_market_cap_millions is not None:
        market_cap_filter = f"max ${report.max_market_cap_millions:.0f}M"
    else:
        market_cap_filter = "none"

    adv_filter = (
        f"min ${report.min_adv_millions:.1f}M"
        if report.min_adv_millions is not None
        else "none"
    )
    stage_lines = (
        [
            f"Stage robustness:      {row.stage} n={row.n_selected_trades} "
            f"mean={_fmt_pct(row.mean_excess_return_pct)}"
            for row in report.stage_robustness
        ]
        if report.stage_robustness
        else ["Stage robustness:      n/a"]
    )
    lines = [
        "=" * 60,
        "HISTORICAL IMPLIED POS VALIDATION",
        "=" * 60,
        f"Watchlist:             {report.watchlist_path}",
        f"Date range:            {report.start_date.isoformat()} -> {report.end_date.isoformat()}",
        f"Cadence / hold:        {report.cadence} / {report.hold_days}d",
        f"Selection:             top {report.top_n} pos_spread names per snapshot",
        f"Market-cap filter:     {market_cap_filter}",
        f"ADV filter:            {adv_filter}",
        f"Watchlist assets:      {report.n_assets_in_watchlist}",
        f"Screenable assets:     {report.n_assets_screenable}",
        f"Snapshot dates:        {report.n_snapshot_dates}",
        f"Observations:          {report.n_observations}",
        f"ADV-covered obs:       {report.n_adv_covered_observations}",
        f"Selected trades:       {report.n_selected_trades}",
        f"Unique clusters:       {report.clusters.n_assets}",
        f"Mean spread (selected): {_fmt_pct(report.mean_selected_pos_spread_pp)}",
        f"Mean excess return:    {_fmt_pct(report.mean_selected_excess_return_pct)}",
        f"Mean excess (all):     {_fmt_pct(report.mean_all_excess_return_pct)}",
        f"Mean excess (bottom):  {_fmt_pct(report.mean_bottom_excess_return_pct)}",
        f"Bootstrap p-value:     {_fmt_p(report.bootstrap.p_value)}",
        f"Cluster target G>=20:  {'YES' if report.meets_cluster_target else 'NO'}",
        f"Bootstrap p<0.05:      {'YES' if report.meets_bootstrap_target else 'NO'}",
        f"Reverse placebo:       {_fmt_pct(report.placebo.reverse_signal_mean_excess_return_pct)} "
        f"(n={report.placebo.reverse_signal_n_trades})",
        f"Shuffle placebo mean:  {_fmt_pct(report.placebo.shuffled_mean_excess_return_pct)} "
        f"[{_fmt_pct(report.placebo.shuffled_ci_low_pct)}, "
        f"{_fmt_pct(report.placebo.shuffled_ci_high_pct)}]",
        f"Shuffle >= actual p:   {_fmt_p(report.placebo.shuffled_beats_actual_p_value)}",
        f"Leave-one-out worst:   {_fmt_pct(report.leave_one_out.worst_case_mean_excess_return_pct)} "
        f"(drop {report.leave_one_out.worst_excluded_asset_id or 'n/a'})",
        f"Leave-one-out best:    {_fmt_pct(report.leave_one_out.best_case_mean_excess_return_pct)} "
        f"(drop {report.leave_one_out.best_excluded_asset_id or 'n/a'})",
        f"Min LOO clusters:      {report.leave_one_out.min_remaining_clusters}",
        *stage_lines,
        f"Persisted snapshots:   {report.persisted_snapshot_rows}",
    ]
    if report.knowledge_db_path is not None:
        lines.append(f"Knowledge DB:          {report.knowledge_db_path}")
    lines.extend(
        [
            f"Observations CSV:      {report.observations_csv_path}",
            f"Selected CSV:          {report.selected_csv_path}",
        ]
    )
    return "\n".join(lines)


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def _fmt_p(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _discount_multiple_to_pct(value: float) -> float:
    return round((float(value) - 1.0) * 100.0, 4)


def _percentile(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    bounded = min(max(float(q), 0.0), 1.0)
    idx = int(round((len(values) - 1) * bounded))
    return float(values[idx])


def _suffix_number(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate whether high historical implied-PoS spreads outperformed"
    )
    parser.add_argument("--watchlist", required=True, help="Watchlist YAML with valuation configs")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--hold-days", type=int, default=365, help="Forward holding window")
    parser.add_argument(
        "--cadence",
        choices=sorted(_VALID_CADENCES),
        default="monthly",
        help="Historical screening cadence",
    )
    parser.add_argument("--top-n", type=int, default=5, help="Top-spread names per snapshot")
    parser.add_argument(
        "--min-market-cap",
        type=float,
        default=None,
        help="Optional minimum historical market cap filter ($M)",
    )
    parser.add_argument(
        "--max-market-cap",
        type=float,
        default=None,
        help="Optional maximum historical market cap filter ($M)",
    )
    parser.add_argument(
        "--min-adv",
        type=float,
        default=None,
        help="Optional minimum historical average daily dollar volume filter ($M)",
    )
    parser.add_argument(
        "--adv-lookback-days",
        type=int,
        default=20,
        help="Trailing market-price rows used for historical ADV when market_prices exists",
    )
    parser.add_argument(
        "--allow-phase1",
        action="store_true",
        help="Include pre-Phase-2 assets instead of filtering to Phase 2+",
    )
    parser.add_argument(
        "--replay-db",
        default=str(REPLAY_STORE_PATH),
        help="Replay SQLite store path",
    )
    parser.add_argument(
        "--knowledge-db",
        default=str(REPLAY_KNOWLEDGE_PATH),
        help="KnowledgeStore DB path used when persisting historical screen snapshots",
    )
    parser.add_argument(
        "--persist-screen-snapshots",
        action="store_true",
        help="Persist historical observation rows into screen_snapshots",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Directory for CSV outputs",
    )
    parser.add_argument(
        "--shuffle-iterations",
        type=int,
        default=1_000,
        help="Within-date shuffle placebo iteration count",
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=10_000,
        help="Block bootstrap iteration count",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    validator = HistoricalImpliedPoSValidator(
        replay_db_path=args.replay_db,
        output_dir=args.output_dir,
        hold_days=args.hold_days,
        cadence=args.cadence,
        top_n=args.top_n,
        require_phase2_plus=not args.allow_phase1,
        min_market_cap_millions=args.min_market_cap,
        max_market_cap_millions=args.max_market_cap,
        min_adv_millions=args.min_adv,
        adv_lookback_days=args.adv_lookback_days,
        knowledge_db_path=args.knowledge_db,
        persist_screen_snapshots=args.persist_screen_snapshots,
        shuffle_iterations=args.shuffle_iterations,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    report = validator.validate(
        args.watchlist,
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
    )
    print(render_historical_implied_pos_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
