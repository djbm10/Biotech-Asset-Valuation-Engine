"""Build the REAL public FcRn / generalized myasthenia gravis landscape for DealScreen.

INTERNAL DEVELOPMENT. The program list below was curated by the same AI environment that
built DealScreen. It is not independent validation.

Every cell comes from a saved public source snapshot, with field-level provenance:
- ``sources/ctgov_myasthenia_gravis_snapshot.json``: ClinicalTrials.gov API v2, all
  interventional myasthenia gravis studies (retrieved 2026-10-28).
- ``sources/openfda_labels_snapshot.json``: openFDA drug-label API (retrieved 2026-10-28).
- ``sources/authority_extract.json``: ChEMBL 37 / Open Targets 26.06 drug->target edges
  and ChEMBL molecule types, extracted from the S&E ontology snapshot. The extract is
  written once (needs the ontology) and is then reused, so rebuilding needs no ontology
  and no network.

Rules:
- Nothing is invented. A field with no source is left blank: development status,
  ownership, geographic rights and licensing availability included.
- "Company" is the registry's lead sponsor, or the FDA labeler for a product whose U.S.
  label lists myasthenia gravis. It is not a statement of rights ownership.
- No U.S. rights statement was found in these sources for any program, so ``US Rights`` is
  blank for every row. Rights facts gathered separately go to the agent evidence library.

Usage: python research/dealscreen_real_v1/build_landscape.py [--refresh-authority]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "examples" / "dealscreen_real"
SRC = OUT / "sources"
CTGOV_URL = "https://clinicaltrials.gov/study/{}"
LABEL_URL = "https://api.fda.gov/drug/label.json?search=set_id:{}"

#: Curated program list. ``match``: lower-case substrings of registry intervention names or
#: otherNames (``exclude`` removes look-alikes). ``authority``: names looked up in the
#: ChEMBL/Open Targets extract. ``label``: key in the openFDA snapshot, with an optional
#: brand filter. ``registry_target`` / ``registry_modality``: verbatim registry phrases used
#: when the authority has nothing.
PROGRAMS: list[dict[str, Any]] = [
    {"id": "RW-01", "name": "Efgartigimod alfa (IV)", "match": ["efgartigimod", "argx-113"],
     "exclude": ["ph20", "pfs", " sc"], "authority": ["efgartigimod alfa", "ARGX-113"],
     "label": ("efgartigimod", "VYVGART"), "label_modality": "IgG1 antibody fragment"},
    {"id": "RW-02", "name": "Efgartigimod alfa and hyaluronidase (SC)", "match": ["ph20"],
     "authority": ["efgartigimod alfa"], "label": ("efgartigimod", "VYVGART Hytrulo"),
     "label_modality": "IgG1 antibody fragment co-formulated with hyaluronidase"},
    {"id": "RW-03", "name": "Rozanolixizumab", "match": ["rozanolixizumab", "ucb7665"],
     "authority": ["rozanolixizumab"]},
    {"id": "RW-04", "name": "Nipocalimab", "match": ["nipocalimab", "m281"], "authority": ["nipocalimab"],
     "label": ("nipocalimab", None)},
    {"id": "RW-05", "name": "Batoclimab", "match": ["batoclimab"], "authority": ["batoclimab"],
     "registry_target": ("FcRn", "anti-neonatal fragment crystallizable receptor (FcRn) monoclonal antibody")},
    {"id": "RW-06", "name": "HBM9161", "match": ["hbm9161"], "authority": ["HBM9161"]},
    {"id": "RW-07", "name": "RVT-1401", "match": ["rvt-1401"], "authority": ["RVT-1401"]},
    {"id": "RW-08", "name": "IMVT-1402", "match": ["imvt-1402"], "authority": ["IMVT-1402"]},
    {"id": "RW-09", "name": "Orilanolimab (ALXN1830)", "match": ["alxn1830"], "authority": ["ALXN1830"]},
    {"id": "RW-10", "name": "Eculizumab", "match": ["eculizumab"], "authority": ["eculizumab"],
     "label": ("eculizumab", "SOLIRIS")},
    {"id": "RW-11", "name": "Eculizumab-aeeb (BKEMV)", "match": [], "authority": ["eculizumab"],
     "label": ("eculizumab", "BKEMV")},
    {"id": "RW-12", "name": "Eculizumab-aagh (EPYSQLI)", "match": [], "authority": ["eculizumab"],
     "label": ("eculizumab", "EPYSQLI")},
    {"id": "RW-13", "name": "Ravulizumab", "match": ["ravulizumab", "alxn1210"], "authority": ["ravulizumab"],
     "label": ("ravulizumab", None)},
    {"id": "RW-14", "name": "Zilucoplan", "match": ["zilucoplan", "ra101495"], "authority": ["zilucoplan"],
     "label": ("zilucoplan", None)},
    {"id": "RW-15", "name": "Gefurulimab", "match": ["gefurulimab"], "authority": ["gefurulimab"]},
    {"id": "RW-16", "name": "ALXN1720", "match": ["alxn1720"], "authority": ["ALXN1720"]},
    {"id": "RW-17", "name": "Pozelimab + Cemdisiran", "match": ["pozelimab + cemdisiran"],
     "authority": ["pozelimab", "cemdisiran"]},
    {"id": "RW-18", "name": "Iptacopan", "match": ["iptacopan"], "authority": ["iptacopan"]},
    {"id": "RW-19", "name": "Vemircopan (ALXN2050)", "match": ["alxn2050"], "authority": ["ALXN2050"]},
    {"id": "RW-20", "name": "Claseprubart", "match": ["claseprubart", "dnth103"], "authority": ["claseprubart"]},
    {"id": "RW-21", "name": "Empasiprubart", "match": ["empasiprubart"], "authority": ["empasiprubart"]},
    {"id": "RW-22", "name": "Inebilizumab", "match": ["inebilizumab"], "authority": ["inebilizumab"]},
    {"id": "RW-23", "name": "Rituximab (investigator-sponsored)", "match": ["rituximab", "mabthera", "rituxan"],
     "authority": ["rituximab"]},
    {"id": "RW-24", "name": "Ublituximab", "match": ["ublituximab"], "authority": ["ublituximab"]},
    {"id": "RW-25", "name": "Mezagitamab (TAK-079)", "match": ["tak-079"], "exclude": ["placebo"],
     "authority": ["TAK-079"]},
    {"id": "RW-26", "name": "Telitacicept", "match": ["telitacicept", "rc18"], "authority": ["telitacicept"]},
    {"id": "RW-27", "name": "Povetacicept", "match": ["povetacicept"], "authority": ["povetacicept"]},
    {"id": "RW-28", "name": "Iscalimab (CFZ533)", "match": ["cfz533"], "authority": ["CFZ533"]},
    {"id": "RW-29", "name": "Belimumab", "match": ["belimumab"], "authority": ["belimumab"]},
    {"id": "RW-30", "name": "Satralizumab", "match": ["satralizumab"], "authority": ["satralizumab"]},
    {"id": "RW-31", "name": "Tocilizumab (investigator-sponsored)", "match": ["tocilizumab"],
     "authority": ["tocilizumab"]},
    {"id": "RW-32", "name": "Remibrutinib", "match": ["remibrutinib"], "authority": ["remibrutinib"]},
    {"id": "RW-33", "name": "Tolebrutinib", "match": ["tolebrutin"], "authority": ["tolebrutinib"]},
    {"id": "RW-34", "name": "Descartes-08", "match": ["descartes-08", "decartes-08"], "authority": [],
     "registry_target": ("BCMA", "chimeric antigen receptor directed to BCMA"), "registry_modality": "CAR-T"},
    {"id": "RW-35", "name": "KYV-101", "match": ["kyv-101"], "authority": [],
     "registry_target": ("CD19", "Anti-CD19 CAR-T cell therapy"), "registry_modality": "CAR-T"},
    {"id": "RW-36", "name": "CABA-201", "match": ["caba-201"], "authority": []},
    {"id": "RW-37", "name": "Anitocabtagene autoleucel", "match": ["anito-cel"], "authority": ["anitocabtagene autoleucel"],
     "registry_target": ("BCMA", "BCMA directed CAR T-cell therapy"), "registry_modality": "CAR-T"},
    {"id": "RW-38", "name": "SHR-2173", "match": ["shr-2173"], "authority": ["SHR-2173"]},
    {"id": "RW-39", "name": "Cizutamig", "match": ["cizutamig"], "authority": ["cizutamig"]},
    {"id": "RW-40", "name": "NMD670", "match": ["nmd670"], "authority": ["NMD670"]},
]

HEADERS = ["Program ID", "Program", "Aliases", "Target", "Mechanism", "Modality", "Therapeutic Area",
           "Indication", "Highest Phase", "Status", "Status Date", "Company", "Trial IDs", "US Rights",
           "US Rights Holder",
           "Geographic Notes", "Partnerships", "Sources", "Source Date", "Notes"]
_PHASE_RANK = {"PHASE1": 1, "PHASE1|PHASE2": 2, "PHASE2": 3, "PHASE2|PHASE3": 4, "PHASE3": 5, "PHASE4": 6}
_PHASE_LABEL = {1: "Phase 1", 2: "Phase 1/2", 3: "Phase 2", 4: "Phase 2/3", 5: "Phase 3", 6: "Phase 4"}
_ACTIVE = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"}


def write_authority_extract() -> None:
    """One-time extract from the S&E ontology (ChEMBL 37 / Open Targets 26.06)."""
    from bve.se.ontology.drug_modality import modality_authority
    from bve.se.ontology.records import EntityType
    from bve.se.ontology.resolver import ResolutionStatus
    from bve.se.ontology.targets import get_authority, get_resolver

    resolver, authority, modality = get_resolver(), get_authority(), modality_authority()
    assert resolver is not None and authority is not None
    names: dict[str, Any] = {}
    for program in PROGRAMS:
        for name in program["authority"]:
            res = resolver.resolve(name, EntityType.DRUG)
            entry: dict[str, Any] = {"resolution": res.status.value, "drug_id": res.canonical_id}
            if res.status is ResolutionStatus.RESOLVED and res.canonical_id:
                entry["edges"] = [
                    {"target": e.canonical_target_id, "relationship": e.relationship_type.value,
                     "action_type": e.action_type, "source": e.source, "release": e.source_release,
                     "record": e.source_record_id, "status": e.status.value}
                    for e in authority.edges_for(res.canonical_id)
                ]
                m = modality.modality_of_names([name]) if modality else None
                entry["molecule_type"] = m.molecule_type if m else None
                entry["chembl_ids"] = list(m.chembl_ids) if m else []
            names[name] = entry
    (SRC / "authority_extract.json").write_text(json.dumps(
        {"source": "S&E ontology snapshot (ChEMBL_37, Open Targets 26.06), resolver_v2",
         "ontology_version": getattr(resolver, "ontology_version", None), "names": names}, indent=1) + "\n")


def _trials(snapshot: dict, program: dict) -> list[dict]:
    hits = []
    for study in snapshot["studies"]:
        for iv in study["interventions"]:
            text = " ".join([iv["name"], *iv["other_names"]]).casefold()
            if any(m in text for m in program["match"]) and not any(x in text for x in program.get("exclude", [])):
                hits.append({"study": study, "intervention": iv})
                break
    return hits


def build() -> dict[str, Any]:
    ctgov = json.loads((SRC / "ctgov_myasthenia_gravis_snapshot.json").read_text())
    labels = json.loads((SRC / "openfda_labels_snapshot.json").read_text())
    authority = json.loads((SRC / "authority_extract.json").read_text())["names"]
    rows, provenance = [], []

    for p in PROGRAMS:
        cells: dict[str, str] = {h: "" for h in HEADERS}
        cells["Program ID"], cells["Program"] = p["id"], p["name"]

        def prov(field: str, value: str, source: str, url: str, date: str, quote: str,
                 program_id: str = p["id"]) -> None:
            provenance.append({"program_id": program_id, "field": field, "value": value, "source": source,
                               "url": url, "source_date": date, "quote_or_record": quote})

        prov("Program", p["name"], "curation (INTERNAL DEVELOPMENT)", "", "2026-10-28",
             "program grouping chosen by the curator; see build_landscape.py PROGRAMS")
        hits = _trials(ctgov, p)
        sources: list[str] = []
        aliases: list[str] = []
        for h in hits:
            for name in [h["intervention"]["name"], *h["intervention"]["other_names"]]:
                if name.casefold() != p["name"].casefold() and name not in aliases and len(aliases) < 6:
                    aliases.append(name)
        if aliases:
            cells["Aliases"] = "; ".join(aliases)
            prov("Aliases", cells["Aliases"], "ClinicalTrials.gov intervention name/otherNames",
                 CTGOV_URL.format(hits[0]["study"]["nct_id"]), ctgov["retrieved_at"][:10],
                 "registry intervention names for the matched trials")

        # Label (U.S. marketed product with a myasthenia gravis indication).
        label = None
        if p.get("label"):
            key, brand = p["label"]
            for res in labels["labels"][key]["results"]:
                if brand is None or brand in (res.get("brand_name") or []):
                    label = res
                    break
        label_mg = bool(label and "myasthenia" in label["indications_and_usage"].casefold())
        label_date = ""
        if label:
            eff = label["effective_time"]
            label_date = f"{eff[:4]}-{eff[4:6]}-{eff[6:]}"
            sources.append(LABEL_URL.format(label["set_id"]))

        # Phase and status from the registry.
        ranks = [(_PHASE_RANK.get("|".join(h["study"]["phases"]), 0), h["study"]) for h in hits]
        ranks = [r for r in ranks if r[0]]
        if label_mg:
            cells["Highest Phase"] = "Marketed"
            cells["Status"] = "Marketed in U.S. (FDA label lists myasthenia gravis)"
            cells["Status Date"] = label_date
            prov("Highest Phase", "Marketed", "openFDA drug label", sources[-1], label_date,
                 label["indications_and_usage"][:300])
            prov("Status", cells["Status"], "openFDA drug label indications", sources[-1], label_date,
                 label["indications_and_usage"][:300])
            prov("Status Date", label_date, "openFDA label effective_time", sources[-1], label_date,
                 label["effective_time"])
        elif ranks:
            best = max(r[0] for r in ranks)
            cells["Highest Phase"] = _PHASE_LABEL[best]
            best_study = max((s for r, s in ranks if r == best), key=lambda s: s["last_update"] or "")
            prov("Highest Phase", cells["Highest Phase"], "ClinicalTrials.gov phase",
                 CTGOV_URL.format(best_study["nct_id"]), best_study["last_update"] or "",
                 f"{best_study['nct_id']} phases={best_study['phases']}")
            statuses = {s["overall_status"] for _, s in ranks}
            latest = max((s for _, s in ranks), key=lambda s: s["last_update"] or "")
            if statuses & _ACTIVE:
                cells["Status"] = "Active trial in registry"
            elif statuses <= {"TERMINATED", "WITHDRAWN"}:
                cells["Status"] = "All registered gMG trials terminated or withdrawn"
            else:
                cells["Status"] = "Registry: no recruiting gMG trial (" + ", ".join(sorted(statuses)) + ")"
            cells["Status Date"] = latest["last_update"] or ""
            prov("Status", cells["Status"], "ClinicalTrials.gov overallStatus",
                 CTGOV_URL.format(latest["nct_id"]), cells["Status Date"],
                 "; ".join(f"{s['nct_id']}={s['overall_status']}" for _, s in ranks))
            prov("Status Date", cells["Status Date"], "ClinicalTrials.gov lastUpdatePostDate",
                 CTGOV_URL.format(latest["nct_id"]), cells["Status Date"], latest["nct_id"])
        if hits:
            nct = sorted({h["study"]["nct_id"] for h in hits})
            cells["Trial IDs"] = "; ".join(nct)
            sources.extend(CTGOV_URL.format(n) for n in nct[:4])
            conditions: list[str] = []
            for h in hits:
                for c in h["study"]["conditions"]:
                    if "myasth" in c.casefold() and c not in conditions:
                        conditions.append(c)
            cells["Indication"] = "; ".join(conditions[:3])
            prov("Indication", cells["Indication"], "ClinicalTrials.gov conditions",
                 CTGOV_URL.format(nct[0]), ctgov["retrieved_at"][:10], "registry conditions, verbatim")
        elif label_mg:
            cells["Indication"] = "Myasthenia Gravis"
            prov("Indication", "Myasthenia Gravis", "openFDA drug label", sources[0], label_date,
                 label["indications_and_usage"][:300])
        cells["Therapeutic Area"] = "Neurology" if cells["Indication"] else ""
        if cells["Therapeutic Area"]:
            prov("Therapeutic Area", "Neurology", "curation (INTERNAL DEVELOPMENT): assigned from the "
                 "myasthenia gravis indication, not stated by a source", "", "2026-10-28", "")

        # Company: FDA labeler for a gMG-labelled product, otherwise latest lead sponsor.
        if label_mg:
            cells["Company"] = (label.get("manufacturer_name") or [""])[0]
            prov("Company", cells["Company"], "openFDA labeler (not a rights statement)",
                 sources[0], label_date, "manufacturer_name")
        elif hits:
            latest = max((h["study"] for h in hits), key=lambda s: s["last_update"] or "")
            cells["Company"] = latest["lead_sponsor"]
            prov("Company", cells["Company"], "ClinicalTrials.gov lead sponsor (not a rights statement)",
                 CTGOV_URL.format(latest["nct_id"]), latest["last_update"] or "", "leadSponsor")
            collaborators = sorted({c for h in hits for c in h["study"]["collaborators"]})
            if collaborators:
                cells["Partnerships"] = "Registry collaborators: " + ", ".join(collaborators)
                prov("Partnerships", cells["Partnerships"], "ClinicalTrials.gov collaborators",
                     CTGOV_URL.format(latest["nct_id"]), latest["last_update"] or "", "collaborators")
        if label_mg:
            cells["Geographic Notes"] = f"U.S.-labelled product ({', '.join(label.get('brand_name') or [])})"
            labeler = (label.get("manufacturer_name") or [""])[0]
            if labeler:
                cells["US Rights Holder"] = f"{labeler} (U.S. commercializer per FDA label)"
                prov("US Rights Holder", cells["US Rights Holder"],
                     "openFDA labeler of a U.S. label listing myasthenia gravis; evidence of U.S. "
                     "commercialization, not of licensing terms or availability",
                     sources[0], label_date, "manufacturer_name")

        # Target / mechanism / modality: authority first, verbatim registry text second.
        targets, actions, records, molecule_type = [], [], [], None
        for name in p["authority"]:
            entry = authority.get(name, {})
            molecule_type = molecule_type or entry.get("molecule_type")
            for e in entry.get("edges", []):
                if e["relationship"] == "DIRECT_TARGET" and e["status"] == "USABLE" and e["target"]:
                    sym = e["target"].removeprefix("TARGET:")
                    if sym not in targets:
                        targets.append(sym)
                    if e["action_type"] and e["action_type"] not in actions:
                        actions.append(e["action_type"])
                    records.append(f"{e['source']} {e['release']} record {e['record']}")
        if targets:
            cells["Target"] = "; ".join(targets)
            cells["Mechanism"] = f"{'/'.join(targets)} {' / '.join(a.lower() for a in actions)}".strip()
            prov("Target", cells["Target"], "ChEMBL / Open Targets drug->target edge", "",
                 "ChEMBL_37 / OT 26.06", "; ".join(sorted(set(records))[:4]))
            prov("Mechanism", cells["Mechanism"], "ChEMBL / Open Targets action_type", "",
                 "ChEMBL_37 / OT 26.06", "; ".join(sorted(set(records))[:4]))
        elif p.get("registry_target"):
            symbol, quote = p["registry_target"]
            cells["Target"] = symbol
            prov("Target", symbol, "ClinicalTrials.gov intervention description",
                 CTGOV_URL.format(hits[0]["study"]["nct_id"]) if hits else "", ctgov["retrieved_at"][:10], quote)
        if molecule_type:
            cells["Modality"] = molecule_type
            prov("Modality", molecule_type, "ChEMBL molecule_type", "", "ChEMBL_37", molecule_type)
        elif p.get("label_modality") and label:
            cells["Modality"] = p["label_modality"]
            prov("Modality", cells["Modality"], "openFDA label mechanism section", sources[0], label_date,
                 label["mechanism_of_action"][:300])
        elif p.get("registry_modality"):
            cells["Modality"] = p["registry_modality"]
            prov("Modality", cells["Modality"], "ClinicalTrials.gov intervention description",
                 CTGOV_URL.format(hits[0]["study"]["nct_id"]) if hits else "", ctgov["retrieved_at"][:10],
                 (hits[0]["intervention"]["description"] or "")[:200] if hits else "")

        dates = [d for d in [cells["Status Date"], label_date] if d]
        cells["Source Date"] = max(dates) if dates else ctgov["retrieved_at"][:10]
        cells["Sources"] = "; ".join(dict.fromkeys(sources))
        notes = []
        if not hits and not label:
            notes.append("No matching registry record or label in the snapshots")
        if not cells["Target"]:
            notes.append("Target not stated in the sources used")
        cells["Notes"] = "; ".join(notes)
        rows.append(cells)

    # v1 (pinned regression) has no holder column; v2 adds it (Cycle 3).
    with (OUT / "landscape_fcrn_gmg.csv").open("w", newline="", encoding="utf-8") as handle:
        v1 = [h for h in HEADERS if h != "US Rights Holder"]
        writer = csv.DictWriter(handle, fieldnames=v1, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with (OUT / "landscape_fcrn_gmg_v2.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    with (OUT / "field_provenance.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(provenance[0]))
        writer.writeheader()
        writer.writerows(provenance)
    return {"programs": len(rows), "provenance_rows": len(provenance)}


if __name__ == "__main__":
    if "--refresh-authority" in sys.argv or not (SRC / "authority_extract.json").exists():
        write_authority_extract()
    print(build())
