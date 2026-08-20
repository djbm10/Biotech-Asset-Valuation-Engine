# Provenance — S&E production ontology snapshot (Pre-M11A)

Append-only lineage record. This file establishes the link between the published
scientific payload and the exact code that produced it. It does not change or
re-cut the release, and it is not bound by the artifact's receipt.

## Release

```text
ontology release:
se-ontology-snapshot-chembl37-ot26.06-56bc8d70c81dc8c41035be10

release url:
https://github.com/djbm10/Biotech-Asset-Valuation-Engine/releases/tag/se-ontology-snapshot-chembl37-ot26.06-56bc8d70c81dc8c41035be10

ontology_version:
chembl_ChEMBL_37__open_targets_26.06__resolver_v1
(runtime appends the modality ontology: ...__modality_v2)

scientific payload SHA (ontology_snapshot.tar.gz):
56bc8d70c81dc8c41035be100c1507abda2481306cb7745d3f0f5a8dc847f7e9

manifest SHA (as bound by receipt.json):
35ae96ffd6df189f13ec8a2e5b8a64b1518291fe900c81f3bf80716549881cd4
```

## Builder commits

```text
builder commit(s):
35e6721cdd2f70a90c899082f8abbf72907298bb  fix(se): flag widely shared aliases in linear time
a1c6ec84e6ed13d554aac4516ff97d5b0d6b5bb6  feat(se): track the ontology builder and artifact publisher
```

`35e6721` is the commit recorded in the artifact manifest's `built_by.git_commit`;
it is the tree the snapshot was actually built from. `a1c6ec84e6ed13d554aac4516ff97d5b0d6b5bb6` adds no behaviour —
it persists the builder modules that `35e6721` referenced but did not track.

## Module hashes

Pinned by the artifact manifest's `code_hashes`:

```text
artifact.py SHA:   f067fa9a21999b5664bf2927eb86105a5f22d40b4c1c7a5c4ee4f166d13eb809  (NOT manifest-pinned)
bulk.py SHA:       fd2d213b0ead16629dc5bad1c73e8827665a93f35e63c0a360ccb734c3dfa425  (manifest-pinned)

modality.py              6c21f71527bbf900448db11513a37273fddfc9c7168f2b3d80f9ef99b80f418c
records.py               a5c5b5692350ba085c1f7dbd3f0a5d319c5a2b8fa455e0bd3488a678f2d8e295
resolver.py              fe08fa63759732bd2f53b42838f43af050400e90c962e05d473cd29328562de1
sources/chembl.py        55d15b734e02414f2435f6a47a5f7d34fb81586bdeb3c0ecccc4375a945d8abe
sources/open_targets.py  cb50236853c639dc0a34b1d6e118d2838ff2c5ea5aa879ee26f6d15d7f981163
targets.py               8acfb2992fab339cd6ea73e367dbdb1040fde0fbc0ef016cc6cebe2b7cd971c0
build.py                 7b3eeb73330fad08ec78ec5104ceffb4f63fb91fc7ee213a00c7cacd277c789d  (NOT manifest-pinned)
```

**Known gap:** the manifest's `code_hashes` covers the parsers and resolver but
not `artifact.py` (publisher/validator) or `build.py` (CLI driver). Those two are
pinned here instead. Widening `code_hashes` would alter a published manifest, so
it is deferred to the next snapshot rather than applied retroactively.

## Upstream sources

Hashed before parsing; identical values appear in the manifest's `raw_files`.

```text
Open Targets 26.06 'target' export
  https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/26.06/output/target/
  part-00000-810593a9-...-c000.snappy.parquet  30365704 bytes  770cdce2c5b6c46952777139bbe68bd0164a6eb0878ad94832775f7d9838d216
  part-00001-810593a9-...-c000.snappy.parquet  29725904 bytes  e2a0bf1db8d4d31cdcc90cea56cec19c068c7a6077f37d3e75dedc7b44a19bbf
  part-00002-810593a9-...-c000.snappy.parquet  29839950 bytes  7fc4baeb3e0b9a95f0cad2e280b47955e253bceb3eba8cf85f32e770e771284a

ChEMBL_37 (human SINGLE PROTEIN, paged)
  https://www.ebi.ac.uk/chembl/api/data/target.json
  release verified live against https://www.ebi.ac.uk/chembl/api/data/status.json
```

The pin is ChEMBL **37**, not the 36 used in the design docs: the REST service
serves only the current release, and `verify_chembl_release` refuses to stamp a
release the records did not come from.

## Verification performed

- archive checksum verified after a fresh `gh release download` outside the tree
- receipt <-> manifest hash binding recomputed and matched
- independent `bve.se.ontology.artifact.revalidate` reported 0 problems
- all four payload files byte-identical to the local finalized copy
- real-data sanity from the redownloaded artifact: `BCMA` -> TNFRSF17,
  `HER2` -> ERBB2, `TROP2` -> TACSTD2, emergent, no special-case rules
- remote code provenance: builder module bytes refetched from GitHub and hashed
  against the values above (see `remote_code_verification.json`)
