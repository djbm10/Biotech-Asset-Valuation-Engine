# Idea 20 — Step 1: Making M1 Non-Trivial (2026-07-03)

## What this step was

`docs/idea20_path_to_pos_influence.md` lays out the road from the conviction
layer (which today only annotates memos/JSON) to the conviction layer actually
being allowed to move POS. Step 1 — flagged in that doc as "the highest-leverage
single step, do it first" — is to make the **M1 metric** (did the engine pick the
decisive killer question?) mean something.

Before this change M1 was trivially 100%: the snapshot builder left exactly
**one** archetype open per program, so the picker had a single candidate and
could not miss. A metric that cannot discriminate cannot validate anything.

## What changed

- **Schema:** added a `competing_archetypes` column to
  `research/data/killer_question_ground_truth.csv` — a comma-separated list of
  archetypes that were *also open* at the decision date but were not decisive.
- **Loader / model:** `KillerQuestionGroundTruthLabel` now carries
  `competing_archetypes: tuple[KillerArchetype, ...]` (defaults to empty for
  back-compat).
- **Snapshot builder:** `_snapshot_from_label` now opens the decisive archetype
  **and** every competing archetype, so the picker faces a real ranking field.
- **Tests:** `test_killer_question_ground_truth.py` validates the new column
  (known archetypes only, decisive not repeated, no duplicates, every clean row
  has ≥1 competitor).
- Seeded competing archetypes for all 18 rows (15 clean + 2 subjective + 1
  excluded), inferred from each row's own `why_this_archetype_decided` narrative.

## Result

| Metric | Before | After |
|--------|--------|-------|
| M1 top-1 hit rate (clean, N=15) | 100.0% | **53.3%** |
| M1 top-2 recall | 100.0% | 93.3% |
| M3 correct-abstention rate | 100.0% | 53.3% |

M1 dropped below 100% exactly as the plan predicted — it is now a metric that
can fail, which is the point.

## Honest caveat — what 53.3% actually measures

The replay harness runs in **openness-only** mode (no rNPV branch valuator), so
a question's rank is driven purely by its *openness* (UNRESOLVED = 1.0,
PARTIALLY_RESOLVED = 0.5). When several archetypes are equally open they tie,
and the outcome is then decided by two mechanical artifacts rather than picker
judgment:

1. **Tie-break by draft order.** On an openness tie the candidate built first
   wins. `TARGET_VALIDITY` is built first, so target-validity programs score
   near-perfectly and differentiation-vs-target ties (e.g. `olutasistat`) lose.
2. **Ties trigger abstention.** Equal-openness fields fall below the dominance
   margin, so the picker abstains — which drives the M3 drop as much as any real
   abstention judgment.
3. **Tolerability is under-weighted.** A non-severe safety concern is modeled at
   openness 0.5, so every tolerability-decisive program loses top-1 to any
   fully-open competitor.

So 53.3% is a **real baseline** in the sense that the metric now discriminates,
but it largely reflects openness/ordering artifacts, not the picker's
value-of-information reasoning. The genuine unlock for a *meaningful* M1 is
wiring the **VOI branch valuator** (real rNPV swings per program) so questions
rank by value-at-stake rather than by openness alone. That needs per-program
asset/trial/market stubs and is the natural Step 1.5 before growing the corpus
(Step 2).

## Seed labels need domain review

The `competing_archetypes` values are inferences from the failure narratives,
not sourced from primary documents. They are defensible starting points but
should get the same domain review as the decisive labels before the M1 number
is quoted anywhere load-bearing.

## Where this sits on the path

- **Step 1 (this) — DONE:** M1 is non-trivial; mechanism + schema + tests shipped.
- **Step 1.5 (recommended next):** wire the VOI valuator so M1 measures ranking
  skill, not openness artifacts.
- **Steps 2–8:** corpus growth, approved signatures, M2 replay, empirical LR
  calibration, live-input population, shadow mode, first feature-flagged unlock —
  all research- and calendar-bound, per the path doc.
