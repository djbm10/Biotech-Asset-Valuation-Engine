# TARGET_COMPONENT_IDENTITY_CERTIFICATE v1

Preregistered source-readiness audit; **G0 failed, implementation not started**.
See `results/README.md`, `results/component_table.md`, and
`results/minimum_source_contract.md`. Existing behavior is unchanged.

Population and input hashes were committed before the full audit. No new authority
was acquired. Forty-eight components include all nine implicated groups, and all 86
blocked query proposals were evaluated at explicit gene-identity granularity.

Reproduction from the repository root, with the adopted external sidecar/raw artifacts
available at their frozen paths:

```bash
PYTHONHASHSEED=0 PYTHONPATH=src python research/se_target_component_identity_certificate_v1/audit.py
PYTHONHASHSEED=0 PYTHONPATH=src python research/se_target_mention_role_decision_v1/verify_baseline.py
ruff check --no-cache src/bve/se tests/se research/se_target_component_identity_certificate_v1
```

The audit writes only `/tmp/component_certificate_audit`. Keep that directory reserved
for its generated audit files: its hash manifest covers the audit output directory.
Seeds 0, 1 and 42 produced identical hashes; the frozen comparison is in
`results/determinism.json`. Canonical JSON uses sorted keys, fixed gzip mtime and sorted
source locators. The baseline verifier writes `/tmp/role_baseline_check.json`.

The 35 gene-ID conflicts do not imply that all mature protein products differ. The
certificate's identity unit must be resolved explicitly before any protein-level inference.
Source-record grouping and punctuation do not certify a biological complex or fusion.
