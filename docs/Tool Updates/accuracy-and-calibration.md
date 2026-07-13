# Accuracy And Calibration

Plain-language record of the valuation-accuracy work. Goal is honest calibration and uncertainty, not false precision.

## 2026-07-09 - Claim Ledger: All 37 Programs Source-Drafted (still zero promoted)

### What Changed

Scaled the source-drafting fetch pass from the initial 5-program sanity batch to all 37
programs (97 draft rows total). Standardized the fetch path first: `*.fda.gov` is
domain-wide blocked to the fetch tool (confirmed by testing every path tried, not assumed),
so the real path is PMC free full text for pivotal trial papers (works even when the
publisher page 403s) and DailyMed's SPL version-history API for point-in-time FDA label
snapshots (the default DailyMed page serves today's label, which is the wrong,
lookahead-contaminated snapshot for an old approval). Four parallel research passes covered
the remaining 32 programs; results were merged, re-audited for outcome leakage, and
regenerated into all 37 reviewer packets.

### Why It Matters

- **67 of 89 drafted quotes are now verbatim-confirmed** against a real fetched source (PMC
  or a dated DailyMed label version), not reconstructed from search-summary paraphrase. The
  remaining 22 are honestly flagged `needs_primary_pdf_confirmation` where the primary paper
  is paywalled with no PMC copy (e.g., BELLE-3, CHRONOS-1's original trial report).
- **The leakage audit caught one real miss.** One drafted note (mobocertinib) named the
  program's actual 2023 market withdrawal — even though the intent was to explain *why* an
  earlier data cutoff was used, naming the outcome at all is the leak. Scrubbed before
  merge. Everything else the leakage detector flagged (e.g., "the approved dose," "before
  final approval") turned out to be benign — describing the labeled dose or the human
  reviewer's own sign-off, not a program outcome.
- **Still nothing scored.** `n_drafts=97, n_candidate=97, n_approved=0, n_promotable=0,
  affects_live_pos=False`. Every draft stays AI-authored/human-unapproved by construction;
  no likelihood ratio drafted here was allowed outside a conservative band (confirming
  1.0–3.0, refuting 0.3–1.0) and no drafter touched `review_status`/`source_verified`
  directly — both stayed exactly as the skeleton left them. 14,297 tests green.
- **What's next:** human review pass (Chris/Harvey) against the 37 reviewer packets in
  `research/review/reviewer_packets/`. Nothing here is load-bearing until that happens.

## 2026-07-05 - Claim Ledger: Corpus Leakage Scrub (blind review made real) + Fetch-Pass Corrections

### What Changed

Before scaling the source-drafting pass to all 37 programs, we scrubbed the corpus of
lookahead leakage. An audit found **18 of 37** evidence notes reasoned *from* the outcome —
"feasible for accelerated approval", "approvals support a held therapeutic window", "before
market withdrawal decision". In a blind reviewer packet that hands the reviewer the answer.
A reusable scrubber removed the outcome language while preserving the pre-decision evidence
(trial names, response rates, toxicity), and a residual detector confirms the corpus now has
**zero** leakage. A regression test keeps it that way.

### Why It Matters

- **Leakage is more dangerous than slow progress.** If the packet hints at the outcome, the
  reviewer's label is contaminated and the whole calibration is compromised. This was worth
  stopping to fix before adding 32 more programs.
- **The scrub only removes, never invents.** It strips the leaked outcome; it does not add a
  new claim. The original text is preserved in version history, and the transform is
  mechanical and testable, not a hand-wave.
- **The FDA-quote pass got more honest.** Fetching FDA labels through DailyMed surfaced a
  real error in the first batch — the current Venclexta label has no boxed warning (tumor
  lysis syndrome sits in Warnings, not a boxed warning), so that citation was corrected.
  Every quote now carries a `quote_status`: `verbatim_confirmed` where we pulled the exact
  wording (inavolisib), or `needs_primary_pdf_confirmation` where the FDA PDF was blocked to
  the fetcher and the wording was reconstructed (navitoclax, umbralisib, poziotinib,
  venetoclax). The reviewer sees which quotes still need eyes on the source PDF.
- **Still nothing scored.** All five remain candidate/unverified; gate closed. With the
  corpus clean, the remaining 32 programs can now be drafted the same way.

## 2026-07-05 - Claim Ledger: AI Source-Drafting Workflow With a Hard Human Approval Line

### What Changed

AI can do most of the grunt work — find the primary source, pull the exact supporting
quote, propose the strength and weight — as long as its drafts can never grade themselves.
This adds that workflow. AI drafts land in a distinct **`reviewer_candidate`** state that is
inert by construction; the only path from a draft into the scoring pipeline runs through a
promotion step that lifts a draft *only* after a human has both confirmed the quote against
the source and approved it. Running it produced a **97-row draft worksheet**
(`research/review/claim_source_drafts.csv`) and **37 reviewer packets for Chris/Harvey**
(`research/review/reviewer_packets/`).

### Why It Matters

- **The approval line is a wall, not a norm.** "AI drafts → human approves → model scores →
  calibration runs" is enforced in code: a `reviewer_candidate` draft is never promotable,
  and even an `approved` draft is dropped if its source isn't marked verified. Both are
  pinned by tests. An AI draft physically cannot move a probability.
- **No fabricated citations.** The draft skeleton fills context and search targets but
  leaves the source link and quote blank — those get filled by a real fetch pass with
  verifiable links, never from model memory. The reviewer packets are stamped "AI DRAFT —
  UNVERIFIED" and every quote carries a "confirm against source" checkbox.
- **Review stays blind.** The packets omit the outcome, so Chris/Harvey approve on the
  evidence, not backwards from the result (verified by test).
- **Promotion re-enters the same gate.** A promoted atom must still clear the five
  calibration bars from the review layer, so approval and scoring use one contract, not two.
- **Still nothing scored.** Status: `candidate=97, approved=0, promotable=0,
  affects_live_pos=False`. The next step is the real fetch-and-quote pass (fill links +
  quotes) followed by human verification + approval.

## 2026-07-05 - Claim Ledger: Reviewer Packet + Promotion Gates (bottleneck is now review, not code)

### What Changed

The 97 candidate atoms are inert until a human reviews them against primary sources. This
builds the worksheet that review runs on, and the gates that decide which reviewed atoms
are allowed to count. Running it produced a **97-row review packet**
(`research/review/claim_atom_review_packet.csv`) plus **37 per-program Markdown sheets**
(`research/review/programs/`). Each packet row pairs a candidate atom with its program's
question and full evidence text, lists the specific primary sources to go find (FDA
label/review, ODAC/EPAR, ClinicalTrials.gov, pivotal papers), and leaves blank columns for
the reviewer's verdict.

### Why It Matters

- **Review is blind to the answer.** Each Markdown sheet shows the evidence and asks for a
  verdict, but the outcome (did it succeed/fail, why) is deliberately omitted — verified by
  a test. The reviewer judges the evidence on its merits, not backwards from the result.
- **The calibration gate is strict and separable.** For an atom to feed a score it must
  clear five independent bars: the extraction is reviewed, the evidence is approved (not
  rejected, not draft), a real primary source is named, a genuine weight is set (a missing
  weight blocks it), and the strength is high/medium (weak evidence only raises a question).
  Each bar is pinned by its own test. Fail any one and the atom is ignored; a program with
  no clearing atoms yields no prediction at all.
- **Source promotion is built into the workflow.** Every sheet names the current
  (secondary) link and the primary sources that should replace it, so the Wikipedia→FDA
  upgrade is part of the review pass, not a separate chore.
- **Still nothing scored.** Status reads `eligible=0, predictable_programs=0,
  affects_live_pos=False`. The gate is closed until the review pass promotes atoms. The
  code is done; the value now comes from turning ~97 inert candidates into 20–40
  primary-source-backed, approved atoms.

## 2026-07-05 - Claim Ledger: Evidence-Atom Extraction Scaffold (still uncalibrated)

### What Changed

To score the corpus, the model needs the *other half* of each calibration pair: its own
read of what was known before each decision. That read has to start from the raw evidence
notes, broken into individual, checkable pieces. This scaffold does that first pass — it
turns each program's evidence prose into structured "atoms" (one claim + one snippet each)
and lays them out as a review worksheet. Running it over the 37-program corpus produced
**97 candidate atoms** across all 37 programs (`research/data/claim_evidence_atoms.csv`).

### Why It Matters

- **It is deliberately timid.** Every freshly extracted atom comes out at the weakest
  possible setting — low-strength, "inferred" not observed, unreviewed, and with a neutral
  placeholder weight — so a raw extraction physically *cannot* move any probability. Each of
  those four alone would zero it out; all four together make it inert by construction. A
  human reviewer has to promote the strength, set the real weight, confirm it was actually
  observed, and approve it before a single atom counts.
- **It cannot peek at the answer.** The extractor reads the evidence text only. It never
  looks at the outcome columns (did the window hold, did the program succeed, why it failed).
  That is enforced in code and pinned by a test — so the model's "prediction" can't be
  secretly contaminated by the result it will later be graded against.
- **Two locked doors, not one.** An atom needs *both* the extraction reviewed AND the
  evidence itself approved to become material. A test proves that a row lying about its own
  status (claiming strong/observed/approved while the extraction is unreviewed) is still
  forced inert.
- **Still uncalibrated.** Coverage summary reads `material_capable=0, affects_live_pos=False`.
  Nothing here is graded yet; the NO LIVE POS GATE stays closed. The next human step is the
  per-atom review pass (promote strength, set weights, approve) against primary sources.

## 2026-07-04 - Claim Ledger: First 37-Program Review Draft Ingested (still uncalibrated)

### What Changed

A first pass of human research came back — 37 oncology programs of the dose-limiting-
toxicity class (navitoclax, the PI3K-inhibitor cluster, several antibody-drug conjugates,
the approved BTK/ALK/KRAS drugs), each with a target, modality, a candidate answer to "did
the therapeutic window hold," and a source. We ingested it into the corpus (normalizing the
human "yes/no" answers to the schema's true/false) and added a **base-rate preview**.

Of the 37, 19 are candidate "window held," 11 "window failed," and 7 "unknown" — a
provisional held-rate around 63%.

### Why It Matters

- **This is the first real signal of what the exposure/window prior looks like** — roughly
  two-thirds of these programs cleared the window. That number is a useful anchor for the
  model's starting assumption (its prior), which is exactly what this data is for.
- **But every guardrail is deliberately still up.** The preview is labeled non-load-bearing
  in code and in its output: the labels are candidates, the sources are Wikipedia summaries
  rather than FDA reviews or trial papers, and not one row is approved. The calibration
  number the model actually trusts still reads "uncalibrated, zero approved rows," and the
  NO LIVE POS GATE stays closed.
- **What is NOT done, on purpose:** promoting these to primary sources and `approved`
  status, and generating the model's own prediction for each so we can score it. Both are
  required before any of this touches a real POS number. The 63% is an orientation aid, not
  a result.

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
