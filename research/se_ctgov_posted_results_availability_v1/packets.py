"""Build adjudication packets: first 2 PRIMARY outcomes per sampled study (prereg eefd8a2)."""

import hashlib
import json
from pathlib import Path

STUDY = Path(__file__).resolve().parent
RAW = Path.home() / "se_runs/ctgov_posted_results_availability_v1/full"
RUNS = [
    Path.home() / "se_runs" / r / "result.json" for r in ("tac01_protoid_v1", "mint5_protoid_v1")
]


def cut(s, n=300):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n] + "…"


def candidates_by_trial():
    out = {}
    for p in RUNS:
        for c in json.loads(p.read_text())["candidates"]:
            for t in c.get("trial_ids") or []:
                out.setdefault(t.split(":")[-1], set()).add(c["canonical_name"])
    return out


def packets():
    manifest = json.loads((STUDY / "full_manifest.json").read_text())
    cands = candidates_by_trial()
    out = []
    for m in manifest:
        body = (RAW / f"{m['nct']}.json").read_bytes()
        assert hashlib.sha256(body).hexdigest() == m["sha256"]
        d = json.loads(body)
        ps, rs = d.get("protocolSection", {}), d.get("resultsSection")
        arms = ps.get("armsInterventionsModule", {})
        base = {
            "nct": m["nct"],
            "stratum": m["stratum"],
            "title": cut(ps["identificationModule"].get("briefTitle")),
            "phases": ps.get("designModule", {}).get("phases"),
            "engine_candidate_names_for_trial": sorted(cands.get(m["nct"], []))[:12],
            "arms": [
                {
                    "label": a.get("label"),
                    "type": a.get("type"),
                    "interventions": a.get("interventionNames"),
                    "description": cut(a.get("description"), 200),
                }
                for a in arms.get("armGroups", [])
            ][:8],
            "interventions": [
                {"type": i.get("type"), "name": i.get("name"), "otherNames": i.get("otherNames")}
                for i in arms.get("interventions", [])
            ][:8],
        }
        if not rs:
            out.append({**base, "outcome_index": None, "results_present": False})
            continue
        prim = [
            o
            for o in rs.get("outcomeMeasuresModule", {}).get("outcomeMeasures", [])
            if o.get("type") == "PRIMARY"
        ]
        for i, o in enumerate(prim[:2]):
            meas = []
            for cl in o.get("classes", [])[:3]:
                for cat in cl.get("categories", [])[:3]:
                    for mm in cat.get("measurements", [])[:8]:
                        meas.append(
                            {
                                "class": cl.get("title"),
                                "category": cat.get("title"),
                                "group": mm.get("groupId"),
                                "value": mm.get("value"),
                                "spread": mm.get("spread"),
                                "lower": mm.get("lowerLimit"),
                                "upper": mm.get("upperLimit"),
                            }
                        )
            out.append(
                {
                    **base,
                    "outcome_index": i,
                    "results_present": True,
                    "outcome": {
                        "title": cut(o.get("title")),
                        "description": cut(o.get("description"), 400),
                        "time_frame": cut(o.get("timeFrame"), 120),
                        "param_type": o.get("paramType"),
                        "unit": o.get("unitOfMeasure"),
                        "reporting_status": o.get("reportingStatus"),
                        "population": cut(o.get("populationDescription"), 200),
                    },
                    "groups": [
                        {
                            "id": g.get("id"),
                            "title": g.get("title"),
                            "description": cut(g.get("description"), 250),
                        }
                        for g in o.get("groups", [])
                    ][:8],
                    "denoms": [
                        {"group": c.get("groupId"), "n": c.get("value")}
                        for dn in o.get("denoms", [])[:1]
                        for c in dn.get("counts", [])
                    ][:8],
                    "measurements": meas[:24],
                    "analyses": [
                        {
                            "groups": a.get("groupIds"),
                            "p": a.get("pValue"),
                            "method": a.get("statisticalMethod"),
                            "param": a.get("paramType"),
                            "estimate": a.get("paramValue"),
                        }
                        for a in o.get("analyses", [])
                    ][:4],
                }
            )
        if not prim:
            out.append(
                {
                    **base,
                    "outcome_index": None,
                    "results_present": True,
                    "note": "no PRIMARY outcome posted",
                }
            )
    for i, p in enumerate(out):
        p["packet_id"] = i
    return out


if __name__ == "__main__":
    pk = packets()
    (STUDY / "packets.json").write_text(json.dumps(pk, indent=1, ensure_ascii=False) + "\n")
    print(
        len(pk),
        sum(p["results_present"] for p in pk),
        sum(p.get("outcome_index") is not None for p in pk),
    )
