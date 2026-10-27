"""Hand analyst-selected finalists to BVE's valuation CLI and read back its saved output.

Boundary (ARCHITECTURE_BOUNDARIES: Lane 4 must not trigger valuation computation in
process):
- This module never imports ``ValuationEngine`` or any model.
- It writes a standard ``bve-asset`` YAML config, runs an authorised CLI as a subprocess, and
  loads the ``valuation.json`` that CLI saved.
- Every number shown downstream is read from that file.

Inputs:
- **Imported scientific facts** (name, company, indication) label the config.
- **Financial assumptions** come only from an analyst-owned assumptions file.
- Each required input missing from that file is listed, and the asset is NOT READY FOR
  VALUATION: nothing is defaulted from a drug's name, target or phase.
- Engine defaults that ``bve-asset`` already applies (COGS / SG&A rates when omitted) are
  allowed, but they are disclosed as defaults.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from bve.dealscreen.models import LandscapeAsset

#: (dotted key, description, unit). Every one must be present for a valuation.
REQUIRED_INPUTS: tuple[tuple[str, str, str], ...] = (
    ("therapeutic_area", "BVE therapeutic area for PoS base rates", "enum"),
    ("stage", "Current development stage (analyst-confirmed)", "enum"),
    ("modality", "BVE modality", "enum"),
    ("discount_rate", "Discount rate", "fraction"),
    ("market.addressable_patients_annual", "Addressable patients per year", "patients"),
    ("market.net_price_per_patient_usd", "Net price per patient-year", "USD"),
    ("market.peak_penetration", "Peak share of addressable patients", "fraction"),
    ("market.years_to_peak", "Years from launch to peak", "years"),
    ("market.patent_life_years", "Commercial / IP life from launch", "years"),
    ("trials", "Remaining development path: phase, success probability, duration, cost", "list"),
    ("ownership.royalty_rate", "Royalty already owed by the asset (0 if fully owned)", "fraction"),
)
OPTIONAL_WITH_ENGINE_DEFAULT = ("market.cogs_rate", "market.sgna_rate_launch", "market.sgna_rate_mature")
_TRIAL_KEYS = ("phase", "success_probability", "duration_years", "cost_millions")


def _get(data: dict[str, Any], dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@dataclass
class Readiness:
    asset_id: str
    ready: bool
    missing: list[str] = field(default_factory=list)
    defaults_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return "READY" if self.ready else "NOT READY FOR VALUATION"


def check_readiness(asset: LandscapeAsset, assumptions: dict[str, Any] | None) -> Readiness:
    if not assumptions:
        return Readiness(
            asset.asset_id, False,
            missing=[f"{key} ({desc}, {unit})" for key, desc, unit in REQUIRED_INPUTS],
        )
    missing = [
        f"{key} ({desc}, {unit})" for key, desc, unit in REQUIRED_INPUTS if _get(assumptions, key) is None
    ]
    trials = assumptions.get("trials") or []
    for i, trial in enumerate(trials):
        for key in _TRIAL_KEYS:
            if trial.get(key) is None:
                missing.append(f"trials[{i}].{key}")
    defaults = [key for key in OPTIONAL_WITH_ENGINE_DEFAULT if _get(assumptions, key) is None]
    return Readiness(asset.asset_id, not missing, missing=missing, defaults_used=defaults)


def build_config(
    asset: LandscapeAsset,
    assumptions: dict[str, Any],
    *,
    indication_label: str,
    deal: dict[str, Any] | None,
) -> dict[str, Any]:
    market = {k: v for k, v in assumptions["market"].items()}
    config: dict[str, Any] = {
        "analyst_notes": (
            f"DealScreen handoff for {asset.program_name} ({asset.source_system} "
            f"{asset.external_id}). Financial inputs: {assumptions.get('owner', 'analyst')} "
            f"[{assumptions.get('label', 'ANALYST_ASSUMPTIONS')}]."
        ),
        "asset": {
            "id": asset.asset_id.replace(":", "-"),
            "name": asset.program_name,
            "indication": indication_label,
            "therapeutic_area": assumptions["therapeutic_area"],
            "stage": assumptions["stage"],
            "modality": assumptions["modality"],
            "discount_rate": assumptions["discount_rate"],
            "royalty_rate": assumptions["ownership"]["royalty_rate"],
        },
        "company": {
            "id": "asset-level-valuation",
            "name": f"{asset.company or 'Unknown owner'} (asset-level; balance sheet not modelled)",
            "cash_millions": 0.0,
            "debt_millions": 0.0,
            "shares_outstanding_millions": 1.0,
        },
        "trials": [
            {k: t[k] for k in (*_TRIAL_KEYS, "nct_id", "endpoint_type") if k in t}
            for t in assumptions["trials"]
        ],
        "market_model": market,
        "pos_adjusters": {"apply_pos_model": False},
        "limitations": [
            "Hypothetical analyst-owned financial assumptions; not sourced facts.",
            "Company NAV fields are placeholders: this is an asset-level valuation.",
        ],
    }
    if deal:
        config["deal_economics"] = {k: v for k, v in deal.items() if k != "label"}
    return config


@dataclass
class ValuationRun:
    asset_id: str
    case: str  # standalone / acquisition / license
    config_path: str
    output_json: str
    command: list[str]
    summary: dict[str, Any]
    prototype: bool


def run_valuation(
    config: dict[str, Any], workdir: Path, *, case: str, n_sims: int, seed: int,
    asset_id: str,
) -> ValuationRun:
    """Run one config through an authorised CLI in a subprocess and read its output."""
    workdir.mkdir(parents=True, exist_ok=True)
    config_path = workdir / f"{case}.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    output_json = workdir / f"{case}_valuation.json"
    prototype = "deal_economics" in config
    if prototype:
        command = [sys.executable, "-m", "bve.cli.dealscreen_value", "--config", str(config_path),
                   "--output-json", str(output_json), "--n-sims", str(n_sims), "--seed", str(seed)]
    else:
        out_base = workdir / f"{case}_bve_asset"
        command = [sys.executable, "-m", "bve.cli.run_asset", "--config", str(config_path),
                   "--out", str(out_base), "--n-sims", str(n_sims), "--seed", str(seed)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"valuation CLI failed for {asset_id} ({case}): {completed.stderr.strip()[-2000:]}"
        )
    if not prototype:
        produced = next((workdir / f"{case}_bve_asset").glob("*/valuation.json"))
        output_json.write_bytes(produced.read_bytes())
    return ValuationRun(
        asset_id=asset_id, case=case, config_path=str(config_path), output_json=str(output_json),
        command=command, summary=read_summary(output_json), prototype=prototype,
    )


def read_summary(path: str | Path) -> dict[str, Any]:
    """Pull the reported numbers straight from a saved ValuationOutput JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    outputs = data["outputs"]
    rnpv = outputs["rnpv"]
    scenarios = outputs["scenarios"]
    mc = outputs.get("monte_carlo") or {}
    percentiles = mc.get("percentiles") or {}
    return {
        "rnpv_millions": rnpv["rnpv_millions"],
        "peak_sales_millions": rnpv.get("peak_sales_millions"),
        "cumulative_success_probability": rnpv.get("cumulative_success_probability"),
        "years_to_launch": rnpv.get("years_to_launch"),
        "bull_rnpv_millions": scenarios["bull"]["rnpv_millions"],
        "base_rnpv_millions": scenarios["base"]["rnpv_millions"],
        "bear_rnpv_millions": scenarios["bear"]["rnpv_millions"],
        "mc_mean_millions": mc.get("mean_millions"),
        "mc_p10_millions": percentiles.get("p10"),
        "mc_p90_millions": percentiles.get("p90"),
        "mc_probability_positive": mc.get("probability_positive"),
        "analysis_date": data.get("meta", {}).get("analysis_date"),
        "git_commit": data.get("meta", {}).get("git_commit"),
    }
