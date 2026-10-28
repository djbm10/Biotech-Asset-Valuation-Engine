# DealScreen readiness scorecard

The same 15 dimensions every cycle. No numerical readiness score. Status values:
DEMONSTRATED, PARTIAL, NOT DEMONSTRATED, BLOCKED. Evidence is internal development unless
stated otherwise.

## Scorecard as of Audit 0 (2026-10-28, before Cycle 1)

| # | Dimension | Implemented | Known defects | Evidence | Status | Next improvement |
|---|---|---|---|---|---|---|
| 1 | Landscape ingestion and integrity | CSV/XLSX, mapping profiles, exact row accounting, duplicates, rejections with reasons, manifest | No refresh/diff between exports; one source reference per row (field provenance lives outside the importer) | 200/200 synthetic, 40/40 real; tests | PARTIAL | Refresh diff (Gate I) |
| 2 | Identity reconciliation | Keyed by source ID; shared-code flag; same-company authority merge proposal | Same molecule under a different holder not flagged (HBM9161 / batoclimab); merges cannot be applied | MB-102 test; real run | PARTIAL | Flag cross-holder same-molecule pairs |
| 3 | Screening accuracy and coverage | S&E GateEngine over cited facts | 5/9 in-scope real programs UNRESOLVED; 8/29 out-of-scope UNRESOLVED; indication FAIL never possible | Real assessment (same-author reference) | PARTIAL | Close unknowns in-tool (dim 5) |
| 4 | Source traceability | Row/column claims; agent citations with spans; field provenance in the real builder | Field provenance is not imported into DealScreen; it lives in a side file | Provenance completeness test | PARTIAL | Carry citations on analyst facts |
| 5 | Resolving UNKNOWN decisions | Confirm/reject claims; confirm agent findings | 38/39 real open gates have no in-tool path | `results/manual_actions.json` | NOT DEMONSTRATED | **Analyst fact entry with citation (Cycle 1)** |
| 6 | AI diligence usefulness | Offline library + public CT.gov provider; proposals only | Narrow pattern extraction; misses approval statements; 1 useful real finding | Real run | PARTIAL | Approval/status extraction |
| 7 | Ownership, rights, licensing | Rights status from vendor text; silence = UNKNOWN | No rights-holder concept; U.S. label not used; all 40 real UNKNOWN | Real run | NOT DEMONSTRATED | Rights-holder vs availability model |
| 8 | Buyer strategy and capability | BuyerProblemV2 hard gates; capability modalities as a preference | Capability constraints untested on real data | Synthetic only | PARTIAL | Later |
| 9 | Ranking | Declared lexicographic preferences within a disposition | No evidence-strength or rights component | Tests | PARTIAL | Not the bottleneck |
| 10 | Review and approval | Hash-chained log; HUMAN / SYNTHETIC / AI_PREPARED kinds; limits | No real human has used it; no UI beyond CLI and Excel | Tests | PARTIAL | Gate H needs a person |
| 11 | Financial readiness and correctness | Readiness checklist; scenario-order check; reconciliation tests; deal prototype | No stage check: marketed products could be valued pre-approval; deal CLI awaits Lane 1 sign-off | Audit + tests | PARTIAL | Block commercial-stage pre-approval valuation |
| 12 | Excel and report quality | 8-sheet companion workbook, memo, honest labels | Not reviewed by a user | Generated files | PARTIAL | User feedback |
| 13 | Performance and reliability | Synthetic demo 66 s, real import/screen ~50 s each | ~30 s and 1.7 GB per CLI call from ontology loads | Timed runs | PARTIAL | Cache or optional ontology |
| 14 | Security, licensing, integration | License metadata required in profile; public-only data | No security review; no licensed connector | — | NOT DEMONSTRATED | Blocked on approvals |
| 15 | Real-world validation | Real public landscape, same-author reference | No human user; no independent reference | — | NOT DEMONSTRATED | External dependency |


## Scorecard after Cycles 1-2 (2026-10-28)

Only the dimensions that changed are listed. Everything else is as in Audit 0.

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 2 | Identity reconciliation | Cross-holder same-molecule pairs flagged (review only); MB-102 class still isolated | Real: 2 batoclimab licensee/code pairs flagged; tests I1-I3 | PARTIAL (merges still cannot be applied) |
| 3 | Screening accuracy and coverage | With 9 cited actions, in-scope resolved 4/9 → 7/9, 0 wrong | `cycle1/assessment_after.json` (same-author reference; simulated analyst) | PARTIAL |
| 4 | Source traceability | Analyst assertions carry URL, title, date and verbatim quote, and are listed with their gate effects | Tests C4, C7 | PARTIAL → stronger |
| 5 | Resolving UNKNOWN decisions | In-tool path for 39/39 open gates; retract restores the screen byte-for-byte; every gate change disclosed | Tests C1-C7 + 9 review regressions; real run | **DEMONSTRATED (technically; no human has used it)** |
| 7 | Ownership, rights, licensing | Rights assertions need a quote stating the status; AVAILABLE + partnership → CONFLICTING even when confirmed (bug fixed) | Tests | NOT DEMONSTRATED (no real rights data) |
| 11 | Financial readiness and correctness | Commercial-stage programs blocked from pre-approval rNPV | Real: nipocalimab blocked; tests V1-V2 | PARTIAL → stronger |

**Gate status:**
- **Gate C:** technically demonstrated. Supported unknowns are resolved in-tool with evidence preserved and decisions recalculated. It is **not** demonstrated with a human, and analyst time is unmeasured.
- **All other gates:** unchanged.

**After Cycle 3:**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 7 | Ownership, rights, licensing | U.S. rights holder kept separate from availability. Holder taken only from cited evidence (FDA labeler, or an assertion); conflicts shown | Real: holder known for 8/40, AVAILABLE 0/40; tests R1-R5 | PARTIAL (no availability data; no licensor/licensee extraction) |

- **Gate D:** PARTIAL. Suitability, marketing status, holder, encumbrances and unknown availability are now distinct fields. Actual licensing availability has never been demonstrated, because no public source in hand states it.

**After Cycle 4:**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 13 | Performance and reliability | Ontology loaded once at import; screens run from a target cache, and fall back to the full path when a decision introduces an uncached target or the ontology changed | CLI screen 33.5 s / 1.7 GB → 0.53 s / 88 MB; byte equality on 4 workspaces | PARTIAL → stronger (import still ~25-50 s) |

**After Cycle 5 (and the review fixes):**

| # | Dimension | Change | Evidence | Status |
|---|---|---|---|---|
| 1 | Landscape ingestion and integrity | Re-import is a refresh: previous import archived; diff of assets and values with source and date; decisions checked | Tests F1-F5 + 6 review regressions | PARTIAL → stronger (no vendor-style refresh tested on real data) |
| 10 | Review and approval | Decisions survive reordered refreshes; changed-value decisions orphaned and reported, never transferred; decided assets with changed content flagged | Reproduced regression now passes | PARTIAL |
| 7 | Ownership, rights, licensing | Holder wording corrected to "U.S. labeler per FDA label; not a rights statement" | Review M1 | PARTIAL |

- **Gate I:** PARTIAL. Refresh comparison works on reordered and edited public exports. It has not been tested with a real vendor export.
