# Lead verification v1 — prospective bounded plan

Base: e270a4a. User-authorized named follow-up, separate from discovery v1.
No discovery rescoring, new discovery credit, gate decisions or validation promotion.

## Change request

lane: 4; cross_lane: false; core_output_changed: false; backward_compatible: true;
requires_migration: false; feature_flag: null.
Scope: new research evidence ledger and analyst handoff; reporting-only support using existing
Assessed/Source status types where useful; tests and a diagnostic of the existing alias timing
benchmark. Production identity, nomination, gates, PoC and ranking rules stay unchanged.
All rNPV/POS/M&A/watchlist/historical replay outputs unchanged. Engineering review under user
authorization; no clinical sign-off implied. Rollback only these additions/verified test-isolation
fix; preserve source receipts and diagnostics. Focused tests, full tests/se and Ruff required.

## Evidence protocol and success criteria (before new follow-up searches)

Two fixed subjects: HXN-1031 and cizutamig. Named queries are deliberate verification,
not independent discovery. User-provided UCB format/acquisition/date leads are hypotheses.
Seek primary issuer disclosures, CT.gov protocol records and medical abstracts. At most
12 search queries and 20 distinct primary documents/API responses; sequential bounded HTTP,
2 MiB/page, 20-second read timeout, no paid APIs or full engine replay. Record failed access,
URLs, observed dates, published/updated dates, hashes and exact evidence pointers. Preserve raw
public pages locally, publish paraphrases/short excerpts and metadata only.

Before/after comparison is a manual two-case evidence audit, not estimated accuracy or recall.
Success: each material claim in final handoff has a primary citation or explicit UNKNOWN;
separate identity/format, maturity, approval, company relationship, territorial rights and
availability. Specifically do not infer ownership from sponsorship, non-approval from absence,
clinical entry from preclinical models, or efficacy/PoC from safety observations. Acquired-company
status must not imply independently available asset or universal rights. HXN remains a preclinical
research lead unless primary contrary clinical evidence is identified (flag any conflict).
No unsupported material claim, comparator promotion or retrospective discovery credit permitted.
Independent BD usefulness/time assessment remains OUTSTANDING unless a real reviewer is available.

## Regression diagnosis

Observe elapsed wall/CPU and GC time/counters around existing 250/2000 construction workloads.
Compare fresh process versus suite-like retained state and targeted predecessor tests. If evidence
identifies unrelated GC/process state contaminating the microbenchmark, isolate benchmark workload
without changing sizes, ratio or absolute thresholds. Do not alter resolver semantics or claim
an algorithmic fix without profiling evidence. Keep diagnostic results including failures.
