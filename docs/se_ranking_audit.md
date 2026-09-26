# Shortlist ordering — audit before any ranking design

Status: **AUDIT**, 2026-09-26. The first step of the ranking arc. No ranking code has been changed.
Numbers come from `scripts/se_ranking_evidence_audit.py`, which only reads records the pipeline
wrote and re-derives no rule. Runs audited:

- `mint5_on`: the adopted autoimmune dual CD19/BCMA acceptance arm
- `tac01_control_a1`: the oncology CD19 cell-therapy run

"Visible" below means what `build_shortlist` shows: candidates that are not excluded and not low
support.

## 1. What decides the order today

**Nothing evidential.** There are two orderers, and only one ever runs.

- **`ranking.engine.rank_profiles` (pairwise dominance) is unwired.** `pipeline.py:801` calls it on
  `comparative_profiles or []`. No caller anywhere in `src/`, `tests/` or `scripts/` passes
  `comparative_profiles=`. `ranking.ranked` is empty in every run, and `clinical_results`,
  `cohort_assignments` and `clinical_meaningfulness` are also empty in both runs. The
  eight-dimension `PairwiseProfile` has no producer. This is the same pattern as the NL intent layer
  and the M12 connectors: built, but with no production caller.
- **`reporting.shortlist.build_shortlist` sorts by a declared display key.** It sorts on eligible
  before review, then `TargetAssertionStatus` enum order, then **document count**, then mention
  count, then name. With 0 eligible in both runs, the only sort keys that do any work are target
  status and document count.

Consequences visible at the top of the list:

- In `mint5_on`, every visible asset is target `UNRESOLVED`, so order is pure document count. Ranks
  1–12 are conditioning and standard chemotherapy (gemcitabine, busulfan, cytarabine, melphalan…) for
  a *dual CD19/BCMA autoimmune* query, and `water` is at 19. Document count measures how often
  background therapy is mentioned, not how relevant an asset is.
- In `tac01_control_a1`, the 7 `CONFIRMED_TARGET` CD19 assets sort first. That is the one evidential
  signal that works. They include CD19 antibodies (`MONJUVI`, `Zynlonta`) in a *cell therapy*
  query, because the modality gate is UNKNOWN for all 446 visible assets.

## 2. What evidence a visible candidate actually carries

| | `mint5_on` (308 visible) | `tac01_control_a1` (446 visible) |
|---|---|---|
| any trial link (`trial_ids`) | 31.8% | **0%** |
| development stage | 28.2% (P1 61, P2 25, P3 1) | **0%** |
| development status | 31.8% | 0% |
| company | 31.8% | 0% |
| target assertion ≠ UNRESOLVED | 0% | 1.6% (7) |
| construct target set | 8.4% | 1.6% |
| human PoC PASS | 1.9% (6) | 0% |
| modality fact (gate-grade) | 0.6% | 0% |
| `modality_id` field (discovery-context text, *not* gate-grade) | 72.1% | 64.6% |
| therapeutic area PASS | 0 | 0 |
| ELIGIBLE (every gate PASS) | 0 | 0 |

Every gate on the visible population is overwhelmingly UNKNOWN. A BD ordering built today would
mostly be ordering UNKNOWNs.

## 3. Population defects that come before ranking

Ranking can only order what reaches the list. These defects decide what reaches it, and none of them
involves identity.

1. **Case-sensitive therapeutic-area match.**
   - The fact is written as `"oncology"` (`evidence/clinicaltrials.py:208`, `evidence/generic.py:152`).
   - The CLI requirement is `"ONCOLOGY"`.
   - `RequirementOperator.IN` compares case-sensitively (`gates/evaluator.py:36`).
   - Result: **an `--therapeutic-area ONCOLOGY` run excludes every oncology trial-backed asset.** In
     `tac01_control_a1`, 607 of 997 excluded assets have trials, and **all 28 human-PoC passers are
     excluded**. That is why the visible list there has 0% trials. `TAC01` is one of them.
2. **The therapeutic-area fact has one possible value.** Only oncology conditions emit it, and they
   emit only `"oncology"`. So `AUTOIMMUNE` can never PASS (0 PASS in `mint5_on`), and an asset with
   any oncology trial FAILs an autoimmune request even when it also has autoimmune trials
   (cyclophosphamide lists NMOSD and is excluded).
3. **Query residue becomes indication requirements.** `relapsed`, `refractory`, `B-cell` and
   `lymphoma` were compiled into `strategic_gap.indications` as independent literals. A real
   condition string (`"Lymphoma, B-Cell"`) can never be `IN` that list. This is part of the
   query-parser milestone.
4. **Two meanings of "default path".**
   - The gating log and every acceptance pair count *not low support*, which includes excluded
     assets: 1,032 in `mint5_on`.
   - The shortlist shows *not excluded and not low support*: 308.
   - Ranking work must use the second meaning, and reports must say which one they use.

In `mint5_on`, 23 of the 29 human-PoC passers are excluded. That is mostly **correct**: the query
asks for *dual* CD19/BCMA, and blinatumomab, venetoclax and the statins are not. Item 2 still
applies there.

## 4. What the first ranking milestone has to decide (operator)

Not decided here. These are the questions a preregistration must answer, with the evidence each
dimension can draw on today:

| candidate BD dimension | available today? |
|---|---|
| query satisfaction (gate PASS/FAIL/UNKNOWN per requirement) | yes, per requirement, but mostly UNKNOWN |
| development stage | ~28% of visible in one run, 0% in the other |
| human efficacy (`human_poc`) | 6 visible assets total |
| target certainty (`TargetAssertionStatus`, `construct_target_set`) | ≤ 8.4% |
| identity certainty (`qualification_reason`) | 100%, and now trustworthy |
| evidence coverage (source families, document count) | yes, but document count rewards background therapy |
| company / deal feasibility | ≤ 31.8% company, no deal facts |

Decisions needed:

- **Objective.** What is the BD user optimizing for, in which order, and which dimensions are
  lexicographic (never traded off) versus comparable?
- **UNKNOWN semantics.** Is UNKNOWN below FAIL, equal to it, or above it? Is it per dimension, or a
  separate "unassessed" band? `missing_evidence_policy: REVIEW` already exists on the problem and
  says nothing about order.
- **Coverage.** When `conference_ash`, `conference_eha` or `sec_edgar` are NOT_CONFIGURED or FAILED,
  does an asset's position carry a coverage caveat, or does coverage apply per run only?
- **Excluded assets.** Stay invisible (current behaviour), or appear in a ranked "excluded because"
  band?
- **Document count.** Keep it as the final tiebreak only, or drop it? It is the only
  non-alphabetical signal currently doing work, and it points the wrong way.

## 5. Recommendation

1. **Fix the population defects before preregistering any ordering.** At minimum item 1 (a one-line
   case normalization plus a test), and ideally item 2. Otherwise any ranking milestone on an
   oncology query is measured on a list that has already thrown away every trial-backed asset. These
   are gating defects, not identity, so fixing them does not reopen the identity arc. Items 3 and 4
   belong to the parser milestone and to report wording.
2. **Then** preregister the BD objective from §4 as the first ranking milestone. Prefer declared
   lexicographic tiers over a weighted composite: the pairwise engine's abstention design already
   says a total order across traded-off dimensions is preference-sensitive.
3. **Do not wire `rank_profiles` yet.** Its eight tiers (differentiation, durability/safety,
   operating fit, buyer advantage, transaction path…) have no producer, and inventing tier values to
   feed it would be exactly the composite the operator ruled out.
