# S&E acceptance log

Real-world failures found by asking the engine real BD questions, newest first. This is
not a benchmark: there is no denominator, no score and no target list. An entry earns its
place by being something a user hit, and it stays open until a user would not hit it again.

The rule for acting on an entry: fix it when a real query exposed it, not because it is
listed. Silent misreads outrank refusals, because a refusal tells the user something is
wrong and a misread does not.

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
