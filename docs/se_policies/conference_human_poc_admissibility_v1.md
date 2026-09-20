# Policy: conference-abstract admissibility for `human_poc_present` — v1

**Status:** PREREGISTERED — written and hashed before the delta was run.
**Date:** 2026-09-20
**Applies to:** `document_type` in {`conference_abstract`, `conference_abstract_metadata`}
**Supersedes:** the blanket exclusion in `bve/se/evidence/source_capability.py`, introduced
at the AACR milestone as an explicitly temporary, revisitable position.

---

## 1. The finding that shapes this policy

**The admissibility rule specified for this milestone already exists and is already enforced,
on every source, by `bve/se/evidence/human_poc.py`.** Each of the six required conditions and
each of the seven required exclusions maps to a construct that is already in the code and
already applied to PubMed and press releases.

The only thing preventing a conference abstract from satisfying that standard is a single
predicate, `may_establish_human_poc(document_type)`, consulted in the pipeline's `HUMAN_POC`
stage before a document's text is read.

This matters for what the milestone *is*. It is not "write a rule for conference abstracts."
Writing a second, parallel rule would create two definitions of human proof-of-concept — the
same error as giving one kind of document two type names — and the second definition would
inevitably drift from the first. The milestone is therefore: **preregister the existing
standard, remove the source exclusion, and measure whether the standard does the work
unassisted.**

That framing is also the one that makes the result falsifiable. If the existing standard
admits something it should not, that is a defect in the standard on *all* sources, not a
conference-specific leniency — and it is better found here than left unexamined.

## 2. The rule, and where each clause is enforced

A conference abstract may establish `human_poc_present = true` only when a **single sentence**
satisfies every condition below. Sentence scoping is itself a substantive requirement: an
abstract naming an asset in one sentence and a response rate in another has not said the
second is about the first.

| # | Required condition | Enforced by | Location |
|---|---|---|---|
| 1 | Human patients were actually treated or exposed | `_HUMAN_TERMS` must match | `efficacy_statements` |
| 2 | The result is attributable to the named asset | asset name must appear in the same sentence, matched longest-first | `efficacy_statements` |
| 3 | An **observed** outcome, not a planned endpoint | `_UNREPORTED_TERMS` must **not** match, **and** a reported quantity `_VALUE` must be present | `efficacy_statements` |
| 4 | The outcome is disease-relevant clinical evidence | `_EFFICACY_TERMS` must match (CR/PR/ORR, remission, disease activity, PFS/OS, clinical benefit…) | `_EFFICACY_TERMS` |
| 5 | Enough context to identify population and result | sentence ≤ 400 chars, and conditions 1–4 hold within it | `_MAX_SENTENCE_CHARS` |
| 6 | Combination efficacy is not transferred to a component | `_reports_a_regimen` — a coordinator adjacent to the asset's own name, or another asset named in the same sentence | `_reports_a_regimen` |

### Must remain UNKNOWN

| Case | Enforced by |
|---|---|
| protocol / design abstracts | `_UNREPORTED_TERMS` (`will be`, `is planned`, `to assess`, `we will`) |
| "ORR/PFS/OS **were** endpoints" | `_UNREPORTED_TERMS` (`primary endpoint was`, `primary outcome was`, `secondary endpoint`, `outcome measure`) |
| "efficacy will be evaluated" | `_UNREPORTED_TERMS` |
| safety / PK-only reports | `_NON_EFFICACY_TERMS` (`safety`, `adverse event`, `pharmacokinetic`, `dose-limiting`, `cytokine release`) |
| biomarker / correlative studies | `_NON_EFFICACY_TERMS` (`biomarker`, `expansion`, `persistence`) |
| sponsor adjectives | `_UNREPORTED_TERMS` (`promising`, `potential to`, `may improve`, `warrant`) |
| animal / in-vitro efficacy | `_NONHUMAN_TERMS` (`mice`, `murine`, `xenograft`, `in vitro`, `cell line`, `preclinical`) |
| eligibility prose written in results vocabulary | `_ELIGIBILITY_TERMS` |

### An additional gate, not part of this policy but load-bearing

A `human_poc_present` fact is produced only for an asset that has independently passed
`qualifies_as_asset`. **A conference mention alone does not qualify a name as an asset.** So
"conference source alone is not sufficient" holds by construction, through the identity layer,
and is not something this policy needs to add.

## 3. The change being made

One change, in one place: remove `conference_abstract` and `conference_abstract_metadata` from
`NON_DECISIONAL_FOR_HUMAN_POC` in `bve/se/evidence/source_capability.py`.

Explicitly **not** changed: the AACR connector, the identity layer, target logic, `SourceTier`,
any global evidence threshold, and the definition of `human_poc_present` itself.

## 4. Frozen controls

Declared before the delta. Each is to be **verified against the actual abstract text**, not
assumed from the earlier manual survey.

### Mandatory negative control

- **CT023** — "The primary endpoint was safety and the secondary endpoints were ORR,
  progression free survival (PFS), overall survival (OS)…". Endpoints named, no result
  reported. **Must remain UNKNOWN.** If CT023 passes, the milestone fails and the exclusion
  is restored.

### Additional negative controls

- **1440**, **LB110** — correlative / biomarker studies. Must remain UNKNOWN.
- Any abstract whose only efficacy language is preclinical. Must remain UNKNOWN.

### Candidate positive controls

Listed as *candidates* because the survey that found them was a keyword scan, not the
standard. It is an expected and acceptable outcome that some do not pass.

- **PR06** — CTL019, complete responses in pediatric ALL.
- **CT007** — CD19/CD20 bispecific CAR, patients in ongoing complete remission.
- **LB-138** — autologous anti-CD19 CAR, "Pt 1 achieved a complete response (CR)".

### Predeclared expectations, so that being wrong is visible

Two clauses of the existing standard are likely to refuse some of the candidates above, and
saying so now prevents the result being rationalised afterwards:

- `_VALUE` requires a reported quantity (`%`, `n of m`, `n=`). CT007's "4 of patients in
  ongoing complete remission" is malformed in the source and may not match.
- `_reports_a_regimen` refuses a sentence naming another asset. CAR-T abstracts frequently
  name the lymphodepletion regimen alongside the construct.

**Predeclared:** if fewer than the three candidates pass, that is a true negative of the
standard, not a shortfall to be fixed by loosening it. **No threshold, term list, or character
limit is to be altered after the output is seen.**

## 5. Success criterion

Adopt conference abstracts as an admissible human-PoC source class **only if**:

1. CT023 remains UNKNOWN; and
2. every new `human_poc_present` PASS is verified, by reading the cited sentence, to report an
   observed human clinical outcome attributable to the named asset; and
3. `target.expression` and every other evidence gate are unchanged.

Any false positive → restore the exclusion and report the defect.

## 6. Hashes of the frozen standard

Recorded so that any later change to the standard is detectable.

```
policy_version              = conference_human_poc_admissibility_v1
extractor_version           = human_poc_v1
human_poc.py        sha256  = cd8d963c5ff18da54f58aebcb9bf140f5d54c83c2bafe8924af9d254f703958a
source_capability.py sha256 = 4b06ad2e94291d19f1d4d8f4b22368c1b52f8e6ee69633ca645c3a9832bc3c9c
```

`source_capability.py` is expected to change — that is the single edit this milestone makes.
`human_poc.py` **must not change**; its hash is the preregistration.
