# Provenance — S&E production ontology, resolver_v2 (M10D)

Append-only lineage record for the combined target + drug + mechanism-edge ontology.
It links the published scientific payload to the exact code and upstream bytes that
produced it. It does not change or re-cut the release, and it is not bound by the
artifact's receipt. Supersedes nothing: `se_ontology_snapshot_chembl37_ot26.06.md`
remains the record for the earlier target-only `resolver_v1` payload.

## Release

```text
ontology_version:
chembl_ChEMBL_37__open_targets_26.06__resolver_v2
(runtime appends the modality ontology: ...__modality_v2)

scientific payload SHA (ontology_snapshot.tar.gz):
1eef14f137275b7485a418cfd60e0ec612a9b595c6666160568c7e39368459f6

manifest SHA (as bound by receipt.json):
a4206a6d8772c5300cf195b807b7345fb5bc00951f1232eaf293f0384cab4ca2

receipt-bound payload files:
records.jsonl   986fa262e3c275424968996b78703614563304cf22f5e2a2f1d3c39e0fc6f50b
edges.jsonl     2a6b6ea8f55abf8b292138904eefc2baa2a285d8ad5851f4cc6d91ac3b93f551
snapshot.json   c23936cb971cfb5579603acd1271993bc5c394172e05a760c4a350e3c51c0fe8

receipt issued_at: 2026-09-08T02:44:08Z
```

Contents: TARGET entities, DRUG entities, drug aliases/identifiers, ChEMBL 37 direct
mechanism edges, Open Targets 26.06 direct mechanism edges, non-direct family/complex
edges preserved as `FAMILY_OR_COMPLEX_ASSOCIATION` (non-decisional), conflict states,
per-source provenance, resolver and modality versions.

```text
records 156,066   (open_targets 101,098 · chembl 54,968)
edges    22,965   (DIRECT_TARGET 12,896 · FAMILY_OR_COMPLEX_ASSOCIATION 10,069)
                  (chembl 7,561 · open_targets 15,404)
                  (USABLE 19,883 · TARGET_NOT_IN_SNAPSHOT 3,082 · decisional 9,816)
normalized DRUG 55,582 · TARGET 78,378
conflicts ALIAS_SHARED_ACROSS_ENTITIES 43,406 · CANONICAL_SYMBOL_DISAGREEMENT 36
```

`resolver_v2` exists because neither source release moved: ChEMBL 37 and Open Targets
26.06 are the same releases the `resolver_v1` payload used. Without the resolver bump the
combined artifact would have carried the same version token as the target-only one it
replaces.

## Builder commits

```text
manifest built_by.git_commit:
a8b150af80bb169b1eaf412841e13fd10054a238  feat(se): add Open Targets as a second drug->target authority

builder bytes finalized in:
c395ff7ed13ee3383e263daac493a2f8dd082dfd                                feat(se): attribute targets per asset instead of inheriting the query target
```

The manifest records `a8b150a` because that was `HEAD` when the build ran. Two pinned
modules (`mechanisms.py`, `targets.py`) plus the two unpinned driver modules
(`build.py`, `artifact.py`) were modified-but-uncommitted at build time; those exact
bytes were committed unchanged as `c395ff7`. Both commits are pushed to
`origin/fix-se-ci-failures`, so every byte below is recoverable from a tracked commit.

## Module hashes

Pinned by the artifact manifest's `code_hashes`, with the commit whose tracked bytes
reproduce each hash:

```text
bulk.py                       fd2d213b0ead16629dc5bad1c73e8827665a93f35e63c0a360ccb734c3dfa425  a8b150a & c395ff7
mechanisms.py                 2f3938c4a2c2adfb31046a658b7c5e1c241424900618f71d3ad9bd34e03c84b5  c395ff7 only
modality.py                   6c21f71527bbf900448db11513a37273fddfc9c7168f2b3d80f9ef99b80f418c  a8b150a & c395ff7
records.py                    a5c5b5692350ba085c1f7dbd3f0a5d319c5a2b8fa455e0bd3488a678f2d8e295  a8b150a & c395ff7
resolver.py                   fe08fa63759732bd2f53b42838f43af050400e90c962e05d473cd29328562de1  a8b150a & c395ff7
sources/chembl.py             55d15b734e02414f2435f6a47a5f7d34fb81586bdeb3c0ecccc4375a945d8abe  a8b150a & c395ff7
sources/chembl_drug.py        973e14f28e9eb70f1f10c10dcbe924fa7c011898f8934b40c1ce36a3017e963e  a8b150a & c395ff7
sources/open_targets.py       cb50236853c639dc0a34b1d6e118d2838ff2c5ea5aa879ee26f6d15d7f981163  a8b150a & c395ff7
sources/open_targets_drug.py  d0f2497292b537a135ad49325d00d7129861a7a65ba7bbcf546aeef58badd0ab  a8b150a & c395ff7
targets.py                    85395bbf8f374444bf8fef90154f5306cbd2c1a230fe3bf10d1378de16eb7396  c395ff7 only
```

**Known gap, unchanged from `resolver_v1`:** `code_hashes` covers the parsers, resolver
and mechanism layer but not the driver modules. Pinned here instead, at their `c395ff7`
bytes, which are the bytes the build ran:

```text
build.py      a23330839299baf4092535bca261422de193220f07414867f3191d439cf9e1ac  (NOT manifest-pinned)
artifact.py   05d935510ba011b50af20d07c053b081809380aa6d7784cd1ffcdbfc31838b47  (NOT manifest-pinned)
snapshot.py   1f19ee5ddbe30e597f453bb8baeb0b0ec5e96b385f7ac6dfeb9efa891da17526  (NOT manifest-pinned)
```

Widening `code_hashes` would alter a published manifest, so it stays deferred to the next
snapshot rather than applied retroactively.

## Upstream sources

Hashed before parsing; identical values appear in the manifest's `raw_files`.

```text
Open Targets 26.06, release 26.06, retrieved 2026-09-08
  https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/26.06/output/

  target/
    part-00000-810593a9-...-c000.snappy.parquet  30365704 bytes  26353 rows  770cdce2c5b6c46952777139bbe68bd0164a6eb0878ad94832775f7d9838d216
    part-00001-810593a9-...-c000.snappy.parquet  29725904 bytes  26245 rows  e2a0bf1db8d4d31cdcc90cea56cec19c068c7a6077f37d3e75dedc7b44a19bbf
    part-00002-810593a9-...-c000.snappy.parquet  29839950 bytes  26093 rows  7fc4baeb3e0b9a95f0cad2e280b47955e253bceb3eba8cf85f32e770e771284a
  drug_molecule/
    part-00000-5581d2c3-...-c000.snappy.parquet  14647216 bytes  22407 rows  d98d7e4e6e3c7a91fdd915c7dd2f5f8e07504da73fec22880bf4aca10fc524da
  drug_mechanism_of_action/
    part-00000-10b94b1b-...-c000.snappy.parquet    281271 bytes   2733 rows  949aedc4717356279877da143a13cf11f267f96d062fe0e12c1c44816959cb4a
    part-00001-10b94b1b-...-c000.snappy.parquet    299939 bytes   3031 rows  4a02cef4c182bb0ed20d341c6c4553f6c839b02f3217777fb65993a38e456a29

  source digest: 8be5eb35f70cab7da402ac22ba4ca693   101,098 records

ChEMBL_37, retrieved 2026-09-08
  https://www.ebi.ac.uk/chembl/api/data/target.json
  https://www.ebi.ac.uk/chembl/api/data/molecule.json
  https://www.ebi.ac.uk/chembl/api/data/mechanism.json
  release verified live against https://www.ebi.ac.uk/chembl/api/data/status.json

  source digest: 287566166b1d35efc24c24dedd02e08f    54,968 records
```

The three `target/` parquet parts are byte-identical to the ones behind the `resolver_v1`
payload; the drug and mechanism exports are new to this release.

## Verification performed

- Open Targets refetched from scratch, recording per-file URL, byte length and sha256
  before parsing; recorded values match the table above.
- archive checksum verified with `sha256sum -c` after the build.
- archive extracted into a clean tree outside the working directory, and
  `bve.se.ontology.artifact.revalidate` reported OK there — version, 156,066 records and
  22,965 edges all confirmed from the extracted copy, not the build directory.
- receipt <-> manifest hash binding recomputed and matched.
- installed payload at `data/se/ontology/current/` byte-identical to the published copy
  (`records.jsonl` 986fa262...).
- real-data sanity through the installed snapshot: pembrolizumab -> `CONFIRMED_TARGET`
  PDCD1; durvalumab -> `CONFIRMED_OTHER_TARGET` CD274; carboplatin -> `UNRESOLVED`;
  ivonescimab -> `UNRESOLVED`. No special-case rules.

## Scope limit

The mechanism edges answer one question only: what target(s) does this asset itself act
on? A `FAMILY_OR_COMPLEX_ASSOCIATION` edge names a protein family or complex and lists
every member gene, so it supports no per-member claim. Those edges are preserved for
analyst review and never confirm or exclude a target. Authority silence is `UNRESOLVED`,
never a negative.
