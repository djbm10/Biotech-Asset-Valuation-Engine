from __future__ import annotations

from datetime import date

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter
from bve.se.evidence.clinicaltrials import ClinicalTrialsEvidenceExtractor
from bve.se.evidence.ledger import EvidenceLedger
from bve.se.gates.engine import GateEngine
from bve.se.schemas.contracts import BuyerProblemV2, CompiledQuery, OverallDisposition


def _protocol() -> dict:
    return {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Asset A CD19 BiTE"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {
            "overallStatus": "RECRUITING",
            "lastUpdatePostDateStruct": {"date": "2026-01-01"},
        },
        "designModule": {"phases": ["PHASE1"]},
        "conditionsModule": {"conditions": ["B-cell acute lymphoblastic leukemia"]},
        "outcomesModule": {
            "outcomeMeasures": [
                {"title": "Objective response rate", "timeFrame": "12 weeks"}
            ]
        },
        "armsInterventionsModule": {
            "interventions": [
                {
                    "name": "Asset A",
                    "type": "DRUG",
                    "description": "bispecific CD19-directed CD3 T-cell engager",
                }
            ]
        },
    }


def test_ctgov_snapshot_extracts_cited_gate_facts(tmp_path, se_ontology_snapshot) -> None:
    adapter = ClinicalTrialsGovAdapter(
        lambda **_: [_protocol()], snapshot_root=tmp_path / "snapshots"
    )
    discovery = adapter.search(
        CompiledQuery(
            query_id="q",
            query="CD19 T-cell engager",
            target_ids=["CD19"],
            modality_ids=["T_CELL_ENGAGER"],
        ),
        as_of_date=date(2026, 7, 10),
    )
    hit = discovery.hits[0]
    document = discovery.source_documents[0]
    ledger = EvidenceLedger()
    ledger.register_document(document)
    bundle = ClinicalTrialsEvidenceExtractor().extract(hit, document)
    for claim in bundle.claims:
        ledger.add_claim(claim)
    for fact in bundle.facts:
        ledger.add_fact(fact)

    assert {fact.fact_type for fact in bundle.facts} >= {
        "identity_valid",
        "construct_target_set",
        "modality_id",
        "therapeutic_area",
        "development_stage_order",
        "development_status",
    }
    assert all(ledger.reconstruct_fact_evidence(fact.fact_id) for fact in bundle.facts)
    assert len(bundle.clinical_results) == 1
    assert bundle.clinical_results[0].endpoint == "Objective response rate"
    assert bundle.clinical_results[0].incomplete_reporting is True


def test_registry_evidence_does_not_invent_human_poc_or_deal_access(tmp_path) -> None:
    adapter = ClinicalTrialsGovAdapter(
        lambda **_: [_protocol()], snapshot_root=tmp_path / "snapshots"
    )
    discovery = adapter.search(
        CompiledQuery(
            query_id="q",
            query="CD19 T-cell engager",
            target_ids=["CD19"],
            modality_ids=["T_CELL_ENGAGER"],
        ),
        as_of_date=date(2026, 7, 10),
    )
    bundle = ClinicalTrialsEvidenceExtractor().extract(
        discovery.hits[0], discovery.source_documents[0]
    )
    problem = BuyerProblemV2.model_validate(
        {
            "problem_id": "p",
            "version": "1",
            "buyer": {
                "buyer_id": "b",
                "name": "Buyer",
                "as_of_date": "2026-07-10",
            },
            "strategic_gap": {
                "therapeutic_areas": ["oncology"],
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": "CD19", "label": "CD19"}],
                },
                "modalities": ["T_CELL_ENGAGER"],
                "evidence_floor": {"minimum_stage": "PHASE_1", "human_poc_required": True},
                "acceptable_deal_routes": ["LICENSE"],
            },
        }
    )
    evaluation = GateEngine().evaluate(problem, subject_id=discovery.hits[0].hit_id, facts=bundle.facts)
    assert evaluation.disposition == OverallDisposition.UNRESOLVED
    unresolved = {item.requirement_id for item in evaluation.review_items}
    assert "evidence.human_poc" in unresolved
    assert "access.acceptable_route_exists" in unresolved
