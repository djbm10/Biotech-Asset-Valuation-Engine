# Source contract — NCI Thesaurus (NCIt) target sidecar

| Attribute | Value |
|---|---|
| Source | NCI Thesaurus, NCI Enterprise Vocabulary Services (EVS) |
| Release | 26.08e (archived, immutable path) |
| Locator | `https://evs.nci.nih.gov/ftp1/NCI_Thesaurus/archive/26.08e_Release/Thesaurus_26.08e.FLAT.zip` |
| Artifact sha256 | `645ad414c3a0b6ceecda66e132ca66055c15608f39508597c23a3a94b38309da` (the builder refuses any other) |
| Local copy | `~/se_sources/ncit/26.08e/` (not committed) |
| Licence | Public domain (US Government work); attribution to NCI EVS requested |
| Access | Anonymous HTTPS download; no key, no rate limit relevant at release granularity |
| Format | Tab-separated FLAT file: code, IRI, parents, synonyms, definition, display name, status, semantic type |
| Derived artifact | `data/se/ontology/ncit/ncit_26.08e_targets.json`, built by `scripts/build_ncit_target_sidecar.py` |
| Fields used | parents (class membership), synonyms + display name (linking), definition (mechanism sentence only) |
| Fields not used | roles (mechanism class, not gene), associations, any non-product branch |
| Semantics relied on | (1) membership in a curated "Anti-X CAR T Cells Preparation" class asserts the product targets X; (2) the definition's "Upon/After/Following …" sentence states what the product is directed to |
| Semantics NOT relied on | Any other definition prose: it describes construct architecture, armoring, switches and background biology |
| Coverage | 959 products under CAR / antineoplastic-immune-cell roots; 21 antigen classes, all CAR-T (no CAR-NK, antibody or ADC classes) |
| Measured precision | 0/136 false facts on the held-out half (`ncit_target_sidecar_v1.md` §8) |
| Known limits | Class membership incomplete for duals (handled by agreement); some concepts have no definition; non-gene antigens (GD2, Claudin18.2) yield no gene target by design |
| Replay | Sidecar token `ncit_target_sidecar_v1@ncit_26.08e@<sha16>` is sealed in `corpus_manifest.extractor_versions`; replay fails closed if the installed sidecar differs or is absent |
| Versioning | A new NCIt release is a new sidecar file and token; it never alters runs sealed under 26.08e |

## Second derived artifact — entity-type sidecar (candidate_qualification_v6)

| Attribute | Value |
|---|---|
| File | `data/se/ontology/ncit/ncit_26.08e_entity_types.json` |
| Builder | `scripts/build_ncit_entity_types.py` (same frozen zip) |
| sha256 (2026-10-03 build) | `ec498e5694a0e3842eabeb2afd5689cd8a054e13ac0cbc56a73d7e32566124fd` |
| Contents | 278,601 normalized names whose **every** NCIt concept has only non-product semantic types (closed UMLS set in the policy) |
| Fields used | synonyms + display name (key), semantic type |
| Semantics relied on | NCIt's semantic type classifies what kind of thing a name denotes (procedure, activity, concept) |
| Replay | `extractor_versions["ncit_entity_types"]`, fail-closed like the target sidecar |
