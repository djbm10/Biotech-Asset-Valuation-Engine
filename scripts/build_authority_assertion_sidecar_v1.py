"""Offline sidecar materialization against immutable accepted target snapshot."""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from bve.se.ontology.assertion_provenance import (
    canonical_json,
    capture_assertions,
    link_assertions,
    replay,
    stable_id,
)
from bve.se.ontology.bulk import file_sha256, iter_rows
from bve.se.ontology.records import EntityType
from bve.se.ontology.sources.open_targets import parse_open_targets_target
from bve.se.ontology.targets import get_resolver


class JsonLines:
    def __init__(self, path):
        self.file = path.open("wb")
        self.gzip = gzip.GzipFile(filename="", fileobj=self.file, mode="wb", mtime=0)

    def write(self, row):
        self.gzip.write((canonical_json(row) + "\n").encode())

    def close(self):
        self.gzip.close()
        self.file.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    study = Path("research/se_authority_assertion_provenance_sidecar_v1")
    pinned = json.loads((study / "input_hashes.json").read_text())
    for name, digest in pinned.items():
        assert file_sha256(Path(name))[0] == digest, name
    snapshot_digest = pinned["data/se/ontology/current/records.jsonl"]
    resolver = get_resolver()
    records = {
        r.record_key: r for r in resolver.snapshot.records if r.entity_type == EntityType.TARGET
    }
    components = defaultdict(list)
    id_components = defaultdict(set)
    for entity in resolver.entities_of_type(EntityType.TARGET):
        keys = sorted(r.record_key for r in entity.source_records)
        component_id = stable_id({"snapshot": snapshot_digest, "records": keys})
        item = {
            "component_id": component_id,
            "record_keys": keys,
            "canonical_id": entity.canonical_id,
            "canonical_label": entity.label,
        }
        id_components[entity.canonical_id].add(component_id)
        for key in keys:
            components[key].append(item)
    for values in components.values():
        values.sort(key=lambda x: x["component_id"])
    expected = json.loads((study / "expected.json").read_text())
    wanted = {
        (a["source_record_key"], a["locator"]["field"]) for r in expected for a in r["assertions"]
    }
    audit_links = {}
    preflight = json.loads((study / "preflight.json").read_text())
    assertions = JsonLines(out / "assertions.jsonl.gz")
    linkage = JsonLines(out / "linkage.jsonl.gz")
    unknown = JsonLines(out / "unrecoverable.jsonl.gz")
    covered = set()
    ids = set()
    count = Counter()
    target_counts = Counter()
    variants = defaultdict(set)
    artifact_rows = []
    for artifact in sorted(preflight["artifacts"], key=lambda a: a["path"]):
        path = Path(artifact["path"])
        assert file_sha256(path) == (artifact["sha256"], artifact["bytes"])
        row_count = 0
        for row_index, raw in enumerate(iter_rows(path)):
            row_count += 1
            parsed = parse_open_targets_target(raw)
            if parsed is None:
                continue
            key = parsed.record_key
            assert key not in covered
            accepted = records[key]
            rows = capture_assertions(
                "open_targets", "26.06", artifact["sha256"], "target/" + path.name, row_index, raw
            )
            links = link_assertions(rows, parsed, accepted)
            row_fields = defaultdict(list)
            for link in links:
                for assertion_id in link["assertion_ids"]:
                    row_fields[assertion_id].append(link["field"])
            for row in rows:
                assert row["assertion_id"] not in ids
                ids.add(row["assertion_id"])
                value = raw
                for part in row["field_path"]:
                    value = value[part]
                assert value == row["raw_scalar"]
                start, end = row["component_interval"]
                assert value[start:end] == row["raw_component"]
                assert replay(value, row["transforms"]) == row["normalized_key"]
                assert row_fields[row["assertion_id"]]
                row.update(
                    {
                        "snapshot_records_sha256": snapshot_digest,
                        "source_record_key": key,
                        "snapshot_fields": sorted(row_fields[row["assertion_id"]]),
                        "resolver_components": components[key],
                    }
                )
                assertions.write(row)
                count["raw_source_assertions"] += 1
                count["sidecar_assertion_rows"] += 1
                count["raw_and_transform_roundtrips"] += 1
                for cid in {c["canonical_id"] for c in components[key]}:
                    target_counts[cid] += 1
                variants[row["normalized_key"]].add(row["raw_component"])
            for link in links:
                link.update(
                    {
                        "snapshot_records_sha256": snapshot_digest,
                        "resolver_components": components[key],
                    }
                )
                linkage.write(link)
                count["fully_recoverable_snapshot_fields"] += 1
                if (key, link["field"]) in wanted:
                    audit_links[(key, link["field"])] = link
            covered.add(key)
        artifact_rows.append({**artifact, "rows": row_count})
    for key in sorted(set(records) - covered):
        assert records[key].source == "chembl", key
        for link in link_assertions([], None, records[key]):
            link.update(
                {"snapshot_records_sha256": snapshot_digest, "resolver_components": components[key]}
            )
            linkage.write(link)
            unknown.write(link)
            count["unrecoverable_snapshot_fields"] += 1
            if (key, link["field"]) in wanted:
                audit_links[(key, link["field"])] = link
    for stream in (assertions, linkage, unknown):
        stream.close()
    query_audit = []
    for row in expected:
        resolved = resolver.resolve(row["lookup"])
        observed = {
            "status": resolved.status.value,
            "canonical_id": resolved.canonical_id,
            "candidates": sorted(c.canonical_id for c in resolved.candidates),
            "rule": resolved.rule,
        }
        assert all(observed[k] == row[k] for k in observed), row["case_id"]
        links = []
        for a in row["assertions"]:
            link = audit_links[(a["source_record_key"], a["locator"]["field"])]
            assert link["status"] == a["expected"]
            assert link["value"] == a["raw_snapshot_text"]
            links.append(link)
        query_audit.append({"case_id": row["case_id"], "lookup_unchanged": True, "links": links})
    collisions = {
        "normalization": {k: sorted(v) for k, v in sorted(variants.items()) if len(v) > 1},
        "canonical_id_components": {
            k: sorted(v) for k, v in sorted(id_components.items()) if len(v) > 1
        },
    }
    count.update(
        {
            "unique_canonical_target_ids_with_sidecar": len(target_counts),
            "canonical_ids_with_multiple_assertions": sum(v > 1 for v in target_counts.values()),
            "normalization_collisions": len(collisions["normalization"]),
            "source_component_collisions": len(collisions["canonical_id_components"]),
            "audited_queries": len(query_audit),
            "audited_snapshot_field_occurrences": sum(len(r["links"]) for r in query_audit),
            "recoverable_source_records": len(covered),
            "unrecoverable_source_records": len(records) - len(covered),
        }
    )
    for name, value in [
        ("counts", dict(count)),
        ("collision_report", collisions),
        ("query_linkage_audit", query_audit),
        ("raw_artifacts", artifact_rows),
    ]:
        (out / f"{name}.json").write_text(canonical_json(value) + "\n")
    for name, digest in pinned.items():
        assert file_sha256(Path(name))[0] == digest, name
    manifest = {
        p.name: file_sha256(p)[0] for p in sorted(out.iterdir()) if p.name != "manifest.json"
    }
    (out / "manifest.json").write_text(canonical_json(manifest) + "\n")
    print(canonical_json(dict(count)), flush=True)


if __name__ == "__main__":
    main()
