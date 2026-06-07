# Single-Asset Valuation and M&A Layer Report

**Date:** 2026-05-17  
**Repository:** Biotech Asset Valuation Engine  
**Scope:** Single-asset valuation, acquisition discount screening, acquirer fit, M&A probability, BD/M&A decomposition, historical replay, and the controls used to keep outputs auditable.

## Executive Summary

The Biotech Asset Valuation Engine (BVE) is a reproducible valuation and intelligence system for clinical-stage biotech assets. Its core unit is a single-asset valuation: a YAML-defined asset, company, trial path, and commercial model are converted into probability-adjusted rNPV, NAV per share, scenarios, Monte Carlo output, sensitivities, assumption logs, market-implied expectation comparisons, runway/dilution context, catalyst payoff, analog checks, and top acquirer matches.

The M&A stack builds on the same valuation math. It does not create a separate "deal model" detached from rNPV. Instead, it reuses the single-asset rNPV engine, compares model value to enterprise value, evaluates whether the asset is mature enough to transact, compares the target to precedent biotech M&A deals, scores strategic fit against curated acquirer profiles, estimates acquisition probability, and stores daily probability snapshots for historical replay.

The system is designed to be accurate in the institutional sense: not by pretending that clinical forecasts are precise, but by making assumptions explicit, preserving provenance, applying deterministic formulas, logging versioned score regimes, surfacing limitations, and testing results against historical outcomes. The latest expanded M&A replay remains directional only, not statistically validated alpha, which is the correct conclusion given current sample size.

## Main User Workflows

### 1. Single-Asset Valuation

Command:

```bash
bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts
```

Primary code path:

- CLI: `src/bve/cli/run_asset.py`
- Orchestrator: `src/bve/valuation/valuation_engine.py`
- Output model: `src/bve/valuation/outputs.py`

Outputs:

- `valuation.json`: full machine-readable run artifact
- `bd_memo.md` / `bd_memo.docx`: BD memo
- Optional VC and hedge-fund memos
- Charts: rNPV distribution, tornado sensitivity, revenue curve, scenario bars, catalyst timeline

### 2. Acquisition Discount Screen

Command:

```bash
bve-acquisition-screen --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml
```

Primary code path:

- `src/bve/intelligence/acquisition_screen.py`

This layer runs only the core rNPV stack for each watchlist asset and computes:

```text
enterprise_value = market_cap - net_cash
acquisition_discount = model_rnpv / enterprise_value
```

The engine explicitly avoids multiplying by approval probability twice because rNPV is already risk-adjusted.

### 3. Acquirer Fit Screen

Command:

```bash
bve-acquirer-fit \
  --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml \
  --acquirer vertex_pharmaceuticals \
  --profiles-file examples/research/acquirer_profiles \
  --top 15 \
  --readiness-filter off \
  --output-format report
```

Primary code path:

- `src/bve/intelligence/acquirer_fit.py`
- `src/bve/intelligence/acquirer_profiles.py`
- `src/bve/intelligence/comparable_deals.py`

This layer ranks target assets for one buyer by therapeutic fit, modality fit, stage, strategic priority, valuation, and budget capacity.

### 4. M&A Probability Scan

Command:

```bash
bve-ma-probability \
  --watchlist examples/configs/watchlists/watchlist_replay_expanded_phase2.yaml \
  --profiles-file examples/research/acquirer_profiles \
  --top 25
```

Primary code path:

- `src/bve/intelligence/ma_probability.py`

This layer turns target attractiveness, acquirer fit, acquisition discount, de-risking stage, capital vulnerability, scarcity, and transaction triggers into a ranked M&A probability screen.

### 5. Full Historical Backtest

Command:

```bash
PYTHONPATH=src .venv/bin/python -m bve.ops.historical_replay run \
  --start 2021-01-01 \
  --end 2026-05-15 \
  --profile mna \
  --universe-file examples/research/universe_expanded_mna.yaml \
  --cadence quarterly \
  --max-hold-days 28 \
  --max-positions 2 \
  --max-open-positions 2 \
  --catalyst-timing \
  --cooling \
  --require-catalyst-days 90 \
  --min-thesis-score 0.50
```

Follow-up commands:

```bash
PYTHONPATH=src .venv/bin/python -m bve.ops.historical_replay summary --run-id <RUN_ID>
PYTHONPATH=src .venv/bin/python -m bve.ops.historical_replay significance --run-id <RUN_ID>
PYTHONPATH=src .venv/bin/python -m bve.ops.historical_replay walk-forward --run-id <RUN_ID>
```

Primary code path:

- `src/bve/ops/historical_replay.py`
- `src/bve/analysis/replay_significance.py`
- `src/bve/analysis/replay_evaluator.py`

## Single-Asset Valuation Engine

### Inputs

A valuation config defines:

- Asset identity, therapeutic area, indication, modality, stage, discount rate, royalty rate, mechanism of action, catalysts, competitors, and notes.
- Company data: ticker, cash, debt, shares, burn rate, current price, and notes.
- Trial path: phase, duration, cost, endpoint, success probability, enrollment, and NCT ID.
- Market model: addressable patients or TAM, price, penetration, years to peak, patent life, COGS, SG&A, competition, lifecycle events, and line-of-therapy segments where relevant.
- Optional POS adjusters and trial-design adjusters.
- Optional comparable deals and memo-specific thesis framing.

The CLI validates required fields and enum values before the engine runs. This prevents silent use of malformed configs.

### Core Computation

`ValuationEngine.run()` executes the following sequence:

1. Prepare trials.
2. Apply heuristic, empirical, calibrated, or fitted POS mode when configured.
3. Apply trial-design POS adjustments when configured.
4. Resolve SG&A profile and LOE erosion profile.
5. Run revenue sanity checks.
6. Substitute default phase costs where appropriate.
7. Compute probability, revenue, cost, and rNPV.
8. Convert asset rNPV into company NAV and NAV/share.
9. Build bear/base/bull scenarios.
10. Run Monte Carlo.
11. Run sensitivity analysis.
12. Build the assumption log.
13. Attach lifecycle-event summaries and provenance hashes.
14. Attach optional deal-comps analysis.
15. Compute market-implied expectation, runway, dilution, launch analogs, catalyst payoff, variant perception, and top acquirers.

### rNPV Method

The rNPV stack is probability-weighted DCF:

```text
rNPV = P(approval) * PV(commercial EBIT) - sum(P(reaching phase_i) * PV(cost_i))
```

The important discipline is that development costs are weighted by the probability of reaching each phase, while commercial cash flows are weighted by cumulative approval probability. This makes late-stage failures and phase costs economically visible without treating all future cash flows as certain.

### Probability of Success

The tool supports several POS layers:

- Raw trial success probabilities from the YAML config.
- Heuristic log-odds adjusters on top of base rates.
- Trial-design adjustments for design quality, comparator fit, pathway risk, power, and related evidence features.
- Empirical POS modes when an empirical POS engine is available.
- Calibrated or fitted overlays when calibration artifacts exist.

The design is intentionally layered. Clinical prior, evidence quality, and empirical calibration are distinct concepts, so the code keeps them separable and blocks critical double-counting where trial-design features overlap with POS adjusters.

### Revenue and Commercial Model

The revenue layer supports:

- Addressable-patient or TAM-based modeling.
- Net price and gross-to-net basis checks.
- Peak penetration and years-to-peak.
- Patent-life and LOE erosion profiles by modality.
- COGS and SG&A.
- Competition and lifecycle events.
- A revenue audit table that decomposes year-by-year revenue, uptake, competition, price pressure, payer access, COGS, SG&A, and EBIT.

Accuracy comes from making the commercial model explicit. The engine warns on unusual commercial assumptions, such as very high net price or linear uptake for specialty markets where an S-curve may be more realistic.

### Scenario, Monte Carlo, and Sensitivity

The scenario engine produces bear/base/bull cases. Monte Carlo samples uncertainty around POS, peak sales, discount rate, years to peak, and correlated commercial drivers. Sensitivity analysis identifies the largest rNPV swings and ranks them for tornado charts.

This matters because a single rNPV point estimate is rarely enough for biotech. The tool is built to show whether the thesis depends mainly on clinical success, peak penetration, price, duration, discount rate, or cost.

### Market-Implied Expectations

When company price and shares are available, the engine back-solves what the market is implying:

- market-implied POS
- model POS
- POS gap
- market-implied peak sales / variant perception where available

This converts valuation from "what is fair value?" into "what does the market already believe, and where does the model disagree?"

### Capital and Catalyst Context

The single-asset output can also attach:

- Cash runway forecast from cash and burn.
- Dilution scenarios when remaining trial costs exceed available cash.
- Catalyst payoff decomposition with value-if-success and value-if-failure.
- Launch analog matches by mechanism and indication.
- Top acquirer matches from the built-in acquirer universe.

These layers are not replacements for rNPV. They are decision context around whether the valuation can be financed, what catalyst skew looks like, and who might care strategically.

## M&A Layer 1: Acquisition Discount

The acquisition screen asks whether model value is large relative to enterprise value.

Inputs:

- Watchlist asset.
- Valuation config.
- Market cap from KnowledgeStore, watchlist override, company snapshot, or price times shares.
- Net cash.

Outputs:

- model rNPV
- model POS
- market cap
- enterprise value
- acquisition discount
- EV / peak sales
- acquisition readiness fields
- comparable-deal enrichment where available

Formula:

```text
enterprise_value = market_cap - net_cash
acquisition_discount = model_rnpv / enterprise_value
```

Important exclusions:

- missing valuation config
- valuation context error
- valuation error
- missing market cap
- non-positive enterprise value
- not acquisition-ready when the strict readiness filter is enabled

## M&A Layer 2: Acquisition Readiness

The acquisition-readiness gate prevents early or weakly de-risked assets from being treated like actionable M&A targets.

Rules:

- Phase 3, NDA/BLA, approved, and commercial assets are acquisition-ready by stage.
- Preclinical and Phase 1 assets fail readiness.
- Phase 2 assets require evidence from the KnowledgeStore.
- A Phase 2 readout must show primary endpoint success, quantitative de-risking, and adequate design quality.
- Low-power readouts, negative readouts, missing readouts, and posterior POS that does not improve over prior POS fail readiness.

This prevents the screen from ranking assets purely because they are cheap. Cheapness only matters if the asset is credible enough to transact.

## M&A Layer 3: Comparable Deals

Comparable-deal analysis loads curated biotech M&A deals and normalizes indication, biological target, and mechanism of action. Matching proceeds by:

1. canonical indication plus phase
2. therapeutic area plus phase
3. phase only
4. no comps

For matched deals, the tool computes:

- peer min / median / max EV-to-peak-sales
- percentile versus comps
- premium or discount versus median
- fair-value bands for enterprise value, upfront, and total biobucks
- high/medium-quality fair-value bands where available

This layer gives the valuation screen a market precedent check. A target can be theoretically valuable but still expensive relative to precedent deals.

## M&A Layer 4: Acquirer Fit

The acquirer-fit engine ranks one target universe against one acquirer profile.

Curated acquirer profiles include:

- therapeutic-area gaps
- preferred modalities
- strategic priorities
- existing partnerships
- budget / net cash / acquisition capacity
- recent deal behavior

The standard scoring components are:

- therapeutic area
- modality
- stage
- strategic priority
- valuation
- budget

Hard fails include:

- pre-Phase 2 stage
- not acquisition-ready when strict readiness is required
- outside budget

For profiles that use pipeline-gap scoring, the engine emphasizes:

- matched pipeline gap
- urgency
- TA fit
- modality fit
- stage fit
- budget fit
- existing partnership or acquisition option

The output includes the raw fit score, final fit score, hard-fail reasons, matched gap, matched modality, matched priorities, budget headroom, valuation source, comparable-deal context, and explanation text.

## M&A Layer 5: M&A Probability

The M&A probability scanner builds on acquisition discount, acquirer fit, vulnerability, targetability, scarcity, and transaction triggers.

Major components:

- acquisition discount / valuation component
- strategic fit
- de-risking stage
- capital vulnerability
- scarcity
- best acquirer and runner-up acquirer
- transaction driver count
- gap urgency
- BD pattern adjustment
- optional calibrated takeout probability

Score versions are explicit. Current versions include `v1.0` through `v1.4`, with different weights. This is critical because changing the scoring philosophy changes backtest interpretation. Score versioning makes old results reproducible.

The scanner also applies targetability rules:

- excludes known acquirers as targets
- excludes explicitly banned tickers
- excludes mega-caps above configured thresholds
- excludes commercial franchises above configured revenue-share thresholds
- applies soft penalties for multi-product commercial companies
- applies market-cap penalties for large targets

The probability layer persists daily snapshots in `ma_probability_snapshots`, including rank, probability, best acquirer, score components, candidate acquirers, and calibration fields. Historical replay uses only snapshots available as of the decision date.

## M&A Layer 6: BD / M&A Decision Decomposition

The BD/M&A decomposition layer answers the questions a senior BD team would ask before pursuing a deal.

Composite weights:

- asset quality: 30%
- value creation: 20%
- transaction timing: 20%
- strategic fit: 25%
- deal feasibility: 5%

Asset quality includes:

- clinical evidence
- differentiation
- regulatory path
- IP durability
- CMC feasibility
- commercial meaningfulness

Value creation includes:

- premium-adjusted rNPV gap
- synergy upside
- downside protection
- cost to complete
- capital solution value

Transaction timing includes:

- financing pressure
- seller willingness
- transaction window quality
- external deal activity
- catalyst setup

Strategic fit includes:

- TA fit
- modality fit
- pipeline gap urgency
- development capability
- commercial capability
- CMC capability
- relationship control

Deal feasibility includes:

- affordability
- antitrust feasibility
- asset control
- integration feasibility
- bidder competition risk

Institutional gates cap the final score. They never boost it:

- G1: poor asset quality caps composite.
- G2: weak strategic fit caps composite.
- G3: negative premium-adjusted rNPV gap caps composite.
- G4: low seller willingness and low financing pressure caps composite.
- G5: poor asset control caps composite.

The output includes recommended action, recommended structure, rationale, risks, kill criteria, diligence questions, gate codes, and component scores.

## M&A Layer 7: Historical Replay and Validation

Historical replay is the validation layer. It replays decisions over historical dates and stores:

- run metadata
- decisions
- returns
- attributions
- summaries
- point-in-time notes
- M&A prediction notes

The replay summary explicitly records:

- historical prices, events, and signal snapshots use `<= as_of_date`
- dated snapshots only
- skill-adjusted return excludes POS-error and market-drift decisions
- M&A predictions come from `ma_probability_snapshots` as of the decision date where available

The summary report includes:

- decision count
- resolved decisions
- gross return
- net return after friction
- hit rate
- attribution breakdown
- skill-adjusted return
- significance tests
- baseline comparisons
- failure mode analysis
- market-regime analysis

The current expanded M&A run remains directional only. The latest Tier D run inspected was:

```text
run_id: 52d9bf04-db0a-4e7e-86df-c5ab75ee11cb
period: 2021-01-01 to 2026-05-15
universe size: 84
decisions: 19
mean net return: -3.06%
hit rate: 36.8%
validation status: directional_only
```

The engine correctly reports that this does not demonstrate statistically significant alpha. That is a feature, not a bug: the system is designed to say when the evidence is not strong enough.

## Accuracy Controls

### 1. Typed Models

The project uses Pydantic models for assets, companies, trials, market models, valuation outputs, acquirer profiles, M&A rows, and BD/M&A decomposition outputs. Invalid enum values and missing required fields are caught early.

### 2. Centralized Assumptions

Shared assumptions live in `src/bve/config/industry_assumptions.yaml`. The valuation output records:

- assumptions YAML hash
- config hash
- WACC vintage
- analyst overrides

This makes it possible to tell which defaults and overrides produced a given number.

### 3. Assumption Log

Each valuation output includes an assumption log with key drivers, sources, sensitivity ratings, limitations, and thesis changers. This turns the model into an audit artifact rather than an opaque spreadsheet.

### 4. Revenue Audit Table

The revenue audit table decomposes annual revenue and EBIT mechanics. This is important because many valuation errors come from hidden commercial assumptions rather than rNPV arithmetic.

### 5. No Double-Counting of POS

The acquisition screen explicitly notes that rNPV is already risk-adjusted and therefore does not multiply by approval probability again. The trial-design layer also checks for overlap with POS adjusters.

### 6. Point-in-Time Replay Discipline

Historical replay uses dated snapshots and as-of-date filters. M&A prediction snapshots are used only when created on or before the replay decision date.

### 7. Score Versioning

Actionable scores and M&A probability scores are versioned. This prevents a current formula from being silently applied to old decisions during analysis.

### 8. Hard Filters and Gates

The M&A system uses hard filters for targetability, readiness, stage, and budget. The BD/M&A decomposition uses gates that cap scores when institutional red flags are present.

### 9. Baselines and Significance

Replay summaries compare model performance against baselines and run significance tests. The system reports when results are not statistically significant instead of overclaiming.

### 10. Known Limitations Are Documented

`docs/model_limitations.md` records limitations around POS, revenue, data sources, portfolio modeling, and M&A. Key limitations include small validation samples, rules-based acquirer fit, estimated seller willingness, and data-source constraints.

## What the Tool Is Good At

BVE is strongest when used for:

- repeatable single-asset rNPV analysis
- explicit clinical and commercial assumption tracking
- catalyst-driven valuation framing
- market-implied expectation comparison
- watchlist-scale acquisition discount screening
- acquirer-target fit ranking
- M&A probability monitoring
- historical replay of decision policies
- post-hoc attribution of model errors versus market/timing effects

## What the Tool Should Not Be Used For Without Review

BVE should not be treated as a fully automated investment or BD decision engine. Human review is still required for:

- clinical data quality and endpoint interpretation
- management credibility
- IP diligence
- CMC diligence
- antitrust assessment
- seller willingness
- confidential strategic priorities
- commercial payer dynamics
- final deal valuation and negotiation strategy

The engine can rank and explain candidates, but it cannot replace diligence.

## Recommended Operating Procedure

For a single asset:

1. Build or update the YAML config.
2. Run `bve-asset` with memos and charts.
3. Review the assumption log, revenue audit, tornado sensitivities, and market-implied expectation.
4. Stress the top three assumptions.
5. Record thesis changers and kill criteria.

For M&A screening:

1. Run acquisition discount screen on the watchlist.
2. Apply readiness filtering.
3. Run acquirer-fit screens for named buyers.
4. Run the M&A probability scanner.
5. Inspect best acquirer, runner-up, hard-fail reasons, transaction drivers, and budget headroom.
6. Use BD/M&A decomposition for serious target-buyer pairs.
7. Persist snapshots for future replay.

For validation:

1. Seed historical prices, events, claims, and M&A snapshots.
2. Run historical replay with the intended policy.
3. Run summary, significance, and walk-forward reports.
4. Compare to baselines.
5. Treat results as directional until sample size and significance improve.

## Bottom Line

The tool is a valuation engine first and an M&A intelligence layer second. The single-asset valuation stack produces auditable rNPV, NAV/share, uncertainty, sensitivity, and market-expectation outputs. The M&A stack then asks whether that asset is cheap enough, de-risked enough, strategically relevant enough, financially feasible enough, and timely enough for a buyer to act.

Its accuracy comes from reproducibility, provenance, typed inputs, deterministic scoring, point-in-time replay, explicit limitations, and refusal to overstate validation. The current M&A layer is useful for screening and research-grade prioritization; it should be escalated to capital or deal decisions only after human diligence and stronger validation evidence.
