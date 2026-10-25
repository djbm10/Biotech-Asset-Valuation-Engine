# Seal record (written before any reference exists)

- Engine run `se:56d01728-11fc-4f38-9cd5-bd599331a106`, engine commit
  `dacbca2a8a14ff8106f38b79d8b6a739dfd3ad44`, with `src/` identical to `fcfefe3`.
- Launched 2026-10-25T18:50:53Z and ended 18:54:14Z: 3 min 21 s wall, peak RSS 2.02 GB
  (cap 4 GiB).
- **Exit code 3: the engine reported acquisition FAILED, "UNSCOREABLE, not promoted".**
  - ClinicalTrials.gov: 45 queries SUCCESS, **1 FAILED**. A pass-2 follow-up query was built
    from a whole trial-arm label (parentheses and commas included). CT.gov answered HTTP 400
    on all 3 attempts. This is a deterministic query-construction defect in the engine, not
    an infrastructure fault, so a rerun would reproduce it.
  - PubMed: 35 SUCCESS, 11 NO_EVIDENCE_FOUND.
  - NOT_CONFIGURED, as preregistered: company pipeline, company press release, AACR, ASCO,
    ASH, EHA, SEC EDGAR.
- The engine still wrote a complete `result.json`: 442 candidates = 25 eligible, 49 review,
  149 excluded, 219 low-support.
- Candidates exist, so under the protocol there is **no retry**. The run is scored as is and
  reported as **INCOMPLETE (one mandatory CT.gov query failed; seven families not
  configured)**. The engine's own status, FAILED/UNSCOREABLE, is reported alongside, not
  overridden.

## Two sealed views (the same definitions as the earlier pilots)

1. **Official** (`receipt.json`): all 442 candidates, sha256 `4cb71774…2da5333`.
2. **Review population** (`receipt_review.json`): eligible ∪ unresolved (74), sha256
   `20783cc8…56660f47`.

Kept outside the repo, at `~/se_runs/il3ra_pilot_v1/`:
- `result.json` (sha256 `198bc9e4…6be8152a`);
- both candidate exports;
- custody;
- snapshots.

This commit contains no candidate name.
