# SE_VALIDATION_READINESS_REVIEW v1 — **NO-GO; keep H21–H25 sealed**

Rubric frozen at `6f024d4` (`docs/se_policies/se_validation_readiness_review_v1.md`) before evaluation. HEAD at measurement: the commit after `6f024d4`. The verdict is computed by `assess.py` from measured facts; the self-test passes and two builds are byte-identical. No production change; no engine run; H21–H25 not consulted beyond their public freeze; H6–H10 not run. No validation grade is assigned. `VALIDATION_STANDARD.md` defines no S&E gates, and POS thresholds were not applied.

**Verdict:** technical readiness **GO**, scientific readiness **NO-GO**, overall **NO-GO**.

Basis key: **C** current code (measured), **T** current tests, **F** prior frozen validation, **D** diagnostic evidence, **I** inference.

## 1. Readiness table

| Dim | Severity | Result | Measured fact (basis) |
|---|---|---|---|
| D1 human-PoC false evidence | CRITICAL | **FAIL** | Current `efficacy_statements` still accepts both exact frozen false sentences: H18 Tirzepatide (human myotubes) and H19 Sacituzumab Tirumotecan (5% discount rate). `human_poc.py` and `snapshot_cache.py` are unchanged since frozen engine `5feee85` (C, F) |
| D2 target recognition | CRITICAL | **FAIL** | Offline `parse_query`: H16 LAG-3, H18 GLP-1 receptor and H19 TROP2 are recognized; **H17 IL-4Rα and H20 factor XI produce zero TARGET spans → refusal** (C). Greek v2 failed and was reverted (D) |
| D3 qualification | MAJOR | FAIL | `asset_qualification.py` and `registry.py` unchanged since `5feee85`; qualification v2 is source-blocked (C, D) |
| D4 modality | MAJOR | FAIL | Structured `modality_in` on datopotamab's frozen text still returns **PEPTIDE**. `gates/evaluator.py` changed only for target references (C); semantics v2/v3/v4 stopped (D) |
| D5 identity | MAJOR | FAIL | `resolve_identifier` returns None for all six H18/H19 brands; resolver and registry unchanged (C); trade-name diagnosis STOP (D) |
| D6 coverage disclosure | QUALITY | pass | INCOMPLETE status and unconfigured families are preserved in frozen runs (F). **Not re-measured; set by rubric definition** |
| D7 ordering (H16) | QUALITY | fail | `reporting/shortlist.py` unchanged; modality-first `_rank_key` remains (C, F) |
| D8 determinism | TECHNICAL | **PASS** | Byte-identical replays recorded for the last four milestones (D) |
| D9 test health | TECHNICAL | **PASS** | Last full `tests/se`: 1,941 passed, 3 existing xfails, 0 failures (T) |

**Disclosed checker error:** the first D9 measurement read "3 xfailed" as a failure (substring match). It was fixed to word-bounded counts with two new self-test cases before this report; the original NO-GO/NO-GO output is noted here, not hidden.

**Scientific vs technical.** The engine can execute H21–H25 reproducibly. A unit-test pass rate of 1,941/1,941 says nothing about D1/D2: the exact false human-PoC sentences still pass, and two of five exposed queries still refuse.

## 2. Implementation inventory

| Subsystem | State | Production consumer |
|---|---|---|
| Target-reference identity surface (`07d104b`) | **Implemented & adopted** | pipeline, query, compiler, intent, parser, evaluator, acquisition |
| Authority assertion sidecar / target-mention provenance | Implemented, **diagnostic-only** | none (`target_mentions` imported by nothing in production) |
| Modality scope representation + head attachment + appositive rule A | Implemented, **diagnostic-only** | none |
| Modality semantics v2/v3/v4 | **Design-stopped** | none (gating parked) |
| Product-description rule B | Tested & **rejected** | — |
| Greek target orthography v2; target-mention provenance (first attempt); query-identity carry | Tested & **rejected/reverted** | — |
| Human-efficacy context safety v1 (`755e9c1`) | Tested & **rejected/reverted** (rejected both false witnesses; lost 19/162 true claims; 5 criteria failed) | — |
| Therapeutic-product qualification v2; 86 target-component identities | **Source/evidence-blocked** | — |
| Trade-name identity; ESG401 arm nomination | **Design-stopped (diagnosis)** | — |
| BL-M02D1 coverage; NK-construct identity bridge | **Planned/unexamined** | — |

## 3. Failure-status register (H16–H20, exposed development evidence)

| Failure | First proven boundary | Adopted production change since | Status | Strongest evidence | More work justified? |
|---|---|---|---|---|---|
| H16 P@20 0.50 | modality-first `_rank_key` over target-UNKNOWN rows | none | **Unchanged** | frozen `_rank_key` probe (F); shortlist.py unchanged (C) | Yes, quality; preregistered ordering milestone |
| H17/H20 refusals | missing authority aliases (Greek α; "factor XI") | target-reference surface (does not add aliases) | **Unchanged** | zero TARGET spans now (C) | Yes: authoritative alias **source**, not grammar |
| H18/H19 false human-PoC | prose admissibility; no product–endpoint–number binding | none (v1 reverted) | **Unchanged** | both sentences still accepted (C) | **Yes, highest** |
| H18/H19 trade-name duplicates | `_IDENTIFIER_ALIAS_TYPES` (intended) | none | **Unchanged** | `resolve_identifier` = None ×6 (C); diagnosis STOP (D) | Only with a regulator brand→INN source + product relation |
| H19 three NON_ASSET | DRUG typing + experimental arm → STRUCTURED_THERAPEUTIC | none | **Unchanged** | qualification files unchanged (C) | Source-blocked |
| H19 datopotamab exclusion | longest-substring structured modality (`peptide` in linker) | diagnostic scope only | **Unchanged** | `modality_in` = PEPTIDE (C) | Parked (v4: 1/8 recall) |
| H19 ESG401 | nomination reads interventions only | none | **Unchanged** | diagnosis STOP (D) | No (no failure class) |
| H19 BL-M02D1 | absent from all 779 captured snapshots | none | **Unresolved** | (F) | Source coverage; unexamined |
| H19 NK-construct duplicate | no construct-identity bridge | none | **Unchanged** | (F) | Evidence-blocked |

**No H16–H20 failure is demonstrably corrected.** Every adopted change since `5feee85` is either an interface refactor (target-reference) or decision-neutral.

## 4. Validation value

The suite's PASS rule fails any query with a false human-PoC row. The measured D1 failure is the exact defect that failed H18/H19. Two of five H16–H20 queries refused on missing target aliases, and H21–H25 also depend on alias coverage (TSLP, plasma kallikrein, IL-36 receptor, myostatin, factor D). That is inference from the public freeze, not a probe. Spending the last untouched primary suite now would mostly reconfirm known defects and burn independent evidence. **Keep H21–H25 sealed.**

## 5. Prioritized next milestones (ranking only; none opened)

| Rank | Milestone | Why | Evidence quality | P(meet prereg) | Risk / cost |
|---|---|---|---|---|---|
| **1** | **HUMAN_POC_PRECISION_FIRST v1**: admit human-PoC only from structured clinical-result routes, and route prose efficacy sentences to an explicit UNVERIFIED state rather than True (I) | One false row fails a whole query; prose acceptance is the proven route of both failures. Human-PoC presence is not a row-relevance criterion, so lowering its recall costs little shortlist quality, unlike context safety v1, which tried to keep prose recall | High (exact witnesses, 162+59 adjudicated claims exist) | Medium-high: a precision-first contract avoids the v1 recall trade-off | Low code risk; needs explicit analyst-facing disclosure of the recall loss |
| 2 | **TARGET_ALIAS_AUTHORITY_SOURCE v1**: ingest authoritative names (HGNC previous/alias symbols and names, UniProt recommended/alternative names) into the target authority, rather than grammar-derived Greek/abbreviation rules | A source-data improvement beats another regex layer; two of five refusals were alias gaps; Greek v2 failed on grammar-derived collisions | High for the defect class; authoritative inputs are identified | Medium | Ontology rebuild; must re-run collision controls; holdout targets must not be inspected |
| 3 | **REVIEW_ORDERING_TARGET_EVIDENCE v1** (H16): order target-supported rows ahead of modality-only matches | Precision on every query whose reference products lack authority modality | Medium (one exposed query) | Medium | Ranking change; needs a frozen ordering contract |

Lower: trade-name identity (needs a regulator brand source), qualification (source-blocked), modality gating (parked), ESG401 (no failure class), BL-M02D1 (coverage; unexamined).

**Single highest-value next milestone: HUMAN_POC_PRECISION_FIRST v1.** It is the only CRITICAL defect with a measured, unchanged failure that a preregistered, precision-first contract can plausibly close without an unresolved trade-off. Human-PoC recovery was stopped. Reopening it in this precision-first form requires an explicit user decision. This review only recommends it.

## 6. Conflicts recorded

- `VALIDATION_STANDARD.md` has no S&E search-engine section; S&E gates live only in the heldout suite policies.
- `VALIDATION_STANDARD.md` lists POS N=99; `CLAUDE.md` says N=145 (refreshed 2026-06-22). This is unrelated to S&E and was not resolved here.
- The "Biotech Tool Context Drive" files are not in this repository and were **not consulted**; conflicts with them are unchecked.
