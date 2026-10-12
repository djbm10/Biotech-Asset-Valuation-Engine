"""Inert, grounded treatment/cohort provenance; never emits efficacy facts.

These records validate an explicitly supplied evidence certificate. They do not
infer scientific attribution from text, identity, trial membership or receipt.
No existing extraction or decision path consumes them.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from bve.se.schemas.contracts import StrictModel


class FrozenProvenance(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AttributionStatus(str, Enum):
    CERTIFIED = "CERTIFIED"
    UNKNOWN = "UNKNOWN"


class TreatmentRelationship(str, Enum):
    RECEIPT = "RECEIPT"
    REGIMEN_RECEIPT = "REGIMEN_RECEIPT"
    RESULT_OWNERSHIP = "RESULT_OWNERSHIP"
    UNRESOLVED = "UNRESOLVED"


class TreatmentScope(str, Enum):
    SINGLE_NAMED_TREATMENT = "SINGLE_NAMED_TREATMENT"
    EXPLICIT_ADD_ON_COMPARISON = "EXPLICIT_ADD_ON_COMPARISON"
    REGIMEN_COMPONENT = "REGIMEN_COMPONENT"
    POOLED_REGIMEN = "POOLED_REGIMEN"
    NONCLINICAL = "NONCLINICAL"
    NON_TREATMENT = "NON_TREATMENT"
    UNRESOLVED = "UNRESOLVED"


class ArtifactReference(FrozenProvenance):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    json_pointer: str = Field(pattern=r"^/")


class TextEvidence(FrozenProvenance):
    """An exact assertion span in a versioned artifact, not a proximity window."""

    reference: ArtifactReference
    field: str = Field(min_length=1)
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def exact_length(self) -> TextEvidence:
        if self.end - self.start != len(self.text):
            raise ValueError("Evidence offsets must match the exact text length")
        return self


class CapturedSource(FrozenProvenance):
    document_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    snapshot_path: str = Field(min_length=1)
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class VersionedArmReference(FrozenProvenance):
    """Context only; a protocol arm is not an observed result group."""

    trial_id: str = Field(min_length=1)
    arm_label: str = Field(min_length=1)
    source: CapturedSource
    evidence: ArtifactReference


class VersionedResultGroupReference(FrozenProvenance):
    result_group_id: str = Field(min_length=1)
    source: CapturedSource
    evidence: ArtifactReference


class OwnershipCertificate(FrozenProvenance):
    """Already grounded prose proof, never derived from a receipt record.

    Structured/discourse ownership certification is deliberately not implemented
    by this representation of the currently adopted explicit-prose certificates.
    """

    basis: Literal["A_EXPLICIT_PROSE", "A_ACCEPTED_ALIAS"]
    grounding_reference: ArtifactReference
    treatment_cohort_evidence: TextEvidence
    result_cohort_evidence: TextEvidence
    result_treatment_evidence: TextEvidence
    qualifiers: tuple[str, ...] = Field(min_length=1)


class TreatmentCohortAttribution(FrozenProvenance):
    attribution_id: str = Field(min_length=1)
    witness_id: str = Field(min_length=1)
    asset_id: str | None = None
    candidate_names: tuple[str, ...] = Field(min_length=1)
    relationship: TreatmentRelationship
    receipt_status: AttributionStatus
    cohort_membership_status: AttributionStatus
    result_ownership_status: AttributionStatus
    scope: TreatmentScope
    basis: Literal["A_EXPLICIT_PROSE", "A_ACCEPTED_ALIAS", "D_REGIMEN", "G_UNSUPPORTED"]
    passage: TextEvidence
    grounding_reference: ArtifactReference
    source: CapturedSource | None = None
    trial_context_ids: tuple[str, ...] = ()
    arm: VersionedArmReference | None = None
    result_group: VersionedResultGroupReference | None = None
    regimen_components: tuple[str, ...] = ()
    qualifiers: tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    ownership_certificate: OwnershipCertificate | None = None

    @model_validator(mode="after")
    def separate_receipt_and_ownership(self) -> TreatmentCohortAttribution:
        certified = AttributionStatus.CERTIFIED
        unresolved = self.relationship == TreatmentRelationship.UNRESOLVED
        owns = self.relationship == TreatmentRelationship.RESULT_OWNERSHIP
        if (self.receipt_status == certified) != (not unresolved):
            raise ValueError("Relationship and receipt status disagree")
        if (self.cohort_membership_status == certified) != (not unresolved):
            raise ValueError("Actual treatment-linked cohort membership must be independently supplied")
        if (self.result_ownership_status == certified) != owns:
            raise ValueError("Receipt is not result ownership")
        if (self.ownership_certificate is not None) != owns:
            raise ValueError("Only explicit result ownership carries an ownership certificate")
        component = self.scope in {
            TreatmentScope.REGIMEN_COMPONENT, TreatmentScope.POOLED_REGIMEN,
        }
        if self.relationship == TreatmentRelationship.REGIMEN_RECEIPT:
            if not component or len(self.regimen_components) < 2 or self.basis != "D_REGIMEN":
                raise ValueError("Regimen receipt requires component scope and retained regimen")
        if component and not unresolved and self.relationship != TreatmentRelationship.REGIMEN_RECEIPT:
            raise ValueError("Regimen component receipt cannot own a pooled/regimen result")
        if self.relationship == TreatmentRelationship.RECEIPT:
            if self.scope != TreatmentScope.SINGLE_NAMED_TREATMENT or self.regimen_components:
                raise ValueError("Single-treatment receipt cannot discard regimen scope")
        if not unresolved and self.scope in {
            TreatmentScope.NONCLINICAL, TreatmentScope.NON_TREATMENT, TreatmentScope.UNRESOLVED,
        }:
            raise ValueError("Nonclinical/unsupported scope cannot certify human treatment receipt")
        if owns:
            if self.scope not in {
                TreatmentScope.SINGLE_NAMED_TREATMENT, TreatmentScope.EXPLICIT_ADD_ON_COMPARISON,
            }:
                raise ValueError("Ownership requires a certified whole-treatment/add-on result")
            proof = self.ownership_certificate
            assert proof is not None
            if proof.basis != self.basis or proof.grounding_reference != self.grounding_reference:
                raise ValueError("Ownership proof must retain its independent grounding and basis")
            if proof.qualifiers != self.qualifiers:
                raise ValueError("Ownership cannot discard or change scope qualifiers")
            if any(e != self.passage for e in (
                proof.treatment_cohort_evidence, proof.result_cohort_evidence,
                proof.result_treatment_evidence,
            )):
                raise ValueError("The adopted prose proof must refer to the same grounded assertion")
            if self.regimen_components and self.scope != TreatmentScope.EXPLICIT_ADD_ON_COMPARISON:
                raise ValueError("Components require explicitly retained add-on comparison scope")
        if self.arm is not None and self.arm.trial_id not in self.trial_context_ids:
            raise ValueError("Arm labels must retain their trial context and source version")
        return self

    def canonical_json(self) -> str:
        """Stable sidecar serialization; does not serialize or modify existing runs."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"))
