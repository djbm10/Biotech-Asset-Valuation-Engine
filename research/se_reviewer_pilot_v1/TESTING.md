# Validation record

**UNVALIDATED research display.** Engineering tests are not independent BD or scientific validation.

Base: `5eb941d947f6cbbc18b83851cd5bc3a7f1235192`. All commands used the existing `.venv`.

| Check | Result |
|---|---|
| Initial focused follow-up + brief tests | 38 passed |
| Final reporting regression (follow-up, brief, triage, reporting) | 52 passed in 0.47 s |
| Full `tests/se` regression | 2,015 passed, 3 xfailed, 1 expected coverage warning; 670.75 s |
| Old card serialization / HTML / Markdown | Byte-identical to base for two scaffolds |
| Old full-brief serialization / HTML / Markdown | Byte-identical for five existing fixture cases |
| Two-asset facts vs prior source-backed records | Identical assessed facts, statuses and links |
| Fresh-directory package regeneration | Byte-identical, including manifest |
| Raw historical study/code rules | Unchanged |
| Independent BD review / analyst time | PENDING / not measured |

The full S&E run began before the final reporting-only warning/approval-category guards were
finished. The final 52-test reporting regression includes those edits and the two additional tests;
no scientific modules changed. This timing distinction is retained rather than claiming the broad
run collected the later tests. The two-asset output is unchanged by the final category guard.

Commands:

```bash
.venv/bin/python -m pytest tests/se -q
.venv/bin/python -m pytest tests/se/test_research_followup.py tests/se/test_bd_brief.py tests/se/test_bd_triage.py tests/se/test_reporting.py -q
.venv/bin/ruff check src/
.venv/bin/ruff check src/bve/se/reporting/bd_brief.py src/bve/se/reporting/research_followup.py tests/se/test_research_followup.py research/se_reviewer_pilot_v1/generate.py
```

Ruff is **not globally green**. `src/` has 7,568 pre-existing findings, unchanged from the prior
milestone. The changed-file run contains the same 16 pre-existing ISC004 string-concatenation
findings in `bd_brief.py` as `git show 5eb941d:src/bve/se/reporting/bd_brief.py` checked with the same
configuration. The adapter, generator and new tests pass Ruff; no new findings were introduced.
The comparison used diagnostic code/message counts and inspection of the unchanged source lines.
No unrelated lint cleanup or threshold reduction was performed.

The compatibility comparison imported the base reporting module from `git show` and compared the
current renderer against identical inputs. Existing fixture cases included supported, unresolved,
contradictory, duplicate, excluded and held-back cards. These are engineering invariance checks,
not recall/precision or usability measurements. No frozen experiment was repeated or rescored.

Full log: `full_regression.txt`; final reporting log: `reporting_regression.txt`. The warning
comes from a coverage test intentionally lacking a recorded trial universe; its recall cannot be
shown complete. It was not suppressed. The prior alias timing regression passed in this full run.
