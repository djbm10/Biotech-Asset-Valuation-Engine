"""Tier A adapter: resolves IS_DIAGNOSTIC_THERAPEUTIC_OR_PROCEDURAL using the
already-captured ClinicalTrials.gov candidate-bearing field
interventions[].type (Milestone 2 registry-history source), which is
itself Tier A authority per Section 5 ("ClinicalTrials.gov candidate-bearing
fields already captured"). No new network access is required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdcd1_external_authority_lib as lib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OLD_WT = Path("/tmp/claude-1000/-home-djmann/90a2afa9-89b8-4374-9690-8552e2a3ec32/scratchpad/pdcd1_evidence_final_wt")
M2_SOURCE = OLD_WT / "artifacts/pipeline/pdcd1_rebase_v1/stages/02_registry_history_capture/62914ac00fa635d38755e25b/source"
M3_SNAPSHOT = OLD_WT / "artifacts/pipeline/pdcd1_rebase_v1/stages/03_candidate_bearing_evidence_triage/f5dd19d08deb59a75232d3bc"
SUBJECT_LEDGER = ROOT / "_m4_scratch" / "authority_research_subject_ledger.jsonl"

MODALITY_TYPES = {
    "DRUG", "BIOLOGICAL", "COMBINATION_PRODUCT", "DIETARY_SUPPLEMENT", "GENETIC",
}
NONPRODUCT_TYPES = {
    "PROCEDURE", "DEVICE", "DIAGNOSTIC_TEST", "RADIATION", "BEHAVIORAL", "OTHER",
}


def load_occurrence_index():
    occ_to_field = {}
    with (M3_SNAPSHOT / "normalized" / "candidate_bearing_occurrence_ledger.jsonl").open() as f:
        for line in f:
            row = json.loads(line)
            occ_to_field[row["occurrence_id"]] = row


def main() -> None:
    occ_index = {}
    with (M3_SNAPSHOT / "normalized" / "candidate_bearing_occurrence_ledger.jsonl").open() as f:
        for line in f:
            row = json.loads(line)
            occ_index[row["occurrence_id"]] = row

    # Cache intervention type by (nct_id, intervention_index) across all
    # version files actually referenced, resolved from the "current" file
    # per study (Tier A: current authoritative registry state).
    type_cache: dict[str, list[dict]] = {}

    def interventions_for(nct_id: str):
        if nct_id in type_cache:
            return type_cache[nct_id]
        f = M2_SOURCE / nct_id / "current.json"
        if not f.is_file():
            type_cache[nct_id] = []
            return []
        d = json.loads(f.read_text())
        ivs = d.get("protocolSection", {}).get("armsInterventionsModule", {}).get("interventions", [])
        type_cache[nct_id] = ivs
        return ivs

    subjects = [json.loads(l) for l in SUBJECT_LEDGER.read_text().splitlines() if l.strip()]
    units = []
    for subject in subjects:
        occ_ids = subject["milestone3_evidence_bindings"]["occurrence_ids"]
        observed_types = set()
        detail_rows = []
        for occ_id in occ_ids:
            occ = occ_index.get(occ_id)
            if not occ:
                continue
            ivs = interventions_for(occ["nct_id"])
            idx = occ["intervention_index"]
            if idx < len(ivs):
                t = ivs[idx].get("type")
                if t:
                    observed_types.add(t)
                    detail_rows.append({"nct_id": occ["nct_id"], "intervention_index": idx, "type": t})

        assertions = []
        if observed_types:
            evidence_hash = lib.stable_hash(sorted(detail_rows, key=lambda r: (r["nct_id"], r["intervention_index"])))
            if observed_types & MODALITY_TYPES and not (observed_types & NONPRODUCT_TYPES):
                assertions.append({
                    "assertion_type": "MODALITY_EXPLICIT",
                    "subject_id": subject["subject_id"],
                    "evidence_location": "protocolSection.armsInterventionsModule.interventions[].type",
                    "authority_tier": "tier_a",
                    "source_date": None,
                    "evidence_hash": evidence_hash,
                    "confidence_class": "HIGH_TIER_A_REGISTRY_FIELD",
                    "detail": {"observed_types": sorted(observed_types), "modality": "PRODUCT_LIKE"},
                })
            elif observed_types & NONPRODUCT_TYPES and not (observed_types & MODALITY_TYPES):
                assertions.append({
                    "assertion_type": "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME",
                    "subject_id": subject["subject_id"],
                    "evidence_location": "protocolSection.armsInterventionsModule.interventions[].type",
                    "authority_tier": "tier_a",
                    "source_date": None,
                    "evidence_hash": evidence_hash,
                    "confidence_class": "HIGH_TIER_A_REGISTRY_FIELD",
                    "detail": {"observed_types": sorted(observed_types), "modality": "NON_PRODUCT_PROCEDURAL_OR_DIAGNOSTIC"},
                })
            else:
                assertions.append({
                    "assertion_type": "MODALITY_EXPLICIT",
                    "subject_id": subject["subject_id"],
                    "evidence_location": "protocolSection.armsInterventionsModule.interventions[].type",
                    "authority_tier": "tier_a",
                    "source_date": None,
                    "evidence_hash": evidence_hash,
                    "confidence_class": "MIXED_TIER_A_REGISTRY_FIELD",
                    "detail": {"observed_types": sorted(observed_types), "modality": "MIXED_ACROSS_OCCURRENCES", "note": "SOURCE_NOT_EXHAUSTIVE: differing intervention type across bound occurrences; treat as conflict candidate, not resolved."},
                })

        unit = {
            "subject_id": subject["subject_id"],
            "source_target": "clinicaltrials_gov_candidate_bearing_field",
            "assertions": assertions,
        }
        units.append(unit)

    out = ROOT / "_m4_scratch" / "ctgov_modality_units.jsonl"
    with out.open("w") as f:
        for u in units:
            f.write(json.dumps(u, sort_keys=True) + "\n")
    print(f"wrote {len(units)} units to {out}")
    resolved = sum(1 for u in units if u["assertions"])
    print(f"resolved (had at least one assertion): {resolved}")


if __name__ == "__main__":
    main()
