# Preregistration — adverse-event framing in the human-PoC veto (v1)

Written and committed **before** any code change or measurement, 2026-09-21.

Baseline: `src/bve/se/evidence/human_poc.py` at `bf96578`, sha256
`6f4b9d1c5d9064a452172e83dc6103e444e6a7369770fa6e584a1722df012468`,
`EXTRACTOR_VERSION = "human_poc_v2"`. Reference run `aacr_cr` (`human_poc` = 42).

Successor to `human_poc_abbreviations_and_mixed_sentences_v1.md`, which was **frozen, not adopted**:
clause-scoping the non-efficacy veto found one real result (`Cevostamab`) and one false positive
(`tabelecleucel`). This milestone exists to refuse the false positive without losing the real one.

**This is a separate milestone, not a patch to the frozen one.** The predecessor's result stands as
recorded. Its two candidate remediations were identified *after* seeing which sentence failed, which
is exactly why they are being declared here, in advance, with controls chosen before measurement —
rather than applied silently to make the previous run look successful.

---

## 1. The rule

Three clauses, the first two new:

1. **Adverse-event framing makes a clause non-efficacy.** `complication` / `complications` joins
   `_NON_EFFICACY_TERMS`. A clause that introduces its contents as complications is reporting harm,
   whatever endpoint vocabulary it then uses.
2. **`tumor flare reaction` is not an efficacy `flare`.** `tumor flare`, `tumour flare` and
   `flare reaction` join `_NON_EFFICACY_TERMS`. This is needed independently of rule 1: a sentence
   saying *"tumor flare reaction occurred in 20% of patients"* carries no complications word and
   would otherwise still read as an efficacy result.
3. **A quantified response in a separate clean clause still counts.** This is existing behaviour and
   is not being changed — it is pinned by test so that rules 1 and 2 cannot quietly take it away.

Why `flare` itself stays an efficacy term: an IgG4-RD or lupus **disease flare** is a real efficacy
endpoint, and the corpus contains at least two legitimate PASSes that depend on it. The word is
doing honest work in two different clinical registers, and the fix must separate the registers
rather than delete the term.

Nothing else changes. Out of scope, unchanged, and not to be touched while measuring:
`_VALUE`, `_EFFICACY_TERMS`, `_HUMAN_TERMS`, `_UNREPORTED_TERMS`, `_NONHUMAN_TERMS`, the abbreviation
tuples added at `bf96578`, the clause splitter, and **sentence-scoped attribution** — which the
predecessor's evidence suggests is the real recall bottleneck, and which is explicitly deferred to
its own milestone.

## 2. Declared before measurement: a pre-existing false positive that this milestone will NOT fix

`INDIGO` is in the **baseline 40**, and it is wrong:

> *"The INDIGO trial achieved its global enrollment goal with 194 patients, making it the largest
> phase 3 trial in IgG4-RD to date and providing 90% power to detect a clinically meaningful
> reduction in flare risk."*

That is an enrollment and statistical-power statement, not an observed result, and `INDIGO` is a
trial name being carried as an asset. It predates every change in this milestone and its
predecessor. It is recorded here so that the post-run count of 41 is not read as 41 clean facts, and
so that a later milestone does not rediscover it and mistake it for a regression. **It is not to be
fixed in this milestone**, because fixing it means either new `_UNREPORTED_TERMS` entries (`power to
detect`, `enrollment goal`) or an identity change, and both deserve their own controls.

## 3. Controls

`tabelecleucel` and `Cevostamab` are pinned as the user specified. The remaining controls were
**not** used to invent the rule: they are existing corpus PASSes that the rule must not disturb, and
they were selected by asking which live facts touch the words being changed — before the rule was
written into code.

### Must become UNKNOWN

| id | sentence | today |
|---|---|---|
| tabelecleucel | *"For VSTs, the principal early complications are tumor flare reaction (in approximately 20% of tabelecleucel recipients), GVHD (below 5% with enriched products), acute infusion reactions, and low-grade CRS-like cytokine release."* | PASS (endpoint `flare`) |

### Must remain PASS

| id | sentence | why it is at risk |
|---|---|---|
| Cevostamab | *"Cevostamab (FcRH5×CD3) demonstrated a 30.2% overall response rate in patients who underwent BCMA-targeted treatment and 60.6% in BCMA-targeted naïve patients; the triple-step dosing strategy reduced cytokine release syndrome."* | the whole point of the predecessor |
| obexelimab | *"flares were reported in 26 patients (26.8%) in the obexelimab group and in 53 patients (54.6%) in the placebo group."* | a real efficacy result **on `flare`** — proves rule 2 did not delete the endpoint |
| abatacept | *"Although 14 of 15 patients flared, disease activity remained lower, and responsiveness lasting >3 months to previously failed drugs … observed in 7 of 15"* | contains `flared`; must not be caught by `flare reaction` |

### Additional negative controls

| id | sentence | must be |
|---|---|---|
| tumor-flare-alone | *"Tumor flare reaction occurred in 20% of patients treated with X."* | refused — carries no complications word, so this tests rule 2 alone |
| complication-alone | *"The principal complications were infusion reactions in 8 of 20 patients."* | refused |
| mixed-clean-clause | *"The overall response rate was 62% in 40 patients, and the principal early complications were infusion reactions."* | **PASS** — tests rule 3; a complications clause must not veto a clean quantified result elsewhere |
| safety-only | *"X was well tolerated with grade 3 adverse events in 5 of 20 patients."* | refused |

## 4. Predicted outcome, declared in advance

Replay of the sealed AACR corpus, same argv as `aacr_cr` with a new output directory.

| gate | `aacr_decoupled` | `aacr_cr` | **predicted** |
|---|---|---|---|
| `identity.distinct_asset` | 775 | 775 | 775 |
| `target.expression` | 56 | 56 | 56 |
| `evidence.minimum_stage` | 638 | 638 | 638 |
| `evidence.human_poc` | 40 | 42 | **41** |
| candidates / low-support | 2837 / 1409 | 2837 / 1409 | 2837 / 1409 |

**Adoption bar, fixed now:** `human_poc` = 41; `Cevostamab` present; `tabelecleucel` absent;
`obexelimab` and `abatacept` still present; no other asset gained or lost; the other four gates
unchanged. Anything else — including 41 reached by losing a different asset — is a failure, not a
pass, and is reported as such.

If a *new* false positive appears, the stop condition from the predecessor applies unchanged: freeze
and report before remediating.

## 5. Not to be done

Touching sentence-scoped attribution; fixing `INDIGO`; relaxing `_VALUE`; adding further
abbreviations; adjusting any term list after seeing the run.
