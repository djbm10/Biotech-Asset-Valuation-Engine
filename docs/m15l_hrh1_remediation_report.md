# M15L — HRH1 identity-layer remediation

**Status: frozen.** Run 2026-09-13 on engine `c4f4e65`. Target HRH1, benchmark
`m15_benchmark_v1.json` (sha256 `f3273ebf…f94c`, unchanged from M15).

## 0. What this is, and what it is not

M15L is **not a replay of M15 and is not controlled evidence against it.** The corpus is
newly acquired. That was forced, not chosen:

Once the prose extractor could read generic drug names, the planner began asking follow-up
queries that the sealed M15 corpus had never been asked. The replay refused, by design:

> `clinicaltrials_gov: sealed acquisition records no further attempt for query
> 'Bepotastine'; live discovery and replay have diverged`

That refusal is correct — answering a changed plan out of a fixed set of bytes would be a
different run wearing a replay's name — and it was left alone rather than loosened to
produce a comparable number. The consequence is that a fix to the search plan cannot be
measured on a sealed corpus, and the honest response is a new acquisition plus a plain
statement of what that costs in comparability.

| | M15 | M15L |
|---|---|---|
| role | frozen zero-shot baseline | post-diagnosis remediation |
| corpus | sealed, 4,876 records | newly acquired, 4,761 admitted |
| engine | `e2fcd34` (M14-frozen) | `c4f4e65` |
| target vocabulary | frozen | identical |
| alias admission | measured live | **M15's sealed decisions replayed** (`--alias-probe-in`) |
| benchmark | `f3273ebf…` | `f3273ebf…`, hash-verified by the scorer |

Alias admission is pinned to M15's recorded decisions — including its refusal of `HRH1`,
the target's own gene symbol — so the retrieval plan's adaptive layer cannot have improved
the result underneath the identity layer. Everything else that differs is either the engine
change under test or corpus drift between two acquisitions eleven days apart on the same
as-of date.

## 1. Result

| | M13 SLC6A2 | M14 SLC6A2 | M15 HRH1 (zero-shot) | **M15L HRH1 (remediated)** |
|---|---|---|---|---|
| Discovery | 5/41 (12.2%) | 40/41 (97.6%) | 49/51 (96.1%) | **49/51 (96.1%)** |
| — independently corroborated | — | 20/41 | 35/51 (68.6%) | **35/51 (68.6%)** |
| — authority-seeded only | — | 20/41 | 14/51 | 14/51 |
| — unattributed | — | 0 | 0 | **0** |
| Identification | 0/41 | 4/41 (9.8%) | 6/51 (11.8%) | **41/51 (80.4%)** |
| Target-confirmed | 0 | 4 of 4 | 6 of 6 | **41 of 41** |
| Traps falsely asserted | 0/21 (vacuous) | 0/21 | 0/24, 1 surfaced | **0/24, 5 surfaced** |
| Eligible | 0 | 0 | 0 | 0 |
| Corpus admitted | 2,019 | 16,813 | 4,864 | 4,761 |
| Candidates | 72 | 853 | 42 | 2,119 |
| Identity mentions | — | 1,021 | 53 | 11,361 |

Against the full 66-asset gold set including pre-registry molecules: 50/66 identified.

**Identification moved 11.8% → 80.4% with target precision intact.** Every one of the 41
identified assets was asserted to HRH1 on direct evidence, and not one of the 24 family
traps (HRH2/HRH3/HRH4) was falsely asserted, with five of them now surfacing as candidates
— so that zero is less vacuous than M15's and far less vacuous than M13's.

## 2. What was fixed, and why each fix is target-agnostic

### 2.1 PubMed intake gated on the canonical id (`3e516b1`)

The PubMed adapter admitted a record only if `target.casefold() in text` for each entry of
`query.target_ids` — i.e. it required the literal string `target:hrh1` to appear in an
abstract. All 4,833 PubMed records in M15 were discarded. M14 escaped this only because
SLC6A2 is unambiguous and so resolved to a bare symbol.

Replaced with `vocabulary.targets_in(text)`, the gate CT.gov and the corpus adapter already
used. Tested on two targets, one of them SLC6A2, so a fix reaching only HRH1 would fail.

### 2.2 The normalizer welded digits into molecule names (`4a2b615`)

`normalize_identity_name` joined every letter-digit boundary to collapse `CLN-978`/`CLN
978`/`CLN978`. Because punctuation is *replaced by a space* rather than treated as a
boundary, `Plitidepsin 1.5 mg/day` became `plitidepsin1 5mg day` — the molecule name
destroyed, and with it any chance for a later layer to strip the dose. Bounded to runs of
≤4 characters: a code prefix is short, a molecule name is not.

### 2.3 The prose extractor could not read a small molecule (`c4f4e65`) — the dominant defect

`extract_observed_asset_names` recognized development codes plus six suffixes: `mab`,
`cept`, `parib`, `tinib`, `lisib`, `nib`. Those describe oncology biologics and kinase
inhibitors and nothing else. For any target whose assets are small molecules the extractor
returned cell lines, amino-acid residues and assay constants and not one drug — verbatim
from M15's PubMed mentions: `HEK293`, `LYS191`, `ASN198`, `IC 50`, `EC50`, `MG-132` —
while 148 sealed abstracts named fexofenadine. This is a PDCD1-shaped assumption sitting
inside a supposedly generic extractor, and it is why §2.1 multiplied evidence fourteenfold
without moving identification at all.

The replacement matches a suffix lexicon **counted off the 71,506 DRUG entities of the
frozen ontology snapshot**: a suffix earns its place by being shared by ≥40 chemically
distinct molecules, which is what an INN stem is. Choosing stems by hand after seeing which
drugs a benchmark missed would be hand-mapping, so none were. A prose vocabulary sampled
from the same snapshot's TARGET labels stops `membrane`, `cytokine` and `phosphatase` from
reading as molecules; the twenty amino acids in three-letter form and the assay constants
are closed universal sets. The six legacy suffixes are unioned in, so the change can only
widen what is readable.

Measured on the **sealed** M15 bytes with the planner removed
(`m15_extraction_reach.json`, sha256 `a8f8458f…`):

| on the identical 4,876 sealed snapshots | legacy extractor | derived lexicon |
|---|---|---|
| distinct mentions | 834 | 2,772 |
| identification misses that are even nameable | **0 / 45** | **38 / 45** |

This is the one measurement in this document that *is* controlled against M15: same bytes,
one component swapped. It is an upper bound on identification, not an identification result.

## 3. What still fails — diagnosed, deliberately not fixed

Per the freeze rule, these were diagnosed after the result was computed and **nothing was
tuned in response**. They are the input to M17 or later, not to M16.

### 3.1 Ten identification misses

`DIMETHINDENE`, `DOXEPIN`, `DOXYLAMINE`, `GSK-1004723`, `HISTAMINE`, `KETOTIFEN`,
`LEVOCABASTINE`, `LY2624803`, `PYRILAMINE`, `TRIPELENNAMINE`.

Three distinguishable causes:

1. **Stem-invisible names.** `KETOTIFEN`, `LEVOCABASTINE`, `PYRILAMINE`, `TRIPELENNAMINE`,
   `DIMETHINDENE` end in stems too rare to clear the 40-molecule threshold. Lowering the
   threshold after seeing this list is exactly the retrofit the freeze rule forbids. The
   generic answer is a second, non-frequency signal for name shape, not a nudged constant.
2. **Endogenous-ligand collision.** `HISTAMINE` is blocked by the prose vocabulary because
   it is also the name of the endogenous ligand and appears in the target's own label. The
   block is conservative and correct in kind; distinguishing "drug histamine" from "the
   molecule histamine" is a genuine identity problem, not a lexicon bug.
3. **Undiscovered, not unidentified.** `GSK-1004723` and `LY2624803` are the two discovery
   misses. No document reaching this corpus named them; nothing downstream could recover
   them.

### 3.2 Decoration still rides on names

Unchanged from the M15 diagnosis and still open: dose and strength (`Olanzapine 5 MG`,
`5 mg Desloratadine`), salt and ester forms (`Bepotastine besilate`, `Fexofenadine
Hydrochloride`), combinations collapsed into one string (`azelastine/fluticasone 137/50 mcg
nasal spray`, `Fexofenadine, Ranitidine`), and comparator arms read as assets
(`hydroxyzine/placebo`). These cost recall less than they did before §2.3, because a
decorated CT.gov label is no longer the only route to a name.

### 3.3 Precision is unmeasured at the mention layer

2,119 candidates for 51 gold assets. The trap metric says none of the near-misses that
matter were falsely asserted, and `eligible` remains 0, so no false asset was promoted. But
the mention layer now admits real drugs from unrelated classes that happen to appear in
antihistamine abstracts. The engine treats these as mentions, never as identity, which is
M11's rule holding; whether they impose a review-queue cost is not yet measured.

### 3.4 `MIN_SUPPORTED_DOCS = 5` still cannot tell "contested" from "rare"

Carried forward from M15 unchanged and still not acted on. The probe refused `HRH1` because
CT.gov holds exactly one study naming it, not because a rival claimant contested it. M15L
replayed that refusal deliberately and still reached 80.4%, so the symbol is not load-bearing
— but the threshold conflates two different facts.

## 4. Discipline record

- Target-specific synonyms added: **0**. Hand-mapped assets: **0**. Benchmark rules changed
  after seeing results: **0**. The scorer verifies the benchmark's sha256 and refuses to
  score on a mismatch.
- Every fix had red tests first, and every recovery assertion is paired with the same
  assertion for an unrelated target or therapeutic area.
- M14's frozen result was re-verified from its sealed corpus after §2.1 and §2.2 and did not
  move: 40/41 discovery, 20/41 non-circular, 4/41 identification, identical asset lists.
  After §2.3 the M14 replay diverges for the same planner reason as M15's and was not
  re-scored; M14 stands as published.
- Suite at freeze: 678 passed, 2 xfailed. Ruff clean.

## 5. Sealed artifacts

| artifact | sha256 |
|---|---|
| `m15_benchmark_v1.json` | `f3273ebf33fdd481e587c658c2c47e69fc48b90880fd8d740bb027d7ebfef94c` |
| `m15_hrh1_problem.yaml` | `a2817873e21cdd139c76b61392ffc2b2c55aff80c3f1db313f42b109e2d6f70f` |
| `M15L_result.json` | `4637b8c947e905591374ff98546e6107c9ab76a3278a6cbc63629048ea72f123` |
| `M15_alias_probes.json` (replayed) | `a33a715c6a7243cd2426f1eefb200d3f0525a35cd4d083f294eaa1a8f6cf5aef` |
| `M15L_score.json` | `3d1f9664ac72d0526aa0604a1a153e2b8680f5558daef6878399b0d22871d552` |
| `m15_extraction_reach.json` | `a8f8458fda7d9a940418b6e08471453bf700d459f3734cd6de7b040c0e7fe50f` |
| `score_zero_shot.py` | `c3e8c1028448eebe2103859be2c6cd94adf5bc7fb4a485138a63f33a698b182d` |
| `measure_extraction_reach.py` | `a1e3c40c59233504c2ed64c916dfd5f602ce83679479850bf4a2a7e566efb1c0` |
| `run_m15l.sh` | `01c75951dcb3b161cd1ba255c9a58cac901a89968989b1880fe61d442a3467f7` |

Custody ledger: 4,773 lines.

## 6. What M15L does not establish

It does not establish that the engine generalizes. HRH1 has been diagnosed against twice;
its misses were read, catalogued and reasoned about before these fixes were written. The
fixes were built to be target-agnostic and tested that way, but only an untouched target
can show whether they are.

That is M16, drawn mechanically under rules frozen before the pool was computed.
