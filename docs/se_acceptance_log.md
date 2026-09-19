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
