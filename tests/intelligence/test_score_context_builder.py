"""Tests for the live-scanner score-context builder (commit 1)."""
from __future__ import annotations

import datetime as dt

from bve.intelligence.composite_scorer import CompositeScorer
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.score_context_builder import (
    build_asset_context,
    build_score_contexts,
)
from bve.intelligence.taxonomy import EventType

_TODAY = dt.date(2026, 6, 16)


def _sig(sid="s1", *, asset="asset-A", days_ago=5, **fields) -> StructuredSignal:
    base = dict(
        id=sid, event_id=f"evt-{sid}", asset_id=asset, company_id="co-A",
        event_type=EventType.TRIAL_READOUT, signal_date=_TODAY - dt.timedelta(days=days_ago),
        extraction_model="test", extraction_confidence=0.9,
        created_at=dt.datetime(2026, 6, 11, tzinfo=dt.timezone.utc),
    )
    base.update(fields)
    return StructuredSignal(**base)


class _Rec:
    def __init__(self, payload):
        self.payload_json = payload


class _FakeStore:
    def __init__(self, by_asset):
        self._by = by_asset

    def get_structured_signals(self, *, asset_id=None, date_from=None, date_to=None, limit=100):
        return [_Rec(s.model_dump(mode="json")) for s in self._by.get(asset_id, [])]


# ── build_asset_context (pure) ───────────────────────────────────────────────────

class TestBuildAssetContext:
    def test_no_signals_returns_none(self):
        assert build_asset_context([]) is None

    def test_positive_readout_sets_catalyst_and_endpoint_z(self):
        ctx = build_asset_context([_sig(primary_endpoint_met=True, p_value=0.001)])
        assert ctx is not None
        assert ctx.context.catalyst_signal_strength == 0.6
        assert ctx.context.endpoint_z_score > 0
        assert ctx.contributing_signal_ids == ("s1",)
        assert ctx.contributing_event_ids == ("evt-s1",)

    def test_missed_endpoint_is_negative(self):
        ctx = build_asset_context([_sig(primary_endpoint_met=False, p_value=0.20)])
        assert ctx.context.catalyst_signal_strength == -0.6
        assert ctx.context.endpoint_z_score < 0

    def test_fda_approval_dominates(self):
        ctx = build_asset_context([_sig(fda_action_type="approval", primary_endpoint_met=False)])
        assert ctx.context.catalyst_signal_strength == 1.0  # FDA action overrides endpoint

    def test_crl_is_strong_negative(self):
        ctx = build_asset_context([_sig(fda_action_type="crl")])
        assert ctx.context.catalyst_signal_strength == -1.0

    def test_severe_safety_negative(self):
        ctx = build_asset_context([_sig(safety_grade=5)])
        assert ctx.context.catalyst_signal_strength == -0.8

    def test_terminated_enrollment_sets_slippage(self):
        ctx = build_asset_context([_sig(enrollment_status="terminated")])
        assert ctx.context.enrollment_slippage_alert is True

    def test_strongest_catalyst_selected(self):
        ctx = build_asset_context([
            _sig("weak", primary_endpoint_met=True, days_ago=3),
            _sig("strong", fda_action_type="crl", days_ago=10),
        ])
        assert ctx.context.catalyst_signal_strength == -1.0  # |crl| > |endpoint met|

    def test_neutral_signal_yields_no_context(self):
        # A signal with no mappable field → neutral → None.
        assert build_asset_context([_sig(event_type=EventType.TRIAL_READOUT)]) is None


# ── build_score_contexts (over a store) ──────────────────────────────────────────

class TestBuildScoreContexts:
    def test_only_assets_with_signals_included(self):
        store = _FakeStore({"asset-A": [_sig(primary_endpoint_met=True, p_value=0.01)]})
        out = build_score_contexts(store, ["asset-A", "asset-B"], as_of=_TODAY)
        assert set(out) == {"asset-A"}

    def test_signal_moves_the_composite_score(self):
        store = _FakeStore({"asset-A": [_sig(primary_endpoint_met=True, p_value=0.001)]})
        out = build_score_contexts(store, ["asset-A"], as_of=_TODAY)
        adj = CompositeScorer().compute_adjustments(out["asset-A"].context)
        assert CompositeScorer.total(adj) > 0  # positive readout lifts the score

    def test_malformed_payload_skipped(self):
        class _BadStore:
            def get_structured_signals(self, **kw):
                return [_Rec({"not": "a signal"}), _Rec("garbage")]

        assert build_score_contexts(_BadStore(), ["asset-A"], as_of=_TODAY) == {}

    def test_passes_bounded_lookback_window_to_store(self):
        seen = {}

        class _CapturingStore:
            def get_structured_signals(self, *, asset_id=None, date_from=None, date_to=None, limit=100):
                seen["date_from"] = date_from
                seen["date_to"] = date_to
                return []

        build_score_contexts(_CapturingStore(), ["asset-A"], as_of=_TODAY, lookback_days=90)
        assert seen["date_to"] == _TODAY
        assert seen["date_from"] == _TODAY - dt.timedelta(days=90)
