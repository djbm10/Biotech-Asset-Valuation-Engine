"""Materialize frozen manual annotations; not an attribution/extraction engine."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from bve.se.schemas.treatment_cohort import TreatmentCohortAttribution


def materialize(row: dict) -> TreatmentCohortAttribution:
    passage = {
        "reference": row["text_reference"], "field": row["text_field"],
        "start": 0, "end": len(row["text"]), "text": row["text"],
    }
    source = row["source"]
    captured_source = None if source is None else {
        "document_id": source["document_id"], "source_url": source["source_url"],
        "document_type": source["document_type"], "snapshot_path": source["snapshot_path"],
        "snapshot_sha256": row["source_snapshot_sha256"],
    }
    # This is a supplied adopted certificate, not a receipt-to-ownership inference.
    proof = None
    if row["expected_relation"] == "RESULT_OWNERSHIP":
        proof = {
            "basis": row["basis"], "grounding_reference": row["annotation_reference"],
            "treatment_cohort_evidence": passage, "result_cohort_evidence": passage,
            "result_treatment_evidence": passage, "qualifiers": row["qualifiers"],
        }
    return TreatmentCohortAttribution.model_validate({
        "attribution_id": "treatment-attribution:" + hashlib.sha256(
            row["witness_id"].encode()).hexdigest(),
        "witness_id": row["witness_id"], "asset_id": row["asset_id"],
        "candidate_names": row["candidate_names"], "relationship": row["expected_relation"],
        "receipt_status": row["receipt_status"],
        "cohort_membership_status": row["cohort_membership_status"],
        "result_ownership_status": row["result_ownership_status"],
        "scope": row["scope"], "basis": row["basis"], "passage": passage,
        "grounding_reference": row["annotation_reference"], "source": captured_source,
        "trial_context_ids": row["trial_ids"], "arm": row["arm_id"],
        "result_group": row["result_group_id"], "regimen_components": row["regimen_components"],
        "qualifiers": row["qualifiers"], "reason": row["reason"],
        "ownership_certificate": proof,
    })


def serialize(rows: list[dict]) -> str:
    return "\n".join(materialize(row).canonical_json() for row in rows) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(serialize(json.loads(args.population.read_text())))


if __name__ == "__main__":
    main()
