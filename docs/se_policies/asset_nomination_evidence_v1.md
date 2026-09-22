# Preregistration — a prose token is not an asset without positive evidence (v1)

Written and committed **before** any code change and before any measurement, 2026-09-22.

Baseline: `frag_control` / `frag_live2`, the two same-day live acquisitions that adopted
[multi_token_drug_name_identity_v1.md](multi_token_drug_name_identity_v1.md). Fragmentation is
frozen as adopted and is not touched here.

Scope: **nomination and qualification only.** Ranking is not altered. Target rules and human-PoC
rules are not weakened. No hand-written blacklist of the offending words is added.

---

## 1. The defect

The shortlist a reader sees is headed by `frontline`, `bsAbs`, `Placebo`, `cornerstone`, `safer`,
`refine`. These are not assets. They are ordinary English, a class abbreviation, and a control
arm, each minted as a `CanonicalAsset` and each occupying a row a real answer could have had.

## 2. Route audit — measured before the rule was written

Which route mints each? Probed directly against the frozen artifacts.

| token | dev-code | stem rule | ontology name | shape model | shape score |
|---|---|---|---|---|---|
| `frontline` | no | no | **yes** | yes | 1.113 |
| `safer` | no | no | no | **yes** | 0.470 |
| `cornerstone` | no | **yes** | no | yes | 0.511 |
| `refine` | no | no | no | **yes** | 0.735 |
| `bsAbs` | no | no | no | **yes** | 1.435 |
| `Placebo` | no | no | no | no | −0.255 |
| `choice` | no | no | **yes** | no | −0.675 |
| `discase` | no | no | **yes** | no | −1.007 |
| `benzhexol` | no | no | no | **yes** | 1.441 |
| `ibritumomab` | no | **yes** | no | yes | 1.182 |
| `lestaurinib` | no | **yes** | no | yes | 0.898 |

Four facts follow, and each one kills an otherwise obvious fix.

**(a) The ontology is itself contaminated.** `frontline`, `choice` and `discase` are *real
molecule names* in the snapshot — `FRONTLINE` is a veterinary product. "Ontology identity" cannot
be treated as sufficient positive evidence on its own.

**(b) The shape score cannot be thresholded.** `bsAbs` scores **1.435**; `lestaurinib`, a real
drug, scores **0.898**. Junk spans 0.47–1.44 and real spans 0.89–1.44. There is no cut that
separates them, so no amount of threshold tuning is a fix — which is also why this policy forbids
touching the threshold. It would not work and would only fit the corpus.

**(c) The shape model is simultaneously the junk source and the only route that reaches hard real
assets.** `benzhexol` and `busulfan` are nominated by no other route. Disabling the shape route
would remove the milestone's own retain-controls. It must be constrained, not removed.

**(d) `Placebo` is structurally declared.** It is not prose at all: `structurally_typed_drug=True`,
**35 trials, 30 companies**, from ClinicalTrials.gov intervention fields typed `DRUG`. Structured
DRUG declaration therefore cannot be sufficient evidence either — the registry really does declare
placebo as an intervention.

### The finding that decides the rule

Structural corroboration does not separate real from junk either:

| candidate | typed | trials | companies | provisional |
|---|---|---|---|---|
| `frontline` | False | 0 | 0 | True |
| `safer` | False | 0 | 0 | True |
| `cornerstone` | False | 0 | 0 | True |
| **`gemcitabine`** | False | 0 | 0 | True |
| **`pomalidomide`** | False | 0 | 0 | True |

`gemcitabine` and `pomalidomide` are unambiguously real drugs and are **structurally identical to
the junk on every field**. A rule requiring trials, companies or structured typing would delete
them. So would requiring non-provisional status.

What does separate them is *how the corpus uses the token*:

| token | characteristic frames observed |
|---|---|
| `frontline` | `frontline setting`, `frontline trials`, `frontline chemotherapy` — attributive modifier |
| `safer` | `effective and safer`, `potentially safer option` — predicate adjective |
| `cornerstone` | `the cornerstone of` (every occurrence) |
| `bsAbs` | `antibodies (bsAbs)` (every occurrence) — a parenthetical gloss of the preceding class term |
| `gemcitabine` | `Combined with gemcitabine and Cisplatin`, `Rituximab, gemcitabine, and`, `courses of gemcitabine` |
| `pomalidomide` | `treated with pomalidomide`, `combined with pomalidomide`, `belantamab mafodotin, pomalidomide, and` |

Real drugs occur in **administration and coordination frames**. Ordinary words occur as
modifiers, predicates, and glosses. This is the "asset-specific pharmacologic naming context"
the milestone is built on.

## 3. The rule

**A token nominated by prose shape alone is not an asset until something independent says it
denotes a therapeutic.** Qualification is positive: a candidate is admitted when it carries at
least one *qualifying evidence* below, and is otherwise routed to review rather than deleted.

Qualifying evidence, declared now and in priority order:

1. **Development-code structure** — `_ASSET_CODE_RE` (e.g. `ABBV-383`, `AMG 420`). Unchanged.
2. **Structured DRUG declaration** in a registry intervention field, *excluding* the
   comparator/control role (see §3.1).
3. **Ontology identity that is drug-bearing** — a molecule record, not a bare name match. A name
   present only as a trade name with no development or target evidence does not qualify
   (`FRONTLINE`).
4. **A multi-token ontology molecule** — every name repaired by the adopted fragmentation rule
   qualifies by construction.
5. **Administration or coordination context** — the token appears in a pharmacologic frame:
   administered (`treated with`, `received`, `courses of`, `doses of`), combined (`plus`,
   `combined with`, `in combination with`), or coordinated in a list with an *already-qualified*
   asset. Corroboration must come from **at least two independent source documents**, so a single
   unlucky sentence cannot qualify a word.

Not qualifying, stated explicitly: frequency; shape score magnitude; occurring in an abstract that
also contains efficacy evidence; occurring near a target name; being a bare ontology string.

### 3.1 Placebo and class terms

`Placebo` is real information and is not discarded — it is **role-typed as a comparator**, not
minted as a canonical therapeutic asset, and is excluded from the answer population rather than
from the record. Class abbreviations glossed parenthetically from a preceding class term
(`bispecific antibodies (bsAbs)`) are **class terms, not assets**, and are likewise not canonical
assets. Neither is handled by naming the strings.

## 4. Controls, frozen now

**Negative — must NOT be canonical assets after the change.** The first six were named by the
requester; the rest were observed in `frag_live2`'s PASS population before this rule was written.

`frontline`, `safer`, `cornerstone`, `refine`, `Placebo`, `bsAbs`, `choice`, `though`, `discase`,
`POD24`, `Novel`, `although`, `total`, `evaluate`, `suggest`, `first`, `their`, `months`, `safety`

**Positive — must REMAIN assets.** Deleting any one of these is a milestone failure.

| control | why it is hard |
|---|---|
| `benzhexol` | ontology-missing; shape route only; no trials, no companies |
| `ibritumomab` | ontology-missing; stem + shape |
| `lestaurinib` | shape score 0.898 — *below* `bsAbs`, which must die |
| `gemcitabine`, `pomalidomide` | real drugs structurally identical to the junk |
| `ABBV-383`, `AMG 420`, `ALLO-715` | development codes, 1 mention each, no structured typing |
| `busulfan` | nominated by no stem rule |
| `belantamab mafodotin`, `idecabtagene vicleucel`, `ciltacabtagene autoleucel` | newly repaired multi-token names |
| `teclistamab`, `elranatamab`, `talquetamab`, `blinatumomab` | structured, target-confirmed |

`benzhexol`, `ibritumomab` and `lestaurinib` are **absent from this corpus**, so they are unit
controls on the qualification function, not corpus controls. Stated now so their absence from a
run is not later read as a pass.

### Contamination disclosure

The negative controls beyond the requester's six were read off `frag_live2`, a member of the same
corpus family the change will be measured on. This is declared rather than hidden. Mitigations:
the rule is a structural principle, not a list of these strings; the six headline negatives and
all three hard positives were specified by the requester, not chosen by me; and no threshold is
tuned. A rule that only removes the enumerated strings fails §6 by construction.

## 5. What counts as a lost legitimate asset

A **loss** is any candidate that (a) was a canonical asset before, (b) is not one after, and
(c) is a real therapeutic agent, judged by reading its mentions — not by whether it passed a gate.

Per the fragmentation milestone's lesson, raw lost/gained totals between two live acquisitions are
dominated by drift. Losses are therefore classified by qualifying evidence and **enumerated
individually**, never counted.

Conversely, a junk candidate that *stops* being an asset is the intended effect and is not a loss
however many there are.

## 6. Acceptance bar, fixed now

Validation is a **fresh live acquisition** with only this change active, compared against a
control run from this milestone's parent commit, same day, same source index. Sealed replay is
not admissible: this change is upstream of discovery. Both runs must show **0 divergent
attempts** or the comparison is void.

1. Every negative control in §4 ceases to be a canonical asset.
2. Every positive control in §4 remains one, the three unit controls included.
3. No real asset lost — every loss enumerated and read individually.
4. `target.expression` unchanged except where a deleted false asset carried an assertion; any
   other movement is a failure.
5. No real human-PoC evidence lost. False human-PoC attributions to non-assets removed. Both
   reported by membership, not by count.
6. **The removal generalizes**: the junk removed must substantially exceed the enumerated negative
   controls. Removing only the listed strings is a blacklist wearing a rule's clothes and fails.
7. Top-10 shortlist reported before and after.
8. **Every candidate receiving a decisional PASS that is not a real asset is enumerated by name**,
   before and after.

Ranking is untouched throughout. Shortlist ordering is the *next* milestone and only becomes
worth doing if the population is predominantly real after this one.

## 7. Not to be done

Hand-listing `frontline`, `safer`, `cornerstone`, `refine` or any offending string; tuning the
shape-model threshold or retraining it; lowering or raising the stem threshold; weakening target
or human-PoC rules; altering ranking or ordering; touching the adopted fragmentation rule;
deleting candidates outright where routing to review preserves the information.

---

## 8. Amendments, made before measurement

### 8a — NARROWING: ontology membership is never an automatic pass (2026-09-22)

§3 item 3 said ontology identity qualifies when it is "a molecule record, not a bare name match",
and glossed `FRONTLINE` as not qualifying. **That gloss was wrong.** `FRONTLINE` *is* a real ChEMBL
record, so as written the rule would have admitted `frontline` — the very control it must remove.
Corrected here before any code or measurement.

What the snapshot can actually distinguish, measured:

`frontline`, `choice` and `discase` are **not canonical records at all**. Each enters solely as a
`TRADE_NAME` alias of a *different* molecule:

| name | alias types | resolves to |
|---|---|---|
| `frontline` | TRADE_NAME only | FIPRONIL — a veterinary insecticide |
| `choice` | TRADE_NAME only | WARFARIN |
| `discase` | TRADE_NAME only | CHYMOPAPAIN |
| `busulfan` | CANONICAL_SYMBOL, APPROVED_NAME, SYNONYM, TRADE_NAME, XREF | itself |

Treating `frontline` as an asset is therefore an **identity error**, not merely weak evidence.

Of 40 ordinary English words probed against the snapshot, **`TRADE_NAME` is the only alias type
that admits any, and it admits exactly these three**. `CANONICAL_SYMBOL`, `APPROVED_NAME`,
`SYNONYM` and `DEVELOPMENT_CODE` admit none. The narrowing is a property of the alias types, not a
fit to the three offenders.

Excluding TRADE_NAME-only names outright is **not** the fix, and the check that shows why is worth
recording: real trade names are TRADE_NAME-only too — `Keytruda`→PEMBROLIZUMAB,
`Revlimid`→LENALIDOMIDE, `Carvykti`→CILTACABTAGENE AUTOLEUCEL, `Abecma`→IDECABTAGENE VICLEUCEL.
Parent-realness does not separate them either: FIPRONIL and WARFARIN are real molecules.

§3 item 3 is replaced by:

> **3. Ontology evidence, in two kinds, neither of them a bare name match.**
>
> **3a — identity-bearing membership qualifies.** The name is reachable as a `CANONICAL_SYMBOL`,
> `APPROVED_NAME`, `SYNONYM` or `DEVELOPMENT_CODE`. These admit no ordinary vocabulary.
>
> **3b — a mechanism-of-action edge qualifies.** The molecule carries a `DIRECT_TARGET` edge to a
> target. Sufficient, **never necessary**: `gemcitabine` 16, `teclistamab` 6, `pomalidomide` 5,
> `busulfan` 1, against 0 for `frontline`, `choice`, `discase` and `Placebo` — but also **0 for
> `benzhexol`, `lestaurinib` and `ibritumomab`**, which are protected positive controls and are
> absent from the ontology entirely. Requiring an edge would delete them.
>
> **3c — a TRADE_NAME-only name confers identity, never qualification.** It is an alias of its
> parent, not an asset of its own, and is resolved to that parent. The parent must then earn
> qualification independently **from those same mentions**. This is one rule doing both jobs:
> `Keytruda`'s occurrences are administration frames (`treated with`, `plus chemotherapy`), so
> PEMBROLIZUMAB qualifies under §3 item 5; `frontline`'s occurrences are attributive (`frontline
> setting`), are not mentions of fipronil in any sense, and so qualify nothing.

The ontology therefore contributes **which molecule a name denotes**, and — except via 3a/3b —
not **whether the thing is an asset**. That question is settled by usage.

Alias binding must not launder junk: resolving `frontline`→FIPRONIL must not mint FIPRONIL as an
asset. **`FIPRONIL` is added to the negative controls** — if it appears as a canonical asset after
the change, the amendment has failed and made the defect harder to see rather than removing it.

This amendment is a **narrowing**: it removes an automatic pass the policy previously granted. It
adds no new qualifying route.

### Hash

The v1 hash `342dc2bc4dcfba43d7028a0312a31e43a901b13d70897b86a8096f3dbd6c8dd7` covers the text as
first committed (`8e5e105`). This amendment supersedes §3 item 3; the superseding hash is recorded
in the commit that adds this section, and both remain in the log.

### 8b — NARROWING: prose qualifies only in argument position (2026-09-22)

§3 item 5 named "administration or coordination context" but delegated the detail to the existing
`has_pharmacologic_context` patterns. Measuring which pattern actually fires for each negative
control shows the patterns are the defect, so the rule is made explicit here before any change.

**A single pattern mints all of the prose-route junk:**

```
{name}\s+(?:monotherapy|therapy|treatment|infusion|injection|tablets?|capsules?)
```

`safer therapy` (3 docs), `cornerstone treatment` (1), `refine treatment` (4), `bsAbs therapy` (3),
`though treatment` (2), `frontline therapy` (**48**). The left-hand patterns leak identically:
`treated with frontline` and `receiving frontline` are `treated with frontline chemotherapy` — the
object of the preposition is the phrase, whose head is `chemotherapy`, not `frontline`.

In every one of these the name is a **modifier of a following head noun**, a slot English grants to
any adjective. `asset_qualification`'s own docstring already states this principle for
`_CONTEXT_HEAD` — "read only when the name is the *head* of the phrase, so a qualifier in front of
it does not lend it the noun's authority" — and `_CONTEXT_RIGHT` breaks it.

**The corpus frequency ceiling cannot be the backstop, and this is why the rule must be syntactic.**
Measured over the 5,629-document corpus (ceiling = 5% = 281 documents):

| junk | df | real | df |
|---|---|---|---|
| `bsAbs` | 48 | **`gemcitabine`** | **30** |
| `safer` | 39 | `pomalidomide` | 58 |
| `cornerstone` | 34 | `busulfan` | 59 |
| `refine` | 29 | `teclistamab` | 94 |

`gemcitabine` is **rarer than `cornerstone`**. `MAX_DOCUMENT_FRACTION` catches only the very
commonest words (`total` 1557, `months` 2283, `safety` 2493, `novel` 701, `although` 499) and
nothing in the mid-frequency band where both the junk and the real drugs live. Any ceiling low
enough to veto `cornerstone` deletes `gemcitabine`. **The ceiling is not raised or tuned.** This is
the fifth candidate fix the audit has disproved, after ontology identity, shape score, structured
declaration and structural corroboration.

§3 item 5 is replaced by:

> **5. Pharmacologic use, counted only in argument position.** An occurrence qualifies when the
> name fills a slot only a noun can fill: object of an administration verb or preposition
> (`treated with X`, `received X`, `doses of X`), subject of a pharmacologic predicate (`X is a
> selective inhibitor`, `X was administered`), or bearing a dose (`X 1000 mg`).
>
> An occurrence in which the name **immediately precedes a pharmacologic head noun it modifies**
> — `therapy`, `treatment`, `monotherapy`, `chemotherapy`, `regimen`, `setting`, `agent`, `option`,
> `approach`, `strategy`, `care`, `line`, `arm`, `cohort` — is **modifier position and qualifies
> nothing**, whatever precedes it. This veto is per-occurrence and applies to real drugs too:
> `Pomalidomide capsules` and `Gemcitabine Injection` earn nothing, and those molecules qualify
> instead through `treatment with pomalidomide` and `gemcitabine 1000mg`, which is the intended
> behaviour rather than a concession.
>
> Qualification requires such an occurrence in **≥2 independent documents**, as already frozen.

Predicted effect, recorded before measuring: `frontline`, `safer`, `cornerstone`, `refine`,
`though` lose every qualifying occurrence; `bsAbs` retains one (`treated with bsAbs`, 1 document)
and so fails the two-document requirement rather than the position rule. If `bsAbs` survives, the
two-document rule is not being applied.

This is a **narrowing**: it removes qualifying occurrences and adds none.
