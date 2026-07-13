from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from bve.cli.replay_document import _extract_science_evidence_output
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.science_evidence import (
    ScienceEvidenceBundle,
    ScienceEvidenceDirection,
    ScienceEvidenceItem,
    ScienceEvidenceMappedComponent,
    ScienceEvidenceMappedField,
    ScienceEvidenceSourceType,
)
from bve.intelligence.science_evidence_artifact import (
    build_science_evidence_artifact,
    compute_document_hash,
    load_science_evidence_artifact,
    save_science_evidence_artifact,
)


class _Client:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def generate(self, prompt: str, **kwargs) -> str:
        self.calls += 1
        return json.dumps(self.payload)


def _item(component: ScienceEvidenceMappedComponent = ScienceEvidenceMappedComponent.T):
    return ScienceEvidenceItem(
        evidence_id="ev-1",
        asset_id="asset-1",
        source_type=ScienceEvidenceSourceType.PRESS_RELEASE,
        source_id="doc-1",
        source_uri="https://example.com/doc-1",
        quote="The target pathway was causally linked to disease activity.",
        mapped_component=component,
        mapped_field=ScienceEvidenceMappedField.TARGET_PATHWAY,
        direction=ScienceEvidenceDirection.SUPPORTIVE,
        confidence=0.82,
        extraction_method="unit_test",
    )


def _bundle() -> ScienceEvidenceBundle:
    return ScienceEvidenceBundle(
        asset_id="asset-1",
        asset_name="Asset 1",
        indication="UC",
        phase="phase2",
        modality="small_molecule",
        target="JAK1",
        mechanism="JAK1 inhibition",
        items=[_item()],
        bundle_warnings=["ambiguous_low_context_item"],
        unresolved_gaps=["human PK/PD exposure-response evidence"],
    )


def _doc() -> RawDocument:
    return RawDocument(
        id="doc-1",
        source="press_release",
        source_url="https://example.com/doc-1",
        title="Clinical update",
        raw_text="The target pathway was causally linked to disease activity.",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        entity_hints=EntityHints(
            asset_id="asset-1",
            company_id="company-1",
            drug_name="Asset 1",
            indication="UC",
        ),
        document_hash="a" * 64,
    )


def _llm_payload() -> dict:
    return {
        "asset_id": "asset-1",
        "asset_name": "Asset 1",
        "indication": "UC",
        "phase": "phase2",
        "modality": "small_molecule",
        "target": "JAK1",
        "mechanism": "JAK1 inhibition",
        "items": [_item().model_dump(mode="json")],
        "bundle_warnings": [],
        "unresolved_gaps": ["human PK/PD exposure-response evidence"],
    }


def test_artifact_round_trips_with_identity_versions_and_hash(tmp_path) -> None:
    artifact = build_science_evidence_artifact(
        _bundle(),
        document_text="source text",
        source_document_id="doc-1",
        asset_id="asset-1",
        model_id="mock-model",
    )

    assert artifact.schema_version.startswith("science_evidence_artifact")
    assert artifact.extractor_version
    assert artifact.prompt_version
    assert artifact.model_id == "mock-model"
    assert artifact.document_hash == compute_document_hash("source text")
    assert artifact.source_document_id == "doc-1"
    assert artifact.asset_id == "asset-1"

    path = save_science_evidence_artifact(artifact, tmp_path / "artifact.json")
    loaded = load_science_evidence_artifact(path, current_document_text="source text")

    assert loaded.bundle.asset_id == "asset-1"
    assert loaded.bundle.items[0].evidence_id == "ev-1"
    assert loaded.artifact_warnings == []


def test_artifact_hash_mismatch_warns_or_fails(tmp_path) -> None:
    path = save_science_evidence_artifact(
        build_science_evidence_artifact(
            _bundle(),
            document_text="original text",
            source_document_id="doc-1",
            asset_id="asset-1",
        ),
        tmp_path / "artifact.json",
    )

    warned = load_science_evidence_artifact(path, current_document_text="changed text")
    assert "science_evidence_artifact_document_hash_mismatch" in warned.artifact_warnings

    with pytest.raises(ValueError, match="document_hash_mismatch"):
        load_science_evidence_artifact(
            path,
            current_document_text="changed text",
            mismatch_policy="fail",
        )


def test_replay_helper_writes_artifact_and_compact_surface(tmp_path) -> None:
    client = _Client(_llm_payload())

    output = _extract_science_evidence_output(
        _doc(),
        client,
        artifact_output_dir=tmp_path,
        model_id="mock-model",
    )

    assert client.calls == 1
    assert output["science_evidence_artifact_path"]
    assert (tmp_path / "asset-1" / "doc-1.science_evidence.json").exists()
    assert output["science_evidence_surface"]["evidence_counts_by_component"] == {"T": 1}
    assert len(output["science_evidence_surface"]["top_snippets"]) == 1
    assert output["science_evidence_surface"]["unresolved_gaps"] == [
        "human PK/PD exposure-response evidence"
    ]


def test_replay_helper_loads_artifact_without_llm_call(tmp_path) -> None:
    artifact_path = save_science_evidence_artifact(
        build_science_evidence_artifact(
            _bundle(),
            document_text=_doc().raw_text,
            source_document_id="doc-1",
            asset_id="asset-1",
        ),
        tmp_path / "artifact.json",
    )
    client = _Client(_llm_payload())

    output = _extract_science_evidence_output(
        _doc(),
        client,
        artifact_path=artifact_path,
    )

    assert client.calls == 0
    assert output["science_evidence_artifact_path"] == str(artifact_path)
    assert output["science_evidence_bundle"]["asset_id"] == "asset-1"
