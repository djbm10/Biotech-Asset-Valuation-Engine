# S&E acceptance log

Real-world failures found by asking the engine real BD questions, newest first. This is
not a benchmark: there is no denominator, no score and no target list. An entry earns its
place by being something a user hit, and it stays open until a user would not hit it again.

The rule for acting on an entry: fix it when a real query exposed it, not because it is
listed. Silent misreads outrank refusals, because a refusal tells the user something is
wrong and a misread does not.

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
