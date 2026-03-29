# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## After any code change

After writing or modifying any code, always run these steps in order:

1. **Run tests**: `python -m pytest tests/ -v`
2. **Run lint**: `ruff check src/`
3. **Commit changes**: create a git commit with a Conventional Commit message

If any tests fail or lint errors are found, fix them before committing.

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

# POS model backtest (40-program oncology dataset)
python -m bve.analysis.backtest research/data/oncology_phase_transitions.csv

# Historical replay — seed prices, run, inspect
python -m bve.ops.historical_replay seed \
    --tickers VKTX ALNY SRPT NTLA XBI \
    --start 2025-04-01 --end 2026-03-01
python -m bve.ops.historical_replay run \
    --start 2025-04-01 --end 2026-03-01 --cadence weekly \
    --decision-policy top2_add --max-hold-days 28 \
    --catalyst-timing --cooling --require-catalyst-days 14
python -m bve.ops.historical_replay summary --run-id <run_id>
python -m bve.ops.historical_replay inspect --run-id <run_id> --week 2025-09-15
```

The canonical real-world test case is `examples/configs/relay_rly2608.yaml` (RLAY / RLY-2608). Outputs land in `outputs/<TICKER>/`.

## Architecture

The codebase has two distinct subsystems that share entities but are otherwise independent.

### 1. Valuation pipeline (asset pricing)

The core flow, orchestrated by `valuation/valuation_engine.py`:

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

### 2. Intelligence layer (ops / weekly runner)

A separate operational loop that tracks a live universe of biotech names, maintains a knowledge store of thesis claims and events, and surfaces actionable opportunities.

**`KnowledgeStore`** (`intelligence/knowledge_layer.py`) — SQLite-backed store for all intelligence data: thesis claims, events, forecasts, decisions. Live store at `outputs/intelligence/ops.db`.

**`ThesisTracker`** (`intelligence/thesis_tracker.py`) — reads claims from `KnowledgeStore` and computes `ThesisSnapshot` (n_confirmed, n_refuted, n_expired, thesis_strength). `snapshot(asset_id, as_of_date=...)` supports time-frozen queries for replay.

**`ActionableGenerator`** (`intelligence/actionable_output.py`) — takes a list of `ScoredCandidate` objects and produces a `WeeklyActionableReport`. Composite score formula: `ranking × 0.50 + thesis × 0.30 + opportunity × 0.20`. With thesis_strength=None (no resolved claims), the neutral value of 0.5 is used. Assets scoring ≥ 0.50 receive "add" action.

**`UNIVERSE`** (`ops/weekly_runner.py`) — the list of 27 tracked assets, each with `ticker`, `asset_id`, `company_id`, `indication`, `ranking_score`, `opportunity_score`, `conviction`, `catalyst`, `claim_type`, `claim_assertion`. Three conviction tiers: Tier A (medium-high, 0.56–0.72), Tier B (weak, 0.30–0.44), Tier C (known failures/distressed, 0.12–0.28).

### 3. Historical replay (`ops/historical_replay.py`)

A time-frozen simulation loop for backtesting decision policies without lookahead bias:

```
seed  → downloads prices (yfinance) + inserts thesis claims into isolated replay KB
run   → ReplayClock advances week-by-week:
          _step_decision: builds ScoredCandidates as of replay date,
                          applies ReplayPolicy gates, persists decisions
          _step_resolve:  closes positions at exit_target date,
                          classifies attribution
summary / inspect → ReplaySummary stats + per-decision breakdown
```

**No-lookahead guarantee**: isolated SQLite at `outputs/intelligence/replay_store.sqlite` (never touches ops.db). `ThesisTracker.snapshot(as_of_date=...)` adds `AND date(created_at) <= ?`. Attribution uses `get_events_in_window(asset_id, entry_date, exit_date)` — never all-history events.

**`ReplayPolicyConfig`** gates (all composable via CLI flags):
- `--max-hold-days N` — forced exit after N calendar days (use multiples of 7; 15d == 21d at weekly cadence)
- `--catalyst-timing` — entry only 3–10 days before a seeded catalyst; `<2d` → half size
- `--xbi-filter` — block all entries when XBI < 20-day MA
- `--cooling` — block asset 7d after 1 consecutive `thesis_error`, 14d after 2+
- `--require-catalyst-days N` — block entry if no catalyst within N days (0 = disabled)

**Attribution taxonomy**: `confirmed_thesis` (event + matching return), `pos_error` (negative event, positive return), `timing_error` (positive event, negative return), `thesis_error` (no event, negative return), `market_drift` (no event, positive return), `unclassified`.

**Seeding catalyst events**: events must be inserted into `ReplayStore.historical_events` with realistic `announced_at` dates. The density gate (`require_catalyst_within_days`) and timing gate both query this table.

### 4. POS model backtest (`analysis/backtest.py`)

Validates POS model predictions against historical drug trial outcomes. Dataset: `research/data/oncology_phase_transitions.csv` (99 programs). Output: Brier score, AUC-ROC, calibration buckets.

**Current state (Sprint 26C validated)**: N=99, Phase 2 success=39.6%, Phase 3 success=60.8% — at realistic industry base rates. Brier=0.2127, AUC=0.74 (heuristic model). Both models show ~15% skill improvement over no-skill baseline. Dataset is adequately calibrated for directional use.

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
- `test_historical_replay.py` — replay store, no-lookahead bias invariant, isolation from live DB
- `test_replay_policy.py` — all `ReplayPolicy` gate combinations (cooling, catalyst density, XBI, timing)

All models are Pydantic v2 (`BaseModel`, frozen where appropriate). Use `model_copy(update={...})` to derive modified instances — direct field assignment on frozen models raises an error.

## Backtest validation — best path forward

Three backtest surfaces exist at different readiness levels:

### Priority 1: POS backtest dataset — COMPLETE (Sprint 26C)

`research/data/oncology_phase_transitions.csv` has N=99, Phase 2=39.6%, Phase 3=60.8% success — at realistic industry base rates. Brier=0.2127, AUC=0.74. Dataset is adequately calibrated. No further additions required unless expanding to other therapeutic areas.

### Priority 2: Extend the historical replay time range

The replay runs (9 and 10) produced only N=4 decisions — statistically insufficient. Extend the date range back to 2024-01-01, seed prices for all 27 universe names from that date, and populate `historical_events` with real readouts from 2024. This will increase the number of resolved positions from 4 to ~20+, making hit rate and mean return meaningful.

```bash
python -m bve.ops.historical_replay seed \
    --tickers VKTX ALNY SRPT NTLA VRTX CRSP BEAM RXRX MRNA BMRN REGN LLY \
              KYMR ARVN RVMD MDGL IMVT FULC FATE OCUL SRRK IOVA NVAX AMRN PRTA EDIT ZYME XBI \
    --start 2024-01-01 --end 2026-03-10
```

### Priority 3: Portfolio backtest against knowledge store

`analysis/portfolio_backtest.py` (`PortfolioStrategy.TOP_N_EQUAL_WEIGHT`, `SCORE_WEIGHTED`, `CATALYST_MOMENTUM`) uses `BacktestSnapshot` records from the live ops.db. Requires the weekly runner to have run for several weeks first. Be aware of the built-in survivorship bias warning — delisted names are excluded from yfinance returns.
