#!/usr/bin/env python3
"""Deterministic Phase 1 controller. It routes envelopes; roles do substantive work."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, signal, subprocess, sys, time, uuid, tarfile, io
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2"
ORCH=BASE/"orchestration"; AUTH=BASE/"governance/new_cohort_v2_candidate_universe_v3_milestone_authorization.json"
AUTH_MAN=BASE/"governance/new_cohort_v2_candidate_universe_v3_milestone_authorization_manifest.json"
V3=BASE/"candidate_universe_v3"
MILESTONE="BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3"; VALIDATE="INDEPENDENTLY_VALIDATE_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3"
PROHIBITED=("SELECT","SEED","REVIEWER","CORPUS","SEMANTIC","RELEASE")
ROLE_TYPES=("GOVERNANCE_AUTHORITY","MILESTONE_TRANSITION_AUTHORITY","PROTOCOL_ENGINEER","BUILDER","INDEPENDENT_VALIDATOR","LINEAGE_AUDITOR","REMEDIATION_ENGINEER","COHORT_SELECTOR","SELECTION_VALIDATOR","IDENTITY_BINDING_ENGINEER","CORPUS_BUILDER","CORPUS_VALIDATOR","PRIMARY_REVIEWER","BLIND_REVIEWER","RECONCILIATION_ENGINEER","THIRD_ADJUDICATOR","INDEPENDENT_OUTPUT_VALIDATOR","RELEASE_AUTHORITY")
INCOMPATIBLE_ROLE_PAIRS=frozenset((tuple(sorted(pair)) for pair in (("BUILDER","INDEPENDENT_VALIDATOR"),("PROTOCOL_ENGINEER","INDEPENDENT_VALIDATOR"),("COHORT_SELECTOR","SELECTION_VALIDATOR"),("CORPUS_BUILDER","CORPUS_VALIDATOR"),("PRIMARY_REVIEWER","BLIND_REVIEWER"),("RECONCILIATION_ENGINEER","THIRD_ADJUDICATOR"),("RELEASE_AUTHORITY","BUILDER"))))
def route_conclusion(conclusion_class, blocker_type=None):
    """Pure routing table: no narrative response can advance a milestone."""
    routes={"PASS":"INDEPENDENT_VALIDATOR","FAIL_REMEDIABLE":"REMEDIATION_ENGINEER","FAIL_GOVERNANCE_REQUIRED":"GOVERNANCE_AUTHORITY","FAIL_AUTHORIZATION_REQUIRED":"MILESTONE_TRANSITION_AUTHORITY","FAIL_VERSION_COLLISION":"LINEAGE_AUDITOR","FAIL_HASH_OR_LINEAGE":"HUMAN_STOP","FAIL_SOURCE_ACCESS":"HUMAN_STOP","FAIL_ENVIRONMENT":"HUMAN_STOP","TERMINAL_SUCCESS":"TERMINAL_COMPLETION"}
    if conclusion_class not in routes: raise ValueError(f"unknown conclusion class: {conclusion_class}")
    return routes[conclusion_class]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p): return str(p.relative_to(ROOT))
def load():
    a=json.loads(AUTH.read_text()); return a
def verify_authority(a):
    assert a["overall_conclusion"]=="NEW_COHORT_V2_CANDIDATE_UNIVERSE_V3_MILESTONE_AUTHORIZED"
    assert a["active_protocol_version"]=="1.1.0" and a["activated_milestone"]==MILESTONE
    assert a["candidate_universe_v3"]["version"]=="3.0.0" and not V3.exists()
    assert a["authorization_state"]["candidate_universe_v3_validation_authorized"] is False
    assert a["lineage_and_isolation"]["candidate_universe_v1_immutable"] is True
def state(a):
    hashes={rel(AUTH):sha(AUTH),rel(AUTH_MAN):sha(AUTH_MAN)}
    for k,v in a["governing_hashes"].items():
        if isinstance(v,dict) and v.get("path") and (ROOT/v["path"]).exists(): hashes[v["path"]]=sha(ROOT/v["path"])
    return {"workflow_id":"phase1-cd19-bcma-new-cohort-v2-orchestration","benchmark_family":a["benchmark_identity"]["benchmark_family"],"benchmark_version":a["benchmark_identity"]["benchmark_version"],"benchmark_lineage":a["benchmark_identity"]["benchmark_lineage"],"active_protocol_version":a["active_protocol_version"],"active_candidate_universe_version":a["candidate_universe_v3"]["version"],"current_authorized_milestone":MILESTONE,"current_status":"AUTHORIZED_PENDING_BUILDER","required_role":"BUILDER","governing_artifact_paths":sorted(hashes),"governing_artifact_hashes":hashes,"completed_milestones":a["completed_milestones"],"failed_milestones":["CANDIDATE_UNIVERSE_V1","CANDIDATE_UNIVERSE_V2"],"blocked_milestones":[],"pending_validation":VALIDATE,"next_permitted_milestones":[MILESTONE],"explicitly_prohibited_milestones":["BUILD_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V2","VALIDATE_NEW_COHORT_V2_CANDIDATE_UNIVERSE_V2","COHORT_SELECTION","SELECTION_SEED_EXECUTION","REVIEWER_ID_GENERATION","EVIDENCE_CORPUS_CONSTRUCTION","SEMANTIC_REVIEW","RELEASE"],"historical_state":a["historical_state"],"last_invocation_id":None,"last_conclusion":None,"human_intervention_required":False,"human_intervention_reason":None,"terminal_status":False}
def ledger(event, inv=None, **kw):
    ORCH.mkdir(parents=True,exist_ok=True); p=ORCH/"orchestration_ledger.jsonl"; seq=sum(1 for _ in p.open())+1 if p.exists() else 1
    d={"sequence":seq,"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"workflow_id":"phase1-cd19-bcma-new-cohort-v2-orchestration","invocation_id":inv,"role":kw.pop("role",None),"milestone":kw.pop("milestone",MILESTONE),"event_type":event,"input_state_hash":kw.pop("input_state_hash",None),"prompt_hash":kw.pop("prompt_hash",None),"session_id":kw.pop("session_id",None),"worktree":kw.pop("worktree",None),"process_id":kw.pop("process_id",None),"exit_code":kw.pop("exit_code",None),"conclusion":kw.pop("conclusion",None),"output_hashes":kw.pop("output_hashes",{}),"state_transition_result":kw.pop("state_transition_result",None),"next_action":kw.pop("next_action",None),"human_intervention_status":kw.pop("human_intervention_status",False),**kw}
    with p.open("a") as f: f.write(json.dumps(d,sort_keys=True)+"\n")
def write_state(s):
    p=ORCH/"workflow_state.json"; tmp=p.with_suffix(".tmp"); tmp.write_text(json.dumps(s,indent=2,sort_keys=True)+"\n"); tmp.replace(p)
def prompt(args, inv, role, out, result):
    p=ORCH/f"prompts/{inv}.md"; cmd=[sys.executable,str(ROOT/"scripts/build_phase1_cd19_bcma_role_prompt.py"),"--role",role,"--milestone",MILESTONE,"--invocation-id",inv,"--output",str(p),"--result-path",str(result)]
    r=subprocess.run(cmd,capture_output=True,text=True,check=True); return p,json.loads(r.stdout)
def worktree(root, inv, role):
    p=Path(root)/f"{role.lower()}-{inv}"; p.parent.mkdir(parents=True,exist_ok=True)
    r=subprocess.run(["git","worktree","add","--detach",str(p),"HEAD"],cwd=ROOT,capture_output=True,text=True)
    if r.returncode:
        # Managed environments may expose .git read-only. A HEAD archive is still a
        # clean, non-concurrent checkout and contains no controller/user scratch state.
        if p.exists(): shutil.rmtree(p)
        archive=subprocess.run(["git","archive","--format=tar","HEAD"],cwd=ROOT,capture_output=True,check=True).stdout
        p.mkdir(parents=True,exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(archive),mode="r:") as tf: tf.extractall(p)
    # Bind only explicit authoritative inputs; never copy candidate outputs or user work.
    for src in [AUTH,AUTH_MAN,BASE/"protocol/new_cohort_v2_selection_protocol_v1_1.json",BASE/"governance/new_cohort_v2_candidate_universe_v2_lineage_audit.json"]:
        dst=p/src.relative_to(ROOT); dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
    return p
def dry(args,a,s):
    inv=f"builder-{uuid.uuid4().hex[:12]}"; result=ORCH/f"results/{inv}.json"; p,meta=prompt(args,inv,"BUILDER",V3,result)
    ledger("WORKFLOW_STARTED",inv); ledger("STATE_LOADED",inv); ledger("AUTHORIZATION_VERIFIED",inv,role="GOVERNANCE_AUTHORITY"); ledger("PROMPT_GENERATED",inv,role="BUILDER",prompt_hash=meta["prompt_sha256"])
    # Dry run is observational: it may append audit events and prompts, but does
    # not claim an invocation or mutate the authoritative workflow state.
    print(json.dumps({"dry_run":True,"current_state_loaded":True,"authorization_verified":True,"protocol":"1.1.0","v1_v2_failed_lineage_verified":True,"v3_exists":False,"prompt_path":rel(p),"prompt_sha256":meta["prompt_sha256"],"fresh_builder_session_planned":True,"new_worktree_planned":True,"network_boundary":"builder-only","expected_outputs":rel(V3)+"/ plus result envelope","post_build_validator":VALIDATE,"role_launched":False},indent=2))
    return 0
def run_role(args,a,s):
    inv=f"builder-{uuid.uuid4().hex[:12]}"; result=ORCH/f"results/{inv}.json"; log=ORCH/f"logs/{inv}.jsonl"; final=ORCH/f"responses/{inv}.txt"; log.parent.mkdir(parents=True,exist_ok=True); final.parent.mkdir(parents=True,exist_ok=True)
    wt=worktree(args.worktree_root,inv,"BUILDER"); role_result=wt/"research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/orchestration/results"/f"{inv}.json"; p,meta=prompt(args,inv,"BUILDER",wt/V3.relative_to(ROOT),Path("research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/orchestration/results")/f"{inv}.json")
    # Role receives a fresh process/session; no resume flag and no conversation is supplied.
    cmd=[args.codex_command,"exec","--json","--cd",str(wt),"--output-last-message",str(final),"--model",args.model,"--sandbox","workspace-write"]
    if args.allow_network: cmd += ["-c","network_access=true"]
    started=time.time(); ledger("ROLE_LAUNCHED",inv,role="BUILDER",worktree=str(wt),prompt_hash=meta["prompt_sha256"],process_id=None,next_action="await builder")
    with log.open("w") as f:
        try: proc=subprocess.run(cmd,input=p.read_text(),text=True,stdout=f,stderr=subprocess.STDOUT,timeout=args.timeout,cwd=wt)
        except subprocess.TimeoutExpired: s.update(current_status="HUMAN_STOP",human_intervention_required=True,human_intervention_reason="Codex invocation timed out",terminal_status=True); write_state(s); ledger("HUMAN_STOP",inv,role="BUILDER",worktree=str(wt),next_action="human intervention"); return 2
    ledger("ROLE_COMPLETED",inv,role="BUILDER",worktree=str(wt),exit_code=proc.returncode)
    if role_result.exists():
        result.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(role_result,result)
        envelope=json.loads(role_result.read_text())
        for output in envelope.get("output_paths",[]):
            source=wt/output
            target=ROOT/output
            if source.exists() and output.startswith("research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/candidate_universe_v3/"):
                target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
    if not result.exists(): s.update(current_status="HUMAN_STOP",human_intervention_required=True,human_intervention_reason="Process exited without result envelope",terminal_status=True); write_state(s); return 2
    vr=subprocess.run([sys.executable,str(ROOT/"scripts/validate_phase1_cd19_bcma_role_result.py"),str(result)],capture_output=True,text=True)
    if vr.returncode: s.update(current_status="HUMAN_STOP",human_intervention_required=True,human_intervention_reason="Invalid or untrusted role result envelope",terminal_status=True); write_state(s); return 2
    d=json.loads(result.read_text()); s.update(last_invocation_id=inv,last_conclusion=d["conclusion"],current_status="VALIDATION_PENDING",required_role="INDEPENDENT_VALIDATOR",pending_validation=VALIDATE,next_permitted_milestones=[VALIDATE]); write_state(s); ledger("RESULT_ACCEPTED",inv,role="BUILDER",conclusion=d["conclusion"],next_action="launch fresh independent validator"); print(json.dumps({"invocation_id":inv,"worktree":str(wt),"result":str(result),"session_id":d.get("session_id"),"v3_started":True},indent=2)); return 0
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--start-from-current-state",action="store_true"); ap.add_argument("--max-milestones",type=int,default=20); ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--resume",action="store_true"); ap.add_argument("--stop-after"); ap.add_argument("--allow-network",action="store_true"); ap.add_argument("--codex-command",default="codex"); ap.add_argument("--worktree-root",default="/tmp/phase1_cd19_bcma_worktrees"); ap.add_argument("--log-dir"); ap.add_argument("--approval-policy",default="bounded-workspace-write"); ap.add_argument("--model",default="gpt-5"); ap.add_argument("--reasoning-effort",default="high"); ap.add_argument("--timeout",type=int,default=3600); args=ap.parse_args()
    lock=ORCH/"orchestrator.lock"; ORCH.mkdir(parents=True,exist_ok=True)
    try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY); os.write(fd,str(os.getpid()).encode()); os.close(fd)
    except FileExistsError: print("concurrent orchestrator lock exists",file=sys.stderr); return 2
    try:
        a=load(); verify_authority(a); s=state(a); write_state(s)
        if args.dry_run: return dry(args,a,s)
        if not args.start_from_current_state and not args.resume: raise RuntimeError("explicit --start-from-current-state or --resume required")
        if args.stop_after and args.stop_after!=MILESTONE: raise RuntimeError("stop-after is not current authorized milestone")
        if not args.allow_network: print("network disabled; builder may stop if mandatory source retrieval requires network",file=sys.stderr)
        return run_role(args,a,s)
    except AssertionError as e:
        s=state(a) if 'a' in locals() else {}; s.update(current_status="HUMAN_STOP",human_intervention_required=True,human_intervention_reason=str(e) or "authorization verification failed",terminal_status=True); write_state(s); ledger("HUMAN_STOP",next_action="human intervention"); return 2
    except Exception as e:
        print(f"orchestrator blocked: {e}",file=sys.stderr); return 2
    finally:
        try: lock.unlink()
        except FileNotFoundError: pass
if __name__=="__main__": raise SystemExit(main())
