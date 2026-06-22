# What We Built — Plain-English Summary (2026-06-22)

This is a friendly walkthrough of two bodies of work, written so you can hand it
to someone who hasn't been living inside the code.

1. **Part 1** — the engineering done in the recent sessions on the
   `core-engine-v1` branch (config quality, calibration math, a mapping audit,
   and cleanup).
2. **Part 2** — the **Science Thesis layer**, a whole subsystem built across ten
   phases on a *separate* branch (`science-wip/evidence-workflow`).

A quick note on branches: think of a branch as a parallel copy of the project.
The session work lives on `core-engine-v1`. The science work lives on its own
branch and has **not been merged in yet** — so today the two don't see each
other except for two small shared files.

---

## Part 1 — Recent session work (`core-engine-v1`)

The big picture: after getting the test suite fully green (an earlier effort we
called "ROI #1"), we worked through a short, deliberately-ordered list. Each item
was small, additive (it didn't break existing behavior), and shipped as its own
saved checkpoint (a git commit). The ordering mattered — we did cheap, safe,
informative things first so they could tell us whether the riskier things were
even worth doing.

### 1. A "config quality" dashboard (ROI #2, first slice only)

**The problem it solves.** The engine runs off lots of YAML config files (one per
drug asset). Some of those configs are well-researched; others are mostly filled
in with default placeholder numbers. Before you spend time and compute analyzing
an asset, it helps to know: *how trustworthy is this config, really?*

**What we built.**
- **`src/bve/ops/config_quality.py`** — a scanner that reads every config and
  gives it a completeness score from 0 to 1.
- **`src/bve/cli/config_quality_report.py`** — a command-line tool,
  `bve-config-quality`, that runs the scan and prints a Markdown or JSON report.
- **`tests/test_config_quality.py`** — 17 tests locking the behavior in.
- Registered the new command in `pyproject.toml`.

**Two ideas that made it honest (and worth calling out):**
- **Scoring weights are explicit and versioned.** We didn't bury the "how
  important is each field" numbers in code logic. They live in a labeled table
  (`QUALITY_SCORE_VERSIONS["v1.0"]`, and the numbers add up to exactly 1.0). If we
  ever change how we score, we bump the version — so old reports stay
  interpretable.
- **We separated two *different* kinds of "weak."** A field can be weak because
  it's simply **missing** (the system filled in a default), or it can be present
  but **only roughly sourced**. Those are not the same thing, so we score them
  separately. Missing economic decompositions get partial credit based on how
  they were derived (fully curated = full credit, loosely derived = half, none =
  zero).
- **When a config has no quality metadata at all, the score is `None`, not 0.**
  This matters: a fake "0" would look like a *bad* config, when really we just
  *don't know*. Honest "we can't tell" beats a confident wrong number.

**What it told us.** 20 of the merger-and-acquisition configs scored a low 0.23 —
a clear "curate these first" queue. And 45 replay configs honestly showed "n/a"
because they carry no quality metadata, which confirmed a risk we'd flagged: the
metadata isn't uniformly present across config vintages.

We intentionally stopped here. The fancier "which fields actually move the
valuation the most" feature (materiality/leverage) was pushed to a later slice.

### 2. Calibration math: are our probability predictions any good? (ROI #3)

**The problem it solves.** The engine predicts probabilities (e.g. "this drug has
a 44% chance of passing Phase 2"). A prediction of "70%" is only meaningful if,
across many such predictions, things rated 70% actually happen about 70% of the
time. Measuring that is called **calibration**.

**A design choice worth noting.** There were already three calibration-related
modules in the repo. Rather than start a fourth one (which would create a second,
competing "source of truth"), we **extended the existing ones**. Less confusion,
less drift.

**What we added.**
- In **`calibration_metrics.py`**, a `brier_decomposition()` function. The Brier
  score is a single accuracy number; the *decomposition* (a classic 1973 method by
  Murphy) splits it into three intuitive pieces:
  - **Reliability** — how far off your stated probabilities are from reality
    (lower is better).
  - **Resolution** — how well your model separates winners from losers (higher is
    better).
  - **Uncertainty** — the inherent difficulty of the problem (you can't change
    this; it's just the base rate variance).
  The nice property: these three reconstruct the score exactly, so nothing is
  hand-wavy.
- Wired that decomposition into the existing report objects so it shows up in both
  the JSON and Markdown outputs.
- **`tests/test_calibration_decomposition.py`** — 11 tests. Some check the math
  itself (e.g. perfect predictions give zero reliability). Others are **regression
  anchors**: they pin today's real numbers so that if the model or dataset
  silently drifts, a test fails and tells us to look.

**The anchored numbers (oncology dataset, captured today):** 145 programs,
Brier = 0.2339, AUC = 0.6941, calibration error (ECE) = 0.14, and the
decomposition reliability = 0.024 / resolution = 0.030 / uncertainty = 0.250.
Plain reading: the model is *adequately calibrated for directional use* — good
enough to rank and lean on, not a precision instrument.

**One subtlety we handled honestly.** We made sure the anchors use the *real*
model's scores, not a deprecated shortcut function that the codebase itself warns
"does not reflect true model performance." Easy trap; we avoided it.

We also wrote a dated report, **`docs/vision_reports/calibration_pack_2026-06.md`**,
and were careful to label it: this measures *prediction quality only*, NOT trading
profit-and-loss. Those are different questions and shouldn't be mixed.

### 3. The mapping audit: should we build the "what matters most" feature? (report-only)

**The question.** The dashboard (item 1) flags weak fields. The engine also has a
"tornado" sensitivity analysis (it wiggles each input up and down to see which one
swings the valuation most). The tempting next feature: join those two — "here are
your weak fields, ranked by how much they actually move the answer." But that's
only worth building if the two sides line up cleanly. So we did an **audit
first**, writing no feature code.

**What we found (the important part).** The tornado analysis only wiggles the
*old-style* market inputs. It completely ignores the newer, more detailed
`commercial_inputs` breakdown (the patient-funnel and pricing fields). And because
almost every config (50 of 51) carries a total-market-size number, the tornado
never even touches price, patient population, or gross-to-net. So of the seven
"core economic drivers" we care about, only about 3.5 map cleanly; price, timing,
and cost don't map at all.

**The verdict.** **Don't build the materiality ranker yet.** If we did, it would
silently leave out price, cost, and timing, and give a false sense of
completeness. The audit explicitly recommended unblocking it first by adding
"named sensitivity hooks" (see *What's next* below). Writing **`slice2_materiality_mapping_audit_2026-06.md`**
saved us from shipping something misleading — that was the whole point of doing
the audit before the build.

### 4. Cleanup

- Refreshed some stale numbers in `CLAUDE.md` (the project's instructions file).
  The oncology dataset had grown from 99 to 145 programs, so the old accuracy
  figures were out of date.
- Removed a leftover temporary work folder (`/tmp/bve-ingestion-verify`) from a
  previous automated session, after confirming nothing important was lost.

### The commits, in order
`c166839` (dashboard) → `f2f31a5` (calibration) → `58b81ce` (audit doc) →
`cad897e` (doc refresh) → `4f7432c` (this summary). The test suite was green at
the end.

### What's next (planned, not started)
**Named sensitivity hooks.** In plain terms: teach the tornado analysis to also
wiggle the inputs it currently ignores — cost, trial duration/timing, price/WAC/
gross-to-net (from `commercial_inputs`), and patient population — and tag each one
so it links back to the quality dashboard. Only *after* that does the "what
matters most" ranker become honest to build. This is its own task because it
touches valuation outputs, the tornado tests, and the memo reports — not a quick
add-on.

---

## Part 2 — The Science Thesis layer (Phases 1–10)

This is a separate, larger subsystem on the `science-wip/evidence-workflow`
branch. Here's the idea in one breath: **before** you trust a drug's success
probability, you should be able to ask "what has to be biologically true for this
to work, and what's the actual evidence for each of those things?" The Science
Thesis layer answers that in a structured, repeatable way.

**Three principles it sticks to (this is what keeps it trustworthy):**
1. **It's deterministic and heuristic.** Same input → same output. It uses
   transparent rules, not a calibrated statistical model, and it says so plainly.
2. **It never makes things up.** If evidence for "the drug hits its target" is
   missing, it does *not* invent it. Instead it lowers confidence and turns the
   gap into a diligence question: *missing evidence → lower confidence → "go find
   this out" → which upcoming readout would answer it.*
3. **Mostly no LLM and no network calls.** It reads what's already in the repo.
   The one exception is an *optional* LLM extractor (Phase 6b) that is fenced in
   tightly — it may pull evidence, but it may never score or change a probability.

**One shared engine, two ways to use it:**
- **Discovery / Investment mode** — start from "what must be true?", find the one
  or two biology questions that actually change the value, and update your belief
  as evidence comes in.
- **BD (business development) mode** — start from a *buyer's* problem, gate out
  assets that don't solve it, then dig in. (This mirrors real corporate-development
  practice: filter for relevance before scoring.)

### The ten phases, in order (each builds on the last)

| Phase | What it added, in plain terms | Main file(s) |
|---|---|---|
| **1** | The foundation: the data shapes for a thesis and a deterministic way to score it. Deliberately keeps the *thesis* separate from any *probability adjustment*. | `intelligence/science_thesis.py`, `models/science_score.py` |
| **2** | A builder that fills in the thesis from whatever the repo already knows about an asset — and where evidence is absent, it records honest gaps instead of guessing. | `intelligence/science_thesis_builder.py` |
| **3a/3b** | Made the thesis and the BD-fit result *visible* — in the memo documents, the watchlist, and via command-line flags (`--science-thesis`, `--apply-science-pos-modifier`, `--buyer-problem`). | CLI wiring |
| **4** | Compact, machine-readable JSON summaries for audit and replay. Rule of thumb: "save what the user actually saw," not every internal object. | `intelligence/science_thesis_summary.py` |
| **5** | An "evidence landing zone": typed containers for individual pieces of evidence, plus a careful adapter that only accepts source-backed items. Sets up safe extraction later. | `intelligence/science_evidence.py` |
| **6a** | A deterministic extractor that maps *existing, already-structured* repo data into evidence items. It's a translator, not an interpreter — ambiguous or unsourced things become warnings, not facts. | `intelligence/science_evidence_extractor.py` |
| **6b** | An *optional* LLM-based extractor, locked behind the evidence schema. It can fill in source-backed evidence, but it is explicitly forbidden from scoring, changing probabilities, or recommending. | `intelligence/science_evidence_llm_extractor.py` |
| **7** | Plumbing so the Phase 6b extractor can run from the existing document-replay / ingestion flows. No new science logic — just wiring. | replay / ingestion wiring |
| **8** | Saves extracted evidence as durable, replayable artifacts (with version stamps and a document hash), so you don't have to re-run an expensive LLM call to reproduce a result. Includes a hash-mismatch policy (warn / fail / ignore). | `intelligence/science_evidence_artifact.py` |
| **9** | A compact way to *show* the evidence in human-facing output — counts, the best snippets, how many items were rejected as ambiguous, and what's still unknown — without dumping giant tables. | `intelligence/science_evidence_surface.py` |
| **10a** | A retrospective vocabulary for *why things failed*: target/pathway failure, dose/exposure failure, biomarker-translation failure, efficacy failure, safety failure, commercial/strategic failure, success, or unknown. Plus the records and report objects to aggregate them. | `intelligence/science_outcomes.py` |
| **10b** | "Calibration readiness" checks. It deliberately refuses to auto-tune the heuristic weights, reporting `calibration_status = heuristic` and `weight_update_allowed = false`. Recalibration is a separate, future decision. | `intelligence/science_calibration.py` |

### Guardrails that apply across all phases
- Diagnostics are **looking-backward only** and never quietly change the
  production weights.
- Recalibration needs its own deliberate phase — a small sample of outcomes is not
  permission to retune.
- **Science** failures are kept distinct from **commercial/strategic** failures —
  they're different problems and shouldn't be blurred.
- Loading a saved evidence artifact must never re-trigger an LLM call, and must
  never directly change a probability, BD decision, or the thesis.

### Status of this branch
Latest checkpoint: `607aac2`. The design notes live in
`docs/vision_reports/science_thesis_layer_phase{1,2,4,5,6a,7,8_10}_plan.md` and
`docs/science_thesis_workflow.md` *on that branch*. It is **not merged** into
`core-engine-v1` yet — over there, only two small shared files
(`science_engine.py` and `models/science_score.py`) exist.

> **Honesty note.** Part 2 was reconstructed from the plan documents and the
> module descriptions on the other branch, not from running its tests here. If you
> want it verified against actual passing tests and live behavior, that means
> checking out the `science-wip` branch and running it.
