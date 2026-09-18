# M16 — HTR2A zero-shot generalization test

**Status: frozen.** Run 2026-09-13 on engine `d653c8a` (the M15L-remediated architecture,
unmodified). Target HTR2A, benchmark `m16_benchmark_v1.json`
(sha256 `70f97611…dea5f`), verified by the scorer before scoring.

M16 is the decisive test of whether the M15L identity-layer remediation generalized. The
target was drawn mechanically; no component was tuned against it before this result was
computed, and nothing has been tuned against it since.

## 1. Result

| | M13 SLC6A2 | M14 SLC6A2 | M15 HRH1 zero-shot | M15L HRH1 remediated | **M16 HTR2A zero-shot** |
|---|---|---|---|---|---|
| Discovery | 5/41 (12.2%) | 40/41 | 49/51 (96.1%) | 49/51 | **40/41 (97.6%)** |
| — independently corroborated | — | 20/41 | 35/51 (68.6%) | 35/51 | **22/41 (53.7%)** |
| — authority-seeded only | — | 20/41 | 14/51 | 14/51 | **18/41** |
| — unattributed | — | 0 | 0 | 0 | **0** |
| Identification | 0/41 | 4/41 (9.8%) | 6/51 (11.8%) | 41/51 (80.4%) | **29/41 (70.7%)** |
| Target assertions | 0 | 4 | 6 | 41 | **30** |
| — outside the gold set | 0 | 0 | 0 | 0 | **0** |
| Traps falsely asserted | 0/21 (vacuous) | 0/21 | 0/24, 1 surfaced | 0/24, 5 surfaced | **0/7, 2 surfaced** |
| Eligible | 0 | 0 | 0 | 0 | 0 |
| Corpus admitted | 2,019 | 16,813 | 4,864 | 4,761 | 3,661 |
| Candidates | 72 | 853 | 42 | 2,119 | 2,170 |
| Identity mentions | — | 1,021 | 53 | 11,361 | 10,201 |

Against the full 45-asset gold set including pre-registry molecules: 31/45.

**The remediation generalized.** On a target the engine had never seen, identification is
**70.7%**, against **11.8%** for the last zero-shot target under the pre-remediation
architecture. Every one of the 30 target assertions is a gold molecule — zero false
assertions, inside or outside the family — and none of the 7 HTR2B/HTR2C traps was
asserted, with 2 of them surfacing as candidates, so that zero is not vacuous.

The honest comparison is M15 (11.8%) → M16 (70.7%), both zero-shot. M15L's 80.4% is not
the comparator: HTR2A is harder in one respect that matters, namely that 18 of its 40
discovered assets were reached only through the authority seed, against 14 of 49 for HRH1.

### Independence from the HRH1 work

HTR2A and HRH1 are both aminergic GPCRs, which raised a fair question about whether M16 is
really an independent test. Measured rather than assumed: the two gold sets share
**2 molecules** — ESMIRTAZAPINE and TRIMIPRAMINE. 28 of the 30 assets M16 asserted are
absent from the HRH1 benchmark entirely, and the therapeutic area (psychiatry/neurology)
and drug classes (antipsychotics, serotonergics, psychedelics) are disjoint from
antihistamines. The overlap is too small to carry the result.

## 2. How the target was drawn

`m16_pool_rules.json` (sha256 `ec00e2c1…`) was frozen before the pool was computed, all
thresholds and selection mechanics inherited unchanged from M15. Funnel: 888 targets with
edges → 17 passed `min_distinct_drugs 40` → 17 passed `max_mab_fraction 0.30` → 15 passed
rules 1 and 7 → 7 passed rule 6. Seed = int of the sha256 of the frozen pool file, one
binding `random.choice` draw: **HTR2A** (72 distinct drugs, 0% mAb).

### Two declared amendments

Both were made after observing something, and both are recorded in the artifacts rather
than in this report alone.

**Rule 6 amendment 3 — the prior-contact test was self-defeating.** The first pool came
back **empty**: all 15 survivors rejected. The hits were overwhelmingly retrieved PubMed
abstracts and CT.gov records under `outputs/se/snapshots/` and the `B8_*_snapshots/` trees
that merely *mention* a gene symbol — ADRB1 in four abstracts, HTR2C in two. The rule's own
text already excludes "replay/result/corpus artifacts"; the implementation had named a few
directories instead of excluding the kind. Since every run enlarges the corpus, left alone
the rule rejects every candidate forever. The exclusion now covers `*snapshots*` and
`*custody*` directories and `result_*.json` wherever they live. Declared in the rules file
as made **after** seeing the empty pool but **before** looking at which symbols it restored,
and justified on the principle rather than on the symbols.

A separate rule-6 defect is noted and deliberately **not** fixed: `\bAR\b` and `\bMET\b`
match ordinary English case-insensitively, so AR (1,374 files) and MET (10,473) are rejected
by false positives. That is conservative — it can only shrink the pool — but it permanently
excludes short symbols from every future draw.

**Benchmark builder amendment — the trap metric would have silently vanished.**
`family_of()` requires a trailing digit, so `HTR2A` yielded no family stem, the sibling set
came out empty and `traps_n` was **0** — not "no traps were asserted" but "no trap metric
exists", which is exactly the vacuity that made M13's zero meaningless. A subunit rule
(`^([A-Z]+\d+)([A-Z])$`) now fires *only* when the numbered rule fails. SLC6A2 and HRH1 were
rebuilt and both raw benchmarks are **byte-identical** to the frozen originals; M13, M14,
M15 and M15L are untouched. The change is strictly adversarial — it adds 7 molecules the
engine must not assert and removes them from the negatives — so it cannot raise any M16
score. It is recorded in the benchmark under `benchmark_builder_amendment`.

## 3. What still fails — diagnosed, deliberately not fixed

Per the freeze rule these were read after the result was computed and nothing was tuned in
response.

**The 12 identification misses.** `BLONANSERIN`, `CHLORPROTHIXENE`, `CYCLOBENZAPRINE`,
`EPLIVANSERIN`, `IFERANSERIN`, `NELOTANSERIN`, `SARPOGRELATE`, `SB-773812`, `TEMANOGREL`,
`THIOTHIXENE`, `VABICASERIN`, `VOLINANSERIN`.

1. **The `-anserin` class is the single largest cluster** — EPLIVANSERIN, IFERANSERIN,
   NELOTANSERIN, VOLINANSERIN, and VABICASERIN alongside them. This is the stem-invisible
   failure predicted in M15L §3.1, reproducing on an untouched target and on a different
   stem: `anserin` is shared by too few molecules to clear the lexicon's 40-molecule
   threshold. It is now confirmed as a generic failure mode rather than an HRH1 artifact,
   and it is the clearest candidate for the next remediation. Lowering the threshold is
   still the forbidden retrofit; the generic answer remains a second, non-frequency signal
   for name shape.
2. **`SB-773812` was asserted to HTR2A but scored as an identification miss.** It appears
   in the target-assertion list and in the missed list simultaneously, so the engine found
   the molecule and reached the right target while the identification matcher failed to
   equate its name with the gold string — most likely development-code punctuation. A real
   defect, worth one test, and untouched until this result is frozen.
3. **`TEMANOGREL` is the sole discovery miss.** No document reaching this corpus named it.

**Authority-seeded share rose.** 18/40 discovered assets were reached only through the
authority seed, against 14/49 for HRH1. Discovery still assumes a target is named in its
assets' documents; where it is not, the ontology carries the result, and that recovery is
circular by construction because the gold set is cut from the same edges. This is reported
separately from the headline for exactly that reason.

**Precision at the mention layer remains unmeasured.** 2,170 candidates for 41 gold assets.
The traps hold, `eligible` is 0, and no false assertion was made — but whether the mention
layer imposes a review-queue cost is still not quantified, unchanged from M15L §3.3.

## 4. Discipline record

- Target-specific synonyms added: **0**. Hand-mapped assets: **0**. Engine changes between
  M15L and M16: **none** — M16 ran on `d653c8a` exactly as frozen.
- The scorer verified the benchmark sha256 before scoring and would have refused a mismatch.
- No HTR2A alias is contested in this snapshot, so the admission probe had nothing to rule
  on; probe decisions were recorded live (`M16_alias_probes.json`) rather than replayed.
- Two amendments were made after observing an outcome; both are declared in the artifacts,
  both are argued from principle, and one is provably unable to improve any score.

## 5. Sealed artifacts

| artifact | sha256 |
|---|---|
| `m16_pool_rules.json` | `ec00e2c114b1fe60dd89605cf950d6a01efc80c1f6d2889ba90d7bbb2406446e` |
| `m16_candidate_pool.json` | `6faf60fb2101d7916783997cefb5cc05a5eb5c9137f9516138f3b0b894e5c560` |
| `m16_selection.json` | `86d497564aa090bf4617c749bd4f717f85bb4834f8cfd09856450dcd7bf36a89` |
| `m16_benchmark_v1.json` | `70f97611a6782587dc363fca4af5363060eeffee8a3be4ee4d63f26976adea5f` |
| `m16_htr2a_problem.yaml` | `23aae5ebadc8344d4144eac4e60e61afbf6cf43bba7726dffcff3b971702f1e4` |
| `m16_registry_reach.json` | `0294abead6fcca9df5b02d84bee4f18b45775ef311dce28e9ae97688ce91f62d` |
| `M16_result.json` | `84704947d874ccb3783fc7c40bd7202f44be4e674e9bda45c5ac121e9a38439e` |
| `M16_score.json` | `97f6e2af1e4be49e689058e1d096cf5bcd6eabe06364ef20a1eaee945dcc8cb6` |
| `M16_alias_probes.json` | `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570` |
| `run_m16.sh` | `36ecdf0bf221ce4ed0e83e0627aab6b8321fab98a30772978d628fb40e44bd7d` |
| `score_zero_shot.py` | `93e9c92b0baf1ade85fb2957d850823321a48192c070a692691e44e8690f854a` |
| `m13_build_benchmark.py` | `caf6f0b42d8534384c3e4c54cdd008b8de16f8cdd4a1ee640bfa447f1869c34b` |
| `m16_build_pool.py` | `016479dda84a1941de97218a332f7907e3f5b857480e01c41d18f263d9d90305` |
| `m16_registry_reach.py` | `27279f008521034e1715ad2edb0cecd0fc071eff6199a8a6ccff2ce84a20f185` |

Acquisition ledger: 3,667 lines. Corpus: 3,661 records admitted, 0 orphans.

## 6. What M16 does establish, and what it does not

It establishes that the identity remediation is **not** HRH1-specific: an untouched target
in an unrelated therapeutic area, with a two-molecule gold overlap, went from an
architecture that identified 11.8% zero-shot to one that identifies 70.7% zero-shot, with
zero false target assertions and a non-vacuous trap result.

It does not establish that the engine is finished. Three targets is three targets; all
three are small-molecule receptor targets reached mainly through CT.gov and PubMed, and no
biologic-heavy or pre-clinical-heavy target has been drawn. Discovery still leans on the
authority seed where documents do not name the target, and the `-anserin` cluster shows the
lexicon's frequency threshold failing in a way that will recur on every target with a small
drug class.
