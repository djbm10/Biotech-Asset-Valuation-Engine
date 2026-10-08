"""Candidate population for ORPHAN_EVIDENCE_ROUTING (diagnosis; not adopted).

Orphan = a PubMed/conference abstract the adapter kept as a document but emitted no hits for
(the follow-up literal-term gate). Rule under study: route the orphan to an EXISTING qualified
asset only when the adapter's own extractor observes a name whose link key equals one of that
asset's names (exact key, never substring); no asset is created. Then the frozen reader runs.
"""
import json, re, sys
from pathlib import Path
from bve.se.discovery.adapters import extract_observed_asset_names
from bve.se.evidence.human_poc import efficacy_statements
from bve.se.evidence.source_capability import may_establish_human_poc

key = lambda s: re.sub(r"[^a-z0-9]", "", s.casefold())

def main(run):
    r = json.load(open(f"{run}/result.json"))
    with_m = {m["source_document_id"] for m in r["identity_mentions"]}
    hpoc = {f["subject_id"] for f in r["facts"] if f["fact_type"] == "human_poc_present"}
    by_key = {}
    for a in r["candidates"]:
        if not a.get("qualification_reason"): continue
        for n in [a["canonical_name"], *a["aliases"]]:
            by_key.setdefault(key(n), set()).add(a["asset_id"])
    cands = {a["asset_id"]: a for a in r["candidates"]}
    out = []
    for d in r["source_documents"]:
        if d["document_id"] in with_m or not d.get("snapshot_path") or d["document_type"] not in ("publication_abstract", "conference_abstract"):
            continue
        if not may_establish_human_poc(d["document_type"]): continue
        rec = json.loads(Path(d["snapshot_path"]).read_text())
        observed = extract_observed_asset_names(rec.get("title", ""), rec.get("abstract", ""))
        targets = {aid for n in observed for aid in by_key.get(key(n), ())}
        for aid in sorted(targets):
            a = cands[aid]
            st = efficacy_statements(f"{rec.get('title','')} {rec.get('abstract','')}", asset_names=[a["canonical_name"], *a["aliases"]], document_id=d["document_id"])
            if st:
                out.append({"asset_id": aid, "name": a["canonical_name"], "had_hpoc": aid in hpoc, "document": d["document_id"], "url": d["source_url"], "sentence": st[0].sentence[:300], "matched": st[0].asset_name})
    for o in out: print(("NEW " if not o["had_hpoc"] else "    ") + f"{o['name'][:30]!r} via {o['matched']!r} {o['url']} | {o['sentence'][:200]}")
    print("total", len(out), "assets gaining hPoC", len({o['asset_id'] for o in out if not o['had_hpoc']}))

if __name__ == "__main__":
    main(sys.argv[1])
