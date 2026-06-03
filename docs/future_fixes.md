# Future Fixes and Known Limitations

This file tracks features the system does not yet do, design gaps that are known and intentional,
and planned improvements. It is the honest counterpart to the architecture documentation.

---

## What It Does Not Fully Do Yet

### 1. It does not automatically discover every good target

The SEC scanner (`src/bve/ingestion/universe_scanner.py`) can discover biotech-ish tickers from
EDGAR filings, but the real M&A universe still requires manual curation. The scanner can expand
coverage from ~50 to 100–150 names, but those names need a human to confirm therapeutic focus,
stage, and encumbrance status before they enter the acquirer-fit scoring pipeline.

**The gap**: automated discovery ≠ curated universe. A name scraped from EDGAR may be a
diagnostics company, a CDMO, or a platform play that looks like a drug company. The
`research/universe/targets.yaml` and `research/universe/acquirers.yaml` files are the curated
ground truth. The scanner feeds candidates into that curation process; it does not replace it.

### 2. It does not deeply parse unstructured news yet

The ingestion layer handles SEC filings, ClinicalTrials.gov, and FDA structured/semi-structured
sources. It does not yet have a strong RSS/news/LLM layer for headlines like:

> "Company reports encouraging early data in rare kidney disease"

unless the rule-based event classifier (`src/bve/ingestion/event_classifier.py`) happens to catch
the pattern. The event classifier works on keyword rules and signal types — it will not reliably
extract p-values, effect sizes, or endpoint context from free-text press releases. A full NLP/LLM
parsing layer for unstructured biotech news is a planned but not-yet-built component.

### 3. It does not prove accuracy yet

The engine produces candidate rankings and M&A fit scores, but there is no validated evidence
that these rankings are predictive of actual acquisitions at a statistically meaningful level.

The VRTX/REGN backtest (Block 15) is a step toward proof, but:
- N=5 verified primary positives
- 4 of 5 are Vertex; REGN has N=1
- All hit-rate and AUC figures have confidence intervals spanning roughly 0%–100%

Proof requires:
- Historical acquisition dataset with ≥20 verified deals across ≥3 acquirers
- Rolling 24-month backtest with no-lookahead guarantee
- Precision@10, Precision@25
- AUC-ROC with p-value < 0.05
- Brier score and calibration curves
- Out-of-sample validation on a held-out acquirer

None of these are complete. The backtest infrastructure is built; the labeled dataset is not
large enough yet.

### 4. It is not institutional-grade validated yet

The architecture is substantially closer to institutional grade than when the project started
(no-lookahead enforcement, source freshness audits, CT.gov point-in-time exclusion, bucket
minimum gates, VRTX-heavy disclaimers). But clean architecture does not prove the model works.
Evidence of predictive validity comes from backtesting against historical outcomes, not from
reading the codebase. Until the backtest dataset reaches ≥20 verified deals and the
rolling-window evaluation produces a statistically interpretable AUC, the tool is a
decision-support framework, not a validated predictive model.

---

## Planned Improvements

### AUTO-1 — Automatic clinical trial result ingestion and POS update (human-in-the-loop)

**Current state**: POS adjusters are set manually. When a Phase 2 trial reads out, a human
must open the YAML config and update:
- `prior_phase_data` (e.g. `STRONG_SINGLE` or `FAILED`)
- `clinical_effect_magnitude` (e.g. `EXCEEDS_MCID`)
- `data_maturity` (e.g. `MATURE_FINAL`)
- `moa_exception_flags` (e.g. add `HUMAN_PROOF_OF_MECHANISM`)

**The fix**: Build an automated pipeline that:

1. **Ingests** clinical trial result signals from:
   - ClinicalTrials.gov status transitions (e.g. `ACTIVE_NOT_RECRUITING` → `COMPLETED`)
   - FDA press announcements for breakthrough/accelerated designations
   - SEC 8-K filings containing trial result language
   - Company press releases parsed with an LLM extractor

2. **Extracts** the following fields in a structured format:
   - Trial phase and NCT ID
   - Primary endpoint met / not met
   - Effect size relative to MCID (requires TA-specific MCID table)
   - Safety signals (AE rates, dose discontinuations)
   - Data maturity (final vs. interim)
   - Regulatory feedback (if any)

3. **Proposes** a `POSAdjusterDraft` — a machine-generated suggestion for which enum
   values to set on `POSAdjusters`, with the source excerpt and confidence score attached

4. **Routes to human review**: the draft sits in a queue. A reviewer sees:
   - The raw excerpt ("ORR 42% vs 18% placebo, p=0.001, n=87")
   - The proposed mapping (e.g. `clinical_effect_magnitude=EXCEEDS_MCID`)
   - The current value in the YAML (e.g. `UNKNOWN`)
   - A diff showing what would change in the POS estimate

5. **On approval**: the approved values are written back to the asset YAML config,
   a provenance record is created in the evidence ledger, and the affected asset's
   POS is recomputed. The change is committed with the source URL as the commit message body.

**Why human review is required**: The mapping from raw trial data to `PriorPhaseDataStrength`
enum tier is judgment-sensitive. A trial can "succeed" statistically but fail commercially
(effect size below MCID). The model does not know the MCID for every endpoint in every TA
automatically. A human must confirm that the proposed tier is correct before it updates
the live POS estimate.

**Priority**: High. This is the single change that would most improve the usefulness of the
model for BD teams tracking live pipeline assets. Without it, POS updates lag real-world
data by however long it takes someone to manually update the YAML.

**Estimated scope**:
- New module: `src/bve/ingestion/trial_result_extractor.py` — parses 8-K/PR text using an LLM
- New module: `src/bve/ingestion/pos_update_queue.py` — stores pending POS adjuster drafts
- New module: `src/bve/review/pos_review_gate.py` — human approval workflow (CLI or web)
- Schema addition: `POSAdjusterDraft` dataclass with `proposed_value`, `source_excerpt`,
  `source_url`, `extracted_at`, `confidence`, `reviewer_id`, `approved_at`
- Integration: `ValuationEngine` reads approved drafts before computing POS

---

### AUTO-1B — Phase-conditional weighting: endpoint type vs. actual trial data

**The problem in plain terms**

The POS model gives endpoint type (+0.40 for hard clinical outcomes) the same weight whether
you have zero human data or two clean replicated Phase 2 readouts. That is wrong. Endpoint
type is a *design prior* — a prediction about how trustworthy the upcoming trial will be.
Once you have actual trial data, that data already contains the endpoint type's information.
A clean Phase 2 on a hard clinical endpoint tells you both "the endpoint was credible" AND
"the molecule worked on that endpoint." Counting endpoint type again on top of the Phase 2
result is partial double-counting.

**When endpoint type should matter by phase**

| When you're assessing POS | What endpoint type is doing | Should it matter? |
|---|---|---|
| Pre-Phase 1 (no human data) | Tells you how credible the upcoming readout will be | A lot — it's one of your only signals |
| Pre-Phase 3 (have Phase 1+2 data) | Tells you how the Phase 3 is designed | Somewhat — but Phase 2 results already ran on this endpoint and showed what they showed |
| Pre-NDA (have Phase 1+2+3 data) | Retrospective design note | Almost nothing — the data exists, endpoint quality is baked in |

**Concrete example**

Pre-Phase 1 (no human data): endpoint type is a major signal.
- Base rate 60%, endpoint = hard clinical → +0.40 logit → POS rises to ~73%
- This makes sense: you're projecting forward with nothing else to go on.

Pre-Phase 3 (have clean Phase 2): endpoint type should barely matter.
- You have `prior_phase_data = STRONG_SINGLE` (+0.20) and
  `clinical_effect_magnitude = EXCEEDS_MCID` (+0.25).
- The Phase 2 already ran on that hard clinical endpoint and worked.
- Adding another +0.40 for "hard clinical endpoint in Phase 3" is mostly counting the same
  evidence twice: the molecule already showed up on that endpoint in Phase 2.

**The fix**

Layer 1 mixes two types of signals that need to be separated:

| Signal type | Examples | Weight rule |
|---|---|---|
| **Prospective design priors** (before data) | endpoint_type, sample_size, moa_precedent, dose_selection | Full weight when `prior_phase_data = UNKNOWN/MIXED`; attenuated when strong data exists |
| **Retrospective data evidence** (after data) | prior_phase_data, clinical_effect_magnitude, data_maturity | Should dominate when data exists; ceiling too low at current values |

Specific calibration changes needed:

1. **`prior_phase_data = STRONG_REPLICATED`**: raise from +0.30 → +0.45 to +0.50.
   Two clean replicated human studies is the strongest non-approval signal. Its ceiling
   being lower than `endpoint_type = HARD_CLINICAL` (+0.40) is backwards.

2. **`endpoint_type` weight should be phase-conditional**:
   - No prior data (`prior_phase_data = UNKNOWN/MIXED`): full weight (+0.40 for hard clinical)
   - Strong prior data (`prior_phase_data = STRONG_SINGLE/STRONG_REPLICATED`): attenuate to
     +0.10 to +0.15 — the endpoint quality is already proven by the data
   - At NDA/BLA stage: endpoint type is irrelevant — the trial is done

3. **Layer 1 `endpoint_type` and Layer 2 `endpoint_basis` overlap** — both capture
   "how trustworthy/validated is the endpoint." The `check_pos_layer_overlap()` guard warns
   about this. The long-term fix is merging them into a single endpoint quality signal or
   making Layer 2 only activate when it adds something Layer 1 doesn't already encode.

**Implementation path**

- Add `data_exists: bool` computed flag to `POSAdjusters` (True when
  `prior_phase_data` is not UNKNOWN/MIXED)
- In `apply_pos_adjusters()`, scale `_ENDPOINT_LOGODDS_*` by an attenuation factor:
  `1.0` when no data, `0.25` when strong data exists
- Raise `_PRIOR_PHASE_LOGODDS[STRONG_REPLICATED]` from +0.30 to +0.48
- Raise `_PRIOR_PHASE_LOGODDS[STRONG_SINGLE]` from +0.20 to +0.32
- Add regression tests to confirm Phase 3 POS with strong Phase 2 data is not dominated
  by endpoint type

**Priority**: Medium. This is a calibration correctness issue, not a feature gap. It matters
most for assets with confirmed Phase 2 readouts where the model may be underweighting the
actual result and overweighting the design prior.

---

### AUTO-2 — LLM news parsing layer for unstructured biotech headlines

Parse RSS feeds from BioPharmaDive, FierceBiotech, STAT News, and company IR pages.
Use an LLM to extract:
- Asset name and sponsor
- Signal type (efficacy, safety, regulatory, partnership)
- Sentiment and materiality estimate
- Mapping to event classifier signal types

Route to the existing `EventClassifier` pipeline after extraction.

---

### AUTO-3 — Rolling backtest automation

Run the VRTX/REGN backtest automatically on a monthly cadence as new deals are added to
the seed CSV. Generate a trend report showing whether the model's ranking metrics improve
or degrade as the dataset grows. Flag when any bucket falls below minimum thresholds.

---

### AUTO-4 — Expand to third acquirer

Add AstraZeneca, Pfizer, or BMS as a third acquirer with ≥5 verified deals. This is the
minimum required to make AUC and MRR figures statistically interpretable and to reduce
the VRTX-heavy concentration risk in the current backtest.

---

## Known Non-Issues (Intentional Design Choices)

- **POS adjusters are evidence-informed priors, not statistically estimated coefficients.**
  They are calibrated from published Biomedtracker/IQVIA base rates and literature-sourced
  log-odds values. They are not regression weights fitted to a dataset. This is intentional:
  fitting weights to N<100 historical outcomes would overfit badly. The model is designed to
  be defensible as a structured expert judgment system, not a black-box ML model.

- **The negative DCF for Semma, ViaCyte, and Decibel is not a model failure.** These are
  early-stage option-value acquisitions. A standalone DCF correctly returns negative for
  pre-revenue assets with no near-term approval path. The strategic premium metric
  (Block 15) now makes this explicit.

- **CT.gov phase data is not point-in-time by default.** The ClinicalTrials.gov v2 API
  returns current records. The `TrialPhaseResolver` and `clinicaltrials_point_in_time_audit.csv`
  enforce exclusion of post-snapshot records. This is a deliberate constraint, not a gap.
