# M17 — CHRM1 zero-shot generalization test

**Status: frozen.** Run 2026-09-13 on engine `aeea608` (M16 architecture plus the two
generic identity remediations described in §3, unmodified thereafter). Target CHRM1,
benchmark `m17_benchmark_v1.json` (sha256 `03876755…3ec83`), verified by the scorer against
its frozen pin before scoring. Exit status 2 (`INCOMPLETE`) is the expected diagnostic
state for a discovery-only run.

M17 asks whether the identity remediation built after M16 generalizes to a target drawn
mechanically afterwards. Nothing was tuned against CHRM1 before this result was computed.

## 1. Result

| | M13 SLC6A2 | M15 HRH1 | M16 HTR2A | **M17 CHRM1** |
|---|---|---|---|---|
| Discovery | 5/41 (12.2%) | 49/51 (96.1%) | 40/41 (97.6%) | **21/21 (100%)** |
| — independently corroborated | — | 35 (68.6%) | 22 (53.7%) | **7 (33.3%)** |
| — authority-seeded only | — | 14 | 18 | **14** |
| — unattributed | — | 0 | 0 | **0** |
| Identification | 0/41 | 6/51 (11.8%) | 29/41 (70.7%) | **21/21 (100%)** |
| Target assertions | 0 | 6 | 30 | **21** |
| — outside the gold set | 0 | 0 | 0 | **0** |
| Traps falsely asserted | 0/21 (vacuous) | 0/24, 1 surfaced | 0/7, 2 surfaced | **0/26, 16 surfaced** |
| Corpus admitted | 2,019 | 4,864 | 3,661 | **15,454** |
| Candidates | 72 | 42 | 2,170 | **8,080** |
| Identity mentions | — | 53 | 10,201 | **56,395** |

Against the full gold set including pre-registry molecules: **32/32**.

Every registry-reachable gold asset was discovered, identified, and correctly attributed.
All 21 target assertions are gold molecules; none is a trap and none falls outside the gold
set. The trap zero is emphatically not vacuous — **16 of the 26 traps surfaced as
candidates** and were each declined, the highest trap exposure of any milestone so far.

That matters more here than in any previous draw. CHRM1's traps are its own subtypes
(CHRM2/3/4): muscarinic subtype selectivity is a genuine pharmacological problem, the
sibling symbols differ by one character, and the literature discusses them together
constantly. The engine saw two-thirds of them and asserted none.

## 2. The caveat that belongs next to the headline

**Independent corroboration fell to 33.3%, the lowest of any milestone.** 14 of the 21
discovered assets were reached only through the authority seed, and the gold set was cut
from the same DIRECT_TARGET edges that seed the acquisition path — so that recovery is
circular by construction and is reported separately rather than folded into the headline.

Only 7 assets — ATROPINE, BENZTROPINE, MK-7622, PILOCARPINE, PIRENZEPINE, SCOPOLAMINE,
XANOMELINE — were corroborated by evidence the seed did not supply.

So the honest reading of 100%/100% is: on this target the engine identified everything it
discovered, and discovered everything the benchmark deemed reachable, but a larger share of
that reach than usual was owed to the ontology rather than to the corpus. The
identification result is the load-bearing one; the discovery result is partly a restatement
of the seed.

A second structural note: the registry-reachable denominator (21) equals the discovery
denominator, and all 11 pre-registry molecules also identified, giving 32/32 overall. CHRM1
is an old target whose drugs are almost all well-documented, which makes it easier than
HTR2A on identification and harder on corpus volume.

## 3. What changed between M16 and M17

Two generic remediations, both built before the CHRM1 draw and frozen before this run.

### 3.1 The canonical identity contract (`e689936`)

M16's SB-773812 was resolved correctly and asserted to HTR2A correctly, yet scored an
identification miss. The cause was two name spaces: `IdentityMention.normalized_asset_name`
is `normalize_identity_name(raw)` (`sb773812`) while `CanonicalAsset.canonical_name` is the
display string (`SB-773812`). Anything joining assets to mentions *by name* compared across
the two and silently dropped every asset whose name carries punctuation — which is every
development code.

`AssetRegistry._alias_keys` already computed the right keys for its own index but never
published them, so each caller re-derived the convention and the scorer derived it wrong.
Fixed by publishing `CanonicalAsset.identity_keys` at `_index_asset`, the single write path.

Under the corrected harness the same frozen result files read M16 **30/41** (published
29/41) and M15L **42/51** (published 41/51); M15 is unchanged. These corrected figures are
reported alongside the published ones and never substituted for them — M16 stays frozen at
29/41.

### 3.2 The drug-name-shape route (`aeea608`)

The prose extractor's ≥40-molecule stem rule is structurally blind to drugs from small
classes: HRH1 lost KETOTIFEN, HTR2A lost the whole `-anserin` cluster. **The threshold was
not lowered and no suffix was added** — either would be tuning against names already
observed. Recall comes from two added routes instead:

- **exact match** against 41,250 single-token frozen-ontology drug names (ontology-derived,
  therefore circular, and reported as such);
- **a learned shape model** — pure-Python multinomial naive Bayes over character 3/4/5-grams
  (`drug_name_shape.py`), threshold 0.2498 chosen as the lowest decision value reaching a
  **pre-declared** 95% precision on a held-out split keyed by `sha256(token)`, buying
  95.0%/77.0% precision/recall. 583 benchmark strings across PDCD1, SLC6A2, HRH1 and HTR2A
  were excluded from positives, negatives, training and calibration alike.

Extraction may nominate a name; it may never assert a target. The existing identity and
`CandidateTargetAssertion` gates remain authoritative, which is why a 55% mention-layer
false-accept rate (§5) still yields zero false target assertions.

## 4. M16R — the controlled remediation benchmark

M15L was run on a newly acquired corpus and is therefore not a controlled comparison
against M15. M16R is: the **same sealed M16 corpus**, the same frozen benchmark, engine the
only variable.

| | M16 published (frozen) | M16R |
|---|---|---|
| Discovery | 40/41 | 40/41 |
| Identification | 29/41 | **40/41** |
| Target assertions | 30 | 40 |
| — outside gold | 0 | 0 |
| Traps falsely asserted | 0/7 (2 surfaced) | 0/7 (5 surfaced) |
| Candidates / mentions | 2,170 / 10,201 | 4,665 / 28,411 |

The sole remaining miss, TEMANOGREL, is also the only discovery miss: it is absent from the
corpus and unreachable by any extraction change.

**Route confound, stated rather than glossed:** all 10 extraction gains are names the
frozen ontology already knows, so the circular exact-match route alone suffices for all 10.
The arm's-length shape model independently covers 7; IFERANSERIN, SARPOGRELATE and
VABICASERIN come only from the exact route. The 11th gain, SB-773812, is the identity
contract, not extraction.

## 5. The dominant remaining failure layer

It is no longer discovery, identification, or target precision. It is **mention-layer
precision**, and it got worse:

| class | M16 | M16R | **M17** |
|---|---|---|---|
| known_molecule | 849 (39.1%) | 1,645 (35.3%) | 1,892 (23.4%) |
| development_code | 688 (31.7%) | 684 (14.7%) | 1,071 (13.3%) |
| **unknown_word (false accepts)** | **576 (26.5%)** | **2,270 (48.7%)** | **4,480 (55.5%)** |
| gold | 32 | 43 | 32 |
| trap | 3 | 5 | 16 |
| other | 22 | 18 | 589 |

More than half of what the engine nominates is an ordinary alphabetic token the frozen
ontology has no drug record for. The failure modes are diagnostic rather than mysterious:
chemical-class nouns (`phenols`, `quinolines`, `xanthones`), demonyms and place names
(`Afghanistan`, `Jordanian`), and hyphen compounds. This was deliberately left untuned so
that M17 ran against a frozen model.

It costs nothing in benchmark terms — the gates hold, and false target assertions stayed at
zero across 8,080 candidates — but it is the reason `SCORING` reports **7,966 unresolved**
against 114 excluded and 0 eligible. Anything downstream that consumes candidates rather
than assertions inherits this noise directly.

The other open items are unchanged: endogenous-ligand collision, dose/salt/combination
decoration, `MIN_SUPPORTED_DOCS = 5` conflating contested with rare, and the rule-6
`\bAR\b`/`\bMET\b` English-word false-positive mode.

## 6. How the target was drawn

`m17_pool_rules.json` (sha256 `2e2bf9c0…`) was frozen before the pool was computed. Funnel:
888 targets with edges → 17 passed `min_distinct_drugs 40` → 17 passed `max_mab_fraction
0.30` → 14 passed rules 1 and 7 → 5 passed rule 6, giving
`[ADRB1, CHRM1, CHRM3, DRD2, NR3C1]`. Seed = int of the sha256 of the frozen pool file, one
binding `random.Random(...).choice(sorted(pool))`: **CHRM1**.

`amendment_4` was declared before observing which symbols it restores: a milestone's own
selection record and report reproduce the candidate pool, and counting that as "contact"
would make every milestone permanently burn the pool it declined to draw from. Rule 7
gained HTR2A.

## 7. The alias probe refused the shared symbols

CHRM1's vocabulary has 5 sole-claimant terms and 2 shared ones requiring the run-time probe.
The frozen `retrieval_alias_admission_v1` probe **rejected both**: `M1` and `HM1` each have
two claimants (`CHRM1`/`SNRNP35` for `HM1`) and zero anchor-hit support to separate them, so
both returned `RETRIEVAL_AMBIGUOUS`.

The 15,454-record corpus — 4x M16's — is therefore not alias over-admission. It comes from
the target-to-asset expansion route: CHRM1 is an old, densely-drugged target whose anchor
set is dominated by the atropine family and its many formulations, so per-asset query
fan-out is far larger than HTR2A's. PubMed supplied 14,627 of the records; CT.gov 827.

## 8. Recommendation

The mandate's stopping condition is met: an untouched target shows strong discovery,
materially improved identification, and zero false target assertions, with no
target-specific changes. **The architecture-remediation loop should stop here.**

Three consecutive mechanically drawn targets now show the same shape — M15 HRH1 exposed
identification as the binding constraint, M16 HTR2A showed the fix generalizing at 70.7%,
M17 CHRM1 closes it at 100% against the hardest trap set drawn. Continuing to draw targets
would measure the same architecture again at rising corpus cost.

The next work is productization, not benchmark optimization. The one subsystem that should
be addressed first is mention-layer precision (§5) — not because it breaks any benchmark,
but because 55% false accepts is the difference between a system that scores well and one
you would put in front of a user.
