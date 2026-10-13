# MODALITY_SCOPE_HEAD_ATTACHMENT v1 — preregistration

Extractor/representation correction only. **Decision-neutral**: no gate, fact, qualification, ranking, nomination or identity consumer is added; `scoped_modality_assertions` keeps zero production importers. Prompted by the v2 design stop (`cdc9845`): `explicit_product_predicate` certifies whichever modality mention *starts* right after "is (a|an)", so the first modifier, not the product noun, becomes PRODUCT_LEVEL.

## Frozen rule

Applies only after the existing early exits (no product subject, negation/hedge, embedded alias, `conjugated to`), which are unchanged.

1. **Predicate phrase.** After the existing copula match `<product> is (a|an)?`, the predicate phrase runs from the copula end to the first of: a sentence boundary (existing `.;\n`), one of `, : ( )`, or a closed boundary word
   `with containing comprising comprised consisting delivered conjugated linked that which who targeting for in against of to by from via using after before plus versus vs as at on under when while`.
   Tokens are maximal runs of letters/digits joined by internal hyphens. Trailing whitespace is trimmed. The **grammatical head** is the last token of the phrase.
2. **Coordination.** If the phrase contains `and`, `or` or `nor`, every mention starting inside the phrase is AMBIGUOUS, rule `product_phrase_coordination`.
3. **Head attachment.** A mention starting inside the phrase is PRODUCT_LEVEL (rule `explicit_product_predicate`, relations `PRODUCT_IS_MODALITY`, relation span = product end → mention start) iff:
   - the text between phrase start and mention start is zero or more **hyphenated compound modifier tokens** (`x-y[-z…]`), each followed by whitespace; and
   - the text between mention end and phrase end is zero or more whitespace-separated **generic product heads**: `therapeutic therapeutics therapy therapies drug agent product treatment medicine candidate`.
   That is, the modality designation is the phrase head or is followed only by a semantically empty product noun.
4. Otherwise a mention starting inside the phrase is AMBIGUOUS, rule `product_phrase_not_head`.
5. Mentions starting at or after the phrase end follow the existing relation/component path unchanged.

A grammatical head that is not a modality alias (e.g. `nanoparticle`, `fragment`) yields **no** whole-product modality; no category is invented. Non-hyphenated premodifiers (`novel`, `bispecific` before `antibody`) are not admitted and stay AMBIGUOUS as at baseline (conservative, intentional). Modifier constituents are AMBIGUOUS, not COMPONENT_LEVEL: promoting them would be a new component recognizer, which is out of scope.

The record schema, `version`, and rule names of unaffected assertions are unchanged, so every assertion outside the predicted delta keeps a byte-identical `assertion_id`. Phrase/head structure is exposed by a pure helper `product_phrase(text, start, end)` that `_scope` itself uses (single source of truth).

## Frozen population and expectations

`research/se_modality_scope_head_attachment_v1/`:

- `controls.json` — 25 structural controls (the three failed v2 modifier controls first) with **every** detected mention's exact `(start, end, modality, scope, rule)` plus phrase/head expectations. Covers premodifiers, hyphenated compound modifiers, multiword product nouns, nested product/component phrases, unrecognized product nouns, conflicting product claims, missing subject, unsupported coreference, product-level modality adjectives, coordination and verb guards.
- `baseline_records.json` — full pre-implementation records for the 33 v1 controls, the 14 v2 controls and the 5 H19 assertions.
- `expected_delta.json` — every predicted record change in that population. Every other record must be byte-identical (including `assertion_id`).
- `checker.py` — derives the verdict from frozen expectations vs actual output; it contains no verdict constant. `--selftest` proves invalid fixtures fail, valid fixtures pass and a mutated measurement flips the verdict.

## Acceptance (all required)

A1 three v2 modifier errors corrected; A2 all whole-product controls correct; A3 full frozen population conforms exactly (new controls + baseline/delta); A4 no unsupported product modality invented; A5 ambiguous structures stay ambiguous; A6 no candidate-level fact/gate change (no production importer; full suite); A7 two independent builds byte-identical; A8 every change is in `expected_delta.json`; A9 full `tests/se` passes except existing xfails; A10 Ruff clean. Any unexpected delta fails. No post-result rule patching; on failure revert `src/` and keep artifacts.

Out of scope: semantic gating (a separately preregistered v3 design follows adoption), qualification, the 86 target identities, human-PoC, ESG401, ranking, acquisition, identity. H21–H25 not inspected; H6–H10 not run.
