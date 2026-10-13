"""Offline snapshot provenance audit; no production mutations."""

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from bve.se.ontology.records import EntityType, normalize_lookup_key
from bve.se.ontology.targets import default_snapshot_path, get_resolver

ROOT = Path("/home/djmann/projects/bve-b8")
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
MODE = sys.argv[1]
SNAP = default_snapshot_path()
raw_bytes = (SNAP / "records.jsonl").read_bytes()
digest = hashlib.sha256(raw_bytes).hexdigest()
resolver = get_resolver()
components = list(resolver.entities_of_type(EntityType.TARGET))
by_record = defaultdict(list)
by_id = defaultdict(list)
for entity in components:
    keys = sorted(r.record_key for r in entity.source_records)
    component = {
        "component_id": hashlib.sha256(json.dumps(keys).encode()).hexdigest(),
        "record_keys": keys,
        "canonical_id": entity.canonical_id,
    }
    by_id[entity.canonical_id].append(component)
    for key in keys:
        by_record[key].append(component)
assertions = defaultdict(list)
raw_records = {}
for line_number, line in enumerate(raw_bytes.splitlines(), 1):
    record = json.loads(line)
    if record["entity_type"] != "TARGET":
        continue
    key = record["source"] + ":" + record["source_id"]
    raw_records[key] = record
    fields = [
        ("canonical_symbol", record.get("canonical_symbol"), "SYMBOL"),
        ("label", record.get("label"), "APPROVED_NAME"),
    ]
    fields += [
        (f"aliases/{i}/value", a["value"], a["alias_type"])
        for i, a in enumerate(record.get("aliases", []))
    ]
    for field, value, kind in fields:
        if not value:
            continue
        assertions[normalize_lookup_key(value)].append(
            {
                "raw_label": value,
                "match_type": kind,
                "source": record["source"],
                "source_record_key": key,
                "locator": {
                    "file": str(SNAP / "records.jsonl"),
                    "sha256": digest,
                    "line": line_number,
                    "field": field,
                },
                "loaded_label": " ".join(value.split()),
                "normalized_match_key": normalize_lookup_key(value),
                "components": by_record[key],
            }
        )

if MODE == "freeze":
    failures = json.loads(
        (
            ROOT
            / "research/se_target_mention_role_representation_v1/results/provenance_failure_diagnosis.json"
        ).read_text()
    )
    rows = []
    for i, failure in enumerate(failures):
        rows.append(
            {
                "id": f"F{i:03}",
                "prior_id": failure["id"],
                "category": "prior_failure",
                "query": failure["query"],
                "surface": failure["surface"],
                "lookup": failure["lookup_text"],
                "span_candidates": [
                    [j, j + len(failure["surface"])]
                    for j in range(len(failure["query"]))
                    if failure["query"].startswith(failure["surface"], j)
                ],
            }
        )
    categories = defaultdict(list)
    for key, values in sorted(assertions.items()):
        for a in values:
            text = a["raw_label"]
            if a["match_type"] == "SYMBOL":
                categories["canonical_symbol"].append(text)
            if a["match_type"] == "APPROVED_NAME":
                categories["canonical_name"].append(text)
            if a["match_type"] == "SYNONYM":
                categories["synonym"].append(text)
            if any(c in text for c in "αβγδε"):
                categories["greek"].append(text)
            if any(w in text.casefold().split() for w in ("alpha", "beta", "gamma")):
                categories["spelled_form"].append(text)
        if len({a["source"] for a in values}) > 1:
            categories["overlapping_authorities"].append(values[0]["raw_label"])
        if any(
            len(by_id[c["canonical_id"]]) > 1 for a in values for c in a["components"]
        ):
            categories["component_collision"].append(values[0]["raw_label"])
        if len(values) > 1:
            categories["multiple_assertions"].append(values[0]["raw_label"])
    for category, names in sorted(categories.items()):
        for name in sorted(set(names))[:5]:
            rows.append(
                {
                    "id": f"C{len(rows) - 77:03}",
                    "category": category,
                    "lookup": name,
                    "query": name,
                    "surface": name,
                    "span_candidates": [[0, len(name)]],
                }
            )
    for name in (
        "CD19",
        "B-lymphocyte antigen CD19",
        "MRCK",
        "E2",
        "CAR",
        "NOT_A_REAL_TARGET_93741",
        "",
    ):
        rows.append(
            {
                "id": f"C{len(rows) - 77:03}",
                "category": "fixed_existing_resolution_controls",
                "lookup": name,
                "query": name,
                "surface": name,
                "span_candidates": [[0, len(name)]],
            }
        )
    (OUT / "population.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
    )
    (OUT / "freeze.json").write_text(
        json.dumps(
            {
                "baseline": "cc609b1",
                "snapshot_records_sha256": digest,
                "selection": "All 77 prior failed observations; lexicographic first five unique raw values per structural category; seven explicit resolution controls. No aliases added.",
                "count": len(rows),
            },
            indent=2,
        )
        + "\n"
    )
    print("Frozen", len(rows))
else:
    population = json.loads((OUT / "population.json").read_text())
    audit = []
    for row in population:
        lookup = row["lookup"]
        result = resolver.resolve(lookup)
        matches = assertions.get(normalize_lookup_key(lookup), [])
        ids = sorted({c["canonical_id"] for a in matches for c in a["components"]})
        classes = []
        if any(a["raw_label"] != a["loaded_label"] for a in matches):
            classes.append("A")
        if any(len(by_id[i]) > 1 for i in ids):
            classes.append("B")
        if len(matches) > len(
            {
                (a["source_record_key"], a["normalized_match_key"], a["match_type"])
                for a in matches
            }
        ):
            classes.append("C")
        if matches:
            classes.append("E")
        audit.append(
            {
                **row,
                "normalized_lookup": normalize_lookup_key(lookup),
                "current_status": result.status.value,
                "current_canonical_id": result.canonical_id,
                "current_candidate_ids": sorted(
                    c.canonical_id for c in result.candidates
                ),
                "current_rule": result.rule,
                "current_basis": result.basis.model_dump(mode="json")
                if result.basis
                else None,
                "assertions": matches,
                "all_components_for_matched_ids": {i: by_id[i] for i in ids},
                "all_records_for_matched_ids": {
                    k: raw_records[k]
                    for i in ids
                    for c in by_id[i]
                    for k in c["record_keys"]
                },
                "classifications": classes,
                "combined_class": "G"
                if len(classes) > 1
                else (classes[0] if classes else "NONE"),
                "loss_boundary": "SourceAlias.strip_value/all_aliases/_build_entity collapse raw field lineage; _index retains only alias type and canonical ID; _entities overwrites colliding ID; _resolved reconstructs basis from retrieved component. Original snapshot remains recoverable.",
                "contract": "Retain every matching raw assertion with snapshot-addressed field locator and source-component ID; legacy resolution remains separate.",
            }
        )
    (OUT / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    )
    summary = {
        "rows": len(audit),
        "prior_failures": sum(r["category"] == "prior_failure" for r in audit),
        "all_failed_rows_recoverable": all(
            r["assertions"] for r in audit if r["category"] == "prior_failure"
        ),
        "status_counts": {
            s: sum(r["current_status"] == s for r in audit)
            for s in sorted({r["current_status"] for r in audit})
        },
        "snapshot_sha256": digest,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
