# Science Thesis Layer - Phase 2 Plan

## Objective

Move from:

```text
Scoring contract exists
```

to:

```text
Tool can populate the contract from asset context,
apply buyer-specific BD logic,
and show the result in user-facing reports.
```

Phase 2 should prove the workflow, not perfect the knowledge base.

The core win:

```text
Harvey: asset evidence -> science thesis -> belief-changing readout
Chris: buyer problem -> hard filters -> actionability -> deal route
```

## Scope Guardrails

Do not build yet:

- LLM extraction
- richer ontology
- new scoring weights
- historical calibration
- perfect buyer strategy model

Keep Phase 2 deterministic, evidence-conservative, and report-visible.

Core rule: `ScienceThesisBuilder` should be boring and honest.

Good output:

```text
Target thesis appears plausible, but human PK/PD evidence is missing.
Binding constraint: enough_drug.
Next readout must show dose-dependent target engagement at tolerable exposure.
```

Bad output:

```text
Strong translational profile based on inferred biomarker logic.
```

Prefer sparse truth over polished inference. If evidence is missing, the builder should
say missing, not infer.

## Deliverable 1: ScienceThesisBuilder

Purpose: the Harvey bridge.

Convert existing local objects into a `ScienceThesis` without inventing evidence.

File:

```text
src/bve/intelligence/science_thesis_builder.py
```

Inputs:

- `AssetDossier`
- `ScienceAssessment`
- `ScienceDiligenceResult`
- phase
- modality
- indication
- known clinical context
- known biomarker context
- known PK/PD context
- known safety context

Must produce:

- `binding_science_question`
- `secondary_science_questions`
- `missing_critical_evidence`
- `evidence_gaps`
- `next_readout_requirement`
- `bd_diligence_questions`
- `heuristic_science_modifier`

Guardrail:

```text
If evidence is missing:
  do not guess
  lower confidence
  add missing_critical_evidence
  add evidence_gap
  add diligence question
```

Missing evidence must appear in:

- `missing_critical_evidence`
- `evidence_gaps`
- `bd_diligence_questions`
- `next_readout_requirement`

The builder must not fabricate:

- PK/PD
- biomarker validation
- human POC
- clinical meaningfulness
- buyer fit

If evidence is weak:

- lower confidence
- add warning
- add diligence question

Acceptance:

- Builds a valid `ScienceThesis` from a minimal fixture.
- Does not invent missing PK/PD, biomarker, or human POC evidence.
- Missing evidence lowers confidence and appears in `missing_critical_evidence`.
- Output includes `heuristic_science_modifier`.
- Output can feed `compute_probability_stack()`.

## Deliverable 2: Basic Science Thesis Report Section

Do this early.

Purpose: validate whether the builder output is readable and useful.

Add section:

```text
Science Thesis
- Core biological hypothesis
- Binding science question
- What must be true
- Missing critical evidence
- Next readout requirement
- Heuristic POS modifier
- Warnings
```

Primary file for Phase 2:

```text
src/bve/reporting/memo_generator.py
```

Do not wire all report surfaces at once. Add `investment_memo_agent.py` and
`research_report.py` later, once the content shape is proven.

Keep the section compact. The point is to see whether the output works in real memos.

Acceptance:

- Existing memo generation does not break when `ScienceThesis` is absent.
- Memo output includes the section when `ScienceThesis` is present.
- Missing evidence and warnings are visible.

## Deliverable 3: BuyerProblemLibrary

Purpose: the Chris bridge.

Encode buyer sandboxes as config, not hardcoded Python.

Files:

```text
src/bve/intelligence/buyer_problem_library.py
examples/configs/buyer_problems/vertex.yaml
examples/configs/buyer_problems/regeneron.yaml
```

YAML shape:

```yaml
buyer_id:
buyer_name:
problems:
  - problem_id:
    strategic_gap:
    required_ta:
    required_targets:
    required_modalities:
    excluded_tas:
    excluded_modalities:
    must_have_evidence:
    capability_constraints:
    known_internal_overlap:
    combination_or_lifecycle_fit:
    scarcity_value:
    time_sensitivity:
    urgency:
    confidence:
```

Guardrail:

Do not try to perfectly model Vertex or Regeneron strategy yet. Use plausible examples
to prove the workflow.

Acceptance:

- Loads Vertex YAML into valid `BuyerProblem` objects.
- Loads Regeneron YAML into valid `BuyerProblem` objects.
- Rejects malformed buyer problem configs.
- Supports multiple problems per buyer.
- Preserves urgency, scarcity, exclusions, and required sandbox fields.

## Deliverable 4: Layer15BuyerMatch

Purpose: apply buyer-specific BD logic.

File:

```text
src/bve/intelligence/layer15_buyer_match.py
```

Flow:

```text
ScienceThesis + BuyerProblem
-> hard gates
-> thesis fit
-> evidence/diligence readiness
-> buyer-owner advantage
-> BDActionabilityResult
-> deal route
```

Must support:

- out-of-sandbox asset -> gated out
- in-sandbox asset -> scored
- missing evidence -> lower diligence readiness
- high urgency / scarcity -> higher actionability
- internal overlap -> lower deal feasibility

Acceptance:

- Calls `evaluate_bd_hard_gates()`.
- Gated assets return `BDRoute.AVOID`.
- In-sandbox assets receive a `BDActionabilityResult`.
- Missing evidence lowers diligence readiness.
- Scarcity/time sensitivity can increase actionability.
- Internal overlap risk reduces deal feasibility.
- Strong human POC plus strategic fit routes to license/acquisition.
- Early uncertain science routes to option/collaboration.

## Deliverable 5: Basic BD Fit Report Section

Add section:

```text
BD Fit
- Buyer problem
- Hard-gate result
- Buyer problem fit
- Science thesis fit
- Buyer-owner advantage
- Missing diligence evidence
- Recommended route
- Route rationale
```

Primary file for Phase 2:

```text
src/bve/reporting/memo_generator.py
```

Do not touch multiple report pipelines yet.

Keep it compact. The goal is to make Chris-style BD filtering visible in the workflow.

Acceptance:

- Existing memo generation does not break when `BDActionabilityResult` is absent.
- Memo output includes the section when `BDActionabilityResult` is present.
- Failed gates, missing diligence evidence, and route rationale are visible.

## Deliverable 6: End-To-End Deterministic Test

Test flow:

```text
asset fixture
-> ScienceThesisBuilder
-> ScienceThesis
-> probability stack
-> BuyerProblemLibrary
-> Layer15BuyerMatch
-> BDActionabilityResult
-> report section
```

Acceptance:

- No LLM.
- No network.
- No invented evidence.
- Missing evidence visible.
- POS modifier applied.
- BD gates applied.
- Deal route generated.
- Report includes thesis and BD fit.

## Preferred Build Order

1. `ScienceThesisBuilder` with minimal fixture
2. Basic Science Thesis section in `memo_generator.py` only
3. `BuyerProblemLibrary` YAML loader
4. Vertex/Regeneron example configs
5. `Layer15BuyerMatch`
6. Basic BD Fit section in `memo_generator.py` only
7. End-to-end deterministic test
