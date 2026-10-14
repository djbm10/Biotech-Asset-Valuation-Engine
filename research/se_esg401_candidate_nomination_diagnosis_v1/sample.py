"""Reproducible arm-description sample from non-holdout development CT.gov snapshots.

Unit = one arm group with a non-empty description. Strata are surface shapes only (alternative
conjunction, combination conjunction, other); order = sha256(unit key); first K per stratum.
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_esg401_candidate_nomination_diagnosis_v1"
RUNS = Path.home() / "se_runs"
DEV = ("tac01_protoid_v1", "mint5_protoid_v1")
H19 = (
    RUNS
    / "heldout_h19_v4/snapshots/clinicaltrials_gov/4c21f6a50df9a1ed3dbb18ccc7fed97c83241e158f710856c1ed0caab050a63d.json"
)
K = 15


def stratum(text):
    if re.search(r"\bor\b|\beither\b|\s/\s", text, re.I):
        return "ALT_SHAPE"
    if re.search(r"\+|\band\b|\bplus\b|\bcombined\b|\bcombination\b|\bfollowed by\b", text, re.I):
        return "COMB_SHAPE"
    return "OTHER"


def unit(path, sha, nct, i, arm):
    key = f"{sha}|{i}"
    return {
        "unit_id": hashlib.sha256(key.encode()).hexdigest()[:16],
        "artifact": str(path),
        "artifact_sha256": sha,
        "nct": nct,
        "arm_index": i,
        "field": f"/armsInterventionsModule/armGroups/{i}/description",
        "label": arm.get("label"),
        "type": arm.get("type"),
        "interventionNames": arm.get("interventionNames") or [],
        "description": arm["description"],
        "stratum": stratum(arm["description"]),
    }


def main():
    seen, pool = set(), []
    for run in DEV:
        for p in sorted((RUNS / run / "snapshots").rglob("*.json")):
            if "clinicaltrials" not in str(p):
                continue
            d = json.loads(p.read_text())
            nct = d["identificationModule"]["nctId"]
            if nct in seen:
                continue
            seen.add(nct)
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            for i, arm in enumerate(
                (d.get("armsInterventionsModule") or {}).get("armGroups") or []
            ):
                if (arm.get("description") or "").strip():
                    pool.append(unit(p, sha, nct, i, arm))
    denominators, sample = {}, []
    for st in ("ALT_SHAPE", "COMB_SHAPE", "OTHER"):
        group = sorted((u for u in pool if u["stratum"] == st), key=lambda u: u["unit_id"])
        denominators[st] = len(group)
        sample += group[:K]
    h = json.loads(H19.read_text())
    esg = unit(
        H19,
        hashlib.sha256(H19.read_bytes()).hexdigest(),
        "NCT06145308",
        3,
        h["armsInterventionsModule"]["armGroups"][3],
    )
    esg["development_reference"] = True
    out = {
        "trials": len(seen),
        "arms_with_description": len(pool),
        "denominators": denominators,
        "units": sample + [esg],
    }
    (STUDY / "sample.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(
        json.dumps({k: out[k] for k in ("trials", "arms_with_description", "denominators")}),
        len(out["units"]),
    )


if __name__ == "__main__":
    main()
