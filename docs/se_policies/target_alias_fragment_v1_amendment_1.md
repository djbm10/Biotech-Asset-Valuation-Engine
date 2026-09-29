# Target alias fragments v1, Amendment 1: claimant versus eligible resolver

Status: **PREREGISTERED** 2026-09-29. Parent commit: `022e251`, where v1 failed F3 and was reverted.
Approved by the user after the v1 result. Ranking policy is **frozen**.

Written and committed **before** any code change. The v1 fragment definition (§2 conditions 1–4)
is unchanged. Only the mechanism changes.

## 1. Why v1 failed

v1 removed fragment aliases from the lookup index. `DPP` was claimed by DPP7 (a fragment of
`DPP II`) and by DSPP (DSPP's own alias), so it resolved AMBIGUOUS. Removing DPP7's claim left
DSPP as the only claimant, so "DPP-4-inhibitor" gave linagliptin the target DSPP. Dropping a
claim can therefore **create** a resolution by removing the ambiguity that protected another
entity.

## 2. The amended rule

> A fragment rule may remove a target resolution, but must never create a new one.

It keeps two concepts separate:

- **Claimant.** The ontology says an entity claims the alias. Every claim, fragment or not, stays
  indexed and still counts toward ambiguity.
- **Eligible resolver.** The claim is trustworthy enough to establish the entity. A fragment
  claim is not.

`resolve()` runs exactly as before. When it would return RESOLVED to entity `E`, and every one of
`E`'s claims on that lookup key is a fragment claim, it returns UNRESOLVED instead, with rule
`fragment_alias_only`. AMBIGUOUS and UNRESOLVED results are unchanged. So the amendment can only
turn RESOLVED into UNRESOLVED. It can never turn anything into RESOLVED, and it can never change
which entity is resolved.

Expected results:

- `IV` → UNRESOLVED (ST6GALNAC4 is its only claimant, and only as a fragment).
- `DPP` → AMBIGUOUS, as before.
- `CD19`, `BCMA`, `NF-E2` and `ST6GALNAC4` → unchanged.

The scope is `resolve()` for TARGET entities, which is everything that establishes a target:
construct-target reading, gates and target attribution. The following are **unchanged** and
declared as such:

- `claimants_of` (fragments are still claimants);
- `aliases_for` / `unambiguous_aliases_for` (query building). This only affects acquisition,
  which a sealed replay cannot measure, so it is not changed without a measurement;
- DRUG and DISEASE entities.

## 3. Acceptance (the sealed replays again, into new directories)

The v1 checks F1, F2 and F4 are unchanged. F3 is replaced by a stronger check:

- **F1.** No asset carries `TARGET:ST6GALNAC4` in a construct set or an assertion.
- **F2.** No target-gate PASS or CONFIRMED_TARGET is lost relative to `*_modality_v1`.
- **F3′ (monotonicity).** Across the **entire** candidate population of both runs, the set of
  resolved asset→target pairs after the fix is a subset of the set before it. Both
  `construct_target_set` members and non-UNRESOLVED target assertions count. There are **zero**
  newly resolved pairs; only removals are allowed. Each removal is listed.
- **F4.** Ranking is unchanged. R1–R3 pass, and top-20 changes are listed and explained.
  `tests/se` passes.

If F1–F4 all pass, the fix is adopted and `ASSET_SENTENCE_TARGET` is preregistered as a separate
milestone. If any fails, the change is reverted with a normal revert commit and recorded here.

## 4. Results

### 4.1 Measurement — 2026-09-29, implementation `010218e`

Sealed replays: `se_runs/tac01_fragment_a1` and `se_runs/mint5_fragment_a1`, each against its
`modality_v1` baseline. Output: `tac01_fragment_a1/fragment_eval.txt`.

- **F1 PASS.** ST6GALNAC4 carriers went from 26 to 0 in TAC01 and from 28 to 0 in mint5.
- **F2 PASS.** No target-gate PASS or CONFIRMED_TARGET was lost in either run.
- **F3′ PASS.** Zero new resolved asset→target pairs in either run. Pairs removed: 26 (TAC01) and
  28 (mint5). Each is exactly one ST6GALNAC4 pair per former carrier, so no other target was
  removed. The Linagliptin→DSPP creation seen in v1 did not occur, because `DPP` stays AMBIGUOUS.
- **F4 PASS.** R1–R3 PASS on both runs, and both top 20s are identical to the baselines.
  `tests/se`: 1518 passed, 3 xfailed.

**Status: ADOPTED.** Next is milestone 2, `ASSET_SENTENCE_TARGET`, preregistered separately.
