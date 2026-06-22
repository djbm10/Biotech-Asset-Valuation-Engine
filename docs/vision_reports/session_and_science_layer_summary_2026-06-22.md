# Session + Science Thesis Layer Summary

**Date:** 2026-06-22
**Branches:** `core-engine-v1` (this session's work) · `science-wip/evidence-workflow` (science thesis layer)

This file consolidates two things: (1) the additive engineering work done in the
recent sessions on `core-engine-v1`, and (2) the full Science Thesis layer
(Phases 1–10) built on the `science-wip/evidence-workflow` branch.

---

## Part 1 — Session work (`core-engine-v1`)

The session ran a sequenced, additive program after the test-suite-greening
effort (ROI #1). Each item shipped as its own verified commit.

### ROI #2 — Config-quality / audit dashboard (slice 1 only)
- **`src/bve/ops/config_quality.py`** (new) — corpus provenance + completeness
  dashboard. Versioned explicit weights from day one
  (`QUALITY_SCORE_VERSIONS["v1.0"]`, sums to 1.0; `CURRENT_QUALITY_VERSION`).
  Separates two evidence axes: `_meta.defaulted_fields` (missing→coerced) vs
  `commercial_inputs` provenance (`curated_funnel` 1.0 / `derived` 0.5 / `none` 0.0).
  `completeness_score` is `None` when metadata absent (honest n/a, not fake 0).
- **`src/bve/cli/config_quality_report.py`** (new) — `bve-config-quality` CLI
  (`--root` repeatable, `--score-version`, `--output`, `--json`).
- **`tests/test_config_quality.py`** (new, 17 tests).
- **`pyproject.toml`** — registered `bve-config-quality` entry point.
- Findings: 20 derived M&A configs score 0.23 (curation queue); 45 replay configs
  honestly report n/a — validating the metadata-inconsistency risk.
- Leverage/materiality deliberately deferred to slice 2.

### ROI #3 — Calibration math (Murphy decomposition + dated pack)
- Chose to **extend existing modules**, not add a parallel `analysis/calibration.py`.
- **`src/bve/analysis/calibration_metrics.py`** — added `BrierDecomposition`
  dataclass + `brier_decomposition()` (Murphy reliability/resolution/uncertainty).
  Identity is exact on the **binned** Brier (forecasts→bin means); raw-vs-binned
  gap exposed as informational `binning_residual` only. Top bin right-closed so
  `p==1.0` isn't dropped.
- **`src/bve/analysis/pos_calibration.py`** — wired `decomposition` field into
  `TACalibrationResult` + `to_dict` + Markdown report; added `as_of` + scope note.
- **`tests/test_calibration_decomposition.py`** (new, 11 tests) — pure-math
  properties + regression anchors via the **authoritative** path
  `run_backtest_from_csv(csv).to_calibration_records()` (NOT the deprecated
  `load_from_backtest_csv` proxy).
- **Anchors (oncology, 2026-06-22, authoritative path):** N=145, Brier=0.2339,
  AUC=0.6941, ECE=0.1404; decomposition rel=0.024 res=0.030 unc=0.250 (abs tol 0.01).
- **`docs/vision_reports/calibration_pack_2026-06.md`** (new) — dated artifact,
  scope = calibration/discrimination quality only, NOT trading P&L.

### Slice-2 materiality mapping audit (report-only)
- **`docs/vision_reports/slice2_materiality_mapping_audit_2026-06.md`** (new).
- **Decisive finding:** the tornado (`analysis/sensitivity.py`, 8 specs) shocks
  **legacy `market_model` scalars only** and never touches the `commercial_inputs`
  decomposition. With TAM present in 50/51 configs, `net_price`/`wac`/`g2n`/`addressable_k`
  are never the shock target.
- **Coverage:** of 15 economic fields — exact 5, derived→unmapped 1, ambiguous 2,
  unmapped 7. Of the 7 core categories, ≈3.5 map cleanly; price, timing, and cost
  are unmapped.
- **Verdict:** do **not** build a full materiality ranker yet. Unblock it with
  either named sensitivity hooks or richer config provenance.

### Housekeeping
- Refreshed stale `CLAUDE.md` POS-backtest numbers (N=99→145, P2 44.3%, P3 59.1%,
  Brier 0.2339, AUC 0.6941, ECE 0.140, + Murphy decomposition pointers).
- Removed leftover `/tmp/bve-ingestion-verify` Codex worktree (branch tip preserved).

### Commit chain
`c166839` config-quality dashboard → `f2f31a5` Murphy decomposition + anchors +
dated pack → `58b81ce` slice-2 audit doc → `cad897e` CLAUDE.md refresh.
Full suite green at `cad897e` (1076 passed, 1 skipped in the targeted subset).

### Next task (described, not started)
**Named sensitivity hooks** — add `SensitivitySpec`s for the unmapped economic
drivers (`cost_millions`, `duration_years`/timing, a `commercial_inputs.pricing`
price/WAC/g2n bar, `commercial_inputs.patient_pool.addressable_k`, possibly
SG&A/COGS) with an explicit `defaulted_field → spec` provenance linkage as the
contract. Blast radius: tornado regression fixtures, charts, memo templates,
`valuation.json`. No partial materiality ranker unless loudly labelled partial.

---

## Part 2 — Science Thesis layer, Phases 1–10 (`science-wip/evidence-workflow`)

A separate Layer 0 subsystem: a **deterministic, heuristic** science thesis that
feeds POS and BD workflows. It is **not calibrated**, makes **no network calls**,
and (except the optional Phase 6b extractor) uses **no LLM**. Design principle:
*missing evidence → lower confidence → diligence question → next readout.* It must
never fabricate PK/PD, biomarker validation, human proof-of-concept, clinical
meaningfulness, or buyer fit.

**Durable decision:** one shared `ScienceThesis` powers two modes —
*Discovery/Investment* (what must be true? → belief update → POS/rNPV impact) and
*BD* (buyer-defined gates → diligence), with different entry points and gates.

### Phase map

| Phase | Theme | Key modules |
|---|---|---|
| 1 | Layer 0 models + deterministic scoring contract (thesis separate from POS modifier) | `intelligence/science_thesis.py`, `models/science_score.py` |
| 2 | Deterministic builder — populate the contract from asset context (boring/honest: absent evidence → gaps) | `intelligence/science_thesis_builder.py` |
| 3a/3b | Surface Science Thesis + BD Fit in memos, watchlist, and CLI | `cli` wiring (`--science-thesis`, `--apply-science-pos-modifier`, `--buyer-problem[-id]`) |
| 4 | Compact JSON-safe Science/BD summaries for audit & replay ("persist what users saw") | `intelligence/science_thesis_summary.py` |
| 5 | Structured evidence landing zone — typed `ScienceEvidenceItem`/`Bundle` + conservative adapter | `intelligence/science_evidence.py` |
| 6a | Deterministic extractor mapping existing structured repo objects → bundle (mapper, not interpreter) | `intelligence/science_evidence_extractor.py` |
| 6b | LLM schema-filling extractor behind the bundle schema (may extract, may not score/modify POS) | `intelligence/science_evidence_llm_extractor.py` |
| 7 | Wire the 6b extractor into document replay / ingestion (no new science logic) | (replay/ingestion wiring) |
| 8 | Evidence artifact persistence — replayable/auditable JSON (`schema/extractor/prompt` versions, `document_hash`, hash-policy warn/fail/ignore) | `intelligence/science_evidence_artifact.py` |
| 9 | Compact evidence surfacing — counts, top snippets, rejected/ambiguous, gaps (full tables stay in artifact JSON) | `intelligence/science_evidence_surface.py` |
| 10a | Outcome diagnostics — retrospective taxonomy (`target_pathway_failure`, `exposure_dose_failure`, `biomarker_translation_failure`, `efficacy_failure`, `safety_failure`, `commercial_strategic_failure`, `success`, `unknown`); `ScienceOutcomeRecord`, `ScienceDiagnosticsReport` | `intelligence/science_outcomes.py` |
| 10b | Calibration readiness hooks — `evaluate_calibration_readiness(...)`, `calibration_status=heuristic`, `weight_update_allowed=false` | `intelligence/science_calibration.py` |

### Cross-phase guardrails
- Diagnostics are retrospective only; production weights are never mutated.
- Recalibration requires a separate review phase — small-sample diagnostics alone
  cannot change weights.
- Science failures are kept distinct from commercial/strategic failures.
- Artifact loading must not re-trigger an LLM call, nor directly update POS, BD
  actionability, or the thesis.

### Branch state
Tip `607aac2 feat(science): add evidence artifact diagnostics workflow`. Plans
live in `docs/vision_reports/science_thesis_layer_phase{1,2,4,5,6a,7,8_10}_plan.md`
and `docs/science_thesis_workflow.md` on that branch. **Not yet merged into
`core-engine-v1`** — `core-engine-v1` carries only `science_engine.py` and
`models/science_score.py`.
