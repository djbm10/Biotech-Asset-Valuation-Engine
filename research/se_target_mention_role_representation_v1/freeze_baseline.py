"""Freeze exact current parser/compiler decisions and required mention intervals."""

import hashlib
import json
from datetime import date
from pathlib import Path
from bve.se.intent import parse_query, compile_intent, build_buyer_identity, intent_to_trial_query
from bve.se.intent.compiler import IntentNotCompilable

ROOT = Path("/home/djmann/projects/bve-b8")
OUT = Path("/tmp/mention_v1")
OUT.mkdir(exist_ok=True)
BUYER = build_buyer_identity("representation-neutrality", as_of_date=date(2026, 10, 12))


def digest(x):
    return hashlib.sha256(
        json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def decision(intent):
    try:
        problem = compile_intent(intent, buyer=BUYER).model_dump(mode="json")
    except IntentNotCompilable as error:
        problem = {"blockers": error.blockers}
    try:
        trial = intent_to_trial_query(intent, as_of_date=date(2026, 10, 12)).model_dump(mode="json")
    except IntentNotCompilable as error:
        trial = {"blockers": error.blockers}
    return {"intent": intent.model_dump(mode="json"), "problem": problem, "trial_query": trial}


paths = [
    "research/se_target_authority_span_query_role_contract_v1/results/audit.json",
    "research/se_target_authority_span_query_role_contract_v1/structural_controls.json",
    "research/se_target_query_alias_coverage_v1/survey_baseline.json",
    "research/target_reference_identity_surface_diagnosis_v1/current_scientific_baseline.json",
]
audit = json.loads((ROOT / paths[0]).read_text())
queries = []
requirements = []
for i, r in enumerate(audit):
    qid = f"diagnosis:{i:04}"
    queries.append({"id": qid, "query": r["query"]})
    spans = []
    for s in r["candidate_spans"]:
        a = s["authority"]
        if a["status"] != "UNRESOLVED" or a["all_claimants"]:
            spans.append(
                {
                    "start": s["start"],
                    "end": s["end"],
                    "lookup_text": s["text"],
                    "status": a["status"],
                    "entity_id": a["entity_id"],
                    "claimants": a["all_claimants"],
                }
            )
    requirements.append(
        {
            "id": qid,
            "witness_id": r["witness_id"],
            "spelling": r["spelling"],
            "frame": r["frame"],
            "known_English_mismatch": bool(r["current_outside_reference"])
            and r["spelling"] == "original_authority_name",
            "protected_Greek": r["preservation_obligation_unmet_by_whole_name_only"],
            "required_spans": spans,
        }
    )
for i, r in enumerate(json.loads((ROOT / paths[1]).read_text())["rows"]):
    queries.append({"id": r["id"], "query": r["query"]})
for i, r in enumerate(json.loads((ROOT / paths[2]).read_text())["rows"]):
    for j, frame in enumerate(r["frames"]):
        queries.append({"id": f"alias:{i:03}:{j}", "query": frame["query"]})
for r in json.loads((ROOT / paths[3]).read_text())["rows"]:
    queries.append({"id": "adopted:" + r["id"], "query": r["query"]})
rows = []
for q in queries:
    intent = parse_query(q["query"])
    rows.append({**q, "decision_sha256": digest(decision(intent))})
manifest = {
    "baseline": "92e8f56",
    "seed": 0,
    "rows": len(rows),
    "input_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
}
for name, value in [
    ("baseline.json", rows),
    ("required_mentions.json", requirements),
    ("manifest.json", manifest),
]:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
print(
    json.dumps(
        {
            "rows": len(rows),
            "required_observations": len(requirements),
            "required_spans": sum(len(r["required_spans"]) for r in requirements),
        }
    )
)
