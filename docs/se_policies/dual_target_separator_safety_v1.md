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
