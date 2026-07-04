# Accuracy And Calibration

Plain-language record of the valuation-accuracy work. Goal is honest calibration and uncertainty, not false precision.

## 2026-07-04 - Claim Ledger: Calibration Corpus Infrastructure (the data on-ramp)

### What Changed

The claim ledger is only as good as the historical data we check it against, and that
data doesn't exist yet. This step builds the **on-ramp** for that data — not the data
itself, which is human research work.

Concretely: a corpus schema and tooling for the exposure/therapeutic-window wedge. A
generator reads our existing failed-oncology-program list, finds the toxicity- and
exposure-driven failures, and writes a structured worksheet — one row per program, with
the mechanically-known fields pre-filled and the judgment fields (the target, the
sources, and whether the claim actually held) left blank and marked "REVIEW REQUIRED".
It seeded **31 draft programs** (e.g. navitoclax, umbralisib, parsaclisib — the
dose-limiting-toxicity class).

Alongside it: a loader that will only ever let a **human-approved** row into a
calibration number, a validator that rejects half-filled or unsourced rows, and a
calibration report that currently prints "uncalibrated, n=0" because nothing is approved.

### Why It Matters

- **It makes the human work concrete and bounded.** Instead of "go build a dataset," the
  next step is now "open this CSV of 31 programs, fill in the target/sources/outcome for
  each, and mark it approved." That's the reviewable, paceable unit the plan asks for.
- **A draft can never sneak into a metric.** By construction, only `review_status=approved`
  rows with real source links count. Until a human does that review, every calibration
  number is honestly zero, and the NO LIVE POS GATE stays closed.
- **What is NOT done, on purpose:** the actual labeling. The 31 rows are starting points
  with placeholders, not facts. Nothing is calibrated until they're reviewed and approved.

## 2026-07-04 - Claim Ledger: Phase 1 Vertical Slice (shadow-only, no live POS)

### What Changed

We started building the long-term "thesis engine" — the plan to replace the single
science score (a scalar T/D/B number) with a claim-by-claim, evidence-backed ledger
that can explain exactly why a program's odds moved. Rather than build all ten claim
families shallowly, we built one all the way through: **exposure / therapeutic window**
(the "can enough drug reach the target without the toxicity capping the dose" question
— the class of failure behind drugs like navitoclax).

Concretely, three pieces now exist and are tested:

1. **A claim ledger.** Each biological claim (e.g. "enough drug reaches the target")
   carries its own prior, its own evidence, and its own posterior confidence. Evidence
   is logged as atoms that reuse the existing conviction-layer math, so we did not
   stand up a second parallel system.
2. **An evidence-quality gate.** Every piece of evidence carries provenance and a
   strength tier. The rule the plan insisted on is enforced in code: weak, unreviewed,
   inferred, or wrong-population evidence *raises a question* but cannot move the
   confidence number. Only strong, human-reviewed, directly-observed evidence moves it —
   and missing evidence leaves the claim open (high uncertainty), never marks it false.
3. **A shadow science modifier + a System-1-vs-System-2 audit.** The ledger produces a
   shadow version of the science modifier that is compared against the live scalar one
   and flags where they disagree (including the case where the live path raises an
   exposure kill-flag but the ledger looks favorable).

### Why It Matters

- **Nothing here touches live POS, by construction.** Every shadow output carries an
  `affects_live_pos = False` flag, and a test asserts the modules contain no path into
  `compute_science_modifier`. The plan's hard rule — no ledger output moves live POS
  until it passes calibration, reason-fidelity review, *and* governance approval — holds
  because the wiring to do so does not exist yet.
- **Refutation is first-class.** A single strong refuting result is not drowned out by a
  pile of weak company-slide confirmations; the confidence still falls.
- **Openness is wired through.** A killer question the tool hasn't answered yet seeds a
  claim that stays fully "open" until real evidence arrives, so the ledger honestly shows
  what it does *not* yet know instead of defaulting to a confident number.
- **What is NOT done, on purpose:** no corpus of 30-50 reviewed historical programs yet,
  so nothing is calibrated. This is the machinery, verified end-to-end on the exposure/
  window family; the hard data work (Phase 8) comes next and paces everything after it.

## 2026-07-04 - Conviction Layer: M2 Harness Built (does confidence move the right way?)

### What Changed

M2 is the measurement that actually gates letting this layer touch POS: when the
tool sees pre-readout biomarker evidence and updates its confidence, does it move
in the direction the eventual outcome justifies? We built the harness that scores
it. For each drug with sourced biomarker data, it feeds the evidence to the real
(approved-only) signature engine, reads whether confidence went up (target looks
engaged) or down (looks refuted), and checks that against what actually happened.

We seeded it with seven cases and then corrected two after domain review. Final
set: four clean successes where engagement was real and the drug worked
(imatinib/dasatinib phospho-CRKL, palbociclib phospho-Rb, erlotinib phospho-EGFR);
one "engaged-but-failed" case (erlotinib in EGFR-wild-type lung — pEGFR genuinely
suppressed, but the tumor isn't EGFR-dependent, so no benefit); one "couldn't
engage" case (imatinib in T315I-resistant CML — the drug can't bind, the marker
stays up, and the tool correctly reads that as refuting/failure); and one that is
simply not measurable (a CDK4/6 drug in an Rb-null tumor — no substrate to suppress,
correctly excluded). The tool scores 5-of-6 on the measurable cases, and the point
is that it handles all three call types — right, wrong, and refuting — correctly.

### Why It Matters

- The plumbing for the POS-gating metric exists and is verified against the real
  approved signatures, not stubs — the "works from day one" bar.
- **The rate is a discrimination demo, not a score** (the report says so every run):
  curated cases, primary-source unverified.
- **The headline lesson for POS is one clean case: erlotinib in EGFR-wild-type lung.**
  Target engagement was confirmed and the drug still failed. A single verifiable case
  (BR.21 subgroup) is enough to make the argument for keeping any future POS influence
  *refutation-only* — it can lower confidence on a refuted target but must never raise
  it just because a biomarker moved.
- Also logged: the engine currently matches a signature on biomarker OR mechanism,
  so an off-target marker move can fire the wrong signature — a fix needed before any
  M2 number is load-bearing. Nothing here touches POS; measurement only.

Tool: `bve.analysis.killer_question_m2_replay`; seed data in
`research/data/killer_question_m2_inputs.csv`.

## 2026-07-03 - Conviction Layer: Biomarker Signature Library Grows 1 -> 5 Approved

### What Changed

The next real milestone ("M2") is measuring whether the tool's confidence updates
point the *right direction* — and that needs a library of "if the drug is really
hitting its target, we should see biomarker X move this way" signatures to score
against. It had exactly one (JAK/pSTAT). We drafted five candidates with the
scientific case for each, and a domain review then **approved four and rejected
one**:

- **Approved:** CDK4/6 (phospho-Rb), BCR-ABL (phospho-CRKL), EGFR (phospho-EGFR),
  and HER2 (phospho-HER2, *scoped to the small-molecule TKI drugs only*).
- **Rejected:** VEGFR — VEGF paradoxically *rises* when you block the pathway and
  hypertension is a toxicity signal, so there's no clean "target engaged" marker.
  We kept the entry in the file marked `rejected` as a documented negative finding
  rather than deleting it, so a future session doesn't re-litigate it.

The library now has 5 approved, 1 rejected, 1 example-draft. A hard rule still
holds: only `approved` entries can ever move a number, and a wrong one would argue
*against* a good drug — so every approval is a recorded domain-expert decision.

### Why It Matters

- Four clean target-engagement signatures is enough to get the M2 measurement off
  the ground (it needs approved signatures to score against).
- **One honest caveat carried in the file:** the HER2 signature is valid only for
  the small-molecule (TKI) HER2 drugs; antibody drugs like trastuzumab engage the
  target differently, and the engine can't yet tell the two apart automatically —
  so that gating is a flagged prerequisite before HER2 is used on a real program.
- Still nothing fires automatically: M2 also needs each historical drug's biomarker
  readouts sourced one by one, so the scoring harness comes after that data exists.

Files: `src/bve/config/expected_signatures.yaml`, review record in
`docs/expected_signature_review.md`.

## 2026-07-03 - Killer-Question Backtest: Corpus Doubled to N=30, and a Blind Spot

### What Changed

We reviewed 15 of the draft rows against the actual trial histories and promoted
them into the real scorecard, taking it from 15 to **30 labeled programs**. We
rejected 10 drafts along the way — some were the same drug under another name
(would have double-counted), and one was a plain misjudgment by the draft tool
(an anti-PD-L1 drug the tool blamed on "wrong target" when it actually just lost
to a better competitor). Every promoted row is stamped as "seed + review, not
primary-source verified" so nobody over-trusts it.

### Why It Matters

- **The headline hit-rate went up (53% -> 67%), but not because the tool got
  smarter.** We happened to add many programs of the one type the tool already
  nails (is-the-target-real questions), so the number rose by composition. Broken
  out by type, the tool gets target questions 18/18 right and differentiation
  2/4 — and **tolerability questions 0 out of 8.**
- **Tolerability is a real, now-measured blind spot.** When a drug's make-or-break
  question is "is the safety/tolerability manageable?", the tool never ranks it
  first. That is baked into how the tool scores openness, not bad luck, and no
  amount of extra data fixes it. It matches what we always suspected: tolerability
  may have to stay a display-only flag rather than a score-moving question.
- **The value of the rNPV-swing ranking (Step 1.5) got much clearer.** On the
  bigger set, the "correctly says no-single-answer" metric is 30% without it and
  83% with it — a far bigger gap than the small set could show.

Full writeup: `docs/vision_reports/idea20_corpus_n30_2026-07-03.md`.

## 2026-07-03 - Killer-Question Backtest: Seed-Labeling Accelerator (Step 2 start)

### What Changed

The backtest can only get sharper if the labeled set of historical programs
grows, and that labeling is expert judgment we can't automate. So we built a tool
that does the *tedious* half: it reads the 155-program history file, pulls the 74
failed programs we haven't labeled yet, fills in the mechanical fields, and
proposes a most-likely "decisive question" for each one from the data already on
the row (safety, competition, target novelty, and keywords in the notes). It
wrote **56 draft rows** for review.

Every draft is marked `seed_review` so it is impossible for an un-reviewed guess
to sneak into the real scorecard — the backtest only counts human-confirmed
"clean" rows, and the loader refuses the draft status outright.

### Why It Matters

- It turns weeks of blank-page labeling into review-and-correct, which is much
  faster and more consistent. Each draft shows exactly which signals drove the
  guess, so a reviewer can accept or fix it in seconds.
- **30 of the 56 drafts are "no single dominant question" cases** — exactly the
  kind the abstention metric (M3) has been starved of.
- **Honest gap found:** this history file has essentially no programs whose
  failure was about *dose/exposure* or *drug delivery* — the two question types
  we most need more of. Those have to be sourced from outside this file; the tool
  can't invent them. Recorded so the research plan reflects reality.

Tool: `bve.analysis.killer_question_label_worksheet`; drafts in
`research/data/killer_question_label_worksheet.csv`.

## 2026-07-03 - Killer-Question Backtest: Ranking by Value, Not Draft Order (Step 1.5)

### What Changed

The M1 backtest (Step 1, below) still ranked questions only by how "open" they
were, so when two questions were equally open the winner was decided by which one
the code happened to build first — an artifact, not judgment. We now thread the
engine's rNPV "branch valuator" into the backtest: each open question is scored by
how much the drug's value would swing if that question resolved yes vs no, so
equally-open questions break by **value at stake** instead of build order.

### Why It Matters

- **M1 held at 53.3% but is now earned.** The programs the tool gets right it now
  gets right because the decisive question genuinely carries the most value, not
  because of build order. That is exactly what Step 1.5 was supposed to prove.
- **M3 (does the tool correctly say "no single dominant question"?) rose from
  53.3% to 66.7%.** Six programs that used to trigger a false "can't decide"
  abstention now resolve cleanly on value.
- **Two honest limits found**, both stated plainly so nobody over-reads the number:
  (1) every historical program is currently valued against one shared placeholder
  economics stub, so the valuator re-weights question *types* globally rather than
  reasoning per drug; (2) the valuator maps most question types onto the same trial
  gate, so it can only separate the late-stage "is it differentiated?" question
  from the rest.

**Correction (measured later same day):** an earlier draft of this note called
per-program economics "the real unlock." That was wrong — we tested it and it is
**inert** on this data. The ranking cancels out the size of a drug's market, and
the programs are too similar in trial stage for per-program economics to change
any decision. The levers that actually matter are growing the labeled set and,
eventually, a deeper change to how question types map to trial stages. See the
writeup for the measurement.

Full writeup: `docs/vision_reports/idea20_m1_voi_step1p5_2026-07-03.md`.

## 2026-07-03 - Killer-Question Backtest: M1 Made Real

### What Changed

The backtest that checks whether the tool picks the *decisive* make-or-break
question for each drug (metric "M1") used to score a meaningless 100%. The reason
was mechanical: each historical program's reconstructed snapshot left only **one**
question open, so the picker had a single choice and could not be wrong.

We added a `competing_archetypes` column to the ground-truth file recording the
*other* questions that were genuinely open at the decision date, and the harness
now leaves all of them open. The picker now has to rank the decisive question
above a real field of competitors.

With that, M1 dropped from 100% to **53.3%** (top-2 recall 93.3%). That is the
first honest baseline for this metric.

### Why It Matters

- This is Step 1 of the path to letting the conviction layer eventually influence
  POS. That gate stays closed until we can *measure* the layer points the right
  way, and M1 is the foundational measurement.
- Important caveat, stated plainly: the replay currently ranks questions only by
  how "open" they are, so the 53.3% is still driven partly by tie-breaking
  artifacts rather than genuine value-of-information reasoning. The next step
  (1.5) is to rank questions by how much value is actually at stake (rNPV swing),
  which makes the number reflect real skill. The competing-question labels are
  also seed inferences that still need domain review before the number is quoted
  anywhere load-bearing.

Full writeup: `docs/vision_reports/idea20_m1_nontrivial_2026-07-03.md`.

## 2026-07-02 - POS Accuracy Program + Commercial Backtest

### What Changed

1. **Headline POS backtest now reports out-of-sample metrics.**
   The report prints in-sample and out-of-sample Brier, AUC, and ECE side by side using the existing time split: train rows before 2022, out-of-sample rows from 2022 onward.

2. **POS recalibration is measured out-of-sample only.**
   Added an isotonic recalibration path that fits on `<2022` rows and reports raw OOS vs calibrated OOS on `>=2022` rows. Existing valuation outputs still use raw POS unless explicitly changed later.

3. **Science double-count was verified already fixed.**
   The science modifier is T/D/B only: target validity, enough drug, translation bridge. H/M/S-style signals no longer add positive science multiplier credit when POS already owns them. The overlap guard remains in place.

4. **The phase-transition dataset was expanded and then split correctly.**
   The mixed dataset is now `research/data/phase_transitions.csv` with 155 rows including oncology plus immunology, CNS, and metabolic examples. The legacy `research/data/oncology_phase_transitions.csv` is oncology-only again so older oncology-specific loaders do not silently pool non-oncology rows.

5. **Prior-phase evidence is now fallback-only.**
   `prior_phase_data` no longer stacks on top of more granular evidence like clinical effect magnitude, biomarker selection, dose confidence, or placebo-response assessment. When detailed evidence is present, prior-phase data is ignored and flagged.

6. **Peak-sales backtest now exists.**
   Added `research/data/peak_sales_backtest.csv` and `bve.analysis.peak_sales_backtest`. It compares predicted peak sales vs realized sales for approved drugs. The seed dataset is intentionally tiny (`N=2`) and the report prints a low-N warning so it cannot be mistaken for a calibration basis.

### Why It Matters

- The model now separates **measurement** from **model changes**: first report OOS behavior, then recalibrate, then grow data.
- Non-oncology rows no longer make an oncology-named file or legacy oncology calibration path misleading.
- The POS model avoids one real evidence double-count: broad prior-phase evidence cannot boost POS again when more specific clinical evidence already explains the same signal.
- Revenue accuracy now has a measurement surface instead of being untested.

### How It Works

- `run_backtest_from_csv(...)` loads row-level therapeutic areas and labels the calibration suite `heuristic_mixed_ta` when a file contains more than one TA.
- `phase_transitions.csv` is the mixed headline dataset.
- `oncology_phase_transitions.csv` remains the oncology-only legacy dataset.
- Isotonic recalibration lives behind explicit analysis functions and reports calibrated POS alongside raw POS.
- `prior_phase_data` applies only when no granular evidence field supersedes it.
- Peak-sales backtest computes MAE, RMSE, MAPE, median APE, within-25%, within-50%, and within-2x.

### Proof It Works

Commits:

- `9f63ee1` - `feat(analysis): report OOS POS calibration metrics`
- `08d9b3c` - `feat(analysis): surface OOS POS recalibration metrics`
- `547a3a8` - `feat(analysis): expand POS backtest dataset`
- `8917446` - `feat(analysis): add peak-sales backtest`
- `298b86a` - `fix(analysis): separate mixed POS backtest dataset`
- `bddb182` - `fix(models): treat prior phase data as fallback evidence`

Verification:

- `python -m pytest tests/ -v` passed.
- `ruff check src/` passed.
- Focused checks passed for calibration decomposition, oncology dataset guard, prior-phase fallback, POS realism, and peak-sales backtest.

Current caution:

- The mixed POS dataset is still small (`N=155`), and non-oncology slices are very small. Use OOS calibration metrics directionally, not as proof of precision.
- Peak-sales backtest is only a scaffold until many more sourced commercial cases are added.
