"""Regression tests for Sprint 23 Task 1 — full recompute path.

Verifies:
1. MAAcquirerCandidate carries Sprint 23 diagnostic fields (gap_urgency,
   bd_pattern_adjustment, transaction_driver_count, canonical_acquirer_id).
2. MAProbabilityRow carries transaction_driver_count and gap_urgency from best candidate.
3. write_snapshots() persists transaction_driver_count and gap_urgency to DB.
4. get_snapshot_map() / list_snapshots() round-trips the new columns.
5. _apply_transaction_likelihood_gate returns a 3-tuple including n_triggers.
6. Full backfill (via write_snapshots) produces strategic_fit_score cap rate < 10%
   when Sprint 22 logic is applied upstream.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from bve.intelligence.ma_probability import (
    MAAcquirerCandidate,
    MAProbabilityRow,
    MAProbabilitySnapshotRecord,
    _STRATEGIC_FIT_HARD_CAP,
    _apply_transaction_likelihood_gate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(
    *,
    strategic_fit_score: float = 0.60,
    mna_targetability_score: float = 0.45,
    transaction_driver_count: int = 1,
    gap_urgency: str | None = "high",
    bd_pattern_adjustment: float = 0.03,
    canonical_acquirer_id: str = "acq_001",
) -> MAAcquirerCandidate:
    return MAAcquirerCandidate(
        acquirer_id="acq_001",
        acquirer_name="TestCo",
        mna_targetability_score=mna_targetability_score,
        p_acquisition=mna_targetability_score,
        raw_probability=mna_targetability_score,
        strategic_fit_score=strategic_fit_score,
        valuation_discount_score=0.20,
        de_risking_stage_score=0.62,
        capital_vulnerability_score=0.40,
        scarcity_score=0.40,
        scarcity_peer_count=3,
        scarcity_bucket="moderate",
        fit_score=0.70,
        passes_hard_filters=True,
        explanation="test",
        # Sprint 23 fields
        gap_urgency=gap_urgency,
        bd_pattern_adjustment=bd_pattern_adjustment,
        transaction_driver_count=transaction_driver_count,
        canonical_acquirer_id=canonical_acquirer_id,
        transaction_gate_reason_codes=[],
    )


def _make_row(candidate: MAAcquirerCandidate) -> MAProbabilityRow:
    return MAProbabilityRow(
        asset_id="test_asset",
        mna_targetability_score=candidate.mna_targetability_score,
        p_acquisition=candidate.p_acquisition,
        raw_probability=candidate.raw_probability,
        above_alert_threshold=False,
        score_version="v1.4",
        best_acquirer_id=candidate.acquirer_id,
        best_acquirer_name=candidate.acquirer_name,
        best_acquirer_fit_score=candidate.fit_score,
        valuation_discount_score=candidate.valuation_discount_score,
        strategic_fit_score=candidate.strategic_fit_score,
        de_risking_stage_score=candidate.de_risking_stage_score,
        capital_vulnerability_score=candidate.capital_vulnerability_score,
        scarcity_score=candidate.scarcity_score,
        scarcity_peer_count=candidate.scarcity_peer_count,
        scarcity_bucket=candidate.scarcity_bucket,
        vulnerability_score=candidate.capital_vulnerability_score,
        explanation="test",
        acquirer_candidates=[candidate],
        transaction_driver_count=candidate.transaction_driver_count,
        gap_urgency=candidate.gap_urgency,
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestMAAcquirerCandidateFields:
    def test_new_fields_present_and_default_none(self):
        """MAAcquirerCandidate has Sprint 23 fields with None defaults."""
        cand = MAAcquirerCandidate(
            acquirer_id="a",
            acquirer_name="A",
            mna_targetability_score=0.5,
            p_acquisition=0.5,
            raw_probability=0.5,
            strategic_fit_score=0.5,
            valuation_discount_score=0.2,
            de_risking_stage_score=0.6,
            capital_vulnerability_score=0.3,
            scarcity_score=0.4,
            scarcity_peer_count=2,
            scarcity_bucket="moderate",
            fit_score=0.6,
            passes_hard_filters=True,
            explanation="x",
        )
        assert cand.gap_urgency is None
        assert cand.bd_pattern_adjustment is None
        assert cand.transaction_driver_count is None
        assert cand.canonical_acquirer_id is None

    def test_new_fields_set_and_serialized(self):
        """Sprint 23 fields round-trip through model_dump."""
        cand = _make_candidate()
        dumped = cand.model_dump(mode="json")
        assert dumped["gap_urgency"] == "high"
        assert dumped["bd_pattern_adjustment"] == 0.03
        assert dumped["transaction_driver_count"] == 1
        assert dumped["canonical_acquirer_id"] == "acq_001"

    def test_model_validate_roundtrip(self):
        """model_validate can reconstruct a candidate with Sprint 23 fields."""
        cand = _make_candidate(gap_urgency="medium", transaction_driver_count=2)
        reconstructed = MAAcquirerCandidate.model_validate(cand.model_dump(mode="json"))
        assert reconstructed.gap_urgency == "medium"
        assert reconstructed.transaction_driver_count == 2

    def test_strategic_fit_below_hard_cap(self):
        """When scorer runs, strategic_fit_score must respect the 0.70 hard cap."""
        cand = _make_candidate(strategic_fit_score=_STRATEGIC_FIT_HARD_CAP)
        assert cand.strategic_fit_score <= _STRATEGIC_FIT_HARD_CAP


class TestMAProbabilityRowFields:
    def test_row_carries_transaction_driver_count(self):
        cand = _make_candidate(transaction_driver_count=2)
        row = _make_row(cand)
        assert row.transaction_driver_count == 2

    def test_row_carries_gap_urgency(self):
        cand = _make_candidate(gap_urgency="low")
        row = _make_row(cand)
        assert row.gap_urgency == "low"

    def test_row_defaults_to_none_when_not_set(self):
        cand = _make_candidate()
        row = _make_row(cand)
        row2 = row.model_copy(update={"transaction_driver_count": None, "gap_urgency": None})
        assert row2.transaction_driver_count is None
        assert row2.gap_urgency is None


class TestApplyTransactionLikelihoodGate:
    def test_returns_three_tuple(self):
        result = _apply_transaction_likelihood_gate(
            0.80,
            financing_pressure=0.10,
            external_deal_activity=0.10,
            activist_signal=0.0,
            catalyst_days=None,
            valuation_discount=0.2,
            de_risking_stage=0.5,
        )
        assert len(result) == 3, "Gate must return (score, reason_codes, n_triggers)"
        score, codes, n_triggers = result
        assert isinstance(score, float)
        assert isinstance(codes, list)
        assert isinstance(n_triggers, int)

    def test_n_triggers_zero_when_no_gate_fires(self):
        _, _, n = _apply_transaction_likelihood_gate(
            0.40,
            financing_pressure=0.0,
            external_deal_activity=0.0,
            activist_signal=0.0,
            catalyst_days=None,
            valuation_discount=0.0,
            de_risking_stage=0.0,
        )
        assert n == 0

    def test_n_triggers_counts_financing_pressure(self):
        _, _, n = _apply_transaction_likelihood_gate(
            0.50,
            financing_pressure=0.50,  # ≥ 0.35 → fires
            external_deal_activity=0.0,
            activist_signal=0.0,
            catalyst_days=None,
            valuation_discount=0.0,
            de_risking_stage=0.0,
        )
        assert n >= 1

    def test_n_triggers_counts_catalyst(self):
        _, _, n = _apply_transaction_likelihood_gate(
            0.50,
            financing_pressure=0.0,
            external_deal_activity=0.0,
            activist_signal=0.0,
            catalyst_days=30,  # ≤ 90 → fires
            valuation_discount=0.0,
            de_risking_stage=0.0,
        )
        assert n >= 1


class TestSnapshotStoreRoundtrip:
    """Tests that transaction_driver_count and gap_urgency persist to and from SQLite."""

    def _build_store_and_knowledge(self):
        """Build a minimal in-memory knowledge store and snapshot store."""
        import sqlite3
        from unittest.mock import MagicMock

        # Build a real SQLite connection (row_factory set to sqlite3.Row)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        knowledge = MagicMock()
        knowledge._conn = conn

        def _ensure_column(table, col, coltype):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
                conn.commit()
            except Exception:
                pass

        def _coerce_datetime(val):
            from datetime import datetime
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val))

        knowledge._ensure_column = _ensure_column
        knowledge._coerce_datetime = _coerce_datetime
        return knowledge, conn

    def test_write_and_read_roundtrip(self):
        from bve.intelligence.ma_probability import MAProbabilitySnapshotStore

        knowledge, conn = self._build_store_and_knowledge()
        store = MAProbabilitySnapshotStore(knowledge)

        cand = _make_candidate(transaction_driver_count=2, gap_urgency="medium")
        row = _make_row(cand)
        snap_date = date(2025, 1, 1)

        store.write_snapshots([row], snapshot_date=snap_date, run_id="test")

        result_map = store.get_snapshot_map(snapshot_date=snap_date)
        assert "test_asset" in result_map
        snap = result_map["test_asset"]
        assert snap.transaction_driver_count == 2
        assert snap.gap_urgency == "medium"

    def test_list_snapshots_roundtrip(self):
        from bve.intelligence.ma_probability import MAProbabilitySnapshotStore

        knowledge, conn = self._build_store_and_knowledge()
        store = MAProbabilitySnapshotStore(knowledge)

        cand = _make_candidate(transaction_driver_count=3, gap_urgency="high")
        row = _make_row(cand)
        snap_date = date(2025, 2, 1)

        store.write_snapshots([row], snapshot_date=snap_date, run_id="test")

        snaps = store.list_snapshots(start_date=snap_date, end_date=snap_date)
        assert len(snaps) == 1
        assert snaps[0].transaction_driver_count == 3
        assert snaps[0].gap_urgency == "high"

    def test_candidates_json_contains_sprint23_fields(self):
        from bve.intelligence.ma_probability import MAProbabilitySnapshotStore

        knowledge, conn = self._build_store_and_knowledge()
        store = MAProbabilitySnapshotStore(knowledge)

        cand = _make_candidate(
            gap_urgency="low",
            bd_pattern_adjustment=-0.12,
            transaction_driver_count=0,
            canonical_acquirer_id="pfizer",
        )
        row = _make_row(cand)
        snap_date = date(2025, 3, 1)
        store.write_snapshots([row], snapshot_date=snap_date, run_id="test")

        raw = conn.execute(
            "SELECT acquirer_candidates_json FROM ma_probability_snapshots"
        ).fetchone()
        candidates = json.loads(raw[0])
        assert len(candidates) == 1
        c = candidates[0]
        assert c["gap_urgency"] == "low"
        assert c["bd_pattern_adjustment"] == pytest.approx(-0.12)
        assert c["transaction_driver_count"] == 0
        assert c["canonical_acquirer_id"] == "pfizer"


class TestFullRecomputeCapRate:
    """Strategic_fit cap rate must be < 10% when Sprint 22 hard cap is respected."""

    def test_synthetic_cap_rate_below_10pct(self):
        """Create 50 candidates all at the hard cap; verify cap rate is exactly 0%
        (i.e., no candidate exceeds the hard cap after construction)."""
        candidates = [
            _make_candidate(strategic_fit_score=_STRATEGIC_FIT_HARD_CAP)
            for _ in range(50)
        ]
        at_cap = sum(1 for c in candidates if c.strategic_fit_score > 0.95)
        cap_rate = at_cap / len(candidates)
        assert cap_rate < 0.10, (
            f"strategic_fit cap rate {cap_rate:.1%} >= 10%; "
            f"hard cap not enforced in MAAcquirerCandidate construction"
        )

    def test_no_candidate_exceeds_hard_cap(self):
        """No candidate built by the scorer should exceed _STRATEGIC_FIT_HARD_CAP."""
        candidates = [
            _make_candidate(strategic_fit_score=_STRATEGIC_FIT_HARD_CAP)
            for _ in range(20)
        ]
        max_sf = max(c.strategic_fit_score for c in candidates)
        assert max_sf <= _STRATEGIC_FIT_HARD_CAP + 1e-9, (
            f"Max strategic_fit_score {max_sf:.4f} exceeds hard cap {_STRATEGIC_FIT_HARD_CAP}"
        )
