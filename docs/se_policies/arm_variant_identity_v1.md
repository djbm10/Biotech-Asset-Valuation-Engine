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
