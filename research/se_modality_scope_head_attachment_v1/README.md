# MODALITY_SCOPE_HEAD_ATTACHMENT v1

Policy: `docs/se_policies/modality_scope_head_attachment_v1.md`. Preregistration `07cb021` (rule, 25 controls, baseline, expected delta, checker + self-test); red-first tests `248a05e` (46 red / 9 green at baseline, `red.log`, `red_passed.log`); implementation and results in the adoption commit.

## Rule

`explicit_product_predicate` now reads the predicate noun phrase after "<product> is (a|an)" (bounded by punctuation or a closed boundary-word list) and takes its last token as the grammatical head. A modality mention is PRODUCT_LEVEL only if it is the head designation: preceded only by hyphenated compound modifiers and followed only by generic product nouns (`therapy`, `therapeutic`, `drug` …). Everything else in the phrase is AMBIGUOUS (`product_phrase_not_head`); a coordinated phrase is AMBIGUOUS (`product_phrase_coordination`). A non-modality head (`nanoparticle`, `fragment`) yields no product modality. The helper `product_phrase()` is the one place phrase and head are computed; `_scope` uses it.

## Changed assertions (7 of 78 in the frozen existing population; all preregistered)

| Input | Mention | Before | After |
|---|---|---|---|
| v2 MODIFIER_PEPTIDE | `peptide` PEPTIDE | PRODUCT_LEVEL | AMBIGUOUS `product_phrase_not_head` |
| v2 MODIFIER_PEPTIDE | `antibody` MONOCLONAL_ANTIBODY | AMBIGUOUS `unproven_subject_or_relation` | AMBIGUOUS `product_phrase_not_head` |
| v2 MODIFIER_PEPTIDE | `antibody-drug conjugate` ADC | AMBIGUOUS | **PRODUCT_LEVEL** |
| v2 MODIFIER_ANTIBODY | `antibody` MONOCLONAL_ANTIBODY | PRODUCT_LEVEL | AMBIGUOUS `product_phrase_not_head` |
| v2 MODIFIER_ANTIBODY | `cell therapy` CELL_THERAPY | AMBIGUOUS | **PRODUCT_LEVEL** |
| v2 MODIFIER_PAYLOAD | `small-molecule` SMALL_MOLECULE | PRODUCT_LEVEL | AMBIGUOUS `product_phrase_not_head` |
| v2 P_ADC | `antibody` (inside "antibody-drug conjugate") | PRODUCT_LEVEL | AMBIGUOUS `product_phrase_not_head` |

The last row is a real correction: the sub-span `antibody` was previously certified as a whole-product MONOCLONAL_ANTIBODY for an ADC. The ADC assertion itself stays PRODUCT_LEVEL. All 33 v1 witness records and the 5 H19 assertions (datopotamab: ADC PRODUCT_LEVEL, peptide COMPONENT_LEVEL) are byte-identical, including `assertion_id`.

## Validation

`checker.py` derives the verdict from the frozen expectations and measured output; it has no verdict constant. Self-test (`selftest.json`): the valid fixture passes; the unpatched baseline, a re-promoted modifier and an unregistered delta each fail. Measured result: `results/summary.json` gives verdict **ADOPT**, with 0 control failures and 0 population failures. Two independent builds are byte-identical (`results/hashes.json`).

Known conservative limits (frozen, not patched): non-hyphenated premodifiers (`novel peptide therapeutic`, `bispecific` as its own mention) stay AMBIGUOUS. Modifier constituents are AMBIGUOUS, not COMPONENT_LEVEL.

## Acceptance — ADOPTED

A1–A5, A8: derived by `checker.py` (all true). A6: `scoped_modality_assertions` still has zero production importers (`results/consumers.txt`), so no candidate fact or gate can change; H19 assertions are byte-identical. A7: byte-identical builds. A9: full `tests/se` **1,928 passed, 3 existing xfails**, 0 failures (`results/full_tests_se.log`). A10: Ruff clean (`results/ruff.log`). No rule was changed after results were seen.

Next: separately preregistered `PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v3` design (fresh evaluation; v2's failed certification is not evidence of safety). No semantic gating here.
