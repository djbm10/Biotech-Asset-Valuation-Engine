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
