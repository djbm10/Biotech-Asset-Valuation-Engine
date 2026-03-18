"""
Wave 4A — Tests for the Streamlit Review Queue helper logic.

Exercises:
  - _pending_diffs: returns diffs that have no review_decision
  - _reviewed_diffs: returns diffs that have a review_decision
  - _signal_for_event: fetches structured_signal payload by event_id
  - _submit_decision: writes ReviewDecision and audit log entry
  - Decision persistence: round-trips through add_review_decision → get_review_decisions
  - Post-decision: diff moves from pending → reviewed
  - Confidence badge helper
  - Tags and supporting_quote round-trip
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

pytest.importorskip("streamlit")

from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace


# ---------------------------------------------------------------------------
# Helpers for seeding test data
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_diff(
    store: KnowledgeStore,
    *,
    run_id: str | None = None,
    asset_id: str = "asset-001",
    event_id: str | None = None,
    delta_npv: float = 50.0,
) -> str:
    run_id = run_id or str(uuid.uuid4())
    event_id = event_id or str(uuid.uuid4())
    payload = {
        "run_id": run_id,
        "event_id": event_id,
        "asset_id": asset_id,
        "valuation_before": {"rnpv_millions": 100.0},
        "valuation_after":  {"rnpv_millions": 150.0},
        "delta_npv": delta_npv,
        "created_at": _now_iso(),
        "valuation_delta": {"npv_delta_pct": 50.0},
        "assumptions_changed": [
            {
                "parameter_path": "trials[nda].success_probability",
                "before": 0.50,
                "after": 0.65,
                "delta_pct": 30.0,
                "rationale": "Positive Ph3 readout",
            }
        ],
        "applied_overrides": {},
        "market_cap_snapshot_millions": 800.0,
    }
    store._conn.execute(
        """
        INSERT INTO valuation_diffs
            (run_id, asset_id, event_id, delta_npv, created_at, payload_json, source_trace_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            asset_id,
            event_id,
            delta_npv,
            _now_iso(),
            json.dumps(payload),
            json.dumps({"source_type": "test", "source_ref": "test"}),
        ),
    )
    store._conn.commit()
    return run_id


def _insert_signal(
    store: KnowledgeStore,
    event_id: str,
    *,
    asset_id: str = "asset-001",
    company_id: str = "co-001",
    event_type: str = "trial_readout",
    extraction_confidence: float = 0.85,
) -> str:
    signal_id = str(uuid.uuid4())
    payload = {
        "id": signal_id,
        "event_id": event_id,
        "asset_id": asset_id,
        "company_id": company_id,
        "event_type": event_type,
        "signal_date": "2025-01-15",
        "trial_phase": "phase_3",
        "primary_endpoint_met": True,
        "extraction_confidence": extraction_confidence,
        "extraction_model": "gpt-4o",
        "interim_flag": False,
        "p_value": 0.001,
        "hazard_ratio": 0.72,
    }
    _trace = json.dumps({"source_type": "test", "source_ref": "test"})
    store._conn.execute(
        """
        INSERT INTO structured_signals
            (id, extraction_result_id, event_id, company_id, asset_id, event_type,
             signal_date, payload_json, source_trace_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_id,
            str(uuid.uuid4()),
            event_id,
            company_id,
            asset_id,
            event_type,
            "2025-01-15",
            json.dumps(payload),
            _trace,
            _now_iso(),
        ),
    )
    store._conn.commit()
    return signal_id


# ---------------------------------------------------------------------------
# Import helpers under test (not the Streamlit-coupled main() function)
# ---------------------------------------------------------------------------

from bve.review_app import (
    _confidence_badge,
    _pending_diffs,
    _reviewed_diffs,
    _severity_icon,
    _signal_for_event,
    _submit_decision,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store() -> KnowledgeStore:
    s = KnowledgeStore(db_path=":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# _pending_diffs
# ---------------------------------------------------------------------------

class TestPendingDiffs:
    def test_empty_when_no_diffs(self, store: KnowledgeStore) -> None:
        assert _pending_diffs(store) == []

    def test_single_pending_diff(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-001")
        pending = _pending_diffs(store)
        assert len(pending) == 1
        assert pending[0]["run_id"] == "run-001"

    def test_multiple_pending_diffs(self, store: KnowledgeStore) -> None:
        for i in range(3):
            _insert_diff(store, run_id=f"run-{i:03d}")
        pending = _pending_diffs(store)
        assert len(pending) == 3

    def test_reviewed_diff_excluded(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-A")
        _insert_diff(store, run_id="run-B")
        # Review run-A
        _submit_decision(
            store,
            run_id="run-A",
            asset_id="asset-001",
            decision="accepted",
            reviewer_id="analyst",
            rationale="Looks good",
            override_value=None,
            reviewer_confidence=0.9,
            analyst_tags=[],
            supporting_quote=None,
        )
        pending = _pending_diffs(store)
        assert len(pending) == 1
        assert pending[0]["run_id"] == "run-B"

    def test_all_reviewed_returns_empty(self, store: KnowledgeStore) -> None:
        for run_id in ("run-X", "run-Y"):
            _insert_diff(store, run_id=run_id)
            _submit_decision(
                store,
                run_id=run_id,
                asset_id="asset-001",
                decision="rejected",
                reviewer_id="analyst",
                rationale="Disagree",
                override_value=None,
                reviewer_confidence=None,
                analyst_tags=[],
                supporting_quote=None,
            )
        assert _pending_diffs(store) == []


# ---------------------------------------------------------------------------
# _reviewed_diffs
# ---------------------------------------------------------------------------

class TestReviewedDiffs:
    def test_empty_when_no_decisions(self, store: KnowledgeStore) -> None:
        _insert_diff(store)
        assert _reviewed_diffs(store) == []

    def test_appears_after_decision(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-rev")
        _submit_decision(
            store,
            run_id="run-rev",
            asset_id="asset-001",
            decision="accepted",
            reviewer_id="analyst",
            rationale="Approved",
            override_value=None,
            reviewer_confidence=0.8,
            analyst_tags=[],
            supporting_quote=None,
        )
        reviewed = _reviewed_diffs(store)
        assert len(reviewed) == 1
        assert reviewed[0]["run_id"] == "run-rev"
        assert reviewed[0]["decision"] == "accepted"

    def test_decision_columns_present(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-cols")
        _submit_decision(
            store,
            run_id="run-cols",
            asset_id="asset-001",
            decision="rejected",
            reviewer_id="rev-42",
            rationale="Not credible",
            override_value=None,
            reviewer_confidence=None,
            analyst_tags=[],
            supporting_quote=None,
        )
        row = _reviewed_diffs(store)[0]
        assert row["decision"] == "rejected"
        assert row["reviewer_id"] == "rev-42"
        assert row["delta_npv"] is not None


# ---------------------------------------------------------------------------
# _signal_for_event
# ---------------------------------------------------------------------------

class TestSignalForEvent:
    def test_returns_none_when_absent(self, store: KnowledgeStore) -> None:
        result = _signal_for_event(store, "nonexistent-event-id")
        assert result is None

    def test_returns_payload(self, store: KnowledgeStore) -> None:
        event_id = str(uuid.uuid4())
        _insert_signal(store, event_id, extraction_confidence=0.75)
        signal = _signal_for_event(store, event_id)
        assert signal is not None
        assert signal["event_id"] == event_id
        assert signal["extraction_confidence"] == pytest.approx(0.75)

    def test_fields_from_payload(self, store: KnowledgeStore) -> None:
        event_id = str(uuid.uuid4())
        _insert_signal(store, event_id)
        signal = _signal_for_event(store, event_id)
        assert signal["trial_phase"] == "phase_3"
        assert signal["primary_endpoint_met"] is True
        assert signal["p_value"] == pytest.approx(0.001)
        assert signal["hazard_ratio"] == pytest.approx(0.72)


# ---------------------------------------------------------------------------
# _submit_decision
# ---------------------------------------------------------------------------

class TestSubmitDecision:
    def test_decision_persisted(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-submit")
        _submit_decision(
            store,
            run_id="run-submit",
            asset_id="asset-001",
            decision="accepted",
            reviewer_id="analyst-dj",
            rationale="Data convincing",
            override_value=None,
            reviewer_confidence=0.9,
            analyst_tags=["high_quality"],
            supporting_quote="IGA 0/1 at Week 16: 42% vs 8%",
        )
        decisions = store.get_review_decisions(decision="accepted")
        assert len(decisions) == 1
        d = decisions[0]
        assert d.decision == "accepted"
        assert d.reviewer_id == "analyst-dj"
        assert d.rationale == "Data convincing"

    def test_reviewer_confidence_stored(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-conf")
        _submit_decision(
            store,
            run_id="run-conf",
            asset_id="asset-001",
            decision="accepted",
            reviewer_id="analyst",
            rationale="Good",
            override_value=None,
            reviewer_confidence=0.85,
            analyst_tags=[],
            supporting_quote=None,
        )
        decisions = store.get_review_decisions()
        assert decisions[0].reviewer_confidence == pytest.approx(0.85)

    def test_analyst_tags_round_trip(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-tags")
        _submit_decision(
            store,
            run_id="run-tags",
            asset_id="asset-001",
            decision="rejected",
            reviewer_id="analyst",
            rationale="Tags test",
            override_value=None,
            reviewer_confidence=None,
            analyst_tags=["interim_only", "surrogate_endpoint"],
            supporting_quote=None,
        )
        decisions = store.get_review_decisions()
        assert decisions[0].analyst_tags == ["interim_only", "surrogate_endpoint"]

    def test_supporting_quote_round_trip(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-quote")
        _submit_decision(
            store,
            run_id="run-quote",
            asset_id="asset-001",
            decision="accepted",
            reviewer_id="analyst",
            rationale="With quote",
            override_value=None,
            reviewer_confidence=None,
            analyst_tags=[],
            supporting_quote="ORR 42% (95% CI: 31–54%)",
        )
        decisions = store.get_review_decisions()
        assert decisions[0].supporting_quote == "ORR 42% (95% CI: 31–54%)"

    def test_override_value_stored(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-override")
        _submit_decision(
            store,
            run_id="run-override",
            asset_id="asset-001",
            decision="accepted",
            reviewer_id="analyst",
            rationale="Modified",
            override_value=0.72,
            reviewer_confidence=None,
            analyst_tags=[],
            supporting_quote=None,
        )
        decisions = store.get_review_decisions()
        assert decisions[0].override_value == pytest.approx(0.72)

    def test_audit_log_entry_created(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-audit")
        _submit_decision(
            store,
            run_id="run-audit",
            asset_id="asset-001",
            decision="rejected",
            reviewer_id="analyst",
            rationale="Audit test",
            override_value=None,
            reviewer_confidence=None,
            analyst_tags=[],
            supporting_quote=None,
        )
        rows = store.query_audit_log(action="rejected")
        assert len(rows) >= 1
        assert any(r["action"] == "rejected" for r in rows)

    def test_deferred_decision(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-deferred")
        _submit_decision(
            store,
            run_id="run-deferred",
            asset_id="asset-001",
            decision="deferred",
            reviewer_id="analyst",
            rationale="Need more data",
            override_value=None,
            reviewer_confidence=0.3,
            analyst_tags=["needs_followup"],
            supporting_quote=None,
        )
        decisions = store.get_review_decisions(decision="deferred")
        assert len(decisions) == 1
        assert decisions[0].decision == "deferred"


# ---------------------------------------------------------------------------
# Post-decision queue state
# ---------------------------------------------------------------------------

class TestQueueStateTransitions:
    def test_diff_moves_pending_to_reviewed(self, store: KnowledgeStore) -> None:
        _insert_diff(store, run_id="run-trans")
        assert len(_pending_diffs(store)) == 1
        assert len(_reviewed_diffs(store)) == 0

        _submit_decision(
            store,
            run_id="run-trans",
            asset_id="asset-001",
            decision="accepted",
            reviewer_id="analyst",
            rationale="OK",
            override_value=None,
            reviewer_confidence=None,
            analyst_tags=[],
            supporting_quote=None,
        )

        assert len(_pending_diffs(store)) == 0
        assert len(_reviewed_diffs(store)) == 1

    def test_multiple_diffs_partial_review(self, store: KnowledgeStore) -> None:
        for i in range(5):
            _insert_diff(store, run_id=f"run-multi-{i}")

        # Review first 2
        for i in range(2):
            _submit_decision(
                store,
                run_id=f"run-multi-{i}",
                asset_id="asset-001",
                decision="accepted",
                reviewer_id="analyst",
                rationale="OK",
                override_value=None,
                reviewer_confidence=None,
                analyst_tags=[],
                supporting_quote=None,
            )

        assert len(_pending_diffs(store)) == 3
        assert len(_reviewed_diffs(store)) == 2


# ---------------------------------------------------------------------------
# _confidence_badge
# ---------------------------------------------------------------------------

class TestConfidenceBadge:
    def test_none_returns_na(self) -> None:
        assert "n/a" in _confidence_badge(None)

    def test_high_confidence_green(self) -> None:
        badge = _confidence_badge(0.85)
        assert "🟢" in badge
        assert "85%" in badge

    def test_medium_confidence_yellow(self) -> None:
        badge = _confidence_badge(0.65)
        assert "🟡" in badge

    def test_low_confidence_red(self) -> None:
        badge = _confidence_badge(0.3)
        assert "🔴" in badge

    def test_boundary_80_percent(self) -> None:
        assert "🟢" in _confidence_badge(0.80)

    def test_boundary_50_percent(self) -> None:
        assert "🟡" in _confidence_badge(0.50)

    def test_boundary_just_below_50(self) -> None:
        assert "🔴" in _confidence_badge(0.49)


# ---------------------------------------------------------------------------
# _severity_icon
# ---------------------------------------------------------------------------

class TestSeverityIcon:
    def test_none_returns_white(self) -> None:
        assert _severity_icon(None) == "⚪"

    def test_above_100_red(self) -> None:
        assert _severity_icon(150.0) == "🔴"

    def test_negative_above_100_red(self) -> None:
        assert _severity_icon(-120.0) == "🔴"

    def test_exactly_100_red(self) -> None:
        assert _severity_icon(100.1) == "🔴"

    def test_25_to_100_yellow(self) -> None:
        assert _severity_icon(50.0) == "🟡"
        assert _severity_icon(-50.0) == "🟡"

    def test_boundary_25_yellow(self) -> None:
        assert _severity_icon(25.0) == "🟡"

    def test_below_25_white(self) -> None:
        assert _severity_icon(10.0) == "⚪"
        assert _severity_icon(0.0) == "⚪"

    def test_boundary_just_under_25_white(self) -> None:
        assert _severity_icon(24.9) == "⚪"
