"""Scope the two candidate mechanisms over ALL qualified assets (diagnosis only).

M1 routing: PASS sentences naming an asset inside PubMed/conference documents that carry no
   identity mention at all (the adapter kept the document but emitted no hits).
M2 clause-'and': sentences rejected ONLY by _reports_a_regimen because the name is followed by
   ' and ' + a numeral (clause coordination, not a co-product).
"""
import json, re, sys, collections
from pathlib import Path
import bve.se.evidence.human_poc as hp
sys.path.insert(0, "research/se_approved_efficacy")
from trace_v1 import trace  # noqa: E402

def main(run):
    r = json.load(open(f"{run}/result.json"))
    docs = {d["document_id"]: d for d in r["source_documents"]}
    with_mentions = {m["source_document_id"] for m in r["identity_mentions"]}
    mention_doc = {m["mention_id"]: m["source_document_id"] for m in r["identity_mentions"]}
    hpoc = {f["subject_id"] for f in r["facts"] if f["fact_type"] == "human_poc_present"}
    qualified = [a for a in r["candidates"] if a.get("qualification_reason")]
    texts = {}
    def sents(d):
        if d not in texts:
            try: texts[d] = hp._sentences(Path(docs[d]["snapshot_path"]).read_text(errors="ignore"))
            except Exception: texts[d] = []
        return texts[d]
    orphan = [d for d, doc in docs.items() if d not in with_mentions and doc["document_type"] in ("publication_abstract", "conference_abstract") and doc.get("snapshot_path")]
    m1 = collections.defaultdict(list); m2 = collections.defaultdict(list)
    for a in qualified:
        names = sorted({n for n in [a["canonical_name"], *a["aliases"]] if len(n.strip()) >= 4}, key=len, reverse=True)
        if not names: continue
        pat = re.compile("|".join(re.escape(n) for n in names), re.I)
        for d in orphan:
            for s in sents(d):
                if pat.search(s) and trace(s, names) == "PASS":
                    m1[a["canonical_name"]].append((d, s[:220]))
        routed = {mention_doc[m] for m in a["mention_ids"] if m in mention_doc}
        for d in routed:
            if docs.get(d, {}).get("document_type") == "trial_registry_record": continue
            for s in sents(d):
                if trace(s, names) == "regimen":
                    low = s.casefold()
                    named = next(n for n in names if n.casefold() in low)
                    tail = low[low.find(named.casefold()) + len(named):]
                    if re.match(r"\s+and\s+\d", tail):
                        m2[a["canonical_name"]].append((d, s[:220]))
    print(f"orphan abstracts: {len(orphan)}")
    print(f"M1 assets with PASS sentences only in orphan docs: {len(m1)}; of which currently lacking human_poc: {sum(1 for n in m1 if not any(a['canonical_name']==n and a['asset_id'] in hpoc for a in qualified))}")
    for n, rows in sorted(m1.items(), key=lambda x: -len(x[1])):
        has = any(a["canonical_name"] == n and a["asset_id"] in hpoc for a in qualified)
        print(f"  {n[:40]!r} n={len(rows)} has_hpoc={has}")
        for d, s in rows[:2]: print(f"      {d} | {s}")
    print(f"M2 assets with clause-'and' regimen rejections: {len(m2)}")
    for n, rows in m2.items():
        for d, s in rows[:2]: print(f"  {n[:30]!r} {d} | {s}")

if __name__ == "__main__":
    main(sys.argv[1])
