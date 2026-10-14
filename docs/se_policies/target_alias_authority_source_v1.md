# TARGET_ALIAS_AUTHORITY_SOURCE v1 — source-authority readiness (preregistration)

Readiness and design only; no production change. The Greek v2 implementation stays reverted; no orthographic transform, shortening, substring or synonym invention. The 86 target-component identities stay closed. Query-target alias coverage is not evidence that any asset acts on a target. H17/H20 are development checks only. H21–H25 and H6–H10 are untouched; heldout concepts were excluded by the frozen survey (`survey_freeze.json`).

## Frozen sources (versions/hashes recorded in `research/se_target_alias_authority_source_v1/freeze_hashes.txt`)

- **HGNC** complete set, 2026-10-13 (45,277 records; `target_component_identity_authority_evidence_v1/raw/hgnc.json`): approved name, alias_symbol, alias_name, prev_symbol, prev_name.
- **NCIt 26.09d identifier records** (13,032; `target_query_alias_coverage_v1/ncit_identifier_records.json`): protein-typed (P106 "Amino Acid, Peptide, or Protein") concept synonyms (P90) with Swiss-Prot (P93) and/or an encoded-by gene carrying HGNC.
- **NCIt 26.08e non-product names** (`data/se/ontology/ncit/ncit_26.08e_entity_types.json`): used only to detect cross-type claimants (measurement, disease, etc.).
- **UniProt 2026_03**: 348 accessions only. Recorded where present; not a general coverage source.
- **Runtime snapshot** (`data/se/ontology/current`, ChEMBL_37 + OT 26.06): existing lookup keys and claimants.

## Independent population

The 192 Open Targets entities of the frozen alias survey that are selected by hash (not the 96 Greek proposals). An entity joins HGNC by Ensembl gene id and NCIt by UniProt accession or HGNC id. A **candidate name** is any HGNC or NCIt-protein string for that entity whose normalized key (`normalize_lookup_key`) is not already a runtime key for that entity.

## Classification (per candidate name, all claimants counted, none excluded)

- `CONFLICT_RUNTIME`: the runtime resolves the key to any other TARGET.
- `AMBIGUOUS_AUTHORITY`: the key appears for ≥2 distinct HGNC genes (any name field), or on NCIt protein records mapping to different genes.
- `CROSS_TYPE`: the key is an NCIt non-product name or a non-protein NCIt claimant.
- `CERTIFIED`: none of the above.
- **Reachable:** `CERTIFIED` and ≤ 2 parser tokens (the adopted target cap; not raised here).

## Readiness (computed by `audit.py`, self-tested)

- **J1 coverage:** ≥ 10% of the 192 entities gain ≥ 1 CERTIFIED reachable name.
- **J2 safety:** no CERTIFIED name has a competing claimant in any source. The 16 frozen survey controls hold: wrong subunit, confusable, activation state, other factor, disease and homonym controls gain no CERTIFIED mapping to the H17/H20 entities.
- **J3 H17 (development):** some frozen authority contains the exact query spelling `IL-4Rα`.
- **J4 H20 (development):** `factor XI` is CERTIFIED to F11 through an NCIt protein record with an identifier chain (cross-type measurement claimants recorded, not counted as targets). The adopted target-reference path must also carry F11 through offline compilation for the existing unique alias `FXI`, which is the downstream proof that a resolved F11 survives compilation.
- **J5:** byte-identical builds.

Verdict:
- **JUSTIFIED** iff J1 ∧ J2 ∧ J3 ∧ J4 ∧ J5.
- **JUSTIFIED_EXCLUDING_H17** iff all but J3 pass. H17 is then recorded as not repairable from authoritative sources (it would need an orthographic transform, which is out of scope).
- **STOP** otherwise.

**Disclosure:** before this freeze, I read the HGNC/UniProt/NCIt IL4R and F11 records while locating sources. J3 is expected to FAIL (no source spells `IL-4Rα`). That expectation comes from those development records, and the outcome tiers above were defined with it known.
