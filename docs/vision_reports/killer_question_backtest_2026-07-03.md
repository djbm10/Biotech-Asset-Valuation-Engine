# Killer-Question Backtest — v1 Eval Report

**Date:** 2026-07-03
**Mode:** `screening_backtest` (openness-only reconstruction)
**Commit:** e85493c
**CLI:** `python -m bve.analysis.killer_question_backtest`

---

## What this measures

For each resolved drug program in the ground-truth label corpus, the engine
reconstructs the science state as of the **decision date** (no post-decision
information) and replays the killer-question picker in openness-only mode. The
picker ranks archetypes by openness (how unresolved the underlying question is)
without needing a full rNPV branch valuation.

**Three metrics:**
- **M1 top-1 (headline):** did the engine's #1 ranked archetype match the
  labeler's decisive archetype?
- **M1 top-2 (secondary):** was the decisive archetype visible anywhere in the
  top-2 ranked candidates?
- **M3:** was abstention appropriate — engine abstained iff no single question
  was dominant?

M2 (conviction direction accuracy) is not applicable in this mode. It requires
wired conviction producers and will be measured in a later eval.

---

## Results

| Metric | N | Value | Calibration status |
|--------|---|-------|--------------------|
| M1 top-1 hit rate (headline) | 15 | 100.0% | Directional — N < threshold for calibration claim |
| M1 top-2 recall (secondary) | 15 | 100.0% | Directional |
| M3 abstention correctness | 15 | 100.0% | Directional |

**Appendix (not in headline):**
- 2 subjective-archetype rows (TOLERABILITY_CEILING, TARGET_VALIDITY with
  entangled hypotheses)
- 1 excluded row (solanezumab — too many confounded questions for a clean
  single-archetype label)

---

## What 100% means here — and what it doesn't

**What it means:** the harness infrastructure is correctly wired. The
reconstruction pipeline (label → point-in-time snapshot → picker → score) is
working end-to-end with no lookahead leakage.

**What it doesn't mean:** the model is good at finding the decisive question in
the real world. In screening mode, `_snapshot_from_label` constructs the snapshot
by leaving *only* the decisive archetype's component UNRESOLVED and resolving
everything else. With a single open question, the picker trivially selects it.
100% is the expected floor when inputs are this synthetic, not a signal of model
quality.

**When the number becomes meaningful:** M1 will carry real signal once the label
corpus includes cases where multiple archetypes are simultaneously unresolved and
the picker has to rank them correctly to reach the ground-truth answer. That
requires either:
- Full as-of snapshots (capturing what was genuinely open at decision date), or
- Seed cases where the label corpus includes programs with two or more plausible
  decisive archetypes.

The `screening_backtest` mode stamp exists specifically to prevent this result
from being cited as model validation before those conditions are met.

---

## Ground-truth corpus (v1 seed, 2026-07-03)

**18 programs total.** 15 clean (headline-eligible), 2 subjective, 1 excluded.

| Archetype | Clean count |
|-----------|-------------|
| TOLERABILITY_CEILING | 6 |
| TARGET_VALIDITY | 6 |
| DIFFERENTIATION | 3 |
| DOSE_ADEQUACY | 0 (1 subjective) |
| DELIVERY_EXPOSURE | 0 |
| NOVEL_OR_UNMODELED_RISK | 0 |

All 15 clean rows have `single_question_dominant = true` — the corpus seed was
deliberately picked from unambiguous cases. Adding `single_question_dominant =
false` programs (for M3 to be meaningful) and cases with multiple open archetypes
is the next corpus expansion step.

---

## What unlocks next

Per the Idea 20 plan (`docs/idea20_backtest_plan.md`), conviction layer influence
on POS/valuation/BD requires M1 (on clean archetypes) and M2 to clear a
pre-registered bar at sufficient N. This eval does not clear that bar — it
establishes the measurement machinery and a baseline of "harness works."

**P5 path forward:**
1. Add cases with multiple simultaneously-open archetypes to generate real M1
   signal.
2. Add `single_question_dominant = false` cases to give M3 genuine signal.
3. Wire conviction producers to enable M2 measurement.
4. Grow N toward the calibration threshold before any headline claim.
