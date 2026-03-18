"""CLI for running snapshot-based portfolio backtests."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from bve.analysis.portfolio_backtest import (
    PortfolioBacktestConfig,
    PortfolioBacktester,
    PortfolioStrategy,
    SURVIVORSHIP_BIAS_WARNING,
)
from bve.intelligence.knowledge_layer import KnowledgeStore


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    return date.fromisoformat(raw)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run portfolio backtest from backtest_snapshots")
    p.add_argument(
        "--db", default="outputs/intelligence_phase2/knowledge.db", help="Knowledge DB path"
    )
    p.add_argument("--start-date", default=None, help="Inclusive start date (YYYY-MM-DD)")
    p.add_argument("--end-date", default=None, help="Inclusive end date (YYYY-MM-DD)")
    p.add_argument(
        "--strategy",
        default=PortfolioStrategy.TOP_N_EQUAL_WEIGHT.value,
        choices=[s.value for s in PortfolioStrategy],
    )
    p.add_argument("--n-holdings", type=int, default=5)
    p.add_argument("--rebalance-freq-days", type=int, default=30)
    p.add_argument("--benchmark", default="XBI")
    p.add_argument("--initial-capital", type=float, default=1_000_000)
    p.add_argument("--transaction-cost-bps", type=float, default=10)
    p.add_argument("--out", default=None, help="Optional JSON output path")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    cfg = PortfolioBacktestConfig(
        start_date=_parse_date(args.start_date),
        end_date=_parse_date(args.end_date),
        strategy=PortfolioStrategy(args.strategy),
        n_holdings=args.n_holdings,
        rebalance_freq_days=args.rebalance_freq_days,
        benchmark_ticker=args.benchmark,
        initial_capital=args.initial_capital,
        transaction_cost_bps=args.transaction_cost_bps,
    )

    store = KnowledgeStore(args.db)
    try:
        result = PortfolioBacktester(store, cfg).run()
    finally:
        store.close()

    print(SURVIVORSHIP_BIAS_WARNING)
    print("-" * 72)
    print(f"Signals: {result.n_signals}")
    print(f"Snapshot coverage: {result.snapshot_coverage_pct:.2f}%")
    print(f"Missing price positions: {result.missing_price_positions}")
    print(f"Assets excluded (missing prices): {result.assets_excluded_missing_prices}")
    if result.notes:
        print("Notes:")
        for note in result.notes:
            print(f"  - {note}")
    print(f"CAGR: {result.cagr:.2%}")
    print(f"Sharpe: {result.sharpe_ratio:.3f}")
    print(f"Sortino: {result.sortino_ratio:.3f}")
    print(f"Max drawdown: {result.max_drawdown:.2%}")
    print(f"Win rate: {result.win_rate:.2%}")
    print(f"Alpha vs benchmark: {result.alpha_vs_benchmark:.2%}")
    print(f"Beta vs benchmark: {result.beta_vs_benchmark:.3f}")
    print(f"Information ratio: {result.information_ratio:.3f}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(f"Wrote JSON: {out_path}")


if __name__ == "__main__":
    main()
