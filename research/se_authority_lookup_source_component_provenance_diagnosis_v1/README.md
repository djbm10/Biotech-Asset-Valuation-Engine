# Authority lookup provenance diagnosis v1

Population frozen in 5aa8fdd, before the contract. See the policy document for boundary B.
`audit.json` carries every field-level assertion and full matching component record;
`audit.md` indexes all 124 observations. `validation.json` records 443 raw-field
round-trips and byte-identical audit output in an independent process with hash seed 42.
No production or snapshot changes; full production tests were not rerun.

Reproduce from repository root with PYTHONPATH=src:
`python research/se_authority_lookup_source_component_provenance_diagnosis_v1/audit.py audit /tmp/audit-copy`
after copying population.json to that temporary directory. This reads only the installed
snapshot; compare its digest with freeze.json first. Do not invoke freeze mode against
the committed population. Validate with `python .../validate.py .../research-directory`.
The audit script was formatted after population freeze; selection semantics are unchanged.

Known limitation: current legacy status/basis is observed, not repaired. Lookup assertions
recover snapshot fields, not discarded upstream raw synonym fields or component ownership.
