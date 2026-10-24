# Shared-alias timing regression investigation

## Finding and limits

**Verified confound: the benchmark measured unrelated whole-process cyclic garbage collection.**
It timed resolver construction with GC enabled in whatever heap state earlier tests left behind.
A process retaining the installed ontology (78,378 canonical entities) spent 3.870 seconds in GC
inside a 3.892-second small construction. The same construction without a collection took about
0.02 seconds. This cost depends on retained process state, not the synthetic sharing-group size.

The original two failures (5.031 s and 4.656 s for the large case) were uninstrumented. Their
exact GC events cannot be reconstructed. The corrected ordered-prefix diagnostic **did not
reproduce the failure**: it passed, with 0.144 s of GC inside the 0.172 s small case and 0.022 s
of GC inside the 0.290 s large case. Instrumentation and the added reporting tests can shift GC
scheduling. Do not describe this as a captured trace of the original failure.

Evidence supports process-state contamination as the explanation, with no evidence of quadratic
resolver work in these controls. It does not prove that every historical timing excursion had
only that cause. CPU time closely tracked wall time in the probes, so scheduling contention was
not the dominant measured cost. Installed ontology contents, GC timing and process state matter.

## Controlled observations

| Process / mode | Small (250) | Large (2,000) | Interpretation |
|---|---:|---:|---|
| Fresh process, normal GC, first repeat | 0.025 s | 0.168 s | Pass |
| Retained ontology, normal GC, first repeat | 3.892 s (3.870 s GC) | 0.178 s | Collection falls on small case; ratio can conceal contamination |
| Retained ontology, GC disabled, three repeats | 0.021–0.029 s | 0.179–0.208 s | Roughly proportional construction work |
| Original suite order through benchmark, instrumented | 0.172 s (0.144 s GC) | 0.290 s (0.022 s GC) | Pass; expensive full-heap collection did not land on large case |

Full per-measurement summaries: diagnostic_summary.json and ordered_prefix_diagnostic.json.
Raw callback traces, original probe source and logs remain under ignored raw/diagnostics/, with
hashes in the summaries. The earlier faulty diagnostic hook is recorded in VALIDATION.md.

## Narrow fix

Only the measurement helper in tests/se/test_ontology_resolver.py changed to
`timeit.timeit(lambda: self._shared(count), number=1)`. Python 3.11's standard timeit disables
cyclic GC during the timed interval and restores its previous enabled state afterward. Reference
count cleanup still occurs. Construction sizes remain **250 and 2,000**, and the assertion remains
**large < max(small * 24.0, 0.5)**. No relaxed threshold, repeated-minimum selection, skip, xfail,
resolver change, identity rule or scientific gate change.

This isolates algorithmic scaling from an unrelated retained heap. It is not a production memory
optimization: production GC and resident ontology costs remain real. It makes no claim that the
full source-coverage replay fits this laptop. The existing flag-content test remains unchanged.

## Reproduce diagnostics (sequentially, from repo root)

These commands document work, not a request for the user to execute it. Use fresh output paths.

```bash
.venv/bin/python research/se_lead_verification_v1/diagnose_alias.py > /tmp/alias-fresh-new.jsonl
.venv/bin/python research/se_lead_verification_v1/diagnose_alias.py --ontology > /tmp/alias-retained-new.jsonl

env PYTHONPATH=research/se_lead_verification_v1:src \
  BVE_GC_DIAGNOSTIC_OUTPUT=/tmp/alias-ordered-new.json BVE_GC_STOP_AFTER=1 \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -m pytest tests/se -q -p diagnostic_pytest
```

The standalone probe times the unchanged `_shared` workload directly, including normal-GC controls.
The pytest probe wraps the current benchmark: after this fix, timed construction should record no
cyclic GC callbacks. To inspect pre-fix evidence use the retained traces; do not modify scientific
artifacts or reset the working tree. Numeric timings are machine/process dependent.

## Validation

- Corrected diagnostic hook isolated check: 2 passed.
- Ordered prefix, before fix: **1,194 passed, 806 deselected, 3 xfailed** in 1,034.88 s.
- After fix, focused reporting/triage/ontology tests: **83 passed** in 2.51 s.
- Ruff on new code and changed tests: passed.
- Final full tests/se without diagnostic plugin: **2,000 passed, 3 xfailed**, one existing
  synthetic-fixture trial-universe warning, in **2,017.75 s (33m 37s)**. The timing test passed
  in full-suite context. This long duration is reported as observed, not a performance improvement.
