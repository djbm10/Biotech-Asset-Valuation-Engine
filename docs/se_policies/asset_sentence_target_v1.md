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

### 5.1 Measurement — 2026-09-29, implementation `523f836`

Sealed replays: `se_runs/tac01_sentence_v1` and `se_runs/mint5_sentence_v1`, each against its
`fragment_a1` baseline. Output: `tac01_sentence_v1/sentence_eval.txt`.

- **T1 PASS.** No ST6GALNAC4 carrier in either run.
- **T2 PASS.** No baseline construct set changed (S8 held), and no PASS or CONFIRMED_TARGET was
  lost.
- **T3 FAIL.** There were 6 distinct new facts (3 in TAC01, 4 in mint5, with ICG318 in both).
  Each was checked by hand:

  | Asset | New target | Verdict | Cause |
  |---|---|---|---|
  | UCART19 | CD19 | correct | "an allogeneic genome-edited anti-CD19 CAR T-cell product" |
  | ponatinib | ABL1 | correct | The sentence is really about PonatiLink-2, a molecule not in the registry, so it is right by luck |
  | AT-007 | PTGER4 | supported | "specific inhibitor EP4". The sentence supports it; not independently verified |
  | **ICG318** | **MLPH** | **FALSE** | `LN`, the abbreviation "lupus nephritis (LN)", sits 4 tokens from the cue `CAR` and is an alias of MLPH |
  | **AMG 420** | **AMELX** | **FALSE** | `AMG`, a token of the asset's own name, is an alias of AMELX. v1 kept the asset's own tokens out of S6 (completeness) but still let them be read as targets |
  | **Cevostamab** | **TNFRSF17** | **FALSE** | "targeting FcRH5 (cevostamab) next-generation constructs … targeting BCMA". `FcRH5` is not symbol-shaped, so the reader never saw it. BCMA belongs to another clause, and S6 cannot detect a target spelled outside the symbol shape |

  None of these facts landed in a post-fix top 50. But ICG318 was **#1 in the mint5 baseline top
  20** and fell out of it **because of** its false fact, so the criterion's intent is violated.
- **T4.** The TAC01 top 20 is identical, and no CD19 programme was lost. No row among #8–20
  gained CD19.
- **T5.** None of the 8 wrong-target cell therapies gained a target.
- **T6.** R1–R3 PASS on both runs. The TAC01 top 20 is unchanged. The only mint5 top-20
  movement is ICG318 leaving (target gate UNKNOWN→FAIL on the false MLPH fact), with every
  other row moving up one place. The movement is explained by a gate change, but the right
  reason is missing.

**Status: FAILED_ACCEPTANCE.** Reverted with a normal revert commit. Recall was 3 correct facts
out of roughly 1,000 candidates. The false facts come from two defects in the rule, not from the
thresholds:

1. A clinical abbreviation or a name fragment can be read as a gene alias (the same class as `IV`).
2. S6 is blind to a target spelled outside the symbol shape, so a sentence with two clauses
   passes as complete.

Any revision needs a separate amendment.

### 5.2 Closure — 2026-09-29

**Route closed. No Amendment 1.** Free-text same-sentence target attribution is not adopted. In
the frozen corpus, ontology alias collisions and target names that are not written as symbols
prevent sufficiently precise attribution, while the restrictions that preserve precision leave
inadequate coverage. v1 produced 6 facts, 3 of them false, and none of the TAC01 #8–20 problem
rows resolved. Tightening the rule to approved symbols or common names would raise precision
only by lowering recall further.

The cevostamab sentence ("Investigational agents targeting FcRH5 (cevostamab) and
next-generation constructs … targeting BCMA …") is logged as the defining example of why the
symbol-oriented ontology reader is unsuitable for free text:

- the correct biological target (FcRH5 = FCRL5) is stated plainly beside the asset;
- the reader cannot see it, because it is not written in symbol shape;
- so the reader selects another nearby target instead.

Stop patching this extractor. Free text is revisited only after the structured-authority routes
below have been tried, and then only with a substantially different entity and relationship
model, not more alias-window rules.

Next is a target-authority source coverage survey over the 13 unresolved TAC01 top-20 assets,
followed by preregistration of one new structured authority. Ranking stays frozen. Source
priority:

1. structured sponsor or company pipeline data;
2. additional drug and biologic identity authorities;
3. pinned trial-registry lookup by asset name, plus a new live validation corpus;
4. free text with a new model.
