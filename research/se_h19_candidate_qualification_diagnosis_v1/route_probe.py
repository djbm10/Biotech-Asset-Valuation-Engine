"""Counterfactual pure-helper route audit; never mutates saved candidate decisions."""

import hashlib
import json
from pathlib import Path
from bve.se.discovery import asset_qualification as q

ROOT = Path("/home/djmann/projects/bve-b8")
OUT = Path("/tmp/h19_qualification_results")
r = json.loads(Path("/home/djmann/se_runs/heldout_h19_v4/result.json").read_text())
texts = [
    (d["document_id"], Path(d["snapshot_path"]).read_text())
    for d in r["source_documents"]
    if d.get("snapshot_path")
]
results = []
for name in ["[68Ga]Ga-TTP", "Rescue Medications", "Rescue Medication"]:
    a = next(a for a in r["candidates"] if a["canonical_name"] == name)
    witnessed = [did for did, text in texts if q.has_pharmacologic_context(text, name)]
    aliases = a["aliases"]
    frequency = sum(any(n.casefold() in text.casefold() for n in aliases) for _, text in texts)
    e = q.AssetEvidence(
        name=name,
        support=frequency,
        entity_specific_link=bool(a["trial_ids"] or a["company_ids"]),
        pharmacologic_documents=len(witnessed),
        pharmacologic_context=bool(witnessed),
        document_frequency=frequency,
        corpus_documents=len(texts),
    )
    route = q.qualification_reason(e)
    results.append(
        {
            "name": name,
            "original_decision": a["qualification_reason"],
            "structured_route_removed_probe": route.value if route else None,
            "development_code_shape": q.is_development_code(name),
            "class_term": q.class_terms.is_class_term(name),
            "qualifying_prose_document_ids": witnessed,
            "probe_evidence": e.model_dump(),
            "note": "Read-only alternate-route probe on serialized captured text. Does not change recorded route or prove product identity.",
        }
    )
(OUT / "alternate_routes.json").write_text(json.dumps(results, sort_keys=True, indent=2) + "\n")
files = [
    ROOT / "src/bve/se/lexicon/identity_bearing_drug_names_v1.json",
    ROOT / "src/bve/se/lexicon/known_drug_names_v1.json",
    ROOT / "src/bve/se/lexicon/multi_token_drug_names_v1.json",
    ROOT / "src/bve/se/ontology/modality.py",
]
(OUT / "supplemental_provenance_inputs.json").write_text(
    json.dumps(
        {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        sort_keys=True,
        indent=2,
    )
    + "\n"
)
print(
    [
        (x["name"], x["structured_route_removed_probe"], len(x["qualifying_prose_document_ids"]))
        for x in results
    ]
)
