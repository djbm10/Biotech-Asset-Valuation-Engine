# ARM_VARIANT_IDENTITY v1 — dose, arm and cohort variants of one product are one asset (preregistration)

**Status:** PREREGISTERED 2026-10-04. No pipeline implementation exists.
**Baselines:** `~/se_runs/{tac01,mint5}_qual_v7`, ranked under the adopted
`ranking_lexicographic_v2`.

## 1. Problem

A registry sometimes enters one investigational product as several interventions, one per
arm or dose level: "CD19-BCMA Targeted CAR-T Dose 1" and "… Dose 2". Each name becomes its own
canonical asset, so the same programme occupies several shortlist rows.

The identity layer has two existing merge routes, and neither applies:
- authority identity (`authority_identity_merge_v1`): these names have no authority record;
- source co-offering: they are separate interventions.

## 2. Rule (frozen)

The reference implementation is `research/se_arm_identity/reader_frozen_v1.py`
(sha256 `ea919bed80f2f331252675cb5445f1829004480c17f7cf685482d19587c2b8ad`).

**V1. Arm qualifier.** A name ends in a qualifier from a closed grammar, separated from the
rest of the name by whitespace or punctuation:
- `Dose N` and `Dose level N`;
- `DL N`;
- `[iv] high|low|middle|mid|medium|intermediate dose`;
- `Cohort|Arm|Group|Part` followed by a 1–2-digit number or a single letter A–H.

The **arm base** is the text before the qualifier, stripped of separators, and must be
non-empty.

**V2. Grouping.** Candidates are grouped by casefolded arm base. A name with no qualifier is
never a member. This rule does **not** attach a qualified name to an unqualified one with the
same base.

**V3. Same-record evidence (required).** A group merges only if every member shares at least
one trial id: the same registry record lists every member as an intervention. Textual
similarity alone never merges. Shared targets are not consulted.

**V4. Size.** A group needs at least 2 members.

**Merge mechanics.** The existing reversible `propose_merge` / `apply_merge` is used, with:
- `deterministic_basis = "arm_variant:<base>:<shared trial ids>"`;
- survivor = the member whose canonical name sorts first, casefolded.

Every member's name is kept as an alias of the merged asset. Each member's trial ids, mention
ids and claims are unioned, as `apply_merge` already does, so all arm and dose provenance
survives. The merge runs after `consolidate_by_authority`, and its redirects are applied the
same way.

**Out of scope.** Unqualified-to-qualified attachment, for example
"zamtocabtagene autoleucel (MB-CART2019.1)" versus "MB-CART2019.1 Dose level 1". That case
needs a different evidence model and is recorded as a residual. Ranking, targets,
qualification and modality code are untouched.

## 3. Frozen population (enumerated and verified before code)

The population is `research/se_arm_identity/population_v1.json`
(sha256 `e60ecd80d5d528a633c78b4f83d371748161f40bb88bceb15b032ce25b3be140`). It holds 4 groups
per benchmark, the same in both. Each was checked against the sealed CT.gov record.

| Group | Record | Verdict |
|---|---|---|
| CD19-BCMA Targeted CAR-T Dose 1 / Dose 2 | NCT06371040 | One product. The interventions differ only in dose: 5.0e5, 1.5e6 and 5e6 per kg. **MERGE** |
| CD19.CAR-multiVST for Group A / Group B | NCT03768310 | One product. Groups A and B are disease-status cohorts given the same cells. **MERGE** |
| ET190L1-ARTEMIS™ T cells - iv high / -iv low / -iv middle dose | NCT03895944 | One product at 1, 3 and 10 ×10⁶. **MERGE** |
| MB-CART2019.1 Dose level 1 / Dose level 2 | NCT03870945 | One product at 1 and 2.5 ×10⁶ per kg. **MERGE** |

There are no expected non-merges. No group in the population fails V3, and every group is
verified as the same product. **0 false merges are expected.**

## 4. Acceptance (frozen)

Sealed replays go into new directories and are compared against `*_qual_v7`.

- **I1.** Exactly the 4 frozen groups merge in each benchmark, each into one asset, and
  nothing else merges by this route.
- **I2.** Zero false merges, by I1 plus §3.
- **I3.** Provenance: each merged asset lists every member name among its aliases, and the
  union of the members' trial ids.
- **I4.** No asset outside the merged groups changes identity. Their gate decisions,
  qualification reasons and `construct_target_set` values are unchanged. A merged asset's
  decisions must equal its members' decisions where all members agreed.
- **I5.** Ranking code is unchanged. Every top-50 movement is a merged duplicate row
  disappearing, or backfill. Retained relative order is preserved, except where the merged
  survivor's key changed by construction.
- **I6.** Two TAC01 replays give identical results.
- **I7.** `tests/se` and ruff pass.

## 5. Stop condition

- **Adopt** if I1–I7 all pass.
- **Otherwise** record the failure and revert. Do not tune the qualifier grammar or the
  evidence requirement.

## 6. Measurement clarification (operator, 2026-10-04, before any replay existed)

- **Identity, facts and gates** (I1–I4) are compared against the raw `*_qual_v7`
  `result.json`.
- **Ranking** (I5): the baseline order is the `*_qual_v7` `result.json` rebuilt with the
  adopted ranking v2 key, using `build_shortlist` at HEAD. It is **not** the v1 order that was
  stored with the run. No movement already attributed to ranking v2 may be counted as an
  effect of this milestone.
- **Scorer:** `scripts/score_arm_variant_identity.py`.

## 7. Result — 2026-10-05, code `d045206`

**Runs:**
- `~/se_runs/tac01_armid_v1`
- `~/se_runs/tac01_armid_v1_det`
- `~/se_runs/mint5_armid_v1`

**Scorer output:** `research/se_arm_identity/stage_i_v1.txt`, under the §6 rules.

| Criterion | Result |
|---|---|
| **I1** | **PASS.** Exactly the 4 frozen groups merged in each benchmark, each into one asset, and nothing else merged by this route. |
| **I2** | **PASS**, by I1 plus §3. 0 false merges. |
| **I3** | **PASS.** Every member name is an alias of its merged asset, and the shared trial ids are kept. |
| **I4** | **PASS.** For non-merged assets: 0 missing, 0 qualification changes, 0 gate changes, 0 `construct_target_set` changes, in both benchmarks. For the three gated groups, the members agreed and the survivor's gate equals theirs. MB-CART2019.1's members were ungated (unqualified, low-support) in the baseline, and the survivor still is. |
| **I5** | **PASS.** Both sides are built with ranking v2. TAC01 top 50 is unchanged. mint5: *CD19-BCMA Targeted CAR-T Dose 2* (#13), now absorbed into Dose 1, left; one row backfilled at #50; retained order is preserved. No ranking-v2 movement is attributed here. |
| **I6** | **PASS, with disclosure.** Construct facts, gates and the v2 top 50 are identical across the two TAC01 runs. The merge records match on every field except `created_at` and `applied_at`, which are wall-clock stamps. The baseline's 31 authority merges carry the same stamps, so this is pre-existing run metadata of the same kind as the run id earlier milestones excluded. It is not a semantic difference. The scorer's raw comparison printed FAIL; the semantic comparison passes. |
| **I7** | **PASS.** `tests/se` 1604 passed, 3 xfailed. Ruff is clean. |

**Residuals recorded:**
- An unqualified sibling remains separate, as §2 declared out of scope: `ET190L1 ARTEMIS™ T cells`.
- The mint5 #50 backfill is a procedure entry: `TCRαβ+/CD19+ depleted allogeneic HSCT`.

**Status: ADOPTED.** The new baselines are `~/se_runs/{tac01,mint5}_armid_v1`.

**Bookkeeping (operator, 2026-10-05):** I6 is recorded as **semantic determinism PASS; the raw
records differ only in wall-clock metadata** (`created_at`, `applied_at`). It is not reverted.
From now on, determinism scorers exclude volatile timestamps explicitly, and that exclusion is
declared before the scorer is run.
