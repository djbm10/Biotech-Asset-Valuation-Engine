# Phase 1 CD19/BCMA orchestration

`scripts/run_phase1_cd19_bcma_orchestrator.py` is a deterministic controller. It derives state from the signed governance report and hashes its bound inputs before routing roles. Substantive construction and validation remain in fresh Codex processes.

The controller uses `codex exec` 0.145.0 (when available), never `codex exec resume`. Each invocation has a unique identity, prompt, JSONL execution log, final response file, result envelope, and detached worktree rooted under `/tmp/phase1_cd19_bcma_worktrees`. Only explicit governance inputs are copied into a role worktree. Builder outputs are copied back only under the V3 namespace and are hash-checked before acceptance.

State is [workflow_state.json](../research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/orchestration/workflow_state.json), governed by `workflow_state.schema.json`; role envelopes live in `results/<invocation_id>.json` and are checked by `validate_phase1_cd19_bcma_role_result.py`. The append-only ledger is `orchestration_ledger.jsonl`. Prompt templates are in `prompt_templates/` for V3 construction, independent validation, transition governance, remediation, lineage audit, and protocol amendment.

The incompatible role matrix includes Builder and validator, protocol engineer and sole protocol validator, Selector and selection validator, corpus builder and corpus validator, primary reviewer and blind reviewer, reconciliation engineer and third adjudicator, and artifact creator and sole release authority. A validator receives no builder narrative, cannot write builder outputs, and must recompute hashes and counts directly.

The current authorized route is:

`BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3` → `INDEPENDENTLY_VALIDATE_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3`

V1 and V2 are preserved failed lineages. Selection, seed execution, reviewer IDs, evidence corpus, semantic review, and release are fail-closed until separately authorized.

Dry run:

```bash
python scripts/run_phase1_cd19_bcma_orchestrator.py --start-from-current-state --dry-run --stop-after BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3
```

Start/resume:

```bash
python scripts/run_phase1_cd19_bcma_orchestrator.py --start-from-current-state --allow-network --max-milestones 20
python scripts/run_phase1_cd19_bcma_orchestrator.py --resume --max-milestones 20
```

The lock, incomplete invocation logs, and failed worktrees are preserved for inspection. Governance, hash, source-access, collision, custody, and repeated-failure conditions stop the workflow for human intervention.
