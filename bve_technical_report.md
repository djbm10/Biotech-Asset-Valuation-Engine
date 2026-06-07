# Biotech Asset Valuation Engine — Exhaustive Technical Report

**Project root:** `\\wsl.localhost\ubuntu\home\djmann\projects\biotech-asset-valuation-engine`
**Report date:** 2026-05-14
**Source material:** direct code reading, not documentation alone

---

## 1. Executive Summary

### What the Tool Is

The Biotech Asset Valuation Engine (BVE) is a Python-based quantitative framework for risk-adjusted net present value (rNPV) modeling of drug development programs. It is designed for business development (BD) professionals, biotech equity investors, and venture capitalists who need to value clinical-stage assets, understand variant perception vs. market prices, and track thesis evolution over time.

### What Business Problem It Solves

Clinical-stage biotech valuation is notoriously hard because the cash flows are probabilistic, far in the future, and contingent on multiple binary events (trial successes). Standard DCF frameworks cannot handle this cleanly. BVE wraps the canonical rNPV framework — discounting expected future commercial cash flows probability-weighted by each trial phase's success rate — in a system that also:
- Adjusts raw industry base rates for asset-specific qualitative factors (POS model)
- Models competitive dynamics at launch
- Handles deal economics (royalties, milestones, co-development splits)
- Generates BD memos, charts, and structured JSON artifacts
- Tracks investment thesis claims and generates weekly ranked opportunity lists
- Runs historical replay simulations with no-lookahead guarantees

### What Decisions It Supports

1. **BD deal evaluation:** Should we in-license this asset? At what milestone split does the deal break even?
2. **Portfolio prioritization:** Which of 27 tracked assets is most actionable this week?
3. **Investment screening:** Is this biotech trading at a discount to model rNPV? What does the market imply?
4. **Scenario/risk analysis:** What is the bull/bear NAV range? Which driver has the biggest tornado impact?
5. **Thesis monitoring:** Have our investment claims been confirmed or refuted by new data?

### What the Tool Does Well

- **Structurally sound rNPV math:** The four-model pipeline (ProbabilityModel → RevenueModel → CostModel → RNPVModel) is correctly separated with clean interfaces. The rNPV formula is textbook-correct.
- **Log-odds POS model:** The two-layer qualitative adjuster system is well thought out. Log-odds space prevents probability leakage above 1 or below 0. Adjusters are calibrated at reasonable magnitudes. The TA-specific endpoint tables show sophisticated domain knowledge.
- **Competition modeling:** The `CompetitionModel` class with time-varying competitor ramps, first-mover bonus/penalty, class saturation, and Monte Carlo sampling of pipeline competitors is more sophisticated than most commercial BD models.
- **No-lookahead replay:** The historical replay system uses genuinely isolated SQLite stores and time-frozen SQL queries to prevent lookahead bias — a common flaw in backtest systems.
- **Audit trail:** SHA-256 hashing of config and assumptions YAML, provenance metadata, revenue audit tables, and `assumption_log` give the output genuine auditability.
- **Pydantic v2 throughout:** Frozen models, field validators, and `model_copy(update=...)` semantics are used consistently, preventing silent mutation bugs.

### What the Tool Does Not Do (Honest Limitations)

- **No real-time data:** The tool does not pull live pipeline data, updated trial status, or current pricing from any public API automatically. All inputs are analyst-entered YAML.
- **POS calibration is directional only:** The log-odds adjuster magnitudes are stated as "evidence-informed priors" and "judgment calls." No regression analysis on historical drug outcomes calibrates the exact log-odds values used.
- **No multi-asset portfolio optimization:** NAV is single-asset or sum-of-parts; there is no Markowitz-style portfolio optimization, correlation between assets, or capital allocation solver.
- **US-only by default:** Market models are US-focused unless the user explicitly adds geography splits. Ex-US value is easily forgotten.
- **Intelligence layer requires manual claim resolution:** Thesis claims don't resolve automatically from any live data feed; resolution is either programmatic rule application or manual entry.
- **LLM extraction is uncalibrated:** The YAML explicitly marks `llm_extraction.calibration_status: "uncalibrated"` and requires N=200 labeled outcomes to validate. This means the LLM-based signal extraction cannot be trusted quantitatively yet.
- **Backtest N is too small for statistical inference:** Best replay run shows N=60, mean=+3.29%, requiring ~111 trades for p<0.10. Current evidence is not statistically significant.

---

## 2. Full System Map

### Package Structure

```
src/bve/
├── config/           — YAML assumptions, AssumptionsLoader singleton, constants.py
├── entities/         — Asset, Company, Indication, ClinicalTrial domain objects
├── models/           — Core valuation models (POS, Revenue, Cost, rNPV, Competition, etc.)
├── valuation/        — ValuationEngine orchestrator, scenarios, sensitivity, outputs
├── analysis/         — Implied probability back-solve, sensitivity, ranking calibrator, backtest
├── reporting/        — Memo generator, JSON export, charts
├── cli/              — Entry points: run_asset.py, run_batch.py, calibrate.py
├── intelligence/     — KnowledgeStore, ThesisTracker, ActionableGenerator, ComparableDealMatcher
├── ops/              — weekly_runner.py, historical_replay.py
├── ingestion/        — market_data.py (yfinance wrapper)
├── connectors/       — market_prices.py, press_release.py
├── agents/           — data_ingestion agents (FDA, ClinicalTrials.gov, PubMed, SEC, news)
├── pipeline/         — PipelineState, ChangeDetector, UniverseRegistry, DiskCache
├── ui/               — Dashboard app components (Streamlit or similar)
└── visualization/    — valuation_charts.py, clinical_timeline.py, portfolio_charts.py
```

### File-by-File Module Descriptions (Key Files)

**`src/bve/valuation/valuation_engine.py`**
The main orchestrator. `ValuationEngine` is constructed either directly (raw parameters) or via `ValuationEngine.from_program(DrugAssetProgram, company)`. The `run()` method sequences: `_prepare_trials()` (POS layers) → `_resolve_market_model_with_sgna()` (SG&A auto-selection) → revenue sanity checks → `_apply_trial_cost_defaults()` → `ProbabilityModel.compute()` → `RevenueModel.compute()` → `CostModel.compute()` → `RNPVModel.compute()` → NAV calculation → `build_scenarios()` → `run_monte_carlo()` → `compute_sensitivity()` → `build_assumption_log()` → `ValuationOutput`. Every major step returns immutable result objects.

**`src/bve/models/pos_model.py`**
The probability-of-success model. Two-layer architecture: Layer 1 applies `POSAdjusters` in log-odds space; Layer 2 optionally applies `TrialDesignFeatureSet` as a second orthogonal adjustment. Contains 9 adjuster enumerations with 5–8 tiers each, TA-specific endpoint log-odds tables for 14 therapeutic areas, gene/cell therapy concern overlays, and MoA exception flags. The `compute_pos()` function is the single calculation entry point.

**`src/bve/models/probability_model.py`**
Stateless. `ProbabilityModel.compute()` walks forward through sorted trials, computes cumulative `prob_reaching` for each phase as the product of all prior success probabilities, sums durations for `years_to_approval`, and returns a `ProbabilityResult`. No randomness here; all stochasticity is in Monte Carlo.

**`src/bve/models/revenue_model.py`**
Stateless. `RevenueModel.compute()` delegates the within-patent revenue curve to `MarketModel` methods (which handle LOT segments, competition fractions, SG&A ramps) and appends up to 5 LOE tail years from the erosion profile. Returns `RevenueStream` with year-by-year revenue, gross profit, and EBIT arrays.

**`src/bve/models/cost_model.py`**
Stateless. `CostModel.compute()` discounts each trial's cost to present value at the phase midpoint (or sub-interval midpoints for `SpendProfile.ANNUAL_UNIFORM`), probability-weights by `prob_reaching`, adds deal co-dev share scaling, payable milestone PVs, upfront costs, post-approval R&D, and CMC costs. Returns `CostStream`.

**`src/bve/models/rnpv_model.py`**
Stateless. `RNPVModel.compute()` loops over `RevenueStream.ebit_by_year`, applies deal royalty and profit-share deductions, then either the simple NOL-window tax path (Path A) or the full `TaxProfile` FCF path (Path B), discounts each year's after-tax FCF by ownership fraction, multiplies cumulative sum by `P(approval)`, subtracts trial costs PV, adds milestone receipts PV and upfront receipts. Final rNPV rounded to nearest $1M.

**`src/bve/models/market_model.py`**
The commercial model supporting three revenue modes: `lines_of_therapy` segments, patient-based (`addressable_patients_annual × net_price_per_patient_usd`), and TAM-based (`total_addressable_market_millions × peak_penetration`). Also handles S-curve vs. linear uptake, geography splits, price erosion, lifecycle events (label expansions, new formulations), payer access model, and competition model integration.

**`src/bve/models/competition_model.py`**
`CompetitionModel` aggregates `CompetitorLaunch` objects. Each competitor has a time-varying market share ramp (linear or logistic S-curve). Three independent overlays: `CrowdingModel` (decay per excess competitor beyond threshold), `FirstMoverConfig` (bonus/penalty to first/late approved entrants), `ClassSaturationProfile` (TAM ceiling + market expansion factor). `sample_launch_outcomes()` provides Monte Carlo sampling of pipeline competitor success.

**`src/bve/models/drug_asset_program.py`**
Frozen container bundling `Asset`, `list[ClinicalTrial]`, `MarketModel`, `DealEconomics`, `CommercialPlan`, and optional `CMCCosts`, `ConfirmatoryTrialObligation`. Three-state `CommercialPlan` enforces explicit LOE state (unset/suppressed/loaded). Validated that `market_model.asset_id == asset.id`.

**`src/bve/models/deal_economics.py`**
`DealEconomics` carries: `royalty_rate` (top-line), `profit_share_rate` (EBIT-level), `cdev_cost_share` (R&D cost fraction), `upfront_cost_millions`, `upfront_receipt_millions`, `payable_milestones`, `receivable_milestones`, and `launch_year_offset`. The `milestone_pv()` helper performs timing-and-probability-appropriate discounting for five trigger types.

**`src/bve/models/multi_indication.py`**
`run_multi_indication_valuation()` calls `ValuationEngine.from_program()` once per indication. When `cascade_pos=True`, the secondary's rNPV is multiplied by the primary's `cumulative_success_probability`. `FranchiseCostSharing` reduces secondary SG&A, COGS, and cdev_cost_share. The cost-sharing benefit is isolated by running the engine twice (with and without sharing).

**`src/bve/models/monte_carlo.py`**
`run_monte_carlo()` draws 10,000 correlated samples using a Gaussian copula (`scipy.stats`) via `correlated_uniform_samples()`. Phase success probabilities use Beta distributions parameterized by `mean × ESS`. Peak sales uses log-normal. Discount rate uses normal. Each trial runs the full engine chain via `_run_single_trial()` which calls `compute_rnpv_full()` — no shortcut to base rNPV. Returns `MonteCarloResult` with full percentile distribution, variance driver ranking (Spearman r), and 3-record audit trail.

**`src/bve/intelligence/knowledge_layer.py`**
`KnowledgeStore` is a SQLite-backed store. Holds raw documents, extraction results, structured signals, evidence facts, thesis claims, events, decisions, market prices, SOTP snapshots, enrollment snapshots, catalyst calendars, and a knowledge graph (nodes + edges). The live store is `outputs/intelligence/ops.db`.

**`src/bve/intelligence/thesis_tracker.py`**
`ThesisTracker` wraps a `KnowledgeStore`. Manages `thesis_claims` table with claim lifecycle (open/confirmed/refuted/expired/superseded). `snapshot(asset_id, as_of_date)` produces a `ThesisSnapshot` with counts and `thesis_strength = n_confirmed / (n_confirmed + n_refuted + n_expired)`. A `weighted_thesis_strength` uses per-claim-type weights (`ENDPOINT_MET=2.0`, `REGULATORY_PATHWAY=1.5`, etc.). The time-freeze is enforced in SQL (`date(created_at) <= ?`) and additionally in Python for claims resolved after `as_of_date`.

**`src/bve/intelligence/actionable_output.py`**
`ActionableGenerator.generate()` computes composite scores: `ranking×0.50 + thesis×0.30 + opportunity×0.20`. When `thesis_strength=None`, the neutral value 0.5 is used. Action thresholds: `buy ≥ 0.70`, `add ≥ 0.50`, `monitor ≥ 0.30`, `avoid < 0.30`. v2.0 scoring adds six signal adjustment layers (catalyst_ev, enrollment, phase_correlation, endpoint_z, competitor_impact, capital_risk) additively on top of the base composite.

**`src/bve/ops/historical_replay.py`**
`ReplayStore` is fully isolated from `ops.db`. `HistoricalReplay.run()` advances a `ReplayClock` week-by-week, building `ScoredCandidate` objects as of each week's date (using time-frozen thesis snapshots), applies `ReplayPolicy` gates, records decisions to the replay store. Exit resolution classifies outcomes into 6 attribution types. The `--min-thesis-score` filter and `--require-catalyst-days` gate are the most important parameters for selecting quality candidates.

**`src/bve/config/industry_assumptions.yaml`**
Single source of truth for all calibrated priors. Contains: phase success rates (16 TAs), phase durations, phase costs by TA, commercial defaults (G2N, COGS, SG&A profiles), WACC defaults, tax defaults, MC parameters, LOE erosion profiles (7 modalities, 5 tail years each), competition haircuts, POS model caps, trial design log-odds, endpoint benchmarking priors, enrollment quality benchmarks, competitor impact parameters, composite scoring weights, and LLM extraction thresholds.

**`src/bve/analysis/implied_probability.py`**
`compute_implied_market_assumptions()` performs two back-solves from stock price:
1. Given model peak sales: `implied_POS = (market_cap - net_cash + trial_costs_pv) / gross_revenue_pv`
2. Given model POS: `implied_peak_sales = model_peak × (implied_EV + costs_pv) / (model_POS × gross_revenue_pv)`

### End-to-End Data Flow

```
YAML config
    ↓
CLI (run_asset.py) parses → Asset, Company, ClinicalTrial[], MarketModel,
                              POSAdjusters, TrialDesignFeatureSet, MonteCarloParams
    ↓
ValuationEngine.__init__() / from_program()
    ↓
ValuationEngine.run()
    ├── _prepare_trials()
    │     ├── apply_pos_to_trials()  ← compute_pos() ← base_rate + log-odds adjusters
    │     └── _apply_design_adjustments()  ← compute_design_adjusted_pos()
    ├── _resolve_market_model_with_sgna()
    ├── ProbabilityModel.compute()  → ProbabilityResult (phases, cum_prob, years_to_approval)
    ├── RevenueModel.compute()      → RevenueStream (revenue_by_year, ebit_by_year, LOE tail)
    ├── CostModel.compute()         → CostStream (pv_cost_weighted per phase, deal costs)
    ├── RNPVModel.compute()         → RNPVResult (rnpv_millions, nav, peak_sales)
    ├── build_scenarios()           → ScenarioSet (bull/base/bear)
    ├── run_monte_carlo()           → MonteCarloResult (10k trials, distribution)
    ├── compute_sensitivity()       → list[SensitivityPoint] (8 parameters, tornado)
    └── build_assumption_log()      → AssumptionLog (all key numbers with sources)
    ↓
ValuationOutput (complete artifact)
    ├── reporting/export.py → valuation.json
    ├── reporting/memo_generator.py → BD memo (.docx via python-docx)
    └── visualization/valuation_charts.py → 5 matplotlib charts
```

### CLI Entry Points

```bash
# Single asset valuation
bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts
  Flags: --config, --memo [bd|vc|hf], --charts, --output-dir, --seed, --no-loe

# Batch (directory of configs)
bve-batch --config-dir examples/configs/ --memo bd --charts
  Flags: --config-dir, --memo, --charts, --output-dir, --parallel

# Portfolio SOTP
bve-portfolio --config examples/configs/relay_portfolio.yaml
  Flags: --config, --output-dir

# POS model backtest
python -m bve.analysis.backtest research/data/oncology_phase_transitions.csv

# Historical replay (3-step workflow)
python -m bve.ops.historical_replay seed --tickers VKTX ALNY ... --start 2025-04-01 --end 2026-03-01
python -m bve.ops.historical_replay run --start ... --end ... --cadence weekly
    --decision-policy top2_add --max-hold-days 28 --catalyst-timing --cooling
    --require-catalyst-days 14
python -m bve.ops.historical_replay summary --run-id <run_id>
python -m bve.ops.historical_replay inspect --run-id <run_id> --week 2025-09-15
```

---

## 3. Data Inputs

### Asset (`src/bve/entities/asset.py`)

The central entity for a single drug asset.

**Required fields:**
- `id: str` — unique identifier (e.g., `"rly-2608"`)
- `name: str` — human-readable name
- `indication: str` — indication string
- `therapeutic_area: TherapeuticArea` — enum: `oncology`, `rare_disease`, `cns`, `cardiovascular`, `immunology`, `infectious_disease`, `ophthalmology`, `other`, `oncology_solid`, `hematology`, `psychiatry`, `metabolic`, `dermatology`, `gastroenterology`, `pulmonary`, `renal`
- `stage: DevelopmentStage` — enum: `preclinical`, `phase_1`, `phase_2`, `phase_3`, `nda_bla`, `approved`
- `modality: Modality` — enum: `small_molecule`, `biologic`, `gene_therapy`, `cell_therapy`, `adc`, `rna_therapy`, `other`

**Optional fields (with defaults):**
- `discount_rate: float = 0.12` — WACC
- `royalty_rate: float = 0.0` — base royalty on asset (equity split, not deal royalty)
- `net_ownership: float` — computed as `1 - royalty_rate`
- `effective_tax_rate: float = 0.21` — US statutory rate
- `nol_benefit_years: int = 0` — years of zero cash tax from NOL carryforward
- `post_approval_rd_millions: float = 0.0` — Phase 4 / REMS / pharmacovigilance costs
- `approval_pathway: ApprovalPathwayType` — enum: `standard`, `accelerated`, `breakthrough`, `priority_review`
- `mechanism_of_action: str = ""`
- `differentiation_notes: str = ""`
- `competitor_assets: list[str] = []`
- `upcoming_catalysts: list[dict] = []`

**Used by:** `ProbabilityModel`, `CostModel`, `RNPVModel`, `ValuationEngine`

**If missing/invalid:** Pydantic raises `ValidationError` at construction. Unknown `therapeutic_area` falls back to `"other"` with `UserWarning` (from `AssumptionsLoader`).

---

### ClinicalTrial (`src/bve/entities/trial.py`)

One remaining clinical phase for an asset.

**Required fields:**
- `asset_id: str` — must match `Asset.id`
- `phase: TrialPhase` — enum: `phase_1`, `phase_2`, `phase_3`, `nda_bla`
- `success_probability: float` — point estimate in (0, 1); overridden by POS model if `apply_pos_model=True`
- `duration_years: float` — phase duration (industry default: Ph1=1.5, Ph2=2.5, Ph3=3.5, NDA=1.5)
- `cost_millions: float` — trial cost; may be replaced by TA default if `cost_source='default'`

**Optional fields:**
- `enrollment: int = 0`
- `primary_endpoint: str = ""`
- `endpoint_type: EndpointType` — used by POS model; extensive enum
- `nct_id: str = ""`
- `notes: str = ""`
- `cost_source: str = "override"` — `"default"` triggers TA-calibrated substitution with warning
- `spend_profile: SpendProfile` — `UNIFORM` (midpoint discounting) or `ANNUAL_UNIFORM` (sub-interval)

**Used by:** `ProbabilityModel`, `CostModel`, `pos_model.apply_pos_to_trials()`

---

### MarketModel (`src/bve/models/market_model.py`)

The commercial revenue model. Three mutually exclusive revenue modes.

**Mode 1 — Lines of Therapy:**
- `lines_of_therapy: list[LineOfTherapySegment]` — each segment has `line`, `addressable_patients`, `net_price_usd`, `peak_penetration`, `years_to_peak`, `launch_year_offset`

**Mode 2 — Patient-based:**
- `addressable_patients_annual: int` — eligible patients per year
- `net_price_per_patient_usd: float` — annual net price (post G2N)

**Mode 3 — TAM-based:**
- `total_addressable_market_millions: float` — peak addressable market in $M

**Common required fields:**
- `asset_id: str` — must match Asset.id
- `peak_penetration: float` — fraction of addressable market at peak (0-1)
- `years_to_peak: int` — years from launch to peak penetration
- `patent_life_years: int` — exclusivity window

**Optional fields with defaults:**
- `cogs_rate: float = 0.18` — COGS as fraction of net revenue
- `sgna_rate_launch: float = 0.40` — SG&A in launch years
- `sgna_rate_mature: float = 0.20` — SG&A at maturity
- `sgna_ramp_years: int = 5` — linear ramp period
- `compliance_rate: float = 0.80`
- `competition_model: Optional[CompetitionModel]`
- `use_s_curve: bool = False` — logistic vs. linear uptake
- `lifecycle_events: list[LifecycleEvent] = []`
- `geography_split: Optional[GeographySplit]`
- `commercial_model: Optional[str]` — profile name for SG&A (e.g., `"partnered"`, `"rare_disease_kol"`)
- `payer_access: Optional[PayerAccessModel]`
- `commercial_inputs: Optional[CommercialInputs]` — explicit driver-based build

**If missing/invalid:** Revenue modes are mutually exclusive — providing more than one raises `ValidationError`. `peak_penetration` of 0 produces zero revenue silently.

---

### DealEconomics (`src/bve/models/deal_economics.py`)

**Optional fields (all default to no-deal semantics):**
- `royalty_rate: float = 0.0` — royalty paid on net sales to deal partner (top-line)
- `profit_share_rate: float = 0.0` — EBIT-level profit split
- `cdev_cost_share: float = 1.0` — fraction of R&D cost we bear (1.0 = fully ours)
- `upfront_cost_millions: float = 0.0` — payment at t=0
- `upfront_receipt_millions: float = 0.0` — receipt at t=0
- `payable_milestones: list[Milestone] = []` — milestone payments we make
- `receivable_milestones: list[Milestone] = []` — milestone payments we receive
- `launch_year_offset: float = 0.0` — years between approval and first sale (for FIRST_SALE triggers)

**Each Milestone has:** `trigger: MilestoneTrigger`, `amount_millions: float`, `phase: Optional[TrialPhase]`, `probability_weighted: bool = True`

**Used by:** `CostModel` (cost scaling + payable milestone PV), `RNPVModel` (royalty/profit-share deductions + receivable milestone PV)

---

### CommercialPlan (`src/bve/models/drug_asset_program.py`)

Three states:
- `CommercialPlan()` — loe_source="unset"; engine fetches LOE from `AssumptionsLoader`
- `CommercialPlan.no_loe()` — loe_source="suppressed"; no post-patent tail
- `CommercialPlan.from_modality(m)` — loe_source="modality:m"; explicit profile

Validation: raises `ValueError` if `loe_profile` dict provided with `loe_source="unset"`.

---

### POSAdjusters (`src/bve/models/pos_model.py`)

**All fields optional (defaults represent "average" trial):**
- `endpoint_type: EndpointType = SURROGATE_VALIDATED`
- `moa_precedent: MoAPrecedent = PARTIAL`
- `sample_size_adequacy: SampleSizeAdequacy = ADEQUATE`
- `safety_profile: SafetyProfile = MINOR` (alias for MANAGEABLE = 0.00)
- `competitive_pressure: CompetitivePressure = MODERATE` (alias for NORMAL_BAR = 0.00)
- `biomarker_selection: BiomarkerSelectionStrength = NO_SELECTION`
- `prior_phase_data: PriorPhaseDataStrength = MIXED`
- `has_breakthrough_designation: bool = False`
- `extraordinary_evidence: bool = False` — expands positive cap from +0.80 to +1.00
- `gene_cell_therapy_concerns: list[GeneTherapyConcern] = []`
- `moa_exception_flags: list[MoAExceptionFlag] = []`
- Deprecated backward-compat: `biomarker_selected_population: bool`, `strong_prior_phase_data: bool`

---

## 4. Core Models and Calculations

### 4a. POS Model

**Layer 1 — POSAdjusters**

The base rate for each (therapeutic_area, phase) pair comes from `PHASE_SUCCESS_RATES` in `industry_assumptions.yaml`. Example: oncology Phase 2 = 24.8%.

The base rate is converted to log-odds, then eight adjusters are summed:

| Adjuster | Reference (0 adjustment) | Best case | Worst case |
|---|---|---|---|
| Endpoint type | `SURROGATE_VALIDATED` (0.00) | `HARD_CLINICAL` (+0.40-0.45) | `BIOMARKER_ONLY` (-0.55) |
| MoA precedent | `PARTIAL` (0.00) | `VALIDATED_CLASS` (+0.35) | `KNOWN_LIABILITY` (-0.60) |
| MoA exception flags | none (0.00) | `PRIOR_FAILURES_DUE_TO_BAD_DRUG` (+0.25) | — |
| Sample size | `ADEQUATE` (0.00) | `WELL_POWERED` (+0.20) | `EXPLORATORY` (-0.50) |
| Safety | `MANAGEABLE` (0.00) | `CLEAN` (+0.10) | `MECHANISM_LINKED_SEVERE` (-0.80) |
| Competitive pressure | `NORMAL_BAR` (0.00) | `LOW_BAR` (+0.10) | `HIGH_BAR` (-0.30) |
| Biomarker selection | `NO_SELECTION` (0.00) | `VALIDATED` (+0.40) | `POST_HOC_WEAK` (-0.10) |
| Prior phase data | `MIXED` (0.00) | `STRONG_REPLICATED` (+0.30) | `FAILED` (-0.35) |
| Breakthrough designation | false (0.00) | true (+0.05) | — |
| Gene/cell therapy concerns | none (0.00) | `DURABLE_FUNCTIONAL_CORRECTION` (+0.275) | `SERIOUS_SAFETY_CONCERN` (-0.425) |

The combined adjustment is capped at ±0.80 log-odds (`_L1_CAP_POSITIVE = 0.80`, `_L1_CAP_NEGATIVE = -0.80`). With `extraordinary_evidence=True`, positive cap extends to +1.00.

Note: the cap applies to the **adjustment delta**, not the absolute log-odds — the TA base rate is always preserved; only analyst qualitative input is bounded. This is the correct design.

Accelerated approval: for `TrialPhase.NDA_BLA` with `ApprovalPathwayType.ACCELERATED`, the base rate is discounted by 18% before log-odds conversion (`base_rate × (1 − 0.18)`).

**Layer 2 — TrialDesignFeatureSet**

Three orthogonal dimensions, applied as a second log-odds adjustment on top of Layer 1 output:

| Dimension | Range |
|---|---|
| EvidenceDesignQuality | `RCT_DOUBLE_BLIND` (+0.20) to `REGISTRY_OBSERVATIONAL` (-0.35) |
| ComparatorFit | `MATCHES_SOC` (+0.10) to `NO_VALID_COMPARATOR` (-0.30) |
| RegulatoryPathwayRisk | `ORPHAN_RARE_DISEASE` (+0.10) to `NO_CLEAR_PRECEDENT` (-0.30) |

Each dimension's score is multiplied by a phase-scaling factor: Phase 1 = 0.20, Phase 2 = 0.50, Phase 3 = 1.00, NDA = 0.90. Combined cap: +0.30 / −0.60 (asymmetric — bad design hurts more than good design helps).

**`check_pos_layer_overlap()`**
Checks for BTD overlap (BTD is in Layer 1 only; `accelerated_approval` pathway is in Layer 2 only). Raises `ValueError` on critical overlap. This prevents double-counting the most obvious pair, but does NOT prevent all possible logical overlaps between, e.g., `biomarker_selected_population` in Layer 1 and endpoint-type scoring that partially reflects biomarker-selected trials.

**Industry Base Rates (from `industry_assumptions.yaml`)**

| TA | Ph1 | Ph2 | Ph3 | NDA |
|---|---|---|---|---|
| All (cross-TA avg) | 64.0% | 37.0% | 60.0% | 87.0% |
| Oncology | 48.9% | 24.8% | 49.5% | 91.6% |
| Oncology solid | 48.9% | 23.4% | 42.9% | 92.9% |
| Hematology | 50.1% | 27.8% | 60.0% | 90.0% |
| Rare disease | 67.4% | 44.6% | 60.4% | 93.6% |
| CNS | 47.7% | 26.8% | 53.1% | 86.7% |
| Cardiovascular | 50.0% | 29.0% | 55.2% | 82.5% |
| Immunology | 55.2% | 34.6% | 65.3% | 94.1% |
| Metabolic | 61.8% | 45.0% | 63.6% | 87.5% |
| Dermatology | 63.6% | 38.6% | 60.0% | 88.4% |
| Psychiatry | 52.7% | 26.8% | 56.3% | 91.2% |

Source: Biomedtracker/IQVIA 2021, Thomas et al. 2016, Citeline Pharmaprojects 2023.

---

### 4b. Cumulative Approval Probability

`compute_cumulative_pos()` in `pos_model.py` multiplies all per-phase success probabilities:

```
P(approval) = ∏(success_probability[i] for i in phases)
```

`ProbabilityModel.compute()` also accumulates `prob_reaching[i]` for each phase (the probability of reaching that phase, = product of all prior success probabilities). Phase timing is sequential: each phase starts when the prior ends. No parallelism is modeled.

---

### 4c. Revenue Model

**Mode 2 (patient-based, the most common):**

```
peak_sales_millions = (addressable_patients_annual × peak_penetration × compliance_rate
                       × net_price_per_patient_usd) / 1,000,000
```

For year `y` from launch:
```
penetration(y) = peak_penetration × min(1, y / years_to_peak)       [linear ramp]
     or         = peak_penetration × s_curve(y, years_to_peak)       [logistic]

revenue_in_year(y) = (addressable_patients_annual × penetration(y) × compliance_rate
                      × net_price_in_year(y) × our_available_market_fraction(y)) / 1M
```

Where `our_available_market_fraction(y)` comes from `CompetitionModel` (1.0 if no competition modeled).

SG&A rate at year `y`:
```
if y <= 1: sgna = sgna_rate_launch
elif y >= years_to_peak: sgna = sgna_rate_mature
else: sgna = sgna_rate_launch + (sgna_rate_mature - sgna_rate_launch)
             × (y - 1) / (years_to_peak - 1)   [linear ramp]
```

```
gross_profit_in_year(y) = revenue_in_year(y) × (1 - cogs_rate)
ebit_in_year(y) = gross_profit_in_year(y) - revenue_in_year(y) × sgna_rate(y)
```

**LOE tail (post-patent):** For each of up to 5 tail years after `patent_life_years`:
```
tail_rev(k) = peak_sales × (1 - loe_profile["year_k_loss"])
post_loe_sgna_rate = sgna_rate_mature × loe_profile["post_loe_sgna_fraction"]
tail_ebit(k) = tail_rev(k) × (1 - cogs_rate) - tail_rev(k) × post_loe_sgna_rate
```

Note: because `post_loe_sgna_fraction` is typically 0.25-0.30 (marketing collapses), the post-LOE EBIT margin is often **higher** than pre-LOE, which the code acknowledges in comments.

---

### 4d. Cost Model

For each clinical phase `i`:
```
cost_after_share = phase.cost_millions × deal.cdev_cost_share
mid_year = (phase.year_start + phase.year_end) / 2
pv_cost_gross = cost_after_share × (1 + inflation_rate)^mid_year / (1 + r)^mid_year
pv_cost_weighted = pv_cost_gross × phase.prob_reaching
```

With `SpendProfile.ANNUAL_UNIFORM`, cost is split across integer-boundary sub-intervals with appropriate fraction weights.

Additional costs:
- `milestone_costs_pv`: each payable milestone discounted at its trigger year and probability-weighted
- `upfront_cost_millions`: added at face value (t=0, no discount)
- `post_approval_rd_pv`: post-approval R&D discounted at `years_to_approval`, probability-weighted by `cumulative_approval_probability`
- `cmc_pv`: CMC/manufacturing costs at Phase 3 midpoint (or custom year), weighted by Phase 3 `prob_reaching`

```
total_pv_weighted_millions = sum(pv_cost_weighted) + milestone_costs_pv
                             + upfront_cost + post_approval_pv + cmc_pv
```

**"Probability-weighted"** means costs we expect to incur on average across all paths — including the paths where the trial fails and we never reach later phases. This is the standard rNPV treatment, not just the cost of the success path.

---

### 4e. rNPV Model

**The canonical formula (from `rnpv_model.py` docstring):**

```
rNPV = P(approval) × Σ_t [after_tax_FCF_t × net_ownership / (1 + WACC)^t]
       − total_pv_weighted_development_costs
       + PV(receivable_milestones)
       + upfront_receipt
```

Where for each commercial year `t` from launch (absolute year = `years_to_approval + t`):
```
royalty_t      = revenue_t × deal.royalty_rate          [top-line deduction]
profit_share_t = ebit_t × deal.profit_share_rate        [EBIT-level deduction]
adjusted_ebit  = ebit_t - royalty_t - profit_share_t
```

**Path A (simple tax, default):**
```
effective_tax = 0 if t <= nol_benefit_years else asset.effective_tax_rate
after_tax_adjusted = adjusted_ebit × (1 - effective_tax)
captured = after_tax_adjusted × net_ownership
gross_revenue_pv += captured / (1 + r)^(years_to_approval + t)
```

**Path B (TaxProfile, BD-ready):**
Full NOL tracking with utilization limits, maintenance capex, working capital, and one-time launch capex via `compute_year_fcf()` from `tax_profile.py`.

```
probability_adjusted_revenue_pv = gross_revenue_pv × cumulative_approval_probability
rnpv = probability_adjusted_revenue_pv - trial_costs_pv + milestone_receipts_pv + upfront_receipt
```

`net_ownership = 1 - asset.royalty_rate` — the equity stake. Deal royalty and profit share are applied separately before the ownership split.

**NAV:**
```
nav_millions = rnpv_millions × company.ownership_of(asset.id) + company.net_cash_millions
nav_per_share = nav_millions / company.shares_outstanding_millions
```

---

### 4f. Scenario Analysis

`build_scenarios()` in `valuation/scenario.py` constructs Bull/Base/Bear cases by applying shocks to key parameters:

| Parameter | Bear shock | Bull shock |
|---|---|---|
| Peak sales | −30% | +30% |
| Phase POS | −20% relative per phase | +20% relative per phase |
| Discount rate | +3pp | −3pp |
| Years to peak | +2 years | −2 years |

Each scenario runs `compute_rnpv_full()` independently with the shocked inputs, producing a separate `RNPVResult`. NAV per share is computed for each scenario using the same company cash and shares.

---

### 4g. Monte Carlo

**N = 10,000 trials** (configurable via `MonteCarloParams.n_simulations`).

**Uncertain variables per trial:**
1. Phase success probabilities: `Beta(mean × ESS, (1-mean) × ESS)` per phase. Default ESS: Ph1=20, Ph2=25, Ph3=25, NDA=45.
2. Peak sales: `LogNormal` with CV from stage-conditional table (Phase 2 default = 0.45; Phase 3 = 0.30).
3. Discount rate: `Normal(asset.discount_rate, 0.02)`, clipped to (0.01, 0.50).
4. Years to peak: `Normal(years_to_peak, 1.5)`, rounded to int, clipped to [1, 20].
5. Competition: pipeline competitors sampled with Bernoulli(approval_probability) independent draws.

**Gaussian copula correlation:** `correlated_uniform_samples()` applies a pre-specified correlation matrix (default: positive correlation between peak_sales and penetration). Each uniform sample is then transformed via its marginal inverse CDF.

**Key output metrics:** full percentile distribution (P5 through P95, rounded to nearest $5M), `probability_positive`, `probability_above_500m`, `probability_above_1b`, `expected_upside`, `expected_downside`, `downside_value_at_risk` (|P5|), `top_variance_drivers` (Spearman rank correlation between draw arrays and rNPV outcomes), 3-record audit trail (P5/P50/P95 representative simulations).

Each trial runs the **full engine chain** (`compute_rnpv_full()`) — no shortcut to base rNPV. This is correctly enforced by the `SimulationOutput.engine_rerun: bool = True` invariant.

---

### 4h. Variant Perception / Market-Implied Back-Solve

From `src/bve/analysis/implied_probability.py`:

**Implied POS (given model peak sales):**
```
rNPV = P × gross_revenue_pv - trial_costs_pv
market's rNPV ≈ market_cap - net_cash   (single-asset proxy)

implied_POS = (market_cap - net_cash + trial_costs_pv) / gross_revenue_pv
```

**Implied peak sales (given model POS):**
```
gross_pv is proportional to peak_sales (linear scaling in revenue model)
implied_peak = model_peak × (implied_EV + costs_pv) / (model_POS × gross_revenue_pv)
```

**Important limitation:** This uses `market_cap - net_cash` as a proxy for the market's implied asset rNPV. This is only valid for single-asset companies or when the pipeline is fully captured in one model. For multi-pipeline companies, the denominator needs SOTP decomposition which is not automated here.

---

### 4i. M&A / Strategic Fit Scanner

Exists in `src/bve/intelligence/` as `ComparableDealMatcher` (referenced in `valuation_engine.py` line 283). The scanner matches the asset's `indication`, `therapeutic_area`, and `stage` against a list of `ComparableDeal` objects passed by the caller. It produces a `ComparableDealAnalysis` with a fair value band derived from deal EV/peak-sales multiples in comparable transactions.

An `acquirer_profiles.yaml` is referenced in the CLAUDE.md and examples, but was not among the files directly read — it appears to define strategic fit scoring for specific acquirers by therapeutic area and modality preference. The `mna_targetability_rules.yaml` contains target screening rules. These feed an M&A screen but are not wired into the default `bve-asset` CLI run.

---

### 4j. Intelligence Loop / Thesis Tracker

**KnowledgeStore schema (SQLite)**
Core tables (partially observed from `knowledge_layer.py`):
- `thesis_claims` — claim lifecycle with type, assertion, threshold, status, weights
- `events` / `historical_events` — structured events with asset_id, event_type, announced_at
- `decisions` — replay decision records
- `historical_prices` — per-ticker OHLCV
- `knowledge_graph_nodes` / `knowledge_graph_edges` — KG structure
- `evidence_facts` — per-fact source tracing
- `raw_documents`, `extraction_results`, `structured_signals` — document pipeline
- `replay_runs` — replay run metadata
- `company_sotp_snapshots`, `equity_policy_snapshots` — SOTP audit records

**ThesisTracker mechanics:**
```
thesis_strength = n_confirmed / (n_confirmed + n_refuted + n_expired)
                  (None when no resolved claims)

weighted_thesis_strength = Σ(weight[c] for c in confirmed) / Σ(weight[c] for c in resolved)
```

Default claim weights:
- `ENDPOINT_MET = 2.0` (most important — binary trial success)
- `REGULATORY_PATHWAY = 1.5`
- `COMPETITOR_FAILURE = 1.5`
- `LABEL_EXPANSION = 1.25`
- `POS_ABOVE_THRESHOLD = 1.0`
- `ENROLLMENT_ON_TRACK = 0.75`
- `MARKET_REACTION_POSITIVE = 0.5` (least important — noisy signal)
- `CUSTOM = 1.0`

**No-lookahead guarantee:** `snapshot(asset_id, as_of_date)` issues SQL `WHERE date(created_at) <= ?`. Claims resolved after `as_of_date` are re-classified as "open" in Python post-processing.

**ActionableGenerator composite score:**
```
base_composite = ranking_score × 0.50 + thesis_strength × 0.30 + opportunity_score × 0.20
```
When `thesis_strength=None`, 0.5 (neutral) is substituted.

v2.0 signal adjustments (additive on top of base_composite):
- Catalyst EV signal: `signal_strength (clipped ±1) × 0.15`
- Enrollment penalty: site_stalling → −0.05, velocity_low → −0.05, slippage → −0.10
- Phase correlation: `(posterior_pos - prior_pos) × 0.25` (bounded ±0.25 by updater)
- Endpoint z-score: `z (clipped ±2) × 0.05`
- Competitor impact: `-mean_competitor_signal (clipped ±1) × 0.05`
- Capital risk: `{LOW:0, MEDIUM:−0.03, HIGH:−0.08, CRITICAL:−0.15}`

Action thresholds: `buy ≥ 0.70`, `add ≥ 0.50`, `monitor ≥ 0.30`, `avoid < 0.30`. Screening-grade names are clamped to "monitor" maximum.

---

### 4k. Historical Replay

**ReplayClock** advances from `start_date` to `end_date` in weekly steps (or monthly). At each step:
1. `_step_decision()`: build `ScoredCandidate` list using time-frozen thesis snapshots (`as_of_date=current_week`), apply `ReplayPolicy` gates, record decisions.
2. `_step_resolve()`: find decisions at their `exit_target_date`, look up price return, classify attribution.

**ReplayPolicy gates (all composable):**
- `--max-hold-days N` — force exit after N calendar days
- `--catalyst-timing` — entry only 3–10 days before catalyst; `<2d` → half size
- `--xbi-filter` — block all entries when XBI below 20-day moving average
- `--cooling` — block asset 7d after 1 consecutive `thesis_error`, 14d after 2+
- `--require-catalyst-days N` — block entry if no catalyst within N calendar days (0 = disabled)
- `--decision-policy` — `top2_add`, `top1_add`, `top3_add`, etc.
- `--min-thesis-score` — minimum `thesis_strength` for entry

**Attribution taxonomy (6 types):**
- `confirmed_thesis` — positive event + positive return
- `pos_error` — negative event + positive return (market shrugged off bad news)
- `timing_error` — positive event + negative return (entered too early/late)
- `thesis_error` — no event + negative return (thesis was wrong)
- `market_drift` — no event + positive return (beta/momentum)
- `unclassified` — exit without sufficient data to classify

**No-lookahead guarantee:** isolated `replay_store.sqlite` separate from `ops.db`. `ThesisTracker.snapshot(as_of_date=...)` SQL filter prevents future-claim contamination. Attribution uses only events with `announced_at` between `entry_date` and `exit_date`.

---

## 5. Exact Formula Library

### Log-Odds Conversion
```python
# Base rate → log-odds
base_rate = max(0.01, min(0.99, base_rate))  # clip to avoid ±inf
log_odds = math.log(base_rate / (1.0 - base_rate))  # natural log

# Apply adjustment
adjustment = sum_of_adjuster_log_odds_values
adjustment = max(-0.80, min(+0.80, adjustment))  # cap the delta
log_odds_adjusted = log_odds + adjustment

# Back to probability
pos = 1.0 / (1.0 + math.exp(-log_odds_adjusted))   # sigmoid
```

### Cumulative P(Approval)
```
P(approval) = ∏ success_probability[i]   for all trial phases i

prob_reaching[0] = 1.0
prob_reaching[i] = prob_reaching[i-1] × success_probability[i-1]
```

### Revenue in Year Y (patient-based mode)
```
penetration(y) = peak_penetration × min(1, y / years_to_peak)   [linear]
revenue(y) = addressable_patients × penetration(y) × compliance_rate
             × net_price_per_patient × our_available_market_fraction(y) / 1e6
sgna_rate(y) = sgna_rate_launch + (sgna_rate_mature - sgna_rate_launch)
               × max(0, min(1, (y-1)/(years_to_peak-1)))
ebit(y) = revenue(y) × (1 - cogs_rate) - revenue(y) × sgna_rate(y)
        = revenue(y) × (1 - cogs_rate - sgna_rate(y))
```

### Discounting (Phase Cost PV)
```
pv_cost_gross_phase_i = cost_millions × cdev_cost_share
                        × (1 + inflation_rate)^mid_year_i / (1 + WACC)^mid_year_i
pv_cost_weighted_phase_i = pv_cost_gross_phase_i × prob_reaching_phase_i
```

### FCF per Commercial Year (Path A, simple tax)
```
royalty_t        = revenue_t × deal.royalty_rate
profit_share_t   = ebit_t × deal.profit_share_rate
adjusted_ebit_t  = ebit_t - royalty_t - profit_share_t
tax_rate_t       = 0 if t ≤ nol_benefit_years else effective_tax_rate
after_tax_fcf_t  = adjusted_ebit_t × (1 - tax_rate_t)
captured_t       = after_tax_fcf_t × net_ownership
pv_captured_t    = captured_t / (1 + WACC)^(years_to_approval + t)
```

### rNPV
```
gross_revenue_pv       = Σ_t pv_captured_t    [sum over all commercial years]
prob_adj_revenue_pv    = gross_revenue_pv × P(approval)
milestone_receipts_pv  = Σ milestone_pv(m, prob, WACC) for m in receivable_milestones
sales_threshold_pv     = Σ milestone_pv(m, prob, WACC) for m in payable_milestones (SALES_THRESHOLD type)
rNPV = prob_adj_revenue_pv - trial_costs_pv - sales_threshold_pv
       + milestone_receipts_pv + upfront_receipt
```

### NAV Per Share
```
nav_millions = rNPV × company.ownership_of(asset.id) + company.net_cash_millions
nav_per_share = nav_millions / company.shares_outstanding_millions
```

### Market-Implied POS (Back-solve)
```
implied_POS = (market_cap - net_cash + trial_costs_pv) / gross_revenue_pv
implied_peak_sales = model_peak × (implied_EV + costs_pv) / (model_POS × gross_revenue_pv)
  where implied_EV = market_cap - net_cash
```

### Composite Actionable Score
```
thesis_input = thesis_strength if thesis_strength is not None else 0.50
base_composite = ranking_score × 0.50 + thesis_input × 0.30 + opportunity_score × 0.20
composite = base_composite + Σ(signal_adjustments)  [v2.0 only]
composite = max(0.0, min(1.0, composite))
```

### Monte Carlo Log-Normal Draw
```
σ_ln = sqrt(log(1 + CV²))
μ_ln = log(base_peak) - 0.5 × σ_ln²
uniform_u = correlated_uniform_samples["peak_sales"]
peak_sales_draw = lognorm(s=σ_ln, scale=exp(μ_ln)).ppf(clip(u, 1e-6, 1-1e-6))
```

### Beta Distribution (Phase Success)
```
alpha = mean × ESS
beta_param = (1 - mean) × ESS
phase_pos_draw ~ Beta(alpha, beta_param)
```

---

## 6. Configuration / YAML Audit

### `industry_assumptions.yaml` — Key Findings

**Well-sourced entries:**
- Phase success rates cite Biomedtracker/IQVIA 2021, Thomas 2016, and Citeline 2023. The values (oncology Phase 2 = 24.8%) are consistent with published benchmarks.
- LOE erosion profiles cite IQVIA LOE Impact analysis and Bernstein biosimilar studies.
- WACC default of 0.12 cites Damodaran's Biotech sector (updated 2026-Q1).

**Judgment calls (stated as such):**
- All log-odds adjuster magnitudes in `trial_design.logodds` are explicitly labeled "EVIDENCE-INFORMED PRIORS — not statistically estimated coefficients. Magnitude is a JUDGMENT CALL."
- Competition `penetration_haircut_per_competitor` values (15% first, 10% each additional) are "JUDGMENT CALLS — directional priors."
- Competitor impact `tau_years` and `pos_delta_*` values are "internal calibration; directional only."

**Uncalibrated entries (flagged in YAML):**
- `llm_extraction.calibration_status: "uncalibrated"` — these thresholds (discard=0.30, review=0.50, auto=0.50) should not be trusted quantitatively.
- Phase correlation `alpha`, `beta`, `max_update_pp` — stated "EVIDENCE-INFORMED PRIORS — not statistically estimated."
- Pre-readout scoring thresholds — all "JUDGMENT CALLS — no literature directly calibrates these."

**Most Sensitive Assumptions for rNPV:**
1. `peak_penetration` in market model — quadratic impact (affects both revenue and peak sales)
2. Phase success rates — linear multiplier on cum_prob, multiplicative through all phases
3. `net_price_per_patient_usd` — direct multiplier on every year's revenue
4. `patent_life_years` — gate on how many discounted years of EBIT are captured
5. `discount_rate` — affects all future cash flows; more sensitive for assets far from approval
6. `cogs_rate` and `sgna_rate_launch/mature` — determine EBIT margin from which rNPV is derived

**Red Flags:**
- The 2026-Q1 WACC update raised the default from 0.10 to 0.12. Configs written before this update will use the new default silently if they don't specify `discount_rate`. Analyst override detection in `_build_provenance()` catches this for the specific default check.
- `oncology_solid` Phase 3 success rate = 42.9% is substantially lower than the broad `oncology` entry (49.5%). Assets tagged `oncology` vs. `oncology_solid` will get materially different base rates. No warning is raised on this distinction.
- `phase_cost_defaults` for cardiovascular Phase 3 = $400M is plausible for CVOT-era large-outcomes trials but is a cross-sectional median that hides enormous variance (range $50M to $2B+).
- The LOE tail assumption that post-LOE EBIT **increases** (because SG&A collapses faster than revenue) is technically correct for the model but can confuse non-expert analysts who see rising EBIT after patent expiry.

**Duplicates/Conflicts:**
- `commercial.sgna.rate_launch = 0.40` and `commercial.sgna_profiles.specialty_pharma.rate_launch = 0.40` are identical — the legacy entry exists only for backward compatibility.
- `commercial.sgna_profiles.default` maps to `specialty_pharma` which is fine, but having both increases confusion about which takes precedence.
- Phase success rates for `"oncology"` (broad) vs. `"oncology_solid"` vs. `"hematology"` are all separate entries — the broad entry remains for backward compatibility but new configs should use the granular keys.

---

## 7. Output Report Explanation

### valuation.json Fields

**Top-level structure (from `ValuationOutput` in `valuation/outputs.py`):**

- `asset` — full `Asset` object including all fields
- `company` — full `Company` object (cash, shares, burn, ticker, current price)
- `trials` — list of `ClinicalTrial` objects **after** POS model adjustment (not raw input)
- `rnpv` — `RNPVResult` with all sub-fields:
  - `rnpv_millions` — **primary output**, rounded to nearest $1M
  - `gross_revenue_pv_millions` — PV of commercial cash flows pre-probability. If you divide this by the cumulative success probability you get `probability_adjusted_revenue_pv_millions`.
  - `probability_adjusted_revenue_pv_millions` — `gross_revenue_pv × P(approval)`. What we expect to receive on average from commercial revenues.
  - `trial_costs_pv_millions` — what we expect to spend on average on trials (probability-weighted).
  - `cumulative_success_probability` — P(approval), the most important number for BD conversations.
  - `years_to_launch` — sum of remaining phase durations.
  - `peak_sales_millions` — competition-adjusted peak annual revenue.
  - `net_ownership` — equity stake in the program.
  - `nav_millions`, `nav_per_share` — total company value including net cash.
  - `royalty_deductions_pv_millions`, `profit_share_deductions_pv_millions` — deal partner's share of value.
  - `phase_breakdown` — per-phase PV cost detail.
  - `probability_result`, `revenue_stream`, `cost_stream` — full sub-objects.
  - `tax_audit` — Path B only; full year-by-year FCF breakdown.
- `scenarios` — Bull/Base/Bear `RNPVResult` objects.
- `monte_carlo` — full `MonteCarloResult`:
  - `mean_millions`, `median_millions`, `std_millions`
  - `percentile_5_millions` through `percentile_95_millions` (rounded to $5M)
  - `probability_positive` — fraction of trials with positive rNPV
  - `expected_upside`, `expected_downside` — conditional expected values
  - `downside_value_at_risk` — |P5|
  - `top_variance_drivers` — ordered list of parameter names by Spearman |r|
  - `clinical_failure_rate`, `competitor_disruption_rate`, `payer_restriction_rate`
  - `audit_trail` — P5/P50/P95 representative simulations
- `sensitivities` — 8 `SensitivityPoint` objects sorted by |swing| for tornado chart.
- `assumption_log` — structured list of every key assumption with source URL and confidence.
- `lifecycle_events_applied` — serialized list of `LifecycleEvent` effects.
- `assumptions_yaml_hash`, `config_hash` — SHA-256 audit hashes.
- `wacc_vintage` — vintage string from YAML (e.g., "2026-Q1").
- `analyst_overrides` — fields that differ from industry defaults.
- `revenue_audit_table` — year-by-year multiplier decomposition for revenue.
- `comps_fair_value_band` — comparable deal analysis (optional).

### What a BD Analyst Should Look at First

1. `rnpv.rnpv_millions` — is this deal worth doing at the proposed structure?
2. `rnpv.cumulative_success_probability` — does this match your clinical intuition?
3. `rnpv.years_to_launch` — when do cash flows actually start? Long timelines kill NPV.
4. `monte_carlo.percentile_5_millions` — the downside case under MC (not just Bear scenario).
5. `sensitivities` (tornado chart) — which one or two parameters dominate the value?
6. `rnpv.royalty_deductions_pv_millions` + `profit_share_deductions_pv_millions` — how much value goes to the partner?

### Numbers That Are Diagnostic Only
- `gross_revenue_pv_millions` — pre-probability, so not a realistic number; diagnostic only
- `assumption_log` — helps audit assumptions, not a valuation output
- `revenue_audit_table` — per-year decomposition for checking model mechanics
- `top_variance_drivers` — tells you what to worry about, not what the value is

### What Could Mislead the User

1. **Peak sales ignores ex-US**: by default, `addressable_patients_annual` is US only. The model makes no automatic upward adjustment for global revenue.
2. **The LOE tail is model-dependent**: LOE erosion profiles are applied automatically based on modality, but if an analyst uses `CommercialPlan.no_loe()`, this is silently suppressed without a visible warning in the output.
3. **rNPV rounded to $1M implies false precision**: for most Phase 2 assets, the true uncertainty is ±$200M or more. The $1M rounding looks precise but is not.
4. **MC mean vs. deterministic rNPV**: these can diverge because the MC distribution is skewed (log-normal peak sales). The MC mean is arguably a better expected value estimate, but the two numbers are presented side by side without this being explained.
5. **nav_per_share uses diluted shares**: if a company is burning cash and will need to raise equity, the share count will increase and NAV/share will decrease. The model does not project future dilution.

---

## 8. Tests and Validation

### Test Suite Coverage

**`tests/test_models.py`** (directly read)
- `TestPOSModel` — tests directional ordering (validated MoA > novel, clean safety > serious), bounds (pos in (0,1)). Does NOT test specific numerical values — only monotonicity. The test `test_base_rate_returned_with_default_adjusters` only checks `0.10 <= pos <= 0.70`, not the exact value.
- `TestMarketModel` — tests revenue curve length, zero revenue after patent, S-curve peak, linear ramp peak.
- `TestRNPV` — tests positive rNPV for base case, monotonicity (higher POS → higher rNPV, higher WACC → lower rNPV), years_to_launch accuracy, phase breakdown sum.
- `TestMonteCarlo` — tests N simulations, MC mean "near" deterministic rNPV (loose).
- `TestValuationEngine` — tests full pipeline runs, scenario generation.

**`tests/test_competition_crowding.py`** (inferred from CLAUDE.md)
Covers `CrowdingModel`, `FirstMoverConfig`, `ClassSaturationProfile` invariants.

**`tests/test_multi_indication.py`**
Covers cascade PoS arithmetic, `FranchiseCostSharing` mechanics, isolation of primary from secondary.

**`tests/test_historical_replay.py`**
Covers replay store, no-lookahead invariant, isolation from live DB.

**`tests/test_replay_policy.py`**
Covers all `ReplayPolicy` gate combinations.

### What Is NOT Tested

1. **Numerical accuracy of log-odds formula**: no test verifies that `compute_pos()` returns, say, exactly 0.4713 for a specific input combination. Only monotonicity is tested.
2. **Revenue formula arithmetic**: no test computes `revenue_in_year(3)` for a known input set and checks the exact value.
3. **rNPV formula arithmetic**: the test only checks sign and monotonicity, not the actual formula. If a constant were accidentally multiplied or dropped, the tests would not catch it.
4. **LOE tail arithmetic**: no specific test for the post-LOE revenue computation.
5. **Deal economics correctness**: no test verifies that `royalty_rate=0.10` applied to $100M revenue correctly deducts $10M × (1-tax) × net_ownership in PV terms.
6. **Gaussian copula correlation**: no test that the copula actually produces correlated samples with the specified Spearman r.
7. **Competitor S-curve vs. linear**: no test that the two ramp modes produce the expected difference at intermediate years.
8. **NAV/share computation**: no test for the NAV formula itself.
9. **Sensitivity analysis correctness**: no test that the tornado values are computed with correct input perturbation.
10. **CLI integration**: no end-to-end test that runs the CLI and checks the JSON output.
11. **LLM extraction**: no test of extraction quality or calibration.
12. **Attribution taxonomy**: no test that the 6-way classification is applied correctly to specific event/return combinations.

### Assessment of Test Quality

**Strong tests (real math):**
- Phase breakdown sum check (`assert total_from_breakdown == pytest.approx(result.trial_costs_pv_millions, abs=0.05)`) is a genuine correctness check.
- No-lookahead invariant test in replay is meaningful — it specifically checks that future-dated events don't appear in time-frozen snapshots.

**Superficial tests:**
- Most POS tests are only ordinal (A > B), not numerical. They would pass even if the log-odds formula were replaced with a linear interpolation.
- `test_positive_rnpv_for_base_case` just checks `> 0` — it would pass even if the formula had a sign error in a cost term.

### Does the Backtest Prove Correctness?

The POS backtest (`analysis/backtest.py`) validates directional skill: Brier=0.2127, AUC=0.74 on N=99 oncology programs. This is better than chance (stated: "~15% skill improvement over no-skill baseline") but not a rigorous calibration proof. N=99 is insufficient for sub-TA analysis. The dataset is oncology-only, so no validation exists for CNS, CV, rare disease, etc.

The historical replay backtest cannot reach statistical significance at N=60 (requires N≈111 for p<0.10). It demonstrates that the system can generate and record decisions, not that it has positive expected alpha.

---

## 9. Institutional-Grade Critique

### Where the Tool Is Institutionally Strong

1. **rNPV framework is textbook-correct.** The formula, probability weighting, and discounting mechanics are sound and would survive scrutiny from a pharma BD MD or buy-side quant.
2. **Explicit POS source separation.** The two-layer architecture (industry base rate + qualitative adjusters) makes the model transparent and auditable. The source of each adjustment is traceable.
3. **Deal economics are sophisticated.** Royalty vs. profit-share distinction, milestone trigger types, co-dev cost share, and the separation of revenue-level from EBIT-level deal deductions show genuine BD domain knowledge.
4. **Competition model is genuinely dynamic.** Time-varying competitor ramps, S-curve adoption, first-mover bonus, and class saturation are features absent from most Excel-based BD models.
5. **Audit trail is solid.** SHA-256 hashing, provenance metadata, and structured assumption logs make runs reproducible and auditable. This matters in institutional settings.
6. **No-lookahead replay is technically correct.** The SQL time-freeze plus Python post-processing for resolution timing is a genuine prevention of the most common backtest flaw.

### Where the Tool Is Fragile

1. **All inputs are analyst-entered YAML.** The model is only as good as the assumptions. There is no automated cross-check between YAML inputs and public data (ClinicalTrials.gov, SEC filings, etc.).
2. **The POS adjuster magnitudes are unjustified.** Saying "`STRONG_REPLICATED` prior phase data = +0.30 log-odds" is an assertion, not a calibration. If the true magnitude is +0.15 or +0.50, the model's output could be off by 10-20 percentage points in absolute POS.
3. **Monte Carlo does not vary trial cost or LOE.** Cost uncertainty is not sampled — the trial cost is fixed at the analyst's point estimate for all 10,000 trials. Similarly, LOE profile is fixed. For BD decisions where cost uncertainty is meaningful (Phase 3 cost overruns are common), this understates total rNPV uncertainty.
4. **Competition modeling requires accurate competitor inputs.** The `CompetitionModel` can produce significantly wrong outputs if the analyst mis-estimates competitor peak market share or launch timing. There is no validation against real launch analogs.
5. **No stochastic phase timing.** Phase duration is fixed at the analyst's estimate. Real trials run long 30-50% of the time. This understates uncertainty in `years_to_approval` and therefore in all discount factors.

### Double-Counting Risks

1. **Biomarker selection in both Layer 1 and endpoint type.** `biomarker_selection = VALIDATED` (+0.40) and `endpoint_type = HARD_CLINICAL` (+0.40-0.45) can both be set for a biomarker-selected OS trial. The endpoint score partially reflects that biomarker-selected trials are better powered and more likely to succeed — some overlap exists. `check_pos_layer_overlap()` does not catch this.
2. **Cascade PoS in multi-indication modeling vs. per-trial POS.** The secondary's own trials already carry success probabilities conditioned on the mechanism working (since they're expansion trials). The cascade multiplier then multiplies by the primary's P(approval) again. If the secondary trials' success probabilities are already conditioned on primary success, this double-counts the clinical dependency. The CLAUDE.md note "The secondary DrugAssetProgram's own trial success probabilities are NOT modified — they represent the additional clinical risk conditional on the primary mechanism having worked" suggests the intent is to NOT double-count, but ensuring this in practice depends entirely on how the analyst sets the secondary's `success_probability`.
3. **Competitive pressure in POS (Layer 1) and competition model in revenue.** `competitive_pressure = HIGH_BAR` reduces POS, correctly modeling regulatory bar. The `CompetitionModel` reduces revenue, correctly modeling market share. These are genuinely separate effects — but an analyst might also intuitively reduce `peak_penetration` for the same reason, triple-counting the competitive effect.

### False Precision Risks

- `rnpv_millions` rounded to $1M on assets where Phase 2 PoS uncertainty alone generates ±$200M standard deviation.
- Phase success rates cited to 3 decimal places (e.g., 24.8%, 48.9%) from published aggregates that themselves have wide confidence intervals.
- LOE erosion profiles with 5 decimal places of fraction (e.g., `year_1_loss: 0.40`) presented as established benchmarks.

### Calibration Gaps

- The POS model has AUC=0.74 on N=99 oncology programs only. No calibration data for other TAs.
- The LLM extraction module is explicitly self-labeled "uncalibrated."
- The composite actionable score weights (0.50/0.30/0.20) have no calibrated empirical basis — they are stated as design choices.
- Signal layer weights in v2.0 scoring (`catalyst_ev: 0.15`, `endpoint_z: 0.05`, etc.) appear to be expert judgment, not regression outputs.

### What Should Be Labeled "Directional Only"

1. Any single rNPV number — the correct output is a distribution, not a point estimate.
2. The POS model output — always present as a range (base ± sensitivity).
3. The intelligence-layer composite scores — not predictive of return with demonstrated statistical significance.
4. Historical replay results until N≥111 decisions are accumulated.
5. Any cross-TA POS estimates beyond oncology — uncalibrated.

---

## 10. Code-Level Issues

### Actual Bugs Found

1. **`_compute_sensitivities()` calls `_rnpv()` with no arguments at line 539** in `valuation_engine.py`:
   ```python
   _rnpv()  # ← This is a wasted compute call, result discarded
   ```
   Line 539 calls `_rnpv()` with no arguments and discards the result. This appears to be a dead function call left from refactoring — it runs the full engine recomputation unnecessarily and silently.

2. **Audit trail `clinical_draw` is max phase prob, not cumulative PoS.** In `monte_carlo.py` line 621:
   ```python
   cum_pos = max(drw.phase_success_probs.values()) if drw.phase_success_probs else 0.0
   ```
   This uses `max()` across phase draws, not the product. It should be the product to represent cumulative P(approval) for the simulation. This is a bug in the audit record, though it doesn't affect the rNPV computation itself.

3. **`_lognormal_mult()` uses wrong scale for mean.** In `monte_carlo.py` line 476:
   ```python
   return lognorm(s=s, scale=np.exp(-0.5 * s ** 2)).rvs(n, random_state=rng)
   ```
   `scale=exp(-0.5s²)` makes the **median** = 1.0, but the **mean** of a log-normal is `exp(μ + 0.5σ²)`. If `μ = -0.5s²`, then `mean = exp(-0.5s² + 0.5s²) = exp(0) = 1.0` — actually correct. The comment "mean≈1" in the code is right. Not a bug, but the explanation is confusing.

### Dead Code / Duplicate Logic

1. **`compute_rnpv()` backward-compatible wrapper** at the bottom of `rnpv_model.py` — functionally dead for internal engine use (all paths now call `compute_rnpv_full()`). Kept for external callers but not tested specifically.

2. **Legacy boolean fields in `POSAdjusters`** (`biomarker_selected_population`, `strong_prior_phase_data`) — deprecated but still accepted, mapped via `model_validator`. These are backward-compat debt that will need maintenance.

3. **Legacy broad TA entries** (`oncology`, `rare_disease`, `cns`) in `phase_success_rates` alongside granular entries (`oncology_solid`, `hematology`, `psychiatry`). The broad entries remain for backward compat but create ambiguity.

### Hardcoded Values That Should Be in Config

1. `_COMPETITION_HAIRCUT_PER_ENTRANT = 0.15` at line 639 of `valuation_engine.py` (in `_compute_sensitivities`) — this is already in `industry_assumptions.yaml` under `competition.penetration_haircut_per_competitor.first_competitor`, but the code does not read it from there. Two sources of truth for the same value.

2. `_AA_NDA_DISCOUNT: float = 0.18` at the top of `pos_model.py` — this is also in `industry_assumptions.yaml` as `pos_model.accelerated_approval_nda_discount: 0.18`. The code in `pos_model.py` doesn't read from the YAML; it uses the hardcoded constant. Two sources of truth, could diverge if one is updated.

3. Sensitivity shock magnitudes (±30% peak sales, ±2pp discount rate, ±20% POS, ±3yr patent life, ±30% penetration, ±5pp tax, ±10pp G2N, ±1/2 competitor entries) are hardcoded throughout `_compute_sensitivities()` with no reference to config.

### Inconsistent Naming

- `gross_revenue_pv_millions` in `RNPVResult` is described as "Pre-probability PV of post-deal, after-tax, ownership-adjusted EBIT" — it's not "gross revenue" at all, it's a PV of net FCF. The name is misleading. The field docstring clarifies this but the name remains confusing.
- `trial_costs_pv_millions` includes CMC costs, post-approval R&D, and milestone payments — not just "trial costs." Same naming/content mismatch.

### Functions That Are Too Large

- `ValuationEngine.run()` at ~150 lines handles: POS preparation, SG&A resolution, revenue sanity, confirmatory obligation check, cost defaults, four-engine rNPV, NAV calculation, scenarios, Monte Carlo, sensitivity, assumption log, lifecycle events, provenance, comparable deals, and output construction. This is architectural debt acknowledged in the code comment "Sensitivity and scenario analysis still call compute_rnpv() — architectural debt."

- `run_monte_carlo()` at ~280 lines handles parameter sampling, copula correlation, DRIVER_BASED vs. SIMPLE mode, all 10,000 trial iterations, variance driver computation, audit trail construction, and conditional threshold probabilities.

### Missing Docstrings

- `_apply_trial_cost_defaults()` has a docstring but `_check_compliance_rate()` does not.
- `_run_single_trial()` has a good docstring; `run_monte_carlo()` has acceptable documentation.
- Many small helper functions in `market_model.py` lack docstrings.

---

## 11. End-to-End Example: RLY-2608 (Relay Therapeutics)

### Input Values from `relay_rly2608.yaml`

**Asset:**
- Indication: PIK3CA H1047R HR+/HER2- mBC (2nd/3rd line, US)
- TA: `oncology`, Stage: `phase_2`, Modality: `small_molecule`
- WACC: 10%, Royalty rate: 0% (fully owned)

**Company (Q4 2024):**
- Net cash: $410M, Shares: 93.5M diluted, Stock price: ~$5.80

**Remaining Trials:**
| Phase | P(Success) | Duration | Cost |
|---|---|---|---|
| Phase 2 | 0.50 (raw; POS model overrides) | 2.0 yr | $85M |
| Phase 3 | 0.60 (raw) | 3.5 yr | $280M |
| NDA/BLA | 0.87 (raw) | 1.5 yr | $35M |

**POS Model Adjusters (Phase 2 as example):**
- endpoint_type: `surrogate_validated` (+0.00 in oncology TA: `ORR → -0.025`)
- moa_precedent: `validated` (+0.35)
- sample_size_adequacy: `borderline` (-0.20)
- safety_profile: `clean` (+0.10)
- competitive_pressure: `high` = `elevated_bar` (-0.15)
- biomarker_selected_population: `true` → maps to `VALIDATED` (+0.40)
- strong_prior_phase_data: `true` → maps to `STRONG_SINGLE` (+0.20)

Layer 1 net adjustment Phase 2: `-0.025 + 0.35 - 0.20 + 0.10 - 0.15 + 0.40 + 0.20 = +0.675`
Cap at +0.80 → capped at +0.675 (under cap).

Base rate oncology Phase 2 = 24.8%
log_odds_base = log(0.248 / 0.752) = log(0.330) = -1.109
Adjusted log_odds = -1.109 + 0.675 = -0.434
P(Phase 2 success) = 1 / (1 + exp(0.434)) = 1 / (1 + 1.544) ≈ 0.393 ≈ 39%

Layer 2 (design model, Phase 2): `single_arm` + `accelerated_approval`
From YAML: single_arm_objective = -0.10 (at Phase 2 scaling 0.50): net = -0.05
accelerated_validated_surrogate = -0.05 (at Phase 2 scaling 0.50): net = -0.025
Total Layer 2: -0.075, capped at -0.60 → -0.075
P(Phase 2) post-Layer 2: exp(-0.434 - 0.075) / (1 + exp(-(-0.434-0.075))) ≈ 0.375 ≈ 37-38%

**Market Model:**
- Addressable patients: 17,000/year (H1047R-selected, US)
- Net price: $180,000/year
- Peak penetration: 22%
- Years to peak: 5
- Patent life: 12 years
- COGS: 15%, SG&A launch: 40%, SG&A mature: 20%

**Peak sales calculation:**
```
peak_sales = 17,000 × 0.22 × 1.0 × $180,000 / 1e6
           = 17,000 × 0.22 × 180,000 / 1,000,000
           = 3,740 × 180,000 / 1,000,000
           = 673,200,000 / 1,000,000
           = ~$673M peak annual revenue
```

**EBIT at peak (year 5+):**
```
gross_profit = $673M × (1 - 0.15) = $673M × 0.85 = $572M
sgna_mature = $673M × 0.20 = $135M
EBIT at peak = $572M - $135M = $437M
```

**Cumulative P(approval) (approximate, using POS-model-adjusted values):**
Using estimated adj. probabilities ~Phase 2 = 0.38, Phase 3 = 0.60 (with positive adjusters), NDA = 0.87:
```
P(approval) ≈ 0.38 × 0.60 × 0.87 ≈ 0.198 ≈ ~20%
```

**Years to approval:**
```
2.0 + 3.5 + 1.5 = 7.0 years
```

**Rough rNPV order of magnitude:**
PV of EBIT stream (12-year patent, 10% WACC, launch at year 7):
- Peak EBIT ~$437M but ramping; rough average ~$300M/yr × 12 years
- Discount factor for midpoint year 13 (7+6) at 10% ≈ 0.28
- Rough un-probability-adjusted PV of EBIT ≈ $300M × 12 × 0.28 ≈ $1.0B (very rough)
- After tax (21%): $1.0B × 0.79 = $790M
- × P(approval) ≈ 20%: $158M
- Less trial costs PV (Phase 2+3+NDA at prob-weighted, discounted): ~$85M+$280M+$35M roughly → PV maybe $150-200M × prob_reaching → ~$120M
- Rough rNPV ≈ $158M - $120M ≈ **$38-80M** (directional estimate)

**NAV/share (approximate):**
```
NAV ≈ rNPV × 100% ownership + $410M net cash
    ≈ $80M + $410M = $490M
NAV/share = $490M / 93.5M shares ≈ $5.24/share
```

Stock price at analysis: ~$5.80. This suggests the market is roughly pricing the asset at model value or even with a slight premium — consistent with the YAML comment that "market implies ~20% P(approval)" while the model computes ~20% as well. The variant perception thesis in the YAML claims the market is wrong on qualitative factors (inavolisib validation, selectivity), but the numbers suggest close alignment at these assumptions.

**Plain English Interpretation:**
RLY-2608 is a Phase 2 oncology asset with roughly 1-in-5 odds of FDA approval. At a 22% market share assumption in a ~17,000-patient H1047R-selected US population priced at $180K net, peak revenues could reach ~$670M annually. After tax and 10% cost of capital, that's worth about $80M in risk-adjusted terms, plus the company holds $410M in cash. The $5.80 stock price is roughly consistent with these assumptions — there is limited quantitative mispricing visible, but if the Phase 2 ORR data is strong (≥50% confirmed ORR), the model POS would jump from ~20% to potentially 30-35%, adding $80-120M to rNPV or roughly $1-1.30/share incremental value.

---

## 12. Beginner Explanation

### What This Tool Does and Why

A biotech drug in Phase 2 clinical trials might reach patients and generate billions in sales — or it might fail the trial next year. Nobody knows which outcome will happen. What investors and business development professionals can do is make educated bets based on probability: "Assets like this one, with this mechanism, in this indication, historically succeed about 37% of the time at Phase 2."

This tool takes that probability-based thinking and makes it rigorous. Instead of a gut feeling, you get a number: the "risk-adjusted net present value" (rNPV). This is what a drug program is worth if you could buy thousands of identical copies and let probability play out. It's the average outcome weighted by how likely it is.

### How Each Piece Connects

1. **You describe the drug** (YAML config): What disease? What phase? How big is the potential market? How much will it cost to run the remaining trials?

2. **The POS model estimates success probabilities**: Based on 14 years of industry data (Biomedtracker/IQVIA), it knows that oncology Phase 2 trials succeed ~25% of the time. Then it adjusts up or down based on qualitative factors: Is the mechanism well-validated? Is the safety profile clean? Is the patient population biomarker-enriched? All adjustments happen in "log-odds space" which keeps the probability between 0% and 100%.

3. **The revenue model builds the commercial case**: If approved, how many patients would use it? At what price? How quickly would it capture market share? How much do competitors already control? This produces a year-by-year revenue forecast for the full patent period.

4. **The cost model discounts trial costs**: Running Phase 3 costs $280M, but it won't start for 2 years (after Phase 2). Its "present value" today is lower due to time discounting. And it's probability-weighted — we only spend it if we actually advance to Phase 3, which depends on Phase 2 succeeding.

5. **The rNPV model combines everything**: `rNPV = P(approval) × PV(future profits) − PV(trial costs)`. If P(approval) is 20% and future profits if approved are worth $500M today, that's $100M expected profit. Subtract $80M in expected trial costs, and rNPV = $20M.

6. **Monte Carlo shows the distribution**: Run 10,000 versions of this with slightly different assumptions each time (the Phase 2 might succeed or fail; peak sales might be higher or lower; the discount rate might fluctuate). The result is a distribution: 5% of scenarios you get −$50M, 50% of scenarios you get $15M, 95% of scenarios you get $180M. This is more honest than a single number.

7. **The intelligence layer tracks whether your thesis is playing out**: Did the Phase 2 ORR data come in strong? Did the competitor fail? Did FDA grant Breakthrough designation? These events are tracked as "claims" with outcomes, letting you update your thesis systematically rather than narratively.

### What to Trust vs. Not Trust

**Trust:**
- The structure of the model (it's industry-standard rNPV)
- The qualitative direction of adjustments (better safety = higher POS)
- The tornado chart (tells you which variable matters most)
- The Monte Carlo distribution shape (even if absolute values are uncertain)
- The audit trail and provenance metadata

**Be Skeptical Of:**
- The exact rNPV number — it could easily be off by 50% depending on peak penetration assumptions
- Phase 3 POS estimates when based on limited Phase 2 data
- The intelligence layer's composite scores — not statistically validated yet
- Any single output without reading the assumption log
- The implied POS back-solve for diversified companies (assumes single-asset proxy)

---

## 13. Improvement Roadmap

### Must-Fix (Bugs)

1. **Remove the wasted `_rnpv()` call** at line 539 of `valuation_engine.py`. It runs the full engine needlessly. Low risk, instant savings.
2. **Fix `clinical_draw` in `SimulationAuditRecord`** to use the product of phase draws (cumulative PoS), not the max. Change `max(drw.phase_success_probs.values())` to `∏(drw.phase_success_probs.values())`.
3. **Unify the two sources of `_AA_NDA_DISCOUNT`**: `pos_model.py` hardcodes 0.18; `industry_assumptions.yaml` also stores it. One should read from the other.
4. **Unify the two sources of `penetration_haircut_per_entrant`**: `valuation_engine.py` line 639 hardcodes 0.15; the YAML has the same value. The engine should read from `AssumptionsLoader`.

### High-ROI Improvements

1. **Add phase duration uncertainty to Monte Carlo.** Draw `duration_years` from a right-skewed distribution (clinical trials run long 30-50% of the time). This is the biggest missing source of rNPV uncertainty.
2. **Add trial cost uncertainty to Monte Carlo.** Draw `cost_millions` from a distribution with meaningful spread (Phase 3 cost overruns of 2-3x are not rare). Currently cost is fixed.
3. **Add numerical precision tests.** Add one or two tests that fix all inputs and check exact `rnpv_millions` values with `pytest.approx()`. The current suite doesn't verify formula correctness.
4. **Improve `gross_revenue_pv_millions` naming.** Rename to `gross_fcf_pv_millions` or add clear docstring that it is NOT gross revenue but probability-weighted, after-tax, ownership-adjusted FCF PV. Currently deeply misleading.
5. **Add global revenue expansion.** A `global_revenue_multiplier` on `MarketModel` (e.g., 1.40 for typical US→global) would let analysts capture ex-US value without building full `GeographySplit` configs.
6. **Calibrate POS log-odds magnitudes** by running regression on the oncology backtest dataset (`n=99`) to see if the Layer 1 adjusters actually predict Phase 2/3 success better than the base rates alone.

### Nice-to-Have

1. Add SOTP (sum-of-parts) automatic aggregation when multiple asset configs are in the same portfolio YAML.
2. Add `--watch` mode to CLI that re-runs valuation when the config YAML changes (useful during live analysis sessions).
3. Export charts as SVG (currently PNG/matplotlib) for vector-quality BD presentations.
4. Add a `--compare` flag to `bve-asset` that diffs two valuation runs side-by-side.

### Data Improvements

1. **POS model calibration on larger dataset**: expand from N=99 oncology to 200+ programs across multiple TAs. Add CNS (the hardest TA) and rare disease programs.
2. **Market model validation**: compare 5-10 historical drug launches against what the model would have predicted for peak sales at Phase 2 stage. Identify systematic biases.
3. **LOE erosion profile validation**: compare modeled LOE curves to actual revenue histories for small molecules and biologics post-LOE.

### Validation Improvements

1. Calibrate `llm_extraction` confidence thresholds on 200+ labeled signal outcomes (required by the YAML's own `calibration_required_n: 200`).
2. Extend historical replay date range to accumulate N≥111 decisions for p<0.10 statistical graduation.
3. Implement Platt scaling or isotonic regression for probability calibration of the POS model predictions.

### What Would Make This Credible to Pharma BD/VC/Hedge Fund

1. Third-party calibration of the POS model against a held-out dataset (not used in model development).
2. Formal documentation of the model methodology (equivalent to a sell-side quant model white paper).
3. Track record: a live log of decisions made, with outcomes tracked vs. model predictions, for at least 12-18 months.
4. Independent audit of the rNPV formula implementation vs. the published specification.
5. Explainable UI that shows all assumptions with one-click drill-down for any output number.

---

## 14. Final Deliverables

### One-Page Summary

The Biotech Asset Valuation Engine is a Python framework that implements the standard pharmaceutical rNPV model with significant extensions:

**Core:** `YAML config → ValuationEngine → ProbabilityModel × RevenueModel × CostModel × RNPVModel → BD memo + JSON + charts`

**POS model:** Two-layer log-odds adjuster system on top of industry base rates (Biomedtracker/IQVIA). Layer 1: 8 qualitative adjusters (endpoint, MoA, sample size, safety, competition, biomarker, prior data, BTD). Layer 2: trial design quality (bias control, comparator fit, regulatory pathway risk). Results in a capped, TA-specific probability estimate.

**Revenue:** Three modes (patient-based, TAM-based, lines-of-therapy). Competition model with dynamic competitor ramps. LOE erosion tail for 5 post-patent years. SG&A and COGS auto-calibrated to modality.

**Cost:** Probability-weighted PV of trial costs, deal milestones, CMC, post-approval R&D.

**rNPV:** `P(approval) × PV(after-tax FCF × ownership) - costs + milestone income`. Deal economics handle royalty/profit-share stacking.

**Monte Carlo:** 10,000 correlated draws (Gaussian copula). Full engine rerun per trial. Spearman variance decomposition.

**Intelligence:** SQLite-backed claim tracking, thesis strength computation, weekly actionable scoring (ranking×50% + thesis×30% + opportunity×20%), historical replay with no-lookahead guarantee.

**Honest assessment:** Structurally sound, well-engineered, and more sophisticated than typical Excel-based BD models. The POS model adjuster magnitudes are judgment calls, not calibrated. Test suite verifies ordinal relationships but not formula numerics. Statistical track record insufficient for institutional investment use without additional validation.

---

### Table of Every Module/File with One-Line Description

| File | Description |
|---|---|
| `valuation/valuation_engine.py` | Main orchestrator: sequences all models and produces ValuationOutput |
| `models/pos_model.py` | Two-layer probability-of-success model with log-odds adjusters |
| `models/probability_model.py` | Walks trials forward to compute cumulative P(approval) and timing |
| `models/revenue_model.py` | Builds year-by-year revenue, gross profit, and EBIT from MarketModel |
| `models/cost_model.py` | Discounts and probability-weights all trial R&D and deal costs |
| `models/rnpv_model.py` | Combines ProbabilityResult, RevenueStream, CostStream into rNPV |
| `models/drug_asset_program.py` | Frozen container for all program inputs; three-state CommercialPlan |
| `models/deal_economics.py` | Deal terms: royalty, profit share, milestones, co-dev cost share |
| `models/competition_model.py` | Time-varying competitive dynamics with crowding, first-mover, saturation |
| `models/multi_indication.py` | Multi-indication rNPV with cascade PoS and franchise cost sharing |
| `models/market_model.py` | Commercial revenue model: three modes, S-curve, competition, lifecycle events |
| `models/monte_carlo.py` | 10,000-trial correlated Monte Carlo simulation with full engine rerun |
| `models/trial_design_features.py` | Layer 2 POS: evidence quality, comparator fit, regulatory pathway risk |
| `config/industry_assumptions.yaml` | Single source of truth for all calibrated industry priors |
| `config/assumptions_loader.py` | Singleton that loads and caches the YAML; immutable MappingProxyType |
| `analysis/implied_probability.py` | Back-solves market-implied POS and peak sales from stock price |
| `analysis/backtest.py` | Validates POS model against N=99 historical oncology outcomes |
| `valuation/scenario.py` | Builds Bull/Base/Bear scenarios with parameter shocks |
| `valuation/outputs.py` | ValuationOutput container and JSON/memo/chart export |
| `reporting/export.py` | Writes valuation.json with full artifact including meta and assumptions |
| `reporting/memo_generator.py` | Renders Jinja2 templates → Markdown → .docx BD/VC/HF memos |
| `visualization/valuation_charts.py` | Produces 5 matplotlib charts (tornado, MC distribution, revenue, etc.) |
| `intelligence/knowledge_layer.py` | SQLite-backed store for all intelligence data |
| `intelligence/thesis_tracker.py` | Manages structured thesis claims; computes thesis_strength |
| `intelligence/actionable_output.py` | Weekly actionable report with composite scoring and action thresholds |
| `ops/historical_replay.py` | Time-frozen historical replay with no-lookahead guarantee |
| `ops/weekly_runner.py` | UNIVERSE of 27 tracked assets; weekly decision runner |
| `cli/run_asset.py` | CLI entry point for single asset valuation |
| `cli/run_batch.py` | CLI entry point for batch valuation over directory of configs |
| `entities/asset.py` | Asset domain entity with all drug/program metadata fields |
| `entities/trial.py` | ClinicalTrial entity with phase, success_probability, endpoints |
| `entities/company.py` | Company entity with cash, shares, burn rate, ownership stakes |

---

### Glossary of Key Terms

| Term | Definition |
|---|---|
| rNPV | Risk-adjusted Net Present Value: expected NPV weighted by probability of approval |
| POS | Probability of Success: probability that a trial phase succeeds |
| Log-odds | log(p/(1-p)); linear space for combining multiplicative probability adjustments |
| Cumulative P(approval) | Product of all phase success probabilities; overall approval probability |
| WACC | Weighted Average Cost of Capital; the discount rate applied to future cash flows |
| NOL | Net Operating Loss; accumulated tax losses that shelter future income from cash tax |
| EBIT | Earnings Before Interest and Tax; pre-tax operating profit |
| FCF | Free Cash Flow; EBIT after tax, capex, and working capital |
| Peak sales | Maximum annual revenue during the patent protection period |
| LOE | Loss of Exclusivity; when the patent expires and generics/biosimilars enter |
| G2N | Gross-to-Net; rebates, chargebacks, and discounts reducing WAC to net price |
| cdev_cost_share | Co-development cost share; fraction of R&D costs the company bears in a deal |
| CommercialPlan | Three-state container for LOE erosion assumptions (unset/suppressed/loaded) |
| cascade_pos | Multi-indication: secondary rNPV multiplied by primary P(approval) |
| ThesisClaim | Structured, verifiable investment thesis assertion with lifecycle states |
| thesis_strength | n_confirmed / (n_confirmed + n_refuted + n_expired) |
| ScoredCandidate | Input to ActionableGenerator with ranking, thesis, and opportunity scores |
| ReplayClock | Week-by-week time advance mechanism for no-lookahead historical simulation |
| ESS | Equivalent Sample Size; Beta distribution width parameter (higher = tighter) |
| Gaussian copula | Statistical method to impose correlations between independently sampled variables |

---

### 20 Most Important Assumptions

1. **Oncology Phase 2 base rate = 24.8%** (Biomedtracker 2021) — most-used single number
2. **Default WACC = 12%** for clinical-stage biotech (2026-Q1 vintage)
3. **LOE Year 1 loss fractions** (small molecule: 40%, biologic: 20%) — post-patent value driver
4. **COGS rate by modality** (small molecule: 12%, cell therapy: 60%) — EBIT margin driver
5. **SG&A launch rate = 40%, mature = 20%** (specialty pharma default)
6. **MC peak_sales_cv by stage** (Phase 2 = 0.45, Phase 3 = 0.30) — MC distribution width
7. **Accelerated approval NDA discount = 18%** for AA programs
8. **BTD log-odds = +0.05** (small; BTD is process, not probability)
9. **Layer 1 cap = ±0.80 log-odds** (bounds analyst adjustment)
10. **Phase durations** (Ph1=1.5yr, Ph2=2.5yr, Ph3=3.5yr, NDA=1.5yr) — time-to-value driver
11. **Phase cost medians by TA** (e.g., CV Phase 3 = $400M) — trial cost estimates
12. **Post-LOE SG&A fraction = 0.25-0.30** of mature branded rate — post-LOE margin
13. **Competitive pressure haircut = 15% first entrant, 10% each additional** (in sensitivity only)
14. **Biomarker validated enrichment = +0.40 log-odds** — largest single positive adjuster
15. **STRONG_REPLICATED prior phase data = +0.30 log-odds**
16. **US effective tax rate = 21%** (post-TCJA)
17. **MC ESS values** (NDA=45, Ph3=25, Ph2=25, Ph1=20) — tightness of POS priors
18. **Composite score weights** (ranking 50%, thesis 30%, opportunity 20%)
19. **Gene/cell therapy COGS = 45-60%** of net revenue (highest modality cost)
20. **Orphan/rare disease Phase 3 success = 60.4%** (above average; orphan FDA engagement)

---

### 20 Biggest Risks / Limitations

1. All inputs are analyst-entered; garbage in, garbage out — no auto-validation against live data
2. POS adjuster magnitudes are expert judgment, not empirically calibrated regression coefficients
3. No stochastic phase timing — trial delays are not modeled in Monte Carlo
4. No stochastic trial costs — Phase 3 overruns are not sampled
5. US-only by default — ex-US value routinely excluded
6. Single-asset market cap proxy for implied POS back-solve — invalid for diversified companies
7. POS model calibrated only on oncology (AUC=0.74, N=99) — untested in other TAs
8. LLM extraction explicitly self-labeled "uncalibrated" — cannot trust confidence scores
9. Intelligence composite scores have no demonstrated statistical predictive validity
10. Historical replay N=60 decisions — insufficient for p<0.10 statistical significance
11. Double-counting risk: biomarker enrichment appears in both endpoint-type scoring and biomarker_selection adjuster
12. Double-counting risk: competitive pressure in both POS (Layer 1) and peak_penetration (market model)
13. Cascade PoS in multi-indication modeling depends on analyst correctly conditioning secondary trial probabilities
14. The post-LOE EBIT increases (due to SG&A collapse) can mislead non-expert analysts
15. Wasted engine call at line 539 of valuation_engine.py (cosmetic performance bug)
16. `clinical_draw` in MC audit record uses max() instead of product of phase probabilities (incorrect metric)
17. Sensitivity shock magnitudes (±30%, etc.) are hardcoded — no sensitivity-range configuration
18. `gross_revenue_pv_millions` name is misleading — it is not gross revenue
19. Phase correlation update (Wave 4) thresholds are explicitly uncalibrated
20. survivorship bias warning in portfolio backtest: delisted names excluded from yfinance returns

---

### 20 Best Next Improvements

1. Add stochastic phase duration to Monte Carlo (right-skewed distribution, CV ~0.35)
2. Add stochastic trial costs to Monte Carlo (log-normal with CV ~0.40 per phase)
3. Fix `clinical_draw` bug in SimulationAuditRecord to use product of phase probabilities
4. Remove wasted `_rnpv()` call at line 539 of valuation_engine.py
5. Unify the two sources of `_AA_NDA_DISCOUNT` constant (code vs. YAML)
6. Add numerical precision tests for rNPV formula with known-answer test cases
7. Rename `gross_revenue_pv_millions` to `gross_fcf_pv_millions` to eliminate misleading name
8. Calibrate POS log-odds adjuster magnitudes against N=99 oncology dataset regression
9. Expand POS backtest dataset to include CNS, cardiovascular, and rare disease programs
10. Add `global_revenue_multiplier` field to MarketModel for quick ex-US approximation
11. Accumulate historical replay decisions to N≥111 for p<0.10 graduation
12. Implement LLM extraction calibration (Platt scaling) once N=200 labeled outcomes exist
13. Unify hardcoded sensitivity haircut (0.15) with YAML `competition.penetration_haircut_per_competitor`
14. Add `--compare` CLI flag to diff two valuation runs side-by-side
15. Add automatic cross-check of analyst-entered YAML inputs against publicly available ClinicalTrials.gov data
16. Produce a formal methodology white paper suitable for institutional review
17. Track live decision log with outcomes for 12-18 months to establish empirical track record
18. Add SOTP auto-aggregation across multi-asset portfolios in a single CLI command
19. Build explained dashboard view showing full assumption chain for any output number
20. Add explicit warning when `peak_penetration` × `addressable_patients` produces an implausibly large peak sales figure vs. comparable drug launches

---

*Report generated from direct source code reading: 2026-05-14. All file paths are relative to `\\wsl.localhost\ubuntu\home\djmann\projects\biotech-asset-valuation-engine\src\bve\`.*
