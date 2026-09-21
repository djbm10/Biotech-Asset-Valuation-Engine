# S&E acceptance log

Real-world failures found by asking the engine real BD questions, newest first. This is
not a benchmark: there is no denominator, no score and no target list. An entry earns its
place by being something a user hit, and it stays open until a user would not hit it again.

The rule for acting on an entry: fix it when a real query exposed it, not because it is
listed. Silent misreads outrank refusals, because a refusal tells the user something is
wrong and a misread does not.

## 2026-09-19 — human_poc_present: the evidence floor can now decide, and says no

The acceptance query states two scientific constraints. The first was closed yesterday.
The second, `human_poc_required`, compiled correctly and then decided nothing: the gate
asked for a `human_poc_present` fact and no producer emitted one, so all 1,921 evaluated
candidates sat at UNKNOWN. The compiler and the gate were right; the missing capability was
evidence production.

`bve.se.evidence.human_poc` now answers it from two routes that mean the same thing: a
structured clinical result whose endpoint measures benefit and whose value was actually
reported, and a sentence in a document the asset was seen in that reports one. Everything
that is merely true of a clinical-stage asset produces nothing — a trial, a phase, a
tolerated dose, an exposure curve, a biomarker movement, a protocol endpoint with no value.

**Replayed from run C's sealed corpus** (`acceptance_20260919_poc`, same bytes, same query,
no added modality):

| decision | before | after |
| --- | --- | --- |
| `evidence.human_poc` PASS | 0 | 81 |
| `evidence.human_poc` FAIL | 0 | 0 |
| `evidence.human_poc` UNKNOWN | 1,921 | 1,840 |
| `target.expression` PASS / FAIL / UNKNOWN | 53 / 582 / 1,286 | unchanged |

**Assets satisfying both constraints: zero.** The cross-tab is the finding: of the 53
assets whose construct is documented to hit both CD19 and BCMA, *not one* has an admissible
human efficacy result in this corpus; and of the 81 with human efficacy, 22 are documented
single-target assets that the dual gate correctly excludes and 59 have no construct
evidence at all. No single-target or safety-only asset satisfies the query. Eligible remains
0 — now for a defensible reason rather than for want of a producer.

Zero FAILs is deliberate. Nothing in this corpus reports a human efficacy *failure* the
contract can represent conservatively, and UNKNOWN sends an asset to review rather than
excluding it for evidence nobody published.

**What the citations show.** All 83 facts came from the prose route; the structured route
produced nothing because the CT.gov corpus has no posted results at all (every
`ClinicalResult` is a protocol endpoint, correctly `incomplete_reporting`). The sentences
themselves are right — obexelimab's flare rates, ICG318's 10-of-12 sCR in refractory SLE,
FELIX's 77% remission, teclistamab, glofitamab, talquetamab, elranatamab, blinatumomab.

**The new binding constraint is upstream, and this is the first stage to expose it loudly.**
Roughly fifty of the 81 passing "assets" are not assets: `although`, `before`, `months`,
`baseline`, `Euroflow`, `IQR 72`. Every one genuinely appears in a sentence reporting
efficacy — because the name is an ordinary English word. The efficacy layer attributed
correctly to the name identity gave it. Mention precision was already known to be the weak
layer (M17: ~55% false accepts); it had never before been handed a decisional PASS. Fixing
it belongs in identity, not here.

**Two defects this run caught that the suite could not**, both consistent with the lesson
from `construct_target_set`:

- On the live corpus the prose route's *only* match was a registry eligibility block
  — "inadequate response to at least one immunomodulatory therapy" — written in exactly the
  vocabulary of a result. Registry records now speak only through their structured outcome
  measures, and eligibility phrasing and multi-thousand-character concatenated fields are
  excluded outright.
- The stage crashed on the first replay: two documents reporting the same sentence collapsed
  to one claim id with two different source documents behind it, which the ledger refused. A
  claim is a statement by a source, not a string.

Still open, unchanged and deliberately not special-cased: `CD19 or CD19-BCMA CAR-T` passes
the dual gate though an arm offering a *choice* between a single-target and a dual product
is not a dual asset.

## 2026-09-18 — construct_target_set: giving the dual gate something to decide on

The previous entry left `target_logic` compiled, carried and evaluated — and deciding
nothing, because no producer in the pipeline ever emitted a `construct_target_set` fact.
1,919 UNKNOWNs is not a gate bug; it is a missing fact. This entry is the fact.

**What a construct target set is, and what it is not.** It is the set of targets supported
as belonging to *one molecular construct*. It is deliberately not: the targets a trial was
retrieved for, the targets co-occurring in a document, the union of a regimen's partners,
the targets the buyer asked for, or the targets named in protocol-level prose. A trial
comparing a CD19 CAR-T against a BCMA CAR-T names both targets on every arm, and the
previous producer attributed both to both molecules — which is exactly the false positive a
dual-target question is least able to survive.

**Two admissible routes, and no third.**
1. *Per-asset direct mechanism evidence.* `CandidateTargetAssertion` already carried
   confirmed, per-asset, DIRECT target edges from the M10D authority, with provenance. The
   set is derived from those — no parallel truth system. `FAMILY_OR_COMPLEX_ASSOCIATION`
   evidence stays non-decisional, and an asset with any unanswered assertion yields no fact
   at all rather than a partial one.
2. *The intervention record's own fields.* Registry sponsors write structured product
   descriptions ("CD19-directed CD3 bispecific T-cell engager"), which is a statement about
   one product. Only `name`, `description` and `otherNames` are read — never the protocol —
   and declared combination products and multi-molecule names return nothing.

When both speak, the authority supersedes; the superseded claim stays in the ledger.
Document co-occurrence was not deleted, it was demoted to `document_target_context`, which
no gate reads.

**Two defects surfaced while proving it.** The gate compared bare approved symbols (`CD19`)
against canonical ids (`TARGET:CD19`) as raw strings, so a *correct* set still failed the
subset test; both sides now normalize. And entailment demanded the literal canonical id
appear in the cited passage, which no source ever writes — the citation now counts any
ontology-recognized spelling.

Twenty-seven red-first tests, including the ones that matter most: two co-administered
single-target drugs do not become one dual construct, silence is not denial, and the module
source contains no target identifier at all, so nothing here is special-cased to CD19.

**Judged on the live re-run** (`se:ff17949b`, code `ab16296`, same question, same
as-of, no modality added). `target_logic` went from 1,919 UNKNOWN and nothing decided to
**53 PASS, 582 FAIL, 1,286 UNKNOWN**. No single-target asset satisfies the dual
requirement: 314 assets carry a CD19-only set and every one is excluded. The passing
names are the ones the question was about -- AZD0120, GC012F, ARI0003, FKC289,
`CD19/BCMA Lupus Nephritis Targeted CAR T-cells`, `anti-CD19/BCMA CAR NK cells`.

**Two defects only the live corpus could show, both since fixed.** The first corrected
run produced construct sets of 50, 92 and 119 targets, because the route read the right
text and then matched it with the ontology's *substring* index -- `ar` and `si` live
inside "radiotherapy" and "infusion". All three assets passing the dual gate in that run
passed on such a set, every one a single-target CD19 CAR-T: a junk set large enough will
contain both halves of any conjunction. Targets are now read as whole symbol-shaped
tokens anchored to an attributive cue, and sets top out at four members.

The second run then failed in both directions at once. Regimens still passed --
"Autologous BCMA CAR-T cells and CD19 CAR-T cells", "BCMA CART + CD19 CART" -- and real
duals were excluded, because "CD19-BCMA dual nanobody based CAR-T" stopped at the first
symbol that resolved. A coordinated name now yields nothing when the product noun is
repeated on both sides, while "anti-CD19 and anti-BCMA CAR" stays one construct because
the noun appears once and is shared. And `T` is a real gene symbol, so every "CAR T cell"
in the corpus had been asserting TBXT.

**Still open.** `CD19 or CD19-BCMA CAR-T` passes, and an arm offering a choice between a
single-target and a dual product is not a dual asset. Source coverage is unchanged at 2
of 9 connectors, so the run is honestly INCOMPLETE. Eligibility is still 0 because
`human_poc` is unbuilt, and the shortlist's top rows are junk mentions -- `safety`,
`months`, `first` -- which is now the most visible weakness a user would hit.


## 2026-09-18 — the live BCMA acceptance run, judged

Query, verbatim: *"Find clinical-stage dual CD19/BCMA therapies for autoimmune disease with
human efficacy."* Run `se:522b718a`, code `d2779c2`, as-of 2026-09-17, 71 minutes,
`--therapeutic-area AUTOIMMUNE` supplied to answer the disease-class clarification.
Reproducible from `reproduce.sh` in the run directory.

**The question compiled and every phrase had a visible fate.** `residual_terms` was empty.
`dual` → TARGET_LOGIC ALL, `clinical-stage` → minimum_stage, `human efficacy` →
human_poc_required, both targets resolved, `autoimmune disease` escalated and then answered
by the supplied area. The acceptance rule from the second pass held end to end.

**The modality change worked on live data.** No modality was named, and the gate engine
emitted **zero** `modality_technology` decisions across 1,919 evaluated candidates — not a
gate that passed everything, no gate. The corpus contains monoclonal antibodies, ADCs,
CAR-T and T-cell engagers precisely because nothing narrowed it.

### The shortlist does not answer the question that was asked

Top ten, all `[REVIEW]`: inebilizumab, obexelimab, denintuzumab, AUCATZYL, MONJUVI,
Uplizna, Zynlonta, inotuzumab, "choice", daratumumab.

**Not one is a dual CD19/BCMA asset.** Seven are single-target CD19. Inotuzumab is CD22,
daratumumab is CD38, and "choice" is not a molecule at all — it is a junk mention promoted
to a candidate, the known mention-precision weakness showing up in the first ten rows of a
user-facing list.

The cause is not the compiler. `target_logic` produced 1,919 decisions and **every one was
UNKNOWN**, because the corpus yielded **zero** `construct_target_set` facts. The conjunction
is compiled, carried into the contract, and evaluated — and then decides nothing, so every
asset routes to review and the display order is whatever was declared. A CD19-only asset
FAILs the dual gate in tests, where the fact exists; in the live corpus the fact never
exists, so it does not fail, it defers.

This is the same shape as the `human_poc_required` limit recorded in the second pass, and
now measured: of the six phrases, only two actually *decide* anything on live data.

| phrase | compiled | facts available | decides? |
|---|---|---|---|
| `clinical-stage` | `minimum_stage=PHASE_1` | 1,755 `development_stage_order` | **yes** |
| `autoimmune disease` (via flag) | `therapeutic_areas` | 1,343 `therapeutic_area` | **yes** — the only gate that excluded anything (577) |
| `dual` | `TargetOperator.ALL` | **0** `construct_target_set` | no — 1,919 UNKNOWN |
| `human efficacy` | `human_poc_required` | **0** `human_poc_present` | no — all review |
| `CD19`, `BCMA` | target expression | — | drove retrieval, not selection |

**Verdict: the acceptance rule passes, the acceptance *question* does not.** Nothing was
silently dropped and nothing claimed more than it did — every unsatisfied requirement is
named on every row. But a BD user who asked for dual CD19/BCMA assets is handed seven
single-target CD19 antibodies and a CD38 myeloma drug, in a declared order, with no ranking
and nothing eligible. Honest, and not yet useful.

### What this run says to do next, in order

1. **Emit `construct_target_set`.** It is the single highest-value missing fact: without it
   the target expression — the core of almost every BD question — cannot decide anything,
   and multi-target questions degrade into single-target retrieval wearing the right label.
2. **Mention precision.** "choice" at rank 9 of a user-facing list is the cheapest possible
   demonstration that the nomination layer is the weakest one.
3. **`human_poc_present`** has no producer. Until it does, "with human efficacy" means
   "every asset needs review on this point", and the shortlist should probably say so in
   those words.
4. Source coverage was **INCOMPLETE and said so**: 7 of 9 connectors are NOT_CONFIGURED
   (SEC EDGAR, company pipeline/press release, AACR/ASCO/ASH/EHA), and the blind spots are
   named per source. Only CT.gov (1,577 docs) and PubMed (2,123 docs) contributed.

## 2026-09-18 — third pass: the question was refused for naming no modality

### FIXED — "therapies" was treated as a missing modality rather than a wider question

The live acceptance query — *"Find clinical-stage dual CD19/BCMA therapies for autoimmune
disease with human efficacy."* — did not run. Every scientific phrase in it compiled or was
escalated by name, exactly as the second-pass rule requires, and then the run was refused
with `no modality recognized in the query`.

That refusal was wrong in a way the rule did not cover. A BD user writing *therapies* is
deliberately declining to narrow: CAR-T, bispecific, anything that hits both targets. The
engine treated the absence as an omission to be corrected and made the user supply a
modality — so the run that eventually happened answered a **narrower** question under the
original's name. The second-pass rule guards against a run looking more capable than it
was; this was the mirror image, a run looking like the question it was not.

Naming no modality is now valid and means exactly one thing: **no modality gate**, search
across every supported modality. `StrategicGap.modalities` may be empty, and the gate engine
emits no modality requirement at all for it rather than an `IN []` that every asset would
fail. Generic nouns — `therapy`, `therapies`, `program`, `asset`, `drug` — resolve to no
modality and never infer one. A question that does name a modality is untouched, gate for
gate.

Because an absent gate is invisible in a list of present ones, every run now prints what it
will actually gate on, absences included: `modality constraint: none`.

### FIXED — `dual` was residual, and the conjunction it states was only ever inferred

`dual` landed in `residual_terms`. That looked survivable because the acceptance query's
target operator came out `ALL` anyway — but it came out `ALL` by *inference* from the `/`
between the targets, and the inference falls back to `ANY` on any connector it does not
recognize. `dual CD19, BCMA therapies` compiled to "either CD19 or BCMA", which returns
single-target assets under a dual-target heading. The word the user wrote decided nothing.

`dual` is now a `TARGET_LOGIC` span that *states* the conjunction, and a stated conjunction
beats the inference. The underlying contract needed nothing new: `TargetOperator.ALL` was
already `required.issubset(observed)` against the asset's own construct-level target set —
one molecule, both targets — and that is now pinned by tests that a CD19-only asset and a
BCMA-only asset each FAIL the dual query while an asset hitting both PASSes.

Where the stated conjunction cannot be compiled, it refuses rather than narrowing quietly:
`dual CD19` (one target named) and `dual CD19 or BCMA` (the question contradicting itself)
are both blockers that name `dual`.

### FIXED — the unenforceable-phrase warning did not notice being answered

Passing `--therapeutic-area AUTOIMMUNE --indication "systemic lupus erythematosus"` cleared
the `NEEDS_CLARIFICATION` blocker and the run proceeded, but the warning still read *"this
run will NOT apply [autoimmune disease] unless you state them with --therapeutic-area or
--indication"* — after both had been stated. The gate was right and the message described a
run that did not happen.

The warning was frozen at parse time, when what the caller would supply was not yet known.
It is now composed at compile time by `SearchIntent.warnings_for(indication_supplied=...)`,
and once answered it says so instead.

### STILL OPEN — "autoimmune disease" is answered by hand, not by a vocabulary

It remains `UNRESOLVED_SCIENTIFIC`. Mapping it to the controlled therapeutic area
`AUTOIMMUNE` is the right next step and the phrase is explicit enough to carry it, but that
is a vocabulary question, not a question-layer one — the ontology snapshot still holds zero
DISEASE entities. Until then the user states the area and the engine says it was answered.

## 2026-09-17 — second pass: the acceptance rule for scientific phrases

**The rule now in force.** A scientifically meaningful phrase must do one of three things:
be compiled into an enforceable constraint, be reported unresolved and named, or be
refused. It may never fall silently into residual text while the run proceeds as though the
whole question had been honoured. The run is allowed to be less capable than the question;
it is not allowed to look more capable than it was.

### FIXED — "human efficacy" is now the evidence floor the contract already had

`EvidenceFloor.human_poc_required` existed and the gate engine already evaluated it against
each asset's `human_poc_present` fact. Nothing in the question layer ever set it, so a user
asking for human efficacy got a shortlist that never applied the requirement.

A closed list of phrases now sets it — `human efficacy`, `human efficacy data`, `human proof
of concept`, `efficacy in humans`, `clinical efficacy` and equivalents. Every entry carries
its own "in humans" qualifier. Vague claims (`promising`, `effective`, `strong data`, and
bare `efficacy`) deliberately set nothing and stay residual: enthusiasm is not a contract
term, and an evidence floor the user did not state is worse than one the engine admits it
did not understand.

**What enforcing it actually does today, stated plainly.** No extractor emits a
`human_poc_present` fact, so the requirement evaluates UNKNOWN for every asset and routes it
to analyst review with the requirement named. That is the honest outcome and it satisfies
the rule — the constraint is applied and the uncertainty is visible — but a user should not
read "human efficacy" as a filter that leaves only proven assets. It currently means "every
asset needs review on this point". The contrast is `minimum_stage`, which the CT.gov
extractor does supply facts for (`development_stage_order`), so that one truly decides.

### FIXED — "clinical-stage" is a stage floor, and still guesses no phase

It maps to `EvidenceFloor.minimum_stage = "PHASE_1"`, which the gate reads as
`development_stage_order >= 2`. That is exactly "entered human clinical development":
DISCOVERY and PRECLINICAL fall below it, every clinical phase sits at or above it equally.
It is emphatically **not** a `PhaseConstraint` — the phase gate is EXACT, so turning
"clinical-stage" into "phase 1" would answer a different question. Pinned by a test that
asserts `phase_constraint is None`.

### FIXED — a disease *class* is now escalated by name instead of quietly compiled

`autoimmune disease` used to break into the residual tokens `autoimmune` and `disease`,
which the compiler then poured into `StrategicGap.indications` — and that list *is* gate-
enforced, as `indication IN [...]` against each asset's own indication fact. So the phrase
did not merely vanish: it became a constraint that can never match, because an asset's
indication reads "systemic lupus erythematosus", never "autoimmune disease". Every asset
would drift to review for a reason the user never stated.

There is no controlled disease vocabulary to resolve it against — the published ontology
snapshot holds 84,560 TARGET and 71,506 DRUG entities and **zero** DISEASE entities. Since
the phrase is recognized as scientific and cannot be represented faithfully, the question is
now refused with `NEEDS_CLARIFICATION` naming the phrase, and it compiles as soon as the
user states `--therapeutic-area` or `--indication`. The phrase still widens *retrieval* as a
trial-query condition, which decides nothing.

**Known limit, stated rather than hidden:** only self-declaring class words are recognized
(`disease`, `disorder`, `syndrome`, `indication`, plurals). A bare disease name such as
`myeloma` is still unrecognized and still becomes free text. Closing that needs a disease
vocabulary in the ontology snapshot; it is not closeable in the question layer.

### FIXED — dual-target notation resolved *neither* target, and `x` resolved as a gene

Found while compiling the live acceptance query. `CD19/BCMA` and `CD19xBCMA` — the ordinary
way a dual-target programme is written — were single whitespace tokens, matched nothing, and
took the whole question down with "no biological target recognized". Only the spaced forms
worked. The tokenizer now splits on `/`, `×`, and an `x` between a symbol character and an
uppercase letter.

Worse, in the spaced form `CD19 x BCMA` the connector `x` itself resolved to **PSMB5**, so
the engine asserted a third target the question never named. Connector words are now barred
from target resolution outright. This one is a scientific-correctness defect, not a UX one:
an invented target is the precise failure the resolver exists to prevent.

## 2026-09-17 — first acceptance pass, at `se-v1.0.0`

Questions asked, both taken verbatim from a BD framing:

1. *"Find clinical-stage bispecifics targeting BCMA for autoimmune disease with human
   efficacy."*
2. *"Find small-molecule programs against target X, phase 1-2, and explain why each asset
   qualifies."*

### FIXED — a phase range written with a dash lost half of itself, in silence

`phase 1-2` matched only `phase 1`. The `-2` was dropped, and because unrecognized text is
never promoted, nothing in `explain()` said so. The phase gate is EXACT by design, so the
engine then answered a narrower question than it was asked, with every disposition
downstream of that decision changed and no sign of it anywhere in the output.

The pattern accepted `/` as the only range separator. It now accepts `-`, the unicode
dashes, and `to` / `and` / `or`, and `phase 2 or later` still reads as a minimum rather
than a range. Pinned by `test_a_phase_range_is_read_whole_however_it_is_written`.

### FIXED — the plural of a modality refused to compile at all

`bispecifics` resolved to nothing while `bispecific` resolved to `BISPECIFIC_ANTIBODY`, and
since a query naming no recognized modality is refused outright, the whole question was
rejected with `BLOCKED: no modality recognized in the query`. Asking for one asset type in
the plural is the normal way to ask.

`_match_modality` now retries a depluralized phrase. The depluralization is in the question
layer only: the modality vocabulary still holds labelling spellings, so gating and labelling
keep matching what a source actually wrote. Pinned by
`test_a_plural_modality_is_the_same_request_as_its_singular`.

### OPEN — indication and evidence-strength phrases are dropped to residual

`autoimmune disease`, `clinical-stage` and `human efficacy` all land in `residual_terms`.
That is honest — an unrecognized phrase is never promoted into a criterion — but the user's
intent is then silently unenforced. The therapeutic area stays `UNSPECIFIED` unless
`--therapeutic-area` is passed, and `human_poc_required` exists in the problem contract with
nothing in the natural-language layer mapping "human efficacy" onto it.

Not fixed yet, because the honest failure mode is the tolerable one and the fix is real
work: an indication vocabulary, plus a decision about which phrases may set an evidence
requirement. Reopen when a user is actually misled by a shortlist that ignored the
indication they asked for.

### OPEN — `HRH1` escalates as ambiguous against `DHX8`

`HRH1` is both the histamine receptor and a `DHX8` alias, so the query exits 4 rather than
running. This is the same family as the HISTAMINE endogenous-ligand collision already on the
caveat list, and the escalation is the designed behaviour, but a user asking for the receptor
by its approved symbol has to disambiguate a symbol that was never ambiguous to them.

---

## 2026-09-19 — live acceptance run @ `ad78e62` — PASS_WITH_COVERAGE_LIMITATIONS

Query: `Find clinical-stage dual CD19/BCMA therapies for autoimmune disease with human efficacy.`
Run `se:b0b0c119-d24e-4127-ad02-f17a7297feb6`, artifacts in
`/home/djmann/se_runs/acceptance_20260919_live/`. Confirmation run, no code changes.

**1. Query interpretation — correct.** Every phrase is accounted for in the compiled
problem: `clinical-stage` -> EVIDENCE `minimum_stage`; `dual` -> TARGET_LOGIC `ALL`;
`CD19` -> `CD19`; `BCMA` -> `TNFRSF17`; `human efficacy` -> EVIDENCE `human_poc_required`;
`autoimmune disease` -> UNRESOLVED_SCIENTIFIC `[disease_class_not_enforceable]`, answered by
the supplied `--therapeutic-area AUTOIMMUNE` and warned about in the output. Target
constraint `ALL of CD19, TNFRSF17`; **modality constraint: none**; phase constraint none;
evidence floor `minimum_stage=PHASE_1` + `human_poc_required`.

**2. Source coverage — INCOMPLETE, honestly labelled.** `clinicaltrials_gov` 341 queries /
1922 records / 0 failed; `pubmed` 341 / 3480 / 1 failed. Seven mandatory families returned
nothing because they have no configured connector: company pipeline/presentation, company
press release, AACR, ASCO, ASH, EHA, SEC EDGAR. All seven are emitted as blind spots with
the "cannot speak to what it would have shown" wording. Convergence mode LIVE, status
INCOMPLETE, output declared diagnostic and not promoted.

**3. Dual-target behaviour — correct.** `target.expression`: 56 PASS, 615 FAIL, 701 UNKNOWN.
Every one of the 56 names a construct carrying both antigens (`BCMA/CD19 CAR T cells`,
`GC012F`, `ARI0003`, `CD19/BCMA in vivo CAR-T`, ...). No CD19-only or BCMA-only asset passes;
615 single-target assets are explicitly FAILed rather than left ambiguous. The known
`CD19 or CD19-BCMA CAR-T` residual is **still present** — a disjunctive arm label read as
conjunctive. Unchanged from the sealed replay, still the only such residual.

**4. Human PoC — consistent with the sealed replay.** `evidence.human_poc`: 40 PASS, 1332
UNKNOWN, 0 FAIL. The PASS set is dominated by real molecules (teclistamab, elranatamab,
talquetamab, glofitamab, blinatumomab, obexelimab, rituximab, tocilizumab, vedolizumab,
infliximab, abatacept, venetoclax, lenalidomide, ...). Seven residual non-assets remain:
`choice`, `though`, `frontline`, `discase`, `DAS28`, `PET30`, `INDIGO` — the same residual
the sealed replay measured under the declared 5% document-frequency ceiling. This is the
known, pre-declared limitation of the identity-qualification layer, not a new defect; the
ceiling was declared before measurement and was deliberately not fitted to these names.

**Assets passing BOTH `target.expression` and `human_poc`: 0.** All 56 dual-target
constructs carry `human_poc` UNKNOWN. Given the seven missing source families — where
company and conference evidence for CAR-T efficacy actually lives — UNKNOWN is the correct
answer, and the run says so rather than inventing one.

**5. Final answer — the honest answer is "none proven, under incomplete coverage."**
No asset is promoted as satisfying the query. `eligible: 0`. The 578 review candidates are
review, not answers. The scientifically interesting population is the 56 confirmed dual
CD19/BCMA constructs, several explicitly autoimmune (`CD19/BCMA Lupus Nephritis Targeted
CAR T-cells injection`), but none of them cleared human efficacy from the two sources that
were reachable, so none is presented as an answer.

**6. User-facing shortlist — no wrong answers, but the ordering is poor.** Top ten:
`approval`, `frontline`, `Vicleucel`, `guide`, `optimize`, `belantamab`, `search`, `success`,
`mafodotin`, `though`. Every row is marked `[review, target UNRESOLVED]`, so no single-target
or junk name is presented as satisfying the query, and the INCOMPLETE status plus seven blind
spots are printed above the list. But prose words occupy the top rows. This is the known
renderer behaviour recorded previously: nothing is ever ELIGIBLE, so the review population
*is* the shortlist and its order is declared rather than ranked. It is a presentation defect,
not a scientific correctness defect — no code change made.

**Verdict: PASS_WITH_COVERAGE_LIMITATIONS.** Behaviour matches the sealed replay on every
measured axis (target 56 PASS, human_poc 40 PASS, 0 new target assertions, eligible 0). The
architecture loop stops here. Remaining known work, in order: source connectors for the
seven missing families; shortlist ordering; the disjunctive-arm-label residual.

**Operational caveat.** `reproduce.sh` in that output directory records `--allow-incomplete`,
but the process that actually produced these artifacts was launched without it. A relaunch
intended to add the flag was correctly refused at the custody boundary ("a sealed acquisition
is immutable"), and the original run completed. The flag does not affect gating or scoring,
only whether an INCOMPLETE run exits non-zero, so the artifacts are sound — but
`reproduce.sh` is not byte-faithful to the invocation for this run.

---

## 2026-09-19 — source family 1/7: ASH — WIRED, VALIDATED, LOW YIELD BY DESIGN

`CrossrefConferenceConnector` and `CONFERENCE_VENUES` were built and covered in M12 and had
**no production caller** — `default_connectors()` returned only CT.gov, FDA label, PubMed and
SEC EDGAR, so every reference to the conference machinery outside its own module was a test.
The family reported "no configured connector" while a working connector sat beside it. Same
shape as `bve.se.intent`, importable and unimported since M9. Nothing was rebuilt.

### Live acquisition (`conference_ash`, Crossref → *Blood*)

| | |
|---|---|
| Acquisition status | SUCCESS |
| Records returned | 200 |
| Documents parsed / indexed | 200 / 200 |
| Parse failures | 0 |
| Source-index entries | 200 |
| Runtime | 45.1s |

Content is on-topic: CD19 CAR-T abstracts, tafasitamab Phase I trial data, bicistronic
CD19/CD22 CARs, DOIs and publication dates back to 1992.

### Isolated delta (sealed acceptance custody replayed + ASH index; ASH the only variable)

| Measure | Before | After |
|---|---|---|
| Discovery (ASH) | — | 341 queries, 37 records, 103 candidates, 0 failed |
| Documents / claims | 15,032 / 25,947 | 15,125 / 26,113 |
| Candidates | 2,720 | 2,725 (+5) |
| `identity.distinct_asset` PASS | 669 | **679 (+10)** |
| `target.expression` PASS / FAIL | 56 / 615 | **56 / 615 (unchanged)** |
| `evidence.human_poc` PASS | 40 | **40 (unchanged)** |
| Assets clearing both gates | 0 | **0** |
| `CONFIRMED_TARGET` assertions | 35 | **35 (unchanged)** |
| Low-support demotions | 1,348 | 1,348 |
| Blind spots | 7 | **6** |
| Runtime | — | 1,983.9s |

New assets, all five: `ACIT001`, `BMA117159`, `BMS-986354`, `CC-98633`, `EXC002`. Every one
is development-code shaped and a real clinical molecule. **Zero prose junk, zero new false
target assertions, zero assets lost from either gate.**

### The result, stated honestly

**ASH converted no `human_poc` UNKNOWN to PASS, and that is the designed behaviour, not a
shortfall.** Crossref yields title-and-DOI metadata only — in the exported index `text` is
identical to `title` — so everything this connector produces is `DISCOVERY_EVIDENCE`. It can
nominate an asset worth resolving; it can never mint an identity alias or carry a human
efficacy claim. The connector's own docstring said so before the run.

So ASH buys **discovery breadth** (+5 real assets, +10 identity confirmations) and buys
**nothing decisional**, exactly as the evidence-type contract requires. A source that added
`human_poc` PASSes from titles alone would be a defect.

**Consequence for the remaining six.** EHA, ASCO and AACR are the same Crossref mechanism and
should be expected to behave the same way: breadth, not efficacy. The families that can
actually move `human_poc` off UNKNOWN are the **full-text** ones — company press releases
(`SecFiledPressReleaseConnector`, already built) and company pipeline pages. If the goal is
to convert the 56 dual CD19/BCMA constructs from UNKNOWN, the conference tier will not do it
and the priority order should be re-examined after EHA.

Nothing was tuned. `tests/se` 1022 passed / 2 xfailed, ruff clean.

## EHA source validation — 2026-09-19

Family 2 of the source-coverage program, and the first venue `CONFERENCE_VENUES` did not
already contain. Wiring is one table entry plus one tuple member; the runner gained no
branch. Verdict: **wiring PASS, source FROZEN pending a correctness decision** (below).

### Acquisition (live)

| | |
|---|---|
| status | SUCCESS |
| queries | 341 |
| raw records / parsed / indexed | 176 / 176 / 176 |
| parse failures | 0 |
| source-index entries | 176 |
| runtime | 61.3s |

Container journal verified against live Crossref before wiring: `HemaSphere` (Wiley),
total-results 56 for a BCMA probe, items numbered `P###`/`PB####` — EHA congress abstract
supplements. The casing is the filter value verbatim; `Hemasphere` matches nothing.
`ConferenceVenue.publisher` is `EHA`, the society whose meeting produced the abstract, not
Wiley, who prints the journal.

### Isolated delta

Baseline is the sealed acceptance custody of 2026-09-19 replayed with only the EHA source
index added, so EHA is the single variable and the numbers are directly comparable to ASH's.
`conference_eha` left the blind-spot list; `conference_ash` re-entered it, which is the
isolation working.

| measure | baseline | +EHA |
|---|---|---|
| documents | 15,088 | 15,172 |
| claims | 26,836 | 27,107 |
| candidates | 2,720 | 2,743 |
| `identity.distinct_asset` PASS | 669 | **697** |
| `target.expression` PASS | 56 | **56** |
| `evidence.human_poc` PASS | 40 | **40** |
| eligible | 0 | 0 |
| assets lost | — | 0 |
| runtime | — | 1,250.4s discovery / 376.1s extraction |

`human_poc` and `target.expression` are unchanged, as the ASH result predicted: Crossref
supplies title and DOI, so the connector emits DISCOVERY_EVIDENCE by contract. No previously
UNKNOWN dual CD19/BCMA construct became supported. That is the expected result for this
tier, not a failure of it.

### New correctness defect — FROZEN, not remediated

Of 23 new assets, **5 are real** (`BMS-986393`, `CC-95266`, `FLOTETUZUMAB`, `IMN-003A`,
`YTB323` — the last is rapcabtagene autoleucel, directly on-question) and **18 are not**:

- 16 EHA abstract numbers minted as assets: `PB1983`, `PB2209`, `PB2210`, `PB2289`,
  `PB2442`, `PF155`, `PS941`, `PS942`, `PS945`, `PS947`, `PS962`, `PS965`, `PS1208`,
  `PS1219`, `PS1372`, `PS1501`
- 2 non-assets: `IMAGINE` (trial acronym), `FOR 60`

Mechanism: EHA prints the abstract number as a leading token of the title
(`PB1983: TRIAL-IN-PROGRESS: PHASE II STUDY OF PHE885, ...`). The token is letters followed
by digits, which is exactly the learned drug-code n-gram shape, so the identity layer accepts
it. `PB1983` is the sharpest case — the title names a genuine BCMA CAR-T (PHE885) and the
extractor took the abstract number instead.

ASH did not expose this because *Blood*'s Crossref titles carry no abstract-number prefix.
The defect is in the identity layer, not the connector; EHA merely supplied the first corpus
whose titles are numbered. Nothing was promoted — all 18 sit in `review`/`excluded`, zero
eligible — so this degrades shortlist precision rather than any decision. Remediation is
deliberately **not** attempted here, per the standing rule that a newly exposed correctness
defect is frozen and reported before it is fixed, and because fixing an identity rule while
measuring a source would entangle the two.

## Bibliographic-identifier boundary — 2026-09-19 (EHA defect remediation)

Fixes the defect frozen in the EHA entry above. Re-measured on the same sealed baseline with
a freshly acquired EHA corpus (`/home/djmann/se_runs/eha_probe2/`, 176 records, 0 failures,
57.4s), EHA again the only variable.

**Rule:** a source-native bibliographic identifier is metadata, not an asset identity
candidate, even when its lexical shape resembles a development code. The recognizer is not
weakened and there is no prefix blacklist — only the *metadata position* disqualifies a token.

133 of 176 EHA documents carry a captured identifier; all 176 raw titles are unchanged.

### Abstract-number assets

| | before fix | after fix |
|---|---|---|
| abstract numbers minted as assets | **16** | **0** |
| new assets total | 23 | 7 |

Eliminated: `PB1983`, `PB2209`, `PB2210`, `PB2289`, `PB2442`, `PF155`, `PS941`, `PS942`,
`PS945`, `PS947`, `PS962`, `PS965`, `PS1208`, `PS1219`, `PS1372`, `PS1501`.

### Real assets retained — all five

`BMS-986393`, `CC-95266`, `FLOTETUZUMAB`, `IMN-003A`, `YTB323`. **0 assets lost** against the
baseline. `IMAGINE` (trial acronym) and `FOR 60` remain: neither is a bibliographic
identifier, so both are correctly outside this fix's scope.

### No regression elsewhere

| requirement | baseline | +EHA, post-fix |
|---|---|---|
| `target.expression` PASS | 56 | **56** |
| `evidence.human_poc` PASS | 40 | **40** |
| `evidence.minimum_stage` PASS | 637 | **637** |
| `identity.distinct_asset` PASS | 669 | 681 (+12; was +28 with the junk) |
| false target assertions | — | **0** |
| eligible | 0 | 0 |

Suite 1042 passed / 3 xfailed, ruff clean.

### Separate gap found and recorded, not fixed

`PHE885` — the real BCMA CAR-T that `PB1983`'s title is actually about — is nominated in **no**
context: with or without the abstract number, before or after this change. The shape model does
not accept unhyphenated letters-then-digits codes. So removing the identifier does not reveal
the asset it displaced. Widening the recognizer is a recall/precision decision about the
recognizer itself, which this boundary fix is explicitly not permitted to make. Pinned as a
strict xfail in `tests/se/test_bibliographic_id_boundary.py` so it cannot be forgotten or
silently resolved.

---

## 2026-09-19 — Source validation: SEC-filed issuer press releases (`company_press_release_sec_filed`)

Family 3 of the revised source-expansion order, and the first activated family whose
documents carry full release text rather than bibliographic metadata. The question was not
"does the connector work" but: **can genuinely new full-text evidence move a scientifically
meaningful UNKNOWN to PASS without introducing false attribution?**

**Wiring** (@`ad39f31`): the connector already existed and was covered; it had no production
caller. One entry added to `default_connectors()`. No connector changes.

### Live acquisition (`/home/djmann/se_runs/pr_probe/`)

| | |
|---|---|
| registrant selection | generic — EDGAR full-text search over the target alias phrases, no curated issuer list |
| phrases issued | 54 |
| hits returned | 1,363 |
| eligible after the pre-fetch screen | 566 |
| exhibits actually fetched | 25 (`max_documents` cap) |
| rejected by the classifier | 21 (`no_press_release_indicator`) |
| documents parsed / indexed | 4 |
| parse failures | 0 |
| runtime | 100.8s |
| custody / replay | sealed; deterministic replay verified |

Pre-fetch rejections across the full 1,363: `form_not_eligible` 435, `not_an_ex99_exhibit`
70, `no_press_release_indicator` 21.

The four admitted documents are genuine issuer releases: Molecular Partners AG (Swiss
registrant, arriving on the 6-K path — MP0533 Phase 1/2a AML), Harpoon Therapeutics
(HPN217, BCMA), Autolus (obe-cel PDUFA), Bristol Myers Squibb (Q4 2022 results).
Classification bases: `file_description` and `document_header`.

**Effective coverage universe.** SEC registrants filing 8-K or 6-K, and only those. Private
companies, non-registrants, subsidiaries of a filer, and early-stage companies that have not
yet registered are invisible to this family by construction. SEC provenance establishes that
a registrant filed the document; it adds nothing to the truth value of the science in it.

**Coverage is capped, not exhausted.** 566 eligible → 25 fetched. `max_documents=25` is the
binding constraint, not source availability. Recorded, deliberately not tuned.

### Isolated delta (sealed acceptance custody + only this source's index)

| | baseline | +press releases |
|---|---|---|
| source documents | 3,699 | 3,702 |
| claims | 26,836 | 27,504 |
| candidates | 2,720 | 2,777 |
| identity mentions | 15,088 | 15,287 |
| `identity.distinct_asset` PASS | 669 | 713 |
| `evidence.human_poc` PASS | 40 | **42** |
| `target.expression` FAIL | 615 | 625 |
| resolved target assertions | 576 | 596 |
| eligible | 0 | 0 |
| blind spots | 7 | 7 |
| assets lost | — | 5 (all case variants of retained junk tokens) |

Dual CD19/BCMA constructs moving UNKNOWN → PASS: **none**. Zero newly eligible assets.

**Both new human_poc PASSes manually inspected** — and they are the same drug:

- **Zeposia / ozanimod** (the identity layer holds them as two assets; the known
  alias-merging constraint, not a new defect).
- Source: BMS Q4 2022 EX-99.1,
  `sec.gov/Archives/edgar/data/14272/000001427223000018/q42022ex991.htm`.
- Population/indication: relapsing multiple sclerosis, Phase 3 DAYBREAK open-label extension.
- Result: ">92% of participants who received Zeposia mounted a serological response
  following COVID-19 vaccination"; separately, 68% relapse-free at 74 months.
- Why it satisfies the rule: a measured human outcome, in a named trial, attributed to the
  asset within its own sentence. Not sponsor enthusiasm, not protocol language, not a
  regimen result credited to a component.
- Honest caveat: Zeposia is a marketed drug and the serological endpoint is immune response
  to vaccination, not disease efficacy. The gate is doing what it was specified to do; the
  result is of no relevance to the CD19/BCMA question. That is the correct outcome, not a
  disappointing one.

No efficacy was misattributed. No real asset was lost.

### Open, recorded not remediated

1. **Prose junk amplified by full text.** Of 62 new asset names, roughly seven are real
   (`BMS-986393`, `CC-95266`, `HPN217`, `HPN328`, `HPN424`, `HPN536`, `BCM-001`/`BCM-003`);
   the rest are ordinary prose the identity layer minted — `BRISTOL`, `LONDON`, `EX-99`,
   `AACR 2023`, author surnames, and bare English words. This is the known mention-support
   disposition behaviour, not a new class of defect, but press-release prose exercises it far
   harder than titles and abstracts did. Four documents produced 55 junk names.
2. **Mandatory-family naming mismatch.** `_MANDATORY_SOURCES` in `src/bve/cli/se_search.py`
   names `company_press_release`; the connector's family is
   `company_press_release_sec_filed`. The evidence is admitted regardless (adapters are built
   from every index family), but the blind spot does not clear — measured: 7 → 7 — and its
   message, "no evidence from it was acquired", is now literally false for this run. Keeping
   a blind spot for non-SEC-delivered press releases is arguably right; the wording is not.
   Needs a decision.
3. Snapshot text arrives with function words stripped ("showed more 92% participants
   received"), which makes sentence-scoped attribution read more loosely than the written
   contract implies. Pre-existing; noted here because full text is the first place it matters.

**Verdict: wiring PASS, evidence boundary PASS, zero false attribution.** Tests 1065 passed
/ 3 xfailed, ruff clean.

### 2026-09-19 (follow-up) — coverage areas separated from connector families (@`9cfde01`)

The blind-spot defect above, fixed. `company_press_release` was both the name of a coverage
area and, apparently, of a connector; since no connector had that exact name the manifest
reported the area unreached while `company_press_release_sec_filed` was acquiring from it.

Renaming in either direction trades one false claim for another, so neither was done. An area
now declares the families that reach it and the limitation that survives when only a narrower
family did. Measured against the real press-release index: blind spots **7 → 6**, and in place
of *"no evidence from it was acquired"* the manifest states that releases from private
companies, non-registrants, subsidiaries whose parent filing does not carry them, and
company-hosted newsrooms were not reached.

Invariants pinned (18 tests, `tests/se/test_coverage_areas.py`): a reached area never reports
as unacquired; an unreached area still does; a FAILED family is never laundered into a
coverage note; families that name their own area are unaffected. Reporting only — no gate,
extraction or score change. Suite 1083 passed / 3 xfailed, ruff clean.

## 2026-09-20 — Family 4: company pipeline pages (@`783a310`)

The fourth family, and the first whose documents are not publications at all. A company
pipeline page states a current condition, is rewritten without notice, and carries no
publication date because it has none to carry.

### Two design decisions, taken before acquisition

**Temporal basis.** Refusing undated pages under the global as-of rule makes this tier
unreachable; stamping them with their retrieval date would be worse, asserting that today's
pipeline also held on whatever earlier day the question was asked. So `TemporalBasis` splits
`PUBLISHED_AT` from `OBSERVED_AT`. An observed page keeps `published_at` genuinely unknown,
records when it was seen, and answers only questions asked on or after that moment. A page
that does state a publication date keeps that stronger claim regardless of its family.

**Company attribution.** The manifest declares the company each URL belongs to rather than
leaving it to be recovered later from the hostname or the prose — a recovery that is wrong
for every co-branded, in-licensed or newly acquired program. Bare URL lists still load.

### Manifest, frozen before any delta was looked at

`research/se_benchmarks/company_pipeline/declared_sources.yaml`, sha256
`3f18b98ec6e5c7af270c4b169bd01127147527f1aaee7595ff1db61087ce8267`, manifest_version 1.0.0.

Selection is target-independent and mechanical: the population is the engine's own tracked
company universe (123 tickers, built for the weekly BD loop years before this source existed),
and the tranche is the first 20 by `sha256("bve-company-pipeline-tranche-1:<ticker>")`,
reproduced by `scripts/se_select_company_tranche.py`. No company was included or excluded for
the programs it runs; a test pins that the manifest text contains no target terms.

### Live acquisition (`/home/djmann/se_runs/pipe_probe/`)

- URLs declared **20**, fetched **9**, failed **11**, redirected **8**.
- Failures are ordinary web reality, and all explicit: 403 from Vertex, Ultragenyx, Sarepta,
  Acelyrin and Verve; dead hosts for Turning Point and Immunomedics; acquisition redirects
  that then refused, at J&J (Intra-Cellular) and AbbVie (Cerevel).
- Dated pages **6**, `OBSERVED_AT` pages **3** (Tango, Amarin, Sage) — no date invented.
- One redirect is a real finding rather than noise: **`sagerx.com` now redirects to
  `supernus.com`**. Supernus acquired Sage, so the manifest's declared attribution is already
  stale, and the redirect record is the only place that shows up — the page still arrives.

### Isolated delta (sealed acceptance custody + only this source's index)

| | baseline | +pipeline pages |
|---|---|---|
| source documents | 3,699 | 3,701 |
| claims | 26,836 | 27,102 |
| candidates | 2,720 | 2,767 |
| identity mentions | 15,088 | 15,187 |
| `identity.distinct_asset` PASS | 669 | **681** |
| `evidence.human_poc` PASS | 40 | 40 |
| `target.expression` PASS | 56 | 56 |
| eligible | 0 | 0 |
| blind spots | 7 | **6** |
| assets lost | — | 1 (`Color`, a junk token) |

Dual CD19/BCMA constructs moving UNKNOWN → PASS: **none**.

**The scope boundary held exactly as specified.** Pipeline presence added identity and
discovery and moved neither the target gate nor `human_poc` — which is what the design said
it must not do, and the first time that boundary has been tested by a source that talks about
programs in prose.

**Only two of the nine pages reached the answer.** The acceptance question is dated
2026-09-17 and the pages were observed 2026-09-20, so all three `OBSERVED_AT` pages are
non-decisional for it by construction. That is the new rule working, not a defect, but it
means this delta understates what the family contributes to a current-dated question.

### Candidate cleanliness — a new kind of junk

48 new names: **9 real assets** (RLY-2608, RLY-4008, RLY-8161, GDC-1971, lirafugratinib,
zovegalisib, capivasertib, esomeprazole, fulvestrant) and **39 junk**.

**Zero junk names received any decisional PASS** — not target, not `human_poc`, not even
identity. The stop condition was not triggered.

But the junk is a different species from the press-release prose junk, and worth separating:
`currentColor`, `tbody`, `parentNode`, `yoast`, `licdn`, `pd-pipeline-row`, `interpolate-size`
are **markup and script tokens**, not prose. `_strip_html` is leaking attribute, style and
script content into document text. `MA 02139` — a Cambridge postcode — is drug-shaped by the
recognizer and is the only genuinely prose-shaped false asset in the set.

That is a narrower and more tractable problem than mention precision in prose: it is fixable
in the HTML stripper rather than in the identity layer. Recorded, not remediated, per the
standing instruction not to reopen identity.

## 2026-09-20 — Source normalization: HTML becomes visible text

The company-pipeline delta produced 39 junk candidates that were not misread prose but
implementation text: `currentColor`, `tbody`, `parentNode`, `yoast`, `pd-pipeline-row`. The
cause was `_strip_html`, which removed what sat between angle brackets and therefore kept the
*contents* of `<script>` and `<style>` as if they were words on the page.

The repair is at that boundary, not in identity or nomination. Normalization is now defined
positively — visible text, via an HTML parser already in the dependency tree — so what is
excluded follows from what visible text *is* rather than from a blacklist of observed junk.
No identity, drug-code, target, `human_poc`, manifest or temporal behaviour was changed.

### Two findings that outrank the fix

**Custody seals extracted text, not raw bytes.** `DeclaredUrlConnector` calls `_strip_html`
*before* `store.add`, and no sealed corpus in `se_runs/` contains raw HTML. A sealed replay
therefore cannot test an extraction change: the markup was discarded along with the content.
The same 9 declared URLs were re-fetched from the same frozen manifest (unchanged, same
digest) instead. **Consequence for every other family:** the press-release and conference
corpora were built with the old stripper and will not benefit until re-acquired.

**Excluding a container by position nearly emptied a document.** The first implementation
dropped `<head>` wholesale. Real pages carry unclosed void elements, and a lenient parser
then nests `<body>` *inside* `<head>` — so Tango's page returned **zero** text, which reads
downstream as "this company has no pipeline". Caught because its old text held real content
(PRMT5, MTAP, TNG). The rule is now to exclude only elements that are non-content *by their
own nature*; machine metadata is still excluded, through `<script>` and through attributes,
which are never read at all.

### Isolated delta — same sealed baseline, same question

| | baseline | + pipeline (old) | + pipeline (fixed) |
|---|---|---|---|
| pages with markup leakage | — | 8 / 9 | **0 / 9** |
| candidates added | — | 48 | **17** |
| `identity.distinct_asset` PASS | 669 | 681 | 680 |
| `evidence.human_poc` PASS | 40 | 40 | **40** |
| `target.expression` PASS | 56 | 56 | **56** |
| `evidence.minimum_stage` PASS | 637 | 637 | **637** |
| assets lost | — | 1 (`Color`) | **0** |
| blind spots | 7 | 6 | **6** |

**31 names removed, every one of them markup or script**; none newly appeared. All 9 real
assets are retained and hold identity PASS: RLY-2608, RLY-4008, RLY-8161, GDC-1971,
lirafugratinib, zovegalisib, capivasertib, esomeprazole, fulvestrant. No false decisional
fact: `identity.distinct_asset` is the only gate any newly added name reaches, and every name
reaching it is real.

The 8 residual junk names are prose-shaped — `Elevar`, `Privacy`, `Relay`, `relaytx`,
`webinar`, `belongs`, `solve`, and `MA 02139` — and are the known mention-precision problem,
untouched here. Nothing was tuned against `MA 02139`.

## 2026-09-20 — Family 5: ASCO (`conference_asco`)

Wired through the existing Crossref mechanism: ASCO abstracts appear as *Journal of Clinical
Oncology* supplements. Activation was a single entry in `ACTIVE_CONFERENCE_FAMILIES`, which
is what the venue table was built for.

### The numbering convention — verified, and not what EHA suggested

EHA opens each abstract title with `S###`/`P####`, which is why it declares a pattern and why
the identifier-as-asset defect was possible there. **ASCO does not.** Across 228 live JCO
titles, **zero** begin with an abstract-number token; ASCO prints the number in Crossref's
`page` field instead, in the shapes `####`, `e#####` (online-only), `TPS####` (Trials in
Progress) and `LBA####` (late-breaking).

So ASCO declares `abstract_id_pattern=None`, and that is a documented fact rather than an
unexamined gap. Inventing an anchored pattern that never matches would be indistinguishable
from one that is wrong, and a token of that shape at the head of an ASCO title is part of the
title — development codes in that shape are common, so stripping one would delete a real
asset.

### Acquisition and isolated delta

200 records, 200 parsed, 200 indexed, 0 parse failures, connector succeeded.

| | baseline | + ASCO |
|---|---|---|
| source documents | 3,699 | 3,715 |
| claims | 26,836 | 26,915 |
| candidates | 2,720 | 2,725 |
| `identity.distinct_asset` PASS | 669 | **676** |
| `evidence.human_poc` PASS | 40 | **40** |
| `target.expression` PASS | 56 | **56** |
| `evidence.minimum_stage` PASS | 637 | **637** |
| assets lost | — | **0** |
| blind spots | 7 | 6 |

Exactly as predicted for a title-and-DOI source: discovery and identity breadth, and
`human_poc` structurally unmoved. No threshold was changed on the strength of this result.

### A third species of junk: trial codes

Five names added — **3 real assets** (AMG 404, BI 765179, ociperlimab) and **2 trial/study
codes**: `LEAP-004` (a lenvatinib + pembrolizumab study) and `KEYNOTE-024` (a pembrolizumab
study). `LEAP-004` received an `identity.distinct_asset` PASS; `KEYNOTE-024` did not.

This is neither prose junk nor markup junk. **A study acronym-code is shaped exactly like a
development code** — letters, hyphen, digits — so nothing in the name itself distinguishes
them; only the surrounding phrase does ("Phase II LEAP-004 Study of…"). Conference titles are
dense in study names, so this will scale with AACR rather than stay at two.

Recorded, not remediated: it does not meet the stop condition (no target or `human_poc` PASS),
and the standing instruction is not to reopen identity or alter thresholds on this result.

## 2026-09-20 — The study-code identity boundary

ASCO surfaced `LEAP-004` and `KEYNOTE-024` as assets, and `LEAP-004` took an
`identity.distinct_asset` PASS. A study acronym-code is shaped exactly like a development
code — `LEAP-004` and `AMG 404` are indistinguishable as tokens — so the boundary reads the
source's grammar instead: a code is not an asset where the source names a study with it.

`src/bve/se/discovery/study_identifier.py`, applied in the development-code route of
`extract_observed_asset_names`. Three properties do the work:

- **Per occurrence, never per token.** A code framed as a study here is still an intervention
  in the next document. Only the study-framed occurrences are dropped.
- **The framing must attach to the code**: separator, at most a short bounded run of *design*
  wording (`phase N`, `randomized`, `open-label`…), then the noun. The bound is the point —
  unbounded, it reaches across a clause and finds the "study" belonging to another subject,
  which is exactly how `AMG 404` would be lost out of "A phase 1b study of blinatumomab with
  the … antibody AMG 404". Proximity to "phase" decides nothing.
- **The noun is singular, and a session category is not a description.** Both learned from a
  failure, below.

### What the S&E suite caught that the new tests did not

The first version vetoed `PB1983` out of `PB1983: TRIAL-IN-PROGRESS: PHASE II STUDY OF
PHE885`, failing `test_a_venue_without_a_documented_convention_captures_nothing`. "Trials in
Progress" is a conference *session category* — the taxonomy ASCO numbers `TPS####`, verified
live in the ASCO milestone — and an abstract number in front of it does not thereby name a
trial. Two grammatical corrections, neither lexical: the naming noun must be **singular**
("the LEAP-004 trial" names a study; "LEAP-004 trials" names none), and the category phrase is
excluded. Without the full suite this would have shipped as a broad suppressor across the
whole conference tier, not an ASCO-local fix.

### Isolated delta — sealed acceptance custody + the ASCO index

| | baseline | + ASCO, study boundary |
|---|---|---|
| source documents | 3,699 | 3,715 |
| candidates | 2,720 | 2,719 |
| `identity.distinct_asset` PASS | 669 | 675 |
| `evidence.human_poc` PASS | 40 | **40** |
| `target.expression` PASS | 56 | **56** |
| `evidence.minimum_stage` PASS | 637 | **637** |
| blind spots | 7 | 6 |

**Assets added: 3** — `AMG 404`, `BI 765179`, `ociperlimab`, i.e. exactly the real assets ASCO
contributed. The only new name taking a decisional pass is `ociperlimab`, a real anti-TIGIT
antibody; `LEAP-004` no longer appears there, so **no false decisional fact remains**.

**Study codes removed: 6.** Two are ASCO's (`LEAP-004`, `KEYNOTE-024`); four were already in
the baseline (`CRB-402`, `ORIENT-31`, `AML19`, `CLL10`), so the rule corrects a defect wider
than the source that exposed it. `human_poc` and `target.expression` are untouched, which is
what says no evidence was lost with them.

A limit on that verification: `LEAP-004` and `KEYNOTE-024` were confirmed against their ASCO
source titles, but the other four could not be — document bodies are not retrievable by text
search from sealed custody (`teclistamab`, certainly present in this corpus, also returns
nothing). Their identification as trial names is prior knowledge, not run evidence. What *is*
guaranteed by construction and by test is that each removed occurrence carried explicit study
framing in its source.

## 2026-09-20 — Family 6: AACR (`conference_aacr`) — the first conference source with prose

The fifth conference venue wired, and the first that is not a pointer. Three expectations held
going in were inverted by measurement, and one defect was found only by the live replay.

### Route

**Crossref, not the official bulk proceedings route.** The bulk route was audited and rejected
on its own terms: `AacrBulkProceedingsConnector` has no production caller and no downloader
(`BulkArtifact` presumes a file already on disk), its `# 1234` marker convention was only ever
exercised against a synthetic `extract_fn`, the PDF path is robots-disallowed
(`/DownloadFile/`, `/DocumentViewer/`), and landing pages return 403 to our declared agent.
Using it would have required a bypass that is out of bounds. Not attempted.

Crossref is also the richer route here. AACR proceedings are Cancer Research supplements,
reached by **member 1086** — `type:proceedings-article` returns 0, and a bare
`container-title:"Cancer Research"` matches a different journal (54,823 items, 0 abstracts).

### What the venue deposits

| | ASH / EHA / ASCO | AACR |
|---|---|---|
| records | title + DOI | title + **full abstract body** |
| bodies present | 0% | **192 / 198 (97%)** |
| median body length | — | 2,470 chars |
| parse failures | 0 | **0** |

The 6 without bodies are Corrections and Retractions, which genuinely have none — the type
split tracked reality without being told to.

### Typing and evidence policy, kept separate

A record holding a full abstract is stored as `conference_abstract`; title-only stays
`conference_abstract_metadata`. What such a document may *establish* is a different question,
and is now answered explicitly in `src/bve/se/evidence/source_capability.py`: conference
abstracts are non-decisional for `human_poc` **only**, permissive by default so that no future
source is silently disqualified.

This module had to be **added**, not preserved. The prior claim that the conference tier
"emits `DISCOVERY_EVIDENCE` by contract" described nothing — `document_type` had **zero
readers**. The tier could not move `human_poc` only because a title contains no result. The
invariant would have lapsed the instant abstract bodies arrived, with no test failing.

### The abstract identifier

AACR prints `Abstract <ID>: ` at the front of every proceedings title and repeats the
identifier in `page`. Carried as bibliographic metadata, excluded from identity nomination,
exactly as the EHA boundary established.

An enumerated prefix list was written first, from an April sample, and the tests were written
from that same sample so all of them passed. The **first full live acquisition** missed six
records — `LB-138`, `ND02`, `DDT01-04`, `P5-04-26` — because AACR numbers each session in its
own scheme and coins new ones per meeting, exactly as a sponsor coins a development code. Left
in the title, those would have been nominated as assets. The rule now reads the frame the
source declares (label, identifier, required colon) rather than enumerating tokens. Verified
against all 198 live titles: **138 captured, 0 missed**.

### The defect the replay found: the venue cites itself inside the abstract

138 of 198 abstracts end with AACR's own bibliographic record of the abstract —
`Citation Format: <every author>. <title> [abstract]. In: Proceedings ...`. It is metadata
sitting in the prose field, and left in it was the largest junk source in the run: **98 of 334
new candidates were author names**. An author list is a run of capitalised unfamiliar tokens,
which is indistinguishable from a list of development codes.

Three versions of the removal rule were wrong, each caught by a different mechanism:

1. Element-scoped with a lazy `.*?...\Z` — the lazy quantifier still reached the end anchor and
   would have deleted every paragraph after the block. Caught by a test written for it.
2. Element-scoped and correct — but **15 of 198 records append the citation to the final prose
   paragraph with no wrapper**, so an element rule reaches 92% and looks finished. Caught by
   re-measuring the corpus; the suite was green.
3. Frame required `[abstract]. In: Proceedings` — AACR writes `In: Abstracts: AACR Special
   Conference ...` for non-annual meetings. **1 of 198 residue**, small enough to read as
   rounding. Caught only by insisting on zero.

Final rule: require the frame `Citation Format: ... [abstract]. In:`, bounded by the enclosing
paragraph and never by the end of the fragment. Residue **0 / 198**.

### Delta — sealed custody replayed with the AACR index alone

| | baseline | + AACR |
|---|---|---|
| source documents | 3,699 | 3,815 |
| candidates | 2,720 | 2,837 |
| `identity.distinct_asset` PASS | 669 | 771 |
| `target.expression` PASS | 56 | **56** |
| `evidence.minimum_stage` PASS | 637 | **637** |
| `evidence.human_poc` PASS | 40 | **40** |
| blind spots | 7 | 6 |
| bibliographic IDs leaked as assets | — | **0 / 138** |
| named studies nominated | — | **0** |
| author tokens nominated (before → after fix) | — | **98 → 0** |

Every decisional set is identical to baseline, not merely equal in count. **192 abstract bodies
of oncology efficacy prose entered the corpus and `human_poc` did not move by one asset** —
which is the real test of the evidence policy, and is reported as measured rather than as
expected. Runtime 39 min. `tests/se`: 1165 passed, 3 xfailed. Ruff clean.

126 new candidates remain, of which ~15 are plausible drugs; the rest are cell lines
(`HCT116`, `HEK293`, `SW620`), reagents (`PD98059`, `PLX4720`) and journal back-references
(`NEJM 2011`). Known mention-precision class, deferred, and it touches no gate.

### Observed, not acted on: human PoC in the AACR corpus

Per the milestone's terms, `human_poc` admissibility was **not** changed. Surveying the corpus
for what a later decision would be about: **6 of 198 abstracts carry response language with a
patient count and human context**, and roughly 4 are attributable to a named asset — PR06
(CTL019, complete responses in pediatric ALL), CT007 (4 patients in ongoing complete remission,
median follow-up 11.1 months), CT023 (Phase 1, 11 patients treated), LB-138 (Pt 1 complete
response). The remaining two are correlative biomarker studies.

So the corpus does contain genuine attributable human efficacy, and the policy is currently
withholding it. One caution for the preregistered milestone that decides this: **CT023 reports
its endpoints, not its results** — a rule keyed on efficacy vocabulary rather than on a stated
outcome would admit it wrongly.

---

## 2026-09-20 — Conference-abstract human-PoC admissibility (preregistered, v1)

**Policy:** `docs/se_policies/conference_human_poc_admissibility_v1.md`, sha256
`02770b9e90084845a8241e130dc371979b98c712271adaf7d8decd24c09dd84f`, committed at `3c341e4`
**before** the delta was run. `human_poc.py` sha256 `cd8d963c…703958a` verified unchanged
after the milestone's single edit — the standard is exactly what was preregistered.

**Change:** one line. `NON_DECISIONAL_FOR_HUMAN_POC` emptied in
`bve/se/evidence/source_capability.py`. No change to the AACR connector, identity layer,
target logic, `SourceTier`, or the definition of `human_poc_present`.

### Measured delta — replay `aacr_poc`, sealed AACR custody, 26 min

| gate | base | `aacr_delta2` (AACR, exclusion in force) | `aacr_poc` (exclusion lifted) |
|---|---|---|---|
| `evidence.human_poc` | 40 | 40 | **40** |
| `target.expression` | 56 | 56 | 56 |
| `evidence.minimum_stage` | 637 | 637 | 638 |
| `identity.distinct_asset` | 669 | 771 | 775 |
| `strategy.therapeutic_area` | 0 | 0 | 0 |

**New human-PoC PASSes: 0. New assets named: none. False positives: 0.**

### Controls, verified against the stored abstract text

Per-sentence trace of `efficacy_statements`' refusal order, against the sealed corpus:

- **CT023 (mandatory negative)** — remains UNKNOWN. **But the control is vacuous.** The
  abstract *does* report a result: *"Ten of the 11 patients achieved an objective response
  (91% ORR), with 8 patients (73%) achieving complete response (CR)."* It was refused at
  `WOULD_PASS_IF_ASSET_NAMED` — no asset name in that sentence — not for lacking a reported
  outcome. The preregistration's characterisation of CT023 (and my earlier report of it) was
  wrong. It is a valid *attribution* control, not a planned-endpoint control.
- **CT007** — refused. `"…with 4 of patients in ongoing complete remission."` →
  `WOULD_PASS_IF_ASSET_NAMED`. Malformed count, asset not in sentence. Predeclared.
- **PR06** — refused. `"13 patients (81%) achieved a CR…"` → `NO_EFFICACY_TERM` (bare `CR`
  is not in `_EFFICACY_TERMS`); the title sentence → `NON_EFFICACY:persistence`;
  `"CTL019 cells can induce potent and durable responses…"` → `NO_VALUE`.
- **LB-138** — refused. `"Pt 1 achieved a complete response (CR) and experienced Gr 3
  fever…"` → `NON_EFFICACY:cytokine release`; the MRD sentence → `NO_EFFICACY_TERM`.
- **1440**, **LB110** — remain UNKNOWN.

Per §4 of the policy these are **true negatives of the standard**, not shortfalls. No
threshold, term list or character limit was altered after the output was seen.

### Verdict

Null result. The source class is adopted — a conference abstract may now be *read* for
human PoC — and on this corpus the standard admits nothing new. The milestone's value is
that admissibility is now decided by what a document reports rather than by what an API
used to return, and that the standard was shown to hold unassisted against 192 abstract
bodies of oncology efficacy prose with zero false positives.

**Impact on the CD19/BCMA acceptance question: none.** `human_poc` is the binding evidence
floor and it did not move.

### Open, not remediated

- **Cross-run nondeterminism.** `identity.distinct_asset` +4 and `minimum_stage` +1 between
  `aacr_delta2` and `aacr_poc`, which differ *only* by the human-PoC source policy — a
  change that cannot reach either gate. DISCOVERY also ran 1080s vs 1720s. The isolated-delta
  method assumes run-to-run determinism; this says it does not currently hold. Must be
  diagnosed before any future delta of this size is trusted.
- Three refusal clauses are, on this evidence, the binding constraints on conference prose:
  bare `CR` absent from `_EFFICACY_TERMS`, `cytokine release` vetoing a sentence that also
  reports a response, and sentence-scoped attribution. Each is a defensible position and
  each is now measured. Changing any of them is a **separate, separately preregistered**
  milestone — not a fix to this one.

**Tests:** `tests/se` 1165 passed, 3 xfailed. ruff clean. 16 new preregistered tests in
`tests/se/test_conference_human_poc_admissibility.py`.

---

## 2026-09-20 — Determinism investigation, and the corrected AACR baseline

### The reported nondeterminism was not nondeterminism

`aacr_delta2` and `aacr_poc` have byte-identical argv. Compared field by field:
candidates (2837), facts (25,430), claims (30,231), source-document corpus digest
(`d07d9856…`) and identity mentions (16,042) are **identical**; mentions differ only in
`observed_at`. The runtime gap (1080s vs 1720s) was machine load — a full test suite was
running concurrently. No ordering, concurrency, cache or network instability exists: there
is no concurrency anywhere in `src/bve/se`, `--replay-corpus` blocks the network via
`block_network()`, and the set-iteration sites accumulate rather than truncate.

### What actually moved: an evidence policy gating identity

`may_establish_human_poc` sat at the top of the `HUMAN_POC` document loop as a bare
`continue`, beside the registry-record skip. `has_pharmacologic_context` — the scan that
decides whether a string is *used the way documents use a drug name*, an identity question —
sits below it. So excluding a document from one evidence fact also withheld it from asset
qualification. `source_capability`'s own claim to be "deliberately one fact" was false.

Cost, measured: exactly four candidates — **`bivalent`, `tetravalent`, `dopaminergic`,
`CARTCRCRNone`**. None are drugs; none concern human efficacy. They appeared when the
conference exclusion was lifted because a *different* gate's guard had been suppressing the
identity scan.

Fixed at `0389edd`: the predicate now guards the efficacy read and nothing else. The
exclusion list is empty today, so the coupling is inert — pinned by two tests rather than
merely removed, because an inert defect is one nobody notices re-introducing.

### Corrected AACR baseline — run `aacr_decoupled`

| gate | `aacr_delta2` | `aacr_poc` | **`aacr_decoupled`** |
|---|---|---|---|
| `evidence.human_poc` | 40 | 40 | **40** |
| `target.expression` | 56 | 56 | **56** |
| `evidence.minimum_stage` | 637 | 638 | **638** |
| `identity.distinct_asset` | 771 | 775 | **775** |
| candidates / low-support | 2837 / 1413 | 2837 / 1409 | **2837 / 1409** |

**`aacr_decoupled` reproduces `aacr_poc` exactly** — candidates, facts, claims, gate
evaluations, mentions, documents, review queue and both partitions all hash-identical after
dropping wall-clock metadata; only `run_id`, `retrieval_date` and the `attempt_id` derived
from `run_id` differ. That is an independent, full-scale confirmation of replay determinism,
on a 3,816-document corpus, obtained for free from a change that is a no-op while the
exclusion list is empty.

**`identity.distinct_asset` = 775 is the correct AACR figure.** The AACR milestone's 771
understated its own candidate count, because the commit that added the abstract bodies also
added the exclusion that suppressed their identity contribution.

### Determinism harness

`tests/se/test_replay_determinism.py`. Its first version was itself vacuous: the adapters had
no snapshot root, so extraction never ran and the run produced **no facts at all** — it
compared empty families and would have reported determinism forever. With snapshots wired it
compares canonical identities, merges, gate decisions at requirement granularity, and the
`target` / `human_poc` / `minimum_stage` fact families, each asserted non-empty, across two
different `PYTHONHASHSEED` values **in separate processes** — the property a same-process
test is structurally blind to, since one interpreter shares one seed.

Fact families are named, not prefix-matched: `"target"` matches neither `construct_target_set`
nor `document_target_context`, and `"development_stage"` silently missed `development_status`.
Both mistakes yield an empty family that compares equal forever.

**Tests:** `tests/se` 1189 passed, 3 xfailed. ruff clean.

### Not done, deliberately

Refinements to the human-PoC standard for bare `CR`/complete response and for mixed
efficacy+safety sentences remain **unmade and unpreregistered**. They are a separate
milestone. No term list, threshold or character limit was touched here.

## 2026-09-21 — Human-PoC abbreviations and mixed sentences: STOP CONDITION

Preregistered at `922017d` (amended before measurement, §6), implemented at `bf96578`, replay
`aacr_cr` against baseline `aacr_decoupled`. Suite 1205 passed / 3 xfailed, ruff clean.

**Verdict: the milestone is frozen, not adopted.** One of the two new PASSes is a false positive
on a toxicity sentence, which is the stop condition the preregistration declared in §4.

### Gates

| gate | `aacr_decoupled` | `aacr_cr` |
|---|---|---|
| `identity.distinct_asset` | 775 | 775 |
| `target.expression` | 56 | 56 |
| `evidence.minimum_stage` | 638 | 638 |
| `evidence.human_poc` | 40 | **42** |
| candidates / low-support | 2837 / 1409 | 2837 / 1409 |

Every gate the preregistration required to hold, held. No PASS was lost. The coupling defect found
at `0389edd` did not recur.

### The two new PASSes

**`Cevostamab` — correct, and exactly the false negative the milestone set out to fix.**
*"Cevostamab (FcRH5×CD3) demonstrated a 30.2% overall response rate in patients who underwent
BCMA-targeted treatment and 60.6% in BCMA-targeted naïve patients; the triple-step dosing strategy
reduced cytokine release syndrome."* A quantified response rate, in named patients, attributed to a
named asset. It was refused before only because a clause about *dosing strategy* mentioned CRS.

**`tabelecleucel` — false positive.**
*"For VSTs, the principal early complications are tumor flare reaction (in approximately 20% of
tabelecleucel recipients), GVHD (below 5% with enriched products), acute infusion reactions, and
low-grade CRS-like cytokine release."* This is a toxicity sentence and it produced a human
proof-of-concept fact.

Cause, and it is not simply the clause scope. `flare` is in `_EFFICACY_TERMS` because a disease
flare is an autoimmune efficacy endpoint — and *tumor flare reaction* is an adverse event that
shares the word. The clause `the principal early complications are tumor flare reaction (in
approximately 20% of tabelecleucel recipients)` carries an efficacy term, a value, a human term and
no term from `_NON_EFFICACY_TERMS`, because `complication` is not in that tuple. The sentence-wide
veto had been suppressing this by accident, via the unrelated `cytokine release` at the far end of
the sentence. Narrowing the veto removed an accidental protection, and the word `flare` is doing
work in two directions at once.

### What each change actually bought

| change | new PASSes |
|---|---|
| A — bare `CR` as an efficacy term | **0** |
| B — `pts` / `Pt` as human terms | **0** |
| C — clause-scoped non-efficacy veto | **2** (one correct, one false) |

A and B are correct and pinned by test, and they moved nothing at corpus scale: the PR06 sentences
they unblock are refused one clause later by sentence-scoped attribution, since `CTL019` is not
named in the sentence reporting its own result. That clause is out of scope by declaration. So the
two fixes that were actually requested are, on this corpus, unexercised — and the change that moved
the number is the one that broke.

**No remediation was applied.** Adding `complication` to `_NON_EFFICACY_TERMS` refuses the
tabelecleucel sentence and leaves Cevostamab untouched, and splitting `flare` from `tumor flare` is
a second candidate. Both are post-hoc adjustments chosen after seeing which sentence failed, which
is the thing preregistration exists to prevent. They are recorded as proposals for a successor
milestone with its own declared controls, not applied here.

## 2026-09-21 — Human-PoC adverse-event framing: ADOPTED

Preregistration `docs/se_policies/human_poc_safety_context_v1.md` (`066a820`), implemented
`862a74f` (`EXTRACTOR_VERSION = "human_poc_v3"`). Replay `aacr_safety` vs baseline
`aacr_decoupled`, same argv as `aacr_cr`.

Successor to the frozen `human_poc_abbreviations_and_mixed_sentences_v1` milestone, whose
clause-scoped veto found one real result and one false positive.

| gate | `aacr_decoupled` | `aacr_cr` (frozen) | predicted | **`aacr_safety`** |
|---|---|---|---|---|
| `identity.distinct_asset` | 775 | 775 | 775 | 775 |
| `target.expression` | 56 | 56 | 56 | 56 |
| `evidence.minimum_stage` | 638 | 638 | 638 | 638 |
| `evidence.human_poc` | 40 | 42 | **41** | **41** |
| candidates / low-support | 2837 / 1409 | 2837 / 1409 | 2837 / 1409 | 2837 / 1409 |

Claims 30231 → 30236, facts 25430 → 25431, `source_documents` unchanged at 3816. No other
gate moved. **No asset was lost**, so the two `flare` PASSes the rule was most at risk of
deleting — obexelimab (disease-flare counts vs placebo) and abatacept ("14 of 15 patients
flared") — both survived.

The single gain is `Cevostamab`: *"…demonstrated a 30.2% overall response rate in patients who
underwent BCMA-targeted treatment and 60.6% in BCMA-targeted naïve patients…"* — a real,
quantified, attributed human result that the pre-clause-scoped veto refused because of an
unrelated `cytokine release syndrome` clause at the far end of the sentence.

`tabelecleucel` is absent, as pinned. Every one of the eight preregistered controls behaved as
declared in advance. Suite: 1213 passed, 3 xfailed; ruff clean.

**Recorded, not fixed:** `INDIGO` remains a pre-existing false positive inside the 41 — an
enrollment-and-statistical-power sentence, on a trial name carried as an asset. It was declared
in §2 of the preregistration before measurement and is explicitly out of scope here; 41 is not
41 clean facts.

**Deferred to its own milestone:** sentence-scoped attribution. The predecessor showed it is the
binding recall constraint (the PR06 sentences unblocked by bare `CR` die one clause later
because `CTL019` is not named in the sentence reporting its own result), but loosening it is a
larger scientific change.
