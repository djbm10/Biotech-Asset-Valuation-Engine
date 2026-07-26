#!/usr/bin/env python3
"""Render a bounded, hash-bound prompt for one fresh orchestration role."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/governance/new_cohort_v2_candidate_universe_v3_milestone_authorization.json"
ORCH = AUTH.parent.parent / "orchestration"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--milestone", required=True)
    ap.add_argument("--invocation-id", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--result-path", required=True)
    ap.add_argument("--builder-outputs", default="")
    args = ap.parse_args()
    auth = json.loads(AUTH.read_text())
    templates = {"BUILDER":"build_v3.md", "INDEPENDENT_VALIDATOR":"validate_v3.md", "MILESTONE_TRANSITION_AUTHORITY":"governance_transition.md", "REMEDIATION_ENGINEER":"remediation_v3.md", "LINEAGE_AUDITOR":"lineage_audit.md", "GOVERNANCE_AUTHORITY":"protocol_amendment.md"}
    template = ORCH / "prompt_templates" / templates.get(args.role, "governance_transition.md")
    paths = [str(AUTH.relative_to(ROOT)), "research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/protocol/new_cohort_v2_selection_protocol_v1_1.json", "research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/governance/new_cohort_v2_candidate_universe_v2_lineage_audit.json"]
    text = template.read_text().format(protocol_version=auth["active_protocol_version"], milestone=args.milestone, v3_namespace=auth["candidate_universe_v3"]["namespace"], authorization_path=paths[0], input_paths=", ".join(paths), output_namespace=auth["candidate_universe_v3"]["namespace"], result_path=args.result_path, builder_outputs=args.builder_outputs)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(text)
    print(json.dumps({"prompt_path": str(out), "prompt_sha256": sha(out), "role": args.role, "invocation_id": args.invocation_id, "input_hashes": {p: sha(ROOT/p) for p in paths}}))
    return 0
if __name__ == "__main__": raise SystemExit(main())
