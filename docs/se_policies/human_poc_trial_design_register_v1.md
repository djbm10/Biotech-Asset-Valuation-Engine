# Preregistration — trial-design statements are not results (v1)

Written and committed **before** any code change or measurement, 2026-09-21.

Baseline: `src/bve/se/evidence/human_poc.py` at `862a74f`, `EXTRACTOR_VERSION = "human_poc_v3"`.
Reference run `aacr_safety` (`evidence.human_poc` = 41, the adopted baseline).

Target: the `INDIGO` false positive declared in §2 of
`human_poc_safety_context_v1.md` and deliberately left unfixed there.

> *"The INDIGO trial achieved its global enrollment goal with 194 patients, making it the largest
> phase 3 trial in IgG4-RD to date and providing 90% power to detect a clinically meaningful
> reduction in flare risk."*

It clears every rung of the ladder honestly: `flare` is an efficacy term, `194 patients` and `90%`
are values, patients are named, one asset is named, no safety term, no future tense. It is still
not a result. It reports **how the trial was built** — how many enrolled, and how small an effect
the design could detect.

---

## 1. The rule

A **statistical-design** register joins `_UNREPORTED_TERMS`:

- `power to detect`, `powered to detect` — the sensitivity of a design, not an observed effect.
- `enrollment goal`, `enrolment goal` — a recruitment target.

`_UNREPORTED_TERMS` is the right home: these say the measurement has not been reported, which is
exactly what that list means. They are whole-sentence, like every other member.

**Explicitly rejected: `achieved its`.** It matches only INDIGO among the live passages, so it would
"work". But *"the trial achieved its primary endpoint"* is how a genuine result is announced, and
adopting a phrase that happens to be unique in this corpus while being wrong in general is how a
benchmark gets gamed. Rejected before measurement, on meaning rather than on count.

## 2. What this milestone does NOT fix

`INDIGO` is **also** an identity defect: a trial name carried as an asset. Refusing this sentence
removes the visible symptom; the trial name remains in the candidate set and could acquire evidence
from some other sentence. That is an identity-layer change with its own controls and is out of
scope. **If `INDIGO` disappears from `human_poc` here, that does not mean trial-name assets are
fixed.**

Also out of scope, unchanged: sentence-scoped attribution (deferred until a real BD query shows it
is hiding an answer), `_EFFICACY_TERMS`, `_VALUE`, the clause splitter, and everything adopted in
the two preceding milestones.

## 3. Controls

Collateral was measured before the rule was written, over all **54 supporting passages behind the
41 live PASSes**: `power to detect` → 1 (INDIGO), `enrollment goal` → 1 (INDIGO), `powered to
detect` / `enrolment goal` / `enrollment target` / `statistical power` → 0.

| id | sentence | must be |
|---|---|---|
| INDIGO | the sentence above | **refused** |
| power-alone | *"The study enrolled 194 patients and had 90% power to detect a 30% reduction in flare risk with drugx."* | refused — tests the power clause without the enrollment phrase |
| enrollment-alone | *"drugx reached its enrollment goal of 194 patients, 40% of whom were in remission at baseline."* | refused |
| achieved-endpoint | *"drugx achieved its primary endpoint, with a 62% response rate in 40 patients."* | **PASS** — the phrase rejected in §1 must not be smuggled in by either new term |
| observed-reduction | *"Treatment with drugx produced a 30% reduction in flare risk, observed in 194 patients."* | **PASS** — the real result whose vocabulary INDIGO borrows |
| obexelimab | *"flares were reported in 26 patients (26.8%) in the obexelimab group and in 53 patients (54.6%) in the placebo group."* | PASS — unchanged |
| Cevostamab | the ORR sentence adopted at `862a74f` | PASS — unchanged |

## 4. Predicted outcome, declared in advance

Replay of the sealed AACR corpus, same argv as `aacr_safety`, new output directory.

| gate | `aacr_safety` | **predicted** |
|---|---|---|
| `identity.distinct_asset` | 775 | 775 |
| `target.expression` | 56 | 56 |
| `evidence.minimum_stage` | 638 | 638 |
| `evidence.human_poc` | 41 | **40** |
| candidates / low-support | 2837 / 1409 | 2837 / 1409 |

**Adoption bar, fixed now:** `human_poc` = 40; `INDIGO` absent; **the other 40 assets all still
present**, Cevostamab among them; no other gate moves. 40 reached by losing any asset other than
INDIGO is a failure, not a pass — and note the number coincides with the old pre-Cevostamab
baseline of 40 while the *membership* differs, so the count alone must not be read as a revert.

## 5. Not to be done

Touching attribution; touching identity to remove trial-name assets; adding `achieved its`;
adjusting any term after seeing the run.
