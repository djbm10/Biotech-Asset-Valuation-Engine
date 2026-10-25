"""DEVELOPMENT: trace each analyst-visible candidate of a GUCY2C dev replay to its sources.

    python research/se_gucy2c_dev_v2/trace_visible.py RESULT.json [--gi-terms a,b,...]

For every visible candidate prints: qualification route, trials, target, modality,
therapeutic-area facts, and per source document the publisher, title, and the areas the
current lexicon (plus optional proposed GI terms) would classify from title+abstract.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from bve.se.ontology.therapeutic_areas import classify_therapeutic_areas


def _doc_text(path: str) -> tuple[str, str]:
    record = json.loads(Path(path).read_text())
    if "title" in record or "abstract" in record:
        return record.get("title", ""), f"{record.get('title', '')} {record.get('abstract', '')}"
    text = json.dumps(record)
    return text[:120], text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--gi-terms", default="")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    gi = tuple(t for t in args.gi_terms.split(",") if t)
    r = json.loads(Path(args.result).read_text())
    docs = {d["document_id"]: d for d in r["source_documents"]}
    mentions = {m["mention_id"]: m for m in r["identity_mentions"]}
    facts = defaultdict(list)
    for f in r["facts"]:
        facts[f["subject_id"]].append(f)
    cands = {c["asset_id"]: c for c in r["candidates"]}
    rows = []
    for aid in [*r["eligible_asset_ids"], *r["unresolved_asset_ids"]]:
        c = cands[aid]
        doc_ids = dict.fromkeys(mentions[m]["source_document_id"] for m in c["mention_ids"] if m in mentions)
        per_doc = []
        for did in doc_ids:
            d = docs[did]
            title, text = _doc_text(d["snapshot_path"])
            areas = classify_therapeutic_areas(text)
            if gi and any(t in text.casefold() for t in gi):
                areas = sorted({*areas, "GASTROINTESTINAL"})
            per_doc.append({"url": d["source_url"], "publisher": d["publisher"],
                            "title": title[:110], "areas": areas})
        row = {"name": c["canonical_name"], "route": c["qualification_reason"],
               "trials": c["trial_ids"], "targets": c["target_ids"], "modality": c["modality_id"],
               "ta_facts": sorted({str(f["value"]) for f in facts[aid] if f["fact_type"] == "therapeutic_area"}),
               "docs": per_doc,
               "union": sorted({a for p in per_doc for a in p["areas"]})}
        rows.append(row)
        print(f"{row['name'][:32]:32} {row['route']:24} trials={len(row['trials'])} union={row['union']}")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rows, indent=1) + "\n")


if __name__ == "__main__":
    main()
