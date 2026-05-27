"""Block 12 — init_asset workflow.

Scaffolds the minimum file set needed to add a new biotech company to the BVE
tracking universe.  Creates a directory tree under ``configs/<TICKER>/`` and
``outputs/<TICKER>/`` containing commented YAML templates for:

  1. asset_profile.yaml          — asset identity, indication, modality
  2. valuation_config.yaml       — valuation parameters (PoS, revenue, cost)
  3. management_quality.json     — management quality placeholder
  4. ma_target_profile.yaml      — M&A target profile placeholder
  5. acquirer_mapping.yaml       — buyer-side acquirer mapping placeholder
  6. financial_snapshot.json     — financial snapshot placeholder
  7. trial_records.yaml          — clinical trial records placeholder

All files are comment-annotated so a BD analyst can fill them out quickly.
Existing files are NEVER overwritten (safe to re-run).

Usage (Python)
--------------
    from bve.workflows.init_asset import init_asset
    paths = init_asset("SRPT")
    for p in paths:
        print(p)

Usage (CLI)
-----------
    bve-init-asset --ticker SRPT
    bve-init-asset --ticker SRPT --configs-dir my_configs/
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Template content
# ---------------------------------------------------------------------------

_ASSET_PROFILE_YAML = """\
# Asset profile for {ticker}
# Fill in the fields below and run: bve-asset --config configs/{ticker}/asset_profile.yaml

ticker: {ticker}
company_name: "{ticker} Therapeutics"   # Replace with full company name
asset_name: ""                           # Lead program name (e.g. "RLY-2608")
asset_id: "{ticker_lower}_lead"         # Unique asset ID (lowercase, snake_case)
modality: small_molecule                 # small_molecule | biologic | gene_therapy | cell_therapy | other
therapeutic_area: oncology               # oncology | immunology | neurology | cardiology | rare | other
indication: ""                           # Primary indication (e.g. "HR+/HER2- Breast Cancer")
mechanism_of_action: ""                  # Brief MoA (e.g. "PI3Kalpha H1047R-selective inhibitor")
highest_phase: phase2                    # phase1 | phase2 | phase3 | approved
lead_nct_id: ""                          # ClinicalTrials.gov NCT ID (e.g. "NCT05216432")

# Company financials (approximate; update from latest 10-Q)
cash_millions: 0.0                       # Cash + equivalents + short-term investments
shares_outstanding_millions: 0.0         # Diluted shares outstanding
stock_price: 0.0                         # Current stock price (USD)

analyst_notes: >
  Add your thesis, variant perception, or key diligence notes here.
"""

_VALUATION_CONFIG_YAML = """\
# Valuation configuration for {ticker} / {ticker} lead program
# Reference: docs/valuation_config_schema.md

asset:
  id: "{ticker_lower}_lead"
  name: ""                               # Program name
  royalty_rate: 0.0                      # If partnered, royalty paid out

company:
  name: "{ticker} Therapeutics"
  cash_millions: 0.0
  net_debt_millions: 0.0
  shares_outstanding_millions: 0.0

trials:
  - asset_id: "{ticker_lower}_lead"
    phase: phase2
    name: "Phase 2 {ticker}"
    start_year: {year}
    duration_years: 3.0
    cost_millions: 40.0
    nct_id: ""

market_model:
  asset_id: "{ticker_lower}_lead"
  addressable_patients_annual: 50000
  net_price_per_patient_usd: 80000
  peak_penetration: 0.10
  years_to_peak: 5
  patent_life_years: 10
  cogs_rate: 0.15
  sgna_rate_launch: 0.40
  sgna_rate_mature: 0.20

pos_adjusters:
  # Layer 1 PoS adjusters — set only the factors you want to override
  # phase2:
  #   endpoint_type: primary_surrogate    # surrogate | primary_surrogate | validated_surrogate | clinical
  #   moa_precedent: validated            # novel | partially_validated | validated | established
  #   biomarker_selected: false
  #   breakthrough_designation: false

discount_rate: 0.12
launch_year_offset: 5                    # Years from today to first commercial sale
"""

_MANAGEMENT_QUALITY_JSON = {
    "_note": "Placeholder — replace values before running bve-evaluate-target",
    "_ticker": "{ticker}",
    "clinical_execution_score": 0.5,
    "trial_design_rigor_score": 0.5,
    "regulatory_strategy_score": 0.5,
    "capital_allocation_score": 0.5,
    "bd_partnering_score": 0.5,
    "disclosure_quality_score": 0.5,
    "governance_score": 0.5,
    "notes": "Placeholder values — analyst assessment required",
    "as_of": "{today}",
}

_MA_TARGET_PROFILE_YAML = """\
# M&A target profile for {ticker}
# Used by MAProbabilityScanner and BuyerTargetThesis

ticker: {ticker}
asset_id: "{ticker_lower}_lead"
company_name: "{ticker} Therapeutics"

# Pipeline / science
lead_indication: ""
lead_mechanism: ""
lead_phase: phase2
n_pipeline_assets: 1
has_platform_technology: false
has_proprietary_data_asset: false

# Deal context
management_receptivity: unknown          # open | neutral | resistant | entrenched | unknown
has_activist_pressure: false
has_strategic_review: false
has_prior_partnership_history: false
founder_on_board: false

# Financials (approximate)
market_cap_millions: 0.0
enterprise_value_millions: 0.0
cash_millions: 0.0
burn_rate_monthly_millions: 0.0

# Watchlist classification
watchlist_type: monitoring               # top_priority | active_monitoring | monitoring | low_priority
conviction: medium                       # high | medium | low
"""

_ACQUIRER_MAPPING_YAML = """\
# Acquirer mapping for {ticker}
# Lists potential strategic acquirers and their strategic fit rationale
# Used by AcquirerFitEngine

target_ticker: {ticker}
target_asset_id: "{ticker_lower}_lead"

potential_acquirers:
  - acquirer_name: ""                    # e.g. "Pfizer"
    ticker: ""                           # e.g. "PFE"
    strategic_fit_rationale: ""          # 1–2 sentences on why this acquirer
    has_indication_overlap: false
    has_platform_overlap: false
    has_geographic_overlap: false
    bd_activity_score: 0.5               # 0–1; historical BD activity proxy
    balance_sheet_capacity: true         # Can they afford it?
    notes: ""
"""

_FINANCIAL_SNAPSHOT_JSON = {
    "_note": "Placeholder — populate from latest 10-Q or yfinance refresh",
    "_ticker": "{ticker}",
    "as_of": "{today}",
    "cash_and_equivalents_millions": None,
    "short_term_investments_millions": None,
    "total_cash_millions": None,
    "net_debt_millions": None,
    "quarterly_burn_rate_millions": None,
    "months_of_runway": None,
    "shares_outstanding_millions": None,
    "market_cap_millions": None,
    "stock_price": None,
    "revenue_ttm_millions": None,
    "rd_expense_ttm_millions": None,
    "data_source": "placeholder",
}

_TRIAL_RECORDS_YAML = """\
# Clinical trial records for {ticker}
# One entry per trial. NCT IDs can be validated via bve-trial-diff --nct <NCT_ID>

trials:
  - asset_id: "{ticker_lower}_lead"
    phase: phase2
    name: "Phase 2 {ticker} Lead Program"
    nct_id: ""                           # ClinicalTrials.gov identifier
    start_year: {year}
    duration_years: 3.0
    cost_millions: 40.0
    enrollment_target: 0
    primary_endpoint: ""                 # e.g. "ORR", "PFS", "OS"
    endpoint_type: primary_surrogate     # surrogate | primary_surrogate | validated_surrogate | clinical
    status: recruiting                   # not_started | recruiting | active | completed | terminated
    notes: ""
"""


# ---------------------------------------------------------------------------
# Core scaffolding logic
# ---------------------------------------------------------------------------

def _render(template: str, ticker: str, today: str) -> str:
    return template.format(
        ticker=ticker,
        ticker_lower=ticker.lower(),
        year=date.today().year,
        today=today,
    )


def _write_if_missing(path: Path, content: str) -> bool:
    """Write *content* to *path* only if the file does not already exist.

    Returns True if the file was created, False if it already existed.
    """
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def init_asset(
    ticker: str,
    *,
    configs_dir: Optional[Path] = None,
    outputs_dir: Optional[Path] = None,
) -> list[Path]:
    """Scaffold the minimum file set for a new biotech company.

    Parameters
    ----------
    ticker:
        Stock ticker (case-insensitive; stored as UPPER).
    configs_dir:
        Root configs directory; defaults to ``configs/``.
    outputs_dir:
        Root outputs directory; defaults to ``outputs/``.

    Returns
    -------
    list[Path]
        Paths of files that were *created* (existing files are skipped).
    """
    ticker = ticker.upper()
    today = date.today().isoformat()

    configs_root = configs_dir or Path("configs")
    outputs_root = outputs_dir or Path("outputs")

    cfg_dir = configs_root / ticker
    out_dir = outputs_root / ticker

    created: list[Path] = []

    def _yaml(name: str, template: str) -> None:
        p = cfg_dir / name
        if _write_if_missing(p, _render(template, ticker, today)):
            created.append(p)

    def _json_file(name: str, template: dict) -> None:
        # Walk the dict and substitute only string leaf values to avoid
        # str.format() KeyErrors on JSON curly braces in nested structures.
        def _subst(obj: object) -> object:
            if isinstance(obj, str):
                return (
                    obj.replace("{ticker}", ticker)
                       .replace("{ticker_lower}", ticker.lower())
                       .replace("{today}", today)
                )
            if isinstance(obj, dict):
                return {k: _subst(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_subst(v) for v in obj]
            return obj
        rendered = json.dumps(_subst(template), indent=2)
        p = out_dir / name
        if _write_if_missing(p, rendered + "\n"):
            created.append(p)

    _yaml("asset_profile.yaml", _ASSET_PROFILE_YAML)
    _yaml("valuation_config.yaml", _VALUATION_CONFIG_YAML)
    _yaml("ma_target_profile.yaml", _MA_TARGET_PROFILE_YAML)
    _yaml("acquirer_mapping.yaml", _ACQUIRER_MAPPING_YAML)
    _yaml("trial_records.yaml", _TRIAL_RECORDS_YAML)

    _json_file("management_quality.json", _MANAGEMENT_QUALITY_JSON)
    _json_file("financial_snapshot.json", _FINANCIAL_SNAPSHOT_JSON)

    return created


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="bve-init-asset",
        description=(
            "Scaffold the minimum file set to add a new biotech company to the "
            "BVE tracking universe. Creates commented YAML/JSON templates under "
            "configs/<TICKER>/ and outputs/<TICKER>/."
        ),
    )
    parser.add_argument("--ticker", required=True, help="Stock ticker (e.g. SRPT, VKTX).")
    parser.add_argument(
        "--configs-dir", default=None, dest="configs_dir",
        help="Root configs directory. Defaults to configs/.",
    )
    parser.add_argument(
        "--outputs-dir", default=None, dest="outputs_dir",
        help="Root outputs directory. Defaults to outputs/.",
    )
    args = parser.parse_args(argv)

    ticker = args.ticker.upper()
    print(f"[bve-init-asset] Initialising asset scaffold for {ticker}...", file=sys.stderr)

    created = init_asset(
        ticker,
        configs_dir=Path(args.configs_dir) if args.configs_dir else None,
        outputs_dir=Path(args.outputs_dir) if args.outputs_dir else None,
    )

    if not created:
        print(
            f"[bve-init-asset] All template files already exist for {ticker} — nothing created.",
            file=sys.stderr,
        )
    else:
        for p in created:
            print(f"  created: {p}")
        print(
            f"[bve-init-asset] {len(created)} file(s) created for {ticker}. "
            "Fill in the templates and run `bve-asset --config configs/<TICKER>/asset_profile.yaml`.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
