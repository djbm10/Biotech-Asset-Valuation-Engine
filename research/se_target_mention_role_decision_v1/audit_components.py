import gzip
import json
from pathlib import Path
from collections import defaultdict

rows = json.load(open("/tmp/role_proposals.json"))
candidates = [r for r in rows if r["proposal"]["rule"] == "A_WHOLE_B_SUPPRESS"]
component_ids = {
    e["component_id"] for r in candidates for e in r["proposal"]["mention"]["authority_evidence"]
}
components = {}
symbols = defaultdict(dict)
with gzip.open(
    "/home/djmann/se_runs/authority_assertion_provenance_sidecar_v1/seed0/assertions.jsonl.gz", "rt"
) as f:
    for line in f:
        r = json.loads(line)
        for c in r["resolver_components"]:
            if c["component_id"] in component_ids:
                components[c["component_id"]] = c
                if r["field_path"] == ["approvedSymbol"]:
                    symbols[c["component_id"]][r["source_record_key"]] = {
                        "raw_symbol": r["raw_component"],
                        "assertion_id": r["assertion_id"],
                        "artifact_sha256": r["artifact_sha256"],
                        "field_path": r["field_path"],
                        "record_id": r["record_id"],
                    }
audit = []
for r in candidates:
    m = r["proposal"]["mention"]
    ids = {e["component_id"] for e in m["authority_evidence"]}
    cs = [{"component": components[c], "symbols": symbols[c]} for c in sorted(ids)]
    multiple = any(len(c["symbols"]) > 1 for c in cs)
    audit.append(
        {
            "id": r["id"],
            "query": r["query"],
            "canonical_id": m["canonical_id"],
            "mention": m,
            "multiple_source_gene_records": multiple,
            "components": cs,
        }
    )
Path("/tmp/role_component_audit.json").write_text(json.dumps(audit, indent=2))
print(
    json.dumps(
        {
            "candidate_rows": len(audit),
            "multiple_source_gene_rows": sum(a["multiple_source_gene_records"] for a in audit),
            "multiple_source_components": len(
                {
                    c["component"]["component_id"]
                    for a in audit
                    if a["multiple_source_gene_records"]
                    for c in a["components"]
                }
            ),
            "source_component_count": len(components),
        },
        indent=2,
    )
)
