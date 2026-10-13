# TARGET_COMPONENT_IDENTITY_AUTHORITY_EVIDENCE v1 — preregistration

Baseline d47b810. Source/evidence only. No certificates, aliases, lookup changes or
parser consumers. The minimum source contract from certificate v1 remains authoritative.
Previous 35 gene-ID conflicts / 51 ambiguous / zero permitting certificates are immutable.

## Required fields and source comparison (before identity acquisition)

| Mandatory requirement | ChEMBL 37 SQLite | HGNC approved-gene release | Reviewed UniProtKB | Existing OT 26.06 | Complex Portal |
|---|---|---|---|---|---|
| Release, immutable artifact, exact locator | release DB, table/PK/column | dated object generation, JSON pointer | release header, entry/version, JSON pointer | retained Parquet/row/field | versioned complex accessions/download |
| Stable identity and biological type | target/component ID, target_type/component_type | HGNC/Ensembl ID, locus_type/group, status | primary/secondary accession, review status, taxon | gene ID, biotype | complex ID and interactor types |
| Canonical name/symbol and synonyms | target name, component_synonyms including syn_type | symbol/name/alias/previous symbols | recommended names, genes, alternative names | approved name/symbol and raw synonyms | names and synonyms |
| Membership / constituent IDs | target_components to component_sequences accessions | gene-to-protein xrefs, not complex equivalence | explicit gene/Ensembl/HGNC xrefs, processing and features | gene/protein crossrefs only | explicit participants/stoichiometry |
| Typed fusion/complex/family/relation | CHIMERIC PROTEIN, complex/family/PPI target types; target_relations | no general complex/fusion membership | no general complex membership guarantee | insufficient | strong complex/interactor evidence, not broad gene/family authority |
| Current/historical identity status | release-pinned component accessions, not current status | Approved/withdrawn and previous symbols as provided | current primary/secondary, inactive response or explicit unresolved lookup | historical mixed crossrefs, not equivalence | complex accession version, not gene nomenclature authority |
| Gene/protein/complex distinction | target and component layers retained | authoritative gene layer | reviewed protein layer | historical gene claims | complex layer |

Selected: ChEMBL 37 + HGNC dated object + UniProtKB 2026_03, alongside unchanged existing
OT/sidecar evidence. No one source suffices alone. Complex Portal is not selected: ChEMBL's
structured type/membership/relations are the proposed sufficient complex/fusion layer;
if actual fields fail S1, stop rather than add it post-result. Current ChEMBL REST is not
selected because it is not an immutable release artifact or the lost historical response.
Neither OT crossrefs alone nor normalized ChEMBL exports can satisfy the contract.

Sources/schema documentation checked before record acquisition:
- https://chembl.gitbook.io/chembl-interface-documentation/downloads (release 37, May 2026)
- https://chembl.blogspot.com/2013/01/chembl-15-schema-changes.html
- https://www.genenames.org/help/hgnc-data/ and /download/archive/monthly/json/
- https://www.uniprot.org/help/accession_numbers and /help/api_queries
- https://www.ebi.ac.uk/training/online/courses/complex-portal-quick-tour/getting-data-from-complex-portal/

Only schema/version/vocabulary and HTTP headers have been inspected for the new sources.
No new biological source records were acquired before this commit. HGNC October archive
URLs tried returned 404; selected current object is pinned by generation and ETag instead.

## Exact selected releases/routes

1. Existing independent release DB:
`/home/djmann/staging/pdcd1_gold_role_authority_v1/sources/chembl_37/chembl_37/chembl_37_sqlite/chembl_37.db`.
Open read-only. Require version ChEMBL_37. SHA-256 full file, preserve schema DDL and version
rows. Record the existing official tarball provenance/manifest; this is new independent
identity evidence, NOT recovered historical API provenance. Tables: target_dictionary,
target_type, target_components, component_sequences, component_synonyms, target_relations.
Keep all selected rows and all relevant constituents, with exact primary-key locators.

2. HGNC official complete-set JSON:
`https://storage.googleapis.com/public-download-files/hgnc/json/json/hgnc_complete_set.json?generation=1791894733877675`.
Expected ETag `f99ab3a0652d842facdc7c3b34961f35`, Last-Modified 2026-10-13 12:32:13 GMT,
object generation 1791894733877675; freeze raw bytes/headers/hash. No substitution on 404,
ETag mismatch or missing required gene fields. Preserve absent/withdrawn/unmapped explicitly.

3. UniProtKB REST `https://rest.uniprot.org/uniprotkb/{accession}.json`, release **2026_03**,
release date **02-September-2026**. Require release headers on successful responses and
retain raw responses, headers, URLs, entry versions and any redirect/inactive information.
Freeze each response by SHA-256. Network retries may repeat the same request up to 3 times;
no alternative authority after scored failure. Unreviewed records are retained but cannot
be labelled reviewed support. A missing/inactive lookup is explicit evidence of availability
status, not a guessed historical identity or a biological equivalence link.

## Frozen populations and deterministic expansion

Preserve all 48 components, nine implicated groups, 86 blocked proposals, all source-member
IDs and all canonical-ID collisions from certificate v1. Pin their artifacts and the 6,199
baseline. Query all 29 missing ChEMBL IDs by exact stable ID, no names or substring joins.

Add real structural controls by SQL selection: for each of SINGLE PROTEIN, CHIMERIC PROTEIN,
PROTEIN COMPLEX, PROTEIN COMPLEX GROUP, PROTEIN FAMILY, PROTEIN-PROTEIN INTERACTION and
SELECTIVITY GROUP, select the first three human targets in ascending numeric tid. Freeze
selection and raw rows before normalization. Include complete target_components, sequences/
accessions, typed target relations (either endpoint selected) and endpoint target records.
No efficacy or asset/trial data is read. Type vocabulary supplies classification; names do not.
If any required structural category is absent, record S1 failure; do not relabel a name probe.

HGNC extract: exact Ensembl IDs of all existing raw OT members, plus exact UniProt accessions
of acquired ChEMBL components (HGNC explicit uniprot_ids membership); retain all matches.
UniProt request universe: all ChEMBL component accessions in selected targets/typed-relation
endpoints plus all explicit HGNC uniprot_ids for these records. Deduplicate by exact accession,
sort; never infer from protein names. Record remaining unmatched gene IDs/accessions.

## Lossless evidence model and conflict semantics

Raw sources are immutable. Extract JSON/SQL values without changing case, punctuation, Greek,
spacing or delimiters. Every leaf assertion has source/version/artifact SHA, row/PK and field
pointer, exact raw value, identity transform, deterministic SHA-derived assertion ID. Arrays
retain component indices; scalar aliases are not split. Structured membership relations refer
to exact source row IDs. Do not merge genes sharing a protein or promote one fusion constituent.

Preserve historical OT gene assertions, current HGNC gene assertions, UniProt protein records,
and ChEMBL target/component claims as separate layers. Same-ID-version/name disagreement is
recorded side by side; gene/protein/complex-level differences are labelled level differences,
not automatically contradictions. Retain all 35 prior gene-ID conflicts unchanged. No winner
selection and no new permitting certificate. Nonmatching identities remain ambiguous.

## Acceptance gates fixed before acquisition/normalization

S1: all required table/field families exist, all 29 ChEMBL records recovered by exact ID,
all seven structural control types present, actual chimeric/complex/PPI controls preserve
constituents (at least one control with >=2 distinct constituent IDs in each of these three
types), raw taxon/type/name/ID/membership and typed-relation locators present. HGNC and reviewed
UniProt supply explicit gene/protein mapping fields and accession/review status or honest
unresolved responses. Never waive missing constituent or type data by parsing labels. Missing
individual equivalence is allowed as UNKNOWN; missing mandatory source structure fails S1.
S2: releases and raw hashes/headers frozen, no mutable-current substitution or version drift.
S3: 100% imported leaf assertions independently replay exact raw values at original locators.
S4: every selected membership row retained; zero constituent collapse or inferred name edges.
S5: all prior conflicts remain separately identifiable; neither old artifact nor mapping edited.
S6: report all 86 diagnostic coverage statuses, disjoint precedence: prior gene conflict,
explicit relational structure, explicit multi-entity structure, uniquely supported typed path,
ambiguous, no evidence. These are evidence-coverage descriptions, not certificates. Uniquely
supported requires one explicit gene/protein path with all relevant source fields and no
competing constituent; no recovery count is a pass target.
S7: two independent offline builds with seeds 0 and 42 have identical canonical evidence,
assertion IDs and coverage bytes. Acquisition timestamps excluded from canonical evidence.
S8: 6,199/6,199 frozen decision hashes unchanged.
S9: accepted snapshot and adopted sidecar hashes unchanged.
S10: no imports into production parser/resolver/discovery or other scientific decisions.
S11: focused lineage/structure/neutrality tests and Ruff pass; full tests/se if production
code changes. Proposed implementation is offline research evidence tooling only.

If a gate fails, preserve evidence and stop; no post-result source substitutions/patch loop.
If all pass, adopt evidence only, update handoff; certificate v2 is a separately preregistered
future milestone. H21–H25 untouched, H6–H10 unrun, human-PoC stopped.
