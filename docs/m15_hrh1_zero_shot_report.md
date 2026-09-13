# M15 — HRH1 zero-shot generalization

**Status: frozen and published. No code was changed for HRH1 before this result was
produced, and nothing in this document was tuned after seeing it.**

The engine that produced M15 is byte-identical to the engine M14 froze (`e2fcd34`). The
target was drawn mechanically from a candidate pool computed under rules written before the
pool existed. M15 is therefore a real zero-shot measurement: the second one, and the first
where the previous milestone's remediation had a chance to generalize or fail to.

---

## 1. Headline

| | M13 SLC6A2 (frozen) | M14 SLC6A2 (remediated) | **M15 HRH1 (zero-shot)** |
|---|---|---|---|
| Discovery | 5/41 (12.2%) | 40/41 (97.6%) | **49/51 (96.1%)** |
| — independently corroborated | — | 20/41 (48.8%) | **35/51 (68.6%)** |
| — authority-seeded only | — | 20/41 | 14/51 |
| — unattributed | — | 0 | 0 |
| Identification | 0/41 | 4/41 (9.8%) | **6/51 (11.8%)** |
| Target-confirmed | 0 | 4 of 4 identified | **6 of 6 identified** |
| Traps falsely asserted | 0 of 21, vacuously | 0 of 21 | **0 of 24, non-vacuously** |
| Eligible | 0 | 0 | 0 |
| Corpus admitted | 2,019 | 16,813 | 4,864 |
| Candidates | 72 | 853 | 42 |

Denominator: the 51 registry-reachable gold molecules. The full gold set is 66; the other
15 have no CT.gov record at all and scoring the engine for missing them would measure the
registry. Benchmark artifact verified by content hash at scoring time
(`f3273ebf…f94c`), so "the denominators did not move" is a checked claim rather than a
restatement of the file's own fields.

### What generalized

**Discovery generalized, and it improved in the way that matters.** The headline rate is
flat (97.6% → 96.1%), but the non-circular component rose from 48.8% to 68.6%. That is the
number that is not an artifact of the gold set having been cut from the same
`DIRECT_TARGET` edges the authority-seeding path reads. 35 of 51 HRH1 molecules were
reached by target-vocabulary retrieval that did not already know the answer.

**Precision generalized and is no longer vacuous.** M13's zero false assertions meant
nothing, because it asserted nothing at all. M15 made six identifications, all six were
target-confirmed, and none of the 24 traps was falsely asserted. The traps for HRH1 include
its own paralogue family (HRH2/HRH3/HRH4) — the hardest available negatives — and the
M11 rule that co-occurrence is never identity held on all of them without modification.

**The alias-admission probe generalized, including against the target's own symbol.**

### What did not generalize

**Identification did not.** 11.8% is barely above M14's 9.8%, and both are catastrophic
against the ~87% the PDCD1 baseline reached. 49 of 51 gold molecules are physically present
in the admitted corpus text and only 6 become correctly named assets. This is now, by a
wide margin, the binding constraint on the whole system.

---

## 2. The probe refused the target's own symbol, and that was correct

`HRH1` is a shared alias: `TARGET:DHX8` claims it too, because DHX8's protein name is
"RNA helicase HRH1". The frozen `retrieval_alias_admission_v1` probe therefore had to
decide whether `HRH1` may be searched, and it refused:

| alias | claimants | probe docs | supporting HRH1 | decision |
|---|---|---|---|---|
| `HRH1` | `TARGET:DHX8`, `TARGET:HRH1` | 1 | 1 | `RETRIEVAL_AMBIGUOUS` (policy requires 5) |

The refusal was not driven by ambiguity in the evidence — DHX8 got zero supporting
documents. It was driven by **absence** of evidence: a CT.gov probe for `HRH1` returns
exactly one study in the entire registry. Trials do not name histamine receptors by gene
symbol.

This is the fail-closed rule behaving as designed, and it must not be softened on the
strength of this outcome. It is also a genuine finding about the policy's shape: a
`MIN_SUPPORTED_DOCS = 5` floor cannot distinguish "contested" from "rare", and for any
target whose literature does not use gene symbols, the floor removes the symbol. Whether
that distinction should be drawn is a live question, but drawing it now, having seen that
it costs HRH1 its own symbol, would be exactly the retrofitting the freeze exists to
prevent. Recorded, not acted on.

M15 consequently ran on the seven sole-claimant aliases (`H1-R`, `H1R`, `HH1R`, `hisH1`,
`Histamine H1 receptor`, `histamine receptor H1`, `histamine receptor, subclass H1`) and
still reached 96% of the gold set. The symbol was not load-bearing.

---

## 3. Diagnosis: where the 45 identification misses go

Published as diagnosis only. No remediation is included in M15, and none of what follows
was used to alter any M15 number.

### 3.1 The dominant defect: 99.4% of the corpus never reaches identity extraction

| | records acquired | became source documents | share |
|---|---|---|---|
| clinicaltrials_gov | 31 | 31 | 100% |
| pubmed | 4,833 | **0** | **0%** |

4,833 PubMed records were fetched, admitted to custody, and sealed — and not one of them
entered the pipeline as a document. The cause is a single line in the PubMed adapter
(`adapters.py:1062`):

```python
if not all(target.casefold() in text for target in query.target_ids):
    continue
```

`query.target_ids` for M15 is `('TARGET:HRH1',)` — the *canonical identifier*, not a
searchable string. The adapter therefore discards any abstract that does not literally
contain the text `target:hrh1`, which no abstract ever does. Every PubMed record was
dropped.

M14 scored 44 PubMed documents only by luck: `SLC6A2` is an unambiguous symbol, so M13's
problem file could declare `canonical_id: SLC6A2`, `target_ids` was the bare symbol, and
the substring test occasionally matched. The moment a target's bare symbol is ambiguous —
and `HRH1`, `PD-1` and `NET` all are — the prefixed canonical id is mandatory and this gate
silently drops the entire source family. It is not an HRH1 problem. It is a defect that
fires for every target whose symbol is contested, and it has been silently suppressing
PubMed on those targets all along.

Three separate faults are stacked in that one line: it tests the canonical id instead of
the admitted target vocabulary; it ignores every alias; and it uses naive substring
containment rather than word boundaries, so a symbol like `NET` matches "network".

### 3.2 Name extraction: the asset name is a regimen description, not a molecule

Of the 53 identity mentions M15 did produce, the raw CT.gov intervention labels show four
further target-agnostic defects:

| defect | observed | consequence |
|---|---|---|
| dose/strength/route retained | `Plitidepsin 1.5 mg/day`, `Olanzapine 5 MG`, `5 mg Desloratadine` | never equals the canonical name |
| salt/ester form retained | `Bepotastine besilate`, `Fexofenadine Hydrochloride` | same molecule, different string |
| combinations collapsed | `azelastine/fluticasone 137/50 mcg nasal spray`, `Fexofenadine, Ranitidine`, `Aripiprazole/Escitalopram combination` | two molecules become one non-existent one |
| comparator arms treated as assets | `hydroxyzine/placebo` | placebo enters the identity space |

And the normalizer itself is lossy in a way that compounds all four:

```
'Plitidepsin 1.5 mg/day'  ->  'plitidepsin1 5mg day'
'H1 receptor blockade'    ->  'h1receptor blockade'
```

Punctuation is being **deleted** rather than treated as a token boundary, so the `.` in
`1.5` vanishes and glues `1` onto `plitidepsin`. No amount of dose-stripping downstream can
recover a molecule name that has had a digit welded to it.

### 3.3 Bounding the two layers

Only 5 of the 45 missed molecules (`AZELASTINE`, `BEPOTASTINE`, `DESLORATADINE`,
`FEXOFENADINE`, `HYDROXYZINE`) are recoverable from a CT.gov raw mention by fixing §3.2
alone. The remaining 40 are reachable **only** in PubMed text that §3.1 throws away. The
extraction/normalization defects are real and worth fixing on their merits, but the
document-intake gate is where the identification result actually lives.

---

## 4. Discipline record

- No code changed between `e2fcd34` and this run. M15 measured the M14 engine.
- The target was drawn mechanically; the pool rules were frozen before the pool was computed.
- The benchmark's content hash is verified at scoring time; a moved benchmark voids the score.
- No asset was hand-mapped. No target-specific synonym was added. Both counters are 0 in
  `M15_score.json`.
- The scorer (`score_zero_shot.py`) is target-generic and was **validated by replication**:
  pointed at M14's sealed artifacts it reproduces all 15 published M14 fields exactly,
  including the full corroborated and seeded-only asset lists. It imports the frozen
  yardstick from `score_M13.py` rather than reimplementing it.
- M13 remains at 5/41 and 0/41. M14 remains at 40/41, 20/41 non-circular, 4/41.
- The probe refusal of `HRH1` is published as it happened and was not overridden.
- One process ran; no collision.

## 5. Sealed artifacts

| sha256 | artifact |
|---|---|
| `f3273ebf33fdd481e587c658c2c47e69fc48b90880fd8d740bb027d7ebfef94c` | `m15_benchmark_v1.json` |
| `6bacd95e78db4b66e28b47b406939d67a7066773a80b84ef51f96d9a7fa2e6f0` | `m15_candidate_pool.json` |
| `f19abb7b7adedce1e597af44a2c0a5e0dae01848baadb5b698d9752b71079538` | `m15_selection.json` |
| `b40e63490c9a92d25210d13b05665bc6d61fca67be5c0dead95f0715394b7c1b` | `m15_pool_rules.json` |
| `a2817873e21cdd139c76b61392ffc2b2c55aff80c3f1db313f42b109e2d6f70f` | `m15_hrh1_problem.yaml` |
| `95ef887534f1139fb61645409b4c279788909bcfa22248e2afbf9845a0d1ac4b` | `M15_result.json` |
| `a33a715c6a7243cd2426f1eefb200d3f0525a35cd4d083f294eaa1a8f6cf5aef` | `M15_alias_probes.json` |
| `f1a3faf9a02afae20ecb6b26e655e8fff2826b82f0460478abd46cb1d43bffeb` | `M15_score.json` |
| `c3e8c1028448eebe2103859be2c6cd94adf5bc7fb4a485138a63f33a698b182d` | `score_zero_shot.py` |
| `effa6dbfdf7d2fd9d31068b28f9b40d8df258c9b8cf0e1665546d8e09e3a1204` | `run_m15.sh` |

Custody: `M15_custody/acquisition_ledger.jsonl`, 4,876 lines. Snapshots under
`M15_snapshots/`. The corpus is sealed and will be replayed for the M15 remediation
benchmark rather than re-acquired, so that remediation is measured against identical
evidence.
