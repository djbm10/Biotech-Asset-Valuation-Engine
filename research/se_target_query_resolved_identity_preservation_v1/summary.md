# TARGET_QUERY_RESOLVED_IDENTITY_PRESERVATION v1 — FAILED

Preregistration **533c699**; unadopted candidate **612c088**. Normal revert follows
this committed failure record. No acceptance amendments or post-result patches.

The 4,704 frozen query parses preserve biological target symbols, operators,
ambiguity and every span's classification/offset/provenance after the declared
reference normalization. All 16 raw resolver controls remain unchanged. The
existing FXI diagnostic compiles five plans for TARGET:F11; bare F11 remains
ambiguous. New focused tests: **14 passed**. Three hash seeds yield identical
intent/problem/plan JSON. Ruff clean for src/bve/se, tests/se and evaluator.

Full tests/se: **1709 passed,
6 failed, 0 errors, 3 skipped/xfail**.
See result.json and full_tests.xml for exact cases.

I8 fails, including the adopted AK/ATPase -> AK6 serialization contract: candidate
returns TARGET:AK6. I6 independently fails: a stubbed FDA connector emits
`description:"TARGET:GAX1"` where its interface expects a biological search term.
A successful discovery plan is not proof of compatibility with all acquisition
consumers. Candidate must be reverted. The shared canonical_id field conflates
ontology identity and literal search vocabulary; the next investigation must
separate these roles across consumers before another implementation.

Human-PoC extractor, ontology resolver and target-attribution source bytes match
baseline. No new aliases were admitted. No live searches, replays or holdout
probes. H21–H25 and H6–H10 remain unrun. Human-PoC recovery remains stopped.

Source reconciliation: connected GitHub branch was 979ba4d, an ancestor 237
commits behind the clean local e4a5b8d at inspection time. The checked Biotech Tool
Context Drive documentation and tests metadata were older; August entity-layer
notes agree that identity joins require identifiers. Targeted searches found no
newer codex handoff or target-query-alias policy. The newer local October frozen
evidence governs. No private advice or meeting preparation files were imported.
