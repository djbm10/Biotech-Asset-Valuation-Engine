import json
import re
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, "src")
from bve.se.intent import parse_query
from bve.se.intent.target_mentions import analyze_target_mentions
from bve.se.ontology.assertion_sidecar_lookup import SidecarLookup

ROOT = Path.cwd()
B = ROOT / "research/se_target_mention_role_representation_v1"
SIDE = ROOT / "research/se_authority_assertion_provenance_sidecar_v1"
manifest = json.loads((SIDE / "results/artifact_manifest.json").read_text())
hashes = json.loads((SIDE / "input_hashes.json").read_text())
heads = r"(?:therapies|treatments|drugs|agents|antibodies|inhibitors|assets)"
request = r"(?:Find|Show|List|Identify)\s+(?:clinical[- ]stage\s+)?"
patterns = [
    re.compile(request + r"(?P<body>.+?)\s+" + heads + r"(?:\s+for\s+.+?)?[.?]?$", re.I),
    re.compile(
        request
        + heads
        + r"\s+(?:targeting|blocking|binding|inhibiting)\s+(?P<body>.+?)(?:\s+for\s+.+?)?[.?]?$",
        re.I,
    ),
]


def proposal(a):
    q = a.original_query
    g = next((m for p in patterns if (m := p.fullmatch(q))), None)
    if not g:
        return {"rule": "KEEP_OUTSIDE_GRAMMAR"}
    start, end = g.span("body")
    body = q[start:end]
    if body.lower().startswith("anti-"):
        start += 5
        body = body[5:]
    suffix = re.search(r"-(?:directed|targeting|blocking|binding|specific)$", body, re.I)
    if suffix:
        end = start + suffix.start()
    whole = [m for m in a.mentions if m.start == start and m.end == end]
    if not whole:
        return {"rule": "KEEP_NO_WHOLE_AUTHORITY"}
    valid = [
        m
        for m in whole
        if m.status == "RESOLVED"
        and m.authority_evidence
        and len({(e.entity_id, e.component_id) for e in m.authority_evidence}) == 1
        and all(e.entity_id == m.canonical_id for e in m.authority_evidence)
    ]
    if len(valid) != 1:
        return {
            "rule": "UNCERTIFIED_WHOLE_IDENTITY",
            "whole": [m.model_dump(mode="json") for m in whole],
        }
    m = valid[0]
    hit = [s for s in a.production_observations if s.start < end and start < s.end]
    if any(
        s.start < start
        or s.end > end
        or s.kind not in {"TARGET", "AMBIGUOUS_TARGET", "RESIDUAL", "TARGET_LOGIC"}
        for s in hit
    ):
        return {"rule": "OTHER_ROLE_OWNERSHIP"}
    if (
        len(hit) == 1
        and hit[0].kind == "TARGET"
        and hit[0].start == start
        and hit[0].end == end
        and hit[0].entity_id == m.canonical_id
    ):
        return {"rule": "KEEP_ALREADY_WHOLE"}
    return {
        "rule": "A_WHOLE_B_SUPPRESS",
        "start": start,
        "end": end,
        "mention": m.model_dump(mode="json"),
        "removed": [s.model_dump(mode="json") for s in hit],
    }


rows = []
with SidecarLookup(
    Path("/home/djmann/se_runs/target_mention_role_representation_v2/index.sqlite"),
    assertions_sha256=manifest["assertions.jsonl.gz"],
    snapshot_sha256=hashes["data/se/ontology/current/records.jsonl"],
) as side:
    for i, b in enumerate(json.loads((B / "baseline.json").read_text())):
        intent = parse_query(b["query"])
        a = analyze_target_mentions(intent, provenance=side)
        rows.append(dict(b, proposal=proposal(a)))
        if i % 500 == 0:
            print(i, flush=True)
Path("/tmp/role_proposals.json").write_text(json.dumps(rows, indent=2))
print(Counter(r["proposal"]["rule"] for r in rows))
