"""Select existing frozen source groups, without issuing biological certificates."""

import json
from collections import defaultdict
from pathlib import Path
from bve.se.ontology.targets import get_resolver
from bve.se.ontology.records import EntityType
from bve.se.ontology.assertion_provenance import stable_id

root = Path.cwd()
out = Path("/tmp/component_certificate_v1")
snapshot = json.loads(
    (root / "research/se_authority_assertion_provenance_sidecar_v1/input_hashes.json").read_text()
)["data/se/ontology/current/records.jsonl"]
resolver = get_resolver()
groups = {}
by_id = defaultdict(list)
for e in resolver.entities_of_type(EntityType.TARGET):
    keys = sorted(r.record_key for r in e.source_records)
    cid = stable_id({"snapshot": snapshot, "records": keys})
    group = {
        "component_id": cid,
        "canonical_id": e.canonical_id,
        "canonical_label": e.label,
        "record_keys": keys,
        "records": [r.model_dump(mode="json") for r in e.source_records],
    }
    groups[cid] = group
    by_id[e.canonical_id].append(cid)
selected = {}


def add(cid, category):
    if cid not in selected:
        selected[cid] = dict(groups[cid], categories=[])
    selected[cid]["categories"].append(category)


for cid in json.loads(
    (
        root / "research/se_target_mention_role_decision_v1/multiple_source_components.json"
    ).read_text()
):
    add(cid, "nine_implicated_groups")
for symbol in [
    "CD19",
    "PDCD1",
    "IL4R",
    "EGFR",
    "GFRA1",
    "IL2RA",
    "HBB",
    "CAMK2A",
    "THRA",
    "CDC42BPA",
    "SNORA62",
]:
    for cid in by_id["TARGET:" + symbol]:
        add(cid, "named_clean_receptor_subunit_or_collision_control")
for category, needle in [
    ("fusion_lexical_probe", "fusion"),
    ("complex_lexical_probe", "complex"),
    ("heterodimer_lexical_probe", "heterodimer"),
    ("ligand_receptor_lexical_probe", "ligand"),
    ("slash_lexical_probe", "/"),
    ("hyphen_lexical_probe", "-"),
]:
    matches = [
        g
        for g in groups.values()
        if any(needle in (r["label"] or "").lower() for r in g["records"])
    ]
    for g in sorted(matches, key=lambda g: g["component_id"])[:3]:
        add(g["component_id"], category)
# Raw-field recovery and clean OT-only controls, selected without expected certificate labels.
clean = [
    g
    for g in groups.values()
    if len(g["records"]) == 1
    and g["records"][0]["source"] == "open_targets"
    and g["records"][0]["canonical_symbol"]
]
for g in sorted(clean, key=lambda g: g["component_id"])[:6]:
    add(g["component_id"], "single_open_targets_record_control")
for cid in selected:
    selected[cid]["categories"] = sorted(set(selected[cid]["categories"]))
(out / "population.json").write_text(
    json.dumps(sorted(selected.values(), key=lambda g: g["component_id"]), indent=2, sort_keys=True)
    + "\n"
)
print(
    len(selected),
    dict(
        (c, sum(c in g["categories"] for g in selected.values()))
        for c in sorted({c for g in selected.values() for c in g["categories"]})
    ),
)
