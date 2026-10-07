"""Classify frozen generic-descriptor assets (GENERIC_DESCRIPTOR_SPLIT_DIAGNOSIS v1).

Per trial: lead sponsor, collaborators, and product codes read from the asset's own
intervention entry (name, otherNames, description). Sponsor is context only, never identity.
  A  one product: every trial carries the same product code, or a single trial.
  B  pooled: two or more trials carry DIFFERENT product codes, or an authority-linked member.
  C  insufficient: no product code separates or unites the trials.
"""
import json, re, sys
from collections import Counter
from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist

CODE = re.compile(r"\b([A-Z]{1,6}[- ]?\d{2,5}[A-Z]{0,2}(?:[.-]\d{1,2})?)\b")
NOT_CODE = re.compile(r"^(CD\d+|NCT\d+|IL\d+|COVID\d+|HLA\d*|IGG\d|FIX\d+|DAY\d+|TP\d+)$", re.I)

def codes(text):
    return sorted({c.replace(" ", "-").upper() for c in CODE.findall(text or "") if not NOT_CODE.match(c.replace("-", "").replace(" ", ""))})

def main(runs, pop_path):
    pop = json.load(open(pop_path))
    for bench in ("tac01", "mint5"):
        r = json.load(open(f"{runs}/{bench}_ncitid_v1/result.json"))
        snap = {}
        for d in r["source_documents"]:
            m = re.search(r"NCT\d{8}", d.get("source_url") or "")
            if m and d.get("snapshot_path"):
                snap.setdefault(m.group(0), d["snapshot_path"])
        ranks = {e.asset_id: i + 1 for i, e in enumerate(build_shortlist(SESearchResult.model_validate(r), limit=10_000).entries)}
        ncit = {x["asset_id"]: x["ncit_code"] for x in r["ncit_target_dispositions"]}
        tally = Counter()
        print(f"===== {bench}")
        for a in [p for p in pop if p["benchmark"] == bench]:
            names = {n.casefold() for n in a["aliases"] + [a["canonical_name"]]}
            rows = []
            for t in a["trial_ids"]:
                j = json.load(open(snap[t]))
                sp = j["sponsorCollaboratorsModule"]
                own = [iv for iv in j["armsInterventionsModule"].get("interventions", []) if (iv.get("name") or "").casefold() in names] or j["armsInterventionsModule"].get("interventions", [])
                text = " ".join([iv.get("name") or "" for iv in own] + [o for iv in own for o in (iv.get("otherNames") or [])] + [iv.get("description") or "" for iv in own])
                rows.append((t, sp["leadSponsor"]["name"], codes(text)))
            sponsors = {s for _, s, _ in rows}
            coded = [frozenset(c) for _, _, c in rows if c]
            if len(rows) == 1:
                verdict = "A1"
            elif len(coded) >= 2 and not frozenset.intersection(*coded):
                verdict = "B"
            elif coded and len(coded) == len(rows) and frozenset.intersection(*coded):
                verdict = "A"
            elif len(sponsors) == 1:
                verdict = "C1"   # one sponsor, codes do not decide
            else:
                verdict = "C"
            tally[verdict] += 1
            if verdict != "A1":
                print(f"{verdict:2} rank={ranks.get(a['asset_id'], '-')} ncit={ncit.get(a['asset_id'], '-')} {a['canonical_name'][:55]!r} trials={len(rows)} sponsors={len(sponsors)}")
                for t, s, c in rows:
                    print(f"      {t} | {s[:45]} | {c}")
        print("tally", dict(tally))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
