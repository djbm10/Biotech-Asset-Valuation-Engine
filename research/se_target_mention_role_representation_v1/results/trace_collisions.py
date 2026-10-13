"""Read-only source-component evidence for the frozen provenance failures."""

import json
from pathlib import Path
from bve.se.ontology.records import EntityType, normalize_lookup_key
from bve.se.ontology.targets import get_resolver

p = Path("/tmp/mention_v1_results")
failures = json.loads((p / "provenance_failure_diagnosis.json").read_text())
keys = sorted(
    {
        (r["lookup_text"], f["entity_id"])
        for r in failures
        for f in r["findings"]
        if f["reason"] == "resolved_lookup_has_no_matching_source_assertion_in_retrieved_entity"
    }
)
r = get_resolver()
rows = []
for text, entity_id in keys:
    components = []
    for entity in r.entities_of_type(EntityType.TARGET):
        if entity.canonical_id != entity_id:
            continue
        components.append(
            {
                "canonical_id": entity.canonical_id,
                "source_record_keys": [s.record_key for s in entity.source_records],
                "matching_aliases": [
                    a.model_dump(mode="json")
                    for a in entity.aliases
                    if normalize_lookup_key(a.value) == normalize_lookup_key(text)
                ],
                "source_records": [s.model_dump(mode="json") for s in entity.source_records],
            }
        )
    rows.append(
        {
            "lookup_text": text,
            "canonical_id": entity_id,
            "components": components,
            "get_source_records": [s.record_key for s in r.get(entity_id).source_records],
        }
    )
(p / "canonical_id_collisions.json").write_text(
    json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
)
print(
    json.dumps(
        [
            {
                "lookup": x["lookup_text"],
                "id": x["canonical_id"],
                "components": len(x["components"]),
                "records": [c["source_record_keys"] for c in x["components"]],
            }
            for x in rows
        ],
        indent=2,
    )
)
