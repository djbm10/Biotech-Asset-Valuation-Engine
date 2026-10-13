# AUTHORITY_ASSERTION_PROVENANCE_SIDECAR v1

Preregistration 0bb2e7a; red tests f634e8e; isolated implementation 2f74f93.
`schema.md` defines the additive artifact. `expected.json`, `synthetics.json`,
`raw_witness_records.json`, `preflight.json` and `input_hashes.json` were frozen before
implementation. Historical audit remains unchanged at 5aa8fdd/2a86312.

Full generated artifacts are retained outside git:
`/home/djmann/se_runs/authority_assertion_provenance_sidecar_v1/seed0/`
and independently regenerated in sibling `seed42/`.
Committed result receipts bind these artifacts by SHA256. Large original shards and
sidecar JSONL files are intentionally referenced rather than copied into git.

Reproduce sequentially from repository root, with retained original source paths:

```bash
PYTHONHASHSEED=0 PYTHONPATH=src python scripts/build_authority_assertion_sidecar_v1.py --output /tmp/authority-sidecar-seed0
PYTHONHASHSEED=42 PYTHONPATH=src python scripts/build_authority_assertion_sidecar_v1.py --output /tmp/authority-sidecar-seed42
```

Compare manifest.json files and verify the listed artifact hashes. No live calls occur.
The builder requires the three frozen Parquet source artifacts, pyarrow and the unchanged
accepted snapshot. Source hashes are also bound by the accepted snapshot manifest.
Separate ChEMBL release databases cannot replace missing original API payloads.

Decision neutrality uses the unchanged frozen 6,199-case baseline generator at
`research/se_target_mention_role_representation_v1/freeze_baseline.py` under seed 0.
Its output in `/tmp/mention_v1/baseline.json` must match the committed baseline exactly.
Full tests/se and required Ruff are independent adoption gates, recorded in results.

No target-role or alias-expansion implementation is included. Human-PoC stopped;
H21–H25 untouched and H6–H10 unrun.
