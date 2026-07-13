# Conviction Update Layer

**In one sentence:** a transparent way for the tool to *raise or lower* its confidence
in a drug program's single most important make-or-break question as new evidence comes
in — and to show its work, including when evidence argues *against* the program.

---

## 2026-07-03 — First backtest of the killer-question picker itself (Idea 20, v1)

**What changed.** Built the measurement infrastructure to evaluate whether the tool
identifies the question that actually decided resolved drug programs — the eval that
must exist before conviction is allowed to influence any score.

**What was built:**
- A curated ground-truth label file: 18 resolved programs, each with the decisive
  archetype, why it was decisive, the source, and a citation date. Labels use hindsight;
  engine inputs are frozen to the pre-readout decision date (no lookahead).
- A no-lookahead replay harness that reconstructs the engine's science state as of the
  decision date and re-runs the killer-question picker — without any post-decision facts.
- A scorer that computes M1 (did the engine rank the decisive question #1 or #2?) and M3
  (did it abstain when and only when no question was dominant?), with a hard N-gate that
  prevents the output from being cited as calibration below the minimum sample size.

**First result (v1, `screening_backtest` mode):** M1 top-1 = 100%, N = 15 clean
programs. The honest interpretation: the harness is correctly wired. In v1 the snapshot
is constructed to leave *only* the decisive archetype open, so 100% is the expected floor
— it means no infrastructure bugs, not that the model is accurate.

**The `screening_backtest` stamp** is baked into every report line to prevent this
number from being overclaimed. Real M1 signal comes when the corpus includes cases
where multiple archetypes are simultaneously open and the picker has to rank them.

**Why this matters.** The conviction layer can annotate confidence and show its work in
memos and JSON. Whether it's *right* was previously unverified. This is the first step
toward verifying it — and the gate the plan requires before any conviction signal is
allowed to influence POS, valuation, BD score, or route.

**Still gated.** Conviction influence on any score remains off. The eval says the
plumbing works; it does not yet say the picker is accurate enough to earn that unlock.

---

> **Background terms (defined once):**
> - **Killer question** — the one question that most decides whether a drug program
>   succeeds (e.g. "Does the drug actually hit the target hard enough in humans?").
>   The tool already identifies this per program.
> - **Posterior** — the tool's current confidence (0–100%) in that question, after
>   weighing the evidence.
> - **Conviction trail** — the paper trail: starting confidence → each piece of
>   evidence and how much it moved the needle → ending confidence.

---

## 2026-07-02 — The expected-signature check now moves confidence (PR-3 step 4)

**What changed.** After one signature was reviewed and **approved by domain input**
(JAK inhibitors → the marker *pSTAT* should go **down**, as proof the drug is engaging
its target), we turned on the machinery that lets that signature actually move
confidence. Feed the tool an observed biomarker result and it now checks it against the
approved expectation and updates confidence accordingly — with a full paper trail.

**Why it matters.** This is the falsification engine doing its real job: if a JAK drug's
pSTAT *doesn't* drop the way the biology demands, that's genuine evidence against it, and
the tool will now *lower* confidence for that reason — visibly, with the rationale
attached. Confirmation raises it; contradiction lowers it; missing data does neither.

**How it works (plainly).**
- **Observed matches the approved expectation** (pSTAT went down) → confidence **up**.
- **Observed contradicts it** (pSTAT went up) → confidence **down** — real falsification.
- **The required marker wasn't measured** → **untested**: confidence doesn't move, and the
  trail says "we had an approved test for this, but no data to run it." Silence is never
  treated as failure.
- The move is a proper likelihood-ratio update (same honest math as the dose-response
  step), never a flat number, so it behaves sensibly at any starting confidence.

**The safety rails that make this trustworthy.**
- **Only *approved* signatures can ever move confidence.** The gate is enforced in code:
  a draft/example signature is structurally incapable of firing. Right now exactly one
  entry (JAK → pSTAT down) is approved; everything else stays draft.
- **Dormant until you feed it data.** With no observed biomarker input, the producer does
  nothing at all.
- **Still touches nothing else** — not the success odds, not the valuation, not any score.
  It only annotates the confidence trail for the one target-engagement question.

**Proof it works.** 9 automated checks against the real approved JAK entry: a match raises
confidence *via the likelihood ratio* (not a flat add), a contradiction lowers it, a
missing marker is untested (no move + flag), a **draft entry can never fire**, and the
trail shows up in the JSON summary. Full conviction/killer-question/science suites green.

---

## 2026-07-02 — Groundwork for "does the drug do what we expect?" (PR-3, plumbing only)

**What changed.** We laid the foundation for a new kind of evidence check: for a given
drug mechanism, define *ahead of time* the lab-marker changes we'd expect to see if the
drug is really working (its "expected signature"), so real results can later be checked
against it. This step built the library, the loader, and a safe read-out — **but did not
turn on any scoring yet.**

**Why it matters.** This is the sharpest falsification tool in the set: if a drug
*doesn't* show the changes its mechanism demands, that's real evidence against it. But
it's only as trustworthy as the expected signatures we write down — **a wrong "expected"
entry would confidently argue against a good drug.** So we deliberately built the machinery
first and left the actual scoring switched off until a domain expert signs off on each entry.

**How it works (plainly).** Each signature entry carries a **review status**:
*draft*, *approved*, or *retired*. The hard rule baked in: **only "approved" entries will
ever be allowed to move confidence.** Everything currently in the library is *draft /
example-only*, so right now the tool will, at most, show "a relevant signature exists for
this program — not scored." Nothing changes any number.

**What it deliberately does *not* do (yet).** No automatic data gathering, no AI-generated
signatures, no change to success odds, valuation, or any score. It only *displays* that a
candidate signature is available and untested.

**Proof it works.** 13 automated checks: the library loads and validates (malformed entries
are rejected outright), and the headline invariant — *every* surfaced signature reads as
"not scored," **even an approved one** — holds, because no scoring is wired yet.

**Still gated.** Turning approved signatures into real confidence updates is a separate,
later step that won't start until the seed signatures are reviewed by domain experts.

---

## 2026-07-01 — Dose-response evidence now moves confidence honestly (PR-2)

**What changed.** When a drug shows a *dose-response trend* (higher dose → bigger
effect — a classic sign the drug is really doing something), the tool used to just add
a flat +10% to its confidence. We replaced that with a principled update, and it now
writes the change into the conviction trail so you can see it happened.

**Why it matters.** A flat "+10%" is a guess that behaves oddly — add it to something
already at 92% and you get a nonsensical 102%-style result, and it hides *why* the
number moved. The new method never overshoots, moves the needle by a sensible amount at
any starting point, and leaves a readable reason ("human dose-response trend supports
adequate target engagement"). Same directional judgment as before, now defensible in a
diligence conversation.

**How it works (plainly).** Instead of adding a fixed number, evidence is applied as a
"how much more likely is this drug to work, given what we just saw" multiplier. Strong
positive evidence pushes confidence up but with diminishing returns near 100%; it can
never exceed certainty. A dose-response trend is treated as moderately positive.

**What it deliberately does *not* touch.** This is a *diligence/confidence* signal only.
It does **not** change the drug's success-probability estimate, its valuation, its
business-development score, or which killer question is chosen. Those stay exactly as
they were — this only annotates our confidence with an auditable trail.

**Proof it works.** The trend now correctly raises confidence more than a flat readout;
a flat/no-trend readout changes nothing (silence is not treated as bad news); and the
trail shows up in the memo and JSON on normal runs. Full test regression on the report
and valuation paths passed (293 checks).

---

## 2026-07-01 — The confidence trail now shows up in reports (Surfacing)

**What changed.** The conviction trail is now printed in the BD (business development)
memo and the machine-readable JSON output: for the killer question you see
*starting confidence → each evidence update → ending confidence*, with the reason,
strength, and type of each update.

**Why it matters.** An engine that quietly changes a number is hard to trust. Showing
"we started at 50%, this readout was a clean hit, so we moved to 75%, here's why" is
exactly what an analyst or partner needs to sanity-check the call — and it's easy to
explain to someone outside the tool.

**How it works (plainly).** Each program carries a small, read-only list of confidence
updates. The report and JSON builders render it as a compact table. It's presentation
only — reading it changes nothing about the underlying scores.

---

## 2026-07-01 — The confidence engine itself (PR-1)

**What changed.** Built the core engine that takes a piece of evidence and updates
confidence in a killer question, plus the first evidence reader (for clinical trial
readouts).

**Why it matters.** This is the foundation for a "falsification engine" — a tool that
can be *talked out of* a thesis by evidence, not just talked into one. Being able to
lower confidence, credibly, is what makes the raise-confidence side trustworthy too.

**How it works (plainly).**
- Evidence is combined so a single strong "this refutes the thesis" result can outweigh
  several weak "this supports it" results — weak confirmations can't drown out a real
  red flag. Confidence is mathematically kept between 0% and 100%.
- **Readouts vs. the bar:** a trial result is compared to the effect size that actually
  matters for the disease. It lands in one of four buckets:
  - *Clean hit* → confidence up.
  - *Near miss, but trending the right way* → confidence up a little (the key insight:
    a near-miss with a real dose-response trend should **not** snap back to the base
    rate — it's a weak positive, not a failure).
  - *Clean miss* → confidence down.
  - *Silence / no data* → **no change** (we never treat "we haven't looked" as bad news).
- **A human can override** the confidence at any time, and that override is logged with
  a reason — never a hidden change.

**Guardrails baked in.** Confidence never feeds back into success-probability or
valuation; every update carries a reason; refuting evidence is a first-class citizen;
silence is never treated as refutation.

**Proof it works.** 12 automated checks, including the headline one: a near-miss *with*
a dose-response trend raises confidence, while the *same* near-miss *without* a trend
lowers it — trend is the deciding factor.

---

## Still to come (Batch 2)
- **More approved signatures:** each new mechanism goes through the same domain-review
  gate before it can move confidence (the C5/complement entry is drafted but not approved).
- **Feed observed biomarkers from the asset config:** the producer is wired and tested;
  the remaining integration is a config field to supply observed biomarker results per run.
- **Backtest:** measure how often these confidence updates actually pointed the right way.
