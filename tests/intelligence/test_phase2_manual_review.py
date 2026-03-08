from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.phase2.manual_review import (
    ManualReviewStore,
    SourceDocumentMetadata,
    render_case,
)
from bve.intelligence.phase2.valuation_integration import (
    AssumptionFieldChange,
    ScenarioSnapshot,
    ValuationDiffLog,
)
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType

_NOW = datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc)


def _signal() -> StructuredSignal:
    return StructuredSignal(
        id="sig-1",
        event_id="evt-1",
        asset_id="asset-1",
        company_id="company-1",
        event_type=EventType.TRIAL_READOUT,
        signal_date=date(2026, 1, 10),
        extraction_confidence=0.91,
        extraction_model="test",
        created_at=_NOW,
    )


def _extraction_result() -> ExtractionResult:
    signal = _signal()
    return ExtractionResult(
        document_id="doc-1",
        asset_id=signal.asset_id,
        company_id=signal.company_id,
        source_url="https://example.org/doc-1",
        status=ExtractionStatus.SUCCESS,
        signal=signal,
        event_type_detected=signal.event_type.value,
        raw_llm_response='{"event_type":"trial_readout"}',
        raw_llm_json={"event_type": "trial_readout", "trial_phase": "phase_2"},
        ambiguity_flag=False,
        extraction_confidence=0.91,
        rationale="Phase 2 primary endpoint readout reported",
        extraction_model="test",
        prompt_version="v1.0",
        latency_ms=120,
        extracted_at=_NOW,
    )


def _proposal() -> AssumptionChangeProposal:
    return AssumptionChangeProposal(
        id="prop-1",
        signal_id="sig-1",
        asset_id="asset-1",
        engine_asset_id="asset-1",
        parameter_path="trials[*].success_probability",
        current_value=0.45,
        proposed_value=0.54,
        change_mode=ChangeMode.AUTO,
        bound_pct=20.0,
        event_type=EventType.TRIAL_READOUT,
        rationale="Positive readout supports higher POS",
        created_at=_NOW,
    )


def _diff() -> ValuationDiffLog:
    before = ScenarioSnapshot(
        rnpv_millions=100.0,
        nav_millions=500.0,
        nav_per_share=4.0,
        approval_probability=0.32,
        mc_mean_millions=95.0,
        bull_rnpv_millions=300.0,
        base_rnpv_millions=100.0,
        bear_rnpv_millions=-20.0,
    )
    after = ScenarioSnapshot(
        rnpv_millions=135.0,
        nav_millions=535.0,
        nav_per_share=4.3,
        approval_probability=0.38,
        mc_mean_millions=120.0,
        bull_rnpv_millions=360.0,
        base_rnpv_millions=135.0,
        bear_rnpv_millions=-10.0,
    )
    return ValuationDiffLog(
        run_id="run-1",
        asset_id="asset-1",
        event_id="evt-1",
        generated_at=_NOW,
        assumptions_changed=[
            AssumptionFieldChange(
                field="trials[phase_2].success_probability",
                old_value=0.45,
                new_value=0.54,
                delta=0.09,
                delta_pct=20.0,
            )
        ],
        valuation_before=before,
        valuation_after=after,
        delta_npv=35.0,
        delta_nav_per_share=0.3,
        delta_mc_mean_millions=25.0,
        delta_bull_rnpv_millions=60.0,
        delta_base_rnpv_millions=35.0,
        delta_bear_rnpv_millions=10.0,
        applied_overrides={"trials[phase_2].success_probability": 0.54},
    )


def _source_metadata() -> SourceDocumentMetadata:
    return SourceDocumentMetadata(
        document_id="doc-1",
        source="press_release",
        title="Company reports phase 2 topline",
        source_url="https://example.org/doc-1",
        published_at="2026-01-10T08:00:00Z",
        retrieved_at="2026-01-10T09:59:00Z",
    )


def test_manual_review_persistence_and_action_logging(tmp_path):
    store = ManualReviewStore(tmp_path / "reviews")
    case = store.create_case(
        case_id="case-1",
        source_document=_source_metadata(),
        extraction_result=_extraction_result(),
        proposal=_proposal(),
        valuation_diff=_diff(),
        created_at=_NOW,
    )

    loaded = store.load_case(case.id)
    assert loaded.id == "case-1"
    assert loaded.status == "pending"
    assert store.case_path("case-1").exists()

    action = store.record_action(
        case_id="case-1",
        action="modify",
        reviewer_id="analyst-1",
        rationale="Use smaller adjustment",
        override_value=0.50,
        provenance={"tool": "bve-review-phase2", "channel": "cli"},
        action_at=_NOW,
    )
    assert action.previous_status == "pending"
    assert action.next_status == "modified"

    updated = store.load_case("case-1")
    assert updated.status == "modified"
    assert updated.latest_override_value == 0.50
    assert len(updated.actions) == 1
    assert updated.actions[0].provenance["tool"] == "bve-review-phase2"

    lines = store.actions_log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["case_id"] == "case-1"
    assert payload["reviewer_id"] == "analyst-1"
    assert payload["action"] == "modify"


def test_status_transitions_enforced(tmp_path):
    store = ManualReviewStore(tmp_path / "reviews")
    store.create_case(
        case_id="case-2",
        source_document=_source_metadata(),
        extraction_result=_extraction_result(),
        proposal=_proposal(),
        valuation_diff=_diff(),
        created_at=_NOW,
    )

    store.record_action(
        case_id="case-2",
        action="modify",
        reviewer_id="analyst-1",
        rationale="Adjust value",
        override_value=0.51,
        action_at=_NOW,
    )
    store.record_action(
        case_id="case-2",
        action="approve",
        reviewer_id="analyst-1",
        rationale="Looks good",
        action_at=_NOW,
    )
    case = store.load_case("case-2")
    assert case.status == "approved"

    with pytest.raises(ValueError):
        store.record_action(
            case_id="case-2",
            action="reject",
            reviewer_id="analyst-2",
            rationale="Cannot reject after approval",
            action_at=_NOW,
        )


def test_modify_requires_override_value(tmp_path):
    store = ManualReviewStore(tmp_path / "reviews")
    store.create_case(
        case_id="case-3",
        source_document=_source_metadata(),
        extraction_result=_extraction_result(),
        proposal=_proposal(),
        valuation_diff=_diff(),
        created_at=_NOW,
    )
    with pytest.raises(ValueError):
        store.record_action(
            case_id="case-3",
            action="modify",
            reviewer_id="analyst-1",
            rationale="Missing override",
            action_at=_NOW,
        )


def test_render_case_contains_required_review_fields(tmp_path):
    store = ManualReviewStore(tmp_path / "reviews")
    store.create_case(
        case_id="case-4",
        source_document=_source_metadata(),
        extraction_result=_extraction_result(),
        proposal=_proposal(),
        valuation_diff=_diff(),
        created_at=_NOW,
    )
    case = store.load_case("case-4")
    rendered = render_case(case)

    assert "Source Document Metadata" in rendered
    assert "Extracted Event JSON" in rendered
    assert "Mapping Proposal" in rendered
    assert "Valuation Before/After Diff" in rendered
    assert "confidence_score" in rendered
    assert "ambiguity_flag" in rendered
    assert "rationale" in rendered
    assert "Reviewer Actions" in rendered
