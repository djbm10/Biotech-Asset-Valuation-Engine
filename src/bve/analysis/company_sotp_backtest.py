"""
Historical backtest over stored company-level SOTP snapshots.

Uses ``company_sotp_snapshots`` as the primary signal dataset, selects the top
ranked company discounts on each historical snapshot date, and evaluates their
forward excess returns versus XBI using replay-store prices.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from bve.analysis.alpha_validation import (
    DEFAULT_BENCHMARK_TICKER,
    DEFAULT_BOOTSTRAP_BLOCK_DAYS,
    DEFAULT_BOOTSTRAP_ITERATIONS,
    DEFAULT_BOOTSTRAP_SEED,
    BootstrapDiagnostics,
    ClusterDiagnostics,
    ExcessReturnStats,
    OverlapDiagnostics,
    OUTPUT_DIR,
    PairedExcessTrade,
    _compute_block_bootstrap,
    _compute_cluster_diagnostics,
    _compute_excess_return_stats,
    _compute_overlap_diagnostics,
)
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore


@dataclass(frozen=True)
class CompanySOTPBacktestConfig:
    start_date: date
    end_date: date
    hold_days: int = 365
    top_n: int = 10
    benchmark_ticker: str = DEFAULT_BENCHMARK_TICKER
    min_ranked_sotp_discount: float = 1.0
    require_recency_gate: bool = True
    allowed_action_policies: tuple[str, ...] = ("buy", "watch", "needs_manual_review")
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS
    bootstrap_block_days: int = DEFAULT_BOOTSTRAP_BLOCK_DAYS
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED


@dataclass(frozen=True)
class CompanySOTPBacktestTrade:
    snapshot_date: date
    exit_date: date
    ticker: str
    company_id: str
    ranked_sotp_discount: float
    action_policy: str
    company_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float


@dataclass(frozen=True)
class CompanySOTPBacktestReport:
    start_date: date
    end_date: date
    hold_days: int
    top_n: int
    benchmark_ticker: str
    min_ranked_sotp_discount: float
    n_snapshot_dates: int
    n_candidate_rows: int
    n_selected_trades: int
    n_missing_price_trades: int
    stats: ExcessReturnStats
    overlap: OverlapDiagnostics
    clusters: ClusterDiagnostics
    bootstrap: BootstrapDiagnostics
    csv_path: Path
    trades: list[CompanySOTPBacktestTrade]
    allowed_action_policies: tuple[str, ...]


def _normalize_action_policies(policies: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if not policies:
        return ()
    return tuple(
        policy.strip().lower()
        for policy in policies
        if policy and policy.strip()
    )


class CompanySOTPBacktester:
    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        *,
        replay_db_path: str | Path = REPLAY_STORE_PATH,
        output_dir: str | Path = OUTPUT_DIR,
        config: Optional[CompanySOTPBacktestConfig] = None,
    ) -> None:
        self.knowledge = knowledge_store
        self.replay_db_path = Path(replay_db_path)
        self.output_dir = Path(output_dir)
        self.config = config or CompanySOTPBacktestConfig(
            start_date=date(2021, 1, 1),
            end_date=date.today(),
        )

    def run(self) -> CompanySOTPBacktestReport:
        last_entry_date = self.config.end_date - timedelta(days=self.config.hold_days)
        snapshot_dates = [
            item
            for item in sorted(self.knowledge.list_company_sotp_snapshot_dates())
            if self.config.start_date <= item <= last_entry_date
        ]

        trades: list[CompanySOTPBacktestTrade] = []
        paired: list[PairedExcessTrade] = []
        n_candidate_rows = 0
        n_missing_price_trades = 0

        replay = ReplayStore(str(self.replay_db_path))
        try:
            for snapshot_date in snapshot_dates:
                rows = self.knowledge.get_company_sotp_snapshots(
                    snapshot_date=snapshot_date,
                    limit=10000,
                )
                eligible = self._select_rows(rows)
                n_candidate_rows += len(eligible)
                exit_date = snapshot_date + timedelta(days=self.config.hold_days)
                for row in eligible[: self.config.top_n]:
                    company_return = replay.get_return(row["ticker"], snapshot_date, exit_date)
                    benchmark_return = replay.get_return(
                        self.config.benchmark_ticker,
                        snapshot_date,
                        exit_date,
                    )
                    if company_return is None or benchmark_return is None:
                        n_missing_price_trades += 1
                        continue
                    excess_return = float(company_return - benchmark_return)
                    trades.append(
                        CompanySOTPBacktestTrade(
                            snapshot_date=snapshot_date,
                            exit_date=exit_date,
                            ticker=str(row["ticker"]),
                            company_id=str(row["company_id"]),
                            ranked_sotp_discount=float(row["ranked_sotp_discount"]),
                            action_policy=str(row.get("action_policy") or "unknown"),
                            company_return_pct=float(company_return),
                            benchmark_return_pct=float(benchmark_return),
                            excess_return_pct=excess_return,
                        )
                    )
                    paired.append(
                        PairedExcessTrade(
                            trade_id=f"{row['ticker']}:{snapshot_date.isoformat()}",
                            asset_id=str(row["company_id"]),
                            ticker=str(row["ticker"]),
                            entry_date=snapshot_date,
                            exit_date=exit_date,
                            trade_return=float(company_return),
                            xbi_return=float(benchmark_return),
                            excess_return=excess_return,
                        )
                    )
        finally:
            replay.close()

        stats = _compute_excess_return_stats(paired)
        overlap = _compute_overlap_diagnostics(paired, stats)
        clusters = _compute_cluster_diagnostics(paired)
        bootstrap = _compute_block_bootstrap(
            paired,
            iterations=self.config.bootstrap_iterations,
            block_size_days=self.config.bootstrap_block_days,
            seed=self.config.bootstrap_seed,
        )
        csv_path = self._write_csv(trades)
        return CompanySOTPBacktestReport(
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            hold_days=self.config.hold_days,
            top_n=self.config.top_n,
            benchmark_ticker=self.config.benchmark_ticker,
            min_ranked_sotp_discount=self.config.min_ranked_sotp_discount,
            n_snapshot_dates=len(snapshot_dates),
            n_candidate_rows=n_candidate_rows,
            n_selected_trades=len(trades),
            n_missing_price_trades=n_missing_price_trades,
            stats=stats,
            overlap=overlap,
            clusters=clusters,
            bootstrap=bootstrap,
            csv_path=csv_path,
            trades=trades,
            allowed_action_policies=_normalize_action_policies(self.config.allowed_action_policies),
        )

    def _select_rows(self, rows: list[dict]) -> list[dict]:
        eligible: list[dict] = []
        allowed_actions = set(_normalize_action_policies(self.config.allowed_action_policies))
        for row in rows:
            if self.config.require_recency_gate and not bool(
                row.get("balance_sheet_passes_recency_gate", False)
            ):
                continue
            if float(row.get("ranked_sotp_discount") or 0.0) < self.config.min_ranked_sotp_discount:
                continue
            action = str(row.get("action_policy") or "").lower()
            if allowed_actions and action not in allowed_actions:
                continue
            eligible.append(row)
        eligible.sort(
            key=lambda row: (
                -float(row.get("ranked_sotp_discount") or 0.0),
                str(row.get("ticker") or ""),
            )
        )
        return eligible

    def _write_csv(self, trades: list[CompanySOTPBacktestTrade]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        policy_suffix = ""
        normalized_policies = _normalize_action_policies(self.config.allowed_action_policies)
        if normalized_policies:
            policy_suffix = "_actions-" + "-".join(normalized_policies)
        out_path = self.output_dir / (
            f"company_sotp_backtest_{self.config.start_date.isoformat()}_"
            f"{self.config.end_date.isoformat()}_hold{self.config.hold_days}d_top{self.config.top_n}"
            f"{policy_suffix}.csv"
        )
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "snapshot_date",
                    "exit_date",
                    "ticker",
                    "company_id",
                    "ranked_sotp_discount",
                    "action_policy",
                    "company_return_pct",
                    "benchmark_return_pct",
                    "excess_return_pct",
                ],
            )
            writer.writeheader()
            for trade in trades:
                writer.writerow(
                    {
                        "snapshot_date": trade.snapshot_date.isoformat(),
                        "exit_date": trade.exit_date.isoformat(),
                        "ticker": trade.ticker,
                        "company_id": trade.company_id,
                        "ranked_sotp_discount": trade.ranked_sotp_discount,
                        "action_policy": trade.action_policy,
                        "company_return_pct": trade.company_return_pct,
                        "benchmark_return_pct": trade.benchmark_return_pct,
                        "excess_return_pct": trade.excess_return_pct,
                    }
                )
        return out_path


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def _lane_label(report: CompanySOTPBacktestReport) -> str:
    normalized = _normalize_action_policies(report.allowed_action_policies)
    return "/".join(normalized) if normalized else "all_actions"


def _render_report(report: CompanySOTPBacktestReport) -> str:
    lines = [
        "Company SOTP backtest complete",
        f"  Action policies: {_lane_label(report)}",
        f"  Date range: {report.start_date} -> {report.end_date}",
        f"  Hold days: {report.hold_days}",
        f"  Top N: {report.top_n}",
        f"  Snapshot dates: {report.n_snapshot_dates}",
        f"  Candidate rows: {report.n_candidate_rows}",
        f"  Selected trades: {report.n_selected_trades}",
        f"  Missing price trades: {report.n_missing_price_trades}",
        f"  Mean excess return: {report.stats.mean_excess_return}",
        f"  Precision proxy hit rate: {report.stats.hit_rate}",
        f"  Cluster count: {report.clusters.n_assets}",
        f"  Bootstrap p-value: {report.bootstrap.p_value}",
        f"  CSV: {report.csv_path}",
    ]
    return "\n".join(lines)


def _render_comparison(
    primary: CompanySOTPBacktestReport,
    comparator: CompanySOTPBacktestReport,
) -> str:
    lines = [
        "Company SOTP backtest comparison",
        f"  Primary lane: {_lane_label(primary)}",
        f"    Candidate rows: {primary.n_candidate_rows}",
        f"    Selected trades: {primary.n_selected_trades}",
        f"    Mean excess return: {primary.stats.mean_excess_return}",
        f"    Precision proxy hit rate: {primary.stats.hit_rate}",
        f"    Bootstrap p-value: {primary.bootstrap.p_value}",
        f"    CSV: {primary.csv_path}",
        f"  Comparator lane: {_lane_label(comparator)}",
        f"    Candidate rows: {comparator.n_candidate_rows}",
        f"    Selected trades: {comparator.n_selected_trades}",
        f"    Mean excess return: {comparator.stats.mean_excess_return}",
        f"    Precision proxy hit rate: {comparator.stats.hit_rate}",
        f"    Bootstrap p-value: {comparator.bootstrap.p_value}",
        f"    CSV: {comparator.csv_path}",
    ]
    return "\n".join(lines)


def _write_wave_log(
    report: CompanySOTPBacktestReport,
    wave_label: str,
    wave_log_path: Path,
    *,
    strict_report: Optional[CompanySOTPBacktestReport] = None,
) -> None:
    """Append a wave-tracking entry to the persistent wave log JSON.

    The log accumulates one record per backtest run so that pack improvement
    waves can be compared across sessions (Step 7 of the Company Pack Expansion
    Plan). Each entry captures the backtest-measurable metrics: candidate count,
    mean excess return, hit rate, cluster count, and bootstrap p-value.

    To also capture the action-policy distribution from the backfiller (% buy,
    % watch, % needs_manual_review), populate ``backfill_action_totals`` manually
    or by passing the backfiller output separately.
    """
    wave_log_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if wave_log_path.exists():
        try:
            existing = json.loads(wave_log_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []

    entry: dict = {
        "run_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wave_label": wave_label,
        "lane": _lane_label(report),
        "date_range": f"{report.start_date}/{report.end_date}",
        "hold_days": report.hold_days,
        "top_n": report.top_n,
        "n_snapshot_dates": report.n_snapshot_dates,
        "n_candidate_rows": report.n_candidate_rows,
        "n_selected_trades": report.n_selected_trades,
        "n_missing_price_trades": report.n_missing_price_trades,
        "mean_excess_return": report.stats.mean_excess_return,
        "hit_rate": report.stats.hit_rate,
        "cluster_count": report.clusters.n_assets,
        "bootstrap_p": report.bootstrap.p_value,
        "csv_path": str(report.csv_path),
        # Populated externally after a backfiller run; leave None until then.
        "backfill_action_totals": None,
    }
    if strict_report is not None:
        entry["strict_buy_watch_comparison"] = {
            "n_candidate_rows": strict_report.n_candidate_rows,
            "n_selected_trades": strict_report.n_selected_trades,
            "mean_excess_return": strict_report.stats.mean_excess_return,
            "hit_rate": strict_report.stats.hit_rate,
            "cluster_count": strict_report.clusters.n_assets,
            "bootstrap_p": strict_report.bootstrap.p_value,
        }

    existing.append(entry)
    wave_log_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"  Wave log updated: {wave_log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest stored company-level SOTP snapshots")
    parser.add_argument("--db", required=True, help="KnowledgeStore SQLite path")
    parser.add_argument("--replay-db", default=str(REPLAY_STORE_PATH))
    parser.add_argument("--start", required=True, help="YYYY-MM-DD start date")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD end date")
    parser.add_argument("--hold-days", type=int, default=365)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-ranked-discount", type=float, default=1.0)
    parser.add_argument(
        "--allowed-action-policy",
        action="append",
        dest="allowed_action_policies",
        help=(
            "Allow only these company action policies. Repeat the flag to include multiple "
            "values, e.g. --allowed-action-policy buy --allowed-action-policy watch. "
            "Defaults to buy + watch + needs_manual_review."
        ),
    )
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument(
        "--compare-to-strict-buy-watch",
        action="store_true",
        help=(
            "Also run the legacy strict lane limited to buy/watch and print a "
            "side-by-side comparison."
        ),
    )
    parser.add_argument(
        "--wave-label",
        default="",
        help=(
            "Short label describing what changed in this backtest wave, e.g. "
            "'anab_fulc_ocul_prta_rxrx'. Used for the wave log entry."
        ),
    )
    parser.add_argument(
        "--wave-log",
        default="",
        help=(
            "Path to a persistent JSON file that accumulates wave-tracking entries. "
            "When provided, the backtest results are appended after each run so that "
            "pack improvement waves can be compared across sessions (Step 7)."
        ),
    )
    args = parser.parse_args()

    store = KnowledgeStore(args.db)
    try:
        allowed_action_policies = tuple(
            args.allowed_action_policies or CompanySOTPBacktestConfig.allowed_action_policies
        )
        report = CompanySOTPBacktester(
            store,
            replay_db_path=args.replay_db,
            output_dir=args.output_dir,
            config=CompanySOTPBacktestConfig(
                start_date=_parse_date(args.start),
                end_date=_parse_date(args.end),
                hold_days=args.hold_days,
                top_n=args.top_n,
                min_ranked_sotp_discount=args.min_ranked_discount,
                allowed_action_policies=allowed_action_policies,
            ),
        ).run()
        strict_report = None
        if args.compare_to_strict_buy_watch:
            strict_report = CompanySOTPBacktester(
                store,
                replay_db_path=args.replay_db,
                output_dir=args.output_dir,
                config=CompanySOTPBacktestConfig(
                    start_date=_parse_date(args.start),
                    end_date=_parse_date(args.end),
                    hold_days=args.hold_days,
                    top_n=args.top_n,
                    min_ranked_sotp_discount=args.min_ranked_discount,
                    allowed_action_policies=("buy", "watch"),
                ),
            ).run()
    finally:
        store.close()
    print(_render_report(report))
    if strict_report is not None:
        print()
        print(_render_comparison(report, strict_report))
    if args.wave_log:
        _write_wave_log(
            report,
            wave_label=args.wave_label or "unlabeled",
            wave_log_path=Path(args.wave_log),
            strict_report=strict_report,
        )


if __name__ == "__main__":
    main()
