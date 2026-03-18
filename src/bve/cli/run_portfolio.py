"""
CLI entry point: run a company-level portfolio valuation from a portfolio YAML config.

Usage
-----
    bve-portfolio --config examples/configs/relay_portfolio.yaml

Portfolio YAML format
---------------------
    company:
      id: "relay-therapeutics"
      name: "Relay Therapeutics"
      ticker: "RLAY"
      cash_millions: 410.0
      debt_millions: 0.0
      shares_outstanding_millions: 93.5
      burn_rate_millions_per_quarter: 35.0
      current_price: 5.80

    assets:
      - config: "examples/configs/relay_rly2608.yaml"
      - config: "examples/configs/relay_rly4008.yaml"

    dilution_scenarios:               # optional
      - label: "Phase 3 equity raise ($150M at current price)"
        additional_shares_millions: 25.9   # $150M / $5.80
        proceeds_millions: 150.0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _build_company(cfg: dict):
    from bve.entities.company import Company
    c = cfg["company"]
    return Company(
        id=c["id"],
        name=c["name"],
        ticker=c.get("ticker"),
        cash_millions=c["cash_millions"],
        debt_millions=c.get("debt_millions", 0.0),
        shares_outstanding_millions=c["shares_outstanding_millions"],
        burn_rate_millions_per_quarter=c.get("burn_rate_millions_per_quarter"),
        current_price=c.get("current_price"),
    )


def main():
    parser = argparse.ArgumentParser(description="BVE: Run company-level portfolio valuation")
    parser.add_argument("--config", required=True, help="Path to portfolio YAML config")
    parser.add_argument("--out", default="outputs", help="Base output directory (default: outputs/)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-sims", type=int, default=10_000)
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"ERROR: Config not found: {cfg_path}", file=sys.stderr)
        sys.exit(1)

    cfg = _load_yaml(cfg_path)

    if "company" not in cfg:
        print("ERROR: Portfolio config must have a 'company:' section.", file=sys.stderr)
        sys.exit(1)
    if "assets" not in cfg or not cfg["assets"]:
        print("ERROR: Portfolio config must list at least one asset under 'assets:'.", file=sys.stderr)
        sys.exit(1)

    company = _build_company(cfg)
    print(f"\nPortfolio: {company.name} ({company.ticker or '—'})")
    print(f"  Config:  {cfg_path}")
    print(f"  Assets:  {len(cfg['assets'])}")

    # Run each asset valuation
    from bve.cli.run_asset import _load_config, _validate_config, _build_objects, _build_pos_adjusters
    from bve.models.monte_carlo import MonteCarloParams, PhaseSuccessDistribution
    from bve.entities.trial import TrialPhase
    from bve.valuation.valuation_engine import ValuationEngine

    asset_outputs = []
    for entry in cfg["assets"]:
        asset_cfg_path = Path(entry["config"])
        if not asset_cfg_path.is_absolute():
            asset_cfg_path = cfg_path.parent / asset_cfg_path
        if not asset_cfg_path.exists():
            print(f"  WARNING: Asset config not found: {asset_cfg_path} — skipping", file=sys.stderr)
            continue

        asset_cfg = _load_config(asset_cfg_path)
        _validate_config(asset_cfg, asset_cfg_path)
        asset, _, trials, market_model = _build_objects(asset_cfg)
        pos_adjusters, apply_pos = _build_pos_adjusters(asset_cfg)

        mc_cfg = asset_cfg.get("monte_carlo", {})
        phase_dists = []
        for phase_key in ("phase_1", "phase_2", "phase_3", "nda_bla"):
            pd_cfg = mc_cfg.get("phase_distributions", {}).get(phase_key)
            if pd_cfg:
                phase_dists.append(PhaseSuccessDistribution(
                    phase=TrialPhase(phase_key),
                    mean=pd_cfg["mean"],
                    equivalent_sample_size=pd_cfg.get("ess", 20),
                ))

        mc_params = MonteCarloParams(
            n_simulations=args.n_sims,
            random_seed=mc_cfg.get("random_seed", args.seed),
            peak_sales_cv=mc_cfg.get("peak_sales_cv", 0.35),
            discount_rate_std=mc_cfg.get("discount_rate_std", 0.02),
            years_to_peak_std=mc_cfg.get("years_to_peak_std", 1.5),
            phase_distributions=phase_dists,
            use_default_correlations=mc_cfg.get("use_default_correlations", True),
        )

        engine = ValuationEngine(
            asset, company, trials, market_model,
            pos_adjusters=pos_adjusters,
            mc_params=mc_params,
            apply_pos_model=apply_pos,
            analyst_notes=asset_cfg.get("analyst_notes"),
            config_path=str(asset_cfg_path.resolve()),
            limitations=asset_cfg.get("limitations"),
            thesis_changers=asset_cfg.get("thesis_changers"),
        )
        engine.sources = asset_cfg.get("sources")

        print(f"  Running: {asset.name} ...", end=" ", flush=True)
        output = engine.run()
        asset_outputs.append(output)
        print(f"rNPV ${output.rnpv.rnpv_millions:,.0f}M  P(approval) {output.rnpv.cumulative_success_probability:.1%}")

    if not asset_outputs:
        print("ERROR: No asset valuations completed.", file=sys.stderr)
        sys.exit(1)

    # Build portfolio valuation
    from bve.valuation.portfolio import run_portfolio_valuation, DilutionScenario

    dilution_scenarios = []
    for ds in cfg.get("dilution_scenarios", []):
        dilution_scenarios.append(DilutionScenario(
            label=ds["label"],
            additional_shares_millions=ds["additional_shares_millions"],
            proceeds_millions=ds["proceeds_millions"],
        ))

    portfolio = run_portfolio_valuation(company, asset_outputs, dilution_scenarios)

    # Console output
    print(portfolio.summary())
    if portfolio.dilution_scenarios:
        print("\nDilution Analysis:")
        print(f"  {'Scenario':<45} {'NAV/Share':>10} {'Impact':>10}")
        print(f"  {'  Base (no dilution)':<45} ${portfolio.nav_per_share:>8.2f}  {'—':>10}")
        for scenario in portfolio.dilution_scenarios:
            result = portfolio.nav_under_dilution(scenario)
            print(f"  {('  ' + result['label']):<45} ${result['diluted_nav_per_share']:>8.2f}  ${result['nav_per_share_impact']:>+8.2f}")

    # Save outputs
    ticker = company.ticker or company.id.upper()
    out_dir = Path(args.out) / ticker.upper()
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "portfolio_valuation.json"
    with open(json_path, "w") as f:
        json.dump(portfolio.to_dict(), f, indent=2, default=str)

    print(f"\nOutputs -> {out_dir}/")
    print("  portfolio_valuation.json")


if __name__ == "__main__":
    main()
