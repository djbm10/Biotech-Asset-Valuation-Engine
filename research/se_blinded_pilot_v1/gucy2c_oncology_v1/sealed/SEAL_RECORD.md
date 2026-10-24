# Seal record (written before any reference exists)

- Engine run: `se:d710e7c8-c9ce-43a7-80ab-6fb08a36bf8a`, engine commit `e909f4d4e167ef24e47bccc74fa2a140758e76da`.
- Launched 2026-10-24T20:53:17Z, ended 21:52:10Z (58 min 52 s wall), peak RSS 3.33 GB
  (cap 4 GiB), exit code 2.
- Engine status: **INCOMPLETE**, not promoted. ClinicalTrials.gov (483 queries, 630 records)
  and PubMed (483 queries, 11,694 records) delivered. Seven required families (company
  pipeline, company press release, AACR, ASCO, ASH, EHA, SEC EDGAR) had no configured
  connector in this invocation (no `--source-index`), so each made one failed attempt.
- Candidates: 5,984 total = 0 eligible, 474 review, 571 excluded, 4,939 low-support.
- Per protocol this run is scored as is. Candidates were produced, so no retry.

## Two sealed views

1. **Official** (`receipt.json`, candidates sha256 `e7aae615…`): `bve-se-pilot export`
   unchanged, all 5,984 candidates. This is the preregistered measurement.
2. **Secondary, declared here before the reference exists** (`receipt_review.json`,
   sha256 `ebd01745…`): the same export filtered to the engine's own review population
   (eligible ∪ unresolved ids = 474). Rationale: the exporter does not apply the engine's
   own exclusion and low-support routing, so the official view measures the raw candidate
   pool, not what an analyst would be shown. Both are reported; neither replaces the other.

Large artifacts (result.json 248 MB, candidates.json 10 MB, custody) stay outside the repo at
`~/se_runs/gucy2c_pilot_v1/`; their hashes are in the receipts.
