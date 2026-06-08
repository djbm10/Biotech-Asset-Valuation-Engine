# Future Fixes and Known Limitations

This file tracks features the system does not yet do, design gaps that are known and intentional,
and planned improvements. It is the honest counterpart to the architecture documentation.

---

## What It Does Not Fully Do Yet

### 1. It does not automatically discover every good target

The SEC scanner (`src/bve/ingestion/universe_scanner.py`) can discover biotech-ish tickers from
EDGAR filings, but the real M&A universe still requires manual curation. The scanner can expand
coverage from ~50 to 100–150 names, but those names need a human to confirm therapeutic focus,
stage, and encumbrance status before they enter the acquirer-fit scoring pipeline.

**The gap**: automated discovery ≠ curated universe. A name scraped from EDGAR may be a
diagnostics company, a CDMO, or a platform play that looks like a drug company. The
`research/universe/targets.yaml` and `research/universe/acquirers.yaml` files are the curated
ground truth. The scanner feeds candidates into that curation process; it does not replace it.

### 2. It does not deeply parse unstructured news yet

The ingestion layer handles SEC filings, ClinicalTrials.gov, and FDA structured/semi-structured
sources. It does not yet have a strong RSS/news/LLM layer for headlines like:

> "Company reports encouraging early data in rare kidney disease"

unless the rule-based event classifier (`src/bve/ingestion/event_classifier.py`) happens to catch
the pattern. The event classifier works on keyword rules and signal types — it will not reliably
extract p-values, effect sizes, or endpoint context from free-text press releases. A full NLP/LLM
parsing layer for unstructured biotech news is a planned but not-yet-built component.

### 3. It does not prove accuracy yet

The engine produces candidate rankings and M&A fit scores, but there is no validated evidence
that these rankings are predictive of actual acquisitions at a statistically meaningful level.

The VRTX/REGN backtest (Block 15) is a step toward proof, but:
- N=5 verified primary positives
- 4 of 5 are Vertex; REGN has N=1
- All hit-rate and AUC figures have confidence intervals spanning roughly 0%–100%

Proof requires:
- Historical acquisition dataset with ≥20 verified deals across ≥3 acquirers
- Rolling 24-month backtest with no-lookahead guarantee
- Precision@10, Precision@25
- AUC-ROC with p-value < 0.05
- Brier score and calibration curves
- Out-of-sample validation on a held-out acquirer

None of these are complete. The backtest infrastructure is built; the labeled dataset is not
large enough yet.

### 4. It does not model goodwill or acquisition control premium

The rNPV output is intrinsic value — the probability-weighted discounted cash flow of the asset
if developed and commercialized by the current holder. Observed M&A prices routinely include
30–80% premiums over intrinsic value. That gap is goodwill. The tool does not model it.

**What goodwill captures that the tool misses:**
- Acquisition control premium over intrinsic value
- Assembled workforce / platform know-how
- Strategic synergies (cost savings, cross-selling)
- Brand / relationships
- Pipeline optionality beyond the modeled indication(s)

**What the tool partially captures as proxies:**
- Platform value is approximated via modality scoring and TA fit in the M&A layer
- Acquirer urgency / pipeline pressure reflects some strategic premium logic
- `deal_premium.py` compares observed deal prices to rNPV — the gap between them is
  essentially goodwill + control premium, but it is measured after the fact, not modeled
  prospectively into the asset price

**Practical implication**: The tool will systematically underprice acquisition targets relative
to actual deal values. The rNPV output is best interpreted as a **floor valuation** or intrinsic
value baseline, not an expected deal price. A BD team should add an explicit strategic premium
estimate on top of rNPV when sizing deal probability or comparing to rumored deal prices.

See `DEAL-1` in Planned Improvements for the implementation path.

### 5. It is not institutional-grade validated yet

The architecture is substantially closer to institutional grade than when the project started
(no-lookahead enforcement, source freshness audits, CT.gov point-in-time exclusion, bucket
minimum gates, VRTX-heavy disclaimers). But clean architecture does not prove the model works.
Evidence of predictive validity comes from backtesting against historical outcomes, not from
reading the codebase. Until the backtest dataset reaches ≥20 verified deals and the
rolling-window evaluation produces a statistically interpretable AUC, the tool is a
decision-support framework, not a validated predictive model.

---

## Planned Improvements

### HARVEY-0 — Harvey's advice: science thesis, belief update, and BD fit layer

**Source**: Notes from `docs/advice/Harvey Advice.md`.

**Core message**: The tool should not try to answer every scientific question
with a broad generic score. It should identify the one or two critical
scientific or strategic questions that create a bifurcation in value: 10x
better, 10x worse, program shutdown, or expansion into a much larger population.
The best use of AI is a human-machine interface: combine the analyst's base
belief with public information retrieval, structured evidence, and explicit
belief updates.

**What to add to the tool**

1. **Macro/regulatory timing overlay**
   - Track FDA staffing, political environment, review-capacity bottlenecks,
     and whether IND/FDA timelines may move faster or slower.
   - Treat these as timing and probability overlays on top of historical base
     rates, not as a replacement for asset-level science.

2. **Killer thesis question extraction**
   - For each asset, extract the main biological hypothesis from company
     presentations, quarterly calls, earnings transcripts, conference decks,
     clinical readouts, and papers.
   - Identify the one or two readouts that would actually answer that
     hypothesis.
   - Store the question explicitly, e.g. "Does target X modify disease Y enough
     to matter?" or "Can this modality deliver enough drug to the brain?"

3. **Target biology validation**
   - Score whether the drug hits the right target or pathway for the disease.
   - Look for genetic association between target and disease.
   - Look for clinical validation from drugs hitting the same receptor, target,
     protein, or adjacent pathway.
   - Distinguish causal genetic support from weak or spurious association.
   - Use competitor and analog-pathway data as evidence for or against target
     validity.

4. **Drug exposure, PK/PD, and tissue delivery**
   - Score whether enough drug reaches the target tissue at the tested dose.
   - Track on-target tissue biodistribution and off-target tissue distribution.
   - Evaluate potency against the degree of pathway suppression required.
   - Parse whether the dosing interval is biologically plausible.
   - Distinguish biology that needs transient spikes from biology that needs
     sustained suppression.
   - Use dose-response and exposure-response trends to infer target engagement.

5. **Biomarker quality and target engagement**
   - Extract biomarkers that are expected to move if the pathway is being hit.
   - Rank biomarkers by how directly they answer the biological hypothesis.
   - Distinguish target-engagement biomarkers from weak correlative biomarkers.
   - Check public clinical or preclinical data for expected biomarker movement.
   - Preserve upside after a failed or marginal trial when biomarker data shows
     underdosing or partial pathway engagement rather than wrong biology.

6. **Readout interpretation beyond pass/fail**
   - Do not treat clinical results as binary endpoint pass/fail.
   - Capture whether the trial barely passed, strongly passed, failed but
     trended, or showed no effect.
   - Capture dose response, population differences, trial-design differences,
     and comparator differences before concluding the asset is good or bad.
   - Distinguish a true clinical failure from a miss against arbitrary market
     expectations.
   - Use the result to update the biological thesis, not only the phase status.

7. **Effect size, clinical meaning, and market-share relevance**
   - Model whether longer dosing interval alone is valuable or whether the drug
     needs multi-pathway efficacy to take share.
   - Capture whether the readout unlocks a much larger indication or patient
     population.
   - Separate minor incremental improvements from true value-inflection data.
   - Include tolerability, convenience, and KOL sentiment in market-share
     assumptions.

8. **Safety and toxicity layer**
   - Track off-target tissue toxicity and pathway inhibition in unwanted
     tissues.
   - Treat safety and tolerability as core POS and commercial adoption inputs.
   - Ingest conference notes and KOL commentary about tolerability when public.

9. **Competitive and KOL context**
   - Compare clinical results against the next-best competitor and standard of
     care, not only against the trial's stated endpoint threshold.
   - Ingest KOL comments from conferences and transcripts because those views
     can move expected market share.
   - Detect cases where the market overreacted to a near miss that is clinically
     close to the best competitor.

10. **Investment decision loop**
    - Use the tool for thesis-driven investing and medium-term arbitrage, not
      daily trading.
    - Define the expected signal, expected price movement, and expected time
      window before entering a position.
    - When the signal occurs, record the model's expected action and the
      analyst's executed action.
    - If the signal does not occur or the market does not react as expected,
      record why and use it for model learning.

11. **BD strategic fit and synergy**
    - Score whether an asset complements and unlocks value in an acquirer's
      existing portfolio, not only whether it has high standalone rNPV.
    - Include modality fit: small molecule, antibody, protein, gene therapy,
      RNA, cell therapy, etc.
    - Include whether the acquirer has development, manufacturing, clinical,
      and commercial resources for that modality.
    - Distinguish "this fills a strategic gap we want to enter" from "this is a
      capability stretch we should avoid."
    - Keep the standardized scoring framework, but let the subject matter expert
      apply room-level context and override reasoning.

**How Harvey would approach fixing it**

1. **Start with the key question, not the score**
   - For each asset, force the analyst/tool to write the main biological
     question and the one or two readouts that would answer it.
   - Do not let generic science sub-scores change POS unless they map back to
     that question.

2. **Build an evidence packet around that question**
   - Pull company decks, earnings-call transcripts, quarterly presentations,
     conference notes, ClinicalTrials.gov records, PubMed papers, competitor
     readouts, and preclinical data.
   - Ask targeted retrieval questions:
     - Is the target causally linked to the disease?
     - Is there clinical or genetic validation?
     - Does the drug reach the target tissue?
     - Is target engagement shown by the right biomarker?
     - Is the dose interval consistent with the biology?
     - Did the trial result answer the thesis question?

3. **Turn the answer into a belief update**
   - Record prior belief before the readout.
   - Record evidence observed.
   - Record whether the evidence confirms, weakens, or leaves the thesis
     unresolved.
   - Update POS/rNPV only after explaining the mechanism of the update.

4. **Separate thesis failure from execution failure**
   - Wrong target/pathway: large POS reduction or program-kill flag.
   - Right biology but underdosed: discount value, preserve optionality if dose
     optimization is plausible.
   - Biomarker moved but endpoint missed: lower confidence, but do not treat as
     equivalent to no biological effect.
   - Endpoint barely missed against an arbitrary threshold: compare to clinical
     meaning, competitor profile, and market expectations before marking down.

5. **Keep human review in the loop**
   - Let AI retrieve, summarize, and propose the belief update.
   - Route judgment-heavy calls to expert review: target validity, biomarker
     relevance, dosing adequacy, KOL sentiment, strategic fit, and modality
     capability.
   - Store the expert's rationale so future backtests can learn which judgments
     were useful.

**Priority**: High. This is the most direct path from a generic valuation/POS
tool to a useful biotech diligence assistant: it makes the model reason about
the specific scientific question that could actually change the asset's value.

---

### HARVEY-1 — Drug delivery / PK-PD confidence as a POS Layer 1 adjuster

**Source**: Harvey Advice (05 June 2026), synthesised from HARVEY-0.

**Core gap**: The existing POS model captures target biology (MoAPrecedent,
MoAExceptionFlag) and endpoint/trial design (TrialDesignFeatureSet). What is
not captured at all is whether there is evidence that *enough drug reached the
target site at the tested dose*. Harvey identified this as the second critical
bifurcation question after target validity: right biology + wrong dose/delivery
= program failure that looks like biology failure.

**What to add**

1. **`DrugDeliveryConfidence` enum in `pos_model.py` (Layer 1)**

   Five tiers, applied in log-odds space as a new field on `POSAdjusters`:

   | Tier | Log-odds | When to use |
   |---|---|---|
   | `confirmed` | +0.20 | Dose-response trend shown AND direct target-engagement biomarker moved |
   | `likely` | +0.07 | PK data consistent with target engagement; no direct biomarker yet |
   | `uncertain` | 0.00 | No public PK/PD data — default; zero adjustment |
   | `poor` | −0.20 | Known tissue-access barrier (e.g., CNS target with no CNS PK shown) |
   | `conflicting` | −0.35 | Dose data exists but target engagement not demonstrated at tested dose |

   Default is `uncertain` so existing configs require no changes.

2. **`ScienceThesis` dataclass in a new `src/bve/intelligence/science_thesis.py`**

   Stores the "killer thesis question" for each asset — the one or two
   biological questions whose answer creates a value bifurcation. Not a POS
   input itself; used to surface the question in the weekly report and to anchor
   belief-update records.

   Fields:
   - `killer_question: str` — e.g. "Can we suppress RAS ≥90% at the tested
     dose?"
   - `key_readout_event: str` — which trial result or event answers it
   - `delivery_confidence: DrugDeliveryConfidence`
   - `thesis_last_updated: Optional[date]`
   - `belief_history: list[str]` — ordered log of prior → evidence → update

3. **Anti-double-count guard**

   In `check_pos_layer_overlap()`, flag a warning if both
   `drug_delivery_confidence=confirmed` and
   `MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM` are set — they partially
   overlap because human POM often implies target engagement at dose.

**What this does NOT add**

- Does not add a broad generic "science score" — Harvey explicitly warned
  against this.
- Does not model PK parameters numerically (half-life, Cmax, Ctrough). Those
  require data not reliably available from public sources.
- `ScienceThesis` does not feed POS directly at first — it is a structured
  annotation layer for the analyst to reason against, not an automated scoring
  input.

**Backward compatibility**: `drug_delivery_confidence` defaults to `uncertain`
(0.00 log-odds adjustment). All existing YAML configs and test fixtures
continue to work unchanged.

**Priority**: Medium. The POS model already covers target biology reasonably
well through MoAPrecedent and MoAExceptionFlags. Drug delivery confidence is
the single largest missing signal Harvey identified. Add after the calibration
runner (Sprint E) has had a chance to show whether the existing Layer 1
adjusters are well-weighted.

---

### HARVEY-2 — Two-question science framework: right target + enough drug

**Source**: Harvey Advice (05 June 2026). Direct quote context.

**The explicit simplification Harvey gave**: Everything in a science layer
should reduce to one of two questions. Everything else — biomarkers, dose
response, trial design, endpoint choice — is evidence you use to answer one
of them.

**Question 1: Did you hit the right target?**

> "What's the known data that says that this target is likely to modify the
> disease? Is there any genetic data that associates the target with the
> disease? Is there clinical validation from drugs hitting the same receptor,
> target, protein, or adjacent pathway?"

Signals that answer Q1:
- Genetic association (GWAS, Mendelian): causal vs. spurious
- Clinical analog: approved drug in the same mechanism class
- Pathway validation: different target but same signaling chain has worked
- Competitor failure analysis: was the failure drug-quality or target-biology?

**Question 2: Did enough drug reach the target at the tested dose?**

> "If your disease is in the brain, it's much harder to actually get to the
> brain. This is probably why neuroscience tends to have a lot of failures —
> you might have hit the right target, but you didn't get enough of the drug."

Signals that answer Q2:
- On-target tissue biodistribution data
- Off-target tissue distribution (safety corollary)
- Dose-response trend: higher doses → stronger effect = target being engaged
- Pathway suppression level vs. required level (e.g., need 90–99%, got 20–50%)
- Dose interval plausibility: transient spike vs. sustained suppression biology

**Why only two questions**

> "In the end, it's really one or two of those questions that we're really
> worried about as a team. It sounds like you really want to hone in to that —
> what is that killer thesis question that's going to give you a bifurcation."

Biomarker quality, endpoint design, trial design, KOL sentiment — all of these
matter, but they matter as *evidence for Q1 or Q2*, not as independent science
dimensions. Adding more top-level dimensions creates a broader score that looks
more complete but answers a less precise question.

**Implementation rule**

When building the science layer, the first field to populate for each asset is:

```text
primary_science_question: "Q1: right target" | "Q2: enough drug" | "both"
```

Then evidence is attached to that question, not to a generic science bucket.

**Priority**: High. This is the distilled version of everything Harvey said
about science. HARVEY-1 (`DrugDeliveryConfidence`) implements the Q2 signal.
Q1 is partially covered by `MoAPrecedent` and `MoAExceptionFlag`. The gap is
that nothing forces the analyst to *explicitly declare which question is the
primary risk* for each asset before scoring begins.

---

### HARVEY-3 — Structured diligence question format

**Source**: Harvey Advice (05 June 2026).

Harvey described a specific 4-step diligence question format that the tool
should be able to run for each asset. His exact framing:

> "If the question is 'nobody believed we can target RAS' — did the data
> readout suggest they're inhibiting that pathway? The tool should be able
> to say: if they were hitting the pathway, we should expect to see signaling
> protein X, Y, Z go down, and this clinical marker go up. Is there any
> public info that shows that they were able to hit these in trial or
> preclinical study?"

**The four steps**

1. **State the biological thesis question**
   - One sentence: what the company believes must be true for the drug to work
   - Example: "Inhibiting KRAS G12C will reduce tumor proliferation in NSCLC
     patients with this mutation"

2. **Define what observable evidence would confirm or refute it**
   - If the thesis is true, what should we see in the data?
   - Example: "KRAS downstream signaling proteins (pERK, pAKT) should decrease;
     tumor response rate should exceed 30%"
   - This step forces precision — it makes the thesis falsifiable before the
     readout happens

3. **Search public sources for that evidence**
   - Company presentations, earnings-call transcripts, CT.gov, PubMed,
     competitor readouts, preclinical publications, conference abstracts

4. **Return a verdict**
   - Confirmed: evidence aligns with thesis
   - Weakened: evidence is inconsistent or ambiguous
   - Unresolved: not enough public data to assess

**Why this matters for the tool**

Currently the tool ingests events and updates scores, but it does not reason
about whether a specific readout answered the thesis question. A Phase 2 pass
is treated as a Phase 2 pass. Harvey's framework says: a Phase 2 pass that did
not answer the primary thesis question is less informative than a Phase 2 that
directly addressed it.

**What to build**

A `ScienceThesisRecord` per asset:
- `thesis_question: str` — the one-sentence falsifiable biological question
- `expected_confirmatory_signals: list[str]` — observable signals that would
  confirm it
- `expected_refutation_signals: list[str]` — signals that would weaken it
- `evidence_for: list[str]` — public references supporting confirmation
- `evidence_against: list[str]` — public references supporting refutation
- `verdict: "confirmed" | "weakened" | "unresolved"` — current state
- `last_updated: date`

The verdict feeds into the `ScienceThesis.delivery_confidence` field from
HARVEY-1 and into the weekly report's "Killer Thesis Question" section.

**Priority**: Medium. This is primarily a data-entry and reasoning layer.
The schema is simple; the hard part is populating it from public sources.
Start by requiring the analyst to fill `thesis_question` manually for each
asset in `targets.yaml`. Automate retrieval later.

---

### HARVEY-4 — Human-machine belief update interface

**Source**: Harvey Advice (05 June 2026).

> "I can ask Claude to make a guess, or I can interface with it as I have a
> base belief around it, and it has certain access to a bunch of information,
> and we can now interface my base belief with its info and update my belief,
> and hopefully get to something that is more significant than either of us
> could have alone."

Harvey described this as the right model for how the tool should work — not
AI replacing judgment, but AI providing structured evidence that the analyst
uses to update a prior belief.

**The explicit Bayesian structure**

```text
prior_belief  →  evidence  →  posterior_belief
     (analyst)    (tool)           (analyst + tool)
```

Each science thesis record should have:
- `analyst_prior_confidence: float` — analyst's belief before seeing the
  evidence (0–1, subjective)
- `evidence_summary: str` — what the tool found in public sources
- `evidence_direction: "confirms" | "weakens" | "unresolved"` — tool's
  assessment
- `analyst_posterior_confidence: float` — analyst's updated belief after
  reviewing the tool's evidence
- `update_rationale: str` — why the belief changed (or didn't)

**What this prevents**

Without this structure, the analyst either ignores the tool output or defers
to it entirely. The belief-update format forces a documented decision: "I saw
this evidence, I had this prior, here is what I now believe and why."

This also creates a learning dataset: over time, which analyst updates were
validated by actual outcomes? Which tool-proposed updates were wrong?

**What Harvey said about AI limitations**

> "Tools are essentially the current best use case of AI — the machine-human
> interface. It is not able to do it on its own without a lot of corrections
> along the way."

The tool should never claim to have updated the thesis. It should surface
evidence and propose an update. The analyst confirms, overrides, or defers.

**Priority**: Medium. The data schema is straightforward. The harder part is
building the habit of recording prior and posterior beliefs. Start with a
simple field in `targets.yaml`: `thesis_prior_confidence: 0.6`. Then the tool
populates evidence and the analyst updates the posterior after each readout.

---

### HARVEY-5 — Investment and arbitrage decision discipline

**Source**: Harvey Advice (05 June 2026).

Harvey explained the correct investment use case for the tool and why options
calls on biotech are not viable:

> "If you do calls in them years out, it's extremely expensive, and that's
> just not a viable approach to invest."

The right use case is **medium-term thesis-driven arbitrage**:

> "Do I think this opportunity is likely to have a 10% swing in the next year
> or two? You have a thesis built off of your model, and once a data readout
> or piece of news comes out that moves the price in the direction that
> suggests you should execute your trade — buy or sell — you can execute that
> trade. You've applied a hypothesis using your model, and once you've seen
> the signal, you've executed on it. If you don't see the signal, your model
> can learn why something didn't happen."

He gave the Amgen GLP-1 example explicitly:

> "When Amgen dropped their data — 19.9% body weight loss vs the industry
> pricing them for 20–21% — their stock fell 30%. To me, knowing the
> properties of the drug and the rest of the Amgen portfolio, it felt like
> an overreaction. It would likely come back at a reasonable time point. That
> was a potential to put in an investment and see upside, because as soon as
> they get a more mature data set, they're probably going to correct to closer
> to the median model."

**What the tool should encode per tracked asset**

- `investment_thesis: str` — what signal would confirm the investment case
- `expected_catalyst: str` — the specific readout or event being waited for
- `expected_price_direction: "up" | "down"` — what the thesis predicts
- `expected_time_window_months: int` — how long to wait for the signal
- `position_entered: bool`
- `signal_observed: bool`
- `outcome: "confirmed" | "refuted" | "no_signal" | "pending"`

**What to NOT do**

- Do not use the tool for daily trading
- Do not hold positions waiting for biology to play out over years
- Do not buy options far out on pre-Phase-2 programs — too expensive relative
  to the uncertainty
- Do not treat a price drop as a buy signal unless you understand *why* the
  market dropped and whether it represents a thesis error or market overreaction

**Priority**: Low for the current engineering phase. The tool is not yet at
the point where investment tracking is the primary workflow. Revisit after the
weekly M&A screen has been validated against historical outcomes and the
science thesis layer (HARVEY-2, HARVEY-3) is in place.

---

### PAIR-SCORER-1 — Pair score distribution compression: full recalibration needed

**Problem**: The acquirer-pair logit scorer saturates near 1.0 for most decent-quality
pairs. With v2.1 intercept (-3.0), the median pair scores ~0.90 instead of 0.99, but
strong pairs still cluster at 0.97–0.99. The top-pair rankings lack meaningful
separation.

**Root cause**: The logit weights were set as evidence-informed priors, not fitted to
historical data. The sum of positive weights (~8.90) is large relative to the intercept.
Any pair with decent features across all dimensions pushes the log-odds well above zero
and the sigmoid saturates.

**What a proper fix requires**:

1. **Labeled historical dataset**: A set of (acquirer, target) pairs with known outcomes
   — closed acquisition, licensing deal, or no transaction. Minimum N~50 positive pairs
   across ≥3 acquirers to fit a logistic regression with any confidence.

2. **Logistic regression refit**: Re-estimate `INTERCEPT` and all `WEIGHTS` from the
   labeled data. Expect the intercept to be far more negative (deals are rare — true base
   rate for any given pair is well under 5%). Expect some weights to shrink or flip.

3. **Calibration check**: After fitting, verify that the score distribution matches the
   empirical positive rate at each decile. A well-calibrated pair scorer should show
   ~5–10% of top-decile pairs converting to deals, not 99%.

4. **Separate ranking from probability**: Consider maintaining two outputs —
   `pair_rank_score` (for ordering) and `pair_acquisition_probability` (calibrated to
   base rates). The current score conflates both.

**Interim mitigations already in place**:
- `_apply_ta_fit_cap`: caps scores at 0.60/0.75 when TA overlap is poor
- `_apply_size_fit_cap`: caps at 0.85 when deal-size fit is poor (added v2.1)
- `INTERCEPT = -3.0`: shifted median pair from ~0.99 to ~0.90 (v2.1)

**Priority**: Medium. The caps prevent the worst outliers, and the scores still rank
pairs correctly in relative terms. Full recalibration requires labeled historical deal
data that does not yet exist at sufficient scale. Revisit after the historical deal
database reaches ≥50 verified pairs.

---

### ARCH-0 — Target architecture: RAG plus structured valuation and scoring

**Wanted architecture**: The biotech M&A product should not be framed as
"training a model" first. The better architecture is a historical-deal
intelligence engine that combines retrieval, comparable-deal search, structured
rNPV valuation, buyer-target fit scoring, and eventually supervised predictive
models once enough labeled outcomes exist.

The target architecture should be built in this order:

1. Historical deal database
2. Drug asset database
3. Clinical trial result extraction
4. Comparable deal search
5. Buyer pipeline-gap analysis
6. rNPV valuation model
7. Strategic fit scoring
8. Predictive acquisition-likelihood model
9. LLM explanation layer

**Data layer**: collect structured historical acquisition and partnership data:

| Field | Meaning |
|---|---|
| buyer | Acquirer or strategic partner. |
| target | Acquired company, licensed asset owner, or partner. |
| date | Announcement and close dates where available. |
| deal value | Total headline value and disclosed transaction value. |
| upfront | Cash/equity paid at signing or close. |
| milestones | Development, regulatory, commercial, and sales milestones. |
| royalty terms | Royalty rate, tiering, term, and geography when disclosed. |
| asset name | Drug, platform, or portfolio acquired/licensed. |
| indication | Lead and optional indications. |
| modality | Small molecule, antibody, cell therapy, gene therapy, RNA, etc. |
| phase | Development stage at deal announcement. |
| trial results | Endpoint, effect size, p-value, safety, durability, and limitations. |
| mechanism of action | Target biology and pathway rationale. |
| market size | Addressable patients, price, penetration, and competition. |
| patent life | Remaining exclusivity and IP runway. |
| competitive landscape | Current/future standard of care and direct competitors. |
| probability of approval | Pre-deal POS estimate and later observed outcome. |
| revenue estimates | Peak sales, ramp, erosion, and scenario assumptions. |
| strategic rationale | Publicly stated deal thesis and inferred buyer need. |
| buyer pipeline gap | TA, modality, LOE, revenue-cliff, or franchise gap filled. |
| stock/cash position | Buyer financing capacity and currency quality at announcement. |
| outcome after deal | Approval, failure, delay, write-down, discontinuation, or commercial result. |

**Retrieval and comparable-deal layer**: use RAG over deal documents, press
releases, investor decks, 10-Ks/10-Qs, trial readouts, abstracts, and conference
materials. The system should answer questions like:

```text
Which historical acquisitions or partnerships look most similar to this asset?
```

Similarity should support multiple dimensions:

- modality,
- indication,
- phase,
- endpoint/result quality,
- buyer pipeline gap,
- valuation multiple,
- rights structure,
- deal structure,
- strategic rationale,
- post-deal outcome.

Example:

```text
A Phase 2 rare-disease gene therapy should be compared against:
  similar modality deals,
  same or adjacent indication deals,
  similar stage-of-development acquisitions,
  similar buyer pipeline-gap situations,
  similar valuation multiples,
  similar post-deal outcome patterns.
```

**What learning means**: the system should learn from historical examples, but
the first step is not LLM fine-tuning. Start with structured data, retrieval,
similarity search, and transparent scoring. Later, once labeled outcomes are
large enough and point-in-time safe, train supervised models to learn:

- what makes a drug asset attractive,
- what deal values similar assets received,
- which buyers tend to acquire which assets,
- how approval probability changes with phase, modality, endpoint, and evidence
  quality,
- what strategic gaps drive M&A,
- how much premium buyers pay for de-risked clinical data,
- which assets are poor strategic fits,
- which announced deals later succeeded, failed, or were written down.

**Modeling stack**:

| Layer | Role |
|---|---|
| RAG | Gives the system a searchable filing cabinet with citations. |
| Structured scoring | Converts facts into POS, rNPV, Layer 0-5 M&A scores, and confidence. |
| Comparable-deal engine | Finds historical acquisitions/partnerships with similar facts. |
| Supervised ML | Learns outcome patterns once enough labeled, no-lookahead examples exist. |
| Fine-tuning | Optional later step for house style and extraction/output consistency. |
| LLM explanation | Explains the evidence, comparables, score drivers, and caveats. |

The LLM should not be the valuation model. It should explain and retrieve:

```text
This asset is attractive to Buyer X because it fills a pipeline gap, has Phase 2
efficacy, targets a high-value indication, and resembles three prior acquisitions
with $1B-$3B deal values.
```

**Preferred wording**:

```text
Build a biotech M&A intelligence engine that combines historical deal retrieval,
asset comparables, rNPV valuation, buyer-target fit scoring, and eventually
predictive models trained on past acquisition outcomes.
```

**Priority**: High. This is the long-term product architecture that connects the
current valuation engine, M&A layers, live scanner, calibration dataset, and
future RAG/extraction work into one coherent system.

---

### LIVE-1 — Make live scanner rescoring fully automatic and explainable

**Current state**: The watchlist pipeline can fetch documents from configured
connectors, extract structured signals, apply confidence gates, map eligible
signals into valuation changes, persist valuation diffs, refresh market prices,
and rerank assets from stored valuation diffs and structured signals.

That means the live scanner can rerank after new evidence **when** the evidence
is successfully fetched, extracted, mapped, and allowed through the valuation
gate. It is not yet a fully autonomous news intelligence system. Some documents
are skipped by confidence gates, some mappings are routed to manual review, and
many unstructured biotech-news headlines still need better interpretation before
they can safely change POS, rNPV, M&A probability, or BD priority.

**The gap**: the live scanner path needs a stronger end-to-end contract:

```text
new source document
  -> extracted event and facts
  -> materiality judgment
  -> proposed model changes
  -> auto/apply or human-review route
  -> valuation and M&A rescore
  -> ranked output with "why score changed"
```

Today, parts of that chain exist, but the handoff is not yet institutional-grade
for live news. The system needs clearer coverage of which event types can update
which model fields, stronger free-text extraction, better source conflict
resolution, and explicit score-change attribution.

**The fix**:

1. **Build a live-news event coverage matrix**
   - For each event type, define whether it can affect POS, revenue, cost,
     market expectations, M&A target attractiveness, BD priority, acquirer fit,
     or close probability.
   - Example: positive Phase 2 readout can affect POS and rNPV; strategic
     partnership can affect M&A seller willingness and acquirer relationship;
     CRL can affect POS, timing, cost, and M&A ranking.

2. **Add a score-change attribution object**
   - Store before/after scores for valuation rank, M&A probability, BD route,
     POS, rNPV, and confidence.
   - Store the source document, extracted fact, mapped field, and exact
     contribution to the score movement.
   - Output a readable explanation: "Rank increased because Phase 2 readout
     raised prior-phase data strength and rNPV increased by $X."

3. **Separate auto-apply from review-required mappings**
   - Low-risk factual updates can auto-apply.
   - Judgment-sensitive updates, especially endpoint quality, clinical effect
     magnitude, MCID interpretation, safety severity, and M&A strategic
     implications, should route to review before changing the live score.

4. **Improve free-text biotech-news parsing**
   - Use source-specific prompts for press releases, SEC 8-Ks, FDA pages,
     conference abstracts, and news articles.
   - Extract p-values, effect sizes, endpoint names, safety rates, regulatory
     action type, partnership terms, rights geography, and milestone structure.
   - Attach source excerpts so analysts can audit every proposed score change.

5. **Rerun both relevant paths**
   - Rerun the fast live scanner ranking after any approved valuation or M&A
     signal change.
   - Rerun the institutional BD layers when the event changes eligibility,
     target attractiveness, BD urgency, pair feasibility, deal structure, or
     calibrated M&A probability.

6. **Add score-change tests and replay validation**
   - Use historical documents to assert that known positive/negative events move
     the correct model fields in the correct direction.
   - Replay documents point-in-time and compare the generated score-change
     attribution to expected outcomes.

**Priority**: High. This is the clearest path from "good scoring framework" to
"useful live BD/M&A monitoring product."

**Estimated scope**:
- New module: `src/bve/intelligence/live_score_attribution.py`
- New module: `src/bve/intelligence/live_event_impact_matrix.py`
- Expand `MappingEngine` coverage for M&A-specific event impacts
- Extend `KnowledgeStore` with score-change attribution records
- Add `bve-live-explain` or weekly report section showing why ranks changed
- Add replay fixtures for positive readout, failed readout, FDA hold, CRL,
  partnership, takeover rumor, financing stress, and asset discontinuation

---

### LIVE-2 — Convert written reports and news articles into structured scoring inputs

**Current state**: Many M&A and POS layer inputs are structured fields that must
already be present on the target, asset, or acquirer object. For example, Layer
0E can score integration complexity when it receives fields such as
`manufacturing_complexity`, `product_count`, `geographic_complexity`, and
`payer_access_complexity`, but it does not itself read a free-text manufacturing
report and infer those fields. Layer 3D can score buyer integration capability
when it receives an `AcquirerIntegrationProfile`, but it does not infer that
profile directly from news or analyst reports.

**The gap**: the tool should be able to ingest written diligence reports, company
manufacturing summaries, SEC filings, press releases, news articles, and analyst
notes, then convert the text into auditable structured sub-score inputs across
the relevant layers.

Examples:

```text
Report says:
  "The company relies on a single viral-vector CDMO, has limited redundancy,
   and tech transfer would be difficult."

Draft structured fields:
  manufacturing_complexity = "high"
  has_manufacturing_dependency = true
  supply_redundancy = low
  systems_compliance_transfer_risk = elevated
  affected layers = 0D, 0E, 3B, 3D
```

```text
News article says:
  "The asset is licensed ex-US to a partner with a right of first refusal."

Draft structured fields:
  asset_rights_scope = "regional_split"
  has_existing_partnership = true
  has_right_of_first_refusal = true
  affected layers = 0B, 0D, 3B
```

**The fix**:

1. **Create a report/news-to-score extraction layer**
   - Accept uploaded reports, pasted text, URLs, SEC filings, press releases,
     and stored news articles.
   - Extract structured facts with source excerpts, confidence, and field-level
     provenance.
   - Support both target-level and buyer-specific inputs.

2. **Add layer-specific extraction schemas**
   - **POS**: endpoint, effect size, p-value, safety, prior-phase data,
     data maturity, biomarker selection, regulatory pathway.
   - **0B**: deal route signals, rights geography, licensing/option/co-dev
     structure, platform versus product rationale.
   - **0D**: rights control, royalty/milestone burden, partner encumbrances,
     IP ownership/FTO, manufacturing readiness, diligence readiness.
   - **0E**: product count, indication count, salesforce burden,
     manufacturing transfer complexity, geography, payer/access/channel
     complexity, systems/compliance transfer risk.
   - **0F**: cash runway, financing pressure, valuation distress, salvageability
     signals.
   - **Layer 1 / 2 / 3**: strategic scarcity, BD urgency, buyer fit,
     affordability inputs, integration capability, antitrust/process risk.

3. **Generate `ScoreInputDraft` objects, not silent score changes**
   - Proposed field name and value.
   - Current field value.
   - Source excerpt and URL/file reference.
   - Confidence score.
   - Affected layer(s).
   - Estimated score impact.
   - Human review status.

4. **Human-review gate for judgment-sensitive fields**
   - Auto-apply only low-risk factual fields, such as product count or disclosed
     cash balance, when source confidence is high.
   - Route subjective fields, such as endpoint meaningfulness, manufacturing
     severity, asset salvageability, and strategic scarcity, to review before
     changing live scores.

5. **Write approved values back to the structured target/asset/acquirer record**
   - Update YAML/config or the knowledge store.
   - Preserve provenance so every raw score can be traced back to a report,
     article, filing, or analyst note.
   - Rerun affected POS, M&A, Layer 0, Layer 3, and ranking outputs.

**Priority**: High. This is required if the tool is meant to move from manual
score entry to an evidence-driven BD/M&A intelligence system. It also prevents
analysts from needing to manually translate every written report into YAML
fields.

**Estimated scope**:
- New module: `src/bve/intelligence/score_input_extractor.py`
- New schema: `ScoreInputDraft`
- New mapping registry: report/news fact type → layer field
- Extend `KnowledgeStore` with score-input draft and provenance tables
- Add review workflow for approving/rejecting extracted scoring inputs
- Add fixtures for manufacturing report, rights/partnership article, financing
  distress article, clinical readout press release, and acquirer capability
  profile article

---

### MODEL-1 — Move from coarse buckets to evidence-derived continuous 0-1 inputs

**Current state**: Some inputs are already continuous 0-1 sub-scores, especially
in Layer 0D, Layer 0F, and buyer-specific Layer 3 capability models. Other
inputs are still coarse discrete buckets such as `low` / `medium` / `high`,
`local` / `regional` / `global`, or simple booleans.

Examples:

| Current coarse input | Limitation |
|---|---|
| `manufacturing_complexity = high` | Treats all high-complexity manufacturing the same, even though a single-CDMO viral-vector process is not the same as a moderately complex biologic. |
| `payer_access_complexity = high` | Does not distinguish mild prior-auth burden from severe reimbursement uncertainty. |
| `geographic_complexity = global` | Does not distinguish US+EU launch from US+EU+Japan+China+ROW launch. |
| `salesforce_required = true` | Does not distinguish a small specialty KOL field team from a large primary-care salesforce. |

**The gap**: the tool should eventually decipher available evidence and produce
continuous 0-1 scores for as many scoring inputs as possible. Coarse buckets are
useful for early manual entry, but they lose information and can make the model
less accurate.

**Target end state**:

```text
Written evidence / structured facts
  -> interpreted severity and confidence
  -> continuous 0-1 sub-score
  -> layer score with provenance
```

Example:

```text
Report:
  "The product uses a single specialized viral-vector CDMO, no backup supplier,
   and commercial-scale comparability is not yet demonstrated."

Current coarse mapping:
  manufacturing_complexity = "high"

Better continuous mapping:
  process_transferability = 0.25
  supply_redundancy = 0.15
  gmp_quality_readiness = 0.60
  scale_capacity = 0.35
  manufacturing_complexity_continuous = 0.88
  confidence = 0.75
```

**The fix**:

1. **Keep coarse fields as fallback**
   - Preserve `low` / `medium` / `high` fields for quick manual entry and
     backward compatibility.
   - When continuous fields are absent, map buckets to default scores as today.

2. **Add continuous override fields**
   - Add optional 0-1 versions for coarse dimensions where needed.
   - Examples:
     - `manufacturing_complexity_score`
     - `payer_access_complexity_score`
     - `geographic_complexity_score`
     - `salesforce_burden_score`
     - `channel_complexity_score`
     - `regulatory_pathway_risk_score`

3. **Use evidence-derived scoring where reports are available**
   - Let the report/news extraction layer propose continuous scores, not only
     bucket labels.
   - Store the source excerpt and confidence behind each proposed score.
   - Require review for judgment-heavy continuous scores.

4. **Prefer continuous scores in model computation**
   - Scoring functions should use continuous override fields when provided.
   - Fall back to bucket-to-score maps only when the continuous score is missing.

5. **Calibrate continuous score ranges**
   - Use historical cases and expert-reviewed examples to anchor what 0.20,
     0.50, 0.80, etc. mean for each dimension.
   - Avoid false precision by attaching confidence and data-quality labels.

**Priority**: Medium-high. This improves accuracy and nuance across POS, Layer
0, M&A target scoring, and buyer-specific Layer 3 scoring. It should be built
after or alongside `LIVE-2`, because the greatest value comes when written
evidence can generate continuous scores automatically.

**Estimated scope**:
- Add continuous override fields to key Layer 0E and Layer 3D inputs
- Audit all bucket-to-score maps and expose their fallback values
- Update scoring functions to prefer continuous overrides
- Extend `ScoreInputDraft` to support continuous score proposals
- Add calibration fixtures for manufacturing, payer access, geography,
  salesforce burden, regulatory complexity, and integration capability

---

### MNA-1 — Build specialist scoring models for routed non-core company types

**Current state**: Layer 0 and the exclusion/routing engine can identify company
types that do not belong in the standard therapeutics acquisition model. It can
route royalty/passive IP companies, services-only companies, diagnostics/tools
companies, licensing-only cases, distress cases, platform cases, and commercial
franchise cases away from the default path.

The core implemented deal-type model routes are:

| Route | Status |
|---|---|
| `lead_asset_rnpv_model` | Implemented core route |
| `portfolio_mna_model` | Implemented core route |
| `platform_fit_model` | Implemented core route |
| `commercial_synergy_model` | Implemented core route |
| `licensing_model` | Implemented core route |
| `distress_adjusted_model` | Implemented core route |

But some routes currently exist mostly as **classification / exclusion
destinations**, not as full specialist scoring models:

| Routed company type | Current gap |
|---|---|
| Royalty/passive IP company | `royalty_model` route exists, but there is no full royalty-acquisition scoring framework. |
| Tools company | Routed away from therapeutics M&A, but no tools-specific M&A score. |
| Diagnostics company | Routed away from therapeutics M&A, but no diagnostics-specific M&A score. |
| CRO/CDMO/services company | Routed to services M&A model, but no full services-M&A score. |

**Should this be fixed?** Yes, if the tool is intended to screen the broader
life-sciences universe. No, if the tool remains intentionally focused on
therapeutics assets and biotech company acquisitions. The current behavior is
acceptable for a therapeutics-first scanner because it prevents wrong-model
scoring. It becomes a product gap once these routed categories are expected to
receive ranked outputs.

**The fix**: create specialist models that match the economics and deal logic of
each routed category.

1. **Royalty/passive IP model**
   - Inputs: royalty stream durability, payer/product concentration, patent
     runway, counterparty quality, tiered royalty economics, litigation/IP risk,
     discount rate, and transaction comparables.
   - Output: royalty stream value, acquisition attractiveness, concentration
     risk, and buyer universe.

2. **Diagnostics model**
   - Inputs: test volume, reimbursement/CPT status, clinical utility evidence,
     guideline adoption, lab/channel fit, gross margin, regulatory status, and
     pharma companion-diagnostic relevance.
   - Output: diagnostics M&A score and likely buyer class.

3. **Tools / reagents model**
   - Inputs: recurring revenue, installed base, consumables pull-through,
     customer concentration, margin profile, R&D/manufacturing quality, and
     strategic fit with tools acquirers.
   - Output: tools M&A score and valuation multiple framework.

4. **Services / CRO / CDMO model**
   - Inputs: backlog, capacity utilization, customer concentration, GMP record,
     modality specialization, EBITDA margin, capex needs, and sponsor quality.
   - Output: services M&A score, integration complexity, and buyer universe.

**Priority**: Medium. This is not required for the core therapeutics M&A model,
but it is important if the scanner is meant to cover all life-sciences companies
rather than route non-therapeutics names out of scope.

**Estimated scope**:
- New module: `src/bve/intelligence/ma_royalty_model.py`
- New module: `src/bve/intelligence/ma_diagnostics_model.py`
- New module: `src/bve/intelligence/ma_tools_model.py`
- New module: `src/bve/intelligence/ma_services_model.py`
- ~~Extend Layer 0 routing output to call the appropriate specialist model when
  requested instead of stopping at `ROUTE_TO_OTHER_MODEL`~~ — **DONE** (2026-06-04):
  `ROUTE_TO_OTHER_MODEL` has been removed from Layer 0A. Gate 10 no longer routes
  deal types to specialist models. Model routing is now owned by Layer 0B
  (`DealStructureRoute`). See `ARCH-1` below.
- Add sample fixtures for one royalty company, one diagnostics company, one
  tools company, and one CDMO/CRO-style company

---

### MNA-2 — Improve company value estimate for Layer 0C and M&A sizing

**Current state**: Layer 0C consumes `enterprise_value_millions` and
`market_cap_millions` when those fields are already populated. It prefers EV
when supplied, falls back to market cap, and otherwise marks the size bucket as
unknown. Layer 0C itself does not deeply calculate enterprise value or
multi-asset company value.

**The gap**: market cap alone is not the best estimate of what a buyer is paying
for the company. For M&A sizing, enterprise value is more accurate:

```text
enterprise_value =
    market_cap
  + debt
  + preferred_stock
  + minority_interest
  - cash_and_equivalents
```

For multi-asset companies, the best internal valuation is a sum-of-the-parts
view:

```text
model_sotp_value =
    rNPV(lead_asset)
  + rNPV(other_pipeline_assets)
  + commercial_franchise_value
  + platform_value
  + net_cash
  - debt
```

Layer 0C should distinguish:

- **market-implied company value**: calculated from public market and balance
  sheet data,
- **model-implied company value**: internal SOTP/rNPV value from the tool,
- **expected acquisition cost**: EV or SOTP reference value plus expected
  takeover premium.

**The fix**:

1. **Create a company value resolver**
   - Pull latest market cap from stored market-price snapshots or yfinance.
   - Pull latest cash, debt, preferred stock, and minority interest from SEC
     filings when available.
   - Calculate public-market EV.
   - Track source date and source quality for each component.

2. **Add a value-source hierarchy for Layer 0C**
   - calculated EV from market data + SEC balance sheet,
   - manually supplied EV from config/database,
   - market cap fallback,
   - unknown/data gap.

3. **Add multi-asset SOTP support**
   - Combine modeled rNPVs for all configured assets under the same company.
   - Add optional platform and commercial-franchise value fields.
   - Add net cash and debt adjustments.
   - Compare `market_ev` versus `model_sotp_value`.

4. **Expose all values in Layer 0C output**
   - `market_cap_millions`
   - `cash_millions`
   - `debt_millions`
   - `calculated_enterprise_value_millions`
   - `model_sotp_value_millions`
   - `reference_value_used_millions`
   - `reference_value_source`
   - `expected_acquisition_cost_millions`
   - `data_freshness`
   - `data_gaps`

5. **Use the improved value downstream**
   - Layer 0C uses the best available reference value for size bucket.
   - Layer 3A uses expected acquisition cost for buyer affordability.
   - Layer 1 value-creation logic can compare market EV to model SOTP value.
   - M&A memo output shows whether the target is cheap, expensive, or
     strategically underpriced.

**Priority**: High for M&A accuracy. Market cap fallback is acceptable for a
rough screen, but EV and SOTP are needed for credible acquisition sizing and
multi-asset target analysis.

**Estimated scope**:
- New module: `src/bve/intelligence/company_value_resolver.py`
- Extend `TargetSizeInput` / `TargetSizeResult`
- Integrate stored `market_prices` and SEC balance-sheet facts
- Add SOTP adapter from configured company assets
- Add tests for EV calculation, market-cap fallback, stale data, negative EV,
  and multi-asset SOTP

---

### MNA-2B — Make BD/M&A scoring multiplicative and gate weak deal dimensions

**Current state**: The full BD/M&A framework is directionally correct. It does
not treat "good science" alone as enough for acquisition. The architecture
separates target quality, seller willingness, buyer fit, pair realism,
affordability, and deal feasibility across the M&A layers.

The live weekly M&A screen is only partially aligned with that framework. It is
currently closer to:

```text
ma_score =
    target strength
  + best buyer-pair fit
  + seller willingness
  + catalyst timing
  + financing/risk pressure
```

That is useful for ranking diligence priorities, but it is not yet the right
shape for acquisition probability.

The better conceptual model is:

```text
acquisition likelihood =
  buyer need
× buyer financial capacity
× target attractiveness
× valuation gap
× regulatory/antitrust feasibility
× execution risk
× board/shareholder willingness
```

**Current factor coverage**:

| Factor | Current tool status |
|---|---|
| Buyer need | Yes, via TA overlap, pipeline gap, acquirer urgency, and modality fit. |
| Buyer financial capacity | Partial, via deal-size fit and affordability logic, but market cap, EV, and debt need better wiring. |
| Target attractiveness | Yes, via asset quality, clinical stage, catalysts, evidence, and POS/science signals. |
| Valuation gap | Partial. Valuation and implied-expectation modules exist, but valuation gap is not central enough in the live M&A score. |
| Regulatory / antitrust feasibility | Partial. Layer 3/4 design has a place for this, but it needs stronger enforcement in scoring. |
| Execution risk | Partial, via integration capacity, rights/control, and pair realism concepts. |
| Board / shareholder willingness | Partial, proxied through cash runway, distress, strategic review, restructuring, and seller willingness. |

**The gap**: The framework understands the right BD logic, but several weak
dimensions are still additive, thinly modeled, or underwired. A target with
excellent science should not score highly when buyer need is weak, affordability
is poor, antitrust risk is high, valuation mismatch is large, execution risk is
unacceptable, or the seller is not transaction-ready.

This is what "directionally right, but not fully mature" means:

- **Conceptually right**: the framework has places for buyer gaps,
  affordability, seller willingness, antitrust, execution risk, deal structure,
  and calibration.
- **Implementation still immature**: some of those fields are rules-based,
  missing data, not wired into the main score path, or treated as soft
  adjustments instead of hard constraints.
- **Needed behavior**: weak dimensions should act as real caps/gates, so a high
  science score cannot overwhelm deal-breaking M&A problems.

**The fix**:

1. **Convert key M&A dimensions from additive boosts to gated components**
   - Buyer need, affordability, antitrust feasibility, execution risk, valuation
     gap, and seller willingness should each be able to cap the final score.
   - Example: no buyer need or high antitrust risk should prevent a high final
     score even if the asset quality score is strong.

2. **Add explicit score caps for weak dimensions**
   - Low buyer need: cap to strategic radar / monitoring range.
   - Low affordability or impossible deal size: cap to low transaction
     probability.
   - High antitrust risk: cap or fail the pair.
   - High execution/integration risk: reduce likely route from acquisition to
     license/collaboration or cap the pair score.
   - Low seller willingness: route to relationship-building/watchlist rather
     than actionable M&A.

3. **Make valuation gap first-class**
   - Compare market EV, model SOTP/rNPV, and expected acquisition cost.
   - Penalize cases where the buyer would need to pay far above risk-adjusted
     value without a clear strategic premium rationale.
   - Support deal-structure alternatives, such as CVR/license/option, when the
     valuation gap is high but strategic interest is real.

4. **Expose the gating explanation in reports**
   - Show which dimension capped the score.
   - Distinguish "great science, weak deal setup" from "credible acquisition
     candidate."
   - Keep `ma_score` labeled as an uncalibrated ranked diligence score until
     Layer 5 historical calibration is complete.

**Priority**: High. This is central to making the BD/M&A layer behave like a
real acquisition screen rather than a science-quality screen with M&A overlays.

**Estimated scope**:
- Extend Layer 3 gate outputs with explicit cap reasons per dimension.
- Add valuation-gap inputs from the company value resolver in `MNA-2`.
- Strengthen pair-level affordability, antitrust, and execution-risk caps.
- Add report fields for `score_cap_applied`, `cap_reason`, and
  `blocked_by_dimension`.
- Add tests proving strong science cannot overcome weak buyer need,
  unaffordable price, high antitrust risk, or low seller willingness.

---

### MNA-2C — Add a simple Macro Deal Environment layer after POS

**Core idea**: Macro should be a deal-weather layer, not a second science model.
It should sit after POS/rNPV and before BD/M&A scoring.

```text
POS / science
-> rNPV / valuation
-> Macro Deal Environment
-> BD/M&A Layer 0-5
-> report
```

It should not be a huge macro prediction engine. It should be a small
"deal weather" layer that tells the M&A system how strict or flexible to be.

**1. Core Object**

```python
MacroDealEnvironment:
    as_of_date
    regime_version
    capital_markets
    biotech_financing_window
    patent_cliff_pipeline_pressure
    regulatory_pricing_policy
    antitrust_posture
    geopolitical_supply_chain_risk
    therapeutic_area_sentiment
    confidence
    sources
```

Each regime flag should be simple:

```text
tailwind / neutral / headwind
```

or:

```text
low / medium / high
```

No fake decimal precision at first.

**2. Regime Flags**

| Flag | Meaning | Main effect |
|---|---|---|
| `capital_markets` | Rates, discount rates, investor risk appetite | Changes valuation discipline and stage preference |
| `biotech_financing_window` | Can small biotechs raise money? | Changes seller willingness and financing risk |
| `patent_cliff_pipeline_pressure` | Are big buyers under pressure to replace revenue or fill pipeline gaps? | Changes buyer urgency |
| `regulatory_pricing_policy` | FDA/pricing/IRA/payer pressure | Changes commercial risk and deal structure |
| `antitrust_posture` | FTC/regulator strictness | Tightens/loosens pair-level antitrust caps |
| `geopolitical_supply_chain_risk` | China, tariffs, CDMO/CRO exposure | Changes execution-risk caps |
| `therapeutic_area_sentiment` | Is the TA hot or cold? | Changes buyer appetite and premium tolerance |

**Open design note — keep this layer clean**

The exact final shape of this layer is still unsettled. The safest design is to
start simple and avoid creating overlapping macro inputs that pretend to be more
precise than they are. The current best simplification is:

```text
V1 Macro Layer Inputs:

- Capital markets regime
- Biotech financing window
- Patent-cliff / pipeline pressure
- Regulatory / pricing climate
- Antitrust posture
- Geopolitical / supply-chain risk
- Therapeutic-area sentiment
```

Possible cleanup rules:

- **Merge interest-rate / discount-rate environment into
  `capital_markets_regime`**. Rates are one reason capital markets are easy or
  hard; they do not need to be a separate flag at first.
- **Merge accelerated approval climate into FDA / regulatory policy climate**,
  unless the asset specifically depends on accelerated approval.
- **Merge IPO / follow-on financing activity into
  `biotech_financing_window`**. IPOs and follow-ons are evidence for whether
  the financing window is open or closed.
- **Merge sector risk appetite into `capital_markets_regime` or
  `biotech_financing_window`**. As a standalone input it is probably too vague.
- **Treat deal-structure market preference as an output, not an input**. Macro
  conditions should produce deal-structure bias; the model should not require a
  separate manually-entered "deal preference" flag unless needed later.
- **Keep supply-chain/manufacturing as mostly asset-specific execution risk**.
  The macro layer should only say whether the external environment makes those
  risks more or less painful.
- **Keep buyer stock price, buyer cash, buyer debt, and balance-sheet capacity
  outside the macro layer**. Those belong in the buyer-specific BD/M&A layer.
  Macro can change how strict that buyer-capacity layer is, but should not own
  buyer-specific financial facts.

The practical principle:

```text
Macro = broad environment.
Buyer layer = this specific acquirer's capacity and urgency.
Target layer = this specific company's asset quality, financing pressure, and dealability.
Pair layer = whether this buyer can realistically buy this target.
```

**3. Source Model**

Every flag needs provenance:

```python
MacroRegimeFlag:
    name
    value
    source_type: automated | manual | mixed
    source
    last_updated
    confidence
    rationale
```

Example:

```text
antitrust_posture:
  value: aggressive
  source_type: manual
  source: analyst quarterly macro review
  last_updated: 2026-06-01
  confidence: medium
  rationale: FTC scrutiny remains elevated for horizontal/pipeline overlap deals.
```

That prevents "vibes scoring."

**4. What Gets Automated**

Only automate the easy, objective pieces first.

| Flag | Automation |
|---|---|
| Patent cliff / pipeline pressure | Acquirer profiles, LOE dates, revenue cliffs, pipeline gaps |
| Biotech financing window | XBI trend, biotech IPO count, follow-on count/volume |
| Therapeutic area sentiment | Recent deal activity, TA-specific price performance, recent clinical wins/failures |
| Capital markets | Fed funds / 10Y yield / biotech index trend, or manual initially |
| Antitrust posture | Manual quarterly |
| Geopolitical risk | Manual quarterly |
| Pricing policy | Manual quarterly plus asset-specific IRA/payer exposure |

**5. What It Affects**

The macro layer should mostly affect **M&A and deal structure**, not POS.

```text
Should affect POS:
- FDA endpoint acceptance
- accelerated approval path
- confirmatory trial burden
- class-wide regulatory safety concerns

Should not affect POS:
- interest rates
- IPO window
- buyer cash/debt
- China tariffs
- antitrust
- patent cliffs
```

Most macro factors do this instead:

```text
seller_willingness
buyer_urgency
valuation_gap
deal_structure_bias
pair_score_caps
affordability strictness, by modifying how the buyer-specific BD layer interprets cash/debt
execution-risk strictness
```

**6. Modifier Logic**

Do not make a separate macro score. Use macro to adjust existing gates.

Example:

```text
antitrust_posture = aggressive
-> tighten existing pair antitrust caps

geopolitical_supply_chain_risk = high
-> tighten execution-risk caps for China/CDMO-dependent assets

biotech_financing_window = closed
-> increase seller willingness for companies with <18 months runway

capital_markets = headwind
-> penalize expensive early-stage/platform acquisitions
-> favor late-stage, de-risked, milestone-heavy structures

patent_cliff_pipeline_pressure = high
-> increase buyer urgency for buyers with near-term LOE gaps
```

**7. Cap Example**

For antitrust:

```text
normal posture:
  same-indication high-overlap pair cap = 0.60

aggressive posture:
  same-indication high-overlap pair cap = 0.50

permissive posture:
  same-indication high-overlap pair cap = 0.70
```

One antitrust model. Macro just changes strictness.

For financing:

```text
biotech_financing_window = closed
and target cash runway < 12 months
-> seller_willingness + boost
-> financing_risk + boost
-> full acquisition or strategic alternative more plausible
```

For rates:

```text
capital_markets = headwind
and target is preclinical/platform-heavy
-> acquisition score cap
-> route bias toward license/option/collaboration
```

**8. Deal Structure Bias**

This is where macro becomes very useful.

Output should include:

```text
preferred_structure_bias:
  full_acquisition: lower
  license: higher
  option_to_acquire: higher
  CVR: higher
  minority_equity: neutral
```

Example:

```text
High-rate / weak-financing / high-uncertainty environment:
  - lower full-acquisition probability for speculative platforms
  - higher licensing/option/CVR probability
  - higher distressed takeout probability for de-risked assets with weak runway
```

**9. Report Output**

The report should show a small section:

```text
Macro Deal Environment

Overall read:
Risk-off biotech M&A environment. Buyers have pipeline need, but capital markets
favor disciplined, de-risked, milestone-heavy deals.

Regime flags:
- Capital markets: headwind
- Biotech financing window: closed
- Patent cliff / pipeline pressure: tailwind
- Regulatory/pricing policy: headwind
- Antitrust posture: aggressive
- Geopolitical/supply-chain risk: medium
- TA sentiment: oncology hot, gene therapy cold

Effect on this target:
- Seller willingness increased due to weak financing window and 11-month runway.
- Full takeout score capped because buyer-target overlap creates antitrust risk.
- Deal structure biased toward license/CVR rather than clean acquisition.
```

**10. Data Stored Per Target**

For each target-acquirer pair:

```python
MacroAdjustedPairResult:
    base_pair_score
    macro_adjusted_pair_score
    macro_caps_applied
    cap_reason
    affected_dimensions
    deal_structure_bias
    macro_explanation
```

Example:

```text
base_pair_score: 0.78
macro_adjusted_pair_score: 0.61
macro_caps_applied:
  - antitrust_aggressive_posture_same_indication_cap
  - high_rate_platform_deal_cap
deal_structure_bias:
  full_acquisition: down
  option_to_acquire: up
  license: up
```

**11. Simple First Version**

Make V1 intentionally modest:

```text
V1 Macro Layer:
1. Capital markets regime
2. Biotech financing window
3. Patent cliff / pipeline pressure
4. Antitrust posture
5. Regulatory/pricing pressure
6. Geopolitical/supply-chain risk
7. TA sentiment
```

Each flag should only do one or two things.

No giant formula. No 40 subfactors. No pretending it knows everything.

**12. Final Shape**

The final framework would look like:

```text
Asset Science:
  Does the drug work?

POS:
  How likely is approval?

rNPV:
  What is it worth standalone?

Macro Environment:
  Is the market favorable for deals, financing, and risk-taking?

BD/M&A:
  Who needs it, who can buy it, who can close it, and what structure makes sense?

Output:
  ranked diligence queue
  likely buyers
  deal blockers
  preferred deal route
  confidence / data gaps
```

This gives the product a clean principle:

```text
POS = drug truth
Macro = deal weather
BD/M&A = buyer-seller fit
```

That keeps the tool powerful without turning it into a noisy black box.

**Priority**: Medium-high. Add after the core M&A gates/caps in `MNA-2B` are
stable. The layer should initially be mostly explanatory and cap-modifying, not
a standalone acquisition-probability model.

**Estimated scope**:
- New module: `src/bve/intelligence/macro_deal_environment.py`
- Add `MacroDealEnvironment` and `MacroRegimeFlag` models.
- Add manual config support for quarterly macro flags.
- Add optional automated inputs for buyer firepower, biotech financing window,
  and therapeutic-area sentiment.
- Wire macro modifiers into existing pair caps and deal-structure routing.
- Add report section showing macro regime, provenance, target-specific effect,
  and deal-structure bias.
- Add tests proving macro flags modify existing gates rather than creating
  duplicate parallel scores.

---

### MNA-3 — Add route-adjusted transaction size to Layer 0C

**Current state**: Layer 0C estimates the size of the whole target company using
EV or market cap. That is useful for full-company takeout screening, but it can
overstate the size of non-acquisition routes selected by Layer 0B.

Example:

```text
Company EV = $30B
Layer 0C whole-company bucket = MEGA_DEAL
Layer 0B route = REGIONAL_LICENSE
Actual likely regional-license transaction size = maybe $500M-$2B
```

The current Layer 0C answer is not wrong; it answers "how big is the whole
company?" The missing piece is "how big is the likely transaction route?"

**The fix**: Layer 0C should output two informational size views:

1. **Whole-company size**
   - Based on EV, market cap, or SOTP.
   - Used to understand the target company's total scale.

2. **Route-adjusted expected transaction size**
   - Based on the Layer 0B deal route.
   - Examples:
     - `FULL_COMPANY_TAKEOUT` uses whole-company EV/SOTP plus premium.
     - `REGIONAL_LICENSE` uses geography-adjusted rights value.
     - `GLOBAL_LICENSE` uses asset/license economics rather than full-company EV.
     - `OPTION_TO_LICENSE_OR_ACQUIRE` uses upfront/option fee plus expected
       milestone exposure.
     - `CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION` uses development-cost share,
       profit share, and milestone economics.
     - `MINORITY_EQUITY_PLUS_COLLABORATION` uses expected equity check plus
       collaboration funding.

**Boundary with Layer 3A**: Layer 0C should still apply **no affordability
penalty**. It only reports size context. Layer 3A remains responsible for
answering whether a specific buyer can afford the route-adjusted transaction.

```text
Layer 0C:
  whole_company_size = $30B
  route_adjusted_transaction_size = $800M regional license
  no penalty

Layer 3A:
  buyer-specific affordability check against $800M
```

**Priority**: High once Layer 0B has detailed deal-structure routes. Without
this, a company can look like a mega-deal even when the realistic route is a
much smaller license, option, co-dev, or minority-equity transaction.

**Estimated scope**:
- Extend `TargetSizeResult` with route-adjusted size fields.
- Add a `DealStructureRoute` input to the target-size resolver.
- Add default route-size heuristics for license, option, co-dev, regional, and
  minority-equity routes.
- Ensure Layer 3A consumes route-adjusted transaction size when available.
- Add tests showing full-company EV and route-adjusted size can differ without
  double-counting affordability.

---

### MNA-4 — Narrow Layer 3F to internal strategic fit / conflict

**Current state**: Layer 3F is named strategic conflict and still risks being
interpreted as a broad cannibalization penalty. That is too crude. A better or
cheaper next-generation asset in the same market is often exactly the kind of
asset an incumbent buyer may want to acquire defensively.

**The gap**: several concerns that can be confused with strategic conflict are
already owned elsewhere:

| Concern | Owning layer |
|---|---|
| Drug may fail | POS / Layer 1A asset quality |
| Regulators may block the deal | Layer 3E antitrust |
| Buyer cannot afford the deal | Layer 3A affordability |
| Buyer cannot integrate or operate it | Layer 3D integration capability |
| Buyer has strategic pull / wants the asset | Layer 2A / 2C |

Layer 3F should only cover internal buyer-business conflicts that remain after
those layers have done their work.

**The fix**:

1. Rename Layer 3F from `Strategic Conflict` to
   `Internal Strategic Fit / Conflict`.

2. Remove standalone `product_cannibalization` and
   `pipeline_cannibalization` as primary fields. They are too directionally
   ambiguous.

3. Replace them with fields that distinguish internal ownership fit:

   ```text
   internal_strategic_fit =
       0.25 * franchise_transition_logic
     + 0.20 * pricing_contracting_fit
     + 0.20 * partner_alliance_fit
     + 0.15 * internal_portfolio_priority_fit
     + 0.10 * organizational_sponsorship
     + 0.10 * cannibalization_risk_inverse
   ```

4. Treat same-market overlap as one of three cases:
   - complementary overlap: positive,
   - defensive / franchise-protective overlap: positive or neutral,
   - value-destructive internal conflict: negative.

5. Add tests showing:
   - same-market next-generation target can improve strategic fit when it
     protects or transitions a franchise,
   - drug failure risk remains in POS / Layer 1A, not Layer 3F,
   - antitrust overlap remains in Layer 3E, not Layer 3F,
   - pricing, partner, and internal portfolio conflicts can still cap the pair.

**Priority**: Medium-high. This prevents double-counting, avoids treating all
overlap as bad, and gives Layer 3F a distinct job: whether the buyer's internal
business system supports owning the asset.

**Estimated scope**:
- Update `src/bve/intelligence/ma_layer3_pair_realism.py`
- Update or add `src/bve/intelligence/ma_internal_conflict.py`
- Add fixtures for franchise transition, defensive acquisition, partner
  conflict, pricing conflict, and true value-destructive cannibalization cases

---

### ARCH-1 — Layer 0 0A/0B separation: eligibility vs. deal-structure routing ✅ IMPLEMENTED

**Completed**: 2026-06-04

**What was the problem**: Layer 0A (the hard-exclusion / eligibility engine) was
doing double duty: it was both a stoplight gate (pass/fail) AND a model router
(licensing-only → LICENSING_MODEL, distress-only → DISTRESS_MODEL, etc.). This
violated separation of concerns. Gate 10 used `_CANONICAL_ROUTING_MAP` to route
companies to specialist models, mixing eligibility logic with transaction-type
classification.

**What was built**:

1. **0A refactored to pure stoplight gate** — produces one of seven
   `EligibilityStatus` values:
   `PASS / DILIGENCE_QUEUE / REFRESH_REQUIRED / LEGAL_REVIEW_QUEUE /
   SEVERE_CAP / HISTORICAL_ONLY / HARD_FAIL`.
   Gate 10 no longer routes companies. `_CANONICAL_ROUTING_MAP = {}`.

2. **0B now owns all model routing** — `classify_deal_structure_route()` in
   `deal_type_classification.py` emits `DealStructureRouteResult` with one of
   eleven `DealStructureRoute` values. `ASSET_LICENSE_PARTNERSHIP` expands into
   five licensing sub-routes (GLOBAL, REGIONAL, OPTION, CO_DEV, MINORITY_EQUITY).
   Structural signal overrides determine the sub-route.

3. **0B runs for imperfect targets** — when 0A returns DILIGENCE_QUEUE,
   REFRESH_REQUIRED, SEVERE_CAP, or LEGAL_REVIEW_QUEUE, 0B still runs and
   produces a tentative route (lower confidence). HARD_FAIL and HISTORICAL_ONLY
   do not get a 0B route.

4. **`EligibilityAssessment`** attached to `Layer0Result` — structured
   `can_enter_live_ranking` / `can_enter_historical_dataset` flags with
   `status_reason`, `hard_blockers`, `caps`, `required_diligence_items`.

5. **`MONITOR_ONLY` stays in Layer 4** — not a `DealStructureRoute` value.
   Action/cadence recommendations remain in `WatchlistClass`.

**Files changed**:
- `src/bve/intelligence/exclusions/rules.py` — Gate 10 refactored
- `src/bve/intelligence/deal_type_classification.py` — `DealStructureRoute` enum,
  `DealStructureRouteResult`, `classify_deal_structure_route()`, `_check_structure_overrides()`
- `src/bve/intelligence/ma_eligibility.py` — `EligibilityStatus`, `EligibilityAssessment`,
  `_build_eligibility_assessment()`, `run_0b` logic in `evaluate_layer0()`
- `tests/test_deal_type_enum_drift.py` — updated for new Gate 10 behavior
- `tests/test_ma_layer0_refactor.py` — new acceptance test suite (83 tests)

---

### AUTO-1 — Automatic clinical trial result ingestion and POS update (human-in-the-loop)

**Current state**: POS adjusters are set manually. When a Phase 2 trial reads out, a human
must open the YAML config and update:
- `prior_phase_data` (e.g. `STRONG_SINGLE` or `FAILED`)
- `clinical_effect_magnitude` (e.g. `EXCEEDS_MCID`)
- `data_maturity` (e.g. `MATURE_FINAL`)
- `moa_exception_flags` (e.g. add `HUMAN_PROOF_OF_MECHANISM`)

**The fix**: Build an automated pipeline that:

1. **Ingests** clinical trial result signals from:
   - ClinicalTrials.gov status transitions (e.g. `ACTIVE_NOT_RECRUITING` → `COMPLETED`)
   - FDA press announcements for breakthrough/accelerated designations
   - SEC 8-K filings containing trial result language
   - Company press releases parsed with an LLM extractor

2. **Extracts** the following fields in a structured format:
   - Trial phase and NCT ID
   - Primary endpoint met / not met
   - Effect size relative to MCID (requires TA-specific MCID table)
   - Safety signals (AE rates, dose discontinuations)
   - Data maturity (final vs. interim)
   - Regulatory feedback (if any)

3. **Proposes** a `POSAdjusterDraft` — a machine-generated suggestion for which enum
   values to set on `POSAdjusters`, with the source excerpt and confidence score attached

4. **Routes to human review**: the draft sits in a queue. A reviewer sees:
   - The raw excerpt ("ORR 42% vs 18% placebo, p=0.001, n=87")
   - The proposed mapping (e.g. `clinical_effect_magnitude=EXCEEDS_MCID`)
   - The current value in the YAML (e.g. `UNKNOWN`)
   - A diff showing what would change in the POS estimate

5. **On approval**: the approved values are written back to the asset YAML config,
   a provenance record is created in the evidence ledger, and the affected asset's
   POS is recomputed. The change is committed with the source URL as the commit message body.

**Why human review is required**: The mapping from raw trial data to `PriorPhaseDataStrength`
enum tier is judgment-sensitive. A trial can "succeed" statistically but fail commercially
(effect size below MCID). The model does not know the MCID for every endpoint in every TA
automatically. A human must confirm that the proposed tier is correct before it updates
the live POS estimate.

**Priority**: High. This is the single change that would most improve the usefulness of the
model for BD teams tracking live pipeline assets. Without it, POS updates lag real-world
data by however long it takes someone to manually update the YAML.

**Estimated scope**:
- New module: `src/bve/ingestion/trial_result_extractor.py` — parses 8-K/PR text using an LLM
- New module: `src/bve/ingestion/pos_update_queue.py` — stores pending POS adjuster drafts
- New module: `src/bve/review/pos_review_gate.py` — human approval workflow (CLI or web)
- Schema addition: `POSAdjusterDraft` dataclass with `proposed_value`, `source_excerpt`,
  `source_url`, `extracted_at`, `confidence`, `reviewer_id`, `approved_at`
- Integration: `ValuationEngine` reads approved drafts before computing POS

---

### POS-1 — Stratified conditional base rates by prior phase data quality

**The problem**

The current `PHASE_SUCCESS_RATES` table has one base rate per TA/phase combination. For example,
oncology Phase 3 = 0.495. This is the Biomedtracker/IQVIA-observed average across all drugs that
reached Phase 3 — a heterogeneous population that includes drugs entering on strong replicated
Phase 2 data AND drugs entering on weak or marginal Phase 2 signals. The model then applies a flat
`prior_phase_data_strength` log-odds adjuster on top of this pooled average.

**Why this is wrong**

The adjuster is measured against the wrong baseline. A drug with `strong_replicated` Phase 2 data
isn't an "average Phase 3 drug + bonus" — it's drawn from a fundamentally different sub-population
that historically succeeds at a higher rate than the pooled average. Conversely, a drug with `weak`
Phase 2 data is drawn from a sub-population that succeeds at a lower rate than the pooled average.
Applying a symmetric log-odds nudge on top of a single pooled base rate does not correctly represent
either group.

This means:
- Strong-Phase-2 drugs are undervalued (model starts at the average, adds a small bump)
- Weak-Phase-2 drugs are overvalued (model starts at the average, subtracts a small penalty)
- The flat +0.30 log-odds for `STRONG_REPLICATED` has different absolute probability impacts
  depending on where other adjusters have already moved the base (the additive log-odds assumption
  is geometrically inconsistent with a base rate that already encodes selection effects)

**The fix**

Replace the single Phase 3 (and Phase 2) base rate with a table stratified by prior phase data
quality. The stratified rates are empirically derivable from the same Biomedtracker/IQVIA dataset,
broken out by Phase 2 outcome quality:

```yaml
# Instead of:
oncology:
  phase_3: 0.495

# Use:
oncology:
  phase_3:
    strong_replicated: 0.65   # drugs with replicated Phase 2 signals
    strong_single:     0.58   # drugs with one strong Phase 2 study
    dose_response:     0.54   # clean dose-response but not full efficacy
    mixed:             0.495  # current pooled average (reference / no prior data)
    weak:              0.33   # marginal Phase 2 signal
    failed:            0.15   # borderline failure or rescued for Phase 3
```

With stratified base rates, `prior_phase_data_strength` becomes the **selector** that picks the
right row, rather than a log-odds bump stacked on the wrong baseline. The remaining adjusters
(endpoint type, safety, biomarker selection, competitive pressure) still apply on top of the
correctly-conditioned starting point.

**What to do with `prior_phase_data_strength` log-odds adjuster**

Remove it from the additive adjuster stack — its information is now encoded in the base rate
selection. Keep the enum field on `POSAdjusters` as the base rate selector. The field becomes
a first-class routing input rather than a log-odds weight.

**Implementation path**

1. **`industry_assumptions.yaml`**: nest Phase 2 and Phase 3 rates under
   `prior_phase_data_strength` keys. Keep a `mixed` fallback equal to the current value for
   backward compatibility when no prior data exists.
2. **`AssumptionsLoader.get_phase_success_rate()`**: add optional `prior_phase_strength`
   parameter. When provided, look up the stratified rate; when absent, use `mixed` fallback.
3. **`pos_model.compute_pos()`**: pass `pos_adjusters.prior_phase_data` to the base rate lookup;
   remove `_PRIOR_PHASE_LOGODDS` from the additive adjuster stack.
4. **Backtest re-validation**: re-run Brier/AUC on `research/data/oncology_phase_transitions.csv`
   after the change. Expect improved calibration at the extremes (strong and weak prior data groups).
5. **Backward compatibility**: configs that do not set `prior_phase_data` continue to receive the
   `mixed` base rate (identical to current behavior).

**Why the data to calibrate this exists**

The Biomedtracker/IQVIA phase transition reports include stratifications by Phase 2 design quality,
randomization, and endpoint type. The conditional rates above are conservative estimates consistent
with published literature (e.g., Thomas et al. 2016 showed ~2x differential between structured
vs. unstructured Phase 2 design for Phase 3 outcomes in oncology).

**Priority**: Medium-high. This is a calibration correctness fix that improves the model's
behavior specifically for the most common use case: evaluating assets that already have Phase 2
data in hand. Until fixed, the model systematically underestimates POS for well-validated Phase 2
drugs and overestimates for marginal ones.

**Estimated scope**:
- `src/bve/config/industry_assumptions.yaml` — nested base rate tables
- `src/bve/config/assumptions.py` — updated `get_phase_success_rate()` signature
- `src/bve/models/pos_model.py` — remove `_PRIOR_PHASE_LOGODDS` from adjuster stack; add base
  rate selector logic
- `tests/test_assumptions_loader.py` — add stratified lookup tests
- `tests/test_phase1.py` — update snapshot values that will shift for strong/weak prior data cases

---

### AUTO-1B — Phase-conditional weighting: endpoint type vs. actual trial data

**The problem in plain terms**

The POS model gives endpoint type (+0.40 for hard clinical outcomes) the same weight whether
you have zero human data or two clean replicated Phase 2 readouts. That is wrong. Endpoint
type is a *design prior* — a prediction about how trustworthy the upcoming trial will be.
Once you have actual trial data, that data already contains the endpoint type's information.
A clean Phase 2 on a hard clinical endpoint tells you both "the endpoint was credible" AND
"the molecule worked on that endpoint." Counting endpoint type again on top of the Phase 2
result is partial double-counting.

**When endpoint type should matter by phase**

| When you're assessing POS | What endpoint type is doing | Should it matter? |
|---|---|---|
| Pre-Phase 1 (no human data) | Tells you how credible the upcoming readout will be | A lot — it's one of your only signals |
| Pre-Phase 3 (have Phase 1+2 data) | Tells you how the Phase 3 is designed | Somewhat — but Phase 2 results already ran on this endpoint and showed what they showed |
| Pre-NDA (have Phase 1+2+3 data) | Retrospective design note | Almost nothing — the data exists, endpoint quality is baked in |

**Concrete example**

Pre-Phase 1 (no human data): endpoint type is a major signal.
- Base rate 60%, endpoint = hard clinical → +0.40 logit → POS rises to ~73%
- This makes sense: you're projecting forward with nothing else to go on.

Pre-Phase 3 (have clean Phase 2): endpoint type should barely matter.
- You have `prior_phase_data = STRONG_SINGLE` (+0.20) and
  `clinical_effect_magnitude = EXCEEDS_MCID` (+0.25).
- The Phase 2 already ran on that hard clinical endpoint and worked.
- Adding another +0.40 for "hard clinical endpoint in Phase 3" is mostly counting the same
  evidence twice: the molecule already showed up on that endpoint in Phase 2.

**The fix**

Layer 1 mixes two types of signals that need to be separated:

| Signal type | Examples | Weight rule |
|---|---|---|
| **Prospective design priors** (before data) | endpoint_type, sample_size, moa_precedent, dose_selection | Full weight when `prior_phase_data = UNKNOWN/MIXED`; attenuated when strong data exists |
| **Retrospective data evidence** (after data) | prior_phase_data, clinical_effect_magnitude, data_maturity | Should dominate when data exists; ceiling too low at current values |

Specific calibration changes needed:

1. **`prior_phase_data = STRONG_REPLICATED`**: raise from +0.30 → +0.45 to +0.50.
   Two clean replicated human studies is the strongest non-approval signal. Its ceiling
   being lower than `endpoint_type = HARD_CLINICAL` (+0.40) is backwards.

2. **`endpoint_type` weight should be phase-conditional**:
   - No prior data (`prior_phase_data = UNKNOWN/MIXED`): full weight (+0.40 for hard clinical)
   - Strong prior data (`prior_phase_data = STRONG_SINGLE/STRONG_REPLICATED`): attenuate to
     +0.10 to +0.15 — the endpoint quality is already proven by the data
   - At NDA/BLA stage: endpoint type is irrelevant — the trial is done

3. **Layer 1 `endpoint_type` and Layer 2 `endpoint_basis` overlap** — both capture
   "how trustworthy/validated is the endpoint." The `check_pos_layer_overlap()` guard warns
   about this. The long-term fix is merging them into a single endpoint quality signal or
   making Layer 2 only activate when it adds something Layer 1 doesn't already encode.

**Implementation path**

- Add `data_exists: bool` computed flag to `POSAdjusters` (True when
  `prior_phase_data` is not UNKNOWN/MIXED)
- In `apply_pos_adjusters()`, scale `_ENDPOINT_LOGODDS_*` by an attenuation factor:
  `1.0` when no data, `0.25` when strong data exists
- Raise `_PRIOR_PHASE_LOGODDS[STRONG_REPLICATED]` from +0.30 to +0.48
- Raise `_PRIOR_PHASE_LOGODDS[STRONG_SINGLE]` from +0.20 to +0.32
- Add regression tests to confirm Phase 3 POS with strong Phase 2 data is not dominated
  by endpoint type

**Priority**: Medium. This is a calibration correctness issue, not a feature gap. It matters
most for assets with confirmed Phase 2 readouts where the model may be underweighting the
actual result and overweighting the design prior.

---

### AUTO-2 — LLM news parsing layer for unstructured biotech headlines

Parse RSS feeds from BioPharmaDive, FierceBiotech, STAT News, and company IR pages.
Use an LLM to extract:
- Asset name and sponsor
- Signal type (efficacy, safety, regulatory, partnership)
- Sentiment and materiality estimate
- Mapping to event classifier signal types

Route to the existing `EventClassifier` pipeline after extraction.

---

### AUTO-3 — Rolling backtest automation

Run the VRTX/REGN backtest automatically on a monthly cadence as new deals are added to
the seed CSV. Generate a trend report showing whether the model's ranking metrics improve
or degrade as the dataset grows. Flag when any bucket falls below minimum thresholds.

---

### AUTO-4 — Expand to third acquirer

Add AstraZeneca, Pfizer, or BMS as a third acquirer with ≥5 verified deals. This is the
minimum required to make AUC and MRR figures statistically interpretable and to reduce
the VRTX-heavy concentration risk in the current backtest.

---

### DEAL-1 — Goodwill and strategic premium layer on top of rNPV

**The problem**

rNPV is intrinsic value. Every observed biotech acquisition includes a control premium and
strategic synergy premium that rNPV does not capture. The result: the tool's deal price floor
is correct but the tool has no way to estimate the *expected transaction price* — which is
what a BD team or buy-side investor actually needs.

**Component decomposition**

A deal price can be modeled as:

```
DealPrice = rNPV_floor
          + ControlPremium          (% of rNPV; reflects competitive bidding, urgency)
          + PlatformKnowhowValue    (assembled workforce, IP breadth, manufacturing know-how)
          + SynergyNPV              (PV of cost saves, avoided R&D duplication, cross-sell)
          + PipelineOptionality     (real-options value of unmodeled indications)
```

**Implementation path**

1. **New dataclass** `src/bve/models/goodwill_model.py`:
   ```python
   @dataclass(frozen=True)
   class GoodwillComponents:
       control_premium_pct: float         # 0.30–0.80 typical range (literature-backed)
       platform_knowhow_millions: float   # assembled workforce / IP value estimate
       synergy_npv_millions: float        # PV of acquirer-specific cost saves
       pipeline_optionality_millions: float  # real-options value for unmodeled indications
   ```
   `total_goodwill(rnpv)` returns sum of all components, with `control_premium` computed
   as `control_premium_pct × rnpv`.

2. **`DealEconomics` extension**: add optional `goodwill: GoodwillComponents | None = None`.
   When present, `ValuationOutput` reports `deal_price_estimate = rnpv + goodwill.total()`.
   When absent, the output only reports the rNPV floor with a disclaimer note.

3. **Acquirer-level defaults** in `acquirers.yaml`: each acquirer profile gains a
   `typical_control_premium_range: [0.35, 0.60]` field. The engine samples from this range
   in Monte Carlo to produce a deal price distribution, not just a point estimate.

4. **`deal_premium.py` integration**: currently measures the rNPV-to-deal-price gap ex-post.
   With this model, it can compare predicted goodwill to observed goodwill and over time
   calibrate the acquirer-level premium distributions to real historical deal data.

5. **Output addition**: new `goodwill_decomposition` dict in `valuation.json` and a
   "Deal Price Range" band on the scenario bars chart showing `[rNPV, rNPV + goodwill_low,
   rNPV + goodwill_high]`.

**Calibration source for control premium**

Published M&A literature (Mergerstat, PwC Pharma M&A reports) gives biotech control premiums
of 30–80% over undisturbed market price. The rNPV floor typically already implies some
development optionality, so the premium over rNPV may be narrower (20–50%) for assets where
rNPV already exceeds market cap, and wider (60–100%) for distressed or platform deals.
`deal_premium.py` on the VRTX/REGN dataset can empirically calibrate these numbers once
the dataset is large enough.

**Why this is not in the current model**

Control premium is acquirer-specific and deal-context-specific. A hardcoded 50% uplift would
be misleading. The fix requires (a) acquirer profiling, (b) synergy estimation logic, and
(c) empirical calibration from historical deals. The infrastructure for (a) and (c) now
exists in `acquirers.yaml` and `deal_premium.py`; (b) is the missing piece.

**Priority**: Medium. This is the fix that closes the gap between "what the tool says the
asset is worth" and "what a deal will actually price at." It matters most when using the
tool to assess whether a rumored deal price is fair or to size position targets around
acquisition probability.

---

### AUTO-5 — Automatic live data ingestion and score updates (full pipeline automation)

**The problem**

Almost every adjuster in the POS model and every sub-score in the M&A scanner is set manually
in YAML config files. When a trial reads out, a press release drops, a competitor gets approved,
or a company files an 8-K, nothing in the system updates automatically. A human must:
- Read the news
- Decide which adjusters change
- Open the relevant YAML
- Update the values
- Re-run the engine

This makes the tool a point-in-time snapshot rather than a live scoring system. The lag between
a real-world event and a score update is as long as it takes someone to notice and act.

For the M&A Layer 1 subweights specifically, the current framework is useful because it
forces an analyst to score asset quality, scarcity, value creation, transaction setup, and
structural cleanliness in a consistent way. The future product should preserve that framework
but remove the requirement that every sub-score be hand-entered. A non-BD user will not have
access to private buyer diligence, banker conversations, or internal pipeline-gap work, but
the tool can still approximate a large part of the process from public evidence: SEC filings,
press releases, ClinicalTrials.gov, FDA pages, PubMed, conference abstracts, company decks,
earnings transcripts, financing history, price action, and reputable news.

The intended future state is a public-source BD analyst layer:

- Search public sources for each Layer 1 subweight before scoring it.
- Produce citation-backed proposed scores for clinical evidence, differentiation,
  regulatory path, IP/exclusivity, CMC feasibility, commercial meaningfulness,
  management execution, strategic scarcity, financing pressure, seller openness,
  rights clarity, and related fields.
- Store each proposed sub-score with source URLs, extracted evidence, freshness date,
  confidence, and a short rationale.
- Update proposed scores when new material news arrives, while preserving the previous
  score history so users can see what changed and why.
- Route judgment-heavy or low-confidence updates to review instead of silently changing
  the live score.
- Clearly label fields that remain only rough public-market proxies for private BD
  information, especially seller openness, buyer-specific pipeline-gap urgency, private
  process activity, diligence readiness, and undisclosed contractual encumbrances.

This should make the M&A scoring layer useful for regular investors and independent analysts:
not as a replacement for company-side BD diligence, but as a disciplined public-information
framework that continuously refreshes when the evidence changes.

The POS layer should be one of the main upstream generators for Layer 1A Asset
Quality. Today, POS adjusters and Layer 1A subweights can both be manually set,
which creates duplicate analyst work and risks inconsistent scores. The target
architecture should make POS/science/regulatory outputs propose Asset Quality
subscores:

- `clinical_evidence` from phase, prior-phase data, endpoint quality, effect
  size, trial design, safety, consistency, and data maturity.
- `regulatory_path` from approval pathway, endpoint acceptability, precedent,
  designations, FDA/EMA meeting outcomes, hold/CRL status, and filing readiness.
- `differentiation` from effect size, comparator quality, standard-of-care
  mapping, biomarker selection, safety, convenience, and durability.
- `commercial_meaningfulness` from POS-adjusted market model, label breadth,
  endpoint quality, safety/access implications, competition, and expected
  adoption.

POS should not replace Layer 1A. POS estimates technical/regulatory probability;
Layer 1A converts that evidence into buyer-neutral asset quality. The automated
handoff should create reviewable `Layer1AssetQualityDraft` records with source
facts, proposed 0-1 subscore, confidence, and score-impact attribution.

**What should update automatically (full scope)**

| Data source | What it should trigger |
|---|---|
| ClinicalTrials.gov status transition | `prior_phase_data`, `data_maturity` update candidates |
| SEC 8-K trial result language | `clinical_effect_magnitude`, `safety_flag` update candidates |
| FDA press release (designation/approval) | `has_breakthrough_designation`, `approval_pathway` update |
| Company press release (LLM-parsed) | All POS adjusters flagged as stale |
| Competitor approval in same TA | `competitive_pressure` update for all assets in that TA |
| Head-to-head trial result | `clinical_effect_magnitude` update (vs active comparator) |
| New safety signal (AE report, FDA safety comms) | `safety_flag` update candidate |
| M&A news (acquirer deal announced) | Acquirer pipeline gap recalculated; M&A scores for TA refreshed |
| Company BD activity (partnership, licensing) | `prior_bd_activity`, `seller_openness` update |

**What the update pipeline looks like**

1. **Ingestion**: continuous monitor watches SEC EDGAR, CT.gov, FDA, major wire services
2. **Classification**: event classifier tags the event type and the asset(s) affected
3. **Extraction**: LLM or rule-based extractor pulls structured fields (trial phase, p-value,
   endpoint met/not met, safety signal type, etc.)
4. **Draft proposal**: system generates a `ScoreUpdateDraft` with:
   - Proposed adjuster/sub-score change
   - Source excerpt and URL
   - Confidence level
   - Current value vs proposed value
   - Estimated score delta
   - POS-to-Layer-1A handoff fields when the event changes clinical evidence,
     regulatory path, differentiation, or commercial meaningfulness
5. **Routing**: high-confidence changes (e.g., CT.gov status = COMPLETED) can auto-apply
   with provenance record; low-confidence changes route to human review queue
6. **Application**: approved changes write back to YAML + evidence ledger; engine recomputes;
   M&A rankings re-ranked; watchlist classes updated

**Why full automation isn't built yet**

The ingestion and classification infrastructure exists (`event_classifier.py`,
`universe_scanner.py`, `continuous_monitoring.py`). The missing pieces are:
- A structured mapping from event type → specific adjuster field + new value
- A `ScoreUpdateDraft` queue with human-review gate (partial design in AUTO-1)
- A rule engine that translates "competitor approved in 1L NSCLC" into a competitive_pressure
  update for every other asset in that bucket
- M&A layer re-ranking triggered by score changes (currently batch-only)

**Priority**: High. This is the single architectural gap that limits the tool from being a
continuously-maintained intelligence system rather than a manually-updated scorecard.

---

### AUTO-6 — Endpoint quality → commercial value propagation post-approval

**The problem**

When a drug gets approved on a weak or surrogate endpoint (e.g., accelerated approval on
biomarker response rate rather than OS in oncology), the POS model correctly penalizes the
probability of approval. But once approved, P(approval) = 1.0 and the rNPV is driven entirely
by the `MarketModel` assumptions set manually in YAML. The model has no automatic link from
"weak endpoint" → "lower payer access" → "lower penetration/price."

**What a weak endpoint approval actually means commercially**

- Narrow label: FDA often restricts to the exact population studied, reducing addressable patients
- Payer pushback: formulary restrictions, step-therapy requirements, prior authorization burden
- Net price discount: payers negotiate harder without hard clinical outcome data
- Confirmatory trial overhang: risk of label withdrawal if confirmatory trial fails
- Competitor displacement risk: a later entrant with OS data can displace the surrogate-approval drug

**None of this is captured automatically.** The rNPV of a drug approved on a surrogate endpoint
looks identical to a drug approved on hard OS data if the analyst uses the same MarketModel
assumptions for both.

**The fix**

1. Add `approval_endpoint_quality: EndpointQuality` field to `CommercialPlan`
   (enum: `HARD_CLINICAL`, `VALIDATED_SURROGATE`, `UNVALIDATED_SURROGATE`, `ACCELERATED_PENDING_CONFIRMATION`)
2. In `MarketModel`, apply automatic adjustments when `approval_endpoint_quality` is set:
   - `HARD_CLINICAL`: no adjustment (reference)
   - `VALIDATED_SURROGATE`: −10% peak penetration (payer friction, not clinically meaningful gap)
   - `UNVALIDATED_SURROGATE`: −20% peak penetration, −15% net price (significant payer pushback)
   - `ACCELERATED_PENDING_CONFIRMATION`: as above + confirmation trial costs added to `CostModel`
3. Add `label_breadth_discount: float` field (0–1.0) to apply when the approved label is
   narrower than the full `addressable_patients_annual` pool
4. Document as a post-approval commercial adjustment, separate from the pre-approval POS penalty,
   so the two layers are not double-counted

**Priority**: Medium. Matters most for assets on accelerated approval pathways or those with
surrogate endpoint approvals where the label is actively contested by payers.

---

## Calibration and Behavior Review Items

The following are known model behaviors that are defensible but potentially miscalibrated.
Each should be reviewed and considered for adjustment as the backtest dataset grows.

### REVIEW-1 — Endpoint type weight attenuation by phase

**Current behavior**: `endpoint_type` contributes the same logit weight whether the asset is
pre-Phase 1 (no human data) or pre-NDA (Phase 3 complete). Documented in AUTO-1B.

**Why it may be wrong**: Endpoint type is a design prior — a prediction about how trustworthy
future data will be. Once you have Phase 2 data on that same endpoint, the endpoint quality is
already embedded in the result. Counting endpoint type again is partial double-counting.

**Review question**: Should `endpoint_type` weight attenuate to near-zero when
`prior_phase_data = STRONG_REPLICATED`?

---

### REVIEW-2 — Novel MoA penalty vs strong Phase 1 data

**Current behavior**: `moa_precedent = NO_PRECEDENT` applies a fixed negative logit (~−0.25)
regardless of what Phase 1 showed. `prior_phase_data = STRONG_SINGLE` adds only +0.20, so
a novel MoA asset with clean Phase 1 proof-of-mechanism is still net-negative vs a conventional
MoA with no data.

**Why it may be wrong**: If Phase 1 demonstrates clear human proof of mechanism (PK/PD,
dose-response, early efficacy signal), the lack of historical precedent becomes a much weaker
concern. The `HUMAN_PROOF_OF_MECHANISM` exception flag partially handles this, but only if
manually set.

**Review question**: Should `HUMAN_PROOF_OF_MECHANISM` in `moa_exception_flags` fully neutralize
the `NO_PRECEDENT` penalty rather than partially offsetting it?

---

### REVIEW-3 — Small sample size penalty vs effect size magnitude

**Current behavior**: `sample_size = SMALL` applies a fixed negative logit (~−0.20) regardless
of the observed effect size. `clinical_effect_magnitude = EXCEEDS_MCID` adds +0.25, so they
partially cancel. A small trial with a massive effect size is penalized for being small even
when the signal is statistically unambiguous.

**Why it may be wrong**: A 40-patient trial showing 80% ORR vs 10% historical control has
very different inferential weight than a 40-patient trial showing 25% ORR vs 18% SoC. Both
receive the same `SMALL` penalty. In high-effect-size scenarios, underpowering concerns
largely vanish.

**Review question**: Should `sample_size` penalty be conditioned on `clinical_effect_magnitude`?
If `EXCEEDS_MCID` and n ≥ threshold, attenuate the small-sample penalty.

---

### REVIEW-4 — Safety flag is static; no dynamic safety update

**Current behavior**: `safety_flag` is set manually and never changes unless a human updates
the YAML. Default when unknown = neutral (0 adjustment). Late-emerging safety signals from
post-approval studies, REMS additions, or competitor class-effect signals do not flow into
the model.

**Why it may be wrong**: Safety is one of the highest-impact factors for both POS and commercial
value, but it's the least automatically maintained. A class-effect AE warning in a related drug
should trigger a review of all assets with the same MoA.

**Review question**: Should safety flag changes be one of the first AUTO-5 automated triggers,
given safety's disproportionate impact on both POS and payer access?

---

### REVIEW-5 — Competitive pressure reflects crowding, not head-to-head outcomes

**Current behavior**: `competitive_pressure` captures how crowded the therapeutic area is.
A head-to-head win (drug beats active comparator) is captured indirectly via
`clinical_effect_magnitude = EXCEEDS_MCID`, not as a competitive signal. A head-to-head loss
requires manually setting `prior_phase_data = FAILED` or `MIXED`.

**Why it may be wrong**: Competitive pressure and head-to-head outcomes are distinct signals.
A drug can be in an uncrowded space but lose a head-to-head (bad). Or it can be in a crowded
space and dominate every comparator (good). These are not equivalent. The current model treats
competitive landscape as a static crowding count, not a relative differentiation score.

**Review question**: Add a `competitive_differentiation` sub-adjuster that captures relative
performance vs SoC/competitors (SUPERIOR / COMPARABLE / INFERIOR), separate from crowding count.

---

### REVIEW-6 — POS Layer 2 trial-design buckets are context-blind

**Current behavior**: POS Layer 2 uses generic log-odds buckets for
`evidence_design_quality`, `comparator_fit`, `regulatory_pathway_risk`, and
`clinical_effect_magnitude`, then applies phase scaling. The same raw bucket
value is used across therapeutic areas, indications, lines of therapy, endpoint
types, and regulatory contexts.

**Why it may be wrong**: trial-design evidence quality is context dependent. A
single-arm objective-response study can be acceptable in refractory oncology or
ultra-rare disease, but weak in a common disease where randomized active-control
data are expected. Placebo can be acceptable when no standard therapy exists,
but unacceptable when active standard-of-care treatment is available. MCID and
surrogate validity also vary by disease and endpoint.

The current model is therefore context-interpreted by the analyst, but not fully
context-calibrated in the coefficients.

There is also a product-description gap. The intended two-layer POS rubric says
Layer 1 should cover evidence quality / biological credibility and Layer 2 should
cover trial design / execution tightness. The code only partially matches that
full description today:

- POS Layer 1 mostly covers endpoint type, MoA precedent, sample size adequacy,
  safety, biomarker selection, and prior-phase data, but effect size and
  statistical strength are still mostly tiered/manual rather than automatically
  parsed from p-values, confidence intervals, and endpoint-specific effect sizes.
- POS Layer 2 covers evidence design quality, comparator fit, regulatory pathway
  risk, clinical effect magnitude, and phase scaling, but it does not yet expose
  every expected design-tightness input as a first-class field.
- Missing or only partially wired Layer 2 fields include endpoint hierarchy,
  explicit powering/statistical power, patient selection, stratification,
  follow-up duration, operational feasibility, and detailed FDA/EMA alignment.
- Supporting modules contain some of this logic, but the integrated core POS
  path should make the distinction visible and auditable in one output.

**The fix**:

1. Add context fields to `TrialDesignFeatureSet`:
   - `therapeutic_area`
   - `indication`
   - `line_of_therapy`
   - `endpoint_type`
   - `comparator_available`
   - `accepted_regulatory_precedent`
   - `rare_disease_context`

2. Add TA/indication/line-specific maps for:
   - when single-arm evidence is acceptable,
   - when placebo is acceptable,
   - what comparator counts as standard of care,
   - which surrogate endpoints are validated,
   - MCID thresholds by endpoint and disease.

3. Adjust Layer 2 bucket effects by context. Examples:
   - attenuate `single_arm_objective` penalty when no ethical/practical
     comparator exists,
   - increase penalty for no active comparator when one is expected,
   - distinguish validated oncology surrogate from novel biomarker-only endpoint,
   - apply TA-specific MCID thresholds to `clinical_effect_magnitude`.

4. Add tests covering:
   - refractory oncology single-arm objective endpoint,
   - first-line oncology active-comparator expectation,
   - ultra-rare disease natural-history control,
   - common chronic disease placebo in an active-treatment setting,
   - disease-specific MCID mapping.

5. Expand the integrated POS Layer 2 schema so the product-level rubric is true
   in code, not only in documentation:
   - `endpoint_hierarchy_quality`
   - `statistical_power_adequacy`
   - `patient_selection_fit`
   - `stratification_quality`
   - `follow_up_duration_adequacy`
   - `operational_feasibility`
   - `regulatory_alignment_quality`

6. Add a POS output audit that explicitly reports:
   - which Layer 1 evidence-quality fields were scored,
   - which Layer 2 design-tightness fields were scored,
   - which expected fields were missing,
   - whether a score is analyst-entered, extracted from source text, or computed
     from structured trial data.

**Review question**: Should POS Layer 2 remain generic and analyst-interpreted,
or should the model load TA/indication/line-specific evidence-design maps from
configuration and use those to set the bucket effects directly?

---

### REVIEW-6B — Clinical readout magnitude and duration are under-specified

**Current behavior**: Clinical readout interpretation still relies too much on
coarse buckets such as `clinical_effect_magnitude = EXCEEDS_MCID` or
`prior_phase_data = STRONG_SINGLE`. Those buckets can lose critical numerical
context. For example, a readout showing `+6 months overall survival` and a
readout showing `+6 years overall survival` may both be treated as "positive
overall survival data" unless the analyst manually encodes the magnitude and
follow-up context.

**Why it may be wrong**: The economic and clinical meaning of an endpoint result
depends on units, time horizon, baseline risk, comparator, confidence interval,
follow-up duration, censoring, and disease context. A six-month OS benefit in
refractory oncology can be highly meaningful; a six-year OS benefit would be an
extraordinary, potentially category-changing result. The model needs to
differentiate these cases instead of compressing them into the same qualitative
positive-data bucket.

This also exposes a broader scoring weakness: many values in the log-odds and
composite scoring stack were selected as expert-judgment priors, not learned
from observed outcomes. Log-odds additivity is useful for bounded probability
math, but it has downsides: correlated evidence can be double-counted, absolute
effect sizes can be flattened, and hand-picked coefficients can look more
precise than the evidence supports.

**The fix**:

1. Add structured readout fields that preserve numerical context:
   - `endpoint_name`
   - `endpoint_unit` (months, years, percent, hazard_ratio, score_change, etc.)
   - `absolute_effect_size`
   - `relative_effect_size`
   - `confidence_interval`
   - `p_value`
   - `median_follow_up`
   - `baseline_or_control_value`
   - `comparator_type`
   - `disease_context`
   - `line_of_therapy`

2. Normalize time-based outcomes before scoring. For OS/PFS/duration endpoints,
   convert reported effects into a consistent unit and explicitly distinguish
   `+6 months` from `+6 years`.

3. Replace single qualitative effect buckets with endpoint-specific effect-size
   functions where data exists. Example: oncology OS should use a different
   mapping than depression scale change, seizure-frequency reduction, or
   hemoglobin improvement.

4. Add extraction tests for readout units and duration:
   - `+6 month overall survival`
   - `+6 year overall survival`
   - median OS improvement vs hazard ratio
   - PFS benefit with immature OS
   - percent response endpoint vs time-to-event endpoint

5. Add backtesting hooks so effect-size mappings, log-odds adjuster weights,
   and composite scoring thresholds can be fitted or recalibrated against
   historical outcomes instead of staying fixed at AI-selected defaults. At
   minimum, compare current heuristic weights against:
   - logistic regression with base-rate offset,
   - regularized interaction model for correlated signals,
   - isotonic or Platt calibration on model outputs,
   - simple ablation tests showing whether each adjuster improves Brier score,
     AUC, and calibration error.

**Review question**: Should clinical readout scoring move from qualitative
buckets to endpoint-specific numerical effect-size functions before any further
POS coefficient tuning?

**Priority**: High. This can materially change POS, rNPV, and acquisition
attractiveness, especially when the tool ingests clinical readout press
releases automatically.

---

### REVIEW-7 — Accelerated approval pathway penalty may be asymmetric

**Current behavior**: `approval_pathway = ACCELERATED_APPROVAL` applies a slight negative
logit to reflect confirmatory trial risk. But Breakthrough Designation (`BREAKTHROUGH_DESIGNATION`)
applies only a slight positive logit. Both are assigned the same phase-conditional scaling.

**Why it may be wrong**: Breakthrough Designation is both a regulatory pathway signal AND
evidence of FDA engagement — it often co-occurs with strong early data. Treating it as a minor
positive may underweight what is in practice a strong combined signal (strong data + FDA buy-in).

**Review question**: Should Breakthrough Designation interact with `prior_phase_data` — i.e.,
Breakthrough + STRONG_SINGLE should yield a larger combined bonus than either alone?

---

### REVIEW-8 — Market sizing mode is not enforced by therapeutic area

**Current behavior**: The analyst manually selects market sizing mode (lines_of_therapy /
patient-based / TAM-based) in YAML. There is no enforcement or warning if an oncology asset
uses TAM-based sizing instead of lines_of_therapy.

**Why it may be wrong**: TAM-based sizing for oncology systematically overstates or understates
depending on the analyst's TAM assumption. Lines-of-therapy is the clinically grounded mode
for oncology because it reflects actual treatment decision points.

**Review question**: Add a validation warning when `therapeutic_area = oncology` and
`market_sizing_mode = TAM_BASED`. Suggest switching to `lines_of_therapy` with a pointer to
the YAML schema.

---

### MODEL-2 — Adjuster independence assumption inflates POS when signals are correlated

**The problem**

Log-odds additivity assumes every adjuster is statistically independent — that knowing the
biomarker is validated tells you nothing about whether prior phase data was strong. In practice
these signals are correlated. Trials with validated predictive biomarkers tend to produce stronger
Phase 2 signals. Strong Phase 2 signals tend to come from well-designed RCTs with hard endpoints.
Clean safety tends to co-occur with mechanism-validated targets.

When signals are correlated and you treat them as independent, the combined log-odds sum
overcounts evidence. A drug scoring positive on `biomarker: validated` + `prior_phase_data:
strong_replicated` + `rct_double_blind` + `clinical_effect_magnitude: exceeds_mcid` is
not receiving four independent pieces of evidence — it is receiving four correlated descriptions
of the same underlying reality: a well-designed trial on a real target that showed a clean result.
The model inflates POS in the all-positive case and deflates it in the all-negative case, because
there is no covariance structure in the adjuster stack.

`check_pos_layer_overlap()` detects specific named pairs but does not address the general
problem — the log-odds stack has no correlation model at all.

**The real fix**

A logistic regression fitted to historical trial outcomes with interaction terms, or a Bayesian
network with an explicit dependency graph between signals. Either requires a training dataset of
several hundred labeled trial outcomes with structured adjuster values. The dataset does not
exist at that scale yet. Until it does, the model should be understood as a structured expert
judgment system that ranks correctly directionally, not as a calibrated probability estimator.

**Interim mitigation**

Add an explicit correlation warning to `compute_pos()` output when two or more of the following
high-correlation pairs are both set positively:
- `biomarker: validated` + `prior_phase_data: strong_single/strong_replicated`
- `prior_phase_data: strong_replicated` + `clinical_effect_magnitude: exceeds_mcid`
- `moa_precedent: clinically_validated_target` + `moa_exception_flags: HUMAN_PROOF_OF_MECHANISM`
- `evidence_design: rct_double_blind` + `comparator_fit: matches_soc`

The warning should report the estimated overcounting magnitude and suggest the analyst consider
whether the signals are truly independent or are describing the same underlying evidence.

**Priority**: Medium. This is a fundamental statistical limitation of the log-odds architecture.
It cannot be fully fixed without a labeled training dataset. The interim mitigation makes the
limitation visible without requiring a model rewrite.

---

### MODEL-3 — Adjuster magnitudes are not empirically validated

**The problem**

The log-odds values throughout the POS model (+0.20 for strong prior data, +0.40 for hard
clinical endpoint, +0.25 for validated biomarker, etc.) are evidence-informed priors calibrated
from published literature and expert judgment. They are not regression coefficients fitted to
observed trial outcomes.

The current backtest (N=99 oncology programs, Brier=0.2127, AUC=0.74) validates that the model
ranks correctly more often than not — the drugs it assigns higher POS to succeed at a higher
rate. But AUC only measures ranking order. It does not validate whether the probability
magnitudes are accurate.

A drug the model assigns 80% POS does not mean 80% of drugs in that configuration get approved.
It means those drugs rank near the top. The gap between a ranked-correctly model and a
calibrated-probability model matters when rNPV is directly multiplied by
`cumulative_approval_probability`. Systematically inflated POS magnitudes (e.g., from the
independence issue in MODEL-2) translate directly into inflated rNPV, which a BD team could
use to justify overpaying for an asset.

**The fix**

1. **Expand the backtest dataset** to N≥300 labeled trial outcomes across multiple TAs, with
   structured adjuster values recorded at the time of assessment (not retrofitted).
2. **Fit calibration correction curves** per TA/phase — Platt scaling or isotonic regression
   on the backtest outputs to convert model scores to calibrated probabilities.
3. **Report calibration diagnostics** alongside every POS output: expected calibration error
   (ECE), reliability diagram bucket counts, and a flag when the input combination falls
   outside the training distribution.
4. **Separate ranking validity from calibration validity** in all external communications:
   "AUC=0.74 means the model ranks drugs correctly" is a different claim from "the model's
   probability estimates are accurate."

**Priority**: High for any use case where the absolute POS value (not just ranking) drives a
financial decision. The current model is defensible as a ranking tool; it is not yet defensible
as a calibrated probability estimator.

---

## Known Non-Issues (Intentional Design Choices)

- **POS adjusters are evidence-informed priors, not statistically estimated coefficients.**
  They are calibrated from published Biomedtracker/IQVIA base rates and literature-sourced
  log-odds values. They are not regression weights fitted to a dataset. This is intentional:
  fitting weights to N<100 historical outcomes would overfit badly. The model is designed to
  be defensible as a structured expert judgment system, not a black-box ML model.

- **The negative DCF for Semma, ViaCyte, and Decibel is not a model failure.** These are
  early-stage option-value acquisitions. A standalone DCF correctly returns negative for
  pre-revenue assets with no near-term approval path. The strategic premium metric
  (Block 15) now makes this explicit.

- **CT.gov phase data is not point-in-time by default.** The ClinicalTrials.gov v2 API
  returns current records. The `TrialPhaseResolver` and `clinicaltrials_point_in_time_audit.csv`
  enforce exclusion of post-snapshot records. This is a deliberate constraint, not a gap.
