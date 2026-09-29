# Asset-sentence target attribution v1 (`ASSET_SENTENCE_TARGET`)

Status: **PREREGISTERED** 2026-09-29. Parent commit: the Amendment 1 adoption of
`target_alias_fragment_v1`. This is milestone 2 of 2 in the target-evidence arc. Ranking policy
is **frozen**.

Written and committed **before** any code change. The rules in §2 and the acceptance criteria in
§4 are fixed here.

## 1. The gap

In `tac01_modality_v1`, TAC01 top-20 rows #8–20 have an UNKNOWN target gate:

- they are identity-resolved in ChEMBL or Open Targets but have no mechanism rows;
- they have no CT.gov intervention record that states a target.

The 8 wrong-target cell therapies are among them. Their documents often say what they bind in
prose, for example "tabelecleucel, an EBV-specific T-cell therapy" or "ALLO-715, a BCMA-directed
allogeneic CAR T". The engine reads none of this.

## 2. The rule

> A document sentence may give an asset a construct target set only when it names that asset
> and explicitly attributes the target to it.

A sentence is admitted for asset `A` only when **all** of the following hold. Each rule is
structural, and no drug or alias string is listed.

- **S1. Scope.** It is one sentence (same splitter as human PoC, at most 400 characters) from a
  document `A` was observed in. `trial_registry_record` documents are excluded, because
  the intervention route already reads those as structured fields.
- **S2. Named.** `A`'s own name appears as whole tokens.
- **S3. Sole asset.** No other registry asset name appears in the sentence.
  - Coordinated lists ("the BCMA-directed products X and Y") are **out of scope for v1**. A
    list cannot be told apart from a regimen ("X and lenalidomide") by structure alone without
    the regimen-role model, which this arc does not build. Lists stay UNKNOWN.
- **S4. Explicit and adjacent.** The existing attributive reader (`attributed_targets_in`:
  whole-token, cue-anchored, cue window 4) finds at least one target in the sentence. An
  attributive cue must also sit within 4 tokens of `A`'s name, as in "tisagenlecleucel, a
  CD19-directed CAR T". A target named elsewhere in the sentence is general discussion and is
  refused.
- **S5. Not another therapy's context.** The sentence contains no prior-therapy or contrast
  frame: *prior, previous, after, following, post-, relapsed, refractory to, failure, exposed,
  versus, compared, unlike, rather than, not*. These frames describe another therapy, as in
  "after CD19-directed CAR T, A achieved …". They are English grammar words, not drug names.
- **S6. Complete.** Every symbol-shaped token the reader considers near a cue resolves. If any
  such token is UNRESOLVED or AMBIGUOUS, the sentence is refused. A partial set for a dual
  construct (CD19 found, a second arm unresolved) would fail a dual-target question for a
  reason the evidence never gave.

Sentences that pass become one `construct_target_set` fact for `A`, under these constraints:

- **S7. Agreement.** All admitted sentences for `A`, across all documents, must yield the
  **identical** target set. Any disagreement means no fact.
- **S8. Fill only.** The fact is emitted only when `A` has **no** `construct_target_set` fact
  from the authority or intervention routes. It never supersedes and never competes (the
  gate reads competing facts as UNKNOWN). Existing target decisions therefore cannot change.
- **S9. Qualified assets only.** The fact is produced only for assets that pass asset
  qualification, the same guard human PoC uses. A correct attribution to a non-asset is
  still wrong.
- **S10. Provenance.** Each claim uses `extraction_method = "ASSET_SENTENCE_TARGET"` and cites
  its document and the sentence verbatim, with confidence below the authority's. The shortlist
  labels the target fact with this basis, so it is never shown as ChEMBL or OT evidence.

## 3. Out of scope

- Coordinated lists (see S3).
- The regimen-role model.
- Propagation from paragraph or document context.
- Registry prose.
- Any ranking change.
- Any change to the authority or intervention routes.

## 4. Acceptance (sealed replays against `tac01_fragment_a1` / `mint5_fragment_a1`)

- **T1.** No ST6GALNAC4 carrier reappears.
- **T2.** No control is lost:
  - every target-gate PASS and CONFIRMED_TARGET in the baselines is kept;
  - every baseline `construct_target_set` is unchanged, which S8 guarantees and the check
    verifies.
- **T3.** Precision:
  - every newly resolved asset→target pair across both populations is listed with its
    sentence;
  - every new pair on an asset in either run's post-fix top 50 is checked by hand;
  - **zero false assertions** among those.
- **T4.** Real CD19 programmes: every CD19 therapy in the TAC01 top 20 keeps CD19. The number
  of #8–20 rows that gain CD19 is reported, and none gains a non-CD19 target it does not have.
- **T5.** Wrong-target cell therapies: any of the 8 that gains a target gains the correct one
  and moves below or out of the TAC01 top 20 because of its target gate. None moves up. Not
  all 8 are required to resolve.
- **T6.** Ranking is frozen:
  - no change to `reporting/shortlist.py` ordering or the scorer;
  - R1–R3 pass;
  - every top-20 change is explained by a target-gate change.
  - `tests/se` passes.

If T1–T6 all pass, the rule is adopted. If any fails, it is reverted with a normal revert commit
and the result is recorded here.

## 5. Results

(appended after measurement)
