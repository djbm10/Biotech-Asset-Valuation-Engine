#!/usr/bin/env python3
"""Strict structural and custody validation for role result envelopes."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"PASS","FAIL_REMEDIABLE","FAIL_GOVERNANCE_REQUIRED","FAIL_AUTHORIZATION_REQUIRED","FAIL_VERSION_COLLISION","FAIL_HASH_OR_LINEAGE","FAIL_SOURCE_ACCESS","FAIL_ENVIRONMENT","TERMINAL_SUCCESS"}
REQUIRED = json.loads((ROOT/"research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/orchestration/role_result.schema.json").read_text())["required"]
def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("result"); ap.add_argument("--root",default=str(ROOT)); a=ap.parse_args()
    try: d=json.loads(Path(a.result).read_text())
    except Exception as e: print(f"invalid JSON: {e}"); return 2
    missing=[k for k in REQUIRED if k not in d]; errors=[]
    if missing: errors.append("missing="+",".join(missing))
    if d.get("conclusion_class") not in ALLOWED: errors.append("invalid conclusion_class")
    if d.get("accepted_malformed_input_count") != 0: errors.append("accepted malformed input")
    if d.get("enforcement_gap_count") != 0: errors.append("enforcement gap")
    root=Path(a.root)
    for p,h in d.get("output_hashes",{}).items():
        f=root/p if not Path(p).is_absolute() else Path(p)
        if not f.exists(): errors.append(f"missing output: {p}")
        elif hashlib.sha256(f.read_bytes()).hexdigest()!=h: errors.append(f"hash mismatch: {p}")
    if errors: print(json.dumps({"valid":False,"errors":errors})); return 1
    print(json.dumps({"valid":True,"invocation_id":d["invocation_id"],"conclusion_class":d["conclusion_class"]})); return 0
if __name__ == "__main__": raise SystemExit(main())
