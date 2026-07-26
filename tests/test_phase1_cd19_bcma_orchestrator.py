from __future__ import annotations
import hashlib, json, subprocess, sys
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

@pytest.mark.parametrize("klass,next_role", [("PASS","INDEPENDENT_VALIDATOR"),("FAIL_REMEDIABLE","REMEDIATION_ENGINEER"),("FAIL_GOVERNANCE_REQUIRED","GOVERNANCE_AUTHORITY"),("FAIL_VERSION_COLLISION","LINEAGE_AUDITOR"),("FAIL_HASH_OR_LINEAGE","HUMAN_STOP"),("TERMINAL_SUCCESS","TERMINAL_COMPLETION")])
def test_deterministic_conclusion_routing(klass,next_role):
    assert mod.route_conclusion(klass)==next_role

def test_unknown_conclusion_is_rejected():
    with pytest.raises(ValueError): mod.route_conclusion("UNKNOWN")
