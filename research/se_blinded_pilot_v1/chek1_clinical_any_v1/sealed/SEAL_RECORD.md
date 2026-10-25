# Seal record (written before any reference exists)

- Engine run `se:a93f9efc-10fa-40d4-b0e0-db8781af6b2a`, engine commit
  `80a0a0060a3158803e7f14e32788473c44959b6f`. `src/` is identical to `ba9becf`.
- Launched 2026-10-25T16:02:04Z, ended 16:05:10Z: 3 min 6 s wall, peak RSS 2.02 GB (cap
  4 GiB), exit code 2.
- Engine status **INCOMPLETE**, not promoted.
  - Delivered: ClinicalTrials.gov (30 queries, 90 records found, SUCCESS) and PubMed (30
    queries, 5,362 found, SUCCESS, 1 retry).
  - NOT_CONFIGURED, exactly as preregistered (no `--source-index`, no `BVE_SE_USER_AGENT`):
    company pipeline, company press release, AACR, ASCO, ASH, EHA and SEC EDGAR.
- Candidates: 701 in total = 3 eligible, 91 review, 98 excluded, 509 low-support.
- Scored as is under the protocol. Candidates exist, so no retry.

## Two sealed views (the same definitions as gucy2c_oncology_v1)

1. **Official** (`receipt.json`): `se_pilot export` unchanged, all 701 candidates.
   Candidates sha256 `1b14a6d7…8fa45bb2`.
2. **Review population** (`receipt_review.json`): the same export filtered to eligible ∪
   unresolved (94). Candidates sha256 `8b543160…cd970fd0`.

Artifacts stay outside the repo at `~/se_runs/chek1_pilot_v1/`:
- `result.json` (18 MB, sha256 `d862a260…e398fa45bb2`);
- both candidate exports;
- custody;
- snapshots.

This commit contains no candidate name.
