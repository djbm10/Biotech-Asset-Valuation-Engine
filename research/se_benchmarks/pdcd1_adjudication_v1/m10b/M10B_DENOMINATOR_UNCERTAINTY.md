# M10B — Denominator Uncertainty Resolution

Descriptive only. The frozen V1 adjudication rules (`GOLD_ENTRY_ROLE_RULES.md`, tip
`fe5d03d2…`) are untouched, and no new authority is introduced. Nothing here re-runs the
pipeline or changes identity/extraction.

## entity_role x target_relevance

| entity_role | PDCD1_MATCH | NON_PDCD1 | UNCERTAIN | total |
|---|---|---|---|---|
| ASSET | 28 | 106 | 48 | 182 |
| COMBINATION_REGIMEN | 0 | 1 | 15 | 16 |
| INDICATION | 0 | 0 | 1 | 1 |
| PLACEHOLDER_DESCRIPTION | 0 | 0 | 1 | 1 |
| UNCERTAIN | 0 | 0 | 24 | 24 |
| total | 28 | 107 | 89 | 224 |

## Corrected recall bound

`entity_role` and `target_relevance` are separate dimensions, so only `ASSET + UNCERTAIN`
(48) can ever join the PDCD1-asset denominator. The other 41 UNCERTAIN entries are not
assets at all, and adding them understates the pipeline.

- confirmed: 25/28 = **89.3%** (best case; every uncertain entry turns out not to be PDCD1)
- worst case: 37/76 = **48.7%** (every uncertain ASSET turns out to be PDCD1)

## Why each of the 48 is uncertain

| subtype | n | identified | missed |
|---|---|---|---|
| AUTHORITY_HAS_MOLECULE_BUT_NO_MOA | 20 | 5 | 15 |
| DEVELOPMENT_CODE_ABSENT_FROM_AUTHORITY | 12 | 5 | 7 |
| NAME_UNRESOLVED_IN_AUTHORITY | 6 | 2 | 4 |
| CELL_THERAPY_VACCINE_OR_CONSTRUCT | 5 | 0 | 5 |
| BIOSIMILAR_CANDIDATE | 3 | 0 | 3 |
| NON_SMALL_MOLECULE_TRADITIONAL_MEDICINE | 2 | 0 | 2 |
| total | 48 | 12 | 36 |

The coformulation subtypes score zero here because those entries carry
`entity_role=COMBINATION_REGIMEN`, not `ASSET`. That is A3.3 behaving as intended, not a
gap in the partition.

## The three confirmed misses

| entry | reachable | extracted | identified | diagnosis |
|---|---|---|---|---|
| Budigalimab (ABBV-181) | yes | no | no | extraction failure |
| Budigalimab | yes | no | no | duplicate presentation of the same molecule |
| Dostarlimab-gxly (GSK4057190 / TSR-042, JEMPERLI) | yes | yes | no | alias binding failure |

Both Budigalimab entries rest on a single reachable trial, NCT04223804, whose attrition
ledger row is `NO_ASSET_NAME_EXTRACTED` / `MODALITY_NOT_CONFIRMED`. The registry does
carry the names (`interventions: ABBV-181`, `other_names: Budigalimab`), so this is one
extraction failure on one trial, counted twice by the benchmark.

Dostarlimab-gxly was extracted: the pipeline emitted the mention `dostarlimab`, which
satisfies the sibling M8 entry `Dostarlimab` (identified=True) but not the hyphenated
`Dostarlimab-gxly` under exact alias matching. The molecule was found; the alias string
was not bound to it.

So the three misses are two molecules and two root causes -- one trial-level extraction
failure and one alias-binding gap -- not a broad identity deficiency.
