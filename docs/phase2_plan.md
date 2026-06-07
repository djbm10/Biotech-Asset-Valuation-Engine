# Phase 2 Plan — Live Pipeline & End-to-End Proof

**Goal**: Prove the machine works on real data, end-to-end, weekly.

**Not a goal**: Adding more scoring theory. Phase 1 built the institutional scoring
foundation. Phase 2 connects it to the world.

---

## Target State

One command, real output:

```bash
bve-weekly-run \
  --targets research/universe/targets.yaml \
  --acquirers research/universe/acquirers.yaml \
  --as-of 2026-06-01 \
  --lookback-days 14 \
  --score-mode provisional \
  --output outputs/weekly/2026-06-01
```

Produces:

```
outputs/weekly/2026-06-01/
  ranked_targets.csv
  top_acquirer_pairs.csv
  evidence_events.jsonl
  score_changes.csv
  audit_report.md
  validation_snapshot.json
```

Answers: who is likely to be acquired, why, by whom, what changed, how confident.

---

## Block Map

```
2A ──► 2B ──► 2D ──► 2E ──► 2F ──► 2G
  └──► 2C ──►
```

| Block | File(s) | Unblocks |
|-------|---------|---------|
| 2A | `research/universe/targets.yaml`, `acquirers.yaml`, `company_aliases.yaml`, `manual_overrides.yaml` + `src/bve/ingestion/universe_loader.py` | 2B, 2C |
| 2B | `src/bve/ingestion/profile_enricher.py` | 2D |
| 2C | `src/bve/ingestion/live_ingestion_runner.py` | 2D |
| 2D | `src/bve/intelligence/weekly_ma_screen.py` | 2E |
| 2E | `src/bve/reporting/weekly_report.py` | 2F |
| 2F | `src/bve/cli/{weekly_run,ingest_live,build_profiles,run_ma_screen}.py` + pyproject.toml | 2G |
| 2G | `.github/workflows/weekly_bve_run.yml` | — |

---

## Block 2A — Universe Configs

**New files:**
- `research/universe/targets.yaml` — 100–150 biotech/drug-developer targets
- `research/universe/acquirers.yaml` — 20–30 Big Pharma + large biotech
- `research/universe/company_aliases.yaml` — ticker → name/CIK lookup
- `research/universe/manual_overrides.yaml` — field-level overrides for enricher
- `src/bve/ingestion/universe_loader.py` — typed loaders with schema validation

**Target schema (per ticker):**
```yaml
RVMD:
  name: Revolution Medicines
  ticker: RVMD
  cik: "0001628171"
  exchange: NASDAQ
  company_type: drug_developer
  therapeutic_areas: [oncology]
  lead_asset: daraxonrasib
  lead_asset_phase: phase3
  lead_modality: small_molecule
  lead_indication: RAS-mutant cancers
  is_single_asset_company: false
  include_in_screen: true
```

**Acquirer schema:**
```yaml
AZN:
  name: AstraZeneca
  ticker: AZN
  cik: null
  therapeutic_areas: [oncology, respiratory, rare_disease]
  modalities: [small_molecule, biologic, antibody_drug_conjugate]
  deal_size_range_millions: [500, 40000]
  preferred_stages: [phase2, phase3, commercial]
  include_as_acquirer: true
```

**Priority acquirers:**
PFE, MRK, BMY, JNJ, ABBV, AMGN, GILD, REGN, VRTX, LLY, NVO, NVS, RHHBY, AZN,
SNY, GSK, TAK, BIIB, UTHR, INCY, MRNA, SNY, Astellas, Bayer

**Tests:** `tests/test_universe_loader.py` — schema validation, missing field errors, load round-trip.

---

## Block 2B — Profile Enricher

**New file:** `src/bve/ingestion/profile_enricher.py`

Turns `TargetEntry` + `AcquirerEntry` + data sources → model-ready profiles.

```python
ProfileEnricher.enrich_target(entry, ledger, overrides) → TargetProfileEnriched
ProfileEnricher.enrich_acquirer(entry, ledger, overrides) → AcquirerProfileEnriched
ProfileEnricher.enrich_all(targets, acquirers, ledger, overrides) → (list, list)
```

**Data sources (in fallback order):**
1. `manual_overrides.yaml` — always wins; no API call if field present
2. SEC 10-Q/10-K (existing `sec_edgar.py`) → cash, debt, R&D burn → cash_runway_months
3. ClinicalTrials.gov (existing `clinicaltrials_gov.py`) → phase confirmation
4. yfinance (existing `market_data.py`) → market_cap, enterprise_value
5. Evidence ledger → bd_appetite, urgency (from recent acquirer events)

**Key rule:** if `manual_overrides.yaml` has the field, use it. Don't fetch.
This is the Phase 2 reliability guarantee — automated extraction is noisy.

**Tests:** `tests/test_profile_enricher.py` — all data source calls mocked, manual override precedence, cash_runway calculation.

---

## Block 2C — Live Ingestion Runner

**New file:** `src/bve/ingestion/live_ingestion_runner.py`

Wires real sources into the evidence ledger using the full Phase 1 pipeline.

**Pipeline per item:**
```
source item
→ normalize(text, date, source_type, ticker) → RawItem
→ EventClassifier.classify_headline_multi()
→ EventClusterer.assign_cluster_id()
→ MaterialityEstimator.estimate()
→ ContextModifierEngine.apply()
→ ReviewGate.needs_review() → flag if materiality ≥ threshold
→ EvidenceLedger.append_if_not_duplicate()
```

**Sources (wire in this order):**
1. SEC 8-K filings — most reliable; already in `sec_edgar.py`
2. ClinicalTrials.gov study updates — already in `clinicaltrials_gov.py`
3. FDA designations/approvals — already in `fda.py`
4. RSS feeds: BioSpace, FierceBiotech, PRNewswire (biotech filter)

**Output:**
- `outputs/intelligence/evidence_ledger.jsonl` — append-only event log
- `outputs/weekly/YYYY-MM-DD/new_events.csv`

**Minimum viable:** 25 tickers, finds real recent events, logs them deduped.

**Tests:** `tests/test_live_ingestion_runner.py` — all network calls mocked; verifies dedup, classification round-trip, output file format.

---

## Block 2D — Weekly MA Screen

**New file:** `src/bve/intelligence/weekly_ma_screen.py`

The core ranking function. Brings every Phase 1 component together.

```python
WeeklyMAScreen.run(
    as_of_date, targets, acquirers, ledger, score_mode, gate
) → WeeklyMAScreenResult
```

**Per-target (all targets):**
1. `BaselineScorer.compute(structural_features, as_of_date)`
2. `EvidenceLedger.compute_score_state(ticker, as_of_date, score_mode)`
3. Apply `ReviewGate.weight_factor()` per event
4. `ConfidenceBandEstimator.compute(score, evidence_records)`
5. `EvidenceLedger.compute_evidence_coverage()` → per-domain coverage
6. `ScoreExplainer.explain()` → drivers + risk flags
7. Suppress if overall coverage < 0.20 (move to suppressed list)

**Per target-acquirer pair (top 40 targets × all acquirers):**

Build `PairFeatures` from profiles:
- `ta_overlap` = Jaccard(target.therapeutic_areas, acquirer.therapeutic_areas)
- `size_fit` = 1.0 if market_cap in deal_size_range, else exponential decay
- `modality_fit` = Jaccard(target.modality, acquirer.modalities)
- `acquirer_appetite/urgency/integration_capacity` = from AcquirerProfileEnriched

Then: `AcquirerPairScorer.score(features)`

**Suppression rule:** tickers with evidence_coverage_overall < 0.20 go to `suppressed_targets` — not ranked, labeled in report.

**Tests:** `tests/test_weekly_ma_screen.py` — fixture profiles, deterministic scoring, suppression logic, pair ordering.

---

## Block 2E — Weekly Report Generator

**New file:** `src/bve/reporting/weekly_report.py`

```python
WeeklyReportGenerator.generate(result, prev_result=None) → str
WeeklyReportGenerator.write_outputs(result, output_dir, prev_result=None) → list[Path]
```

**Report sections:**
1. Header — date, mode, version, universe size
2. Top 25 Targets table — rank, ticker, prob, range, top acquirer, driver, risk
3. Biggest Score Changes — delta vs prev_result; ticker, feature, Δscore, reason
4. New High-Impact Events — materiality ≥ 0.65 from this run
5. Pending Human Review — events flagged, awaiting disposition
6. Top 20 Pairs — target, acquirer, pair_score, ta_overlap, modality_fit
7. Suppressed Names — tickers removed + their coverage scores
8. Model Diagnostics — events processed, dupes skipped, source breakdown

**Output files written:**
- `ranked_targets.csv`
- `top_acquirer_pairs.csv`
- `evidence_events.jsonl`
- `score_changes.csv` (only when prev_result provided)
- `audit_report.md` (full Markdown report)
- `validation_snapshot.json` (pipeline_version, n_targets, n_events, score_mode, content hashes)

**Tests:** `tests/test_weekly_report.py` — fixture result → verify CSV columns, JSON keys, Markdown sections present.

---

## Block 2F — CLI Entry Points

Four commands wired through pyproject.toml `[project.scripts]`:

```bash
bve-build-profiles  --targets ... --acquirers ... --overrides ... --output ...
bve-ingest-live     --targets ... --lookback-days 14 --sources sec,ct,fda,rss
bve-run-ma-screen   --profiles ... --ledger ... --as-of ... --score-mode ...
bve-weekly-run      --targets ... --acquirers ... --as-of ... --lookback-days 14 \
                    --score-mode provisional --output ...
```

`bve-weekly-run` orchestrates: profile_enricher → live_ingestion_runner → weekly_ma_screen → weekly_report.

All commands support `--dry-run`. Exit 0 on success, 1 on error.

**Tests:** `tests/test_cli_weekly_run.py` — mocked pipeline, verifies output file creation and exit codes.

---

## Block 2G — GitHub Actions Workflow

**New file:** `.github/workflows/weekly_bve_run.yml`

```yaml
on:
  schedule:
    - cron: "0 23 * * 0"   # Sunday ~7pm ET
  workflow_dispatch:
    inputs:
      as_of_date:   { type: string, default: '' }
      score_mode:   { type: choice, options: [provisional, approved_only, all_auto], default: provisional }
      lookback_days: { type: string, default: '7' }
```

Steps: checkout → Python 3.11 → install → build profiles → ingest → screen → upload artifact.

**Rules:**
- Do NOT auto-commit outputs in first version — artifact upload only.
- Do NOT store secrets in workflow — use GitHub Secrets for any future paid sources.
- Open a GitHub Issue (via `gh issue create`) if `pending_review_count > 0`.

Phase 2 is not done until `workflow_dispatch` completes successfully.

---

## Acceptance Criteria

### Functional (all must pass)
1. 100+ targets and 20+ acquirers loaded from YAML
2. At least 3 live data sources wired (SEC 8-K, CT.gov, FDA)
3. Evidence ledger receives real new events for ≥25 tickers
4. Score replay works with both `approved_only` and `provisional` modes
5. `ranked_targets.csv` generated with all required columns
6. `top_acquirer_pairs.csv` generated with all required columns
7. `audit_report.md` generated with all 8 sections
8. `bve-weekly-run` runs end-to-end from CLI
9. GitHub Action completes on `workflow_dispatch`

### Quality (all must hold)
1. No duplicate score impact from the same event cluster
2. Every score change has source URL/text/date
3. Every ranked target has evidence coverage score
4. Targets with coverage < 0.20 are suppressed or clearly labeled
5. High-impact events (materiality ≥ 0.70) are provisional/pending-review
6. Scores are reproducible for a fixed `as_of_date`

### Test coverage
- `test_universe_loader.py`
- `test_profile_enricher.py` (mocked sources)
- `test_live_ingestion_runner.py` (mocked sources)
- `test_weekly_ma_screen.py`
- `test_weekly_report.py`
- `test_cli_weekly_run.py` (smoke test)

---

## What NOT to do in Phase 2

- No paid data sources
- No full LLM text extraction
- No automated asset/indication extraction (use manual overrides)
- No AUC optimization
- No expansion to 500+ names
- Do not treat ranked output as an investment signal

First: prove the full pipeline works with 100–150 names.

---

## Reuse from Phase 1

Every Phase 1 module is already wired in; Phase 2 adds glue only:

| Phase 1 module | Used by |
|----------------|---------|
| `event_classifier.py` (multi-label, correlation merge) | 2C |
| `event_cluster.py` (semantic dedup) | 2C |
| `materiality_estimator.py` | 2C |
| `context_modifiers.py` | 2C |
| `evidence_ledger.py` (hash dedup, decay, coverage) | 2C, 2D |
| `review_gate.py` (score modes) | 2C, 2D |
| `baseline_scorer.py` | 2D |
| `acquirer_pair_scorer.py` | 2D |
| `confidence_bands.py` | 2D |
| `score_explainer.py` | 2D, 2E |
| `ranking_backtest.py` | validation_snapshot.json |
| `model_versions.py` | audit trail throughout |
