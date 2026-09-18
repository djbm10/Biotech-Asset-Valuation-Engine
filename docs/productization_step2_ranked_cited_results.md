# Productization step 2 + 3 — ranked, cited asset results

Steps 2 and 3 collapsed into one implementation, as anticipated: "why this asset matched" is
derivable from exactly the records the citations come from, so building them separately would
have meant walking the same graph twice and risking two answers.

## 1. What the audit found

The instruction was to wire existing components rather than build new ones. Everything below
already existed; three of the findings changed the design.

| Component | State | Used how |
|---|---|---|
| `bve.se.ranking.engine.rank_profiles` | Real, and a scientific contract (pairwise, abstains, emits `rank` only when win counts are unique) | Deferred to when populated — never modified |
| `TargetAssertionStatus` | Declared enum precedence | Reused as the display order's precedence; no new weights |
| `SourceEvidenceType` | Already encodes discovery / identity / target / development-stage / company-ownership / regulatory / relationship | Used verbatim as the citation taxonomy |
| `SourceEvidenceClaim` | Complete contract, **zero importers** | *Not* used — see §3 |
| `GateEvaluation` / `OverallDisposition` | Real, per candidate | Sectioning and the "what is missing" explanation |
| `CandidateTargetAssertion` + `TargetEvidenceRef` | Real, carries source/release/record-id/hash | Target citations |
| `review_queue` (`AnalystReviewItem`) | Real | Review labelling |
| `low_support_asset_ids` (M18) | Real | The deferred section |
| `render_search_memo` | The **run** audit memo | Left untouched; the shortlist is the **asset** view |
| `bve-shortlist` / `bve.intelligence.se_shortlist` | A different subsystem (v1 `BuyerProblem`, hand-authored assets YAML) | Not reusable; not conflated |

### Three findings that shaped the design

**1. The pairwise ranker produces nothing in a discovery run.** M16R's artifact holds
`{"ranked": [], "comparisons": []}` and M17's scoring stage logged `0 profiles | 0 eligible`.
It needs comparative clinical profiles that a landscape run does not build. So "ranked
results" could not come from it today. Rather than invent a weighted score — which would have
created a second, unvalidated ranking model indistinguishable from the real one — the
shortlist uses a **declared display order** that says so in the output, and steps aside
entirely the moment `ranking.ranked` is populated.

**2. No candidate in a real run is `ELIGIBLE`.** M17: 0 eligible, 114 excluded, 7,966
unresolved. Every candidate has at least one `UNKNOWN` gate (usually construct-level target
and modality). A shortlist restricted to eligible assets would therefore have been empty on
every run to date. The shortlist shows the review population and labels it, and prints a note
saying why.

**3. Three of the displayed fields are not asset properties.** `modality_id` is read from the
trial/protocol text the asset was discovered in (`adapters.py` — `vocabulary.modality_in(...)`
over intervention context), which is why the junk candidate `"Genetic polymorphism"` carries
`RNA_THERAPEUTIC`. `development_stage` is null for 4,636/4,665 M16R candidates. `company_ids`
is populated for 41 of 4,665. Printing any of these as a plain fact would fabricate.

## 2. What was built

`src/bve/se/reporting/shortlist.py` — `build_shortlist(result, limit=10) -> Shortlist` and
`render_shortlist(shortlist, detail=False) -> str`. Wired into `bve-se-search` as
`--format shortlist` and `--format shortlist-json` (the same object, so the two views cannot
describe different assets), with `--top N` and `--detail`.

**Ordering.** `ranking.ranked` when non-empty (`ordering_basis: "pairwise_ranking"`);
otherwise `"declared_display_order"`, keyed on: section (eligible before review) → the
existing `TargetAssertionStatus` precedence → document count → mention count → name → asset
id. The last key makes ties deterministic. `ShortlistEntry.score` exists and is always `None`
under display ordering, so a consumer cannot mistake position for score by finding nothing to
check. No target-specific weighting.

**Citations.** Three origins, because the engine really does know things three ways:

- `SOURCE_DOCUMENT` — a real `SourceDocument`: publisher, url, content hash, publication date,
  and the *source-native* identifier (`NCT03646318`, `PMID:20391952`) rather than the internal
  `document:…` hash, which means nothing outside this engine.
- `STRUCTURED_AUTHORITY` — target attribution, which comes from ChEMBL/Open Targets release
  records and has no document to quote. Rendered with source, release and record hash, and
  labelled so it is never read as a claim from the literature.
- `DISCOVERY_CONTEXT` — modality, with a note saying it was read from the surrounding text and
  is not asserted as a property of the molecule.

A fact with no evidence renders as `unresolved` with a note, never as a blank or an omission.
A company id with nothing in the corpus naming the company renders as unresolved *and says the
linkage exists* — the name is not printed as an ownership claim. The query is never cited.

**Explanation.** `ShortlistEntry.why` is built from the same records: what the run was
searching when the asset appeared, the target status and how many authority records back it,
the document count and families, and — for anything not eligible — the gate rationale and its
`next_action`, which is precisely "what is missing".

**Readability.** A well-covered asset carries 145 documents and seven gate rationales. The
object keeps all of them; the default view caps citations at 6, review items at 3 and reasons
at 5, each with `... and N more (--detail)`. Nothing is dropped from the data, only from the
summary.

## 3. One decision worth recording

`SourceEvidenceClaim` (contracts.py:595) already carries every field a citation needs and has
no importers. It was not used. It is a producer-side contract: a renderer minting one would
make the reporting layer look like a source of evidence, and a downstream consumer could not
tell a claim the pipeline extracted from one a printer assembled. `Citation` mirrors its field
names and reuses `SourceEvidenceType`, but is explicitly a projection of records that already
exist. If evidence claims are ever produced for real, the projection should read them rather
than the underlying records.

## 4. Verified on real data

Rendered from the sealed M17 CHRM1 artifact (8,080 candidates) without modification:

```
1. atropine  [REVIEW]
   Company: unresolved  -- no company named in this corpus
   Modality: unresolved  -- no modality was read from the surrounding text
   Phase: unresolved  -- no development stage was established for this candidate
   Target: CONFIRMED_TARGET TARGET:CHRM1
   Disposition: UNRESOLVED
   Why: target TARGET:CHRM1 is CONFIRMED_TARGET, from 12 authority records (chembl, open_targets)
   Evidence: PubMed PMID:42730916, ... and 151 more

Counts: eligible 0, review 7966, excluded 114, low_support 0, total_candidates 8080, shown 5
Note: Order is a declared display order, not a score: ...
Note: No candidate passed every gate; ...
```

The top of the list is the CHRM1-confirmed muscarinic agents, which is the right answer for
the question asked. 25 tests in `tests/se/test_shortlist_rendering.py`; no scientific
behaviour was touched, so the benchmarks are unchanged by construction.

## 5. Known gap — now closed, see `docs/productization_phase_intent_gate.md`

**The phase constraint in a typed question was silently dropped.** `SearchIntent` parses
`phases`, and `compile_intent` never reads the field — the string "phase 2" in
`small molecule CHRM1 programs in phase 2` reaches the parser, is shown in the interpretation,
and then has no effect on the compiled `BuyerProblemV2`. The shortlist *displays* phase
honestly, but the run is not filtered by it. Honouring it means deciding where it belongs —
the evidence floor's `minimum_stage`, a gate, or a post-filter — and that changes what gets
excluded, which is a scientific-gating decision rather than a rendering one. Flagged here
rather than changed quietly.

It was subsequently fixed as a gate, not as a filter over this shortlist: `PhaseConstraint`
(EXACT / ANY_OF / MINIMUM) on `StrategicGap`, decided by `GateEngine` against the asset's own
`development_stage_order` facts. The shortlist now *reports* that decision beside the stage
evidence that produced it; it still does not make one.
