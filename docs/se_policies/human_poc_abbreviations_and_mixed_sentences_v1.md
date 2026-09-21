# Preregistration — human-PoC abbreviations and mixed efficacy+safety sentences (v1)

Written and committed **before** any code change or measurement, 2026-09-20.

Baseline: `src/bve/se/evidence/human_poc.py` sha256
`cd8d963c5ff18da54f58aebcb9bf140f5d54c83c2bafe8924af9d254f703958a`, at commit `2b4e714`,
`EXTRACTOR_VERSION = "human_poc_v1"`.

Predecessor: `conference_human_poc_admissibility_v1.md`. That milestone returned a null result and
named the three clauses that bind on conference prose. This milestone acts on two of them. The
third — sentence-scoped attribution — is deliberately untouched.

---

## 1. What is being fixed, and what is not

The standard stays exactly as it is: a human proof-of-concept fact requires real treated patients, a
named asset or construct in the same sentence, an observed result, an attributable outcome, and no
planned endpoint. **Nothing in this milestone relaxes any of those five requirements.**

Two defects are being fixed, and they are the same defect twice:

- **The standard does not recognise the conventional abbreviation of terms it already accepts.**
  `complete response` and `complete remission` are already efficacy terms; bare `CR` is not.
  `patient` and `participant` are already human terms; `pts` and `Pt` are not. An abstract that
  writes the short form says the same thing as one that writes it out.
- **A safety term anywhere in a sentence vetoes an efficacy result reported elsewhere in it.**
  `Pt 1 achieved a complete response (CR) and experienced Gr 3 fever …` is refused because
  `cytokine release` appears nine words later.

Explicitly **not** in scope, and not to be changed while measuring this milestone:

- The requirement that the sentence report a **quantified** value (`%`, `n=`, or `x of y`). This is
  the `observed result` requirement and it stays.
- Sentence-scoped attribution. An asset named in one sentence and a result in another stays refused.
- `_MAX_SENTENCE_CHARS`, `_ELIGIBILITY_TERMS`, `_NONHUMAN_TERMS`, `_UNREPORTED_TERMS`.
- `NON_DECISIONAL_FOR_HUMAN_POC`, which the previous milestone emptied.

## 2. The three changes, stated before measurement

**Change A — bare `CR` as an efficacy term.** Matched **case-sensitively** with word boundaries, not
by the existing casefolded substring test. Case sensitivity and word boundaries are both load-bearing:
substring matching would fire inside `across` and `increase`, and a case-insensitive word match would
fire on prose uses of `cr`. `CRS`, `CRP` and `CRi` do not match under `\bCR\b`.

Only `CR` is added. `PR` is **excluded** because AACR abstract numbers take the form `PR06` and the
identity layer has already been burned once by bibliographic identifiers. `ORR` is excluded because
`objective response` and `overall response` already cover it and adding it buys nothing the positives
need.

**Change B — `pts` / `Pt` / `Pts` as human terms.** Same rule, same justification: word-bounded,
case-insensitive is acceptable here because `pts` is not an English word. This change is **not one
the user asked for.** It is included because without it neither LB-138 nor PR06's `10/16 evaluable
pts` sentence can be evaluated at all — the safety veto is not what refuses them — and because it is
the identical principle to change A. It is measured and reported separately so it can be rejected
alone.

**Change C — the non-efficacy veto becomes clause-scoped.** Today any `_NON_EFFICACY_TERMS` match
anywhere in the sentence refuses it outright. After this change, the veto is lifted only if the
sentence contains a **clause** that holds an efficacy term and holds **no** non-efficacy term.
Clauses are split on `,` `;` `:` and the coordinators ` and ` / ` but ` / ` while `. Every other
requirement continues to be evaluated over the whole sentence — in particular the value and human
requirements are **not** clause-scoped, so this change cannot admit a sentence that reports no number.

The documented rationale for the veto — *"'response to treatment and incidence of cytokine release
syndrome' contains both"* — is preserved and pinned by test. It survives because that sentence
reports no value, not because the veto still fires. That is a weaker guarantee than before and is
declared here rather than discovered later.

## 3. Controls, every one verified by reading the stored text

The previous milestone's mandatory negative control was vacuous because it was chosen from a keyword
survey and never read. Every control below was read in full first.

**There is no whole-abstract planned-endpoint negative control available in this corpus.** All four
candidates surfaced by a future-tense scan of the 198 sealed AACR abstracts were read and all four
were rejected: `3997`, `4013` and `2552` are preclinical (they would be refused by `_NONHUMAN_TERMS`,
a clause this milestone does not touch, making them vacuous); `5389` and `CT071` are trial abstracts
that **do** report observed responses (`75% patients (3/4) achieved an SRI-4 response`;
`Three of the five pts (60%) achieved clinical responses`). AACR publishes presented results, so a
trial-in-progress abstract is not a natural inhabitant of this corpus.

The gate is sentence-scoped by construction, so the negative controls are sentences, drawn from
verified corpus text. This is a deviation from the instruction and the reason is recorded above.

### Positive controls

| id | sentence (abridged) | refused today at | predicted after |
|---|---|---|---|
| PR06-a | `13 patients (81%) achieved a CR, including the patient with CD19+ T ALL…` | `NO_EFFICACY_TERM` | **PASS** via change A |
| PR06-b | `10/16 evaluable pts as of August 28, 2013 have ongoing BM CR…` | `NO_EFFICACY_TERM` | **PASS** via changes A+B |
| LB-138 | `Pt 1 achieved a complete response (CR) and experienced Gr 3 fever…` | `NON_EFFICACY:cytokine release` | **STILL REFUSED**, at `NO_VALUE` |

**LB-138 is predicted not to pass.** Changes B and C each move it one clause further down the ladder,
and it then fails the quantified-result requirement, which this milestone does not touch. This is
declared in advance so that a failure to pass is a confirmed prediction and not a reason to weaken
`_VALUE` after seeing the result. Whether the standard should accept a categorical outcome with no
number is a real question and a separate milestone.

### Negative controls — each must remain refused

| id | sentence (abridged) | must be refused at |
|---|---|---|
| CT023-neg | `The primary endpoint was safety and the secondary endpoints were ORR, progression free survival (PFS), overall survival (OS)…` | `UNREPORTED` (it is refused at `NON_EFFICACY:safety` today — change C removes that veto, so this control is load-bearing) |
| 5389-neg-a | `Safety, pharmacokinetic/pharmacodynamic profiles, primary efficacy parameters … will be evaluated over 48 weeks.` | `UNREPORTED` |
| 5389-neg-b | `Primary efficacy endpoint is SLE Responder Index 4 (SRI-4) criteria.` | `UNREPORTED` |
| CT071-neg | `This primary objective is to determine the maximum tolerated dose …, and the key secondary objective is to investigate the anti-myeloma activity.` | `UNREPORTED` |
| doc-neg | `response to treatment and incidence of cytokine release syndrome` | refused (at `NO_VALUE`, per §2) |
| abbrev-neg | prose containing `CRS`, `CRP`, `across`, `increase` and no efficacy term | `NO_EFFICACY_TERM` |
| id-neg | `Abstract PR06: …` | must not gain an efficacy term from `PR` |

Corpus hashes of the control abstracts, pinned here: `5389`
`f9694fed86bcffa193a03ef08c805a87a5b867e8d9bea09fbfacc3032b372b5c`; `CT071`
`25745925e1a3184deab4986f22abb534e49d7c7dbaa78739ab02d99d5d2bb10e`.

## 4. Measurement, declared in advance

One replay of the sealed AACR corpus
(`/home/djmann/se_runs/acceptance_20260919_live/custody` + `/home/djmann/se_runs/aacr_probe5/source_index.yaml`),
compared against run `aacr_decoupled`:

| gate | `aacr_decoupled` baseline |
|---|---|
| `evidence.human_poc` | 40 |
| `target.expression` | 56 |
| `evidence.minimum_stage` | 638 |
| `identity.distinct_asset` | 775 |
| candidates / low-support | 2837 / 1409 |

**Predeclared outcomes.**

- A rise in `evidence.human_poc` is the intended effect. Every new PASS will be listed individually
  with its asset, its sentence, and its document — no aggregate count will be reported alone.
- `target.expression`, `evidence.minimum_stage`, `identity.distinct_asset` and the candidate count
  **must be unchanged**. Any movement is a coupling defect of the kind found at `0389edd`, and is
  reported as a defect rather than absorbed into the result.
- **Zero new false positives** is the acceptance bar. A new PASS on prose junk, markup, a preclinical
  result, or a planned endpoint is a stop condition: freeze and report before remediating.
- If change B produces false positives that changes A and C do not, change B is reverted alone.
- `human_poc` staying at 40 is a permitted outcome and is a true negative, not a failure. No term
  list, threshold or character limit is to be adjusted after seeing the number.

## 5. Not to be done during this milestone

Relaxing `_VALUE`; relaxing sentence-scoped attribution; adding `PR`, `ORR`, `MRD` or any further
abbreviation; touching the determinism harness; remediating the 126 known junk candidates.
