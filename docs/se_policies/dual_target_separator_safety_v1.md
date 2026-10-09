# DUAL_TARGET_SEPARATOR_SAFETY v1 — a split fragment must not become a target on its own (preregistration)

**Status:** PREREGISTERED 2026-10-09. No implementation exists.
**Origin:** `target_recognition_generalization_diagnosis_v1.md` §8, defect D-sep.
**Out of scope:** affix recognition (it comes in TARGET_AFFIX_RECOGNITION v3, afterwards),
variant and isoform semantics, ranking. H11–H15 remain untouched.

## 1. Defect

The tokenizer splits a whitespace token on the dual-target separators (`/`, `×`, `x` before a
capital letter). Each piece then resolves independently. When a separator-containing **name**
does not resolve as a whole, a fragment that happens to be an alias resolves alone and is
asserted as a target. Examples:
- `anti-ABP/ZF` → `ZF` → **CREBZF**;
- `AK/ATPase-directed` → `AK` → **ADK**.

At the pre-fix parser (`62974b8`), the frozen affixed separator cases contain **430
different-target** and **26 gained-target** wrong assertions.

## 2. Rule (frozen)

**Fragment confirmation.** For each whitespace token containing a dual-target separator,
consider every RESOLVED target span that lies inside the token without covering all of it.
Those spans are kept only if **every piece** of the token is covered by a TARGET or
AMBIGUOUS_TARGET span. Otherwise they become free text (RESIDUAL,
`rule="separator_fragment_unconfirmed"`).

So a split is read as a dual-target expression only when every part of it names a target.

**What the rule never touches:**
- **AMBIGUOUS_TARGET spans** (they assert nothing and already fail closed);
- spans that cover the whole token (a multi-piece n-gram such as `12/15-lipoxygenase`);
- tokens without a separator;
- the operator logic.

No vocabulary is added.

## 3. Frozen population

`research/se_separator/cases_v1.json` (sha256
`2f49c4742e1bfe2c05be89f5768745256432ae97cff718af934774d57c1a0f7f`), built by
`freeze_cases_v1.py` at `62974b8`, contains:
- **5,720 cases**: 1,430 separator names × 4 affix wrappers. Classes before the fix: lost
  4,457, equal 779, different 430, gained 26, ambiguity_changed 28. Each case stores its bare
  and pre-fix affixed parse.
- **11 controls**, with their parse frozen:
  - dual-target: `CD19/BCMA` (with and without "dual"), `CD19xBCMA`, `CD19×CD22`,
    `CD19/CD22/CD20`;
  - `CD3/CD20` (refused today: CD3 unresolved, CD20 ambiguous);
  - `CD19 or BCMA`;
  - TAC01, H2 and H4;
  - `CD19/CAR`.

The no-regression set is the bare parse of all 7,329 names in
`research/se_heldout/affix_population_v2.json`.

## 4. Acceptance (frozen)

- **SS1. Zero wrong targets.** In every frozen case, the targets of the affixed parse are a
  **subset** of the bare parse's targets. "different" and "gained" go to **0**.
- **SS2. No regression on bare names.** All 7,329 bare-frame parses are identical to the
  frozen ones.
- **SS3. Cases equal before stay equal.** All 779 "equal" cases are unchanged.
- **SS4. Controls identical.** All 11 controls give the frozen targets, operator and
  ambiguous sets. TAC01, mint5 and H1–H5 are identical to `affix_controls_before_v1.json`.
- **SS5.** Ambiguous candidate sets never gain a member. A case's ambiguous set after the fix
  is a subset of its pre-fix ambiguous set.
- **SS6.** `tests/se` and ruff pass.

"Lost" cases may stay lost. Recovering them is v3's job, under strict parity. This milestone
is about **zero wrong targets**.

## 5. Stop condition

- **Adopt** if SS1–SS6 all pass.
- **Otherwise** revert, with no patching after the results.

## 6. Result — 2026-10-09: FAILED_ACCEPTANCE, reverted

**Scorer:** `scripts/score_dual_target_separator_safety_v1.py` → `research/se_separator/stage_ss_v1.txt`;
failure samples in `stage_ss_v1_failures.txt`. The code was applied to the working tree only
and is reverted with no patching. The `tests/se` run was stopped once SS2 and SS3 had failed.

| Criterion | Result |
|---|---|
| **SS1** | PASS. 0 wrong targets. "different" and "gained" go from 430 + 26 to **0**. |
| **SS2** | **FAIL.** 7 of 7,329 bare parses changed. |
| **SS3** | **FAIL.** 708 of 779 previously-equal cases changed: their target was lost. |
| SS4 | PASS. All 11 controls, plus TAC01, mint5 and H1–H5, are identical. |
| SS5 | PASS. No ambiguous set gained a member. |
| SS6 | Not completed. |

**What the failures show.** SS2 and SS3 measured against a baseline that **itself contains
fragment-derived targets**. The rule removed exactly those:

| Name | Frozen target | How the baseline got it |
|---|---|---|
| `TaxREB107` | TOR1A | The tokenizer splits on `x` before a capital (`Ta` + `REB107`), and the fragment `Ta` resolves to TOR1A. **A wrong target in a bare name.** |
| `UNQ2421/PRO4979/PRO34274` | FNDC3B | Only the middle piece resolves. Here the fragment is coincidentally correct. |
| `24b2/STAC2-directed`, `anti-1A6/DRIM` (the 708 SS3 cases) | STAC2, UTP20 | Fragments that are aliases of the same gene, so the target is coincidentally correct. |

The preregistered SS2 and SS3 required preserving baseline behaviour that is partly the
defect, so SS1 and SS2/SS3 cannot be satisfied together by any fragment rule. This is a
**preregistration design error**: SS2 and SS3 were written assuming every baseline target was
legitimate. As frozen, the milestone fails.

**Also learned:**
- **Bare names are affected too, not only affixed ones.** For example, `TaxREB107` → TOR1A comes
  from the `x`-before-capital separator.
- Some fragment resolutions are correct only by coincidence: the fragment is an alias of the
  same gene as the whole name.

**Decision needed before v2:** how to tell a coincidentally correct fragment target (fragment
alias of the same gene as the whole name) from a wrong one. The frozen baseline needs labels
for which of its fragment-derived targets are correct.

## 7. DUAL_TARGET_SEPARATOR_SAFETY v2 — preregistration (2026-10-09)

**Operator decision.**
- A wrong fragment target must disappear.
- A target is kept only when the **unsplit whole name** independently resolves to it, and it is
  then derived from the whole name.
- A target that only a fragment provides may drop to unresolved.
- No case may resolve to a different target.

**Labels (frozen before code).** `research/se_separator/labels_v2.json` (sha256
`2e419cca0f3ffd8213c963bd52722832d4b162f206d5182ff263fa6164a135b1`), built by
`freeze_labels_v2.py` from the authority alone, without the parser. For each
separator-bearing token T, the expected set E is:

| Label | Condition | Expected set E |
|---|---|---|
| **WHOLE** | `resolve_target(clean(T))` is RESOLVED | {that target} |
| **DUAL** | otherwise, every separator piece resolves (RESOLVED or AMBIGUOUS) | the RESOLVED pieces' targets |
| **NONE** | otherwise | ∅ |

There are 7,150 cases: 1,430 bare separator names and 5,720 affixed cases.

| Kind | Label | Correct before | Wrong before | Missing before |
|---|---|---|---|---|
| bare | WHOLE | 1,394 | **5** | 13 |
| bare | DUAL | 1 | — | 1 |
| bare | NONE | 16 | — | — |
| affixed | NONE | 4,555 | **1,165** | — |

**Rule.** For each whitespace token containing a dual-target separator:
1. if the whole cleaned token resolves (RESOLVED), the token's target spans are replaced by
   one span over the whole token → that target (`rule="separator_whole_name"`);
2. else, if every piece is covered by a TARGET or AMBIGUOUS_TARGET span, they are kept (the
   existing dual-target reading);
3. else, every RESOLVED target span inside the token becomes RESIDUAL
   (`separator_fragment_unconfirmed`).

AMBIGUOUS spans are never promoted.

**Acceptance (strict):**
- **DV1.** For every case, the parsed targets ⊆ E. **Zero** wrong targets.
- **DV2.** For every WHOLE case, the parsed targets = E.
- **DV3.** For every DUAL case, the parsed targets = E.
- **DV4.** The 11 frozen controls, plus TAC01, mint5 and H1–H5, are identical to the frozen
  parses.
- **DV5.** No case's ambiguous set gains a member.
- **DV6.** Every population name **without** a separator parses identically in the bare frame.
- **DV7.** `tests/se` and ruff pass.

**Stop condition.**
- **Adopt** if DV1–DV7 all pass.
- **Otherwise** revert, with no patching after the results.

## 8. Result — DUAL_TARGET_SEPARATOR_SAFETY v2, 2026-10-09: FAILED_ACCEPTANCE (1 case), reverted

**Scorer:** `scripts/score_dual_target_separator_safety_v2.py` → `research/se_separator/stage_dv_v2.txt`.
The code was applied to the working tree only and is reverted. A copy is kept outside the
repository. `tests/se` was not run.

| Criterion | Result |
|---|---|
| **DV1** | **PASS.** 0 wrong targets in 7,150 cases. All 1,165 affixed and 5 bare wrong targets are gone. |
| **DV2** | **PASS.** All 1,412 WHOLE cases resolve to their whole-name target. That includes the 13 previously missing, and `TaxREB107` → RPL6 instead of the fragment's TOR1A. |
| **DV3** | **FAIL: 1 of 2.** `H2B/h` (expected DUAL {FUT1, H2BC21}) parses to ∅. |
| DV4 | PASS. The 11 controls, TAC01, mint5 and H1–H5 are identical. |
| DV5 | PASS. |
| DV6 | PASS. 0 non-separator names changed. |
| DV7 | Not run. |

**The single failure.**
- At HEAD, `H2B/h` is also ∅. The parser's 2-gram `H2B h` resolves AMBIGUOUS, so neither piece is
  asserted. v2 did not cause this: it was "missing" before and is "missing" after.
- The label, derived from the authority alone, reads the pieces as two separate targets, `H2B`
  and `h` (`h` → FUT1). Reading the lone letter `h` as a gene is exactly the kind of fragment
  target this milestone exists to prevent, so the preregistered expected set for this case is
  arguably itself wrong.
- But DV3 was frozen as equality, so the milestone fails as preregistered. No patching after
  the results.

**Operator decision needed for v3.** Re-freeze the DUAL label so that a piece counts only if
it resolves **and is not a single character or a stopword**, and/or relax DV3 to "⊆ E". With
either change, the measured v2 behaviour would pass every criterion it was scored on. Note that
DV7 has not been run.

## 9. DUAL_TARGET_SEPARATOR_SAFETY v3 — preregistration (2026-10-09)

**Operator decision.** This corrects how the label builder defines a valid fragment. It is not
parser tuning. A DUAL component must resolve **and** be at least 2 characters long **and** not
be a parser stopword.

**Labels (frozen before code).** `research/se_separator/labels_v3.json` (sha256
`5ce8570faa28084c09455e9e0b39605e2b26632d380b2f6566483e4a56197984`), built by
`freeze_labels_v3.py`. It differs from v2 only in that `valid()` predicate. Exactly one case
changed label: `H2B/h` DUAL → NONE. The other 7,149 labels are identical.

**Rule.** The **identical** v2 production rule (§7), re-applied byte for byte from the reverted
copy.

**Acceptance.** DV1–DV7 as in §7, unchanged, with **DV3 still an exact match**, scored against
`labels_v3.json`. DV7 includes the full `tests/se` run and ruff. Adopt or revert strictly.

## 10. Result — DUAL_TARGET_SEPARATOR_SAFETY v3, 2026-10-09: ADOPTED

**Scorer:** `scripts/score_dual_target_separator_safety_v3.py` → `research/se_separator/stage_dv_v3.txt`.

| Criterion | Result |
|---|---|
| **DV1** | **PASS.** 0 wrong targets in 7,150 cases. Before: 1,170 (1,165 affixed, 5 bare). |
| **DV2** | **PASS.** All 1,412 WHOLE cases resolve to the whole-name target, including the 13 previously missed. |
| **DV3** | **PASS.** The DUAL case is exact. |
| **DV4** | **PASS.** The 11 controls are identical; TAC01, mint5 and H1–H5 are identical in full intent. |
| **DV5** | **PASS.** |
| **DV6** | **PASS.** 0 of the non-separator names changed. |
| **DV7** | **PASS.** `tests/se` 1655 passed, 3 xfailed; ruff clean. A regression test was added: `tests/se/test_dual_target_separator_safety.py`. |

**Status: ADOPTED.** No benchmark parse changed, so no replay is needed (DV4).

**Next:** TARGET_AFFIX_RECOGNITION v3 under the same strict parity concept. H11–H15 stay
untouched until it is adopted or reverted.
