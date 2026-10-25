"""Operator adjudication for il3ra_clinical_any_v1 (labelled; NOT the official score).

    python adjudicate.py RESULT.json REFERENCE.json OUT.json

The official scorer matches candidates to reference assets by exact name. This adds a
second, labelled view:
- trial-linked match: a candidate counts as finding a reference asset when it carries one of
  that asset's reference trial ids;
- modality compared after mapping both vocabularies to a coarse class.

The engine output and the reference are not changed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROUTES = [("eligible_asset_ids", "ELIGIBLE"), ("unresolved_asset_ids", "REVIEW"),
          ("excluded_asset_ids", "EXCLUDED"), ("low_support_asset_ids", "LOW_SUPPORT")]
VISIBLE = {"ELIGIBLE", "REVIEW"}

# Coarse class: the engine's authority/discovery codes and the reference's free text.
COARSE = {
    "ANTIBODY_DRUG_CONJUGATE": "adc", "antibody-drug conjugate": "adc",
    "ANTIBODY": "antibody", "MONOCLONAL_ANTIBODY": "antibody", "monoclonal antibody": "antibody",
    "BISPECIFIC_ANTIBODY": "engager", "MULTISPECIFIC_ANTIBODY": "engager",
    "T_CELL_ENGAGER": "engager", "T-cell engager": "engager",
    "CAR_T": "cell", "CELL_THERAPY": "cell", "GENE_THERAPY": "cell", "CAR-T": "cell",
    "SMALL_MOLECULE": "small molecule", "small molecule": "small molecule",
    "PROTEIN": "protein", "radioligand": "radioligand",
}


def coarse(value: str | None) -> str | None:
    if not value:
        return None
    if value in COARSE:
        return COARSE[value]
    low = value.lower()
    if "engager" in low:
        return "engager"
    if "cell" in low or "car" in low:
        return "cell"
    if "fusion" in low or "toxin" in low:
        return "protein"
    if "conjugate" in low:
        return "adc"
    return low


def main() -> None:
    result = json.loads(Path(sys.argv[1]).read_text())
    reference = json.loads(Path(sys.argv[2]).read_text())
    route = {i: lab for key, lab in ROUTES for i in result[key]}
    cands = result["candidates"]
    rows = []
    for ref in reference["assets"]:
        trials = {t.upper() for t in ref["trial_ids"]}
        names = {n.lower() for n in ref["names"]}
        hits = [c for c in cands
                if trials & {t.upper() for t in c["trial_ids"]}
                or names & {n.lower() for n in [c["canonical_name"], *c.get("aliases", [])]}]
        found_trials = trials & {t.upper() for c in hits for t in c["trial_ids"]}
        visible = [c for c in hits if route.get(c["asset_id"]) in VISIBLE]
        ref_mod = coarse(ref["modality"])
        stated = {coarse(c.get("authority_modality") or c.get("modality_id")) for c in hits} - {None}
        rows.append({
            "reference_id": ref["reference_id"], "in_scope": ref["in_scope"],
            "name": ref["names"][0],
            "candidates": [{"name": c["canonical_name"], "route": route.get(c["asset_id"]),
                            "target_ids": c["target_ids"],
                            "authority_modality": c.get("authority_modality"),
                            "discovery_modality": c.get("modality_id"),
                            "trials": len(c["trial_ids"])} for c in hits],
            "found_any": bool(hits), "found_visible": bool(visible),
            "n_visible_rows": len(visible),
            "ref_trials": len(trials), "trials_found": len(found_trials),
            "modality_ref": ref_mod, "modality_stated": sorted(stated),
            "modality_ok": (stated == {ref_mod}) if stated and ref_mod else None,
            "target_stated": any(c["target_ids"] for c in hits),
        })
    ins = [r for r in rows if r["in_scope"]]
    mod = [r for r in ins if r["modality_ok"] is not None]
    summary = {
        "in_scope": len(ins),
        "found_any_route": sum(r["found_any"] for r in ins),
        "found_visible": sum(r["found_visible"] for r in ins),
        "visible_rows_for_reference_assets": sum(r["n_visible_rows"] for r in ins),
        "trials_found": sum(r["trials_found"] for r in ins),
        "trials_ref": sum(r["ref_trials"] for r in ins),
        "complete_trial_history": sum(r["found_any"] and r["trials_found"] == r["ref_trials"]
                                      for r in ins),
        "target_stated_on_found": sum(r["target_stated"] for r in ins if r["found_any"]),
        "modality_coarse_ok": sum(bool(r["modality_ok"]) for r in mod),
        "modality_coarse_stated": len(mod),
        "controls_visible": sum(r["found_visible"] for r in rows if not r["in_scope"]),
        "controls_any_route": sum(r["found_any"] for r in rows if not r["in_scope"]),
    }
    Path(sys.argv[3]).write_text(json.dumps({"summary": summary, "assets": rows}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
