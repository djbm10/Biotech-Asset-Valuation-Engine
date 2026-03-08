# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable + dev deps)
pip install -e ".[dev]"

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_competition_crowding.py -v

# Run a single test by name
python -m pytest tests/test_models.py::TestRNPVModel::test_base_case -v

# Lint / type-check
ruff check src/
mypy src/bve/

# CLI: run a single asset valuation
bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts

# CLI: batch (directory of configs)
bve-batch --config-dir examples/configs/ --memo bd --charts

# CLI: portfolio
bve-portfolio --config examples/configs/relay_portfolio.yaml
```

The canonical real-world test case is `examples/configs/relay_rly2608.yaml` (RLAY / RLY-2608). Outputs land in `outputs/<TICKER>/`.

## Architecture

### Valuation pipeline

The core flow, orchestrated by `ValuationEngine.run()`:

```
YAML config → CLI (run_asset.py) → ValuationEngine
  → _prepare_trials()          POS model layer 1 (log-odds adjusters)
                               POS model layer 2 (trial design features)
  → ProbabilityModel.compute() per-phase timing + cumulative P(approval)
  → RevenueModel.compute()     annual revenue curve (LOE tail optional)
  → CostModel.compute()        probability-weighted PV of trial R&D + deal costs
  → RNPVModel.compute()        P(approval)×PV(EBIT) − PV(costs) + milestones
  → build_scenarios()          Bull / Base / Bear shocks
  → run_monte_carlo()          10k correlated draws (Gaussian copula)
  → _compute_sensitivities()   Tornado analysis (5 parameters ±)
  → ValuationOutput            full artifact → JSON + memo + charts
```

`ValuationEngine` can be constructed directly or via `ValuationEngine.from_program(DrugAssetProgram, company)`. The `from_program` path is preferred for programmatic use — it carries an explicit `CommercialPlan` (LOE state) rather than fetching it at run time.

### Key data containers

- **`DrugAssetProgram`** (`models/drug_asset_program.py`) — frozen Pydantic container bundling `Asset`, `list[ClinicalTrial]`, `MarketModel`, `DealEconomics`, and `CommercialPlan`. The recommended input to the engine. Use `DrugAssetProgram.build(asset, trials, market_model, load_loe=True)`.

- **`CommercialPlan`** — three distinct states: `"unset"` (engine fetches LOE from `AssumptionsLoader`), `"suppressed"` (no post-patent tail), `"modality:<name>"` (explicit profile loaded). Never conflate these; `"unset"` with an LOE dict is rejected at construction.

- **`MarketModel`** — three revenue modes:
  1. `lines_of_therapy` (list of `LineOfTherapySegment`) — recommended for oncology with distinct 1L/2L/3L pools
  2. Patient-based: `addressable_patients_annual` + `net_price_per_patient_usd`
  3. TAM-based: `total_addressable_market_millions`
  Modes 2 and 3 share `peak_penetration`, `years_to_peak`, `patent_life_years`. Holds `cogs_rate`, `sgna_rate_launch`, `sgna_rate_mature` for the cost structure applied by `RNPVModel`.

- **`DealEconomics`** (`models/deal_economics.py`) — deal terms consumed by `CostModel` (scales trial costs via `cdev_cost_share`; discounts payable milestones) and `RNPVModel` (royalty stacking on `asset.net_ownership`; receivable milestones + upfront receipts). Default is no-deal semantics.

### Competition model (`models/competition_model.py`)

`CompetitionModel` sits on `MarketModel` and adjusts `revenue_in_year()` via `our_available_market_fraction(year)`. Three independent layers that can be combined:

- **`CrowdingModel`** — decay per competitor beyond a threshold (default: disabled)
- **`FirstMoverConfig`** — bonus to earliest approved entrant(s), penalty to late entrants; applied inside `_single_competitor_share()` **before** crowding, so crowding operates on first-mover-adjusted shares
- **`ClassSaturationProfile`** — saturation ceiling (class cannot collectively exceed a TAM fraction) + market expansion factor; applied in `our_available_market_fraction()` **after** first-mover-adjusted combined share is computed

Invariant: with saturation enabled, `available ≤ ceiling − combined_competitor_share` always holds (floor is capped at headroom). With `market_expansion_factor > 1`, available can exceed the static headroom but is bounded by `1.0 − combined`.

`sample_launch_outcomes(rng)` propagates all three configs to the sampled `CompetitionModel`.

### Multi-indication (`models/multi_indication.py`)

`run_multi_indication_valuation(MultiIndicationProgram, company)` calls `ValuationEngine.from_program()` once per indication. Key mechanics:

- **Cascade PoS**: `secondary.adjusted_rnpv = secondary.rnpv × primary_cumulative_pos` (when `cascade_pos=True`)
- **`FranchiseCostSharing`**: reduces `sgna_rate_launch/mature`, `cogs_rate`, and `DealEconomics.cdev_cost_share` on secondaries only. Primary program is never touched. Per-secondary `cost_sharing` overrides `MultiIndicationProgram.default_cost_sharing`. When sharing is active the engine runs twice per secondary (with/without sharing) to compute `IndicationResult.cost_sharing_benefit_millions`.

### POS model (`models/pos_model.py`)

Log-odds adjusters applied on top of Biomedtracker/IQVIA base rates (in `industry_assumptions.yaml`). Layer 1: `POSAdjusters` (endpoint type, MoA precedent, sample size, safety, competitive pressure, biomarker enrichment, prior phase data, breakthrough designation). Layer 2: `TrialDesignFeatureSet` (`models/trial_design_features.py`). A `check_pos_layer_overlap()` guard warns when both layers adjust the same factor.

### Assumptions / calibration

All industry priors live in `src/bve/config/industry_assumptions.yaml` and are accessed via the `AssumptionsLoader` singleton. `constants.py` re-exports the same names for backward compatibility. Returned data is immutable (`MappingProxyType`). Unknown TA/modality falls back to `"other"` with a `UserWarning`.

### Reporting

`reporting/memo_generator.py` renders Jinja2 templates (`bd_memo.md.j2`, `vc_memo.md.j2`, `hf_memo.md.j2`) → Markdown → `.docx` (via `python-docx`). `reporting/charts.py` produces 5 matplotlib charts. `reporting/export.py` writes `valuation.json` with full run artifact including `meta` (git commit, seed, timestamp) and `assumptions` (every key number with source + sensitivity rating).

### Test structure

Tests in `tests/` are organized by feature area:
- `test_models.py` — core rNPV / revenue / cost math
- `test_phase1.py`–`test_step7.py` — incremental feature tests added as the engine grew
- `test_competition_crowding.py` — `CrowdingModel`, `FirstMoverConfig`, `ClassSaturationProfile`
- `test_multi_indication.py` — `MultiIndicationProgram`, cascade PoS, `FranchiseCostSharing`
- `test_assumptions_loader.py` — YAML loading, fallback warnings, immutability

All models are Pydantic v2 (`BaseModel`, frozen where appropriate). Use `model_copy(update={...})` to derive modified instances — direct field assignment on frozen models raises an error.
