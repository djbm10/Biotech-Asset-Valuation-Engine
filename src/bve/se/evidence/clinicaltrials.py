"""Deterministic claim extraction from ClinicalTrials.gov protocol snapshots."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from bve.se.discovery.adapters import _candidate_interventions, _targets_in_text
from bve.se.schemas.contracts import (
    CandidateHit,
    ClinicalResult,
    ExtractedClaim,
    NormalizedFact,
    SourceDocument,
    TemporalFact,
    VerificationStatus,
)

_ONCOLOGY_TERMS = (
    "leukemia",
    "lymphoma",
    "myeloma",
    "malignancy",
    "cancer",
    "tumor",
)

_STAGE_ORDER = {
    "EARLY_PHASE1": 2,
    "PHASE1": 2,
    "PHASE1|PHASE2": 2,
    "PHASE2": 3,
    "PHASE3": 4,
    "PHASE4": 6,
}


class ExtractionBundle(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)
    facts: list[NormalizedFact] = Field(default_factory=list)
    clinical_results: list[ClinicalResult] = Field(default_factory=list)


def _id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _claim(
    hit: CandidateHit,
    document: SourceDocument,
    *,
    predicate: str,
    value,
    passage: str,
    locator: str,
) -> ExtractedClaim:
    return ExtractedClaim(
        claim_id=_id("claim", hit.hit_id, predicate, json.dumps(value, sort_keys=True)),
        subject_id=hit.hit_id,
        predicate=predicate,
        normalized_value=value,
        source_document_id=document.document_id,
        supporting_passage=passage,
        locator=locator,
        direct_observation=True,
        extraction_method="clinicaltrials_structured",
        extractor_version="ctgov_v1",
        extraction_confidence=0.95,
        verification_status=VerificationStatus.MACHINE_VERIFIED,
        applicable_as_of_date=hit.applicable_as_of_date,
    )


def _fact(hit: CandidateHit, claim: ExtractedClaim, fact_type: str, value) -> NormalizedFact:
    return NormalizedFact(
        fact_id=_id("fact", hit.hit_id, fact_type),
        subject_id=hit.hit_id,
        fact_type=fact_type,
        value=value,
        supporting_claim_ids=[claim.claim_id],
        confidence=claim.extraction_confidence,
    )


class ClinicalTrialsEvidenceExtractor:
    """Extract only facts directly represented in the structured trial registry record."""

    version = "ctgov_v1"

    def extract(self, hit: CandidateHit, document: SourceDocument) -> ExtractionBundle:
        if not document.snapshot_path:
            raise ValueError("ClinicalTrials.gov extraction requires a saved source snapshot")
        protocol = json.loads(Path(document.snapshot_path).read_text())
        identification = protocol.get("identificationModule", {})
        design = protocol.get("designModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        status_module = protocol.get("statusModule", {})
        interventions = {name: (targets, modality) for name, targets, modality in _candidate_interventions(protocol)}
        candidate = interventions.get(hit.asset_name or "")
        raw_intervention: dict = next(
            (
                intervention
                for intervention in protocol.get("armsInterventionsModule", {}).get("interventions", [])
                if intervention.get("name") == hit.asset_name
            ),
            {},
        )
        intervention_passage = json.dumps(raw_intervention, sort_keys=True)
        claims: list[ExtractedClaim] = []
        facts: list[NormalizedFact] = []

        identity_passage = json.dumps(
            {"identification": identification, "intervention": raw_intervention}, sort_keys=True
        )
        identity_claim = _claim(
            hit,
            document,
            predicate="identity_valid",
            value=True,
            passage=identity_passage,
            locator="identificationModule.nctId + armsInterventionsModule.interventions",
        )
        claims.append(identity_claim)
        facts.append(_fact(hit, identity_claim, "identity_valid", True))

        targets = sorted(candidate[0]) if candidate else sorted(_targets_in_text(json.dumps(protocol)))
        if targets:
            target_claim = _claim(
                hit,
                document,
                predicate="construct_target_set",
                value=targets,
                passage=intervention_passage,
                locator="armsInterventionsModule.interventions",
            )
            claims.append(target_claim)
            facts.append(_fact(hit, target_claim, "construct_target_set", targets))

        modality = candidate[1] if candidate else None
        if modality:
            modality_claim = _claim(
                hit,
                document,
                predicate="modality_id",
                value=modality,
                passage=intervention_passage,
                locator="armsInterventionsModule.interventions",
            )
            claims.append(modality_claim)
            facts.append(_fact(hit, modality_claim, "modality_id", modality))

        conditions = conditions_module.get("conditions", [])
        condition_text = " ".join(conditions).casefold()
        if conditions and any(term in condition_text for term in _ONCOLOGY_TERMS):
            ta_claim = _claim(
                hit,
                document,
                predicate="therapeutic_area",
                value="oncology",
                passage="; ".join(conditions),
                locator="conditionsModule.conditions",
            )
            claims.append(ta_claim)
            facts.append(_fact(hit, ta_claim, "therapeutic_area", "oncology"))
        if conditions:
            indication_claim = _claim(
                hit,
                document,
                predicate="indication",
                value=conditions[0],
                passage="; ".join(conditions),
                locator="conditionsModule.conditions",
            )
            claims.append(indication_claim)
            facts.append(_fact(hit, indication_claim, "indication", conditions[0]))

        phases = design.get("phases", [])
        stage_order = max((_STAGE_ORDER.get(phase, -1) for phase in phases), default=-1)
        if stage_order >= 0:
            stage_claim = _claim(
                hit,
                document,
                predicate="development_stage_order",
                value=stage_order,
                passage=json.dumps(phases),
                locator="designModule.phases",
            )
            claims.append(stage_claim)
            facts.append(_fact(hit, stage_claim, "development_stage_order", stage_order))

        status = status_module.get("overallStatus")
        last_update = status_module.get("lastUpdatePostDateStruct", {}).get("date")
        if status and last_update:
            status_claim = _claim(
                hit,
                document,
                predicate="development_status",
                value=status,
                passage=f"Overall status: {status}; last update: {last_update}",
                locator="statusModule",
            )
            claims.append(status_claim)
            try:
                effective_from = date.fromisoformat(last_update[:10])
            except ValueError:
                effective_from = hit.applicable_as_of_date
            facts.append(
                TemporalFact(
                    **_fact(hit, status_claim, "development_status", status).model_dump(),
                    effective_from=effective_from,
                    effective_to=None,
                    freshness_days=365,
                    evaluated_as_of=hit.applicable_as_of_date,
                    is_stale=(hit.applicable_as_of_date - effective_from).days > 365,
                )
            )
        clinical_results: list[ClinicalResult] = []
        # Registry outcome measures are useful evidence even when they do not contain a
        # normalized effect size.  Preserve the endpoint as a claim and emit an explicitly
        # incomplete result so downstream cohort/ranking logic abstains rather than guessing.
        for index, measure in enumerate(
            protocol.get("outcomesModule", {}).get("outcomeMeasures", [])
        ):
            endpoint = str(measure.get("title") or measure.get("measure") or "").strip()
            if not endpoint:
                continue
            outcome_passage = json.dumps(measure, sort_keys=True)
            endpoint_claim = _claim(
                hit,
                document,
                predicate="clinical_endpoint",
                value=endpoint,
                passage=outcome_passage,
                locator=f"outcomesModule.outcomeMeasures[{index}]",
            )
            claims.append(endpoint_claim)
            clinical_results.append(
                ClinicalResult(
                    result_id=_id("clinical_result", hit.hit_id, str(index), endpoint),
                    subject_id=hit.hit_id,
                    indication=str(conditions[0] if conditions else ""),
                    population="",
                    treatment_line="",
                    development_stage="|".join(phases),
                    endpoint=endpoint,
                    endpoint_family=endpoint,
                    incomplete_reporting=True,
                    supporting_claim_ids=[endpoint_claim.claim_id],
                )
            )
        return ExtractionBundle(claims=claims, facts=facts, clinical_results=clinical_results)
