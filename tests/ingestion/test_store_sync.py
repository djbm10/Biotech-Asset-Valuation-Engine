"""Tests for ingest-live → KnowledgeStore mirroring (store_sync).

Proves the production loop's final link: a classified EvidenceRecord becomes an
Event + StructuredSignal in the store, the score-context builder sees it, and the
weekly score gate then holds / publishes it. Persistence + mapping only — no
scoring/gating logic lives here.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from bve.entities.trial import TrialPhase
from bve.ingestion.evidence_ledger import EvidenceRecord
from bve.intelligence.actionable_output import ScoredCandidate
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.score_context_builder import build_score_contexts
from bve.intelligence.taxonomy import EventType
from bve.ingestion.store_sync import (
    persist_records,
    record_to_event,
    record_to_signal,
)
from bve.ops.weekly_runner import _apply_score_gate

_TODAY = dt.date(2026, 6, 20)
_MAP = {"AAA": ("asset-A", "co-a", "NSCLC")}


class _Gen:
    weights = {"ranking": 0.5, "thesis": 0.3, "opportunity": 0.2}


def _store(tmp_path) -> KnowledgeStore:
    return KnowledgeStore(Path(tmp_path) / "ops.db")


def _record(ticker="AAA", *, event_type="clinical_positive_ph3",
            direction="positive", phase="Phase 3", days_ago=3, ehash="h1") -> EvidenceRecord:
    return EvidenceRecord(
        ticker=ticker,
        event_date=(_TODAY - dt.timedelta(days=days_ago)).isoformat(),
        event_type=event_type,
        direction=direction,
        phase_detected=phase,
        source_type="press_release",
        source_url="https://example.com/pr",
        raw_text="Phase 3 met its primary endpoint (p=0.001).",
        confidence=0.9,
        match_reasons=["endpoint_met"],
        score_deltas={},
        summary="Ph3 primary endpoint met",
        event_hash=ehash,
    )


# ── Mapping ───────────────────────────────────────────────────────────────────────

class TestMapping:
    def test_positive_clinical_maps_to_endpoint_met_signal(self):
        rec = _record()
        ev = record_to_event(rec, asset_id="asset-A", company_id="co-a", indication_id="NSCLC")
        sig = record_to_signal(rec, ev, asset_id="asset-A", company_id="co-a")
        assert ev.event_type == EventType.TRIAL_READOUT
        assert ev.id == "evt-h1"
        assert sig.event_id == "evt-h1"
        assert sig.primary_endpoint_met is True
        assert sig.trial_phase == TrialPhase.PHASE_3

    def test_negative_clinical_maps_to_endpoint_missed(self):
        rec = _record(event_type="clinical_negative_ph3", direction="negative")
        ev = record_to_event(rec, asset_id="asset-A", company_id="co-a", indication_id=None)
        sig = record_to_signal(rec, ev, asset_id="asset-A", company_id="co-a")
        assert sig.primary_endpoint_met is False

    def test_fda_approval_maps_to_action_type(self):
        rec = _record(event_type="fda_approval", direction="positive", phase=None)
        ev = record_to_event(rec, asset_id="asset-A", company_id="co-a", indication_id=None)
        sig = record_to_signal(rec, ev, asset_id="asset-A", company_id="co-a")
        assert ev.event_type == EventType.FDA_APPROVAL
        assert sig.fda_action_type == "approval"


# ── Persistence ───────────────────────────────────────────────────────────────────

class TestPersist:
    def test_persists_event_and_signal(self, tmp_path):
        store = _store(tmp_path)
        n_ev, n_sig, n_skip = persist_records([_record()], store, _MAP)
        assert (n_ev, n_sig, n_skip) == (1, 1, 0)
        assert len(store.get_events(asset_id="asset-A")) == 1
        assert len(store.get_structured_signals(asset_id="asset-A")) == 1
        store.close()

    def test_unknown_ticker_skipped(self, tmp_path):
        store = _store(tmp_path)
        n_ev, n_sig, n_skip = persist_records([_record(ticker="ZZZ")], store, _MAP)
        assert (n_ev, n_sig, n_skip) == (0, 0, 1)
        store.close()

    def test_idempotent_rerun(self, tmp_path):
        store = _store(tmp_path)
        persist_records([_record()], store, _MAP)
        persist_records([_record()], store, _MAP)
        # Stable ids from event_hash → upsert, not duplicate.
        assert len(store.get_events(asset_id="asset-A")) == 1
        assert len(store.get_structured_signals(asset_id="asset-A")) == 1
        store.close()


# ── End-to-end production loop ─────────────────────────────────────────────────────

class TestProductionLoop:
    def test_ingest_to_gate_hold_to_approve_publishes(self, tmp_path):
        store = _store(tmp_path)
        # 1. Classified record mirrored into the store.
        persist_records([_record()], store, _MAP)

        # 2. Score-context builder sees the signal.
        cands = [ScoredCandidate(asset_id="asset-A", ticker="AAA", ranking_score=0.5,
                                 opportunity_score=0.5, thesis_strength=0.5)]
        ctxs = build_score_contexts(store, ["asset-A"], as_of=_TODAY)
        assert "asset-A" in ctxs

        # 3. Gate creates a score_update; a major clinical move is held at prior.
        pub1, _, pending1, _, held1 = _apply_score_gate(
            store, cands, ctxs, _Gen(), run_id="r1", as_of=_TODAY)
        assert held1 == 1
        assert pub1["AAA"] == 0.5
        assert any(i.ticker == "AAA" for i in pending1)

        # 4. bve-review-score approve.
        sid = store.get_score_updates(status="pending")[0].id
        store.resolve_score_update(sid, action="approve", reviewer="doug")

        # 5. Next gate run publishes the held score.
        ctxs2 = build_score_contexts(store, ["asset-A"], as_of=_TODAY)
        pub2, applied2, pending2, _, held2 = _apply_score_gate(
            store, cands, ctxs2, _Gen(), run_id="r2", as_of=_TODAY)
        assert pub2["AAA"] > 0.5
        assert pending2 == []
        assert held2 == 0
        store.close()
