from __future__ import annotations
import hashlib, json, subprocess, sys
from types import SimpleNamespace
from pathlib import Path
import pytest

ROOT=Path(__file__).parents[1]
RUN=ROOT/"scripts/run_phase1_cd19_bcma_orchestrator.py"
AUTH=ROOT/"research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/governance/new_cohort_v2_candidate_universe_v3_milestone_authorization.json"
ORCH=AUTH.parent.parent/"orchestration"
from importlib.util import spec_from_file_location, module_from_spec
spec=spec_from_file_location("phase1_orch", RUN); mod=module_from_spec(spec); spec.loader.exec_module(mod)

def run(*args):
    return subprocess.run([sys.executable,str(RUN),*args],cwd=ROOT,text=True,capture_output=True)

def test_current_authorization_dry_run_and_no_role_launch():
    r=run("--start-from-current-state","--dry-run","--stop-after","BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3")
    assert r.returncode==0, r.stderr
    d=json.loads(r.stdout); assert d["authorization_verified"] and not d["role_launched"]
    assert d["protocol"]=="1.1.0" and d["post_build_validator"].startswith("INDEPENDENTLY")

def test_authority_rejects_wrong_protocol(monkeypatch, tmp_path):
    data=json.loads(AUTH.read_text()); data["active_protocol_version"]="9.9.9"
    original=AUTH.read_bytes(); AUTH.write_text(json.dumps(data))
    try:
        r=run("--start-from-current-state","--dry-run")
        assert r.returncode != 0
    finally: AUTH.write_bytes(original)

def test_result_validator_rejects_missing_and_altered_output(tmp_path):
    result=tmp_path/"result.json"; result.write_text(json.dumps({"invocation_id":"x"}))
    r=subprocess.run([sys.executable,str(ROOT/"scripts/validate_phase1_cd19_bcma_role_result.py"),str(result)],capture_output=True,text=True)
    assert r.returncode==1

def envelope(**overrides):
    d={"invocation_id":"i","role_identity":"builder","role_type":"BUILDER","assigned_milestone":"BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3","conclusion":"ok","conclusion_class":"PASS","input_paths":[],"input_hashes":{},"output_paths":[],"output_hashes":{},"files_created":[],"files_modified":[],"files_deleted":[],"governing_authorization_verified":True,"authorization_boundary_respected":True,"tests_run":[],"tests_passed":True,"accepted_malformed_input_count":0,"enforcement_gap_count":0,"next_milestone_claimed":"INDEPENDENTLY_VALIDATE_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3","blocker_type":None,"blocker_details":None,"human_intervention_required":False,"parent_invocation_id":None,"session_id":"s","worktree_path":"/tmp/w","execution_log_path":"/tmp/l"}
    d.update(overrides); return d

def test_result_validator_hashes_declared_outputs(tmp_path):
    output=tmp_path/"out.json"; output.write_text("good")
    result=tmp_path/"result.json"; result.write_text(json.dumps(envelope(output_paths=[str(output)],output_hashes={str(output):hashlib.sha256(b"bad").hexdigest()})))
    r=subprocess.run([sys.executable,str(ROOT/"scripts/validate_phase1_cd19_bcma_role_result.py"),str(result),"--root","/"],capture_output=True,text=True)
    assert r.returncode==1

def test_incompatible_role_pairs_are_documented():
    text=(ROOT/"docs/phase1_cd19_bcma_orchestration.md").read_text()
    assert "Builder and validator" in text and "Selector and selection validator" in text

def test_codex_command_puts_global_options_before_exec():
    args=SimpleNamespace(codex_command="codex", approval_policy="on-request",
                         allow_network=True, model="gpt-5")
    command=mod.build_codex_command(args, Path("/tmp/builder-wt"),
                                    Path("/tmp/builder-output.txt"))
    assert command == [
        "codex", "--ask-for-approval", "on-request", "--sandbox", "workspace-write",
        "--model", "gpt-5", "-c", "sandbox_workspace_write.network_access=true", "exec", "--json", "--cd",
        "/tmp/builder-wt", "--output-last-message", "/tmp/builder-output.txt",
    ]
    assert command.index("exec") > command.index("--ask-for-approval")
    assert command.index("exec") < command.index("--json")

@pytest.mark.parametrize("klass,next_role", [("PASS","INDEPENDENT_VALIDATOR"),("FAIL_REMEDIABLE","REMEDIATION_ENGINEER"),("FAIL_GOVERNANCE_REQUIRED","GOVERNANCE_AUTHORITY"),("FAIL_VERSION_COLLISION","LINEAGE_AUDITOR"),("FAIL_HASH_OR_LINEAGE","HUMAN_STOP"),("TERMINAL_SUCCESS","TERMINAL_COMPLETION")])
def test_deterministic_conclusion_routing(klass,next_role):
    assert mod.route_conclusion(klass)==next_role

def test_unknown_conclusion_is_rejected():
    with pytest.raises(ValueError): mod.route_conclusion("UNKNOWN")

def test_approval_policy_defaults_to_never_and_only_documented_values_are_valid():
    assert mod.parse_args([]).approval_policy == "never"
    for value in ("untrusted", "on-request", "never"):
        assert mod.parse_args(["--approval-policy", value]).approval_policy == value
    with pytest.raises(SystemExit):
        mod.parse_args(["--approval-policy", "bounded-workspace-write"])

def test_network_configuration_is_builder_only_and_exactly_keyed():
    base = SimpleNamespace(codex_command="codex", approval_policy="never",
                           allow_network=False, model="gpt-5")
    without = mod.build_codex_command(base, Path("/tmp/builder-wt"), Path("/tmp/out"))
    assert "network_access=true" not in " ".join(without)
    base.allow_network = True
    with_network = mod.build_codex_command(base, Path("/tmp/builder-wt"), Path("/tmp/out"))
    config_index = with_network.index("-c")
    assert ["-c", "sandbox_workspace_write.network_access=true"] == with_network[config_index:config_index + 2]
    validator = mod.build_codex_command(base, Path("/tmp/validator-wt"), Path("/tmp/out"),
                                        "INDEPENDENT_VALIDATOR")
    assert "sandbox_workspace_write.network_access=true" not in validator
    assert mod.role_spec("BUILDER").network_access is True
    assert mod.role_spec("INDEPENDENT_VALIDATOR").network_access is False

def test_role_specs_are_distinct_and_validator_is_independent():
    builder = mod.role_spec("BUILDER")
    validator = mod.role_spec("INDEPENDENT_VALIDATOR")
    assert builder.role_type != validator.role_type
    assert builder.template != validator.template
    assert builder.permitted_outputs != validator.permitted_outputs
    assert builder.required_next_gate == mod.VALIDATE
    assert validator.required_next_gate is None

def test_successful_result_envelope_path_returns_without_name_error(monkeypatch, tmp_path):
    result = tmp_path / "builder.json"
    result.write_text(json.dumps(envelope(invocation_id="builder-1", role_type="BUILDER")))
    state = {"accepted_invocations": [], "last_invocation_id": None,
             "last_conclusion": None, "pending_validation": mod.VALIDATE}
    monkeypatch.setattr(mod, "write_state", lambda state: None)
    monkeypatch.setattr(mod, "ledger", lambda *args, **kwargs: None)
    assert mod.accept_result(state, "BUILDER", "builder-1", result, tmp_path) == "INDEPENDENT_VALIDATOR"
    assert state["required_role"] == "INDEPENDENT_VALIDATOR"

@pytest.mark.parametrize("role,klass,next_role", [
    ("BUILDER", "PASS", "INDEPENDENT_VALIDATOR"),
    ("INDEPENDENT_VALIDATOR", "FAIL_REMEDIABLE", "REMEDIATION_ENGINEER"),
    ("INDEPENDENT_VALIDATOR", "FAIL_GOVERNANCE_REQUIRED", "GOVERNANCE_AUTHORITY"),
    ("INDEPENDENT_VALIDATOR", "FAIL_VERSION_COLLISION", "LINEAGE_AUDITOR"),
])
def test_role_aware_routing(role, klass, next_role, monkeypatch, tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps(envelope(invocation_id="i", role_type=role, conclusion_class=klass)))
    state = {"accepted_invocations": [], "last_invocation_id": None,
             "last_conclusion": None, "pending_validation": mod.VALIDATE}
    monkeypatch.setattr(mod, "write_state", lambda state: None)
    monkeypatch.setattr(mod, "ledger", lambda *args, **kwargs: None)
    assert mod.accept_result(state, role, "i", result, tmp_path) == next_role

def test_validator_pass_is_terminal_and_accepted_milestone_is_not_rerun(monkeypatch, tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps(envelope(invocation_id="validator-1",
                                           role_type="INDEPENDENT_VALIDATOR",
                                           conclusion_class="PASS")))
    state = {"accepted_invocations": [], "last_invocation_id": None,
             "last_conclusion": None, "pending_validation": mod.VALIDATE}
    monkeypatch.setattr(mod, "write_state", lambda state: None)
    monkeypatch.setattr(mod, "ledger", lambda *args, **kwargs: None)
    assert mod.accept_result(state, "INDEPENDENT_VALIDATOR", "validator-1", result, tmp_path) == "TERMINAL_COMPLETION"
    assert state["terminal_status"] is True
    assert state["accepted_invocations"][0]["invocation_id"] == "validator-1"

def test_missing_resume_state_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "state_path", lambda: tmp_path / "missing-state.json")
    with pytest.raises(RuntimeError, match="persisted workflow_state"):
        mod.verify_resume({})

def test_invalid_and_missing_result_envelopes_are_rejected(tmp_path):
    missing = tmp_path / "missing.json"
    missing.write_text("{}")
    invalid = subprocess.run([sys.executable, str(ROOT / "scripts/validate_phase1_cd19_bcma_role_result.py"),
                              str(missing)], capture_output=True, text=True)
    assert invalid.returncode != 0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(envelope(conclusion_class="NOT_A_CLASS")))
    invalid = subprocess.run([sys.executable, str(ROOT / "scripts/validate_phase1_cd19_bcma_role_result.py"),
                              str(bad)], capture_output=True, text=True)
    assert invalid.returncode != 0
