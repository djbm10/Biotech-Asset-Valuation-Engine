#!/usr/bin/env python3
"""Fail-closed, resumable controller for the Phase 1 V3 authorization.

The controller only routes result envelopes.  Every role is a new Codex
process in a new checkout; this file never resumes a Codex conversation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2"
ORCH = BASE / "orchestration"
AUTH = BASE / "governance/new_cohort_v2_candidate_universe_v3_milestone_authorization.json"
AUTH_MAN = BASE / "governance/new_cohort_v2_candidate_universe_v3_milestone_authorization_manifest.json"
V3 = BASE / "candidate_universe_v3"
MILESTONE = "BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3"
VALIDATE = "INDEPENDENTLY_VALIDATE_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3"
APPROVAL_POLICIES = ("untrusted", "on-request", "never")
ROLE_TEMPLATES = {
    "BUILDER": "build_v3.md",
    "INDEPENDENT_VALIDATOR": "validate_v3.md",
    "REMEDIATION_ENGINEER": "remediation_v3.md",
    "GOVERNANCE_AUTHORITY": "protocol_amendment.md",
    "MILESTONE_TRANSITION_AUTHORITY": "governance_transition.md",
    "LINEAGE_AUDITOR": "lineage_audit.md",
}
ROLE_TYPES = tuple(ROLE_TEMPLATES)
ROLE_NETWORK_DEFAULTS = {role: role == "BUILDER" for role in ROLE_TYPES}
PROHIBITED = ("SELECT", "SEED", "REVIEWER", "CORPUS", "SEMANTIC", "RELEASE")
ALLOWED_CONCLUSIONS = {
    "PASS", "FAIL_REMEDIABLE", "FAIL_GOVERNANCE_REQUIRED", "FAIL_AUTHORIZATION_REQUIRED",
    "FAIL_VERSION_COLLISION", "FAIL_HASH_OR_LINEAGE", "FAIL_SOURCE_ACCESS",
    "FAIL_ENVIRONMENT", "TERMINAL_SUCCESS",
}


class RoleSpec:
    def __init__(self, role_type: str, milestone: str, template: str, network_access: bool,
                 permitted_inputs: tuple[str, ...], permitted_outputs: tuple[str, ...],
                 prohibited_paths: tuple[str, ...], expected_conclusions: tuple[str, ...],
                 required_next_gate: str | None):
        self.role_type = role_type
        self.milestone = milestone
        self.template = template
        self.network_access = network_access
        self.permitted_inputs = permitted_inputs
        self.permitted_outputs = permitted_outputs
        self.prohibited_paths = prohibited_paths
        self.expected_conclusions = expected_conclusions
        self.required_next_gate = required_next_gate


def role_spec(role: str, *, network_access: bool | None = None) -> RoleSpec:
    if role not in ROLE_TEMPLATES:
        raise ValueError(f"unsupported role: {role}")
    is_builder = role == "BUILDER"
    return RoleSpec(
        role, MILESTONE if is_builder else VALIDATE, ROLE_TEMPLATES[role],
        ROLE_NETWORK_DEFAULTS[role] if network_access is None else network_access,
        (rel(AUTH), rel(AUTH_MAN), rel(BASE / "protocol/new_cohort_v2_selection_protocol_v1_1.json"),
         rel(BASE / "governance/new_cohort_v2_candidate_universe_v2_lineage_audit.json")),
        (rel(V3) + "/",) if is_builder else (rel(BASE / "candidate_universe_v3_validation") + "/",),
        tuple(rel(BASE / p) for p in ("candidate_universe_v3", "candidate_universe_v3_validation"))
        if not is_builder else tuple(rel(BASE / p) for p in ("candidate_universe_v1", "candidate_universe_v2")),
        tuple(sorted(ALLOWED_CONCLUSIONS)),
        VALIDATE if is_builder else None,
    )


def route_conclusion(conclusion_class: str, blocker_type: str | None = None) -> str:
    """Pure routing table; narrative text cannot advance a milestone."""
    routes = {
        "PASS": "INDEPENDENT_VALIDATOR", "FAIL_REMEDIABLE": "REMEDIATION_ENGINEER",
        "FAIL_GOVERNANCE_REQUIRED": "GOVERNANCE_AUTHORITY",
        "FAIL_AUTHORIZATION_REQUIRED": "MILESTONE_TRANSITION_AUTHORITY",
        "FAIL_VERSION_COLLISION": "LINEAGE_AUDITOR", "FAIL_HASH_OR_LINEAGE": "HUMAN_STOP",
        "FAIL_SOURCE_ACCESS": "HUMAN_STOP", "FAIL_ENVIRONMENT": "HUMAN_STOP",
        "TERMINAL_SUCCESS": "TERMINAL_COMPLETION",
    }
    if conclusion_class not in routes:
        raise ValueError(f"unknown conclusion class: {conclusion_class}")
    return routes[conclusion_class]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def load_authority() -> dict[str, Any]:
    return json.loads(AUTH.read_text())


def verify_authority(authority: dict[str, Any]) -> None:
    assert authority["overall_conclusion"] == "NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3_MILESTONE_AUTHORIZED"
    assert authority["active_protocol_version"] == "1.1.0"
    assert authority["activated_milestone"] == MILESTONE
    assert authority["candidate_universe_v3"]["version"] == "3.0.0"
    assert not V3.exists(), "V3 already exists; do not rerun the authorized build"
    assert authority["authorization_state"]["candidate_universe_v3_validation_authorized"] is False
    assert authority["lineage_and_isolation"]["candidate_universe_v1_immutable"] is True


def required_input_inventory(authority: dict[str, Any], role: str = "BUILDER") -> dict[str, Any]:
    """Return the exact inputs and committed/dirty classification for a role."""
    spec = role_spec(role)
    paths = set(spec.permitted_inputs) | {
        rel(ORCH / "role_result.schema.json"), rel(ORCH / "workflow_state.schema.json"),
        rel(ORCH / "prompt_templates" / spec.template), rel(ROOT / "scripts/build_phase1_cd19_bcma_role_prompt.py"),
        rel(ROOT / "scripts/validate_phase1_cd19_bcma_role_result.py"),
    }
    for value in authority.get("governing_hashes", {}).values():
        if isinstance(value, dict) and value.get("path"):
            paths.add(value["path"])
    committed = set(subprocess.run(["git", "ls-files", "--", *sorted(paths)], cwd=ROOT,
                                   capture_output=True, text=True, check=True).stdout.splitlines())
    dirty = set(subprocess.run(["git", "status", "--porcelain", "--", *sorted(paths)], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.splitlines())
    missing = sorted(p for p in paths if not (ROOT / p).exists())
    return {"role": role, "required": sorted(paths), "required_committed": sorted(committed),
            "explicitly_copied": [], "missing": missing,
            "missing_from_head": sorted(paths - committed), "dirty_relevant": sorted(dirty),
            "safe": not missing and paths <= committed}


def preflight(authority: dict[str, Any], role: str = "BUILDER") -> dict[str, Any]:
    inventory = required_input_inventory(authority, role)
    all_dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.splitlines()
    relevant = set(inventory["required"])
    inventory["unrelated_dirty"] = [line for line in all_dirty
                                     if line[3:] not in relevant and not line[3:].endswith("orchestrator.lock")]
    inventory["role_launch_safe"] = inventory["safe"]
    return inventory


def initial_state(authority: dict[str, Any]) -> dict[str, Any]:
    inventory = required_input_inventory(authority)
    hashes = {p: sha(ROOT / p) for p in inventory["required"] if (ROOT / p).exists()}
    return {
        "workflow_id": "phase1-cd19-bcma-new-cohort-v2-orchestration",
        "benchmark_family": authority["benchmark_identity"]["benchmark_family"],
        "benchmark_version": authority["benchmark_identity"]["benchmark_version"],
        "benchmark_lineage": authority["benchmark_identity"]["benchmark_lineage"],
        "active_protocol_version": authority["active_protocol_version"],
        "active_candidate_universe_version": authority["candidate_universe_v3"]["version"],
        "current_authorized_milestone": MILESTONE, "current_status": "AUTHORIZED_PENDING_BUILDER",
        "required_role": "BUILDER", "governing_artifact_paths": sorted(hashes),
        "governing_artifact_hashes": hashes, "completed_milestones": authority["completed_milestones"],
        "failed_milestones": ["CANDIDATE_UNIVERSE_V1", "CANDIDATE_UNIVERSE_V2"],
        "blocked_milestones": [], "pending_validation": VALIDATE,
        "next_permitted_milestones": [MILESTONE], "explicitly_prohibited_milestones": [
            "BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V2", "VALIDATE_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V2",
            "COHORT_SELECTION", "SELECTION_SEED_EXECUTION", "REVIEWER_ID_GENERATION",
            "EVIDENCE_CORPUS_CONSTRUCTION", "SEMANTIC_REVIEW", "RELEASE"],
        "historical_state": authority["historical_state"], "last_invocation_id": None,
        "last_conclusion": None, "accepted_invocations": [], "human_intervention_required": False,
        "human_intervention_reason": None, "terminal_status": False,
    }


def state_path() -> Path:
    return ORCH / "workflow_state.json"


def state_hash(state: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def write_state(state: dict[str, Any]) -> None:
    ORCH.mkdir(parents=True, exist_ok=True)
    tmp = state_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(state_path())


def ledger(event: str, invocation_id: str | None = None, **kwargs: Any) -> None:
    ORCH.mkdir(parents=True, exist_ok=True)
    path = ORCH / "orchestration_ledger.jsonl"
    sequence = sum(1 for _ in path.open()) + 1 if path.exists() else 1
    record = {"sequence": sequence, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "workflow_id": "phase1-cd19-bcma-new-cohort-v2-orchestration", "invocation_id": invocation_id,
              "event_type": event, **kwargs}
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def verify_resume(state: dict[str, Any]) -> None:
    if not state_path().exists():
        raise RuntimeError("resume requires persisted workflow_state.json")
    ledger_path = ORCH / "orchestration_ledger.jsonl"
    records = [json.loads(line) for line in ledger_path.read_text().splitlines()] if ledger_path.exists() else []
    launched = {r.get("invocation_id") for r in records if r.get("event_type") == "ROLE_LAUNCHED"}
    completed = {r.get("invocation_id") for r in records if r.get("event_type") == "ROLE_COMPLETED"}
    accepted = {r.get("invocation_id") for r in records if r.get("event_type") == "RESULT_ACCEPTED"}
    incomplete = launched - completed - accepted
    if incomplete:
        raise RuntimeError(f"incomplete invocation(s) require human recovery: {sorted(incomplete)}")
    for item in state.get("accepted_invocations", []):
        result = Path(item["result_path"])
        if not result.is_absolute():
            result = ROOT / result
        if not result.exists() or sha(result) != item["result_hash"]:
            raise RuntimeError("accepted output was altered or is missing; human stop")
        for path, digest in item.get("output_hashes", {}).items():
            output = Path(path)
            if not output.is_absolute():
                output = ROOT / output
            if not output.exists() or sha(output) != digest:
                raise RuntimeError("accepted output was altered or is missing; human stop")


def prompt(args: argparse.Namespace, invocation_id: str, role: str, result_path: Path,
           builder_outputs: str = "") -> tuple[Path, dict[str, Any]]:
    output = ORCH / "prompts" / f"{invocation_id}.md"
    cmd = [sys.executable, str(ROOT / "scripts/build_phase1_cd19_bcma_role_prompt.py"), "--role", role,
           "--milestone", role_spec(role).milestone, "--invocation-id", invocation_id,
           "--output", str(output), "--result-path", str(result_path),
           "--builder-outputs", builder_outputs]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output, json.loads(completed.stdout)


def output_paths_allowed(role: str, paths: list[str]) -> bool:
    spec = role_spec(role)
    return all(any(path.startswith(prefix) for prefix in spec.permitted_outputs) for path in paths)


def ensure_response_path(invocation_id: str, args: argparse.Namespace) -> Path:
    directory = Path(args.log_dir) if args.log_dir else ORCH / "responses"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{invocation_id}.txt"
    if path.exists():
        raise RuntimeError(f"response path collision: {path}")
    path.touch()
    path.unlink()
    return path


def worktree(root: str, invocation_id: str, role: str, authority: dict[str, Any]) -> Path:
    inventory = required_input_inventory(authority, role)
    if not inventory["safe"]:
        raise RuntimeError("role checkout is missing required committed input(s): " + ", ".join(inventory["missing_from_head"]))
    path = Path(root) / f"{role.lower()}-{invocation_id}"
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["git", "worktree", "add", "--detach", str(path), "HEAD"], cwd=ROOT,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"cannot create isolated worktree: {result.stderr.strip()}")
    return path


def build_codex_command(args: argparse.Namespace, worktree_path: Path, final: Path, role: str = "BUILDER") -> list[str]:
    spec = role_spec(role, network_access=getattr(args, "allow_network", False) if role == "BUILDER" else False)
    command = [args.codex_command, "--ask-for-approval", args.approval_policy, "--sandbox", "workspace-write",
               "--model", args.model]
    if spec.network_access:
        command += ["-c", "sandbox_workspace_write.network_access=true"]
    command += ["exec", "--json", "--cd", str(worktree_path), "--output-last-message", str(final)]
    return command


def accept_result(state: dict[str, Any], role: str, invocation_id: str, result: Path, worktree_path: Path) -> str:
    data = json.loads(result.read_text())
    if data.get("invocation_id") != invocation_id or data.get("role_type") != role:
        raise RuntimeError("result envelope identity mismatch")
    conclusion = data.get("conclusion_class")
    if conclusion not in ALLOWED_CONCLUSIONS:
        raise RuntimeError("invalid result envelope conclusion_class")
    if not output_paths_allowed(role, data.get("output_paths", [])):
        raise RuntimeError("result envelope writes outside the role output namespace")
    output_hashes = data.get("output_hashes", {})
    for path, digest in output_hashes.items():
        actual = worktree_path / path if not Path(path).is_absolute() else Path(path)
        if not actual.exists() or sha(actual) != digest:
            raise RuntimeError("result output hash mismatch")
    next_role = route_conclusion(conclusion)
    if role == "INDEPENDENT_VALIDATOR" and conclusion == "PASS":
        next_role = "TERMINAL_COMPLETION"
    state.setdefault("accepted_invocations", [])
    state["last_invocation_id"] = invocation_id
    state["last_conclusion"] = conclusion
    state["accepted_invocations"].append({"invocation_id": invocation_id, "role": role,
        "result_path": rel(result), "result_hash": sha(result), "output_hashes": output_hashes})
    if next_role == "TERMINAL_COMPLETION":
        state.update(current_status="TERMINAL_SUCCESS", required_role="", terminal_status=True,
                     pending_validation=None, next_permitted_milestones=[])
    elif next_role == "HUMAN_STOP":
        state.update(current_status="HUMAN_STOP", required_role="", terminal_status=True,
                     human_intervention_required=True, human_intervention_reason=conclusion)
    else:
        state.update(current_status=f"{next_role}_PENDING", required_role=next_role,
                     pending_validation=VALIDATE if next_role == "INDEPENDENT_VALIDATOR" else state.get("pending_validation"),
                     next_permitted_milestones=[VALIDATE if next_role == "INDEPENDENT_VALIDATOR" else MILESTONE])
    write_state(state)
    ledger("RESULT_ACCEPTED", invocation_id, role=role, conclusion=conclusion, next_action=next_role,
           result_hash=sha(result), output_hashes=output_hashes)
    return next_role


def run_role(args: argparse.Namespace, authority: dict[str, Any], state: dict[str, Any], role: str | None = None) -> int:
    role = role or state["required_role"]
    if role not in ROLE_TEMPLATES:
        return 0
    invocation_id = f"{role.lower()}-{uuid.uuid4().hex[:12]}"
    result = ORCH / "results" / f"{invocation_id}.json"
    result.parent.mkdir(parents=True, exist_ok=True)
    log = ORCH / "logs" / f"{invocation_id}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    final = ensure_response_path(invocation_id, args)
    worktree_path = worktree(args.worktree_root, invocation_id, role, authority)
    builder_outputs: list[str] = []
    if role == "INDEPENDENT_VALIDATOR":
        for accepted in state.get("accepted_invocations", []):
            for output in accepted.get("output_hashes", {}):
                source = Path(output)
                if not source.is_absolute():
                    source = ROOT / source
                if source.exists() and output_paths_allowed("BUILDER", [output]):
                    destination = worktree_path / output
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    if sha(destination) != accepted["output_hashes"][output]:
                        raise RuntimeError("accepted builder output changed before validation")
                    builder_outputs.append(output)
    role_result = worktree_path / rel(ORCH / "results" / f"{invocation_id}.json")
    prompt_path, metadata = prompt(args, invocation_id, role, role_result.relative_to(worktree_path),
                                   ", ".join(builder_outputs))
    command = build_codex_command(args, worktree_path, final, role)
    ledger("ROLE_LAUNCHED", invocation_id, role=role, worktree=str(worktree_path),
           prompt_hash=metadata["prompt_sha256"], process_id=None)
    try:
        with log.open("w") as handle:
            process = subprocess.run(command, input=prompt_path.read_text(), text=True,
                                     stdout=handle, stderr=subprocess.STDOUT, timeout=args.timeout, cwd=worktree_path)
    except subprocess.TimeoutExpired:
        state.update(current_status="HUMAN_STOP", required_role="", terminal_status=True,
                     human_intervention_required=True, human_intervention_reason="Codex invocation timed out")
        write_state(state); ledger("HUMAN_STOP", invocation_id, role=role, next_action="human intervention")
        return 2
    ledger("ROLE_COMPLETED", invocation_id, role=role, exit_code=process.returncode)
    if not role_result.exists():
        state.update(current_status="HUMAN_STOP", required_role="", terminal_status=True,
                     human_intervention_required=True, human_intervention_reason="missing result envelope")
        write_state(state); ledger("HUMAN_STOP", invocation_id, role=role, next_action="human intervention")
        return 2
    shutil.copy2(role_result, result)
    validator = subprocess.run([sys.executable, str(ROOT / "scripts/validate_phase1_cd19_bcma_role_result.py"),
                                str(result), "--root", str(worktree_path)], capture_output=True, text=True)
    if validator.returncode:
        state.update(current_status="HUMAN_STOP", required_role="", terminal_status=True,
                     human_intervention_required=True, human_intervention_reason="invalid result envelope")
        write_state(state); return 2
    envelope = json.loads(result.read_text())
    for output in envelope.get("output_paths", []):
        source = worktree_path / output if not Path(output).is_absolute() else Path(output)
        target = ROOT / output if not Path(output).is_absolute() else Path(output)
        if source.exists() and output_paths_allowed(role, [output]):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    try:
        next_role = accept_result(state, role, invocation_id, result, worktree_path)
    except (ValueError, KeyError, RuntimeError, json.JSONDecodeError) as error:
        state.update(current_status="HUMAN_STOP", required_role="", terminal_status=True,
                     human_intervention_required=True, human_intervention_reason=str(error))
        write_state(state); ledger("HUMAN_STOP", invocation_id, role=role, next_action="human intervention")
        return 2
    print(json.dumps({"invocation_id": invocation_id, "role": role, "worktree": str(worktree_path),
                      "result": str(result), "next_role": next_role}, indent=2))
    return 0


def smoke_test(codex_command: str) -> dict[str, Any]:
    process = subprocess.run([codex_command, "--ask-for-approval", "never", "--sandbox", "read-only",
                              "exec", "Return exactly CODEX_OK"], capture_output=True, text=True, timeout=120)
    exact = process.stdout.strip() == "CODEX_OK" or process.stdout.strip().endswith("CODEX_OK")
    return {"exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr,
            "session_initialized": "thread.started" in process.stdout or "session" in process.stdout.lower(),
            "exact_response_returned": exact}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-from-current-state", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-milestones", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--stop-after")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument("--worktree-root", default="/tmp/phase1_cd19_bcma_worktrees")
    parser.add_argument("--log-dir")
    parser.add_argument("--approval-policy", choices=APPROVAL_POLICIES, default="never")
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--timeout", type=int, default=3600)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_milestones < 1:
        print("--max-milestones must be positive", file=sys.stderr); return 2
    if args.smoke_test:
        print(json.dumps(smoke_test(args.codex_command), indent=2)); return 0
    lock = ORCH / "orchestrator.lock"; ORCH.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, str(os.getpid()).encode()); os.close(fd)
    except FileExistsError:
        print("concurrent orchestrator lock exists", file=sys.stderr); return 2
    try:
        authority = load_authority(); verify_authority(authority)
        if args.preflight:
            print(json.dumps(preflight(authority, "BUILDER"), indent=2)); return 0
        if args.resume and args.start_from_current_state:
            raise RuntimeError("choose --resume or --start-from-current-state")
        if args.resume:
            if not state_path().exists(): raise RuntimeError("resume requires persisted workflow_state.json")
            state = json.loads(state_path().read_text()); verify_resume(state)
        elif args.start_from_current_state:
            state = initial_state(authority)
        else:
            raise RuntimeError("explicit --start-from-current-state or --resume required")
        if args.dry_run:
            print(json.dumps({"dry_run": True, "role_launched": False, "current_state_loaded": True,
                              "authorization_verified": True, "protocol": "1.1.0",
                              "required_role": state["required_role"], "approval_policy": args.approval_policy,
                              "post_build_validator": VALIDATE}, indent=2)); return 0
        if args.start_from_current_state:
            write_state(state)
        for _ in range(args.max_milestones):
            if state.get("terminal_status") or state.get("human_intervention_required"): return 2 if state.get("human_intervention_required") else 0
            if args.stop_after and args.stop_after not in state.get("next_permitted_milestones", []): return 0
            code = run_role(args, authority, state)
            if code: return code
        state.update(current_status="MAX_MILESTONES_REACHED", human_intervention_required=True,
                     human_intervention_reason="maximum milestone limit reached", terminal_status=True)
        write_state(state); ledger("HUMAN_STOP", state.get("last_invocation_id"), next_action="human intervention")
        return 2
    except Exception as error:
        print(f"orchestrator blocked: {error}", file=sys.stderr); return 2
    finally:
        try: lock.unlink()
        except FileNotFoundError: pass


if __name__ == "__main__":
    raise SystemExit(main())
