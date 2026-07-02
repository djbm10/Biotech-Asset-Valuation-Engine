# Conviction Update Layer

**In one sentence:** a transparent way for the tool to *raise or lower* its confidence
in a drug program's single most important make-or-break question as new evidence comes
in — and to show its work, including when evidence argues *against* the program.

> **Background terms (defined once):**
> - **Killer question** — the one question that most decides whether a drug program
>   succeeds (e.g. "Does the drug actually hit the target hard enough in humans?").
>   The tool already identifies this per program.
> - **Posterior** — the tool's current confidence (0–100%) in that question, after
>   weighing the evidence.
> - **Conviction trail** — the paper trail: starting confidence → each piece of
>   evidence and how much it moved the needle → ending confidence.

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
- **Expected-signature check:** for a given mechanism, define ahead of time what
  biomarker changes we'd expect to see, then check real data against it (matches raise
  confidence, contradictions lower it). Uses a hand-curated library, no auto-generation.
- **Backtest:** measure how often these confidence updates actually pointed the right way.
