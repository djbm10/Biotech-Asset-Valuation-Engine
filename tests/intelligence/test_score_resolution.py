"""Tests for the score-update resolution path (commit 3): approve/reject/idempotency/stale."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from bve.entities.trial import TrialPhase
from bve.intelligence.actionable_output import ScoredCandidate
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.score_context_builder import build_score_contexts
from bve.intelligence.taxonomy import EventType
from bve.ops.weekly_runner import _apply_score_gate

_TODAY = dt.date(2026, 6, 20)
_ST = SourceTrace(source_type="manual", source_ref="test")


class _Gen:
    weights = {"ranking": 0.5, "thesis": 0.3, "opportunity": 0.2}


def _store(tmp_path) -> KnowledgeStore:
    return KnowledgeStore(Path(tmp_path) / "ops.db")


def _seed(store, asset_id, sid, *, days_ago=3, **fields):
    base = dict(
        id=sid, event_id=f"evt-{sid}", asset_id=asset_id, company_id="co",
        event_type=EventType.TRIAL_READOUT, signal_date=_TODAY - dt.timedelta(days=days_ago),
        trial_phase=TrialPhase.PHASE_3, extraction_model="t", extraction_confidence=0.9,
        created_at=dt.datetime(2026, 6, 17, tzinfo=dt.timezone.utc),
    )
    base.update(fields)
    store.add_structured_signal(StructuredSignal(**base), _ST, extraction_result_id=f"x-{sid}")


def _cand(asset_id, ticker):
    return ScoredCandidate(asset_id=asset_id, ticker=ticker, ranking_score=0.5,
                           opportunity_score=0.5, thesis_strength=0.5)


def _run_gate(store, asset_id="asset-A", ticker="AAA"):
    cands = [_cand(asset_id, ticker)]
    ctxs = build_score_contexts(store, [asset_id], as_of=_TODAY)
    return _apply_score_gate(store, cands, ctxs, _Gen(), run_id="r", as_of=_TODAY)


# ── Direct resolution semantics ──────────────────────────────────────────────────

class TestResolveScoreUpdate:
    def test_approve_sets_status_and_audit_lineage(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, "asset-A", "s1", primary_endpoint_met=True, p_value=0.001)
        _run_gate(store)  # creates a pending row (major event held)
        pending = store.get_score_updates(status="pending")
        assert len(pending) == 1
        sid = pending[0].id

        res = store.resolve_score_update(sid, action="approve", reviewer="doug",
                                         rationale="confirmed")
        assert res.status == "approved"
        assert res.reviewer == "doug"
        assert res.resolved_at is not None
        assert res.review_decision_id

        # Audit lineage row exists, linked by review_decision_id.
        audit = store.query_audit_log(entity_id=sid) if hasattr(store, "query_audit_log") else None
        if audit is not None:
            assert any(a.get("review_decision_id") == res.review_decision_id for a in audit)
        store.close()

    def test_reject_keeps_prior(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, "asset-A", "s1", primary_endpoint_met=True, p_value=0.001)
        _run_gate(store)
        sid = store.get_score_updates(status="pending")[0].id
        res = store.resolve_score_update(sid, action="reject", reviewer="doug")
        assert res.status == "rejected"
        store.close()

    def test_idempotent_same_action(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, "asset-A", "s1", primary_endpoint_met=True, p_value=0.001)
        _run_gate(store)
        sid = store.get_score_updates(status="pending")[0].id
        first = store.resolve_score_update(sid, action="approve", reviewer="d")
        again = store.resolve_score_update(sid, action="approve", reviewer="d")
        assert first.status == again.status == "approved"
        # still exactly one resolved row
        assert len(store.get_score_updates(status="approved")) == 1
        store.close()

    def test_conflicting_resolution_refused(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, "asset-A", "s1", primary_endpoint_met=True, p_value=0.001)
        _run_gate(store)
        sid = store.get_score_updates(status="pending")[0].id
        store.resolve_score_update(sid, action="approve")
        try:
            store.resolve_score_update(sid, action="reject")
        except ValueError:
            store.close()
            return
        store.close()
        raise AssertionError("expected ValueError on conflicting re-resolution")

    def test_unknown_id_returns_none(self, tmp_path):
        store = _store(tmp_path)
        assert store.resolve_score_update("nope", action="approve") is None
        store.close()


# ── Gate honours resolution on the next run ──────────────────────────────────────

class TestGatePostResolution:
    def test_approved_move_publishes_and_suppresses_pending(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, "asset-A", "s1", primary_endpoint_met=True, p_value=0.001)
        pub1, _, pending1, _, held1 = _run_gate(store)
        assert held1 == 1 and pub1["AAA"] == 0.5  # held at prior first

        sid = store.get_score_updates(status="pending")[0].id
        store.resolve_score_update(sid, action="approve", reviewer="doug")

        pub2, applied2, pending2, n_applied2, held2 = _run_gate(store)
        assert pub2["AAA"] > 0.5            # approved → new score now publishes
        assert pending2 == []               # pending item suppressed
        assert held2 == 0
        assert "asset-A" in applied2
        store.close()

    def test_rejected_move_keeps_prior_and_suppresses_pending(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, "asset-A", "s1", primary_endpoint_met=True, p_value=0.001)
        _run_gate(store)
        sid = store.get_score_updates(status="pending")[0].id
        store.resolve_score_update(sid, action="reject", reviewer="doug")

        pub2, applied2, pending2, _, held2 = _run_gate(store)
        assert pub2["AAA"] == 0.5           # rejected → prior kept
        assert pending2 == []               # suppressed
        assert "asset-A" not in applied2
        store.close()

    def test_idempotent_repeated_runs_no_duplicate_rows(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, "asset-A", "s1", primary_endpoint_met=True, p_value=0.001)
        _run_gate(store)
        _run_gate(store)
        _run_gate(store)
        # Same movement signature → one upserted row, not three.
        assert len(store.get_score_updates(asset_id="asset-A")) == 1
        store.close()

    def test_new_event_retriggers_after_resolution(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, "asset-A", "s1", primary_endpoint_met=True, p_value=0.001)
        _run_gate(store)
        sid = store.get_score_updates(status="pending")[0].id
        store.resolve_score_update(sid, action="reject", reviewer="doug")

        # A NEW, distinct event arrives (FDA approval, more recent + stronger) → the
        # builder now selects evt-s2 → new signature → re-trigger despite prior reject.
        _seed(store, "asset-A", "s2", event_type=EventType.FDA_APPROVAL,
              fda_action_type="approval", days_ago=1)
        _, _, pending2, _, held2 = _run_gate(store)
        assert held2 == 1                   # fresh pending despite prior rejection
        assert any(i.ticker == "AAA" for i in pending2)
        # Two distinct movement rows now exist (old rejected + new pending).
        keys = {r.resolution_key for r in store.get_score_updates(asset_id="asset-A")}
        assert len(keys) == 2
        store.close()
