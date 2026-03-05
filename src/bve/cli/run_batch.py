"""
Batch runner: process multiple asset config files and aggregate outputs.

Usage
-----
    python -m bve.cli.run_batch --configs-dir configs/ --memo bd --charts
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="BVE: Batch asset valuation")
    parser.add_argument("--configs-dir", required=True, help="Directory containing asset YAML configs")
    parser.add_argument("--memo", choices=["bd", "vc", "hf"], default="bd")
    parser.add_argument("--charts", action="store_true")
    parser.add_argument("--out", default="memos")
    parser.add_argument("--n-sims", type=int, default=5_000)
    args = parser.parse_args()

    configs_dir = Path(args.configs_dir)
    configs = sorted(configs_dir.glob("*.yaml"))

    if not configs:
        print(f"No YAML configs found in {configs_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(configs)} config(s). Running batch valuation...")

    from bve.cli.run_asset import _load_config, _build_objects
    from bve.models.monte_carlo import MonteCarloParams
    from bve.valuation.valuation_engine import ValuationEngine
    from bve.reporting.export import export_full_package
    from bve.reporting.tables import valuation_summary_table
    import pandas as pd

    summaries = []
    mc_params = MonteCarloParams(n_simulations=args.n_sims)

    for cfg_path in configs:
        print(f"  Processing {cfg_path.name}...", end=" ")
        try:
            cfg = _load_config(cfg_path)
            asset, company, trials, market_model = _build_objects(cfg)
            engine = ValuationEngine(asset, company, trials, market_model, mc_params=mc_params)
            output = engine.run()
            export_full_package(output, memo_type=args.memo, output_dir=args.out, save_charts=args.charts)
            tbl = valuation_summary_table(output)
            summaries.append(tbl)
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")

    if summaries:
        combined = pd.concat(summaries, ignore_index=True)
        summary_path = Path(args.out) / "batch_summary.csv"
        combined.to_csv(summary_path, index=False)
        print(f"\nBatch summary saved: {summary_path}")
        print(combined.to_string(index=False))


if __name__ == "__main__":
    main()
