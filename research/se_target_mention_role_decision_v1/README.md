# Target mention-role decision v1 preflight

Design stopped before implementation: exact match lineage does not certify the identity
of a multi-source resolver component. See the policy document for the finding and minimum
next interface. This is not a preregistered implementation result.

Artifacts are diagnostic proposals, not approved target deltas. Gzip files contain canonical
JSON, compressed with `mtime=0`; `artifact_hashes.json` pins them. All inputs are existing
frozen authority/development artifacts. No holdouts or live sources were used.

Reproduce from the repository root with `PYTHONPATH=src` and `PYTHONHASHSEED=0`:

1. `python research/se_target_mention_role_decision_v1/probe_whole_role.py`
2. `python research/se_target_mention_role_decision_v1/audit_components.py`
3. `python research/se_target_mention_role_decision_v1/verify_baseline.py`

The captured scripts retain their original `/tmp/role_*.json` output locations and the
installed adopted sidecar paths under `/home/djmann/se_runs/`; run sequentially. They do
not modify production files. Use the same frozen snapshot and sidecar as representation
v2. `input_hashes.json` records the relevant inputs. The probe uses sidecar-index metadata
checks; raw component verification streams the adopted assertion gzip directly.

`candidate_component_audit.json.gz` retains every proposed whole-slot case, its exact
matching assertions, component membership, and raw approved-symbol assertions.
`multiple_source_components.json` is the readable nine-component summary.
`source_examples.json.gz` contains six complete raw assertion records for three examples.
`baseline_check.json` records the independent full frozen decision comparison.
