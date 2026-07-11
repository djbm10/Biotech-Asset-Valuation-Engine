# S&E holdout developer handoff

This document describes the frozen developer package. A future custodian supplies the replacement
holdout paths after this commit; this package contains no holdout data, labels, answers, or scoring
thresholds.

## Frozen package

- Commit: recorded by the custodian from `git rev-parse HEAD`.
- Worktree: detached clean worktree created from that commit.
- Source archive: custodian-generated archive of that commit; verify its SHA-256 independently.
- Python: Python 3.12.x or the repository's declared Python >=3.11.
- Runtime dependencies: those declared in `pyproject.toml`; package-data files (`*.yaml`, `*.j2`)
  are included in built wheels.

## Problem input schema

The holdout runner accepts a strict `se_holdout_problem_v1` classification specification. It is
deliberately separate from `BuyerProblemV2`, which describes buyer strategy and discovery queries.
The required fields are `problem_id`, `title`, `version`, `task`, all three allowed dispositions,
an all-three-class labeling rubric, at least one decision rule, and `source_text_policy`.

Before any single-shot inference, validate the exact problem and unlabeled cases without producing
predictions:

```bash
PYTHONPATH=src python -m bve.cli.se_holdout_evaluate \
  --problem <PROBLEM_YAML> \
  --holdout-data <UNLABELED_HOLDOUT_JSONL> \
  --validate-only
```

The command prints a validation report containing the problem ID and case count. It does not call
the prediction function and does not create a prediction artifact.

## Case input schema

The evaluator accepts JSON Lines. Each nonblank line must contain the four core fields below.
Buyer-capability requirements are optional and activate an additional hard gate.

```json
{
  "case_id": "string",
  "target": "string",
  "modality": "string",
  "source_text": "string",
  "required_buyer_capability": "optional string",
  "buyer_capabilities": ["optional", "capability", "inventory"]
}
```

Additional fields—including any label or expected disposition field—are rejected. If a required
buyer capability is present but the inventory is absent, the capability gate is UNKNOWN; an
affirmative inventory mismatch is FAIL. Case IDs must be unique. The evaluator emits one prediction
for every input case, sorted canonically by `case_id`.

## Prediction output schema

```json
{
  "problem_id": "string",
  "prediction_count": 0,
  "predictions": [
    {
      "case_id": "string",
      "disposition": "INCLUDE|EXCLUDE|UNKNOWN",
      "gates": [
        {
          "gate": "target_match",
          "status": "PASS|FAIL|UNKNOWN",
          "evidence": ["exact matched evidence"],
          "reason": "gate-level rationale"
        }
      ],
      "reason": "overall decision rationale"
    }
  ]
}
```

Every prediction also contains `reason` and a `gates` list. Each gate record has the exact `gate`,
three-state `status`, matched `evidence`, and `reason`. Confirmed mismatch on any required gate
produces EXCLUDE; otherwise any unresolved gate produces UNKNOWN; INCLUDE requires every applicable
gate to PASS.

The output is deterministic JSON. Duplicate, missing, extra, or invalid predictions are rejected by
the validation boundary. Exit code 0 indicates successful serialization; malformed input or
validation failure exits nonzero with no valid prediction artifact.

## Exact inference command template

Run once from the detached frozen worktree, substituting only custodian-supplied paths:

```bash
PYTHONPATH=src python -m bve.cli.se_holdout_evaluate \
  --problem <PROBLEM_YAML> \
  --holdout-data <UNLABELED_HOLDOUT_JSONL> \
  --output <PREDICTIONS_JSON>
```

The label file is not an argument and must not be visible to the process. Hash and make the output
immutable before the independent custodian opens labels.

## Developer verification

```bash
python -m pytest tests/se -q
ruff check src/bve/se src/bve/cli/se_acquire.py src/bve/cli/se_evaluate.py \
  src/bve/cli/se_holdout_evaluate.py src/bve/cli/se_search.py scripts/holdout_preflight.py tests/se
python -m pytest tests/se/test_holdout_runner.py tests/se/test_holdout_cli.py \
  tests/se/test_clean_environment_smoke.py -q
python -m bve.cli.se_holdout_evaluate --help
python -m bve.cli.se_search --help
python -m bve.cli.se_evaluate --help
```

The final handoff reports the exact commit, detached worktree, source archive hash, Python version,
dependency versions, and results of these checks separately. No holdout evaluation is performed by
the developer/package owner.
