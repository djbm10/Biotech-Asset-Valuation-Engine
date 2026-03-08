from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from bve.entities.trial import TrialPhase
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.knowledge_layer import (
    KnowledgeStore,
    MemoRecord,
    SourceTrace,
    StoredValuationDiff,
)
from bve.intelligence.phase2.valuation_integration import (
    AssumptionFieldChange,
    ScenarioSnapshot,
    ValuationDiffLog,
)
from bve.intelligence.schemas.runs import ReviewDecision
from bve.intelligence.schemas.signals import Event, StructuredSignal
from bve.intelligence.taxonomy import EventType

_T0 = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc)
_T2 = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)


def _trace(ref: str) -> SourceTrace:
    return SourceTrace(
        source_type="unit_test",
        source_ref=ref,
        ingested_at=_T2,
    )


def _event(
    event_id: str,
    *,
    event_type: EventType,
    company_id: str = "company-1",
    asset_id: str = "asset-1",
    observed_at: datetime = _T1,
) -> Event:
    return Event(
        id=event_id,
        event_type=event_type,
        asset_id=asset_id,
        company_id=company_id,
        observed_at=observed_at,
        ingested_at=_T2,
        source_type="press_release",
        source_url=f"https://example.org/{event_id}",
        headline=f"{event_type.value} headline",
        confidence=0.92,
    )


def _signal(signal_id: str, event_id: str, event_type: EventType = EventType.TRIAL_READOUT) -> StructuredSignal:
    return StructuredSignal(
        id=signal_id,
        event_id=event_id,
        asset_id="asset-1",
        company_id="company-1",
        event_type=event_type,
        signal_date=date(2026, 2, 10),
        trial_phase=TrialPhase.PHASE_2,
        extraction_confidence=0.92,
        extraction_model="unit-test",
        created_at=_T1,
    )


def _raw_document(doc_id: str) -> RawDocument:
    return RawDocument.from_text(
        id=doc_id,
        source="press_release",
        title="Phase 2 topline update",
        raw_text="Company announced positive phase 2 topline results.",
        source_url=f"https://example.org/{doc_id}",
        retrieved_at=_T0,
        entity_hints=EntityHints(
            asset_id="asset-1",
            company_id="company-1",
            drug_name="Drug X",
            indication="Indication Y",
        ),
    )


def _extraction_result(doc_id: str, signal: StructuredSignal) -> ExtractionResult:
    return ExtractionResult(
        document_id=doc_id,
        asset_id=signal.asset_id,
        company_id=signal.company_id,
        source_url=f"https://example.org/{doc_id}",
        status=ExtractionStatus.SUCCESS,
        signal=signal,
        event_type_detected=signal.event_type.value,
        raw_llm_response='{"event_type":"trial_readout"}',
        raw_llm_json={"event_type": "trial_readout", "trial_phase": "phase_2"},
        ambiguity_flag=False,
        extraction_confidence=0.92,
        rationale="Signal extracted successfully",
        extraction_model="unit-test",
        prompt_version="v1.0",
        latency_ms=120,
        extracted_at=_T1,
    )


def _snapshot(rnpv: float, nav_ps: float) -> ScenarioSnapshot:
    return ScenarioSnapshot(
        rnpv_millions=rnpv,
        nav_millions=rnpv + 300.0,
        nav_per_share=nav_ps,
        approval_probability=0.35,
        mc_mean_millions=rnpv - 5.0,
        bull_rnpv_millions=rnpv + 120.0,
        base_rnpv_millions=rnpv,
        bear_rnpv_millions=rnpv - 70.0,
    )


def _diff(run_id: str, event_id: str, generated_at: datetime, delta_npv: float) -> ValuationDiffLog:
    before = _snapshot(100.0, 4.0)
    after = _snapshot(100.0 + delta_npv, 4.0 + (delta_npv / 100.0))
    return ValuationDiffLog(
        run_id=run_id,
        asset_id="asset-1",
        event_id=event_id,
        generated_at=generated_at,
        assumptions_changed=[
            AssumptionFieldChange(
                field="trials[phase_2].success_probability",
                old_value=0.45,
                new_value=0.50,
                delta=0.05,
                delta_pct=11.111111,
            )
        ],
        valuation_before=before,
        valuation_after=after,
        delta_npv=delta_npv,
        delta_nav_per_share=after.nav_per_share - before.nav_per_share,
        delta_mc_mean_millions=after.mc_mean_millions - before.mc_mean_millions,
        delta_bull_rnpv_millions=after.bull_rnpv_millions - before.bull_rnpv_millions,
        delta_base_rnpv_millions=after.base_rnpv_millions - before.base_rnpv_millions,
        delta_bear_rnpv_millions=after.bear_rnpv_millions - before.bear_rnpv_millions,
        applied_overrides={"trials[phase_2].success_probability": 0.50},
    )


def _decision(decision_id: str, run_id: str, verdict: str, reviewed_at: datetime) -> ReviewDecision:
    return ReviewDecision(
        id=decision_id,
        proposal_id=f"proposal-{decision_id}",
        run_id=run_id,
        decision=verdict,
        reviewer_id="analyst-1",
        reviewed_at=reviewed_at,
        rationale=f"{verdict} rationale",
    )


def test_stored_valuation_diff_round_trip(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    event = _event("evt-1", event_type=EventType.TRIAL_READOUT)
    store.add_event(event, _trace("event"))

    stored = StoredValuationDiff(
        run_id="run-1",
        event_id=event.id,
        asset_id=event.asset_id,
        valuation_before={"rnpv_millions": 100.0, "nav_per_share": 4.0},
        valuation_after={"rnpv_millions": 125.0, "nav_per_share": 4.25},
        delta_npv=25.0,
        created_at=_T2,
        valuation_delta={"delta_npv": 25.0, "delta_nav_per_share": 0.25},
    )
    store.add_valuation_diff(stored, company_id=event.company_id, source_trace=_trace("diff"))

    loaded = store.get_valuation_diffs(company_id=event.company_id)
    assert [d.run_id for d in loaded] == [stored.run_id]
    assert loaded[0].valuation_before["rnpv_millions"] == 100.0
    assert loaded[0].valuation_after["rnpv_millions"] == 125.0
    assert loaded[0].delta_npv == 25.0
    store.close()


def test_conversion_from_phase2_diff_to_stored_diff(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    event = _event("evt-1", event_type=EventType.TRIAL_READOUT)
    store.add_event(event, _trace("event"))

    phase2_diff = _diff("run-1", event.id, _T2, 30.0)
    stored = store.add_valuation_diff(
        phase2_diff,
        company_id=event.company_id,
        source_trace=_trace("diff"),
    )

    assert isinstance(stored, StoredValuationDiff)
    assert stored.run_id == "run-1"
    assert stored.event_id == event.id
    assert stored.valuation_before["rnpv_millions"] == 100.0
    assert stored.valuation_after["rnpv_millions"] == 130.0

    loaded = store.get_valuation_diffs(company_id=event.company_id)
    assert loaded[0].run_id == "run-1"
    assert loaded[0].delta_npv == 30.0
    store.close()


def test_full_provenance_chain_reconstruction(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")

    event = _event("evt-1", event_type=EventType.TRIAL_READOUT)
    signal = _signal("sig-1", event.id)
    raw_doc = _raw_document("doc-1")
    extraction = _extraction_result(raw_doc.id, signal)
    diff = _diff("run-1", event.id, _T2, 35.0)

    store.add_raw_document(raw_doc, _trace("raw-document"))
    extraction_record = store.add_extraction_result(extraction, _trace("extraction"))
    store.add_structured_signal(
        signal,
        _trace("structured-signal"),
        extraction_result_id=extraction_record.id,
    )
    store.add_event(event, _trace("event"), signal_id=signal.id)
    store.add_valuation_diff(diff, company_id=event.company_id, source_trace=_trace("diff"))
    store.add_review_decision(
        _decision("dec-1", diff.run_id, "accepted", _T2),
        company_id=event.company_id,
        asset_id=event.asset_id,
        source_trace=_trace("review"),
    )
    memo = MemoRecord(
        id="memo-1",
        company_id=event.company_id,
        asset_id=event.asset_id,
        title="Analyst memo",
        memo_type="analyst_memo",
        content_markdown="Short note",
        created_at=_T2,
        source_signal_ids=[signal.id],
        source_run_ids=[diff.run_id],
        source_trace=_trace("memo"),
    )
    store.add_memo(memo)

    record = store.get_record_with_trace("valuation_diffs", diff.run_id)
    chain = record.provenance_chain

    assert chain["source_url"] == raw_doc.source_url
    assert chain["raw_document"]["record_id"] == raw_doc.id
    assert chain["extraction_result"]["record_id"] == extraction_record.id
    assert chain["structured_signal"]["record_id"] == signal.id
    assert chain["event"]["record_id"] == event.id
    assert chain["valuation_diff"]["record_id"] == diff.run_id
    assert [row["record_id"] for row in chain["review_decisions"]] == ["dec-1"]
    assert [row["record_id"] for row in chain["memos"]] == ["memo-1"]
    store.close()


def test_retrieval_by_company_asset_event_type_and_date(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    event_a = _event(
        "evt-a",
        event_type=EventType.TRIAL_READOUT,
        company_id="company-a",
        asset_id="asset-a",
        observed_at=_T0,
    )
    event_b = _event(
        "evt-b",
        event_type=EventType.FINANCING,
        company_id="company-b",
        asset_id="asset-b",
        observed_at=_T2,
    )
    store.add_event(event_a, _trace("event-a"))
    store.add_event(event_b, _trace("event-b"))

    signal_a = _signal("sig-a", event_a.id, EventType.TRIAL_READOUT)
    signal_b = _signal("sig-b", event_b.id, EventType.FINANCING)
    store.add_structured_signal(
        signal_a,
        _trace("sig-a"),
        extraction_result_id="extract-a",
    )
    store.add_structured_signal(
        signal_b,
        _trace("sig-b"),
        extraction_result_id="extract-b",
    )

    by_company = store.get_events(company_id="company-a")
    assert [e.id for e in by_company] == ["evt-a"]

    by_asset = store.get_events(asset_id="asset-b")
    assert [e.id for e in by_asset] == ["evt-b"]

    by_type = store.get_events(event_type=EventType.TRIAL_READOUT)
    assert [e.id for e in by_type] == ["evt-a"]

    by_date = store.get_events(date_from=date(2026, 2, 15), date_to=date(2026, 2, 28))
    assert [e.id for e in by_date] == ["evt-b"]

    signals_by_type = store.get_structured_signals(event_type=EventType.TRIAL_READOUT)
    assert [s.id for s in signals_by_type] == ["sig-a"]
    store.close()


def test_dossier_generation_contains_required_sections(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    event = _event("evt-1", event_type=EventType.TRIAL_READOUT, observed_at=_T1)
    store.add_event(event, _trace("event"))

    diff = _diff("run-1", event.id, _T2, 35.0)
    store.add_valuation_diff(
        diff,
        company_id="company-1",
        source_trace=_trace("diff"),
        assumptions_snapshot={
            "trials[phase_2].success_probability": 0.50,
            "trials[phase_3].success_probability": 0.72,
        },
        valuation_snapshot={"rnpv_millions": 135.0, "nav_per_share": 4.35},
    )
    store.add_review_decision(
        ReviewDecision(
            id="dec-deferred",
            proposal_id="prop-1",
            run_id=None,
            decision="deferred",
            reviewer_id="analyst-2",
            reviewed_at=_T2,
            rationale="Need competitor readout context",
        ),
        company_id="company-1",
        asset_id="asset-1",
        source_trace=_trace("review"),
    )
    store.add_memo(
        MemoRecord(
            id="memo-1",
            company_id="company-1",
            asset_id="asset-1",
            title="Open items",
            memo_type="analyst_memo",
            content_markdown="Tracking follow-ups",
            created_at=_T2,
            open_questions=["Need updated comparator hazard ratio"],
            source_trace=_trace("memo"),
        )
    )

    dossier = store.generate_dossier(company_id="company-1", asset_id="asset-1", persist=True)

    assert dossier.company_id == "company-1"
    assert dossier.asset_id == "asset-1"
    assert [event.id for event in dossier.recent_events] == ["evt-1"]
    assert dossier.current_assumptions["trials[phase_2].success_probability"] == 0.50
    assert dossier.latest_valuation_snapshot["rnpv_millions"] == 135.0
    assert [change.run_id for change in dossier.recent_changes] == ["run-1"]
    assert any("Deferred review dec-deferred" in q for q in dossier.open_questions)
    assert "Need updated comparator hazard ratio" in dossier.open_questions
    assert [d.id for d in store.get_dossiers(company_id="company-1", asset_id="asset-1")] == [dossier.id]
    store.close()
