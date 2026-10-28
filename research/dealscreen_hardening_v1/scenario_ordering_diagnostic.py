"""Decompose a config's bull/base/bear rNPV into revenue and cost components.

Research diagnostic (read-only): it calls the same ``compute_rnpv_full`` entry point the
engine's scenarios use, with the same scenario shocks, and changes nothing. It exists to
explain why a scenario labelled "bear" can carry a higher rNPV than "base".

Usage: python research/dealscreen_hardening_v1/scenario_ordering_diagnostic.py CONFIG.yaml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bve.cli import run_asset as ra
from bve.models.rnpv_model import compute_rnpv_full
from bve.valuation.scenario import SCENARIO_BASE, SCENARIO_BEAR, SCENARIO_BULL


def _shock(asset, trials, market, s):
    r = max(0.01, asset.discount_rate + s.discount_rate_add)
    a = asset.model_copy(update={"discount_rate": r})
    m = market.model_copy(update={"net_price_per_patient_usd": (market.net_price_per_patient_usd or 1)
                                  * s.peak_sales_mult, "uptake_curve": None})
    t = [x.model_copy(update={"success_probability": min(0.99, x.success_probability * s.pos_mult),
                              "duration_years": max(0.5, x.duration_years + s.duration_add_years),
                              "cost_millions": x.cost_millions * s.cost_mult}) for x in trials]
    return a, t, m


def decompose(config_path: Path) -> dict:
    cfg = ra._load_config(config_path)
    asset, _company, trials, market = ra._build_objects(cfg)
    from bve.config.assumptions_loader import AssumptionsLoader

    # The engine's default when no CommercialPlan is set (ValuationEngine.run, "unset").
    loe = AssumptionsLoader.get().loe_erosion_profile(asset.modality.value)
    out = {}
    for s in (SCENARIO_BEAR, SCENARIO_BASE, SCENARIO_BULL):
        a, t, m = _shock(asset, trials, market, s)
        r = compute_rnpv_full(a, t, m, loe_profile=loe)
        # Value if the program reaches market: the same run with every remaining phase certain.
        certain = [x.model_copy(update={"success_probability": 0.99}) for x in t]
        c = compute_rnpv_full(a, certain, m, loe_profile=loe)
        out[s.label] = {
            "rnpv": round(r.rnpv_millions, 1),
            "cumulative_pos": round(r.cumulative_success_probability, 4),
            "prob_adj_revenue_pv": round(r.probability_adjusted_revenue_pv_millions, 1),
            "trial_costs_pv": round(r.trial_costs_pv_millions, 1),
            "peak_sales": round(r.peak_sales_millions, 1),
            "rnpv_if_every_phase_succeeds": round(c.rnpv_millions, 1),
        }
    return out


if __name__ == "__main__":
    print(json.dumps(decompose(Path(sys.argv[1])), indent=2))
