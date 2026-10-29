"""Build the CLDN18.2 comparison landscape mechanically (cycle C1). INTERNAL DEVELOPMENT.

Every cell is derived by a fixed rule from a saved source, with field provenance:
- registry fields from ``sources/ctgov_cldn18_snapshot.json`` (ClinicalTrials.gov API v2);
- target / modality by a fixed vocabulary scan of the program's registry intervention descriptions,
  registry study titles naming only this investigational agent, and the curator's verbatim quotes
  (``sources/public_evidence.json``);
- U.S. labeler and marketing from ``sources/openfda_labels_snapshot.json``.
Nothing is typed in by hand. Rights availability is never filled (no source states it as a field);
licensing facts stay in the evidence file, as they would in a separate news feed.

Usage: python research/dealscreen_comparison_v1/build_landscape.py
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
SRC = HERE / "sources"
OUT = HERE / "inputs"
CTGOV = "https://clinicaltrials.gov/study/{}"

COLUMNS = ["Program ID", "Program", "Aliases", "Target", "Mechanism", "Modality", "Therapeutic Area",
           "Indication", "Highest Phase", "Status", "Status Date", "Company", "Trial IDs", "US Rights",
           "US Rights Holder", "Geographic Notes", "Partnerships", "Sources", "Source Date", "Notes"]

#: Fixed target vocabulary: pattern -> label written to the Target column.
TARGETS = [
    (r"claudin[\s-]*18[.\s]*2|cldn[\s-]*18[.\s]*2|claudin18\.2|claudin-18 isoform 2", "Claudin 18.2"),
    (r"\bpd-?1\b", "PD-1"), (r"\bpd-?l1\b", "PD-L1"), (r"\btigit\b", "TIGIT"), (r"\bctla-?4\b", "CTLA-4"),
    (r"\bher2\b", "HER2"), (r"\bcd3\b", "CD3"), (r"\b4-1bb\b|\bcd137\b", "4-1BB"), (r"\bcd47\b", "CD47"),
    (r"\bmuc1\b", "MUC1"), (r"\bmesothelin\b|\bmsln\b", "Mesothelin"), (r"\bcd28\b", "CD28"),
]
#: Fixed modality vocabulary, in priority order (first match wins).
MODALITIES = [
    (r"antibody[\s-]*drug[\s-]*conjugate|\badc\b", "Antibody-drug conjugate"),
    (r"car[\s-]*nk\b", "CAR-NK"),
    (r"car[\s-]*t\b|chimeric antigen receptor", "CAR-T"),
    (r"radioligand|177lu|lutetium", "Radioligand"),
    (r"\bpet\b|imaging|89zr|\[18f\]|tracer", "Imaging agent"),
    (r"bispecific|bi-specific|t[\s-]*cell engager", "Bispecific antibody"),
    (r"monoclonal antibody|\bmab\b", "Monoclonal antibody"),
]
ACTIVE = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"}
STOPPED = {"TERMINATED", "WITHDRAWN", "SUSPENDED"}
PHASE_LABEL = {"EARLY_PHASE1": "Phase 1", "PHASE1": "Phase 1", "PHASE2": "Phase 2", "PHASE3": "Phase 3",
               "PHASE4": "Phase 4"}
PHASE_ORDER = {"EARLY_PHASE1": 1, "PHASE1": 1, "PHASE2": 2, "PHASE3": 3, "PHASE4": 4}


def _studies() -> list[dict[str, Any]]:
    return json.loads((SRC / "ctgov_cldn18_snapshot.json").read_text())["studies"]


def _matches(intervention: dict[str, Any], keys: list[str]) -> bool:
    text = " ".join([intervention.get("name", ""), *intervention.get("otherNames", [])]).casefold()
    return any(k in text for k in keys)


def _scan(texts: list[tuple[str, str]], vocabulary: list[tuple[str, str]], first_only: bool):
    found: list[tuple[str, str]] = []
    for text, where in texts:
        for pattern, label in vocabulary:
            if re.search(pattern, text, re.IGNORECASE) and label not in [f[0] for f in found]:
                found.append((label, where))
                if first_only:
                    return found
    return found


def build() -> None:
    programs = yaml.safe_load((HERE / "programs.yaml").read_text())["programs"]
    evidence = json.loads((SRC / "public_evidence.json").read_text())["items"]
    labels = json.loads((SRC / "openfda_labels_snapshot.json").read_text())["labels"]
    rows, provenance = [], []
    for prog in programs:
        keys = [k.casefold() for k in prog["match"]]
        trials, own_texts, conditions, aliases, collaborators = [], [], [], [], set()
        phases, statuses, dates, sponsors = [], [], [], []
        for s in _studies():
            p = s["protocolSection"]
            nct = p["identificationModule"]["nctId"]
            ivs = p.get("armsInterventionsModule", {}).get("interventions", [])
            mine = [i for i in ivs if _matches(i, keys)]
            if not mine:
                continue
            trials.append(nct)
            for i in mine:
                aliases += [n for n in i.get("otherNames", []) if n not in aliases and len(n) < 40]
                if i.get("description"):
                    own_texts.append((i["description"], f"{nct} intervention description"))
            investigational = [i for i in ivs if i.get("type") in ("DRUG", "BIOLOGICAL", "GENETIC")]
            if len(investigational) == len(mine):  # the title can only describe this agent
                title = p["identificationModule"].get("officialTitle") or p["identificationModule"]["briefTitle"]
                own_texts.append((title, f"{nct} title (single investigational agent)"))
            conditions += [c for c in p.get("conditionsModule", {}).get("conditions", []) if c not in conditions]
            phases += [ph for ph in (p.get("designModule", {}).get("phases", []) or []) if ph in PHASE_ORDER]
            statuses.append(p["statusModule"]["overallStatus"])
            dates.append(p["statusModule"].get("lastUpdatePostDateStruct", {}).get("date", ""))
            sponsors.append((dates[-1], p["sponsorCollaboratorsModule"]["leadSponsor"]["name"]))
            collaborators |= {c["name"] for c in p["sponsorCollaboratorsModule"].get("collaborators", [])}
        ev = [e for e in evidence if e["program_id"] == prog["id"] and e.get("fetched")]
        ev_texts = [(e["quote"], f"{e['url']} (quote)") for e in ev if e["fact_type"] in ("target", "modality", "alias", "other", "approval")]
        targets = _scan(own_texts + ev_texts, TARGETS, first_only=False)
        modality = _scan(own_texts + ev_texts, MODALITIES, first_only=True)
        label = None
        for key, results in labels.items():
            if isinstance(results, list) and any(k in key for k in keys):
                label = results[0]
        row = {c: "" for c in COLUMNS}
        row.update({
            "Program ID": prog["id"], "Program": prog["name"], "Aliases": "; ".join(aliases[:6]),
            "Target": "; ".join(t[0] for t in targets), "Modality": modality[0][0] if modality else "",
            "Therapeutic Area": "Oncology", "Indication": "; ".join(conditions[:6]),
            "Highest Phase": PHASE_LABEL[max(phases, key=PHASE_ORDER.get)] if phases else "",
            "Status": ("Active trial in registry" if ACTIVE & set(statuses)
                       else "All registered trials terminated or withdrawn" if statuses and set(statuses) <= STOPPED
                       else f"Registry: no active trial ({', '.join(sorted(set(statuses)))})" if statuses else ""),
            "Status Date": max(dates) if dates else "",
            "Company": max(sponsors)[1] if sponsors else "",
            "Trial IDs": "; ".join(trials), "Partnerships": "; ".join(sorted(collaborators)),
            "Sources": "; ".join(CTGOV.format(t) for t in trials[:5]), "Source Date": "2026-10-29",
        })
        if label is not None:
            o = label["openfda"]
            row.update({"Highest Phase": "Marketed",
                        "Status": "Marketed in U.S. (FDA label lists gastric/GEJ adenocarcinoma)",
                        "US Rights Holder": f"{o['manufacturer_name'][0]} (U.S. labeler per FDA label; not a rights statement)",
                        "Company": o["manufacturer_name"][0]})
        rows.append(row)
        for field, where in [("Target", "; ".join(t[1] for t in targets)),
                             ("Modality", modality[0][1] if modality else ""),
                             ("Indication", "registry conditions"), ("Highest Phase", "registry phases / FDA label"),
                             ("Status", "registry overallStatus / FDA label"), ("Company", "registry lead sponsor (latest) / FDA labeler"),
                             ("Partnerships", "registry collaborators")]:
            if row[field]:
                provenance.append({"program_id": prog["id"], "field": field, "value": row[field], "derived_from": where})
    OUT.mkdir(exist_ok=True)
    with (OUT / "landscape_cldn18.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with (OUT / "field_provenance.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["program_id", "field", "value", "derived_from"])
        writer.writeheader()
        writer.writerows(provenance)
    library = {"documents": [{"url": e["url"], "title": e["title"], "date": e.get("date"), "text": e["quote"]}
                             for e in evidence if e.get("fetched")]}
    (OUT / "evidence_library.json").write_text(json.dumps(library, indent=1))
    print(f"{len(rows)} rows; {len(provenance)} provenance records; {len(library['documents'])} evidence documents")


if __name__ == "__main__":
    build()
