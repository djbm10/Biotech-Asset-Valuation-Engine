# Minimum additional source contract — proposal, not acquired

The original frozen ChEMBL API responses were discarded. A normalized label, a shared
UniProt cross-reference, a target-fetch filter or an ingestion union cannot replace their
component/type/relationship assertions. Do not fabricate historical response provenance.

The next source-evidence milestone must be separately preregistered before reading new
identity evidence or making certificate labels. It must freeze:

1. A release-addressed ChEMBL 37 target evidence bundle (or explicitly justified newer
   release, separately versioned), with artifact hashes, schema version and exact row/field
   locators. Cover all 29 missing source records in this audit, and genuine positive complex,
   fusion/chimeric, multi-component and relational target controls. The existing build filters
   for human SINGLE PROTEIN targets; that filter cannot supply these missing positive classes.
2. Actual target type, organism/taxonomy, target-to-component membership, stable component
   identifiers, component accessions, component-specific names/synonyms and available typed
   target relations. Verify the release schema; do not invent a relation from punctuation.
3. An explicit gene-versus-protein-versus-complex identity contract. The current elected
   gene-symbol-derived ID and a protein display name can have different granularity. Multiple
   genes encoding the same protein do not become one gene; a protein complex is not a gene.
4. Where ChEMBL membership/accessions alone cannot prove equivalence, a separately pinned
   approved gene authority / reviewed protein authority relation linking precise identifiers
   at the required granularity. Gene identifiers, approved symbols, current/historical
   accession status, taxon and relationship semantics must be explicit. Sequence identity,
   shared cross-reference or same record is insufficient on its own.
5. New evidence must be labelled as new independent identity evidence. Even a release-matched
   database is not the original lost HTTP artifact and cannot restore its original alias
   spelling/component positions by assertion. Link it to existing IDs using typed source keys,
   with conflicts and missing relations retained.

Capture structural-field provenance before normalization. Keep this evidence bundle separate
from the accepted lookup snapshot and existing sidecar; no automatic rebuilding, graph repair,
alias import, canonical reassignment or parser consumption. Freeze expected certificate outputs
before a subsequent implementation. If exact equivalence remains unsupported, retain AMBIGUOUS.

No additional source was acquired or used in TARGET_COMPONENT_IDENTITY_CERTIFICATE v1.
