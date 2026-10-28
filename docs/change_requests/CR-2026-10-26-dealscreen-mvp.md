# Change Request: BVE DealScreen MVP (buyer-specific BD screening workbench)

**Title:** BVE DealScreen: bring-your-own-landscape import, buyer screening, analyst review, valuation handoff, Excel and memo deliverables
**Date:** 2026-10-26
**Requestor:** repository owner (task prompt "BVE DealScreen")
**Status:** DECLARED before implementation code. No sign-offs have been given (see the end of this document).

---

## Classification

```yaml
lane: "4"                      # platform / workflow / review / export
cross_lane: true               # one isolated prototype CLI is adjacent to Lane 1 (see "Lane 1 boundary")
affected_modules:
  - src/bve/dealscreen/                 # new package (Lane 4): import, identity, screening adapter, review, agent, export, memo
  - src/bve/cli/dealscreen.py           # new CLI: bve-dealscreen
  - src/bve/cli/dealscreen_value.py     # new PROTOTYPE CLI: bve-dealscreen-value (valuation boundary, see below)
  - pyproject.toml                      # two console scripts + an optional `dealscreen` extra (openpyxl)
  - examples/dealscreen/                # synthetic demo inputs, ground truth kept separate
  - tests/dealscreen/                   # new tests
core_output_changed: false     # no rNPV / POS / M&A / watchlist / replay output changes
backward_compatible: true
requires_migration: false
feature_flag: null             # new commands only; nothing existing calls them
tests_required:
  - unit: true
  - integration: true
  - backtest_regression: false # core_output_changed is false; reconciliation tests are added anyway
```

## Problem statement

A BD team already holds asset landscapes in Excel exports from commercial providers. BVE can screen
(`bve.se` gate engine) and value (`ValuationEngine`), but it has no way to:
- take that landscape in;
- run the buyer's own requirements over it;
- record analyst decisions;
- hand selected assets to valuation;
- give back an auditable workbook.

The S&E engine's demonstrated failures on live retrieval also matter here, and the importer must not repeat them:
- GUCY2C: attribution and agonist-vs-antagonist mechanism;
- CHEK1: identity splits and composite names;
- IL3RA: the MB-102 false merge of two companies' assets sharing one code, wrong modality labels, and ELIGIBLE resting on registry text rather than a target fact.

## Capability audit (Phase 0)

| Capability | Status | Where |
|---|---|---|
| Buyer problem contract (target expression, modalities, biology, TA, indication, phase, capability constraints, deal routes) | **Reusable** | `bve.se.schemas.contracts.BuyerProblemV2` |
| PASS / FAIL / UNKNOWN gate evaluation with mandatory evidence on PASS/FAIL and review items for UNKNOWN | **Reusable** | `bve.se.gates.engine.GateEngine`, `gates.evaluator` |
| Indication compatibility (positive-only, NCIt authority; never FAIL on registry text) | **Reusable** | `bve.se.ontology.indication_compatibility` |
| Target normalization (HGNC symbols, ambiguity → None) | **Reusable**, heavy (≈30 s, 1.6 GB load) | `bve.se.ontology.targets.normalize_target` |
| Modality vocabulary | **Reusable** | `bve.se.ontology.modality.normalize_modality` |
| Identity edges / merge proposals as contracts | **Reusable** | `IdentityEdge`, `IdentityRelationship`, `IdentityMerge` |
| Row data-quality check | **Reusable** (minimal) | `bve.data.data_quality.DataQualityChecker` |
| CT.gov single-study fetch + normalizer | **Reusable** | `bve.ingestion.clinicaltrials_gov.fetch_study`, `bve.se.universe.ctgov.normalize_study` |
| Valuation from a YAML config, saved `valuation.json` with bull/base/bear | **Reusable** | `bve-asset` (`bve.cli.run_asset`), `ValuationOutput.save_json` |
| Deal economics (upfront, milestones, royalty) in the engine | **Reusable, but only programmatic** | `DealEconomics` via `ValuationEngine.from_program`; **no CLI or YAML path exists** |
| Markdown → docx | **Reusable** | `bve.reporting.export.markdown_to_docx` |
| Vendor landscape import (CSV/XLSX, mapping profiles, provenance, manifest) | **Missing** | new |
| Analyst decision log with versioned, attributable records | **Missing** for S&E (the Lane 3 `DecisionLayer` is for trading decisions) | new |
| Commercial-rights diligence kept apart from scientific eligibility | **Missing** (the gate engine's access gate is a single CONTAINS_ANY over deal routes) | new, outside the gate engine |
| Diligence research agent | **Missing**; LLM extraction exists in `intelligence/` but is Lane 3 and keyed | new, bounded, public-only, offline-capable |
| XLSX export | **Missing**; `openpyxl` was not installed | new, optional extra |
| S&E live discovery, PubMed minting, ranking | **Experimental** (UNVALIDATED; pilots fail precision) | **not used** by DealScreen |
| Paid connectors (Citeline, Cortellis, internal SQL), Vertex systems, web UI | **Out of scope** | none |

Other notes:
- **Document conflict recorded.** `AGENTS.md` "Current State" describes 2026-03 (Sprint 5, 1,071 tests). The repository is far beyond that. `ROADMAP_LOCK.md` does not list `src/bve/se/` or `src/bve/cli/` in any lane.
- **Biotech Tool Context.** The Drive copy is a mirror of an older repository checkout (`.git`, `.venv`, `data`, `Setup`). No governance document newer than the local copies was found.
- **Lane assignment.** DealScreen is classified Lane 4 here, as a workflow and review consumer of `bve.se` gate contracts.

## Proposed solution (minimal scope)

1. **Importer** (`dealscreen.importer`, `dealscreen.mapping`)
   - Reads CSV and XLSX through a YAML column-mapping profile.
   - Keeps the raw row, row hash, source system and external ID, field-level provenance and dataset version.
   - Rejects malformed rows with diagnostics. Exact duplicate rows are collapsed with provenance.
   - Writes a reproducible manifest (input SHA-256, profile hash, counts).
   - Imported values are `SOURCE_PROVIDED` claims, not BVE confirmation.
2. **Identity** (`dealscreen.identity`)
   - One asset per (source system, external ID).
   - Never merges on a shared name or code. A shared code becomes an `UNCERTAIN_RELATIONSHIP` edge and a review item.
   - An optional ontology authority can only *propose* a merge (`IdentityMerge.PROPOSED`). Merges are applied only by analyst decision.
3. **Screening adapter** (`dealscreen.screening`)
   - Maps imported claims to `NormalizedFact`s and runs the **existing** `GateEngine` over a `BuyerProblemV2`.
   - Preferences produce a declared, lexicographic ranking that never changes a disposition.
   - Commercial diligence (ownership, U.S. rights, encumbrances, licensing availability) is evaluated separately:
     - AVAILABLE only on an explicit availability statement;
     - silence is UNKNOWN.
4. **Review** (`dealscreen.review`)
   - Append-only, hash-chained JSONL decision log with reviewer, timestamp, old and new state, and rationale.
   - Explicit actions only. Machine recommendations are stored separately.
   - Finalists are limited to 10 and valuations to 3. Excluded assets cannot be approved.
5. **Diligence agent** (`dealscreen.agent`)
   - A provider protocol, an offline deterministic provider (local evidence files), and a public ClinicalTrials.gov provider.
   - Output is proposed findings with citation, date, span and limitations.
   - Findings never alter decisions until an analyst confirms them.
6. **Valuation handoff** (`dealscreen.valuation_handoff`)
   - Readiness check against analyst-owned assumptions. Any missing input gives NOT READY with a checklist.
   - Writes a standard `bve-asset` YAML config, runs it **as a subprocess** of an authorised CLI, and reads back the saved `valuation.json`.
   - DealScreen never imports or calls `ValuationEngine`.
7. **Deliverables:** an 8-sheet companion workbook (never overwrites an existing file) and a one-page memo.
8. **Demo:** a seeded generator for a 200-row synthetic landscape. Ground truth and the synthetic reviewer fixture are kept in separate files.

### Lane 1 boundary (the one cross-lane element)

`bve-asset` cannot express deal terms. An acquisition-versus-license comparison needs `DealEconomics`, which only `ValuationEngine.from_program` accepts.

**Change:** a new, separate CLI module `bve.cli.dealscreen_value`, labelled **PROTOTYPE**.
- It parses the same YAML through `bve.cli.run_asset`'s own builders.
- It accepts an optional `deal_economics:` block and runs the unchanged engine through `ValuationEngine.from_program`.
- It saves `valuation.json`.

**Unchanged:**
- no model, formula, assumption, PoS calibration or default;
- `bve-asset` itself.

**Required test:** with no `deal_economics` block, the prototype's rNPV and scenarios equal `bve-asset`'s on the same config.

**Approval:** this prototype needs **Lane 1 quant + clinical sign-off** before any non-demo use. That sign-off is unavailable here, so the outputs are labelled "PROTOTYPE valuation path, Lane 1 sign-off pending".

## Impact assessment

| Output | Changed? | Test coverage |
|---|---|---|
| rNPV | no (reconciliation test against `bve-asset`) | `tests/dealscreen/test_valuation_handoff.py` |
| POS | no | the existing suite, unchanged |
| M&A score | no | n/a |
| Watchlist class | no | n/a |
| Historical replay | no | n/a |
| S&E benchmarks, sealed pilots | no (not touched; the S&E suite is re-run) | `tests/se/` |

## Acceptance criteria (frozen before implementation)

| | Criterion |
|---|---|
| A1 | 200 synthetic rows are accounted for: imported, collapsed as exact duplicates, or rejected with a stated reason |
| A2 | The raw source row, source system, external ID and dataset version survive into the workbook's `Landscape` sheet |
| A3 | Gate decisions match the separately stored synthetic ground truth. Mismatches are reported, not tuned away |
| A4 | Two assets sharing a code (MB-102 class) are never merged; a review item is raised |
| A5 | No asset shows U.S. rights AVAILABLE without an explicit availability claim |
| A6 | Scientific disposition and commercial status are independent fields; a scientifically ELIGIBLE asset can have UNKNOWN rights |
| A7 | Every PASS/FAIL cites a claim traceable to an imported field (row + column) or to an analyst-confirmed finding |
| A8 | Approvals need an explicit logged decision; a ranking cannot create one; the log refuses edits (hash chain) |
| A9 | Identical inputs give byte-identical screening output (timestamps excluded) |
| A10 | Funnel counts reconcile: imported = eligible + unresolved + excluded at every stage |
| A11 | An asset missing a required financial input gets NOT READY and no valuation |
| A12 | Valuation numbers in the workbook equal the saved `valuation.json` produced by the BVE CLI |
| A13 | The XLSX opens with openpyxl and contains the 8 required populated sheets |
| A14 | Validation badges (UNVALIDATED / prototype) appear on every deliverable; the S&E suite is unchanged |

## Rollback plan

- Everything is additive. Revert the DealScreen commits, which remove `src/bve/dealscreen/`, the two CLI modules, the two console-script lines, the optional extra, `examples/dealscreen/` and `tests/dealscreen/`.
- No existing module, data store or config is modified, so there is no migration to undo.

## Sign-offs required

| Lane | Sign-off | State |
|---|---|---|
| 4 | engineering | **not given**; not available in this session |
| 1 (prototype valuation CLI only) | quant + clinical | **not given**; the prototype stays labelled and demo-only until given |

No sign-off is claimed. The work goes on a feature branch and is not merged into `master`.

---

## Amendment 1 (2026-10-27): hardening

Lane classification unchanged.

| Item | Module | Effect on outputs | Sign-off |
|---|---|---|---|
| Console summary prints the current trial-design field names | `src/bve/cli/run_asset.py` | none (it crashed before) | engineering (not given) |
| `_validate_config` rejects per-phase `trial_design` keys the builder does not read | `src/bve/cli/run_asset.py` | fail-closed: configs that used to crash now stop with a clear error | engineering (not given) |
| Scenario-ordering check, with BLOCKED display for unexplained ordering | `src/bve/dealscreen/` | display only; engine numbers unchanged | engineering (not given) |
| `types-PyYAML`, `types-openpyxl` in the `dev` extra | `pyproject.toml` | none | engineering (not given) |
| **Proposed, not applied:** migrate RLAY's legacy trial-design keys | `examples/configs/relay_rly2608.yaml` | RLAY base rNPV $65M (silent defaults) → $39M | **Lane 1 quant + clinical, required, not given** |

Evidence: `research/dealscreen_hardening_v1/FINANCIAL_AUDIT.md`.
