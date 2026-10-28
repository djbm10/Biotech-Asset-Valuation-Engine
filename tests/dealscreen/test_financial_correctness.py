"""Financial-correctness regressions found in the DealScreen hardening audit (2026-10-27).

1. RLAY: every config with ``trial_design.apply_design_model: true`` crashed in the
   ``bve-asset`` console summary (renamed fields), and legacy per-phase keys were
   silently ignored, so phases were valued with the rct_double_blind defaults. The CLI now
   prints current fields and refuses keys the design builder does not read.
2. Selimab: bear rNPV above base is a property of a cost-dominated program, not an engine
   error. DealScreen explains it from the saved output, and blocks any ordering it cannot
   explain.
3. The PROTOTYPE deal-terms path reconciles with the engine's own compute path.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from bve.dealscreen.valuation_handoff import (
    EXPLAINED_COST_DOMINATED,
    ORDERED,
    UNEXPLAINED,
    scenario_check,
)

ROOT = Path(__file__).resolve().parents[2]
RLAY = ROOT / "examples" / "configs" / "relay_rly2608.yaml"

#: The synthetic Selimab handoff config (hypothetical inputs), as DealScreen wrote it.
SELIMAB = {
    "asset": {"id": "selimab", "name": "Selimab", "indication": "Crohn's disease",
              "therapeutic_area": "immunology", "stage": "phase_2", "modality": "biologic",
              "discount_rate": 0.10, "royalty_rate": 0.0},
    "company": {"id": "asset-level", "name": "asset-level", "cash_millions": 0.0, "debt_millions": 0.0,
                "shares_outstanding_millions": 1.0},
    "trials": [
        {"phase": "phase_2", "success_probability": 0.40, "duration_years": 2.0, "cost_millions": 70},
        {"phase": "phase_3", "success_probability": 0.60, "duration_years": 3.0, "cost_millions": 260},
        {"phase": "nda_bla", "success_probability": 0.90, "duration_years": 1.0, "cost_millions": 25},
    ],
    "market_model": {"addressable_patients_annual": 4000, "net_price_per_patient_usd": 90000,
                     "peak_penetration": 0.15, "years_to_peak": 6, "patent_life_years": 12,
                     "cogs_rate": 0.12, "sgna_rate_launch": 0.40, "sgna_rate_mature": 0.22},
    "pos_adjusters": {"apply_pos_model": False},
}


def _write(tmp_path: Path, cfg: dict, name: str = "cfg.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return path


def _run_asset(monkeypatch, config: Path, out: Path) -> None:
    from bve.cli import run_asset

    monkeypatch.setattr("sys.argv", ["bve-asset", "--config", str(config), "--out", str(out),
                                     "--n-sims", "200"])
    run_asset.main()


# -- 1. RLAY trial-design layer ---------------------------------------------------------
def test_rlay_legacy_design_keys_fail_closed_with_a_clear_message(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_asset(monkeypatch, RLAY, tmp_path)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "does not read" in err and "evidence_design" in err and "approval_pathway" in err


def test_design_layer_with_current_keys_runs_and_prints_its_settings(monkeypatch, tmp_path, capsys):
    cfg = copy.deepcopy(SELIMAB)
    cfg["trial_design"] = {"apply_design_model": True,
                           "phase_2": {"evidence_design_quality": "single_arm_objective",
                                       "comparator_fit": "no_valid_comparator",
                                       "regulatory_pathway_risk": "accelerated_validated_surrogate"}}
    _run_asset(monkeypatch, _write(tmp_path, cfg), tmp_path / "out")
    out = capsys.readouterr().out
    assert "phase_2: single_arm_objective/no_valid_comparator/accelerated_validated_surrogate" in out
    assert (tmp_path / "out" / "SELIMAB" / "valuation.json").exists()


def test_proposed_rlay_migration_patch_applies_and_validates(tmp_path):
    import subprocess

    from bve.cli import run_asset as ra

    patch = ROOT / "docs" / "change_requests" / "proposed" / "rlay_trial_design_migration.patch"
    check = subprocess.run(["git", "apply", "--check", str(patch)], cwd=ROOT, capture_output=True,
                           check=False)
    assert check.returncode == 0, check.stderr
    # Not applied: the committed config still carries the legacy keys (Lane 1 sign-off pending).
    assert "evidence_design:" in RLAY.read_text()
    work = tmp_path / "repo"
    (work / "examples" / "configs").mkdir(parents=True)
    (work / "examples" / "configs" / "relay_rly2608.yaml").write_text(RLAY.read_text())
    subprocess.run(["git", "apply", str(patch)], cwd=work, check=True)
    migrated = yaml.safe_load((work / "examples" / "configs" / "relay_rly2608.yaml").read_text())
    ra._validate_config(migrated, Path("migrated.yaml"))  # no SystemExit


# -- 2. scenario ordering ---------------------------------------------------------------
@pytest.fixture(scope="module")
def selimab_output(tmp_path_factory):
    from bve.cli.dealscreen_value import run

    path = _write(tmp_path_factory.mktemp("selimab"), SELIMAB)
    output, _ = run(path, n_sims=200, seed=42)
    return output


def test_selimab_bear_above_base_is_reproduced_and_explained(selimab_output):
    s = selimab_output.scenarios
    assert s.bear.rnpv_millions > s.base.rnpv_millions  # the documented anomaly, reproduced
    r = selimab_output.rnpv
    # Cost-dominated: probability-adjusted revenue does not cover development cost.
    assert r.probability_adjusted_revenue_pv_millions < r.trial_costs_pv_millions
    summary = {"bear_rnpv_millions": s.bear.rnpv_millions, "base_rnpv_millions": s.base.rnpv_millions,
               "bull_rnpv_millions": s.bull.rnpv_millions,
               "prob_adj_revenue_pv_millions": r.probability_adjusted_revenue_pv_millions,
               "trial_costs_pv_millions": r.trial_costs_pv_millions}
    check = scenario_check(summary)
    assert check["status"] == EXPLAINED_COST_DOMINATED and check["reliable"]
    assert "not a computation error" in check["explanation"]


def test_scenario_mechanism_bear_lowers_expected_cost_more_than_revenue():
    """The engine's own scenario shocks, decomposed: the cost term falls more than revenue."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "diag", ROOT / "research" / "dealscreen_hardening_v1" / "scenario_ordering_diagnostic.py")
    assert spec and spec.loader
    diag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diag)
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        parts = diag.decompose(_write(Path(d), SELIMAB))
    bear, base = parts["Bear"], parts["Base"]
    cost_drop = base["trial_costs_pv"] - bear["trial_costs_pv"]
    revenue_drop = base["prob_adj_revenue_pv"] - bear["prob_adj_revenue_pv"]
    assert cost_drop > revenue_drop > 0
    assert base["rnpv_if_every_phase_succeeds"] < 0  # loses money even if it succeeds


def test_ordered_and_unexplained_cases():
    ordered = {"bear_rnpv_millions": -10, "base_rnpv_millions": 5, "bull_rnpv_millions": 50}
    assert scenario_check(ordered)["status"] == ORDERED
    odd = {"bear_rnpv_millions": 80, "base_rnpv_millions": 40, "bull_rnpv_millions": 90,
           "prob_adj_revenue_pv_millions": 300, "trial_costs_pv_millions": 100}
    check = scenario_check(odd)
    assert check["status"] == UNEXPLAINED and not check["reliable"]


# -- 3. PROTOTYPE deal path reconciles with the engine ----------------------------------
def test_prototype_deal_path_reconciles_with_engine_compute(tmp_path):
    from bve.cli import run_asset as ra
    from bve.cli.dealscreen_value import build_deal_economics, run
    from bve.config.assumptions_loader import AssumptionsLoader
    from bve.models.rnpv_model import compute_rnpv_full

    deal_block = {"upfront_cost_millions": 150, "royalty_rate": 0.12,
                  "milestones": [{"description": "Approval", "amount_millions": 200,
                                  "trigger": "approval", "direction": "payable"}]}
    cfg = copy.deepcopy(SELIMAB)
    cfg["deal_economics"] = deal_block
    path = _write(tmp_path, cfg)
    output, _ = run(path, n_sims=200, seed=1)
    asset, _c, trials, market = ra._build_objects(ra._load_config(path))
    loe = AssumptionsLoader.get().loe_erosion_profile(asset.modality.value)
    direct = compute_rnpv_full(asset, trials, market, loe_profile=loe,
                               deal=build_deal_economics(deal_block))
    assert output.rnpv.rnpv_millions == direct.rnpv_millions


def test_upfront_only_deal_shifts_rnpv_by_exactly_the_upfront(tmp_path):
    from bve.cli.dealscreen_value import run

    plain, _ = run(_write(tmp_path, SELIMAB, "plain.yaml"), n_sims=200, seed=1)
    cfg = copy.deepcopy(SELIMAB)
    cfg["deal_economics"] = {"upfront_cost_millions": 100.0}
    paid, _ = run(_write(tmp_path, cfg, "paid.yaml"), n_sims=200, seed=1)
    assert abs((plain.rnpv.rnpv_millions - paid.rnpv.rnpv_millions) - 100.0) <= 1.0  # engine rounds to $1M
