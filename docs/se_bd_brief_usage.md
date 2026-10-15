# BD screening brief — usage

`bve-se-bd-brief` turns a finished S&E run directory into a BD screening brief: strategic gap,
candidate landscape, evidence status per fact, technical diligence questions and an analyst
conclusion. It writes `brief.html` (open in a browser), `brief.md` and `checks.json`.

It **reads only**. It changes no gate, identity, target, modality, ranking or human-PoC
decision, and computes no score. It is a development demonstration, not a validated product.

## Run it

```bash
PYTHONPATH=src python -m bve.cli.se_bd_brief \
    --run-dir ~/se_runs/tac01_protoid_v1 \
    --context examples/se_bd/cd19_cell_therapy_bcl.yaml \
    --output-dir docs/demos/bd_search_evaluation_v1/cd19_cell_therapy_bcl
```

(`bve-se-bd-brief` with the same flags once the package is reinstalled.)

- `--run-dir`: a directory written by `bve-se-run` with `problem.yaml` and `shortlist.json`.
  `result.json` is optional. Without it, gate rows and efficacy passages show as unavailable.
- `--context`: optional YAML with `title`, `question`, `rationale` and `unenforced_requirements`.
  Everything in it is displayed and nothing in it is enforced. Use public framing only.
- `--limit`: number of reviewable candidates to show. The default is 10, taken in the shortlist's
  declared order.

## Reading the brief

| Label | Meaning |
|---|---|
| ✅ Supported | backed by a structured authority record (ChEMBL / Open Targets / NCIt) or a cited registry field |
| ⚠️ Unverified | appears in public text but has not been validated: registry sponsors (not owners) and prose efficacy statements |
| ❔ Unknown | no evidence; known only from search context, or not extracted |
| ❌ Contradictory | an authority record or extracted statement conflicts with the request |

Additional rules:

- **Eligibility** is the engine's gate disposition: Meets, Fails or Unknown. When "Meets" rests
  on a human-PoC gate PASS from prose, the label says so.
- A **modality hint from trial text** is shown separately and is never evidence.
- **Human efficacy** passages are quoted for reading. A prose-derived `human_poc_present` is
  never shown as supported.

## Demos

The demos come from frozen non-holdout development runs, both as of 2026-09-24:

- `docs/demos/bd_search_evaluation_v1/cd19_cell_therapy_bcl/`: CD19 cell therapy in B-cell
  lymphoma (TAC01).
- `docs/demos/bd_search_evaluation_v1/cd19_bcma_dual_autoimmune/`: CD19 and BCMA dual
  targeting in autoimmune disease (MINT5).

See `docs/demos/bd_search_evaluation_v1/README.md` for the assessment.
