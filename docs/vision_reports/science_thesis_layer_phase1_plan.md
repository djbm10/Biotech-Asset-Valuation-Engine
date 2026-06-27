# Science Thesis Layer - Phase 1 Plan

This document is the durable design note for the shared science layer. It captures the Harvey/Chris conclusion so future implementation does not drift back into a generic science score.

## Durable Decision

Build one shared `ScienceThesis` layer with two operating modes.

- `Discovery/Investment Mode`: broad scan, thesis definition, belief update, POS/rNPV impact, and market mispricing context. This follows Harvey's advice: start with "what must be true?", identify the one or two biological questions that change value, and update belief as evidence arrives.
- `BD Mode`: buyer-defined filter and diligence workflow. This follows Chris's Vertex advice: BD starts from a strategic/scientific sandbox and asks whether assets solve the buyer's problem. Irrelevant assets should be gated out before scoring.

The same `ScienceThesis` powers both modes, but the entry point, gates, scoring context, and downstream outputs differ.

## Phase 1 Objective

Create the minimum deterministic contract and scoring path needed for Layer 0 to feed POS and BD workflows.

Phase 1 should answer:

```text
What must be true for this asset to work?
What is the binding science constraint?
What evidence would change belief?
How should this heuristically change POS?
If run in BD mode, does the asset pass buyer sandbox filters and merit diligence?
```

## Non-Goals

- No full LLM extraction pipeline.
- No automated PubMed/news evidence harvesting.
- No historical calibration or backtest claims.
- No replacement for technical diligence.
- No broad rewrite of existing `ScienceAssessment` consumers.
- No claim that Phase 1 weights are validated POS math.
- No more major concept expansion before deterministic models and tests.

## Core Models

Create new module:

```text
src/bve/intelligence/science_thesis.py
```

Initial types:

```text
ScienceMode = discovery_investment | bd
ScienceQuestion = right_target | enough_drug | biomarker_translation | human_poc | clinical_meaningfulness | safety_margin
EvidencePolarity = supports | weakens | neutral
EvidenceResolution = unresolved | partially_resolved | resolved | refuted
ScienceKillFlag = target_refuted | negative_human_poc | infeasible_exposure | unacceptable_safety
NegativeHumanPOCInterpretability = clear | ambiguous | weak
BindingConstraintSource = component_score | manual_override | hard_cap
CalibrationStatus = heuristic | calibrated | deprecated
BDRoute = avoid | monitor | collaboration | option | equity_plus_collaboration | license | major_license | acquisition
```

Primary data objects:

```text
ScienceEvidenceItem
- source_id
- source_type
- claim
- polarity
- confidence
- component
- rationale

ScienceComponentScore
- name
- score
- confidence
- resolution
- resolution_basis
- evidence_for
- evidence_against
- missing_evidence
- rationale

BeliefState
- prior_belief
- current_belief
- update_history

ScienceModifierResult
- scoring_version
- weight_set_version
- calibration_status
- science_score
- science_score_confidence
- heuristic_science_modifier
- binding_constraint
- binding_constraint_source
- modifier_cap
- kill_flags
- negative_human_poc_interpretability
- warnings
- rationale

ScienceThesis
- asset_id
- asset_name
- scoring_version
- weight_set_version
- calibration_status
- indication
- phase
- modality
- mode
- core_biological_hypothesis
- binding_science_question
- secondary_science_questions
- what_must_be_true
- expected_biomarker_changes
- expected_clinical_changes
- key_readouts
- key_failure_modes
- missing_critical_evidence
- evidence_gaps
- must_answer_before_next_stage
- components
- belief_state
- modifier_result
- next_readout_requirement
- bd_diligence_questions
```

`BeliefState` should stay lightweight in Phase 1. It records current conviction and simple update history, but does not need a full time-series learning system.

`binding_science_question` replaces `primary_science_question`. Real assets often have multiple live risks, so `secondary_science_questions` should preserve the non-binding unresolved questions. Do not use a vague `both` enum.

For BD mode:

```text
BuyerProblem
- buyer_id
- buyer_name
- strategic_gap
- required_ta
- required_targets
- required_modalities
- excluded_tas
- excluded_modalities
- must_have_evidence
- capability_constraints
- existing_portfolio_context
- known_internal_overlap
- combination_or_lifecycle_fit
- alternative_assets_available
- competitive_intensity
- scarcity_value
- time_sensitivity
- urgency
- confidence

BDActionabilityResult
- passed_hard_gates
- failed_gates
- buyer_problem_fit
- science_thesis_fit
- evidence_quality
- diligence_readiness
- modality_capability_fit
- buyer_owner_advantage
- internal_portfolio_fit
- assessed_internal_overlap_risk
- combination_or_lifecycle_fit
- alternative_assets_available
- competitive_intensity
- scarcity_value
- time_sensitivity
- deal_feasibility
- bd_actionability
- bd_actionability_confidence
- recommended_bd_route
- route_confidence
- route_rationale
- warnings
- diligence_questions
```

BD-specific fields should stay in the BD layer, not in the core science score. Science can be necessary for actionability, but it is not sufficient for BD.

Distinguish `known_internal_overlap` on `BuyerProblem` from `assessed_internal_overlap_risk` on `BDActionabilityResult`. The former is input context; the latter is the scored output.

## Versioning And Confidence

All scoring outputs should be versioned:

```text
scoring_version
weight_set_version
calibration_status = heuristic | calibrated | deprecated
```

Phase 1 should use `calibration_status = heuristic`. Final outputs should also carry confidence, because a `0.72` score from weak evidence should not read the same as a `0.72` score from strong human data.

Required final confidence fields:

```text
science_score_confidence
bd_actionability_confidence
route_confidence
```

## Missing Evidence

Missing evidence is often as important as negative evidence, especially in BD. Surface it explicitly:

```text
missing_critical_evidence
evidence_gaps
must_answer_before_next_stage
```

These fields should make the output actionable: what must be answered before the next trial, investment decision, diligence step, license, or acquisition.

## Phase-Aware Science Scoring

Keep these separate:

```text
science_score
= strength/quality of evidence around the asset thesis

belief_state
= current conviction over time after evidence updates

heuristic_science_modifier
= uncalibrated POS adjustment derived from science_score, phase, caps, and kill flags
```

`heuristic_science_modifier` can feed the POS stack, but the name should make clear that Phase 1 is not calibrated against historical outcomes.

Discovery/Investment components:

```text
T = target/pathway confidence
D = dose/exposure/PK-PD confidence
B = biomarker/translational validity
H = human proof / clinical signal
M = clinical meaningfulness
S = safety/tolerability
Q = evidence quality
```

`B` is distinct from both target validity and PK/PD. A biomarker can move without predicting clinical benefit.

Clinical meaningfulness should include medical/commercial adoption context:

```text
standard_of_care_context
competitive_effect_threshold
clinically_meaningful_delta
```

This prevents scientifically active drugs from being treated as valuable when the effect size is not meaningful versus standard of care or future competitors.

Biomarkers may appear in both Layer 0 and the later POS stack, but the same evidence must not increase POS twice. Use this split:

```text
Layer 0 biomarker/translational validity
= mechanistic confidence: target engagement, proximity to mechanism,
  biomarker-to-clinical bridge, and whether the biomarker answers the thesis.

POS biomarker adjuster
= clinical/regulatory probability: biomarker-enriched population, validated
  companion diagnostic, regulatory acceptance, or patient-selection advantage.
```

Evidence tags should make overlap explicit:

```text
biomarker_target_engagement -> Layer 0
biomarker_patient_selection -> POS
biomarker_regulatory_validation -> POS
biomarker_clinical_bridge -> Layer 0 or POS, but not both
```

If the same biomarker evidence supports both layers, either reduce/disable the POS biomarker adjuster for that asset or emit a double-counting warning.

Safety should be decomposed enough to avoid false precision:

```text
mechanistic_safety_risk
observed_clinical_safety_signal
tolerability_adherence_risk
regulatory_safety_burden
```

Evidence quality (`Q`) should grade more than source presence:

```text
species_relevance
model_relevance
endpoint_relevance
sample_size
reproducibility
independent_validation
recency
source_credibility
```

This prevents weak, stale, or poorly relevant evidence from being treated like strong human or independently validated evidence.

Discovery/Investment heuristic weights:

```text
preclinical:   T .30 + D .25 + B .20 + H .05 + M .05 + S .05 + Q .10
phase_1:       T .20 + D .30 + B .20 + H .10 + M .05 + S .05 + Q .10
phase_2:       T .15 + D .15 + B .15 + H .25 + M .15 + S .10 + Q .05
post_phase_2:  T .10 + D .10 + B .10 + H .30 + M .20 + S .15 + Q .05
phase_3:       T .10 + D .10 + B .10 + H .25 + M .20 + S .20 + Q .05
```

These are Phase 1 heuristics. They should be versioned and treated as calibration candidates, not validated coefficients.

Phase rule:

```text
pre-Phase 2:
  enough_drug asks whether the drug can reach the right tissue/cell at a feasible dose.

post-credible Phase 2:
  enough_drug should become resolved or partially resolved when human data support it.
  The main question becomes whether the selected dose produced enough effect safely
  and whether the effect is robust enough for the next trial.
```

Post-Phase-2 enough-drug resolution must be based on human evidence, not merely a
generic resolved flag. Acceptable `resolution_basis` values include:

```text
human_pkpd
human_dose_response
human_exposure_response
human_clinical_poc
```

Modifier:

```text
science_score = min(weighted_science_evidence, binding_constraint + 0.15)
heuristic_science_modifier = 0.70 + 0.40 * science_score
```

`binding_constraint` should default to the score of the component tied to `binding_science_question`. It may be manually overridden when expert review identifies a different binding issue. Store the source in `binding_constraint_source`:

```text
BindingConstraintSource = component_score | manual_override | hard_cap
```

Caps and overrides:

```text
modifier_cap = 1.10

if direct_negative_human_POC and negative_human_poc_interpretability == clear:
    modifier_cap = min(modifier_cap, 0.60)

if direct_negative_human_POC and negative_human_poc_interpretability in {ambiguous, weak}:
    emit warning and require rationale before applying hard cap

if no_feasible_exposure_at_active_dose:
    modifier_cap = min(modifier_cap, 0.65)

if target_pathway_refuted:
    modifier_cap = min(modifier_cap, 0.40)
    program_kill_flag = true
    emit target_pathway_refuted_program_kill warning

heuristic_science_modifier = min(heuristic_science_modifier, modifier_cap)
```

If `program_kill_flag = true`, the output should state that the current science thesis is refuted unless the thesis is explicitly reformulated. Target/pathway refutation is not just a warning; it must prevent the science layer from increasing technical POS.

Do not treat every failed human trial as direct negative human POC. Record whether failure was interpretable as biology failure or potentially explained by endpoint choice, underpowering, wrong dose, wrong population, or operational issues.

## BD Mode Scoring

BD mode starts with hard gates:

```text
TA fits buyer strategy
target/pathway fits buyer sandbox
modality fits or fills an explicit capability gap
asset solves the explicit buyer problem
```

Only survivors get actionability scoring:

```text
bd_actionability =
  0.30 * buyer_problem_fit
+ 0.15 * science_thesis_fit
+ 0.15 * evidence_quality
+ 0.10 * diligence_readiness
+ 0.10 * modality_capability_fit
+ 0.10 * buyer_owner_advantage
+ 0.10 * deal_feasibility
```

Additional BD fields should be surfaced as rationale and route inputs:

```text
internal_portfolio_fit
assessed_internal_overlap_risk
combination_or_lifecycle_fit
alternative_assets_available
competitive_intensity
scarcity_value
time_sensitivity
```

`buyer_owner_advantage` answers whether this buyer is the natural owner of the asset: better platform, trial network, manufacturing capability, regulatory experience, commercial channel, or combination/lifecycle opportunity.

Comparator and scarcity context matter in BD. An asset can be only moderately attractive scientifically but strategically valuable if few alternatives exist inside the buyer's gap.

Phase 1 actionability should populate and use portfolio/scarcity fields, not just
store them as passive contract fields. `internal_portfolio_fit`,
`combination_or_lifecycle_fit`, `scarcity_value`, and `time_sensitivity` can
increase buyer problem fit or owner advantage, while
`assessed_internal_overlap_risk` should reduce deal feasibility.

## Deal Route Logic

Phase 1 should include simple deterministic route guidance:

```text
early / uncertain science:
  collaboration or option

platform upside + uncertainty:
  equity_plus_collaboration

strong human POC + strategic fit:
  license or acquisition

late-stage asset + urgent strategic need:
  acquisition or major_license

fails hard gates or thesis refuted:
  avoid
```

The route should include `route_rationale`, not just a label.

## Phase 1 Integration Points

1. POS path:
   - Add a compatibility adapter from `ScienceThesis.modifier_result.heuristic_science_modifier` into the existing probability stack science modifier.
   - Keep the existing `0.70 + 0.40 * score` range for normal uncertainty.
   - Apply caps and kill flags before the modifier touches technical POS.
   - Emit overlap warnings when the same biomarker evidence is used in Layer 0 and POS.

2. BD path:
   - Add `BuyerProblem` and `BDActionabilityResult` Layer 1.5-compatible contracts.
   - Do not replace existing M&A scoring yet.
   - Surface `passed_hard_gates`, `failed_gates`, `bd_actionability`, `bd_actionability_confidence`, `recommended_bd_route`, `route_confidence`, `route_rationale`, missing evidence, and diligence questions as input to future buyer-problem matching.

3. Reporting:
   - Discovery output should show thesis, binding constraint, next readout, POS impact, confidence, missing evidence, and why the modifier is heuristic.
   - BD output should show buyer problem, hard-gate result, fit, why not, diligence questions, buyer-owner advantage, comparator/scarcity context, and route-to-deal rationale.

## Phase 1 Implementation Checklist

- Add `src/bve/intelligence/science_thesis.py` Pydantic models and deterministic scoring helpers.
- Add unit tests for:
  - discovery mode computes separate `science_score`, `belief_state`, and `heuristic_science_modifier`;
  - version fields are present on score outputs;
  - final confidence fields are present for science score, BD actionability, and route;
  - weak binding constraint caps score despite strong other components;
  - biomarker/translational validity can be binding even when target and PK/PD are strong;
  - same biomarker evidence cannot increase POS twice without an overlap warning or adjuster reduction;
  - missing critical evidence is surfaced in science and BD outputs;
  - evidence quality grades species/model/endpoint relevance, sample size, reproducibility, independent validation, recency, and source credibility;
  - direct negative human POC only caps hard when interpretability is clear;
  - ambiguous failed human data requires rationale before applying hard cap;
  - target/pathway refutation emits kill flag;
  - post-Phase 2 PK/PD is treated as resolved/partially resolved when supported by credible human data, not rescored from preclinical speculation;
  - clinical meaningfulness includes standard-of-care and competitive-effect context;
  - safety decomposition can surface mechanistic, observed clinical, tolerability, and regulatory safety risks separately;
  - BD hard gates exclude out-of-sandbox assets before scoring;
  - BD actionability includes science as one component, not the whole score;
  - buyer owner advantage, internal portfolio fit, comparator context, scarcity, and time sensitivity affect BD actionability/rationale;
  - deal route logic produces collaboration/option/license/acquisition/avoid recommendations with rationale.
- Add narrow adapter test showing `ScienceThesis.modifier_result.heuristic_science_modifier` feeds the probability stack without changing unrelated probability behavior.
- Add one small fixture/example:
  - Discovery example: asset with right-target vs enough-drug vs biomarker translation binding risk.
  - BD example: Vertex autoimmune/B-cell buyer problem with one passing asset and one gated asset.

## Acceptance Criteria

Phase 1 is complete when the repo can produce deterministic `ScienceThesis` outputs for an asset in both modes, explain the binding constraint, produce a capped phase-aware `heuristic_science_modifier`, surface confidence and missing evidence, and produce BD hard-gate/actionability/route-to-deal output for a buyer problem.

Warning fields should capture issues such as:

```text
biomarker_double_counting_risk
ambiguous_negative_human_poc
low_confidence_high_score
manual_binding_constraint_override
```

The first implementation does not need perfect evidence extraction. It needs the right contract, scoring semantics, tests, and integration surface.

Do not expand Phase 1 beyond these contracts before implementation. The next step is deterministic models and tests, not more concept growth.
