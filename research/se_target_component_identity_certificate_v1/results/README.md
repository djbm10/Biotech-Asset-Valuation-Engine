# TARGET_COMPONENT_IDENTITY_CERTIFICATE v1 — G0 failed

Preregistration **5af5775**. **Stopped before production implementation; not adopted.**
The frozen source-readiness gate fails. No behavioral candidate exists to revert, and
C1–C10 implementation acceptance is not reported as passed.

## Evidence and boundary

The audit covers 48 frozen resolver components, 72 retained raw Open Targets records and
3,534 exact sidecar assertions, including four raw Greek-form labels. All nine implicated
merged groups are included. Twenty-nine member records are ChEMBL records with no retained
original response. Their normalized rows omit original target type, component ownership
and relationship fields. Every one of the nine groups has at least one such missing member.

The ChEMBL ingestion filter requests human SINGLE PROTEIN targets. That is neither a raw
record-level equivalence certificate nor a population of biological complex/relational
positive controls. Lexical probes such as 'complex subunit', 'fusion factor', slash or
hyphen names cannot fill that gap. No name-based structural oracle was invented.

The available raw Open Targets records support 19 clean primary-gene mapping controls,
including six deliberately frozen single-record controls. This does not certify every
synonym in those records, establish a protein/complex identity, or certify a merged group.
The distinction prevents turning 'same record' into 'same biological entity'.

## Eighty-six proposed decision changes

| Diagnostic outcome | Count |
|---|---:|
| CERTIFIED_SINGLE_ENTITY issued | 0 |
| CERTIFIED_MULTI_ENTITY issued | 0 |
| CERTIFIED_RELATIONAL_ENTITY issued | 0 |
| Explicit primary gene-ID mapping CONFLICT | 35 |
| AMBIGUOUS | 51 |
| Still without a permitting certificate (overlapping total) | 86 |

These are diagnostic outcomes, not runtime certificates. All nine whole merged groups
remain AMBIGUOUS, even where specific member-to-canonical gene mappings expose conflicts.
A resolver group containing multiple records is not an authority assertion of a biological
multi-entity target. We therefore do not certify the nine groups as MULTI_ENTITY by counting
records alone.

The 35 conflicts are five approved-name mappings, each in seven existing query frames:

| Raw approved name's gene | Elected canonical gene |
|---|---|
| H4C1 | H4C8 |
| BOLA2 | BOLA2B |
| UBA52 | RPS27A |
| ALK | EML4 |
| JMJD7 | PLA2G4B |

Each conflict uses the raw approved-name assertion's source gene ID and the other source
gene's exact approved-symbol assertion supporting the elected symbol. No substring or
normalized-name inference is used. These are conflicts **at gene-identity granularity**;
they do not prove that all encoded/mature protein products differ. In particular, shared
protein products cannot repair a conflicting gene identity. The required protein-level
identity/equivalence contract remains absent. No mapping was changed.

`component_audit.json.gz` records all 48 groups, canonical labels, source identities,
primary raw assertions, member assertion IDs, exact fields/releases/artifacts, missing
structure, canonical-ID collision sets, diagnostic status and reason. `assertions.json.gz`
contains the 3,534 original sidecar rows. `raw_records.json.gz` contains the retained raw
Open Targets rows with artifact/row locators. `blocked_86_audit.json` links every blocked
proposal to exact matching assertions and its diagnostic finding. `component_table.md`
is the readable summary; `hashes.json` pins canonical artifacts.

## Validation and next step

Three audit builds (seeds 0, 1, 42) have identical canonical artifact hashes. All 6,199 frozen
parser/compiler/trial/buyer decision hashes were recomputed unchanged. Ruff passes for
src/bve/se, tests/se and the new diagnostic scripts. Production src/tests/scripts and
accepted ontology files are unchanged from e2b31bf. Full tests/se was not rerun: this
milestone stopped at the preregistered source gate without a production implementation.
This is not a C10 implementation-pass claim.

See `minimum_source_contract.md` for the required separately frozen structured authority
bundle and granularity contract. The retained source data is enough to expose conflicts,
but not to certify the complete source-component identity scope requested here. Do not
implement TARGET_MENTION_ROLE_DECISION v2, add aliases, or repair the graph on this result.
No new authority source was used. H21–H25 untouched; H6–H10 unrun; human-PoC stopped.
