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

### 4. It does not model goodwill or acquisition control premium

The rNPV output is intrinsic value — the probability-weighted discounted cash flow of the asset
if developed and commercialized by the current holder. Observed M&A prices routinely include
30–80% premiums over intrinsic value. That gap is goodwill. The tool does not model it.

**What goodwill captures that the tool misses:**
- Acquisition control premium over intrinsic value
- Assembled workforce / platform know-how
- Strategic synergies (cost savings, cross-selling)
- Brand / relationships
- Pipeline optionality beyond the modeled indication(s)

**What the tool partially captures as proxies:**
- Platform value is approximated via modality scoring and TA fit in the M&A layer
- Acquirer urgency / pipeline pressure reflects some strategic premium logic
- `deal_premium.py` compares observed deal prices to rNPV — the gap between them is
  essentially goodwill + control premium, but it is measured after the fact, not modeled
  prospectively into the asset price

**Practical implication**: The tool will systematically underprice acquisition targets relative
to actual deal values. The rNPV output is best interpreted as a **floor valuation** or intrinsic
value baseline, not an expected deal price. A BD team should add an explicit strategic premium
estimate on top of rNPV when sizing deal probability or comparing to rumored deal prices.

See `DEAL-1` in Planned Improvements for the implementation path.

### 5. It is not institutional-grade validated yet

The architecture is substantially closer to institutional grade than when the project started
(no-lookahead enforcement, source freshness audits, CT.gov point-in-time exclusion, bucket
minimum gates, VRTX-heavy disclaimers). But clean architecture does not prove the model works.
Evidence of predictive validity comes from backtesting against historical outcomes, not from
reading the codebase. Until the backtest dataset reaches ≥20 verified deals and the
rolling-window evaluation produces a statistically interpretable AUC, the tool is a
decision-support framework, not a validated predictive model.

---

## Planned Improvements

### LIVE-1 — Make live scanner rescoring fully automatic and explainable

**Current state**: The watchlist pipeline can fetch documents from configured
connectors, extract structured signals, apply confidence gates, map eligible
signals into valuation changes, persist valuation diffs, refresh market prices,
and rerank assets from stored valuation diffs and structured signals.

That means the live scanner can rerank after new evidence **when** the evidence
is successfully fetched, extracted, mapped, and allowed through the valuation
gate. It is not yet a fully autonomous news intelligence system. Some documents
are skipped by confidence gates, some mappings are routed to manual review, and
many unstructured biotech-news headlines still need better interpretation before
they can safely change POS, rNPV, M&A probability, or BD priority.

**The gap**: the live scanner path needs a stronger end-to-end contract:

```text
new source document
  -> extracted event and facts
  -> materiality judgment
  -> proposed model changes
  -> auto/apply or human-review route
  -> valuation and M&A rescore
  -> ranked output with "why score changed"
```

Today, parts of that chain exist, but the handoff is not yet institutional-grade
for live news. The system needs clearer coverage of which event types can update
which model fields, stronger free-text extraction, better source conflict
resolution, and explicit score-change attribution.

**The fix**:

1. **Build a live-news event coverage matrix**
   - For each event type, define whether it can affect POS, revenue, cost,
     market expectations, M&A target attractiveness, BD priority, acquirer fit,
     or close probability.
   - Example: positive Phase 2 readout can affect POS and rNPV; strategic
     partnership can affect M&A seller willingness and acquirer relationship;
     CRL can affect POS, timing, cost, and M&A ranking.

2. **Add a score-change attribution object**
   - Store before/after scores for valuation rank, M&A probability, BD route,
     POS, rNPV, and confidence.
   - Store the source document, extracted fact, mapped field, and exact
     contribution to the score movement.
   - Output a readable explanation: "Rank increased because Phase 2 readout
     raised prior-phase data strength and rNPV increased by $X."

3. **Separate auto-apply from review-required mappings**
   - Low-risk factual updates can auto-apply.
   - Judgment-sensitive updates, especially endpoint quality, clinical effect
     magnitude, MCID interpretation, safety severity, and M&A strategic
     implications, should route to review before changing the live score.

4. **Improve free-text biotech-news parsing**
   - Use source-specific prompts for press releases, SEC 8-Ks, FDA pages,
     conference abstracts, and news articles.
   - Extract p-values, effect sizes, endpoint names, safety rates, regulatory
     action type, partnership terms, rights geography, and milestone structure.
   - Attach source excerpts so analysts can audit every proposed score change.

5. **Rerun both relevant paths**
   - Rerun the fast live scanner ranking after any approved valuation or M&A
     signal change.
   - Rerun the institutional BD layers when the event changes eligibility,
     target attractiveness, BD urgency, pair feasibility, deal structure, or
     calibrated M&A probability.

6. **Add score-change tests and replay validation**
   - Use historical documents to assert that known positive/negative events move
     the correct model fields in the correct direction.
   - Replay documents point-in-time and compare the generated score-change
     attribution to expected outcomes.

**Priority**: High. This is the clearest path from "good scoring framework" to
"useful live BD/M&A monitoring product."

**Estimated scope**:
- New module: `src/bve/intelligence/live_score_attribution.py`
- New module: `src/bve/intelligence/live_event_impact_matrix.py`
- Expand `MappingEngine` coverage for M&A-specific event impacts
- Extend `KnowledgeStore` with score-change attribution records
- Add `bve-live-explain` or weekly report section showing why ranks changed
- Add replay fixtures for positive readout, failed readout, FDA hold, CRL,
  partnership, takeover rumor, financing stress, and asset discontinuation

---

### MNA-1 — Build specialist scoring models for routed non-core company types

**Current state**: Layer 0 and the exclusion/routing engine can identify company
types that do not belong in the standard therapeutics acquisition model. It can
route royalty/passive IP companies, services-only companies, diagnostics/tools
companies, licensing-only cases, distress cases, platform cases, and commercial
franchise cases away from the default path.

The core implemented deal-type model routes are:

| Route | Status |
|---|---|
| `lead_asset_rnpv_model` | Implemented core route |
| `portfolio_mna_model` | Implemented core route |
| `platform_fit_model` | Implemented core route |
| `commercial_synergy_model` | Implemented core route |
| `licensing_model` | Implemented core route |
| `distress_adjusted_model` | Implemented core route |

But some routes currently exist mostly as **classification / exclusion
destinations**, not as full specialist scoring models:

| Routed company type | Current gap |
|---|---|
| Royalty/passive IP company | `royalty_model` route exists, but there is no full royalty-acquisition scoring framework. |
| Tools company | Routed away from therapeutics M&A, but no tools-specific M&A score. |
| Diagnostics company | Routed away from therapeutics M&A, but no diagnostics-specific M&A score. |
| CRO/CDMO/services company | Routed to services M&A model, but no full services-M&A score. |

**Should this be fixed?** Yes, if the tool is intended to screen the broader
life-sciences universe. No, if the tool remains intentionally focused on
therapeutics assets and biotech company acquisitions. The current behavior is
acceptable for a therapeutics-first scanner because it prevents wrong-model
scoring. It becomes a product gap once these routed categories are expected to
receive ranked outputs.

**The fix**: create specialist models that match the economics and deal logic of
each routed category.

1. **Royalty/passive IP model**
   - Inputs: royalty stream durability, payer/product concentration, patent
     runway, counterparty quality, tiered royalty economics, litigation/IP risk,
     discount rate, and transaction comparables.
   - Output: royalty stream value, acquisition attractiveness, concentration
     risk, and buyer universe.

2. **Diagnostics model**
   - Inputs: test volume, reimbursement/CPT status, clinical utility evidence,
     guideline adoption, lab/channel fit, gross margin, regulatory status, and
     pharma companion-diagnostic relevance.
   - Output: diagnostics M&A score and likely buyer class.

3. **Tools / reagents model**
   - Inputs: recurring revenue, installed base, consumables pull-through,
     customer concentration, margin profile, R&D/manufacturing quality, and
     strategic fit with tools acquirers.
   - Output: tools M&A score and valuation multiple framework.

4. **Services / CRO / CDMO model**
   - Inputs: backlog, capacity utilization, customer concentration, GMP record,
     modality specialization, EBITDA margin, capex needs, and sponsor quality.
   - Output: services M&A score, integration complexity, and buyer universe.

**Priority**: Medium. This is not required for the core therapeutics M&A model,
but it is important if the scanner is meant to cover all life-sciences companies
rather than route non-therapeutics names out of scope.

**Estimated scope**:
- New module: `src/bve/intelligence/ma_royalty_model.py`
- New module: `src/bve/intelligence/ma_diagnostics_model.py`
- New module: `src/bve/intelligence/ma_tools_model.py`
- New module: `src/bve/intelligence/ma_services_model.py`
- ~~Extend Layer 0 routing output to call the appropriate specialist model when
  requested instead of stopping at `ROUTE_TO_OTHER_MODEL`~~ — **DONE** (2026-06-04):
  `ROUTE_TO_OTHER_MODEL` has been removed from Layer 0A. Gate 10 no longer routes
  deal types to specialist models. Model routing is now owned by Layer 0B
  (`DealStructureRoute`). See `ARCH-1` below.
- Add sample fixtures for one royalty company, one diagnostics company, one
  tools company, and one CDMO/CRO-style company

---

### ARCH-1 — Layer 0 0A/0B separation: eligibility vs. deal-structure routing ✅ IMPLEMENTED

**Completed**: 2026-06-04

**What was the problem**: Layer 0A (the hard-exclusion / eligibility engine) was
doing double duty: it was both a stoplight gate (pass/fail) AND a model router
(licensing-only → LICENSING_MODEL, distress-only → DISTRESS_MODEL, etc.). This
violated separation of concerns. Gate 10 used `_CANONICAL_ROUTING_MAP` to route
companies to specialist models, mixing eligibility logic with transaction-type
classification.

**What was built**:

1. **0A refactored to pure stoplight gate** — produces one of seven
   `EligibilityStatus` values:
   `PASS / DILIGENCE_QUEUE / REFRESH_REQUIRED / LEGAL_REVIEW_QUEUE /
   SEVERE_CAP / HISTORICAL_ONLY / HARD_FAIL`.
   Gate 10 no longer routes companies. `_CANONICAL_ROUTING_MAP = {}`.

2. **0B now owns all model routing** — `classify_deal_structure_route()` in
   `deal_type_classification.py` emits `DealStructureRouteResult` with one of
   eleven `DealStructureRoute` values. `ASSET_LICENSE_PARTNERSHIP` expands into
   five licensing sub-routes (GLOBAL, REGIONAL, OPTION, CO_DEV, MINORITY_EQUITY).
   Structural signal overrides determine the sub-route.

3. **0B runs for imperfect targets** — when 0A returns DILIGENCE_QUEUE,
   REFRESH_REQUIRED, SEVERE_CAP, or LEGAL_REVIEW_QUEUE, 0B still runs and
   produces a tentative route (lower confidence). HARD_FAIL and HISTORICAL_ONLY
   do not get a 0B route.

4. **`EligibilityAssessment`** attached to `Layer0Result` — structured
   `can_enter_live_ranking` / `can_enter_historical_dataset` flags with
   `status_reason`, `hard_blockers`, `caps`, `required_diligence_items`.

5. **`MONITOR_ONLY` stays in Layer 4** — not a `DealStructureRoute` value.
   Action/cadence recommendations remain in `WatchlistClass`.

**Files changed**:
- `src/bve/intelligence/exclusions/rules.py` — Gate 10 refactored
- `src/bve/intelligence/deal_type_classification.py` — `DealStructureRoute` enum,
  `DealStructureRouteResult`, `classify_deal_structure_route()`, `_check_structure_overrides()`
- `src/bve/intelligence/ma_eligibility.py` — `EligibilityStatus`, `EligibilityAssessment`,
  `_build_eligibility_assessment()`, `run_0b` logic in `evaluate_layer0()`
- `tests/test_deal_type_enum_drift.py` — updated for new Gate 10 behavior
- `tests/test_ma_layer0_refactor.py` — new acceptance test suite (83 tests)

---

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

### DEAL-1 — Goodwill and strategic premium layer on top of rNPV

**The problem**

rNPV is intrinsic value. Every observed biotech acquisition includes a control premium and
strategic synergy premium that rNPV does not capture. The result: the tool's deal price floor
is correct but the tool has no way to estimate the *expected transaction price* — which is
what a BD team or buy-side investor actually needs.

**Component decomposition**

A deal price can be modeled as:

```
DealPrice = rNPV_floor
          + ControlPremium          (% of rNPV; reflects competitive bidding, urgency)
          + PlatformKnowhowValue    (assembled workforce, IP breadth, manufacturing know-how)
          + SynergyNPV              (PV of cost saves, avoided R&D duplication, cross-sell)
          + PipelineOptionality     (real-options value of unmodeled indications)
```

**Implementation path**

1. **New dataclass** `src/bve/models/goodwill_model.py`:
   ```python
   @dataclass(frozen=True)
   class GoodwillComponents:
       control_premium_pct: float         # 0.30–0.80 typical range (literature-backed)
       platform_knowhow_millions: float   # assembled workforce / IP value estimate
       synergy_npv_millions: float        # PV of acquirer-specific cost saves
       pipeline_optionality_millions: float  # real-options value for unmodeled indications
   ```
   `total_goodwill(rnpv)` returns sum of all components, with `control_premium` computed
   as `control_premium_pct × rnpv`.

2. **`DealEconomics` extension**: add optional `goodwill: GoodwillComponents | None = None`.
   When present, `ValuationOutput` reports `deal_price_estimate = rnpv + goodwill.total()`.
   When absent, the output only reports the rNPV floor with a disclaimer note.

3. **Acquirer-level defaults** in `acquirers.yaml`: each acquirer profile gains a
   `typical_control_premium_range: [0.35, 0.60]` field. The engine samples from this range
   in Monte Carlo to produce a deal price distribution, not just a point estimate.

4. **`deal_premium.py` integration**: currently measures the rNPV-to-deal-price gap ex-post.
   With this model, it can compare predicted goodwill to observed goodwill and over time
   calibrate the acquirer-level premium distributions to real historical deal data.

5. **Output addition**: new `goodwill_decomposition` dict in `valuation.json` and a
   "Deal Price Range" band on the scenario bars chart showing `[rNPV, rNPV + goodwill_low,
   rNPV + goodwill_high]`.

**Calibration source for control premium**

Published M&A literature (Mergerstat, PwC Pharma M&A reports) gives biotech control premiums
of 30–80% over undisturbed market price. The rNPV floor typically already implies some
development optionality, so the premium over rNPV may be narrower (20–50%) for assets where
rNPV already exceeds market cap, and wider (60–100%) for distressed or platform deals.
`deal_premium.py` on the VRTX/REGN dataset can empirically calibrate these numbers once
the dataset is large enough.

**Why this is not in the current model**

Control premium is acquirer-specific and deal-context-specific. A hardcoded 50% uplift would
be misleading. The fix requires (a) acquirer profiling, (b) synergy estimation logic, and
(c) empirical calibration from historical deals. The infrastructure for (a) and (c) now
exists in `acquirers.yaml` and `deal_premium.py`; (b) is the missing piece.

**Priority**: Medium. This is the fix that closes the gap between "what the tool says the
asset is worth" and "what a deal will actually price at." It matters most when using the
tool to assess whether a rumored deal price is fair or to size position targets around
acquisition probability.

---

### AUTO-5 — Automatic live data ingestion and score updates (full pipeline automation)

**The problem**

Almost every adjuster in the POS model and every sub-score in the M&A scanner is set manually
in YAML config files. When a trial reads out, a press release drops, a competitor gets approved,
or a company files an 8-K, nothing in the system updates automatically. A human must:
- Read the news
- Decide which adjusters change
- Open the relevant YAML
- Update the values
- Re-run the engine

This makes the tool a point-in-time snapshot rather than a live scoring system. The lag between
a real-world event and a score update is as long as it takes someone to notice and act.

**What should update automatically (full scope)**

| Data source | What it should trigger |
|---|---|
| ClinicalTrials.gov status transition | `prior_phase_data`, `data_maturity` update candidates |
| SEC 8-K trial result language | `clinical_effect_magnitude`, `safety_flag` update candidates |
| FDA press release (designation/approval) | `has_breakthrough_designation`, `approval_pathway` update |
| Company press release (LLM-parsed) | All POS adjusters flagged as stale |
| Competitor approval in same TA | `competitive_pressure` update for all assets in that TA |
| Head-to-head trial result | `clinical_effect_magnitude` update (vs active comparator) |
| New safety signal (AE report, FDA safety comms) | `safety_flag` update candidate |
| M&A news (acquirer deal announced) | Acquirer pipeline gap recalculated; M&A scores for TA refreshed |
| Company BD activity (partnership, licensing) | `prior_bd_activity`, `seller_openness` update |

**What the update pipeline looks like**

1. **Ingestion**: continuous monitor watches SEC EDGAR, CT.gov, FDA, major wire services
2. **Classification**: event classifier tags the event type and the asset(s) affected
3. **Extraction**: LLM or rule-based extractor pulls structured fields (trial phase, p-value,
   endpoint met/not met, safety signal type, etc.)
4. **Draft proposal**: system generates a `ScoreUpdateDraft` with:
   - Proposed adjuster/sub-score change
   - Source excerpt and URL
   - Confidence level
   - Current value vs proposed value
   - Estimated score delta
5. **Routing**: high-confidence changes (e.g., CT.gov status = COMPLETED) can auto-apply
   with provenance record; low-confidence changes route to human review queue
6. **Application**: approved changes write back to YAML + evidence ledger; engine recomputes;
   M&A rankings re-ranked; watchlist classes updated

**Why full automation isn't built yet**

The ingestion and classification infrastructure exists (`event_classifier.py`,
`universe_scanner.py`, `continuous_monitoring.py`). The missing pieces are:
- A structured mapping from event type → specific adjuster field + new value
- A `ScoreUpdateDraft` queue with human-review gate (partial design in AUTO-1)
- A rule engine that translates "competitor approved in 1L NSCLC" into a competitive_pressure
  update for every other asset in that bucket
- M&A layer re-ranking triggered by score changes (currently batch-only)

**Priority**: High. This is the single architectural gap that limits the tool from being a
continuously-maintained intelligence system rather than a manually-updated scorecard.

---

### AUTO-6 — Endpoint quality → commercial value propagation post-approval

**The problem**

When a drug gets approved on a weak or surrogate endpoint (e.g., accelerated approval on
biomarker response rate rather than OS in oncology), the POS model correctly penalizes the
probability of approval. But once approved, P(approval) = 1.0 and the rNPV is driven entirely
by the `MarketModel` assumptions set manually in YAML. The model has no automatic link from
"weak endpoint" → "lower payer access" → "lower penetration/price."

**What a weak endpoint approval actually means commercially**

- Narrow label: FDA often restricts to the exact population studied, reducing addressable patients
- Payer pushback: formulary restrictions, step-therapy requirements, prior authorization burden
- Net price discount: payers negotiate harder without hard clinical outcome data
- Confirmatory trial overhang: risk of label withdrawal if confirmatory trial fails
- Competitor displacement risk: a later entrant with OS data can displace the surrogate-approval drug

**None of this is captured automatically.** The rNPV of a drug approved on a surrogate endpoint
looks identical to a drug approved on hard OS data if the analyst uses the same MarketModel
assumptions for both.

**The fix**

1. Add `approval_endpoint_quality: EndpointQuality` field to `CommercialPlan`
   (enum: `HARD_CLINICAL`, `VALIDATED_SURROGATE`, `UNVALIDATED_SURROGATE`, `ACCELERATED_PENDING_CONFIRMATION`)
2. In `MarketModel`, apply automatic adjustments when `approval_endpoint_quality` is set:
   - `HARD_CLINICAL`: no adjustment (reference)
   - `VALIDATED_SURROGATE`: −10% peak penetration (payer friction, not clinically meaningful gap)
   - `UNVALIDATED_SURROGATE`: −20% peak penetration, −15% net price (significant payer pushback)
   - `ACCELERATED_PENDING_CONFIRMATION`: as above + confirmation trial costs added to `CostModel`
3. Add `label_breadth_discount: float` field (0–1.0) to apply when the approved label is
   narrower than the full `addressable_patients_annual` pool
4. Document as a post-approval commercial adjustment, separate from the pre-approval POS penalty,
   so the two layers are not double-counted

**Priority**: Medium. Matters most for assets on accelerated approval pathways or those with
surrogate endpoint approvals where the label is actively contested by payers.

---

## Calibration and Behavior Review Items

The following are known model behaviors that are defensible but potentially miscalibrated.
Each should be reviewed and considered for adjustment as the backtest dataset grows.

### REVIEW-1 — Endpoint type weight attenuation by phase

**Current behavior**: `endpoint_type` contributes the same logit weight whether the asset is
pre-Phase 1 (no human data) or pre-NDA (Phase 3 complete). Documented in AUTO-1B.

**Why it may be wrong**: Endpoint type is a design prior — a prediction about how trustworthy
future data will be. Once you have Phase 2 data on that same endpoint, the endpoint quality is
already embedded in the result. Counting endpoint type again is partial double-counting.

**Review question**: Should `endpoint_type` weight attenuate to near-zero when
`prior_phase_data = STRONG_REPLICATED`?

---

### REVIEW-2 — Novel MoA penalty vs strong Phase 1 data

**Current behavior**: `moa_precedent = NO_PRECEDENT` applies a fixed negative logit (~−0.25)
regardless of what Phase 1 showed. `prior_phase_data = STRONG_SINGLE` adds only +0.20, so
a novel MoA asset with clean Phase 1 proof-of-mechanism is still net-negative vs a conventional
MoA with no data.

**Why it may be wrong**: If Phase 1 demonstrates clear human proof of mechanism (PK/PD,
dose-response, early efficacy signal), the lack of historical precedent becomes a much weaker
concern. The `HUMAN_PROOF_OF_MECHANISM` exception flag partially handles this, but only if
manually set.

**Review question**: Should `HUMAN_PROOF_OF_MECHANISM` in `moa_exception_flags` fully neutralize
the `NO_PRECEDENT` penalty rather than partially offsetting it?

---

### REVIEW-3 — Small sample size penalty vs effect size magnitude

**Current behavior**: `sample_size = SMALL` applies a fixed negative logit (~−0.20) regardless
of the observed effect size. `clinical_effect_magnitude = EXCEEDS_MCID` adds +0.25, so they
partially cancel. A small trial with a massive effect size is penalized for being small even
when the signal is statistically unambiguous.

**Why it may be wrong**: A 40-patient trial showing 80% ORR vs 10% historical control has
very different inferential weight than a 40-patient trial showing 25% ORR vs 18% SoC. Both
receive the same `SMALL` penalty. In high-effect-size scenarios, underpowering concerns
largely vanish.

**Review question**: Should `sample_size` penalty be conditioned on `clinical_effect_magnitude`?
If `EXCEEDS_MCID` and n ≥ threshold, attenuate the small-sample penalty.

---

### REVIEW-4 — Safety flag is static; no dynamic safety update

**Current behavior**: `safety_flag` is set manually and never changes unless a human updates
the YAML. Default when unknown = neutral (0 adjustment). Late-emerging safety signals from
post-approval studies, REMS additions, or competitor class-effect signals do not flow into
the model.

**Why it may be wrong**: Safety is one of the highest-impact factors for both POS and commercial
value, but it's the least automatically maintained. A class-effect AE warning in a related drug
should trigger a review of all assets with the same MoA.

**Review question**: Should safety flag changes be one of the first AUTO-5 automated triggers,
given safety's disproportionate impact on both POS and payer access?

---

### REVIEW-5 — Competitive pressure reflects crowding, not head-to-head outcomes

**Current behavior**: `competitive_pressure` captures how crowded the therapeutic area is.
A head-to-head win (drug beats active comparator) is captured indirectly via
`clinical_effect_magnitude = EXCEEDS_MCID`, not as a competitive signal. A head-to-head loss
requires manually setting `prior_phase_data = FAILED` or `MIXED`.

**Why it may be wrong**: Competitive pressure and head-to-head outcomes are distinct signals.
A drug can be in an uncrowded space but lose a head-to-head (bad). Or it can be in a crowded
space and dominate every comparator (good). These are not equivalent. The current model treats
competitive landscape as a static crowding count, not a relative differentiation score.

**Review question**: Add a `competitive_differentiation` sub-adjuster that captures relative
performance vs SoC/competitors (SUPERIOR / COMPARABLE / INFERIOR), separate from crowding count.

---

### REVIEW-6 — Layer 2 single-arm penalty is context-blind

**Current behavior**: Layer 2 penalizes `evidence_design = SINGLE_ARM` regardless of whether
a comparator is scientifically possible. For ultra-rare diseases or first-in-class mechanisms
with no active control, single-arm is the only ethical and practical design. The model doesn't
know a comparator doesn't exist — it just scores the design type.

**Why it may be wrong**: The penalty is calibrated for settings where a randomized comparator
was possible but not used. Applying the same penalty to a setting where no comparator exists
overstates the evidentiary weakness.

**Review question**: Add a `comparator_available: bool` flag to `TrialDesignFeatureSet`. When
`False` and `evidence_design = SINGLE_ARM`, attenuate or eliminate the single-arm penalty.

---

### REVIEW-7 — Accelerated approval pathway penalty may be asymmetric

**Current behavior**: `approval_pathway = ACCELERATED_APPROVAL` applies a slight negative
logit to reflect confirmatory trial risk. But Breakthrough Designation (`BREAKTHROUGH_DESIGNATION`)
applies only a slight positive logit. Both are assigned the same phase-conditional scaling.

**Why it may be wrong**: Breakthrough Designation is both a regulatory pathway signal AND
evidence of FDA engagement — it often co-occurs with strong early data. Treating it as a minor
positive may underweight what is in practice a strong combined signal (strong data + FDA buy-in).

**Review question**: Should Breakthrough Designation interact with `prior_phase_data` — i.e.,
Breakthrough + STRONG_SINGLE should yield a larger combined bonus than either alone?

---

### REVIEW-8 — Market sizing mode is not enforced by therapeutic area

**Current behavior**: The analyst manually selects market sizing mode (lines_of_therapy /
patient-based / TAM-based) in YAML. There is no enforcement or warning if an oncology asset
uses TAM-based sizing instead of lines_of_therapy.

**Why it may be wrong**: TAM-based sizing for oncology systematically overstates or understates
depending on the analyst's TAM assumption. Lines-of-therapy is the clinically grounded mode
for oncology because it reflects actual treatment decision points.

**Review question**: Add a validation warning when `therapeutic_area = oncology` and
`market_sizing_mode = TAM_BASED`. Suggest switching to `lines_of_therapy` with a pointer to
the YAML schema.

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
