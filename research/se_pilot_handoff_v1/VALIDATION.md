# Validation record — 2026-10-23

- `.venv/bin/python -m pytest tests/se -q`: **1,981 passed, 3 xfailed**,
  one warning, 748.70 s. This run collected the first five added cases before four further
  handoff cases were added. No failures. Existing expected failures remain expected.
- Final focused regression, including all final code changes and the four subsequent cases:
  `.venv/bin/python -m pytest tests/se/test_pilot_handoff.py tests/se/test_bd_brief.py tests/se/test_bd_triage.py -q`:
  **42 passed**. Final collection has 1,988 cases (1,979 original + 9 new).
- `.venv/bin/ruff check research/se_pilot_handoff_v1 tests/se/test_pilot_handoff.py src/bve/cli/se_bd_brief.py tests/se/test_bd_brief.py`:
  passed.
- Reporting module has **16 pre-existing ISC004 findings**, identical count/rule to HEAD's
  version. `ruff check src/bve/se/reporting/bd_brief.py --ignore ISC004`: passed. No new
  reporting lint failures. One existing CLI import-order issue was fixed.
- Full requested `ruff check src/`: **7,568 existing findings** remain (7,569 before the
  import-order cleanup). No broad formatting/lint rewrite was attempted.
- `bash -n research/se_pilot_handoff_v1/cloud_execute.sh`: passed. Direct invocation without
  authorization exited 2 without starting an arm. No paid VM or arm was launched.
- Focused tests cover changed-byte rejection, manifest path traversal, escaping symlinks,
  nested custody manifests, duplicate-destination refusal, ontology symlink dereferencing,
  byte-preserved snapshots, allowlisted inputs, environment mismatch and authorization refusal.
- Real payload preparation and verification: **16,599 files**, **1,544,183,782 payload bytes**,
  about 1.5 GB on disk. Exact runtime package pins captured. A final payload is prepared after
  commit to bind code_head to the committed implementation; it remains local under /tmp.
- Real baseline preflight: **14,194 sealed snapshots verify**, all four frozen-input hashes
  pass, ontology directories present, disk sufficient. Local RAM **11.5 GB**, correctly
  refused. Before commit, the dirty-source check also correctly refused reporting edits.
- Worklist generated again into `/tmp/bve-analyst-worklist-check-v1`; `cmp` passed for HTML,
  Markdown and JSON against the checked-in report. The test also verifies determinism.
- `git diff --check`: passed. Frozen specifications, reference results, old demonstration
  reports, custody data and validation locks have no diff.

These are software/integrity checks. No cloud environment installation, paid execution,
new scientific recall evaluation, timed analyst task or independent FINAL-output usefulness
review was completed. The old independent PARTLY rating is not upgraded.
