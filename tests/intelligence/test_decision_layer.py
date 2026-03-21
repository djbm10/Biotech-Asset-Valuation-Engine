"""Tests for Wave J — Decision + Position Layer."""
from __future__ import annotations

import tempfile
from datetime import date, timedelta

import pytest

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.decision_layer import (
    DecisionLayer,
    DecisionRecord,
    OutcomeAttribution,
    PositionSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_layer() -> tuple[DecisionLayer, KnowledgeStore]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    store = KnowledgeStore(tmp.name)
    layer = DecisionLayer(store)
    return layer, store


def _record(layer: DecisionLayer, asset_id: str = "asset-1", action: str = "buy") -> DecisionRecord:
    return layer.record_decision(
        asset_id=asset_id,
        recommended_action=action,  # type: ignore[arg-type]
        signal_id="sig-1",
        recommended_size_pct=0.05,
        signal_strength=0.75,
        portfolio_exposure_pct_at_decision=0.30,
        catalyst_bucket_exposure_pct=0.10,
        indication_bucket_exposure_pct=0.25,
        liquidity_bucket="liquid",
        conviction_tier="high",
        critic_flags_count=1,
        reasoning_text="Phase 3 readout H2 2025",
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schema_creates_tables() -> None:
    layer, store = _make_layer()
    try:
        for table in ("decision_records", "position_snapshots", "outcome_attributions"):
            row = store._conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            ).fetchone()
            assert row is not None, f"Table {table} not found"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# record_decision
# ---------------------------------------------------------------------------

def test_record_decision_returns_decision_record() -> None:
    layer, store = _make_layer()
    try:
        d = _record(layer)
        assert isinstance(d, DecisionRecord)
        assert d.recommended_action == "buy"
        assert d.executed_action is None
        assert d.asset_id == "asset-1"
    finally:
        store.close()


def test_record_decision_persists_portfolio_context() -> None:
    layer, store = _make_layer()
    try:
        d = _record(layer)
        retrieved = layer.get_decision(d.decision_id)
        assert retrieved is not None
        assert retrieved.portfolio_exposure_pct_at_decision == pytest.approx(0.30)
        assert retrieved.catalyst_bucket_exposure_pct == pytest.approx(0.10)
        assert retrieved.indication_bucket_exposure_pct == pytest.approx(0.25)
        assert retrieved.liquidity_bucket == "liquid"
        assert retrieved.conviction_tier == "high"
    finally:
        store.close()


def test_record_decision_preserves_recommendation_fields() -> None:
    layer, store = _make_layer()
    try:
        d = _record(layer)
        retrieved = layer.get_decision(d.decision_id)
        assert retrieved.recommended_action == "buy"
        assert retrieved.recommended_size_pct == pytest.approx(0.05)
        assert retrieved.critic_flags_count == 1
    finally:
        store.close()


def test_record_decision_idempotent() -> None:
    layer, store = _make_layer()
    try:
        d = _record(layer)
        # Re-insert same decision_id via INSERT OR IGNORE — should not raise
        store._conn.execute(
            "INSERT OR IGNORE INTO decision_records "
            "(decision_id, asset_id, recommended_action, decided_at) "
            "VALUES (?, 'asset-x', 'pass', datetime('now'))",
            (d.decision_id,),
        )
        store._conn.commit()
        retrieved = layer.get_decision(d.decision_id)
        assert retrieved.asset_id == "asset-1"  # original preserved
    finally:
        store.close()


# ---------------------------------------------------------------------------
# update_execution
# ---------------------------------------------------------------------------

def test_update_execution_records_executed_action() -> None:
    layer, store = _make_layer()
    try:
        d = _record(layer)
        updated = layer.update_execution(d.decision_id, "hold", 0.03)
        assert updated is not None
        assert updated.executed_action == "hold"
        assert updated.executed_size_pct == pytest.approx(0.03)
    finally:
        store.close()


def test_update_execution_recommended_unchanged() -> None:
    layer, store = _make_layer()
    try:
        d = _record(layer)
        updated = layer.update_execution(d.decision_id, "pass")
        assert updated.recommended_action == "buy"   # unchanged
        assert updated.executed_action == "pass"
    finally:
        store.close()


def test_update_execution_unknown_decision_returns_none() -> None:
    layer, store = _make_layer()
    try:
        result = layer.update_execution("nonexistent", "buy")
        assert result is None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# model_vs_execution_drift
# ---------------------------------------------------------------------------

def test_model_vs_execution_drift_empty() -> None:
    layer, store = _make_layer()
    try:
        drift = layer.model_vs_execution_drift()
        assert drift["n_total"] == 0
        assert drift["n_diverged"] == 0
        assert drift["pct_diverged"] is None
    finally:
        store.close()


def test_model_vs_execution_drift_no_divergence() -> None:
    layer, store = _make_layer()
    try:
        d = _record(layer)
        layer.update_execution(d.decision_id, "buy")  # same as recommended
        drift = layer.model_vs_execution_drift()
        assert drift["n_diverged"] == 0
        assert drift["pct_diverged"] == pytest.approx(0.0)
    finally:
        store.close()


def test_model_vs_execution_drift_with_divergence() -> None:
    layer, store = _make_layer()
    try:
        d1 = _record(layer, "a1", "buy")
        d2 = _record(layer, "a2", "buy")
        layer.update_execution(d1.decision_id, "buy")    # same
        layer.update_execution(d2.decision_id, "pass")   # different
        drift = layer.model_vs_execution_drift()
        assert drift["n_diverged"] == 1
        assert drift["pct_diverged"] == pytest.approx(0.5)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# record_position
# ---------------------------------------------------------------------------

def test_record_position_creates_active_position() -> None:
    layer, store = _make_layer()
    try:
        pos = layer.record_position(
            "asset-1", 0.05,
            entry_date=date(2025, 1, 10),
            entry_price_usd=12.50,
        )
        assert isinstance(pos, PositionSnapshot)
        assert pos.is_active is True
        assert pos.holding_period_days is None
    finally:
        store.close()


def test_get_active_positions_returns_open_only() -> None:
    layer, store = _make_layer()
    try:
        layer.record_position("a1", 0.05)
        layer.record_position("a2", 0.03)
        active = layer.get_active_positions()
        assert len(active) == 2
    finally:
        store.close()


# ---------------------------------------------------------------------------
# close_position
# ---------------------------------------------------------------------------

def test_close_position_sets_is_active_false() -> None:
    layer, store = _make_layer()
    try:
        layer.record_position("asset-1", 0.05, entry_date=date(2025, 1, 1))
        closed = layer.close_position(
            "asset-1", exit_price_usd=15.00, exit_reason="profit_target",
            exit_date=date(2025, 3, 15),
        )
        assert closed is not None
        assert closed.is_active is False
        assert closed.exit_reason == "profit_target"
    finally:
        store.close()


def test_close_position_computes_holding_period() -> None:
    layer, store = _make_layer()
    try:
        layer.record_position("asset-1", 0.05, entry_date=date(2025, 1, 1))
        closed = layer.close_position(
            "asset-1", exit_date=date(2025, 3, 1)
        )
        assert closed.holding_period_days == 59
    finally:
        store.close()


def test_close_position_no_active_position_returns_none() -> None:
    layer, store = _make_layer()
    try:
        result = layer.close_position("no-such-asset")
        assert result is None
    finally:
        store.close()


def test_close_position_removes_from_active() -> None:
    layer, store = _make_layer()
    try:
        layer.record_position("asset-1", 0.05, entry_date=date(2025, 1, 1))
        layer.close_position("asset-1", exit_date=date(2025, 2, 1))
        active = layer.get_active_positions()
        assert len(active) == 0
    finally:
        store.close()


# ---------------------------------------------------------------------------
# attribute_outcome
# ---------------------------------------------------------------------------

def test_attribute_outcome_returns_attribution() -> None:
    layer, store = _make_layer()
    try:
        d = _record(layer)
        attr = layer.attribute_outcome(d.decision_id, 0.18, "confirmed_thesis")
        assert isinstance(attr, OutcomeAttribution)
        assert attr.return_pct == pytest.approx(0.18)
        assert attr.attribution_type == "confirmed_thesis"
    finally:
        store.close()


def test_attribute_outcome_links_asset_id() -> None:
    layer, store = _make_layer()
    try:
        d = _record(layer, "asset-xyz")
        attr = layer.attribute_outcome(d.decision_id, -0.12, "pos_error")
        assert attr.asset_id == "asset-xyz"
    finally:
        store.close()


def test_get_attributions_filter_by_type() -> None:
    layer, store = _make_layer()
    try:
        d1 = _record(layer, "a1")
        d2 = _record(layer, "a2")
        layer.attribute_outcome(d1.decision_id, 0.10, "confirmed_thesis")
        layer.attribute_outcome(d2.decision_id, -0.05, "pos_error")
        pos_errors = layer.get_attributions(attribution_type="pos_error")
        assert len(pos_errors) == 1
        assert pos_errors[0].attribution_type == "pos_error"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# get_decision_history
# ---------------------------------------------------------------------------

def test_get_decision_history_returns_all() -> None:
    layer, store = _make_layer()
    try:
        _record(layer, "a1")
        _record(layer, "a2")
        _record(layer, "a3")
        history = layer.get_decision_history()
        assert len(history) == 3
    finally:
        store.close()


def test_get_decision_history_filter_by_asset() -> None:
    layer, store = _make_layer()
    try:
        _record(layer, "a1")
        _record(layer, "a1")
        _record(layer, "a2")
        history = layer.get_decision_history("a1")
        assert len(history) == 2
        assert all(d.asset_id == "a1" for d in history)
    finally:
        store.close()
