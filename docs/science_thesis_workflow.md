# Science Thesis Workflow

The Science Thesis layer is deterministic and heuristic. It is not calibrated
and does not use LLM extraction or network calls.

## Single-Asset Memo Render

Science Thesis only:

```bash
bve-asset --config examples/configs/relay_rly2608.yaml --science-thesis
```

This builds a sparse `ScienceThesis`, attaches it to `ValuationOutput`, and
renders the memo section. It does not change POS or valuation math.

Apply heuristic POS modifier:

```bash
bve-asset --config examples/configs/relay_rly2608.yaml \
  --science-thesis \
  --apply-science-pos-modifier
```

This applies `ScienceThesis.modifier_result.heuristic_science_modifier` to the
first remaining technical POS. Treat this as an auditable heuristic sensitivity,
not calibrated probability math.

Run buyer fit / BD mode:

```bash
bve-asset --config examples/configs/relay_rly2608.yaml \
  --science-thesis \
  --buyer-problem examples/configs/buyer_problems/vertex.yaml \
  --buyer-problem-id autoimmune_b_cell_depth
```

This loads buyer problem config, runs Layer 1.5 hard gates/actionability, and
renders the BD Fit section in the BD memo.

## Failure Rules

- `--apply-science-pos-modifier` requires `--science-thesis`.
- `--buyer-problem` requires `--science-thesis`.
- `--buyer-problem-id` requires `--buyer-problem`.
- Unknown buyer problem IDs fail clearly.

## Interpretation

The builder is intentionally boring and honest:

```text
missing evidence -> lower confidence -> diligence question -> next readout
```

It should not fabricate PK/PD, biomarker validation, human proof-of-concept,
clinical meaningfulness, or buyer fit. Missing evidence should remain visible in
memos and tests.

## Watchlist Read-Only Enrichment

```bash
bve-watchlist-run \
  --watchlist path/to/watchlist.yaml \
  --science-thesis \
  --summary-json outputs/watchlist_summary.json
```

This adds read-only science fields to each asset summary without changing
ranking, composite scores, opportunity tiers, valuation math, LLM extraction, or
calibration assumptions.

Science fields:

- `science_binding_question`
- `science_modifier`
- `science_missing_evidence_count`
- `science_next_readout`

Buyer mode is also read-only and requires `--science-thesis`:

```bash
bve-watchlist-run \
  --watchlist path/to/watchlist.yaml \
  --science-thesis \
  --buyer-problem examples/configs/buyer_problems/vertex.yaml \
  --buyer-problem-id autoimmune_b_cell_depth \
  --summary-json outputs/watchlist_summary.json
```

BD fields:

- `bd_route`
- `bd_hard_gate_passed`
- `bd_actionability_score`

Watchlist failure rules match the single-asset path:

- `--buyer-problem` requires `--science-thesis`.
- `--buyer-problem-id` requires `--buyer-problem`.
- `--science-thesis` is not supported in replay mode.

Watchlist caveat: current `--science-thesis` watchlist enrichment is
valuation-backed and requires valuation context / `valuation_config`. Assets
without valuation configs can fail when enrichment is enabled. This is
acceptable for Phase 3b because the goal is normal valuation-backed screening
visibility, not sparse universe screening.

## JSON Audit Summaries

`science_summary` and `bd_summary` are compact audit summaries. They preserve
the memo/watchlist-visible conclusions needed for replay and traceability,
including binding science question, heuristic modifier, whether the modifier was
applied, missing evidence count, warnings, BD route, gate status, actionability
score, and failed gates.

They are not full diligence records. Full rich `ScienceThesis` and
`BDActionabilityResult` objects remain runtime/memo-facing objects and should
not be treated as fully reconstructable from `valuation.json` or watchlist
`summary_json`.

## Known Limitations

- No LLM/document extraction yet.
- No automatic PubMed/news parsing yet.
- No historical calibration claim.
- Buyer problem examples are plausible workflow fixtures, not complete buyer
  strategy databases.
- JSON summaries are audit snapshots, not complete replacements for the
  underlying evidence/thesis objects.
