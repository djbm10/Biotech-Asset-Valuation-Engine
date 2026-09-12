# PDCD1 end-to-end baseline — run B8

**The first scientifically scoreable, target-aware PDCD1 baseline.** Acquired under
verified custody, sealed, replay-verified byte-for-byte, processed offline from the seal
alone, and scored against the frozen V2 benchmark.

- Run id `B8`, branch `se-acquisition-custody`, scoring commit `1e7181d`
- Ontology `chembl_ChEMBL_37__open_targets_26.06__resolver_v2__modality_v2`
- Universe hash `9656d1ea75c1eb516fd6f513ef5e6ded2e85a6d43a9ff27535c44d77ce81c435`
- Frozen inputs: `frozen_inputs_B8.json`; decision log: `B8_decision_log.jsonl`

## Does the generalized engine meet the intended product behavior?

**Partly — and the part it meets is the part that was previously unmeasurable.**

The engine finds essentially every confirmed PDCD1 asset and does not confuse PD-1 with
PD-L1 at the level of an individual asset. It does not yet produce a trustworthy *asset
record*: identity merging contaminates asset aliases, and target confirmation reaches
only 65% of the confirmed set. A user asking "which assets target PDCD1?" gets a complete
answer; a user asking "what is this asset?" gets an answer that is sometimes wrong.

| Claim | Verdict |
|---|---|
| Finds the confirmed PDCD1 universe | **Met** — 40/40 discovered, 35/40 identified |
| Distinguishes PDCD1 from CD274 per asset | **Met** — every canonical PD-L1 asset resolved to CD274 |
| Produces clean, non-contaminated asset identities | **Not met** — alias merging across combination trials |
| Confirms targets from an authority | **Partly** — 26/40 (65%) directly confirmed |
| Fail-closed under incomplete sources | **Met** — run refused to promote output |
| Reproducible offline from a sealed corpus | **Met** — exact replay parity |

## Recall

| Metric | n | denom | rate |
|---|---:|---:|---:|
| V2 confirmed PDCD1 — discovery (reachable in corpus) | 40 | 40 | **100.0%** |
| V2 confirmed PDCD1 — identification (named as an asset) | 35 | 40 | **87.5%** |
| Direct PDCD1 target confirmation | 26 | 40 | **65.0%** |
| — of those identified | 26 | 35 | 74.3% |
| Strict M8 (historical continuity only) | 81 | 224 | 36.2% |

Residual interval over the 9 still-uncertain V2 assets: **[71.4%, 87.5%]**.

The M8 figure is reported for continuity with earlier baselines and is **not** the product
metric: its 224-subject denominator mixes confirmed PDCD1 assets with backbone drugs,
comparators and unresolved early-stage assets. The 38-point gap between 36.2% and 87.5% is
benchmark composition, not retrieval failure — consistent with the B6 and role-authority
findings.

Retrieval is no longer the bottleneck. Every confirmed PDCD1 asset is in the corpus; the
loss is entirely downstream of retrieval.

### The 5 identification misses

| Asset | First failure boundary |
|---|---|
| Budigalimab (ABBV-181) | IDENTITY — in corpus, never extracted as a named asset |
| Budigalimab | IDENTITY |
| Subcutaneous pembrolizumab/berahyaluronidase alfa | IDENTITY |
| SMT112, AK112 | IDENTITY |
| Dostarlimab-gxly (GSK4057190 / TSR-042, JEMPERLI) | IDENTITY_NORMALIZATION — extracted under a spelling that does not normalize to the gold name |

All five are present in the sealed corpus. None is a retrieval failure. Four fail to be
extracted as a named asset at all; one is extracted under a non-normalizing spelling.

## Precision

| | n | of 133 confirmed negatives |
|---|---:|---:|
| Surfaced in the corpus | 42 | 31.6% |
| **Falsely asserted to target PDCD1** | **7** | **5.26%** |
| Correctly resolved to another target | — | — |

Surfaced is not asserted. A backbone or comparator drug appearing in a PD-1 combination
trial is a correct discovery result; only a false *assertion* is a target-attribution
error.

PD-L1 traps — the sharpest available test, since a run that cannot tell PDCD1 from CD274
will assert them — surfaced 6 (Adebrelimab, Atezolizumab, Avelumab, Durvalumab,
Pumitamig ×2) and falsely asserted 2 (Atezolizumab, Durvalumab).

### Diagnosis of the 7 false assertions: alias contamination, not target confusion

Every falsely-asserted negative traces to one mechanism, and it is **not** PD-1/PD-L1
confusion. The engine's own canonical entries are correct:

- `Durvalumab` → `CONFIRMED_OTHER_TARGET`, documented `TARGET:CD274`, direct evidence from
  both Open Targets 26.06 and ChEMBL_37
- `Atezolizumab` → `CONFIRMED_OTHER_TARGET`, documented `TARGET:CD274`
- `Ipilimumab`, `Cetuximab` → `CONFIRMED_OTHER_TARGET`

The false assertion arises because IDENTITY merges co-administered drugs from combination
trials into a single asset's alias list. The gold name `Durvalumab` also matches assets
whose canonical names are `Ad-p53`, `Hiltonol` and `Immunotherapy` — each of which carries
`Durvalumab` as an alias and is separately `CONFIRMED_TARGET` for PDCD1. Scoring folds
worst-case across every spelling an asset carries, so those assets' correct PDCD1
assertions land on Durvalumab.

This is scored as an error deliberately and the rule was fixed in advance of results
(`assertion_status`, pre-registered in `frozen_inputs_B8.json`): if any merged spelling of
an asset carries a confirmed PDCD1 assertion, the run has told its user that name targets
PDCD1. The user-visible failure is real. Its cause is asset identity, not target
attribution.

**This is the single highest-value fix available**: it is the same root cause as 4 of the
5 recall misses. Identity — not retrieval, not the ontology, not target attribution — is
the binding constraint on this pipeline.

## Uncertainty

| | |
|---|---|
| UNRESOLVED PDCD1 assertions | 44 |
| CONFLICTING assertions | 0 |
| Assets in the review queue | 1068 / 1068 (100%) |
| Review items | 10,681 |
| Still-uncertain V2 assets identified | 1 / 9 |

Unresolved assets are held for review, never excluded. Zero conflicting assertions means
the two authorities (ChEMBL_37, Open Targets 26.06) did not disagree anywhere in this run.

The 100% review-queue rate is a direct consequence of fail-closed behavior: with 7 of 9
source families unconfigured, no asset can satisfy its full gate requirement set, so every
asset carries at least one unmet requirement. This is correct conservative behavior, not
a defect, but it means the review queue carries no prioritization signal in this run.

## Custody and reproducibility

| | |
|---|---|
| Records sealed | 13,608 (CT.gov 2,918 / PubMed 10,690) |
| Snapshots | 13,608 |
| Query attempts / semantic queries | 1,928 / 1,883 |
| **Orphan records** | **0** |
| Withheld (as-of-cutoff, named but not admitted) | 109 |
| Failed attempts | 12 (HTTP 500/400/429), all superseded, 0 bytes each |

**Replay parity is exact.** A second acquisition run reading only the sealed corpus
reproduced the universe hash, all 1,928 attempt materialization sets, and all 13,608
ledger entries byte-for-byte. The only differences were the snapshot directory root and
the `other_content_hashes` field, which the live ledger predates.

Three orphan mechanisms found and closed during this work:

1. **Superseded retry bytes** — a retry's bytes were written but the superseded attempt's
   materializations were not named. Closed.
2. **As-of-cutoff withheld records** — the provider snapshotted records the cutoff then
   excluded; 109 of them existed as unexplained files. Now named with `admitted=False`,
   and replay re-declares them.
3. **Byte-version drift** — a record re-fetched mid-sweep after the registry updated it
   has two byte-sets on disk. The ledger now names the rest via `other_content_hashes`.

A fourth finding was diagnosed and dismissed: 11 files written by the provider but never
interpreted, caused by the CT.gov adapter's NCT-keyed memo returning first-seen bytes.
Replay proved these never reached interpretation — rebuilding from sealed membership
alone reproduced the run exactly. They are enumerated in
`B8_uninterpreted_byte_versions.json` as a named, non-interpreted disposition. No
reacquisition was required and the adapter memo was deliberately left unchanged, since
altering it would change replay semantics without affecting custody validity.

## Source state

`SUCCESS` clinicaltrials_gov · `PARTIAL` pubmed · `NOT_CONFIGURED` ×7
(company pipeline/presentation, company press release, SEC EDGAR, ASH, ASCO, AACR, EHA)

Run status **INCOMPLETE**, no fatal reasons. The sole incomplete reason is the 7 expected
unconfigured families, declared in advance in `frozen_inputs_B8.json`. The engine refused
to promote its output — correct fail-closed behavior — and the result is explicitly
diagnostic.

This bounds the result: recall is measured against what CT.gov and PubMed can reach. The
100% discovery figure is 100% *of the confirmed set within two sources*, and the 7
unconfigured families are exactly where early-stage and undisclosed assets would live.

## What this baseline establishes

1. **Retrieval is solved for this target.** 40/40 confirmed PDCD1 assets reachable.
2. **Target attribution is sound per asset.** Zero authority conflicts; every canonical
   PD-L1 asset correctly resolved to CD274; direct-evidence-only discipline held.
3. **Identity is the binding constraint.** It causes 4 of 5 recall misses and all 7
   precision errors.
4. **Target confirmation coverage is the second constraint.** 65% of confirmed assets
   carry a direct authority confirmation; the rest are held as UNRESOLVED rather than
   guessed.
5. **The custody layer works.** Zero orphans and exact replay parity, on a 13,608-record
   corpus, with three distinct loss mechanisms closed.

## Known limitations

- Two of nine source families configured; the remaining seven are declared blind spots.
- The M8 224-subject denominator is not a PDCD1-targeting denominator and should not be
  quoted as recall.
- The review queue is saturated by fail-closed gating and carries no prioritization signal
  in this run.
- 9 V2 assets remain adjudication-uncertain; the residual interval [71.4%, 87.5%] bounds
  their effect rather than resolving it.

## Scoring defects fixed after the run, before reporting

Two defects in the scorer (not the engine, not the frozen rules) were found and corrected:
`canonical_target_id` was compared against the bare symbol `PDCD1` while the pipeline
namespaces it as `TARGET:PDCD1`, which scored every asset as `NO_ASSERTION`; and the
review-queue rate counted gate-requirement items against assets, yielding 1000%. No
denominator, subject set, annotation rule, or adjudication was changed.
