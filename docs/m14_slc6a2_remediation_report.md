# M14 — Target-to-Asset Discovery Expansion (SLC6A2 remediation)

**This is a remediation result, not a second zero-shot result.** M13 remains frozen at
**5/41 discovery, 0/41 identification** and is not recomputed anywhere in this document.
M14 re-runs the *same* frozen benchmark — same problem YAML, same 41-asset gold set, same
scorer rules, same two reachable source families — after two generic fixes, to measure how
much of the M13 failure those fixes recover.

| | M13 (frozen, zero-shot) | M14 (remediation) |
|---|---|---|
| Discovery (gold reachable) | 5/41 (12.2%) | **40/41 (97.6%)** |
| — of which independently corroborated | — | **20/41 (48.8%)** |
| — of which authority-seeded only | — | 20/41 |
| Identification | 0/41 | **4/41 (9.8%)** |
| Target-confirmed | 0 | 4 |
| Traps falsely asserted | 0 (vacuously) | 0 (of 21, with 4 real assertions standing) |
| Eligible into ranked output | 0 | 0 |
| Corpus records admitted | 2,019 | 16,813 |
| Candidates | 72 | 853 |

## What changed

**D2 — discovery is now two-directional.** M13's buried assumption was that a document
about an asset names that asset's biological target. For PDCD1 that is nearly always true;
for SLC6A2 it is nearly always false — an atomoxetine trial does not say "SLC6A2". The
`DrugTargetAuthority` now indexes USABLE `DIRECT_TARGET` edges by target, and the compiler
emits one query per authoritatively associated asset alongside the target-vocabulary
queries.

An authority edge decides *where to look* and nothing else. Every such query carries
`seed_provenance=AUTHORITY_SEEDED_ASSET` through the contract, the evidence it retrieves
goes through identity resolution, `CandidateTargetAssertion` and the normal gates
unchanged, and the scorer keeps the two populations apart. No authority edge was allowed
to make an asset a qualifying answer.

**D1 — alias admission is now measured, not assumed.** The M13 corpus was destroyed by
`NET`, an SLC6A2 synonym that in the trial registry overwhelmingly means *neutrophil
extracellular trap*. The fix is a retrieval-disambiguation rule, not an ontology or
identity change: no alias is removed from any entity. A sole-claimant alias is searchable;
a shared alias is probed alone against a deterministic, as-of-bounded sample, and admitted
for target T only if T's claimant-specific anchors dominate every rival claimant.

The policy (`retrieval_alias_admission_v1`, sha256 `9a8572d5…`) was registered and hashed
**before any probe ran**, with thresholds ≥5 supported documents, ≥80% share, ≥4× next
best, and calibrated on 40 held-out shared aliases involving neither PDCD1 nor SLC6A2.

The SLC6A2 decisions it produced:

| alias | decision |
|---|---|
| `NAT1` | ACTIVE_PROBE_ADMITTED |
| `NET1` | ACTIVE_PROBE_ADMITTED |
| `SLC6A5` | ACTIVE_PROBE_ADMITTED |
| `NET` | RETRIEVAL_AMBIGUOUS — only 3 probe documents support SLC6A2 |
| `solute carrier family 6 member 5` | RETRIEVAL_AMBIGUOUS — 0 supporting documents |

The single alias that destroyed the M13 corpus is the single alias the frozen rule refuses,
and it is refused without the rule ever having seen an SLC6A2 outcome.

The root cause was in retrieval rather than in the compiler: `QueryVocabulary.for_query`
re-expanded `target_aliases()` for every query, which made any caller-side narrowing
advisory and would have collapsed each seeded query back into `target OR drug`.

## Source-by-source waterfall

| source | reachable | via target vocabulary | via authority seed only |
|---|---|---|---|
| clinicaltrials_gov | 13 | 13 | 0 |
| pubmed | 40 | 15 | 25 |
| sec_edgar | unconfigured | — | — |
| 6 conference / company families | unconfigured | — | — |

| stage | combined |
|---|---|
| gold assets | 41 |
| reachable in admitted corpus | 40 |
| reachable via target vocabulary | 20 |
| reachable only via authority seed | 20 |
| correctly identified as an asset | 4 |
| target-confirmed on SLC6A2 | 4 |
| eligible into ranked output | 0 |

Source families are held identical to M13 on purpose. SEC EDGAR is now reachable — the
operator credential is present — but enabling it would confound a remediation comparison
with a source-coverage change, so it stays unconfigured and is reported as such, exactly as
in M13.

## Reading the discovery number honestly

The 41-asset gold set was cut from the same USABLE `DIRECT_TARGET` edges the seeding path
now reads. Recovering an asset *because the authority named it* therefore demonstrates the
plumbing, not discovery; counted alone it would be circular. The defensible headline is the
independently corroborated half:

* **20/41 (48.8%)** reached through SLC6A2's own search vocabulary — a 4× improvement over
  M13 and not circular.
* **20/41** reached only because the authority pointed at them — real functionality (this
  is how a buyer would actually enumerate a target's asset space) but not evidence that
  the engine can find assets it was not told about.
* **1** (`MIDOMAFETAMINE`) still unreachable.

## What did not improve

**Identification is still the binding constraint: 4/41.** 16,813 admitted records and 1,021
identity mentions yielded four correctly named gold assets. The engine now retrieves the
right documents and largely fails to recognise the asset in them — the same class of defect
M13 exposed, no longer masked by a retrieval failure upstream of it. Every asset it did
identify it also correctly placed on SLC6A2 (4/4), and it falsely asserted none of the 21
traps, so precision is no longer vacuous — but it is measured on four assets.

**Nothing was promoted.** The run is `INCOMPLETE` because seven mandatory source families
are unconfigured, so 0 assets reached the ranked output. That is the fail-closed contract
behaving correctly, and it is unchanged from M13.

## Discipline record

* M13 untouched: 5/41 and 0/41 stand.
* Frozen denominators unchanged (41 / 48 / 21 / 3134); the scorer voids on any movement.
* Yardstick imported from `score_M13.py`, not reimplemented.
* Thresholds pre-registered and hashed before the first probe; calibrated on a held-out set
  excluding both benchmark targets on both sides of every pair.
* Hand-mapped assets: 0. Target-specific synonyms added: 0. No special case for SLC6A2 or
  atomoxetine exists anywhere in the code.

## Next

M15: a second untouched target, zero-shot, with no target-specific modification. If the
identification defect reproduces there, it is the engine's, not SLC6A2's.

## Artifacts

`M14_seal_v1.sha256` in the staging benchmark directory pins: `M14_result.json`,
`M14_score.json`, `M14_waterfall.json`, `M14_alias_probes.json`,
`m14_alias_admission_policy_v1.json`, `m14_calibration_v2.json`,
`m14_calibration_decision_v2.json`, `m13_benchmark_v1.json`.
