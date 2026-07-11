"""Assign asset–indication results to explicit comparable cohorts."""

from __future__ import annotations

import hashlib

from bve.se.schemas.contracts import ClinicalResult, CohortAssignment, CohortStatus


def _stage_band(stage: str) -> str | None:
    normalized = stage.upper().replace(" ", "_")
    if normalized in {"PHASE_1", "PHASE_1_2"}:
        return "EARLY_CLINICAL"
    if normalized == "PHASE_2":
        return "MID_CLINICAL"
    if normalized in {"PHASE_3", "REGISTRATION", "APPROVED"}:
        return "LATE_OR_REGISTRATIONAL"
    return None


def assign_cohort(result: ClinicalResult) -> CohortAssignment:
    required = {
        "indication": result.indication,
        "population": result.population,
        "treatment_line": result.treatment_line,
        "stage": result.development_stage,
        "endpoint_family": result.endpoint_family,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    stage_band = _stage_band(result.development_stage)
    if missing or stage_band is None:
        reason = "Missing cohort fields: " + ", ".join(missing or ["recognized stage"])
        return CohortAssignment(
            subject_id=result.subject_id,
            indication=result.indication or None,
            population=result.population or None,
            treatment_line=result.treatment_line or None,
            stage=result.development_stage or None,
            endpoint_family=result.endpoint_family or None,
            status=CohortStatus.COHORT_UNRESOLVED,
            rationale=reason,
            supporting_claim_ids=result.supporting_claim_ids,
        )
    parts = [
        result.indication.casefold().strip(),
        result.population.casefold().strip(),
        result.treatment_line.casefold().strip(),
        stage_band,
        result.endpoint_family.casefold().strip(),
    ]
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return CohortAssignment(
        subject_id=result.subject_id,
        indication=result.indication,
        population=result.population,
        treatment_line=result.treatment_line,
        stage=stage_band,
        endpoint_family=result.endpoint_family,
        cohort_id=f"cohort:{digest}",
        status=CohortStatus.COMPARABLE,
        rationale="All required cohort dimensions are normalized.",
        supporting_claim_ids=result.supporting_claim_ids,
    )
