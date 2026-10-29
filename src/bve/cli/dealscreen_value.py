"""bve-dealscreen-value: PROTOTYPE valuation entry point that also accepts deal terms.

Why this exists: ``bve-asset`` cannot express deal terms, and an acquisition-versus-license
comparison needs ``DealEconomics``, which the engine accepts only programmatically (it is
what ``ValuationEngine.from_program`` sets).

What it does:
- parses the config with ``bve.cli.run_asset``'s own loader, validator and builders;
- constructs ``ValuationEngine`` exactly as ``bve-asset`` does;
- attaches an optional ``deal_economics:`` block in the same way ``from_program`` does;
- runs the unchanged engine and saves ``valuation.json`` through ``ValuationOutput.save_json``.

No formula, default, PoS calibration or assumption is changed here.

Status: PROTOTYPE, outside Lane 1 sign-off (CR-2026-10-26-dealscreen-mvp). Lane 1 quant +
clinical sign-off is required before any non-demonstration use. With no ``deal_economics``
block the result equals ``bve-asset`` on the same config (pinned by a test).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROTOTYPE_LABEL = "PROTOTYPE valuation path (DealScreen); Lane 1 quant + clinical sign-off pending"


#: Top-level keys the shared bve-asset loader reads, plus this command's deal block.
KNOWN_TOP_LEVEL_KEYS = frozenset({
    "_meta", "analyst_notes", "asset", "company", "competition", "decision_framing", "limitations",
    "market_model", "monte_carlo", "pos_adjusters", "sources", "strategic_takeout", "thesis_changers",
    "trial_design", "trials", "deal_economics",
})
#: Known misplacements and where the value belongs (cycle A1 F3).
MISPLACED_KEY_HINTS = {
    "discount_rate": "asset.discount_rate",
    "deal_options": "deal_economics (one deal per config)",
    "deal": "deal_economics",
    "market": "nothing (bve-asset also ignores a top-level market block; revenue inputs belong in market_model)",
}


#: market_model keys the shared bve-asset loader passes to MarketModel (run_asset._build_objects).
#: Anything else (e.g. compliance_rate, gross_to_net_rate, price_basis) is dropped by that loader.
KNOWN_MARKET_MODEL_KEYS = frozenset({
    "total_addressable_market_millions", "addressable_patients_annual", "net_price_per_patient_usd",
    "peak_penetration", "years_to_peak", "patent_life_years", "cogs_rate", "sgna_rate_launch",
    "sgna_rate_mature", "lines_of_therapy", "competition_model", "lifecycle_events", "commercial_inputs",
})
#: Disclosed on every DealScreen valuation display (cycle A4 J1).
def _compliance_default() -> float:
    from bve.models.market_model import MarketModel

    return float(MarketModel.model_fields["compliance_rate"].default)


COMPLIANCE_NOTE = (f"peak sales include a {_compliance_default():.2f} compliance factor (engine default; "
                   "not settable through the bve-asset loader)")


class ConfigKeyError(ValueError):
    """The config has top-level keys nothing reads; refusing beats silently using defaults."""


def check_top_level_keys(cfg: dict[str, Any]) -> None:
    unknown = sorted(set(cfg) - KNOWN_TOP_LEVEL_KEYS)
    if unknown:
        details = "; ".join(
            f"{k!r} is not read" + (f" (did you mean {MISPLACED_KEY_HINTS[k]}?)" if k in MISPLACED_KEY_HINTS else "")
            for k in unknown)
        raise ConfigKeyError(f"unknown top-level config key(s): {details}. Nothing was valued.")
    market = cfg.get("market_model") or {}
    dropped = sorted(set(market) - KNOWN_MARKET_MODEL_KEYS) if isinstance(market, dict) else []
    if dropped:
        raise ConfigKeyError(
            f"market_model key(s) {dropped} are not read by the bve-asset loader and would be silently "
            f"ignored (e.g. compliance stays at the 0.80 default). Nothing was valued.")


def build_deal_economics(block: dict[str, Any] | None):
    from bve.models.deal_economics import DealEconomics, Milestone

    if not block:
        return None
    milestones = [Milestone(**m) for m in block.get("milestones", [])]
    fields = {k: v for k, v in block.items() if k not in {"milestones", "label"}}
    return DealEconomics(milestones=milestones, **fields)


def run(config_path: Path, *, n_sims: int, seed: int):
    from bve.cli import run_asset as ra
    from bve.entities.trial import TrialPhase
    from bve.models.monte_carlo import MonteCarloParams, PhaseSuccessDistribution
    from bve.valuation.valuation_engine import ValuationEngine

    cfg = ra._load_config(config_path)
    check_top_level_keys(cfg)
    ra._validate_config(cfg, config_path)
    asset, company, trials, market_model = ra._build_objects(cfg)
    pos_adjusters, apply_pos = ra._build_pos_adjusters(cfg)
    design_adjusters, apply_design = ra._build_design_adjusters(cfg)
    mc_cfg = cfg.get("monte_carlo", {})
    phase_dists = [
        PhaseSuccessDistribution(
            phase=TrialPhase(key), mean=pd_cfg["mean"], equivalent_sample_size=pd_cfg.get("ess", 20)
        )
        for key in ("phase_1", "phase_2", "phase_3", "nda_bla")
        if (pd_cfg := mc_cfg.get("phase_distributions", {}).get(key))
    ]
    mc_params = MonteCarloParams(
        n_simulations=n_sims,
        random_seed=mc_cfg.get("random_seed", seed),
        peak_sales_cv=mc_cfg.get("peak_sales_cv", ra._MC_DEFAULTS.mc_peak_sales_cv),
        discount_rate_std=mc_cfg.get("discount_rate_std", ra._MC_DEFAULTS.mc_discount_rate_std),
        years_to_peak_std=mc_cfg.get("years_to_peak_std", ra._MC_DEFAULTS.mc_years_to_peak_std),
        phase_distributions=phase_dists,
        use_default_correlations=mc_cfg.get("use_default_correlations", True),
    )
    engine = ValuationEngine(
        asset, company, trials, market_model,
        pos_adjusters=pos_adjusters,
        design_adjusters=design_adjusters,
        mc_params=mc_params,
        apply_pos_model=apply_pos,
        apply_design_model=apply_design,
        analyst_notes=cfg.get("analyst_notes"),
        config_path=str(config_path.resolve()),
        limitations=cfg.get("limitations"),
        thesis_changers=cfg.get("thesis_changers"),
    )
    engine.sources = cfg.get("sources")
    deal = build_deal_economics(cfg.get("deal_economics"))
    if deal is not None:
        # The same attachment ValuationEngine.from_program performs.
        engine._deal_economics = deal
    return engine.run(), deal


def perspective_line(output: Any, deal: Any) -> str:
    """Whose value this is, and the discount rate actually used (cycle A1 F3b)."""
    rate = getattr(getattr(output, "rnpv", None), "discount_rate", None)
    rate_text = f"{rate:.1%}" if isinstance(rate, (int, float)) else "see valuation.json"
    if deal is None:
        view = "asset-holder rNPV with no deal terms (not a buyer's deal NPV)"
    else:
        terms = ", ".join(f"{k}={v}" for k, v in deal.model_dump(mode="json").items() if v not in (None, [], 0, 0.0))
        view = f"rNPV with deal terms applied ({terms or 'defaults'}); payable/receivable per DealEconomics fields"
    return f"Perspective: {view}. Discount rate used: {rate_text}; {COMPLIANCE_NOTE}. {PROTOTYPE_LABEL}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bve-dealscreen-value", description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-json", required=True, help="where to save valuation.json")
    parser.add_argument("--n-sims", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        return 1
    try:
        output, deal = run(config_path, n_sims=args.n_sims, seed=args.seed)
    except ConfigKeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    output.save_json(out)
    provenance = {
        "label": PROTOTYPE_LABEL,
        "config": str(config_path),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "deal_economics": deal.model_dump(mode="json") if deal is not None else None,
        "n_sims": args.n_sims,
        "seed": args.seed,
    }
    out.with_suffix(".provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True))
    s = output.summary_dict
    print(f"{s['asset_name']}: rNPV ${s['rnpv_millions']:,.1f}M "
          f"(bull {s['bull_rnpv']:,.1f} / base {s['base_rnpv']:,.1f} / bear {s['bear_rnpv']:,.1f}) -> {out}")
    print(perspective_line(output, deal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
