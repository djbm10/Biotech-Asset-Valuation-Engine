# Biotech Asset Valuation and M&A Engine — Exhaustive Institutional Technical Report

**Date:** 2026-05-31
**Project root:** `/home/djmann/projects/biotech-asset-valuation-engine`
**Source of truth:** Current repository code and configs
**Style reference checked:** `Old_report` is empty in this checkout; `bve_technical_report.md` is the usable older detailed technical report. It is used only as a style/depth reference.
**Report purpose:** Institutional review of implemented valuation, M&A, intelligence, replay, and validation logic.
**Status convention:** Implemented in code | Partially implemented | Config-driven but not validated | Planned / aspirational | Missing but needed

## How to Read This Report

This report follows the older technical report's format: it starts with a plain-English business summary, then maps the codebase, then explains the math and model logic with formulas, guardrails, and limitations. Every substantive claim is classified against the current repository. Where the code contains a module but the data or validation is thin, the report says so directly.

The most important distinction is:

| Label | Meaning in this report |
|---|---|
| Implemented in code | The repository contains working logic, entities, CLI/API integration, or tests for the feature. |
| Partially implemented | The repo has meaningful logic, but coverage, wiring, or institutional depth is incomplete. |
| Config-driven but not validated | The model can accept the assumption, but the repo does not prove that assumption is current or empirically calibrated. |
| Planned / aspirational | The concept is described or scaffolded but not a reliable current capability. |
| Missing but needed | The feature is not materially represented and would matter for institutional use. |

**What to look at first:** an investment analyst should start with rNPV, NAV/share, market-implied POS, scenario range, and Monte Carlo downside. A BD or corporate strategy reviewer should start with acquirer fit, M&A probability drivers, control/rights gaps, and the roadmap items around profile freshness, deal structure, and seller willingness.

## 1. Executive Summary

### What the tool does

The repository implements a biotech asset valuation and decision-intelligence system. At its core, it converts a YAML-defined drug asset, company balance sheet, clinical trial path, and commercial model into a risk-adjusted net present value (`rNPV`), company NAV/share, scenario cases, Monte Carlo distribution, sensitivity analysis, market-implied expectation comparison, runway/dilution diagnostics, catalyst payoff, and memo/report outputs.

On top of the single-asset valuation engine, the repo implements a multi-layer M&A stack:

| Layer | Purpose | Current status |
|---|---|---|
| Acquisition discount screen | Compare model rNPV to market enterprise value | Implemented in code |
| Acquisition readiness | Gate early/weak Phase 2 assets unless de-risked evidence exists | Implemented in code |
| Comparable deals | Match assets to biotech precedent deals and EV/peak-sales bands | Implemented in code |
| Acquirer fit | Rank targets for one buyer using curated acquirer profiles | Implemented in code |
| M&A probability | Rank targets by acquisition attractiveness/probability across acquirers | Implemented in code, validation limited |
| BD/M&A decomposition | Institutional scorecard for asset quality, value creation, timing, fit, feasibility | Implemented as standalone modules; partially wired into main workflow |
| Catalyst hazard scaling | Dynamic 6m/18m probability scaling by catalyst days and type | Implemented in code |
| Deal encumbrance | ROFR vs ROFN vs co-development lock on closing probability | Implemented in code |
| Antitrust regime | Deal-specific antitrust scrutiny with enforcement era modifier | Implemented in code |
| Stage-specific transaction priors | Phase-adjusted acquisition vs license base rate fractions | Implemented in code |
| M&A calibration framework | Schema, no-lookahead validator, fit readiness gate for labeled dataset | Implemented in code; dataset curation pending |
| Historical replay | Replays decision policies and M&A predictions point-in-time | Implemented in code, statistically underpowered |
| Calibration overlay | Fits/logistically calibrates M&A probability from historical snapshots | Partially implemented; depends on sparse labels |

### What decisions it supports

The tool can support:

- Single-asset valuation: "What is this asset worth on a risk-adjusted basis?"
- Market disagreement: "What is the market implying versus our model?"
- Catalyst framing: "What upside/downside follows from success or failure?"
- M&A screening: "Which targets are cheap, de-risked, and strategically relevant?"
- Acquirer-target fit: "Which buyer is the most logical owner?"
- Weekly monitoring: "Which opportunities changed enough to review?"
- Replay/backtest analysis: "Did a historical decision policy have signal?"
- POS uncertainty: "What is the confidence interval around this success probability?"

It should not yet be used as an autonomous investment or BD decision engine. It is strongest as a structured research and prioritization layer.

### Current maturity level

| Area | Maturity |
|---|---|
| Core rNPV math | High relative to prototype tools; implemented, modular, tested |
| POS and trial-design model | Good architecture; substantially expanded with 20+ adjusters, base rate hierarchy, uncertainty intervals |
| Revenue model | Broad feature surface; accuracy depends heavily on input quality |
| Cost model | Solid probability weighting; CMC and inflation included |
| Monte Carlo | More advanced than old report; includes timing/cost/financing options |
| M&A acquirer fit | Useful screening-grade model; BD data depth still limited |
| M&A probability | Directionally useful; catalyst hazard, encumbrance, antitrust now modeled |
| Historical replay | Implemented; current N too small for confident alpha claims |
| Persistence/API/UI | Present, but not the primary institutional validation issue |

### Strongest parts

- The valuation pipeline is cleanly separated: `ProbabilityModel -> RevenueModel -> CostModel -> RNPVModel`.
- rNPV, NAV/share, market-implied POS, Monte Carlo, and sensitivity are inspectable.
- The engine uses typed Pydantic entities and config validation.
- Acquisition screen reuses the same rNPV math and explicitly avoids double-counting POS.
- Acquirer profiles are typed, source-referenced, and support pipeline gaps, modality preferences, priorities, budget, recent deals, and existing partnerships.
- Historical replay records point-in-time discipline and warns when statistical significance is absent.
- POS model now has 20+ log-odds adjusters, a three-level base rate hierarchy, modality-specific rates for 7 modalities, 8 indication-subtype rates, and computable confidence intervals.
- M&A closing probability now separates strategic interest from closing feasibility: encumbrance and antitrust apply multiplicatively to `p_effective_close_12m` without mutating the calibrated `p_any_strategic_transaction_12m`.
- The test suite is large: latest full run reported 12,051 passed, 1 skipped.

### Weakest parts

- POS adjuster magnitudes and many M&A weights are still evidence-informed priors, not robustly calibrated coefficients.
- M&A probability is not yet supported by a large labeled takeout/control dataset.
- Several BD-critical variables are not represented deeply enough: exact IP/exclusivity dates, regional rights, change-of-control clauses, and buyer-specific internal strategy.
- Acquirer profiles are curated manually and can become stale quickly.
- Some advanced BD layers exist as modules but are not fully integrated into the default `bve-ma-probability` ranking path.
- Public data cannot reveal many deal blockers that BD teams care about.

### Biggest institutional gaps

| Gap | Why it matters |
|---|---|
| Pair-level historical calibration | Without acquirer-target labeled history, probability scores are ranking heuristics |
| Rights/control model | A perfect strategic fit may be impossible to acquire if rights are split or blocked |
| IP/exclusivity model | Deal value and LOE urgency depend on patent/exclusivity windows |
| Seller willingness evidence | Strategic fit does not mean a target will transact |
| Buyer-specific deal logic | Different pharma buyers have different thresholds, structures, and politics |
| BD source freshness | Acquirer priorities from earnings calls and deal history can stale quickly |

## 2. System Architecture

### Repo structure audited

Relevant current files and directories:

| Area | Key files/modules |
|---|---|
| Asset CLI | `src/bve/cli/run_asset.py`, `src/bve/cli/run_batch.py`, `src/bve/cli/run_portfolio.py` |
| Core valuation | `src/bve/valuation/valuation_engine.py`, `src/bve/valuation/outputs.py`, `src/bve/valuation/scenario.py`, `src/bve/valuation/scenario_tree.py` |
| Core models | `src/bve/models/pos_model.py`, `probability_model.py`, `revenue_model.py`, `market_model.py`, `cost_model.py`, `rnpv_model.py`, `monte_carlo.py`, `competition_model.py`, `tax_profile.py`, `deal_economics.py`, `cmc_costs.py` |
| POS entities | `src/bve/entities/trial.py` — `GeneTherapyConcern`, `GeneTherapyModality`, `DataMaturityLevel`, `CMCRiskLevel`, `BreakthroughDesignationType` |
| Commercial inputs | `src/bve/models/payer_access.py`, `geography.py`, `launch_archetype.py`, `commercial_model_profile.py` |
| M&A screen | `src/bve/intelligence/acquisition_screen.py`, `acquisition_readiness.py`, `comparable_deals.py`, `acquirer_fit.py`, `ma_probability.py`, `ma_scoring.py` |
| BD/M&A layers | `src/bve/intelligence/ma_bd_decomposition.py`, `ma_layer3_gate.py`, `ma_layer4_routing.py`, `ma_layer5_calibration.py` |
| M&A calibration | `src/bve/intelligence/ma_calibration_dataset.py` — `MACalibrationCase`, `validate_no_lookahead()`, `check_fit_readiness()` |
| Acquirer profiles | `src/bve/intelligence/acquirer_profiles.py`, `examples/research/acquirer_profiles/*.yaml` |
| M&A data | `research/mna/comparable_deals.yaml`, `deal_universe_2020_2026.yaml`, `pipeline_gaps.yaml`, `target_monitor.yaml`, `vulnerability_signals.yaml`, `examples/research/universe_expanded_mna.yaml` |
| Replay/backtest | `src/bve/ops/historical_replay.py`, `src/bve/analysis/replay_significance.py`, `replay_evaluator.py`, `ma_calibration.py`, `ma_backtest.py` |
| Intelligence loop | `src/bve/intelligence/knowledge_layer.py`, `thesis_tracker.py`, `decision_layer.py`, `actionable_output.py`, `weekly_review.py` |
| Persistence | `src/bve/persistence/`, `migrations/`, SQLite-backed `KnowledgeStore` tables |
| Reporting | `src/bve/reporting/`, memo templates, chart modules |
| Configs | `src/bve/config/industry_assumptions.yaml`, `targetability_rules.yaml`, `examples/configs/*.yaml`, watchlists |
| Tests | `tests/`, `tests/intelligence/`, `tests/ops/`, `tests/empirical/`, `tests/pit/`, `tests/stress/` |

### Current outputs

| Output | Status | Source |
|---|---|---|
| `valuation.json` | Implemented | `ValuationOutput` serialization |
| BD/VC/HF memos | Implemented | `src/bve/reporting/templates/*_memo.md.j2` |
| Charts | Implemented | `src/bve/reporting/charts.py`, `src/bve/visualization/*` |
| Acquisition screen report | Implemented | `bve-acquisition-screen` |
| Acquirer fit report/JSON | Implemented | `bve-acquirer-fit` |
| M&A probability report/JSON | Implemented | `bve-ma-probability` |
| SQLite knowledge/replay stores | Implemented | `KnowledgeStore`, `ReplayStore` |
| Historical replay summary/significance | Implemented | `historical_replay summary/significance` |
| API/UI surfaces | Implemented but secondary | `apps/api/*` |

### Old report comparison

| Topic from older report | Current repo finding |
|---|---|
| Old `Old_report` file | Empty in this checkout; not usable |
| `bve_technical_report.md` says M&A scanner not well-wired | Outdated. Current repo has acquisition screen, acquirer fit, M&A probability, snapshots, monitoring, calibration, and BD layers |
| Old report says Monte Carlo lacks stochastic timing/cost | Outdated. `MonteCarloParams` now supports phase-duration gamma draws and trial-cost lognormal draws |
| Old report warns tests lack exact known-answer checks | Partly outdated. `tests/test_known_answers.py` includes rNPV and deal-economics known-answer style tests |
| Old report says POS calibration limited | Still broadly true. Empirical/calibration modules exist, but institutional-grade cross-TA validation remains incomplete |
| Old report treats M&A as mostly strategic-fit placeholder | Outdated. M&A is now substantial with encumbrance, antitrust, catalyst hazard, and stage-specific priors, but still not fully institutional without richer BD data |

### Full system map

The current system is best understood as five connected engines:

```text
YAML / configs / research data
        |
        v
DrugAssetProgram + company inputs + market model + deal economics
        |
        v
ValuationEngine
  -> POS / trial-design model
       -> base rate hierarchy (TA → indication subtype → modality)
       -> 20+ log-odds adjusters (Layer 1)
       -> trial design / regulatory evidence (Layer 2)
       -> POS uncertainty intervals (compute_pos_with_ci)
  -> probability tree
  -> revenue model
  -> cost model
  -> rNPV / NAV / scenarios / Monte Carlo
        |
        v
ValuationOutput / memos / charts / JSON
        |
        v
Intelligence and M&A layers
  -> market expectations
  -> acquisition discount
  -> acquirer fit
  -> M&A probability
     -> catalyst hazard scaling (6m/18m dynamic)
     -> deal encumbrance (ROFR/ROFN/co-dev/block)
     -> antitrust regime modeling
     -> stage-specific transaction priors
     -> p_effective_close_12m = p_any × encumbrance × antitrust
  -> weekly review / thesis / decision loop
        |
        v
Replay, calibration, backtest, monitoring, database snapshots
  -> M&A calibration dataset framework (schema + no-lookahead + fit gate)
```

### File-by-file module descriptions

| Module | What it does | Institutional read |
|---|---|---|
| `src/bve/valuation/valuation_engine.py` | Orchestrates end-to-end asset valuation and attaches intelligence artifacts. | Central production path for single-asset work. |
| `src/bve/valuation/outputs.py` | Defines the serialized valuation output object. | Important because it controls what downstream memos and JSON expose. |
| `src/bve/models/pos_model.py` | Applies Layer 1 evidence-driven POS adjustments in log-odds space. 20+ adjusters, three-level base rate hierarchy, BTD type-conditional, data maturity, CMC risk, competitive benchmark, prior regulatory actions, POS ceiling, uncertainty intervals. | Core POS logic; adjuster magnitudes remain calibration-sensitive. |
| `src/bve/models/trial_design_features.py` | Scores trial design, comparator fit, and regulatory pathway risk. | Good separation of design quality from biology, but overlap controls are limited. |
| `src/bve/models/probability_model.py` | Computes probability of reaching each phase and cumulative approval probability. | Mechanically clean and auditable. |
| `src/bve/models/market_model.py` | Defines commercial opportunity, pricing basis, uptake, geography, payer, and competition inputs. | Flexible enough for serious modeling; accuracy depends on config quality. |
| `src/bve/models/revenue_model.py` | Converts commercial assumptions into annual revenue, gross profit, EBIT, and LOE tail. | Broadly implemented; explicit LOE erosion exists. |
| `src/bve/models/cost_model.py` | Probability-weights trial, CMC, milestone, upfront, and post-approval costs. | Stronger than a simple static R&D-cost model. |
| `src/bve/models/rnpv_model.py` | Discounts after-tax FCF and subtracts probability-weighted development costs. | Core financial math is inspectable and testable. |
| `src/bve/models/monte_carlo.py` | Samples POS, peak sales or drivers, WACC, timing, costs, financing dilution, and competition. | Advanced for a prototype; still depends on input distributions. |
| `src/bve/intelligence/acquisition_screen.py` | Compares model rNPV with market enterprise value to flag acquisition discount. | Useful first-pass takeout screen; not a deal-probability model by itself. |
| `src/bve/intelligence/acquirer_fit.py` | Scores a target against curated acquirer profiles. | Practical BD screen; profile freshness and hidden strategy are the weak points. |
| `src/bve/intelligence/ma_probability.py` | Ranks targets and persists M&A probability snapshots. | Directionally useful; exact probabilities require more labels. |
| `src/bve/intelligence/ma_scoring.py` | Decomposes target attractiveness, deal likelihood, and acquirer fit. | Good explanatory layer, but still heuristic. |
| `src/bve/intelligence/ma_layer3_gate.py` | Applies institutional-style gating for deal rationale, seller readiness, control, and feasibility. | Strong design direction; data coverage is incomplete. |
| `src/bve/intelligence/ma_layer4_routing.py` | Routes opportunities to watchlist classes and possible deal structures. | Useful for BD workflow language; not calibrated. |
| `src/bve/intelligence/ma_layer5_calibration.py` | Adds shrinkage, confidence, cohorts, probability bands, catalyst hazard scaling, deal encumbrance, and antitrust regime. | Core closing-probability layer; encumbrance and antitrust separate closing feasibility from strategic interest. |
| `src/bve/intelligence/ma_calibration_dataset.py` | Schema, no-lookahead validator, and fit readiness gate for labeled M&A calibration data. | Framework is in place; calibration waits for ≥50 positives + ≥100 negatives with no lookahead. |
| `src/bve/ops/historical_replay.py` | Replays historical decisions point-in-time. | Essential for credibility; current sample size is still small. |
| `src/bve/intelligence/thesis_tracker.py` | Tracks claim lifecycle and weighted thesis strength. | Useful for disciplined research review. |
| `src/bve/intelligence/decision_layer.py` | Stores recommended vs executed actions and attribution. | Important bridge between model output and actual portfolio behavior. |

### CLI entry points that matter for this review

| Command | Purpose |
|---|---|
| `bve-asset` | Run canonical single-asset valuation and generate memo/chart artifacts. |
| `bve-batch` / `bve-portfolio` | Run multiple assets or portfolio-level views. |
| `bve-acquisition-screen` | Screen targets by acquisition discount and basic readiness. |
| `bve-acquirer-fit` | Rank buyer-target strategic fit using acquirer profiles. |
| `bve-ma-probability` | Generate M&A probability/watchlist ranking and snapshots. |
| `bve-watchlist` | Run monitoring pipeline and intelligence ingestion. |
| `bve-rank` | Rank opportunities with market-implied POS gap and thesis signals. |
| `bve-calibrate` / replay utilities | Evaluate historical policy and calibration quality. |

### Data inputs in old-report format

| Input category | Examples | Current status | Main risk |
|---|---|---|---|
| Asset config | Stage, indication, trial path, commercial assumptions, company financials | Implemented | Manual assumptions can dominate output. |
| Industry defaults | Phase durations, base rates, R&D costs, WACC, tax, LOE defaults | Implemented in YAML | Defaults may be too generic for a given modality/TA. |
| Market data | Price, shares, market cap, enterprise value, volume | Implemented through connectors/snapshots | Coverage and point-in-time availability matter. |
| Clinical/regulatory evidence | Trial events, endpoints, readouts, FDA/CT.gov/PubMed/press releases | Implemented/partial | Extraction confidence and source freshness matter. |
| M&A research data | Comparable deals, acquirer profiles, pipeline gaps, vulnerability signals | Implemented/config-driven | Manual curation and sparse labels limit probability claims. |
| Expert BD judgment | Hidden blockers, seller willingness, buyer urgency, real priorities | Missing/needed | Public data cannot fully substitute for BD review. |

## 3. Single-Asset Valuation Engine

Primary module: `src/bve/valuation/valuation_engine.py`.

`ValuationEngine.run()` executes:

1. `_prepare_trials()`: applies POS model and trial-design model.
2. `_resolve_market_model_with_sgna()`: resolves commercial SG&A profile.
3. Revenue sanity checks.
4. Compliance/confirmatory-obligation warnings.
5. Trial cost defaults.
6. `ProbabilityModel.compute()`.
7. `RevenueModel.compute()`.
8. `CostModel.compute()`.
9. `RNPVModel.compute()`.
10. NAV/share calculation.
11. Scenario generation.
12. Monte Carlo.
13. Sensitivity.
14. Assumption log and provenance hashes.
15. Optional comparable-deal analysis.
16. Market-implied expectation, runway, dilution, analog, catalyst payoff, variant perception, and top acquirers.

### Core formula stack

| Model | File | Function | Role |
|---|---|---|---|
| POS | `models/pos_model.py` | `compute_pos()` | Phase-specific success probability |
| Probability path | `models/probability_model.py` | `ProbabilityModel.compute()` | Cumulative approval probability and phase timing |
| Revenue | `models/revenue_model.py` | `RevenueModel.compute()` | Revenue, gross profit, EBIT curves |
| Cost | `models/cost_model.py` | `CostModel.compute()` | Probability-weighted PV of development costs |
| rNPV | `models/rnpv_model.py` | `RNPVModel.compute()` | Probability-adjusted FCF less development costs |

### Cumulative probability of approval

For ordered phases:

```text
P(reaching phase_i) = product(success_probability_j for j before i)
P(approval) = product(success_probability_i for all remaining phases)
years_to_approval = sum(duration_years_i)
```

Implemented in `ProbabilityModel.compute()`.

### NAV/share

In `ValuationEngine.run()`:

```text
ownership = company.ownership_of(asset.id)
NAV = rNPV * ownership + company.net_cash_millions
NAV/share = NAV / company.shares_outstanding_millions
```

### Audit trail

Implemented audit/provenance outputs include:

- `assumption_log`
- `assumptions_yaml_hash`
- `config_hash`
- `wacc_vintage`
- `analyst_overrides`
- `revenue_audit_table`
- `random_seed`
- `n_simulations`
- `config_path`

Status: Implemented in code.

## 4. POS Model

Primary files:

- `src/bve/models/pos_model.py`
- `src/bve/models/trial_design_features.py`
- `src/bve/entities/trial.py`
- `src/bve/empirical/*`
- `src/bve/config/industry_assumptions.yaml`
- `src/bve/config/constants.py`

### Base rate hierarchy

Base rates are selected from the most specific source available:

```text
Priority 1 (most specific): indication_subtype override
  → e.g. gbm Phase 2 = 0.120, ultra_rare_monogenic Phase 2 = 0.580
Priority 2: modality-specific override (gene_therapy_modality set)
  → e.g. car_t_autologous Phase 2 = 0.45, aav_in_vivo Phase 2 = 0.38
Priority 3 (default): therapeutic_area base rate
  → e.g. oncology_solid Phase 2 = 0.234

Conflict rule: if BOTH indication_subtype AND gene_therapy_modality are set,
  indication_subtype wins and a confidence_flag
  "modality_base_rate_overridden_by_subtype" is emitted.
```

All base rates read from `AssumptionsLoader.get()`, never from hardcoded dicts.

### Indication subtype rates

8 high-impact subtypes implemented in `industry_assumptions.yaml`:

| Subtype key | Phase 1 | Phase 2 | Phase 3 | NDA/BLA | TA fallback | Confidence |
|---|---:|---:|---:|---:|---|---|
| `gbm` | 0.440 | 0.120 | 0.280 | 0.880 | oncology_solid | medium |
| `alzheimers` | 0.470 | 0.180 | 0.420 | 0.840 | cns | medium |
| `ultra_rare_monogenic` | 0.710 | 0.580 | 0.700 | 0.960 | rare_disease | medium |
| `nsclc_targeted` | 0.510 | 0.280 | 0.510 | 0.930 | oncology_solid | medium |
| `nsclc_io_refractory` | 0.480 | 0.190 | 0.390 | 0.900 | oncology_solid | low |
| `cll_btk_era` | 0.520 | 0.380 | 0.630 | 0.920 | hematology | low |
| `psychiatry_mdd` | 0.510 | 0.220 | 0.530 | 0.910 | psychiatry | medium |
| `pain_chronic` | 0.450 | 0.200 | 0.450 | 0.860 | cns | low |

Each entry carries metadata: `source`, `n_programs`, `date_range`, `confidence`, `ta_fallback`. Status: Implemented in code.

### Modality-specific base rates

7 modalities implemented in `industry_assumptions.yaml` under `modality_phase_rates`:

| Modality key | Phase 1 | Phase 2 | Phase 3 | NDA/BLA |
|---|---:|---:|---:|---:|
| `gene_therapy_aav` | 0.55 | 0.38 | 0.50 | 0.82 |
| `gene_therapy_lentiviral` | 0.52 | 0.35 | 0.48 | 0.79 |
| `car_t_autologous` | 0.60 | 0.45 | 0.62 | 0.88 |
| `car_t_allogeneic` | 0.44 | 0.30 | 0.45 | 0.75 |
| `lnp_mrna` | 0.58 | 0.42 | 0.60 | 0.85 |
| `aso_rnai` | 0.57 | 0.40 | 0.58 | 0.87 |
| `biologic_antibody` | 0.62 | 0.38 | 0.61 | 0.88 |

All entries labeled `prior_estimate_not_backtested`. Accessed via `AssumptionsLoader.get_modality_phase_rate(modality_key, phase)`. Status: Implemented in code.

### Layer 1: POS adjusters

Core formula:

```text
base = select_base_rate(indication_subtype, gene_therapy_modality, therapeutic_area, phase)
base_log_odds = ln(base / (1 - base))
adjusted_log_odds = base_log_odds + capped(sum(log_odds_adjusters))
POS = sigmoid(adjusted_log_odds)
```

Where the absolute POS ceiling is applied after sigmoid conversion:

```text
pos_ceiling = min(0.75, max(base_rate × 2.5, base_rate + 0.25))
if base_rate > pos_ceiling:
    pos_ceiling = 1.0   # ceiling inactive for high-base-rate phases (NDA/BLA)
final_pos = min(pos, pos_ceiling)
```

This prevents absurd highs for low-base-rate programs without incorrectly capping NDA/BLA-stage assets whose base rate already exceeds the formula bound.

Layer 1 caps:

```text
positive cap = +0.80 log-odds
extraordinary evidence positive cap = +1.00 (requires: strong replicated prior data
  + validated biomarker + exceeds MCID + non-empty rationale text)
negative cap = -0.80
```

### Full Layer 1 adjuster table

| Adjuster | Enum / values | Phase gate | Log-odds range | Notes |
|---|---|---|---|---|
| Endpoint type | `EndpointType` (TA-specific and generic lookup) | All phases | −0.45 to +0.35 | TA-specific table; generic fallback |
| MoA precedent | `MechanismPrecedent` | All phases | −0.30 to +0.25 | |
| MoA exception flags | Multiple bool flags | All phases | Various | Should not stack speculatively |
| Sample size adequacy | Bool | Phase 2+ only | +0.15 | Silenced at Phase 1 |
| Safety profile | `SafetyProfile` | All phases | −0.40 to 0.00 | |
| Competitive pressure | `CompetitivePressure` | All phases | −0.20 to 0.00 | Separate from revenue competition |
| Biomarker enrichment | `BiomarkerSelection` | All phases | 0.00 to +0.40 | |
| Prior phase data | `PriorPhaseData` | All phases | −0.15 to +0.35 | |
| Breakthrough designation | `BreakthroughDesignationType` (7 types) | All phases | −0.15 to +0.10 | Type-conditional; see BTD table |
| Clinical effect magnitude | `ClinicalEffectMagnitude` | Phase 1/2/3 | −0.20 to +0.25 | Silenced at NDA/BLA with flag |
| Dose selection adequacy | Bool | Phase 2+ | 0.00 to +0.15 | |
| Platform validation | Bool | All phases | 0.00 to +0.10 | |
| Extraordinary evidence | Bool (gated) | All phases | +0.20 | Requires 3 conditions + rationale |
| Gene/cell therapy concerns | `GeneTherapyConcern` list (12 values) | All phases | −0.25 to +0.30 | Durability cap −0.30; total cap −0.60 |
| Gene therapy modality | `GeneTherapyModality` (10 values) | All phases | 0.00 | Context field; triggers modality base rate |
| Data maturity | `DataMaturityLevel` (5 values) | Phase 2/3 only | −0.35 to 0.00 | Silenced at Phase 1 and NDA/BLA |
| CMC risk | `CMCRiskLevel` (5 values) | Phase 3/NDA only | −0.40 to 0.00 | Early warning flag at Phase 1/2 for complex modalities |
| Competitive benchmark | `CompetitiveBenchmarkPosition` (5 values) | Phase 2/3 only | −0.50 to +0.20 | Approvability-relevant comparator position |
| Prior regulatory actions | `list[RegulatoryActionRecord]` | Phase-conditional | −0.20 to −0.50 per action | Stacking cap −0.60; penalty scaled by resolution and indication |
| Indication subtype | `Optional[str]` | Base rate only | N/A (base rate substitution) | Subtype wins over modality; metadata emitted |

### Breakthrough designation type-conditional table

| BTD type | Log-odds | Notes |
|---|---:|---|
| `NONE` | 0.00 | No designation |
| `FAST_TRACK_ONLY` | +0.02 | Process signal only; minimal POS effect |
| `GRANTED_STANDARD` | +0.05 | Backward-compatible default for `has_breakthrough_designation=True` |
| `GRANTED_RARE_HEME` | +0.10 | Best evidence for regulatory translation |
| `GRANTED_SOLID_TUMOR` | +0.03 | Selection bias adjusted; crowded field |
| `GRANTED_EARLY_PHASE` | +0.08 | Strong early FDA engagement signal |
| `BREAKTHROUGH_REVOKED` | −0.15 | Loss of FDA confidence; materially negative |

Backward compatibility: `has_breakthrough_designation=True` maps to `GRANTED_STANDARD`. BTD overlap warning emitted when `GRANTED_RARE_HEME` or `GRANTED_EARLY_PHASE` co-occurs with strong prior phase data and exceeds-MCID clinical effect (potential double-counting).

### Data maturity and CMC risk adjusters

`DataMaturityLevel` (Phase 2/3 only):

| Level | Log-odds | Condition |
|---|---:|---|
| `MATURE_FINAL` | 0.00 | Final readout, events mature |
| `INTERIM_PRE_PLANNED` | −0.10 | Pre-planned interim, adequate events |
| `IMMATURE_ONGOING` | −0.20 | OS/PFS ongoing, primary endpoint not reached |
| `EARLY_INTERIM_UNPLANNED` | −0.35 | Early/unplanned; high reversal risk |
| `UNKNOWN` | 0.00 + flag | Emits `data_maturity_unknown`; wider CI bounds |

`CMCRiskLevel` (Phase 3/NDA numerical penalty; early warning flag at Phase 1/2 for complex modalities):

| Level | Log-odds | Condition |
|---|---:|---|
| `PROVEN_SCALABLE` | 0.00 | Commercial-scale manufacturing demonstrated |
| `LATE_STAGE_DEV` | −0.10 | Phase 3 manufacturing in progress, feasible |
| `DEVELOPMENT_STAGE` | −0.20 | Process not yet locked; scale challenges likely |
| `KNOWN_ISSUES` | −0.40 | Prior batch failures or CRO changes on record |
| `UNKNOWN` | 0.00 + flag | `cmc_risk_unassessed_complex_modality` at Phase 1/2 for gene therapy modalities |

### Competitive benchmark position

Phase gate: Phase 2 and Phase 3 only. Represents approvability-relevant comparator position (not commercial inferiority — commercial effects belong in rNPV revenue, not POS).

| Position | Log-odds | Observable anchor |
|---|---:|---|
| `BEST_IN_CLASS` | +0.20 | Clearly superior on primary endpoint vs SoC/comparator |
| `COMPETITIVE` | 0.00 | Reference (on par) |
| `BELOW_COMPARATOR` | −0.25 | Measurably behind best-in-class on key regulatory endpoint |
| `CLEARLY_INFERIOR` | −0.50 | Materially worse; approvability at risk |
| `UNKNOWN` | 0.00 + flag | Emits `competitive_benchmark_unknown` |

### Prior regulatory actions

Applies a probability penalty for prior FDA actions on the molecule or related programs. Clinical holds apply at all phases; CRL, advisory committee negative, and refusal-to-file apply at Phase 3 and NDA/BLA only. Stacking cap: −0.60 total.

| Action | Base log-odds |
|---|---:|
| `CLINICAL_HOLD_SAFETY` | −0.45 |
| `CLINICAL_HOLD_CMC` | −0.20 |
| `CRL_SAFETY` | −0.50 |
| `CRL_EFFICACY` | −0.35 |
| `CRL_CMC` | −0.25 |
| `ADVISORY_COMMITTEE_NEGATIVE` | −0.30 |
| `PRIOR_REFUSAL_TO_FILE` | −0.35 |

Each action is wrapped in `RegulatoryActionRecord` with context fields. Penalty scaling:

```text
issue_resolved = True         → 50% of base penalty
same_indication = False       → 40% of base penalty
both resolved + diff_indication → 20% of base penalty
```

### POS uncertainty intervals

```python
# Opt-in function (not run by default — heavier)
result = compute_pos_with_ci(
    phase, therapeutic_area, adjusters,
    n_mc_samples=500
)
# result.pos            — point estimate
# result.pos_ci_low     — 5th percentile
# result.pos_ci_high    — 95th percentile
# result.pos_ci_width   — ci_high - ci_low
```

Implementation: Triangular(min, mode, max) draws per adjuster, 500 samples default. UNKNOWN inputs deliberately have wider uncertainty bounds (not zero-variance) to ensure CI widens with more unknowns:

```text
dose_selection UNKNOWN:    min=−0.20, mode=0.00, max=+0.10
clinical_effect UNKNOWN:   min=−0.20, mode=0.00, max=+0.20
data_maturity UNKNOWN:     min=−0.25, mode=0.00, max=+0.05
cmc_risk UNKNOWN (gene):   min=−0.30, mode=0.00, max=+0.05
cmc_risk UNKNOWN (other):  min=−0.15, mode=0.00, max=+0.05
```

Status: Implemented in code. Also available as `compute_pos_detailed(..., include_ci=True)`.

### Layer 2: Trial design/regulatory evidence

Primary file: `src/bve/models/trial_design_features.py`.

Layer 2 is explicitly orthogonal to Layer 1:

- Layer 1 scores what evidence exists.
- Layer 2 scores whether the evidence package is trustworthy and regulator-acceptable.

Inputs:

| Dimension | Examples | Mechanics |
|---|---|---|
| Evidence design quality | double-blind RCT, open-label RCT, single-arm objective, registry/observational | Log-odds |
| Comparator fit | matches SoC, placebo acceptable, outdated comparator, no valid comparator | Log-odds |
| Regulatory pathway risk | standard, orphan rare disease, accelerated validated surrogate, novel surrogate, no clear precedent | Log-odds |

Phase scaling:

| Phase | Design scaling |
|---|---:|
| Phase 1 | 0.20 |
| Phase 2 | 0.50 |
| Phase 3 | 1.00 |
| NDA/BLA | 0.90 |

Caps:

```text
positive cap = +0.30
negative cap = -0.60
```

Combined Layer 1 + Layer 2 cap:

```text
COMBINED_L1_L2_CAP_POSITIVE = +0.90
COMBINED_L1_L2_CAP_NEGATIVE = -0.90
Applied in _apply_design_adjustments() in valuation_engine.py
```

Double-counting risk:

- The implementation currently returns a clean overlap report because the Layer 2 dimensions are designed to be orthogonal.
- Practical risk remains: analysts can still encode the same concept in multiple YAML fields, especially competition, endpoint strength, and peak penetration.

### Accelerated approval

`ApprovalPathwayType.ACCELERATED` applies an NDA/BLA confirmatory-risk discount.

Constant: `_AA_NDA_DISCOUNT = 0.18`.

### Evidence basis and validation

Status:

- Implemented in code.
- Many tests assert monotonicity, bounds, and integration.
- Empirical modules exist for calibration and overlay, but institutional-grade validation is not complete.

Known weaknesses:

- POS point estimates should be shown as ranges; `compute_pos_with_ci()` is now available but not yet exposed in the default memo output.
- Cross-TA calibration remains a major gap.
- Qualitative tiers can create false precision.
- Some public data is not point-in-time safe.

## 5. Revenue Model

Primary files:

- `src/bve/models/market_model.py`
- `src/bve/models/revenue_model.py`
- `src/bve/models/competition_model.py`
- `src/bve/models/geography.py`
- `src/bve/models/payer_access.py`
- `src/bve/models/launch_archetype.py`
- `src/bve/models/revenue_audit.py`

### Revenue modes

| Mode | Formula | Status |
|---|---|---|
| Patient-based | `eligible patients * net price * compliance * penetration` | Implemented |
| TAM-based | `TAM * penetration` | Implemented |
| Line-of-therapy | Sum of per-segment patient pools, price, penetration, launch timing | Implemented |

### Patient-based sizing

Representative formula:

```text
annual_revenue_y =
    addressable_patients_annual
  * net_price_per_patient_usd
  * compliance_rate
  * penetration_y
  / 1,000,000
```

### Pricing and gross-to-net

`MarketModel` has `PriceBasis`:

- `NET`: already net.
- `WAC` / `LIST`: gross-to-net can be applied if configured.

Revenue sanity checks warn on unusually high net price and questionable adoption curves.

### Geography launch timing

`RevenueModel.compute()` supports geography extension when `geography_split` is present. Delayed regions can extend the commercial horizon, and LOE tails are applied by region timing.

Status: Implemented in code, but accuracy depends on configured geography assumptions.

### Payer access

Payer access is represented through `PayerAccessModel` and can affect uptake/adoption. Monte Carlo driver mode can sample payer access.

Status: Implemented, but public payer assumptions remain highly judgmental.

### Competition

Competition is implemented through:

- `CompetitionModel`
- `CompetitorLaunch`
- `CrowdingModel`
- `FirstMoverConfig`
- `ClassSaturationProfile`
- Monte Carlo competitor sampling

Competition can affect revenue, and separate competitive pressure can affect POS. This is conceptually correct, but it creates analyst double-counting risk if peak penetration is also reduced for the same issue.

### LOE / patent erosion

`RevenueModel.compute()` appends up to five post-LOE tail years based on modality-specific erosion profiles. Post-LOE SG&A is reduced using `post_loe_sgna_fraction`.

Status: Implemented. Exact patent/exclusivity expiry dates are not deeply modeled as a BD diligence object.

### COGS / SG&A / EBIT

```text
gross_profit_y = revenue_y * (1 - cogs_rate)
EBIT_y = gross_profit_y - revenue_y * sgna_rate_y
```

SG&A ramps from launch to mature profile. Revenue audit tables expose the annual bridge.

### Current limitations

- Peak penetration and addressable patients dominate output and remain analyst-driven.
- Payer access is not backed by payer-contract data.
- Ex-US modeling exists but is only as good as geography config.
- LOE profile is generic unless overridden.
- Dynamic market share and future label sequencing can still be simplified.

## 6. Cost Model

Primary files:

- `src/bve/models/cost_model.py`
- `src/bve/models/cmc_costs.py`
- `src/bve/models/deal_economics.py`
- `src/bve/models/confirmatory_trial.py`

### Trial R&D costs

For each phase:

```text
pv_cost_gross_i = cost_i * cdev_cost_share * (1 + inflation)^t / (1 + discount_rate)^t
pv_cost_weighted_i = pv_cost_gross_i * P(reaching phase_i)
```

For uniform spend, `t` is the phase midpoint. For annual-uniform spend, the phase is split across integer-year intervals.

### CMC/manufacturing costs

`CMCCosts` supports:

- API development
- formulation/process development
- manufacturing scale-up
- validation/PPQ
- facility/tech transfer
- timing modes: parallel to Phase 3, post-Phase 2, pre-Phase 3 start, or custom year

CMC PV is probability-weighted using Phase 3 reaching probability or fallback.

Status: Implemented and tested.

### Upfronts and milestones

`DealEconomics` integration supports:

- co-development cost share
- payable milestones
- upfront cost
- receivable milestones
- upfront receipt
- royalties
- profit share

Cost model handles payable/upfront cost side; rNPV handles receivable and revenue deductions.

### Post-approval commitments

Post-approval R&D is discounted at years to approval and probability-weighted by cumulative approval probability.

Confirmatory trial obligation warnings exist, but confirmatory obligation risk does not automatically change POS unless configured.

### Current limitations

- Exact CRO quotes, site cost curves, and enrollment delays require external input.
- CMC model handles costs, not deep manufacturability risk scoring inside M&A probability.
- Milestone triggers are simplified relative to real contracts.
- Inflation is configurable but not a full macro scenario model.

## 7. rNPV / NAV / Variant Perception

Primary files:

- `src/bve/models/rnpv_model.py`
- `src/bve/expectations/market_implied_pos.py`
- `src/bve/analysis/variant_perception.py`
- `src/bve/valuation/valuation_engine.py`

### rNPV formula

Canonical implementation:

```text
rNPV =
    P(approval) * sum_t[after_tax_FCF_t * net_ownership / (1 + WACC)^t]
  - total_pv_weighted_development_costs
  + PV(receivable milestones)
  + upfront_receipt
```

Per-year economics:

```text
adjusted_EBIT_t =
    EBIT_t
  - revenue_t * deal.royalty_rate
  - EBIT_t * deal.profit_share_rate

cash_tax_t = max(adjusted_EBIT_t - usable_NOL_t, 0) * tax_rate_t
after_tax_FCF_t = adjusted_EBIT_t - cash_tax_t - capex_t - working_capital_t - launch_capex_t
```

Tax paths:

- Simple path: effective tax rate with optional NOL benefit years.
- `TaxProfile` path: NOL tracking, utilization, jurisdiction blend, capex, working capital, launch capex, and audit.

### NAV/share formula

```text
NAV = rNPV * ownership + net_cash
NAV/share = NAV / shares_outstanding
```

### Market-implied POS

Back-solve concept:

```text
market_asset_ev = market_cap - net_cash
implied_POS ~= (market_asset_ev + trial_costs_pv) / gross_revenue_pv
```

The implementation uses `compute_implied_pos()` with current EV, net cash, peak sales, model POS, years to peak, discount rate, patent duration, and trial-cost PV.

### Variant perception

Variant perception back-solves what market assumptions would need to be true:

- implied POS
- implied peak sales
- implied penetration
- implied price
- implied eligible patients
- perception category: clinical, commercial, pricing, allocation, mixed, or indeterminate

### Guardrails

- Returns `None` when price data is missing or invalid.
- Should be used cautiously for multi-asset companies.
- Diversified companies make single-asset EV isolation misleading.
- Negative enterprise values and non-core assets distort interpretation.

### Interpretation

| Model vs market | Interpretation |
|---|---|
| Model POS > implied POS | Model is more bullish clinically than market |
| Model POS < implied POS | Market prices stronger clinical confidence than model |
| Model peak sales > implied peak | Model is more bullish commercially |
| Market cap exceeds model NAV | Either market sees other assets, higher POS, higher sales, strategic value, or model is too conservative |

## 8. Scenario Analysis

Primary files:

- `src/bve/valuation/scenario.py`
- `src/bve/models/scenario_shock.py`
- `src/bve/valuation/scenario_tree.py`
- `src/bve/scenarios/library.yaml`
- `src/bve/scenarios/stress_runner.py`

### Base/bull/bear

Legacy scenarios:

| Parameter | Bear | Base | Bull |
|---|---:|---:|---:|
| Peak sales | 0.55x | 1.00x | 1.50x |
| POS | 0.70x | 1.00x | 1.30x |
| Duration | +1.0 year | 0 | -0.5 year |
| Cost | 1.20x | 1.00x | 0.90x |
| Discount rate | +2 pp | 0 | -1 pp |

Scenario results rerun the engine. rNPV is not directly shocked.

### ScenarioShock categories

Implemented categories include:

- clinical shocks
- regulatory shocks
- commercial shocks
- competition shocks
- cost/FCF shocks
- deal-economics shocks

Scenario outputs include delta versus base, key assumption changes, top value drivers, kill-criteria flag, and memo interpretation.

### Scenario tree

`scenario_tree.py` implements:

- Multi-branch catalyst trees.
- Six-outcome payoff trees: strong positive, positive, mixed, neutral, negative, strong negative.
- Probability sum validation.
- Expected return, POS revision, upside/downside, skew ratio, setup score.

Status: Implemented. These are useful for catalyst framing but depend heavily on analyst probabilities.

## 9. Monte Carlo Engine

Primary file: `src/bve/models/monte_carlo.py`.

### Simulation modes

| Mode | Description | Status |
|---|---|---|
| `simple` | Samples peak sales directly as one lognormal draw | Implemented |
| `driver_based` | Builds peak sales from sampled patients, price, penetration, payer access, geography | Implemented |

Validator prevents direct peak-sales sampling plus driver sampling at the same time.

### Variables sampled

| Variable | Distribution / mechanic |
|---|---|
| Phase success | Beta with mean and equivalent sample size |
| Peak sales | Lognormal |
| Eligible patients | Lognormal multiplier |
| Net price | Lognormal multiplier |
| Peak penetration | Lognormal multiplier |
| Payer access | Lognormal multiplier |
| Geography | Lognormal multiplier |
| Discount rate | Normal clipped to 1%-50% |
| Years to peak | Normal, rounded, clipped 1-20 |
| Phase duration | Gamma multiplier, optional |
| Trial cost | Lognormal multiplier, optional |
| Financing dilution | Equity-offering discount, optional |
| Competition | Sampled competitor launch outcomes, optional |

### Correlation logic

The engine can use `CorrelationSpec` and `DEFAULT_CORRELATION` through Gaussian copula uniform samples.

### Simulation path

Each trial:

1. Sample clinical probabilities.
2. Apply duration multipliers.
3. Apply cost multipliers.
4. Apply commercial draw.
5. Apply competition draw.
6. Apply discount rate.
7. Rerun full rNPV engine.
8. Apply financing dilution if enabled.
9. Compute NAV/share.

Hard invariant: output records `engine_rerun=True`; rNPV is not a direct shock to base rNPV.

### Outputs

Monte Carlo returns:

- mean, median, std
- P5/P10/P25/P50/P75/P90/P95
- probability positive
- probability above $500M and $1B
- expected upside/downside
- downside value-at-risk
- top variance drivers
- clinical failure, competitor disruption, payer restriction rates
- probability NAV above EV or price when inputs are provided
- compact audit trail for P5/P50/P95 simulations

### Weaknesses

- Correlations are still assumptions.
- Cost and duration stochasticity are optional, not necessarily enabled in every config.
- CMC manufacturability risk is mostly a cost input, not a failure-state distribution.
- Monte Carlo precision can exceed data quality if presented without bands.

## 10. M&A Probability Scanner

Primary files:

- `src/bve/intelligence/acquisition_screen.py`
- `src/bve/intelligence/acquisition_readiness.py`
- `src/bve/intelligence/comparable_deals.py`
- `src/bve/intelligence/acquirer_fit.py`
- `src/bve/intelligence/ma_probability.py`
- `src/bve/intelligence/ma_scoring.py`
- `src/bve/intelligence/ma_bd_decomposition.py`
- `src/bve/intelligence/ma_layer3_gate.py`
- `src/bve/intelligence/ma_layer4_routing.py`
- `src/bve/intelligence/ma_layer5_calibration.py`
- `src/bve/intelligence/ma_calibration.py`
- `src/bve/intelligence/ma_calibration_dataset.py`

### What the scanner is trying to predict

The scanner ranks public biotech targets by acquisition attractiveness/probability and identifies the most likely acquirer. In practice, the current score is a structured ranking heuristic with optional calibration, not a validated probability of takeout.

### Target universe

Config examples:

- `examples/research/universe_expanded_mna.yaml`
- `examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml`
- generated valuation configs under `examples/configs/replay_generated/`

Targetability rules:

- `src/bve/config/targetability_rules.yaml`
- `examples/research/mna_targetability_rules.yaml`

Targetability gates include excluded tickers, known acquirers, mega-cap limits, commercial franchise share, multi-product penalties, and market-cap penalties.

### Acquirer universe

There are 33 curated acquirer profile YAMLs in `examples/research/acquirer_profiles/`. Profiles support:

- pipeline gaps
- preferred modalities
- recent deals
- stated priorities
- existing partnerships
- cash/budget/capacity
- source references

Profile IDs are slugified company names, e.g. `vertex_pharmaceuticals`, `regeneron_pharmaceuticals`.

### Acquisition discount

Implemented formula:

```text
enterprise_value = market_cap - net_cash
acquisition_discount = model_rnpv / enterprise_value
```

The implementation explicitly avoids multiplying by POS again because rNPV already embeds POS.

### Acquisition readiness

Rules:

- Phase 3/NDA/approved/commercial: ready by stage.
- Preclinical/Phase 1: not ready.
- Phase 2: requires KnowledgeStore Phase 2 readout evidence, endpoint success, quantitative de-risking, and non-low-power design.

Status: Implemented.

### Acquirer-target scoring

`AcquirerFitScorer` standard components:

| Component | Meaning |
|---|---|
| Therapeutic area | Does the target TA match acquirer gap/exposure? |
| Modality | Does the modality match preferred platforms? |
| Stage | Is the asset late enough or acquisition-ready? |
| Strategic priority | Does target match stated priorities or partnership? |
| Valuation | Is EV reasonable versus comps or recent deal history? |
| Budget | Does target fit acquirer capacity? |

Pipeline-gap formula emphasizes:

```text
fit = 0.35*TA_match*urgency
    + 0.25*modality_match*urgency
    + 0.20*stage_score*urgency
    + 0.20*budget_fit*urgency
    + 0.10*partnership_score
```

### M&A probability components

`MAProbabilityScanner` scores each target against each acquirer, chooses the best candidate, and ranks targets. Components include:

- strategic fit
- valuation discount
- de-risking stage
- capital vulnerability
- scarcity
- external deal pressure
- target signal score
- catalyst proximity
- targetability multiplier
- transaction gate reason codes
- optional calibrated `p_takeout_calibrated`

Score versions:

| Version | Main intent |
|---|---|
| `v1.0` / `v1.1` | Balanced acquisition discount, fit, stage, vulnerability |
| `v1.2` | Strategic-fit dominant |
| `v1.3` | Strategic fit plus scarcity |
| `v1.4` | Strategic fit plus de-risking, vulnerability, scarcity |

### Stage-specific transaction priors

YAML section `transaction_mix_by_stage` in `industry_assumptions.yaml`:

| Stage | Acquisition fraction | License/partnership fraction |
|---|---:|---:|
| Preclinical | 0.15 | 0.75 |
| Phase 1 | 0.25 | 0.65 |
| Phase 2 | 0.40 | 0.55 |
| Phase 3 | 0.65 | 0.30 |
| NDA/BLA | 0.75 | 0.20 |
| Approved | 0.80 | 0.15 |
| Fallback | 0.60 | 0.35 |

`Layer5Inputs.target_stage` maps to these fractions. When set, derived probabilities are labeled `p_full_acquisition_source = DERIVED_STAGE_ADJUSTED`; otherwise `DERIVED` (flat prior). The fractions do not sum to 1.0 intentionally — the remainder covers other deal structures.

Status: Implemented in code.

### Catalyst-based hazard scaling

Layer 5 closing probability is dynamically shaped by catalyst timing and type.

`CatalystType` enum (7 values):

| Type | Description |
|---|---|
| `NONE` | No binary catalyst; continuous progress |
| `INVESTOR_UPDATE` | Conference or investor day — minor |
| `PHASE_2_POC` | Phase 2 proof-of-concept readout |
| `FDA_MEETING` | Type B/C meeting or advisory committee |
| `REGULATORY_DECISION` | PDUFA date, EMA opinion, CRL response |
| `PHASE_3_READOUT` | Pivotal Phase 3 top-line data |
| `UNKNOWN` | No catalyst schedule available |

Timing shape derivation:

```text
days_to_catalyst ≤ 90 AND type ∈ {PHASE_3_READOUT, REGULATORY_DECISION}
  → "strongly_front_loaded"
days_to_catalyst ≤ 180 AND type ∉ {NONE, INVESTOR_UPDATE}
  → "front_loaded"
days_to_catalyst > 365
  → "back_loaded"
otherwise → "neutral"
```

Dynamic 6m scale and 18m exponent:

| Timing shape | 6m scale | 18m exponent |
|---|---:|---:|
| `strongly_front_loaded` | 0.80 | 1.10 |
| `front_loaded` | 0.68 | 1.25 |
| `neutral` | 0.55 | 1.35 |
| `back_loaded` | 0.38 | 1.55 |

Backward compatibility: `days_to_catalyst=None` + `catalyst_type=UNKNOWN` → `neutral` → uses original constants exactly.

New `Layer5Output` audit fields: `timing_shape`, `timing_rationale`, `scale_6m_applied`, `scale_18m_exponent_applied`.

Status: Implemented in code.

### Deal encumbrance — ROFR vs ROFN

A critical design decision: encumbrance affects **closing probability**, not **strategic interest**. The conceptual separation is:

```text
p_any_strategic_transaction_12m  ← calibrated interest; NOT mutated by encumbrance
p_transaction_close_given_interest = encumbrance_multiplier × antitrust_multiplier
p_effective_close_12m = p_any × p_transaction_close_given_interest
```

`DealEncumbranceType` enum and closing multipliers:

| Type | Multiplier | G7 gate | Observable anchor |
|---|---:|---|---|
| `NONE` | 1.00 | No | No encumbrance |
| `CHANGE_OF_CONTROL` | 0.92 | No | Structural cost and process delay; no veto |
| `ROFN` | 0.90 | No | 30–90 day window, then free to shop; soft |
| `ROFR` | 0.68 | Yes | Partner can match any bid; price-capping risk |
| `CO_DEVELOPMENT_LOCK` | 0.50 | Yes | Mutual consent required for acquisition |
| `FULL_BLOCK` | 0.10 | Yes | Structure reform needed; near-veto |

Key change from prior implementation: ROFN and CHANGE_OF_CONTROL do **not** trigger the G7 hard gate. Only ROFR, CO_DEVELOPMENT_LOCK, and FULL_BLOCK trigger G7.

New `Layer5Output` audit fields: `p_effective_close_12m`, `encumbrance_close_multiplier`, `encumbrance_flag` (set for ROFR/CO_DEV/FULL_BLOCK only).

Status: Implemented in code.

### Antitrust regime modeling

Antitrust affects closing probability, not strategic interest or rank score. Applied multiplicatively with encumbrance.

`AntitrustRiskTier` (6 values) and base multipliers:

| Tier | Base multiplier | Observable anchor |
|---|---:|---|
| `NEGLIGIBLE` | 1.00 | No TA overlap, <$2B, novel mechanism |
| `LOW` | 0.97 | Minor overlap; acquirer <15% share in TA |
| `MODERATE` | 0.85 | Meaningful overlap; likely second request |
| `SIGNIFICANT` | 0.70 | >30% combined share or TA-consolidating deal |
| `LIKELY_CHALLENGED` | 0.45 | FTC/DOJ challenged similar; >50% combined |
| `BLOCKED_RISK` | 0.20 | DOJ/FTC public concern; structural remedy required |

`AntitrustRegime` modifier:

| Regime | Modifier | Note |
|---|---:|---|
| `PRE_2021` | 1.10 | Lenient era; soften base multiplier |
| `AGGRESSIVE_2021_2024` | 0.90 | Lina Khan era; tighten |
| `CURRENT_STANDARD` | 1.00 | Reference |
| `UNKNOWN` | 0.90 | Conservative default (= aggressive) |

```text
antitrust_multiplier = base × regime_modifier, clamped [0.05, 1.00]
p_effective_close_12m = p_any × encumbrance_multiplier × antitrust_multiplier
```

`AntitrustSubSignals` (informational only): structured sub-signals to justify tier selection — same-indication overlap, same-MoA overlap, pipeline overlap count, combined market share %, prior FTC scrutiny, cross-border CFIUS risk, deal size. Analyst sets tier manually.

New `Layer5Output` audit fields: `antitrust_multiplier_applied`, `antitrust_flag` (set for MODERATE or above).

Status: Implemented in code.

### Transaction-driver logic

`ma_scoring.py` decomposes into:

| Sub-score | Components |
|---|---|
| Target attractiveness | de-risking, valuation discount, scarcity, peak-sales signal |
| Deal likelihood | financing pressure, external deal activity, insider/board signals, catalyst proximity |
| Acquirer fit | TA/modality, pipeline gap, affordability, partnership bonus |

Drivers:

- financing pressure
- external deal activity
- catalyst proximity
- scarcity plus fit
- activist/ownership signal
- valuation distress

Caps:

- No transaction drivers: composite capped.
- One driver: score cannot exceed higher near-term threshold.
- Financing-not-pressured and no-buyer-urgency dual gate caps score.

### Deal value estimation

Deal value is estimated from:

- enterprise value
- comparable EV/peak-sales bands
- recent deal history
- model rNPV and acquisition discount context

Status: Implemented as screening approximation. Not a substitute for a full buyer-specific deal model.

### M&A calibration dataset framework

Primary file: `src/bve/intelligence/ma_calibration_dataset.py`.

Framework implemented; actual dataset curation is pending and must not be rushed.

`MACalibrationCase` required fields:

```text
ticker, company_name, observation_date, target_stage, therapeutic_area, modality,
cash_runway_months_as_of, seller_willingness_as_of [0,1],
catalyst_days_as_of (Optional), asset_quality_score_as_of [0,1],
acquirer_fit_score_as_of [0,1], outcome_12m (bool),
outcome_type (acquisition|license|partnership|none),
outcome_date (Optional), source_refs (list), feature_as_of_dates (dict),
lookahead_pass (bool)
```

No-lookahead validator:

```text
validate_no_lookahead(case) → NoLookaheadResult
  passed = True  if all feature_as_of_dates ≤ observation_date
  passed = False + violations list if any field date > observation_date
```

Fit readiness gate:

```text
check_fit_readiness(dataset) → FitReadinessResult
  ready = True only when ALL:
    ≥ 50 positive cases (outcome_12m = True)
    ≥ 100 negative cases (outcome_12m = False)
    ALL cases have lookahead_pass = True
DO NOT call fit_logistic_calibration() until ready = True.
A poorly curated calibration dataset produces false confidence — worse than no calibration.
```

YAML I/O: `save_dataset_to_yaml()` / `load_dataset_from_yaml()`.

Status: Framework implemented in code. Dataset curation pending (Block 37C).

### BD field implementation matrix

| Institutional BD field | Current status | Data source needed | Why BD person could help |
|---|---|---|---|
| Exact royalty stacks | Partially implemented | Contracts, SEC exhibits, royalty databases | Public terms often incomplete; economics materially change value |
| IP expiries | Partially implemented | Orange Book, patents, exclusivity, counsel review | Real protection differs from generic patent life |
| LOE cliffs | Partially implemented | Product revenue by franchise, patent/exclusivity dates | Buyer urgency depends on precise revenue cliff timing |
| Asset-control clauses | ROFR/ROFN implemented; other clauses partial | Collaboration agreements, option clauses | These can block or steer deal structure |
| Change-of-control provisions | Implemented as encumbrance type | Contracts, diligence | Public investors often miss these deal blockers |
| Existing partnerships | Implemented in profiles | Profile YAML, deal docs | BD can say whether partnership gives real control/information rights |
| Regional rights splits | Missing to partial | License maps by geography | Determines whether full acquisition, license, or regional deal is realistic |
| CMC bottlenecks | Partially implemented as costs + risk adjuster | CMC experts, manufacturing disclosures | Bottlenecks can determine acquirer capability and timing |
| Manufacturing complexity | Partially implemented | Modality, process, capacity, tech transfer data | BD knows which buyers can absorb complex modalities |
| Antitrust risk | Implemented — tier + regime model | Market share, overlap, counsel review | Strategic fit can create antitrust risk; tier selection requires BD judgment |
| BD history by acquirer | Partially implemented | Recent deals in profiles, broader deal DB | BD can separate real appetite from public rhetoric |
| Prior deals by acquirer | Implemented but incomplete | Deal databases, terms, failed deals | Needed for buyer-specific valuation logic |
| Stated strategic priorities | Implemented via curated profiles | Earnings calls, R&D days, investor decks | BD can validate whether statements are real or generic |
| Seller willingness | Partially implemented as signals/gates | Banker/process intel, board/investor signals | This is mostly non-public |
| Board/investor pressure | Partially implemented as target signals | Ownership, activists, governance changes | BD can judge whether pressure creates a process |
| Cash runway | Implemented | Cash/burn data, financing history | BD can say whether runway actually creates willingness |
| Upcoming catalysts | Implemented + catalyst hazard scaling | Catalyst calendar, trial events | BD can interpret whether buyer acts pre- or post-catalyst |
| Competitive threat | Partially implemented | Competitor pipelines, market maps | BD can identify must-block or must-own assets |
| Commercial infrastructure fit | Partially implemented via TA/modality | Salesforce/geography/franchise data | Determines synergy and ownership logic |
| Pipeline gap fit | Implemented | Acquirer profile gaps | BD can validate whether gap is urgent |
| Alternative bidders | Missing to partial | Competitive bidder map | Drives deal process probability and price |
| Deal structure likelihood | Partially implemented in Layer 4 | Contract rights, buyer behavior, asset maturity | BD can identify acquisition vs option/license/partnership realism |

### Backtest results and validation limits

Latest expanded M&A replay inspected:

```text
run_id: 52d9bf04-db0a-4e7e-86df-c5ab75ee11cb
period: 2021-01-01 to 2026-05-15
universe size: 84
decisions: 19
mean net return: -3.06%
hit rate: 36.8%
status: directional_only
```

The significance report did not support statistically significant alpha. Therefore M&A probability outputs should be labeled research-grade/directional.

## 11. Weekly Intelligence / Thesis Tracker

Primary files:

- `src/bve/intelligence/thesis_tracker.py`
- `src/bve/intelligence/actionable_output.py`
- `src/bve/intelligence/decision_layer.py`
- `src/bve/intelligence/weekly_review.py`
- `src/bve/intelligence/knowledge_layer.py`

Implemented capabilities:

- Claims with lifecycle: open, confirmed, refuted, expired, superseded.
- Weighted thesis strength by claim type.
- Structured evidence ingestion into KnowledgeStore.
- Decision records with recommended versus executed actions.
- Position snapshots and outcome attribution.
- Weekly review across fundamental, timing, thesis, and sizing sections.

Current gaps:

- Evidence ingestion quality depends on extraction/connectors and manual review.
- Forced action logic exists through actionable output and policies, but still needs governance for production use.
- Claim confirmation is only as good as stored signals.
- Portfolio-level decision discipline requires human process.

## 12. Historical Replay / Backtesting

Primary file: `src/bve/ops/historical_replay.py`.

Replay supports:

- `seed`
- `seed-signals`
- `run`
- `summary`
- `significance`
- `walk-forward`
- `inspect`

Point-in-time controls:

- historical prices/events/signals use `<= as_of_date`
- dated snapshots only
- M&A predictions from snapshots as of decision date when available

Current known Tier D audit:

| Run | Universe | Hold | Decisions | Mean net | Hit rate |
|---|---:|---:|---:|---:|---:|
| Baseline 28d | 27 | 28d | 20 | -2.54% | 40.0% |
| Baseline 14d | 27 | 14d | 21 | -4.09% | 33.3% |
| Baseline 45d | 27 | 45d | 21 | -1.40% | 47.6% |
| Expanded M&A | 84 | 28d | 19 | -3.06% | 36.8% |

Valid conclusions:

- The replay framework works.
- The current policy did not show robust positive alpha.
- Timing errors dominate observed failures.
- Sample size is too small for strong statistical conclusions.

Invalid conclusions:

- Do not claim the M&A probability model predicts takeouts accurately.
- Do not claim investment-grade alpha.
- Do not generalize across TAs from sparse replay results.

## 13. Data Sources

### Repo/config data

- YAML asset configs under `examples/configs/`.
- Watchlists under `examples/configs/watchlists/`.
- Acquirer profiles under `examples/research/acquirer_profiles/`.
- M&A comparables under `research/mna/comparable_deals.yaml`.
- Deal universe under `research/mna/deal_universe_2020_2026.yaml`.
- Vulnerability signals under `research/mna/vulnerability_signals.yaml`.

### Hardcoded or centralized assumptions

- `src/bve/config/industry_assumptions.yaml`
- `src/bve/config/constants.py`
- score weights in M&A modules
- scenario shocks and caps

### Public data connectors

- ClinicalTrials.gov
- FDA
- SEC EDGAR
- PubMed
- market prices via yfinance
- press releases

### Paid/proprietary data needed

- Biomedtracker / Citeline / PharmaProjects historical outcomes
- Evaluate / Cortellis / Informa deal databases
- Orange Book plus patent/exclusivity legal review
- IQVIA/Symphony claims and launch curves
- Capital IQ / FactSet ownership and financing history
- Banker/process intelligence where available

### Expert judgment needed from BD

- strategic urgency
- internal build-versus-buy preference
- likely deal structure
- hidden blockers
- seller willingness
- alternative bidder map
- rights/control interpretation

## 14. Validation / Testing

Current test surface:

- Latest full suite result: 12,051 passed, 1 skipped.
- Tests cover valuation math, POS (base rate hierarchy, all adjuster types, BTD types, data maturity, CMC risk, competitive benchmark, regulatory actions, POS CI), revenue sanity, cost defaults, CMC, LOE, taxes, Monte Carlo, M&A scoring, acquirer fit, M&A probability, catalyst hazard scaling, deal encumbrance, antitrust regime, stage-specific priors, M&A calibration dataset schema, replay, PIT queries, calibration, APIs, dashboards, and stress.

Validation types present:

| Type | Status |
|---|---|
| Unit tests | Implemented broadly |
| Known-answer tests | Implemented for some rNPV/deal cases |
| Regression tests | Implemented |
| Replay/backtests | Implemented |
| Significance tests | Implemented |
| M&A calibration dataset framework | Implemented; dataset curation pending |
| Cross-TA POS calibration | Incomplete |
| External independent audit | Missing |

Needed for investment committee credibility:

- larger labeled clinical outcome dataset
- held-out calibration for POS
- larger M&A takeout/control dataset (≥50 positives + ≥100 negatives, no lookahead)
- explicit model-grade labels by output
- third-party formula review
- data provenance freshness dashboard
- BD expert-reviewed acquirer profiles

## 14A. Exact Formula Library and Output Interpretation

This section mirrors the older report's formula-first style. The formulas below describe the implemented model families; exact field names vary by entity/config.

### POS log-odds adjustment

Implemented in `src/bve/models/pos_model.py`.

```text
logit(p) = ln(p / (1 - p))
adjusted_logit = logit(base_phase_probability) + sum(adjustments)
adjusted_probability = sigmoid(adjusted_logit)
final_pos = min(adjusted_probability, pos_ceiling)
```

Base rate selected by hierarchy: indication_subtype > modality > TA. Layer 1 caps large positive and negative evidence packages before converting back to probability. The current model is directionally sensible but still needs held-out calibration by phase, therapeutic area, endpoint type, and modality.

### POS uncertainty interval

Implemented in `src/bve/models/pos_model.py`.

```text
for each adjuster:
    sample from Triangular(min_logodds, mode_logodds, max_logodds)
    (UNKNOWN inputs use wider bounds, not zero-variance)

adjusted_logit_sample_i = base_logit + sum(sampled_adjustments_i)
pos_sample_i = sigmoid(adjusted_logit_sample_i)

pos_ci_low  = percentile_5(pos_samples)
pos_ci_high = percentile_95(pos_samples)
```

Default 500 samples. Confidence interval width reflects analyst uncertainty about adjuster magnitudes, not just sampling noise.

### Trial-design/regulatory evidence adjustment

Implemented in `src/bve/models/trial_design_features.py`.

```text
design_adjustment =
    endpoint_quality
  + comparator_fit
  + regulatory_pathway_quality
  + sample_size / evidence penalties

phase_scaled_adjustment = design_adjustment * phase_weight
final_adjustment = clip(phase_scaled_adjustment, lower_cap, upper_cap)
```

Combined Layer 1 + Layer 2 cap: ±0.90. Current guardrail: design evidence is separated from biology/POS, but the overlap checker is conservative and not yet an institutional-grade double-counting detector.

### Cumulative probability of approval

Implemented in `src/bve/models/probability_model.py`.

```text
probability_reaching_phase_i = product(success_probability_j for all prior phases j)

cumulative_probability_of_approval =
    product(success_probability_i for all phases i in the remaining development path)
```

### Revenue in a forecast year

Implemented across `src/bve/models/market_model.py` and `src/bve/models/revenue_model.py`.

```text
eligible_patients_t =
    prevalence_or_incidence
  * diagnosis_rate
  * treatment_rate
  * line_of_therapy_share
  * geography_launch_factor_t
  * payer_access_factor_t

treated_patients_t = eligible_patients_t * penetration_t

net_price_t =
    list_or_WAC_price_t
  * (1 - gross_to_net_discount_t)

revenue_t =
    treated_patients_t
  * net_price_t
  * adherence_or_duration_factor
  * competition_factor_t
  * LOE_factor_t
```

### EBIT and free cash flow bridge

```text
gross_profit_t = revenue_t * gross_margin_t
SG&A_t = revenue_t * SG&A_percent_t
EBIT_t = gross_profit_t - SG&A_t - other_operating_costs_t

deal_adjusted_EBIT_t =
    EBIT_t
  - revenue_t * royalty_rate
  - EBIT_t * profit_share_rate

tax_t = max(deal_adjusted_EBIT_t, 0) * cash_tax_rate_t

after_tax_FCF_t =
    deal_adjusted_EBIT_t
  - tax_t
  - capex_t
  - working_capital_t
```

### Probability-weighted development cost

Implemented in `src/bve/models/cost_model.py`.

```text
PV_trial_cost_i =
    trial_cost_i
  * probability_reaching_trial_i
  * ownership_or_cost_share_i
  * inflation_factor_i
  / (1 + discount_rate) ^ timing_i

total_PV_development_cost =
    sum(PV_trial_cost_i)
  + PV_CMC
  + PV_payable_milestones
  + PV_upfronts
  + PV_post_approval_commitments
```

### rNPV

Implemented in `src/bve/models/rnpv_model.py`.

```text
PV_commercial_cash_flows =
    probability_of_approval
  * sum(after_tax_FCF_t * net_ownership / (1 + WACC)^t)

rNPV =
    PV_commercial_cash_flows
  - total_PV_probability_weighted_development_cost
  + PV_receivable_milestones
  + upfront_receipts
```

### NAV/share

```text
company_NAV =
    sum(asset_rNPV)
  + net_cash
  - debt
  - corporate_overhead_PV
  +/- other_adjustments

NAV_per_share = company_NAV / diluted_shares_outstanding
```

### Market-implied POS

```text
market_asset_value =
    enterprise_value
  - non_target_asset_value
  - net_cash_adjustments

market_implied_POS =
    value_required_by_market / undiscounted_or_probability_unadjusted_asset_value
```

### Acquisition discount

```text
enterprise_value = market_cap - net_cash
acquisition_discount = model_asset_rNPV / enterprise_value
```

The implementation intentionally uses already risk-adjusted rNPV and avoids applying POS a second time.

### M&A probability score (Layer 5 closing model)

```text
raw_MA_score =
    w1 * target_attractiveness
  + w2 * capital_vulnerability
  + w3 * scarcity
  + w4 * acquirer_fit
  + w5 * transaction_timing
  + w6 * valuation_dislocation

gated_score = apply_hard_fails_and_caps(raw_MA_score)
p_any_strategic_12m = shrink(gated_score, base_rate, cohort_rate, confidence)

# Closing feasibility (separate from strategic interest)
p_effective_close_12m =
    p_any_strategic_12m
  × encumbrance_close_multiplier
  × antitrust_multiplier

calibrated_probability = p_effective_close_12m  # or p_any if encumbrance=NONE
```

The separation of `p_any_strategic_12m` from `p_effective_close_12m` is a deliberate design invariant: strategic interest scores must not be mutated by operational deal friction.

### What output should be trusted first

| Output | Trust level today | Why |
|---|---|---|
| rNPV bridge | Higher | Formula path is explicit and testable. |
| NAV/share | Medium-high | Useful if balance sheet/share count are fresh. |
| Scenario range | Medium-high | Good for sensitivity framing, not prediction. |
| Monte Carlo percentiles | Medium | Good distributional view; input distributions dominate. |
| POS uncertainty interval | Medium | Meaningful when inputs are explicit; width reflects ignorance. |
| Market-implied POS | Medium | Helpful diagnostic, but can be confounded. |
| Acquisition discount | Medium | Good screen, but not a deal thesis alone. |
| Acquirer ranking | Medium | Useful for BD discussion, needs profile review. |
| p_effective_close_12m | Low-medium | Directional; encumbrance/antitrust informed but still heuristic. |
| Exact M&A probability | Low-medium | Directional only until calibration dataset is sufficient. |
| Deal structure recommendation | Low-medium | Good workflow hint, not yet validated. |

## 15. Institutional Gap Analysis

| Area | Current status | Why it matters | Institutional requirement | Severity | Recommended fix |
|---|---|---|---|---|---|
| POS calibration | Partially implemented | POS drives valuation | Held-out cross-TA calibration | High | Expand outcome dataset and calibrate adjusters |
| M&A probability | Partially validated | Probability language can mislead | Labeled takeout/control model | High | Build pair-level deal panel and report precision/recall |
| Acquirer profiles | Config-driven | Buyer logic changes fast | Source-dated profile refresh process | High | Add profile freshness checks and BD review workflow |
| Rights/control | Encumbrance implemented; regional/CoC partial | Can block acquisition | Structured rights model | Medium-high | Add regional rights and change-of-control contract fields |
| IP/LOE | Partially implemented | Drives value and urgency | Asset-specific expiry/exclusivity table | High | Add patent/exclusivity module |
| Seller willingness | Partially implemented | Fit does not imply process | Evidence-backed willingness model | High | Add process/ownership/banker signal fields |
| Antitrust | Implemented — tier + regime + sub-signals | Strategic fit can create risk | Validated overlap scoring | Medium | Tier selection is still analyst judgment; automate from market share data |
| Deal structure | Partially implemented | Acquisition vs license vs option matters | Structure probability model | Medium | Train/rules engine by stage/rights/buyer |
| CMC risk | Costed + CMC risk adjuster in POS | Manufacturing can break deals | Modality/process risk score | Medium | Add acquirer CMC-capability fields |
| Replay N | Low | Statistical power inadequate | Larger PIT dataset | High | Backfill snapshots and labels |
| M&A calibration dataset | Framework complete; dataset absent | Without labels, probability is heuristic | ≥50 positives + ≥100 negatives | High | Curate no-lookahead labeled dataset (Block 37C) |
| POS CI in memos | Computed but not exposed in default output | Point estimates mislead | CI shown alongside POS in reports | Medium | Wire `compute_pos_with_ci()` into ValuationOutput |

## 16. Highest-ROI Roadmap

### Must fix now

| Item | Why | Build | Data needed | Files affected | Acceptance criteria |
|---|---|---|---|---|---|
| M&A status labels | Prevent overclaiming | Add output-grade labels and warnings | Existing replay metrics | `ma_probability.py`, CLI renderer | Reports say directional/research-grade unless validation threshold met |
| Acquirer profile freshness | Stale profiles mislead BD | Add `profile_as_of` checks and stale warnings | Profile dates | `acquirer_profiles.py`, CLIs | Profiles >180 days flagged |
| Pair-level validation panel | Needed for probability credibility | Build acquirer-target-date dataset | Deal universe, snapshots, acquirer labels | `ma_calibration.py`, replay | Precision/recall/acquirer accuracy report |
| POS CI in ValuationOutput | Point estimates mislead; CI now computed | Wire `compute_pos_with_ci()` into engine output | None (already implemented) | `valuation_engine.py`, `outputs.py` | POS range shown in BD/HF memos |

### High-value next

| Item | Why | Build | Data needed | Files affected | Acceptance criteria |
|---|---|---|---|---|---|
| IP/exclusivity module | LOE urgency and deal value | Patent/exclusivity table and scoring | Orange Book/patent data | valuation, M&A profiles | LOE urgency uses exact expiry where available |
| Seller willingness model | Fit is not enough | Ownership/process/financing/management signal model | SEC 13D, financing, banker/process signals | `vulnerability_signals.py`, `ma_scoring.py` | Seller score has evidence refs |
| Deal structure predictor | BD needs structure realism | Acquisition/license/option/co-dev classifier | Historical deal structures | `ma_layer4_routing.py`, new calibration | Output includes structure probability |
| Buyer-specific valuation logic | Different buyers pay differently | Acquirer-specific comps and budget curves | Deals by acquirer | `acquirer_fit.py` | Fit reports show buyer-specific value band |
| M&A calibration dataset curation | Without labels, calibration is heuristic | Curate ≥50 positives + ≥100 negatives | Public deal records + no-lookahead validation | `ma_calibration_dataset.py` | `check_fit_readiness()` returns ready=True |

### Nice to have

- Antitrust tier automation from commercial overlap data (tier is currently analyst-set).
- Manufacturing capability map by acquirer.
- Conference/earnings-call source refresh automation.
- Formal review UI for BD feedback.
- Regional rights schema (full acquisition vs regional license feasibility).

### Lower priority / overengineered risk

- More score versions without more labels.
- More complex neural models before the dataset is credible.
- Fine-grained probability decimals when the real uncertainty is qualitative.

### 20 most important assumptions

1. Phase success probabilities are directionally applicable to the asset's stage, TA, and modality.
2. POS adjusters improve discrimination rather than simply encoding optimism.
3. Trial-design evidence is not double-counted with core clinical evidence.
4. Remaining phase durations approximate real development timing.
5. Patient population estimates are current and not inflated.
6. Diagnosis, treatment, and line-of-therapy shares reflect real clinical practice.
7. Net price and gross-to-net assumptions are achievable.
8. Payer access does not materially lag modeled launch uptake.
9. Competitive erosion is neither understated nor double-counted.
10. LOE erosion timing and shape are reasonable for the asset and market.
11. Gross margin, SG&A, tax, capex, and working capital assumptions match commercialization reality.
12. CMC and trial costs are stage- and modality-appropriate.
13. Royalty/profit-share inputs capture the economics that are known.
14. Cash, debt, shares, and market capitalization are point-in-time accurate.
15. Comparable deals are truly comparable by stage, asset type, indication, and rights.
16. Acquirer profiles reflect current strategy, not stale public messaging.
17. Pipeline gaps represent real buyer urgency.
18. Seller willingness can be approximated from public signals, with limited confidence.
19. M&A takeout labels are sufficient for directional calibration only; fit gate enforces minimum dataset size.
20. Backtests are interpreted as process validation unless statistical power is adequate.

### 20 biggest risks and limitations

1. POS calibration can dominate valuation error.
2. Commercial peak-sales assumptions can overwhelm all other variables.
3. Public data can miss hidden clinical, regulatory, CMC, or legal blockers.
4. Market-implied POS can be distorted by non-asset factors.
5. Scenario and Monte Carlo outputs can look more precise than the inputs justify.
6. Acquirer-profile curation can become stale after one earnings call, pipeline failure, or deal.
7. Strategic fit can be high while transaction probability is low.
8. Seller unwillingness is difficult to infer from public filings.
9. Rights, royalties, and regional splits are not yet modeled deeply enough for full diligence.
10. Antitrust tier selection requires analyst judgment; sub-signals are informational, not automated.
11. Comparable deal data may mix true upfront economics with headline biobucks.
12. Deal structure routing is not yet calibrated.
13. Sparse takeout/control labels limit probability credibility despite the fit gate framework.
14. Historical replay sample size is too small for strong alpha claims.
15. Manual YAML inputs can create silent assumption drift.
16. Backtest universes can suffer survivorship or availability bias.
17. Clinical text extraction depends on source quality and extraction confidence.
18. The M&A model may overweight public investor signals relative to private BD reality.
19. Exact probability decimals can create false confidence; POS CI should be shown alongside point estimates.
20. The tool cannot replace expert diligence on science, legal control, manufacturing, or buyer intent.

### 20 highest-value next improvements

1. Wire `compute_pos_with_ci()` into `ValuationOutput` and all BD/HF memo templates.
2. Add structured asset-control and regional rights schema.
3. Add exact royalty-stack modeling by asset and territory.
4. Add IP/exclusivity and patent-expiry diligence fields.
5. Add acquirer profile freshness warnings in all M&A outputs.
6. Add BD-reviewed fields and review history to acquirer profiles.
7. Expand the pair-level acquirer-target historical panel to meet the fit gate (≥50/≥100).
8. Separate takeout, license, option, partnership, and royalty-deal labels in dataset.
9. Calibrate M&A probability bands against a larger historical dataset.
10. Add seller-willingness model with evidence references.
11. Automate antitrust tier from commercial overlap data where available.
12. Add manufacturing-complexity and acquirer-CMC-capability fields.
13. Add source-quality grades to comparable deals.
14. Expand market-implied POS diagnostics for multi-asset companies.
15. Add confidence labels to every major valuation output.
16. Add assumption freshness checks for market data, cash, shares, and clinical events.
17. Add independent formula audit fixtures for more valuation paths.
18. Build a BD feedback review workflow that writes structured config deltas.
19. Add dashboard views for why a target is actionable versus merely interesting.
20. Tighten output language so unvalidated scores are labeled as directional screens.

## 17. Final Assessment

### Could this tool help identify asymmetric biotech investments?

Yes, as a research system. It can expose model-versus-market disagreements, catalyst skew, valuation sensitivity, thesis evidence, and now POS uncertainty ranges. It should not yet be trusted as an autonomous alpha engine.

### Could it help identify acquisition targets?

Yes, for screening and prioritization. The acquirer-fit and M&A probability modules are genuinely useful for surfacing plausible targets and buyers. The M&A closing model now separately captures deal encumbrance and antitrust regime effects, which is a meaningful step toward institutional-grade output. The largest weakness remains missing non-public BD data and limited labeled validation.

### Which parts are genuinely useful today?

- Single-asset rNPV and NAV/share.
- Sensitivity and Monte Carlo ranges.
- Market-implied POS and variant perception.
- POS uncertainty intervals via `compute_pos_with_ci()`.
- Acquisition discount screen.
- Acquirer fit ranking.
- M&A watchlist monitoring with catalyst hazard, encumbrance, and antitrust context.
- Historical replay framework.
- Stage-specific transaction type priors (acquisition vs license framing by stage).

### Which parts should not be trusted yet?

- Exact M&A probabilities.
- Acquirer top-1 predictions without manual BD review.
- Seller willingness.
- Deal structure recommendation.
- Cross-TA POS calibration where historical support is sparse.
- Antitrust tier assignment without commercial overlap data.

### What would make it credible to BD, hedge fund, or biotech investor users?

- BD-reviewed acquirer profiles.
- Rights/control/IP diligence fields (especially regional rights and exact patent expiry).
- Larger labeled M&A and clinical outcome datasets passing the fit readiness gate.
- Freshness checks on every external assumption.
- Explicit probability calibration and confidence bands (POS CI already implemented; needs wiring into outputs).
- Conservative output language that distinguishes ranking from probability.
- A workflow for BD experts to correct assumptions and convert feedback into config fields.
