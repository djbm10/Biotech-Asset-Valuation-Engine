# How the Tool Scores (Plain-Language Overview)

**In one sentence:** the tool does two jobs — it puts a *dollar value* on a single
drug program, and it *ranks a watchlist* of biotech names each week into a short
buy/watch/avoid list — and every number it produces can be traced back to a stated
assumption.

> This is the backfill "everything it does and how it scores" overview. Each scoring
> layer below has a short *what it's based on* so you can explain it to someone who
> isn't in the code. Deeper technical detail lives in the repo's `CLAUDE.md` and
> `docs/pos_scoring_system.md`; the confidence/falsification layer has its own file,
> [Conviction Update Layer](conviction-update-layer.md).

---

## 2026-07-02 — Backfill: the full scoring picture

### The two things the tool produces

1. **A single drug's value** — "what is this program worth today, given the odds it
   ever reaches patients?" This is the *valuation pipeline*.
2. **A weekly ranked action list** — "of the names we track, which few deserve
   attention this week, and should we buy, watch, or avoid?" This is the
   *intelligence layer*.

They share the same underlying facts but answer different questions.

---

### Job 1 — Valuing a single drug

The value is a **risk-adjusted net present value (rNPV)**. Plain version:

> **Value = (chance the drug gets approved) × (money it would make, in today's dollars)
> − (what it costs to run the trials) + (any deal payments).**

The tool builds this in a fixed order, each step feeding the next:

**1. Probability of success (POS) — "will it actually get approved?"**
This is the single biggest lever, and it's built in three stacked pieces:

- **Base rate.** Start from the historical industry success rate for that *disease
  area and trial phase* — e.g. a Phase 2 cancer drug historically clears ~25% of the
  time, a Phase 3 rare-disease drug ~60%. These come from published industry data.
- **Layer 1 — the science signals (8 of them).** Nudge that base rate up or down based
  on trial specifics: strength of the goal being measured (a survival benefit counts
  far more than a lab marker), whether the drug's mechanism is already proven, trial
  size/statistical power, safety, biomarker selection, prior data, and breakthrough
  designation. Each signal moves the odds by a set amount; they're combined in
  "log-odds" so the result can never go above 100% or below 0%, and the *total* nudge
  is capped so a pile of good news alone can't fake a near-certainty.
- **Layer 2 — the trial-design quality (separate from the science).** Even a great
  drug fails if the trial can't *prove* it. This layer scores whether the study is
  designed credibly (blinded/randomized vs. single-arm), whether it's compared against
  the right standard of care, and the regulatory pathway. Good design helps a little;
  bad design can hurt a lot (the penalty is bigger than the bonus by design). The
  effect is scaled by phase — trial design matters far more at Phase 3 than Phase 1.

  *Guardrail:* Layers 1 and 2 are deliberately kept from scoring the same thing twice,
  and the tool warns if they overlap.

**2. Revenue — "how much could it sell?"** A year-by-year sales curve: how many
patients, at what price, how fast it ramps to peak, and a drop-off after patent expiry.

**3. Costs — "what will it take to get there?"** The remaining trial R&D and any deal
costs, in today's dollars, weighted by the odds each phase is even reached.

**4. Competition adjustment — "will rivals eat the market?"** Sales are trimmed by how
crowded the space is, who launched first, and whether the whole drug class saturates a
ceiling. This shrinks the revenue the drug realistically captures.

**5. Put it together (rNPV), then stress-test it.** The tool combines the above, then:
- runs **Bull / Base / Bear** scenarios,
- runs **10,000 randomized simulations** (varying the uncertain inputs together) to
  produce a *range* of values, not just one number, and
- runs a **tornado analysis** showing which 5 assumptions move the answer the most.

**What it's based on:** every input traces to a stated assumption in one config file,
each tagged with its source and how sensitive the answer is to it. Nothing is a black box.

---

### Job 2 — The weekly ranked action list

Separately, the tool tracks a watchlist of names and, each week, scores every one into
a single **composite score from 0 to 1**, then turns that into an action.

**The composite score is a weighted blend of three things:**

| Ingredient | Weight | What it's based on |
|---|---|---|
| **Ranking score** | 50% | The core opportunity/quality signal for the name |
| **Thesis strength** | 30% | How well the *evidence* has held up vs. what we predicted (confirmed vs. refuted claims). Neutral 0.5 if nothing's resolved yet. |
| **Opportunity score** | 20% | Timing/setup — is now an unusually good moment? |

(A newer "v2.0" mode can add six smaller signal nudges — catalyst timing, enrollment,
correlations, endpoint strength, competitor impact, capital risk — on top of the same
three base weights.)

**The score maps straight to an action:**

| Composite score | Action |
|---|---|
| ≥ 0.70 | **buy** — open a new position |
| 0.50 – 0.70 | **add** — increase an existing one |
| 0.30 – 0.50 | **monitor** — watch only |
| < 0.30 | **avoid** |

**Safety gates that can override the score (this is the important part):**
- **Running out of cash?** A company at CRITICAL risk of running out of money before its
  big readout is forced to **avoid** no matter how good the score. HIGH risk turns a
  weak score into an explicit **reduce**.
- **The critic flagged a concern?** A serious "caution" finding knocks a buy/add down to
  **monitor** — it's kept visible, not hidden, because a flagged concern beats a silent one.
- **Screening-grade names** (built from rough heuristics, not a full underwrite) can never
  be labeled buy/add — capped at **monitor** until someone does the real work.

**It never goes silent.** Even a week with nothing worth acting on produces an explicit
"no actionable opportunities" report, with counts of what was considered and why things
were filtered. Position sizes are proportional to the score and capped.

---

### The layer that changes its mind: science thesis & conviction

On top of the odds, the tool identifies the *one* make-or-break question for a program
("does the drug hit the target hard enough in humans?") and tracks confidence in it as
evidence arrives — and it will *lower* confidence when evidence argues against the
thesis. That's a whole subsystem with its own write-up:
see **[Conviction Update Layer](conviction-update-layer.md)**. Key point: that
confidence trail is a *diligence signal only* — it never secretly feeds back into the
POS, the valuation, or the weekly score.

---

### How we know the scoring actually works

Three checks run against real history:

- **POS backtest** — compares the odds the model assigned against how ~145 real cancer
  drug programs actually turned out. Current read: the model is *directionally
  well-calibrated* (its confidence roughly matches reality) — good enough to rank and
  compare, honest about not being a crystal ball.
- **Historical replay** — replays the weekly ranking week-by-week through past years
  *without letting it peek at the future*, and measures whether its picks would have
  paid off. This is the main path to proving the strategy statistically.
- **Portfolio backtest** — tests simple portfolio strategies built from the weekly
  scores over time.

**Bottom line:** the tool scores drugs on *odds × money − cost*, scores watchlist names
on a *50/30/20 blend with hard safety gates*, keeps a *separate, visible confidence
trail* for the one question that matters most, and *checks itself against history* — and
every number points back to a written assumption.
