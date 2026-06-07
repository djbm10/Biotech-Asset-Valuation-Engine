# Master Architecture Contract

Updated: 2026-04-17  
Phase: A — Architecture Freeze

This document is the human-readable anchor for the architecture freeze. The machine-readable
source of truth is [`src/bve/config/architecture_contract.yaml`](/home/djmann/projects/biotech-asset-valuation-engine/src/bve/config/architecture_contract.yaml:1).

## Purpose

Every system addition must map back to the existing 6-question product contract. If a module,
score, or workflow cannot be traced to one of those six questions, it is out of bounds until
the contract is updated first.

## The 6-Question Contract

| # | Question | Primary modules |
|---|---|---|
| 1 | What is this asset? | `entities/`, `normalization/`, `connectors/`, `ingestion/`, `dossier/` |
| 2 | How good is the science and trial design? | `models/`, `features/`, `similarity/` |
| 3 | What is the real probability of success? | `models/`, `empirical/`, `intelligence/` |
| 4 | What is it worth? | `valuation/`, `analysis/`, `models/` |
| 5 | What is the market pricing in? | `analysis/`, `intelligence/`, `event_study/` |
| 6 | What should I do now? | `intelligence/`, `alerts/`, `pipeline/`, `ops/`, `ui/` |

## Required Output Contract

Every module that emits a decision-relevant artifact must provide:

| Field | Meaning |
|---|---|
| `value` | The actual fact, score, or recommendation emitted |
| `confidence` | How reliable that value is, independent of whether it is high or low |
| `provenance` | The evidence chain and model/version path used to produce it |
| `freshness` | When the underlying evidence was last verified and when it goes stale |
| `explainability` | A human-readable rationale, not just a scalar |
| `downstream_dependencies` | Which modules consume the output next |

This is mandatory for both current modules and planned modules.

## Allowed Score Types

Every score in the system must be classified as exactly one of:

- `descriptive`
- `predictive`
- `decision`
- `calibration / QA`

This prevents value judgments, forecasts, policy outputs, and QA metrics from being mixed
together under one ambiguous number.

## Current Module Map

The top-level package map is frozen in the YAML contract and enforced by test. Current root
modules under `src/bve/` are all mapped there, including operational packages such as
`pipeline/`, `persistence/`, `services/`, and the top-level `review_app.py` module.

Operational rule:

1. New top-level package or module added under `src/bve/` requires a contract update first.
2. Existing package changing primary question requires a contract update in the same change.
3. Planned module promoted to current requires both YAML and this document to be updated.

## Ownership of Key Scores

The score registry lives in the YAML contract. The important boundary is:

- Facts and resolver confidence live in Question 1.
- Science and design sub-scores live in Question 2.
- Success probabilities live in Question 3.
- Valuation outputs live across Questions 4 and 5.
- Actions and sizing live in Question 6.
- Calibration and stale-input metrics are QA scores, not predictive scores.

That ownership split is the guardrail against double counting and hidden policy logic.

## Confidence, Provenance, and Freshness Rules

The contract uses these cross-cutting rules:

1. Direct public-source facts from SEC, FDA, and ClinicalTrials.gov outrank press-release and
   inferred facts.
2. Model confidence is never the same thing as score magnitude. High PoS with low evidence
   coverage must remain low-confidence.
3. Screening-grade assumptions cannot silently inherit capital-candidate confidence.
4. A stale upstream fact makes the downstream output stale, even when the downstream math did
   not change.
5. Conflicts are not deleted. The system may pick an active winner, but alternates stay visible
   in provenance.

## Recalculation Triggers

The contract also freezes the triggers that justify recomputation:

- New evidence arriving for an asset or company
- Alias/entity resolution changes
- Trial, safety, financing, regulatory, or competitor events
- Price or market-cap changes
- Portfolio context changes
- New calibration versions or realized outcomes
- Replay date changes

If a module reruns without one of these causes, that should be treated as operational drift.

## Recommendation Trace

A final recommendation must be explainable through one path:

1. Identity and evidence: normalized company, asset, indication, trial, and source records
2. Science and design: extracted features and analog context
3. Predictive layer: calibrated probability stack and regulatory inference
4. Economic layer: valuation, implied market expectations, and scenario bridge
5. Decision layer: action label, size, and portfolio context
6. QA layer: calibration history, stale-input state, and post-mortem lineage

The architecture freeze is successful only if a serious user can trace any recommendation back
through that chain without reading arbitrary source files.

## Planned Module Contracts

The YAML contract contains explicit input/output contracts for the planned build phases:

- Phase B: canonical asset graph
- Phase C: fully automated evidence ingestion
- Phase D: science diligence engine
- Phase E: layered probability stack
- Phase F: dynamic competition engine
- Phase G: financing engine
- Phase H: market access engine
- Phase I: market expectations core
- Phase J: variant-view engine
- Phase K: catalyst payoff trees
- Phase L: portfolio decision engine
- Phase M: continuous monitoring
- Phase N: calibration feedback loop
- Phase O: operating layer

Those phases are now constrained by explicit contracts rather than open-ended feature ideas.
