# Science Thesis Layer Phase 8-10 Plan

## Phase 8: Evidence Artifact Persistence

Objective: make extracted science evidence replayable and auditable without requiring the same LLM call again.

Deliverables:

- `ScienceEvidenceArtifact` JSON wrapper around `ScienceEvidenceBundle`.
- Artifact identity/versioning fields:
  - `schema_version`
  - `extractor_version`
  - `prompt_version`
  - `model_id`
  - `document_hash`
  - `created_at`
  - `source_document_id`
  - `asset_id`
- Replay CLI artifact flags:
  - `--science-evidence-output-dir`
  - `--science-evidence-artifact`
  - `--science-evidence-artifact-hash-policy warn|fail|ignore`
- Hash mismatch rule: loaded artifact hash mismatch must warn or fail clearly.

Guardrails:

- Persist compact validated evidence artifacts, not rich runtime thesis objects.
- Loading an artifact must avoid another LLM science-evidence call.
- Artifact loading must not update POS, BD actionability, or ScienceThesis directly.

## Phase 9: Compact Evidence Surfacing

Objective: show source-backed evidence in human-facing outputs without creating long evidence dumps.

Deliverables:

- `build_compact_evidence_surface(...)` summary with:
  - evidence counts by component,
  - top source-backed snippets,
  - rejected/ambiguous warning count,
  - unresolved gaps.

Guardrails:

- Keep full evidence tables in artifact JSON.
- Keep replay/memo evidence surfacing concise.
- Do not turn evidence snippets into new scoring logic.

## Phase 10a: Outcome Diagnostics

Objective: define retrospective outcome taxonomy before any calibration work.

Outcome labels:

- `target_pathway_failure`
- `exposure_dose_failure`
- `biomarker_translation_failure`
- `efficacy_failure`
- `safety_failure`
- `commercial_strategic_failure`
- `success`
- `unknown`

Deliverables:

- `ScienceOutcomeRecord`
- `ScienceDiagnosticsReport`
- deterministic aggregation by outcome, binding question, modifier, and missing evidence count.

Guardrails:

- Diagnostics are retrospective only.
- Do not blur science failures with commercial/strategic failures.
- Do not mutate production weights.

## Phase 10b: Calibration Readiness Hooks

Objective: add readiness checks without recalibrating heuristic weights prematurely.

Deliverables:

- `ScienceCalibrationDiagnostic`
- `evaluate_calibration_readiness(...)`
- explicit `calibration_status = heuristic`
- `weight_update_allowed = false`

Guardrails:

- Recalibration requires a separate review phase.
- Do not update weights based only on small sample diagnostics.
- Keep `heuristic_science_modifier` labeled heuristic until validated.
