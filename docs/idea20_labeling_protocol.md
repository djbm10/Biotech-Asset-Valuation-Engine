# Idea 20 Labeling Protocol

This protocol defines the ground truth used to test whether the killer-question
spine identified the question that actually decided a resolved program.

## Scope

Labels are point-in-time and no-lookahead for engine inputs:

- The engine may only use information available on or before `decision_date`.
- The human label may use hindsight, but must cite the source used for that
  hindsight.
- This protocol only creates labels. It does not alter POS, valuation, BD score,
  BD route, or science modifiers.

## Dataset

Ground-truth labels live in:

`research/data/killer_question_ground_truth.csv`

Each row is one resolved program. Required fields:

- `program_id`: stable join key into `research/data/phase_transitions.csv`.
- `decision_date`: as-of date for engine replay.
- `outcome`: resolved outcome, usually `approved` or `failed`.
- `decisive_archetype`: the question family judged decisive.
- `label_status`: `clean`, `subjective`, or `excluded`.
- `decisive_confidence`: labeler confidence, `high`, `medium`, or `low`.
- `why_this_archetype_decided`: short rationale for why this was decisive.
- `label_source`: auditable citation string for the label.
- `label_date`: date the label was assigned.
- `pivotal_evidence_event`: event or readout that resolved the program.
- `single_question_dominant`: `true` if one question clearly dominated.

Allowed `decisive_archetype` values:

- `TARGET_VALIDITY`
- `DELIVERY_EXPOSURE`
- `DOSE_ADEQUACY`
- `DIFFERENTIATION`
- `TOLERABILITY_CEILING`
- `NOVEL_OR_UNMODELED_RISK`

## Label Status

`label_status` is the only source of truth for headline eligibility.

- `clean`: eligible for the headline metric.
- `subjective`: appendix and error analysis only.
- `excluded`: not scored.

The scorer must never infer clean-ness from `decisive_archetype`. The same
archetype can be clean in one program and subjective in another.

## Hard Rules

- No explanation, no label: `why_this_archetype_decided`, `label_source`, and
  `label_date` must be populated.
- `label_date` must be on or after `decision_date`.
- Missing evidence is not refutation.
- `subjective` and `excluded` rows must remain outside the headline metric.
- `single_question_dominant=false` rows are valid for abstention analysis, not
  for proving top-1 hit rate.

## P0 Seed Labels

P0 is a protocol and seed-label pass only. It validates the schema and forces
ambiguous cases into `subjective` or `excluded`; it does not build the scoring
harness.
