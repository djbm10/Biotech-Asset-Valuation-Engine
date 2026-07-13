from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from bve.se.discovery.orchestrator import AdapterResult
from bve.se.discovery.adapters import ClinicalTrialsGovAdapter
from bve.se.pipeline import run_landscape_search
from bve.se.schemas.contracts import BuyerProblemV2, CandidateHit, RunStatus, SearchOutcome


ROOT = Path(__file__).resolve().parents[2]


class FixtureAdapter:
    source_name = "fixture"
    mandatory = True

    def search(self, query, *, as_of_date):
        return AdapterResult(
            hits=[
                CandidateHit(
                    hit_id="hit:1",
                    source="fixture",
                    source_document_id="doc:1",
                    query=query.query,
                    asset_name="Asset A",
                    company_name="Example Bio",
                    trial_id="NCT00000001",
                    target_terms=query.target_ids,
                    modality_terms=query.modality_ids,
                    provisional_identity_key="example bio|asset a",
                    retrieved_at=datetime.now(timezone.utc),
                    applicable_as_of_date=as_of_date,
                )
            ],
            outcome=SearchOutcome.SUCCESS,
        )


def test_pipeline_keeps_discovery_only_candidates_unresolved() -> None:
    problem = BuyerProblemV2.model_validate(
        yaml.safe_load(
            (ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml").read_text()
        )
    )
    result = run_landscape_search(
        problem,
        [FixtureAdapter()],
        run_id="run:pipeline",
        code_version="test",
        normalization_version="test",
        declared_mandatory_sources=["fixture"],
    )
    assert result.run_manifest.status == RunStatus.CONVERGED
    assert len(result.candidates) == 1
    assert result.eligible_asset_ids == []
    assert result.unresolved_asset_ids == [result.candidates[0].asset_id]
    assert result.review_queue


def test_missing_declared_source_forces_incomplete() -> None:
    problem = BuyerProblemV2.model_validate(
        yaml.safe_load(
            (ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml").read_text()
        )
    )
    result = run_landscape_search(
        problem,
        [FixtureAdapter()],
        run_id="run:missing",
        code_version="test",
        normalization_version="test",
        declared_mandatory_sources=["fixture", "conference_ash"],
    )
    assert result.run_manifest.status == RunStatus.INCOMPLETE
    assert "conference_ash" in " ".join(result.run_manifest.incomplete_reasons)


def test_ctgov_pipeline_emits_claims_facts_gates_and_review_queue(tmp_path) -> None:
    protocol = {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Asset A CD19 BiTE"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {
            "overallStatus": "RECRUITING",
            "lastUpdatePostDateStruct": {"date": "2026-01-01"},
        },
        "designModule": {"phases": ["PHASE1"]},
        "conditionsModule": {"conditions": ["B-cell acute lymphoblastic leukemia"]},
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
    adapter = ClinicalTrialsGovAdapter(
        lambda **_: [protocol], snapshot_root=tmp_path / "snapshots"
    )
    problem = BuyerProblemV2.model_validate(
        yaml.safe_load(
            (ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml").read_text()
        )
    )
    result = run_landscape_search(
        problem,
        [adapter],
        run_id="run:ctgov",
        code_version="test",
        normalization_version="test",
        declared_mandatory_sources=["clinicaltrials_gov"],
    )
    assert result.source_documents
    assert result.claims
    assert result.facts
    assert len(result.gate_evaluations) == 1
    assert result.unresolved_asset_ids == [result.candidates[0].asset_id]
    assert result.review_queue
    assert all(claim.source_document_id in {doc.document_id for doc in result.source_documents} for claim in result.claims)
