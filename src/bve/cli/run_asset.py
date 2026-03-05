"""
CLI entry point: run a full valuation for a single asset defined in a YAML config file.

Usage
-----
    bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts
    bve-asset --config examples/configs/xyz101.yaml --memo hf --charts --all-memos
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def _load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _build_objects(cfg: dict):
    """Parse config dict → Asset, Company, trials, MarketModel."""
    from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality, Catalyst
    from bve.entities.company import Company
    from bve.entities.trial import ClinicalTrial, TrialPhase, EndpointType
    from bve.models.market_model import MarketModel

    a = cfg["asset"]
    asset = Asset(
        id=a["id"],
        name=a["name"],
        indication=a["indication"],
        therapeutic_area=TherapeuticArea(a["therapeutic_area"]),
        stage=DevelopmentStage(a["stage"]),
        modality=Modality(a.get("modality", "small_molecule")),
        mechanism_of_action=a.get("mechanism_of_action"),
        discount_rate=a.get("discount_rate", 0.10),
        royalty_rate=a.get("royalty_rate", 0.0),
        upcoming_catalysts=[Catalyst(**c) for c in a.get("upcoming_catalysts", [])],
        competitor_assets=a.get("competitor_assets", []),
        differentiation_notes=a.get("differentiation_notes"),
        notes=a.get("notes"),
    )

    c = cfg["company"]
    company = Company(
        id=c["id"],
        name=c["name"],
        ticker=c.get("ticker"),
        cash_millions=c["cash_millions"],
        debt_millions=c.get("debt_millions", 0.0),
        shares_outstanding_millions=c["shares_outstanding_millions"],
        burn_rate_millions_per_quarter=c.get("burn_rate_millions_per_quarter"),
        current_price=c.get("current_price"),
        asset_ids=[asset.id],
        notes=c.get("notes"),
    )

    trials = []
    for t in cfg.get("trials", []):
        trials.append(ClinicalTrial(
            asset_id=asset.id,
            phase=TrialPhase(t["phase"]),
            nct_id=t.get("nct_id"),
            success_probability=t["success_probability"],
            duration_years=t["duration_years"],
            cost_millions=t["cost_millions"],
            enrollment=t.get("enrollment"),
            primary_endpoint=t.get("primary_endpoint"),
            endpoint_type=EndpointType(t.get("endpoint_type", "surrogate_validated")),
            notes=t.get("notes"),
        ))

    m = cfg["market_model"]
    market_model = MarketModel(
        asset_id=asset.id,
        total_addressable_market_millions=m.get("total_addressable_market_millions"),
        addressable_patients_annual=m.get("addressable_patients_annual"),
        net_price_per_patient_usd=m.get("net_price_per_patient_usd"),
        peak_penetration=m["peak_penetration"],
        years_to_peak=m.get("years_to_peak", 5),
        patent_life_years=m.get("patent_life_years", 12),
        cogs_rate=m.get("cogs_rate", 0.18),
        sgna_rate_launch=m.get("sgna_rate_launch", 0.40),
        sgna_rate_mature=m.get("sgna_rate_mature", 0.20),
    )

    return asset, company, trials, market_model


def _build_pos_adjusters(cfg: dict):
    """Parse optional pos_adjusters section from config."""
    from bve.entities.trial import TrialPhase
    from bve.models.pos_model import (
        POSAdjusters, CompetitivePressure, MoAPrecedent, SafetyProfile, SampleSizeAdequacy
    )
    from bve.entities.trial import EndpointType

    pos_cfg = cfg.get("pos_adjusters", {})
    if not pos_cfg.get("apply_pos_model", False):
        return None, False

    phase_map = {
        "phase_1": TrialPhase.PHASE_1,
        "phase_2": TrialPhase.PHASE_2,
        "phase_3": TrialPhase.PHASE_3,
        "nda_bla": TrialPhase.NDA_BLA,
    }

    adjusters = {}
    for phase_key, phase_enum in phase_map.items():
        phase_cfg = pos_cfg.get(phase_key)
        if phase_cfg is None:
            continue
        adjusters[phase_enum] = POSAdjusters(
            endpoint_type=EndpointType(phase_cfg.get("endpoint_type", "surrogate_validated")),
            moa_precedent=MoAPrecedent(phase_cfg.get("moa_precedent", "partial")),
            sample_size_adequacy=SampleSizeAdequacy(phase_cfg.get("sample_size_adequacy", "adequate")),
            safety_profile=SafetyProfile(phase_cfg.get("safety_profile", "minor")),
            competitive_pressure=CompetitivePressure(phase_cfg.get("competitive_pressure", "moderate")),
            biomarker_selected_population=phase_cfg.get("biomarker_selected_population", False),
            strong_prior_phase_data=phase_cfg.get("strong_prior_phase_data", False),
            has_breakthrough_designation=phase_cfg.get("has_breakthrough_designation", False),
        )

    return adjusters, True


def _output_dir(cfg: dict, base: str) -> Path:
    """Derive output directory: outputs/<ticker_or_asset_name>/"""
    ticker = cfg.get("company", {}).get("ticker") or cfg.get("asset", {}).get("id", "asset")
    return Path(base) / ticker.upper()


def main():
    parser = argparse.ArgumentParser(description="BVE: Run single-asset valuation")
    parser.add_argument("--config", required=True, help="Path to asset YAML config")
    parser.add_argument("--memo", choices=["bd", "vc", "hf"], default="bd")
    parser.add_argument("--all-memos", action="store_true", help="Generate all three memo types")
    parser.add_argument("--charts", action="store_true", help="Save charts")
    parser.add_argument("--out", default="outputs", help="Base output directory (default: outputs/)")
    parser.add_argument("--n-sims", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"ERROR: Config file not found: {cfg_path}", file=sys.stderr)
        sys.exit(1)

    cfg = _load_config(cfg_path)
    asset, company, trials, market_model = _build_objects(cfg)
    pos_adjusters, apply_pos = _build_pos_adjusters(cfg)

    from bve.models.monte_carlo import MonteCarloParams, PhaseSuccessDistribution
    from bve.entities.trial import TrialPhase
    from bve.valuation.valuation_engine import ValuationEngine
    from bve.reporting.export import export_full_package
    from bve.reporting.memo_generator import save_memo

    # Build MC params — allow per-phase distributions from config
    mc_cfg = cfg.get("monte_carlo", {})
    phase_dists = []
    for phase_key, mean_key in [("phase_1", None), ("phase_2", None), ("phase_3", None), ("nda_bla", None)]:
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
        analyst_notes=cfg.get("analyst_notes"),
        config_path=str(cfg_path.resolve()),
        limitations=cfg.get("limitations"),
        thesis_changers=cfg.get("thesis_changers"),
    )

    print(f"\nRunning valuation: {asset.name} ({company.ticker or company.name})")
    print(f"  Config:    {cfg_path}")
    print(f"  POS model: {'enabled' if apply_pos else 'using YAML point estimates'}")
    print(f"  MC sims:   {args.n_sims:,}")
    output = engine.run()

    # --- Console summary ---
    d = output.summary_dict
    print(f"\n{'═'*58}")
    print(f"  {asset.name} | {asset.indication}")
    print(f"  {company.name} ({company.ticker or '—'})")
    print(f"{'═'*58}")
    print(f"  {'rNPV':<34} ${d['rnpv_millions']:>10,.1f}M")
    print(f"  {'P(Approval)':<34} {d['prob_approval_pct']:>11}")
    print(f"  {'Peak Sales (base)':<34} ${d['peak_sales_millions']:>10,.0f}M")
    print(f"  {'Years to Launch':<34} {d['years_to_launch']:>11.1f} yrs")
    print(f"  {'Net Cash':<34} ${d['net_cash_millions']:>10,.0f}M")
    print(f"  {'NAV/Share':<34} ${d['nav_per_share']:>10.2f}")
    if d["current_price"]:
        print(f"  {'Current Price':<34} ${d['current_price']:>10.2f}")
        upside = d["implied_upside_pct"]
        direction = "upside" if upside and upside > 0 else "downside"
        print(f"  {'Implied vs NAV':<34} {abs(upside or 0):>10.0f}% {direction}")
    print(f"{'─'*58}")
    print(f"  {'MC Mean':<34} ${d['mc_mean']:>10,.0f}M")
    print(f"  {'MC P10 – P90':<34}   ${d['mc_p10']:>7,.0f}M – ${d['mc_p90']:,.0f}M")
    print(f"  {'Scenarios Bull / Base / Bear':<34}   "
          f"${d['bull_rnpv']:,.0f} / ${d['base_rnpv']:,.0f} / ${d['bear_rnpv']:,.0f}M")
    print(f"{'═'*58}")

    # --- Save outputs ---
    out_dir = _output_dir(cfg, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}

    # JSON
    json_path = output.save_json(out_dir / "valuation.json")
    artifacts["valuation.json"] = str(json_path)

    # Memos
    memo_types = ["bd", "vc", "hf"] if args.all_memos else [args.memo]
    for mt in memo_types:
        from bve.reporting.memo_generator import generate_memo
        from bve.reporting.export import markdown_to_docx
        md = generate_memo(output, memo_type=mt)
        md_path = out_dir / f"{mt}_memo.md"
        md_path.write_text(md, encoding="utf-8")
        artifacts[f"{mt}_memo.md"] = str(md_path)
        try:
            docx_path = out_dir / f"{mt}_memo.docx"
            markdown_to_docx(md, docx_path, title=f"{asset.name} — {mt.upper()} Memo")
            artifacts[f"{mt}_memo.docx"] = str(docx_path)
        except Exception as e:
            artifacts[f"{mt}_memo.docx"] = f"ERROR: {e}"

    # Charts
    if args.charts:
        from bve.reporting.charts import save_all_charts
        chart_dir = out_dir / "charts"
        chart_paths = save_all_charts(output, str(chart_dir))
        for k, v in chart_paths.items():
            artifacts[f"chart_{k}"] = v

    print(f"\nOutputs → {out_dir}/")
    for k, v in artifacts.items():
        rel = Path(v).relative_to(Path(args.out)) if Path(v).exists() else Path(v)
        print(f"  {k:<28} {rel}")


if __name__ == "__main__":
    main()
