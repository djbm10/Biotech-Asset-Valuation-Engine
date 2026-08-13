PDCD1_BENCHMARK_REBASE_V1_MILESTONE_5_CANDIDATE_IDENTITY_ADJUDICATION_FINALIZED

Snapshot: `f26fd47e34ab97badde4e2ae`
Branch: `artifact/pdcd1-rebase-v1-candidate-identity`
Release: https://github.com/djbm10/Biotech-Asset-Valuation-Engine/releases/tag/pdcd1-rebase-v1-candidate-identity-f26fd47e34ab97badde4e2ae
Tag: `pdcd1-rebase-v1-candidate-identity-f26fd47e34ab97badde4e2ae`

Milestone 5 was built from frozen Milestone 4 snapshot `d933fec9aaeecd2df64884b6` only. No new external research exceptions were used.

Artifacts:
- Snapshot directory: `artifacts/pipeline/pdcd1_rebase_v1/stages/05_candidate_identity_adjudication/f26fd47e34ab97badde4e2ae/`
- Canonical candidates: `candidates/canonical_candidate_ledger.jsonl`
- Alias/development-code bindings: `aliases/alias_development_code_ledger.jsonl`
- Subject mapping: `subjects/subject_candidate_mapping_ledger.jsonl`
- Identity boundaries: `boundaries/identity_boundary_ledger.jsonl`
- Conflict resolutions: `conflicts/conflict_resolution_ledger.jsonl`
- Rejected aliases: `aliases/rejected_alias_ledger.jsonl`
- Build A/B comparison: `reproducibility/BUILD_A_VS_BUILD_B_COMPARISON.md`
- Storage status: `export/STORAGE_STATUS.json`

Counts:
- Total subjects mapped: 554
- Total canonical candidates: 224
- Total alias/development-code bindings: 158
- `CONFLICT_UNRESOLVED`: 60
- `DISTINCT_PRODUCT`: 29
- `EXPLICIT_NONCANDIDATE`: 205
- `GENERIC_OR_NONIDENTIFYING`: 0
- `INSUFFICIENT_EVIDENCE`: 11
- `VERIFIED_ALIAS_OF_CANDIDATE`: 158
- `VERIFIED_CANONICAL_CANDIDATE`: 91

M4 conflict handling:
- M4 conflict subjects: 76
- Resolved from frozen identity evidence: 16
- Left `CONFLICT_UNRESOLVED`: 60

Build A vs Build B:
- Subject coverage: 554/554 in both builds
- Agreement: 554/554, 100.0%
- Reconciliation ledger: present at `reproducibility/reconciliation_ledger.jsonl`; empty because no subject-level identity/candidate disagreements remained.

Validation and publication:
- M5 validator against local snapshot: `overall_pass: true`
- M5 mutation suite: 10/10 passing
- `py_compile`: passing for new scripts/tests
- `ruff check`: passing for new scripts/tests
- M4 validator against frozen M4 snapshot: `overall_pass: true`
- Release archive: `pdcd1-rebase-v1-candidate-identity-f26fd47e34ab97badde4e2ae.tar.gz`
- Release archive sha256: `4a5fcfea340eb06424c2223594094b618b99d5ecfe373d8c5a894f430f31a502`
- Independent release redownload verification: checksum OK, extraction OK, 17 receipt-bound artifacts recomputed with no mismatches, downloaded snapshot M5 validator `overall_pass: true`
- Final post-publication driver run: `ALREADY_FINALIZED` with all-zero counters
