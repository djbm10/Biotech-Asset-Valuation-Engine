# Roadmap to Institutional Grade

**Status:** Phase 0 complete — platform reframe done
**Engine baseline:** Sprint 30 complete — rNPV, MC, competition model, multi-indication, LOE, deal
economics, POS backtest, historical replay, weekly runner, M&A backfiller (15 acquirers, 38-date replay)
**Primary goal:** Evolve from research/triage system → institutional underwriting + validation platform
→ shadow book with risk controls → small real-capital decision engine

---

## Master Roadmap (Phases 0–9)

| Phase | Name | Timeline | Status |
|-------|------|----------|--------|
| 0 | Reframe the system correctly | 1 week | **Complete** |
| 1 | Build company truth | 4–8 weeks | Not started |
| 2 | Institutional provenance and governance | 2–4 weeks | Not started |
| 3 | Lock point-in-time validation | 4–6 weeks | Not started |
| 4 | Replace score thresholds with EV-to-size | 3–5 weeks | Not started |
| 5 | Reconciliation and drift monitoring | 2–4 weeks | Not started |
| 6 | Upgrade commercial realism (gold tier) | 6–10 weeks | Not started |
| 7 | Demote and rebuild M&A layer | 3–6 weeks | Not started |
| 8 | Shadow book like a real fund | 8–12 weeks | Not started |
| 9 | Build actual alpha layers | Ongoing | Not started |

### Non-negotiable principles
- **Company is the decision object.** Not asset-only. Company-level underwriting is the core gap.
- **Point-in-time truth only.** Every decision must be reproducible from what the system knew at that date.
- **Separate ranking, calibration, and sizing.** Blending them fools you.
- **Screening and capital deployment are different products.** Most names stay screening-grade.
- **No threshold-score fake precision.** Move from rank-to-action to EV-to-size.
- **Human review mandatory for serious names.** Models do not deploy large capital without expert challenge.

### End-state architecture layers
1. Data / provenance layer
2. Company snapshot layer
3. Valuation layer
4. Calibration / uncertainty layer
5. Portfolio / risk / sizing layer
6. Review workflow layer
7. Backtest / replay / monitoring layer
8. Alpha-data layer

---

## Phase 0 — Reframe the system correctly ✓

**Timeline:** 1 week | **Completed:** 2026-04-09

**Deliverables:**
- `docs/PRODUCT_SPEC.md` — written product spec with 3 modes (Screening, Capital-candidate, Shadow-book),
  mode definitions, allowed action types, governance table
- Mode labels on all top-level CLI outputs
- Screening-grade gate in action layer: `screening_grade: true` configs blocked from buy/size actions

**Exit criteria met:**
- No code path pushes a screening-grade name into buy/size outputs ✓
- Every top-level report labels the mode clearly ✓

---

## Phase 1 — Build company truth (next)

**Timeline:** 4–8 weeks | **Status:** Not started

**The audit says this is the highest-leverage phase.**

Goal: make `CompanySnapshot` the canonical unit of analysis. The current system models assets, not
companies. This is the root gap the audit identified.

### 1A — Canonical CompanySnapshot schema

Fields: company_id, as_of_date, share price/market cap/EV, cash, debt, royalty streams/obligations,
modeled assets, platform value, unmodeled pipeline bucket, dilution/financing path, major catalysts,
management/governance flags, confidence metadata, provenance metadata, reviewer state, stale state.

### 1B — Material bucket framework

Every value bucket gets: value, methodology, source type, source reference, as-of date,
corroboration count, reviewer, confidence, last changed timestamp, change reason.

### 1C — Top-25 underwriting packs

Pick 25 names. For each: quarterly pack, event-dated updates, two-source corroboration on all
material manual buckets, dilution bridge, platform/unmodeled pipeline bridge, discrepancy notes.

**What to cut during Phase 1:**
- No expanding broad-universe heuristics before this is done
- No more fancy action logic on incomplete company models

**Exit criteria:**
- Top-25 names have full company packs
- Every top name can answer: "why is company value different from market EV?"
- Every material assumption is dated and attributable

---

## Historical sprint record (pre-Phase 0)

**Primary goal:** Convert the engine from a valuation calculator into a mispricing detector.

---

## What the engine can and cannot do today

**Can do (production-quality):**
- Full rNPV for a single drug program given a hand-written YAML config
- Monte Carlo with correlated draws (Gaussian copula, 10k simulations)
- Competition model (crowding, first-mover, class saturation)
- Deal economics (milestones, royalty stacking, cost sharing)
- LOE erosion by modality
- Weekly operational runner across 27 tracked names
- Historical replay with no-lookahead bias guarantee

**Cannot do (blocked without this roadmap):**
- Screen the universe *without* hand-writing a YAML per ticker (current: 3 configs exist, 24 gaps)
- Translate rNPV into a daily "what is the market mispricing" signal
- Detect events in near-real-time (current: daily at best, manually checked)
- Systematically match acquirer pipeline gaps against universe names
- Validate POS model predictions against outcomes (dataset too small, biased)

---

## Phase 1 — Must fix (4–6 weeks)

### Core thesis: the implied PoS spread is the primary signal

The engine already computes implied PoS correctly (`analysis/implied_probability.py`, formula:
`implied_pos = (EV + PV_costs) / PV_EBIT`). What it lacks is the infrastructure to run this
across all 27 universe names automatically and surface it as the daily output.

---

### Sprint 10 — Market-implied PoS at universe scale (2 weeks)

#### Architecture decision: parametric configs

The 27 UNIVERSE entries have ticker, indication, and catalyst but no full YAML config. Hand-writing
27 configs takes weeks and goes stale. Instead:

- Build `ops/universe_configs.py`: a parametric DrugAssetProgram generator that reads a UNIVERSE entry
  plus a thin config layer (`research/universe_params.yaml`) and assembles a `DrugAssetProgram` using
  industry defaults. This produces "screening-grade" valuations — accurate enough for the spread signal,
  not accurate enough for a BD memo.
- The full YAML configs (relay_rly2608.yaml, etc.) remain the "portfolio-grade" path for names where
  precision matters.

#### Task 10.1 — `research/universe_params.yaml`
New file. Per-ticker overrides on top of industry defaults:
```yaml
VKTX:
  ta: metabolic
  phase: 2
  peak_sales_millions: 3200        # VK2735 obesity, consensus est
  years_to_approval: 4.5
  patent_life_years: 12
  program_label: "VK2735 obesity"
  single_asset: true               # single-asset simplification valid
ALNY:
  ta: rare_disease
  phase: 3
  peak_sales_millions: 4800
  years_to_approval: 2.5
  patent_life_years: 12
  program_label: "zilebesiran KARDIA-2"
  single_asset: false              # multi-program → implied PoS flagged as approximate
# ... all 27 names
```

Minimum fields per name: `ta`, `phase`, `peak_sales_millions`, `years_to_approval`, `patent_life_years`,
`program_label`, `single_asset`. Everything else falls back to `industry_assumptions.yaml` defaults.

`single_asset: false` doesn't disable the calculation — it adds an `approximation_warning` to the
output, since EV for multi-program companies (VRTX, LLY, REGN) includes multiple pipeline programs and
the single-program implied PoS will be meaninglessly high.

#### Task 10.2 — `ops/universe_configs.py`
```python
def build_program_from_params(ticker: str, params: dict, company: Company) -> DrugAssetProgram:
    """
    Assemble a screening-grade DrugAssetProgram from universe_params.yaml entry.
    Uses AssumptionsLoader for base rates; params override peak_sales, timing, TA.
    """
```

Key choices:
- `Asset`: `id=f"a-{ticker.lower()}"`, `modality` defaults to `"small_molecule"` unless overridden
- `MarketModel`: TAM mode using `peak_sales_millions` + `peak_penetration=0.25` (industry default)
- Trials: single trial per phase from `phase` field up through Phase 3, using TA base rates
- `CommercialPlan.no_loe()` for now (keeps screening consistent; LOE addable per-name later)
- `DealEconomics` defaults (no deal = 100% ownership)

#### Task 10.3 — `analysis/implied_pos_batch.py`
```python
@dataclass
class ScreenRow:
    ticker: str
    program_label: str
    model_pos: float
    implied_pos: Optional[float]    # None if gross_pv <= 0 or company.current_price missing
    spread_pp: Optional[float]      # model_pos - implied_pos, in percentage points
    rnpv_millions: float
    ev_millions: float
    acquisition_discount_pct: float
    next_catalyst: str
    days_to_catalyst: Optional[int]
    clinical_stage: str
    single_asset: bool              # flags approximation validity
    approximation_warning: Optional[str]
    data_date: date

def run_implied_pos_batch(
    universe: list[dict],         # from weekly_runner.UNIVERSE
    params_path: Path,            # universe_params.yaml
    market_data_fetcher,          # callable(ticker) -> (price, shares, net_cash)
    as_of: Optional[date] = None,
) -> list[ScreenRow]:
```

Market data fetcher: wraps existing `ingestion/market_data.py` — `get_fundamentals(ticker)` already
returns cash; add `fetch_price_history()` for current price and shares.

EV computation: `EV = (current_price × shares_outstanding) - net_cash`. For multi-program companies,
document the decomposition limitation explicitly.

#### Task 10.4 — Wire into weekly runner

Add `ScreenRow` persistence to `KnowledgeStore` (new table: `screen_snapshots`). Weekly runner
`report` command prints the spread table and persists rows for time-series tracking.

#### Acceptance criteria
- `bve-screen` (Sprint 11) outputs a row for all 27 universe names
- Implied PoS matches `compute_implied_market_assumptions()` result when run against same output
- Multi-program names flagged with `approximation_warning`
- `test_implied_pos_batch.py`: 20+ tests covering formula, multi-program flag, missing-price handling

---

### Sprint 11 — Unified screener CLI (1 week)

#### Task 11.1 — `cli/screener.py`
Entry point: `bve-screen`. Add to `pyproject.toml`:
```toml
[project.scripts]
bve-screen = "bve.cli.screener:main"
```

Output columns (fixed-width table via `tabulate` or `rich`):
```
TICKER  STAGE  MODEL_POS  IMPLIED_POS  SPREAD    rNPV     EV      ACQ_DISC  NEXT_CATALYST       D2CAT
VKTX    Ph2      68.4%       41.2%    +27.2pp   $1,840M  $2,100M  -12%      VK2735 oral Ph2      23
ALNY    Ph3      74.1%       58.3%    +15.8pp   $4,920M  $6,200M   -8%      KARDIA-2 readout     41
...
```

Columns:
- `TICKER`, `STAGE` — from UNIVERSE
- `MODEL_POS` — `cumulative_success_probability` from engine
- `IMPLIED_POS` — from `implied_pos_batch`
- `SPREAD` — primary signal: `model_pos - implied_pos` in pp, colored green (positive) / red (negative)
- `rNPV` — raw model rNPV
- `EV` — live EV from yfinance
- `ACQ_DISC` — `(rnpv - ev) / ev × 100` (existing acquisition_discount metric kept as secondary)
- `NEXT_CATALYST` — from UNIVERSE
- `D2CAT` — days to catalyst (parsed from UNIVERSE catalyst string or manual field in universe_params.yaml)

Sort default: `SPREAD` descending (biggest mispricing first).

Flags:
- `--sort [spread|rnpv|ev|d2cat]`
- `--min-spread N` — filter to spread ≥ N pp
- `--stage [ph1|ph2|ph3|nda]`
- `--json` — machine-readable output for downstream scripts
- `--as-of YYYY-MM-DD` — use archived screen_snapshot from KnowledgeStore

#### Task 11.2 — `days_to_catalyst` parser
Add `catalyst_date: Optional[date]` field to `universe_params.yaml`. Parser: if explicit date, use it;
else `days_to_catalyst = None`. Over time, populate as catalysts are confirmed.

#### Acceptance criteria
- `bve-screen` runs end-to-end without errors on the full 27-name universe
- `--json` output is parseable by `implied_pos_batch.ScreenRow`
- Rendering works in 80-column and 120-column terminals

---

### Sprint 12 — Rules-based universe + survivorship bias fix (2 weeks)

#### Problem statement

The current 27-name UNIVERSE is manually curated — selection bias by construction. The historical
replay backtest (Sprint 9) ran on these same names, so hit rate reflects curator skill, not model skill.
Separately, the POS backtest dataset (40 programs) has 82.5% actual success — unusable for Brier score.

#### Track A: POS backtest dataset fix (1 week, mostly manual research)

Target: add 20–40 Phase 2/3 failures to `research/data/oncology_phase_transitions.csv`.
Target distribution: ~40% Phase 2 success, ~60% Phase 3 success (realistic industry rates).

Sources for failures:
- BioMedTracker discontinued programs database (public summary available)
- FDA CRL database (FDA.gov/drugs, CRL letters)
- Known high-profile failures: Aduhelm controversy, CRISPR off-target failures, NASH trial failures,
  Alzheimer programs 2018–2023

Data schema additions needed for failures:
```csv
program_id,phase,ta,primary_endpoint,success,actual_outcome,discontinued_reason,year
oncology_fail_001,2,oncology,OS,0,discontinued,futility_interim,2021
```

After adding failures: re-run `python -m bve.analysis.backtest research/data/oncology_phase_transitions.csv`.
Target: Brier score < 0.22, AUC > 0.60.

**This is the single most important data task.** Until failures are added, no calibration metric is
interpretable.

#### Track B: Rules-based universe builder (1 week, engineering)

New file: `ops/universe_builder.py`

```python
@dataclass
class UniverseFilter:
    min_mktcap_m: float = 200
    max_mktcap_m: float = 10_000
    min_adv_m: float = 2.0          # average daily volume in $M
    min_phase: int = 2              # at least one Phase 2+ asset

@dataclass
class UniverseCandidate:
    ticker: str
    company_name: str
    market_cap_m: float
    adv_m: float
    as_of: date
    sources: list[str]

def build_universe(as_of: date, filter: UniverseFilter) -> list[UniverseCandidate]:
    """
    Screen XBI + IBB constituent lists against filter criteria.
    Starting point: ETF constituents as biotech proxy universe (~200 names),
    then filter by mktcap, ADV, and clinical stage.

    Clinical stage filter: use ClinicalTrials.gov API to check for active
    Phase 2+ studies per company.
    """
```

Implementation approach:
1. Download XBI + IBB constituent tickers (from ETF holdings pages, quarterly snapshots available)
2. For each ticker: pull mktcap, ADV from yfinance
3. For each passing ticker: query ClinicalTrials.gov for active Phase 2+ trials
4. Persist result to SQLite table `universe_snapshots(date, ticker, mktcap_m, adv_m, phase, passed)`

Historical reconstruction (2024-01-01 → present):
- Use quarterly price snapshots for historical mktcap/ADV
- ClinicalTrials.gov data is mostly point-in-time; use current data for historical approximation
  (known limitation: companies that failed will have fewer trials now than they did historically)

**Constraint:** True historical universe reconstruction requires a paid biotech data provider (Evaluate
Pharma, FactSet, IQVIA). The free approach has look-ahead bias in the clinical stage filter (we're
querying today's trial status for historical periods). Document this explicitly. The rules-based mktcap
and ADV filters are clean; only the Phase 2+ gate is contaminated.

Backtest rerun:
- Extend replay seed to 2024-01-01 for all rules-based universe names
- Target: N ≥ 20 resolved decisions for meaningful hit-rate statistics

---

## Phase 2 — Differentiation / edge (2–3 months)

### Sprint 13 — Acquirer pipeline gap analysis (3 weeks)

#### Why this matters

No public tool does systematic cross-company pipeline gap matching. This is the most defensible
proprietary capability because it combines public pipeline data (which anyone can get) with a scoring
function (which embeds domain judgment). The output — "VKTX scores 0.82 on Pfizer's gap list" — is a
claim that requires both data and interpretation to make.

#### Architecture

New directory: `intelligence/strategic_fit/`

**`intelligence/strategic_fit/acquirer_profiles.yaml`** — manually curated, semi-annual update cycle:
```yaml
pfizer:
  name: "Pfizer"
  TA_priorities:
    - oncology_solid_tumor    # weight: 1.0 (highest gap)
    - rare_disease            # weight: 0.85
    - inflammation            # weight: 0.70
    - metabolic               # weight: 0.60
  stage_preference:
    min_phase: 2
    preferred_phase: 3
    weight_by_stage:
      phase_2: 0.70
      phase_3: 1.00
      nda: 0.90              # discount for NDA (less upside)
  mechanism_gaps:
    - "KRAS G12D"            # Pfizer has G12C (adagrasib), gaps G12D
    - "antibody-drug conjugate"
    - "mRNA platform"
  deal_size_range_m: [3000, 50000]
  recent_deals:
    - {target: "Seagen", year: 2023, value_b: 43, rationale: "ADC platform"}
    - {target: "Arena", year: 2022, value_b: 6.7, rationale: "inflammation"}
  avoid:
    - "gene therapy"          # Pfizer wrote off gene therapy after hemophilia issues

lilly:
  # ... similar structure
  TA_priorities:
    - metabolic               # GLP-1 adjacencies, diabetes, obesity
    - neurodegeneration
    - immunology
  mechanism_gaps:
    - "oral GLP-1"            # Lilly has tirzepatide; gaps oral small molecule class
    - "NASH non-GLP-1"

novo_nordisk:
  TA_priorities:
    - metabolic
    - rare_blood_disease
    - cardiovascular
  deal_size_range_m: [1000, 20000]
```

**`intelligence/strategic_fit/strategic_fit.py`**:
```python
@dataclass
class StrategicFitScore:
    ticker: str
    acquirer: str
    ta_match_score: float           # 0-1: TA priority match
    stage_score: float              # 0-1: stage preference match
    mechanism_novelty_score: float  # 0-1: fills a mechanism gap
    commercial_fit_score: float     # 0-1: deal size in range × market overlap
    avoid_penalty: float            # 0-1: penalty if asset in acquirer's avoid list
    total: float                    # weighted sum
    rationale: list[str]            # human-readable explanation strings

def score_fit(
    asset_profile: dict,            # from universe_params.yaml per ticker
    acquirer_profile: dict,         # from acquirer_profiles.yaml
) -> StrategicFitScore:
```

Scoring weights (Phase 2 defaults, calibrate later):
- `ta_match × 0.35 + stage × 0.20 + mechanism_novelty × 0.30 + commercial × 0.15`
- `avoid_penalty` reduces total by 0.40 if triggered

Output: the `bve-screen` table gains a `FIT` column showing the max score across all 3 acquirers,
plus `BEST_FIT_FOR` showing which acquirer. A `bve-screen --mna` flag shows the full per-acquirer
breakdown.

#### Acceptance criteria
- 3 acquirer profiles curated (Pfizer, Lilly, Novo)
- `score_fit()` produces deterministic, interpretable scores
- `bve-screen --mna` table outputs without errors for all 27 names
- `test_strategic_fit.py`: 25+ tests covering scoring, edge cases, zero-gap acquirer

---

### Sprint 14 — Commercial model layer (2 weeks)

#### Problem statement

Current `MarketModel` uses single-point peak sales. In an MC context, peak sales is already sampled
from a log-normal distribution — but the *inputs* (population, share, price) are hidden inside that
single number. This makes the model unjustifiable to a sophisticated audience who will ask "how did
you get $3.2B peak sales?" The answer should be: "180k addressable patients × 35% peak share × $55k
net price."

#### Architecture

New file: `models/commercial_inputs.py`:
```python
class PatientPool(BaseModel, frozen=True):
    indication: str
    prevalence_thousands: float           # diagnosed prevalent population in thousands
    diagnosed_fraction: float = 1.0       # fraction currently diagnosed
    treated_fraction: float = 1.0         # fraction of diagnosed receiving treatment
    addressable_k: Optional[float] = None # override if prevalence chain not used
    annual_incidence_k: Optional[float] = None
    uncertainty_cv: float = 0.25          # coefficient of variation for MC

class PricingModel(BaseModel, frozen=True):
    net_price_usd: float                  # net price per patient per year
    launch_discount: float = 0.10         # rebates/discounts at launch
    annual_erosion_rate: float = 0.02     # price erosion per year post-launch
    uncertainty_cv: float = 0.15

class ShareModel(BaseModel, frozen=True):
    peak_share: float                     # peak penetration of addressable market
    years_to_peak: int = 5
    share_cv: float = 0.20               # coefficient of variation

class CommercialInputs(BaseModel, frozen=True):
    patient_pool: PatientPool
    pricing: PricingModel
    share: ShareModel

    def to_peak_sales_millions(self) -> float:
        """Point estimate: addressable × peak_share × net_price × (1 - discount)."""

    def sample_peak_sales(self, rng: np.random.Generator) -> float:
        """MC draw: propagate uncertainty through population × share × price."""
```

`MarketModel` extension: add `commercial_inputs: Optional[CommercialInputs] = None`. When set:
- `peak_sales_millions` is derived from `commercial_inputs.to_peak_sales_millions()`
- MC samples via `commercial_inputs.sample_peak_sales(rng)` instead of the current log-normal

This is backward-compatible: existing configs without `commercial_inputs` continue to use direct
`total_addressable_market_millions` or `addressable_patients_annual` fields.

YAML config addition:
```yaml
market_model:
  commercial_inputs:
    patient_pool:
      indication: "obesity"
      prevalence_thousands: 120000
      diagnosed_fraction: 0.40
      treated_fraction: 0.20
      uncertainty_cv: 0.30
    pricing:
      net_price_usd: 14000
      launch_discount: 0.15
      annual_erosion_rate: 0.025
    share:
      peak_share: 0.08
      years_to_peak: 5
```

#### Acceptance criteria
- `relay_rly2608.yaml` updated with `commercial_inputs` block
- MC output is measurably wider (CV of peak sales increases when propagating population uncertainty)
- `test_commercial_inputs.py`: 25+ tests covering to_peak_sales, sample_peak_sales, backward compat

---

### Sprint 15 — Real-time event monitoring (2 weeks)

#### Task 15.1 — `ops/event_monitor.py`

Two polling sources, 15-minute cadence:

**FDA events** (via OpenFDA API — free, rate-limited):
```python
def poll_fda_events(universe_tickers: list[str]) -> list[DetectedEvent]:
    """
    Queries:
    - /drug/drugsfda.json: recent approval/CRL actions
    - /drug/event.json: serious adverse events (safety signals)
    Filter: application numbers linked to universe companies (needs IND→ticker mapping table).
    """
```

**SEC EDGAR 8-K** (via EDGAR full-text search):
```python
def poll_edgar_8k(universe_tickers: list[str]) -> list[DetectedEvent]:
    """
    Queries EDGAR full-text search for 8-K filings from universe companies in last 24h.
    Filters for keywords: "clinical trial", "phase 3", "primary endpoint", "FDA", "approval".
    """
```

`DetectedEvent`:
```python
@dataclass
class DetectedEvent:
    ticker: str
    asset_id: str
    event_type: str          # "fda_approval", "fda_crl", "8k_clinical", "8k_partnership"
    headline: str
    source_url: str
    detected_at: datetime
    requires_recompute: bool
```

Persistence: insert into `KnowledgeStore` via `insert_event()`. Deduplication by `(ticker, headline[:80], date)`.

#### Task 15.2 — `ops/recompute_trigger.py`

```python
def check_and_trigger(store: KnowledgeStore, as_of: date) -> list[str]:
    """
    Returns tickers that have new material events since last_screen_date.
    Caller decides whether to recompute immediately or batch nightly.
    """
```

Integration: `weekly_runner report` checks for pending triggers before generating report.

#### Task 15.3 — Scheduler

Simple: cron job or `ops/monitor_daemon.py` with `time.sleep(900)` loop.
For now: document the manual invocation. Full daemon is a Phase 3 hardening item.

---

## Phase 3 — Long-term moat (6–12 months)

### Sprint 16 — Calibration database

#### Architecture

Extend `KnowledgeStore` schema with two new tables:

```sql
-- One row per prediction made, at time of prediction
CREATE TABLE pos_predictions (
    id INTEGER PRIMARY KEY,
    program_id TEXT NOT NULL,
    ticker TEXT,
    ta TEXT,
    phase TEXT,
    model_pos REAL,
    implied_pos REAL,
    spread_pp REAL,
    peak_sales_millions REAL,
    rnpv_millions REAL,
    predicted_at DATE,
    trial_end_expected DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- One row per resolved outcome
CREATE TABLE pos_outcomes (
    id INTEGER PRIMARY KEY,
    program_id TEXT NOT NULL,
    outcome DATE,
    outcome_type TEXT CHECK(outcome_type IN (
        'approval', 'crl', 'failure_efficacy', 'failure_safety',
        'partial_approval', 'discontinued', 'ongoing'
    )),
    trial_name TEXT,
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

`analysis/calibration_metrics.py`:
```python
def compute_calibration(
    predictions: list[PredictionRecord],
    outcomes: list[OutcomeRecord],
    min_n: int = 20,
) -> CalibrationReport:
    """
    Brier score, AUC-ROC, reliability diagram (5 buckets).
    Requires min_n matched pairs. Returns None if insufficient data.
    """
```

Calibration buckets: `[0–20%, 20–40%, 40–60%, 60–80%, 80–100%]`.
Target after 500+ predictions: ECE < 0.08, AUC > 0.65.

Key discipline: **only save predictions at the time they are made.** Never backfill. The calibration
database is worthless if predictions are retroactively adjusted. The `predicted_at` field enforces this.

---

### Sprint 17 — Indication-specific PoS models (requires 500+ calibrated predictions)

Replace `PHASE_SUCCESS_RATES[ta][phase]` in `industry_assumptions.yaml` with Bayesian posterior means
from the calibration database.

Architecture: `models/pos_calibrated.py`:
```python
class CalibratedPOSModel:
    """
    Hierarchical Bayesian model: pooling across TAs, with TA-specific shrinkage.
    Posterior mean replaces the industry prior after N >= 50 outcomes per (ta, phase) bin.
    Below N=50: blended (fraction calibrated × posterior + (1 - fraction) × industry prior).
    """
    def base_rate(self, ta: str, phase: str) -> float: ...
    def confidence_interval(self, ta: str, phase: str) -> tuple[float, float]: ...
```

Trigger: automatically rebuild model monthly via `bve-recalibrate` CLI command.

---

### Sprint 18 — Expert network integration layer

Structured note entry:
```bash
bve-note --ticker VKTX \
         --type physician_call \
         --date 2026-04-15 \
         --content "Prescriber at UPMC: seeing 12% weight loss at 24 weeks in obese patients without diabetes. Tolerability better than Ozempic. Considering switching existing semaglutide patients." \
         --confidence 0.70
```

`intelligence/expert_notes.py`:
- Stores note + metadata in `KnowledgeStore`
- Extracts structured signals: asset name mentions, efficacy signals, safety signals, commercial signals
- Converts to `ThesisClaim` with source_type="expert_note"

Signal extraction: keyword-based rules initially (no LLM needed for MVP). Patterns:
- `r"(\d+)%\s+(weight loss|HbA1c|EASI|TTP)"` → efficacy signal
- `r"(well tolerated|discontinuation|adverse)"` → safety signal
- `r"(switching|prescribing|formulary)"` → commercial signal

---

## Implementation sequencing

```
Week 1-2:  Sprint 10 — universe_params.yaml + parametric config builder + implied PoS batch
Week 3:    Sprint 11 — bve-screen CLI
Week 4-5:  Sprint 12 Track A (POS dataset failures, manual research) +
           Sprint 12 Track B (universe_builder.py, in parallel)
Month 2:   Sprint 13 — acquirer profiles + strategic fit scoring
Month 2-3: Sprint 14 — commercial inputs layer
Month 3:   Sprint 15 — event monitoring
Month 4+:  Calibration database, ongoing prediction tracking
Month 6+:  Enough predictions to start calibration analysis
Month 9+:  Indication-specific models if calibration data sufficient
```

## Risk register

| Risk | Impact | Mitigation |
|------|--------|------------|
| universe_params.yaml requires peak_sales estimates for 27 names | High — wrong estimates corrupt the spread signal | Use conservative consensus-range midpoints; document source per name; flag high-uncertainty names |
| Multi-program companies (VRTX, LLY, REGN) — implied PoS out of range | Medium — misleading spread for ~8 names | `single_asset: false` flag + `approximation_warning` in screener output |
| Historical universe reconstruction has look-ahead bias | Medium — backtest overstates model performance | Disclose explicitly; use only mktcap/ADV filters for clean backtest, Phase 2+ gate is disclosed-contaminated |
| OpenFDA API rate limits | Low — 240 requests/minute free tier | Batch polls, 15-min cadence is 4 polls/hour well within limits |
| Calibration database worthless without outcomes | High — Phase 3 timeline depends on real readouts | Start recording predictions immediately even if outcomes won't arrive for months |
| Acquirer profile curation goes stale | Medium — post-deal, priorities shift | Semi-annual review cadence; `last_updated` field in YAML |
| POS dataset failure additions require manual research | Medium-High — bottleneck is human time | Prioritize 20 high-profile failures (NASH, Alzheimer, oncology) first; dataset improves incrementally |

## Definition of "institutional grade"

The system crosses the institutional threshold when it can answer, for any universe name, within 30
seconds:

1. **Mispricing**: "The market implies a 41% PoS for VK2735. Our model predicts 68%. The 27pp spread
   represents the market underpricing the obesity data quality and Novo's competitive disadvantage in
   oral delivery."

2. **Acquisition fit**: "VKTX scores 0.79 on Lilly's gap list. Lilly has tirzepatide but no
   next-gen oral GLP-1 outside their own pipeline. VK2735 oral fills that gap at a reasonable size
   ($2.1B EV vs $3–8B deal range)."

3. **Catalyst timing**: "KARDIA-2 readout expected Q2 2026 (41 days). At current spread of +15.8pp,
   a positive readout would close the spread, implying ~22% price appreciation. Risk: KARDIA-1B
   showed marginal SBP reduction in high-CV patients."

None of this requires access to non-public information. It requires the infrastructure to systematically
produce it for 27 names simultaneously, in under a minute.
