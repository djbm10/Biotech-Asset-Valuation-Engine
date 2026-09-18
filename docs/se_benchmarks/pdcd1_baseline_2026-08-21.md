# PDCD1 baseline — first evaluation of the generalized S&E pipeline

**Date:** 2026-08-21 · **Status:** baseline recorded; run did not converge (see below)

This is the first run of the generalized discovery pipeline against a target it was
not built around. All inputs were frozen before any result was inspected;
the frozen record is `frozen_inputs.json` in the run directory.

## Frozen inputs

| Input | Value |
|---|---|
| M8 gold standard | `pdcd1-rebase-v1-m8-benchmark-final-v2-67cf77f410194a03a4290442` (224 canonical candidates) |
| M8 archive sha256 | `233fd39ad16a9686d131913206ce4dac414b79473f24e7e269dcae92096efef5` |
| Ontology release | `se-ontology-snapshot-chembl37-ot26.06-56bc8d70c81dc8c41035be10` |
| Ontology payload sha256 | `56bc8d70c81dc8c41035be100c1507abda2481306cb7745d3f0f5a8dc847f7e9` |
| Runtime ontology_version | `chembl_ChEMBL_37__open_targets_26.06__resolver_v1__modality_v2` |
| Trial universe provider | `ctgov_rest` v2 (ClinicalTrials.gov REST v2, live) |
| Extractor | `clinicaltrials_v2` v1 · normalization `cd19_bcma_v1+t_cell_engager_v1` |
| BuyerProblem | `baseline_pdcd1_landscape` v1.0.0, target `PDCD1`, all 17 modality_v2 modalities |
| Pipeline commit | `814bb04514aee68992fe829af0cc191a979762f8` |

The scored query uses canonical `PDCD1`. The bare nickname `"PD-1"` is measured
separately as a product-behaviour smoke test and is not scored for recall.

## Defect found and fixed before scoring

The first attempt lost ClinicalTrials.gov entirely. The ontology-derived alias
expansion went into one `query.intr` value and CT.gov answered
`400 Too complicated query` — its Essie parser counts *words*, not terms, and refuses
past roughly a dozen. CD19/BCMA never reached that cliff; a real ontology does.

Fixed in `814bb04` (batch the terms under a word budget, union and dedupe by NCT id,
fail the fetch if any batch fails) with regression tests. Against the live API the
real PDCD1 expansion now returns 403 trials instead of zero. The failed run is kept
at `result_A_pdcd1_PREFIX_run0_ctgov_failed.json` as the evidence, and is not scored.

## A. Scientific benchmark (query target = PDCD1)

| Metric | Value |
|---|---|
| Run status | **INCOMPLETE** — 7 mandatory sources unavailable (`connector not configured`) |
| Candidate recall vs 224 M5 canonical candidates | **39 / 224 = 17.4 %** |
| Observed candidates | 100 |
| Trial coverage | 250 records returned, **`truncated: true`** |
| False candidate merges | 8 observed assets each covering 2–11 distinct gold entries |
| False candidate inventions | 81 |
| Eligible / excluded / unresolved | 0 / 0 / **100** |
| Review queue | 863 |
| Canonical identities formed | **0** across all 4 coverage passes |
| Evidence | 254 mentions · 291 documents · 1315 claims · 950 facts · 115 companies · 0 clinical results |

Source outcome: `clinicaltrials_gov` SUCCESS, `pubmed` PARTIAL, and
`company_pipeline_or_presentation`, `company_press_release`, `sec_edgar`,
`conference_{ash,asco,aacr,eha}` all FAILED with `connector not configured`.

### Miss breakdown (185 misses)

| Category | Count | Meaning |
|---|---|---|
| **discovery** | 165 | gold asset name never appears in any retrieved document |
| **extraction** | 20 | name present in retrieved text, but no identity mention was produced |
| identity | 0 | — |
| ontology | 0 | — |
| evidence | 0 | — |
| gate | 0 | — |

No miss is attributable to the ontology or to a gate: nothing was ever gated, because
no candidate reached eligibility. 38 of the 185 misses are chemotherapy backbones,
comparators or placebo (cisplatin, carboplatin, gemcitabine, Abraxane, radiotherapy),
which the M8 gold set includes as co-administered agents in PDCD1 trials.

### What this points at

The bottleneck is **retrieval breadth, not entity resolution**. Two concrete causes,
both upstream of anything AACT would change:

1. **`page_size = 250` is hardcoded** in `src/bve/se/discovery/adapters.py:424` and
   doubles as `max_records`. The seed fetch was truncated at 250 of 403+ available
   trials from a single expansion, and CT.gov holds far more PD-1 trials than that.
   There is no CLI flag to raise it.
2. **Seven of nine mandatory sources have no connector.** Company pipelines, press
   releases, SEC filings and the four conferences contributed zero documents, so any
   asset whose only public trace is a conference abstract or a pipeline page cannot be
   found at all. This is also what keeps the run from ever converging.

The 0 canonical identities and 863-deep review queue are a downstream consequence:
with only trial-registry and PubMed text and no corroborating source family, the
identity layer has nothing to promote a provisional identity on.

## B. Product-behaviour smoke test (user query = "PD-1")

**Expected:** AMBIGUOUS / clarification. **Observed:** silent literal search. **FAIL.**

The resolver is correct on its own:

```
'PD-1'   → ResolutionStatus.AMBIGUOUS   (abstains)
'PD1'    → ResolutionStatus.AMBIGUOUS   (abstains)
'PDCD1'  → RESOLVED → TARGET:PDCD1
'CD279'  → RESOLVED → TARGET:PDCD1
'HER2'   → RESOLVED → TARGET:ERBB2
'BCMA'   → RESOLVED → TARGET:TNFRSF17
```

But the search layer discards that abstention. The run proceeded with the literal
string `PD-1` as its only seed term — no ontology expansion at all, versus 216 distinct
alias terms in run A — and returned 233 candidates with no ambiguity, clarification or
abstention signal anywhere in the output. The output contains zero occurrences of
`AMBIGUOUS`, `ambiguity`, `abstain` or `disambiguation`.

Per the benchmark design this is **not** counted as a candidate-recall failure. It is a
query-interface safety defect: an ambiguous nickname silently degrades to an
unexpanded literal search instead of asking the user which entity they meant.

## Recommendation for M9E / M10

The miss breakdown does not support AACT as the next priority. AACT would change
throughput on the one source that already succeeded. The 165 discovery misses are
caused by a 250-record cap and by seven missing connectors, neither of which AACT
addresses. In priority order:

1. Make the trial-universe record cap configurable and raise it (small, unblocks the
   largest single share of misses).
2. Propagate the resolver's AMBIGUOUS status into the query interface so an
   ambiguous nickname asks for clarification instead of searching literally.
3. Wire at least the company-pipeline and press-release connectors, without which no
   run of this shape can converge.
4. Only then revisit AACT for throughput.

## Artifacts

Run directory `/home/djmann/staging/pdcd1_baseline/`:
`frozen_inputs.json`, `pdcd1_baseline_problem.yaml`, `pd1_smoke_problem.yaml`,
`pdcd1_reference_universe_m8v2.csv`, `result_A_pdcd1.json`, `scorecard_A.json`,
`miss_breakdown_A.json`, `result_B_pd1_smoke.json`,
`result_A_pdcd1_PREFIX_run0_ctgov_failed.json`.
