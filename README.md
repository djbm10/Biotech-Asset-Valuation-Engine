# Biotech Asset Valuation Engine (BVE)

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Version](https://img.shields.io/badge/version-0.2.0-green)
![Tests](https://img.shields.io/badge/tests-18%20passing-brightgreen)

A Python toolkit for quantitative valuation of clinical-stage biopharmaceutical assets. Built for BD teams, venture investors, and healthcare-focused funds who need auditable, reproducible outputs — not black-box numbers.

**What it produces in one command:**

```
outputs/RLAY/
  valuation.json       <- machine-readable: rNPV, scenarios, MC, assumptions, run artifact
  bd_memo.md           <- BD acquisition analysis memo (Markdown)
  bd_memo.docx         <- same memo as Word document
  charts/
    RLY-2608_mc_distribution.png
    RLY-2608_tornado.png
    RLY-2608_revenue_curve.png
    RLY-2608_scenario_bars.png
    RLY-2608_catalyst_timeline.png
```

---

## Quickstart

```bash
# 1. Install
conda create -n biotech-env python=3.11 -y && conda activate biotech-env
pip install -e ".[dev]"

# 2. Run the included real-world case (Relay Therapeutics / RLY-2608)
bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts

# 3. Outputs land in outputs/RLAY/
```

---

## Real-World Case Study: Relay Therapeutics (RLAY) / RLY-2608

RLY-2608 is a mutant-selective PI3Ka inhibitor in Phase 2 for HR+/HER2- metastatic breast cancer.
This is the canonical example — a real public company, real trial (NCT05216432), real comps.

**Data sources (all public, cited in the config):**

| Assumption | Value | Source |
|------------|-------|--------|
| Addressable patients | 17,000/yr | SEER + IQVIA; H1047R subgroup derivation |
| Net price/patient/yr | $180,000 | Inavolisib WAC comp ($260K) x (1-30% G2N) |
| Peak penetration | 22% | Alpelisib/inavolisib launch trajectory comps |
| P(Phase 2 success) | 49% | POS model: oncology prior + 6 adjusters |
| P(Phase 3 success) | 76% | POS model: biomarker enrichment + precedent |
| Cash (Q4 2024) | $410M | Relay 10-K 2023 / Q3 2024 earnings |

**Computed outputs (base case):**

```
rNPV                      $129M
P(Approval)                34.6%
Peak Sales                $539M
NAV (incl. $410M cash)    $539M   ($5.76/share vs. $5.80 market -> -1%)

Monte Carlo (10,000 sims):
  P50 median              $38M
  P10 - P90:              -$60M  to  $262M

Scenarios:
  Bull   $858M rNPV  |  $13.56/share
  Base   $129M rNPV  |  $5.76/share
  Bear  -$120M rNPV  |  $3.11/share

Top sensitivity drivers (tornado):
  Phase POS (+-20%)        swing: $268M
  Peak Sales (+-30%)       swing: $185M
  Peak Penetration (+-30%) swing: $185M
  Discount Rate (+-2pp)    swing: $138M
```

Full config with annotated sources: [`examples/configs/relay_rly2608.yaml`](examples/configs/relay_rly2608.yaml)

---

## Case Studies

Three real public companies modeled through different institutional lenses.
Each produces a full memo, 5 charts, and machine-readable `valuation.json`.
All inputs are source-cited; all outputs are reproducible with `--seed 42`.

| Company | Asset | Indication | Memo Type | rNPV | P(Approval) |
|---------|-------|------------|-----------|------|-------------|
| [Relay Therapeutics (RLAY)](case_studies/relay_rly2608/) | RLY-2608 | PIK3CA H1047R HR+/HER2- mBC | BD acquisition | $129M | 34.6% |
| [EyePoint Pharmaceuticals (EYPT)](case_studies/eypt_eyp1901/) | EYP-1901 | Wet AMD (nAMD) | HF mispricing | $235M | 71.9% |
| [Praxis Precision Medicine (PRAX)](case_studies/prax_ulixacaltamide/) | ulixacaltamide | Essential tremor | VC platform | $545M | 44.8% |

See [`case_studies/README.md`](case_studies/README.md) for full methodology, outputs, and reproduce commands.

---

## Architecture

```
Input YAML config
      |
      v
  CLI: bve-asset
      |
      +---> ValuationEngine.run()
              |
              +---> POS Model        (log-odds adjusters on top of Biomedtracker priors)
              +---> rNPV Model       (probability-weighted DCF)
              +---> Scenario Engine  (Bull / Base / Bear)
              +---> Monte Carlo      (10k sims, Gaussian copula correlations)
              +---> Sensitivity      (tornado analysis)
              +---> AssumptionLog    (every key number traced to a source)
              |
              v
         ValuationOutput
              |
              +---> valuation.json   (full run artifact: inputs + outputs + assumptions + meta)
              +---> BD / VC / HF memo (Jinja2 -> Markdown -> docx)
              +---> 5 matplotlib charts
```

**Package layout:**

```
src/bve/
  config/        constants.py (phase transition priors), settings.yaml
  entities/      Asset, Company, ClinicalTrial, Indication
  models/        pos_model.py, rnpv_model.py, monte_carlo.py, market_model.py, correlations.py
  valuation/     valuation_engine.py, scenario.py, outputs.py, assumptions.py
  ingestion/     clinicaltrials_gov.py, market_data.py, sec_edgar.py, fda.py
  reporting/     memo_generator.py, charts.py, export.py, templates/{bd,vc,hf}_memo.md.j2
  cli/           run_asset.py, run_batch.py
examples/
  configs/       relay_rly2608.yaml   <- real-world case (RLAY / RLY-2608)
                 xyz101.yaml          <- synthetic scaffold for testing
tests/
  test_models.py                      <- 18 tests, all passing
```

---

## Methodology

### rNPV

Risk-adjusted NPV: probability-weighted discounted cash flow.

- **Trial costs**: discounted to today at phase midpoint, weighted by P(reaching that phase)
- **Revenue**: EBIT projected year 1 through patent expiry post-launch, weighted by P(approval)
- **rNPV** = P(approval) x PV(EBIT) - sum[P(reaching phase_i) x PV(cost_i)]
- SG&A ramps 40% -> 20% over first 5 years post-launch (specialty oncology benchmark)
- WACC default: 10% (Damodaran biotech sector; configurable per asset)

### Probability of Success (POS) Model

Two-layer approach anchored to published industry data:

**Layer 1 - Base rates** (Biomedtracker/IQVIA 2021, Thomas et al. 2016):

| Phase | Oncology | All TAs |
|-------|----------|---------|
| Phase 1 | 54% | 64% |
| Phase 2 | 32% | 37% |
| Phase 3 | 55% | 60% |
| NDA/BLA | 83% | 87% |

**Layer 2 - Log-odds adjusters** (applied on top of base rate):

| Factor | Range (log-odds) | Effect |
|--------|-----------------|--------|
| Endpoint type | -0.55 to +0.35 | Hard clinical (OS) vs. novel biomarker |
| MoA precedent | -0.35 to +0.35 | Validated class vs. first-in-class |
| Sample size adequacy | -0.50 to +0.20 | Well-powered vs. underpowered |
| Safety profile | -0.80 to +0.10 | Clean vs. serious signals |
| Competitive pressure | -0.15 to +0.15 | Low-competition vs. crowded class |
| Biomarker enrichment | +0.40 | Biomarker-selected population |
| Strong prior phase data | +0.25 | Consistent earlier-phase signals |
| Breakthrough designation | +0.20 | FDA BTD (correlates with faster review) |

Log-odds space ensures adjusters are additive and results stay in (0, 1).
Each adjuster shifts P by approximately +/-10-25pp around the base rate.

### Monte Carlo

10,000 simulations with correlated draws via Gaussian copula:

- **Phase POS**: Beta(alpha, beta) parameterized from analyst mean + equivalent sample size
- **Peak sales**: log-normal with configurable CV (default 35%)
- **Discount rate**: Normal(mu, sigma=2pp)
- **Years to peak**: Normal(mu, sigma=1.5 yrs)
- **Correlation structure**: peak_sales <-> penetration (rho = -0.20); configurable

### Scenario Analysis

Bull / Base / Bear applied as multiplicative shocks:

| Parameter | Bear | Base | Bull |
|-----------|------|------|------|
| Peak sales multiplier | 0.55x | 1.0x | 1.5x |
| POS multiplier | 0.70x | 1.0x | 1.3x |
| Duration delta | +1.0 yr | 0 | -0.5 yr |
| WACC delta | +2pp | 0 | -1pp |

---

## Data Provenance

Every key assumption carries a source. The YAML config is the primary provenance document:

```yaml
market_model:
  # Addressable population derivation:
  #   US HR+/HER2- mBC incident cases: ~35,000/year
  #   PIK3CA-mutant: ~40% = ~100,000 prevalent
  #   H1047R subgroup: ~40% of PIK3CA-mutant = ~40,000 prevalent
  #   2nd/3rd-line eligible: ~50% = ~20,000
  #   Diagnosed/tested (ctDNA): ~85% -> addressable: ~17,000
  addressable_patients_annual: 17000   # see derivation above

  # Net price derivation:
  #   Comp: Inavolisib WAC ~$300K/year
  #   RLY-2608: slight 2nd-in-class discount -> $260K WAC
  #   G2N: 30% for specialty oncology -> $260K x 0.70 = $182K
  net_price_per_patient_usd: 180000    # see derivation above
```

The `valuation.json` output includes a full `assumptions` block tracing every modeled number
to its source, with sensitivity ratings (High / Medium / Low).

The `meta` block records the complete run artifact — enough to reproduce any output exactly:

```json
{
  "meta": {
    "analysis_date": "2026-03-04",
    "run_timestamp": "2026-03-04T21:12:00",
    "git_commit": "521b871",
    "random_seed": 42,
    "n_simulations": 10000,
    "bve_version": "0.2.0",
    "python_version": "3.11.x",
    "config_path": "examples/configs/relay_rly2608.yaml"
  }
}
```

---

## Assumptions and Limitations Philosophy

Institutional-grade outputs are not "more precise" — they're more honest about uncertainty.

Every memo includes:

- **Appendix A: Key Assumptions** — every material number with source and sensitivity rating
- **Appendix B: What Would Change This Thesis** — explicit kill criteria and re-rating triggers
- **Appendix C: Limitations** — what the model does NOT capture (by design)
- **Appendix D: Methodology** — enough detail to reconstruct the model independently

**Hard limits of this model (always explicit in outputs):**

1. **US-only**: Ex-US revenues not modeled. Global upside is typically 35-50% of US value.
2. **Single-asset**: Company-level portfolio NAV requires running multiple configs.
3. **Static competition**: Market share modeled as a fixed penetration ceiling; no dynamic erosion.
4. **No tax model**: NOL carryforwards, R&D credits, and operating leverage excluded.
5. **Binary approval outcome**: Partial labels, accelerated approval + confirmatory, and label
   expansion scenarios require explicit configuration.
6. **Point-in-time**: Config snapshots data at a fixed date. Re-run after material updates.

---

## CLI Reference

```bash
# Single asset — BD memo + charts
bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts

# All three memo types (BD, VC, HF) simultaneously
bve-asset --config examples/configs/relay_rly2608.yaml --all-memos --charts

# Custom output directory, reproducible seed, custom sim count
bve-asset --config examples/configs/relay_rly2608.yaml \
          --memo bd --charts \
          --out /path/to/outputs \
          --seed 42 \
          --n-sims 50000

# Batch (multiple assets from a directory of configs)
bve-batch --config-dir examples/configs/ --memo bd --charts
```

**Memo types:**

| Flag | Audience | Focus |
|------|----------|-------|
| `--memo bd` | BD/licensing teams | Deal structure, strategic fit, milestone frameworks |
| `--memo vc` | Venture / growth equity | Milestone-to-value, runway, portfolio fit |
| `--memo hf` | Hedge funds | Catalyst timeline, variant perception, event-driven framing |

---

## Writing a New Asset Config

Copy and annotate `examples/configs/relay_rly2608.yaml`. Minimal required sections:

```yaml
asset:
  id: "asset-id"
  name: "Asset Name"
  indication: "Indication (line, geography)"
  therapeutic_area: "oncology"        # oncology | rare_disease | cns | cardiovascular | immunology | other
  stage: "phase_2"                    # phase_1 | phase_2 | phase_3 | nda_bla
  modality: "small_molecule"          # small_molecule | biologic | cell_gene | adc | other
  discount_rate: 0.10
  royalty_rate: 0.0                   # royalty paid out; net_ownership = 1 - royalty_rate

company:
  id: "company-id"
  name: "Company Name"
  ticker: "TICK"
  cash_millions: 400.0
  shares_outstanding_millions: 100.0
  burn_rate_millions_per_quarter: 30.0
  current_price: 10.00

trials:
  - phase: "phase_2"
    nct_id: "NCT00000000"            # or null if not yet registered
    success_probability: 0.40        # used if apply_pos_model: false
    duration_years: 2.0
    cost_millions: 80.0
    enrollment: 120
    primary_endpoint: "ORR >= 40%"
    endpoint_type: "surrogate_validated"

market_model:
  addressable_patients_annual: 20000
  net_price_per_patient_usd: 150000
  peak_penetration: 0.20
  years_to_peak: 5
  patent_life_years: 12

pos_adjusters:
  apply_pos_model: true              # false to use trial.success_probability directly
  phase_2:
    endpoint_type: "surrogate_validated"
    moa_precedent: "validated"       # validated | partial | novel
    sample_size_adequacy: "adequate" # well_powered | adequate | borderline | underpowered
    safety_profile: "clean"          # clean | minor | concerning | serious
    competitive_pressure: "moderate" # low | moderate | high
    biomarker_selected_population: true
    strong_prior_phase_data: false

# Optional: override default limitations and thesis-changers in the memo
limitations:
  - "US market only. Ex-US not modeled."
thesis_changers:
  - "Phase 2 ORR >= 50% -> strong bull case."
```

---

## Running Tests

```bash
python -m pytest tests/ -v
# 18 tests, all passing
```

Tests cover: rNPV model, POS log-odds arithmetic, Monte Carlo output statistics,
scenario engine shocks, assumption log construction, and JSON serialization.

---

## Development Setup

```bash
pip install -e ".[dev]"
ruff check src/
mypy src/bve/
```

---

## Ingestion Modules (optional)

| Module | What it fetches | Notes |
|--------|----------------|-------|
| `ingestion/clinicaltrials_gov.py` | Trial details by NCT ID | ClinicalTrials.gov v2 API; no key required |
| `ingestion/market_data.py` | Price history, returns, fundamentals | yfinance |
| `ingestion/sec_edgar.py` | Cash, R&D expense, shares outstanding | SEC EDGAR; no key required |
| `ingestion/fda.py` | Approval history, designations | openFDA API |

These are standalone helpers for populating or validating config values.
The valuation engine does not require them — the YAML config is the source of truth.

---

## Disclaimer

For informational and research purposes only. Does not constitute investment advice,
a recommendation to buy or sell securities, or a fairness opinion. All projections are
model estimates subject to material uncertainty. Verify inputs against primary sources
before use in any decision context.

Model outputs are only as good as their inputs. Read the limitations. Inspect the
assumptions table. The most important section of any BVE memo is Appendix C.
