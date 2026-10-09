"""Snapshot parsed intents for AR3/AR4/AR5 controls (TARGET_AFFIX_RECOGNITION v1)."""
import json, sys
from bve.se.intent.parser import parse_query

QUERIES = {
    "TAC01": "Find clinical-stage CD19 cell therapies for relapsed or refractory B-cell lymphoma.",
    "mint5": "Find clinical-stage dual CD19/BCMA therapies for autoimmune disease with human efficacy.",
    "H1": "Find clinical-stage GPRC5D-directed therapies for relapsed or refractory multiple myeloma.",
    "H2": "Find clinical-stage KRAS G12C inhibitors for non-small cell lung cancer.",
    "H3": "Find clinical-stage FcRn-blocking antibodies for generalized myasthenia gravis.",
    "H4": "Find clinical-stage TL1A antibodies for ulcerative colitis.",
    "H5": "Find clinical-stage Claudin 18.2-directed therapies for gastric cancer.",
    "AMB1": "Find clinical-stage anti-CD20 antibodies for lymphoma.",
    "AMB2": "Find clinical-stage PD-1-directed antibodies for melanoma.",
}
out = {k: json.loads(parse_query(q).model_dump_json()) for k, q in QUERIES.items()}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True)
for k, v in out.items():
    print(k, [t["canonical_id"] for t in v["targets"]], [s["candidates"] for s in v["spans"] if s["kind"] == "AMBIGUOUS_TARGET"])
