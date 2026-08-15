# S&E Biomedical Entity Layer (M9A)

Replaces the 47-line hardcoded `cd19_bcma_v1` alias stub with a target-agnostic,
bulk-backed, versioned entity layer.

## Why this came first

The S&E pipeline (`bve-se-search`) already ran discovery → evidence → identity
resolution → gates → shortlist. What it could not do was generalize: `normalize_target`
knew exactly two targets, so a run against PDCD1 or KRAS G12D had no alias expansion at
all. Every downstream generalization claim failed here first, which is why the ontology
was built before the broad-universe provider (M9B) and the NL intent compiler (M9C).

## Layering

```
CanonicalEntity          normalized view: canonical symbol, aliases, conflicts
      ↑                  (built at load time, never persisted as truth)
SourceEntityRecord[]     what each source said, preserved verbatim
      ↑
OntologySnapshot         versioned, provenance-stamped, on disk
      ↑
Open Targets bulk / ChEMBL API
```

Source records are never overwritten by the normalized view. When two sources
disagree, both survive and the disagreement is reported as a `ConflictFlag`.

## Design rules

**Entities are joined on identifiers, never on names.** Records group via UniProt
accession (`JOIN_NAMESPACES`). String similarity is not used anywhere in grouping, so
the layer cannot invent a merge between two targets with similar names.

**ChEMBL protein complexes are not joinable.** A `PROTEIN COMPLEX` row lists several
accessions; joining on them would absorb every member protein into the complex. Those
accessions are recorded under `uniprot_unjoinable` for inspection instead.

**Ambiguity is escalated, not guessed.** A string matching more than one entity returns
`AMBIGUOUS` with all candidates. The only tie-break is alias specificity (a `SYMBOL`
beats a `SYNONYM`), and only when it leaves exactly one candidate. The rule that fired
is recorded in `ResolutionResult.rule`.

**Shared classification identifiers are not conflicts.** Every enzyme in a class carries
the same EC number, so `XREF`/`DESCRIPTION` aliases are excluded from conflict flagging
— but they still resolve as `AMBIGUOUS`, so nothing is silently picked.

**Symbol authority is declared, not implicit.** `SYMBOL_AUTHORITY` puts Open Targets
first for targets (its `approvedSymbol` is the HGNC approved symbol). Note this inverts
the old stub: `TNFRSF17` is the approved symbol and `BCMA` the synonym, so
`normalize_target("BCMA") == "TNFRSF17"`.

**Modality stays curated in-repo.** Open Targets and ChEMBL classify molecules far more
coarsely than an S&E screen needs, so `modality.py` is a controlled vocabulary
(`modality_v2`, 18 classes). It is a taxonomy, not benchmark seeding: no entry may
encode a specific target, programme, or company.

## Explaining a resolution

Every `RESOLVED` result carries a `ResolutionBasis` answering "why did you interpret my
query this way?" without the caller re-deriving anything:

```python
result = resolver.resolve("HER2")
result.basis.explain(result.canonical_symbol)
# "'HER2' -> synonym alias 'HER2' asserted by chembl -> ERBB2"

resolver.resolve("PD-1").basis.explain("PDCD1")
# "'PD-1' -> synonym alias 'PD-1' asserted by chembl, open_targets -> PDCD1
#  -> merged on uniprot:Q15116"
```

`identifier_edges` lists only the `namespace:value` identifiers shared by two or more
source records — the edges that actually caused the merge — so a single-source entity
reports none. `asserted_by` and `asserting_record_keys` are sorted, so the derivation is
stable regardless of record ordering.

`AMBIGUOUS` and `UNRESOLVED` results carry no basis by design; there is no derivation to
report, and `candidates` is the actionable field:

```
resolver.resolve("p150")
# AMBIGUOUS (homonym_requires_escalation) -> ['TARGET:ABL1', 'TARGET:ELP1']
```

## Versioning

Every run stamps `RunManifest.ontology_version`:

```
chembl_36__open_targets_26.06__resolver_v1__modality_v2
```

Sources sort by name, so the token does not depend on build order. `resolver_v1` bumps
when resolution semantics change; bump it whenever output could differ for an unchanged
upstream snapshot.

## Degradation without a snapshot

A fresh clone has no snapshot. Lookups then return `None`/`()`, callers fall back to the
aliases declared on the buyer problem, and the run is stamped `no_snapshot__modality_v2`
with an explicit entry in `RunManifest.known_blind_spots`. Runs get narrower, never
silently wrong.

## Building a snapshot

```bash
# ChEMBL only (paged REST pull; no bulk download required)
bve-se-ontology-build --output data/se/ontology/current --chembl-release 36

# Open Targets bulk export (target-agnostic production path)
bve-se-ontology-build --output data/se/ontology/current \
    --open-targets-dir <downloaded target export> --open-targets-release 26.06 \
    --chembl-release 36
```

Override the load path with `BVE_SE_ONTOLOGY_SNAPSHOT`. Call `reset_resolver_cache()`
after installing a new snapshot — the resolver is cached per path.

Neither ingest path accepts a list of targets of interest: the snapshot is built over
the whole upstream slice, so resolution never depends on what was asked for. Do not add
benchmark-specific aliases to make a test pass — that would invalidate the zero-shot
evaluation the roadmap depends on.

## Real-data quirks handled

Both were found by running against the live ChEMBL API, not by reading docs:

- UniProt synonyms arrive field-prefixed (`CD_antigen=CD279`, `Synonyms=PD1`). Taking
  the raw string buries `CD279` behind a prefix no search will match.
- Only `;` separates multiple values. Splitting on commas shreds UniProt recommended
  names — `"4-aminobutyrate aminotransferase, mitochondrial"` became a junk alias
  `"mitochondrial"` that then collided with every mitochondrial protein in the snapshot.
  Fixing this dropped conflict-flagged entities from 223/600 to 36/600, and the
  survivors are genuine homonyms (`ADRA1A`/`ADRA1D`, `p150`, `PCP`).

## Next

- **M9B** — `TrialUniverseProvider` (CT.gov REST v2 first, AACT second, hybrid mode).
  Downstream S&E code must not be able to tell which backend supplied a trial.
- **M9C** — natural language → `SearchIntent` → deterministic compile to `BuyerProblemV2`
- **M9D** — wire broad discovery into the existing orchestrator/ledger/registry/gates
- **Before M11** — build and durably publish the full production snapshot as a
  separately versioned artifact. At that point `no_snapshot__modality_v2` must become an
  **evaluation blocker**, not merely a blind-spot warning: production search may abstain
  without a snapshot, but a benchmark claim may not be scored that way.
