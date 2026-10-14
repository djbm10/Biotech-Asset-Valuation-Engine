# SE_VALIDATION_READINESS_REVIEW v1 — readiness rubric (frozen before evaluation)

Project-level assessment of whether to spend the sealed H21–H25 primary suite (`heldout_validation_suite_v5.md`, frozen and unrun). H21–H25 queries, references and labels are **not** consulted beyond the suite's existing public freeze, and nothing is run. H6–H10 are not run. No production change. The H16–H20 artifacts are used only as exposed development evidence. `VALIDATION_STANDARD.md` has no S&E search-engine gates; its POS/M&A thresholds are **not** applied here. No validation grade is assigned.

## Dimensions and severity

| ID | Dimension | Severity | GO condition |
|---|---|---|---|
| D1 | False scientific evidence (human-PoC) | **CRITICAL** | The H18/H19 false human-PoC acceptance no longer reproduces on current code |
| D2 | Target recognition (exposed H16–H20 queries) | **CRITICAL** (query-level FAIL by the suite rule) | No exposed query refuses for lack of target recognition |
| D3 | Candidate qualification (non-asset admission) | MAJOR | The H19 NON_ASSET admission path has an adopted production change |
| D4 | Product modality correctness | MAJOR | The datopotamab false-modality exclusion is corrected in the gate path |
| D5 | Identity / duplicate consolidation | MAJOR | The H18/H19 duplicate classes have an adopted production change |
| D6 | Source coverage & disclosure | QUALITY | Missing sources are disclosed (INCOMPLETE status preserved) |
| D7 | Shortlist ordering (H16) | QUALITY | The H16 ordering boundary has an adopted production change |
| D8 | Determinism / auditability | **CRITICAL** (technical) | Recent adopted milestones show byte-identical replays |
| D9 | Test health | **CRITICAL** (technical) | The last full `tests/se` has no failures beyond the existing xfails |

## Verdict rule (computed by `assess.py` from measured facts)

- **Technical readiness** = D8 ∧ D9.
- **Scientific readiness:** NO-GO if any CRITICAL scientific dimension (D1, D2) fails. Otherwise CONDITIONAL if any MAJOR dimension fails, and GO only if all MAJOR dimensions pass.
- **Overall:** NO-GO if technical readiness fails or scientific readiness is NO-GO; else the scientific readiness value.
- **Validation value:** if a CRITICAL scientific failure that the suite rule makes decisive (false human-PoC, or target refusal) is still known and unchanged, spending H21–H25 mainly re-confirms a known defect. **Recommend keeping the suite sealed** unless the overall verdict is GO or CONDITIONAL.

Each finding records its basis: current code, current tests, prior frozen validation, diagnostic evidence, or inference. "Changed" means a production code path on the failure route differs from the frozen engine `5feee85` **and** the measured behaviour on the exposed evidence differs. A decision-neutral API with no production importer never counts as a fix.
