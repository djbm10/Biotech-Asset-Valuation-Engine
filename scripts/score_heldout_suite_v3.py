"""Score HELDOUT_VALIDATION_SUITE v3 exactly as preregistered (heldout_validation_suite_v3.md §2-§4)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from bve.se.pipeline import SESearchResult
from bve.se.reporting.shortlist import build_shortlist

ROOT = Path(__file__).resolve().parents[1]
REFS = {
    "H11": [["tiragolumab"], ["domvanalimab", "AB154"], ["vibostolimab", "MK-7684"], ["ociperlimab", "BGB-A1217"], ["belrestotug", "EOS-448", "GSK4428859"], ["rilvegostomig", "AZD2936"]],
    "H12": [["eculizumab", "Soliris"], ["ravulizumab", "Ultomiris"], ["crovalimab", "PiaSky", "SKY59"], ["pozelimab", "REGN3918"], ["zilucoplan", "Zilbrysq"], ["cemdisiran"], ["tesidolumab", "LFG316"]],
    "H13": [["secukinumab", "Cosentyx"], ["ixekizumab", "Taltz"], ["bimekizumab", "Bimzelx"], ["izokibep"], ["sonelokimab", "M1095"], ["netakimab"], ["vunakizumab"], ["xeligekimab"]],
    "H14": [["daratumumab", "Darzalex"], ["isatuximab", "Sarclisa"], ["felzartamab", "MOR202"], ["mezagitamab", "TAK-079"], ["CID-103"]],
    "H15": [["evinacumab", "Evkeeza"], ["zodasiran", "ARO-ANG3"], ["solbinsiran", "LY3561774"], ["vupanorsen"], ["SHR-1918"]],
}
INTENDED = {"H11": ["TIGIT"], "H12": ["C5"], "H13": ["IL17A"], "H14": ["CD38"], "H15": ["ANGPTL3"]}
key = lambda s: re.sub(r"[^a-z0-9]", "", s.casefold())  # noqa: E731


def score(qid: str, labels: dict) -> dict:
    path = Path.home() / f"se_runs/heldout_{qid.lower()}_v3/result.json"
    if not path.exists():
        log = (path.parent / "logs/run.log").read_text()
        reason = next((line.strip() for line in log.splitlines() if "blocked" in line), "no result")
        return {"query": qid, "verdict": "FAIL", "refused": reason}
    raw = json.loads(path.read_text())
    cands = {a["asset_id"]: a for a in raw["candidates"]}
    entries = build_shortlist(SESearchResult.model_validate(raw), limit=100_000).entries
    names_of = lambda e: {key(n) for n in [cands[e.asset_id]["canonical_name"], *cands[e.asset_id]["aliases"]]}  # noqa: E731
    all_keys = [names_of(e) for e in entries]
    top_keys = all_keys[:20]
    found_all = [r[0] for r in REFS[qid] if any(key(n) in ks for n in r for ks in all_keys)]
    found_20 = [r[0] for r in REFS[qid] if any(key(n) in ks for n in r for ks in top_keys)]
    top = entries[:20]
    lab = [labels[e.name] for e in top]
    judged = [x for x in lab if x != "UNVERIFIABLE"]
    p20 = sum(x == "RELEVANT" for x in judged) / len(judged)
    hpoc = {f["subject_id"]: f for f in raw["facts"] if f["fact_type"] == "human_poc_present"}
    claims = {c["claim_id"]: c for c in raw["claims"]}
    hpoc_rows = [(e.name, [claims[c]["supporting_passage"][:260] for c in hpoc[e.asset_id]["supporting_claim_ids"] if c in claims]) for e in top if e.asset_id in hpoc]
    result = {
        "query": qid, "shortlist": len(entries), "labels": dict(zip([e.name for e in top], lab)),
        "P@20": round(p20, 3), "recall_all": round(len(found_all) / len(REFS[qid]), 3), "found_all": found_all,
        "recall_20": round(len(found_20) / len(REFS[qid]), 3), "NON_ASSET": lab.count("NON_ASSET"),
        "DUPLICATE": lab.count("DUPLICATE"), "human_poc_rows_top20": hpoc_rows,
    }
    result["thresholds"] = {"P@20>=0.70": p20 >= 0.70, "recall_all>=0.60": result["recall_all"] >= 0.60,
                            "NON_ASSET<=1": result["NON_ASSET"] <= 1, "DUPLICATE<=2": result["DUPLICATE"] <= 2}
    problem = yaml.safe_load((path.parent / "problem.yaml").read_text())
    compiled = sorted(t["canonical_id"] for t in _find(problem, "target_expression")["targets"])
    result["target_recognition"] = {"compiled": compiled, "intended": INTENDED[qid], "exact": compiled == INTENDED[qid]}
    return result


def _find(node, wanted):
    if isinstance(node, dict):
        if wanted in node:
            return node[wanted]
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            hit = _find(child, wanted)
            if hit is not None:
                return hit
    return None


def main() -> None:
    labels = json.loads((ROOT / "research/se_heldout/labels_v3.json").read_text())
    out = [score(q, labels.get(q, {})) for q in ("H11", "H12", "H13", "H14", "H15")]
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
