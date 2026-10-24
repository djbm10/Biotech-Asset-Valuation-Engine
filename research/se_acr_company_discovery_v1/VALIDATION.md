# Engineering checks and review

This record concerns the isolated research harness, not scientific gate validation.
Production source, historical studies, sealed artifacts and scientific thresholds are unchanged.

## Checks

- Focused acquisition/custody/study regression: **101 passed in 97.41 s**.
  Command: `.venv/bin/python -m pytest tests/se/test_acr_company_discovery.py tests/se/test_acquisition.py tests/se/test_acquisition_http.py tests/se/test_acquisition_custody.py -q`.
- Final study-only run: **6 passed in 0.34 s**.
- First full `tests/se` run: **1 failed, 1990 passed, 3 xfailed** in 799.75 s.
  The unchanged `TestWidelySharedAlias::test_flagging_does_not_scale_quadratically`
  timing test measured 0.125 s for the smaller case and 5.031 s for the larger case,
  exceeding its 3.011 s bound. No resolver or timing-test code was changed.
- Isolated rerun of both `TestWidelySharedAlias` tests: **2 passed in 0.32 s**.
  This suggests process-state or scheduling sensitivity but does not establish its cause.
- One fresh full regression with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`:
  **1 failed, 1990 passed, 3 xfailed** in 941.09 s. The same unchanged timing test measured
  0.146 s / 4.656 s against a 3.501 s bound. The full suite is **not green**; this timing
  failure remains unresolved. No further full-suite retries, threshold changes or resolver
  changes were made. Both runs emitted the existing synthetic-fixture trial-universe warning.
- Ruff on both new Python modules and the new test: **passed**.
  Repository-wide `ruff check src/` still reports **7,568 existing findings**; production
  source was not edited. This is existing lint debt, not a clean repository-wide lint result.
- `git diff --check`: passed.

## Reproducibility and custody

- Frozen preregistration hashes match. Preregistration was committed before search/implementation.
- Recomputed ranked URL selection equals the saved selection, including exclusions.
- Recomputed nominations from the retained corpus equal sealed nominations exactly.
- Repeated evaluation produces byte-identical `evaluation/results.json`.
- All 41 sealed acquisition files verify. Acquisition code hash matches the implementation
  recorded at run time; runtime HEAD was the preregistration commit.
- Acquired source bytes and complete search responses remain local and Git-ignored;
  published metadata/hashes cannot substitute for those bytes in reproduction.

## Final-output assessment

The implementing agent reviewed the final 740-word brief against the acquired sources,
frozen endpoint and manual evidence-span ledger. HXN-1031 receives preclinical discovery
credit only. CDR111/cizutamig receive no endpoint credit without explicit antibody-format
evidence on the acquired pages. KT501 was already recovered historically. No comparator,
generic construct, human efficacy, ownership or licensing availability is promoted as a success.

This desk audit is **not independent**. Independent BD review and measured analyst time
remain **OUTSTANDING**. A narrow source-recovery endpoint does not validate a clinical
shortlist or establish real commercial opportunities.
