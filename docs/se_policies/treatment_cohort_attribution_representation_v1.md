**FINAL DECISION: FAILED / REVERTED.** Formal R1 and R7 failed; no representation adoption. See [complete result](../../research/se_treatment_cohort_attribution_representation_v1/result/summary.md). The preregistration below is preserved unchanged. Candidate `56513a2` was normally reverted in `98ed522`; source/tests/scripts match `7103da1`. Human-PoC recovery remains stopped pending stronger result-specific evidence.

# TREATMENT_COHORT_ATTRIBUTION_REPRESENTATION v1

## Preregistration — frozen before implementation

Baseline: `7103da1`, clean `m11-identity-graph`. Adopted quantity and treatment
contracts remain unchanged. This milestone adds a typed, inert provenance record
and materializes the already grounded evidence into a research sidecar. It does
not implement a text interpreter, result-arm resolver, quantity binder, efficacy
emitter, identity resolver or pipeline consumer. No live searches or replays;
H6–H10 remain unrun. H16–H20 remain development evidence.

### Architecture and interface

Add `src/bve/se/schemas/treatment_cohort.py`, independent of existing run models.
It may import `StrictModel`; no existing production module may import it in this
milestone. Do not add fields to existing run/result/fact serialization.

`TreatmentCohortAttribution` validates supplied grounded annotations and provides
canonical deterministic JSON. It represents candidate identity (nullable asset
ID for synthetic fixtures, never a fabricated canonical entity), source and
artifact references, exact evidence text, trial context, source-local arm/result
references where actually certified, regimen members, qualifiers and reasons.
Receipt, cohort membership and result ownership each have their own status.
The four relationship types are RECEIPT, REGIMEN_RECEIPT, RESULT_OWNERSHIP and
UNRESOLVED. Validation rejects inconsistent statuses or scope. No confidence
value upgrades an unknown relationship.

Ownership requires an explicit certificate referencing the adopted grounded
ownership audit, actual receipt/cohort membership, result evidence and the
retained scope/qualifiers. The available 15 certificates use explicit prose.
Regimen-component/pooled-component records cannot become ownership records.
Add-on comparison certificates retain background, observational and
non-monotherapy limitations; they are not isolated causal-effect certificates.
An ownership certificate is a supplied proof object, not a conclusion drawn
automatically from receipt, arm presence or trial ID. Validation checks structure
and provenance consistency, not the scientific truth of arbitrary new annotations.

An arm label, if represented, must carry trial and source-version provenance;
result-group identity is separate and never automatically equated to an arm.
No frozen row has a certified result-to-arm mapping, so those references stay
null. Captured registry context remains available through the immutable adopted
audit references. This does not manufacture a structured-result certificate.

Smallest interface: `TreatmentCohortAttribution.model_validate(grounded_record)`
and `canonical_json()`. A research-only materializer translates frozen manual
annotations to records. There is no automatic treatment→cohort resolver and no
downstream consumer. This is an architectural representation adoption, not a
human-PoC behavior adoption or a new scientific validation result.

### Frozen population and expectations

Packet: `research/se_treatment_cohort_attribution_representation_v1/`.
`expected_representation.json` freezes all 33 adopted audit rows and 65 existing
negative controls, one record per frozen occurrence, without deduplication.
Every row references its exact immutable audit/control and original witness
text. `reader_baseline.json` freezes direct current-reader outputs for these
98 inputs; `protected_files.json` freezes every existing tracked src/tests/scripts
file; `run_baseline.json` freezes the seven original result-file hashes.
`freeze.json` seals these files before implementation. No production result is
rewritten and no manually expected design decision replaces a reader baseline.

| Population | RESULT_OWNERSHIP | RECEIPT | REGIMEN_RECEIPT | UNRESOLVED |
|---|---:|---:|---:|---:|
| 33 adopted witnesses | 15 | 0 | 11 | 7 |
| 65 attribution negatives | 0 | 13 | 15 | 37 |
| Total | 15 | 13 | 26 | 44 |

Negative controls with explicit actual recipient/treatment or on-treatment
clinical context retain receipt only. Negative regimen examples retain component
receipt, including serial lists and alternative corticosteroids. Remaining
controls lack a certified link to the relevant actual human outcome cohort and
remain unresolved. Their original ownership expectations remain negative even
where receipt is supported; this does not redefine efficacy ontology or repair
cross-sentence reader behavior. All labeling is manual, preimplementation and
traceable, not a phrase lookup embedded in production code.

Among the 14 unresolved clinical-content positives: nine REGIMEN_RECEIPT, five
UNRESOLVED, zero RESULT_OWNERSHIP. The source audit supplies their individual
reasons; no new identity or intervention link is inferred.

### Measurable acceptance checks

- **R1:** exactly 98 records; IDs, relation, all three statuses, candidate,
  regimen, scope, qualifiers and evidence match frozen annotations, 98/98.
- **R2:** all 83 non-owning records serialize UNKNOWN ownership and no ownership
  certificate. Mutation tests reject receipt→ownership status/enum upgrades
  lacking a certificate and reject inconsistent receipt/cohort statuses.
- **R3:** all 65 negative expectations serialize non-owning. Do not demand that
  the unchanged reader reject C056; it must reproduce its baseline output.
- **R4:** 98/98 record references verify against file SHA256 and JSON pointers;
  text evidence matches the referenced exact field. Original snapshot provenance
  is retained for publication witnesses and verified when present. Synthetic
  fixtures remain explicitly synthetic. No invented trial/result-arm links.
- **R5:** all component/pooled records remain non-owning; validation rejects
  ownership with component/pooled scope even if supplied an ownership certificate.
  Add-on certificates preserve all frozen qualifiers. Regimen alternatives stay
  alternatives, not an assertion that both drugs were received.
- **R6:** two materializations and JSON round trips produce byte-identical
  canonical records, IDs and order. No timestamps, random IDs or mutable model
  state influence output.
- **R7:** all 98 reader outputs are byte/canonically identical to baseline;
  all seven original result files retain their SHA256; all existing production
  files retain their SHA256. Thus human_poc_present, evidence.human_poc gates,
  shortlist membership and ranking remain unchanged. Existing integration tests
  must also pass. This proves neutrality of an unconsumed sidecar, not a replay
  of the engine or evaluation of a new efficacy policy.
- **R8:** no existing src/tests/scripts files change; only the new isolated
  schema, its tests, research packet and policy/handoff documentation are added
  or updated. No production imports or consumer wiring to the new module.
- **R9:** full `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m pytest tests/se
  -q -p no:cacheprovider` passes with only existing xfails. `ruff check src/bve/se
  tests/se research/se_treatment_cohort_attribution_representation_v1/*.py`
  is clean. New schema tests exercise contradictory inputs, missing provenance,
  exact text, immutability, deterministic serialization and regimen safeguards.

Development checks may identify mechanical implementation defects before the
formal acceptance score. Freeze implementation before one formal R1–R9 score.
If that score fails, record it, revert the implementation normally, retain the
frozen evidence/results and update the handoff; no post-result rule adjustment.

### C056 and stop boundary

C056 is the existing serial-regimen reader defect: its current reader emits an
efficacy statement for RX-001. Its representation is REGIMEN_RECEIPT with UNKNOWN
result ownership. Both facts must coexist in this milestone. The sidecar is not
consumed, so faithful representation does not require fixing the reader. If
integration becomes necessary to create the record, stop instead of changing
reader behavior.

After adoption, report counts, each of the 14 unresolved rows and the neutrality
checks. Zero new ownership edges for these 14 means stop further human-PoC
recovery until stronger sources or structured result attribution exist. Do not
invent another attribution rule or open a behavior milestone automatically.
