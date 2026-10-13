# TARGET_COMPONENT_IDENTITY_CERTIFICATE v1 — preregistration

Starting HEAD: e2b31bf. Decision-neutral milestone. No implementation is authorized by
this document until the source-readiness gate below passes. Existing parser, aliases,
resolver identities, target-role decisions and accepted snapshots remain unchanged.

## Frozen diagnosis population and source-readiness gate

`population.json` freezes 48 existing resolver components: all nine implicated groups,
clean gene/receptor/subunit names, both canonical-ID collision families, six single
Open Targets record controls, and lexical fusion/complex/ligand/slash/hyphen traps.
Selection is recorded in `freeze_population.py`. Lexical traps are **not** labelled as
biological fusions, complexes or relations by their spelling. In particular, a protein
whose name includes 'complex subunit' is not thereby a multi-protein complex.

Also use all 86 previously blocked proposals and their exact matching assertion IDs
from the prior frozen candidate-component audit. All available sidecar assertions for
selected component members are in scope. Do not synthesize missing raw ChEMBL records.

G0: inventory the structure-bearing fields in the retained authority artifacts, including
source entity identifiers, target type, component membership and relationship types.
Prove a lineage-preserving route from these fields to the linked canonical identity.
The existing sidecar establishes label lineage, not biological equivalence. The prior
sidecar study reports no original ChEMBL response artifacts; verify the consequence,
not a guessed reconstruction from normalized exports or current API responses.

If the frozen sources cannot support the required biological component distinctions,
STOP before production implementation. Record each unresolved component and the minimum
additional authority/source contract. Do not label missing evidence CERTIFIED_MULTI_ENTITY
merely because the resolver graph joined several source records. Do not label every
alias in a gene record CERTIFIED_SINGLE_ENTITY merely because of record co-membership.
A diagnostic AMBIGUOUS result is not an adopted runtime certificate.

## Proposed certificate contract

Identity unit must be explicit: gene, protein, complex, fusion, or another authority-typed
entity. Separate a raw assertion/component from the resolver's ingestion grouping.
Certificate key: exact assertion ID(s), source component locator, canonical identity and
snapshot version. Preserve one-to-many lineage and all canonical-ID collisions.

- CERTIFIED_SINGLE_ENTITY: structured authority identity establishes one entity and a
  supported same-entity link to the canonical identity, at the same identity granularity.
- CERTIFIED_MULTI_ENTITY: authority structure explicitly denotes several entities; never
  constituent-level equivalence. Several graph members alone are not such an assertion.
- CERTIFIED_RELATIONAL_ENTITY: an explicit typed relation (fusion, complex, heterodimer,
  ligand/receptor relation); no promotion of a constituent symbol to the whole relation.
- CONFLICT: positive authority evidence establishes incompatible identity claims. Missing
  evidence alone is not a conflict. Raw approved gene identities can expose a mismatched
  elected gene mapping without authorizing a repair of the component.
- AMBIGUOUS: identity, structure, granularity, equivalence or original evidence insufficient.

Include exact raw artifact SHA/release, record and field/component locators, raw text,
assertion IDs, source membership evidence, equivalence evidence, rule identifier, status,
and abstention reason. No random IDs, timestamps, fuzzy matching, lexical structure
inference, benchmark exceptions, or canonical-ID-as-equivalence assumptions.

## Acceptance, if G0 supports implementation

C1: all nine groups explicitly audited; no omitted member or unsupported certificate.
C2: ALK approved-name to EML4 mapping never certified as single same entity.
C3: zero constituent-level single certificates from multi/relational controls.
C4: all clean positive controls with sufficient frozen identity evidence certified; unknown
controls cannot be relabelled positive or negative after implementation results.
C5: every same-canonical-ID/different-component pair remains independently traceable.
C6: every positive certificate cites structured authority evidence, not just normalized text.
C7: 100% certificate premises have exact assertion or raw structured-field provenance.
C8: three builds/seeds produce identical canonical certificate bytes and IDs.
C9: all 6,199 frozen parser/compiler/trial/buyer decision hashes remain unchanged.
C10: full tests/se passes except existing xfails; Ruff clean.

Before implementation, freeze exact per-case expected certificates and the deterministic
rule with all premises, commit that implementation supplement, then red tests, smallest
additive implementation, focused/frozen/full tests/Ruff and adopt or normally revert.
No post-result patch loop. This initial preregistration is the source-readiness phase;
it does not pretend that scientific oracle labels are known before diagnosis.

Report the 86 proposed decisions by status; 'still uncertifiable' is an overlapping total
of AMBIGUOUS/unsupported cases, not an extra disjoint category. If G0 fails, report diagnostic
status and do not present the result as an adopted certificate layer or an implementation
acceptance score. No target-role v2 or authority-mapping repair in this milestone.

H21–H25 untouched; H6–H10 unrun; human-PoC stopped. No live acquisition.
