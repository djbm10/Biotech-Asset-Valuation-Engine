# Biotech Asset Valuation Engine (BVE)

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Version](https://img.shields.io/badge/version-0.2.0-green)
![Tests](https://img.shields.io/badge/tests-11%2C158%20passing-brightgreen)

BVE helps biotech investors and BD/strategy teams evaluate whether a biotech asset is
**undervalued by the market**, **strategically actionable for BD/M&A**, or **worth
monitoring before a clinical or regulatory catalyst**.

It is a structured research and triage engine — not an autonomous investment system.
Every output is annotated with its confidence level and the assumptions that drive it.

---

## The Three Commands

### 1. Evaluate a specific target

```bash
bve-evaluate-target --ticker SRPT
bve-evaluate-target --ticker SRPT --output outputs/srpt_decision.md
```

Produces a single Markdown decision report: valuation, M&A probability, management
quality, input integrity, prediction log history, and model validation summary.

**Use when:** You have a company in mind and need an all-surfaces view before a
meeting, diligence call, or investment committee.

---

### 2. Run the morning screen

```bash
bve-morning-screen
bve-morning-screen --top 15 --output outputs/screen_$(date +%F).md
```

Produces a ranked daily screen across the tracked universe: top M&A candidates,
valuation dislocations, catalyst watchlist, CT.gov changes, stale inputs, and
unresolved predictions. All sections degrade gracefully when data is absent.

**Use when:** Starting the day and need to know what deserves attention.

---

### 3. Check model credibility

```bash
bve-validate
bve-validate --output outputs/validation_report.md
```

Produces a validation and credibility report: POS backtest grade, known-answer
suite results, and an overall letter grade (A / B / C / D).

**Use when:** Before presenting outputs to a new audience, after a model change, or
as a regular sanity check. **This is the highest-confidence output in the system.**

---

## Quickstart

```bash
# 1. Install
conda create -n biotech-env python=3.11 -y && conda activate biotech-env
pip install -e ".[dev]"

# 2. Run the canonical real-world case (Relay Therapeutics / RLY-2608)
bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts

# 3. Outputs land in outputs/RLAY/
```

### Scaffold a new asset from scratch

```bash
bve-init-asset --ticker SRPT
# Creates configs/SRPT/ and outputs/SRPT/ with annotated templates.
# Fill them in, then run bve-asset to generate the valuation.
```

---

## What to Trust

See [`docs/output_trust_guide.md`](docs/output_trust_guide.md) for the full
score-by-score breakdown. Short version:

| Output | Confidence | Note |
|---|---|---|
| Model validation grade | **Validated** | Most reliable output in the system |
| POS backtest (Brier/AUC) | **Validated** | N=99 oncology; ~15% skill vs. baseline |
| rNPV / NAV/share | Model-dependent | Inspect inputs and tornado chart first |
| P(approval) | Directional | Use for ranking, not absolute probability |
| M&A probability score | Directional | Screen signal; not a deal forecast |
| Backtest alpha | Not yet actionable | Directionally positive; statistically underpowered |

**Five things not to do with BVE outputs:**

1. Cite M&A probability scores as deal forecasts.
2. Use screening-grade configs for capital decisions.
3. Act on the morning screen without checking the staleness section.
4. Treat management quality composites as independently verified assessments.
5. Claim demonstrated forward alpha from the current backtest N.

---

## Case Studies

Three real public companies modeled through different institutional lenses.
Each produces a full memo, 5 charts, and machine-readable `valuation.json`.
All inputs are source-cited; all outputs are reproducible with `--seed 42`.

| Company | Asset | Indication | Memo type | rNPV | P(Approval) |
|---------|-------|------------|-----------|------|-------------|
| [Relay Therapeutics (RLAY)](case_studies/relay_rly2608/) | RLY-2608 | PIK3CA H1047R HR+/HER2- mBC | BD acquisition | $129M | 34.6% |
| [EyePoint Pharmaceuticals (EYPT)](case_studies/eypt_eyp1901/) | EYP-1901 | Wet AMD (nAMD) | HF mispricing | $235M | 71.9% |
| [Praxis Precision Medicine (PRAX)](case_studies/prax_ulixacaltamide/) | ulixacaltamide | Essential tremor | VC platform | $545M | 44.8% |

**Historical backtests** (model vs. known outcome):

| Company | Asset | Indication | Analysis date | Key feature |
|---------|-------|------------|---------------|-------------|
| BeiGene (BGNE) | zanubrutinib | R/R MCL | Nov 2018 (BLA) | BTK first-mover dynamics + crowding |
| Regeneron (REGN) | dupilumab | Moderate-severe AD | Jun 2016 (BLA) | Lifecycle events — atopic march franchise |
| Biogen/Eisai (BIIB) | lecanemab | Early Alzheimer's | Jul 2022 (Ph3) | Surrogate endpoint risk + CMS coverage |
| Geron (GERN) | imetelstat | Low-risk MDS | Jan 2023 (NDA) | Orphan economics; tiny population |

See [`case_studies/README.md`](case_studies/README.md) for reproduce commands.

---

## Architecture

### Valuation pipeline

```
YAML config → bve-asset CLI → ValuationEngine
  → ProbabilityModel     per-phase PoS (log-odds adjusters on Biomedtracker priors)
  → RevenueModel         annual revenue curve (LOE tail optional)
  → CostModel            probability-weighted PV of trial R&D + deal costs
  → RNPVModel            P(approval) × PV(EBIT) − PV(costs) + milestones
  → Scenario engine      Bull / Base / Bear shocks
  → Monte Carlo          10,000 correlated draws (Gaussian copula)
  → Sensitivity          Tornado analysis (5 parameters ±)
  → ValuationOutput      → valuation.json + memos + charts
```

### Intelligence OS

```
KnowledgeStore (SQLite ops.db)
  → ThesisTracker        claim lifecycle → thesis_strength
  → MAProbabilityScanner 5-layer M&A scoring → mna_probability_score
  → ActionableGenerator  composite score → action labels
  → WeeklyRunner         weekly recompute across tracked universe
```

### Product workflows (Block 12)

```
bve-evaluate-target  →  evaluate_target.py   loads all surfaces → DecisionReport
bve-morning-screen   →  morning_screen.py    6-section ranked screen
bve-init-asset       →  init_asset.py        scaffolds configs/TICKER/ templates
```

---

## Model Validation Status

Current validation surface — run `bve-validate` to see the live report:

| Component | Status | Metric |
|---|---|---|
| POS model (oncology) | **Validated** | Brier 0.2127, AUC 0.74, N=99 |
| rNPV methodology | **Validated** | Methodology; input accuracy is config-dependent |
| M&A probability | Directional | Not yet statistically validated against deal outcomes |
| Historical replay alpha | Underpowered | N ≈ 60–130; ~111 needed for p < 0.10 |

---

## Methodology

### rNPV

- **Trial costs:** discounted to today at phase midpoint, weighted by P(reaching that phase)
- **Revenue:** EBIT projected year 1 through patent expiry post-launch, weighted by P(approval)
- **rNPV** = P(approval) × PV(EBIT) − Σ[P(reaching phase_i) × PV(cost_i)]
- SG&A ramps 40% → 20% over 5 years post-launch (specialty oncology benchmark)
- WACC default: 12% (configurable per asset)

### POS model

Two-layer approach anchored to Biomedtracker / IQVIA base rates:

**Layer 1 — Base rates (by therapeutic area and phase):**

| Phase | Oncology | All TAs |
|-------|----------|---------|
| Phase 1 | 54% | 64% |
| Phase 2 | 32% | 37% |
| Phase 3 | 55% | 60% |
| NDA/BLA | 83% | 87% |

**Layer 2 — Log-odds adjusters:**

| Factor | Range | Effect |
|--------|-------|--------|
| Endpoint type | −0.55 to +0.35 | Hard clinical vs. novel biomarker |
| MoA precedent | −0.35 to +0.35 | Validated class vs. first-in-class |
| Sample size | −0.50 to +0.20 | Well-powered vs. underpowered |
| Safety profile | −0.80 to +0.10 | Clean vs. serious signals |
| Competition | −0.15 to +0.15 | Low vs. crowded class |
| Biomarker enrichment | +0.40 | Selected population |
| Prior phase data | +0.25 | Consistent earlier-phase signals |
| Breakthrough designation | +0.20 | FDA BTD |

### Monte Carlo

10,000 simulations with correlated draws via Gaussian copula. Phase POS: Beta(α, β)
from analyst mean + equivalent sample size. Peak sales: log-normal. Discount rate:
Normal. Correlation structure configurable (default: peak_sales ↔ penetration = −0.20).

---

## Full CLI Reference

```bash
# Valuation
bve-asset        --config <yaml> --memo bd --charts
bve-batch        --config-dir examples/configs/ --memo bd --charts
bve-portfolio    --config examples/configs/relay_portfolio.yaml

# Product workflows
bve-evaluate-target  --ticker SRPT
bve-morning-screen   --top 15 --output outputs/screen.md
bve-init-asset       --ticker SRPT
bve-validate         --output outputs/validation_report.md

# Intelligence / M&A
bve-ma-probability   --ticker SRPT
bve-universe-screen
bve-morning-screen

# Data
bve-refresh-market-data  --ticker SRPT
bve-refresh-financials   --ticker SRPT
bve-trial-diff           --nct NCT05216432
bve-input-integrity      --ticker SRPT

# Replay / backtest
python -m bve.ops.historical_replay seed --tickers SRPT VKTX ...
python -m bve.ops.historical_replay run  --start 2021-01-01 --end 2026-03-01
python -m bve.ops.historical_replay summary --run-id <id>
```

---

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v          # 11,158 tests
ruff check src/
mypy src/bve/
```

---

## Disclaimer

For informational and research purposes only. Does not constitute investment advice,
a recommendation to buy or sell securities, or a fairness opinion. All projections are
model estimates subject to material uncertainty. Verify inputs against primary sources
before use in any decision context.

Model outputs are only as good as their inputs. Read [`docs/model_limitations.md`](docs/model_limitations.md).
Inspect the assumptions table. Check the trust guide before acting on any number.
