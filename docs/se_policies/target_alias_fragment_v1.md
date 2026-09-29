# Target alias fragments v1: a split-off token is not a target name

Status: **PREREGISTERED** 2026-09-28. Parent commit: `3416127`.
This is milestone 1 of 2 in the target-evidence arc. Milestone 2 is same-sentence asset-target
attribution, preregistered separately after this one is adopted. Ranking policy is **frozen**.

Written and committed **before** any code change. The acceptance criteria in §4 are fixed here.

## 1. The defect

Open Targets files the alias `IV` for ST6GALNAC4, as both SYNONYM and SYMBOL. It was split out of
`ST6GalNAc IV`. The construct-target reader resolves symbol-shaped tokens near an attributive cue.
So any CT.gov intervention reading "Given IV" near "anti-CD19" or "CART-19" asserts ST6GALNAC4.

In `tac01_modality_v1` this puts ST6GALNAC4 into the construct sets of liso-cel, tisa-cel,
tafasitamab, `BCMA-CD19 cCAR T cells` and others. The alias type cannot tell such a fragment apart
from a real symbol, because the source labels it SYMBOL.

## 2. The rule

> A short alias fragment cannot establish a target unless the authority explicitly supports that
> token as an independent target alias.

For a TARGET entity `E`, alias `a` is a **fragment** when all of these hold:

1. `a` is short: **at most 3 characters**.
2. Some other alias `b` of `E` has two or more whitespace-separated tokens, one of which is `a`.
3. **Every** token of `b` is itself an alias of `E`. This is the signature of an upstream split:
   `ST6GalNAc IV` → `ST6GalNAc` + `IV`.
4. `a` is not `E`'s canonical (approved) symbol. That symbol is the authority's explicit support
   for a token as an independent target name.

A fragment is not indexed as a lookup key for `E`. It resolves to nothing through `E`, for any
caller: construct-target reading, gates, query compilation. `E` keeps the alias in its record for
display and audit. Other entities' claims on the same string are untouched. Drug and disease
entities are untouched.

No alias string is listed in code. On the installed snapshot (resolver_v2) the rule catches 20
aliases. Examples: `IV` (ST6GALNAC4), `II` (DPP7, TCN2), `B` (PPIB), `GP` (TNC), `TC` (TCN2),
`RH` (DDX21), `p35` (IL12A), `p44` (GTF2H2). Without the length bound, conditions 2–4 also catch
real standalone symbols such as `NF-E2`, `VIAAT` and `SLSN7`, which is why the bound is part of
the rule.

## 3. Out of scope

Same-sentence attribution (milestone 2), ranking, and all other alias-quality problems.

## 4. Acceptance (sealed replays: TAC01 `tac01_control_a1` and mint5 `mint5_on` custody)

- **F1.** No asset in either run carries `TARGET:ST6GALNAC4` in any `construct_target_set` fact,
  and no target assertion for it.
- **F2.** No correct target control is lost:
  - every asset with `CONFIRMED_TARGET` or a target-gate PASS in `tac01_modality_v1` /
    `mint5_modality_v1` keeps it;
  - or, if it changes, the change is shown by hand to be the removal of a false target only.
- **F3.** No new target assertion or construct target appears in either run. This rule can only
  remove resolutions.
- **F4.** Ranking policy is unchanged. The frozen scorer's R1–R3 pass. Top-20 changes are listed
  and explained. `tests/se` passes.

If F1–F4 all pass, the rule is adopted and milestone 2 is preregistered. If any fails, the change
is reverted with a normal revert commit and the result is recorded here.

## 5. Results

(appended after measurement)

### 5.1 Measurement — 2026-09-29, implementation `f30e3bf`

Sealed replays: `se_runs/tac01_fragment_v1` and `se_runs/mint5_fragment_v1`, each compared with its
`modality_v1` baseline. Output is in `tac01_fragment_v1/fragment_eval.txt`.

- **F1 PASS.** ST6GALNAC4 carriers went from 26 to 0 in TAC01 and from 28 to 0 in mint5. Liso-cel,
  tisa-cel, cilta-cel, tafasitamab, blinatumomab and `BCMA-CD19 cCAR T cells` all lost only
  ST6GALNAC4.
- **F2 PASS.** No target-gate PASS or CONFIRMED_TARGET was lost in either run.
- **F3 FAIL.** In both runs Linagliptin gained the construct target `TARGET:DSPP` from the
  intervention text "DPP-4-inhibitor":
  - Before the change, `DPP` had two claimants, DPP7 (a split fragment of `DPP II`) and DSPP
    (its own alias), so it resolved AMBIGUOUS, which is correct.
  - Removing DPP7's claim left DSPP as the only claimant, so `DPP` resolved.
  - The rule removed an ambiguity that had been protecting another entity. It therefore **created**
    a resolution, which §2 said was impossible.
- **F4.** R1–R3 PASS on both runs, and both top 20s are identical to the baselines.

**Status: FAILED_ACCEPTANCE.** Reverted with a normal revert commit. The flaw is in §2's mechanism
(dropping the fragment from the index), not in its definition of a fragment. Any revision needs a
separate amendment.
