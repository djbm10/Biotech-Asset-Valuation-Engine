"""Trace frozen failed provenance checks without changing candidate or acceptance."""

import json
from collections import Counter
from pathlib import Path
from bve.se.intent import parse_query
from bve.se.intent.target_mentions import analyze_target_mentions
from bve.se.ontology.records import normalize_lookup_key
from bve.se.ontology.targets import get_resolver

ROOT = Path("/home/djmann/projects/bve-b8")
P = Path("/tmp/mention_v1_results")
failed = json.loads((P / "evaluation_seed_0.json").read_text())["failures"]
queries = {
    r["id"]: r["query"]
    for r in json.loads(
        (ROOT / "research/se_target_mention_role_representation_v1/baseline.json").read_text()
    )
}
rows = []
for f in failed:
    intent = parse_query(queries[f["id"]])
    analysis = analyze_target_mentions(intent)
    m = next(m for m in analysis.mentions if m.mention_id == f["mention"])
    resolver = get_resolver()
    raw = resolver.resolve(m.lookup_text)
    findings = []
    for e in m.authority_evidence:
        entity = resolver.get(e.entity_id)
        source = {r.record_key: r for r in entity.source_records}
        if not e.matching_aliases and e.basis != "CANONICAL_ID":
            findings.append(
                {
                    "reason": "resolved_lookup_has_no_matching_source_assertion_in_retrieved_entity",
                    "entity_id": e.entity_id,
                    "entity_source_records": [
                        r.model_dump(mode="json") for r in entity.source_records
                    ],
                    "resolver_basis": raw.basis.model_dump(mode="json") if raw.basis else None,
                    "snapshot_exact_alias_records": [
                        r.record_key
                        for r in resolver.snapshot.records
                        if any(
                            a.normalized == normalize_lookup_key(m.lookup_text)
                            for a in r.all_aliases()
                        )
                    ],
                }
            )
        for a in e.matching_aliases:
            r = source[a.record_key]
            fields = {(v.value, v.alias_type.value) for v in r.aliases} | {
                (r.canonical_symbol, "SYMBOL"),
                (r.label, "APPROVED_NAME"),
            }
            if (a.value, a.alias_type) not in fields:
                findings.append(
                    {
                        "reason": "reported_alias_is_transformed_source_field_without_transform_provenance",
                        "assertion": a.model_dump(mode="json"),
                        "raw_label": r.label,
                        "raw_symbol": r.canonical_symbol,
                        "source_all_aliases": [
                            v.model_dump(mode="json")
                            for v in r.all_aliases()
                            if v.normalized == normalize_lookup_key(m.lookup_text)
                        ],
                    }
                )
    rows.append(
        {
            "id": f["id"],
            "query": queries[f["id"]],
            "surface": m.surface,
            "lookup_text": m.lookup_text,
            "findings": findings,
        }
    )
(P / "provenance_failure_diagnosis.json").write_text(
    json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
)
print(
    json.dumps(
        {
            "failures": len(rows),
            "with_findings": sum(bool(r["findings"]) for r in rows),
            "reasons": dict(Counter(x["reason"] for r in rows for x in r["findings"])),
            "surfaces": dict(Counter(r["surface"] for r in rows)),
        },
        indent=2,
    )
)
