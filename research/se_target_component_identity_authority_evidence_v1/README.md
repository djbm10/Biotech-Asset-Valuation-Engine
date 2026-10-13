# TARGET_COMPONENT_IDENTITY_AUTHORITY_EVIDENCE v1 — ADOPTED

Preregistration `a8938d6`; frozen acquisition/red controls `b37b476`; offline implementation
`1889503`. All S1–S11 pass under their preregistered applicability. Evidence is adopted
independently. **No component identity certificate or target-role decision was implemented.**

## What was acquired

| Authority | Frozen version | Evidence |
|---|---|---|
| ChEMBL | release 37 SQLite; full DB SHA in `chembl_artifact.json` | All 29 previously missing IDs; seven structured control types; complete one-hop typed-relation endpoints |
| HGNC | 2026-10-13 object generation 1791894733877675 | 367 selected approved-gene records with original full-document pointers |
| UniProtKB | 2026_03, 02-September-2026 | 348 exact-accession responses: 345 reviewed, two unreviewed, one inactive |

ChEMBL contributes 332 targets, 341 sequence components, 917 target-component memberships,
2,133 component synonym rows and 625 typed relations (SUBSET OF, SUPERSET OF, OVERLAPS WITH).
Real structural controls include chimeric proteins, complexes, complex groups, families,
protein–protein interactions and selectivity groups. Their constituents remain separate.
Four constituent records are explicitly RNA components of a protein/nucleic-acid complex;
their UniProt accession is NULL/not applicable, and their stable ChEMBL component IDs are
preserved. They are not silently converted to proteins or discarded.

The independent release DB is **not** a reconstruction of the lost historical API responses.
The accepted ChEMBL snapshot, original sidecar and existing canonical mappings remain intact.
New HGNC/UniProt release claims retain their own versions; newer does not mean automatically
preferred. Gene identifiers, protein accessions and complex/relational targets are different
identity levels. A cross-reference is not an assertion of gene/protein equivalence.

## Validation

- 5,102 source records and **1,291,485 field assertions** independently replay exactly to raw
  JSON pointers or original SQLite table/primary-key/column values.
- Two independent builds, seeds 0 and 42, are byte-identical, including IDs and coverage.
- All 917 imported component membership rows match the frozen source rows exactly.
- All 48 previous components and both canonical-ID collision families remain distinct in
  `results/source_claim_comparison.json`. Gene/protein-level claims are shown separately.
- All **6,199** frozen parser/compiler/trial/buyer decisions remain identical.
- Six focused tests pass; Ruff clean. Full tests/se not required/run because no production
  code changed. There is no production parser, resolver, acquisition or shortlist hook.
- Accepted ontology and adopted assertion-sidecar hashes remain unchanged.

For all 86 blocked proposals, coverage is: uniquely supported 0; multi-entity 0; relational 0;
**conflicting 35; ambiguous 51; no evidence 0**. Those query-level diagnostic categories remain
unchanged even though structured source evidence is now available. All 29 legacy ChEMBL
records are typed SINGLE PROTEIN in the independent release; their ingestion grouping does
not certify gene identity. No count was optimized and no permitting certificate was issued.

Twelve historical Ensembl IDs are unmatched in the frozen HGNC complete set. Two UniProt
records are unreviewed and one is inactive. These statuses and raw claims remain explicit;
there is no substitute identity or source fallback. The complete proposed next identity
certificate must preserve these uncertainties, not treat acquisition as equivalence.

## Artifacts and replay

Permanent additive bundle:
`/home/djmann/se_runs/target_component_identity_authority_evidence_v1/`

- `raw/`: immutable source responses, headers, DB row capture, HGNC object, request universe,
  extraction pointers and raw manifest. The 30.5 GB release DB is referenced by full SHA and
  original retained path rather than copied per assertion.
- `seed0/`, `seed42/`: canonical source-record and assertion JSONL gzip, coverage and hashes.
- Repository `results/`: acceptance, baseline proof, source-claim comparison, exact coverage,
  counts, test/lint logs and artifact hashes. `results/validation.json` is the independent
  verifier output; `results/adoption.json` also records isolation, S8 and S11.

Offline reproduction uses the frozen raw bundle, never today's API responses:

```bash
PYTHONHASHSEED=0 python research/se_target_component_identity_authority_evidence_v1/evidence.py \
  --raw /home/djmann/se_runs/target_component_identity_authority_evidence_v1/raw \
  --output /tmp/identity-authority-fresh-seed0
```

Use a new output directory; repeat with seed 42 and compare `hashes.json`. Run `validate.py`
with `--raw`, `--build0`, `--build42`, `--root` and `--output`. It independently reads original
SQLite rows and raw JSON values, checks content hashes and preserves source memberships.
The acquisition scripts record the original routes but must not be used to substitute a
new UniProt release or changed HGNC object for the frozen evidence. Missing or changed
source versions fail the preregistered gates.

## Next milestone

The source prerequisite is now sufficient to **separately preregister
TARGET_COMPONENT_IDENTITY_CERTIFICATE v2**. That study must define identity granularity,
combine old and new claims conservatively, and freeze certificate expectations before
implementation. This adoption does not pre-authorize a gene/protein equivalence inference,
repair a graph edge, add an alias, or implement target-role decision v2.

H21–H25 untouched; H6–H10 unrun; H17/H20 remain development data; human-PoC recovery stopped.
